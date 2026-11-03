"""A self-employment loss reduces section 32 earned income (#622).

Ground truth, verbatim, 26 USC 32(c)(2)(A): "The term 'earned income' means--
(i) wages, salaries, tips, and other employee compensation, but only if such
amounts are includible in gross income for the taxable year, plus (ii) the
amount of the taxpayer's net earnings from self-employment for the taxable
year (within the meaning of section 1402(a)), but such net earnings shall be
determined with regard to the deduction allowed to the taxpayer by section
164(f)."

Net earnings under 1402(a) are gross income less deductions, so a loss is
negative, and nothing in (ii) floors it. The 2025 Form 1040 EIC Worksheet B
takes Schedule SE, Part I, line 3 less the deductible part of SE tax (line 13)
as line 1e, including a joint filer's spouse's amounts, and line 4b combines
it with wages: "If line 4b is zero or less, ... You can't take the credit."
The projection floored the filers' combined self-employment at zero before
the 164(f) adjustment, so a loss never netted against wages.

The 164(f) deduction is one-half of each individual's own SE tax, so it is
taken per filer: a spouse's loss does not reduce the other spouse's SE tax.
For a positive amount the projection keeps its existing factor,
1 - 0.0765 x 0.9235 (one-half of 15.3% of 92.35% of profit); a loss carries
no SE tax and enters unchanged.

Worked examples (Rev. Proc. 2025-32 section 4.06(1) amounts, single, one
qualifying child: 4,427 maximum, 15.98% phase-out above 23,890; no child: 664
maximum, 7.65% phase-out above 10,860):

- wages 47,269.90, Schedule C -973.98: earned income and AGI are 46,295.92,
  so the credit is 4,427 - 0.1598 x 22,405.92 = 846.53 (690.89 un-netted);
- wages 14,204.28, Schedule C -425,168.66: earned income is negative, so no
  credit (4,427 un-netted);
- childless, wages 16,011.53, Schedule C -1,122.78: 664 - 0.0765 x
  (14,888.75 - 10,860) = 355.80 (269.91 un-netted).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)
SE_EARNED = (
    "us:tax/federal-income-tax#input."
    "net_earnings_from_self_employment_after_self_employment_tax_deduction"
)
EITC = "us:statutes/26/32#eitc"
# One-half of the 15.3% SECA rate on 92.35% of profit, the 164(f) deduction.
POSITIVE_FACTOR = 1 - 0.5 * (0.124 + 0.029) * (1 - 0.5 * (0.124 + 0.029))


def _se_earned_income(self_employment: float) -> float:
    """32(c)(2)(A)(ii) for one individual: a loss carries no SE tax."""
    if self_employment > 0:
        return self_employment * POSITIVE_FACTOR
    return self_employment


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


def _se_input(case: Case) -> float:
    projected = attach_axiom_tax_inputs_to_case(case)
    [value] = [
        record["value"]
        for record in projected.metadata["axiom_input_records"]
        if record["entity_id"] == "tax_unit" and record["name"] == SE_EARNED
    ]
    return value


def _worker(case_id, wages, self_employment, *, child_age=None):
    people = [
        _person("person-1", "HeadOfHousehold", 40, **{
            Concepts.YEARLY_EARNED_INCOME: wages,
            Concepts.SELF_EMPLOYMENT_INCOME: self_employment,
        })
    ]
    if child_age is not None:
        people.append(_person("person-2", "Child", child_age))
    return Case(case_id=case_id, period="2026", entities=tuple(people))


def test_a_wage_earners_se_loss_reaches_section_32() -> None:
    assert _se_input(_worker("loss", 47_269.90, -973.98, child_age=5)) == (
        pytest.approx(-973.98)
    )
    assert _se_input(_worker("big-loss", 14_204.28, -425_168.66, child_age=5)) == (
        pytest.approx(-425_168.66)
    )


def test_each_spouse_takes_their_own_164_f_deduction() -> None:
    """Joint: head profit 10,000, spouse loss 10,000. The head's SE tax still
    yields a 706.48 deduction, so the combined amount is -706.48, not zero."""
    case = Case(
        case_id="mixed-joint",
        period="2026",
        entities=(
            _person("person-1", "HeadOfHousehold", 40, **{
                Concepts.SELF_EMPLOYMENT_INCOME: 10_000,
            }),
            _person("person-2", "Spouse", 39, **{
                Concepts.SELF_EMPLOYMENT_INCOME: -10_000,
            }),
        ),
    )

    assert _se_input(case) == pytest.approx(10_000 * POSITIVE_FACTOR - 10_000)
    assert _se_input(case) == pytest.approx(-706.4775)


_SE = st.floats(min_value=-500_000, max_value=500_000, allow_nan=False)


@PROPERTY_SETTINGS
@given(
    head_se=_SE,
    spouse_se=st.one_of(st.none(), _SE),
    dependent_se=_SE,
)
def test_section_32_self_employment_is_the_filers_signed_sum(
    head_se, spouse_se, dependent_se
) -> None:
    people = [
        _person("head", "HeadOfHousehold", 40, **{
            Concepts.YEARLY_EARNED_INCOME: 20_000,
            Concepts.SELF_EMPLOYMENT_INCOME: head_se,
        })
    ]
    if spouse_se is not None:
        people.append(
            _person("spouse", "Spouse", 39, **{
                Concepts.SELF_EMPLOYMENT_INCOME: spouse_se,
            })
        )
    # A dependent's business is on the dependent's own return.
    people.append(
        _person("child", "Child", 17, **{
            Concepts.SELF_EMPLOYMENT_INCOME: dependent_se,
        })
    )
    case = Case(case_id="se-property", period="2026", entities=tuple(people))
    expected = _se_earned_income(head_se) + (
        _se_earned_income(spouse_se) if spouse_se is not None else 0
    )

    assert _se_input(case) == pytest.approx(expected, abs=1e-6)


@pytest.fixture(scope="module")
def engine_eitc() -> dict[str, float]:
    from test_axiom_tax_exempt_interest_engine import _pinned_engine

    binary, roots = _pinned_engine()
    cases = [
        _worker("one-child-phase-out", 47_269.90, -973.98, child_age=5),
        _worker("one-child-net-loss", 14_204.28, -425_168.66, child_age=5),
        _worker("childless-phase-out", 16_011.53, -1_122.78),
    ]
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            ("us:tax/federal-income-tax#eitc",),
            axiom_engine_binary=binary,
        )
        results = runner.run_cases(
            [attach_axiom_tax_inputs_to_case(case) for case in cases], [EITC]
        )
    values = {}
    for result in results:
        assert not result.errors, result.errors
        values[result.household_id] = result.values[EITC]
    return values


@pytest.mark.parametrize(
    ("case_id", "eitc"),
    [
        pytest.param("one-child-phase-out", 846.53, id="phase-out-nets-loss"),
        pytest.param("one-child-net-loss", 0.0, id="negative-earned-income"),
        pytest.param("childless-phase-out", 355.80, id="childless-phase-out"),
    ],
)
def test_engine_eitc_nets_the_loss(engine_eitc, case_id, eitc) -> None:
    assert engine_eitc[case_id] == pytest.approx(eitc, abs=0.01)
