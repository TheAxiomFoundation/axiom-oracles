#!/usr/bin/env python3
"""Read one campaign shard with the unchanged campaign comparator/selectors.

This is a partial diagnostic; it does not relax the full campaign gates or
claim a certificate. All cache bodies are opened read-only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracles-root", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    os.environ["RULESPEC_US_CHECKOUT"] = str(args.rulespec_root.resolve())
    script = args.oracles_root / "scripts/us_tariff_schedule_campaign.py"
    spec = importlib.util.spec_from_file_location("measured_campaign", script)
    campaign = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(campaign)
    manifest_path = args.manifest or args.oracles_root / "reference/us-tariff-schedule/eval/MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    selected = [s for s in manifest["shards"].values() if s["chapter"] == args.chapter]
    if len(selected) != 1:
        raise ValueError(f"expected one {args.chapter} shard; found {len(selected)}")
    shard = selected[0]
    shard_path = Path(shard["path"])
    actual_sha = campaign._sha256(shard_path)
    if actual_sha != shard["sha256"]:
        raise ValueError("committed shard SHA-256 mismatch")
    routes = campaign._routing_dispositions()
    entries = campaign.yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())["entries"]
    campaign.validate_dispositions(entries, {})
    counts = defaultdict(Counter)
    census = Counter()
    samples = defaultdict(list)
    errors = cases = derived = unexplained = 0
    record_digest = hashlib.sha256()
    attribution = {e["id"]: e["attribution"] for e in entries}
    with gzip.open(shard_path, "rt") as source:
        for raw in source:
            record = json.loads(raw)
            cases += 1
            record_digest.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            component_classes = []
            for row in campaign.compare_record(record):
                counts[row["slot"]]["match" if row["match"] else "mismatch"] += 1
                if row["match"]:
                    continue
                if row["slot"] == "engine_error":
                    errors += 1
                    unexplained += 1
                    continue
                if row["slot"] == "total":
                    if not component_classes or None in component_classes:
                        unexplained += 1
                    else:
                        derived += 1
                    continue
                signature = campaign.mismatch_signature(row)
                unit = campaign.mismatch_unit(row, routes)
                class_id = campaign.matching_class_id(signature, unit, entries)
                component_classes.append(class_id)
                census[class_id or "__unexplained__"] += 1
                if class_id is None:
                    unexplained += 1
                if len(samples[class_id or "__unexplained__"]) < 5:
                    samples[class_id or "__unexplained__"].append({
                        "hts10": record["hts10"], "iso2": record["iso2"],
                        "date": record["probe"], "slot": row["slot"],
                        "actual": row["actual"], "expected": row["expected"],
                        "delta": row["delta"], "signature": signature,
                    })
    if cases != shard["cases"]:
        raise ValueError("shard case count mismatch")
    matches = sum(c["match"] for c in counts.values())
    mismatches = sum(c["mismatch"] for c in counts.values())
    if mismatches != sum(v for k, v in census.items() if k != "__unexplained__") + derived + unexplained:
        raise ValueError("classification conservation failure")
    receipt = {
        "schema": "measurement.partial_chapter_census.v1",
        "partial_diagnostic_only": True,
        "chapter": args.chapter, "cases": cases,
        "campaign_source_sha256": campaign._sha256(script),
        "manifest_path": str(manifest_path), "shard": shard,
        "verified_shard_sha256": actual_sha,
        "canonical_record_sha256": record_digest.hexdigest(),
        "summary": {"comparisons": matches + mismatches, "matches": matches,
                    "mismatches": mismatches, "unexplained": unexplained,
                    "engine_errors": errors, "derived_total_units": derived},
        "class_census": dict(sorted(census.items())),
        "axiom_attributed_open": sum(v for k, v in census.items() if attribution.get(k) == "axiom-attributed-open"),
        "per_slot": {k: dict(v) for k, v in sorted(counts.items())},
        "samples": dict(sorted(samples.items())),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: receipt[k] for k in ("chapter", "cases", "summary", "class_census", "axiom_attributed_open", "elapsed_seconds")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
