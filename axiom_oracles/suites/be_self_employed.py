from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


SELF_EMPLOYED_MODULE = "be:regulations/social_security/self_employed/contributions"
EUROMOD_2025_FIRST_THRESHOLD_INDEX_FACTOR = 2.8844857470602205


def be_self_employed_ssc_cases() -> list[Case]:
    """Belgium self-employed social-contribution cases for EUROMOD BE_2025."""

    return [
        _main_activity_case("be-self-employed-ssc-30k", 30_000.0),
    ]


def _main_activity_case(case_id: str, annual_income: float) -> Case:
    gross_income_input = _self_employed_input(
        "belgium_self_employed_gross_professional_income"
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "single-main-activity-self-employed-ssc",
            "yearly_self_employment_income": annual_income,
            "axiom_inputs": {
                _self_employed_input("belgium_self_employed_article_14_index_factor"): (
                    EUROMOD_2025_FIRST_THRESHOLD_INDEX_FACTOR
                ),
                gross_income_input: annual_income,
                _self_employed_input("belgium_self_employed_professional_expenses"): 0,
                _self_employed_input("belgium_self_employed_professional_losses"): 0,
                _self_employed_input(
                    "belgium_self_employed_prior_activity_income_taxed_current_year"
                ): 0,
                _self_employed_input(
                    "belgium_self_employed_article_28_cessation_income"
                ): 0,
                _self_employed_input(
                    "belgium_self_employed_article_28_exclusion_condition_met"
                ): False,
                _self_employed_input(
                    "belgium_spouse_helper_fiscally_attributed_professional_income"
                ): 0,
                _self_employed_input(
                    "belgium_spouse_helper_only_indemnity_sector"
                ): False,
                _self_employed_input(
                    "belgium_self_employed_early_retirement_pension_suspended_for_income_ceiling"
                ): False,
                _self_employed_input("belgium_self_employed_is_student"): False,
                _self_employed_input(
                    "belgium_self_employed_is_secondary_activity"
                ): False,
                _self_employed_input(
                    "belgium_self_employed_has_reached_pension_age"
                ): False,
                _self_employed_input(
                    "belgium_self_employed_receives_retirement_or_survivor_pension"
                ): False,
                _self_employed_input("belgium_self_employed_is_spouse_helper"): False,
                _self_employed_input(
                    "belgium_self_employed_is_starter_main_activity"
                ): False,
            },
            "euromod_inputs": [_euromod_self_employed_input(annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yse": [gross_income_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
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
