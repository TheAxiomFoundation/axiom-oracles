#!/usr/bin/env python
"""Emit per-state dashboard reports from the state-tax Populace campaign.

The campaign runner (scripts/run_state_tax_populace.py) writes ONE
campaign-level report covering every ready state over the full pinned US
Populace. The dashboard is suite-keyed, so this script projects that
report into one slim axiom.comparison_report.v2 per state
(``axiom-policyengine-<st>-income-tax-populace.json``) and registers each
in ``dashboard/public/data/manifest.json``. Each projected report cites
the campaign report as its source of record.

Usage:
    .venv/bin/python scripts/emit_populace_campaign_artifacts.py [campaign.json]

With no argument the newest reports/state-tax-populace-campaign-*.json is
used.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "reports"
DASH_DATA = REPO_ROOT / "dashboard" / "public" / "data"


def latest_campaign_report() -> Path:
    candidates = sorted(REPORTS.glob("state-tax-populace-campaign-*.json"))
    if not candidates:
        raise SystemExit("no reports/state-tax-populace-campaign-*.json found")
    return candidates[-1]


def project_state(
    state: str, entry: dict, campaign: dict, source_name: str
) -> dict:
    compared = int(entry["compared_count"])
    mismatches = entry.get("mismatches") or []
    mismatch_count = int(entry["mismatch_count"])
    matched = compared - mismatch_count
    rate = (matched / compared * 100) if compared else 100.0
    concept = entry["output"]
    aggregate = {
        "comparison": "amount",
        "comparison_count": compared,
        "compared": compared,
        "components": [],
        "concept": concept,
        "description": (
            "State income tax liability over every routed tax unit in the "
            "pinned US Populace"
        ),
        "match_count": matched,
        "match_rate": rate,
        "matched": matched,
        "mismatch_count": mismatch_count,
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "weighted_match_rate": rate,
    }
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": f"{state.lower()}-income-tax-populace",
        "case_count": compared,
        "population": "populace-us",
        "engines": {
            "axiom": entry["program"],
            "policyengine": entry["policyengine_target"],
        },
        "aggregates": [aggregate],
        "cases": [],
        "mismatches": mismatches,
        "errors": [],
        "summary": {
            "comparison_count": compared,
            "match_count": matched,
            "match_rate": rate,
            "mismatch_count": mismatch_count,
        },
        "provenance": {
            "campaign_report": source_name,
            "dataset_identity": campaign.get("dataset_identity"),
            "runtime_provenance": campaign.get("runtime_provenance"),
            "tolerance": entry.get("tolerance"),
            "relative_tolerance": entry.get("relative_tolerance"),
            "max_absolute_difference": entry.get("max_absolute_difference"),
            "weighted_compared_tax_units": entry.get(
                "weighted_compared_tax_units"
            ),
        },
    }


CASES_ROOT = DASH_DATA / "cases"
CHUNK_SIZE = 500


def emit_case_chunks(state: str, entry: dict) -> str | None:
    """Project the campaign's per-tax-unit rows into case-explorer chunks.

    Campaign reports produced before the runner persisted rows have no
    ``cases`` key; those states keep the explorer's no-evidence message
    until the next campaign run.
    """

    rows = entry.get("cases") or []
    if not rows:
        return None
    suite = f"{state.lower()}-income-tax-populace"
    concept = entry.get("output") or "state_income_tax"
    out_rows = []
    for row in rows:
        matched = bool(row.get("matched"))
        compact = {
            "id": row.get("tax_unit_id"),
            "r": 1.0 if matched else 0.0,
            "h": {},
            "m": []
            if matched
            else [
                {
                    "c": concept,
                    "l": row.get("axiom"),
                    "x": row.get("policyengine"),
                    "d": round(
                        (row.get("axiom") or 0) - (row.get("policyengine") or 0),
                        2,
                    ),
                }
            ],
            "v": [
                {
                    "c": concept,
                    "l": row.get("axiom"),
                    "x": row.get("policyengine"),
                }
            ]
            if matched
            else [],
        }
        out_rows.append(compact)
    out_rows.sort(key=lambda r: r["r"])
    out_dir = CASES_ROOT / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("chunk-*.json"):
        stale.unlink()
    chunks = [
        out_rows[i : i + CHUNK_SIZE] for i in range(0, len(out_rows), CHUNK_SIZE)
    ]
    for i, chunk in enumerate(chunks):
        (out_dir / f"chunk-{i}.json").write_text(
            json.dumps(chunk, separators=(",", ":"))
        )
    index = {
        "suite": suite,
        "count": len(out_rows),
        "total_cases": len(out_rows),
        "chunks": len(chunks),
        "chunk_size": CHUNK_SIZE,
        "engines": {"left": "axiom", "right": "policyengine"},
        "mismatch_concepts": [concept],
        "source": "state-tax-populace-campaign",
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return f"{suite}: {len(out_rows)} cases in {len(chunks)} chunks"


def main() -> int:
    source = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else latest_campaign_report()
    )
    campaign = json.loads(source.read_text())
    states = (campaign.get("comparison") or {}).get("states") or {}
    if not states:
        raise SystemExit(f"{source} carries no per-state comparison block")

    manifest_path = DASH_DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    reports = list(manifest.get("reports") or [])

    for state, entry in sorted(states.items()):
        emitted = emit_case_chunks(state, entry)
        if emitted:
            print(emitted)
        report = project_state(state, entry, campaign, source.name)
        filename = f"axiom-policyengine-{state.lower()}-income-tax-populace.json"
        (DASH_DATA / filename).write_text(
            json.dumps(report, indent=1, sort_keys=True) + "\n"
        )
        if filename not in reports:
            reports.append(filename)
        print(
            f"{state}: {report['summary']['match_count']}/"
            f"{report['summary']['comparison_count']} -> {filename}"
        )

    manifest["reports"] = reports
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"manifest: {len(reports)} reports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
