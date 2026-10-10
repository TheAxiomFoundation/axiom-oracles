"""Execution evidence and approved waiver debt hold for varying report counts."""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    OracleTargetResolver,
    attest,
)
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.conformance.waivers import AttestationWaiver, WaiverIndex


PROPERTY_SETTINGS = settings(max_examples=30, deadline=None, derandomize=True)
ORACLE = OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine")


def _report(*, suite="probe", total=1, aggregate=1, claim=1, variable="registered_tax"):
    engines = {"left": "axiom", "right": "policyengine"}
    return {
        "suite": suite,
        "engines": engines,
        "case_count": total,
        "summary": {
            "comparison_count": total,
            "match_count": total,
            "mismatch_count": 0,
            "error_count": 0,
        },
        "aggregates": [{"concept": "actual_tax", "comparison_count": aggregate}],
        "output_bindings": {"actual_tax": {"axiom": "axiom_tax", "policyengine": variable}},
        "observed_outputs": [{
            "case_id": index, "concept": "actual_tax", "engine": "policyengine",
            "variable": variable, "value": 0,
        } for index in range(total)] + [{
            "case_id": index, "concept": "actual_tax", "engine": "axiom",
            "variable": "axiom_tax", "value": 0,
        } for index in range(total)],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": True,
            "case_count": total,
            "comparison_count": total,
            "error_count": 0,
            "engines": engines,
            "outputs": [{
                "concept": "actual_tax",
                "engine": "policyengine",
                "variable": variable,
                "comparisons": claim,
            }],
        },
    }


def _universe(*, policy_id="tx:policy", suite="probe"):
    return Universe(
        jurisdiction="tx",
        oracle=ORACLE,
        policies=[UniversePolicy(
            id=policy_id,
            oracle_policy_name=policy_id,
            output_vars=("registered_tax",),
            in_scope=True,
            suite=suite,
        )],
    )


@PROPERTY_SETTINGS
@given(
    total=st.integers(min_value=1, max_value=100),
    aggregate=st.integers(min_value=0, max_value=120),
    claim=st.one_of(st.integers(min_value=-5, max_value=125), st.booleans()),
)
@example(total=10, aggregate=1, claim=2)
@example(total=1, aggregate=10, claim=2)
@example(total=10, aggregate=10, claim=0)
@example(total=10, aggregate=10, claim=True)
@example(total=10, aggregate=10, claim=1)
def test_output_claim_is_positive_and_bounded_by_its_aggregate_and_report(
    total, aggregate, claim,
):
    """Coverage rejects any output count its own positive body evidence cannot support."""
    report = _report(total=total, aggregate=aggregate, claim=claim)
    resolver = OracleTargetResolver()
    evidence = attest(report, oracle=ORACLE, resolver=resolver)
    board, rows = score_jurisdiction(_universe(), [report], resolver=resolver)
    supported = (
        isinstance(claim, int) and not isinstance(claim, bool)
        and 0 < claim <= min(total, aggregate)
    )
    assert evidence.eligible is supported
    assert board.covered == int(supported)
    assert board.conformant is supported
    assert rows[0].covered is supported
    if not supported:
        assert rows[0].status == "unattested"


@PROPERTY_SETTINGS
@given(
    suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12),
    count=st.integers(min_value=1, max_value=100),
    reason=st.sampled_from(("compared_surface_differs", "oracle_variable_not_recorded")),
)
def test_new_waiver_debt_cannot_cover_a_fresh_stamped_unbound_report(
    suffix, count, reason,
):
    """A direct waiver index grants no new policy or suite migration privileges."""
    policy_id = f"tx:new-{suffix}"
    suite = f"new-suite-{suffix}"
    report = _report(
        suite=suite, total=count, aggregate=count, claim=count, variable="other_tax"
    )
    resolver = OracleTargetResolver()
    evidence = attest(report, oracle=ORACLE, resolver=resolver)
    assert evidence.eligible
    assert evidence.binding_gap(("registered_tax",)) == "compared_surface_differs"

    waivers = WaiverIndex([AttestationWaiver("tx", policy_id, suite, reason)])
    board, rows = score_jurisdiction(
        _universe(policy_id=policy_id, suite=suite), [report],
        waivers=waivers, resolver=resolver,
    )
    assert board.covered == 0
    assert not board.conformant
    assert rows[0].status == "unbound"
    assert board.covered_with_waived_output_attestation == 0
