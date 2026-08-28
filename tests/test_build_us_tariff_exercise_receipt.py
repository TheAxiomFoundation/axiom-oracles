from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_us_tariff_exercise_receipt.py"
)


def _load_producer():
    spec = importlib.util.spec_from_file_location("tariff_exercise_receipt", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _fixture(tmp_path: Path):
    producer = _load_producer()
    repo = tmp_path / "repo"
    campaign_path = repo / producer.CAMPAIGN_REL
    campaign_path.parent.mkdir(parents=True, exist_ok=True)
    campaign_path.write_text(
        "NEUTRAL_BOOLEAN_INPUTS = ('neutral_fact',)\n"
        "PROBE_BOOLEAN_INPUTS = ('probe_fact',)\n"
        "def _probe_boolean_inputs(probe):\n"
        "    return {'probe_fact': probe == '2026-02-24'}\n"
    )

    contract_path = repo / "reference/us-tariff-schedule/input-contract.json"
    feed = [
        "country_of_origin",
        "flag_a",
        "hts_line",
        "hts_number",
        "neutral_fact",
        "probe_fact",
    ]
    contract = {
        "schema": "fixture.input-contract.v1",
        "emitted_entry_flags": ["flag_a", "flag_dropped"],
        "expected_dropped_entry_flags": ["flag_dropped"],
        "neutral_boolean_inputs": ["neutral_fact"],
        "probe_boolean_inputs": {"probe_fact": {"derivation": "fixture"}},
        "chapters": [{"chapter": "01", "case_feed_inputs": feed}],
    }
    _write_json(contract_path, contract)
    contract_ref = producer._file_receipt(contract_path, repo_root=repo) | {
        "schema": contract["schema"]
    }
    campaign_ref = producer._file_receipt(campaign_path, repo_root=repo)
    run_identity = {
        "input_contract": contract_ref,
        "campaign_evaluator": {"campaign": campaign_ref},
    }
    run_identity_sha = _canonical_sha256(run_identity)

    shard_path = tmp_path / "shard.jsonl.gz"
    row = {
        "chapter": "01",
        "engine_errors": [],
        "flags": {"flag_a": True},
        "hts10": "0101210010",
        "hts_line": "01012100",
        "iso2": "CA",
        "probe": "2026-02-24",
        "origin_regime": "0001",
    }
    with gzip.open(shard_path, "wt") as target:
        target.write(json.dumps(row, sort_keys=True) + "\n")
    generation_id = "1" * 32
    shard_key = "2" * 64
    shard = {
        "key": shard_key,
        "chapter": "01",
        "generation_id": generation_id,
        "run_identity_sha256": run_identity_sha,
        "path": str(shard_path),
        "sha256": _sha256(shard_path),
        "cases": 1,
        "engine_errors": 0,
    }
    evaluation_manifest = {
        "schema": producer.MANIFEST_SCHEMA,
        "generation_id": generation_id,
        "run_identity": run_identity,
        "run_identity_sha256": run_identity_sha,
        "shards": {shard_key: shard},
    }

    comparison_artifact_path = tmp_path / "comparison.jsonl.gz"
    with gzip.open(comparison_artifact_path, "wt") as target:
        target.write("{}\n")
    comparison_artifact = producer._file_receipt(
        comparison_artifact_path, repo_root=repo
    )
    comparison_path = repo / producer.COMPARISON_REL
    comparison = {
        "schema": producer.COMPARISON_SCHEMA,
        "generation_id": generation_id,
        "run_identity_sha256": run_identity_sha,
        "evaluation_manifest_sha256": _canonical_sha256(evaluation_manifest),
        "comparison_artifact": comparison_artifact,
        "engine_errors": 0,
    }
    _write_json(comparison_path, comparison)
    manifest = evaluation_manifest | {
        "comparison_artifact": comparison_artifact,
        "comparison_receipt": producer._file_receipt(
            comparison_path, repo_root=repo
        ),
    }
    _write_json(repo / producer.MANIFEST_REL, manifest)
    _write_json(
        repo / producer.REPORT_REL,
        {"suite": producer.SUITE, "summary": {"engine_errors": 0}},
    )
    return producer, repo, shard_path


def test_build_receipt_scans_bound_shard_and_derives_every_feed_field(
    tmp_path: Path,
) -> None:
    producer, repo, _shard = _fixture(tmp_path)

    receipt = producer.build_receipt(
        repo_root=repo,
        expected_shard_count=1,
        campaign=producer._load_campaign(repo),
    )

    assert receipt["cases"] == 1
    assert set(receipt["evidence_fields"]) == {
        "hts_number",
        "hts_line",
        "country_of_origin",
        "entry_date",
        "origin_regime",
        "flag_a",
        "neutral_fact",
        "probe_fact",
    }
    assert all(
        row == {"distinct": 1, "state": "constant"}
        for row in receipt["evidence_fields"].values()
    )
    assert [row["path"] for row in receipt["evidence_artifacts"]] == [
        str(producer.MANIFEST_REL),
        str(producer.COMPARISON_REL),
        str(producer.REPORT_REL),
    ]


def test_build_receipt_rejects_shard_hash_drift(tmp_path: Path) -> None:
    producer, repo, shard = _fixture(tmp_path)
    with gzip.open(shard, "at") as target:
        target.write("{}\n")

    with pytest.raises(ValueError, match="shard body is absent or stale"):
        producer.build_receipt(
            repo_root=repo,
            expected_shard_count=1,
            campaign=producer._load_campaign(repo),
        )

