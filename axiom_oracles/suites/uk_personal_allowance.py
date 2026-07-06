"""UK personal allowance (ITA 2007 s.35) — Axiom RuleSpec vs UKMOD ``tinta_s``.

The composed single-employee income-tax pipeline in rulespec-uk
(``uk/statutes/income_tax/individual/pilot_worker_oracle_pipeline.yaml``)
already exposes the personal allowance as a named intermediate step,
``uk_pit_pilot_personal_allowance``:

    ceil(max(0, personal_allowance_base_amount
                - max(0, adjusted_net_income - adjusted_net_income_reduction_threshold) / 2))

which is the Income Tax Act 2007 section 35(1)-(3) preliminary allowance less
the section 35(2)-(3) income-limit taper (half of adjusted net income in excess
of the limit, floored at zero). UKMOD's ``tinta_uk`` policy computes the same
final personal allowance ``tinta_s = $ITPerAll`` less the income-limit taper,
so the surface is a pure single-individual income sweep with no household
structure, receipt history, or stochastic take-up draw — the most directly
gradable of the uncovered UK surfaces (see axiom-oracles#190).

The final worker-PIT liability (``uk_pit_pilot_income_tax_liability`` vs UKMOD
``tin_s``) is already compared by the ``uk-worker-pit`` suite; this surface
compares the s.35 allowance itself so the taper is exercised as a first-class
parity target rather than only folded into the downstream liability.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
PIT_MODULE = "uk:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# Personal allowances are frozen at the 2026-27 vintage; the engine selects
# the parameter version by period.start, so the Axiom side evaluates on the
# 2026-27 tax-year boundary (6 April 2026). UKMOD resolves the policy year from
# euromod_system (UK_2026). 2025-26 and 2026-27 share the frozen £12,570
# allowance and £100,000 income limit, so UK_2025 and UK_2026 return the same
# values for these cases.
UK_PERSONAL_ALLOWANCE_PERIOD = "2026-04-06"

# Single-individual gross-employment-income grid straddling the s.35 taper.
#   40k   — full allowance (income below the £100,000 limit)
#   100k  — at the income limit (full allowance; taper starts above it)
#   110k  — mid-taper (allowance reduced by half of £10,000 excess)
#   125.14k — allowance fully withdrawn to zero (£12,570 * 2 above the limit)
#   150k  — allowance remains zero (well beyond full withdrawal)
_ALLOWANCE_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("40k", 40_000.0),
    ("100k", 100_000.0),
    ("110k", 110_000.0),
    ("125k", 125_140.0),
    ("150k", 150_000.0),
)


def uk_personal_allowance_cases() -> list[Case]:
    """Single-individual UK personal-allowance cases for the UKMOD UK_2026 oracle."""

    return [
        _single_allowance_case(f"uk-personal-allowance-{label}", income)
        for label, income in _ALLOWANCE_INCOME_GRID
    ]


def _single_allowance_case(case_id: str, annual_income: float) -> Case:
    income_input = _pit_input("uk_pit_pilot_annual_employment_income")
    return Case(
        case_id=case_id,
        period=UK_PERSONAL_ALLOWANCE_PERIOD,
        metadata={
            **UK_METADATA,
            "scenario": "single-personal-allowance",
            "yearly_earned_income": annual_income,
            "axiom_inputs": {
                income_input: annual_income,
                _pit_input("uk_pit_pilot_supplied_section_24_reliefs"): 0,
            },
            "euromod_inputs": [_euromod_worker_input(annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [income_input],
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
        outputs=(Concepts.UK_PERSONAL_ALLOWANCE,),
    )


def _pit_input(name: str) -> str:
    return f"{PIT_MODULE}#input.{name}"


def _euromod_worker_input(annual_income: float) -> dict[str, float | int]:
    employed = annual_income > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "yem": annual_income / 12,
        "yemmy": 12 if employed else 0,
    }
