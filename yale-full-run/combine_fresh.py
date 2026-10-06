#!/usr/bin/env python3
"""Combine disjoint fresh CH79 and bounded probes without claiming full coverage."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

from measure_shards import aggregate, atomic_json, sha256, utc_now
from pair_shards import pair_chapter
from run_targeted_probe import campaign_module

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--run-root", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
started = time.monotonic()
started_utc = utc_now()
root = a.run_root.resolve()
sources = {}
aggregates = {}
case_ids = {}
chapter79 = {}
origin_counts = {}
selection_path = root / "targeted-selection.json"
selection = json.loads(selection_path.read_text())

for variant in ("A", "B"):
    chapter_path = root / ("A-fresh-ch79-census-chapters/ch79.json" if variant == "A" else "B-ch79-census-chapters/ch79.json")
    chapter_top_path = root / ("A-fresh-ch79-census.json" if variant == "A" else "B-ch79-census.json")
    top = json.loads(chapter_top_path.read_text())
    if sha256(chapter_path) != top["chapter_artifacts"]["79"]["sha256"]:
        raise ValueError("CH79 census artifact SHA mismatch")
    chapter79[variant] = json.loads(chapter_path.read_text())
    manifest_path = root / f"targeted-{variant}/diagnostic-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema"] != "measurement.bounded_endpoint_eval_manifest.v1" or manifest["status"] != "complete":
        raise ValueError("bounded diagnostic incomplete")
    if manifest["selection_sha256"] != sha256(selection_path):
        raise ValueError("bounded selection SHA mismatch")
    chapters = [chapter79[variant]]
    census_paths = [chapter_path]
    for chapter in ("62", "84", "29", "94"):
        path = root / f"targeted-{variant}/diagnostic-ch{chapter}-census.json"
        if sha256(path) != manifest["chapter_diagnostics"][chapter]["sha256"]:
            raise ValueError("bounded chapter census SHA mismatch")
        chapters.append(json.loads(path.read_text()))
        census_paths.append(path)
    if len({chapter["chapter"] for chapter in chapters}) != len(chapters):
        raise ValueError("overlapping chapter populations")
    ids = set()
    origins = Counter()
    provenance = []
    for path, census in zip(census_paths, chapters, strict=True):
        shard = census["shard"]
        if sha256(shard["path"]) != shard["sha256"] or census["verified_shard_sha256"] != shard["sha256"]:
            raise ValueError("underlying fresh shard SHA mismatch")
        cases = 0
        with gzip.open(shard["path"], "rt") as source:
            for raw in source:
                record = json.loads(raw)
                if record["case_id"] in ids:
                    raise ValueError("duplicate case across combined cohorts")
                ids.add(record["case_id"])
                origins[record["iso2"]] += 1
                cases += 1
        if cases != census["cases"] or cases != shard["cases"]:
            raise ValueError("fresh shard case census mismatch")
        provenance.append({"chapter": census["chapter"], "coverage": "complete_chapter" if census["chapter"] == "79" else "bounded_stratified_sample",
                           "census_path": str(path), "census_sha256": sha256(path), "shard": shard})
    aggregates[variant] = aggregate(chapters)
    case_ids[variant] = ids
    origin_counts[variant] = dict(sorted(origins.items()))
    sources[variant] = {"chapter79_parent_census": {"path": str(chapter_top_path), "sha256": sha256(chapter_top_path), "inputs": top["hashes"]},
                        "bounded_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path), "inputs": manifest["inputs"]},
                        "cohorts": provenance}

if case_ids["A"] != case_ids["B"] or len(case_ids["A"]) != 10538:
    raise ValueError("combined fresh A/B case identities differ")

# Recompute the complete CH79 pair from fresh results. Also authenticate the
# earlier historical pairing's provenance without changing that old receipt.
campaign = campaign_module(root / "B/oracles")
fresh_pair = pair_chapter(campaign, chapter79["A"]["shard"], chapter79["B"]["shard"], 5)
fresh_pair["schema"] = "measurement.fresh_complete_chapter_pair.v1"
fresh_pair["diagnostic_only"] = True
fresh_pair["campaign_source_sha256"] = sha256(Path(campaign.__file__))
fresh_pair_path = root / "fresh-ch79-paired.json"
atomic_json(fresh_pair_path, fresh_pair)
reproduction_path = root / "A-ch79-cache-reproduction.json"
reproduction = json.loads(reproduction_path.read_text())
historical_sha = sha256(reproduction["historical"]["path"])
if historical_sha != reproduction["historical"]["sha256"] or historical_sha != chapter79["A"]["shard"]["sha256"]:
    raise ValueError("historical/fresh A79 byte identity failed")
historical_pair_path = root / "paired-ch79-historical-A-fresh-B.json"
historical_pair = json.loads(historical_pair_path.read_text())
if historical_pair["transitions"] != fresh_pair["transitions"]:
    raise ValueError("historical and recomputed fresh79 pairing transitions differ")
bounded_pair_path = root / "targeted-A-B-paired.json"
bounded_pair = json.loads(bounded_pair_path.read_text())
if bounded_pair["selection_sha256"] != sha256(selection_path):
    raise ValueError("bounded pair selection drift")
transitions = Counter(fresh_pair["transitions"])
transitions.update(bounded_pair["transitions"])
per_slot = defaultdict(Counter)
for pair in (fresh_pair, bounded_pair):
    for slot, counts in pair["per_slot"].items():
        per_slot[slot].update(counts)

expected = {
    "A": {"comparisons": 118194, "matches": 112030, "mismatches": 6164, "unexplained": 3394, "axiom_attributed_open": 0},
    "B": {"comparisons": 118194, "matches": 114532, "mismatches": 3662, "unexplained": 168, "axiom_attributed_open": 83},
}
for variant, values in expected.items():
    if any(aggregates[variant]["summary"][key] != value for key, value in values.items()):
        raise ValueError("combined census differs from expected arithmetic")
if sum(transitions.values()) != 118194 or transitions["mismatch_to_match"] != 2660 or transitions["match_to_mismatch"] != 158:
    raise ValueError("combined paired population does not conserve")

receipt = {
    "schema": "measurement.fresh_combined_partial_census.v1", "diagnostic_only": True,
    "official_classification_receipt": False, "full_schedule": False, "representative_population_claim": False,
    "coverage": {"complete_chapters": ["79"], "bounded_chapters": ["62", "84", "29", "94"],
                 "bounded_chapter94_exact_hts10": "9403999020", "cases": 10538, "comparisons": 118194,
                 "complete_chapter_cases": 8100, "bounded_cases": 2438, "cohorts_disjoint": True},
    "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": started_utc, "finished_utc": utc_now(),
    "elapsed_seconds": round(time.monotonic() - started, 3), "helper_source_sha256": sha256(__file__),
    "aggregate_helper_sha256": sha256(root / "measure_shards.py"),
    "selection": {"path": str(selection_path), "sha256": sha256(selection_path), "criteria": selection["criteria"]},
    "sources": sources, "variant_census": aggregates, "origin_case_counts": origin_counts,
    "same_case_identity_population": True,
    "case_id_population_sha256": hashlib.sha256(("\n".join(sorted(case_ids["A"])) + "\n").encode()).hexdigest(),
    "paired": {"transitions": transitions, "per_slot": per_slot,
               "fresh_ch79_pair": {"path": str(fresh_pair_path), "sha256": sha256(fresh_pair_path)},
               "fresh_bounded_pair": {"path": str(bounded_pair_path), "sha256": sha256(bounded_pair_path)}},
    "historical_A79_authentication": {"fresh_gzip_sha256": chapter79["A"]["shard"]["sha256"],
                                     "historical_gzip_sha256": historical_sha, "byte_identity": True,
                                     "reproduction_receipt_sha256": sha256(reproduction_path),
                                     "historical_pair_receipt_sha256": sha256(historical_pair_path),
                                     "direct_fresh_pair_recomputation_matches_historical_pair": True},
    "validation": "PASS: artifact/shard hashes, disjoint cohorts, equal A/B identities, census and paired conservation",
}
atomic_json(a.output, receipt)
print(json.dumps({"cases": receipt["coverage"]["cases"], "A": aggregates["A"]["summary"], "B": aggregates["B"]["summary"],
                  "paired_transitions": transitions, "validation": receipt["validation"], "elapsed_seconds": receipt["elapsed_seconds"]}, sort_keys=True), flush=True)
