"""Canonical country-checkout routing for RuleSpec content.

RuleSpec content has one supported on-disk shape::

    rulespec-<country>/<jurisdiction>/<canonical-root>/...

The five canonical content roots are ``legislation``, ``policies``,
``programs``, ``regulations``, and ``statutes``.  Flat jurisdiction
checkouts, workspaces containing a matching checkout, checkout aliases,
symlinked roots, and repository identities inferred from Git origin are not
accepted.  Callers must authorize the exact country checkout or one of its
direct jurisdiction children.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


RULESPEC_ATOMIC_ROOTS = frozenset(
    {"legislation", "policies", "regulations", "statutes"}
)
RULESPEC_FILESYSTEM_ROOTS = frozenset({*RULESPEC_ATOMIC_ROOTS, "programs"})


class _GitProbeError(RuntimeError):
    """Git identity could not be checked for an observed repository boundary."""


def jurisdiction_country(prefix: str) -> str:
    """Return the country portion of a jurisdiction prefix (us-ca -> us)."""
    return prefix.split("-", 1)[0]


def monorepo_checkout_name(prefix: str) -> str:
    """Return the canonical country-checkout name for a jurisdiction prefix."""
    return f"rulespec-{jurisdiction_country(prefix)}"


def _lexical_rulespec_path(path: Path) -> Path | None:
    """Return one absolute path only when no component is a symlink."""

    raw = Path(os.path.abspath(Path(path).expanduser()))
    if sys.platform == "darwin":
        for alias, expected_target in (
            (Path("/var"), Path("/private/var")),
            (Path("/tmp"), Path("/private/tmp")),
            (Path("/etc"), Path("/private/etc")),
        ):
            try:
                relative = raw.relative_to(alias)
            except ValueError:
                continue
            try:
                if alias.is_symlink() and alias.resolve(strict=True) == expected_target:
                    raw = expected_target / relative
            except OSError:
                pass
            break

    cursor = Path(raw.anchor)
    for part in raw.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            return None
    return raw


def _canonical_country_checkout_name(path: Path) -> str | None:
    """Return the exact canonical country-checkout name for ``path``."""

    lexical = _lexical_rulespec_path(path)
    if lexical is None or not lexical.is_dir():
        return None
    checkout = lexical.resolve()
    name = checkout.name
    if not name.startswith("rulespec-"):
        return None
    country = name.removeprefix("rulespec-")
    if re.fullmatch(r"[a-z]{2}", country) is None:
        return None
    nested_same_name = checkout / name
    if nested_same_name.exists() or nested_same_name.is_symlink():
        return None
    try:
        git_boundary = _nearest_git_boundary(checkout)
    except _GitProbeError:
        return None
    if git_boundary is not None and git_boundary != checkout:
        return None
    if git_boundary is None:
        return name
    try:
        git_top_level = _git_top_level(str(checkout))
    except _GitProbeError:
        return None
    if git_top_level != checkout:
        return None
    try:
        origin_name = _git_origin_repo_name(str(checkout))
    except _GitProbeError:
        return None
    if origin_name is not None and origin_name != name:
        return None
    return name


def canonical_rulespec_checkout_name(
    path: Path,
    *,
    require_exists: bool = True,
) -> str | None:
    """Return an exact ``rulespec-<country>`` checkout name.

    With ``require_exists=False``, a missing but lexically exact checkout path
    is accepted for declarative metadata such as comparison provenance. Existing
    paths always receive the full directory, symlink, Git-boundary, and origin
    verification.
    """

    lexical = _lexical_rulespec_path(path)
    if lexical is None:
        return None
    if lexical.exists() or require_exists:
        return _canonical_country_checkout_name(lexical)
    name = lexical.name
    country = name.removeprefix("rulespec-") if name.startswith("rulespec-") else ""
    return name if re.fullmatch(r"[a-z]{2}", country) else None


def canonical_rulespec_root_identity(path: Path) -> str | None:
    """Return the stable identity of an exact canonical jurisdiction root.

    For example, the direct ``us-co`` child of ``rulespec-us`` has identity
    ``rulespec-us/us-co``.  Checkout roots, files, flat legacy roots, nested
    directories, workspaces, and aliased checkout names return ``None``.
    """

    lexical = _lexical_rulespec_path(path)
    if lexical is None:
        return None
    content_root = lexical.resolve()
    if not content_root.is_dir():
        return None
    jurisdiction = content_root.name
    checkout = content_root.parent
    expected_checkout = monorepo_checkout_name(jurisdiction)
    if checkout.name != expected_checkout:
        return None
    if _canonical_country_checkout_name(checkout) != expected_checkout:
        return None
    country = jurisdiction_country(jurisdiction)
    if not _is_jurisdiction_dir_name(jurisdiction, country):
        return None
    return f"{expected_checkout}/{jurisdiction}"


def is_policy_repo_root(path: Path) -> bool:
    """Return True for an exact canonical country checkout root."""

    return canonical_rulespec_checkout_name(Path(path)) is not None


def is_jurisdiction_content_root(path: Path) -> bool:
    """Return True for an exact direct jurisdiction child of a checkout."""

    return canonical_rulespec_root_identity(path) is not None


def find_policy_repo_root(path: Path) -> Path | None:
    """Return the canonical jurisdiction content root containing ``path``."""

    lexical = _lexical_rulespec_path(path)
    if lexical is None:
        return None
    current = lexical.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if canonical_rulespec_root_identity(candidate) is not None:
            return candidate
    return None


def canonical_rulespec_repo_name(path: Path) -> str | None:
    """Return the exact country-checkout repository name for ``path``."""

    lexical = _lexical_rulespec_path(path)
    if lexical is None:
        return None
    current = lexical.resolve()
    content_root = find_policy_repo_root(current)
    if content_root is not None:
        return content_root.parent.name
    return _canonical_country_checkout_name(current)


def candidate_jurisdiction_content_dirs(base: Path, prefix: str) -> list[Path]:
    """Return the one canonical content root explicitly authorized by ``base``.

    ``base`` must be either the exact country checkout or the exact matching
    jurisdiction root.  Workspace, sibling, ambient-environment, and Git-origin
    discovery is not performed.  The direct child is not existence-checked.
    """

    lexical = _lexical_rulespec_path(base)
    if lexical is None:
        return []
    base = lexical.resolve()
    expected_checkout = monorepo_checkout_name(prefix)
    if (
        base.name == expected_checkout
        and _canonical_country_checkout_name(base) == expected_checkout
    ):
        return [base / prefix]
    if canonical_rulespec_root_identity(base) == f"{expected_checkout}/{prefix}":
        return [base]
    return []


def jurisdiction_subdir_names(checkout: Path) -> set[str]:
    """Return direct jurisdiction children of one exact country checkout."""

    lexical = _lexical_rulespec_path(checkout)
    if lexical is None:
        return set()
    checkout = lexical.resolve()
    checkout_name = _canonical_country_checkout_name(checkout)
    if checkout_name is None:
        return set()
    country = checkout_name.removeprefix("rulespec-")
    return {
        child.name
        for child in checkout.iterdir()
        if not child.is_symlink()
        and child.is_dir()
        and _is_jurisdiction_dir_name(child.name, country)
    }


def iter_jurisdiction_content_dirs(
    rulespec_root: Path,
) -> list[tuple[str, Path]]:
    """Enumerate jurisdiction roots under one explicit canonical input.

    A country checkout yields all of its direct jurisdiction roots.  A direct
    jurisdiction root yields only itself.  Any other path yields no results.
    """

    lexical = _lexical_rulespec_path(rulespec_root)
    if lexical is None:
        return []
    root = lexical.resolve()
    if identity := canonical_rulespec_root_identity(root):
        return [(identity.split("/", 1)[1], root)]
    if not is_policy_repo_root(root):
        return []
    return [(name, root / name) for name in sorted(jurisdiction_subdir_names(root))]


def canonical_rulespec_module_path(
    rulespec_file: Path,
    *,
    content_root: Path,
) -> Path | None:
    """Return an exact canonical ``.yaml`` module path, or ``None``.

    The module must be a regular, non-symlinked file beneath one of the five
    canonical roots of the explicitly supplied jurisdiction content root.
    """

    if canonical_rulespec_root_identity(content_root) is None:
        return None
    lexical_file = _lexical_rulespec_path(rulespec_file)
    if lexical_file is None or not lexical_file.is_file():
        return None
    resolved_root = Path(content_root).resolve()
    resolved_file = lexical_file.resolve()
    try:
        relative = resolved_file.relative_to(resolved_root)
    except ValueError:
        return None
    if (
        len(relative.parts) < 2
        or relative.parts[0] not in RULESPEC_ATOMIC_ROOTS
        or relative.suffix != ".yaml"
    ):
        return None
    return resolved_file


def canonical_program_spec_path(
    spec_file: Path,
    *,
    content_root: Path,
) -> Path | None:
    """Return an exact declarative ProgramSpec path, or ``None``.

    Program specs occupy the fifth filesystem root but are never atomic
    RuleSpec modules. This validator keeps that path contract distinct from
    ``canonical_rulespec_module_path``.
    """

    if canonical_rulespec_root_identity(content_root) is None:
        return None
    lexical_file = _lexical_rulespec_path(spec_file)
    if lexical_file is None or not lexical_file.is_file():
        return None
    resolved_root = Path(content_root).resolve()
    resolved_file = lexical_file.resolve()
    try:
        relative = resolved_file.relative_to(resolved_root)
    except ValueError:
        return None
    if (
        len(relative.parts) < 3
        or relative.parts[0] != "programs"
        or relative.suffix != ".yaml"
        or relative.name.endswith(".test.yaml")
    ):
        return None
    return resolved_file


def _is_jurisdiction_dir_name(name: str, country: str) -> bool:
    """Return whether ``name`` is a jurisdiction of ``country``."""

    if re.fullmatch(r"[a-z]{2}", country) is None:
        return False
    return re.fullmatch(rf"{re.escape(country)}(?:-[a-z0-9]+)*", name) is not None


def _nearest_git_boundary(path: Path) -> Path | None:
    """Return the nearest lexical ``.git`` boundary without invoking Git."""

    for candidate in (path, *path.parents):
        marker = candidate / ".git"
        if marker.is_symlink():
            raise _GitProbeError(f"Git boundary is a symlink: {marker}")
        if marker.exists():
            return candidate
    return None


def _git_top_level(root: str) -> Path | None:
    """Return the exact Git worktree root containing ``root``, when present."""

    try:
        completed = subprocess.run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _GitProbeError(f"Could not inspect Git top-level for {root}") from exc
    if completed.returncode != 0:
        return None
    top_level = completed.stdout.strip()
    return Path(top_level).resolve() if top_level else None


def _git_origin_repo_name(root: str) -> str | None:
    """Return a repository basename from Git origin when configured."""

    try:
        completed = subprocess.run(
            ["git", "-C", root, "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _GitProbeError(f"Could not inspect Git origin for {root}") from exc
    if completed.returncode != 0:
        return None
    remote = completed.stdout.strip().rstrip("/")
    if not remote:
        return None
    name = remote.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name.removesuffix(".git") or None
