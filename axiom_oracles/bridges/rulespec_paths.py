"""RuleSpec checkout-path and item-id helpers for the oracle bridge layer.

These helpers were extracted from
``axiom_encode.harness.validator_pipeline`` (TheAxiomFoundation/axiom-encode @
a314fc624967b4e990beb7d9ffc429dae6e26642) so that :mod:`.tax_populace` can
resolve compile paths and public item-id aliases without depending on the
encoder harness. They keep their original (underscored) names because the
encoder's shims import them by those names.

Compile paths follow the canonical RuleSpec hard cut
(:mod:`axiom_oracles.rulespec_roots`): a checkout is used only when it is a
canonical ``rulespec-<country>`` checkout or a direct jurisdiction directory
of one. Nothing here creates an alias of a checkout under another name; a
non-canonical checkout raises ``NonCanonicalRuleSpecRoot``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..rulespec_roots import NonCanonicalRuleSpecRoot, require_canonical_content_root
from .jurisdiction import jurisdiction_prefix
from .repo_routing import canonical_rulespec_repo_name


def _canonical_checkout_for(policy_repo_path: Path) -> Path:
    """Return the canonical checkout ``policy_repo_path`` names or sits in.

    See :func:`axiom_oracles.rulespec_roots.require_canonical_content_root`:
    the checkout itself or one of its direct jurisdiction directories.
    """
    return require_canonical_content_root(policy_repo_path)


def _rulespec_repo_alias_parent(policy_repo_path: Path) -> Path | None:
    """Return ``None`` for a canonical checkout; refuse anything else.

    Before the hard cut this exposed a renamed checkout through a temporary
    symlink carrying its canonical name. Renamed checkouts are now refused
    with ``NonCanonicalRuleSpecRoot`` instead of aliased.
    """
    _canonical_checkout_for(policy_repo_path)
    return None


def _canonical_rulespec_compile_path(
    rules_file: Path,
    policy_repo_path: Path,
) -> Path:
    """Return ``rules_file`` once its checkout is shown to be canonical.

    Raises ``NonCanonicalRuleSpecRoot`` when ``policy_repo_path`` is not a
    canonical checkout or a direct jurisdiction directory of one, or when
    ``rules_file`` lies outside that checkout.
    """
    checkout = _canonical_checkout_for(policy_repo_path)
    try:
        Path(rules_file).resolve().relative_to(checkout)
    except ValueError:
        raise NonCanonicalRuleSpecRoot(
            f"RuleSpec file {rules_file} is outside the canonical checkout {checkout}"
        ) from None
    return Path(rules_file)


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
