"""Certificate integration tests for the computed executable premise."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from axiom_oracles.executable_receipt import RECEIPT_SCHEMA

REPO_ROOT = Path(__file__).resolve().parents[1]
CERTIFY_PATH = REPO_ROOT / "scripts/certify.py"
EXECUTABLE_CERTIFICATES = Path("certificates/executable")
WORKFLOW_SHA = "a" * 40


def _load_certify() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "certify_executable_under_test",
        CERTIFY_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def certificate_root(tmp_path: Path) -> Path:
    shutil.copytree(
        REPO_ROOT / EXECUTABLE_CERTIFICATES,
        tmp_path / EXECUTABLE_CERTIFICATES,
    )
    receipt_path = (
        tmp_path / EXECUTABLE_CERTIFICATES / "us-co-snap/receipt.json"
    )
    receipt_path.unlink(missing_ok=True)
    return tmp_path


def _write_valid_receipt(root: Path) -> Path:
    manifest = json.loads(
        (root / EXECUTABLE_CERTIFICATES / "us-co-snap/manifest.json").read_text()
    )
    release_manifest = json.loads(
        (root / EXECUTABLE_CERTIFICATES / "engine-releases.json").read_text()
    )
    release = release_manifest["releases"][manifest["engine"]["release"]]
    target = manifest["engine"]["target"]
    asset = release["assets"][target]
    golden_inputs = json.loads(
        (root / manifest["golden"]["input_path"]).read_text()
    )
    golden_outputs = json.loads(
        (root / manifest["golden"]["outputs_path"]).read_text()
    )["expected"]

    allowlist_path = root / manifest["workflow"]["allowlist"]
    allowlist = json.loads(allowlist_path.read_text())
    allowlist["allowed_workflow_shas"] = [WORKFLOW_SHA]
    allowlist_path.write_text(json.dumps(allowlist, indent=2) + "\n")

    work = ".executable-receipt-work"
    archive = f"{work}/engine.tar.xz"
    binary = (
        f"{work}/engine/axiom-rules-engine-{target}/axiom-rules-engine"
    )
    artifact_manifest = f"{work}/artifact-manifest.json"
    artifact = f"{work}/{manifest['artifact']['name']}"
    curl = [
        "curl",
        "--fail",
        "--location",
        "--proto",
        "=https",
        "--tlsv1.2",
        "--silent",
        "--show-error",
        "--output",
    ]
    engine_url = (
        f"https://github.com/{release['repository']}/releases/download/"
        f"{manifest['engine']['release']}/{asset['name']}"
    )
    artifact_base = (
        f"https://github.com/{manifest['artifact']['repository']}/releases/"
        f"download/{manifest['artifact']['release']}"
    )
    commands = [
        {"argv": [*curl, archive, engine_url], "exit_code": 0},
        {
            "argv": ["sha256sum", "--check", f"{work}/engine.sha256"],
            "exit_code": 0,
        },
        {
            "argv": ["tar", "-xJf", archive, "-C", f"{work}/engine"],
            "exit_code": 0,
        },
        {"argv": [binary, "--version"], "exit_code": 0},
        {
            "argv": [
                *curl,
                artifact_manifest,
                f"{artifact_base}/{manifest['artifact']['release_manifest']['name']}",
            ],
            "exit_code": 0,
        },
        {
            "argv": [
                "sha256sum",
                "--check",
                f"{work}/artifact-manifest.sha256",
            ],
            "exit_code": 0,
        },
        {
            "argv": [
                *curl,
                artifact,
                f"{artifact_base}/{manifest['artifact']['name']}",
            ],
            "exit_code": 0,
        },
        {
            "argv": ["sha256sum", "--check", f"{work}/artifact.sha256"],
            "exit_code": 0,
        },
        {
            "argv": [
                binary,
                "run-compiled",
                "--artifact",
                artifact,
            ],
            "exit_code": 0,
            "stdin_sha256": manifest["golden"]["input_sha256"],
        },
    ]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "program": manifest["program"],
        "engine": {
            "repository": release["repository"],
            "release": manifest["engine"]["release"],
            "version": release["version"],
            "target": target,
            "asset": asset["name"],
            "sha256": asset["sha256"],
        },
        "artifact": {
            "repository": manifest["artifact"]["repository"],
            "release": manifest["artifact"]["release"],
            "name": manifest["artifact"]["name"],
            "sha256": manifest["artifact"]["sha256"],
            "manifest_sha256": manifest["artifact"]["release_manifest"]["sha256"],
        },
        "golden": {
            "name": manifest["golden"]["name"],
            "input_path": manifest["golden"]["input_path"],
            "input_sha256": manifest["golden"]["input_sha256"],
            "inputs": golden_inputs,
            "outputs": golden_outputs,
        },
        "commands": commands,
        "timestamp": "2026-07-28T12:34:56Z",
        "workflow": {
            "repository": manifest["workflow"]["repository"],
            "path": manifest["workflow"]["path"],
            "sha": WORKFLOW_SHA,
            "run_id": 123456,
            "run_attempt": 1,
            "event": manifest["workflow"]["event"],
            "ref": manifest["workflow"]["ref"],
        },
    }
    receipt_path = root / manifest["receipt_path"]
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt_path


def _verdict(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    executable_spec: dict,
) -> tuple[dict, dict | None]:
    certify = _load_certify()
    monkeypatch.setattr(certify, "REPO_ROOT", root)
    return certify._executable_verdict(executable_spec)


def test_certificate_executable_fails_closed_without_committed_receipt(
    certificate_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_certify()
    executable_spec = copy.deepcopy(
        certify.PROGRAMS["us-co/snap"]["executable"]
    )

    verdict, evidence = _verdict(
        monkeypatch,
        certificate_root,
        executable_spec,
    )

    assert verdict["mode"] == "computed"
    assert verdict["value"] is False
    assert verdict["receipt_sha256"] is None
    assert any(
        "receipt: file does not exist" in failure
        for failure in verdict["failures"]
    )
    assert "evidence" not in verdict
    assert evidence is None


def test_allowlisted_receipt_holds_only_for_certificate_owned_golden_values(
    certificate_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _write_valid_receipt(certificate_root)
    certify = _load_certify()
    executable_spec = copy.deepcopy(
        certify.PROGRAMS["us-co/snap"]["executable"]
    )

    verdict, evidence = _verdict(
        monkeypatch,
        certificate_root,
        executable_spec,
    )

    assert verdict["mode"] == "computed"
    assert verdict["value"] is True
    assert verdict["failures"] == []
    assert verdict["receipt_sha256"] is not None
    assert verdict["evidence"]["workflow"]["sha"] == WORKFLOW_SHA
    assert evidence == {
        "claim": "executable",
        "mode": "computed",
        "artifact": "certificates/executable/us-co-snap/receipt.json",
        "sha256": verdict["receipt_sha256"],
        "accepted": True,
    }

    mismatched_spec = copy.deepcopy(executable_spec)
    mismatched_spec["expected_outputs"]["snap_net_income"] = 225
    mismatched_verdict, mismatched_evidence = _verdict(
        monkeypatch,
        certificate_root,
        mismatched_spec,
    )

    assert mismatched_verdict["value"] is False
    assert mismatched_verdict["failures"] == [
        "expected_outputs: does not exactly match the hash-bound "
        "golden output expectations"
    ]
    assert mismatched_verdict["receipt_sha256"] is None
    assert "evidence" not in mismatched_verdict
    assert mismatched_evidence is None
