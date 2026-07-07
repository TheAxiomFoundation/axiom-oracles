"""Ghana composed disposable-income oracle suite (GHAMOD ``ils_dispy``).

``gh-dispy`` compares the rulespec-gh composed single-employee pipeline —
``pilot_worker_disposable_income`` (Act 766 s.3(1) employee SSNIT
contribution, s.112(2) deduction of that contribution from the income-tax
base, Act 1111 First Schedule bands, disposable income = gross + benefits
- tax - contribution) — against GHAMOD ``ils_dispy``, the model's
disposable-income identity (``ils_origy + ils_ben - ils_tax -
ils_sicee``, decomposition probed live at 60,000 gross).

GHAMOD taxes GROSS employment income (probed: ``il_tintb3 = yem``),
omitting the s.112(2) SSNIT deduction, so the two engines diverge
wherever any band above nil is reached: at 60,000 gross GHAMOD returns
tax 10,182 / dispy 46,518 where the statutory chain gives 9,357 / 47,343
(``ghamod-tin-taxes-gross-employment-income-omitting-s112-deduction``,
finding #13). The live cases therefore sit in the shared-nil zone —
gross at or below the 5,880 first-band bound, where both engines charge
no tax and disposable income is exactly 94.5% of gross — exercising the
composed origy - sicee identity end to end; the taxed-zone divergence is
dispositioned with the probed values in ghamod_issues.json.

License discipline as in ``gh_income_tax``: expected values are values
GHAMOD itself produced; no bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    GH_METADATA,
    GH_PERIOD,
    _gh_formal_earner,
)

PIPELINE_MODULE = "gh:statutes/composed/pilot-worker-disposable-income-pipeline"

# Post-uprating annual gross incomes inside the shared-nil zone: GHAMOD
# taxes gross (nil at or below 5,880) and the statutory chain taxes gross
# less the 5.5% contribution (nil below 6,222.22), so both charge zero
# tax and dispy = 0.945 x gross on each case (5,000 -> 4,725.00 and the
# 5,880 first-band bound -> 5,556.60).
_DISPY_INCOME_GRID = (
    ("5000-nil-zone", 5_000.0),
    ("5880-nil-band-bound", 5_880.0),
)


def _pipeline_input(name: str) -> str:
    return f"{PIPELINE_MODULE}#input.{name}"


def gh_dispy_cases() -> list[Case]:
    """Single formal-sector employee disposable-income cases for ils_dispy."""
    return [
        _dispy_case(f"gh-dispy-{label}", income)
        for label, income in _DISPY_INCOME_GRID
    ]


def _dispy_case(case_id: str, annual_income: float) -> Case:
    qualifying_income = _pipeline_input("qualifying_employment_income")
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-formal-employee-disposable-income",
            "yearly_earned_income": annual_income,
            # Placeholder; the post-uprating euromod yem overwrites it via
            # the bridge so both engines price the identical gross base.
            "axiom_inputs": {
                qualifying_income: annual_income,
                _pipeline_input("personal_reliefs_claimed"): 0.0,
                _pipeline_input("benefits_received"): 0.0,
            },
            "euromod_inputs": [_gh_formal_earner(101, annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [qualifying_income]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.GH_PILOT_DISPOSABLE_INCOME,),
    )
