"""Auxiliary outputs are bound evidence without changing legacy populations."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.dispositions import (
    apply_dispositions,
    assignment_digest,
    load_dispositions,
    selected_rows_sha256,
    selection_binding,
)
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.comparison.selectors import (
    ArithmeticEvaluationError,
    evaluate_expression,
    expression_variables,
    match_row,
    mismatch_signature,
    row_variables,
    validate_match,
)
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult

ROOT = Path(__file__).resolve().parents[1]
CONCEPT = "us:test#income_tax"
ROW = {
    "case_id": "a", "concept": CONCEPT, "kind": "amount_difference",
    "left": 100, "right": 50, "difference": 50,
    "aux": {"left": {"niit": 60, "addmed": 5}, "right": {"niit": 10, "addmed": None}},
}


def test_requested_raw_aux_outputs_reach_each_mismatch_row():
    mapping = ProgramMapping(
        standard=CONCEPT, description="Tax", category="tax", comparison="amount",
        targets={"policyengine": "income_tax", "taxsim": "fiitax"},
    )
    left = [EngineResult("policyengine", "a", {"income_tax": 100, "niit": 99}, raw={"niit": 60})]
    right = [EngineResult("taxsim", "a", {"fiitax": 50, "niit": 10})]
    comparator = Comparator([mapping])
    case = Case(case_id="a", period="2024", outputs=(CONCEPT,))

    def report(outputs):
        return build_comparison_report(
            suite_name="aux", population="taxsim-csv", locales={"us"}, scope=None,
            cases=[case], mappings=[mapping],
            comparisons=comparator.compare(left, right, row_aux_outputs=outputs),
        )

    row = report(["niit", "addmed"])["mismatches"][0]
    assert row["aux"] == {
        "left": {"niit": 60, "addmed": None},
        "right": {"niit": 10, "addmed": None},
    }
    assert "aux" not in report([])["mismatches"][0]


@pytest.mark.parametrize("selector", [
    {"left_aux.niit": {"min": 59}, "right_aux.niit": {"max": 11}},
    {"left_aux": {"niit": {"values": [60]}}, "right_aux": {"niit": {"min": 10}}},
])
def test_aux_match_bounds(selector):
    assert validate_match(selector) == []
    assert match_row(selector, ROW)
    assert not match_row(selector, {key: value for key, value in ROW.items() if key != "aux"})
    changed = copy.deepcopy(ROW)
    changed["aux"]["left"]["niit"] = 20
    assert not match_row(selector, changed)


@pytest.mark.parametrize("selector", [
    {"left_aux": {}}, {"left_aux.niit": {}}, {"left_aux.niit": {"tolerance": 1}},
    {"right_aux.niit.bad": {"min": 0}}, {"left_aux": {"niit.bad": {"min": 0}}},
])
def test_aux_match_rejects_vacuous_or_invalid_bounds(selector):
    assert validate_match(selector)


def test_aux_row_arithmetic_and_missing_values():
    expression = "left_aux.niit - right_aux.niit - difference"
    assert expression_variables(expression) == {"left_aux.niit", "right_aux.niit", "difference"}
    assert evaluate_expression(expression, row_variables(ROW)) == 0
    with pytest.raises(ArithmeticEvaluationError, match="missing or not numeric"):
        evaluate_expression("right_aux.addmed", row_variables(ROW))


@pytest.mark.parametrize("expression", [
    "left_aux.niit.real", "left_aux.niit()", 'left_aux["niit"]', "other.niit", "left_aux",
])
def test_aux_arithmetic_cannot_execute_python(expression):
    with pytest.raises(ArithmeticEvaluationError):
        expression_variables(expression)


@pytest.mark.parametrize("signature", [False, True])
@pytest.mark.parametrize("stamped", [False, True])
def test_population_binding_changes_when_aux_changes(signature, stamped):
    before = copy.deepcopy(ROW)
    if stamped:
        before["signature"] = "a" * 64
    after = copy.deepcopy(before)
    after["aux"]["left"]["niit"] += 1
    assert selection_binding([before], signature=signature) != selection_binding([after], signature=signature)


BASELINE = json.loads((ROOT / "docs/taxsim-disposition-migration-baseline.json").read_text())


@pytest.mark.parametrize("baseline", BASELINE["reports"], ids=lambda item: item["path"])
def test_every_existing_taxsim_report_preserves_digests_without_aux(baseline):
    report = json.loads((ROOT / baseline["path"]).read_text())
    rows = report.get("mismatches") or []
    assert all("aux" not in row for row in rows)
    # Pin both legacy population encodings, independently of their production
    # implementations, as well as the PR3 audited row-assignment digests.
    canonical = sorted([
        str(row.get("case_id")), str(row.get("concept")),
        json.dumps(row.get("left"), sort_keys=True),
        json.dumps(row.get("right"), sort_keys=True),
        json.dumps(row.get("difference"), sort_keys=True),
    ] for row in rows)
    assert selected_rows_sha256(rows) == hashlib.sha256(
        json.dumps(canonical, separators=(",", ":")).encode()
    ).hexdigest()
    for row in rows:
        error = row.get("error") or {}
        old_identity = {
            "concept": row.get("concept"), "kind": row.get("kind"),
            "delta": row.get("difference"), "facts": dict(row.get("facts") or {}),
            "error_signature": error.get("signature"),
        }
        assert mismatch_signature(row) == hashlib.sha256(json.dumps(
            old_identity, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
    if len(rows) == report["summary"]["mismatch_count"]:
        path = baseline.get("dispositions_file")
        document = load_dispositions(ROOT / path, repo_root=ROOT) if path else None
        report = apply_dispositions(report, document)
    assert assignment_digest(report) == baseline["after_assignment_digest"]
