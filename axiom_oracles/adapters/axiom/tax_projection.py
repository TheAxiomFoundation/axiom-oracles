from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity
from .runner import (
    AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY,
    AXIOM_INPUT_RECORDS_METADATA_KEY,
    AXIOM_RELATIONS_METADATA_KEY,
    AXIOM_RESULT_SELECTION_METADATA_KEY,
)


AXIOM_TAX_UNIT_INPUTS_METADATA_KEY = "axiom_tax_unit_inputs"


def _generated_parameter_rule(
    name: str,
    *,
    dtype: str,
    source: str,
    formula: str,
    unit: str | None = None,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "name": name,
        "kind": "parameter",
        "dtype": dtype,
        "source": source,
        "versions": [
            {
                "effective_from": "2026-01-01",
                "formula": formula,
            }
        ],
    }
    if unit is not None:
        rule["unit"] = unit
    return rule


def _generated_tax_unit_rule(
    name: str,
    *,
    dtype: str,
    source: str,
    formula: str,
    unit: str | None = None,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "name": name,
        "kind": "derived",
        "entity": "TaxUnit",
        "dtype": dtype,
        "period": "Year",
        "source": source,
        "versions": [
            {
                "effective_from": "2026-01-01",
                "formula": formula,
            }
        ],
    }
    if unit is not None:
        rule["unit"] = unit
    return rule


def _generated_person_rule(
    name: str,
    *,
    dtype: str,
    source: str,
    formula: str,
    unit: str | None = None,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "name": name,
        "kind": "derived",
        "entity": "Person",
        "dtype": dtype,
        "period": "Year",
        "source": source,
        "versions": [
            {
                "effective_from": "2026-01-01",
                "formula": formula,
            }
        ],
    }
    if unit is not None:
        rule["unit"] = unit
    return rule


def _generated_data_relation_rule(name: str, *, source: str) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "data_relation",
        "source": source,
        "data_relation": {"arity": 2},
    }


US_FEDERAL_INCOME_TAX_IMPORTS = (
    "us:policies/irs/rev-proc-2025-32/child-tax-credit",
    "us:policies/irs/rev-proc-2025-32/standard-deduction",
    "us:statutes/26/1/j",
    "us:statutes/26/21",
    "us:statutes/26/22",
    "us:statutes/26/24/h",
    "us:statutes/26/25A",
    "us:statutes/26/25B",
    "us:statutes/26/26",
    "us:statutes/26/32",
    "us:statutes/26/55",
    "us:statutes/26/86",
    "us:statutes/26/163",
    "us:statutes/26/164/f",
    "us:statutes/26/1401",
    "us:statutes/26/1402/a",
    "us:statutes/26/1411",
    "us:statutes/26/3101/a",
    "us:statutes/26/3101/b/1",
    "us:statutes/26/3101/b/2",
    "us:statutes/26/6401",
)

US_FEDERAL_INCOME_TAX_BRIDGE_TARGET = "us:tax/federal-income-tax/oracle-bridge"

US_FEDERAL_INCOME_TAX_PROGRAM_RULES = (
    _generated_parameter_rule(
        "ctc_refundable_phase_in_rate",
        dtype="Rate",
        source="26 USC 24(d)(1)(B)(i)",
        formula="0.15",
    ),
    _generated_parameter_rule(
        "ctc_refundable_min_children_for_ss_excess",
        dtype="Integer",
        source="26 USC 24(d)(1)(B)(ii)",
        formula="3",
    ),
    _generated_parameter_rule(
        "ctc_social_security_half_share",
        dtype="Rate",
        source="26 USC 24(d)(2)(A)(ii)-(iii)",
        formula="0.50",
    ),
    _generated_parameter_rule(
        "additional_senior_deduction_amount",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70103",
        formula="6000",
    ),
    _generated_parameter_rule(
        "additional_senior_deduction_phaseout_rate",
        dtype="Rate",
        source="H.R.1 (119th Congress), section 70103",
        formula="0.06",
    ),
    _generated_parameter_rule(
        "additional_senior_deduction_joint_threshold",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70103",
        formula="150000",
    ),
    _generated_parameter_rule(
        "additional_senior_deduction_other_threshold",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70103",
        formula="75000",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_rate",
        dtype="Rate",
        source="26 USC 199A(a)(2)",
        formula="0.20",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_phaseout_joint_start",
        dtype="Money",
        unit="USD",
        source="Rev. Proc. 2025-32 section 3.27; 26 USC 199A(e)(2)",
        formula="403500",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_phaseout_other_start",
        dtype="Money",
        unit="USD",
        source="Rev. Proc. 2025-32 section 3.27; 26 USC 199A(e)(2)",
        formula="201750",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_phaseout_joint_length",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70105; 26 USC 199A(b)(3)(B)",
        formula="150000",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_phaseout_other_length",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70105; 26 USC 199A(b)(3)(B)",
        formula="75000",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_floor_threshold",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70105",
        formula="1000",
    ),
    _generated_parameter_rule(
        "qualified_business_income_deduction_floor_amount",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70105",
        formula="400",
    ),
    _generated_tax_unit_rule(
        "ctc_refundable_phase_in_threshold",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 24(h)(6) to 26 USC 24(d)(1)(B)(i)",
        formula="ctc_refundable_phase_in_threshold_under_subsection_h",
    ),
    _generated_tax_unit_rule(
        "ctc_credit_without_subsection_and_26a_limit",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 24(h) to 26 USC 24(a)",
        formula=(
            "max("
            "0, "
            "ctc_maximum_before_phase_out_under_subsection_h "
            "- (50 * ceil(max(0, modified_adjusted_gross_income "
            "- ctc_phase_out_threshold_under_subsection_h) / 1000))"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_phase_in_earned_income_base",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(1)(B)(i)",
        formula=(
            "taxable_earned_income_under_section_32 "
            "+ amount_excluded_from_gross_income_under_section_112"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_phase_in_relevant_earnings",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 24(h)(6) to 26 USC 24(d)(1)(B)(i)",
        formula=(
            "ctc_refundable_phase_in_rate "
            "* max(0, ctc_phase_in_earned_income_base "
            "- ctc_refundable_phase_in_threshold)"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_social_security_tax",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(2)",
        formula=(
            "max("
            "0, "
            "employee_3101_3201a_taxes "
            "+ american_employer_foreign_affiliate_equivalent_3121l_taxes "
            "+ (ctc_social_security_half_share * self_employment_1401_taxes) "
            "+ (ctc_social_security_half_share * railroad_3211a_taxes) "
            "- special_refund_social_security_taxes_under_6413c"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_social_security_excess",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(1)(B)(ii)",
        formula=(
            "if qualifying_children_count >= ctc_refundable_min_children_for_ss_excess: "
            "max(0, ctc_social_security_tax - eitc) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_refundable_limitation_increase_amount",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(1)(B)",
        formula="max(ctc_phase_in_relevant_earnings, ctc_social_security_excess)",
    ),
    _generated_tax_unit_rule(
        "aggregate_subpart_c_credits_without_subsection",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge resolving the section 26(a) CTC limit",
        formula=(
            "min("
            "ctc_credit_without_subsection_and_26a_limit, "
            "income_tax_before_credits"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "aggregate_subpart_c_credits_with_increased_26a_limit",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge resolving the section 24(d) refundability limit",
        formula=(
            "min("
            "ctc_credit_without_subsection_and_26a_limit, "
            "income_tax_before_credits + ctc_refundable_limitation_increase_amount"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_refundable_tax_increase",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(1)(B)",
        formula=(
            "max("
            "0, "
            "aggregate_subpart_c_credits_with_increased_26a_limit "
            "- aggregate_subpart_c_credits_without_subsection"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "ctc_refundable_cap",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(1)(A), resolved through 26 USC 24(h)",
        formula="ctc_credit_without_subsection_and_26a_limit",
    ),
    _generated_tax_unit_rule(
        "ctc_refundable_foreign_income_eligible",
        dtype="Judgment",
        source="26 USC 24(d)(3)",
        formula="not elects_foreign_earned_income_exclusion_under_911",
    ),
    _generated_tax_unit_rule(
        "refundable_ctc",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 24(h) to 26 USC 24(d)(1)",
        formula=(
            "if ctc_refundable_foreign_income_eligible: "
            "min("
            "ctc_refundable_cap, "
            "min(ctc_refundable_limitation_increase_amount, ctc_refundable_tax_increase)"
            ") "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "non_refundable_ctc",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(1), resolved through 26 USC 24(h)",
        formula="max(0, ctc_credit_without_subsection_and_26a_limit - refundable_ctc)",
    ),
    _generated_tax_unit_rule(
        "ctc_value",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine's realized CTC value",
        formula=(
            "min("
            "ctc_credit_without_subsection_and_26a_limit, "
            "ctc_refundable_limitation_increase_amount"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "self_employment_income",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 1402(a) before 26 USC 1401",
        formula="max(0, net_earnings_from_self_employment)",
    ),
    _generated_tax_unit_rule(
        "self_employment_1401_taxes",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge exposing 26 USC 1401(a) and (b)(1) taxes for 26 USC 24(d)(2)",
        formula="self_employment_oasdi_tax + self_employment_hospital_insurance_tax",
    ),
    _generated_tax_unit_rule(
        "self_employment_tax_ald",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge exposing 26 USC 164(f) above-the-line deduction",
        formula="self_employment_tax_deduction",
    ),
    _generated_tax_unit_rule(
        "taxable_earned_income_under_section_32",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 164(f) to earned income used by 26 USC 24(d)",
        formula=(
            "wages "
            "+ net_earnings_before_paragraph_12_adjustment "
            "- self_employment_tax_deduction"
        ),
    ),
    _generated_tax_unit_rule(
        "earned_income",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge using 26 USC 32 earned income after self-employment tax adjustment",
        formula="taxable_earned_income_under_section_32",
    ),
    _generated_tax_unit_rule(
        "filer_adjusted_earnings",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine adjusted earnings from leaf income facts",
        formula="taxable_earned_income_under_section_32",
    ),
    _generated_tax_unit_rule(
        "additional_senior_deduction_eligible_count",
        dtype="Integer",
        source="Oracle composition bridge applying H.R.1 section 70103 age and filing-status eligibility",
        formula=(
            "(if taxpayer_has_attained_age_65_before_close_of_taxable_year: 1 else: 0) "
            "+ (if spouse_has_attained_age_65_before_close_of_taxable_year "
            "and filing_status_is_joint_return: 1 else: 0)"
        ),
    ),
    _generated_tax_unit_rule(
        "additional_senior_deduction_magi",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge using adjusted gross income for H.R.1 section 70103 phaseout",
        formula="adjusted_gross_income",
    ),
    _generated_tax_unit_rule(
        "additional_senior_deduction_phaseout_threshold",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying H.R.1 section 70103 filing-status thresholds",
        formula=(
            "if filing_status_is_joint_return: "
            "additional_senior_deduction_joint_threshold "
            "else: additional_senior_deduction_other_threshold"
        ),
    ),
    _generated_tax_unit_rule(
        "additional_senior_deduction_phaseout_amount",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying H.R.1 section 70103 phaseout",
        formula=(
            "max(0, additional_senior_deduction_magi "
            "- additional_senior_deduction_phaseout_threshold) "
            "* additional_senior_deduction_phaseout_rate"
        ),
    ),
    _generated_tax_unit_rule(
        "additional_senior_deduction",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying H.R.1 section 70103 senior deduction",
        formula=(
            "max("
            "0, "
            "additional_senior_deduction_amount "
            "- additional_senior_deduction_phaseout_amount"
            ") * additional_senior_deduction_eligible_count"
        ),
    ),
    _generated_data_relation_rule(
        "business_income_of_tax_unit",
        source="Oracle comparison bridge relating tax-unit filers to person-level 26 USC 199A income leaves",
    ),
    _generated_person_rule(
        "business_income_for_qbid",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine person-level 26 USC 199A QBI aggregation",
        formula=(
            "max("
            "0, "
            "person_self_employment_income_for_qbid "
            "+ person_rental_income_for_qbid"
            ")"
        ),
    ),
    _generated_person_rule(
        "business_income_counts_for_qbid",
        dtype="Judgment",
        source="Oracle comparison bridge matching PolicyEngine positive person-level QBI aggregation",
        formula="business_income_for_qbid > 0",
    ),
    _generated_tax_unit_rule(
        "qualified_business_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 199A(c) to ECPS self-employment and rental income leaves",
        formula=(
            "max("
            "0, "
            "sum_where("
            "business_income_of_tax_unit, "
            "business_income_for_qbid, "
            "business_income_counts_for_qbid"
            ") - self_employment_tax_deduction"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "adjusted_net_capital_gain_for_qbid",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge approximating 26 USC 199A(a)(2) capital-gain cap from ECPS leaves",
        formula="max(0, long_term_capital_gains + qualified_dividend_income)",
    ),
    _generated_tax_unit_rule(
        "amt_part_iii_required",
        dtype="Judgment",
        source="Oracle comparison bridge applying Form 6251 Part III when preferential gains are present",
        formula=(
            "adjusted_net_capital_gain > 0 "
            "or unrecaptured_section_1250_gain > 0 "
            "or capital_gains_28_percent_rate_gain > 0"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_adjusted_net_capital_gain_limited",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge limiting preferential gains for the AMT capital-gain worksheet",
        formula="min(adjusted_net_capital_gain, amt_income_less_exemptions)",
    ),
    _generated_tax_unit_rule(
        "amt_income_less_adjusted_net_capital_gain",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge computing non-preferential AMT income",
        formula=(
            "max(0, amt_income_less_exemptions "
            "- amt_adjusted_net_capital_gain_limited)"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_ordinary_income_tax_under_amt_rates",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 55 AMT rates to non-preferential AMT income",
        formula=(
            "amt_lower_rate "
            "* min("
            "amt_income_less_adjusted_net_capital_gain, "
            "amt_twenty_eight_percent_threshold"
            ") "
            "+ amt_higher_rate "
            "* max("
            "0, "
            "amt_income_less_adjusted_net_capital_gain "
            "- amt_twenty_eight_percent_threshold"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gains_in_zero_rate_bracket",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1(h) preferential brackets inside AMT",
        formula=(
            "max("
            "0, "
            "min(max(amt_income_less_exemptions, 0), capital_gains_zero_rate_threshold) "
            "- amt_income_less_adjusted_net_capital_gain"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gains_in_fifteen_percent_bracket",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1(h) preferential brackets inside AMT",
        formula=(
            "min("
            "max("
            "0, "
            "amt_adjusted_net_capital_gain_limited "
            "- amt_capital_gains_in_zero_rate_bracket"
            "), "
            "max("
            "0, "
            "min("
            "max(amt_income_less_exemptions, 0), "
            "capital_gains_fifteen_percent_threshold"
            ") "
            "- (amt_income_less_adjusted_net_capital_gain "
            "+ amt_capital_gains_in_zero_rate_bracket)"
            ")"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gains_in_twenty_percent_bracket",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1(h) preferential brackets inside AMT",
        formula=(
            "max("
            "0, "
            "amt_adjusted_net_capital_gain_limited "
            "- amt_capital_gains_in_zero_rate_bracket "
            "- amt_capital_gains_in_fifteen_percent_bracket"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_tax_including_capital_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge computing Form 6251 Part III preferential-gain tax",
        formula=(
            "amt_ordinary_income_tax_under_amt_rates "
            "+ capital_gains_zero_rate "
            "* amt_capital_gains_in_zero_rate_bracket "
            "+ capital_gains_fifteen_percent_rate "
            "* amt_capital_gains_in_fifteen_percent_bracket "
            "+ capital_gains_twenty_percent_rate "
            "* amt_capital_gains_in_twenty_percent_bracket "
            "+ unrecaptured_section_1250_gain_rate "
            "* unrecaptured_section_1250_gain "
            "+ capital_gains_28_percent_rate "
            "* capital_gains_28_percent_rate_gain"
        ),
    ),
    _generated_tax_unit_rule(
        "current_law_deductions_before_qbid_if_not_itemizing",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge for 2026 federal income tax deductions before 26 USC 199A",
        formula=(
            "standard_deduction "
            "+ deduction_for_personal_exemptions_provided_in_section_151 "
            "+ deduction_provided_in_section_170_p "
            "+ deduction_provided_in_section_224 "
            "+ deduction_provided_in_section_225 "
            "+ qualified_passenger_vehicle_loan_interest_deduction "
            "+ additional_senior_deduction"
        ),
    ),
    _generated_tax_unit_rule(
        "current_law_deductions_before_qbid_if_itemizing",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge for 2026 federal income tax deductions before 26 USC 199A",
        formula=(
            "itemized_taxable_income_deductions "
            "+ deduction_provided_in_section_224 "
            "+ deduction_provided_in_section_225 "
            "+ wagering_losses_deduction "
            "+ qualified_passenger_vehicle_loan_interest_deduction "
            "+ additional_senior_deduction"
        ),
    ),
    _generated_tax_unit_rule(
        "taxable_income_less_qbid",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching 26 USC 199A taxable-income cap ordering",
        formula=(
            "if individual_who_does_not_elect_to_itemize_deductions_for_taxable_year: "
            "max(0, adjusted_gross_income - current_law_deductions_before_qbid_if_not_itemizing) "
            "else: max(0, gross_income - current_law_deductions_before_qbid_if_itemizing)"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_business_income_deduction_phaseout_start",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge selecting 2026 26 USC 199A(e)(2) threshold by filing status",
        formula=(
            "if filing_status == 1: "
            "qualified_business_income_deduction_phaseout_joint_start "
            "else: qualified_business_income_deduction_phaseout_other_start"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_business_income_deduction_phaseout_length",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge selecting 26 USC 199A(b)(3)(B) phaseout range by filing status",
        formula=(
            "if filing_status == 1: "
            "qualified_business_income_deduction_phaseout_joint_length "
            "else: qualified_business_income_deduction_phaseout_other_length"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_business_income_deduction_phaseout_rate",
        dtype="Rate",
        source="Oracle comparison bridge applying 26 USC 199A(b)(3)(B) phaseout for missing W-2/UBIA leaves",
        formula=(
            "min("
            "1, "
            "max("
            "0, "
            "taxable_income_less_qbid "
            "- qualified_business_income_deduction_phaseout_start"
            ") / qualified_business_income_deduction_phaseout_length"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_business_income_deduction_before_floor",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 199A(a)(2) rate and taxable-income cap",
        formula=(
            "min("
            "qualified_business_income_deduction_rate "
            "* qualified_business_income "
            "* (1 - qualified_business_income_deduction_phaseout_rate), "
            "qualified_business_income_deduction_rate "
            "* max(0, taxable_income_less_qbid - adjusted_net_capital_gain_for_qbid)"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_business_income_deduction_floor",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying H.R.1 section 70105 qualified business income deduction floor",
        formula=(
            "if qualified_business_income >= qualified_business_income_deduction_floor_threshold: "
            "qualified_business_income_deduction_floor_amount "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_business_income_deduction",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 199A to ECPS leaf inputs",
        formula=(
            "max("
            "qualified_business_income_deduction_before_floor, "
            "qualified_business_income_deduction_floor"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "deduction_provided_in_section_199A",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge routing 26 USC 199A deduction into 26 USC 63",
        formula="qualified_business_income_deduction",
    ),
    _generated_tax_unit_rule(
        "gross_income_before_social_security_benefits",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge aggregating ECPS leaf income facts before applying 26 USC 86",
        formula=(
            "wages "
            "+ dividend_income "
            "+ taxable_interest_income "
            "+ short_term_capital_gains "
            "+ long_term_capital_gains "
            "+ rental_income "
            "+ pension_annuity_disability_benefits_received "
            "+ unemployment_compensation "
            "+ net_earnings_before_paragraph_12_adjustment"
        ),
    ),
    _generated_tax_unit_rule(
        "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge routing ECPS capital-gain leaves into 26 USC 1411(c)(1)(A)(iii)",
        formula="short_term_capital_gains + long_term_capital_gains",
    ),
    _generated_tax_unit_rule(
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 164(f) before 26 USC 86",
        formula=(
            "gross_income_before_social_security_benefits "
            "- self_employment_tax_deduction"
        ),
    ),
    _generated_tax_unit_rule(
        "adjusted_gross_income",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 86 to adjusted gross income before social security",
        formula=(
            "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933 "
            "+ social_security_benefits_included_in_gross_income"
        ),
    ),
    _generated_tax_unit_rule(
        "gross_income",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 86 to ECPS leaf income facts",
        formula="adjusted_gross_income",
    ),
    _generated_tax_unit_rule(
        "modified_adjusted_gross_income",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge using derived adjusted gross income where no imported modifier applies",
        formula="adjusted_gross_income",
    ),
    _generated_tax_unit_rule(
        "current_law_deductions_if_not_itemizing",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge for 2026 federal income tax deductions",
        formula=(
            "current_law_deductions_before_qbid_if_not_itemizing "
            "+ deduction_provided_in_section_199A "
        ),
    ),
    _generated_tax_unit_rule(
        "current_law_deductions_if_itemizing",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge for 2026 federal income tax deductions",
        formula=(
            "current_law_deductions_before_qbid_if_itemizing "
            "+ deduction_provided_in_section_199A "
        ),
    ),
    _generated_tax_unit_rule(
        "taxable_income_for_individual_who_does_not_itemize",
        dtype="Money",
        unit="USD",
        source="26 USC 63(b), resolved with 2026 current-law deduction modules",
        formula="adjusted_gross_income - current_law_deductions_if_not_itemizing",
    ),
    _generated_tax_unit_rule(
        "taxable_income_general_rule",
        dtype="Money",
        unit="USD",
        source="26 USC 63(a), resolved with 2026 current-law deduction modules",
        formula="gross_income - current_law_deductions_if_itemizing",
    ),
    _generated_tax_unit_rule(
        "taxable_income",
        dtype="Money",
        unit="USD",
        source="26 USC 63(a)-(b), resolved with 2026 current-law deduction modules",
        formula=(
            "if individual_who_does_not_elect_to_itemize_deductions_for_taxable_year: "
            "max(0, taxable_income_for_individual_who_does_not_itemize) "
            "else: max(0, taxable_income_general_rule)"
        ),
    ),
    _generated_tax_unit_rule(
        "credits_allowable_under_subpart_c_excluding_section_33_for_overpayment",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge aggregating refundable credits for 26 USC 6401(b)(1)",
        formula=(
            "eitc "
            "+ min("
            "refundable_ctc, "
            "ctc_refundable_child_amount "
            "* ctc_qualifying_children_under_subsection_h"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "tax_imposed_by_subtitle_a_reduced_by_subparts_a_b_d_and_g_credits",
        dtype="Money",
        unit="USD",
        source="26 USC 6401(b)(1), resolved through 26 USC 26(a)",
        formula="income_tax_before_refundable_credits",
    ),
    _generated_tax_unit_rule(
        "tax_unit_itemizes",
        dtype="Judgment",
        source="Oracle composition bridge from 26 USC 63(e) to 26 USC 55",
        formula="individual_makes_election_to_itemize_deductions_for_taxable_year",
    ),
)

_TAX_UNIT_ID = "tax_unit"
_AXIOM_TAX_REF_PREFIX = "us:tax/federal-income-tax"
_TAX_FILER_ADULT_AGE = 18
_STANDARD_DEDUCTION_OTHER_CASE_2026_AMOUNT = 16_100
_STANDARD_DEDUCTION_OTHER_CASE_AFTER_2017_BASE_AMOUNT = 15_750

_RELATION_REFS = (
    "us:tax/federal-income-tax/oracle-bridge#relation.business_income_of_tax_unit",
    "us:statutes/26/21#relation.qualifying_individual_of_tax_unit",
    "us:statutes/26/22#relation.taxpayer_or_spouse_of_tax_unit",
    "us:statutes/26/24/h#relation.dependent_of_tax_unit",
    "us:statutes/26/25A#relation.education_credit_member_of_tax_unit",
    "us:statutes/26/32#relation.qualifying_child_of_tax_unit",
)

_SPOUSE_RELATIONS = {
    "spouse",
    "wife",
    "husband",
    "partner",
    "marriedpartner",
    "married_partner",
}

_HEAD_RELATIONS = {
    "head",
    "headofhousehold",
    "head_of_household",
    "householder",
    "referenceperson",
    "reference_person",
    "self",
}

_DEPENDENT_RELATIONS = {
    "child",
    "daughter",
    "dependent",
    "foster_child",
    "grandchild",
    "son",
    "stepchild",
}

_BOOLEAN_DEFAULTS_FALSE = (
    "abode_relationship_violates_local_law",
    "amt_kiddie_tax_applies",
    "amt_part_iii_required",
    "aotc_disallowance_period_applies",
    "aotc_election_in_effect",
    "at_least_half_time_student",
    "completed_first_four_years_postsecondary_before_year",
    "credit_allowed_under_section_33_by_reason_of_section_1446",
    "deduction_under_section_151_allowable_to_another_taxpayer",
    "disability_proof_furnished",
    "education_credit_election_in_effect",
    "education_credit_identification_requirements_met",
    "elects_foreign_earned_income_exclusion_under_911",
    "estate_or_trust_common_trust_fund_or_partnership",
    "eitc_disallowance_period_applies",
    "excludes_foreign_earned_income",
    "expenses_paid_to_allowed_provider",
    "has_felony_drug_conviction",
    "indebtedness_incurred_after_2024_for_purchase_of_vehicle",
    "indebtedness_owed_to_related_person_under_section_267_b_or_707_b_1",
    "indebtedness_secured_by_first_lien_on_vehicle",
    "institution_employer_identification_number_included",
    "individual_makes_election_to_itemize_deductions_for_taxable_year",
    "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year",
    "is_dependent_under_section_152_a_1",
    "is_dependent_under_section_152_disregarding_listed_subsections",
    "is_incapable_of_self_care",
    "is_nonresident_alien",
    "is_spouse_of_taxpayer",
    "is_student_under_section_152_f_2",
    "joint_return_filed_for_spouse_distribution_year",
    "lease_financing",
    "loan_finances_fleet_sales",
    "loan_finances_vehicle_intended_for_scrap_or_parts",
    "loan_finances_vehicle_with_salvage_title",
    "loan_for_commercial_vehicle_not_used_for_personal_purposes",
    "married_individual_filing_separate_return_where_either_spouse_itemizes_deductions",
    "married_taxpayer_lived_apart_from_spouse_at_all_times_during_taxable_year",
    "meets_higher_education_act_student_requirements",
    "medically_determinable_impairment",
    "nonresident_alien_individual",
    "payee_statement_received",
    "provider_identification_requirements_met",
    "qualifying_individual_tin_included_on_return",
    "qualifying_individual_identification_requirements_met",
    "prior_deficiency_denial_without_required_eligibility_information",
    "retired_on_disability_before_year_end",
    "return_under_section_443_a_1_for_less_than_12_months_due_to_accounting_period_change",
    "satisfies_cdcc_married_living_apart_rules",
    "satisfies_eitc_separated_spouse_rules",
    "section_151_deduction_allowed_to_another_taxpayer",
    "section_152_e_non_custodial_parent",
    "section_6013_g_or_h_election_in_effect_for_taxable_year",
    "section_6013_resident_alien_election",
    "service_provider_identifying_information_requirement_satisfied",
    "spouses_lived_apart_all_year",
    "spouse_not_member_of_household_during_last_six_months",
    "taxable_year_closed_by_reason_of_taxpayer_death",
    "taxable_year_begins_after_2024_and_before_2029",
    "taxable_year_begins_before_2027",
    "taxable_year_begins_after_2025",
    "taxpayer_claims_section_911_benefits",
    "taxpayer_makes_lump_sum_election_under_subsection_e",
    "taxpayer_receives_social_security_benefit_for_listed_purpose",
    "taxpayer_is_nonresident_alien_for_any_portion_of_year",
    "taxpayer_is_qualifying_child_of_another_taxpayer",
    "taxpayer_is_section_1_g_child",
    "taxpayer_treated_as_resident_by_section_6013_g_or_h_election",
    "taxpayer_or_spouse_has_us_principal_abode_more_than_half_year",
    "unable_to_engage_substantial_gainful_activity",
    "vehicle_final_assembly_occurred_within_united_states",
    "vehicle_identification_number_included_on_return",
    "vehicle_is_car_minivan_van_suv_pickup_truck_or_motorcycle",
    "vehicle_manufactured_primarily_for_public_streets_roads_and_highways",
    "vehicle_operated_exclusively_on_rail_or_rails",
    "vehicle_original_use_commences_with_taxpayer",
    "vehicle_purchased_for_personal_use",
    "vehicle_treated_as_motor_vehicle_under_clean_air_act_title_II",
)

_TAX_UNIT_NUMERIC_DEFAULTS = (
    "able_account_contributions",
    "allocable_investment_deductions",
    "alternative_minimum_tax_foreign_tax_credit",
    "amt_tax_including_capital_gains",
    "adjusted_gross_income_under_section_67_e",
    "amount_excluded_from_gross_income_under_section_911",
    "amount_excluded_from_gross_income_under_section_911_a_1",
    "amount_excluded_from_gross_income_under_section_112",
    "amount_excluded_from_gross_income_under_section_931",
    "amount_excluded_from_gross_income_under_section_933",
    "annuity_income",
    "aotc_prior_year_election_count",
    "american_employer_foreign_affiliate_equivalent_3121l_taxes",
    "auto_loan_interest_deduction",
    "capital_gains_28_percent_rate_gain",
    "charitable_deduction_for_non_itemizers",
    "cost_of_living_adjustment_25b",
    "credit_allowed_under_section_33",
    "credit_against_chapter_tax_before_section_911_double_benefit_denial",
    "credit_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
    "ctc_limiting_tax_liability",
    "deduction_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
    "deduction_under_subtitle_before_section_911_double_benefit_denial",
    "dependent_care_assistance_exclusion",
    "dependent_care_assistance_excludable_under_section_129",
    "dividend_income",
    "eitc_relevant_investment_income",
    "elective_deferrals",
    "eligible_deferred_compensation_deferrals",
    "employee_3101_3201a_taxes",
    "energy_efficient_home_improvement_credit",
    "employment_related_expenses_paid",
    "excess_payroll_tax_withheld",
    "excludable_educational_assistance",
    "exclusion_from_gross_income_under_subtitle_before_section_911_double_benefit_denial",
    "exclusion_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
    "exemptions",
    "financial_trading_business_income",
    "foreign_tax_credit",
    "form_4972_lumpsum_distributions",
    "impairment_duration_months",
    "highest_section_1_e_bracket_begin_amount",
    "inclusion_by_reason_of_prior_year_lump_sum_portion_before_subsection_e_limitation",
    "individual_testing_period_distributions",
    "investment_of_working_capital_income",
    "itemized_taxable_income_deductions",
    "long_term_capital_gains",
    "lump_sum_payment_portion_attributable_to_prior_taxable_years",
    "min_head_spouse_earned",
    "misc_deduction",
    "new_clean_vehicle_credit",
    "other_nontaxable_pension_annuity_disability_benefits_subject_to_reduction",
    "other_non_title_pension_annuity_or_disability_benefits_excluded_from_gross_income",
    "overtime_income_deduction",
    "passive_activity_business_income",
    "passenger_vehicle_loan_interest_paid_or_accrued",
    "pension_annuity_disability_benefits_received",
    "qualified_dividend_income",
    "qualified_plan_distributions",
    "qualifying_children_count",
    "qualified_retirement_contributions",
    "qualified_retirement_penalty",
    "qualified_tuition_and_related_expenses",
    "recapture_of_investment_credit",
    "recovery_rebate_credit",
    "railroad_3211a_taxes",
    "railroad_retirement_annuity_amount_equivalent_to_social_security_benefit",
    "railroad_retirement_monthly_annuity_amount_under_section_3_f_3",
    "refundable_payroll_tax_credit",
    "railroad_retirement_act_benefits_excluded_from_gross_income",
    "rental_income",
    "residential_clean_energy_credit",
    "royalty_income",
    "salt_deduction",
    "section_104_a_4_va_benefits",
    "section_22_disability_income",
    "section_401_k_8_distribution",
    "section_401_m_6_distribution",
    "section_402_g_2_distribution",
    "section_404_k_distribution",
    "section_408A_d_3_distribution",
    "section_408_d_4_distribution",
    "section_72_p_distribution",
    "section_911_disallowed_deductions_and_exclusions",
    "section_911_excluded_gross_income",
    "section_911_excluded_income",
    "section_931_excluded_income",
    "section_933_excluded_income",
    "self_employment_income_subject_to_1401_b",
    "short_term_capital_gains",
    "social_security_benefit_checks_deemed_received_in_taxable_year_under_section_708",
    "social_security_benefit_repayments_during_taxable_year",
    "social_security_title_ii_benefits_excluded_from_gross_income",
    "special_refund_social_security_taxes_under_6413c",
    "spouse_earned_income_for_cdcc",
    "spouse_testing_period_distributions",
    "sum_of_prior_year_gross_income_increases_from_lump_sum_portion",
    "tax_exempt_interest_received_or_accrued",
    "tax_unit_childcare_expenses",
    "taxable_interest_income",
    "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception",
    "taxable_net_gain_from_dispositions",
    "taxable_pension_annuity_disability_benefits_included",
    "tax_imposed_by_chapter_before_cdcc",
    "taxpayer_earned_income_for_cdcc",
    "tip_income_deduction",
    "trustee_to_trustee_transfer_or_rollover_distribution_portion",
    "undistributed_net_investment_income",
    "unemployment_compensation",
    "unrecaptured_section_1250_gain",
    "unreported_payroll_tax",
    "used_clean_vehicle_credit",
    "vehicle_gross_vehicle_weight_rating",
    "vehicle_wheel_count",
    "voluntary_employee_qualified_plan_contributions",
    "veterans_affairs_pension_annuity_or_disability_benefits_excluded_from_gross_income",
    "wagering_losses_deduction",
    "workers_compensation_benefit_portion_equal_to_social_security_reduction",
    "workers_compensation_treated_as_social_security_benefit_under_section_86_d_3",
)

_INPUT_REF_OVERRIDES = {
    name: f"us:statutes/26/63/c#input.{name}"
    for name in (
        "cost_of_living_adjustment_under_section_1_f_3",
        "deduction_under_section_151_allowable_to_another_taxpayer",
        "estate_or_trust_common_trust_fund_or_partnership",
        "is_blind",
        "married_individual_filing_separate_return_where_either_spouse_itemizes_deductions",
        "nonresident_alien_individual",
        "return_under_section_443_a_1_for_less_than_12_months_due_to_accounting_period_change",
        "taxable_year_begins_after_2025",
    )
}
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:policies/irs/rev-proc-2025-32/standard-deduction#input.{name}"
        for name in (
            "additional_standard_deduction_entitlement_count_under_subsection_f",
            "individual_is_unmarried_and_not_surviving_spouse",
            "may_be_claimed_as_dependent_by_another_taxpayer",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/63#input.{name}"
        for name in (
            "deduction_for_personal_exemptions_provided_in_section_151",
            "deduction_provided_in_section_170_p",
            "deduction_provided_in_section_199A",
            "deduction_provided_in_section_224",
            "deduction_provided_in_section_225",
            "deductions_allowable_in_arriving_at_adjusted_gross_income",
            "deductions_allowable_under_this_chapter",
            "deductions_allowed_by_this_chapter_other_than_standard_deduction",
            "gross_income",
            "individual_makes_election_to_itemize_deductions_for_taxable_year",
            "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/63/f#input.{name}"
        for name in (
            "additional_exemption_allowable_for_spouse_under_section_151_b",
            "spouse_has_attained_age_65_before_close_of_taxable_year",
            "spouse_is_blind_as_of_close_of_taxable_year_or_time_of_death",
            "taxpayer_has_attained_age_65_before_close_of_taxable_year",
            "taxpayer_is_blind_at_close_of_taxable_year",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/1411#input.{name}"
        for name in (
            "adjusted_gross_income_under_section_67_e",
            "allocable_investment_deductions",
            "amount_excluded_from_gross_income_under_section_911_a_1",
            "annuity_income",
            "dividend_income",
            "financial_trading_business_income",
            "highest_section_1_e_bracket_begin_amount",
            "is_estate_or_trust",
            "is_individual",
            "investment_of_working_capital_income",
            "passive_activity_business_income",
            "qualified_plan_distributions",
            "rental_income",
            "royalty_income",
            "self_employment_income_subject_to_1401_b",
            "taxable_interest_income",
            "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception",
            "trust_all_unexpired_interests_devoted_to_section_170_c_2_B_purposes",
            "undistributed_net_investment_income",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/163#input.{name}"
        for name in (
            "amount_excluded_from_gross_income_under_section_911",
            "amount_excluded_from_gross_income_under_section_931",
            "amount_excluded_from_gross_income_under_section_933",
            "indebtedness_incurred_after_2024_for_purchase_of_vehicle",
            "indebtedness_owed_to_related_person_under_section_267_b_or_707_b_1",
            "indebtedness_secured_by_first_lien_on_vehicle",
            "lease_financing",
            "loan_finances_fleet_sales",
            "loan_finances_vehicle_intended_for_scrap_or_parts",
            "loan_finances_vehicle_with_salvage_title",
            "loan_for_commercial_vehicle_not_used_for_personal_purposes",
            "passenger_vehicle_loan_interest_paid_or_accrued",
            "vehicle_final_assembly_occurred_within_united_states",
            "vehicle_gross_vehicle_weight_rating",
            "vehicle_identification_number_included_on_return",
            "vehicle_is_car_minivan_van_suv_pickup_truck_or_motorcycle",
            "vehicle_manufactured_primarily_for_public_streets_roads_and_highways",
            "vehicle_operated_exclusively_on_rail_or_rails",
            "vehicle_original_use_commences_with_taxpayer",
            "vehicle_purchased_for_personal_use",
            "vehicle_treated_as_motor_vehicle_under_clean_air_act_title_II",
            "vehicle_wheel_count",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/911/d/6#input.{name}"
        for name in (
            "credit_against_chapter_tax_before_section_911_double_benefit_denial",
            "credit_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
            "deduction_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
            "deduction_under_subtitle_before_section_911_double_benefit_denial",
            "exclusion_from_gross_income_under_subtitle_before_section_911_double_benefit_denial",
            "exclusion_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/21#input.{name}"
        for name in (
            "abode_relationship_violates_local_law",
            "dependent_care_assistance_excludable_under_section_129",
            "employment_related_expenses_paid",
            "is_dependent_under_section_152_a_1",
            "is_dependent_under_section_152_disregarding_listed_subsections",
            "is_spouse_of_taxpayer",
            "married_at_close_of_taxable_year",
            "married_filing_separate_return",
            "married_joint_return_filed",
            "qualifying_individual_tin_included_on_return",
            "section_152_e_non_custodial_parent",
            "service_provider_identifying_information_requirement_satisfied",
            "spouse_earned_income_for_cdcc",
            "spouse_not_member_of_household_during_last_six_months",
            "tax_imposed_by_chapter_before_cdcc",
            "taxpayer_earned_income_for_cdcc",
            "taxpayer_or_spouse_has_us_principal_abode_more_than_half_year",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/24/h#input.{name}"
        for name in (
            "dependent_under_section_152",
            "filing_status_is_joint_return",
            "noncitizen_exception_to_other_dependent_credit_under_subsection_h",
            "qualifying_child_described_in_subsection_c",
            "qualifying_child_ssn_included_on_return",
            "qualifying_child_ssn_is_valid_for_subsection_h",
            "taxpayer_or_spouse_ssn_included_on_return",
            "taxpayer_or_spouse_ssn_is_valid_for_subsection_h",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/22#input.{name}"
        for name in (
            "other_non_title_pension_annuity_or_disability_benefits_excluded_from_gross_income",
            "railroad_retirement_act_benefits_excluded_from_gross_income",
            "social_security_title_ii_benefits_excluded_from_gross_income",
            "veterans_affairs_pension_annuity_or_disability_benefits_excluded_from_gross_income",
            "workers_compensation_treated_as_social_security_benefit_under_section_86_d_3",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/86#input.{name}"
        for name in (
            "inclusion_by_reason_of_prior_year_lump_sum_portion_before_subsection_e_limitation",
            "lump_sum_payment_portion_attributable_to_prior_taxable_years",
            "married_taxpayer_lived_apart_from_spouse_at_all_times_during_taxable_year",
            "railroad_retirement_annuity_amount_equivalent_to_social_security_benefit",
            "railroad_retirement_monthly_annuity_amount_under_section_3_f_3",
            "social_security_benefit_checks_deemed_received_in_taxable_year_under_section_708",
            "social_security_benefit_repayments_during_taxable_year",
            "sum_of_prior_year_gross_income_increases_from_lump_sum_portion",
            "tax_exempt_interest_received_or_accrued",
            "taxpayer_makes_lump_sum_election_under_subsection_e",
            "taxpayer_receives_social_security_benefit_for_listed_purpose",
            "title_II_monthly_benefits_received_during_taxable_year",
            "workers_compensation_benefit_portion_equal_to_social_security_reduction",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/164/f#input.{name}"
        for name in ("taxpayer_is_individual",)
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/1402/a#input.{name}"
        for name in (
            "partnership_section_702_a_8_income_or_loss",
            "self_employment_trade_or_business_deductions",
            "self_employment_trade_or_business_gross_income",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/24/d#input.{name}"
        for name in (
            "aggregate_subpart_c_credits_with_increased_26a_limit",
            "aggregate_subpart_c_credits_without_subsection",
            "american_employer_foreign_affiliate_equivalent_3121l_taxes",
            "amount_excluded_from_gross_income_under_section_112",
            "ctc_credit_without_subsection_and_26a_limit",
            "elects_foreign_earned_income_exclusion_under_911",
            "employee_3101_3201a_taxes",
            "qualifying_children_count",
            "railroad_3211a_taxes",
            "special_refund_social_security_taxes_under_6413c",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/6401#input.{name}"
        for name in (
            "credit_allowed_under_section_33",
            "credit_allowed_under_section_33_by_reason_of_section_1446",
            "credits_allowable_under_subpart_c_excluding_section_33_for_overpayment",
            "section_6013_g_or_h_election_in_effect_for_taxable_year",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/32#input.{name}"
        for name in (
            "qualifying_child_is_married_at_close_of_taxable_year",
            "qualifying_child_name_age_and_tin_included_on_return",
            "qualifying_child_principal_place_of_abode_is_in_united_states",
            "qualifying_child_under_section_152_c_as_modified_for_eitc",
            "taxpayer_entitled_to_section_151_deduction_for_child_or_would_be_but_for_section_152_e",
            "taxpayer_claims_section_911_benefits",
            "taxpayer_includes_required_social_security_number_on_return",
            "taxpayer_is_dependent_for_section_151_to_another_taxpayer",
            "taxpayer_is_married_under_section_7703_a",
            "taxpayer_is_nonresident_alien_for_any_portion_of_year",
            "taxpayer_is_qualifying_child_of_another_taxpayer",
            "taxpayer_treated_as_resident_by_section_6013_g_or_h_election",
            "taxable_year_closed_by_reason_of_taxpayer_death",
            "taxable_year_is_full_12_months",
            "prior_deficiency_denial_without_required_eligibility_information",
            "spouse_includes_required_social_security_number_on_return",
            "childless_taxpayer_or_spouse_age_eligible_for_eitc",
            "childless_taxpayer_principal_place_of_abode_in_united_states_more_than_half_year",
            "eitc_disallowance_period_applies",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"{US_FEDERAL_INCOME_TAX_BRIDGE_TARGET}#input.{name}"
        for name in (
            "person_rental_income_for_qbid",
            "person_self_employment_income_for_qbid",
        )
    }
)


def attach_axiom_tax_inputs(cases: list[Case]) -> list[Case]:
    """Attach Axiom federal tax input records to ECPS-style neutral cases."""

    return [attach_axiom_tax_inputs_to_case(case) for case in cases]


def attach_axiom_tax_itemization_choice(cases: list[Case]) -> list[Case]:
    """Attach oracle-comparison itemization candidates to Axiom tax cases."""

    return [attach_axiom_tax_itemization_choice_to_case(case) for case in cases]


def attach_axiom_tax_itemization_choice_to_case(case: Case) -> Case:
    metadata = dict(case.metadata)
    metadata[AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY] = _itemization_overlays()
    metadata[AXIOM_RESULT_SELECTION_METADATA_KEY] = {
        "strategy": "min",
        "output": "us:statutes/26/6401#income_tax",
    }
    return replace(case, metadata=metadata)


def attach_axiom_tax_inputs_to_case(case: Case) -> Case:
    metadata = dict(case.metadata)
    if metadata.get(AXIOM_INPUT_RECORDS_METADATA_KEY):
        return case

    people = _people(case)
    if not people:
        raise RuntimeError("Axiom federal tax projection requires at least one person.")

    records = _tax_unit_input_records(case, people)
    records.extend(_person_input_records(people))
    relations = _relation_records(people)
    metadata[AXIOM_INPUT_RECORDS_METADATA_KEY] = records
    metadata[AXIOM_RELATIONS_METADATA_KEY] = [
        *metadata.get(AXIOM_RELATIONS_METADATA_KEY, []),
        *relations,
    ]
    return replace(case, metadata=metadata)


def _tax_unit_input_records(case: Case, people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    dependents = _tax_dependents(people, head, spouse)
    wages = _earned_income(head) + (_earned_income(spouse) if spouse else 0)

    # Investment / unearned income pulled from the Case so Axiom matches what
    # PolicyEngine and TAXSIM see.
    earners = [person for person in (head, spouse) if person is not None]
    dividends = _sum_concept(earners, Concepts.DIVIDEND_INCOME)
    qualified_dividends = _sum_concept(earners, Concepts.QUALIFIED_DIVIDEND_INCOME)
    interest = _sum_concept(earners, Concepts.INTEREST_INCOME)
    short_capital_gains = _sum_concept(earners, Concepts.SHORT_TERM_CAPITAL_GAINS)
    long_capital_gains = _sum_concept(earners, Concepts.LONG_TERM_CAPITAL_GAINS)
    pensions = _sum_concept(earners, Concepts.PENSION_INCOME)
    social_security = _sum_concept(people, Concepts.SOCIAL_SECURITY_BENEFITS)
    unemployment = _sum_concept(earners, Concepts.UNEMPLOYMENT_INSURANCE_INCOME)
    rental = _sum_concept(earners, Concepts.RENTAL_INCOME)
    self_employment = _sum_concept(earners, Concepts.SELF_EMPLOYMENT_INCOME)

    filing_status = _filing_status(spouse=spouse, dependents=dependents)
    taxpayer_is_blind = bool(head.fact(Concepts.BLIND, False))
    spouse_is_blind = bool(spouse.fact(Concepts.BLIND, False)) if spouse else False

    inputs: dict[str, Any] = {
        "additional_standard_deduction_entitlement_count_under_subsection_f": sum(
            int(_age(person) >= 65)
            + int(bool(person.fact(Concepts.BLIND, False)))
            for person in (head, spouse)
            if person is not None
        ),
        "additional_exemption_allowable_for_spouse_under_section_151_b": spouse
        is not None,
        "age_at_close_of_taxable_year": _age(head),
        "childless_taxpayer_or_spouse_age_eligible_for_eitc": (
            any(_eitc_childless_age_eligible(person) for person in people)
        ),
        "childless_taxpayer_principal_place_of_abode_in_united_states_more_than_half_year": True,
        "employee_medicare_tax": wages * 0.0145,
        "employee_social_security_tax": wages * 0.062,
        "filer_meets_eitc_identification_requirements": True,
        "filing_status": filing_status,
        "filing_status_is_joint_return": spouse is not None,
        "individual_is_unmarried_and_not_surviving_spouse": spouse is None,
        "is_estate_or_trust": False,
        "is_individual": True,
        "married_at_close_of_taxable_year": spouse is not None,
        "married_filing_separate_return": False,
        "married_joint_return_filed": spouse is not None,
        "may_be_claimed_as_dependent_by_another_taxpayer": False,
        "tax_exempt_interest_received_or_accrued": 0,
        "spouse_has_attained_age_65_before_close_of_taxable_year": bool(
            spouse and _age(spouse) >= 65
        ),
        "spouse_is_blind_as_of_close_of_taxable_year_or_time_of_death": spouse_is_blind,
        "spouse_includes_required_social_security_number_on_return": spouse is not None,
        "taxable_year_is_full_12_months": True,
        "taxpayer_includes_required_social_security_number_on_return": True,
        "taxpayer_has_attained_age_65_before_close_of_taxable_year": _age(head) >= 65,
        "taxpayer_is_blind_at_close_of_taxable_year": taxpayer_is_blind,
        "taxpayer_is_dependent_for_section_151_to_another_taxpayer": False,
        "taxpayer_is_married_under_section_7703_a": spouse is not None,
        "trust_all_unexpired_interests_devoted_to_section_170_c_2_B_purposes": False,
        "wages": wages,
        "wages_taken_into_account_for_additional_medicare_tax": wages,
        # Investment / unearned income — projected from Case concepts.
        "dividend_income": dividends,
        "qualified_dividend_income": qualified_dividends,
        "taxable_interest_income": interest,
        "short_term_capital_gains": short_capital_gains,
        "long_term_capital_gains": long_capital_gains,
        "rental_income": rental,
        "pension_annuity_disability_benefits_received": pensions,
        "partnership_section_702_a_8_income_or_loss": 0,
        "self_employment_trade_or_business_deductions": 0,
        "self_employment_trade_or_business_gross_income": self_employment,
        "taxpayer_is_individual": True,
        "title_II_monthly_benefits_received_during_taxable_year": social_security,
        "unemployment_compensation": unemployment,
    }
    for name in _BOOLEAN_DEFAULTS_FALSE:
        inputs.setdefault(name, _boolean_default(name, case))
    for name in _TAX_UNIT_NUMERIC_DEFAULTS:
        inputs.setdefault(name, 0)
    inputs.update(_case_axiom_tax_unit_inputs(case))
    inputs["deduction_provided_in_section_170_p"] = inputs.get(
        "charitable_deduction_for_non_itemizers",
        0,
    )
    inputs["deduction_provided_in_section_224"] = inputs.get(
        "tip_income_deduction",
        0,
    )
    inputs["deduction_provided_in_section_225"] = inputs.get(
        "overtime_income_deduction",
        0,
    )
    inputs["taxpayer_earned_income_for_cdcc"] = _earned_income(head)
    inputs["spouse_earned_income_for_cdcc"] = _earned_income(spouse) if spouse else 0
    inputs["employment_related_expenses_paid"] = inputs.get(
        "tax_unit_childcare_expenses",
        0,
    )
    inputs["employee_3101_3201a_taxes"] = inputs.get("employee_social_security_tax", 0)
    inputs["qualifying_children_count"] = sum(
        1 for dependent in dependents if _age(dependent) < 17
    )
    inputs["passenger_vehicle_loan_interest_paid_or_accrued"] = inputs.get(
        "auto_loan_interest_deduction",
        0,
    )
    itemized_taxable_income_deductions = inputs.get(
        "itemized_taxable_income_deductions",
        0,
    )
    inputs.setdefault(
        "cost_of_living_adjustment_under_section_1_f_3",
        _standard_deduction_cola(case),
    )
    inputs.setdefault("deduction_for_personal_exemptions_provided_in_section_151", 0)
    inputs.setdefault("deductions_allowable_in_arriving_at_adjusted_gross_income", 0)
    inputs.setdefault(
        "deductions_allowable_under_this_chapter",
        itemized_taxable_income_deductions,
    )
    inputs.setdefault(
        "deductions_allowed_by_this_chapter_other_than_standard_deduction",
        itemized_taxable_income_deductions,
    )
    return [_input_record(name, "TaxUnit", _TAX_UNIT_ID, value) for name, value in inputs.items()]


def _person_input_records(people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    records = []
    for person in people:
        age = _age(person)
        is_dependent = _is_tax_dependent(person, head, spouse)
        inputs: dict[str, Any] = {
            "age": age,
            "age_at_close_of_taxable_year": age,
            "dependent_under_section_152": is_dependent,
            "earned_income": _earned_income(person),
            "has_same_principal_place_of_abode_more_than_half_year": is_dependent,
            "is_blind": bool(person.fact(Concepts.BLIND, False)),
            "is_qualifying_child_dependent": is_dependent and age < 19,
            "is_section_152_a_1_dependent": is_dependent and age < 19,
            "is_spouse": person is spouse,
            "is_tax_unit_dependent": is_dependent,
            "is_taxpayer": person is head or person is spouse,
            "meets_ctc_child_identification_requirements": is_dependent,
            "meets_eitc_identification_requirements": is_dependent,
            "noncitizen_exception_to_other_dependent_credit_under_subsection_h": False,
            "person_rental_income_for_qbid": _number(
                person.fact(Concepts.RENTAL_INCOME, 0)
            ),
            "person_self_employment_income_for_qbid": _number(
                person.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0)
            ),
            "qualifying_child_described_in_subsection_c": is_dependent and age < 17,
            "qualifying_child_is_married_at_close_of_taxable_year": False,
            "qualifying_child_name_age_and_tin_included_on_return": is_dependent,
            "qualifying_child_principal_place_of_abode_is_in_united_states": is_dependent,
            "qualifying_child_ssn_included_on_return": is_dependent,
            "qualifying_child_ssn_is_valid_for_subsection_h": is_dependent,
            "qualifying_child_under_section_152_c_as_modified_for_eitc": is_dependent
            and age < 19,
            "taxpayer_entitled_to_section_151_deduction_for_child_or_would_be_but_for_section_152_e": is_dependent,
            "taxpayer_or_spouse_ssn_included_on_return": True,
            "taxpayer_or_spouse_ssn_is_valid_for_subsection_h": True,
        }
        for name in _BOOLEAN_DEFAULTS_FALSE:
            inputs.setdefault(name, False)
        for name in _TAX_UNIT_NUMERIC_DEFAULTS:
            inputs.setdefault(name, 0)
        for name, value in inputs.items():
            records.append(_input_record(name, "Person", person.entity_id, value))
    return records


def _relation_records(people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    dependents = _tax_dependents(people, head, spouse)
    tax_filers = [person for person in (head, spouse) if person is not None]
    records = []
    for relation_ref in _RELATION_REFS:
        if relation_ref in {
            "us:tax/federal-income-tax/oracle-bridge#relation.business_income_of_tax_unit",
            "us:statutes/26/22#relation.taxpayer_or_spouse_of_tax_unit",
        }:
            relation_people = tax_filers
        elif relation_ref in {
            "us:statutes/26/24/h#relation.dependent_of_tax_unit",
            "us:statutes/26/32#relation.qualifying_child_of_tax_unit",
        }:
            relation_people = dependents
        else:
            relation_people = people
        records.extend(
            {
                "name": relation_ref,
                "tuple": [person.entity_id, _TAX_UNIT_ID],
            }
            for person in relation_people
        )
    return records


def _input_record(
    name: str,
    entity: str,
    entity_id: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "name": _input_ref(name),
        "entity": entity,
        "entity_id": entity_id,
        "value": value,
    }


def _input_ref(name: str) -> str:
    if name in _INPUT_REF_OVERRIDES:
        return _INPUT_REF_OVERRIDES[name]
    return f"{_AXIOM_TAX_REF_PREFIX}#input.{name}"


def _case_axiom_tax_unit_inputs(case: Case) -> dict[str, Any]:
    raw_inputs = case.metadata.get(AXIOM_TAX_UNIT_INPUTS_METADATA_KEY, {})
    if not raw_inputs:
        return {}
    if not isinstance(raw_inputs, dict):
        raise RuntimeError("metadata['axiom_tax_unit_inputs'] must be a mapping.")
    itemization_inputs = {
        "individual_makes_election_to_itemize_deductions_for_taxable_year",
        "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year",
        "tax_unit_itemizes",
    }
    supplied_itemization_inputs = sorted(itemization_inputs.intersection(raw_inputs))
    if supplied_itemization_inputs:
        raise RuntimeError(
            "metadata['axiom_tax_unit_inputs'] must not include itemization status; "
            "itemization status is resolved by Axiom candidate selection."
        )
    aggregate_inputs = {
        "adjusted_gross_income",
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
        "additional_senior_deduction",
        "earned_income",
        "filer_adjusted_earnings",
        "gross_income",
        "irs_gross_income",
        "modified_adjusted_gross_income",
        "deduction_provided_in_section_199A",
        "qualified_business_income_deduction",
        "self_employment_1401_taxes",
        "self_employment_income",
        "self_employment_tax_ald",
        "taxable_earned_income_under_section_32",
        "taxable_social_security_benefits_included",
    }
    supplied_aggregate_inputs = sorted(aggregate_inputs.intersection(raw_inputs))
    if supplied_aggregate_inputs:
        raise RuntimeError(
            "metadata['axiom_tax_unit_inputs'] must not include calculator-derived "
            f"aggregate inputs: {', '.join(supplied_aggregate_inputs)}."
        )
    return dict(raw_inputs)


def _itemization_overlays() -> list[list[dict[str, Any]]]:
    return [
        [
            _input_record(
                "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year",
                "TaxUnit",
                _TAX_UNIT_ID,
                True,
            ),
            _input_record(
                "individual_makes_election_to_itemize_deductions_for_taxable_year",
                "TaxUnit",
                _TAX_UNIT_ID,
                False,
            ),
        ],
        [
            _input_record(
                "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year",
                "TaxUnit",
                _TAX_UNIT_ID,
                False,
            ),
            _input_record(
                "individual_makes_election_to_itemize_deductions_for_taxable_year",
                "TaxUnit",
                _TAX_UNIT_ID,
                True,
            ),
        ],
    ]


def _filing_status(*, spouse: Entity | None, dependents: list[Entity]) -> int:
    if spouse is not None:
        return 1
    if any(_hoh_qualifying_dependent(dependent) for dependent in dependents):
        return 3
    return 0


def _hoh_qualifying_dependent(dependent: Entity) -> bool:
    return _age(dependent) < 19 or bool(dependent.fact(Concepts.DISABLED, False))


def _boolean_default(name: str, case: Case) -> bool:
    year = int(str(case.period).split("-", maxsplit=1)[0])
    if name == "taxable_year_begins_after_2024_and_before_2029":
        return 2024 < year < 2029
    if name == "taxable_year_begins_after_2025":
        return year > 2025
    if name == "taxable_year_begins_before_2027":
        return year < 2027
    return False


def _standard_deduction_cola(case: Case) -> float:
    year = int(str(case.period).split("-", maxsplit=1)[0])
    if year != 2026:
        return 0
    increase = (
        _STANDARD_DEDUCTION_OTHER_CASE_2026_AMOUNT
        - _STANDARD_DEDUCTION_OTHER_CASE_AFTER_2017_BASE_AMOUNT
    )
    return increase / _STANDARD_DEDUCTION_OTHER_CASE_AFTER_2017_BASE_AMOUNT


def _eitc_childless_age_eligible(person: Entity) -> bool:
    age = _age(person)
    return 25 <= age < 65


def _people(case: Case) -> list[Entity]:
    return [
        entity
        for entity in case.entities
        if str(entity.kind).lower().replace("_", "-") == "person"
    ]


def _head(people: list[Entity]) -> Entity:
    for person in people:
        if _relation(person) in _HEAD_RELATIONS:
            return person
    return people[0]


def _tax_filers(people: list[Entity]) -> tuple[Entity, Entity | None]:
    explicit_head = _head(people)
    explicit_spouse = _spouse(people, explicit_head)
    if explicit_spouse is not None:
        return explicit_head, explicit_spouse

    adult_people = [
        person
        for person in people
        if _age(person) >= _TAX_FILER_ADULT_AGE
        and _relation(person) not in _DEPENDENT_RELATIONS
    ]
    if not adult_people:
        return explicit_head, None
    ranked = sorted(
        adult_people,
        key=lambda person: (_age(person), _earned_income(person)),
        reverse=True,
    )
    head = ranked[0]
    spouse = ranked[1] if len(ranked) > 1 else None
    return head, spouse


def _tax_dependents(
    people: list[Entity],
    head: Entity,
    spouse: Entity | None,
) -> list[Entity]:
    return [
        person
        for person in people
        if _is_tax_dependent(person, head, spouse)
    ]


def _is_tax_dependent(
    person: Entity,
    head: Entity,
    spouse: Entity | None,
) -> bool:
    return person is not head and person is not spouse


def _spouse(people: list[Entity], head: Entity) -> Entity | None:
    for person in people:
        if person is not head and _relation(person) in _SPOUSE_RELATIONS:
            return person
    return None


def _relation(entity: Entity) -> str:
    return (
        str(entity.fact(Concepts.HOUSEHOLD_RELATION, ""))
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _age(entity: Entity) -> int:
    return int(_number(entity.fact(Concepts.PERSON_AGE, 0)))


def _earned_income(entity: Entity) -> float:
    return _number(entity.fact(Concepts.YEARLY_EARNED_INCOME, 0))


def _sum_concept(entities: list[Entity], concept: str) -> float:
    return sum(_number(entity.fact(concept, 0)) for entity in entities)


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0
    return float(value)
