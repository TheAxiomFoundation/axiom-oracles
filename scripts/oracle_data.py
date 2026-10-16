#!/usr/bin/env python3
"""Publish generated oracle data separately from protected source history.

``prepare`` is destructive and belongs in a disposable publisher checkout:
it combines current main source with the latest data before generation.
``materialize`` changes only generated files in a reader's worktree; its
optional ``--baseline`` prepares an unverified detached producer merge so
generation can reconcile reviewed main data with already-published data.
"""

from __future__ import annotations

import argparse
import ast
from fnmatch import fnmatchcase
from functools import cache
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tempfile

DATA_BRANCH = "oracle-data"
DATA_REF = f"refs/heads/{DATA_BRANCH}"
MAIN_REF = "refs/heads/main"
MANIFEST_PATH = "dashboard/public/data/manifest.json"
SNAPSHOT_PATH = "dashboard/public/data/snapshot.json"
SNAPSHOT_SCHEMA = "axiom.oracle_data_snapshot.v1"
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
    "all": DATA_PATHS,
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
    return Path(
        _git(root or Path.cwd(), "rev-parse", "--show-toplevel").stdout.decode().strip()
    )


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
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }

    def path_value(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return (
                scripts.parent
                if node.id == "REPO_ROOT"
                else path_value(assignments[node.id])
            )
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
        _declared_output("conformance_scoreboard.py", "DASHBOARD_DATA_DIR")
        + "/conformance_detail_*.json",
        _declared_output("conformance_burndown.py", "OUTPUT_PATH"),
        _declared_output("exercise_census.py", "OUTPUT_PATH"),
        _declared_output("de_certificate_census.py", "OUTPUT_PATH"),
        _declared_output("certify.py", "OUT_DIR") + "/*.json",
        _declared_output("generate_affected_map.py", "OUTPUT_PATH"),
        MANIFEST_PATH,
        SNAPSHOT_PATH,
    )


def _manifest_union(
    root: Path, source: str, data: str, *, prefer_data: bool
) -> bytes | None:
    identities = [
        _tree_identities(root, ref, [MANIFEST_PATH])[MANIFEST_PATH]
        for ref in (source, data)
    ]
    if identities[0] == identities[1]:
        return None
    documents = []
    for identity in identities:
        if identity["oid"] is None:
            documents.append({"reports": []})
            continue
        if identity["mode"] not in ("100644", "100755"):
            raise DataError(
                "report manifest must be a regular JSON file; checkout unchanged"
            )
        try:
            doc = json.loads(_git(root, "cat-file", "blob", identity["oid"]).stdout)
            if (
                not isinstance(doc, dict)
                or not isinstance(doc.get("reports"), list)
                or any(not isinstance(entry, str) for entry in doc["reports"])
            ):
                raise ValueError("expected a reports list of file names")
        except ValueError as exc:
            raise DataError(
                f"cannot union report manifest: {exc}; checkout unchanged"
            ) from exc
        documents.append(doc)
    preferred, other = documents[::-1] if prefer_data else documents
    preferred["reports"] = list(dict.fromkeys(preferred["reports"] + other["reports"]))
    return (json.dumps(preferred, indent=2) + "\n").encode()


def _merge_tree(
    root: Path,
    source: str,
    data: str,
    *,
    prefer_data: bool = False,
    reconcile: bool = False,
) -> str:
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
            path
            for path, stages in conflicts.items()
            if not (reconcile and _in_scope(path, DATA_PATHS))
            and not any(
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
    # index, or the worktree. Publishers verify after prepare; readers must
    # validate the resulting snapshot binding before applying this tree.
    with tempfile.TemporaryDirectory(prefix="oracle-data-merge-") as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        _git(root, "read-tree", tree, env=env)
        updates = []
        for path, stages in conflicts.items():
            mode, oid = stages.get("3" if prefer_data else "2", ("0", "0" * 40))
            updates.append(f"{mode} {oid}\t{path}\0".encode())
        if manifest is not None:
            oid = (
                _git(root, "hash-object", "-w", "--stdin", input=manifest)
                .stdout.decode()
                .strip()
            )
            updates.append(f"100644 {oid}\t{MANIFEST_PATH}\0".encode())
        _git(
            root, "update-index", "-z", "--index-info", input=b"".join(updates), env=env
        )
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
    return (
        _git(
            root,
            "commit-tree",
            tree,
            *parent_args,
            input=b"Merge current source and published oracle data\n",
            env=env,
        )
        .stdout.decode()
        .strip()
    )


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


def _reader_merge_tree(
    root: Path, source: str, data: str, *, producer: bool = False
) -> str:
    # Merge data changes in isolation. Source code carried by the full-history
    # data branch is irrelevant to a reader and can conflict with feature work.
    base = _git(root, "merge-base", source, data).stdout.decode().strip()
    scoped = _scoped_tree(root, base, data)
    data_only = (
        base
        if scoped == _sha(root, f"{base}^{{tree}}")
        else _commit_tree(root, scoped, base)
    )
    return _merge_tree(root, source, data_only, prefer_data=not producer)


def _state_path(root: Path) -> Path:
    location = Path(
        _git(root, "rev-parse", "--git-path", "oracle-data-materialized.json")
        .stdout.decode()
        .strip()
    )
    return location if location.is_absolute() else root / location


def _snapshot_document(root: Path, tree: str) -> dict:
    """Bind the complete generated-file set, including deletions and modes.

    Git blob object IDs hash the file contents (with Git's blob header). This
    records identities, not a claim that the generators or reports are correct.
    Publication runs the freshness gates before recording these identities.
    """
    manifest = _tree_identities(root, tree, [MANIFEST_PATH])[MANIFEST_PATH]
    if manifest["oid"] is not None:
        try:
            document = json.loads(
                _git(root, "cat-file", "blob", manifest["oid"]).stdout
            )
            if not isinstance(document, dict) or not isinstance(
                document.get("reports"), list
            ):
                raise ValueError("expected a reports list")
            if any(
                os.path.normpath(
                    os.path.join(str(root), "dashboard/public/data", name)
                ).casefold()
                == str(root / SNAPSHOT_PATH).casefold()
                for name in document["reports"]
            ):
                raise DataError(
                    "snapshot.json is reserved metadata and cannot be a dashboard report"
                )
            if any(
                not isinstance(name, str)
                or not name
                or name in (".", "..")
                or "\0" in name
                or PurePosixPath(name).name != name
                or "\\" in name
                for name in document["reports"]
            ):
                raise ValueError(
                    "report names must be plain file names inside dashboard/public/data"
                )
        except (ValueError, TypeError, KeyError) as exc:
            raise DataError("invalid report manifest; cannot bind snapshot") from exc
    files = _tree_identities(root, tree, list(DATA_PATHS))
    files = {
        path: identity
        for path, identity in files.items()
        if path != SNAPSHOT_PATH and identity["oid"] is not None
    }
    if any(identity["mode"] not in ("100644", "100755") for identity in files.values()):
        raise DataError(
            "snapshot contains non-regular generated files; checkout unchanged"
        )
    return {"schema": SNAPSHOT_SCHEMA, "files": files}


def _verify_snapshot(root: Path, tree: str) -> list[str]:
    identity = _tree_identities(root, tree, [SNAPSHOT_PATH])[SNAPSHOT_PATH]
    try:
        if identity["mode"] not in ("100644", "100755"):
            raise ValueError("missing regular snapshot.json")
        document = json.loads(_git(root, "cat-file", "blob", identity["oid"]).stdout)
        if document != _snapshot_document(root, tree):
            raise ValueError("generated-file hashes or file set differ")
    except (ValueError, TypeError) as exc:
        raise DataError(
            f"incompatible oracle-data snapshot: {exc}; checkout unchanged; "
            "prepare, regenerate and publish a reconciled snapshot first"
        ) from exc
    return [*document["files"], SNAPSHOT_PATH]


def write_snapshot(root: Path | None = None) -> None:
    """Record generated identities after the caller's regeneration/check gates.

    Use a private index so this also binds untracked generated files without
    staging unrelated changes. This function itself does not run freshness gates.
    """
    root = _repository(root)
    ignored = _git(root, "check-ignore", "--quiet", "--", SNAPSHOT_PATH, check=False)
    if ignored.returncode == 0:
        raise DataError("snapshot.json is ignored; refusing snapshot binding")
    if ignored.returncode != 1:
        raise DataError(
            "cannot inspect snapshot ignore rules; refusing snapshot binding"
        )
    tree = _publication_tree(root, DATA_PATHS)
    document = _snapshot_document(root, tree)
    untracked = _git(root, "ls-files", "--others", "-z", "--", *DATA_PATHS).stdout
    if any(
        path.decode() != SNAPSHOT_PATH and path.decode() not in document["files"]
        for path in untracked.split(b"\0")
        if path
    ):
        raise DataError(
            "generated files are outside the candidate snapshot; refusing snapshot binding"
        )
    paths = list(document["files"])
    _guard_checkout_bytes(root, [*paths, SNAPSHOT_PATH])
    if _worktree_identities(root, paths) != document["files"]:
        raise DataError(
            "generated bytes differ from their staged Git blobs; refusing snapshot binding"
        )
    (root / SNAPSHOT_PATH).write_text(json.dumps(document, sort_keys=True) + "\n")


def _publication_tree(root: Path, scope: tuple[str, ...]) -> str:
    """Build exactly what would be committed, without changing the real index."""
    with tempfile.TemporaryDirectory(prefix="oracle-data-candidate-") as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        _git(root, "read-tree", "HEAD", env=env)
        tracked = _git(
            root, "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", *scope
        ).stdout.split(b"\0")
        # Optional aggregate families need not exist in every source revision.
        # Keep tracked deletions, but do not pass never-present pathspecs to add.
        selected = [
            path
            for path in scope
            if os.path.lexists(root / path)
            or any(name and _in_scope(name.decode(), (path,)) for name in tracked)
        ]
        if selected:
            _git(root, "add", "-A", "--", *selected, env=env)
        return _git(root, "write-tree", env=env).stdout.decode().strip()


def _bind_publication(root: Path, tree: str) -> None:
    _guard_checkout_bytes(root, [SNAPSHOT_PATH])
    (root / SNAPSHOT_PATH).write_text(
        json.dumps(_snapshot_document(root, tree), sort_keys=True) + "\n"
    )
    _git(root, "add", "--", SNAPSHOT_PATH)


def _verify_publication(root: Path, tree: str) -> None:
    """Run all publication gates against the exact candidate, never local edits."""
    runner = _git(
        root, "show", f"{tree}:scripts/commit_refreshed_report.sh", check=False
    )
    if runner.returncode or b"VERIFY_DERIVED_REFRESH" not in runner.stdout:
        raise DataError(
            "publication requires the check-only freshness gate runner; nothing committed"
        )
    with tempfile.TemporaryDirectory(prefix="oracle-data-verify-") as directory:
        checkout = Path(directory) / "checkout"
        _git(
            root,
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(root),
            str(checkout),
        )
        candidate = _commit_tree(root, tree, _sha(root, "HEAD"))
        _git(checkout, "checkout", "--quiet", "--detach", candidate)
        # A shared clone's origin is the disposable publisher, which need not
        # have a local main branch. NZ ancestor gates must see the actual
        # remote main history rather than silently losing their merge-base.
        main = _fetch(root, MAIN_REF)
        assert main is not None
        _git(checkout, "update-ref", "refs/remotes/origin/main", main)
        env = {
            **os.environ,
            "VERIFY_DERIVED_REFRESH": "1",
            "SIMULATE_DERIVED_REFRESH": "0",
            "PYTHON": sys.executable,
            "PYTHONPATH": str(checkout),
            "AXIOM_ORACLES_DATA_SOURCE": "checkout",
        }
        try:
            process = subprocess.Popen(
                ["bash", "scripts/commit_refreshed_report.sh", "recovery", DATA_BRANCH],
                cwd=checkout,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as exc:
            raise DataError(
                f"publication gate environment failed; nothing committed: {exc}"
            ) from exc
        with process:
            try:
                output, errors = process.communicate(timeout=540)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise DataError(
                    "publication freshness gates timed out; nothing committed"
                ) from exc
        if process.returncode:
            diagnostics = output + errors
            if (
                process.returncode in (126, 127)
                or re.search(
                    r"ModuleNotFoundError:|ImportError:|command not found",
                    diagnostics,
                )
                or (
                    "FileNotFoundError:" in diagnostics
                    and (
                        "subprocess.py" in diagnostics
                        or re.search(
                            r"No such file or directory: ['\"](?:git|bash|sh|curl|uv|python[\d.]*)['\"]",
                            diagnostics,
                        )
                    )
                )
            ):
                raise DataError(
                    "publication gate environment failed; install the package and required tools; "
                    f"nothing committed:\n{output}{errors}"
                )
            raise DataError(
                "publication freshness gates failed; prepare and regenerate all affected aggregates; "
                f"nothing committed:\n{output}{errors}"
            )
        if _publication_tree(checkout, DATA_PATHS) != tree:
            raise DataError(
                "freshness gates changed candidate generated files; nothing committed"
            )


def _read_state(root: Path) -> dict:
    try:
        state = json.loads(_state_path(root).read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise DataError(f"cannot read previous data materialization: {exc}") from exc
    if not isinstance(state, dict) or any(
        not isinstance(path, str)
        or "\0" in path
        or PurePosixPath(path).is_absolute()
        or ".." in PurePosixPath(path).parts
        or not _in_scope(path, DATA_PATHS)
        or not isinstance(identity, dict)
        or set(identity) != {"oid", "mode"}
        for path, identity in state.items()
    ):
        raise DataError("invalid previous data materialization metadata")
    return state


def _tree_identities(root: Path, tree: str, paths: list[str]) -> dict:
    identities = {path: {"oid": None, "mode": None} for path in paths}
    for start in range(0, len(paths), 200):
        entries = _git(
            root,
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            tree,
            "--",
            *paths[start : start + 200],
        ).stdout
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
        oid = (
            _git(
                root, "hash-object", "--stdin", input=os.fsencode(os.readlink(absolute))
            )
            .stdout.decode()
            .strip()
        )
        return {"oid": oid, "mode": "120000"}
    if not stat.S_ISREG(mode):
        raise DataError(f"local data path {path} is not a file; checkout unchanged")
    oid = _git(root, "hash-object", "--no-filters", "--", path).stdout.decode().strip()
    return {"oid": oid, "mode": "100755" if mode & 0o111 else "100644"}


def _worktree_identities(root: Path, paths: list[str]) -> dict:
    # One Git process per file makes a bound real-corpus reader take minutes.
    # Hash raw bytes: clean filters must not hide a report/overview mismatch.
    identities, regular = {}, []
    for path in paths:
        try:
            mode = (root / path).lstat().st_mode
        except FileNotFoundError:
            identities[path] = {"oid": None, "mode": None}
            continue
        if stat.S_ISREG(mode):
            identities[path] = {"mode": "100755" if mode & 0o111 else "100644"}
            regular.append(path)
        else:
            identities[path] = _worktree_identity(root, path)
    for start in range(0, len(regular), 200):
        batch = regular[start : start + 200]
        hashes = (
            _git(root, "hash-object", "--no-filters", "--", *batch)
            .stdout.decode()
            .splitlines()
        )
        if len(hashes) != len(batch):
            raise DataError("cannot hash generated files; checkout unchanged")
        for path, oid in zip(batch, hashes, strict=True):
            identities[path]["oid"] = oid
    return identities


def _guard_checkout_bytes(root: Path, paths: list[str]) -> None:
    """Refuse transformations that could change bound bytes during restoration."""
    for name, safe in (
        ("core.autocrlf", {"false", "no", "off", "0", "input"}),
        ("core.eol", {"lf", "native"}),
    ):
        configured = _git(root, "config", "--get", name, check=False)
        value = configured.stdout.decode().strip().lower()
        if configured.returncode == 0 and value not in safe:
            raise DataError(
                "Git checkout filters can change bound data bytes; checkout unchanged"
            )
    attributes = _git(
        root,
        "check-attr",
        "-z",
        "--stdin",
        "--all",
        input=b"".join(path.encode() + b"\0" for path in paths),
    ).stdout.split(b"\0")
    for start in range(0, len(attributes) - 1, 3):
        _, attribute, value = attributes[start : start + 3]
        if (attribute == b"eol" and value.lower() == b"crlf") or attribute in (
            b"filter",
            b"working-tree-encoding",
            b"ident",
        ):
            raise DataError(
                "Git checkout filters can change bound data bytes; checkout unchanged"
            )


def _guard_worktree(
    root: Path, source: str, tree: str, paths: list[str], previous: dict
) -> dict:
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
                raise DataError(
                    f"local data parent {parent.relative_to(root)} is not a directory; checkout unchanged"
                )
    for start in range(0, len(paths), 200):
        changed = _git(
            root,
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--",
            *paths[start : start + 200],
        ).stdout
        if changed:
            raise DataError(
                "staged data overlaps published updates; checkout unchanged"
            )
    _guard_checkout_bytes(root, paths)
    committed = _tree_identities(root, source, paths)
    desired = _tree_identities(root, tree, paths)
    current_files = _worktree_identities(root, paths)
    for path in paths:
        current = current_files[path]
        allowed = [committed[path], desired[path]]
        if path in previous:
            allowed.append(previous[path])
        if current not in allowed:
            raise DataError(
                f"local data edits overlap published update at {path}; checkout unchanged"
            )
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


def prepare(root: Path | None = None, *, reconcile: bool = False) -> str:
    """Prepare a disposable publisher from current remote main and data."""
    root = _repository(root)
    main = _fetch(root, MAIN_REF)
    assert main is not None
    data = _fetch(root, DATA_REF, optional=True)
    baseline = main
    if data is not None:
        # Reconciliation keeps reviewed main bytes for conflicting generated
        # reports. Full regeneration and exact-candidate gates are mandatory
        # before the automated publisher may bind or publish this merge.
        # Authored inputs outside DATA_PATHS always remain fail-closed.
        tree = _merge_tree(root, main, data, reconcile=reconcile)
        baseline = _composite_commit(root, tree, main, data)
    _checkout_baseline(root, baseline)
    return baseline


def materialize(root: Path | None = None, *, baseline: bool = False) -> list[str]:
    """Read bound data, or prepare an unverified producer baseline.

    Producer baselines use the publisher's aggregate conflict policy. They
    deliberately accept an unbound merged tree: generation and candidate
    gates must reconcile it before publication. Consumer reads verify the
    exact published binding before changing any checkout bytes.
    """
    if os.environ.get("AXIOM_ORACLES_DATA_SOURCE") == "checkout":
        return []
    root = _repository(root)
    source = _sha(root, "HEAD")
    data = _fetch(root, DATA_REF, optional=True)
    # A disappeared branch also removes the last overlay. Reconcile recorded
    # paths against HEAD with exactly the same guards as an ordinary refresh.
    tree = (
        source
        if data is None
        else _reader_merge_tree(root, source, data, producer=baseline)
    )
    if (
        not baseline
        and data is not None
        and (
            _tree_identities(root, tree, [SNAPSHOT_PATH])
            != _tree_identities(root, data, [SNAPSHOT_PATH])
        )
    ):
        raise DataError(
            "incompatible oracle-data snapshot: merged binding differs from the published binding; checkout unchanged"
        )
    bound = [] if data is None or baseline else _verify_snapshot(root, tree)
    changed = _git(
        root,
        "diff",
        "--no-renames",
        "--name-only",
        "-z",
        source,
        tree,
        "--",
        *DATA_PATHS,
    ).stdout
    paths = [p.decode() for p in changed.split(b"\0") if p]
    previous = _read_state(root)
    # Include prior materializations that the remote has since reverted
    # to HEAD, otherwise such a revert would leave old data in the reader.
    previous_targets = _tree_identities(root, tree, list(previous))
    paths.extend(
        path
        for path in previous
        if path not in paths and previous[path] != previous_targets[path]
    )
    # Keep checkout-byte and local-file guards for producers too, independently
    # of snapshot validity. An unverified baseline still must preserve local
    # work and must not smudge unchanged generated files on detached checkout.
    guarded = bound
    if baseline:
        guarded = [
            path
            for path, identity in _tree_identities(root, tree, list(DATA_PATHS)).items()
            if identity["oid"] is not None
        ]
    targets = list(dict.fromkeys([*paths, *guarded]))
    if bound:
        if _git(
            root, "diff", "--cached", "--name-only", "-z", "--", *DATA_PATHS
        ).stdout:
            raise DataError(
                "staged data overlaps the bound snapshot; checkout unchanged"
            )
    if bound or baseline:
        untracked = _git(root, "ls-files", "--others", "-z", "--", *DATA_PATHS).stdout
        if any(path.decode() not in targets for path in untracked.split(b"\0") if path):
            raise DataError(
                "local data files are outside the prepared data tree; checkout unchanged"
            )
    desired = _guard_worktree(root, source, tree, targets, previous) if targets else {}
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
        commit = (
            source
            if data is None
            else _composite_commit(root, scoped_tree, source, data)
        )
        _checkout_baseline(root, commit)
    else:
        present = b"".join(
            path.encode() + b"\0" for path in paths if desired[path]["oid"] is not None
        )
        if present:
            _git(
                root,
                "restore",
                "--worktree",
                f"--source={tree}",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
                input=present,
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
        raise DataError(
            "publish requires a detached baseline or the local oracle-data branch"
        )
    main = _fetch(root, MAIN_REF)
    data = _fetch(root, DATA_REF, optional=True)
    if not _ancestor(root, main, head) or (data and not _ancestor(root, data, head)):
        raise DataError(
            "source or data advanced; prepare and regenerate before publishing"
        )
    staged = _git(root, "diff", "--cached", "--name-only", "-z").stdout
    if any(not _in_scope(p.decode(), scope) for p in staged.split(b"\0") if p):
        raise DataError("staged files outside the publication group; nothing committed")
    tree = _publication_tree(root, scope)
    _verify_publication(root, tree)
    # Verification may take several minutes. Recheck remote ancestry before
    # changing the caller's index or making the publication commit.
    main = _fetch(root, MAIN_REF)
    data = _fetch(root, DATA_REF, optional=True)
    if not _ancestor(root, main, head) or (data and not _ancestor(root, data, head)):
        raise DataError(
            "source or data advanced; prepare and regenerate before publishing"
        )
    if _publication_tree(root, scope) != tree:
        raise DataError(
            "publication files changed during verification; nothing committed"
        )
    _bind_publication(root, tree)
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
    prep = commands.add_parser(
        "prepare", help="reset disposable publisher to current source + data"
    )
    prep.add_argument(
        "--reconcile",
        action="store_true",
        help="retain reviewed main data on conflicts; regenerate all data before publishing",
    )
    commands.add_parser(
        "snapshot",
        help="record generated content identities after freshness gates (does not run gates)",
    )
    read = commands.add_parser(
        "materialize", help="read published data into this checkout"
    )
    read.add_argument(
        "--baseline",
        action="store_true",
        help="prepare an unverified producer baseline (requires a clean tracked checkout)",
    )
    write = commands.add_parser(
        "publish", help="commit prepared data to oracle-data only"
    )
    write.add_argument("--group", choices=PUBLISH_GROUPS, required=True)
    write.add_argument("--message", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(f"prepared {prepare(reconcile=args.reconcile)}")
        elif args.command == "snapshot":
            write_snapshot()
            print("recorded generated content identities")
        elif args.command == "materialize":
            print(f"materialized {len(materialize(baseline=args.baseline))} data files")
        else:
            print(
                "published oracle-data"
                if publish(group=args.group, message=args.message)
                else "no data changes"
            )
    except DataError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
