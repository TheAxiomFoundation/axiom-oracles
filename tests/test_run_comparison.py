import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_run_comparison_module():
    module_path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_script_module(name: str):
    module_path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_path_uses_repo_env_override_when_config_path_is_missing(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    override = tmp_path / "axiom-encode"
    override.mkdir()
    monkeypatch.setenv("AXIOM_ENCODE_REPO", str(override))

    resolved = run_comparison._resolve_path(
        str(tmp_path / "missing-axiom-encode"), "axiom_encode_repo"
    )

    assert resolved == override.resolve()


def test_tax_ecps_runner_uses_current_python_and_policyengine_us(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    axiom_encode = tmp_path / "axiom-encode"
    axiom_rules = tmp_path / "axiom-rules-engine"
    rulespec = tmp_path / "workspace" / "rulespec-us"
    axiom_encode.mkdir()
    axiom_rules.mkdir()
    rulespec.mkdir(parents=True)
    output = tmp_path / "report.json"
    calls = []

    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        run_comparison, "_ensure_rulespec_us_checkout", lambda _remote: rulespec
    )

    def fake_run(cmd, *, check, stdout=None, cwd=None, capture_output=False, text=False):
        del check, cwd, capture_output, text
        calls.append(cmd)
        if stdout is not None:
            stdout.write("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    runner_config = {
        "axiom_encode_repo": str(axiom_encode),
        "axiom_rules_repo": str(axiom_rules),
        "rulespec_remote": "https://example.test/rulespec-us.git",
        "parameters": {
            "sample_size": 1000,
            "year": 2026,
            "python": "3.13",
            "surface": "all",
            # No data_folder: Populace loads from the pinned HF cache, so the
            # live fiit-ecps.yaml omits the key. Assert --data-folder is then
            # not passed (and note passing a missing dir would SystemExit).
            "pinned": True,
        },
    }
    run_comparison._run_axiom_encode_tax_ecps_compare(runner_config, output)

    cmd = calls[-1]
    # The encoder renamed the subcommand in its ECPS→Populace rename; no
    # `tax-ecps-compare` alias survives on axiom-encode main (#296).
    assert "tax-populace-compare" in cmd
    assert "tax-ecps-compare" not in cmd
    # The runner records the temp clone's HEAD before deleting it so
    # provenance can stamp a real rulespec-us SHA (None here: not a git repo).
    assert "_cloned_rulespec_us_sha" in runner_config
    assert cmd[:4] == ["uv", "run", "--python", "3.13"]
    assert "--with-editable" in cmd
    assert str(axiom_encode.resolve()) in cmd
    assert "policyengine==4.11.0" in cmd
    # 1.729.0 is the version the certified pinned Populace artifact was built
    # with and clears the harness floor (MIN_POLICYENGINE_US_VERSION 1.723);
    # the old 1.705.16 pin was below the floor and failed hard.
    assert "policyengine-us==1.729.0" in cmd
    assert "policyengine-core==3.26.11" in cmd
    assert "--data-folder" not in cmd
    assert "--allow-policyengine-us-version" in cmd
    assert "--allow-uncertified-policyengine-data" in cmd
    assert output.read_text() == "{}"


def test_axiom_oracles_runner_composes_declared_program(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    axiom_rules = tmp_path / "axiom-rules-engine"
    compose_binary = tmp_path / "axiom-compose"
    program = tmp_path / "axiom-programs" / "us-al" / "snap" / "fy-2026.yaml"
    rulespec_us = tmp_path / "rulespec-us"
    rulespec_al = tmp_path / "rulespec-us-al"
    composed = tmp_path / "al-snap-composed.yaml"
    compiled = tmp_path / "al-snap-compiled.json"
    output = tmp_path / "report.json"
    for path in (axiom_rules, rulespec_us, rulespec_al, program.parent):
        path.mkdir(parents=True, exist_ok=True)
    compose_binary.write_text("#!/bin/sh\n")
    program.write_text("program: us-al/snap\n")
    calls = []

    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_args, **_kwargs: None
    )

    def fake_run(cmd, *, check=False, cwd=None, env=None, text=False,
                 capture_output=False, stdout=None, timeout=None):
        del check, cwd, env, text, capture_output, stdout, timeout
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_oracles_compare(
        {
            "axiom_rules_repo": str(axiom_rules),
            "parameters": {
                "left": "axiom",
                "right": "policyengine",
                "concepts": [
                    "us:statutes/7/2014/o#snap_eligible",
                    "us:statutes/7/2014/u#snap_benefit",
                ],
                "sample_size": 0,
                "period": "2026-01",
                "population": "enhanced-cps",
                "axiom_compose_binary": str(compose_binary),
                "axiom_program": str(program),
                "axiom_composed_program": str(composed),
                "axiom_compiled_program": str(compiled),
                "rulespec_roots": [str(rulespec_us), str(rulespec_al)],
                "axiom_rulespec_repo_roots": str(tmp_path),
                "jurisdiction_fips": "01",
            },
        },
        output,
    )

    assert calls[0] == [
        str(compose_binary.resolve()),
        str(program.resolve()),
        "--rulespec-root",
        str(rulespec_us.resolve()),
        "--rulespec-root",
        str(rulespec_al.resolve()),
        "-o",
        str(composed.resolve()),
    ]
    # The engine compile carries explicit --rulespec-root flags now
    # (post-hard-cut contract); rulespec-us-al is not a valid engine root
    # (two-letter country checkouts only) and must not be passed (#296).
    engine_cmd = calls[1]
    assert engine_cmd[0] == str(
        axiom_rules.resolve() / "target" / "release" / "axiom-rules-engine"
    )
    assert engine_cmd[1] == "compile"
    assert engine_cmd[engine_cmd.index("--program") + 1] == str(composed.resolve())
    assert engine_cmd[engine_cmd.index("--output") + 1] == str(compiled.resolve())
    root_flags = [
        engine_cmd[i + 1]
        for i, tok in enumerate(engine_cmd)
        if tok == "--rulespec-root"
    ]
    assert root_flags == [str(rulespec_us.resolve())]
    assert calls[2][:4] == ["uv", "run", "--python", "3.14"]
    assert "--axiom-compiled-program" in calls[2]
    assert str(compiled.resolve()) in calls[2]


def test_snap_ecps_runner_writes_v2_report_from_csv(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    axiom_encode = tmp_path / "axiom-encode"
    axiom_rules = tmp_path / "axiom-rules-engine"
    axiom_encode.mkdir()
    axiom_rules.mkdir()
    output = tmp_path / "report.json"
    calls = []

    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_args, **_kwargs: None
    )

    def fake_run(cmd, *, check, cwd=None):
        del check, cwd
        calls.append(cmd)
        csv_path = cmd[cmd.index("--write-csv") + 1]
        Path(csv_path).write_text(
            "spm_unit_id,household_id,pe_snap,axiom_snap_allotment,"
            "difference,absolute_difference,match,pe_snap_eligible,"
            "axiom_snap_eligible,pe_gross_income,axiom_gross_income,"
            "pe_net_income,axiom_net_income,pe_utility_allowance,"
            "axiom_utility_allowance,pe_shelter_deduction,"
            "axiom_shelter_deduction,"
            "pe_standard_deduction,"
            "axiom_ny_snap_categorically_eligible,"
            "axiom_ny_snap_residual_130_percent_categorical_path_satisfied\n"
            "101,201,77.20,76.00,-1.20,1.20,True,True,True,"
            "1200,1200,900,900,200,200,50,50,209,not_holds,not_holds\n"
            "102,202,0.00,24.00,24.00,24.00,False,False,holds,"
            "12000,12000,9000,9000,0,0,0,0,209,holds,holds\n"
        )
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_encode_snap_ecps_compare(
        {
            "axiom_encode_repo": str(axiom_encode),
            "axiom_rules_repo": str(axiom_rules),
            "parameters": {
                "jurisdiction": "us-co",
                "sample_size": 0,
                "year": 2026,
                "month": 1,
                "utility_projection": "policyengine-type",
                "tolerance": 1.5,
            },
        },
        output,
    )

    cmd = calls[0]
    assert cmd[:3] == ["uv", "run", "--directory"]
    assert str(axiom_encode.resolve()) in cmd
    assert "snap-populace-compare" in cmd
    assert "--sample-size" not in cmd
    assert "--axiom-binary" in cmd

    report = json.loads(output.read_text())
    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["case_count"] == 2
    assert report["summary"]["comparison_count"] == 4
    assert report["summary"]["mismatch_count"] == 2
    assert report["aggregates"][0]["matched"] == 1
    assert report["aggregates"][0]["comparison"] == "amount"
    assert report["aggregates"][1]["comparison"] == "eligibility"
    assert report["aggregates"][1]["matched"] == 1
    # Every row is a case now — matched concepts carry both engines'
    # values as evidence, mismatching ones stay in `mismatches`.
    assert len(report["cases"]) == 2
    by_id = {c["case_id"]: c for c in report["cases"]}
    matched = by_id["ecps-spm-101"]
    assert matched["match_rate"] == 100.0
    assert not matched["mismatches"]
    assert {m["concept"] for m in matched["matches"]} == {
        "us:statutes/7/2014/u#snap_benefit",
        "us:statutes/7/2014/o#snap_eligible",
    }
    mismatched = by_id["ecps-spm-102"]
    assert len(mismatched["mismatches"]) == 2
    assert "matches" not in mismatched
    assert mismatched["metadata"]["axiom_ny_snap_categorically_eligible"]
    assert mismatched["metadata"][
        "axiom_ny_snap_residual_130_percent_categorical_path_satisfied"
    ]
    assert report["cases"][0]["metadata"]["pe_standard_deduction"] == 209


def test_snap_qc_runner_registered_and_reemits_committed_report(monkeypatch, tmp_path):
    """The snap-qc-compare runner is registered and, when the replay cannot run
    here (no engine binary / dated rulespec / QC file, or the bridge is mid-build),
    re-emits the committed dashboard report — the euromod graceful-skip contract.
    No engine or data is needed, exactly as the runner promises."""
    run_comparison = load_run_comparison_module()

    assert run_comparison.RUNNERS["snap-qc-compare"] is (
        run_comparison._run_snap_qc_compare
    )

    dashboard_dir = tmp_path / "dashboard-data"
    dashboard_dir.mkdir()
    committed = dashboard_dir / "axiom-snapqc-co-snap.json"
    committed.write_text('{"schema_version": "axiom.comparison_report.v2"}')
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard_dir)
    # Force the skip path without touching the engine, rulespec, or QC file.
    monkeypatch.setattr(
        run_comparison, "_snap_qc_skip_reason", lambda *_a, **_k: "forced skip"
    )

    output = tmp_path / "report.json"
    run_comparison._run_snap_qc_compare(
        {
            "parameters": {
                "jurisdiction": "us-co",
                "fiscal_year": 2024,
                "sample_size": 0,
                "dashboard_filename": "axiom-snapqc-co-snap.json",
            }
        },
        output,
    )

    assert output.read_text() == committed.read_text()


def test_snap_qc_runner_writes_v2_shell_when_no_committed_report(monkeypatch, tmp_path):
    """With nothing committed yet, the skip path writes a valid empty v2 report
    recording the skip reason, so the weekly matrix never crashes on a first run."""
    run_comparison = load_run_comparison_module()

    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", tmp_path / "empty")
    monkeypatch.setattr(
        run_comparison, "_snap_qc_skip_reason", lambda *_a, **_k: "no engine here"
    )

    output = tmp_path / "report.json"
    run_comparison._run_snap_qc_compare(
        {"parameters": {"suite": "co-snap-qc", "dashboard_filename": "missing.json"}},
        output,
    )

    report = json.loads(output.read_text())
    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["suite"] == "co-snap-qc"
    assert report["case_count"] == 0
    assert report["errors"] == ["skipped: no engine here"]


def test_gettsim_synthetic_runner_registered_and_reemits_committed_report(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()

    assert run_comparison.RUNNERS["gettsim-synthetic-compare"] is (
        run_comparison._run_gettsim_synthetic_compare
    )

    dashboard_dir = tmp_path / "dashboard-data"
    dashboard_dir.mkdir()
    committed = dashboard_dir / "euromod-gettsim-de-worker-dual-oracle.json"
    committed.write_text('{"schema_version": "axiom.comparison_report.v2.1"}')
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard_dir)
    monkeypatch.setattr(
        run_comparison,
        "_gettsim_synthetic_skip_reason",
        lambda _params: ("forced skip", None),
    )

    output = tmp_path / "report.json"
    run_comparison._run_gettsim_synthetic_compare(
        {
            "parameters": {
                "suite": "de-worker-dual-oracle",
                "dashboard_filename": committed.name,
            }
        },
        output,
    )

    assert output.read_text() == committed.read_text()


def test_gettsim_synthetic_runner_compares_requested_sample(monkeypatch, tmp_path):
    from axiom_oracles.adapters.euromod import EuromodPlatformRunner
    from axiom_oracles.adapters.gettsim import GettsimRunner
    from axiom_oracles.core.results import EngineResult

    run_comparison = load_run_comparison_module()
    monkeypatch.setenv("EUROMOD_PYTHON", "/fake/euromod-python")
    monkeypatch.setattr(
        run_comparison,
        "_gettsim_synthetic_skip_reason",
        lambda _params: (None, tmp_path),
    )

    def fake_euromod_run(self, cases, variables):
        assert len(cases) == 1
        assert self.extra_columns == ("drgn1",)
        assert set(variables) == {
            "tsceehl_s",
            "tsceepi_s",
            "tsceeui_s",
            "tsceeci_s",
            "tin_s",
            "bch00_s",
        }
        return [
            EngineResult(
                engine="euromod",
                household_id=cases[0].case_id,
                values={variable: 0.0 for variable in variables},
            )
        ]

    def fake_gettsim_run(_self, _case, targets):
        aliases = {
            leaf
            for branch in targets.values()
            for leaf in _target_aliases(branch)
        }
        return SimpleNamespace(values={alias: [0.0] for alias in aliases})

    monkeypatch.setattr(EuromodPlatformRunner, "run_cases", fake_euromod_run)
    monkeypatch.setattr(GettsimRunner, "run_case", fake_gettsim_run)
    monkeypatch.setattr(
        GettsimRunner,
        "run_metadata",
        lambda _self: {
            "engine": "gettsim",
            "gettsim_version": "1.2.1",
            "policy_date_str": "2025-06-30",
            "rounding": True,
        },
    )

    output = tmp_path / "report.json"
    run_comparison._run_gettsim_synthetic_compare(
        {
            "parameters": {
                "suite": "de-worker-dual-oracle",
                "sample_size": 1,
                "euromod_extra_columns": ["drgn1"],
            }
        },
        output,
    )

    report = json.loads(output.read_text())
    assert report["engines"] == {"left": "euromod", "right": "gettsim"}
    assert report["case_count"] == 1
    assert report["summary"]["comparison_count"] == 6
    assert report["summary"]["mismatch_count"] == 0
    assert report["summary"]["error_count"] == 0
    assert report["engine_metadata"]["euromod"]["extra_columns"] == ["drgn1"]
    assert report["engine_metadata"]["gettsim"]["gettsim_version"] == "1.2.1"


def test_gettsim_synthetic_first_run_shell_attributes_unavailable_engine(tmp_path):
    run_comparison = load_run_comparison_module()
    run_comparison.DASHBOARD_DATA_DIR = tmp_path / "missing-dashboard"
    params = {
        "suite": "de-worker-dual-oracle",
        "dashboard_filename": "missing.json",
    }

    euromod_output = tmp_path / "euromod-missing.json"
    run_comparison._reemit_gettsim_synthetic_report(
        params, euromod_output, "EUROMOD_PYTHON unset"
    )
    euromod_report = json.loads(euromod_output.read_text())
    assert euromod_report["errors"] == [
        {
            "case_id": None,
            "side": "left",
            "engine": "euromod",
            "error": "skipped: EUROMOD_PYTHON unset",
        }
    ]
    assert euromod_report["summary"]["errors_by_engine"] == {"euromod": 1}

    gettsim_output = tmp_path / "gettsim-missing.json"
    run_comparison._reemit_gettsim_synthetic_report(
        params, gettsim_output, "GETTSIM unavailable (not installed)"
    )
    gettsim_report = json.loads(gettsim_output.read_text())
    assert gettsim_report["errors"][0]["side"] == "right"
    assert gettsim_report["errors"][0]["engine"] == "gettsim"


def test_gettsim_synthetic_runtime_regression_fails_loudly(monkeypatch, tmp_path):
    from axiom_oracles.adapters import gettsim as gettsim_adapter
    from axiom_oracles.adapters.gettsim import GettsimAdapterError

    run_comparison = load_run_comparison_module()
    monkeypatch.setenv("EUROMOD_PYTHON", "/fake/euromod-python")

    def fail_version_check():
        raise GettsimAdapterError("unsupported installed version")

    monkeypatch.setattr(gettsim_adapter, "gettsim_version", fail_version_check)

    with pytest.raises(GettsimAdapterError, match="unsupported installed version"):
        run_comparison._gettsim_synthetic_skip_reason(
            {"euromod_model_root": str(tmp_path)}
        )


def _target_aliases(branch):
    if isinstance(branch, str):
        return [branch]
    return [alias for child in branch.values() for alias in _target_aliases(child)]


def test_de_dual_oracle_registry_config_shape() -> None:
    config = yaml.safe_load(
        (COMPARISONS_DIR / "de-worker-dual-oracle.yaml").read_text()
    )
    params = config["runner"]["parameters"]

    assert config["runner"]["type"] == "gettsim-synthetic-compare"
    assert params["suite"] == "de-worker-dual-oracle"
    assert params["euromod_country"] == "DE"
    assert params["euromod_system"] == "DE_2025"
    assert params["euromod_dataset"] == "DE_2024_b1_2015_03_e2"
    assert params["euromod_template_dataset"] == "DE_training_data"
    assert params["euromod_extra_columns"] == ["drgn1"]
    assert params["gettsim_policy_date"] == "2025-06-30"
    assert params["gettsim_version"] == "1.2.1"
    assert len(params["concepts"]) == 6
    assert config["dashboard"]["filename"] == (
        "euromod-gettsim-de-worker-dual-oracle.json"
    )


def test_de_axiom_pair_runner_is_registered() -> None:
    run_comparison = load_run_comparison_module()

    assert run_comparison.RUNNERS["de-axiom-oracle-compare"] is (
        run_comparison._run_de_axiom_oracle_compare
    )


@pytest.mark.parametrize(
    ("name", "oracle", "canonical_record"),
    [
        (
            "de-worker-dual-oracle-axiom-euromod",
            "euromod",
            "comparisons/de-worker-dual-oracle/axiom-euromod.json",
        ),
        (
            "de-worker-dual-oracle-axiom-gettsim",
            "gettsim",
            "comparisons/de-worker-dual-oracle/axiom-gettsim.json",
        ),
    ],
)
def test_de_axiom_pair_configs_have_exact_names_and_synchronized_pins(
    name, oracle, canonical_record
) -> None:
    run_comparison = load_run_comparison_module()
    executable = load_script_module("de_executable")
    unified = load_script_module("de_unified_comparison")
    config_path = COMPARISONS_DIR / f"{name}.yaml"
    config = run_comparison._load_comparison(name)
    params = config["runner"]["parameters"]

    assert config_path.stem == config["name"] == name
    assert config["runner"]["type"] == "de-axiom-oracle-compare"
    assert params["suite"] == name
    assert params["oracle"] == oracle
    assert config["artifacts"]["canonical_record"] == canonical_record
    assert config["selector"]["report"] == canonical_record

    configured_pin = {
        "commit": params["rulespec_upstream_sha"],
        "tree": params["rulespec_upstream_tree"],
    }
    assert configured_pin == unified.RULESPEC_REF_PIN
    assert configured_pin == {
        "commit": executable.RULESPEC_PIN["commit"],
        "tree": executable.RULESPEC_PIN["tree"],
    }
    assert all(
        len(value) == 40 and set(value) <= set("0123456789abcdef")
        for value in configured_pin.values()
    )


def test_load_comparison_rejects_internal_name_drift(monkeypatch, tmp_path):
    """A selector name must resolve to a config declaring that exact name;
    silently running a differently named config repeats the #295 failure."""

    run_comparison = load_run_comparison_module()
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "expected-name.yaml").write_text(
        "name: different-name\n"
        "runner:\n"
        "  type: de-axiom-oracle-compare\n"
        "  parameters: {}\n"
    )
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", comparisons)

    with pytest.raises(SystemExit, match="config.*name|name.*config"):
        run_comparison._load_comparison("expected-name")


def test_canonical_record_path_accepts_only_comparisons_descendants(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    repo = tmp_path / "repo"
    comparisons = repo / "comparisons"
    comparisons.mkdir(parents=True)
    monkeypatch.setattr(run_comparison, "REPO_ROOT", repo)

    assert run_comparison._canonical_record_path({}) is None
    assert run_comparison._canonical_record_path(
        {
            "artifacts": {
                "canonical_record": (
                    "comparisons/de-worker-dual-oracle/axiom-euromod.json"
                )
            }
        }
    ) == (comparisons / "de-worker-dual-oracle" / "axiom-euromod.json").resolve()

    for unsafe in (
        "",
        str(tmp_path / "absolute.json"),
        "../outside.json",
        "dashboard/public/data/not-canonical.json",
        "comparisons/../../outside.json",
    ):
        with pytest.raises(SystemExit, match="canonical_record"):
            run_comparison._canonical_record_path(
                {"artifacts": {"canonical_record": unsafe}}
            )

    outside = tmp_path / "outside"
    outside.mkdir()
    (comparisons / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SystemExit, match="canonical_record"):
        run_comparison._canonical_record_path(
            {
                "artifacts": {
                    "canonical_record": "comparisons/escape/record.json"
                }
            }
        )


def test_write_canonical_record_publishes_exact_bytes_atomically(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    source = tmp_path / "reports" / "source.json"
    target = tmp_path / "comparisons" / "de" / "record.json"
    source.parent.mkdir()
    source.write_bytes(b'{"suite":"de-pair","revision":1}\n')
    replaced = []
    real_replace = run_comparison.os.replace

    def recording_replace(staging, destination):
        replaced.append((Path(staging), Path(destination)))
        real_replace(staging, destination)

    monkeypatch.setattr(run_comparison.os, "replace", recording_replace)

    run_comparison._write_canonical_record(source, target)

    assert target.read_bytes() == source.read_bytes()
    assert len(replaced) == 1
    assert replaced[0][1] == target
    assert replaced[0][0].parent == target.parent
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))

    source.write_bytes(b'{"suite":"de-pair","revision":2}\n')
    run_comparison._write_canonical_record(source, target)
    assert target.read_bytes() == source.read_bytes()


def test_uk_efrs_runner_merges_universal_credit_surfaces(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    axiom_encode = tmp_path / "axiom-encode"
    axiom_rules = tmp_path / "axiom-rules-engine"
    rulespec_uk = tmp_path / "rulespec-uk"
    data_folder = tmp_path / "policyengine-data"
    for path in (axiom_encode, axiom_rules, rulespec_uk, data_folder):
        path.mkdir()
    output = tmp_path / "report.json"
    calls = []

    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_args, **_kwargs: None
    )

    def fake_run(cmd, *, check, cwd=None, capture_output=None, text=None, env=None):
        del check, cwd, capture_output, text
        calls.append(cmd)
        assert env is not None
        assert str(run_comparison.REPO_ROOT) in env["PYTHONPATH"].split(os.pathsep)
        surface = cmd[cmd.index("--surface") + 1]
        payload = {
            "compared_persons": 2,
            "compared_benunits": 1,
            "compared_values": 1,
            "mismatch_count": 0,
            "mismatches": [],
            "oracle_divergence_count": 0,
            "oracle_divergences": [],
            "output_summary": [
                {
                    "surface": surface,
                    "output": "carer_element",
                    "compared": 1,
                    "mismatches": 0,
                    "oracle_divergences": 0,
                    "max_abs_diff": 0,
                    "max_relative_diff": 0,
                }
            ],
            "skipped_surfaces": [],
            "projection_notes": [f"note {surface}"],
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload))

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_encode_uk_efrs_compare(
        {
            "axiom_encode_repo": str(axiom_encode),
            "axiom_rules_repo": str(axiom_rules),
            "rulespec_root": str(rulespec_uk),
            "parameters": {
                "sample_size": 100,
                "year": 2026,
                "python": "3.13",
                "dataset": "enhanced_frs_2023_24",
                "data_folder": str(data_folder),
                "surfaces": [
                    "universal-credit-carer-element",
                    "universal-credit-childcare-cap",
                ],
            },
        },
        output,
    )

    assert len(calls) == 2
    assert calls[0][:4] == ["uv", "run", "--python", "3.13"]
    assert "uk-populace-compare" in calls[0]  # renamed subcommand (#1108)
    assert "policyengine[uk]==4.11.0" not in calls[0]
    assert "policyengine-uk==2.88.56" in calls[0]
    assert "--rulespec-root" in calls[0]
    assert str(rulespec_uk.resolve()) in calls[0]

    report = json.loads(output.read_text())
    assert report["compared_values"] == 2
    assert report["compared_persons"] == 2
    assert len(report["output_summary"]) == 2
    assert report["projection_notes"] == [
        "note universal-credit-carer-element",
        "note universal-credit-childcare-cap",
    ]


def test_uk_efrs_runner_composes_universal_credit_program(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    axiom_encode = tmp_path / "axiom-encode"
    axiom_rules = tmp_path / "axiom-rules-engine"
    rulespec_uk = tmp_path / "rulespec-uk"
    data_folder = tmp_path / "policyengine-data"
    compose_binary = tmp_path / "axiom-compose"
    program = tmp_path / "axiom-programs" / "uk" / "universal-credit" / "fy-2026-27.yaml"
    composed = tmp_path / "uk-uc-composed.yaml"
    output = tmp_path / "report.json"
    for path in (axiom_encode, axiom_rules, rulespec_uk, data_folder, program.parent):
        path.mkdir(parents=True, exist_ok=True)
    compose_binary.write_text("#!/bin/sh\n")
    program.write_text("program: uk/universal-credit\n")
    calls = []

    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_args, **_kwargs: None
    )

    def fake_run(cmd, *, check, cwd=None, capture_output=None, text=None, env=None):
        del check, cwd, capture_output, text
        calls.append(cmd)
        if "uk-populace-compare" not in cmd:
            return subprocess.CompletedProcess(cmd, 0)
        # The runner overlays this checkout's bridge over the encoder's
        # axiom-oracles pin via PYTHONPATH.
        assert env is not None
        assert str(run_comparison.REPO_ROOT) in env["PYTHONPATH"].split(os.pathsep)
        payload = {
            "compared_persons": 1,
            "compared_benunits": 1,
            "compared_values": 1,
            "mismatch_count": 0,
            "mismatches": [],
            "oracle_divergence_count": 0,
            "oracle_divergences": [],
            "output_summary": [],
            "skipped_surfaces": [],
            "projection_notes": [],
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload))

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_encode_uk_efrs_compare(
        {
            "axiom_encode_repo": str(axiom_encode),
            "axiom_rules_repo": str(axiom_rules),
            "rulespec_root": str(rulespec_uk),
            "parameters": {
                "sample_size": 100,
                "year": 2026,
                "python": "3.13",
                "dataset": "enhanced_frs_2023_24",
                "data_folder": str(data_folder),
                "surface": "universal-credit-carer-element",
                "axiom_compose_binary": str(compose_binary),
                "axiom_program": str(program),
                "axiom_composed_program": str(composed),
                "rulespec_roots": [str(rulespec_uk)],
            },
        },
        output,
    )

    assert calls[0] == [
        str(compose_binary.resolve()),
        str(program.resolve()),
        "--rulespec-root",
        str(rulespec_uk.resolve()),
        "-o",
        str(composed.resolve()),
    ]
    assert "uk-populace-compare" in calls[1]  # renamed subcommand (#1108)
    assert "--universal-credit-program" in calls[1]
    assert str(composed.resolve()) in calls[1]


def test_tax_ecps_dashboard_adapter_maps_summary_and_cases():
    run_comparison = load_run_comparison_module()

    report = run_comparison._adapt_tax_ecps_to_v2(
        {
            "compared_tax_units": 2,
            "compared_values": 7,
            "mismatch_count": 2,
            "output_summary": [
                {
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "compared": 3,
                    "mismatches": 1,
                    "max_abs_diff": 50,
                    "max_relative_diff": 1,
                },
                {
                    "surface": "employee-oasdi",
                    "output": "employee_oasdi",
                    "compared": 2,
                    "mismatches": 0,
                    "max_abs_diff": 0,
                    "max_relative_diff": 0,
                },
                {
                    "surface": "cdcc",
                    "output": "cdcc",
                    "compared": 1,
                    "mismatches": 0,
                    "max_abs_diff": 0,
                    "max_relative_diff": 0,
                },
                {
                    "surface": "nonrefundable-credits",
                    "output": "income_tax_capped_non_refundable_credits",
                    "compared": 1,
                    "mismatches": 1,
                    "max_abs_diff": 25,
                    "max_relative_diff": 1,
                },
            ],
            "mismatches": [
                {
                    "entity_id": "tax_unit_1",
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "axiom": 100,
                    "policyengine": 150,
                    "diff": -50,
                },
                {
                    "entity_id": "tax_unit_2",
                    "surface": "nonrefundable-credits",
                    "output": "income_tax_capped_non_refundable_credits",
                    "axiom": 75,
                    "policyengine": 100,
                    "diff": -25,
                }
            ],
        },
        {},
        suite="fiit-ecps",
    )

    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["suite"] == "fiit-ecps"
    assert report["summary"]["comparison_count"] == 7
    assert report["summary"]["mismatch_count"] == 2
    assert report["summary"]["mismatches_by_concept"] == [
        {"value": "us:tax/federal-income-tax#ctc", "count": 1},
        {"value": "us:tax/federal-income-tax#nonrefundable_credits", "count": 1},
    ]
    assert report["summary"]["mismatches_by_kind"] == [
        {"value": "amount_difference", "count": 2}
    ]
    assert report["aggregates"][0]["concept"] == "us:tax/federal-income-tax#liability"
    assert report["aggregates"][0]["match_rate"] == 500 / 7
    assert report["aggregates"][0]["left_weighted_sum"] is None
    assert report["aggregates"][1]["weighted_difference"] is None
    assert report["case_count"] == 2
    assert len(report["cases"]) == 2
    assert report["cases"][0]["metadata"]["entity_id"] == "tax_unit_1"
    assert report["mismatches"][0]["concept"] == "us:tax/federal-income-tax#ctc"
    assert any(
        aggregate["concept"] == "us:tax/federal-income-tax#cdcc"
        for aggregate in report["aggregates"]
    )
    # Back-compat: raw without a dataset_identity block keeps the legacy label
    # and does not invent a top-level identity key.
    assert "dataset_identity" not in report
    assert report["cases"][0]["metadata"]["dataset"] == "enhanced_cps"
    assert "dataset_identity" not in report["cases"][0]["metadata"]


def test_tax_ecps_dashboard_adapter_threads_dataset_identity():
    """axiom-encode#952 emits a top-level `dataset_identity` in --json output.

    The dashboard adapter must consume it: surface it on the report top-level
    (so it survives case-row slimming) and stamp each case's dataset label +
    identity, replacing the hardcoded `enhanced_cps` string.
    """
    run_comparison = load_run_comparison_module()

    identity = {
        "country": "us",
        "source": "pinned",
        "path": None,
        "sha256": "16be6338f9d0",
        "revision": "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z",
        "built_with": "1.729.0",
    }
    report = run_comparison._adapt_tax_ecps_to_v2(
        {
            "compared_tax_units": 1,
            "compared_values": 1,
            "mismatch_count": 1,
            "dataset_identity": identity,
            "output_summary": [
                {
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "compared": 1,
                    "mismatches": 1,
                    "max_abs_diff": 50,
                    "max_relative_diff": 1,
                }
            ],
            "mismatches": [
                {
                    "entity_id": "tax_unit_1",
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "axiom": 100,
                    "policyengine": 150,
                    "diff": -50,
                }
            ],
        },
        {},
        suite="fiit-ecps",
    )

    # Top-level identity — verbatim from encode, so nothing is lost.
    assert report["dataset_identity"] == identity
    # Per-case dataset label is derived from identity, not the legacy constant.
    case_metadata = report["cases"][0]["metadata"]
    assert case_metadata["dataset"] == (
        "populace-us@populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    )
    assert case_metadata["dataset_identity"] == identity


def test_tax_ecps_dashboard_adapter_keeps_identity_when_all_cases_match():
    """A clean run (no mismatches) has no case rows, but the report must still
    record which pinned artifact produced it — identity lives at top-level."""
    run_comparison = load_run_comparison_module()

    identity = {
        "country": "us",
        "source": "pinned",
        "path": None,
        "sha256": "16be6338f9d0",
        "revision": "populace-us-2024-f0af251",
        "built_with": "1.729.0",
    }
    report = run_comparison._adapt_tax_ecps_to_v2(
        {
            "compared_tax_units": 3,
            "compared_values": 3,
            "mismatch_count": 0,
            "dataset_identity": identity,
            "output_summary": [
                {
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "compared": 3,
                    "mismatches": 0,
                    "max_abs_diff": 0,
                    "max_relative_diff": 0,
                }
            ],
            "mismatches": [],
        },
        {},
        suite="fiit-ecps",
    )

    assert report["cases"] == []
    # Identity survives on the top-level even with zero case rows — this is the
    # slice `_slim_report_for_dashboard` would ship for a clean weekly run.
    slim = run_comparison._slim_report_for_dashboard(report)
    assert slim["dataset_identity"] == identity


def test_slim_report_honors_per_suite_mismatch_cap_override():
    """dashboard.max_mismatches lifts the default 1,000-row cap (#439).

    The triage pipeline reads the committed dashboard copy; a suite whose
    unexplained rows sit past the default cap declares a higher cap in its
    comparison YAML so every mismatch row persists.
    """
    run_comparison = load_run_comparison_module()

    mismatches = [
        {"case_id": f"case-{i}", "kind": "amount_difference"}
        for i in range(1500)
    ]
    report = {
        "schema_version": "axiom.comparison_report.v2.1",
        "summary": {"mismatch_count": len(mismatches)},
        "mismatches": mismatches,
        "cases": [],
    }

    # Default cap truncates and declares it.
    slim = run_comparison._slim_report_for_dashboard(dict(report))
    assert len(slim["mismatches"]) == 1000
    assert slim["dashboard_truncation"]["total_mismatches"] == 1500

    # A per-suite override above the total keeps every row, no truncation.
    full = run_comparison._slim_report_for_dashboard(
        dict(report), max_mismatches=4000
    )
    assert len(full["mismatches"]) == 1500
    assert "dashboard_truncation" not in full

    # An override below the total still truncates at the override.
    tighter = run_comparison._slim_report_for_dashboard(
        dict(report), max_mismatches=1200
    )
    assert len(tighter["mismatches"]) == 1200
    assert tighter["dashboard_truncation"]["shown_mismatches"] == 1200


def test_versioned_chunk_storage_removes_inline_case_mirrors(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", tmp_path)
    suite_dir = tmp_path / "cases" / "bound-suite"
    suite_dir.mkdir(parents=True)
    (suite_dir / "index.json").write_text(
        json.dumps({"schema_version": "axiom_oracles.chunk_index.v1"})
    )
    report = {
        "suite": "bound-suite",
        "case_count": 1,
        "mismatches": [],
        "cases": [{"case_id": "mirrored", "matched": True}],
        "summary": {
            "comparison_count": 1,
            "match_count": 1,
            "mismatch_count": 0,
        },
    }

    slim = run_comparison._slim_report_for_dashboard(report)

    assert slim["cases"] == []
    assert slim["dashboard_truncation"] == {
        "total_mismatches": 0,
        "shown_mismatches": 0,
        "total_case_rows": 1,
        "shown_case_rows": 0,
    }
    assert report["cases"], "slimming must not mutate the full report"


def test_dashboard_writer_refreshes_versioned_chunks_before_slimming(
    monkeypatch, tmp_path
):
    from axiom_oracles.evidence import validate_suite_evidence

    run_comparison = load_run_comparison_module()
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", tmp_path)
    suite_dir = tmp_path / "cases" / "bound-suite"
    suite_dir.mkdir(parents=True)
    (suite_dir / "chunk-0.json").write_text(
        '[{"id":"stale","r":100,"h":{},"m":[],"v":[]}]'
    )
    (suite_dir / "index.json").write_text(
        json.dumps({"schema_version": "axiom_oracles.chunk_index.v1"})
    )
    report = {
        "suite": "bound-suite",
        "case_count": 1,
        "engines": {"left": "axiom", "right": "oracle"},
        "concepts": [
            {
                "id": "benefit",
                "comparison": "amount",
                "tolerance": 0,
                "relative_tolerance": 0,
            }
        ],
        "aggregates": [
            {
                "concept": "benefit",
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
            }
        ],
        "mismatches": [],
        "cases": [
            {
                "case_id": "fresh",
                "match_rate": 100,
                "matches": [{"concept": "benefit", "left": 2, "right": 2}],
                "mismatches": [],
                "metadata": {
                    "household_summary": {"household_size": 1},
                    "axiom_input_records": [
                        {"name": "income", "value": 5, "entity_id": "household"}
                    ],
                    "axiom_all_outputs": {"benefit": 2},
                },
            }
        ],
        "summary": {
            "comparison_count": 1,
            "match_count": 1,
            "mismatch_count": 0,
        },
    }

    run_comparison._write_dashboard_report(report, "bound-report.json")

    dashboard_report = tmp_path / "bound-report.json"
    stored = json.loads(dashboard_report.read_text())
    chunk = json.loads((suite_dir / "chunk-0.json").read_text())
    index = json.loads((suite_dir / "index.json").read_text())
    evidence = validate_suite_evidence(dashboard_report)
    generator = load_script_module("generate_chunk_indexes")
    index_current, _message = generator.generate(
        dashboard_report,
        check=True,
        strip_inline=False,
    )
    assert stored["cases"] == []
    assert chunk[0]["id"] == "fresh"
    assert chunk[0]["v"] == [{"c": "benefit", "l": 2, "x": 2}]
    assert index["input_slots"] == ["income"]
    assert index["output_slots"] == ["benefit"]
    assert evidence.valid is True
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert index_current is True


def test_compact_full_evidence_preserves_explicit_zero_matches():
    from scripts.emit_case_artifacts import compact_case

    all_mismatch = compact_case(
        {
            "case_id": "all-mismatch",
            "matches": [],
            "mismatches": [
                {"concept": "benefit", "left": 1, "right": 2}
            ],
        },
        {},
    )
    all_match = compact_case(
        {
            "case_id": "all-match",
            "match_rate": 99.9999995,
            "matches": [{"concept": "benefit", "left": 1, "right": 1}],
            "mismatches": [],
        },
        {},
    )
    verdict_free = compact_case(
        {"case_id": "qc-shape", "matched": True, "mismatches": []},
        {},
    )

    assert all_mismatch["v"] == []
    assert all_mismatch["m"][0]["d"] == 1
    assert all_mismatch["r"] == 0.0
    assert all_match["r"] == 100.0
    assert "v" not in verdict_free


def test_skipped_versioned_run_preserves_existing_bound_artifacts(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", tmp_path)
    suite_dir = tmp_path / "cases" / "bound-suite"
    suite_dir.mkdir(parents=True)
    target = tmp_path / "bound-report.json"
    index_path = suite_dir / "index.json"
    chunk_path = suite_dir / "chunk-0.json"
    target.write_text('{"existing":"report"}')
    index_path.write_text(
        json.dumps({"schema_version": "axiom_oracles.chunk_index.v1"})
    )
    chunk_path.write_text('[{"id":"existing"}]')
    before = tuple(
        path.read_bytes() for path in (target, index_path, chunk_path)
    )

    run_comparison._write_dashboard_report(
        {
            "suite": "bound-suite",
            "case_count": 1,
            "cases": [],
            "summary": {
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
            },
        },
        target.name,
        preserve_existing_versioned=True,
    )

    after = tuple(path.read_bytes() for path in (target, index_path, chunk_path))
    assert after == before


def test_dataset_label_from_identity_falls_back_without_revision():
    run_comparison = load_run_comparison_module()

    assert (
        run_comparison._dataset_label_from_identity(None, fallback="enhanced_cps")
        == "enhanced_cps"
    )
    assert (
        run_comparison._dataset_label_from_identity(
            {"country": "us"}, fallback="enhanced_cps"
        )
        == "populace-us"
    )
    # An empty dict from an error path normalizes to None → legacy label.
    assert run_comparison._normalize_dataset_identity({"dataset_identity": {}}) is None


def test_uk_efrs_dashboard_adapter_separates_known_pe_divergence():
    run_comparison = load_run_comparison_module()

    report = run_comparison._adapt_uk_efrs_to_v2(
        {
            "compared_persons": 1,
            "compared_benunits": 1,
            "compared_values": 2,
            "mismatch_count": 1,
            "mismatches": [
                {
                    "surface": "universal-credit-carer-element",
                    "entity_id": "benunit_1",
                    "output": "carer_element",
                    "axiom": 209.34,
                    "policyengine": 200.00,
                    "diff": 9.34,
                }
            ],
            "oracle_divergence_count": 1,
            "oracle_divergences": [
                {
                    "surface": "universal-credit-standard-allowance",
                    "entity_id": "benunit_2",
                    "output": "standard_allowance_single_25_or_over",
                    "axiom": 424.90,
                    "policyengine": 410.00,
                    "diff": 14.90,
                    "reason": "PolicyEngine UK forecast-indexed rate",
                    "issue_url": "https://example.test/pe-issue",
                }
            ],
            "output_summary": [
                {
                    "surface": "universal-credit-carer-element",
                    "output": "carer_element",
                    "compared": 1,
                    "mismatches": 1,
                    "oracle_divergences": 0,
                    "max_abs_diff": 9.34,
                    "max_relative_diff": 0.04,
                },
                {
                    "surface": "universal-credit-standard-allowance",
                    "output": "standard_allowance_single_25_or_over",
                    "compared": 1,
                    "mismatches": 0,
                    "oracle_divergences": 1,
                    "max_abs_diff": 14.90,
                    "max_relative_diff": 0.04,
                },
                {
                    "surface": "universal-credit-award",
                    "output": "universal_credit_award_amount",
                    "compared": 1,
                    "mismatches": 0,
                    "oracle_divergences": 0,
                    "max_abs_diff": 0,
                    "max_relative_diff": 0,
                },
            ],
            "projection_notes": ["component amount comparison"],
        },
        {},
        suite="uk-universal-credit-efrs",
    )

    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["suite"] == "uk-universal-credit-efrs"
    assert report["summary"]["comparison_count"] == 3
    assert report["summary"]["mismatch_count"] == 2
    assert report["summary"]["true_mismatch_count"] == 1
    assert report["summary"]["known_policyengine_divergence_count"] == 1
    assert report["summary"]["mismatches_by_kind"] == [
        {"value": "amount_difference", "count": 1},
        {"value": "known_policyengine_divergence", "count": 1},
    ]
    assert report["aggregates"][0]["concept"] == "uk:benefits/universal-credit#amount"
    assert round(report["aggregates"][0]["match_rate"], 6) == round(100 / 3, 6)
    assert any(
        aggregate["concept"]
        == "uk:statutes/ukpga/2012/5/8#universal_credit_award_amount"
        for aggregate in report["aggregates"]
    )
    assert report["mismatches"][1]["kind"] == "known_policyengine_divergence"
    assert report["mismatches"][1]["issue_url"] == "https://example.test/pe-issue"


def test_uk_efrs_dashboard_adapter_caps_known_divergence_examples():
    run_comparison = load_run_comparison_module()

    report = run_comparison._adapt_uk_efrs_to_v2(
        {
            "compared_persons": 3,
            "compared_benunits": 0,
            "compared_values": 3,
            "mismatch_count": 0,
            "mismatches": [],
            "oracle_divergence_count": 3,
            "oracle_divergences": [
                {
                    "surface": "universal-credit-carer-element",
                    "entity_id": f"person_{index}",
                    "output": "carer_element",
                    "axiom": 209.34,
                    "policyengine": 200.00,
                    "diff": 9.34,
                    "reason": "PolicyEngine UK forecast-indexed rate",
                }
                for index in range(3)
            ],
            "output_summary": [
                {
                    "surface": "universal-credit-carer-element",
                    "output": "carer_element",
                    "compared": 3,
                    "mismatches": 0,
                    "oracle_divergences": 3,
                    "max_abs_diff": 9.34,
                    "max_relative_diff": 0.04,
                }
            ],
        },
        {"dashboard": {"known_policyengine_divergence_detail_limit": 1}},
        suite="uk-universal-credit-efrs",
    )

    assert report["summary"]["mismatch_count"] == 3
    assert report["summary"]["known_policyengine_divergence_count"] == 3
    assert report["summary"]["stored_mismatch_example_count"] == 1
    assert report["summary"]["mismatches_by_kind"] == [
        {"value": "known_policyengine_divergence", "count": 3}
    ]
    assert len(report["mismatches"]) == 1
    assert len(report["cases"]) == 1


def test_uk_efrs_dashboard_adapter_maps_non_uc_surface():
    run_comparison = load_run_comparison_module()

    report = run_comparison._adapt_uk_efrs_to_v2(
        {
            "compared_persons": 1,
            "compared_benunits": 0,
            "mismatches": [],
            "oracle_divergences": [],
            "output_summary": [
                {
                    "surface": "national-insurance-final",
                    "output": "national_insurance_contribution",
                    "compared": 1,
                    "mismatches": 0,
                    "oracle_divergences": 0,
                }
            ],
        },
        {
            "dashboard": {
                "parent_concept": "uk:tax-benefits/efrs#amount",
                "parent_description": "UK tax and benefit EFRS surfaces",
            }
        },
        suite="uk-tax-benefits-efrs",
    )

    assert report["suite"] == "uk-tax-benefits-efrs"
    assert report["summary"]["comparison_count"] == 1
    assert report["aggregates"][0]["concept"] == "uk:tax-benefits/efrs#amount"
    assert report["aggregates"][1]["concept"] == (
        "uk:statutes/ukpga/1992/4/1#national_insurance_contribution"
    )


# ---------------------------------------------------------------------------
# Registry ↔ dashboard publish invariants
#
# The EUROMOD Belgium lane commits its dashboard reports directly, and the
# suites that generate them are wired through comparisons/<name>.yaml. A suite
# that names a dashboard_filename but never lands in dashboard/public/data or
# in manifest.json is "registered but unpublished" — the exact gap that hid the
# GRAPA (be-elderly-income-support) and be-social-assistance reports from the
# dashboard suite selector. These pins fail loudly if that recurs.
# ---------------------------------------------------------------------------

import yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARISONS_DIR = REPO_ROOT / "comparisons"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"


@pytest.mark.parametrize("state", ["al", "ma", "nc", "sc", "tn"])
def test_snap_residual_suites_pin_reviewed_policyengine_stack(state):
    config = yaml.safe_load(
        (COMPARISONS_DIR / f"{state}-snap-ecps.yaml").read_text()
    )
    params = config["runner"]["parameters"]
    run_comparison = load_run_comparison_module()

    assert params["sample_size"] == 0
    assert params["period"] == "2026-01"
    assert params["python"] == "3.13"
    assert run_comparison._resolve_pe_oracle_pins(params) == (
        "policyengine==4.18.9",
        "policyengine-us==1.767.3",
        "policyengine-core==3.30.3",
    )


def test_ri_income_tax_grid_pins_reviewed_policyengine_stack():
    config = yaml.safe_load(
        (COMPARISONS_DIR / "ri-income-tax-liability.yaml").read_text()
    )
    params = config["runner"]["parameters"]
    run_comparison = load_run_comparison_module()

    assert run_comparison._resolve_pe_oracle_pins(params) == (
        "policyengine==4.18.9",
        "policyengine-us==1.784.4",
        "policyengine-core==3.30.3",
    )


def _euromod_be_registry_configs() -> list[dict]:
    configs: list[dict] = []
    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            continue
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            continue
        runner = config.get("runner") or {}
        params = runner.get("parameters") or {}
        if (
            runner.get("type") == "euromod-synthetic-compare"
            and params.get("euromod_country") == "BE"
        ):
            configs.append(config)
    return configs


def test_euromod_be_registry_reports_are_published_and_manifested():
    """Every EUROMOD-BE comparison config must have a committed dashboard
    report AND a manifest entry, so no BE suite is registered-but-unpublished."""
    manifest = json.loads((DASHBOARD_DATA_DIR / "manifest.json").read_text())
    manifest_reports = set(manifest["reports"])

    configs = _euromod_be_registry_configs()
    assert configs, "expected at least one euromod-synthetic-compare BE config"

    for config in configs:
        filename = config["dashboard"]["filename"]
        report_path = DASHBOARD_DATA_DIR / filename
        assert report_path.exists(), (
            f"{config['name']}: dashboard report {filename} is not committed"
        )
        assert filename in manifest_reports, (
            f"{config['name']}: {filename} is missing from manifest.json"
        )


def test_every_euromod_be_dashboard_report_is_manifested():
    """Guards the direct-CLI publish gap: any committed axiom-euromod-be-*.json
    report must appear in manifest.json, else the dashboard cannot load it."""
    manifest = json.loads((DASHBOARD_DATA_DIR / "manifest.json").read_text())
    manifest_reports = set(manifest["reports"])
    committed = {
        path.name for path in DASHBOARD_DATA_DIR.glob("axiom-euromod-be-*.json")
    }
    missing = sorted(committed - manifest_reports)
    assert not missing, f"committed BE reports absent from manifest.json: {missing}"


def test_be_elderly_income_support_registry_config_shape():
    """Pins the GRAPA config's BE dataset-gating workaround and switch-override
    contract so a future edit cannot silently drop the template_dataset (which
    would abort the BE run) or the manual switch semantics."""
    config = yaml.safe_load(
        (COMPARISONS_DIR / "be-elderly-income-support.yaml").read_text()
    )
    params = config["runner"]["parameters"]
    assert config["runner"]["type"] == "euromod-synthetic-compare"
    assert params["suite"] == "be-elderly-income-support"
    assert params["euromod_country"] == "BE"
    assert params["euromod_system"] == "BE_2025"
    # The dataset-name gating workaround: run under a real configuration name,
    # template rows from the bundled demo dataset.
    assert params["euromod_dataset"] == "BE_2024_c1_2015_03_e2"
    assert params["euromod_template_dataset"] == "BE_training_data"
    assert config["dashboard"]["filename"] == (
        "axiom-euromod-be-elderly-income-support.json"
    )


def test_euromod_synthetic_runner_forwards_extra_template_columns(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    model_root = tmp_path / "model"
    model_root.mkdir()
    engine_repo = tmp_path / "engine"
    engine_binary = engine_repo / "target" / "release" / "axiom-rules-engine"
    engine_binary.parent.mkdir(parents=True)
    engine_binary.write_text("")
    monkeypatch.setenv("EUROMOD_PYTHON", "/fake/euromod-python")
    captured = {}

    def fake_run(command, *, check, cwd, env):
        captured.update({"command": command, "check": check, "cwd": cwd, "env": env})

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)
    run_comparison._run_euromod_synthetic_compare(
        {
            "axiom_rules_repo": str(engine_repo),
            "parameters": {
                "suite": "be-replacement-income-pit",
                "period": 2025,
                "sample_size": 0,
                "euromod_model_root": str(model_root),
                "euromod_extra_columns": ["drgn1", "bhl"],
            },
        },
        tmp_path / "report.json",
    )

    assert captured["env"]["EUROMOD_EXTRA_COLUMNS"] == "drgn1,bhl"


# ---------------------------------------------------------------------------
# UK fiscal-year eval-date invariant
#
# UK tax-benefit law (FA rates, Scottish Rate Resolution bands, NIC thresholds,
# benefit upratings) commences on the 6 April fiscal-year boundary, and UKMOD's
# UK_<year> system represents that fiscal year. The Axiom engine selects a
# parameter version by period.start (effective_from <= start; period.end is
# ignored), so a bare-year "2026" period — which _period_for_case resolves to a
# 1 January start — evaluates the Axiom side on the value live the previous
# January, not the fiscal-year vintage. Today that is harmless only because no
# compared parameter steps between 1 January and 6 April; a future April-6 rate
# change (e.g. the Class 3 NIC weekly rate) would silently be read at its old
# value with a Jan-1 start. This guard fails loudly if any UK suite regresses to
# a pre-fiscal-year (January) start, so the eval date stays fiscal-correct.
# ---------------------------------------------------------------------------


def _euromod_uk_registry_configs() -> list[dict]:
    configs: list[dict] = []
    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            continue
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            continue
        runner = config.get("runner") or {}
        params = runner.get("parameters") or {}
        if (
            runner.get("type") == "euromod-synthetic-compare"
            and params.get("euromod_country") == "UK"
        ):
            configs.append(config)
    return configs


def _system_year(euromod_system: str) -> int:
    """Parse the fiscal year off a EUROMOD-platform system name (UK_2026 -> 2026)."""
    digits = "".join(ch for ch in str(euromod_system) if ch.isdigit())
    assert len(digits) == 4, f"cannot read a 4-digit year from system {euromod_system!r}"
    return int(digits)


def test_uk_euromod_suites_evaluate_on_or_after_the_fiscal_boundary():
    """Every UK euromod-synthetic-compare suite must evaluate the Axiom side on
    or after 6 April of its system year — never on the bare-year 1 January start.

    The check runs the real ``_period_for_case`` resolver (the one the axiom
    adapter feeds the engine), so it pins the actual eval instant the engine
    would key parameter versions off, not a reimplementation. Annual (tax_year)
    suites must start exactly on the 6 April fiscal boundary; monthly benefit
    suites (UC/PC assessment periods) start on 1 April, which is still inside the
    fiscal year and past the 1 January regression this guard forbids.
    """
    from datetime import date

    from axiom_oracles.adapters.axiom.runner import _period_for_case
    from axiom_oracles.core.case import Case

    configs = _euromod_uk_registry_configs()
    assert configs, "expected at least one euromod-synthetic-compare UK config"

    for config in configs:
        params = config["runner"]["parameters"]
        name = config.get("name", params.get("suite", "?"))
        year = _system_year(params["euromod_system"])
        resolved = _period_for_case(Case(case_id="guard", period=str(params["period"])))
        start = date.fromisoformat(resolved["start"])
        fiscal_start = date(year, 4, 6)

        assert start >= date(year, 4, 1), (
            f"{name}: Axiom eval start {start.isoformat()} is before the "
            f"{year} fiscal year — a bare-year period resolves to a 1 January "
            f"start and reads the pre-April parameter vintage. Use an explicit "
            f"fiscal-year period (e.g. '{year}-04-06')."
        )
        if resolved["period_kind"] == "tax_year":
            assert start == fiscal_start, (
                f"{name}: annual suite must evaluate on the 6 April fiscal "
                f"boundary; resolved start is {start.isoformat()}. Set "
                f"period: '{year}-04-06'."
            )


# --- provenance completion from the affected map (#296) ---------------------
#
# A `sha: null` entry for a mapped repo reads as "cannot prove fresh" to
# select_affected_suites.py, which re-selects the suite every 6-hourly sweep
# even right after a successful refresh — the encode snap/tax lanes and the
# bare-$HOME-roots lanes all stamped exactly that. The completion helper fills
# the gaps from the runner's own fresh-clone SHA or the supervised-layout
# checkout, and never invents anything else.


def _completion_fixture(monkeypatch, tmp_path, mapped_repos):
    run_comparison = load_run_comparison_module()
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "affected_map.json").write_text(
        json.dumps(
            {
                "suites": [
                    {"suite": "demo-suite", "name": "demo", "repos": mapped_repos}
                ]
            }
        )
    )
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", comparisons)
    config = {"name": "demo", "dashboard": {"suite": "demo-suite"}}
    return run_comparison, config


def test_completion_fills_missing_repo_from_convention_checkout(
    monkeypatch, tmp_path
):
    rc, config = _completion_fixture(
        monkeypatch, tmp_path, ["TheAxiomFoundation/rulespec-us-az"]
    )
    checkout = tmp_path / "rulespec-us-az"
    checkout.mkdir()
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(
        provenance, "resolve_rulespec_checkout", lambda slug: checkout
    )
    monkeypatch.setattr(rc, "_git_head_sha", lambda repo: "a" * 40)

    completed = rc._complete_rulespecs_from_affected_map(config, {}, [])
    assert completed == [
        {"repo": "TheAxiomFoundation/rulespec-us-az", "sha": "a" * 40}
    ]


def test_completion_prefers_runner_clone_sha_for_rulespec_us(monkeypatch, tmp_path):
    rc, config = _completion_fixture(
        monkeypatch, tmp_path, ["TheAxiomFoundation/rulespec-us"]
    )
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(
        provenance,
        "resolve_rulespec_checkout",
        lambda slug: pytest.fail("clone SHA must win over convention lookup"),
    )
    runner = {"_cloned_rulespec_us_sha": "b" * 40}
    # The fiit lane's remote fallback produced a sha-less entry; the clone SHA
    # must fill it in place rather than duplicating the repo.
    completed = rc._complete_rulespecs_from_affected_map(
        config, runner, [{"repo": "TheAxiomFoundation/rulespec-us", "sha": None}]
    )
    assert completed == [{"repo": "TheAxiomFoundation/rulespec-us", "sha": "b" * 40}]


def test_completion_never_overrides_declared_path_sha(monkeypatch, tmp_path):
    rc, config = _completion_fixture(
        monkeypatch, tmp_path, ["TheAxiomFoundation/rulespec-us"]
    )
    declared = [{"repo": "TheAxiomFoundation/rulespec-us", "sha": "c" * 40}]
    completed = rc._complete_rulespecs_from_affected_map(
        config, {"_cloned_rulespec_us_sha": "d" * 40}, list(declared)
    )
    assert completed == declared


def test_completion_keeps_null_sha_when_nothing_resolves(monkeypatch, tmp_path):
    """NEGATIVE: an unresolvable repo stays `sha: null` — the selector's
    conservative "cannot prove fresh" reading must survive, not be papered
    over with an invented SHA."""
    rc, config = _completion_fixture(
        monkeypatch, tmp_path, ["TheAxiomFoundation/rulespec-us-nv"]
    )
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    completed = rc._complete_rulespecs_from_affected_map(config, {}, [])
    assert completed == [{"repo": "TheAxiomFoundation/rulespec-us-nv", "sha": None}]


def test_completion_tolerates_missing_map(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", tmp_path / "nowhere")
    entries = [{"repo": "TheAxiomFoundation/rulespec-us", "sha": None}]
    assert (
        run_comparison._complete_rulespecs_from_affected_map(
            {"name": "demo"}, {}, entries
        )
        == entries
    )


def test_axiom_oracles_runner_honors_python_parameter(monkeypatch, tmp_path):
    """taxcalc==6.7.1 cannot resolve on 3.14 (no numba wheel); the lane pins
    `python: "3.13"` and the runner must pass it through to uv (#296)."""
    run_comparison = load_run_comparison_module()
    axiom_rules = tmp_path / "axiom-rules-engine"
    axiom_rules.mkdir()
    calls = []

    def fake_run(cmd, *, check, cwd=None, env=None, stdout=None,
                 capture_output=False, text=False):
        del check, cwd, env, capture_output, text
        calls.append(cmd)
        if stdout is not None:
            stdout.write("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_oracles_compare(
        {
            "axiom_rules_repo": str(axiom_rules),
            "parameters": {
                "left": "taxcalc",
                "right": "policyengine",
                "concept": "us:tax/federal-income-tax#liability",
                "period": "2026",
                "sample_size": 25,
                "python": "3.13",
            },
        },
        tmp_path / "out.json",
    )
    cmd = calls[-1]
    assert cmd[:4] == ["uv", "run", "--python", "3.13"]
    assert "taxcalc==6.7.1" in cmd
    # The explicit numba floor keeps the resolver off the sdist-only numba
    # 0.53.1 whose build fails on any current Python (#296).
    assert "numba>=0.60" in cmd


def test_completion_never_applies_to_skip_capable_lanes(monkeypatch, tmp_path):
    """NEGATIVE: euromod/gettsim/snap-qc re-emit the committed report when
    their model root or data is absent — stamping current rulespec SHAs onto a
    re-emitted (not re-run) report would mark rules-stale numbers fresh, so
    provenance completion is restricted to always-real runner types (#296)."""
    run_comparison = load_run_comparison_module()
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(
        provenance,
        "resolve_rulespec_checkout",
        lambda slug: pytest.fail("skip-capable lanes must not resolve checkouts"),
    )
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "uk-benefit-cap"}))
    config = {
        "name": "uk-benefit-cap-ukmod",
        "dashboard": {"suite": "uk-benefit-cap"},
        "runner": {
            "type": "euromod-synthetic-compare",
            "parameters": {
                "axiom_rulespec_repo_roots": str(tmp_path),
                "euromod_country": "UK",
            },
        },
    }
    block = run_comparison._build_run_provenance(
        config, "euromod-synthetic-compare", output
    )
    for entry in block.get("rulespecs", []):
        assert entry.get("sha") is None


def test_state_income_tax_grid_generation_fails_closed(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    output = tmp_path / "ut.json"
    committed = (
        tmp_path
        / "dashboard"
        / "public"
        / "data"
        / "axiom-policyengine-taxsim-ut-income-tax-liability.json"
    )
    committed.parent.mkdir(parents=True)
    committed.write_text('{"stale": true}\n')
    monkeypatch.setattr(run_comparison, "REPO_ROOT", tmp_path)
    rulespec = tmp_path / "rulespec-us"
    engine = tmp_path / "axiom-rules-engine"
    rulespec.mkdir()
    engine.mkdir()
    monkeypatch.setattr(
        run_comparison,
        "_resolve_state_income_tax_grid_repos",
        lambda _params=None: (rulespec, engine),
    )

    def unavailable(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["generator"])

    monkeypatch.setattr(run_comparison.subprocess, "run", unavailable)

    with pytest.raises(subprocess.CalledProcessError):
        run_comparison._run_state_income_tax_liability_grid(
            {"parameters": {"state": "UT"}},
            output,
        )

    assert not output.exists()


def test_state_income_tax_grid_exposes_actual_repos_to_provenance(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    rulespec = tmp_path / "rulespec-us"
    engine = tmp_path / "axiom-rules-engine"
    rulespec.mkdir()
    engine.mkdir()
    monkeypatch.setattr(run_comparison, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_comparison,
        "_resolve_state_income_tax_grid_repos",
        lambda _params=None: (rulespec, engine),
    )
    source = (
        tmp_path
        / "dashboard"
        / "public"
        / "data"
        / "axiom-policyengine-taxsim-ri-income-tax-liability.json"
    )
    source.parent.mkdir(parents=True)
    source.write_text('{"fresh": true}\n')
    calls = []

    def generated(cmd, *, check, cwd, env):
        calls.append((cmd, check, cwd, env))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_comparison.subprocess, "run", generated)
    runner = {
        "parameters": {
            "state": "RI",
            "policyengine_version": "4.18.9",
            "policyengine_us_version": "1.784.4",
            "policyengine_core_version": "3.30.3",
        }
    }
    output = tmp_path / "out.json"

    run_comparison._run_state_income_tax_liability_grid(runner, output)

    assert runner["parameters"]["rulespec_roots"] == [str(rulespec)]
    assert runner["parameters"]["axiom_rules_repo"] == str(engine)
    cmd, check, cwd, env = calls[0]
    assert check is True
    assert cwd == tmp_path
    assert cmd[-2:] == ["--state", "RI"]
    assert "policyengine==4.18.9" in cmd
    assert "policyengine-us==1.784.4" in cmd
    assert "policyengine-core==3.30.3" in cmd
    assert run_comparison._PE_ORACLE_PINS[1] not in cmd
    assert env["RULESPEC_US_REPO"] == str(rulespec)
    assert env["AXIOM_RULES_REPO"] == str(engine)
    assert json.loads(output.read_text()) == {"fresh": True}


# ---------------------------------------------------------------------------
# _write_dashboard_report source binding: the pointer contract must mirror
# the consumer's (repo-relative AND under reports/) — sol stack reviews
# r3–r6. A premerged-slim copy is only ever trusted through its source
# binding, so when the full report goes to a non-canonical location the
# committed dashboard copy is NOT updated at all: pointer-emitting OR
# pointer-free, apply_dispositions.py --check is guaranteed to flag a
# premerged copy that cannot be re-derived from a committed full report.
# Consumer acceptance of the canonical emitted shape is pinned on the
# real artifacts by test_dispositions.py::
# test_panel_dashboard_block_is_bound_to_committed_full_report.
# ---------------------------------------------------------------------------

_SENTINEL = '{"sentinel": true}'


def _premerged_panel_report() -> dict:
    """A merged report large enough to be slimmed into a premerged copy."""
    n = 1001  # crosses _DASHBOARD_MAX_MISMATCHES so the slim is premerged
    return {
        "suite": "t-suite",
        "schema_version": "axiom.comparison_report.v2.1",
        "summary": {
            "mismatch_count": n,
            "dispositioned": {"explained_rate": 1.0, "unexplained_count": 0},
        },
        "mismatches": [
            {"case_id": f"c{i}", "concept": "x", "disposition": None}
            for i in range(n)
        ],
        "cases": [],
    }


def _write_dashboard_with_full_report_at(tmp_path, monkeypatch, full_path):
    """Returns the dashboard copy's path; it starts as a sentinel so tests
    can distinguish 'updated' from 'left untouched'."""
    run_comparison = load_run_comparison_module()
    repo = tmp_path / "repo"
    dashboard = repo / "dashboard" / "public" / "data"
    dashboard.mkdir(parents=True)
    monkeypatch.setattr(run_comparison, "REPO_ROOT", repo)
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setattr(run_comparison, "_merge_dispositions", lambda r: r)
    target = dashboard / "t-suite.json"
    target.write_text(_SENTINEL)
    full = repo / full_path if not full_path.is_absolute() else full_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(json.dumps(_premerged_panel_report()))
    run_comparison._write_dashboard_report(
        _premerged_panel_report(), "t-suite.json", full_report_path=full
    )
    return target


def test_dashboard_binding_emitted_for_reports_dir_source(tmp_path, monkeypatch):
    target = _write_dashboard_with_full_report_at(
        tmp_path, monkeypatch, Path("reports/t-suite-full.json")
    )
    slim = json.loads(target.read_text())
    assert "stored_mismatch_example_count" in slim["summary"]  # premerged
    block = slim["summary"]["dispositioned"]
    assert block["source_report"]["path"] == "reports/t-suite-full.json"
    assert len(block["source_report"]["sha256"]) == 64
    assert len(block["assignment_sha256"]) == 64


def test_dashboard_not_updated_for_in_repo_source_outside_reports(
    tmp_path, monkeypatch, capsys
):
    """In-repo but outside reports/: an unbindable premerged copy would be
    flagged by the consumer whether or not it carries a pointer, so the
    committed dashboard copy must be left untouched (sol r5)."""
    target = _write_dashboard_with_full_report_at(
        tmp_path, monkeypatch, Path("custom-out/t-suite-full.json")
    )
    assert target.read_text() == _SENTINEL
    assert "NOT updated" in capsys.readouterr().out


def test_dashboard_not_updated_for_source_outside_repo(
    tmp_path, monkeypatch, capsys
):
    target = _write_dashboard_with_full_report_at(
        tmp_path, monkeypatch, tmp_path / "elsewhere" / "t-suite-full.json"
    )
    assert target.read_text() == _SENTINEL
    assert "NOT updated" in capsys.readouterr().out


def test_dashboard_still_updated_for_unbindable_non_premerged_copy(
    tmp_path, monkeypatch
):
    """A small report slims to a FULL dashboard copy (no truncation, no
    stored_mismatch_example_count): the consumer re-merges it directly and
    never needs a pointer, so a non-canonical full-report location does
    not block the dashboard write."""
    run_comparison = load_run_comparison_module()
    repo = tmp_path / "repo"
    dashboard = repo / "dashboard" / "public" / "data"
    dashboard.mkdir(parents=True)
    monkeypatch.setattr(run_comparison, "REPO_ROOT", repo)
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setattr(run_comparison, "_merge_dispositions", lambda r: r)
    small = {
        "suite": "t-suite",
        "summary": {"mismatch_count": 1},
        "mismatches": [{"case_id": "c0", "concept": "x"}],
        "cases": [],
    }
    full = tmp_path / "elsewhere" / "t-suite-full.json"
    full.parent.mkdir(parents=True)
    full.write_text(json.dumps(small))
    run_comparison._write_dashboard_report(
        small, "t-suite.json", full_report_path=full
    )
    slim = json.loads((dashboard / "t-suite.json").read_text())
    assert "stored_mismatch_example_count" not in slim.get("summary", {})
    assert "dispositioned" not in slim.get("summary", {})


def test_dashboard_still_updated_for_case_only_truncated_copy(
    tmp_path, monkeypatch
):
    """Case-only overflow also writes stored_mismatch_example_count, but the
    consumer (apply_dispositions._is_premerged_slim_report) only treats a
    copy as premerged when stored < mismatch_count. The producer must use
    the same predicate: a copy whose mismatch sample is complete is
    re-merged directly by the consumer and never needs a pointer, so a
    non-canonical full-report location must not block its dashboard write
    (sol stack review r6: 1 mismatch / 1,001 cases skipped publication)."""
    run_comparison = load_run_comparison_module()
    repo = tmp_path / "repo"
    dashboard = repo / "dashboard" / "public" / "data"
    dashboard.mkdir(parents=True)
    monkeypatch.setattr(run_comparison, "REPO_ROOT", repo)
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setattr(run_comparison, "_merge_dispositions", lambda r: r)
    report = {
        "suite": "t-suite",
        "schema_version": "axiom.comparison_report.v2.1",
        "summary": {
            "mismatch_count": 1,
            "dispositioned": {"explained_rate": 1.0, "unexplained_count": 0},
        },
        "mismatches": [{"case_id": "c0", "concept": "x", "disposition": None}],
        "cases": [{"case_id": f"c{i}"} for i in range(1001)],
    }
    full = tmp_path / "elsewhere" / "t-suite-full.json"
    full.parent.mkdir(parents=True)
    full.write_text(json.dumps(report))
    run_comparison._write_dashboard_report(
        report, "t-suite.json", full_report_path=full
    )
    slim = json.loads((dashboard / "t-suite.json").read_text())
    # every mismatch row survives the trim: stored == mismatch_count
    assert slim["summary"]["stored_mismatch_example_count"] == 1
    assert slim["summary"]["mismatch_count"] == 1
    # published, and pointer-free — the consumer re-merges it directly
    assert "source_report" not in slim["summary"]["dispositioned"]


# --- state grid rulespec resolution + pinned federal snapshots (#455) --------


def _git_init_clean(path, gitignore=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    if gitignore is not None:
        (path / ".gitignore").write_text(gitignore)
        git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "--quiet", "-m", "init"], check=True)
    return path


def test_state_income_tax_grid_resolver_prefers_suite_rulespec_roots(
    monkeypatch, tmp_path
):
    """CI shape: no env override and no sibling checkout — the suite YAML's
    rulespec_roots (the path materialize_ci_workspace.py guarantees) wins."""
    run_comparison = load_run_comparison_module()
    monkeypatch.setattr(
        run_comparison, "REPO_ROOT", tmp_path / "workspace" / "axiom-oracles"
    )
    monkeypatch.delenv("RULESPEC_US_REPO", raising=False)
    rulespec = _git_init_clean(tmp_path / "TheAxiomFoundation" / "rulespec-us")
    engine = _git_init_clean(tmp_path / "engine", gitignore="target/\n")
    monkeypatch.setenv("AXIOM_RULES_REPO", str(engine))
    built = []
    monkeypatch.setattr(
        run_comparison,
        "_ensure_engine_binary",
        lambda repo, *, kind: built.append((repo, kind)),
    )
    binary = engine / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    params = {"rulespec_roots": [str(tmp_path / "missing"), str(rulespec)]}

    root, rules = run_comparison._resolve_state_income_tax_grid_repos(params)

    assert root == rulespec.resolve()
    assert rules == engine.resolve()
    assert built == [(engine.resolve(), "release")]


def test_state_income_tax_grid_resolver_env_overrides_suite_roots(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    monkeypatch.setattr(
        run_comparison, "REPO_ROOT", tmp_path / "workspace" / "axiom-oracles"
    )
    env_root = _git_init_clean(tmp_path / "env-root" / "rulespec-us")
    other = _git_init_clean(tmp_path / "TheAxiomFoundation" / "rulespec-us")
    engine = _git_init_clean(tmp_path / "engine", gitignore="target/\n")
    monkeypatch.setenv("RULESPEC_US_REPO", str(env_root))
    monkeypatch.setenv("AXIOM_RULES_REPO", str(engine))
    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda repo, *, kind: None
    )
    binary = engine / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    params = {"rulespec_roots": [str(other)]}

    root, _rules = run_comparison._resolve_state_income_tax_grid_repos(params)

    assert root == env_root.resolve()


def test_pinned_snapshot_unusable_reason(tmp_path):
    run_comparison = load_run_comparison_module()
    repo = tmp_path / "rulespec-us"
    repo.mkdir()
    assert run_comparison._pinned_snapshot_unusable_reason(repo, "0" * 40)
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    (repo / "a.txt").write_text("law\n")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "--quiet", "-m", "one"], check=True)
    tree = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert run_comparison._pinned_snapshot_unusable_reason(repo, tree) is None
    mismatch = run_comparison._pinned_snapshot_unusable_reason(repo, "0" * 40)
    assert "does not match" in mismatch
    (repo / "a.txt").write_text("edited\n")
    assert "dirty" in run_comparison._pinned_snapshot_unusable_reason(repo, tree)


def test_ensure_rulespec_us_checkout_materializes_pinned_revision(tmp_path):
    """The pinned SHA — no longer the remote's HEAD — is fetched and checked
    out detached, emulating GitHub's reachable-SHA fetch on the test remote."""
    run_comparison = load_run_comparison_module()
    remote = tmp_path / "remote"
    subprocess.run(["git", "init", "--quiet", str(remote)], check=True)
    git = ["git", "-C", str(remote), "-c", "user.name=t", "-c", "user.email=t@t"]
    (remote / "law.yaml").write_text("v1\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "--quiet", "-m", "one"], check=True)
    pinned_sha = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (remote / "law.yaml").write_text("v2\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "--quiet", "-m", "two"], check=True)
    subprocess.run(
        ["git", "-C", str(remote), "config", "uploadpack.allowAnySHA1InWant", "true"],
        check=True,
    )

    target = run_comparison._ensure_rulespec_us_checkout(
        remote.as_uri(), pinned_sha
    )

    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == pinned_sha
    assert (target / "law.yaml").read_text() == "v1\n"
    assert target.name == "rulespec-us"


def test_federal_grid_materializes_pin_when_configured_root_mismatches(
    monkeypatch, tmp_path
):
    """A configured root at the wrong tree no longer kills the leg — the
    pinned revision is materialized in a scratch clone instead."""
    run_comparison = load_run_comparison_module()
    stale_root = tmp_path / "rulespec-us"
    stale_root.mkdir()
    monkeypatch.setattr(
        run_comparison,
        "_pinned_snapshot_unusable_reason",
        lambda root, tree: "tree mismatch (test)",
    )
    pinned_clone = tmp_path / "scratch" / "rulespec-us"
    pinned_clone.mkdir(parents=True)
    calls = []

    def fake_checkout(remote, revision=None):
        calls.append((remote, revision))
        return pinned_clone

    monkeypatch.setattr(
        run_comparison, "_ensure_rulespec_us_checkout", fake_checkout
    )
    verified = []
    monkeypatch.setattr(
        run_comparison,
        "_verify_federal_rulespec_snapshot",
        lambda params, roots: verified.append([str(r) for r in roots]),
    )
    monkeypatch.setattr(
        run_comparison.subprocess,
        "run",
        lambda cmd, *, check, cwd: subprocess.CompletedProcess(cmd, 0),
    )
    params = {
        "policy": "qualified_business_income_deduction",
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
        "rulespec_roots": [str(stale_root)],
        "rulespec_remote": "https://example.test/rulespec-us.git",
        "rulespec_upstream_sha": "a" * 40,
        "rulespec_upstream_tree": "b" * 40,
    }

    run_comparison._run_federal_tax_liability_grid(
        {"parameters": params}, tmp_path / "out.json"
    )

    assert calls == [("https://example.test/rulespec-us.git", "a" * 40)]
    assert params["rulespec_roots"] == [str(pinned_clone)]
    assert verified == [[str(pinned_clone)]]


def test_federal_grid_accepts_configured_root_matching_pin(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    good_root = tmp_path / "rulespec-us"
    good_root.mkdir()
    monkeypatch.setattr(
        run_comparison, "_pinned_snapshot_unusable_reason", lambda root, tree: None
    )
    monkeypatch.setattr(
        run_comparison,
        "_ensure_rulespec_us_checkout",
        lambda *_a, **_k: pytest.fail("must not clone when the root matches"),
    )
    monkeypatch.setattr(
        run_comparison, "_verify_federal_rulespec_snapshot", lambda params, roots: None
    )
    monkeypatch.setattr(
        run_comparison.subprocess,
        "run",
        lambda cmd, *, check, cwd: subprocess.CompletedProcess(cmd, 0),
    )
    params = {
        "policy": "qualified_business_income_deduction",
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
        "rulespec_roots": [str(good_root)],
        "rulespec_remote": "https://example.test/rulespec-us.git",
        "rulespec_upstream_sha": "a" * 40,
        "rulespec_upstream_tree": "b" * 40,
    }

    run_comparison._run_federal_tax_liability_grid(
        {"parameters": params}, tmp_path / "out.json"
    )

    assert params["rulespec_roots"] == [str(good_root)]
