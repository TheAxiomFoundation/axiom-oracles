#!/usr/bin/env python3
"""US tariff duty T0 grid: rulespec-us duty spine vs frozen USITC statutory rates.

Companion to TheAxiomFoundation/rulespec-us#1190 and
TheAxiomFoundation/axiom-oracles#444. Runs the 40 frozen grid cases from
``axiom_oracles.suites.us_tariff`` — (HTS-10 line, origin country, customs
value, entry date, postal flag) — through the composed rulespec-us pipeline
``us:policies/cbp/us-tariff-duty/composition#us_tariff_duty`` (evaluated by
the axiom rules engine) and grades the result against duty amounts frozen
directly from the official USITC HTS editions retained in axiom-corpus (2026
Rev 3 / 4 / 12 / 14 plus the Rev 14 chapter-99 notes) and the controlling
Federal Register instruments. The reference engine is the statute itself:
every expected duty is a hand-verified statutory computation whose components
each cite a retained corpus artifact (``rate_components`` in the suite and in
each report row).

Temporal design: one grid date per retained HTS revision window
(2026-02-15 / 03-15 / 07-23 / 08-01) straddling the 2026-02-24 IEEPA
termination (EO 14389) and the 2026-07-24 §122 sunset + CBP postal
informal-entry cutover — the engine's ``effective_from``/``effective_to``
version selection is what is under test, not just the rates.

Run locally (needs a built axiom rules engine and the rulespec-us checkout
with the us-tariff-duty spine)::

    RULESPEC_US_CHECKOUT=/path/to/rulespec-us \
      uv run python scripts/generate_us_tariff.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.suites.us_tariff import (  # noqa: E402
    COMPOSITION_MODULE,
    FROZEN_GRID,
    US_SCOPE,
    US_TARIFF_DUTY,
    us_tariff_cases,
)

RULESPEC_US = Path(
    os.environ.get("RULESPEC_US_CHECKOUT")
    or os.path.expanduser("~/TheAxiomFoundation/rulespec-us")
)

COMPOSITION_PATH = "us/policies/cbp/us-tariff-duty/composition.yaml"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

BASENAME = "axiom-usitc-us-tariff"
VALIDATION_YEAR = 2026


def _axiom_duties() -> dict[str, float]:
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner

    program = RULESPEC_US / COMPOSITION_PATH
    if not program.exists():
        raise FileNotFoundError(
            f"composition module not found: {program} "
            "(set RULESPEC_US_CHECKOUT to a rulespec-us checkout with the "
            "us-tariff-duty spine)"
        )
    binary = os.environ.get("AXIOM_RULES_ENGINE_BINARY")

    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=binary,
        default_entity="CustomsEntry",
        default_entity_id="entry",
        rulespec_repo_roots=(RULESPEC_US,),
        mode="explain",
    )
    results = runner.run_cases(us_tariff_cases(), [US_TARIFF_DUTY])
    duties: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: "
                f"{result.errors}"
            )
        duties[str(result.household_id)] = float(result.values[US_TARIFF_DUTY])
    return duties


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(axiom: dict[str, float]) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    scenario_mismatches: dict[str, int] = {}
    for cell in FROZEN_GRID:
        expected = cell.expected_duty
        ax_val = axiom[cell.case_id]
        ok = _match(ax_val, expected)
        scenario = "postal" if cell.is_postal else "line-entry"
        report_cases.append(
            {
                "case_id": cell.case_id,
                "concept": US_TARIFF_DUTY,
                "scenario": scenario,
                "entry_date": cell.entry_date,
                "hts_number": cell.hts_number,
                "country_of_origin": cell.origin,
                "customs_value": cell.customs_value,
                "is_postal_shipment": cell.is_postal,
                "expected_rate": cell.expected_rate,
                "rate_components": list(cell.rate_components),
                "axiom": ax_val,
                "usitc_statutory": expected,
                "axiom_vs_usitc_statutory": {
                    "difference": ax_val - expected,
                    "match": ok,
                },
            }
        )
        if not ok:
            scenario_mismatches[scenario] = scenario_mismatches.get(scenario, 0) + 1
            mismatches.append(
                {
                    "case_id": cell.case_id,
                    "concept": US_TARIFF_DUTY,
                    "kind": "amount_difference",
                    "engines": ["axiom", "usitc_statutory"],
                    "left_engine": "axiom",
                    "right_engine": "usitc_statutory",
                    "left": ax_val,
                    "right": expected,
                    "difference": ax_val - expected,
                }
            )
    n = len(FROZEN_GRID)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * match_count / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "us-tariff",
        "concept": US_TARIFF_DUTY,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["US"],
        "scope": US_SCOPE,
        "engines": {
            "axiom": US_TARIFF_DUTY,
            "usitc_statutory": "USITC HTS 2026 Rev3/4/12/14 + FR instruments (frozen statutory computation)",
        },
        "tolerance": {"absolute": _TOLERANCE, "relative": _RELATIVE_TOLERANCE},
        "case_count": n,
        "summary": {
            "comparison_count": n,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "axiom_vs_usitc_statutory_match_rate": match_rate,
            "usitc_statutory_matches": match_count,
            "weighted": {
                "comparison_weight": n,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
                "match_rate": match_rate,
            },
            "mismatches_by_concept": (
                [{"count": mismatch_count, "value": US_TARIFF_DUTY}]
                if mismatch_count
                else []
            ),
            "mismatches_by_kind": (
                [{"count": mismatch_count, "value": "amount_difference"}]
                if mismatch_count
                else []
            ),
            "mismatches_by_scenario": [
                {"count": count, "value": scenario}
                for scenario, count in sorted(scenario_mismatches.items())
            ],
            "error_count": 0,
            "errors_by_engine": [],
        },
        "mismatches": mismatches,
        "errors": [],
        "cases": report_cases,
        "provenance": {
            "generated": datetime.now(timezone.utc).date().isoformat(),
            "generator": "scripts/generate_us_tariff.py",
            "axiom_engine": (
                f"axiom rules engine over rulespec-us {COMPOSITION_PATH} "
                f"({COMPOSITION_MODULE})"
            ),
            "reference": (
                "Frozen statutory duty computations from the USITC HTS 2026 "
                "Rev 3 / 4 / 12 / 14 editions retained in axiom-corpus "
                "(axiom-corpus PR #557) and the controlling Federal Register "
                "instruments (EO 14389 IEEPA termination, §122 proclamation "
                "2026-03824, FR 2026-14542 Brazil-301, FR 2026-15181/-15274 "
                "forced-labor 301, CBP IFRs 2026-12669/-12670). Each case row "
                "carries its component-level citations in rate_components."
            ),
            "commensurability": (
                "Both sides are the same closed form of the same supplied "
                "inputs: an ad valorem duty (or the 2026-02-24..07-23 postal "
                "flat 10% in lieu) on a supplied customs value for one HTS-10 "
                "line, origin, and entry date. The reference side multiplies "
                "the hand-verified statutory rate stack by the customs value; "
                "the axiom side composes the encoded MFN/special rate and "
                "overlay contributions and applies the same customs value, so "
                "any difference is an encoding defect, not a modelling gap."
            ),
        },
    }


def main() -> int:
    axiom = _axiom_duties()
    report = build_report(axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    (REPORTS / f"{BASENAME}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{BASENAME}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"us-tariff: statutory match {summary['axiom_vs_usitc_statutory_match_rate']}% "
        f"({summary['usitc_statutory_matches']}/{report['case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
