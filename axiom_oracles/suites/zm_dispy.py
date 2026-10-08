"""Zambia composed disposable-income oracle suite (MicroZAMOD ``ils_dispy``).

``zm-dispy`` compares the rulespec-zm composed single-employee pipeline
- ``pilot_worker_disposable_income`` (the Act 22 of 2023 Charging
Schedule income tax on GROSS income, less the employee NAPSA and NHIMA
contributions) - against MicroZAMOD ``ils_dispy`` on ZM_2025.

The live cases sit in the shared-nil zone: gross at or below the
61,200 exempt bound, where neither engine charges tax and disposable
income is gross less the two contributions. Above it the engines
diverge, because MicroZAMOD taxes a base NET of the employee
contributions (probed: ``ttb_s = yem - tsceepi_s - tsceehl_s``) while
the pipeline taxes gross. Whether CY2025 law allows that deduction is
rulespec-zm#1 CANDIDATE finding 1 (see ``zm_core`` and
``axiom_oracles/data/microzamod_issues.json``; the rest of s.37 and
the principal Act are not captured). Magnitude if it holds (probed on
2026-10-04): at 240,000 gross the model returns tax 54,984 and dispy
170,616 where the schedule on gross gives 60,312 and 165,288. The taxed
zone is a ledger entry, not a live case. (Ghana's gh-dispy has the
mirror-image divergence: GHAMOD taxed gross where the statute
deducted.)

Bridges: the engine's own post-uprating ``yem`` feeds the imported tax
input, and the engine's own ``tsceepi_s``/``tsceehl_s`` feed the
pipeline's contribution inputs, which the pipeline takes as inputs
rather than computing. The contribution legs therefore cannot
disagree here; they are tested against the rulespec-zm NAPSA and NHIMA
modules by zm-napsa-contributions and zm-nhima-contributions. What
zm-dispy tests is the tax leg (nil on both sides in this zone) and
that ``ils_dispy`` carries nothing beyond gross less tax and the two
contributions for this household. Period basis: the pipeline and
``ils_dispy`` are compared annually (the adapter's default x12), but
the adapter returns ``tsceepi_s``/``tsceehl_s`` monthly (its
``NON_ANNUALIZED_OUTPUTS`` list), so those two bridges multiply by 12
onto the annual pipeline inputs. Live run: 40,000 gross -> dispy
37,600 and 61,200 -> 57,528 on both engines (gross less 5% NAPSA and
1% NHIMA, no tax).

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
# nothing at or below 61,200 gross, and the model's net base (94% of
# gross below the NAPSA ceiling) stays at or below 61,200 for gross up
# to ~65,106 (61,200 / 0.94 = 65,106.38; probed: tax 0 at 65,106 and
# positive at 65,107), so both engines charge zero tax and dispy =
# gross - NAPSA - NHIMA on each case.
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
            # yem arrives annualized; the adapter returns tsceepi_s and
            # tsceehl_s monthly (NON_ANNUALIZED_OUTPUTS), so their
            # bridges annualize onto the Year-period pipeline inputs.
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [individual_income],
                "tsceepi_s": {"inputs": [napsa_input], "multiply_by": 12},
                "tsceehl_s": {"inputs": [nhima_input], "multiply_by": 12},
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
