#!/usr/bin/env python3
"""Attendance Allowance rate grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded Attendance Allowance weekly rates (rulespec-uk
``uk/policies/attendance_allowance_composed_amount_pipeline.yaml``, the
SI 2026/148 Schedule 1 Part III figures) against PolicyEngine-UK's
``attendance_allowance`` on a synthetic care-category grid at the 2026 validation
year. This is a ``rate_only`` surface: PolicyEngine-UK applies its
``gov.dwp.attendance_allowance`` rate table over a frozen ``aa_category`` FRS
input (higher / lower / none), so the comparison binds the rate schedule, not the
SSCBA 1992 s.64-66 needs assessment.

Both sides carry the same rate given the same supplied award category:

* PolicyEngine-UK's ``attendance_allowance`` = ``select([HIGHER, LOWER],
  [aa.higher, aa.lower], default=0) * WEEKS_IN_YEAR`` — the higher (£114.60) or
  lower (£76.70) weekly rate annualised over PE's ``WEEKS_IN_YEAR`` (52).
* The rulespec ``aa_pilot_weekly_amount`` selects the SI 2026/148 Schedule 1
  Part III weekly rate for the awarded category; this generator annualises it
  over the same 52 weeks (the period conversion PolicyEngine applies), so the
  compared annual amounts are on the same basis. The Axiom side is evaluated
  through the axiom rules engine (``AxiomRulesRunner``); its rate is the engine's,
  not a re-implementation.

The award category (higher / lower / none) is a frozen input on both engines, so
the grid isolates the rate schedule and matches to the penny (higher £5,959.20,
lower £3,988.40, none £0). PolicyEngine-UK carries monetary variables in float32,
so any residual is a sub-£0.01 representation artifact inside tolerance.

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_attendance_allowance_pe.py

On a runner without those, the committed dashboard report stands (the runner in
run_comparison.py reuses it), exactly like the Council Tax Reduction and Winter
Fuel Payment grids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from canonical_rulespec_runtime import parse_canonical_runtime_args

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
POLICYENGINE_UK_VERSION = "2.89.2"


#: Encoded program under comparison and its rate-given-category output.
AA_PROGRAM = "uk/policies/attendance_allowance_composed_amount_pipeline.yaml"
AA_BASE = "uk:policies/attendance_allowance_composed_amount_pipeline"
AA_OUTPUT = f"{AA_BASE}#aa_pilot_weekly_amount"
AA_CONCEPT = AA_OUTPUT
#: The engine returns and resolves derived outputs by their bare rule name; the
#: module-qualified ref is the concept label carried in the report.
AA_ENGINE_OUTPUT = "aa_pilot_weekly_amount"

#: The two award-category judgments the pipeline reads (bare rule names).
_AWARDED_HIGHER = "aa_pilot_awarded_higher_rate"
_AWARDED_LOWER = "aa_pilot_awarded_lower_rate"

#: PolicyEngine-UK variable read for the final compared output.
_PE_AWARD = "attendance_allowance"

#: PolicyEngine-UK annualises the weekly Attendance Allowance rate over
#: WEEKS_IN_YEAR (52); the rulespec pipeline exposes the weekly rate, so the
#: comparison annualises it over the same 52 weeks. A period conversion, not a
#: policy value.
_WEEKS_IN_YEAR = 52

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class AACase:
    """One synthetic Attendance Allowance claimant on the rate grid."""

    case_id: str
    pe_category: str
    awarded_higher: bool
    awarded_lower: bool
    scenario: str


def _grid() -> list[AACase]:
    """Attendance Allowance cases exercising the rate schedule by category.

    The higher rate (day-and-night attendance needs), the lower rate (day-or-night
    needs), and the no-award case. The award category is a frozen input on both
    engines (PolicyEngine's ``aa_category``, the pipeline's award judgments), so
    the grid binds the rate schedule.
    """

    return [
        AACase("uk-aa-higher-rate", "HIGHER", True, False, "higher-rate-day-and-night"),
        AACase("uk-aa-lower-rate", "LOWER", False, True, "lower-rate-day-or-night"),
        AACase("uk-aa-no-award", "NONE", False, False, "no-award"),
    ]


def _pe_situation(case: AACase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {
            "person": {
                "age": {year: 70},
                "aa_category": {year: case.pe_category},
            }
        },
        "benunits": {"bu": {"members": ["person"]}},
        "households": {"hh": {"members": ["person"]}},
    }


def _policyengine_awards(cases: list[AACase]) -> dict[str, float]:
    """PolicyEngine-UK ``attendance_allowance`` per case (annual amount)."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    awards: dict[str, float] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        awards[case.case_id] = float(sim.calculate(_PE_AWARD, year).sum())
    return awards


def _axiom_awards(
    cases: list[AACase],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    """Rulespec Attendance Allowance annual amount through the axiom rules engine.

    The pipeline exposes the weekly rate for the awarded category; this annualises
    it over PolicyEngine's WEEKS_IN_YEAR (52) so both sides are on the annual basis
    PolicyEngine reports.
    """

    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = rulespec_root / AA_PROGRAM

    axiom_cases: list[Case] = []
    for case in cases:
        axiom_cases.append(
            Case(
                case_id=case.case_id,
                period="2026-04-06",
                metadata={
                    "axiom_entity": "Person",
                    "axiom_entity_id": "person",
                    "axiom_inputs": {
                        _AWARDED_HIGHER: case.awarded_higher,
                        _AWARDED_LOWER: case.awarded_lower,
                    },
                },
                outputs=(AA_ENGINE_OUTPUT,),
            )
        )

    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=axiom_binary,
        default_entity="Person",
        default_entity_id="person",
        rulespec_root=rulespec_root,
        mode="explain",
    )
    results = runner.run_cases(axiom_cases, [AA_ENGINE_OUTPUT])
    awards: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        weekly = result.values.get(AA_ENGINE_OUTPUT)
        if weekly is None:
            weekly = result.values.get(AA_OUTPUT)
        if weekly is None:
            raise RuntimeError(
                f"axiom rules engine returned no Attendance Allowance rate for "
                f"{result.household_id}: keys={list(result.values)}"
            )
        awards[str(result.household_id)] = float(weekly) * _WEEKS_IN_YEAR
    return awards


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[AACase],
    pe_awards: dict[str, float],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_award = pe_awards[case.case_id]
        ax_award = axiom[case.case_id]
        ok = _match(ax_award, pe_award)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": AA_CONCEPT,
                "scenario": case.scenario,
                "aa_category": case.pe_category,
                "axiom": ax_award,
                "policyengine": pe_award,
                "axiom_vs_policyengine": {
                    "difference": ax_award - pe_award,
                    "match": ok,
                },
            }
        )
        if not ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": AA_CONCEPT,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax_award,
                    "right": pe_award,
                    "difference": ax_award - pe_award,
                }
            )
    n = len(cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-attendance-allowance-pe",
        "concept": AA_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {
            "axiom": AA_OUTPUT,
            "policyengine": _PE_AWARD,
        },
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
                [{"count": mismatch_count, "value": AA_CONCEPT}]
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
            "generator": "scripts/generate_uk_attendance_allowance_pe.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {AA_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "comparability": "rate_only",
            "commensurability": (
                "PolicyEngine-UK Attendance Allowance (gov.dwp.attendance_allowance: "
                "higher 114.60, lower 76.70 per week, annualised over WEEKS_IN_YEAR "
                "= 52) applies its rate table over a frozen aa_category input; the "
                "rulespec pipeline selects the SI 2026/148 Schedule 1 Part III weekly "
                "rate for the same supplied award category and this comparison "
                "annualises it over the same 52 weeks. The award category is a frozen "
                "input on both engines, so the grid binds the rate schedule, not the "
                "SSCBA 1992 s.64-66 needs assessment."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="uk")
    cases = _grid()
    pe_awards = _policyengine_awards(cases)
    axiom = _axiom_awards(
        cases,
        rulespec_root=rulespec_root,
        axiom_binary=axiom_binary,
    )
    report = build_report(cases, pe_awards, axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-attendance-allowance-pe"
    dated = REPORTS / f"{basename}-{report['provenance']['generated']}.json"
    dash = DASH_PUBLIC / f"{basename}.json"
    text = json.dumps(report, indent=2) + "\n"
    dated.write_text(text)
    dash.write_text(text)

    summary = report["summary"]
    print(
        f"uk-attendance-allowance-pe: {summary['match_count']}/"
        f"{report['case_count']} match "
        f"({summary['axiom_vs_policyengine_match_rate']}%)"
    )
    print(f"  report:    {dated.relative_to(REPO_ROOT)}")
    print(f"  dashboard: {dash.relative_to(REPO_ROOT)}")
    return 0 if summary["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
