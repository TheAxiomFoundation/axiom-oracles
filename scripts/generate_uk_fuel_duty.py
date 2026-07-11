#!/usr/bin/env python3
"""Fuel duty case grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded fuel duty module (rulespec-uk
``uk/policies/govuk/fuel-duty.yaml``, Hydrocarbon Oil Duties Act 1979 s.6)
against PolicyEngine-UK's ``fuel_duty`` on a synthetic household grid at the
2026 validation year.

Both sides are commensurable because ``fuel_duty`` is the same closed form of the
same supplied inputs on each engine:

* PolicyEngine-UK computes an effective per-litre rate
  ``petrol_and_diesel - in_rural_relief_area * rural_relief`` (£0.5345 for 2026,
  the OBR-forecast rate reflecting the temporary 5p cut extension) applied to the
  household's petrol and diesel litres.
* The rulespec ``fuel_duty_annual_amount`` grounds the HODA s.6(1A) standing rate
  (£0.5795 a litre) and subtracts a supplied temporary reduction and the rural
  relief. The temporary reduction is bridged as the difference between the
  standing statutory rate and PolicyEngine's in-force effective rate
  (0.5795 - 0.5345 = 0.045), which is exactly the temporary Budget-resolution cut
  that is not carried into the consolidated s.6(1A) text. Both engines therefore
  apply the same in-force effective rate to the same litres.

The rural relief rate, the relief-area flag, and the litres are read from
PolicyEngine and fed as rulespec supplied inputs, so the grid matches to the
penny across petrol-only, diesel-only, combined, rural-relief, and zero cases.

Run locally (needs PolicyEngine-UK 2.89.2, a built axiom rules engine, and the
rulespec-uk checkout)::

    uv run python scripts/generate_uk_fuel_duty.py \
      --rulespec-root /path/to/rulespec-uk \
      --axiom-binary /path/to/axiom-rules-engine
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_rulespec_runtime import parse_canonical_runtime_args

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
POLICYENGINE_UK_VERSION = "2.89.2"


FD_PROGRAM = "uk/policies/govuk/fuel-duty.yaml"
FD_BASE = "uk:policies/govuk/fuel-duty"
FD_OUTPUT = f"{FD_BASE}#fuel_duty_annual_amount"
FD_CONCEPT = FD_OUTPUT

# The HODA s.6(1A) standing rate the module grounds; must match the module.
STANDING_RATE = 0.5795

_PETROL = f"{FD_BASE}#petrol_litres"
_DIESEL = f"{FD_BASE}#diesel_litres"
_REDUCTION = f"{FD_BASE}#temporary_fuel_duty_reduction_per_litre"
_AREA = f"{FD_BASE}#in_rural_fuel_duty_relief_area"
_RELIEF = f"{FD_BASE}#rural_fuel_duty_relief_per_litre"

_PE_FUEL = "fuel_duty"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class FDCase:
    case_id: str
    scenario: str
    petrol_litres: float
    diesel_litres: float
    rural: bool = False


def _grid() -> list[FDCase]:
    return [
        FDCase("fd-petrol-only-small", "petrol-only", 800.0, 0.0),
        FDCase("fd-petrol-only-large", "petrol-only", 2500.0, 0.0),
        FDCase("fd-diesel-only", "diesel-only", 0.0, 1200.0),
        FDCase("fd-petrol-and-diesel", "petrol-and-diesel", 900.0, 400.0),
        FDCase("fd-heavy-driver", "petrol-and-diesel", 3000.0, 1000.0),
        FDCase("fd-rural-relief-petrol", "rural-relief", 1000.0, 0.0, rural=True),
        FDCase("fd-rural-relief-both", "rural-relief", 700.0, 300.0, rural=True),
        FDCase("fd-rural-relief-diesel", "rural-relief", 0.0, 1500.0, rural=True),
        FDCase("fd-no-fuel", "no-fuel", 0.0, 0.0),
    ]


def _pe_situation(case: FDCase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {"person": {"age": {year: 40}}},
        "benunits": {"bu": {"members": ["person"]}},
        "households": {
            "hh": {
                "members": ["person"],
                "petrol_litres": {year: case.petrol_litres},
                "diesel_litres": {year: case.diesel_litres},
                "in_rural_fuel_duty_relief_area": {year: case.rural},
            }
        },
    }


def _policyengine_rows(cases: list[FDCase]) -> dict[str, dict]:
    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, dict] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        params = sim.tax_benefit_system.parameters(f"{year}-04-06")
        pe_main_rate = float(params.gov.hmrc.fuel_duty.petrol_and_diesel)
        rural_relief = float(params.gov.hmrc.fuel_duty.rural_fuel_duty_relief)
        rows[case.case_id] = {
            "fuel_duty": float(sim.calculate(_PE_FUEL, year).sum()),
            "petrol_litres": float(sim.calculate("petrol_litres", year).sum()),
            "diesel_litres": float(sim.calculate("diesel_litres", year).sum()),
            "rural": bool(sim.calculate("in_rural_fuel_duty_relief_area", year)[0]),
            # Temporary Budget-resolution reduction from the s.6(1A) standing rate
            # to PolicyEngine's in-force effective main rate.
            "temporary_reduction": STANDING_RATE - pe_main_rate,
            "rural_relief": rural_relief,
        }
    return rows


def _axiom_awards(
    cases: list[FDCase],
    pe_rows: dict[str, dict],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = rulespec_root / FD_PROGRAM

    axiom_cases: list[Case] = []
    for case in cases:
        row = pe_rows[case.case_id]
        axiom_cases.append(
            Case(
                case_id=case.case_id,
                period="2026-04-06",
                metadata={
                    "axiom_entity": "Household",
                    "axiom_entity_id": "household",
                    "axiom_inputs": {
                        _PETROL: row["petrol_litres"],
                        _DIESEL: row["diesel_litres"],
                        _REDUCTION: row["temporary_reduction"],
                        _AREA: row["rural"],
                        _RELIEF: row["rural_relief"],
                    },
                },
                outputs=(FD_OUTPUT,),
            )
        )

    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=axiom_binary,
        default_entity="Household",
        default_entity_id="household",
        rulespec_root=rulespec_root,
        mode="explain",
    )
    results = runner.run_cases(axiom_cases, [FD_OUTPUT])
    awards: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        awards[str(result.household_id)] = float(result.values[FD_OUTPUT])
    return awards


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[FDCase], pe_rows: dict[str, dict], axiom: dict[str, float]
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_val = pe_rows[case.case_id]["fuel_duty"]
        ax_val = axiom[case.case_id]
        ok = _match(ax_val, pe_val)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": FD_CONCEPT,
                "scenario": case.scenario,
                "petrol_litres": pe_rows[case.case_id]["petrol_litres"],
                "diesel_litres": pe_rows[case.case_id]["diesel_litres"],
                "rural": pe_rows[case.case_id]["rural"],
                "axiom": ax_val,
                "policyengine": pe_val,
                "axiom_vs_policyengine": {
                    "difference": ax_val - pe_val,
                    "match": ok,
                },
            }
        )
        if not ok:
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
                }
            )
    n = len(cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-fuel-duty",
        "concept": FD_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
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
            "policyengine_matches": matches,
            "weighted": {
                "comparison_weight": n,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
                "match_rate": match_rate,
            },
            "mismatches_by_concept": (
                [{"count": mismatch_count, "value": FD_CONCEPT}]
                if mismatch_count
                else []
            ),
            "mismatches_by_kind": (
                [{"count": mismatch_count, "value": "amount_difference"}]
                if mismatch_count
                else []
            ),
            "mismatches_by_scenario": [],
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
            "commensurability": (
                "PolicyEngine-UK fuel_duty applies an effective per-litre rate "
                "(petrol_and_diesel 0.5345 for 2026, less rural relief) to the "
                "household's petrol and diesel litres. The rulespec module grounds "
                "the HODA s.6(1A) standing rate £0.5795 and subtracts a supplied "
                "temporary reduction (0.5795 - 0.5345 = 0.045, the temporary "
                "Budget-resolution 5p cut extension not carried into the "
                "consolidated s.6(1A) text) and the rural relief, so both engines "
                "apply the same in-force effective rate to the same supplied litres."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="uk")
    cases = _grid()
    pe_rows = _policyengine_rows(cases)
    axiom = _axiom_awards(
        cases,
        pe_rows,
        rulespec_root=rulespec_root,
        axiom_binary=axiom_binary,
    )
    report = build_report(cases, pe_rows, axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-fuel-duty"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-fuel-duty: PE match {summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{report['case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
