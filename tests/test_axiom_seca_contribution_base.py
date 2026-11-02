"""Section 1402(b) inputs on the Case surface, so 1401(a) SECA evaluates (#612).

26 USC 1402(b)(1), the self-employment income the 1401(a) tax reaches, is net
earnings from self-employment except "(1) in the case of the tax imposed by
section 1401(a), that part of the net earnings from self-employment which is
in excess of (i) an amount equal to the contribution and benefit base (as
determined under section 230 of the Social Security Act) which is effective
for the calendar year in which such taxable year begins, minus (ii) the amount
of the wages paid to such individual during such taxable years".

The pinned rulespec-us module (us/statutes/26/1402/b.yaml at ca2d424f, line
151, quoted in #612) computes that cap as
``contribution_and_benefit_base_effective_for_calendar_year_in_which_taxable_year_begins
- wages_paid_to_individual_during_taxable_year_for_section_1401_a``. The Case
projection supplied neither name, so the engine answered
``missing input contribution_and_benefit_base_effective_for_calendar_year_in_which_taxable_year_begins``
and ``us:tax/payroll#employee_fica`` lost its 1401(a) component on every unit.

The base is SSA's 2026 amount (90 FR 49047): "The OASDI contribution and
benefit base is $184,500 for remuneration paid in 2026 and self-employment
income earned in tax years beginning in 2026." It is the same constant the
bridge's own ``social_security_wage_base`` reads (#611), so the SECA tax and
its 164(f) deduction use one base.

Worked example (single, age 40, wages 50,000, Schedule C 20,000):

    net earnings from self-employment = 20,000 x (1 - 0.5 x 0.153) = 18,470
    3101(a)    6.2% x 50,000                              = 3,100.00
    3101(b)(1) 1.45% x 50,000                             =   725.00
    1401(a)    12.4% x min(18,470, 184,500 - 50,000)      = 2,290.28
    1401(b)(1) 2.9% x 18,470                              =   535.63

With wages 180,000 the 1401(a) cap binds: 12.4% x (184,500 - 180,000) =
558.00 (744.00 at the old 186,000).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.us_tax_parameters import (
    OASDI_CONTRIBUTION_AND_BENEFIT_BASE_2026,
)

PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)
BASE_INPUT = (
    "us:statutes/26/1402/b#input."
    "contribution_and_benefit_base_effective_for_calendar_year_in_which_taxable_year_begins"
)
WAGES_INPUT = (
    "us:statutes/26/1402/b#input."
    "wages_paid_to_individual_during_taxable_year_for_section_1401_a"
)
EMPLOYEE_FICA_TARGETS = (
    "us:statutes/26/3101/a#oasdi_wage_tax",
    "us:statutes/26/3101/b/1#hospital_insurance_wage_tax",
    "us:statutes/26/1401/a#old_age_survivors_and_disability_insurance_tax",
    "us:statutes/26/1401/b/1#self_employment_income_tax",
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


def _self_employed(wages, self_employment=20_000):
    return Case(
        case_id=f"seca-{wages}",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 40, **{
                Concepts.YEARLY_EARNED_INCOME: wages,
                Concepts.SELF_EMPLOYMENT_INCOME: self_employment,
            }),
        ),
    )


def _tax_unit_inputs(case: Case) -> dict[str, object]:
    projected = attach_axiom_tax_inputs_to_case(case)
    return {
        record["name"]: record["value"]
        for record in projected.metadata["axiom_input_records"]
        if record["entity_id"] == "tax_unit"
    }


@pytest.mark.xfail(strict=True, reason="#612: the projection omits 1402(b) inputs")
def test_projection_supplies_the_1402_b_base_and_wages() -> None:
    inputs = _tax_unit_inputs(_self_employed(50_000))

    assert inputs[BASE_INPUT] == 184_500
    assert inputs[WAGES_INPUT] == 50_000


@pytest.mark.xfail(strict=True, reason="#612: the projection omits 1402(b) inputs")
def test_one_base_for_seca_and_its_deduction() -> None:
    """The 1402(b) base the SECA tax reads is the bridge's own wage base."""
    [wage_base] = [
        rule["versions"][0]["formula"]
        for rule in US_TAX_ORACLE_PROGRAM_RULES
        if rule["name"] == "social_security_wage_base"
    ]
    inputs = _tax_unit_inputs(_self_employed(50_000))

    assert inputs[BASE_INPUT] == OASDI_CONTRIBUTION_AND_BENEFIT_BASE_2026
    assert float(wage_base) == inputs[BASE_INPUT]


@pytest.mark.xfail(strict=True, reason="#612: the projection omits 1402(b) inputs")
@PROPERTY_SETTINGS
@given(
    head_wages=st.floats(min_value=0, max_value=400_000, allow_nan=False),
    spouse_wages=st.one_of(
        st.none(), st.floats(min_value=0, max_value=400_000, allow_nan=False)
    ),
    dependent_wages=st.floats(min_value=0, max_value=100_000, allow_nan=False),
)
def test_1402_b_wages_are_the_filers_wages(
    head_wages, spouse_wages, dependent_wages
) -> None:
    """1402(b)(1)(B) subtracts the wages paid to the individual, so a
    dependent's wages never enter the filers' cap; the input matches the
    filer wages the projection already supplies for 1401(a)."""
    people = [
        _person("head", "HeadOfHousehold", 45, **{
            Concepts.YEARLY_EARNED_INCOME: head_wages,
            Concepts.SELF_EMPLOYMENT_INCOME: 10_000,
        })
    ]
    if spouse_wages is not None:
        people.append(
            _person("spouse", "Spouse", 44, **{
                Concepts.YEARLY_EARNED_INCOME: spouse_wages,
            })
        )
    people.append(
        _person("child", "Child", 16, **{
            Concepts.YEARLY_EARNED_INCOME: dependent_wages,
        })
    )
    inputs = _tax_unit_inputs(
        Case(case_id="seca-wages", period="2026", entities=tuple(people))
    )

    assert inputs[WAGES_INPUT] == head_wages + (spouse_wages or 0)
    assert inputs[WAGES_INPUT] == inputs[
        "us:tax/federal-income-tax#input.wages_paid_to_individual_for_section_1401_a"
    ]
    assert inputs[BASE_INPUT] == OASDI_CONTRIBUTION_AND_BENEFIT_BASE_2026


@pytest.fixture(scope="module")
def engine_fica() -> dict[str, dict]:
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
            ("us:tax/payroll#employee_fica",),
            axiom_engine_binary=binary,
        )
        cases = [
            attach_axiom_tax_inputs_to_case(_self_employed(wages))
            for wages in (50_000, 180_000)
        ]
        results = runner.run_cases(cases, list(EMPLOYEE_FICA_TARGETS))
    values = {}
    for result in results:
        assert not result.errors, result.errors
        values[result.household_id] = result.values
    return values


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        pytest.param(
            "seca-50000", (3_100.00, 725.00, 2_290.28, 535.63), id="below-base"
        ),
        pytest.param(
            "seca-180000", (11_160.00, 2_610.00, 558.00, 535.63), id="cap-binds"
        ),
    ],
)
def test_engine_returns_all_four_employee_fica_components(
    engine_fica, case_id, expected
) -> None:
    """A missing component fails here instead of turning a suite's rows into
    ``missing_left``."""
    values = engine_fica[case_id]
    for target, amount in zip(EMPLOYEE_FICA_TARGETS, expected, strict=True):
        assert target in values, f"{target} missing"
        assert values[target] == pytest.approx(amount, abs=0.01), target
