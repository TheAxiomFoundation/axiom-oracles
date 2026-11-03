"""A dependent's dividends and gains stay out of the filers' 1(h) base (#619).

Ground truth, verbatim:

- 26 USC 1(h)(1): "If a taxpayer has a net capital gain for any taxable year,
  the tax imposed by this section for such taxable year shall not exceed the
  sum of-- (A) a tax computed at the rates and in the same manner as if this
  subsection had not been enacted on the greater of-- (i) taxable income
  reduced by the net capital gain; ..."
- 26 USC 1(h)(11)(A)-(B)(i): net capital gain is "increased by qualified
  dividend income", meaning "dividends received during the taxable year".
- 26 USC 1(g)(7) lets a parent elect to put a child's interest and dividends
  on the parent's return ("Election to claim certain unearned income of child
  on parent's return"); no engine compared here models that election.

So the filers' worksheet reads the filers' dividends and gains. The AGI leaves
already sum the filers only, while the projection summed every member into the
1(h), worksheet and 1411 inputs, which put a dependent's qualified dividends
on line 4 of the filers' Qualified Dividends and Capital Gain Tax Worksheet
without their being on line 1, moving the filers' ordinary income into the 0%
and 15% brackets. The TAXSIM and Tax-Calculator projections already receive
filer sums.

Worked example: an unmarried head (wages 60,000) with a 10-year-old child who
received 10,000 of qualified dividends. Head-of-household taxable income is
60,000 - 24,150 = 35,850 (Rev. Proc. 2025-32 section 4.14(1)), all ordinary,
so the tax is 1,770 + 0.12 x (35,850 - 17,700) = 3,948 (section 4.01 Table 2).
Counting the child's dividends taxed 10,000 of it at 0% instead: 2,748.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    attach_axiom_tax_inputs_to_case,
    attach_axiom_tax_itemization_choice_to_case,
)
from axiom_oracles.adapters.taxcalc.projection import taxcalc_input_for_case
from axiom_oracles.adapters.taxsim.projection import taxsim_input_for_case
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)
CO_SCOPE = {"scope": {"type": "census_state", "geoid": "08"}}
BRIDGE = "us:tax/oracle-bridge#input."
INPUTS_1H = "us:statutes/26/1/h#input."
INPUTS_1411 = "us:statutes/26/1411#input."
FEDERAL = "us:tax/federal-income-tax#input."
TAX_BEFORE_CREDITS = (
    "us:statutes/26/1/j#income_tax_main_rates",
    "us:statutes/26/1/h#capital_gains_tax",
)
_MONEY = st.floats(min_value=0, max_value=50_000, allow_nan=False, allow_infinity=False)


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


def _tax_unit_inputs(case: Case) -> dict[str, object]:
    projected = attach_axiom_tax_inputs_to_case(case)
    return {
        record["name"]: record["value"]
        for record in projected.metadata["axiom_input_records"]
        if record["entity_id"] == "tax_unit"
    }


def _investment(dividends, qualified, short_term, long_term, interest):
    return {
        Concepts.DIVIDEND_INCOME: dividends,
        Concepts.QUALIFIED_DIVIDEND_INCOME: qualified,
        Concepts.SHORT_TERM_CAPITAL_GAINS: short_term,
        Concepts.LONG_TERM_CAPITAL_GAINS: long_term,
        Concepts.INTEREST_INCOME: interest,
    }


def test_dependent_investment_income_stays_off_the_filers_inputs() -> None:
    case = Case(
        case_id="1h-dependent",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 45, **{
                Concepts.YEARLY_EARNED_INCOME: 100_000,
                **_investment(1_000, 600, 100, 200, 70),
            }),
            _person("person-2", "Child", 15, **_investment(500, 300, 40, 50, 30)),
        ),
    )
    inputs = _tax_unit_inputs(case)

    expected = {
        f"{INPUTS_1H}qualified_dividend_income": 600,
        f"{INPUTS_1H}short_term_capital_gains": 100,
        f"{INPUTS_1H}long_term_capital_gains": 200,
        f"{BRIDGE}capital_gains_tax_qualified_dividend_income": 600,
        f"{BRIDGE}capital_gains_tax_short_term_capital_gains": 100,
        f"{BRIDGE}capital_gains_tax_long_term_capital_gains": 200,
        f"{FEDERAL}qualified_dividend_income": 600,
        f"{FEDERAL}short_term_capital_gains": 100,
        f"{FEDERAL}long_term_capital_gains": 200,
        f"{INPUTS_1411}dividend_income": 1_000,
        f"{INPUTS_1411}taxable_interest_income": 70,
    }
    assert {name: inputs[name] for name in expected} == expected


def _household(head, spouse, dependents):
    people = [
        _person("head", "HeadOfHousehold", 50, **{
            Concepts.YEARLY_EARNED_INCOME: 80_000,
            **head,
        })
    ]
    if spouse is not None:
        people.append(_person("spouse", "Spouse", 49, **spouse))
    for index, (age, facts) in enumerate(dependents):
        people.append(_person(f"child-{index}", "Child", age, **facts))
    return Case(
        case_id="1h-property",
        period="2026",
        metadata=CO_SCOPE,
        entities=tuple(people),
    )


@st.composite
def _investment_facts(draw):
    # Qualified dividends are a subset of ordinary dividends.
    qualified = draw(_MONEY)
    dividends = qualified + draw(_MONEY)
    return _investment(
        dividends,
        qualified,
        draw(st.floats(min_value=-20_000, max_value=50_000, allow_nan=False)),
        draw(st.floats(min_value=-20_000, max_value=50_000, allow_nan=False)),
        draw(_MONEY),
    )


def _has_investment_income(facts) -> bool:
    return any(value != 0 for value in facts.values())


# Dependents under 19 make the head of household regardless of income, so no
# filer input may depend on what the dependents received.
_DEPENDENTS = st.lists(
    st.tuples(st.integers(min_value=0, max_value=18), _investment_facts()),
    min_size=1,
    max_size=3,
).filter(lambda deps: any(_has_investment_income(facts) for _, facts in deps))


@PROPERTY_SETTINGS
@given(
    head=_investment_facts(),
    spouse=st.one_of(st.none(), _investment_facts()),
    dependents=_DEPENDENTS,
)
def test_a_dependents_investment_income_never_moves_a_tax_unit_input(
    head, spouse, dependents
) -> None:
    with_income = _household(head, spouse, dependents)
    without = _household(
        head, spouse, [(age, _investment(0, 0, 0, 0, 0)) for age, _ in dependents]
    )

    assert _tax_unit_inputs(with_income) == _tax_unit_inputs(without)


@PROPERTY_SETTINGS
@given(
    head=_investment_facts(),
    spouse=st.one_of(st.none(), _investment_facts()),
    dependents=_DEPENDENTS,
)
def test_axiom_1h_inputs_match_the_taxsim_and_taxcalc_filer_sums(
    head, spouse, dependents
) -> None:
    """Differential: three projections of one Case, one filer base."""
    case = _household(head, spouse, dependents)
    filers = [head] + ([spouse] if spouse is not None else [])

    def filer_sum(concept):
        return sum(facts[concept] for facts in filers)

    inputs = _tax_unit_inputs(case)
    taxsim = taxsim_input_for_case(case, taxsimid=1)
    taxcalc = taxcalc_input_for_case(case, record_id=1)

    qualified = filer_sum(Concepts.QUALIFIED_DIVIDEND_INCOME)
    short_term = filer_sum(Concepts.SHORT_TERM_CAPITAL_GAINS)
    long_term = filer_sum(Concepts.LONG_TERM_CAPITAL_GAINS)
    for name, value in {
        f"{INPUTS_1H}qualified_dividend_income": qualified,
        f"{INPUTS_1H}short_term_capital_gains": short_term,
        f"{INPUTS_1H}long_term_capital_gains": long_term,
        f"{INPUTS_1411}dividend_income": filer_sum(Concepts.DIVIDEND_INCOME),
        f"{INPUTS_1411}taxable_interest_income": filer_sum(Concepts.INTEREST_INCOME),
    }.items():
        assert inputs[name] == pytest.approx(value), name
    assert taxsim["dividends"] == pytest.approx(qualified)
    assert taxsim["stcg"] == pytest.approx(short_term)
    assert taxsim["ltcg"] == pytest.approx(long_term)
    assert taxcalc["e00650"] == pytest.approx(qualified)
    assert taxcalc["p22250"] == pytest.approx(short_term)
    assert taxcalc["p23250"] == pytest.approx(long_term)


def test_engine_taxes_the_filers_ordinary_income_at_ordinary_rates() -> None:
    from test_axiom_tax_exempt_interest_engine import _pinned_engine

    binary, roots = _pinned_engine()
    case = Case(
        case_id="1h-engine",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 40, **{
                Concepts.YEARLY_EARNED_INCOME: 60_000,
            }),
            _person("person-2", "Child", 10, **_investment(10_000, 10_000, 0, 0, 0)),
        ),
    )
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            ("us:tax/federal-income-tax#tax_before_credits",),
            axiom_engine_binary=binary,
        )
        projected = attach_axiom_tax_itemization_choice_to_case(
            attach_axiom_tax_inputs_to_case(case)
        )
        [result] = runner.run_cases([projected], list(TAX_BEFORE_CREDITS))

    assert not result.errors, result.errors
    assert sum(result.values[target] for target in TAX_BEFORE_CREDITS) == (
        pytest.approx(3_948, abs=0.01)
    )
