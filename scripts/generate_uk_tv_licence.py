#!/usr/bin/env python3
"""TV licence case grid: rulespec-uk vs PolicyEngine-UK.

Compares the encoded TV licence fee-and-concession module (rulespec-uk
``uk/policies/govuk/tv-licence.yaml``, Communications Act 2003 s.363/s.365 and
the Communications (Television Licensing) Regulations 2004 Schedule 1) against
PolicyEngine-UK's ``tv_licence`` (net cost) and ``free_tv_licence_value``
(concession value) on a synthetic household grid at the 2026 validation year.

Both sides are commensurable because each output is the same closed form of the
same supplied facts on each engine:

* PolicyEngine-UK computes
  ``tv_licence = (owns & ~evade) * fee * (1 - discount)`` and
  ``free_tv_licence_value = (owns & ~evade) * fee * discount`` where
  ``fee = gov.dcms.bbc.tv_licence.colour`` (£180 for 2026-27) and
  ``discount = max(aged, blind)`` — the over-75 concession (100 per cent, for a
  household with someone aged 75+ receiving Pension Credit) and the blind
  concession (50 per cent).
* The rulespec ``tv_licence_net_cost`` and ``free_tv_licence_value`` are the
  identical closed forms, with the fee grounded in SI 2004/692 Schedule 1
  (£180.00) and the concession structure in Communications Act 2003 s.365.

For each synthetic household this generator reads PolicyEngine's own computed
facts — whether the household owns a receiver, would evade, contains a person
aged 75+, receives Pension Credit, and contains a blind person — plus the two
concession rates (gov.dcms.bbc.tv_licence.discount) and feeds those as the
rulespec supplied inputs, so both engines test the identical fee/concession
arithmetic. The Axiom side is evaluated through the axiom rules engine
(``AxiomRulesRunner``).

Run locally (needs PolicyEngine-UK 2.89.2, a built axiom rules engine, and the
rulespec-uk checkout)::

    uv run python scripts/generate_uk_tv_licence.py \
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


TVL_PROGRAM = "uk/policies/govuk/tv-licence.yaml"
TVL_BASE = "uk:policies/govuk/tv-licence"
TVL_NET = f"{TVL_BASE}#tv_licence_net_cost"
TVL_FREE = f"{TVL_BASE}#free_tv_licence_value"

# Rulespec supplied inputs.
_OWNS = f"{TVL_BASE}#household_owns_tv"
_EVADE = f"{TVL_BASE}#household_would_evade_tv_licence"
_AGED75 = f"{TVL_BASE}#household_has_person_aged_75"
_PC = f"{TVL_BASE}#household_receives_pension_credit"
_BLIND = f"{TVL_BASE}#household_has_blind_person"
_AGED_RATE = f"{TVL_BASE}#tv_licence_aged_concession_rate"
_BLIND_RATE = f"{TVL_BASE}#tv_licence_blind_concession_rate"

_PE_NET = "tv_licence"
_PE_FREE = "free_tv_licence_value"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class TVLCase:
    case_id: str
    scenario: str
    head_age: int
    head_income: float = 0.0
    owns_tv: bool = True
    would_evade: bool = False
    head_blind: bool = False
    partner_age: int | None = None


def _grid() -> list[TVLCase]:
    return [
        TVLCase("tvl-working-age-full-fee", "full-fee", 40),
        TVLCase("tvl-over75-pension-credit-free", "over-75-free", 80),
        TVLCase(
            "tvl-over75-no-pension-credit-pays",
            "over-75-no-pc-pays",
            80,
            head_income=40000,
        ),
        TVLCase("tvl-blind-half-fee", "blind-half", 45, head_blind=True),
        TVLCase(
            "tvl-over75-pc-and-blind-larger",
            "over-75-and-blind",
            82,
            head_blind=True,
        ),
        TVLCase("tvl-no-receiver", "no-receiver", 50, owns_tv=False),
        TVLCase("tvl-evader", "evader", 50, would_evade=True),
        TVLCase(
            "tvl-couple-one-over75-pc",
            "couple-over-75-free",
            70,
            partner_age=78,
        ),
        TVLCase(
            "tvl-blind-over75-not-on-pc",
            "blind-over75-no-pc",
            80,
            head_income=40000,
            head_blind=True,
        ),
    ]


def _pe_situation(case: TVLCase) -> dict:
    year = VALIDATION_YEAR
    people = {
        "person": {
            "age": {year: case.head_age},
            "employment_income": {year: case.head_income},
            "is_blind": {year: case.head_blind},
        }
    }
    members = ["person"]
    if case.partner_age is not None:
        people["partner"] = {"age": {year: case.partner_age}}
        members = ["person", "partner"]
    return {
        "people": people,
        "benunits": {"bu": {"members": members}},
        "households": {
            "hh": {
                "members": members,
                "household_owns_tv": {year: case.owns_tv},
                "would_evade_tv_licence_fee": {year: case.would_evade},
            }
        },
    }


def _policyengine_rows(cases: list[TVLCase]) -> dict[str, dict]:
    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, dict] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        params = sim.tax_benefit_system.parameters(f"{year}-04-06")
        ages = sim.calculate("age", year)
        is_blind = sim.calculate("is_blind", year)
        pc = float(sim.calculate("pension_credit", year).sum())
        rows[case.case_id] = {
            "tv_licence": float(sim.calculate(_PE_NET, year).sum()),
            "free_tv_licence_value": float(sim.calculate(_PE_FREE, year).sum()),
            "owns_tv": bool(sim.calculate("household_owns_tv", year)[0]),
            "would_evade": bool(sim.calculate("would_evade_tv_licence_fee", year)[0]),
            "has_aged_75": bool((ages >= 75).any()),
            "receives_pc": pc > 0,
            "has_blind": bool(is_blind.any()),
            "aged_rate": float(params.gov.dcms.bbc.tv_licence.discount.aged.discount),
            "blind_rate": float(params.gov.dcms.bbc.tv_licence.discount.blind.discount),
        }
    return rows


def _axiom_awards(
    cases: list[TVLCase],
    pe_rows: dict[str, dict],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, dict]:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    program = rulespec_root / TVL_PROGRAM

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
                        _OWNS: row["owns_tv"],
                        _EVADE: row["would_evade"],
                        _AGED75: row["has_aged_75"],
                        _PC: row["receives_pc"],
                        _BLIND: row["has_blind"],
                        _AGED_RATE: row["aged_rate"],
                        _BLIND_RATE: row["blind_rate"],
                    },
                },
                outputs=(TVL_NET, TVL_FREE),
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
    results = runner.run_cases(axiom_cases, [TVL_NET, TVL_FREE])
    awards: dict[str, dict] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: {result.errors}"
            )
        awards[str(result.household_id)] = {
            "net": float(result.values[TVL_NET]),
            "free": float(result.values[TVL_FREE]),
        }
    return awards


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[TVLCase], pe_rows: dict[str, dict], axiom: dict[str, dict]
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    comparisons = 0
    matches = 0
    for case in cases:
        row = pe_rows[case.case_id]
        ax = axiom[case.case_id]
        for concept, ax_val, pe_val in (
            (TVL_NET, ax["net"], row["tv_licence"]),
            (TVL_FREE, ax["free"], row["free_tv_licence_value"]),
        ):
            comparisons += 1
            ok = _match(ax_val, pe_val)
            matches += int(ok)
            report_cases.append(
                {
                    "case_id": case.case_id,
                    "concept": concept,
                    "scenario": case.scenario,
                    "has_aged_75": row["has_aged_75"],
                    "receives_pc": row["receives_pc"],
                    "has_blind": row["has_blind"],
                    "owns_tv": row["owns_tv"],
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
                        "concept": concept,
                        "kind": "amount_difference",
                        "engines": ["axiom", "policyengine"],
                        "left_engine": "axiom",
                        "right_engine": "policyengine",
                        "left": ax_val,
                        "right": pe_val,
                        "difference": ax_val - pe_val,
                    }
                )
    n = comparisons
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-tv-licence",
        "concept": TVL_NET,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {"axiom": TVL_NET, "policyengine": _PE_NET},
        "tolerance": {"absolute": _TOLERANCE, "relative": _RELATIVE_TOLERANCE},
        "case_count": len(cases),
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
            "mismatches_by_concept": [],
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
            "generator": "scripts/generate_uk_tv_licence.py",
            "axiom_engine": f"axiom rules engine over rulespec-uk {TVL_PROGRAM}",
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK tv_licence and free_tv_licence_value are "
                "fee * (1 - discount) and fee * discount for a household that "
                "owns a receiver and does not evade, with fee = £180 (2026-27, "
                "gov.dcms.bbc.tv_licence.colour) and discount = max(over-75 100%, "
                "blind 50%). The rulespec module reproduces this with the fee "
                "grounded in SI 2004/692 Schedule 1 (£180.00) and the concession "
                "structure in Communications Act 2003 s.365; the demographic "
                "facts and the two concession rates are supplied from "
                "PolicyEngine on both sides."
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
    basename = "axiom-policyengine-uk-tv-licence"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-tv-licence: PE match {summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{summary['comparison_count']} comparisons)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
