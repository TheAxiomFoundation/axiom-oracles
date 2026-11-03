"""Helpers for naming RuleSpec checkouts and their jurisdiction directories.

RuleSpec content lives in one checkout per country,
``rulespec-<country>/<prefix>/...``: one repository per country holding a
directory per jurisdiction (``rulespec-us/us/`` for federal content,
``rulespec-us/us-ca/``, ``rulespec-uk/uk-kingston-upon-thames/``, ...). The
country is the jurisdiction prefix up to the first ``-``.

Which checkouts the rules engine may read is decided by
:mod:`axiom_oracles.rulespec_roots`. The helpers here only name checkouts and
enumerate jurisdiction directories for coverage reports and output ids.
Coverage still names a per-jurisdiction ``rulespec-<prefix>`` checkout it
finds in a workspace, but no runtime path compiles from one. The legacy
discovery helpers (workspace candidate lists, content-root resolution,
legacy-to-monorepo path rewriting) were removed with the canonical RuleSpec
hard cut; nothing called them.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path


def jurisdiction_country(prefix: str) -> str:
    """Return the country portion of a jurisdiction repo prefix (us-ca -> us)."""
    return prefix.split("-", 1)[0]


def monorepo_checkout_name(prefix: str) -> str:
    """Return the country monorepo repository name for a jurisdiction prefix."""
    return f"rulespec-{jurisdiction_country(prefix)}"


def legacy_checkout_name(prefix: str) -> str:
    """Return the legacy per-jurisdiction repository name for a prefix."""
    return f"rulespec-{prefix}"


def canonical_rulespec_repo_name(path: Path) -> str | None:
    """Return the canonical `rulespec-*` repo name for a checkout when known.

    Temp checkouts resolve through their Git origin (``rulespec-us-clean.abcd``
    with origin ``rulespec-us`` -> ``rulespec-us``). Paths under a first-level
    jurisdiction directory of a country monorepo resolve to that
    jurisdiction's canonical legacy repo name:
    ``<rulespec-us>/us-ca/...`` -> ``rulespec-us-ca``.
    """
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent

    root: Path | None = None
    for candidate in (current, *current.parents):
        if candidate.name.startswith("rulespec-"):
            root = candidate
            break

    base = root if root is not None else current
    origin_name = _git_origin_repo_name(str(base))
    if origin_name and origin_name.startswith("rulespec-"):
        checkout_name = origin_name
    elif base.name.startswith("rulespec-"):
        checkout_name = base.name
    else:
        return None

    if root is not None:
        suffix = checkout_name.removeprefix("rulespec-")
        subdir = _jurisdiction_subdir_under(root, current, suffix=suffix)
        if subdir is not None:
            return f"rulespec-{subdir}"
        if current != root and jurisdiction_subdir_names(root):
            return None
    return checkout_name


def jurisdiction_subdir_names(checkout: Path) -> set[str]:
    """Return the first-level jurisdiction directory names of a checkout.

    Empty for legacy checkouts; for a country monorepo this is the set of
    per-jurisdiction directories (``{"us", "us-ca", ...}``).
    """
    checkout = Path(checkout)
    suffix = _checkout_suffix(checkout)
    if suffix is None or not checkout.is_dir():
        return set()
    return {
        child.name
        for child in checkout.iterdir()
        if child.is_dir() and _is_jurisdiction_dir_name(child.name, suffix)
    }


def iter_jurisdiction_content_dirs(workspace_root: Path) -> list[tuple[str, Path]]:
    """Enumerate ``(prefix, content_root)`` for checkouts under a workspace.

    Legacy checkouts contribute themselves under their name suffix; country
    monorepo checkouts contribute each first-level jurisdiction directory.
    A monorepo whose country content still sits at the repository root (a
    partially migrated checkout) contributes the root under the country
    prefix as well — callers walking such a root should skip the jurisdiction
    subdirectories via ``jurisdiction_subdir_names``.
    """
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()

    def add(prefix: str, content_dir: Path) -> None:
        resolved = content_dir.resolve()
        if resolved not in seen:
            seen.add(resolved)
            out.append((prefix, content_dir))

    root = Path(workspace_root)
    candidate_checkouts = []
    if (
        root.is_dir()
        and root.name.startswith("rulespec-")
        and not (root / root.name).is_dir()
    ):
        candidate_checkouts.append(root)
    candidate_checkouts.extend(sorted(root.glob("rulespec-*")))

    for checkout in candidate_checkouts:
        if not checkout.is_dir():
            continue
        suffix = _checkout_suffix(checkout)
        if suffix is None:
            continue
        subdir_names = jurisdiction_subdir_names(checkout)
        for name in sorted(subdir_names):
            add(name, checkout / name)
        if suffix not in subdir_names:
            add(suffix, checkout)
    return out


def _is_jurisdiction_dir_name(name: str, suffix: str) -> bool:
    """Return whether a directory name is a jurisdiction dir of ``rulespec-<suffix>``."""
    return name == suffix or name.startswith(f"{suffix}-")


def _jurisdiction_subdir_under(
    repo_root: Path,
    descendant: Path,
    *,
    suffix: str | None = None,
) -> str | None:
    """Return the first-level jurisdiction dir of ``repo_root`` holding ``descendant``."""
    if suffix is None:
        suffix = _checkout_suffix(repo_root)
    if not suffix:
        return None
    try:
        parts = Path(descendant).relative_to(repo_root).parts
    except ValueError:
        return None
    if not parts:
        return None
    head = parts[0]
    return head if _is_jurisdiction_dir_name(head, suffix) else None


def _checkout_suffix(checkout: Path) -> str | None:
    """Return a checkout's jurisdiction suffix (Git origin beats dir name)."""
    origin_name = _git_origin_repo_name(str(checkout))
    name = (
        origin_name
        if origin_name and origin_name.startswith("rulespec-")
        else checkout.name
    )
    if not name.startswith("rulespec-"):
        return None
    return name.removeprefix("rulespec-") or None


@lru_cache(maxsize=256)
def _git_origin_repo_name(root: str) -> str | None:
    """Best-effort repository basename from Git origin."""
    try:
        completed = subprocess.run(
            ["git", "-C", root, "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    remote = completed.stdout.strip().rstrip("/")
    if not remote:
        return None
    name = remote.rsplit("/", 1)[-1]
    return name.removesuffix(".git") or None
