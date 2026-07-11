"""Resolve an exact canonical RuleSpec path to its jurisdiction prefix."""

from __future__ import annotations

from pathlib import Path

from .repo_routing import (
    canonical_rulespec_root_identity,
    find_policy_repo_root,
    is_policy_repo_root,
)


def jurisdiction_prefix(repo_path: Path) -> str:
    """Return the jurisdiction anchored by an exact checkout/root/path.

    Country checkouts resolve to their country jurisdiction.  Files and
    directories below a direct jurisdiction root resolve to that jurisdiction.
    Arbitrary directory names, flat legacy checkouts, and aliases are rejected.
    """

    path = Path(repo_path)
    content_root = find_policy_repo_root(path)
    if content_root is not None:
        identity = canonical_rulespec_root_identity(content_root)
        if identity is not None:
            return identity.split("/", 1)[1]
    if is_policy_repo_root(path):
        return path.resolve().name.removeprefix("rulespec-")
    raise ValueError(
        "path must be an exact canonical rulespec-<country> checkout, direct "
        "jurisdiction root, or path beneath that root"
    )
