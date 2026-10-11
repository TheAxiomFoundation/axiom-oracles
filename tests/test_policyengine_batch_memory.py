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
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        results = PolicyEngineRunner(batch_size=batch_size).run_cases(
            cases, ["income_tax"]
        )
        survivors_after_run = sum(ref() is not None for ref in batch_garbage)
    finally:
        if was_enabled:
            gc.enable()

    batches = -(-len(cases) // batch_size)
    assert [result.household_id for result in results] == [
        case.case_id for case in cases
    ]
    assert survivors_at_batch_start == [0] * batches
    assert survivors_after_run == 0


def test_compare_collects_each_comparison_batch(monkeypatch, tmp_path) -> None:
    """`compare` disables automatic collection, so it must collect per batch."""
    import importlib

    from click.testing import CliRunner

    from axiom_oracles.core.case import Case as CoreCase

    cli_module = importlib.import_module("axiom_oracles.cli")
    from tests.test_comparison_completeness import MAPPING, result

    cases = [
        CoreCase(case_id=index, period="2026", outputs=("test:amount",))
        for index in range(1, 5)
    ]
    monkeypatch.setattr(cli_module, "_load_population_cases", lambda **kwargs: cases)
    monkeypatch.setattr(
        cli_module, "_echo_resolved_axiom_composition", lambda *args: None
    )
    monkeypatch.setattr(
        cli_module, "comparable_mappings", lambda *args, **kwargs: [MAPPING]
    )
    monkeypatch.setattr(
        cli_module, "_prepare_cases_for_engines", lambda batch, *args, **kwargs: batch
    )
    survivors_at_batch_start: list[int] = []
    batch_garbage: list[weakref.ref] = []

    class Runner:
        def __init__(self, engine):
            self.engine = engine

        def run_cases(self, batch, variables):
            if self.engine == "axiom":
                survivors_at_batch_start.append(
                    sum(ref() is not None for ref in batch_garbage)
                )
            batch_garbage.append(weakref.ref(_Cyclic()))
            return [result(self.engine, case.case_id, {"amount": 10}) for case in batch]

    monkeypatch.setattr(
        cli_module, "_build_runner", lambda engine, *args, **kwargs: Runner(engine)
    )
    run = CliRunner().invoke(
        cli_module.cli,
        [
            "compare",
            "axiom",
            "policyengine",
            "--comparison-batch-size",
            "1",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    assert run.exit_code == 0, run.output
    assert survivors_at_batch_start == [0, 0, 0, 0]


def test_failed_batch_is_bisected_after_its_garbage_is_collected(monkeypatch) -> None:
    """A failing batch splits in half; each retry starts with the failed
    attempt's cyclic garbage already freed, and results keep case order."""
    attempts: list[tuple[int, int]] = []
    batch_garbage: list[weakref.ref] = []

    def fake_once(self, cases, variables):
        attempts.append((len(cases), sum(ref() is not None for ref in batch_garbage)))
        batch_garbage.append(weakref.ref(_Cyclic()))
        if len(cases) > 1:
            raise ValueError("one bad case")
        raise ValueError("still bad")

    def fake_single(self, case, variables):
        return EngineResult("policyengine", case.case_id, {"income_tax": 1})

    monkeypatch.setattr(PolicyEngineRunner, "_run_case_batch_once", fake_once)
    monkeypatch.setattr(PolicyEngineRunner, "run_case", fake_single)
    cases = [Case(case_id=f"case-{index}", period="2026") for index in range(4)]

    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        results = PolicyEngineRunner(batch_size=4).run_cases(cases, ["income_tax"])
    finally:
        if was_enabled:
            gc.enable()

    assert [result.household_id for result in results] == [
        case.case_id for case in cases
    ]
    assert [size for size, _ in attempts] == [4, 2, 1, 1, 2, 1, 1]
    assert all(survivors == 0 for _, survivors in attempts)
