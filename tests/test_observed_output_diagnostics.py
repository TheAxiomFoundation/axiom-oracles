"""Queried diagnostic components are not values returned by a comparison."""

import pytest

from axiom_oracles.conformance.attestation import OracleTargetResolver, attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.observations import observed_output_value
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction


CONCEPT = "us:policies/income_tax/savers_credit_pipeline#federal_savers_credit"
ACTUAL = "savers_credit_potential"
DIAGNOSTIC = "savers_credit"
ORACLE = OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine")


def _report(*, claim_diagnostic, bind_actual=True):
    """Mirror the real Saver's Credit grid's compared and diagnostic fields."""
    outputs = [{
        "concept": CONCEPT, "engine": "policyengine", "variable": ACTUAL,
        "comparisons": 1,
    }]
    if claim_diagnostic:
        outputs.append({
            "concept": CONCEPT, "engine": "policyengine", "variable": DIAGNOSTIC,
            "comparisons": 1,
        })
    report = {
        "suite": "probe", "case_count": 1,
        "engines": {"left": "axiom", "right": "policyengine"},
        "summary": {"comparison_count": 1, "match_count": 1, "mismatch_count": 0},
        "aggregates": [{"concept": CONCEPT, "comparison_count": 1}],
        "output_bindings": {CONCEPT: {"policyengine": ACTUAL}},
        "cases": [{
            "case_id": "single-one-below-50-percent-limit", "concept": CONCEPT,
            "axiom": 1000.0, "policyengine": 1000.0,
            "policyengine_components": {
                ACTUAL: 1000.0,
                DIAGNOSTIC: 814.9000244140625,
                "savers_credit_credit_limit": 814.9000244140625,
            },
        }],
        "attestation": {"executed": True, "outputs": outputs},
    }
    if not bind_actual:
        report.pop("output_bindings")
    return report


@pytest.mark.parametrize("claim_diagnostic", [False, True])
@pytest.mark.parametrize("bind_actual", [False, True])
def test_grid_diagnostic_cannot_cover_final_output_even_with_positive_stamp(claim_diagnostic, bind_actual):
    report = _report(claim_diagnostic=claim_diagnostic, bind_actual=bind_actual)
    evidence = attest(report, oracle=ORACLE, resolver=OracleTargetResolver())
    assert not observed_output_value(
        report, case_id=report["cases"][0]["case_id"], engine="policyengine",
        concept=CONCEPT, output=DIAGNOSTIC, value=814.9000244140625,
        targets=(ACTUAL,),
    )
    assert not evidence.binds((DIAGNOSTIC,))
    assert evidence.binds((ACTUAL,)) is bind_actual

    universe = Universe("us-pe", ORACLE, [UniversePolicy(
        id=f"us-pe:{output}", oracle_policy_name=output,
        output_vars=(output,), in_scope=True, suite="probe",
    ) for output in (ACTUAL, DIAGNOSTIC)])
    board, scores = score_jurisdiction(universe, [report], resolver=OracleTargetResolver())
    assert not scores[1].covered
    assert not board.conformant
    # A genuine compared output remains covered when the stamp itself is valid.
    assert scores[0].covered is (bind_actual and not claim_diagnostic)
    assert board.covered == int(bind_actual and not claim_diagnostic)


@pytest.mark.parametrize("include_actual_stamp", [False, True])
def test_equal_zero_diagnostic_cannot_become_a_compared_output_by_its_stamp(include_actual_stamp):
    report = _report(claim_diagnostic=True, bind_actual=False)
    case = report["cases"][0]
    case["axiom"] = case["policyengine"] = 0
    case["policyengine_components"] = {ACTUAL: 0, DIAGNOSTIC: 0}
    if not include_actual_stamp:
        report["attestation"]["outputs"] = [report["attestation"]["outputs"][1]]
    evidence = attest(report, oracle=ORACLE, resolver=OracleTargetResolver())
    assert not evidence.binds((DIAGNOSTIC,))
    universe = Universe("us-pe", ORACLE, [UniversePolicy(
        id=f"us-pe:{DIAGNOSTIC}", oracle_policy_name=DIAGNOSTIC,
        output_vars=(DIAGNOSTIC,), in_scope=True, suite="probe",
    )])
    board, scores = score_jurisdiction(universe, [report], resolver=OracleTargetResolver())
    assert board.covered == 0
    assert not scores[0].covered


def test_registered_comparison_target_retains_the_real_grid_output():
    report = _report(claim_diagnostic=False, bind_actual=False)
    resolver = OracleTargetResolver({CONCEPT: {"policyengine": frozenset({ACTUAL})}})
    evidence = attest(report, oracle=ORACLE, resolver=resolver)
    assert evidence.eligible
    assert evidence.binds((ACTUAL,))
    assert not evidence.binds((DIAGNOSTIC,))
    universe = Universe("us-pe", ORACLE, [UniversePolicy(
        id=f"us-pe:{ACTUAL}", oracle_policy_name=ACTUAL,
        output_vars=(ACTUAL,), in_scope=True, suite="probe",
    )])
    board, scores = score_jurisdiction(universe, [report], resolver=resolver)
    assert board.covered == 1
    assert scores[0].covered
