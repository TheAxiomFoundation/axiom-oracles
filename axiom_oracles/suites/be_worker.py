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
COUPLE_PIT_MODULE = "be:statutes/income_tax/individual/couple_pit_oracle_pipeline"
JOINT_ASSESSMENT_MODULE = "be:statutes/income_tax/individual/joint_assessment"
TAX_FREE_AMOUNT_TAX_MODULE = (
    "be:statutes/income_tax/individual/tax_free_amount_tax"
)
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
COUPLE_SPOUSE_RELATION = (
    f"{COUPLE_PIT_MODULE}#relation.belgium_pit_couple_spouse_of_tax_unit"
)


def be_worker_pit_cases() -> list[Case]:
    """Single-worker Belgium PIT cases for the EUROMOD BE_2025 oracle."""

    return [
        _single_worker_pit_case("be-worker-pit-10k", 10_000.0),
        _single_worker_pit_case("be-worker-pit-30k", 30_000.0),
        _single_worker_pit_case("be-worker-pit-60k", 60_000.0),
    ]


def be_marital_quotient_cases() -> list[Case]:
    """Single-earner married-couple Belgium PIT cases for the EUROMOD BE_2025 oracle.

    These exercise the CIR 1992 Article 87 marital quotient (huwelijksquotiënt /
    quotient conjugal): when only one spouse has professional income, 30% of it
    (capped at the indexed 13,460 EUR) is imputed to the zero-income spouse, and
    each spouse is then taxed separately on their own post-imputation share with
    their own tax-free amount. The composed
    ``couple_pit_oracle_pipeline`` output is compared to the EUROMOD ``tin_s``
    household aggregate (the runner sums both members' tax). Because the whole
    household income belongs to spouse A, the ``yem`` and ``yemeq_s`` bridges
    feed the engine's post-uprating gross and work-bonus reference remuneration
    into the related ``head`` Person record. The ``spouse`` Person record is
    pinned at zero for both worker inputs.
    """

    return [
        _single_earner_couple_pit_case("be-marital-quotient-30k", 30_000.0),
        _single_earner_couple_pit_case("be-marital-quotient-45k", 45_000.0),
        _single_earner_couple_pit_case("be-marital-quotient-60k", 60_000.0),
    ]


def be_article_51_forfait_cases() -> list[Case]:
    """Single-worker Belgium Article 51 professional-expense forfait cases.

    Isolates the CIR 1992 Article 51 employee forfait ``tintace_s`` as its own
    comparison surface (it is otherwise exercised only as a base reduction inside
    the composed ``tin_s`` worker-PIT/marital-quotient pipelines). EUROMOD
    BE_2025 computes ``tintace_s = min(0.30 * il_netYem, 5930)`` where
    ``il_netYem`` is employment income after ordinary employee social security;
    the encoded ``belgium_pit_pilot_worker_forfait_professional_expenses`` applies
    the identical Article 51 employee rate (30%) and indexed cap (5,930 EUR) to
    the pipeline's own post-employee-SSC remuneration. Both engines therefore
    apply the same rate and cap to the same statutory base, bridged on the
    engine's post-uprating gross (``yem``).

    The sweep crosses the forfait cap: the 30% rate binds below a post-SSC base of
    ~19,767 EUR (0.30 * 19,766.67 = 5,930) and the cap binds above it. After
    uprating and ordinary employee SSC (13.07%), the 12k case lands on the 30%-rate
    side (post-SSC base ~11,000 EUR, forfait ~3,300 EUR) while 22k / 27k / 35k / 60k
    are all in the capped region (forfait 5,930 EUR), so the sweep exercises both
    limbs of the min().
    """

    return [
        _single_worker_forfait_case("be-article-51-forfait-12k", 12_000.0),
        _single_worker_forfait_case("be-article-51-forfait-22k", 22_000.0),
        _single_worker_forfait_case("be-article-51-forfait-27k", 27_000.0),
        _single_worker_forfait_case("be-article-51-forfait-35k", 35_000.0),
        _single_worker_forfait_case("be-article-51-forfait-60k", 60_000.0),
    ]


def be_pit_work_bonus_credit_cases() -> list[Case]:
    """Single-worker Belgium Article 289ter/1 work-bonus tax-credit cases.

    Isolates the refundable low-wage work-bonus credit ``tintcly_s`` — the
    ``tinfe_be`` fiscal-expenditure component EUROMOD BE_2025 labels the earned-
    income (EITC-style) credit — as its own comparison surface. It is otherwise
    exercised only folded into the composed ``tin_s`` worker-PIT liability. The
    encoded ``belgium_pit_pilot_article_289ter1_low_wage_work_bonus_credit``
    computes the CIR 1992 Article 289ter/1 credit from the ONSS full-year equal-
    month work-bonus A/B amounts capped by the employee contributions actually
    granted; EUROMOD BE_2025 ``tintcly_s`` computes the same credit from the
    UNCAPPED ``i_tsceerdA_s`` / ``i_tsceerdB_s`` bases (the sole difference).
    Both are bridged on the engine's post-uprating gross (``yem``).

    The sweep spans the credit region: the 10k / 14k cases are low-wage, where the
    uncapped-versus-granted base difference is visible (ec-jrc issue #12); the 30k
    / 45k cases sit where the credit tapers and the bases coincide.
    """

    return [
        _single_worker_work_bonus_credit_case("be-work-bonus-credit-10k", 10_000.0),
        _single_worker_work_bonus_credit_case("be-work-bonus-credit-14k", 14_000.0),
        _single_worker_work_bonus_credit_case("be-work-bonus-credit-30k", 30_000.0),
        _single_worker_work_bonus_credit_case("be-work-bonus-credit-45k", 45_000.0),
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


def _single_worker_forfait_case(case_id: str, annual_income: float) -> Case:
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_ARTICLE_51_EMPLOYEE_FORFAIT,
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
            "scenario": "single-worker-article-51-forfait",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [remuneration_input],
                "yemeq_s": [WORK_BONUS_REFERENCE_INPUT],
            },
        },
    )


def _single_worker_work_bonus_credit_case(case_id: str, annual_income: float) -> Case:
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_ARTICLE_289TER1_WORK_BONUS_CREDIT,
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
            "scenario": "single-worker-work-bonus-credit",
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


def _single_earner_couple_pit_case(case_id: str, annual_income: float) -> Case:
    """One married couple; only spouse A has professional income.

    The related ``head`` Person is spouse A and runs the imported worker pilot
    from EUROMOD's post-uprating gross ``yem`` and work-bonus reference
    ``yemeq_s``. The related ``spouse`` Person is spouse B and is pinned at zero
    for both worker inputs. The Article 126 joint-assessment flags select an
    ordinary joint assessment, and the Article 87/88 no-tax-increase guard is
    satisfied, so the Article 87 one-earner marital quotient applies. Local
    additions are supplied at 0 so the composed federal-plus-local output is
    comparable to EUROMOD ``tin_s``.
    """

    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    spouse_a_role_input = _couple_pit_input(
        "belgium_pit_couple_worker_is_spouse_a"
    )
    spouse_b_role_input = _couple_pit_input(
        "belgium_pit_couple_worker_is_spouse_b"
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "TaxUnit",
            "axiom_entity_id": "taxunit",
            "scenario": "single-earner-married-couple-marital-quotient",
            "yearly_earned_income": annual_income,
            "axiom_inputs": {
                _joint_assessment_input(
                    "belgium_pit_spouse_a_convention_exempt_professional_income_not_counted_for_other_tax"
                ): 0,
                _joint_assessment_input(
                    "belgium_pit_spouse_b_convention_exempt_professional_income_not_counted_for_other_tax"
                ): 0,
                _joint_assessment_input(
                    "belgium_pit_article_126_married_or_legal_cohabiting"
                ): True,
                _joint_assessment_input(
                    "belgium_pit_article_126_year_of_marriage_or_legal_cohabitation_declaration"
                ): False,
                _joint_assessment_input(
                    "belgium_pit_article_126_legal_cohabitants_marry_after_prior_year_declaration"
                ): False,
                _joint_assessment_input(
                    "belgium_pit_article_126_factual_separation_effective_for_entire_taxable_period_after_separation_year"
                ): False,
                _joint_assessment_input(
                    "belgium_pit_article_126_year_of_marriage_dissolution_legal_separation_or_cohabitation_cessation"
                ): False,
                _joint_assessment_input(
                    "belgium_pit_article_126_dissolution_by_death"
                ): False,
                _joint_assessment_input(
                    "belgium_pit_article_126_survivor_or_heirs_joint_assessment_election_made"
                ): False,
                _joint_assessment_input(
                    "belgium_pit_article_87_88_no_tax_increase_condition_met"
                ): True,
                _tax_free_amount_tax_input(
                    "belgium_pit_article_134_joint_lower_income_spouse_supplement_assignment_reduces_joint_state_tax"
                ): False,
                _couple_pit_input("belgium_pit_couple_communal_additional_tax_rate"): 0,
                _couple_pit_input(
                    "belgium_pit_couple_agglomeration_additional_tax_rate"
                ): 0,
            },
            "axiom_input_records": [
                {
                    "name": remuneration_input,
                    "entity": "Person",
                    "entity_id": "head",
                    "value": annual_income,
                },
                {
                    "name": WORK_BONUS_REFERENCE_INPUT,
                    "entity": "Person",
                    "entity_id": "head",
                    "value": 0,
                },
                {
                    "name": spouse_a_role_input,
                    "entity": "Person",
                    "entity_id": "head",
                    "value": True,
                },
                {
                    "name": spouse_b_role_input,
                    "entity": "Person",
                    "entity_id": "head",
                    "value": False,
                },
                {
                    "name": remuneration_input,
                    "entity": "Person",
                    "entity_id": "spouse",
                    "value": 0,
                },
                {
                    "name": WORK_BONUS_REFERENCE_INPUT,
                    "entity": "Person",
                    "entity_id": "spouse",
                    "value": 0,
                },
                {
                    "name": spouse_a_role_input,
                    "entity": "Person",
                    "entity_id": "spouse",
                    "value": False,
                },
                {
                    "name": spouse_b_role_input,
                    "entity": "Person",
                    "entity_id": "spouse",
                    "value": True,
                },
            ],
            "axiom_relations": {
                COUPLE_SPOUSE_RELATION: [
                    ["head", "taxunit"],
                    ["spouse", "taxunit"],
                ]
            },
            "euromod_inputs": _single_earner_couple_euromod_rows(annual_income),
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {
                    "records": [
                        {
                            "name": remuneration_input,
                            "entity": "Person",
                            "entity_id": "head",
                        }
                    ]
                },
                "yemeq_s": {
                    "records": [
                        {
                            "name": WORK_BONUS_REFERENCE_INPUT,
                            "entity": "Person",
                            "entity_id": "head",
                        }
                    ]
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
                entity_id="spouse",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.YEARLY_EARNED_INCOME: 0.0,
                },
            ),
        ),
        outputs=(Concepts.BE_MARITAL_QUOTIENT_COUPLE_PIT_BEFORE_WITHHOLDING,),
    )


def _pit_input(name: str) -> str:
    return f"{PIT_MODULE}#input.{name}"


def _joint_assessment_input(name: str) -> str:
    return f"{JOINT_ASSESSMENT_MODULE}#input.{name}"


def _couple_pit_input(name: str) -> str:
    return f"{COUPLE_PIT_MODULE}#input.{name}"


def _tax_free_amount_tax_input(name: str) -> str:
    return f"{TAX_FREE_AMOUNT_TAX_MODULE}#input.{name}"


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


def _single_earner_couple_euromod_rows(
    annual_income: float,
) -> list[dict[str, float | int]]:
    """Two married adults in one household; only the head has employment income.

    ``dms`` = 2 marks both as married and ``idpartner`` links them, so EUROMOD
    establishes the joint assessment and applies the marital quotient. The
    zero-income spouse is not employed (``les`` = 0).
    """

    head = {
        "idhh": 1,
        "idperson": 101,
        "idpartner": 102,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 2,
        "les": 3,
        "lfs": 15,
        "lhw": 38,
        "liwmy": 12,
        "liwwh": 120,
        "loc": 5,
        "yem": annual_income / 12,
        "yemmy": 12,
    }
    spouse = {
        "idhh": 1,
        "idperson": 102,
        "idpartner": 101,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 0,
        "dms": 2,
        "les": 0,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": 5,
        "yem": 0.0,
        "yemmy": 0,
    }
    return [head, spouse]
