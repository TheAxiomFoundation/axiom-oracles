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
          sha_toplevel: /path/to/repo    # checkout used to resolve the SHA
          worktree_toplevel: /path/to/repo # checkout used to attest its state
          diff_sha256: 3f0a…            # only when dirty: identifies the change
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
import stat
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


#: Inherited variables that point git at some other repository or index. Git
#: exports GIT_DIR and GIT_INDEX_FILE to hooks, so a run started from one would
#: otherwise describe the wrong checkout. Every git call here drops them.
_REPO_LOCATING_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


def _git_env(**overrides: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _REPO_LOCATING_ENV}
    env.update(overrides)
    # Exact commit/tree/blob identities must always describe original objects.
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


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
            env=_git_env(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    sha = result.stdout.strip()
    return sha or None


def _git_toplevel(repo: Path) -> str | None:
    """Resolved checkout root selected by Git, without inherited selectors."""
    try:
        result = _git_output(repo, "rev-parse", "--show-toplevel")
        return str(Path(os.fsdecode(result.strip())).resolve()) if result.strip() else None
    except Exception:  # path resolution and Git lookup are best-effort
        return None


#: First line of the manifest ``diff_sha256`` hashes (:func:`_change_manifest`).
_MANIFEST_HEADER = b"axiom_oracles.worktree_manifest.v1\n"


def _git_output(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    stdin: bytes | None = None,
) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=stdin,
        capture_output=True,
        check=True,
        env=env if env is not None else _git_env(),
    ).stdout


def _private_index(toplevel: Path, workdir: Path) -> dict[str, str]:
    """Read indexes in a private git directory, including split-index files.

    Git can update a shared index's mtime even when merely listing its
    entries. ``GIT_INDEX_FILE`` alone leaves that file in the original git
    directory, so copy the per-worktree metadata too. Objects, refs and
    common config are still read from the original common directory.
    Index flags stay intact: raw content comparison ignores hidden flags
    and exempts only absent skip-worktree entries excluded by sparse rules.
    """
    gitdir = Path(
        os.fsdecode(_git_output(toplevel, "rev-parse", "--absolute-git-dir").strip())
    )
    common = os.fsdecode(
        _git_output(
            toplevel, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).strip()
    )
    # Pin HEAD in the private directory rather than depending on its copied
    # symbolic reference resolving through the original checkout's refs.
    (workdir / "HEAD").write_bytes(_git_output(toplevel, "rev-parse", "HEAD"))
    for relative in ("index", "config.worktree", "info/sparse-checkout"):
        source = gitdir / relative
        if source.exists():
            destination = workdir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    for source in gitdir.glob("sharedindex.*"):
        shutil.copy2(source, workdir / source.name)
    if not (workdir / "index").exists():
        raise OSError("checkout index unavailable")
    return _git_env(
        GIT_DIR=str(workdir),
        GIT_COMMON_DIR=common,
        GIT_WORK_TREE=str(toplevel),
        GIT_INDEX_FILE=str(workdir / "index"),
    )


def _worktree_entry(
    toplevel: Path, path: bytes, object_format: str
) -> tuple[bytes, bytes]:
    """Git blob identity and raw SHA-256 manifest entry for a tracked path."""
    target = toplevel / os.fsdecode(path)
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return b"-", b"-"
    if stat.S_ISLNK(info.st_mode):
        content = os.fsencode(os.readlink(target))
        mode = b"120000"
    elif stat.S_ISDIR(info.st_mode):
        return b"040000 -", b"040000 -"
    elif stat.S_ISREG(info.st_mode):
        content = target.read_bytes()
        mode = b"100755" if info.st_mode & 0o111 else b"100644"
    else:
        raise OSError("tracked path is not a regular file, symlink or directory")
    blob = b"blob " + str(len(content)).encode() + b"\0" + content
    oid = hashlib.new(object_format, blob).hexdigest().encode()
    return (
        mode + b" " + oid,
        mode + b" sha256:" + hashlib.sha256(content).hexdigest().encode(),
    )


def _change_manifest(
    paths: set[bytes],
    head: dict[bytes, bytes],
    index: dict[bytes, list[bytes]],
    worktree: dict[bytes, bytes],
) -> bytes:
    """Canonical tracked changes: path, HEAD, index and raw working content.

    Each sorted path contributes a NUL-separated line. HEAD entries contain
    mode/object id; index entries add stage and are joined by semicolons;
    working entries contain mode/raw SHA-256. An initialized submodule's
    working entry contains its HEAD and, when dirty, recursive manifest
    digest. ``-`` marks an absent side. No filters or diff drivers run.
    """
    lines = [
        b"\0".join(
            (
                path,
                head.get(path, b"-"),
                b";".join(sorted(index.get(path, []))) or b"-",
                worktree[path],
            )
        )
        for path in sorted(paths)
    ]
    return _MANIFEST_HEADER + b"".join(line + b"\n" for line in lines)


def _measure_worktree(
    toplevel: Path, ancestors: frozenset[Path], reference: str = "HEAD"
) -> dict[str, Any]:
    """Measure one initialized checkout; child failures propagate to the caller."""
    resolved = toplevel.resolve()
    if resolved in ancestors:
        raise OSError("recursive submodule checkout")
    ancestors = ancestors | {resolved}
    # Resolve once, before reading the index. A later checkout or commit cannot
    # silently change the content against which this attestation is measured.
    tree = os.fsdecode(
        _git_output(toplevel, "rev-parse", "--verify", f"{reference}^{{tree}}").strip()
    )
    object_format = (
        _git_output(toplevel, "rev-parse", "--show-object-format").strip().decode()
    )
    with tempfile.TemporaryDirectory(prefix="axiom-provenance-") as directory:
        env = _private_index(toplevel, Path(directory))
        head: dict[bytes, bytes] = {}
        for record in _git_output(
            toplevel, "ls-tree", "-r", "-z", "--full-tree", tree, env=env
        ).split(b"\0"):
            meta, _, path = record.partition(b"\t")
            if path:
                mode, _type, oid = meta.split(b" ")
                head[path] = mode + b" " + oid
        index: dict[bytes, list[bytes]] = {}
        omitted: set[bytes] = set()
        try:
            sparse = (
                _git_output(
                    toplevel, "config", "--bool", "core.sparseCheckout", env=env
                ).strip()
                == b"true"
            )
        except subprocess.CalledProcessError:  # unset
            sparse = False
        for record in _git_output(
            toplevel, "ls-files", "-s", "-v", "-z", env=env
        ).split(b"\0"):
            tag, entry = record[:1], record[2:]
            meta, _, path = entry.partition(b"\t")
            if path:
                index.setdefault(path, []).append(meta)
                if (
                    sparse
                    and tag in (b"S", b"s")
                    and not os.path.lexists(toplevel / os.fsdecode(path))
                ):
                    omitted.add(path)
        if omitted:
            # A manually set skip-worktree bit can hide an included deletion.
            # Let Git evaluate the effective rules; failure makes the tree
            # unverifiable rather than granting an unproven exemption.
            included = _git_output(
                toplevel,
                "sparse-checkout",
                "check-rules",
                "-z",
                env=env,
                stdin=b"\0".join(sorted(omitted)) + b"\0",
            )
            omitted.difference_update(included.split(b"\0"))
        changed: set[bytes] = set()
        worktree: dict[bytes, bytes] = {}
        for path in head.keys() | index.keys():
            expected = head.get(path, b"-")
            entries = index.get(path, [])
            if entries != ([expected + b" 0"] if path in head else []):
                changed.add(path)
            if path in omitted:
                worktree[path] = b"-"
                continue
            target = toplevel / os.fsdecode(path)
            gitlink = expected.startswith(b"160000 ") or any(
                e.startswith(b"160000 ") for e in entries
            )
            if gitlink and (
                not os.path.lexists(target)
                or target.is_dir()
                and not target.is_symlink()
            ):
                if not os.path.lexists(target / ".git"):
                    # An empty deinitialized submodule retains its index pin.
                    # An absent non-sparse directory is a tracked deletion.
                    if target.exists() and any(target.iterdir()):
                        raise OSError("populated submodule has no git metadata")
                    worktree[path] = b"040000 -" if target.exists() else b"-"
                    if not target.exists():
                        changed.add(path)
                    continue
                child_root = Path(
                    os.fsdecode(
                        _git_output(target, "rev-parse", "--show-toplevel").strip()
                    )
                )
                if child_root.resolve() != target.resolve():
                    raise OSError("submodule resolves to another checkout")
                child_sha = _git_output(target, "rev-parse", "HEAD").strip()
                child = _measure_worktree(target, ancestors, os.fsdecode(child_sha))
                entry = b"160000 " + child_sha
                if child["dirty"]:
                    entry += b" sha256:" + child["diff_sha256"].encode()
                worktree[path] = entry
                if entry != expected:
                    changed.add(path)
            else:
                actual, worktree[path] = _worktree_entry(toplevel, path, object_format)
                if actual != expected:
                    changed.add(path)
        if not changed:
            return {"dirty": False}
        manifest = _change_manifest(changed, head, index, worktree)
    return {"dirty": True, "diff_sha256": hashlib.sha256(manifest).hexdigest()}


def worktree_state(
    repo: Path | str | None, *, reference: str = "HEAD"
) -> dict[str, Any]:
    """Whether tracked index and raw files match the given commit or tree.

    Returns ``{"dirty": False}`` when they match, ``{"dirty": True,
    "diff_sha256": <64-hex>}`` when they do not, and ``{"dirty": None}`` when
    inspection fails. The whole enclosing repository counts, wherever in
    it ``repo`` points, because the recorded SHA names the whole commit.

    Compare raw Git blob identities directly, without clean filters,
    line-ending normalization, stat caches or hidden index flags. Thus even
    normalized/smudged checkout bytes that differ from the commit count as
    dirty. Only absent skip-worktree files excluded by the effective sparse
    patterns are exempt; failed pattern inspection makes the tree unverifiable.
    Initialized submodules are measured recursively, including their index
    and tracked bytes; an unverifiable child makes its parent unverifiable.
    Untracked files do not count, so build output never marks a tree dirty;
    an untracked module a run compiles goes unseen.

    ``diff_sha256`` hashes :func:`_change_manifest`, including each dirty
    child's recursive digest. The same tracked change on the same commit
    hashes the same whatever the checkout path or local Git config. Reads
    use private index/shared-index copies and never write the checkout.
    Never raises: provenance must annotate a run, never fail one.
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
        return _measure_worktree(toplevel, frozenset(), reference)
    except Exception:  # provenance must annotate, never fail a run
        return {"dirty": None}


def unclean_rulespecs(
    rulespecs: list[dict[str, Any]] | None, *, require_recorded: bool = False
) -> list[dict[str, Any]]:
    """Rulespec entries whose ``sha`` is not shown to be what ran.

    An entry with a ``sha`` is unclean when it records ``dirty: true``, or
    ``dirty: null`` (git could not tell), or its recorded SHA and attestation
    roots disagree or are incomplete. With ``require_recorded`` an entry
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
        if _repository_mismatch(entry):
            unclean.append(entry)
        elif "dirty" in entry:
            if entry["dirty"] is not False:
                unclean.append(entry)
        elif require_recorded:
            unclean.append(entry)
    return unclean


def _repository_mismatch(entry: dict[str, Any]) -> bool:
    """New repository attestations must name the same absolute checkout root."""
    if "sha_toplevel" not in entry and "worktree_toplevel" not in entry:
        return False  # reports written before repository identities were recorded
    sha_root = entry.get("sha_toplevel")
    tree_root = entry.get("worktree_toplevel")
    return not (
        isinstance(sha_root, str)
        and isinstance(tree_root, str)
        and Path(sha_root).is_absolute()
        and Path(tree_root).is_absolute()
        and sha_root == tree_root
    )


def worktree_attestation(
    repo: Path | str, *, reference: str = "HEAD"
) -> dict[str, Any]:
    """Record the measured root; refuse a root borrowing its parent's identity.

    Unlike the general-purpose ``worktree_state`` subdirectory API, a rulespec
    checkout must be rooted exactly at the requested path. All measurements
    use Git's resolved root and the same sanitized environment as SHA lookup.
    """
    state: dict[str, Any] = {"worktree_toplevel": None, "dirty": None}
    try:
        root = Path(os.path.expandvars(os.path.expanduser(str(repo)))).resolve()
        toplevel = _git_toplevel(root)
        state["worktree_toplevel"] = toplevel
        if toplevel == str(root):
            state.update(_measure_worktree(Path(toplevel), frozenset(), reference))
    except Exception:  # same best-effort contract as worktree_state
        pass
    return state


def describe_rulespec_tree(entry: dict[str, Any]) -> str:
    """``owner/repo@sha12 (state)`` for messages about unclean entries."""
    sha = str(entry.get("sha") or "")[:12] or "unknown"
    if _repository_mismatch(entry):
        state = "SHA and working tree repository mismatch"
    elif entry.get("dirty") is True:
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
            env=_git_env(),
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
    ``rulespec_root`` / ``rulespec_roots``). The ``repo`` slug comes from the
    origin remote when available, otherwise from the directory basename so a report is never left with an
    anonymous rulespec entry. An entry whose ``sha`` resolved also carries the
    checkout's :func:`worktree_attestation` and both resolved repository roots.
    A path resolving to an enclosing checkout is unverifiable. Deduplicated
    on the whole entry, order-stable, so two checkouts of one commit in
    different states both stay.
    """
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
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
            entry.update(
                sha_toplevel=_git_toplevel(path),
                **worktree_attestation(path, reference=sha),
            )
            if _repository_mismatch(entry):
                entry["dirty"] = None
                entry.pop("diff_sha256", None)
        key = tuple(entry.get(k) for k in (
            "repo", "sha", "dirty", "diff_sha256", "sha_toplevel", "worktree_toplevel"
        ))
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
