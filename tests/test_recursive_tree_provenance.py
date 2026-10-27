"""Recursive provenance must identify the tracked content in submodules.

An initialized descendant follows the same rules as its parent: hidden
tracked edits make the whole tree dirty, distinct index or working bytes
produce distinct manifests, and failed inspection propagates as unknown.
Untracked output and an empty uninitialized submodule's unchanged pin stay
clean; an absent non-sparse submodule directory remains a tracked deletion.
Measuring any level must preserve its index and shared-index metadata.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from axiom_oracles.provenance import rulespec_provenance, worktree_state


_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.test",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.test",
}
_RULE = "rule.yaml"
_HEAD_BYTES = b"rate: 0.18\n"


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch):
    for name, value in _GIT_ENV.items():
        monkeypatch.setenv(name, value)
    for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE", "GIT_PREFIX",
    ):
        monkeypatch.delenv(name, raising=False)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env={**os.environ, **_GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _seed(repo: Path) -> Path:
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / _RULE).write_bytes(_HEAD_BYTES)
    (repo / ".gitignore").write_text("*.out\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _add_submodule(parent: Path, source: Path) -> None:
    _git(
        parent, "-c", "protocol.file.allow=always", "submodule", "add",
        "-q", str(source), "child",
    )
    _git(parent, "commit", "-qm", "add child")


def _submodule_tree(base: Path, depth: int = 1) -> tuple[Path, Path]:
    """Build a committed parent with a checked-out descendant at ``depth``."""
    source = _seed(base / "source-leaf")
    for level in range(depth - 1):
        enclosing = _seed(base / f"source-parent-{level}")
        _add_submodule(enclosing, source)
        source = enclosing
    parent = _seed(base / "rulespec-rw")
    _add_submodule(parent, source)
    _git(
        parent, "-c", "protocol.file.allow=always", "submodule", "update",
        "--init", "--recursive", "-q",
    )
    return parent, parent.joinpath(*(["child"] * depth))


@pytest.fixture
def run_comparison():
    source = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("recursive_run_comparison", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
@pytest.mark.parametrize("depth", [1, 2])
def test_hidden_descendant_edit_cannot_leave_parent_clean(tmp_path, flag, depth):
    parent, child = _submodule_tree(tmp_path, depth)
    _git(child, "update-index", flag, _RULE)
    (child / _RULE).write_text("rate: 0.17\n")
    assert _git(parent, "status", "--porcelain", "--untracked-files=no") == ""

    [entry] = rulespec_provenance([parent])

    assert entry["dirty"] is True
    assert len(entry["diff_sha256"]) == 64
    assert _git(child, "ls-files", "-v", _RULE)[0] in ("h", "S")


def test_weekly_run_refuses_hidden_nested_edit_before_publication(
    tmp_path, monkeypatch, run_comparison
):
    parent, child = _submodule_tree(tmp_path / "repos", depth=2)
    _git(child, "update-index", "--assume-unchanged", _RULE)
    (child / _RULE).write_text("rate: 0.17\n")
    assert _git(parent, "status", "--porcelain", "--untracked-files=no") == ""

    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "rw-vat.yaml").write_text(
        "name: rw-vat\nrunner:\n  type: fake-rw\n  parameters:\n"
        "    sample_size: 0\n"
        f"    rulespec_roots: [{json.dumps(str(parent))}]\n"
        "artifacts:\n  report_basename: rw-vat\n"
        "dashboard:\n  filename: rw-vat.json\n"
    )
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    reports = tmp_path / "reports"
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", comparisons)
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "weekly")
    monkeypatch.setattr(
        "sys.argv", ["run_comparison.py", "rw-vat", "--output-dir", str(reports)]
    )

    executed_bytes = []

    def fake_runner(runner, output):
        executed_bytes.append((child / _RULE).read_bytes())
        output.write_text(json.dumps({"compared_values": 1, "mismatch_count": 0}))

    monkeypatch.setitem(run_comparison.RUNNERS, "fake-rw", fake_runner)
    with pytest.raises(SystemExit, match="weekly run refused before publication"):
        run_comparison.main()

    assert executed_bytes == [b"rate: 0.17\n"]
    assert not list(reports.glob("*"))
    assert not list(reports.glob(".*.tmp"))
    assert not list(dashboard.iterdir())


def test_distinct_child_edits_under_one_head_have_distinct_parent_digests(tmp_path):
    parent, child = _submodule_tree(tmp_path)
    head = _git(child, "rev-parse", "HEAD")
    (child / _RULE).write_text("rate: 0.17\n")
    first = worktree_state(parent)
    (child / _RULE).write_text("rate: 0.16\n")
    second = worktree_state(parent)

    assert _git(child, "rev-parse", "HEAD") == head
    assert first["dirty"] is second["dirty"] is True
    assert first["diff_sha256"] != second["diff_sha256"]


@pytest.fixture
def recursive_trees(tmp_path):
    """Reuse committed trees while every property example resets its child."""
    return {
        depth: _submodule_tree(tmp_path / f"depth-{depth}", depth)
        for depth in (1, 2)
    }


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    contents=st.lists(st.binary(max_size=24), min_size=2, max_size=2, unique=True),
    staged=st.booleans(),
    depth=st.integers(min_value=1, max_value=2),
)
@example(contents=[b"rate: 0.17\n", b"rate: 0.16\n"], staged=False, depth=1)
@example(contents=[b"rate: 0.17\n", b"rate: 0.16\n"], staged=True, depth=2)
def test_recursive_digest_distinguishes_tracked_bytes_and_index(
    recursive_trees, contents, staged, depth
):
    """At fixed HEAD, changing either tracked working bytes or index bytes
    changes the parent's digest, including through a nested gitlink."""
    parent, child = recursive_trees[depth]
    try:
        head = _git(child, "rev-parse", "HEAD")
        states = []
        for content in contents:
            (child / _RULE).write_bytes(b"# changed\n" + content)
            if staged:
                _git(child, "add", _RULE)
                (child / _RULE).write_bytes(_HEAD_BYTES)
            states.append(worktree_state(parent))
        assert _git(child, "rev-parse", "HEAD") == head
        assert all(state["dirty"] is True for state in states)
        assert states[0]["diff_sha256"] != states[1]["diff_sha256"]
    finally:
        _git(child, "read-tree", "HEAD")
        (child / _RULE).write_bytes(_HEAD_BYTES)
        assert worktree_state(parent) == {"dirty": False}


@pytest.mark.parametrize("depth", [1, 2])
def test_unverifiable_initialized_descendant_makes_parent_unknown(tmp_path, depth):
    parent, child = _submodule_tree(tmp_path, depth)
    child_gitdir = Path(_git(child, "rev-parse", "--absolute-git-dir"))
    (child_gitdir / "index").unlink()

    assert worktree_state(parent) == {"dirty": None}


@pytest.mark.parametrize("depth", [1, 2])
def test_populated_descendant_without_git_metadata_makes_parent_unknown(tmp_path, depth):
    parent, child = _submodule_tree(tmp_path, depth)
    (child / ".git").unlink()

    assert (child / _RULE).read_bytes() == _HEAD_BYTES
    assert worktree_state(parent) == {"dirty": None}


@pytest.mark.parametrize("depth", [1, 2])
def test_untracked_and_ignored_descendant_output_keeps_parent_clean(tmp_path, depth):
    parent, child = _submodule_tree(tmp_path, depth)
    assert worktree_state(parent) == {"dirty": False}
    (child / "scratch.yaml").write_text("rate: 0.17\n")
    (child / "compiled.out").write_text("generated output\n")

    assert worktree_state(parent) == {"dirty": False}


@pytest.mark.parametrize("absent", [False, True], ids=["empty-directory", "absent"])
def test_uninitialized_submodule_preserves_deletion_behavior(tmp_path, absent):
    parent, child = _submodule_tree(tmp_path)
    _git(parent, "submodule", "deinit", "-f", "--", "child")
    if absent:
        child.rmdir()

    state = worktree_state(parent)
    if absent:
        assert state["dirty"] is True
        assert len(state["diff_sha256"]) == 64
    else:
        assert state == {"dirty": False}


@pytest.mark.parametrize("dirty", [False, True], ids=["clean", "dirty-child"])
def test_recursive_measurement_preserves_split_indexes_and_shared_mtimes(tmp_path, dirty):
    parent, child = _submodule_tree(tmp_path)
    if dirty:
        (child / _RULE).write_text("rate: 0.17\n")
    snapshots = {}
    for repo in (parent, child):
        _git(repo, "update-index", "--split-index")
        gitdir = Path(_git(repo, "rev-parse", "--absolute-git-dir"))
        shared = list(gitdir.glob("sharedindex.*"))
        assert shared
        for path in [gitdir / "index", *shared]:
            content = path.read_bytes()
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
            snapshots[path] = (content, path.stat().st_mtime_ns)

    assert worktree_state(parent)["dirty"] is dirty

    for path, (content, mtime) in snapshots.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
        assert not (path.parent / "index.lock").exists()


def _sparse_seed(repo: Path) -> Path:
    _seed(repo)
    for directory in ("included", "excluded"):
        (repo / directory).mkdir()
        (repo / directory / _RULE).write_bytes(_HEAD_BYTES)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add sparse directories")
    return repo


@pytest.mark.parametrize("linked", [False, True], ids=["ordinary", "linked-worktree"])
def test_actual_sparse_index_preserves_omissions_and_checkout_metadata(tmp_path, linked):
    source = _sparse_seed(tmp_path / "source")
    checkout = source
    if linked:
        checkout = tmp_path / "rulespec-rw"
        _git(source, "config", "extensions.worktreeConfig", "true")
        _git(source, "worktree", "add", "-q", "--detach", str(checkout), "HEAD")
    _git(checkout, "sparse-checkout", "set", "--cone", "--sparse-index", "included")

    # This verifies a real sparse directory entry, rather than merely
    # skip-worktree flags on an otherwise full index.
    assert "S excluded/" in _git(checkout, "ls-files", "--sparse", "-t").splitlines()
    assert not (checkout / "excluded" / _RULE).exists()
    assert _git(checkout, "config", "--worktree", "--bool", "core.sparseCheckout") == "true"
    if linked:
        assert (source / "excluded" / _RULE).read_bytes() == _HEAD_BYTES

    snapshots = {}
    for repo in {source, checkout}:
        gitdir = Path(_git(repo, "rev-parse", "--absolute-git-dir"))
        for relative in ("index", "config.worktree", "info/sparse-checkout"):
            path = gitdir / relative
            if path.exists():
                snapshots[path] = (path.read_bytes(), path.stat().st_mtime_ns)

    assert worktree_state(checkout) == {"dirty": False}
    included = checkout / "included" / _RULE
    included.write_text("rate: 0.17\n")
    assert worktree_state(checkout)["dirty"] is True
    included.write_bytes(_HEAD_BYTES)
    assert worktree_state(checkout) == {"dirty": False}
    if linked:
        assert worktree_state(source) == {"dirty": False}

    for path, (content, mtime) in snapshots.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
        assert not (path.parent / "index.lock").exists()
