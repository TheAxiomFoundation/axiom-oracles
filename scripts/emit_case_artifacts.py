"""Emit per-suite case artifacts for the dashboard's case explorer.

Dashboard report copies slim case rows to 1,000, which forbids browsing
every match and mismatch. The full rows live in ``reports/``; this script
re-emits them as compact chunked JSON under
``dashboard/public/data/cases/<suite>/`` so the program pages can
lazy-load and filter them client-side without a server.

Disposition annotations (the native deviation-analysis layer,
``dispositions/<suite>.yaml``) are read from the DASHBOARD report copy —
the run already merged and normalized them there — so every mismatch a
disposition covers carries its class. The explorer's default view is the
queue of UNEXPLAINED mismatches, the raw material for the next
disposition.

Suites whose reports carry no per-case rows (the fiit harness) or whose
population exceeds the cap (SSI) fall back to mismatch-only artifacts:
one row per disagreeing case, flagged ``partial`` so the UI says matched
cases aren't listed.

Row shape (kept deliberately small):
    {"id": case_id, "r": match_rate,
     "h": {"n": household_size, "e": earned_income, "a": ages},
     "m": [{"c": concept, "l": left, "x": right, "d": difference,
            "e": disposition_kind_if_explained}, ...]}

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
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "public" / "data"
OUT_ROOT = DASHBOARD_DATA / "cases"
CHUNK_SIZE = 500
MAX_CASES = 25_000  # keep artifacts static-site friendly


def latest_full_report(basename: str) -> Path | None:
    """Newest full-population (-0-) report for a report basename."""
    candidates = sorted(
        REPORTS.glob(f"{basename}-0-*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def dashboard_report(basename: str) -> dict | None:
    """The slim, disposition-merged report the dashboard serves."""
    path = DASHBOARD_DATA / f"{basename}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def mismatches_complete(report: dict | None) -> bool:
    """True when the report's mismatch list is the whole population."""
    if not report:
        return False
    declared = (report.get("summary") or {}).get("mismatch_count")
    if declared is None:
        declared = report.get("mismatch_count")
    if declared is None:
        return False
    return len(report.get("mismatches") or []) == declared


def explained_lookup(report: dict | None) -> dict:
    """(case_id, concept) -> disposition class for annotated rows."""
    out = {}
    for m in (report or {}).get("mismatches") or []:
        note = m.get("disposition")
        if note:
            out[(m.get("case_id"), m.get("concept"))] = note.get(
                "disposition"
            )
    return out


def compact_case(case: dict, explained: dict) -> dict:
    hs = (case.get("metadata") or {}).get("household_summary") or {}
    ages = hs.get("ages") or []
    mismatches = []
    for m in case.get("mismatches") or []:
        row = {
            "c": m.get("concept"),
            "l": m.get("left"),
            "x": m.get("right"),
            "d": m.get("difference"),
        }
        kind = explained.get((case.get("case_id"), m.get("concept")))
        if kind:
            row["e"] = kind
        mismatches.append(row)
    row = {
        "id": case.get("case_id"),
        "r": case.get("match_rate"),
        "h": {
            "n": hs.get("household_size") or len(ages) or None,
            "e": round(sum(hs.get("yearly_earned_income_per_person") or [0])),
            "a": ages,
        },
        "m": mismatches,
    }
    # Small-suite reports carry full evidence (raw input records, matched
    # values). The dashboard copy keeps only the substantive inputs — most
    # records are zero/false defaults, and shipping all ~600 per case makes
    # the artifact two orders of magnitude heavier than the site can carry.
    # `i0` records how many defaults were dropped; the full report under
    # reports/ remains the complete record.
    records = (case.get("metadata") or {}).get("axiom_input_records")
    if records:
        kept = []
        dropped = 0
        for r in records:
            value = r.get("value")
            if value is None or value is False or value == 0 or value == "":
                dropped += 1
                continue
            kept.append(
                {"n": r.get("name"), "v": value, "e": r.get("entity_id")}
            )
        row["i"] = kept
        if dropped:
            row["i0"] = dropped
    matches = case.get("matches")
    if matches:
        row["v"] = [
            {"c": m.get("concept"), "l": m.get("left"), "x": m.get("right")}
            for m in matches
        ]
    return row


def normalize_mismatch(m: dict) -> dict:
    """Standard and fiit-harness mismatch rows -> one shape."""
    if "entity_id" in m and "case_id" not in m:
        # fiit harness: entity_id/surface/axiom/policyengine/diff, plus the
        # household context (ages/earned) newer runs attach to each row.
        return {
            "case_id": m.get("entity_id"),
            "concept": m.get("surface"),
            "left": m.get("axiom"),
            "right": m.get("policyengine"),
            "difference": m.get("diff"),
            "ages": [int(a) for a in (m.get("ages") or [])],
            "earned": m.get("earned"),
        }
    return {
        "case_id": m.get("case_id"),
        "concept": m.get("concept"),
        "left": m.get("left"),
        "right": m.get("right"),
        "difference": m.get("difference"),
        "ages": m.get("ages") or [],
        "earned": m.get("yearly_earned_income"),
    }


def mismatch_only_rows(report: dict, explained: dict) -> list[dict]:
    """One row per disagreeing case, from a complete mismatch list."""
    by_case: dict = {}
    for raw in report.get("mismatches") or []:
        m = normalize_mismatch(raw)
        row = by_case.setdefault(
            m["case_id"],
            {
                "id": m["case_id"],
                "r": None,
                "h": {
                    "n": len(m["ages"]) or None,
                    "e": round(m["earned"]) if m["earned"] else 0,
                    "a": m["ages"],
                },
                "m": [],
            },
        )
        entry = {
            "c": m["concept"],
            "l": m["left"],
            "x": m["right"],
            "d": m["difference"],
        }
        kind = explained.get((m["case_id"], m["concept"]))
        if kind:
            entry["e"] = kind
        row["m"].append(entry)
    return list(by_case.values())


def write_artifacts(
    suite: str,
    rows: list[dict],
    meta: dict,
    source: str,
    partial: bool,
) -> str:
    out_dir = OUT_ROOT / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("chunk-*.json"):
        stale.unlink()
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
        "engines": meta.get("engines"),
        "mismatch_concepts": concepts,
        "source": source,
        "total_cases": meta.get("total_cases") or len(rows),
    }
    if partial:
        index["partial"] = "mismatch-only"
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    mode = "mismatch-only rows" if partial else "cases"
    return f"wrote {suite}: {len(rows)} {mode} in {len(chunks)} chunks"


def emit_suite(suite: str, dashboard_config: dict) -> str:
    basename = dashboard_config["basename"]
    src = latest_full_report(basename)
    full = json.loads(src.read_text()) if src else None
    dash = dashboard_report(basename)
    if full is None and dash is None:
        return f"skip {suite}: no full report under reports/"

    # Dispositions live on the dashboard copy; only trust the lookup when
    # its mismatch list is the whole population.
    explained = (
        explained_lookup(dash) if mismatches_complete(dash) else {}
    )
    meta = {
        "engines": (full or {}).get("engines") or (dash or {}).get("engines"),
        "total_cases": (full or {}).get("case_count")
        or (full or {}).get("compared_tax_units")
        or (dash or {}).get("case_count"),
    }

    cases = (full or {}).get("cases") or []
    declared_cases = (full or {}).get("case_count")
    full_ok = (
        cases
        and (not declared_cases or len(cases) == declared_cases)
        and len(cases) <= MAX_CASES
    )
    if full_ok:
        rows = [compact_case(c, explained) for c in cases]
        return write_artifacts(suite, rows, meta, src.name, partial=False)

    # No usable case rows — fall back to a mismatch-only queue, from the
    # annotated dashboard list when complete, else the full report's own.
    if mismatches_complete(dash):
        rows = mismatch_only_rows(dash, explained)
        source = f"{basename}.json"
    elif full is not None and mismatches_complete(full):
        rows = mismatch_only_rows(full, explained)
        source = src.name
    else:
        if cases:
            return (
                f"skip {suite}: {len(cases)} cases exceeds cap and no "
                "complete mismatch list"
            )
        return f"skip {suite}: no case rows and no complete mismatch list"
    if not rows:
        return f"skip {suite}: no case rows, and nothing disagrees"
    if len(rows) > MAX_CASES:
        return f"skip {suite}: {len(rows)} mismatch rows exceeds artifact cap"
    return write_artifacts(suite, rows, meta, source, partial=True)


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
