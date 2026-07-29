#!/usr/bin/env python3
"""Produce the CO SNAP executable receipt from public release bytes.

This is deliberately not a developer harness. It has no engine/artifact path
arguments and no fallback build: the only execution path downloads the pinned
released engine archive and published program artifact, verifies both against
committed SHA-256 pins, and runs the committed golden request.

The CLI only runs inside the governed GitHub Actions workflow. Unit tests call
the pure helpers; a local or differently named workflow cannot emit a receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "certificates/executable/us-co-snap/manifest.json"
WORK_DIR = Path(".executable-receipt-work")
RECEIPT_SCHEMA = "axiom_oracles.executable_receipt.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_CREDENTIALS = (
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "ANTHROPIC_API_KEY",
    "AXIOM_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
)


class ProducerError(RuntimeError):
    """The public stranger path could not produce acceptable evidence."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProducerError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProducerError(f"{path} must contain a JSON object")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ProducerError(
            f"repository path must be relative and contained: {value!r}"
        )
    resolved = (root / path).resolve()
    if resolved != root and root not in resolved.parents:
        raise ProducerError(f"repository path escapes root: {value!r}")
    return resolved


def _positive_int(env: dict[str, str], name: str) -> int:
    raw = env.get(name, "")
    if not raw.isdigit() or int(raw) <= 0:
        raise ProducerError(f"{name} must be a positive integer")
    return int(raw)


def _workflow_provenance(
    manifest: dict[str, Any], env: dict[str, str]
) -> dict[str, Any]:
    workflow = manifest["workflow"]
    if env.get("GITHUB_ACTIONS") != "true":
        raise ProducerError("receipt production is restricted to GitHub Actions")
    if env.get("GITHUB_REPOSITORY") != workflow["repository"]:
        raise ProducerError("GITHUB_REPOSITORY does not match the pinned workflow")
    if env.get("GITHUB_REPOSITORY_ID") != workflow["repository_id"]:
        raise ProducerError(
            "GITHUB_REPOSITORY_ID does not match the pinned repository"
        )
    if env.get("GITHUB_EVENT_NAME") != workflow["event"]:
        raise ProducerError("GITHUB_EVENT_NAME does not match the pinned workflow")
    if env.get("GITHUB_REF") != workflow["ref"]:
        raise ProducerError("GITHUB_REF does not match the pinned workflow ref")

    sha = env.get("GITHUB_WORKFLOW_SHA", "")
    if not COMMIT_RE.fullmatch(sha):
        raise ProducerError("GITHUB_WORKFLOW_SHA must be a full lowercase commit SHA")
    source_sha = env.get("GITHUB_SHA", "")
    if not COMMIT_RE.fullmatch(source_sha):
        raise ProducerError("GITHUB_SHA must be a full lowercase commit SHA")
    if source_sha != sha:
        raise ProducerError(
            "GITHUB_SHA must equal GITHUB_WORKFLOW_SHA for this governed workflow"
        )
    ref = workflow["ref"]
    expected_prefix = f"{workflow['repository']}/{workflow['path']}@"
    workflow_ref = env.get("GITHUB_WORKFLOW_REF", "")
    if workflow_ref != expected_prefix + ref:
        raise ProducerError(
            "GITHUB_WORKFLOW_REF does not match the pinned path and ref"
        )
    present = sorted(name for name in FORBIDDEN_CREDENTIALS if env.get(name))
    if present:
        raise ProducerError(
            "credential-bearing environment is forbidden: " + ", ".join(present)
        )
    return {
        "repository": workflow["repository"],
        "repository_id": workflow["repository_id"],
        "path": workflow["path"],
        "sha": sha,
        "source_sha": source_sha,
        "run_id": _positive_int(env, "GITHUB_RUN_ID"),
        "run_attempt": _positive_int(env, "GITHUB_RUN_ATTEMPT"),
        "event": workflow["event"],
        "ref": ref,
    }


def _recorded_run(
    argv: list[str],
    commands: list[dict[str, Any]],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    record: dict[str, Any] = {"argv": argv, "exit_code": proc.returncode}
    if input_bytes is not None:
        record["stdin_sha256"] = hashlib.sha256(input_bytes).hexdigest()
    commands.append(record)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode(errors="replace").strip()
        raise ProducerError(
            f"command exited {proc.returncode}: {argv!r}: {detail[:500]}"
        )
    return proc


def _curl(url: str, destination: Path, commands: list[dict[str, Any]]) -> None:
    _recorded_run(
        [
            "curl",
            "--fail",
            "--location",
            "--proto",
            "=https",
            "--tlsv1.2",
            "--silent",
            "--show-error",
            "--output",
            str(destination),
            url,
        ],
        commands,
    )


def _checksum(
    path: Path,
    expected: str,
    checksum_path: Path,
    commands: list[dict[str, Any]],
) -> str:
    if not SHA256_RE.fullmatch(expected):
        raise ProducerError(f"invalid committed SHA-256 for {path}")
    checksum_path.write_text(f"{expected}  {path}\n")
    _recorded_run(["sha256sum", "--check", str(checksum_path)], commands)
    observed = _sha256(REPO_ROOT / path)
    if observed != expected:
        raise ProducerError(f"SHA-256 mismatch for {path}: {observed} != {expected}")
    return observed


def _published_program_entry(
    release_manifest: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    rows = [
        row
        for row in release_manifest.get("programs", [])
        if isinstance(row, dict)
        and row.get("jurisdiction") == "us-co"
        and row.get("program_id") == "snap"
    ]
    if len(rows) != 1:
        raise ProducerError(
            "published manifest must contain exactly one us-co/snap row"
        )
    row = rows[0]
    if row.get("artifact") != artifact["name"]:
        raise ProducerError("published manifest names a different CO SNAP artifact")
    if row.get("artifact_sha256") != artifact["sha256"]:
        raise ProducerError("published manifest carries a different artifact SHA-256")
    return row


def _exact_typed_output(raw: Any, expected: Any) -> Any:
    """Return an engine output only when its released JSON type is exact."""

    if type(raw) is not dict:
        raise ProducerError("engine output entry is not an object")

    expected_type = type(expected)
    scalar_kind: str | None = None
    if expected_type is bool:
        scalar_kind = "bool"
    elif expected_type is int:
        scalar_kind = "integer"

    if scalar_kind is not None:
        typed_value = raw.get("value")
        if (
            raw.get("kind") != "scalar"
            or raw.get("dtype") != scalar_kind
            or type(typed_value) is not dict
            or typed_value.get("kind") != scalar_kind
            or "value" not in typed_value
        ):
            raise ProducerError(
                f"expected released-engine scalar/{scalar_kind} output"
            )
        value = typed_value["value"]
        if type(value) is not expected_type:
            raise ProducerError(
                f"expected exact JSON {scalar_kind} output, got {value!r}"
            )
    elif expected_type is str:
        if raw.get("kind") != "judgment" or "outcome" not in raw:
            raise ProducerError("expected released-engine judgment output")
        value = raw["outcome"]
        if type(value) is not str:
            raise ProducerError(
                f"expected exact JSON judgment string, got {value!r}"
            )
    else:
        raise ProducerError(
            f"unsupported pinned golden output type: {expected_type.__name__}"
        )

    if value != expected:
        raise ProducerError(f"golden mismatch: {value!r} != {expected!r}")
    return value


def _extract_outputs(
    stdout: bytes, bindings_document: dict[str, Any]
) -> dict[str, Any]:
    try:
        response = json.loads(stdout)
        raw_outputs = response["results"][0]["outputs"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ProducerError(
            f"engine response does not match the result schema: {exc}"
        ) from exc
    if not isinstance(raw_outputs, dict):
        raise ProducerError("engine result outputs must be an object")

    bindings = bindings_document.get("bindings")
    expected = bindings_document.get("expected")
    if not isinstance(bindings, dict) or not isinstance(expected, dict):
        raise ProducerError("golden output bindings are malformed")
    if set(bindings) != set(expected):
        raise ProducerError("golden bindings and expectations name different outputs")
    observed = {}
    for name, legal_id in bindings.items():
        if legal_id not in raw_outputs:
            raise ProducerError(f"engine response is missing {legal_id}")
        observed[name] = _exact_typed_output(raw_outputs[legal_id], expected[name])
    return observed


def produce() -> Path:
    """Run the only receipt-producing path and return its committed output path."""

    repo_root = REPO_ROOT
    environment = dict(os.environ)
    manifest = _load_json(MANIFEST_PATH)
    provenance = _workflow_provenance(manifest, environment)

    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise ProducerError("the governed producer requires Linux x86_64")

    output_path = _repo_path(repo_root, manifest["receipt_path"])
    engine_manifest_path = _repo_path(repo_root, manifest["engine"]["release_manifest"])
    engine_releases = _load_json(engine_manifest_path)
    release_name = manifest["engine"]["release"]
    try:
        release = engine_releases["releases"][release_name]
        asset = release["assets"][manifest["engine"]["target"]]
    except (KeyError, TypeError) as exc:
        raise ProducerError(
            "engine release/target is absent from the pin manifest"
        ) from exc

    golden = manifest["golden"]
    input_path = _repo_path(repo_root, golden["input_path"])
    outputs_path = _repo_path(repo_root, golden["outputs_path"])
    if _sha256(input_path) != golden["input_sha256"]:
        raise ProducerError("committed golden request bytes do not match their pin")
    if _sha256(outputs_path) != golden["outputs_sha256"]:
        raise ProducerError("committed golden output bindings do not match their pin")
    input_bytes = input_path.read_bytes()
    inputs = _load_json(input_path)
    bindings = _load_json(outputs_path)

    work_path = repo_root / WORK_DIR
    if work_path.exists() or work_path.is_symlink():
        raise ProducerError(f"refusing pre-existing producer work path: {WORK_DIR}")
    output_path.unlink(missing_ok=True)
    work_path.mkdir()

    archive = WORK_DIR / "engine.tar.xz"
    engine_checksum = WORK_DIR / "engine.sha256"
    extract_dir = WORK_DIR / "engine"
    artifact_manifest_path = WORK_DIR / "artifact-manifest.json"
    artifact_manifest_checksum = WORK_DIR / "artifact-manifest.sha256"
    artifact_path = WORK_DIR / manifest["artifact"]["name"]
    artifact_checksum = WORK_DIR / "artifact.sha256"
    extract_dir.mkdir()

    engine_url = (
        f"https://github.com/{release['repository']}/releases/download/"
        f"{release_name}/{asset['name']}"
    )
    artifact_base = (
        f"https://github.com/{manifest['artifact']['repository']}/releases/download/"
        f"{manifest['artifact']['release']}"
    )
    commands: list[dict[str, Any]] = []
    try:
        _curl(engine_url, archive, commands)
        observed_engine_sha = _checksum(
            archive, asset["sha256"], engine_checksum, commands
        )
        _recorded_run(["tar", "-xJf", str(archive), "-C", str(extract_dir)], commands)
        binary = (
            extract_dir
            / f"axiom-rules-engine-{manifest['engine']['target']}"
            / "axiom-rules-engine"
        )
        if not (repo_root / binary).is_file():
            raise ProducerError("released engine archive lacks the expected binary")
        version_proc = _recorded_run([str(binary), "--version"], commands)
        version_line = version_proc.stdout.decode(errors="strict").strip()
        if version_line != f"axiom-rules-engine {release['version']}":
            raise ProducerError(f"released engine version mismatch: {version_line!r}")

        release_manifest_spec = manifest["artifact"]["release_manifest"]
        release_manifest_url = f"{artifact_base}/{release_manifest_spec['name']}"
        _curl(release_manifest_url, artifact_manifest_path, commands)
        observed_manifest_sha = _checksum(
            artifact_manifest_path,
            release_manifest_spec["sha256"],
            artifact_manifest_checksum,
            commands,
        )
        published_manifest = _load_json(repo_root / artifact_manifest_path)
        _published_program_entry(published_manifest, manifest["artifact"])

        artifact_url = f"{artifact_base}/{manifest['artifact']['name']}"
        _curl(artifact_url, artifact_path, commands)
        observed_artifact_sha = _checksum(
            artifact_path,
            manifest["artifact"]["sha256"],
            artifact_checksum,
            commands,
        )
        run_proc = _recorded_run(
            [str(binary), "run-compiled", "--artifact", str(artifact_path)],
            commands,
            input_bytes=input_bytes,
        )
        outputs = _extract_outputs(run_proc.stdout, bindings)

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "program": manifest["program"],
            "engine": {
                "repository": release["repository"],
                "release": release_name,
                "version": release["version"],
                "target": manifest["engine"]["target"],
                "asset": asset["name"],
                "sha256": observed_engine_sha,
            },
            "artifact": {
                "repository": manifest["artifact"]["repository"],
                "release": manifest["artifact"]["release"],
                "name": manifest["artifact"]["name"],
                "sha256": observed_artifact_sha,
                "manifest_sha256": observed_manifest_sha,
            },
            "golden": {
                "name": golden["name"],
                "input_path": golden["input_path"],
                "input_sha256": golden["input_sha256"],
                "inputs": inputs,
                "outputs": outputs,
            },
            "commands": commands,
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "workflow": provenance,
        }
        temporary_output = output_path.with_suffix(".json.tmp")
        temporary_output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
        temporary_output.replace(output_path)
        return output_path
    finally:
        if work_path.is_dir() and not work_path.is_symlink():
            shutil.rmtree(work_path)


def main() -> int:
    if len(sys.argv) != 1:
        print("executable receipt producer accepts no arguments", file=sys.stderr)
        return 2
    try:
        path = produce()
    except (KeyError, TypeError, ProducerError, OSError) as exc:
        print(f"executable receipt not produced: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
