#!/usr/bin/env python3
"""Reverify prior partial B evidence; no engine, classify, or source mutation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prior = args.prior_run.resolve()
    oracles = prior / "B/oracles"
    rulespec = prior / "B/rulespec-us"
    os.environ["RULESPEC_US_CHECKOUT"] = str(rulespec)
    sys.path.insert(0, str(oracles))

    # Execute the previous source-join verifier with its sole output redirected
    # into this workspace. It only reads the old B sources and partial shards.
    old_script = prior / "audit_measured_gaps.py"
    original = old_script.read_text()
    old_output = 'output = RUN / "measured-gap-evidence.json"'
    assert original.count(old_output) == 1
    redirected = original.replace(old_output, "output = Path(" + repr(str(args.output.resolve())) + ")")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scope = {"__name__": "prior_source_audit_reverification", "__file__": str(old_script)}
    exec(compile(redirected, str(old_script), "exec"), scope)
    result = json.loads(args.output.read_text())
    result["scope"] = "Prior partial probes only, independently reread and reclassified; not new campaign coverage."
    result["verification_script"] = {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)}
    result["prior_verifier_sha256"] = sha(old_script)
    result["argv"] = sys.argv
    result["cwd"] = str(Path.cwd())
    retained_pages = []
    for number, raw in enumerate(scope["notes_raw"].splitlines(), 1):
        if number in (246, 248, 251, 266, 550, 553, 554, 555, 563, 576):
            row = json.loads(raw)
            retained_pages.append({"physical_jsonl_line": number,
                                   "citation_path": row.get("citation_path"),
                                   "body": row.get("body")})
    result["corpus"]["directly_reverified_pages"] = retained_pages

    campaign_path = oracles / "scripts/us_tariff_schedule_campaign.py"
    campaign = module("gap_audit_current_campaign", campaign_path)
    helper = module("gap_audit_prior_census", prior / "measure_shards.py")
    selectors = campaign.validate_dispositions(
        campaign.yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())["entries"], {}
    )
    routes = campaign._routing_dispositions()
    manifest = json.loads((prior / "targeted-B/diagnostic-MANIFEST.json").read_text())
    verified = {}
    for shard in manifest["shards"].values():
        chapter = shard["chapter"]
        observed = helper.measure(campaign, shard, selectors, routes, 3)
        old = json.loads((prior / f"targeted-B/diagnostic-ch{chapter}-census.json").read_text())
        fields = ("summary", "class_census", "class_per_slot", "attribution_census", "per_slot")
        for field in fields:
            assert observed[field] == old[field], (chapter, field)
        verified[chapter] = {field: observed[field] for field in fields}
        verified[chapter]["verified_shard_sha256"] = observed["verified_shard_sha256"]
        verified[chapter]["cases"] = observed["cases"]
    result["reproduced_partial_current_selector_census"] = verified

    paths = [
        campaign_path, campaign.DISPOSITION_LEDGER,
        oracles / "reference/us-tariff-schedule/output-semantics-ruling.md",
        prior / "measure_shards.py",
        rulespec / "tools/b16_entry_flags.py",
        rulespec / "tools/generate_incidence_tables.py",
        rulespec / "tools/generate_schedule_compositions.py",
        rulespec / "us/policies/cbp/us-tariff-schedule/generated/ch62/ch62.yaml",
        rulespec / "us/policies/cbp/us-tariff-schedule/generated/ch84/ch84.yaml",
        rulespec / "us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml",
        rulespec / "us/policies/usitc/us-tariff-duty/overlays/section-301/forced-labor-costa-rica-9903-05-33.yaml",
        rulespec / "us/policies/cbp/us-tariff-duty/composition.yaml",
    ]
    result["audited_source_hashes"] = {str(path): sha(path) for path in paths}
    result["rulespec_head"] = subprocess.run(
        ["git", "-C", str(rulespec), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert result["rulespec_head"] == "c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf"
    result["verification"] = "PASS"
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "verification": "PASS", "scope": "prior partial probes",
        "chapters": sorted(verified), "cases": sum(row["cases"] for row in verified.values()),
        "unexplained": sum(row["summary"]["unexplained"] for row in verified.values()),
        "axiom_attributed_open": sum(row["summary"]["axiom_attributed_open"] for row in verified.values()),
        "output": str(args.output.resolve()),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
