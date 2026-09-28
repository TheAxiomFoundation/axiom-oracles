"""Uganda composed disposable-income oracle suite (UGAMOD ``ils_dispy``).

``ug-dispy`` compares the rulespec-ug composed single-employee pipeline —
``pilot_worker_disposable_income`` (Act 4 of 2012 Third Schedule resident
income tax on chargeable income, Cap. 230 s.11 employee 5% share on total
wages, disposable income = gross + benefits - tax - employee share) —
against UGAMOD ``ils_dispy``, the model's disposable-income identity.

Unlike Ghana (finding #13: GHAMOD taxes gross, omitting the s.112(2)
SSNIT deduction, so gh-dispy live cases sit in the shared-nil zone), the
Ugandan Income Tax Act contains no employee NSSF deduction and UGAMOD
agrees (probed: ``ttb_s = yem``), so the two engines share the identical
tax base at every income. The live cases therefore run the FULL PAYE
grid — every band boundary and interior point including the
additional-rate region — probed live exact to within UGAMOD's monthly
sub-shilling rounding (worst 0.4 UGX/yr at 150m).

License discipline as in ``ug_income_tax``: the bundle is referenced by
path only; expected values are values UGAMOD itself produced; no bundle
content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .ug_income_tax import (
    RATE_MODULE,
    UG_METADATA,
    UG_PERIOD,
    _RATE_INCOME_GRID,
    _ug_formal_earner,
)

PIPELINE_MODULE = "ug:statutes/composed/pilot-worker-disposable-income-pipeline"
NSSF_MODULE = (
    "ug:statutes/cap-230/national-social-security-fund-act/"
    "section-10-payment-of-standard-contribution-by-employers"
)

# The imported rules carry their own inputs: the Third Schedule tax reads
# the rate module's chargeable_income and the Cap. 230 employee share
# reads the NSSF module's total_wages; benefits_received is the composed
# module's own input. For the plain formal employee chargeable income
# equals gross employment income (probed: ttb_s = yem), so the bridge
# feeds the engine's post-uprating yem to both imported inputs.
_CHARGEABLE_INCOME = f"{RATE_MODULE}#input.chargeable_income"
_TOTAL_WAGES = f"{NSSF_MODULE}#input.total_wages"
_BENEFITS_RECEIVED = f"{PIPELINE_MODULE}#input.benefits_received"


def ug_dispy_cases() -> list[Case]:
    """Single formal-sector employee disposable-income cases for ils_dispy."""
    return [
        _dispy_case(f"ug-dispy-{label}", income)
        for label, income in _RATE_INCOME_GRID
    ]


def _dispy_case(case_id: str, annual_income: float) -> Case:
    return Case(
        case_id=case_id,
        period=UG_PERIOD,
        metadata={
            **UG_METADATA,
            "scenario": "single-formal-employee-disposable-income",
            "yearly_earned_income": annual_income,
            # Placeholders; the post-uprating euromod yem overwrites both
            # imported inputs via the bridge so the engines price the
            # identical gross base.
            "axiom_inputs": {
                _CHARGEABLE_INCOME: annual_income,
                _TOTAL_WAGES: annual_income,
                _BENEFITS_RECEIVED: 0.0,
            },
            "euromod_inputs": [_ug_formal_earner(101, annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [_CHARGEABLE_INCOME, _TOTAL_WAGES]
            },
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
        outputs=(Concepts.UG_PILOT_DISPOSABLE_INCOME,),
    )
