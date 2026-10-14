"""26 USC 32(c)(1)(A)(ii)(II), the childless EITC age test, on both projection surfaces.

Ground truth is the statute. 26 USC 32(c)(1)(A), U.S. Code 2024 edition
(govinfo USCODE-2024-title26, section 32), verbatim:

    (A) In general
    The term "eligible individual" means--
    (i) any individual who has a qualifying child for the taxable year, or
    (ii) any other individual who does not have a qualifying child for the
    taxable year, if--
    (I) such individual's principal place of abode is in the United States
    for more than one-half of such taxable year,
    (II) such individual (or, if the individual is married, either the
    individual or the individual's spouse) has attained age 25 but not
    attained age 65 before the close of the taxable year, and
    (III) such individual is not a dependent for whom a deduction is
    allowable under section 151 to another taxpayer ...

Clause (II) names only the individual claiming the credit and, if married,
that individual's spouse. A dependent's age never counts. The Axiom input
``childless_taxpayer_or_spouse_age_eligible_for_eitc`` is this clause, so each
surface must compute it over the filers (head and spouse) only.

Every expected value below is read off clause (II): true exactly when a filer
is at least 25 and under 65 at the close of the year. No engine output is used.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.bridges.tax_populace import project_eitc_tax_unit_inputs
from axiom_oracles.core.case import Case, Concepts, Entity

AGE_INPUT = "childless_taxpayer_or_spouse_age_eligible_for_eitc"
CASE_AGE_INPUT = f"us:statutes/26/32#input.{AGE_INPUT}"
PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)


def _clause_ii_ii(head_age, spouse_age=None):
    """Clause (II) as written: the individual, or, if married, the spouse."""
    return any(25 <= age < 65 for age in (head_age, spouse_age) if age is not None)


# Each case: (head age, spouse age or None, dependent ages, clause (II) result).
STATUTE_CASES = [
    pytest.param(22, None, [30], False, id="head-22-dependent-30"),
    pytest.param(22, 30, [], True, id="head-22-joint-spouse-30"),
    pytest.param(64, None, [], True, id="head-64"),
    pytest.param(65, None, [40], False, id="head-65-dependent-40"),
    pytest.param(70, None, [40], False, id="head-70-dependent-40"),
    pytest.param(24, None, [], False, id="head-24-below-floor"),
    pytest.param(25, None, [], True, id="head-25-at-floor"),
    pytest.param(64, None, [10], True, id="head-64-child-10"),
    pytest.param(66, 64, [], True, id="joint-head-66-spouse-64"),
    pytest.param(65, 65, [45], False, id="joint-both-65-dependent-45"),
    pytest.param(22, 23, [60], False, id="joint-22-23-dependent-60"),
]


# ---------------------------------------------------------------------------
# Populace bridge: project_eitc_tax_unit_inputs with explicit role flags.
# ---------------------------------------------------------------------------


def _bridge_person(age, *, head=False, spouse=False):
    return {
        "age": age,
        "ssn_card_type": "CITIZEN",
        "is_tax_unit_head": head,
        "is_tax_unit_spouse": spouse,
        "is_tax_unit_head_or_spouse": head or spouse,
    }


def _bridge_persons(head_age, spouse_age, dependent_ages):
    persons = [_bridge_person(head_age, head=True)]
    if spouse_age is not None:
        persons.append(_bridge_person(spouse_age, spouse=True))
    persons.extend(_bridge_person(age) for age in dependent_ages)
    return persons


def _bridge(head_age, spouse_age, dependent_ages):
    if spouse_age is not None:
        filing_status = "JOINT"
    elif dependent_ages:
        filing_status = "HEAD_OF_HOUSEHOLD"
    else:
        filing_status = "SINGLE"
    row = {"filing_status": filing_status, "adjusted_gross_income": 10_000}
    persons = _bridge_persons(head_age, spouse_age, dependent_ages)
    return project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT]


@pytest.mark.parametrize(("head", "spouse", "dependents", "expected"), STATUTE_CASES)
def test_bridge_age_test_counts_filers_only(head, spouse, dependents, expected):
    assert _bridge(head, spouse, dependents) is expected


def test_bridge_dependent_listed_first_does_not_count():
    """Row order is irrelevant: the 30-year-old is a dependent wherever listed."""
    row = {"filing_status": "HEAD_OF_HOUSEHOLD", "adjusted_gross_income": 10_000}
    persons = [_bridge_person(30), _bridge_person(22, head=True)]
    assert project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT] is False


# Source roles outrank PolicyEngine's age-ranked flags (axiom-oracles#633).
# PolicyEngine-US 1.764.6 heads every unit with its oldest adult and makes the
# next-oldest the spouse, whatever the Populace constructor's
# tax_unit_role_input says. Clause (II) applies to the constructor's filers.


def _source_person(age, role, *, pe_head=False, pe_spouse=False, flags=True):
    person = {"age": age, "ssn_card_type": "CITIZEN", "tax_unit_role_input": role}
    if flags:
        person.update(
            is_tax_unit_head=pe_head,
            is_tax_unit_spouse=pe_spouse,
            is_tax_unit_head_or_spouse=pe_head or pe_spouse,
        )
    return person


SOURCE_ROLE_CASES = [
    pytest.param(
        [
            _source_person(85, "DEPENDENT", pe_head=True),
            _source_person(65, "HEAD", pe_spouse=True),
            _source_person(64, "SPOUSE"),
        ],
        True,
        id="populace-57137-source-spouse-64-counts",
        # the constructor's filers are 65 and 64; the 64-year-old spouse is
        # 25 to 64
    ),
    pytest.param(
        [
            _source_person(85, "HEAD", pe_head=True),
            _source_person(60, "DEPENDENT", pe_spouse=True),
        ],
        False,
        id="populace-138-dependent-60-is-not-a-spouse",
        # the only filer is 85; the source files SURVIVING_SPOUSE
    ),
    pytest.param(
        [
            _source_person(30, "DEPENDENT", pe_head=True),
            _source_person(22, "HEAD", pe_spouse=True),
        ],
        False,
        id="head-22-dependent-30-ranked-head-by-age",
    ),
    pytest.param(
        [
            _source_person(30, "HEAD", flags=False),
            _source_person(70, "DEPENDENT", flags=False),
            _source_person(75, "DEPENDENT", flags=False),
        ],
        True,
        id="head-30-dependents-70-75-without-flags",
        # the age fallback alone would pick 75 and 70
    ),
]


@pytest.mark.parametrize(("persons", "expected"), SOURCE_ROLE_CASES)
def test_bridge_age_test_follows_source_roles(persons, expected):
    row = {"filing_status": "JOINT", "adjusted_gross_income": 10_000}
    assert project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT] is (
        expected
    )


# ---------------------------------------------------------------------------
# Case surface: attach_axiom_tax_inputs_to_case with household relations.
# ---------------------------------------------------------------------------


def _case(head_age, spouse_age, dependent_ages, *, dependent_relation="Dependent"):
    people = [
        {
            Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            Concepts.PERSON_AGE: head_age,
            Concepts.YEARLY_EARNED_INCOME: 8_000,
        }
    ]
    if spouse_age is not None:
        people.append(
            {Concepts.HOUSEHOLD_RELATION: "Spouse", Concepts.PERSON_AGE: spouse_age}
        )
    people.extend(
        {Concepts.HOUSEHOLD_RELATION: dependent_relation, Concepts.PERSON_AGE: age}
        for age in dependent_ages
    )
    entities = tuple(
        Entity(f"person-{index + 1}", "person", facts=facts)
        for index, facts in enumerate(people)
    )
    projected = attach_axiom_tax_inputs_to_case(
        Case(case_id="eitc-childless-age", period="2026", entities=entities)
    )
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    return by_key[("tax_unit", CASE_AGE_INPUT)]


@pytest.mark.parametrize(("head", "spouse", "dependents", "expected"), STATUTE_CASES)
def test_case_surface_age_test_counts_filers_only(head, spouse, dependents, expected):
    assert _case(head, spouse, dependents) is expected


@pytest.mark.parametrize("relation", ["Child", "Dependent", "Grandchild"])
def test_case_surface_adult_dependent_relations_do_not_count(relation):
    assert _case(22, None, [30], dependent_relation=relation) is False


# ---------------------------------------------------------------------------
# Properties.
# ---------------------------------------------------------------------------

ages = st.integers(min_value=0, max_value=110)
spouse_ages = st.none() | ages
dependent_age_lists = st.lists(ages, max_size=4)


@PROPERTY_SETTINGS
@given(head=ages, spouse=spouse_ages, dependents=dependent_age_lists)
def test_property_bridge_equals_clause_ii_ii(head, spouse, dependents):
    assert _bridge(head, spouse, dependents) is _clause_ii_ii(head, spouse)


@PROPERTY_SETTINGS
@given(head=ages, spouse=spouse_ages, dependents=dependent_age_lists)
def test_property_bridge_dependents_never_change_the_input(head, spouse, dependents):
    assert _bridge(head, spouse, dependents) is _bridge(head, spouse, [])


@PROPERTY_SETTINGS
@given(head=ages, spouse=spouse_ages, dependents=dependent_age_lists)
def test_property_case_surface_equals_clause_ii_ii(head, spouse, dependents):
    assert _case(head, spouse, dependents) is _clause_ii_ii(head, spouse)


@PROPERTY_SETTINGS
@given(head=ages, spouse=spouse_ages, dependents=dependent_age_lists)
def test_property_case_surface_dependents_never_change_the_input(
    head, spouse, dependents
):
    assert _case(head, spouse, dependents) is _case(head, spouse, [])


@PROPERTY_SETTINGS
@given(head=ages, spouse=spouse_ages, dependents=dependent_age_lists)
def test_property_case_surface_agrees_with_the_bridge(head, spouse, dependents):
    assert _case(head, spouse, dependents) is _bridge(head, spouse, dependents)


@st.composite
def source_role_units(draw):
    """A unit with constructor roles, arbitrary PolicyEngine flags and order."""
    head = draw(ages)
    spouse = draw(spouse_ages)
    dependents = draw(dependent_age_lists)
    members = [(head, "HEAD")]
    if spouse is not None:
        members.append((spouse, "SPOUSE"))
    members.extend((age, "DEPENDENT") for age in dependents)
    members = draw(st.permutations(members))
    indices = st.none() | st.integers(min_value=0, max_value=len(members) - 1)
    pe_head = draw(indices)
    pe_spouse = draw(indices.filter(lambda index: index is None or index != pe_head))
    persons = [
        _source_person(
            age,
            role,
            pe_head=index == pe_head,
            pe_spouse=index == pe_spouse,
            flags=draw(st.booleans()),
        )
        for index, (age, role) in enumerate(members)
    ]
    return persons, _clause_ii_ii(head, spouse)


@PROPERTY_SETTINGS
@given(unit=source_role_units())
def test_property_bridge_follows_source_roles_whatever_the_flags(unit):
    persons, expected = unit
    row = {"filing_status": "JOINT", "adjusted_gross_income": 10_000}
    assert project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT] is (
        expected
    )
