from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
import yaml

from scripts import rebind_us_tariff_campaign_dispositions as producer


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sealed(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["receipt_payload_sha256"] = producer.canonical_sha256(result)
    return result


def _receipt(path: Path, repo: Path) -> dict[str, Any]:
    return producer.file_receipt(producer.snapshot_file(path), repo)


def _fixture(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    reference = repo / "reference/us-tariff-schedule"
    reference.mkdir(parents=True)
    ledger_path = reference / "campaign-dispositions.yaml"
    manifest_path = reference / "eval/MANIFEST.json"
    comparison_path = reference / "comparison-summary.json"
    transition_path = reference / "preview-selector-transition-receipt.json"
    cafta_path = reference / "cafta-reference-defect-supersession-receipt.json"
    steel_path = reference / "steel-scope-projection-receipt.json"
    remaining_path = reference / "remaining-residual-receipt.json"

    artifact_path = tmp_path / "comparison.jsonl.gz"
    artifact_path.write_bytes(b"fixture comparison body\n")
    artifact_receipt = _receipt(artifact_path, repo)
    generation_id = "a" * 32
    run_identity = {"fixture": True}
    run_identity_sha256 = producer.canonical_sha256(run_identity)
    evaluation_only = {
        "schema": "axiom_oracles.us_tariff_schedule.eval_manifest.v3",
        "shards": {},
        "run_identity": run_identity,
        "run_identity_sha256": run_identity_sha256,
        "generation_id": generation_id,
    }
    comparison = {
        "schema": "axiom_oracles.us_tariff_schedule.comparison_summary.v3",
        "run_identity_sha256": run_identity_sha256,
        "generation_id": generation_id,
        "evaluation_manifest_sha256": producer.canonical_sha256(evaluation_only),
        "comparison_artifact": artifact_receipt,
    }
    _write_json(comparison_path, comparison)
    manifest = {
        **evaluation_only,
        "comparison_artifact": artifact_receipt,
        "comparison_receipt": _receipt(comparison_path, repo),
    }
    _write_json(manifest_path, manifest)
    inputs = {
        "evaluation_manifest": _receipt(manifest_path, repo),
        "comparison_receipt": _receipt(comparison_path, repo),
        "comparison_artifact": artifact_receipt,
    }
    bindings = {
        "run_identity_sha256": run_identity_sha256,
        "generation_id": generation_id,
        "evaluation_manifest_sha256": comparison["evaluation_manifest_sha256"],
    }

    cafta = _sealed(
        {
            "schema": producer.CAFTA_SCHEMA,
            "verdict": "PASS",
            "inputs": inputs,
            "bindings": bindings,
            "fixture": "cafta",
        }
    )
    _write_json(cafta_path, cafta)

    children_by_id: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []
    child_number = 0
    for parent_id, child_ids in producer.TRANSITION_PARENT_TO_CHILDREN.items():
        children = []
        for child_id in child_ids:
            child_number += 1
            child = {
                "id": child_id,
                "parent_id": parent_id,
                "logical_class": f"logical-{child_number}",
                "match": {"slot": f"slot-{child_number}"},
                "disposition": "explained_residual",
                "attribution": "fixture-attribution",
                "expected_units": child_number,
                "expected_signature_count": child_number + 100,
                "expected_signature_population_sha256": _hash(
                    f"transition signatures {child_number}"
                ),
            }
            children.append(child)
            children_by_id[child_id] = child
        evidence: dict[str, Any] = {}
        if parent_id == "cafta-52i-deferred":
            evidence["cafta_supersession_receipt"] = {
                "file": _receipt(cafta_path, repo),
                "payload": cafta,
            }
        transitions.append(
            {
                "parent_id": parent_id,
                "status": "retired" if not children else "superseded",
                "children": children,
                "evidence": evidence,
            }
        )
    transition = _sealed(
        {
            "schema": producer.TRANSITION_SCHEMA,
            "verdict": "PASS",
            "inputs": inputs,
            "bindings": bindings,
            "transitions": transitions,
        }
    )
    _write_json(transition_path, transition)

    def proof_classes(ids: tuple[str, ...], label: str) -> list[dict[str, Any]]:
        return [
            {
                "id": entry_id,
                "disposition": "explained_residual",
                "attribution": f"{label}-attribution",
                "expected_units": number + 1,
                "expected_signature_count": number + 11,
                "expected_signature_population_sha256": _hash(
                    f"{label} signature population {number}"
                ),
                "identity_population_sha256": _hash(
                    f"{label} identity population {number}"
                ),
                "signatures": [_hash(f"{label} signature {number}")],
            }
            for number, entry_id in enumerate(ids)
        ]

    steel_classes = proof_classes(producer.STEEL_ENTRY_IDS, "steel")
    steel = _sealed(
        {
            "schema": producer.STEEL_SCHEMA,
            "verdict": "PASS",
            "inputs": inputs,
            "bindings": bindings,
            "classes": steel_classes,
        }
    )
    _write_json(steel_path, steel)
    remaining_classes = proof_classes(producer.REMAINING_ENTRY_IDS, "remaining")
    remaining = _sealed(
        {
            "schema": producer.REMAINING_SCHEMA,
            "verdict": "PASS",
            "inputs": inputs,
            "bindings": bindings,
            "classes": remaining_classes,
        }
    )
    _write_json(remaining_path, remaining)

    old_number = 0

    def old_hash() -> str:
        nonlocal old_number
        old_number += 1
        return _hash(f"old ledger hash {old_number}")

    entries: list[dict[str, Any]] = []
    for entry_id in producer.TRANSITION_ENTRY_IDS:
        child = children_by_id[entry_id]
        entry = {
            **child,
            "evidence": {
                "transition": {
                    "parent_id": child["parent_id"],
                    "child_id": entry_id,
                    "receipt_payload_sha256": old_hash(),
                }
            },
        }
        if entry_id == producer.CAFTA_ENTRY_ID:
            entry["evidence"]["cafta_supersession_receipt_payload_sha256"] = old_hash()
        entries.append(entry)

    def class_entry(
        item: dict[str, Any], evidence_key: str, receipt_path: Path
    ) -> dict[str, Any]:
        return {
            **item,
            "evidence": {
                evidence_key: {
                    "receipt": producer._relative_path(receipt_path, repo),
                    "sha256": old_hash(),
                    "receipt_payload_sha256": old_hash(),
                    "identity_population_sha256": item["identity_population_sha256"],
                }
            },
        }

    entries.extend(
        class_entry(item, "steel_scope_projection", steel_path)
        for item in steel_classes
    )
    entries.extend(
        class_entry(item, "remaining_residuals", remaining_path)
        for item in remaining_classes
    )
    ledger = {
        "schema": producer.LEDGER_SCHEMA,
        "suite": producer.SUITE,
        "updated": "fixture",
        "entries": entries,
    }
    ledger_path.write_text(
        "# formatting sentinel: must survive byte-for-byte\n"
        + yaml.safe_dump(ledger, sort_keys=False)
    )
    assert old_number == producer.EXPECTED_TARGET_COUNT
    return {
        "repo_root": repo,
        "ledger_path": ledger_path,
        "transition_receipt_path": transition_path,
        "cafta_receipt_path": cafta_path,
        "steel_receipt_path": steel_path,
        "remaining_receipt_path": remaining_path,
        "eval_manifest_path": manifest_path,
        "comparison_receipt_path": comparison_path,
    }


def _mutate_json(path: Path, mutation: Any, *, reseal: bool = False) -> None:
    value = json.loads(path.read_text())
    mutation(value)
    if reseal:
        value.pop("receipt_payload_sha256", None)
        value = _sealed(value)
    _write_json(path, value)


def test_generate_changes_exactly_39_scalars_and_check_is_idempotent(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    before = paths["ledger_path"].read_text()
    plan = producer.prepare_plan(**paths)
    assert len(plan.targets) == len(plan.changed) == 39

    with pytest.raises(ValueError, match="stale tariff disposition ledger: 39"):
        producer.run(mode="check", **paths)
    result = producer.run(mode="generate", **paths)
    assert result["target_scalars"] == result["changed_scalars"] == 39
    after = paths["ledger_path"].read_text()
    assert after == plan.output.decode()
    assert after.startswith("# formatting sentinel: must survive byte-for-byte\n")
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    assert len(before_lines) == len(after_lines)
    assert sum(left != right for left, right in zip(before_lines, after_lines)) == 39

    checked = producer.run(mode="check", **paths)
    assert checked["target_scalars"] == 39
    assert checked["changed_scalars"] == 0
    assert paths["ledger_path"].read_text() == after


def test_partial_rebinding_fails_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    plan = producer.prepare_plan(**paths)
    target = plan.targets[0]
    ledger = producer.parse_yaml(
        paths["ledger_path"].read_bytes(), label="fixture ledger"
    )
    entry = next(item for item in ledger["entries"] if item["id"] == target.entry_id)
    producer._set_mapping_at(entry, target.path, target.value)
    paths["ledger_path"].write_text(yaml.safe_dump(ledger, sort_keys=False))

    with pytest.raises(ValueError, match="partially rebound ledger.*found 38"):
        producer.run(mode="generate", **paths)


def test_unexpected_hash_field_fails_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    ledger = producer.parse_yaml(
        paths["ledger_path"].read_bytes(), label="fixture ledger"
    )
    ledger["entries"].append(
        {
            "id": "unexpected-transition-entry",
            "evidence": {
                "transition": {"receipt_payload_sha256": _hash("unexpected target")}
            },
        }
    )
    paths["ledger_path"].write_text(yaml.safe_dump(ledger, sort_keys=False))

    with pytest.raises(ValueError, match="exact 39-field contract"):
        producer.prepare_plan(**paths)


def test_tampered_proof_payload_fails_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    steel_path = paths["steel_receipt_path"]
    steel = json.loads(steel_path.read_text())
    steel["classes"][0]["expected_units"] += 1
    _write_json(steel_path, steel)

    with pytest.raises(ValueError, match="does not authenticate its document"):
        producer.prepare_plan(**paths)


@pytest.mark.parametrize(
    ("artifact", "mutation", "message"),
    [
        (
            "eval_manifest_path",
            lambda value: value.__setitem__("schema", "bogus.eval.schema"),
            "complete comparison-bound v3 manifest",
        ),
        (
            "comparison_receipt_path",
            lambda value: value.__setitem__("schema", "bogus.comparison.schema"),
            "comparison receipt is not schema v3",
        ),
        (
            "eval_manifest_path",
            lambda value: value.__setitem__(
                "run_identity_sha256", _hash("bogus run identity digest")
            ),
            "run-identity digest drift",
        ),
        (
            "comparison_receipt_path",
            lambda value: value.__setitem__(
                "evaluation_manifest_sha256", _hash("bogus evaluation digest")
            ),
            "evaluation-manifest binding is stale",
        ),
    ],
)
def test_campaign_schema_and_digest_mutations_fail_closed(
    tmp_path: Path,
    artifact: str,
    mutation: Any,
    message: str,
) -> None:
    paths = _fixture(tmp_path)
    _mutate_json(paths[artifact], mutation)

    with pytest.raises(ValueError, match=message):
        producer.prepare_plan(**paths)


def test_comparison_artifact_mutation_fails_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    comparison = json.loads(paths["comparison_receipt_path"].read_text())
    artifact_path = Path(comparison["comparison_artifact"]["path"])
    artifact_path.write_bytes(b"tampered comparison body\n")

    with pytest.raises(ValueError, match="comparison artifact hash or size drift"):
        producer.prepare_plan(**paths)


@pytest.mark.parametrize(
    "receipt_key", ["transition_receipt_path", "cafta_receipt_path"]
)
def test_direct_proof_evaluation_digest_mutation_fails_closed(
    tmp_path: Path, receipt_key: str
) -> None:
    paths = _fixture(tmp_path)

    def mutate(value: dict[str, Any]) -> None:
        value["bindings"]["evaluation_manifest_sha256"] = _hash(
            "bogus direct proof evaluation digest"
        )

    _mutate_json(paths[receipt_key], mutate, reseal=True)
    with pytest.raises(ValueError, match="proof evaluation-manifest binding drift"):
        producer.prepare_plan(**paths)


@pytest.mark.parametrize(
    ("has_children", "wrong_status", "expected_status"),
    [(True, "retired", "superseded"), (False, "superseded", "retired")],
)
def test_transition_status_must_match_child_state(
    tmp_path: Path,
    has_children: bool,
    wrong_status: str,
    expected_status: str,
) -> None:
    paths = _fixture(tmp_path)

    def mutate(value: dict[str, Any]) -> None:
        transition = next(
            item
            for item in value["transitions"]
            if bool(item["children"]) is has_children
        )
        transition["status"] = wrong_status

    _mutate_json(paths["transition_receipt_path"], mutate, reseal=True)
    with pytest.raises(ValueError, match=f"must be {expected_status}"):
        producer.prepare_plan(**paths)


def test_ledger_race_at_conditional_publish_is_not_overwritten(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    ledger_path = paths["ledger_path"]
    concurrent = b"# concurrent ledger replacement\n"

    with pytest.raises(ValueError, match="evidence changed after validation"):
        producer.run(
            mode="generate",
            _before_replace=lambda: ledger_path.write_bytes(concurrent),
            **paths,
        )
    assert ledger_path.read_bytes() == concurrent


def test_evidence_race_at_conditional_publish_leaves_ledger_unchanged(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    ledger_path = paths["ledger_path"]
    original_ledger = ledger_path.read_bytes()
    comparison = json.loads(paths["comparison_receipt_path"].read_text())
    artifact_path = Path(comparison["comparison_artifact"]["path"])

    def race() -> None:
        artifact_path.write_bytes(b"late comparison replacement\n")

    with pytest.raises(ValueError, match="evidence changed after validation"):
        producer.run(
            mode="generate",
            _before_replace=race,
            **paths,
        )
    assert ledger_path.read_bytes() == original_ledger


def test_prepared_publication_drift_leaves_prior_ledger_unchanged(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    ledger_path = paths["ledger_path"]
    original_ledger = ledger_path.read_bytes()

    def tamper_with_prepared_publication() -> None:
        staged = list(ledger_path.parent.glob(ledger_path.name + ".rebind.*"))
        assert len(staged) == 1
        staged[0].write_bytes(b"tampered staged ledger\n")

    with pytest.raises(ValueError, match="evidence changed after validation"):
        producer.run(
            mode="generate",
            _before_replace=tamper_with_prepared_publication,
            **paths,
        )
    assert ledger_path.read_bytes() == original_ledger


def test_evidence_race_inside_replace_rolls_back_exact_prior_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path)
    ledger_path = paths["ledger_path"]
    original_ledger = ledger_path.read_bytes()
    original_mode = ledger_path.stat().st_mode
    steel_receipt_path = paths["steel_receipt_path"]
    real_replace = producer.os.replace
    injected = False

    def replace_then_race(source: Path, destination: Path) -> None:
        nonlocal injected
        real_replace(source, destination)
        if not injected and Path(destination).resolve() == ledger_path.resolve():
            injected = True
            steel_receipt_path.write_bytes(b"post-replacement steel proof race\n")

    monkeypatch.setattr(producer.os, "replace", replace_then_race)
    with pytest.raises(ValueError, match="evidence changed after validation"):
        producer.run(mode="generate", **paths)

    assert injected
    assert ledger_path.read_bytes() == original_ledger
    assert ledger_path.stat().st_mode == original_mode


def test_post_replace_mode_drift_rolls_back_exact_prior_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path)
    ledger_path = paths["ledger_path"]
    original_ledger = ledger_path.read_bytes()
    original_mode = ledger_path.stat().st_mode
    real_replace = producer.os.replace
    injected = False

    def replace_then_chmod(source: Path, destination: Path) -> None:
        nonlocal injected
        real_replace(source, destination)
        if not injected and Path(destination).resolve() == ledger_path.resolve():
            injected = True
            ledger_path.chmod(0o600)

    monkeypatch.setattr(producer.os, "replace", replace_then_chmod)
    with pytest.raises(ValueError, match="published ledger bytes or mode drifted"):
        producer.run(mode="generate", **paths)

    assert injected
    assert ledger_path.read_bytes() == original_ledger
    assert ledger_path.stat().st_mode == original_mode


def test_publication_holds_shared_manifest_lock_through_replace(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    manifest = paths["eval_manifest_path"]
    lock_path = manifest.with_name(f".{manifest.name}.lock")

    def require_contender_is_blocked() -> None:
        contender = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import fcntl, sys\n"
                    "with open(sys.argv[1], 'a+') as handle:\n"
                    "    try:\n"
                    "        fcntl.flock(handle.fileno(), "
                    "fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
                    "    except BlockingIOError:\n"
                    "        raise SystemExit(42)\n"
                    "raise SystemExit(0)\n"
                ),
                str(lock_path),
            ],
            check=False,
        )
        assert contender.returncode == 42

    producer.run(mode="generate", _before_replace=require_contender_is_blocked, **paths)


def test_exact_reviewed_target_shape() -> None:
    assert len(producer.TRANSITION_PARENT_TO_CHILDREN) == 18
    assert len(producer.TRANSITION_ENTRY_IDS) == 30
    assert producer.CAFTA_ENTRY_ID in producer.TRANSITION_ENTRY_IDS
    assert len(set(producer.TRANSITION_ENTRY_IDS)) == 30
    assert len(producer.STEEL_ENTRY_IDS) == len(producer.REMAINING_ENTRY_IDS) == 2
    assert 30 + 1 + 2 * 2 + 2 * 2 == producer.EXPECTED_TARGET_COUNT == 39
