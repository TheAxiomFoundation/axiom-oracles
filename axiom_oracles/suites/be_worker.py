from __future__ import annotations

from ..core.case import Case, Concepts, Entity


BE_SCOPE = {"type": "country", "geoid": "BE"}
BE_METADATA = {
    "locale": "BE",
    "scope": BE_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
PIT_MODULE = "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
SSC_MODULE = "be:regulations/social_security/workers/employee_contributions"


def be_worker_pit_cases() -> list[Case]:
    """Single-worker Belgium PIT cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_pit_case("be-worker-pit-30k", 30_000.0),
        _single_worker_pit_case("be-worker-pit-60k", 60_000.0),
    ]


def be_worker_ssc_cases() -> list[Case]:
    """Single-worker Belgium employee-SSC cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_ssc_case("be-worker-ssc-30k", 30_000.0),
        _single_worker_ssc_case("be-worker-ssc-60k", 60_000.0),
    ]


def _single_worker_pit_case(case_id: str, annual_income: float) -> Case:
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_WORKER_PIT_BEFORE_WITHHOLDING,
        axiom_inputs={
            _pit_input("belgium_pit_article_23_worker_remuneration"): annual_income,
            _pit_input("belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"): 0,
            _pit_input(
                "belgium_pit_article_466bis_hypothetical_total_tax_if_treaty_exempt_foreign_professional_income_were_belgian"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_treaty_exempt_foreign_professional_income_base_applies"
            ): False,
            _pit_input("belgium_pit_communal_additional_tax_rate"): 0,
            _pit_input("belgium_pit_agglomeration_additional_tax_rate"): 0,
            _pit_input("belgium_pit_professional_withholding"): 0,
            _pit_input("belgium_pit_prepayments"): 0,
            _pit_input("belgium_pit_other_withholding_or_creditable_tax"): 0,
        },
        metadata_extra={
            "scenario": "single-worker-pit",
            "yearly_earned_income": annual_income,
        },
    )


def _single_worker_ssc_case(case_id: str, annual_income: float) -> Case:
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,
        axiom_inputs={
            _ssc_input(
                "belgium_employee_social_security_contribution_base"
            ): annual_income,
            _ssc_input(
                "belgium_employee_social_security_supplied_work_bonus_reduction"
            ): 0,
            _ssc_input(
                "belgium_employee_social_security_supplied_other_worker_reduction"
            ): 0,
        },
        metadata_extra={
            "scenario": "single-worker-ssc",
            "yearly_earned_income": annual_income,
        },
    )


def _single_worker_case(
    case_id: str,
    annual_income: float,
    *,
    output: str,
    axiom_inputs: dict[str, float | bool],
    metadata_extra: dict[str, object],
) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            **metadata_extra,
            "axiom_inputs": axiom_inputs,
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
        outputs=(output,),
    )


def _pit_input(name: str) -> str:
    return f"{PIT_MODULE}#input.{name}"


def _ssc_input(name: str) -> str:
    return f"{SSC_MODULE}#input.{name}"
