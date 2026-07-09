"""Zambia composed disposable-income oracle suite (MicroZAMOD ``ils_dispy``).

``zm-dispy`` compares the rulespec-zm composed single-employee pipeline
- ``pilot_worker_disposable_income`` (the Act 22 of 2023 Charging
Schedule income tax on GROSS income, less the employee NAPSA and NHIMA
contributions) - against MicroZAMOD ``ils_dispy`` on ZM_2025.

The engines diverge wherever any band above nil is reached:
MicroZAMOD taxes a base NET of the employee contributions (``ttb_s =
yem - tsceepi_s - tsceehl_s``), which the CY2025 statute does not
support (Act 22 of 2024 s.4 makes the approved-fund deduction
employer-only; no NHIMA deductibility provision exists) - rulespec-zm#1
finding 1, probed: at 240,000 gross the model returns tax 54,984 /
dispy 170,616 where the statutory chain gives 60,312 / 165,288, and at
409,968 gross the tax gap is 9,101.29/yr. The live cases therefore sit
in the shared-nil zone - gross at or below the 61,200 exempt bound,
where both engines charge no tax and disposable income is exactly
gross less the two contributions - exercising the composed
origy - contributions identity end to end; the taxed-zone divergence
is dispositioned with the probed values in the comparison description
and the rulespec-zm#1 ledger (the Ghana gh-dispy precedent, with the
opposite sign: GHAMOD taxed gross where the statute deducted, and
MicroZAMOD deducts where the statute taxes gross).

Bridges feed the engine's own post-uprating ``yem`` to the imported
tax input and the engine's own ``tsceepi_s``/``tsceehl_s`` to the
composed contribution inputs, so parity in the nil zone is exact by
construction regardless of the uprating index or the administrative
NAPSA ceiling.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values MicroZAMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .zm_core import ZM_METADATA, ZM_PERIOD_2025, _zm_formal_earner

PIPELINE_MODULE = "zm:statutes/composed/pilot-worker-disposable-income-pipeline"
PAYE_MODULE = "zm:statutes/act-2023-22/income-tax-amendment-2023"

# Annual gross incomes inside the shared-nil zone: the statute charges
# nothing at or below 61,200 gross, and the model's net base stays
# below its own 61,200 bound for gross up to ~65,116, so both engines
# charge zero tax and dispy = gross - NAPSA - NHIMA on each case.
_DISPY_INCOME_GRID = (
    ("40000-nil-interior", 40_000.0),
    ("61200-exempt-bound", 61_200.0),
)


def zm_dispy_cases() -> list[Case]:
    """Single formal-sector employee disposable-income cases for ils_dispy."""
    return [
        _dispy_case(f"zm-dispy-{label}", income)
        for label, income in _DISPY_INCOME_GRID
    ]


def _dispy_case(case_id: str, annual_income: float) -> Case:
    individual_income = f"{PAYE_MODULE}#input.individual_income"
    napsa_input = f"{PIPELINE_MODULE}#input.napsa_employee_contribution"
    nhima_input = f"{PIPELINE_MODULE}#input.nhima_employee_contribution"
    benefits_input = f"{PIPELINE_MODULE}#input.benefits_received"
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2025,
        metadata={
            **ZM_METADATA,
            "scenario": "single-formal-employee-disposable-income",
            "yearly_earned_income": annual_income,
            # Placeholders; the bridges overwrite with the engine's own
            # post-uprating yem and its computed contributions.
            "axiom_inputs": {
                individual_income: annual_income,
                napsa_input: annual_income * 0.05,
                nhima_input: annual_income * 0.01,
                benefits_input: 0.0,
            },
            "euromod_inputs": [_zm_formal_earner(101, annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [individual_income],
                "tsceepi_s": [napsa_input],
                "tsceehl_s": [nhima_input],
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
        outputs=(Concepts.ZM_PILOT_DISPOSABLE_INCOME,),
    )
