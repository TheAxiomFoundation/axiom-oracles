#!/usr/bin/env python3
"""Fuel duty dated-schedule grid: rulespec-uk vs PolicyEngine-UK, 2025 to 2028.

Compares the encoded fuel duty module (rulespec-uk
``uk/policies/govuk/fuel-duty.yaml``, Hydrocarbon Oil Duties Act 1979 s.6)
against PolicyEngine-UK's ``fuel_duty`` at every month start from January 2025
to December 2028, one litre at a time, so each row is the per-litre duty in
force in that month.

The Axiom side takes nothing from PolicyEngine for the main rate:

* The module grounds the HODA s.6(1A) standing rate (£0.5795 a litre).
* The temporary reduction comes from the dated statutory schedule in
  ``reference/uk-fuel-duty-schedule/schedule.yaml``: the Excise Duties
  (Surcharges or Rebates) Act 1979 orders (SI 2022/365 as continued by SI
  2023/329, 2024/300, 2025/228 and SI 2026/164 art. 3 as amended by SI
  2026/555; SI 2026/164 art. 8), at the rate in force on the month start. That
  schedule is not yet a rulespec module (rulespec-uk#349). Until it is, it is a
  primary-source input, where the previous grid bridged PolicyEngine's own
  effective rate into both engines and so could never disagree.

PolicyEngine-UK's ``fuel_duty`` is a monthly variable. It charges the month's
litres (the year's litres / 12) at ``gov.hmrc.fuel_duty.petrol_and_diesel``
read at the month start, less the rural relief where it applies. So the
PolicyEngine side is its own variable evaluated for each month with 12 litres
in the year.

Rural rows (one month a year) add the Rural Fuel Duty Relief, which the module
takes as a supplied input (not encoded). Its rate and the relief-area flag are
read from PolicyEngine and fed to both engines, so those rows test the main
rate under relief, not the relief itself.

Each mismatch row carries ``pe_mechanism``: ``superseded_schedule_calendar_average``
for months to March 2027, where PolicyEngine-UK 2.102.0 applies a calendar-year
average of the pre-May-2026 Budget 2025 schedule dated 1 January
(PolicyEngine-UK#1882), and ``rpi_indexation_not_enacted`` from April 2027,
where PolicyEngine applies forecast RPI uprating (Budget 2025 policy) that no
enacted instrument provides; the #1882 fix keeps those forecast steps. A row
whose PolicyEngine value is not its own parameter stays ``unreconciled``.

Run locally (needs the pinned PolicyEngine-UK, a built axiom rules engine and
the rulespec-uk checkout)::

    RULESPEC_UK_CHECKOUT=/path/to/rulespec-uk \\
      uv run python scripts/generate_uk_fuel_duty.py
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"
SCHEDULE = REPO_ROOT / "reference" / "uk-fuel-duty-schedule" / "schedule.yaml"

YEARS = (2025, 2026, 2027, 2028)
# Budget 2025: fuel duty to be uprated "by Retail Prices Index (RPI) from April
# 2027" (policy, not an enacted instrument).
RPI_FORECAST_FROM = date(2027, 4, 1)
RURAL_MONTH = 6
POLICYENGINE_UK_VERSION = os.environ.get("POLICYENGINE_UK_VERSION", "2.102.0")

RULESPEC_UK = Path(
    os.environ.get("RULESPEC_UK_CHECKOUT")
    or os.path.expanduser("~/TheAxiomFoundation/rulespec-uk")
)

FD_PROGRAM = "uk/policies/govuk/fuel-duty.yaml"
FD_BASE = "uk:policies/govuk/fuel-duty"
FD_OUTPUT = f"{FD_BASE}#fuel_duty_annual_amount"
FD_CONCEPT = FD_OUTPUT

_PETROL = f"{FD_BASE}#input.petrol_litres"
_DIESEL = f"{FD_BASE}#input.diesel_litres"
_REDUCTION = f"{FD_BASE}#input.temporary_fuel_duty_reduction_per_litre"
_AREA = f"{FD_BASE}#input.in_rural_fuel_duty_relief_area"
_RELIEF = f"{FD_BASE}#input.rural_fuel_duty_relief_per_litre"

_PE_FUEL = "fuel_duty"

# Per-litre rows: a hundredth of a penny would hide nothing the schedule
# distinguishes (its steps are whole pence); the 0.0000109 gap between an
# order's operative percentage and its column (D) reference rate stays inside.
_TOLERANCE = 0.00005
_RELATIVE_TOLERANCE = 0.0

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class FDCase:
    case_id: str
    month: date
    rural: bool
    scenario: str


def load_schedule() -> dict:
    return yaml.safe_load(SCHEDULE.read_text())


def schedule_period(schedule: dict, on: date) -> dict:
    for period in schedule["periods"]:
        start = date.fromisoformat(period["effective_from"])
        end = date.fromisoformat(period["effective_to"])
        if start <= on <= end:
            return period
    raise ValueError(f"no schedule period covers {on}")


def statutory_rate(schedule: dict, on: date) -> float:
    """The published (column D) main rate in force on ``on``."""

    return float(schedule_period(schedule, on)["reference_rate"])


def _grid() -> list[FDCase]:
    cases: list[FDCase] = []
    for year in YEARS:
        for month in range(1, 13):
            start = date(year, month, 1)
            cases.append(
                FDCase(f"fd-{start:%Y-%m}", start, False, f"{year}-schedule")
            )
        start = date(year, RURAL_MONTH, 1)
        cases.append(FDCase(f"fd-{start:%Y-%m}-rural", start, True, f"{year}-rural-relief"))
    return cases


def _check_policyengine_version() -> None:
    from importlib.metadata import version

    installed = version("policyengine-uk")
    if installed != POLICYENGINE_UK_VERSION:
        raise SystemExit(
            f"policyengine-uk {installed} is installed but the suite pins "
            f"{POLICYENGINE_UK_VERSION}; run under the pinned version"
        )


def _policyengine_rows(cases: list[FDCase]) -> dict[str, dict]:
    from policyengine_uk import Simulation

    rows: dict[str, dict] = {}
    for year in YEARS:
        year_cases = [c for c in cases if c.month.year == year]
        situation = {
            "people": {f"p-{c.case_id}": {"age": {year: 40}} for c in year_cases},
            "benunits": {
                f"bu-{c.case_id}": {"members": [f"p-{c.case_id}"]} for c in year_cases
            },
            "households": {
                f"hh-{c.case_id}": {
                    "members": [f"p-{c.case_id}"],
                    "petrol_litres": {year: 12.0},
                    "diesel_litres": {year: 0.0},
                    "in_rural_fuel_duty_relief_area": {year: c.rural},
                }
                for c in year_cases
            },
        }
        sim = Simulation(situation=situation)
        for index, case in enumerate(year_cases):
            period = f"{case.month:%Y-%m}"
            params = sim.tax_benefit_system.parameters(case.month.isoformat()).gov.hmrc.fuel_duty
            rows[case.case_id] = {
                "fuel_duty": float(sim.calculate(_PE_FUEL, period)[index]),
                "petrol_and_diesel_parameter": float(params.petrol_and_diesel),
                "rural_relief": float(params.rural_fuel_duty_relief),
            }
    return rows


def _axiom_values(cases: list[FDCase], pe_rows: dict, schedule: dict) -> dict[str, float]:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    standing = float(schedule["standing_rate"]["rate"])
    axiom_cases: list[Case] = []
    for case in cases:
        reduction = round(standing - statutory_rate(schedule, case.month), 10)
        axiom_cases.append(
            Case(
                case_id=case.case_id,
                period=case.month.isoformat(),
                metadata={
                    "axiom_entity": "Household",
                    "axiom_entity_id": "household",
                    "axiom_inputs": {
                        _PETROL: 1.0,
                        _DIESEL: 0.0,
                        _REDUCTION: reduction,
                        _AREA: case.rural,
                        _RELIEF: pe_rows[case.case_id]["rural_relief"] if case.rural else 0.0,
                    },
                },
                outputs=(FD_OUTPUT,),
            )
        )

    runner = AxiomRulesRunner(
        program_path=RULESPEC_UK / FD_PROGRAM,
        binary_path=os.environ.get("AXIOM_RULES_ENGINE_BINARY"),
        default_entity="Household",
        default_entity_id="household",
        rulespec_repo_roots=(RULESPEC_UK,),
        mode="explain",
    )
    values: dict[str, float] = {}
    for result in runner.run_cases(axiom_cases, [FD_OUTPUT]):
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        values[str(result.household_id)] = float(result.values[FD_OUTPUT])
    return values


def classify_mechanism(case: FDCase, pe_row: dict, statutory: float, axiom: float) -> str:
    """Name the PolicyEngine behaviour a mismatching month reconciles to.

    Attribution needs all of: the Axiom value is the dated statutory rate less
    any supplied relief (so an Axiom error is never explained away); the
    PolicyEngine value is exactly its own parameter read at the month start less
    the same relief; and that parameter differs from the statutory rate.
    """

    relief = pe_row["rural_relief"] if case.rural else 0.0
    if abs(axiom - (statutory - relief)) > _TOLERANCE:
        return "unreconciled"
    if abs(pe_row["fuel_duty"] - (pe_row["petrol_and_diesel_parameter"] - relief)) > _TOLERANCE:
        return "unreconciled"
    if abs(pe_row["petrol_and_diesel_parameter"] - statutory) <= _TOLERANCE:
        return "unreconciled"
    if case.month < RPI_FORECAST_FROM:
        return "superseded_schedule_calendar_average"
    if pe_row["petrol_and_diesel_parameter"] > statutory:
        return "rpi_indexation_not_enacted"
    return "unreconciled"


def _match(left: float, right: float) -> bool:
    return abs(left - right) <= _TOLERANCE


def _counts(values: list[str]) -> list[dict]:
    tally: dict[str, int] = {}
    for value in values:
        tally[value] = tally.get(value, 0) + 1
    return [{"count": n, "value": v} for v, n in sorted(tally.items())]


def build_report(cases: list[FDCase], pe_rows: dict, axiom: dict, schedule: dict) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    for case in cases:
        pe_row = pe_rows[case.case_id]
        period = schedule_period(schedule, case.month)
        statutory = float(period["reference_rate"])
        ax_val = axiom[case.case_id]
        pe_val = pe_row["fuel_duty"]
        ok = _match(ax_val, pe_val)
        row = {
            "case_id": case.case_id,
            "concept": FD_CONCEPT,
            "scenario": case.scenario,
            "month": f"{case.month:%Y-%m}",
            "rural": case.rural,
            "litres": 1.0,
            "statutory_rate": statutory,
            "schedule_period": period["id"],
            "policyengine_petrol_and_diesel": pe_row["petrol_and_diesel_parameter"],
            "rural_relief": pe_row["rural_relief"] if case.rural else 0.0,
            "axiom": ax_val,
            "policyengine": pe_val,
            "axiom_vs_policyengine": {"difference": ax_val - pe_val, "match": ok},
        }
        report_cases.append(row)
        if ok:
            continue
        mechanism = classify_mechanism(case, pe_row, statutory, ax_val)
        row["pe_mechanism"] = mechanism
        mismatches.append(
            {
                "case_id": case.case_id,
                "concept": FD_CONCEPT,
                "kind": "amount_difference",
                "engines": ["axiom", "policyengine"],
                "left_engine": "axiom",
                "right_engine": "policyengine",
                "left": ax_val,
                "right": pe_val,
                "difference": ax_val - pe_val,
                "month": f"{case.month:%Y-%m}",
                "rural": case.rural,
                "scenario": case.scenario,
                "statutory_rate": statutory,
                "schedule_period": period["id"],
                "policyengine_petrol_and_diesel": pe_row["petrol_and_diesel_parameter"],
                "rural_relief": pe_row["rural_relief"] if case.rural else 0.0,
                "pe_mechanism": mechanism,
            }
        )
    n = len(report_cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * match_count / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-fuel-duty",
        "concept": FD_CONCEPT,
        "population": "case-grid",
        "validation_year": YEARS[0],
        "validation_years": list(YEARS),
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {"axiom": FD_OUTPUT, "policyengine": _PE_FUEL},
        "tolerance": {"absolute": _TOLERANCE, "relative": _RELATIVE_TOLERANCE},
        "case_count": n,
        "summary": {
            "comparison_count": n,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "axiom_vs_policyengine_match_rate": match_rate,
            "policyengine_matches": match_count,
            "weighted": {
                "comparison_weight": n,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
                "match_rate": match_rate,
            },
            "mismatches_by_concept": _counts([m["concept"] for m in mismatches]),
            "mismatches_by_kind": _counts([m["kind"] for m in mismatches]),
            "mismatches_by_scenario": _counts([m["scenario"] for m in mismatches]),
            "mismatches_by_mechanism": _counts([m["pe_mechanism"] for m in mismatches]),
            "error_count": 0,
            "errors_by_engine": [],
        },
        "mismatches": mismatches,
        "errors": [],
        "cases": report_cases,
        "provenance": {
            "generated": datetime.now(timezone.utc).date().isoformat(),
            "generator": "scripts/generate_uk_fuel_duty.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {FD_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "schedule": "reference/uk-fuel-duty-schedule/schedule.yaml",
            "commensurability": (
                "One litre of petrol a month. PolicyEngine-UK's monthly fuel_duty charges "
                "the month's litres at gov.hmrc.fuel_duty.petrol_and_diesel read at the "
                "month start. The Axiom module charges the HODA 1979 s.6(1A) standing "
                "rate less the reduction in force on that date under the Excise Duties "
                "(Surcharges or Rebates) Act 1979 orders (reference/uk-fuel-duty-schedule, "
                "not yet a rulespec module: rulespec-uk#349). Rural rows supply "
                "PolicyEngine's relief rate and area flag to both engines."
            ),
        },
    }


def main() -> int:
    _check_policyengine_version()
    schedule = load_schedule()
    cases = _grid()
    pe_rows = _policyengine_rows(cases)
    axiom = _axiom_values(cases, pe_rows, schedule)
    report = build_report(cases, pe_rows, axiom, schedule)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-fuel-duty"
    stamp = date.today().isoformat()
    text = json.dumps(report, indent=2) + "\n"
    (REPORTS / f"{basename}-{stamp}.json").write_text(text)
    (DASH_PUBLIC / f"{basename}.json").write_text(text)

    summary = report["summary"]
    print(
        f"uk-fuel-duty: PE match {summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['match_count']}/{report['case_count']} months); "
        f"mismatches by mechanism: {summary['mismatches_by_mechanism']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
