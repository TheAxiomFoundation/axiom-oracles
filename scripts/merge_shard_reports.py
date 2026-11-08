#!/usr/bin/env python
"""Merge sharded comparison reports into one full-population report.

Big states OOM a single compare process on constrained machines; the
``--case-shard K/N`` option runs disjoint case subsets in fresh processes.
This merges the shard reports back into one ``axiom.comparison_report.v2``:
counters and weights sum, row lists concatenate, aggregates re-sum by
concept, and per-shard identity fields must agree. ``engine_identity``
binaries (the TAXSIM executables each shard ran) merge by identity with
their row counts summed; equivalent printed build stamps share one entry
and retain the first shard's observed spelling. Shards that ran different
binaries keep one entry per binary. The provenance copy
(``provenance.oracle.taxsim_binaries``) merges the same way, even when no
shard carries ``engine_identity``; every shard must record it or none, a
shard with rows must not record an empty list, the two copies must agree,
and ``provenance.oracle.policyengine_taxsim`` and
``provenance.oracle.taxsim_pin_profile`` must agree across shards.

Usage (the script imports axiom_oracles, so run it in the project
environment):
    uv run scripts/merge_shard_reports.py OUT.json SHARD0.json SHARD1.json [...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from axiom_oracles.adapters.taxsim.pins import normalize_build_stamp

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
    engine_identity = _merge_engine_identity(shards)
    _require_binaries_for_rows(
        shards,
        [((s.get("engine_identity") or {}).get("taxsim")) for s in shards],
        "binaries",
        "engine_identity.taxsim",
    )
    provenance_binaries = _merge_provenance_taxsim(shards)
    taxsim = (engine_identity or {}).get("taxsim")
    # Each shard's two copies must describe the same binaries and rows; a
    # merged comparison alone lets two shards' opposite disagreements cancel.
    for index, shard in enumerate(shards):
        shard_taxsim = (shard.get("engine_identity") or {}).get("taxsim") or {}
        shard_oracle = (shard.get("provenance") or {}).get("oracle") or {}
        if "binaries" in shard_taxsim and "taxsim_binaries" in shard_oracle:
            if _canonical_binaries(shard_taxsim["binaries"]) != _canonical_binaries(
                shard_oracle["taxsim_binaries"]
            ):
                raise SystemExit(
                    f"TAXSIM identity disagrees between engine_identity and "
                    f"provenance in shard {index}"
                )
    # The per-shard check above implies this one whenever every shard
    # carries both lists. It stays for a shard whose engine_identity.taxsim
    # block omits `binaries` while its provenance lists them: that shard skips
    # the per-shard comparison, and only the merged lists show the gap.
    if (
        taxsim
        and provenance_binaries is not None
        and _canonical_binaries(provenance_binaries)
        != _canonical_binaries(taxsim.get("binaries") or [])
    ):
        raise SystemExit(
            "TAXSIM identity disagrees between engine_identity and provenance"
        )
    if engine_identity is None:
        merged.pop("engine_identity", None)
    else:
        merged["engine_identity"] = engine_identity
    binaries = taxsim.get("binaries") if taxsim else provenance_binaries
    if binaries is not None and isinstance(merged.get("provenance"), dict):
        provenance = dict(merged["provenance"])
        oracle = dict(provenance.get("oracle") or {})
        oracle["taxsim_binaries"] = [dict(item) for item in binaries]
        if taxsim and taxsim.get("pin_profile"):
            oracle["taxsim_pin_profile"] = taxsim["pin_profile"]
        provenance["oracle"] = oracle
        merged["provenance"] = provenance
    return merged


def _shard_has_rows(shard: dict) -> bool:
    summary = shard.get("summary") or {}
    return bool(
        any(shard.get(key) for key in ("case_count", "cases", "mismatches", "errors"))
        or any(summary.get(key) for key in (*_SUM_SUMMARY, "engine_error_count"))
    )


def _require_binaries_for_rows(
    shards: list[dict], blocks: list, key: str, path: str
) -> None:
    """A shard that ran rows must name the binaries that produced them."""
    for shard, block in zip(shards, blocks, strict=True):
        if isinstance(block, dict) and key in block:
            if not isinstance(block[key], list):
                raise SystemExit(f"invalid TAXSIM identity {path}.{key}")
            if not block[key] and _shard_has_rows(shard):
                raise SystemExit(
                    f"shards have incomplete TAXSIM identity coverage at {path}"
                )


def _merge_provenance_taxsim(shards: list[dict]) -> list[dict] | None:
    """Merge every shard's ``provenance.oracle.taxsim_binaries``.

    ``None`` when no shard records one. The wrapper version and pin profile
    must agree across shards, and either every shard records binaries or
    none does, so the first shard's identity cannot stand in for the rows
    of a later shard that ran something else.
    """
    oracles = [
        ((shard.get("provenance") or {}).get("oracle") or {}) for shard in shards
    ]
    for field in ("policyengine_taxsim", "taxsim_pin_profile"):
        values = [oracle.get(field) for oracle in oracles]
        if any(value != values[0] for value in values[1:]):
            raise SystemExit(
                f"shards disagree on provenance.oracle.{field} identity"
            )
    present = ["taxsim_binaries" in oracle for oracle in oracles]
    if not any(present):
        return None
    if not all(present):
        raise SystemExit(
            "shards have incomplete TAXSIM identity coverage at provenance.oracle"
        )
    _require_binaries_for_rows(
        shards, oracles, "taxsim_binaries", "provenance.oracle"
    )
    return _merge_binaries(
        [oracle["taxsim_binaries"] for oracle in oracles], "taxsim"
    )


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
        merged[engine] = dict(header)
        # An engine identity without a binary inventory keeps its shape.
        if any("binaries" in part for part in parts):
            merged[engine]["binaries"] = _merge_binaries(
                [part.get("binaries") or [] for part in parts], engine
            )
    return merged


def _canonical_binaries(records: list[dict]) -> list[str]:
    """Order-free form of one binary list, equivalent stamps merged."""
    return sorted(
        json.dumps(record, sort_keys=True)
        for record in _merge_binaries([records], "taxsim")
    )


def _merge_binaries(lists: list[list[dict]], engine: str) -> list[dict]:
    """Merge binary records by identity, summing their rows."""
    binaries: dict[str, dict] = {}
    for records in lists:
        for binary in records:
            # Rows, and rows per pin-profile scope, are counts to sum.
            identity = {
                k: v for k, v in binary.items() if k not in ("rows", "scopes")
            }
            if engine == "taxsim" and identity.get("build_observed") is not None:
                identity["build_observed"] = normalize_build_stamp(
                    identity["build_observed"]
                )
            key = json.dumps(
                identity,
                sort_keys=True,
            )
            rows = int(binary.get("rows") or 0)
            if key in binaries:
                binaries[key]["rows"] += rows
            else:
                binaries[key] = {**binary, "rows": rows}
                binaries[key].pop("scopes", None)
            if "scopes" in binary:
                scopes = binaries[key].setdefault("scopes", {})
                for scope, count in binary["scopes"].items():
                    scopes[scope] = scopes.get(scope, 0) + int(count)
    return list(binaries.values())


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
