import importlib.util
import json
import subprocess
from pathlib import Path


def load_run_comparison_module():
    module_path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison", module_path)
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

    def fake_run(cmd, *, check, stdout=None, cwd=None):
        del check, cwd
        calls.append(cmd)
        if stdout is not None:
            stdout.write("{}")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_encode_tax_ecps_compare(
        {
            "axiom_encode_repo": str(axiom_encode),
            "axiom_rules_repo": str(axiom_rules),
            "rulespec_remote": "https://example.test/rulespec-us.git",
            "parameters": {
                "sample_size": 1000,
                "year": 2026,
                "python": "3.13",
                "surface": "all",
                "pinned": True,
            },
        },
        output,
    )

    cmd = calls[0]
    assert cmd[:4] == ["uv", "run", "--python", "3.13"]
    assert "--with-editable" in cmd
    assert str(axiom_encode.resolve()) in cmd
    assert "policyengine==4.11.0" in cmd
    assert "policyengine-us==1.705.1" in cmd
    assert "policyengine-core==3.26.11" in cmd
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

    def fake_run(cmd, *, check, cwd=None, env=None):
        del check, cwd, env
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

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
    assert calls[1] == [
        str(axiom_rules.resolve() / "target" / "release" / "axiom-rules-engine"),
        "compile",
        "--program",
        str(composed.resolve()),
        "--output",
        str(compiled.resolve()),
    ]
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
    assert "snap-ecps-compare" in cmd
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
    assert len(report["cases"]) == 1
    assert report["cases"][0]["metadata"]["axiom_ny_snap_categorically_eligible"]
    assert report["cases"][0]["metadata"][
        "axiom_ny_snap_residual_130_percent_categorical_path_satisfied"
    ]
    assert report["cases"][0]["metadata"]["pe_standard_deduction"] == 209


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
