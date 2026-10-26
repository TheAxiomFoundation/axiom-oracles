"""Max's d1081 ruling keeps unbound final outputs in scope and uncovered."""

from dataclasses import replace
from functools import cache
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    OracleTargetResolver,
)
from axiom_oracles.conformance.loader import parse as parse_universe
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
RETRACTIONS = (
    ("be", "be:tintb_be", "tintasp_s", "be-marital-quotient"),
    ("us-pe", "us-pe:snap", "snap", "ca-snap-ecps"),
    ("us-pe", "us-pe:ks_tanf", "ks_tanf", "ks-tanf-ecps"),
    ("us-pe", "us-pe:nc_income_tax", "nc_income_tax", "nc-income-tax-liability"),
    ("us-pe", "us-pe:savers_credit", "savers_credit", "us-savers-grid"),
)
PARAMETERS = pytest.mark.parametrize(
    "jurisdiction,policy_id,missing_output,former_suite", RETRACTIONS,
    ids=[row[1] for row in RETRACTIONS],
)


@cache
def _registered_policy(jurisdiction, policy_id):
    universe = parse_universe(ROOT / "conformance" / f"{jurisdiction}.yaml")
    return universe, next(policy for policy in universe.policies if policy.id == policy_id)


@PARAMETERS
def test_missing_final_output_retracts_the_registration_without_excluding_the_policy(
    jurisdiction, policy_id, missing_output, former_suite,
):
    """Retracting evidence must preserve the policy boundary and name its repair."""
    _, policy = _registered_policy(jurisdiction, policy_id)
    assert policy.in_scope is True
    assert policy.exclusion_reason is None
    assert missing_output in policy.output_vars
    assert policy.suite is None, former_suite
    assert policy.note and "\n" not in policy.note
    assert missing_output in policy.note
    assert "comparison" in policy.note.lower()
    assert "same-case" in policy.note.lower()


@PARAMETERS
def test_public_detail_preserves_the_missing_final_output_as_an_uncovered_policy(
    jurisdiction, policy_id, missing_output, former_suite,
):
    """Canonical and served detail must publish the same honest coverage gap."""
    canonical = ROOT / "conformance/detail" / f"{jurisdiction}.json"
    served = ROOT / "dashboard/public/data" / f"conformance_detail_{jurisdiction}.json"
    for path in (canonical, served):
        document = json.loads(path.read_text())
        row = next(row for row in document["policies"] if row["id"] == policy_id)
        assert row["in_scope"] is True
        assert row["exclusion_reason"] is None
        assert row["suite"] is None, former_suite
        assert row["status"] == "uncovered"
        assert row["covered"] is False
        assert row["output_attestation"] is None
        assert row["attested_outputs"] == []
        assert missing_output in row["note"]
    assert canonical.read_bytes() == served.read_bytes()


@settings(max_examples=50, deadline=None, derandomize=True)
@given(
    retraction=st.sampled_from(RETRACTIONS),
    comparisons=st.integers(min_value=1, max_value=100),
    registered_comparison=st.booleans(),
    stamped_execution=st.booleans(),
    register_rerun=st.booleans(),
)
def test_coverage_restores_only_with_a_registered_stamped_output_comparison(
    retraction, comparisons, registered_comparison, stamped_execution, register_rerun,
):
    """Neither a diagnostic comparison nor a successful stamp restores final coverage."""
    jurisdiction, policy_id, missing_output, former_suite = retraction
    universe, policy = _registered_policy(jurisdiction, policy_id)
    assert policy.suite is None
    policy = replace(policy, suite=former_suite if register_rerun else None)
    engines = {"left": "axiom", "right": universe.oracle.backend}
    report = {
        "suite": former_suite,
        "engines": engines,
        "case_count": comparisons,
        "summary": {
            "comparison_count": comparisons,
            "match_count": comparisons,
            "mismatch_count": 0,
            "error_count": 0,
        },
        "aggregates": [{"concept": "restoring-comparison", "comparison_count": comparisons}],
        "observed_outputs": [
            {"case_id": f"case-{index}", "concept": "restoring-comparison",
             "engine": universe.oracle.backend,
             "variable": missing_output if registered_comparison else "diagnostic_only",
             "value": 0}
            for index in range(comparisons)
        ],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": stamped_execution,
            "case_count": comparisons,
            "comparison_count": comparisons,
            "error_count": 0,
            "engines": engines,
            "outputs": [{
                "concept": "restoring-comparison",
                "engine": universe.oracle.backend,
                "variable": missing_output if registered_comparison else "diagnostic_only",
                "comparisons": comparisons,
            }],
        },
    }
    report["observed_outputs"] += [
        dict(row, engine="axiom") for row in report["observed_outputs"]
    ]
    board, rows = score_jurisdiction(
        replace(universe, policies=[policy]), [report], resolver=OracleTargetResolver(),
    )
    expected = register_rerun and stamped_execution and registered_comparison
    assert board.policies_in_scope == 1
    assert board.covered == int(expected)
    assert rows[0].covered is expected
    assert board.covered_with_waived_output_attestation == 0
    assert rows[0].attested_outputs == ([missing_output] if expected else [])
