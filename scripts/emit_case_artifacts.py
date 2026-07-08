"""Emit per-suite case artifacts for the dashboard's case explorer.

Dashboard report copies slim case rows to 1,000, which forbids browsing
every match and mismatch. The full rows live in ``reports/``; this script
re-emits them as compact chunked JSON under
``dashboard/public/data/cases/<suite>/`` so the program pages can
lazy-load and filter them client-side without a server.

Row shape (kept deliberately small):
    {"id": case_id, "r": match_rate,
     "h": {"n": household_size, "e": earned_income, "a": ages},
     "m": [{"c": concept, "l": left, "x": right, "d": difference}, ...]}

Usage:
    .venv/bin/python scripts/emit_case_artifacts.py            # all suites
    .venv/bin/python scripts/emit_case_artifacts.py <suite>...  # named suites
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "reports"
OUT_ROOT = REPO_ROOT / "dashboard" / "public" / "data" / "cases"
CHUNK_SIZE = 500
MAX_CASES = 25_000  # keep artifacts static-site friendly


def latest_full_report(basename: str) -> Path | None:
    """Newest full-population (-0-) report for a report basename."""
    candidates = sorted(
        REPORTS.glob(f"{basename}-0-*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def compact_case(case: dict) -> dict:
    hs = (case.get("metadata") or {}).get("household_summary") or {}
    ages = hs.get("ages") or []
    row = {
        "id": case.get("case_id"),
        "r": case.get("match_rate"),
        "h": {
            "n": hs.get("household_size") or len(ages) or None,
            "e": round(sum(hs.get("yearly_earned_income_per_person") or [0])),
            "a": ages,
        },
        "m": [
            {
                "c": m.get("concept"),
                "l": m.get("left"),
                "x": m.get("right"),
                "d": m.get("difference"),
            }
            for m in case.get("mismatches") or []
        ],
    }
    return row


def emit_suite(suite: str, dashboard_config: dict) -> str:
    basename = dashboard_config["basename"]
    src = latest_full_report(basename)
    if src is None:
        return f"skip {suite}: no full report under reports/"
    report = json.loads(src.read_text())
    cases = report.get("cases") or []
    declared = report.get("case_count")
    if not cases:
        return f"skip {suite}: report has no case rows"
    if declared and len(cases) != declared:
        return f"skip {suite}: report itself is truncated ({len(cases)}/{declared})"
    if len(cases) > MAX_CASES:
        return f"skip {suite}: {len(cases)} cases exceeds artifact cap"

    out_dir = OUT_ROOT / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("chunk-*.json"):
        stale.unlink()
    rows = [compact_case(c) for c in cases]
    chunks = [rows[i : i + CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]
    for i, chunk in enumerate(chunks):
        (out_dir / f"chunk-{i}.json").write_text(
            json.dumps(chunk, separators=(",", ":"))
        )
    concepts = sorted(
        {m["c"] for row in rows for m in row["m"] if m.get("c")}
    )
    index = {
        "suite": suite,
        "count": len(rows),
        "chunks": len(chunks),
        "chunk_size": CHUNK_SIZE,
        "engines": report.get("engines"),
        "mismatch_concepts": concepts,
        "source": src.name,
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return f"wrote {suite}: {len(rows)} cases in {len(chunks)} chunks"


def dashboard_suites() -> dict[str, dict]:
    """suite -> {basename} from the comparison configs."""
    out = {}
    for path in glob.glob(str(REPO_ROOT / "comparisons" / "*.yaml")):
        text = Path(path).read_text()
        suite = re.search(r'^\s*suite:\s*([\w-]+)', text, re.M)
        base = re.search(r'^\s*report_basename:\s*([\w-]+)', text, re.M)
        if suite and base:
            out[suite.group(1)] = {"basename": base.group(1)}
    return out


def main() -> None:
    suites = dashboard_suites()
    wanted = sys.argv[1:] or sorted(suites)
    for suite in wanted:
        if suite not in suites:
            print(f"skip {suite}: unknown suite")
            continue
        print(emit_suite(suite, suites[suite]))


if __name__ == "__main__":
    main()
