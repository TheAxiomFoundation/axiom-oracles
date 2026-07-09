"""Ethiopia composed disposable-income oracle suite (ETMOD ``ils_dispy``).

``et-dispy`` compares the rulespec-et composed monthly pipeline -
``pilot_worker_disposable_income`` (the Proclamation 1395/2025
Article 11 employment income tax on gross monthly income, less the
Proclamation 715/2011 employee 7 percent pension share) - against
ETMOD ``ils_dispy`` on ET_2025.

The statutory base is gross employment income (Proclamation 979/2016
Articles 10(3) and 65(1)(c) verified: no employee deduction exists)
and ETMOD taxes gross too, so unlike Ghana (finding #13) and Zambia
(finding 1) there is NO base divergence: the live cases run the FULL
grid - the Uganda pattern - from the nil zone through the top band.

Bridges feed the engine's own post-uprating ``yem`` (divided to the
monthly module basis) to both imported inputs, so parity is
index-proof.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values ETMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .et_core import ET_METADATA, ET_PERIOD, _et_formal_earner
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE

PIPELINE_MODULE = "et:statutes/composed/pilot-worker-disposable-income-pipeline"
TAX_MODULE = "et:statutes/proc-1395-2025/income-tax-amendment-2025"
PENSION_MODULE = "et:statutes/proc-715-2011/private-organization-employees-pension"

_DISPY_MONTHLY_GRID = (
    ("1500-nil-zone", 1_500.0),
    ("3000-band2", 3_000.0),
    ("7000-band3-top", 7_000.0),
    ("12000-band5", 12_000.0),
    ("20000-top-band", 20_000.0),
)


def et_dispy_cases() -> list[Case]:
    """Single formal-sector employee disposable-income cases for ils_dispy."""
    return [
        _dispy_case(f"et-dispy-{label}", monthly)
        for label, monthly in _DISPY_MONTHLY_GRID
    ]


def _dispy_case(case_id: str, monthly_target: float) -> Case:
    income_input = f"{TAX_MODULE}#input.monthly_employment_income"
    salary_input = f"{PENSION_MODULE}#input.monthly_salary"
    benefits_input = f"{PIPELINE_MODULE}#input.benefits_received"
    return Case(
        case_id=case_id,
        period=ET_PERIOD,
        metadata={
            **ET_METADATA,
            "scenario": "single-formal-employee-disposable-income",
            "monthly_employment_income": monthly_target,
            # Placeholders; the engine's post-uprating yem overwrites
            # both imported inputs via the bridge (monthly basis).
            "axiom_inputs": {
                income_input: monthly_target,
                salary_input: monthly_target,
                benefits_input: 0.0,
            },
            "euromod_inputs": [_et_formal_earner(101, monthly_target)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {"inputs": [income_input, salary_input], "divide_by": 12}
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
        outputs=(Concepts.ET_PILOT_DISPOSABLE_INCOME,),
    )
