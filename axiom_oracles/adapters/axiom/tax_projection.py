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


US_TAX_ORACLE_IMPORTS = (
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
    # 1402(a)(12) lives in a child fragment; the engine resolves rule names
    # only from explicitly imported modules, so the parent import alone
    # leaves self_employment_tax_equivalent_deduction_fraction unbound.
    "us:statutes/26/1402/a/12",
    "us:statutes/26/1411",
    "us:statutes/26/3101/a",
    "us:statutes/26/3101/b/1",
    "us:statutes/26/3101/b/2",
    "us:statutes/26/6401",
)

US_TAX_ORACLE_BRIDGE_TARGET = "us:tax/oracle-bridge"

US_TAX_ORACLE_PROGRAM_RULES = (
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
        "social_security_wage_base",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine's 2026 SSA contribution and benefit base",
        formula="186000",
    ),
    _generated_parameter_rule(
        "contribution_and_benefit_base_under_section_230_of_social_security_act",
        dtype="Money",
        unit="USD",
        source="Social Security Administration 2026 contribution and benefit base",
        formula="186000",
    ),
    _generated_parameter_rule(
        "alaska_permanent_fund_dividend_amount",
        dtype="Money",
        unit="USD",
        source="Alaska Department of Revenue 2024 Permanent Fund Dividend amount, carried forward for 2026 oracle comparison",
        formula="1403.83",
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
    _generated_parameter_rule(
        "self_employment_net_earnings_exemption",
        dtype="Money",
        unit="USD",
        source="26 USC 1402(b)(2)",
        formula="400",
    ),
    _generated_parameter_rule(
        "capital_loss_limit_joint_or_non_separate",
        dtype="Money",
        unit="USD",
        source="26 USC 1211(b), PolicyEngine 2026 capital-loss limit",
        formula="3000",
    ),
    _generated_parameter_rule(
        "capital_loss_limit_separate",
        dtype="Money",
        unit="USD",
        source="26 USC 1211(b), PolicyEngine 2026 capital-loss limit",
        formula="1500",
    ),
    _generated_parameter_rule(
        "business_loss_limit_joint_2026",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), PolicyEngine 2026 excess business-loss threshold",
        formula="610000",
    ),
    _generated_parameter_rule(
        "business_loss_limit_other_2026",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), PolicyEngine 2026 excess business-loss threshold",
        formula="305000",
    ),
    _generated_parameter_rule(
        "co_income_tax_rate",
        dtype="Rate",
        source="C.R.S. 39-22-104(1.7)(a)(V), matching PolicyEngine's 2026 Colorado income tax rate",
        formula="0.044",
    ),
    _generated_parameter_rule(
        "co_withholding_single_standard_deduction",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Colorado withheld-tax proxy for 2026",
        formula="16100",
    ),
    _generated_parameter_rule(
        "co_eitc_match_2026",
        dtype="Rate",
        source="C.R.S. 39-22-123.5, resolved for 2026 oracle comparison",
        formula="0.25",
    ),
    _generated_parameter_rule(
        "co_family_affordability_child_amount_2026",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 and 2025 DR 0104 Book, carried forward by PolicyEngine for 2026 oracle comparison",
        formula="3273",
    ),
    _generated_parameter_rule(
        "co_family_affordability_reduction_threshold_joint_2026",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 family affordability credit threshold, uprated by PolicyEngine for 2026",
        formula="26000",
    ),
    _generated_parameter_rule(
        "co_family_affordability_reduction_threshold_other_2026",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 family affordability credit threshold, uprated by PolicyEngine for 2026",
        formula="16000",
    ),
    _generated_parameter_rule(
        "co_family_affordability_reduction_increment_2026",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 family affordability credit reduction increment, uprated by PolicyEngine for 2026",
        formula="5000",
    ),
    _generated_parameter_rule(
        "co_family_affordability_reduction_rate",
        dtype="Rate",
        source="Colorado HB24-1311 family affordability credit reduction rate",
        formula="0.06875",
    ),
    _generated_parameter_rule(
        "co_ctc_child_age_threshold",
        dtype="Integer",
        source="C.R.S. 39-22-129 child tax credit age threshold",
        formula="6",
    ),
    _generated_parameter_rule(
        "co_ctc_joint_first_threshold_2026",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit, 2025 thresholds carried forward by PolicyEngine for 2026",
        formula="36000",
    ),
    _generated_parameter_rule(
        "co_ctc_joint_second_threshold_2026",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit, 2025 thresholds carried forward by PolicyEngine for 2026",
        formula="61000",
    ),
    _generated_parameter_rule(
        "co_ctc_joint_third_threshold_2026",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit, 2025 thresholds carried forward by PolicyEngine for 2026",
        formula="87000",
    ),
    _generated_parameter_rule(
        "co_ctc_other_first_threshold_2026",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit, 2025 thresholds carried forward by PolicyEngine for 2026",
        formula="26000",
    ),
    _generated_parameter_rule(
        "co_ctc_other_second_threshold_2026",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit, 2025 thresholds carried forward by PolicyEngine for 2026",
        formula="51000",
    ),
    _generated_parameter_rule(
        "co_ctc_other_third_threshold_2026",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit, 2025 thresholds carried forward by PolicyEngine for 2026",
        formula="77000",
    ),
    _generated_parameter_rule(
        "co_ctc_high_amount",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit amount table",
        formula="1200",
    ),
    _generated_parameter_rule(
        "co_ctc_middle_amount",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit amount table",
        formula="600",
    ),
    _generated_parameter_rule(
        "co_ctc_low_amount",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit amount table",
        formula="200",
    ),
    _generated_parameter_rule(
        "co_pension_subtraction_older_cap",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g)(III)(B)",
        formula="24000",
    ),
    _generated_parameter_rule(
        "co_pension_subtraction_younger_cap",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g)(III)(A)",
        formula="20000",
    ),
    _generated_parameter_rule(
        "co_federal_deduction_addback_agi_threshold",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(p), 2025 DR 0104 Book Additions Line 4",
        formula="300000",
    ),
    _generated_parameter_rule(
        "co_federal_deduction_addback_joint_exemption",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(p), 2025 DR 0104 Book Additions Line 4",
        formula="16000",
    ),
    _generated_parameter_rule(
        "co_federal_deduction_addback_other_exemption",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(p), 2025 DR 0104 Book Additions Line 4",
        formula="12000",
    ),
    _generated_parameter_rule(
        "co_qbid_addback_joint_agi_threshold",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(o), 2025 DR 0104 Book Additions Line 3",
        formula="1000000",
    ),
    _generated_parameter_rule(
        "co_qbid_addback_other_agi_threshold",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(o), 2025 DR 0104 Book Additions Line 3",
        formula="500000",
    ),
    _generated_parameter_rule(
        "salt_cap_joint_or_non_separate_2026",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 2026 SALT cap",
        formula="40400",
    ),
    _generated_parameter_rule(
        "salt_cap_separate_2026",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 2026 SALT cap",
        formula="20200",
    ),
    _generated_parameter_rule(
        "salt_cap_phaseout_threshold_joint_or_non_separate_2026",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 2026 SALT cap phaseout",
        formula="505000",
    ),
    _generated_parameter_rule(
        "salt_cap_phaseout_threshold_separate_2026",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 2026 SALT cap phaseout",
        formula="252500",
    ),
    _generated_parameter_rule(
        "salt_cap_phaseout_rate",
        dtype="Rate",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 SALT cap phaseout rate",
        formula="0.30",
    ),
    _generated_parameter_rule(
        "salt_cap_floor_joint_or_non_separate",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 SALT cap floor",
        formula="10000",
    ),
    _generated_parameter_rule(
        "salt_cap_floor_separate",
        dtype="Money",
        unit="USD",
        source="H.R.1 (119th Congress), section 70120; policyengine.py 4.4.4 SALT cap floor",
        formula="5000",
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
    _generated_data_relation_rule(
        "payroll_member_of_tax_unit",
        source="Oracle comparison bridge relating tax-unit members to person-level payroll-tax wage leaves",
    ),
    _generated_person_rule(
        "employee_payroll_wages",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge projecting PolicyEngine payroll_tax_gross_wages from ECPS employment-income leaves",
        formula="max(0, person_payroll_earnings)",
    ),
    _generated_person_rule(
        "employee_has_payroll_wages",
        dtype="Judgment",
        source="Oracle comparison bridge identifying tax-unit members with payroll wages",
        formula="employee_payroll_wages > 0",
    ),
    _generated_person_rule(
        "employee_social_security_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 3101(a) with the SSA wage base to person wage leaves",
        formula=(
            "oasdi_wage_tax_rate "
            "* min(employee_payroll_wages, social_security_wage_base)"
        ),
    ),
    _generated_person_rule(
        "employee_medicare_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 3101(b)(1) to person wage leaves",
        formula="hospital_insurance_wage_tax_rate * employee_payroll_wages",
    ),
    _generated_person_rule(
        "employee_3101_tax_before_additional_medicare",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge summing 26 USC 3101(a) and 3101(b)(1) employee payroll taxes",
        formula="employee_social_security_tax + employee_medicare_tax",
    ),
    _generated_tax_unit_rule(
        "employee_additional_medicare_tax_for_ctc",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 3101(b)(2) to tax-unit payroll wages",
        formula=(
            "additional_medicare_tax_rate "
            "* max("
            "0, "
            "sum_where("
            "payroll_member_of_tax_unit, "
            "employee_payroll_wages, "
            "employee_has_payroll_wages"
            ") - additional_medicare_wage_tax_threshold"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "employee_3101_3201a_taxes",
        dtype="Money",
        unit="USD",
        source="26 USC 24(d)(2)(A)(i), resolved from tax-unit member payroll-tax leaves",
        formula=(
            "sum_where("
            "payroll_member_of_tax_unit, "
            "employee_3101_tax_before_additional_medicare, "
            "employee_has_payroll_wages"
            ") + employee_additional_medicare_tax_for_ctc"
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
    # us:statutes/26/1402/a defers its executable net-earnings rule, so the
    # tax-unit name is supplied by aggregating the existing person-level
    # person_self_employment_net_earnings_after_paragraph_12 machinery — no
    # new computation, only the same member aggregation the SE-tax ALD rule
    # uses. The encoded us:statutes/26/1402/b `self_employment_income`
    # (which replaces the dropped shim; see
    # _tax_oracle_program_rules_for_concepts) consumes this name.
    _generated_tax_unit_rule(
        "net_earnings_from_self_employment",
        dtype="Money",
        unit="USD",
        source=(
            "Oracle composition bridge summing member-level 26 USC 1402(a) "
            "net earnings for the encoded us:statutes/26/1402/b rules"
        ),
        formula=(
            "sum_where("
            "business_income_of_tax_unit, "
            "person_self_employment_net_earnings_after_paragraph_12, "
            "person_has_positive_self_employment_income_for_agi"
            ")"
        ),
    ),
    # The encoded 1402/b rule tests its 1402(b)(2) threshold against this
    # leaf; the operand is the same 1402(a) net earnings the rule includes
    # when the test passes, so it aliases the aggregate above.
    _generated_tax_unit_rule(
        "net_earnings_from_self_employment_for_paragraph_2_threshold_test",
        dtype="Money",
        unit="USD",
        source=(
            "Oracle composition bridge supplying the 26 USC 1402(b)(2) "
            "threshold-test operand from the section 1402(a) net earnings"
        ),
        formula="net_earnings_from_self_employment",
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
        formula="self_employment_tax_ald_for_agi",
    ),
    _generated_tax_unit_rule(
        "taxable_earned_income_under_section_32",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 164(f) to earned income used by 26 USC 24(d)",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_adjusted_earnings_for_eitc, "
            "person_has_adjusted_earnings_for_eitc"
            ")"
        ),
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
        source="Oracle comparison bridge relating tax-unit members to person-level 26 USC 199A income leaves",
    ),
    _generated_data_relation_rule(
        "filer_adjusted_earnings_of_tax_unit",
        source="Oracle comparison bridge relating tax-unit filers to person-level 26 USC 32 adjusted earnings",
    ),
    _generated_person_rule(
        "person_capital_gains_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61 and 1211, projected from ECPS capital-gain leaves",
        formula="person_short_term_capital_gains + person_long_term_capital_gains",
    ),
    _generated_person_rule(
        "person_positive_capital_gains_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 61 capital-gain leaves",
        formula="max(0, person_capital_gains_for_agi)",
    ),
    _generated_person_rule(
        "person_capital_losses_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 1211, projected from ECPS capital-gain leaves",
        formula="max(0, -person_capital_gains_for_agi)",
    ),
    _generated_person_rule(
        "person_has_positive_capital_gains_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person capital gains",
        formula="person_positive_capital_gains_for_agi > 0",
    ),
    _generated_person_rule(
        "person_has_capital_losses_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying person capital losses",
        formula="person_capital_losses_for_agi > 0",
    ),
    _generated_person_rule(
        "person_positive_self_employment_income_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 61 self-employment leaves",
        formula="max(0, person_self_employment_income_for_qbid)",
    ),
    _generated_person_rule(
        "person_self_employment_loss_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), projected from ECPS self-employment leaves",
        formula="max(0, -person_self_employment_income_for_qbid)",
    ),
    _generated_person_rule(
        "person_has_positive_self_employment_income_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person self-employment income",
        formula="person_positive_self_employment_income_for_agi > 0",
    ),
    _generated_person_rule(
        "person_has_self_employment_loss_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying person self-employment losses",
        formula="person_self_employment_loss_for_agi > 0",
    ),
    _generated_person_rule(
        "person_positive_rental_income_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 61 rental leaves",
        formula="max(0, person_rental_income_for_qbid)",
    ),
    _generated_person_rule(
        "person_rental_loss_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), projected from ECPS rental leaves",
        formula="max(0, -person_rental_income_for_qbid)",
    ),
    _generated_person_rule(
        "person_has_positive_rental_income_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person rental income",
        formula="person_positive_rental_income_for_agi > 0",
    ),
    _generated_person_rule(
        "person_has_rental_loss_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying person rental losses",
        formula="person_rental_loss_for_agi > 0",
    ),
    _generated_person_rule(
        "person_positive_dividend_income_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 61 dividend leaves",
        formula="max(0, person_dividend_income)",
    ),
    _generated_person_rule(
        "person_has_positive_dividend_income_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person dividend income",
        formula="person_positive_dividend_income_for_agi > 0",
    ),
    _generated_person_rule(
        "person_positive_taxable_interest_income_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 61 interest leaves",
        formula="max(0, person_taxable_interest_income)",
    ),
    _generated_person_rule(
        "person_has_positive_taxable_interest_income_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person taxable interest income",
        formula="person_positive_taxable_interest_income_for_agi > 0",
    ),
    _generated_person_rule(
        "person_positive_pension_income_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 61 pension leaves",
        formula="max(0, person_pension_income)",
    ),
    _generated_person_rule(
        "person_has_positive_pension_income_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person pension income",
        formula="person_positive_pension_income_for_agi > 0",
    ),
    _generated_person_rule(
        "person_positive_unemployment_compensation_for_agi",
        dtype="Money",
        unit="USD",
        source="PolicyEngine gross-income convention for 26 USC 85 unemployment leaves",
        formula="max(0, person_unemployment_compensation)",
    ),
    _generated_person_rule(
        "person_has_positive_unemployment_compensation_for_agi",
        dtype="Judgment",
        source="Oracle comparison bridge identifying positive person unemployment compensation",
        formula="person_positive_unemployment_compensation_for_agi > 0",
    ),
    _generated_person_rule(
        "person_is_tax_unit_head_for_co",
        dtype="Judgment",
        source="Oracle comparison bridge identifying the tax-unit head for Colorado person-level subtractions",
        formula="is_taxpayer and not is_spouse",
    ),
    _generated_person_rule(
        "person_is_tax_unit_spouse_for_co",
        dtype="Judgment",
        source="Oracle comparison bridge identifying the tax-unit spouse for Colorado person-level subtractions",
        formula="is_spouse",
    ),
    _generated_person_rule(
        "person_self_employment_net_earnings_before_paragraph_12",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1402(a) to person-level ECPS self-employment leaves",
        formula="max(0, person_self_employment_income_for_qbid)",
    ),
    _generated_person_rule(
        "person_self_employment_net_earnings_after_paragraph_12",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1402(a)(12) to person-level ECPS self-employment leaves",
        formula=(
            "person_self_employment_net_earnings_before_paragraph_12 "
            "* (1 - (self_employment_tax_equivalent_deduction_fraction "
            "* (self_employment_oasdi_tax_rate "
            "+ self_employment_hospital_insurance_tax_rate)))"
        ),
    ),
    _generated_person_rule(
        "person_taxable_self_employment_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1402(b)(2) to person-level ECPS self-employment leaves",
        formula=(
            "if person_self_employment_net_earnings_after_paragraph_12 "
            "< self_employment_net_earnings_exemption: "
            "0 "
            "else: person_self_employment_net_earnings_after_paragraph_12"
        ),
    ),
    _generated_person_rule(
        "person_social_security_taxable_self_employment_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying the 26 USC 1401(a) wage-base interaction to person-level ECPS leaves",
        formula=(
            "min("
            "person_taxable_self_employment_income, "
            "max(0, social_security_wage_base - employee_payroll_wages)"
            ")"
        ),
    ),
    _generated_person_rule(
        "person_self_employment_oasdi_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1401(a) to person-level ECPS self-employment leaves",
        formula=(
            "person_social_security_taxable_self_employment_income "
            "* self_employment_oasdi_tax_rate"
        ),
    ),
    _generated_person_rule(
        "person_self_employment_hospital_insurance_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 1401(b)(1) to person-level ECPS self-employment leaves",
        formula=(
            "person_taxable_self_employment_income "
            "* self_employment_hospital_insurance_tax_rate"
        ),
    ),
    _generated_person_rule(
        "person_self_employment_1401_tax_before_additional_medicare",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge summing 26 USC 1401(a) and (b)(1) person-level self-employment taxes",
        formula=(
            "person_self_employment_oasdi_tax "
            "+ person_self_employment_hospital_insurance_tax"
        ),
    ),
    _generated_person_rule(
        "person_self_employment_tax_ald_for_qbid",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 164(f) to person-level self-employment taxes for AGI and QBI",
        formula=(
            "person_self_employment_1401_tax_before_additional_medicare "
            "* self_employment_tax_deduction_fraction"
        ),
    ),
    _generated_person_rule(
        "person_adjusted_earnings_for_eitc",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine person-level adjusted earnings for 26 USC 32",
        formula=(
            "max("
            "0, "
            "person_payroll_earnings "
            "+ person_self_employment_income_for_qbid "
            "- person_self_employment_tax_ald_for_qbid"
            ")"
        ),
    ),
    _generated_person_rule(
        "person_has_adjusted_earnings_for_eitc",
        dtype="Judgment",
        source="Oracle comparison bridge identifying tax-unit filers with positive adjusted earnings for 26 USC 32",
        formula="person_adjusted_earnings_for_eitc > 0",
    ),
    _generated_person_rule(
        "person_has_self_employment_tax_ald_for_qbid",
        dtype="Judgment",
        source="Oracle comparison bridge identifying tax-unit members with person-level 26 USC 164(f) deductions",
        formula="person_self_employment_tax_ald_for_qbid > 0",
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
            "+ person_rental_income_for_qbid "
            "- person_self_employment_tax_ald_for_qbid"
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
            ")"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "self_employment_tax_ald_for_agi",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge summing member-level 26 USC 164(f) deductions for PolicyEngine AGI alignment",
        formula=(
            "sum_where("
            "business_income_of_tax_unit, "
            "person_self_employment_tax_ald_for_qbid, "
            "person_has_self_employment_tax_ald_for_qbid"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "adjusted_net_capital_gain_for_qbid",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge approximating 26 USC 199A(a)(2) capital-gain cap from ECPS leaves",
        formula=(
            "max(0, capital_gains_tax_long_term_capital_gains "
            "+ capital_gains_tax_qualified_dividend_income)"
        ),
    ),
    _generated_tax_unit_rule(
        "net_capital_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine net capital gains before loss limitation",
        formula=(
            "capital_gains_tax_long_term_capital_gains "
            "+ capital_gains_tax_short_term_capital_gains"
        ),
    ),
    _generated_tax_unit_rule(
        "loss_limited_net_capital_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying Schedule D capital-loss limits for PolicyEngine alignment",
        formula=(
            "if filing_status == 2: "
            "max(-1500, net_capital_gains) "
            "else: max(-3000, net_capital_gains)"
        ),
    ),
    _generated_tax_unit_rule(
        "non_sch_d_capital_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge default for capital gains not reported on Schedule D",
        formula="0",
    ),
    _generated_tax_unit_rule(
        "investment_income_form_4952",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge default where ECPS does not provide Form 4952 investment income election inputs",
        formula="0",
    ),
    _generated_tax_unit_rule(
        "has_qualified_dividends_or_long_term_capital_gains",
        dtype="Judgment",
        source="Oracle comparison bridge matching PolicyEngine's qualified-dividend and long-term-gain gate",
        formula=(
            "loss_limited_net_capital_gains > 0 "
            "or net_capital_gains > 0 "
            "or capital_gains_tax_long_term_capital_gains > 0 "
            "or non_sch_d_capital_gains > 0 "
            "or capital_gains_tax_qualified_dividend_income > 0"
        ),
    ),
    _generated_tax_unit_rule(
        "dividend_income_reduced_by_investment_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Schedule D worksheet qualified-dividend reduction",
        formula=(
            "max("
            "0, "
            "capital_gains_tax_qualified_dividend_income "
            "- max(0, investment_income_form_4952)"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "capital_gains_worksheet_line_9",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Schedule D worksheet line 9",
        formula=(
            "max("
            "0, "
            "(if non_sch_d_capital_gains > 0: "
            "non_sch_d_capital_gains "
            "else: "
            "max("
            "0, "
            "min("
            "capital_gains_tax_long_term_capital_gains "
            "+ capital_gains_tax_qualified_dividend_income, "
            "net_capital_gains"
            ") "
            ") + non_sch_d_capital_gains"
            ") - min(0, investment_income_form_4952)"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "capital_gains_worksheet_line_10",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Schedule D worksheet line 10",
        formula=(
            "if has_qualified_dividends_or_long_term_capital_gains: "
            "dividend_income_reduced_by_investment_income "
            "+ capital_gains_worksheet_line_9 "
            "else: "
            "max("
            "0, "
            "min("
            "capital_gains_tax_long_term_capital_gains "
            "+ capital_gains_tax_qualified_dividend_income, "
            "net_capital_gains"
            ")"
            ") + non_sch_d_capital_gains"
        ),
    ),
    _generated_tax_unit_rule(
        "capital_gains_worksheet_line_13",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Schedule D worksheet line 13",
        formula=(
            "if has_qualified_dividends_or_long_term_capital_gains: "
            "capital_gains_worksheet_line_10 "
            "- min("
            "capital_gains_worksheet_line_9, "
            "unrecaptured_section_1250_gain "
            "+ capital_gains_28_percent_rate_gain"
            ") "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "capital_gains_worksheet_line_14",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Schedule D worksheet line 14",
        formula=(
            "if has_qualified_dividends_or_long_term_capital_gains: "
            "max(0, taxable_income - capital_gains_worksheet_line_13) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "capital_gains_worksheet_line_19",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Schedule D worksheet line 19",
        formula=(
            "if has_qualified_dividends_or_long_term_capital_gains: "
            "max("
            "min("
            "capital_gains_worksheet_line_14, "
            "min(capital_gains_zero_rate_threshold, taxable_income)"
            "), "
            "max(0, taxable_income - capital_gains_worksheet_line_10)"
            ") "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_part_iii_required",
        dtype="Judgment",
        source="Oracle comparison bridge applying Form 6251 Part III when Schedule D worksheet lines are present",
        formula=(
            "capital_gains_worksheet_line_10 > 0 "
            "or capital_gains_worksheet_line_13 > 0 "
            "or capital_gains_worksheet_line_14 > 0 "
            "or capital_gains_worksheet_line_19 > 0 "
            "or unrecaptured_section_1250_gain > 0"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_15_capped_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 15",
        formula=(
            "min("
            "capital_gains_worksheet_line_13 "
            "+ unrecaptured_section_1250_gain, "
            "capital_gains_worksheet_line_10"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_16_capped_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 16",
        formula="min(amt_capital_gain_line_15_capped_gains, amt_income_less_exemptions)",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_17_excess_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 17",
        formula="max(0, amt_income_less_exemptions - amt_capital_gain_line_16_capped_income)",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_18_excess_income_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying 26 USC 55 AMT rates to Form 6251 Part III line 17",
        formula=(
            "amt_lower_rate "
            "* min("
            "amt_capital_gain_line_17_excess_income, "
            "amt_twenty_eight_percent_threshold"
            ") "
            "+ amt_higher_rate "
            "* max("
            "0, "
            "amt_capital_gain_line_17_excess_income "
            "- amt_twenty_eight_percent_threshold"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_21_reduced_zero_rate_bracket",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 21",
        formula="max(0, capital_gains_zero_rate_threshold - capital_gains_worksheet_line_14)",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_22_smaller_income_or_gain",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 22",
        formula="min(amt_income_less_exemptions, capital_gains_worksheet_line_13)",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_23_zero_rate_amount",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Form 6251 Part III line 23",
        formula=(
            "min("
            "amt_capital_gain_line_22_smaller_income_or_gain, "
            "amt_capital_gain_line_21_reduced_zero_rate_bracket"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_24_taxable_gain_after_zero_rate",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 24",
        formula=(
            "max("
            "0, "
            "amt_capital_gain_line_22_smaller_income_or_gain "
            "- amt_capital_gain_line_23_zero_rate_amount"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_29_reduced_fifteen_rate_bracket",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 29",
        formula=(
            "max("
            "0, "
            "capital_gains_fifteen_percent_threshold "
            "- (capital_gains_worksheet_line_14 "
            "+ amt_capital_gain_line_23_zero_rate_amount)"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_30_fifteen_rate_gain",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 30",
        formula=(
            "min("
            "amt_capital_gain_line_24_taxable_gain_after_zero_rate, "
            "amt_capital_gain_line_29_reduced_fifteen_rate_bracket"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_31_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 31",
        formula="amt_capital_gain_line_30_fifteen_rate_gain * capital_gains_fifteen_percent_rate",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_32_taxed_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 32",
        formula=(
            "amt_capital_gain_line_23_zero_rate_amount "
            "+ amt_capital_gain_line_30_fifteen_rate_gain"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_33_twenty_rate_gain",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 33",
        formula=(
            "max("
            "0, "
            "amt_capital_gain_line_22_smaller_income_or_gain "
            "- amt_capital_gain_line_32_taxed_gains"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_34_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 34",
        formula="amt_capital_gain_line_33_twenty_rate_gain * capital_gains_twenty_percent_rate",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_35_taxed_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 35",
        formula=(
            "amt_capital_gain_line_17_excess_income "
            "+ amt_capital_gain_line_32_taxed_gains "
            "+ amt_capital_gain_line_33_twenty_rate_gain"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_36_excess",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching Form 6251 Part III line 36",
        formula="max(0, amt_income_less_exemptions - amt_capital_gain_line_35_taxed_income)",
    ),
    _generated_tax_unit_rule(
        "amt_capital_gain_line_37_excess_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching 26 USC 55(b)(3)(E) excess capital-gain tax",
        formula=(
            "if unrecaptured_section_1250_gain == 0: "
            "0 "
            "else: amt_capital_gain_line_36_excess "
            "* unrecaptured_section_1250_gain_rate"
        ),
    ),
    _generated_tax_unit_rule(
        "amt_tax_including_capital_gains",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge computing Form 6251 Part III preferential-gain tax",
        formula=(
            "amt_capital_gain_line_18_excess_income_tax "
            "+ amt_capital_gain_line_31_tax "
            "+ amt_capital_gain_line_34_tax "
            "+ amt_capital_gain_line_37_excess_tax"
        ),
    ),
    _generated_data_relation_rule(
        "co_withheld_income_tax_member_of_tax_unit",
        source="Oracle comparison bridge relating Colorado tax-unit members to person-level withheld income tax proxies",
    ),
    _generated_data_relation_rule(
        "co_dependent_of_tax_unit",
        source="Oracle comparison bridge relating Colorado tax units to dependent children for state refundable credits",
    ),
    _generated_person_rule(
        "person_agi_for_co_withholding",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine's person-level Colorado withheld-tax proxy from ECPS income leaves",
        formula=(
            "max("
            "0, "
            "person_payroll_earnings "
            "+ person_self_employment_income_for_qbid "
            "+ person_rental_income_for_qbid "
            "+ person_dividend_income "
            "+ person_taxable_interest_income "
            "+ person_short_term_capital_gains "
            "+ person_long_term_capital_gains "
            "+ person_pension_income "
            "+ person_unemployment_compensation"
            ")"
        ),
    ),
    _generated_person_rule(
        "person_gross_income_for_co_withholding_count",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge identifying filers with income for Colorado withholding proxy",
        formula=(
            "max(0, person_payroll_earnings) "
            "+ person_positive_self_employment_income_for_agi "
            "+ person_positive_rental_income_for_agi "
            "+ person_positive_capital_gains_for_agi "
            "+ person_positive_dividend_income_for_agi "
            "+ person_positive_taxable_interest_income_for_agi "
            "+ person_positive_pension_income_for_agi "
            "+ person_positive_unemployment_compensation_for_agi "
            "+ max(0, person_social_security_benefits)"
        ),
    ),
    _generated_person_rule(
        "person_has_gross_income_for_co_withholding_count",
        dtype="Judgment",
        source="Oracle comparison bridge identifying filers with Colorado withholding income",
        formula="person_gross_income_for_co_withholding_count > 0",
    ),
    _generated_person_rule(
        "person_co_withheld_income_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge matching PolicyEngine Colorado withheld income tax proxy",
        formula=(
            "co_income_tax_rate "
            "* max(0, person_agi_for_co_withholding "
            "- co_withholding_single_standard_deduction)"
        ),
    ),
    _generated_person_rule(
        "person_has_co_withheld_income_tax",
        dtype="Judgment",
        source="Oracle comparison bridge identifying tax-unit members with positive Colorado withheld income tax",
        formula="person_co_withheld_income_tax > 0",
    ),
    _generated_person_rule(
        "co_ctc_eligible_child",
        dtype="Judgment",
        source="C.R.S. 39-22-129 Colorado child tax credit eligible child proxy from ECPS household facts",
        formula="oracle_person_is_tax_unit_dependent and oracle_person_age < co_ctc_child_age_threshold",
    ),
    _generated_person_rule(
        "co_family_affordability_child_eligible",
        dtype="Judgment",
        source="Colorado HB24-1311 family affordability credit qualifying child proxy from ECPS household facts",
        formula="oracle_person_is_qualifying_child_dependent and oracle_person_age < 17",
    ),
    _generated_person_rule(
        "co_family_affordability_child_age_multiplier",
        dtype="Decimal",
        source="Colorado HB24-1311 family affordability credit age multiplier",
        formula=(
            "if oracle_person_age < 6: "
            "1 "
            "else: "
            "if oracle_person_age < 17: 0.75 else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "state_withheld_income_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge computing Colorado state withheld income tax for federal SALT itemization",
        formula=(
            "if is_colorado_tax_unit: "
            "co_income_tax_rate "
            "* max("
            "0, "
            "adjusted_gross_income "
            "- co_withholding_single_standard_deduction "
            "* co_withholding_filer_count"
            ") "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_withholding_filer_count",
        dtype="Integer",
        source="Oracle comparison bridge counting filers with positive Colorado withholding income",
        formula=(
            "count_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_has_gross_income_for_co_withholding_count"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "state_and_local_sales_or_income_tax",
        dtype="Money",
        unit="USD",
        source="26 USC 164(a), resolved against available ECPS sales and income tax leaves",
        formula=(
            "max("
            "state_withheld_income_tax + local_income_tax, "
            "state_sales_tax + local_sales_tax"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "salt",
        dtype="Money",
        unit="USD",
        source="26 USC 164(a), state and local taxes before the statutory cap",
        formula="state_and_local_sales_or_income_tax + real_estate_taxes",
    ),
    _generated_tax_unit_rule(
        "salt_cap_max",
        dtype="Money",
        unit="USD",
        source="26 USC 164(b)(6), resolved for 2026 oracle comparison",
        formula=(
            "if filing_status == 2: "
            "salt_cap_separate_2026 "
            "else: salt_cap_joint_or_non_separate_2026"
        ),
    ),
    _generated_tax_unit_rule(
        "salt_cap_phaseout_threshold",
        dtype="Money",
        unit="USD",
        source="26 USC 164(b)(6), resolved for 2026 oracle comparison",
        formula=(
            "if filing_status == 2: "
            "salt_cap_phaseout_threshold_separate_2026 "
            "else: salt_cap_phaseout_threshold_joint_or_non_separate_2026"
        ),
    ),
    _generated_tax_unit_rule(
        "salt_cap_floor",
        dtype="Money",
        unit="USD",
        source="26 USC 164(b)(6), resolved for 2026 oracle comparison",
        formula=(
            "if filing_status == 2: "
            "salt_cap_floor_separate "
            "else: salt_cap_floor_joint_or_non_separate"
        ),
    ),
    _generated_tax_unit_rule(
        "salt_cap_phaseout_reduction",
        dtype="Money",
        unit="USD",
        source="26 USC 164(b)(6), resolved for 2026 oracle comparison",
        formula=(
            "salt_cap_phaseout_rate "
            "* max(0, adjusted_gross_income - salt_cap_phaseout_threshold)"
        ),
    ),
    _generated_tax_unit_rule(
        "salt_cap",
        dtype="Money",
        unit="USD",
        source="26 USC 164(b)(6), resolved for 2026 oracle comparison",
        formula=(
            "max("
            "salt_cap_floor, "
            "max(0, salt_cap_max - salt_cap_phaseout_reduction)"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "salt_deduction",
        dtype="Money",
        unit="USD",
        source="26 USC 164(b)(6), capped state and local tax deduction",
        formula="min(salt_cap, salt)",
    ),
    _generated_tax_unit_rule(
        "interest_deduction",
        dtype="Money",
        unit="USD",
        source="26 USC 163, projected from mortgage-interest case leaves",
        formula="deductible_mortgage_interest",
    ),
    _generated_tax_unit_rule(
        "total_itemized_taxable_income_deductions",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge aggregating itemized deduction leaves",
        formula=(
            "salt_deduction "
            "+ interest_deduction "
            "+ itemized_medical_expenses "
            "+ casualty_loss_deduction "
            "+ charitable_deduction "
            "+ misc_deduction"
        ),
    ),
    _generated_tax_unit_rule(
        "itemized_taxable_income_deductions",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge computing itemized deductions from leaf inputs",
        formula=(
            "max("
            "0, "
            "total_itemized_taxable_income_deductions "
            "- itemized_taxable_income_deductions_reduction"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "qualified_passenger_vehicle_loan_interest_deduction",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge supplying PolicyEngine's 2026 qualified passenger vehicle loan interest deduction leaf",
        formula="auto_loan_interest_deduction",
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
        "capital_losses",
        dtype="Money",
        unit="USD",
        source="26 USC 1211, capital losses expressed as a non-negative amount",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_capital_losses_for_agi, "
            "person_has_capital_losses_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "capital_loss_limit",
        dtype="Money",
        unit="USD",
        source="26 USC 1211(b), capital-loss limit selected by filing status",
        formula=(
            "if filing_status == 2: "
            "capital_loss_limit_separate "
            "else: capital_loss_limit_joint_or_non_separate"
        ),
    ),
    _generated_tax_unit_rule(
        "limited_capital_loss",
        dtype="Money",
        unit="USD",
        source="26 USC 1211(b), limited capital loss deduction",
        formula="min(capital_loss_limit, capital_losses)",
    ),
    _generated_tax_unit_rule(
        "business_loss_limit",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), excess business-loss threshold selected by filing status",
        formula=(
            "if filing_status == 1: "
            "business_loss_limit_joint_2026 "
            "else: business_loss_limit_other_2026"
        ),
    ),
    _generated_tax_unit_rule(
        "business_income_for_loss_limit",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), positive business income before excess-loss limitation",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_self_employment_income_for_agi, "
            "person_has_positive_self_employment_income_for_agi"
            ") "
            "+ sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_rental_income_for_agi, "
            "person_has_positive_rental_income_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "business_loss_for_loss_limit",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), business losses before excess-loss limitation",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_self_employment_loss_for_agi, "
            "person_has_self_employment_loss_for_agi"
            ") "
            "+ sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_rental_loss_for_agi, "
            "person_has_rental_loss_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "limited_business_loss",
        dtype="Money",
        unit="USD",
        source="26 USC 461(l), excess business-loss limitation",
        formula=(
            "min("
            "business_loss_for_loss_limit, "
            "business_income_for_loss_limit + business_loss_limit"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "loss_ald",
        dtype="Money",
        unit="USD",
        source="26 USC 165, 461(l), and 1211, loss deductions above the line",
        formula="limited_business_loss + limited_capital_loss",
    ),
    _generated_tax_unit_rule(
        "positive_capital_gains_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61, positive capital gains included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_capital_gains_for_agi, "
            "person_has_positive_capital_gains_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "positive_self_employment_income_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61, positive self-employment income included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_self_employment_income_for_agi, "
            "person_has_positive_self_employment_income_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "positive_rental_income_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61, positive rental income included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_rental_income_for_agi, "
            "person_has_positive_rental_income_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "positive_dividend_income_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61, positive dividend income included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_dividend_income_for_agi, "
            "person_has_positive_dividend_income_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "positive_taxable_interest_income_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61, positive taxable interest included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_taxable_interest_income_for_agi, "
            "person_has_positive_taxable_interest_income_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "positive_pension_income_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 61, positive pension income included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_pension_income_for_agi, "
            "person_has_positive_pension_income_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "positive_unemployment_compensation_for_agi",
        dtype="Money",
        unit="USD",
        source="26 USC 85, positive unemployment compensation included in gross income",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_positive_unemployment_compensation_for_agi, "
            "person_has_positive_unemployment_compensation_for_agi"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "gross_income_before_social_security_benefits",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge aggregating ECPS leaf income facts before applying 26 USC 86",
        formula=(
            "wages "
            "+ positive_self_employment_income_for_agi "
            "+ positive_rental_income_for_agi "
            "+ positive_capital_gains_for_agi "
            "+ positive_dividend_income_for_agi "
            "+ positive_taxable_interest_income_for_agi "
            "+ positive_pension_income_for_agi "
            "+ positive_unemployment_compensation_for_agi "
            "+ alaska_permanent_fund_dividend"
        ),
    ),
    _generated_tax_unit_rule(
        "alaska_permanent_fund_dividend",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge applying Alaska Permanent Fund Dividend to Alaska tax-unit filers",
        formula=(
            "alaska_permanent_fund_dividend_amount "
            "* alaska_permanent_fund_dividend_eligible_person_count"
        ),
    ),
    _generated_tax_unit_rule(
        "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge routing ECPS capital-gain leaves into 26 USC 1411(c)(1)(A)(iii)",
        formula=(
            "capital_gains_tax_short_term_capital_gains "
            "+ capital_gains_tax_long_term_capital_gains"
        ),
    ),
    _generated_tax_unit_rule(
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge applying 26 USC 164(f) before 26 USC 86",
        formula=(
            "gross_income_before_social_security_benefits "
            "- loss_ald "
            "- self_employment_tax_ald_for_agi"
        ),
    ),
    _generated_tax_unit_rule(
        "adjusted_gross_income_before_listed_exclusions_and_social_security_inclusion",
        dtype="Money",
        unit="USD",
        source="Oracle composition bridge supplying 26 USC 86(b)(2) modified-AGI base",
        formula=(
            "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933"
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
        "co_additions",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3), resolved from encoded Colorado addition leaves available to the oracle bridge",
        formula=(
            "co_state_addback "
            "+ co_federal_deduction_addback "
            "+ co_qualified_business_income_deduction_addback"
        ),
    ),
    _generated_tax_unit_rule(
        "co_state_addback_line_a",
        dtype="Money",
        unit="USD",
        source="Colorado state income tax addback worksheet, 2025 DR 0104 Book Additions Line 2",
        formula=(
            "if state_withheld_income_tax + real_estate_taxes > salt_deduction: "
            "max(0, salt_deduction - real_estate_taxes) "
            "else: max(0, state_withheld_income_tax)"
        ),
    ),
    _generated_tax_unit_rule(
        "co_state_addback_line_d",
        dtype="Money",
        unit="USD",
        source="Colorado state income tax addback worksheet, 2025 DR 0104 Book Additions Line 2",
        formula=(
            "max("
            "0, "
            "total_itemized_taxable_income_deductions - standard_deduction"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_state_addback",
        dtype="Money",
        unit="USD",
        source="Colorado state income tax addback worksheet, 2025 DR 0104 Book Additions Line 2",
        formula=(
            "if individual_makes_election_to_itemize_deductions_for_taxable_year: "
            "min(co_state_addback_line_a, co_state_addback_line_d) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_federal_deduction_addback_exemption",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(p), exemption selected by filing status",
        formula=(
            "if filing_status == 1: "
            "co_federal_deduction_addback_joint_exemption "
            "else: co_federal_deduction_addback_other_exemption"
        ),
    ),
    _generated_tax_unit_rule(
        "co_taxable_income_deductions_for_addback",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(p), federal deductions subject to Colorado addback",
        # The addback reaches only the section 63 itemized-or-standard
        # deduction; the other current-law deductions (199A, 170(p), tips,
        # overtime, car-loan interest, senior bonus) stay out of it.
        formula=(
            "if individual_makes_election_to_itemize_deductions_for_taxable_year: "
            "itemized_taxable_income_deductions "
            "else: standard_deduction"
        ),
    ),
    _generated_tax_unit_rule(
        "co_federal_deduction_addback",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(p), federal deduction addback",
        formula=(
            "if adjusted_gross_income > co_federal_deduction_addback_agi_threshold: "
            "max("
            "0, "
            "co_taxable_income_deductions_for_addback "
            "- co_federal_deduction_addback_exemption"
            ") "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_qualified_business_income_deduction_addback",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(3)(o), qualified business income deduction addback",
        formula=(
            "if filing_status == 1: "
            "if adjusted_gross_income > co_qbid_addback_joint_agi_threshold: "
            "qualified_business_income_deduction "
            "else: 0 "
            "else: "
            "if adjusted_gross_income > co_qbid_addback_other_agi_threshold: "
            "qualified_business_income_deduction "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_subtractions",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4), resolved from encoded Colorado subtraction leaves available to the oracle bridge",
        formula=(
            "max("
            "0, "
            "co_social_security_subtraction "
            "+ co_pension_subtraction"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_age",
        dtype="Integer",
        source="Oracle comparison bridge projecting Colorado head age for person-level subtractions",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "oracle_person_age, "
            "person_is_tax_unit_head_for_co"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_age",
        dtype="Integer",
        source="Oracle comparison bridge projecting Colorado spouse age for person-level subtractions",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "oracle_person_age, "
            "person_is_tax_unit_spouse_for_co"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_social_security_benefits",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge projecting Colorado head Social Security benefits for person-level subtractions",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_social_security_benefits, "
            "person_is_tax_unit_head_for_co"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_social_security_benefits",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge projecting Colorado spouse Social Security benefits for person-level subtractions",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_social_security_benefits, "
            "person_is_tax_unit_spouse_for_co"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_taxable_social_security",
        dtype="Money",
        unit="USD",
        source="PolicyEngine taxable Social Security allocation, assigning non-spouse residual to the head",
        formula=(
            "max("
            "0, "
            "social_security_benefits_included_in_gross_income "
            "- co_spouse_taxable_social_security"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_taxable_social_security",
        dtype="Money",
        unit="USD",
        source="PolicyEngine taxable Social Security allocation to the tax-unit spouse",
        formula=(
            "if title_II_monthly_benefits_received_during_taxable_year > 0: "
            "social_security_benefits_included_in_gross_income "
            "* co_spouse_social_security_benefits "
            "/ title_II_monthly_benefits_received_during_taxable_year "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_social_security_subtraction",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(f), head-level Colorado Social Security subtraction",
        formula=(
            "if co_head_age >= 65: "
            "co_head_taxable_social_security "
            "else: "
            "if co_head_age >= 55: "
            "min(co_head_taxable_social_security, co_pension_subtraction_younger_cap) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_social_security_subtraction",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(f), spouse-level Colorado Social Security subtraction",
        formula=(
            "if co_spouse_age >= 65: "
            "co_spouse_taxable_social_security "
            "else: "
            "if co_spouse_age >= 55: "
            "min(co_spouse_taxable_social_security, co_pension_subtraction_younger_cap) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_social_security_subtraction",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(f), summed head/spouse Colorado Social Security subtraction",
        formula=(
            "co_head_social_security_subtraction "
            "+ co_spouse_social_security_subtraction"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_pension_subtraction_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge projecting Colorado head pension income for person-level subtractions",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_pension_income, "
            "person_is_tax_unit_head_for_co"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_pension_subtraction_income",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge projecting Colorado spouse pension income for person-level subtractions",
        formula=(
            "sum_where("
            "filer_adjusted_earnings_of_tax_unit, "
            "person_pension_income, "
            "person_is_tax_unit_spouse_for_co"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_pension_subtraction_cap_after_social_security",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g)(III), head pension cap after Colorado Social Security subtraction",
        formula=(
            "if co_head_age >= 65: "
            "max(0, co_pension_subtraction_older_cap "
            "- co_head_social_security_subtraction) "
            "else: "
            "if co_head_age >= 55: "
            "max(0, co_pension_subtraction_younger_cap "
            "- co_head_social_security_subtraction) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_pension_subtraction_cap_after_social_security",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g)(III), spouse pension cap after Colorado Social Security subtraction",
        formula=(
            "if co_spouse_age >= 65: "
            "max(0, co_pension_subtraction_older_cap "
            "- co_spouse_social_security_subtraction) "
            "else: "
            "if co_spouse_age >= 55: "
            "max(0, co_pension_subtraction_younger_cap "
            "- co_spouse_social_security_subtraction) "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_head_pension_subtraction",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g), head Colorado pension and annuity subtraction",
        formula=(
            "min("
            "max(0, co_head_pension_subtraction_income), "
            "co_head_pension_subtraction_cap_after_social_security"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_spouse_pension_subtraction",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g), spouse Colorado pension and annuity subtraction",
        formula=(
            "min("
            "max(0, co_spouse_pension_subtraction_income), "
            "co_spouse_pension_subtraction_cap_after_social_security"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_pension_subtraction",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(4)(g), pension and annuity subtraction",
        formula=(
            "co_head_pension_subtraction "
            "+ co_spouse_pension_subtraction"
        ),
    ),
    _generated_tax_unit_rule(
        "co_taxable_income",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(1.7), Colorado taxable income starts from federal taxable income",
        formula="max(0, taxable_income + co_additions - co_subtractions)",
    ),
    _generated_tax_unit_rule(
        "co_income_tax_before_non_refundable_credits",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-104(1.7), Colorado flat-rate income tax",
        formula="co_taxable_income * co_income_tax_rate",
    ),
    _generated_tax_unit_rule(
        "co_non_refundable_credits",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge default for unencoded Colorado non-refundable credits",
        formula="0",
    ),
    _generated_tax_unit_rule(
        "co_income_tax_before_refundable_credits",
        dtype="Money",
        unit="USD",
        source="Colorado income tax before refundable credits",
        formula=(
            "max("
            "0, "
            "co_income_tax_before_non_refundable_credits "
            "- co_non_refundable_credits"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_sales_tax_refund_eligible",
        dtype="Judgment",
        source="Colorado sales tax refund eligibility, matching PolicyEngine 2026 oracle comparison",
        formula=(
            "age_at_close_of_taxable_year >= 18 "
            "or filing_status_is_joint_return "
            "or co_income_tax_before_non_refundable_credits > 0 "
            "or wages > 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_sales_tax_refund",
        dtype="Money",
        unit="USD",
        source="Colorado sales tax refund, matching PolicyEngine 2026 oracle comparison",
        formula=(
            "if co_sales_tax_refund_eligible: "
            "co_sales_tax_refund_base "
            "* co_sales_tax_refund_filing_status_multiplier "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_refundable_credits",
        dtype="Money",
        unit="USD",
        source="Colorado refundable credits resolved from encoded bridge components",
        formula=(
            "co_sales_tax_refund"
            " + co_eitc"
            " + co_ctc"
            " + co_family_affordability_credit"
        ),
    ),
    _generated_tax_unit_rule(
        "co_eitc",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-123.5 Colorado earned income tax credit",
        formula="eitc * co_eitc_match_2026",
    ),
    _generated_tax_unit_rule(
        "co_ctc_eligible_children_count",
        dtype="Integer",
        source="C.R.S. 39-22-129 child tax credit eligible children",
        formula="count_where(co_dependent_of_tax_unit, co_ctc_eligible_child)",
    ),
    _generated_tax_unit_rule(
        "co_ctc_amount_per_child",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 child tax credit amount table",
        formula=(
            "if filing_status == 1: "
            "if adjusted_gross_income <= co_ctc_joint_first_threshold_2026: "
            "co_ctc_high_amount "
            "else: "
            "if adjusted_gross_income <= co_ctc_joint_second_threshold_2026: "
            "co_ctc_middle_amount "
            "else: "
            "if adjusted_gross_income <= co_ctc_joint_third_threshold_2026: "
            "co_ctc_low_amount "
            "else: 0 "
            "else: "
            "if adjusted_gross_income <= co_ctc_other_first_threshold_2026: "
            "co_ctc_high_amount "
            "else: "
            "if adjusted_gross_income <= co_ctc_other_second_threshold_2026: "
            "co_ctc_middle_amount "
            "else: "
            "if adjusted_gross_income <= co_ctc_other_third_threshold_2026: "
            "co_ctc_low_amount "
            "else: 0"
        ),
    ),
    _generated_tax_unit_rule(
        "co_ctc",
        dtype="Money",
        unit="USD",
        source="C.R.S. 39-22-129 Colorado child tax credit",
        formula="co_ctc_eligible_children_count * co_ctc_amount_per_child",
    ),
    _generated_tax_unit_rule(
        "co_family_affordability_child_units",
        dtype="Decimal",
        source="Colorado HB24-1311 family affordability credit age-weighted child count",
        formula=(
            "sum_where("
            "co_dependent_of_tax_unit, "
            "co_family_affordability_child_age_multiplier, "
            "co_family_affordability_child_eligible"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_family_affordability_pre_reduction_credit",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 family affordability credit before AGI reduction",
        formula=(
            "co_family_affordability_child_amount_2026 "
            "* co_family_affordability_child_units"
        ),
    ),
    _generated_tax_unit_rule(
        "co_family_affordability_reduction_threshold",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 family affordability credit reduction threshold",
        formula=(
            "if filing_status == 1: "
            "co_family_affordability_reduction_threshold_joint_2026 "
            "else: co_family_affordability_reduction_threshold_other_2026"
        ),
    ),
    _generated_tax_unit_rule(
        "co_family_affordability_reduction_fraction",
        dtype="Rate",
        source="Colorado HB24-1311 family affordability credit reduction",
        formula=(
            "min("
            "1, "
            "ceil("
            "max(0, adjusted_gross_income - co_family_affordability_reduction_threshold) "
            "/ co_family_affordability_reduction_increment_2026"
            ") * co_family_affordability_reduction_rate"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_family_affordability_credit",
        dtype="Money",
        unit="USD",
        source="Colorado HB24-1311 family affordability credit",
        formula=(
            "co_family_affordability_pre_reduction_credit "
            "* (1 - co_family_affordability_reduction_fraction)"
        ),
    ),
    _generated_tax_unit_rule(
        "co_sales_tax_refund_base",
        dtype="Money",
        unit="USD",
        source="Colorado 2025 state sales tax refund table, carried forward by PolicyEngine for 2026 oracle comparison",
        formula=(
            "19 "
            "+ (if co_modified_agi >= 52001: 6 else: 0) "
            "+ (if co_modified_agi >= 105001: 4 else: 0) "
            "+ (if co_modified_agi >= 168001: 6 else: 0) "
            "+ (if co_modified_agi >= 233001: 2 else: 0) "
            "+ (if co_modified_agi >= 299001: 22 else: 0)"
        ),
    ),
    _generated_tax_unit_rule(
        "co_modified_agi",
        dtype="Money",
        unit="USD",
        source="Colorado sales tax refund modified adjusted gross income, including tax-exempt Social Security",
        formula=(
            "adjusted_gross_income "
            "+ max("
            "0, "
            "title_II_monthly_benefits_received_during_taxable_year "
            "- social_security_benefits_included_in_gross_income"
            ")"
        ),
    ),
    _generated_tax_unit_rule(
        "co_sales_tax_refund_filing_status_multiplier",
        dtype="Decimal",
        source="Colorado sales tax refund filing-status multiplier",
        formula="if filing_status == 1: 2 else: 1",
    ),
    _generated_tax_unit_rule(
        "co_income_tax",
        dtype="Money",
        unit="USD",
        source="Colorado income tax liability resolved from encoded bridge components",
        formula="co_income_tax_before_refundable_credits - co_refundable_credits",
    ),
    _generated_tax_unit_rule(
        "state_income_tax",
        dtype="Money",
        unit="USD",
        source="Oracle comparison bridge routing state income tax liability by jurisdiction",
        formula="if is_colorado_tax_unit: co_income_tax else: 0",
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
_HOH_YOUNG_ADULT_DEPENDENT_AGE_LIMIT = 24
_HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT = 5_500
_AXIOM_TAX_REF_PREFIX = "us:tax/federal-income-tax"
_TAX_FILER_ADULT_AGE = 18
_STANDARD_DEDUCTION_OTHER_CASE_2026_AMOUNT = 16_100
_STANDARD_DEDUCTION_OTHER_CASE_AFTER_2017_BASE_AMOUNT = 15_750

_RELATION_REFS = (
    "us:tax/oracle-bridge#relation.business_income_of_tax_unit",
    "us:tax/oracle-bridge#relation.co_dependent_of_tax_unit",
    "us:tax/oracle-bridge#relation.co_withheld_income_tax_member_of_tax_unit",
    "us:tax/oracle-bridge#relation.filer_adjusted_earnings_of_tax_unit",
    "us:tax/oracle-bridge#relation.payroll_member_of_tax_unit",
    "us:statutes/26/151#relation.exemption_individual_of_tax_unit",
    "us:statutes/26/151#relation.senior_deduction_individual_of_tax_unit",
    "us:statutes/26/21#relation.qualifying_individual_of_tax_unit",
    "us:statutes/26/22#relation.taxpayer_or_spouse_of_tax_unit",
    "us:statutes/26/24/h#relation.dependent_of_tax_unit",
    "us:statutes/26/25A#relation.education_credit_member_of_tax_unit",
    "us:statutes/26/32#relation.qualifying_child_of_tax_unit",
    "us:statutes/26/7703#relation.living_apart_child_of_tax_unit",
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
    "individual_is_nonresident_alien",
    "individual_is_noncitizen_territory_resident",
    "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year",
    "international_social_security_agreement_under_section_233_in_effect",
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
    "self_employment_income_is_subject_exclusively_to_foreign_social_security_laws_under_agreement",
    "social_security_agreement_under_section_233_applies_to_nonresident_alien",
    "spouses_lived_apart_all_year",
    "spouse_not_member_of_household_during_last_six_months",
    "spouse_dies_during_taxable_year",
    "taxable_year_closed_by_reason_of_taxpayer_death",
    "taxable_year_begins_after_2024_and_before_2029",
    "taxable_year_begins_before_2027",
    "taxable_year_begins_after_2025",
    "taxpayer_files_separate_return",
    "taxpayer_maintains_household_as_home",
    "taxpayer_claims_section_911_benefits",
    "taxpayer_makes_lump_sum_election_for_prior_year_portion",
    "taxpayer_makes_lump_sum_election_under_subsection_e",
    "taxpayer_married_at_time_of_spouse_death",
    "taxpayer_elects_to_treat_section_112_excluded_amounts_as_earned_income",
    "taxpayer_receives_social_security_benefit_for_listed_purpose",
    "taxpayer_is_nonresident_alien_for_any_portion_of_year",
    "taxpayer_is_qualifying_child_of_another_taxpayer",
    "taxpayer_is_section_1_g_child",
    "taxpayer_treated_as_resident_by_section_6013_g_or_h_election",
    "legally_separated_under_decree_of_divorce_or_separate_maintenance",
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
    "penal_institution_service_compensation",
    "nonresident_alien_income_not_connected_with_united_states_business",
    "auto_loan_interest_deduction",
    "casualty_loss_deduction",
    "capital_gains_28_percent_rate_gain",
    "charitable_deduction",
    "charitable_deduction_for_non_itemizers",
    "cost_of_living_adjustment_25b",
    "credit_allowed_under_section_33",
    "credit_against_chapter_tax_before_section_911_double_benefit_denial",
    "credit_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
    "ctc_limiting_tax_liability",
    "deductible_mortgage_interest",
    "deduction_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
    "deduction_under_subtitle_before_section_911_double_benefit_denial",
    "dependent_care_assistance_exclusion",
    "dependent_care_assistance_excludable_under_section_129",
    "dividend_income",
    "eitc_relevant_investment_income",
    "elective_deferrals",
    "eligible_deferred_compensation_deferrals",
    "energy_efficient_home_improvement_credit",
    "employment_related_expenses_paid",
    "excess_payroll_tax_withheld",
    "excludable_educational_assistance",
    "exclusion_from_gross_income_under_subtitle_before_section_911_double_benefit_denial",
    "exclusion_properly_allocable_or_chargeable_to_amounts_excluded_under_subsection_a",
    "exemptions",
    "early_delivered_social_security_benefit_checks_deemed_received_in_taxable_year",
    "financial_trading_business_income",
    "foreign_tax_credit",
    "form_4972_lumpsum_distributions",
    "impairment_duration_months",
    "highest_section_1_e_bracket_begin_amount",
    "inclusion_by_reason_of_prior_year_lump_sum_portion_before_lump_sum_limitation",
    "inclusion_by_reason_of_prior_year_lump_sum_portion_before_subsection_e_limitation",
    "individual_testing_period_distributions",
    "investment_of_working_capital_income",
    "itemized_medical_expenses",
    "itemized_taxable_income_deductions_reduction",
    "local_income_tax",
    "local_sales_tax",
    "long_term_capital_gains",
    "lump_sum_payment_portion_attributable_to_prior_taxable_years",
    "min_head_spouse_earned",
    "misc_deduction",
    "new_clean_vehicle_credit",
    "net_investment_income_tax",
    "nonresident_withholding_credit_treated_as_refundable_amount",
    "other_nontaxable_pension_annuity_disability_benefits_subject_to_reduction",
    "other_non_title_pension_annuity_or_disability_benefits_excluded_from_gross_income",
    "overtime_income_deduction",
    "passive_activity_business_income",
    "passenger_vehicle_loan_interest_paid_or_accrued",
    "pension_or_annuity_amount",
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
    "railroad_retirement_additional_tier_1_monthly_annuity_amount",
    "railroad_retirement_annuity_amount_equivalent_to_social_security_benefit",
    "railroad_retirement_monthly_annuity_amount_under_section_3_f_3",
    "refundable_payroll_tax_credit",
    "railroad_retirement_act_benefits_excluded_from_gross_income",
    "rental_income",
    "real_estate_taxes",
    "residential_clean_energy_credit",
    "royalty_income",
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
    "self_employment_income_amount_subject_exclusively_to_foreign_social_security_laws_under_agreement",
    "self_employment_income_subject_to_1401_b",
    "short_term_capital_gains",
    "social_security_benefit_checks_deemed_received_in_taxable_year_under_section_708",
    "social_security_benefit_repayments_during_taxable_year",
    "social_security_title_ii_benefits_excluded_from_gross_income",
    "special_refund_social_security_taxes_under_6413c",
    "spouse_earned_income_for_cdcc",
    "spouse_not_member_of_household_final_month_count",
    "spouse_testing_period_distributions",
    "sum_of_prior_year_gross_income_increases_from_lump_sum_portion",
    "tax_exempt_interest_received_or_accrued",
    "tax_unit_childcare_expenses",
    "taxpayer_household_cost_fraction_furnished",
    "taxable_interest_income",
    "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception",
    "taxable_net_gain_from_dispositions",
    "taxable_pension_annuity_disability_benefits_included",
    "tax_imposed_by_chapter_before_cdcc",
    "taxpayer_earned_income_for_cdcc",
    "state_sales_tax",
    "subsidized_state_work_activity_service_compensation",
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
    "workers_compensation_treated_as_social_security_benefit",
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
            "ctc_child_satisfies_subsection_c",
            "ctc_person_satisfies_dependency_rules",
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
            "workers_compensation_treated_as_social_security_benefit",
            "workers_compensation_treated_as_social_security_benefit_under_section_86_d_3",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/86#input.{name}"
        for name in (
            "inclusion_by_reason_of_prior_year_lump_sum_portion_before_subsection_e_limitation",
            "inclusion_by_reason_of_prior_year_lump_sum_portion_before_lump_sum_limitation",
            "lump_sum_payment_portion_attributable_to_prior_taxable_years",
            "married_taxpayer_lived_apart_from_spouse_at_all_times_during_taxable_year",
            "railroad_retirement_additional_tier_1_monthly_annuity_amount",
            "railroad_retirement_annuity_amount_equivalent_to_social_security_benefit",
            "railroad_retirement_monthly_annuity_amount_under_section_3_f_3",
            "early_delivered_social_security_benefit_checks_deemed_received_in_taxable_year",
            "social_security_benefit_checks_deemed_received_in_taxable_year_under_section_708",
            "social_security_benefit_repayments_during_taxable_year",
            "sum_of_prior_year_gross_income_increases_from_lump_sum_portion",
            "taxpayer_makes_lump_sum_election_for_prior_year_portion",
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
        name: f"us:statutes/26/26#input.{name}"
        for name in ("net_investment_income_tax",)
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
        name: f"us:statutes/26/1401#input.{name}"
        for name in (
            "international_social_security_agreement_under_section_233_in_effect",
            "self_employment_income_is_subject_exclusively_to_foreign_social_security_laws_under_agreement",
            "self_employment_income_amount_subject_exclusively_to_foreign_social_security_laws_under_agreement",
            "wages_taken_into_account_for_additional_medicare_tax",
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
            "nonresident_withholding_credit_treated_as_refundable_amount",
            "section_6013_g_or_h_election_in_effect_for_taxable_year",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/32#input.{name}"
        for name in (
            "qualifying_child_is_married_at_close_of_taxable_year",
            "qualifying_child_marital_status_requires_section_151_entitlement",
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
        name: f"us:statutes/26/32/c/2#input.{name}"
        for name in (
            "employee_compensation_includible_in_gross_income",
            "pension_or_annuity_amount",
            "nonresident_alien_income_not_connected_with_united_states_business",
            "penal_institution_service_compensation",
            "subsidized_state_work_activity_service_compensation",
            "taxpayer_elects_to_treat_section_112_excluded_amounts_as_earned_income",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"us:statutes/26/7703#input.{name}"
        for name in (
            "spouse_dies_during_taxable_year",
            "taxpayer_married_at_time_of_spouse_death",
            "taxpayer_married_at_close_of_taxable_year",
            "legally_separated_under_decree_of_divorce_or_separate_maintenance",
            "taxpayer_files_separate_return",
            "taxpayer_maintains_household_as_home",
            "taxpayer_household_cost_fraction_furnished",
            "spouse_not_member_of_household_final_month_count",
        )
    }
)
_INPUT_REF_OVERRIDES.update(
    {
        name: f"{US_TAX_ORACLE_BRIDGE_TARGET}#input.{name}"
        for name in (
            "alaska_permanent_fund_dividend_eligible_person_count",
            "capital_gains_tax_long_term_capital_gains",
            "capital_gains_tax_qualified_dividend_income",
            "capital_gains_tax_short_term_capital_gains",
            "filer_dividend_income",
            "filer_long_term_capital_gains",
            "filer_pension_annuity_disability_benefits_received",
            "filer_rental_income",
            "filer_short_term_capital_gains",
            "filer_taxable_interest_income",
            "filer_unemployment_compensation",
            "is_colorado_tax_unit",
            "oracle_person_age",
            "oracle_person_is_qualifying_child_dependent",
            "oracle_person_is_tax_unit_dependent",
            "person_dividend_income",
            "person_long_term_capital_gains",
            "person_payroll_earnings",
            "person_pension_income",
            "person_rental_income_for_qbid",
            "person_self_employment_income_for_qbid",
            "person_short_term_capital_gains",
            "person_social_security_benefits",
            "person_taxable_interest_income",
            "person_unemployment_compensation",
            "spouse_has_attained_age_55_before_close_of_taxable_year",
            "taxpayer_has_attained_age_55_before_close_of_taxable_year",
        )
    }
)


def attach_axiom_tax_inputs(cases: list[Case]) -> list[Case]:
    """Attach Axiom tax input records to ECPS-style neutral cases."""

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


def _sum_dividends(entities) -> float:
    """Total dividends, never less than the qualified split.

    ECPS rows sometimes carry only the qualified-dividend leaf; qualified
    dividends are a subset of total dividends, so the ordinary total is at
    least the qualified amount.
    """
    return sum(
        max(
            _number(entity.fact(Concepts.DIVIDEND_INCOME, 0)),
            _number(entity.fact(Concepts.QUALIFIED_DIVIDEND_INCOME, 0)),
        )
        for entity in entities
    )


def _tax_unit_input_records(case: Case, people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    dependents = _tax_dependents(people, head, spouse)
    wages = _earned_income(head) + (_earned_income(spouse) if spouse else 0)

    # Investment / unearned income pulled from the Case so Axiom matches what
    # PolicyEngine and TAXSIM see.
    earners = [person for person in (head, spouse) if person is not None]
    filer_dividends = _sum_dividends(earners)
    filer_interest = _sum_concept(earners, Concepts.INTEREST_INCOME)
    filer_short_capital_gains = _sum_concept(
        earners,
        Concepts.SHORT_TERM_CAPITAL_GAINS,
    )
    filer_long_capital_gains = _sum_concept(
        earners,
        Concepts.LONG_TERM_CAPITAL_GAINS,
    )
    capital_gains_tax_qualified_dividends = _sum_concept(
        people,
        Concepts.QUALIFIED_DIVIDEND_INCOME,
    )
    capital_gains_tax_short_capital_gains = _sum_concept(
        people,
        Concepts.SHORT_TERM_CAPITAL_GAINS,
    )
    capital_gains_tax_long_capital_gains = _sum_concept(
        people,
        Concepts.LONG_TERM_CAPITAL_GAINS,
    )
    tax_unit_dividends = _sum_dividends(people)
    tax_unit_interest = _sum_concept(people, Concepts.INTEREST_INCOME)
    filer_pensions = _sum_concept(earners, Concepts.PENSION_INCOME)
    social_security = _sum_concept(people, Concepts.SOCIAL_SECURITY_BENEFITS)
    filer_unemployment = _sum_concept(
        earners,
        Concepts.UNEMPLOYMENT_INSURANCE_INCOME,
    )
    filer_rental = _sum_concept(earners, Concepts.RENTAL_INCOME)
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
        "filer_meets_eitc_identification_requirements": True,
        "filing_status": filing_status,
        "filing_status_is_joint_return": spouse is not None,
        "individual_is_unmarried_and_not_surviving_spouse": spouse is None,
        "is_estate_or_trust": False,
        "is_colorado_tax_unit": _is_colorado_case(case),
        "is_individual": True,
        "married_at_close_of_taxable_year": spouse is not None,
        "married_filing_separate_return": False,
        "married_joint_return_filed": spouse is not None,
        "may_be_claimed_as_dependent_by_another_taxpayer": False,
        "tax_exempt_interest_received_or_accrued": 0,
        "spouse_has_attained_age_65_before_close_of_taxable_year": bool(
            spouse and _age(spouse) >= 65
        ),
        "spouse_has_attained_age_55_before_close_of_taxable_year": bool(
            spouse and _age(spouse) >= 55
        ),
        "spouse_is_blind_as_of_close_of_taxable_year_or_time_of_death": spouse_is_blind,
        "spouse_includes_required_social_security_number_on_return": spouse is not None,
        "spouse_dies_during_taxable_year": False,
        "taxable_year_is_full_12_months": True,
        "taxpayer_files_separate_return": False,
        "taxpayer_maintains_household_as_home": False,
        "taxpayer_includes_required_social_security_number_on_return": True,
        "taxpayer_has_attained_age_65_before_close_of_taxable_year": _age(head) >= 65,
        "taxpayer_has_attained_age_55_before_close_of_taxable_year": _age(head) >= 55,
        "taxpayer_is_blind_at_close_of_taxable_year": taxpayer_is_blind,
        "taxpayer_is_dependent_for_section_151_to_another_taxpayer": False,
        "taxpayer_is_married_under_section_7703_a": spouse is not None,
        "taxpayer_married_at_close_of_taxable_year": spouse is not None,
        "taxpayer_married_at_time_of_spouse_death": spouse is not None,
        "trust_all_unexpired_interests_devoted_to_section_170_c_2_B_purposes": False,
        "wages": wages,
        "wages_paid_to_individual_for_section_1401_a": wages,
        "employee_compensation_includible_in_gross_income": wages,
        "wages_taken_into_account_for_additional_medicare_tax": wages,
        # Investment / unearned income — projected from Case concepts.
        "dividend_income": tax_unit_dividends,
        "qualified_dividend_income": capital_gains_tax_qualified_dividends,
        "taxable_interest_income": tax_unit_interest,
        "short_term_capital_gains": capital_gains_tax_short_capital_gains,
        "long_term_capital_gains": capital_gains_tax_long_capital_gains,
        "rental_income": filer_rental,
        "pension_annuity_disability_benefits_received": filer_pensions,
        "filer_dividend_income": filer_dividends,
        "filer_taxable_interest_income": filer_interest,
        "filer_short_term_capital_gains": filer_short_capital_gains,
        "filer_long_term_capital_gains": filer_long_capital_gains,
        "filer_rental_income": filer_rental,
        "filer_pension_annuity_disability_benefits_received": filer_pensions,
        "filer_unemployment_compensation": filer_unemployment,
        "deductible_mortgage_interest": _number(
            case.fact(Concepts.MORTGAGE_INTEREST_PAID, 0)
        ),
        "misc_deduction": _number(case.fact(Concepts.ITEMIZED_DEDUCTIONS_OTHER, 0)),
        "tax_unit_childcare_expenses": _number(
            case.fact(Concepts.CHILDCARE_EXPENSES, 0)
        ),
        "partnership_section_702_a_8_income_or_loss": 0,
        "real_estate_taxes": _number(case.fact(Concepts.PROPERTY_TAX_PAID, 0)),
        "self_employment_trade_or_business_deductions": 0,
        "self_employment_trade_or_business_gross_income": self_employment,
        # 26 USC 32(c)(2)(A)(ii): NESE determined with regard to the
        # 164(f)/1402(a)(12) deduction (one-half of the combined
        # 1401(a)+(b)(1) rates).
        "net_earnings_from_self_employment_after_self_employment_tax_deduction": (
            # 32(c)(2)(A)(ii) via 164(f): earned income nets out one-half
            # of the SECA tax imposed (rates apply to 92.35% of profits).
            max(0.0, self_employment)
            * (1 - 0.5 * (0.124 + 0.029) * (1 - 0.5 * (0.124 + 0.029)))
        ),
        "alaska_permanent_fund_dividend_eligible_person_count": _alaska_permanent_fund_dividend_eligible_person_count(
            case,
            people,
        ),
        "capital_gains_tax_qualified_dividend_income": capital_gains_tax_qualified_dividends,
        "capital_gains_tax_short_term_capital_gains": capital_gains_tax_short_capital_gains,
        "capital_gains_tax_long_term_capital_gains": capital_gains_tax_long_capital_gains,
        "taxpayer_is_individual": True,
        "title_II_monthly_benefits_received_during_taxable_year": social_security,
        "unemployment_compensation": filer_unemployment,
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
    inputs["qualifying_children_count"] = sum(
        1 for dependent in dependents if _age(dependent) < 17
    )
    inputs["passenger_vehicle_loan_interest_paid_or_accrued"] = inputs.get(
        "auto_loan_interest_deduction",
        0,
    )
    inputs.setdefault(
        "cost_of_living_adjustment_under_section_1_f_3",
        _standard_deduction_cola(case),
    )
    inputs.setdefault("deduction_for_personal_exemptions_provided_in_section_151", 0)
    inputs.setdefault("deductions_allowable_in_arriving_at_adjusted_gross_income", 0)
    inputs.setdefault("deductions_allowable_under_this_chapter", 0)
    inputs.setdefault("deductions_allowed_by_this_chapter_other_than_standard_deduction", 0)
    records = [
        _input_record(name, "TaxUnit", _TAX_UNIT_ID, value)
        for name, value in inputs.items()
    ]
    records.append(
        _input_record_for_ref(
            "us:statutes/26/1401#input.filing_status",
            "TaxUnit",
            _TAX_UNIT_ID,
            filing_status,
        )
    )
    for name, value in {
        "long_term_capital_gains": capital_gains_tax_long_capital_gains,
        "short_term_capital_gains": capital_gains_tax_short_capital_gains,
        "net_capital_gain_taken_into_account_as_investment_income_under_section_163_d_4_B_iii": 0,
        "qualified_dividend_income": capital_gains_tax_qualified_dividends,
        "unrecaptured_section_1250_gain": inputs.get("unrecaptured_section_1250_gain", 0),
        "capital_gains_28_percent_rate_gain": inputs.get(
            "capital_gains_28_percent_rate_gain",
            0,
        ),
    }.items():
        records.append(
            _input_record_for_ref(
                f"us:statutes/26/1/h#input.{name}",
                "TaxUnit",
                _TAX_UNIT_ID,
                value,
            )
        )
    for name, value in {
        "tin_included_on_return_claiming_exemption": True,
        "is_taxpayer": True,
        "is_spouse_of_taxpayer": False,
        "filing_status": filing_status,
        "spouse_has_no_gross_income_for_calendar_year": False,
        "spouse_is_dependent_of_another_taxpayer": False,
        "qualified_individual_social_security_number_included_on_return": True,
        "age": _age(head),
        "taxpayer_is_individual": True,
        "taxable_year_begins_after_exemption_amount_zero_start": True,
        "taxable_year_begins_before_senior_deduction_termination": True,
    }.items():
        records.append(
            _input_record_for_ref(
                f"us:statutes/26/151#input.{name}",
                "TaxUnit",
                _TAX_UNIT_ID,
                value,
            )
        )
    # Raw section 112 combat-zone inputs, zero-defaulted from the populace
    # bridge's shared table. Compositions built from rulespec-us vintages
    # whose 26/32 EITC closure imports the raw 26/112 machinery (e.g. the
    # pinned ca2d424f snapshot) require these on every tax unit; newer
    # vintages take the aggregate section-112 exclusion input instead and
    # the runner prunes these unsupported records, so carrying them is
    # vintage-safe in both directions — PROVIDED pruning is on. The runner
    # defaults prune_unsupported_inputs=False, and cli.py enables it only
    # when it derives program_imports itself: a future tax suite passing an
    # explicit axiom_program/axiom_compiled_program on a newer vintage
    # would receive these records unpruned and must enable pruning (or
    # strip them) explicitly.
    from ...bridges.tax_populace import project_section_112_tax_unit_inputs

    for name, value in project_section_112_tax_unit_inputs().items():
        records.append(
            _input_record_for_ref(
                f"us:statutes/26/112#input.{name}",
                "TaxUnit",
                _TAX_UNIT_ID,
                value,
            )
        )
    return records


def _person_input_records(people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    dependents = _tax_dependents(people, head, spouse)
    filing_status = _filing_status(spouse=spouse, dependents=dependents)
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
            "oracle_person_age": age,
            "oracle_person_is_qualifying_child_dependent": is_dependent and age < 19,
            "oracle_person_is_tax_unit_dependent": is_dependent,
            # Qualified dividends are a subset of total dividends and some
            # ECPS rows carry only the qualified leaf; AGI must include them
            # either way (mirrors _sum_dividends).
            "person_dividend_income": max(
                _number(person.fact(Concepts.DIVIDEND_INCOME, 0)),
                _number(person.fact(Concepts.QUALIFIED_DIVIDEND_INCOME, 0)),
            ),
            "person_long_term_capital_gains": _number(
                person.fact(Concepts.LONG_TERM_CAPITAL_GAINS, 0)
            ),
            "person_payroll_earnings": _earned_income(person),
            "person_pension_income": _number(person.fact(Concepts.PENSION_INCOME, 0)),
            "person_rental_income_for_qbid": _number(
                person.fact(Concepts.RENTAL_INCOME, 0)
            ),
            "person_self_employment_income_for_qbid": _number(
                person.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0)
            ),
            "person_short_term_capital_gains": _number(
                person.fact(Concepts.SHORT_TERM_CAPITAL_GAINS, 0)
            ),
            "person_social_security_benefits": _number(
                person.fact(Concepts.SOCIAL_SECURITY_BENEFITS, 0)
            ),
            "person_taxable_interest_income": _number(
                person.fact(Concepts.INTEREST_INCOME, 0)
            ),
            "person_unemployment_compensation": _number(
                person.fact(Concepts.UNEMPLOYMENT_INSURANCE_INCOME, 0)
            ),
            "ctc_child_satisfies_subsection_c": is_dependent and age < 17,
            "ctc_person_satisfies_dependency_rules": is_dependent,
            "qualifying_child_described_in_subsection_c": is_dependent and age < 17,
            "qualifying_child_is_married_at_close_of_taxable_year": False,
            "qualifying_child_marital_status_requires_section_151_entitlement": False,
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
        for name, value in _section_151_person_inputs(
            person,
            head=head,
            spouse=spouse,
            filing_status=filing_status,
        ).items():
            records.append(
                _input_record_for_ref(
                    f"us:statutes/26/151#input.{name}",
                    "Person",
                    person.entity_id,
                    value,
                )
            )
        for name, value in _section_152c_person_inputs(
            person,
            head=head,
            is_dependent=is_dependent,
        ).items():
            records.append(
                _input_record_for_ref(
                    f"us:statutes/26/152/c#input.{name}",
                    "Person",
                    person.entity_id,
                    value,
                )
            )
        for name, value in _section_7703_person_inputs(
            person,
            is_dependent=is_dependent,
        ).items():
            records.append(
                _input_record_for_ref(
                    f"us:statutes/26/7703#input.{name}",
                    "Person",
                    person.entity_id,
                    value,
                )
            )
    return records


def _section_151_person_inputs(
    person: Entity,
    *,
    head: Entity,
    spouse: Entity | None,
    filing_status: int,
) -> dict[str, Any]:
    is_taxpayer = person is head
    is_spouse = person is spouse
    return {
        "tin_included_on_return_claiming_exemption": True,
        "is_taxpayer": is_taxpayer,
        "is_spouse_of_taxpayer": is_spouse,
        "spouse_has_no_gross_income_for_calendar_year": False,
        "spouse_is_dependent_of_another_taxpayer": False,
        "qualified_individual_social_security_number_included_on_return": True,
        "age": _age(person),
        "filing_status": filing_status if is_taxpayer or is_spouse else 0,
    }


def _section_152c_person_inputs(
    person: Entity,
    *,
    head: Entity,
    is_dependent: bool,
) -> dict[str, Any]:
    age = _age(person)
    relationship = _relation(person)
    is_child_or_descendant = is_dependent and relationship in _DEPENDENT_RELATIONS
    return {
        "individual_is_child_of_taxpayer_or_descendant_of_such_child": (
            is_child_or_descendant
        ),
        "individual_is_sibling_stepsibling_or_descendant_of_such_relative": False,
        "individual_is_permanently_and_totally_disabled": False,
        "individual_is_younger_than_taxpayer": age < _age(head),
        "individual_age_at_close_of_calendar_year": age,
        "individual_is_student": False,
        "individual_principal_place_of_abode_with_taxpayer_fraction": (
            1 if is_dependent else 0
        ),
        "individual_own_support_fraction_provided_by_individual": 0,
        "filing_status": 0,
        "return_filed_only_for_claim_of_refund": False,
        "individual_may_be_claimed_as_qualifying_child_by_two_or_more_taxpayers": False,
        "parents_of_individual_may_claim_individual_but_no_parent_claims": False,
        "taxpayer_is_parent_of_individual": is_child_or_descendant,
        "taxpayer_adjusted_gross_income_higher_than_highest_parent_adjusted_gross_income": True,
        "parents_filing_status": 1,
        "child_resided_with_taxpayer_parent_for_longest_period": True,
        "child_resided_with_both_parents_same_amount_of_time_and_taxpayer_parent_has_highest_adjusted_gross_income": False,
        "no_parent_of_individual_is_a_claiming_taxpayer": False,
        "taxpayer_has_highest_adjusted_gross_income_among_claiming_taxpayers": True,
    }


def _section_7703_person_inputs(
    person: Entity,
    *,
    is_dependent: bool,
) -> dict[str, Any]:
    age = _age(person)
    relationship = _relation(person)
    is_child_or_descendant = is_dependent and relationship in _DEPENDENT_RELATIONS
    return {
        "person_is_child_within_federal_tax_child_definition": (
            is_child_or_descendant and age < 19
        ),
        "taxpayer_household_is_child_principal_place_of_abode": is_dependent,
        "child_principal_abode_fraction_of_taxable_year": 1 if is_dependent else 0,
        "would_be_entitled_to_child_deduction_but_for_parent_release_rule": is_dependent,
    }


def _relation_records(people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    dependents = _tax_dependents(people, head, spouse)
    tax_filers = [person for person in (head, spouse) if person is not None]
    records = []
    for relation_ref in _RELATION_REFS:
        if relation_ref in {
            "us:tax/oracle-bridge#relation.filer_adjusted_earnings_of_tax_unit",
            "us:statutes/26/22#relation.taxpayer_or_spouse_of_tax_unit",
        }:
            relation_people = tax_filers
        elif relation_ref in {
            "us:tax/oracle-bridge#relation.co_dependent_of_tax_unit",
            "us:statutes/26/24/h#relation.dependent_of_tax_unit",
            "us:statutes/26/32#relation.qualifying_child_of_tax_unit",
            "us:statutes/26/7703#relation.living_apart_child_of_tax_unit",
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
    return _input_record_for_ref(_input_ref(name), entity, entity_id, value)


def _input_record_for_ref(
    ref: str,
    entity: str,
    entity_id: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "name": ref,
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
        "employee_3101_3201a_taxes",
        "employee_medicare_tax",
        "employee_social_security_tax",
        "filer_adjusted_earnings",
        "gross_income",
        "irs_gross_income",
        "itemized_taxable_income_deductions",
        "modified_adjusted_gross_income",
        "deduction_provided_in_section_199A",
        "qualified_business_income_deduction",
        "salt_deduction",
        "self_employment_1401_taxes",
        "self_employment_income",
        "self_employment_tax_ald",
        "state_income_tax",
        "state_withheld_income_tax",
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
    age = _age(dependent)
    if age < 19:
        return True
    return (
        age < _HOH_YOUNG_ADULT_DEPENDENT_AGE_LIMIT
        and _dependent_gross_income(dependent)
        < _HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT
    )


def _dependent_gross_income(dependent: Entity) -> float:
    return (
        _earned_income(dependent)
        + max(0, _number(dependent.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0)))
        + _number(dependent.fact(Concepts.DIVIDEND_INCOME, 0))
        + _number(dependent.fact(Concepts.INTEREST_INCOME, 0))
        + _number(dependent.fact(Concepts.SHORT_TERM_CAPITAL_GAINS, 0))
        + _number(dependent.fact(Concepts.LONG_TERM_CAPITAL_GAINS, 0))
        + _number(dependent.fact(Concepts.PENSION_INCOME, 0))
        + _number(dependent.fact(Concepts.UNEMPLOYMENT_INSURANCE_INCOME, 0))
        + max(0, _number(dependent.fact(Concepts.RENTAL_INCOME, 0)))
    )


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


def _alaska_permanent_fund_dividend_eligible_person_count(
    case: Case,
    people: list[Entity],
) -> int:
    if not _is_alaska_case(case):
        return 0
    head, spouse = _tax_filers(people)
    return sum(1 for person in (head, spouse) if person is not None)


def _is_alaska_case(case: Case) -> bool:
    scope = case.scope
    if scope is not None and scope.type != "country":
        return scope.geoid.startswith("02")

    state_code = (
        case.fact(Concepts.STATE_CODE)
        or case.metadata.get("state_code")
        or case.metadata.get("state")
    )
    if state_code in (None, ""):
        return False
    normalized = str(state_code).strip().upper()
    return normalized in {"AK", "02", "2"}


def _is_colorado_case(case: Case) -> bool:
    scope = case.scope
    if scope is not None and scope.type != "country":
        return scope.geoid.startswith("08")

    state_code = (
        case.fact(Concepts.STATE_CODE)
        or case.metadata.get("state_code")
        or case.metadata.get("state")
    )
    if state_code in (None, ""):
        return False
    normalized = str(state_code).strip().upper()
    return normalized in {"CO", "08", "8"}


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
