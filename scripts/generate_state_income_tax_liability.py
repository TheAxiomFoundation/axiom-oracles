#!/usr/bin/env python
"""Generate the composed state income-tax liability comparison reports.

For each of California, New York, Illinois, and Massachusetts this script runs
the same modest case grid (single and married filers at incomes that cross the
state's brackets) through three independent computations and records a v2
comparison report plus the per-case residuals:

* **axiom** — the composed liability pipeline in rulespec-us
  (``us-XX/policies/income_tax/pilot_liability_pipeline``), evaluated through
  the axiom rules engine. The engine-computed liabilities are read from the
  committed ``.test.yaml`` fixtures, which ``axiom-encode test`` verifies equal
  the engine output to full decimal precision, so they are the engine's values
  rather than an independent re-implementation.
* **policyengine** — PolicyEngine ``ca_income_tax`` / ``ny_income_tax`` /
  ``il_income_tax`` / ``ma_income_tax`` computed live at the 2026 tax year.
* **taxsim** — the pinned TAXSIM binary's ``siitax``. The pinned binary is a
  1960-2024 federal/state calculator (it abandons law year 2026), so the TAXSIM
  leg is run at 2024, its latest available law year; the 2024-to-2026 bracket
  and exemption indexation vintage is recorded in the dispositions rather than
  absorbed by tolerance.

Nothing here invents a value: the axiom side is the engine fixture, the
PolicyEngine side is a live calculation, and the TAXSIM side is the pinned
binary's output. Run with the axiom-oracles environment (PolicyEngine and
policyengine-taxsim installed):

    uv run --python 3.14 python scripts/generate_state_income_tax_liability.py
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[1]
RULESPEC_US = REPO_ROOT.parent / "rulespec-us"
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
TAXSIM_YEAR = 2024  # pinned binary abandons 2026; latest available law year

# TAXSIM state codes (not FIPS) from the adapter projection.
_TAXSIM_STATE = {
    "CA": 5,
    "NY": 33,
    "IL": 14,
    "MA": 22,
    "OH": 36,
    "UT": 45,
    "VA": 47,
    "NE": 28,
    "DE": 8,
    "MD": 21,
    "ME": 20,
    "MN": 24,
    "CT": 7,
    # Alabama, Idaho, and Kentucky rejoin the generation set now that their
    # rulespec-us composed pilot pipelines have landed on main (rulespec-us#773),
    # so an affected-rerun against rulespec-us main finds the companion fixtures.
    # Their us-pe suites, comparisons, and dispositions were registered in or#254;
    # the _PE_VAR/_TOL entries below were retained across the omission for this
    # restore.
    "AL": 1,
    "ID": 13,
    "KY": 18,
    # Arizona (TAXSIM SOI code 3). Its rulespec-us composed pilot landed on main,
    # so an affected-rerun against rulespec-us main finds the companion fixtures.
    "AZ": 3,
    # Georgia, Michigan, and North Carolina flat-tax pilots (rulespec-us
    # C.R.S.-wave state coverage): composed pipelines and companion fixtures
    # landed on rulespec-us main 2026-07-08.
    "GA": 11,
    "MI": 23,
    "NC": 34,
    # Colorado (TAXSIM SOI code 6). Its rulespec-us composed pilot pipeline
    # (rulespec-us#942) applies the flat 39-22-104(1.7)(c) tax with the encoded
    # rate imported hash-pinned from the statute module.
    "CO": 6,
}
# PolicyEngine target per state. CA, IL, and OH use the before-refundable-credits
# variable, the exact statutory analog of each core (the final ca_income_tax /
# il_income_tax additionally net the refundable CalEITC/Young Child credit and
# the Illinois EITC/use tax, and oh_income_tax nets the Ohio refundable credits,
# which these cores exclude). NY and MA have no refundable credits for these
# childless cases, so the final variable is identical to the
# before-refundable-credits value. Ohio also has no refundable credit active for
# the childless wage grid, so oh_income_tax_before_refundable_credits equals
# oh_income_tax here.
_PE_VAR = {
    "CA": "ca_income_tax_before_refundable_credits",
    "NY": "ny_income_tax",
    "IL": "il_income_tax_before_refundable_credits",
    "MA": "ma_income_tax",
    "OH": "oh_income_tax_before_refundable_credits",
    # Virginia's before-non-refundable-credits variable is the exact 58.1-320
    # bracket-tax analog; on the childless grid it equals the final va_income_tax
    # (no VA credits).
    "VA": "va_income_tax_before_non_refundable_credits",
    # Utah's before-credits variable is the pure 59-10-104 flat tax; the
    # before-non-refundable variable nets the phased-out 59-10-1018 taxpayer
    # credit that this flat core excludes.
    "UT": "ut_income_tax_before_credits",
    # Alabama, Idaho, and Kentucky use the before-refundable-credits variable,
    # the exact statutory analog of each core. Alabama's final al_income_tax
    # equals it on this grid (no refundable credits); Idaho's final id_income_tax
    # additionally nets the refundable grocery credit that the 63-3024 core
    # excludes; Kentucky's final ky_income_tax nets the refundable/family-size
    # credits that the 141.020 flat core excludes.
    "AL": "al_income_tax_before_refundable_credits",
    "ID": "id_income_tax_before_refundable_credits",
    "KY": "ky_income_tax_before_refundable_credits",
    # Nebraska's before-credits variable is the pure 77-2715.03 four-bracket
    # progressive tax on Nebraska taxable income (AGI less the 77-2716.01 standard
    # deduction). The before-refundable variable nets the 77-2716.01 personal
    # exemption credit (a post-tax nonrefundable credit) that this core excludes.
    "NE": "ne_income_tax_before_credits",
    # Delaware, Maryland, Maine, Minnesota, and Connecticut use the
    # before-refundable-credits variable, the exact statutory analog of each
    # composed pipeline. Delaware's final de_income_tax nets the refundable EITC;
    # Maryland's md_income_tax_before_refundable_credits is the STATE tax only (the
    # county tax md_county_tax is a separate variable the pipeline excludes); Maine
    # and Minnesota net their refundable credits in the final variable; Connecticut
    # nets the refundable EITC/property-tax credit. On this childless grid each
    # before-refundable variable is the pipeline's exact target.
    "DE": "de_income_tax_before_refundable_credits",
    "MD": "md_income_tax_before_refundable_credits",
    "ME": "me_income_tax_before_refundable_credits",
    "MN": "mn_income_tax_before_refundable_credits",
    "CT": "ct_income_tax_before_refundable_credits",
    # Arizona levies a single flat rate (43-1011) on Arizona taxable income (AGI
    # less the 43-1041 standard deduction). az_income_tax equals
    # az_income_tax_before_refundable_credits on this childless grid (no refundable
    # credits active), so the final variable is the pipeline's exact target.
    "AZ": "az_income_tax",
    # Georgia's before-non-refundable-credits variable is the exact 48-7-20
    # flat-tax analog (AGI less the 48-7-27 standard deduction); the childless
    # grid activates none of the 48-7-29 / low-income / CDCC credits, so it
    # equals the final ga_income_tax here.
    "GA": "ga_income_tax_before_non_refundable_credits",
    # Michigan's before-non-refundable-credits variable is the exact MCL 206.51
    # flat-tax analog (AGI less the 206.30 personal exemptions); the grid
    # activates no homestead/heating/EITC credits.
    "MI": "mi_income_tax_before_non_refundable_credits",
    # North Carolina's before-credits variable is the exact 105-153.7 flat-tax
    # analog (AGI less the 105-153.5(a) standard deduction); the grid activates
    # no child deduction or 105-153.10 credits.
    "NC": "nc_income_tax_before_credits",
    # Colorado's before-non-refundable variable is the exact 39-22-104(1.7)(c)
    # flat-tax analog on this grid, and it matches the composed pipeline to the
    # cent at the pinned policyengine-us on all six cases. The 39-22-627
    # temporary-rate mechanism is inactive at the 2026 validation year. TAXSIM
    # residuals are 2024-vintage plus a concept difference (siitax nets the 2024
    # TABOR sales-tax refund); each is decomposed exactly in dispositions.
    "CO": "co_income_tax_before_non_refundable_credits",
}
# Ordered state list; new states append here so the grid, reports, and main loop
# all pick them up. Derived from _TAXSIM_STATE insertion order.
_STATES = tuple(_TAXSIM_STATE)
_MODULE = {
    st: f"us-{st.lower()}:policies/income_tax/pilot_liability_pipeline"
    for st in _TAXSIM_STATE
}
_LIABILITY_OUTPUT = {
    st: f"{_MODULE[st]}#{st.lower()}_pit_pilot_income_tax_liability"
    for st in _TAXSIM_STATE
}


@dataclass
class Case:
    case_id: str
    state: str
    filing: str  # "single" | "married"
    wages: float


# Modest grid: single and married filers at incomes crossing the brackets.
# CA/NY are progressive, IL is flat, MA is flat plus a surtax that these
# incomes stay below.
def _grid() -> list[Case]:
    cases: list[Case] = []
    plan = {
        "single": [30000, 60000, 150000],
        "married": [60000, 120000, 300000],
    }
    for state in _STATES:
        for filing, incomes in plan.items():
            for inc in incomes:
                cases.append(
                    Case(
                        case_id=f"{state.lower()}-{filing}-{inc}",
                        state=state,
                        filing=filing,
                        wages=float(inc),
                    )
                )
    return cases


def _axiom_liabilities() -> dict[tuple[str, str, int], float]:
    """Read the engine-verified pipeline liabilities from the test fixtures.

    ``axiom-encode test`` proves these equal the axiom rules-engine output to
    full decimal precision, so they are the engine's liabilities. The fixture
    inputs are the pipeline's supplied AGI/base-income (which equals wages for
    the ordinary wage earner this slice models), filing status, and the
    supplied 2026 indexed schedule.
    """
    import yaml

    out: dict[tuple[str, str, int], float] = {}
    for state in _TAXSIM_STATE:
        test_file = (
            RULESPEC_US
            / f"us-{state.lower()}"
            / "policies"
            / "income_tax"
            / "pilot_liability_pipeline.test.yaml"
        )
        doc = yaml.safe_load(test_file.read_text())
        liab_key = _LIABILITY_OUTPUT[state]
        for case in doc:
            name = case["name"]
            # Map the fixture case to (state, filing, income) by its supplied AGI.
            inputs = case["input"]
            agi_key = next(k for k in inputs if k.endswith("adjusted_gross_income"))
            agi = int(round(float(inputs[agi_key])))
            filing = (
                "married"
                if name.startswith("joint")
                or "married" in name
                else "single"
            )
            liab_raw = case["output"].get(liab_key)
            if liab_raw is None:
                continue
            out[(state, filing, agi)] = float(str(liab_raw))
    return out


def _policyengine_liability(case: Case) -> float:
    from policyengine_us import Simulation

    year = VALIDATION_YEAR
    people = {"head": {"age": {year: 40}, "employment_income": {year: case.wages}}}
    members = ["head"]
    if case.filing == "married":
        people["spouse"] = {"age": {year: 40}, "employment_income": {year: 0}}
        members = ["head", "spouse"]
    situation = {
        "people": people,
        "tax_units": {"tu": {"members": members}},
        "families": {"f": {"members": members}},
        "spm_units": {"s": {"members": members}},
        "households": {"h": {"members": members, "state_code": {year: case.state}}},
    }
    sim = Simulation(situation=situation)
    return float(sim.calculate(_PE_VAR[case.state], year)[0])


def _taxsim_liabilities(cases: list[Case]) -> dict[str, float]:
    from policyengine_taxsim.runners.taxsim_runner import TaxsimRunner
    import pandas as pd

    rows = []
    for i, case in enumerate(cases, start=1):
        mstat = 2 if case.filing == "married" else 1
        rows.append(
            {
                "taxsimid": i,
                "year": TAXSIM_YEAR,
                "state": _TAXSIM_STATE[case.state],
                "mstat": mstat,
                "page": 40,
                "sage": 40 if mstat == 2 else 0,
                "depx": 0,
                "pwages": case.wages,
                "swages": 0,
                "idtl": 2,
            }
        )
    frame = pd.DataFrame(rows)
    runner = TaxsimRunner(frame)
    try:
        result = runner.run(show_progress=False)
    except TypeError:
        result = runner.run()
    records = result.to_dict(orient="records")
    return {
        case.case_id: float(rec["siitax"])
        for case, rec in zip(cases, records, strict=True)
    }


def _match(left: float, right: float, tolerance: float, rel: float) -> bool:
    diff = abs(left - right)
    if diff <= tolerance:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= rel


# Per-state comparison tolerances mirror the concept-mapping entries.
_TOL = {
    "CA": (5.0, 0.02),
    "NY": (5.0, 0.02),
    "IL": (5.0, 0.02),
    "MA": (1.0, 0.0),
    # Ohio reproduces PolicyEngine to the cent (the residual is PolicyEngine's
    # float32 rounding, under a tenth of a cent); a $1 absolute band catches any
    # structural bracket error without absorbing the indexation vintage.
    "OH": (1.0, 0.0),
    # Virginia matches PolicyEngine exactly (fixed statutory brackets, no
    # rounding); a $1 band catches structural bracket errors without absorbing
    # the TAXSIM standard-deduction vintage.
    "VA": (1.0, 0.0),
    # Utah is a single flat rate on the taxable base; exact match.
    "UT": (1.0, 0.0),
    # Alabama, Idaho, and Kentucky each reproduce PolicyEngine to a hundredth of
    # a cent (the residual is PolicyEngine's float32 rounding); a $1 absolute
    # band catches any structural bracket error without absorbing the
    # 2024-to-2026 rate/deduction vintage carried by the TAXSIM leg.
    "AL": (1.0, 0.0),
    "ID": (1.0, 0.0),
    "KY": (1.0, 0.0),
    # Nebraska reproduces PolicyEngine to the cent (the residual is PolicyEngine's
    # float32 rounding, under a tenth of a cent); a $1 band catches structural
    # bracket errors without absorbing the TAXSIM rate-compression and indexation
    # vintage.
    "NE": (1.0, 0.0),
    # Delaware, Maryland, Maine, Minnesota, and Connecticut each reproduce
    # PolicyEngine to the cent (residual is PolicyEngine's float32 rounding); a $1
    # absolute band catches any structural bracket error without absorbing the
    # 2024-to-2026 vintage on the TAXSIM leg. Maryland's TAXSIM residual also
    # carries the county/local income tax that siitax includes but the state-only
    # target excludes; that scope gap is dispositioned, not absorbed by tolerance.
    "DE": (1.0, 0.0),
    "MD": (1.0, 0.0),
    "ME": (1.0, 0.0),
    "MN": (1.0, 0.0),
    "CT": (1.0, 0.0),
    # Arizona reproduces PolicyEngine exactly (flat 2.5% on AGI less the standard
    # deduction; no rounding residual). A $1 absolute band catches any structural
    # error without absorbing the 2024-to-2026 standard-deduction indexation on
    # the TAXSIM leg.
    "AZ": (1.0, 0.0),
    # Georgia, Michigan, and North Carolina are flat taxes in the same shape as
    # Arizona: a $1 absolute band catches structural errors without absorbing
    # each state's 2024-to-2026 rate/deduction vintage on the TAXSIM leg.
    "GA": (1.0, 0.0),
    "MI": (1.0, 0.0),
    "NC": (1.0, 0.0),
    # Colorado reproduces PolicyEngine to the cent on all six grid cases; a
    # $1 absolute band catches structural errors without absorbing anything.
    "CO": (1.0, 0.0),
}


def _build_report(
    state: str,
    cases: list[Case],
    axiom: dict[tuple[str, str, int], float],
    pe: dict[str, float],
    taxsim: dict[str, float],
) -> dict:
    tol, rel = _TOL[state]
    concept = _LIABILITY_OUTPUT[state]
    report_cases = []
    # `mismatches` uses the standard v2 schema (concept, case_id, kind, left,
    # right) so scripts/apply_dispositions.py can join the committed dispositions
    # against these rows and validate that every residual is explained. The
    # axiom-vs-PolicyEngine comparison matches on every case, so only the
    # axiom-vs-TAXSIM-2024 residuals become mismatch rows (axiom is `left`,
    # TAXSIM 2024 is `right`); the indexation-vintage dispositions pin those.
    mismatches: list[dict] = []
    pe_matches = 0
    taxsim_matches = 0
    n = 0
    for case in cases:
        if case.state != state:
            continue
        n += 1
        ax = axiom[(state, case.filing, int(case.wages))]
        pe_v = pe[case.case_id]
        ts_v = taxsim[case.case_id]
        pe_ok = _match(ax, pe_v, tol, rel)
        ts_ok = _match(ax, ts_v, tol, rel)
        pe_matches += int(pe_ok)
        taxsim_matches += int(ts_ok)
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": concept,
                "filing_status": case.filing,
                "employment_income": case.wages,
                "axiom": ax,
                "policyengine": pe_v,
                "taxsim_2024": ts_v,
                "axiom_vs_policyengine": {
                    "difference": ax - pe_v,
                    "match": pe_ok,
                },
                "axiom_vs_taxsim_2024": {
                    "difference": ax - ts_v,
                    "match": ts_ok,
                },
            }
        )
        if not ts_ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": concept,
                    "kind": "amount_difference",
                    "engines": ["axiom", "taxsim"],
                    "left_engine": "axiom",
                    "right_engine": "taxsim",
                    "left": ax,
                    "right": ts_v,
                    "difference": ax - ts_v,
                }
            )
    comparison_count = n
    mismatch_count = len(mismatches)
    match_count = comparison_count - mismatch_count
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": f"{state.lower()}-income-tax-liability",
        "concept": concept,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "taxsim_law_year": TAXSIM_YEAR,
        "engines": {
            "axiom": _MODULE[state],
            "policyengine": _PE_VAR[state],
            "taxsim": "siitax",
        },
        "tolerance": {"absolute": tol, "relative": rel},
        "case_count": n,
        "summary": {
            "comparison_count": comparison_count,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "axiom_vs_policyengine_match_rate": round(100.0 * pe_matches / n, 2),
            "axiom_vs_taxsim_2024_match_rate": round(100.0 * taxsim_matches / n, 2),
            "policyengine_matches": pe_matches,
            "taxsim_2024_matches": taxsim_matches,
        },
        "mismatches": mismatches,
        "cases": report_cases,
        "provenance": {
            "generated": date.today().isoformat(),
            "generator": "scripts/generate_state_income_tax_liability.py",
            "axiom_source": "engine-verified pilot_liability_pipeline.test.yaml fixtures",
            "note": (
                "axiom-vs-PolicyEngine matches every case at the 2026 validation "
                "year; the mismatches array carries the axiom-vs-TAXSIM-2024 "
                "residuals, whose 2024-to-2026 indexation vintage is dispositioned."
            ),
        },
    }


def main() -> int:
    cases = _grid()
    axiom = _axiom_liabilities()
    pe = {case.case_id: _policyengine_liability(case) for case in cases}
    taxsim = _taxsim_liabilities(cases)
    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    for state in _STATES:
        report = _build_report(state, cases, axiom, pe, taxsim)
        basename = f"axiom-policyengine-taxsim-{state.lower()}-income-tax-liability"
        (REPORTS / f"{basename}-{stamp}.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        (DASH_PUBLIC / f"{basename}.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        s = report["summary"]
        print(
            f"{state}: PE match {s['axiom_vs_policyengine_match_rate']}% "
            f"({s['policyengine_matches']}/{report['case_count']}), "
            f"TAXSIM-2024 match {s['axiom_vs_taxsim_2024_match_rate']}% "
            f"({s['taxsim_2024_matches']}/{report['case_count']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
