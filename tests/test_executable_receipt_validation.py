"""Focused fail-closed tests for executable receipt validation."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import axiom_oracles.executable_receipt as executable_receipt
from axiom_oracles.executable_receipt import (
    RECEIPT_SCHEMA,
    validate_executable_receipt,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CERTIFICATES = Path("certificates/executable")
WORKFLOW_SHA = "a" * 40


@pytest.fixture
def receipt_root(tmp_path: Path) -> Path:
    shutil.copytree(REPO_ROOT / CERTIFICATES, tmp_path / CERTIFICATES)
    allowlist_path = tmp_path / CERTIFICATES / "workflow-allowlist.json"
    allowlist = json.loads(allowlist_path.read_text())
    allowlist["allowed_workflow_shas"] = [WORKFLOW_SHA]
    allowlist_path.write_text(json.dumps(allowlist, indent=2) + "\n")
    return tmp_path


@pytest.fixture
def valid_receipt(receipt_root: Path) -> dict:
    manifest = json.loads(
        (receipt_root / CERTIFICATES / "us-co-snap/manifest.json").read_text()
    )
    releases = json.loads(
        (receipt_root / CERTIFICATES / "engine-releases.json").read_text()
    )
    release = releases["releases"][manifest["engine"]["release"]]
    asset = release["assets"][manifest["engine"]["target"]]
    golden_inputs = json.loads(
        (receipt_root / manifest["golden"]["input_path"]).read_text()
    )
    golden_outputs = json.loads(
        (receipt_root / manifest["golden"]["outputs_path"]).read_text()
    )["expected"]

    target = manifest["engine"]["target"]
    work = ".executable-receipt-work"
    archive = f"{work}/engine.tar.xz"
    extracted_binary = f"{work}/engine/axiom-rules-engine-{target}/axiom-rules-engine"
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
        {
            "argv": [*curl, archive, engine_url],
            "exit_code": 0,
        },
        {
            "argv": ["sha256sum", "--check", f"{work}/engine.sha256"],
            "exit_code": 0,
        },
        {
            "argv": ["tar", "-xJf", archive, "-C", f"{work}/engine"],
            "exit_code": 0,
        },
        {"argv": [extracted_binary, "--version"], "exit_code": 0},
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
                extracted_binary,
                "run-compiled",
                "--artifact",
                artifact,
            ],
            "exit_code": 0,
            "stdin_sha256": manifest["golden"]["input_sha256"],
        },
    ]
    return {
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
            "repository_id": manifest["workflow"]["repository_id"],
            "path": manifest["workflow"]["path"],
            "sha": WORKFLOW_SHA,
            "source_sha": WORKFLOW_SHA,
            "run_id": 123456,
            "run_attempt": 1,
            "event": manifest["workflow"]["event"],
            "ref": manifest["workflow"]["ref"],
        },
    }


def _write_receipt(root: Path, receipt: dict[str, Any]) -> Path:
    manifest = json.loads(
        (root / CERTIFICATES / "us-co-snap/manifest.json").read_text()
    )
    receipt_path = root / manifest["receipt_path"]
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt_path


def _verified_payload(
    receipt: dict[str, Any],
    receipt_sha256: str,
    *,
    certificate_overrides: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    workflow = receipt["workflow"]
    signer_identity = (
        f"https://github.com/{workflow['repository']}/{workflow['path']}"
        f"@{workflow['ref']}"
    )
    certificate = {
        "subjectAlternativeName": signer_identity,
        "issuer": "https://token.actions.githubusercontent.com",
        "githubWorkflowTrigger": workflow["event"],
        "githubWorkflowSHA": workflow["sha"],
        "githubWorkflowRepository": workflow["repository"],
        "githubWorkflowRef": workflow["ref"],
        "buildSignerURI": signer_identity,
        "buildSignerDigest": workflow["sha"],
        "runnerEnvironment": "github-hosted",
        "sourceRepositoryURI": f"https://github.com/{workflow['repository']}",
        "sourceRepositoryDigest": workflow["source_sha"],
        "sourceRepositoryRef": workflow["ref"],
        "sourceRepositoryIdentifier": workflow["repository_id"],
        "buildConfigURI": signer_identity,
        "buildConfigDigest": workflow["sha"],
        "buildTrigger": workflow["event"],
        "runInvocationURI": (
            f"https://github.com/{workflow['repository']}/actions/runs/"
            f"{workflow['run_id']}/attempts/{workflow['run_attempt']}"
        ),
    }
    certificate.update(certificate_overrides or {})
    return [
        {
            "attestation": {"test": "cryptographic bundle"},
            "verificationResult": {
                "signature": {"certificate": certificate},
                "verifiedTimestamps": [
                    {
                        "type": "Tlog",
                        "timestamp": "2026-07-28T12:35:01Z",
                    }
                ],
                "statement": {
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "subject": [
                        {
                            "name": "receipt.json",
                            "digest": {"sha256": receipt_sha256},
                        }
                    ],
                    "predicate": {},
                },
            },
        }
    ]


def _install_verified_attestation(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    receipt: dict[str, Any],
    *,
    certificate_overrides: dict[str, str] | None = None,
    returncode: int = 0,
) -> list[list[str]]:
    manifest = json.loads(
        (root / CERTIFICATES / "us-co-snap/manifest.json").read_text()
    )
    receipt_path = root / manifest["receipt_path"]
    bundle_path = root / manifest["attestation"]["path"]
    bundle_path.write_text('{"test": "sigstore bundle"}\n')
    receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    payload = _verified_payload(
        receipt,
        receipt_sha256,
        certificate_overrides=certificate_overrides,
    )
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert cwd == root.resolve()
        assert capture_output is True
        assert text is True
        assert check is False
        assert timeout == 30
        assert "GH_TOKEN" not in env
        assert "GITHUB_TOKEN" not in env
        assert command[:3] == ["gh", "attestation", "verify"]
        assert command[3] == str(receipt_path.resolve())
        assert command[command.index("--bundle") + 1] == str(bundle_path.resolve())
        assert command[command.index("--signer-digest") + 1] == WORKFLOW_SHA
        assert command[command.index("--source-digest") + 1] == WORKFLOW_SHA
        stderr = "test attestation refusal" if returncode else ""
        return subprocess.CompletedProcess(
            command,
            returncode,
            json.dumps(payload) if not returncode else "",
            stderr,
        )

    monkeypatch.setattr(executable_receipt.subprocess, "run", fake_run)
    return calls


def _validate(
    receipt_root: Path,
    receipt: dict,
    **kwargs,
):
    return validate_executable_receipt(
        receipt,
        repo_root=receipt_root,
        **kwargs,
    )


def test_valid_receipt_from_committed_output_path(
    receipt_root: Path,
    valid_receipt: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _write_receipt(receipt_root, valid_receipt)
    calls = _install_verified_attestation(
        monkeypatch,
        receipt_root,
        valid_receipt,
    )

    result = validate_executable_receipt(repo_root=receipt_root)

    assert result.valid is True
    assert result.failures == ()
    assert result.receipt_sha256 is not None
    assert result.attestation_sha256 is not None
    assert result.evidence is not None
    assert len(calls) == 1
    assert result.evidence["golden"]["outputs"] == {
        "snap_benefit_amount": 478,
        "snap_net_income": 226,
        "snap_eligible": "holds",
    }


def test_missing_receipt_fails_closed(receipt_root: Path):
    result = validate_executable_receipt(repo_root=receipt_root)

    assert result.valid is False
    assert any("receipt: file does not exist" in item for item in result.failures)
    assert all(str(receipt_root) not in item for item in result.failures)


def test_wrong_engine_checksum_is_rejected(receipt_root: Path, valid_receipt: dict):
    valid_receipt["engine"]["sha256"] = "0" * 64

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "receipt.engine.sha256: checksum is not the pinned asset member "
        "for the declared release and target",
    )


def test_wrong_golden_output_is_rejected(receipt_root: Path, valid_receipt: dict):
    valid_receipt["golden"]["outputs"]["snap_net_income"] = 225

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "receipt.golden.outputs: does not exactly match pinned golden values",
    )


def test_missing_workflow_provenance_is_rejected(
    receipt_root: Path, valid_receipt: dict
):
    del valid_receipt["workflow"]["run_id"]

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == ("receipt.workflow: missing required key 'run_id'",)


def test_hand_authored_nonallowlisted_workflow_sha_is_rejected(
    receipt_root: Path, valid_receipt: dict
):
    valid_receipt["workflow"]["sha"] = "b" * 40
    valid_receipt["workflow"]["source_sha"] = "b" * 40

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "receipt.workflow.sha: is not a member of allowed_workflow_shas",
    )


def test_hand_authored_allowlisted_receipt_without_bundle_is_rejected(
    receipt_root: Path,
    valid_receipt: dict,
):
    _write_receipt(receipt_root, valid_receipt)

    result = validate_executable_receipt(repo_root=receipt_root)

    assert result.valid is False
    assert result.failures == ("attestation: file does not exist",)


def test_parsed_receipt_cannot_bypass_exact_byte_authentication(
    receipt_root: Path,
    valid_receipt: dict,
):
    result = validate_executable_receipt(
        valid_receipt,
        repo_root=receipt_root,
    )

    assert result.valid is False
    assert result.failures == (
        "attestation: receipt must be validated from its exact filesystem bytes",
    )


def test_structurally_invalid_bundle_is_rejected(
    receipt_root: Path,
    valid_receipt: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _write_receipt(receipt_root, valid_receipt)
    _install_verified_attestation(
        monkeypatch,
        receipt_root,
        valid_receipt,
        returncode=1,
    )

    result = validate_executable_receipt(repo_root=receipt_root)

    assert result.valid is False
    assert result.failures == ("attestation: cryptographic verification failed",)


@pytest.mark.skipif(shutil.which("gh") is None, reason="GitHub CLI unavailable")
def test_real_gh_cli_accepts_verifier_flag_combination(
    receipt_root: Path,
    valid_receipt: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    real_run = subprocess.run
    _write_receipt(receipt_root, valid_receipt)
    calls = _install_verified_attestation(
        monkeypatch,
        receipt_root,
        valid_receipt,
    )
    assert validate_executable_receipt(repo_root=receipt_root).valid is True

    environment = dict(os.environ)
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    completed = real_run(
        calls[0],
        cwd=receipt_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    # The synthetic bundle must fail cryptographic parsing, but argument parsing
    # must succeed. This catches mutually exclusive gh identity flags that mocks
    # cannot detect.
    assert completed.returncode != 0
    assert "bundle content could not be parsed" in completed.stderr.lower()


def test_receipt_changed_after_signing_is_rejected(
    receipt_root: Path,
    valid_receipt: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    receipt_path = _write_receipt(receipt_root, valid_receipt)
    _install_verified_attestation(monkeypatch, receipt_root, valid_receipt)
    valid_receipt["timestamp"] = "2026-07-28T12:35:02Z"
    receipt_path.write_text(json.dumps(valid_receipt, indent=2) + "\n")

    result = validate_executable_receipt(repo_root=receipt_root)

    assert result.valid is False
    assert result.failures == (
        "attestation.statement.subject: does not bind the receipt SHA-256",
    )


@pytest.mark.parametrize(
    ("certificate_overrides", "expected_field"),
    [
        (
            {
                "githubWorkflowRepository": "attacker/fork",
                "sourceRepositoryIdentifier": "999",
            },
            "githubWorkflowRepository",
        ),
        (
            {
                "subjectAlternativeName": (
                    "https://github.com/TheAxiomFoundation/axiom-oracles/"
                    ".github/workflows/other.yml@refs/heads/main"
                )
            },
            "subjectAlternativeName",
        ),
        ({"buildSignerDigest": "b" * 40}, "buildSignerDigest"),
        ({"sourceRepositoryRef": "refs/heads/other"}, "sourceRepositoryRef"),
    ],
)
def test_verified_certificate_provenance_must_match_governed_workflow(
    receipt_root: Path,
    valid_receipt: dict,
    monkeypatch: pytest.MonkeyPatch,
    certificate_overrides: dict[str, str],
    expected_field: str,
):
    _write_receipt(receipt_root, valid_receipt)
    _install_verified_attestation(
        monkeypatch,
        receipt_root,
        valid_receipt,
        certificate_overrides=certificate_overrides,
    )

    result = validate_executable_receipt(repo_root=receipt_root)

    assert result.valid is False
    assert any(
        failure.startswith(f"attestation.certificate.{expected_field}:")
        for failure in result.failures
    )


def test_unknown_receipt_key_is_rejected(receipt_root: Path, valid_receipt: dict):
    valid_receipt["attested"] = True

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == ("receipt: unknown key 'attested'",)


def test_inputs_use_type_exact_json_equality(receipt_root: Path, valid_receipt: dict):
    mutated = valid_receipt["golden"]["inputs"]
    integer_input = next(
        item
        for item in mutated["dataset"]["inputs"]
        if item["value"]["kind"] == "integer" and item["value"]["value"] in (0, 1)
    )
    integer_input["value"]["value"] = bool(integer_input["value"]["value"])

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "receipt.golden.inputs: does not exactly match the parsed "
        "hash-bound golden fixture",
    )


def test_raw_fixture_bytes_are_rehashed(receipt_root: Path, valid_receipt: dict):
    fixture = receipt_root / CERTIFICATES / "us-co-snap/golden-request.json"
    fixture.write_bytes(fixture.read_bytes() + b"\n")

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "golden input: raw bytes sha256 does not match manifest.golden.input_sha256",
    )


def test_raw_output_binding_bytes_are_rehashed(receipt_root: Path, valid_receipt: dict):
    bindings = receipt_root / CERTIFICATES / "us-co-snap/golden-outputs.json"
    bindings.write_bytes(bindings.read_bytes() + b"\n")

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "golden output bindings: raw bytes sha256 does not match "
        "manifest.golden.outputs_sha256",
    )


def test_sigstore_trusted_root_bytes_are_rehashed(
    receipt_root: Path,
    valid_receipt: dict,
):
    manifest = json.loads(
        (receipt_root / CERTIFICATES / "us-co-snap/manifest.json").read_text()
    )
    trusted_root = receipt_root / manifest["attestation"]["trusted_root_path"]
    trusted_root.write_bytes(trusted_root.read_bytes() + b"\n")

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "Sigstore trusted root: raw bytes sha256 does not match "
        "manifest.attestation.trusted_root_sha256",
    )


def test_dev_engine_run_command_is_structurally_rejected(
    receipt_root: Path, valid_receipt: dict
):
    valid_receipt["commands"][-1]["argv"][0] = "./target/debug/axiom-rules-engine"

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "receipt.commands[8].argv: does not match the required released-binary "
        "stranger-path command",
    )


def test_run_stdin_must_hash_the_raw_fixture(receipt_root: Path, valid_receipt: dict):
    valid_receipt["commands"][-1]["stdin_sha256"] = "0" * 64

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == (
        "receipt.commands[8].stdin_sha256: does not match the raw golden fixture bytes",
    )


def test_bool_is_not_an_integer_zero_exit(receipt_root: Path, valid_receipt: dict):
    valid_receipt["commands"][0]["exit_code"] = False

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert result.failures == ("receipt.commands[0].exit_code: must be integer 0",)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-07-28 12:34:56Z",
        "2026-07-28T12:34:56+00:00",
        "2026-02-30T12:34:56Z",
    ],
)
def test_timestamp_must_be_valid_rfc3339_utc(
    receipt_root: Path, valid_receipt: dict, timestamp: str
):
    valid_receipt["timestamp"] = timestamp

    result = _validate(receipt_root, valid_receipt)

    assert result.valid is False
    assert len(result.failures) == 1
    assert result.failures[0].startswith("receipt.timestamp:")


def test_explicit_expected_outputs_cannot_override_bindings(
    receipt_root: Path, valid_receipt: dict
):
    expected = copy.deepcopy(valid_receipt["golden"]["outputs"])
    expected["snap_benefit_amount"] = 477

    result = _validate(
        receipt_root,
        valid_receipt,
        expected_outputs=expected,
    )

    assert result.valid is False
    assert result.failures == (
        "expected_outputs: does not exactly match the hash-bound "
        "golden output expectations",
    )


def test_malformed_receipt_returns_failure_instead_of_raising(
    receipt_root: Path, valid_receipt: dict
):
    receipt_path = receipt_root / "malformed-receipt.json"
    receipt_path.write_text('{"schema": "x", "schema": "y"}')

    result = validate_executable_receipt(
        receipt_path,
        repo_root=receipt_root,
    )

    assert result.valid is False
    assert len(result.failures) == 1
    assert "duplicate object key 'schema'" in result.failures[0]
