"""The refundable child tax credit counts the CDCC's use of the 26(a) limit (#609).

26 USC 24(d)(1), verbatim: "The aggregate credits allowed to a taxpayer under
subpart C shall be increased by the lesser of-- (A) the credit which would be
allowed under this section without regard to this subsection and the
limitation under section 26(a) or (B) the amount by which the aggregate
amount of credits allowed by this subpart (determined without regard to this
subsection) would increase if the limitation imposed by section 26(a) were
increased by the greater of-- (i) 15 percent of so much of the taxpayer's
earned income ... as exceeds $3,000, or (ii) ..."

"This subpart" is subpart A of part IV, which holds the CDCC (section 21) as
well as the CTC. The bridge's two aggregates
(``aggregate_subpart_c_credits_without_subsection`` and
``..._with_increased_26a_limit``) counted the CTC alone. While the Case-surface
CDCC was always 0 that was exact; once it is not, a CDCC that absorbs the tax
leaves more of the CTC to refund.

Worked example: tax before credits 1,000, CTC 2,200, CDCC 1,000, and a 24(d)
increase of 1,500. The aggregate without the increase is min(3,200, 1,000) =
1,000 and with it min(3,200, 2,500) = 2,500, so (B) is 1,500. Counting the CTC
alone gave min(2,200, 2,500) - min(2,200, 1,000) = 1,200.

Engine example: an unmarried head (wages 30,000) with a 5-year-old and 3,000
of childcare. Head-of-household taxable income is 30,000 - 24,150 = 5,850, so
the tax is 585 (Rev. Proc. 2025-32 sections 4.14(1) and 4.01 Table 2). The
CDCC rate is 50 - 8 = 42% (21(a)(2)(A)), on 3,000: 1,260, limited to 585.
The 24(d) increase is 0.15 x (30,000 - 2,500) = 4,125, so (B) is
min(2,785, 4,710) - min(2,785, 585) = 2,200 (1,615 counting the CTC alone).
"""

from __future__ import annotations

import pytest
from bridge_formula import BridgeReader
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
    attach_axiom_tax_itemization_choice_to_case,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)
TAX_INCREASE = "ctc_refundable_tax_increase"


def _tax_increase(*, ctc, cdcc, tax, increase) -> float:
    reader = BridgeReader(
        US_TAX_ORACLE_PROGRAM_RULES,
        values={
            "ctc_credit_without_subsection_and_26a_limit": ctc,
            "cdcc": cdcc,
            "income_tax_before_credits": tax,
            "ctc_refundable_limitation_increase_amount": increase,
        },
    )
    return reader.value(TAX_INCREASE)


def _section_24_d_1_b(*, ctc, cdcc, tax, increase) -> float:
    """24(d)(1)(B): the rise in the subpart A aggregate from a higher limit."""
    credits = ctc + cdcc
    return min(credits, tax + increase) - min(credits, tax)


def test_a_cdcc_that_absorbs_the_tax_leaves_more_ctc_to_refund() -> None:
    assert _tax_increase(ctc=2_200, cdcc=1_000, tax=1_000, increase=1_500) == (
        pytest.approx(1_500)
    )


_MONEY = st.floats(min_value=0, max_value=20_000, allow_nan=False, allow_infinity=False)


@PROPERTY_SETTINGS
@given(
    ctc=st.floats(min_value=0, max_value=6_600, allow_nan=False),
    cdcc=st.floats(min_value=1, max_value=6_000, allow_nan=False),
    tax=_MONEY,
    increase=_MONEY,
)
@example(ctc=2_200, cdcc=1_000, tax=1_000, increase=1_500)
def test_the_refundable_increase_is_section_24_d_1_b(ctc, cdcc, tax, increase) -> None:
    assert _tax_increase(ctc=ctc, cdcc=cdcc, tax=tax, increase=increase) == (
        pytest.approx(_section_24_d_1_b(ctc=ctc, cdcc=cdcc, tax=tax, increase=increase))
    )


@PROPERTY_SETTINGS
@given(
    ctc=st.floats(min_value=0, max_value=6_600, allow_nan=False),
    tax=_MONEY,
    increase=_MONEY,
)
def test_without_a_cdcc_the_increase_counts_the_ctc_alone(ctc, tax, increase) -> None:
    """Units with no CDCC keep the value the CTC-only aggregate gave."""
    assert _tax_increase(ctc=ctc, cdcc=0, tax=tax, increase=increase) == (
        pytest.approx(min(ctc, tax + increase) - min(ctc, tax))
    )


def test_engine_refunds_the_ctc_the_cdcc_crowds_out() -> None:
    from test_axiom_tax_exempt_interest_engine import _pinned_engine

    binary, roots = _pinned_engine()
    case = Case(
        case_id="ctc-after-cdcc",
        period="2026",
        facts={Concepts.CHILDCARE_EXPENSES: 3_000},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 32,
                    Concepts.YEARLY_EARNED_INCOME: 30_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 5,
                },
            ),
        ),
    )
    outputs = ["us:statutes/26/21#cdcc", f"us:tax/oracle-bridge#{TAX_INCREASE}"]
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            (Concepts.CDCC, Concepts.FEDERAL_INCOME_TAX),
            axiom_engine_binary=binary,
        )
        projected = attach_axiom_tax_itemization_choice_to_case(
            attach_axiom_tax_inputs_to_case(case)
        )
        [result] = runner.run_cases([projected], outputs)

    assert not result.errors, result.errors
    assert result.values["us:statutes/26/21#cdcc"] == pytest.approx(585, abs=0.01)
    assert result.values[f"us:tax/oracle-bridge#{TAX_INCREASE}"] == pytest.approx(
        2_200, abs=0.01
    )
