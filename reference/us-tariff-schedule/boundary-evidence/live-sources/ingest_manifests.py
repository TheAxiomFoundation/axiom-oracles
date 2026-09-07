"""Signed ingest manifests and guards for generated corpus artifacts."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import io
import json
import os
import re
import subprocess
from base64 import b64decode, b64encode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeGuard

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

INGEST_MANIFEST_SCHEMA_VERSION = "axiom-corpus/ingest-manifest/v1"
INGEST_MANIFEST_SIGNATURE_ALGORITHM = "ed25519"
INGEST_MANIFEST_KEY_ID = "axiom-corpus-ingest-v1"
INGEST_MANIFEST_PRIVATE_KEY_ENV = "AXIOM_CORPUS_INGEST_PRIVATE_KEY"
INGEST_MANIFEST_PUBLIC_KEY_ENV = "AXIOM_CORPUS_INGEST_PUBLIC_KEY"
INGEST_MANIFEST_ROOT = Path(".axiom") / "ingest-manifests"
PROTECTED_CORPUS_PREFIXES = (
    "data/corpus/sources/",
    "data/corpus/inventory/",
    "data/corpus/provisions/",
    "data/corpus/coverage/",
)
TEXT_OFFICIAL_DOCUMENT_SUFFIXES = {
    ".csv",
    ".html",
    ".htm",
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
FULL_GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class IngestGuardResult:
    """Result from checking changed corpus artifacts against ingest manifests."""

    repo: Path
    protected_changes: tuple[str, ...]
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_mapping(self) -> dict[str, Any]:
        return {
            "repo": str(self.repo),
            "passed": self.passed,
            "protected_changes": list(self.protected_changes),
            "issues": list(self.issues),
        }


def build_ingest_manifest(
    *,
    repo: Path,
    base: Path,
    jurisdiction: str,
    document_class: str,
    version: str,
    command: str,
    applied_files: list[Path] | None = None,
    deleted_files: list[Path] | None = None,
    reasoning_logs: list[Path] | None = None,
) -> dict[str, Any]:
    """Build an unsigned ingest manifest for one corpus scope."""
    repo = repo.resolve()
    base = _resolve_under_repo(repo, base)
    git_metadata = _git_metadata(repo)
    provenance_issues = _git_provenance_issues(git_metadata)
    if provenance_issues:
        raise ValueError(
            "Cannot build an ingest manifest from non-canonical generator state: "
            + " ".join(provenance_issues)
        )
    deleted_files = deleted_files or []
    files = applied_files
    if files is None and not deleted_files:
        files = _infer_scope_artifacts(
            base=base,
            jurisdiction=jurisdiction,
            document_class=document_class,
            version=version,
        )
    if files is None:
        files = []
    if not files and not deleted_files:
        raise FileNotFoundError(
            f"No corpus artifacts found for {jurisdiction}/{document_class}/{version} under {base}."
        )
    coverage = _load_scope_coverage(
        base=base,
        jurisdiction=jurisdiction,
        document_class=document_class,
        version=version,
    )
    manifest: dict[str, Any] = {
        "schema_version": INGEST_MANIFEST_SCHEMA_VERSION,
        "tool": "axiom-corpus-ingest signed ingest manifest",
        "axiom_corpus_version": _package_version(),
        "axiom_corpus_git": git_metadata,
        "generated_at": datetime.now(UTC).isoformat(),
        "jurisdiction": jurisdiction,
        "document_class": document_class,
        "version": version,
        "command": {"text": command},
        "coverage": coverage,
        "reasoning_logs": [
            _manifest_file_entry(repo, _resolve_under_repo(repo, path))
            for path in sorted(reasoning_logs or [])
        ],
        "applied_files": [
            _manifest_file_entry(repo, _resolve_under_repo(repo, path)) for path in sorted(files)
        ]
        + [
            _manifest_deleted_file_entry(repo, _resolve_under_repo(repo, path))
            for path in sorted(deleted_files)
        ],
    }
    return manifest


def sign_ingest_manifest(
    payload: dict[str, Any],
    *,
    private_key: str,
    key_id: str = INGEST_MANIFEST_KEY_ID,
) -> dict[str, Any]:
    """Return a copy of an ingest manifest with an Ed25519 signature."""
    signed = copy.deepcopy(payload)
    signed.pop("signature", None)
    provenance_issues = _manifest_git_provenance_issues(signed)
    if provenance_issues:
        raise ValueError(
            "Cannot sign an ingest manifest with non-canonical generator state: "
            + " ".join(provenance_issues)
        )
    signed["signature"] = {
        "algorithm": INGEST_MANIFEST_SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "value": _manifest_ed25519_signature(signed, private_key),
    }
    return signed


def verify_ingest_manifest(
    payload: dict[str, Any],
    *,
    public_key: str,
    repo: Path,
    head_ref: str,
) -> list[str]:
    """Return verification issues for a signed ingest manifest."""
    repo = repo.resolve()
    issues = _manifest_git_provenance_issues(payload)
    git_metadata = payload.get("axiom_corpus_git")
    commit = git_metadata.get("commit") if isinstance(git_metadata, dict) else None
    if _is_full_git_commit(commit) and not _git_commit_is_ancestor(
        repo,
        commit=commit,
        head_ref=head_ref,
    ):
        issues.append(
            f"`axiom_corpus_git.commit` `{commit}` is not an ancestor of guarded head `{head_ref}`."
        )
    if payload.get("schema_version") != INGEST_MANIFEST_SCHEMA_VERSION:
        issues.append("Unsupported ingest manifest schema version.")
    signature = payload.get("signature")
    if not isinstance(signature, dict):
        issues.append("Missing ingest manifest signature.")
        return issues
    if signature.get("algorithm") != INGEST_MANIFEST_SIGNATURE_ALGORITHM:
        issues.append("Unsupported ingest manifest signature algorithm.")
    actual = str(signature.get("value") or "")
    try:
        _verify_manifest_ed25519_signature(payload, public_key, actual)
    except ValueError as exc:
        issues.append(str(exc))
    except InvalidSignature:
        issues.append("Invalid ingest manifest signature.")
    return issues


def write_signed_ingest_manifest(
    *,
    repo: Path,
    manifest: dict[str, Any],
    private_key: str,
    output: Path | None = None,
    key_id: str = INGEST_MANIFEST_KEY_ID,
) -> Path:
    """Sign and write an ingest manifest."""
    repo = repo.resolve()
    signed = sign_ingest_manifest(manifest, private_key=private_key, key_id=key_id)
    manifest_path = output or default_ingest_manifest_path(
        jurisdiction=str(signed["jurisdiction"]),
        document_class=str(signed["document_class"]),
        version=str(signed["version"]),
    )
    manifest_path = _resolve_under_repo(repo, manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n")
    return manifest_path


def default_ingest_manifest_path(
    *,
    jurisdiction: str,
    document_class: str,
    version: str,
) -> Path:
    """Return the default repo-relative manifest path for one corpus scope."""
    return (
        INGEST_MANIFEST_ROOT
        / _safe_segment(jurisdiction)
        / _safe_segment(document_class)
        / f"{_safe_segment(version)}.json"
    )


def guard_ingested_artifacts(
    *,
    repo: Path,
    base_ref: str | None = None,
    head_ref: str | None = "HEAD",
    public_key: str | None = None,
) -> IngestGuardResult:
    """Check changed generated corpus artifacts against signed manifests."""
    repo = repo.resolve()
    public_key = public_key or os.environ.get(INGEST_MANIFEST_PUBLIC_KEY_ENV)
    try:
        changes = _changed_paths(repo=repo, base_ref=base_ref, head_ref=head_ref)
    except (subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as exc:
        return IngestGuardResult(
            repo=repo,
            protected_changes=(),
            issues=(f"Unable to read changed paths: {exc}",),
        )
    protected = tuple(path for path in changes if _is_protected_corpus_artifact(path.path))
    if not changes:
        return IngestGuardResult(repo=repo, protected_changes=(), issues=())

    read_ref = (head_ref or "HEAD") if base_ref else None
    try:
        manifests = _load_ingest_manifests(repo, ref=read_ref)
        baseline_ref = base_ref or "HEAD"
        baseline_manifests = _load_ingest_manifests(repo, ref=baseline_ref)
    except ValueError as exc:
        return IngestGuardResult(
            repo=repo,
            protected_changes=tuple(change.path for change in protected),
            issues=(str(exc),),
        )
    entries_by_path: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]] = {}
    reasoning_manifests_by_path: dict[str, set[Path]] = {}
    for manifest_path, payload in manifests.items():
        for entry in payload.get("applied_files", []):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if isinstance(path, str) and path:
                entries_by_path[path] = (manifest_path, payload, entry)
        for path in _reasoning_log_paths(payload):
            reasoning_manifests_by_path.setdefault(path, set()).add(manifest_path)

    baseline_reasoning_manifests_by_path: dict[str, set[Path]] = {}
    for manifest_path, payload in baseline_manifests.items():
        for path in _reasoning_log_paths(payload):
            baseline_reasoning_manifests_by_path.setdefault(path, set()).add(manifest_path)

    changed_reasoning_paths_by_manifest: dict[Path, set[str]] = {}
    for change in changes:
        manifest_paths = reasoning_manifests_by_path.get(change.path, set()) | (
            baseline_reasoning_manifests_by_path.get(change.path, set())
        )
        for manifest_path in manifest_paths:
            changed_reasoning_paths_by_manifest.setdefault(manifest_path, set()).add(change.path)

    changed_manifest_paths = {
        Path(change.path)
        for change in changes
        if change.path.startswith(f"{INGEST_MANIFEST_ROOT.as_posix()}/")
        and change.path.endswith(".json")
    }
    for manifest_path in changed_manifest_paths:
        candidate_payload = manifests.get(manifest_path, {})
        baseline_payload = baseline_manifests.get(manifest_path, {})
        attested_paths = _reasoning_log_paths(candidate_payload) | _reasoning_log_paths(
            baseline_payload
        )
        if attested_paths:
            changed_reasoning_paths_by_manifest.setdefault(manifest_path, set()).update(
                attested_paths
            )
    changed_reasoning_manifests = set(changed_reasoning_paths_by_manifest)
    if not protected and not changed_reasoning_manifests:
        return IngestGuardResult(repo=repo, protected_changes=(), issues=())
    if not public_key:
        return IngestGuardResult(
            repo=repo,
            protected_changes=tuple(change.path for change in protected),
            issues=(
                f"{INGEST_MANIFEST_PUBLIC_KEY_ENV} is required to verify corpus ingest manifests.",
            ),
        )

    manifest_issues: dict[Path, list[str]] = {}

    def verification_issues(
        manifest_path: Path,
        payload: dict[str, Any],
    ) -> list[str]:
        if manifest_path not in manifest_issues:
            manifest_issues[manifest_path] = verify_ingest_manifest(
                payload,
                public_key=public_key,
                repo=repo,
                head_ref=head_ref or "HEAD",
            )
        return manifest_issues[manifest_path]

    issues: list[str] = []
    authorizing_manifests: set[Path] = set()
    for change in protected:
        manifest_entry = entries_by_path.get(change.path)
        if manifest_entry is None:
            issues.append(
                f"Unmanifested corpus artifact change: `{change.path}`. "
                "Run `axiom-corpus-ingest sign-ingest-manifest` for the scope."
            )
            continue
        manifest_path, _payload, entry = manifest_entry
        authorizing_manifests.add(manifest_path)
        current_manifest_issues = verification_issues(manifest_path, _payload)
        if current_manifest_issues:
            for issue in current_manifest_issues:
                issues.append(f"{manifest_path.as_posix()}: {issue}")
            continue
        if change.status == "D":
            if entry.get("deleted") is not True:
                issues.append(
                    f"`{change.path}` is deleted but its ingest manifest does not mark it deleted."
                )
            continue
        actual_sha = _artifact_sha(repo, change.path, ref=read_ref)
        if actual_sha is None:
            issues.append(f"Manifested corpus artifact is missing: `{change.path}`.")
            continue
        expected_sha = str(entry.get("sha256") or "")
        if actual_sha != expected_sha:
            issues.append(
                f"`{change.path}` sha256 does not match ingest manifest "
                f"`{manifest_path.as_posix()}`."
            )
            continue
        issues.extend(_artifact_content_issues(repo, change.path, ref=read_ref))

    for manifest_path in sorted(authorizing_manifests | changed_reasoning_manifests):
        current_payload = manifests.get(manifest_path)
        if current_payload is None:
            changed_paths = sorted(changed_reasoning_paths_by_manifest.get(manifest_path, set()))
            issues.append(
                f"{manifest_path.as_posix()}: signed manifest was removed while its "
                f"reasoning log changed: {changed_paths}."
            )
            continue
        current_manifest_issues = verification_issues(manifest_path, current_payload)
        if current_manifest_issues:
            for issue in current_manifest_issues:
                issues.append(f"{manifest_path.as_posix()}: {issue}")
            continue
        for issue in _reasoning_log_issues(repo, current_payload, ref=read_ref):
            issues.append(f"{manifest_path.as_posix()}: {issue}")
        current_reasoning_paths = _reasoning_log_paths(current_payload)
        for path in sorted(changed_reasoning_paths_by_manifest.get(manifest_path, set())):
            if path not in current_reasoning_paths:
                issues.append(
                    f"{manifest_path.as_posix()}: reasoning log `{path}` is no longer "
                    "attested after a related log or manifest change."
                )

    return IngestGuardResult(
        repo=repo,
        protected_changes=tuple(change.path for change in protected),
        issues=tuple(dict.fromkeys(issues)),
    )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a local file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 digest for bytes."""
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class _ChangedPath:
    status: str
    path: str


def _canonical_manifest_bytes(payload: dict[str, Any]) -> bytes:
    unsigned = copy.deepcopy(payload)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest_ed25519_signature(payload: dict[str, Any], private_key: str) -> str:
    key = _load_ed25519_private_key(private_key)
    signature = key.sign(_canonical_manifest_bytes(payload))
    return b64encode(signature).decode("ascii")


def _verify_manifest_ed25519_signature(
    payload: dict[str, Any], public_key: str, signature: str
) -> None:
    key = _load_ed25519_public_key(public_key)
    try:
        signature_bytes = b64decode(signature.encode("ascii"), validate=True)
    except (BinasciiError, UnicodeEncodeError) as exc:
        raise ValueError("Invalid ingest manifest signature encoding.") from exc
    key.verify(signature_bytes, _canonical_manifest_bytes(payload))


def _load_ed25519_private_key(private_key: str) -> Ed25519PrivateKey:
    text = private_key.strip().replace("\\n", "\n")
    if text.startswith("-----BEGIN "):
        loaded = serialization.load_pem_private_key(
            text.encode("utf-8"),
            password=None,
        )
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("Ingest manifest private key must be Ed25519.")
        return loaded
    raw = _load_raw_key_bytes(text, expected_length=32, kind="private")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _load_ed25519_public_key(public_key: str) -> Ed25519PublicKey:
    text = public_key.strip().replace("\\n", "\n")
    if text.startswith("-----BEGIN "):
        loaded = serialization.load_pem_public_key(text.encode("utf-8"))
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValueError("Ingest manifest public key must be Ed25519.")
        return loaded
    raw = _load_raw_key_bytes(text, expected_length=32, kind="public")
    return Ed25519PublicKey.from_public_bytes(raw)


def _load_raw_key_bytes(text: str, *, expected_length: int, kind: str) -> bytes:
    try:
        raw = b64decode(text.encode("ascii"), validate=True)
    except (BinasciiError, UnicodeEncodeError) as exc:
        raise ValueError(f"Ingest manifest {kind} key must be raw base64 or PEM.") from exc
    if len(raw) != expected_length:
        raise ValueError(f"Ingest manifest {kind} key must decode to {expected_length} bytes.")
    return raw


def _manifest_file_entry(repo: Path, path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return {
        "path": _repo_relative(repo, path),
        "sha256": sha256_file(path),
    }


def _manifest_deleted_file_entry(repo: Path, path: Path) -> dict[str, Any]:
    return {
        "path": _repo_relative(repo, path),
        "deleted": True,
    }


def _infer_scope_artifacts(
    *,
    base: Path,
    jurisdiction: str,
    document_class: str,
    version: str,
) -> list[Path]:
    files: list[Path] = []
    source_root = base / "sources" / jurisdiction / document_class / version
    if source_root.exists():
        files.extend(path for path in source_root.rglob("*") if path.is_file())
    for path in (
        base / "inventory" / jurisdiction / document_class / f"{version}.json",
        base / "provisions" / jurisdiction / document_class / f"{version}.jsonl",
        base / "coverage" / jurisdiction / document_class / f"{version}.json",
    ):
        if path.exists():
            files.append(path)
    if not files:
        raise FileNotFoundError(
            f"No corpus artifacts found for {jurisdiction}/{document_class}/{version} under {base}."
        )
    return sorted(files)


def _load_scope_coverage(
    *,
    base: Path,
    jurisdiction: str,
    document_class: str,
    version: str,
) -> dict[str, Any] | None:
    coverage_path = base / "coverage" / jurisdiction / document_class / f"{version}.json"
    if not coverage_path.exists():
        return None
    try:
        payload = json.loads(coverage_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "complete": payload.get("complete"),
        "source_count": payload.get("source_count"),
        "provision_count": payload.get("provision_count"),
        "matched_count": payload.get("matched_count"),
        "missing_count": len(payload.get("missing_from_provisions") or []),
        "extra_count": len(payload.get("extra_provisions") or []),
    }


def _load_ingest_manifests(repo: Path, *, ref: str | None = None) -> dict[Path, dict[str, Any]]:
    if ref:
        return _load_ingest_manifests_from_ref(repo, ref=ref)
    manifest_root = repo / INGEST_MANIFEST_ROOT
    manifests: dict[Path, dict[str, Any]] = {}
    if not manifest_root.exists():
        return manifests
    for path in sorted(manifest_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            manifests[path.relative_to(repo)] = {}
            continue
        if isinstance(payload, dict):
            manifests[path.relative_to(repo)] = payload
    return manifests


def _load_ingest_manifests_from_ref(repo: Path, *, ref: str) -> dict[Path, dict[str, Any]]:
    manifests: dict[Path, dict[str, Any]] = {}
    tree_result = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "-z",
            ref,
            "--",
            INGEST_MANIFEST_ROOT.as_posix(),
        ],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if tree_result.returncode != 0:
        detail = tree_result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Unable to list ingest manifests at `{ref}`: {detail}")

    objects: list[tuple[Path, str]] = []
    for raw_entry in tree_result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            _mode, object_type, raw_oid = metadata.split(b" ", 2)
        except ValueError as exc:
            raise ValueError(f"Malformed Git tree entry while reading `{ref}`.") from exc
        path = Path(raw_path.decode("utf-8", errors="surrogateescape"))
        if object_type == b"blob" and path.suffix == ".json":
            objects.append((path, raw_oid.decode("ascii")))
    objects.sort(key=lambda item: item[0].as_posix())
    if not objects:
        return manifests

    batch_result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo,
        check=False,
        input="".join(f"{oid}\n" for _path, oid in objects).encode("ascii"),
        capture_output=True,
    )
    if batch_result.returncode != 0:
        detail = batch_result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Unable to read ingest manifests at `{ref}`: {detail}")

    output = io.BytesIO(batch_result.stdout)
    for path, expected_oid in objects:
        header = output.readline().rstrip(b"\n").split()
        if len(header) != 3 or header[0].decode("ascii", errors="replace") != expected_oid:
            raise ValueError(f"Malformed Git batch header for ingest manifest `{path}`.")
        if header[1] != b"blob":
            raise ValueError(f"Git object for ingest manifest `{path}` is not a blob.")
        try:
            size = int(header[2])
        except ValueError as exc:
            raise ValueError(f"Malformed Git object size for ingest manifest `{path}`.") from exc
        blob = output.read(size)
        if len(blob) != size or output.read(1) != b"\n":
            raise ValueError(f"Truncated Git object for ingest manifest `{path}`.")
        try:
            payload = json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            manifests[path] = {}
            continue
        if isinstance(payload, dict):
            manifests[path] = payload
    if output.read(1):
        raise ValueError(f"Unexpected trailing Git batch output while reading `{ref}`.")
    return manifests


def _artifact_sha(repo: Path, path: str, *, ref: str | None) -> str | None:
    payload = _artifact_bytes(repo, path, ref=ref)
    if payload is None:
        return None
    return sha256_bytes(payload)


def _artifact_bytes(repo: Path, path: str, *, ref: str | None) -> bytes | None:
    if ref:
        return _git_blob(repo, ref=ref, path=path)
    artifact_path = repo / path
    if not artifact_path.exists():
        return None
    return artifact_path.read_bytes()


def _artifact_content_issues(repo: Path, path: str, *, ref: str | None) -> list[str]:
    payload = _artifact_bytes(repo, path, ref=ref)
    if payload is None:
        return []
    issues: list[str] = []
    if _is_official_document_artifact(path) and _looks_like_agent_digest(path, payload):
        issues.append(
            f"`{path}` is under official-documents/ but looks like an agent digest "
            "with Title:/Sources: headers. Move it to reasoning/ and keep "
            "primary_source false, or replace it with captured official source text."
        )
    if _is_inventory_artifact(path):
        issues.extend(_inventory_primary_source_issues(path, payload))
    return issues


def _reasoning_log_issues(
    repo: Path,
    payload: dict[str, Any],
    *,
    ref: str | None,
) -> list[str]:
    raw_entries = payload.get("reasoning_logs")
    if not isinstance(raw_entries, list):
        return ["`reasoning_logs` must be a list."]

    issues: list[str] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            issues.append("Each reasoning log entry must be an object.")
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            issues.append("Each reasoning log entry must have a path.")
            continue
        path = raw_path
        actual_sha = _artifact_sha(repo, path, ref=ref)
        if actual_sha is None:
            issues.append(f"Manifested reasoning log is missing: `{path}`.")
            continue
        expected_sha = str(entry.get("sha256") or "")
        if actual_sha != expected_sha:
            issues.append(f"`{path}` sha256 does not match the signed reasoning log entry.")
    return issues


def _reasoning_log_paths(payload: dict[str, Any]) -> set[str]:
    raw_entries = payload.get("reasoning_logs")
    if not isinstance(raw_entries, list):
        return set()
    return {
        path
        for entry in raw_entries
        if isinstance(entry, dict)
        if isinstance(path := entry.get("path"), str) and path
    }


def _is_official_document_artifact(path: str) -> bool:
    return path.startswith("data/corpus/sources/") and "/official-documents/" in path


def _is_inventory_artifact(path: str) -> bool:
    return path.startswith("data/corpus/inventory/") and path.endswith(".json")


def _looks_like_agent_digest(path: str, payload: bytes) -> bool:
    if Path(path).suffix.lower() not in TEXT_OFFICIAL_DOCUMENT_SUFFIXES:
        return False
    text = _decode_text(payload)
    if text is None:
        return False
    lines = [line.strip() for line in text.splitlines()[:20] if line.strip()]
    has_title = any(line.startswith("Title:") for line in lines[:5])
    has_sources = any(line.startswith("Sources:") for line in lines[:10])
    return has_title and has_sources


def _inventory_primary_source_issues(path: str, payload: bytes) -> list[str]:
    text = _decode_text(payload)
    if text is None:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    issues: list[str] = []
    for item in parsed.get("items") or []:
        if not isinstance(item, dict):
            continue
        raw_metadata = item.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        if metadata.get("primary_source") is not True:
            continue
        source_path = str(item.get("source_path") or "")
        if "/reasoning/" not in source_path:
            continue
        citation = str(item.get("citation_path") or "<unknown citation>")
        issues.append(
            f"`{path}` marks `{citation}` primary_source true while source_path "
            f"`{source_path}` is under reasoning/. Primary rows must point at "
            "official-documents/ captures, not reasoning artifacts."
        )
    return issues


def _decode_text(payload: bytes) -> str | None:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _git_blob(repo: Path, *, ref: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _changed_paths(
    *,
    repo: Path,
    base_ref: str | None,
    head_ref: str | None,
) -> tuple[_ChangedPath, ...]:
    if base_ref:
        diff_ref = f"{base_ref}...{head_ref or 'HEAD'}"
        args = ["git", "diff", "--name-status", "-z", "--no-renames", diff_ref]
    else:
        args = ["git", "diff", "--name-status", "-z", "--no-renames", "HEAD"]
    result = subprocess.run(
        args,
        cwd=repo,
        check=True,
        capture_output=True,
    )
    fields = result.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise ValueError("Malformed NUL-delimited Git diff output.")

    changes: list[_ChangedPath] = []
    for raw_status, raw_path in zip(fields[::2], fields[1::2], strict=True):
        status = raw_status.decode("ascii")
        if not status:
            raise ValueError("Git diff returned an empty change status.")
        path = os.fsdecode(raw_path)
        changes.append(_ChangedPath(status=status[0], path=path))
    return tuple(changes)


def _is_protected_corpus_artifact(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PROTECTED_CORPUS_PREFIXES)


def _git_metadata(repo: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    status = git("status", "--porcelain", "--untracked-files=no")
    return {
        # The manifest is repository-relative; an absolute checkout path is
        # neither reproducible nor useful provenance.
        "root": ".",
        "commit": git("rev-parse", "HEAD"),
        "dirty_tracked": None if status is None else bool(status),
    }


def _manifest_git_provenance_issues(payload: dict[str, Any]) -> list[str]:
    metadata = payload.get("axiom_corpus_git")
    if not isinstance(metadata, dict):
        return ["`axiom_corpus_git` must be an object."]
    return _git_provenance_issues(metadata)


def _git_provenance_issues(metadata: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if metadata.get("root") != ".":
        issues.append("`axiom_corpus_git.root` must be `.`.")
    if metadata.get("dirty_tracked") is not False:
        issues.append("`axiom_corpus_git.dirty_tracked` must be false.")
    if not _is_full_git_commit(metadata.get("commit")):
        issues.append("`axiom_corpus_git.commit` must be a full 40-character lowercase Git commit.")
    return issues


def _is_full_git_commit(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and FULL_GIT_COMMIT_PATTERN.fullmatch(value) is not None


def _git_commit_is_ancestor(repo: Path, *, commit: str, head_ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head_ref],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _package_version() -> str:
    try:
        return importlib.metadata.version("axiom-corpus")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def _resolve_under_repo(repo: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else repo / path
    resolved = candidate.resolve()
    resolved.relative_to(repo)
    return resolved


def _repo_relative(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo).as_posix()


def _safe_segment(value: str) -> str:
    cleaned = value.strip().strip("/")
    cleaned = cleaned.replace("\\", "-").replace(":", "-")
    if cleaned in {"", ".", ".."} or "/" in cleaned:
        raise ValueError(f"unsafe path segment: {value!r}")
    return cleaned
