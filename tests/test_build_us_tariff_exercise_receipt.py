from __future__ import annotations

import gzip
import hashlib
import importlib.util
import inspect
import json
import os
import stat
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


def _fixture(tmp_path: Path, *, chapter_count: int = 1, rows_per_shard: int = 1):
    producer = _load_producer()
    repo = tmp_path / "repo"
    campaign_path = repo / producer.CAMPAIGN_REL
    campaign_path.parent.mkdir(parents=True, exist_ok=True)
    campaign_path.write_text(
        "import hashlib, json\n"
        "NEUTRAL_BOOLEAN_INPUTS = ('neutral_fact',)\n"
        "PROBE_BOOLEAN_INPUTS = ('probe_fact',)\n"
        "def _probe_boolean_inputs(probe):\n"
        "    return {'probe_fact': probe == '2026-02-24'}\n"
        "def _canonical_sha256(value):\n"
        "    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()\n"
        "def _current_shard_keys(run_identity, generation_id):\n"
        "    run_sha = _canonical_sha256(run_identity)\n"
        "    return {chapter: _canonical_sha256({'chapter': chapter, 'chapter_identity': identity, "
        "'generation_id': generation_id, 'run_identity_sha256': run_sha}) "
        "for chapter, identity in run_identity['chapters'].items()}\n"
    )

    contract_path = repo / producer.INPUT_CONTRACT_REL
    feed = [
        "country_of_origin",
        "flag_a",
        "hts_line",
        "hts_number",
        "neutral_fact",
        "probe_fact",
        *sorted(producer.ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS),
    ]
    contract = {
        "schema": producer.INPUT_CONTRACT_SCHEMA,
        "emitted_entry_flags": [
            "flag_a",
            "flag_dropped",
            *sorted(producer.ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS),
        ],
        "expected_dropped_entry_flags": ["flag_dropped"],
        "neutral_boolean_inputs": ["neutral_fact"],
        "neutral_boolean_value": False,
        "probe_boolean_inputs": {"probe_fact": {"derivation": "fixture"}},
        "reference_assumptions": {
            "fixture_assumption": {
                "campaign_binding": {"input": "flag_a", "value": True}
            }
        },
        "chapters": [
            {"chapter": f"{index + 1:02d}", "case_feed_inputs": feed}
            for index in range(chapter_count)
        ],
    }
    _write_json(contract_path, contract)
    contract_ref = producer._file_receipt(contract_path, repo_root=repo) | {
        "schema": contract["schema"]
    }
    campaign_ref = producer._file_receipt(campaign_path, repo_root=repo)
    chapter_identities = {
        f"{index + 1:02d}": {"fixture": index + 1} for index in range(chapter_count)
    }
    run_identity = {
        "input_contract": contract_ref,
        "campaign_evaluator": {"campaign": campaign_ref},
        "chapters": chapter_identities,
    }
    run_identity_sha = _canonical_sha256(run_identity)

    shard_path = tmp_path / "shard.jsonl.gz"
    row = {
        "chapter": "01",
        "engine_errors": [],
        "flags": {
            "flag_a": True,
            **{
                name: False for name in producer.ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS
            },
        },
        "hts10": "0101210010",
        "hts_line": "01012100",
        "iso2": "CA",
        "probe": "2026-02-24",
        "origin_regime": "0001",
    }
    generation_id = "1" * 32
    shards = {}
    for index in range(chapter_count):
        path = shard_path if index == 0 else tmp_path / f"shard-{index + 1}.jsonl.gz"
        record = row | {"chapter": f"{index + 1:02d}"}
        with gzip.open(path, "wt") as target:
            target.write((json.dumps(record, sort_keys=True) + "\n") * rows_per_shard)
        chapter = record["chapter"]
        shard_key = _canonical_sha256(
            {
                "chapter": chapter,
                "chapter_identity": chapter_identities[chapter],
                "generation_id": generation_id,
                "run_identity_sha256": run_identity_sha,
            }
        )
        shards[shard_key] = {
            "key": shard_key,
            "chapter": record["chapter"],
            "generation_id": generation_id,
            "run_identity_sha256": run_identity_sha,
            "path": str(path),
            "sha256": _sha256(path),
            "cases": rows_per_shard,
            "engine_errors": 0,
        }
    evaluation_manifest = {
        "schema": producer.MANIFEST_SCHEMA,
        "generation_id": generation_id,
        "run_identity": run_identity,
        "run_identity_sha256": run_identity_sha,
        "shards": shards,
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
        "per_slot": {"section_338": {"match": chapter_count * rows_per_shard}},
    }
    _write_json(comparison_path, comparison)
    manifest = evaluation_manifest | {
        "comparison_artifact": comparison_artifact,
        "comparison_receipt": producer._file_receipt(comparison_path, repo_root=repo),
    }
    _write_json(repo / producer.MANIFEST_REL, manifest)
    _write_json(
        repo / producer.REPORT_REL,
        {
            "suite": producer.SUITE,
            "summary": {
                "total": chapter_count * rows_per_shard,
                "matches": chapter_count * rows_per_shard,
                "mismatches": 0,
                "engine_errors": 0,
            },
            "output_summary": comparison["per_slot"],
            "classification": {
                "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
                "inputs": {
                    "comparison_receipt_sha256": _sha256(comparison_path),
                    "comparison_artifact_sha256": comparison_artifact["sha256"],
                },
            },
        },
    )
    _write_json(
        repo / producer.BRIDGE_REL,
        {
            "schema": "axiom_oracles.bridge_manifest.v1",
            "suite": producer.SUITE,
            "program": "fixture",
            "period": "2026",
            "strict": True,
            "oracle": {},
            "population": {
                "family": "fixture",
                "pin_required": True,
                "pinned": {"revision": "fixture", "sha256": "f" * 64},
            },
            "bindings": [
                {
                    "input": name,
                    "kind": "mapped",
                    "source_function": "fixture",
                    "audit": "read",
                }
                for name in producer.MAPPED_FIELDS
            ]
            + [
                {
                    "input": "probe_fact",
                    "kind": "projected",
                    "source_function": "fixture",
                    "audit": "read",
                },
                {
                    "input": "flag_a",
                    "kind": "constant",
                    "value": True,
                    "source_function": "fixture",
                    "audit": "read",
                },
                {
                    "inputs": sorted(producer.ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS),
                    "kind": "constant",
                    "value": False,
                    "source_function": "fixture",
                    "audit": "read",
                },
                {
                    "input": "neutral_fact",
                    "kind": "constant",
                    "value": False,
                    "reason": "Pinned fixture false",
                    "audit": "read",
                },
            ],
            "completeness": {
                "status": "verified",
                "source": "committed_exercise_receipt",
                "receipt": str(producer.RECEIPT_REL),
            },
        },
    )
    return producer, repo, shard_path


def test_build_receipt_scans_bound_shard_and_derives_every_feed_field(
    tmp_path: Path,
) -> None:
    producer, repo, _shard = _fixture(tmp_path)

    receipt = producer.build_receipt(repo_root=repo, expected_shard_count=1)

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
        *producer.ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS,
    }
    assert all(
        row == {"distinct": 1, "state": "constant"}
        for row in receipt["evidence_fields"].values()
    )
    assert [row["path"] for row in receipt["evidence_artifacts"]] == [
        str(producer.MANIFEST_REL),
        str(producer.COMPARISON_REL),
        str(producer.REPORT_REL),
        str(producer.BRIDGE_REL),
    ]


def test_build_receipt_rejects_shard_hash_drift(tmp_path: Path) -> None:
    producer, repo, shard = _fixture(tmp_path)
    original = gzip.decompress(shard.read_bytes()).decode()
    with gzip.open(shard, "at") as target:
        target.write(original)

    with pytest.raises(ValueError, match="shard body is absent or stale"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)


@pytest.mark.parametrize(
    "target", ["report", "manifest", "comparison", "bridge", "contract", "campaign"]
)
@pytest.mark.parametrize("restore", [False, True], ids=["drift", "aba"])
def test_metadata_drift_during_scan_cannot_be_relabelled(
    tmp_path: Path,
    monkeypatch,
    target: str,
    restore: bool,
) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    paths = {
        "report": producer.REPORT_REL,
        "manifest": producer.MANIFEST_REL,
        "comparison": producer.COMPARISON_REL,
        "bridge": producer.BRIDGE_REL,
        "contract": producer.INPUT_CONTRACT_REL,
        "campaign": producer.CAMPAIGN_REL,
    }
    path = repo / paths[target]
    original = path.read_bytes()
    campaign = producer._load_campaign(repo)
    probe = campaign._probe_boolean_inputs

    def mutate(value):
        path.write_bytes(original + b"\n")
        if restore:
            path.write_bytes(original)
        return probe(value)

    monkeypatch.setattr(campaign, "_probe_boolean_inputs", mutate)
    monkeypatch.setattr(producer, "_load_campaign", lambda *_args: campaign)
    with pytest.raises(ValueError, match="evidence changed"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)


@pytest.mark.parametrize("restore", [False, True], ids=["replacement", "aba"])
def test_shard_scan_hashes_actual_consumed_bytes(
    tmp_path: Path,
    monkeypatch,
    restore: bool,
) -> None:
    producer, repo, shard = _fixture(tmp_path, rows_per_shard=2)
    original = shard.read_bytes()
    records = [json.loads(line) for line in gzip.decompress(original).splitlines()]
    records[1]["iso2"] = "US"
    changed = gzip.compress("".join(json.dumps(row) + "\n" for row in records).encode())
    # Keep both valid gzip streams the same length, so this specifically
    # exercises the consumed-byte hash, not an incidental gzip framing error.
    assert len(changed) <= len(original)
    changed = changed.ljust(len(original), b"\0")
    read = producer._HashingReader.read
    mutated = False

    def mutate_before_read(self, size=-1):
        nonlocal mutated
        if not mutated:
            mutated = True
            shard.write_bytes(changed)
        return read(self, size)

    monkeypatch.setattr(producer._HashingReader, "read", mutate_before_read)
    campaign = producer._load_campaign(repo)
    probe = campaign._probe_boolean_inputs

    def restore_after_read(value):
        if restore:
            shard.write_bytes(original)
        return probe(value)

    monkeypatch.setattr(campaign, "_probe_boolean_inputs", restore_after_read)
    monkeypatch.setattr(producer, "_load_campaign", lambda *_args: campaign)
    with pytest.raises(ValueError, match="shard body is absent or stale"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)
    assert mutated
    if restore:
        assert shard.read_bytes() == original


def test_replacing_shard_path_does_not_change_the_scanned_descriptor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    producer, repo, shard = _fixture(tmp_path)
    original = shard.read_bytes()
    replacement = tmp_path / "replacement.gz"
    replacement.write_bytes(original)
    read = producer._HashingReader.read
    replaced = False

    def replace_path(self, size=-1):
        nonlocal replaced
        if not replaced:
            replaced = True
            os.replace(replacement, shard)
        return read(self, size)

    monkeypatch.setattr(producer._HashingReader, "read", replace_path)
    with pytest.raises(ValueError, match="shard changed while scanning"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)


def test_previously_scanned_shard_is_guarded_until_return(
    tmp_path: Path, monkeypatch
) -> None:
    producer, repo, first_shard = _fixture(tmp_path, chapter_count=2)
    original = first_shard.read_bytes()
    campaign = producer._load_campaign(repo)
    probe = campaign._probe_boolean_inputs
    calls = 0

    def mutate_on_second_shard(value):
        nonlocal calls
        calls += 1
        if calls == 2:
            first_shard.write_bytes(original + b"\0")
        return probe(value)

    monkeypatch.setattr(campaign, "_probe_boolean_inputs", mutate_on_second_shard)
    monkeypatch.setattr(producer, "_load_campaign", lambda *_args: campaign)
    with pytest.raises(ValueError, match="evidence changed"):
        producer.build_receipt(repo_root=repo, expected_shard_count=2)
    assert calls == 2


@pytest.mark.parametrize("mutation", ["counts", "classification", "boolean_count"])
def test_report_must_bind_the_current_comparison(tmp_path: Path, mutation: str) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    path = repo / producer.REPORT_REL
    report = json.loads(path.read_text())
    if mutation == "classification":
        report["classification"]["inputs"]["comparison_receipt_sha256"] = "0" * 64
    elif mutation == "counts":
        report["output_summary"] = {"section_338": {"match": 2}}
    else:
        report["output_summary"] = {"section_338": {"match": True}}
    _write_json(path, report)
    with pytest.raises(ValueError, match="campaign report .*current comparison"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)


def test_observed_constant_value_must_match_bridge(tmp_path: Path) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    path = repo / producer.BRIDGE_REL
    bridge = json.loads(path.read_text())
    bridge["bindings"][-1]["value"] = True
    _write_json(path, bridge)
    with pytest.raises(ValueError, match="construction constant has wrong value"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)


@pytest.mark.parametrize(
    ("field", "kind", "value"),
    [
        ("neutral_fact", "projected", None),
        ("flag_a", "projected", None),
        ("probe_fact", "constant", False),
    ],
)
def test_bridge_kind_must_match_authenticated_source_semantics(
    tmp_path: Path, field: str, kind: str, value: bool | None
) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    path = repo / producer.BRIDGE_REL
    bridge = json.loads(path.read_text())
    for binding in bridge["bindings"]:
        names = binding.get("inputs", [binding.get("input")])
        if field not in names:
            continue
        binding["kind"] = kind
        if value is None:
            binding.pop("value", None)
        else:
            binding["value"] = value
        break
    else:  # pragma: no cover - fixture guard
        raise AssertionError(field)
    _write_json(path, bridge)
    with pytest.raises(ValueError, match="kind contradicts source semantics"):
        producer.build_receipt(repo_root=repo, expected_shard_count=1)


def test_production_api_has_no_unauthenticated_campaign_injection(
    tmp_path: Path,
) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    assert "campaign" not in inspect.signature(producer.build_receipt).parameters
    with pytest.raises(TypeError, match="campaign"):
        producer.build_receipt(  # type: ignore[call-arg]
            repo_root=repo,
            expected_shard_count=1,
            campaign=object(),
        )


def test_shard_key_is_rederived_by_authenticated_campaign(tmp_path: Path) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    manifest = json.loads((repo / producer.MANIFEST_REL).read_text())
    contract = json.loads((repo / producer.INPUT_CONTRACT_REL).read_text())
    campaign = producer._load_campaign(repo)
    old_key, shard = next(iter(manifest["shards"].items()))
    fake_key = "f" * 64 if old_key != "f" * 64 else "e" * 64
    shard["key"] = fake_key
    manifest["shards"] = {fake_key: shard}
    with pytest.raises(ValueError, match="shard identity drift"):
        producer._shard_catalog(manifest, contract, campaign, 1)


def test_shard_json_rejects_duplicate_keys() -> None:
    producer = _load_producer()
    with pytest.raises(ValueError, match="duplicate JSON key"):
        json.loads(
            '{"iso2":"CA","iso2":"US"}', object_pairs_hook=producer._unique_pairs
        )


@pytest.mark.parametrize(
    "raw", ["/tmp/evidence.json", "../evidence.json", "a/../b.json"]
)
def test_repository_evidence_paths_reject_escape(tmp_path: Path, raw: str) -> None:
    producer = _load_producer()
    with pytest.raises(ValueError, match="invalid .* path"):
        producer._repo_file(tmp_path, raw, "fixture")


def test_external_bulk_paths_must_be_absolute() -> None:
    producer = _load_producer()
    with pytest.raises(ValueError, match="must be absolute"):
        producer._external_file("relative/shard.jsonl.gz", "fixture shard")


def test_receipt_consumer_needs_no_external_body_or_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    producer, repo, _shard = _fixture(tmp_path, chapter_count=100)
    receipt = producer.build_receipt(repo_root=repo)
    _write_json(repo / producer.RECEIPT_REL, receipt)
    path_open = Path.open

    def forbid_external_open(path, *args, **kwargs):
        assert path.is_relative_to(repo.resolve()), f"external body read: {path}"
        return path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_external_open)
    snapshots = producer.validate_committed_receipt(receipt, repo_root=repo)
    assert receipt["cases"] == 100
    assert (
        snapshots[repo.resolve() / producer.RECEIPT_REL].sha256
        == hashlib.sha256(producer._render(receipt).encode()).hexdigest()
    )


def test_live_receipt_matches_independently_audited_hash() -> None:
    producer = _load_producer()
    path = producer.REPO_ROOT / producer.RECEIPT_REL

    assert _sha256(path) == producer.TRUSTED_RECEIPT_SHA256


def test_live_consumer_rejects_untrusted_receipt_hash(
    tmp_path: Path, monkeypatch
) -> None:
    producer, repo, _shard = _fixture(tmp_path, chapter_count=100)
    receipt = producer.build_receipt(repo_root=repo)
    _write_json(repo / producer.RECEIPT_REL, receipt)
    monkeypatch.setattr(producer, "REPO_ROOT", repo)

    with pytest.raises(ValueError, match="has not been independently audited"):
        producer.validate_committed_receipt(receipt, repo_root=repo)


@pytest.mark.parametrize(
    "distinct,state",
    [
        (None, None),
        (0, None),
        (-1, None),
        (True, "constant"),
        (1.0, "constant"),
        (2, "varied"),
        (1, None),
        (1, "varied"),
    ],
)
def test_receipt_consumer_rejects_invalid_observation_counts(
    tmp_path: Path,
    distinct,
    state,
) -> None:
    producer, repo, _shard = _fixture(tmp_path)
    receipt = producer.build_receipt(repo_root=repo, expected_shard_count=1)
    receipt["evidence_fields"]["neutral_fact"] = {"distinct": distinct, "state": state}
    _write_json(repo / producer.RECEIPT_REL, receipt)
    with pytest.raises(
        ValueError, match="invalid exercise distinct count|state/count disagree"
    ):
        producer.validate_committed_receipt(
            receipt, repo_root=repo, expected_shard_count=1
        )


@pytest.mark.parametrize("mutation", ["cases", "fields", "artifact", "constant"])
def test_receipt_consumer_rejects_fabricated_or_incomplete_census(
    tmp_path: Path,
    mutation: str,
) -> None:
    producer, repo, _shard = _fixture(tmp_path, rows_per_shard=2)
    receipt = producer.build_receipt(repo_root=repo, expected_shard_count=1)
    messages = {
        "cases": "case count differs",
        "fields": "field catalog differs",
        "artifact": "artifact set/hash drift",
        "constant": "construction constant varied",
    }
    if mutation == "cases":
        receipt["cases"] = 777
    elif mutation == "fields":
        del receipt["evidence_fields"]["flag_a"]
    elif mutation == "artifact":
        receipt["evidence_artifacts"].pop()
    else:
        receipt["evidence_fields"]["neutral_fact"] = {"distinct": 2, "state": "varied"}
    _write_json(repo / producer.RECEIPT_REL, receipt)
    with pytest.raises(ValueError, match=messages[mutation]):
        producer.validate_committed_receipt(
            receipt, repo_root=repo, expected_shard_count=1
        )


@pytest.mark.parametrize(
    "post_drift", ["inputs", "output", "output_aba", "replacement"]
)
def test_guarded_publication_does_not_leave_false_success(
    tmp_path: Path,
    post_drift: str,
) -> None:
    producer = _load_producer()
    path = tmp_path / "receipt.json"
    path.write_bytes(b"old")
    path.chmod(0o644)
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls != 3:
            return
        if post_drift == "inputs":
            raise ValueError("input drift")
        if post_drift == "replacement":
            other = tmp_path / "other.json"
            other.write_bytes(b"external replacement")
            os.replace(other, path)
        else:
            path.write_bytes(b"changed")
            if post_drift == "output_aba":
                path.write_bytes(b"new")

    with pytest.raises(
        ValueError, match="input drift|published exercise receipt changed"
    ):
        producer._publish_receipt(path, b"new", guard)
    if post_drift == "replacement":
        assert path.read_bytes() == b"external replacement"
    else:
        assert path.read_bytes() == b"old"
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert list(tmp_path.glob("receipt.json.*")) == []


def test_guarded_publication_preserves_mode_on_success(tmp_path: Path) -> None:
    producer = _load_producer()
    path = tmp_path / "receipt.json"
    path.write_bytes(b"old")
    path.chmod(0o644)
    producer._publish_receipt(path, b"new", lambda: None)
    assert path.read_bytes() == b"new"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_failed_first_publication_removes_only_its_own_output(tmp_path: Path) -> None:
    producer = _load_producer()
    path = tmp_path / "receipt.json"
    calls = 0

    def guard() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError("late input drift")

    with pytest.raises(ValueError, match="late input drift"):
        producer._publish_receipt(path, b"new", guard)
    assert not path.exists()
