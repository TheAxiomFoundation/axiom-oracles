"""Load-bearing unexplained invariants, checked by examples and generated cases.

Every consumer uses one admitted count; malformed counts always carry a hard
failure, never silently authorize a clean gate. The count is nonnegative and at
least every admitted declared unexplained signal, even with capped/concept-less
rows. Only validated class counts or eligible known-cause rows explain work;
known causes apply only in mode none. The count is at least the number of
listed mismatch rows: a declared total below them is a hard defect.
Raising an unexplained signal or removing an explanation without replacing it
with another explanation cannot lower the count. Duplicate report order cannot
change the maximum per-suite count. Python and JS assessments must agree.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from hypothesis import given, strategies as st

from axiom_oracles.conformance.unexplained import (
    admit_count,
    assess_unexplained,
    load_known_causes,
    resolve_suite_reports,
)

ROOT = Path(__file__).resolve().parents[1]


def _report(mismatch=10, classified=0, declared=0, filename=None):
    return {
        "suite": "sample",
        "engines": {"left": "axiom", "right": "oracle"},
        "summary": {
            "mismatch_count": mismatch,
            "dispositioned": {
                "dispositions_file": filename,
                "unexplained_count": declared,
                "counts": {"upstream_engine_gap": classified, "unexplained": declared},
            },
        },
        "mismatches": [{"concept": "c", "kind": "amount_difference"}],
    }


def _cause(**kwargs):
    return {"suite": "sample", "concept": "c", "kind": "amount_difference", **kwargs}


def parity_cases():
    """Shared mutants transported to Node alongside every committed report."""
    cases = []
    for mismatch, classified, declared, filename in (
        (8702, 8605, 97, None), (8702, 8605, 5000, None),
        (10, 2, 1, None), (10, 30, 2, None), (0, 0, 10, None),
        (10, 9, 1, "dispositions/sample.yaml"), (10, 9, 9, None),
    ):
        report = _report(mismatch, classified, declared, filename)
        cases.append({"report": report, "options": {}})
        cases.append({"report": report, "options": {"known_causes": [_cause()]}})
    for value in (True, False, -1, -1.0, 0.5, float("nan"), float("inf"), float("-inf"), "7", None):
        for field in ("mismatch_count", "unexplained_count", "upstream_engine_gap", "unexplained"):
            report = _report()
            if field == "mismatch_count":
                report["summary"][field] = value
            elif field == "unexplained_count":
                report["summary"]["dispositioned"][field] = value
            else:
                report["summary"]["dispositioned"]["counts"][field] = value
            cases.append({"report": report, "options": {}})
    for rows in ([{}], [{"concept": "c", "kind": "amount_difference", "disposition": None}],
                 [{"concept": "c", "kind": "amount_difference"}] * 2, [None]):
        cases.append({"report": {**_report(1), "mismatches": rows}, "options": {"known_causes": [_cause()]}})
    cases.extend([
        {"report": {"suite": "empty"}, "options": {}},
        {"report": {"suite": "bad", "summary": [], "mismatches": 1}, "options": {}},
        {"report": _report(), "options": {"summary": {"mismatch_count": 1}, "rows": [{}]}},
        {"report": _report(1), "options": {"known_causes": [_cause(fix_owner="rulespec-us")]}},
        {"report": _report(1), "options": {"known_causes": [_cause(engines={"left": "other", "right": "oracle"})]}},
    ])
    report = _report(1, 1)
    report["summary"]["dispositioned"]["counts"]["mystery"] = 1
    cases.append({"report": report, "options": {}})
    understated = {"suite": "sample", "summary": {"mismatch_count": 0},
                   "mismatches": [{"concept": "c", "kind": "amount_difference"}] * 3}
    cases.append({"report": understated, "options": {}})
    cases.append({"report": understated, "options": {"known_causes": [_cause()]}})
    return cases


def test_spsm_and_5000_mutant_gate_despite_capped_conceptless_rows():
    """A producer's admitted unexplained total survives a cap and missing concepts."""
    report = _report(8702, 8605, 97)
    report["mismatches"] = [{}] * 50
    report["summary"]["dispositioned"]["counts"]["unexplained"] = 0
    actual = assess_unexplained(report)
    assert actual.count == 97
    assert actual.mode == "inline"
    assert actual.classified == 8605
    assert actual.defects == ()
    assert "inline classification is producer-declared, not file-validated" in actual.notes
    report["summary"]["dispositioned"]["unexplained_count"] = 5000
    assert assess_unexplained(report).count == 5000


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "1", float("nan"), float("inf"), None])
@pytest.mark.parametrize("field", ["mismatch_count", "unexplained_count", "upstream_engine_gap", "unexplained"])
def test_junk_counts_fail_closed_with_field_diagnostics(value, field):
    """Junk counts are defects; a stored mismatch cannot silently become zero."""
    report = _report(1)
    if field == "mismatch_count":
        report["summary"][field] = value
    elif field == "unexplained_count":
        report["summary"]["dispositioned"][field] = value
    else:
        report["summary"]["dispositioned"]["counts"][field] = value
    assessment = assess_unexplained(report)
    assert assessment.count >= 1
    assert any(field in defect for defect in assessment.defects)


@given(st.integers(min_value=0, max_value=10**12))
def test_admission_preserves_nonnegative_integer_values(value):
    """Admission preserves exact counts, including integral finite JSON floats."""
    assert admit_count(value) == value
    assert admit_count(float(value)) == value


@given(st.integers(min_value=0, max_value=10000), st.integers(min_value=0, max_value=10000), st.integers(min_value=0, max_value=10000))
def test_inline_conservative_envelope(mismatch, classified, declared):
    """No disagreement can lower the maximum of declared and unclassified totals."""
    actual = assess_unexplained(_report(mismatch, classified, declared))
    # _report lists one row, which floors the mismatch total.
    assert actual.count == max(declared, max(mismatch, 1) - classified)
    assert actual.count >= 0
    assert actual.declared == declared
    if classified:
        assert actual.mode == "inline"


@given(st.integers(min_value=1, max_value=10000), st.integers(min_value=0, max_value=10000), st.integers(min_value=1, max_value=10000))
def test_raising_a_declared_signal_never_lowers_count(mismatch, declared, increase):
    """Increasing either admitted unexplained declaration is monotone in all modes."""
    for filename, classified in ((None, 0), (None, 3), ("dispositions/sample.yaml", 3)):
        original = _report(mismatch, classified, declared, filename)
        before = assess_unexplained(original, known_causes=[_cause()]).count
        for signal in ("unexplained_count", "unexplained"):
            mutant = copy.deepcopy(original)
            block = mutant["summary"]["dispositioned"]
            (block if signal == "unexplained_count" else block["counts"])[signal] += increase
            assert assess_unexplained(mutant, known_causes=[_cause()]).count >= before


@given(st.integers(min_value=0, max_value=10000), st.integers(min_value=1, max_value=10000), st.integers(min_value=0, max_value=10000))
def test_removing_classification_never_lowers_count(mismatch, classified, declared):
    """Removing classified evidence, with no replacement labels, cannot help a gate."""
    for filename in (None, "dispositions/sample.yaml"):
        original = _report(mismatch, classified, declared, filename)
        before = assess_unexplained(original).count
        for replacement in (0, classified - 1, None, "junk"):
            mutant = copy.deepcopy(original)
            mutant["summary"]["dispositioned"]["counts"]["upstream_engine_gap"] = replacement
            assert assess_unexplained(mutant).count >= before


@given(st.integers(min_value=1, max_value=100), st.integers(min_value=0, max_value=100))
def test_removing_known_cause_or_concept_never_lowers_count(size, extra):
    """Removing either the label or its eligible concept cannot explain more work."""
    original = {**_report(size + extra), "mismatches": [{"concept": "c", "kind": "amount_difference"}] * size}
    before = assess_unexplained(original, known_causes=[_cause()]).count
    assert assess_unexplained(original).count >= before
    original["mismatches"] = [{}] * size
    assert assess_unexplained(original, known_causes=[_cause()]).count >= before


def test_known_causes_only_explain_eligible_rows_in_none_mode():
    """Labels never double-subtract inline/file classifications or cover concept-less rows."""
    causes = [_cause()]
    report = _report(3)
    report["mismatches"] += [{}, {"concept": "c", "kind": "amount_difference", "disposition": {}}]
    actual = assess_unexplained(report, known_causes=causes)
    assert (actual.count, actual.known_cause_covered) == (2, 1)
    for filename in (None, "dispositions/sample.yaml"):
        actual = assess_unexplained(_report(3, 1, 0, filename), known_causes=causes)
        assert (actual.count, actual.known_cause_covered) == (2, 0)


def test_listed_rows_floor_an_understated_mismatch_total():
    """A listed row with mismatch_count 0 is a hard defect and still counts.

    Independent review of this change (2026-09-25): an unclassified listed row
    under a declared mismatch_count of 0 read 0 in the ratchet, the scoreboard
    and the dashboard.
    """
    report = _report(0)
    report["summary"]["dispositioned"] = None
    del report["summary"]["dispositioned"]
    actual = assess_unexplained(report)
    assert actual.count == 1
    assert actual.mismatch_count == 1
    assert any("mismatch rows are listed but mismatch_count is 0" in d for d in actual.defects)
    # A known cause may explain the listed row, but the understated total is
    # still a hard defect that fails every gate.
    covered = assess_unexplained(report, known_causes=[_cause()])
    assert covered.known_cause_covered == 1
    assert any("mismatch_count is 0" in d for d in covered.defects)


@given(st.integers(min_value=0, max_value=50), st.integers(min_value=0, max_value=50))
def test_count_is_never_below_unexplained_listed_rows(declared_total, listed):
    """Invariant: count >= listed rows that nothing explains."""
    report = {
        "suite": "sample",
        "summary": {"mismatch_count": declared_total},
        "mismatches": [{"concept": "c", "kind": "amount_difference"}] * listed,
    }
    actual = assess_unexplained(report)
    assert actual.count >= listed
    assert actual.count >= declared_total
    assert bool(actual.defects) == (listed > declared_total)


def test_attribution_prefers_engine_specific_cause_and_counts_linked_issues_once():
    """Axiom ownership follows the selected known cause or classified-row issue."""
    causes = [_cause(fix_owner="rulespec-us"), _cause(engines={"left": "axiom", "right": "oracle"}, fix_owner="oracle")]
    assert assess_unexplained(_report(1), known_causes=causes).axiom_attributed == 0
    causes[-1]["issue_url"] = "https://github.com/TheAxiomFoundation/rulespec-us/issues/1"
    assert assess_unexplained(_report(1), known_causes=causes).axiom_attributed == 1
    report = _report(2, 1)
    report["summary"]["dispositioned"]["counts"]["axiom_encoding_gap"] = 1
    report["mismatches"] = [{"disposition": {"disposition": kind, "linked_issue": causes[-1]["issue_url"]}} for kind in ("axiom_encoding_gap", "upstream_engine_gap")]
    assert assess_unexplained(report).axiom_attributed == 2


def test_file_validation_requires_safe_valid_suite_bound_artifact(tmp_path):
    """Bad/missing/foreign files fail closed; suite aliases admit valid evidence."""
    document = {"schema": "axiom_oracles.dispositions.v1", "suite": "alias", "entries": [{
        "id": "one", "concept": "sample#c", "case_id": "case", "disposition": "upstream_engine_gap",
        "evidence": {"mechanism": "A pinned oracle defect", "upstream_url": "https://example.org/issue/1"},
        "expires_on_source_change": False,
    }]}
    path = tmp_path / "dispositions.yaml"
    path.write_text(yaml.safe_dump(document))
    for filename in ("/absolute.yaml", "../outside.yaml", "missing.yaml", "dispositions.yaml"):
        actual = assess_unexplained(_report(10, 9, 1, filename), repo_root=tmp_path)
        assert actual.count == 10
        assert actual.defects
    actual = assess_unexplained(_report(10, 9, 1, "dispositions.yaml"), repo_root=tmp_path, suite={"suite": "sample", "aliases": ["alias"]})
    assert actual.count == 1
    assert actual.defects == ()
    path.write_text("suite: sample\nentries: []\n")
    assert assess_unexplained(_report(10, 9, 1, path.name), repo_root=tmp_path).count == 10
    # A bad file cannot erase a larger declared unexplained signal either.
    assert assess_unexplained(_report(10, 9, 5000, path.name), repo_root=tmp_path).count == 5000


@given(st.lists(st.integers(min_value=0, max_value=10000), min_size=1, max_size=12))
def test_duplicate_resolution_is_order_independent_maximum(counts):
    """Every suite gates its largest assessment, independent of report order."""
    reports = [{**_report(count), "_file": f"report-{i}.json"} for i, count in enumerate(counts)]
    left = resolve_suite_reports(reports)["sample"]
    right = resolve_suite_reports(reversed(reports))["sample"]
    assert left == right
    # _report lists one row, which floors each report's mismatch total.
    assert assess_unexplained(left).count == max(max(count, 1) for count in counts)


def test_assessment_is_frozen_and_overrides_scope_the_view():
    actual = assess_unexplained(_report(100, 0, 100), summary={"mismatch_count": 1}, rows=[{}])
    assert actual.count == 1
    with pytest.raises(FrozenInstanceError):
        actual.count = 0


def _script(name):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"unexplained_test_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_committed_gated_report_has_one_consumer_count(monkeypatch):
    """Exhaustively compare consumer counts; isolate unrelated execution-evidence checks.

    Certificate counting still reads each real report and validates its real
    dispositions file. Execution and NZ producer replay are covered by their
    own integration gates; replacing those here keeps this accounting census
    fast enough to run for every gated report, rather than a sample.
    """
    from axiom_oracles.conformance.scoreboard import _disposition_signals

    ratchet = _script("unexplained_ratchet")
    certify = _script("certify")
    monkeypatch.setattr(certify, "validate_suite_evidence", lambda path: SimpleNamespace(
        defects=(), reconciliation="full", valid=True, binding="bound", chunk_case_count=1,
        report_sha256=None, suite=None, case_count=1,
    ))
    monkeypatch.setattr(certify, "_rederived_nz_report", lambda: json.loads((ROOT / "dashboard/public/data/nz-treasury-incomeexplorer.json").read_text()))
    causes = load_known_causes()
    reports = ratchet.gated_reports()
    for suite, report in reports.items():
        expected = assess_unexplained(report, known_causes=causes).count
        assert _disposition_signals(report)[0] == expected, suite
        assert ratchet.count_unexplained(report, causes) == expected, suite
        # The generic certificate leg accepts the same dashboard contract.
        path = report.get("_file")
        if path:
            report_path = ROOT / "dashboard/public/data" / path
        else:
            report_path = next(path for path in sorted((ROOT / "dashboard/public/data").glob("*.json"))
                               if json.loads(path.read_text()).get("suite") == suite)
        leg, _, _ = certify._suite_verdict({"suite": suite, "oracle_type": "reference", "oracle": "committed count census", "report": report_path.relative_to(ROOT).as_posix()})
        assert leg["unexplained"] == expected, suite
