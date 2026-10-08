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
     "m": [{"c": concept, "l": left, "x": right, "d": right_minus_left,
            "e": disposition_kind_if_explained}, ...]}

Usage:
    .venv/bin/python scripts/emit_case_artifacts.py            # all suites
    .venv/bin/python scripts/emit_case_artifacts.py <suite>...  # named suites
    .venv/bin/python scripts/emit_case_artifacts.py --check <suite>...
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.evidence import (  # noqa: E402
    dashboard_delta,
    dashboard_match_rate,
)

REPORTS = REPO_ROOT / "reports"
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "public" / "data"
OUT_ROOT = DASHBOARD_DATA / "cases"
CHUNK_SIZE = 500
MAX_CASES = 25_000  # keep artifacts static-site friendly
CHUNK_INDEX_SCHEMA_VERSION = "axiom_oracles.chunk_index.v1"


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


def has_versioned_chunks(suite: str) -> bool:
    """Whether an existing chunk corpus is report-bound and must be preserved."""

    path = OUT_ROOT / suite / "index.json"
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == CHUNK_INDEX_SCHEMA_VERSION
    )


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
    metadata = case.get("metadata") or {}
    hs = metadata.get("household_summary") or {}
    ages = hs.get("ages") or []
    mismatches = []
    for m in case.get("mismatches") or []:
        row = {
            "c": m.get("concept"),
            "l": m.get("left"),
            "x": m.get("right"),
            "d": dashboard_delta(m.get("left"), m.get("right")),
        }
        kind = explained.get((case.get("case_id"), m.get("concept")))
        if kind:
            row["e"] = kind
        mismatches.append(row)
    if case.get("matched") is False and not mismatches:
        # SNAP-QC case rows carry a headline boolean and first divergent stage
        # rather than comparator-style value rows. Preserve that negative
        # verdict as an explicit compact mismatch even when the producer has
        # no case-local values; otherwise the household explorer labels the
        # row "engines agree."
        stage = case.get("stage")
        mismatches.append(
            {
                "c": stage if isinstance(stage, str) and stage else "mismatch",
                "l": None,
                "x": None,
                "d": None,
            }
        )
    earned = hs.get("yearly_earned_income_per_person")
    matches = case.get("matches")
    match_rate = case.get("match_rate")
    if isinstance(matches, list):
        match_rate = dashboard_match_rate(len(matches), len(mismatches))
    row = {
        "id": case.get("case_id"),
        "r": match_rate,
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
    records = metadata.get("axiom_input_records")
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
    outputs = metadata.get("axiom_all_outputs")
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
        synth = engine_pair_records(metadata)
        if synth:
            row["i"] = synth
    # A report-bound chunk can also be the durable input source for a
    # hermetic executable receipt. Preserve the exact post-bridge Axiom
    # inputs when the producer exposes them, plus the small bridge/aggregation
    # facts needed to reconstruct record-oriented runs. This is deliberately
    # narrower than copying all case metadata (notably EUROMOD input tables).
    execution = {
        "schema_version": "axiom_oracles.case_execution.v1",
    }
    axiom_inputs = metadata.get("axiom_inputs")
    if isinstance(axiom_inputs, dict):
        execution["axiom_inputs"] = axiom_inputs
    for key in (
        "axiom_entity",
        "axiom_entity_id",
        "axiom_input_records_count",
        "axiom_result_aggregation",
        "euromod_to_axiom_input_bridge_applied",
    ):
        if metadata.get(key) is not None:
            execution[key] = metadata[key]
    if len(execution) > 1:
        row["execution"] = execution
    if isinstance(matches, list):
        row["v"] = [
            {"c": m.get("concept"), "l": m.get("left"), "x": m.get("right")}
            for m in matches
        ]
    elif "matches" in case:
        raise ValueError("full-evidence case matches must be an array")
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
            "d": dashboard_delta(m["left"], m["right"]),
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

    # Once a report has moved inline cases into a versioned chunk corpus, a
    # skip/re-emit run may intentionally carry no inline rows. Do not replace
    # that complete corpus with an empty mismatch-only projection. The binding
    # generator that runs next permits an idempotent index only and fails if a
    # changed report lacks producer-refreshed chunks.
    if has_versioned_chunks(suite):
        return f"preserve {suite}: versioned chunks (no full case rows in this run)"

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


def _load_served_rows(suite: str, index: dict) -> tuple[list[dict], list[str]]:
    """Load exactly the chunks declared by an artifact index."""
    problems: list[str] = []
    out_dir = OUT_ROOT / suite
    declared_chunks = index.get("chunks")
    if isinstance(declared_chunks, int) and not isinstance(declared_chunks, bool):
        if declared_chunks < 0:
            return [], [f"{suite}: index.chunks must be non-negative"]
        expected_names = {f"chunk-{i}.json" for i in range(declared_chunks)}
    elif (
        index.get("schema_version") == CHUNK_INDEX_SCHEMA_VERSION
        and isinstance(declared_chunks, list)
    ):
        declared_names: list[str] = []
        for position, descriptor in enumerate(declared_chunks):
            name = descriptor.get("name") if isinstance(descriptor, dict) else None
            if not isinstance(name, str) or not re.fullmatch(
                r"chunk-\d+\.json", name
            ):
                problems.append(
                    f"{suite}: index.chunks[{position}].name is invalid"
                )
                continue
            declared_names.append(name)
        if len(set(declared_names)) != len(declared_names):
            problems.append(f"{suite}: index.chunks repeats a chunk name")
        expected_names = set(declared_names)
        chunk_count = index.get("chunk_count")
        if (
            isinstance(chunk_count, bool)
            or not isinstance(chunk_count, int)
            or chunk_count < 0
        ):
            problems.append(
                f"{suite}: index.chunk_count must be a non-negative integer"
            )
        elif chunk_count != len(declared_chunks):
            problems.append(
                f"{suite}: index.chunk_count {chunk_count} != "
                f"{len(declared_chunks)} descriptors"
            )
    else:
        return [], [
            f"{suite}: index.chunks must be a non-negative integer or "
            "a v1 descriptor array"
        ]
    actual_names = {path.name for path in out_dir.glob("chunk-*.json")}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        stale = sorted(actual_names - expected_names)
        problems.append(
            f"{suite}: chunk file set drift (missing={missing}, stale={stale})"
        )
    chunk_size = index.get("chunk_size")
    if not isinstance(chunk_size, int) or chunk_size <= 0:
        problems.append(f"{suite}: index.chunk_size must be a positive integer")
        chunk_size = CHUNK_SIZE

    rows: list[dict] = []
    for name in sorted(expected_names, key=lambda item: int(item[6:-5])):
        path = out_dir / name
        if not path.exists():
            continue
        try:
            chunk = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{suite}: cannot read {name}: {exc}")
            continue
        if not isinstance(chunk, list):
            problems.append(f"{suite}: {name} is not a JSON array")
            continue
        if len(chunk) > chunk_size:
            problems.append(
                f"{suite}: {name} has {len(chunk)} rows, above chunk_size "
                f"{chunk_size}"
            )
        rows.extend(chunk)
    return rows, problems


def _canonical_mismatch_payloads(
    report: dict,
) -> tuple[dict[tuple[str, str], dict], list[str]]:
    payloads: dict[tuple[str, str], dict] = {}
    problems: list[str] = []
    for raw in report.get("mismatches") or []:
        normalized = normalize_mismatch(raw)
        case_id = normalized.get("case_id")
        concept = normalized.get("concept")
        if case_id is None or concept is None:
            problems.append("canonical mismatch is missing case_id/concept")
            continue
        key = (str(case_id), str(concept))
        if key in payloads:
            problems.append(f"canonical duplicate mismatch identity {key}")
            continue
        disposition = raw.get("disposition") or {}
        payloads[key] = {
            "l": normalized.get("left"),
            "x": normalized.get("right"),
            # Two sign conventions for the served delta coexist on main: this
            # emitter writes the documented right-minus-left dashboard delta,
            # while the populace-campaign artifacts (AL/MA/NC/SC/TN SNAP,
            # checked by the same CI step) serve the report's stored
            # `difference` (left-minus-right). Both are faithful projections
            # of the same (l, x) pair. The parity check therefore accepts a
            # served `d` equal to EITHER, so a DK PR neither re-emits SNAP
            # under a convention it does not own nor lets DK's fresh chunks
            # fail against the other. Unifying the convention repo-wide is a
            # tracked follow-up, not a side effect here.
            "d": normalized.get("difference"),
            "d_alt": dashboard_delta(
                normalized.get("left"), normalized.get("right")
            ),
            "e": disposition.get("disposition"),
        }
    return payloads, problems


def _served_mismatch_payloads(
    rows: list[dict],
) -> tuple[dict[tuple[str, str], dict], list[str]]:
    payloads: dict[tuple[str, str], dict] = {}
    problems: list[str] = []
    seen_case_ids: set[str] = set()
    for row in rows:
        case_id = row.get("id")
        if case_id is None:
            problems.append("served case row is missing id")
            continue
        case_key = str(case_id)
        if case_key in seen_case_ids:
            problems.append(f"served duplicate case id {case_key}")
        seen_case_ids.add(case_key)
        mismatches = row.get("m") or []
        if not isinstance(mismatches, list):
            problems.append(f"served case {case_key} has non-list m")
            continue
        for mismatch in mismatches:
            concept = mismatch.get("c")
            if concept is None:
                problems.append(
                    f"served mismatch for case {case_key} is missing concept"
                )
                continue
            key = (case_key, str(concept))
            if key in payloads:
                problems.append(f"served duplicate mismatch identity {key}")
                continue
            payloads[key] = {
                "l": mismatch.get("l"),
                "x": mismatch.get("x"),
                "d": mismatch.get("d"),
                "e": mismatch.get("e"),
            }
    return payloads, problems


def check_suite_artifacts(
    suite: str,
    dashboard_config: dict,
) -> tuple[list[str], dict[str, int]]:
    """Compare committed compact artifacts to the complete canonical report."""
    problems: list[str] = []
    basename = dashboard_config["basename"]
    report = dashboard_report(basename)
    if report is None:
        return [f"{suite}: canonical dashboard report is missing"], {}
    if not mismatches_complete(report):
        stored = len(report.get("mismatches") or [])
        declared = (report.get("summary") or {}).get("mismatch_count")
        return [
            f"{suite}: canonical mismatch list is incomplete "
            f"({stored}/{declared}); compact parity is uncheckable"
        ], {}

    out_dir = OUT_ROOT / suite
    index_path = out_dir / "index.json"
    if not index_path.exists():
        return [f"{suite}: case-artifact index.json is missing"], {}
    try:
        index = json.loads(index_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{suite}: cannot read case-artifact index.json: {exc}"], {}
    if not isinstance(index, dict):
        return [f"{suite}: case-artifact index is not a JSON object"], {}

    rows, load_problems = _load_served_rows(suite, index)
    problems.extend(load_problems)
    if index.get("suite") != suite:
        problems.append(
            f"{suite}: index suite is {index.get('suite')!r}, expected {suite!r}"
        )
    if index.get("count") != len(rows):
        problems.append(
            f"{suite}: index count {index.get('count')} != {len(rows)} served rows"
        )
    if index.get("engines") != report.get("engines"):
        problems.append(f"{suite}: index engines drift from canonical report")

    total_cases = report.get("case_count") or report.get("compared_tax_units")
    if index.get("total_cases") != total_cases:
        problems.append(
            f"{suite}: index total_cases {index.get('total_cases')} != "
            f"canonical {total_cases}"
        )

    canonical, canonical_problems = _canonical_mismatch_payloads(report)
    served, served_problems = _served_mismatch_payloads(rows)
    problems.extend(f"{suite}: {item}" for item in canonical_problems)
    problems.extend(f"{suite}: {item}" for item in served_problems)

    canonical_keys = set(canonical)
    served_keys = set(served)
    missing = sorted(canonical_keys - served_keys)
    obsolete = sorted(served_keys - canonical_keys)
    if missing:
        problems.append(
            f"{suite}: {len(missing)} canonical mismatch row(s) missing; "
            f"examples={missing[:5]}"
        )
    if obsolete:
        problems.append(
            f"{suite}: {len(obsolete)} obsolete served mismatch row(s); "
            f"examples={obsolete[:5]}"
        )

    shared = canonical_keys & served_keys
    wrong_annotations = sorted(
        key for key in shared if canonical[key]["e"] != served[key]["e"]
    )
    silent = [
        key
        for key in wrong_annotations
        if canonical[key]["e"] is None and served[key]["e"] is not None
    ]
    if wrong_annotations:
        problems.append(
            f"{suite}: {len(wrong_annotations)} served annotation(s) differ "
            f"from canonical ({len(silent)} silent classifications); "
            f"examples={wrong_annotations[:5]}"
        )
    def _delta_matches(key: tuple[str, str]) -> bool:
        served_d = served[key].get("d")
        return served_d == canonical[key]["d"] or served_d == canonical[key]["d_alt"]

    value_drift = sorted(
        key
        for key in shared
        if any(canonical[key][field] != served[key][field] for field in ("l", "x"))
        or not _delta_matches(key)
    )
    if value_drift:
        problems.append(
            f"{suite}: {len(value_drift)} served mismatch value row(s) drift; "
            f"examples={value_drift[:5]}"
        )

    concepts = sorted({key[1] for key in canonical})
    if index.get("mismatch_concepts") != concepts:
        problems.append(f"{suite}: index mismatch_concepts drift from canonical")
    unique_mismatch_cases = len({key[0] for key in canonical})
    if index.get("partial") == "mismatch-only":
        expected_rows = unique_mismatch_cases
    else:
        expected_rows = total_cases
    if index.get("count") != expected_rows:
        problems.append(
            f"{suite}: index count {index.get('count')} != expected "
            f"{expected_rows} for artifact mode"
        )

    return problems, {
        "cases": len(rows),
        "mismatches": len(canonical),
        "annotated": sum(payload["e"] is not None for payload in canonical.values()),
        "silent": len(silent),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Fail if committed chunks differ from complete canonical dashboard "
            "mismatch rows; does not read ignored reports/ or write files."
        ),
    )
    parser.add_argument("suite", nargs="*", help="Suite slug(s) to emit or check.")
    args = parser.parse_args()

    suites = dashboard_suites()
    if args.suite:
        wanted = args.suite
    elif args.check:
        wanted = sorted(suite for suite in suites if (OUT_ROOT / suite).exists())
    else:
        wanted = sorted(suites)

    if args.check:
        all_problems: list[str] = []
        checked = 0
        mismatch_rows = 0
        annotated_rows = 0
        for suite in wanted:
            if suite not in suites:
                all_problems.append(f"{suite}: unknown suite")
                continue
            problems, stats = check_suite_artifacts(suite, suites[suite])
            all_problems.extend(problems)
            if stats:
                checked += 1
                mismatch_rows += stats["mismatches"]
                annotated_rows += stats["annotated"]
        if all_problems:
            for problem in all_problems:
                print(f"case-artifacts FAILED: {problem}", file=sys.stderr)
            return 1
        print(
            f"case-artifacts OK: {checked} suites, {mismatch_rows} mismatch "
            f"rows, {annotated_rows} annotated, 0 silent classifications"
        )
        return 0

    for suite in wanted:
        if suite not in suites:
            print(f"skip {suite}: unknown suite")
            continue
        print(emit_suite(suite, suites[suite]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
