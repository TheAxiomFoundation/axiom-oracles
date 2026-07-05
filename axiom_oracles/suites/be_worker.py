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
EMPLOYER_SSC_MODULE = "be:regulations/social_security/workers/employer_contributions"
WORK_BONUS_MODULE = "be:regulations/social_security/workers/work_bonus"
EUROMOD_TAX_INCOME_LIST_MODULE = "be:policies/euromod_tax_income_list"
EUROMOD_DISPOSABLE_INCOME_LIST_MODULE = "be:policies/euromod_disposable_income_list"
SPECIAL_CONTRIBUTION_MODULE = "be:statutes/social_security/special_contribution"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"
WORK_BONUS_REFERENCE_INPUT = (
    f"{WORK_BONUS_MODULE}#input."
    "belgium_worker_work_bonus_supplied_reference_annual_remuneration"
)


def be_worker_pit_cases() -> list[Case]:
    """Single-worker Belgium PIT cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_pit_case("be-worker-pit-10k", 10_000.0),
        _single_worker_pit_case("be-worker-pit-30k", 30_000.0),
        _single_worker_pit_case("be-worker-pit-60k", 60_000.0),
    ]


def be_worker_tax_income_list_cases() -> list[Case]:
    """Single-worker Belgium tax-list cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_tax_income_list_case("be-worker-tax-income-list-30k", 30_000.0),
        _single_worker_tax_income_list_case("be-worker-tax-income-list-60k", 60_000.0),
    ]


def be_worker_disposable_income_list_cases() -> list[Case]:
    """Single-worker Belgium disposable-income cases for EUROMOD BE_2025."""

    return [
        _single_worker_disposable_income_list_case(
            "be-worker-disposable-income-list-30k",
            30_000.0,
        ),
        _single_worker_disposable_income_list_case(
            "be-worker-disposable-income-list-55k",
            55_000.0,
        ),
    ]


def be_worker_ssc_cases() -> list[Case]:
    """Single-worker Belgium employee-SSC cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_ssc_case("be-worker-ssc-30k", 30_000.0),
        _single_worker_ssc_case("be-worker-ssc-60k", 60_000.0),
    ]


def be_employer_ssc_cases() -> list[Case]:
    """Single-worker Belgium employer-SSC cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_employer_ssc_case("be-employer-ssc-30k", 30_000.0),
        _single_worker_employer_ssc_case("be-employer-ssc-60k", 60_000.0),
    ]


def _single_worker_pit_case(case_id: str, annual_income: float) -> Case:
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_WORKER_PIT_BEFORE_WITHHOLDING,
        axiom_inputs={
            remuneration_input: annual_income,
            WORK_BONUS_REFERENCE_INPUT: 0,
            _pit_input("belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"): 0,
            _pit_input(
                "belgium_pit_article_466bis_hypothetical_total_tax_if_treaty_exempt_foreign_professional_income_were_belgian"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_treaty_exempt_foreign_professional_income_base_applies"
            ): False,
            _pit_input("belgium_pit_communal_additional_tax_rate"): 0,
            _pit_input("belgium_pit_agglomeration_additional_tax_rate"): 0,
        },
        metadata_extra={
            "scenario": "single-worker-pit",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [remuneration_input],
                "yemeq_s": [WORK_BONUS_REFERENCE_INPUT],
            },
        },
    )


def _single_worker_tax_income_list_case(case_id: str, annual_income: float) -> Case:
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_EUROMOD_ILS_TAX_WORKER_PIT_PILOT,
        axiom_inputs={
            remuneration_input: annual_income,
            WORK_BONUS_REFERENCE_INPUT: 0,
            _pit_input("belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"): 0,
            _pit_input(
                "belgium_pit_article_466bis_hypothetical_total_tax_if_treaty_exempt_foreign_professional_income_were_belgian"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_treaty_exempt_foreign_professional_income_base_applies"
            ): False,
            _pit_input("belgium_pit_communal_additional_tax_rate"): 0,
            _pit_input("belgium_pit_agglomeration_additional_tax_rate"): 0,
            _tax_income_list_input("belgium_euromod_ils_tax_include_pit_component"): True,
            _tax_income_list_input(
                "belgium_euromod_ils_tax_supplied_capital_income_tax_annual_amount"
            ): 0,
            _tax_income_list_input(
                "belgium_euromod_ils_tax_supplied_property_tax_annual_amount"
            ): 0,
        },
        metadata_extra={
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": "single-worker-tax-income-list",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [remuneration_input],
                "yemeq_s": [WORK_BONUS_REFERENCE_INPUT],
            },
        },
    )


def _single_worker_disposable_income_list_case(
    case_id: str,
    annual_income: float,
) -> Case:
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    original_income_input = _disposable_income_list_input(
        "belgium_euromod_ils_dispy_supplied_original_income_annual_amount"
    )
    special_contribution_income_input = _special_contribution_input(
        "belgium_special_social_security_article_107_household_income"
    )
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_EUROMOD_ILS_DISPY_WORKER_PIT_SIC_PILOT,
        axiom_inputs={
            original_income_input: annual_income,
            _disposable_income_list_input(
                "belgium_euromod_ils_dispy_supplied_benefit_annual_amount"
            ): 0,
            _disposable_income_list_input(
                "belgium_euromod_ils_dispy_supplied_other_social_insurance_contribution_annual_amount"
            ): 0,
            remuneration_input: annual_income,
            WORK_BONUS_REFERENCE_INPUT: 0,
            _pit_input("belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"): 0,
            _pit_input(
                "belgium_pit_article_466bis_hypothetical_total_tax_if_treaty_exempt_foreign_professional_income_were_belgian"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_treaty_exempt_foreign_professional_income_base_applies"
            ): False,
            _pit_input("belgium_pit_communal_additional_tax_rate"): 0,
            _pit_input("belgium_pit_agglomeration_additional_tax_rate"): 0,
            _tax_income_list_input("belgium_euromod_ils_tax_include_pit_component"): True,
            _tax_income_list_input(
                "belgium_euromod_ils_tax_supplied_capital_income_tax_annual_amount"
            ): 0,
            _tax_income_list_input(
                "belgium_euromod_ils_tax_supplied_property_tax_annual_amount"
            ): 0,
            _special_contribution_input(
                "belgium_special_social_security_household_has_article_106_person"
            ): True,
            _special_contribution_input(
                "belgium_special_social_security_joint_assessment"
            ): False,
            special_contribution_income_input: annual_income,
            _special_contribution_input(
                "belgium_special_social_security_article_110_retained_or_supplement_paid"
            ): 0,
        },
        metadata_extra={
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": "single-worker-disposable-income-list",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [original_income_input, remuneration_input],
                "yemeq_s": [WORK_BONUS_REFERENCE_INPUT],
                "il_taxabley": [special_contribution_income_input],
            },
        },
    )


def _single_worker_ssc_case(case_id: str, annual_income: float) -> Case:
    contribution_base_input = _ssc_input(
        "belgium_employee_social_security_contribution_base"
    )
    return _single_worker_case(
        case_id,
        annual_income,
        output=(
            Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS_BEFORE_REDUCTIONS,
            Concepts.BE_EMPLOYEE_WORK_BONUS_REDUCTION,
            Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,
        ),
        axiom_inputs={
            contribution_base_input: annual_income,
            _ssc_input(
                "belgium_employee_social_security_supplied_work_bonus_reduction"
            ): 0,
            _ssc_input(
                "belgium_employee_social_security_supplied_other_worker_reduction"
            ): 0,
            WORK_BONUS_REFERENCE_INPUT: 0,
        },
        metadata_extra={
            "scenario": "single-worker-ssc",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [contribution_base_input],
                "yemeq_s": [WORK_BONUS_REFERENCE_INPUT],
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


def _pit_input(name: str) -> str:
    return f"{PIT_MODULE}#input.{name}"


def _ssc_input(name: str) -> str:
    return f"{SSC_MODULE}#input.{name}"


def _employer_ssc_input(name: str) -> str:
    return f"{EMPLOYER_SSC_MODULE}#input.{name}"


def _tax_income_list_input(name: str) -> str:
    return f"{EUROMOD_TAX_INCOME_LIST_MODULE}#input.{name}"


def _disposable_income_list_input(name: str) -> str:
    return f"{EUROMOD_DISPOSABLE_INCOME_LIST_MODULE}#input.{name}"


def _special_contribution_input(name: str) -> str:
    return f"{SPECIAL_CONTRIBUTION_MODULE}#input.{name}"


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
