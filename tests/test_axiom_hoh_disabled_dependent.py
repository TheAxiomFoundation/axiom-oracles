"""Head of household for a filer whose dependent is disabled (#625).

Ground truth, verbatim:

- 26 USC 2(b)(1): an unmarried individual who is not a surviving spouse is a
  head of household if they maintain a household that is, for more than half
  the year, the principal place of abode of "(i) a qualifying child of the
  individual (as defined in section 152(c), determined without regard to
  section 152(e))".
- 26 USC 152(c)(3)(B), "Special rule for disabled": "In the case of an
  individual who is permanently and totally disabled (as defined in section
  22(e)(3)) at any time during such calendar year, the requirements of
  subparagraph (A) shall be treated as met with respect to such individual."
  Subparagraph (A) is the whole age test, including "younger than the
  taxpayer".
- 26 USC 152(c)(1) lists relationship, abode, age, support and joint-return
  tests. It has no gross-income test; that is 152(d)(1)(B), for qualifying
  relatives only.

So a permanently and totally disabled child qualifies the filer at any age and
any income. The Case records a ``disabled`` fact but neither the relationship
nor who provides support. The projection reads ``disabled`` as 152(c)(3)(B)'s
"permanently and totally disabled" and, as it already does for dependents under
19, treats the unrecorded relationship, abode and support tests as met.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    _HOH_YOUNG_ADULT_DEPENDENT_AGE_LIMIT,
    _HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)
FILING_STATUS = "us:tax/federal-income-tax#input.filing_status"
SINGLE, JOINT, HEAD_OF_HOUSEHOLD = 0, 1, 3
STANDARD_DEDUCTION = (
    "us:policies/irs/rev-proc-2025-32/standard-deduction#standard_deduction"
)


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


def _filing_status(case: Case) -> int:
    projected = attach_axiom_tax_inputs_to_case(case)
    [status] = [
        record["value"]
        for record in projected.metadata["axiom_input_records"]
        if record["entity_id"] == "tax_unit" and record["name"] == FILING_STATUS
    ]
    return status


def _filer_with_disabled_adult():
    # ecps-tax-unit-136208's shape: a 64-year-old filer and a 29-year-old
    # dependent with disabled and blind facts.
    return Case(
        case_id="hoh-disabled-29",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 64, **{
                Concepts.YEARLY_EARNED_INCOME: 30_000,
            }),
            _person("person-2", "Dependent", 29, **{
                Concepts.DISABLED: True,
                Concepts.BLIND: True,
            }),
        ),
    )


def test_disabled_adult_dependent_makes_filer_head_of_household() -> None:
    assert _filing_status(_filer_with_disabled_adult()) == HEAD_OF_HOUSEHOLD


def test_disabled_dependent_has_no_gross_income_test() -> None:
    """152(c)(1) has no gross-income test, so a disabled 34-year-old earning
    26,876 still qualifies the filer (the projection used to file single)."""
    case = Case(
        case_id="hoh-disabled-34-with-income",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 66),
            _person("person-2", "Dependent", 34, **{
                Concepts.DISABLED: True,
                Concepts.YEARLY_EARNED_INCOME: 21_866,
                Concepts.SELF_EMPLOYMENT_INCOME: 5_010,
            }),
        ),
    )

    assert _filing_status(case) == HEAD_OF_HOUSEHOLD


_DEPENDENT = st.tuples(
    st.integers(min_value=0, max_value=90),
    st.floats(min_value=0, max_value=200_000, allow_nan=False, allow_infinity=False),
    st.booleans(),
)


def _household(has_spouse, dependents):
    people = [
        _person("head", "HeadOfHousehold", 70, **{
            Concepts.YEARLY_EARNED_INCOME: 25_000,
        })
    ]
    if has_spouse:
        people.append(_person("spouse", "Spouse", 68))
    for index, (age, income, disabled) in enumerate(dependents):
        people.append(
            _person(f"dependent-{index}", "Dependent", age, **{
                Concepts.YEARLY_EARNED_INCOME: income,
                Concepts.DISABLED: disabled,
            })
        )
    return Case(case_id="hoh-property", period="2026", entities=tuple(people))


@PROPERTY_SETTINGS
@given(
    has_spouse=st.booleans(),
    dependents=st.lists(_DEPENDENT, min_size=1, max_size=3).filter(
        lambda dependents: any(disabled for _, _, disabled in dependents)
    ),
)
def test_any_disabled_dependent_qualifies_an_unmarried_filer(
    has_spouse, dependents
) -> None:
    expected = JOINT if has_spouse else HEAD_OF_HOUSEHOLD
    assert _filing_status(_household(has_spouse, dependents)) == expected


@PROPERTY_SETTINGS
@given(
    has_spouse=st.booleans(),
    dependents=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=90),
            st.floats(
                min_value=0, max_value=200_000, allow_nan=False, allow_infinity=False
            ),
            st.just(False),
        ),
        max_size=3,
    ),
)
def test_dependents_not_marked_disabled_keep_the_age_and_income_test(
    has_spouse, dependents
) -> None:
    """The disabled rule changes nothing for a dependent the Case does not mark
    disabled: under 19, or under 24 below the 152(d)(1)(B) amount."""
    qualifies = any(
        age < 19
        or (
            age < _HOH_YOUNG_ADULT_DEPENDENT_AGE_LIMIT
            and income < _HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT
        )
        for age, income, _ in dependents
    )
    expected = JOINT if has_spouse else (HEAD_OF_HOUSEHOLD if qualifies else SINGLE)

    assert _filing_status(_household(has_spouse, dependents)) == expected


def test_engine_gives_the_head_of_household_standard_deduction() -> None:
    """Rev. Proc. 2025-32 section 4.14(1): 24,150 for heads of households,
    16,100 for unmarried individuals."""
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
            ("us:tax/federal-income-tax#standard_deduction",),
            axiom_engine_binary=binary,
        )
        [result] = runner.run_cases(
            [attach_axiom_tax_inputs_to_case(_filer_with_disabled_adult())],
            [STANDARD_DEDUCTION],
        )

    assert not result.errors, result.errors
    assert result.values[STANDARD_DEDUCTION] == pytest.approx(24_150, abs=0.01)
