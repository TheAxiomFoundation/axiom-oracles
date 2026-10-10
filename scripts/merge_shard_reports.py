#!/usr/bin/env python
"""Merge sharded comparison reports into one full-population report.

Big states OOM a single compare process on constrained machines; the
``--case-shard K/N`` option runs disjoint case subsets in fresh processes.
This merges the shard reports back into one ``axiom.comparison_report.v2``:
counters and weights sum, row lists concatenate, aggregates re-sum by
concept, and per-shard identity fields must agree. ``engine_identity``
binaries (the TAXSIM executables each shard ran) merge by identity with
their row counts summed; shards that ran different binaries keep one entry
per binary.

Usage:
    merge_shard_reports.py OUT.json SHARD0.json SHARD1.json [...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

_SUM_SUMMARY = (
    "match_count",
    "mismatch_count",
    "uncompared_mismatches",
    "comparison_count",
    "error_count",
)
_SUM_AGGREGATE = (
    "comparison_count",
    "comparison_weight",
    "match_count",
    "match_weight",
    "mismatch_count",
    "uncompared_mismatches",
    "mismatch_weight",
    "missing_left_count",
    "missing_right_count",
)


def _merge_count_rows(rows_lists: list[list[dict]]) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    for rows in rows_lists:
        for row in rows or []:
            totals[str(row.get("value"))] += int(row.get("count") or 0)
    return [
        {"value": value, "count": count}
        for value, count in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def _merge_count_objects(count_objects: list[dict[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for counts in count_objects:
        for value, count in counts.items():
            totals[str(value)] += int(count or 0)
    return dict(sorted(totals.items()))


def merge(shards: list[dict]) -> dict:
    first = shards[0]
    for key in ("schema_version", "suite", "population", "engines", "locales"):
        for shard in shards[1:]:
            if shard.get(key) != first.get(key):
                raise SystemExit(
                    f"shards disagree on {key}: "
                    f"{first.get(key)!r} vs {shard.get(key)!r}"
                )

    merged = dict(first)
    merged["case_count"] = sum(int(s.get("case_count") or 0) for s in shards)
    for key in ("cases", "mismatches", "errors"):
        merged[key] = [row for shard in shards for row in shard.get(key) or []]

    summary = dict(first.get("summary") or {})
    for key in _SUM_SUMMARY:
        summary[key] = sum(
            int((s.get("summary") or {}).get(key) or 0) for s in shards
        )
    for key in (
        "mismatches_by_concept",
        "mismatches_by_kind",
        "mismatches_by_scenario",
    ):
        summary[key] = _merge_count_rows(
            [(s.get("summary") or {}).get(key) or [] for s in shards]
        )
    summary["errors_by_engine"] = _merge_count_objects(
        [
            (s.get("summary") or {}).get("errors_by_engine") or {}
            for s in shards
        ]
    )
    weighted_lists = [
        (s.get("summary") or {}).get("weighted") for s in shards
    ]
    if all(isinstance(w, dict) for w in weighted_lists):
        total = sum(float(w.get("comparison_weight") or 0) for w in weighted_lists)
        match = sum(float(w.get("match_weight") or 0) for w in weighted_lists)
        mismatch = sum(
            float(w.get("mismatch_weight") or 0) for w in weighted_lists
        )
        summary["weighted"] = {
            "comparison_weight": total,
            "match_weight": match,
            "mismatch_weight": mismatch,
            "match_rate": (match / total) if total else None,
        }
    merged["summary"] = summary

    buckets: dict[str, dict] = {}
    for shard in shards:
        for aggregate in shard.get("aggregates") or []:
            concept = aggregate.get("concept")
            bucket = buckets.get(concept)
            if bucket is None:
                buckets[concept] = dict(aggregate)
                continue
            for key in _SUM_AGGREGATE:
                if key in aggregate or key in bucket:
                    bucket[key] = (bucket.get(key) or 0) + (
                        aggregate.get(key) or 0
                    )
    merged["aggregates"] = list(buckets.values())
    engine_identity = _merge_engine_identity(shards)
    if engine_identity is None:
        merged.pop("engine_identity", None)
    else:
        merged["engine_identity"] = engine_identity
    return merged


def _merge_engine_identity(shards: list[dict]) -> dict | None:
    blocks = [shard.get("engine_identity") for shard in shards]
    if not any(blocks):
        return None
    if not all(blocks):
        raise SystemExit(
            "shards disagree on engine_identity: some record the binaries "
            "they ran and some do not"
        )
    merged: dict = {}
    for engine in sorted({key for block in blocks for key in block}):
        parts = [block.get(engine) for block in blocks]
        if not all(parts):
            raise SystemExit(f"shards disagree on engine_identity.{engine}")
        header = {k: v for k, v in parts[0].items() if k != "binaries"}
        for part in parts[1:]:
            other = {k: v for k, v in part.items() if k != "binaries"}
            if other != header:
                raise SystemExit(
                    f"shards disagree on engine_identity.{engine}: "
                    f"{header!r} vs {other!r}"
                )
        binaries: dict[str, dict] = {}
        for part in parts:
            for binary in part.get("binaries") or []:
                key = json.dumps(
                    {k: v for k, v in binary.items() if k != "rows"},
                    sort_keys=True,
                )
                if key in binaries:
                    binaries[key]["rows"] += int(binary.get("rows") or 0)
                else:
                    binaries[key] = {**binary, "rows": int(binary.get("rows") or 0)}
        merged[engine] = {**header, "binaries": list(binaries.values())}
    return merged


def main() -> int:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    shards = [json.loads(Path(p).read_text()) for p in sys.argv[2:]]
    merged = merge(shards)
    out.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    print(
        f"merged {len(shards)} shards -> {out.name}: "
        f"{merged['case_count']} cases, "
        f"{merged['summary']['mismatch_count']} mismatches"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
