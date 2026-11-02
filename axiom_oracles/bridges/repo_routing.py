"""Helpers for resolving jurisdiction RuleSpec repos versus the rules engine.

Two on-disk layouts are supported for jurisdiction RuleSpec content. Wherever
a jurisdiction's checkout is located, candidates are tried in this order:

1. Country monorepo: ``rulespec-<country>/<prefix>/...`` — one repository per
   country holding a directory per jurisdiction (``rulespec-us/us/`` for
   federal content, ``rulespec-us/us-ca/``, ``rulespec-uk/uk-kingston-upon-thames/``,
   ...), plus shared non-encoding directories such as ``programs/``. The
   country is the jurisdiction prefix up to the first ``-``.
2. Legacy sibling checkouts: ``rulespec-<prefix>/...`` — one repository per
   jurisdiction with encoding buckets at the repository root.

The "content root" for a jurisdiction is the directory its ``<prefix>:...``
references resolve against: the jurisdiction directory inside a monorepo, or
the repository root of a legacy checkout. Durable references are unchanged
across layouts — ``us-ca:regulations/mpp/63-300/1`` resolves to
``<rulespec-us>/us-ca/regulations/mpp/63-300/1.yaml`` in the monorepo layout
and ``<rulespec-us-ca>/regulations/mpp/63-300/1.yaml`` in the legacy layout.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
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


def is_policy_repo_root(path: Path) -> bool:
    """Return True when a path is the root of a jurisdiction RuleSpec repo."""
    name = Path(path).resolve().name
    return name.startswith("rulespec-")


def is_jurisdiction_content_root(path: Path) -> bool:
    """Return True when ``path`` anchors a jurisdiction's RuleSpec content.

    Either a ``rulespec-*`` checkout root (legacy layout) or a first-level
    jurisdiction directory inside a country monorepo checkout
    (``<rulespec-us>/us-ca``).
    """
    candidate = Path(path).resolve()
    if candidate.name.startswith("rulespec-"):
        return True
    parent = candidate.parent
    if not parent.name.startswith("rulespec-"):
        return False
    return _jurisdiction_subdir_under(parent, candidate) is not None


def find_policy_repo_root(path: Path) -> Path | None:
    """Walk upward from a file or directory to its jurisdiction content root.

    Legacy checkouts resolve to the enclosing ``rulespec-*`` repository root.
    Inside a country monorepo checkout, the jurisdiction directory is the
    policy root: ``<rulespec-us>/us-ca/regulations/x.yaml`` resolves to
    ``<rulespec-us>/us-ca`` so repo-relative paths and ``us-ca:`` references
    keep their legacy shape.
    """
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if is_policy_repo_root(candidate):
            subdir = _jurisdiction_subdir_under(candidate, current)
            return candidate / subdir if subdir else candidate
    return None


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


def jurisdiction_content_dir(checkout: Path, prefix: str) -> Path:
    """Return the content root for ``prefix`` inside a checkout, either layout.

    ``<checkout>/<prefix>`` when that directory exists (country monorepo),
    otherwise the checkout root itself (legacy layout, including a monorepo
    whose country content has not moved into its jurisdiction directory yet).
    """
    checkout = Path(checkout)
    subdir = checkout / prefix
    return subdir if subdir.is_dir() else checkout


def candidate_jurisdiction_content_dirs(base: Path, prefix: str) -> list[Path]:
    """Return ordered candidate content roots for ``prefix`` relative to ``base``.

    ``base`` may be the jurisdiction's own checkout (legacy name, monorepo
    jurisdiction directory, or a temp checkout resolved via Git origin), a
    country monorepo checkout, or a workspace directory holding checkouts.
    Monorepo candidates come before legacy ones. Candidates are not
    existence-checked; callers filter with ``is_dir()`` / ``exists()``.
    """
    base = Path(base).expanduser()
    legacy_name = legacy_checkout_name(prefix)
    monorepo_name = monorepo_checkout_name(prefix)
    names = {base.name, canonical_rulespec_repo_name(base)}
    if legacy_name in names:
        # The jurisdiction's own checkout: its content root in either layout.
        return [jurisdiction_content_dir(base, prefix)]
    if monorepo_name in names:
        if base.name.startswith("rulespec-"):
            # A country monorepo checkout holding this jurisdiction's directory.
            return [base / prefix]
        # The country's own jurisdiction directory inside a monorepo
        # (`rulespec-us/us`): siblings live next to it, not inside it.
        return [base.parent / prefix]
    # A workspace directory holding checkouts: monorepo first, then legacy.
    return [base / monorepo_name / prefix, base / legacy_name]


def resolve_jurisdiction_content_dir(
    bases: Iterable[Path],
    prefix: str,
) -> Path | None:
    """Return the first existing content root for ``prefix`` across ``bases``."""
    for base in bases:
        for candidate in candidate_jurisdiction_content_dirs(base, prefix):
            if candidate.is_dir():
                return candidate
    return None


def monorepo_alternative_path(path: Path) -> Path | None:
    """Map a legacy-layout path to its country-monorepo equivalent.

    ``.../rulespec-<prefix>/<rest>`` becomes
    ``.../rulespec-<country>/<prefix>/<rest>``; for country-level content the
    jurisdiction directory is inserted (``rulespec-us/statutes/...`` ->
    ``rulespec-us/us/statutes/...``). The innermost ``rulespec-*`` component
    wins so nested checkouts (``.../_axiom/rulespec-us/...``) rewrite
    correctly. Returns ``None`` when the path has no ``rulespec-*`` component.
    The result is not existence-checked.
    """
    parts = Path(path).parts
    for index in range(len(parts) - 1, -1, -1):
        part = parts[index]
        if not part.startswith("rulespec-"):
            continue
        prefix = part.removeprefix("rulespec-")
        if not prefix:
            continue
        candidate = Path(
            *parts[:index],
            monorepo_checkout_name(prefix),
            prefix,
            *parts[index + 1 :],
        )
        return candidate if candidate != Path(path) else None
    return None


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
