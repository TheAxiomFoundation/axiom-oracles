"""Uganda rental and presumptive income-tax oracle suites (UGAMOD).

``ug-rental`` compares the rulespec-ug individual rental tax — 12% of
gross rental income above the 2,820,000/yr threshold (Third Schedule
Part VI as substituted by the Income Tax (Amendment) Act, 2022; no
expense deductions for individuals per the substituted s.22(1)(c)) —
against UGAMOD ``tpr_s`` (probed exact: 261,600 at 5m gross and 861,600
at 10m).

``ug-presumptive`` compares the rulespec-ug small-business presumptive
tax — the Act 20 of 2020 Second Schedule bands to the 150m regime
ceiling, fixed amounts without records and cumulative-component rates
with records — against UGAMOD ``ttn_s`` in both regimes (probed exact
at every band: e.g. 43,005.01 = 0.4% x excess over 10m with records at
uprated turnover 20,751,252; fixed 900,000 in the 80m-150m band; zero
above the ceiling).

License discipline as in ``ug_income_tax``: bundle referenced by path
only; expected values are values UGAMOD itself produced.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .ug_income_tax import (
    UG_METADATA,
    UG_PERIOD,
    UG_UPRATE_2024_TO_2025,
    _ug_base_row,
)

RENTAL_MODULE = (
    "ug:statutes/act-2022-11/income-tax-amendment-2022/"
    "third-schedule-rental-rate-part-substituted"
)
PRESUMPTIVE_MODULE = "ug:statutes/act-2020-20/income-tax-amendment-2020"

# Annual gross rental incomes (post-uprating UGX): below, at and above
# the 2,820,000 threshold, including both live-probe incomes.
_RENTAL_GRID = (
    ("2m-below-threshold", 2_000_000.0),
    ("2820000-at-threshold", 2_820_000.0),
    ("probe-5m", 5_000_000.0),
    ("probe-10m", 10_000_000.0),
)

# (label, annual turnover, keeps_records) — every band in both regimes,
# the nil band, and the above-ceiling case.
_PRESUMPTIVE_GRID = (
    ("nil-band-8m-records", 8_000_000.0, True),
    ("band1-20m-no-records", 20_000_000.0, False),
    ("band2-40m-no-records", 40_000_000.0, False),
    ("band3-60m-no-records", 60_000_000.0, False),
    ("band4-100m-no-records", 100_000_000.0, False),
    ("band1-20m-records", 20_000_000.0, True),
    ("band2-40m-records", 40_000_000.0, True),
    ("band3-60m-records", 60_000_000.0, True),
    ("band4-100m-records", 100_000_000.0, True),
    ("above-ceiling-160m", 160_000_000.0, False),
)


def _em_monthly(annual: float) -> float:
    return (annual / UG_UPRATE_2024_TO_2025) / 12.0


def ug_rental_cases() -> list[Case]:
    """Individual rental-tax cases for the UGAMOD tpr_s oracle."""
    return [
        _rental_case(f"ug-rental-{label}", income)
        for label, income in _RENTAL_GRID
    ]


def _rental_case(case_id: str, annual_gross_rental: float) -> Case:
    gross_input = f"{RENTAL_MODULE}#input.gross_rental_income"
    row = _ug_base_row(1, 101)
    monthly = _em_monthly(annual_gross_rental)
    row.update({"ypr": monthly})
    return Case(
        case_id=case_id,
        period=UG_PERIOD,
        metadata={
            **UG_METADATA,
            "scenario": "single-landlord-rental-income",
            "annual_gross_rental_income": annual_gross_rental,
            "axiom_inputs": {gross_input: annual_gross_rental},
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ypr": [gross_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.UG_RENTAL_INCOME_TAX,),
    )


def ug_presumptive_cases() -> list[Case]:
    """Small-business presumptive-tax cases for the UGAMOD ttn_s oracle."""
    return [
        _presumptive_case(f"ug-presumptive-{label}", turnover, records)
        for label, turnover, records in _PRESUMPTIVE_GRID
    ]


def _presumptive_case(case_id: str, annual_turnover: float, records: bool) -> Case:
    turnover_input = f"{PRESUMPTIVE_MODULE}#input.annual_gross_turnover"
    records_input = f"{PRESUMPTIVE_MODULE}#input.taxpayer_keeps_records"
    row = _ug_base_row(1, 101)
    row.update({"ytn": _em_monthly(annual_turnover), "trc": 1 if records else 0,
                "tcl": 1})
    return Case(
        case_id=case_id,
        period=UG_PERIOD,
        metadata={
            **UG_METADATA,
            "scenario": "small-business-presumptive-turnover",
            "annual_gross_turnover": annual_turnover,
            "taxpayer_keeps_records": records,
            "axiom_inputs": {
                turnover_input: annual_turnover,
                records_input: records,
            },
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ytn": [turnover_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.UG_PRESUMPTIVE_INCOME_TAX,),
    )
