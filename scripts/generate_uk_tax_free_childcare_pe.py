#!/usr/bin/env python3
"""Tax-Free Childcare top-up grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded Tax-Free Childcare top-up (rulespec-uk
``uk/policies/tax_free_childcare_composed_top_up_pipeline.yaml``, the Childcare
Payments Act 2014 section 1 25%-of-qualifying-payment top-up) against
PolicyEngine-UK's ``tax_free_childcare`` on a synthetic eligible-household grid at
the 2026 validation year.

Both sides compute the same top-up on the same supplied qualifying childcare
payment, and the coverage matrix's "PE frames the rate as 20% vs statute 25%"
question is resolved here: they are the SAME top-up on different bases.

* PolicyEngine-UK's ``tax_free_childcare`` = ``min(eligible_childcare_expense *
  rate / (1 - rate), cap)`` with ``rate = 0.20``, which grosses ``rate / (1 -
  rate)`` up to 0.25 — i.e. 25% of the qualifying childcare payment (the amount
  the parent pays), capped at the per-child entitlement-period maximum.
* The rulespec ``tfc_pilot_top_up_amount`` is the CPA 2014 s.1 top-up: 25% of the
  supplied qualifying childcare payment. The Axiom side is evaluated through the
  axiom rules engine (``AxiomRulesRunner``); its rate is the engine's, not a
  re-implementation.

Scope: the grid stays BELOW the per-child entitlement-period cap (£2,000/year
standard, reached at a qualifying payment of £8,000), which is a separate
parameter not encoded in the pipeline (not yet in the ingested corpus), so on
this grid PolicyEngine's ``min(..., cap)`` reduces to the uncapped 25% top-up and
the two sides match to the penny (£2,000 payment → £500, £4,000 → £1,000, £6,000
→ £1,500). Eligibility (working parents, adjusted net income below £100,000, a
qualifying child using a qualifying provider) is established in the PolicyEngine
situation and supplied to the rulespec pipeline as the qualifying payment.

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_tax_free_childcare_pe.py

On a runner without those, the committed dashboard report stands (the runner in
run_comparison.py reuses it), exactly like the other UK case grids.
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


AA_PROGRAM = "uk/policies/tax_free_childcare_composed_top_up_pipeline.yaml"
TFC_BASE = "uk:policies/tax_free_childcare_composed_top_up_pipeline"
TFC_OUTPUT = f"{TFC_BASE}#tfc_pilot_top_up_amount"
TFC_CONCEPT = TFC_OUTPUT
#: The engine resolves derived outputs by their bare rule name; the
#: module-qualified ref is the concept label carried in the report.
TFC_ENGINE_OUTPUT = "tfc_pilot_top_up_amount"
_QUALIFYING_PAYMENT = "tfc_pilot_qualifying_childcare_payment"

#: PolicyEngine-UK variable read for the final compared output.
_PE_AWARD = "tax_free_childcare"

#: The per-child standard entitlement-period cap is £2,000/year, reached at a
#: qualifying payment of £8,000 (25% top-up). The grid stays clear of it.
_CAP_BINDING_PAYMENT = 8_000.0

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class TFCCase:
    """One synthetic eligible household on the Tax-Free Childcare grid."""

    case_id: str
    qualifying_payment: float
    scenario: str


def _grid() -> list[TFCCase]:
    """Eligible households with below-cap qualifying childcare payments.

    Each case is a working couple with one qualifying child using a qualifying
    provider (adjusted net income below the £100,000 eligibility limit), with a
    qualifying childcare payment below the £8,000 that would reach the £2,000
    per-child cap. The top-up is then exactly 25% of the payment on both engines.
    """

    return [
        TFCCase("uk-tfc-payment2000", 2_000.0, "quarter-cap-below"),
        TFCCase("uk-tfc-payment4000", 4_000.0, "half-cap"),
        TFCCase("uk-tfc-payment6000", 6_000.0, "three-quarter-cap"),
    ]


def _pe_situation(case: TFCCase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {
            "parent1": {"age": {year: 35}, "employment_income": {year: 30_000}},
            "parent2": {"age": {year: 34}, "employment_income": {year: 30_000}},
            "child": {
                "age": {year: 3},
                "childcare_expenses": {year: case.qualifying_payment},
                "tax_free_childcare_uses_qualifying_provider": {year: True},
            },
        },
        "benunits": {"bu": {"members": ["parent1", "parent2", "child"]}},
        "households": {"hh": {"members": ["parent1", "parent2", "child"]}},
    }


def _policyengine_awards(cases: list[TFCCase]) -> dict[str, float]:
    """PolicyEngine-UK ``tax_free_childcare`` per case (annual top-up)."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    awards: dict[str, float] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        awards[case.case_id] = float(sim.calculate(_PE_AWARD, year).sum())
    return awards


def _axiom_awards(
    cases: list[TFCCase],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    """Rulespec Tax-Free Childcare top-up through the axiom rules engine."""

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
                        _QUALIFYING_PAYMENT: case.qualifying_payment,
                    },
                },
                outputs=(TFC_ENGINE_OUTPUT,),
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
    results = runner.run_cases(axiom_cases, [TFC_ENGINE_OUTPUT])
    awards: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        value = result.values.get(TFC_ENGINE_OUTPUT)
        if value is None:
            value = result.values.get(TFC_OUTPUT)
        if value is None:
            raise RuntimeError(
                f"axiom rules engine returned no Tax-Free Childcare top-up for "
                f"{result.household_id}: keys={list(result.values)}"
            )
        awards[str(result.household_id)] = float(value)
    return awards


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[TFCCase],
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
                "concept": TFC_CONCEPT,
                "scenario": case.scenario,
                "qualifying_payment": case.qualifying_payment,
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
                    "concept": TFC_CONCEPT,
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
        "suite": "uk-tax-free-childcare-pe",
        "concept": TFC_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {
            "axiom": TFC_OUTPUT,
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
                [{"count": mismatch_count, "value": TFC_CONCEPT}]
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
            "generator": "scripts/generate_uk_tax_free_childcare_pe.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {AA_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK Tax-Free Childcare (gov.hmrc.tax_free_childcare: "
                "contribution.rate 0.20 grossed up via rate / (1 - rate) = 0.25 on "
                "the qualifying childcare payment, then min with the per-child cap) "
                "vs the Childcare Payments Act 2014 s.1 25%-of-qualifying-payment "
                "top-up. The grid stays below the £8,000 payment at which the "
                "£2,000 per-child cap binds, so PolicyEngine's min(..., cap) reduces "
                "to the uncapped 25% top-up; the qualifying payment is a supplied "
                "input on both engines. The per-child entitlement-period cap is a "
                "separate parameter not encoded in the pipeline (not yet in corpus) "
                "and is out of scope."
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
    basename = "axiom-policyengine-uk-tax-free-childcare-pe"
    dated = REPORTS / f"{basename}-{report['provenance']['generated']}.json"
    dash = DASH_PUBLIC / f"{basename}.json"
    text = json.dumps(report, indent=2) + "\n"
    dated.write_text(text)
    dash.write_text(text)

    summary = report["summary"]
    print(
        f"uk-tax-free-childcare-pe: {summary['match_count']}/"
        f"{report['case_count']} match "
        f"({summary['axiom_vs_policyengine_match_rate']}%)"
    )
    print(f"  report:    {dated.relative_to(REPO_ROOT)}")
    print(f"  dashboard: {dash.relative_to(REPO_ROOT)}")
    return 0 if summary["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
