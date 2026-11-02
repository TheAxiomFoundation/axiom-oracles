#!/usr/bin/env python3
"""Winter Fuel Payment case grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded England-and-Wales Winter Fuel Payment award pipeline
(rulespec-uk ``uk/policies/winter_fuel_payment_composed_award_pipeline.yaml``,
the SI 2025/969 regulation 3 standard amounts with the 2024/25 income-recovery
means test) against PolicyEngine-UK's ``winter_fuel_allowance`` on a synthetic
England pensioner-household grid at the 2026 validation year.

Both sides are commensurable because Winter Fuel is a benefit-unit amount driven
by the same three judgments on each engine:

* PolicyEngine-UK's ``winter_fuel_allowance`` pays ``gov.dwp.winter_fuel_payment``
  amount ``higher``/``lower`` (£300 at/over the higher-age requirement of 80, £200
  below it) to a household containing a state-pension-age member, gated since
  2024/25 on a means test: from 2025 an England/Wales pensioner passes when
  ``total_income`` is below ``maximum_taxable_income`` (£35,000, SI 2025/969), and
  the award is zeroed in Scotland (the devolved Pension Age Winter Heating Payment
  runs separately). Verified from the pinned 2.89.2 parameter tree: ``amount.lower``
  200, ``amount.higher`` 300, ``eligibility.taxable_income_test.maximum_taxable_income``
  35_000 from 2025-01-01, ``require_benefits`` true from 2024-01-01,
  ``higher_age_requirement`` 80.
* The rulespec award ``wfp_pilot_award_amount`` is a closed-form function of three
  supplied benefit-unit judgments — ``wfp_pilot_has_pension_age_member``,
  ``wfp_pilot_any_member_aged_80_or_over`` and
  ``wfp_pilot_income_below_recovery_threshold`` — over the SI 2025/969 reg 3(1)/3(4)
  standard amounts (£200/£300). The pipeline is scoped to the England-and-Wales
  standard amounts only, so the grid is England-and-Wales (a pension-age head in
  an English region); Scotland is out of the pipeline's scope and is not placed.

The bridge mirrors the ``generate_uk_council_tax_reduction`` grid: each synthetic
household's age/income facts drive PolicyEngine directly, and the same facts
determine the three judgments supplied to the rulespec pipeline, so both engines
test the identical unit. The Axiom side is evaluated through the axiom rules
engine (``AxiomRulesRunner``); its numbers are the engine's, not a
re-implementation.

Because the two schemes carry the same SI 2025/969 amounts and the same
income/age gating on the same supplied unit, the grid matches to the penny across
the award surface — the £200 under-80 and £300 at-80 tiers, the household (non
per-member) allocation for couples, the £35,000 income-recovery withdrawal, and
the state-pension-age gate. PolicyEngine-UK carries monetary variables in float32,
so any residual is a sub-£0.01 representation artifact inside tolerance.

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_winter_fuel_payment_pe.py

On a runner without those, the committed dashboard report stands (the runner in
run_comparison.py reuses it), exactly like the Council Tax Reduction grid.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
POLICYENGINE_UK_VERSION = "2.89.2"

#: rulespec-uk checkout (the encoded Winter Fuel pipeline + companion tests).
#: Resolves from the environment, then the org-mirror default.
RULESPEC_UK = Path(
    os.environ.get("RULESPEC_UK_CHECKOUT")
    or os.path.expanduser("~/TheAxiomFoundation/rulespec-uk")
)

#: Encoded program under comparison and its final award output.
WFP_PROGRAM = "uk/policies/winter_fuel_payment_composed_award_pipeline.yaml"
WFP_BASE = "uk:policies/winter_fuel_payment_composed_award_pipeline"
WFP_OUTPUT = f"{WFP_BASE}#wfp_pilot_award_amount"
WFP_CONCEPT = WFP_OUTPUT

#: The three supplied benefit-unit judgments the award reads (bare rule names —
#: the pipeline references them as external inputs, not module-qualified rules).
_HAS_PENSION_AGE = "wfp_pilot_has_pension_age_member"
_ANY_80 = "wfp_pilot_any_member_aged_80_or_over"
_INCOME_BELOW = "wfp_pilot_income_below_recovery_threshold"

#: PolicyEngine-UK variable read for the final compared output.
_PE_AWARD = "winter_fuel_allowance"

#: The SI 2025/969 income-recovery threshold: £35,000 annual taxable income
#: (PE-UK ``maximum_taxable_income`` from 2025-01-01). A household with a
#: pension-age member below it passes the England/Wales income passport.
_RECOVERY_THRESHOLD_ANNUAL = 35_000.0

#: State-pension-age boundary (PE-UK 2026 uses 66; 67 is above it, 60 below).
_AGE_REACHED_PENSION = 67
_AGE_PARTNER_REACHED_PENSION = 66
_AGE_80 = 82
_AGE_BELOW_PENSION = 60

#: Comparison tolerance — matches the CTR grid and the EFRS suites' pound
#: tolerance; PE-UK float32 monetary carry needs a small relative slack.
_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class WFPCase:
    """One synthetic England pensioner household on the Winter Fuel grid."""

    case_id: str
    head_age: int
    partner_age: int | None
    head_income: float
    scenario: str


def _grid() -> list[WFPCase]:
    """England pensioner households exercising the SI 2025/969 award surface.

    Covers: the £200 under-80 and £300 at-80 tiers; the household (non
    per-member) allocation for a couple (a couple both under 80 receives £200,
    not £400; a couple with one member 80+ takes the £300 tier for the whole
    unit); the £35,000 income-recovery withdrawal (below pays, above is nil);
    and the state-pension-age gate (a below-pension-age claimant receives nil).
    Income points sit clear of the £35,000 boundary (£30,000 below, £42,000
    above) so the strict-inequality float boundary is not exercised.
    """

    return [
        WFPCase("uk-wfp-single-under80", _AGE_REACHED_PENSION, None, 0.0,
                "under-80-single-200"),
        WFPCase("uk-wfp-single-age80", _AGE_80, None, 0.0,
                "age-80-single-300"),
        WFPCase("uk-wfp-couple-under80", _AGE_REACHED_PENSION,
                _AGE_PARTNER_REACHED_PENSION, 0.0, "under-80-couple-200"),
        WFPCase("uk-wfp-couple-one-age80", _AGE_80,
                _AGE_PARTNER_REACHED_PENSION, 0.0, "age-80-couple-300"),
        WFPCase("uk-wfp-single-income30000-below-threshold",
                _AGE_REACHED_PENSION, None, 30_000.0,
                "income-below-recovery-threshold-pays"),
        WFPCase("uk-wfp-single-income42000-above-threshold",
                _AGE_REACHED_PENSION, None, 42_000.0,
                "income-above-recovery-threshold-withdrawn"),
        WFPCase("uk-wfp-single-below-pension-age", _AGE_BELOW_PENSION, None,
                0.0, "below-state-pension-age-nil"),
    ]


def _pe_situation(case: WFPCase) -> dict:
    year = VALIDATION_YEAR
    people = {
        "person": {
            "age": {year: case.head_age},
            "employment_income": {year: case.head_income},
        }
    }
    members = ["person"]
    if case.partner_age is not None:
        people["partner"] = {
            "age": {year: case.partner_age},
            "employment_income": {year: 0},
        }
        members = ["person", "partner"]
    return {
        "people": people,
        "benunits": {"bu": {"members": members}},
        "households": {
            "hh": {
                "members": members,
                # England-and-Wales scope: an English region keeps the household
                # on the SI 2025/969 standard amounts (Scotland runs the devolved
                # PAWHP and PE zeroes winter_fuel_allowance there).
                "country": {year: "ENGLAND"},
                "region": {year: "LONDON"},
            }
        },
    }


def _judgments(case: WFPCase) -> dict[str, bool]:
    """The three benefit-unit judgments, from the same facts PE reads.

    ``has_pension_age_member`` — any member has reached state pension age (66);
    ``any_member_aged_80_or_over`` — any member is 80+ (the higher-amount tier);
    ``income_below_recovery_threshold`` — household taxable income is below the
    £35,000 SI 2025/969 recovery threshold (the England/Wales income passport).
    """

    ages = [case.head_age] + (
        [case.partner_age] if case.partner_age is not None else []
    )
    return {
        _HAS_PENSION_AGE: any(a >= 66 for a in ages),
        _ANY_80: any(a >= 80 for a in ages),
        _INCOME_BELOW: case.head_income < _RECOVERY_THRESHOLD_ANNUAL,
    }


def _policyengine_awards(cases: list[WFPCase]) -> dict[str, float]:
    """PolicyEngine-UK ``winter_fuel_allowance`` per case (household amount)."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    awards: dict[str, float] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        awards[case.case_id] = float(sim.calculate(_PE_AWARD, year).sum())
    return awards


def _axiom_awards(cases: list[WFPCase]) -> dict[str, float]:
    """Rulespec Winter Fuel award through the axiom rules engine.

    Each case supplies the three benefit-unit judgments (derived from the same
    age/income facts PolicyEngine reads) as the pipeline's inputs, so the two
    engines test the identical unit (the CTR / uk_pension_credit bridge pattern).
    """

    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = RULESPEC_UK / WFP_PROGRAM
    binary = os.environ.get("AXIOM_RULES_ENGINE_BINARY")

    axiom_cases: list[Case] = []
    for case in cases:
        axiom_cases.append(
            Case(
                case_id=case.case_id,
                # The UK 2026-27 fiscal year starts 6 April 2026; the #194 guard
                # requires UK suites to evaluate on/after that boundary.
                period="2026-04-06",
                metadata={
                    "axiom_entity": "Family",
                    "axiom_entity_id": "benefit_unit",
                    "axiom_inputs": _judgments(case),
                },
                outputs=(WFP_OUTPUT,),
            )
        )

    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=binary,
        default_entity="Family",
        default_entity_id="benefit_unit",
        rulespec_repo_roots=(RULESPEC_UK,),
        mode="explain",
    )
    results = runner.run_cases(axiom_cases, [WFP_OUTPUT])
    awards: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: "
                f"{result.errors}"
            )
        # The engine returns the award under either the full ref or the bare
        # rule name depending on the compiled artifact's aliasing.
        value = result.values.get(WFP_OUTPUT)
        if value is None:
            value = result.values.get("wfp_pilot_award_amount")
        if value is None:
            raise RuntimeError(
                f"axiom rules engine returned no Winter Fuel award for "
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
    cases: list[WFPCase],
    pe_awards: dict[str, float],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_award = pe_awards[case.case_id]
        ax_award = axiom[case.case_id]
        judgments = _judgments(case)
        ok = _match(ax_award, pe_award)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": WFP_CONCEPT,
                "scenario": case.scenario,
                "head_age": case.head_age,
                "partner_age": case.partner_age,
                "head_income": case.head_income,
                "has_pension_age_member": judgments[_HAS_PENSION_AGE],
                "any_member_aged_80_or_over": judgments[_ANY_80],
                "income_below_recovery_threshold": judgments[_INCOME_BELOW],
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
                    "concept": WFP_CONCEPT,
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
        "suite": "uk-winter-fuel-payment-pe",
        "concept": WFP_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {
            "axiom": WFP_OUTPUT,
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
                [{"count": mismatch_count, "value": WFP_CONCEPT}]
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
            "generator": "scripts/generate_uk_winter_fuel_payment_pe.py",
            "axiom_engine": "axiom rules engine over "
            f"rulespec-uk {WFP_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK Winter Fuel Payment (gov.dwp.winter_fuel_payment: "
                "amount.lower 200, amount.higher 300, higher_age_requirement 80, "
                "taxable_income_test.maximum_taxable_income 35000 from 2025, "
                "require_benefits true from 2024; zeroed in Scotland) vs the "
                "SI 2025/969 reg 3(1)/3(4) England-and-Wales standard amounts. The "
                "state-pension-age, 80+ and income-below-recovery-threshold "
                "judgments are supplied to the rulespec pipeline from the same "
                "age/income facts PolicyEngine reads, so both engines test the "
                "identical benefit unit."
            ),
        },
    }


def main() -> int:
    cases = _grid()
    pe_awards = _policyengine_awards(cases)
    axiom = _axiom_awards(cases)
    report = build_report(cases, pe_awards, axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-winter-fuel-payment-pe"
    dated = REPORTS / f"{basename}-{report['provenance']['generated']}.json"
    dash = DASH_PUBLIC / f"{basename}.json"
    text = json.dumps(report, indent=2) + "\n"
    dated.write_text(text)
    dash.write_text(text)

    summary = report["summary"]
    print(
        f"uk-winter-fuel-payment-pe: {summary['match_count']}/"
        f"{report['case_count']} match "
        f"({summary['axiom_vs_policyengine_match_rate']}%)"
    )
    print(f"  report:    {dated.relative_to(REPO_ROOT)}")
    print(f"  dashboard: {dash.relative_to(REPO_ROOT)}")
    return 0 if summary["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
