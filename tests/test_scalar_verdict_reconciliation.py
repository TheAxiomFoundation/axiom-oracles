"""Retained scalar verdicts must agree with their values and residual counts.

A report retains each scalar comparison's verdict by where it puts the row:
``matches`` or ``mismatches``. The consumer recomputes that verdict from the
row's returned values with the report's authoritative comparison kind and
tolerances (its ``concepts`` declaration), and refuses the case when they
disagree. The retained mismatch and match counts must account for every
retained comparison. Every artifact the Comparator produces still passes.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance import observations
from axiom_oracles.conformance.observations import OutputEvidence, observed_output_value
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult

ROOT = Path(__file__).parents[1]
CONCEPT = "us:test/program#benefit"


def _mapping(comparison="amount", tolerance=0, relative_tolerance=0, concept=CONCEPT):
    return ProgramMapping(
        standard=concept,
        description="Benefit",
        category="benefits",
        comparison=comparison,
        tolerance=tolerance,
        relative_tolerance=relative_tolerance,
        targets={"axiom": "axiom_benefit", "policyengine": "pe_benefit"},
    )


def _report(mapping, pairs, *, include_inputs=True):
    """A Comparator report, JSON round-tripped as a consumer reads it."""
    left = [
        EngineResult("axiom", case_id, {} if a is None else {"axiom_benefit": a})
        for case_id, (a, _) in pairs.items()
    ]
    right = [
        EngineResult("policyengine", case_id, {} if p is None else {"pe_benefit": p})
        for case_id, (_, p) in pairs.items()
    ]
    comparisons = Comparator([mapping]).compare(left, right)
    report = build_comparison_report(
        suite_name="verdict-probe",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=[Case(case_id=case_id, period="2026") for case_id in pairs],
        mappings=[mapping],
        comparisons=comparisons,
        include_inputs=include_inputs,
    )
    return json.loads(json.dumps(report))


def _observed(report, case_id, engine="policyengine", output="pe_benefit"):
    rows = [
        row for row in report["observed_outputs"]
        if row["case_id"] == case_id and row["engine"] == engine
        and row["variable"] == output
    ]
    assert rows, "the producer returned this output"
    value = rows[0]["value"]
    # A string is an observation only for an output registered as one.
    return observed_output_value(
        report, case_id=case_id, engine=engine, concept=CONCEPT, output=output,
        value=value, targets=(output,),
        declared_type=str if isinstance(value, str) else None,
    )


def _forge_match(report, case_id, *, recount=True):
    """Move one retained mismatch into matches, as the issue's artifact does."""
    case = next(case for case in report["cases"] if case["case_id"] == case_id)
    row = case["mismatches"].pop(0)
    case.setdefault("matches", []).append(row)
    report["mismatches"] = [
        item for item in report["mismatches"] if item["case_id"] != case_id
    ]
    if recount:
        report["summary"]["mismatch_count"] -= 1
        report["summary"]["match_count"] += 1
    return report


def _forge_mismatch(report, case_id, *, recount=True):
    case = next(case for case in report["cases"] if case["case_id"] == case_id)
    row = case["matches"].pop(0)
    case["mismatches"].append(row)
    if recount:
        report["summary"]["mismatch_count"] += 1
        report["summary"]["match_count"] -= 1
    return report


# --- the issue's artifact ---------------------------------------------------


def test_issue_artifact_match_with_unreconciled_residual_is_refused():
    report = _report(_mapping(), {"c1": (100, 0)})
    assert _observed(report, "c1")
    forged = _forge_match(copy.deepcopy(report), "c1")
    retained = forged["cases"][0]["matches"][0]
    assert (retained["left"], retained["right"], retained["difference"]) == (100, 0, 100)
    assert forged["summary"]["mismatch_count"] == 0
    assert not _observed(forged, "c1")
    assert not _observed(forged, "c1", engine="axiom", output="axiom_benefit")


def test_forged_match_is_refused_even_without_a_concept_declaration():
    """Without an authoritative kind, only equal values can retain a match."""
    report = _forge_match(_report(_mapping(), {"c1": (100, 0)}), "c1")
    report.pop("concepts")
    assert not _observed(report, "c1")


def test_forged_match_cannot_borrow_a_wider_row_tolerance():
    report = _forge_match(_report(_mapping(tolerance=5), {"c1": (100, 0)}), "c1")
    report["cases"][0]["matches"][0]["tolerance"] = 1000
    assert not _observed(report, "c1")


def test_retained_mismatch_must_be_counted():
    report = _report(_mapping(), {"c1": (100, 0), "c2": (5, 5)})
    assert _observed(report, "c2")
    report["summary"]["mismatch_count"] = 0
    report["summary"]["match_count"] = 2
    # The undercount leaves the whole report unable to account for its rows.
    assert not _observed(report, "c1")
    assert not _observed(report, "c2")


def test_retained_match_must_be_counted():
    report = _report(_mapping(), {"c1": (5, 5), "c2": (7, 7)})
    report["summary"]["match_count"] = 1
    report["summary"]["mismatch_count"] = 1
    assert not _observed(report, "c1")


def test_misrecorded_residual_is_refused():
    report = _report(_mapping(), {"c1": (100, 0)})
    report["cases"][0]["mismatches"][0]["difference"] = 5
    assert not _observed(report, "c1")


def test_forged_eligibility_match_is_refused():
    report = _report(_mapping("eligibility"), {"c1": (True, False)})
    assert _observed(report, "c1")
    assert not _observed(_forge_match(report, "c1"), "c1")


def test_forged_mismatch_of_agreeing_values_is_refused():
    report = _report(_mapping(tolerance=5), {"c1": (100, 98)})
    assert _observed(report, "c1")
    assert not _observed(_forge_mismatch(report, "c1"), "c1")


def test_one_comparison_retained_with_both_verdicts_is_refused():
    """A case match and a top-level mismatch for one comparison contradict.

    Each row is consistent with its own values and the counts cover both.
    Both rows agree on the Axiom value, so for that side only the shared
    identity reveals the contradiction (the oracle side also disagrees on
    its value).
    """
    report = _report(_mapping(), {"c1": (5, 5), "c2": (1, 1)})
    axiom = {"engine": "axiom", "output": "axiom_benefit"}
    assert _observed(report, "c1", **axiom)
    report["mismatches"].append({
        "case_id": "c1", "concept": CONCEPT, "kind": "amount_difference",
        "left": 5, "right": 9, "difference": -4, "tolerance": 0,
    })
    report["summary"]["mismatch_count"] += 1
    assert not _observed(report, "c1", **axiom)
    assert not _observed(report, "c1")
    assert _observed(report, "c2", **axiom)


def _fiit_marked(report, marker):
    if marker == "suite":
        report["suite"] = "fiit-ecps"
    elif marker == "output-summary":
        report["output_summary"] = [{"surface": "employee-medicare", "output": "x"}]
    else:
        report["provenance"] = {"generated_by": "scripts/run_comparison.py::fiit-ecps"}
    return report


@pytest.mark.parametrize("marker", ["suite", "output-summary", "provenance"])
def test_fiit_marker_does_not_exempt_a_forged_match(marker):
    """Marking a report as FIIT exempts nothing but FIIT's own mismatch rows."""
    forged = _forge_match(_report(_mapping(), {"c1": (100, 0)}), "c1")
    _fiit_marked(forged, marker)
    assert not _observed(forged, "c1")


@pytest.mark.parametrize("marker", ["suite", "output-summary", "provenance"])
def test_fiit_marker_does_not_exempt_an_uncounted_mismatch(marker):
    report = _fiit_marked(_report(_mapping(), {"c1": (100, 0), "c2": (5, 5)}), marker)
    report["summary"]["mismatch_count"] = 0
    assert not _observed(report, "c2")


@pytest.mark.parametrize("left, right, matches", [
    ("12.5", 12.5, True), ("12.5", "13", False), (True, 1, True), ("0.5", 0, False),
])
def test_amount_values_are_compared_as_the_comparator_converts_them(left, right, matches):
    report = _report(_mapping(), {"c1": (left, right)})
    retained = report["cases"][0]["matches" if matches else "mismatches"]
    assert retained and retained[0]["left"] == left
    assert _observed(report, "c1")
    assert not _observed(
        _forge_mismatch(report, "c1") if matches else _forge_match(report, "c1"), "c1"
    )


@pytest.mark.parametrize("comparison", ["coverage", "value", "judgment"])
def test_other_comparison_kinds_compare_truthiness_as_the_comparator_does(comparison):
    report = _report(_mapping(comparison), {"same": (2, 1), "differ": ("0", 0)})
    assert report["cases"][0]["matches"] and report["cases"][1]["mismatches"]
    assert _observed(report, "same")
    assert _observed(report, "differ")
    assert not _observed(_forge_mismatch(report, "same"), "same")


# --- valid controls ---------------------------------------------------------


@pytest.mark.parametrize("include_inputs", [True, False])
def test_valid_amount_reports_still_observe(include_inputs):
    report = _report(
        _mapping(tolerance=5, relative_tolerance=0.01),
        {"within-abs": (100, 96), "within-rel": (10_000, 10_090), "outside": (100, 0),
         "zero": (0, 0)},
        include_inputs=include_inputs,
    )
    for case_id in ("within-abs", "within-rel", "outside", "zero"):
        assert _observed(report, case_id), case_id


@pytest.mark.parametrize("include_inputs", [True, False])
def test_valid_eligibility_reports_still_observe(include_inputs):
    report = _report(
        _mapping("eligibility"),
        {"both": (True, True), "neither": (False, False), "left": (True, False),
         "numeric": (1, True)},
        include_inputs=include_inputs,
    )
    for case_id in ("both", "neither", "left", "numeric"):
        assert _observed(report, case_id), case_id


def test_compacted_successful_report_still_observes():
    """A compact report drops successful rows; its counts still reconcile."""
    report = _report(_mapping(), {f"c{i}": (i, i) for i in range(5)}, include_inputs=False)
    assert all("matches" not in case for case in report["cases"])
    assert report["summary"]["match_count"] == 5
    assert all(_observed(report, f"c{i}") for i in range(5))


def test_missing_side_stays_a_retained_mismatch():
    report = _report(_mapping(), {"c1": (None, 5), "c2": (3, 3)})
    case = report["cases"][0]
    assert case["mismatches"][0]["kind"] == "missing_left"
    assert _observed(report, "c1")
    assert _observed(report, "c2")


# --- properties -------------------------------------------------------------

AMOUNTS = st.one_of(
    st.integers(-1_000, 1_000),
    st.floats(-1_000, 1_000, allow_nan=False, allow_infinity=False),
)
# The Comparator converts amount values with float(), so numeric strings and
# bools compare as numbers.
AMOUNT_VALUES = st.one_of(AMOUNTS, AMOUNTS.map(repr), st.booleans())
# Every other kind compares truthiness of whatever the engines returned. The
# report's aggregates convert every value with float(), so only numeric
# strings reach a report; "0" is truthy.
OTHER_VALUES = st.one_of(
    st.booleans(), st.integers(-2, 2), st.sampled_from(("0", "1", "2.5", "-1")),
    st.floats(-2, 2, allow_nan=False, allow_infinity=False),
)
KINDS = st.sampled_from(("amount", "eligibility", "coverage", "value", "judgment"))
TOLERANCES = st.sampled_from((0, 0.5, 1, 5))
RELATIVE = st.sampled_from((0, 0.001, 0.01))


@st.composite
def _comparator_reports(draw):
    comparison = draw(KINDS)
    values = AMOUNT_VALUES if comparison == "amount" else OTHER_VALUES
    mapping = _mapping(comparison, draw(TOLERANCES), draw(RELATIVE))
    count = draw(st.integers(1, 5))
    pairs = {}
    for index in range(count):
        left = draw(values)
        # Near-equal pairs exercise the tolerance edge.
        right = draw(st.one_of(values, st.just(left)))
        pairs[f"c{index}"] = (left, right)
    return mapping, pairs, draw(st.booleans())


PROPERTY = settings(
    max_examples=60, deadline=None, derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)


@PROPERTY
@given(generated=_comparator_reports())
@example(generated=(_mapping(tolerance=5), {"c0": (100, 105)}, True))
@example(generated=(_mapping(relative_tolerance=0.01), {"c0": (100, 101)}, True))
def test_property_every_comparator_report_still_observes(generated):
    """Differential: the consumer's verdict equals the Comparator's on its own output."""
    mapping, pairs, include_inputs = generated
    report = _report(mapping, pairs, include_inputs=include_inputs)
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", k, {"axiom_benefit": a}) for k, (a, _) in pairs.items()],
        [EngineResult("policyengine", k, {"pe_benefit": p}) for k, (_, p) in pairs.items()],
    )
    concept = report["concepts"][0]
    for item in comparisons:
        returned = item.comparisons[0]
        assert observations.scalar_verdict(
            concept, returned.left_value, returned.right_value
        ) is returned.matches
    for case_id in pairs:
        assert _observed(report, case_id)
        assert _observed(report, case_id, engine="axiom", output="axiom_benefit")


@PROPERTY
@given(
    generated=_comparator_reports(),
    pick=st.integers(0, 4),
    recount=st.booleans(),
    drop_concepts=st.booleans(),
)
def test_property_disagreeing_retained_verdict_always_fails(
    generated, pick, recount, drop_concepts
):
    """Flip any retained verdict, with or without fixing the counts: refused."""
    mapping, pairs, _ = generated
    report = _report(mapping, pairs, include_inputs=True)
    case_id = list(pairs)[pick % len(pairs)]
    case = next(case for case in report["cases"] if case["case_id"] == case_id)
    if case["mismatches"]:
        _forge_match(report, case_id, recount=recount)
    else:
        _forge_mismatch(report, case_id, recount=recount)
    left, right = pairs[case_id]
    forged_mismatch = bool(case["mismatches"])
    if drop_concepts and not (forged_mismatch and recount and left != right):
        # Without an authority, values that differ within the tolerance can
        # carry either verdict; only the counts can refuse that forgery.
        report.pop("concepts")
    assert not _observed(report, case_id)


# --- the repository's committed reports -------------------------------------


def _committed_reports():
    names = subprocess.run(
        ["git", "ls-files", "-z", "--", "reports/*.json", "dashboard/public/data/*.json",
         "comparisons/*.json"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode().split("\0")
    for name in names:
        if not name:
            continue
        try:
            report = json.loads((ROOT / name).read_text())
        except (OSError, ValueError):
            continue
        if isinstance(report, dict) and isinstance(report.get("cases"), list):
            yield name, report


def test_committed_reports_retain_no_contradicted_scalar_verdict():
    """Differential over the repository's reports: the new check refuses none."""
    checked = 0
    for name, report in _committed_reports():
        evidence = OutputEvidence(report)
        assert evidence.scalar_verdicts_reconciled, name
        assert not evidence.contradicted_scalar_comparisons, (
            name, sorted(evidence.contradicted_scalar_comparisons, key=repr)[:5],
        )
        checked += 1
    assert checked > 50
