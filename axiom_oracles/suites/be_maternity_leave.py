from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


MATERNITY_MODULE = "be:regulations/health_insurance/maternity/indemnity_rates"
BRUSSELS_REGION = 1
DAILY_WORKING_DAY_DENOMINATOR = 12 * 26
FIRST_30_WORKING_DAYS = 30
AFTER_30_WORKING_DAYS = 60
DAILY_REMUNERATION_CAP_BE_2025 = 183.13


def be_maternity_leave_cases() -> list[Case]:
    """Belgium maternity worker cases for EUROMOD BE_2025 bmact_s."""

    return [
        _maternity_leave_case("be-maternity-leave-mother-30k", 30_000.0),
        _maternity_leave_case("be-maternity-leave-mother-45k", 45_000.0),
        _maternity_leave_case(
            "be-maternity-leave-mother-60k-capped",
            60_000.0,
            apply_daily_cap=True,
        ),
    ]


def _maternity_leave_case(
    case_id: str,
    annual_income: float,
    *,
    apply_daily_cap: bool = False,
) -> Case:
    uncapped_daily_input = _maternity_input(
        "belgium_maternity_uncapped_lost_daily_remuneration"
    )
    capped_daily_input = _maternity_input(
        "belgium_maternity_lost_daily_remuneration_after_article_113_cap"
    )
    daily_income = annual_income / DAILY_WORKING_DAY_DENOMINATOR
    bridge_inputs = [uncapped_daily_input]
    if not apply_daily_cap:
        bridge_inputs.append(capped_daily_input)
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": (
                "maternity-leave-employed-capped"
                if apply_daily_cap
                else "maternity-leave-employed-under-cap"
            ),
            "yearly_earned_income": annual_income,
            "newborn_child_birth_month": 1,
            "euromod_switches": [("PBE", True)],
            "axiom_inputs": {
                _maternity_input(
                    "belgium_maternity_article_216_uncapped_worker_first_30_days_applies"
                ): True,
                uncapped_daily_input: daily_income,
                capped_daily_input: (
                    DAILY_REMUNERATION_CAP_BE_2025
                    if apply_daily_cap
                    else daily_income
                ),
                _maternity_input("belgium_maternity_first_30_working_days_count"): (
                    FIRST_30_WORKING_DAYS
                ),
                _maternity_input("belgium_maternity_after_30_working_days_count"): (
                    AFTER_30_WORKING_DAYS
                ),
            },
            "euromod_inputs": _maternity_euromod_inputs(annual_income),
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {
                    "inputs": bridge_inputs,
                    "divide_by": DAILY_WORKING_DAY_DENOMINATOR,
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
            Entity(
                entity_id="partner",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                },
            ),
            Entity(
                entity_id="child",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 0,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            ),
        ),
        outputs=(Concepts.BE_MATERNITY_REST_PERIOD_AMOUNT,),
    )


def _maternity_euromod_inputs(
    annual_income: float,
) -> list[dict[str, float | int]]:
    mother_id = 101
    father_id = 102
    child_id = 103
    monthly_income = annual_income / 12
    return [
        _euromod_person_row(
            mother_id,
            age=35,
            region=BRUSSELS_REGION,
            gender=0,
            partner_id=father_id,
            marital_status=2,
            employment_income=monthly_income,
        ),
        _euromod_person_row(
            father_id,
            age=35,
            region=BRUSSELS_REGION,
            gender=1,
            partner_id=mother_id,
            marital_status=2,
        ),
        _euromod_person_row(
            child_id,
            age=0,
            region=BRUSSELS_REGION,
            gender=1,
            mother_id=mother_id,
            father_id=father_id,
            birth_month=1,
        ),
    ]


def _euromod_person_row(
    person_id: int,
    *,
    age: int,
    region: int,
    gender: int,
    partner_id: int = 0,
    mother_id: int = 0,
    father_id: int = 0,
    marital_status: int = 1,
    employment_income: float = 0,
    birth_month: int = 0,
) -> dict[str, float | int]:
    employed = employment_income > 0
    return {
        "idperson": person_id,
        "idpartner": partner_id,
        "idmother": mother_id,
        "idfather": father_id,
        "byr": 0,
        "dag": age,
        "dgn": gender,
        "dmb": birth_month,
        "dms": marital_status,
        "drgn1": region,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwptmy": 0,
        "liwwh": 0,
        "liwwh21_h": 18 if employed else 0,
        "liwwh33_h": 24 if employed else 0,
        "liwwh42_h": 5 if employed else 0,
        "loc": 5,
        "yem": employment_income,
        "yemmy": 12 if employed else 0,
        "yse": 0,
        "ysemy": 0,
        "bun": 0,
        "poa": 0,
    }


def _maternity_input(name: str) -> str:
    return f"{MATERNITY_MODULE}#input.{name}"
