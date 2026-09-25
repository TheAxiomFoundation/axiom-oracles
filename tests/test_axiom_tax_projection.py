import hashlib
import json

import pytest

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
    attach_axiom_tax_itemization_choice_to_case,
)
from axiom_oracles.core.case import Case, Concepts, Entity


def test_axiom_tax_projection_maps_family_inputs_and_relations() -> None:
    case = Case(
        case_id="family",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 38,
                    Concepts.YEARLY_EARNED_INCOME: 20_000,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 8,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    records = projected.metadata["axiom_input_records"]
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in records
    }

    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.filing_status")
    ] == 1
    assert by_key[("tax_unit", "us:statutes/26/1401#input.filing_status")] == 1
    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.wages")] == 70_000
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/1401#input."
            "international_social_security_agreement_under_section_233_in_effect",
        )
    ] is False
    assert by_key[
        ("tax_unit", "us:statutes/26/26#input.net_investment_income_tax")
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/32/c/2#input."
            "employee_compensation_includible_in_gross_income",
        )
    ] == 70_000
    assert by_key[
        ("tax_unit", "us:statutes/26/32/c/2#input.pension_or_annuity_amount")
    ] == 0
    assert by_key[
        ("person-3", "us:tax/federal-income-tax#input.is_tax_unit_dependent")
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/151#input.tin_included_on_return_claiming_exemption")
    ] is True
    assert by_key[
        ("person-1", "us:statutes/26/151#input.is_taxpayer")
    ] is True
    assert by_key[
        ("person-2", "us:statutes/26/151#input.is_spouse_of_taxpayer")
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/151#input.is_taxpayer")
    ] is False
    assert by_key[
        ("person-3", "us:statutes/26/151#input.is_spouse_of_taxpayer")
    ] is False
    assert by_key[
        ("person-3", "us:statutes/26/151#input.filing_status")
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/1/h#input."
            "net_capital_gain_taken_into_account_as_investment_income_under_section_163_d_4_B_iii",
        )
    ] == 0
    assert by_key[
        ("person-3", "us:tax/federal-income-tax#input.age")
    ] == 8
    assert by_key[
        (
            "person-3",
            "us:statutes/26/32#input."
            "qualifying_child_under_section_152_c_as_modified_for_eitc",
        )
    ] is True
    assert by_key[
        (
            "person-3",
            "us:statutes/26/32#input."
            "qualifying_child_name_age_and_tin_included_on_return",
        )
    ] is True
    assert by_key[
        (
            "person-3",
            "us:statutes/26/32#input."
            "taxpayer_entitled_to_section_151_deduction_for_child_or_would_be_but_for_section_152_e",
        )
    ] is True
    assert by_key[
        (
            "person-3",
            "us:statutes/26/32#input."
            "qualifying_child_marital_status_requires_section_151_entitlement",
        )
    ] is False
    assert by_key[
        ("person-3", "us:statutes/26/24/h#input.qualifying_child_described_in_subsection_c")
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/24/h#input.ctc_child_satisfies_subsection_c")
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/24/h#input.ctc_person_satisfies_dependency_rules")
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/24/h#input.dependent_under_section_152")
    ] is True
    assert by_key[
        (
            "person-3",
            "us:statutes/26/152/c#input."
            "individual_is_child_of_taxpayer_or_descendant_of_such_child",
        )
    ] is True
    assert by_key[
        (
            "person-3",
            "us:statutes/26/152/c#input.individual_age_at_close_of_calendar_year",
        )
    ] == 8
    assert by_key[
        (
            "person-3",
            "us:statutes/26/152/c#input."
            "individual_principal_place_of_abode_with_taxpayer_fraction",
        )
    ] == 1
    assert by_key[
        ("person-3", "us:statutes/26/152/c#input.filing_status")
    ] == 0
    assert by_key[
        (
            "person-1",
            "us:statutes/26/152/c#input."
            "individual_is_child_of_taxpayer_or_descendant_of_such_child",
        )
    ] is False
    assert by_key[
        ("person-1", "us:tax/federal-income-tax#input.is_taxpayer")
    ] is True
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/63/c#input."
            "married_individual_filing_separate_return_where_either_spouse_itemizes_deductions",
        )
    ] is False
    assert by_key[
        ("tax_unit", "us:statutes/26/63/c#input.nonresident_alien_individual")
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/63/c#input."
            "return_under_section_443_a_1_for_less_than_12_months_due_to_accounting_period_change",
        )
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:policies/irs/rev-proc-2025-32/standard-deduction#input."
            "additional_standard_deduction_entitlement_count_under_subsection_f",
        )
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:policies/irs/rev-proc-2025-32/standard-deduction#input."
            "may_be_claimed_as_dependent_by_another_taxpayer",
        )
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:policies/irs/rev-proc-2025-32/standard-deduction#input."
            "individual_is_unmarried_and_not_surviving_spouse",
        )
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/63/c#input."
            "estate_or_trust_common_trust_fund_or_partnership",
        )
    ] is False
    assert (
        "tax_unit",
        "us:statutes/26/86#input."
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
    ) not in by_key
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "title_II_monthly_benefits_received_during_taxable_year",
        )
    ] == 0
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.adjusted_gross_income",
    ) not in by_key
    assert ("tax_unit", "us:statutes/26/63#input.gross_income") not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/6401#input."
        "credits_allowable_under_subpart_c_excluding_section_33_for_overpayment",
    ) not in by_key
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/6401#input."
            "nonresident_withholding_credit_treated_as_refundable_amount",
        )
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/6401#input."
            "section_6013_g_or_h_election_in_effect_for_taxable_year",
        )
    ] is False
    assert by_key[
        ("tax_unit", "us:statutes/26/24/h#input.filing_status_is_joint_return")
    ] is True
    assert by_key[
        ("tax_unit", "us:statutes/26/22#input.social_security_title_ii_benefits_excluded_from_gross_income")
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/22#input."
            "workers_compensation_treated_as_social_security_benefit",
        )
    ] == 0
    assert by_key[
        ("tax_unit", "us:statutes/26/32#input.childless_taxpayer_or_spouse_age_eligible_for_eitc")
    ] is True
    assert by_key[
        ("tax_unit", "us:statutes/26/32#input.taxpayer_is_qualifying_child_of_another_taxpayer")
    ] is False
    assert by_key[
        ("tax_unit", "us:statutes/26/32#input.taxable_year_is_full_12_months")
    ] is True
    assert by_key[
        ("tax_unit", "us:statutes/26/32#input.taxpayer_is_married_under_section_7703_a")
    ] is True
    assert by_key[
        ("tax_unit", "us:statutes/26/7703#input.spouse_dies_during_taxable_year")
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/7703#input.taxpayer_married_at_close_of_taxable_year",
        )
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/7703#input.person_is_child_within_federal_tax_child_definition")
    ] is True
    assert by_key[
        ("tax_unit", "us:statutes/26/63/c#input.taxable_year_begins_after_2025")
    ] is True
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/63/c#input.cost_of_living_adjustment_under_section_1_f_3",
        )
    ] == pytest.approx(350 / 15_750)
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/21#relation.qualifying_individual_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/22#relation.taxpayer_or_spouse_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/24/h#relation.dependent_of_tax_unit"
    } == {
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation.co_dependent_of_tax_unit"
    } == {
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/32#relation.qualifying_child_of_tax_unit"
    } == {
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/151#relation.exemption_individual_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/7703#relation.living_apart_child_of_tax_unit"
    } == {
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation."
        "business_income_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation."
        "filer_adjusted_earnings_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
    }
    assert len(projected.metadata["axiom_relations"]) == 29
    assert "axiom_input_record_overlays" not in projected.metadata
    assert "axiom_result_selection" not in projected.metadata


def test_axiom_tax_itemization_choice_is_oracle_comparison_metadata() -> None:
    case = Case(case_id="case-1", period="2026")

    projected = attach_axiom_tax_itemization_choice_to_case(case)

    assert projected.metadata["axiom_result_selection"] == {
        "strategy": "min",
        "output": "us:statutes/26/6401#income_tax",
    }
    itemization_candidates = [
        {
            record["name"]: record["value"]
            for record in overlay
        }
        for overlay in projected.metadata["axiom_input_record_overlays"]
    ]
    assert itemization_candidates == [
        {
            "us:statutes/26/63#input."
            "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year": True,
            "us:statutes/26/63#input."
            "individual_makes_election_to_itemize_deductions_for_taxable_year": False,
        },
        {
            "us:statutes/26/63#input."
            "individual_who_does_not_elect_to_itemize_deductions_for_taxable_year": False,
            "us:statutes/26/63#input."
            "individual_makes_election_to_itemize_deductions_for_taxable_year": True,
        },
    ]


def test_axiom_tax_projection_routes_social_security_to_section_86() -> None:
    case = Case(
        case_id="social-security",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 70,
                    Concepts.YEARLY_EARNED_INCOME: 10_000,
                    Concepts.SOCIAL_SECURITY_BENEFITS: 20_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert (
        "tax_unit",
        "us:statutes/26/86#input."
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
    ) not in by_key
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "title_II_monthly_benefits_received_during_taxable_year",
        )
    ] == 20_000
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "railroad_retirement_additional_tier_1_monthly_annuity_amount",
        )
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "early_delivered_social_security_benefit_checks_deemed_received_in_taxable_year",
        )
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "inclusion_by_reason_of_prior_year_lump_sum_portion_before_lump_sum_limitation",
        )
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "taxpayer_makes_lump_sum_election_for_prior_year_portion",
        )
    ] is False
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.taxable_social_security_benefits_included",
    ) not in by_key
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }
    assert (
        generated_rules_by_name[
            "adjusted_gross_income_before_listed_exclusions_and_social_security_inclusion"
        ]["versions"][0]["formula"]
        == "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933"
    )


def test_axiom_tax_projection_routes_self_employment_through_sections_1402_and_164() -> None:
    case = Case(
        case_id="self-employment",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 53,
                    Concepts.SELF_EMPLOYMENT_INCOME: 2_004.071,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/1402/a#input."
            "self_employment_trade_or_business_gross_income",
        )
    ] == 2_004.071
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/1402/a#input.self_employment_trade_or_business_deductions",
        )
    ] == 0
    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/1402/a#input.partnership_section_702_a_8_income_or_loss",
        )
    ] == 0
    assert by_key[
        ("tax_unit", "us:statutes/26/164/f#input.taxpayer_is_individual")
    ] is True
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.self_employment_income",
    ) not in by_key
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.filer_adjusted_earnings",
    ) not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/24/d#input.taxable_earned_income_under_section_32",
    ) not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/24/d#input.self_employment_1401_taxes",
    ) not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/86#input."
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
    ) not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/63#input.deduction_provided_in_section_199A",
    ) not in by_key


def test_axiom_tax_projection_routes_dependent_self_employment_through_member_qbi() -> None:
    case = Case(
        case_id="dependent-self-employment",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 56,
                    Concepts.YEARLY_EARNED_INCOME: 245_994.781,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 23,
                    Concepts.SELF_EMPLOYMENT_INCOME: 2_004.071,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    qbi_relation_rows = {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation."
        "business_income_of_tax_unit"
    }
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }

    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/1402/a#input."
            "self_employment_trade_or_business_gross_income",
        )
    ] == 0
    assert by_key[
        (
            "person-2",
            "us:tax/oracle-bridge#input."
            "person_self_employment_income_for_qbid",
        )
    ] == 2_004.071
    assert qbi_relation_rows == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
    }
    assert "person_adjusted_earnings_for_eitc" in generated_rules_by_name
    assert "person_self_employment_tax_ald_for_qbid" in generated_rules_by_name
    assert "self_employment_tax_ald_for_agi" in generated_rules_by_name
    assert "sum_where(filer_adjusted_earnings_of_tax_unit" in (
        generated_rules_by_name["taxable_earned_income_under_section_32"]["versions"][
            0
        ]["formula"]
    )
    assert "self_employment_tax_ald_for_agi" in (
        generated_rules_by_name[
            "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933"
        ]["versions"][0]["formula"]
    )
    qualified_business_income_formula = generated_rules_by_name[
        "qualified_business_income"
    ]["versions"][0]["formula"]
    assert "person_self_employment_tax_ald_for_qbid" in (
        generated_rules_by_name["business_income_for_qbid"]["versions"][0]["formula"]
    )
    assert "- self_employment_tax_deduction" not in qualified_business_income_formula


def test_axiom_tax_projection_floors_eitc_adjusted_earnings_per_filer() -> None:
    case = Case(
        case_id="negative-spouse-self-employment",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 61,
                    Concepts.YEARLY_EARNED_INCOME: 5_466.55,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 59,
                    Concepts.SELF_EMPLOYMENT_INCOME: -10_019.35,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }

    assert by_key[
        (
            "person-2",
            "us:tax/oracle-bridge#input."
            "person_self_employment_income_for_qbid",
        )
    ] == -10_019.35
    assert "max(0, person_payroll_earnings" in (
        generated_rules_by_name["person_adjusted_earnings_for_eitc"]["versions"][0][
            "formula"
        ]
    )
    assert "sum_where(filer_adjusted_earnings_of_tax_unit" in (
        generated_rules_by_name["taxable_earned_income_under_section_32"]["versions"][
            0
        ]["formula"]
    )


def test_axiom_tax_projection_uses_tax_unit_social_security_for_section_86() -> None:
    case = Case(
        case_id="dependent-social-security",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 59,
                    Concepts.SELF_EMPLOYMENT_INCOME: 60_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 15,
                    Concepts.SOCIAL_SECURITY_BENEFITS: 5_500,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/86#input."
            "title_II_monthly_benefits_received_during_taxable_year",
        )
    ] == 5_500


def test_axiom_tax_projection_uses_tax_unit_wages_for_ctc_payroll_tax() -> None:
    case = Case(
        case_id="dependent-worker-ctc",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 10_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 16,
                    Concepts.YEARLY_EARNED_INCOME: 90_000,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 12,
                },
            ),
            Entity(
                "person-4",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 9,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.wages")] == 10_000
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.employee_social_security_tax",
    ) not in by_key
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.employee_medicare_tax",
    ) not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/24/d#input.employee_3101_3201a_taxes",
    ) not in by_key
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation.payroll_member_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
        ("person-3", "tax_unit"),
        ("person-4", "tax_unit"),
    }

    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }
    assert "sum_where(payroll_member_of_tax_unit" in (
        generated_rules_by_name["employee_3101_3201a_taxes"]["versions"][0][
            "formula"
        ]
    )
    assert "employee_has_payroll_wages" in (
        generated_rules_by_name["employee_3101_3201a_taxes"]["versions"][0][
            "formula"
        ]
    )


def test_axiom_tax_projection_routes_qbi_through_person_relation_rows() -> None:
    case = Case(
        case_id="qbi",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 37,
                    Concepts.RENTAL_INCOME: 1_127.323,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 38,
                    Concepts.RENTAL_INCOME: -11_272.103,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    qbi_relation_rows = {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation."
        "business_income_of_tax_unit"
    }

    assert by_key[
        (
            "person-1",
            "us:tax/oracle-bridge#input."
            "person_rental_income_for_qbid",
        )
    ] == 1_127.323
    assert by_key[
        (
            "person-2",
            "us:tax/oracle-bridge#input."
            "person_rental_income_for_qbid",
        )
    ] == -11_272.103
    assert qbi_relation_rows == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
    }
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.qualified_business_income_deduction",
    ) not in by_key


def test_axiom_tax_projection_matches_pe_childless_eitc_age_proxy() -> None:
    case = Case(
        case_id="pe-childless-eitc-age-proxy",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 71,
                    Concepts.YEARLY_EARNED_INCOME: 7_653.171,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 69,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 45,
                    Concepts.YEARLY_EARNED_INCOME: 9_970.988,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        (
            "tax_unit",
            "us:statutes/26/32#input."
            "childless_taxpayer_or_spouse_age_eligible_for_eitc",
        )
    ] is True


def test_axiom_tax_projection_limits_head_of_household_to_qualifying_dependents() -> None:
    case = Case(
        case_id="dependent-above-qualifying-child-age",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 39,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 19,
                    Concepts.YEARLY_EARNED_INCOME: 7_653,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.filing_status")] == 0


def test_axiom_tax_projection_infers_head_of_household_for_low_income_young_adult_dependent() -> None:
    case = Case(
        case_id="single-parent-with-young-adult-dependent",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 39,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Dependent",
                    Concepts.PERSON_AGE: 22,
                    Concepts.YEARLY_EARNED_INCOME: 0,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.filing_status")] == 3


def test_axiom_tax_projection_does_not_treat_high_income_disabled_adult_as_head_of_household_dependent() -> None:
    case = Case(
        case_id="single-filer-with-high-income-disabled-adult",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 66,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Dependent",
                    Concepts.PERSON_AGE: 34,
                    Concepts.DISABLED: True,
                    Concepts.YEARLY_EARNED_INCOME: 21_866,
                    Concepts.SELF_EMPLOYMENT_INCOME: 5_010,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.filing_status")] == 0


def test_axiom_tax_projection_infers_head_of_household_for_qualifying_child() -> None:
    case = Case(
        case_id="single-parent-with-qualifying-child",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 39,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 5,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.filing_status")] == 3


def test_axiom_tax_projection_does_not_synthesize_qualified_dividends() -> None:
    case = Case(
        case_id="dividends",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 45,
                    Concepts.DIVIDEND_INCOME: 1_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        ("tax_unit", "us:statutes/26/1411#input.dividend_income")
    ] == 1_000
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.qualified_dividend_income")
    ] == 0


def test_axiom_tax_projection_uses_qualified_dividend_leaf_input() -> None:
    case = Case(
        case_id="qualified-dividends",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 45,
                    Concepts.DIVIDEND_INCOME: 1_000,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 600,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        ("tax_unit", "us:statutes/26/1411#input.dividend_income")
    ] == 1_000
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.qualified_dividend_income")
    ] == 600


def test_axiom_tax_projection_separates_dependent_preferential_income_from_agi() -> None:
    case = Case(
        case_id="dependent-preferential-income",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 45,
                    Concepts.YEARLY_EARNED_INCOME: 100_000,
                    Concepts.DIVIDEND_INCOME: 1_000,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 600,
                    Concepts.SHORT_TERM_CAPITAL_GAINS: 100,
                    Concepts.LONG_TERM_CAPITAL_GAINS: 200,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 15,
                    Concepts.DIVIDEND_INCOME: 500,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 300,
                    Concepts.SHORT_TERM_CAPITAL_GAINS: 40,
                    Concepts.LONG_TERM_CAPITAL_GAINS: 50,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:statutes/26/1411#input.dividend_income")] == 1_500
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.qualified_dividend_income")
    ] == 900
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.short_term_capital_gains")
    ] == 140
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.long_term_capital_gains")
    ] == 250
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input.filer_dividend_income",
        )
    ] == 1_000
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input."
            "filer_short_term_capital_gains",
        )
    ] == 100
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input."
            "filer_long_term_capital_gains",
        )
    ] == 200
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input."
            "capital_gains_tax_qualified_dividend_income",
        )
    ] == 900
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input."
            "capital_gains_tax_short_term_capital_gains",
        )
    ] == 140
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input."
            "capital_gains_tax_long_term_capital_gains",
        )
    ] == 250


def test_axiom_tax_projection_uses_oldest_adults_as_filers() -> None:
    case = Case(
        case_id="shared-household",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 32,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 45,
                    Concepts.YEARLY_EARNED_INCOME: 150_000,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 44,
                    Concepts.YEARLY_EARNED_INCOME: 200_000,
                },
            ),
            Entity(
                "person-4",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 8,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.wages")] == 350_000
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.filing_status")
    ] == 1
    assert by_key[
        ("person-1", "us:tax/federal-income-tax#input.is_tax_unit_dependent")
    ] is True
    assert by_key[
        ("person-2", "us:tax/federal-income-tax#input.is_taxpayer")
    ] is True
    assert by_key[
        ("person-3", "us:tax/federal-income-tax#input.is_spouse")
    ] is True


def test_axiom_tax_projection_treats_18_year_old_as_potential_spouse() -> None:
    case = Case(
        case_id="young-adult-tax-unit",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 30_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 18,
                    Concepts.YEARLY_EARNED_INCOME: 0,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 12,
                    Concepts.YEARLY_EARNED_INCOME: 0,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.filing_status")
    ] == 1
    assert by_key[
        ("person-2", "us:tax/federal-income-tax#input.is_spouse")
    ] is True
    assert by_key[
        ("person-2", "us:tax/federal-income-tax#input.is_tax_unit_dependent")
    ] is False
    assert by_key[
        ("person-3", "us:tax/federal-income-tax#input.is_tax_unit_dependent")
    ] is True


def test_axiom_tax_projection_keeps_zero_earning_second_adult_as_spouse() -> None:
    case = Case(
        case_id="one-earner-couple",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 65,
                    Concepts.YEARLY_EARNED_INCOME: 100_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 56,
                    Concepts.YEARLY_EARNED_INCOME: 0,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.filing_status")
    ] == 1
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.additional_senior_deduction",
    ) not in by_key
    assert by_key[
        ("person-2", "us:tax/federal-income-tax#input.is_spouse")
    ] is True


def test_axiom_tax_projection_maps_standard_deduction_blind_fact() -> None:
    case = Case(
        case_id="blind-senior",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 65,
                    Concepts.BLIND: True,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        ("person-1", "us:statutes/26/63/c#input.is_blind")
    ] is True
    assert (
        "person-1",
        "us:statutes/26/63/c#input.is_aged_65_or_over",
    ) not in by_key


def test_axiom_tax_projection_derives_additional_senior_deduction_in_bridge() -> None:
    case = Case(
        case_id="high-income-senior",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 70,
                    Concepts.YEARLY_EARNED_INCOME: 80_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.additional_senior_deduction",
    ) not in by_key


def test_axiom_tax_projection_reduces_each_senior_deduction_amount_for_phaseout() -> None:
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }
    formula = generated_rules_by_name["additional_senior_deduction"]["versions"][0][
        "formula"
    ]

    deduction = eval(
        formula,
        {"__builtins__": {}},
        {
            "max": max,
            "additional_senior_deduction_amount": 6_000,
            "additional_senior_deduction_eligible_count": 2,
            "additional_senior_deduction_phaseout_amount": 600,
        },
    )

    assert deduction == 10_800


def test_axiom_tax_projection_counts_age_and_blindness_separately() -> None:
    case = Case(
        case_id="senior-blind-filer",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 70,
                    Concepts.BLIND: True,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        (
            "tax_unit",
            "us:policies/irs/rev-proc-2025-32/standard-deduction"
            "#input.additional_standard_deduction_entitlement_count_under_subsection_f",
        )
    ] == 2


def test_axiom_tax_projection_uses_case_supplied_tax_unit_inputs() -> None:
    case = Case(
        case_id="itemizer",
        period="2026",
        metadata={
            "axiom_tax_unit_inputs": {
                "state_sales_tax": 1_000,
                "tip_income_deduction": 500,
                "overtime_income_deduction": 250,
                "charitable_deduction_for_non_itemizers": 100,
            }
        },
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 100_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        (
            "tax_unit",
            "us:tax/federal-income-tax#input.state_sales_tax",
        )
    ] == 1_000
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.itemized_taxable_income_deductions",
    ) not in by_key
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.adjusted_gross_income",
    ) not in by_key
    assert ("tax_unit", "us:statutes/26/63#input.gross_income") not in by_key
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.modified_adjusted_gross_income",
    ) not in by_key
    assert (
        "tax_unit",
        "us:statutes/26/63#input.deduction_provided_in_section_199A",
    ) not in by_key
    assert by_key[
        ("tax_unit", "us:statutes/26/63#input.deduction_provided_in_section_224")
    ] == 500
    assert by_key[
        ("tax_unit", "us:statutes/26/63#input.deduction_provided_in_section_225")
    ] == 250
    assert by_key[
        ("tax_unit", "us:statutes/26/63#input.deduction_provided_in_section_170_p")
    ] == 100
    assert not any("tax_unit_itemizes" in name for _, name in by_key)
    assert "axiom_input_record_overlays" not in projected.metadata


def test_axiom_tax_projection_computes_itemized_leaves_and_colorado_tax_wiring() -> None:
    case = Case(
        case_id="co-itemizer",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
        facts={
            Concepts.PROPERTY_TAX_PAID: 2_000,
            Concepts.MORTGAGE_INTEREST_PAID: 5_000,
            Concepts.ITEMIZED_DEDUCTIONS_OTHER: 300,
        },
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 100_000,
                    Concepts.DIVIDEND_INCOME: 1_500,
                    Concepts.INTEREST_INCOME: 100,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }

    assert by_key[
        ("tax_unit", "us:tax/oracle-bridge#input.is_colorado_tax_unit")
    ] is True
    assert by_key[
        (
            "tax_unit",
            "us:tax/federal-income-tax#input.individual_is_nonresident_alien",
        )
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:tax/federal-income-tax#input.individual_is_noncitizen_territory_resident",
        )
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:tax/federal-income-tax#input.social_security_agreement_under_section_233_applies_to_nonresident_alien",
        )
    ] is False
    assert by_key[
        (
            "tax_unit",
            "us:tax/federal-income-tax#input.wages_paid_to_individual_for_section_1401_a",
        )
    ] == 100_000
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.real_estate_taxes")
    ] == 2_000
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.deductible_mortgage_interest")
    ] == 5_000
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.misc_deduction")
    ] == 300
    assert by_key[
        ("person-1", "us:tax/oracle-bridge#input.person_dividend_income")
    ] == 1_500
    assert by_key[
        ("person-1", "us:tax/oracle-bridge#input.person_taxable_interest_income")
    ] == 100
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/oracle-bridge#relation.co_withheld_income_tax_member_of_tax_unit"
    } == {("person-1", "tax_unit")}
    assert "state_withheld_income_tax" in generated_rules_by_name
    assert (
        "contribution_and_benefit_base_under_section_230_of_social_security_act"
        in generated_rules_by_name
    )
    assert "itemized_taxable_income_deductions" in generated_rules_by_name
    assert "state_income_tax" in generated_rules_by_name
    assert "loss_ald" in generated_rules_by_name
    assert "limited_capital_loss" in generated_rules_by_name
    assert "limited_business_loss" in generated_rules_by_name
    assert (
        generated_rules_by_name["qualified_passenger_vehicle_loan_interest_deduction"][
            "versions"
        ][0]["formula"]
        == "auto_loan_interest_deduction"
    )
    assert "co_pension_subtraction_income" not in generated_rules_by_name
    assert "co_pension_subtraction_cap_after_social_security" not in (
        generated_rules_by_name
    )
    assert (
        "positive_capital_gains_for_agi"
        in generated_rules_by_name["gross_income_before_social_security_benefits"][
            "versions"
        ][0]["formula"]
    )
    assert (
        "filer_short_term_capital_gains"
        not in generated_rules_by_name["gross_income_before_social_security_benefits"][
            "versions"
        ][0]["formula"]
    )
    assert (
        "loss_ald"
        in generated_rules_by_name[
            "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933"
        ]["versions"][0]["formula"]
    )
    # The 39-22-104(3)(p) addback reaches only the section 63
    # itemized-or-standard deduction, not the other current-law deductions.
    assert (
        "standard_deduction"
        in generated_rules_by_name["co_taxable_income_deductions_for_addback"][
            "versions"
        ][0]["formula"]
    )
    assert (
        "current_law_deductions"
        not in generated_rules_by_name["co_taxable_income_deductions_for_addback"][
            "versions"
        ][0]["formula"]
    )
    assert (
        "co_modified_agi"
        in generated_rules_by_name["co_sales_tax_refund_base"]["versions"][0][
            "formula"
        ]
    )
    assert (
        "title_II_monthly_benefits_received_during_taxable_year"
        in generated_rules_by_name["co_modified_agi"]["versions"][0]["formula"]
    )
    assert (
        "co_sales_tax_refund"
        in generated_rules_by_name["co_refundable_credits"]["versions"][0]["formula"]
    )
    assert (
        "co_head_pension_subtraction"
        in generated_rules_by_name["co_pension_subtraction"]["versions"][0]["formula"]
    )
    assert (
        "co_spouse_pension_subtraction"
        in generated_rules_by_name["co_pension_subtraction"]["versions"][0]["formula"]
    )
    assert (
        "co_spouse_social_security_benefits"
        in generated_rules_by_name["co_spouse_taxable_social_security"]["versions"][0][
            "formula"
        ]
    )


def test_axiom_tax_projection_rejects_case_supplied_tax_aggregates() -> None:
    case = Case(
        case_id="aggregate-inputs",
        period="2026",
        metadata={
            "axiom_tax_unit_inputs": {
                "adjusted_gross_income": 103_000,
                "additional_senior_deduction": 6_000,
                "deduction_provided_in_section_199A": 2_000,
                "itemized_taxable_income_deductions": 20_000,
                "irs_gross_income": 105_000,
                "qualified_business_income_deduction": 2_000,
                "salt_deduction": 10_000,
                "self_employment_tax_ald": 1_000,
                "state_income_tax": 4_000,
                "state_withheld_income_tax": 4_000,
                "taxable_earned_income_under_section_32": 90_000,
            }
        },
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 100_000,
                },
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="calculator-derived aggregate inputs"):
        attach_axiom_tax_inputs_to_case(case)


def test_axiom_tax_projection_derives_alaska_pfd_for_tax_filers_from_scope() -> None:
    case = Case(
        case_id="alaska-couple-with-dependent",
        period="2026",
        metadata={"scope": {"type": "census_county", "geoid": "02170"}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 38,
                    Concepts.YEARLY_EARNED_INCOME: 20_000,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 8,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert (
        "tax_unit",
        "us:statutes/26/86#input."
        "adjusted_gross_income_determined_without_regard_to_sections_86_85_c_135_137_221_911_931_933",
    ) not in by_key
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.adjusted_gross_income",
    ) not in by_key
    assert ("tax_unit", "us:statutes/26/63#input.gross_income") not in by_key
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.earned_income",
    ) not in by_key
    assert by_key[
        (
            "tax_unit",
            "us:tax/oracle-bridge#input."
            "alaska_permanent_fund_dividend_eligible_person_count",
        )
    ] == 2


def test_axiom_tax_projection_counts_young_adult_as_other_dependent() -> None:
    case = Case(
        case_id="young-adult-dependent",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 45,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 23,
                    Concepts.YEARLY_EARNED_INCOME: 0,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    assert by_key[
        ("person-2", "us:tax/federal-income-tax#input.is_tax_unit_dependent")
    ] is True
    assert by_key[
        ("person-2", "us:statutes/26/24/h#input.dependent_under_section_152")
    ] is True
    assert by_key[
        ("person-2", "us:statutes/26/24/h#input.qualifying_child_described_in_subsection_c")
    ] is False
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/24/h#relation.dependent_of_tax_unit"
    } == {("person-2", "tax_unit")}


def test_axiom_tax_projection_rejects_external_itemization_status() -> None:
    case = Case(
        case_id="bad-itemization-input",
        period="2026",
        metadata={"axiom_tax_unit_inputs": {"tax_unit_itemizes": True}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 100_000,
                },
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="must not include itemization status"):
        attach_axiom_tax_inputs_to_case(case)


def test_axiom_tax_projection_computes_eitc_disqualified_investment_income() -> None:
    """32(i)'s input is computed from filer investment income, never defaulted.

    Leaving eitc_relevant_investment_income to _TAX_UNIT_NUMERIC_DEFAULTS
    zeroed the disqualified-income gate and granted EITC to units above the
    $12,200 limit (the ecps-projection-defaults-eitc-investment-income
    class): interest + dividends + rent + positive net capital gain.
    """
    case = Case(
        case_id="eitc-invest",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 3_000,
                    Concepts.INTEREST_INCOME: 1_000,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 2_000,
                    Concepts.RENTAL_INCOME: 500,
                    Concepts.LONG_TERM_CAPITAL_GAINS: 12_000,
                    Concepts.SHORT_TERM_CAPITAL_GAINS: -2_000,
                },
            ),
        ),
    )

    projected = attach_axiom_tax_inputs_to_case(case)
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }

    # 1,000 + 2,000 + 500 + max(0, 12,000 - 2,000) = 13,500 — over the
    # $12,200 Rev. Proc. 2025-32 maximum, so the composed 32(i) gate must
    # actually see it.
    assert by_key[
        (
        "tax_unit",
        "us:tax/federal-income-tax#input.eitc_relevant_investment_income",
    )
    ] == 13_500


# Married filing separately. The expectations below are projected INPUT
# values (what the projection hands the engine), fixed by the statute reading
# documented in tax_projection.py, never engine outputs.

_CO_SCOPE = {"type": "census_state", "geoid": "08"}
_FIS = "us:tax/federal-income-tax#input."


def _person(entity_id: str, relation: str, age: int, **facts) -> Entity:
    return Entity(
        entity_id,
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: relation,
            Concepts.PERSON_AGE: age,
            **facts,
        },
    )


def _projected(case: Case) -> dict[tuple[str, str], object]:
    records = attach_axiom_tax_inputs_to_case(case).metadata["axiom_input_records"]
    by_key: dict[tuple[str, str], object] = {}
    for record in records:
        key = (record["entity_id"], record["name"])
        # One record per (entity, ref): a duplicate would make the dict hide
        # a conflicting value.
        assert key not in by_key, key
        by_key[key] = record["value"]
    return by_key


def _mfs_case(
    case_id: str,
    *,
    filer_age: int = 40,
    wages: float = 40_000,
    dependents: tuple[Entity, ...] = (),
    **facts,
) -> Case:
    return Case(
        case_id=case_id,
        period="2026",
        facts={
            Concepts.STATE_CODE: "CO",
            Concepts.MARRIED_FILING_SEPARATELY: True,
            **facts,
        },
        metadata={"scope": _CO_SCOPE},
        entities=(
            _person(
                "filer",
                "HeadOfHousehold",
                filer_age,
                **{Concepts.YEARLY_EARNED_INCOME: wages},
            ),
            *dependents,
        ),
    )


def _filing_status_records(by_key, *person_ids: str) -> dict[str, object]:
    statuses = {
        "bridge": by_key[("tax_unit", f"{_FIS}filing_status")],
        "1401": by_key[("tax_unit", "us:statutes/26/1401#input.filing_status")],
        "151": by_key[("tax_unit", "us:statutes/26/151#input.filing_status")],
    }
    for person_id in person_ids:
        statuses[f"151:{person_id}"] = by_key[
            (person_id, "us:statutes/26/151#input.filing_status")
        ]
    return statuses


def _non_separate_regression_cases() -> list[Case]:
    return [
        Case(
            case_id="regression-single",
            period="2026",
            metadata={"scope": _CO_SCOPE},
            entities=(
                _person(
                    "p1",
                    "HeadOfHousehold",
                    70,
                    **{
                        Concepts.YEARLY_EARNED_INCOME: 20_000,
                        Concepts.SOCIAL_SECURITY_BENEFITS: 24_000,
                        Concepts.INTEREST_INCOME: 1_500,
                    },
                ),
            ),
        ),
        Case(
            case_id="regression-joint",
            period="2026",
            metadata={"scope": _CO_SCOPE},
            entities=(
                _person(
                    "p1",
                    "HeadOfHousehold",
                    66,
                    **{Concepts.YEARLY_EARNED_INCOME: 90_000},
                ),
                _person(
                    "p2",
                    "Spouse",
                    60,
                    **{
                        Concepts.YEARLY_EARNED_INCOME: 30_000,
                        Concepts.PENSION_INCOME: 12_000,
                    },
                ),
                _person("p3", "Child", 8),
                _person("p4", "Child", 15),
            ),
        ),
        Case(
            case_id="regression-head-of-household",
            period="2026",
            metadata={"scope": _CO_SCOPE},
            entities=(
                _person(
                    "p1",
                    "HeadOfHousehold",
                    35,
                    **{Concepts.YEARLY_EARNED_INCOME: 45_000},
                ),
                _person("p2", "Child", 8),
            ),
        ),
    ]


# SHA-256 of the canonical JSON of {"records": axiom_input_records,
# "relations": axiom_relations} that the projection at base commit 5420b1923
# (before married-filing-separately support) produced for each case above.
_NON_SEPARATE_PRE_MFS_DIGESTS = {
    "regression-single": (
        "443d48ca7997c8111be54512fe92980263e918c183d3c80bd1fa71c77c924a54"
    ),
    "regression-joint": (
        "c4f2d5af028510a44fec65fbf69d6439d5231c7a56ced6fb464a87b8956da80d"
    ),
    "regression-head-of-household": (
        "799028b3bfd3ba4cf31de20d6caf2234750c99ee88abc77b7a8b03269ef9cfd8"
    ),
}


@pytest.mark.parametrize(
    "case",
    _non_separate_regression_cases(),
    ids=lambda case: case.case_id,
)
def test_axiom_tax_projection_keeps_non_separate_inputs_byte_identical(
    case: Case,
) -> None:
    metadata = attach_axiom_tax_inputs_to_case(case).metadata
    payload = {
        "records": metadata["axiom_input_records"],
        "relations": metadata["axiom_relations"],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert digest == _NON_SEPARATE_PRE_MFS_DIGESTS[case.case_id]


def test_axiom_tax_projection_projects_married_filing_separately_as_code_2() -> None:
    by_key = _projected(_mfs_case("mfs-childless"))

    assert set(_filing_status_records(by_key, "filer").values()) == {2}
    assert (
        by_key[("tax_unit", "us:statutes/26/21#input.married_at_close_of_taxable_year")]
        is True
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/21#input.married_filing_separate_return")]
        is True
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/21#input.married_joint_return_filed")]
        is False
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/24/h#input.filing_status_is_joint_return")]
        is False
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:policies/irs/rev-proc-2025-32/standard-deduction"
                "#input.individual_is_unmarried_and_not_surviving_spouse",
            )
        ]
        is False
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/7703#input.taxpayer_files_separate_return")]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_married_at_close_of_taxable_year",
            )
        ]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/32#input.taxpayer_is_married_under_section_7703_a",
            )
        ]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/32#input."
                "spouse_includes_required_social_security_number_on_return",
            )
        ]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/63/f#input."
                "additional_exemption_allowable_for_spouse_under_section_151_b",
            )
        ]
        is False
    )
    # Spouses shared a home (LIVED_APART_FROM_SPOUSE_ALL_YEAR defaults False).
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/86#input."
                "married_taxpayer_lived_apart_from_spouse_at_all_times_during_taxable_year",
            )
        ]
        is False
    )
    assert by_key[("tax_unit", f"{_FIS}spouses_lived_apart_all_year")] is False
    assert by_key[("tax_unit", f"{_FIS}satisfies_eitc_separated_spouse_rules")] is False
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.spouse_not_member_of_household_final_month_count",
            )
        ]
        == 0
    )
    # 21(e)(3)-(4) inputs the pinned 21 reads at code 2.
    assert by_key[("tax_unit", f"{_FIS}legally_separated_under_decree")] is False
    assert (
        by_key[
            (
                "tax_unit",
                f"{_FIS}maintains_household_principal_abode_of_qualifying_"
                "individual_more_than_half_year",
            )
        ]
        is False
    )
    assert by_key[("tax_unit", f"{_FIS}furnishes_over_half_cost_of_household")] is False
    # No spouse entity reaches the program.
    assert by_key[("filer", "us:statutes/26/151#input.is_spouse_of_taxpayer")] is False
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/63/f#input.spouse_has_attained_age_65_before_close_of_taxable_year",
            )
        ]
        is False
    )


def test_axiom_tax_projection_carries_separate_filer_living_apart_facts() -> None:
    by_key = _projected(
        _mfs_case(
            "mfs-lived-apart",
            filer_age=70,
            **{Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True},
        )
    )

    assert set(_filing_status_records(by_key, "filer").values()) == {2}
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/86#input."
                "married_taxpayer_lived_apart_from_spouse_at_all_times_during_taxable_year",
            )
        ]
        is True
    )
    assert by_key[("tax_unit", f"{_FIS}spouses_lived_apart_all_year")] is True
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/21#input.spouse_not_member_of_household_during_last_six_months",
            )
        ]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.spouse_not_member_of_household_final_month_count",
            )
        ]
        == 12
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_maintains_household_as_home",
            )
        ]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_household_cost_fraction_furnished",
            )
        ]
        == 1
    )
    # No child: neither 7703(b) nor 32(d)(2)(B) can apply.
    assert by_key[("tax_unit", f"{_FIS}satisfies_eitc_separated_spouse_rules")] is False
    # 63(f): the filer's own age counts once; the married amount comes from
    # filing_status 2 in the pinned standard-deduction rule.
    assert (
        by_key[
            (
                "tax_unit",
                "us:policies/irs/rev-proc-2025-32/standard-deduction#input."
                "additional_standard_deduction_entitlement_count_under_subsection_f",
            )
        ]
        == 1
    )


@pytest.mark.parametrize(
    ("residence_facts", "final_month_count", "lived_apart"),
    [
        ({Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True}, 12, True),
        ({Concepts.SPOUSE_ABSENT_LAST_SIX_MONTHS: True}, 6, False),
    ],
    ids=["lived-apart-all-year", "absent-last-six-months"],
)
def test_axiom_tax_projection_gives_head_of_household_under_section_7703_b(
    residence_facts: dict,
    final_month_count: int,
    lived_apart: bool,
) -> None:
    by_key = _projected(
        _mfs_case(
            "mfs-child-absent-spouse",
            filer_age=35,
            wages=15_000,
            dependents=(_person("child", "Child", 8),),
            **residence_facts,
        )
    )

    # 7703(b) makes the filer "not considered as married", so 2(c) and 2(b)
    # give head of household; every emitted status agrees.
    assert set(_filing_status_records(by_key, "filer").values()) == {3}
    assert by_key[("child", "us:statutes/26/151#input.filing_status")] == 0
    assert (
        by_key[("tax_unit", "us:statutes/26/21#input.married_at_close_of_taxable_year")]
        is False
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/21#input.married_filing_separate_return")]
        is False
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:policies/irs/rev-proc-2025-32/standard-deduction"
                "#input.individual_is_unmarried_and_not_surviving_spouse",
            )
        ]
        is True
    )
    # Still married under 7703(a) and still a separate return.
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_married_at_close_of_taxable_year",
            )
        ]
        is True
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/7703#input.taxpayer_files_separate_return")]
        is True
    )
    assert (
        by_key[("tax_unit", "us:statutes/26/24/h#input.filing_status_is_joint_return")]
        is False
    )
    # 32(d)(2)(B): qualifying child in the home, spouse absent.
    assert by_key[("tax_unit", f"{_FIS}satisfies_eitc_separated_spouse_rules")] is True
    # 7703(b)(1)-(3) household facts the pinned 7703 rule reads.
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_maintains_household_as_home",
            )
        ]
        is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_household_cost_fraction_furnished",
            )
        ]
        == 1
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.spouse_not_member_of_household_final_month_count",
            )
        ]
        == final_month_count
    )
    assert (
        by_key[
            (
                "child",
                "us:statutes/26/7703#input.person_is_child_within_federal_tax_child_definition",
            )
        ]
        is True
    )
    # 21(e)(4)(A): an 8-year-old dependent is a 21(b)(1)(A) qualifying
    # individual.
    assert (
        by_key[
            (
                "tax_unit",
                f"{_FIS}maintains_household_principal_abode_of_qualifying_"
                "individual_more_than_half_year",
            )
        ]
        is True
    )
    assert by_key[("tax_unit", f"{_FIS}furnishes_over_half_cost_of_household")] is True
    # 86(c)(1)(C)(ii) keys on living apart ALL year, not the last six months.
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/86#input."
                "married_taxpayer_lived_apart_from_spouse_at_all_times_during_taxable_year",
            )
        ]
        is lived_apart
    )


def test_axiom_tax_projection_keeps_cohabiting_separate_filer_married() -> None:
    by_key = _projected(
        _mfs_case(
            "mfs-child-cohabiting",
            filer_age=35,
            wages=45_000,
            dependents=(_person("child", "Child", 8),),
        )
    )

    assert set(_filing_status_records(by_key, "filer").values()) == {2}
    assert (
        by_key[("tax_unit", "us:statutes/26/21#input.married_at_close_of_taxable_year")]
        is True
    )
    assert by_key[("tax_unit", f"{_FIS}satisfies_eitc_separated_spouse_rules")] is False
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/7703#input.taxpayer_maintains_household_as_home",
            )
        ]
        is False
    )
    assert (
        by_key[
            (
                "tax_unit",
                f"{_FIS}maintains_household_principal_abode_of_qualifying_"
                "individual_more_than_half_year",
            )
        ]
        is False
    )


def test_axiom_tax_projection_requires_a_child_for_the_living_apart_rule() -> None:
    """7703(b)(1) needs a child (152(f)(1)); a sibling dependent is not one.

    The projected 152(c) relationship test also excludes siblings, so the
    32(d)(2)(B) separated-spouse rule has no qualifying child either.
    """

    by_key = _projected(
        _mfs_case(
            "mfs-sibling-lived-apart",
            filer_age=35,
            wages=30_000,
            dependents=(_person("sibling", "Sibling", 10),),
            **{Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True},
        )
    )

    assert set(_filing_status_records(by_key, "filer").values()) == {2}
    assert by_key[("tax_unit", f"{_FIS}satisfies_eitc_separated_spouse_rules")] is False
    # The sibling is still a 21(b)(1)(A) qualifying individual, so 21(e)(4)
    # can treat the filer as unmarried for the credit at code 2.
    assert (
        by_key[
            (
                "tax_unit",
                f"{_FIS}maintains_household_principal_abode_of_qualifying_"
                "individual_more_than_half_year",
            )
        ]
        is True
    )


def test_axiom_tax_projection_limits_cdcc_qualifying_individual_to_under_13() -> None:
    by_key = _projected(
        _mfs_case(
            "mfs-teen-lived-apart",
            filer_age=45,
            wages=50_000,
            dependents=(_person("child", "Child", 14),),
            **{Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True},
        )
    )

    assert set(_filing_status_records(by_key, "filer").values()) == {3}
    assert by_key[("tax_unit", f"{_FIS}satisfies_eitc_separated_spouse_rules")] is True
    assert (
        by_key[
            (
                "tax_unit",
                f"{_FIS}maintains_household_principal_abode_of_qualifying_"
                "individual_more_than_half_year",
            )
        ]
        is False
    )


@pytest.mark.parametrize(
    "second_adult",
    [
        _person("spouse", "Spouse", 40, **{Concepts.YEARLY_EARNED_INCOME: 30_000}),
        # No spouse relation: _tax_filers promotes a second non-dependent adult.
        _person("roommate", "Other", 38, **{Concepts.YEARLY_EARNED_INCOME: 30_000}),
    ],
    ids=["explicit-spouse", "promoted-adult"],
)
def test_axiom_tax_projection_rejects_separate_return_with_a_spouse_filer(
    second_adult: Entity,
) -> None:
    case = _mfs_case("mfs-with-spouse", dependents=(second_adult,))

    with pytest.raises(RuntimeError, match=r"'mfs-with-spouse'.*spouse filer"):
        attach_axiom_tax_inputs_to_case(case)


def test_axiom_tax_projection_reads_residence_facts_through_separate_filing() -> None:
    case = Case(
        case_id="lived-apart-not-mfs",
        period="2026",
        facts={Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True},
        entities=(_person("filer", "HeadOfHousehold", 40),),
    )

    with pytest.raises(ValueError, match="without"):
        attach_axiom_tax_inputs_to_case(case)


def test_axiom_tax_projection_gates_senior_deduction_count_on_section_151() -> None:
    """The bridge count defers to the encoded 151(d)(5)(C)(v) eligibility."""

    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }
    formula = generated_rules_by_name["additional_senior_deduction_eligible_count"][
        "versions"
    ][0]["formula"]

    assert formula.startswith("if senior_deduction_eligible: ")
    assert formula.endswith(" else: 0")

    by_key = _projected(_mfs_case("mfs-senior", filer_age=70))
    # The gate reads filing_status 2 and the two inputs the projection sets.
    assert by_key[("tax_unit", "us:statutes/26/151#input.filing_status")] == 2
    assert (
        by_key[("tax_unit", "us:statutes/26/151#input.taxpayer_is_individual")] is True
    )
    assert (
        by_key[
            (
                "tax_unit",
                "us:statutes/26/151#input."
                "taxable_year_begins_before_senior_deduction_termination",
            )
        ]
        is True
    )
