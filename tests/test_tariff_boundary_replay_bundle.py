"""Offline replays must reject substituted bundles before executing their engine."""

import json
from pathlib import Path

import pytest

from scripts import tariff_boundary_replay_bundle as bundle


def test_untrusted_manifest_is_rejected_before_parsing_or_running(
    tmp_path, monkeypatch
):
    (tmp_path / "manifest.json").write_bytes(b"not JSON")
    monkeypatch.setattr(
        bundle.subprocess, "run", lambda *a, **k: pytest.fail("must not execute")
    )
    with pytest.raises(ValueError, match="trust anchor"):
        bundle.verify(tmp_path, "0" * 64)


@pytest.mark.parametrize(
    "relative", ["axiom-rules-engine", "runs/0.compiled.json", "evidence.json"]
)
def test_substituted_payload_is_rejected_before_execution(
    tmp_path, monkeypatch, relative
):
    original = b"original"
    manifest = {
        "schema": bundle.SCHEMA,
        "repository_base_ref": bundle.REPOSITORY_BASE_REF,
        "engine_source_repository": bundle.ENGINE_SOURCE_REPOSITORY,
        "engine_source_ref": bundle.ENGINE_SOURCE_REF,
        "engine_sha256": bundle.ENGINE_SHA256,
        "files": {
            name: {"sha256": bundle.digest(original), "bytes": len(original)}
            for name in bundle.FILES
        },
    }
    raw = bundle.render(manifest)
    for name in bundle.FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original if name != relative else b"changed!")
    (tmp_path / "manifest.json").write_bytes(raw)
    monkeypatch.setattr(
        bundle.subprocess, "run", lambda *a, **k: pytest.fail("must not execute")
    )
    with pytest.raises(ValueError, match="digest/size mismatch"):
        bundle.verify(tmp_path, bundle.digest(raw))


def test_symlink_payload_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.write_bytes(b"payload")
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "manifest.json").symlink_to(outside)
    with pytest.raises(ValueError, match="escaped or is a symlink"):
        bundle.verify(root, bundle.digest(b"payload"))


def test_path_traversal_manifest_cannot_add_an_executable(tmp_path):
    manifest = bundle.render(
        {
            "schema": bundle.SCHEMA,
            "repository_base_ref": bundle.REPOSITORY_BASE_REF,
            "engine_source_repository": bundle.ENGINE_SOURCE_REPOSITORY,
            "engine_source_ref": bundle.ENGINE_SOURCE_REF,
            "engine_sha256": bundle.ENGINE_SHA256,
            "files": {"../engine": {}},
        }
    )
    (tmp_path / "manifest.json").write_bytes(manifest)
    with pytest.raises(ValueError, match="file population"):
        bundle.verify(tmp_path, bundle.digest(manifest))


def test_committed_bundle_receipt_has_complete_inputs_and_no_certification():
    path = (
        Path(__file__).resolve().parents[1]
        / "reference/us-tariff-schedule/boundary-evidence/offline-replay-manifest.json"
    )
    receipt = json.loads(path.read_bytes())
    assert set(receipt["manifest"]["files"]) == bundle.FILES
    assert receipt["manifest"]["claims"]["certified"] is False
    assert receipt["manifest"]["claims"]["closed"] is False
    assert receipt["manifest"]["files"]["verify.py"]["sha256"] == bundle.digest(
        Path(bundle.__file__).read_bytes()
    )
    assert receipt["verification"]["manifest_sha256"] == bundle.digest(
        bundle.render(receipt["manifest"])
    )
    assert receipt["verification"]["returned_output_bindings"] == 768
    assert receipt["verification"]["query_executions"] == 384
    assert receipt["verification"]["distinct_entity_ids"] == 192
    assert receipt["verification"]["verification_scope"] == (
        "exact_recorded_native_outcomes_only"
    )
    assert receipt["verification"]["engine_binary_reproducible_build_verified"] is False
