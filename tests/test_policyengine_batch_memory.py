"""A PolicyEngine batch's objects are reclaimed before the next batch starts."""

from __future__ import annotations

import gc
import weakref

import pytest

from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


class _Cyclic:
    """Stands in for a batch Simulation: reachable only through a cycle."""

    def __init__(self) -> None:
        self.me = self


@pytest.mark.parametrize("batch_size", [1, 2, 4, 6, 50])
def test_each_batch_is_collected_before_the_next_starts(
    monkeypatch, batch_size: int
) -> None:
    survivors_at_batch_start: list[int] = []
    batch_garbage: list[weakref.ref] = []

    def fake_batch(self, cases, variables):
        survivors_at_batch_start.append(sum(ref() is not None for ref in batch_garbage))
        batch_garbage.append(weakref.ref(_Cyclic()))
        return [
            EngineResult("policyengine", case.case_id, {"income_tax": 0})
            for case in cases
        ]

    monkeypatch.setattr(PolicyEngineRunner, "_run_case_batch", fake_batch)
    cases = [Case(case_id=f"case-{index}", period="2026") for index in range(6)]

    # With automatic collection off, only an explicit full collection can free
    # a cycle, so the test cannot pass by a threshold happening to trip.
    gc.collect()
    gc.disable()
    try:
        results = PolicyEngineRunner(batch_size=batch_size).run_cases(
            cases, ["income_tax"]
        )
        survivors_after_run = sum(ref() is not None for ref in batch_garbage)
    finally:
        gc.enable()

    batches = -(-len(cases) // batch_size)
    assert [result.household_id for result in results] == [
        case.case_id for case in cases
    ]
    assert survivors_at_batch_start == [0] * batches
    assert survivors_after_run == 0
