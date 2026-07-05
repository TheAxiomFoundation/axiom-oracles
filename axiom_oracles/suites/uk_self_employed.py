from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .uk_worker import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    UK_METADATA,
    UK_WORKER_PERIOD,
)


SELF_EMPLOYED_MODULE = (
    "uk:statutes/social_security/workers/pilot_worker_self_employed_nic_pipeline"
)
EMPLOYER_MODULE = (
    "uk:statutes/social_security/workers/pilot_worker_employer_secondary_nic_pipeline"
)

# 2026-27 secondary threshold (£5,000 a year), set by Treasury order under
# SSCBA 1992 s.5; the employer pipeline takes it as a supplied input, so the
# oracle case provides it rather than the module hard-coding an ungrounded
# literal. UKMOD applies the weekly-rounded equivalent (£96/week).
UK_SECONDARY_THRESHOLD_ANNUAL = 5_000.0

# Same single-earner gross grid as the employee suites so the three UK NIC
# comparisons share a grid: 30k/45k exercise the Class 4 main band and the
# employer band; 60k+ exercise the Class 4 additional band above the 50,270
# upper profits limit; all exercise the employer secondary charge above 5,000.
_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("30k", 30_000.0),
    ("45k", 45_000.0),
    ("60k", 60_000.0),
    ("130k", 130_000.0),
    ("360k", 360_000.0),
)


def uk_self_employed_nic_cases() -> list[Case]:
    """Single-earner UK self-employed NIC (Class 4) cases for UKMOD UK_2026."""

    return [
        _single_self_employed_case(f"uk-self-employed-nic-{label}", profits)
        for label, profits in _INCOME_GRID
    ]


def uk_employer_secondary_nic_cases() -> list[Case]:
    """Single-employment UK employer secondary Class 1 cases for UKMOD UK_2026."""

    return [
        _single_employer_case(f"uk-employer-nic-{label}", earnings)
        for label, earnings in _INCOME_GRID
    ]


def _single_self_employed_case(case_id: str, annual_profits: float) -> Case:
    profits_input = _se_input("uk_nic_pilot_se_annual_profits")
    return Case(
        case_id=case_id,
        period=UK_WORKER_PERIOD,
        metadata={
            **UK_METADATA,
            "scenario": "single-self-employed-nic",
            "yearly_self_employment_income": annual_profits,
            "axiom_inputs": {profits_input: annual_profits},
            "euromod_inputs": [_euromod_self_employed_input(annual_profits)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yse": [profits_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.SELF_EMPLOYMENT_INCOME: annual_profits,
                },
            ),
        ),
        outputs=(Concepts.UK_WORKER_SELF_EMPLOYED_NIC,),
    )


def _single_employer_case(case_id: str, annual_earnings: float) -> Case:
    earnings_input = _er_input("uk_nic_pilot_er_annual_employment_income")
    threshold_input = _er_input("uk_nic_pilot_er_secondary_threshold")
    return Case(
        case_id=case_id,
        period=UK_WORKER_PERIOD,
        metadata={
            **UK_METADATA,
            "scenario": "single-employer-secondary-nic",
            "yearly_earned_income": annual_earnings,
            "axiom_inputs": {
                earnings_input: annual_earnings,
                threshold_input: UK_SECONDARY_THRESHOLD_ANNUAL,
            },
            "euromod_inputs": [_euromod_employee_input(annual_earnings)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [earnings_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_earnings,
                },
            ),
        ),
        outputs=(Concepts.UK_WORKER_EMPLOYER_SECONDARY_NIC,),
    )


def _se_input(name: str) -> str:
    return f"{SELF_EMPLOYED_MODULE}#input.{name}"


def _er_input(name: str) -> str:
    return f"{EMPLOYER_MODULE}#input.{name}"


def _euromod_self_employed_input(annual_profits: float) -> dict[str, float | int]:
    trading = annual_profits > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "les": 5 if trading else 0,
        "lfs": 15 if trading else 0,
        "lhw": 38 if trading else 0,
        "liwmy": 12 if trading else 0,
        "liwwh": 120 if trading else 0,
        "yse": annual_profits / 12,
        "ysemy": 12 if trading else 0,
    }


def _euromod_employee_input(annual_earnings: float) -> dict[str, float | int]:
    employed = annual_earnings > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "yem": annual_earnings / 12,
        "yemmy": 12 if employed else 0,
    }
