#!/usr/bin/env python3
"""Export verified adjudications and bound mismatch counts for dashboard notes.

Counts are report mismatch rows, not households. An adjudication with no bound
row in a state/year is included with zero affected_rows and an empty ledger_entries
list; its existence does not establish the cause of an unclassified difference.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_oracles.comparison.adjudications import load_adjudications  # noqa: E402
from axiom_oracles.comparison.dispositions import (  # noqa: E402
    apply_dispositions,
    load_dispositions,
)
from axiom_oracles.comparison.report_io import load_report, registered_report_suites  # noqa: E402

OUTPUT = Path("reports/taxsim-emulator/dashboard-notes.json")
EXPLAINING = {"explained_residual", "upstream_engine_gap"}


def dashboard_notes(repo_root: Path = ROOT) -> dict:
    """Derive a deterministic artifact; validate every atom and population first."""
    registry_path = repo_root / "adjudications/taxsim-emulator.yaml"
    registry = load_adjudications(registry_path, repo_root=repo_root)
    ready = {record["id"]: record for record in registry["adjudications"]
             if record["status"] == "evidence_ready"}
    suites = {path.stem for path in (repo_root / "comparisons").glob("taxsim-emulator-*.yaml")}
    periods: set[tuple[str, int]] = set()
    counts: Counter[tuple[str, int, str, str, str]] = Counter()
    ledger: dict[tuple[str, str], dict] = {}
    sources = []
    registered = registered_report_suites(repo_root, suites=suites)
    for path in sorted(registered):
        report = load_report(path)
        suite = report["suite"]
        if suite != registered[path]:
            raise ValueError(f"registered report {path} names an unexpected suite {suite!r}")
        if len(report.get("mismatches", [])) != report["summary"]["mismatch_count"]:
            raise ValueError(f"{path}: dashboard notes require the full report")
        dispositions_path = repo_root / "dispositions" / f"{suite}.yaml"
        dispositions = (load_dispositions(dispositions_path, repo_root=repo_root)
                        if dispositions_path.exists() else None)
        entries = {entry["id"]: entry for entry in (dispositions or {}).get("entries", [])}
        merged = apply_dispositions(
            report, dispositions, dispositions_file=str(dispositions_path.relative_to(repo_root)),
            repo_root=repo_root,
        )
        block = merged["summary"]["dispositioned"]
        failed = set(block["expired_entries"]) | set(block["orphaned_entries"])
        if any(entries[entry_id]["disposition"] in EXPLAINING for entry_id in failed):
            raise ValueError(f"{suite}: an explained entry has expired or has no bound rows")
        config = yaml.safe_load((repo_root / "comparisons" / f"{suite}.yaml").read_text())
        period = config.get("runner", {}).get("parameters", {}).get("period")
        years = {int(period)} if period is not None and str(period).isdigit() else set()
        for row in merged.get("mismatches", []):
            facts = row.get("facts") or {}
            year = facts.get("year")
            state = facts.get("state") or "US"
            if not isinstance(year, int) or isinstance(year, bool):
                raise ValueError(f"{suite}: mismatch row lacks a law year")
            periods.add((state, year))
            years.add(year)
            annotation = row.get("disposition") or {}
            if annotation.get("disposition") not in EXPLAINING:
                continue
            entry = entries[annotation["id"]]
            reference = entry["adjudication"]
            if reference not in ready:
                raise ValueError(f"{suite}: explanation lacks an evidence_ready adjudication")
            counts[state, year, reference, suite, entry["id"]] += 1
            ledger[suite, entry["id"]] = {
                "suite": suite, "entry_id": entry["id"], "concept": entry["concept"],
                "disposition": entry["disposition"],
            }
        # Include states with no mismatches as well. They have no attributed rows.
        for locale in report.get("locales", []):
            state = locale.removeprefix("US-")
            periods.update((state, year) for year in years)
        sources.append(str(path.relative_to(repo_root)))
    bound: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
    for (state, year, reference, suite, entry_id), count in sorted(counts.items()):
        bound[state, year, reference].append({**ledger[suite, entry_id], "affected_rows": count})
    notes = []
    for state, year in sorted(periods):
        adjudications = []
        for reference, record in sorted(ready.items()):
            if year not in record["law_years"] or record["jurisdiction"] not in {"US", state}:
                continue
            entries = bound.get((state, year, reference), [])
            adjudications.append({
                "id": reference, "verdict": record["verdict"],
                "attribution": record["attribution"], "jurisdiction": record["jurisdiction"],
                "description": record["question"], "issues": sorted(record["issues"]),
                "affected_rows": sum(entry["affected_rows"] for entry in entries),
                "ledger_entries": entries,
            })
        notes.append({"state": state, "year": year, "adjudications": adjudications})
    return {
        "schema": "axiom_oracles.taxsim_dashboard_notes.v1",
        "registry": "adjudications/taxsim-emulator.yaml",
        "count_unit": "comparison mismatch rows",
        "reports": sources, "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(dashboard_notes(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path = ROOT / OUTPUT
    if args.check:
        if not path.exists() or path.read_text() != rendered:
            print(f"drift: {OUTPUT}; run uv run scripts/export_taxsim_dashboard_notes.py")
            return 1
        print("TAXSIM dashboard notes match verified adjudications and bound report rows")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    gc.disable()
    raise SystemExit(main())
