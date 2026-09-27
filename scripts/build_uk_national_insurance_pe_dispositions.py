#!/usr/bin/env python3
"""Build dispositions/uk-national-insurance-pe.yaml from the committed NICs grid report.

Every mismatch row in the report carries ``pe_mechanism``, the PolicyEngine
behaviour its value reconciles to under PolicyEngine's own parameters
(scripts/generate_uk_national_insurance_pe.py). This script groups the reconciled
rows by (tax year, measure, mechanism) and writes one selector-bound
``upstream_engine_gap`` entry per group:

* ``case_selector.case_ids`` names the exact rows, and ``selector_binding`` pins
  a digest of their left/right/difference values, so any movement (a new
  PolicyEngine release, an Axiom change) expires the entry instead of letting it
  explain a different residual.
* ``arithmetic`` reproduces a representative row both ways: the Axiom value
  from the statutory limits and the PolicyEngine value from PolicyEngine's
  parameters (or its regulation 100 case 1 amount for the float32 defect).
* ``linked_issue`` is the PolicyEngine-UK issue; ``sources`` carry the Axiom
  legal ids and the companion tests that exercise them.

Rows whose mechanism is ``unreconciled`` are never dispositioned. They stay
unexplained until someone reads them.

When a fixed PolicyEngine-UK release is pinned in comparisons/uk-national-insurance-pe.yaml
and the report regenerated, the fixed rows stop mismatching. Their entries then
report as expired (``scripts/apply_dispositions.py`` notes them); rerun this
script to drop them.

    uv run python scripts/build_uk_national_insurance_pe_dispositions.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import json

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    evaluate_arithmetic,
    selected_rows_sha256,
)

SUITE = "uk-national-insurance-pe"
REPORT = REPO_ROOT / "dashboard" / "public" / "data" / "axiom-policyengine-uk-national-insurance.json"
OUTPUT = REPO_ROOT / "dispositions" / f"{SUITE}.yaml"

FREEZE_ISSUE = "https://github.com/PolicyEngine/policyengine-uk/issues/1879"
FLOAT32_ISSUE = "https://github.com/PolicyEngine/policyengine-uk/issues/1878"
DUAL_EARNER_ISSUE = "https://github.com/PolicyEngine/policyengine-uk/issues/1885"
ISSUES = {
    "cpi_uprated_thresholds": FREEZE_ISSUE,
    "float32_drops_additional_band": FLOAT32_ISSUE,
    "class_1_deducted_from_class_4_profits": DUAL_EARNER_ISSUE,
}
RULESPEC_BLOB = "https://github.com/TheAxiomFoundation/rulespec-uk/blob/main/uk"
RULESPEC_FREEZE_TESTS_PR = "https://github.com/TheAxiomFoundation/rulespec-uk/pull/350"

AXIOM_SOURCES = {
    "c1": [
        f"{RULESPEC_BLOB}/statutes/social_security/workers/pilot_worker_class_1_nic_pipeline.yaml",
        f"{RULESPEC_BLOB}/statutes/social_security/workers/pilot_worker_class_1_nic_pipeline.test.yaml",
        f"{RULESPEC_BLOB}/statutes/ukpga/2021/26/5.yaml",
        f"{RULESPEC_BLOB}/statutes/ukpga/2026/11/10.yaml",
    ],
    "c4": [
        f"{RULESPEC_BLOB}/statutes/ukpga/1992/4/15.yaml",
        f"{RULESPEC_BLOB}/statutes/ukpga/1992/4/15.test.yaml",
        f"{RULESPEC_BLOB}/regulations/uksi/2001/1004/100.yaml",
        f"{RULESPEC_BLOB}/regulations/uksi/2001/1004/100.test.yaml",
    ],
}

STATUTORY = {
    "pt": 12570,
    "uel": 50270,
    "lpl": 12570,
    "upl": 50270,
}


def _num(value: float) -> str:
    return repr(float(value))


def _class_4_parts(income: float, lower: float, upper: float) -> dict[str, str]:
    """Literal expressions for the s.15(3) / regulation 100 amounts at given limits."""

    band = f"({_num(min(income, upper))} - {_num(lower)})" if income > lower else "0"
    main = f"0.06 * {band}" if income > lower else "0"
    additional = f"0.02 * ({_num(income)} - {_num(upper)})" if income > upper else "0"
    step_four = f"0.06 * ({_num(upper)} - {_num(lower)})"
    return {"main": main, "additional": additional, "step_four": step_four}


def _expressions(row: dict) -> tuple[str, str]:
    """(Axiom expression, PolicyEngine expression) for one mismatch row."""

    measure = row["measure"]
    income = float(row["compared_income"])
    params = row["policyengine_parameters"]
    mechanism = row["pe_mechanism"]
    isolation = "float32-isolation" in row["case_id"]

    if measure.startswith("c1-"):
        pe_pt = f"{_num(params['primary_threshold_weekly'])} * 52"
        pe_uel = f"{_num(params['upper_earnings_limit_weekly'])} * 52"
        pe_uel_value = params["upper_earnings_limit_weekly"] * 52
        if measure == "c1-main":
            ax_top = min(income, STATUTORY["uel"])
            axiom = (
                f"0.08 * ({_num(ax_top)} - {STATUTORY['pt']})"
                if income > STATUTORY["pt"]
                else "0"
            )
            pe_top = _num(income) if income < pe_uel_value else pe_uel
            pe = f"0.08 * ({pe_top} - {pe_pt})"
        else:
            axiom = (
                f"0.02 * ({_num(income)} - {STATUTORY['uel']})"
                if income > STATUTORY["uel"]
                else "0"
            )
            pe = f"0.02 * ({_num(income)} - {pe_uel})" if income > pe_uel_value else "0"
        return axiom, pe

    if isolation:
        lower, upper = row["supplied_profits_limits"]
        ax_lower, ax_upper = lower, upper
    else:
        ax_lower, ax_upper = STATUTORY["lpl"], STATUTORY["upl"]
    pe_lower = params["lower_profits_limit"]
    pe_upper = params["upper_profits_limit"]
    ax = _class_4_parts(income, ax_lower, ax_upper)
    pe = _class_4_parts(income, pe_lower, pe_upper)
    if mechanism == "class_1_deducted_from_class_4_profits":
        # PolicyEngine charges Class 4 on profits less its total Class 1; the
        # regulation 100 maximum binds in neither engine on these rows (the
        # arithmetic check below fails loudly if it ever does).
        deducted = income - float(row["policyengine_class_1_total"])
        pe = _class_4_parts(deducted, pe_lower, pe_upper)
        if measure == "c4-main":
            return ax["main"], pe["main"]
        return f"{ax['main']} + {ax['additional']}", f"{pe['main']} + {pe['additional']}"

    def before_maximum(parts: dict[str, str]) -> str:
        return f"{parts['main']} + {parts['additional']}"

    if measure == "c4-main":
        return ax["main"], pe["main"]
    # Regulation 100 with no Class 1 or Class 2: case 1 (step four) below the
    # upper limit, case 2 (the full amount) at or above it.
    ax_max = ax["step_four"] if income < ax_upper else before_maximum(ax)
    if mechanism == "float32_drops_additional_band":
        pe_expr = pe["step_four"]
    else:
        pe_expr = pe["step_four"] if income < pe_upper else before_maximum(pe)
    if measure == "c4-maximum":
        return ax_max, pe_expr
    # c4-total = min(before maximum, maximum); below the upper limit that is the
    # main amount, at or above it the case-2 amount (or the float32 case 1).
    ax_total = ax["main"] if income < ax_upper else before_maximum(ax)
    if mechanism == "float32_drops_additional_band":
        return ax_total, pe["step_four"]
    return ax_total, (pe["main"] if income < pe_upper else before_maximum(pe))


def _mechanism_text(year: int, measure: str, mechanism: str, isolation: bool) -> str:
    tax_year = f"{year}-{(year + 1) % 100:02d}"
    if mechanism == "class_1_deducted_from_class_4_profits":
        return (
            f"{tax_year} dual earners (employment plus self-employment; the thresholds "
            "agree this year): PolicyEngine's ni_class_4_main and ni_class_4 charge Class 4 "
            "on self_employment_income less ni_class_1_employee. SSCBA 1992 s.15(1) and "
            "Schedule 2 compute Class 4 on the trading profits chargeable to income tax, "
            "with no deduction for Class 1 contributions, so Axiom charges the full "
            "profits. The PolicyEngine value reproduces the s.15(3) percentages on "
            "(profits - its Class 1 total) exactly. Where the regulation 100 maximum "
            "binds, both engines agree and no row is recorded."
        )
    if mechanism == "float32_drops_additional_band":
        if isolation:
            return (
                f"Isolation case: both engines receive the same non-round Class 4 limits "
                f"(PolicyEngine's own CPI-uprated {year} values, supplied to PolicyEngine as "
                "a parameter reform and to the Axiom regulation 100 module as its limit "
                "inputs). With profits above the upper limit, regulation 100 case 2 applies "
                "and the maximum is the full main-plus-additional amount, as Axiom returns. "
                "PolicyEngine's ni_class_4_maximum compares step four with the main-rate "
                "Class 4 in float32. Rounding makes the two equal amounts differ, so it takes "
                "case 1 and returns step four (the main-band amount) alone, dropping the 2% "
                "additional band from ni_class_4_maximum and ni_class_4."
            )
        return (
            f"{tax_year}: PolicyEngine CPI-uprates the Class 4 limits to non-round values "
            "(PolicyEngine-UK#1879), and with those limits its float32 regulation 100 "
            "comparison takes case 1 for profits above the upper limit. It returns step "
            "four (the main-band amount) alone, dropping the 2% additional band "
            "(PolicyEngine-UK#1878). Axiom applies SSCBA 1992 s.15(3) at the unaltered "
            "12,570 / 50,270 limits and regulation 100 case 2. The PolicyEngine value "
            "reproduces 0.06 x (its upper - lower limit) exactly."
        )
    if measure.startswith("c1-"):
        return (
            f"{tax_year}: PolicyEngine CPI-uprates the Class 1 primary threshold and upper "
            "earnings limit (gov.hmrc.national_insurance.class_1.thresholds) from 2028. "
            "The government has announced they stay at 12,570 / 50,270 until April 2031 "
            "(HMRC policy paper, 26 Nov 2025). The Axiom Class 1 pipeline derives them "
            "from the personal allowance and basic rate limit, frozen at 12,570 / 37,700 "
            "through 2030-31 by FA 2021 s.5 as amended by FA 2026 s.10. Both engines "
            "charge the same earnings (PolicyEngine's ni_class_1_income). The PolicyEngine "
            "value reproduces the statutory percentages at its uprated thresholds "
            "(weekly x 52)."
        )
    return (
        f"{tax_year}: PolicyEngine CPI-uprates the Class 4 lower and upper profits limits "
        "(gov.hmrc.national_insurance.class_4.thresholds) from 2027. SSCBA 1992 s.15(3) "
        "fixes them at 12,570 / 50,270, alterable only by a Treasury order under SSAA "
        "1992 s.141(4)(d), in force for the following and subsequent tax years (s.142(3)). "
        "No such order has been made, so Axiom applies the unaltered limits. The "
        "PolicyEngine value reproduces the statutory percentages and regulation 100 "
        "steps at its uprated limits."
    )


def build() -> dict:
    report = json.loads(REPORT.read_text())
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in report.get("mismatches") or []:
        mechanism = row.get("pe_mechanism")
        if mechanism not in ISSUES:
            continue
        isolation = "float32-isolation" in row["case_id"]
        groups[(row["validation_year"], row["measure"], mechanism, isolation, row["concept"])].append(row)

    entries = []
    for (year, measure, mechanism, isolation, concept), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: str(r["case_id"]))
        representative = rows[0]
        axiom_expr, pe_expr = _expressions(representative)
        left = float(representative["left"])
        right = float(representative["right"])
        arithmetic = [
            {"expression": axiom_expr, "equals": round(left, 6), "tolerance": 0.005},
            {"expression": pe_expr, "equals": round(right, 6), "tolerance": 0.005},
            {
                "expression": f"({axiom_expr}) - ({pe_expr})",
                "equals": round(left - right, 6),
                "tolerance": 0.01,
            },
        ]
        for item in arithmetic:
            value = evaluate_arithmetic(item["expression"])
            if abs(value - item["equals"]) > item["tolerance"]:
                raise SystemExit(
                    f"{representative['case_id']}: {item['expression']} = {value}, "
                    f"expected {item['equals']}"
                )
        family = "c1" if measure.startswith("c1-") else "c4"
        issue = ISSUES[mechanism]
        sources = list(AXIOM_SOURCES[family])
        if mechanism == "cpi_uprated_thresholds" or (
            mechanism == "float32_drops_additional_band" and not isolation
        ):
            sources.append(RULESPEC_FREEZE_TESTS_PR)
        if mechanism == "float32_drops_additional_band" and not isolation:
            sources.append(FREEZE_ISSUE)
        slug = "float32-isolation" if isolation else mechanism.replace("_", "-")
        entries.append(
            {
                "id": f"nic-{year}-{measure}-{slug}",
                "concept": concept,
                "case_selector": {"case_ids": [r["case_id"] for r in rows]},
                "selector_binding": {
                    "units": len(rows),
                    "rows_sha256": selected_rows_sha256(rows),
                },
                "kind": "amount_difference",
                "disposition": "upstream_engine_gap",
                "evidence": {
                    "mechanism": _mechanism_text(year, measure, mechanism, isolation),
                    "arithmetic": arithmetic,
                    "upstream_url": issue,
                    "sources": sources,
                },
                "linked_issue": issue,
                "expires_on_source_change": True,
            }
        )
    return {
        "schema": "axiom_oracles.dispositions.v1",
        "suite": SUITE,
        "updated": report["provenance"].get("generated")
        or report["provenance"].get("generated_at", "")[:10],
        "entries": entries,
    }


HEADER = """\
# GENERATED by scripts/build_uk_national_insurance_pe_dispositions.py from the
# committed report; rerun it after regenerating the report. Every entry is an
# expected failure against the pinned PolicyEngine-UK, attributed to the filed
# PolicyEngine-UK issue whose mechanism the row reconciles to (to the penny, under
# PolicyEngine's own parameters). Entries are selector-bound: when a fixed
# PolicyEngine-UK release is pinned and the rows start matching, they expire.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()
    text = HEADER + yaml.safe_dump(build(), sort_keys=False, width=100, allow_unicode=True)
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT.relative_to(REPO_ROOT)} is stale; rerun without --check")
            return 1
        print(f"{OUTPUT.relative_to(REPO_ROOT)} is current")
        return 0
    OUTPUT.write_text(text)
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
