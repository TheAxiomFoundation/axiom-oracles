"""Exact canonical RuleSpec paths used by the oracle bridge layer."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .repo_routing import (
    RULESPEC_ATOMIC_ROOTS,
    canonical_program_spec_path,
    canonical_rulespec_module_path,
    canonical_rulespec_root_identity,
    find_policy_repo_root,
    is_policy_repo_root,
)


def require_rulespec_checkout(path: Path, *, country: str | None = None) -> Path:
    """Return one exact canonical country checkout or raise ``ValueError``."""

    raw_checkout = Path(path)
    if not is_policy_repo_root(raw_checkout):
        raise ValueError(
            "RuleSpec root must be an exact canonical rulespec-<country> checkout"
        )
    checkout = raw_checkout.resolve()
    if country is not None and checkout.name != f"rulespec-{country}":
        raise ValueError(
            f"RuleSpec root for {country!r} must be named rulespec-{country}"
        )
    return checkout


def resolve_rulespec_program(
    checkout: Path,
    *,
    jurisdiction: str,
    relative_path: Path,
    override: Path | None = None,
) -> Path:
    """Resolve an exact program under a canonical jurisdiction content root."""

    checkout = require_rulespec_checkout(
        checkout,
        country=jurisdiction.split("-", 1)[0],
    )
    content_root = checkout / jurisdiction
    if canonical_rulespec_root_identity(content_root) is None:
        raise ValueError(f"RuleSpec jurisdiction root is not canonical: {content_root}")
    candidate = Path(override) if override is not None else content_root / relative_path
    return require_rulespec_module(candidate, checkout)


def resolve_rulespec_module_ref(checkout: Path, module_ref: str) -> Path:
    """Resolve one extensionless absolute module reference under ``checkout``."""

    checkout = require_rulespec_checkout(checkout)
    if "#" in module_ref or module_ref.count(":") != 1:
        raise ValueError(f"invalid absolute RuleSpec module reference: {module_ref!r}")
    jurisdiction, relative = module_ref.split(":", 1)
    country = checkout.name.removeprefix("rulespec-")
    relative_path = Path(relative.strip("/"))
    if (
        re.fullmatch(rf"{re.escape(country)}(?:-[a-z0-9]+)*", jurisdiction) is None
        or not relative.strip("/")
        or relative_path.is_absolute()
        or any(part in {"", ".", ".."} for part in relative_path.parts)
        or relative_path.parts[0] not in RULESPEC_ATOMIC_ROOTS
        or relative_path.suffix in {".yaml", ".yml"}
    ):
        raise ValueError(f"invalid canonical RuleSpec module reference: {module_ref!r}")
    return resolve_rulespec_program(
        checkout,
        jurisdiction=jurisdiction,
        relative_path=Path(f"{relative_path}.yaml"),
    )


def require_axiom_binary(path: Path) -> Path:
    """Return an exact executable regular file with no symlink components."""

    raw = Path(os.path.abspath(Path(path).expanduser()))
    cursor = Path(raw.anchor)
    for part in raw.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"axiom-rules-engine binary path is symlinked: {cursor}")
    binary = raw.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f"axiom-rules-engine binary is not executable: {binary}")
    return binary


def require_axiom_compiled_artifact(path: Path) -> Path:
    """Return an exact regular compiled artifact with no symlink components."""

    raw = Path(os.path.abspath(Path(path).expanduser()))
    cursor = Path(raw.anchor)
    for part in raw.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"Axiom compiled artifact path is symlinked: {cursor}")
    artifact = raw.resolve()
    if not artifact.is_file():
        raise ValueError(f"Axiom compiled artifact is not a regular file: {artifact}")
    return artifact


def rulespec_engine_env() -> dict[str, str]:
    """Build an engine environment with legacy ambient roots removed."""

    env = os.environ.copy()
    env.pop("AXIOM_RULESPEC_REPO_ROOTS", None)
    env.pop("AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE", None)
    return env


def rulespec_root_args(checkout: Path) -> list[str]:
    """Render the engine's required explicit country-checkout argument."""

    return ["--rulespec-root", str(require_rulespec_checkout(checkout))]


def _authorized_rulespec_content_root(
    rules_file: Path,
    policy_repo_path: Path,
) -> Path | None:
    """Return the file's content root when explicitly authorized by the caller."""

    content_root = find_policy_repo_root(rules_file)
    if content_root is None:
        return None
    raw_authorized = Path(policy_repo_path)
    authorized = raw_authorized.resolve()
    if canonical_rulespec_root_identity(raw_authorized) is not None:
        return content_root if content_root == authorized else None
    if is_policy_repo_root(raw_authorized):
        return content_root if content_root.parent == authorized else None
    return None


def require_rulespec_module(
    rules_file: Path,
    policy_repo_path: Path,
) -> Path:
    """Return one exact canonical ``.yaml`` compile path.

    ``policy_repo_path`` must be the exact country checkout or the exact direct
    jurisdiction root containing ``rules_file``.  No temporary alias, legacy
    flat checkout, sibling workspace, Git-origin identity, or ``.yml`` path is
    accepted.
    """

    content_root = _authorized_rulespec_content_root(rules_file, policy_repo_path)
    canonical = (
        canonical_rulespec_module_path(rules_file, content_root=content_root)
        if content_root is not None
        else None
    )
    if canonical is None:
        raise ValueError(
            "RuleSpec program must be an exact .yaml module beneath one of the "
            "four atomic roots of the explicitly supplied "
            "rulespec-<country>/<jurisdiction> checkout/root"
        )
    return canonical


def require_program_spec(spec_file: Path, rulespec_root: Path) -> Path:
    """Return one exact declarative ProgramSpec under ``programs/``."""

    content_root = _authorized_rulespec_content_root(spec_file, rulespec_root)
    canonical = (
        canonical_program_spec_path(spec_file, content_root=content_root)
        if content_root is not None
        else None
    )
    if canonical is None:
        raise ValueError(
            "ProgramSpec must be an exact .yaml file beneath "
            "rulespec-<country>/<jurisdiction>/programs/<program>/"
        )
    return canonical


def _rulespec_public_item_key(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return item_id
    return str(item.get("name") or "").strip()


def _rulespec_public_item_keys(
    item: Any,
    *,
    policy_repo_path: Path,
) -> set[str]:
    """Return only the exact item key emitted by the canonical engine path.

    ``policy_repo_path`` remains a required argument so callers cannot fall
    back to an ambient checkout contract.  It must itself be a canonical
    country checkout or jurisdiction root.  Legacy prefix/path aliases are
    intentionally not generated.
    """

    root = Path(policy_repo_path)
    if not is_policy_repo_root(root) and canonical_rulespec_root_identity(root) is None:
        raise ValueError("policy_repo_path must be an exact canonical RuleSpec root")
    key = _rulespec_public_item_key(item)
    return {key} if key else set()
