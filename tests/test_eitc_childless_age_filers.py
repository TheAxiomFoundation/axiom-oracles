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
from axiom_oracles.bridges.tax_populace import (
    project_eitc_tax_unit_inputs,
    tax_unit_filers,
)
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.populations.populace_us import _person_entity, _PersonRow

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


# One filer list. The age test, investment income and the identification test
# all read tax_unit_filers, so the three inputs always describe one return.
# Rows with PolicyEngine role flags use them: the bridge passes through
# PolicyEngine's filing status for that unit, and PolicyEngine-US 1.764.6
# derives the flags by age (axiom-oracles#633 moves filers and filing status
# to the constructor's roles together). Rows without flags take the
# constructor's tax_unit_role_input.


def _source_person(age, role, *, pe_head=False, pe_spouse=False, flags=True, **facts):
    person = {
        "age": age,
        "ssn_card_type": "CITIZEN",
        "tax_unit_role_input": role,
        **facts,
    }
    if flags:
        person.update(
            is_tax_unit_head=pe_head,
            is_tax_unit_spouse=pe_spouse,
            is_tax_unit_head_or_spouse=pe_head or pe_spouse,
        )
    return person


UNFLAGGED_SOURCE_ROLE_CASES = [
    pytest.param(
        [
            _source_person(30, "HEAD", flags=False),
            _source_person(70, "DEPENDENT", flags=False),
            _source_person(75, "DEPENDENT", flags=False),
        ],
        True,
        id="head-30-dependents-70-75",
        # the filer is 30; an age ranking alone would pick 75 and 70
    ),
    pytest.param(
        [
            _source_person(30, "DEPENDENT", flags=False),
            _source_person(22, "HEAD", flags=False),
        ],
        False,
        id="head-22-dependent-30",
    ),
    pytest.param(
        [
            _source_person(85, "DEPENDENT", flags=False),
            _source_person(65, "HEAD", flags=False),
            _source_person(64, "SPOUSE", flags=False),
        ],
        True,
        id="head-65-spouse-64-dependent-85",
    ),
]


@pytest.mark.parametrize(("persons", "expected"), UNFLAGGED_SOURCE_ROLE_CASES)
def test_bridge_age_test_uses_source_roles_without_flags(persons, expected):
    row = {"filing_status": "JOINT", "adjusted_gross_income": 10_000}
    assert project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT] is (
        expected
    )


def _unit_57137(*, flags):
    """Populace unit 57137's shape: source DEPENDENT 85, HEAD 65, SPOUSE 64.

    PolicyEngine-US 1.764.6's flags head the unit with 85 and make 65 the
    spouse. The dependent has 13,000 of interest; the source spouse has no
    valid SSN.
    """
    return [
        _source_person(
            85, "DEPENDENT", pe_head=True, flags=flags, taxable_interest_income=13_000
        ),
        _source_person(65, "HEAD", pe_spouse=True, flags=flags),
        _source_person(64, "SPOUSE", flags=flags, ssn_card_type="OTHER"),
    ]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        pytest.param(
            True,
            {
                AGE_INPUT: False,
                "eitc_relevant_investment_income": 13_000,
                "taxpayer_includes_required_social_security_number_on_return": True,
            },
            id="pe-flags-filers-85-and-65",
            # clause (II) over 85 and 65 fails; Worksheet 1 line 1 is the
            # 85-year-old filer's 13,000; both filers have valid SSNs
        ),
        pytest.param(
            False,
            {
                AGE_INPUT: True,
                "eitc_relevant_investment_income": 0,
                "taxpayer_includes_required_social_security_number_on_return": False,
            },
            id="source-roles-filers-65-and-64",
            # clause (II): the 64-year-old spouse qualifies; the dependent's
            # interest is not on the return; 32(c)(1)(E)(ii) requires "if the
            # individual is married, the taxpayer identification number of
            # such individual's spouse", and the spouse has no valid SSN
        ),
    ],
)
def test_bridge_eitc_inputs_describe_one_return(flags, expected):
    row = {"filing_status": "JOINT", "adjusted_gross_income": 10_000}
    projected = project_eitc_tax_unit_inputs(row=row, persons=_unit_57137(flags=flags))
    assert {name: projected[name] for name in expected} == expected
    assert (
        projected["spouse_includes_required_social_security_number_on_return"]
        is expected["taxpayer_includes_required_social_security_number_on_return"]
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
def flagged_units(draw, *, head_required=True):
    """Rows as the Populace loader delivers them: PolicyEngine flags (at most
    one head and one spouse) beside arbitrary constructor roles, SSNs and
    interest, in any order. With ``head_required=False`` the flags may name
    no head, which the age-ranked PolicyEngine-US 1.764.6 formula produces
    for a unit with no adult."""
    size = draw(st.integers(min_value=1, max_value=5))
    unit_ages = draw(st.lists(ages, min_size=size, max_size=size))
    indices = st.integers(min_value=0, max_value=size - 1)
    head = draw(indices if head_required else st.none() | indices)
    spouse = draw(st.none() | indices.filter(lambda index: index != head))
    persons = [
        _source_person(
            age,
            draw(st.sampled_from(["HEAD", "SPOUSE", "DEPENDENT", ""])),
            pe_head=index == head,
            pe_spouse=index == spouse,
            ssn_card_type=draw(st.sampled_from(["CITIZEN", "OTHER"])),
            taxable_interest_income=draw(st.integers(min_value=0, max_value=20_000)),
        )
        for index, age in enumerate(unit_ages)
    ]
    return persons, head, spouse


@PROPERTY_SETTINGS
@given(unit=flagged_units(head_required=False))
def test_property_bridge_eitc_inputs_share_one_filer_list(unit):
    """The age test, investment income and identification all read
    ``tax_unit_filers``; when the flags name a head, that list is the flagged
    head and spouse."""
    persons, head, spouse = unit
    filers = tax_unit_filers(persons)
    if head is not None:
        flagged = [persons[index] for index in (head, spouse) if index is not None]
        assert [id(person) for person in filers] == [id(p) for p in flagged]
    row = {"filing_status": "JOINT", "adjusted_gross_income": 10_000}
    projected = project_eitc_tax_unit_inputs(row=row, persons=persons)
    assert projected[AGE_INPUT] is any(25 <= person["age"] < 65 for person in filers)
    assert projected["eitc_relevant_investment_income"] == sum(
        person["taxable_interest_income"] for person in filers
    )
    assert projected[
        "taxpayer_includes_required_social_security_number_on_return"
    ] is all(person["ssn_card_type"] == "CITIZEN" for person in filers)


@PROPERTY_SETTINGS
@given(unit=flagged_units())
def test_property_populace_case_loader_agrees_with_the_bridge(unit):
    """The production Case path (populace_us._person_entity over the same
    PolicyEngine flags) projects the same age input as the bridge.

    The rows follow PolicyEngine-US 1.764.6's role formulas: one head
    whenever the unit has an adult (the oldest non-child), and
    ``is_tax_unit_dependent = ~head & ~spouse``, so the loader never emits its
    "Other" relation. A dataset or PolicyEngine version that supplied
    non-dependent non-filers would need its own differential: the Case
    surface's ``_tax_filers`` promotes an "Other" adult to spouse."""
    persons, head, spouse = unit
    rows = [
        _PersonRow(
            person_id=index,
            tax_unit_id=1,
            is_tax_unit_head=index == head,
            is_tax_unit_spouse=index == spouse,
            is_tax_unit_dependent=index not in (head, spouse),
            age=person["age"],
            yearly_earned_income=8_000.0 if index == head else 0.0,
            pregnant=False,
            disabled=False,
            blind=False,
            veteran=False,
            benefits_medicaid=False,
            non_wage_income={},
        )
        for index, person in enumerate(persons)
    ]
    entities = tuple(
        _person_entity(row, index, case_unit="tax_unit")
        for index, row in enumerate(rows)
    )
    projected = attach_axiom_tax_inputs_to_case(
        Case(case_id="populace-loader", period="2026", entities=entities)
    )
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    row = {"filing_status": "JOINT", "adjusted_gross_income": 10_000}
    bridge = project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT]
    assert by_key[("tax_unit", CASE_AGE_INPUT)] is bridge
