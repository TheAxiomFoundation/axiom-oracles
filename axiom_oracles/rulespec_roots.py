"""Canonical RuleSpec checkout validation for every engine invocation.

The rules engine resolves RuleSpec modules only from the roots it is handed.
This module decides which directories may be handed to it. A root is
canonical when all of the following hold:

* the path resolves to an existing directory named ``rulespec-<cc>``, with
  ``<cc>`` two lowercase ASCII letters (``rulespec-us``, ``rulespec-uk``).
  Per-jurisdiction checkouts (``rulespec-us-co``), renamed copies
  (``rulespec-us-clean``, a real ``rulespec-uk-official`` directory) and
  workspaces are not roots. A symlink may point at a canonical checkout; the
  engine always receives the resolved checkout, never the link;
* the directory does not contain a child of its own name, which would make
  the checkout ambiguous with a workspace holding it;
* when the directory is inside a Git work tree, it is that work tree's top
  level, and the basename of its ``origin`` remote, when one is configured,
  equals the directory name, ignoring case as GitHub does. A subdirectory
  of another repository and a checkout of a differently named repository
  are both refused.

A directory outside any Git work tree passes on its name alone. That covers
the staged copies :mod:`axiom_oracles.engine_compat` builds from a canonical
checkout and the materialized SNAP QC overlay, both of which are derived from
a checkout that already passed this check.

The module has no dependencies beyond the standard library so that any
caller, including scripts loaded by file path, can import it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: Exact canonical checkout name.
CANONICAL_ROOT_NAME = re.compile(r"^rulespec-[a-z]{2}$")

#: Environment variables older engines read their roots from. A runtime call
#: never forwards an inherited value of either.
AMBIENT_ROOT_ENV_VARS = (
    "AXIOM_RULESPEC_REPO_ROOTS",
    "AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE",
)

class NonCanonicalRuleSpecRoot(ValueError):
    """A directory offered as an engine root is not a canonical checkout."""


def _git_dir(top: Path) -> Path | None:
    """Return the Git directory a work tree's ``.git`` entry points at."""
    marker = top / ".git"
    if marker.is_dir():
        return marker
    try:
        text = marker.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        if line.startswith("gitdir:"):
            target = Path(line.removeprefix("gitdir:").strip())
            return (target if target.is_absolute() else top / target).resolve()
    return None


def _git_config(top: Path) -> Path | None:
    """Return the config file holding a work tree's remotes."""
    git_dir = _git_dir(top)
    if git_dir is None:
        return None
    commondir = git_dir / "commondir"
    if commondir.is_file():
        try:
            common = Path(commondir.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError):
            return None
        git_dir = (common if common.is_absolute() else git_dir / common).resolve()
    return git_dir / "config"


def _origin_url(config: Path) -> str | None:
    """Return ``remote.origin.url`` from a Git config file, if set."""
    section = None
    url = None
    for raw in config.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            section = re.sub(r"\s+", " ", line.strip("[]").strip())
            continue
        if section == 'remote "origin"':
            key, _, value = line.partition("=")
            if key.strip().lower() == "url":
                url = value.strip().strip('"')
    return url


def _git_problem(checkout: Path, name: str) -> str | None:
    """Return why ``checkout``'s Git identity disqualifies it, if it does.

    Reads ``.git`` entries from the filesystem rather than running ``git``,
    so the result does not depend on the ``git`` binary or its environment.
    """
    for candidate in (checkout, *checkout.parents):
        marker = candidate / ".git"
        if marker.exists() or marker.is_symlink():
            top = candidate
            break
    else:
        return None
    if top != checkout:
        return f"it is inside the Git work tree {top}, not its top level"
    config = _git_config(checkout)
    if config is None:
        return "its .git entry does not name a readable Git directory"
    if not config.is_file():
        return None
    try:
        url = _origin_url(config)
    except (OSError, UnicodeDecodeError) as exc:
        return f"its Git config could not be read: {exc}"
    url = (url or "").rstrip("/")
    if not url:
        return None
    origin = re.split(r"[/:]", url)[-1].removesuffix(".git")
    # GitHub repository names are case-insensitive.
    if origin.casefold() != name:
        return f"its origin is {origin!r}, not {name!r}"
    return None


def canonical_root_problem(path: Path | str) -> str | None:
    """Return why ``path`` is not a canonical root, or ``None`` when it is."""
    given = Path(os.path.abspath(os.path.expanduser(str(path))))
    try:
        resolved = given.resolve(strict=True)
    except (OSError, RuntimeError):
        return "it does not exist"
    name = resolved.name
    if not CANONICAL_ROOT_NAME.match(name):
        return f"its name {name!r} is not rulespec-<two-letter country>"
    if not resolved.is_dir():
        return "it is not a directory"
    nested = resolved / name
    if nested.exists() or nested.is_symlink():
        return f"it contains a nested {name!r}, so it is ambiguous with a workspace"
    return _git_problem(resolved, name)


def canonical_rulespec_root(path: Path | str) -> Path | None:
    """Return the resolved canonical checkout for ``path``, or ``None``."""
    if canonical_root_problem(path) is not None:
        return None
    return Path(os.path.abspath(os.path.expanduser(str(path)))).resolve()


def require_canonical_rulespec_root(
    path: Path | str, *, country: str | None = None
) -> Path:
    """Return the resolved canonical checkout for ``path`` or raise.

    Raises :class:`NonCanonicalRuleSpecRoot` (a ``ValueError``) naming the
    reason. With ``country``, the checkout must be ``rulespec-<country>``.
    """
    problem = canonical_root_problem(path)
    resolved = Path(os.path.abspath(os.path.expanduser(str(path)))).resolve()
    if problem is None and country is not None:
        expected = f"rulespec-{country}"
        if resolved.name != expected:
            problem = f"it is not {expected!r}"
    if problem is not None:
        raise NonCanonicalRuleSpecRoot(
            f"RuleSpec root {path} is not a canonical rulespec-<country> "
            f"checkout: {problem}"
        )
    return resolved


def engine_env(
    env: dict[str, str] | None, roots: list[Path] | None = None
) -> dict[str, str]:
    """Return an engine environment that carries no inherited root list.

    ``env`` defaults to the current process environment. Inherited
    :data:`AMBIENT_ROOT_ENV_VARS` are removed. With ``roots``, each is checked
    with :func:`require_canonical_rulespec_root` and the list is written to
    ``AXIOM_RULESPEC_REPO_ROOTS`` for engines that predate the explicit
    ``--rulespec-root`` flag.
    """
    out = dict(os.environ if env is None else env)
    for key in AMBIENT_ROOT_ENV_VARS:
        out.pop(key, None)
    if roots:
        out["AXIOM_RULESPEC_REPO_ROOTS"] = os.pathsep.join(
            str(require_canonical_rulespec_root(root)) for root in roots
        )
    return out
