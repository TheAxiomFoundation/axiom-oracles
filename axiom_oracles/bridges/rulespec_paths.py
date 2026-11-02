"""RuleSpec checkout-path and item-id helpers for the oracle bridge layer.

These helpers were extracted verbatim from
``axiom_encode.harness.validator_pipeline`` (TheAxiomFoundation/axiom-encode @
a314fc624967b4e990beb7d9ffc429dae6e26642) so that :mod:`.ecps_tax` can resolve
canonical ``rulespec-*`` compile paths and public item-id aliases without
depending on the encoder harness. They keep their original (underscored) names
because :mod:`.ecps_tax` is a verbatim copy that imports them by those names;
the encoder's own ``validator_pipeline`` retains its originals for its other
call sites.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .jurisdiction import jurisdiction_prefix
from .repo_routing import canonical_rulespec_repo_name, jurisdiction_subdir_names


def _rulespec_repo_alias_parent(policy_repo_path: Path) -> Path | None:
    """Expose a temp checkout under its canonical `rulespec-*` repo name."""
    canonical_name = canonical_rulespec_repo_name(policy_repo_path)
    return _rulespec_repo_alias_parent_for_root(policy_repo_path, canonical_name)


def _monorepo_rulespec_repo_alias(
    policy_repo_path: Path,
) -> tuple[Path, str] | None:
    """Expose a country monorepo root when validating one jurisdiction subdir."""
    policy_root = Path(policy_repo_path).resolve()
    monorepo_root = policy_root.parent
    if not monorepo_root.name.startswith("rulespec-"):
        return None
    if policy_root.name not in jurisdiction_subdir_names(monorepo_root):
        return None
    canonical_name = canonical_rulespec_repo_name(monorepo_root)
    alias_parent = _rulespec_repo_alias_parent_for_root(monorepo_root, canonical_name)
    if alias_parent is None or canonical_name is None:
        return None
    return alias_parent, canonical_name


def _is_canonical_monorepo_content_root(policy_repo_path: Path) -> bool:
    """Return true for a country content root inside its canonical checkout."""
    policy_root = Path(policy_repo_path).resolve()
    monorepo_root = policy_root.parent
    if not monorepo_root.name.startswith("rulespec-"):
        return False
    if policy_root.name not in jurisdiction_subdir_names(monorepo_root):
        return False
    return canonical_rulespec_repo_name(monorepo_root) == monorepo_root.name


def _rulespec_repo_alias_parent_for_root(
    rulespec_root: Path,
    canonical_name: str | None,
) -> Path | None:
    """Expose a checkout root under a canonical `rulespec-*` repo name."""
    if not canonical_name or Path(rulespec_root).name == canonical_name:
        return None

    resolved_repo = Path(rulespec_root).resolve()
    digest = hashlib.sha256(str(resolved_repo).encode()).hexdigest()[:16]
    alias_parent = Path(tempfile.gettempdir()) / "axiom-rulespec-repo-aliases" / digest
    alias_parent.mkdir(parents=True, exist_ok=True)
    alias = alias_parent / canonical_name
    if alias.exists() or alias.is_symlink():
        with contextlib.suppress(OSError, RuntimeError):
            if alias.resolve() == resolved_repo:
                return alias_parent
        if alias.is_symlink() or alias.is_file():
            alias.unlink()
        else:
            shutil.rmtree(alias)
    alias.symlink_to(resolved_repo, target_is_directory=True)
    return alias_parent


def _canonical_rulespec_compile_path(
    rules_file: Path,
    policy_repo_path: Path,
) -> Path:
    """Return a compile path under the canonical repo alias when needed."""
    monorepo_alias = _monorepo_rulespec_repo_alias(policy_repo_path)
    if monorepo_alias is not None:
        monorepo_alias_parent, monorepo_canonical_name = monorepo_alias
        try:
            relative = rules_file.resolve().relative_to(
                Path(policy_repo_path).resolve().parent
            )
        except ValueError:
            return rules_file
        return monorepo_alias_parent / monorepo_canonical_name / relative
    if _is_canonical_monorepo_content_root(policy_repo_path):
        return rules_file

    alias_parent = _rulespec_repo_alias_parent(policy_repo_path)
    canonical_name = canonical_rulespec_repo_name(policy_repo_path)
    if alias_parent is None or canonical_name is None:
        return rules_file
    try:
        relative = rules_file.resolve().relative_to(policy_repo_path.resolve())
    except ValueError:
        return rules_file
    return alias_parent / canonical_name / relative


def _rulespec_public_item_key(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return item_id
    return str(item.get("name") or "").strip()


def _canonical_rulespec_item_id_alias(
    item_id: str,
    *,
    policy_repo_path: Path,
) -> str | None:
    if ":" not in item_id:
        return None
    raw_prefix, raw_path = item_id.split(":", 1)
    canonical_prefix = jurisdiction_prefix(policy_repo_path)
    local_prefixes = _rulespec_local_item_prefixes(policy_repo_path)
    if raw_prefix != canonical_prefix and raw_prefix not in local_prefixes:
        return None
    canonical_path = _canonical_rulespec_item_path_for_policy_root(
        raw_path,
        policy_repo_path=policy_repo_path,
        canonical_prefix=canonical_prefix,
    )
    alias = f"{canonical_prefix}:{canonical_path}"
    if alias == item_id:
        return None
    return alias


def _rulespec_local_item_prefixes(policy_repo_path: Path) -> set[str]:
    """Return noncanonical prefixes the engine may stamp for this checkout."""
    canonical_prefix = jurisdiction_prefix(policy_repo_path)
    prefixes: set[str] = set()
    current = Path(policy_repo_path).resolve()
    for candidate in (current, *current.parents):
        name = candidate.name
        if name.startswith("rulespec-"):
            prefixes.add(name.removeprefix("rulespec-"))
            break
    local_prefix = Path(policy_repo_path).name.removeprefix("rulespec-")
    if local_prefix:
        prefixes.add(local_prefix)
    canonical_name = canonical_rulespec_repo_name(policy_repo_path)
    if canonical_name and canonical_name.startswith("rulespec-"):
        prefixes.add(canonical_name.removeprefix("rulespec-"))
    prefixes.discard(canonical_prefix)
    return {prefix for prefix in prefixes if prefix}


def _rulespec_content_prefix_segment(
    *,
    policy_repo_path: Path,
    canonical_prefix: str,
) -> str | None:
    """Return a monorepo content-root path segment when engine ids include it."""
    policy_path = Path(policy_repo_path)
    if policy_path.name == canonical_prefix and policy_path.parent.name.startswith(
        "rulespec-"
    ):
        return canonical_prefix
    if (policy_path / canonical_prefix).is_dir():
        return canonical_prefix
    return None


def _canonical_rulespec_item_path_for_policy_root(
    item_path: str,
    *,
    policy_repo_path: Path,
    canonical_prefix: str,
) -> str:
    content_segment = _rulespec_content_prefix_segment(
        policy_repo_path=policy_repo_path,
        canonical_prefix=canonical_prefix,
    )
    if content_segment and item_path.startswith(f"{content_segment}/"):
        return item_path.split("/", 1)[1]
    return item_path


def _rulespec_public_item_keys(
    item: Any,
    *,
    policy_repo_path: Path,
) -> set[str]:
    key = _rulespec_public_item_key(item)
    if not key:
        return set()
    keys = {key}
    if alias := _canonical_rulespec_item_id_alias(
        key,
        policy_repo_path=policy_repo_path,
    ):
        keys.add(alias)
    return keys
