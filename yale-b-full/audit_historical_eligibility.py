#!/usr/bin/env python3
"""Audit retained baseline cache eligibility without decompressing/replaying shards."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-run", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    prior = args.prior_run.resolve()
    candidate = args.candidate.resolve()
    baseline = prior / "A"
    campaign_path = candidate / "oracles/scripts/us_tariff_schedule_campaign.py"
    os.environ["RULESPEC_US_CHECKOUT"] = str(candidate / "rulespec-us")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("eligibility_campaign", campaign_path)
    campaign = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(campaign)

    a_reference = baseline / "oracles/reference/us-tariff-schedule"
    b_reference = candidate / "oracles/reference/us-tariff-schedule"
    archived_manifest_path = baseline / "committed/MANIFEST.json"
    fresh_manifest_path = a_reference / "eval/MANIFEST.json"
    b_manifest_path = b_reference / "eval/MANIFEST.json"
    archived_manifest = json.loads(archived_manifest_path.read_text())
    fresh_manifest = json.loads(fresh_manifest_path.read_text())
    b_manifest_bytes = b_manifest_path.read_bytes()
    b_manifest = json.loads(b_manifest_bytes)
    prior_historical_path = prior / "baseline-historical-cache-audit.json"
    prior_historical = json.loads(prior_historical_path.read_text())
    a_receipt = json.loads((a_reference / "declared-input-contract-receipt.json").read_text())
    common = {
        "selected_sha256": digest(a_reference / "selected-intervals.csv.gz"),
        "routing_sha256": digest(a_reference / "disposition-routing.csv.gz"),
        "engine_sha256": digest(args.engine),
        "outputs": campaign.OUTPUT_NAMES,
    }
    receipts = {
        "retained_fresh_A": digest(a_reference / "declared-input-contract-receipt.json"),
        "archived_main": digest(baseline / "committed/declared-input-contract-receipt.json"),
        "historical_pre_510": prior_historical["historical_input_contract_sha256"],
        "retained_B": digest(b_reference / "declared-input-contract-receipt.json"),
    }
    artifact_inputs = {
        "campaign": {"path": str(campaign_path), "sha256": digest(campaign_path)},
        "baseline_campaign": {"path": str(baseline / "oracles/scripts/us_tariff_schedule_campaign.py"),
                              "sha256": digest(baseline / "oracles/scripts/us_tariff_schedule_campaign.py")},
        "historical_manifest": {"path": str(archived_manifest_path), "sha256": digest(archived_manifest_path)},
        "retained_fresh_A_manifest": {"path": str(fresh_manifest_path), "sha256": digest(fresh_manifest_path)},
        "candidate_manifest_snapshot": {"path": str(b_manifest_path),
                                        "sha256": hashlib.sha256(b_manifest_bytes).hexdigest()},
        "prior_historical_receipt_digest_evidence": {"path": str(prior_historical_path),
                                                   "sha256": digest(prior_historical_path)},
    }
    assert artifact_inputs["campaign"]["sha256"] == artifact_inputs["baseline_campaign"]["sha256"]
    assert common["selected_sha256"] == digest(b_reference / "selected-intervals.csv.gz")
    assert common["routing_sha256"] == digest(b_reference / "disposition-routing.csv.gz")
    assert a_receipt["entry_flag_tool_sha256"] == digest(baseline / "rulespec-us/tools/b16_entry_flags.py")

    def key(chapter: str, receipt: str) -> str:
        ingredients = {**common, "chapter": chapter,
                       "module_sha256": digest(campaign._module_path(baseline / "rulespec-us", chapter)),
                       "input_contract_sha256": receipt}
        return hashlib.sha256(campaign._render(ingredients).encode()).hexdigest()

    checks = []
    # Cache files are hashed, never decompressed or fed into compare_record.
    for dictionary_key, shard in sorted(archived_manifest["shards"].items(), key=lambda item: item[1]["chapter"]):
        chapter = shard["chapter"]
        assert dictionary_key == shard["key"]
        path = Path(shard["path"])
        exists = path.is_file()
        verified = exists and digest(path) == shard["sha256"]
        keys = {name: key(chapter, receipt) for name, receipt in receipts.items()}
        checks.append({
            "chapter": chapter, "historical_key": dictionary_key,
            "cases": shard["cases"], "path": str(path), "sha256": shard["sha256"],
            "exists": exists, "sha256_verified": verified,
            "compressed_bytes": path.stat().st_size if exists else 0,
            "computed_keys": keys,
            "key_matches": {name: value == dictionary_key for name, value in keys.items()},
            "eligible_under_retained_A": verified and keys["retained_fresh_A"] == dictionary_key,
        })

    fresh_checks = []
    for dictionary_key, shard in sorted(fresh_manifest["shards"].items(), key=lambda item: item[1]["chapter"]):
        assert dictionary_key == shard["key"]
        path = Path(shard["path"])
        expected_key = key(shard["chapter"], receipts["retained_fresh_A"])
        verified = path.is_file() and digest(path) == shard["sha256"]
        historical = next(item for item in checks if item["chapter"] == shard["chapter"])
        fresh_checks.append({
            **shard, "computed_key": expected_key,
            "sha256_verified": verified,
            "eligible_under_retained_A": verified and dictionary_key == expected_key,
            "same_compressed_bytes_as_historical": verified and historical["sha256_verified"]
                and shard["sha256"] == historical["sha256"],
        })

    # Check the optimized ingredient computation against the actual helper once.
    original_receipt = campaign.INPUT_CONTRACT_RECEIPT
    campaign.INPUT_CONTRACT_RECEIPT = a_reference / "declared-input-contract-receipt.json"
    helper_key = campaign._shard_key(chapter="79", rulespec_root=baseline / "rulespec-us", engine_binary=args.engine)
    assert helper_key == key("79", receipts["retained_fresh_A"])
    campaign.INPUT_CONTRACT_RECEIPT = original_receipt

    pair_path = prior / "fresh-ch79-paired.json"
    pair = json.loads(pair_path.read_text())
    fresh_79 = next(item for item in fresh_checks if item["chapter"] == "79")
    candidate_79 = next(item for item in b_manifest["shards"].values() if item["chapter"] == "79")
    candidate_79_key = campaign._shard_key(chapter="79", rulespec_root=candidate / "rulespec-us", engine_binary=args.engine)
    pair_is_bound = (
        pair["campaign_source_sha256"] == digest(campaign_path)
        and pair["baseline_shard"]["key"] == fresh_79["key"]
        and pair["baseline_shard"]["sha256"] == fresh_79["sha256"]
        and pair["candidate_shard"]["key"] == candidate_79["key"] == candidate_79_key
        and pair["candidate_shard"]["sha256"] == candidate_79["sha256"]
        and digest(Path(candidate_79["path"])) == candidate_79["sha256"]
        and fresh_79["eligible_under_retained_A"]
    )
    assert pair_is_bound
    result = {
        "schema": "measurement.historical_cache_eligibility.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "argv": sys.argv, "cwd": str(Path.cwd()), "audit_source_sha256": digest(Path(__file__)),
        "method": "Exact current campaign cache ingredients and render; all historical compressed bodies hashed only; no decompression, evaluation, census, or pairing replay.",
        "inputs": artifact_inputs, "common_key_ingredients": common, "receipt_sha256": receipts,
        "historical_receipt_digest_provenance": "Prior lane baseline-historical-cache-audit.json; no historical receipt installed.",
        "same_campaign_source_A_and_B": True, "same_selected_and_routing_A_and_B": True,
        "optimized_key_matches_official_helper_ch79": True,
        "historical_chapters": len(checks),
        "historical_hash_verified": sum(item["sha256_verified"] for item in checks),
        "historical_compressed_bytes": sum(item["compressed_bytes"] for item in checks),
        "historical_key_matches_by_receipt": {name: sum(item["key_matches"][name] for item in checks) for name in receipts},
        "eligible_historical_chapters_under_retained_A": [item["chapter"] for item in checks if item["eligible_under_retained_A"]],
        "eligible_fresh_A_chapters": [item["chapter"] for item in fresh_checks if item["eligible_under_retained_A"]],
        "prior_ch79_pair_evidence": {"path": str(pair_path), "sha256": digest(pair_path),
                                   "bound_to_current_sources_and_retained_accepted_shards": pair_is_bound,
                                   "cases": pair["cases"], "comparison_units": sum(pair["transitions"].values()),
                                   "match_to_mismatch": pair["transitions"].get("match_to_mismatch", 0),
                                   "mismatch_to_match": pair["transitions"].get("mismatch_to_match", 0),
                                   "fresh_baseline_byte_identical_to_historical": fresh_79["same_compressed_bytes_as_historical"],
                                   "measurement_origin": "Prior lane measurement; hashes verified here, pairing not rerun."},
        "historical_checks": checks, "fresh_A_checks": fresh_checks,
        "elapsed_seconds": round(time.monotonic() - start, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({name: result[name] for name in (
        "historical_chapters", "historical_hash_verified", "historical_compressed_bytes",
        "historical_key_matches_by_receipt", "eligible_historical_chapters_under_retained_A",
        "eligible_fresh_A_chapters", "prior_ch79_pair_evidence", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
