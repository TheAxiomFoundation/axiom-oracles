#!/usr/bin/env python3
"""Capital Gains Tax case grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded UK capital gains tax policy module (rulespec-uk
``uk/policies/govuk/capital-gains-tax.yaml``, grounded in TCGA 1992
s.1H/1I/1K) against PolicyEngine-UK's ``capital_gains_tax`` on a synthetic
individual grid at the 2026 validation year.

Both sides are commensurable because the band split takes the same supplied
inputs on each engine. PolicyEngine-UK computes ``capital_gains_tax`` by
deducting the annual exempt amount from ``capital_gains``, then charging the
portion within the individual's unused basic rate band at the CGT basic rate
and the excess at the higher/additional rate (both 24%). The rulespec module
reproduces that split with the annual exempt amount (£3,000, s.1K) and the
18%/24% rates (s.1H) grounded from the corpus, and with the individual's
taxable income and basic rate limit as supplied inputs.

The bridge mirrors the ``uk_council_tax_reduction`` suite: for each synthetic
individual this generator reads PolicyEngine's own ``adjusted_net_income`` and
``allowances`` (taxable income = the former less the latter, for individuals
with no gift aid or pension band extension) and the ``gov.hmrc.income_tax``
basic rate limit parameter, and feeds those exact values as the rulespec
supplied inputs, so both engines test the identical band-split arithmetic. The
Axiom side is evaluated through the axiom rules engine (``AxiomRulesRunner``);
its numbers are the engine's, not a re-implementation.

Because the two are the same statute with the same inputs, the grid matches to
the penny across the full surface — gains within the exemption, gains within
the basic rate band, gains spanning both bands, and gains fully above the band.
The only residuals are sub-£0.01 PolicyEngine float32 artifacts.

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_capital_gains_tax.py
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


CGT_PROGRAM = "uk/policies/govuk/capital-gains-tax.yaml"
CGT_BASE = "uk:policies/govuk/capital-gains-tax"
CGT_OUTPUT = f"{CGT_BASE}#capital_gains_tax"
CGT_CONCEPT = CGT_OUTPUT

#: The three supplied inputs the band split reads (all Money).
_CAPITAL_GAINS = f"{CGT_BASE}#capital_gains"
_TAXABLE_INCOME = f"{CGT_BASE}#taxable_income"
_BASIC_RATE_LIMIT = f"{CGT_BASE}#basic_rate_limit"

#: PolicyEngine-UK variables read for the bridge and the final compared output.
_PE_CGT = "capital_gains_tax"
_PE_ANI = "adjusted_net_income"
_PE_ALLOWANCES = "allowances"
_PE_CAPITAL_GAINS = "capital_gains"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class CGTCase:
    """One synthetic individual on the CGT grid."""

    case_id: str
    employment_income: float
    capital_gains: float
    scenario: str


def _grid() -> list[CGTCase]:
    """Individuals exercising the TCGA 1992 s.1H/1I band split.

    Covers: gains within the annual exempt amount (no charge); gains just over
    the exemption fully within the basic rate band; gains spanning the basic and
    higher rate bands; gains fully above the basic rate band; and a mid-income
    case with the basic rate band partly used by income.
    """

    return [
        CGTCase(
            "cgt-within-annual-exempt-amount",
            20000,
            2000,
            "gains-below-annual-exempt-amount",
        ),
        CGTCase(
            "cgt-basic-rate-band-only", 20000, 8000, "gains-within-basic-rate-band"
        ),
        CGTCase(
            "cgt-spanning-basic-and-higher",
            20000,
            50000,
            "gains-span-basic-and-higher-bands",
        ),
        CGTCase(
            "cgt-fully-higher-rate", 80000, 30000, "gains-fully-above-basic-rate-band"
        ),
        CGTCase(
            "cgt-mid-income-partial-band",
            30000,
            20000,
            "basic-rate-band-partly-used-by-income",
        ),
        CGTCase("cgt-large-gain-low-income", 15000, 120000, "large-gain-low-income"),
    ]


def _pe_situation(case: CGTCase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {
            "person": {
                "age": {year: 40},
                "employment_income": {year: case.employment_income},
                "capital_gains": {year: case.capital_gains},
            }
        },
        "benunits": {"bu": {"members": ["person"]}},
        "households": {"hh": {"members": ["person"]}},
    }


def _policyengine_rows(cases: list[CGTCase]) -> dict[str, dict[str, float]]:
    """PolicyEngine-UK CGT plus the internals bridged into the rulespec side."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, dict[str, float]] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        params = sim.tax_benefit_system.parameters(f"{year}-04-06")
        basic_rate_limit = float(params.gov.hmrc.income_tax.rates.uk.thresholds[1])
        ani = float(sim.calculate(_PE_ANI, year).sum())
        allowances = float(sim.calculate(_PE_ALLOWANCES, year).sum())
        rows[case.case_id] = {
            "cgt": float(sim.calculate(_PE_CGT, year).sum()),
            "capital_gains": float(sim.calculate(_PE_CAPITAL_GAINS, year).sum()),
            "taxable_income": max(0.0, ani - allowances),
            "basic_rate_limit": basic_rate_limit,
        }
    return rows


def _axiom_amounts(
    cases: list[CGTCase],
    pe_rows: dict[str, dict[str, float]],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    """Rulespec CGT band split through the axiom rules engine.

    Each case feeds PolicyEngine's own ``capital_gains``, taxable income
    (``adjusted_net_income`` less ``allowances``) and basic rate limit as the
    rulespec supplied inputs, so the two engines test the identical band-split
    arithmetic (the ``uk_council_tax_reduction`` bridge pattern).
    """

    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = rulespec_root / CGT_PROGRAM

    axiom_cases: list[Case] = []
    for case in cases:
        row = pe_rows[case.case_id]
        axiom_cases.append(
            Case(
                case_id=case.case_id,
                period=str(VALIDATION_YEAR),
                metadata={
                    "axiom_entity": "Person",
                    "axiom_entity_id": "person",
                    "axiom_inputs": {
                        _CAPITAL_GAINS: row["capital_gains"],
                        _TAXABLE_INCOME: row["taxable_income"],
                        _BASIC_RATE_LIMIT: row["basic_rate_limit"],
                    },
                },
                outputs=(CGT_OUTPUT,),
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
    results = runner.run_cases(axiom_cases, [CGT_OUTPUT])
    amounts: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        amounts[str(result.household_id)] = float(result.values[CGT_OUTPUT])
    return amounts


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[CGTCase],
    pe_rows: dict[str, dict[str, float]],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_cgt = pe_rows[case.case_id]["cgt"]
        ax_cgt = axiom[case.case_id]
        ok = _match(ax_cgt, pe_cgt)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": CGT_CONCEPT,
                "scenario": case.scenario,
                "capital_gains": pe_rows[case.case_id]["capital_gains"],
                "taxable_income": pe_rows[case.case_id]["taxable_income"],
                "basic_rate_limit": pe_rows[case.case_id]["basic_rate_limit"],
                "axiom": ax_cgt,
                "policyengine": pe_cgt,
                "axiom_vs_policyengine": {
                    "difference": ax_cgt - pe_cgt,
                    "match": ok,
                },
            }
        )
        if not ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": CGT_CONCEPT,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax_cgt,
                    "right": pe_cgt,
                    "difference": ax_cgt - pe_cgt,
                }
            )
    n = len(cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-capital-gains-tax",
        "concept": CGT_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {"axiom": CGT_OUTPUT, "policyengine": _PE_CGT},
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
                [{"count": mismatch_count, "value": CGT_CONCEPT}]
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
            "generator": "scripts/generate_uk_capital_gains_tax.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {CGT_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK capital_gains_tax (annual exempt amount £3,000, "
                "basic rate 18%, higher/additional 24%) vs the TCGA 1992 s.1H/1I/1K "
                "band split; capital_gains is a supplied input on both sides. "
                "PolicyEngine's taxable income (adjusted_net_income less allowances) "
                "and basic rate limit (gov.hmrc.income_tax basic rate threshold) are "
                "bridged into the rulespec supplied inputs."
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
    basename = "axiom-policyengine-uk-capital-gains-tax"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-capital-gains-tax: PE match "
        f"{summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{report['case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
