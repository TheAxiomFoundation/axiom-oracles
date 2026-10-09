"""Retired bootstrap waiver metadata cannot be reintroduced."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.waivers import (
    BOOTSTRAP_WAIVERS,
    AttestationWaiver,
    parse,
    serialize,
)

BOOTSTRAP_ROWS = [
    AttestationWaiver(jurisdiction, policy_id, approved[0], approved[1])
    for (jurisdiction, policy_id), approved in sorted(BOOTSTRAP_WAIVERS.items())
]


@pytest.mark.parametrize(
    "waiver",
    BOOTSTRAP_ROWS,
    ids=[policy_id for (_, policy_id) in sorted(BOOTSTRAP_WAIVERS)],
)
def test_deleted_bootstrap_waivers_cannot_return(tmp_path, waiver):
    """Every previously approved row was removed from the committed file."""
    committed = Path(__file__).parents[1] / "conformance/attestation_waivers.yaml"
    assert parse(committed).keys() == set()
    path = tmp_path / "attestation_waivers.yaml"
    path.write_text(serialize([waiver]))
    problem = None
    try:
        parse(path)
    except ValueError as exc:
        problem = str(exc)
    assert problem is not None, f"retired bootstrap waiver returned: {waiver.policy_id}"
    assert "retired" in problem


@pytest.mark.parametrize("present", [False, True], ids=["absent", "empty"])
def test_empty_waiver_state_remains_valid(tmp_path, present):
    path = tmp_path / "attestation_waivers.yaml"
    if present:
        path.write_text(serialize([]))
    index = parse(path)
    assert index.keys() == set()
    assert len(index) == 0


@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(indices=set())
@example(indices={0})
@given(indices=st.sets(st.integers(min_value=0, max_value=len(BOOTSTRAP_ROWS) - 1)))
def test_bootstrap_subsets_obey_current_empty_approval_floor(tmp_path, indices):
    """The independent predicate accepts exactly the empty subset."""
    path = tmp_path / "attestation_waivers.yaml"
    path.write_text(serialize([BOOTSTRAP_ROWS[index] for index in indices]))
    accepted = True
    try:
        parse(path)
    except ValueError:
        accepted = False
    assert accepted == (len(indices) == 0)
