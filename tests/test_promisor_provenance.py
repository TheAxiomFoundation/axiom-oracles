"""Provenance reads must leave a partial clone's object store alone.

A promisor (partial) clone may lack trees or blobs that its remote promised.
Git fetches such objects on demand into the checkout's object store, so a
provenance read that walks a missing tree would change the repository it
only meant to describe. The invariant: every provenance read leaves the
object store byte-for-byte unchanged, and a tree it cannot read without a
fetch is reported unverifiable (``dirty: None``), never clean.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from axiom_oracles.provenance import (
    _git_sha,
    _git_toplevel,
    worktree_attestation,
    worktree_state,
)

_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.test",
}


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch):
    for key, value in _GIT_ENV.items():
        monkeypatch.setenv(key, value)
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_NO_LAZY_FETCH",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
    ):
        monkeypatch.delenv(key, raising=False)


def _git(repo: Path, *args: str, stdin: bytes | None = None, **env: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        input=stdin,
        env={**os.environ, **_GIT_ENV, **env},
    ).stdout


def _snapshot(directory: Path) -> dict[str, str]:
    """Every file under ``directory`` with its SHA-256."""
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _promisor_clone(tmp_path: Path, *, drop: str) -> tuple[Path, str]:
    """A blob-filtered clone whose promisor pack lacks one object.

    ``drop`` is ``"subtree"`` (a tree below the root) or ``"root"`` (HEAD's
    root tree). The index and working files still match HEAD exactly, so the
    only reason the tree is unreadable is the missing promised object.
    """
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q")
    _git(upstream, "config", "uploadpack.allowFilter", "true")
    _git(upstream, "config", "uploadpack.allowAnySHA1InWant", "true")
    (upstream / "rules").mkdir()
    (upstream / "rules" / "rate.yaml").write_text("rate: 0.18\n")
    (upstream / "README").write_text("rules\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "rules")

    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--filter=blob:none", f"file://{upstream}", str(clone)],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )
    missing = (
        _git(clone, "rev-parse", "HEAD:rules" if drop == "subtree" else "HEAD^{tree}")
        .strip()
        .decode()
    )
    objects = _git(
        clone, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)"
    ).split()
    keep = b"".join(oid + b"\n" for oid in objects if oid.decode() != missing)
    pack_dir = clone / ".git" / "objects" / "pack"
    old = list(pack_dir.iterdir())
    name = _git(clone, "pack-objects", str(pack_dir / "pack"), stdin=keep).strip()
    for path in old:
        path.unlink()
    (pack_dir / f"pack-{name.decode()}.promisor").write_bytes(b"")
    probe = subprocess.run(
        ["git", "-C", str(clone), "cat-file", "-e", missing],
        capture_output=True,
        # Older Git ignores GIT_NO_LAZY_FETCH; an unreachable remote keeps
        # this check from fetching the object it looks for.
        env={
            **os.environ,
            **_GIT_ENV,
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "protocol.allow",
            "GIT_CONFIG_VALUE_0": "never",
        },
    )
    assert probe.returncode != 0, "fixture should lack the promised object"
    return clone, missing


@pytest.mark.parametrize("drop", ["subtree", "root"])
def test_missing_promised_tree_is_unverifiable_and_not_fetched(tmp_path, drop):
    clone, _ = _promisor_clone(tmp_path, drop=drop)
    git_dir = clone / ".git"
    before = _snapshot(git_dir / "objects")

    assert worktree_state(clone) == {"dirty": None}
    attestation = worktree_attestation(clone)
    assert attestation["dirty"] is None
    assert attestation["worktree_toplevel"] == str(clone.resolve())
    # Metadata reads still work: they need no tree.
    assert _git_sha(clone) is not None
    assert _git_toplevel(clone) == str(clone.resolve())

    assert _snapshot(git_dir / "objects") == before
    assert not (git_dir / "FETCH_HEAD").exists()


def test_complete_promisor_clone_still_measures_clean_and_dirty(tmp_path):
    """The refusal is about missing objects, not about partial clones."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q")
    _git(upstream, "config", "uploadpack.allowFilter", "true")
    (upstream / "rate.yaml").write_text("rate: 0.18\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "rules")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--filter=blob:none", f"file://{upstream}", str(clone)],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )
    before = _snapshot(clone / ".git" / "objects")
    assert worktree_state(clone) == {"dirty": False}
    (clone / "rate.yaml").write_text("rate: 0.2\n")
    state = worktree_state(clone)
    assert state["dirty"] is True and len(state["diff_sha256"]) == 64
    assert _snapshot(clone / ".git" / "objects") == before


def test_inherited_git_config_survives_the_read_guard(tmp_path, monkeypatch):
    """The guard appends to inherited ``GIT_CONFIG_COUNT`` entries."""
    from axiom_oracles.provenance import _git_read_env

    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.quotePath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    env = _git_read_env()
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_0"] == "core.quotePath"
    assert env["GIT_CONFIG_KEY_1"] == "protocol.allow"
    assert env["GIT_CONFIG_VALUE_1"] == "never"
    assert env["GIT_NO_LAZY_FETCH"] == "1"
