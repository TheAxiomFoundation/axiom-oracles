from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


JOBBONUS_MODULE = "be-vlg:regulations/employment/jobbonus"
GROSS_WAGE_INPUT = "flanders_jobbonus_average_monthly_gross_wage_at_full_time"


def be_flemish_jobbonus_cases() -> list[Case]:
    """Belgium Flemish jobbonus cases for EUROMOD BE_2025."""

    return [
        _jobbonus_case(
            "be-flemish-jobbonus-low-wage-full-time",
            monthly_gross=1_500.0,
            domiciled_in_flanders=True,
            euromod_region=2,
        ),
        _jobbonus_case(
            "be-flemish-jobbonus-threshold-wage-full-time",
            monthly_gross=2_000.0,
            domiciled_in_flanders=True,
            euromod_region=2,
        ),
        _jobbonus_case(
            "be-flemish-jobbonus-upper-band-full-time",
            monthly_gross=2_600.0,
            domiciled_in_flanders=True,
            euromod_region=2,
        ),
        _jobbonus_case(
            "be-flemish-jobbonus-high-wage-full-time",
            monthly_gross=3_200.0,
            domiciled_in_flanders=True,
            euromod_region=2,
        ),
        _jobbonus_case(
            "be-flemish-jobbonus-brussels-resident",
            monthly_gross=1_500.0,
            domiciled_in_flanders=False,
            euromod_region=1,
        ),
    ]


def _jobbonus_case(
    case_id: str,
    *,
    monthly_gross: float,
    domiciled_in_flanders: bool,
    euromod_region: int,
) -> Case:
    annual_income = monthly_gross * 12
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "flemish-jobbonus-full-time-worker",
            "monthly_gross_income": monthly_gross,
            "yearly_earned_income": annual_income,
            "axiom_inputs": _jobbonus_axiom_inputs(
                monthly_gross=monthly_gross,
                domiciled_in_flanders=domiciled_in_flanders,
            ),
            "euromod_inputs": [
                _euromod_jobbonus_input(
                    monthly_gross=monthly_gross,
                    region=euromod_region,
                )
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yemeq_s": {
                    "inputs": [GROSS_WAGE_INPUT],
                    "divide_by": 12,
                },
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.BE_FLEMISH_JOBBONUS,),
    )


def _jobbonus_axiom_inputs(
    *,
    monthly_gross: float,
    domiciled_in_flanders: bool,
) -> dict[str, float | bool]:
    return {
        _jobbonus_input("flanders_jobbonus_is_beneficiary_class"): True,
        _jobbonus_input(
            "flanders_jobbonus_is_domiciled_in_flanders_on_january_1_after_reference_year"
        ): domiciled_in_flanders,
        _jobbonus_input(
            "flanders_jobbonus_is_below_retirement_age_in_worked_quarter"
        ): True,
        GROSS_WAGE_INPUT: monthly_gross,
        _jobbonus_input("flanders_jobbonus_work_fraction"): 1.0,
        _jobbonus_input("flanders_jobbonus_is_full_time_worker"): True,
    }


def _euromod_jobbonus_input(
    *,
    monthly_gross: float,
    region: int,
) -> dict[str, float | int]:
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "drgn1": region,
        "les": 3,
        "lfs": 15,
        "lhw": 38,
        "liwmy": 12,
        "liwwh": 120,
        "loc": 5,
        "yem": monthly_gross,
        "yemmy": 12,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _jobbonus_input(name: str) -> str:
    return name
