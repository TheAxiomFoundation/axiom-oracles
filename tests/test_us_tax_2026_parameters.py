"""2026 amounts the tax projections read, against their publications (#611).

Ground truth, verbatim:

- SSA, "Cost-of-Living Increase and Other Determinations for 2026",
  90 FR 49047 (Nov. 3, 2025): "The OASDI contribution and benefit base is
  $184,500 for remuneration paid in 2026 and self-employment income earned in
  tax years beginning in 2026."
- Rev. Proc. 2025-32, section 4.31: "For taxable years beginning in 2026, in
  determining a taxpayer's excess business loss, the amount under
  § 461(l)(3)(A)(ii)(II) is $256,000 ($512,000 for joint returns)."
- Rev. Proc. 2025-32, section 4.23: "For taxable years beginning in 2026, the
  exemption amount referred to in § 152(d)(1)(B) is $5,300."
- 26 USC 152(d)(1)(B): a qualifying relative is an individual "whose gross
  income for the calendar year in which such taxable year begins is less than
  the exemption amount (as defined in section 151(d))".

Both projections file an unmarried head with a dependent aged 19 to 23 as head
of household only when the dependent's gross income is below that amount, so a
dependent with 5,299.99 qualifies and one with 5,300 does not, on the Axiom leg
and the Tax-Calculator leg of the same Case alike.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom import tax_projection
from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.adapters.taxcalc import projection as taxcalc_projection
from axiom_oracles.adapters.taxcalc.projection import taxcalc_input_for_case
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.us_tax_parameters import (
    QUALIFYING_RELATIVE_GROSS_INCOME_LIMIT_2026,
)

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)
FILING_STATUS = "us:tax/federal-income-tax#input.filing_status"
# Axiom filing_status codes and the Tax-Calculator MARS code for the same
# status: single, joint, head of household.
AXIOM_TO_MARS = {0: 1, 1: 2, 3: 4}
SINGLE, HEAD_OF_HOUSEHOLD = 0, 3


def _rule_formula(name: str) -> str:
    [rule] = [rule for rule in US_TAX_ORACLE_PROGRAM_RULES if rule["name"] == name]
    return rule["versions"][0]["formula"]


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
    return Case(case_id="params", period="2026", entities=tuple(people))


def _axiom_filing_status(case: Case) -> int:
    projected = attach_axiom_tax_inputs_to_case(case)
    [status] = [
        record["value"]
        for record in projected.metadata["axiom_input_records"]
        if record["entity_id"] == "tax_unit" and record["name"] == FILING_STATUS
    ]
    return status


def _taxcalc_mars(case: Case) -> int:
    return taxcalc_input_for_case(case, record_id=1)["MARS"]


def _single_parent_with_young_adult(dependent_gross_income):
    return _case(
        _person("person-1", "HeadOfHousehold", 48, **{
            Concepts.YEARLY_EARNED_INCOME: 40_000,
        }),
        _person("person-2", "Child", 20, **{
            Concepts.YEARLY_EARNED_INCOME: dependent_gross_income,
        }),
    )


@pytest.mark.xfail(strict=True, reason="#611: the bridge pins 186,000")
def test_bridge_oasdi_base_is_the_ssa_2026_amount() -> None:
    assert _rule_formula("social_security_wage_base") == "184500"
    assert (
        _rule_formula(
            "contribution_and_benefit_base_under_section_230_of_social_security_act"
        )
        == "184500"
    )


@pytest.mark.xfail(strict=True, reason="#611: the bridge pins 305,000/610,000")
def test_bridge_excess_business_loss_threshold_is_rev_proc_2025_32() -> None:
    assert _rule_formula("business_loss_limit_other_2026") == "256000"
    assert _rule_formula("business_loss_limit_joint_2026") == "512000"


@pytest.mark.xfail(strict=True, reason="#611: the projections pin 5,500 and 5,200")
def test_both_projections_read_one_qualifying_relative_limit() -> None:
    assert QUALIFYING_RELATIVE_GROSS_INCOME_LIMIT_2026 == 5_300
    assert (
        tax_projection._HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT
        == QUALIFYING_RELATIVE_GROSS_INCOME_LIMIT_2026
    )
    assert (
        taxcalc_projection._HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT
        == QUALIFYING_RELATIVE_GROSS_INCOME_LIMIT_2026
    )


@pytest.mark.xfail(strict=True, reason="#611: the Axiom projection pins 5,500")
def test_axiom_projection_applies_the_152_d_1_b_limit() -> None:
    # "less than the exemption amount": 5,299.99 qualifies, 5,300 does not.
    assert _axiom_filing_status(_single_parent_with_young_adult(5_299.99)) == (
        HEAD_OF_HOUSEHOLD
    )
    assert _axiom_filing_status(_single_parent_with_young_adult(5_300)) == SINGLE
    assert _axiom_filing_status(_single_parent_with_young_adult(5_450)) == SINGLE


@pytest.mark.xfail(strict=True, reason="#611: the Tax-Calculator projection pins 5,200")
def test_taxcalc_projection_applies_the_152_d_1_b_limit() -> None:
    assert _taxcalc_mars(_single_parent_with_young_adult(5_250)) == 4
    assert _taxcalc_mars(_single_parent_with_young_adult(5_299.99)) == 4
    assert _taxcalc_mars(_single_parent_with_young_adult(5_300)) == 1


# Incomes cluster around the two stale limits and the published one, so the
# band where the projections used to disagree is always exercised.
_DEPENDENT_INCOME = st.one_of(
    st.integers(min_value=5_100, max_value=5_600),
    st.floats(min_value=0, max_value=60_000, allow_nan=False, allow_infinity=False),
)
_DEPENDENT = st.tuples(
    st.integers(min_value=0, max_value=40),
    _DEPENDENT_INCOME,
    st.sampled_from(["Child", "Dependent"]),
)


@pytest.mark.xfail(strict=True, reason="#611: 5,500 and 5,200 disagree")
@PROPERTY_SETTINGS
@given(
    has_spouse=st.booleans(),
    dependents=st.lists(_DEPENDENT, min_size=0, max_size=3),
)
@example(has_spouse=False, dependents=[(20, 5_250, "Child")])
@example(has_spouse=False, dependents=[(22, 5_400, "Dependent")])
def test_axiom_and_taxcalc_projections_file_the_same_status(
    has_spouse, dependents
) -> None:
    """Differential: the two projections of one Case agree on filing status.

    Dependents here carry no disabled fact, so the property covers the age and
    gross-income test the two projections share.
    """
    people = [
        _person("head", "HeadOfHousehold", 45, **{
            Concepts.YEARLY_EARNED_INCOME: 30_000,
        })
    ]
    if has_spouse:
        people.append(_person("spouse", "Spouse", 44))
    for index, (age, income, relation) in enumerate(dependents):
        people.append(
            _person(f"dependent-{index}", relation, age, **{
                Concepts.YEARLY_EARNED_INCOME: income,
            })
        )
    case = _case(*people)

    assert AXIOM_TO_MARS[_axiom_filing_status(case)] == _taxcalc_mars(case)
