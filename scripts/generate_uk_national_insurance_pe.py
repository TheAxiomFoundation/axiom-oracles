#!/usr/bin/env python3
"""National Insurance case grid: rulespec-uk vs PolicyEngine-UK, 2026-27 to 2030-31.

Compares the encoded employee (Class 1 primary) and self-employed (Class 4,
Class 2) National Insurance surfaces against PolicyEngine-UK on a synthetic
earnings/profits grid for the tax years 2026-27 through 2030-31.

Unlike the EFRS NICs surfaces (which feed PolicyEngine's own thresholds, and
for Class 4 its ``ni_class_4_main``, into the Axiom modules), every Axiom
threshold and amount here comes from Axiom modules:

* Class 1: ``uk/statutes/social_security/workers/pilot_worker_class_1_nic_pipeline``
  on the annual earnings. The earnings are PolicyEngine's own
  ``ni_class_1_income``, so both engines charge the same base; from 2029
  PolicyEngine scales employment income by a modelled incidence adjustment
  (30,000 becomes 29,952). The pipeline derives the annual primary threshold and
  upper earnings limit from the personal allowance and basic rate limit (frozen
  at 12,570 / 37,700 through 2030-31 by FA 2021 s.5 as amended by FA 2026 s.10).
  Beyond 2026-27 the NICs figures themselves are announced policy, not yet
  legislated (SSCBA 1992 s.5(1): set "for that year by regulations").
* Class 4: ``uk/statutes/ukpga/1992/4/15`` (SSCBA 1992 s.15, lower/upper profits
  limits 12,570 / 50,270, altered only by a s.141 SSAA 1992 order) on the
  profits, then ``uk/regulations/uksi/2001/1004/100`` (the regulation 100 annual
  maximum) on the s.15 outputs. The harness passes s.15 outputs into regulation
  100 inputs: an Axiom-to-Axiom composition, no PolicyEngine value enters.
* Class 2: the self-employed pilot pipeline's Class 2 amount payable.

PolicyEngine-UK runs one person per household with only the relevant income.
Each mismatch row carries ``pe_mechanism``: the documented PolicyEngine
behaviour its value reconciles to (to the penny) under PolicyEngine's own
parameters. ``cpi_uprated_thresholds`` is PolicyEngine-UK#1879, which
CPI-uprates the NICs thresholds that are frozen to April 2031.
``float32_drops_additional_band`` is PolicyEngine-UK#1878, where
``ni_class_4_maximum`` takes regulation 100 case 1 and drops the 2% band once
float32 rounding separates two equal amounts. A row whose PolicyEngine value
matches neither mechanism is ``unreconciled`` and stays unexplained.
``scripts/build_uk_national_insurance_pe_dispositions.py`` turns the reconciled
rows into selector-bound dispositions.

Four ``float32-isolation`` cases supply non-round Class 4 limits to both engines
(a PolicyEngine parameter reform; the regulation 100 module's own limit inputs,
with the s.15 amounts at those limits computed by the harness in exact decimal).
They isolate PolicyEngine-UK#1878 from the threshold freeze, since the freeze fix
alone makes the limits round again.

Run (needs the pinned PolicyEngine-UK, a built axiom rules engine and a
rulespec-uk checkout)::

    POLICYENGINE_UK_VERSION=2.102.0 RULESPEC_UK_CHECKOUT=/path/to/rulespec-uk \\
      AXIOM_RULES_ENGINE_BINARY=/path/to/axiom-rules-engine \\
      uv run --no-project --with-editable . --with policyengine-uk==2.102.0 \\
      python scripts/generate_uk_national_insurance_pe.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

SUITE = "uk-national-insurance-pe"
REPORT_BASENAME = "axiom-policyengine-uk-national-insurance"
VALIDATION_YEARS = (2026, 2027, 2028, 2029, 2030)
POLICYENGINE_UK_VERSION = os.environ.get("POLICYENGINE_UK_VERSION", "2.102.0")

RULESPEC_UK = Path(
    os.environ.get("RULESPEC_UK_CHECKOUT")
    or os.path.expanduser("~/TheAxiomFoundation/rulespec-uk")
)

C1_PROGRAM = "uk/statutes/social_security/workers/pilot_worker_class_1_nic_pipeline.yaml"
C1_BASE = "uk:statutes/social_security/workers/pilot_worker_class_1_nic_pipeline"
S15_PROGRAM = "uk/statutes/ukpga/1992/4/15.yaml"
S15_BASE = "uk:statutes/ukpga/1992/4/15"
R100_PROGRAM = "uk/regulations/uksi/2001/1004/100.yaml"
R100_BASE = "uk:regulations/uksi/2001/1004/100"
SE_PROGRAM = "uk/statutes/social_security/workers/pilot_worker_self_employed_nic_pipeline.yaml"
SE_BASE = "uk:statutes/social_security/workers/pilot_worker_self_employed_nic_pipeline"

# Compared surfaces: short key -> (Axiom output id, PolicyEngine variable).
CONCEPTS = {
    "c1-main": (f"{C1_BASE}#uk_nic_pilot_main_primary_contribution", "ni_class_1_employee_primary"),
    "c1-additional": (
        f"{C1_BASE}#uk_nic_pilot_additional_primary_contribution",
        "ni_class_1_employee_additional",
    ),
    "c4-main": (f"{S15_BASE}#main_class_4_contribution", "ni_class_4_main"),
    "c4-maximum": (f"{R100_BASE}#class_4_annual_maximum", "ni_class_4_maximum"),
    "c4-total": (f"{R100_BASE}#class_4_contribution_after_annual_maximum", "ni_class_4"),
    "c2": (f"{SE_BASE}#uk_nic_pilot_se_class_2_amount_payable", "ni_class_2"),
}
CLASS_1_CONCEPTS = ("c1-main", "c1-additional")
CLASS_4_CONCEPTS = ("c4-main", "c4-maximum", "c4-total", "c2")
ISOLATION_CONCEPTS = ("c4-maximum", "c4-total")

# Earnings and profits include each statutory boundary and non-round amounts
# above the upper limits, where PolicyEngine's float32 arithmetic misbehaves.
EMPLOYEE_EARNINGS = (10000, 12570, 30000, 50270, 52301, 65432, 87654.32, 131071.37)
SELF_EMPLOYED_PROFITS = (10000, 12570, 30000, 50270, 52301, 65432, 98765.43, 131071.37)

# PolicyEngine-UK#1885 cases: employment plus self-employment in the 2026-27
# control year (where the thresholds agree), so the only difference is
# PolicyEngine deducting Class 1 from the Class 4 profits. (earnings, profits)
DUAL_EARNER_CASES = ((30000, 20000), (45000, 30000), (60000, 25000), (20000, 60000))
DUAL_EARNER_YEAR = 2026
DUAL_CONCEPTS = ("c4-main", "c4-maximum", "c4-total")

# PolicyEngine-UK#1878 isolating cases: non-round limits supplied to both
# engines (PolicyEngine's own CPI-uprated 2027-2030 values, rounded to the
# penny so every harness amount is an exact decimal; see _axiom_rows).
ISOLATION_CASES = (
    (2027, 12821.38, 51275.32, 100000),
    (2028, 13077.80, 52300.78, 65432),
    (2029, 13339.32, 53346.68, 87654.32),
    (2030, 13606.11, 54413.63, 300000),
)

MAIN_PRIMARY_PERCENTAGE = 0.08
ADDITIONAL_PRIMARY_PERCENTAGE = 0.02
WEEKS_IN_YEAR = 52

_TOLERANCE = 0.01
_RELATIVE_TOLERANCE = 2e-7
_RECONCILE_TOLERANCE = 0.01

UK_SCOPE = {"type": "country", "geoid": "UK"}


@dataclass(frozen=True)
class NICase:
    case_id: str
    year: int
    kind: str  # "class_1" | "class_4" | "isolation" | "dual"
    amount: float  # employment income (class_1) or profits (all others)
    scenario: str
    lower_limit: float | None = None  # isolation only
    upper_limit: float | None = None  # isolation only
    employment: float | None = None  # dual only

    @property
    def period(self) -> str:
        return f"{self.year}-04-06"

    @property
    def tax_year(self) -> str:
        return f"{self.year}-{(self.year + 1) % 100:02d}"


def _slug(amount: float) -> str:
    text = f"{amount:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def _scenario(amount: float, lower: float, upper: float) -> str:
    if amount < lower:
        return "below-lower-limit"
    if amount == lower:
        return "at-lower-limit"
    if amount < upper:
        return "between-limits"
    if amount == upper:
        return "at-upper-limit"
    return "above-upper-limit"


def _grid() -> list[NICase]:
    cases: list[NICase] = []
    for year in VALIDATION_YEARS:
        for earnings in EMPLOYEE_EARNINGS:
            cases.append(
                NICase(
                    f"nic-{year}-class1-{_slug(earnings)}",
                    year,
                    "class_1",
                    earnings,
                    f"class-1-{_scenario(earnings, 12570, 50270)}",
                )
            )
        for profits in SELF_EMPLOYED_PROFITS:
            cases.append(
                NICase(
                    f"nic-{year}-class4-{_slug(profits)}",
                    year,
                    "class_4",
                    profits,
                    f"class-4-{_scenario(profits, 12570, 50270)}",
                )
            )
    for earnings, profits in DUAL_EARNER_CASES:
        cases.append(
            NICase(
                f"nic-{DUAL_EARNER_YEAR}-dual-{_slug(earnings)}-{_slug(profits)}",
                DUAL_EARNER_YEAR,
                "dual",
                profits,
                "class-4-dual-earner",
                employment=earnings,
            )
        )
    for year, lower, upper, profits in ISOLATION_CASES:
        cases.append(
            NICase(
                f"nic-{year}-float32-isolation-{_slug(profits)}",
                year,
                "isolation",
                profits,
                "class-4-float32-isolation",
                lower_limit=lower,
                upper_limit=upper,
            )
        )
    return cases


def _concepts_for(case: NICase) -> tuple[str, ...]:
    if case.kind == "class_1":
        return CLASS_1_CONCEPTS
    if case.kind == "class_4":
        return CLASS_4_CONCEPTS
    if case.kind == "dual":
        return DUAL_CONCEPTS
    return ISOLATION_CONCEPTS


# --------------------------------------------------------------------------
# PolicyEngine-UK
# --------------------------------------------------------------------------


def _pe_situation(year: int, cases: list[NICase]) -> dict:
    people = {}
    for case in cases:
        if case.kind == "class_1":
            income = {"employment_income": {year: case.amount}}
        elif case.kind == "dual":
            income = {
                "employment_income": {year: case.employment},
                "self_employment_income": {year: case.amount},
            }
        else:
            income = {"self_employment_income": {year: case.amount}}
        people[case.case_id] = {"age": {year: 40}, **income}
    return {
        "people": people,
        "benunits": {f"bu-{c.case_id}": {"members": [c.case_id]} for c in cases},
        "households": {f"hh-{c.case_id}": {"members": [c.case_id]} for c in cases},
    }


def _check_policyengine_version() -> None:
    from importlib.metadata import version

    installed = version("policyengine-uk")
    if installed != POLICYENGINE_UK_VERSION:
        raise SystemExit(
            f"policyengine-uk {installed} is installed but the suite pins "
            f"{POLICYENGINE_UK_VERSION}; run under the pinned version"
        )


def _pe_parameters(sim, year: int) -> dict[str, float]:
    """PolicyEngine's NICs parameters as its year-``year`` simulation reads them.

    PolicyEngine evaluates a year's parameters at the period start (1 January);
    the mechanism reconciliation below fails loudly (``unreconciled``) if that
    ever stops being the instant its formulas use.
    """
    ni = sim.tax_benefit_system.parameters(f"{year}-01-01").gov.hmrc.national_insurance
    return {
        "primary_threshold_weekly": float(ni.class_1.thresholds.primary_threshold),
        "upper_earnings_limit_weekly": float(ni.class_1.thresholds.upper_earnings_limit),
        "lower_profits_limit": float(ni.class_4.thresholds.lower_profits_limit),
        "upper_profits_limit": float(ni.class_4.thresholds.upper_profits_limit),
        "main_class_4_percentage": float(ni.class_4.rates.main),
        "additional_class_4_percentage": float(ni.class_4.rates.additional),
    }


def _isolation_reform(year: int, lower: float, upper: float) -> dict:
    window = f"{year}-01-01.{year}-12-31"
    base = "gov.hmrc.national_insurance.class_4.thresholds"
    return {
        f"{base}.lower_profits_limit": {window: lower},
        f"{base}.upper_profits_limit": {window: upper},
    }


def _pe_values(sim, case_ids: list[str], year: int, concepts: tuple[str, ...]) -> dict:
    out: dict[str, dict[str, float]] = {cid: {} for cid in case_ids}
    for key in concepts:
        variable = CONCEPTS[key][1]
        if key.startswith("c1-"):
            values = sim.calculate_add(variable, year)
        else:
            values = sim.calculate(variable, year)
        for cid, value in zip(case_ids, values):
            out[cid][key] = float(value)
    return out


def _policyengine_rows(cases: list[NICase]) -> tuple[dict, dict]:
    from policyengine_uk import Simulation

    rows: dict[str, dict[str, float]] = {}
    parameters: dict[str, dict[str, float]] = {}
    for year in VALIDATION_YEARS:
        year_cases = [c for c in cases if c.year == year and c.kind != "isolation"]
        sim = Simulation(situation=_pe_situation(year, year_cases))
        people = [c.case_id for c in year_cases]
        c1 = [c.case_id for c in year_cases if c.kind == "class_1"]
        c4 = [c.case_id for c in year_cases if c.kind == "class_4"]
        dual = [c.case_id for c in year_cases if c.kind == "dual"]
        values = _pe_values(sim, people, year, CLASS_1_CONCEPTS + CLASS_4_CONCEPTS)
        earnings = sim.calculate_add("ni_class_1_income", year)
        earnings_by_id = dict(zip(people, (float(v) for v in earnings)))
        class_1_total = sim.calculate_add("ni_class_1_employee", year)
        class_1_total_by_id = dict(zip(people, (float(v) for v in class_1_total)))
        for cid in c1:
            rows[cid] = {k: values[cid][k] for k in CLASS_1_CONCEPTS}
            rows[cid]["_earnings"] = earnings_by_id[cid]
        for cid in c4:
            rows[cid] = {k: values[cid][k] for k in CLASS_4_CONCEPTS}
        for cid in dual:
            rows[cid] = {k: values[cid][k] for k in DUAL_CONCEPTS}
            rows[cid]["_earnings"] = earnings_by_id[cid]
            rows[cid]["_pe_class_1_primary"] = values[cid]["c1-main"]
            rows[cid]["_pe_class_1_total"] = class_1_total_by_id[cid]
        parameters[str(year)] = _pe_parameters(sim, year)
    for case in cases:
        if case.kind != "isolation":
            continue
        reform = _isolation_reform(case.year, case.lower_limit, case.upper_limit)
        sim = Simulation(situation=_pe_situation(case.year, [case]), reform=reform)
        rows[case.case_id] = _pe_values(sim, [case.case_id], case.year, ISOLATION_CONCEPTS)[
            case.case_id
        ]
        parameters[case.case_id] = _pe_parameters(sim, case.year)
    return rows, parameters


# --------------------------------------------------------------------------
# Axiom
# --------------------------------------------------------------------------


def _runner(program: str):
    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner

    return AxiomRulesRunner(
        program_path=RULESPEC_UK / program,
        binary_path=os.environ.get("AXIOM_RULES_ENGINE_BINARY"),
        default_entity="Person",
        default_entity_id="person",
        rulespec_repo_roots=(RULESPEC_UK,),
        mode="explain",
    )


def _run(program: str, requests: list[tuple[NICase, dict]], outputs: list[str]) -> dict:
    sys.path.insert(0, str(REPO_ROOT))
    from axiom_oracles.core.case import Case

    axiom_cases = [
        Case(
            case_id=case.case_id,
            period=case.period,
            metadata={
                "axiom_entity": "Person",
                "axiom_entity_id": "person",
                "axiom_inputs": inputs,
            },
            outputs=tuple(outputs),
        )
        for case, inputs in requests
    ]
    results = _runner(program).run_cases(axiom_cases, outputs)
    values: dict[str, dict[str, float]] = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id} "
                f"({program}): {result.errors}"
            )
        values[str(result.household_id)] = {
            name: float(result.values[name]) for name in outputs
        }
    return values


def _module_parameters(program: str, period_start: str) -> dict[str, float]:
    """The literal parameter values an Axiom module has in force at ``period_start``.

    The rules engine answers derived outputs only, so the s.15 limits and
    percentages that regulation 100 takes as inputs are read from the s.15
    module's own parameter versions (the latest ``effective_from`` on or before
    the period start, as the engine selects them). Only numeric-literal
    formulas are accepted.
    """
    import yaml

    doc = yaml.safe_load((RULESPEC_UK / program).read_text())
    values: dict[str, float] = {}
    for rule in doc.get("rules") or []:
        if rule.get("kind") != "parameter":
            continue
        # Inclusive [effective_from, effective_to] interval, as the engine
        # selects versions; a parameter with no version in force is an error,
        # never a silent fallback to an expired one.
        versions = [
            v
            for v in rule.get("versions") or []
            if str(v["effective_from"]) <= period_start
            and (v.get("effective_to") is None or period_start <= str(v["effective_to"]))
        ]
        if not versions:
            raise SystemExit(
                f"{program}#{rule['name']}: no parameter version in force on {period_start}"
            )
        formula = str(max(versions, key=lambda v: str(v["effective_from"]))["formula"])
        values[rule["name"]] = float(formula.strip())
    return values


def _axiom_rows(cases: list[NICase], pe_rows: dict) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {c.case_id: {} for c in cases}

    class_1 = [c for c in cases if c.kind in ("class_1", "dual")]
    c1_outputs = [CONCEPTS[k][0] for k in CLASS_1_CONCEPTS]
    c1 = _run(
        C1_PROGRAM,
        [
            (
                c,
                {
                    f"{C1_BASE}#input.uk_nic_pilot_annual_employment_income": pe_rows[
                        c.case_id
                    ]["_earnings"]
                },
            )
            for c in class_1
        ],
        c1_outputs,
    )
    for case in class_1:
        if case.kind == "class_1":
            for key in CLASS_1_CONCEPTS:
                rows[case.case_id][key] = c1[case.case_id][CONCEPTS[key][0]]
    class_1_main = {
        c.case_id: c1[c.case_id][CONCEPTS["c1-main"][0]] for c in class_1 if c.kind == "dual"
    }

    class_4 = [c for c in cases if c.kind in ("class_4", "dual")]
    s15_outputs = [
        f"{S15_BASE}#main_class_4_contribution",
        f"{S15_BASE}#class_4_contribution_before_annual_maximum",
    ]
    s15 = _run(
        S15_PROGRAM,
        [
            (
                c,
                {
                    f"{S15_BASE}#input.class_4_contributions_payable_under_section_15": True,
                    f"{S15_BASE}#input.profits_chargeable_to_class_4_contributions": c.amount,
                },
            )
            for c in class_4
        ],
        s15_outputs,
    )

    def r100_inputs(profits: float, s15_row: dict[str, float], class_1: float = 0) -> dict:
        # Primary Class 1 at the main primary percentage: the Axiom Class 1
        # pipeline's main amount for dual earners, nil for sole traders.
        return {
            f"{R100_BASE}#input.primary_class_1_contributions_paid_at_main_primary_percentage": class_1,
            f"{R100_BASE}#input.primary_class_1_contributions_payable_at_main_primary_percentage": class_1,
            f"{R100_BASE}#input.class_4_contributions_payable_at_main_class_4_percentage": s15_row[
                "main"
            ],
            f"{R100_BASE}#input.class_4_contribution_before_annual_maximum": s15_row[
                "before_maximum"
            ],
            f"{R100_BASE}#input.class_4_contributions_payable_under_section_15_for_year": True,
            f"{R100_BASE}#input.profits_and_gains_for_year": profits,
            f"{R100_BASE}#input.lower_profits_limit": s15_row["lower"],
            f"{R100_BASE}#input.upper_profits_limit": s15_row["upper"],
            f"{R100_BASE}#input.main_class_4_percentage": s15_row["main_rate"],
            f"{R100_BASE}#input.additional_class_4_percentage": s15_row["additional_rate"],
        }

    s15_rows = {}
    for c in class_4:
        parameters = _module_parameters(S15_PROGRAM, c.period)
        s15_rows[c.case_id] = {
            "lower": parameters["lower_profits_limit"],
            "upper": parameters["upper_profits_limit"],
            "main_rate": parameters["main_class_4_percentage"],
            "additional_rate": parameters["additional_class_4_percentage"],
            "main": s15[c.case_id][f"{S15_BASE}#main_class_4_contribution"],
            "before_maximum": s15[c.case_id][
                f"{S15_BASE}#class_4_contribution_before_annual_maximum"
            ],
        }

    # Isolation: the non-round limits are supplied; the s.15 amounts at those
    # limits are the s.15(3) arithmetic with the s.15(3ZA) percentages, in exact
    # decimal. Regulation 100 case 1 turns on an equality (step four against the
    # main-rate Class 4), so a binary-float main amount would flip the case in
    # Axiom exactly as float32 does in PolicyEngine; penny limits keep every
    # amount an exact decimal that survives the runner's str() conversion.
    isolation = [c for c in cases if c.kind == "isolation"]
    for case in isolation:
        amount = Decimal(str(case.amount))
        lower = Decimal(str(case.lower_limit))
        upper = Decimal(str(case.upper_limit))
        main = Decimal("0.06") * max(Decimal(0), min(amount, upper) - lower)
        additional = Decimal("0.02") * max(Decimal(0), amount - upper)
        for value in (main, main + additional):
            if Decimal(str(float(value))) != value:
                raise SystemExit(f"{case.case_id}: {value} is not float-exact")
        s15_rows[case.case_id] = {
            "lower": case.lower_limit,
            "upper": case.upper_limit,
            "main_rate": 0.06,
            "additional_rate": 0.02,
            "main": float(main),
            "before_maximum": float(main + additional),
        }

    r100_outputs = [CONCEPTS["c4-maximum"][0], CONCEPTS["c4-total"][0]]
    r100 = _run(
        R100_PROGRAM,
        [
            (c, r100_inputs(c.amount, s15_rows[c.case_id], class_1_main.get(c.case_id, 0)))
            for c in class_4 + isolation
        ],
        r100_outputs,
    )
    se = _run(
        SE_PROGRAM,
        [
            (c, {f"{SE_BASE}#input.uk_nic_pilot_se_annual_profits": c.amount})
            for c in class_4
            if c.kind == "class_4"
        ],
        [CONCEPTS["c2"][0]],
    )
    for case in class_4:
        rows[case.case_id]["c4-main"] = s15_rows[case.case_id]["main"]
        rows[case.case_id]["c4-maximum"] = r100[case.case_id][CONCEPTS["c4-maximum"][0]]
        rows[case.case_id]["c4-total"] = r100[case.case_id][CONCEPTS["c4-total"][0]]
        if case.kind == "class_4":
            rows[case.case_id]["c2"] = se[case.case_id][CONCEPTS["c2"][0]]
        else:
            rows[case.case_id]["_class_1_main"] = class_1_main[case.case_id]
        rows[case.case_id]["_s15"] = s15_rows[case.case_id]
    for case in isolation:
        rows[case.case_id]["c4-maximum"] = r100[case.case_id][CONCEPTS["c4-maximum"][0]]
        rows[case.case_id]["c4-total"] = r100[case.case_id][CONCEPTS["c4-total"][0]]
        rows[case.case_id]["_s15"] = s15_rows[case.case_id]
    return rows


# --------------------------------------------------------------------------
# Mechanism reconciliation
# --------------------------------------------------------------------------


def _pe_expected(
    case: NICase, key: str, p: dict[str, float], income: float
) -> dict[str, float]:
    """What PolicyEngine should return under its own parameters.

    ``correct`` applies the statutory formula to PolicyEngine's parameters (so a
    difference from Axiom is purely the parameters: PolicyEngine-UK#1879).
    ``main_only`` is regulation 100 case 1 (the main-band amount alone), which
    PolicyEngine-UK#1878's float32 comparison selects for profits above the
    upper limit.
    """

    if key.startswith("c1-"):
        pt = p["primary_threshold_weekly"] * WEEKS_IN_YEAR
        uel = p["upper_earnings_limit_weekly"] * WEEKS_IN_YEAR
        if key == "c1-main":
            return {
                "correct": MAIN_PRIMARY_PERCENTAGE * max(0.0, min(income, uel) - pt)
            }
        return {"correct": ADDITIONAL_PRIMARY_PERCENTAGE * max(0.0, income - uel)}
    if key == "c2":
        return {"correct": 0.0}
    lpl = p["lower_profits_limit"]
    upl = p["upper_profits_limit"]
    main_rate = p["main_class_4_percentage"]
    additional_rate = p["additional_class_4_percentage"]
    main = main_rate * max(0.0, min(income, upl) - lpl)
    before_maximum = main + additional_rate * max(0.0, income - upl)
    step_four = main_rate * (upl - lpl)
    if key == "c4-main":
        return {"correct": main}
    # Regulation 100 with no Class 1 or Class 2: case 1 (step four above the
    # main-rate Class 4) below the upper limit, case 2 (the full amount) at or
    # above it.
    correct_maximum = step_four if step_four > main else before_maximum
    if key == "c4-maximum":
        return {"correct": correct_maximum, "main_only": step_four}
    return {
        "correct": min(before_maximum, correct_maximum),
        "main_only": min(before_maximum, step_four),
    }


def _pe_dual_model(
    profits: float, class_1_primary: float, class_1_total: float, p: dict[str, float]
) -> dict[str, float]:
    """PolicyEngine-UK's ni_class_4_main / ni_class_4_maximum / ni_class_4 formulas.

    Transcribed from PolicyEngine-UK 2.102.0 (no Class 2 payable): the Class 4
    profits are ``self_employment_income - ni_class_1_employee``
    (PolicyEngine-UK#1885), while regulation 100's step six uses the undeducted
    profits and step four subtracts the primary Class 1 at the main percentage.
    """

    lpl, upl = p["lower_profits_limit"], p["upper_profits_limit"]
    main_rate = p["main_class_4_percentage"]
    additional_rate = p["additional_class_4_percentage"]
    deducted = profits - class_1_total
    additional_income = max(deducted - upl, 0.0)
    main = (max(deducted - lpl, 0.0) - additional_income) * main_rate
    before_maximum = main + additional_income * additional_rate
    step_four_raw = (upl - lpl) * main_rate - class_1_primary
    step_four = max(step_four_raw, 0.0)
    case_1 = step_four_raw >= 0 and step_four_raw > class_1_primary + main
    step_seven = max(0.0, (min(upl, profits) - lpl) - step_four / main_rate)
    maximum = (
        step_four
        if case_1
        else step_four + step_seven * additional_rate + max(0.0, profits - upl) * additional_rate
    )
    return {
        "c4-main": main,
        "c4-maximum": maximum,
        "c4-total": max(min(before_maximum, maximum), 0.0),
    }


# The statute's figures, independent of any module: SSCBA 1992 s.15(3) for
# Class 4; for Class 1, the PA and BRL that FA 2021 s.5 (as amended by FA 2026
# s.10) fixes, from which the Axiom pipeline derives PT = 12,570 and UEL =
# 12,570 + 37,700.
STATUTORY_CLASS_4_LIMITS = (12570.0, 50270.0)
STATUTORY_CLASS_1_THRESHOLDS = (12570.0, 50270.0)


def statutory_value(
    case: NICase, key: str, income: float, class_1_main: float = 0.0
) -> float:
    """The statutory amount, computed from the statute's figures by plain arithmetic.

    A mismatch is only ever attributed to PolicyEngine when the Axiom value
    equals this: an Axiom error is never explained away as a PolicyEngine one.
    """

    if key.startswith("c1-"):
        pt, uel = STATUTORY_CLASS_1_THRESHOLDS
        if key == "c1-main":
            return MAIN_PRIMARY_PERCENTAGE * max(0.0, min(income, uel) - pt)
        return ADDITIONAL_PRIMARY_PERCENTAGE * max(0.0, income - uel)
    if key == "c2":
        # s.11(5B): at or above the small profits threshold (6,845; every grid
        # profit exceeds it) Class 2 is treated as paid with nothing payable.
        return 0.0
    lower, upper = (
        (case.lower_limit, case.upper_limit)
        if case.kind == "isolation"
        else STATUTORY_CLASS_4_LIMITS
    )
    main = 0.06 * max(0.0, min(income, upper) - lower)
    before_maximum = main + 0.02 * max(0.0, income - upper)
    if key == "c4-main":
        return main
    # Regulation 100 (no Class 2): step four is the main-band amount at the
    # limits less primary Class 1 at the main percentage; case 1 when it
    # exceeds that Class 1 plus the main-rate Class 4, else steps 4 + 8 + 9.
    step_four_value = 0.06 * (upper - lower) - class_1_main
    step_four = max(0.0, step_four_value)
    if step_four_value > 0 and step_four_value > class_1_main + main:
        maximum = step_four
    else:
        step_seven = max(0.0, (min(upper, income) - lower) - step_four / 0.06)
        maximum = step_four + 0.02 * step_seven + 0.02 * max(0.0, income - upper)
    if key == "c4-maximum":
        return maximum
    return min(before_maximum, maximum)


def _parameters_differ_from_statute(case: NICase, key: str, p: dict[str, float]) -> bool:
    if key.startswith("c1-"):
        pt, uel = STATUTORY_CLASS_1_THRESHOLDS
        # PolicyEngine stores weekly figures; 241.73 x 52 = 12,569.96 is the
        # statutory annual figure to within its own weekly rounding.
        return (
            abs(p["primary_threshold_weekly"] * WEEKS_IN_YEAR - pt) > 1.0
            or abs(p["upper_earnings_limit_weekly"] * WEEKS_IN_YEAR - uel) > 1.0
        )
    if key == "c2":
        return False
    lower, upper = (
        (case.lower_limit, case.upper_limit)
        if case.kind == "isolation"
        else STATUTORY_CLASS_4_LIMITS
    )
    return (
        abs(p["lower_profits_limit"] - lower) > _TOLERANCE
        or abs(p["upper_profits_limit"] - upper) > _TOLERANCE
    )


def classify_mechanism(
    case: NICase, key: str, axiom: float, pe: float, p: dict[str, float], income: float
) -> str:
    """Name the PolicyEngine mechanism a mismatch reconciles to, or ``unreconciled``.

    Attribution needs all of: the Axiom value equals the statutory computation;
    the PolicyEngine value equals the named mechanism under PolicyEngine's own
    parameters; and that mechanism actually departs from the statute (for the
    threshold mechanism, PolicyEngine's parameters themselves differ).
    """

    if abs(axiom - statutory_value(case, key, income)) > _TOLERANCE:
        return "unreconciled"
    expected = _pe_expected(case, key, p, income)
    correct = expected["correct"]
    main_only = expected.get("main_only")
    if (
        main_only is not None
        and abs(correct - main_only) > _RECONCILE_TOLERANCE
        and abs(pe - main_only) <= _RECONCILE_TOLERANCE
    ):
        return "float32_drops_additional_band"
    if (
        abs(pe - correct) <= _RECONCILE_TOLERANCE
        and abs(correct - axiom) > _TOLERANCE
        and _parameters_differ_from_statute(case, key, p)
    ):
        return "cpi_uprated_thresholds"
    return "unreconciled"


def classify_dual_mechanism(
    case: NICase,
    key: str,
    axiom: float,
    pe: float,
    p: dict[str, float],
    axiom_class_1_main: float,
    pe_class_1_primary: float,
    pe_class_1_total: float,
) -> str:
    """Attribute a dual-earner mismatch to PolicyEngine-UK#1885 only when it reconciles.

    The Axiom value must equal the statute (s.15 on the full profits, regulation
    100 with the Axiom Class 1 main amount) and the PolicyEngine value its own
    formula with the Class 4 profits reduced by its Class 1.
    """

    statute = statutory_value(case, key, case.amount, axiom_class_1_main)
    if abs(axiom - statute) > _TOLERANCE:
        return "unreconciled"
    modelled = _pe_dual_model(case.amount, pe_class_1_primary, pe_class_1_total, p)[key]
    if abs(pe - modelled) <= _RECONCILE_TOLERANCE and abs(modelled - statute) > _TOLERANCE:
        return "class_1_deducted_from_class_4_profits"
    return "unreconciled"


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _match(left: float, right: float) -> bool:
    diff = abs(left - right)
    if diff <= _TOLERANCE:
        return True
    base = max(abs(left), abs(right))
    return base > 0 and diff / base <= _RELATIVE_TOLERANCE


def _counts(values: list[str]) -> list[dict]:
    tally: dict[str, int] = {}
    for value in values:
        tally[value] = tally.get(value, 0) + 1
    return [{"count": n, "value": v} for v, n in sorted(tally.items())]


def build_report(
    cases: list[NICase],
    pe_rows: dict,
    pe_parameters: dict,
    axiom_rows: dict,
) -> dict:
    report_cases: list[dict] = []
    mismatches: list[dict] = []
    mismatch_scenarios: list[str] = []
    for case in cases:
        params = pe_parameters[case.case_id if case.kind == "isolation" else str(case.year)]
        s15 = axiom_rows[case.case_id].get("_s15")
        # The income each measure is charged on: PolicyEngine's Class 1 earnings
        # base for Class 1, the profits for Class 4 (dual earners included).
        income = (
            pe_rows[case.case_id]["_earnings"] if case.kind == "class_1" else case.amount
        )
        dual = {}
        if case.kind == "dual":
            dual = {
                "employment_income": case.employment,
                "compared_employment_income": pe_rows[case.case_id]["_earnings"],
                "axiom_class_1_main": axiom_rows[case.case_id]["_class_1_main"],
                "policyengine_class_1_primary": pe_rows[case.case_id]["_pe_class_1_primary"],
                "policyengine_class_1_total": pe_rows[case.case_id]["_pe_class_1_total"],
            }
        for key in _concepts_for(case):
            concept, pe_variable = CONCEPTS[key]
            ax_val = axiom_rows[case.case_id][key]
            pe_val = pe_rows[case.case_id][key]
            ok = _match(ax_val, pe_val)
            row = {
                "case_id": f"{case.case_id}-{key}",
                "concept": concept,
                "scenario": case.scenario,
                "tax_year": case.tax_year,
                "validation_year": case.year,
                "measure": key,
                "income_kind": (
                    "employment_income" if case.kind == "class_1" else "self_employment_income"
                ),
                "income": case.amount,
                "compared_income": income,
                "policyengine_variable": pe_variable,
                "axiom": ax_val,
                "policyengine": pe_val,
                "axiom_vs_policyengine": {"difference": ax_val - pe_val, "match": ok},
            }
            if s15 is not None:
                row["axiom_profits_limits"] = [s15["lower"], s15["upper"]]
            if case.kind == "isolation":
                row["supplied_profits_limits"] = [case.lower_limit, case.upper_limit]
            row.update(dual)
            report_cases.append(row)
            if ok:
                continue
            if case.kind == "dual":
                mechanism = classify_dual_mechanism(
                    case,
                    key,
                    ax_val,
                    pe_val,
                    params,
                    dual["axiom_class_1_main"],
                    dual["policyengine_class_1_primary"],
                    dual["policyengine_class_1_total"],
                )
            else:
                mechanism = classify_mechanism(case, key, ax_val, pe_val, params, income)
            row["pe_mechanism"] = mechanism
            mismatch_scenarios.append(case.scenario)
            mismatches.append(
                {
                    "case_id": row["case_id"],
                    "concept": concept,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": ax_val,
                    "right": pe_val,
                    "difference": ax_val - pe_val,
                    "validation_year": case.year,
                    "measure": key,
                    "income": case.amount,
                    "compared_income": income,
                    "pe_mechanism": mechanism,
                    "policyengine_parameters": params,
                    **(
                        {"supplied_profits_limits": [case.lower_limit, case.upper_limit]}
                        if case.kind == "isolation"
                        else {}
                    ),
                    **dual,
                }
            )
    n = len(report_cases)
    mismatch_count = len(mismatches)
    match_count = n - mismatch_count
    match_rate = round(100.0 * match_count / n, 6) if n else 100.0
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITE,
        "concept": SUITE,
        "population": "case-grid",
        "validation_year": VALIDATION_YEARS[0],
        "validation_years": list(VALIDATION_YEARS),
        "locales": ["UK"],
        "scope": UK_SCOPE,
        "engines": {
            "axiom": (
                "uk:statutes/social_security/workers/pilot_worker_class_1_nic_pipeline, "
                "uk:statutes/ukpga/1992/4/15, uk:regulations/uksi/2001/1004/100, "
                "uk:statutes/social_security/workers/pilot_worker_self_employed_nic_pipeline"
            ),
            "policyengine": ", ".join(dict.fromkeys(v for _, v in CONCEPTS.values())),
        },
        "tolerance": {"absolute": _TOLERANCE, "relative": _RELATIVE_TOLERANCE},
        "case_count": n,
        "summary": {
            "comparison_count": n,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "axiom_vs_policyengine_match_rate": match_rate,
            "policyengine_matches": match_count,
            "weighted": {
                "comparison_weight": n,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
                "match_rate": match_rate,
            },
            "mismatches_by_concept": _counts([m["concept"] for m in mismatches]),
            "mismatches_by_kind": _counts([m["kind"] for m in mismatches]),
            "mismatches_by_scenario": _counts(mismatch_scenarios),
            "mismatches_by_mechanism": _counts([m["pe_mechanism"] for m in mismatches]),
            "error_count": 0,
            "errors_by_engine": [],
        },
        "mismatches": mismatches,
        "errors": [],
        "cases": report_cases,
        "provenance": {
            "generated": datetime.now(timezone.utc).date().isoformat(),
            "generator": "scripts/generate_uk_national_insurance_pe.py",
            "axiom_engine": "axiom rules engine over rulespec-uk "
            + ", ".join((C1_PROGRAM, S15_PROGRAM, R100_PROGRAM, SE_PROGRAM)),
            "policyengine_uk": POLICYENGINE_UK_VERSION,
            "policyengine_parameters_by_year": {
                year: pe_parameters[str(year)] for year in map(str, VALIDATION_YEARS)
            },
            "commensurability": (
                "One person per household with only employment income (Class 1) or "
                "only self-employment profits (Class 4 and 2), so no Class 1/Class 4 "
                "interaction arises. The Class 1 earnings compared are PolicyEngine's own "
                "ni_class_1_income (from 2029 PolicyEngine scales employment income by "
                "a modelled incidence adjustment, e.g. 30,000 -> 29,952), fed to the Axiom "
                "pipeline so both engines charge the same earnings. PolicyEngine's monthly "
                "Class 1 amounts are summed "
                "over the year; its weekly thresholds annualise as weekly x 52 "
                "(241.73 x 52 = 12,569.96 against Axiom's annual 12,570, a 0.0032 "
                "contribution difference inside tolerance). Axiom thresholds come "
                "from Axiom modules only; no PolicyEngine value is an Axiom input "
                "except the float32-isolation limits, which both engines receive."
            ),
        },
    }


def main() -> int:
    _check_policyengine_version()
    cases = _grid()
    pe_rows, pe_parameters = _policyengine_rows(cases)
    axiom_rows = _axiom_rows(cases, pe_rows)
    report = build_report(cases, pe_rows, pe_parameters, axiom_rows)

    REPORTS.mkdir(exist_ok=True)
    DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    text = json.dumps(report, indent=2) + "\n"
    (REPORTS / f"{REPORT_BASENAME}-{stamp}.json").write_text(text)
    (DASH_PUBLIC / f"{REPORT_BASENAME}.json").write_text(text)

    summary = report["summary"]
    print(
        f"{SUITE}: PE match {summary['axiom_vs_policyengine_match_rate']}% "
        f"({summary['match_count']}/{report['case_count']} comparisons); "
        f"mismatches by mechanism: {summary['mismatches_by_mechanism']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
