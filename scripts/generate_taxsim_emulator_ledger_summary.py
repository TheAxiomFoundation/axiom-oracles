#!/usr/bin/env python3
"""Regenerate the ledger's count and remaining-cluster tables from full reports."""

from __future__ import annotations

import argparse
import gc
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_oracles.comparison.dispositions import CLASSIFIED_DISPOSITION_KINDS  # noqa: E402
from axiom_oracles.comparison.report_io import load_report  # noqa: E402

DOC = Path("docs/taxsim-emulator-ledger.md")


def sections(root: Path = ROOT) -> dict[str, str]:
    counts = [
        "| Year | Comparisons | Raw match rate | Explained rate | Explained mismatches | Unexplained |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    remaining = [
        "| Year | Bound unexplained | No ledger entry | Largest unbound state/concept populations | Largest rounded dollar clusters |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    maryland = []
    for year in range(2021, 2026):
        report = load_report(root / f"reports/taxsim-emulator/taxsim-emulator-ecps-{year}.json.gz")
        summary = report["summary"]
        block = summary["dispositioned"]
        explained = sum(block["counts"][kind] for kind in CLASSIFIED_DISPOSITION_KINDS)
        counts.append(
            f"| {year} | {summary['comparison_count']:,} | {block['raw_match_rate']:.4f}% | "
            f"{block['explained_rate']:.4f}% | {explained:,} | {block['unexplained_count']:,} |"
        )
        unbound = [row for row in report["mismatches"] if not row.get("disposition")]
        populations: Counter[tuple[str, str]] = Counter()
        dollars: Counter[tuple[str, int]] = Counter()
        for row in unbound:
            state = (row.get("facts") or {}).get("state") or "US"
            concept = "state" if "state-income-tax#" in row["concept"] else "federal"
            populations[state, concept] += 1
            if concept == "state":
                dollars[state, round(row["difference"])] += 1
        top_populations = "; ".join(
            f"{state} {concept} {count:,}" for (state, concept), count
            in sorted(populations.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
        )
        top_dollars = "; ".join(
            f"{state} {'+' if amount >= 0 else '-'}${abs(amount):,}: {count:,}"
            for (state, amount), count
            in sorted(dollars.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
        )
        remaining.append(
            f"| {year} | {block['counts']['unexplained']:,} | {len(unbound):,} | "
            f"{top_populations} | {top_dollars} |"
        )
        if year >= 2024:
            maryland.append(populations["MD", "state"])
    remaining.extend([
        "", "All listed dollar clusters are state-liability differences, rounded to the",
        "nearest dollar for descriptive grouping only. Their selectors were not",
        f"expanded on that basis. Maryland's unbound state residuals number {maryland[0]}/{maryland[1]}",
        "in 2024/2025, after the county signature; they do not share its $1 identity.",
    ])
    return {"LEDGER COUNTS": "\n".join(counts), "REMAINING CLUSTERS": "\n".join(remaining)}


def render(text: str, generated: dict[str, str]) -> str:
    for name, body in generated.items():
        pattern = re.compile(rf"(<!-- BEGIN {name} -->\n).*?(\n<!-- END {name} -->)", re.S)
        text, count = pattern.subn(lambda match: match[1] + body + match[2], text)
        if count != 1:
            raise ValueError(f"expected exactly one {name} marker pair")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / DOC
    original = path.read_text()
    rendered = render(original, sections())
    if args.check:
        if rendered != original:
            print(f"drift: {DOC}; run uv run scripts/generate_taxsim_emulator_ledger_summary.py")
            return 1
        print("TAXSIM ledger documentation counts match full reports")
        return 0
    path.write_text(rendered)
    print(f"wrote generated tables in {DOC}")
    return 0


if __name__ == "__main__":
    gc.disable()
    raise SystemExit(main())
