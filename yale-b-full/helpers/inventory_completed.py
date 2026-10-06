#!/usr/bin/env python3
"""Incremental, read-only diagnostic inventory of completed current-key shards.

Reuses the previous lane's measurement functions and the unchanged campaign's
selectors. This is not an official classification, and never runs classify.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import measure_shards as measurement


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(path):
    spec = importlib.util.spec_from_file_location("inventory_campaign", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_hashes(campaign, oracles, rulespec):
    paths = {
        "inventory_helper": Path(__file__).resolve(),
        "measurement_helper": Path(measurement.__file__).resolve(),
        "campaign": oracles / "scripts/us_tariff_schedule_campaign.py",
        "selected": campaign.SELECTED,
        "routing": campaign.ROUTING_ROWS,
        "routing_receipt": campaign.ROUTING_RECEIPT,
        "input_contract": campaign.INPUT_CONTRACT_RECEIPT,
        "dispositions": campaign.DISPOSITION_LEDGER,
        "preview": campaign.PREVIEW_DISPOSITION_LINE_SETS,
    }
    paths.update({"preview_producer:" + name: path for name, path in
                  campaign.PREVIEW_DISPOSITION_PRODUCER_SOURCES.items()})
    for stem in ("note16-232-steel", "note19-232-aluminum", "note20-china-301",
                 "note2aa-122-exemptions"):
        paths["incidence:" + stem] = campaign.INCIDENCE_ROOT / (stem + ".yaml")
    return {name: measurement.sha256(path) for name, path in sorted(paths.items())}


def shard_identity(shard):
    return {key: shard[key] for key in
            ("chapter", "key", "sha256", "cases", "engine_errors")}


def conservation(census, attributions):
    summary = census["summary"]
    require(summary["comparisons"] == summary["matches"] + summary["mismatches"],
            "comparisons do not conserve")
    require(summary["mismatches"] == sum(census["class_census"].values()) ==
            sum(census["attribution_census"].values()), "mismatch census does not conserve")
    for class_id, slots in census["class_per_slot"].items():
        require(sum(slots.values()) == census["class_census"][class_id],
                "class/slot census does not conserve: " + class_id)
    class_attributes = Counter()
    classes_by_slot = Counter()
    for class_id, units in census["class_census"].items():
        attr = attributions.get(class_id)
        require(attr is not None, "unknown class in census: " + class_id)
        class_attributes[attr] += units
        classes_by_slot.update(census["class_per_slot"].get(class_id, {}))
    require(class_attributes == Counter(census["attribution_census"]),
            "class attribution totals do not conserve")
    for slot, counts in census["per_slot"].items():
        require(counts.get("mismatch", 0) == counts.get("explained", 0) +
                counts.get("unexplained", 0) == classes_by_slot[slot],
                "per-slot mismatch totals do not conserve: " + slot)
    require(summary["matches"] == sum(item.get("match", 0) for item in census["per_slot"].values()),
            "match totals do not conserve")
    require(summary["unexplained"] == class_attributes["unexplained"],
            "unexplained totals do not conserve")
    require(summary["axiom_attributed_open"] == class_attributes["axiom-attributed-open"],
            "open totals do not conserve")
    return "PASS"


def compact_sample(sample):
    return {"case_id": sample["case_id"], "hts10": sample["hts10"],
            "origin": sample["iso2"], "date": sample["probe"],
            "axiom": sample["actual"], "yale": sample["expected"],
            "delta": sample["delta"], "flags": sample["flags"]}


def inventory(chapters, attributions):
    rows = []
    families = {}
    for census in chapters:
        chapter = census["chapter"]
        for class_id, slots in census["class_per_slot"].items():
            attr = attributions[class_id]
            for slot, units in slots.items():
                if not units:
                    continue
                samples = [compact_sample(sample)
                           for group in census["samples_by_class_slot_and_delta_sign"].values()
                           for sample in group
                           if sample["class"] == class_id and sample["slot"] == slot]
                row = {"chapter": chapter, "class": class_id, "slot": slot,
                       "attribution": attr, "mismatch_units": units,
                       "unexplained_units": units if attr == "unexplained" else 0,
                       "axiom_attributed_open_units": units if attr == "axiom-attributed-open" else 0,
                       "samples": samples}
                row["gap_units"] = row["unexplained_units"] + row["axiom_attributed_open_units"]
                rows.append(row)
                if not row["gap_units"]:
                    continue
                family = families.setdefault((class_id, slot), {
                    "class": class_id, "slot": slot, "attribution": attr,
                    "gap_units": 0, "unexplained_units": 0,
                    "axiom_attributed_open_units": 0, "per_chapter": {}, "samples": []})
                for field in ("gap_units", "unexplained_units", "axiom_attributed_open_units"):
                    family[field] += row[field]
                family["per_chapter"][chapter] = units
                # Retain each chapter's bounded examples: a dominant chapter
                # must not erase the examples of a smaller distinct mechanism.
                family["samples"].extend({"chapter": chapter, **sample} for sample in samples)
    rows.sort(key=lambda row: (-row["gap_units"], -row["mismatch_units"], row["chapter"], row["class"], row["slot"]))
    ranked = sorted(families.values(), key=lambda row: (-row["gap_units"], row["class"], row["slot"]))
    return rows, ranked


def write_markdown(path, receipt):
    totals = receipt["aggregate"]["summary"]
    lines = ["# Completed B chapter diagnostic inventory", "",
             "Diagnostic only; the official preview-population guard was not run.", "",
             f"Coverage: {len(receipt['completed_chapters'])}/{len(receipt['required_chapters'])} chapters. "
             f"Status: {receipt['status']}. Conservation: {receipt['conservation']}.", "",
             "Completed: " + ", ".join(receipt["completed_chapters"]) + ".", "",
             "| Comparisons | Matches | Mismatches | Unexplained units | Axiom-open units |",
             "|---:|---:|---:|---:|---:|",
             "| " + " | ".join(f"{totals.get(field, 0):,}" for field in
                                ("comparisons", "matches", "mismatches", "unexplained", "axiom_attributed_open")) + " |",
             "", "Gap units include both component and total comparison units; they are not unique transactions.", "",
             "| Chapter | Class | Slot | Unexplained units | Axiom-open units |",
             "|---|---|---|---:|---:|"]
    for row in receipt["per_chapter_class_slot"]:
        if row["gap_units"]:
            lines.append(f"| {row['chapter']} | {row['class']} | {row['slot']} | "
                         f"{row['unexplained_units']:,} | {row['axiom_attributed_open_units']:,} |")
    if not receipt["ranked_gap_families"]:
        lines.append("| — | No measured gaps in the completed coverage | — | 0 | 0 |")
    lines.extend(["", "The JSON retains every mismatch class/slot/chapter, attribution, samples, source hashes, "
                  "and per-chapter artifact hashes. A class/slot family groups observed counts; it does not by itself establish one legal cause.", ""])
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracles-root", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--engine-binary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chapters", default="all", help="Completed manifest chapters, or a comma-separated subset")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--verify-only", action="store_true", help="Verify retained censuses; do not measure missing chapters")
    args = parser.parse_args()
    require(args.samples >= 1, "samples must be positive")
    started = time.monotonic()
    oracles = args.oracles_root.resolve()
    rulespec = args.rulespec_root.resolve()
    os.environ["RULESPEC_US_CHECKOUT"] = str(rulespec)
    campaign = load_module(oracles / "scripts/us_tariff_schedule_campaign.py")
    manifest_path = (args.manifest or campaign.EVAL_MANIFEST).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest["schema"] == "axiom_oracles.us_tariff_schedule.eval_manifest.v1", "bad manifest schema")
    shards = {}
    for key, shard in manifest["shards"].items():
        require(key == shard["key"], "manifest key differs from shard key")
        require(shard["chapter"] not in shards, "duplicate chapter in evaluation manifest")
        shards[shard["chapter"]] = shard
    contract = json.loads(campaign.INPUT_CONTRACT_RECEIPT.read_text())
    required = sorted(item["chapter"] for item in contract["chapters"])
    selected = sorted(shards) if args.chapters == "all" else sorted(item.strip().zfill(2) for item in args.chapters.split(","))
    require(len(selected) == len(set(selected)), "duplicate requested chapter")
    require(set(selected) <= set(shards) <= set(required), "requested/manifest chapters are missing or undeclared")
    dependencies = source_hashes(campaign, oracles, rulespec)
    ledger = campaign.yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())
    require(ledger["suite"] == "us-tariff-schedule", "wrong disposition ledger")
    selectors = campaign.validate_dispositions(ledger["entries"], {})
    attributions = {entry["id"]: entry["attribution"] for entry in selectors}
    attributions.update({"__unexplained_component__": "unexplained", "__unexplained_total__": "unexplained",
                         "__unexplained_engine_error__": "unexplained", "__derived_total__": "derived"})
    routes = None
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    chapter_dir = output.parent / (output.stem + "-chapters")
    receipt = {"schema": "measurement.incremental_gap_inventory.v1", "diagnostic_only": True,
               "official_classification": False, "conformance_claim": False,
               "preview_selector_population_validation": "not performed; producer update required for official classify",
               "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": measurement.utc_now(),
               "source_hashes": dependencies, "manifest_path": str(manifest_path),
               "manifest_snapshot_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
               "required_chapters": required, "selected_chapters": selected,
               "manifest_chapters": sorted(shards), "completed_chapters": [],
               "pending_diagnostic_chapters": selected.copy(), "chapter_artifacts": {},
               "status": "running", "coverage": "partial", "conservation": "PASS"}
    completed = []

    def checkpoint():
        receipt["aggregate"] = measurement.aggregate(completed)
        rows, families = inventory(completed, attributions)
        receipt["per_chapter_class_slot"] = rows
        receipt["ranked_gap_families"] = families
        summary = receipt["aggregate"]["summary"]
        require(sum(row["unexplained_units"] for row in rows) == summary.get("unexplained", 0), "inventory unexplained conservation")
        require(sum(row["axiom_attributed_open_units"] for row in rows) == summary.get("axiom_attributed_open", 0), "inventory open conservation")
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        receipt["checkpoint_utc"] = measurement.utc_now()
        measurement.atomic_json(output, receipt)
        write_markdown(output.with_suffix(".md"), receipt)

    checkpoint()
    try:
        for chapter in selected:
            shard = shards[chapter]
            key = campaign._shard_key(chapter=chapter, rulespec_root=rulespec, engine_binary=args.engine_binary.resolve())
            require(key == shard["key"], "current campaign cache key does not match chapter " + chapter)
            require(measurement.sha256(shard["path"]) == shard["sha256"], "shard hash mismatch: " + chapter)
            fingerprint = {"sources": dependencies, "shard": shard_identity(shard), "samples": args.samples}
            artifact = chapter_dir / ("ch" + chapter + ".json")
            resumed = False
            if artifact.is_file():
                saved = json.loads(artifact.read_text())
                require(saved.get("schema") == "measurement.incremental_chapter_census.v1", "bad chapter artifact schema")
                require(saved["fingerprint"] == fingerprint, "chapter census fingerprint changed: " + chapter)
                census = saved["measurement"]
                require(saved["measurement_sha256"] == hashlib.sha256(json.dumps(census, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "chapter measurement hash mismatch")
                resumed = True
            elif args.verify_only:
                print(json.dumps({"chapter": chapter, "status": "no retained census; not measured"}), flush=True)
                continue
            else:
                if routes is None:
                    routes = campaign._routing_dispositions()
                census = measurement.measure(campaign, shard, selectors, routes, args.samples)
                conservation(census, attributions)
                saved = {"schema": "measurement.incremental_chapter_census.v1", "fingerprint": fingerprint,
                         "measurement_sha256": hashlib.sha256(json.dumps(census, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                         "measurement": census, "created_utc": measurement.utc_now(), "conservation": "PASS"}
                measurement.atomic_json(artifact, saved)
            require(shard_identity(census["shard"]) == shard_identity(shard), "census shard identity mismatch")
            require(census["chapter"] == chapter and census["cases"] == shard["cases"] and
                    census["verified_shard_sha256"] == shard["sha256"], "census chapter identity mismatch")
            conservation(census, attributions)
            completed.append(census)
            receipt["completed_chapters"].append(chapter)
            receipt["pending_diagnostic_chapters"].remove(chapter)
            receipt["chapter_artifacts"][chapter] = {"path": str(artifact), "sha256": measurement.sha256(artifact), "resumed": resumed}
            checkpoint()
            print(json.dumps({"chapter": chapter, "resumed": resumed, "conservation": "PASS", **census["summary"]}), flush=True)
        receipt["status"] = "verified_with_missing_censuses" if receipt["pending_diagnostic_chapters"] else "complete_for_selected_chapters"
        receipt["coverage"] = "full_schedule" if receipt["completed_chapters"] == required else "partial"
        require(source_hashes(campaign, oracles, rulespec) == dependencies,
                "diagnostic source inputs changed during census")
    except BaseException as exc:
        receipt["status"] = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed"
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        receipt["finished_utc"] = measurement.utc_now()
        checkpoint()


if __name__ == "__main__":
    main()
