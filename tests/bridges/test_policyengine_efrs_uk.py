import argparse
import math
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace

import pytest

import axiom_oracles.bridges.efrs_uk as efrs_uk
from axiom_oracles.bridges.efrs_uk import (
    BENEFIT_CAP_REGULATION_80A_BASE,
    BENEFIT_CAP_RELEVANT_AMOUNT_OUTPUTS,
    CARER_SUPPORT_PAYMENT_FINAL_BASE,
    CARER_SUPPORT_PAYMENT_FINAL_OUTPUTS,
    CARERS_ALLOWANCE_FINAL_BASE,
    CARERS_ALLOWANCE_FINAL_OUTPUTS,
    CHILD_BENEFIT_BASE,
    CHILD_BENEFIT_FINAL_BASE,
    CHILD_BENEFIT_FINAL_OUTPUTS,
    CHILD_BENEFIT_OUTPUTS,
    CHILD_BENEFIT_SECTION_141_BASE,
    DLA_FINAL_BASE,
    DLA_FINAL_OUTPUTS,
    ESA_FINAL_BASE,
    ESA_FINAL_OUTPUTS,
    ESA_REGULATION_118_BASE,
    ESA_TARIFF_INCOME_OUTPUTS,
    HOUSING_BENEFIT_ENTITLEMENT_BASE,
    HOUSING_BENEFIT_ENTITLEMENT_OUTPUTS,
    HOUSING_BENEFIT_FINAL_BASE,
    HOUSING_BENEFIT_FINAL_OUTPUTS,
    HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_BASE,
    HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS,
    HOUSING_BENEFIT_REGULATION_52_BASE,
    HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS,
    INCOME_SUPPORT_REGULATION_53_BASE,
    INCOME_SUPPORT_TARIFF_INCOME_OUTPUTS,
    INCOME_TAX_INCOME_BASE_COMPONENTS,
    INCOME_TAX_INCOME_BASE_OUTPUTS,
    INCOME_TAX_SECTION_10_BASE,
    INCOME_TAX_SECTION_10_OUTPUTS,
    INCOME_TAX_SECTION_11D_BASE,
    INCOME_TAX_SECTION_11D_OUTPUTS,
    INCOME_TAX_SECTION_13_BASE,
    INCOME_TAX_SECTION_13_OUTPUTS,
    INCOME_TAX_SECTION_23_ADDITION_COMPONENTS,
    INCOME_TAX_SECTION_23_BASE,
    INCOME_TAX_SECTION_23_REDUCTION_COMPONENTS,
    JSA_REGULATION_116_BASE,
    JSA_TARIFF_INCOME_OUTPUTS,
    NATIONAL_INSURANCE_CLASS_1_OUTPUTS,
    NATIONAL_INSURANCE_CLASS_4_OUTPUTS,
    NATIONAL_INSURANCE_FINAL_OUTPUTS,
    NATIONAL_INSURANCE_REGULATION_100_BASE,
    NATIONAL_INSURANCE_REGULATION_100_OUTPUTS,
    NATIONAL_INSURANCE_SECTION_1_BASE,
    NATIONAL_INSURANCE_SECTION_8_BASE,
    NATIONAL_INSURANCE_SECTION_15_BASE,
    PENSION_CREDIT_BASE,
    PENSION_CREDIT_CHILD_ADDITION_OUTPUTS,
    PENSION_CREDIT_DEEMED_INCOME_OUTPUTS,
    PENSION_CREDIT_FINAL_BASE,
    PENSION_CREDIT_FINAL_OUTPUTS,
    PENSION_CREDIT_OUTPUTS,
    PENSION_CREDIT_REGULATION_15_BASE,
    PENSION_CREDIT_SCHEDULE_IIA_BASE,
    PERSONAL_ALLOWANCE_BASE,
    PERSONAL_ALLOWANCE_OUTPUTS,
    PERSONAL_ALLOWANCE_PROGRAM_PATH,
    PIP_FINAL_BASE,
    PIP_FINAL_OUTPUTS,
    SCOTTISH_CHILD_PAYMENT_FINAL_BASE,
    SCOTTISH_CHILD_PAYMENT_FINAL_OUTPUTS,
    SDA_FINAL_BASE,
    SDA_FINAL_OUTPUTS,
    STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS,
    STATE_PENSION_CREDIT_QUALIFYING_AGE_OUTPUTS,
    STATE_PENSION_CREDIT_SAVINGS_CREDIT_OUTPUTS,
    STATE_PENSION_CREDIT_SECTION_1_BASE,
    STATE_PENSION_CREDIT_SECTION_2_BASE,
    STATE_PENSION_CREDIT_SECTION_3_BASE,
    STATE_PENSION_FINAL_BASE,
    STATE_PENSION_FINAL_OUTPUTS,
    STUDENT_LOAN_REPAYMENT_BASE,
    STUDENT_LOAN_REPAYMENT_OUTPUTS,
    UNIVERSAL_CREDIT_ASSESSABLE_CAPITAL_OUTPUTS,
    UNIVERSAL_CREDIT_AWARD_OUTPUTS,
    UNIVERSAL_CREDIT_CHILD_ELEMENT_OUTPUTS,
    UNIVERSAL_CREDIT_CHILDCARE_ELEMENT_OUTPUTS,
    UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS,
    UNIVERSAL_CREDIT_FINAL_BASE,
    UNIVERSAL_CREDIT_FINAL_OUTPUTS,
    UNIVERSAL_CREDIT_HOUSING_COSTS_OUTPUTS,
    UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS,
    UNIVERSAL_CREDIT_LCWRA_OUTPUTS,
    UNIVERSAL_CREDIT_REGULATION_18_BASE,
    UNIVERSAL_CREDIT_REGULATION_22_BASE,
    UNIVERSAL_CREDIT_REGULATION_32_BASE,
    UNIVERSAL_CREDIT_REGULATION_34_BASE,
    UNIVERSAL_CREDIT_REGULATION_72_BASE,
    UNIVERSAL_CREDIT_STANDARD_ALLOWANCE_OUTPUTS,
    UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS,
    UNIVERSAL_CREDIT_WORK_ALLOWANCE_OUTPUTS,
    WEEKS_IN_YEAR,
    WELFARE_REFORM_ACT_SECTION_8_BASE,
    WELFARE_REFORM_ACT_SECTION_11_BASE,
    add_policyengine_uk_disability_categories_from_reported_amounts,
    build_benefit_cap_relevant_amount_request,
    build_carer_support_payment_final_request,
    build_carers_allowance_final_request,
    build_child_benefit_final_request,
    build_child_benefit_request,
    build_dla_final_request,
    build_pip_final_request,
    build_esa_income_final_request,
    build_esa_income_tariff_income_request,
    build_housing_benefit_entitlement_request,
    build_housing_benefit_final_request,
    build_housing_benefit_pension_age_tariff_income_request,
    build_housing_benefit_working_age_tariff_income_request,
    build_income_support_tariff_income_request,
    build_income_tax_income_base_request,
    build_income_tax_section_10_request,
    build_income_tax_section_11d_request,
    build_income_tax_section_13_request,
    build_jsa_income_tariff_income_request,
    build_national_insurance_class_1_request,
    build_national_insurance_class_4_final_request,
    build_national_insurance_class_4_request,
    build_national_insurance_final_request,
    build_pension_credit_child_addition_request,
    build_pension_credit_deemed_income_request,
    build_pension_credit_final_request,
    build_pension_credit_request,
    build_personal_allowance_request,
    build_scottish_child_payment_final_request,
    build_sda_final_request,
    build_state_pension_credit_guarantee_credit_request,
    build_state_pension_credit_qualifying_age_request,
    build_state_pension_credit_savings_credit_request,
    build_state_pension_final_request,
    build_student_loan_repayment_request,
    build_uk_efrs_coverage_report,
    build_uk_hbai_policy_coverage_report,
    build_universal_credit_assessable_capital_request,
    build_universal_credit_award_request,
    build_universal_credit_childcare_element_request,
    build_universal_credit_childcare_work_condition_request,
    build_universal_credit_final_request,
    build_universal_credit_housing_costs_request,
    build_universal_credit_income_deduction_request,
    build_universal_credit_request,
    build_universal_credit_tariff_income_request,
    build_universal_credit_work_allowance_request,
    compare_outputs,
    compare_uk_efrs,
    disability_category_from_reported_amounts,
    normalize_policyengine_entity,
    policyengine_benunit_variables_for_surfaces,
    policyengine_person_variables_for_surfaces,
    project_benefit_cap_relevant_amount_inputs,
    project_carer_support_payment_final_inputs,
    project_carers_allowance_final_inputs,
    project_child_benefit_inputs,
    project_dla_final_inputs,
    project_esa_income_final_inputs,
    project_esa_income_tariff_income_inputs,
    project_housing_benefit_final_inputs,
    project_housing_benefit_pension_age_tariff_income_inputs,
    project_housing_benefit_working_age_tariff_income_inputs,
    project_income_support_tariff_income_inputs,
    project_income_tax_income_base_components,
    project_income_tax_section_10_inputs,
    project_income_tax_section_11d_inputs,
    project_income_tax_section_13_inputs,
    project_income_tax_section_23_inputs,
    project_jsa_income_tariff_income_inputs,
    project_national_insurance_class_4_final_inputs,
    project_national_insurance_class_4_inputs,
    project_national_insurance_final_inputs,
    project_pension_credit_child_addition_inputs,
    project_pension_credit_deemed_income_inputs,
    project_pension_credit_final_inputs,
    project_pension_credit_inputs,
    project_personal_allowance_inputs,
    project_scottish_child_payment_final_inputs,
    project_sda_final_inputs,
    project_state_pension_credit_guarantee_credit_inputs,
    project_state_pension_credit_qualifying_age_inputs,
    project_state_pension_credit_savings_credit_inputs,
    project_state_pension_final_inputs,
    project_student_loan_repayment_inputs,
    project_universal_credit_assessable_capital_inputs,
    project_universal_credit_award_inputs,
    project_universal_credit_childcare_element_inputs,
    project_universal_credit_childcare_work_condition_inputs,
    project_universal_credit_final_inputs,
    project_universal_credit_housing_costs_inputs,
    project_universal_credit_income_deduction_inputs,
    project_universal_credit_tariff_income_inputs,
    project_universal_credit_work_allowance_inputs,
    require_policyengine_uk_versions,
    select_person_indices,
)


def decimal_output(value):
    return {"value": {"value": str(value)}}


def judgment_output(holds):
    return {"kind": "judgment", "outcome": "holds" if holds else "not_holds"}


class FakePersonFrame:
    def __init__(self, data):
        self.data = {key: list(value) for key, value in data.items()}

    @property
    def columns(self):
        return self.data.keys()

    def copy(self):
        return FakePersonFrame(self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = list(value)


def test_disability_category_from_reported_amounts_uses_weekly_thresholds():
    assert disability_category_from_reported_amounts(
        [
            0,
            29.0 * WEEKS_IN_YEAR,
            29.5 * WEEKS_IN_YEAR,
            75.8 * WEEKS_IN_YEAR,
            114.0 * WEEKS_IN_YEAR,
            float("nan"),
        ],
        (
            ("LOWER", 30.30),
            ("MIDDLE", 76.70),
            ("HIGHER", 114.60),
        ),
    ) == [
        "NONE",
        "NONE",
        "LOWER",
        "MIDDLE",
        "HIGHER",
        "NONE",
    ]


def test_add_policyengine_uk_disability_categories_backfills_stale_local_h5(
    monkeypatch,
):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_disability_category_thresholds",
        lambda year: (
            (
                "dla_sc_reported",
                "dla_sc_category",
                (
                    ("LOWER", 30.30),
                    ("MIDDLE", 76.70),
                    ("HIGHER", 114.60),
                ),
            ),
            (
                "pip_dl_reported",
                "pip_dl_category",
                (
                    ("STANDARD", 73.90),
                    ("ENHANCED", 110.40),
                ),
            ),
        ),
    )
    original_person = FakePersonFrame(
        {
            "person_id": [1, 2],
            "dla_sc_reported": [0, 76.7 * WEEKS_IN_YEAR],
            "pip_dl_reported": [110.4 * WEEKS_IN_YEAR, 0],
        }
    )
    dataset = SimpleNamespace(person=original_person)

    added = add_policyengine_uk_disability_categories_from_reported_amounts(
        dataset,
        year=2026,
    )

    assert added == ("dla_sc_category", "pip_dl_category")
    assert dataset.person is not original_person
    assert dataset.person.data["dla_sc_category"] == ["NONE", "MIDDLE"]
    assert dataset.person.data["pip_dl_category"] == ["ENHANCED", "NONE"]
    assert "dla_sc_category" not in original_person.data


def test_national_insurance_class_1_request_projects_weekly_inputs(monkeypatch):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_class_1_weekly_parameters",
        lambda year: {
            "primary_threshold": 241.73,
            "upper_earnings_limit": 966.73,
        },
    )

    request = build_national_insurance_class_1_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "ni_class_1_income": 52_000,
                    "ni_class_1_employee": 3_356.12,
                    "ni_liable": True,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "custom",
                "name": "tax_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": list(
                output["axiom"]
                for output in NATIONAL_INSURANCE_CLASS_1_OUTPUTS.values()
            ),
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_8_BASE}#input.primary_class_1_contribution_payable_as_mentioned_in_section_6_1_a:person_7"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_8_BASE}#input.earnings_paid_in_tax_week_in_respect_of_employment:person_7"
    ] == {"kind": "decimal", "value": "1000.0"}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_8_BASE}#input.current_primary_threshold_or_prescribed_equivalent:person_7"
    ] == {"kind": "decimal", "value": "241.73"}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_8_BASE}#input.current_upper_earnings_limit_or_prescribed_equivalent:person_7"
    ] == {"kind": "decimal", "value": "966.73"}


def test_national_insurance_class_4_projection_uses_pe_profit_base():
    assert project_national_insurance_class_4_inputs(
        {
            "self_employment_income": 60_000,
            "ni_class_1_employee": 3_000,
            "ni_liable": True,
        }
    ) == {
        "class_4_contributions_payable_under_section_15": True,
        "profits_chargeable_to_class_4_contributions": 57_000,
    }


def test_national_insurance_class_4_request_projects_annual_inputs():
    request = build_national_insurance_class_4_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "self_employment_income": 0,
                    "ni_class_1_employee": 0,
                    "ni_class_4_main": 0,
                    "ni_liable": True,
                },
                {
                    "person_id": 8,
                    "self_employment_income": 60_000,
                    "ni_class_1_employee": 3_000,
                    "ni_class_4_main": 2_262,
                    "ni_liable": True,
                },
            ],
            "person_ids": [7, 8],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_8",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                output["axiom"]
                for output in NATIONAL_INSURANCE_CLASS_4_OUTPUTS.values()
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_15_BASE}#input.class_4_contributions_payable_under_section_15:person_8"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_15_BASE}#input.profits_chargeable_to_class_4_contributions:person_8"
    ] == {"kind": "decimal", "value": "57000.0"}


def test_national_insurance_class_4_final_projection_uses_regulation_100_inputs():
    assert project_national_insurance_class_4_final_inputs(
        {
            "self_employment_income": 100_000,
            "ni_class_1_employee": 3_000,
            "ni_class_1_employee_primary": 6_000,
            "ni_class_4_main": 2_262,
            "ni_liable": True,
        },
        parameters={
            "lower_profits_limit": 12_570,
            "upper_profits_limit": 50_270,
            "main_class_4_percentage": 0.06,
            "additional_class_4_percentage": 0.02,
        },
    ) == {
        "primary_class_1_contributions_paid_at_main_primary_percentage": 6_000,
        "primary_class_1_contributions_payable_at_main_primary_percentage": 6_000,
        "class_4_contributions_payable_at_main_class_4_percentage": 2_262,
        "class_4_contribution_before_annual_maximum": 3_196.6,
        "class_4_contributions_payable_under_section_15_for_year": True,
        "profits_and_gains_for_year": 100_000,
        "lower_profits_limit": 12_570,
        "upper_profits_limit": 50_270,
        "main_class_4_percentage": 0.06,
        "additional_class_4_percentage": 0.02,
    }


def test_national_insurance_class_4_final_request_projects_annual_inputs(monkeypatch):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_class_4_parameters",
        lambda year: {
            "lower_profits_limit": 12_570,
            "upper_profits_limit": 50_270,
            "main_class_4_percentage": 0.06,
            "additional_class_4_percentage": 0.02,
        },
    )
    request = build_national_insurance_class_4_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "self_employment_income": 0,
                    "ni_class_1_employee": 0,
                    "ni_class_1_employee_primary": 0,
                    "ni_class_4": 0,
                    "ni_class_4_main": 0,
                    "ni_class_4_maximum": 0,
                    "ni_liable": True,
                },
                {
                    "person_id": 8,
                    "self_employment_income": 100_000,
                    "ni_class_1_employee": 3_000,
                    "ni_class_1_employee_primary": 6_000,
                    "ni_class_4": 1_748.6,
                    "ni_class_4_main": 2_262,
                    "ni_class_4_maximum": 1_748.6,
                    "ni_liable": True,
                },
            ],
            "person_ids": [7, 8],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_8",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                output["axiom"]
                for output in NATIONAL_INSURANCE_REGULATION_100_OUTPUTS.values()
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{NATIONAL_INSURANCE_REGULATION_100_BASE}#input.primary_class_1_contributions_paid_at_main_primary_percentage:person_8"
    ] == {"kind": "decimal", "value": "6000.0"}
    assert inputs[
        f"{NATIONAL_INSURANCE_REGULATION_100_BASE}#input.class_4_contribution_before_annual_maximum:person_8"
    ] == {"kind": "decimal", "value": "3196.6"}
    assert inputs[
        f"{NATIONAL_INSURANCE_REGULATION_100_BASE}#input.class_4_contributions_payable_under_section_15_for_year:person_8"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{NATIONAL_INSURANCE_REGULATION_100_BASE}#input.profits_and_gains_for_year:person_8"
    ] == {"kind": "decimal", "value": "100000.0"}


def test_national_insurance_final_projection_uses_contribution_classes():
    assert project_national_insurance_final_inputs(
        {
            "ni_class_1_employee": 2_400,
            "ni_class_2": 100,
            "ni_class_3": 50,
            "ni_class_4": 350,
        }
    ) == {
        "primary_class_1_contribution_for_year": 2_400,
        "class_2_contribution_for_year": 100,
        "class_3_contribution_for_year": 50,
        "class_4_contribution_for_year": 350,
    }


def test_national_insurance_final_request_projects_annual_inputs():
    request = build_national_insurance_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "national_insurance": 0,
                    "ni_class_1_employee": 0,
                    "ni_class_2": 0,
                    "ni_class_3": 0,
                    "ni_class_4": 0,
                },
                {
                    "person_id": 8,
                    "national_insurance": 2_900,
                    "ni_class_1_employee": 2_400,
                    "ni_class_2": 100,
                    "ni_class_3": 50,
                    "ni_class_4": 350,
                },
            ],
            "person_ids": [7, 8],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_8",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                f"{NATIONAL_INSURANCE_SECTION_1_BASE}#national_insurance_contribution",
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_1_BASE}#input.primary_class_1_contribution_for_year:person_8"
    ] == {"kind": "decimal", "value": "2400.0"}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_1_BASE}#input.class_2_contribution_for_year:person_8"
    ] == {"kind": "decimal", "value": "100.0"}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_1_BASE}#input.class_3_contribution_for_year:person_8"
    ] == {"kind": "decimal", "value": "50.0"}
    assert inputs[
        f"{NATIONAL_INSURANCE_SECTION_1_BASE}#input.class_4_contribution_for_year:person_8"
    ] == {"kind": "decimal", "value": "350.0"}


class FakePolicyEngineVariable:
    def __init__(self, name, entity, *, adds=None, subtracts=None):
        self.name = name
        self.entity = entity
        self.adds = adds
        self.subtracts = subtracts


class FakePolicyEngineEntity:
    key = "benunit"


def test_normalize_policyengine_entity_accepts_entity_objects():
    assert normalize_policyengine_entity(FakePolicyEngineEntity()) == "benunit"


def test_personal_allowance_projection_matches_policyengine_gift_aid_taper():
    projected = project_personal_allowance_inputs(
        {
            "adjusted_net_income": 101_000,
            "gift_aid_grossed_up": 600,
        }
    )

    assert projected == {
        "individual_makes_claim": True,
        "individual_meets_requirements_under_section_56": True,
        "adjusted_net_income": 100_400,
    }


def test_personal_allowance_request_projects_efrs_people():
    request = build_personal_allowance_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "adjusted_net_income": 20_000,
                    "gift_aid_grossed_up": 0,
                    "personal_allowance": 12_570,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [PERSONAL_ALLOWANCE_OUTPUTS["personal_allowance"]["axiom"]],
        }
    ]
    assert {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    } == {
        f"{PERSONAL_ALLOWANCE_BASE}#input.individual_makes_claim": {
            "kind": "bool",
            "value": True,
        },
        f"{PERSONAL_ALLOWANCE_BASE}#input.individual_meets_requirements_under_section_56": {
            "kind": "bool",
            "value": True,
        },
        f"{PERSONAL_ALLOWANCE_BASE}#input.adjusted_net_income": {
            "kind": "decimal",
            "value": "20000.0",
        },
    }


def test_student_loan_repayment_projection_uses_policyengine_plan_enum():
    assert project_student_loan_repayment_inputs(
        {
            "student_loan_plan": "StudentLoanPlan.PLAN_4",
            "adjusted_net_income": 40_000,
        }
    ) == {
        "loan_plan_is_plan_1": False,
        "loan_plan_is_plan_2": False,
        "loan_plan_is_plan_4": True,
        "loan_plan_is_plan_5": False,
        "loan_plan_is_postgraduate": False,
        "annual_income_before_tax_and_other_deductions": 40_000,
    }

    assert project_student_loan_repayment_inputs(
        {
            "student_loan_plan": "StudentLoanPlan.POSTGRADUATE",
            "adjusted_net_income": 35_000,
        }
    ) == {
        "loan_plan_is_plan_1": False,
        "loan_plan_is_plan_2": False,
        "loan_plan_is_plan_4": False,
        "loan_plan_is_plan_5": False,
        "loan_plan_is_postgraduate": True,
        "annual_income_before_tax_and_other_deductions": 35_000,
    }

    assert project_student_loan_repayment_inputs(
        {
            "student_loan_plan": "StudentLoanPlan.NONE",
            "adjusted_net_income": 100_000,
        }
    ) == {
        "loan_plan_is_plan_1": False,
        "loan_plan_is_plan_2": False,
        "loan_plan_is_plan_4": False,
        "loan_plan_is_plan_5": False,
        "loan_plan_is_postgraduate": False,
        "annual_income_before_tax_and_other_deductions": 100_000,
    }


def test_student_loan_repayment_request_projects_plan_inputs():
    request = build_student_loan_repayment_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "student_loan_plan": "StudentLoanPlan.PLAN_1",
                    "adjusted_net_income": 40_000,
                    "student_loan_repayment": 1_179,
                    "student_loan_repayments": 1_179,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    period = {
        "period_kind": "tax_year",
        "start": "2026-04-06",
        "end": "2027-04-05",
    }
    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": period,
            "outputs": [
                output["axiom"] for output in STUDENT_LOAN_REPAYMENT_OUTPUTS.values()
            ],
        }
    ]
    assert {
        record["name"]: (record["entity_id"], record["interval"], record["value"])
        for record in request["dataset"]["inputs"]
    } == {
        f"{STUDENT_LOAN_REPAYMENT_BASE}#input.loan_plan_is_plan_1": (
            "person_7",
            period,
            {"kind": "bool", "value": True},
        ),
        f"{STUDENT_LOAN_REPAYMENT_BASE}#input.loan_plan_is_plan_2": (
            "person_7",
            period,
            {"kind": "bool", "value": False},
        ),
        f"{STUDENT_LOAN_REPAYMENT_BASE}#input.loan_plan_is_plan_4": (
            "person_7",
            period,
            {"kind": "bool", "value": False},
        ),
        f"{STUDENT_LOAN_REPAYMENT_BASE}#input.loan_plan_is_plan_5": (
            "person_7",
            period,
            {"kind": "bool", "value": False},
        ),
        f"{STUDENT_LOAN_REPAYMENT_BASE}#input.loan_plan_is_postgraduate": (
            "person_7",
            period,
            {"kind": "bool", "value": False},
        ),
        f"{STUDENT_LOAN_REPAYMENT_BASE}#input.annual_income_before_tax_and_other_deductions": (
            "person_7",
            period,
            {"kind": "decimal", "value": "40000.0"},
        ),
    }


def test_income_tax_income_base_projection_uses_income_components():
    components = project_income_tax_income_base_components(
        {
            "employment_income": 30_000,
            "private_pension_income": 2_000,
            "savings_interest_income": 100,
        }
    )

    assert components == [
        {
            "name": "employment_income",
            "amount_charged_to_income_tax": 30_000,
            "relief_deducted_under_section_24": 0.0,
        },
        {
            "name": "private_pension_income",
            "amount_charged_to_income_tax": 2_000,
            "relief_deducted_under_section_24": 0.0,
        },
        {
            "name": "savings_interest_income",
            "amount_charged_to_income_tax": 100,
            "relief_deducted_under_section_24": 0.0,
        },
    ]


def test_income_tax_income_base_projection_projects_net_income_relief():
    components = project_income_tax_income_base_components(
        {
            "employment_income": 30_000,
            "private_pension_income": 2_000,
            "adjusted_net_income": 31_250,
        }
    )

    assert components[0]["relief_deducted_under_section_24"] == 750
    assert components[1]["relief_deducted_under_section_24"] == 0.0


def test_income_tax_section_23_projection_uses_pe_liability_components():
    projected = project_income_tax_section_23_inputs(
        {
            "income_tax_pre_charges": 4_500,
            "CB_HITC": 300,
            "personal_pension_contributions_tax": 200,
            "capped_mcad": 100,
            "other_tax_credits": 50,
        }
    )

    assert projected == {
        "net_income_taken_as_zero_under_section_24b": False,
        "tax_calculated_at_applicable_rates_on_income_remaining_after_allowances": 5_000,
        "tax_reductions_listed_in_section_26": 150,
        "additional_tax_amounts_listed_in_section_30": 0.0,
    }


def test_income_tax_section_10_projection_uses_pe_earned_income_and_rates():
    projected = project_income_tax_section_10_inputs(
        {"earned_taxable_income": 60_000},
        parameters={
            "basic_rate_limit": 37_700,
            "higher_rate_limit": 125_140,
            "basic_rate": 0.2,
            "higher_rate": 0.4,
            "additional_rate": 0.45,
        },
    )

    assert projected == {
        "income_charged_under_section_10": 60_000,
        "basic_rate": 0.2,
        "higher_rate": 0.4,
        "additional_rate": 0.45,
    }


def test_income_tax_section_11d_projection_removes_savings_deductions():
    projected = project_income_tax_section_11d_inputs(
        {
            "earned_taxable_income": 37_000,
            "taxable_savings_interest_income": 2_500,
            "received_allowances_savings_income": 100,
            "savings_allowance": 500,
            "savings_starter_rate_income": 400,
        },
        parameters={
            "basic_rate_limit": 37_700,
            "higher_rate_limit": 125_140,
            "savings_basic_rate": 0.2,
            "savings_higher_rate": 0.4,
            "savings_additional_rate": 0.45,
        },
    )

    assert projected == {
        "income_already_charged_before_section_11d_savings_income": 37_900,
        "savings_income_remaining_after_sections_12_and_12a": 1_500,
        "basic_rate_limit": 37_700,
        "higher_rate_limit": 125_140,
        "savings_basic_rate": 0.2,
        "savings_higher_rate": 0.4,
        "savings_additional_rate": 0.45,
    }


def test_income_tax_section_13_projection_uses_taxed_dividends_and_rates():
    projected = project_income_tax_section_13_inputs(
        {
            "earned_taxable_income": 37_000,
            "taxable_savings_interest_income": 2_000,
            "received_allowances_savings_income": 500,
            "taxable_dividend_income": 3_000,
            "received_allowances_dividend_income": 500,
            "taxed_dividend_income": 2_000,
        },
        parameters={
            "basic_rate_limit": 37_700,
            "higher_rate_limit": 125_140,
            "dividend_allowance": 500,
            "dividend_ordinary_rate": 0.1075,
            "dividend_upper_rate": 0.3575,
            "dividend_additional_rate": 0.3935,
        },
    )

    assert projected == {
        "income_already_charged_before_section_13_dividend_income": 39_000,
        "dividend_income_subject_to_section_13_rates": 2_000,
        "basic_rate_limit": 37_700,
        "higher_rate_limit": 125_140,
        "dividend_ordinary_rate": 0.1075,
        "dividend_upper_rate": 0.3575,
        "dividend_additional_rate": 0.3935,
    }


def test_income_tax_net_income_output_skips_negative_component_rows():
    spec = INCOME_TAX_INCOME_BASE_OUTPUTS["net_income"]

    assert efrs_uk.output_applies(
        spec,
        {
            "total_income": 31_250,
            "adjusted_net_income": 31_250,
            "employment_income": 30_000,
            "private_pension_income": 1_250,
        },
    )
    assert not efrs_uk.output_applies(
        spec,
        {
            "total_income": 14_483.34,
            "adjusted_net_income": 17_287.67,
            "employment_income": 17_287.67,
            "self_employment_income": -2_804.33,
        },
    )


def test_income_tax_income_base_request_projects_section_23_relation():
    request = build_income_tax_income_base_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "employment_income": 30_000,
                    "private_pension_income": 2_000,
                    "adjusted_net_income": 31_250,
                    "income_tax_pre_charges": 4_500,
                    "CB_HITC": 300,
                    "personal_pension_contributions_tax": 200,
                    "capped_mcad": 100,
                    "other_tax_credits": 50,
                    "income_tax": 4_850,
                    "total_income": 32_000,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": list(
                output["axiom"] for output in INCOME_TAX_INCOME_BASE_OUTPUTS.values()
            ),
        }
    ]
    assert request["dataset"]["relations"] == [
        {
            "name": f"{INCOME_TAX_SECTION_23_BASE}#relation.income_component_of_taxpayer",
            "tuple": ["person_7_income_employment_income", "person_7"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
        {
            "name": f"{INCOME_TAX_SECTION_23_BASE}#relation.income_component_of_taxpayer",
            "tuple": ["person_7_income_private_pension_income", "person_7"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.amount_charged_to_income_tax:person_7_income_employment_income"
    ] == {"kind": "decimal", "value": "30000.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.relief_deducted_under_section_24:person_7_income_employment_income"
    ] == {"kind": "decimal", "value": "750.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.relief_deducted_under_section_24:person_7_income_private_pension_income"
    ] == {"kind": "decimal", "value": "0.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.net_income_taken_as_zero_under_section_24b:person_7"
    ] == {"kind": "bool", "value": False}
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.tax_calculated_at_applicable_rates_on_income_remaining_after_allowances:person_7"
    ] == {"kind": "decimal", "value": "5000.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.tax_reductions_listed_in_section_26:person_7"
    ] == {"kind": "decimal", "value": "150.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_23_BASE}#input.additional_tax_amounts_listed_in_section_30:person_7"
    ] == {"kind": "decimal", "value": "0.0"}


def test_income_tax_section_10_request_projects_earned_income_inputs(monkeypatch):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_income_tax_section_10_parameters",
        lambda year: {
            "basic_rate_limit": 37_700,
            "higher_rate_limit": 125_140,
            "basic_rate": 0.2,
            "higher_rate": 0.4,
            "additional_rate": 0.45,
        },
    )
    request = build_income_tax_section_10_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "earned_taxable_income": 60_000,
                    "pays_scottish_income_tax": False,
                    "basic_rate_earned_income": 37_700,
                    "higher_rate_earned_income": 22_300,
                    "add_rate_earned_income": 0,
                    "basic_rate_earned_income_tax": 7_540,
                    "higher_rate_earned_income_tax": 8_920,
                    "add_rate_earned_income_tax": 0,
                    "earned_income_tax": 16_460,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": list(
                output["axiom"] for output in INCOME_TAX_SECTION_10_OUTPUTS.values()
            ),
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_10_BASE}#input.income_charged_under_section_10:person_7"
    ] == {"kind": "decimal", "value": "60000.0"}
    assert f"{INCOME_TAX_SECTION_10_BASE}#input.basic_rate_limit:person_7" not in inputs
    assert (
        f"{INCOME_TAX_SECTION_10_BASE}#input.higher_rate_limit:person_7" not in inputs
    )
    assert inputs[f"{INCOME_TAX_SECTION_10_BASE}#input.basic_rate:person_7"] == {
        "kind": "decimal",
        "value": "0.2",
    }
    assert inputs[f"{INCOME_TAX_SECTION_10_BASE}#input.higher_rate:person_7"] == {
        "kind": "decimal",
        "value": "0.4",
    }
    assert inputs[f"{INCOME_TAX_SECTION_10_BASE}#input.additional_rate:person_7"] == {
        "kind": "decimal",
        "value": "0.45",
    }


def test_income_tax_section_11d_request_projects_savings_inputs(monkeypatch):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_income_tax_section_11d_parameters",
        lambda year: {
            "basic_rate_limit": 37_700,
            "higher_rate_limit": 125_140,
            "savings_basic_rate": 0.2,
            "savings_higher_rate": 0.4,
            "savings_additional_rate": 0.45,
        },
    )
    request = build_income_tax_section_11d_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "earned_taxable_income": 37_000,
                    "taxable_savings_interest_income": 2_500,
                    "received_allowances_savings_income": 100,
                    "savings_allowance": 500,
                    "savings_starter_rate_income": 400,
                    "basic_rate_savings_income": 700,
                    "higher_rate_savings_income": 800,
                    "add_rate_savings_income": 0,
                    "taxed_savings_income": 1_500,
                    "savings_income_tax": 460,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": list(
                output["axiom"] for output in INCOME_TAX_SECTION_11D_OUTPUTS.values()
            ),
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_11D_BASE}#input.income_already_charged_before_section_11d_savings_income:person_7"
    ] == {"kind": "decimal", "value": "37900.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_11D_BASE}#input.savings_income_remaining_after_sections_12_and_12a:person_7"
    ] == {"kind": "decimal", "value": "1500.0"}
    assert inputs[f"{INCOME_TAX_SECTION_11D_BASE}#input.basic_rate_limit:person_7"] == {
        "kind": "integer",
        "value": 37700,
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_11D_BASE}#input.higher_rate_limit:person_7"
    ] == {
        "kind": "integer",
        "value": 125140,
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_11D_BASE}#input.savings_basic_rate:person_7"
    ] == {
        "kind": "decimal",
        "value": "0.2",
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_11D_BASE}#input.savings_higher_rate:person_7"
    ] == {
        "kind": "decimal",
        "value": "0.4",
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_11D_BASE}#input.savings_additional_rate:person_7"
    ] == {
        "kind": "decimal",
        "value": "0.45",
    }


def test_income_tax_section_13_request_projects_dividend_inputs(monkeypatch):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_income_tax_section_13_parameters",
        lambda year: {
            "basic_rate_limit": 37_700,
            "higher_rate_limit": 125_140,
            "dividend_allowance": 500,
            "dividend_ordinary_rate": 0.1075,
            "dividend_upper_rate": 0.3575,
            "dividend_additional_rate": 0.3935,
        },
    )
    request = build_income_tax_section_13_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "earned_taxable_income": 37_000,
                    "taxable_savings_interest_income": 2_000,
                    "received_allowances_savings_income": 500,
                    "taxable_dividend_income": 3_000,
                    "received_allowances_dividend_income": 500,
                    "taxed_dividend_income": 2_000,
                    "dividend_income_tax": 715,
                }
            ],
            "person_ids": [7],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": list(
                output["axiom"] for output in INCOME_TAX_SECTION_13_OUTPUTS.values()
            ),
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_13_BASE}#input.income_already_charged_before_section_13_dividend_income:person_7"
    ] == {"kind": "decimal", "value": "39000.0"}
    assert inputs[
        f"{INCOME_TAX_SECTION_13_BASE}#input.dividend_income_subject_to_section_13_rates:person_7"
    ] == {"kind": "decimal", "value": "2000.0"}
    assert inputs[f"{INCOME_TAX_SECTION_13_BASE}#input.basic_rate_limit:person_7"] == {
        "kind": "integer",
        "value": 37700,
    }
    assert inputs[f"{INCOME_TAX_SECTION_13_BASE}#input.higher_rate_limit:person_7"] == {
        "kind": "integer",
        "value": 125140,
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_13_BASE}#input.dividend_ordinary_rate:person_7"
    ] == {
        "kind": "decimal",
        "value": "0.1075",
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_13_BASE}#input.dividend_upper_rate:person_7"
    ] == {
        "kind": "decimal",
        "value": "0.3575",
    }
    assert inputs[
        f"{INCOME_TAX_SECTION_13_BASE}#input.dividend_additional_rate:person_7"
    ] == {
        "kind": "decimal",
        "value": "0.3935",
    }


def test_income_tax_section_10_output_skips_scottish_income_tax_rows():
    spec = INCOME_TAX_SECTION_10_OUTPUTS["income_tax_on_section_10_income"]

    assert efrs_uk.output_applies(spec, {"pays_scottish_income_tax": False})
    assert not efrs_uk.output_applies(spec, {"pays_scottish_income_tax": True})


def test_child_benefit_projection_uses_child_index():
    projected = project_child_benefit_inputs(
        {
            "child_benefit_child_index": 2,
            "child_benefit_respective_amount": 17.90 * WEEKS_IN_YEAR,
        }
    )

    assert projected == {
        "during_subsistence_of_marriage_any_party_married_to_more_than_one_person": False,
        "marriage_ceremony_took_place_under_law_permitting_polygamy": False,
        "specified_benefit_allowance_or_increase_paid_for_week_to_person": False,
        "specified_benefit_is_in_respect_of_only_elder_or_eldest_child_for_child_benefit_entitlement": False,
        "child_or_qualifying_young_person_is_only_elder_or_eldest_for_payee": False,
        "paragraph_2_relationship_coordination_applies": False,
        "child_or_qualifying_young_person_is_elder_or_eldest_among_paragraph_2_children": False,
        "payee_is_voluntary_organisation": False,
        "payee_resides_with_parent_otherwise_than_paragraph_2_a": False,
    }


def test_child_benefit_request_filters_to_positive_respective_amount_rows():
    request = build_child_benefit_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "child_benefit_child_index": -1,
                    "child_benefit_respective_amount": 0,
                },
                {
                    "person_id": 8,
                    "child_benefit_child_index": 1,
                    "child_benefit_respective_amount": 27.05 * WEEKS_IN_YEAR,
                },
            ],
            "person_ids": [7, 8],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_8",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": [CHILD_BENEFIT_OUTPUTS["child_benefit_weekly_rate"]["axiom"]],
        }
    ]
    assert {record["name"]: record["value"] for record in request["dataset"]["inputs"]}[
        f"{CHILD_BENEFIT_BASE}#input.child_or_qualifying_young_person_is_only_elder_or_eldest_for_payee"
    ] == {
        "kind": "bool",
        "value": True,
    }


def test_child_benefit_final_request_projects_family_relation_and_claim_gate():
    request = build_child_benefit_final_request(
        pe_data={
            "all_persons": [
                {
                    "person_id": 7,
                    "person_benunit_id": 3,
                    "child_benefit_child_index": -1,
                    "child_benefit_respective_amount": 0,
                },
                {
                    "person_id": 8,
                    "person_benunit_id": 3,
                    "child_benefit_child_index": 1,
                    "child_benefit_respective_amount": 27.05 * WEEKS_IN_YEAR,
                },
                {
                    "person_id": 9,
                    "person_benunit_id": 3,
                    "child_benefit_child_index": 2,
                    "child_benefit_respective_amount": 17.90 * WEEKS_IN_YEAR,
                },
            ],
            "persons": [],
            "benunits": [
                {
                    "benunit_id": 3,
                    "child_benefit": 0,
                    "child_benefit_entitlement": 44.95 * WEEKS_IN_YEAR,
                    "would_claim_child_benefit": False,
                }
            ],
            "person_ids": [],
            "benunit_ids": [3],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_3",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": [
                CHILD_BENEFIT_FINAL_OUTPUTS["child_benefit_weekly_amount"]["axiom"]
            ],
        }
    ]
    assert request["dataset"]["relations"] == [
        {
            "name": (
                f"{CHILD_BENEFIT_SECTION_141_BASE}#relation."
                "child_benefit_children_or_qualifying_young_persons_for_whom_person_responsible"
            ),
            "tuple": ["person_8", "benunit_3"],
            "interval": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
        },
        {
            "name": (
                f"{CHILD_BENEFIT_SECTION_141_BASE}#relation."
                "child_benefit_children_or_qualifying_young_persons_for_whom_person_responsible"
            ),
            "tuple": ["person_9", "benunit_3"],
            "interval": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
        },
    ]
    inputs = {
        f"{record['name']}:{record['entity_id']}": record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{CHILD_BENEFIT_FINAL_BASE}#input.would_claim_child_benefit:benunit_3"
    ] == {
        "kind": "bool",
        "value": False,
    }
    assert inputs[
        f"{CHILD_BENEFIT_SECTION_141_BASE}#input.is_child_or_qualifying_young_person_for_child_benefit:person_8"
    ] == {
        "kind": "bool",
        "value": True,
    }


def test_benefit_cap_relevant_amount_projection_uses_pe_case_inputs():
    projected = project_benefit_cap_relevant_amount_inputs(
        {
            "num_adults": 1,
            "num_children": 0,
            "benunit_region": "LONDON",
        }
    )

    assert projected == {
        "claim_is_for_joint_claimants": False,
        "responsible_for_child_or_qualifying_young_person": False,
        "award_contains_housing_costs_element": False,
        "accommodation_in_respect_of_which_claimant_meets_occupation_condition_is_in_greater_london": False,
        "claimant_receives_housing_benefit_for_dwelling_in_greater_london": False,
        "claimant_has_accommodation_normally_occupied_as_home": True,
        "accommodation_normally_occupied_as_home_is_in_greater_london": True,
        "jobcentre_plus_office_allocated_to_claim_is_in_greater_london": False,
    }

    assert (
        project_benefit_cap_relevant_amount_inputs(
            {
                "num_adults": 2,
                "num_children": 0,
                "benunit_region": "WALES",
            }
        )["claim_is_for_joint_claimants"]
        is True
    )


def test_benefit_cap_relevant_amount_request_filters_to_finite_caps():
    request = build_benefit_cap_relevant_amount_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benefit_cap": math.inf,
                    "num_adults": 1,
                    "num_children": 0,
                    "benunit_region": "LONDON",
                },
                {
                    "benunit_id": 12,
                    "benefit_cap": 22_020,
                    "num_adults": 2,
                    "num_children": 0,
                    "benunit_region": "WALES",
                },
            ],
            "benunit_ids": [11, 12],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_12",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in BENEFIT_CAP_RELEVANT_AMOUNT_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{BENEFIT_CAP_REGULATION_80A_BASE}#input.claim_is_for_joint_claimants"
    ] == {
        "kind": "bool",
        "value": True,
    }


def test_pension_credit_projection_uses_relation_type():
    assert project_pension_credit_inputs(
        {
            "relation_type": "COUPLE",
            "is_couple": False,
            "severe_disability_minimum_guarantee_addition": 0,
            "num_carers": 1,
        }
    ) == {
        "claimant_is_prisoner": False,
        "member_of_religious_order_fully_maintained_by_order": False,
        "claimant_has_partner": True,
        "treated_as_severely_disabled_person_under_schedule_i_part_i_paragraph_1": False,
        "severe_disability_couple_rate_conditions_satisfied": False,
        "paragraph_4_of_part_ii_of_schedule_i_satisfied_for_this_partner": True,
    }


def test_state_pension_credit_qualifying_age_projection_uses_equalized_age():
    assert project_state_pension_credit_qualifying_age_inputs(
        {
            "gender": "FEMALE",
            "state_pension_age": 66,
            "age": 67,
        }
    ) == {
        "claimant_is_woman": True,
        "pensionable_age": 66,
        "pensionable_age_for_woman_born_same_day": 66,
        "claimant_age": 67,
    }
    assert (
        project_state_pension_credit_qualifying_age_inputs(
            {
                "gender": "Gender.MALE",
                "state_pension_age": 66,
                "age": 65,
            }
        )["claimant_is_woman"]
        is False
    )


def test_state_pension_credit_qualifying_age_request_projects_people():
    request = build_state_pension_credit_qualifying_age_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "gender": "FEMALE",
                    "state_pension_age": 66,
                    "age": 67,
                }
            ],
            "person_ids": [7],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "custom",
                "name": "day",
                "start": "2026-04-06",
                "end": "2026-04-06",
            },
            "outputs": list(
                output["axiom"]
                for output in STATE_PENSION_CREDIT_QUALIFYING_AGE_OUTPUTS.values()
            ),
        }
    ]
    assert {record["name"]: record["value"] for record in request["dataset"]["inputs"]}[
        f"{STATE_PENSION_CREDIT_SECTION_1_BASE}#input.claimant_is_woman"
    ] == {
        "kind": "bool",
        "value": True,
    }


def test_state_pension_final_projection_uses_current_and_data_year_types():
    projected = project_state_pension_final_inputs(
        {
            "state_pension_type": "NEW",
            "state_pension_type_data_year": "BASIC",
            "state_pension_reported_data_year": 10_400,
        },
        parameters={
            "data_year_basic_state_pension_weekly_rate": 184.90,
            "data_year_full_new_state_pension_weekly_rate": 241.30,
            "state_pension_policy_uprating_factor": 1.0,
        },
    )

    assert projected == {
        "current_state_pension_type_is_basic": False,
        "current_state_pension_type_is_new": True,
        "data_year_state_pension_type_is_basic": True,
        "data_year_state_pension_type_is_new": False,
        "reported_state_pension_weekly_amount_in_data_year": 200,
        "data_year_basic_state_pension_weekly_rate": 184.90,
        "data_year_full_new_state_pension_weekly_rate": 241.30,
        "state_pension_abolished_by_policy": False,
        "state_pension_policy_uprating_factor": 1.0,
    }


def test_state_pension_final_request_projects_people(monkeypatch):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_state_pension_parameters",
        lambda *, year, data_year: {
            "data_year_basic_state_pension_weekly_rate": 184.90,
            "data_year_full_new_state_pension_weekly_rate": 241.30,
            "state_pension_policy_uprating_factor": 1.0,
        },
    )

    request = build_state_pension_final_request(
        pe_data={
            "data_year": 2023,
            "persons": [
                {
                    "person_id": 7,
                    "state_pension": 10_400,
                    "state_pension_type": "BASIC",
                    "state_pension_type_data_year": "BASIC",
                    "state_pension_reported_data_year": 10_400,
                }
            ],
            "person_ids": [7],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": [
                f"{STATE_PENSION_FINAL_BASE}#state_pension_weekly_amount",
            ],
        }
    ]
    values_by_name = {
        item["name"]: item["value"] for item in request["dataset"]["inputs"]
    }
    assert values_by_name == {
        f"{STATE_PENSION_FINAL_BASE}#input.current_state_pension_type_is_basic": {
            "kind": "bool",
            "value": True,
        },
        f"{STATE_PENSION_FINAL_BASE}#input.current_state_pension_type_is_new": {
            "kind": "bool",
            "value": False,
        },
        f"{STATE_PENSION_FINAL_BASE}#input.data_year_state_pension_type_is_basic": {
            "kind": "bool",
            "value": True,
        },
        f"{STATE_PENSION_FINAL_BASE}#input.data_year_state_pension_type_is_new": {
            "kind": "bool",
            "value": False,
        },
        f"{STATE_PENSION_FINAL_BASE}#input.reported_state_pension_weekly_amount_in_data_year": {
            "kind": "decimal",
            "value": "200.0",
        },
        f"{STATE_PENSION_FINAL_BASE}#input.data_year_basic_state_pension_weekly_rate": {
            "kind": "decimal",
            "value": "184.9",
        },
        f"{STATE_PENSION_FINAL_BASE}#input.data_year_full_new_state_pension_weekly_rate": {
            "kind": "decimal",
            "value": "241.3",
        },
        f"{STATE_PENSION_FINAL_BASE}#input.state_pension_abolished_by_policy": {
            "kind": "bool",
            "value": False,
        },
        f"{STATE_PENSION_FINAL_BASE}#input.state_pension_policy_uprating_factor": {
            "kind": "decimal",
            "value": "1.0",
        },
    }


def test_pension_credit_request_projects_benefit_units():
    request = build_pension_credit_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_couple": False,
                    "severe_disability_minimum_guarantee_addition": 0,
                    "carer_minimum_guarantee_addition": 0,
                    "num_carers": 0,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": list(
                output["axiom"] for output in PENSION_CREDIT_OUTPUTS.values()
            ),
        }
    ]
    assert {record["name"]: record["value"] for record in request["dataset"]["inputs"]}[
        f"{PENSION_CREDIT_BASE}#input.claimant_has_partner"
    ] == {
        "kind": "bool",
        "value": False,
    }


def test_pension_credit_deemed_income_projection_uses_regulation_15_inputs():
    assert project_pension_credit_deemed_income_inputs(
        {
            "pension_credit_assessable_capital": 10_501,
        }
    ) == {
        "claimant_capital": 10_501,
        "capital_disregarded_under_regulation_17_8": False,
    }


def test_pension_credit_deemed_income_request_projects_regulation_15_inputs():
    request = build_pension_credit_deemed_income_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "pension_credit_assessable_capital": 10_501,
                    "pension_credit_deemed_income": 2 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": list(
                output["axiom"]
                for output in PENSION_CREDIT_DEEMED_INCOME_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{PENSION_CREDIT_REGULATION_15_BASE}#input.claimant_capital"
    ] == {
        "kind": "decimal",
        "value": "10501.0",
    }
    assert inputs_by_name[
        f"{PENSION_CREDIT_REGULATION_15_BASE}"
        "#input.capital_disregarded_under_regulation_17_8"
    ] == {
        "kind": "bool",
        "value": False,
    }


@pytest.mark.parametrize(
    ("project", "row", "expected"),
    [
        (
            project_esa_income_tariff_income_inputs,
            {"esa_income_assessable_capital": 6_251},
            {
                "claimant_capital": 6_251,
                "claimant_in_prescribed_accommodation_under_regulation_118_3": False,
            },
        ),
        (
            project_jsa_income_tariff_income_inputs,
            {"jsa_income_assessable_capital": 6_251},
            {
                "claimant_capital": 6_251,
                "claimant_in_prescribed_accommodation_under_regulation_116_1B": False,
            },
        ),
        (
            project_income_support_tariff_income_inputs,
            {"income_support_assessable_capital": 6_251},
            {
                "claimant_capital": 6_251,
                "claimant_in_prescribed_accommodation_under_regulation_53_1B": False,
            },
        ),
        (
            project_housing_benefit_working_age_tariff_income_inputs,
            {"housing_benefit_assessable_capital": 6_251},
            {
                "claimant_capital": 6_251,
                "claimant_in_prescribed_circumstances_under_regulation_52_4": False,
            },
        ),
        (
            project_housing_benefit_pension_age_tariff_income_inputs,
            {"housing_benefit_assessable_capital": 10_501},
            {
                "claimant_capital": 10_501,
                "capital_disregarded_under_regulation_44_2": False,
            },
        ),
    ],
)
def test_legacy_tariff_income_projections_use_assessable_capital(
    project,
    row,
    expected,
):
    assert project(row) == expected


@pytest.mark.parametrize(
    ("build", "base", "outputs", "row", "branch_leaf"),
    [
        (
            build_esa_income_tariff_income_request,
            ESA_REGULATION_118_BASE,
            ESA_TARIFF_INCOME_OUTPUTS,
            {
                "esa_income_assessable_capital": 6_251,
                "esa_income_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            "claimant_in_prescribed_accommodation_under_regulation_118_3",
        ),
        (
            build_jsa_income_tariff_income_request,
            JSA_REGULATION_116_BASE,
            JSA_TARIFF_INCOME_OUTPUTS,
            {
                "jsa_income_assessable_capital": 6_251,
                "jsa_income_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            "claimant_in_prescribed_accommodation_under_regulation_116_1B",
        ),
        (
            build_income_support_tariff_income_request,
            INCOME_SUPPORT_REGULATION_53_BASE,
            INCOME_SUPPORT_TARIFF_INCOME_OUTPUTS,
            {
                "income_support_assessable_capital": 6_251,
                "income_support_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            "claimant_in_prescribed_accommodation_under_regulation_53_1B",
        ),
        (
            build_housing_benefit_working_age_tariff_income_request,
            HOUSING_BENEFIT_REGULATION_52_BASE,
            HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS,
            {
                "housing_benefit_assessable_capital": 6_251,
                "housing_benefit_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            "claimant_in_prescribed_circumstances_under_regulation_52_4",
        ),
        (
            build_housing_benefit_pension_age_tariff_income_request,
            HOUSING_BENEFIT_PENSION_AGE_REGULATION_29_BASE,
            HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS,
            {
                "housing_benefit_assessable_capital": 10_501,
                "housing_benefit_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            "capital_disregarded_under_regulation_44_2",
        ),
    ],
)
def test_legacy_tariff_income_requests_project_benefit_week_inputs(
    build,
    base,
    outputs,
    row,
    branch_leaf,
):
    request = build(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [{"benunit_id": 11, **row}],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": [output["axiom"] for output in outputs.values()],
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[f"{base}#input.claimant_capital"] == {
        "kind": "decimal",
        "value": str(float(row[next(key for key in row if key.endswith("_capital"))])),
    }
    assert inputs_by_name[f"{base}#input.{branch_leaf}"] == {
        "kind": "bool",
        "value": False,
    }


def test_state_pension_credit_guarantee_credit_projection_uses_section_2_inputs():
    projected = project_state_pension_credit_guarantee_credit_inputs(
        {
            "is_guarantee_credit_eligible": True,
            "pension_credit_income": 11_000,
            "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
            "minimum_guarantee": 280.00 * WEEKS_IN_YEAR,
        }
    )

    assert projected == {
        "claimant_income": 11_000,
        "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
        "prescribed_additional_amounts_applicable": 42.00 * WEEKS_IN_YEAR,
        "claimant_is_entitled_to_guarantee_credit": True,
    }


def test_state_pension_credit_guarantee_credit_request_projects_benefit_units():
    request = build_state_pension_credit_guarantee_credit_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 12,
                    "benunit_weight": 1,
                    "is_guarantee_credit_eligible": True,
                    "guarantee_credit": 2_000,
                    "pension_credit_income": 11_000,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                    "minimum_guarantee": 280.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [12],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_12",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": list(
                output["axiom"]
                for output in STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS.values()
            ),
        }
    ]
    inputs = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{STATE_PENSION_CREDIT_SECTION_2_BASE}#input.claimant_is_entitled_to_guarantee_credit"
    ] == {
        "kind": "bool",
        "value": True,
    }
    assert inputs[
        f"{STATE_PENSION_CREDIT_SECTION_2_BASE}#input.prescribed_additional_amounts_applicable"
    ] == {
        "kind": "decimal",
        "value": str(42.00 * WEEKS_IN_YEAR),
    }


def test_state_pension_credit_savings_credit_projection_uses_section_3_inputs():
    projected = project_state_pension_credit_savings_credit_inputs(
        {
            "relation_type": "RelationType.COUPLE",
            "is_savings_credit_eligible": True,
            "savings_credit_income": 18_000,
            "pension_credit_income": 18_600,
            "standard_minimum_guarantee": 363.25 * WEEKS_IN_YEAR,
            "minimum_guarantee": 410.50 * WEEKS_IN_YEAR,
        },
        parameters={
            "savings_credit_threshold_single": 208.07 * WEEKS_IN_YEAR,
            "savings_credit_threshold_couple": 329.75 * WEEKS_IN_YEAR,
            "phase_in_rate": 0.6,
            "phase_out_rate": 0.4,
        },
    )

    assert projected == {
        "claimant_satisfies_savings_credit_first_condition": True,
        "claimant_qualifying_income": 18_000,
        "claimant_income": 18_600,
        "savings_credit_threshold": 329.75 * WEEKS_IN_YEAR,
        "prescribed_percentage_for_amount_a": 0.6,
        "prescribed_percentage_for_amount_b": 0.4,
        "prescribed_percentage_for_maximum_savings_credit": 0.6,
        "standard_minimum_guarantee": 363.25 * WEEKS_IN_YEAR,
        "appropriate_minimum_guarantee": 410.50 * WEEKS_IN_YEAR,
        "maximum_savings_credit_taken_as_nil_by_regulations": False,
    }


def test_state_pension_credit_savings_credit_request_projects_benefit_units(
    monkeypatch,
):
    monkeypatch.setattr(
        efrs_uk,
        "policyengine_uk_savings_credit_parameters",
        lambda year: {
            "savings_credit_threshold_single": 208.07 * WEEKS_IN_YEAR,
            "savings_credit_threshold_couple": 329.75 * WEEKS_IN_YEAR,
            "phase_in_rate": 0.6,
            "phase_out_rate": 0.4,
        },
    )

    request = build_state_pension_credit_savings_credit_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 12,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_savings_credit_eligible": True,
                    "savings_credit": 12.5 * WEEKS_IN_YEAR,
                    "savings_credit_income": 11_000,
                    "pension_credit_income": 11_000,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                    "minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [12],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_12",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": list(
                output["axiom"]
                for output in STATE_PENSION_CREDIT_SAVINGS_CREDIT_OUTPUTS.values()
            ),
        }
    ]
    assert {record["name"]: record["value"] for record in request["dataset"]["inputs"]}[
        f"{STATE_PENSION_CREDIT_SECTION_3_BASE}#input.savings_credit_threshold"
    ] == {
        "kind": "decimal",
        "value": str(208.07 * WEEKS_IN_YEAR),
    }


def test_universal_credit_request_queries_monthly_table_amounts():
    request = build_universal_credit_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "uc_standard_allowance": 338.58 * 12,
                    "uc_standard_allowance_claimant_type": "SINGLE_YOUNG",
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
        surface="universal-credit-standard-allowance",
    )

    assert request["mode"] == "explain"
    assert request["dataset"] == {"inputs": [], "relations": []}
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_STANDARD_ALLOWANCE_OUTPUTS.values()
            ),
        }
    ]


def test_universal_credit_award_projection_uses_monthly_eligible_components():
    projected = project_universal_credit_award_inputs(
        {
            "is_uc_eligible": True,
            "uc_standard_allowance": 1_200,
            "uc_child_element": 2_400,
            "uc_disability_elements": 600,
            "uc_housing_costs_element": 360,
            "uc_childcare_element": 120,
            "uc_carer_element": 60,
            "uc_income_reduction": 300,
        }
    )

    assert projected == {
        "amount_included_under_section_9_standard_allowance": 100,
        "amount_included_under_section_10_responsibility_for_children_and_young_persons": 200,
        "amount_included_under_section_11_housing_costs": 30,
        "amount_included_under_section_12_other_particular_needs_or_circumstances": 65,
        "earned_income_deduction_calculated_in_prescribed_manner": 25,
        "unearned_income_deduction_calculated_in_prescribed_manner": 0.0,
    }

    assert project_universal_credit_award_inputs(
        {
            "is_uc_eligible": False,
            "uc_standard_allowance": 1_200,
            "uc_child_element": 2_400,
            "uc_income_reduction": 300,
        }
    ) == {
        "amount_included_under_section_9_standard_allowance": 0.0,
        "amount_included_under_section_10_responsibility_for_children_and_young_persons": 0.0,
        "amount_included_under_section_11_housing_costs": 0.0,
        "amount_included_under_section_12_other_particular_needs_or_circumstances": 0.0,
        "earned_income_deduction_calculated_in_prescribed_manner": 0.0,
        "unearned_income_deduction_calculated_in_prescribed_manner": 0.0,
    }


def test_universal_credit_award_request_projects_section_8_inputs():
    request = build_universal_credit_award_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "is_uc_eligible": True,
                    "uc_standard_allowance": 1_200,
                    "uc_child_element": 2_400,
                    "uc_disability_elements": 600,
                    "uc_housing_costs_element": 360,
                    "uc_childcare_element": 120,
                    "uc_carer_element": 60,
                    "uc_income_reduction": 300,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"] for output in UNIVERSAL_CREDIT_AWARD_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{WELFARE_REFORM_ACT_SECTION_8_BASE}#input.amount_included_under_section_12_other_particular_needs_or_circumstances"
    ] == {
        "kind": "decimal",
        "value": "65.0",
    }


def test_universal_credit_final_projection_uses_annual_pre_cap_and_cap_reduction():
    assert project_universal_credit_final_inputs(
        {
            "universal_credit_pre_benefit_cap": 12_000,
            "benefit_cap_reduction": 1_250,
        }
    ) == {
        "universal_credit_pre_benefit_cap_for_year": 12_000.0,
        "benefit_cap_reduction_for_year": 1_250.0,
    }


def test_universal_credit_final_request_projects_final_inputs():
    request = build_universal_credit_final_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 10,
                    "universal_credit": 0,
                    "universal_credit_pre_benefit_cap": 0,
                    "benefit_cap_reduction": 0,
                },
                {
                    "benunit_id": 11,
                    "universal_credit": 10_750,
                    "universal_credit_pre_benefit_cap": 12_000,
                    "benefit_cap_reduction": 1_250,
                },
            ],
            "benunit_ids": [10, 11],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [
                UNIVERSAL_CREDIT_FINAL_OUTPUTS["universal_credit_annual_amount"][
                    "axiom"
                ],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{UNIVERSAL_CREDIT_FINAL_BASE}#input.universal_credit_pre_benefit_cap_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "12000.0"}
    assert inputs[
        f"{UNIVERSAL_CREDIT_FINAL_BASE}#input.benefit_cap_reduction_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "1250.0"}


def test_carers_allowance_final_projection_uses_pe_boundary_facts():
    assert project_carers_allowance_final_inputs(
        {
            "age": 30,
            "country": "SCOTLAND",
            "care_hours": 0,
            "carers_allowance": 0,
            "carers_allowance_reported": 4_495.40,
        },
        year=2026,
    ) == {
        "person_is_aged_16_or_over": True,
        "weekly_care_hours": 35.0,
        "cared_for_person_receives_qualifying_disability_benefit": True,
        "weekly_earnings_after_tax_national_insurance_and_expenses": 0.0,
        "person_is_in_full_time_education": False,
        "person_lives_in_scotland": True,
    }


def test_carers_allowance_final_request_projects_final_inputs():
    request = build_carers_allowance_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 1,
                    "age": 30,
                    "country": "ENGLAND",
                    "care_hours": 0,
                    "carers_allowance": 0,
                    "carers_allowance_reported": 0,
                },
                {
                    "person_id": 2,
                    "age": 30,
                    "country": "ENGLAND",
                    "care_hours": 35,
                    "carers_allowance": 4_495.40,
                    "carers_allowance_reported": 0,
                },
            ],
            "person_ids": [1, 2],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_2",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                CARERS_ALLOWANCE_FINAL_OUTPUTS["carers_allowance_annual_amount"][
                    "axiom"
                ],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{CARERS_ALLOWANCE_FINAL_BASE}#input.person_is_aged_16_or_over:person_2"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{CARERS_ALLOWANCE_FINAL_BASE}#input.cared_for_person_receives_qualifying_disability_benefit:person_2"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{CARERS_ALLOWANCE_FINAL_BASE}#input.weekly_care_hours:person_2"
    ] == {"kind": "decimal", "value": "35.0"}
    assert inputs[
        f"{CARERS_ALLOWANCE_FINAL_BASE}#input.person_lives_in_scotland:person_2"
    ] == {"kind": "bool", "value": False}


def test_carer_support_payment_final_projection_uses_pe_boundary_facts():
    assert project_carer_support_payment_final_inputs(
        {
            "age": 30,
            "country": "SCOTLAND",
            "care_hours": 0,
            "carer_support_payment": 5_103.80,
            "carers_allowance_reported": 0,
        },
        year=2026,
    ) == {
        "person_is_aged_16_or_over": True,
        "person_lives_in_scotland": True,
        "weekly_care_hours": 35.0,
        "cared_for_person_receives_qualifying_disability_benefit": True,
        "weekly_earnings_after_tax_national_insurance_and_expenses": 0.0,
        "person_is_in_full_time_education": False,
    }


def test_carer_support_payment_final_request_projects_final_inputs():
    request = build_carer_support_payment_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 1,
                    "age": 30,
                    "country": "ENGLAND",
                    "care_hours": 35,
                    "carer_support_payment": 0,
                    "carers_allowance_reported": 0,
                },
                {
                    "person_id": 2,
                    "age": 30,
                    "country": "SCOTLAND",
                    "care_hours": 35,
                    "carer_support_payment": 5_103.80,
                    "carers_allowance_reported": 0,
                },
            ],
            "person_ids": [1, 2],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_2",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                CARER_SUPPORT_PAYMENT_FINAL_OUTPUTS[
                    "carer_support_payment_annual_amount"
                ]["axiom"],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{CARER_SUPPORT_PAYMENT_FINAL_BASE}#input.person_lives_in_scotland:person_2"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{CARER_SUPPORT_PAYMENT_FINAL_BASE}#input.person_is_aged_16_or_over:person_2"
    ] == {"kind": "bool", "value": True}
    assert inputs[
        f"{CARER_SUPPORT_PAYMENT_FINAL_BASE}#input.weekly_care_hours:person_2"
    ] == {"kind": "decimal", "value": "35.0"}
    assert inputs[
        f"{CARER_SUPPORT_PAYMENT_FINAL_BASE}#input.cared_for_person_receives_qualifying_disability_benefit:person_2"
    ] == {"kind": "bool", "value": True}


def test_scottish_child_payment_final_projection_uses_pe_boundary_facts():
    assert project_scottish_child_payment_final_inputs(
        {
            "age": 7,
            "is_scp_eligible": True,
            "would_claim_scp": False,
            "scottish_child_payment": 1_466.40,
        }
    ) == {
        "person_lives_in_scotland": True,
        "child_age": 7.0,
        "applicant_or_partner_receives_qualifying_benefit": True,
    }
    assert (
        project_scottish_child_payment_final_inputs(
            {
                "age": 7,
                "is_scp_eligible": float("nan"),
                "would_claim_scp": True,
                "scottish_child_payment": 0,
            }
        )["applicant_or_partner_receives_qualifying_benefit"]
        is False
    )


def test_scottish_child_payment_final_request_projects_final_inputs():
    request = build_scottish_child_payment_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 1,
                    "age": 7,
                    "is_scp_eligible": False,
                    "would_claim_scp": False,
                    "scottish_child_payment": 0,
                },
                {
                    "person_id": 2,
                    "age": 7,
                    "is_scp_eligible": True,
                    "would_claim_scp": True,
                    "scottish_child_payment": 1_466.40,
                },
            ],
            "person_ids": [1, 2],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_2",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                SCOTTISH_CHILD_PAYMENT_FINAL_OUTPUTS[
                    "scottish_child_payment_annual_amount"
                ]["axiom"],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{SCOTTISH_CHILD_PAYMENT_FINAL_BASE}#input.person_lives_in_scotland:person_2"
    ] == {"kind": "bool", "value": True}
    assert inputs[f"{SCOTTISH_CHILD_PAYMENT_FINAL_BASE}#input.child_age:person_2"] == {
        "kind": "decimal",
        "value": "7.0",
    }
    assert inputs[
        f"{SCOTTISH_CHILD_PAYMENT_FINAL_BASE}#input.applicant_or_partner_receives_qualifying_benefit:person_2"
    ] == {"kind": "bool", "value": True}


def test_sda_final_projection_uses_reported_receipt():
    assert project_sda_final_inputs(
        {
            "sda_reported": 6_206.20,
        }
    ) == {
        "reported_severe_disablement_allowance_for_year": 6_206.20,
    }


def test_sda_final_request_projects_final_inputs():
    request = build_sda_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 1,
                    "sda": 0,
                    "sda_reported": 0,
                },
                {
                    "person_id": 2,
                    "sda": 6_206.20,
                    "sda_reported": 6_206.20,
                },
            ],
            "person_ids": [1, 2],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_2",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                SDA_FINAL_OUTPUTS["severe_disablement_allowance_annual_amount"][
                    "axiom"
                ],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{SDA_FINAL_BASE}#input.reported_severe_disablement_allowance_for_year:person_2"
    ] == {"kind": "decimal", "value": "6206.2"}


def test_dla_final_projection_uses_category_inputs():
    assert project_dla_final_inputs(
        {
            "age": 10,
            "dla_sc_category": "MIDDLE",
            "dla_m_category": "HIGHER",
        }
    ) == {
        "child_is_under_16": True,
        "child_is_aged_3_or_over": True,
        "child_is_aged_5_or_over": True,
        "care_component_is_highest_rate": False,
        "care_component_is_middle_rate": True,
        "care_component_is_lowest_rate": False,
        "mobility_component_is_higher_rate": True,
        "mobility_component_is_lower_rate": False,
    }


def test_dla_final_request_projects_final_inputs():
    request = build_dla_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 1,
                    "age": 10,
                    "dla": 0,
                    "dla_sc": 0,
                    "dla_m": 0,
                    "dla_sc_category": "NONE",
                    "dla_m_category": "NONE",
                },
                {
                    "person_id": 2,
                    "age": 10,
                    "dla": 8_148.40,
                    "dla_sc": 3_988.40,
                    "dla_m": 4_160.00,
                    "dla_sc_category": "MIDDLE",
                    "dla_m_category": "HIGHER",
                },
                {
                    "person_id": 3,
                    "age": 40,
                    "dla": 8_148.40,
                    "dla_sc": 3_988.40,
                    "dla_m": 4_160.00,
                    "dla_sc_category": "MIDDLE",
                    "dla_m_category": "HIGHER",
                },
            ],
            "person_ids": [1, 2, 3],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_2",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                DLA_FINAL_OUTPUTS[
                    "disability_living_allowance_self_care_weekly_amount"
                ]["axiom"],
                DLA_FINAL_OUTPUTS["disability_living_allowance_mobility_weekly_amount"][
                    "axiom"
                ],
                DLA_FINAL_OUTPUTS["disability_living_allowance_annual_amount"]["axiom"],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[f"{DLA_FINAL_BASE}#input.care_component_is_middle_rate:person_2"] == {
        "kind": "bool",
        "value": True,
    }
    assert inputs[
        f"{DLA_FINAL_BASE}#input.mobility_component_is_higher_rate:person_2"
    ] == {"kind": "bool", "value": True}


def test_pip_final_projection_maps_categories_to_rate_band_leaves():
    from axiom_oracles.bridges.efrs_uk import project_pip_final_inputs

    mixed = project_pip_final_inputs(
        {"pip_dl_category": "ENHANCED", "pip_m_category": "STANDARD"}
    )
    assert mixed == {
        f"{PIP_FINAL_BASE}#input.daily_living_is_enhanced_rate": True,
        f"{PIP_FINAL_BASE}#input.daily_living_is_standard_rate": False,
        f"{PIP_FINAL_BASE}#input.mobility_is_enhanced_rate": False,
        f"{PIP_FINAL_BASE}#input.mobility_is_standard_rate": True,
    }

    nil = project_pip_final_inputs({"pip_dl_category": "NONE", "pip_m_category": "NONE"})
    assert all(value is False for value in nil.values())


def test_pip_final_request_projects_final_inputs():
    request = build_pip_final_request(
        pe_data={
            "persons": [
                {
                    "person_id": 1,
                    "pip": 0,
                    "pip_dl": 0,
                    "pip_m": 0,
                    "pip_dl_category": "NONE",
                    "pip_m_category": "NONE",
                    "receives_enhanced_pip_dl": False,
                },
                {
                    "person_id": 2,
                    "pip": 10_119.20,
                    "pip_dl": 5_959.20,
                    "pip_m": 4_160.00,
                    "pip_dl_category": "ENHANCED",
                    "pip_m_category": "ENHANCED",
                    "receives_enhanced_pip_dl": True,
                },
            ],
            "person_ids": [1, 2],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_2",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-04-06",
                "end": "2027-04-05",
            },
            "outputs": [
                PIP_FINAL_OUTPUTS["pip_daily_living_weekly_amount"]["axiom"],
                PIP_FINAL_OUTPUTS["pip_mobility_weekly_amount"]["axiom"],
                PIP_FINAL_OUTPUTS["personal_independence_payment_weekly_total"][
                    "axiom"
                ],
                PIP_FINAL_OUTPUTS["receives_enhanced_daily_living_component"]["axiom"],
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[f"{PIP_FINAL_BASE}#input.daily_living_is_enhanced_rate:person_2"] == {
        "kind": "bool",
        "value": True,
    }
    assert inputs[f"{PIP_FINAL_BASE}#input.mobility_is_enhanced_rate:person_2"] == {
        "kind": "bool",
        "value": True,
    }


def test_pension_credit_final_projection_uses_entitlement_components():
    assert project_pension_credit_final_inputs(
        {
            "pension_credit_entitlement": 2_825,
            "would_claim_pc": False,
        }
    ) == {
        "pension_credit_entitlement_for_year": 2_825.0,
        "person_or_partner_would_claim_pension_credit": False,
    }
    assert (
        project_pension_credit_final_inputs(
            {
                "pension_credit_entitlement": 2_825,
                "would_claim_pc": float("nan"),
            }
        )["person_or_partner_would_claim_pension_credit"]
        is False
    )


def test_pension_credit_final_request_projects_final_inputs():
    request = build_pension_credit_final_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "pension_credit_entitlement": 3_400,
                    "pension_credit": 3_400,
                    "would_claim_pc": True,
                },
                {
                    "benunit_id": 12,
                    "pension_credit_entitlement": 0,
                    "pension_credit": 0,
                    "would_claim_pc": False,
                },
            ],
            "benunit_ids": [11, 12],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [
                PENSION_CREDIT_FINAL_OUTPUTS["pension_credit_annual_amount"]["axiom"]
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{PENSION_CREDIT_FINAL_BASE}#input.pension_credit_entitlement_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "3400.0"}
    assert inputs[
        f"{PENSION_CREDIT_FINAL_BASE}#input.person_or_partner_would_claim_pension_credit:benunit_11"
    ] == {"kind": "bool", "value": True}


def test_esa_income_final_projection_uses_reported_award_and_tariff_income():
    assert project_esa_income_final_inputs(
        {
            "esa_income_reported_for_year": 2_600,
            "esa_income_tariff_income": 520,
            "esa_income_eligible": True,
        }
    ) == {
        "reported_income_related_esa_for_year": 2_600.0,
        "income_related_esa_tariff_income_for_year": 520.0,
        "income_related_esa_eligible": True,
    }
    assert (
        project_esa_income_final_inputs(
            {
                "esa_income_reported_for_year": 2_600,
                "esa_income_tariff_income": 0,
                "esa_income_eligible": float("nan"),
            }
        )["income_related_esa_eligible"]
        is False
    )


def test_esa_income_final_request_projects_final_inputs():
    request = build_esa_income_final_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "esa_income_reported_for_year": 2_600,
                    "esa_income_tariff_income": 520,
                    "esa_income_eligible": True,
                    "esa_income": 2_080,
                },
                {
                    "benunit_id": 12,
                    "esa_income_reported_for_year": 0,
                    "esa_income_tariff_income": 0,
                    "esa_income_eligible": False,
                    "esa_income": 0,
                },
            ],
            "benunit_ids": [11, 12],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [ESA_FINAL_OUTPUTS["income_related_esa_annual_amount"]["axiom"]],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{ESA_FINAL_BASE}#input.reported_income_related_esa_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "2600.0"}
    assert inputs[
        f"{ESA_FINAL_BASE}#input.income_related_esa_tariff_income_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "520.0"}
    assert inputs[f"{ESA_FINAL_BASE}#input.income_related_esa_eligible:benunit_11"] == {
        "kind": "bool",
        "value": True,
    }


def test_housing_benefit_final_projection_uses_pre_cap_and_cap_reduction():
    assert project_housing_benefit_final_inputs(
        {
            "housing_benefit_pre_benefit_cap": 5_200,
            "benefit_cap_reduction": 1_040,
            "would_claim_housing_benefit": True,
        }
    ) == {
        "housing_benefit_pre_benefit_cap_for_year": 5_200.0,
        "benefit_cap_reduction_for_year": 1_040.0,
        "would_claim_housing_benefit": True,
    }
    assert (
        project_housing_benefit_final_inputs(
            {
                "housing_benefit_pre_benefit_cap": 5_200,
                "benefit_cap_reduction": 0,
                "would_claim_housing_benefit": float("nan"),
            }
        )["would_claim_housing_benefit"]
        is False
    )


def test_housing_benefit_final_request_projects_final_inputs():
    request = build_housing_benefit_final_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "housing_benefit_pre_benefit_cap": 5_200,
                    "benefit_cap_reduction": 1_040,
                    "would_claim_housing_benefit": True,
                    "housing_benefit": 4_160,
                },
                {
                    "benunit_id": 12,
                    "housing_benefit_pre_benefit_cap": 0,
                    "benefit_cap_reduction": 0,
                    "would_claim_housing_benefit": False,
                    "housing_benefit": 0,
                },
            ],
            "benunit_ids": [11, 12],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [
                HOUSING_BENEFIT_FINAL_OUTPUTS["housing_benefit_annual_amount"]["axiom"]
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{HOUSING_BENEFIT_FINAL_BASE}#input.housing_benefit_pre_benefit_cap_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "5200.0"}
    assert inputs[
        f"{HOUSING_BENEFIT_FINAL_BASE}#input.benefit_cap_reduction_for_year:benunit_11"
    ] == {"kind": "decimal", "value": "1040.0"}
    assert inputs[
        f"{HOUSING_BENEFIT_FINAL_BASE}#input.would_claim_housing_benefit:benunit_11"
    ] == {"kind": "bool", "value": True}


def test_housing_benefit_applicable_amount_projection_uses_demographics():
    assert efrs_uk.project_housing_benefit_applicable_amount_inputs(
        {
            "is_couple": True,
            "housing_benefit_any_over_sp_age": False,
            "eldest_adult_age": 40,
            "benefits_premiums": 1_040.0,
        }
    ) == {
        "hb_pilot_is_couple": True,
        "hb_pilot_any_member_pension_age": False,
        "hb_pilot_eldest_adult_age": 40.0,
        "hb_pilot_premium_amount": 1_040.0,
    }


def test_housing_benefit_applicable_amount_applies_requires_eligibility():
    spec = efrs_uk.HOUSING_BENEFIT_APPLICABLE_AMOUNT_OUTPUTS[
        "hb_pilot_applicable_amount"
    ]
    assert efrs_uk.output_applies(spec, {"housing_benefit_eligible": True})
    assert not efrs_uk.output_applies(spec, {"housing_benefit_eligible": False})


def test_housing_benefit_entitlement_projection_uses_realised_components():
    assert efrs_uk.project_housing_benefit_entitlement_inputs(
        {
            "is_couple": False,
            "housing_benefit_any_over_sp_age": False,
            "eldest_adult_age": 40,
            "benefits_premiums": 0,
            "housing_benefit_applicable_income": 5_000,
            "benunit_rent": 5_200,
            "LHA_eligible": False,
            "LHA_cap": 0,
        }
    ) == {
        "hb_pilot_is_couple": False,
        "hb_pilot_any_member_pension_age": False,
        "hb_pilot_eldest_adult_age": 40.0,
        "hb_pilot_premium_amount": 0.0,
        "hb_pilot_number_of_non_dependants": 0,
        "hb_pilot_non_dependant_gross_weekly_income": 0.0,
        "hb_pilot_applicable_income": 5_000.0,
        "hb_pilot_eligible_rent": 5_200.0,
        "hb_pilot_lha_path_applies": False,
        "hb_pilot_maximum_rent": 0.0,
    }


def test_housing_benefit_entitlement_applies_excludes_non_dependant_deductions():
    spec = efrs_uk.HOUSING_BENEFIT_ENTITLEMENT_OUTPUTS["hb_pilot_entitlement"]
    assert efrs_uk.output_applies(
        spec,
        {"housing_benefit_eligible": True, "housing_benefit_non_dep_deductions": 0},
    )
    assert not efrs_uk.output_applies(
        spec,
        {
            "housing_benefit_eligible": True,
            "housing_benefit_non_dep_deductions": 1_040,
        },
    )
    assert not efrs_uk.output_applies(
        spec,
        {"housing_benefit_eligible": False, "housing_benefit_non_dep_deductions": 0},
    )


def test_housing_benefit_entitlement_request_projects_entitlement_inputs():
    request = build_housing_benefit_entitlement_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 21,
                    "housing_benefit_eligible": True,
                    "housing_benefit_non_dep_deductions": 0,
                    "is_couple": False,
                    "housing_benefit_any_over_sp_age": False,
                    "eldest_adult_age": 40,
                    "benefits_premiums": 0,
                    "housing_benefit_applicable_income": 5_000,
                    "benunit_rent": 5_200,
                    "LHA_eligible": False,
                    "LHA_cap": 0,
                    "housing_benefit_entitlement": 5_179.59,
                },
            ],
            "benunit_ids": [21],
        },
        year=2026,
    )

    assert request["queries"] == [
        {
            "entity_id": "benunit_21",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [
                HOUSING_BENEFIT_ENTITLEMENT_OUTPUTS["hb_pilot_entitlement"]["axiom"]
            ],
        }
    ]
    inputs = {
        record["name"] + ":" + record["entity_id"]: record["value"]
        for record in request["dataset"]["inputs"]
    }
    assert inputs[
        f"{HOUSING_BENEFIT_ENTITLEMENT_BASE}#input.hb_pilot_applicable_income:benunit_21"
    ] == {"kind": "decimal", "value": "5000.0"}
    assert inputs[
        f"{HOUSING_BENEFIT_ENTITLEMENT_BASE}#input.hb_pilot_eligible_rent:benunit_21"
    ] == {"kind": "decimal", "value": "5200.0"}
    assert inputs[
        f"{HOUSING_BENEFIT_ENTITLEMENT_BASE}#input.hb_pilot_lha_path_applies:benunit_21"
    ] == {"kind": "bool", "value": False}


def test_universal_credit_childcare_element_projection_reverses_rate_and_cap():
    projected = project_universal_credit_childcare_element_inputs(
        {
            "uc_childcare_element": 1_020,
            "uc_maximum_childcare_element_amount": 1_800,
        }
    )

    assert projected == {
        "charges_paid_for_relevant_childcare_attributable_to_assessment_period": 100,
        "amount_considered_excessive_having_regard_to_paid_work_extent": 0.0,
        "amount_met_or_reimbursed_by_employer_or_some_other_person": 0.0,
        "secretary_of_state_work_transition_childcare_payment_meets_non_other_relevant_support_conditions": False,
        "amount_from_funds_provided_by_secretary_of_state_or_scottish_or_welsh_ministers_for_work_related_activity_or_training": 0.0,
        "secretary_of_state_work_transition_childcare_payment_amount": 0.0,
        "maximum_amount_specified_in_table_in_regulation_36": 150,
    }
    assert project_universal_credit_childcare_element_inputs(
        {
            "uc_childcare_element": 0,
            "uc_maximum_childcare_element_amount": 0,
        }
    ) == {
        "charges_paid_for_relevant_childcare_attributable_to_assessment_period": 0.0,
        "amount_considered_excessive_having_regard_to_paid_work_extent": 0.0,
        "amount_met_or_reimbursed_by_employer_or_some_other_person": 0.0,
        "secretary_of_state_work_transition_childcare_payment_meets_non_other_relevant_support_conditions": False,
        "amount_from_funds_provided_by_secretary_of_state_or_scottish_or_welsh_ministers_for_work_related_activity_or_training": 0.0,
        "secretary_of_state_work_transition_childcare_payment_amount": 0.0,
        "maximum_amount_specified_in_table_in_regulation_36": 0.0,
    }


def test_universal_credit_childcare_element_request_projects_regulation_34_inputs():
    request = build_universal_credit_childcare_element_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_childcare_element": 1_020,
                    "uc_maximum_childcare_element_amount": 1_800,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_CHILDCARE_ELEMENT_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_34_BASE}#input.charges_paid_for_relevant_childcare_attributable_to_assessment_period"
    ] == {
        "kind": "decimal",
        "value": "100.0",
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_34_BASE}#input.maximum_amount_specified_in_table_in_regulation_36"
    ] == {
        "kind": "decimal",
        "value": "150.0",
    }


def test_universal_credit_childcare_work_condition_projection_uses_adult_work_flags():
    assert project_universal_credit_childcare_work_condition_inputs(
        {
            "uc_childcare_adult_count": 2,
            "uc_childcare_any_adult_in_work": True,
            "uc_childcare_all_adults_in_work": False,
        }
    ) == {
        "claimant_in_paid_work": True,
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
        "claimant_is_member_of_couple": True,
        "other_member_in_paid_work": False,
        "other_member_has_limited_capability_for_work": False,
        "other_member_has_regular_and_substantial_caring_responsibilities_for_severely_disabled_person": False,
        "other_member_temporarily_absent_from_claimants_household": False,
    }

    single_projection = project_universal_credit_childcare_work_condition_inputs(
        {
            "uc_childcare_adult_count": 1,
            "uc_childcare_any_adult_in_work": True,
            "uc_childcare_all_adults_in_work": True,
        }
    )
    assert single_projection["claimant_is_member_of_couple"] is False
    assert single_projection["claimant_in_paid_work"] is True


def test_universal_credit_childcare_work_condition_request_projects_regulation_32_inputs():
    request = build_universal_credit_childcare_work_condition_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_childcare_adult_count": 2,
                    "uc_childcare_any_adult_in_work": True,
                    "uc_childcare_all_adults_in_work": False,
                    "uc_childcare_work_condition": False,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_32_BASE}#input.claimant_in_paid_work"
    ] == {
        "kind": "bool",
        "value": True,
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_32_BASE}#input.claimant_is_member_of_couple"
    ] == {
        "kind": "bool",
        "value": True,
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_32_BASE}#input.other_member_in_paid_work"
    ] == {
        "kind": "bool",
        "value": False,
    }


def test_adds_universal_credit_childcare_work_projection_columns():
    pd = pytest.importorskip("pandas")
    benunit = pd.DataFrame({"benunit_id": [10, 11, 12]})
    person = pd.DataFrame(
        {
            "person_benunit_id": [10, 10, 11],
            "is_adult": [True, True, True],
            "in_work": [True, False, True],
        }
    )

    projected = efrs_uk.add_universal_credit_childcare_work_projection_columns(
        benunit,
        person,
    ).set_index("benunit_id")

    assert projected.loc[10, "uc_childcare_adult_count"] == 2
    assert bool(projected.loc[10, "uc_childcare_any_adult_in_work"]) is True
    assert bool(projected.loc[10, "uc_childcare_all_adults_in_work"]) is False
    assert projected.loc[11, "uc_childcare_adult_count"] == 1
    assert bool(projected.loc[11, "uc_childcare_all_adults_in_work"]) is True
    assert projected.loc[12, "uc_childcare_adult_count"] == 0
    assert bool(projected.loc[12, "uc_childcare_any_adult_in_work"]) is False


def test_adds_pension_credit_child_addition_projection_columns():
    pd = pytest.importorskip("pandas")
    benunit = pd.DataFrame({"benunit_id": [10, 11, 12]})
    person = pd.DataFrame(
        {
            "person_benunit_id": [10, 10, 10, 11],
            "birth_year": [2010, 2018, 1980, 2019],
            "is_child_or_qualifying_young_person_for_pension_credit": [
                True,
                True,
                False,
                True,
            ],
            "dla": [0, 1, 0, 0],
            "pip": [0, 0, 0, 0],
            "receives_highest_dla_sc": [True, False, False, False],
            "receives_enhanced_pip_dl": [False, False, False, False],
        }
    )

    projected = efrs_uk.add_pension_credit_child_addition_projection_columns(
        benunit,
        person,
    ).set_index("benunit_id")

    assert projected.loc[10, "pc_child_addition_child_count"] == 2
    assert projected.loc[10, "pc_child_addition_standard_disabled_child_count"] == 1
    assert projected.loc[10, "pc_child_addition_severely_disabled_child_count"] == 1
    assert bool(projected.loc[10, "pc_child_addition_any_pre_2017_child"]) is True
    assert projected.loc[11, "pc_child_addition_child_count"] == 1
    assert bool(projected.loc[11, "pc_child_addition_any_pre_2017_child"]) is False
    assert projected.loc[12, "pc_child_addition_child_count"] == 0


def test_pension_credit_child_addition_request_projects_schedule_iia_inputs():
    request = build_pension_credit_child_addition_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 22,
                    "pc_child_addition_child_count": 2,
                    "pc_child_addition_standard_disabled_child_count": 1,
                    "pc_child_addition_severely_disabled_child_count": 1,
                    "pc_child_addition_any_pre_2017_child": True,
                }
            ],
            "benunit_ids": [22],
        },
        year=2026,
    )

    inputs_by_name = {
        item["name"]: item["value"] for item in request["dataset"]["inputs"]
    }
    assert request["queries"] == [
        {
            "entity_id": "benunit_22",
            "period": {
                "period_kind": "custom",
                "name": "benefit_week",
                "start": "2026-04-06",
                "end": "2026-04-12",
            },
            "outputs": [
                PENSION_CREDIT_CHILD_ADDITION_OUTPUTS["additional_amount_applicable"][
                    "axiom"
                ]
            ],
        }
    ]
    assert inputs_by_name[
        f"{PENSION_CREDIT_SCHEDULE_IIA_BASE}#input.claimant_responsible_child_or_qualifying_young_person_count"
    ] == {"kind": "integer", "value": 2}
    assert inputs_by_name[
        f"{PENSION_CREDIT_SCHEDULE_IIA_BASE}#input.claimant_responsible_disabled_not_severely_disabled_child_or_qualifying_young_person_count"
    ] == {"kind": "integer", "value": 1}
    assert inputs_by_name[
        f"{PENSION_CREDIT_SCHEDULE_IIA_BASE}#input.claimant_responsible_severely_disabled_child_or_qualifying_young_person_count"
    ] == {"kind": "integer", "value": 1}
    assert inputs_by_name[
        f"{PENSION_CREDIT_SCHEDULE_IIA_BASE}#input.eldest_child_or_qualifying_young_person_born_before_6_april_2017"
    ] == {"kind": "bool", "value": True}


def test_project_pension_credit_child_addition_inputs_defaults_to_zero():
    projected = project_pension_credit_child_addition_inputs({})

    assert projected == {
        "claimant_responsible_child_or_qualifying_young_person_count": 0,
        "claimant_responsible_disabled_not_severely_disabled_child_or_qualifying_young_person_count": 0,
        "claimant_responsible_severely_disabled_child_or_qualifying_young_person_count": 0,
        "eldest_child_or_qualifying_young_person_born_before_6_april_2017": False,
    }


def test_universal_credit_housing_costs_projection_uses_monthly_amount():
    projected = project_universal_credit_housing_costs_inputs(
        {"uc_housing_costs_element": 360}
    )

    assert projected["payments_are_in_respect_of_accommodation_for_section_11"] is True
    assert projected["accommodation_is_in_great_britain"] is True
    assert projected["accommodation_is_residential_accommodation"] is True
    assert projected["claimant_is_liable_to_make_accommodation_payments"] is True
    assert (
        projected[
            "claimant_is_treated_as_not_liable_to_make_accommodation_payments_by_regulations"
        ]
        is False
    )
    assert (
        projected["amount_determined_or_calculated_by_regulations_under_section_11"]
        == 30
    )


def test_universal_credit_housing_costs_request_projects_section_11_inputs():
    request = build_universal_credit_housing_costs_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "uc_housing_costs_element": 360,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_HOUSING_COSTS_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{WELFARE_REFORM_ACT_SECTION_11_BASE}#input.amount_determined_or_calculated_by_regulations_under_section_11"
    ] == {
        "kind": "decimal",
        "value": "30.0",
    }


def test_universal_credit_work_allowance_projection_uses_regulation_22_case_inputs():
    projected = project_universal_credit_work_allowance_inputs(
        {
            "num_adults": 1,
            "num_children": 1,
            "is_uc_work_allowance_eligible": True,
            "uc_housing_costs_element": 360,
        }
    )

    assert projected == {
        "claim_is_for_joint_claimants": False,
        "claimant_is_member_of_couple": False,
        "claimant_makes_claim_as_single_person": False,
        "joint_claimants_responsible_for_child_or_qualifying_young_person": False,
        "one_or_both_joint_claimants_have_limited_capability_for_work": False,
        "single_claimant_responsible_for_child_or_qualifying_young_person": True,
        "single_claimant_has_limited_capability_for_work": False,
        "award_contains_housing_costs_element": True,
    }

    assert (
        project_universal_credit_work_allowance_inputs(
            {
                "num_adults": 2,
                "num_children": 0,
                "is_uc_work_allowance_eligible": True,
                "uc_housing_costs_element": 0,
            }
        )["one_or_both_joint_claimants_have_limited_capability_for_work"]
        is True
    )


def test_universal_credit_work_allowance_request_projects_regulation_22_inputs():
    request = build_universal_credit_work_allowance_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "num_adults": 1,
                    "num_children": 1,
                    "is_uc_work_allowance_eligible": True,
                    "uc_housing_costs_element": 360,
                    "uc_work_allowance": 5_124,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_WORK_ALLOWANCE_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#input.award_contains_housing_costs_element"
    ] == {
        "kind": "bool",
        "value": True,
    }


def test_universal_credit_income_deduction_projection_uses_regulation_22_inputs():
    projected = project_universal_credit_income_deduction_inputs(
        {
            "num_adults": 1,
            "num_children": 1,
            "is_uc_work_allowance_eligible": True,
            "uc_housing_costs_element": 360,
            "uc_work_allowance": 5_124,
            "uc_earned_income": 6_876,
            "uc_unearned_income": 600,
        }
    )

    assert projected == {
        "claim_is_for_joint_claimants": False,
        "claimant_is_member_of_couple": False,
        "claimant_makes_claim_as_single_person": False,
        "joint_claimants_responsible_for_child_or_qualifying_young_person": False,
        "one_or_both_joint_claimants_have_limited_capability_for_work": False,
        "single_claimant_responsible_for_child_or_qualifying_young_person": True,
        "single_claimant_has_limited_capability_for_work": False,
        "award_contains_housing_costs_element": True,
        "claimant_earned_income_in_assessment_period": 1_000,
        "joint_claimants_combined_earned_income_in_assessment_period": 0.0,
        "claimant_unearned_income_in_assessment_period": 50,
        "joint_claimants_combined_unearned_income_in_assessment_period": 0.0,
    }

    joint_projection = project_universal_credit_income_deduction_inputs(
        {
            "num_adults": 2,
            "num_children": 0,
            "is_uc_work_allowance_eligible": True,
            "uc_housing_costs_element": 0,
            "uc_work_allowance": 8_520,
            "uc_earned_income": 15_480,
            "uc_unearned_income": 3_600,
        }
    )
    assert (
        joint_projection["joint_claimants_combined_earned_income_in_assessment_period"]
        == 2_000
    )
    assert (
        joint_projection[
            "joint_claimants_combined_unearned_income_in_assessment_period"
        ]
        == 300
    )
    assert (
        joint_projection["one_or_both_joint_claimants_have_limited_capability_for_work"]
        is True
    )


def test_universal_credit_income_deduction_request_projects_regulation_22_inputs():
    request = build_universal_credit_income_deduction_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "num_adults": 1,
                    "num_children": 1,
                    "is_uc_work_allowance_eligible": True,
                    "uc_housing_costs_element": 360,
                    "uc_work_allowance": 5_124,
                    "uc_earned_income": 6_876,
                    "uc_unearned_income": 600,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#input.claimant_earned_income_in_assessment_period"
    ] == {
        "kind": "decimal",
        "value": "1000.0",
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_22_BASE}#input.claimant_unearned_income_in_assessment_period"
    ] == {
        "kind": "decimal",
        "value": "50.0",
    }


def test_universal_credit_tariff_income_projection_uses_regulation_72_inputs():
    assert project_universal_credit_tariff_income_inputs(
        {
            "uc_assessable_capital": 6_001,
        }
    ) == {
        "person_capital": 6_001,
        "capital_is_disregarded": False,
        "actual_income_from_capital_taken_into_account_under_regulation_66_1_i_annuity": False,
        "actual_income_from_capital_taken_into_account_under_regulation_66_1_j_trust": False,
        "actual_income_derived_from_that_capital_due_to_be_paid_to_person_on_day_amount": 0.0,
    }


def test_universal_credit_assessable_capital_projection_uses_regulation_18_inputs():
    assert project_universal_credit_assessable_capital_inputs(
        {
            "uc_assessable_capital": 12_345,
        }
    ) == {
        "claim_is_for_joint_claimants": False,
        "claimant_is_member_of_couple": False,
        "claimant_makes_claim_as_single_person": False,
        "claimant_capital": 12_345,
        "other_member_of_couple_capital": 0.0,
    }


def test_universal_credit_assessable_capital_request_projects_regulation_18_inputs():
    request = build_universal_credit_assessable_capital_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_assessable_capital": 12_345,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "custom",
                "name": "day",
                "start": "2026-04-06",
                "end": "2026-04-06",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_ASSESSABLE_CAPITAL_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_18_BASE}#input.claimant_capital"
    ] == {
        "kind": "decimal",
        "value": "12345.0",
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_18_BASE}#input.other_member_of_couple_capital"
    ] == {
        "kind": "decimal",
        "value": "0.0",
    }


def test_universal_credit_tariff_income_request_projects_regulation_72_inputs():
    request = build_universal_credit_tariff_income_request(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "is_uc_eligible": True,
                    "uc_assessable_capital": 6_001,
                    "uc_tariff_income": 52.20,
                }
            ],
            "benunit_ids": [11],
        },
        year=2026,
    )

    assert request["mode"] == "explain"
    assert request["queries"] == [
        {
            "entity_id": "benunit_11",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS.values()
            ),
        }
    ]
    inputs_by_name = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_72_BASE}#input.person_capital"
    ] == {
        "kind": "decimal",
        "value": "6001.0",
    }
    assert inputs_by_name[
        f"{UNIVERSAL_CREDIT_REGULATION_72_BASE}#input.capital_is_disregarded"
    ] == {
        "kind": "bool",
        "value": False,
    }


def test_universal_credit_child_element_request_filters_to_positive_rows():
    request = build_universal_credit_request(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "uc_child_index": -1,
                    "uc_individual_child_element": 0,
                    "uc_individual_disabled_child_element": 0,
                    "uc_individual_severely_disabled_child_element": 0,
                },
                {
                    "person_id": 8,
                    "uc_child_index": 1,
                    "uc_is_child_born_before_child_limit": True,
                    "uc_individual_child_element": 351.88 * 12,
                    "uc_individual_disabled_child_element": 0,
                    "uc_individual_severely_disabled_child_element": 0,
                },
            ],
            "person_ids": [7, 8],
        },
        year=2026,
        surface="universal-credit-child-element",
    )

    assert request["queries"] == [
        {
            "entity_id": "person_8",
            "period": {
                "period_kind": "month",
                "name": "benefit_month",
                "start": "2026-04-01",
                "end": "2026-04-30",
            },
            "outputs": list(
                output["axiom"]
                for output in UNIVERSAL_CREDIT_CHILD_ELEMENT_OUTPUTS.values()
            ),
        }
    ]


def test_run_axiom_parameter_outputs_reads_generated_rulespec_parameters(tmp_path):
    program = tmp_path / "regulations" / "uksi" / "2013" / "376" / "36.yaml"
    program.parent.mkdir(parents=True)
    program.write_text(
        """
format: rulespec/v1
rules:
  - name: standard_allowance_single_under_25_amount
    kind: parameter
    dtype: Money
    period: Month
    versions:
      - effective_from: '0001-01-01'
        formula: |-
          300
      - effective_from: '2026-04-01'
        formula: |-
          338.58
""".strip()
    )

    results = efrs_uk.run_axiom_parameter_outputs(
        program=program,
        rulespec_root=tmp_path,
        request={
            "queries": [
                {
                    "period": {"start": "2026-04-01"},
                    "outputs": [
                        "uk:regulations/uksi/2013/376/36#standard_allowance_single_under_25_amount"
                    ],
                }
            ]
        },
    )

    assert results == [
        {
            "outputs": {
                "uk:regulations/uksi/2013/376/36#standard_allowance_single_under_25_amount": {
                    "value": {"value": "338.58"}
                }
            }
        }
    ]


def test_run_axiom_parameter_outputs_resolves_composed_program_imports(tmp_path):
    rulespec_root = tmp_path / "rulespec-uk"
    source = rulespec_root / "regulations" / "uksi" / "2013" / "376" / "36.yaml"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
format: rulespec/v1
rules:
  - name: carer_element_amount
    kind: parameter
    dtype: Money
    period: Month
    versions:
      - effective_from: '0001-01-01'
        formula: |-
          200
      - effective_from: '2026-04-01'
        formula: |-
          209.34
""".strip()
    )
    composed = tmp_path / "uk-uc-composed.yaml"
    composed.write_text(
        """
format: rulespec/v1
module:
  kind: composition
imports:
  - uk:regulations/uksi/2013/376/36
""".strip()
    )

    results = efrs_uk.run_axiom_parameter_outputs(
        program=composed,
        rulespec_root=rulespec_root,
        request={
            "queries": [
                {
                    "period": {"start": "2026-04-01"},
                    "outputs": ["uk:regulations/uksi/2013/376/36#carer_element_amount"],
                }
            ]
        },
    )

    assert results == [
        {
            "outputs": {
                "uk:regulations/uksi/2013/376/36#carer_element_amount": {
                    "value": {"value": "209.34"}
                }
            }
        }
    ]


def test_select_person_indices_uses_positive_weights_and_explicit_ids():
    rows = [
        {"person_id": 10, "person_weight": 0},
        {"person_id": 11, "person_weight": 2.5},
        {"person_id": 12, "person_weight": 3.5},
    ]

    assert select_person_indices(rows, sample_size=1) == [1]
    assert select_person_indices(rows, sample_size=0) == [1, 2]
    assert select_person_indices(rows, sample_size=1, person_ids=(12,)) == [2]

    with pytest.raises(SystemExit, match="not eligible"):
        select_person_indices(rows, sample_size=0, person_ids=(10,))


def test_policyengine_variables_for_surfaces_deduplicates_person_variables():
    assert policyengine_person_variables_for_surfaces(
        ["personal-allowance", "child-benefit"]
    ) == (
        "adjusted_net_income",
        "child_benefit_child_index",
        "child_benefit_respective_amount",
        "gift_aid_grossed_up",
        "personal_allowance",
    )
    assert policyengine_person_variables_for_surfaces(["income-tax-income-base"]) == (
        *sorted(
            (
                *INCOME_TAX_INCOME_BASE_COMPONENTS,
                *INCOME_TAX_SECTION_23_ADDITION_COMPONENTS,
                *INCOME_TAX_SECTION_23_REDUCTION_COMPONENTS,
                "adjusted_net_income",
                "income_tax",
                "total_income",
            )
        ),
    )
    assert policyengine_person_variables_for_surfaces(
        ["income-tax-section-13-dividend-income"]
    ) == (
        "dividend_income_tax",
        "earned_taxable_income",
        "received_allowances_dividend_income",
        "received_allowances_savings_income",
        "taxable_dividend_income",
        "taxable_savings_interest_income",
        "taxed_dividend_income",
    )
    assert policyengine_person_variables_for_surfaces(
        ["national-insurance-class-1"]
    ) == (
        "ni_class_1_employee",
        "ni_class_1_employee_additional",
        "ni_class_1_employee_primary",
        "ni_class_1_income",
        "ni_employee",
        "ni_liable",
    )
    assert policyengine_person_variables_for_surfaces(
        ["national-insurance-class-4"]
    ) == (
        "ni_class_1_employee",
        "ni_class_4_main",
        "ni_liable",
        "self_employment_income",
    )
    assert policyengine_person_variables_for_surfaces(["national-insurance-final"]) == (
        "national_insurance",
        "ni_class_1_employee",
        "ni_class_2",
        "ni_class_3",
        "ni_class_4",
    )
    assert policyengine_person_variables_for_surfaces(
        ["state-pension-credit-qualifying-age"]
    ) == (
        "age",
        "gender",
        "is_SP_age",
        "state_pension_age",
    )
    assert policyengine_person_variables_for_surfaces(["state-pension-final"]) == (
        "state_pension",
        "state_pension_reported",
        "state_pension_type",
    )
    assert policyengine_person_variables_for_surfaces(
        ["carer-support-payment-final"]
    ) == (
        "age",
        "care_hours",
        "carer_support_payment",
        "carers_allowance_reported",
        "country",
    )
    assert policyengine_person_variables_for_surfaces(
        ["scottish-child-payment-final"]
    ) == (
        "age",
        "is_scp_eligible",
        "scottish_child_payment",
        "would_claim_scp",
    )
    assert policyengine_person_variables_for_surfaces(
        ["severe-disablement-allowance-final"]
    ) == (
        "sda",
        "sda_reported",
    )
    assert policyengine_person_variables_for_surfaces(["esa-income-final"]) == (
        "esa_income_reported",
    )
    assert policyengine_person_variables_for_surfaces(["student-loan-repayment"]) == (
        "adjusted_net_income",
        "student_loan_plan",
        "student_loan_repayment",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["personal-allowance", "pension-credit"]
    ) == (
        "carer_minimum_guarantee_addition",
        "is_couple",
        "num_carers",
        "relation_type",
        "severe_disability_minimum_guarantee_addition",
        "standard_minimum_guarantee",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["state-pension-credit-savings-credit"]
    ) == (
        "is_savings_credit_eligible",
        "minimum_guarantee",
        "pension_credit_income",
        "relation_type",
        "savings_credit",
        "savings_credit_income",
        "standard_minimum_guarantee",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["state-pension-credit-guarantee-credit"]
    ) == (
        "guarantee_credit",
        "is_guarantee_credit_eligible",
        "minimum_guarantee",
        "pension_credit_income",
        "standard_minimum_guarantee",
    )
    assert policyengine_benunit_variables_for_surfaces(["pension-credit-final"]) == (
        "pension_credit",
        "pension_credit_entitlement",
        "would_claim_pc",
    )
    assert policyengine_benunit_variables_for_surfaces(["esa-income-final"]) == (
        "esa_income",
        "esa_income_eligible",
        "esa_income_tariff_income",
    )
    assert policyengine_benunit_variables_for_surfaces(["housing-benefit-final"]) == (
        "benefit_cap_reduction",
        "housing_benefit",
        "housing_benefit_pre_benefit_cap",
        "would_claim_housing_benefit",
    )
    assert policyengine_benunit_variables_for_surfaces(["state-pension-final"]) == ()
    assert policyengine_benunit_variables_for_surfaces(
        ["benefit-cap-relevant-amount"]
    ) == (
        "benefit_cap",
        "benunit_region",
        "num_adults",
        "num_children",
    )
    assert policyengine_person_variables_for_surfaces(
        ["universal-credit-child-element"]
    ) == (
        "uc_child_index",
        "uc_individual_child_element",
        "uc_individual_disabled_child_element",
        "uc_individual_severely_disabled_child_element",
        "uc_is_child_born_before_child_limit",
    )
    assert policyengine_benunit_variables_for_surfaces(
        [
            "universal-credit-standard-allowance",
            "universal-credit-carer-element",
        ]
    ) == (
        "uc_carer_element",
        "uc_standard_allowance",
        "uc_standard_allowance_claimant_type",
    )
    assert policyengine_benunit_variables_for_surfaces(["universal-credit-award"]) == (
        "is_uc_eligible",
        "uc_carer_element",
        "uc_child_element",
        "uc_childcare_element",
        "uc_disability_elements",
        "uc_housing_costs_element",
        "uc_income_reduction",
        "uc_maximum_amount",
        "uc_standard_allowance",
    )
    assert policyengine_benunit_variables_for_surfaces(["universal-credit-final"]) == (
        "benefit_cap_reduction",
        "universal_credit",
        "universal_credit_pre_benefit_cap",
        "would_claim_uc",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-housing-costs"]
    ) == ("uc_housing_costs_element",)
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-childcare-element"]
    ) == (
        "uc_childcare_element",
        "uc_maximum_childcare_element_amount",
    )
    assert policyengine_person_variables_for_surfaces(
        ["universal-credit-childcare-work-condition"]
    ) == (
        "in_work",
        "is_adult",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-childcare-work-condition"]
    ) == ("uc_childcare_work_condition",)
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-work-allowance"]
    ) == (
        "is_uc_work_allowance_eligible",
        "num_adults",
        "num_children",
        "uc_housing_costs_element",
        "uc_work_allowance",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-income-deduction"]
    ) == (
        "is_uc_work_allowance_eligible",
        "num_adults",
        "num_children",
        "uc_earned_income",
        "uc_housing_costs_element",
        "uc_income_reduction",
        "uc_maximum_amount",
        "uc_unearned_income",
        "uc_work_allowance",
    )
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-assessable-capital"]
    ) == ("uc_assessable_capital",)
    assert policyengine_benunit_variables_for_surfaces(
        ["universal-credit-tariff-income"]
    ) == (
        "is_uc_eligible",
        "uc_assessable_capital",
        "uc_tariff_income",
    )
    assert policyengine_benunit_variables_for_surfaces(["student-loan-repayment"]) == ()
    assert policyengine_person_variables_for_surfaces(
        ["income-tax-section-11d-savings-income"]
    ) == (
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
    )


def test_uk_efrs_coverage_report_counts_computed_pe_backlog(tmp_path):
    source_root = tmp_path / "variables"
    gov_root = source_root / "gov" / "hmrc"
    input_root = source_root / "input"
    gov_root.mkdir(parents=True)
    input_root.mkdir(parents=True)
    (gov_root / "income_tax.py").write_text(
        """
from policyengine_uk.model_api import *

class income_tax(Variable):
    entity = Person
    def formula(person, period, parameters):
        return person("taxable_income", period)

class personal_allowance(Variable):
    entity = Person
    def formula(person, period, parameters):
        return 12570
""".strip()
    )
    (input_root / "employment_income.py").write_text(
        """
from policyengine_uk.model_api import *

class employment_income(Variable):
    entity = Person
    adds = ["employment_income_before_lsr"]

class age(Variable):
    entity = Person
""".strip()
    )

    report = build_uk_efrs_coverage_report(
        policyengine_variables=[
            FakePolicyEngineVariable("income_tax", "person"),
            FakePolicyEngineVariable("personal_allowance", "person"),
            FakePolicyEngineVariable(
                "employment_income",
                "person",
                adds=["employment_income_before_lsr"],
            ),
            FakePolicyEngineVariable("age", "person"),
        ],
        source_root=source_root,
    )

    assert report.variables_total == 4
    assert report.computed_variables_total == 3
    assert report.computed_variables_by_entity == {"person": 3}
    assert report.computed_variables_by_domain == {"gov": 2, "input": 1}
    assert report.computed_covered_variables == [
        "income_tax",
        "personal_allowance",
    ]
    assert report.missing_variables_total == 1
    assert [variable.name for variable in report.missing_variables] == [
        "employment_income",
    ]


def test_uk_efrs_coverage_report_filters_domain_and_entity(tmp_path):
    source_root = tmp_path / "variables"
    (source_root / "gov").mkdir(parents=True)
    (source_root / "household").mkdir(parents=True)
    (source_root / "gov" / "tax.py").write_text(
        """
from policyengine_uk.model_api import *

class income_tax(Variable):
    entity = Person
    def formula(person, period, parameters):
        return 1

class universal_credit(Variable):
    entity = BenUnit
    def formula(benunit, period, parameters):
        return 1
""".strip()
    )
    (source_root / "household" / "net_income.py").write_text(
        """
from policyengine_uk.model_api import *

class hbai_household_net_income(Variable):
    entity = Household
    def formula(household, period, parameters):
        return 1
""".strip()
    )

    report = build_uk_efrs_coverage_report(
        policyengine_variables=[
            FakePolicyEngineVariable("income_tax", "person"),
            FakePolicyEngineVariable("universal_credit", "benunit"),
            FakePolicyEngineVariable("hbai_household_net_income", "household"),
        ],
        source_root=source_root,
        domain_filter="gov",
        entity_filter="benunit",
    )

    assert report.variables_total == 1
    assert report.computed_variables_total == 1
    assert report.missing_variables_total == 0
    assert report.missing_variables == []


def test_uk_efrs_coverage_report_serializes_json(tmp_path):
    source_root = tmp_path / "variables" / "gov"
    source_root.mkdir(parents=True)
    (source_root / "income_tax.py").write_text(
        """
from policyengine_uk.model_api import *

class income_tax(Variable):
    entity = Person
    def formula(person, period, parameters):
        return 1
""".strip()
    )

    report = build_uk_efrs_coverage_report(
        policyengine_variables=[FakePolicyEngineVariable("income_tax", "person")],
        source_root=source_root.parent,
    )

    payload = report.to_json()
    assert payload["missing_variables_total"] == 0
    assert payload["missing_variables"] == []
    assert "income_tax" in payload["covered_output_variables"]
    assert "personal_allowance" in payload["covered_output_variables"]


def test_uk_hbai_policy_coverage_report_classifies_policy_components(tmp_path):
    source_root = tmp_path / "variables"
    hbai_path = source_root / "household" / "income"
    hbai_path.mkdir(parents=True)
    (hbai_path / "hbai_household_net_income.py").write_text(
        """
from policyengine_uk.model_api import *

class hbai_household_net_income(Variable):
    entity = Household
    adds = [
        "employment_income",
        "council_tax_benefit",
        "free_school_meals",
        "free_school_fruit_veg",
        "free_school_milk",
        "free_tv_licence_value",
        "child_benefit",
        "esa_income",
        "esa_contrib",
        "housing_benefit",
        "universal_credit",
        "pension_credit",
        "working_tax_credit",
        "child_tax_credit",
        "tax_free_childcare",
        "afcs",
        "bsp",
        "pip",
        "dla",
        "iidb",
        "incapacity_benefit",
        "attendance_allowance",
        "carers_allowance",
        "jsa_contrib",
        "maternity_allowance",
        "sda",
        "ssmg",
        "scottish_child_payment",
        "carer_support_payment",
        "cost_of_living_support_payment",
        "state_pension",
        "statutory_sick_pay",
        "statutory_maternity_pay",
        "healthy_start_vouchers",
        "winter_fuel_allowance",
    ]
    subtracts = [
        "income_tax",
        "national_insurance",
        "student_loan_repayments",
        "council_tax",
        "domestic_rates",
        "maintenance_expenses",
        "LVT",
    ]
""".strip()
    )

    report = build_uk_hbai_policy_coverage_report(source_root=source_root)
    by_name = {component.name: component for component in report.components}

    assert report.adds == (
        "employment_income",
        "council_tax_benefit",
        "free_school_meals",
        "free_school_fruit_veg",
        "free_school_milk",
        "free_tv_licence_value",
        "child_benefit",
        "esa_income",
        "esa_contrib",
        "housing_benefit",
        "universal_credit",
        "pension_credit",
        "working_tax_credit",
        "child_tax_credit",
        "tax_free_childcare",
        "afcs",
        "bsp",
        "pip",
        "dla",
        "iidb",
        "incapacity_benefit",
        "attendance_allowance",
        "carers_allowance",
        "jsa_contrib",
        "maternity_allowance",
        "sda",
        "ssmg",
        "scottish_child_payment",
        "carer_support_payment",
        "cost_of_living_support_payment",
        "state_pension",
        "statutory_sick_pay",
        "statutory_maternity_pay",
        "healthy_start_vouchers",
        "winter_fuel_allowance",
    )
    assert report.subtracts == (
        "income_tax",
        "national_insurance",
        "student_loan_repayments",
        "council_tax",
        "domestic_rates",
        "maintenance_expenses",
        "LVT",
    )
    assert by_name["employment_income"].status == "fixed_input"
    assert by_name["employment_income"].policy_component is False
    assert by_name["council_tax_benefit"].status == "fixed_input"
    assert by_name["council_tax_benefit"].policy_component is False
    assert by_name["free_school_meals"].status == "fixed_input"
    assert by_name["free_school_meals"].policy_component is False
    assert by_name["free_school_fruit_veg"].status == "fixed_input"
    assert by_name["free_school_fruit_veg"].policy_component is False
    assert by_name["free_school_milk"].status == "fixed_input"
    assert by_name["free_school_milk"].policy_component is False
    assert by_name["free_tv_licence_value"].status == "partial"
    assert by_name["free_tv_licence_value"].policy_component is True
    assert by_name["child_benefit"].status == "exact"
    assert by_name["child_benefit"].surfaces == (
        "child-benefit",
        "child-benefit-final",
    )
    assert by_name["child_benefit"].covered_outputs == (
        "child_benefit_respective_amount",
        "child_benefit_entitlement",
        "child_benefit",
    )
    assert by_name["esa_contrib"].status == "fixed_input"
    assert by_name["esa_contrib"].policy_component is False
    assert by_name["afcs"].status == "fixed_input"
    assert by_name["afcs"].policy_component is False
    assert by_name["bsp"].status == "fixed_input"
    assert by_name["bsp"].policy_component is False
    assert by_name["iidb"].status == "fixed_input"
    assert by_name["iidb"].policy_component is False
    assert by_name["incapacity_benefit"].status == "fixed_input"
    assert by_name["incapacity_benefit"].policy_component is False
    assert by_name["jsa_contrib"].status == "fixed_input"
    assert by_name["jsa_contrib"].policy_component is False
    assert by_name["maternity_allowance"].status == "fixed_input"
    assert by_name["maternity_allowance"].policy_component is False
    assert by_name["statutory_sick_pay"].status == "fixed_input"
    assert by_name["statutory_sick_pay"].policy_component is False
    assert by_name["statutory_maternity_pay"].status == "fixed_input"
    assert by_name["statutory_maternity_pay"].policy_component is False
    assert by_name["healthy_start_vouchers"].status == "fixed_input"
    assert by_name["healthy_start_vouchers"].policy_component is False
    assert by_name["income_tax"].status == "exact"
    assert by_name["income_tax"].policy_component is True
    assert by_name["national_insurance"].status == "exact"
    assert by_name["national_insurance"].surfaces == (
        "national-insurance-class-1",
        "national-insurance-class-4",
        "national-insurance-class-4-final",
        "national-insurance-final",
    )
    assert by_name["national_insurance"].covered_outputs == (
        "ni_employee",
        "ni_class_4_main",
        "ni_class_4",
        "national_insurance",
    )
    assert by_name["student_loan_repayments"].status == "partial"
    assert by_name["universal_credit"].status == "exact"
    assert by_name["universal_credit"].surfaces == (
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
    )
    assert by_name["universal_credit"].covered_outputs == (
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
    )
    assert by_name["pension_credit"].status == "exact"
    assert by_name["pension_credit"].surfaces == (
        "state-pension-credit-guarantee-credit",
        "state-pension-credit-savings-credit",
        "pension-credit",
        "pension-credit-child-addition",
        "pension-credit-deemed-income",
        "pension-credit-final",
    )
    assert by_name["pension_credit"].covered_outputs == (
        "guarantee_credit",
        "savings_credit",
        "standard_minimum_guarantee",
        "severe_disability_minimum_guarantee_addition",
        "carer_minimum_guarantee_addition",
        "child_minimum_guarantee_addition",
        "pension_credit_deemed_income",
        "pension_credit",
    )
    assert by_name["esa_income"].status == "exact"
    assert by_name["esa_income"].surfaces == (
        "esa-income-tariff-income",
        "esa-income-final",
    )
    assert by_name["esa_income"].covered_outputs == (
        "esa_income_tariff_income",
        "esa_income",
    )
    assert by_name["housing_benefit"].status == "exact"
    assert by_name["housing_benefit"].surfaces == (
        "housing-benefit-working-age-tariff-income",
        "housing-benefit-pension-age-tariff-income",
        "housing-benefit-applicable-amount",
        "housing-benefit-entitlement",
        "housing-benefit-final",
    )
    assert by_name["housing_benefit"].covered_outputs == (
        "housing_benefit_tariff_income",
        "housing_benefit_applicable_amount",
        "housing_benefit_entitlement",
        "housing_benefit",
    )
    assert by_name["working_tax_credit"].status == "partial"
    assert by_name["child_tax_credit"].status == "partial"
    assert by_name["tax_free_childcare"].status == "partial"
    assert by_name["pip"].status == "exact"
    assert by_name["dla"].status == "exact"
    assert by_name["dla"].surfaces == (
        "disability-living-allowance-rates",
        "disability-living-allowance-final",
    )
    assert by_name["dla"].covered_outputs == (
        "dla_sc",
        "dla_m",
        "dla",
    )
    assert by_name["attendance_allowance"].status == "partial"
    assert by_name["carers_allowance"].status == "exact"
    assert by_name["carers_allowance"].surfaces == (
        "carers-allowance-rate",
        "carers-allowance-final",
    )
    assert by_name["sda"].status == "exact"
    assert by_name["sda"].surfaces == (
        "severe-disablement-allowance-rates",
        "severe-disablement-allowance-final",
    )
    assert by_name["sda"].covered_outputs == ("sda",)
    assert by_name["ssmg"].status == "partial"
    assert by_name["scottish_child_payment"].status == "exact"
    assert by_name["scottish_child_payment"].surfaces == (
        "scottish-child-payment-parameters",
        "scottish-child-payment-final",
    )
    assert by_name["scottish_child_payment"].covered_outputs == (
        "scottish_child_payment",
    )
    assert by_name["carer_support_payment"].status == "exact"
    assert by_name["carer_support_payment"].surfaces == (
        "carer-support-payment-parameters",
        "carer-support-payment-final",
    )
    assert by_name["carer_support_payment"].covered_outputs == (
        "carer_support_payment",
    )
    assert by_name["cost_of_living_support_payment"].status == "partial"
    assert by_name["state_pension"].status == "exact"
    assert by_name["state_pension"].surfaces == (
        "state-pension-rates",
        "state-pension-final",
    )
    assert by_name["winter_fuel_allowance"].status == "partial"
    assert by_name["council_tax"].status == "fixed_input"
    assert by_name["council_tax"].policy_component is False
    assert by_name["domestic_rates"].status == "fixed_input"
    assert by_name["domestic_rates"].policy_component is False
    assert by_name["LVT"].status == "out_of_scope"
    assert by_name["LVT"].policy_component is False
    assert report.policy_component_count == 23
    assert report.covered_policy_component_count == 23
    assert report.exact_policy_component_count == 14
    assert report.covered_policy_component_share == 1
    assert math.isclose(report.exact_policy_component_share, 14 / 23)


def test_uk_hbai_policy_coverage_report_reads_module_level_component_constants(
    tmp_path,
):
    source_root = tmp_path / "variables"
    hbai_path = source_root / "household" / "income"
    hbai_path.mkdir(parents=True)
    (hbai_path / "hbai_household_net_income.py").write_text(
        """
from policyengine_uk.model_api import *

HBAI_HOUSEHOLD_NET_INCOME_ADDS = [
    "employment_income",
    "dla",
]
HBAI_HOUSEHOLD_NET_INCOME_SUBTRACTS = [
    "income_tax",
]

class hbai_household_net_income(Variable):
    entity = Household

    def formula(household, period, parameters):
        return add(household, period, HBAI_HOUSEHOLD_NET_INCOME_ADDS) - add(
            household, period, HBAI_HOUSEHOLD_NET_INCOME_SUBTRACTS
        )
""".strip()
    )

    report = build_uk_hbai_policy_coverage_report(source_root=source_root)

    assert report.adds == ("employment_income", "dla")
    assert report.subtracts == ("income_tax",)
    assert report.status_counts == {
        "exact": 2,
        "fixed_input": 1,
    }
    assert report.policy_component_count == 2
    assert report.covered_policy_component_count == 2
    assert report.exact_policy_component_count == 2


def test_uk_hbai_policy_coverage_report_serializes_json(tmp_path):
    source_root = tmp_path / "variables" / "household"
    source_root.mkdir(parents=True)
    (source_root / "hbai_household_net_income.py").write_text(
        """
from policyengine_uk.model_api import *

class hbai_household_net_income(Variable):
    entity = Household
    adds = ["employment_income", "child_benefit"]
    subtracts = ["income_tax"]
""".strip()
    )

    report = build_uk_hbai_policy_coverage_report(source_root=source_root.parent)
    payload = report.to_json()

    assert payload["policy_component_count"] == 2
    assert payload["covered_policy_component_count"] == 2
    assert payload["exact_policy_component_count"] == 2
    assert payload["status_counts"] == {
        "exact": 2,
        "fixed_input": 1,
    }
    assert payload["activity_totals"] is None
    assert payload["components"][0]["name"] == "employment_income"


def test_policyengine_uk_version_guard_rejects_unpinned_version(monkeypatch):
    def fake_version(package):
        versions = {
            "policyengine-uk": "2.87.99",
        }
        return versions[package]

    monkeypatch.setattr(efrs_uk, "version", fake_version)

    with pytest.raises(SystemExit, match="policyengine-uk>=2.88 required"):
        require_policyengine_uk_versions()


def test_policyengine_uk_version_guard_allows_pinned_versions(monkeypatch):
    def fake_version(package):
        versions = {
            "policyengine-uk": "2.89.2",
        }
        return versions[package]

    monkeypatch.setattr(efrs_uk, "version", fake_version)

    require_policyengine_uk_versions()


def test_policyengine_uk_version_guard_names_coverage_command(monkeypatch):
    def fake_version(package):
        raise PackageNotFoundError(package)

    monkeypatch.setattr(efrs_uk, "version", fake_version)

    with pytest.raises(SystemExit, match="axiom-encode uk-populace-coverage"):
        require_policyengine_uk_versions(command="uk-populace-coverage")


def test_compare_outputs_reports_personal_allowance_mismatch():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "personal_allowance": 12_570,
                }
            ],
            "person_ids": [7],
        },
        axiom_outputs_by_surface={
            "personal-allowance": [
                {
                    "outputs": {
                        PERSONAL_ALLOWANCE_OUTPUTS["personal_allowance"][
                            "axiom"
                        ]: decimal_output(12_569)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_persons == 1
    assert report.compared_benunits == 0
    assert report.compared_values == 1
    assert len(report.mismatches) == 1
    assert report.oracle_divergences == []
    assert report.mismatches[0].entity_id == "person_7"
    assert report.output_summary[0]["mismatches"] == 1
    assert report.skipped_surfaces == []


def test_compare_outputs_rejects_missing_axiom_rows():
    with pytest.raises(ValueError, match="personal-allowance produced 0 Axiom"):
        compare_outputs(
            pe_data={
                "persons": [
                    {
                        "person_id": 7,
                        "personal_allowance": 12_570,
                    }
                ],
                "person_ids": [7],
            },
            axiom_outputs_by_surface={"personal-allowance": []},
            tolerance=0.01,
            relative_tolerance=2e-7,
        )


def test_compare_outputs_no_longer_classifies_personal_allowance_rounding_bug():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "personal_allowance": 12_569.5,
                }
            ],
            "person_ids": [7],
        },
        axiom_outputs_by_surface={
            "personal-allowance": [
                {
                    "outputs": {
                        PERSONAL_ALLOWANCE_OUTPUTS["personal_allowance"][
                            "axiom"
                        ]: decimal_output(12_570)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert len(report.mismatches) == 1
    assert report.mismatches[0].entity_id == "person_7"
    assert report.oracle_divergences == []
    assert report.output_summary[0]["mismatches"] == 1


def test_compare_outputs_compares_child_benefit_weekly_rate():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "child_benefit_child_index": -1,
                    "child_benefit_respective_amount": 0,
                },
                {
                    "person_id": 8,
                    "child_benefit_child_index": 1,
                    "child_benefit_respective_amount": 27.05 * WEEKS_IN_YEAR,
                },
            ],
            "person_ids": [7, 8],
        },
        axiom_outputs_by_surface={
            "child-benefit": [
                {
                    "outputs": {
                        CHILD_BENEFIT_OUTPUTS["child_benefit_weekly_rate"][
                            "axiom"
                        ]: decimal_output(27.05)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_persons == 2
    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []
    assert report.output_summary[0]["compared"] == 1


def test_compare_outputs_compares_child_benefit_final_weekly_amount():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 3,
                    "child_benefit": 0,
                    "child_benefit_entitlement": 44.95 * WEEKS_IN_YEAR,
                    "would_claim_child_benefit": False,
                }
            ],
            "benunit_ids": [3],
        },
        axiom_outputs_by_surface={
            "child-benefit-final": [
                {
                    "outputs": {
                        CHILD_BENEFIT_FINAL_OUTPUTS["child_benefit_weekly_amount"][
                            "axiom"
                        ]: decimal_output(0)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_benunits == 1
    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []
    assert report.output_summary[0]["compared"] == 1


def test_compare_outputs_compares_state_pension_final_weekly_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 3,
                    "state_pension": 200 * WEEKS_IN_YEAR,
                }
            ],
            "person_ids": [3],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "state-pension-final": [
                {
                    "outputs": {
                        STATE_PENSION_FINAL_OUTPUTS["state_pension_weekly_amount"][
                            "axiom"
                        ]: decimal_output(200)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_persons == 1
    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []
    assert report.output_summary[0]["compared"] == 1


def test_compare_outputs_compares_national_insurance_final_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 3,
                    "national_insurance": 2_900,
                }
            ],
            "person_ids": [3],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "national-insurance-final": [
                {
                    "outputs": {
                        NATIONAL_INSURANCE_FINAL_OUTPUTS[
                            "national_insurance_contribution"
                        ]["axiom"]: decimal_output(2_900)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_persons == 1
    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []
    assert report.output_summary[0]["compared"] == 1


def test_compare_outputs_transforms_benefit_cap_relevant_amount_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benefit_cap": 22_020,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "benefit-cap-relevant-amount": [
                {
                    "outputs": {
                        BENEFIT_CAP_RELEVANT_AMOUNT_OUTPUTS[
                            "benefit_cap_relevant_amount"
                        ]["axiom"]: decimal_output(1_835),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []


def test_compare_outputs_compares_applicable_universal_credit_standard_allowance():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_standard_allowance": 338.58 * 12,
                    "uc_standard_allowance_claimant_type": "SINGLE_YOUNG",
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-standard-allowance": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_STANDARD_ALLOWANCE_OUTPUTS[
                            "standard_allowance_single_under_25"
                        ]["axiom"]: decimal_output(338.58),
                        UNIVERSAL_CREDIT_STANDARD_ALLOWANCE_OUTPUTS[
                            "standard_allowance_single_25_or_over"
                        ]["axiom"]: decimal_output(424.90),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []
    assert [
        (item["output"], item["compared"])
        for item in report.output_summary
        if item["compared"]
    ] == [("standard_allowance_single_under_25", 1)]


def test_compare_outputs_compares_raw_protected_universal_credit_lcwra_amount():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_LCWRA_element": 429.80 * 12,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-lcwra-element": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_LCWRA_OUTPUTS[
                            "lcwra_element_standard_lcwra_claimant"
                        ]["axiom"]: decimal_output(217.26),
                        UNIVERSAL_CREDIT_LCWRA_OUTPUTS[
                            "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant"
                        ]["axiom"]: decimal_output(429.80),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []
    assert [
        (item["output"], item["compared"])
        for item in report.output_summary
        if item["compared"]
    ] == [
        (
            "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant",
            1,
        )
    ]


def test_compare_outputs_transforms_universal_credit_award_outputs_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_maximum_amount": 12_000,
                    "uc_income_reduction": 3_600,
                    "universal_credit_pre_benefit_cap": 0,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-award": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_AWARD_OUTPUTS[
                            "universal_credit_maximum_amount"
                        ]["axiom"]: decimal_output(1_000),
                        UNIVERSAL_CREDIT_AWARD_OUTPUTS[
                            "universal_credit_amounts_to_be_deducted"
                        ]["axiom"]: decimal_output(300),
                        UNIVERSAL_CREDIT_AWARD_OUTPUTS["universal_credit_award_amount"][
                            "axiom"
                        ]: decimal_output(700),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 3
    assert report.mismatches == []


def test_compare_outputs_compares_universal_credit_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "universal_credit": 10_750,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-final": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_FINAL_OUTPUTS[
                            "universal_credit_annual_amount"
                        ]["axiom"]: decimal_output(10_750),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_carers_allowance_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 2,
                    "carers_allowance": 4_495.40,
                },
            ],
            "person_ids": [2],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "carers-allowance-final": [
                {
                    "outputs": {
                        CARERS_ALLOWANCE_FINAL_OUTPUTS[
                            "carers_allowance_annual_amount"
                        ]["axiom"]: decimal_output(4_495.40),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_carer_support_payment_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 2,
                    "carer_support_payment": 5_103.80,
                },
            ],
            "person_ids": [2],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "carer-support-payment-final": [
                {
                    "outputs": {
                        CARER_SUPPORT_PAYMENT_FINAL_OUTPUTS[
                            "carer_support_payment_annual_amount"
                        ]["axiom"]: decimal_output(5_103.80),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_scottish_child_payment_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 2,
                    "scottish_child_payment": 1_466.40,
                },
            ],
            "person_ids": [2],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "scottish-child-payment-final": [
                {
                    "outputs": {
                        SCOTTISH_CHILD_PAYMENT_FINAL_OUTPUTS[
                            "scottish_child_payment_annual_amount"
                        ]["axiom"]: decimal_output(1_466.40),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_sda_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 2,
                    "sda": 6_206.20,
                },
            ],
            "person_ids": [2],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "severe-disablement-allowance-final": [
                {
                    "outputs": {
                        SDA_FINAL_OUTPUTS["severe_disablement_allowance_annual_amount"][
                            "axiom"
                        ]: decimal_output(6_206.20),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_dla_final_components_and_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 2,
                    "age": 10,
                    "dla": 8_148.40,
                    "dla_sc": 3_988.40,
                    "dla_m": 4_160.00,
                    "dla_sc_category": "MIDDLE",
                    "dla_m_category": "HIGHER",
                },
            ],
            "person_ids": [2],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "disability-living-allowance-final": [
                {
                    "outputs": {
                        DLA_FINAL_OUTPUTS[
                            "disability_living_allowance_self_care_weekly_amount"
                        ]["axiom"]: decimal_output(76.70),
                        DLA_FINAL_OUTPUTS[
                            "disability_living_allowance_mobility_weekly_amount"
                        ]["axiom"]: decimal_output(80.00),
                        DLA_FINAL_OUTPUTS["disability_living_allowance_annual_amount"][
                            "axiom"
                        ]: decimal_output(8_148.40),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 3
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_pip_final_components_total_and_enhanced_receipt():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 2,
                    "pip": 10_119.20,
                    "pip_dl": 5_959.20,
                    "pip_m": 4_160.00,
                    "pip_dl_category": "ENHANCED",
                    "pip_m_category": "ENHANCED",
                    "receives_enhanced_pip_dl": True,
                },
            ],
            "person_ids": [2],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "personal-independence-payment-final": [
                {
                    "outputs": {
                        PIP_FINAL_OUTPUTS["pip_daily_living_weekly_amount"][
                            "axiom"
                        ]: decimal_output(114.60),
                        PIP_FINAL_OUTPUTS["pip_mobility_weekly_amount"][
                            "axiom"
                        ]: decimal_output(80.00),
                        PIP_FINAL_OUTPUTS["personal_independence_payment_weekly_total"][
                            "axiom"
                        ]: decimal_output(194.60),
                        PIP_FINAL_OUTPUTS["receives_enhanced_daily_living_component"][
                            "axiom"
                        ]: judgment_output(True),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 4
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_pension_credit_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "pension_credit": 3_400,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit-final": [
                {
                    "outputs": {
                        PENSION_CREDIT_FINAL_OUTPUTS["pension_credit_annual_amount"][
                            "axiom"
                        ]: decimal_output(3_400),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_esa_income_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "esa_income": 2_080,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "esa-income-final": [
                {
                    "outputs": {
                        ESA_FINAL_OUTPUTS["income_related_esa_annual_amount"][
                            "axiom"
                        ]: decimal_output(2_080),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_compares_housing_benefit_final_annual_amount():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "housing_benefit": 4_160,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "housing-benefit-final": [
                {
                    "outputs": {
                        HOUSING_BENEFIT_FINAL_OUTPUTS["housing_benefit_annual_amount"][
                            "axiom"
                        ]: decimal_output(4_160),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_floors_universal_credit_award_expression():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_maximum_amount": 3_000,
                    "uc_income_reduction": 3_600,
                    "universal_credit_pre_benefit_cap": 0,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-award": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_AWARD_OUTPUTS[
                            "universal_credit_maximum_amount"
                        ]["axiom"]: decimal_output(250),
                        UNIVERSAL_CREDIT_AWARD_OUTPUTS[
                            "universal_credit_amounts_to_be_deducted"
                        ]["axiom"]: decimal_output(300),
                        UNIVERSAL_CREDIT_AWARD_OUTPUTS["universal_credit_award_amount"][
                            "axiom"
                        ]: decimal_output(0),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 3
    assert report.mismatches == []


def test_compare_outputs_transforms_universal_credit_housing_costs_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_housing_costs_element": 360,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-housing-costs": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_HOUSING_COSTS_OUTPUTS[
                            "section_11_amount_for_accommodation_payments"
                        ]["axiom"]: decimal_output(30),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_transforms_universal_credit_childcare_element_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_childcare_element": 1_020,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-childcare-element": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_CHILDCARE_ELEMENT_OUTPUTS[
                            "childcare_costs_element_amount"
                        ]["axiom"]: decimal_output(85),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_handles_universal_credit_childcare_work_condition():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_childcare_work_condition": True,
                },
                {
                    "benunit_id": 12,
                    "uc_childcare_work_condition": False,
                },
            ],
            "benunit_ids": [11, 12],
        },
        axiom_outputs_by_surface={
            "universal-credit-childcare-work-condition": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS[
                            "work_condition_met_for_assessment_period"
                        ]["axiom"]: judgment_output(True),
                    }
                },
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_CHILDCARE_WORK_CONDITION_OUTPUTS[
                            "work_condition_met_for_assessment_period"
                        ]["axiom"]: judgment_output(False),
                    }
                },
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 2
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_transforms_universal_credit_work_allowance_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_work_allowance": 5_124,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-work-allowance": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_WORK_ALLOWANCE_OUTPUTS[
                            "applicable_work_allowance_amount"
                        ]["axiom"]: decimal_output(427),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []


def test_compare_outputs_transforms_universal_credit_income_deduction_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_earned_income": 6_876,
                    "uc_unearned_income": 600,
                    "uc_income_reduction": 4_381.8,
                    "uc_maximum_amount": 12_000,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-income-deduction": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "earned_income_amount_subject_to_taper"
                        ]["axiom"]: decimal_output(573),
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "unearned_income_for_deduction"
                        ]["axiom"]: decimal_output(50),
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "universal_credit_award_deduction_from_maximum_amount"
                        ]["axiom"]: decimal_output(365.15),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 3
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_matches_income_tax_section_10_earned_income():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "pays_scottish_income_tax": False,
                    "basic_rate_earned_income": 37_700,
                    "higher_rate_earned_income": 22_300,
                    "add_rate_earned_income": 0,
                    "basic_rate_earned_income_tax": 7_540,
                    "higher_rate_earned_income_tax": 8_920,
                    "add_rate_earned_income_tax": 0,
                    "earned_income_tax": 16_460,
                }
            ],
            "person_ids": [7],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "income-tax-section-10-earned-income": [
                {
                    "outputs": {
                        INCOME_TAX_SECTION_10_OUTPUTS["income_charged_at_basic_rate"][
                            "axiom"
                        ]: decimal_output(37_700),
                        INCOME_TAX_SECTION_10_OUTPUTS["income_charged_at_higher_rate"][
                            "axiom"
                        ]: decimal_output(22_300),
                        INCOME_TAX_SECTION_10_OUTPUTS[
                            "income_charged_at_additional_rate"
                        ]["axiom"]: decimal_output(0),
                        INCOME_TAX_SECTION_10_OUTPUTS[
                            "tax_on_income_charged_at_basic_rate"
                        ]["axiom"]: decimal_output(7_540),
                        INCOME_TAX_SECTION_10_OUTPUTS[
                            "tax_on_income_charged_at_higher_rate"
                        ]["axiom"]: decimal_output(8_920),
                        INCOME_TAX_SECTION_10_OUTPUTS[
                            "tax_on_income_charged_at_additional_rate"
                        ]["axiom"]: decimal_output(0),
                        INCOME_TAX_SECTION_10_OUTPUTS[
                            "income_tax_on_section_10_income"
                        ]["axiom"]: decimal_output(16_460),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 7
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_matches_income_tax_section_11d_savings_income():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "basic_rate_savings_income": 700,
                    "higher_rate_savings_income": 800,
                    "add_rate_savings_income": 0,
                    "taxed_savings_income": 1_500,
                    "savings_income_tax": 460,
                }
            ],
            "person_ids": [7],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "income-tax-section-11d-savings-income": [
                {
                    "outputs": {
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_at_savings_basic_rate"
                        ]["axiom"]: decimal_output(700),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_at_savings_higher_rate"
                        ]["axiom"]: decimal_output(800),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_at_savings_additional_rate"
                        ]["axiom"]: decimal_output(0),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_under_section_11d"
                        ]["axiom"]: decimal_output(1_500),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "income_tax_on_section_11d_savings_income"
                        ]["axiom"]: decimal_output(460),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 5
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_allows_section_11d_efrs_float_precision():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "basic_rate_savings_income": 0,
                    "higher_rate_savings_income": 0,
                    "add_rate_savings_income": 7_571.5,
                    "taxed_savings_income": 7_571.5,
                    "savings_income_tax": 3_407.1748046875,
                }
            ],
            "person_ids": [7],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "income-tax-section-11d-savings-income": [
                {
                    "outputs": {
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_at_savings_basic_rate"
                        ]["axiom"]: decimal_output(0),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_at_savings_higher_rate"
                        ]["axiom"]: decimal_output(0),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_at_savings_additional_rate"
                        ]["axiom"]: decimal_output(7_571.275390625),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "savings_income_charged_under_section_11d"
                        ]["axiom"]: decimal_output(7_571.275390625),
                        INCOME_TAX_SECTION_11D_OUTPUTS[
                            "income_tax_on_section_11d_savings_income"
                        ]["axiom"]: decimal_output(3_407.07392578125),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 5
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_skips_scottish_income_tax_section_10_rows():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 7,
                    "pays_scottish_income_tax": True,
                    "earned_income_tax": 17_000,
                }
            ],
            "person_ids": [7],
            "benunits": [],
            "benunit_ids": [],
        },
        axiom_outputs_by_surface={
            "income-tax-section-10-earned-income": [
                {
                    "outputs": {
                        INCOME_TAX_SECTION_10_OUTPUTS[
                            "income_tax_on_section_10_income"
                        ]["axiom"]: decimal_output(16_460),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 0
    assert report.mismatches == []


def test_compare_outputs_skips_capped_universal_credit_income_deduction_final():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_earned_income": 12_000,
                    "uc_unearned_income": 0,
                    "uc_income_reduction": 3_000,
                    "uc_maximum_amount": 3_000,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-income-deduction": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "earned_income_amount_subject_to_taper"
                        ]["axiom"]: decimal_output(1_000),
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "unearned_income_for_deduction"
                        ]["axiom"]: decimal_output(0),
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "universal_credit_award_deduction_from_maximum_amount"
                        ]["axiom"]: decimal_output(550),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 2
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_skips_negative_unearned_income_deduction_final():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_earned_income": 24_000,
                    "uc_unearned_income": -1_200,
                    "uc_income_reduction": 12_000,
                    "uc_maximum_amount": 20_000,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-income-deduction": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "earned_income_amount_subject_to_taper"
                        ]["axiom"]: decimal_output(2_000),
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "unearned_income_for_deduction"
                        ]["axiom"]: decimal_output(-100),
                        UNIVERSAL_CREDIT_INCOME_DEDUCTION_OUTPUTS[
                            "universal_credit_award_deduction_from_maximum_amount"
                        ]["axiom"]: decimal_output(1_100),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 2
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_handles_universal_credit_assessable_capital():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_assessable_capital": 12_345,
                }
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-assessable-capital": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_ASSESSABLE_CAPITAL_OUTPUTS[
                            "claimant_capital_for_prescribed_capital_limit"
                        ]["axiom"]: decimal_output(12_345),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=0,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_transforms_universal_credit_tariff_income_monthly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "is_uc_eligible": True,
                    "uc_assessable_capital": 6_001,
                    "uc_tariff_income": 52.20,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-tariff-income": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS[
                            "capital_tariff_monthly_income"
                        ]["axiom"]: decimal_output(4.35),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_transforms_pension_credit_deemed_income_weekly():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "pension_credit_assessable_capital": 10_501,
                    "pension_credit_deemed_income": 2 * WEEKS_IN_YEAR,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit-deemed-income": [
                {
                    "outputs": {
                        PENSION_CREDIT_DEEMED_INCOME_OUTPUTS[
                            "capital_deemed_weekly_income"
                        ]["axiom"]: decimal_output(2),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


@pytest.mark.parametrize(
    ("surface", "outputs", "output_name", "row", "axiom_value"),
    [
        (
            "esa-income-tariff-income",
            ESA_TARIFF_INCOME_OUTPUTS,
            "capital_tariff_weekly_income",
            {
                "benunit_id": 11,
                "esa_income_assessable_capital": 6_251,
                "esa_income_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            2,
        ),
        (
            "jsa-income-tariff-income",
            JSA_TARIFF_INCOME_OUTPUTS,
            "capital_tariff_weekly_income",
            {
                "benunit_id": 11,
                "jsa_income_assessable_capital": 6_251,
                "jsa_income_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            2,
        ),
        (
            "income-support-tariff-income",
            INCOME_SUPPORT_TARIFF_INCOME_OUTPUTS,
            "capital_tariff_weekly_income",
            {
                "benunit_id": 11,
                "income_support_assessable_capital": 6_251,
                "income_support_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            2,
        ),
        (
            "housing-benefit-working-age-tariff-income",
            HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS,
            "capital_tariff_weekly_income",
            {
                "benunit_id": 11,
                "guarantee_credit": 0,
                "housing_benefit_any_over_sp_age": False,
                "housing_benefit_assessable_capital": 6_251,
                "housing_benefit_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            2,
        ),
        (
            "housing-benefit-pension-age-tariff-income",
            HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS,
            "capital_tariff_weekly_income",
            {
                "benunit_id": 11,
                "guarantee_credit": 0,
                "housing_benefit_any_over_sp_age": True,
                "housing_benefit_assessable_capital": 10_501,
                "housing_benefit_tariff_income": 2 * WEEKS_IN_YEAR,
            },
            2,
        ),
    ],
)
def test_compare_outputs_transforms_legacy_tariff_income_weekly(
    surface,
    outputs,
    output_name,
    row,
    axiom_value,
):
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [row],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            surface: [
                {
                    "outputs": {
                        outputs[output_name]["axiom"]: decimal_output(axiom_value),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_skips_legacy_tariff_income_above_capital_limit():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "esa_income_assessable_capital": 16_001,
                    "esa_income_tariff_income": 29 * WEEKS_IN_YEAR,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "esa-income-tariff-income": [
                {
                    "outputs": {
                        ESA_TARIFF_INCOME_OUTPUTS["capital_tariff_weekly_income"][
                            "axiom"
                        ]: decimal_output(0),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 0
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_splits_housing_benefit_tariff_income_age_surfaces():
    pe_data = {
        "persons": [],
        "person_ids": [],
        "benunits": [
            {
                "benunit_id": 11,
                "guarantee_credit": 0,
                "housing_benefit_any_over_sp_age": True,
                "housing_benefit_assessable_capital": 10_501,
                "housing_benefit_tariff_income": 2 * WEEKS_IN_YEAR,
            },
        ],
        "benunit_ids": [11],
    }

    working_age_report = compare_outputs(
        pe_data=pe_data,
        axiom_outputs_by_surface={
            "housing-benefit-working-age-tariff-income": [
                {
                    "outputs": {
                        HOUSING_BENEFIT_WORKING_AGE_TARIFF_INCOME_OUTPUTS[
                            "capital_tariff_weekly_income"
                        ]["axiom"]: decimal_output(0),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )
    pension_age_report = compare_outputs(
        pe_data=pe_data,
        axiom_outputs_by_surface={
            "housing-benefit-pension-age-tariff-income": [
                {
                    "outputs": {
                        HOUSING_BENEFIT_PENSION_AGE_TARIFF_INCOME_OUTPUTS[
                            "capital_tariff_weekly_income"
                        ]["axiom"]: decimal_output(2),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert working_age_report.compared_values == 0
    assert pension_age_report.compared_values == 1
    assert pension_age_report.mismatches == []


def test_compare_outputs_skips_undefined_universal_credit_tariff_income():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "is_uc_eligible": False,
                    "uc_assessable_capital": 20_000,
                    "uc_tariff_income": 0,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-tariff-income": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_TARIFF_INCOME_OUTPUTS[
                            "capital_tariff_monthly_income"
                        ]["axiom"]: decimal_output(243.60),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 0
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_skips_rebalanced_universal_credit_lcwra_health_element():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "uc_LCWRA_element": 426.5063 * 12,
                },
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "universal-credit-lcwra-element": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_LCWRA_OUTPUTS[
                            "lcwra_element_standard_lcwra_claimant"
                        ]["axiom"]: decimal_output(217.26),
                        UNIVERSAL_CREDIT_LCWRA_OUTPUTS[
                            "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant"
                        ]["axiom"]: decimal_output(429.80),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 0
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_classifies_known_policyengine_universal_credit_rates():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 8,
                    "uc_child_index": 1,
                    "uc_is_child_born_before_child_limit": True,
                    "uc_individual_child_element": 350.526123 * 12,
                    "uc_individual_disabled_child_element": 0,
                    "uc_individual_severely_disabled_child_element": 0,
                },
            ],
            "person_ids": [8],
        },
        axiom_outputs_by_surface={
            "universal-credit-child-element": [
                {
                    "outputs": {
                        UNIVERSAL_CREDIT_CHILD_ELEMENT_OUTPUTS[
                            "child_element_first_child_or_qualifying_young_person"
                        ]["axiom"]: decimal_output(351.88)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.mismatches == []
    assert len(report.oracle_divergences) == 1
    assert report.oracle_divergences[0].issue_url.endswith("/issues/1741")


def test_compare_outputs_classifies_known_policyengine_child_benefit_amounts():
    report = compare_outputs(
        pe_data={
            "persons": [
                {
                    "person_id": 8,
                    "child_benefit_child_index": 1,
                    "child_benefit_respective_amount": 26.935709699992934
                    * WEEKS_IN_YEAR,
                },
            ],
            "person_ids": [8],
        },
        axiom_outputs_by_surface={
            "child-benefit": [
                {
                    "outputs": {
                        CHILD_BENEFIT_OUTPUTS["child_benefit_weekly_rate"][
                            "axiom"
                        ]: decimal_output(27.05)
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.mismatches == []
    assert len(report.oracle_divergences) == 1
    assert report.oracle_divergences[0].issue_url.endswith("/issues/1739")


def test_compare_outputs_classifies_known_policyengine_pension_credit_rates():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_couple": False,
                    "severe_disability_minimum_guarantee_addition": 0,
                    "carer_minimum_guarantee_addition": 0,
                    "num_carers": 0,
                    "standard_minimum_guarantee": 229.3929826081932 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit": [
                {
                    "outputs": {
                        PENSION_CREDIT_OUTPUTS["standard_minimum_guarantee"][
                            "axiom"
                        ]: decimal_output(238.00),
                        PENSION_CREDIT_OUTPUTS["severe_disability_additional_amount"][
                            "axiom"
                        ]: decimal_output(0),
                        PENSION_CREDIT_OUTPUTS["carer_additional_amount"][
                            "axiom"
                        ]: decimal_output(0),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.mismatches == []
    assert len(report.oracle_divergences) == 1
    assert report.oracle_divergences[0].entity_id == "benunit_11"
    assert report.oracle_divergences[0].issue_url.endswith("/issues/1740")


def test_compare_outputs_no_longer_classifies_policyengine_savings_credit_bug():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 79791,
                    "savings_credit": 4022.257080078125,
                    "standard_minimum_guarantee": 18889.0,
                    "minimum_guarantee": 27838.2,
                }
            ],
            "benunit_ids": [79791],
        },
        axiom_outputs_by_surface={
            "state-pension-credit-savings-credit": [
                {
                    "outputs": {
                        f"{STATE_PENSION_CREDIT_SECTION_3_BASE}#savings_credit": decimal_output(
                            1045.2
                        )
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=0,
    )

    assert len(report.mismatches) == 1
    assert report.mismatches[0].entity_id == "benunit_79791"
    assert report.oracle_divergences == []


def test_compare_outputs_handles_state_pension_credit_guarantee_credit():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 12,
                    "minimum_guarantee": 14_560,
                    "guarantee_credit": 3_560,
                }
            ],
            "benunit_ids": [12],
        },
        axiom_outputs_by_surface={
            "state-pension-credit-guarantee-credit": [
                {
                    "outputs": {
                        STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS[
                            "appropriate_minimum_guarantee"
                        ]["axiom"]: decimal_output(14_560),
                        STATE_PENSION_CREDIT_GUARANTEE_CREDIT_OUTPUTS[
                            "guarantee_credit"
                        ]["axiom"]: decimal_output(3_560),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=0,
    )

    assert report.compared_values == 2
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_handles_pension_credit_child_addition():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 22,
                    "child_minimum_guarantee_addition": 307.44 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [22],
        },
        axiom_outputs_by_surface={
            "pension-credit-child-addition": [
                {
                    "outputs": {
                        PENSION_CREDIT_CHILD_ADDITION_OUTPUTS[
                            "additional_amount_applicable"
                        ]["axiom"]: decimal_output(307.44),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=0,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert report.oracle_divergences == []


def test_compare_outputs_classifies_known_policyengine_pension_credit_additions():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_couple": False,
                    "severe_disability_minimum_guarantee_addition": 0,
                    "carer_minimum_guarantee_addition": 47.9466 * WEEKS_IN_YEAR,
                    "num_carers": 1,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit": [
                {
                    "outputs": {
                        PENSION_CREDIT_OUTPUTS["standard_minimum_guarantee"][
                            "axiom"
                        ]: decimal_output(238.00),
                        PENSION_CREDIT_OUTPUTS["severe_disability_additional_amount"][
                            "axiom"
                        ]: decimal_output(0),
                        PENSION_CREDIT_OUTPUTS["carer_additional_amount"][
                            "axiom"
                        ]: decimal_output(48.15),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.mismatches == []
    assert len(report.oracle_divergences) == 1
    assert report.oracle_divergences[0].output == "carer_additional_amount"
    assert report.oracle_divergences[0].issue_url.endswith("/issues/1742")


def test_compare_outputs_classifies_known_policyengine_pension_credit_severe_addition():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_couple": False,
                    "severe_disability_minimum_guarantee_addition": 85.682
                    * WEEKS_IN_YEAR,
                    "carer_minimum_guarantee_addition": 0,
                    "num_carers": 0,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit": [
                {
                    "outputs": {
                        PENSION_CREDIT_OUTPUTS["standard_minimum_guarantee"][
                            "axiom"
                        ]: decimal_output(238.00),
                        PENSION_CREDIT_OUTPUTS["severe_disability_additional_amount"][
                            "axiom"
                        ]: decimal_output(86.05),
                        PENSION_CREDIT_OUTPUTS["carer_additional_amount"][
                            "axiom"
                        ]: decimal_output(0),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.mismatches == []
    assert len(report.oracle_divergences) == 1
    assert report.oracle_divergences[0].output == "severe_disability_additional_amount"
    assert report.oracle_divergences[0].issue_url.endswith("/issues/1742")


def test_compare_outputs_does_not_hide_wrong_pension_credit_additional_rate():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_couple": False,
                    "severe_disability_minimum_guarantee_addition": 0,
                    "carer_minimum_guarantee_addition": 47.9466 * WEEKS_IN_YEAR,
                    "num_carers": 1,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit": [
                {
                    "outputs": {
                        PENSION_CREDIT_OUTPUTS["standard_minimum_guarantee"][
                            "axiom"
                        ]: decimal_output(238.00),
                        PENSION_CREDIT_OUTPUTS["severe_disability_additional_amount"][
                            "axiom"
                        ]: decimal_output(0),
                        PENSION_CREDIT_OUTPUTS["carer_additional_amount"][
                            "axiom"
                        ]: decimal_output(44.00),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.oracle_divergences == []
    assert len(report.mismatches) == 1
    assert report.mismatches[0].output == "carer_additional_amount"


def test_compare_outputs_does_not_hide_wrong_pension_credit_severe_addition_rate():
    report = compare_outputs(
        pe_data={
            "persons": [],
            "person_ids": [],
            "benunits": [
                {
                    "benunit_id": 11,
                    "benunit_weight": 1,
                    "relation_type": "SINGLE",
                    "is_couple": False,
                    "severe_disability_minimum_guarantee_addition": 85.682
                    * WEEKS_IN_YEAR,
                    "carer_minimum_guarantee_addition": 0,
                    "num_carers": 0,
                    "standard_minimum_guarantee": 238.00 * WEEKS_IN_YEAR,
                }
            ],
            "benunit_ids": [11],
        },
        axiom_outputs_by_surface={
            "pension-credit": [
                {
                    "outputs": {
                        PENSION_CREDIT_OUTPUTS["standard_minimum_guarantee"][
                            "axiom"
                        ]: decimal_output(238.00),
                        PENSION_CREDIT_OUTPUTS["severe_disability_additional_amount"][
                            "axiom"
                        ]: decimal_output(82.00),
                        PENSION_CREDIT_OUTPUTS["carer_additional_amount"][
                            "axiom"
                        ]: decimal_output(0),
                    }
                }
            ]
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.oracle_divergences == []
    assert len(report.mismatches) == 1
    assert report.mismatches[0].output == "severe_disability_additional_amount"


def test_compare_uk_efrs_runs_axiom_personal_allowance(
    monkeypatch,
    tmp_path,
):
    rulespec_root = tmp_path / "rulespec-uk"
    program = rulespec_root / PERSONAL_ALLOWANCE_PROGRAM_PATH
    program.parent.mkdir(parents=True)
    program.write_text("format: rulespec/v1\n")
    axiom_rules = tmp_path / "axiom-rules-engine"
    axiom_rules.mkdir()
    captured = {}

    monkeypatch.setattr(
        efrs_uk,
        "load_policyengine_uk_data",
        lambda **_: {
            "persons": [
                {
                    "person_id": 7,
                    "person_weight": 1,
                    "adjusted_net_income": 20_000,
                    "gift_aid_grossed_up": 0,
                    "personal_allowance": 12_570,
                }
            ],
            "person_ids": [7],
        },
    )

    def fake_run_axiom_program(**kwargs):
        captured.update(kwargs)
        return [
            {
                "outputs": {
                    PERSONAL_ALLOWANCE_OUTPUTS["personal_allowance"][
                        "axiom"
                    ]: decimal_output(12_570)
                }
            }
        ]

    monkeypatch.setattr(efrs_uk, "run_axiom_surface", fake_run_axiom_program)

    report = compare_uk_efrs(
        workspace_root=tmp_path,
        rulespec_root=None,
        axiom_rules_path=None,
        year=2026,
        sample_size=100,
        surface="personal-allowance",
        dataset="",
        data_folder=Path(".axiom/policyengine-data"),
        populace_year=2023,
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.compared_values == 1
    assert report.mismatches == []
    assert captured["program"] == program
    assert captured["rulespec_root"] == rulespec_root.resolve()
    assert captured["axiom_rules_path"] == axiom_rules.resolve()
    assert captured["request"]["queries"][0]["entity_id"] == "person_7"


def test_main_returns_nonzero_when_requested_for_mismatches(monkeypatch, tmp_path):
    monkeypatch.setattr(efrs_uk, "resolve_workspace_root", lambda root: tmp_path)
    monkeypatch.setattr(
        efrs_uk,
        "compare_uk_efrs",
        lambda **_: efrs_uk.UKEFRSComparisonReport(
            compared_persons=1,
            compared_benunits=0,
            compared_values=1,
            mismatches=[
                efrs_uk.UKEFRSComparisonRow(
                    surface="personal-allowance",
                    entity_id="person_7",
                    output="personal_allowance",
                    axiom=0,
                    policyengine=1,
                    diff=-1,
                )
            ],
            oracle_divergences=[],
            output_summary=[],
            skipped_surfaces=[],
            projection_notes=[],
        ),
    )

    assert (
        efrs_uk.main(
            argparse.Namespace(
                root=None,
                rulespec_root=None,
                axiom_rules_engine_path=None,
                year=2026,
                sample_size=100,
                surface="all",
                dataset="",
                data_folder=Path(".axiom/policyengine-data"),
                populace_year=2023,
                tolerance=0.01,
                relative_tolerance=2e-7,
                person_ids=None,
                json=True,
                fail_on_mismatch=True,
            )
        )
        == 1
    )
