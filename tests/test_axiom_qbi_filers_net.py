"""Qualified business income nets the filers' businesses only (#618).

Ground truth, verbatim, 26 USC 199A(c):

- (1): "The term 'qualified business income' means, for any taxable year, the
  net amount of qualified items of income, gain, deduction, and loss with
  respect to any qualified trade or business of the taxpayer."
- (2): "If the net amount of qualified income, gain, deduction, and loss with
  respect to qualified trades or businesses of the taxpayer for any taxable
  year is less than zero, such amount shall be treated as a loss from a
  qualified trade or business in the succeeding taxable year."
- (3)(A)(ii): qualified items are items "included or allowed in determining
  taxable income for the taxable year".

A joint return is one taxpayer, so the head's and spouse's businesses net
before any floor, and a net loss carries forward instead of offsetting
nothing this year. A dependent's business is on the dependent's own return,
so it is not in the filers' taxable income and not their QBI. The bridge
floored each person at zero and summed every tax-unit member, dependents
included, as the pinned PolicyEngine does; PolicyEngine main now nets the
filers.

Per person the bridge's QBI items are Schedule C income plus Part I rents less
the 164(f) deduction attributable to the Schedule C income. The reference
below computes that deduction from the statute: 92.35% of profit is net
earnings (1402(a)(12)), none below 400 (1402(b)(2)); 12.4% on net earnings up
to the 184,500 base less wages (1401(a), 1402(b)(1)), 2.9% on all of it
(1401(b)(1)); 164(f) deducts half.

The issue's households, with Part I rents standing in for farm rent:

- joint: head wages 100,000 and rents +20,000, spouse rents -20,000: QBI 0
  (the per-person floor gave 20,000, a QBID of 4,000);
- joint: head wages 60,000 and rents +5,000, spouse rents -2,000: QBI 3,000,
  QBID 600, Tax-Calculator's figure (the floor gave 5,000, a QBID of 1,000);
- head of household, wages 60,000, with a 10-year-old child whose Schedule C
  shows 20,000: QBI 0 (the dependent's 20,000 less its 1,412.96 deduction
  was counted).
"""

from __future__ import annotations

import pytest
from bridge_formula import STATUTORY_SECA_VALUES, reader_for_case
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
    attach_axiom_tax_itemization_choice_to_case,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)
QBI = "us:tax/oracle-bridge#qualified_business_income"
QBID = "us:tax/oracle-bridge#qualified_business_income_deduction"


def _seca_deduction(self_employment: float, wages: float) -> float:
    """26 USC 164(f): half the 1401(a) and (b)(1) taxes on one person."""
    net_earnings = max(0.0, self_employment) * (1 - 0.5 * (0.124 + 0.029))
    if net_earnings < 400:
        return 0.0
    oasdi = 0.124 * min(net_earnings, max(0.0, 184_500 - max(0.0, wages)))
    return 0.5 * (oasdi + 0.029 * net_earnings)


def _qbi_items(person: dict) -> float:
    return (
        person.get("se", 0.0)
        + person.get("rent", 0.0)
        - _seca_deduction(person.get("se", 0.0), person.get("wages", 0.0))
    )


def _person(entity_id, relation, age, *, wages=0.0, se=0.0, rent=0.0):
    return Entity(
        entity_id,
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: relation,
            Concepts.PERSON_AGE: age,
            Concepts.YEARLY_EARNED_INCOME: wages,
            Concepts.SELF_EMPLOYMENT_INCOME: se,
            Concepts.RENTAL_INCOME: rent,
        },
    )


def _projected(case_id, *people):
    return attach_axiom_tax_inputs_to_case(
        Case(case_id=case_id, period="2026", entities=tuple(people))
    )


def _qbi(projected) -> float:
    reader = reader_for_case(
        projected, US_TAX_ORACLE_PROGRAM_RULES, values=STATUTORY_SECA_VALUES
    )
    return reader.value("qualified_business_income")


def _qbid(projected, taxable_income_less_qbid) -> float:
    # The 199A(a)(2) cap reads taxable income through the imported deduction
    # modules; pin it so only the bridge's 199A arithmetic is under test.
    reader = reader_for_case(
        projected,
        US_TAX_ORACLE_PROGRAM_RULES,
        values={
            **STATUTORY_SECA_VALUES,
            "taxable_income_less_qbid": taxable_income_less_qbid,
        },
    )
    return reader.value("qualified_business_income_deduction")


def _offsetting_spouses():
    return _projected(
        "qbi-offset",
        _person("person-1", "HeadOfHousehold", 45, wages=100_000, rent=20_000),
        _person("person-2", "Spouse", 44, rent=-20_000),
    )


def _partly_offsetting_spouses():
    return _projected(
        "qbi-partial",
        _person("person-1", "HeadOfHousehold", 45, wages=60_000, rent=5_000),
        _person("person-2", "Spouse", 44, rent=-2_000),
    )


def _dependent_business():
    return _projected(
        "qbi-dependent",
        _person("person-1", "HeadOfHousehold", 40, wages=60_000),
        _person("person-2", "Child", 10, se=20_000),
    )


def test_spouses_businesses_net_before_the_floor() -> None:
    assert _qbi(_offsetting_spouses()) == pytest.approx(0)
    assert _qbid(_offsetting_spouses(), 67_800) == pytest.approx(0)


def test_partly_offsetting_spouses_get_20_percent_of_the_net() -> None:
    assert _qbi(_partly_offsetting_spouses()) == pytest.approx(3_000)
    assert _qbid(_partly_offsetting_spouses(), 30_800) == pytest.approx(600)


def test_a_dependents_business_is_not_the_filers_qbi() -> None:
    assert _qbi(_dependent_business()) == pytest.approx(0)


_AMOUNT = st.floats(min_value=-200_000, max_value=200_000, allow_nan=False)
_FILER = st.fixed_dictionaries(
    {
        "wages": st.floats(min_value=0, max_value=250_000, allow_nan=False),
        "se": _AMOUNT,
        "rent": _AMOUNT,
    }
)
_DEPENDENT = st.fixed_dictionaries(
    {
        "age": st.integers(min_value=0, max_value=30),
        "se": _AMOUNT,
        "rent": _AMOUNT,
    }
)


@PROPERTY_SETTINGS
@given(
    head=_FILER,
    spouse=st.one_of(st.none(), _FILER),
    dependents=st.lists(_DEPENDENT, max_size=2),
)
def test_qbi_is_the_floored_net_of_the_filers_items(head, spouse, dependents) -> None:
    people = [_person("head", "HeadOfHousehold", 50, **head)]
    filers = [head]
    if spouse is not None:
        people.append(_person("spouse", "Spouse", 49, **spouse))
        filers.append(spouse)
    for index, dependent in enumerate(dependents):
        people.append(
            _person(
                f"dependent-{index}",
                "Child",
                dependent["age"],
                se=dependent["se"],
                rent=dependent["rent"],
            )
        )
    expected = max(0.0, sum(_qbi_items(filer) for filer in filers))

    assert _qbi(_projected("qbi-property", *people)) == pytest.approx(
        expected, abs=1e-6
    )


def test_engine_gives_20_percent_of_the_filers_net_qbi() -> None:
    from test_axiom_tax_exempt_interest_engine import _pinned_engine

    binary, roots = _pinned_engine()
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            (Concepts.TAXABLE_INCOME,),
            axiom_engine_binary=binary,
        )
        [result] = runner.run_cases(
            [attach_axiom_tax_itemization_choice_to_case(_partly_offsetting_spouses())],
            [QBI, QBID],
        )

    assert not result.errors, result.errors
    assert result.values[QBI] == pytest.approx(3_000, abs=0.01)
    assert result.values[QBID] == pytest.approx(600, abs=0.01)
