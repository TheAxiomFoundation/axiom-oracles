"""Farm rental income (Schedule E line 40) on every Case projection.

Ground truth (verbatim; U.S. government works):

Form 4835 (2025), header: "Farm Rental Income and Expenses (Crop and
Livestock Shares (Not Cash) Received by Landowner (or Sub-Lessor)) (Income
Not Subject to Self-Employment Tax)".
    "32 Net farm rental income or (loss). Subtract line 31 from line 7. If
        the result is income, enter it here and on Schedule E (Form 1040),
        line 40. If the result is a loss, you must go to line 34."
    "c You may have to complete Form 8582 to determine your deductible loss
       ... enter the deductible loss here and on Schedule E (Form 1040),
       line 40." (line 34c)
Form 4835 instructions (2025), p. 2: "Use this form only if the activity was a
rental activity for purposes of the passive activity loss limitations."

Schedule E (Form 1040) 2025, p. 1: "If you are an individual, report farm
rental income or loss from Form 4835 on page 2, line 40." p. 2, Part V:
    "40 Net farm rental income or (loss) from Form 4835."
    "41 Total income or (loss). Combine lines 26, 32, 37, 39, and 40. Enter
        the result here and on Schedule 1 (Form 1040), line 5"
Schedule 1 (Form 1040) 2025: "5 Rental real estate, royalties, partnerships,
S corporations, trusts, etc. Attach Schedule E".

26 USC 199A(c)(1): "The term “qualified business income” means, for any
taxable year, the net amount of qualified items of income, gain, deduction,
and loss with respect to any qualified trade or business of the taxpayer."
199A(c)(3)(B) excludes capital gains, dividends, non-business interest,
954(c)(1)(C)-(D) and (F) items, and non-business annuities; it does not name
rents. 26 CFR 1.199A-1(b)(14): "Trade or business means a trade or business
that is a trade or business under section 162 (a section 162 trade or
business) other than the trade or business of performing services as an
employee." Instructions for Form 8995 (2025): "Material participation under
section 469 isn't required to qualify for the QBI deduction." and "The
ownership and rental of real property may constitute a trade or business if
it meets the standard described above."

26 USC 461(l)(3)(A): the excess business loss is the excess of "the aggregate
deductions of the taxpayer for the taxable year which are attributable to
trades or businesses of such taxpayer" over "the aggregate gross income or
gain of such taxpayer for the taxable year which is attributable to such
trades or businesses, plus" the threshold. Form 461 (2025): "5 Enter amount
from Schedule 1 (Form 1040), line 5".

Instructions for Form 8960 (2025), line 4a: "Enter the following amount from
your properly completed return. ... Schedule 1 (Form 1040), line 5." and
"Farm income from a passive activity is subject to the tax under section
1411(c)(2)."

TAXSIM (taxsim.nber.org/taxsimtest): "14. otherprop Other property income in
AGI subject to NIIT, including unearned or limited partnership and passive
S-Corp profits rent not eligible for QBI deduction non-qualified dividends
other taxable income or loss not otherwise included".

Tax-Calculator 6.7.1 records_variables.json: e02000 "Sch E total rental,
royalty, partnership, S-corporation, etc, income/loss (includes e26270 and
e27200)"; e27200 "Sch E: Farm rent net income or loss (included in e02000)".

Every expected amount below comes from those texts and the stated inputs,
never from the code under test.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.adapters.taxcalc.projection import taxcalc_input_for_case
from axiom_oracles.adapters.taxsim.projection import (
    TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY,
    attach_taxsim_inputs,
    taxsim_input_for_case,
)
from axiom_oracles.core.case import Case, Concepts, Entity

PERSON_FARM_RENT_INPUT = "us:tax/oracle-bridge#input.person_farm_rent_income"
EITC_INVESTMENT_INCOME_INPUT = (
    "us:tax/federal-income-tax#input.eitc_relevant_investment_income"
)
NIIT_RENTS_INPUT = "us:statutes/26/1411#input.rental_income"
FILING_STATUS_INPUT = "us:tax/federal-income-tax#input.filing_status"
PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)
RULES = {rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES}


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


def _case(*people):
    return Case(
        case_id="farm-rent",
        period="2026",
        entities=tuple(people),
        metadata={"state_code": "CO"},
    )


def _by_key(case):
    return {
        (record["entity_id"], record["name"]): record["value"]
        for record in attach_axiom_tax_inputs_to_case(case).metadata[
            "axiom_input_records"
        ]
    }


def _formula(name):
    (version,) = RULES[name]["versions"]
    return version["formula"]


def _with_farm_rent(entity, amount):
    if entity is None or not amount:
        return entity
    return Entity(
        entity.entity_id,
        entity.kind,
        facts={**entity.facts, Concepts.FARM_RENT_INCOME: amount},
    )


# ---------------------------------------------------------------------------
# The Axiom bridge: one signed per-person input, read by four bridge legs.
# ---------------------------------------------------------------------------


def test_each_person_carries_their_signed_schedule_e_line_40() -> None:
    by_key = _by_key(
        _case(
            _person(
                "person-1",
                "HeadOfHousehold",
                61,
                **{Concepts.FARM_RENT_INCOME: 18_250.5},
            ),
            _person("person-2", "Spouse", 59, **{Concepts.FARM_RENT_INCOME: -4_100}),
            _person("person-3", "Child", 12),
        )
    )

    assert by_key[("person-1", PERSON_FARM_RENT_INPUT)] == 18_250.5
    assert by_key[("person-2", PERSON_FARM_RENT_INPUT)] == -4_100
    assert by_key[("person-3", PERSON_FARM_RENT_INPUT)] == 0


def test_gross_income_takes_the_positive_part_and_461l_the_loss() -> None:
    """Line 40 is net income or (loss). As with Part I rents, the positive
    part is a 26 USC 61 gross-income leaf and the loss is an above-the-line
    deduction inside the 461(l) business-loss sum, filers only."""
    assert _formula("person_positive_farm_rent_income_for_agi") == (
        "max(0, person_farm_rent_income)"
    )
    assert _formula("person_farm_rent_loss_for_agi") == (
        "max(0, -person_farm_rent_income)"
    )
    assert "positive_farm_rent_income_for_agi" in _formula(
        "gross_income_before_social_security_benefits"
    )
    assert _formula("positive_farm_rent_income_for_agi") == (
        "sum_where(filer_adjusted_earnings_of_tax_unit, "
        "person_positive_farm_rent_income_for_agi, "
        "person_has_positive_farm_rent_income_for_agi)"
    )
    assert (
        "sum_where(filer_adjusted_earnings_of_tax_unit, "
        "person_farm_rent_loss_for_agi, person_has_farm_rent_loss_for_agi)"
    ) in _formula("business_loss_for_loss_limit")
    # 461(l)(3)(A)(ii)(I): positive trade-or-business income raises the
    # allowance, so the positive part also joins business_income_for_loss_limit.
    assert (
        "sum_where(filer_adjusted_earnings_of_tax_unit, "
        "person_positive_farm_rent_income_for_agi, "
        "person_has_positive_farm_rent_income_for_agi)"
    ) in _formula("business_income_for_loss_limit")


def test_farm_rent_is_qbi_like_part_i_rents() -> None:
    """199A(c)(3)(B) does not exclude rents; whether a rental is a section
    162 trade or business turns on facts the Case lacks, so both Schedule E
    rental streams take the same convention."""
    formula = _formula("business_income_for_qbid")
    assert "+ person_rental_income_for_qbid " in formula
    assert "+ person_farm_rent_income " in formula


def test_colorado_withholding_proxy_reads_farm_rent_like_part_i_rents() -> None:
    assert "+ person_farm_rent_income " in _formula("person_agi_for_co_withholding")
    assert "+ person_positive_farm_rent_income_for_agi " in _formula(
        "person_gross_income_for_co_withholding_count"
    )


def test_niit_rents_input_adds_the_filers_farm_rent() -> None:
    """Form 8960 line 4a takes Schedule 1 line 5 (which carries Schedule E
    line 40), and a Form 4835 activity is a rental activity, so passive farm
    rent is 1411(c)(1)(A)(i) rents. Dependents' amounts are their own."""
    by_key = _by_key(
        _case(
            _person(
                "person-1",
                "HeadOfHousehold",
                50,
                **{
                    Concepts.RENTAL_INCOME: 2_000,
                    Concepts.FARM_RENT_INCOME: 9_000,
                },
            ),
            _person("person-2", "Spouse", 49, **{Concepts.FARM_RENT_INCOME: -1_500}),
            _person("person-3", "Child", 9, **{Concepts.FARM_RENT_INCOME: 700}),
        )
    )

    assert by_key[("tax_unit", NIIT_RENTS_INPUT)] == 2_000 + 9_000 - 1_500


@pytest.mark.parametrize(
    ("wages", "farm_rent", "head_of_household"),
    [
        # 5,499 of gross income is under the projection's 5,500 young-adult
        # limit; 5,500 is not. A loss is no gross income (26 USC 61(a)(5)
        # rents enter as the positive part), so it neither counts nor
        # offsets the dependent's 6,000 of wages.
        pytest.param(0, 5_499, True, id="under-the-limit"),
        pytest.param(0, 5_500, False, id="at-the-limit"),
        pytest.param(0, -20_000, True, id="a-loss-is-no-gross-income"),
        pytest.param(6_000, -20_000, False, id="a-loss-does-not-offset-wages"),
    ],
)
def test_dependent_farm_rent_counts_in_the_head_of_household_gross_income_test(
    wages, farm_rent, head_of_household
) -> None:
    dependent = _person(
        "person-2",
        "Child",
        21,
        **{
            Concepts.YEARLY_EARNED_INCOME: wages,
            Concepts.FARM_RENT_INCOME: farm_rent,
        },
    )
    case = _case(_person("person-1", "HeadOfHousehold", 48), dependent)

    assert _by_key(case)[("tax_unit", FILING_STATUS_INPUT)] == (
        3 if head_of_household else 0
    )


# ---------------------------------------------------------------------------
# The other engines' rows.
# ---------------------------------------------------------------------------


def _joint_with_child():
    return (
        _person(
            "person-1",
            "HeadOfHousehold",
            63,
            **{
                Concepts.YEARLY_EARNED_INCOME: 40_000,
                Concepts.RENTAL_INCOME: 3_000,
                Concepts.FARM_RENT_INCOME: 11_000,
            },
        ),
        _person("person-2", "Spouse", 60, **{Concepts.FARM_RENT_INCOME: -2_500}),
        _person("person-3", "Child", 14, **{Concepts.FARM_RENT_INCOME: 900}),
    )


def test_taxsim_otherprop_carries_the_filers_farm_rent() -> None:
    row = taxsim_input_for_case(_case(*_joint_with_child()), taxsimid=1)

    # Part I rents 3,000 plus filer farm rent 11,000 - 2,500; the child's
    # 900 is on the child's own return.
    assert row["otherprop"] == 3_000 + 11_000 - 2_500
    (attached,) = attach_taxsim_inputs([_case(*_joint_with_child())])
    assert TAXSIM_UNPROJECTED_INPUTS_METADATA_KEY not in attached.metadata


def test_taxcalc_e27200_is_inside_e02000() -> None:
    row = taxcalc_input_for_case(_case(*_joint_with_child()), record_id=1)

    assert row["e27200"] == 11_000 - 2_500
    assert row["e02000"] == 3_000 + 11_000 - 2_500


@pytest.mark.parametrize(
    ("wages", "farm_rent", "mars"),
    # The Tax-Calculator projection's own limit is 5,200 (the Axiom
    # projection's is 5,500; axiom-oracles#611 tracks both against the
    # $5,300 of Rev. Proc. 2025-32 section .23).
    [
        pytest.param(0, 5_199, 4, id="under-the-limit"),
        pytest.param(0, 5_200, 1, id="at-the-limit"),
        pytest.param(0, -20_000, 4, id="a-loss-is-no-gross-income"),
        pytest.param(6_000, -20_000, 1, id="a-loss-does-not-offset-wages"),
    ],
)
def test_taxcalc_head_of_household_test_counts_dependent_farm_rent(
    wages, farm_rent, mars
):
    dependent = _person(
        "person-2",
        "Child",
        21,
        **{
            Concepts.YEARLY_EARNED_INCOME: wages,
            Concepts.FARM_RENT_INCOME: farm_rent,
        },
    )
    row = taxcalc_input_for_case(
        _case(_person("person-1", "HeadOfHousehold", 48), dependent),
        record_id=1,
    )
    assert row["MARS"] == mars


def test_policyengine_receives_farm_rent_income_per_person() -> None:
    people = _joint_with_child()
    case = _case(*people)
    runner = PolicyEngineRunner()

    situation = runner._build_situation_from_case(case)
    assert {
        name: inputs["farm_rent_income"] for name, inputs in situation["people"].items()
    } == {
        "person-1": {2026: 11_000},
        "person-2": {2026: -2_500},
        "person-3": {2026: 900},
    }


# ---------------------------------------------------------------------------
# Invariants (property-based, derandomized).
# ---------------------------------------------------------------------------

NON_NEGATIVE = st.integers(min_value=0, max_value=200_000)
SIGNED = st.integers(min_value=-200_000, max_value=200_000)
FARM_RENT = st.integers(min_value=-150_000, max_value=150_000)
PERSON_INCOME = st.fixed_dictionaries(
    {
        Concepts.YEARLY_EARNED_INCOME: NON_NEGATIVE,
        Concepts.SELF_EMPLOYMENT_INCOME: SIGNED,
        Concepts.INTEREST_INCOME: NON_NEGATIVE,
        Concepts.TAX_EXEMPT_INTEREST_INCOME: NON_NEGATIVE,
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
    """A head, an optional spouse, and up to three dependents with every
    other Case income concept drawn; farm rent is added by each test."""
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


def _filer_passive_basket(head, spouse):
    return sum(
        float(person.fact(Concepts.RENTAL_INCOME, 0) or 0)
        + float(person.fact(Concepts.FARM_RENT_INCOME, 0) or 0)
        for person in (head, spouse)
        if person is not None
    )


@PROPERTY_SETTINGS
@given(household=households(), head_rent=FARM_RENT, spouse_rent=FARM_RENT)
def test_property_filer_farm_rent_moves_exactly_its_axiom_inputs(
    household, head_rent, spouse_rent
) -> None:
    """Varying only the filers' farm rent changes, and changes by exactly
    the stated amounts: each filer's person_farm_rent_income (by that
    filer's amount), the 1411 rents input (by the filer sum), and Worksheet
    1 line 13 (by its floored change). Every other record and every
    relation is identical."""
    head, spouse, dependents = household
    spouse_rent = spouse_rent if spouse is not None else 0
    base_case = _household_case(head, spouse, dependents)
    varied_head = _with_farm_rent(head, head_rent)
    varied_spouse = _with_farm_rent(spouse, spouse_rent)
    varied_case = _household_case(varied_head, varied_spouse, dependents)
    base = attach_axiom_tax_inputs_to_case(base_case)
    varied = attach_axiom_tax_inputs_to_case(varied_case)

    line_13_change = max(0.0, _filer_passive_basket(varied_head, varied_spouse)) - (
        max(0.0, _filer_passive_basket(head, spouse))
    )
    expected = {
        ("person-1", PERSON_FARM_RENT_INPUT): head_rent,
        ("person-2", PERSON_FARM_RENT_INPUT): spouse_rent,
        ("tax_unit", NIIT_RENTS_INPUT): head_rent + spouse_rent,
        ("tax_unit", EITC_INVESTMENT_INCOME_INPUT): line_13_change,
    }

    assert varied.metadata["axiom_relations"] == base.metadata["axiom_relations"]
    changes = {}
    for before, after in zip(
        base.metadata["axiom_input_records"],
        varied.metadata["axiom_input_records"],
        strict=True,
    ):
        assert (before["name"], before["entity_id"]) == (
            after["name"],
            after["entity_id"],
        )
        if before != after:
            changes[(after["entity_id"], after["name"])] = (
                after["value"] - before["value"]
            )
    assert changes == {key: delta for key, delta in expected.items() if delta}


@PROPERTY_SETTINGS
@given(
    household=households(),
    dependent_rent=st.lists(FARM_RENT, min_size=3, max_size=3),
)
def test_property_dependents_farm_rent_reaches_only_their_input_and_the_hoh_test(
    household, dependent_rent
) -> None:
    """A dependent's Schedule E is on the dependent's own return: it moves
    only that dependent's person input and, through the 152(d) gross-income
    test, the filing status. No TAXSIM or Tax-Calculator income column
    moves."""
    head, spouse, dependents = household
    base_case = _household_case(head, spouse, dependents)
    varied_dependents = [
        _with_farm_rent(dependent, amount)
        for dependent, amount in zip(dependents, dependent_rent)
    ]
    varied_case = _household_case(head, spouse, varied_dependents)

    base = _by_key(base_case)
    varied = _by_key(varied_case)
    assert set(base) == set(varied)
    changed = {key for key in base if base[key] != varied[key]}
    allowed = {
        (dependent.entity_id, PERSON_FARM_RENT_INPUT) for dependent in dependents
    }
    filing_status_moved = base[("tax_unit", FILING_STATUS_INPUT)] != (
        varied[("tax_unit", FILING_STATUS_INPUT)]
    )
    if not filing_status_moved:
        assert changed <= allowed
    for dependent, amount in zip(dependents, dependent_rent):
        assert varied[(dependent.entity_id, PERSON_FARM_RENT_INPUT)] == amount

    base_taxsim = taxsim_input_for_case(base_case, taxsimid=1)
    varied_taxsim = taxsim_input_for_case(varied_case, taxsimid=1)
    assert varied_taxsim == base_taxsim
    base_taxcalc = taxcalc_input_for_case(base_case, record_id=1)
    varied_taxcalc = taxcalc_input_for_case(varied_case, record_id=1)
    assert {
        column
        for column in base_taxcalc
        if base_taxcalc[column] != varied_taxcalc[column]
    } <= {"MARS"}


@PROPERTY_SETTINGS
@given(household=households(), head_rent=FARM_RENT, spouse_rent=FARM_RENT)
def test_property_taxsim_otherprop_moves_by_exactly_the_filer_farm_rent(
    household, head_rent, spouse_rent
) -> None:
    head, spouse, dependents = household
    spouse_rent = spouse_rent if spouse is not None else 0
    base = taxsim_input_for_case(_household_case(head, spouse, dependents), taxsimid=1)
    varied = taxsim_input_for_case(
        _household_case(
            _with_farm_rent(head, head_rent),
            _with_farm_rent(spouse, spouse_rent),
            dependents,
        ),
        taxsimid=1,
    )
    delta = head_rent + spouse_rent

    assert set(varied) == set(base)
    assert {column for column in base if varied[column] != base[column]} == (
        {"otherprop"} if delta else set()
    )
    assert varied["otherprop"] - base["otherprop"] == delta


@PROPERTY_SETTINGS
@given(household=households(), head_rent=FARM_RENT, spouse_rent=FARM_RENT)
def test_property_taxcalc_farm_rent_is_e27200_and_inside_e02000(
    household, head_rent, spouse_rent
) -> None:
    """e27200 is the filers' farm rent and e02000 always contains it, so
    Tax-Calculator never grants QBID (qbinc reads e27200) on farm rent
    that AGI (ymod1 reads e02000) leaves out. Nothing else moves."""
    head, spouse, dependents = household
    spouse_rent = spouse_rent if spouse is not None else 0
    base = taxcalc_input_for_case(_household_case(head, spouse, dependents), record_id=1)
    varied = taxcalc_input_for_case(
        _household_case(
            _with_farm_rent(head, head_rent),
            _with_farm_rent(spouse, spouse_rent),
            dependents,
        ),
        record_id=1,
    )
    delta = head_rent + spouse_rent
    rental = sum(
        float(person.fact(Concepts.RENTAL_INCOME, 0) or 0)
        for person in (head, spouse)
        if person is not None
    )

    assert set(varied) == set(base)
    assert {column for column in base if varied[column] != base[column]} == (
        {"e02000", "e27200"} if delta else set()
    )
    assert base["e27200"] == 0
    assert varied["e27200"] == delta
    assert varied["e02000"] - varied["e27200"] == pytest.approx(rental)


@PROPERTY_SETTINGS
@given(
    household=households(),
    amounts=st.lists(FARM_RENT, min_size=5, max_size=5),
)
def test_property_policyengine_inputs_carry_each_persons_farm_rent(
    household, amounts
) -> None:
    """Every PolicyEngine input path pins farm_rent_income per person
    exactly as the Case facts say (sign kept), and 0 where a person has
    none."""
    head, spouse, dependents = household
    people = [head, *([spouse] if spouse is not None else []), *dependents]
    people = [
        _with_farm_rent(person, amount) for person, amount in zip(people, amounts)
    ]
    case = _case(*people)
    expected = {
        person.entity_id: person.fact(Concepts.FARM_RENT_INCOME, 0) for person in people
    }
    runner = PolicyEngineRunner()

    situation = runner._build_situation_from_case(case)
    assert {
        name: inputs["farm_rent_income"] for name, inputs in situation["people"].items()
    } == {name: {2026: amount} for name, amount in expected.items()}

    calculator = runner._build_household_calculator_input_from_case(case)
    assert [person["farm_rent_income"] for person in calculator["people"]] == [
        expected[person.entity_id] for person in people
    ]

    person_rows = runner._policyengine_dataset_rows([case], ["income_tax"])[0]
    assert {row["person_id"]: row["farm_rent_income"] for row in person_rows} == {
        f"case_0__{name}": amount for name, amount in expected.items()
    }
