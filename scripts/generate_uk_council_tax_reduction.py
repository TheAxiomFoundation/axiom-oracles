#!/usr/bin/env python3
"""Council Tax Reduction case grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded England pension-age Council Tax Reduction scheme
(rulespec-uk ``uk/policies/govuk/council-tax-reduction.yaml``, the SI 2012/2885
prescribed requirements) against PolicyEngine-UK's ``council_tax_reduction`` on
a synthetic pensioner-household grid at the 2026 validation year.

Both sides are commensurable because Council Tax Reduction takes the same
supplied inputs on each engine:

* PolicyEngine-UK's ``council_tax_reduction_maximum_eligible_liability`` is
  ``council_tax`` (a reported/projected household input), and its England
  pension-age path (parameters
  ``gov.local_authorities.england.council_tax_reduction.pensioners``:
  maximum-support 1, capital limit £16,000, withdrawal rate 0.20) is
  parameter-identical to SI 2012/2885 Schedule 1.
* The rulespec England pension-age award
  ``council_tax_reduction_annual_amount`` is a closed-form function of five
  supplied inputs — ``applicable_amount_for_year``, ``income_for_year``,
  ``council_tax_liability_for_year``, ``non_dependant_deductions_for_year`` and
  ``household_capital`` — the applicable amount / applicable income / non-dep
  deductions PolicyEngine computes internally.

The bridge mirrors the ``uk_pension_credit`` suite: for each synthetic
household this generator reads PolicyEngine's own computed applicable amount,
applicable income, non-dependant deductions, ``council_tax`` liability and
``savings``, and feeds those exact values as the rulespec supplied inputs, so
both engines test the identical means-test arithmetic. The Axiom side is
evaluated through the axiom rules engine (``AxiomRulesRunner``); its numbers are
the engine's, not a re-implementation.

Because the two schemes are the same statute with the same inputs, the grid
matches to the penny across the full award surface — full award below the
applicable amount, the 20 per cent taper interior, the £16,000 capital screen,
and single/couple households. The only residuals are sub-£0.001 PolicyEngine
float32 artifacts, inside the £0.01 tolerance.

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_council_tax_reduction.py

On a runner without those, the committed dashboard report stands (the runner in
run_comparison.py reuses it), exactly like the state income-tax grid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timezone
from datetime import datetime
from pathlib import Path

from canonical_rulespec_runtime import parse_canonical_runtime_args

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
POLICYENGINE_UK_VERSION = "2.89.2"

#: rulespec-uk checkout (the encoded England pension-age scheme + companion
#: tests). Resolves from the environment, then the org-mirror default.

#: Encoded program under comparison and its final award output.
CTR_PROGRAM = "uk/policies/govuk/council-tax-reduction.yaml"
CTR_BASE = "uk:policies/govuk/council-tax-reduction"
CTR_OUTPUT = f"{CTR_BASE}#council_tax_reduction_annual_amount"
CTR_CONCEPT = CTR_OUTPUT

#: The five supplied inputs the England pension-age award reads (Judgment for
#: the immigration-control flag, Money for the rest).
_APPLICABLE_AMOUNT = f"{CTR_BASE}#applicable_amount_for_year"
_INCOME = f"{CTR_BASE}#income_for_year"
_COUNCIL_TAX = f"{CTR_BASE}#council_tax_liability_for_year"
_NON_DEP = f"{CTR_BASE}#non_dependant_deductions_for_year"
_CAPITAL = f"{CTR_BASE}#household_capital"
_IMMIGRATION = f"{CTR_BASE}#liable_person_subject_to_immigration_control"

#: PolicyEngine-UK variables read for the bridge and the final compared output.
_PE_AWARD = "council_tax_reduction"
_PE_APPLICABLE_AMOUNT = "council_tax_reduction_applicable_amount"
_PE_APPLICABLE_INCOME = "council_tax_reduction_applicable_income"
_PE_NON_DEP = "council_tax_reduction_non_dep_deductions"
_PE_LIABILITY = "council_tax_reduction_maximum_eligible_liability"
_PE_CAPITAL = "savings"

#: Comparison tolerance — matches the bridges/mappings/uk.yaml CTR entry and the
#: EFRS suites' pound tolerance. PolicyEngine-UK carries monetary variables in
#: float32, so a small relative tolerance absorbs the last-bit representation
#: difference on the taper-interior cases.
_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class CTRCase:
    """One synthetic England pensioner household on the CTR grid."""

    case_id: str
    head_age: int
    state_pension: float
    employment_income: float
    savings: float
    council_tax: float
    couple: bool
    scenario: str


def _grid() -> list[CTRCase]:
    """England pension-age households exercising the SI 2012/2885 award surface.

    Covers: full award when income is at or below the applicable amount; the
    20 per cent taper interior (three award levels); the £16,000 capital screen
    at and above the limit; a high council-tax liability; and single vs couple
    applicable amounts. Every case is in England with a pension-age head, so the
    supported scheme is the England pensioner prescribed scheme.
    """

    return [
        CTRCase(
            "ctr-pa-single-full-below-aa",
            70,
            4000,
            0,
            0,
            1800,
            False,
            "full-award-income-below-applicable-amount",
        ),
        CTRCase(
            "ctr-pa-single-full-income-at-aa",
            70,
            9000,
            4000,
            0,
            1800,
            False,
            "full-award-income-near-applicable-amount",
        ),
        CTRCase(
            "ctr-pa-single-taper-interior-a",
            70,
            18312,
            0,
            0,
            3000,
            False,
            "taper-interior",
        ),
        CTRCase(
            "ctr-pa-single-taper-interior-b",
            70,
            25164,
            0,
            0,
            3000,
            False,
            "taper-interior",
        ),
        CTRCase(
            "ctr-pa-single-taper-interior-c",
            70,
            20000,
            0,
            0,
            2500,
            False,
            "taper-interior",
        ),
        CTRCase(
            "ctr-pa-single-taper-to-zero",
            70,
            12000,
            20000,
            0,
            1800,
            False,
            "taper-exhausts-award",
        ),
        CTRCase(
            "ctr-pa-single-capital-at-limit",
            70,
            4000,
            0,
            16000,
            1800,
            False,
            "capital-at-limit-eligible",
        ),
        CTRCase(
            "ctr-pa-single-capital-over-limit",
            70,
            4000,
            0,
            20000,
            1800,
            False,
            "capital-over-limit-excluded",
        ),
        CTRCase(
            "ctr-pa-single-high-council-tax",
            72,
            8000,
            0,
            0,
            2600,
            False,
            "full-award-high-liability",
        ),
        CTRCase(
            "ctr-pa-couple-full-below-aa",
            70,
            6000,
            0,
            0,
            2200,
            True,
            "couple-full-award",
        ),
        CTRCase(
            "ctr-pa-couple-taper-interior",
            70,
            24000,
            0,
            0,
            2400,
            True,
            "couple-taper-interior",
        ),
    ]


def _pe_situation(case: CTRCase) -> dict:
    year = VALIDATION_YEAR
    people = {
        "person": {
            "age": {year: case.head_age},
            "state_pension": {year: case.state_pension},
            "employment_income": {year: case.employment_income},
        }
    }
    members = ["person"]
    if case.couple:
        # A pension-age partner keeps the benefit unit on the pensioner scheme
        # and lifts the applicable amount to the couple rate.
        people["partner"] = {"age": {year: 68}, "state_pension": {year: 0}}
        members = ["person", "partner"]
    return {
        "people": people,
        "benunits": {"bu": {"members": members}},
        "households": {
            "hh": {
                "members": members,
                "council_tax": {year: case.council_tax},
                "local_authority": {year: "KINGSTON_UPON_THAMES"},
                "region": {year: "LONDON"},
                "country": {year: "ENGLAND"},
                "savings": {year: case.savings},
            }
        },
    }


def _policyengine_rows(cases: list[CTRCase]) -> dict[str, dict[str, float]]:
    """PolicyEngine-UK award plus the internals bridged into the rulespec side."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, dict[str, float]] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        rows[case.case_id] = {
            "award": float(sim.calculate(_PE_AWARD, year).sum()),
            "applicable_amount": float(
                sim.calculate(_PE_APPLICABLE_AMOUNT, year).sum()
            ),
            "applicable_income": float(
                sim.calculate(_PE_APPLICABLE_INCOME, year).sum()
            ),
            "non_dep_deductions": float(sim.calculate(_PE_NON_DEP, year).sum()),
            "council_tax_liability": float(sim.calculate(_PE_LIABILITY, year).sum()),
            "capital": float(sim.calculate(_PE_CAPITAL, year).sum()),
        }
    return rows


def _axiom_awards(
    cases: list[CTRCase],
    pe_rows: dict[str, dict[str, float]],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    """Rulespec England pension-age award through the axiom rules engine.

    Each case feeds PolicyEngine's own applicable amount / applicable income /
    non-dependant deductions / ``council_tax`` liability / ``savings`` as the
    rulespec supplied inputs, so the two engines test the identical means-test
    arithmetic (the ``uk_pension_credit`` bridge pattern).
    """

    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = rulespec_root / CTR_PROGRAM

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
                        _APPLICABLE_AMOUNT: row["applicable_amount"],
                        _INCOME: row["applicable_income"],
                        _COUNCIL_TAX: row["council_tax_liability"],
                        _NON_DEP: row["non_dep_deductions"],
                        _CAPITAL: row["capital"],
                        _IMMIGRATION: False,
                    },
                },
                outputs=(CTR_OUTPUT,),
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
    results = runner.run_cases(axiom_cases, [CTR_OUTPUT])
    awards: dict[str, float] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        awards[str(result.household_id)] = float(result.values[CTR_OUTPUT])
    return awards


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[CTRCase],
    pe_rows: dict[str, dict[str, float]],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    for case in cases:
        pe_award = pe_rows[case.case_id]["award"]
        ax_award = axiom[case.case_id]
        ok = _match(ax_award, pe_award)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": CTR_CONCEPT,
                "scenario": case.scenario,
                "couple": case.couple,
                "council_tax_liability": pe_rows[case.case_id]["council_tax_liability"],
                "applicable_amount": pe_rows[case.case_id]["applicable_amount"],
                "applicable_income": pe_rows[case.case_id]["applicable_income"],
                "household_capital": pe_rows[case.case_id]["capital"],
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
                    "concept": CTR_CONCEPT,
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
        "suite": "uk-council-tax-reduction",
        "concept": CTR_CONCEPT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {
            "axiom": CTR_OUTPUT,
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
                [{"count": mismatch_count, "value": CTR_CONCEPT}]
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
            "generator": "scripts/generate_uk_council_tax_reduction.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {CTR_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK England pension-age Council Tax Reduction "
                "(gov.local_authorities.england.council_tax_reduction.pensioners: "
                "max-support 1, capital limit 16000, withdrawal 0.20) vs the "
                "SI 2012/2885 prescribed pension-age scheme; council_tax "
                "liability is a supplied input on both sides. PolicyEngine's "
                "computed applicable amount, applicable income and non-dependant "
                "deductions are bridged into the rulespec supplied inputs."
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
    basename = "axiom-policyengine-uk-council-tax-reduction"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-council-tax-reduction: PE match "
        f"{summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{report['case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
