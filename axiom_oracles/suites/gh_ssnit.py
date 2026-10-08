"""Ghana SSNIT contribution oracle suite (GHAMOD).

``gh-ssnit-contributions`` compares the Axiom Act 766 s.3 contribution
outputs against GHAMOD (SOUTHMOD A4.0, country GH, system GH_2025):

* ``employee_social_security_contribution`` (worker 5.5% of qualifying
  employment income, s.3(1)) against GHAMOD ``tscee_s``.
* ``employer_social_security_contribution`` (employer 13%, s.3(2)) against
  GHAMOD ``tscer_s``.

All cases use formal-sector (lfo=1) employee heads aged 35, inside GHAMOD's
contributor window, where both engines apply the identical flat rates (live
run 2026-10-04: tscee_s and tscer_s are exactly 5.5% and 13% of the
post-uprating yem at every sweep income). GHAMOD pays contributions only for
ages 15 to 45 (probed: ages 14, 46 and 50 get tscee_s = tscer_s = 0), a model
simplification with no basis in Act 766 s.3, the section encoded, which sets
no age limit. The encoded RuleSpec follows s.3, so out-of-window ages are not
live cases; the divergence is recorded in
``axiom_oracles/data/ghamod_issues.json``
(``ghamod-tscee-tscer-age-15-45-contributor-cap``).

Input convention and license discipline follow ``gh_income_tax``: monetary
inputs pre-divide by the GH_2025 employment-income uprating index so the
engine prices the intended nominal amount, the post-uprating ``yem`` bridge
keeps both engines on an identical base, and no SOUTHMOD model XML, dataset
row, or DRD text is committed — expected values are values GHAMOD itself
produced.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    GH_METADATA,
    GH_PERIOD,
    _gh_formal_earner,
)

SSNIT_MODULE = (
    "gh:statutes/act-766/national-pensions-2008/"
    "section-3-contributions-to-the-scheme"
)


def _ssnit_input(name: str) -> str:
    return f"{SSNIT_MODULE}#input.{name}"


# Income sweep (nominal GHS, annual). The rates are flat so any positive
# income validates them; the sweep spans low formal wages through executive
# pay to pin scale-independence. Expected annual amounts (GHAMOD-produced,
# probed live at age 35): 550/1,300 · 3,300/7,800 · 6,600/15,600 ·
# 27,500/65,000 — employee/employer respectively.
_SSNIT_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("10k", 10_000.0),
    ("60k", 60_000.0),
    ("120k", 120_000.0),
    ("500k", 500_000.0),
)


def gh_ssnit_contributions_cases() -> list[Case]:
    """Formal-employee SSNIT cases for the GHAMOD tscee_s/tscer_s oracles."""
    return [
        _ssnit_case(f"gh-ssnit-{label}", income)
        for label, income in _SSNIT_INCOME_GRID
    ]


def _ssnit_case(case_id: str, annual_income: float) -> Case:
    qualifying_income = _ssnit_input("qualifying_employment_income")
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-formal-employee-ssnit-contributions",
            "yearly_earned_income": annual_income,
            # Placeholder; the post-uprating euromod yem overwrites it via the
            # bridge so both engines price the identical contribution base.
            "axiom_inputs": {qualifying_income: annual_income},
            "euromod_inputs": [_gh_formal_earner(101, annual_income, dag=35)],
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
        outputs=(
            Concepts.GH_EMPLOYEE_SSNIT_CONTRIBUTION,
            Concepts.GH_EMPLOYER_SSNIT_CONTRIBUTION,
        ),
    )
