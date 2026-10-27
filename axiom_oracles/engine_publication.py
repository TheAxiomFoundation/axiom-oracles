"""Admission checks for the engine identity in published Axiom reports.

Historical exceptions bind a report path to its exact published bytes. They
never supply an identity and cannot exempt a rerun, edited copy, or new path.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .engine_identity import ENGINE_REPOSITORY

from axiom_oracles.provenance import _git_env

ENGINE_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
BINARY_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
DASHBOARD_DATA = "dashboard/public/data"
LEGACY_ALLOWLIST = "conformance/legacy-engine-identity.json"
LEGACY_SCHEMA = "axiom_oracles.legacy-engine-identity.v1"


def is_axiom_report(report: object) -> bool:
    """Recognize both runner engine pairs and campaign engine mappings."""
    if not isinstance(report, Mapping):
        return False
    identity = report.get("engine_identity")
    if isinstance(identity, Mapping) and "axiom" in identity:
        return True
    for block in (report, report.get("provenance")):
        if not isinstance(block, Mapping):
            continue
        runtime = block.get("runtime_provenance")
        engine = block.get("engine")
        if isinstance(runtime, Mapping) and "axiom_engine" in runtime:
            return True
        if isinstance(engine, Mapping) and engine.get("repository") == ENGINE_REPOSITORY:
            return True
    engines = report.get("engines")
    if isinstance(engines, Mapping):
        if "axiom" in engines or any(
            value in ("axiom", "axiom-rules", "axiom-rules-engine")
            for value in engines.values()
            if isinstance(value, str)
        ):
            return True
    elif isinstance(engines, list) and "axiom" in engines:
        return True
    cases = report.get("cases")
    return isinstance(cases, list) and any(
        isinstance(case, Mapping) and "axiom" in case for case in cases
    )


def engine_identity_errors(report: object) -> list[str]:
    """Return all missing or malformed canonical engine identity fields."""
    provenance = report.get("provenance") if isinstance(report, Mapping) else None
    engine = provenance.get("engine") if isinstance(provenance, Mapping) else None
    engine = engine if isinstance(engine, Mapping) else {}
    errors = []
    for field, pattern, length in (
        ("commit", ENGINE_COMMIT, 40),
        ("binary_sha256", BINARY_SHA256, 64),
    ):
        value = engine.get(field)
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            errors.append(f"provenance.engine.{field} must be {length} hex characters")
    return errors


def validate_engine_identity(report: object) -> None:
    """Reject an unresolved new Axiom publication; never infer an identity."""
    errors = engine_identity_errors(report)
    if errors:
        raise ValueError("; ".join(errors))


def load_legacy_allowlist(document: object) -> dict[str, str]:
    """Read the frozen path/digest exceptions, rejecting ambiguous entries."""
    if not isinstance(document, dict) or document.get("schema") != LEGACY_SCHEMA:
        raise ValueError("invalid legacy engine identity allow-list schema")
    reports = document.get("reports")
    if not isinstance(reports, dict):
        raise ValueError("legacy engine identity reports must be a path/digest object")
    for path, digest in reports.items():
        if (
            not isinstance(path, str)
            or Path(path).parent.as_posix() != DASHBOARD_DATA
            or not path.endswith(".json")
            or not isinstance(digest, str)
            or BINARY_SHA256.fullmatch(digest) is None
        ):
            raise ValueError(f"invalid legacy engine identity exception: {path!r}")
    return reports


def legacy_history_errors(repo_root: Path, legacy: Mapping[str, str]) -> list[str]:
    """The exception mapping may only shrink across committed history.

    CI uses a full checkout. Comparing every ancestor also prevents a revert
    from restoring a removed exception. The migration's initial file has no
    ancestor and establishes the baseline, like the other conformance floors.
    """
    history = subprocess.run(
        [
            "git", "--no-replace-objects", "log", "--full-history", "--format=%H",
            "HEAD", "--", LEGACY_ALLOWLIST,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        env=_git_env(),
    )
    for revision in history.stdout.splitlines():
        previous = subprocess.run(
            ["git", "--no-replace-objects", "show", f"{revision}:{LEGACY_ALLOWLIST}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=_git_env(),
        )
        # A commit deleting the list removes every exemption.
        baseline = (
            load_legacy_allowlist(json.loads(previous.stdout))
            if previous.returncode == 0
            else {}
        )
        added = sorted(path for path, digest in legacy.items() if baseline.get(path) != digest)
        if added:
            return [
                "legacy engine identity allow-list may only shrink; "
                f"added or changed since {revision}: {', '.join(added)}"
            ]
    return []


def publication_errors(
    report: object,
    *,
    path: str,
    content: bytes,
    legacy: Mapping[str, str],
) -> list[str]:
    """Validate new bytes, allowing only byte-identical historical reports."""
    if not is_axiom_report(report) and not Path(path).name.startswith("axiom-"):
        return []
    errors = engine_identity_errors(report)
    if errors and legacy.get(path) == hashlib.sha256(content).hexdigest():
        return []
    return errors


def check_publications(repo_root: Path, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Check tracked and newly generated top-level reports without changing them."""
    legacy = load_legacy_allowlist(json.loads((repo_root / LEGACY_ALLOWLIST).read_text()))
    errors = legacy_history_errors(repo_root, legacy)
    paths = subprocess.run(
        [
            "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
            f"{DASHBOARD_DATA}/*.json",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        env=_git_env(),
    ).stdout.split("\0")
    counts = {"axiom_reports": 0, "legacy_reports": 0, "unresolved_reports": 0}
    for relative in sorted(set(paths)):
        if not relative or Path(relative).parent.as_posix() != DASHBOARD_DATA:
            continue
        path = repo_root / relative
        if not path.exists():
            continue
        content = path.read_bytes()
        try:
            report = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            errors.append(f"{relative}: invalid JSON")
            continue
        if not is_axiom_report(report) and not path.name.startswith("axiom-"):
            continue
        counts["axiom_reports"] += 1
        identity_errors = engine_identity_errors(report)
        if identity_errors:
            counts["unresolved_reports"] += 1
            if legacy.get(relative) == hashlib.sha256(content).hexdigest():
                counts["legacy_reports"] += 1
        for error in publication_errors(
            report, path=relative, content=content, legacy=legacy if allow_legacy else {}
        ):
            errors.append(f"{relative}: {error}")
    return {**counts, "errors": errors}
