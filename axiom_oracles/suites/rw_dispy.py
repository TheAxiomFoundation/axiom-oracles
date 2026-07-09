"""Rwanda composed disposable-income oracle suite (RWAMOD ``ils_dispy``).

``rw-dispy`` compares the rulespec-rw composed monthly pipeline -
``pilot_worker_disposable_income`` (the Law 027/2022 Article 56
Table 2 employment income tax on gross monthly income, less the
Presidential Order 086/01 employee pension half, the Law 003/2016
employee maternity contribution and the PM Order 105/03 CBHI employee
levy of 0.5 percent on the composed net salary) - against RWAMOD
``ils_dispy`` on RW_2025 for the formal private-sector worker.

RWAMOD's disposable income for that worker is exactly the same
identity (origy less tin less the employee pension, maternity and
CBHI-levy arms; RAMA/MMI apply to other sectors), and both engines
tax the identical gross base, so the live cases run the FULL grid -
the Uganda/Ethiopia pattern - from the nil zone through the top band.

The suite disables the euromod output annualization (monthly module)
and bridges the engine's own post-uprating ``yem`` to the three
imported inputs, so parity is index-proof. EUROMOD's one-franc band
lower limits price tin about 0.3 FRW below the statutory bracket
reading at the top of the grid - inside the 1-FRW tolerance.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values RWAMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .rw_core import RW_METADATA, RW_PERIOD, _rw_formal_earner

PIPELINE_MODULE = "rw:statutes/composed/pilot-worker-disposable-income-pipeline"
TAX_MODULE = "rw:statutes/law-2022-027/employment-income-tax"
PENSION_MODULE = "rw:regulations/po-2024-086-01/pension-contribution-rate"
MATERNITY_MODULE = "rw:statutes/law-2016-003/maternity-leave-contributions"

_DISPY_MONTHLY_GRID = (
    ("30000-nil-zone", 30_000.0),
    ("60000-exempt-bound", 60_000.0),
    ("80000-band2", 80_000.0),
    ("150000-band3", 150_000.0),
    ("400000-top-band", 400_000.0),
    ("1000000-high-income", 1_000_000.0),
)


def rw_dispy_cases() -> list[Case]:
    """Single formal private-sector disposable-income cases for ils_dispy."""
    return [
        _dispy_case(f"rw-dispy-{label}", monthly)
        for label, monthly in _DISPY_MONTHLY_GRID
    ]


def _dispy_case(case_id: str, monthly_target: float) -> Case:
    income_input = f"{TAX_MODULE}#input.monthly_taxable_employment_income"
    pension_input = f"{PENSION_MODULE}#input.covered_remuneration"
    maternity_input = f"{MATERNITY_MODULE}#input.contributory_salary"
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "single-formal-employee-disposable-income",
            "monthly_employment_income": monthly_target,
            "axiom_inputs": {
                income_input: monthly_target,
                pension_input: monthly_target,
                maternity_input: monthly_target,
            },
            "euromod_inputs": [_rw_formal_earner(101, monthly_target)],
            # euromod_annualize_outputs is off for this suite (monthly
            # pipeline), so the bridged yem is already monthly.
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [income_input, pension_input, maternity_input]
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: monthly_target * 12.0,
                },
            ),
        ),
        outputs=(Concepts.RW_PILOT_DISPOSABLE_INCOME,),
    )
