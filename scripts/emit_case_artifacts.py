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


# Compared-concept values ride in the case's mismatch/match rows already;
# everything else axiom_*-prefixed in metadata is per-case evidence worth
# showing (income intermediates, deduction amounts, eligibility-path flags).
ENGINE_PAIR_SKIP = {"axiom_snap_eligible", "axiom_snap_allotment"}


def engine_pair_records(metadata: dict) -> list[dict]:
    """Fallback input panel from flat axiom_*/pe_* metadata columns.

    The encoder-backed SNAP harness exports per-case intermediates
    (gross/net income, shelter deduction, utility allowance) as metadata
    instead of raw input records. Surface Axiom's value under the bare
    name; when PolicyEngine's counterpart differs beyond rounding, show
    it alongside.
    """
    out = []
    for key in sorted(metadata):
        if not key.startswith("axiom_") or key in ENGINE_PAIR_SKIP:
            continue
        # Bookkeeping columns (axiom_input_records_count, axiom_relations_
        # count) are metadata about the projection, not household inputs —
        # rendering them as panel rows is how "input records count 507"
        # ended up masquerading as the household's only information.
        if key.endswith("_count"):
            continue
        # The snap_*-prefixed diagnostic columns duplicate the short-name
        # intermediates (snap_gross_monthly_income == gross_income) and
        # echo the compared allotment itself.
        if key.startswith("axiom_snap_"):
            continue
        value = metadata[key]
        if value is None or isinstance(value, str):
            continue
        name = key[len("axiom_") :]
        out.append({"n": name, "v": value})
        peer = metadata.get("pe_" + name)
        numeric = isinstance(peer, (int, float)) and isinstance(
            value, (int, float)
        )
        if peer is not None and (
            abs(peer - value) >= 0.005 if numeric else peer != value
        ):
            out.append({"n": f"{name} (policyengine)", "v": peer})
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
    earned = hs.get("yearly_earned_income_per_person")
    row = {
        "id": case.get("case_id"),
        "r": case.get("match_rate"),
        "h": {
            "n": hs.get("household_size") or len(ages) or None,
            # None (not 0) when the harness never captured earnings — the
            # UI renders "$0 / year" for 0, which asserts a fact we lack.
            "e": round(sum(earned)) if earned else None,
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
            if isinstance(value, dict):
                value = value.get("value")
            try:
                if value is not None and not isinstance(value, bool):
                    value = float(value)
                    if value == int(value):
                        value = int(value)
            except (TypeError, ValueError):
                pass
            if value is None or value is False or value == 0 or value == "":
                dropped += 1
                continue
            kept.append(
                {"n": r.get("name"), "v": value, "e": r.get("entity_id")}
            )
        row["i"] = kept
        if dropped:
            row["i0"] = dropped
        # Consumed by write_artifacts for the suite-level slot dictionary,
        # stripped before chunks are written.
        row["_all_input_names"] = [{"name": r.get("name")} for r in records]
    outputs = (case.get("metadata") or {}).get("axiom_all_outputs")
    if isinstance(outputs, dict) and outputs:
        kept_o = []
        dropped_o = 0
        for name in sorted(outputs):
            value = outputs[name]
            if value is None or value is False or value == 0:
                dropped_o += 1
                continue
            kept_o.append({"n": name, "v": value})
        row["o"] = kept_o
        if dropped_o:
            row["o0"] = dropped_o
        row["_all_output_names"] = sorted(outputs)
    else:
        synth = engine_pair_records(case.get("metadata") or {})
        if synth:
            row["i"] = synth
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
                    "e": round(m["earned"]) if m["earned"] is not None else None,
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
    input_slots = sorted(
        {
            record.get("name")
            for row in rows
            for record in row.get("_all_input_names", [])
            if record.get("name")
        }
    )
    output_slots = sorted(
        {name for row in rows for name in row.get("_all_output_names", [])}
    )
    for row in rows:
        row.pop("_all_input_names", None)
        row.pop("_all_output_names", None)
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
        **({"input_slots": input_slots} if input_slots else {}),
        **({"output_slots": output_slots} if output_slots else {}),
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
    source_name = src.name if src else None
    if not cases and dash is not None:
        # Legacy hand-run suites embed their complete rows in the dashboard
        # copy itself (nyc-synthetic); treat that as the full source when
        # the row count matches the declared population.
        dash_cases = dash.get("cases") or []
        if dash_cases and len(dash_cases) == (dash.get("case_count") or 0):
            cases = dash_cases
            declared_cases = dash.get("case_count")
            source_name = f"{basename}.json (embedded)"
    full_ok = (
        cases
        and (not declared_cases or len(cases) == declared_cases)
        and len(cases) <= MAX_CASES
    )
    if full_ok:
        rows = [compact_case(c, explained) for c in cases]
        return write_artifacts(suite, rows, meta, source_name, partial=False)

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
    """suite -> {basename} from the comparison configs, plus any manifest
    report whose suite has no config (legacy hand-run suites like
    nyc-synthetic) — those emit from the dashboard report's own embedded
    rows when complete."""
    out = {}
    for path in glob.glob(str(REPO_ROOT / "comparisons" / "*.yaml")):
        text = Path(path).read_text()
        suite = re.search(r'^\s*suite:\s*([\w-]+)', text, re.M)
        base = re.search(r'^\s*report_basename:\s*([\w-]+)', text, re.M)
        if suite and base:
            out[suite.group(1)] = {"basename": base.group(1)}
    manifest = DASHBOARD_DATA / "manifest.json"
    if manifest.exists():
        for name in json.loads(manifest.read_text()).get("reports", []):
            path = DASHBOARD_DATA / name
            if not path.exists():
                continue
            try:
                report = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            suite = report.get("suite")
            if suite and suite not in out:
                out[suite] = {"basename": name[: -len(".json")]}
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
