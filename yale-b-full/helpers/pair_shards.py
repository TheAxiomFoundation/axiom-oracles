#!/usr/bin/env python3
"""Pair verified historical/fresh eval shards using the current comparator.

Requires identical case ordering and identities; fails closed on divergence.
This is a historical-cache diagnostic, not current-pipeline baseline evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import time

from measure_shards import atomic_json, sha256, sign, utc_now


def pair_chapter(campaign, baseline, candidate, limit):
    started = time.monotonic()
    for shard in (baseline, candidate):
        if sha256(shard["path"]) != shard["sha256"]:
            raise ValueError(f"shard SHA-256 mismatch: {shard['path']}")
    changes = Counter()
    per_slot = defaultdict(Counter)
    signs = defaultdict(Counter)
    samples = defaultdict(list)
    cases = 0
    with gzip.open(baseline["path"], "rt") as a, gzip.open(candidate["path"], "rt") as b:
        for raw_a, raw_b in itertools.zip_longest(a, b):
            if raw_a is None or raw_b is None:
                raise ValueError("unequal case population")
            record_a, record_b = json.loads(raw_a), json.loads(raw_b)
            if record_a["case_id"] != record_b["case_id"]:
                raise ValueError(f"case identity/order mismatch at ordinal {cases}: {record_a['case_id']}, {record_b['case_id']}")
            for field in ("hts10", "hts_line", "iso2", "probe", "expected", "plan"):
                if record_a[field] != record_b[field]:
                    raise ValueError(f"case comparability field {field} differs: {record_a['case_id']}")
            cases += 1
            rows_a = {row["slot"]: row for row in campaign.compare_record(record_a)}
            rows_b = {row["slot"]: row for row in campaign.compare_record(record_b)}
            for slot in sorted(set(rows_a) | set(rows_b)):
                row_a, row_b = rows_a.get(slot), rows_b.get(slot)
                if row_a is None:
                    transition = "candidate_only_slot"
                elif row_b is None:
                    transition = "baseline_only_slot"
                elif row_a["match"] and not row_b["match"]:
                    transition = "match_to_mismatch"
                elif not row_a["match"] and row_b["match"]:
                    transition = "mismatch_to_match"
                elif row_a.get("actual") == row_b.get("actual"):
                    transition = "retained_match" if row_a["match"] else "retained_mismatch_same_actual"
                else:
                    transition = "retained_match_changed_actual" if row_a["match"] else "retained_mismatch_changed_actual"
                changes[transition] += 1
                per_slot[slot][transition] += 1
                direction = "_to_".join(sign(row.get("delta")) if row else "missing" for row in (row_a, row_b))
                signs[slot + "|" + transition][direction] += 1
                sample_key = "|".join((slot, transition, direction))
                if transition != "retained_match" and len(samples[sample_key]) < limit:
                    samples[sample_key].append({
                        "case_id": record_a["case_id"], "hts10": record_a["hts10"],
                        "iso2": record_a["iso2"], "probe": record_a["probe"], "slot": slot,
                        "baseline": {key: row_a.get(key) for key in ("actual", "expected", "delta", "match")} if row_a else None,
                        "candidate": {key: row_b.get(key) for key in ("actual", "expected", "delta", "match")} if row_b else None,
                        "changed_flags": {key: [record_a["flags"].get(key), record_b["flags"].get(key)]
                                          for key in set(record_a["flags"]) | set(record_b["flags"])
                                          if record_a["flags"].get(key) != record_b["flags"].get(key)},
                    })
    if cases != baseline["cases"] or cases != candidate["cases"]:
        raise ValueError("manifest case count mismatch")
    return {"chapter": baseline["chapter"], "cases": cases,
            "baseline_shard": baseline, "candidate_shard": candidate,
            "shard_hash_verification": "PASS", "case_comparability": "PASS",
            "transitions": changes, "per_slot": per_slot, "delta_sign_transitions": signs,
            "samples_by_slot_transition_and_sign": samples,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracles-root", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--chapters", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    started = time.monotonic()
    started_utc = utc_now()
    os.environ["RULESPEC_US_CHECKOUT"] = str(args.rulespec_root.resolve())
    script = args.oracles_root.resolve() / "scripts/us_tariff_schedule_campaign.py"
    spec = importlib.util.spec_from_file_location("paired_campaign", script)
    campaign = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(campaign)
    a = {shard["chapter"]: shard for shard in json.loads(args.baseline_manifest.read_text())["shards"].values()}
    b = {shard["chapter"]: shard for shard in json.loads(args.candidate_manifest.read_text())["shards"].values()}
    selected = sorted(set(a) & set(b)) if args.chapters == "all-common" else [item.strip().zfill(2) for item in args.chapters.split(",")]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("chapters must be nonempty and unique")
    if set(selected) - set(a) or set(selected) - set(b):
        raise ValueError("requested chapter missing from manifest")
    receipt = {
        "schema": "measurement.historical_baseline_candidate_pair.v1",
        "diagnostic_only": True, "conformance_claim": False,
        "baseline_provenance": "Historical cached engine results; this does not establish acceptance by current pipeline cache-key rules.",
        "candidate_provenance": "Hash-verified manifest shards; engine freshness is established separately by campaign logs.",
        "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": started_utc,
        "hashes": {"measurement_source_sha256": sha256(__file__),
                   "campaign_source_sha256": sha256(script),
                   "baseline_manifest_sha256": sha256(args.baseline_manifest),
                   "candidate_manifest_sha256": sha256(args.candidate_manifest)},
        "baseline_manifest": str(args.baseline_manifest.resolve()),
        "candidate_manifest": str(args.candidate_manifest.resolve()),
        "selected_chapters": selected, "completed_chapters": [], "chapter_artifacts": {},
        "status": "running", "cases": 0, "transitions": Counter(), "per_slot": defaultdict(Counter),
    }
    atomic_json(args.output, receipt)
    try:
        for chapter in selected:
            measurement = pair_chapter(campaign, a[chapter], b[chapter], args.samples)
            chapter_path = args.output.parent / (args.output.stem + "-chapters") / f"ch{chapter}.json"
            atomic_json(chapter_path, measurement)
            receipt["completed_chapters"].append(chapter)
            receipt["chapter_artifacts"][chapter] = {"path": str(chapter_path.resolve()), "sha256": sha256(chapter_path)}
            receipt["cases"] += measurement["cases"]
            receipt["transitions"].update(measurement["transitions"])
            for slot, values in measurement["per_slot"].items():
                receipt["per_slot"][slot].update(values)
            receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
            atomic_json(args.output, receipt)
            print(json.dumps({"chapter": chapter, "cases": measurement["cases"], "transitions": measurement["transitions"], "elapsed_seconds": measurement["elapsed_seconds"]}), flush=True)
        receipt["status"] = "complete"
    except BaseException as exc:
        receipt["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        receipt["finished_utc"] = utc_now()
        atomic_json(args.output, receipt)


if __name__ == "__main__":
    main()
