"""The live SNAP QC replay lane: suite selection, report gate, and workflow.

``scripts/snap_qc_replay.py`` decides which suites the weekly live replay runs
and refuses any report that was not computed on the run or is not exact. These
tests pin the classification against the registry (so a new SNAP QC suite
cannot silently stay out of the lane), every failure mode of ``check``, and
the workflow invariants the replay depends on.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "snap-qc-replay.yml"
SHA = "f" * 40


def _load_script():
    path = REPO_ROOT / "scripts" / "snap_qc_replay.py"
    spec = importlib.util.spec_from_file_location("snap_qc_replay", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


replay = _load_script()

_CONCEPTS = [
    "us:regulations/7-cfr/273/10#snap_total_gross_income",
    "us:policies/usda/snap/fy-2024-cola/deductions#snap_standard_deduction",
    "us:regulations/7-cfr/273/10#snap_net_monthly_income",
    "us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment",
]


def _exact_report(case_count: int = 3, *, binary: str = "/engine/bin") -> dict:
    """A live, exact report in the shape snap_qc_compare._build_report emits."""
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "co-snap-qc",
        "case_count": case_count,
        "concepts": [{"id": concept} for concept in _CONCEPTS],
        "aggregates": [
            {
                "concept": concept,
                "comparison_count": case_count,
                "mismatch_count": 0,
                "missing_left_count": 0,
                "missing_right_count": 0,
                "missing_both_count": 0,
            }
            for concept in _CONCEPTS
        ],
        "summary": {
            "comparison_count": case_count,
            "match_count": case_count,
            "mismatch_count": 0,
            "error_case_count": 0,
            "stages": [],
            "provenance": {"axiom_binary": binary},
        },
        "mismatches": [],
        "errors": [],
        "provenance": {
            "rulespecs": [{"repo": "TheAxiomFoundation/rulespec-us", "sha": SHA}],
        },
    }


# --------------------------------------------------------------------------- #
# Classification against the registry
# --------------------------------------------------------------------------- #


def test_every_registered_snap_qc_suite_is_classified_exactly_once():
    registered = replay.registered_suites()
    assert registered, "no snap-qc-compare suites found in comparisons/"
    assert replay.classification_errors(registered) == []
    assert set(replay.REQUIRED_SUITES) | set(replay.PENDING_SUITES) == set(registered)


def test_classification_errors_name_unclassified_and_stale_suites(monkeypatch):
    monkeypatch.setattr(replay, "REQUIRED_SUITES", ("co-snap-qc", "gone-snap-qc"))
    monkeypatch.setattr(replay, "PENDING_SUITES", {"co-snap-qc": "tracker"})
    errors = replay.classification_errors(["co-snap-qc", "new-snap-qc"])
    assert any("co-snap-qc is both required and pending" in e for e in errors)
    assert any("new-snap-qc is a registered" in e for e in errors)
    assert any("gone-snap-qc is classified" in e for e in errors)


def test_required_suite_compositions_resolve_to_rulespec_paths():
    registered = replay.registered_suites()
    for name in replay.REQUIRED_SUITES:
        program = replay.composition_path(registered[name])
        assert not program.is_absolute()
        assert program.suffix == ".yaml"


def _rulespec_with(tmp_path: Path, *suites: str) -> Path:
    root = tmp_path / "rulespec-us"
    registered = replay.registered_suites()
    for name in suites:
        program = root / replay.composition_path(registered[name])
        program.parent.mkdir(parents=True, exist_ok=True)
        program.write_text("module: {}\n")
    return root


def test_select_runs_every_required_suite_and_notes_unlanded_pending(tmp_path):
    root = _rulespec_with(tmp_path)  # no compositions at all
    selected, landed, notes = replay.select_suites(root)
    # Required suites run even when their composition is missing: the leg
    # must fail loudly, never drop out of the matrix.
    assert selected == list(replay.REQUIRED_SUITES)
    assert landed == []
    assert [note.split(":")[0] for note in notes] == list(replay.PENDING_SUITES)


def test_select_adds_a_pending_suite_once_its_composition_lands(tmp_path):
    pending = next(iter(replay.PENDING_SUITES))
    root = _rulespec_with(tmp_path, pending)
    selected, landed, notes = replay.select_suites(root)
    assert selected == [*replay.REQUIRED_SUITES, pending]
    assert landed == [pending]
    assert notes == []


def test_select_only_restricts_and_rejects_unknown_names(tmp_path):
    root = _rulespec_with(tmp_path)
    selected, _, notes = replay.select_suites(root, only=["ca-snap-qc"])
    assert selected == ["ca-snap-qc"]
    assert notes == []
    with pytest.raises(SystemExit, match="unknown snap-qc-compare suite"):
        replay.select_suites(root, only=["xx-snap-qc"])


def test_suites_command_writes_matrix_and_cache_key(tmp_path, monkeypatch, capsys):
    output = tmp_path / "github_output"
    summary = tmp_path / "step_summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    root = _rulespec_with(tmp_path)

    assert replay.main(["suites", "--rulespec-root", str(root)]) == 0

    lines = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert json.loads(lines["suites"]) == list(replay.REQUIRED_SUITES)
    assert lines["puf_cache_key"] == replay.puf_cache_key(
        replay.fiscal_years(replay.registered_suites())
    )
    assert "co-snap-qc" in summary.read_text()


def test_puf_cache_key_changes_with_the_pin(monkeypatch):
    from axiom_oracles.populations import snap_qc

    before = replay.puf_cache_key([2024])
    pin = snap_qc.SNAP_QC_PINS[2024]
    repinned = snap_qc.SnapQcPin(
        fiscal_year=2024,
        url=pin.url.replace("2026-05", "2026-08"),
        sha256="b" * 64,
        archive_member=pin.archive_member,
    )
    monkeypatch.setitem(snap_qc.SNAP_QC_PINS, 2024, repinned)
    assert replay.puf_cache_key([2024]) != before


# --------------------------------------------------------------------------- #
# check_report: every way a report can fail the gate
# --------------------------------------------------------------------------- #


def _check(report: dict, **kwargs) -> list[str]:
    kwargs.setdefault("expect_rulespec_sha", SHA)
    kwargs.setdefault("expect_axiom_binary", Path("/engine/bin"))
    return replay.check_report(report, suite="co-snap-qc", **kwargs)


def test_live_exact_report_passes():
    assert _check(_exact_report()) == []


def test_reemitted_report_fails_even_with_perfect_numbers():
    report = _exact_report()
    report["provenance"]["reemitted_report"] = True
    report["provenance"]["reemitted_from"] = {"generated_at": "2026-07-13"}
    failures = _check(report)
    assert any("re-emitted the committed report" in f for f in failures)


def test_benefit_mismatch_fails():
    report = _exact_report()
    report["summary"]["mismatch_count"] = 1
    report["mismatches"] = [{"case_id": "2024-202401-7", "stage": "benefit"}]
    assert any("1 of 3 cases miss the QC benefit" in f for f in _check(report))


def test_error_cases_and_rows_fail():
    report = _exact_report()
    report["summary"]["error_case_count"] = 1
    report["errors"] = [{"case_id": "x", "error": "missing output y"}]
    assert any("1 error cases and 1 error rows" in f for f in _check(report))


def test_stage_only_divergence_fails_although_the_benefit_matches():
    report = _exact_report()
    report["aggregates"][1]["mismatch_count"] = 2
    failures = _check(report)
    assert failures == [f"stage {_CONCEPTS[1]}: 2 mismatches"]


def test_uncompared_or_partially_compared_stage_fails():
    report = _exact_report()
    dropped = report["aggregates"].pop(0)
    report["aggregates"][0]["comparison_count"] = 2
    report["aggregates"][0]["missing_right_count"] = 1
    failures = _check(report)
    assert f"stage {dropped['concept']} was never compared" in failures
    assert f"stage {_CONCEPTS[1]}: compared 2/3, 1 missing_right" in failures


def test_empty_report_fails():
    failures = _check(_exact_report(case_count=0))
    assert "no cases were compared" in failures


def test_wrong_rulespec_sha_or_engine_fails():
    report = _exact_report(binary="/other/engine")
    failures = _check(report, expect_rulespec_sha="a" * 40)
    assert any("expected " + "a" * 40 in f for f in failures)
    assert any("ran engine binary /other/engine" in f for f in failures)


def test_wrong_suite_fails():
    report = _exact_report()
    report["suite"] = "ny-snap-qc"
    assert any("not 'co-snap-qc'" in f for f in _check(report))


def test_divergent_cases_name_the_first_stage_and_the_benefit():
    report = _exact_report()
    report["mismatches"] = [
        {
            "case_id": "2024-202403-11",
            "yrmonth": 202403,
            "stage": "shelter_deduction",
            "qc": {"shelter_deduction": 400.0, "benefit": 291},
            "axiom": {"shelter_deduction": 390.0, "benefit": 288},
        }
    ] * 3
    report["errors"] = [{"case_id": "2024-202403-12", "error": "missing output z"}]
    lines = replay.divergent_cases(report, max_cases=2)
    assert lines[0] == (
        "case 2024-202403-11 (202403): first divergent stage shelter_deduction: "
        "QC 400.0 vs Axiom 390.0; benefit QC 291 vs Axiom 288"
    )
    assert lines[2] == "... and 1 more mismatched cases"
    assert lines[3] == "case 2024-202403-12: missing output z"


def test_failure_excerpt_prefers_the_raised_exception():
    log = "\n".join(
        [
            "Running ca-snap-qc: California CalFresh",
            "Traceback (most recent call last):",
            '  File "x.py", line 1, in <module>',
            "RuntimeError: unknown command `compile-composed`",
            "(legacy compile fallback also failed: duplicate derived rule `r`)",
        ]
    )
    assert replay.failure_excerpt(log) == (
        "RuntimeError: unknown command `compile-composed`\n"
        "(legacy compile fallback also failed: duplicate derived rule `r`)"
    )
    refused = "Running x\nSNAP QC replay not runnable here (no QC file)\nx: --require-live: ..."
    assert replay.failure_excerpt(refused) == (
        "SNAP QC replay not runnable here (no QC file)\nx: --require-live: ..."
    )


# --------------------------------------------------------------------------- #
# The check command end to end
# --------------------------------------------------------------------------- #


def _write_report(directory: Path, report: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "axiom-snapqc-co-snap-0-2026-09-22.json"
    path.write_text(json.dumps(report))
    return path


def test_check_passes_a_live_exact_report(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    report_dir = tmp_path / "reports"
    case_count = replay.committed_case_count(replay.registered_suites()["co-snap-qc"])
    _write_report(report_dir, _exact_report(case_count=case_count or 3))
    code = replay.main(
        [
            "check",
            "co-snap-qc",
            "--report-dir",
            str(report_dir),
            "--expect-rulespec-sha",
            SHA,
            "--expect-axiom-binary",
            "/engine/bin",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert "co-snap-qc: PASS" in out
    assert "::error" not in out
    assert "### co-snap-qc: PASS" in summary.read_text()


def test_check_without_a_report_quotes_the_replay_error(tmp_path, capsys):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    log = report_dir / "replay.log"
    log.write_text(
        "Traceback (most recent call last):\n"
        "RuntimeError: unknown command `compile-composed`\n"
        "(legacy compile fallback also failed: duplicate derived rule "
        "`snap_net_income_limit_100_percent_fpl_48_states_dc`)\n"
    )
    code = replay.main(
        ["check", "ca-snap-qc", "--report-dir", str(report_dir), "--log", str(log)]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "::error title=SNAP QC replay failed: ca-snap-qc::" in out
    assert "duplicate derived rule" in out


def test_check_fails_a_published_report_when_the_replay_step_failed(tmp_path, capsys):
    report_dir = tmp_path / "reports"
    _write_report(report_dir, _exact_report())
    (report_dir / "replay.log").write_text("ValueError: chunk index drift\n")
    code = replay.main(
        [
            "check",
            "co-snap-qc",
            "--report-dir",
            str(report_dir),
            "--log",
            str(report_dir / "replay.log"),
            "--replay-failed",
        ]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "the replay failed (this report may be from an earlier run): ValueError" in out


def test_check_fails_a_stale_report_when_the_log_records_a_failure(tmp_path, capsys):
    # A reused directory: an earlier run's exact report is still there, and
    # this run was refused before publishing. The log alone must fail it.
    report_dir = tmp_path / "reports"
    _write_report(report_dir, _exact_report())
    (report_dir / "replay.log").write_text(
        "Running co-snap-qc: Colorado SNAP\n"
        "SNAP QC replay not runnable here (no QC file); re-emitting ...\n"
        "co-snap-qc: --require-live: the runner re-emitted the committed report ...\n"
    )
    code = replay.main(
        ["check", "co-snap-qc", "--report-dir", str(report_dir), "--log", str(report_dir / "replay.log")]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "SNAP QC replay not runnable here" in out


def test_check_passes_with_a_clean_log(tmp_path, capsys):
    report_dir = tmp_path / "reports"
    case_count = replay.committed_case_count(replay.registered_suites()["co-snap-qc"])
    _write_report(report_dir, _exact_report(case_count=case_count or 3))
    (report_dir / "replay.log").write_text(
        "Running co-snap-qc: Colorado SNAP\nWrote: x.json\nCases: 856\nMismatch entries:  0\n"
    )
    code = replay.main(
        ["check", "co-snap-qc", "--report-dir", str(report_dir), "--log", str(report_dir / "replay.log")]
    )
    assert code == 0, capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Workflow invariants
# --------------------------------------------------------------------------- #


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _steps(job: str) -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def test_workflow_runs_weekly_and_on_demand_only():
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads `on` as True
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["schedule"][0]["cron"].split()[-1] == "1"  # weekly (Mondays)
    assert workflow["permissions"] == {"contents": "read"}


def test_every_job_checks_rulespec_us_out_under_its_repo_basename():
    # The engine serves `us:` imports only from a root named rulespec-us
    # (rulespec-us-<x>); any other checkout directory breaks every compile.
    for job, spec in _workflow()["jobs"].items():
        for step in spec["steps"]:
            with_ = step.get("with") or {}
            if with_.get("repository") == "TheAxiomFoundation/rulespec-us":
                assert with_["path"] == "rulespec-us", job


def test_engine_is_built_at_the_artifact_pin_and_shared_by_one_key():
    prepare = "\n".join(json.dumps(step) for step in _steps("prepare"))
    assert "axiom_artifact_rules_engine_ref" in prepare
    assert "cargo build --release --locked --bin axiom-rules-engine" in prepare
    engine = "engine/target/release/axiom-rules-engine"
    keys = {
        job: [
            step["with"]["key"]
            for step in _steps(job)
            if (step.get("with") or {}).get("path") == engine
        ]
        for job in ("prepare", "replay", "live-tests")
    }
    # One key, computed once in prepare, restored verbatim by every consumer.
    assert keys["prepare"] == ["${{ steps.toolchain.outputs.engine_cache_key }}"]
    assert keys["replay"] == keys["live-tests"] == [
        "${{ needs.prepare.outputs.engine_cache_key }}"
    ]
    assert _workflow()["jobs"]["prepare"]["outputs"]["engine_cache_key"] == (
        keys["prepare"][0]
    )


def test_every_job_runs_on_one_pinned_image():
    # The engine binary is cached once and restored by every job: a floating
    # label (ubuntu-latest mid-migration) could restore it onto an image with
    # an older glibc than the one it was linked on.
    images = {spec["runs-on"] for spec in _workflow()["jobs"].values()}
    assert len(images) == 1
    assert "latest" not in images.pop()
    prepare = "\n".join(json.dumps(step) for step in _steps("prepare"))
    assert "ImageOS" in prepare


def test_replay_requires_a_live_run_and_checks_even_after_failure():
    steps = {step.get("id") or step.get("name"): step for step in _steps("replay")}
    assert "--require-live" in steps["replay"]["run"]
    check = next(step for step in _steps("replay") if "snap_qc_replay.py check" in step.get("run", ""))
    assert "steps.replay.outcome != 'skipped'" in check["if"]
    assert "--expect-rulespec-sha" in check["run"]
    assert "--expect-axiom-binary" in check["run"]
    env = steps["replay"]["env"]
    assert env["AXIOM_SNAP_QC_RULESPEC_ROOT"].endswith("/rulespec-us")
    assert set(env) >= {
        "AXIOM_SNAP_QC_RULESPEC_ROOT",
        "AXIOM_SNAP_QC_AXIOM_BINARY",
        "AXIOM_SNAP_QC_DATA_DIR",
    }


def test_replay_matrix_never_fails_fast():
    strategy = _workflow()["jobs"]["replay"]["strategy"]
    assert strategy["fail-fast"] is False
    assert strategy["matrix"]["suite"] == "${{ fromJson(needs.prepare.outputs.suites) }}"


def test_workflow_never_commits():
    text = WORKFLOW.read_text()
    assert "git push" not in text
    assert "contents: write" not in text

