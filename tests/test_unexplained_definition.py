"""Conservative semantics remain available without changing public numbers."""

from __future__ import annotations

import json
import importlib.util
import math
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.conformance import unexplained
from axiom_oracles.conformance.loader import OracleIdentity, Universe, load_dashboard_reports
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.conformance import scoreboard as scoreboard_module
from axiom_oracles.conformance.unexplained import (
    admit_count,
    assess_unexplained,
    published_unexplained,
    require_count,
    resolve_suite_reports,
)

ROOT = Path(__file__).resolve().parents[1]


def _report(mismatch=10, classified=0, declared=0):
    return {
        "suite": "sample",
        "engines": {"left": "axiom", "right": "reference"},
        "summary": {
            "mismatch_count": mismatch,
            "dispositioned": {
                "unexplained_count": declared,
                "counts": {"upstream_engine_gap": classified, "unexplained": declared},
            },
        },
        "mismatches": [],
    }


@given(st.integers(min_value=0, max_value=10**12))
@settings(deadline=None, database=None)
def test_admission_preserves_counts(value):
    assert admit_count(value) == value
    assert admit_count(float(value)) == value


@given(st.one_of(st.text(), st.booleans(), st.none(), st.integers(max_value=-1)))
@settings(deadline=None, database=None)
def test_unparseable_counts_never_become_zero(value):
    assert admit_count(value) is None
    with pytest.raises(ValueError, match="count"):
        require_count(value, "mismatch_count")


@given(st.integers(min_value=0, max_value=10000), st.data())
@settings(deadline=None, database=None)
def test_unexplained_stays_between_zero_and_mismatches(mismatch, data):
    classified = data.draw(st.integers(min_value=0, max_value=mismatch))
    declared = data.draw(st.integers(min_value=0, max_value=mismatch))
    assessment = assess_unexplained(_report(mismatch, classified, declared))
    assert 0 <= assessment.count <= mismatch
    assert assessment.count == max(declared, mismatch - classified)


@given(st.integers(min_value=0, max_value=10000), st.integers(min_value=1, max_value=10000))
@settings(deadline=None, database=None)
def test_impossible_declared_counts_fail_instead_of_publishing(mismatch, excess):
    with pytest.raises(ValueError, match="exceeds mismatches"):
        assess_unexplained(_report(mismatch, declared=mismatch + excess))
    with pytest.raises(ValueError, match="exceed mismatches"):
        assess_unexplained(_report(mismatch, classified=mismatch + excess))


@given(st.integers(min_value=0, max_value=10000), st.data())
@settings(deadline=None, database=None)
def test_raising_valid_signal_or_removing_classification_never_lowers_count(mismatch, data):
    classified = data.draw(st.integers(min_value=0, max_value=mismatch))
    declared = data.draw(st.integers(min_value=0, max_value=mismatch))
    raised = data.draw(st.integers(min_value=declared, max_value=mismatch))
    fewer = data.draw(st.integers(min_value=0, max_value=classified))
    baseline = assess_unexplained(_report(mismatch, classified, declared)).count
    assert assess_unexplained(_report(mismatch, classified, raised)).count >= baseline
    assert assess_unexplained(_report(mismatch, fewer, declared)).count >= baseline


@given(st.lists(st.integers(min_value=0, max_value=10000), min_size=1, max_size=10))
@settings(deadline=None, database=None)
def test_conservative_duplicate_resolution_is_order_independent(counts):
    reports = [_report(count, declared=count) for count in counts]
    forward = resolve_suite_reports(reports)
    reverse = resolve_suite_reports(reversed(reports))
    assert forward == reverse
    assert assess_unexplained(forward["sample"]).count == max(counts)


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "1", float("nan"), float("inf"), None])
@pytest.mark.parametrize("field", ["mismatch_count", "unexplained_count", "upstream_engine_gap"])
def test_invalid_count_fails_with_semantics_switch_off_or_on(value, field, monkeypatch):
    report = _report()
    if field == "mismatch_count":
        report["summary"][field] = value
    elif field == "unexplained_count":
        report["summary"]["dispositioned"][field] = value
    else:
        report["summary"]["dispositioned"]["counts"][field] = value
    for enabled in (False, True):
        monkeypatch.setattr(unexplained, "CONSERVATIVE_UNEXPLAINED_ENABLED", enabled)
        with pytest.raises(ValueError, match=field):
            published_unexplained(report)


def test_conservative_switch_is_off_and_preserves_committed_spsm(monkeypatch):
    assert unexplained.CONSERVATIVE_UNEXPLAINED_ENABLED is False
    report = json.loads((ROOT / "dashboard/public/data/axiom-spsm-ca-federal-schedule-tax.json").read_text())
    assert published_unexplained(report) == 0
    assert published_unexplained(report, view="scoreboard") == 97
    assert assess_unexplained(report).count == 97
    monkeypatch.setattr(unexplained, "CONSERVATIVE_UNEXPLAINED_ENABLED", True)
    assert published_unexplained(report) == 97


@pytest.mark.parametrize("payload", ['{"broken":', '{"value": NaN}', '{"value": Infinity}', '{"value": 1e999}'])
def test_shared_dashboard_loader_fails_on_invalid_json(tmp_path, payload):
    (tmp_path / "broken.json").write_text(payload)
    with pytest.raises(ValueError, match="broken.json: invalid dashboard JSON"):
        load_dashboard_reports(tmp_path)


def _universe():
    return Universe("tx", OracleIdentity("M", "R", "S", "TX", "euromod"), [
        UniversePolicy("tx:x", "x", ("x_s",), True, suite="sample"),
        UniversePolicy("tx:excluded", "excluded", ("z_s",), False,
                       exclusion_reason="oracle_dataset_lacks_input", note="no activating input"),
    ])


@pytest.mark.parametrize("exposure", [float("nan"), float("inf"), -float("inf"), "5", None, True, [], {}])
def test_invalid_exposure_cannot_witness_or_support_an_exclusion(exposure):
    report = _report(0)
    report["scope"] = {"column_exposure": {"x_s": exposure, "z_s": exposure}}
    board, _ = score_jurisdiction(_universe(), [report])
    assert board.covered == 0
    assert board.unwitnessed_policies == ["x"]
    assert board.invalid_exclusions == ["excluded"]
    assert board.conformant is False


def test_conflicting_duplicate_coverage_is_contested_in_both_orders():
    clean = {**_report(0), "_file": "clean.json"}
    failing = {**_report(5, declared=5), "_file": "failing.json"}
    results = []
    for reports in ([clean, failing], [failing, clean]):
        board, scores = score_jurisdiction(_universe(), reports)
        assert board.covered == 0
        assert scores[0].status == "contested"
        assert any("clean.json, failing.json" in reason for reason in board.blocking_reasons)
        results.append(board.to_summary())
    assert results[0] == results[1]


def test_duplicate_cannot_hide_malformed_summary_count():
    invalid = _report(0)
    invalid["summary"]["mismatch_count"] = True
    with pytest.raises(ValueError, match="boolean"):
        score_jurisdiction(_universe(), [_report(5, declared=5), invalid])


def test_scoreboard_file_validation_is_off_and_preserves_existing_badge(tmp_path, monkeypatch):
    assert scoreboard_module.SCOREBOARD_DISPOSITION_FILE_VALIDATION_ENABLED is False
    report = _report(0)
    report["summary"]["dispositioned"]["dispositions_file"] = "dispositions/missing.yaml"
    board, rows = score_jurisdiction(_universe(), [report], known_causes=[], repo_root=tmp_path)
    assert board.conformant is True
    assert rows[0].status == "conformant"
    monkeypatch.setattr(scoreboard_module, "SCOREBOARD_DISPOSITION_FILE_VALIDATION_ENABLED", True)
    board, rows = score_jurisdiction(_universe(), [report], known_causes=[], repo_root=tmp_path)
    assert board.conformant is False
    assert rows[0].status == "invalid-report"
    assert any("dispositions/missing.yaml" in reason for reason in board.blocking_reasons)


def _javascript(cases):
    def encode_mutants(value):
        if isinstance(value, float) and not math.isfinite(value):
            return {"$nonfinite": repr(value)}
        if isinstance(value, dict):
            return {key: encode_mutants(item) for key, item in value.items()}
        if isinstance(value, list):
            return [encode_mutants(item) for item in value]
        return value

    proc = subprocess.run(["node", str(ROOT / "dashboard/scripts/test-unexplained-parity.mjs")],
                          input=json.dumps(encode_mutants(cases), allow_nan=False), text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime unavailable")
def test_unexplained_gate_domain_and_total_parity(monkeypatch):
    spec = importlib.util.spec_from_file_location("unexplained_gate_parity", ROOT / "scripts/unexplained_ratchet.py")
    ratchet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ratchet)
    reports = load_dashboard_reports(ROOT / "dashboard/public/data")
    grid = {"suite": "zz-parity-grid", "engines": {"axiom": "a", "policyengine": "p"},
            "summary": {"mismatch_count": 5}, "mismatches": [{"concept": "c"}] * 5}
    duplicate_low = {"suite": "zz-parity-duplicate", "engines": {"left": "axiom", "right": "reference"},
                     "summary": {"mismatch_count": 2}, "mismatches": [{"concept": "c"}] * 2}
    duplicate_high = {**duplicate_low, "summary": {"mismatch_count": 7}, "mismatches": [{"concept": "c"}] * 7}
    reports.extend([grid, duplicate_low, duplicate_high])
    monkeypatch.setattr(ratchet, "load_dashboard_reports", lambda _directory: reports)
    expected = ratchet.live_counts()
    assert expected["zz-parity-grid"] == 5
    assert expected["zz-parity-duplicate"] == 7
    documents = [{key: report[key] for key in ("suite", "engines", "summary", "mismatches") if key in report} for report in reports]
    payload = {"documents": documents, "known_causes": unexplained.load_known_causes(ROOT),
               "diagnostics": sorted(ratchet.diagnostic_suites()), "expected": expected}
    proc = subprocess.run(["node", str(ROOT / "dashboard/scripts/test-unexplained-gate-total.mjs")],
                          input=json.dumps(payload, allow_nan=False), text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"UNEXPLAINED GATE PARITY: {len(expected)} suites" in proc.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime unavailable")
def test_python_javascript_parity_on_every_committed_report_and_mutants():
    causes = unexplained.load_known_causes(ROOT)
    cases = []
    for report in load_dashboard_reports(ROOT / "dashboard/public/data"):
        # Only fields the assessment reads cross the process boundary.
        subset = {key: report[key] for key in ("suite", "engines", "summary", "mismatches") if key in report}
        cases.append({"report": subset, "options": {"known_causes": causes}})
    for value in (True, False, -1, 1.5, "1", None, 11, float("nan"), float("inf"), -float("inf")):
        for field in ("mismatch_count", "unexplained_count", "upstream_engine_gap"):
            report = _report()
            if field == "mismatch_count":
                report["summary"][field] = value
            elif field == "unexplained_count":
                report["summary"]["dispositioned"][field] = value
            else:
                report["summary"]["dispositioned"]["counts"][field] = value
            cases.append({"report": report, "options": {}})
    expected = []
    for case in cases:
        report, options = case["report"], case["options"]
        try:
            result = asdict(assess_unexplained(report, **options))
            result["defects"] = list(result["defects"])
            result["notes"] = list(result["notes"])
            expected.append({"assessment": result,
                             "dashboard": published_unexplained(report, **options),
                             "scoreboard": published_unexplained(report, view="scoreboard", **options)})
        except ValueError as exc:
            expected.append({"error": str(exc)})
    assert _javascript(cases) == expected


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime unavailable")
def test_javascript_publication_switch_is_off():
    source = (ROOT / "dashboard/src/utils/unexplained.js").read_text()
    report = _report(8702, 8605, 97)
    report["mismatches"] = [{}] * 50
    script = source + "\n" + f"const report = {json.dumps(report)};\n" + """
if (CONSERVATIVE_UNEXPLAINED_ENABLED !== false) process.exit(1);
if (publishedUnexplained(report) !== 0) process.exit(2);
if (publishedUnexplained(report, {conservative: true}) !== 97) process.exit(3);
if (admitCount(9007199254740992) !== null) process.exit(4);
try { requireCount(9007199254740992, 'mismatch_count'); process.exit(5); } catch {}
"""
    subprocess.run(["node", "--input-type=module", "-e", script], check=True, capture_output=True)
