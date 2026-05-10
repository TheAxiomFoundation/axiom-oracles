from __future__ import annotations

from collections.abc import Iterable

from ..core.case import Case, Concepts, Entity
from .nyc_basic import NYC_FACTS, NYC_METADATA


def nyc_synthetic_cases() -> list[Case]:
    """Synthetic NYC households for ACCESS NYC / PolicyEngine mismatch triage."""

    cases: list[Case] = []
    scenarios = [
        _Scenario("single-adult", (40,), (0, 10_000, 20_000, 30_000, 40_000, 60_000)),
        _Scenario("senior", (65,), (0, 15_000, 25_000, 35_000, 50_000)),
        _Scenario(
            "single-parent-infant",
            (30, 0),
            (0, 15_000, 30_000, 45_000, 70_000, 100_000),
        ),
        _Scenario(
            "single-parent-toddler",
            (30, 2),
            (0, 15_000, 30_000, 40_000, 55_000, 80_000),
        ),
        _Scenario(
            "single-parent-child",
            (30, 5),
            (0, 15_000, 30_000, 40_000, 55_000, 80_000),
        ),
        _Scenario(
            "single-parent-teen",
            (30, 17),
            (0, 20_000, 40_000, 55_000, 80_000, 120_000),
        ),
        _Scenario(
            "pregnant-adult",
            (30,),
            (0, 15_000, 25_000, 40_000, 60_000),
            pregnant_head=True,
        ),
    ]

    for scenario in scenarios:
        for income in scenario.incomes:
            cases.append(_case_for_scenario(scenario, income))
    return cases


class _Scenario:
    def __init__(
        self,
        name: str,
        ages: tuple[int, ...],
        incomes: Iterable[int],
        *,
        pregnant_head: bool = False,
    ):
        self.name = name
        self.ages = ages
        self.incomes = tuple(incomes)
        self.pregnant_head = pregnant_head


def _case_for_scenario(scenario: _Scenario, income: int) -> Case:
    entities = []
    for index, age in enumerate(scenario.ages):
        is_head = index == 0
        facts = {
            Concepts.PERSON_AGE: age,
            Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold" if is_head else "Child",
        }
        if is_head:
            facts[Concepts.YEARLY_EARNED_INCOME] = income
            if scenario.pregnant_head:
                facts[Concepts.PREGNANT] = True
        entities.append(
            Entity(
                entity_id="head" if is_head else f"child-{index}",
                kind="person",
                facts=facts,
            )
        )

    case_id = f"nyc-{scenario.name}-{income // 1000}k"
    return Case(
        case_id=case_id,
        period="2026-05",
        metadata={
            **NYC_METADATA,
            "suite": "nyc-synthetic",
            "scenario": scenario.name,
            "yearly_earned_income": income,
            "ages": list(scenario.ages),
            "pregnant_head": scenario.pregnant_head,
        },
        facts={**NYC_FACTS, Concepts.CASH_ON_HAND: 500},
        entities=tuple(entities),
    )
