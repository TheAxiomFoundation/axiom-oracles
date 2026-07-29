"""Fail-closed validation for computed executable receipts.

The receipt is not a statement of facts that this module trusts.  Every stable
field is re-derived from the committed executable manifest, engine release
manifest, golden fixture, output bindings, and workflow allowlist.  The
recorded command sequence is also exact: it must download and verify the
released archive, execute the binary extracted from that archive, download and
verify the published artifact, and feed the committed fixture to that binary.

Malformed or missing input is evidence that the executable premise does not
hold.  The public validator therefore returns ordered failures and never asks a
caller to turn validation exceptions into a verdict.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "axiom_oracles.executable_receipt.v1"
EXECUTABLE_MANIFEST_SCHEMA = "axiom_oracles.executable_manifest.v1"
ENGINE_RELEASE_MANIFEST_SCHEMA = "axiom_oracles.engine_release_manifest.v1"
WORKFLOW_ALLOWLIST_SCHEMA = "axiom_oracles.executable_workflow_allowlist.v1"

DEFAULT_MANIFEST_PATH = Path("certificates/executable/us-co-snap/manifest.json")
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WORKFLOW_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_UTC_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


@dataclass(frozen=True, slots=True)
class ReceiptValidation:
    """The fail-closed result of validating one executable receipt."""

    valid: bool
    failures: tuple[str, ...]
    receipt_sha256: str | None = None
    attestation_sha256: str | None = None
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class _Contract:
    program: str
    receipt_path: str
    attestation_path: str
    attestation_predicate_type: str
    attestation_trusted_root_path: str
    attestation_trusted_root_sha256: str
    engine_repository: str
    engine_release: str
    engine_version: str
    engine_target: str
    engine_asset: str
    engine_sha256: str
    artifact_repository: str
    artifact_release: str
    artifact_manifest_name: str
    artifact_manifest_sha256: str
    artifact_name: str
    artifact_sha256: str
    golden_name: str
    golden_input_path: str
    golden_input_sha256: str
    golden_inputs: Any
    golden_outputs: dict[str, Any]
    workflow_repository: str
    workflow_repository_id: str
    workflow_path: str
    workflow_event: str
    workflow_ref: str
    allowed_workflow_shas: frozenset[str]


def validate_executable_receipt(
    receipt: dict[str, Any] | str | Path | None = None,
    *,
    repo_root: str | Path | None = None,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    expected_outputs: dict[str, Any] | None = None,
) -> ReceiptValidation:
    """Validate a v1 executable receipt against committed trust roots.

    ``receipt`` may be an already-parsed JSON object or a path.  When omitted,
    the receipt is read from the output path declared by the executable
    manifest.  Relative paths are resolved below ``repo_root`` and declared
    paths are not allowed to escape it.

    ``expected_outputs`` is an optional second pin supplied by a certificate
    consumer.  When present, it must exactly equal the expectations in the
    hash-bound output bindings file; it cannot override them.
    """

    failures: list[str] = []
    try:
        return _validate_executable_receipt(
            receipt=receipt,
            repo_root=Path(repo_root) if repo_root is not None else DEFAULT_REPO_ROOT,
            manifest_path=manifest_path,
            expected_outputs=expected_outputs,
            failures=failures,
        )
    except Exception as error:  # pragma: no cover - last-resort fail-closed boundary
        failures.append(
            "validator: unexpected validation failure "
            f"({type(error).__name__}: {error})"
        )
        return ReceiptValidation(valid=False, failures=tuple(failures))


def _validate_executable_receipt(
    *,
    receipt: dict[str, Any] | str | Path | None,
    repo_root: Path,
    manifest_path: str | Path,
    expected_outputs: dict[str, Any] | None,
    failures: list[str],
) -> ReceiptValidation:
    repo_root = repo_root.resolve()
    resolved_manifest = _resolve_path(
        repo_root,
        manifest_path,
        "manifest path",
        failures,
        allow_absolute=True,
    )
    if resolved_manifest is None:
        return ReceiptValidation(False, tuple(failures))

    manifest, _ = _read_json(resolved_manifest, "manifest", failures)
    if manifest is None:
        return ReceiptValidation(False, tuple(failures))

    contract = _build_contract(
        repo_root=repo_root,
        manifest=manifest,
        expected_outputs=expected_outputs,
        failures=failures,
    )
    if contract is None:
        return ReceiptValidation(False, tuple(failures))

    receipt_sha256: str | None = None
    receipt_path: Path | None = None
    if receipt is None:
        receipt_path = _resolve_path(
            repo_root,
            contract.receipt_path,
            "receipt path",
            failures,
            allow_absolute=False,
        )
        if receipt_path is None:
            return ReceiptValidation(False, tuple(failures))
        receipt_value, receipt_sha256 = _read_json(receipt_path, "receipt", failures)
    elif type(receipt) is dict:
        receipt_value = receipt
    elif isinstance(receipt, (str, Path)):
        receipt_path = _resolve_path(
            repo_root,
            receipt,
            "receipt path",
            failures,
            allow_absolute=True,
        )
        if receipt_path is None:
            return ReceiptValidation(False, tuple(failures))
        receipt_value, receipt_sha256 = _read_json(receipt_path, "receipt", failures)
    else:
        failures.append("receipt: must be a JSON object or a filesystem path")
        receipt_value = None

    if receipt_value is None:
        return ReceiptValidation(False, tuple(failures), receipt_sha256=receipt_sha256)

    _validate_receipt(receipt_value, contract, failures)
    if failures:
        return ReceiptValidation(False, tuple(failures), receipt_sha256=receipt_sha256)

    workflow = receipt_value["workflow"]
    attestation_sha256: str | None = None
    if receipt_path is None:
        failures.append(
            "attestation: receipt must be validated from its exact filesystem bytes"
        )
    else:
        attestation_path = _resolve_path(
            repo_root,
            contract.attestation_path,
            "attestation path",
            failures,
            allow_absolute=False,
        )
        if attestation_path is not None:
            attestation_sha256 = _verify_attestation(
                receipt_path=receipt_path,
                receipt_sha256=receipt_sha256,
                attestation_path=attestation_path,
                contract=contract,
                workflow=workflow,
                repo_root=repo_root,
                failures=failures,
            )
    if failures:
        return ReceiptValidation(
            False,
            tuple(failures),
            receipt_sha256=receipt_sha256,
            attestation_sha256=attestation_sha256,
        )

    evidence = {
        "schema": RECEIPT_SCHEMA,
        "program": contract.program,
        "engine": {
            "repository": contract.engine_repository,
            "release": contract.engine_release,
            "version": contract.engine_version,
            "target": contract.engine_target,
            "asset": contract.engine_asset,
            "sha256": contract.engine_sha256,
        },
        "artifact": {
            "repository": contract.artifact_repository,
            "release": contract.artifact_release,
            "name": contract.artifact_name,
            "sha256": contract.artifact_sha256,
            "manifest_sha256": contract.artifact_manifest_sha256,
        },
        "golden": {
            "name": contract.golden_name,
            "input_sha256": contract.golden_input_sha256,
            "outputs": dict(contract.golden_outputs),
        },
        "timestamp": receipt_value["timestamp"],
        "attestation": {
            "path": contract.attestation_path,
            "sha256": attestation_sha256,
            "predicate_type": contract.attestation_predicate_type,
            "trusted_root_path": contract.attestation_trusted_root_path,
            "trusted_root_sha256": contract.attestation_trusted_root_sha256,
        },
        "workflow": {
            "repository": workflow["repository"],
            "repository_id": workflow["repository_id"],
            "path": workflow["path"],
            "sha": workflow["sha"],
            "source_sha": workflow["source_sha"],
            "run_id": workflow["run_id"],
            "run_attempt": workflow["run_attempt"],
            "event": workflow["event"],
            "ref": workflow["ref"],
        },
    }
    return ReceiptValidation(
        True,
        (),
        receipt_sha256=receipt_sha256,
        attestation_sha256=attestation_sha256,
        evidence=evidence,
    )


def _build_contract(
    *,
    repo_root: Path,
    manifest: Any,
    expected_outputs: dict[str, Any] | None,
    failures: list[str],
) -> _Contract | None:
    start = len(failures)
    manifest_object = _exact_object(
        manifest,
        (
            "schema",
            "program",
            "receipt_path",
            "attestation",
            "engine",
            "artifact",
            "golden",
            "workflow",
        ),
        (),
        "manifest",
        failures,
    )
    if manifest_object is None:
        return None

    _literal_string(
        manifest_object,
        "schema",
        EXECUTABLE_MANIFEST_SCHEMA,
        "manifest.schema",
        failures,
    )
    program = _string_field(manifest_object, "program", "manifest.program", failures)
    receipt_path = _string_field(
        manifest_object, "receipt_path", "manifest.receipt_path", failures
    )
    attestation = _exact_object(
        manifest_object.get("attestation"),
        ("path", "predicate_type", "trusted_root_path", "trusted_root_sha256"),
        (),
        "manifest.attestation",
        failures,
    )

    engine = _exact_object(
        manifest_object.get("engine"),
        ("release_manifest", "release", "target"),
        (),
        "manifest.engine",
        failures,
    )
    artifact = _exact_object(
        manifest_object.get("artifact"),
        (
            "repository",
            "release",
            "release_manifest",
            "name",
            "sha256",
        ),
        (),
        "manifest.artifact",
        failures,
    )
    golden = _exact_object(
        manifest_object.get("golden"),
        (
            "name",
            "input_path",
            "input_sha256",
            "outputs_path",
            "outputs_sha256",
        ),
        (),
        "manifest.golden",
        failures,
    )
    workflow = _exact_object(
        manifest_object.get("workflow"),
        ("allowlist", "repository", "repository_id", "path", "event", "ref"),
        (),
        "manifest.workflow",
        failures,
    )
    if (
        attestation is None
        or engine is None
        or artifact is None
        or golden is None
        or workflow is None
    ):
        return None

    attestation_path = _string_field(
        attestation,
        "path",
        "manifest.attestation.path",
        failures,
    )
    attestation_predicate_type = _string_field(
        attestation,
        "predicate_type",
        "manifest.attestation.predicate_type",
        failures,
    )
    if (
        attestation_predicate_type is not None
        and attestation_predicate_type != "https://slsa.dev/provenance/v1"
    ):
        failures.append(
            "manifest.attestation.predicate_type: only SLSA provenance v1 "
            "is accepted"
        )
    attestation_trusted_root_path = _string_field(
        attestation,
        "trusted_root_path",
        "manifest.attestation.trusted_root_path",
        failures,
    )
    attestation_trusted_root_sha256 = _sha_field(
        attestation,
        "trusted_root_sha256",
        "manifest.attestation.trusted_root_sha256",
        failures,
    )

    engine_manifest_path = _string_field(
        engine,
        "release_manifest",
        "manifest.engine.release_manifest",
        failures,
    )
    engine_release = _string_field(
        engine, "release", "manifest.engine.release", failures
    )
    engine_target = _string_field(engine, "target", "manifest.engine.target", failures)

    artifact_repository = _string_field(
        artifact, "repository", "manifest.artifact.repository", failures
    )
    artifact_release = _string_field(
        artifact, "release", "manifest.artifact.release", failures
    )
    artifact_name = _string_field(artifact, "name", "manifest.artifact.name", failures)
    artifact_sha256 = _sha_field(
        artifact, "sha256", "manifest.artifact.sha256", failures
    )
    artifact_release_manifest = _exact_object(
        artifact.get("release_manifest"),
        ("name", "sha256"),
        (),
        "manifest.artifact.release_manifest",
        failures,
    )
    artifact_manifest_name: str | None = None
    artifact_manifest_sha256: str | None = None
    if artifact_release_manifest is not None:
        artifact_manifest_name = _string_field(
            artifact_release_manifest,
            "name",
            "manifest.artifact.release_manifest.name",
            failures,
        )
        artifact_manifest_sha256 = _sha_field(
            artifact_release_manifest,
            "sha256",
            "manifest.artifact.release_manifest.sha256",
            failures,
        )

    golden_name = _string_field(golden, "name", "manifest.golden.name", failures)
    golden_input_path = _string_field(
        golden, "input_path", "manifest.golden.input_path", failures
    )
    golden_input_sha256 = _sha_field(
        golden, "input_sha256", "manifest.golden.input_sha256", failures
    )
    golden_outputs_path = _string_field(
        golden, "outputs_path", "manifest.golden.outputs_path", failures
    )
    golden_outputs_sha256 = _sha_field(
        golden, "outputs_sha256", "manifest.golden.outputs_sha256", failures
    )

    workflow_allowlist_path = _string_field(
        workflow, "allowlist", "manifest.workflow.allowlist", failures
    )
    workflow_repository = _string_field(
        workflow, "repository", "manifest.workflow.repository", failures
    )
    workflow_repository_id = _decimal_string_field(
        workflow,
        "repository_id",
        "manifest.workflow.repository_id",
        failures,
    )
    workflow_path = _string_field(workflow, "path", "manifest.workflow.path", failures)
    workflow_event = _string_field(
        workflow, "event", "manifest.workflow.event", failures
    )
    workflow_ref = _string_field(workflow, "ref", "manifest.workflow.ref", failures)

    declared_paths = (
        (receipt_path, "manifest.receipt_path"),
        (attestation_path, "manifest.attestation.path"),
        (
            attestation_trusted_root_path,
            "manifest.attestation.trusted_root_path",
        ),
        (engine_manifest_path, "manifest.engine.release_manifest"),
        (golden_input_path, "manifest.golden.input_path"),
        (golden_outputs_path, "manifest.golden.outputs_path"),
        (workflow_allowlist_path, "manifest.workflow.allowlist"),
    )
    for declared, label in declared_paths:
        if declared is not None:
            _resolve_path(
                repo_root,
                declared,
                label,
                failures,
                allow_absolute=False,
            )

    engine_manifest = _load_declared_json(
        repo_root,
        engine_manifest_path,
        "engine release manifest",
        failures,
    )
    engine_repository: str | None = None
    engine_version: str | None = None
    engine_asset: str | None = None
    engine_sha256: str | None = None
    if engine_manifest is not None:
        (
            engine_repository,
            engine_version,
            engine_asset,
            engine_sha256,
        ) = _validate_engine_manifest(
            engine_manifest,
            engine_release,
            engine_target,
            failures,
        )

    _, trusted_root_digest = _load_declared_json_with_digest(
        repo_root,
        attestation_trusted_root_path,
        "Sigstore trusted root",
        failures,
    )
    if (
        trusted_root_digest is not None
        and attestation_trusted_root_sha256 is not None
        and trusted_root_digest != attestation_trusted_root_sha256
    ):
        failures.append(
            "Sigstore trusted root: raw bytes sha256 does not match "
            "manifest.attestation.trusted_root_sha256"
        )

    golden_inputs = None
    input_document, input_digest = _load_declared_json_with_digest(
        repo_root,
        golden_input_path,
        "golden input",
        failures,
    )
    if input_digest is not None and golden_input_sha256 is not None:
        if input_digest != golden_input_sha256:
            failures.append(
                "golden input: raw bytes sha256 does not match "
                "manifest.golden.input_sha256"
            )
    if input_document is not None:
        golden_inputs = input_document

    output_document, output_digest = _load_declared_json_with_digest(
        repo_root,
        golden_outputs_path,
        "golden output bindings",
        failures,
    )
    if output_digest is not None and golden_outputs_sha256 is not None:
        if output_digest != golden_outputs_sha256:
            failures.append(
                "golden output bindings: raw bytes sha256 does not match "
                "manifest.golden.outputs_sha256"
            )
    pinned_outputs = _validate_output_bindings(
        output_document, expected_outputs, failures
    )

    allowlist_document = _load_declared_json(
        repo_root,
        workflow_allowlist_path,
        "workflow allowlist",
        failures,
    )
    allowed_workflow_shas: frozenset[str] | None = None
    if allowlist_document is not None:
        allowed_workflow_shas = _validate_workflow_allowlist(
            allowlist_document,
            workflow_repository,
            workflow_path,
            failures,
        )

    required_values = (
        program,
        receipt_path,
        attestation_path,
        attestation_predicate_type,
        attestation_trusted_root_path,
        attestation_trusted_root_sha256,
        engine_release,
        engine_target,
        engine_repository,
        engine_version,
        engine_asset,
        engine_sha256,
        artifact_repository,
        artifact_release,
        artifact_manifest_name,
        artifact_manifest_sha256,
        artifact_name,
        artifact_sha256,
        golden_name,
        golden_input_path,
        golden_input_sha256,
        golden_inputs,
        pinned_outputs,
        workflow_repository,
        workflow_repository_id,
        workflow_path,
        workflow_event,
        workflow_ref,
        allowed_workflow_shas,
    )
    if len(failures) != start or any(value is None for value in required_values):
        return None

    return _Contract(
        program=program,
        receipt_path=receipt_path,
        attestation_path=attestation_path,
        attestation_predicate_type=attestation_predicate_type,
        attestation_trusted_root_path=attestation_trusted_root_path,
        attestation_trusted_root_sha256=attestation_trusted_root_sha256,
        engine_repository=engine_repository,
        engine_release=engine_release,
        engine_version=engine_version,
        engine_target=engine_target,
        engine_asset=engine_asset,
        engine_sha256=engine_sha256,
        artifact_repository=artifact_repository,
        artifact_release=artifact_release,
        artifact_manifest_name=artifact_manifest_name,
        artifact_manifest_sha256=artifact_manifest_sha256,
        artifact_name=artifact_name,
        artifact_sha256=artifact_sha256,
        golden_name=golden_name,
        golden_input_path=golden_input_path,
        golden_input_sha256=golden_input_sha256,
        golden_inputs=golden_inputs,
        golden_outputs=pinned_outputs,
        workflow_repository=workflow_repository,
        workflow_repository_id=workflow_repository_id,
        workflow_path=workflow_path,
        workflow_event=workflow_event,
        workflow_ref=workflow_ref,
        allowed_workflow_shas=allowed_workflow_shas,
    )


def _validate_engine_manifest(
    document: Any,
    release_name: str | None,
    target_name: str | None,
    failures: list[str],
) -> tuple[str | None, str | None, str | None, str | None]:
    root = _exact_object(
        document,
        ("schema", "releases"),
        (),
        "engine release manifest",
        failures,
    )
    if root is None:
        return None, None, None, None
    _literal_string(
        root,
        "schema",
        ENGINE_RELEASE_MANIFEST_SCHEMA,
        "engine release manifest.schema",
        failures,
    )
    releases = root.get("releases")
    if type(releases) is not dict:
        failures.append("engine release manifest.releases: must be a JSON object")
        return None, None, None, None
    if release_name is None:
        return None, None, None, None
    release = releases.get(release_name)
    release_object = _exact_object(
        release,
        (
            "repository",
            "tag_commit",
            "version",
            "dist_manifest_sha256",
            "sha256_sum_sha256",
            "assets",
        ),
        (),
        f"engine release manifest.releases.{release_name}",
        failures,
    )
    if release_object is None:
        if release is None:
            failures.append(
                f"engine release manifest: release {release_name!r} is not pinned"
            )
        return None, None, None, None

    repository = _string_field(
        release_object,
        "repository",
        f"engine release manifest.releases.{release_name}.repository",
        failures,
    )
    version = _string_field(
        release_object,
        "version",
        f"engine release manifest.releases.{release_name}.version",
        failures,
    )
    _git_sha_field(
        release_object,
        "tag_commit",
        f"engine release manifest.releases.{release_name}.tag_commit",
        failures,
    )
    _sha_field(
        release_object,
        "dist_manifest_sha256",
        f"engine release manifest.releases.{release_name}.dist_manifest_sha256",
        failures,
    )
    _sha_field(
        release_object,
        "sha256_sum_sha256",
        f"engine release manifest.releases.{release_name}.sha256_sum_sha256",
        failures,
    )
    assets = release_object.get("assets")
    if type(assets) is not dict:
        failures.append(
            f"engine release manifest.releases.{release_name}.assets: "
            "must be a JSON object"
        )
        return repository, version, None, None
    if target_name is None:
        return repository, version, None, None
    asset = assets.get(target_name)
    asset_object = _exact_object(
        asset,
        ("name", "sha256"),
        (),
        (f"engine release manifest.releases.{release_name}.assets.{target_name}"),
        failures,
    )
    if asset_object is None:
        if asset is None:
            failures.append(
                "engine release manifest: target "
                f"{target_name!r} is not pinned under release {release_name!r}"
            )
        return repository, version, None, None
    asset_name = _string_field(
        asset_object,
        "name",
        (f"engine release manifest.releases.{release_name}.assets.{target_name}.name"),
        failures,
    )
    asset_sha256 = _sha_field(
        asset_object,
        "sha256",
        (
            f"engine release manifest.releases.{release_name}."
            f"assets.{target_name}.sha256"
        ),
        failures,
    )
    return repository, version, asset_name, asset_sha256


def _validate_output_bindings(
    document: Any,
    explicit_expected: dict[str, Any] | None,
    failures: list[str],
) -> dict[str, Any] | None:
    output_root = _exact_object(
        document,
        ("description", "bindings"),
        ("expected",),
        "golden output bindings",
        failures,
    )
    if output_root is None:
        return None
    _string_field(
        output_root,
        "description",
        "golden output bindings.description",
        failures,
    )
    bindings = output_root.get("bindings")
    if type(bindings) is not dict:
        failures.append("golden output bindings.bindings: must be a JSON object")
        bindings = None
    else:
        for name, legal_id in bindings.items():
            if type(name) is not str or not name:
                failures.append(
                    "golden output bindings.bindings: keys must be nonempty strings"
                )
                break
            if type(legal_id) is not str or not legal_id:
                failures.append(
                    f"golden output bindings.bindings.{name}: must be a nonempty string"
                )

    bound_expected = output_root.get("expected")
    if bound_expected is not None and type(bound_expected) is not dict:
        failures.append("golden output bindings.expected: must be a JSON object")
        bound_expected = None
    if explicit_expected is not None and type(explicit_expected) is not dict:
        failures.append("expected_outputs: must be a JSON object")
        explicit_expected = None
    if bound_expected is None and explicit_expected is None:
        failures.append("golden output bindings: expected outputs are not pinned")
        return None
    if (
        bound_expected is not None
        and explicit_expected is not None
        and not _json_exact_equal(bound_expected, explicit_expected)
    ):
        failures.append(
            "expected_outputs: does not exactly match the hash-bound "
            "golden output expectations"
        )
    pinned = explicit_expected if explicit_expected is not None else bound_expected
    if type(bindings) is dict and type(pinned) is dict:
        if set(bindings) != set(pinned):
            failures.append(
                "golden output bindings: binding keys and expected output keys "
                "must match exactly"
            )
    return dict(pinned) if type(pinned) is dict else None


def _validate_workflow_allowlist(
    document: Any,
    expected_repository: str | None,
    expected_path: str | None,
    failures: list[str],
) -> frozenset[str] | None:
    root = _exact_object(
        document,
        ("schema", "repository", "path", "allowed_workflow_shas"),
        (),
        "workflow allowlist",
        failures,
    )
    if root is None:
        return None
    _literal_string(
        root,
        "schema",
        WORKFLOW_ALLOWLIST_SCHEMA,
        "workflow allowlist.schema",
        failures,
    )
    repository = _string_field(
        root, "repository", "workflow allowlist.repository", failures
    )
    path = _string_field(root, "path", "workflow allowlist.path", failures)
    if (
        repository is not None
        and expected_repository is not None
        and repository != expected_repository
    ):
        failures.append(
            "workflow allowlist.repository: does not match manifest.workflow.repository"
        )
    if path is not None and expected_path is not None and path != expected_path:
        failures.append(
            "workflow allowlist.path: does not match manifest.workflow.path"
        )
    raw_shas = root.get("allowed_workflow_shas")
    if type(raw_shas) is not list:
        failures.append(
            "workflow allowlist.allowed_workflow_shas: must be a JSON array"
        )
        return None
    allowed: list[str] = []
    for index, value in enumerate(raw_shas):
        if type(value) is not str or _WORKFLOW_SHA_RE.fullmatch(value) is None:
            failures.append(
                "workflow allowlist.allowed_workflow_shas"
                f"[{index}]: must be a full lowercase 40-hex commit SHA"
            )
            continue
        allowed.append(value)
    if len(set(allowed)) != len(allowed):
        failures.append(
            "workflow allowlist.allowed_workflow_shas: duplicate SHAs are not allowed"
        )
    return frozenset(allowed)


def _validate_receipt(
    receipt: Any,
    contract: _Contract,
    failures: list[str],
) -> None:
    root = _exact_object(
        receipt,
        (
            "schema",
            "program",
            "engine",
            "artifact",
            "golden",
            "commands",
            "timestamp",
            "workflow",
        ),
        (),
        "receipt",
        failures,
    )
    if root is None:
        return
    _literal_string(root, "schema", RECEIPT_SCHEMA, "receipt.schema", failures)
    _matching_string(root, "program", contract.program, "receipt.program", failures)

    engine = _exact_object(
        root.get("engine"),
        ("repository", "release", "version", "target", "asset", "sha256"),
        (),
        "receipt.engine",
        failures,
    )
    if engine is not None:
        _matching_string(
            engine,
            "repository",
            contract.engine_repository,
            "receipt.engine.repository",
            failures,
        )
        _matching_string(
            engine,
            "release",
            contract.engine_release,
            "receipt.engine.release",
            failures,
        )
        _matching_string(
            engine,
            "version",
            contract.engine_version,
            "receipt.engine.version",
            failures,
        )
        _matching_string(
            engine,
            "target",
            contract.engine_target,
            "receipt.engine.target",
            failures,
        )
        _matching_string(
            engine,
            "asset",
            contract.engine_asset,
            "receipt.engine.asset",
            failures,
        )
        checksum = _sha_field(engine, "sha256", "receipt.engine.sha256", failures)
        if checksum is not None and checksum != contract.engine_sha256:
            failures.append(
                "receipt.engine.sha256: checksum is not the pinned asset member "
                "for the declared release and target"
            )

    artifact = _exact_object(
        root.get("artifact"),
        (
            "repository",
            "release",
            "name",
            "sha256",
            "manifest_sha256",
        ),
        (),
        "receipt.artifact",
        failures,
    )
    if artifact is not None:
        _matching_string(
            artifact,
            "repository",
            contract.artifact_repository,
            "receipt.artifact.repository",
            failures,
        )
        _matching_string(
            artifact,
            "release",
            contract.artifact_release,
            "receipt.artifact.release",
            failures,
        )
        _matching_string(
            artifact,
            "name",
            contract.artifact_name,
            "receipt.artifact.name",
            failures,
        )
        _matching_sha(
            artifact,
            "sha256",
            contract.artifact_sha256,
            "receipt.artifact.sha256",
            failures,
        )
        _matching_sha(
            artifact,
            "manifest_sha256",
            contract.artifact_manifest_sha256,
            "receipt.artifact.manifest_sha256",
            failures,
        )

    golden = _exact_object(
        root.get("golden"),
        ("name", "input_path", "input_sha256", "inputs", "outputs"),
        (),
        "receipt.golden",
        failures,
    )
    if golden is not None:
        _matching_string(
            golden,
            "name",
            contract.golden_name,
            "receipt.golden.name",
            failures,
        )
        _matching_string(
            golden,
            "input_path",
            contract.golden_input_path,
            "receipt.golden.input_path",
            failures,
        )
        _matching_sha(
            golden,
            "input_sha256",
            contract.golden_input_sha256,
            "receipt.golden.input_sha256",
            failures,
        )
        if "inputs" in golden and not _json_exact_equal(
            golden["inputs"], contract.golden_inputs
        ):
            failures.append(
                "receipt.golden.inputs: does not exactly match the parsed "
                "hash-bound golden fixture"
            )
        if "outputs" in golden and not _json_exact_equal(
            golden["outputs"], contract.golden_outputs
        ):
            failures.append(
                "receipt.golden.outputs: does not exactly match pinned golden values"
            )

    if "commands" in root:
        _validate_commands(root["commands"], contract, failures)
    if "timestamp" in root:
        _validate_timestamp(root["timestamp"], failures)
    if "workflow" in root:
        _validate_receipt_workflow(root["workflow"], contract, failures)


def _validate_commands(
    commands: Any,
    contract: _Contract,
    failures: list[str],
) -> None:
    if type(commands) is not list:
        failures.append("receipt.commands: must be a JSON array")
        return
    expected = _expected_commands(contract)
    if len(commands) != len(expected):
        failures.append(
            f"receipt.commands: expected exactly {len(expected)} commands, "
            f"got {len(commands)}"
        )
    for index, raw_command in enumerate(commands):
        label = f"receipt.commands[{index}]"
        command = _exact_object(
            raw_command,
            ("argv", "exit_code"),
            ("stdin_sha256",),
            label,
            failures,
        )
        if command is None:
            continue
        argv = command.get("argv")
        valid_argv = True
        if type(argv) is not list or not argv:
            failures.append(f"{label}.argv: must be a nonempty JSON array")
            valid_argv = False
        elif any(type(argument) is not str for argument in argv):
            failures.append(f"{label}.argv: every argument must be a string")
            valid_argv = False
        if index >= len(expected):
            failures.append(f"{label}: unexpected command")
        elif valid_argv and argv != expected[index]:
            failures.append(
                f"{label}.argv: does not match the required released-binary "
                "stranger-path command"
            )

        exit_code = command.get("exit_code")
        if type(exit_code) is not int:
            failures.append(f"{label}.exit_code: must be integer 0")
        elif exit_code != 0:
            failures.append(f"{label}.exit_code: must be 0")

        if index == len(expected) - 1:
            if "stdin_sha256" not in command:
                failures.append(f"{label}: missing required key 'stdin_sha256'")
            else:
                stdin_sha256 = _sha_field(
                    command, "stdin_sha256", f"{label}.stdin_sha256", failures
                )
                if (
                    stdin_sha256 is not None
                    and stdin_sha256 != contract.golden_input_sha256
                ):
                    failures.append(
                        f"{label}.stdin_sha256: does not match the raw golden "
                        "fixture bytes"
                    )
        elif "stdin_sha256" in command:
            failures.append(
                f"{label}: stdin_sha256 is only allowed on the engine run command"
            )


def _expected_commands(contract: _Contract) -> list[list[str]]:
    work = ".executable-receipt-work"
    archive = f"{work}/engine.tar.xz"
    engine_checksum = f"{work}/engine.sha256"
    extract_directory = f"{work}/engine"
    binary = (
        f"{extract_directory}/axiom-rules-engine-{contract.engine_target}/"
        "axiom-rules-engine"
    )
    artifact_manifest = f"{work}/artifact-manifest.json"
    artifact_manifest_checksum = f"{work}/artifact-manifest.sha256"
    artifact = f"{work}/{contract.artifact_name}"
    artifact_checksum = f"{work}/artifact.sha256"

    engine_url = (
        f"https://github.com/{contract.engine_repository}/releases/download/"
        f"{contract.engine_release}/{contract.engine_asset}"
    )
    artifact_manifest_url = (
        f"https://github.com/{contract.artifact_repository}/releases/download/"
        f"{contract.artifact_release}/{contract.artifact_manifest_name}"
    )
    artifact_url = (
        f"https://github.com/{contract.artifact_repository}/releases/download/"
        f"{contract.artifact_release}/{contract.artifact_name}"
    )
    curl_prefix = [
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
    return [
        [*curl_prefix, archive, engine_url],
        ["sha256sum", "--check", engine_checksum],
        ["tar", "-xJf", archive, "-C", extract_directory],
        [binary, "--version"],
        [*curl_prefix, artifact_manifest, artifact_manifest_url],
        ["sha256sum", "--check", artifact_manifest_checksum],
        [*curl_prefix, artifact, artifact_url],
        ["sha256sum", "--check", artifact_checksum],
        [binary, "run-compiled", "--artifact", artifact],
    ]


def _validate_timestamp(value: Any, failures: list[str]) -> None:
    if type(value) is not str or _UTC_RFC3339_RE.fullmatch(value) is None:
        failures.append(
            "receipt.timestamp: must be an RFC3339 UTC timestamp ending in Z"
        )
        return
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        failures.append("receipt.timestamp: is not a valid calendar timestamp")
        return
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        failures.append("receipt.timestamp: must be UTC")


def _validate_receipt_workflow(
    workflow: Any,
    contract: _Contract,
    failures: list[str],
) -> None:
    root = _exact_object(
        workflow,
        (
            "repository",
            "repository_id",
            "path",
            "sha",
            "source_sha",
            "run_id",
            "run_attempt",
            "event",
            "ref",
        ),
        (),
        "receipt.workflow",
        failures,
    )
    if root is None:
        return
    _matching_string(
        root,
        "repository",
        contract.workflow_repository,
        "receipt.workflow.repository",
        failures,
    )
    repository_id = _decimal_string_field(
        root,
        "repository_id",
        "receipt.workflow.repository_id",
        failures,
    )
    if (
        repository_id is not None
        and repository_id != contract.workflow_repository_id
    ):
        failures.append(
            "receipt.workflow.repository_id: does not match the committed manifest"
        )
    _matching_string(
        root,
        "path",
        contract.workflow_path,
        "receipt.workflow.path",
        failures,
    )
    workflow_sha = _git_sha_field(root, "sha", "receipt.workflow.sha", failures)
    if workflow_sha is not None and workflow_sha not in contract.allowed_workflow_shas:
        failures.append(
            "receipt.workflow.sha: is not a member of allowed_workflow_shas"
        )
    source_sha = _git_sha_field(
        root,
        "source_sha",
        "receipt.workflow.source_sha",
        failures,
    )
    if (
        workflow_sha is not None
        and source_sha is not None
        and source_sha != workflow_sha
    ):
        failures.append(
            "receipt.workflow.source_sha: must equal the governed workflow SHA"
        )
    _positive_int_field(root, "run_id", "receipt.workflow.run_id", failures)
    _positive_int_field(root, "run_attempt", "receipt.workflow.run_attempt", failures)
    _matching_string(
        root,
        "event",
        contract.workflow_event,
        "receipt.workflow.event",
        failures,
    )
    _matching_string(
        root,
        "ref",
        contract.workflow_ref,
        "receipt.workflow.ref",
        failures,
    )


def _verify_attestation(
    *,
    receipt_path: Path,
    receipt_sha256: str | None,
    attestation_path: Path,
    contract: _Contract,
    workflow: dict[str, Any],
    repo_root: Path,
    failures: list[str],
) -> str | None:
    """Cryptographically bind the receipt bytes to the governed Actions run."""

    try:
        bundle_bytes = attestation_path.read_bytes()
    except FileNotFoundError:
        failures.append("attestation: file does not exist")
        return None
    except OSError as error:
        failures.append(f"attestation: cannot read file (errno {error.errno})")
        return None
    attestation_sha256 = hashlib.sha256(bundle_bytes).hexdigest()
    if not bundle_bytes:
        failures.append("attestation: file is empty")
        return attestation_sha256
    if receipt_sha256 is None:
        failures.append("attestation: receipt bytes have no SHA-256")
        return attestation_sha256

    trusted_root_path = _resolve_path(
        repo_root,
        contract.attestation_trusted_root_path,
        "Sigstore trusted root path",
        failures,
        allow_absolute=False,
    )
    if trusted_root_path is None:
        return attestation_sha256

    signer_identity = (
        f"https://github.com/{contract.workflow_repository}/"
        f"{contract.workflow_path}@{contract.workflow_ref}"
    )
    command = [
        "gh",
        "attestation",
        "verify",
        str(receipt_path),
        "--repo",
        contract.workflow_repository,
        "--bundle",
        str(attestation_path),
        "--custom-trusted-root",
        str(trusted_root_path),
        "--predicate-type",
        contract.attestation_predicate_type,
        "--cert-identity",
        signer_identity,
        "--cert-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "--signer-digest",
        workflow["sha"],
        "--source-ref",
        contract.workflow_ref,
        "--source-digest",
        workflow["source_sha"],
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]
    environment = dict(os.environ)
    for credential in ("GH_TOKEN", "GITHUB_TOKEN"):
        environment.pop(credential, None)
    environment["GH_NO_UPDATE_NOTIFIER"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        failures.append("attestation: GitHub CLI is unavailable")
        return attestation_sha256
    except subprocess.TimeoutExpired:
        failures.append("attestation: cryptographic verification timed out")
        return attestation_sha256
    except OSError as error:
        failures.append(
            f"attestation: GitHub CLI could not run (errno {error.errno})"
        )
        return attestation_sha256

    if completed.returncode != 0:
        failures.append("attestation: cryptographic verification failed")
        return attestation_sha256
    try:
        payload = json.loads(
            completed.stdout,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_json_constant,
        )
    except (json.JSONDecodeError, ValueError):
        failures.append("attestation: verifier output is not strict JSON")
        return attestation_sha256
    _validate_verified_attestation(
        payload=payload,
        receipt_sha256=receipt_sha256,
        contract=contract,
        workflow=workflow,
        failures=failures,
    )
    return attestation_sha256


def _validate_verified_attestation(
    *,
    payload: Any,
    receipt_sha256: str,
    contract: _Contract,
    workflow: dict[str, Any],
    failures: list[str],
) -> None:
    """Re-check authenticated certificate fields from ``gh --format json``."""

    if type(payload) is not list or len(payload) != 1:
        failures.append(
            "attestation: verifier must return exactly one verified attestation"
        )
        return
    result = payload[0]
    if type(result) is not dict:
        failures.append("attestation: verified result must be a JSON object")
        return
    verification = result.get("verificationResult")
    if type(verification) is not dict:
        failures.append("attestation: verified result is missing verificationResult")
        return
    signature = verification.get("signature")
    certificate = (
        signature.get("certificate") if type(signature) is dict else None
    )
    if type(certificate) is not dict:
        failures.append("attestation: verified result is missing its certificate")
        return

    signer_identity = (
        f"https://github.com/{contract.workflow_repository}/"
        f"{contract.workflow_path}@{contract.workflow_ref}"
    )
    expected_certificate = {
        "subjectAlternativeName": signer_identity,
        "issuer": "https://token.actions.githubusercontent.com",
        "githubWorkflowTrigger": contract.workflow_event,
        "githubWorkflowSHA": workflow["sha"],
        "githubWorkflowRepository": contract.workflow_repository,
        "githubWorkflowRef": contract.workflow_ref,
        "buildSignerURI": signer_identity,
        "buildSignerDigest": workflow["sha"],
        "runnerEnvironment": "github-hosted",
        "sourceRepositoryURI": (
            f"https://github.com/{contract.workflow_repository}"
        ),
        "sourceRepositoryDigest": workflow["source_sha"],
        "sourceRepositoryRef": contract.workflow_ref,
        "sourceRepositoryIdentifier": contract.workflow_repository_id,
        "buildConfigURI": signer_identity,
        "buildConfigDigest": workflow["sha"],
        "buildTrigger": contract.workflow_event,
        "runInvocationURI": (
            f"https://github.com/{contract.workflow_repository}/actions/runs/"
            f"{workflow['run_id']}/attempts/{workflow['run_attempt']}"
        ),
    }
    for field, expected in expected_certificate.items():
        if certificate.get(field) != expected:
            failures.append(
                f"attestation.certificate.{field}: does not match governed "
                "workflow provenance"
            )

    verified_timestamps = verification.get("verifiedTimestamps")
    if type(verified_timestamps) is not list or not verified_timestamps:
        failures.append("attestation: has no verified transparency timestamp")

    statement = verification.get("statement")
    if type(statement) is not dict:
        failures.append("attestation: verified result is missing its statement")
        return
    if statement.get("predicateType") != contract.attestation_predicate_type:
        failures.append("attestation.statement.predicateType: is not pinned")
    subjects = statement.get("subject")
    if type(subjects) is not list or len(subjects) != 1:
        failures.append("attestation.statement.subject: must contain one subject")
        return
    subject = subjects[0]
    digest = subject.get("digest") if type(subject) is dict else None
    if type(digest) is not dict or digest.get("sha256") != receipt_sha256:
        failures.append(
            "attestation.statement.subject: does not bind the receipt SHA-256"
        )


def _resolve_path(
    repo_root: Path,
    raw_path: str | Path,
    label: str,
    failures: list[str],
    *,
    allow_absolute: bool,
) -> Path | None:
    try:
        path = Path(raw_path)
    except TypeError:
        failures.append(f"{label}: must be a filesystem path")
        return None
    if path.is_absolute():
        if not allow_absolute:
            failures.append(f"{label}: declared path must be repository-relative")
            return None
        candidate = path.resolve()
    else:
        candidate = (repo_root / path).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        failures.append(f"{label}: path escapes the repository root")
        return None
    return candidate


def _load_declared_json(
    repo_root: Path,
    raw_path: str | None,
    label: str,
    failures: list[str],
) -> Any:
    document, _ = _load_declared_json_with_digest(repo_root, raw_path, label, failures)
    return document


def _load_declared_json_with_digest(
    repo_root: Path,
    raw_path: str | None,
    label: str,
    failures: list[str],
) -> tuple[Any, str | None]:
    if raw_path is None:
        return None, None
    path = _resolve_path(
        repo_root,
        raw_path,
        f"{label} path",
        failures,
        allow_absolute=False,
    )
    if path is None:
        return None, None
    return _read_json(path, label, failures)


def _read_json(
    path: Path,
    label: str,
    failures: list[str],
) -> tuple[Any, str | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        failures.append(f"{label}: file does not exist")
        return None, None
    except OSError as error:
        failures.append(f"{label}: cannot read file (errno {error.errno})")
        return None, None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        failures.append(f"{label}: invalid JSON ({error})")
        return None, digest
    if _contains_nonfinite_number(document):
        failures.append(f"{label}: non-finite numbers are not valid evidence")
        return None, digest
    return document, digest


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> Any:
    raise ValueError(f"non-JSON numeric constant {value!r}")


def _contains_nonfinite_number(value: Any) -> bool:
    if type(value) is float:
        return not math.isfinite(value)
    if type(value) is list:
        return any(_contains_nonfinite_number(item) for item in value)
    if type(value) is dict:
        return any(_contains_nonfinite_number(item) for item in value.values())
    return False


def _exact_object(
    value: Any,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    label: str,
    failures: list[str],
) -> dict[str, Any] | None:
    if type(value) is not dict:
        failures.append(f"{label}: must be a JSON object")
        return None
    allowed = set(required) | set(optional)
    for key in required:
        if key not in value:
            failures.append(f"{label}: missing required key {key!r}")
    for key in sorted((set(value) - allowed), key=str):
        failures.append(f"{label}: unknown key {key!r}")
    return value


def _string_field(
    value: dict[str, Any],
    key: str,
    label: str,
    failures: list[str],
) -> str | None:
    if key not in value:
        return None
    field = value[key]
    if type(field) is not str or not field:
        failures.append(f"{label}: must be a nonempty string")
        return None
    return field


def _decimal_string_field(
    value: dict[str, Any],
    key: str,
    label: str,
    failures: list[str],
) -> str | None:
    field = _string_field(value, key, label, failures)
    if field is not None and (not field.isascii() or not field.isdecimal()):
        failures.append(f"{label}: must be a decimal identifier string")
        return None
    return field


def _literal_string(
    value: dict[str, Any],
    key: str,
    expected: str,
    label: str,
    failures: list[str],
) -> None:
    field = _string_field(value, key, label, failures)
    if field is not None and field != expected:
        failures.append(f"{label}: expected {expected!r}, got {field!r}")


def _matching_string(
    value: dict[str, Any],
    key: str,
    expected: str,
    label: str,
    failures: list[str],
) -> None:
    field = _string_field(value, key, label, failures)
    if field is not None and field != expected:
        failures.append(f"{label}: does not match the committed manifest")


def _sha_field(
    value: dict[str, Any],
    key: str,
    label: str,
    failures: list[str],
) -> str | None:
    if key not in value:
        return None
    field = value[key]
    if type(field) is not str or _SHA256_RE.fullmatch(field) is None:
        failures.append(f"{label}: must be a lowercase 64-hex SHA-256")
        return None
    return field


def _matching_sha(
    value: dict[str, Any],
    key: str,
    expected: str,
    label: str,
    failures: list[str],
) -> None:
    field = _sha_field(value, key, label, failures)
    if field is not None and field != expected:
        failures.append(f"{label}: does not match the committed manifest")


def _git_sha_field(
    value: dict[str, Any],
    key: str,
    label: str,
    failures: list[str],
) -> str | None:
    if key not in value:
        return None
    field = value[key]
    if type(field) is not str or _WORKFLOW_SHA_RE.fullmatch(field) is None:
        failures.append(f"{label}: must be a full lowercase 40-hex commit SHA")
        return None
    return field


def _positive_int_field(
    value: dict[str, Any],
    key: str,
    label: str,
    failures: list[str],
) -> int | None:
    if key not in value:
        return None
    field = value[key]
    if type(field) is not int or field <= 0:
        failures.append(f"{label}: must be a positive integer")
        return None
    return field


def _json_exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _json_exact_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _json_exact_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if type(left) is float and (not math.isfinite(left) or not math.isfinite(right)):
        return False
    return bool(left == right)
