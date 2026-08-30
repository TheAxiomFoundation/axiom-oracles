from __future__ import annotations

from ..core.case import Case, Concepts, Entity


BE_SCOPE = {"type": "country", "geoid": "BE"}
BE_METADATA = {
    "locale": "BE",
    "scope": BE_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
ARTICLE_51_FORFAITS_MODULE = (
    "be:statutes/income_tax/professional_expenses/article_51_forfaits"
)
EMPLOYER_SSC_MODULE = "be:regulations/social_security/workers/employer_contributions"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"


def be_article_51_forfait_cases() -> list[Case]:
    """Belgium Article 51 employee-forfait cases on a documentary module.

    EUROMOD exposes ``il_netYem``, employment income after ordinary employee
    social-security contributions, as the Article 51 base. The bridge supplies
    that value directly to the source-backed Article 51 module; no end-to-end
    worker-PIT or oracle-pipeline concept is involved. The legacy documentary
    target remains active only pending the signed canonical page-121/page-122
    migration, after which this suite must be retargeted and rerun.
    """

    return [
        _single_worker_forfait_case("be-article-51-forfait-12k", 12_000.0),
        _single_worker_forfait_case("be-article-51-forfait-22k", 22_000.0),
        _single_worker_forfait_case("be-article-51-forfait-27k", 27_000.0),
        _single_worker_forfait_case("be-article-51-forfait-35k", 35_000.0),
        _single_worker_forfait_case("be-article-51-forfait-60k", 60_000.0),
    ]


def be_employer_ssc_cases() -> list[Case]:
    """Single-worker Belgium employer-SSC cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_employer_ssc_case("be-employer-ssc-30k", 30_000.0),
        _single_worker_employer_ssc_case("be-employer-ssc-60k", 60_000.0),
    ]


def _single_worker_forfait_case(case_id: str, annual_income: float) -> Case:
    forfait_base_input = _article_51_forfaits_input(
        "belgium_pit_article_51_forfait_base_amount"
    )
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_ARTICLE_51_EMPLOYEE_FORFAIT,
        axiom_inputs={forfait_base_input: annual_income},
        metadata_extra={
            "scenario": "single-worker-article-51-forfait",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "il_netYem": [forfait_base_input],
            },
        },
    )


def _single_worker_employer_ssc_case(case_id: str, annual_income: float) -> Case:
    contribution_base_input = _employer_ssc_input(
        "belgium_employer_social_security_contribution_base"
    )
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_EMPLOYER_SOCIAL_CONTRIBUTIONS,
        axiom_inputs={
            contribution_base_input: annual_income,
            _employer_ssc_input(
                "belgium_employer_social_security_employer_has_at_least_10_workers"
            ): True,
            _employer_ssc_input(
                "belgium_employer_social_security_employer_has_at_least_20_workers"
            ): False,
        },
        metadata_extra={
            "scenario": "single-worker-employer-ssc",
            "yearly_earned_income": annual_income,
            "employer_has_at_least_10_workers": True,
            "employer_has_at_least_20_workers": False,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [contribution_base_input],
            },
        },
    )


def _single_worker_case(
    case_id: str,
    annual_income: float,
    *,
    output: str | tuple[str, ...],
    axiom_inputs: dict[str, float | bool],
    metadata_extra: dict[str, object],
) -> Case:
    outputs = output if isinstance(output, tuple) else (output,)
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            **metadata_extra,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [_euromod_worker_input(annual_income)],
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
        outputs=outputs,
    )


def _article_51_forfaits_input(name: str) -> str:
    return f"{ARTICLE_51_FORFAITS_MODULE}#input.{name}"


def _employer_ssc_input(name: str) -> str:
    return f"{EMPLOYER_SSC_MODULE}#input.{name}"


def _euromod_worker_input(annual_income: float) -> dict[str, float | int]:
    employed = annual_income > 0
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
        "loc": 5,
        "yem": annual_income / 12,
        "yemmy": 12 if employed else 0,
    }
