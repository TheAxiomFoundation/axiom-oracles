from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.taxsim.projection import (
    TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY,
    attach_taxsim_inputs,
    taxsim_input_for_case,
)
from axiom_oracles.adapters.taxsim.runner import TaxsimPackageRunner
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

    with pytest.raises(RuntimeError, match="tax years after 2026; got 2027"):
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


def test_taxsim_projection_leaves_out_tax_exempt_interest_and_records_it() -> None:
    """TAXSIM-35 has no Form 1040 line 2a input (taxsim.nber.org/taxsimtest:
    "11. intrec Taxable Interest Received."; "It is an error to include a
    variable not named above"), so the row is identical with or without it,
    and attach_taxsim_inputs records the head + spouse amount it dropped
    (4,000 + 1,500; the child's 900 is not the filers')."""

    def case(head_interest, spouse_interest, child_interest):
        return Case(
            case_id="tax-exempt-interest",
            period="2026",
            facts={Concepts.STATE_CODE: "CO"},
            entities=(
                Entity(
                    "person-1",
                    "person",
                    facts={
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.PERSON_AGE: 70,
                        Concepts.INTEREST_INCOME: 2_000,
                        Concepts.SOCIAL_SECURITY_BENEFITS: 24_000,
                        Concepts.TAX_EXEMPT_INTEREST_INCOME: head_interest,
                    },
                ),
                Entity(
                    "person-2",
                    "person",
                    facts={
                        Concepts.HOUSEHOLD_RELATION: "Spouse",
                        Concepts.PERSON_AGE: 68,
                        Concepts.TAX_EXEMPT_INTEREST_INCOME: spouse_interest,
                    },
                ),
                Entity(
                    "person-3",
                    "person",
                    facts={
                        Concepts.HOUSEHOLD_RELATION: "Child",
                        Concepts.PERSON_AGE: 15,
                        Concepts.TAX_EXEMPT_INTEREST_INCOME: child_interest,
                    },
                ),
            ),
        )

    [without] = attach_taxsim_inputs([case(0, 0, 0)])
    [with_interest] = attach_taxsim_inputs([case(4_000, 1_500, 900)])

    assert with_interest.metadata["taxsim_input"] == without.metadata["taxsim_input"]
    assert with_interest.metadata["taxsim_input"]["intrec"] == 2_000
    assert "taxsim_unprojected_inputs" not in without.metadata
    assert with_interest.metadata["taxsim_unprojected_inputs"] == {
        "tax_exempt_interest_income": 5_500
    }


def _tax_exempt_interest_case(head_interest, spouse_interest, child_interest):
    return Case(
        case_id="diagnostic",
        period="2026",
        facts={Concepts.STATE_CODE: "CO"},
        entities=tuple(
            Entity(
                relation,
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: relation,
                    Concepts.PERSON_AGE: age,
                    Concepts.TAX_EXEMPT_INTEREST_INCOME: amount,
                },
            )
            for relation, age, amount in (
                ("head", 70, head_interest),
                ("spouse", 68, spouse_interest),
                ("child", 15, child_interest),
            )
        ),
    )


@pytest.mark.parametrize("row_location", ["metadata", "facts"])
def test_preprojected_taxsim_cases_record_dropped_filer_input(row_location) -> None:
    case = _tax_exempt_interest_case(4_000, 1_500, 900)
    row = taxsim_input_for_case(case, taxsimid="custom-id")
    case = replace(
        case,
        **{row_location: {**getattr(case, row_location), "taxsim_input": row}},
    )

    [projected] = attach_taxsim_inputs([case])

    assert projected.metadata["taxsim_input"] == row
    assert projected.metadata[TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY] == {
        "tax_exempt_interest_income": 5_500
    }
    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in case.metadata


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    head=st.integers(min_value=-100_000, max_value=100_000),
    spouse=st.integers(min_value=-100_000, max_value=100_000),
    child=st.integers(min_value=-100_000, max_value=100_000),
    row_location=st.sampled_from(["fresh", "metadata", "facts"]),
)
def test_taxsim_diagnostic_is_filer_sum_regardless_of_projection_path(
    head, spouse, child, row_location
) -> None:
    case = _tax_exempt_interest_case(head, spouse, child)
    row = taxsim_input_for_case(case, taxsimid=1)
    if row_location != "fresh":
        case = replace(
            case,
            **{row_location: {**getattr(case, row_location), "taxsim_input": row}},
        )

    [projected] = attach_taxsim_inputs([case])

    expected = {"tax_exempt_interest_income": head + spouse} if head + spouse else {}
    assert (
        projected.metadata.get(TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY, {})
        == expected
    )
    assert projected.metadata["taxsim_input"] == row


def _taxsim_diagnostic_result(case, output_present):
    class FixedRunner:
        def __init__(self, frame):
            pass

        def run(self, show_progress=False):
            return [{"taxsimid": 1, "fiitax": 100}] if output_present else []

    [result] = TaxsimPackageRunner(runner_factory=FixedRunner).run_cases([case])
    return result


@pytest.mark.parametrize("output_present", [True, False])
def test_taxsim_repeated_attachment_clears_diagnostic_after_zeroing(
    output_present,
) -> None:
    [original] = attach_taxsim_inputs([_tax_exempt_interest_case(10_000, 0, 900)])
    zeroed = replace(
        original, entities=_tax_exempt_interest_case(0, 0, 900).entities
    )

    [reattached] = attach_taxsim_inputs([zeroed])
    result = _taxsim_diagnostic_result(reattached, output_present)

    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in reattached.metadata
    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in (result.raw or {})
    assert reattached.metadata["taxsim_input"] == original.metadata["taxsim_input"]
    assert original.metadata[TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY] == {
        "tax_exempt_interest_income": 10_000
    }
    assert result.values == ({"fiitax": 100} if output_present else {})
    assert bool(result.errors) is not output_present


@pytest.mark.parametrize("output_present", [True, False])
def test_taxsim_direct_result_uses_current_zero_instead_of_stale_diagnostic(
    output_present,
) -> None:
    [original] = attach_taxsim_inputs([_tax_exempt_interest_case(10_000, 0, 900)])
    zeroed = replace(
        original, entities=_tax_exempt_interest_case(0, 0, 900).entities
    )

    result = _taxsim_diagnostic_result(zeroed, output_present)

    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in (result.raw or {})
    assert result.values == ({"fiitax": 100} if output_present else {})
    assert bool(result.errors) is not output_present


@pytest.mark.parametrize("output_present", [True, False])
def test_taxsim_row_only_case_retains_diagnostic_without_source_facts(
    output_present,
) -> None:
    [original] = attach_taxsim_inputs([_tax_exempt_interest_case(10_000, 0, 900)])
    row_only = replace(original, entities=())

    [reattached] = attach_taxsim_inputs([row_only])
    result = _taxsim_diagnostic_result(reattached, output_present)

    expected = {"tax_exempt_interest_income": 10_000}
    assert reattached.metadata[TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY] == expected
    assert result.raw[TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY] == expected
    assert result.values == ({"fiitax": 100} if output_present else {})
    assert bool(result.errors) is not output_present


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    initial=st.integers(min_value=1, max_value=100_000),
    head=st.integers(min_value=-100_000, max_value=100_000),
    child=st.integers(min_value=-100_000, max_value=100_000),
)
def test_taxsim_reattachment_clears_diagnostic_when_current_filers_sum_to_zero(
    initial, head, child
) -> None:
    """Current filer facts replace prior diagnostics, including signed cancellation."""
    [original] = attach_taxsim_inputs([_tax_exempt_interest_case(initial, 0, child)])
    zeroed = replace(
        original, entities=_tax_exempt_interest_case(head, -head, child).entities
    )

    [reattached] = attach_taxsim_inputs([zeroed])

    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in reattached.metadata
    assert reattached.metadata["taxsim_input"] == original.metadata["taxsim_input"]
