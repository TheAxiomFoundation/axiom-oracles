#!/usr/bin/env python3
"""Pair two fresh bounded diagnostics without historical-cache provenance claims."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import time

from measure_shards import atomic_json, sha256, utc_now
from pair_shards import pair_chapter
from run_targeted_probe import campaign_module

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--oracles-root", type=Path, required=True)
p.add_argument("--baseline-manifest", type=Path, required=True)
p.add_argument("--candidate-manifest", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
started = time.monotonic()
started_utc = utc_now()
baseline = json.loads(a.baseline_manifest.read_text())
candidate = json.loads(a.candidate_manifest.read_text())
for manifest in (baseline, candidate):
    if manifest["schema"] != "measurement.bounded_endpoint_eval_manifest.v1" or manifest["status"] != "complete":
        raise ValueError("expected a complete fresh bounded diagnostic manifest")
if baseline["selection_sha256"] != candidate["selection_sha256"] or set(baseline["shards"]) != set(candidate["shards"]):
    raise ValueError("A/B bounded selection or completed chapters differ")
campaign = campaign_module(a.oracles_root)
receipt = {"schema": "measurement.fresh_bounded_endpoint_pair.v1", "diagnostic_only": True,
           "representative_full_schedule_claim": False, "official_conformance_claim": False,
           "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": started_utc,
           "source_sha256": sha256(__file__), "campaign_source_sha256": sha256(Path(campaign.__file__)),
           "baseline_manifest_sha256": sha256(a.baseline_manifest), "candidate_manifest_sha256": sha256(a.candidate_manifest),
           "selection_sha256": baseline["selection_sha256"], "cases": 0,
           "transitions": Counter(), "per_slot": defaultdict(Counter), "chapters": {}}
for chapter in baseline["shards"]:
    paired = pair_chapter(campaign, baseline["shards"][chapter], candidate["shards"][chapter], 5)
    receipt["chapters"][chapter] = paired
    receipt["cases"] += paired["cases"]
    receipt["transitions"].update(paired["transitions"])
    for slot, values in paired["per_slot"].items():
        receipt["per_slot"][slot].update(values)
    atomic_json(a.output, receipt)
receipt["finished_utc"] = utc_now()
receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
atomic_json(a.output, receipt)
print(json.dumps({"cases": receipt["cases"], "transitions": receipt["transitions"],
                  "per_slot": receipt["per_slot"], "elapsed_seconds": receipt["elapsed_seconds"]}), flush=True)
