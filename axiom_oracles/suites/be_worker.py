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
PENSIONER_PIT_MODULE = "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline"
SELF_EMPLOYMENT_PIT_MODULE = (
    "be:statutes/income_tax/individual/self_employed_oracle_pipeline"
)
SELF_EMPLOYED_SSC_MODULE = "be:regulations/social_security/self_employed/contributions"
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

# Live-probed against EUROMOD_RELEASES_J2.0+, BE_2025,
# BE_2024_c1_2015_03_e2 on 2026-08-22. EUROMOD uprates these monthly inputs
# before exposing them as output columns; each synthetic row pre-divides by
# its own factor so the post-uprating bridge supplies the fixture's annual
# amount to RuleSpec. ``poa`` is not uprated in this model vintage.
EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR = 1.055022392834293
EUROMOD_BE_2025_BUN_UPRATING_FACTOR = 1.0793082886106142
EUROMOD_BE_2025_BHL_UPRATING_FACTOR = 1.1096513390601312
EUROMOD_BE_2025_POA_UPRATING_FACTOR = 1.0
MERGED_BELGIUM_PIPELINES_FIXTURE_COMMIT = "b105e2b3a3086ddd2de447d58a9b951346870dd1"


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


def be_pensioner_pit_cases() -> list[Case]:
    """Merged Belgian pensioner-PIT fixtures against EUROMOD BE_2025.

    The three pension-only rows compare final PIT, pension social withholding,
    and the Articles 147--153 pension reduction to ``tin_s``, ``tscpe_s``, and
    ``tintcri_s``. The mixed pension-and-wage row carries the two named
    EUROMOD mechanisms documented in JRC issues #26 and #12.
    """

    return [
        _pensioner_pit_case(
            "be-pensioner-pit-pension-15k",
            fixture_name="pension_15k_reduction_consumes_all_remaining_tax",
            pension=15_000.0,
            article_153_pension_tax_share=1_022.5,
        ),
        _pensioner_pit_case(
            "be-pensioner-pit-pension-25k",
            fixture_name=(
                "pension_25k_article_191_band_and_partial_additional_reduction"
            ),
            pension=25_000.0,
            article_153_pension_tax_share=4_605.604,
        ),
        _pensioner_pit_case(
            "be-pensioner-pit-pension-40k",
            fixture_name="pension_40k_solidarity_band_and_article_152_phaseout",
            pension=40_000.0,
            article_153_pension_tax_share=10_475.5,
        ),
        _pensioner_pit_case(
            "be-pensioner-pit-pension-30k-wage-15k",
            fixture_name="mixed_30k_pension_15k_wage_prorates_reductions",
            pension=30_000.0,
            wage=15_000.0,
            work_bonus_reference=12_931.034482758621,
            article_153_pension_tax_share=8_166.699220235831,
        ),
    ]


def be_self_employment_pit_cases() -> list[Case]:
    """Merged self-employment-PIT fixtures against EUROMOD BE_2025.

    Four rows compare final PIT. The fifth deliberately feeds EUROMOD a
    negative net ``yse`` while retaining the source-backed RuleSpec gross and
    justified-expense inputs, exposing EUROMOD's ``max(yse, 0)`` convention on
    the shared taxable-income surface.
    """

    return [
        _self_employment_pit_case(
            "be-self-employment-pit-yse-25k",
            fixture_name=(
                "euromod_exact_gross_yse_25000_exposes_credit_before_local_tax_engine_order"
            ),
            self_employment_income=25_000.0,
            low_activity_credit=880.0,
        ),
        _self_employment_pit_case(
            "be-self-employment-pit-yse-45k",
            fixture_name="euromod_exact_gross_yse_45000_matches_to_machine_precision",
            self_employment_income=45_000.0,
        ),
        _self_employment_pit_case(
            "be-self-employment-pit-yse-70k",
            fixture_name="euromod_exact_gross_yse_70000_matches_to_machine_precision",
            self_employment_income=70_000.0,
        ),
        _self_employment_pit_case(
            "be-self-employment-pit-yem-30k-yse-20k",
            fixture_name="mixed_yem_30000_yse_20000_exposes_imported_semantics",
            self_employment_income=20_000.0,
            wage=30_000.0,
            work_bonus_reference=30_000.0,
            work_bonus_reference_bridge="yem",
            secondary_activity=True,
        ),
        _self_employment_pit_case(
            "be-self-employment-pit-negative-yse-1k-yem-10k",
            fixture_name=(
                "article_23_current_self_employment_loss_nets_across_worker_activity"
            ),
            self_employment_income=1_000.0,
            euromod_net_self_employment_income=-1_000.0,
            justified_professional_expenses=2_000.0,
            wage=10_000.0,
            work_bonus_reference=8_620.689655172413,
            secondary_activity=True,
            regional_additional_tax_rate=0.0,
            communal_additional_tax_rate=0.0,
            output=Concepts.BE_SELF_EMPLOYMENT_COMBINED_TAXABLE_INCOME,
        ),
    ]


def be_replacement_income_pit_cases() -> list[Case]:
    """Merged unemployment/sickness replacement-income PIT fixtures."""

    return [
        _replacement_income_pit_case(
            "be-replacement-income-pit-bun-12k",
            fixture_name="unemployment_12k_euromod_input_bun_zero_tax",
            unemployment_benefit=12_000.0,
            article_153_unemployment_tax_share=272.5,
        ),
        _replacement_income_pit_case(
            "be-replacement-income-pit-bun-18k",
            fixture_name="unemployment_18k_euromod_input_bun_zero_tax",
            unemployment_benefit=18_000.0,
            article_153_unemployment_tax_share=2_024.5,
        ),
        _replacement_income_pit_case(
            "be-replacement-income-pit-bun-24k",
            fixture_name="unemployment_24k_euromod_articles_147_to_153",
            unemployment_benefit=24_000.0,
            article_153_unemployment_tax_share=4_424.5,
        ),
        _replacement_income_pit_case(
            "be-replacement-income-pit-bhl-18k",
            fixture_name="sickness_18k_euromod_bhl_article_153_cap",
            sickness_benefit=18_000.0,
            article_153_sickness_tax_share=2_024.5,
        ),
        _replacement_income_pit_case(
            "be-replacement-income-pit-bun-15k-yem-15k",
            fixture_name="unemployment_15k_plus_wage_15k_no_activity_exclusion",
            unemployment_benefit=15_000.0,
            article_153_unemployment_tax_share=2_955.5882352941176,
            wage=15_000.0,
            work_bonus_reference=12_931.034482758621,
        ),
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


def _pensioner_pit_case(
    case_id: str,
    *,
    fixture_name: str,
    pension: float,
    article_153_pension_tax_share: float,
    wage: float = 0.0,
    work_bonus_reference: float = 0.0,
) -> Case:
    gross_pension_input = _pensioner_pit_input(
        "belgium_pit_pensioner_annual_gross_pension"
    )
    legal_pension_input = _pensioner_pit_input(
        "belgium_pit_pensioner_annual_legal_pension"
    )
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    inputs: dict[str, float | bool] = {
        gross_pension_input: pension,
        legal_pension_input: pension,
        _pensioner_pit_input(
            "belgium_pit_pensioner_article_153_tax_share_attributable_to_pension_income"
        ): article_153_pension_tax_share,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_153_tax_share_attributable_to_unemployment_benefits"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_153_tax_share_attributable_to_sickness_invalidity_indemnities"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_annual_gross_unemployment_benefit"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_annual_gross_sickness_benefit"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_annual_gross_invalidity_benefit"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_annual_invalidity_social_withholding"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_151_older_unemployed_with_seniority_supplement"
        ): False,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_154_first_twelve_month_maximum_unemployment_benefit"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_154_mixed_replacement_excess_rate"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_pensioner_beneficiary_has_family_charge"
        ): False,
        _pensioner_pit_input(
            "belgium_pit_pensioner_has_reached_legal_retirement_age"
        ): True,
        _pensioner_pit_input(
            "belgium_pit_pensioner_receives_survivor_pension_or_transition_allowance"
        ): False,
        _pensioner_pit_input("belgium_pit_pensioner_communal_additional_tax_rate"): 0,
        _pensioner_pit_input(
            "belgium_pit_pensioner_agglomeration_additional_tax_rate"
        ): 0,
        remuneration_input: wage,
        WORK_BONUS_REFERENCE_INPUT: work_bonus_reference,
    }
    bridge = {
        "poa": _person_record_bridge(gross_pension_input, legal_pension_input),
        "yem": _person_record_bridge(remuneration_input),
        "yemeq_s": _person_record_bridge(WORK_BONUS_REFERENCE_INPUT),
    }
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "single-pensioner-pit"
            if wage == 0
            else "mixed-pension-wage-pit",
            "yearly_pension_income": pension,
            "yearly_earned_income": wage,
            "rulespec_fixture_commit": MERGED_BELGIUM_PIPELINES_FIXTURE_COMMIT,
            "rulespec_fixture": (
                "be/statutes/income_tax/individual/"
                f"pensioner_pit_oracle_pipeline.test.yaml#{fixture_name}"
            ),
            "euromod_input_uprating_factors": {
                "poa": EUROMOD_BE_2025_POA_UPRATING_FACTOR,
                "yem": EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
            },
            "axiom_input_records": _person_input_records(inputs),
            "euromod_inputs": [_euromod_pensioner_pit_input(pension, wage)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: bridge,
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 70,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PENSION_INCOME: pension,
                    Concepts.YEARLY_EARNED_INCOME: wage,
                },
            ),
        ),
        outputs=(
            (Concepts.BE_PENSIONER_PIT_BEFORE_WITHHOLDING,)
            if wage
            else (
                Concepts.BE_PENSIONER_PIT_BEFORE_WITHHOLDING,
                Concepts.BE_PENSIONER_ANNUAL_SOCIAL_WITHHOLDING,
                Concepts.BE_PENSIONER_REPLACEMENT_REDUCTION,
            )
        ),
    )


def _self_employment_pit_case(
    case_id: str,
    *,
    fixture_name: str,
    self_employment_income: float,
    wage: float = 0.0,
    work_bonus_reference: float = 0.0,
    work_bonus_reference_bridge: str = "yemeq_s",
    low_activity_credit: float = 0.0,
    secondary_activity: bool = False,
    justified_professional_expenses: float = 0.0,
    euromod_net_self_employment_income: float | None = None,
    regional_additional_tax_rate: float = 0.33257,
    communal_additional_tax_rate: float = 0.0717,
    output: str = Concepts.BE_SELF_EMPLOYMENT_PIT_BEFORE_WITHHOLDING,
) -> Case:
    gross_self_employment_input = _self_employed_ssc_input(
        "belgium_self_employed_gross_professional_income"
    )
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    inputs: dict[str, float | bool] = {
        _self_employed_ssc_input("belgium_self_employed_article_14_index_factor"): (
            4.639439281617473
        ),
        gross_self_employment_input: self_employment_income,
        _self_employed_ssc_input("belgium_self_employed_professional_expenses"): 0,
        _self_employed_ssc_input("belgium_self_employed_professional_losses"): 0,
        _self_employed_ssc_input(
            "belgium_self_employed_prior_activity_income_taxed_current_year"
        ): 0,
        _self_employed_ssc_input(
            "belgium_self_employed_article_28_cessation_income"
        ): 0,
        _self_employed_ssc_input(
            "belgium_self_employed_article_28_exclusion_condition_met"
        ): False,
        _self_employed_ssc_input(
            "belgium_self_employed_early_retirement_pension_suspended_for_income_ceiling"
        ): False,
        _self_employed_ssc_input(
            "belgium_self_employed_has_reached_pension_age"
        ): False,
        _self_employed_ssc_input("belgium_self_employed_is_secondary_activity"): (
            secondary_activity
        ),
        _self_employed_ssc_input("belgium_self_employed_is_spouse_helper"): False,
        _self_employed_ssc_input(
            "belgium_self_employed_is_starter_main_activity"
        ): False,
        _self_employed_ssc_input("belgium_self_employed_is_student"): False,
        _self_employed_ssc_input(
            "belgium_self_employed_receives_retirement_or_survivor_pension"
        ): False,
        _self_employed_ssc_input(
            "belgium_spouse_helper_fiscally_attributed_professional_income"
        ): 0,
        _self_employed_ssc_input("belgium_spouse_helper_only_indemnity_sector"): False,
        remuneration_input: wage,
        WORK_BONUS_REFERENCE_INPUT: work_bonus_reference,
        _self_employment_pit_input(
            "belgium_pit_self_employment_actual_professional_expenses_are_justified"
        ): True,
        _self_employment_pit_input(
            "belgium_pit_self_employment_agglomeration_additional_tax_rate"
        ): 0,
        _self_employment_pit_input(
            "belgium_pit_self_employment_article_466_separately_taxed_income_tax_included_in_total"
        ): 0,
        _self_employment_pit_input(
            "belgium_pit_self_employment_article_466_tax_share_on_nonprofessional_movable_income"
        ): 0,
        _self_employment_pit_input(
            "belgium_pit_self_employment_article_51_business_purchase_costs"
        ): 0,
        _self_employment_pit_input(
            "belgium_pit_self_employment_communal_additional_tax_rate"
        ): communal_additional_tax_rate,
        _self_employment_pit_input(
            "belgium_pit_self_employment_is_business_profit_category"
        ): False,
        _self_employment_pit_input(
            "belgium_pit_self_employment_justified_professional_expenses_excluding_social_contribution_and_purchase_costs"
        ): justified_professional_expenses,
        _self_employment_pit_input(
            "belgium_pit_self_employment_prior_period_professional_losses"
        ): 0,
        _self_employment_pit_input(
            "belgium_pit_self_employment_regional_additional_tax_rate"
        ): regional_additional_tax_rate,
        _self_employment_pit_input(
            "belgium_pit_self_employment_supplied_low_activity_income_refundable_credit"
        ): low_activity_credit,
    }
    bridge: dict[str, object] = {
        "yem": _person_record_bridge(remuneration_input),
    }
    if work_bonus_reference_bridge == "yem":
        bridge["yem"] = _person_record_bridge(
            remuneration_input,
            WORK_BONUS_REFERENCE_INPUT,
        )
    else:
        bridge["yemeq_s"] = _person_record_bridge(WORK_BONUS_REFERENCE_INPUT)
    if euromod_net_self_employment_income is None:
        bridge["yse"] = _person_record_bridge(gross_self_employment_input)
    euromod_yse = (
        self_employment_income
        if euromod_net_self_employment_income is None
        else euromod_net_self_employment_income
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": (
                "negative-self-employment-netting"
                if euromod_net_self_employment_income is not None
                else "self-employment-pit"
            ),
            "yearly_self_employment_income": self_employment_income,
            "yearly_euromod_yse": euromod_yse,
            "yearly_earned_income": wage,
            "rulespec_fixture_commit": MERGED_BELGIUM_PIPELINES_FIXTURE_COMMIT,
            "rulespec_fixture": (
                "be/statutes/income_tax/individual/"
                f"self_employed_oracle_pipeline.test.yaml#{fixture_name}"
            ),
            "euromod_input_uprating_factors": {
                "yem": EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
                "yse": EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
            },
            "axiom_input_records": _person_input_records(inputs),
            "euromod_inputs": [_euromod_self_employment_pit_input(euromod_yse, wage)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: bridge,
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.SELF_EMPLOYMENT_INCOME: self_employment_income,
                    Concepts.YEARLY_EARNED_INCOME: wage,
                },
            ),
        ),
        outputs=(output,),
    )


def _replacement_income_pit_case(
    case_id: str,
    *,
    fixture_name: str,
    unemployment_benefit: float = 0.0,
    sickness_benefit: float = 0.0,
    article_153_unemployment_tax_share: float = 0.0,
    article_153_sickness_tax_share: float = 0.0,
    wage: float = 0.0,
    work_bonus_reference: float = 0.0,
) -> Case:
    unemployment_input = _pensioner_pit_input(
        "belgium_pit_replacement_annual_gross_unemployment_benefit"
    )
    sickness_input = _pensioner_pit_input(
        "belgium_pit_replacement_annual_gross_sickness_benefit"
    )
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    inputs: dict[str, float | bool] = {
        _pensioner_pit_input("belgium_pit_pensioner_annual_gross_pension"): 0,
        _pensioner_pit_input("belgium_pit_pensioner_annual_legal_pension"): 0,
        _pensioner_pit_input(
            "belgium_pit_pensioner_article_153_tax_share_attributable_to_pension_income"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_153_tax_share_attributable_to_unemployment_benefits"
        ): article_153_unemployment_tax_share,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_153_tax_share_attributable_to_sickness_invalidity_indemnities"
        ): article_153_sickness_tax_share,
        unemployment_input: unemployment_benefit,
        sickness_input: sickness_benefit,
        _pensioner_pit_input(
            "belgium_pit_replacement_annual_gross_invalidity_benefit"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_annual_invalidity_social_withholding"
        ): 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_151_older_unemployed_with_seniority_supplement"
        ): False,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_154_first_twelve_month_maximum_unemployment_benefit"
        ): 20_000 if unemployment_benefit else 0,
        _pensioner_pit_input(
            "belgium_pit_replacement_article_154_mixed_replacement_excess_rate"
        ): 0.9,
        _pensioner_pit_input(
            "belgium_pit_pensioner_beneficiary_has_family_charge"
        ): False,
        _pensioner_pit_input(
            "belgium_pit_pensioner_has_reached_legal_retirement_age"
        ): False,
        _pensioner_pit_input(
            "belgium_pit_pensioner_receives_survivor_pension_or_transition_allowance"
        ): False,
        _pensioner_pit_input("belgium_pit_pensioner_communal_additional_tax_rate"): 0,
        _pensioner_pit_input(
            "belgium_pit_pensioner_agglomeration_additional_tax_rate"
        ): 0,
        remuneration_input: wage,
        WORK_BONUS_REFERENCE_INPUT: work_bonus_reference,
    }
    bridge: dict[str, object] = {
        "yem": _person_record_bridge(remuneration_input),
        "yemeq_s": _person_record_bridge(WORK_BONUS_REFERENCE_INPUT),
    }
    if unemployment_benefit:
        bridge["bun"] = _person_record_bridge(unemployment_input)
        reduction_output = Concepts.BE_REPLACEMENT_UNEMPLOYMENT_REDUCTION
    else:
        bridge["bhl"] = _person_record_bridge(sickness_input)
        reduction_output = Concepts.BE_REPLACEMENT_SICKNESS_INVALIDITY_REDUCTION
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": (
                "unemployment-replacement-income-pit"
                if unemployment_benefit
                else "sickness-replacement-income-pit"
            ),
            "yearly_unemployment_income": unemployment_benefit,
            "yearly_sickness_income": sickness_benefit,
            "yearly_earned_income": wage,
            "rulespec_fixture_commit": MERGED_BELGIUM_PIPELINES_FIXTURE_COMMIT,
            "rulespec_fixture": (
                "be/statutes/income_tax/individual/"
                f"pensioner_pit_oracle_pipeline.test.yaml#{fixture_name}"
            ),
            "euromod_input_uprating_factors": {
                "bun": EUROMOD_BE_2025_BUN_UPRATING_FACTOR,
                "bhl": EUROMOD_BE_2025_BHL_UPRATING_FACTOR,
                "yem": EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
            },
            "axiom_input_records": _person_input_records(inputs),
            "euromod_inputs": [
                _euromod_replacement_income_pit_input(
                    unemployment_benefit=unemployment_benefit,
                    sickness_benefit=sickness_benefit,
                    wage=wage,
                )
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: bridge,
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 45,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.UNEMPLOYMENT_INSURANCE_INCOME: unemployment_benefit,
                    Concepts.YEARLY_EARNED_INCOME: wage,
                },
            ),
        ),
        outputs=(
            (Concepts.BE_PENSIONER_PIT_BEFORE_WITHHOLDING,)
            if wage
            else (Concepts.BE_PENSIONER_PIT_BEFORE_WITHHOLDING, reduction_output)
        ),
    )


def _single_worker_pit_case(case_id: str, annual_income: float) -> Case:
    remuneration_input = _pit_input("belgium_pit_article_23_worker_remuneration")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.BE_WORKER_PIT_BEFORE_WITHHOLDING,
        axiom_inputs={
            remuneration_input: annual_income,
            WORK_BONUS_REFERENCE_INPUT: 0,
            _pit_input(
                "belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"
            ): 0,
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
            _pit_input(
                "belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"
            ): 0,
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
            _pit_input(
                "belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"
            ): 0,
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
            _pit_input(
                "belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_hypothetical_total_tax_if_treaty_exempt_foreign_professional_income_were_belgian"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_treaty_exempt_foreign_professional_income_base_applies"
            ): False,
            _pit_input("belgium_pit_communal_additional_tax_rate"): 0,
            _pit_input("belgium_pit_agglomeration_additional_tax_rate"): 0,
            _tax_income_list_input(
                "belgium_euromod_ils_tax_include_pit_component"
            ): True,
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
            _pit_input(
                "belgium_pit_article_466_tax_share_on_nonprofessional_movable_income"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_hypothetical_total_tax_if_treaty_exempt_foreign_professional_income_were_belgian"
            ): 0,
            _pit_input(
                "belgium_pit_article_466bis_treaty_exempt_foreign_professional_income_base_applies"
            ): False,
            _pit_input("belgium_pit_communal_additional_tax_rate"): 0,
            _pit_input("belgium_pit_agglomeration_additional_tax_rate"): 0,
            _tax_income_list_input(
                "belgium_euromod_ils_tax_include_pit_component"
            ): True,
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
    spouse_a_role_input = _couple_pit_input("belgium_pit_couple_worker_is_spouse_a")
    spouse_b_role_input = _couple_pit_input("belgium_pit_couple_worker_is_spouse_b")
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


def _pensioner_pit_input(name: str) -> str:
    return f"{PENSIONER_PIT_MODULE}#input.{name}"


def _self_employment_pit_input(name: str) -> str:
    return f"{SELF_EMPLOYMENT_PIT_MODULE}#input.{name}"


def _self_employed_ssc_input(name: str) -> str:
    return f"{SELF_EMPLOYED_SSC_MODULE}#input.{name}"


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


def _person_input_records(
    inputs: dict[str, float | bool],
) -> list[dict[str, str | float | bool]]:
    return [
        {
            "name": name,
            "entity": "Person",
            "entity_id": "head",
            "value": value,
        }
        for name, value in inputs.items()
    ]


def _person_record_bridge(*input_names: str) -> dict[str, list[dict[str, str]]]:
    return {
        "records": [
            {
                "name": name,
                "entity": "Person",
                "entity_id": "head",
            }
            for name in input_names
        ]
    }


def _euromod_pensioner_pit_input(
    annual_pension: float,
    annual_wage: float,
) -> dict[str, float | int]:
    employed = annual_wage > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 70,
        "dgn": 1,
        "dms": 1,
        "drgn1": 0,
        "dwt": 1,
        "les": 4,
        "lfs": 15,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 540,
        "loc": 5,
        "poa": (annual_pension / 12.0 / EUROMOD_BE_2025_POA_UPRATING_FACTOR),
        "yem": annual_wage / 12.0 / EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
        "yemmy": 12 if employed else 0,
        "yse": 0,
        "yiy": 0,
    }


def _euromod_self_employment_pit_input(
    annual_self_employment_income: float,
    annual_wage: float,
) -> dict[str, float | int]:
    employed = annual_wage > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "drgn1": 2,
        "dwt": 1,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "loc": 5,
        "poa": 0,
        "yem": annual_wage / 12.0 / EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
        "yemmy": 12 if employed else 0,
        "yse": (
            annual_self_employment_income
            / 12.0
            / EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR
        ),
        "yiy": 0,
    }


def _euromod_replacement_income_pit_input(
    *,
    unemployment_benefit: float,
    sickness_benefit: float,
    wage: float,
) -> dict[str, float | int]:
    is_unemployment = unemployment_benefit > 0
    employed = wage > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 45,
        "dgn": 1,
        "ddi": 0,
        "dms": 1,
        "drgn1": 0,
        "dwt": 1,
        "les": 5 if is_unemployment else 6,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "loc": 5,
        "lunmy": 12 if is_unemployment else 0,
        "bun": (unemployment_benefit / 12.0 / EUROMOD_BE_2025_BUN_UPRATING_FACTOR),
        "bunmy": 12 if is_unemployment else 0,
        "bhl": sickness_benefit / 12.0 / EUROMOD_BE_2025_BHL_UPRATING_FACTOR,
        "poa": 0,
        "yem": wage / 12.0 / EUROMOD_BE_2025_YEM_YSE_UPRATING_FACTOR,
        "yemmy": 12 if employed else 0,
        "yse": 0,
        "yiy": 0,
    }


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
