#!/usr/bin/env python
"""Generate the composed state income-tax liability comparison reports.

For each registered state liability suite this script runs a modest single- and
married-filer grid through three independent computations and records a v2
comparison report plus the per-case residuals. Most states use wage-income cases
that cross their brackets; Washington uses a dedicated long-term-capital-gains
grid for its RCW 82.87 tax.

* **axiom** — the registered RuleSpec surface, evaluated through the axiom rules
  engine. Most legacy state grids read engine-verified values from committed
  ``.test.yaml`` fixtures. Canonical bounded surfaces such as Georgia accept
  reviewed completed-income inputs rather than constructing an annual return.
  Kentucky executes its canonical KRS 141.020 RuleSpec live.
* **policyengine** — the configured per-state PolicyEngine liability target in
  ``_PE_VAR``, computed live at the 2026 tax year.
* **taxsim** — the pinned policyengine-taxsim binary, run at 2026. The graded
  output column resolves from the concept mapping (``_taxsim_output_column``):
  ``staxbc`` (state tax before credits) for pre-credit schedule concepts,
  ``siitax`` for final-liability concepts. Any target-scope or model-vintage
  residual is recorded in dispositions rather than absorbed by tolerance.

Nothing here invents a value: the axiom side is the engine fixture, the
PolicyEngine side is a live calculation, and the TAXSIM side is the pinned
binary's output. Run with the axiom-oracles environment (PolicyEngine and
policyengine-taxsim installed):

    uv run --python 3.14 python scripts/generate_state_income_tax_liability.py
    uv run --python 3.14 python scripts/generate_state_income_tax_liability.py \
        --state GA
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, distribution
import math
import platform
import sys
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
import os
from pathlib import Path
import re

from axiom_oracles.comparison.dispositions import (
    apply_dispositions_from_dir,
    report_json_text,
)
from axiom_oracles.provenance import build_provenance, rulespec_provenance

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[1]
RULESPEC_US = Path(
    os.environ.get("RULESPEC_US_REPO", REPO_ROOT.parent / "rulespec-us")
).resolve()
AXIOM_RULES = Path(
    os.environ.get("AXIOM_RULES_REPO", REPO_ROOT.parent / "axiom-rules-engine")
).resolve()
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

VALIDATION_YEAR = 2026
TAXSIM_YEAR = 2026  # policyengine-taxsim 2.30.0 models 2026 law incl. OBBBA

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
    # New Hampshire is intentionally absent. RSA Chapter 77 was repealed in
    # its entirety effective January 1, 2025; the RuleSpec repeal-result module
    # is documentary and its constant zero is not a current-law comparison.
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
    # Synthetic name used in reports. Runtime calculation combines the pure
    # section 59-10-104 amount with the section 59-10-104.1 exemption.
    "UT": "ut_resident_income_tax_before_credits_derived",
    # Alabama's canonical section 40-18-5 surface maps only to the schedule
    # before nonrefundable credits; it does not claim final annual liability.
    # Kentucky's canonical KRS 141.020 schedule also applies before every
    # allowable credit, so its exact PolicyEngine analog is the unit-level tax
    # before nonrefundable credits. Idaho retains its reviewed target.
    "AL": "al_income_tax_before_non_refundable_credits",
    "ID": "id_income_tax_before_refundable_credits",
    "KY": "ky_income_tax_before_non_refundable_credits_unit",
    # Nebraska's before-credits variable is the pure 77-2715.03 four-bracket
    # progressive tax on Nebraska taxable income (AGI less the 77-2716.01 standard
    # deduction). The before-refundable variable nets the 77-2716.01 personal
    # exemption credit (a post-tax nonrefundable credit) that this core excludes.
    "NE": "ne_income_tax_before_credits",
    # Maine and Minnesota use a before-refundable-credits variable as the exact
    # statutory analog of each composed pipeline. Delaware's canonical campaign
    # target is instead the Person-grain individual schedule before
    # nonrefundable credits; the legacy grid is excluded below because it cannot
    # truthfully express Person aggregation or omit filing-method selection.
    # Maine and Minnesota net their refundable credits in the final variable;
    # Maryland uses the state-only before-credits target: county tax is separate,
    # and the before-refundable target additionally subtracts nonrefundable credits.
    "DE": "de_income_tax_before_non_refundable_credits_indv",
    "MD": "md_income_tax_before_credits",
    "ME": "me_income_tax_before_refundable_credits",
    "MN": "mn_income_tax_before_refundable_credits",
    "CT": "ct_resident_ordinary_tax_before_personal_credit_derived",
    # Arizona levies a single flat rate (43-1011) on Arizona taxable income (AGI
    # less the 43-1041 standard deduction). az_income_tax equals
    # az_income_tax_before_refundable_credits on this childless grid (no refundable
    # credits active), so the final variable is the pipeline's exact target.
    "AZ": "az_income_tax_before_non_refundable_credits",
    # Georgia's target is the direct section 48-7-20 annual-tax analog. The
    # canonical RuleSpec accepts completed Georgia taxable net income from the
    # distinct upstream ga_taxable_income variable and applies only the 4.99
    # percent rate; it does not construct deductions or other return inputs.
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
    "MS": "ms_income_tax_before_credits_joint",
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
    "AL": (
        "canonical RuleSpec exposes only the section 40-18-5 schedule on "
        "completed taxable income; no broad annual-liability or TAXSIM surface"
    ),
    "AR": (
        "reviewed RuleSpec exposes only the Person-grain Act 2 schedule "
        "component; no broad liability output or six-case grid fixtures"
    ),
    "CT": (
        "canonical RuleSpec exposes the full-year-resident ordinary section "
        "12-700 component with a 98-fixture boundary suite; no broad liability "
        "output or legacy six-case grid fixtures"
    ),
    "DE": (
        "canonical RuleSpec comparison exposes only the Person-grain section "
        "1102(a)(14) individual schedule; no filing-method selector, broad "
        "TaxUnit liability output, or truthful TAXSIM comparison surface"
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
_MODULE["AL"] = (
    "us-al:policies/income_tax/"
    "2026_section_40_18_5_schedule_before_credits"
)
_MODULE["CT"] = (
    "us-ct:policies/income_tax/"
    "2026_resident_ordinary_tax_before_personal_credit"
)
_MODULE["GA"] = (
    "us-ga:policies/income_tax/2026_annual_tax_before_nonrefundable_credits"
)
_MODULE["KY"] = (
    "us-ky:policies/income_tax/2026_krs_141_020_schedule_before_credits"
)
_MODULE["MS"] = "us-ms:policies/income_tax/2026_section_27_7_5_schedule"
_MODULE["UT"] = (
    "us-ut:policies/income_tax/"
    "2026_full_year_resident_before_credit_schedule"
)
_LIABILITY_OUTPUT = {
    st: f"{_MODULE[st]}#{st.lower()}_pit_pilot_income_tax_liability"
    for st in _TAXSIM_STATE
}
_LIABILITY_OUTPUT["AL"] = (
    f"{_MODULE['AL']}#"
    "al_pit_2026_section_40_18_5_schedule_before_credits"
)
_LIABILITY_OUTPUT["CT"] = (
    f"{_MODULE['CT']}#ct_pit_2026_resident_ordinary_tax_before_personal_credit"
)
_LIABILITY_OUTPUT["DE"] = (
    f"{_MODULE['DE']}#de_pit_pilot_separate_schedule_tax"
)
_LIABILITY_OUTPUT["GA"] = (
    f"{_MODULE['GA']}#ga_pit_2026_annual_tax_before_nonrefundable_credits"
)
_LIABILITY_OUTPUT["KY"] = (
    f"{_MODULE['KY']}#ky_pit_2026_krs_141_020_schedule_before_credits"
)
_LIABILITY_OUTPUT["MS"] = (
    f"{_MODULE['MS']}#ms_pit_2026_section_27_7_5_schedule_tax"
)
_LIABILITY_OUTPUT["UT"] = (
    f"{_MODULE['UT']}#ut_pit_2026_resident_income_tax_before_credits"
)

_LIABILITY_OUTPUT["NY"] = (
    f"{_MODULE['NY']}#ny_pit_pilot_main_income_tax"
)

# The Populace campaign may validate a narrower source-faithful surface than
# the legacy six-case grid. Keep these explicit so the grid's historical broad
# concept and artifacts do not get relabeled.
_POPULACE_MODULE = {
    "CA": _MODULE["CA"],
    "DC": (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits"
    ),
    "KS": "us-ks:policies/income_tax/2026_k40es_schedule_before_credits",
    "MN": _MODULE["MN"],
}
_POPULACE_OUTPUT = {
    "AR": (
        f"{_MODULE['AR']}#"
        "ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    ),
    "CA": (
        f"{_POPULACE_MODULE['CA']}#"
        "ca_pit_pilot_behavioral_health_services_tax"
    ),
    "CT": _LIABILITY_OUTPUT["CT"],
    "DC": (
        f"{_POPULACE_MODULE['DC']}#"
        "dc_pit_2026_section_47_1806_03_schedule_before_credits"
    ),
    "DE": _LIABILITY_OUTPUT["DE"],
    "KS": (
        f"{_POPULACE_MODULE['KS']}#"
        "ks_pit_2026_k40es_schedule_before_credits"
    ),
    "MS": _LIABILITY_OUTPUT["MS"],
    "MN": f"{_POPULACE_MODULE['MN']}#mn_pit_pilot_schedule_tax",
    "OH": f"{_MODULE['OH']}#oh_pit_pilot_schedule_tax",
    "UT": _LIABILITY_OUTPUT["UT"],
}
_POPULACE_PE_VAR = {
    "AR": "ar_income_tax_before_non_refundable_credits_indiv",
    "CA": "ca_mental_health_services_tax",
    "CT": "ct_resident_ordinary_tax_before_personal_credit_derived",
    "DC": "dc_income_tax_before_credits_joint",
    "DE": "de_income_tax_before_non_refundable_credits_indv",
    "KS": "ks_k40es_schedule_before_credits_reviewed",
    "MS": "ms_income_tax_before_credits_joint",
    "MN": "mn_basic_tax_precision_stable",
    "OH": "oh_nonbusiness_income_tax_before_non_refundable_credits_derived",
    "UT": "ut_resident_income_tax_before_credits_derived",
}
_POPULACE_AGGREGATION = {
    "AR": "person_sum_to_tax_unit",
    "DE": "person_sum_to_tax_unit",
    "MS": "person_sum_to_tax_unit",
}

# These comprehensive RuleSpec suites contain boundary/relation cases in
# addition to the six canonical liability-grid fixtures. For these states only,
# accept strict ``(single|married|joint)_<income>`` names and skip everything
# else. Other states retain the legacy AGI/suffix extraction behavior.
_STRICT_GRID_FIXTURE_STATES = frozenset({"CO", "GA", "NY"})
_LIVE_AXIOM_STATES = frozenset({"KY", "MS", "UT"})


@dataclass
class Case:
    case_id: str
    state: str
    filing: str  # "single" | "married"
    wages: float


# Modest grid: single and married filers at incomes crossing common liability
# thresholds. Washington substitutes a long-term-capital-gains grid because its
# individual-tax surface is the RCW 82.87 capital-gains excise tax.
def _grid(states: tuple[str, ...] | None = None) -> list[Case]:
    cases: list[Case] = []
    plan = {
        "single": [30000, 60000, 150000],
        "married": [60000, 120000, 300000],
    }
    for state in _STATES if states is None else states:
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


def _axiom_liabilities(
    states: tuple[str, ...] | None = None,
) -> dict[tuple[str, str, int], float]:
    """Read the engine-verified pipeline liabilities from the test fixtures.

    ``axiom-encode test`` proves these equal the axiom rules-engine output to
    full decimal precision, so they are the engine's liabilities. The fixture
    inputs may be a pipeline's AGI/base-income or a canonical surface's
    completed taxable-income boundary. For strict-grid states, the fixture name
    preserves the historical wage-grid label; it does not make RuleSpec derive
    that upstream boundary.
    """
    import yaml

    out: dict[tuple[str, str, int], float] = {}
    for state in _STATES if states is None else states:
        if state in _LIVE_AXIOM_STATES:
            continue
        jurisdiction, module_path = _MODULE[state].split(":", 1)
        test_file = RULESPEC_US / jurisdiction / f"{module_path}.test.yaml"
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
            try:
                agi = (
                    int(grid_name.group(2))
                    if strict_grid_fixtures
                    else (
                        int(round(float(inputs[agi_key])))
                        if agi_key is not None
                        else int(name.rsplit("_", 1)[-1])
                    )
                )
            except ValueError:
                # Upstream boundary/regression fixtures whose names carry no
                # wage-grid income (e.g. `single_retirement_income`) are not
                # comparison-grid cases — skip them instead of aborting the
                # whole state grid (which used to silently reuse stale data).
                continue
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


def _policyengine_simulation(case: Case):
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
    return Simulation(situation=situation)


def _policyengine_liability(case: Case) -> float:
    if case.state == "UT":
        return _utah_policyengine_values(case)[0]
    sim = _policyengine_simulation(case)
    return float(sim.calculate(_PE_VAR[case.state], VALIDATION_YEAR)[0])


def _exact_one_policyengine_value(sim, variable: str):
    result = sim.calculate(variable, VALIDATION_YEAR)
    raw = result.values if hasattr(result, "values") else result
    try:
        values = list(raw)
    except TypeError as exc:
        raise RuntimeError(
            f"Utah {variable} must return exactly one value; got a scalar"
        ) from exc
    if len(values) != 1:
        raise RuntimeError(
            f"Utah {variable} must return exactly one value; got {len(values)}"
        )
    value = values[0]
    return value.item() if hasattr(value, "item") else value


def _finite_utah_number(sim, variable: str) -> float:
    value = _exact_one_policyengine_value(sim, variable)
    if isinstance(value, bool):
        raise RuntimeError(f"Utah {variable} did not return a finite numeric value")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Utah {variable} did not return a finite numeric value"
        ) from exc
    if not math.isfinite(number):
        raise RuntimeError(f"Utah {variable} did not return a finite numeric value")
    return number


def _utah_policyengine_values(case: Case) -> tuple[float, float, bool]:
    """Return the derived target and its two reviewed upstream boundaries."""

    if case.state != "UT":
        raise ValueError("Utah projection requested for a non-Utah case")
    sim = _policyengine_simulation(case)
    taxable_income = _finite_utah_number(sim, "ut_taxable_income")
    before_credits = _finite_utah_number(
        sim, "ut_income_tax_before_credits"
    )
    if before_credits < 0:
        raise RuntimeError(
            "Utah ut_income_tax_before_credits must be nonnegative"
        )
    exempt_value = _exact_one_policyengine_value(sim, "ut_income_tax_exempt")
    if not isinstance(exempt_value, bool):
        raise RuntimeError(
            "Utah ut_income_tax_exempt did not return a strict Boolean"
        )
    return (
        0.0 if exempt_value else before_credits,
        taxable_income,
        exempt_value,
    )


def _kentucky_policyengine_values(case: Case) -> tuple[float, float]:
    """Return the direct target and its reviewed completed-net-income boundary."""

    if case.state != "KY":
        raise ValueError("Kentucky projection requested for a non-Kentucky case")
    sim = _policyengine_simulation(case)
    separate = sum(
        float(value)
        for value in sim.calculate("ky_taxable_income_indiv", VALIDATION_YEAR)
    )
    joint = sum(
        float(value)
        for value in sim.calculate("ky_taxable_income_joint", VALIDATION_YEAR)
    )
    filing_separately = bool(
        sim.calculate("ky_files_separately", VALIDATION_YEAR)[0]
    )
    completed_net_income = max(
        0.0,
        separate if filing_separately else joint,
    )
    target = float(
        sim.calculate(
            "ky_income_tax_before_non_refundable_credits_unit",
            VALIDATION_YEAR,
        )[0]
    )
    return target, completed_net_income


def _mississippi_policyengine_values(
    case: Case,
) -> tuple[float, tuple[float, ...]]:
    """Return the joint/default Person target and its exact upstream values."""

    if case.state != "MS":
        raise ValueError("Mississippi projection requested for a non-MS case")
    sim = _policyengine_simulation(case)
    completed_taxable_income = tuple(
        float(value)
        for value in sim.calculate("ms_taxable_income_joint", VALIDATION_YEAR)
    )
    target = sum(
        float(value)
        for value in sim.calculate(
            "ms_income_tax_before_credits_joint",
            VALIDATION_YEAR,
        )
    )
    return target, completed_taxable_income


def _kentucky_axiom_liabilities(
    cases: list[Case],
    completed_net_income: dict[str, float],
) -> dict[tuple[str, str, int], float]:
    """Execute the canonical Kentucky RuleSpec over reviewed upstream inputs."""

    from axiom_oracles.bridges.state_tax_populace_runner import (
        DISPOSITION_READY,
        TaxUnitRoute,
        _state_request,
    )
    from axiom_oracles.bridges.tax_populace import (
        output_number,
        run_axiom_program,
    )

    kentucky_cases = [case for case in cases if case.state == "KY"]
    input_slot = (
        f"{_MODULE['KY']}#input."
        "ky_pit_2026_krs_141_020_completed_net_income"
    )
    routes = tuple(
        TaxUnitRoute(
            case.case_id,
            case.case_id,
            "KY",
            "21",
            1.0,
            DISPOSITION_READY,
        )
        for case in kentucky_cases
    )
    request = _state_request(
        state="KY",
        routes=routes,
        year=VALIDATION_YEAR,
        output=_LIABILITY_OUTPUT["KY"],
        projected_inputs={
            input_slot: {
                case.case_id: completed_net_income[case.case_id]
                for case in kentucky_cases
            }
        },
    )
    program = (
        RULESPEC_US
        / "us-ky"
        / "policies"
        / "income_tax"
        / "2026_krs_141_020_schedule_before_credits.yaml"
    )
    results = run_axiom_program(
        program=program,
        request=request,
        rulespec_root=RULESPEC_US,
        axiom_rules_path=AXIOM_RULES,
    )
    if len(results) != len(kentucky_cases):
        raise RuntimeError(
            "Kentucky live RuleSpec execution returned "
            f"{len(results)} results for {len(kentucky_cases)} cases"
        )
    return {
        (case.state, case.filing, int(case.wages)): output_number(
            result["outputs"][_LIABILITY_OUTPUT["KY"]]
        )
        for case, result in zip(kentucky_cases, results, strict=True)
    }


def _mississippi_axiom_liabilities(
    cases: list[Case],
    completed_taxable_income: dict[str, tuple[float, ...]],
) -> dict[tuple[str, str, int], float]:
    """Execute the canonical Person schedule over the reviewed joint boundary."""

    import pandas as pd

    from axiom_oracles.bridges.state_tax_populace_runner import (
        DISPOSITION_READY,
        TaxUnitRoute,
        _person_entity_id,
        _state_request,
    )
    from axiom_oracles.bridges.tax_populace import (
        output_number,
        run_axiom_program,
    )

    mississippi_cases = [case for case in cases if case.state == "MS"]
    if not mississippi_cases:
        return {}
    input_slot = (
        f"{_MODULE['MS']}#input.ms_pit_2026_supplied_taxable_income"
    )
    routes = tuple(
        TaxUnitRoute(
            case.case_id,
            case.case_id,
            "MS",
            "28",
            1.0,
            DISPOSITION_READY,
        )
        for case in mississippi_cases
    )
    raw_person_rows = []
    projected_values: dict[str, float] = {}
    person_ids_by_case: dict[str, list[str]] = {}
    for case in mississippi_cases:
        person_ids = []
        for index, value in enumerate(completed_taxable_income[case.case_id]):
            person_id = f"{case.case_id}-person-{index}"
            person_ids.append(person_id)
            raw_person_rows.append(
                {
                    "person_id": person_id,
                    "person_tax_unit_id": case.case_id,
                }
            )
            projected_values[person_id] = value
        person_ids_by_case[case.case_id] = person_ids
    request = _state_request(
        state="MS",
        routes=routes,
        year=VALIDATION_YEAR,
        output=_LIABILITY_OUTPUT["MS"],
        projected_inputs={input_slot: projected_values},
        raw_persons=pd.DataFrame(raw_person_rows),
        all_tax_unit_ids={case.case_id for case in mississippi_cases},
        comparison_aggregation="person_sum_to_tax_unit",
    )
    program = (
        RULESPEC_US
        / "us-ms"
        / "policies"
        / "income_tax"
        / "2026_section_27_7_5_schedule.yaml"
    )
    results = run_axiom_program(
        program=program,
        request=request,
        rulespec_root=RULESPEC_US,
        axiom_rules_path=AXIOM_RULES,
    )
    expected_result_count = sum(map(len, person_ids_by_case.values()))
    if len(results) != expected_result_count:
        raise RuntimeError(
            "Mississippi live RuleSpec execution returned "
            f"{len(results)} results for {expected_result_count} people"
        )
    expected_entities = {
        _person_entity_id(person_id)
        for person_ids in person_ids_by_case.values()
        for person_id in person_ids
    }
    results_by_entity: dict[str, dict] = {}
    for result in results:
        entity_id = result.get("entity_id")
        if (
            not isinstance(entity_id, str)
            or entity_id not in expected_entities
            or entity_id in results_by_entity
        ):
            raise RuntimeError(
                "Mississippi live RuleSpec execution returned an unexpected "
                f"or duplicate Person entity_id: {entity_id!r}"
            )
        results_by_entity[entity_id] = result
    missing_entities = expected_entities - results_by_entity.keys()
    if missing_entities:
        raise RuntimeError(
            "Mississippi live RuleSpec execution omitted Person entity_id(s): "
            + ", ".join(sorted(missing_entities))
        )

    output: dict[tuple[str, str, int], float] = {}
    for case in mississippi_cases:
        total = 0.0
        for person_id in person_ids_by_case[case.case_id]:
            result = results_by_entity[_person_entity_id(person_id)]
            total += output_number(result["outputs"][_LIABILITY_OUTPUT["MS"]])
        output[(case.state, case.filing, int(case.wages))] = total
    return output


def _utah_axiom_liabilities(
    cases: list[Case],
    policyengine_values: dict[str, tuple[float, float, bool]],
) -> dict[tuple[str, str, int], float]:
    """Execute the canonical Utah surface over exact reviewed projections."""

    from axiom_oracles.bridges.state_tax_populace_runner import (
        DISPOSITION_READY,
        TaxUnitRoute,
        _state_request,
        _tax_unit_entity_id,
    )
    from axiom_oracles.bridges.tax_populace import (
        output_number,
        run_axiom_program,
    )

    utah_cases = [case for case in cases if case.state == "UT"]
    if not utah_cases:
        return {}
    prefix = f"{_MODULE['UT']}#input."
    slots = {
        "taxable": f"{prefix}ut_pit_2026_state_taxable_income",
        "resident": f"{prefix}ut_pit_2026_is_full_year_utah_resident_return",
        "aligned": (
            f"{prefix}ut_pit_2026_federal_and_utah_filing_units_are_aligned"
        ),
        "exempt": (
            f"{prefix}ut_pit_2026_is_exempt_under_section_59_10_104_1"
        ),
    }
    routes = tuple(
        TaxUnitRoute(
            case.case_id,
            case.case_id,
            "UT",
            "49",
            1.0,
            DISPOSITION_READY,
        )
        for case in utah_cases
    )
    request = _state_request(
        state="UT",
        routes=routes,
        year=VALIDATION_YEAR,
        output=_LIABILITY_OUTPUT["UT"],
        projected_inputs={
            slots["taxable"]: {
                case.case_id: policyengine_values[case.case_id][1]
                for case in utah_cases
            },
            slots["resident"]: {
                case.case_id: True for case in utah_cases
            },
            slots["aligned"]: {
                case.case_id: True for case in utah_cases
            },
            slots["exempt"]: {
                case.case_id: policyengine_values[case.case_id][2]
                for case in utah_cases
            },
        },
    )
    program = (
        RULESPEC_US
        / "us-ut"
        / "policies"
        / "income_tax"
        / "2026_full_year_resident_before_credit_schedule.yaml"
    )
    results = run_axiom_program(
        program=program,
        request=request,
        rulespec_root=RULESPEC_US,
        axiom_rules_path=AXIOM_RULES,
    )
    if len(results) != len(utah_cases):
        raise RuntimeError(
            "Utah live RuleSpec execution returned "
            f"{len(results)} results for {len(utah_cases)} cases"
        )
    expected_entities = {
        _tax_unit_entity_id(case.case_id) for case in utah_cases
    }
    results_by_entity: dict[str, dict] = {}
    for result in results:
        entity_id = result.get("entity_id")
        if (
            not isinstance(entity_id, str)
            or entity_id not in expected_entities
            or entity_id in results_by_entity
        ):
            raise RuntimeError(
                "Utah live RuleSpec execution returned an unexpected or "
                f"duplicate TaxUnit entity_id: {entity_id!r}"
            )
        results_by_entity[entity_id] = result
    missing_entities = expected_entities - results_by_entity.keys()
    if missing_entities:
        raise RuntimeError(
            "Utah live RuleSpec execution omitted TaxUnit entity_id(s): "
            + ", ".join(sorted(missing_entities))
        )
    return {
        (case.state, case.filing, int(case.wages)): output_number(
            results_by_entity[_tax_unit_entity_id(case.case_id)]["outputs"][
                _LIABILITY_OUTPUT["UT"]
            ]
        )
        for case in utah_cases
    }


def _taxsim_binary() -> Path | None:
    """Resolve the pinned TAXSIM binary explicitly.

    policyengine-taxsim's own detection searches sys.prefix/share, which is
    empty in ephemeral `uv run` environments (the wheel's data files don't
    land there) — that failure used to silently cap these grids at stale
    committed data. Fall back to the repo venv's share/, where the vetted
    binary from the pinned wheel lives.
    """
    exe = {
        "darwin": "taxsimtest-osx.exe",
        "linux": "taxsimtest-linux.exe",
        "windows": "taxsimtest-windows.exe",
    }.get(platform.system().lower())
    if exe is None:
        return None
    tail = Path("share") / "policyengine_taxsim" / "taxsimtest" / exe
    try:
        installed = distribution("policyengine-taxsim")
    except PackageNotFoundError:
        installed = None
    if installed is not None:
        for packaged_path in installed.files or ():
            if str(packaged_path).endswith(
                f"share/policyengine_taxsim/taxsimtest/{exe}"
            ):
                candidate = Path(installed.locate_file(packaged_path)).resolve()
                if candidate.exists():
                    return candidate
    for root in (Path(sys.prefix), REPO_ROOT / ".venv"):
        candidate = root / tail
        if candidate.exists():
            return candidate
    return None


def _taxsim_output_column(state: str) -> str:
    """The TAXSIM output column graded for a state's liability concept.

    Resolved from the concept mapping so the comparison surface stays
    declared in one place: states whose canonical concept is a pre-credit
    schedule map ``staxbc`` (state tax before credits — staxbc - v40 =
    siitax on the pinned binary); final-liability concepts map ``siitax``.
    Falls back to ``siitax`` for concepts the mapping does not know.
    """
    from axiom_oracles.comparison.mappings import engine_targets_for_concepts

    targets = engine_targets_for_concepts(
        [_LIABILITY_OUTPUT[state]], "taxsim"
    )
    return targets[0] if targets else "siitax"


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
    runner = TaxsimRunner(frame, taxsim_path=_taxsim_binary())
    try:
        result = runner.run(show_progress=False)
    except TypeError:
        result = runner.run()
    records = result.to_dict(orient="records")
    return {
        case.case_id: float(rec[_taxsim_output_column(case.state)])
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
    # Alabama and Idaho retain a $1 legacy-grid band. Kentucky executes the
    # canonical decimal RuleSpec live from PolicyEngine's reviewed upstream
    # taxable-income candidates, so a cent-or-1e-7 tolerance admits only the
    # upstream engine's float residual.
    "AL": (1.0, 0.0),
    "ID": (1.0, 0.0),
    "KY": (0.01, 0.0000001),
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
    "MS": (0.01, 0.0000001),
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
    "DE": (0.01, 0.0000001),
    "CA": (0.01, 0.0000001),
    "CO": (0.01, 0.0000001),
    "DC": (0.01, 0.0000001),
    "GA": (0.01, 0.0000001),
    "IL": (1.0, 0.0),
    "KY": (0.01, 0.0000001),
    "KS": (0.01, 0.0000001),
    "MS": (0.01, 0.0000001),
    "MN": (1.0, 0.0),
    "LA": (0.01, 0.0000001),
    "MT": (0.01, 0.0000001),
    "NM": (0.01, 0.0000001),
    "OH": (0.01, 0.0000001),
    "OK": (0.01, 0.0000001),
    "SC": (0.01, 0.0000001),
    "UT": (0.01, 0.0000001),
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
                "taxsim": ts_v,
                "axiom_vs_policyengine": {
                    "difference": ax - pe_v,
                    "match": pe_ok,
                },
                "axiom_vs_taxsim": {
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
            "taxsim": _taxsim_output_column(state),
        },
        "tolerance": {"absolute": tol, "relative": rel},
        "case_count": n,
        "summary": {
            "comparison_count": comparison_count,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "axiom_vs_policyengine_match_rate": round(100.0 * pe_matches / n, 2),
            "axiom_vs_taxsim_match_rate": round(100.0 * taxsim_matches / n, 2),
            "policyengine_matches": pe_matches,
            "taxsim_matches": taxsim_matches,
        },
        "mismatches": mismatches,
        "cases": report_cases,
        "provenance": {
            "generated": date.today().isoformat(),
            "generator": "scripts/generate_state_income_tax_liability.py",
            "axiom_source": (
                "live canonical KRS 141.020 RuleSpec execution over reviewed "
                "PolicyEngine upstream completed-net-income projections"
                if state == "KY"
                else (
                    "live canonical section 27-7-5 Person schedule execution "
                    "over reviewed PolicyEngine joint/default completed-taxable-"
                    "income projections"
                    if state == "MS"
                    else "engine-verified RuleSpec companion fixtures"
                )
            ),
            "note": (
                "The mismatches array carries TAXSIM law-vintage residuals"
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate state income-tax comparison reports."
    )
    parser.add_argument(
        "--state",
        choices=_STATES,
        help="Regenerate only the selected state instead of every grid state.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    selected_states = (args.state,) if args.state else _STATES
    cases = _grid(selected_states)
    axiom = _axiom_liabilities(selected_states)
    kentucky_values = {
        case.case_id: _kentucky_policyengine_values(case)
        for case in cases
        if case.state == "KY"
    }
    axiom.update(
        _kentucky_axiom_liabilities(
            cases,
            {
                case_id: values[1]
                for case_id, values in kentucky_values.items()
            },
        )
    )
    mississippi_values = {
        case.case_id: _mississippi_policyengine_values(case)
        for case in cases
        if case.state == "MS"
    }
    axiom.update(
        _mississippi_axiom_liabilities(
            cases,
            {
                case_id: values[1]
                for case_id, values in mississippi_values.items()
            },
        )
    )
    utah_values = {
        case.case_id: _utah_policyengine_values(case)
        for case in cases
        if case.state == "UT"
    }
    axiom.update(_utah_axiom_liabilities(cases, utah_values))
    # States whose reviewed RuleSpec has migrated its companion tests from the
    # six-case wage grid to boundary fixtures can no longer seed the Axiom
    # side of this report from fixtures. Skip them LOUDLY — the Populace
    # campaign (scripts/run_state_tax_populace.py) is their validation path —
    # instead of aborting the whole run, which used to silently freeze every
    # state's committed grid data.
    runnable = []
    for state in selected_states:
        missing = [
            (filing, wages)
            for case in cases
            if case.state == state
            for filing, wages in [(case.filing, int(case.wages))]
            if (state, filing, wages) not in axiom
        ]
        if missing:
            print(
                f"{state}: SKIPPED — fixtures no longer carry the six-case "
                f"grid ({len(missing)} of 6 cases missing); validated by the "
                "Populace campaign instead"
            )
        else:
            runnable.append(state)
    pe = {
        case.case_id: (
            kentucky_values[case.case_id][0]
            if case.state == "KY"
            else (
                mississippi_values[case.case_id][0]
                if case.state == "MS"
                else (
                    utah_values[case.case_id][0]
                    if case.state == "UT"
                    else _policyengine_liability(case)
                )
            )
        )
        for case in cases
        if case.state in runnable
    }
    taxsim = _taxsim_liabilities([c for c in cases if c.state in runnable])
    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rulespecs = rulespec_provenance([RULESPEC_US])
    for state in runnable:
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
            f"TAXSIM match {s['axiom_vs_taxsim_match_rate']}% "
            f"({s['taxsim_matches']}/{report['case_count']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
