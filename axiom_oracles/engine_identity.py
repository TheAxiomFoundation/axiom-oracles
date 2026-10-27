"""Bind engine source commits to the executable bytes used by oracle runs.

Sidecars are local build attestations, not signatures. They prevent accidental
stale-build and cache drift; a checkout near an existing executable never proves
which source produced it. The receipt format also reads axiom-encode's
``<binary>.provenance.json`` build attestations.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENGINE_REPOSITORY = "TheAxiomFoundation/axiom-rules-engine"
ENGINE_RECEIPT_OUTPUT_ENV = "AXIOM_ENGINE_RECEIPT_OUTPUT"
RECEIPT_SUFFIX = ".provenance.json"
_COMMIT = re.compile(r"[0-9a-fA-F]{40}\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_MAX_RECEIPT_BYTES = 64 * 1024


class EngineIdentityError(ValueError):
    """Engine bytes cannot be bound to the claimed source identity."""


# source_status of a commit taken from a build receipt whose digest matches
# the executable's bytes; every other status leaves the commit unresolved.
VERIFIED_RECEIPT = "verified build receipt"


def record_engine_receipt(receipt: Mapping[str, Any]) -> None:
    """Record verified execution evidence for a parent that wraps a generator.

    Ordinary runs leave no journal. When the parent supplies a private output
    path, all engine invocations must agree on commit and binary digest. Path
    and other receipt metadata may differ without changing the engine bytes.
    """
    destination = os.environ.get(ENGINE_RECEIPT_OUTPUT_ENV)
    if not destination:
        return
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Generator workers can share this path; lock a stable sibling because
        # atomic replacement changes the journal file's inode.
        with output.with_name(output.name + ".lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if output.exists():
                with output.open("rb") as previous_file:
                    raw = previous_file.read(_MAX_RECEIPT_BYTES + 1)
                try:
                    previous = json.loads(raw) if len(raw) <= _MAX_RECEIPT_BYTES else None
                except (ValueError, UnicodeError):
                    previous = None
                if not isinstance(previous, dict):
                    raise EngineIdentityError("Engine execution receipt journal is malformed")
                if any(
                    previous.get(field) != receipt.get(field)
                    for field in ("commit", "binary_sha256")
                ):
                    raise EngineIdentityError("Engine execution identities disagree in this run")
            encoded = json.dumps(dict(receipt), indent=2, sort_keys=True) + "\n"
            if len(encoded.encode("utf-8")) > _MAX_RECEIPT_BYTES:
                raise EngineIdentityError("Engine execution receipt is too large")
            descriptor, staged_name = tempfile.mkstemp(
                dir=output.parent, prefix=output.name + "."
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as staged:
                    staged.write(encoded)
                os.replace(staged_name, output)
            finally:
                if os.path.exists(staged_name):
                    os.unlink(staged_name)
    except OSError as exc:
        raise EngineIdentityError(f"Cannot record engine execution receipt: {output}") from exc


def engine_binding_receipt_path(binary_path: str | Path) -> Path:
    binary = Path(binary_path)
    return binary.with_name(binary.name + RECEIPT_SUFFIX)


def _resolved_executable(binary_path: str | Path) -> Path:
    raw = os.path.expandvars(os.path.expanduser(str(binary_path)))
    # subprocess searches PATH for bare command names. Resolve the same file
    # before hashing and pass its absolute path to the eventual invocation.
    if not os.path.dirname(raw):
        located = shutil.which(raw)
        if located:
            return Path(located).resolve()
    return Path(raw).resolve()


def _binary_sha256(binary: Path) -> str | None:
    try:
        with binary.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        return None


def _read_binding(binary: Path) -> dict[str, Any] | None:
    try:
        with engine_binding_receipt_path(binary).open("rb") as stream:
            raw = stream.read(_MAX_RECEIPT_BYTES + 1)
        if len(raw) > _MAX_RECEIPT_BYTES:
            return None
        value = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def engine_receipt(
    binary_path: str | Path, *, include_version: bool = False
) -> dict[str, Any]:
    """Hash this executable now; accept a source SHA only from matching bytes.

    Missing, malformed and stale sidecars leave ``commit`` unresolved. A bare
    binary still records its actual digest. No neighbouring repository is
    consulted, and arbitrary files are never executed unless ``include_version``
    is explicitly requested.
    """
    binary = _resolved_executable(binary_path)
    digest = _binary_sha256(binary)
    binding = _read_binding(binary)
    commit: str | None = None
    version: str | None = None
    working_tree = "unresolved"
    status = "unresolved: no build receipt"
    if digest is None:
        status = "unresolved: unreadable executable"
    elif binding is not None:
        candidate = binding.get("commit", binding.get("engine_commit"))
        bound_digest = binding.get("binary_sha256")
        if (
            isinstance(candidate, str)
            and _COMMIT.fullmatch(candidate)
            and isinstance(bound_digest, str)
            and _SHA256.fullmatch(bound_digest)
            and bound_digest.lower() == digest
            and binding.get("repository", ENGINE_REPOSITORY) == ENGINE_REPOSITORY
        ):
            commit = candidate.lower()
            bound_version = binding.get("version")
            version = bound_version if isinstance(bound_version, str) else None
            working_tree = str(binding.get("working_tree", "unresolved"))
            status = VERIFIED_RECEIPT
        else:
            status = "unresolved: build receipt does not match executable"
    if include_version and digest is not None and version is None:
        try:
            result = subprocess.run(
                [str(binary), "--version"], capture_output=True, text=True,
                check=False, timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            pass
        if _binary_sha256(binary) != digest:
            raise EngineIdentityError("Engine executable changed while reading its version")
    return {
        "repository": ENGINE_REPOSITORY,
        "commit": commit,
        "binary_sha256": digest,
        "version": version,
        "source_status": status,
        "working_tree": working_tree,
        "binary_path": str(binary),
        "binary": str(binary),
        # Existing consumers retain their historical field names.
        "axiom_rules_engine_sha": commit,
        "axiom_rules_engine_version": version,
    }


def _git(repo: Path, *args: str) -> str:
    from .provenance import _git_env

    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], check=True,
            capture_output=True, text=True, timeout=30, env=_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EngineIdentityError(f"Cannot verify engine source checkout {repo}") from exc
    return result.stdout.strip()


def _clean_source_commit(repo: Path) -> str:
    from .provenance import worktree_attestation

    if Path(_git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise EngineIdentityError(f"Engine source must be a repository root: {repo}")
    commit = _git(repo, "rev-parse", "HEAD")
    if _COMMIT.fullmatch(commit) is None:
        raise EngineIdentityError("Engine source must have a full 40-hex HEAD commit")
    if (
        _git(repo, "status", "--porcelain", "--untracked-files=all")
        or worktree_attestation(repo, reference=commit).get("dirty") is not False
    ):
        raise EngineIdentityError("Engine source must be clean before a build can be receipted")
    if _git(repo, "rev-parse", "HEAD").lower() != commit.lower():
        raise EngineIdentityError("Engine source changed while verifying the build checkout")
    return commit.lower()


def build_engine_binary(
    repo: str | Path,
    binary_path: str | Path,
    command: Sequence[str],
    *,
    run: Callable[..., Any] = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Observe a build in a clean checkout, then bind its output to that HEAD.

    The expected output is removed first, so a successful command that leaves
    stale bytes elsewhere cannot accidentally attest an old executable. Cargo's
    output directory is explicit even when callers have a shared target cache.
    """
    source = Path(repo).expanduser().resolve()
    binary = Path(binary_path).expanduser().resolve()
    commit = _clean_source_commit(source)
    binary.unlink(missing_ok=True)
    engine_binding_receipt_path(binary).unlink(missing_ok=True)
    from .provenance import _git_env, _REPO_LOCATING_ENV

    build_env = _git_env() if env is None else {
        key: value for key, value in env.items() if key not in _REPO_LOCATING_ENV
    }
    build_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    build_env["CARGO_TARGET_DIR"] = str(source / "target")
    run(list(command), check=True, cwd=source, env=build_env, timeout=600)
    if _clean_source_commit(source) != commit:
        raise EngineIdentityError("Engine source changed during the build")
    digest = _binary_sha256(binary)
    if digest is None:
        raise EngineIdentityError(f"Engine build produced no readable executable: {binary}")
    try:
        manifest = tomllib.loads((source / "Cargo.toml").read_text())
        version = manifest.get("package", {}).get("version")
    except (OSError, ValueError):
        version = None
    payload = {
        "repository": ENGINE_REPOSITORY,
        "engine_commit": commit,
        "commit": commit,
        "binary_sha256": digest,
        "version": version if isinstance(version, str) else None,
        "working_tree": "clean",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_command": list(command),
        "written_by": "axiom-oracles",
    }
    receipt_path = engine_binding_receipt_path(binary)
    descriptor, staged_name = tempfile.mkstemp(
        dir=receipt_path.parent, prefix=receipt_path.name + "."
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as staged:
            json.dump(payload, staged, indent=2, sort_keys=True)
            staged.write("\n")
        os.replace(staged_name, receipt_path)
    finally:
        if os.path.exists(staged_name):
            os.unlink(staged_name)
    return engine_receipt(binary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    inspect = commands.add_parser("inspect", help="Hash and verify an existing executable")
    inspect.add_argument("binary")
    inspect.add_argument("--expect-commit")
    build = commands.add_parser("build", help="Build and receipt a clean engine checkout")
    build.add_argument("--repo", required=True)
    build.add_argument("--binary", required=True)
    build.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                raise EngineIdentityError("A build command is required after --")
            receipt = build_engine_binary(args.repo, args.binary, command)
        else:
            receipt = engine_receipt(args.binary)
            if args.expect_commit is not None:
                if _COMMIT.fullmatch(args.expect_commit) is None:
                    raise EngineIdentityError("Expected commit must be a full 40-hex SHA")
                if receipt["commit"] != args.expect_commit.lower():
                    raise EngineIdentityError(
                        f"Executable has no verified receipt for {args.expect_commit}: "
                        f"{receipt['source_status']}"
                    )
    except (EngineIdentityError, OSError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
