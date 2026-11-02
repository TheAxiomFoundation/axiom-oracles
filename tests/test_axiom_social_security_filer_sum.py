"""Only the filers' Social Security enters their section 86 base (#623).

Ground truth, verbatim:

- 26 USC 86(a)(1): "gross income for the taxable year of any taxpayer
  described in subsection (b) ... includes social security benefits in an
  amount equal to the lesser of" half the benefits or half the excess.
- 26 USC 86(d)(1): "the term 'social security benefit' means any amount
  received by the taxpayer by reason of entitlement to-- (A) a monthly
  benefit under title II of the Social Security Act".

A dependent's benefits are paid by reason of the dependent's own entitlement,
so they are the dependent's, not the filers'. The Case projection summed every
person in the tax unit into ``title_II_monthly_benefits_received_during_taxable_year``.
The TAXSIM (``gssi``) and Tax-Calculator (``e02400``) projections already sum
the head and spouse only.

Worked example (ecps-tax-unit-58696's shape): joint filers with 17,492.96 of
wages and an 18-year-old child receiving 65,028.39. Counting the child's
benefits, 0.5 x 65,028.39 + 17,492.96 = 50,007.16 exceeds the 44,000 joint
adjusted base amount, so 0.85 x 6,007.16 + 6,000 = 11,106.08 became taxable.
With the filers' own benefits (none), nothing is taxable and AGI is 17,492.96.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.adapters.taxcalc.projection import taxcalc_input_for_case
from axiom_oracles.adapters.taxsim.projection import taxsim_input_for_case
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)
TITLE_II = (
    "us:statutes/26/86#input.title_II_monthly_benefits_received_during_taxable_year"
)
AGI = "adjusted_gross_income"
_MONEY = st.floats(min_value=0, max_value=120_000, allow_nan=False, allow_infinity=False)


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


def _joint_filers_with_child_beneficiary():
    return Case(
        case_id="ss-58696-shape",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 50, **{
                Concepts.YEARLY_EARNED_INCOME: 17_492.96,
            }),
            _person("person-2", "Spouse", 48),
            _person("person-3", "Child", 18, **{
                Concepts.SOCIAL_SECURITY_BENEFITS: 65_028.39,
            }),
        ),
    )


def test_child_beneficiary_benefits_stay_off_the_filers_base() -> None:
    assert _tax_unit_inputs(_joint_filers_with_child_beneficiary())[TITLE_II] == 0


def test_disabled_adult_dependent_benefits_stay_off_the_filers_base() -> None:
    # ecps-tax-unit-59151's shape: filers with their own benefits and a
    # disabled 37-year-old dependent receiving 23,091.88.
    case = Case(
        case_id="ss-59151-shape",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 70, **{
                Concepts.SOCIAL_SECURITY_BENEFITS: 30_000,
            }),
            _person("person-2", "Spouse", 69, **{
                Concepts.SOCIAL_SECURITY_BENEFITS: 12_000,
            }),
            _person("person-3", "Dependent", 37, **{
                Concepts.DISABLED: True,
                Concepts.SOCIAL_SECURITY_BENEFITS: 23_091.88,
            }),
        ),
    )

    assert _tax_unit_inputs(case)[TITLE_II] == 42_000


def _household(head_ss, spouse_ss, dependent_ss):
    people = [
        _person("head", "HeadOfHousehold", 67, **{
            Concepts.YEARLY_EARNED_INCOME: 20_000,
            Concepts.SOCIAL_SECURITY_BENEFITS: head_ss,
        })
    ]
    if spouse_ss is not None:
        people.append(
            _person("spouse", "Spouse", 66, **{
                Concepts.SOCIAL_SECURITY_BENEFITS: spouse_ss,
            })
        )
    for index, (age, benefits) in enumerate(dependent_ss):
        people.append(
            _person(f"child-{index}", "Child", age, **{
                Concepts.SOCIAL_SECURITY_BENEFITS: benefits,
            })
        )
    # TAXSIM's projection needs a state; Colorado matches the CO lanes.
    return Case(
        case_id="ss-property",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
        entities=tuple(people),
    )


_DEPENDENTS = st.lists(
    st.tuples(st.integers(min_value=0, max_value=40), _MONEY), min_size=1, max_size=3
)


@PROPERTY_SETTINGS
@given(
    head_ss=_MONEY,
    spouse_ss=st.one_of(st.none(), _MONEY),
    dependents=_DEPENDENTS.filter(lambda deps: any(ss > 0 for _, ss in deps)),
)
def test_a_dependents_benefits_never_move_a_tax_unit_input(
    head_ss, spouse_ss, dependents
) -> None:
    with_benefits = _household(head_ss, spouse_ss, dependents)
    without = _household(head_ss, spouse_ss, [(age, 0) for age, _ in dependents])

    assert _tax_unit_inputs(with_benefits) == _tax_unit_inputs(without)


@PROPERTY_SETTINGS
@given(
    head_ss=_MONEY,
    spouse_ss=st.one_of(st.none(), _MONEY),
    dependents=_DEPENDENTS.filter(lambda deps: any(ss > 0 for _, ss in deps)),
)
def test_axiom_benefits_match_the_taxsim_and_taxcalc_filer_sums(
    head_ss, spouse_ss, dependents
) -> None:
    """Differential: three projections of one Case, one benefit total."""
    case = _household(head_ss, spouse_ss, dependents)
    expected = head_ss + (spouse_ss or 0)

    assert _tax_unit_inputs(case)[TITLE_II] == pytest.approx(expected)
    assert taxsim_input_for_case(case, taxsimid=1)["gssi"] == pytest.approx(expected)
    assert taxcalc_input_for_case(case, record_id=1)["e02400"] == pytest.approx(
        expected
    )


def test_engine_keeps_a_childs_benefits_out_of_the_filers_agi() -> None:
    from test_axiom_tax_exempt_interest_engine import _pinned_engine

    binary, roots = _pinned_engine()
    case = _joint_filers_with_child_beneficiary()
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            ("us:tax/federal-income-tax#liability",),
            axiom_engine_binary=binary,
        )
        [result] = runner.run_cases([attach_axiom_tax_inputs_to_case(case)], [AGI])

    assert not result.errors, result.errors
    assert result.values[AGI] == pytest.approx(17_492.96, abs=0.01)
