#!/usr/bin/env python
"""Merge sharded comparison reports into one full-population report.

Big states OOM a single compare process on constrained machines; the
``--case-shard K/N`` option runs disjoint case subsets in fresh processes.
This merges the shard reports back into one ``axiom.comparison_report.v2``:
counters and weights sum, row lists concatenate, aggregates re-sum by
concept, and per-shard identity fields must agree. TAXSIM binary inventories
are unioned by digest, scope, and platform with summed row counts; their pin
profiles must agree and every nonempty shard must record its identity.

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
    "comparison_count",
    "error_count",
)
_SUM_AGGREGATE = (
    "comparison_count",
    "comparison_weight",
    "match_count",
    "match_weight",
    "mismatch_count",
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


def _merge_taxsim_identity(
    identities: list[dict], *, populated: list[bool],
    binaries_key: str, profile_key: str, path: str,
) -> dict | None:
    """Merge C1 identity records without losing a later shard's executable.

    Both the CLI's engine_identity and run_comparison's provenance copy use
    the same binary records. Require complete coverage within either shape;
    keeping the first shard's identity could authorize unrelated rows.
    """
    present = [binaries_key in identity or profile_key in identity for identity in identities]
    if not any(present):
        return None
    if not all(present):
        raise SystemExit(f"shards have incomplete TAXSIM identity coverage at {path}")
    profile = identities[0].get(profile_key)
    if not isinstance(profile, str) or not profile:
        raise SystemExit(f"invalid TAXSIM identity {path}.{profile_key}")
    binaries: dict[tuple[str, ...], dict] = {}
    for identity, has_rows in zip(identities, populated, strict=True):
        if identity.get(profile_key) != profile:
            raise SystemExit(f"shards disagree on {path}.{profile_key}")
        records = identity.get(binaries_key)
        if not isinstance(records, list):
            raise SystemExit(f"invalid TAXSIM identity {path}.{binaries_key}")
        if not records and has_rows:
            raise SystemExit(f"shards have incomplete TAXSIM identity coverage at {path}")
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("sha256"), str):
                raise SystemExit(f"invalid TAXSIM binary identity at {path}")
            rows = record.get("rows")
            if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
                raise SystemExit(f"invalid TAXSIM binary rows at {path}")
            # Canonical JSON also permits structured scopes supplied by a
            # pin profile without assuming a particular scope vocabulary.
            key = tuple(
                json.dumps(record.get(field), sort_keys=True)
                for field in ("sha256", "scope", "platform")
            )
            if key in binaries:
                binaries[key]["rows"] += rows
            else:
                binaries[key] = dict(record)
    return {
        **identities[0],
        profile_key: profile,
        binaries_key: [binaries[key] for key in sorted(binaries)],
    }


def _merge_taxsim_identities(shards: list[dict], merged: dict) -> None:
    engine_identities = [(shard.get("engine_identity") or {}) for shard in shards]
    oracles = [
        (shard.get("provenance") or {}).get("oracle") or {}
        for shard in shards
    ]
    populated = [
        any(shard.get(key) for key in ("case_count", "cases", "mismatches", "errors"))
        or any(
            (shard.get("summary") or {}).get(key)
            for key in (*_SUM_SUMMARY, "engine_error_count")
        )
        for shard in shards
    ]
    taxsim = _merge_taxsim_identity(
        [identity.get("taxsim") or {} for identity in engine_identities],
        populated=populated,
        binaries_key="binaries", profile_key="pin_profile", path="engine_identity.taxsim",
    )
    oracle = _merge_taxsim_identity(
        oracles, populated=populated,
        binaries_key="taxsim_binaries", profile_key="taxsim_pin_profile",
        path="provenance.oracle",
    )
    versions = [oracle.get("policyengine_taxsim") for oracle in oracles]
    if any(version != versions[0] for version in versions[1:]):
        raise SystemExit("shards disagree on provenance.oracle.policyengine_taxsim identity")
    if taxsim is not None and oracle is not None:
        if (
            taxsim["pin_profile"] != oracle["taxsim_pin_profile"]
            or taxsim["binaries"] != oracle["taxsim_binaries"]
        ):
            raise SystemExit("TAXSIM identity disagrees between engine_identity and provenance")
    if taxsim is not None:
        merged["engine_identity"] = {**engine_identities[0], "taxsim": taxsim}
    if oracle is not None:
        merged["provenance"] = {**merged.get("provenance", {}), "oracle": oracle}


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
    _merge_taxsim_identities(shards, merged)
    merged["case_count"] = sum(int(s.get("case_count") or 0) for s in shards)
    for key in ("cases", "mismatches", "errors"):
        merged[key] = [row for shard in shards for row in shard.get(key) or []]

    summary = dict(first.get("summary") or {})
    for key in _SUM_SUMMARY:
        summary[key] = sum(
            int((s.get("summary") or {}).get(key) or 0) for s in shards
        )
    # Present only when some shard had engine-error rows (the accumulator
    # omits it at zero), so error-free merges keep their summary shape.
    engine_errors = sum(
        int((s.get("summary") or {}).get("engine_error_count") or 0)
        for s in shards
    )
    summary.pop("engine_error_count", None)
    if engine_errors:
        summary["engine_error_count"] = engine_errors
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
