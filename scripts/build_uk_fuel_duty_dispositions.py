#!/usr/bin/env python3
"""Build dispositions/uk-fuel-duty.yaml from the committed fuel duty schedule report.

Each mismatch row in the report carries ``pe_mechanism``
(scripts/generate_uk_fuel_duty.py). This script groups the reconciled rows by
(calendar year, mechanism) and writes one selector-bound entry per group:

* ``superseded_schedule_calendar_average``: PolicyEngine applies a calendar-year
  average of the pre-May-2026 Budget 2025 schedule, dated 1 January, where the
  law charges the dated SI rates. ``upstream_engine_gap``, PolicyEngine-UK#1882.
* ``rpi_indexation_not_enacted``: from April 2027 PolicyEngine applies forecast
  RPI uprating (Budget 2025 policy) that no enacted instrument provides; the
  statute holds s.6(1A) at £0.5795. ``explained_residual``. PolicyEngine models
  announced policy by design (the #1882 fix, PR #1883, keeps the forecast
  steps), so this is a documented difference of convention, not a defect.

Selector bindings pin the rows' values, so pinning a fixed PolicyEngine-UK
release expires the entries; rerun this script to rebuild them.

    uv run python scripts/build_uk_fuel_duty_dispositions.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    evaluate_arithmetic,
    selected_rows_sha256,
)

SUITE = "uk-fuel-duty"
REPORT = REPO_ROOT / "dashboard" / "public" / "data" / "axiom-policyengine-uk-fuel-duty.json"
OUTPUT = REPO_ROOT / "dispositions" / f"{SUITE}.yaml"

FUEL_DUTY_ISSUE = "https://github.com/PolicyEngine/policyengine-uk/issues/1882"
FUEL_DUTY_PR = "https://github.com/PolicyEngine/policyengine-uk/pull/1883"
AXIOM_ENCODING_ISSUE = "https://github.com/TheAxiomFoundation/rulespec-uk/issues/349"
BUDGET_2025_COSTINGS = (
    "https://assets.publishing.service.gov.uk/media/692872fd2a37784b16ecf676/"
    "Budget_2025-Policy_Costings.pdf"
)
SOURCES = [
    "reference/uk-fuel-duty-schedule/schedule.yaml",
    "https://github.com/TheAxiomFoundation/rulespec-uk/blob/main/uk/policies/govuk/fuel-duty.yaml",
    "https://github.com/TheAxiomFoundation/rulespec-uk/blob/main/uk/policies/govuk/fuel-duty.test.yaml",
    AXIOM_ENCODING_ISSUE,
]

KIND = {
    "superseded_schedule_calendar_average": "upstream_engine_gap",
    "rpi_indexation_not_enacted": "explained_residual",
}


def _mechanism_text(year: str, mechanism: str) -> str:
    if mechanism == "superseded_schedule_calendar_average":
        return (
            f"{year}: PolicyEngine's gov.hmrc.fuel_duty.petrol_and_diesel holds one value "
            "per calendar year, dated 1 January: an average of the Budget 2025 schedule, "
            "whose 1 September 2026 and 1 December 2026 steps SI 2026/555 removed or moved "
            "before they took effect. The law charges the dated rates: SI 2022/365's "
            "8.63% reduction (52.95p) to 31 December 2026, SI 2026/164 art. 8's 3.45% "
            "(55.95p) for January and February 2027, and the HODA 1979 s.6(1A) 57.95p "
            "from 1 March 2027. The PolicyEngine value is exactly its parameter read at "
            "the month start (less the supplied rural relief on rural rows)."
        )
    return (
        f"{year}: from April 2027 PolicyEngine applies forecast RPI uprating of fuel "
        "duty, which Budget 2025 announced ('by Retail Prices Index (RPI) from April "
        "2027'). No Finance Act or order has amended HODA 1979 s.6(1A) or made a "
        "reduction or surcharge for these months, so the law charges £0.5795 a litre. "
        "PolicyEngine models announced policy by design, and its #1882 fix (PR #1883) "
        "keeps these forecast steps. Pinned at 2.102.0 the forecast path is also "
        "averaged by calendar year (#1882). The PolicyEngine value is exactly its "
        "parameter read at the month start."
    )


def build() -> dict:
    report = json.loads(REPORT.read_text())
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in report.get("mismatches") or []:
        mechanism = row.get("pe_mechanism")
        if mechanism not in KIND:
            continue
        groups[(row["month"][:4], mechanism, row["concept"])].append(row)

    entries = []
    for (year, mechanism, concept), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: str(r["case_id"]))
        rep = rows[0]
        relief = float(rep.get("rural_relief") or 0.0)
        axiom_expr = f"{rep['statutory_rate']!r} - {relief!r}"
        pe_expr = f"{rep['policyengine_petrol_and_diesel']!r} - {relief!r}"
        arithmetic = [
            {"expression": axiom_expr, "equals": round(float(rep["left"]), 6), "tolerance": 0.00005},
            {"expression": pe_expr, "equals": round(float(rep["right"]), 6), "tolerance": 0.00005},
            {
                "expression": f"({axiom_expr}) - ({pe_expr})",
                "equals": round(float(rep["left"]) - float(rep["right"]), 6),
                "tolerance": 0.0001,
            },
        ]
        for item in arithmetic:
            value = evaluate_arithmetic(item["expression"])
            if abs(value - item["equals"]) > item["tolerance"]:
                raise SystemExit(
                    f"{rep['case_id']}: {item['expression']} = {value}, expected {item['equals']}"
                )
        evidence = {
            "mechanism": _mechanism_text(year, mechanism),
            "arithmetic": arithmetic,
            "sources": list(SOURCES)
            + ([BUDGET_2025_COSTINGS, FUEL_DUTY_PR] if mechanism == "rpi_indexation_not_enacted" else []),
        }
        entry = {
            "id": f"fd-{year}-{mechanism.replace('_', '-')}",
            "concept": concept,
            "case_selector": {"case_ids": [r["case_id"] for r in rows]},
            "selector_binding": {"units": len(rows), "rows_sha256": selected_rows_sha256(rows)},
            "kind": "amount_difference",
            "disposition": KIND[mechanism],
            "evidence": evidence,
            "expires_on_source_change": True,
        }
        if mechanism == "superseded_schedule_calendar_average":
            evidence["upstream_url"] = FUEL_DUTY_ISSUE
            entry["linked_issue"] = FUEL_DUTY_ISSUE
        entries.append(entry)
    return {
        "schema": "axiom_oracles.dispositions.v1",
        "suite": SUITE,
        "updated": report["provenance"].get("generated")
        or report["provenance"].get("generated_at", "")[:10],
        "entries": entries,
    }


HEADER = """\
# GENERATED by scripts/build_uk_fuel_duty_dispositions.py from the committed
# report; rerun it after regenerating the report. Rows are attributed only when
# PolicyEngine's value is exactly its own parameter at the month start, and are
# selector-bound, so pinning a fixed PolicyEngine-UK release expires them.
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
