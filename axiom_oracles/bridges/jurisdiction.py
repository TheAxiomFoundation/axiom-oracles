"""Map a rules/rulespec repo path to its jurisdiction anchor prefix.

Repo names are encoded as `rulespec-<jurisdiction>` or `rules-<jurisdiction>`
(e.g. `rules-us-co`, `rulespec-us-ny`, `rulespec-uk`). The jurisdiction
prefix is the suffix after the repo-kind prefix and is used as the anchor
scheme in `<jurisdiction>:<path>#<name>` RuleSpec references.

Inside a country monorepo checkout the jurisdiction directory carries the
anchor: `<rulespec-us>/us-ca` (or a path beneath it) resolves to `us-ca`,
exactly as the legacy `rulespec-us-ca` sibling checkout did.
"""

from __future__ import annotations

from pathlib import Path

from .repo_routing import canonical_rulespec_repo_name


def jurisdiction_prefix(repo_path: Path) -> str:
    name = canonical_rulespec_repo_name(repo_path) or repo_path.name
    if name.startswith("rulespec-"):
        return name.removeprefix("rulespec-")
    if name.startswith("rules-"):
        return name.removeprefix("rules-")
    return name
