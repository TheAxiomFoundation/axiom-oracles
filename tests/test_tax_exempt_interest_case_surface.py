"""Tax-exempt interest (Form 1040 line 2a) on every Case projection.

Ground truth (verbatim; U.S. government works):

26 USC 86(b)(2) (axiom-corpus us/statute/26/86/b/2, release point 119-100):
    "the term “modified adjusted gross income” means adjusted gross income—
    (A) determined without regard to this section and sections 85(c), 135,
    137, 221, 911, 931, and 933, and (B) increased by the amount of interest
    received or accrued by the taxpayer during the taxable year which is
    exempt from tax."

Form 1040 Instructions (2025), p. 32, "Social Security Benefits
Worksheet—Lines 6a and 6b":
    "3. Combine the amounts from Form 1040 or 1040-SR, lines 1z, 2b, 3b, 4b,
        5b, 7a, and 8"
    "4. Enter the amount, if any, from Form 1040 or 1040-SR, line 2a"
    "5. Combine lines 2, 3, and 4"
Pub. 915 (2025), p. 16, Worksheet 1 carries the same line 4 ("4. Enter the
amount, if any, from Form 1040 or 1040-SR, line 2a"); its later lines are one
higher because its line 5 adds exclusions.

Form 1040 (2025), p. 1: "9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7a, and 8. This
is your total income" and "11a Subtract line 10 from line 9. This is your
adjusted gross income": line 2a never enters total income or AGI.

Pub. 596 (2025), p. 7, Worksheet 1 line 2: "Enter any amount from Form 1040 or
1040-SR, line 2a, plus any amount on Form 8814, line 1b", added unfloored on
line 14 (tests/test_eitc_investment_income_worksheet1.py has the worksheet).

26 USC 103(a) (uscode.house.gov, current through Pub. L. 119-111, fetched
2026-09-27): "Except as provided in subsection (b), gross income does not
include interest on any State or local bond."
26 USC 152(d)(1)(B) (axiom-corpus us/statute/26/152/d/1): a qualifying
relative is an individual "whose gross income for the calendar year in which
such taxable year begins is less than the exemption amount (as defined in
section 151(d))".

TAXSIM (taxsim.nber.org/taxsimtest, the pinned binary's documentation):
"11. intrec Taxable Interest Received."; "It is an error to include a
variable not named above"; "Anything not listed above becomes a zero on the
Form 1040." The pinned binary answers an extra column with "TAXSIM: ERROR
'exint' is not a taxsimtest input variable." / "STOP 901".

Tax-Calculator 6.7.1 records_variables.json: e00400 is "Tax-exempt interest
income", a filing-unit input.

Every expected amount below comes from those texts and the stated inputs,
never from the code under test.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.adapters.taxcalc.projection import taxcalc_input_for_case
from axiom_oracles.adapters.taxsim.projection import (
    TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY,
    attach_taxsim_inputs,
    taxsim_input_for_case,
)
from axiom_oracles.core.case import Case, Concepts, Entity

SECTION_86_INPUT = "us:statutes/26/86#input.tax_exempt_interest_received_or_accrued"
EITC_INVESTMENT_INCOME_INPUT = (
    "us:tax/federal-income-tax#input.eitc_relevant_investment_income"
)
FILING_STATUS_INPUT = "us:statutes/26/1401#input.filing_status"
PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)


def _person(entity_id, relation, age, **facts):
    return Entity(
        entity_id,
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: relation,
            Concepts.PERSON_AGE: age,
            **facts,
        },
    )


def _case(*people, period="2026", metadata=None):
    return Case(
        case_id="tax-exempt-interest",
        period=period,
        entities=tuple(people),
        metadata=metadata or {"state_code": "CO"},
    )


def _records(case):
    return attach_axiom_tax_inputs_to_case(case).metadata["axiom_input_records"]


def _tax_unit_value(case, name):
    (value,) = [
        record["value"]
        for record in _records(case)
        if record["name"] == name and record["entity_id"] == "tax_unit"
    ]
    return value


def _with_tax_exempt_interest(entity, amount):
    if not amount:
        return entity
    return Entity(
        entity.entity_id,
        entity.kind,
        facts={**entity.facts, Concepts.TAX_EXEMPT_INTEREST_INCOME: amount},
    )


# ---------------------------------------------------------------------------
# 26 USC 86(b)(2)(B): the Social Security worksheet's line 4.
# ---------------------------------------------------------------------------


def _single_social_security_filer(tax_exempt_interest):
    # Worked example 1: single; box 5 benefits 20,000 (worksheet line 1);
    # wages 10,000 (line 1z) and taxable interest 8,000 (line 2b), so line 3
    # is 18,000; tax-exempt interest (line 2a) is worksheet line 4.
    return _person(
        "person-1",
        "HeadOfHousehold",
        67,
        **{
            Concepts.YEARLY_EARNED_INCOME: 10_000,
            Concepts.INTEREST_INCOME: 8_000,
            Concepts.SOCIAL_SECURITY_BENEFITS: 20_000,
            Concepts.TAX_EXEMPT_INTEREST_INCOME: tax_exempt_interest,
        },
    )


def test_section_86_input_is_form_1040_line_2a() -> None:
    case = _case(_single_social_security_filer(10_000))

    assert _tax_unit_value(case, SECTION_86_INPUT) == 10_000


def test_section_86_input_sums_both_spouses_on_a_joint_return() -> None:
    """A joint return has one Form 1040 line 2a: 7,000 + 5,000."""
    case = _case(
        _person(
            "person-1",
            "HeadOfHousehold",
            70,
            **{
                Concepts.SOCIAL_SECURITY_BENEFITS: 30_000,
                Concepts.PENSION_INCOME: 25_000,
                Concepts.TAX_EXEMPT_INTEREST_INCOME: 7_000,
            },
        ),
        _person(
            "person-2",
            "Spouse",
            68,
            **{Concepts.TAX_EXEMPT_INTEREST_INCOME: 5_000},
        ),
    )

    assert _tax_unit_value(case, SECTION_86_INPUT) == 12_000


def test_section_86_input_excludes_a_dependents_tax_exempt_interest() -> None:
    """86(b)(2)(B) adds interest "received or accrued by the taxpayer"; a
    child's 3,000 is not on the filers' line 2a."""
    case = _case(
        _single_social_security_filer(10_000),
        _person(
            "person-2",
            "Child",
            12,
            **{Concepts.TAX_EXEMPT_INTEREST_INCOME: 3_000},
        ),
    )

    assert _tax_unit_value(case, SECTION_86_INPUT) == 10_000


def test_tax_exempt_interest_changes_no_gross_income_leaf() -> None:
    """Form 1040 line 9 omits line 2a, so only the two line-2a consumers
    move: the section 86 input (by 10,000) and Worksheet 1's line 14 (by
    10,000). Every other record, the gross-income leaves included, is
    identical."""
    without = _records(_case(_single_social_security_filer(0)))
    with_interest = _records(_case(_single_social_security_filer(10_000)))

    changed = [
        (before, after)
        for before, after in zip(without, with_interest, strict=True)
        if before != after
    ]
    assert sorted(
        (after["name"], after["entity_id"], after["value"] - before["value"])
        for before, after in changed
    ) == [
        (SECTION_86_INPUT, "tax_unit", 10_000),
        (EITC_INVESTMENT_INCOME_INPUT, "tax_unit", 10_000),
    ]


def test_person_zero_records_cannot_shadow_the_tax_unit_value() -> None:
    """Every person repeats the tax unit's numeric defaults as zeros under
    the same ref. The engine keys input records by (name, entity_id), so
    the tax unit's value stays distinct only while no person uses the tax
    unit's id — which the projection refuses."""
    case = _case(
        _single_social_security_filer(10_000),
        _person("person-2", "Child", 12),
    )
    section_86_records = [
        record for record in _records(case) if record["name"] == SECTION_86_INPUT
    ]

    tax_unit_records = [r for r in section_86_records if r["entity"] == "TaxUnit"]
    person_records = [r for r in section_86_records if r["entity"] == "Person"]
    assert [(r["entity_id"], r["value"]) for r in tax_unit_records] == [
        ("tax_unit", 10_000)
    ]
    assert {r["entity_id"] for r in person_records} == {"person-1", "person-2"}
    assert {r["value"] for r in person_records} == {0}

    with pytest.raises(RuntimeError, match="reserves entity id 'tax_unit'"):
        attach_axiom_tax_inputs_to_case(
            _case(_person("tax_unit", "HeadOfHousehold", 40))
        )


@pytest.mark.parametrize(
    ("dependent_income", "expected_filing_status"),
    [
        pytest.param(
            {Concepts.TAX_EXEMPT_INTEREST_INCOME: 10_000},
            3,
            id="tax-exempt-interest-is-not-gross-income",
            # 103(a): gross income 0 < the 152(d)(1)(B) exemption amount, so
            # the 20-year-old still qualifies the filer for head of household
        ),
        pytest.param(
            {Concepts.INTEREST_INCOME: 10_000},
            0,
            id="taxable-interest-is-gross-income",
            # control: 10,000 of taxable interest exceeds the exemption
            # amount, so the filer files single
        ),
    ],
)
def test_dependent_gross_income_excludes_tax_exempt_interest(
    dependent_income, expected_filing_status
) -> None:
    case = _case(
        _person(
            "person-1",
            "HeadOfHousehold",
            45,
            **{Concepts.YEARLY_EARNED_INCOME: 40_000},
        ),
        _person("person-2", "Dependent", 20, **dependent_income),
    )

    assert _tax_unit_value(case, FILING_STATUS_INPUT) == expected_filing_status


# ---------------------------------------------------------------------------
# Invariants (property-based) across the Axiom, TAXSIM, Tax-Calculator, and
# PolicyEngine projections.
# ---------------------------------------------------------------------------

NON_NEGATIVE = st.integers(min_value=0, max_value=60_000)
SIGNED = st.integers(min_value=-60_000, max_value=60_000)
TAX_EXEMPT_INTEREST = st.integers(min_value=0, max_value=60_000)
PERSON_INCOME = st.fixed_dictionaries(
    {
        Concepts.YEARLY_EARNED_INCOME: NON_NEGATIVE,
        Concepts.SELF_EMPLOYMENT_INCOME: SIGNED,
        Concepts.INTEREST_INCOME: NON_NEGATIVE,
        Concepts.DIVIDEND_INCOME: NON_NEGATIVE,
        Concepts.QUALIFIED_DIVIDEND_INCOME: NON_NEGATIVE,
        Concepts.SHORT_TERM_CAPITAL_GAINS: SIGNED,
        Concepts.LONG_TERM_CAPITAL_GAINS: SIGNED,
        Concepts.PENSION_INCOME: NON_NEGATIVE,
        Concepts.SOCIAL_SECURITY_BENEFITS: NON_NEGATIVE,
        Concepts.UNEMPLOYMENT_INSURANCE_INCOME: NON_NEGATIVE,
        Concepts.RENTAL_INCOME: SIGNED,
    }
)


@st.composite
def households(draw):
    """A head, an optional spouse, and up to three dependents, each with a
    full draw of the Case's other income concepts (tax-exempt interest is
    added by each test)."""
    head = _person(
        "person-1",
        "HeadOfHousehold",
        draw(st.integers(min_value=18, max_value=90)),
        **draw(PERSON_INCOME),
    )
    spouse = None
    if draw(st.booleans()):
        spouse = _person(
            "person-2",
            "Spouse",
            draw(st.integers(min_value=18, max_value=90)),
            **draw(PERSON_INCOME),
        )
    dependents = [
        _person(
            f"person-{index + 3}",
            draw(st.sampled_from(["Child", "Dependent"])),
            draw(st.integers(min_value=0, max_value=30)),
            **draw(PERSON_INCOME),
        )
        for index in range(draw(st.integers(min_value=0, max_value=3)))
    ]
    return head, spouse, dependents


def _household_case(head, spouse, dependents):
    return _case(head, *([spouse] if spouse is not None else []), *dependents)


@PROPERTY_SETTINGS
@given(
    household=households(),
    head_interest=TAX_EXEMPT_INTEREST,
    spouse_interest=TAX_EXEMPT_INTEREST,
)
def test_property_filer_interest_moves_exactly_two_axiom_inputs_by_the_delta(
    household, head_interest, spouse_interest
) -> None:
    """Line 2a feeds the 86(b)(2)(B) input and Worksheet 1 line 2 (added
    unfloored), and nothing else: both TaxUnit inputs rise by exactly the
    filers' amount, and every other record and relation is identical."""
    head, spouse, dependents = household
    base = attach_axiom_tax_inputs_to_case(_household_case(head, spouse, dependents))
    varied = attach_axiom_tax_inputs_to_case(
        _household_case(
            _with_tax_exempt_interest(head, head_interest),
            (
                _with_tax_exempt_interest(spouse, spouse_interest)
                if spouse is not None
                else None
            ),
            dependents,
        )
    )
    delta = head_interest + (spouse_interest if spouse is not None else 0)

    assert varied.metadata["axiom_relations"] == base.metadata["axiom_relations"]
    changed = [
        (before, after)
        for before, after in zip(
            base.metadata["axiom_input_records"],
            varied.metadata["axiom_input_records"],
            strict=True,
        )
        if before != after
    ]
    if delta == 0:
        assert changed == []
        return
    assert sorted(after["name"] for _, after in changed) == sorted(
        [SECTION_86_INPUT, EITC_INVESTMENT_INCOME_INPUT]
    )
    for before, after in changed:
        assert (after["entity"], after["entity_id"]) == ("TaxUnit", "tax_unit")
        assert after["value"] - before["value"] == delta


@PROPERTY_SETTINGS
@given(
    household=households(),
    dependent_interest=st.lists(TAX_EXEMPT_INTEREST, min_size=3, max_size=3),
)
def test_property_dependents_tax_exempt_interest_changes_no_projection(
    household, dependent_interest
) -> None:
    """A dependent's line 2a is not the filers' (86(b)(2)(B), Worksheet 1
    line 2 without Form 8814) and is not gross income (103(a)), so it moves
    no Axiom record or relation, no TAXSIM column, and no Tax-Calculator
    column — the head-of-household test included."""
    head, spouse, dependents = household
    base_case = _household_case(head, spouse, dependents)
    varied_case = _household_case(
        head,
        spouse,
        [
            _with_tax_exempt_interest(dependent, amount)
            for dependent, amount in zip(dependents, dependent_interest)
        ],
    )

    base = attach_axiom_tax_inputs_to_case(base_case)
    varied = attach_axiom_tax_inputs_to_case(varied_case)
    assert (
        varied.metadata["axiom_input_records"] == (base.metadata["axiom_input_records"])
    )
    assert varied.metadata["axiom_relations"] == base.metadata["axiom_relations"]
    assert taxsim_input_for_case(varied_case, taxsimid=1) == taxsim_input_for_case(
        base_case, taxsimid=1
    )
    assert taxcalc_input_for_case(varied_case, record_id=1) == (
        taxcalc_input_for_case(base_case, record_id=1)
    )
    (attached,) = attach_taxsim_inputs([varied_case])
    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in attached.metadata


@PROPERTY_SETTINGS
@given(
    household=households(),
    head_interest=TAX_EXEMPT_INTEREST,
    spouse_interest=TAX_EXEMPT_INTEREST,
)
def test_property_taxsim_row_ignores_tax_exempt_interest_and_records_the_drop(
    household, head_interest, spouse_interest
) -> None:
    """TAXSIM has no line-2a column, so the row is invariant; the dropped
    head + spouse amount is recorded on the case (only when nonzero) as a
    JSON-serializable mapping."""
    head, spouse, dependents = household
    base_case = _household_case(head, spouse, dependents)
    varied_case = _household_case(
        _with_tax_exempt_interest(head, head_interest),
        (
            _with_tax_exempt_interest(spouse, spouse_interest)
            if spouse is not None
            else None
        ),
        dependents,
    )
    delta = head_interest + (spouse_interest if spouse is not None else 0)

    (base,) = attach_taxsim_inputs([base_case])
    (varied,) = attach_taxsim_inputs([varied_case])
    assert varied.metadata["taxsim_input"] == base.metadata["taxsim_input"]
    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in base.metadata
    if delta == 0:
        assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in varied.metadata
        return
    recorded = varied.metadata[TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY]
    assert recorded == {"tax_exempt_interest_income": delta}
    assert json.loads(json.dumps(recorded)) == recorded


@PROPERTY_SETTINGS
@given(
    household=households(),
    head_interest=TAX_EXEMPT_INTEREST,
    spouse_interest=TAX_EXEMPT_INTEREST,
)
def test_property_taxcalc_row_moves_only_e00400_by_the_filer_delta(
    household, head_interest, spouse_interest
) -> None:
    """e00400 carries the filing unit's line 2a; no other Tax-Calculator
    column reads it."""
    head, spouse, dependents = household
    base = taxcalc_input_for_case(
        _household_case(head, spouse, dependents), record_id=1
    )
    varied = taxcalc_input_for_case(
        _household_case(
            _with_tax_exempt_interest(head, head_interest),
            (
                _with_tax_exempt_interest(spouse, spouse_interest)
                if spouse is not None
                else None
            ),
            dependents,
        ),
        record_id=1,
    )
    delta = head_interest + (spouse_interest if spouse is not None else 0)

    assert set(varied) == set(base)
    assert {column for column in base if varied[column] != base[column]} == (
        {"e00400"} if delta else set()
    )
    assert base["e00400"] == 0
    assert varied["e00400"] == delta


@PROPERTY_SETTINGS
@given(
    household=households(),
    amounts=st.lists(TAX_EXEMPT_INTEREST, min_size=5, max_size=5),
)
def test_property_policyengine_inputs_carry_each_persons_tax_exempt_interest(
    household, amounts
) -> None:
    """Every PolicyEngine input path pins tax_exempt_interest_income per
    person exactly as the Case facts say, and 0 where a person has none."""
    head, spouse, dependents = household
    people = [head, *([spouse] if spouse is not None else []), *dependents]
    people = [
        _with_tax_exempt_interest(person, amount)
        for person, amount in zip(people, amounts)
    ]
    case = _case(*people)
    expected = {
        person.entity_id: person.fact(Concepts.TAX_EXEMPT_INTEREST_INCOME, 0)
        for person in people
    }
    runner = PolicyEngineRunner()

    situation = runner._build_situation_from_case(case)
    assert {
        name: inputs["tax_exempt_interest_income"]
        for name, inputs in situation["people"].items()
    } == {name: {2026: amount} for name, amount in expected.items()}

    calculator = runner._build_household_calculator_input_from_case(case)
    assert [
        person["tax_exempt_interest_income"] for person in calculator["people"]
    ] == [expected[person.entity_id] for person in people]

    person_rows = runner._policyengine_dataset_rows([case], ["income_tax"])[0]
    assert {
        row["person_id"]: row["tax_exempt_interest_income"] for row in person_rows
    } == {f"case_0__{name}": amount for name, amount in expected.items()}
