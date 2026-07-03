from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA


PREMIUM_MODULE = "be-vlg:regulations/social_security/flemish_social_protection/premium"


def be_flemish_social_protection_premium_cases() -> list[Case]:
    """Belgium Flemish Social Protection premium cases for EUROMOD BE_2025."""

    return [
        Case(
            case_id="be-flemish-social-protection-premium-ordinary-adult",
            period="2025",
            metadata={
                **BE_METADATA,
                "scenario": "flemish-adult-ordinary-premium",
                "yearly_earned_income": 60_000.0,
                "axiom_inputs": _ordinary_adult_axiom_inputs(),
                "euromod_inputs": [_euromod_flemish_high_income_adult_input()],
            },
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 35,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 60_000.0,
                    },
                ),
            ),
            outputs=(Concepts.BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM,),
        )
    ]


def _ordinary_adult_axiom_inputs() -> dict[str, float | int | bool]:
    return {
        _premium_input("flanders_social_protection_premium_year"): 2025,
        _premium_input("flanders_social_protection_age_years"): 35,
        _premium_input("flanders_social_protection_is_subject_to_premium"): True,
        _premium_input(
            "flanders_social_protection_is_administratively_affiliated_without_premium"
        ): False,
        _premium_input(
            "flanders_social_protection_has_increased_health_insurance_reimbursement_on_previous_january_1"
        ): False,
    }


def _euromod_flemish_high_income_adult_input() -> dict[str, float | int]:
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "drgn1": 2,
        "les": 3,
        "lfs": 15,
        "lhw": 38,
        "liwmy": 12,
        "liwwh": 120,
        "loc": 5,
        "yem": 5_000,
        "yemmy": 12,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _premium_input(name: str) -> str:
    return f"{PREMIUM_MODULE}#input.{name}"
