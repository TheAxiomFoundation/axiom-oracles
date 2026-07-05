"""Compare UK RuleSpec output against PolicyEngine over Populace.

The UK counterpart to the US Populace comparators covers mapped surfaces whose
RuleSpec inputs can be projected from PolicyEngine over Populace, plus scalar
parameter surfaces whose generated RuleSpec values can be compared against
PolicyEngine component outputs.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import yaml

from .ecps_tax import (
    _version_tuple,
    input_record,
    money,
    output_number,
    relative_diff,
    run_axiom_program,
    within_tolerance,
)
from .population import (
    DEFAULT_UK_POPULACE_YEAR,
    format_dataset_identity,
    load_populace_dataset,
    local_dataset_path,
    populace_data_requirement,
    population_table,
)

DEFAULT_DATASET = ""
WEEKS_IN_YEAR = 52
MONTHS_IN_YEAR = 12
MIN_POLICYENGINE_UK_VERSION = "2.88"
CATEGORY_THRESHOLD_WEEKLY_TOLERANCE = 1.0

NATIONAL_INSURANCE_SECTION_1_PROGRAM_PATH = Path("statutes/ukpga/1992/4/1.yaml")
NATIONAL_INSURANCE_SECTION_1_BASE = "uk:statutes/ukpga/1992/4/1"
NATIONAL_INSURANCE_SECTION_8_PROGRAM_PATH = Path("statutes/ukpga/1992/4/8.yaml")
NATIONAL_INSURANCE_SECTION_8_BASE = "uk:statutes/ukpga/1992/4/8"
NATIONAL_INSURANCE_SECTION_15_PROGRAM_PATH = Path("statutes/ukpga/1992/4/15.yaml")
NATIONAL_INSURANCE_SECTION_15_BASE = "uk:statutes/ukpga/1992/4/15"
NATIONAL_INSURANCE_REGULATION_100_PROGRAM_PATH = Path(
    "regulations/uksi/2001/1004/100.yaml"
)
NATIONAL_INSURANCE_REGULATION_100_BASE = "uk:regulations/uksi/2001/1004/100"
PERSONAL_ALLOWANCE_PROGRAM_PATH = Path("statutes/ukpga/2007/3/35.yaml")
PERSONAL_ALLOWANCE_BASE = "uk:statutes/ukpga/2007/3/35"
INCOME_TAX_SECTION_10_PROGRAM_PATH = Path("statutes/ukpga/2007/3/10.yaml")
INCOME_TAX_SECTION_10_BASE = "uk:statutes/ukpga/2007/3/10"
INCOME_TAX_SECTION_11D_PROGRAM_PATH = Path("statutes/ukpga/2007/3/11D.yaml")
INCOME_TAX_SECTION_11D_BASE = "uk:statutes/ukpga/2007/3/11D"
INCOME_TAX_SECTION_13_PROGRAM_PATH = Path("statutes/ukpga/2007/3/13.yaml")
INCOME_TAX_SECTION_13_BASE = "uk:statutes/ukpga/2007/3/13"
INCOME_TAX_SECTION_23_PROGRAM_PATH = Path("statutes/ukpga/2007/3/23.yaml")
INCOME_TAX_SECTION_23_BASE = "uk:statutes/ukpga/2007/3/23"
CHILD_BENEFIT_PROGRAM_PATH = Path("regulations/uksi/2006/965/2.yaml")
CHILD_BENEFIT_BASE = "uk:regulations/uksi/2006/965/2"
CHILD_BENEFIT_SECTION_141_PROGRAM_PATH = Path("statutes/ukpga/1992/4/141.yaml")
CHILD_BENEFIT_SECTION_141_BASE = "uk:statutes/ukpga/1992/4/141"
CHILD_BENEFIT_FINAL_PROGRAM_PATH = Path("policies/govuk/child-benefit.yaml")
CHILD_BENEFIT_FINAL_BASE = "uk:policies/govuk/child-benefit"
BENEFIT_CAP_REGULATION_80A_PROGRAM_PATH = Path("regulations/uksi/2013/376/80A.yaml")
BENEFIT_CAP_REGULATION_80A_BASE = "uk:regulations/uksi/2013/376/80A"
STATE_PENSION_CREDIT_SECTION_1_PROGRAM_PATH = Path("statutes/ukpga/2002/16/1.yaml")
STATE_PENSION_CREDIT_SECTION_1_BASE = "uk:statutes/ukpga/2002/16/1"
STATE_PENSION_CREDIT_SECTION_2_PROGRAM_PATH = Path("statutes/ukpga/2002/16/2.yaml")
STATE_PENSION_CREDIT_SECTION_2_BASE = "uk:statutes/ukpga/2002/16/2"
STATE_PENSION_CREDIT_SECTION_3_PROGRAM_PATH = Path("statutes/ukpga/2002/16/3.yaml")
STATE_PENSION_CREDIT_SECTION_3_BASE = "uk:statutes/ukpga/2002/16/3"
STATE_PENSION_FINAL_PROGRAM_PATH = Path("policies/govuk/state-pension.yaml")
STATE_PENSION_FINAL_BASE = "uk:policies/govuk/state-pension"
PENSION_CREDIT_PROGRAM_PATH = Path("regulations/uksi/2002/1792/6.yaml")
PENSION_CREDIT_BASE = "uk:regulations/uksi/2002/1792/6"
PENSION_CREDIT_SCHEDULE_IIA_PROGRAM_PATH = Path(
    "regulations/uksi/2002/1792/schedule/IIA.yaml"
)
PENSION_CREDIT_SCHEDULE_IIA_BASE = "uk:regulations/uksi/2002/1792/schedule/IIA"
PENSION_CREDIT_REGULATION_15_PROGRAM_PATH = Path("regulations/uksi/2002/1792/15.yaml")
PENSION_CREDIT_REGULATION_15_BASE = "uk:regulations/uksi/2002/1792/15"
PENSION_CREDIT_FINAL_PROGRAM_PATH = Path("policies/govuk/pension-credit.yaml")
PENSION_CREDIT_FINAL_BASE = "uk:policies/govuk/pension-credit"
ESA_REGULATION_118_PROGRAM_PATH = Path("regulations/uksi/2008/794/118.yaml")
ESA_REGULATION_118_BASE = "uk:regulations/uksi/2008/794/118"
ESA_FINAL_PROGRAM_PATH = Path("policies/govuk/esa-income.yaml")
ESA_FINAL_BASE = "uk:policies/govuk/esa-income"
JSA_REGULATION_116_PROGRAM_PATH = Path("regulations/uksi/1996/207/116.yaml")
JSA_REGULATION_116_BASE = "uk:regulations/uksi/1996/207/116"
INCOME_SUPPORT_REGULATION_53_PROGRAM_PATH = Path("regulations/uksi/1987/1967/53.yaml")
INCOME_SUPPORT_REGULATION_53_BASE = "uk:regulations/uksi/1987/1967/53"
HOUSING_BENEFIT_REGULATION_52_PROGRAM_PATH = Path("regulations/uksi/2006/213/52.yaml")
HOUSING_BENEFIT_REGULATION_52_BASE = "uk:regulations/uksi/2006/213/52"
HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_PROGRAM_PATH = Path(
    "regulations/uksi/2006/214/29.yaml"
)
HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_BASE = "uk:regulations/uksi/2006/214/29"
HOUSING_BENEFIT_FINAL_PROGRAM_PATH = Path("policies/govuk/housing-benefit.yaml")
HOUSING_BENEFIT_FINAL_BASE = "uk:policies/govuk/housing-benefit"
UNIVERSAL_CREDIT_PROGRAM_PATH = Path("regulations/uksi/2013/376/36.yaml")
UNIVERSAL_CREDIT_BASE = "uk:regulations/uksi/2013/376/36"
UNIVERSAL_CREDIT_REGULATION_18_PROGRAM_PATH = Path("regulations/uksi/2013/376/18.yaml")
UNIVERSAL_CREDIT_REGULATION_18_BASE = "uk:regulations/uksi/2013/376/18"
UNIVERSAL_CREDIT_REGULATION_22_PROGRAM_PATH = Path("regulations/uksi/2013/376/22.yaml")
UNIVERSAL_CREDIT_REGULATION_22_BASE = "uk:regulations/uksi/2013/376/22"
UNIVERSAL_CREDIT_REGULATION_32_PROGRAM_PATH = Path("regulations/uksi/2013/376/32.yaml")
UNIVERSAL_CREDIT_REGULATION_32_BASE = "uk:regulations/uksi/2013/376/32"
UNIVERSAL_CREDIT_REGULATION_34_PROGRAM_PATH = Path("regulations/uksi/2013/376/34.yaml")
UNIVERSAL_CREDIT_REGULATION_34_BASE = "uk:regulations/uksi/2013/376/34"
UNIVERSAL_CREDIT_REGULATION_72_PROGRAM_PATH = Path("regulations/uksi/2013/376/72.yaml")
UNIVERSAL_CREDIT_REGULATION_72_BASE = "uk:regulations/uksi/2013/376/72"
UNIVERSAL_CREDIT_FINAL_PROGRAM_PATH = Path("policies/govuk/universal-credit.yaml")
UNIVERSAL_CREDIT_FINAL_BASE = "uk:policies/govuk/universal-credit"
WELFARE_REFORM_ACT_SECTION_8_PROGRAM_PATH = Path("statutes/ukpga/2012/5/8.yaml")
WELFARE_REFORM_ACT_SECTION_8_BASE = "uk:statutes/ukpga/2012/5/8"
WELFARE_REFORM_ACT_SECTION_11_PROGRAM_PATH = Path("statutes/ukpga/2012/5/11.yaml")
WELFARE_REFORM_ACT_SECTION_11_BASE = "uk:statutes/ukpga/2012/5/11"
STUDENT_LOAN_REPAYMENT_PROGRAM_PATH = Path(
    "policies/govuk/student-loan-repayments.yaml"
)
STUDENT_LOAN_REPAYMENT_BASE = "uk:policies/govuk/student-loan-repayments"
CARERS_ALLOWANCE_FINAL_PROGRAM_PATH = Path("policies/govuk/carers-allowance.yaml")
CARERS_ALLOWANCE_FINAL_BASE = "uk:policies/govuk/carers-allowance"
CARER_SUPPORT_PAYMENT_FINAL_PROGRAM_PATH = Path(
    "policies/govuk/carer-support-payment.yaml"
)
CARER_SUPPORT_PAYMENT_FINAL_BASE = "uk:policies/govuk/carer-support-payment"
SCOTTISH_CHILD_PAYMENT_FINAL_PROGRAM_PATH = Path(
    "policies/govuk/scottish-child-payment.yaml"
)
SCOTTISH_CHILD_PAYMENT_FINAL_BASE = "uk:policies/govuk/scottish-child-payment"
SDA_FINAL_PROGRAM_PATH = Path("policies/govuk/severe-disablement-allowance.yaml")
SDA_FINAL_BASE = "uk:policies/govuk/severe-disablement-allowance"
DLA_FINAL_PROGRAM_PATH = Path("policies/govuk/disability-living-allowance.yaml")
DLA_FINAL_BASE = "uk:policies/govuk/disability-living-allowance"

PERSONAL_ALLOWANCE_OUTPUTS = {
    "personal_allowance": {
        "axiom": f"{PERSONAL_ALLOWANCE_BASE}#personal_allowance",
        "pe": "personal_allowance",
    },
}

NATIONAL_INSURANCE_CLASS_1_OUTPUTS = {
    "main_primary_class_1_contribution": {
        "axiom": f"{NATIONAL_INSURANCE_SECTION_8_BASE}#main_primary_class_1_contribution",
        "pe": "ni_class_1_employee_primary",
        "pe_transform": "annual_to_weekly",
        "applies": ("ni_liable", True),
    },
    "additional_primary_class_1_contribution": {
        "axiom": f"{NATIONAL_INSURANCE_SECTION_8_BASE}#additional_primary_class_1_contribution",
        "pe": "ni_class_1_employee_additional",
        "pe_transform": "annual_to_weekly",
        "applies": ("ni_liable", True),
    },
    "primary_class_1_contribution": {
        "axiom": f"{NATIONAL_INSURANCE_SECTION_8_BASE}#primary_class_1_contribution",
        "pe": "ni_class_1_employee",
        "pe_transform": "annual_to_weekly",
    },
    "employee_national_insurance": {
        "axiom": f"{NATIONAL_INSURANCE_SECTION_8_BASE}#primary_class_1_contribution",
        "pe": "ni_employee",
        "pe_transform": "annual_to_weekly",
    },
}

INCOME_TAX_INCOME_BASE_COMPONENTS = (
    "employment_income",
    "private_pension_income",
    "social_security_income",
    "self_employment_income",
    "property_income",
    "savings_interest_income",
    "dividend_income",
    "miscellaneous_income",
)

INCOME_TAX_SECTION_23_ADDITION_COMPONENTS = (
    "income_tax_pre_charges",
    "CB_HITC",
    "personal_pension_contributions_tax",
)

INCOME_TAX_SECTION_23_REDUCTION_COMPONENTS = (
    "capped_mcad",
    "other_tax_credits",
)

INCOME_TAX_INCOME_BASE_OUTPUTS = {
    "total_income": {
        "axiom": f"{INCOME_TAX_SECTION_23_BASE}#total_income",
        "pe": "total_income",
    },
    "net_income": {
        "axiom": f"{INCOME_TAX_SECTION_23_BASE}#net_income",
        "pe": "adjusted_net_income",
        "applies": "income_tax_net_income_comparable",
    },
    "income_tax_liability": {
        "axiom": f"{INCOME_TAX_SECTION_23_BASE}#income_tax_liability",
        "pe": "income_tax",
    },
}

NATIONAL_INSURANCE_CLASS_4_OUTPUTS = {
    "main_class_4_contribution": {
        "axiom": f"{NATIONAL_INSURANCE_SECTION_15_BASE}#main_class_4_contribution",
        "pe": "ni_class_4_main",
    },
}

NATIONAL_INSURANCE_REGULATION_100_OUTPUTS = {
    "class_4_annual_maximum": {
        "axiom": f"{NATIONAL_INSURANCE_REGULATION_100_BASE}#class_4_annual_maximum",
        "pe": "ni_class_4_maximum",
    },
    "class_4_contribution_after_annual_maximum": {
        "axiom": (
            f"{NATIONAL_INSURANCE_REGULATION_100_BASE}"
            "#class_4_contribution_after_annual_maximum"
        ),
        "pe": "ni_class_4",
    },
}

NATIONAL_INSURANCE_FINAL_OUTPUTS = {
    "national_insurance_contribution": {
        "axiom": f"{NATIONAL_INSURANCE_SECTION_1_BASE}#national_insurance_contribution",
        "pe": "national_insurance",
        "tolerance": 0.01,
    },
}

INCOME_TAX_SECTION_10_OUTPUTS = {
    "income_charged_at_basic_rate": {
        "axiom": f"{INCOME_TAX_SECTION_10_BASE}#income_charged_at_basic_rate",
        "pe": "basic_rate_earned_income",
        "applies": "non_scottish_income_tax",
    },
    "income_charged_at_higher_rate": {
        "axiom": f"{INCOME_TAX_SECTION_10_BASE}#income_charged_at_higher_rate",
        "pe": "higher_rate_earned_income",
        "applies": "non_scottish_income_tax",
    },
    "income_charged_at_additional_rate": {
        "axiom": f"{INCOME_TAX_SECTION_10_BASE}#income_charged_at_additional_rate",
        "pe": "add_rate_earned_income",
        "applies": "non_scottish_income_tax",
    },
    "tax_on_income_charged_at_basic_rate": {
        "axiom": f"{INCOME_TAX_SECTION_10_BASE}#tax_on_income_charged_at_basic_rate",
        "pe": "basic_rate_earned_income_tax",
        "applies": "non_scottish_income_tax",
    },
    "tax_on_income_charged_at_higher_rate": {
        "axiom": f"{INCOME_TAX_SECTION_10_BASE}#tax_on_income_charged_at_higher_rate",
        "pe": "higher_rate_earned_income_tax",
        "applies": "non_scottish_income_tax",
    },
    "tax_on_income_charged_at_additional_rate": {
        "axiom": (
            f"{INCOME_TAX_SECTION_10_BASE}#tax_on_income_charged_at_additional_rate"
        ),
        "pe": "add_rate_earned_income_tax",
        "applies": "non_scottish_income_tax",
    },
    "income_tax_on_section_10_income": {
        "axiom": f"{INCOME_TAX_SECTION_10_BASE}#income_tax_on_section_10_income",
        "pe": "earned_income_tax",
        "applies": "non_scottish_income_tax",
    },
}

INCOME_TAX_SECTION_11D_OUTPUTS = {
    "savings_income_charged_at_savings_basic_rate": {
        "axiom": f"{INCOME_TAX_SECTION_11D_BASE}#savings_income_charged_at_savings_basic_rate",
        "pe": "basic_rate_savings_income",
        "tolerance": 0.25,
    },
    "savings_income_charged_at_savings_higher_rate": {
        "axiom": f"{INCOME_TAX_SECTION_11D_BASE}#savings_income_charged_at_savings_higher_rate",
        "pe": "higher_rate_savings_income",
        "tolerance": 0.25,
    },
    "savings_income_charged_at_savings_additional_rate": {
        "axiom": f"{INCOME_TAX_SECTION_11D_BASE}#savings_income_charged_at_savings_additional_rate",
        "pe": "add_rate_savings_income",
        "tolerance": 0.25,
    },
    "savings_income_charged_under_section_11d": {
        "axiom": f"{INCOME_TAX_SECTION_11D_BASE}#savings_income_charged_under_section_11d",
        "pe": "taxed_savings_income",
        "tolerance": 0.25,
    },
    "income_tax_on_section_11d_savings_income": {
        "axiom": f"{INCOME_TAX_SECTION_11D_BASE}#income_tax_on_section_11d_savings_income",
        "pe": "savings_income_tax",
        "tolerance": 0.25,
    },
}

INCOME_TAX_SECTION_13_OUTPUTS = {
    "dividend_income_charged_under_section_13": {
        "axiom": f"{INCOME_TAX_SECTION_13_BASE}#dividend_income_charged_under_section_13",
        "pe": "taxed_dividend_income",
        "tolerance": 0.1,
    },
    "income_tax_on_section_13_dividend_income": {
        "axiom": f"{INCOME_TAX_SECTION_13_BASE}#income_tax_on_section_13_dividend_income",
        "pe": "dividend_income_tax",
        "tolerance": 0.1,
    },
}

CHILD_BENEFIT_OUTPUTS = {
    "child_benefit_weekly_rate": {
        "axiom": f"{CHILD_BENEFIT_BASE}#child_benefit_weekly_rate",
        "pe": "child_benefit_respective_amount",
        "pe_transform": "annual_to_weekly",
    },
}

CHILD_BENEFIT_FINAL_OUTPUTS = {
    "child_benefit_weekly_amount": {
        "axiom": f"{CHILD_BENEFIT_FINAL_BASE}#child_benefit_weekly_amount",
        "pe": "child_benefit",
        "pe_transform": "annual_to_weekly",
    },
}

BENEFIT_CAP_RELEVANT_AMOUNT_OUTPUTS = {
    "benefit_cap_relevant_amount": {
        "axiom": f"{BENEFIT_CAP_REGULATION_80A_BASE}#benefit_cap_relevant_amount",
        "pe": "benefit_cap",
        "pe_transform": "annual_to_monthly",
    },
}

STATE_PENSION_CREDIT_QUALIFYING_AGE_OUTPUTS = {
    "qualifying_age": {
        "axiom": f"{STATE_PENSION_CREDIT_SECTION_1_BASE}#qualifying_age",
        "pe": "state_pension_age",
    },
    "claimant_has_attained_qualifying_age": {
        "axiom": (
            f"{STATE_PENSION_CREDIT_SECTION_1_BASE}"
            "#claimant_has_attained_qualifying_age"
        ),
        "pe": "is_SP_age",
    },
}

STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS = {
    "appropriate_minimum_guarantee": {
        "axiom": (
            f"{STATE_PENSION_CREDIT_SECTION_2_BASE}#appropriate_minimum_guarantee"
        ),
        "pe": "minimum_guarantee",
        "tolerance": 0.1,
    },
    "guarantee_credit": {
        "axiom": f"{STATE_PENSION_CREDIT_SECTION_2_BASE}#guarantee_credit",
        "pe": "guarantee_credit",
        "tolerance": 0.1,
    },
}

STATE_PENSION_CREDIT_SAVINGS_CREDIT_OUTPUTS = {
    "savings_credit": {
        "axiom": f"{STATE_PENSION_CREDIT_SECTION_3_BASE}#savings_credit",
        "pe": "savings_credit",
        "tolerance": 0.1,
    },
}

STATE_PENSION_FINAL_OUTPUTS = {
    "state_pension_weekly_amount": {
        "axiom": f"{STATE_PENSION_FINAL_BASE}#state_pension_weekly_amount",
        "pe": "state_pension",
        "pe_transform": "annual_to_weekly",
        "tolerance": 0.01,
    },
}

PENSION_CREDIT_OUTPUTS = {
    "standard_minimum_guarantee": {
        "axiom": f"{PENSION_CREDIT_BASE}#standard_minimum_guarantee",
        "pe": "standard_minimum_guarantee",
        "pe_transform": "annual_to_weekly",
    },
    "severe_disability_additional_amount": {
        "axiom": f"{PENSION_CREDIT_BASE}#severe_disability_additional_amount",
        "pe": "severe_disability_minimum_guarantee_addition",
        "pe_transform": "annual_to_weekly",
    },
    "carer_additional_amount": {
        "axiom": f"{PENSION_CREDIT_BASE}#carer_additional_amount",
        "pe": "carer_minimum_guarantee_addition",
        "pe_transform": "annual_to_weekly_per_carer",
    },
}

PENSION_CREDIT_CHILD_ADDITION_OUTPUTS = {
    "additional_amount_applicable": {
        "axiom": f"{PENSION_CREDIT_SCHEDULE_IIA_BASE}#additional_amount_applicable",
        "pe": "child_minimum_guarantee_addition",
        "pe_transform": "annual_to_weekly",
        "tolerance": 0.01,
    },
}

PENSION_CREDIT_DEEMED_INCOME_OUTPUTS = {
    "capital_deemed_weekly_income": {
        "axiom": f"{PENSION_CREDIT_REGULATION_15_BASE}#capital_deemed_weekly_income",
        "pe": "pension_credit_deemed_income",
        "pe_transform": "annual_to_weekly",
        "tolerance": 0.01,
    },
}

PENSION_CREDIT_FINAL_OUTPUTS = {
    "pension_credit_annual_amount": {
        "axiom": f"{PENSION_CREDIT_FINAL_BASE}#pension_credit_annual_amount",
        "pe": "pension_credit",
        "tolerance": 0.01,
    },
}

ESA_TARIFF_INCOME_OUTPUTS = {
    "capital_tariff_weekly_income": {
        "axiom": f"{ESA_REGULATION_118_BASE}#capital_tariff_weekly_income",
        "pe": "esa_income_tariff_income",
        "pe_transform": "annual_to_weekly",
        "capital_pe": "esa_income_assessable_capital",
        "applies": "legacy_capital_tariff_income_defined",
    },
}

ESA_FINAL_OUTPUTS = {
    "income_related_esa_annual_amount": {
        "axiom": f"{ESA_FINAL_BASE}#income_related_esa_annual_amount",
        "pe": "esa_income",
        "tolerance": 0.01,
    },
}

JSA_TARIFF_INCOME_OUTPUTS = {
    "capital_tariff_weekly_income": {
        "axiom": f"{JSA_REGULATION_116_BASE}#capital_tariff_weekly_income",
        "pe": "jsa_income_tariff_income",
        "pe_transform": "annual_to_weekly",
        "capital_pe": "jsa_income_assessable_capital",
        "applies": "legacy_capital_tariff_income_defined",
    },
}

INCOME_SUPPORT_TARIFF_INCOME_OUTPUTS = {
    "capital_tariff_weekly_income": {
        "axiom": f"{INCOME_SUPPORT_REGULATION_53_BASE}#capital_tariff_weekly_income",
        "pe": "income_support_tariff_income",
        "pe_transform": "annual_to_weekly",
        "capital_pe": "income_support_assessable_capital",
        "applies": "legacy_capital_tariff_income_defined",
    },
}

HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS = {
    "capital_tariff_weekly_income": {
        "axiom": f"{HOUSING_BENEFIT_REGULATION_52_BASE}#capital_tariff_weekly_income",
        "pe": "housing_benefit_tariff_income",
        "pe_transform": "annual_to_weekly",
        "capital_pe": "housing_benefit_assessable_capital",
        "applies": "housing_benefit_working_age_tariff_income_defined",
    },
}

HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS = {
    "capital_tariff_weekly_income": {
        "axiom": (
            f"{HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_BASE}"
            "#capital_tariff_weekly_income"
        ),
        "pe": "housing_benefit_tariff_income",
        "pe_transform": "annual_to_weekly",
        "applies": "housing_benefit_pension_age_tariff_income_defined",
    },
}

HOUSING_BENEFIT_FINAL_OUTPUTS = {
    "housing_benefit_annual_amount": {
        "axiom": f"{HOUSING_BENEFIT_FINAL_BASE}#housing_benefit_annual_amount",
        "pe": "housing_benefit",
        "tolerance": 0.01,
    },
}

UNIVERSAL_CREDIT_STANDARD_ALLOWANCE_OUTPUTS = {
    "standard_allowance_single_under_25": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#standard_allowance_single_under_25_amount",
        "pe": "uc_standard_allowance",
        "pe_transform": "annual_to_monthly",
        "applies": ("uc_standard_allowance_claimant_type", "SINGLE_YOUNG"),
    },
    "standard_allowance_single_25_or_over": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#standard_allowance_single_25_or_over_amount",
        "pe": "uc_standard_allowance",
        "pe_transform": "annual_to_monthly",
        "applies": ("uc_standard_allowance_claimant_type", "SINGLE_OLD"),
    },
    "standard_allowance_joint_both_under_25": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#standard_allowance_joint_both_under_25_amount",
        "pe": "uc_standard_allowance",
        "pe_transform": "annual_to_monthly",
        "applies": ("uc_standard_allowance_claimant_type", "COUPLE_YOUNG"),
    },
    "standard_allowance_joint_either_25_or_over": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#standard_allowance_joint_either_25_or_over_amount",
        "pe": "uc_standard_allowance",
        "pe_transform": "annual_to_monthly",
        "applies": ("uc_standard_allowance_claimant_type", "COUPLE_OLD"),
    },
}

UNIVERSAL_CREDIT_CHILD_ELEMENT_OUTPUTS = {
    "child_element_first_child_or_qualifying_young_person": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#first_child_element_amount",
        "pe": "uc_individual_child_element",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_first_child_element",
    },
    "child_element_second_and_each_subsequent_child_or_qualifying_young_person": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#second_and_subsequent_child_element_amount",
        "pe": "uc_individual_child_element",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_subsequent_child_element",
    },
    "disabled_child_additional_amount_lower_rate": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#disabled_child_lower_rate_amount",
        "pe": "uc_individual_disabled_child_element",
        "pe_transform": "annual_to_monthly",
        "applies": "positive_pe_output",
    },
    "disabled_child_additional_amount_higher_rate": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#disabled_child_higher_rate_amount",
        "pe": "uc_individual_severely_disabled_child_element",
        "pe_transform": "annual_to_monthly",
        "applies": "positive_pe_output",
    },
}

UNIVERSAL_CREDIT_LCWRA_OUTPUTS = {
    "lcwra_element_standard_lcwra_claimant": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#lcwra_ordinary_claimant_amount",
        "pe": "uc_LCWRA_element",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_lcwra_standard_amount",
    },
    "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#lcwra_protected_claimant_amount",
        "pe": "uc_LCWRA_element",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_lcwra_higher_amount",
    },
}

UNIVERSAL_CREDIT_CARER_OUTPUTS = {
    "carer_element": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#carer_element_amount",
        "pe": "uc_carer_element",
        "pe_transform": "annual_to_monthly",
        "applies": "positive_pe_output",
    },
}

UNIVERSAL_CREDIT_CHILDCARE_OUTPUTS = {
    "childcare_costs_element_maximum_one_child": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#childcare_costs_element_one_child_maximum_amount",
        "pe": "uc_maximum_childcare_element_amount",
        "pe_transform": "annual_to_monthly",
        "applies": ("uc_childcare_element_eligible_children", 1),
    },
    "childcare_costs_element_maximum_two_or_more_children": {
        "axiom": f"{UNIVERSAL_CREDIT_BASE}#childcare_costs_element_two_or_more_children_maximum_amount",
        "pe": "uc_maximum_childcare_element_amount",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_childcare_two_or_more_children",
    },
}

UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS = {
    "work_condition_met_for_assessment_period": {
        "axiom": (
            f"{UNIVERSAL_CREDIT_REGULATION_32_BASE}"
            "#work_condition_met_for_assessment_period"
        ),
        "pe": "uc_childcare_work_condition",
    },
}

UNIVERSAL_CREDIT_CHILDCARE_ELEMENT_OUTPUTS = {
    "childcare_costs_element_amount": {
        "axiom": f"{UNIVERSAL_CREDIT_REGULATION_34_BASE}#childcare_costs_element_amount",
        "pe": "uc_childcare_element",
        "pe_transform": "annual_to_monthly",
    },
}

UNIVERSAL_CREDIT_AWARD_OUTPUTS = {
    "universal_credit_maximum_amount": {
        "axiom": f"{WELFARE_REFORM_ACT_SECTION_8_BASE}#universal_credit_maximum_amount",
        "pe": "uc_maximum_amount",
        "pe_transform": "annual_to_monthly",
    },
    "universal_credit_amounts_to_be_deducted": {
        "axiom": (
            f"{WELFARE_REFORM_ACT_SECTION_8_BASE}"
            "#universal_credit_amounts_to_be_deducted"
        ),
        "pe": "uc_income_reduction",
        "pe_transform": "annual_to_monthly",
    },
    "universal_credit_award_amount": {
        "axiom": f"{WELFARE_REFORM_ACT_SECTION_8_BASE}#universal_credit_award_amount",
        "pe_expression": "uc_award_before_takeup",
        "pe_transform": "annual_to_monthly",
    },
}

UNIVERSAL_CREDIT_FINAL_OUTPUTS = {
    "universal_credit_annual_amount": {
        "axiom": f"{UNIVERSAL_CREDIT_FINAL_BASE}#universal_credit_annual_amount",
        "pe": "universal_credit",
        "tolerance": 0.01,
    },
}

UNIVERSAL_CREDIT_HOUSING_COSTS_OUTPUTS = {
    "section_11_amount_for_accommodation_payments": {
        "axiom": (
            f"{WELFARE_REFORM_ACT_SECTION_11_BASE}"
            "#section_11_amount_for_accommodation_payments"
        ),
        "pe": "uc_housing_costs_element",
        "pe_transform": "annual_to_monthly",
    },
}

UNIVERSAL_CREDIT_WORK_ALLOWANCE_OUTPUTS = {
    "applicable_work_allowance_amount": {
        "axiom": (
            f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#applicable_work_allowance_amount"
        ),
        "pe": "uc_work_allowance",
        "pe_transform": "annual_to_monthly",
    },
}

UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS = {
    "earned_income_amount_subject_to_taper": {
        "axiom": (
            f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}"
            "#earned_income_amount_subject_to_taper"
        ),
        "pe": "uc_earned_income",
        "pe_transform": "annual_to_monthly",
    },
    "unearned_income_for_deduction": {
        "axiom": f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#unearned_income_for_deduction",
        "pe": "uc_unearned_income",
        "pe_transform": "annual_to_monthly",
    },
    "universal_credit_award_deduction_from_maximum_amount": {
        "axiom": (
            f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}"
            "#universal_credit_award_deduction_from_maximum_amount"
        ),
        "pe": "uc_income_reduction",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_income_reduction_uncapped",
    },
}

UNIVERSAL_CREDIT_ASSESSABLE_CAPITAL_OUTPUTS = {
    "claimant_capital_for_prescribed_capital_limit": {
        "axiom": (
            f"{UNIVERSAL_CREDIT_REGULATION_18_BASE}"
            "#claimant_capital_for_prescribed_capital_limit"
        ),
        "pe": "uc_assessable_capital",
        "tolerance": 0.1,
    },
}

UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS = {
    "capital_tariff_monthly_income": {
        "axiom": f"{UNIVERSAL_CREDIT_REGULATION_72_BASE}#capital_tariff_monthly_income",
        "pe": "uc_tariff_income",
        "pe_transform": "annual_to_monthly",
        "applies": "uc_tariff_income_defined",
    },
}

UNIVERSAL_CREDIT_2026_RULESPEC_RATES = {
    "standard_allowance_single_under_25": 338.58,
    "standard_allowance_single_25_or_over": 424.90,
    "standard_allowance_joint_both_under_25": 528.34,
    "standard_allowance_joint_either_25_or_over": 666.97,
    "child_element_first_child_or_qualifying_young_person": 351.88,
    "child_element_second_and_each_subsequent_child_or_qualifying_young_person": 303.94,
    "disabled_child_additional_amount_lower_rate": 164.79,
    "disabled_child_additional_amount_higher_rate": 514.71,
    "lcwra_element_standard_lcwra_claimant": 217.26,
    "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant": 429.80,
    "carer_element": 209.34,
    "childcare_costs_element_maximum_one_child": 1071.09,
    "childcare_costs_element_maximum_two_or_more_children": 1836.16,
    "childcare_costs_element_reimbursement_rate": 0.85,
    "earned_income_taper_rate": 0.55,
}

STUDENT_LOAN_REPAYMENT_OUTPUTS = {
    "student_loan_repayment": {
        "axiom": f"{STUDENT_LOAN_REPAYMENT_BASE}#student_loan_repayment",
        "pe": "student_loan_repayment",
    },
}

CARERS_ALLOWANCE_FINAL_OUTPUTS = {
    "carers_allowance_annual_amount": {
        "axiom": f"{CARERS_ALLOWANCE_FINAL_BASE}#carers_allowance_annual_amount",
        "pe": "carers_allowance",
    },
}

CARER_SUPPORT_PAYMENT_FINAL_OUTPUTS = {
    "carer_support_payment_annual_amount": {
        "axiom": (
            f"{CARER_SUPPORT_PAYMENT_FINAL_BASE}#carer_support_payment_annual_amount"
        ),
        "pe": "carer_support_payment",
    },
}

SCOTTISH_CHILD_PAYMENT_FINAL_OUTPUTS = {
    "scottish_child_payment_annual_amount": {
        "axiom": (
            f"{SCOTTISH_CHILD_PAYMENT_FINAL_BASE}#scottish_child_payment_annual_amount"
        ),
        "pe": "scottish_child_payment",
    },
}

SDA_FINAL_OUTPUTS = {
    "severe_disablement_allowance_annual_amount": {
        "axiom": (f"{SDA_FINAL_BASE}#severe_disablement_allowance_annual_amount"),
        "pe": "sda",
    },
}

DLA_FINAL_OUTPUTS = {
    "disability_living_allowance_self_care_weekly_amount": {
        "axiom": f"{DLA_FINAL_BASE}#dla_care_component_weekly_amount",
        "pe": "dla_sc",
        "pe_transform": "annual_to_weekly",
        "tolerance": 0.01,
    },
    "disability_living_allowance_mobility_weekly_amount": {
        "axiom": f"{DLA_FINAL_BASE}#dla_mobility_component_weekly_amount",
        "pe": "dla_m",
        "pe_transform": "annual_to_weekly",
        "tolerance": 0.01,
    },
    "disability_living_allowance_annual_amount": {
        "axiom": f"{DLA_FINAL_BASE}#disability_living_allowance_annual_amount",
        "pe": "dla",
        "tolerance": 0.01,
    },
}


@dataclass(frozen=True)
class UKEFRSSurfaceSpec:
    program: Path
    entity: str
    outputs: dict[str, dict[str, Any]]
    pe_variables: tuple[str, ...]
    projection_person_variables: tuple[str, ...] = ()


SURFACE_SPECS = {
    "national-insurance-class-1": UKEFRSSurfaceSpec(
        program=NATIONAL_INSURANCE_SECTION_8_PROGRAM_PATH,
        entity="person",
        outputs=NATIONAL_INSURANCE_CLASS_1_OUTPUTS,
        pe_variables=(
            "ni_class_1_employee",
            "ni_class_1_employee_additional",
            "ni_class_1_employee_primary",
            "ni_class_1_income",
            "ni_employee",
            "ni_liable",
        ),
    ),
    "national-insurance-class-4": UKEFRSSurfaceSpec(
        program=NATIONAL_INSURANCE_SECTION_15_PROGRAM_PATH,
        entity="person",
        outputs=NATIONAL_INSURANCE_CLASS_4_OUTPUTS,
        pe_variables=(
            "ni_class_1_employee",
            "ni_class_4_main",
            "ni_liable",
            "self_employment_income",
        ),
    ),
    "national-insurance-class-4-final": UKEFRSSurfaceSpec(
        program=NATIONAL_INSURANCE_REGULATION_100_PROGRAM_PATH,
        entity="person",
        outputs=NATIONAL_INSURANCE_REGULATION_100_OUTPUTS,
        pe_variables=(
            "ni_class_1_employee",
            "ni_class_1_employee_primary",
            "ni_class_4",
            "ni_class_4_main",
            "ni_class_4_maximum",
            "ni_liable",
            "self_employment_income",
        ),
    ),
    "national-insurance-final": UKEFRSSurfaceSpec(
        program=NATIONAL_INSURANCE_SECTION_1_PROGRAM_PATH,
        entity="person",
        outputs=NATIONAL_INSURANCE_FINAL_OUTPUTS,
        pe_variables=(
            "national_insurance",
            "ni_class_1_employee",
            "ni_class_2",
            "ni_class_3",
            "ni_class_4",
        ),
    ),
    "personal-allowance": UKEFRSSurfaceSpec(
        program=PERSONAL_ALLOWANCE_PROGRAM_PATH,
        entity="person",
        outputs=PERSONAL_ALLOWANCE_OUTPUTS,
        pe_variables=(
            "adjusted_net_income",
            "gift_aid_grossed_up",
            "personal_allowance",
        ),
    ),
    "income-tax-income-base": UKEFRSSurfaceSpec(
        program=INCOME_TAX_SECTION_23_PROGRAM_PATH,
        entity="person",
        outputs=INCOME_TAX_INCOME_BASE_OUTPUTS,
        pe_variables=(
            "adjusted_net_income",
            *INCOME_TAX_INCOME_BASE_COMPONENTS,
            *INCOME_TAX_SECTION_23_ADDITION_COMPONENTS,
            *INCOME_TAX_SECTION_23_REDUCTION_COMPONENTS,
            "income_tax",
            "total_income",
        ),
    ),
    "income-tax-section-10-earned-income": UKEFRSSurfaceSpec(
        program=INCOME_TAX_SECTION_10_PROGRAM_PATH,
        entity="person",
        outputs=INCOME_TAX_SECTION_10_OUTPUTS,
        pe_variables=(
            "add_rate_earned_income",
            "add_rate_earned_income_tax",
            "basic_rate_earned_income",
            "basic_rate_earned_income_tax",
            "earned_income_tax",
            "earned_taxable_income",
            "higher_rate_earned_income",
            "higher_rate_earned_income_tax",
            "pays_scottish_income_tax",
        ),
    ),
    "income-tax-section-11d-savings-income": UKEFRSSurfaceSpec(
        program=INCOME_TAX_SECTION_11D_PROGRAM_PATH,
        entity="person",
        outputs=INCOME_TAX_SECTION_11D_OUTPUTS,
        pe_variables=(
            "add_rate_savings_income",
            "basic_rate_savings_income",
            "earned_taxable_income",
            "higher_rate_savings_income",
            "received_allowances_savings_income",
            "savings_allowance",
            "savings_income_tax",
            "savings_starter_rate_income",
            "taxable_savings_interest_income",
            "taxed_savings_income",
        ),
    ),
    "income-tax-section-13-dividend-income": UKEFRSSurfaceSpec(
        program=INCOME_TAX_SECTION_13_PROGRAM_PATH,
        entity="person",
        outputs=INCOME_TAX_SECTION_13_OUTPUTS,
        pe_variables=(
            "dividend_income_tax",
            "earned_taxable_income",
            "received_allowances_dividend_income",
            "received_allowances_savings_income",
            "taxable_dividend_income",
            "taxable_savings_interest_income",
            "taxed_dividend_income",
        ),
    ),
    "child-benefit": UKEFRSSurfaceSpec(
        program=CHILD_BENEFIT_PROGRAM_PATH,
        entity="person",
        outputs=CHILD_BENEFIT_OUTPUTS,
        pe_variables=(
            "child_benefit_child_index",
            "child_benefit_respective_amount",
        ),
    ),
    "child-benefit-final": UKEFRSSurfaceSpec(
        program=CHILD_BENEFIT_FINAL_PROGRAM_PATH,
        entity="benunit",
        outputs=CHILD_BENEFIT_FINAL_OUTPUTS,
        pe_variables=(
            "child_benefit",
            "child_benefit_entitlement",
            "would_claim_child_benefit",
        ),
        projection_person_variables=(
            "child_benefit_child_index",
            "child_benefit_respective_amount",
        ),
    ),
    "benefit-cap-relevant-amount": UKEFRSSurfaceSpec(
        program=BENEFIT_CAP_REGULATION_80A_PROGRAM_PATH,
        entity="benunit",
        outputs=BENEFIT_CAP_RELEVANT_AMOUNT_OUTPUTS,
        pe_variables=(
            "benefit_cap",
            "benunit_region",
            "num_adults",
            "num_children",
        ),
    ),
    "state-pension-credit-qualifying-age": UKEFRSSurfaceSpec(
        program=STATE_PENSION_CREDIT_SECTION_1_PROGRAM_PATH,
        entity="person",
        outputs=STATE_PENSION_CREDIT_QUALIFYING_AGE_OUTPUTS,
        pe_variables=(
            "age",
            "gender",
            "is_SP_age",
            "state_pension_age",
        ),
    ),
    "state-pension-credit-guarantee-credit": UKEFRSSurfaceSpec(
        program=STATE_PENSION_CREDIT_SECTION_2_PROGRAM_PATH,
        entity="benunit",
        outputs=STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS,
        pe_variables=(
            "guarantee_credit",
            "is_guarantee_credit_eligible",
            "minimum_guarantee",
            "pension_credit_income",
            "standard_minimum_guarantee",
        ),
    ),
    "state-pension-credit-savings-credit": UKEFRSSurfaceSpec(
        program=STATE_PENSION_CREDIT_SECTION_3_PROGRAM_PATH,
        entity="benunit",
        outputs=STATE_PENSION_CREDIT_SAVINGS_CREDIT_OUTPUTS,
        pe_variables=(
            "is_savings_credit_eligible",
            "minimum_guarantee",
            "pension_credit_income",
            "relation_type",
            "savings_credit",
            "savings_credit_income",
            "standard_minimum_guarantee",
        ),
    ),
    "state-pension-final": UKEFRSSurfaceSpec(
        program=STATE_PENSION_FINAL_PROGRAM_PATH,
        entity="person",
        outputs=STATE_PENSION_FINAL_OUTPUTS,
        pe_variables=(
            "state_pension",
            "state_pension_reported",
            "state_pension_type",
        ),
    ),
    "pension-credit": UKEFRSSurfaceSpec(
        program=PENSION_CREDIT_PROGRAM_PATH,
        entity="benunit",
        outputs=PENSION_CREDIT_OUTPUTS,
        pe_variables=(
            "carer_minimum_guarantee_addition",
            "is_couple",
            "num_carers",
            "relation_type",
            "severe_disability_minimum_guarantee_addition",
            "standard_minimum_guarantee",
        ),
    ),
    "pension-credit-child-addition": UKEFRSSurfaceSpec(
        program=PENSION_CREDIT_SCHEDULE_IIA_PROGRAM_PATH,
        entity="benunit",
        outputs=PENSION_CREDIT_CHILD_ADDITION_OUTPUTS,
        pe_variables=("child_minimum_guarantee_addition",),
        projection_person_variables=(
            "birth_year",
            "dla",
            "is_child_or_qualifying_young_person_for_pension_credit",
            "pip",
            "receives_enhanced_pip_dl",
            "receives_highest_dla_sc",
        ),
    ),
    "pension-credit-deemed-income": UKEFRSSurfaceSpec(
        program=PENSION_CREDIT_REGULATION_15_PROGRAM_PATH,
        entity="benunit",
        outputs=PENSION_CREDIT_DEEMED_INCOME_OUTPUTS,
        pe_variables=(
            "pension_credit_assessable_capital",
            "pension_credit_deemed_income",
        ),
    ),
    "pension-credit-final": UKEFRSSurfaceSpec(
        program=PENSION_CREDIT_FINAL_PROGRAM_PATH,
        entity="benunit",
        outputs=PENSION_CREDIT_FINAL_OUTPUTS,
        pe_variables=(
            "pension_credit",
            "pension_credit_entitlement",
            "would_claim_pc",
        ),
    ),
    "esa-income-tariff-income": UKEFRSSurfaceSpec(
        program=ESA_REGULATION_118_PROGRAM_PATH,
        entity="benunit",
        outputs=ESA_TARIFF_INCOME_OUTPUTS,
        pe_variables=(
            "esa_income_assessable_capital",
            "esa_income_tariff_income",
        ),
    ),
    "esa-income-final": UKEFRSSurfaceSpec(
        program=ESA_FINAL_PROGRAM_PATH,
        entity="benunit",
        outputs=ESA_FINAL_OUTPUTS,
        pe_variables=(
            "esa_income",
            "esa_income_eligible",
            "esa_income_tariff_income",
        ),
        projection_person_variables=("esa_income_reported",),
    ),
    "jsa-income-tariff-income": UKEFRSSurfaceSpec(
        program=JSA_REGULATION_116_PROGRAM_PATH,
        entity="benunit",
        outputs=JSA_TARIFF_INCOME_OUTPUTS,
        pe_variables=(
            "jsa_income_assessable_capital",
            "jsa_income_tariff_income",
        ),
    ),
    "income-support-tariff-income": UKEFRSSurfaceSpec(
        program=INCOME_SUPPORT_REGULATION_53_PROGRAM_PATH,
        entity="benunit",
        outputs=INCOME_SUPPORT_TARIFF_INCOME_OUTPUTS,
        pe_variables=(
            "income_support_assessable_capital",
            "income_support_tariff_income",
        ),
    ),
    "housing-benefit-working-age-tariff-income": UKEFRSSurfaceSpec(
        program=HOUSING_BENEFIT_REGULATION_52_PROGRAM_PATH,
        entity="benunit",
        outputs=HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS,
        pe_variables=(
            "guarantee_credit",
            "housing_benefit_assessable_capital",
            "housing_benefit_tariff_income",
        ),
        projection_person_variables=("is_SP_age",),
    ),
    "housing-benefit-pension-age-tariff-income": UKEFRSSurfaceSpec(
        program=HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_PROGRAM_PATH,
        entity="benunit",
        outputs=HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS,
        pe_variables=(
            "guarantee_credit",
            "housing_benefit_assessable_capital",
            "housing_benefit_tariff_income",
        ),
        projection_person_variables=("is_SP_age",),
    ),
    "housing-benefit-final": UKEFRSSurfaceSpec(
        program=HOUSING_BENEFIT_FINAL_PROGRAM_PATH,
        entity="benunit",
        outputs=HOUSING_BENEFIT_FINAL_OUTPUTS,
        pe_variables=(
            "benefit_cap_reduction",
            "housing_benefit",
            "housing_benefit_pre_benefit_cap",
            "would_claim_housing_benefit",
        ),
    ),
    "universal-credit-standard-allowance": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_STANDARD_ALLOWANCE_OUTPUTS,
        pe_variables=(
            "uc_standard_allowance",
            "uc_standard_allowance_claimant_type",
        ),
    ),
    "universal-credit-child-element": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_PROGRAM_PATH,
        entity="person",
        outputs=UNIVERSAL_CREDIT_CHILD_ELEMENT_OUTPUTS,
        pe_variables=(
            "uc_child_index",
            "uc_individual_child_element",
            "uc_individual_disabled_child_element",
            "uc_individual_severely_disabled_child_element",
            "uc_is_child_born_before_child_limit",
        ),
    ),
    "universal-credit-lcwra-element": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_LCWRA_OUTPUTS,
        pe_variables=("uc_LCWRA_element",),
    ),
    "universal-credit-carer-element": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_CARER_OUTPUTS,
        pe_variables=("uc_carer_element",),
    ),
    "universal-credit-childcare-cap": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_CHILDCARE_OUTPUTS,
        pe_variables=(
            "uc_childcare_element_eligible_children",
            "uc_maximum_childcare_element_amount",
        ),
    ),
    "universal-credit-childcare-work-condition": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_REGULATION_32_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS,
        pe_variables=("uc_childcare_work_condition",),
        projection_person_variables=(
            "in_work",
            "is_adult",
        ),
    ),
    "universal-credit-childcare-element": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_REGULATION_34_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_CHILDCARE_ELEMENT_OUTPUTS,
        pe_variables=(
            "uc_childcare_element",
            "uc_maximum_childcare_element_amount",
        ),
    ),
    "universal-credit-award": UKEFRSSurfaceSpec(
        program=WELFARE_REFORM_ACT_SECTION_8_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_AWARD_OUTPUTS,
        pe_variables=(
            "is_uc_eligible",
            "uc_carer_element",
            "uc_child_element",
            "uc_childcare_element",
            "uc_disability_elements",
            "uc_housing_costs_element",
            "uc_income_reduction",
            "uc_maximum_amount",
            "uc_standard_allowance",
        ),
    ),
    "universal-credit-final": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_FINAL_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_FINAL_OUTPUTS,
        pe_variables=(
            "benefit_cap_reduction",
            "universal_credit",
            "universal_credit_pre_benefit_cap",
            "would_claim_uc",
        ),
    ),
    "universal-credit-housing-costs": UKEFRSSurfaceSpec(
        program=WELFARE_REFORM_ACT_SECTION_11_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_HOUSING_COSTS_OUTPUTS,
        pe_variables=("uc_housing_costs_element",),
    ),
    "universal-credit-work-allowance": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_REGULATION_22_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_WORK_ALLOWANCE_OUTPUTS,
        pe_variables=(
            "is_uc_work_allowance_eligible",
            "num_adults",
            "num_children",
            "uc_housing_costs_element",
            "uc_work_allowance",
        ),
    ),
    "universal-credit-income-deduction": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_REGULATION_22_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS,
        pe_variables=(
            "is_uc_work_allowance_eligible",
            "num_adults",
            "num_children",
            "uc_earned_income",
            "uc_housing_costs_element",
            "uc_income_reduction",
            "uc_maximum_amount",
            "uc_unearned_income",
            "uc_work_allowance",
        ),
    ),
    "universal-credit-assessable-capital": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_REGULATION_18_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_ASSESSABLE_CAPITAL_OUTPUTS,
        pe_variables=("uc_assessable_capital",),
    ),
    "universal-credit-tariff-income": UKEFRSSurfaceSpec(
        program=UNIVERSAL_CREDIT_REGULATION_72_PROGRAM_PATH,
        entity="benunit",
        outputs=UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS,
        pe_variables=(
            "is_uc_eligible",
            "uc_assessable_capital",
            "uc_tariff_income",
        ),
    ),
    "student-loan-repayment": UKEFRSSurfaceSpec(
        program=STUDENT_LOAN_REPAYMENT_PROGRAM_PATH,
        entity="person",
        outputs=STUDENT_LOAN_REPAYMENT_OUTPUTS,
        pe_variables=(
            "adjusted_net_income",
            "student_loan_plan",
            "student_loan_repayment",
        ),
    ),
    "carers-allowance-final": UKEFRSSurfaceSpec(
        program=CARERS_ALLOWANCE_FINAL_PROGRAM_PATH,
        entity="person",
        outputs=CARERS_ALLOWANCE_FINAL_OUTPUTS,
        pe_variables=(
            "age",
            "care_hours",
            "carers_allowance",
            "carers_allowance_reported",
            "country",
        ),
    ),
    "carer-support-payment-final": UKEFRSSurfaceSpec(
        program=CARER_SUPPORT_PAYMENT_FINAL_PROGRAM_PATH,
        entity="person",
        outputs=CARER_SUPPORT_PAYMENT_FINAL_OUTPUTS,
        pe_variables=(
            "age",
            "care_hours",
            "carer_support_payment",
            "carers_allowance_reported",
            "country",
        ),
    ),
    "scottish-child-payment-final": UKEFRSSurfaceSpec(
        program=SCOTTISH_CHILD_PAYMENT_FINAL_PROGRAM_PATH,
        entity="person",
        outputs=SCOTTISH_CHILD_PAYMENT_FINAL_OUTPUTS,
        pe_variables=(
            "age",
            "is_scp_eligible",
            "scottish_child_payment",
            "would_claim_scp",
        ),
    ),
    "severe-disablement-allowance-final": UKEFRSSurfaceSpec(
        program=SDA_FINAL_PROGRAM_PATH,
        entity="person",
        outputs=SDA_FINAL_OUTPUTS,
        pe_variables=(
            "sda",
            "sda_reported",
        ),
    ),
    "disability-living-allowance-final": UKEFRSSurfaceSpec(
        program=DLA_FINAL_PROGRAM_PATH,
        entity="person",
        outputs=DLA_FINAL_OUTPUTS,
        pe_variables=(
            "age",
            "dla",
            "dla_m",
            "dla_m_category",
            "dla_sc",
            "dla_sc_category",
        ),
    ),
}

HBAI_FIXED_INPUT_COMPONENTS = frozenset(
    {
        "afcs",
        "bsp",
        "council_tax",
        "council_tax_benefit",
        "dividend_income",
        "domestic_rates",
        "employee_pension_contributions",
        "employment_income",
        "esa_contrib",
        "external_child_payments",
        "free_school_fruit_veg",
        "free_school_meals",
        "free_school_milk",
        "healthy_start_vouchers",
        "iidb",
        "incapacity_benefit",
        "jsa_contrib",
        "maintenance_expenses",
        "maintenance_income",
        "maternity_allowance",
        "miscellaneous_income",
        "personal_pension_contributions",
        "private_pension_income",
        "private_transfer_income",
        "property_income",
        "savings_interest_income",
        "self_employment_income",
        "statutory_maternity_pay",
        "statutory_sick_pay",
    }
)

HBAI_OUT_OF_SCOPE_COMPONENTS = {
    "LVT": (
        "PolicyEngine UK's LVT placeholder is outside the current Axiom UK "
        "tax-benefit law encoding scope, so it is excluded from policy "
        "alignment coverage."
    ),
}

HBAI_COMPONENT_COVERAGE = {
    "income_tax": {
        "status": "exact",
        "surfaces": ("income-tax-income-base",),
        "covered_outputs": ("income_tax",),
        "rationale": "Axiom compares the Section 23 income tax liability output directly to PolicyEngine UK's income_tax variable.",
    },
    "national_insurance": {
        "status": "exact",
        "surfaces": (
            "national-insurance-class-1",
            "national-insurance-class-4",
            "national-insurance-class-4-final",
            "national-insurance-final",
        ),
        "covered_outputs": (
            "ni_employee",
            "ni_class_4_main",
            "ni_class_4",
            "national_insurance",
        ),
        "rationale": "Axiom covers employee Class 1 National Insurance, the main-rate Class 4 self-employed contribution, final Class 4 after Regulation 100's annual maximum, and the final annual PolicyEngine UK national_insurance aggregate of Class 1, Class 2, Class 3, and Class 4 contributions.",
    },
    "child_benefit": {
        "status": "exact",
        "surfaces": ("child-benefit", "child-benefit-final"),
        "covered_outputs": (
            "child_benefit_respective_amount",
            "child_benefit_entitlement",
            "child_benefit",
        ),
        "rationale": "Axiom covers per-child Child Benefit rates, section 141 weekly entitlement, and the final gross benefit-unit Child Benefit receipt after PolicyEngine UK's would_claim_child_benefit gate.",
    },
    "esa_income": {
        "status": "exact",
        "surfaces": ("esa-income-tariff-income", "esa-income-final"),
        "covered_outputs": ("esa_income_tariff_income", "esa_income"),
        "rationale": "Axiom covers capital tariff income used inside income-related ESA and the final annual PolicyEngine UK esa_income wrapper over reported ESA, tariff income, and the eligibility gate.",
    },
    "housing_benefit": {
        "status": "exact",
        "surfaces": (
            "housing-benefit-working-age-tariff-income",
            "housing-benefit-pension-age-tariff-income",
            "housing-benefit-final",
        ),
        "covered_outputs": (
            "housing_benefit_tariff_income",
            "housing_benefit",
        ),
        "rationale": "Axiom covers Housing Benefit capital tariff income branches and the final annual PolicyEngine UK housing_benefit wrapper after the claim gate and benefit-cap reduction.",
    },
    "income_support": {
        "status": "partial",
        "surfaces": ("income-support-tariff-income",),
        "covered_outputs": ("income_support_tariff_income",),
        "rationale": "Axiom covers Income Support capital tariff income, not the final Income Support HBAI amount.",
    },
    "jsa_income": {
        "status": "partial",
        "surfaces": ("jsa-income-tariff-income",),
        "covered_outputs": ("jsa_income_tariff_income",),
        "rationale": "Axiom covers capital tariff income used inside income-based JSA, not the final JSA HBAI amount.",
    },
    "pension_credit": {
        "status": "exact",
        "surfaces": (
            "state-pension-credit-guarantee-credit",
            "state-pension-credit-savings-credit",
            "pension-credit",
            "pension-credit-child-addition",
            "pension-credit-deemed-income",
            "pension-credit-final",
        ),
        "covered_outputs": (
            "guarantee_credit",
            "savings_credit",
            "standard_minimum_guarantee",
            "severe_disability_minimum_guarantee_addition",
            "carer_minimum_guarantee_addition",
            "child_minimum_guarantee_addition",
            "pension_credit_deemed_income",
            "pension_credit",
        ),
        "rationale": "Axiom covers major Pension Credit rates, additions, deemed-income components, and the final annual PolicyEngine UK pension_credit wrapper after the would_claim_pc gate.",
    },
    "state_pension": {
        "status": "exact",
        "surfaces": ("state-pension-rates", "state-pension-final"),
        "covered_outputs": (
            "basic_state_pension",
            "new_state_pension",
            "state_pension",
        ),
        "rationale": "Axiom covers the basic and full new State Pension weekly rates plus the final PolicyEngine UK state_pension receipt wrapper, which prorates reported dataset-year State Pension by current and data-year basic or new State Pension flat-rate ceilings.",
    },
    "universal_credit": {
        "status": "exact",
        "surfaces": (
            "universal-credit-standard-allowance",
            "universal-credit-child-element",
            "universal-credit-lcwra-element",
            "universal-credit-carer-element",
            "universal-credit-childcare-cap",
            "universal-credit-childcare-work-condition",
            "universal-credit-childcare-element",
            "universal-credit-award",
            "universal-credit-housing-costs",
            "universal-credit-work-allowance",
            "universal-credit-income-deduction",
            "universal-credit-assessable-capital",
            "universal-credit-tariff-income",
            "universal-credit-final",
        ),
        "covered_outputs": (
            "uc_standard_allowance",
            "uc_individual_child_element",
            "uc_individual_disabled_child_element",
            "uc_individual_severely_disabled_child_element",
            "uc_LCWRA_element",
            "uc_carer_element",
            "uc_childcare_element",
            "uc_maximum_amount",
            "uc_income_reduction",
            "uc_housing_costs_element",
            "uc_work_allowance",
            "uc_assessable_capital",
            "uc_tariff_income",
            "universal_credit",
        ),
        "rationale": "Axiom covers many Universal Credit legal elements, the award-before-take-up expression, and the final annual PolicyEngine UK universal_credit wrapper after the would_claim_uc gate and benefit-cap reduction.",
    },
    "student_loan_repayments": {
        "status": "partial",
        "surfaces": ("student-loan-repayment",),
        "covered_outputs": ("student_loan_repayment",),
        "rationale": "Axiom covers PolicyEngine UK's modelled student_loan_repayment formula by plan-specific threshold and repayment rate. The HBAI student_loan_repayments component remains partial because the validation population can supply it as reported input data even when student_loan_plan is NONE, overriding PolicyEngine UK's wrapper formula.",
    },
    "working_tax_credit": {
        "status": "partial",
        "surfaces": ("working-tax-credit-elements",),
        "covered_outputs": (
            "wtc_basic_element",
            "wtc_couple_element",
            "wtc_lone_parent_element",
            "wtc_disabled_worker_element",
            "wtc_severely_disabled_worker_element",
        ),
        "rationale": "Axiom covers Schedule 2 element rates after the WTC encoding; it does not yet compute final Working Tax Credit entitlement.",
    },
    "child_tax_credit": {
        "status": "partial",
        "surfaces": ("child-tax-credit-elements",),
        "covered_outputs": (
            "CTC_family_element",
            "CTC_child_element",
            "CTC_disabled_child_element",
            "CTC_severely_disabled_child_element",
        ),
        "rationale": "Axiom covers Child Tax Credit family, child, disabled-child, and severe-disabled-child element rates; it does not yet compute final Child Tax Credit entitlement.",
    },
    "tax_free_childcare": {
        "status": "partial",
        "surfaces": ("tax-free-childcare-parameters",),
        "covered_outputs": ("tax_free_childcare",),
        "rationale": "Axiom covers the Tax-Free Childcare contribution rate and income cap, not the child/provider eligibility tests, expenses, annual caps, or final aggregate amount.",
    },
    "free_tv_licence_value": {
        "status": "partial",
        "surfaces": ("tv-licence-fee",),
        "covered_outputs": ("colour_tv_licence_general_form_issue_fee",),
        "rationale": "Axiom covers the statutory colour TV licence fee feeding PolicyEngine UK's free_tv_licence_value; TV ownership, evasion, and aged or blind discount eligibility remain outside this fee surface.",
    },
    "pip": {
        "status": "exact",
        "surfaces": ("personal-independence-payment-rates",),
        "covered_outputs": (
            "pip_dl",
            "pip_m",
            "pip",
            "receives_enhanced_pip_dl",
        ),
        "rationale": "Axiom covers PolicyEngine UK's category-input Personal Independence Payment mechanics, including daily-living, mobility, enhanced daily-living receipt, and the final aggregate PIP amount; descriptor scoring and residence, age, care-home, and hospital exclusions remain held as inputs or outside PolicyEngine's current PIP formula.",
    },
    "dla": {
        "status": "exact",
        "surfaces": (
            "disability-living-allowance-rates",
            "disability-living-allowance-final",
        ),
        "covered_outputs": (
            "dla_sc",
            "dla_m",
            "dla",
        ),
        "rationale": "Axiom covers Disability Living Allowance weekly self-care and mobility rates plus the final annual PolicyEngine UK DLA wrapper using PE's category inputs.",
    },
    "attendance_allowance": {
        "status": "partial",
        "surfaces": ("attendance-allowance-rates",),
        "covered_outputs": ("attendance_allowance",),
        "rationale": "Axiom covers Attendance Allowance weekly higher and lower rates, not the category assignment or final aggregate Attendance Allowance amount.",
    },
    "carers_allowance": {
        "status": "exact",
        "surfaces": ("carers-allowance-rate", "carers-allowance-final"),
        "covered_outputs": ("carers_allowance",),
        "rationale": "Axiom covers the weekly Carer's Allowance rate and the final annual PolicyEngine UK carers_allowance wrapper, including the care-hours or reported-receipt gate and the Scotland Carer Support Payment replacement gate.",
    },
    "sda": {
        "status": "exact",
        "surfaces": (
            "severe-disablement-allowance-rates",
            "severe-disablement-allowance-final",
        ),
        "covered_outputs": ("sda",),
        "rationale": "Axiom covers the Severe Disablement Allowance maximum weekly rate and the final annual PolicyEngine UK sda wrapper over reported receipt.",
    },
    "ssmg": {
        "status": "partial",
        "surfaces": ("sure-start-maternity-grant-rate",),
        "covered_outputs": ("ssmg",),
        "rationale": "Axiom covers the Sure Start Maternity Grant amount, not the qualifying-benefit, pregnancy, child, prescribed-time, residence, or reported-receipt conditions feeding the final SSMG amount.",
    },
    "scottish_child_payment": {
        "status": "exact",
        "surfaces": (
            "scottish-child-payment-parameters",
            "scottish-child-payment-final",
        ),
        "covered_outputs": ("scottish_child_payment",),
        "rationale": "Axiom covers the Scottish Child Payment weekly amount, child age threshold, and final annual PolicyEngine UK scottish_child_payment wrapper after the eligibility and take-up gates.",
    },
    "carer_support_payment": {
        "status": "exact",
        "surfaces": (
            "carer-support-payment-parameters",
            "carer-support-payment-final",
        ),
        "covered_outputs": ("carer_support_payment",),
        "rationale": "Axiom covers the Carer Support Payment care-hours threshold, weekly rate, Scottish Carer Supplement amount, and final annual PolicyEngine UK carer_support_payment wrapper after Scotland, effective-date, and care/reporting gates.",
    },
    "cost_of_living_support_payment": {
        "status": "partial",
        "surfaces": ("cost-of-living-support-payment-parameters",),
        "covered_outputs": ("cost_of_living_support_payment",),
        "rationale": "Axiom covers the statutory means-tested and disability Cost-of-Living Payment amounts, not the qualifying-period, benefit-receipt, tax-credit, pensioner-top-up, fraud, or final household aggregation rules.",
    },
    "winter_fuel_allowance": {
        "status": "partial",
        "surfaces": ("winter-fuel-payment-rates",),
        "covered_outputs": ("winter_fuel_allowance",),
        "rationale": "Axiom covers ordinary Winter Fuel Payment lower and higher annual amounts and the age-80 threshold, not the final household-level entitlement, shared-household branches, residential-care branches, Scotland replacement, or tax recovery mechanics.",
    },
}

UNIVERSAL_CREDIT_REGULATION_36_SURFACES = frozenset(
    surface
    for surface, spec in SURFACE_SPECS.items()
    if spec.program == UNIVERSAL_CREDIT_PROGRAM_PATH
)

SKIPPED_SURFACES: list[dict[str, str]] = []

ENTITY_WEIGHT_COLUMNS = {
    "person": "person_weight",
    "benunit": "benunit_weight",
    "household": "household_weight",
}

ENTITY_ID_COLUMNS = {
    "person": "person_id",
    "benunit": "benunit_id",
    "household": "household_id",
}


@dataclass(frozen=True)
class UKEFRSVariableSource:
    name: str
    entity: str
    domain: str
    path: str
    has_formula: bool
    has_aggregate: bool
    adds: tuple[str, ...] = ()
    subtracts: tuple[str, ...] = ()

    @property
    def computation_kind(self) -> str:
        if self.has_formula and self.has_aggregate:
            return "formula+aggregate"
        if self.has_formula:
            return "formula"
        if self.has_aggregate:
            return "aggregate"
        return "input"


@dataclass(frozen=True)
class UKEFRSVariableMetadata:
    name: str
    entity: str
    domain: str
    path: str
    computed: bool
    computation_kind: str
    covered_output: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity": self.entity,
            "domain": self.domain,
            "path": self.path,
            "computed": self.computed,
            "computation_kind": self.computation_kind,
            "covered_output": self.covered_output,
        }


@dataclass(frozen=True)
class UKEFRSVariableActivity:
    name: str
    entity: str
    nonzero_count: int
    finite_count: int
    nonfinite_count: int
    weighted_abs_total: float
    max_abs_value: float

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity": self.entity,
            "nonzero_count": self.nonzero_count,
            "finite_count": self.finite_count,
            "nonfinite_count": self.nonfinite_count,
            "weighted_abs_total": self.weighted_abs_total,
            "max_abs_value": self.max_abs_value,
        }


@dataclass(frozen=True)
class UKEFRSCoverageReport:
    policyengine_versions: dict[str, str]
    source_root: str | None
    domain_filter: str | None
    entity_filter: str | None
    variables_total: int
    computed_variables_total: int
    computed_variables_by_entity: dict[str, int]
    computed_variables_by_domain: dict[str, int]
    covered_output_variables: list[str]
    projection_support_variables: list[str]
    computed_covered_variables: list[str]
    missing_variables_total: int
    missing_variables: list[UKEFRSVariableMetadata]
    activity: list[UKEFRSVariableActivity]
    activity_errors: list[dict[str, str]]

    def to_json(self) -> dict[str, Any]:
        return {
            "policyengine_versions": self.policyengine_versions,
            "source_root": self.source_root,
            "domain_filter": self.domain_filter,
            "entity_filter": self.entity_filter,
            "variables_total": self.variables_total,
            "computed_variables_total": self.computed_variables_total,
            "computed_variables_by_entity": self.computed_variables_by_entity,
            "computed_variables_by_domain": self.computed_variables_by_domain,
            "covered_output_variables": self.covered_output_variables,
            "projection_support_variables": self.projection_support_variables,
            "computed_covered_count": len(self.computed_covered_variables),
            "computed_covered_variables": self.computed_covered_variables,
            "missing_variables_total": self.missing_variables_total,
            "missing_variables": [item.to_json() for item in self.missing_variables],
            "activity": [item.to_json() for item in self.activity],
            "activity_errors": self.activity_errors,
        }


@dataclass(frozen=True)
class UKEFRSHBAIComponentActivity:
    weighted_total: float
    weighted_abs_total: float
    weighted_mean: float
    weighted_nonzero_share: float

    def to_json(self) -> dict[str, Any]:
        return {
            "weighted_total": self.weighted_total,
            "weighted_abs_total": self.weighted_abs_total,
            "weighted_mean": self.weighted_mean,
            "weighted_nonzero_share": self.weighted_nonzero_share,
        }


@dataclass(frozen=True)
class UKEFRSHBAIComponentCoverage:
    name: str
    direction: str
    status: str
    policy_component: bool
    surfaces: tuple[str, ...]
    covered_outputs: tuple[str, ...]
    rationale: str
    activity: UKEFRSHBAIComponentActivity | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "status": self.status,
            "policy_component": self.policy_component,
            "surfaces": list(self.surfaces),
            "covered_outputs": list(self.covered_outputs),
            "rationale": self.rationale,
            "activity": self.activity.to_json() if self.activity else None,
        }


@dataclass(frozen=True)
class UKEFRSHBAICoverageReport:
    policyengine_versions: dict[str, str]
    source_root: str | None
    year: int
    dataset: str
    adds: tuple[str, ...]
    subtracts: tuple[str, ...]
    components: list[UKEFRSHBAIComponentCoverage]
    activity_errors: list[dict[str, str]]
    hbai_activity: UKEFRSHBAIComponentActivity | None = None

    @property
    def status_counts(self) -> dict[str, int]:
        return dict(
            sorted(Counter(component.status for component in self.components).items())
        )

    @property
    def policy_component_count(self) -> int:
        return sum(1 for component in self.components if component.policy_component)

    @property
    def covered_policy_component_count(self) -> int:
        return sum(
            1
            for component in self.components
            if component.policy_component and component.status in {"exact", "partial"}
        )

    @property
    def exact_policy_component_count(self) -> int:
        return sum(
            1
            for component in self.components
            if component.policy_component and component.status == "exact"
        )

    @property
    def covered_policy_component_share(self) -> float:
        if self.policy_component_count == 0:
            return 0.0
        return self.covered_policy_component_count / self.policy_component_count

    @property
    def exact_policy_component_share(self) -> float:
        if self.policy_component_count == 0:
            return 0.0
        return self.exact_policy_component_count / self.policy_component_count

    @property
    def activity_totals(self) -> dict[str, float] | None:
        components_with_activity = [
            component
            for component in self.components
            if component.policy_component and component.activity is not None
        ]
        if not components_with_activity:
            return None
        total = sum(
            component.activity.weighted_abs_total
            for component in components_with_activity
            if component.activity is not None
        )
        covered = sum(
            component.activity.weighted_abs_total
            for component in components_with_activity
            if component.activity is not None
            and component.status in {"exact", "partial"}
        )
        exact = sum(
            component.activity.weighted_abs_total
            for component in components_with_activity
            if component.activity is not None and component.status == "exact"
        )
        return {
            "policy_weighted_abs_total": total,
            "covered_policy_weighted_abs_total": covered,
            "exact_policy_weighted_abs_total": exact,
            "covered_policy_weighted_abs_share": covered / total if total else 0.0,
            "exact_policy_weighted_abs_share": exact / total if total else 0.0,
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "policyengine_versions": self.policyengine_versions,
            "source_root": self.source_root,
            "year": self.year,
            "dataset": self.dataset,
            "adds": list(self.adds),
            "subtracts": list(self.subtracts),
            "status_counts": self.status_counts,
            "policy_component_count": self.policy_component_count,
            "covered_policy_component_count": self.covered_policy_component_count,
            "exact_policy_component_count": self.exact_policy_component_count,
            "covered_policy_component_share": self.covered_policy_component_share,
            "exact_policy_component_share": self.exact_policy_component_share,
            "activity_totals": self.activity_totals,
            "hbai_activity": self.hbai_activity.to_json()
            if self.hbai_activity
            else None,
            "components": [component.to_json() for component in self.components],
            "activity_errors": self.activity_errors,
        }


@dataclass(frozen=True)
class UKEFRSComparisonRow:
    surface: str
    entity_id: str
    output: str
    axiom: float
    policyengine: float
    diff: float


@dataclass(frozen=True)
class UKEFRSOracleDivergence(UKEFRSComparisonRow):
    reason: str
    issue_url: str


@dataclass(frozen=True)
class UKEFRSComparisonReport:
    compared_persons: int
    compared_benunits: int
    compared_values: int
    mismatches: list[UKEFRSComparisonRow]
    oracle_divergences: list[UKEFRSOracleDivergence]
    output_summary: list[dict[str, Any]]
    skipped_surfaces: list[dict[str, str]]
    projection_notes: list[str]
    dataset_identity: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "compared_persons": self.compared_persons,
            "compared_benunits": self.compared_benunits,
            "compared_values": self.compared_values,
            "mismatch_count": len(self.mismatches),
            "mismatches": [row.__dict__ for row in self.mismatches],
            "oracle_divergence_count": len(self.oracle_divergences),
            "oracle_divergences": [row.__dict__ for row in self.oracle_divergences],
            "output_summary": self.output_summary,
            "skipped_surfaces": self.skipped_surfaces,
            "projection_notes": self.projection_notes,
            "dataset_identity": self.dataset_identity,
        }


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Workspace root containing rulespec-uk and axiom-rules-engine",
    )
    parser.add_argument(
        "--rulespec-root",
        type=Path,
        default=None,
        help="rulespec-uk checkout; defaults to <root>/rulespec-uk",
    )
    parser.add_argument(
        "--axiom-rules-engine-path",
        type=Path,
        default=None,
        help="axiom-rules-engine checkout; defaults to <root>/axiom-rules-engine",
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help=(
            "Number of positive-weight Populace people to compare; "
            "0 compares all eligible people"
        ),
    )
    parser.add_argument(
        "--person-id",
        type=int,
        action="append",
        default=None,
        dest="person_ids",
        help=(
            "Compare a specific Populace person_id. Repeat to compare multiple "
            "known residual cases; when provided this bypasses --sample-size."
        ),
    )
    parser.add_argument(
        "--surface",
        choices=["all", *SURFACE_SPECS],
        default="all",
        help="UK Populace surface to compare; defaults to all implemented surfaces",
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=(
            "Deprecated local .h5 override for debugging. Omit to load the "
            "published Populace UK dataset."
        ),
    )
    parser.add_argument(
        "--data-folder",
        type=Path,
        default=Path(".axiom") / "policyengine-data",
        help="Deprecated; Populace uses the Hugging Face cache.",
    )
    parser.add_argument(
        "--populace-year",
        type=int,
        default=DEFAULT_UK_POPULACE_YEAR,
        help="Published UK Populace dataset year to load.",
    )
    parser.add_argument(
        "--universal-credit-program",
        type=Path,
        default=None,
        help=(
            "Optional RuleSpec program to use for Universal Credit surfaces. "
            "This lets oracle runs compare a composed axiom-programs package "
            "while keeping non-UC UK surfaces on their source RuleSpec files."
        ),
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="Absolute tolerance for matching PolicyEngine outputs",
    )
    parser.add_argument(
        "--relative-tolerance",
        type=float,
        default=2e-7,
        help=(
            "Relative tolerance for large floating PolicyEngine intermediates; "
            "ordinary pound outputs remain controlled by --tolerance"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when any compared value differs beyond tolerance",
    )


def main(args: argparse.Namespace) -> int:
    report = compare_uk_efrs(
        workspace_root=resolve_workspace_root(args.root),
        rulespec_root=args.rulespec_root,
        axiom_rules_path=args.axiom_rules_engine_path,
        year=args.year,
        sample_size=args.sample_size,
        surface=args.surface,
        dataset=args.dataset,
        data_folder=args.data_folder,
        populace_year=args.populace_year,
        tolerance=args.tolerance,
        relative_tolerance=args.relative_tolerance,
        universal_credit_program=getattr(args, "universal_credit_program", None),
        person_ids=tuple(args.person_ids or ()),
    )
    if args.json:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        print_report(
            report,
            tolerance=args.tolerance,
            relative_tolerance=args.relative_tolerance,
        )
    if args.fail_on_mismatch and report.mismatches:
        return 1
    return 0


def configure_coverage_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--domain",
        default=None,
        help=(
            "Restrict computed-variable backlog to a PolicyEngine source domain "
            "such as gov, household, input, contrib, or misc"
        ),
    )
    parser.add_argument(
        "--entity",
        choices=sorted(ENTITY_WEIGHT_COLUMNS),
        default=None,
        help="Restrict computed-variable backlog to one PolicyEngine entity",
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=(
            "Deprecated local .h5 override for --with-populace-activity. "
            "Omit to load the published Populace UK dataset."
        ),
    )
    parser.add_argument(
        "--data-folder",
        type=Path,
        default=Path(".axiom") / "policyengine-data",
        help="Deprecated; Populace uses the Hugging Face cache.",
    )
    parser.add_argument(
        "--populace-year",
        type=int,
        default=DEFAULT_UK_POPULACE_YEAR,
        help="Published UK Populace dataset year to load.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=40,
        help="Maximum missing variables to print in text mode",
    )
    parser.add_argument(
        "--with-populace-activity",
        "--with-efrs-activity",
        action="store_true",
        dest="with_populace_activity",
        help=(
            "Run PolicyEngine over Populace for missing variables and rank by "
            "observed activity"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")


def configure_hbai_coverage_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=(
            "Deprecated local .h5 override for --with-populace-activity. "
            "Omit to load the published Populace UK dataset."
        ),
    )
    parser.add_argument(
        "--data-folder",
        type=Path,
        default=Path(".axiom") / "policyengine-data",
        help="Deprecated; Populace uses the Hugging Face cache.",
    )
    parser.add_argument(
        "--populace-year",
        type=int,
        default=DEFAULT_UK_POPULACE_YEAR,
        help="Published UK Populace dataset year to load.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help=(
            "PolicyEngine UK variables source root; defaults to the installed "
            "policyengine_uk package"
        ),
    )
    parser.add_argument(
        "--top",
        type=int,
        default=40,
        help="Maximum components to print in text mode",
    )
    parser.add_argument(
        "--with-populace-activity",
        "--with-efrs-activity",
        action="store_true",
        dest="with_populace_activity",
        help=(
            "Run PolicyEngine over Populace and add weighted household-level "
            "activity for each HBAI component"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")


def main_coverage(args: argparse.Namespace) -> int:
    report = build_uk_efrs_coverage_report(
        year=args.year,
        dataset=args.dataset,
        data_folder=args.data_folder,
        domain_filter=args.domain,
        entity_filter=args.entity,
        populace_year=args.populace_year,
        include_efrs_activity=args.with_populace_activity,
    )
    if args.json:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        print_uk_efrs_coverage_report(report, top=args.top)
    return 0


def main_hbai_coverage(args: argparse.Namespace) -> int:
    report = build_uk_hbai_policy_coverage_report(
        year=args.year,
        dataset=args.dataset,
        data_folder=args.data_folder,
        populace_year=args.populace_year,
        include_efrs_activity=args.with_populace_activity,
        source_root=args.source_root,
    )
    if args.json:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        print_uk_hbai_policy_coverage_report(report, top=args.top)
    return 0


def compare_uk_efrs(
    *,
    workspace_root: Path,
    rulespec_root: Path | None,
    axiom_rules_path: Path | None,
    year: int,
    sample_size: int,
    surface: str,
    dataset: str,
    data_folder: Path,
    populace_year: int,
    tolerance: float,
    relative_tolerance: float,
    universal_credit_program: Path | None = None,
    person_ids: tuple[int, ...] = (),
) -> UKEFRSComparisonReport:
    resolved_rulespec_root = (rulespec_root or workspace_root / "rulespec-uk").resolve()
    resolved_axiom_rules_path = (
        axiom_rules_path or workspace_root / "axiom-rules-engine"
    ).resolve()
    surfaces = list(SURFACE_SPECS) if surface == "all" else [surface]
    pe_data = load_policyengine_uk_data(
        year=year,
        sample_size=sample_size,
        dataset=dataset,
        data_folder=data_folder,
        populace_year=populace_year,
        person_ids=person_ids,
        person_variables=policyengine_person_variables_for_surfaces(surfaces),
        benunit_variables=policyengine_benunit_variables_for_surfaces(surfaces),
    )
    surface_results: dict[str, list[dict[str, Any]]] = {}
    for selected_surface in surfaces:
        spec = SURFACE_SPECS[selected_surface]
        if (
            selected_surface in UNIVERSAL_CREDIT_REGULATION_36_SURFACES
            and universal_credit_program is not None
        ):
            program = universal_credit_program.resolve()
        else:
            program = resolved_rulespec_root / spec.program
        if not program.exists():
            raise SystemExit(f"{selected_surface} RuleSpec not found: {program}")
        request = build_axiom_request(
            pe_data=pe_data,
            year=year,
            surface=selected_surface,
        )
        surface_results[selected_surface] = run_axiom_surface(
            program=program,
            request=request,
            rulespec_root=resolved_rulespec_root,
            axiom_rules_path=resolved_axiom_rules_path,
            surface=selected_surface,
        )
    return compare_outputs(
        pe_data=pe_data,
        axiom_outputs_by_surface=surface_results,
        tolerance=tolerance,
        relative_tolerance=relative_tolerance,
    )


def disability_category_from_reported_amounts(
    reported_amounts: Any,
    thresholds: tuple[tuple[str, float], ...],
) -> list[str]:
    """Map annual reported disability amounts to PE-UK category inputs."""

    categories: list[str] = []
    for raw_value in reported_amounts:
        try:
            annual_amount = float(raw_value)
        except (TypeError, ValueError):
            annual_amount = 0.0
        if not math.isfinite(annual_amount):
            annual_amount = 0.0
        weekly_amount = annual_amount / WEEKS_IN_YEAR
        category = "NONE"
        for category_name, weekly_rate in thresholds:
            threshold = max(
                0.0,
                float(weekly_rate) - CATEGORY_THRESHOLD_WEEKLY_TOLERANCE,
            )
            if weekly_amount >= threshold:
                category = category_name
        categories.append(category)
    return categories


def policyengine_uk_disability_category_thresholds(
    year: int,
) -> tuple[tuple[str, str, tuple[tuple[str, float], ...]], ...]:
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    dwp = CountryTaxBenefitSystem().parameters(year).baseline.gov.dwp
    return (
        (
            "attendance_allowance_reported",
            "aa_category",
            (
                ("LOWER", dwp.attendance_allowance.lower),
                ("HIGHER", dwp.attendance_allowance.higher),
            ),
        ),
        (
            "dla_sc_reported",
            "dla_sc_category",
            (
                ("LOWER", dwp.dla.self_care.lower),
                ("MIDDLE", dwp.dla.self_care.middle),
                ("HIGHER", dwp.dla.self_care.higher),
            ),
        ),
        (
            "dla_m_reported",
            "dla_m_category",
            (
                ("LOWER", dwp.dla.mobility.lower),
                ("HIGHER", dwp.dla.mobility.higher),
            ),
        ),
        (
            "pip_m_reported",
            "pip_m_category",
            (
                ("STANDARD", dwp.pip.mobility.standard),
                ("ENHANCED", dwp.pip.mobility.enhanced),
            ),
        ),
        (
            "pip_dl_reported",
            "pip_dl_category",
            (
                ("STANDARD", dwp.pip.daily_living.standard),
                ("ENHANCED", dwp.pip.daily_living.enhanced),
            ),
        ),
    )


def add_policyengine_uk_disability_categories_from_reported_amounts(
    dataset: Any,
    *,
    year: int,
) -> tuple[str, ...]:
    """Backfill post-migration disability category inputs for stale local H5s."""

    person = getattr(dataset, "person", None)
    if person is None:
        return ()

    columns = set(person.columns)
    missing_category_mappings = [
        (reported_column, category_column, thresholds)
        for reported_column, category_column, thresholds in (
            policyengine_uk_disability_category_thresholds(year)
        )
        if reported_column in columns and category_column not in columns
    ]
    if not missing_category_mappings:
        return ()

    person = person.copy()
    added_columns: list[str] = []
    for reported_column, category_column, thresholds in missing_category_mappings:
        person[category_column] = disability_category_from_reported_amounts(
            person[reported_column],
            thresholds,
        )
        added_columns.append(category_column)
    dataset.person = person
    return tuple(added_columns)


def load_policyengine_uk_data(
    *,
    year: int,
    sample_size: int,
    dataset: str,
    data_folder: Path,
    populace_year: int,
    person_ids: tuple[int, ...] = (),
    person_variables: tuple[str, ...] = SURFACE_SPECS[
        "personal-allowance"
    ].pe_variables,
    benunit_variables: tuple[str, ...] = (),
) -> dict[str, Any]:
    _ = data_folder
    local_dataset = local_dataset_path(dataset)
    if local_dataset is not None:
        return load_local_policyengine_uk_data(
            local_path=local_dataset,
            year=year,
            sample_size=sample_size,
            person_ids=person_ids,
            person_variables=person_variables,
            benunit_variables=benunit_variables,
        )

    require_policyengine_uk_versions(command="uk-populace-compare")
    dataset_identity: dict[str, Any] = {}
    pe_dataset = load_populace_dataset(
        "uk",
        year=populace_year,
        command="uk-populace-compare",
        provenance=dataset_identity,
    )
    log(f"Loading PolicyEngine Populace UK {populace_year} dataset...")
    pe_data = load_policyengine_uk_dataset(
        pe_dataset=pe_dataset,
        year=year,
        sample_size=sample_size,
        person_ids=person_ids,
        person_variables=person_variables,
        benunit_variables=benunit_variables,
    )
    pe_data["dataset_identity"] = dataset_identity
    return pe_data


def load_local_policyengine_uk_data(
    *,
    local_path: Path,
    year: int,
    sample_size: int,
    person_ids: tuple[int, ...],
    person_variables: tuple[str, ...],
    benunit_variables: tuple[str, ...],
) -> dict[str, Any]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk.data import UKSingleYearDataset
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    log("Loading local PolicyEngine UK dataset...")
    pe_dataset = UKSingleYearDataset(file_path=str(local_path))
    return load_policyengine_uk_dataset(
        pe_dataset=pe_dataset,
        year=year,
        sample_size=sample_size,
        person_ids=person_ids,
        person_variables=person_variables,
        benunit_variables=benunit_variables,
    )


def load_policyengine_uk_dataset(
    *,
    pe_dataset: Any,
    year: int,
    sample_size: int,
    person_ids: tuple[int, ...],
    person_variables: tuple[str, ...],
    benunit_variables: tuple[str, ...],
) -> dict[str, Any]:
    try:
        from policyengine_uk import Microsimulation
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    added_disability_categories = (
        add_policyengine_uk_disability_categories_from_reported_amounts(
            pe_dataset,
            year=year,
        )
    )
    if added_disability_categories:
        log(
            "Derived UK disability category inputs from reported amounts: "
            + ", ".join(added_disability_categories)
        )
    sim = Microsimulation(dataset=pe_dataset)
    data_year = min(sim.dataset.years)

    raw_person = population_table(pe_dataset, "person")
    raw_benunit = population_table(pe_dataset, "benunit")
    household = population_table(pe_dataset, "household")

    person = add_policyengine_uk_person_weights(raw_person, household)
    person_columns = ["person_id", "person_weight"]
    if "person_benunit_id" in person.columns:
        person_columns.append("person_benunit_id")
    merged = person[person_columns].copy()
    log("Running PolicyEngine UK person outputs...")
    for variable in person_variables:
        merged[variable] = sim.calculate(
            variable,
            period=year,
            map_to="person",
        ).values
    if {"state_pension_reported", "state_pension_type"} & set(person_variables):
        merged["state_pension_reported_data_year"] = sim.calculate(
            "state_pension_reported",
            period=data_year,
            map_to="person",
        ).values
        merged["state_pension_type_data_year"] = sim.calculate(
            "state_pension_type",
            period=data_year,
            map_to="person",
        ).values
    records = table_records(merged)
    selected_indices = select_person_indices(
        records,
        sample_size=sample_size,
        person_ids=person_ids,
    )
    selected = [records[index] for index in selected_indices]
    selected_benunits: list[dict[str, Any]] = []
    if benunit_variables:
        benunit = add_policyengine_uk_benunit_weights(
            raw_benunit,
            raw_person,
            household,
        )
        merged_benunits = benunit[["benunit_id", "benunit_weight"]].copy()
        log("Running PolicyEngine UK benefit-unit outputs...")
        for variable in benunit_variables:
            merged_benunits[variable] = sim.calculate(
                variable,
                period=year,
                map_to="benunit",
            ).values
        merged_benunits = add_universal_credit_childcare_work_projection_columns(
            merged_benunits,
            merged,
        )
        merged_benunits = add_esa_income_reported_projection_columns(
            merged_benunits,
            merged,
        )
        merged_benunits = add_housing_benefit_age_projection_columns(
            merged_benunits,
            merged,
        )
        merged_benunits = add_pension_credit_child_addition_projection_columns(
            merged_benunits,
            merged,
        )
        benunit_records = table_records(merged_benunits)
        selected_benunit_ids = ()
        if person_ids:
            selected_benunit_ids = tuple(
                dict.fromkeys(
                    int(row_value(row, "person_benunit_id"))
                    for row in selected
                    if row_value(row, "person_benunit_id") is not None
                )
            )
        selected_benunit_indices = select_benunit_indices(
            benunit_records,
            sample_size=sample_size,
            benunit_ids=selected_benunit_ids,
        )
        selected_benunits = [
            benunit_records[index] for index in selected_benunit_indices
        ]
    return {
        "data_year": data_year,
        "all_persons": records,
        "persons": selected,
        "person_ids": [int(row_value(row, "person_id")) for row in selected],
        "benunits": selected_benunits,
        "benunit_ids": [int(row_value(row, "benunit_id")) for row in selected_benunits],
    }


def add_policyengine_uk_person_weights(raw_person: Any, household: Any) -> Any:
    person = raw_person.merge(
        household[["household_id", "household_weight"]],
        left_on="person_household_id",
        right_on="household_id",
        how="left",
    )
    return person.rename(columns={"household_weight": "person_weight"}).drop(
        columns=["household_id"],
    )


def add_policyengine_uk_benunit_weights(
    raw_benunit: Any,
    raw_person: Any,
    household: Any,
) -> Any:
    benunit_household_map = raw_person[
        ["person_benunit_id", "person_household_id"]
    ].drop_duplicates()
    benunit = raw_benunit.merge(
        benunit_household_map,
        left_on="benunit_id",
        right_on="person_benunit_id",
        how="left",
    )
    benunit = benunit.merge(
        household[["household_id", "household_weight"]],
        left_on="person_household_id",
        right_on="household_id",
        how="left",
    )
    return benunit.rename(columns={"household_weight": "benunit_weight"}).drop(
        columns=[
            "person_benunit_id",
            "person_household_id",
            "household_id",
        ],
        errors="ignore",
    )


def add_universal_credit_childcare_work_projection_columns(
    benunit: Any,
    person: Any,
) -> Any:
    required = {"person_benunit_id", "is_adult", "in_work"}
    if not required.issubset(set(person.columns)):
        return benunit
    projection = person[["person_benunit_id"]].copy()
    is_adult = person["is_adult"].astype(bool)
    in_work = person["in_work"].astype(bool)
    projection["uc_childcare_adult_count"] = is_adult.astype(int)
    projection["uc_childcare_adult_in_work_count"] = (is_adult & in_work).astype(int)
    projection["uc_childcare_adult_not_in_work_count"] = (is_adult & ~in_work).astype(
        int
    )
    by_benunit = projection.groupby("person_benunit_id", dropna=False).sum()
    by_benunit["uc_childcare_any_adult_in_work"] = (
        by_benunit["uc_childcare_adult_in_work_count"] > 0
    )
    by_benunit["uc_childcare_all_adults_in_work"] = (
        by_benunit["uc_childcare_adult_not_in_work_count"] == 0
    )
    by_benunit = by_benunit[
        [
            "uc_childcare_adult_count",
            "uc_childcare_any_adult_in_work",
            "uc_childcare_all_adults_in_work",
        ]
    ].reset_index()
    merged = benunit.merge(
        by_benunit,
        left_on="benunit_id",
        right_on="person_benunit_id",
        how="left",
    ).drop(columns=["person_benunit_id"], errors="ignore")
    merged["uc_childcare_adult_count"] = merged["uc_childcare_adult_count"].fillna(0)
    merged["uc_childcare_any_adult_in_work"] = merged[
        "uc_childcare_any_adult_in_work"
    ].fillna(False)
    merged["uc_childcare_all_adults_in_work"] = merged[
        "uc_childcare_all_adults_in_work"
    ].fillna(True)
    return merged


def add_housing_benefit_age_projection_columns(
    benunit: Any,
    person: Any,
) -> Any:
    required = {"person_benunit_id", "is_SP_age"}
    if not required.issubset(set(person.columns)):
        return benunit
    projection = person[["person_benunit_id"]].copy()
    projection["housing_benefit_sp_age_count"] = person["is_SP_age"].astype(int)
    by_benunit = projection.groupby("person_benunit_id", dropna=False).sum()
    by_benunit["housing_benefit_any_over_sp_age"] = (
        by_benunit["housing_benefit_sp_age_count"] > 0
    )
    by_benunit = by_benunit[["housing_benefit_any_over_sp_age"]].reset_index()
    merged = benunit.merge(
        by_benunit,
        left_on="benunit_id",
        right_on="person_benunit_id",
        how="left",
    ).drop(columns=["person_benunit_id"], errors="ignore")
    merged["housing_benefit_any_over_sp_age"] = merged[
        "housing_benefit_any_over_sp_age"
    ].fillna(False)
    return merged


def add_esa_income_reported_projection_columns(
    benunit: Any,
    person: Any,
) -> Any:
    required = {"person_benunit_id", "esa_income_reported"}
    if not required.issubset(set(person.columns)):
        return benunit
    projection = person[["person_benunit_id"]].copy()
    projection["esa_income_reported_for_year"] = (
        person["esa_income_reported"].fillna(0).astype(float)
    )
    by_benunit = projection.groupby("person_benunit_id", dropna=False).sum()
    by_benunit = by_benunit[["esa_income_reported_for_year"]].reset_index()
    merged = benunit.merge(
        by_benunit,
        left_on="benunit_id",
        right_on="person_benunit_id",
        how="left",
    ).drop(columns=["person_benunit_id"], errors="ignore")
    merged["esa_income_reported_for_year"] = merged[
        "esa_income_reported_for_year"
    ].fillna(0)
    return merged


def add_pension_credit_child_addition_projection_columns(
    benunit: Any,
    person: Any,
) -> Any:
    required = {
        "person_benunit_id",
        "birth_year",
        "dla",
        "is_child_or_qualifying_young_person_for_pension_credit",
        "pip",
        "receives_enhanced_pip_dl",
        "receives_highest_dla_sc",
    }
    if not required.issubset(set(person.columns)):
        return benunit
    projection = person[["person_benunit_id"]].copy()
    is_child = (
        person["is_child_or_qualifying_young_person_for_pension_credit"]
        .fillna(False)
        .astype(bool)
    )
    standard_disability = (
        person["dla"].fillna(0).astype(float) + person["pip"].fillna(0).astype(float)
    ) > 0
    severe_disability = person["receives_highest_dla_sc"].fillna(False).astype(
        bool
    ) | person["receives_enhanced_pip_dl"].fillna(False).astype(bool)
    birth_year = person["birth_year"].fillna(9999).astype(float)
    projection["pc_child_addition_child_count"] = is_child.astype(int)
    projection["pc_child_addition_standard_disabled_child_count"] = (
        is_child & standard_disability & ~severe_disability
    ).astype(int)
    projection["pc_child_addition_severely_disabled_child_count"] = (
        is_child & severe_disability
    ).astype(int)
    projection["pc_child_addition_any_pre_2017_child"] = (
        is_child & (birth_year < 2017)
    ).astype(int)
    by_benunit = projection.groupby("person_benunit_id", dropna=False).sum()
    by_benunit["pc_child_addition_any_pre_2017_child"] = (
        by_benunit["pc_child_addition_any_pre_2017_child"] > 0
    )
    output_columns = [
        "pc_child_addition_child_count",
        "pc_child_addition_standard_disabled_child_count",
        "pc_child_addition_severely_disabled_child_count",
        "pc_child_addition_any_pre_2017_child",
    ]
    by_benunit = by_benunit[output_columns].reset_index()
    merged = benunit.merge(
        by_benunit,
        left_on="benunit_id",
        right_on="person_benunit_id",
        how="left",
    ).drop(columns=["person_benunit_id"], errors="ignore")
    for column in output_columns:
        if column == "pc_child_addition_any_pre_2017_child":
            merged[column] = merged[column].fillna(False)
        else:
            merged[column] = merged[column].fillna(0).astype(int)
    return merged


def resolve_policyengine_uk_dataset_reference(dataset: str) -> str:
    if "://" in dataset:
        return dataset
    try:
        from policyengine.provenance.manifest import resolve_dataset_reference
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc
    return resolve_dataset_reference("uk", dataset)


def local_policyengine_uk_dataset(
    *,
    dataset: str,
    year: int,
) -> Any | None:
    local_path = local_policyengine_uk_dataset_path(dataset)
    if local_path is None:
        return None
    try:
        import pandas as pd
        from microdf import MicroDataFrame
        from policyengine.tax_benefit_models.uk.datasets import (
            PolicyEngineUKDataset,
            UKYearData,
        )
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    with pd.HDFStore(local_path, mode="r") as store:
        raw_person = store["person"].copy()
        raw_benunit = store["benunit"].copy()
        household = store["household"].copy()

    person = raw_person.merge(
        household[["household_id", "household_weight"]],
        left_on="person_household_id",
        right_on="household_id",
        how="left",
    )
    person = person.rename(columns={"household_weight": "person_weight"}).drop(
        columns=["household_id"]
    )
    benunit_household_map = person[
        ["person_benunit_id", "person_household_id"]
    ].drop_duplicates()
    benunit = raw_benunit.merge(
        benunit_household_map,
        left_on="benunit_id",
        right_on="person_benunit_id",
        how="left",
    )
    benunit = benunit.merge(
        household[["household_id", "household_weight"]],
        left_on="person_household_id",
        right_on="household_id",
        how="left",
    )
    benunit = benunit.rename(columns={"household_weight": "benunit_weight"}).drop(
        columns=[
            "person_benunit_id",
            "person_household_id",
            "household_id",
        ],
        errors="ignore",
    )

    dataset_id = Path(local_path).stem
    return PolicyEngineUKDataset(
        id=f"{dataset_id}_local_{year}",
        name=f"{dataset_id}-local-{year}",
        description=f"Local UK Dataset for year {year} based on {dataset_id}",
        filepath=str(Path(".axiom") / "policyengine-data" / f"{dataset_id}_{year}.h5"),
        year=int(year),
        data=UKYearData(
            person=MicroDataFrame(person, weights="person_weight"),
            benunit=MicroDataFrame(benunit, weights="benunit_weight"),
            household=MicroDataFrame(household, weights="household_weight"),
        ),
    )


def local_policyengine_uk_dataset_path(dataset: str) -> Path | None:
    direct_path = Path(dataset).expanduser()
    if direct_path.exists():
        return direct_path.resolve()
    try:
        from policyengine.provenance.manifest import (
            resolve_dataset_reference,
            resolve_local_managed_dataset_source,
        )
    except ImportError:
        return None

    resolved_dataset = dataset
    if "://" not in dataset:
        try:
            resolved_dataset = resolve_dataset_reference("uk", dataset)
        except ValueError:
            return None
    local_source = resolve_local_managed_dataset_source("uk", resolved_dataset)
    local_path = Path(local_source).expanduser()
    if local_path.exists():
        return local_path.resolve()
    return None


def policyengine_person_variables_for_surfaces(
    surfaces: list[str],
) -> tuple[str, ...]:
    return policyengine_variables_for_surfaces(surfaces, entity="person")


def policyengine_benunit_variables_for_surfaces(
    surfaces: list[str],
) -> tuple[str, ...]:
    return policyengine_variables_for_surfaces(surfaces, entity="benunit")


def policyengine_variables_for_surfaces(
    surfaces: list[str],
    *,
    entity: str,
) -> tuple[str, ...]:
    variables: set[str] = set()
    for surface in surfaces:
        spec = SURFACE_SPECS[surface]
        if spec.entity == entity:
            variables.update(spec.pe_variables)
        if entity == "person":
            variables.update(spec.projection_person_variables)
    return tuple(sorted(variables))


def build_uk_efrs_coverage_report(
    *,
    year: int = 2026,
    dataset: str = DEFAULT_DATASET,
    data_folder: Path = Path(".axiom") / "policyengine-data",
    populace_year: int = DEFAULT_UK_POPULACE_YEAR,
    domain_filter: str | None = None,
    entity_filter: str | None = None,
    include_efrs_activity: bool = False,
    policyengine_variables: list[Any] | None = None,
    source_root: Path | None = None,
) -> UKEFRSCoverageReport:
    versions = policyengine_uk_versions()
    variables = discover_policyengine_uk_variables(
        policyengine_variables=policyengine_variables,
        source_root=source_root,
    )
    scoped_variables = [
        variable
        for variable in variables
        if (domain_filter is None or variable.domain == domain_filter)
        and (entity_filter is None or variable.entity == entity_filter)
    ]
    computed_variables = [
        variable for variable in scoped_variables if variable.computed
    ]
    covered_outputs = covered_uk_policyengine_output_variables()
    support_variables = uk_policyengine_projection_support_variables()
    computed_covered = sorted(
        variable.name
        for variable in computed_variables
        if variable.name in set(covered_outputs)
    )
    missing_variables = [
        variable
        for variable in computed_variables
        if variable.name not in set(covered_outputs)
    ]
    activity: list[UKEFRSVariableActivity] = []
    activity_errors: list[dict[str, str]] = []
    if include_efrs_activity and missing_variables:
        activity, activity_errors = policyengine_uk_efrs_activity(
            missing_variables,
            year=year,
            dataset=dataset,
            data_folder=data_folder,
            populace_year=populace_year,
        )

    source_root_label = None
    if source_root is not None:
        source_root_label = str(source_root.resolve())
    else:
        resolved_source_root = policyengine_uk_variables_source_root(required=False)
        if resolved_source_root is not None:
            source_root_label = str(resolved_source_root)

    return UKEFRSCoverageReport(
        policyengine_versions=versions,
        source_root=source_root_label,
        domain_filter=domain_filter,
        entity_filter=entity_filter,
        variables_total=len(scoped_variables),
        computed_variables_total=len(computed_variables),
        computed_variables_by_entity=dict(
            sorted(Counter(variable.entity for variable in computed_variables).items())
        ),
        computed_variables_by_domain=dict(
            sorted(Counter(variable.domain for variable in computed_variables).items())
        ),
        covered_output_variables=covered_outputs,
        projection_support_variables=support_variables,
        computed_covered_variables=computed_covered,
        missing_variables_total=len(missing_variables),
        missing_variables=sorted(
            missing_variables,
            key=lambda variable: (
                variable.domain,
                variable.entity,
                variable.path,
                variable.name,
            ),
        ),
        activity=sorted(
            activity,
            key=lambda item: (
                item.nonzero_count > 0,
                item.weighted_abs_total,
                item.nonzero_count,
            ),
            reverse=True,
        ),
        activity_errors=activity_errors,
    )


def build_uk_hbai_policy_coverage_report(
    *,
    year: int = 2026,
    dataset: str = DEFAULT_DATASET,
    data_folder: Path = Path(".axiom") / "policyengine-data",
    populace_year: int = DEFAULT_UK_POPULACE_YEAR,
    include_efrs_activity: bool = False,
    source_root: Path | None = None,
) -> UKEFRSHBAICoverageReport:
    versions = policyengine_uk_versions()
    resolved_source_root = source_root or policyengine_uk_variables_source_root()
    source_index = parse_policyengine_uk_variable_sources(resolved_source_root)
    hbai_source = source_index.get("hbai_household_net_income")
    if hbai_source is None:
        raise SystemExit(
            "PolicyEngine UK hbai_household_net_income source not found under "
            f"{resolved_source_root}"
        )
    if not hbai_source.adds and not hbai_source.subtracts:
        raise SystemExit(
            "PolicyEngine UK hbai_household_net_income source does not declare "
            "adds/subtracts components"
        )

    component_activity: dict[str, UKEFRSHBAIComponentActivity] = {}
    hbai_activity = None
    activity_errors: list[dict[str, str]] = []
    if include_efrs_activity:
        component_activity, hbai_activity, activity_errors = (
            policyengine_uk_hbai_activity(
                components=tuple(
                    dict.fromkeys([*hbai_source.adds, *hbai_source.subtracts])
                ),
                year=year,
                dataset=dataset,
                data_folder=data_folder,
                populace_year=populace_year,
            )
        )

    components: list[UKEFRSHBAIComponentCoverage] = []
    for direction, names in (
        ("add", hbai_source.adds),
        ("subtract", hbai_source.subtracts),
    ):
        for name in names:
            components.append(
                classify_hbai_component(
                    name=name,
                    direction=direction,
                    activity=component_activity.get(name),
                )
            )

    return UKEFRSHBAICoverageReport(
        policyengine_versions=versions,
        source_root=str(resolved_source_root.resolve()),
        year=year,
        dataset=dataset,
        adds=hbai_source.adds,
        subtracts=hbai_source.subtracts,
        components=components,
        hbai_activity=hbai_activity,
        activity_errors=activity_errors,
    )


def classify_hbai_component(
    *,
    name: str,
    direction: str,
    activity: UKEFRSHBAIComponentActivity | None = None,
) -> UKEFRSHBAIComponentCoverage:
    if name in HBAI_FIXED_INPUT_COMPONENTS:
        return UKEFRSHBAIComponentCoverage(
            name=name,
            direction=direction,
            status="fixed_input",
            policy_component=False,
            surfaces=(),
            covered_outputs=(),
            rationale=(
                "Private, market, reported, or PolicyEngine input-only component "
                "held fixed when measuring policy alignment."
            ),
            activity=activity,
        )
    if name in HBAI_OUT_OF_SCOPE_COMPONENTS:
        return UKEFRSHBAIComponentCoverage(
            name=name,
            direction=direction,
            status="out_of_scope",
            policy_component=False,
            surfaces=(),
            covered_outputs=(),
            rationale=HBAI_OUT_OF_SCOPE_COMPONENTS[name],
            activity=activity,
        )
    coverage = HBAI_COMPONENT_COVERAGE.get(name)
    if coverage is not None:
        return UKEFRSHBAIComponentCoverage(
            name=name,
            direction=direction,
            status=str(coverage["status"]),
            policy_component=True,
            surfaces=tuple(str(item) for item in coverage["surfaces"]),
            covered_outputs=tuple(str(item) for item in coverage["covered_outputs"]),
            rationale=str(coverage["rationale"]),
            activity=activity,
        )
    return UKEFRSHBAIComponentCoverage(
        name=name,
        direction=direction,
        status="missing",
        policy_component=True,
        surfaces=(),
        covered_outputs=(),
        rationale="No current Axiom UK RuleSpec surface is classified as covering this HBAI policy component.",
        activity=activity,
    )


def policyengine_uk_hbai_activity(
    *,
    components: tuple[str, ...],
    year: int,
    dataset: str,
    data_folder: Path,
    populace_year: int,
) -> tuple[
    dict[str, UKEFRSHBAIComponentActivity],
    UKEFRSHBAIComponentActivity | None,
    list[dict[str, str]],
]:
    _ = data_folder
    require_policyengine_uk_versions(command="uk-populace-hbai-coverage")
    try:
        from policyengine_uk import Microsimulation
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(
            policyengine_uk_install_message("uk-populace-hbai-coverage")
        ) from exc

    local_dataset = local_dataset_path(dataset)
    if local_dataset is not None:
        from policyengine_uk.data import UKSingleYearDataset

        log("Loading local PolicyEngine UK dataset for HBAI activity...")
        pe_dataset = UKSingleYearDataset(file_path=str(local_dataset))
    else:
        log("Loading PolicyEngine UK Populace for HBAI activity...")
        pe_dataset = load_populace_dataset(
            "uk",
            year=populace_year,
            command="uk-populace-hbai-coverage",
        )
    added_disability_categories = (
        add_policyengine_uk_disability_categories_from_reported_amounts(
            pe_dataset,
            year=year,
        )
    )
    if added_disability_categories:
        log(
            "Derived UK disability category inputs from reported amounts: "
            + ", ".join(added_disability_categories)
        )
    sim = Microsimulation(dataset=pe_dataset)

    activity: dict[str, UKEFRSHBAIComponentActivity] = {}
    errors: list[dict[str, str]] = []
    for name in components:
        try:
            activity[name] = microseries_activity(
                sim.calculate(name, period=year, map_to="household")
            )
        except Exception as exc:  # pragma: no cover - depends on PE variable graph
            errors.append({"variable": name, "error": str(exc)})

    hbai_activity = None
    try:
        hbai_activity = microseries_activity(
            sim.calculate(
                "hbai_household_net_income",
                period=year,
                map_to="household",
            )
        )
    except Exception as exc:  # pragma: no cover - depends on PE variable graph
        errors.append({"variable": "hbai_household_net_income", "error": str(exc)})

    return activity, hbai_activity, errors


def microseries_activity(series: Any) -> UKEFRSHBAIComponentActivity:
    abs_series = abs(series)
    return UKEFRSHBAIComponentActivity(
        weighted_total=float(series.sum()),
        weighted_abs_total=float(abs_series.sum()),
        weighted_mean=float(series.mean()),
        weighted_nonzero_share=float((abs_series > 1e-9).mean()),
    )


def discover_policyengine_uk_variables(
    *,
    policyengine_variables: list[Any] | None = None,
    source_root: Path | None = None,
) -> list[UKEFRSVariableMetadata]:
    raw_variables = (
        policyengine_variables
        if policyengine_variables is not None
        else load_policyengine_uk_variables()
    )
    resolved_source_root = source_root or policyengine_uk_variables_source_root()
    source_index = parse_policyengine_uk_variable_sources(resolved_source_root)
    covered_outputs = set(covered_uk_policyengine_output_variables())
    metadata: list[UKEFRSVariableMetadata] = []
    for raw_variable in raw_variables:
        name = str(variable_attribute(raw_variable, "name"))
        source = source_index.get(name)
        entity = normalize_policyengine_entity(
            variable_attribute(raw_variable, "entity", source.entity if source else "")
        )
        has_aggregate = bool(variable_attribute(raw_variable, "adds", None)) or bool(
            variable_attribute(raw_variable, "subtracts", None)
        )
        if source is not None:
            has_aggregate = has_aggregate or source.has_aggregate
            has_formula = source.has_formula
            domain = source.domain
            path = source.path
            computation_kind = source.computation_kind
        else:
            has_formula = False
            domain = "unknown"
            path = ""
            computation_kind = "aggregate" if has_aggregate else "input"
        computed = has_formula or has_aggregate
        metadata.append(
            UKEFRSVariableMetadata(
                name=name,
                entity=entity,
                domain=domain,
                path=path,
                computed=computed,
                computation_kind=computation_kind if computed else "input",
                covered_output=name in covered_outputs,
            )
        )
    return sorted(metadata, key=lambda variable: variable.name)


def load_policyengine_uk_variables() -> list[Any]:
    require_policyengine_uk_versions(command="uk-populace-coverage")
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(
            policyengine_uk_install_message("uk-populace-coverage")
        ) from exc
    return list(CountryTaxBenefitSystem().variables.values())


def parse_policyengine_uk_variable_sources(
    source_root: Path,
) -> dict[str, UKEFRSVariableSource]:
    sources: dict[str, UKEFRSVariableSource] = {}
    for source_file in sorted(source_root.rglob("*.py")):
        if source_file.name == "__init__.py":
            continue
        relative_path = source_file.relative_to(source_root)
        domain = relative_path.parts[0] if relative_path.parts else "unknown"
        try:
            tree = ast.parse(source_file.read_text())
        except SyntaxError:
            continue
        module_string_sequences = module_level_string_sequences(tree)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not class_extends_variable(node):
                continue
            entity = ""
            has_aggregate = False
            adds: tuple[str, ...] = ()
            subtracts: tuple[str, ...] = ()
            has_formula = any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name.startswith("formula")
                for item in node.body
            )
            for item in node.body:
                targets: list[ast.expr] = []
                value: ast.expr | None = None
                if isinstance(item, ast.Assign):
                    targets = list(item.targets)
                    value = item.value
                elif isinstance(item, ast.AnnAssign):
                    targets = [item.target]
                    value = item.value
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if target.id == "entity" and value is not None:
                        entity = normalize_policyengine_entity(ast_value_name(value))
                    if target.id in {"adds", "subtracts"}:
                        has_aggregate = True
                        components = ast_string_sequence(
                            value,
                            module_string_sequences,
                        )
                        if target.id == "adds":
                            adds = components
                        else:
                            subtracts = components
            if node.name == "hbai_household_net_income" and (not adds or not subtracts):
                formula_adds, formula_subtracts = formula_add_subtract_components(
                    node,
                    module_string_sequences,
                )
                adds = adds or formula_adds
                subtracts = subtracts or formula_subtracts
                if adds or subtracts:
                    has_aggregate = True
            sources[node.name] = UKEFRSVariableSource(
                name=node.name,
                entity=entity,
                domain=domain,
                path=relative_path.as_posix(),
                has_formula=has_formula,
                has_aggregate=has_aggregate,
                adds=adds,
                subtracts=subtracts,
            )
    return sources


def module_level_string_sequences(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    sequences: dict[str, tuple[str, ...]] = {}
    for item in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(item, ast.Assign):
            targets = list(item.targets)
            value = item.value
        elif isinstance(item, ast.AnnAssign):
            targets = [item.target]
            value = item.value
        if value is None:
            continue
        components = ast_string_sequence(value)
        if not components:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                sequences[target.id] = components
    return sequences


def formula_add_subtract_components(
    node: ast.ClassDef,
    module_string_sequences: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    adds: list[str] = []
    subtracts: list[str] = []
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not item.name.startswith("formula"):
            continue
        for child in ast.walk(item):
            if not isinstance(child, ast.Call):
                continue
            if ast_value_name(child.func) != "add":
                continue
            if len(child.args) < 3:
                continue
            components = ast_string_sequence(child.args[2], module_string_sequences)
            if not components:
                continue
            source_name = ast_value_name(child.args[2]).upper()
            if "SUBTRACT" in source_name:
                subtracts.extend(components)
            elif "ADD" in source_name:
                adds.extend(components)
    return tuple(dict.fromkeys(adds)), tuple(dict.fromkeys(subtracts))


def class_extends_variable(node: ast.ClassDef) -> bool:
    return any(ast_value_name(base) == "Variable" for base in node.bases)


def ast_value_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Subscript):
        return ast_value_name(node.value)
    return ""


def ast_string_sequence(
    node: ast.AST | None,
    named_sequences: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, ...]:
    if isinstance(node, ast.Name) and named_sequences is not None:
        return named_sequences.get(node.id, ())
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for item in node.elts:
            value = ast_value_name(item)
            if value:
                values.append(value)
        return tuple(values)
    return ()


def variable_attribute(raw_variable: Any, name: str, default: Any = None) -> Any:
    if isinstance(raw_variable, dict):
        return raw_variable.get(name, default)
    return getattr(raw_variable, name, default)


def normalize_policyengine_entity(value: Any) -> str:
    if hasattr(value, "key"):
        return str(value.key).strip().lower()
    text = str(value or "").strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    normalized = {
        "Person": "person",
        "BenUnit": "benunit",
        "BenefitUnit": "benunit",
        "Household": "household",
    }.get(text, text)
    return normalized.lower()


def covered_uk_policyengine_output_variables() -> list[str]:
    return sorted(
        {
            str(output["pe"])
            for spec in SURFACE_SPECS.values()
            for output in spec.outputs.values()
            if output.get("pe")
        }
    )


def uk_policyengine_projection_support_variables() -> list[str]:
    covered_outputs = set(covered_uk_policyengine_output_variables())
    return sorted(
        {
            variable
            for spec in SURFACE_SPECS.values()
            for variable in spec.pe_variables
            if variable not in covered_outputs
        }
    )


def policyengine_uk_variables_source_root(*, required: bool = True) -> Path | None:
    try:
        import policyengine_uk
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        if required:
            raise SystemExit(
                policyengine_uk_install_message("uk-populace-coverage")
            ) from exc
        return None
    source_root = Path(policyengine_uk.__file__).resolve().parent / "variables"
    if not source_root.exists():
        if required:
            raise SystemExit(
                f"PolicyEngine UK variable source root not found: {source_root}"
            )
        return None
    return source_root


def policyengine_uk_versions() -> dict[str, str]:
    packages = ("policyengine", "policyengine-core", "policyengine-uk")
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    return versions


def policyengine_uk_efrs_activity(
    variables: list[UKEFRSVariableMetadata],
    *,
    year: int,
    dataset: str,
    data_folder: Path,
    populace_year: int,
) -> tuple[list[UKEFRSVariableActivity], list[dict[str, str]]]:
    _ = data_folder
    require_policyengine_uk_versions(command="uk-populace-coverage")
    try:
        import numpy as np
        import pandas as pd
        from policyengine_uk import Microsimulation
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(
            policyengine_uk_install_message("uk-populace-coverage")
        ) from exc

    local_dataset = local_dataset_path(dataset)
    if local_dataset is not None:
        from policyengine_uk.data import UKSingleYearDataset

        log("Loading local PolicyEngine UK dataset for coverage activity...")
        pe_dataset = UKSingleYearDataset(file_path=str(local_dataset))
    else:
        log("Loading PolicyEngine UK Populace for coverage activity...")
        pe_dataset = load_populace_dataset(
            "uk",
            year=populace_year,
            command="uk-populace-coverage",
        )
    added_disability_categories = (
        add_policyengine_uk_disability_categories_from_reported_amounts(
            pe_dataset,
            year=year,
        )
    )
    if added_disability_categories:
        log(
            "Derived UK disability category inputs from reported amounts: "
            + ", ".join(added_disability_categories)
        )
    sim = Microsimulation(dataset=pe_dataset)
    raw_person = population_table(pe_dataset, "person")
    raw_benunit = population_table(pe_dataset, "benunit")
    household = population_table(pe_dataset, "household")
    raw_tables = {
        "person": add_policyengine_uk_person_weights(raw_person, household),
        "benunit": add_policyengine_uk_benunit_weights(
            raw_benunit,
            raw_person,
            household,
        ),
        "household": household,
    }

    extra_variables: dict[str, list[str]] = defaultdict(list)
    variables_by_name = {variable.name: variable for variable in variables}
    for variable in variables:
        if variable.entity in ENTITY_WEIGHT_COLUMNS:
            extra_variables[variable.entity].append(variable.name)

    log("Running PolicyEngine UK outputs for coverage activity...")

    activity: list[UKEFRSVariableActivity] = []
    errors: list[dict[str, str]] = []
    for entity, names in sorted(extra_variables.items()):
        raw_table = raw_tables[entity]
        weight_column = ENTITY_WEIGHT_COLUMNS[entity]
        id_column = ENTITY_ID_COLUMNS[entity]
        if weight_column not in raw_table.columns:
            errors.append(
                {
                    "entity": entity,
                    "variable": "*",
                    "error": f"missing weight column {weight_column}",
                }
            )
            continue
        if id_column not in raw_table.columns:
            errors.append(
                {
                    "entity": entity,
                    "variable": "*",
                    "error": f"missing id column {id_column}",
                }
            )
            continue
        output_table = raw_table[[id_column]].copy()
        for name in sorted(names):
            try:
                output_table[name] = sim.calculate(
                    name,
                    period=year,
                    map_to=entity,
                ).values
            except Exception as exc:  # pragma: no cover - depends on PE variable graph
                errors.append(
                    {
                        "entity": entity,
                        "variable": name,
                        "error": str(exc),
                    }
                )
        raw_weights = raw_table[[id_column, weight_column]].copy()
        output_ids = output_table[[id_column]].copy()
        aligned_weights = output_ids.merge(
            raw_weights,
            on=id_column,
            how="left",
            validate="one_to_one",
        )
        weights = pd.Series(
            pd.to_numeric(aligned_weights[weight_column], errors="coerce")
        )
        weight_values = weights.to_numpy(dtype=float, na_value=np.nan)
        weight_values = np.where(np.isfinite(weight_values), weight_values, 0.0)
        for name in sorted(names):
            if name not in output_table.columns:
                errors.append(
                    {
                        "entity": entity,
                        "variable": name,
                        "error": "missing PolicyEngine output column",
                    }
                )
                continue
            raw_values = pd.Series(pd.to_numeric(output_table[name], errors="coerce"))
            values = raw_values.to_numpy(dtype=float, na_value=np.nan)
            finite = np.isfinite(values)
            nonzero = finite & (np.abs(values) > 1e-9)
            weighted_abs_total = float(
                np.sum(np.abs(values[finite]) * weight_values[finite])
            )
            max_abs_value = float(np.max(np.abs(values[finite]))) if finite.any() else 0
            variable = variables_by_name[name]
            activity.append(
                UKEFRSVariableActivity(
                    name=variable.name,
                    entity=variable.entity,
                    nonzero_count=int(np.sum(nonzero)),
                    finite_count=int(np.sum(finite)),
                    nonfinite_count=int(len(values) - np.sum(finite)),
                    weighted_abs_total=weighted_abs_total,
                    max_abs_value=max_abs_value,
                )
            )
    return activity, errors


def print_uk_efrs_coverage_report(
    report: UKEFRSCoverageReport,
    *,
    top: int,
) -> None:
    print("PolicyEngine UK Populace coverage")
    print(
        "PolicyEngine versions: "
        + ", ".join(
            f"{package}=={version}"
            for package, version in report.policyengine_versions.items()
        )
    )
    if report.source_root:
        print(f"Variable source root: {report.source_root}")
    if report.domain_filter or report.entity_filter:
        print(
            "Scope: "
            f"domain={report.domain_filter or 'all'}, "
            f"entity={report.entity_filter or 'all'}"
        )
    print(f"Variables in scope: {report.variables_total:,}")
    print(f"Computed/aggregate variables in scope: {report.computed_variables_total:,}")
    print(
        "Direct Axiom-covered PE outputs in scope: "
        f"{len(report.computed_covered_variables):,}"
    )
    print(f"Missing computed PE outputs in scope: {report.missing_variables_total:,}")
    print()
    print("Computed variables by entity:")
    for entity, count in report.computed_variables_by_entity.items():
        print(f"  - {entity}: {count:,}")
    print("Computed variables by source domain:")
    for domain, count in report.computed_variables_by_domain.items():
        print(f"  - {domain}: {count:,}")
    print()
    print("Currently direct-covered PE output variables:")
    for name in report.covered_output_variables:
        marker = "*" if name in report.computed_covered_variables else "-"
        print(f"  {marker} {name}")
    if report.projection_support_variables:
        print()
        print("PE variables used only to project current RuleSpec inputs:")
        for name in report.projection_support_variables:
            print(f"  - {name}")
    if report.activity:
        print()
        print(f"Top missing Populace-active PE variables (first {top:,}):")
        activity_by_name = {item.name: item for item in report.activity}
        missing_by_name = {item.name: item for item in report.missing_variables}
        for activity in report.activity[:top]:
            variable = missing_by_name.get(activity.name)
            location = variable.path if variable else activity.entity
            print(
                f"  - {activity.name} ({location}): "
                f"nonzero={activity.nonzero_count:,}, "
                f"weighted_abs_total={activity.weighted_abs_total:.2f}, "
                f"max_abs={activity.max_abs_value:.2f}, "
                f"nonfinite={activity.nonfinite_count:,}"
            )
        inactive_count = sum(1 for item in report.activity if item.nonzero_count == 0)
        print(f"Missing variables with zero nonzero Populace rows: {inactive_count:,}")
        if activity_by_name:
            print()
    print(f"Missing computed PE variables (first {top:,}):")
    for variable in report.missing_variables[:top]:
        print(
            f"  - {variable.name} "
            f"({variable.entity}, {variable.domain}, {variable.computation_kind}) "
            f"{variable.path}"
        )
    if report.activity_errors:
        print()
        print("Activity errors:")
        for error in report.activity_errors[:top]:
            print(
                f"  - {error.get('entity', '?')}:{error.get('variable', '?')}: "
                f"{error.get('error', '')}"
            )


def print_uk_hbai_policy_coverage_report(
    report: UKEFRSHBAICoverageReport,
    *,
    top: int,
) -> None:
    print("PolicyEngine UK HBAI policy coverage")
    print(
        "PolicyEngine versions: "
        + ", ".join(
            f"{package}=={version}"
            for package, version in report.policyengine_versions.items()
        )
    )
    if report.source_root:
        print(f"Variable source root: {report.source_root}")
    print(f"Year: {report.year}")
    print(f"Dataset: {report.dataset}")
    print(
        "HBAI components: "
        f"{len(report.adds):,} adds, {len(report.subtracts):,} subtracts"
    )
    print(
        "Policy components covered exactly or partially: "
        f"{report.covered_policy_component_count:,}/"
        f"{report.policy_component_count:,} "
        f"({report.covered_policy_component_share:.1%})"
    )
    print(
        "Policy components covered exactly: "
        f"{report.exact_policy_component_count:,}/"
        f"{report.policy_component_count:,} "
        f"({report.exact_policy_component_share:.1%})"
    )
    print("Status counts:")
    for status, count in report.status_counts.items():
        print(f"  - {status}: {count:,}")
    if report.hbai_activity:
        print()
        print(
            "HBAI weighted total: "
            f"{report.hbai_activity.weighted_total:.2f}; "
            f"weighted abs total: {report.hbai_activity.weighted_abs_total:.2f}"
        )
    if report.activity_totals:
        totals = report.activity_totals
        print(
            "Policy component weighted abs activity covered exactly or partially: "
            f"{totals['covered_policy_weighted_abs_share']:.1%}"
        )
        print(
            "Policy component weighted abs activity covered exactly: "
            f"{totals['exact_policy_weighted_abs_share']:.1%}"
        )
    print()
    print(f"HBAI components (first {top:,}):")
    for component in report.components[:top]:
        activity = ""
        if component.activity:
            activity = (
                f", weighted_abs_total={component.activity.weighted_abs_total:.2f}"
            )
        surfaces = ", ".join(component.surfaces) if component.surfaces else "none"
        print(
            f"  - {component.name} ({component.direction}): "
            f"{component.status}, surfaces={surfaces}{activity}"
        )
    if report.activity_errors:
        print()
        print("Activity errors:")
        for error in report.activity_errors[:top]:
            print(f"  - {error.get('variable', '?')}: {error.get('error', '')}")


def select_person_indices(
    rows: list[dict[str, Any]],
    *,
    sample_size: int,
    person_ids: tuple[int, ...] = (),
) -> list[int]:
    return select_entity_indices(
        rows,
        sample_size=sample_size,
        requested_ids=person_ids,
        id_column="person_id",
        weight_column="person_weight",
        entity_label="Populace person_id",
    )


def select_benunit_indices(
    rows: list[dict[str, Any]],
    *,
    sample_size: int,
    benunit_ids: tuple[int, ...] = (),
) -> list[int]:
    return select_entity_indices(
        rows,
        sample_size=sample_size,
        requested_ids=benunit_ids,
        id_column="benunit_id",
        weight_column="benunit_weight",
        entity_label="Populace benunit_id",
    )


def select_entity_indices(
    rows: list[dict[str, Any]],
    *,
    sample_size: int,
    requested_ids: tuple[int, ...] = (),
    id_column: str,
    weight_column: str,
    entity_label: str,
) -> list[int]:
    eligible = [
        index
        for index, row in enumerate(rows)
        if money(row_value(row, weight_column, 0)) > 0
    ]
    if not requested_ids:
        return eligible if sample_size <= 0 else eligible[:sample_size]

    requested_ids = tuple(dict.fromkeys(int(value) for value in requested_ids))
    index_by_id = {
        int(row_value(row, id_column)): index for index, row in enumerate(rows)
    }
    eligible_set = set(eligible)
    selected: list[int] = []
    missing: list[int] = []
    filtered: list[int] = []
    for person_id in requested_ids:
        index = index_by_id.get(person_id)
        if index is None:
            missing.append(person_id)
        elif index not in eligible_set:
            filtered.append(person_id)
        else:
            selected.append(index)
    if missing:
        raise SystemExit(
            f"Requested {entity_label} not found: "
            + ", ".join(str(value) for value in missing)
        )
    if filtered:
        raise SystemExit(
            f"Requested {entity_label} is not eligible for this comparison: "
            + ", ".join(str(value) for value in filtered)
        )
    return selected


def run_axiom_surface(
    *,
    program: Path,
    request: dict[str, Any],
    rulespec_root: Path,
    axiom_rules_path: Path,
    surface: str,
) -> list[dict[str, Any]]:
    if surface in UNIVERSAL_CREDIT_REGULATION_36_SURFACES:
        return run_axiom_parameter_outputs(
            program=program,
            request=request,
            rulespec_root=rulespec_root,
        )
    return run_axiom_program(
        program=program,
        request=request,
        rulespec_root=rulespec_root,
        axiom_rules_path=axiom_rules_path,
    )


def run_axiom_parameter_outputs(
    *,
    program: Path,
    request: dict[str, Any],
    rulespec_root: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    parameter_cache: dict[str, dict[str, float]] = {}
    for query in request.get("queries", []):
        period_start = str((query.get("period") or {}).get("start") or "")
        if period_start not in parameter_cache:
            parameter_cache[period_start] = rulespec_scalar_parameter_values(
                program,
                rulespec_root=rulespec_root,
                period_start=period_start,
            )
        parameter_values = parameter_cache[period_start]
        outputs: dict[str, dict[str, Any]] = {}
        for output in query.get("outputs", []):
            if output not in parameter_values:
                raise SystemExit(f"unknown RuleSpec scalar parameter: {output}")
            outputs[output] = {"value": {"value": str(parameter_values[output])}}
        results.append({"outputs": outputs})
    return results


def rulespec_scalar_parameter_values(
    program: Path, *, rulespec_root: Path, period_start: str
) -> dict[str, float]:
    return _rulespec_scalar_parameter_values(
        program.resolve(),
        rulespec_root=rulespec_root.resolve(),
        period_start=period_start,
        seen=set(),
    )


def _rulespec_scalar_parameter_values(
    program: Path,
    *,
    rulespec_root: Path,
    period_start: str,
    seen: set[Path],
) -> dict[str, float]:
    if program in seen:
        return {}
    seen.add(program)
    payload = yaml.safe_load(program.read_text()) or {}
    values: dict[str, float] = {}
    try:
        base = rule_base_from_program(program)
    except ValueError:
        base = None
    for rule in payload.get("rules") or []:
        if str(rule.get("kind") or "").strip() != "parameter":
            continue
        if base is None:
            continue
        version = effective_parameter_version(rule.get("versions") or [], period_start)
        if version is None:
            continue
        formula = str(version.get("formula") or "").strip().replace("_", "")
        try:
            value = float(formula)
        except ValueError:
            continue
        values[f"{base}#{rule['name']}"] = value
    for import_ref in payload.get("imports") or []:
        imported = resolve_rulespec_import(import_ref, rulespec_root=rulespec_root)
        if imported is None:
            continue
        values.update(
            _rulespec_scalar_parameter_values(
                imported,
                rulespec_root=rulespec_root,
                period_start=period_start,
                seen=seen,
            )
        )
    return values


def resolve_rulespec_import(import_ref: Any, *, rulespec_root: Path) -> Path | None:
    raw = str(import_ref or "").strip()
    if not raw:
        return None
    if ":" in raw:
        repo_prefix, path_ref = raw.split(":", 1)
        if repo_prefix != "uk":
            return None
    else:
        path_ref = raw
    candidate = rulespec_root / f"{path_ref}.yaml"
    if candidate.exists():
        return candidate.resolve()
    return None


def effective_parameter_version(
    versions: list[dict[str, Any]],
    period_start: str,
) -> dict[str, Any] | None:
    eligible = [
        version
        for version in versions
        if str(version.get("effective_from") or "") <= period_start
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda version: str(version.get("effective_from") or ""))


def rule_base_from_program(program: Path) -> str:
    parts = program.with_suffix("").parts
    if "regulations" in parts:
        index = parts.index("regulations")
        return "uk:" + "/".join(parts[index:])
    if "statutes" in parts:
        index = parts.index("statutes")
        return "uk:" + "/".join(parts[index:])
    if "policies" in parts:
        index = parts.index("policies")
        return "uk:" + "/".join(parts[index:])
    raise ValueError(f"cannot infer UK RuleSpec base from {program}")


def build_axiom_request(
    *,
    pe_data: dict[str, Any],
    year: int,
    surface: str = "personal-allowance",
) -> dict[str, Any]:
    if surface == "national-insurance-class-1":
        return build_national_insurance_class_1_request(pe_data=pe_data, year=year)
    if surface == "national-insurance-class-4":
        return build_national_insurance_class_4_request(pe_data=pe_data, year=year)
    if surface == "national-insurance-class-4-final":
        return build_national_insurance_class_4_final_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "national-insurance-final":
        return build_national_insurance_final_request(pe_data=pe_data, year=year)
    if surface == "personal-allowance":
        return build_personal_allowance_request(pe_data=pe_data, year=year)
    if surface == "income-tax-income-base":
        return build_income_tax_income_base_request(pe_data=pe_data, year=year)
    if surface == "income-tax-section-10-earned-income":
        return build_income_tax_section_10_request(pe_data=pe_data, year=year)
    if surface == "income-tax-section-11d-savings-income":
        return build_income_tax_section_11d_request(pe_data=pe_data, year=year)
    if surface == "income-tax-section-13-dividend-income":
        return build_income_tax_section_13_request(pe_data=pe_data, year=year)
    if surface == "child-benefit":
        return build_child_benefit_request(pe_data=pe_data, year=year)
    if surface == "child-benefit-final":
        return build_child_benefit_final_request(pe_data=pe_data, year=year)
    if surface == "benefit-cap-relevant-amount":
        return build_benefit_cap_relevant_amount_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "state-pension-credit-qualifying-age":
        return build_state_pension_credit_qualifying_age_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "state-pension-credit-guarantee-credit":
        return build_state_pension_credit_guarantee_credit_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "state-pension-credit-savings-credit":
        return build_state_pension_credit_savings_credit_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "state-pension-final":
        return build_state_pension_final_request(pe_data=pe_data, year=year)
    if surface == "pension-credit":
        return build_pension_credit_request(pe_data=pe_data, year=year)
    if surface == "pension-credit-child-addition":
        return build_pension_credit_child_addition_request(pe_data=pe_data, year=year)
    if surface == "pension-credit-deemed-income":
        return build_pension_credit_deemed_income_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "pension-credit-final":
        return build_pension_credit_final_request(pe_data=pe_data, year=year)
    if surface == "esa-income-tariff-income":
        return build_esa_income_tariff_income_request(pe_data=pe_data, year=year)
    if surface == "esa-income-final":
        return build_esa_income_final_request(pe_data=pe_data, year=year)
    if surface == "jsa-income-tariff-income":
        return build_jsa_income_tariff_income_request(pe_data=pe_data, year=year)
    if surface == "income-support-tariff-income":
        return build_income_support_tariff_income_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "housing-benefit-working-age-tariff-income":
        return build_housing_benefit_working_age_tariff_income_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "housing-benefit-pension-age-tariff-income":
        return build_housing_benefit_pension_age_tariff_income_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "housing-benefit-final":
        return build_housing_benefit_final_request(pe_data=pe_data, year=year)
    if surface == "universal-credit-childcare-element":
        return build_universal_credit_childcare_element_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "universal-credit-childcare-work-condition":
        return build_universal_credit_childcare_work_condition_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "universal-credit-award":
        return build_universal_credit_award_request(pe_data=pe_data, year=year)
    if surface == "universal-credit-final":
        return build_universal_credit_final_request(pe_data=pe_data, year=year)
    if surface == "universal-credit-housing-costs":
        return build_universal_credit_housing_costs_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "universal-credit-income-deduction":
        return build_universal_credit_income_deduction_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "universal-credit-assessable-capital":
        return build_universal_credit_assessable_capital_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "universal-credit-tariff-income":
        return build_universal_credit_tariff_income_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "universal-credit-work-allowance":
        return build_universal_credit_work_allowance_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "student-loan-repayment":
        return build_student_loan_repayment_request(pe_data=pe_data, year=year)
    if surface == "carers-allowance-final":
        return build_carers_allowance_final_request(pe_data=pe_data, year=year)
    if surface == "carer-support-payment-final":
        return build_carer_support_payment_final_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "scottish-child-payment-final":
        return build_scottish_child_payment_final_request(
            pe_data=pe_data,
            year=year,
        )
    if surface == "severe-disablement-allowance-final":
        return build_sda_final_request(pe_data=pe_data, year=year)
    if surface == "disability-living-allowance-final":
        return build_dla_final_request(pe_data=pe_data, year=year)
    if surface in UNIVERSAL_CREDIT_REGULATION_36_SURFACES:
        return build_universal_credit_request(
            pe_data=pe_data,
            year=year,
            surface=surface,
        )
    raise ValueError(f"unsupported UK Populace surface: {surface}")


def build_national_insurance_class_1_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_week_interval(year)
    parameters = policyengine_uk_class_1_weekly_parameters(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "national-insurance-class-1"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        projected = {
            "primary_class_1_contribution_payable_as_mentioned_in_section_6_1_a": bool(
                row_value(row, "ni_liable", True)
            ),
            "regulations_under_section_6_6_do_not_displace_calculation": True,
            "regulations_under_sections_116_to_120_do_not_displace_calculation": True,
            "earnings_paid_in_tax_week_in_respect_of_employment": money(
                row_value(row, "ni_class_1_income", 0)
            )
            / WEEKS_IN_YEAR,
            "current_primary_threshold_or_prescribed_equivalent": parameters[
                "primary_threshold"
            ],
            "current_upper_earnings_limit_or_prescribed_equivalent": parameters[
                "upper_earnings_limit"
            ],
        }
        for name, value in projected.items():
            inputs.append(
                input_record(
                    f"{NATIONAL_INSURANCE_SECTION_8_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in NATIONAL_INSURANCE_CLASS_1_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_national_insurance_class_4_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "national-insurance-class-4"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_national_insurance_class_4_inputs(row).items():
            inputs.append(
                input_record(
                    f"{NATIONAL_INSURANCE_SECTION_15_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in NATIONAL_INSURANCE_CLASS_4_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_national_insurance_class_4_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    parameters = policyengine_uk_class_4_parameters(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "national-insurance-class-4-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        projected = project_national_insurance_class_4_final_inputs(
            row,
            parameters=parameters,
        )
        for name, value in projected.items():
            inputs.append(
                input_record(
                    f"{NATIONAL_INSURANCE_REGULATION_100_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in NATIONAL_INSURANCE_REGULATION_100_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_national_insurance_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "national-insurance-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_national_insurance_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{NATIONAL_INSURANCE_SECTION_1_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in NATIONAL_INSURANCE_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_personal_allowance_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "personal-allowance"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_personal_allowance_inputs(row).items():
            inputs.append(
                input_record(
                    f"{PERSONAL_ALLOWANCE_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in PERSONAL_ALLOWANCE_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_income_tax_income_base_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "income-tax-income-base"):
        person_id = int(row_value(row, "person_id"))
        entity_id = person_entity_id(person_id)
        for component in project_income_tax_income_base_components(row):
            payment_id = income_tax_component_entity_id(
                person_id,
                str(component["name"]),
            )
            relations.append(
                {
                    "name": f"{INCOME_TAX_SECTION_23_BASE}#relation.income_component_of_taxpayer",
                    "tuple": [payment_id, entity_id],
                    "interval": interval,
                }
            )
            inputs.append(
                input_record(
                    f"{INCOME_TAX_SECTION_23_BASE}#input.amount_charged_to_income_tax",
                    payment_id,
                    interval,
                    money(component["amount_charged_to_income_tax"]),
                )
            )
            inputs.append(
                input_record(
                    f"{INCOME_TAX_SECTION_23_BASE}#input.relief_deducted_under_section_24",
                    payment_id,
                    interval,
                    money(component["relief_deducted_under_section_24"]),
                )
            )
        for name, value in project_income_tax_section_23_inputs(row).items():
            inputs.append(
                input_record(
                    f"{INCOME_TAX_SECTION_23_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in INCOME_TAX_INCOME_BASE_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": queries,
    }


def build_income_tax_section_10_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    parameters = policyengine_uk_income_tax_section_10_parameters(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "income-tax-section-10-earned-income"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_income_tax_section_10_inputs(
            row,
            parameters=parameters,
        ).items():
            inputs.append(
                input_record(
                    f"{INCOME_TAX_SECTION_10_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in INCOME_TAX_SECTION_10_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_income_tax_section_11d_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    parameters = policyengine_uk_income_tax_section_11d_parameters(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "income-tax-section-11d-savings-income"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_income_tax_section_11d_inputs(
            row,
            parameters=parameters,
        ).items():
            inputs.append(
                input_record(
                    f"{INCOME_TAX_SECTION_11D_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in INCOME_TAX_SECTION_11D_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_income_tax_section_13_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    parameters = policyengine_uk_income_tax_section_13_parameters(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "income-tax-section-13-dividend-income"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_income_tax_section_13_inputs(
            row,
            parameters=parameters,
        ).items():
            inputs.append(
                input_record(
                    f"{INCOME_TAX_SECTION_13_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in INCOME_TAX_SECTION_13_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_child_benefit_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "child-benefit"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_child_benefit_inputs(row).items():
            inputs.append(
                input_record(
                    f"{CHILD_BENEFIT_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [spec["axiom"] for spec in CHILD_BENEFIT_OUTPUTS.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_child_benefit_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    inputs: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    child_rows_by_benunit = child_benefit_person_rows_by_benunit(pe_data)
    for row in rows_for_surface(pe_data, "child-benefit-final"):
        benunit_id = int(row_value(row, "benunit_id"))
        entity_id = benunit_entity_id(benunit_id)
        inputs.append(
            input_record(
                f"{CHILD_BENEFIT_FINAL_BASE}#input.would_claim_child_benefit",
                entity_id,
                interval,
                bool(row_value(row, "would_claim_child_benefit", True)),
            )
        )
        for child_row in child_rows_by_benunit.get(benunit_id, []):
            person_id = int(row_value(child_row, "person_id"))
            person_id_text = person_entity_id(person_id)
            relations.append(
                {
                    "name": (
                        f"{CHILD_BENEFIT_SECTION_141_BASE}#relation."
                        "child_benefit_children_or_qualifying_young_persons_for_whom_person_responsible"
                    ),
                    "tuple": [person_id_text, entity_id],
                    "interval": interval,
                }
            )
            inputs.append(
                input_record(
                    (
                        f"{CHILD_BENEFIT_SECTION_141_BASE}"
                        "#input.is_child_or_qualifying_young_person_for_child_benefit"
                    ),
                    person_id_text,
                    interval,
                    True,
                )
            )
            for name, value in project_child_benefit_inputs(child_row).items():
                inputs.append(
                    input_record(
                        f"{CHILD_BENEFIT_BASE}#input.{name}",
                        person_id_text,
                        interval,
                        value,
                    )
                )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in CHILD_BENEFIT_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": queries,
    }


def build_benefit_cap_relevant_amount_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "benefit-cap-relevant-amount"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_benefit_cap_relevant_amount_inputs(row).items():
            inputs.append(
                input_record(
                    f"{BENEFIT_CAP_REGULATION_80A_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in BENEFIT_CAP_RELEVANT_AMOUNT_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_state_pension_credit_qualifying_age_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = day_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "state-pension-credit-qualifying-age"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_state_pension_credit_qualifying_age_inputs(
            row
        ).items():
            inputs.append(
                input_record(
                    f"{STATE_PENSION_CREDIT_SECTION_1_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in STATE_PENSION_CREDIT_QUALIFYING_AGE_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_state_pension_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    parameters = policyengine_uk_state_pension_parameters(
        year=year,
        data_year=int(pe_data.get("data_year") or year),
    )
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "state-pension-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_state_pension_final_inputs(
            row,
            parameters=parameters,
        ).items():
            inputs.append(
                input_record(
                    f"{STATE_PENSION_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in STATE_PENSION_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_pension_credit_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "pension-credit"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_pension_credit_inputs(row).items():
            inputs.append(
                input_record(
                    f"{PENSION_CREDIT_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [spec["axiom"] for spec in PENSION_CREDIT_OUTPUTS.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_pension_credit_child_addition_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "pension-credit-child-addition"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_pension_credit_child_addition_inputs(row).items():
            inputs.append(
                input_record(
                    f"{PENSION_CREDIT_SCHEDULE_IIA_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in PENSION_CREDIT_CHILD_ADDITION_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_pension_credit_deemed_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "pension-credit-deemed-income"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_pension_credit_deemed_income_inputs(row).items():
            inputs.append(
                input_record(
                    f"{PENSION_CREDIT_REGULATION_15_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in PENSION_CREDIT_DEEMED_INCOME_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_legacy_weekly_tariff_income_request(
    *,
    pe_data: dict[str, Any],
    year: int,
    surface: str,
    base: str,
    outputs: dict[str, dict[str, Any]],
    project_inputs: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    interval = benefit_week_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, surface):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_inputs(row).items():
            inputs.append(
                input_record(
                    f"{base}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [spec["axiom"] for spec in outputs.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_pension_credit_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "pension-credit-final"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_pension_credit_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{PENSION_CREDIT_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in PENSION_CREDIT_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_esa_income_tariff_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    return build_legacy_weekly_tariff_income_request(
        pe_data=pe_data,
        year=year,
        surface="esa-income-tariff-income",
        base=ESA_REGULATION_118_BASE,
        outputs=ESA_TARIFF_INCOME_OUTPUTS,
        project_inputs=project_esa_income_tariff_income_inputs,
    )


def build_esa_income_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "esa-income-final"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_esa_income_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{ESA_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [spec["axiom"] for spec in ESA_FINAL_OUTPUTS.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_jsa_income_tariff_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    return build_legacy_weekly_tariff_income_request(
        pe_data=pe_data,
        year=year,
        surface="jsa-income-tariff-income",
        base=JSA_REGULATION_116_BASE,
        outputs=JSA_TARIFF_INCOME_OUTPUTS,
        project_inputs=project_jsa_income_tariff_income_inputs,
    )


def build_income_support_tariff_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    return build_legacy_weekly_tariff_income_request(
        pe_data=pe_data,
        year=year,
        surface="income-support-tariff-income",
        base=INCOME_SUPPORT_REGULATION_53_BASE,
        outputs=INCOME_SUPPORT_TARIFF_INCOME_OUTPUTS,
        project_inputs=project_income_support_tariff_income_inputs,
    )


def build_housing_benefit_working_age_tariff_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    return build_legacy_weekly_tariff_income_request(
        pe_data=pe_data,
        year=year,
        surface="housing-benefit-working-age-tariff-income",
        base=HOUSING_BENEFIT_REGULATION_52_BASE,
        outputs=HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS,
        project_inputs=project_housing_benefit_working_age_tariff_income_inputs,
    )


def build_housing_benefit_pension_age_tariff_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    return build_legacy_weekly_tariff_income_request(
        pe_data=pe_data,
        year=year,
        surface="housing-benefit-pension-age-tariff-income",
        base=HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_BASE,
        outputs=HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS,
        project_inputs=project_housing_benefit_pension_age_tariff_income_inputs,
    )


def build_housing_benefit_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "housing-benefit-final"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_housing_benefit_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{HOUSING_BENEFIT_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in HOUSING_BENEFIT_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_state_pension_credit_guarantee_credit_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "state-pension-credit-guarantee-credit"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_state_pension_credit_guarantee_credit_inputs(
            row
        ).items():
            inputs.append(
                input_record(
                    f"{STATE_PENSION_CREDIT_SECTION_2_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_state_pension_credit_savings_credit_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    parameters = policyengine_uk_savings_credit_parameters(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "state-pension-credit-savings-credit"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_state_pension_credit_savings_credit_inputs(
            row,
            parameters=parameters,
        ).items():
            inputs.append(
                input_record(
                    f"{STATE_PENSION_CREDIT_SECTION_3_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in STATE_PENSION_CREDIT_SAVINGS_CREDIT_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_request(
    *, pe_data: dict[str, Any], year: int, surface: str
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    spec = SURFACE_SPECS[surface]
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, surface):
        if spec.entity == "benunit":
            entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        else:
            entity_id = person_entity_id(int(row_value(row, "person_id")))
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [output["axiom"] for output in spec.outputs.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": [], "relations": []},
        "queries": queries,
    }


def build_universal_credit_childcare_element_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-childcare-element"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_childcare_element_inputs(
            row
        ).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_REGULATION_34_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_CHILDCARE_ELEMENT_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_childcare_work_condition_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-childcare-work-condition"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_childcare_work_condition_inputs(
            row
        ).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_REGULATION_32_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_award_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-award"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_award_inputs(row).items():
            inputs.append(
                input_record(
                    f"{WELFARE_REFORM_ACT_SECTION_8_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in UNIVERSAL_CREDIT_AWARD_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-final"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in UNIVERSAL_CREDIT_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_housing_costs_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-housing-costs"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_housing_costs_inputs(row).items():
            inputs.append(
                input_record(
                    f"{WELFARE_REFORM_ACT_SECTION_11_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_HOUSING_COSTS_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_income_deduction_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-income-deduction"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_income_deduction_inputs(
            row
        ).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_assessable_capital_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = day_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-assessable-capital"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_assessable_capital_inputs(
            row
        ).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_REGULATION_18_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_ASSESSABLE_CAPITAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_tariff_income_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-tariff-income"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_tariff_income_inputs(row).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_REGULATION_72_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_universal_credit_work_allowance_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = benefit_month_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "universal-credit-work-allowance"):
        entity_id = benunit_entity_id(int(row_value(row, "benunit_id")))
        for name, value in project_universal_credit_work_allowance_inputs(row).items():
            inputs.append(
                input_record(
                    f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in UNIVERSAL_CREDIT_WORK_ALLOWANCE_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_student_loan_repayment_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "student-loan-repayment"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_student_loan_repayment_inputs(row).items():
            inputs.append(
                input_record(
                    f"{STUDENT_LOAN_REPAYMENT_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in STUDENT_LOAN_REPAYMENT_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_carers_allowance_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "carers-allowance-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_carers_allowance_final_inputs(
            row,
            year=year,
        ).items():
            inputs.append(
                input_record(
                    f"{CARERS_ALLOWANCE_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"] for spec in CARERS_ALLOWANCE_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_carer_support_payment_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "carer-support-payment-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_carer_support_payment_final_inputs(
            row,
            year=year,
        ).items():
            inputs.append(
                input_record(
                    f"{CARER_SUPPORT_PAYMENT_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in CARER_SUPPORT_PAYMENT_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_scottish_child_payment_final_request(
    *, pe_data: dict[str, Any], year: int
) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "scottish-child-payment-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_scottish_child_payment_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{SCOTTISH_CHILD_PAYMENT_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [
                    spec["axiom"]
                    for spec in SCOTTISH_CHILD_PAYMENT_FINAL_OUTPUTS.values()
                ],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_sda_final_request(*, pe_data: dict[str, Any], year: int) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "severe-disablement-allowance-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_sda_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{SDA_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [spec["axiom"] for spec in SDA_FINAL_OUTPUTS.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def build_dla_final_request(*, pe_data: dict[str, Any], year: int) -> dict[str, Any]:
    interval = uk_tax_year_interval(year)
    inputs: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for row in rows_for_surface(pe_data, "disability-living-allowance-final"):
        entity_id = person_entity_id(int(row_value(row, "person_id")))
        for name, value in project_dla_final_inputs(row).items():
            inputs.append(
                input_record(
                    f"{DLA_FINAL_BASE}#input.{name}",
                    entity_id,
                    interval,
                    value,
                )
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": interval,
                "outputs": [spec["axiom"] for spec in DLA_FINAL_OUTPUTS.values()],
            }
        )

    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def project_personal_allowance_inputs(row: Any) -> dict[str, Any]:
    adjusted_net_income = money(row_value(row, "adjusted_net_income"))
    gift_aid_grossed_up = money(row_value(row, "gift_aid_grossed_up", 0))
    return {
        "individual_makes_claim": True,
        "individual_meets_requirements_under_section_56": True,
        "adjusted_net_income": max(0.0, adjusted_net_income - gift_aid_grossed_up),
    }


def project_income_tax_income_base_components(row: Any) -> list[dict[str, Any]]:
    components = [
        {
            "name": name,
            "amount_charged_to_income_tax": money(row_value(row, name, 0)),
            "relief_deducted_under_section_24": 0.0,
        }
        for name in INCOME_TAX_INCOME_BASE_COMPONENTS
    ]
    nonzero_components = [
        component
        for component in components
        if money(component["amount_charged_to_income_tax"])
    ]
    if not nonzero_components:
        return []
    total_income = sum(
        money(component["amount_charged_to_income_tax"])
        for component in nonzero_components
    )
    adjusted_net_income = money(row_value(row, "adjusted_net_income", total_income))
    nonzero_components[0]["relief_deducted_under_section_24"] = max(
        0.0,
        total_income - adjusted_net_income,
    )
    return nonzero_components


def project_income_tax_section_23_inputs(row: Any) -> dict[str, Any]:
    additions = sum(
        money(row_value(row, name, 0))
        for name in INCOME_TAX_SECTION_23_ADDITION_COMPONENTS
    )
    reductions = sum(
        money(row_value(row, name, 0))
        for name in INCOME_TAX_SECTION_23_REDUCTION_COMPONENTS
    )
    return {
        "net_income_taken_as_zero_under_section_24b": False,
        "tax_calculated_at_applicable_rates_on_income_remaining_after_allowances": additions,
        "tax_reductions_listed_in_section_26": reductions,
        "additional_tax_amounts_listed_in_section_30": 0.0,
    }


def project_income_tax_section_10_inputs(
    row: Any,
    *,
    parameters: dict[str, float],
) -> dict[str, Any]:
    return {
        "income_charged_under_section_10": money(
            row_value(row, "earned_taxable_income", 0)
        ),
        "basic_rate": parameters["basic_rate"],
        "higher_rate": parameters["higher_rate"],
        "additional_rate": parameters["additional_rate"],
    }


def project_income_tax_section_11d_inputs(
    row: Any,
    *,
    parameters: dict[str, float],
) -> dict[str, Any]:
    savings_after_allowances = max(
        0.0,
        money(row_value(row, "taxable_savings_interest_income", 0))
        - money(row_value(row, "received_allowances_savings_income", 0)),
    )
    zero_rate_savings = min(
        savings_after_allowances,
        money(row_value(row, "savings_allowance", 0))
        + money(row_value(row, "savings_starter_rate_income", 0)),
    )
    return {
        "income_already_charged_before_section_11d_savings_income": money(
            row_value(row, "earned_taxable_income", 0)
        )
        + zero_rate_savings,
        "savings_income_remaining_after_sections_12_and_12a": max(
            0.0,
            savings_after_allowances - zero_rate_savings,
        ),
        "basic_rate_limit": parameters["basic_rate_limit"],
        "higher_rate_limit": parameters["higher_rate_limit"],
        "savings_basic_rate": parameters["savings_basic_rate"],
        "savings_higher_rate": parameters["savings_higher_rate"],
        "savings_additional_rate": parameters["savings_additional_rate"],
    }


def project_income_tax_section_13_inputs(
    row: Any,
    *,
    parameters: dict[str, float],
) -> dict[str, Any]:
    savings_after_income_allowances = max(
        0.0,
        money(row_value(row, "taxable_savings_interest_income", 0))
        - money(row_value(row, "received_allowances_savings_income", 0)),
    )
    dividends_after_income_allowances = max(
        0.0,
        money(row_value(row, "taxable_dividend_income", 0))
        - money(row_value(row, "received_allowances_dividend_income", 0)),
    )
    dividend_allowance_used = min(
        parameters["dividend_allowance"],
        dividends_after_income_allowances,
    )
    return {
        "income_already_charged_before_section_13_dividend_income": money(
            row_value(row, "earned_taxable_income", 0)
        )
        + savings_after_income_allowances
        + dividend_allowance_used,
        "dividend_income_subject_to_section_13_rates": money(
            row_value(row, "taxed_dividend_income", 0)
        ),
        "basic_rate_limit": parameters["basic_rate_limit"],
        "higher_rate_limit": parameters["higher_rate_limit"],
        "dividend_ordinary_rate": parameters["dividend_ordinary_rate"],
        "dividend_upper_rate": parameters["dividend_upper_rate"],
        "dividend_additional_rate": parameters["dividend_additional_rate"],
    }


def project_child_benefit_inputs(row: Any) -> dict[str, Any]:
    child_index = int(row_value(row, "child_benefit_child_index", -1))
    is_eldest = child_index == 1
    return {
        "during_subsistence_of_marriage_any_party_married_to_more_than_one_person": False,
        "marriage_ceremony_took_place_under_law_permitting_polygamy": False,
        "specified_benefit_allowance_or_increase_paid_for_week_to_person": False,
        "specified_benefit_is_in_respect_of_only_elder_or_eldest_child_for_child_benefit_entitlement": False,
        "child_or_qualifying_young_person_is_only_elder_or_eldest_for_payee": is_eldest,
        "paragraph_2_relationship_coordination_applies": False,
        "child_or_qualifying_young_person_is_elder_or_eldest_among_paragraph_2_children": is_eldest,
        "payee_is_voluntary_organisation": False,
        "payee_resides_with_parent_otherwise_than_paragraph_2_a": False,
    }


def child_benefit_person_rows_by_benunit(
    pe_data: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in pe_data.get("all_persons") or pe_data["persons"]:
        if money(row_value(row, "child_benefit_respective_amount", 0)) <= 0:
            continue
        benunit_id = row_value(row, "person_benunit_id")
        if benunit_id is None:
            continue
        grouped.setdefault(int(benunit_id), []).append(row)
    for rows in grouped.values():
        rows.sort(
            key=lambda item: (
                int(row_value(item, "child_benefit_child_index", 999_999)),
                int(row_value(item, "person_id")),
            )
        )
    return grouped


def project_national_insurance_class_4_inputs(row: Any) -> dict[str, Any]:
    profits = money(row_value(row, "self_employment_income", 0)) - money(
        row_value(row, "ni_class_1_employee", 0)
    )
    return {
        "class_4_contributions_payable_under_section_15": bool(
            row_value(row, "ni_liable", True)
        ),
        "profits_chargeable_to_class_4_contributions": profits,
    }


def project_national_insurance_class_4_final_inputs(
    row: Any,
    *,
    parameters: dict[str, float],
) -> dict[str, Any]:
    self_employment_income = money(row_value(row, "self_employment_income", 0))
    employee_ni = money(row_value(row, "ni_class_1_employee", 0))
    profits = self_employment_income - employee_ni
    additional_band_profits = max(0, profits - parameters["upper_profits_limit"])
    pre_maximum_amount = money(row_value(row, "ni_class_4_main", 0)) + (
        additional_band_profits * parameters["additional_class_4_percentage"]
    )
    primary_class_1 = money(row_value(row, "ni_class_1_employee_primary", 0))
    return {
        "primary_class_1_contributions_paid_at_main_primary_percentage": primary_class_1,
        "primary_class_1_contributions_payable_at_main_primary_percentage": primary_class_1,
        "class_4_contributions_payable_at_main_class_4_percentage": money(
            row_value(row, "ni_class_4_main", 0)
        ),
        "class_4_contribution_before_annual_maximum": pre_maximum_amount,
        "class_4_contributions_payable_under_section_15_for_year": bool(
            row_value(row, "ni_liable", True)
        ),
        "profits_and_gains_for_year": self_employment_income,
        "lower_profits_limit": parameters["lower_profits_limit"],
        "upper_profits_limit": parameters["upper_profits_limit"],
        "main_class_4_percentage": parameters["main_class_4_percentage"],
        "additional_class_4_percentage": parameters["additional_class_4_percentage"],
    }


def project_benefit_cap_relevant_amount_inputs(row: Any) -> dict[str, Any]:
    num_adults = int(money(row_value(row, "num_adults", 0)))
    num_children = int(money(row_value(row, "num_children", 0)))
    in_london = enum_name(row_value(row, "benunit_region", "")).upper() == "LONDON"
    return {
        "claim_is_for_joint_claimants": num_adults > 1,
        "responsible_for_child_or_qualifying_young_person": num_children > 0,
        "award_contains_housing_costs_element": False,
        "accommodation_in_respect_of_which_claimant_meets_occupation_condition_is_in_greater_london": False,
        "claimant_receives_housing_benefit_for_dwelling_in_greater_london": False,
        "claimant_has_accommodation_normally_occupied_as_home": True,
        "accommodation_normally_occupied_as_home_is_in_greater_london": in_london,
        "jobcentre_plus_office_allocated_to_claim_is_in_greater_london": False,
    }


def project_state_pension_credit_qualifying_age_inputs(row: Any) -> dict[str, Any]:
    state_pension_age = money(row_value(row, "state_pension_age", 0))
    return {
        "claimant_is_woman": enum_name(row_value(row, "gender", "")).upper()
        == "FEMALE",
        "pensionable_age": state_pension_age,
        "pensionable_age_for_woman_born_same_day": state_pension_age,
        "claimant_age": money(row_value(row, "age", 0)),
    }


def project_state_pension_final_inputs(
    row: Any,
    *,
    parameters: dict[str, float],
) -> dict[str, Any]:
    current_type = enum_name(row_value(row, "state_pension_type", "")).upper()
    data_year_type = enum_name(
        row_value(row, "state_pension_type_data_year", "")
    ).upper()
    return {
        "current_state_pension_type_is_basic": current_type == "BASIC",
        "current_state_pension_type_is_new": current_type == "NEW",
        "data_year_state_pension_type_is_basic": data_year_type == "BASIC",
        "data_year_state_pension_type_is_new": data_year_type == "NEW",
        "reported_state_pension_weekly_amount_in_data_year": money(
            row_value(row, "state_pension_reported_data_year", 0)
        )
        / WEEKS_IN_YEAR,
        "data_year_basic_state_pension_weekly_rate": parameters[
            "data_year_basic_state_pension_weekly_rate"
        ],
        "data_year_full_new_state_pension_weekly_rate": parameters[
            "data_year_full_new_state_pension_weekly_rate"
        ],
        "state_pension_abolished_by_policy": False,
        "state_pension_policy_uprating_factor": parameters[
            "state_pension_policy_uprating_factor"
        ],
    }


def project_national_insurance_final_inputs(row: Any) -> dict[str, Any]:
    return {
        "primary_class_1_contribution_for_year": money(
            row_value(row, "ni_class_1_employee", 0)
        ),
        "class_2_contribution_for_year": money(row_value(row, "ni_class_2", 0)),
        "class_3_contribution_for_year": money(row_value(row, "ni_class_3", 0)),
        "class_4_contribution_for_year": money(row_value(row, "ni_class_4", 0)),
    }


def project_universal_credit_award_inputs(row: Any) -> dict[str, Any]:
    is_uc_eligible = bool(row_value(row, "is_uc_eligible", False))

    def monthly(name: str) -> float:
        return money(row_value(row, name, 0)) / MONTHS_IN_YEAR

    def eligible_monthly(name: str) -> float:
        return monthly(name) if is_uc_eligible else 0.0

    return {
        "amount_included_under_section_9_standard_allowance": eligible_monthly(
            "uc_standard_allowance"
        ),
        "amount_included_under_section_10_responsibility_for_children_and_young_persons": eligible_monthly(
            "uc_child_element"
        ),
        "amount_included_under_section_11_housing_costs": eligible_monthly(
            "uc_housing_costs_element"
        ),
        "amount_included_under_section_12_other_particular_needs_or_circumstances": (
            eligible_monthly("uc_disability_elements")
            + eligible_monthly("uc_childcare_element")
            + eligible_monthly("uc_carer_element")
        ),
        "earned_income_deduction_calculated_in_prescribed_manner": eligible_monthly(
            "uc_income_reduction"
        ),
        "unearned_income_deduction_calculated_in_prescribed_manner": 0.0,
    }


def project_universal_credit_final_inputs(row: Any) -> dict[str, Any]:
    return {
        "universal_credit_pre_benefit_cap_for_year": money(
            row_value(row, "universal_credit_pre_benefit_cap", 0)
        ),
        "benefit_cap_reduction_for_year": money(
            row_value(row, "benefit_cap_reduction", 0)
        ),
    }


def project_universal_credit_childcare_element_inputs(row: Any) -> dict[str, Any]:
    monthly_childcare_element = money(row_value(row, "uc_childcare_element", 0)) / (
        MONTHS_IN_YEAR
    )
    monthly_childcare_maximum = (
        money(row_value(row, "uc_maximum_childcare_element_amount", 0)) / MONTHS_IN_YEAR
    )
    relevant_charges = (
        monthly_childcare_element
        / UNIVERSAL_CREDIT_2026_RULESPEC_RATES[
            "childcare_costs_element_reimbursement_rate"
        ]
        if monthly_childcare_element
        else 0.0
    )
    return {
        "charges_paid_for_relevant_childcare_attributable_to_assessment_period": relevant_charges,
        "amount_considered_excessive_having_regard_to_paid_work_extent": 0.0,
        "amount_met_or_reimbursed_by_employer_or_some_other_person": 0.0,
        "secretary_of_state_work_transition_childcare_payment_meets_non_other_relevant_support_conditions": False,
        "amount_from_funds_provided_by_secretary_of_state_or_scottish_or_welsh_ministers_for_work_related_activity_or_training": 0.0,
        "secretary_of_state_work_transition_childcare_payment_amount": 0.0,
        "maximum_amount_specified_in_table_in_regulation_36": max(
            0.0,
            monthly_childcare_maximum,
        ),
    }


def project_universal_credit_childcare_work_condition_inputs(
    row: Any,
) -> dict[str, Any]:
    adult_count = int(money(row_value(row, "uc_childcare_adult_count", 0)))
    return {
        "claimant_in_paid_work": bool(
            row_value(row, "uc_childcare_any_adult_in_work", False)
        ),
        "claimant_ceased_paid_work_in_assessment_period": False,
        "claimant_ceased_paid_work_in_previous_assessment_period": False,
        "assessment_period_is_first_or_second_assessment_period_in_relation_to_award": False,
        "claimant_ceased_paid_work_in_month_immediately_preceding_award_commencement": False,
        "claimant_receiving_statutory_sick_pay": False,
        "claimant_receiving_statutory_maternity_pay": False,
        "claimant_receiving_statutory_paternity_pay": False,
        "claimant_receiving_statutory_adoption_pay": False,
        "claimant_receiving_statutory_shared_parental_pay": False,
        "claimant_receiving_statutory_parental_bereavement_pay": False,
        "claimant_receiving_statutory_neonatal_care_pay": False,
        "claimant_receiving_maternity_allowance": False,
        "claimant_has_offer_of_paid_work_due_to_start_before_end_of_next_assessment_period": False,
        "claimant_is_member_of_couple": adult_count > 1,
        "other_member_in_paid_work": bool(
            row_value(row, "uc_childcare_all_adults_in_work", False)
        ),
        "other_member_has_limited_capability_for_work": False,
        "other_member_has_regular_and_substantial_caring_responsibilities_for_severely_disabled_person": False,
        "other_member_temporarily_absent_from_claimants_household": False,
    }


def project_universal_credit_housing_costs_inputs(row: Any) -> dict[str, Any]:
    monthly_housing_costs = money(row_value(row, "uc_housing_costs_element", 0)) / (
        MONTHS_IN_YEAR
    )
    return {
        "payments_are_in_respect_of_accommodation_for_section_11": True,
        "accommodation_is_in_great_britain": True,
        "accommodation_is_residential_accommodation": True,
        "claimant_is_liable_to_make_accommodation_payments": True,
        "claimant_is_treated_as_liable_to_make_accommodation_payments_by_regulations": False,
        "claimant_is_treated_as_not_liable_to_make_accommodation_payments_by_regulations": False,
        "claimant_occupies_accommodation_as_home": True,
        "claimant_is_treated_as_occupying_accommodation_as_home_by_regulations": False,
        "claimant_is_treated_as_not_occupying_accommodation_as_home_by_regulations": False,
        "section_11_exception_to_accommodation_amount_applies_by_regulations": False,
        "section_11_inclusion_has_ended_at_prescribed_time_by_regulations": False,
        "section_11_inclusion_has_not_started_until_prescribed_time_by_regulations": False,
        "amount_determined_or_calculated_by_regulations_under_section_11": monthly_housing_costs,
    }


def project_universal_credit_income_deduction_inputs(row: Any) -> dict[str, Any]:
    work_allowance_inputs = project_universal_credit_work_allowance_inputs(row)
    work_allowance_specified = (
        work_allowance_inputs[
            "joint_claimants_responsible_for_child_or_qualifying_young_person"
        ]
        or work_allowance_inputs[
            "one_or_both_joint_claimants_have_limited_capability_for_work"
        ]
        or work_allowance_inputs[
            "single_claimant_responsible_for_child_or_qualifying_young_person"
        ]
        or work_allowance_inputs["single_claimant_has_limited_capability_for_work"]
    )
    monthly_earned_subject_to_taper = (
        money(row_value(row, "uc_earned_income", 0)) / MONTHS_IN_YEAR
    )
    monthly_work_allowance = (
        money(row_value(row, "uc_work_allowance", 0)) / MONTHS_IN_YEAR
        if work_allowance_specified
        else 0.0
    )
    monthly_earned_income_for_deduction = (
        monthly_earned_subject_to_taper + monthly_work_allowance
    )
    monthly_unearned_income = (
        money(row_value(row, "uc_unearned_income", 0)) / MONTHS_IN_YEAR
    )
    joint_claim = bool(work_allowance_inputs["claim_is_for_joint_claimants"])
    claimant_earned_income = 0.0 if joint_claim else monthly_earned_income_for_deduction
    joint_earned_income = monthly_earned_income_for_deduction if joint_claim else 0.0
    claimant_unearned_income = 0.0 if joint_claim else monthly_unearned_income
    joint_unearned_income = monthly_unearned_income if joint_claim else 0.0
    return {
        **work_allowance_inputs,
        "claimant_earned_income_in_assessment_period": claimant_earned_income,
        "joint_claimants_combined_earned_income_in_assessment_period": joint_earned_income,
        "claimant_unearned_income_in_assessment_period": claimant_unearned_income,
        "joint_claimants_combined_unearned_income_in_assessment_period": joint_unearned_income,
    }


def project_universal_credit_tariff_income_inputs(row: Any) -> dict[str, Any]:
    return {
        "person_capital": money(row_value(row, "uc_assessable_capital", 0)),
        "capital_is_disregarded": False,
        "actual_income_from_capital_taken_into_account_under_regulation_66_1_i_annuity": False,
        "actual_income_from_capital_taken_into_account_under_regulation_66_1_j_trust": False,
        "actual_income_derived_from_that_capital_due_to_be_paid_to_person_on_day_amount": 0.0,
    }


def project_pension_credit_deemed_income_inputs(row: Any) -> dict[str, Any]:
    return {
        "claimant_capital": money(
            row_value(row, "pension_credit_assessable_capital", 0)
        ),
        "capital_disregarded_under_regulation_17_8": False,
    }


def project_esa_income_tariff_income_inputs(row: Any) -> dict[str, Any]:
    return {
        "claimant_capital": money(row_value(row, "esa_income_assessable_capital", 0)),
        "claimant_in_prescribed_accommodation_under_regulation_118_3": False,
    }


def project_jsa_income_tariff_income_inputs(row: Any) -> dict[str, Any]:
    return {
        "claimant_capital": money(row_value(row, "jsa_income_assessable_capital", 0)),
        "claimant_in_prescribed_accommodation_under_regulation_116_1B": False,
    }


def project_income_support_tariff_income_inputs(row: Any) -> dict[str, Any]:
    return {
        "claimant_capital": money(
            row_value(row, "income_support_assessable_capital", 0)
        ),
        "claimant_in_prescribed_accommodation_under_regulation_53_1B": False,
    }


def project_housing_benefit_working_age_tariff_income_inputs(
    row: Any,
) -> dict[str, Any]:
    return {
        "claimant_capital": money(
            row_value(row, "housing_benefit_assessable_capital", 0)
        ),
        "claimant_in_prescribed_circumstances_under_regulation_52_4": False,
    }


def project_housing_benefit_pension_age_tariff_income_inputs(
    row: Any,
) -> dict[str, Any]:
    return {
        "claimant_capital": money(
            row_value(row, "housing_benefit_assessable_capital", 0)
        ),
        "capital_disregarded_under_regulation_44_2": False,
    }


def project_housing_benefit_final_inputs(row: Any) -> dict[str, Any]:
    return {
        "housing_benefit_pre_benefit_cap_for_year": money(
            row_value(row, "housing_benefit_pre_benefit_cap", 0)
        ),
        "benefit_cap_reduction_for_year": money(
            row_value(row, "benefit_cap_reduction", 0)
        ),
        "would_claim_housing_benefit": bool_row_value(
            row, "would_claim_housing_benefit", False
        ),
    }


def project_universal_credit_assessable_capital_inputs(row: Any) -> dict[str, Any]:
    return {
        "claim_is_for_joint_claimants": False,
        "claimant_is_member_of_couple": False,
        "claimant_makes_claim_as_single_person": False,
        "claimant_capital": money(row_value(row, "uc_assessable_capital", 0)),
        "other_member_of_couple_capital": 0.0,
    }


def project_universal_credit_work_allowance_inputs(row: Any) -> dict[str, Any]:
    num_adults = int(money(row_value(row, "num_adults", 0)))
    num_children = int(money(row_value(row, "num_children", 0)))
    joint_claim = num_adults > 1
    has_child = num_children > 0
    eligible = bool(row_value(row, "is_uc_work_allowance_eligible", False))
    has_limited_capability = eligible and not has_child
    return {
        "claim_is_for_joint_claimants": joint_claim,
        "claimant_is_member_of_couple": False,
        "claimant_makes_claim_as_single_person": False,
        "joint_claimants_responsible_for_child_or_qualifying_young_person": joint_claim
        and has_child,
        "one_or_both_joint_claimants_have_limited_capability_for_work": joint_claim
        and has_limited_capability,
        "single_claimant_responsible_for_child_or_qualifying_young_person": (
            not joint_claim and has_child
        ),
        "single_claimant_has_limited_capability_for_work": (
            not joint_claim and has_limited_capability
        ),
        "award_contains_housing_costs_element": money(
            row_value(row, "uc_housing_costs_element", 0)
        )
        > 0,
    }


def project_student_loan_repayment_inputs(row: Any) -> dict[str, Any]:
    plan = enum_name(row_value(row, "student_loan_plan", "NONE")).upper()
    return {
        "loan_plan_is_plan_1": plan == "PLAN_1",
        "loan_plan_is_plan_2": plan == "PLAN_2",
        "loan_plan_is_plan_4": plan == "PLAN_4",
        "loan_plan_is_plan_5": plan == "PLAN_5",
        "loan_plan_is_postgraduate": plan
        in {
            "POSTGRADUATE",
            "POSTGRADUATE_LOAN",
            "PLAN_3",
        },
        "annual_income_before_tax_and_other_deductions": money(
            row_value(row, "adjusted_net_income", 0)
        ),
    }


def project_carers_allowance_final_inputs(row: Any, *, year: int) -> dict[str, Any]:
    country = enum_name(row_value(row, "country", "")).upper()
    has_positive_or_reported_award = (
        money(row_value(row, "carers_allowance", 0)) > 0
        or money(row_value(row, "carers_allowance_reported", 0)) > 0
    )
    weekly_care_hours = money(row_value(row, "care_hours", 0))
    if has_positive_or_reported_award:
        weekly_care_hours = max(weekly_care_hours, 35.0)
    return {
        "person_is_aged_16_or_over": money(row_value(row, "age", 0)) >= 16,
        "weekly_care_hours": weekly_care_hours,
        "cared_for_person_receives_qualifying_disability_benefit": has_positive_or_reported_award,
        "weekly_earnings_after_tax_national_insurance_and_expenses": 0.0,
        "person_is_in_full_time_education": False,
        "person_lives_in_scotland": country == "SCOTLAND",
    }


def project_carer_support_payment_final_inputs(
    row: Any,
    *,
    year: int,
) -> dict[str, Any]:
    country = enum_name(row_value(row, "country", "")).upper()
    has_positive_or_reported_award = (
        money(row_value(row, "carer_support_payment", 0)) > 0
        or money(row_value(row, "carers_allowance_reported", 0)) > 0
    )
    weekly_care_hours = money(row_value(row, "care_hours", 0))
    if has_positive_or_reported_award:
        weekly_care_hours = max(weekly_care_hours, 35.0)
    return {
        "person_is_aged_16_or_over": money(row_value(row, "age", 0)) >= 16,
        "person_lives_in_scotland": country == "SCOTLAND" and year >= 2025,
        "weekly_care_hours": weekly_care_hours,
        "cared_for_person_receives_qualifying_disability_benefit": has_positive_or_reported_award,
        "weekly_earnings_after_tax_national_insurance_and_expenses": 0.0,
        "person_is_in_full_time_education": False,
    }


def project_scottish_child_payment_final_inputs(row: Any) -> dict[str, Any]:
    has_final_award = money(row_value(row, "scottish_child_payment", 0)) > 0
    return {
        "person_lives_in_scotland": has_final_award,
        "child_age": money(row_value(row, "age", 99)),
        "applicant_or_partner_receives_qualifying_benefit": has_final_award,
    }


def project_sda_final_inputs(row: Any) -> dict[str, Any]:
    return {
        "reported_severe_disablement_allowance_for_year": money(
            row_value(row, "sda_reported", 0)
        ),
    }


def project_dla_final_inputs(row: Any) -> dict[str, Any]:
    self_care_category = enum_name(row_value(row, "dla_sc_category", "NONE")).upper()
    mobility_category = enum_name(row_value(row, "dla_m_category", "NONE")).upper()
    age = money(row_value(row, "age", 999))
    return {
        "child_is_under_16": age < 16,
        "child_is_aged_3_or_over": age >= 3,
        "child_is_aged_5_or_over": age >= 5,
        "care_component_is_highest_rate": self_care_category
        in {"HIGHER", "HIGHEST", "HIGH"},
        "care_component_is_middle_rate": self_care_category == "MIDDLE",
        "care_component_is_lowest_rate": self_care_category in {"LOWER", "LOW"},
        "mobility_component_is_higher_rate": mobility_category
        in {"HIGHER", "HIGHEST", "HIGH"},
        "mobility_component_is_lower_rate": mobility_category in {"LOWER", "LOW"},
    }


def project_pension_credit_final_inputs(row: Any) -> dict[str, Any]:
    return {
        "pension_credit_entitlement_for_year": money(
            row_value(row, "pension_credit_entitlement", 0)
        ),
        "person_or_partner_would_claim_pension_credit": bool_row_value(
            row, "would_claim_pc", False
        ),
    }


def project_esa_income_final_inputs(row: Any) -> dict[str, Any]:
    return {
        "reported_income_related_esa_for_year": money(
            row_value(row, "esa_income_reported_for_year", 0)
        ),
        "income_related_esa_tariff_income_for_year": money(
            row_value(row, "esa_income_tariff_income", 0)
        ),
        "income_related_esa_eligible": bool_row_value(
            row, "esa_income_eligible", False
        ),
    }


def project_pension_credit_inputs(row: Any) -> dict[str, Any]:
    relation_type = str(row_value(row, "relation_type", "")).upper()
    is_couple = bool(row_value(row, "is_couple", False)) or relation_type == "COUPLE"
    severe_disability_addition = (
        money(row_value(row, "severe_disability_minimum_guarantee_addition", 0))
        / WEEKS_IN_YEAR
    )
    num_carers = int(money(row_value(row, "num_carers", 0)))
    return {
        "claimant_is_prisoner": False,
        "member_of_religious_order_fully_maintained_by_order": False,
        "claimant_has_partner": is_couple,
        "treated_as_severely_disabled_person_under_schedule_i_part_i_paragraph_1": severe_disability_addition
        > 0,
        "severe_disability_couple_rate_conditions_satisfied": severe_disability_addition
        > 100,
        "paragraph_4_of_part_ii_of_schedule_i_satisfied_for_this_partner": num_carers
        > 0,
    }


def project_pension_credit_child_addition_inputs(row: Any) -> dict[str, Any]:
    return {
        "claimant_responsible_child_or_qualifying_young_person_count": int(
            money(row_value(row, "pc_child_addition_child_count", 0))
        ),
        "claimant_responsible_disabled_not_severely_disabled_child_or_qualifying_young_person_count": int(
            money(row_value(row, "pc_child_addition_standard_disabled_child_count", 0))
        ),
        "claimant_responsible_severely_disabled_child_or_qualifying_young_person_count": int(
            money(row_value(row, "pc_child_addition_severely_disabled_child_count", 0))
        ),
        "eldest_child_or_qualifying_young_person_born_before_6_april_2017": bool(
            row_value(row, "pc_child_addition_any_pre_2017_child", False)
        ),
    }


def project_state_pension_credit_guarantee_credit_inputs(
    row: Any,
) -> dict[str, Any]:
    standard_minimum_guarantee = money(row_value(row, "standard_minimum_guarantee", 0))
    minimum_guarantee = money(row_value(row, "minimum_guarantee", 0))
    return {
        "claimant_income": money(row_value(row, "pension_credit_income", 0)),
        "standard_minimum_guarantee": standard_minimum_guarantee,
        "prescribed_additional_amounts_applicable": max(
            0.0,
            minimum_guarantee - standard_minimum_guarantee,
        ),
        "claimant_is_entitled_to_guarantee_credit": bool(
            row_value(row, "is_guarantee_credit_eligible", False)
        ),
    }


def project_state_pension_credit_savings_credit_inputs(
    row: Any,
    *,
    parameters: dict[str, float],
) -> dict[str, Any]:
    relation_type = enum_name(row_value(row, "relation_type", "SINGLE")).upper()
    threshold_key = "COUPLE" if relation_type == "COUPLE" else "SINGLE"
    return {
        "claimant_satisfies_savings_credit_first_condition": bool(
            row_value(row, "is_savings_credit_eligible", False)
        ),
        "claimant_qualifying_income": money(row_value(row, "savings_credit_income", 0)),
        "claimant_income": money(row_value(row, "pension_credit_income", 0)),
        "savings_credit_threshold": parameters[
            f"savings_credit_threshold_{threshold_key.lower()}"
        ],
        "prescribed_percentage_for_amount_a": parameters["phase_in_rate"],
        "prescribed_percentage_for_amount_b": parameters["phase_out_rate"],
        "prescribed_percentage_for_maximum_savings_credit": parameters["phase_in_rate"],
        "standard_minimum_guarantee": money(
            row_value(row, "standard_minimum_guarantee", 0)
        ),
        "appropriate_minimum_guarantee": money(row_value(row, "minimum_guarantee", 0)),
        "maximum_savings_credit_taken_as_nil_by_regulations": False,
    }


def rows_for_surface(pe_data: dict[str, Any], surface: str) -> list[dict[str, Any]]:
    persons = pe_data["persons"]
    if surface == "child-benefit":
        return [
            row
            for row in persons
            if money(row_value(row, "child_benefit_respective_amount", 0)) > 0
        ]
    if surface == "child-benefit-final":
        return [
            row
            for row in pe_data.get("benunits", [])
            if money(row_value(row, "child_benefit_entitlement", 0)) > 0
            or money(row_value(row, "child_benefit", 0)) > 0
        ]
    if surface == "state-pension-final":
        return [
            row
            for row in persons
            if money(row_value(row, "state_pension", 0)) > 0
            or money(row_value(row, "state_pension_reported_data_year", 0)) > 0
        ]
    if surface in {"national-insurance-class-4", "national-insurance-class-4-final"}:
        return [
            row
            for row in persons
            if money(row_value(row, "self_employment_income", 0)) > 0
            or money(row_value(row, "ni_class_4_main", 0)) > 0
            or money(row_value(row, "ni_class_4", 0)) > 0
        ]
    if surface == "national-insurance-final":
        return [
            row
            for row in persons
            if money(row_value(row, "national_insurance", 0)) > 0
            or money(row_value(row, "ni_class_1_employee", 0)) > 0
            or money(row_value(row, "ni_class_2", 0)) > 0
            or money(row_value(row, "ni_class_3", 0)) > 0
            or money(row_value(row, "ni_class_4", 0)) > 0
        ]
    benunits = pe_data.get("benunits", [])
    if surface == "benefit-cap-relevant-amount":
        return [
            row
            for row in benunits
            if math.isfinite(money(row_value(row, "benefit_cap", math.inf)))
        ]
    if surface == "universal-credit-child-element":
        return [
            row
            for row in persons
            if money(row_value(row, "uc_individual_child_element", 0)) > 0
            or money(row_value(row, "uc_individual_disabled_child_element", 0)) > 0
            or money(row_value(row, "uc_individual_severely_disabled_child_element", 0))
            > 0
        ]
    if surface == "universal-credit-standard-allowance":
        return [
            row
            for row in benunits
            if money(row_value(row, "uc_standard_allowance", 0)) > 0
        ]
    if surface == "universal-credit-final":
        return [
            row
            for row in benunits
            if money(row_value(row, "universal_credit", 0)) > 0
            or money(row_value(row, "universal_credit_pre_benefit_cap", 0)) > 0
            or money(row_value(row, "benefit_cap_reduction", 0)) > 0
        ]
    if surface == "carers-allowance-final":
        return [
            row
            for row in persons
            if money(row_value(row, "carers_allowance", 0)) > 0
            or money(row_value(row, "carers_allowance_reported", 0)) > 0
            or money(row_value(row, "care_hours", 0)) >= 35
        ]
    if surface == "carer-support-payment-final":
        return [
            row
            for row in persons
            if money(row_value(row, "carer_support_payment", 0)) > 0
            or (
                enum_name(row_value(row, "country", "")).upper() == "SCOTLAND"
                and (
                    money(row_value(row, "carers_allowance_reported", 0)) > 0
                    or money(row_value(row, "care_hours", 0)) >= 35
                )
            )
        ]
    if surface == "scottish-child-payment-final":
        return [
            row
            for row in persons
            if money(row_value(row, "scottish_child_payment", 0)) > 0
            or bool_row_value(row, "is_scp_eligible", False)
            or bool_row_value(row, "would_claim_scp", False)
        ]
    if surface == "severe-disablement-allowance-final":
        return [
            row
            for row in persons
            if money(row_value(row, "sda", 0)) > 0
            or money(row_value(row, "sda_reported", 0)) > 0
        ]
    if surface == "disability-living-allowance-final":
        return [
            row
            for row in persons
            if money(row_value(row, "age", 999)) < 16
            and (
                money(row_value(row, "dla", 0)) > 0
                or money(row_value(row, "dla_sc", 0)) > 0
                or money(row_value(row, "dla_m", 0)) > 0
                or enum_name(row_value(row, "dla_sc_category", "NONE")).upper()
                != "NONE"
                or enum_name(row_value(row, "dla_m_category", "NONE")).upper() != "NONE"
            )
        ]
    if surface == "pension-credit-final":
        return [
            row
            for row in benunits
            if money(row_value(row, "pension_credit", 0)) > 0
            or money(row_value(row, "pension_credit_entitlement", 0)) > 0
        ]
    if surface == "esa-income-final":
        return [
            row
            for row in benunits
            if money(row_value(row, "esa_income", 0)) > 0
            or money(row_value(row, "esa_income_reported_for_year", 0)) > 0
            or money(row_value(row, "esa_income_tariff_income", 0)) > 0
        ]
    if surface == "housing-benefit-final":
        return [
            row
            for row in benunits
            if money(row_value(row, "housing_benefit", 0)) > 0
            or money(row_value(row, "housing_benefit_pre_benefit_cap", 0)) > 0
            or money(row_value(row, "benefit_cap_reduction", 0)) > 0
        ]
    if surface == "universal-credit-lcwra-element":
        return [
            row for row in benunits if money(row_value(row, "uc_LCWRA_element", 0)) > 0
        ]
    if surface == "universal-credit-carer-element":
        return [
            row for row in benunits if money(row_value(row, "uc_carer_element", 0)) > 0
        ]
    if surface == "universal-credit-childcare-cap":
        return [
            row
            for row in benunits
            if money(row_value(row, "uc_maximum_childcare_element_amount", 0)) > 0
        ]
    if SURFACE_SPECS[surface].entity == "benunit":
        return benunits
    return persons


def compare_outputs(
    *,
    pe_data: dict[str, Any],
    axiom_outputs_by_surface: dict[str, list[dict[str, Any]]],
    tolerance: float,
    relative_tolerance: float,
) -> UKEFRSComparisonReport:
    mismatches: list[UKEFRSComparisonRow] = []
    oracle_divergences: list[UKEFRSOracleDivergence] = []
    summary: dict[str, dict[str, Any]] = {
        f"{surface}:{name}": {
            "surface": surface,
            "output": name,
            "compared": 0,
            "mismatches": 0,
            "oracle_divergences": 0,
            "max_abs_diff": 0.0,
            "max_relative_diff": 0.0,
        }
        for surface, spec in SURFACE_SPECS.items()
        if surface in axiom_outputs_by_surface
        for name in spec.outputs
    }
    compared_values = 0
    for surface, axiom_outputs in axiom_outputs_by_surface.items():
        output_specs = SURFACE_SPECS[surface].outputs
        persons = rows_for_surface(pe_data, surface)
        if len(axiom_outputs) != len(persons):
            raise ValueError(
                f"{surface} produced {len(axiom_outputs):,} Axiom result rows "
                f"for {len(persons):,} PolicyEngine rows"
            )
        for index, result in enumerate(axiom_outputs):
            pe_row = persons[index]
            entity_id = entity_id_for_surface(surface, pe_row)
            outputs = result.get("outputs") or {}
            for name, spec in output_specs.items():
                if not output_applies(spec, pe_row):
                    continue
                axiom_value = output_number(outputs.get(spec["axiom"]))
                pe_value = policyengine_output_value(spec, pe_row)
                diff = axiom_value - pe_value
                abs_diff = abs(diff)
                compared_values += 1
                summary_key = f"{surface}:{name}"
                summary[summary_key]["compared"] += 1
                summary[summary_key]["max_abs_diff"] = max(
                    summary[summary_key]["max_abs_diff"], abs_diff
                )
                summary[summary_key]["max_relative_diff"] = max(
                    summary[summary_key]["max_relative_diff"],
                    relative_diff(axiom_value, pe_value),
                )
                if not within_tolerance(
                    axiom_value,
                    pe_value,
                    absolute_tolerance=float(spec.get("tolerance", tolerance)),
                    relative_tolerance=relative_tolerance,
                ):
                    divergence = known_policyengine_divergence(
                        surface=surface,
                        output=name,
                        entity_id=entity_id,
                        axiom_value=axiom_value,
                        policyengine_value=pe_value,
                        diff=diff,
                        pe_row=pe_row,
                    )
                    if divergence is not None:
                        summary[summary_key]["oracle_divergences"] += 1
                        oracle_divergences.append(divergence)
                    else:
                        summary[summary_key]["mismatches"] += 1
                        mismatches.append(
                            UKEFRSComparisonRow(
                                surface=surface,
                                entity_id=entity_id,
                                output=name,
                                axiom=axiom_value,
                                policyengine=pe_value,
                                diff=diff,
                            )
                        )
    return UKEFRSComparisonReport(
        compared_persons=len(pe_data["person_ids"]),
        compared_benunits=len(pe_data.get("benunit_ids", [])),
        compared_values=compared_values,
        mismatches=mismatches,
        oracle_divergences=oracle_divergences,
        output_summary=list(summary.values()),
        dataset_identity=pe_data.get("dataset_identity") or None,
        skipped_surfaces=SKIPPED_SURFACES,
        projection_notes=[
            "Personal allowance projection supplies validation-population adjusted net income "
            "net of PolicyEngine's gift_aid_grossed_up taper adjustment, because "
            "PolicyEngine UK applies that subtraction inside its personal "
            "allowance formula.",
            "The current projection treats validation-population people as making a claim and "
            "meeting the Section 56 residence/citizenship-condition boundary "
            "facts, matching the usual PolicyEngine UK personal allowance "
            "surface until those upstream legal predicates are encoded.",
            "National Insurance Class 1 comparison projects annual PolicyEngine "
            "NI Class 1 income into a representative tax week, supplies the "
            "PolicyEngine weekly primary threshold and upper earnings limit, "
            "compares RuleSpec's weekly section 8 aggregate output against "
            "PolicyEngine's annual ni_class_1_employee divided by 52, and "
            "also compares the same aggregate against PolicyEngine's "
            "ni_employee wrapper because PE-UK defines ni_employee as an "
            "aggregate containing only ni_class_1_employee. It "
            "compares the main/additional component outputs on ni_liable rows "
            "because PolicyEngine's component formulas are not masked by that "
            "liability predicate.",
            "Child Benefit comparison filters to positive PolicyEngine "
            "child_benefit_respective_amount rows, divides that annualized "
            "PolicyEngine output by 52 to compare against the RuleSpec weekly "
            "rate, and projects the eldest-child branch from "
            "child_benefit_child_index.",
            "Child Benefit relationship-coordination, voluntary-organisation, "
            "specified-benefit, and polygamous-marriage branches are projected "
            "false because PolicyEngine UK's child_benefit_respective_amount "
            "does not expose those legal predicates separately.",
            "Final Child Benefit comparison builds the section 141 family-to-child "
            "relation from positive PolicyEngine child_benefit_respective_amount "
            "person rows, projects PolicyEngine UK's would_claim_child_benefit "
            "receipt gate as an explicit input leaf, and compares the resulting "
            "weekly amount with PolicyEngine's annual child_benefit divided by 52.",
            "Universal Credit Regulation 80A benefit-cap relevant-amount "
            "comparison filters to finite PolicyEngine benefit_cap rows, "
            "divides the annual PE cap by 12, and projects the annual-limit "
            "case from PolicyEngine's num_adults, num_children, and "
            "benunit_region. PolicyEngine uses infinity for exempt benunits, "
            "which are outside the finite relevant-amount comparison.",
            "Pension Credit standard minimum guarantee comparison runs at "
            "benefit-unit level, divides PolicyEngine's annual output by 52, "
            "and projects claimant_has_partner from PolicyEngine's relation_type "
            "or is_couple. Prisoner and fully-maintained religious-order branches "
            "are projected false because those legal predicates are not exposed "
            "in the validation population.",
            "Pension Credit carer additions compare RuleSpec's per-partner "
            "amount against PolicyEngine's annual aggregate carer addition "
            "divided by num_carers and 52. The validation population has no positive "
            "severe-disability addition rows, so that branch is currently a "
            "zero-row guard rather than a positive-eligibility validation.",
            "Pension Credit Schedule IIA child-addition comparison projects "
            "PolicyEngine person-level child-or-qualifying-young-person, "
            "birth-year, and disability-benefit outputs into benefit-unit "
            "counts and the eldest-child-before-6-April-2017 flag, then "
            "compares the weekly RuleSpec aggregate against PolicyEngine's "
            "annual child_minimum_guarantee_addition divided by 52.",
            "State Pension Credit Act section 1 qualifying-age comparison "
            "queries RuleSpec's day-level qualifying_age on a representative "
            "day and supplies PolicyEngine's annual state_pension_age for both "
            "the pensionable-age leaf and the woman-born-same-day leaf. The "
            "same projection compares the attained-age judgment against "
            "PolicyEngine's is_SP_age boolean. Current PolicyEngine UK "
            "data exposes the modern equalized-age surface rather than "
            "historical sex-specific age transitions.",
            "State Pension Credit Act section 2 guarantee-credit comparison "
            "projects PolicyEngine's annual minimum_guarantee into the "
            "statutory appropriate minimum guarantee by supplying "
            "standard_minimum_guarantee and the remaining positive prescribed "
            "additional amount, and gates the amount with PolicyEngine's "
            "is_guarantee_credit_eligible predicate.",
            "State Pension Credit Act section 3 savings-credit comparison "
            "projects PolicyEngine's annual savings_credit_income as qualifying "
            "income, pension_credit_income as claimant income, "
            "standard_minimum_guarantee for the maximum-credit cap, and "
            "minimum_guarantee for the amount B reduction.",
            "Universal Credit Regulation 36 comparisons treat the generated "
            "RuleSpec outputs as component table amounts. PolicyEngine annual "
            "Populace component outputs are divided by 12, and Populace category "
            "variables select the matching standard-allowance, child-element, "
            "carer, LCWRA, and childcare-cap rows.",
            "Welfare Reform Act 2012 section 8 Universal Credit award "
            "comparison projects annual PolicyEngine component outputs into "
            "monthly section 8 maximum-amount buckets, gates those buckets by "
            "PolicyEngine's is_uc_eligible predicate to match uc_maximum_amount, "
            "and projects PolicyEngine's capped uc_income_reduction as the "
            "prescribed income deduction because PolicyEngine exposes the final "
            "deduction rather than the exact statutory earned/unearned split. "
            "The final section 8 award amount is compared against "
            "max(uc_maximum_amount - uc_income_reduction, 0), before "
            "PolicyEngine's would_claim_uc take-up gate.",
            "PolicyEngine-aligned Universal Credit final comparison projects "
            "annual universal_credit_pre_benefit_cap and annual "
            "benefit_cap_reduction into a final annual wrapper matching "
            "PolicyEngine UK's universal_credit amount after the would_claim_uc "
            "gate and benefit-cap reduction.",
            "PolicyEngine-aligned Carer's Allowance final comparison projects "
            "PolicyEngine UK's country and reported Carer's Allowance receipt "
            "into a final annual wrapper that uses the RuleSpec weekly rate, "
            "age gate, and 35-hour care threshold. Current Populace care_hours "
            "is zero on reported-receipt rows, so positive PolicyEngine or "
            "reported receipt is projected to the statutory minimum care "
            "hours and qualifying-disability-benefit fact; source age "
            "divergences remain visible.",
            "PolicyEngine-aligned Carer Support Payment and Scottish Child "
            "Payment final comparisons project PolicyEngine final-award or "
            "reported-receipt gates into source-shaped runtime facts because "
            "PolicyEngine does not expose every underlying eligibility and "
            "take-up predicate separately in the Populace oracle data.",
            "PolicyEngine-aligned Disability Living Allowance final comparison "
            "projects PolicyEngine UK's DLA self-care and mobility category "
            "enums into boolean category leaves for under-16 rows, then "
            "compares selected weekly components and the final annual "
            "aggregate. Adult legacy DLA rows are outside this GOV.UK child "
            "DLA wrapper and are treated as missing coverage rather than "
            "included in the final comparison.",
            "When a local UK .h5 predates the PolicyEngine UK disability "
            "category-input migration, the oracle derives PIP, DLA, and "
            "Attendance Allowance category inputs in memory from reported "
            "amount columns using the policyengine-uk-data category threshold "
            "rule; it does not rewrite the local dataset.",
            "Welfare Reform Act 2012 section 11 Universal Credit housing-costs "
            "comparison projects PolicyEngine's annual uc_housing_costs_element "
            "into the monthly amount determined or calculated by regulations, "
            "with ordinary Great Britain residential-accommodation eligibility "
            "predicates projected true and exception/timing predicates false.",
            "Universal Credit Regulation 22 work-allowance comparison projects "
            "PolicyEngine's is_uc_work_allowance_eligible, num_adults, "
            "num_children, and uc_housing_costs_element into the statutory "
            "higher/lower work-allowance case split, then compares the monthly "
            "RuleSpec allowance against PolicyEngine's annual uc_work_allowance "
            "divided by 12.",
            "Universal Credit Regulation 22 income-deduction comparison "
            "projects PolicyEngine's annual uc_earned_income divided by 12 as "
            "the post-work-allowance amount subject to taper, adds back the "
            "monthly uc_work_allowance when Regulation 22 specifies one to "
            "supply the pre-allowance earned-income leaf, projects annual "
            "uc_unearned_income divided by 12 as the unearned-income leaf, and "
            "compares the final Regulation 22 deduction to uc_income_reduction "
            "only on rows where PolicyEngine's maximum-credit cap is not binding "
            "and PolicyEngine's negative-unearned-income treatment does not "
            "differ from Regulation 22's non-negative unearned-income "
            "deduction.",
            "Universal Credit Regulation 18 assessable-capital comparison "
            "projects PolicyEngine's benefit-unit uc_assessable_capital stock "
            "into the claimant capital leaf, with other-member inclusion "
            "projected to zero because PolicyEngine already resolves household "
            "capital allocation, reported-capital overrides, and exclusions "
            "upstream.",
            "Universal Credit Regulation 72 tariff-income comparison projects "
            "PolicyEngine's annual uc_assessable_capital stock into the "
            "RuleSpec person_capital leaf, projects capital disregards and "
            "actual-capital-income exceptions false, compares the monthly "
            "RuleSpec tariff income against PolicyEngine's annual "
            "uc_tariff_income divided by 12, and only counts rows where "
            "PolicyEngine defines UC eligibility.",
            "State Pension Credit Regulations 2002 Regulation 15 deemed-income "
            "comparison projects PolicyEngine's benefit-unit "
            "pension_credit_assessable_capital stock into the claimant capital "
            "leaf, projects the Regulation 17(8) capital-disregard exception "
            "false because PolicyEngine already applies capital-source "
            "exclusions upstream, and compares weekly RuleSpec deemed income "
            "against PolicyEngine's annual pension_credit_deemed_income "
            "divided by 52.",
            "ESA, JSA, Income Support, and working-age Housing Benefit "
            "tariff-income comparisons project PolicyEngine's corresponding "
            "assessable-capital stock into the claimant-capital leaf, project "
            "the prescribed-accommodation or prescribed-circumstances branch "
            "false because PE does not expose those legal predicates, and "
            "compare only rows at or below the GBP 16,000 statutory capital "
            "limit. PolicyEngine computes its internal tariff variable beyond "
            "that limit, but those rows are outside the direct tariff-income "
            "oracle surface.",
            "Pension-age Housing Benefit tariff-income comparison projects "
            "PolicyEngine's housing_benefit_assessable_capital into the "
            "claimant-capital leaf, projects the regulation 44(2) "
            "capital-disregard exception false because PE applies capital "
            "exclusions upstream, and compares non-guarantee-credit "
            "pension-age rows against PolicyEngine's annual "
            "housing_benefit_tariff_income divided by 52.",
            "Universal Credit Regulation 34 childcare-costs element comparison "
            "projects PolicyEngine's annual uc_childcare_element into monthly "
            "relevant childcare charges by reversing the statutory 85 percent "
            "reimbursement rate, supplies PolicyEngine's annual "
            "uc_maximum_childcare_element_amount divided by 12 as the regulation "
            "36 maximum, and projects excluded, reimbursed, and other-support "
            "amounts to zero.",
            "Universal Credit Regulation 32 childcare work-condition comparison "
            "aggregates PolicyEngine person-level is_adult and in_work outputs "
            "within each benefit unit, projects statutory treated-as-in-work and "
            "other-unable-to-provide-childcare exceptions false, and compares "
            "the resulting RuleSpec work-condition judgment against "
            "PolicyEngine's uc_childcare_work_condition.",
            "The protected LCWRA Regulation 36 table amount is compared only "
            "when PolicyEngine exposes the raw protected amount. Current "
            "PolicyEngine UK Populace outputs apply the July 2025 UC rebalancing "
            "scenario for existing claimants, so those rebalanced health-element "
            "values are not treated as the same surface.",
            "Income Tax Act 2007 section 23 net-income comparison projects "
            "PolicyEngine UK's adjusted_net_income into section 24 reliefs only "
            "for rows with non-negative income components where adjusted net "
            "income does not exceed total income. Rows with loss semantics are "
            "skipped because RuleSpec section 23 net_income cannot exceed the "
            "section 23 total_income output.",
            "Income Tax Act 2007 section 23 final-liability comparison collapses "
            "PolicyEngine's income_tax_additions into the RuleSpec step-4 tax "
            "input and PolicyEngine's income_tax_subtractions into the section "
            "26 reductions input, because PolicyEngine exposes final income_tax "
            "and aggregate additive/subtractive components rather than exact "
            "section 23 step buckets.",
            "Income Tax Act 2007 section 11D savings-income comparison projects "
            "PolicyEngine's taxable_savings_interest_income net of "
            "received_allowances_savings_income, then lets "
            "savings_starter_rate_income and savings_allowance consume rate-band "
            "capacity before the remaining section 11D savings income starts. "
            "It uses UK income-tax thresholds and savings rates from "
            "PolicyEngine parameters to compare the section 11D band amounts "
            "and aggregate savings income tax, with a 25p output tolerance for "
            "Populace float precision in PolicyEngine's savings-income arrays.",
            "Income Tax Act 2007 section 13 dividend-income comparison projects "
            "PolicyEngine's dividend tax formula directly: savings after income "
            "allowances occupies rate-band capacity before dividends, the used "
            "dividend allowance occupies nil-rate dividend band capacity, and "
            "the remaining taxed_dividend_income is compared as the section 13 "
            "charged amount and aggregate dividend income tax.",
        ],
    )


def entity_id_for_surface(surface: str, row: Any) -> str:
    if SURFACE_SPECS[surface].entity == "benunit":
        return benunit_entity_id(int(row_value(row, "benunit_id")))
    return person_entity_id(int(row_value(row, "person_id")))


def policyengine_output_value(spec: dict[str, Any], row: Any) -> float:
    raw_value = policyengine_raw_output_value(spec, row)
    if spec.get("pe_transform") == "annual_to_weekly":
        return raw_value / WEEKS_IN_YEAR
    if spec.get("pe_transform") == "annual_to_weekly_per_carer":
        return (
            raw_value
            / WEEKS_IN_YEAR
            / max(1, int(money(row_value(row, "num_carers", 0))))
        )
    if spec.get("pe_transform") == "annual_to_monthly":
        return raw_value / MONTHS_IN_YEAR
    return raw_value


def policyengine_raw_output_value(spec: dict[str, Any], row: Any) -> float:
    expression = spec.get("pe_expression")
    if expression == "uc_award_before_takeup":
        maximum_amount = money(row_value(row, "uc_maximum_amount", 0))
        income_reduction = money(row_value(row, "uc_income_reduction", 0))
        return max(0.0, maximum_amount - income_reduction)
    if expression is not None:
        raise ValueError(f"unsupported PolicyEngine expression: {expression!r}")
    return money(row_value(row, spec["pe"]))


def output_applies(spec: dict[str, Any], row: Any) -> bool:
    applies = spec.get("applies")
    if applies is None:
        return True
    if applies == "positive_pe_output":
        return policyengine_output_value(spec, row) > 0
    if applies == "income_tax_net_income_comparable":
        return all(
            money(row_value(row, name, 0)) >= 0
            for name in INCOME_TAX_INCOME_BASE_COMPONENTS
        ) and money(row_value(row, "adjusted_net_income", 0)) <= money(
            row_value(row, "total_income", 0)
        )
    if applies == "non_scottish_income_tax":
        return not bool(row_value(row, "pays_scottish_income_tax", False))
    if applies == "uc_first_child_element":
        return (
            policyengine_output_value(spec, row) > 0
            and int(row_value(row, "uc_child_index", -1)) == 1
            and bool(row_value(row, "uc_is_child_born_before_child_limit", False))
        )
    if applies == "uc_subsequent_child_element":
        return policyengine_output_value(spec, row) > 0 and not output_applies(
            {**spec, "applies": "uc_first_child_element"},
            row,
        )
    if applies == "uc_lcwra_standard_amount":
        monthly_value = policyengine_output_value(spec, row)
        return 0 < monthly_value < 300
    if applies == "uc_lcwra_higher_amount":
        monthly_value = policyengine_output_value(spec, row)
        expected = UNIVERSAL_CREDIT_2026_RULESPEC_RATES[
            "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant"
        ]
        return math.isclose(monthly_value, expected, abs_tol=0.01)
    if applies == "uc_childcare_two_or_more_children":
        return int(row_value(row, "uc_childcare_element_eligible_children", 0)) >= 2
    if applies == "uc_income_reduction_uncapped":
        annual_uncapped_reduction = UNIVERSAL_CREDIT_2026_RULESPEC_RATES[
            "earned_income_taper_rate"
        ] * money(row_value(row, "uc_earned_income", 0)) + max(
            0.0,
            money(row_value(row, "uc_unearned_income", 0)),
        )
        pe_reduction = money(row_value(row, "uc_income_reduction", 0))
        maximum_credit = money(row_value(row, "uc_maximum_amount", 0))
        return (
            pe_reduction >= 0
            and annual_uncapped_reduction <= maximum_credit + 0.01
            and math.isclose(pe_reduction, annual_uncapped_reduction, abs_tol=0.01)
        )
    if applies == "uc_tariff_income_defined":
        return bool(row_value(row, "is_uc_eligible", False))
    if applies == "legacy_capital_tariff_income_defined":
        return money(row_value(row, spec["capital_pe"], 0)) <= 16_000
    if applies == "housing_benefit_working_age_tariff_income_defined":
        return not bool(row_value(row, "housing_benefit_any_over_sp_age", False)) and (
            money(row_value(row, spec["capital_pe"], 0)) <= 16_000
        )
    if applies == "housing_benefit_pension_age_tariff_income_defined":
        return bool(row_value(row, "housing_benefit_any_over_sp_age", False)) and (
            money(row_value(row, "guarantee_credit", 0)) <= 0
        )
    if isinstance(applies, tuple) and len(applies) == 2:
        name, expected = applies
        value = row_value(row, name)
        if isinstance(expected, str):
            return enum_name(value) == expected
        return value == expected
    raise ValueError(f"unsupported output applicability rule: {applies!r}")


def enum_name(value: Any) -> str:
    if hasattr(value, "name"):
        return str(value.name)
    text = str(value)
    if "." in text:
        return text.rsplit(".", 1)[-1]
    return text


def known_policyengine_divergence(
    *,
    surface: str,
    output: str,
    entity_id: str,
    axiom_value: float,
    policyengine_value: float,
    diff: float,
    pe_row: Any | None = None,
) -> UKEFRSOracleDivergence | None:
    if (
        surface == "child-benefit"
        and output == "child_benefit_weekly_rate"
        and 0 < diff < 0.2
        and (
            math.isclose(axiom_value, 27.05, abs_tol=1e-9)
            or math.isclose(axiom_value, 17.90, abs_tol=1e-9)
        )
        and (
            math.isclose(policyengine_value, 26.935709699992934, abs_tol=0.005)
            or math.isclose(policyengine_value, 17.836506423219888, abs_tol=0.005)
        )
    ):
        return UKEFRSOracleDivergence(
            surface=surface,
            entity_id=entity_id,
            output=output,
            axiom=axiom_value,
            policyengine=policyengine_value,
            diff=diff,
            reason=(
                "PolicyEngine UK currently uses forecast-indexed 2026 Child "
                "Benefit amounts instead of the published 2026-27 weekly rates."
            ),
            issue_url="https://github.com/PolicyEngine/policyengine-uk/issues/1739",
        )
    if (
        surface == "pension-credit"
        and output == "standard_minimum_guarantee"
        and 0 < diff < 15
        and (
            math.isclose(axiom_value, 238.00, abs_tol=1e-9)
            or math.isclose(axiom_value, 363.25, abs_tol=1e-9)
        )
        and (
            math.isclose(policyengine_value, 229.3929826081932, abs_tol=0.01)
            or math.isclose(policyengine_value, 350.12286608501375, abs_tol=0.01)
        )
    ):
        return UKEFRSOracleDivergence(
            surface=surface,
            entity_id=entity_id,
            output=output,
            axiom=axiom_value,
            policyengine=policyengine_value,
            diff=diff,
            reason=(
                "PolicyEngine UK currently uses forecast-indexed 2026 Pension "
                "Credit guarantee amounts instead of the published 2026-27 "
                "weekly rates."
            ),
            issue_url="https://github.com/PolicyEngine/policyengine-uk/issues/1740",
        )
    if (
        surface == "pension-credit"
        and output in {"severe_disability_additional_amount", "carer_additional_amount"}
        and pension_credit_additional_amount_matches_published_rate(output, axiom_value)
        and policyengine_value > 0
        and 0 < abs(diff) < 5
    ):
        return UKEFRSOracleDivergence(
            surface=surface,
            entity_id=entity_id,
            output=output,
            axiom=axiom_value,
            policyengine=policyengine_value,
            diff=diff,
            reason=(
                "PolicyEngine UK currently uses forecast-indexed 2026 "
                "Pension Credit additional amounts instead of the published "
                "2026-27 weekly rates."
            ),
            issue_url="https://github.com/PolicyEngine/policyengine-uk/issues/1742",
        )
    expected_uc_rate = UNIVERSAL_CREDIT_2026_RULESPEC_RATES.get(output)
    if (
        surface.startswith("universal-credit-")
        and expected_uc_rate is not None
        and math.isclose(axiom_value, expected_uc_rate, abs_tol=1e-9)
        and policyengine_value > 0
        and 0 < abs(diff) < 75
    ):
        return UKEFRSOracleDivergence(
            surface=surface,
            entity_id=entity_id,
            output=output,
            axiom=axiom_value,
            policyengine=policyengine_value,
            diff=diff,
            reason=(
                "PolicyEngine UK currently uses forecast-indexed 2026 "
                "Universal Credit Regulation 36 amounts instead of the "
                "published 2026-27 monthly rates."
            ),
            issue_url="https://github.com/PolicyEngine/policyengine-uk/issues/1741",
        )
    return None


def pension_credit_additional_amount_matches_published_rate(
    output: str,
    axiom_value: float,
) -> bool:
    if output == "carer_additional_amount":
        return math.isclose(axiom_value, 48.15, abs_tol=1e-9)
    if output == "severe_disability_additional_amount":
        return math.isclose(axiom_value, 86.05, abs_tol=1e-9) or math.isclose(
            axiom_value,
            172.10,
            abs_tol=1e-9,
        )
    return False


def print_report(
    report: UKEFRSComparisonReport,
    *,
    tolerance: float,
    relative_tolerance: float,
) -> None:
    print("PolicyEngine UK Populace comparison")
    identity_line = format_dataset_identity(report.dataset_identity)
    if identity_line:
        print(identity_line)
    print(f"Compared persons: {report.compared_persons:,}")
    print(f"Compared benefit units: {report.compared_benunits:,}")
    print(f"Compared values: {report.compared_values:,}")
    print(f"Tolerance: {tolerance:g}")
    print(f"Relative tolerance: {relative_tolerance:g}")
    print(f"Mismatches: {len(report.mismatches):,}")
    print(f"Known PolicyEngine oracle divergences: {len(report.oracle_divergences):,}")
    print()
    print("By output:")
    for item in report.output_summary:
        print(
            f"  - {item['surface']}:{item['output']}: "
            f"{item['mismatches']:,}/{item['compared']:,} mismatch, "
            f"{item['oracle_divergences']:,} known PE divergence, "
            f"max_abs_diff={item['max_abs_diff']:.2f}, "
            f"max_rel_diff={item['max_relative_diff']:.2g}"
        )
    if report.mismatches:
        print()
        print("Top mismatches:")
        for row in sorted(
            report.mismatches, key=lambda item: abs(item.diff), reverse=True
        )[:20]:
            print(
                f"  - entity={row.entity_id} {row.surface}:{row.output}: "
                f"axiom={row.axiom:.2f} pe={row.policyengine:.2f} "
                f"diff={row.diff:.2f}"
            )
    if report.oracle_divergences:
        print()
        print("Known PolicyEngine oracle divergences:")
        for row in sorted(
            report.oracle_divergences, key=lambda item: abs(item.diff), reverse=True
        )[:20]:
            print(
                f"  - entity={row.entity_id} {row.surface}:{row.output}: "
                f"axiom={row.axiom:.2f} pe={row.policyengine:.2f} "
                f"diff={row.diff:.2f}; {row.issue_url}"
            )
    if report.skipped_surfaces:
        print()
        print("Skipped mapped UK surfaces:")
        for item in report.skipped_surfaces:
            print(f"  - {item['surface']}: {item['reason']}")
    print()
    print("Projection notes:")
    for note in report.projection_notes:
        print(f"  - {note}")


def table_records(table: Any) -> list[dict[str, Any]]:
    if isinstance(table, list):
        return [dict(row) for row in table]
    if isinstance(table, dict):
        keys = list(table)
        length = len(table[keys[0]]) if keys else 0
        return [{key: table[key][index] for key in keys} for index in range(length)]
    if hasattr(table, "to_dict"):
        return table.to_dict("records")
    raise TypeError(f"unsupported table type: {type(table).__name__}")


def row_value(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    if hasattr(row, "get"):
        return row.get(name, default)
    return getattr(row, name, default)


def bool_row_value(row: Any, name: str, default: bool = False) -> bool:
    value = row_value(row, name, default)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "nan", "none", "null"}:
            return default
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    try:
        if math.isnan(value):
            return default
    except TypeError:
        pass
    return bool(value)


def tax_year_interval(year: int) -> dict[str, str]:
    return {
        "period_kind": "tax_year",
        "start": f"{year:04d}-01-01",
        "end": f"{year:04d}-12-31",
    }


def uk_tax_year_interval(year: int) -> dict[str, str]:
    return {
        "period_kind": "tax_year",
        "start": f"{year:04d}-04-06",
        "end": f"{year + 1:04d}-04-05",
    }


def day_interval(year: int) -> dict[str, str]:
    return {
        "period_kind": "custom",
        "name": "day",
        "start": f"{year:04d}-04-06",
        "end": f"{year:04d}-04-06",
    }


def benefit_week_interval(year: int) -> dict[str, str]:
    return {
        "period_kind": "custom",
        "name": "benefit_week",
        "start": f"{year:04d}-04-06",
        "end": f"{year:04d}-04-12",
    }


def tax_week_interval(year: int) -> dict[str, str]:
    return {
        "period_kind": "custom",
        "name": "tax_week",
        "start": f"{year:04d}-04-06",
        "end": f"{year:04d}-04-12",
    }


def benefit_month_interval(year: int) -> dict[str, str]:
    return {
        "period_kind": "month",
        "name": "benefit_month",
        "start": f"{year:04d}-04-01",
        "end": f"{year:04d}-04-30",
    }


def person_entity_id(person_id: int) -> str:
    return f"person_{person_id}"


def income_tax_component_entity_id(person_id: int, component: str) -> str:
    return f"{person_entity_id(person_id)}_income_{component}"


def benunit_entity_id(benunit_id: int) -> str:
    return f"benunit_{benunit_id}"


def resolve_workspace_root(root: Path | None) -> Path:
    if root is not None:
        return root.resolve()
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents, Path.home() / "TheAxiomFoundation"]:
        if (candidate / "rulespec-uk").exists() and (
            candidate / "axiom-rules-engine"
        ).exists():
            return candidate
    return cwd


def require_policyengine_uk_versions(command: str = "uk-populace-compare") -> None:
    try:
        policyengine_uk_version = version("policyengine-uk")
    except PackageNotFoundError as exc:
        raise SystemExit(policyengine_uk_install_message(command)) from exc
    if _version_tuple(policyengine_uk_version) < _version_tuple(
        MIN_POLICYENGINE_UK_VERSION
    ):
        raise SystemExit(
            f"policyengine-uk>={MIN_POLICYENGINE_UK_VERSION} required; found "
            f"{policyengine_uk_version}. {policyengine_uk_install_message(command)}"
        )


def policyengine_uk_class_1_weekly_parameters(year: int) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    class_1 = (
        CountryTaxBenefitSystem()
        .parameters(f"{year:04d}-04-06")
        .gov.hmrc.national_insurance.class_1
    )
    return {
        "primary_threshold": money(class_1.thresholds.primary_threshold),
        "upper_earnings_limit": money(class_1.thresholds.upper_earnings_limit),
    }


def policyengine_uk_class_4_parameters(year: int) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    class_4 = (
        CountryTaxBenefitSystem()
        .parameters(f"{year:04d}-04-06")
        .gov.hmrc.national_insurance.class_4
    )
    return {
        "lower_profits_limit": money(class_4.thresholds.lower_profits_limit),
        "upper_profits_limit": money(class_4.thresholds.upper_profits_limit),
        "main_class_4_percentage": float(class_4.rates.main),
        "additional_class_4_percentage": float(class_4.rates.additional),
    }


def policyengine_uk_state_pension_parameters(
    *, year: int, data_year: int
) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    state_pension = CountryTaxBenefitSystem().parameters.gov.dwp.state_pension
    return {
        "data_year_basic_state_pension_weekly_rate": money(
            state_pension.basic_state_pension.amount(data_year)
        ),
        "data_year_full_new_state_pension_weekly_rate": money(
            state_pension.new_state_pension.amount(data_year)
        ),
        "state_pension_policy_uprating_factor": 1.0,
    }


def policyengine_uk_income_tax_section_10_parameters(year: int) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    uk_rates = (
        CountryTaxBenefitSystem()
        .parameters(f"{year:04d}-04-06")
        .gov.hmrc.income_tax.rates.uk
    )
    return {
        "basic_rate_limit": money(uk_rates.thresholds[1]),
        "higher_rate_limit": money(uk_rates.thresholds[2]),
        "basic_rate": money(uk_rates.rates[0]),
        "higher_rate": money(uk_rates.rates[1]),
        "additional_rate": money(uk_rates.rates[2]),
    }


def policyengine_uk_income_tax_section_11d_parameters(year: int) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    income_tax_rates = (
        CountryTaxBenefitSystem()
        .parameters(f"{year:04d}-04-06")
        .gov.hmrc.income_tax.rates
    )
    return {
        "basic_rate_limit": money(income_tax_rates.uk.thresholds[1]),
        "higher_rate_limit": money(income_tax_rates.uk.thresholds[2]),
        "savings_basic_rate": money(income_tax_rates.savings.basic),
        "savings_higher_rate": money(income_tax_rates.savings.higher),
        "savings_additional_rate": money(income_tax_rates.savings.additional),
    }


def policyengine_uk_income_tax_section_13_parameters(year: int) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    income_tax = (
        CountryTaxBenefitSystem().parameters(f"{year:04d}-04-06").gov.hmrc.income_tax
    )
    income_tax_rates = income_tax.rates
    return {
        "basic_rate_limit": money(income_tax_rates.uk.thresholds[1]),
        "higher_rate_limit": money(income_tax_rates.uk.thresholds[2]),
        "dividend_allowance": money(income_tax.allowances.dividend_allowance),
        "dividend_ordinary_rate": money(income_tax_rates.dividends.rates[0]),
        "dividend_upper_rate": money(income_tax_rates.dividends.rates[1]),
        "dividend_additional_rate": money(income_tax_rates.dividends.rates[2]),
    }


def policyengine_uk_savings_credit_parameters(year: int) -> dict[str, float]:
    require_policyengine_uk_versions()
    try:
        from policyengine_uk import CountryTaxBenefitSystem
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(policyengine_uk_install_message()) from exc

    savings_credit = (
        CountryTaxBenefitSystem()
        .parameters(f"{year:04d}-04-06")
        .gov.dwp.pension_credit.savings_credit
    )
    return {
        "savings_credit_threshold_single": money(savings_credit.threshold.SINGLE)
        * WEEKS_IN_YEAR,
        "savings_credit_threshold_couple": money(savings_credit.threshold.COUPLE)
        * WEEKS_IN_YEAR,
        "phase_in_rate": money(savings_credit.rate.phase_in),
        "phase_out_rate": money(savings_credit.rate.phase_out),
    }


def policyengine_uk_install_message(command: str = "uk-populace-compare") -> str:
    return (
        "Run with: "
        f"uv run --with {populace_data_requirement('uk')} "
        f"axiom-encode {command}"
    )


def log(message: str) -> None:
    print(message, file=sys.stderr)
