import pytest

from axiom_oracles.adapters.axiom.tax_projection import (
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
    assert by_key[("tax_unit", "us:tax/federal-income-tax#input.wages")] == 70_000
    assert by_key[
        ("person-3", "us:tax/federal-income-tax#input.is_tax_unit_dependent")
    ] is True
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
        ("person-3", "us:statutes/26/24/h#input.qualifying_child_described_in_subsection_c")
    ] is True
    assert by_key[
        ("person-3", "us:statutes/26/24/h#input.dependent_under_section_152")
    ] is True
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
        if record["name"] == "us:statutes/26/32#relation.qualifying_child_of_tax_unit"
    } == {
        ("person-3", "tax_unit"),
    }
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"]
        == "us:tax/federal-income-tax/oracle-bridge#relation."
        "business_income_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
    }
    assert len(projected.metadata["axiom_relations"]) == 12
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
    assert (
        "tax_unit",
        "us:tax/federal-income-tax#input.taxable_social_security_benefits_included",
    ) not in by_key


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
        == "us:tax/federal-income-tax/oracle-bridge#relation."
        "business_income_of_tax_unit"
    }

    assert by_key[
        (
            "person-1",
            "us:tax/federal-income-tax/oracle-bridge#input."
            "person_rental_income_for_qbid",
        )
    ] == 1_127.323
    assert by_key[
        (
            "person-2",
            "us:tax/federal-income-tax/oracle-bridge#input."
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
                "itemized_taxable_income_deductions": 20_000,
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
            "us:tax/federal-income-tax#input.itemized_taxable_income_deductions",
        )
    ] == 20_000
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


def test_axiom_tax_projection_rejects_case_supplied_tax_aggregates() -> None:
    case = Case(
        case_id="aggregate-inputs",
        period="2026",
        metadata={
            "axiom_tax_unit_inputs": {
                "adjusted_gross_income": 103_000,
                "additional_senior_deduction": 6_000,
                "deduction_provided_in_section_199A": 2_000,
                "irs_gross_income": 105_000,
                "qualified_business_income_deduction": 2_000,
                "self_employment_tax_ald": 1_000,
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


def test_axiom_tax_projection_does_not_synthesize_alaska_pfd_from_policyengine() -> None:
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
