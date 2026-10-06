#!/usr/bin/env python3
"""Read-only census of verified eval shards with current campaign functions.

This is a diagnostic, never an official classification receipt. In particular,
it does not assert the campaign's full-population preview-selector guards.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sign(value):
    return "none" if value is None else "positive" if value > 0 else "negative" if value < 0 else "zero"


def measure(campaign, shard, selectors, routes, sample_limit):
    started = time.monotonic()
    path = Path(shard["path"])
    actual_hash = sha256(path)
    if actual_hash != shard["sha256"]:
        raise ValueError(f"shard SHA-256 mismatch: {path}")
    counts = defaultdict(Counter)
    classes = Counter()
    class_slots = defaultdict(Counter)
    attributions = Counter()
    delta_signs = defaultdict(Counter)
    samples = defaultdict(list)
    compositions = Counter()
    unexplained_components = Counter()
    unexplained_total_causes = Counter()
    attribution = {entry["id"]: entry["attribution"] for entry in selectors}
    # The official classifier also classifies each distinct signature once.
    # Bound the memoization to one chapter so it cannot grow across the schedule.
    signature_classes = {}
    cases = 0
    canonical_digest = hashlib.sha256()
    with gzip.open(path, "rt") as source:
        for raw in source:
            record = json.loads(raw)
            cases += 1
            canonical_digest.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            component_classes = []
            component_unexplained_slots = []
            for row in campaign.compare_record(record):
                slot = row["slot"]
                counts[slot]["match" if row["match"] else "mismatch"] += 1
                if row["match"]:
                    continue
                signature = None
                if slot == "engine_error":
                    bucket = "__unexplained_engine_error__"
                    attr = "unexplained"
                elif slot == "total":
                    if not component_classes:
                        raise ValueError(f"total mismatch lacks mismatching components: {record['case_id']}")
                    if None in component_classes:
                        bucket = "__unexplained_total__"
                        attr = "unexplained"
                        unexplained_total_causes[" + ".join(sorted(set(component_unexplained_slots)))] += 1
                    else:
                        bucket = "__derived_total__"
                        attr = "derived"
                        compositions[" + ".join(sorted(set(component_classes)))] += 1
                    component_classes = []
                    component_unexplained_slots = []
                else:
                    signature = campaign.mismatch_signature(row)
                    if signature not in signature_classes:
                        unit = campaign.mismatch_unit(row, routes)
                        signature_classes[signature] = campaign.matching_class_id(signature, unit, selectors)
                    class_id = signature_classes[signature]
                    component_classes.append(class_id)
                    bucket = class_id or "__unexplained_component__"
                    attr = attribution.get(class_id, "unexplained")
                    if class_id is None:
                        unexplained_components[slot] += 1
                        component_unexplained_slots.append(slot)
                classes[bucket] += 1
                class_slots[bucket][slot] += 1
                attributions[attr] += 1
                counts[slot]["unexplained" if attr == "unexplained" else "explained"] += 1
                delta_sign = sign(row.get("delta"))
                delta_signs[slot][delta_sign] += 1
                group = "|".join((bucket, slot, delta_sign))
                if len(samples[group]) < sample_limit:
                    sample = {key: record.get(key) for key in ("case_id", "hts10", "hts_line", "iso2", "probe", "revision", "interval", "flags")}
                    sample.update({key: row.get(key) for key in ("slot", "actual", "expected", "delta", "error")})
                    sample.update({"class": bucket, "attribution": attr, "signature": signature})
                    samples[group].append(sample)
    if cases != shard["cases"]:
        raise ValueError(f"shard case count mismatch: expected {shard['cases']}, read {cases}")
    matches = sum(counter["match"] for counter in counts.values())
    mismatches = sum(counter["mismatch"] for counter in counts.values())
    if mismatches != sum(classes.values()):
        raise ValueError("classification conservation failure")
    return {
        "chapter": shard["chapter"], "cases": cases, "shard": shard,
        "verified_shard_sha256": actual_hash,
        "canonical_record_sha256": canonical_digest.hexdigest(),
        "observed_component_signature_count": len(signature_classes),
        "summary": {"comparisons": matches + mismatches, "matches": matches,
                    "mismatches": mismatches, "unexplained": attributions["unexplained"],
                    "engine_errors": classes["__unexplained_engine_error__"],
                    "derived_total_units": classes["__derived_total__"],
                    "unexplained_total_units": classes["__unexplained_total__"],
                    "axiom_attributed_open": attributions["axiom-attributed-open"]},
        "class_census": dict(sorted(classes.items())),
        "class_per_slot": {key: dict(value) for key, value in sorted(class_slots.items())},
        "attribution_census": dict(sorted(attributions.items())),
        "per_slot": {key: dict(value) for key, value in sorted(counts.items())},
        "mismatch_delta_signs_per_slot": {key: dict(value) for key, value in sorted(delta_signs.items())},
        "unexplained_components_per_slot": dict(sorted(unexplained_components.items())),
        "unexplained_total_component_compositions": dict(sorted(unexplained_total_causes.items())),
        "derived_total_compositions": dict(sorted(compositions.items())),
        "samples_by_class_slot_and_delta_sign": dict(sorted(samples.items())),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def aggregate(chapters):
    flat_fields = ("summary", "class_census", "attribution_census", "unexplained_components_per_slot",
                   "unexplained_total_component_compositions", "derived_total_compositions")
    nested_fields = ("per_slot", "class_per_slot", "mismatch_delta_signs_per_slot")
    result = {field: Counter() for field in flat_fields}
    result.update({field: defaultdict(Counter) for field in nested_fields})
    result["cases"] = 0
    for chapter in chapters:
        result["cases"] += chapter["cases"]
        for field in flat_fields:
            result[field].update(chapter[field])
        for field in nested_fields:
            for key, values in chapter[field].items():
                result[field][key].update(values)
    summary = result["summary"]
    result["arithmetic_closure_condition"] = summary["unexplained"] == 0 and summary["axiom_attributed_open"] == 0
    result["would_be_conformant"] = None
    result["would_be_conformant_reason"] = "Diagnostic only; official coverage, input, projection and preview-selector population guards must pass."
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracles-root", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--chapters", required=True, help="Comma-separated chapters, or all")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    started = time.monotonic()
    started_utc = utc_now()
    os.environ["RULESPEC_US_CHECKOUT"] = str(args.rulespec_root.resolve())
    script = args.oracles_root.resolve() / "scripts/us_tariff_schedule_campaign.py"
    spec = importlib.util.spec_from_file_location("measured_campaign", script)
    campaign = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(campaign)
    manifest = json.loads(args.manifest.read_text())
    shards = {}
    for shard in manifest["shards"].values():
        chapter = shard["chapter"]
        if chapter in shards:
            raise ValueError(f"multiple shards for chapter {chapter}")
        shards[chapter] = shard
    selected = sorted(shards) if args.chapters == "all" else [item.strip().zfill(2) for item in args.chapters.split(",")]
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("chapters must be nonempty and unique")
    missing = set(selected) - set(shards)
    if missing:
        raise ValueError(f"manifest missing requested chapters: {sorted(missing)}")
    routes = campaign._routing_dispositions()
    ledger = campaign.yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())
    if ledger.get("suite") != "us-tariff-schedule":
        raise ValueError("wrong disposition suite")
    selectors = campaign.validate_dispositions(ledger["entries"], {})
    hashes = {"measurement_source_sha256": sha256(__file__),
              "campaign_source_sha256": sha256(script),
              "disposition_ledger_sha256": sha256(campaign.DISPOSITION_LEDGER),
              "routing_rows_sha256": sha256(campaign.ROUTING_ROWS),
              "manifest_sha256": sha256(args.manifest)}
    required_chapters = None
    if campaign.INPUT_CONTRACT_RECEIPT.is_file():
        contract = json.loads(campaign.INPUT_CONTRACT_RECEIPT.read_text())
        required_chapters = sorted(item["chapter"] for item in contract.get("chapters", []))
        hashes["input_contract_sha256"] = sha256(campaign.INPUT_CONTRACT_RECEIPT)
    receipt = {
        "schema": "measurement.current_campaign_shard_census.v1",
        "diagnostic_only": True, "official_classification": False,
        "preview_selector_population_validation": "not performed; full official classify required",
        "conformance_claim": False,
        "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": started_utc,
        "oracles_root": str(args.oracles_root.resolve()),
        "rulespec_root": str(args.rulespec_root.resolve()),
        "manifest_path": str(args.manifest.resolve()), "hashes": hashes,
        "selected_chapters": selected, "manifest_chapters": sorted(shards),
        "input_contract_required_chapters": required_chapters,
        "completed_chapters": [], "chapter_artifacts": {}, "status": "running",
        "coverage": "partial", "aggregate": aggregate([]),
    }
    atomic_json(args.output, receipt)
    completed = []
    try:
        for chapter in selected:
            measurement = measure(campaign, shards[chapter], selectors, routes, args.samples)
            chapter_path = args.output.parent / (args.output.stem + "-chapters") / f"ch{chapter}.json"
            atomic_json(chapter_path, measurement)
            completed.append(measurement)
            receipt["completed_chapters"].append(chapter)
            receipt["chapter_artifacts"][chapter] = {"path": str(chapter_path.resolve()), "sha256": sha256(chapter_path)}
            receipt["aggregate"] = aggregate(completed)
            receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
            receipt["last_checkpoint_utc"] = utc_now()
            atomic_json(args.output, receipt)
            print(json.dumps({"chapter": chapter, "cases": measurement["cases"], **measurement["summary"], "elapsed_seconds": measurement["elapsed_seconds"]}), flush=True)
        receipt["status"] = "complete"
        receipt["coverage"] = ("full_schedule" if required_chapters and set(selected) == set(required_chapters)
                               else "all_manifest_shards" if set(selected) == set(shards) else "partial")
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
