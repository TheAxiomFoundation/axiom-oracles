"""Reviewer counterexamples must remain unbound through the real scoreboard."""

from copy import deepcopy
from dataclasses import replace

import pytest

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.dispositions import apply_dispositions
from axiom_oracles.comparison.mappings import ProgramMapping, load_program_mappings
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance.attestation import EXECUTION_ATTESTATION_SCHEMA, attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


ORACLE = OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine")


def _sum_mapping():
    # The committed mapping used by review-368-r10/.review-368-probes.py.
    return next(
        mapping for mapping in load_program_mappings()
        if mapping.target_for_engine("policyengine")
        == ["income_tax_main_rates", "capital_gains_tax"]
    )


def _report(mapping, values, *, oracle_on_left=False, paired_components=False):
    if paired_components:
        # Positive component controls compare every member separately; merely
        # returning both sides of a summed mapping cannot certify a member.
        mappings = [replace(
            mapping, standard=f"{mapping.concept_id}:component:{target}",
            targets={"axiom": target, "policyengine": target},
        ) for target in mapping.target_for_engine("policyengine")]
    else:
        mappings = [mapping]
    axiom_values = {}
    for compared_mapping in mappings:
        targets = compared_mapping.target_for_engine("axiom")
        axiom_values.update(
            {target: 0 for target in targets}
            if isinstance(targets, list) else {targets: 0}
        )
    axiom = EngineResult("axiom", "c1", axiom_values)
    oracle = EngineResult("policyengine", "c1", values)
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report = build_comparison_report(
        suite_name="probe", population="synthetic", locales=set(), scope=None,
        cases=[Case(case_id="c1", period="2026")],
        mappings=mappings, comparisons=Comparator(mappings).compare([left], [right]),
    )
    if report["summary"]["mismatch_count"]:
        report = apply_dispositions(report, {
            "schema": "axiom_oracles.dispositions.v1", "suite": "probe",
            "entries": [{
                "id": "missing-oracle-output", "concept": mapping.concept_id,
                "case_id": "c1", "disposition": "upstream_engine_gap",
                "evidence": {
                    "mechanism": "The oracle omitted a configured returned output.",
                    "sources": ["tests/test_observed_output_regressions.py"],
                },
                "expires_on_source_change": True,
            }],
        })
    return report


def _score(report, output="capital_gains_tax"):
    universe = Universe("us-pe", ORACLE, [UniversePolicy(
        id=f"us-pe:{output}", oracle_policy_name=output,
        output_vars=(output,), in_scope=True, suite="probe",
    )])
    return score_jurisdiction(universe, [report])


@pytest.mark.parametrize("strip_values", [False, True])
def test_review_grid_declaration_cannot_attest_a_null_or_unrecorded_output(strip_values):
    """The same explicit declaration never upgrades NULL or no rows to coverage."""
    mapping = _sum_mapping()
    report = _report(mapping, {
        "income_tax_main_rates": 0, "capital_gains_tax": None,
    })
    assert report["mismatches"][0]["right"] is None
    assert report["aggregates"][0]["missing_right_count"] == 1
    report.pop("attestation")
    targets = mapping.target_for_engine("axiom")
    report["engines"] = {
        "axiom": ",".join(targets) if isinstance(targets, list) else targets,
        "policyengine": "income_tax_main_rates,capital_gains_tax",
    }
    if strip_values:
        report["cases"] = []
        report["mismatches"] = []
        report["aggregates"] = []
    assert report["summary"]["comparison_count"] == 1
    assert report["summary"]["dispositioned"]["unexplained_count"] == 0

    evidence = attest(report, oracle=ORACLE)
    board, rows = _score(report)
    assert not evidence.binds(("capital_gains_tax",))
    assert board.covered == 0
    assert not board.conformant
    assert not rows[0].covered


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_review_scalar_stamp_cannot_override_recorded_missing_output(oracle_on_left):
    """A positive scalar claim must agree with that case's returned oracle value."""
    mapping = ProgramMapping(
        standard="us:probe#capital_gains_tax", description="scalar output",
        category="tax", comparison="amount",
        targets={"axiom": "tax", "policyengine": "capital_gains_tax"},
    )
    report = _report(mapping, {"capital_gains_tax": None}, oracle_on_left=oracle_on_left)
    oracle_side = "left" if oracle_on_left else "right"
    assert report["mismatches"][0][oracle_side] is None
    assert report["aggregates"][0][f"missing_{oracle_side}_count"] == 1
    # The legitimate producer already declines to stamp this missing value.
    assert all(row["engine"] != "policyengine" for row in report["attestation"]["outputs"])
    assert _score(report)[0].covered == 0
    claimed = deepcopy(report)
    claimed["attestation"]["outputs"].append({
        "concept": mapping.concept_id, "engine": "policyengine",
        "variable": "capital_gains_tax", "comparisons": 1,
    })

    evidence = attest(claimed, oracle=ORACLE)
    board, rows = _score(claimed)
    assert not evidence.binds(("capital_gains_tax",))
    assert board.covered == 0
    assert not board.conformant
    assert not rows[0].covered


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_review_sum_stamp_cannot_invent_a_missing_component(oracle_on_left):
    mapping = _sum_mapping()
    report = _report(mapping, {
        "income_tax_main_rates": 0, "capital_gains_tax": None,
    }, oracle_on_left=oracle_on_left)
    report["attestation"]["outputs"].append({
        "concept": mapping.concept_id, "engine": "policyengine",
        "variable": "capital_gains_tax", "comparisons": 1,
    })
    assert not attest(report, oracle=ORACLE).binds(("capital_gains_tax",))
    assert _score(report)[0].covered == 0


@pytest.mark.parametrize("oracle_on_left", [False, True])
@pytest.mark.parametrize("value", [0, False])
def test_real_zero_and_false_oracle_members_do_not_invent_axiom_members(oracle_on_left, value):
    mapping = _sum_mapping()
    report = _report(mapping, {
        "income_tax_main_rates": 0, "capital_gains_tax": value,
    }, oracle_on_left=oracle_on_left)
    evidence = attest(report, oracle=ORACLE)
    assert not evidence.binds(("income_tax_main_rates",))
    assert not evidence.binds(("capital_gains_tax",))
    assert any(row["engine"] == "policyengine" and row["variable"] == "capital_gains_tax"
               for row in report["attestation"]["outputs"])
    board, rows = _score(report)
    assert board.covered == 0
    assert not board.conformant
    assert not rows[0].covered


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_returned_oracle_sum_member_cannot_cover_without_its_axiom_member(oracle_on_left):
    mapping = _sum_mapping()
    report = _report(mapping, {
        "income_tax_main_rates": 0, "capital_gains_tax": None,
    }, oracle_on_left=oracle_on_left)
    evidence = attest(report, oracle=ORACLE)
    assert not evidence.binds(("income_tax_main_rates",))
    assert not evidence.binds(("capital_gains_tax",))
    assert _score(report, "income_tax_main_rates")[0].covered == 0
    assert _score(report, "capital_gains_tax")[0].covered == 0


@pytest.mark.parametrize("contradiction", ["missing", "error", "skipped"])
def test_same_case_output_contradiction_cannot_hide_under_another_concept(contradiction):
    """One output's missing/error evidence applies across its concept aliases."""
    output = "capital_gains_tax"
    conflict = {
        "case_id": "c1", "engine": "policyengine", "concept": "concept-b",
        "variable": output, "value": 0,
    }
    if contradiction == "missing":
        conflict.update(value=None, missing=True)
    elif contradiction == "error":
        conflict["error"] = "oracle output failed"
    else:
        conflict["skipped"] = True
    report = {
        "suite": "probe", "case_count": 1,
        "engines": {"left": "axiom", "right": "policyengine"},
        "summary": {
            "comparison_count": 2, "match_count": 2, "mismatch_count": 0,
            "error_count": 0,
        },
        "aggregates": [
            {"concept": "concept-a", "comparison_count": 1},
            {"concept": "concept-b", "comparison_count": 1},
        ],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA, "executed": True,
            "case_count": 1, "comparison_count": 2, "error_count": 0,
            "outputs": [{
                "concept": "concept-a", "engine": "policyengine",
                "variable": output, "comparisons": 1,
            }],
        },
        "observed_outputs": [{
            "case_id": "c1", "engine": "policyengine", "concept": "concept-a",
            "variable": output, "value": 0,
        }, {"case_id": "c1", "engine": "axiom", "concept": "concept-a",
            "variable": output, "value": 0}, conflict],
    }
    evidence = attest(report, oracle=ORACLE)
    board, rows = _score(report)
    assert not evidence.binds((output,))
    assert board.covered == 0
    assert not rows[0].covered


@pytest.mark.parametrize("location", ["top-level", "case-row"])
@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_explicit_missing_sum_member_overrides_its_positive_stamp(location, oracle_on_left):
    """A targeted NULL is decisive even when its enclosing concept is a sum."""
    mapping = _sum_mapping()
    report = _report(mapping, {
        "income_tax_main_rates": 0, "capital_gains_tax": 0,
    }, oracle_on_left=oracle_on_left, paired_components=True)
    assert _score(report)[0].covered == 1
    side = "left" if oracle_on_left else "right"
    report["aggregates"][0][f"missing_{side}_count"] = 1
    missing = {
        "case_id": "c1", "concept": mapping.concept_id,
        "variable": "capital_gains_tax", side: None,
    }
    if location == "top-level":
        report["mismatches"].append(missing)
    else:
        report["cases"][0]["mismatches"].append(missing)
    evidence = attest(report, oracle=ORACLE)
    board, rows = _score(report)
    assert not evidence.binds(("capital_gains_tax",))
    assert board.covered == 0
    assert not rows[0].covered


@pytest.mark.parametrize("location", ["ledger", "top-level", "case-row", "case-match"])
@pytest.mark.parametrize("concept_label", ["absent", "null"])
@pytest.mark.parametrize("contradiction", ["missing", "error", "skipped"])
@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_case_output_contradiction_does_not_require_a_concept_label(
    location, concept_label, contradiction, oracle_on_left,
):
    """A missing label cannot erase evidence identifying the case and output."""
    mapping = _sum_mapping()
    report = _report(mapping, {
        "income_tax_main_rates": 0, "capital_gains_tax": 0,
    }, oracle_on_left=oracle_on_left, paired_components=True)
    assert _score(report)[0].covered == 1
    value = None if contradiction == "missing" else 0
    conflict = {"case_id": "c1", "variable": "capital_gains_tax"}
    if concept_label == "null":
        conflict["concept"] = None
    if contradiction == "error":
        conflict["error"] = "oracle output failed"
    elif contradiction == "skipped":
        conflict["skipped"] = True
    if location == "ledger":
        conflict.update(engine="policyengine", value=value)
        report["observed_outputs"].append(conflict)
    else:
        conflict["left" if oracle_on_left else "right"] = value
        if location == "top-level":
            report["mismatches"].append(conflict)
        else:
            key = "matches" if location == "case-match" else "mismatches"
            report["cases"][0][key].append(conflict)
    evidence = attest(report, oracle=ORACLE)
    board, rows = _score(report)
    assert not evidence.binds(("capital_gains_tax",))
    assert board.covered == 0
    assert not rows[0].covered
