import pytest

from axiom_oracles.adapters.taxsim.projection import (
    attach_taxsim_inputs,
    taxsim_input_for_case,
)
from axiom_oracles.core.case import Case, Concepts, Entity


def test_taxsim_projection_maps_family_wages_dependents_and_scope_state() -> None:
    case = Case(
        case_id="nyc-family",
        period="2024-05",
        metadata={"scope": {"type": "census_place", "geoid": "3651000"}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                    Concepts.SELF_EMPLOYMENT_INCOME: 3_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 38,
                    Concepts.YEARLY_EARNED_INCOME: 20_000,
                    Concepts.SELF_EMPLOYMENT_INCOME: 2_000,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 5,
                },
            ),
            Entity(
                "person-4",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 17,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case, taxsimid=7)

    assert row["taxsimid"] == 7
    assert row["year"] == 2024
    assert row["state"] == 33
    assert row["mstat"] == 2
    assert row["page"] == 40
    assert row["sage"] == 38
    assert row["pwages"] == 50_000
    assert row["swages"] == 20_000
    assert row["psemp"] == 3_000
    assert row["ssemp"] == 2_000
    assert row["depx"] == 2
    assert row["age1"] == 5
    assert row["age2"] == 17
    assert row["dep13"] == 1
    assert row["dep17"] == 1
    assert row["dep18"] == 2
    # idtl=2 requests TAXSIM's decomposed credit columns (v10..v41) used for
    # component-level comparisons.
    assert row["idtl"] == 2


def test_taxsim_projection_uses_state_code_fact_without_scope() -> None:
    case = Case(
        case_id="ca",
        period="2024",
        facts={Concepts.STATE_CODE: "CA"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                    Concepts.YEARLY_EARNED_INCOME: 10_000,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case)

    assert row["state"] == 5
    assert row["mstat"] == 1
    assert row["depx"] == 0


def test_attach_taxsim_inputs_preserves_existing_projection() -> None:
    existing = {
        "taxsimid": "custom-id",
        "year": 2026,
        "state": 36,
        "mstat": 1,
        "page": 40,
    }
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={"taxsim_input": existing},
    )

    [projected] = attach_taxsim_inputs([case])

    assert projected.metadata["taxsim_input"] == existing


def test_taxsim_projection_requires_state() -> None:
    case = Case(
        case_id="missing-state",
        period="2024",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                },
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="state"):
        taxsim_input_for_case(case)


def test_taxsim_projection_rejects_years_after_bundled_taxsim_support() -> None:
    case = Case(
        case_id="future-year",
        period="2027",
        facts={Concepts.STATE_CODE: "NY"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                },
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="through 2026"):
        taxsim_input_for_case(case)


def test_taxsim_projection_splits_dividends_by_qualification() -> None:
    case = Case(
        case_id="dividend-split",
        period="2026",
        facts={Concepts.STATE_CODE: "CO"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.DIVIDEND_INCOME: 5_000,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 3_000,
                    Concepts.RENTAL_INCOME: 1_000,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case)

    # TAXSIM's dividends column is qualified-only; the non-qualified
    # remainder rides in otherprop so AGI stays whole.
    assert row["dividends"] == 3_000
    assert row["otherprop"] == 3_000  # 1,000 rental + 2,000 non-qualified


def test_taxsim_projection_keeps_qualified_only_dividend_rows_whole() -> None:
    case = Case(
        case_id="dividend-qualified-only",
        period="2026",
        facts={Concepts.STATE_CODE: "CO"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 4_000,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case)

    assert row["dividends"] == 4_000
    assert row["otherprop"] == 0
