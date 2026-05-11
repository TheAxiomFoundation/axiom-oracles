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
        ("person-1", "us:tax/federal-income-tax#input.is_taxpayer")
    ] is True
    assert {
        tuple(record["tuple"])
        for record in projected.metadata["axiom_relations"]
        if record["name"] == "us:statutes/26/24/h#relation.member_of_tax_unit"
    } == {
        ("person-1", "tax_unit"),
        ("person-2", "tax_unit"),
        ("person-3", "tax_unit"),
    }
    member_relations = [
        record
        for record in projected.metadata["axiom_relations"]
        if record["name"].endswith("#relation.member_of_tax_unit")
    ]
    assert len(member_relations) == 3
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
        overlay[0]["value"]
        for overlay in projected.metadata["axiom_input_record_overlays"]
        if overlay[0]["name"] == "us:tax/federal-income-tax#input.tax_unit_itemizes"
    ]
    assert itemization_candidates == [False, True]


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
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.additional_senior_deduction")
    ] == 6000
    assert by_key[
        ("person-2", "us:tax/federal-income-tax#input.is_spouse")
    ] is True


def test_axiom_tax_projection_phases_out_additional_senior_deduction() -> None:
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

    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.additional_senior_deduction")
    ] == 5700


def test_axiom_tax_projection_uses_external_tax_unit_inputs() -> None:
    case = Case(
        case_id="itemizer",
        period="2026",
        metadata={
            "axiom_tax_unit_inputs": {
                "itemized_taxable_income_deductions": 20_000,
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
    assert by_key[
        ("tax_unit", "us:tax/federal-income-tax#input.tax_unit_itemizes")
    ] is False
    assert "axiom_input_record_overlays" not in projected.metadata


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

    with pytest.raises(RuntimeError, match="must not include tax_unit_itemizes"):
        attach_axiom_tax_inputs_to_case(case)
