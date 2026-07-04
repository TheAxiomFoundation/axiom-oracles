from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


SELF_EMPLOYED_MODULE = "be:regulations/social_security/self_employed/contributions"
EUROMOD_2025_SELF_EMPLOYED_ARTICLE_14_INDEX_FACTOR = 73447.52 / 15831.12


def be_self_employed_ssc_cases() -> list[Case]:
    """Belgium self-employed social-contribution cases for EUROMOD BE_2025."""

    return [
        _main_activity_case("be-self-employed-ssc-main-5k", 5_000.0),
        _main_activity_case("be-self-employed-ssc-30k", 30_000.0),
        _main_activity_case("be-self-employed-ssc-main-60k", 60_000.0),
        _main_activity_case("be-self-employed-ssc-main-120k", 120_000.0),
        _secondary_activity_case(
            "be-self-employed-ssc-secondary-1k", self_employment_income=1_000.0
        ),
        _secondary_activity_case(
            "be-self-employed-ssc-secondary-10k",
            self_employment_income=10_000.0,
        ),
        _post_pension_case("be-self-employed-ssc-post-pension-10k", 10_000.0),
    ]


def _main_activity_case(case_id: str, annual_income: float) -> Case:
    return _self_employed_case(
        case_id,
        annual_income,
        scenario="single-main-activity-self-employed-ssc",
    )


def _secondary_activity_case(
    case_id: str,
    *,
    self_employment_income: float,
    employment_income: float = 12_000.0,
) -> Case:
    return _self_employed_case(
        case_id,
        self_employment_income,
        scenario="secondary-activity-self-employed-ssc",
        axiom_input_overrides={
            _self_employed_input("belgium_self_employed_is_secondary_activity"): True,
        },
        euromod_overrides={"yem": employment_income / 12, "yemmy": 12},
        metadata_extra={"yearly_employment_income": employment_income},
    )


def _post_pension_case(case_id: str, annual_income: float) -> Case:
    return _self_employed_case(
        case_id,
        annual_income,
        scenario="post-pension-self-employed-ssc",
        age=66,
        axiom_input_overrides={
            _self_employed_input("belgium_self_employed_has_reached_pension_age"): True,
            _self_employed_input(
                "belgium_self_employed_receives_retirement_or_survivor_pension"
            ): True,
        },
        euromod_overrides={"dag": 66, "poa": 1_000},
        metadata_extra={"monthly_old_age_pension": 1_000},
    )


def _self_employed_case(
    case_id: str,
    annual_income: float,
    *,
    scenario: str,
    age: int = 35,
    axiom_input_overrides: dict[str, float | bool] | None = None,
    euromod_overrides: dict[str, float | int] | None = None,
    metadata_extra: dict[str, float | int] | None = None,
) -> Case:
    gross_income_input = _self_employed_input(
        "belgium_self_employed_gross_professional_income"
    )
    axiom_inputs = {
        _self_employed_input("belgium_self_employed_article_14_index_factor"): (
            EUROMOD_2025_SELF_EMPLOYED_ARTICLE_14_INDEX_FACTOR
        ),
        gross_income_input: annual_income,
        _self_employed_input("belgium_self_employed_professional_expenses"): 0,
        _self_employed_input("belgium_self_employed_professional_losses"): 0,
        _self_employed_input(
            "belgium_self_employed_prior_activity_income_taxed_current_year"
        ): 0,
        _self_employed_input("belgium_self_employed_article_28_cessation_income"): 0,
        _self_employed_input(
            "belgium_self_employed_article_28_exclusion_condition_met"
        ): False,
        _self_employed_input(
            "belgium_spouse_helper_fiscally_attributed_professional_income"
        ): 0,
        _self_employed_input("belgium_spouse_helper_only_indemnity_sector"): False,
        _self_employed_input(
            "belgium_self_employed_early_retirement_pension_suspended_for_income_ceiling"
        ): False,
        _self_employed_input("belgium_self_employed_is_student"): False,
        _self_employed_input("belgium_self_employed_is_secondary_activity"): False,
        _self_employed_input("belgium_self_employed_has_reached_pension_age"): False,
        _self_employed_input(
            "belgium_self_employed_receives_retirement_or_survivor_pension"
        ): False,
        _self_employed_input("belgium_self_employed_is_spouse_helper"): False,
        _self_employed_input("belgium_self_employed_is_starter_main_activity"): False,
    }
    if axiom_input_overrides:
        axiom_inputs.update(axiom_input_overrides)

    euromod_input = _euromod_self_employed_input(annual_income)
    if euromod_overrides:
        euromod_input.update(euromod_overrides)

    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": scenario,
            "yearly_self_employment_income": annual_income,
            **(metadata_extra or {}),
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [euromod_input],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yse": [gross_income_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: age,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.SELF_EMPLOYMENT_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS,),
    )


def _euromod_self_employed_input(annual_income: float) -> dict[str, float | int]:
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "les": 0,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": 5,
        "yem": 0,
        "yemmy": 0,
        "yse": annual_income / 12,
        "yiy": 0,
        "poa": 0,
    }


def _self_employed_input(name: str) -> str:
    return f"{SELF_EMPLOYED_MODULE}#input.{name}"
