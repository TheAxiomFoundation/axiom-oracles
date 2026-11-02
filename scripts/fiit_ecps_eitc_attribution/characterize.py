"""Characterize every mismatch row of a fiit-ecps raw report, per row.

Prints counts by surface and output, sign splits, and |diff| / relative-diff
extremes, and tests the per-row predicates the committed dispositions claim
for the non-EITC surfaces (July 2026 text):

- tax_before_credits: |diff| <= 5.83, both signs (bracket rounding);
- capital-gain definitions: |diff| <= 3.25 (float noise);
- ctc: diff == +50 exactly (one $1,000 excess-AGI increment x 5%).

Usage: python characterize.py <raw report.json> [--out summary.json]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    raw = json.loads(args.report.read_text())
    rows = raw["mismatches"]
    print(
        f"compared_tax_units={raw.get('compared_tax_units')} "
        f"compared_values={raw.get('compared_values')} mismatches={len(rows)}"
    )
    by_output: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_output[(row["surface"], row["output"])].append(row)
    summary = {}
    for (surface, output), group in sorted(by_output.items()):
        diffs = [float(row["diff"]) for row in group]
        rel = [
            abs(float(row["diff"])) / max(abs(float(row["policyengine"])), 1e-9)
            for row in group
        ]
        units = {row["entity_id"] for row in group}
        entry = {
            "rows": len(group),
            "units": len(units),
            "axiom_gt_pe": sum(d > 0 for d in diffs),
            "axiom_lt_pe": sum(d < 0 for d in diffs),
            "max_abs_diff": max(abs(d) for d in diffs),
            "min_abs_diff": min(abs(d) for d in diffs),
            "max_rel_diff": max(rel),
        }
        summary[f"{surface}/{output}"] = entry
        print(f"{surface:28s} {output:52s} {entry}")
    surfaces = Counter(row["surface"] for row in rows)
    print("by surface:", dict(surfaces))

    def check(surface_names, predicate, label):
        group = [row for row in rows if row["surface"] in surface_names]
        failing = [row for row in group if not predicate(float(row["diff"]))]
        print(f"{label}: {len(group)} rows, {len(failing)} fail the predicate")
        return {"rows": len(group), "failing": failing[:50], "failing_count": len(failing)}

    checks = {
        "tax_before_credits": check(
            {"tax-before-credits"}, lambda d: abs(d) <= 5.83 + 1e-9, "tbc |diff|<=5.83"
        ),
        "capital_gain": check(
            {"capital-gain-definitions"}, lambda d: abs(d) <= 3.25 + 1e-9, "cg |diff|<=3.25"
        ),
        "ctc": check({"ctc"}, lambda d: abs(d - 50.0) <= 1e-6, "ctc diff==+50"),
    }
    if args.out:
        args.out.write_text(
            json.dumps({"by_output": summary, "checks": checks}, indent=1, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
