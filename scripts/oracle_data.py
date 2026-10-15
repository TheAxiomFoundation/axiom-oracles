#!/usr/bin/env python3
"""Publish generated oracle data separately from protected source history.

``prepare`` is destructive and belongs in a disposable publisher checkout:
it combines current main source with the latest data before generation.
``materialize`` changes only generated files in a reader's worktree; its
optional ``--baseline`` makes those files part of a detached CI baseline so
the report packer can distinguish a refresh from already-published data.
"""

from __future__ import annotations

import argparse
import ast
from fnmatch import fnmatchcase
from functools import cache
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile

DATA_BRANCH = "oracle-data"
DATA_REF = f"refs/heads/{DATA_BRANCH}"
MAIN_REF = "refs/heads/main"
MANIFEST_PATH = "dashboard/public/data/manifest.json"
# Reader scope: only generated outputs of the publication chain. The publisher
# carries full source history, including authored inputs beside these outputs;
# readers must keep those inputs at their own source revision.
DATA_PATHS = (
    "dashboard/public/data/",
    "conformance/scoreboard.json",
    "conformance/detail/",
    "conformance/history/",
    "conformance/exercise-census.json",
    "conformance/de-certificate-census.json",
    "conformance/executable/de-kindergeld-status.json",
    "conformance/executable/nz-treasury-incomeexplorer.json",
    "certificates/",
    "closure/de/summary.json",
    "closure/nz/summary.json",
    "comparisons/de-worker-dual-oracle/axiom-euromod.json",
    "comparisons/de-worker-dual-oracle/axiom-gettsim.json",
    "comparisons/de-worker-dual-oracle/unified-record.json",
    "comparisons/affected_map.json",
    "comparisons/nz-treasury-incomeexplorer/single-person-attestations.json",
    "axiom_oracles/data/euromod_be_coverage.json",
)
PUBLISH_GROUPS = {
    "dashboard": ("dashboard/public/data/",),
    "kpi": (
        "dashboard/public/data/rule_verification.json",
        "dashboard/public/data/rule_verification_summary.json",
    ),
}


class DataError(RuntimeError):
    """Publication or materialization cannot proceed safely."""


def _git(
    root: Path,
    *args: str,
    input: bytes | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=root, input=input, env=env, capture_output=True
    )
    if check and result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise DataError(f"git {args[0]} failed: {message}")
    return result


def _sha(root: Path, ref: str) -> str:
    return _git(root, "rev-parse", "--verify", ref).stdout.decode().strip()


def _repository(root: Path | None) -> Path:
    # Readers such as the dashboard's package scripts run below the root;
    # every publication path remains relative to the repository top level.
    return Path(_git(root or Path.cwd(), "rev-parse", "--show-toplevel").stdout.decode().strip())


def _fetch(root: Path, ref: str, *, optional: bool = False) -> str | None:
    """Fetch an exact remote head, distinguishing absence from transport errors."""
    advertised = _git(root, "ls-remote", "--exit-code", "origin", ref, check=False)
    if advertised.returncode == 2 and optional:
        return None
    if advertised.returncode:
        reason = advertised.stderr.decode(errors="replace").strip()
        raise DataError(f"cannot read origin {ref}: {reason or 'ref is absent'}")
    # FETCH_HEAD is read immediately: another fetch must not replace it first.
    _git(root, "fetch", "--no-tags", "origin", ref)
    return _sha(root, "FETCH_HEAD")


def _ancestor(root: Path, older: str, newer: str) -> bool:
    result = _git(root, "merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise DataError("cannot inspect data branch ancestry")
    return result.returncode == 0


def _declared_output(script: str, name: str) -> str:
    """Read a generator's Path constant without importing its runtime dependencies.

    Output declarations use only REPO_ROOT, string literals and path division.
    Deliberately reject other expressions instead of executing generator code
    in dashboard readers, which otherwise need only Python's standard library.
    """
    scripts = Path(__file__).resolve().parent
    assignments = {
        node.targets[0].id: node.value
        for node in ast.parse((scripts / script).read_text()).body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }

    def path_value(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return scripts.parent if node.id == "REPO_ROOT" else path_value(assignments[node.id])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return path_value(node.left) / path_value(node.right)
        raise DataError(f"unsupported output declaration {script}:{name}")

    return path_value(assignments[name]).relative_to(scripts.parent).as_posix()


@cache
def _regenerated_aggregates() -> tuple[str, ...]:
    # One conflict policy for publishers and readers, derived from the same
    # output declarations the generators write. Dynamic families match only
    # JSON outputs; authored conformance inputs and primary reports stay closed.
    return (
        _declared_output("generate_dashboard_overview.py", "OUT"),
        _declared_output("check_vacuous_gate.py", "FRESHNESS_OUTPUT"),
        _declared_output("conformance_scoreboard.py", "SCOREBOARD_PATH"),
        _declared_output("conformance_scoreboard.py", "DASHBOARD_SCOREBOARD_PATH"),
        _declared_output("conformance_scoreboard.py", "DETAIL_DIR") + "/*.json",
        _declared_output("conformance_scoreboard.py", "HISTORY_DIR") + "/*/*.json",
        _declared_output("conformance_scoreboard.py", "DASHBOARD_DATA_DIR") + "/conformance_detail_*.json",
        _declared_output("conformance_burndown.py", "OUTPUT_PATH"),
        _declared_output("exercise_census.py", "OUTPUT_PATH"),
        _declared_output("de_certificate_census.py", "OUTPUT_PATH"),
        _declared_output("certify.py", "OUT_DIR") + "/*.json",
        _declared_output("generate_affected_map.py", "OUTPUT_PATH"),
        MANIFEST_PATH,
    )


def _manifest_union(root: Path, source: str, data: str, *, prefer_data: bool) -> bytes | None:
    identities = [_tree_identities(root, ref, [MANIFEST_PATH])[MANIFEST_PATH] for ref in (source, data)]
    if identities[0] == identities[1]:
        return None
    documents = []
    for identity in identities:
        if identity["oid"] is None:
            documents.append({"reports": []})
            continue
        if identity["mode"] not in ("100644", "100755"):
            raise DataError("report manifest must be a regular JSON file; checkout unchanged")
        try:
            doc = json.loads(_git(root, "cat-file", "blob", identity["oid"]).stdout)
            if not isinstance(doc, dict) or not isinstance(doc.get("reports"), list) or any(
                not isinstance(entry, str) for entry in doc["reports"]
            ):
                raise ValueError("expected a reports list of file names")
        except ValueError as exc:
            raise DataError(f"cannot union report manifest: {exc}; checkout unchanged") from exc
        documents.append(doc)
    preferred, other = documents[::-1] if prefer_data else documents
    preferred["reports"] = list(dict.fromkeys(preferred["reports"] + other["reports"]))
    return (json.dumps(preferred, indent=2) + "\n").encode()


def _merge_tree(root: Path, source: str, data: str, *, prefer_data: bool = False) -> str:
    result = _git(root, "merge-tree", "--write-tree", "-z", source, data, check=False)
    if result.returncode not in (0, 1):
        details = (result.stdout + result.stderr).decode(errors="replace").strip()
        raise DataError(f"source/data merge failed; checkout unchanged:\n{details}")
    fields = result.stdout.split(b"\0")
    tree = fields[0].decode()
    conflicts = {}
    if result.returncode:
        for entry in fields[1:]:
            if not entry:
                break
            header, path = entry.split(b"\t", 1)
            mode, oid, stage = header.decode().split()
            conflicts.setdefault(path.decode(), {})[stage] = (mode, oid)
        unresolved = [
            path for path, stages in conflicts.items()
            if not any(
                path.count("/") == pattern.count("/") and fnmatchcase(path, pattern)
                for pattern in _regenerated_aggregates()
            )
            or any(mode not in ("100644", "100755") for mode, _ in stages.values())
        ]
        if unresolved or not conflicts:
            raise DataError(
                "source/data merge failed; checkout unchanged; conflicting primary reports or authored inputs: "
                + ", ".join(unresolved)
                + "; keep reviewed main reports and follow "
                "comparisons/README.md#recovering-source-data-conflicts"
            )
    manifest = _manifest_union(root, source, data, prefer_data=prefer_data)
    if not conflicts and manifest is None:
        return tree
    # Resolve in a private index: a refused merge never touches HEAD, the real
    # index, or the worktree. Publishers regenerate and verify after prepare;
    # readers choose the data-side aggregate that matches published reports.
    with tempfile.TemporaryDirectory(prefix="oracle-data-merge-") as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        _git(root, "read-tree", tree, env=env)
        updates = []
        for path, stages in conflicts.items():
            mode, oid = stages.get("3" if prefer_data else "2", ("0", "0" * 40))
            updates.append(f"{mode} {oid}\t{path}\0".encode())
        if manifest is not None:
            oid = _git(root, "hash-object", "-w", "--stdin", input=manifest).stdout.decode().strip()
            updates.append(f"100644 {oid}\t{MANIFEST_PATH}\0".encode())
        _git(root, "update-index", "-z", "--index-info", input=b"".join(updates), env=env)
        return _git(root, "write-tree", env=env).stdout.decode().strip()


def _commit_tree(root: Path, tree: str, *parents: str) -> str:
    # Local environment only: do not change developer or repository identity.
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="github-actions[bot]",
        GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
        GIT_COMMITTER_NAME="github-actions[bot]",
        GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
    )
    parent_args = [arg for parent in parents for arg in ("-p", parent)]
    return _git(
        root, "commit-tree", tree, *parent_args,
        input=b"Merge current source and published oracle data\n", env=env,
    ).stdout.decode().strip()


def _composite_commit(root: Path, tree: str, source: str, data: str) -> str:
    if tree == _sha(root, f"{source}^{{tree}}") and _ancestor(root, data, source):
        return source
    if tree == _sha(root, f"{data}^{{tree}}") and _ancestor(root, source, data):
        return data
    return _commit_tree(root, tree, source, data)


def _scoped_tree(root: Path, source: str, target: str) -> str:
    """Apply only the publication delta to a private index, then write its tree."""
    fd, index_name = tempfile.mkstemp(prefix="oracle-data-index-")
    os.close(fd)
    os.unlink(index_name)
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = index_name
    try:
        _git(root, "read-tree", source, env=env)
        patch = _git(root, "diff", "--binary", source, target, "--", *DATA_PATHS).stdout
        if patch:
            _git(root, "apply", "--cached", "--binary", "-", input=patch, env=env)
        return _git(root, "write-tree", env=env).stdout.decode().strip()
    finally:
        Path(index_name).unlink(missing_ok=True)


def _reader_merge_tree(root: Path, source: str, data: str) -> str:
    # Merge data changes in isolation. Source code carried by the full-history
    # data branch is irrelevant to a reader and can conflict with feature work.
    base = _git(root, "merge-base", source, data).stdout.decode().strip()
    scoped = _scoped_tree(root, base, data)
    data_only = base if scoped == _sha(root, f"{base}^{{tree}}") else _commit_tree(root, scoped, base)
    return _merge_tree(root, source, data_only, prefer_data=True)


def _state_path(root: Path) -> Path:
    location = Path(_git(root, "rev-parse", "--git-path", "oracle-data-materialized.json").stdout.decode().strip())
    return location if location.is_absolute() else root / location


def _read_state(root: Path) -> dict:
    try:
        state = json.loads(_state_path(root).read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise DataError(f"cannot read previous data materialization: {exc}") from exc
    if not isinstance(state, dict) or any(
        not isinstance(path, str) or "\0" in path
        or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
        or not _in_scope(path, DATA_PATHS)
        or not isinstance(identity, dict) or set(identity) != {"oid", "mode"}
        for path, identity in state.items()
    ):
        raise DataError("invalid previous data materialization metadata")
    return state


def _tree_identities(root: Path, tree: str, paths: list[str]) -> dict:
    identities = {path: {"oid": None, "mode": None} for path in paths}
    if paths:
        entries = _git(root, "ls-tree", "-r", "-z", "--full-tree", tree, "--", *paths).stdout
        for entry in entries.split(b"\0"):
            if entry:
                header, name = entry.split(b"\t", 1)
                mode, _, oid = header.decode().split()
                identities[name.decode()] = {"oid": oid, "mode": mode}
    return identities


def _worktree_identity(root: Path, path: str) -> dict:
    absolute = root / path
    try:
        mode = absolute.lstat().st_mode
    except FileNotFoundError:
        return {"oid": None, "mode": None}
    if stat.S_ISLNK(mode):
        oid = _git(root, "hash-object", "--stdin", input=os.fsencode(os.readlink(absolute))).stdout.decode().strip()
        return {"oid": oid, "mode": "120000"}
    if not stat.S_ISREG(mode):
        raise DataError(f"local data path {path} is not a file; checkout unchanged")
    oid = _git(root, "hash-object", f"--path={path}", path).stdout.decode().strip()
    return {"oid": oid, "mode": "100755" if mode & 0o111 else "100644"}


def _guard_worktree(root: Path, source: str, tree: str, paths: list[str], previous: dict) -> dict:
    # Check every target before restoring even the first one. A final-file
    # identity cannot detect a local directory symlink redirecting a deletion
    # to a matching file outside the checkout. Keep final symlinks in the
    # separate identity check below, where their mode and link bytes matter.
    for path in paths:
        parent = root
        for part in PurePosixPath(path).parts[:-1]:
            parent /= part
            try:
                mode = parent.lstat().st_mode
            except FileNotFoundError:
                break  # Restore may create missing directories.
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise DataError(f"local data parent {parent.relative_to(root)} is not a directory; checkout unchanged")
    changed = _git(root, "diff", "--cached", "--name-only", "-z", "--", *paths).stdout
    if changed:
        raise DataError("staged data overlaps published updates; checkout unchanged")
    committed = _tree_identities(root, source, paths)
    desired = _tree_identities(root, tree, paths)
    for path in paths:
        current = _worktree_identity(root, path)
        allowed = [committed[path], desired[path]]
        if path in previous:
            allowed.append(previous[path])
        if current not in allowed:
            raise DataError(f"local data edits overlap published update at {path}; checkout unchanged")
    return desired


def _write_state(root: Path, state: dict) -> None:
    location = _state_path(root)
    fd, name = tempfile.mkstemp(prefix="oracle-data-materialized-", dir=location.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(json.dumps(state, sort_keys=True) + "\n")
        os.replace(name, location)
    finally:
        Path(name).unlink(missing_ok=True)


def _checkout_baseline(root: Path, commit: str) -> None:
    _git(root, "checkout", "--detach", "--force", commit)
    _git(root, "reset", "--hard", commit)


def prepare(root: Path | None = None) -> str:
    """Prepare a disposable publisher from current remote main and data."""
    root = _repository(root)
    main = _fetch(root, MAIN_REF)
    assert main is not None
    data = _fetch(root, DATA_REF, optional=True)
    baseline = main
    if data is not None:
        tree = _merge_tree(root, main, data)
        baseline = _composite_commit(root, tree, main, data)
    _checkout_baseline(root, baseline)
    return baseline


def materialize(root: Path | None = None, *, baseline: bool = False) -> list[str]:
    """Merge published data into this checkout without replacing source files."""
    if os.environ.get("AXIOM_ORACLES_DATA_SOURCE") == "checkout":
        return []
    root = _repository(root)
    source = _sha(root, "HEAD")
    data = _fetch(root, DATA_REF, optional=True)
    # A disappeared branch also removes the last overlay. Reconcile recorded
    # paths against HEAD with exactly the same guards as an ordinary refresh.
    tree = source if data is None else _reader_merge_tree(root, source, data)
    changed = _git(root, "diff", "--no-renames", "--name-only", "-z", source, tree, "--", *DATA_PATHS).stdout
    paths = [p.decode() for p in changed.split(b"\0") if p]
    previous = _read_state(root)
    # Include prior materializations that the remote has since reverted
    # to HEAD, otherwise such a revert would leave old data in the reader.
    previous_targets = _tree_identities(root, tree, list(previous))
    paths.extend(path for path in previous if path not in paths and previous[path] != previous_targets[path])
    desired = _guard_worktree(root, source, tree, paths, previous) if paths else {}
    if baseline and _git(root, "status", "--porcelain", "--untracked-files=no").stdout:
        raise DataError(
            "baseline requires a clean tracked checkout; save staged and unstaged edits "
            "and use a clean disposable checkout before materialize --baseline"
        )
    if not paths and not baseline:
        return []
    if baseline:
        # A data branch can contain newer main source. Restrict its merged
        # tree to the publication delta before making the detached baseline.
        # A private index leaves the caller's index untouched until checkout.
        scoped_tree = _scoped_tree(root, source, tree)
        commit = source if data is None else _composite_commit(root, scoped_tree, source, data)
        _checkout_baseline(root, commit)
    else:
        present = b"".join(path.encode() + b"\0" for path in paths if desired[path]["oid"] is not None)
        if present:
            _git(
                root, "restore", "--worktree", f"--source={tree}",
                "--pathspec-from-file=-", "--pathspec-file-nul", input=present,
            )
    # A previously materialized addition can still be untracked in the
    # index. Neither restore nor a baseline checkout removes it when neither
    # HEAD nor the new tree contains it; unlink only after the shared guard.
    for path in paths:
        if desired[path]["oid"] is None:
            (root / path).unlink(missing_ok=True)
    previous.update(desired)
    _write_state(root, previous)
    return paths


def _in_scope(path: str, scope: tuple[str, ...]) -> bool:
    return any(path.startswith(p) if p.endswith("/") else path == p for p in scope)


def publish(root: Path | None = None, *, group: str, message: str) -> bool:
    """Commit prepared generated data and push only the fixed data ref.

    Call prepare before generation. A source or data update after generation
    fails closed; the caller can prepare and recompute rather than overwrite it.
    """
    root = _repository(root)
    scope = PUBLISH_GROUPS[group]
    head = _sha(root, "HEAD")
    branch = _git(root, "symbolic-ref", "--quiet", "HEAD", check=False)
    if branch.returncode == 0 and branch.stdout.decode().strip() != DATA_REF:
        raise DataError("publish requires a detached baseline or the local oracle-data branch")
    main = _fetch(root, MAIN_REF)
    data = _fetch(root, DATA_REF, optional=True)
    if not _ancestor(root, main, head) or (data and not _ancestor(root, data, head)):
        raise DataError("source or data advanced; prepare and regenerate before publishing")
    staged = _git(root, "diff", "--cached", "--name-only", "-z").stdout
    if any(not _in_scope(p.decode(), scope) for p in staged.split(b"\0") if p):
        raise DataError("staged files outside the publication group; nothing committed")
    _git(root, "add", "-A", "--", *scope)
    result = _git(root, "diff", "--cached", "--quiet", check=False)
    if result.returncode == 0:
        return False
    if result.returncode != 1:
        raise DataError("cannot inspect staged generated data")
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="github-actions[bot]",
        GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
        GIT_COMMITTER_NAME="github-actions[bot]",
        GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
    )
    _git(root, "commit", "-m", message, env=env)
    try:
        _git(root, "push", "origin", f"HEAD:{DATA_REF}")
    except DataError:
        # Keep the failed publication visible to unattended runs' staged-edit
        # guard. A clean unpublished commit could otherwise be reset away by
        # prepare. Soft reset preserves generated bytes and unrelated edits.
        _git(root, "reset", "--soft", head)
        raise
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="reset disposable publisher to current source + data")
    read = commands.add_parser("materialize", help="read published data into this checkout")
    read.add_argument("--baseline", action="store_true", help="make a detached data baseline (requires a clean tracked checkout)")
    write = commands.add_parser("publish", help="commit prepared data to oracle-data only")
    write.add_argument("--group", choices=PUBLISH_GROUPS, required=True)
    write.add_argument("--message", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(f"prepared {prepare()}")
        elif args.command == "materialize":
            print(f"materialized {len(materialize(baseline=args.baseline))} data files")
        else:
            print("published oracle-data" if publish(group=args.group, message=args.message) else "no data changes")
    except DataError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
