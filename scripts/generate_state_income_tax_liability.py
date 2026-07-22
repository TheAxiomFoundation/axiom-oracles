#!/usr/bin/env python
"""Generate the composed state income-tax liability comparison reports.

For each registered state liability suite this script runs a modest single- and
married-filer grid through three independent computations and records a v2
comparison report plus the per-case residuals. Most states use wage-income cases
that cross their brackets; Washington uses a dedicated long-term-capital-gains
grid for its RCW 82.87 tax.

* **axiom** — the composed liability pipeline in rulespec-us
  (``us-XX/policies/income_tax/pilot_liability_pipeline``), evaluated through
  the axiom rules engine. The engine-computed liabilities are read from the
  committed ``.test.yaml`` fixtures, which ``axiom-encode test`` verifies equal
  the engine output to full decimal precision, so they are the engine's values
  rather than an independent re-implementation.
* **policyengine** — the configured per-state PolicyEngine liability target in
  ``_PE_VAR``, computed live at the 2026 tax year.
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

import sys
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import re

from axiom_oracles.comparison.dispositions import (
    apply_dispositions_from_dir,
    report_json_text,
)
from axiom_oracles.provenance import build_provenance, rulespec_provenance

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
    # Second all-state liability wave. Each pipeline landed together with an
    # engine-verified six-case fixture in the state-income-tax campaign.
    "DC": 9,
    "HI": 12,
    "IA": 16,
    "IN": 15,
    "LA": 19,
    "MT": 27,
    "NM": 32,
    "OK": 37,
    "OR": 38,
    "RI": 40,
    "NJ": 31,
    "SC": 41,
    "KS": 17,
    "ND": 35,
    "PA": 39,
    "MO": 26,
    "AR": 4,
    "MS": 25,
    "NH": 30,
    "WV": 49,
    "VT": 46,
    "WI": 50,
    # Washington's individual-income-tax surface is its RCW 82.87 capital-gains
    # excise tax, so it uses a capital-gains-specific grid below.
    "WA": 48,
    # Colorado (TAXSIM SOI code 6). Its rulespec-us composed pilot pipeline
    # (rulespec-us#942) applies the flat 39-22-104(1.7)(c) tax with the encoded
    # rate imported hash-pinned from the statute module.
    "CO": 6,
}
# PolicyEngine target per state. CA uses the before-refundable-credits variable;
# IL and OH use their before-non-refundable-credits schedule-tax variables, the
# exact statutory analogs of those cores. New York uses the narrower section
# 601 main-tax target because the supplemental-tax implementation diverges from
# the statute; Massachusetts has no refundable credits for these childless
# cases.
_PE_VAR = {
    "CA": "ca_income_tax_before_refundable_credits",
    "NY": "ny_main_income_tax",
    "IL": "il_income_tax_before_non_refundable_credits",
    "MA": "ma_income_tax",
    "OH": "oh_income_tax_before_non_refundable_credits",
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
    "AL": "al_income_tax_before_non_refundable_credits",
    "ID": "id_income_tax_before_refundable_credits",
    "KY": "ky_income_tax_before_refundable_credits",
    # Nebraska's before-credits variable is the pure 77-2715.03 four-bracket
    # progressive tax on Nebraska taxable income (AGI less the 77-2716.01 standard
    # deduction). The before-refundable variable nets the 77-2716.01 personal
    # exemption credit (a post-tax nonrefundable credit) that this core excludes.
    "NE": "ne_income_tax_before_credits",
    # Maine, Minnesota, and Connecticut use a before-refundable-credits variable
    # as the exact statutory analog of each composed pipeline. Delaware instead
    # targets the unit-level tax before nonrefundable credits because its promoted
    # RuleSpec encodes the section 1102 schedule and branch selection, not credits.
    # Delaware's later variables net nonrefundable credits and refundable EITC;
    # Maine and Minnesota net their refundable credits in the final variable;
    # Connecticut's target excludes refundable EITC while subtracting the ordered
    # property-tax and stillborn nonrefundable credits encoded by RuleSpec.
    # Maryland uses the state-only before-credits target: county tax is separate,
    # and the before-refundable target additionally subtracts nonrefundable credits.
    "DE": "de_income_tax_before_non_refundable_credits_unit",
    "MD": "md_income_tax_before_credits",
    "ME": "me_income_tax_before_refundable_credits",
    "MN": "mn_income_tax_before_refundable_credits",
    "CT": "ct_income_tax_before_refundable_credits",
    # Arizona levies a single flat rate (43-1011) on Arizona taxable income (AGI
    # less the 43-1041 standard deduction). az_income_tax equals
    # az_income_tax_before_refundable_credits on this childless grid (no refundable
    # credits active), so the final variable is the pipeline's exact target.
    "AZ": "az_income_tax_before_non_refundable_credits",
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
    # Second all-state liability wave. These targets are the closest statutory
    # analogs of the composed core schedules and exclude only credits or other
    # post-schedule adjustments that the narrow pilots intentionally omit.
    "DC": "dc_income_tax_before_credits",
    "HI": "hi_income_tax_before_non_refundable_credits",
    "IA": "ia_income_tax_before_credits",
    "IN": "in_agi_tax",
    "LA": "la_income_tax_before_non_refundable_credits",
    "MT": "mt_income_tax_before_non_refundable_credits_joint",
    "NM": "nm_income_tax_before_non_refundable_credits",
    "OK": "ok_income_tax_before_credits",
    "OR": "or_income_tax_before_credits",
    "RI": "ri_income_tax_before_non_refundable_credits",
    "NJ": "nj_main_income_tax",
    "SC": "sc_income_tax_before_non_refundable_credits",
    "KS": "ks_income_tax_before_credits",
    "ND": "nd_income_tax_before_credits",
    "PA": "pa_income_tax_before_forgiveness",
    "MO": "mo_income_tax_before_credits",
    "AR": "ar_income_tax_before_non_refundable_credits_unit",
    "MS": "ms_income_tax_before_credits_unit",
    # New Hampshire's zero is the legal consequence of RSA Chapter 77's
    # repeal, not an operative zero-rate schedule. PolicyEngine retains legacy
    # Chapter 77 base machinery but gates the tax out at 2026.
    "NH": "nh_income_tax_before_refundable_credits",
    # West Virginia's before-non-refundable-credits variable is the exact
    # section 11-21-4J schedule-tax analog for 2026.
    "WV": "wv_income_tax_before_non_refundable_credits",
    # Vermont's before-non-refundable-credits variable is the section 5822
    # schedule-or-three-percent-minimum analog; the narrow pipeline excludes
    # the later charitable and other nonrefundable credits.
    "VT": "vt_income_tax_before_non_refundable_credits",
    "WI": "wi_income_tax_before_credits",
    "WA": "wa_income_tax_before_refundable_credits",
    # Colorado's before-non-refundable variable is the exact 39-22-104(1.7)(c)
    # flat-tax analog on this grid, and it matches the composed pipeline to the
    # cent at the pinned policyengine-us on all six cases. The 39-22-627
    # temporary-rate mechanism is inactive at the 2026 validation year. TAXSIM
    # residuals are 2024-vintage plus a concept difference (siitax nets the 2024
    # TABOR sales-tax refund); each is decomposed exactly in dispositions.
    "CO": "co_income_tax_before_non_refundable_credits",
}
# The Populace registry covers every declared campaign jurisdiction, including
# narrow surfaces that are intentionally not valid legacy six-case grids.
_POPULACE_STATES = tuple(_TAXSIM_STATE)

# Arkansas's reviewed 2026 RuleSpec exposes only a Person-grain schedule
# component and boundary fixtures. It has no broad liability output or six
# standard grid fixtures, so retaining it here would silently reuse a deleted
# concept. Keep the reason explicit and independently testable while the
# Populace campaign validates the narrow component truthfully.
_GRID_EXCLUDED_STATES = {
    "AR": (
        "reviewed RuleSpec exposes only the Person-grain Act 2 schedule "
        "component; no broad liability output or six-case grid fixtures"
    ),
}

# Ordered grid state list; new eligible states append through _TAXSIM_STATE.
_STATES = tuple(
    state for state in _TAXSIM_STATE if state not in _GRID_EXCLUDED_STATES
)
_MODULE = {
    st: f"us-{st.lower()}:policies/income_tax/pilot_liability_pipeline"
    for st in _TAXSIM_STATE
}
_LIABILITY_OUTPUT = {
    st: f"{_MODULE[st]}#{st.lower()}_pit_pilot_income_tax_liability"
    for st in _TAXSIM_STATE
}
_LIABILITY_OUTPUT["NY"] = (
    f"{_MODULE['NY']}#ny_pit_pilot_main_income_tax"
)

# The Populace campaign may validate a narrower source-faithful surface than
# the legacy six-case grid. Keep these explicit so the grid's historical broad
# concept and artifacts do not get relabeled.
_POPULACE_OUTPUT = {
    "AR": (
        f"{_MODULE['AR']}#"
        "ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    ),
}
_POPULACE_PE_VAR = {
    "AR": "ar_income_tax_before_non_refundable_credits_indiv",
}
_POPULACE_AGGREGATION = {
    "AR": "person_sum_to_tax_unit",
}

# These comprehensive RuleSpec suites contain boundary/relation cases in
# addition to the six canonical liability-grid fixtures. For these states only,
# accept strict ``(single|married|joint)_<income>`` names and skip everything
# else. Other states retain the legacy AGI/suffix extraction behavior.
_STRICT_GRID_FIXTURE_STATES = frozenset({"MS", "NY"})


@dataclass
class Case:
    case_id: str
    state: str
    filing: str  # "single" | "married"
    wages: float


# Modest grid: single and married filers at incomes crossing common liability
# thresholds. Washington substitutes a long-term-capital-gains grid because its
# individual-tax surface is the RCW 82.87 capital-gains excise tax.
def _grid() -> list[Case]:
    cases: list[Case] = []
    plan = {
        "single": [30000, 60000, 150000],
        "married": [60000, 120000, 300000],
    }
    for state in _STATES:
        state_plan = plan
        if state == "WA":
            state_plan = {
                "single": [300000, 600000, 1500000],
                "married": [600000, 1200000, 3000000],
            }
        for filing, incomes in state_plan.items():
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
    for state in _STATES:
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
            inputs = case["input"]
            agi_key = next(
                (k for k in inputs if k.endswith("adjusted_gross_income")),
                None,
            )
            grid_name = re.fullmatch(r"(single|married|joint)_(\d+)", name)
            strict_grid_fixtures = state in _STRICT_GRID_FIXTURE_STATES
            if strict_grid_fixtures and grid_name is None:
                # Comprehensive boundary suites may contain many more cases
                # than the six standard comparison-grid fixtures. Only names
                # that explicitly bind a filing family and employment-income
                # case belong to these reports.
                continue
            # Preserve the existing adjusted-gross-income and fixture-suffix
            # mapping for every other state. The strict-grid pilots accept
            # completed-return taxable-income boundaries, so their fixture
            # names pin the wage grid case instead.
            agi = (
                int(grid_name.group(2))
                if strict_grid_fixtures
                else (
                    int(round(float(inputs[agi_key])))
                    if agi_key is not None
                    else int(name.rsplit("_", 1)[-1])
                )
            )
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
    income_variable = (
        "long_term_capital_gains" if case.state == "WA" else "employment_income"
    )
    people = {
        "head": {"age": {year: 40}, income_variable: {year: case.wages}}
    }
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
                "pwages": 0 if case.state == "WA" else case.wages,
                "swages": 0,
                "ltcg": case.wages if case.state == "WA" else 0,
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
    "NY": (2.25, 0.0000001),
    "IL": (5.0, 0.02),
    "MA": (1.0, 0.0),
    # Ohio's legacy grid retains a $1 band; the full-Populace registry below
    # applies the tighter reviewed absolute-or-relative tolerance.
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
    # Maryland, Maine, and Minnesota reproduce PolicyEngine to the cent (residual
    # is PolicyEngine's float32 rounding); a $1 absolute band catches structural
    # bracket errors without absorbing the 2024-to-2026 vintage on the TAXSIM leg.
    # Maryland's TAXSIM residual also
    # carries the county/local income tax that siitax includes but the state-only
    # target excludes; that scope gap is dispositioned, not absorbed by tolerance.
    # Delaware's full-population maximum absolute residual is $0.232, while every
    # value is within either one cent or 1e-7 relative error.
    "DE": (0.01, 0.0000001),
    "MD": (1.0, 0.0),
    "ME": (1.0, 0.0),
    "MN": (1.0, 0.0),
    # Connecticut's full-population maximum absolute residual is $0.4592, while
    # every value is within either one cent or 1e-7 relative error. The combined
    # tolerance rejects structural drift without failing large-value float noise.
    "CT": (0.01, 0.0000001),
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
    "DC": (1.0, 0.0),
    "HI": (1.0, 0.0),
    "IA": (1.0, 0.0),
    "IN": (1.0, 0.0),
    "LA": (1.0, 0.0),
    "MT": (1.0, 0.0),
    "NM": (1.0, 0.0),
    "OK": (1.0, 0.0),
    "OR": (1.0, 0.0),
    "RI": (1.0, 0.0),
    "NJ": (1.0, 0.0000001),
    "SC": (1.0, 0.0),
    "KS": (1.0, 0.0),
    "ND": (1.0, 0.0),
    "PA": (1.0, 0.0),
    "MO": (1.0, 0.0),
    "AR": (1.0, 0.0),
    "MS": (1.0, 0.0),
    "NH": (1.0, 0.0),
    "WV": (1.0, 0.0),
    "VT": (0.01, 0.0000001),
    "WI": (1.0, 0.0),
    "WA": (1.0, 0.0),
    # Colorado reproduces PolicyEngine to the cent on all six grid cases; a
    # $1 absolute band catches structural errors without absorbing anything.
    "CO": (1.0, 0.0),
}

# Full-Populace contracts may use tighter reviewed tolerances than the legacy
# mixed PolicyEngine/TAXSIM case grids. The grid tolerances above retain room
# for TAXSIM law-vintage differences; these overrides apply only to the pinned
# Populace registry check.
_POPULACE_TOL = {
    "AL": (0.01, 0.0000001),
    "AR": (0.01, 0.0000001),
    "AZ": (0.01, 0.0000001),
    "GA": (0.01, 0.0000001),
    "IL": (1.0, 0.0),
    "LA": (0.01, 0.0000001),
    "MT": (0.01, 0.0000001),
    "NM": (0.01, 0.0000001),
    "OH": (0.01, 0.0000001),
    "OK": (0.01, 0.0000001),
    "SC": (0.01, 0.0000001),
    "VA": (0.01, 0.0000001),
    "WV": (0.01, 0.0000001),
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
    # against these rows and validate that every residual is explained. Either
    # pairwise leg can emit a mismatch row (axiom is `left`); the dispositions
    # pin every expected PolicyEngine or TAXSIM residual.
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
        income_key = (
            "long_term_capital_gains"
            if state == "WA"
            else "employment_income"
        )
        report_cases.append(
            {
                "case_id": case.case_id,
                "concept": concept,
                "filing_status": case.filing,
                income_key: case.wages,
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
        if not pe_ok:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": concept,
                    "kind": "policyengine_amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax,
                    "right": pe_v,
                    "difference": ax - pe_v,
                }
            )
    # Each case always has two independent pairwise comparisons. Keep the
    # denominator stable even when one engine moves from mismatch to match, so
    # raw-match metrics remain comparable and monotonic across reruns.
    comparison_count = n * 2
    mismatch_count = len(mismatches)
    match_count = pe_matches + taxsim_matches
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
                "The mismatches array carries TAXSIM-2024 law-vintage residuals"
                " and any source-grounded Axiom-versus-PolicyEngine residuals;"
                " each must be dispositioned without widening tolerance."
            ),
        },
    }


def _finalize_report(
    report: dict,
    *,
    generated_at: str,
    rulespecs: list[dict],
) -> dict:
    """Attach dispositions and v2.1 provenance before publishing a report."""
    finalized = apply_dispositions_from_dir(
        report,
        REPO_ROOT / "dispositions",
        repo_root=REPO_ROOT,
    )
    finalized["provenance"] = build_provenance(
        generated_by=(
            "scripts/generate_state_income_tax_liability.py::"
            f"{report['suite']}"
        ),
        rulespecs=rulespecs,
        generated_at=generated_at,
    )
    return finalized


def main() -> int:
    cases = _grid()
    axiom = _axiom_liabilities()
    pe = {case.case_id: _policyengine_liability(case) for case in cases}
    taxsim = _taxsim_liabilities(cases)
    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rulespecs = rulespec_provenance([RULESPEC_US])
    for state in _STATES:
        report = _finalize_report(
            _build_report(state, cases, axiom, pe, taxsim),
            generated_at=generated_at,
            rulespecs=rulespecs,
        )
        basename = f"axiom-policyengine-taxsim-{state.lower()}-income-tax-liability"
        serialized = report_json_text(report)
        (REPORTS / f"{basename}-{stamp}.json").write_text(serialized)
        (DASH_PUBLIC / f"{basename}.json").write_text(serialized)
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
