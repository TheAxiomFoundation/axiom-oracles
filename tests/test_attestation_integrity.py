"""An output stamp cannot claim evidence absent from its report body."""

from copy import deepcopy

import pytest

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    OracleTargetResolver,
    attest,
)
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction


def _report():
    return {
        "suite": "probe",
        "engines": {"left": "axiom", "right": "policyengine"},
        "case_count": 2,
        "summary": {"comparison_count": 2, "match_count": 2, "mismatch_count": 0},
        "aggregates": [{"concept": "actual_tax", "comparison_count": 2}],
        "output_bindings": {"actual_tax": {"axiom": "axiom_tax", "policyengine": "snap"}},
        "observed_outputs": [{
            "case_id": index, "concept": "actual_tax", "engine": "policyengine",
            "variable": "snap", "value": 0,
        } for index in range(2)] + [{
            "case_id": index, "concept": "actual_tax", "engine": "axiom",
            "variable": "axiom_tax", "value": 0,
        } for index in range(2)],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": True,
            "case_count": 2,
            "comparison_count": 2,
            "error_count": 0,
            "engines": {"left": "axiom", "right": "policyengine"},
            "outputs": [{
                "concept": "actual_tax",
                "engine": "policyengine",
                "variable": "snap",
                "comparisons": 2,
            }],
        },
    }


def _assert_uncovered(report):
    universe = Universe(
        "us-pe",
        OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine"),
        [UniversePolicy(
            id="us-pe:snap", oracle_policy_name="snap", output_vars=("snap",),
            in_scope=True, suite="probe",
        )],
    )
    evidence = attest(report, oracle=universe.oracle, resolver=OracleTargetResolver())
    board, rows = score_jurisdiction(universe, [report], resolver=OracleTargetResolver())
    assert not evidence.eligible
    assert board.covered == 0
    assert not board.conformant
    assert rows[0].status == "unattested"


@pytest.mark.parametrize("change", [
    {"concept": "uncompared_policy", "comparisons": 5000},
    {"concept": "uncompared_policy"},
    {"comparisons": 5000},
    {"engine": None},
])
def test_output_claim_requires_explicit_engine_and_positive_bounded_body_evidence(change):
    report = _report()
    report["attestation"]["outputs"][0].update(change)
    _assert_uncovered(report)


def test_output_count_is_bounded_by_its_concept_not_only_global_total():
    report = _report()
    report["aggregates"][0]["comparison_count"] = 1
    report["aggregates"].append({"concept": "other_tax", "comparison_count": 1})
    _assert_uncovered(report)


def test_stamp_engine_pair_must_agree_with_the_body():
    report = _report()
    report["attestation"]["engines"]["right"] = "euromod"
    _assert_uncovered(report)


def test_duplicate_output_claims_cannot_multiply_evidence():
    report = _report()
    report["attestation"]["outputs"].append(deepcopy(report["attestation"]["outputs"][0]))
    _assert_uncovered(report)


@pytest.mark.parametrize("execution_claim", [
    {"executed": None},
    {"executed": 0},
    {"executed": "false"},
    {"executed": False},
    {"executed": 1},
], ids=["null", "zero", "string-false", "false", "one"])
def test_stamp_cannot_contradict_recorded_execution(execution_claim):
    report = _report()
    report["attestation"].pop("executed")
    report["attestation"].update(execution_claim)
    evidence = attest(report, oracle="policyengine", resolver=OracleTargetResolver())
    assert not evidence.executed
    _assert_uncovered(report)


def test_stamp_without_execution_field_agrees_with_recorded_same_case_pairs():
    report = _report()
    report["attestation"].pop("executed")
    evidence = attest(report, oracle="policyengine", resolver=OracleTargetResolver())
    assert evidence.executed
    assert evidence.eligible
    assert evidence.binds(("snap",))


def test_unstamped_report_cannot_infer_output_coverage_from_positive_body_counts():
    report = _report()
    report.pop("attestation")
    report["observed_outputs"] = []
    evidence = attest(report, oracle="policyengine", resolver=OracleTargetResolver())
    assert not evidence.stamped
    assert evidence.eligible
    assert not evidence.attested_outputs
    universe = Universe(
        "us-pe", OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine"),
        [UniversePolicy("us-pe:snap", "snap", ("snap",), True, suite="probe")],
    )
    board, rows = score_jurisdiction(universe, [report], resolver=OracleTargetResolver())
    assert board.covered == 0
    assert not rows[0].covered


@pytest.mark.parametrize("count", [1, 2])
def test_observed_output_count_may_be_less_than_the_concept_total(count):
    report = _report()
    report["attestation"]["outputs"][0]["comparisons"] = count
    evidence = attest(report, oracle="policyengine", resolver=OracleTargetResolver())
    assert evidence.eligible
    assert evidence.binds(("snap",))
