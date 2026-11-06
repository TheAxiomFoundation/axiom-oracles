"""Canonical RuleSpec checkout validation for every engine invocation.

The rules engine resolves RuleSpec modules only from the roots it is handed.
This module decides which directories may be handed to it. A root is
canonical when all of the following hold:

* the path, resolved the way the operating system opens it (symlinks first,
  then ``..``), is an existing directory named ``rulespec-<cc>``, with
  ``<cc>`` two lowercase ASCII letters (``rulespec-us``, ``rulespec-uk``).
  Per-jurisdiction checkouts (``rulespec-us-co``), renamed copies
  (``rulespec-us-clean``, a real ``rulespec-uk-official`` directory) and
  workspaces are not roots. A symlink may point at a canonical checkout; the
  engine always receives the resolved checkout, never the link;
* when the path as given is itself named ``rulespec-<cc>``, it resolves to a
  directory of that same name. A link named ``rulespec-uk`` that points at a
  ``rulespec-us`` checkout is refused; a link with a non-country name such as
  ``rulespec-uk-official`` may point at ``rulespec-uk``;
* the directory does not contain a child of its own name, which would make
  the checkout ambiguous with a workspace holding it;
* when the directory or one of its parents is a Git work tree, the directory
  is that work tree's top level, and its ``origin``, when one is configured,
  is ``TheAxiomFoundation/rulespec-<cc>`` on github.com over https or ssh,
  with or without ``.git``, compared case-insensitively. Host, port, path and
  owner/repository are read by :func:`axiom_oracles.provenance.parse_github_remote`
  and compared by :func:`axiom_oracles.provenance.remote_matches_slug`, the
  ones provenance uses, so the two cannot disagree on any origin. Forks, other
  hosts and ports, a subdirectory of another repository and a checkout of a
  differently named repository are refused.

A directory outside any Git work tree, and a checkout with no ``origin``,
pass on the rules above alone. That covers the staged copies
:mod:`axiom_oracles.engine_compat` builds from a canonical checkout, the
materialized SNAP QC overlay, and rsync'd copies under a canonical name.

Git state is read from the filesystem, not by running ``git``. The reader
follows git's rules for what counts as a repository (a ``.git`` directory
without ``HEAD``, ``objects`` and ``refs`` is not one) and for config syntax
(case-insensitive section and key names, quoting, escapes, inline comments).
It refuses rather than follows a config that could change the origin from
elsewhere: ``include`` and ``includeIf`` sections, ``url.<base>.insteadOf``
rewrites, ``extensions.worktreeConfig``, and more than one origin URL. It
reads only the repository's own config, not the user's or the system's.

The module depends only on the standard library and
:mod:`axiom_oracles.provenance`, which imports only the standard library at
module level.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from axiom_oracles.provenance import parse_github_remote, remote_matches_slug

#: Exact canonical checkout name.
CANONICAL_ROOT_NAME = re.compile(r"^rulespec-[a-z]{2}$")

#: GitHub owner of every canonical RuleSpec repository.
CANONICAL_OWNER = "TheAxiomFoundation"

#: Environment variables older engines read their roots from. A runtime call
#: never forwards an inherited value of either.
AMBIENT_ROOT_ENV_VARS = (
    "AXIOM_RULESPEC_REPO_ROOTS",
    "AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE",
)


class NonCanonicalRuleSpecRoot(ValueError):
    """A directory offered as an engine root is not a canonical checkout."""


class _UnreadableGitConfig(ValueError):
    """A Git config this reader refuses to interpret."""


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def given_path(path: Path | str) -> Path:
    """Absolute ``path`` with ``~`` expanded and ``..`` left for resolution.

    ``os.path.abspath`` would collapse ``link/..`` lexically, which can name a
    different directory than the one the operating system opens. Callers
    that look for the checkout enclosing a file walk this path's parents and
    validate the ``rulespec-*`` one they find, so both the name it was given
    under and the directory it opens are checked.
    """
    given = Path(os.path.expanduser(str(path)))
    return given if given.is_absolute() else Path.cwd() / given


_given_path = given_path


def _resolved(path: Path | str) -> Path:
    return _given_path(path).resolve()


# --------------------------------------------------------------------------- #
# Git config
# --------------------------------------------------------------------------- #

_ESCAPES = {"n": "\n", "t": "\t", "b": "\b", '"': '"', "\\": "\\"}


def _parse_git_config(text: str) -> list[tuple[str, str | None, str, str | None]]:
    """Parse Git config text into ``(section, subsection, key, value)`` rows.

    Section and key names are lowercased (they are case-insensitive in git);
    a quoted subsection keeps its case, a legacy ``[section.sub]`` one is
    lowercased. Values follow git-config(1): quotes are removed, escapes are
    decoded, an unquoted ``#`` or ``;`` starts a comment, trailing unquoted
    whitespace is dropped and a trailing backslash continues the line.
    """
    rows: list[tuple[str, str | None, str, str | None]] = []
    section: str | None = None
    subsection: str | None = None
    i, n = 0, len(text)

    def bad(why: str) -> _UnreadableGitConfig:
        return _UnreadableGitConfig(f"malformed Git config ({why})")

    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c in "#;":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "[":
            i += 1
            start = i
            while i < n and (text[i].isalnum() or text[i] in "-."):
                i += 1
            name = text[start:i]
            if not name:
                raise bad("empty section name")
            if i < n and text[i] == "]":
                i += 1
                if "." in name:
                    head, _, tail = name.partition(".")
                    section, subsection = head.lower(), tail.lower()
                else:
                    section, subsection = name.lower(), None
                continue
            while i < n and text[i] in " \t":
                i += 1
            if i >= n or text[i] != '"' or "." in name:
                raise bad("section header")
            i += 1
            sub: list[str] = []
            while True:
                if i >= n or text[i] == "\n":
                    raise bad("unterminated subsection")
                ch = text[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\" and i + 1 < n:
                    sub.append(text[i + 1])
                    i += 2
                    continue
                sub.append(ch)
                i += 1
            if i >= n or text[i] != "]":
                raise bad("section header")
            i += 1
            section, subsection = name.lower(), "".join(sub)
            continue
        if section is None:
            raise bad("entry before any section")
        start = i
        while i < n and (text[i].isalnum() or text[i] == "-"):
            i += 1
        key = text[start:i].lower()
        if not key:
            raise bad("entry name")
        while i < n and text[i] in " \t":
            i += 1
        if i >= n or text[i] in "\r\n" or text[i] in "#;":
            rows.append((section, subsection, key, None))
            continue
        if text[i] != "=":
            raise bad("missing '='")
        i += 1
        while i < n and text[i] in " \t":
            i += 1
        value: list[str] = []
        pending = ""
        quoted = False
        while i < n:
            ch = text[i]
            if ch == "\n":
                if quoted:
                    raise bad("newline inside quotes")
                break
            if ch == "\\":
                if i + 1 < n and text[i + 1] == "\n":
                    i += 2
                    continue
                if i + 2 < n and text[i + 1] == "\r" and text[i + 2] == "\n":
                    i += 3
                    continue
                esc = text[i + 1] if i + 1 < n else ""
                if esc not in _ESCAPES:
                    raise bad("unknown escape")
                value.append(pending + _ESCAPES[esc])
                pending = ""
                i += 2
                continue
            if ch == '"':
                quoted = not quoted
                value.append(pending)
                pending = ""
                i += 1
                continue
            if not quoted and ch in "#;":
                while i < n and text[i] != "\n":
                    i += 1
                break
            if not quoted and ch in " \t\r":
                pending += ch
                i += 1
                continue
            value.append(pending + ch)
            pending = ""
            i += 1
        if quoted:
            raise bad("unterminated quote")
        rows.append((section, subsection, key, "".join(value)))
    return rows


def _origin_url(config: Path) -> str | None:
    """Return the repository's single origin URL, or ``None`` when unset.

    Raises :class:`_UnreadableGitConfig` for a config that could set or
    rewrite the origin from elsewhere, or that sets it more than once.
    """
    rows = _parse_git_config(config.read_text(encoding="utf-8"))
    urls: list[str | None] = []
    for section, subsection, key, value in rows:
        if section in ("include", "includeif"):
            raise _UnreadableGitConfig("it uses include/includeIf")
        if section == "url":
            raise _UnreadableGitConfig("it rewrites URLs with url.<base>")
        if section == "extensions" and key == "worktreeconfig":
            raise _UnreadableGitConfig("it enables per-worktree config")
        if section == "remote" and subsection == "origin" and key == "url":
            urls.append(value)
    if len(urls) > 1:
        raise _UnreadableGitConfig("it sets more than one origin URL")
    return urls[0] if urls else None


def _canonical_origin(url: str, name: str) -> bool:
    """Is ``url`` ``TheAxiomFoundation/<name>`` on github.com over https/ssh?

    Provenance's parser reads the host and path, so the two cannot disagree
    on any origin form. An origin must be configured here: provenance reads
    an absent one as a match, and this check is never asked about one.
    """
    kind, _ = parse_github_remote(url)
    return kind == "github" and remote_matches_slug(url, f"{CANONICAL_OWNER}/{name}")


# --------------------------------------------------------------------------- #
# Work trees
# --------------------------------------------------------------------------- #


def _git_repository(directory: Path) -> tuple[str, Path | None]:
    """Classify ``directory/.git`` as ``absent``, ``repo`` or ``invalid``.

    For ``repo``, also return the directory holding the shared config. As in
    git, a ``.git`` directory without ``HEAD``, ``objects`` and ``refs`` is not
    a repository, so discovery continues to the parent; a ``.git`` file that
    does not name a repository is an error.
    """
    marker = directory / ".git"
    if not marker.exists() and not marker.is_symlink():
        return "absent", None
    git_dir: Path | None = None
    if marker.is_dir():
        git_dir = marker
    elif marker.is_file():
        try:
            text = marker.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return "invalid", None
        line = text.splitlines()[0] if text else ""
        if line.startswith("gitdir:"):
            target = Path(line.removeprefix("gitdir:").strip())
            git_dir = (target if target.is_absolute() else directory / target).resolve()
    if git_dir is None:
        return "invalid", None
    common = git_dir
    commondir = git_dir / "commondir"
    if commondir.is_file():
        try:
            raw = Path(commondir.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError):
            return "invalid", None
        common = (raw if raw.is_absolute() else git_dir / raw).resolve()
    if (
        (git_dir / "HEAD").is_file()
        and (common / "objects").is_dir()
        and (common / "refs").is_dir()
    ):
        return "repo", common
    return ("absent", None) if marker.is_dir() else ("invalid", None)


def _git_problem(checkout: Path, name: str) -> str | None:
    """Return why ``checkout``'s Git identity disqualifies it, if it does."""
    kind, common = _git_repository(checkout)
    if kind == "invalid":
        return "its .git entry does not name a readable Git repository"
    if kind == "absent":
        for parent in checkout.parents:
            if _git_repository(parent)[0] != "absent":
                return f"it is inside the Git work tree {parent}, not its top level"
        return None
    config = common / "config"
    if not config.is_file():
        return None
    try:
        url = _origin_url(config)
    except (OSError, UnicodeDecodeError, _UnreadableGitConfig) as exc:
        return f"its Git config is refused: {exc}"
    if not url:
        return None
    if not _canonical_origin(url, name):
        return f"its origin {url!r} is not {CANONICAL_OWNER}/{name} on github.com"
    return None


def canonical_root_problem(path: Path | str) -> str | None:
    """Return why ``path`` is not a canonical root, or ``None`` when it is."""
    given = _given_path(path)
    try:
        resolved = given.resolve(strict=True)
    except (OSError, RuntimeError):
        return "it does not exist"
    name = resolved.name
    if not CANONICAL_ROOT_NAME.match(name):
        return f"its name {name!r} is not rulespec-<two-letter country>"
    if not resolved.is_dir():
        return "it is not a directory"
    if CANONICAL_ROOT_NAME.match(given.name) and given.name != name:
        return f"it is named {given.name!r} but resolves to {name!r}"
    nested = resolved / name
    if nested.exists() or nested.is_symlink():
        return f"it contains a nested {name!r}, so it is ambiguous with a workspace"
    return _git_problem(resolved, name)


def canonical_rulespec_root(path: Path | str) -> Path | None:
    """Return the resolved canonical checkout for ``path``, or ``None``."""
    if canonical_root_problem(path) is not None:
        return None
    return _resolved(path)


def require_canonical_rulespec_root(
    path: Path | str, *, country: str | None = None
) -> Path:
    """Return the resolved canonical checkout for ``path`` or raise.

    Raises :class:`NonCanonicalRuleSpecRoot` (a ``ValueError``) naming the
    reason. With ``country``, the checkout must be ``rulespec-<country>``.
    """
    problem = canonical_root_problem(path)
    resolved = _resolved(path)
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


def require_canonical_content_root(path: Path | str) -> Path:
    """Return the canonical checkout ``path`` names or sits directly in.

    ``path`` is either a canonical checkout or one of its direct jurisdiction
    directories (``rulespec-us/us`` or ``rulespec-us/us-co``: the checkout's
    country, alone or followed by ``-<subdivision>``). Any other child, such
    as ``programs`` or ``.git``, raises :class:`NonCanonicalRuleSpecRoot`.
    """
    checkout = canonical_rulespec_root(path)
    if checkout is not None:
        return checkout
    resolved = _resolved(path)
    parent = canonical_rulespec_root(resolved.parent)
    if parent is not None and resolved.is_dir():
        country = parent.name.removeprefix("rulespec-")
        if re.fullmatch(rf"{country}(?:-[a-z0-9]+)*", resolved.name):
            return parent
        raise NonCanonicalRuleSpecRoot(
            f"RuleSpec root {path} is neither a canonical checkout nor one of "
            f"its {country!r} jurisdiction directories"
        )
    return require_canonical_rulespec_root(path)


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
