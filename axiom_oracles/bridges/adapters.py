"""PolicyEngine adapter metadata for oracle scenario construction."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyEngineUSVarAdapter:
    """Declarative mapping/config for PE-US replay of an encoded variable."""

    rule_names: tuple[str, ...]
    pe_var: str
    entity: str | None = None
    period: str | None = None
    unit: str | None = None
    comparison: str | None = None
    monthly: bool = False
    spm: bool = False
    derived_person_inputs: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    direct_person_inputs: tuple[tuple[str, str], ...] = ()
    annualized_person_inputs: tuple[tuple[str, str], ...] = ()
    monthly_person_inputs: tuple[tuple[str, str], ...] = ()
    boolean_person_inputs: tuple[tuple[str, str], ...] = ()
    monthly_boolean_person_inputs: tuple[tuple[str, str], ...] = ()
    boolean_enum_person_inputs: tuple[tuple[str, str, str, str], ...] = ()
    monthly_derived_boolean_person_inputs: tuple[
        tuple[str, str, tuple[str, ...]], ...
    ] = ()
    direct_spm_overrides: tuple[tuple[str, str], ...] = ()
    derived_spm_overrides: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    annual_direct_spm_overrides: tuple[tuple[str, str], ...] = ()
    annual_derived_spm_overrides: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    direct_household_overrides: tuple[tuple[str, str], ...] = ()
    inverted_boolean_household_overrides: tuple[tuple[str, str], ...] = ()
    annual_direct_household_overrides: tuple[tuple[str, str], ...] = ()
    annual_inverted_boolean_household_overrides: tuple[tuple[str, str], ...] = ()
    projectable_input_keys: tuple[str, ...] = ()
    unsupported_input_keys: tuple[str, ...] = ()
    unsupported_input_patterns: tuple[str, ...] = ()
    unsupported_falsy_input_keys: tuple[str, ...] = ()
    unsupported_truthy_input_keys: tuple[str, ...] = ()
    unsupported_input_reason: str | None = None
    default_state_code: str | None = None
    state_code_from_boolean_input: tuple[str, str, str] | None = None
    parameter_path: str | None = None
    parameter_value_mode: str = "bool"
    target_person_role: str | None = None


def normalize_state_code_from_utility_region(region: str) -> str:
    """Map sub-state SNAP utility region codes back to their parent state code."""
    match = re.match(r"^([A-Z]{2})_", region)
    if match:
        return match.group(1)
    return region


PE_US_VAR_ADAPTERS = (
    PolicyEngineUSVarAdapter(
        rule_names=("snap", "snap_benefits"),
        pe_var="snap",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_allotment", "snap_normal_allotment"),
        pe_var="snap_normal_allotment",
        monthly=True,
        spm=True,
        unsupported_input_keys=(
            "snap_max_allotment",
            "snap_expected_contribution",
            "snap_min_allotment",
            "is_snap_eligible",
        ),
        unsupported_input_reason=(
            "RuleSpec test supplies intermediate SNAP allotment inputs that "
            "PolicyEngine US does not expose as scenario inputs"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_expected_contribution",),
        pe_var="snap_expected_contribution",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_earned_income_deduction",),
        pe_var="snap_earned_income_deduction",
        monthly=True,
        spm=True,
        direct_spm_overrides=(("snap_earned_income", "snap_earned_income"),),
        derived_spm_overrides=(
            (
                "snap_earned_income",
                "difference_floor_zero",
                (
                    "snap_earned_income_before_exclusions",
                    "snap_child_earned_income_exclusion",
                    "snap_other_earned_income_exclusions",
                    "snap_work_support_public_assistance_income",
                ),
            ),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_min_allotment", "minimum_allotment"),
        pe_var="snap_min_allotment",
        monthly=True,
        spm=True,
        unsupported_input_keys=("snap_one_person_thrifty_food_plan_cost",),
        unsupported_input_patterns=("thrifty_food_plan_cost",),
        unsupported_input_reason=(
            "RuleSpec test supplies a thrifty-food-plan cost input that "
            "PolicyEngine US treats as an internal parameter, not a scenario input"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_net_income", "snap_net_income_calculation"),
        pe_var="snap_net_income",
        monthly=True,
        spm=True,
        direct_spm_overrides=(
            ("snap_gross_income", "snap_gross_income"),
            ("snap_earned_income", "snap_earned_income"),
            ("snap_standard_deduction", "snap_standard_deduction"),
            ("snap_earned_income_deduction", "snap_earned_income_deduction"),
            ("snap_child_support_deduction", "snap_child_support_deduction"),
            (
                "snap_excess_medical_expense_deduction",
                "snap_excess_medical_expense_deduction",
            ),
            (
                "snap_excess_shelter_expense_deduction",
                "snap_excess_shelter_expense_deduction",
            ),
            ("snap_utility_allowance_type", "snap_utility_allowance_type"),
        ),
        derived_spm_overrides=(
            (
                "snap_net_income",
                "difference",
                ("snap_household_income", "snap_deductions"),
            ),
        ),
        annual_derived_spm_overrides=(
            ("housing_cost", "monthly_to_annual", ("housing_cost",)),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_net_income_pre_shelter",),
        pe_var="snap_net_income_pre_shelter",
        monthly=True,
        spm=True,
        direct_spm_overrides=(
            (
                "snap_monthly_household_income_after_all_other_applicable_deductions",
                "snap_net_income_pre_shelter",
            ),
            (
                "snap_monthly_household_income_after_all_other_applicable_deductions_have_been_allowed",
                "snap_net_income_pre_shelter",
            ),
            (
                "snap_household_income_after_all_other_applicable_deductions",
                "snap_net_income_pre_shelter",
            ),
            (
                "snap_household_income_after_all_other_applicable_deductions_have_been_allowed",
                "snap_net_income_pre_shelter",
            ),
            (
                "snap_income_after_all_other_applicable_deductions",
                "snap_net_income_pre_shelter",
            ),
            (
                "snap_income_after_all_other_applicable_deductions_have_been_allowed",
                "snap_net_income_pre_shelter",
            ),
            ("snap_gross_income", "snap_gross_income"),
            ("snap_earned_income", "snap_earned_income"),
            ("snap_standard_deduction", "snap_standard_deduction"),
            ("snap_earned_income_deduction", "snap_earned_income_deduction"),
            ("snap_child_support_deduction", "snap_child_support_deduction"),
            (
                "snap_excess_medical_expense_deduction",
                "snap_excess_medical_expense_deduction",
            ),
            ("snap_utility_allowance_type", "snap_utility_allowance_type"),
        ),
        derived_spm_overrides=(
            (
                "snap_earned_income",
                "difference_floor_zero",
                (
                    "snap_earned_income_before_exclusions",
                    "snap_child_earned_income_exclusion",
                    "snap_other_earned_income_exclusions",
                    "snap_work_support_public_assistance_income",
                ),
            ),
        ),
        annual_derived_spm_overrides=(
            (
                "spm_unit_pre_subsidy_childcare_expenses",
                "difference_floor_zero_annualized",
                (
                    "snap_dependent_care_actual_costs",
                    "snap_dependent_care_excluded_expenses",
                ),
            ),
            (
                "spm_unit_pre_subsidy_childcare_expenses",
                "monthly_to_annual",
                ("snap_dependent_care_deduction",),
            ),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_standard_utility_allowance",),
        pe_var="snap_standard_utility_allowance",
        monthly=True,
        spm=True,
        direct_spm_overrides=(
            ("snap_utility_allowance_type", "snap_utility_allowance_type"),
            ("spm_unit_size", "spm_unit_size"),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_limited_utility_allowance",),
        pe_var="snap_limited_utility_allowance",
        monthly=True,
        spm=True,
        direct_spm_overrides=(
            ("snap_utility_allowance_type", "snap_utility_allowance_type"),
            ("spm_unit_size", "spm_unit_size"),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_individual_utility_allowance",),
        pe_var="snap_individual_utility_allowance",
        monthly=True,
        spm=True,
        direct_spm_overrides=(
            ("snap_utility_allowance_type", "snap_utility_allowance_type"),
            ("spm_unit_size", "spm_unit_size"),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_state_using_standard_utility_allowance",),
        pe_var="snap_state_using_standard_utility_allowance",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_state_uses_child_support_deduction",),
        pe_var="snap_state_uses_child_support_deduction",
        default_state_code="TN",
        parameter_path="gov.usda.snap.income.deductions.child_support",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_self_employment_expense_based_deduction_applies",),
        pe_var="snap_self_employment_expense_based_deduction_applies",
        default_state_code="CA",
        parameter_path=(
            "gov.usda.snap.income.deductions.self_employment."
            "expense_based_deduction_applies"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_self_employment_simplified_deduction_rate",),
        pe_var="snap_self_employment_simplified_deduction_rate",
        default_state_code="MD",
        parameter_path="gov.usda.snap.income.deductions.self_employment.rate",
        parameter_value_mode="float",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_standard_medical_expense_deduction",),
        pe_var="snap_standard_medical_expense_deduction",
        parameter_path="gov.usda.snap.income.deductions.excess_medical_expense.standard",
        parameter_value_mode="float",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_homeless_shelter_deduction_available",),
        pe_var="snap_homeless_shelter_deduction_available",
        parameter_path=(
            "gov.usda.snap.income.deductions.excess_shelter_expense.homeless.available"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_tanf_non_cash_gross_income_limit_fpg_ratio",),
        pe_var="snap_tanf_non_cash_gross_income_limit_fpg_ratio",
        default_state_code="TX",
        parameter_path="gov.hhs.tanf.non_cash.income_limit.gross",
        parameter_value_mode="float",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_tanf_non_cash_asset_limit",),
        pe_var="snap_tanf_non_cash_asset_limit",
        default_state_code="TX",
        parameter_path="gov.hhs.tanf.non_cash.asset_limit",
        parameter_value_mode="float",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("meets_snap_asset_test",),
        pe_var="meets_snap_asset_test",
        monthly=True,
        spm=True,
        annual_direct_spm_overrides=(
            ("snap_assets", "snap_assets"),
            ("snap_countable_resources", "snap_assets"),
            ("snap_countable_financial_resources", "snap_assets"),
            ("snap_financial_resources", "snap_assets"),
            (
                "snap_household_has_elderly_or_disabled_member",
                "has_usda_elderly_disabled",
            ),
        ),
        annual_derived_spm_overrides=(
            (
                "snap_assets",
                "difference",
                (
                    "snap_total_resources_before_exclusions",
                    "snap_mandatory_retirement_account_resource_exclusion",
                    "snap_discretionary_retirement_account_resource_exclusion",
                    "snap_mandatory_education_account_resource_exclusion",
                    "snap_discretionary_education_account_resource_exclusion",
                    "snap_other_resource_exclusions_under_g",
                ),
            ),
        ),
        unsupported_input_keys=(
            "snap_statutory_asset_limit",
            "snap_applicable_asset_limit",
            "snap_asset_limit",
            "snap_asset_limit_with_elderly_or_disabled_member",
        ),
        unsupported_input_reason=(
            "RuleSpec test restates the SNAP asset-test threshold with local "
            "limit/resource abstractions that PolicyEngine US does not expose "
            "as scenario inputs"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("meets_snap_gross_income_test",),
        pe_var="meets_snap_gross_income_test",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("meets_snap_net_income_test",),
        pe_var="meets_snap_net_income_test",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("meets_snap_categorical_eligibility",),
        pe_var="meets_snap_categorical_eligibility",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_snap_eligible",),
        pe_var="is_snap_eligible",
        monthly=True,
        spm=True,
        boolean_person_inputs=(
            ("is_snap_ineligible_student", "is_snap_ineligible_student"),
        ),
        monthly_boolean_person_inputs=(
            (
                "is_snap_immigration_status_eligible",
                "is_snap_immigration_status_eligible",
            ),
        ),
        direct_spm_overrides=(
            ("meets_snap_gross_income_test", "meets_snap_gross_income_test"),
            ("meets_snap_net_income_test", "meets_snap_net_income_test"),
            ("meets_snap_asset_test", "meets_snap_asset_test"),
            (
                "meets_snap_categorical_eligibility",
                "meets_snap_categorical_eligibility",
            ),
            ("meets_snap_work_requirements", "meets_snap_work_requirements"),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_standard_deduction",),
        pe_var="snap_standard_deduction",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_fpg",),
        pe_var="snap_fpg",
        monthly=True,
        spm=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("monthly_state_median_income_85_limit",),
        pe_var="co_ccap_smi",
        monthly=True,
        spm=True,
        annual_direct_spm_overrides=(("family_size", "spm_unit_size"),),
        default_state_code="CO",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("ma_tafdc_payment_standard",),
        pe_var="ma_tafdc_payment_standard",
        monthly=True,
        spm=True,
        annual_direct_spm_overrides=(("assistance_unit_size", "spm_unit_size"),),
        annual_inverted_boolean_household_overrides=(
            ("assistance_unit_has_rent_allowance", "is_in_public_housing"),
        ),
        default_state_code="MA",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("ut_fep_payment_standard",),
        pe_var="ut_fep_payment_standard",
        monthly=True,
        spm=True,
        annual_direct_spm_overrides=(("assistance_unit_size", "spm_unit_size"),),
        default_state_code="UT",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("ma_tafdc_infant_benefit",),
        pe_var="ma_tafdc_infant_benefit",
        boolean_person_inputs=(
            (
                "payment_requested_within_six_months_following_birth_of_eligible_infant",
                "ma_tafdc_eligible_infant",
            ),
        ),
        unsupported_falsy_input_keys=(
            "infant_equipment_not_available_from_any_other_source",
            "crib_or_mattress_requested_for_newborn_infant",
            "layette_requested_for_newborn_infant",
        ),
        unsupported_input_reason=(
            "PolicyEngine Massachusetts TAFDC infant benefit models a flat "
            "per-infant payment and does not expose the 106 CMR 705.600 "
            "equipment-source or component-request conditions"
        ),
        default_state_code="MA",
        target_person_role="child",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("oap_authorized_grant_payment_for_month",),
        pe_var="co_oap",
        default_state_code="CO",
        annualized_person_inputs=(
            ("client_total_countable_income_for_oap", "ssi_countable_income"),
        ),
        boolean_person_inputs=(
            (
                "client_is_oap_eligible_under_sections_3_520_6_and_3_520_7",
                "co_oap_eligible",
            ),
        ),
        unsupported_truthy_input_keys=(
            "client_is_inmate_in_penal_institution",
            "client_is_resident_in_unlicensed_or_uncertified_facility",
        ),
        unsupported_input_reason=(
            "PolicyEngine Colorado OAP does not model these 3.532 grant-payment "
            "exclusion facts"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=(
            "and_cs_authorized_grant_payment",
            "and_cs_authorized_grant_payment_for_month",
            "and_cs_grant_payment_for_month",
            "and_cs_monthly_grant_payment",
        ),
        pe_var="co_state_supplement",
        monthly=True,
        default_state_code="CO",
        annualized_person_inputs=(
            (
                "client_countable_income_other_than_ssi_for_and_cs",
                "ssi_countable_income",
            ),
            ("client_total_countable_income_for_and_cs", "ssi_countable_income"),
            ("and_cs_total_countable_income", "ssi_countable_income"),
            ("client_countable_income_for_and_cs", "ssi_countable_income"),
        ),
        monthly_person_inputs=(
            ("ssi_payment_received_amount", "ssi"),
            ("gross_ssi_payment_amount", "ssi"),
            ("client_ssi_payment_amount_for_and_cs", "ssi"),
            ("and_cs_ssi_payment_amount", "ssi"),
        ),
        boolean_person_inputs=(
            (
                "client_has_been_found_eligible_for_and_cs",
                "is_ssi_eligible_individual",
            ),
            ("client_has_been_found_eligible_for_and_cs", "is_ssi_disabled"),
            (
                "and_cs_client_eligible_for_grant_payment",
                "is_ssi_eligible_individual",
            ),
            ("and_cs_client_eligible_for_grant_payment", "is_ssi_disabled"),
            (
                "client_has_been_found_eligible_for_and_cs",
                "co_state_supplement_eligible",
            ),
            (
                "and_cs_client_eligible_for_grant_payment",
                "co_state_supplement_eligible",
            ),
            (
                "client_is_and_cs_eligible_under_sections_3_546_and_3_547",
                "co_state_supplement_eligible",
            ),
            (
                "client_is_and_cs_eligible_under_sections_3_546_and_3_547",
                "is_ssi_eligible_individual",
            ),
            (
                "client_is_and_cs_eligible_under_sections_3_546_and_3_547",
                "is_ssi_disabled",
            ),
            (
                "and_cs_client_eligible_for_grant_payments_under_3_548",
                "co_state_supplement_eligible",
            ),
            (
                "and_cs_client_eligible_for_grant_payments_under_3_548",
                "is_ssi_eligible_individual",
            ),
            (
                "and_cs_client_eligible_for_grant_payments_under_3_548",
                "is_ssi_disabled",
            ),
            ("and_cs_client_eligible", "co_state_supplement_eligible"),
            ("and_cs_client_eligible", "is_ssi_eligible_individual"),
            ("and_cs_client_eligible", "is_ssi_disabled"),
        ),
        unsupported_truthy_input_keys=(
            "client_is_inmate_in_penal_institution",
            "client_is_resident_in_unlicensed_or_uncertified_facility",
        ),
        unsupported_input_reason=(
            "PolicyEngine Colorado SSP does not model these 3.548 grant-payment "
            "exclusion facts"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("mfip_cash_portion_issued_as_cash",),
        pe_var="mn_mfip",
        monthly=True,
        spm=True,
        default_state_code="MN",
        direct_spm_overrides=(
            (
                "transitional_standard_for_corresponding_payment_month",
                "mn_mfip_full_transitional_standard",
            ),
            (
                "family_wage_level_for_corresponding_payment_month",
                "mn_mfip_family_wage_level",
            ),
            (
                "net_earned_income_in_budget_month",
                "mn_mfip_countable_earned_income",
            ),
            (
                "unearned_income_in_budget_month",
                "mn_mfip_countable_unearned_income",
            ),
            (
                "mfip_food_portion_amount_under_section_0020_09",
                "mn_mfip_food_portion",
            ),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("ca_capi",),
        pe_var="ca_capi",
        default_state_code="CA",
        derived_person_inputs=(
            (
                "ssi_amount_if_eligible",
                "difference",
                (
                    "ssi_ssp_payment_standard_for_selected_individual_living_arrangement",
                    "ssi_ssp_payment_standard_for_selected_individual_living_arrangement",
                ),
            ),
            (
                "ca_capi_eligible_person",
                "positive_if_any",
                (
                    "ssi_ssp_payment_standard_for_selected_individual_living_arrangement",
                    "ssi_ssp_payment_standard_for_selected_eligible_couple_living_arrangement",
                ),
            ),
        ),
        direct_person_inputs=(
            (
                "ca_capi_countable_income_for_payment_month_under_retrospective_accounting",
                "ssi_countable_income",
            ),
        ),
        direct_spm_overrides=(
            ("person_is_member_of_eligible_couple", "spm_unit_is_married"),
        ),
        derived_spm_overrides=(
            (
                "ca_state_supplement",
                "choose_second_if_third_truthy_else_first",
                (
                    "ssi_ssp_payment_standard_for_selected_individual_living_arrangement",
                    "ssi_ssp_payment_standard_for_selected_eligible_couple_living_arrangement",
                    "person_is_member_of_eligible_couple",
                ),
            ),
            (
                "ca_capi_eligible",
                "positive_if_any",
                (
                    "ssi_ssp_payment_standard_for_selected_individual_living_arrangement",
                    "ssi_ssp_payment_standard_for_selected_eligible_couple_living_arrangement",
                ),
            ),
        ),
        unsupported_truthy_input_keys=(
            "person_is_member_of_eligible_couple",
            "couple_one_member_receiving_or_applying_for_capi_and_other_receiving_ssi_ssp",
            "each_member_of_eligible_couple_receives_capi",
        ),
        unsupported_input_reason=(
            "PolicyEngine California CAPI exposes the SPM-unit total and does "
            "not directly compare the person-level eligible-couple share or "
            "mixed CAPI/SSI-SSP couple branch"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("il_aabd_personal_allowance",),
        pe_var="il_aabd_personal_allowance",
        monthly=True,
        spm=True,
        default_state_code="IL",
        direct_spm_overrides=(("persons_eating_together_count", "spm_unit_size"),),
        monthly_boolean_person_inputs=(("client_is_bedfast", "il_aabd_is_bedfast"),),
        projectable_input_keys=("client_is_active",),
        unsupported_truthy_input_keys=("client_is_in_long_term_care",),
        unsupported_input_reason=(
            "PolicyEngine Illinois AABD personal allowance does not model the "
            "DHS long-term-care personal allowance branch"
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_excess_shelter_deduction",),
        pe_var="snap_excess_shelter_expense_deduction",
        monthly=True,
        spm=True,
        direct_spm_overrides=(
            ("snap_gross_income", "snap_gross_income"),
            ("snap_earned_income", "snap_earned_income"),
            ("snap_standard_deduction", "snap_standard_deduction"),
            ("snap_earned_income_deduction", "snap_earned_income_deduction"),
            ("snap_child_support_deduction", "snap_child_support_deduction"),
            (
                "snap_excess_medical_expense_deduction",
                "snap_excess_medical_expense_deduction",
            ),
            ("snap_utility_allowance_type", "snap_utility_allowance_type"),
        ),
        derived_spm_overrides=(
            (
                "snap_earned_income",
                "difference_floor_zero",
                (
                    "snap_earned_income_before_exclusions",
                    "snap_child_earned_income_exclusion",
                    "snap_other_earned_income_exclusions",
                    "snap_work_support_public_assistance_income",
                ),
            ),
        ),
        annual_direct_spm_overrides=(
            (
                "snap_household_has_elderly_or_disabled_member",
                "has_usda_elderly_disabled",
            ),
            ("has_usda_elderly_disabled", "has_usda_elderly_disabled"),
        ),
        annual_derived_spm_overrides=(
            ("housing_cost", "monthly_to_annual", ("housing_cost",)),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_child_support_deduction",),
        pe_var="snap_child_support_gross_income_deduction",
        monthly=True,
        spm=True,
        annualized_person_inputs=(
            ("snap_child_support_payments_made", "child_support_expense"),
        ),
        state_code_from_boolean_input=(
            "snap_state_uses_child_support_deduction",
            "TX",
            "CA",
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_excess_medical_expense_deduction",),
        pe_var="snap_excess_medical_expense_deduction",
        monthly=True,
        spm=True,
        annualized_person_inputs=(
            (
                "snap_allowable_medical_expenses_before_threshold",
                "medical_out_of_pocket_expenses",
            ),
        ),
        boolean_person_inputs=(
            (
                "snap_household_has_elderly_or_disabled_member",
                "is_usda_disabled",
            ),
        ),
        default_state_code="NY",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("snap_maximum_allotment",),
        pe_var="snap_max_allotment",
        monthly=True,
        spm=True,
    ),
)

PE_US_MEDICAID_VAR_ADAPTERS = (
    PolicyEngineUSVarAdapter(
        rule_names=("is_medicaid_eligible",),
        pe_var="is_medicaid_eligible",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_emergency_medicaid_eligible",),
        pe_var="is_emergency_medicaid_eligible",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("medicaid_income_level",),
        pe_var="medicaid_income_level",
        entity="person",
        period="year",
        unit="/1",
        comparison="rate",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("medicaid",),
        pe_var="medicaid",
        entity="person",
        period="year",
        unit="USD",
        comparison="money",
    ),
)

PE_US_CHIP_VAR_ADAPTERS = (
    PolicyEngineUSVarAdapter(
        rule_names=("is_chip_eligible",),
        pe_var="is_chip_eligible",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_chip_eligible_child",),
        pe_var="is_chip_eligible_child",
        entity="person",
        period="year",
        comparison="decision",
        direct_person_inputs=(("medicaid_income_level", "medicaid_income_level"),),
        boolean_person_inputs=(
            (
                "found_eligible_for_medical_assistance_under_subchapter_xix",
                "is_medicaid_eligible",
            ),
        ),
        boolean_enum_person_inputs=(
            (
                "person_meets_chip_immigration_requirement",
                "immigration_status",
                "CITIZEN",
                "UNDOCUMENTED",
            ),
        ),
        target_person_role="child",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_chip_eligible_pregnant",),
        pe_var="is_chip_eligible_pregnant",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_chip_eligible_standard_pregnant_person",),
        pe_var="is_chip_eligible_standard_pregnant_person",
        entity="person",
        period="year",
        comparison="decision",
        direct_person_inputs=(("medicaid_income_level", "medicaid_income_level"),),
        boolean_person_inputs=(
            ("person_is_pregnant", "is_pregnant"),
            (
                "found_eligible_for_medical_assistance_under_subchapter_xix",
                "is_medicaid_eligible",
            ),
        ),
        boolean_enum_person_inputs=(
            (
                "person_meets_chip_immigration_requirement",
                "immigration_status",
                "CITIZEN",
                "UNDOCUMENTED",
            ),
        ),
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_chip_fcep_eligible_person",),
        pe_var="is_chip_fcep_eligible_person",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("chip",),
        pe_var="chip",
        entity="person",
        period="year",
        unit="USD",
        comparison="money",
    ),
)

PE_US_ACA_PTC_VAR_ADAPTERS = (
    PolicyEngineUSVarAdapter(
        rule_names=("is_aca_ptc_eligible",),
        pe_var="is_aca_ptc_eligible",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("pays_aca_premium",),
        pe_var="pays_aca_premium",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("aca_ptc",),
        pe_var="aca_ptc",
        entity="tax_unit",
        period="year",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("premium_tax_credit",),
        pe_var="premium_tax_credit",
        entity="tax_unit",
        period="month",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("assigned_aca_ptc",),
        pe_var="assigned_aca_ptc",
        entity="tax_unit",
        period="year",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("used_aca_ptc",),
        pe_var="used_aca_ptc",
        entity="tax_unit",
        period="year",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("marketplace_net_premium",),
        pe_var="marketplace_net_premium",
        entity="tax_unit",
        period="year",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("aca_required_contribution_percentage",),
        pe_var="aca_required_contribution_percentage",
        entity="tax_unit",
        period="year",
        unit="/1",
        comparison="rate",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("aca_magi_fraction",),
        pe_var="aca_magi_fraction",
        entity="tax_unit",
        period="year",
        unit="/1",
        comparison="rate",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("slcsp",),
        pe_var="slcsp",
        entity="tax_unit",
        period="month",
        unit="USD",
        comparison="money",
    ),
)

PE_US_MEDICARE_VAR_ADAPTERS = (
    PolicyEngineUSVarAdapter(
        rule_names=("is_medicare_eligible",),
        pe_var="is_medicare_eligible",
        entity="person",
        period="year",
        comparison="decision",
        derived_person_inputs=(
            (
                "months_receiving_social_security_disability",
                "max",
                ("months_received_social_security_disability_benefits",),
            ),
            (
                "social_security_disability",
                "positive_if_any",
                ("months_received_social_security_disability_benefits",),
            ),
        ),
        unsupported_truthy_input_keys=(
            "enrolled_during_initial_enrollment_period",
            "coverage_month_is_month_after_enrollment",
            "months_of_disability_benefit_entitlement",
        ),
        unsupported_input_reason=(
            "PolicyEngine's Medicare eligibility oracle does not expose CMS "
            "enrollment-window coverage timing facts or the separate "
            "25th-month disability-entitlement boundary"
        ),
    ),
)

PE_US_HEALTH_VAR_ADAPTERS = (
    *PE_US_MEDICAID_VAR_ADAPTERS,
    *PE_US_CHIP_VAR_ADAPTERS,
    *PE_US_ACA_PTC_VAR_ADAPTERS,
    *PE_US_MEDICARE_VAR_ADAPTERS,
)

PE_US_SSI_VAR_ADAPTERS = (
    PolicyEngineUSVarAdapter(
        rule_names=("ssi", "ssi_payment", "ssi_payment_amount"),
        pe_var="ssi",
        entity="person",
        period="month",
        unit="USD",
        comparison="money",
        monthly=True,
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("ssi_countable_income",),
        pe_var="ssi_countable_income",
        entity="person",
        period="year",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("ssi_countable_resources",),
        pe_var="ssi_countable_resources",
        entity="person",
        period="year",
        unit="USD",
        comparison="money",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("is_ssi_eligible_individual",),
        pe_var="is_ssi_eligible_individual",
        entity="person",
        period="year",
        comparison="decision",
    ),
    PolicyEngineUSVarAdapter(
        rule_names=("expected_state_supplement_for_nursing_home_ssi_recipient",),
        pe_var="ga_ssp_person",
        entity="person",
        period="month",
        unit="USD",
        comparison="money",
        monthly=True,
        default_state_code="GA",
        monthly_derived_boolean_person_inputs=(
            (
                "ga_ssp_eligible_person",
                "all",
                (
                    "receives_ssi_only",
                    "month_following_nursing_home_admission",
                ),
            ),
        ),
    ),
)

PE_US_PROGRAM_VAR_ADAPTERS = {
    "snap": PE_US_VAR_ADAPTERS,
    "medicaid": PE_US_MEDICAID_VAR_ADAPTERS,
    "chip": PE_US_CHIP_VAR_ADAPTERS,
    "aca_ptc": PE_US_ACA_PTC_VAR_ADAPTERS,
    "medicare": PE_US_MEDICARE_VAR_ADAPTERS,
    "health": PE_US_HEALTH_VAR_ADAPTERS,
    "ssi": PE_US_SSI_VAR_ADAPTERS,
}

PE_US_ALL_VAR_ADAPTERS = (
    *PE_US_VAR_ADAPTERS,
    *PE_US_HEALTH_VAR_ADAPTERS,
    *PE_US_SSI_VAR_ADAPTERS,
)

PE_US_VAR_ADAPTERS_BY_NAME = {
    name: adapter
    for adapter in PE_US_ALL_VAR_ADAPTERS
    for name in (adapter.pe_var, *adapter.rule_names)
}

PE_US_MONTHLY_VAR_NAMES = {
    name
    for adapter in PE_US_ALL_VAR_ADAPTERS
    if adapter.monthly or adapter.period == "month"
    for name in (adapter.pe_var, *adapter.rule_names)
}

PE_US_SPM_VAR_NAMES = {
    name
    for adapter in PE_US_ALL_VAR_ADAPTERS
    if adapter.spm
    for name in (adapter.pe_var, *adapter.rule_names)
}


def get_pe_us_var_adapter(name: str) -> PolicyEngineUSVarAdapter | None:
    """Return a PE-US adapter row for a mapped PE variable or adapter alias."""
    return PE_US_VAR_ADAPTERS_BY_NAME.get(name)
