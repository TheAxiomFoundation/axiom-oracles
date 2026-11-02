from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA


ELIGIBILITY_MODULE = "be:statutes/social_integration/eligibility"
MINIMUM_AMOUNT_MODULE = "be:statutes/social_integration/minimum_income_amounts"
PAYABLE_AMOUNT_MODULE = "be:statutes/social_integration/payable_amount"
GRAPA_AMOUNTS_MODULE = "be:statutes/income_guarantee_for_elderly/amounts"
GRAPA_RESOURCES_MODULE = "be:statutes/income_guarantee_for_elderly/resources"
GRAPA_PAYABLE_MODULE = "be:statutes/income_guarantee_for_elderly/payable_amount"


def be_social_assistance_cases() -> list[Case]:
    """Belgium social-integration income-support cases for EUROMOD BE_2025."""

    return [
        Case(
            case_id="be-social-assistance-isolated-no-resources",
            period="2025",
            metadata={
                **BE_METADATA,
                "scenario": "isolated-adult-no-resources",
                "axiom_inputs": _isolated_no_resources_axiom_inputs(),
                "euromod_inputs": [_euromod_isolated_no_resources_input()],
            },
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 35,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    },
                ),
            ),
            outputs=(Concepts.BE_SOCIAL_INTEGRATION_INCOME_SUPPORT,),
        ),
        Case(
            case_id="be-social-assistance-single-parent-no-resources",
            period="2025",
            metadata={
                **BE_METADATA,
                "scenario": "single-parent-dependent-child-no-resources",
                "axiom_inputs": _dependent_family_no_resources_axiom_inputs(),
                "euromod_inputs": _euromod_single_parent_no_resources_inputs(),
            },
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 35,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    },
                ),
                Entity(
                    entity_id="child",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 5,
                        Concepts.HOUSEHOLD_RELATION: "Child",
                    },
                ),
            ),
            outputs=(Concepts.BE_SOCIAL_INTEGRATION_INCOME_SUPPORT,),
        ),
    ]


def be_elderly_income_support_cases() -> list[Case]:
    """Belgium elderly income-guarantee cases for EUROMOD BE_2025."""

    return [
        Case(
            case_id="be-elderly-income-support-isolated-no-resources",
            period="2025",
            metadata={
                **BE_METADATA,
                "scenario": "isolated-senior-no-resources",
                "axiom_inputs": _isolated_senior_no_resources_axiom_inputs(),
                "euromod_inputs": [_euromod_isolated_senior_no_resources_input()],
                "euromod_policy_switch_overrides": [("bsaoa_be", True)],
            },
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 70,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    },
                ),
            ),
            outputs=(Concepts.BE_INCOME_GUARANTEE_FOR_ELDERLY,),
        )
    ]


def _isolated_no_resources_axiom_inputs() -> dict[str, float | int | bool]:
    return _no_resources_axiom_inputs(
        has_dependent_family=False,
        is_cohabiting=False,
    )


def _dependent_family_no_resources_axiom_inputs() -> dict[str, float | int | bool]:
    return _no_resources_axiom_inputs(
        has_dependent_family=True,
        is_cohabiting=False,
    )


def _no_resources_axiom_inputs(
    *,
    has_dependent_family: bool,
    is_cohabiting: bool,
) -> dict[str, float | int | bool]:
    return {
        _eligibility_input(
            "belgium_social_integration_habitually_and_permanently_stays_in_belgium"
        ): True,
        _eligibility_input(
            "belgium_social_integration_authorized_to_stay_in_belgium"
        ): True,
        _eligibility_input(
            "belgium_social_integration_minor_emancipated_by_marriage"
        ): False,
        _eligibility_input("belgium_social_integration_minor_has_dependent_child"): False,
        _eligibility_input("belgium_social_integration_minor_is_pregnant"): False,
        _eligibility_input("belgium_social_integration_age_years"): 35,
        _eligibility_input(
            "belgium_social_integration_person_has_belgian_nationality"
        ): True,
        _eligibility_input(
            "belgium_social_integration_eu_citizen_or_family_with_residence_over_three_months"
        ): False,
        _eligibility_input(
            "belgium_social_integration_eu_residence_months_completed"
        ): 0,
        _eligibility_input(
            "belgium_social_integration_registered_foreigner_in_population_register"
        ): False,
        _eligibility_input("belgium_social_integration_stateless_under_1954_convention"): False,
        _eligibility_input("belgium_social_integration_refugee_under_1980_law"): False,
        _eligibility_input(
            "belgium_social_integration_subsidiary_protection_under_1980_law"
        ): False,
        _eligibility_input("belgium_social_integration_has_sufficient_resources"): False,
        _eligibility_input("belgium_social_integration_can_claim_sufficient_resources"): False,
        _eligibility_input(
            "belgium_social_integration_can_procure_sufficient_resources_by_efforts_or_other_means"
        ): False,
        _eligibility_input("belgium_social_integration_disposed_to_work"): True,
        _eligibility_input(
            "belgium_social_integration_health_or_equity_prevents_work"
        ): False,
        _eligibility_input("belgium_social_integration_social_benefit_rights_asserted"): True,
        _eligibility_input(
            "belgium_social_integration_cpas_requires_maintenance_rights_against_listed_debtor"
        ): False,
        _eligibility_input(
            "belgium_social_integration_maintenance_rights_against_listed_debtor_asserted"
        ): False,
        _minimum_amount_input("has_dependent_family"): has_dependent_family,
        _minimum_amount_input("is_cohabiting"): is_cohabiting,
        _minimum_amount_input("belgium_social_integration_current_index_factor"): (
            2.3894545454545455
        ),
        _minimum_amount_input(
            "belgium_social_integration_use_supplied_current_monthly_amounts"
        ): True,
        _minimum_amount_input(
            "belgium_social_integration_supplied_cohabitant_current_monthly_amount"
        ): 876.13,
        _minimum_amount_input(
            "belgium_social_integration_supplied_isolated_current_monthly_amount"
        ): 1_314.20,
        _minimum_amount_input(
            "belgium_social_integration_supplied_dependent_family_current_monthly_amount"
        ): 1_776.07,
        _payable_amount_input(
            "belgium_social_integration_use_supplied_chapter_2_countable_annual_resources"
        ): True,
        _payable_amount_input(
            "belgium_social_integration_supplied_chapter_2_countable_annual_resources"
        ): 0,
    }


def _isolated_senior_no_resources_axiom_inputs() -> dict[str, float | int | bool]:
    return {
        _grapa_amounts_input("shares_principal_residence"): False,
        _grapa_resources_input(
            "belgium_grapa_shares_principal_residence_with_spouse_or_legal_cohabitant"
        ): False,
        _grapa_resources_input(
            "belgium_grapa_personal_resources_and_pensions_after_exclusions"
        ): 0,
        _grapa_resources_input(
            "belgium_grapa_spouse_or_legal_cohabitant_resources_and_pensions_after_exclusions"
        ): 0,
        _grapa_resources_input("belgium_grapa_article_11_resource_exemption"): 1000,
        _grapa_payable_input(
            "belgium_grapa_use_supplied_article_6_maximum_annual_amount"
        ): True,
        _grapa_payable_input(
            "belgium_grapa_supplied_article_6_maximum_annual_amount"
        ): 18_964.44,
    }


def _euromod_isolated_no_resources_input() -> dict[str, float | int]:
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
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _euromod_single_parent_no_resources_inputs() -> list[dict[str, float | int]]:
    parent_id = 101
    return [
        _euromod_isolated_no_resources_input(),
        {
            "idperson": 102,
            "idpartner": 0,
            "idmother": parent_id,
            "idfather": 0,
            "dag": 5,
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
            "yse": 0,
            "yiy": 0,
            "poa": 0,
        },
    ]


def _euromod_isolated_senior_no_resources_input() -> dict[str, float | int]:
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 70,
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
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _eligibility_input(name: str) -> str:
    return f"{ELIGIBILITY_MODULE}#input.{name}"


def _minimum_amount_input(name: str) -> str:
    return f"{MINIMUM_AMOUNT_MODULE}#input.{name}"


def _payable_amount_input(name: str) -> str:
    return f"{PAYABLE_AMOUNT_MODULE}#input.{name}"


def _grapa_amounts_input(name: str) -> str:
    return f"{GRAPA_AMOUNTS_MODULE}#input.{name}"


def _grapa_resources_input(name: str) -> str:
    return f"{GRAPA_RESOURCES_MODULE}#input.{name}"


def _grapa_payable_input(name: str) -> str:
    return f"{GRAPA_PAYABLE_MODULE}#input.{name}"
