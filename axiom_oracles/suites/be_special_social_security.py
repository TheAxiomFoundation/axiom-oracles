from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


SPECIAL_CONTRIBUTION_MODULE = "be:statutes/social_security/special_contribution"


def be_special_social_security_contribution_cases() -> list[Case]:
    """Belgium Article 108 special social-security contribution cases."""

    return [
        _single_worker_case(
            "be-special-social-security-single-10k",
            annual_income=10_000.0,
        ),
        _single_worker_case(
            "be-special-social-security-single-30k",
            annual_income=30_000.0,
        ),
        _single_worker_case(
            "be-special-social-security-single-55k",
            annual_income=55_000.0,
        ),
        _single_worker_case(
            "be-special-social-security-single-80k",
            annual_income=80_000.0,
        ),
        _joint_worker_case(
            "be-special-social-security-joint-one-earner-30k",
            head_annual_income=30_000.0,
            spouse_annual_income=0.0,
        ),
        _joint_worker_case(
            "be-special-social-security-joint-two-earner-30k-20k",
            head_annual_income=30_000.0,
            spouse_annual_income=20_000.0,
        ),
        _joint_worker_case(
            "be-special-social-security-joint-two-earner-60k-20k",
            head_annual_income=60_000.0,
            spouse_annual_income=20_000.0,
        ),
    ]


def _single_worker_case(case_id: str, *, annual_income: float) -> Case:
    return _special_contribution_case(
        case_id,
        scenario="single-worker-special-social-security-contribution",
        joint_assessment=False,
        yearly_earned_income=annual_income,
        euromod_inputs=[_euromod_worker_input(101, annual_income)],
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
    )


def _joint_worker_case(
    case_id: str,
    *,
    head_annual_income: float,
    spouse_annual_income: float,
) -> Case:
    return _special_contribution_case(
        case_id,
        scenario="joint-worker-special-social-security-contribution",
        joint_assessment=True,
        yearly_earned_income=head_annual_income + spouse_annual_income,
        euromod_inputs=[
            _euromod_worker_input(101, head_annual_income, partner_id=102, dms=2),
            _euromod_worker_input(102, spouse_annual_income, partner_id=101, dms=2),
        ],
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: head_annual_income,
                },
            ),
            Entity(
                entity_id="spouse",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.YEARLY_EARNED_INCOME: spouse_annual_income,
                },
            ),
        ),
        metadata_extra={
            "head_yearly_earned_income": head_annual_income,
            "spouse_yearly_earned_income": spouse_annual_income,
        },
    )


def _special_contribution_case(
    case_id: str,
    *,
    scenario: str,
    joint_assessment: bool,
    yearly_earned_income: float,
    euromod_inputs: list[dict[str, float | int]],
    entities: tuple[Entity, ...],
    metadata_extra: dict[str, float] | None = None,
) -> Case:
    household_income_input = _special_contribution_input(
        "belgium_special_social_security_article_107_household_income"
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": scenario,
            "joint_assessment": joint_assessment,
            "yearly_earned_income": yearly_earned_income,
            **(metadata_extra or {}),
            "axiom_inputs": {
                _special_contribution_input(
                    "belgium_special_social_security_household_has_article_106_person"
                ): True,
                _special_contribution_input(
                    "belgium_special_social_security_joint_assessment"
                ): joint_assessment,
                household_income_input: yearly_earned_income,
                _special_contribution_input(
                    "belgium_special_social_security_article_110_retained_or_supplement_paid"
                ): 0,
            },
            "euromod_inputs": euromod_inputs,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "il_taxabley": [household_income_input],
            },
        },
        entities=entities,
        outputs=(Concepts.BE_SPECIAL_SOCIAL_SECURITY_CONTRIBUTION,),
    )


def _euromod_worker_input(
    person_id: int,
    annual_income: float,
    *,
    partner_id: int = 0,
    dms: int = 1,
) -> dict[str, float | int]:
    employed = annual_income > 0
    return {
        "idperson": person_id,
        "idpartner": partner_id,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1 if person_id == 101 else 0,
        "dms": dms,
        "dcu": 0,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "loc": 5,
        "yem": annual_income / 12,
        "yemmy": 12 if employed else 0,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _special_contribution_input(name: str) -> str:
    return f"{SPECIAL_CONTRIBUTION_MODULE}#input.{name}"
