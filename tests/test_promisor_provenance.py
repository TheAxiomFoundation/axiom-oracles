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
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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
        "GIT_ALLOW_PROTOCOL",
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


_TREE_PATHS = ("", "a", "a/b", "c")


def _layered_promisor_clone(root: Path, missing_path: str) -> Path:
    """A blob-filtered clone of a nested layout lacking one promised tree."""
    upstream = root / "upstream"
    upstream.mkdir(parents=True)
    _git(upstream, "init", "-q")
    _git(upstream, "config", "uploadpack.allowFilter", "true")
    _git(upstream, "config", "uploadpack.allowAnySHA1InWant", "true")
    for relative in ("top.yaml", "a/one.yaml", "a/b/two.yaml", "c/three.yaml"):
        target = upstream / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{relative}: 1\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-qm", "rules")
    clone = root / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--filter=blob:none", f"file://{upstream}", str(clone)],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )
    spec = f"HEAD:{missing_path}" if missing_path else "HEAD^{tree}"
    missing = _git(clone, "rev-parse", spec).strip()
    objects = _git(
        clone, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)"
    ).split()
    keep = b"".join(oid + b"\n" for oid in objects if oid != missing)
    pack_dir = clone / ".git" / "objects" / "pack"
    old = list(pack_dir.iterdir())
    name = _git(clone, "pack-objects", str(pack_dir / "pack"), stdin=keep).strip()
    for path in old:
        path.unlink()
    (pack_dir / f"pack-{name.decode()}.promisor").write_bytes(b"")
    return clone


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    missing_path=st.sampled_from(_TREE_PATHS),
    edit=st.sampled_from([None, "top.yaml", "a/one.yaml", "a/b/two.yaml"]),
)
def test_property_missing_tree_never_attests_clean_or_fetches(
    tmp_path_factory, missing_path, edit
):
    """Whatever tree is missing, and dirty or not, the read never fetches.

    Every tree on the path to a tracked file is read, so a missing one makes
    the whole measurement unverifiable rather than clean or dirty.
    """
    clone = _layered_promisor_clone(tmp_path_factory.mktemp("promisor"), missing_path)
    if edit is not None:
        (clone / edit).write_text("edited: 1\n")
    objects = clone / ".git" / "objects"
    before = _snapshot(objects)
    assert worktree_state(clone) == {"dirty": None}
    assert worktree_attestation(clone)["dirty"] is None
    assert _snapshot(objects) == before


# --- each guard on its own ---------------------------------------------------
#
# Git 2.45 added GIT_NO_LAZY_FETCH, and some distributions backport it (this
# repository's CI images do). A Git without it would still lazily fetch, so
# reads also set GIT_ALLOW_PROTOCOL, which replaces every protocol.allow and
# protocol.<name>.allow setting. A ``git`` wrapper that drops one variable
# before running the real Git leaves the other as the only guard.


def _wrap_git(directory: Path, monkeypatch, *, drop: str) -> None:
    real = shutil.which("git")
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = directory / "git"
    wrapper.write_text(f'#!/bin/sh\nunset {drop}\nexec "{real}" "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")


def _allow_file_protocol(directory: Path, monkeypatch) -> None:
    """A user setting common in CI (submodule tests) that re-allows file://."""
    config = directory / "gitconfig"
    config.write_text('[protocol "file"]\n\tallow = always\n')
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))


def _native_lazy_fetch_switch(tmp_path: Path) -> bool:
    """Whether this Git honours GIT_NO_LAZY_FETCH on its own."""
    (tmp_path / "probe").mkdir()
    clone, missing = _promisor_clone(tmp_path / "probe", drop="subtree")
    before = _snapshot(clone / ".git" / "objects")
    subprocess.run(
        ["git", "-C", str(clone), "cat-file", "-e", missing],
        capture_output=True,
        env={**os.environ, **_GIT_ENV, "GIT_NO_LAZY_FETCH": "1"},
    )
    return _snapshot(clone / ".git" / "objects") == before


@pytest.mark.parametrize("override", ["protocol-config", "inherited-allow-protocol"])
@pytest.mark.parametrize("drop", ["subtree", "root"])
def test_protocol_guard_alone_blocks_fetch_despite_inherited_allows(
    tmp_path, monkeypatch, drop, override
):
    """Without GIT_NO_LAZY_FETCH, user or inherited allows still cannot fetch."""
    clone, _ = _promisor_clone(tmp_path, drop=drop)
    _allow_file_protocol(tmp_path, monkeypatch)
    if override == "inherited-allow-protocol":
        monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    _wrap_git(tmp_path / "bin", monkeypatch, drop="GIT_NO_LAZY_FETCH")
    objects = clone / ".git" / "objects"
    before = _snapshot(objects)
    assert worktree_state(clone) == {"dirty": None}
    assert worktree_attestation(clone)["dirty"] is None
    assert _snapshot(objects) == before


@pytest.mark.parametrize("drop", ["subtree", "root"])
def test_lazy_fetch_switch_alone_blocks_fetch(tmp_path, monkeypatch, drop):
    """Without GIT_ALLOW_PROTOCOL, GIT_NO_LAZY_FETCH still stops the fetch."""
    if not _native_lazy_fetch_switch(tmp_path):
        pytest.skip("this Git ignores GIT_NO_LAZY_FETCH")
    (tmp_path / "case").mkdir()
    clone, _ = _promisor_clone(tmp_path / "case", drop=drop)
    _allow_file_protocol(tmp_path, monkeypatch)
    _wrap_git(tmp_path / "bin", monkeypatch, drop="GIT_ALLOW_PROTOCOL")
    objects = clone / ".git" / "objects"
    before = _snapshot(objects)
    assert worktree_state(clone) == {"dirty": None}
    assert _snapshot(objects) == before


def test_engine_source_status_never_fetches_a_missing_root_tree(tmp_path):
    """A build cannot be receipted clean by fetching its own missing tree.

    ``git status`` compares the index with HEAD's tree, so in a promisor
    clone missing that tree it would fetch it, after which the attestation
    sees a complete store and the source reads clean.
    """
    from axiom_oracles.engine_identity import EngineIdentityError, _clean_source_commit

    clone, _ = _promisor_clone(tmp_path, drop="root")
    objects = clone / ".git" / "objects"
    before = _snapshot(objects)
    with pytest.raises(EngineIdentityError):
        _clean_source_commit(clone.resolve())
    assert _snapshot(objects) == before
