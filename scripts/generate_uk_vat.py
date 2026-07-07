#!/usr/bin/env python3
"""VAT case grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded VAT rate application (rulespec-uk
``uk/policies/govuk/vat.yaml``, VATA 1994 s.2(1) standard rate and s.29A
reduced rate) against PolicyEngine-UK's ``vat`` on a synthetic
household-consumption grid at the 2026 validation year.

Both sides are commensurable because ``vat`` is the same closed-form function of
the same supplied inputs on each engine:

* PolicyEngine-UK computes
  ``vat = (full_rate_vat_consumption * standard_rate
  + reduced_rate_vat_consumption * reduced_rate) / microdata_vat_coverage``
  where the two consumption buckets are household inputs (the Schedule 7A/8/9
  goods classification is applied upstream in the microdata) and
  ``microdata_vat_coverage`` grosses the liability up to HMRC receipts.
* The rulespec ``vat_annual_amount`` is the identical closed form of the same
  three supplied inputs (``full_rate_vat_consumption``,
  ``reduced_rate_vat_consumption``, ``microdata_vat_coverage``) with the rates
  grounded in VATA 1994 s.2(1) (20 per cent) and s.29A (5 per cent).

For each synthetic household this generator sets the two consumption buckets on
the PolicyEngine side, reads back PolicyEngine's ``vat`` and its resolved
``microdata_vat_coverage`` parameter, and feeds the same consumption split and
coverage factor as the rulespec supplied inputs, so both engines test the
identical rate arithmetic. The Axiom side is evaluated through the axiom rules
engine (``AxiomRulesRunner``); its numbers are the engine's, not a
re-implementation.

Because the two are the same statutory rates applied to the same supplied
consumption, the grid matches to the penny (standard-only, reduced-only, mixed,
zero, and grossed-up cases). The only residuals are sub-0.001 PolicyEngine
float32 artifacts, inside the tolerance.

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    RULESPEC_UK_CHECKOUT=/path/to/rulespec-uk \
      uv run python scripts/generate_uk_vat.py

On a runner without those, the committed dashboard report stands (the runner in
run_comparison.py reuses it), exactly like the council-tax-reduction grid.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
POLICYENGINE_UK_VERSION = "2.89.2"

RULESPEC_UK = Path(
    os.environ.get("RULESPEC_UK_CHECKOUT")
    or os.path.expanduser("~/TheAxiomFoundation/rulespec-uk")
)

VAT_PROGRAM = "uk/policies/govuk/vat.yaml"
VAT_BASE = "uk:policies/govuk/vat"
VAT_OUTPUT = f"{VAT_BASE}#vat_annual_amount"
VAT_CONCEPT = VAT_OUTPUT

_FULL = f"{VAT_BASE}#full_rate_vat_consumption"
_REDUCED = f"{VAT_BASE}#reduced_rate_vat_consumption"
_COVERAGE = f"{VAT_BASE}#microdata_vat_coverage"

_PE_VAT = "vat"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class VATCase:
    case_id: str
    full_rate_consumption: float
    reduced_rate_consumption: float
    scenario: str


def _grid() -> list[VATCase]:
    """Households exercising the two-rate VAT surface."""
    return [
        VATCase("vat-zero-consumption", 0.0, 0.0, "no-consumption"),
        VATCase("vat-standard-only-small", 5000.0, 0.0, "standard-rate-only"),
        VATCase("vat-standard-only-large", 24000.0, 0.0, "standard-rate-only"),
        VATCase("vat-reduced-only-small", 0.0, 1500.0, "reduced-rate-only"),
        VATCase("vat-reduced-only-large", 0.0, 6000.0, "reduced-rate-only"),
        VATCase("vat-mixed-typical", 14000.0, 2600.0, "standard-and-reduced"),
        VATCase("vat-mixed-high", 42000.0, 5200.0, "standard-and-reduced"),
        VATCase("vat-reduced-dominant", 3000.0, 9000.0, "reduced-heavy"),
        VATCase("vat-standard-dominant", 30000.0, 800.0, "standard-heavy"),
    ]


def _pe_situation(case: VATCase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {"person": {"age": {year: 40}}},
        "benunits": {"bu": {"members": ["person"]}},
        "households": {
            "hh": {
                "members": ["person"],
                "full_rate_vat_consumption": {year: case.full_rate_consumption},
                "reduced_rate_vat_consumption": {year: case.reduced_rate_consumption},
            }
        },
    }


def _policyengine_rows(cases: list[VATCase]) -> dict[str, dict[str, float]]:
    """PolicyEngine-UK vat plus the supplied inputs bridged into rulespec."""
    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, dict[str, float]] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        coverage = float(
            sim.tax_benefit_system.parameters(
                f"{year}-04-06"
            ).gov.simulation.microdata_vat_coverage
        )
        rows[case.case_id] = {
            "vat": float(sim.calculate(_PE_VAT, year).sum()),
            "full_rate_vat_consumption": float(
                sim.calculate("full_rate_vat_consumption", year).sum()
            ),
            "reduced_rate_vat_consumption": float(
                sim.calculate("reduced_rate_vat_consumption", year).sum()
            ),
            "microdata_vat_coverage": coverage,
        }
    return rows


def _axiom_awards(
    cases: list[VATCase], pe_rows: dict[str, dict[str, float]]
) -> dict[str, float]:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = RULESPEC_UK / VAT_PROGRAM
    binary = os.environ.get("AXIOM_RULES_ENGINE_BINARY")

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
                        _FULL: row["full_rate_vat_consumption"],
                        _REDUCED: row["reduced_rate_vat_consumption"],
                        _COVERAGE: row["microdata_vat_coverage"],
                    },
                },
                outputs=(VAT_OUTPUT,),
            )
        )

    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=binary,
        default_entity="Household",
        default_entity_id="household",
        rulespec_repo_roots=(RULESPEC_UK,),
        mode="explain",
    )
    results = runner.run_cases(axiom_cases, [VAT_OUTPUT])
    awards: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        awards[str(result.household_id)] = float(result.values[VAT_OUTPUT])
    return awards


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[VATCase],
    pe_rows: dict[str, dict[str, float]],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_vat = pe_rows[case.case_id]["vat"]
        ax_vat = axiom[case.case_id]
        ok = _match(ax_vat, pe_vat)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": VAT_CONCEPT,
                "scenario": case.scenario,
                "full_rate_vat_consumption": pe_rows[case.case_id][
                    "full_rate_vat_consumption"
                ],
                "reduced_rate_vat_consumption": pe_rows[case.case_id][
                    "reduced_rate_vat_consumption"
                ],
                "microdata_vat_coverage": pe_rows[case.case_id][
                    "microdata_vat_coverage"
                ],
                "axiom": ax_vat,
                "policyengine": pe_vat,
                "axiom_vs_policyengine": {
                    "difference": ax_vat - pe_vat,
                    "match": ok,
                },
            }
        )
        if not ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": VAT_CONCEPT,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax_vat,
                    "right": pe_vat,
                    "difference": ax_vat - pe_vat,
                }
            )
    n = len(cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-vat",
        "concept": VAT_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {"axiom": VAT_OUTPUT, "policyengine": _PE_VAT},
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
                [{"count": mismatch_count, "value": VAT_CONCEPT}]
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
            "generator": "scripts/generate_uk_vat.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {VAT_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK vat = (full_rate_vat_consumption * standard_rate "
                "+ reduced_rate_vat_consumption * reduced_rate) / "
                "microdata_vat_coverage; the rulespec vat_annual_amount is the "
                "identical closed form with the rates grounded in VATA 1994 "
                "s.2(1) (20 per cent) and s.29A (5 per cent). The consumption "
                "split and the microdata_vat_coverage factor are supplied on both "
                "sides (PolicyEngine household inputs and "
                "gov.simulation.microdata_vat_coverage)."
            ),
        },
    }


def main() -> int:
    cases = _grid()
    pe_rows = _policyengine_rows(cases)
    axiom = _axiom_awards(cases, pe_rows)
    report = build_report(cases, pe_rows, axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-vat"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-vat: PE match {summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{report['case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
