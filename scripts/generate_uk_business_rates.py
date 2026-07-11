#!/usr/bin/env python3
"""Business rates incidence: rulespec-uk vs PolicyEngine-UK.

Compares the encoded business rates household incidence wrapper (rulespec-uk
``uk/policies/govuk/business-rates.yaml``, LGFA 1988 s.43 as enabling authority)
against PolicyEngine-UK's ``business_rates`` on a synthetic household grid at the
2026 validation year.

PolicyEngine-UK does not compute an individual ratepayer's bill; it models the
distributional incidence of non-domestic rates as the product of a household's
``shareholding`` (its fraction of aggregate corporate wealth) and the total
business rates revenue raised across the four nations
(``gov.hmrc.business_rates.statistics.revenue`` England + Scotland + Wales +
Northern Ireland). The rulespec module restates that same incidence model with
both quantities as supplied inputs.

The bridge feeds PolicyEngine's own ``shareholding`` and the held-forward total
revenue parameter as the rulespec supplied inputs, so both engines compute the
identical product and the grid matches to the penny (the only residuals are
sub-£0.01 PolicyEngine float32 artifacts on the large revenue magnitude).

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_business_rates.py
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


BR_PROGRAM = "uk/policies/govuk/business-rates.yaml"
BR_BASE = "uk:policies/govuk/business-rates"
BR_OUTPUT = f"{BR_BASE}#business_rates"
BR_CONCEPT = BR_OUTPUT

_SHAREHOLDING = f"{BR_BASE}#shareholding"
_TOTAL_REVENUE = f"{BR_BASE}#business_rates_total_revenue"

_PE_BR = "business_rates"
_PE_SHAREHOLDING = "shareholding"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class BRCase:
    """One synthetic household on the business rates incidence grid."""

    case_id: str
    shareholding: float
    scenario: str


def _grid() -> list[BRCase]:
    """Households spanning the shareholding range that scales the incidence."""

    return [
        BRCase("br-zero-shareholding", 0.0, "no-corporate-shareholding"),
        BRCase("br-tiny-shareholding", 1e-6, "very-small-shareholding"),
        BRCase("br-small-shareholding", 1e-5, "small-shareholding"),
        BRCase("br-mid-shareholding", 1e-4, "mid-shareholding"),
        BRCase("br-large-shareholding", 5e-4, "large-shareholding"),
        BRCase("br-larger-shareholding", 1e-3, "larger-shareholding"),
    ]


def _pe_situation(case: BRCase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {"person": {"age": {year: 40}}},
        "benunits": {"bu": {"members": ["person"]}},
        "households": {
            "hh": {
                "members": ["person"],
                "shareholding": {year: case.shareholding},
            }
        },
    }


def _policyengine_rows(cases: list[BRCase]) -> dict[str, dict[str, float]]:
    """PolicyEngine-UK business rates incidence plus the bridged inputs."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, dict[str, float]] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        revenue = sim.tax_benefit_system.parameters(
            f"{year}-04-06"
        ).gov.hmrc.business_rates.statistics.revenue
        total_revenue = float(
            revenue.ENGLAND
            + revenue.SCOTLAND
            + revenue.WALES
            + revenue.NORTHERN_IRELAND
        )
        rows[case.case_id] = {
            "business_rates": float(sim.calculate(_PE_BR, year).sum()),
            "shareholding": float(sim.calculate(_PE_SHAREHOLDING, year).sum()),
            "total_revenue": total_revenue,
        }
    return rows


def _axiom_amounts(
    cases: list[BRCase],
    pe_rows: dict[str, dict[str, float]],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    """Rulespec business rates incidence through the axiom rules engine."""

    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = rulespec_root / BR_PROGRAM

    axiom_cases: list[Case] = []
    for case in cases:
        row = pe_rows[case.case_id]
        axiom_cases.append(
            Case(
                case_id=case.case_id,
                period=str(VALIDATION_YEAR),
                metadata={
                    "axiom_entity": "Household",
                    "axiom_entity_id": "household",
                    "axiom_inputs": {
                        _SHAREHOLDING: row["shareholding"],
                        _TOTAL_REVENUE: row["total_revenue"],
                    },
                },
                outputs=(BR_OUTPUT,),
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
    results = runner.run_cases(axiom_cases, [BR_OUTPUT])
    amounts: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        amounts[str(result.household_id)] = float(result.values[BR_OUTPUT])
    return amounts


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[BRCase],
    pe_rows: dict[str, dict[str, float]],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_br = pe_rows[case.case_id]["business_rates"]
        ax_br = axiom[case.case_id]
        ok = _match(ax_br, pe_br)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": BR_CONCEPT,
                "scenario": case.scenario,
                "shareholding": pe_rows[case.case_id]["shareholding"],
                "total_revenue": pe_rows[case.case_id]["total_revenue"],
                "axiom": ax_br,
                "policyengine": pe_br,
                "axiom_vs_policyengine": {
                    "difference": ax_br - pe_br,
                    "match": ok,
                },
            }
        )
        if not ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": BR_CONCEPT,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax_br,
                    "right": pe_br,
                    "difference": ax_br - pe_br,
                }
            )
    n = len(cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-business-rates",
        "concept": BR_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {"axiom": BR_OUTPUT, "policyengine": _PE_BR},
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
                [{"count": mismatch_count, "value": BR_CONCEPT}]
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
            "generator": "scripts/generate_uk_business_rates.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {BR_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK business_rates (shareholding times total "
                "non-domestic rates revenue across England, Scotland, Wales and "
                "Northern Ireland) vs the rulespec LGFA 1988 s.43 incidence "
                "wrapper; shareholding and the total revenue are supplied inputs "
                "on both engines, bridged from PolicyEngine."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="uk")
    cases = _grid()
    pe_rows = _policyengine_rows(cases)
    axiom = _axiom_amounts(
        cases,
        pe_rows,
        rulespec_root=rulespec_root,
        axiom_binary=axiom_binary,
    )
    report = build_report(cases, pe_rows, axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-business-rates"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-business-rates: PE match "
        f"{summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{report['case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
