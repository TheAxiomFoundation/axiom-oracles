"""26 USC 32(i)(2) disqualified income on both Axiom tax projection surfaces.

Ground truth is IRS Publication 596 (2025), "Worksheet 1. Investment Income"
(PDF page 7, https://www.irs.gov/pub/irs-pdf/p596.pdf), used "when you file
Form 1040 or 1040-SR":

    1.  Form 1040 line 2b (taxable interest)
    2.  Form 1040 line 2a (tax-exempt interest), plus Form 8814 line 1b
    3.  Form 1040 line 3b (ordinary dividends)
    4.  Form 8814 amounts on Schedule 1 line 8z (not modeled here)
    5.  Form 1040 line 7a. If the amount on that line is a loss, enter -0-
    6.  Form 4797 line 7 gain (not modeled here)
    7.  line 5 minus line 6; if less than zero, enter -0-
    8-10. royalties and personal-property rent, floored at zero (not
          separable from rental_income here)
    11. net income from passive activities (Schedule E lines 26, 29a (h),
        34a (d), 40; Form 4797 line 10 gains)
    12. losses from passive activities (the same lines' loss columns)
    13. combine lines 11 and 12; if less than zero, enter -0-
    14. add lines 1, 2, 3, 4, 7, 10, and 13. This is your investment income

Every expected value below is that arithmetic done by hand from the stated
inputs (axiom-oracles#562), never an engine's output.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.bridges.tax_populace import (
    project_eitc_relevant_investment_income,
    project_eitc_tax_unit_inputs,
)
from axiom_oracles.core.case import Case, Concepts, Entity

EITC_INVESTMENT_INCOME_INPUT = (
    "us:tax/federal-income-tax#input.eitc_relevant_investment_income"
)
PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)

# ---------------------------------------------------------------------------
# Populace bridge: project_eitc_relevant_investment_income over filer rows.
# ---------------------------------------------------------------------------

BRIDGE_WORKSHEET_1_CASES = [
    pytest.param(
        [{"taxable_interest_income": 12_500, "rental_income": -10_000}],
        12_500,
        id="rental-loss-does-not-offset-interest",
        # line 1 = 12,500; line 12 = -10,000, line 13 = max(0, -10,000) = 0
    ),
    pytest.param(
        [{"taxable_interest_income": 6_000, "tax_exempt_interest_income": 6_500}],
        12_500,
        id="tax-exempt-interest-is-line-2",
        # line 1 = 6,000; line 2 = 6,500; line 14 = 12,500
    ),
    pytest.param(
        [
            {
                "taxable_interest_income": 8_000,
                "passive_partnership_s_corp_income": 5_000,
            }
        ],
        13_000,
        id="passive-s-corp-income-is-line-11",
        # line 1 = 8,000; line 11 = 5,000, line 13 = 5,000; line 14 = 13,000
    ),
    pytest.param(
        [{"taxable_interest_income": 12_500, "short_term_capital_gains": -3_000}],
        12_500,
        id="capital-loss-does-not-offset-interest",
        # line 5: Form 1040 line 7a is a loss, enter -0-; line 7 = 0
    ),
    pytest.param(
        [
            {
                "taxable_interest_income": 8_000,
                "rental_income": 5_000,
                "passive_partnership_s_corp_income": -10_000,
            }
        ],
        8_000,
        id="passive-losses-net-within-the-passive-basket",
        # line 11 = 5,000; line 12 = -10,000; line 13 = max(0, -5,000) = 0
    ),
    pytest.param(
        [
            {
                "taxable_interest_income": 8_000,
                "farm_rent_income": 3_000,
                "rental_income": -1_000,
            }
        ],
        10_000,
        id="farm-rental-income-is-schedule-e-line-40",
        # line 11 = 3,000 (Sch E line 40); line 12 = -1,000; line 13 = 2,000
    ),
    pytest.param(
        [
            {
                "taxable_interest_income": 1_000,
                "non_sch_d_capital_gains": 2_000,
                "short_term_capital_gains": -500,
            }
        ],
        2_500,
        id="capital-gain-distributions-net-into-form-1040-line-7a",
        # line 5 = Form 1040 line 7a = 2,000 - 500 = 1,500; line 7 = 1,500
    ),
    pytest.param(
        [
            {
                "long_term_capital_gains_before_response": 4_000,
                "long_term_capital_gains": 9_999,
                "short_term_capital_gains": 1_000,
            }
        ],
        5_000,
        id="long-term-gain-reads-the-before-response-column-first",
        # line 5 = 4,000 + 1,000 = 5,000 (the first available LT column)
    ),
    pytest.param(
        [{"qualified_dividend_income": 7_000, "non_qualified_dividend_income": 3_000}],
        10_000,
        id="ordinary-dividends-are-line-3b-once",
        # line 3 = Form 1040 line 3b = 7,000 qualified + 3,000 non-qualified
    ),
    pytest.param(
        [
            {"taxable_interest_income": 12_500},
            {"rental_income": -10_000},
        ],
        12_500,
        id="joint-spouse-rental-loss-does-not-offset-head-interest",
        # one joint return: line 1 = 12,500; line 13 = max(0, -10,000) = 0
    ),
    pytest.param(
        [
            {
                "taxable_interest_income": 9_000,
                "passive_partnership_s_corp_income": 5_000,
            },
            {"passive_partnership_s_corp_income": -4_000},
        ],
        10_000,
        id="joint-passive-amounts-net-across-spouses-before-the-floor",
        # line 11 = 5,000; line 12 = -4,000; line 13 = 1,000; 9,000 + 1,000
    ),
    pytest.param(
        [
            {
                "taxable_interest_income": 2_000,
                "tax_exempt_interest_income": 1_000,
                "qualified_dividend_income": 500,
                "non_qualified_dividend_income": 250,
                "long_term_capital_gains": 3_000,
                "short_term_capital_gains": -1_000,
                "rental_income": 4_000,
                "farm_rent_income": -6_000,
            },
            {
                "taxable_interest_income": 750,
                "passive_partnership_s_corp_income": 2_500,
            },
        ],
        7_000,
        id="all-baskets-joint",
        # line 1 = 2,000 + 750 = 2,750; line 2 = 1,000; line 3 = 750;
        # line 5 = 3,000 - 1,000 = 2,000, line 7 = 2,000;
        # line 11 = 4,000 + 2,500 = 6,500, line 12 = -6,000, line 13 = 500;
        # line 14 = 2,750 + 1,000 + 750 + 2,000 + 500 = 7,000
    ),
]


@pytest.mark.parametrize(("filers", "expected"), BRIDGE_WORKSHEET_1_CASES)
def test_bridge_matches_pub_596_worksheet_1(filers, expected):
    assert (
        project_eitc_relevant_investment_income(
            row={"filing_status": "JOINT" if len(filers) == 2 else "SINGLE"},
            persons=filers,
        )
        == expected
    )


def test_bridge_does_not_read_undifferentiated_partnership_income():
    """Intended convention, not a worksheet line: only the passive subset of
    partnership/S-corp income belongs on lines 11-12, and the undifferentiated
    ``partnership_income`` column cannot say which part that is."""
    assert (
        project_eitc_relevant_investment_income(
            row={"filing_status": "SINGLE"},
            persons=[{"taxable_interest_income": 1_000, "partnership_income": 50_000}],
        )
        == 1_000
    )


def _person(age, role, **income):
    return {
        "age": age,
        "is_tax_unit_head": role == "head",
        "is_tax_unit_spouse": role == "spouse",
        "is_tax_unit_head_or_spouse": role in {"head", "spouse"},
        "ssn_card_type": "CITIZEN",
        **income,
    }


@pytest.mark.parametrize("explicit_roles", [True, False], ids=["roles", "ages"])
@pytest.mark.parametrize(
    ("dependent_income", "expected"),
    [
        pytest.param({"taxable_interest_income": 8_000}, 5_000, id="interest"),
        pytest.param({"rental_income": -10_000}, 5_000, id="rental-loss"),
        pytest.param({"short_term_capital_gains": 20_000}, 5_000, id="gain"),
    ],
)
def test_bridge_excludes_dependent_income(explicit_roles, dependent_income, expected):
    """Worksheet 1 lines 1-3 read the filer's own Form 1040; a child's
    interest and dividends enter only through Form 8814 (line 2's 8814
    line 1b and line 4), which the projection does not model. So a
    dependent's amounts, gains or losses, leave line 14 at the filer's
    5,000 of interest."""
    head = _person(34, "head", taxable_interest_income=5_000)
    dependent = _person(12, "dependent", **dependent_income)
    if not explicit_roles:
        for person in (head, dependent):
            for flag in (
                "is_tax_unit_head",
                "is_tax_unit_spouse",
                "is_tax_unit_head_or_spouse",
            ):
                person.pop(flag)
    projected = project_eitc_tax_unit_inputs(
        row={"filing_status": "HEAD_OF_HOUSEHOLD", "adjusted_gross_income": 30_000},
        persons=[head, dependent],
    )
    assert projected["eitc_relevant_investment_income"] == expected


def test_bridge_keeps_both_spouses_and_drops_an_adult_dependent():
    """A joint return's line 1 is both spouses' interest (1,000 + 2,000);
    an adult dependent's 40,000 is on that dependent's own return."""
    projected = project_eitc_tax_unit_inputs(
        row={"filing_status": "JOINT", "adjusted_gross_income": 30_000},
        persons=[
            _person(40, "head", taxable_interest_income=1_000),
            _person(70, "dependent", taxable_interest_income=40_000),
            _person(38, "spouse", taxable_interest_income=2_000),
        ],
    )
    assert projected["eitc_relevant_investment_income"] == 3_000


# ---------------------------------------------------------------------------
# Case surface: attach_axiom_tax_inputs_to_case.
# ---------------------------------------------------------------------------


def _case_investment_income(*people_facts):
    entities = tuple(
        Entity(f"person-{index + 1}", "person", facts=facts)
        for index, facts in enumerate(people_facts)
    )
    projected = attach_axiom_tax_inputs_to_case(
        Case(case_id="eitc-worksheet-1", period="2026", entities=entities)
    )
    by_key = {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }
    return by_key[("tax_unit", EITC_INVESTMENT_INCOME_INPUT)]


def _head(**facts):
    return {
        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
        Concepts.PERSON_AGE: 40,
        Concepts.YEARLY_EARNED_INCOME: 20_000,
        **facts,
    }


def _spouse(**facts):
    return {Concepts.HOUSEHOLD_RELATION: "Spouse", Concepts.PERSON_AGE: 38, **facts}


def _child(**facts):
    return {Concepts.HOUSEHOLD_RELATION: "Child", Concepts.PERSON_AGE: 10, **facts}


@pytest.mark.parametrize(
    ("people", "expected"),
    [
        pytest.param(
            [
                _head(
                    **{
                        Concepts.INTEREST_INCOME: 12_500,
                        Concepts.RENTAL_INCOME: -10_000,
                    }
                )
            ],
            12_500,
            id="rental-loss-does-not-offset-interest",
            # line 1 = 12,500; line 13 = max(0, -10,000) = 0
        ),
        pytest.param(
            [
                _head(**{Concepts.INTEREST_INCOME: 12_500}),
                _spouse(**{Concepts.RENTAL_INCOME: -10_000}),
            ],
            12_500,
            id="joint-spouse-rental-loss-does-not-offset-head-interest",
        ),
        pytest.param(
            [
                _head(
                    **{
                        Concepts.INTEREST_INCOME: 12_500,
                        Concepts.SHORT_TERM_CAPITAL_GAINS: -3_000,
                    }
                )
            ],
            12_500,
            id="capital-loss-does-not-offset-interest",
            # line 5: a loss, enter -0-
        ),
        pytest.param(
            [
                _head(
                    **{
                        Concepts.INTEREST_INCOME: 8_000,
                        Concepts.RENTAL_INCOME: 5_000,
                    }
                ),
                _spouse(**{Concepts.RENTAL_INCOME: -10_000}),
            ],
            8_000,
            id="joint-rental-nets-across-spouses-before-the-floor",
            # line 11 = 5,000; line 12 = -10,000; line 13 = 0
        ),
        pytest.param(
            [
                _head(
                    **{
                        Concepts.INTEREST_INCOME: 1_000,
                        Concepts.DIVIDEND_INCOME: 3_000,
                        Concepts.QUALIFIED_DIVIDEND_INCOME: 2_000,
                        Concepts.LONG_TERM_CAPITAL_GAINS: 4_000,
                        Concepts.SHORT_TERM_CAPITAL_GAINS: -1_500,
                        Concepts.RENTAL_INCOME: 600,
                    }
                )
            ],
            7_100,
            id="all-case-baskets",
            # line 1 = 1,000; line 3 = 3,000 (qualified 2,000 is inside 3b);
            # line 7 = 2,500; line 13 = 600; line 14 = 7,100
        ),
        pytest.param(
            [
                _head(**{Concepts.INTEREST_INCOME: 5_000}),
                _child(
                    **{
                        Concepts.INTEREST_INCOME: 8_000,
                        Concepts.RENTAL_INCOME: -10_000,
                    }
                ),
            ],
            5_000,
            id="dependent-amounts-are-not-the-filers",
        ),
    ],
)
def test_case_surface_matches_pub_596_worksheet_1(people, expected):
    assert _case_investment_income(*people) == expected


# ---------------------------------------------------------------------------
# Invariants (property-based) and differential checks.
# ---------------------------------------------------------------------------

NON_NEGATIVE = st.integers(min_value=0, max_value=60_000)
SIGNED = st.integers(min_value=-60_000, max_value=60_000)
# Lines 1-3 and capital gain distributions cannot be negative on a return;
# capital gains and passive amounts can.
FILER_COLUMN_STRATEGIES = {
    "taxable_interest_income": NON_NEGATIVE,
    "tax_exempt_interest_income": NON_NEGATIVE,
    "qualified_dividend_income": NON_NEGATIVE,
    "non_qualified_dividend_income": NON_NEGATIVE,
    "long_term_capital_gains": SIGNED,
    "short_term_capital_gains": SIGNED,
    "non_sch_d_capital_gains": NON_NEGATIVE,
    "rental_income": SIGNED,
    "passive_partnership_s_corp_income": SIGNED,
    "farm_rent_income": SIGNED,
}
FILER_AMOUNTS = st.fixed_dictionaries(FILER_COLUMN_STRATEGIES)
FILERS = st.lists(FILER_AMOUNTS, min_size=1, max_size=2)
PORTFOLIO_COLUMNS = (
    "taxable_interest_income",
    "tax_exempt_interest_income",
    "qualified_dividend_income",
    "non_qualified_dividend_income",
)
PASSIVE_COLUMNS = (
    "rental_income",
    "passive_partnership_s_corp_income",
    "farm_rent_income",
)


def _worksheet_1_line_14(filers):
    """Worksheet 1 walked line by line, gains and losses on separate lines.

    An independent formulation of the same arithmetic, used as the reference
    in the differential property below: line 11 collects every passive gain
    and line 12 every passive loss before line 13 combines and floors them.
    """
    line_1 = sum(f.get("taxable_interest_income", 0) for f in filers)
    line_2 = sum(f.get("tax_exempt_interest_income", 0) for f in filers)
    line_3 = sum(
        f.get("qualified_dividend_income", 0)
        + f.get("non_qualified_dividend_income", 0)
        for f in filers
    )
    line_4 = 0
    form_1040_line_7a = sum(
        f.get("long_term_capital_gains", 0)
        + f.get("short_term_capital_gains", 0)
        + f.get("non_sch_d_capital_gains", 0)
        for f in filers
    )
    line_5 = form_1040_line_7a if form_1040_line_7a > 0 else 0
    line_6 = 0
    line_7 = max(0, line_5 - line_6)
    line_10 = 0
    passive = [f.get(column, 0) for f in filers for column in PASSIVE_COLUMNS]
    line_11 = sum(amount for amount in passive if amount > 0)
    line_12 = sum(amount for amount in passive if amount < 0)
    line_13 = max(0, line_11 + line_12)
    return line_1 + line_2 + line_3 + line_4 + line_7 + line_10 + line_13


def _bridge(filers):
    return project_eitc_relevant_investment_income(
        row={"filing_status": "JOINT"}, persons=filers
    )


@PROPERTY_SETTINGS
@given(filers=FILERS)
def test_property_bridge_equals_worksheet_1_walked_line_by_line(filers):
    assert _bridge(filers) == _worksheet_1_line_14(filers)


@PROPERTY_SETTINGS
@given(filers=FILERS)
def test_property_losses_never_cross_baskets(filers):
    """Result >= lines 1-3: no capital or passive loss reduces interest and
    dividends, and the result is never negative."""
    portfolio = sum(f[column] for f in filers for column in PORTFOLIO_COLUMNS)
    result = _bridge(filers)
    assert result >= portfolio >= 0


@PROPERTY_SETTINGS
@given(
    filers=FILERS,
    column=st.sampled_from(sorted(FILER_COLUMN_STRATEGIES)),
    bump=st.integers(min_value=0, max_value=60_000),
)
def test_property_monotone_in_every_component(filers, column, bump):
    """More income of any kind never lowers line 14."""
    bumped = [dict(f) for f in filers]
    bumped[-1][column] += bump
    assert _bridge(bumped) >= _bridge(filers)


@PROPERTY_SETTINGS
@given(filers=FILERS)
def test_property_bounded_by_positive_parts(filers):
    """Line 14 never exceeds the sum of every positive amount (floors only
    remove losses, they never add income)."""
    positive_parts = sum(max(0, amount) for f in filers for amount in f.values())
    assert _bridge(filers) <= positive_parts


@PROPERTY_SETTINGS
@given(filers=st.lists(FILER_AMOUNTS, min_size=2, max_size=2))
def test_property_spouse_order_and_merging_do_not_matter(filers):
    """A joint return has one Worksheet 1: swapping the spouses, or moving
    all amounts onto one spouse, leaves line 14 unchanged."""
    head, spouse = filers
    merged = {column: head[column] + spouse[column] for column in head}
    assert _bridge([head, spouse]) == _bridge([spouse, head]) == _bridge([merged])


@PROPERTY_SETTINGS
@given(filer=FILER_AMOUNTS, dependents=st.lists(FILER_AMOUNTS, max_size=3))
def test_property_dependents_never_change_the_tax_unit_input(filer, dependents):
    head = _person(40, "head", **filer)
    row = {"filing_status": "HEAD_OF_HOUSEHOLD", "adjusted_gross_income": 30_000}
    alone = project_eitc_tax_unit_inputs(row=row, persons=[head])
    with_dependents = project_eitc_tax_unit_inputs(
        row=row,
        persons=[head, *(_person(10, "dependent", **d) for d in dependents)],
    )
    assert (
        with_dependents["eitc_relevant_investment_income"]
        == alone["eitc_relevant_investment_income"]
        == _worksheet_1_line_14([filer])
    )


CASE_FILER_AMOUNTS = st.fixed_dictionaries(
    {
        "interest": NON_NEGATIVE,
        "qualified_dividends": NON_NEGATIVE,
        "non_qualified_dividends": NON_NEGATIVE,
        "short_term": SIGNED,
        "long_term": SIGNED,
        "rental": SIGNED,
    }
)


@PROPERTY_SETTINGS
@given(
    head=CASE_FILER_AMOUNTS,
    spouse=st.none() | CASE_FILER_AMOUNTS,
    child=st.none() | CASE_FILER_AMOUNTS,
)
def test_property_case_surface_agrees_with_the_bridge(head, spouse, child):
    """Differential: the two projections implement the same Worksheet 1
    semantics, so on inputs both surfaces can express they must agree."""

    def case_facts(amounts):
        return {
            Concepts.INTEREST_INCOME: amounts["interest"],
            Concepts.DIVIDEND_INCOME: amounts["qualified_dividends"]
            + amounts["non_qualified_dividends"],
            Concepts.QUALIFIED_DIVIDEND_INCOME: amounts["qualified_dividends"],
            Concepts.SHORT_TERM_CAPITAL_GAINS: amounts["short_term"],
            Concepts.LONG_TERM_CAPITAL_GAINS: amounts["long_term"],
            Concepts.RENTAL_INCOME: amounts["rental"],
        }

    def bridge_row(amounts):
        return {
            "taxable_interest_income": amounts["interest"],
            "qualified_dividend_income": amounts["qualified_dividends"],
            "non_qualified_dividend_income": amounts["non_qualified_dividends"],
            "short_term_capital_gains": amounts["short_term"],
            "long_term_capital_gains": amounts["long_term"],
            "rental_income": amounts["rental"],
        }

    people = [_head(**case_facts(head))]
    filers = [bridge_row(head)]
    if spouse is not None:
        people.append(_spouse(**case_facts(spouse)))
        filers.append(bridge_row(spouse))
    if child is not None:
        people.append(_child(**case_facts(child)))
    assert _case_investment_income(*people) == _bridge(filers)
