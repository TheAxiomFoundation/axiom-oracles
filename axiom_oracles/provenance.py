"""Provenance blocks for comparison reports (O2).

A checked-in comparison report should record exactly what produced it, so a
reader can answer "is this number stale, and against which rules/engine/data
did it run" without re-deriving anything. :func:`build_provenance` assembles
that block from the pieces the runner already has in hand; it is intentionally
tolerant — every field degrades to ``None``/absent rather than raising, because
a provenance stamp must never be the thing that fails a run.

The block shape (``axiom_oracles.provenance.v1``)::

    provenance:
      schema: axiom_oracles.provenance.v1
      generated_at: 2026-07-05T12:00:00Z
      generated_by: scripts/run_comparison.py::fiit-ecps
      run_kind: weekly | pr-triggered | manual
      rulespecs:                       # the rulespec repos the cases ran against
        - repo: TheAxiomFoundation/rulespec-us
          sha: 9c1f2ab…                 # 40-hex, or None when unresolved
          dirty: false                  # tracked files differ from `sha`?
          diff_sha256: 3f0a…            # only when dirty (see worktree_state)
      engine:                          # the Axiom side under test
        axiom_rules_engine_sha: …      # git SHA of the axiom-rules checkout
        axiom_rules_engine_version: …  # crate version if resolvable
      oracle:                          # the oracle side it was compared to
        name: policyengine             # or euromod
        policyengine_package: policyengine==4.11.0
        policyengine_us: 1.729.0
        # …or, for EUROMOD:
        euromod_release: J2.0
        euromod_system: BE_2025
        euromod_dataset: BE_2024_c1_2015_03_e2
      dataset:                         # reuse the pinned-populace identity (#80/#952)
        source: populace-hf
        repo_id: policyengine/populace-us
        filename: populace_us_2024.h5
        revision: populace-us-2024-…
        sha256: 16be6338…              # 12-hex prefix
        built_with: 1.729.0

Only ``schema`` and ``generated_at`` are guaranteed present. ``run_kind`` is a
free-form-but-validated enum (see :data:`RUN_KINDS`) resolved from the
``AXIOM_ORACLES_RUN_KIND`` environment variable, defaulting to ``manual`` so a
local run is never mislabeled as a scheduled one.

A ``sha`` names a commit, but a run reads the working tree: a mutated scratch
copy of rulespec-rw once reported ``001fa4b`` while running a 17% VAT rate.
Every rulespec entry whose ``sha`` resolved therefore also records ``dirty``
(:func:`worktree_state`): ``false`` when the tracked files match ``sha``,
``true`` plus a ``diff_sha256`` when they do not, and ``null`` when git could
not tell. Entries without a ``sha``, and reports stamped before this field
existed, carry no ``dirty`` key.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVENANCE_SCHEMA_VERSION = "axiom_oracles.provenance.v1"

#: Rulespec repos all live under this owner. A bare ``rulespec-*`` directory
#: basename (from a local rsync'd root with no git remote) is canonicalized to
#: ``<OWNER>/<basename>`` so a report's ``rulespecs[].repo`` slug matches the
#: affected-map's keys and ``select_affected_suites.py`` can diff SHAs.
RULESPEC_OWNER = "TheAxiomFoundation"

#: Local checkout directory basenames that differ from the upstream repo name.
_RULESPEC_DIR_ALIASES = {"rulespec-uk-official": "rulespec-uk"}

#: Valid ``run_kind`` values. ``weekly`` = the full backstop matrix,
#: ``pr-triggered`` = a PR CI run, ``affected-rerun`` = the 6-hourly
#: stale-suite sweep, ``manual`` = a local/ad-hoc run (the default).
RUN_KINDS = ("weekly", "pr-triggered", "affected-rerun", "manual")

_RUN_KIND_ENV = "AXIOM_ORACLES_RUN_KIND"
_GENERATED_BY_ENV = "AXIOM_ORACLES_GENERATED_BY"


def resolve_run_kind(default: str = "manual") -> str:
    """Return the run kind from the environment, validated against RUN_KINDS."""
    value = (os.environ.get(_RUN_KIND_ENV) or "").strip().lower()
    if value in RUN_KINDS:
        return value
    return default


def _git_sha(repo: Path) -> str | None:
    """Best-effort 40-hex HEAD SHA of a git checkout; None if unavailable."""
    if repo is None:
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    sha = result.stdout.strip()
    return sha or None


#: ``git status`` arguments that decide ``dirty``: staged or unstaged changes
#: to tracked files only (``--untracked-files=no``), and a submodule counts
#: only for modified content, not untracked content, for the same reason.
_STATUS_ARGS = (
    "--no-optional-locks",
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=no",
    "--ignore-submodules=untracked",
)

#: The ``git diff`` behind ``diff_sha256``. Every output-shaping option that
#: git config can change is pinned here, so the hash depends on the change
#: alone. From the checkout's top level, a reader can recompute it with
#: ``git <_DIFF_CONFIG> <_DIFF_ARGS> | shasum -a 256``, after clearing any
#: skip-worktree or assume-unchanged flag that :func:`worktree_state` clears.
_DIFF_CONFIG = (
    "-c",
    "core.quotePath=false",
    "-c",
    "diff.noprefix=false",
    "-c",
    "diff.mnemonicPrefix=false",
    "-c",
    "diff.relative=false",
    "-c",
    "diff.suppressBlankEmpty=false",
)
_DIFF_ARGS = (
    "--no-optional-locks",
    "diff",
    "--binary",
    "--full-index",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--no-renames",
    "--diff-algorithm=myers",
    "--indent-heuristic",
    "--unified=3",
    "--inter-hunk-context=0",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "--submodule=short",
    "--ignore-submodules=untracked",
    "-O/dev/null",
    "HEAD",
    "--",
)


def _git_output(
    repo: Path, *args: str, env: dict[str, str] | None = None, stdin: bytes | None = None
) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=stdin,
        capture_output=True,
        check=True,
        env=env,
    ).stdout


def _index_revealing_hidden_edits(toplevel: Path, workdir: Path) -> dict[str, str] | None:
    """Environment whose index shows edits that index flags hide, or None.

    ``git status`` and ``git diff`` trust a ``skip-worktree`` or
    ``assume-unchanged`` entry without reading the file, so an edit behind
    either flag runs while the tree looks clean. When any flagged file is
    present on disk, copy the index into ``workdir`` and clear both flags on
    the copy (``update-index`` applies only the last mode option it is given,
    hence one pass per flag). The checkout's own index is never written. A
    flagged file absent from disk, as in a sparse checkout, keeps its flag.
    """
    hidden = []
    for record in _git_output(toplevel, "ls-files", "-v", "-z").split(b"\0"):
        tag, path = record[:1], record[2:]
        if not path or not (tag == b"S" or tag.islower()):
            continue
        if os.path.lexists(toplevel / os.fsdecode(path)):
            hidden.append(path)
    if not hidden:
        return None
    index = Path(
        os.fsdecode(_git_output(toplevel, "rev-parse", "--git-path", "index").strip())
    )
    if not index.is_absolute():
        index = toplevel / index
    copy = workdir / "index"
    # copy2 keeps the index's mtime. Git rehashes an entry whose file is no
    # older than the index ("racily clean"); a fresh mtime on the copy would
    # make a same-size edit made in the same second look unchanged.
    shutil.copy2(index, copy)
    env = {**os.environ, "GIT_INDEX_FILE": str(copy)}
    paths = b"\0".join(hidden) + b"\0"
    for flag in ("--no-skip-worktree", "--no-assume-unchanged"):
        _git_output(
            toplevel,
            "update-index",
            "--no-split-index",
            flag,
            "-z",
            "--stdin",
            env=env,
            stdin=paths,
        )
    return env


def worktree_state(repo: Path | str | None) -> dict[str, Any]:
    """Whether a checkout's tracked files match its ``HEAD`` commit.

    Returns ``{"dirty": False}`` when they match, ``{"dirty": True,
    "diff_sha256": <64-hex>}`` when they do not, and ``{"dirty": None}`` when
    git cannot tell (not a checkout, no commit, git missing). The whole
    enclosing repository counts, wherever in it ``repo`` points, because the
    recorded ``sha`` names the whole commit.

    Dirty means ``git status`` reports a staged or unstaged change to a
    tracked file: an edit, a deletion, a mode change, a newly staged file, a
    conflict. Edits hidden behind ``skip-worktree`` or ``assume-unchanged``
    count too (:func:`_index_revealing_hidden_edits`). Untracked files do not
    count, so build output never marks a tree dirty; the cost is that a run
    compiling an untracked module that no tracked file imports goes unseen.

    ``diff_sha256`` is the SHA-256 of ``git diff HEAD`` under the pinned
    :data:`_DIFF_CONFIG` and :data:`_DIFF_ARGS`, so the hash identifies the
    edit: the same edit on the same commit hashes the same whatever the local
    git config, and a different diff hashes differently. (Binary patches are
    deflated, so a binary edit may hash differently under another zlib.) Never
    raises: provenance must annotate a run, never fail one.
    """
    if repo is None:
        return {"dirty": None}
    try:
        toplevel = Path(
            os.fsdecode(
                _git_output(
                    Path(os.path.expandvars(os.path.expanduser(str(repo)))),
                    "rev-parse",
                    "--show-toplevel",
                ).strip()
            )
        )
        _git_output(toplevel, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
        with tempfile.TemporaryDirectory(prefix="axiom-provenance-") as workdir:
            env = _index_revealing_hidden_edits(toplevel, Path(workdir))
            status = _git_output(toplevel, *_STATUS_ARGS, env=env)
            if not status.strip(b"\0"):
                return {"dirty": False}
            diff = _git_output(toplevel, *_DIFF_CONFIG, *_DIFF_ARGS, env=env)
    except Exception:  # provenance must annotate, never fail a run
        return {"dirty": None}
    return {"dirty": True, "diff_sha256": hashlib.sha256(diff).hexdigest()}


def unclean_rulespecs(
    rulespecs: list[dict[str, Any]] | None, *, require_recorded: bool = False
) -> list[dict[str, Any]]:
    """Rulespec entries whose ``sha`` is not shown to be what ran.

    An entry with a ``sha`` is unclean when it records ``dirty: true``, or
    ``dirty: null`` (git could not tell). With ``require_recorded`` an entry
    that has a ``sha`` but no ``dirty`` key at all is unclean as well: use it
    for a block this code just built, where every resolved ``sha`` comes with
    a ``dirty`` value, so a missing one means a path skipped the check. Leave
    it off for committed reports, where a missing key only means the report
    predates the field. Entries without a ``sha`` claim no commit and are
    never unclean here; the affected-rerun selector already treats them as
    unproven.
    """
    unclean = []
    for entry in rulespecs or []:
        if not isinstance(entry, dict) or not entry.get("sha"):
            continue
        if "dirty" in entry:
            if entry["dirty"] is not False:
                unclean.append(entry)
        elif require_recorded:
            unclean.append(entry)
    return unclean


def describe_rulespec_tree(entry: dict[str, Any]) -> str:
    """``owner/repo@sha12 (state)`` for messages about unclean entries."""
    sha = str(entry.get("sha") or "")[:12] or "unknown"
    if entry.get("dirty") is True:
        digest = str(entry.get("diff_sha256") or "")[:12] or "unknown"
        state = f"dirty, diff sha256 {digest}"
    elif "dirty" in entry:
        state = "working tree unverifiable"
    else:
        state = "working tree not recorded"
    return f"{entry.get('repo')}@{sha} ({state})"


def _remote_url(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return result.stdout.strip() or None


def repo_slug_from_remote(url: str | None) -> str | None:
    """Reduce a git remote URL to its ``owner/repo`` slug.

    Handles both ``git@github.com:Owner/repo.git`` and
    ``https://github.com/Owner/repo(.git)`` forms. Returns None for anything
    that is not obviously a GitHub-style remote.
    """
    if not url:
        return None
    url = url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@") and ":" in url:
        url = url.split(":", 1)[1]
    elif "github.com/" in url:
        url = url.split("github.com/", 1)[1]
    else:
        return None
    parts = [p for p in url.split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}"


def rulespec_provenance(paths: list[Path | str] | None) -> list[dict[str, Any]]:
    """Resolve ``{repo, sha, dirty}`` provenance for each rulespec checkout path.

    ``paths`` are local checkout directories (as the runner resolves them from
    ``rulespec_root`` / ``rulespec_roots``). Each is walked up to its enclosing
    git repo; the ``repo`` slug comes from the origin remote when available,
    otherwise from the directory basename so a report is never left with an
    anonymous rulespec entry. An entry whose ``sha`` resolved also carries the
    checkout's :func:`worktree_state`. Deduplicated on the whole entry,
    order-stable, so two checkouts of one commit in different states both stay.
    """
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for raw in paths or []:
        path = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        if not path.exists():
            # Record the intended repo even when the checkout is absent, keyed
            # by basename — the affected-rerun map still needs a name to diff.
            repo = canonical_rulespec_slug(path.name) if path.name else None
            sha = None
        else:
            remote_slug = repo_slug_from_remote(_remote_url(path))
            repo = remote_slug or canonical_rulespec_slug(path.name)
            sha = _git_sha(path)
        entry: dict[str, Any] = {"repo": repo, "sha": sha}
        if sha:
            entry.update(worktree_state(path))
        key = (repo, sha, entry.get("dirty"), entry.get("diff_sha256"))
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return entries


def resolve_rulespec_checkout(slug: str) -> Path | None:
    """Locate a local checkout for a rulespec repo slug via layout conventions.

    The comparison harnesses resolve rulespec repos from a small set of
    supervised-layout locations (`~/TheAxiomFoundation/<name>`, a `~/<name>`
    symlink, the `~/.axiom-oracles/roots/<name>` synced-roots dir, and the
    `rulespec-uk-official` alias). This walks the same conventions so a
    report's provenance can record the SHA of the checkout the run actually
    resolved. Git-bearing candidates win over bare directories (an rsync'd
    root without `.git` has no SHA to record); returns None when nothing
    matches.
    """
    name = slug.split("/", 1)[-1]
    candidate_names = [name] + [
        alias for alias, target in _RULESPEC_DIR_ALIASES.items() if target == name
    ]
    home = Path.home()
    candidates = []
    # AXIOM_RULESPEC_US_ROOT pins the rulespec-us checkout a comparison runs
    # against (see scripts/run_comparison.py); the recorded SHA must come
    # from the same checkout the run actually resolved, not whatever branch
    # the developer's convention-path checkout happens to be on.
    override = os.environ.get("AXIOM_RULESPEC_US_ROOT")
    if override and name == "rulespec-us":
        candidates.append(Path(override))
    for candidate_name in candidate_names:
        candidates.extend(
            [
                home / "TheAxiomFoundation" / candidate_name,
                home / candidate_name,
                home / ".axiom-oracles" / "roots" / candidate_name,
            ]
        )
    existing = [path for path in candidates if path.exists()]
    for path in existing:
        if _git_sha(path):
            return path
    return existing[0] if existing else None


def canonical_rulespec_slug(name: str) -> str:
    """Canonicalize a rulespec repo name to its ``<OWNER>/<repo>`` slug.

    The single source of truth for rulespec slug canonicalization, shared by
    the report stamper (this module) and the affected-map generator
    (``scripts/generate_affected_map.py``) so a report's ``rulespecs[].repo``
    and the affected-map's keys are always the *same string* — otherwise the
    rerun selector would silently fail to match a suite to its repo. Accepts a
    bare dir basename (``rulespec-us``), an rsync alias (``rulespec-uk-official``
    → ``rulespec-uk``), or an already-canonical ``owner/repo`` slug (passthrough).
    Non-rulespec names pass through unchanged (they are never affected-map keys).
    """
    resolved = _RULESPEC_DIR_ALIASES.get(name, name)
    if "/" in resolved or not resolved.startswith("rulespec-"):
        return resolved
    return f"{RULESPEC_OWNER}/{resolved}"


def is_real_run_report(report: Any) -> bool:
    """Whether a parsed report came from a real run rather than a re-emission.

    A skip-capable runner that cannot execute re-emits the committed report and
    marks it ``provenance.reemitted_report``. Its numbers are the committed
    ones, so it must never replace a real run's report, whose provenance
    records what the numbers ran against. Unstamped legacy reports count as
    real: nothing marks them re-emitted. Anything that is not a JSON object is
    not a report.
    """
    if not isinstance(report, dict):
        return False
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return True
    return not provenance.get("reemitted_report")


def build_provenance(
    *,
    generated_by: str,
    run_kind: str | None = None,
    rulespecs: list[dict[str, Any]] | None = None,
    engine: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    dataset: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a provenance block. Empty sub-blocks are omitted, not null."""
    # The caller's per-suite `generated_by` (e.g. run_comparison.py::<suite>)
    # wins — it carries the suite suffix that makes the field identifying. The
    # env var is only a fallback for callers that pass nothing meaningful, so a
    # one-time `export` can't silently flatten every suite to one label.
    block: dict[str, Any] = {
        "schema": PROVENANCE_SCHEMA_VERSION,
        "generated_at": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": generated_by or os.environ.get(_GENERATED_BY_ENV) or "unknown",
        "run_kind": run_kind or resolve_run_kind(),
    }
    if rulespecs:
        block["rulespecs"] = rulespecs
    if engine:
        block["engine"] = {k: v for k, v in engine.items() if v is not None}
    if oracle:
        block["oracle"] = {k: v for k, v in oracle.items() if v is not None}
    if dataset:
        block["dataset"] = {k: v for k, v in dataset.items() if v is not None}
    return block


def engine_provenance(axiom_rules_repo: Path | str | None) -> dict[str, Any]:
    """Axiom-side engine identity: git SHA + crate version if resolvable."""
    repo = (
        Path(os.path.expandvars(os.path.expanduser(str(axiom_rules_repo))))
        if axiom_rules_repo
        else None
    )
    return {
        "axiom_rules_engine_sha": _git_sha(repo) if repo else None,
        "axiom_rules_engine_version": _crate_version(repo) if repo else None,
    }


def _crate_version(repo: Path) -> str | None:
    """Parse ``version = "…"`` from the engine crate's Cargo.toml (top table)."""
    for candidate in (repo / "Cargo.toml",):
        if not candidate.exists():
            continue
        in_package = False
        try:
            for line in candidate.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("["):
                    in_package = stripped == "[package]"
                    continue
                if in_package and stripped.startswith("version"):
                    _, _, rhs = stripped.partition("=")
                    return rhs.strip().strip('"').strip("'") or None
        except OSError:
            return None
    return None


def dataset_provenance_from_identity(identity: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize the encode/populace ``dataset_identity`` block into provenance.

    Reuses the pinned-populace identity fields threaded from axiom-encode#952 /
    populace#80 (``source``/``repo_id``/``filename``/``revision``/``sha256``/
    ``built_with``). Returns None when identity is absent so the caller can omit
    the sub-block entirely.
    """
    if not identity:
        return None
    keep = ("source", "repo_id", "filename", "revision", "sha256", "built_with", "country")
    out = {k: identity[k] for k in keep if identity.get(k) is not None}
    return out or None
