#!/usr/bin/env python3
"""Devolved property transaction tax case grid: rulespec-uk vs PolicyEngine-UK.

Compares the two encoded devolved residential property transaction taxes
against PolicyEngine-UK (2.89.2) on a synthetic household grid at the 2026
validation year:

* Scotland — Land and Buildings Transaction Tax (rulespec-uk
  ``uk/policies/govuk/lbtt.yaml``, SSI 2015/126 + LBTT(S)A 2013 Sch 2A) vs
  PolicyEngine ``land_and_buildings_transaction_tax``.
* Wales — Land Transaction Tax (rulespec-uk ``uk/policies/govuk/ltt.yaml``,
  WSI 2018/128 + LTT(W)A 2017 s.24) vs PolicyEngine ``land_transaction_tax``.

Both sides read the same supplied purchase prices
(``main_residential_property_purchased`` and
``additional_residential_property_purchased``), so the band split is
commensurable. The main-home LBTT surface matches PolicyEngine to the penny.
Two vintage divergences are exposed and dispositioned (see
``dispositions/uk-lbtt-ltt.yaml``) as upstream PolicyEngine staleness:

* LBTT additional-dwelling: PolicyEngine's ``additional_residence_surcharge``
  is 6%, but the LBTT(S)A 2013 Sch 2A Additional Dwelling Supplement has been
  8% since 5 December 2024 (PolicyEngine-UK #1795).
* LTT residential: PolicyEngine's ``gov.wra.land_transaction_tax`` primary
  scale is frozen at its 2021-07-01 vintage (missing the 10 October 2022 rise
  of the starting threshold to £225,000 and first band to 6%) and its
  higher-rate scale at its 2020-12-22 vintage (missing the 11 December 2024
  one-point uplift) (PolicyEngine-UK #1796).

Run locally (needs a PolicyEngine-UK 2.89.2 environment, a built axiom rules
engine, and the rulespec-uk checkout)::

    uv run python scripts/generate_uk_lbtt_ltt.py
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


LBTT_PROGRAM = "uk/policies/govuk/lbtt.yaml"
LBTT_BASE = "uk:policies/govuk/lbtt"
LBTT_OUTPUT = f"{LBTT_BASE}#land_and_buildings_transaction_tax"
LTT_PROGRAM = "uk/policies/govuk/ltt.yaml"
LTT_BASE = "uk:policies/govuk/ltt"
LTT_OUTPUT = f"{LTT_BASE}#land_transaction_tax"

#: The two supplied purchase-price inputs the band split reads (both Money),
#: named identically on the LBTT and LTT modules.
_MAIN = "main_residential_property_purchased"
_ADDITIONAL = "additional_residential_property_purchased"

_PE_LBTT = "land_and_buildings_transaction_tax"
_PE_LTT = "land_transaction_tax"

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class TxnCase:
    """One synthetic household on the devolved transaction-tax grid."""

    case_id: str
    country: str  # "SCOTLAND" or "WALES"
    main_purchase: float
    additional_purchase: float
    scenario: str

    @property
    def program(self) -> str:
        return LBTT_PROGRAM if self.country == "SCOTLAND" else LTT_PROGRAM

    @property
    def output(self) -> str:
        return LBTT_OUTPUT if self.country == "SCOTLAND" else LTT_OUTPUT

    @property
    def concept(self) -> str:
        return self.output

    @property
    def pe_variable(self) -> str:
        return _PE_LBTT if self.country == "SCOTLAND" else _PE_LTT


def _grid() -> list[TxnCase]:
    """Households exercising the LBTT (Scotland) and LTT (Wales) band splits.

    LBTT: main-home purchases spanning every residential band (all match
    PolicyEngine to the penny) plus additional-dwelling purchases that expose
    the 8%-vs-6% Additional Dwelling Supplement staleness. LTT: main-home and
    additional-dwelling purchases that expose the stale Welsh primary and
    higher-rate scales.
    """

    return [
        # --- Scotland LBTT ---
        TxnCase(
            "lbtt-main-below-nil-rate-band",
            "SCOTLAND",
            100000,
            0,
            "main-home-below-nil-rate-band",
        ),
        TxnCase(
            "lbtt-main-two-percent-band",
            "SCOTLAND",
            200000,
            0,
            "main-home-in-two-percent-band",
        ),
        TxnCase(
            "lbtt-main-spanning-two-and-five",
            "SCOTLAND",
            300000,
            0,
            "main-home-spanning-two-and-five-percent-bands",
        ),
        TxnCase(
            "lbtt-main-into-ten-percent-band",
            "SCOTLAND",
            500000,
            0,
            "main-home-into-ten-percent-band",
        ),
        TxnCase("lbtt-main-top-band", "SCOTLAND", 800000, 0, "main-home-in-top-band"),
        TxnCase(
            "lbtt-additional-dwelling",
            "SCOTLAND",
            0,
            300000,
            "additional-dwelling-supplement",
        ),
        TxnCase(
            "lbtt-main-plus-additional",
            "SCOTLAND",
            300000,
            250000,
            "main-plus-additional-dwelling",
        ),
        # --- Wales LTT ---
        TxnCase(
            "ltt-main-below-nil-rate-band",
            "WALES",
            100000,
            0,
            "main-home-below-nil-rate-band",
        ),
        TxnCase(
            "ltt-main-six-percent-band",
            "WALES",
            300000,
            0,
            "main-home-in-six-percent-band",
        ),
        TxnCase(
            "ltt-main-into-ten-percent-band",
            "WALES",
            800000,
            0,
            "main-home-into-ten-percent-band",
        ),
        TxnCase(
            "ltt-additional-higher-rates",
            "WALES",
            0,
            300000,
            "additional-dwelling-higher-rates",
        ),
        TxnCase(
            "ltt-main-plus-additional",
            "WALES",
            400000,
            300000,
            "main-plus-additional-dwelling",
        ),
    ]


def _pe_situation(case: TxnCase) -> dict:
    year = VALIDATION_YEAR
    return {
        "people": {"person": {"age": {year: 40}}},
        "benunits": {"bu": {"members": ["person"]}},
        "households": {
            "hh": {
                "members": ["person"],
                "country": {year: case.country},
                _MAIN: {year: case.main_purchase},
                _ADDITIONAL: {year: case.additional_purchase},
                "main_residential_property_purchased_is_first_home": {year: False},
            }
        },
    }


def _policyengine_rows(cases: list[TxnCase]) -> dict[str, float]:
    """PolicyEngine-UK devolved transaction tax for each synthetic household."""

    from policyengine_uk import Simulation

    year = VALIDATION_YEAR
    rows: dict[str, float] = {}
    for case in cases:
        sim = Simulation(situation=_pe_situation(case))
        rows[case.case_id] = float(sim.calculate(case.pe_variable, year).sum())
    return rows


def _axiom_amounts(
    cases: list[TxnCase],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict[str, float]:
    """Rulespec LBTT/LTT band split through the axiom rules engine.

    Each case feeds its purchase prices as the rulespec supplied inputs, so both
    engines test the identical band-split arithmetic.
    """

    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    amounts: dict[str, float] = {}

    # Group by program so each module is compiled once.
    for program_rel, output, group in (
        (LBTT_PROGRAM, LBTT_OUTPUT, [c for c in cases if c.country == "SCOTLAND"]),
        (LTT_PROGRAM, LTT_OUTPUT, [c for c in cases if c.country == "WALES"]),
    ):
        if not group:
            continue
        program = rulespec_root / program_rel
        axiom_cases = [
            Case(
                case_id=case.case_id,
                period=str(VALIDATION_YEAR),
                metadata={
                    "axiom_entity": "Household",
                    "axiom_entity_id": "household",
                    "axiom_inputs": {
                        f"{case.output.split('#')[0]}#{_MAIN}": case.main_purchase,
                        f"{case.output.split('#')[0]}#{_ADDITIONAL}": case.additional_purchase,
                    },
                },
                outputs=(output,),
            )
            for case in group
        ]
        runner = AxiomRulesRunner(
            program_path=program,
            binary_path=axiom_binary,
            default_entity="Household",
            default_entity_id="household",
            rulespec_root=rulespec_root,
            mode="explain",
        )
        results = runner.run_cases(axiom_cases, [output])
        for result in results:
            if result.errors:
                raise RuntimeError(
                    f"axiom rules engine failed for {result.household_id}: "
                    f"{result.errors}"
                )
            amounts[str(result.household_id)] = float(result.values[output])
    return amounts


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def build_report(
    cases: list[TxnCase],
    pe_rows: dict[str, float],
    axiom: dict[str, float],
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    matches = 0
    mismatch_by_concept: dict[str, int] = {}
    for case in cases:
        pe = pe_rows[case.case_id]
        ax = axiom[case.case_id]
        ok = _match(ax, pe)
        matches += int(ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": case.concept,
                "scenario": case.scenario,
                "country": case.country,
                "main_residential_property_purchased": case.main_purchase,
                "additional_residential_property_purchased": case.additional_purchase,
                "axiom": ax,
                "policyengine": pe,
                "axiom_vs_policyengine": {"difference": ax - pe, "match": ok},
            }
        )
        if not ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": case.concept,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax,
                    "right": pe,
                    "difference": ax - pe,
                }
            )
            mismatch_by_concept[case.concept] = (
                mismatch_by_concept.get(case.concept, 0) + 1
            )
    n = len(cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * matches / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "uk-lbtt-ltt",
        "concept": "uk-lbtt-ltt",
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {
            "axiom": "uk:policies/govuk/{lbtt,ltt} devolved transaction tax",
            "policyengine": f"{_PE_LBTT}, {_PE_LTT}",
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
                [
                    {"count": c, "value": k}
                    for k, c in sorted(mismatch_by_concept.items())
                ]
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
            "generator": "scripts/generate_uk_lbtt_ltt.py",
            "axiom_engine": (
                f"axiom rules engine over rulespec-uk {LBTT_PROGRAM} and {LTT_PROGRAM}"
            ),
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "commensurability": (
                "PolicyEngine-UK land_and_buildings_transaction_tax (Scotland) "
                "and land_transaction_tax (Wales) vs the SSI 2015/126 + LBTT(S)A "
                "2013 Sch 2A and WSI 2018/128 + LTT(W)A 2017 band splits; the "
                "main and additional residential purchase prices are supplied "
                "inputs on both sides. Divergences are upstream PolicyEngine "
                "rate/threshold vintage staleness (#1795 LBTT ADS, #1796 Welsh "
                "LTT), dispositioned in dispositions/uk-lbtt-ltt.yaml."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="uk")
    cases = _grid()
    pe_rows = _policyengine_rows(cases)
    axiom = _axiom_amounts(
        cases,
        rulespec_root=rulespec_root,
        axiom_binary=axiom_binary,
    )
    report = build_report(cases, pe_rows, axiom)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    basename = "axiom-policyengine-uk-lbtt-ltt"
    stamp = date.today().isoformat()
    (REPORTS / f"{basename}-{stamp}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (DASH_PUBLIC / f"{basename}.json").write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    print(
        f"uk-lbtt-ltt: PE match "
        f"{summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['policyengine_matches']}/{report['case_count']} cases); "
        f"{summary['mismatch_count']} dispositioned divergences"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
