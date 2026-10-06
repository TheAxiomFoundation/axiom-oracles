"""Property-based invariants for the married-filing-separately projections.

Invariants tested here hold for every generated separate-return Case:

- TAXSIM: the row is mstat 6, every spouse-only column is zero,
  ``validate_taxsim_row`` accepts it, and the filer's own income lands in the
  primary columns unchanged.
- Axiom: the filing status is 2, or 3 when a qualifying child lives with the
  filer and the spouse was absent for the last six months (26 USC 7703(b),
  2(c)). The bridge, 26/1401 and 26/151 records carry the same code.
- PolicyEngine: the filer is ``is_separated`` and the tax unit's
  ``cohabitating_spouses`` is the negation of the lived-apart fact. No builder
  sets ``filing_status``.
- Cross-engine: all three projections agree that the Case is a separate
  return, and every one of them rejects a separate return that carries a
  spouse entity.
- Round trip: for any Case, separate or not and with or without a spouse,
  the TAXSIM projection never emits a row that ``validate_taxsim_row``
  rejects, because such a row would abort the binary's whole batch.

Expectations are projected inputs, which the design fixes. Engine outputs are
not used.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.adapters.taxsim.projection import (
    taxsim_input_for_case,
    validate_taxsim_row,
)
from axiom_oracles.core.case import Case, Concepts, Entity

_YEAR = 2026
_CO_SCOPE = {"type": "census_state", "geoid": "08"}
_FIS = "us:tax/federal-income-tax#input."
_SPOUSE_ONLY_COLUMNS = ("sage", "swages", "ssemp", "sui")

_money = st.integers(min_value=0, max_value=1_000_000).map(float)
_small_money = st.integers(min_value=0, max_value=60_000).map(float)


@st.composite
def _separate_returns(draw):
    """A separate filer, 0-3 qualifying children, and the residence facts."""

    filer_age = draw(st.integers(min_value=18, max_value=90))
    wages = draw(_money)
    social_security = draw(_small_money)
    interest = draw(_small_money)
    child_ages = draw(st.lists(st.integers(min_value=0, max_value=16), max_size=3))
    lived_apart = draw(st.booleans())
    # Living apart all year implies the spouse was absent the last six months.
    absent = True if lived_apart else draw(st.booleans())
    facts = {
        Concepts.STATE_CODE: "CO",
        Concepts.MARRIED_FILING_SEPARATELY: True,
        Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: lived_apart,
        Concepts.SPOUSE_ABSENT_LAST_SIX_MONTHS: absent,
    }
    filer = Entity(
        "filer",
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            Concepts.PERSON_AGE: filer_age,
            Concepts.YEARLY_EARNED_INCOME: wages,
            Concepts.SOCIAL_SECURITY_BENEFITS: social_security,
            Concepts.INTEREST_INCOME: interest,
        },
    )
    children = tuple(
        Entity(
            f"child{index}",
            "person",
            facts={
                Concepts.HOUSEHOLD_RELATION: "Child",
                Concepts.PERSON_AGE: age,
            },
        )
        for index, age in enumerate(child_ages)
    )
    case = Case(
        case_id="mfs-property",
        period=str(_YEAR),
        facts=facts,
        entities=(filer, *children),
        metadata={"scope": _CO_SCOPE},
    )
    return case, {
        "wages": wages,
        "social_security": social_security,
        "interest": interest,
        "children": len(child_ages),
        "lived_apart": lived_apart,
        "absent": absent,
    }


def _with_spouse(case: Case) -> Case:
    spouse = Entity(
        "spouse",
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: "Spouse",
            Concepts.PERSON_AGE: 40,
            Concepts.YEARLY_EARNED_INCOME: 10_000.0,
        },
    )
    return Case(
        case_id=case.case_id,
        period=case.period,
        facts=case.facts,
        entities=(*case.entities, spouse),
        metadata=case.metadata,
    )


def _axiom_statuses(case: Case) -> set[object]:
    records = attach_axiom_tax_inputs_to_case(case).metadata["axiom_input_records"]
    names = {
        f"{_FIS}filing_status",
        "us:statutes/26/1401#input.filing_status",
        "us:statutes/26/151#input.filing_status",
    }
    return {
        record["value"]
        for record in records
        if record["name"] in names and record["entity_id"] in {"tax_unit", "filer"}
    }


@settings(max_examples=150, deadline=None)
@given(_separate_returns())
def test_taxsim_row_is_a_valid_mstat_6_row_with_the_filers_own_income(generated):
    case, drawn = generated
    row = taxsim_input_for_case(case, taxsimid=1)

    assert row["mstat"] == 6
    for column in _SPOUSE_ONLY_COLUMNS:
        assert row[column] == 0, column
    validate_taxsim_row(row, case_id=case.case_id)
    assert row["depx"] == drawn["children"]
    assert row["pwages"] == drawn["wages"]
    assert row["gssi"] == drawn["social_security"]
    assert row["intrec"] == drawn["interest"]


@settings(max_examples=150, deadline=None)
@given(_separate_returns())
def test_axiom_status_is_separate_or_7703b_head_of_household(generated):
    case, drawn = generated

    statuses = _axiom_statuses(case)

    # One code everywhere it is emitted.
    assert len(statuses) == 1
    expected = 3 if drawn["children"] and drawn["absent"] else 2
    assert statuses == {expected}


@settings(max_examples=150, deadline=None)
@given(_separate_returns())
def test_policyengine_marks_the_filer_separated_and_cohabitation(generated):
    case, drawn = generated
    situation = PolicyEngineRunner()._build_situation_from_case(
        case, variables=["income_tax"]
    )

    assert situation["people"]["filer"]["is_separated"] == {_YEAR: True}
    tax_unit = situation["tax_units"]["tax_unit"]
    assert tax_unit["cohabitating_spouses"] == {_YEAR: not drawn["lived_apart"]}
    assert all(
        "filing_status" not in inputs
        for group in situation.values()
        for inputs in group.values()
    )


@settings(max_examples=60, deadline=None)
@given(_separate_returns())
def test_every_projection_rejects_a_separate_return_with_a_spouse(generated):
    case, _ = generated
    joint_shaped = _with_spouse(case)

    with pytest.raises((RuntimeError, ValueError)):
        taxsim_input_for_case(joint_shaped, taxsimid=1)
    with pytest.raises((RuntimeError, ValueError)):
        attach_axiom_tax_inputs_to_case(joint_shaped)
    with pytest.raises((RuntimeError, ValueError)):
        PolicyEngineRunner()._build_situation_from_case(
            joint_shaped, variables=["income_tax"]
        )


@settings(max_examples=150, deadline=None)
@given(
    separate=st.booleans(),
    spouse=st.booleans(),
    wages=_money,
    spouse_wages=_money,
    children=st.integers(min_value=0, max_value=3),
)
def test_taxsim_projection_never_emits_a_batch_aborting_row(
    separate, spouse, wages, spouse_wages, children
):
    # A separate return never carries a spouse entity (that raises, above).
    spouse = spouse and not separate
    entities = [
        Entity(
            "head",
            "person",
            facts={
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.PERSON_AGE: 45,
                Concepts.YEARLY_EARNED_INCOME: wages,
            },
        )
    ]
    if spouse:
        entities.append(
            Entity(
                "spouse",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 44,
                    Concepts.YEARLY_EARNED_INCOME: spouse_wages,
                },
            )
        )
    entities.extend(
        Entity(
            f"child{index}",
            "person",
            facts={Concepts.HOUSEHOLD_RELATION: "Child", Concepts.PERSON_AGE: 6},
        )
        for index in range(children)
    )
    facts = {Concepts.STATE_CODE: "CO"}
    if separate:
        facts[Concepts.MARRIED_FILING_SEPARATELY] = True
    case = Case(
        case_id="round-trip",
        period=str(_YEAR),
        facts=facts,
        entities=tuple(entities),
    )

    row = taxsim_input_for_case(case, taxsimid=1)

    validate_taxsim_row(row, case_id=case.case_id)
    assert row["mstat"] == (6 if separate else 2 if spouse else 1)
