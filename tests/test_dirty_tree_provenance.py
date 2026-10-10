"""Dirty-working-tree provenance: the recorded SHA must be what ran.

A rulespec entry's ``sha`` names a commit, but a run reads the working tree.
During the 2026-10-04 SOUTHMOD port a mutated scratch copy of rulespec-rw
reported ``001fa4b`` while running a 17% VAT rate. These tests pin the fix end
to end: :func:`worktree_state` classifies a checkout, ``rulespec_provenance``
records it, ``run_comparison.py`` refuses a non-manual report from a dirty
tree, the affected-rerun selector treats a dirty report as stale, and the
vacuous gate's freshness data surfaces it.

Invariants (each tested below, the first two property-based):

* ``dirty`` is ``True`` exactly when a tracked file's working-tree or index
  content differs from ``HEAD``; untracked files never change it.
* ``diff_sha256`` is present exactly when ``dirty`` is ``True``, is a function
  of the change alone (the same operations on two clones of one commit hash
  the same, whatever the git config), and reverting the edit returns the
  checkout to ``{"dirty": False}``.
* The checkout's own index and files are never written.
* The gate refuses exactly when the run kind is not ``manual`` and some entry
  with a SHA is not recorded clean.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from axiom_oracles import provenance
from axiom_oracles.provenance import (
    RUN_KINDS,
    describe_rulespec_tree,
    rulespec_provenance,
    unclean_rulespecs,
    worktree_state,
)

SCRIPTS = Path(__file__).parents[1] / "scripts"

#: Neither the developer's nor the CI runner's git config may leak into these
#: tests: the hash-stability tests set hostile config deliberately, per repo.
_HERMETIC_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.test",
}


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch):
    for key, value in _HERMETIC_GIT_ENV.items():
        monkeypatch.setenv(key, value)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(key, raising=False)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(
        name.removesuffix(".py"), SCRIPTS / name
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_HERMETIC_GIT_ENV},
    ).stdout


def _repo(path: Path, files: dict[str, str] | None = None) -> Path:
    """A committed checkout holding ``files`` (default: two rule files)."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    for relpath, text in (files or {"rw/vat.yaml": "rate: 0.18\n", "rw/pit.yaml": "band: 1\n"}).items():
        target = path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "seed")
    return path


def _head(path: Path) -> str:
    return _git(path, "rev-parse", "HEAD").strip()


def _is_hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


# --- worktree_state: the three cases the fix turns on -----------------------


def test_clean_checkout_is_not_dirty(tmp_path):
    assert worktree_state(_repo(tmp_path / "rulespec-rw")) == {"dirty": False}


def test_edited_tracked_file_is_dirty_with_a_diff_hash(tmp_path):
    """The SOUTHMOD case: a tracked rule edited in place, HEAD unchanged."""
    repo = _repo(tmp_path / "rulespec-rw")
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")

    state = worktree_state(repo)

    assert state["dirty"] is True
    assert _is_hex64(state["diff_sha256"])
    assert set(state) == {"dirty", "diff_sha256"}


def test_untracked_files_only_leave_the_tree_clean(tmp_path):
    """Build output and scratch files are untracked; they must not mark a
    tree dirty (nor would an ignored file)."""
    repo = _repo(tmp_path / "rulespec-rw", {".gitignore": "target/\n", "rw/vat.yaml": "rate: 0.18\n"})
    (repo / "target").mkdir()
    (repo / "target" / "compiled.json").write_text("{}")
    (repo / "scratch.yaml").write_text("rate: 0.17\n")
    (repo / "rw" / "new-module.yaml").write_text("x: 1\n")

    assert worktree_state(repo) == {"dirty": False}


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: (r / "rw/vat.yaml").unlink(), id="deleted"),
        pytest.param(
            lambda r: ((r / "rw/vat.yaml").write_text("rate: 0.17\n"), _git(r, "add", "rw/vat.yaml")),
            id="staged-edit",
        ),
        pytest.param(
            lambda r: ((r / "rw/new.yaml").write_text("x: 1\n"), _git(r, "add", "rw/new.yaml")),
            id="staged-new-file",
        ),
        pytest.param(lambda r: _git(r, "mv", "rw/vat.yaml", "rw/vat2.yaml"), id="renamed"),
        pytest.param(lambda r: (r / "rw/vat.yaml").chmod(0o755), id="mode-change"),
        pytest.param(
            lambda r: ((r / "rw/new.yaml").write_text("x: 1\n"), _git(r, "add", "-N", "rw/new.yaml")),
            id="intent-to-add",
        ),
    ],
)
def test_every_tracked_change_kind_is_dirty(tmp_path, mutate):
    repo = _repo(tmp_path / "rulespec-rw")
    mutate(repo)
    state = worktree_state(repo)
    assert state["dirty"] is True
    assert _is_hex64(state["diff_sha256"])


def test_reverting_the_edit_returns_the_tree_to_clean(tmp_path):
    repo = _repo(tmp_path / "rulespec-rw")
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    assert worktree_state(repo)["dirty"] is True
    (repo / "rw/vat.yaml").write_text("rate: 0.18\n")
    assert worktree_state(repo) == {"dirty": False}


def test_a_subdirectory_reports_the_whole_repository(tmp_path):
    """The recorded SHA names the whole commit, so an edit outside the path
    the run was pointed at still makes it dirty."""
    repo = _repo(tmp_path / "rulespec-rw")
    (repo / "elsewhere.yaml").write_text("x: 1\n")
    _git(repo, "add", "elsewhere.yaml")
    _git(repo, "commit", "-q", "-m", "more")
    (repo / "elsewhere.yaml").write_text("x: 2\n")

    from_subdir = worktree_state(repo / "rw")
    assert from_subdir["dirty"] is True
    assert from_subdir == worktree_state(repo)


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_edits_hidden_behind_index_flags_are_dirty(tmp_path, flag):
    """``git status`` trusts these flags without reading the file, so an edit
    behind one runs under a clean-looking tree. The state must see it, and
    must not clear the flag in the checkout's own index."""
    repo = _repo(tmp_path / "rulespec-rw")
    _git(repo, "update-index", flag, "rw/vat.yaml")
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    assert _git(repo, "status", "--porcelain") == ""  # git itself is blind

    state = worktree_state(repo)

    assert state["dirty"] is True
    assert _is_hex64(state["diff_sha256"])
    listing = _git(repo, "ls-files", "-v", "rw/vat.yaml")
    assert listing[0] in ("S", "h"), "the checkout's own index was rewritten"


def test_hidden_flag_edit_hashes_like_the_plain_edit(tmp_path):
    """Clearing the flags on an index copy yields the ordinary diff, so the
    hash of a hidden edit equals the hash of the same unhidden edit."""
    plain = _repo(tmp_path / "a" / "rulespec-rw")
    hidden = _repo(tmp_path / "b" / "rulespec-rw")
    _git(hidden, "update-index", "--skip-worktree", "rw/vat.yaml")
    for repo in (plain, hidden):
        (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    assert worktree_state(plain)["diff_sha256"] == worktree_state(hidden)["diff_sha256"]


def test_a_file_a_sparse_checkout_leaves_out_is_not_dirty(tmp_path):
    """A sparse checkout leaves skip-worktree files off disk; their rules
    cannot have run, so they must not mark the tree dirty."""
    repo = _repo(tmp_path / "rulespec-rw")
    _git(repo, "sparse-checkout", "set", "--no-cone", "/*", "!/rw/pit.yaml")
    assert not (repo / "rw/pit.yaml").exists()
    assert _git(repo, "ls-files", "-v", "rw/pit.yaml").startswith("S ")
    assert worktree_state(repo) == {"dirty": False}
    # An edit inside the sparse cone still counts.
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    assert worktree_state(repo)["dirty"] is True


def _sparse_repo(path: Path, cone: bool, filename: str = "rule.yaml") -> Path:
    repo = _repo(
        path,
        {f"{directory}/{filename}": "rate: 0.18\n" for directory in ("included", "excluded")},
    )
    if cone:
        _git(repo, "sparse-checkout", "set", "--cone", "included")
    else:
        _git(repo, "sparse-checkout", "set", "--no-cone", "/included/")
    assert not (repo / "excluded" / filename).exists()
    assert (repo / "included" / filename).exists()
    return repo


def _hide_sparse_included_deletion(repo: Path, filename: str = "rule.yaml") -> None:
    path = f"included/{filename}"
    _git(repo, "update-index", "--skip-worktree", path)
    (repo / path).unlink()
    assert _git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert _git(repo, "show", f"HEAD:{path}") == "rate: 0.18\n"


@pytest.mark.parametrize("cone", [True, False], ids=["cone", "non-cone"])
@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("rule.yaml", id="plain-path"),
        pytest.param('rule\n\t"\\name.yaml', id="delimiters-and-quotes"),
        pytest.param("règle-税.yaml", id="multibyte-path"),
    ],
)
def test_sparse_included_hidden_deletion_is_dirty(tmp_path, cone, filename):
    """Only paths excluded by effective patterns may be absent and clean.

    A skip-worktree flag on an included file cannot excuse its deletion,
    even with filenames that cannot be passed through line-based Git output.
    """
    repo = _sparse_repo(tmp_path / "rulespec-rw", cone, filename)
    assert worktree_state(repo) == {"dirty": False}
    _hide_sparse_included_deletion(repo, filename)
    index = repo / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)

    state = worktree_state(repo)

    assert state["dirty"] is True
    assert _is_hex64(state["diff_sha256"])
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    assert _git(repo, "ls-files", "-v", f"included/{filename}").startswith("S ")


@pytest.mark.parametrize("cone", [True, False], ids=["cone", "non-cone"])
def test_weekly_gate_refuses_sparse_included_hidden_deletion(
    tmp_path, run_comparison, cone
):
    repo = _sparse_repo(tmp_path / "rulespec-rw", cone)
    _hide_sparse_included_deletion(repo)

    with pytest.raises(SystemExit, match="weekly run refused before publication"):
        run_comparison._guard_unclean_rulespec_trees(
            "sparse-probe", _provenance("weekly", *rulespec_provenance([repo]))
        )


@pytest.mark.parametrize("failure", ["command-failed", "os-error"])
def test_unverifiable_sparse_rules_refuse_weekly_publication(
    tmp_path, monkeypatch, run_comparison, failure
):
    """A failed sparse-pattern check cannot prove an absent path is exempt."""
    repo = _sparse_repo(tmp_path / "rulespec-rw", cone=True)
    real_output = provenance._git_output

    def fail_rule_check(path, *args, **kwargs):
        if "check-rules" in args:
            if failure == "command-failed":
                raise subprocess.CalledProcessError(1, ["git", *args])
            raise OSError("sparse rules could not be inspected")
        return real_output(path, *args, **kwargs)

    monkeypatch.setattr(provenance, "_git_output", fail_rule_check)

    assert worktree_state(repo) == {"dirty": None}
    with pytest.raises(SystemExit, match="working tree unverifiable"):
        run_comparison._guard_unclean_rulespec_trees(
            "sparse-probe", _provenance("weekly", *rulespec_provenance([repo]))
        )


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    included=st.sets(st.integers(min_value=0, max_value=3), min_size=1, max_size=3),
    cone=st.booleans(),
    rate=st.integers(min_value=0, max_value=100),
)
@example(included={0}, cone=True, rate=18)
@example(included={1, 2}, cone=False, rate=17)
def test_sparse_patterns_alone_determine_missing_flagged_path_dirtiness(
    tmp_path, included, cone, rate
):
    """Different selections and rule contents obey the same sparse model:
    genuine omissions are clean; one included hidden deletion is dirty;
    restoring its bytes is clean without changing the original index flag.
    """
    with tempfile.TemporaryDirectory(dir=tmp_path, prefix="sparse-") as directory:
        content = f"rate: {rate}\n"
        repo = _repo(
            Path(directory) / "rulespec-rw",
            {f"case-{number}/rule.yaml": content for number in range(4)},
        )
        selections = [f"case-{number}" for number in sorted(included)]
        if cone:
            _git(repo, "sparse-checkout", "set", "--cone", *selections)
        else:
            patterns = [f"/{selection}/" for selection in selections]
            _git(repo, "sparse-checkout", "set", "--no-cone", *patterns)
        for number in range(4):
            assert (repo / f"case-{number}/rule.yaml").exists() is (number in included)
        assert worktree_state(repo) == {"dirty": False}

        deleted = f"case-{min(included)}/rule.yaml"
        _git(repo, "update-index", "--skip-worktree", deleted)
        (repo / deleted).unlink()
        assert _git(repo, "status", "--porcelain", "--untracked-files=no") == ""

        state = worktree_state(repo)

        assert state["dirty"] is True, (included, cone, rate, state)
        assert _is_hex64(state["diff_sha256"])
        (repo / deleted).write_text(content)
        assert worktree_state(repo) == {"dirty": False}


@pytest.mark.parametrize(
    "hide",
    [
        pytest.param(lambda r: _git(r, "update-index", "--assume-unchanged", "rw/vat.yaml"), id="assume-unchanged"),
        pytest.param(lambda r: _git(r, "update-index", "--skip-worktree", "rw/vat.yaml"), id="skip-worktree-not-sparse"),
        pytest.param(
            lambda r: (
                _git(r, "config", "core.ignoreStat", "true"),
                (r / "rw/vat.yaml").write_text("rate: 0.19\n"),
                _git(r, "commit", "-qam", "under ignoreStat"),
            ),
            id="core.ignoreStat",
        ),
    ],
)
def test_a_deletion_behind_an_index_flag_is_dirty(tmp_path, hide):
    """Outside a sparse checkout an absent flagged file is a deletion: the
    run went without that module, so the tree is dirty."""
    repo = _repo(tmp_path / "rulespec-rw")
    hide(repo)
    assert _git(repo, "ls-files", "-v", "rw/vat.yaml")[0] in "Sh"
    (repo / "rw/vat.yaml").unlink()
    assert _git(repo, "status", "--porcelain") == ""  # git itself is blind
    state = worktree_state(repo)
    assert state["dirty"] is True
    assert _is_hex64(state["diff_sha256"])


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_a_hidden_edit_survives_a_later_index_rewrite(tmp_path, flag):
    """A flagged entry keeps the stat data from before the edit; once any git
    command rewrites the index after the edit, that stale stat no longer
    looks racy. The revealed entry's stat is zeroed, so git still compares
    the content: a same-size edit made in the commit's second is caught."""
    repo = _repo(tmp_path / "rulespec-rw")
    _git(repo, "update-index", flag, "rw/vat.yaml")
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")  # same size as 0.18
    time.sleep(1.1)
    _git(repo, "update-index", "--refresh")
    _git(repo, "status")
    assert worktree_state(repo)["dirty"] is True


def test_the_checkouts_own_index_is_never_written(tmp_path):
    """Porcelain status/diff refresh the index they read and can rewrite it
    under index.lock; another session committing in a shared checkout would
    then hit the lock. Everything runs against a private copy."""
    repo = _repo(tmp_path / "rulespec-rw")
    _git(repo, "update-index", "--skip-worktree", "rw/pit.yaml")
    time.sleep(1.1)
    (repo / "rw/pit.yaml").touch()  # stat-only change: a refresh would rewrite
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    index = repo / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    files_before = sorted(p.name for p in (repo / ".git").iterdir())

    assert worktree_state(repo)["dirty"] is True

    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    assert sorted(p.name for p in (repo / ".git").iterdir()) == files_before
    assert _git(repo, "ls-files", "-v", "rw/pit.yaml").startswith("S ")


@pytest.mark.parametrize("target", ["none", "missing", "not-git", "no-commit"])
def test_unanswerable_checkouts_are_unverifiable_not_clean(tmp_path, target):
    if target == "none":
        path = None
    elif target == "missing":
        path = tmp_path / "absent"
    elif target == "not-git":
        path = tmp_path / "plain"
        path.mkdir()
    else:
        path = tmp_path / "empty"
        path.mkdir()
        _git(path, "init", "-q")
    assert worktree_state(path) == {"dirty": None}


def test_worktree_state_never_raises_when_git_is_missing(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "rulespec-rw")

    def no_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(provenance.subprocess, "run", no_git)
    assert worktree_state(repo) == {"dirty": None}


# --- diff_sha256: a function of the edit alone ------------------------------


def _edit_two_files(repo: Path) -> None:
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    (repo / "rw/pit.yaml").write_text("band: 2\n")


def test_the_same_edit_on_the_same_commit_hashes_the_same(tmp_path):
    origin = _repo(tmp_path / "origin")
    clones = []
    for name in ("one", "two"):
        clone = tmp_path / name / "rulespec-rw"
        clone.parent.mkdir()
        _git(tmp_path, "clone", "-q", str(origin), str(clone))
        _edit_two_files(clone)
        clones.append(clone)
    assert _head(clones[0]) == _head(clones[1])
    first, second = (worktree_state(c) for c in clones)
    assert first == second
    assert first["dirty"] is True


def test_a_different_edit_hashes_differently(tmp_path):
    repo = _repo(tmp_path / "rulespec-rw")
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")
    seventeen = worktree_state(repo)["diff_sha256"]
    (repo / "rw/vat.yaml").write_text("rate: 0.16\n")
    sixteen = worktree_state(repo)["diff_sha256"]
    assert seventeen != sixteen


def test_the_hash_ignores_git_config(tmp_path, monkeypatch):
    """The hash is built from object ids and raw bytes, not diff text, so no
    diff, attribute, line-ending or compression setting, nor GIT_DIFF_OPTS,
    can change the hash of an edit on a developer's or CI runner's machine."""
    files = {
        "rw/vat.yaml": "a: 1\n\nb: 2\nc: 3\nd: 4\ne: 5\nf: 6\ng: 7\nh: 8\ni: 9\nj: 10\n",
        "rw/naïve.yaml": "x: 1\n",
        "rw/moved.yaml": "long enough content to be detected as a rename\n" * 5,
        "rw/table.pdf": "%PDF-1.4 placeholder\n",
    }
    repo = _repo(tmp_path / "rulespec-rw", files)
    (repo / "rw/vat.yaml").write_text(
        "a: 0\n\nb: 2\nc: 3\nd: 4\ne: 5\nf: 6\ng: 7\nh: 8\ni: 9\nj: 11\n"
    )
    (repo / "rw/naïve.yaml").write_text("x: 2\n")
    _git(repo, "mv", "rw/moved.yaml", "rw/renamed.yaml")
    (repo / "rw/table.pdf").write_bytes(bytes(range(256)) * 4)  # binary edit
    baseline = worktree_state(repo)
    assert baseline["dirty"] is True

    order = tmp_path / "order.txt"
    order.write_text("rw/renamed.yaml\nrw/naïve.yaml\n")
    attributes = tmp_path / "attributes"
    attributes.write_text("*.yaml diff=yamlx text eol=crlf\n")
    for key, value in {
        "diff.noprefix": "true",
        "diff.mnemonicPrefix": "true",
        "diff.algorithm": "patience",
        "diff.context": "10",
        "diff.interHunkContext": "10",
        "diff.indentHeuristic": "false",
        "diff.suppressBlankEmpty": "true",
        "diff.renames": "copies",
        "diff.relative": "true",
        "diff.orderFile": str(order),
        "diff.external": "false",
        "diff.submodule": "log",
        "diff.yamlx.xfuncname": "^.*rate.*$",
        "diff.yamlx.textconv": "rev",
        "core.attributesFile": str(attributes),
        "core.quotePath": "false",
        "core.abbrev": "7",
        "core.compression": "9",
        "core.autocrlf": "true",
        "core.eol": "crlf",
        "color.ui": "always",
        "color.diff": "always",
    }.items():
        _git(repo, "config", key, value)
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("*.yaml diff=yamlx\n*.pdf -diff\n")

    assert worktree_state(repo) == baseline
    assert worktree_state(repo / "rw") == baseline
    monkeypatch.setenv("GIT_DIFF_OPTS", "-u10")
    assert worktree_state(repo) == baseline


def _expected_manifest(repo: Path) -> bytes:
    """An independent rebuild of the documented manifest: per path git
    reports changed, its HEAD entry, index entries and the sha256 of its
    bytes on disk."""
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=no"],
        check=True, capture_output=True, env={**os.environ, **_HERMETIC_GIT_ENV},
    ).stdout
    lines = []
    for path in sorted({r[3:] for r in status.split(b"\0") if r}):
        name = path.decode()
        tree = _git(repo, "ls-tree", "--full-tree", "HEAD", "--", name).strip()
        head = (tree.split("\t")[0].split(" ")[0] + " " + tree.split("\t")[0].split(" ")[2]) if tree else "-"
        staged = sorted(line.split("\t")[0] for line in _git(repo, "ls-files", "-s", "--", name).splitlines())
        target = repo / name
        if target.is_symlink():
            work = "120000 sha256:" + hashlib.sha256(os.fsencode(os.readlink(target))).hexdigest()
        elif target.exists():
            mode = "100755" if target.stat().st_mode & 0o111 else "100644"
            work = f"{mode} sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        else:
            work = "-"
        lines.append("\0".join([name, head, ";".join(staged) or "-", work]) + "\n")
    return b"axiom_oracles.worktree_manifest.v1\n" + "".join(lines).encode()


def test_the_hash_is_sha256_of_the_documented_manifest(tmp_path):
    """Differential check of ``_change_manifest`` against an independent
    rebuild of its documented format, over every kind of change at once."""
    repo = _repo(
        tmp_path / "rulespec-rw",
        {"rw/vat.yaml": "rate: 0.18\n", "rw/pit.yaml": "band: 1\n", "rw/old.yaml": "x\n", "rw/x.sh": "echo\n"},
    )
    (repo / "rw/vat.yaml").write_text("rate: 0.17\n")  # unstaged edit
    (repo / "rw/pit.yaml").write_text("band: 2\n")
    _git(repo, "add", "rw/pit.yaml")  # staged edit
    (repo / "rw/pit.yaml").write_text("band: 3\n")  # ...then edited again
    (repo / "rw/old.yaml").unlink()  # deletion
    (repo / "rw/x.sh").chmod(0o755)  # mode change
    (repo / "rw/blob.bin").write_bytes(bytes(range(256)))
    _git(repo, "add", "rw/blob.bin")  # staged binary
    (repo / "rw/link").symlink_to("vat.yaml")
    _git(repo, "add", "rw/link")  # staged symlink

    expected = hashlib.sha256(_expected_manifest(repo)).hexdigest()
    assert worktree_state(repo) == {"dirty": True, "diff_sha256": expected}


# --- invariant: dirty <=> tracked content differs from HEAD (property) -------

_FILES = ("a.yaml", "b.yaml", "c.yaml")
_OPS = st.lists(
    st.tuples(
        st.sampled_from(
            ["edit", "revert", "delete", "stage", "untracked", "ignored"]
        ),
        st.sampled_from(_FILES),
        st.integers(min_value=0, max_value=3),
    ),
    max_size=6,
)


def _apply_ops(repo: Path, ops) -> bool:
    """Apply ``ops`` to ``repo`` while tracking an independent dict model of
    HEAD, the index and the working tree; return whether the model says some
    tracked path's index or working-tree content differs from HEAD."""
    files = {name: f"{name}: 0\n" for name in _FILES}
    head = dict(files)
    index: dict[str, str | None] = dict(files)
    work: dict[str, str | None] = dict(files)
    for op, name, value in ops:
        path = repo / name
        if op == "edit":
            work[name] = f"{name}: {value}\n"
            path.write_text(work[name])
        elif op == "revert":
            work[name] = head[name]
            path.write_text(head[name])
        elif op == "delete":
            work[name] = None
            path.unlink(missing_ok=True)
        elif op == "stage":
            if index[name] is None and work[name] is None:
                continue  # nothing left for git to stage
            _git(repo, "add", "-A", "--", name)
            index[name] = work[name]
        elif op == "untracked":
            (repo / f"new-{name}-{value}").write_text("untracked\n")
        else:
            (repo / f"{name}.{value}.out").write_text("ignored\n")
    return any(index[n] != head[n] or work[n] != head[n] for n in _FILES)


def _model_repo(path: Path) -> Path:
    return _repo(path, {**{n: f"{n}: 0\n" for n in _FILES}, ".gitignore": "*.out\n"})


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(ops=_OPS)
@example(ops=[("delete", "a.yaml", 0), ("stage", "a.yaml", 0), ("stage", "a.yaml", 0)])
@example(ops=[("edit", "a.yaml", 1), ("stage", "a.yaml", 0), ("revert", "a.yaml", 0)])
def test_dirty_iff_tracked_content_differs_from_head(ops):
    """Model check against an independent dict model of HEAD, the index and
    the working tree: ``dirty`` is exactly "some tracked path's index or
    working-tree content differs from HEAD", whatever untracked or ignored
    files exist; ``diff_sha256`` accompanies it exactly then; and the call is
    deterministic."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _model_repo(Path(tmp) / "rulespec-rw")
        expected_dirty = _apply_ops(repo, ops)

        state = worktree_state(repo)

        assert state["dirty"] is expected_dirty, (ops, state)
        assert ("diff_sha256" in state) is expected_dirty
        assert worktree_state(repo) == state


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(ops=_OPS, hostile=st.booleans())
def test_the_same_change_on_two_clones_hashes_the_same(ops, hostile):
    """Determinism across checkouts: two clones of one commit given the same
    operations record the same state, even when one carries config that
    reshapes diff output (the hash never reads diff text)."""
    with tempfile.TemporaryDirectory() as tmp:
        origin = _model_repo(Path(tmp) / "origin")
        states = []
        for name in ("one", "two"):
            clone = Path(tmp) / name / "rulespec-rw"
            clone.parent.mkdir()
            _git(Path(tmp), "clone", "-q", str(origin), str(clone))
            if hostile and name == "two":
                for key, value in {
                    "diff.algorithm": "patience",
                    "diff.noprefix": "true",
                    "core.autocrlf": "true",
                    "diff.context": "9",
                }.items():
                    _git(clone, "config", key, value)
            _apply_ops(clone, ops)
            states.append(worktree_state(clone))
        assert states[0] == states[1], (ops, states)


# --- rulespec_provenance records the state ----------------------------------


def test_rulespec_provenance_records_clean_and_dirty_checkouts(tmp_path):
    clean = _repo(tmp_path / "clean" / "rulespec-us")
    dirty = _repo(tmp_path / "dirty" / "rulespec-rw")
    (dirty / "rw/vat.yaml").write_text("rate: 0.17\n")

    entries = rulespec_provenance([clean, dirty, tmp_path / "rulespec-nz"])

    assert entries[0] == {
        "repo": "TheAxiomFoundation/rulespec-us",
        "sha": _head(clean),
        "sha_toplevel": str(clean.resolve()),
        "worktree_toplevel": str(clean.resolve()),
        "dirty": False,
    }
    assert entries[1]["repo"] == "TheAxiomFoundation/rulespec-rw"
    assert entries[1]["sha"] == _head(dirty)
    assert entries[1]["dirty"] is True
    assert _is_hex64(entries[1]["diff_sha256"])
    # A path with no checkout claims no commit, so it records no tree state.
    assert entries[2] == {"repo": "TheAxiomFoundation/rulespec-nz", "sha": None}


def test_rulespec_provenance_keeps_one_commit_in_two_states(tmp_path):
    """Dedup is on the whole entry: a clean and a mutated checkout of the
    same commit are two different trees and both are recorded."""
    origin = _repo(tmp_path / "origin")
    clean = tmp_path / "a" / "rulespec-rw"
    dirty = tmp_path / "b" / "rulespec-rw"
    for clone in (clean, dirty):
        clone.parent.mkdir()
        _git(tmp_path, "clone", "-q", str(origin), str(clone))
    (dirty / "rw/vat.yaml").write_text("rate: 0.17\n")

    entries = rulespec_provenance([clean, dirty, clean])

    assert [e["dirty"] for e in entries] == [False, True]
    assert {e["sha"] for e in entries} == {_head(origin)}


# --- unclean_rulespecs / describe_rulespec_tree -----------------------------

_SHA = "0" * 39 + "1"


@pytest.mark.parametrize(
    ("entry", "lenient", "strict"),
    [
        ({"repo": "r", "sha": _SHA, "dirty": False}, False, False),
        ({"repo": "r", "sha": _SHA, "dirty": True, "diff_sha256": "f" * 64}, True, True),
        ({"repo": "r", "sha": _SHA, "dirty": None}, True, True),
        ({"repo": "r", "sha": _SHA}, False, True),
        ({"repo": "r", "sha": None}, False, False),
        ({"repo": "r", "sha": None, "dirty": True}, False, False),
        ("not-an-entry", False, False),
    ],
)
def test_unclean_rulespecs_table(entry, lenient, strict):
    assert bool(unclean_rulespecs([entry])) is lenient
    assert bool(unclean_rulespecs([entry], require_recorded=True)) is strict


_ENTRY = st.fixed_dictionaries(
    {"repo": st.sampled_from(["a/r1", "a/r2"]), "sha": st.sampled_from([None, "", _SHA])},
    optional={
        "dirty": st.sampled_from([True, False, None]),
        "diff_sha256": st.just("e" * 64),
        "sha_toplevel": st.sampled_from([None, "", "relative", "/repo/a", "/repo/b", 1]),
        "worktree_toplevel": st.sampled_from([None, "", "relative", "/repo/a", "/repo/b", 1]),
    },
)


def _expected_unclean_rulespecs(entries, *, require_recorded=False):
    """Independent model: a SHA needs valid matching roots and a clean state."""
    expected = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("sha"):
            continue
        roots = [entry.get("sha_toplevel"), entry.get("worktree_toplevel")]
        identity_recorded = any(key in entry for key in ("sha_toplevel", "worktree_toplevel"))
        identity_valid = not identity_recorded or (
            all(isinstance(root, str) and root.startswith("/") for root in roots)
            and roots[0] == roots[1]
        )
        state_valid = (
            entry["dirty"] is False if "dirty" in entry else not require_recorded
        )
        if not (identity_valid and state_valid):
            expected.append(entry)
    return expected


@settings(deadline=None)
@given(st.lists(_ENTRY, max_size=6))
@example(entries=[{"repo": "a/r1", "sha": _SHA, "dirty": True}, {"repo": "a/r2", "sha": _SHA, "dirty": None}])
@example(entries=[{"repo": "a/r1", "sha": _SHA, "dirty": False, "sha_toplevel": "/repo/a", "worktree_toplevel": "/repo/b"}])
def test_unclean_rulespecs_properties(entries):
    lenient = unclean_rulespecs(entries)
    strict = unclean_rulespecs(entries, require_recorded=True)
    assert all(any(entry is candidate for candidate in strict) for entry in lenient)
    for require_recorded, result in ((False, lenient), (True, strict)):
        assert result == (
            _expected_unclean_rulespecs(entries, require_recorded=require_recorded)
        )
        assert all(entry.get("sha") for entry in result)
        positions = [next(i for i, entry in enumerate(entries) if entry is found) for found in result]
        assert positions == sorted(positions)


def test_describe_rulespec_tree_names_the_state():
    dirty = {"repo": "o/rulespec-rw", "sha": "001fa4b" + "0" * 33, "dirty": True, "diff_sha256": "ab" * 32}
    assert describe_rulespec_tree(dirty) == (
        "o/rulespec-rw@001fa4b00000 (dirty, diff sha256 abababababab)"
    )
    assert "unverifiable" in describe_rulespec_tree({**dirty, "dirty": None})
    assert "not recorded" in describe_rulespec_tree({"repo": "o/r", "sha": _SHA})


# --- run_comparison: the publication gate -----------------------------------


@pytest.fixture
def run_comparison():
    return _load_script("run_comparison.py")


def _provenance(run_kind, *entries):
    return {"run_kind": run_kind, "rulespecs": list(entries)}


_DIRTY = {"repo": "TheAxiomFoundation/rulespec-rw", "sha": "001fa4b" + "0" * 33, "dirty": True, "diff_sha256": "cd" * 32}
_CLEAN = {"repo": "TheAxiomFoundation/rulespec-us", "sha": _SHA, "dirty": False}


@pytest.mark.parametrize("run_kind", [k for k in RUN_KINDS if k != "manual"])
def test_gate_refuses_a_non_manual_run_on_a_dirty_tree(run_comparison, run_kind):
    with pytest.raises(SystemExit) as excinfo:
        run_comparison._guard_unclean_rulespec_trees(
            "rw-vat", _provenance(run_kind, _CLEAN, _DIRTY)
        )
    message = str(excinfo.value.code)
    assert message.startswith(f"rw-vat: {run_kind} run refused before publication:")
    assert "TheAxiomFoundation/rulespec-rw@001fa4b00000" in message
    assert "diff sha256 cdcdcdcdcdcd" in message
    assert "rulespec-us" not in message  # only the unclean tree is named


def test_gate_refuses_a_non_manual_run_whose_tree_state_was_not_recorded(run_comparison):
    """Every SHA this code stamps comes with a tree state; a SHA without one
    means some path skipped the check, which is not proof of a clean tree."""
    with pytest.raises(SystemExit, match="working tree not recorded"):
        run_comparison._guard_unclean_rulespec_trees(
            "s", _provenance("weekly", {"repo": "o/rulespec-us", "sha": _SHA})
        )


def test_gate_warns_but_publishes_a_manual_dirty_run(run_comparison, capsys):
    run_comparison._guard_unclean_rulespec_trees("rw-vat", _provenance("manual", _DIRTY))
    err = capsys.readouterr().err
    assert err.startswith("WARNING: rw-vat:")
    assert "TheAxiomFoundation/rulespec-rw@001fa4b00000" in err


@pytest.mark.parametrize("run_kind", RUN_KINDS)
def test_gate_is_silent_for_clean_or_sha_less_entries(run_comparison, run_kind, capsys):
    run_comparison._guard_unclean_rulespec_trees(
        "s", _provenance(run_kind, _CLEAN, {"repo": "o/rulespec-nz", "sha": None})
    )
    run_comparison._guard_unclean_rulespec_trees("s", {"run_kind": run_kind})
    assert capsys.readouterr().err == ""


@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(run_kind=st.sampled_from(RUN_KINDS), entries=st.lists(_ENTRY, max_size=5))
@example(run_kind="weekly", entries=[{"repo": "a/r1", "sha": _SHA, "dirty": True}, {"repo": "a/r2", "sha": _SHA, "dirty": None}])
@example(run_kind="weekly", entries=[{"repo": "a/r1", "sha": _SHA, "dirty": False, "sha_toplevel": "/repo/a", "worktree_toplevel": "/repo/b"}])
def test_gate_refuses_exactly_non_manual_unclean_runs(run_comparison, run_kind, entries):
    expected_unclean = _expected_unclean_rulespecs(entries, require_recorded=True)
    assert unclean_rulespecs(entries, require_recorded=True) == expected_unclean
    expect_refusal = run_kind != "manual" and bool(expected_unclean)
    try:
        run_comparison._guard_unclean_rulespec_trees("s", _provenance(run_kind, *entries))
    except SystemExit:
        refused = True
    else:
        refused = False
    assert refused is expect_refusal


def _registry_suite(tmp_path, monkeypatch, run_comparison, rulespec_root):
    """A one-suite registry whose fake runner reports from ``rulespec_root``."""
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "rw-vat.yaml").write_text(
        "name: rw-vat\n"
        "runner:\n"
        "  type: fake-rw\n"
        "  parameters:\n"
        "    sample_size: 0\n"
        f"    rulespec_roots: [{json.dumps(str(rulespec_root))}]\n"
        "artifacts:\n"
        "  report_basename: rw-vat\n"
        "dashboard:\n"
        "  filename: rw-vat.json\n"
    )
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", comparisons)
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard)

    def fake_runner(runner, output):
        output.write_text(json.dumps({"compared_values": 1, "mismatch_count": 0}))

    monkeypatch.setitem(run_comparison.RUNNERS, "fake-rw", fake_runner)
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv", ["run_comparison.py", "rw-vat", "--output-dir", str(output_dir)]
    )
    return output_dir, dashboard


def _published(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if not p.name.startswith("."))


def test_main_refuses_an_affected_rerun_on_a_dirty_tree_and_publishes_nothing(
    run_comparison, tmp_path, monkeypatch
):
    root = _repo(tmp_path / "work" / "rulespec-rw")
    (root / "rw/vat.yaml").write_text("rate: 0.17\n")
    output_dir, dashboard = _registry_suite(tmp_path, monkeypatch, run_comparison, root)
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "affected-rerun")

    with pytest.raises(SystemExit) as excinfo:
        run_comparison.main()

    assert str(excinfo.value.code).startswith(
        "rw-vat: affected-rerun run refused before publication:"
    )
    assert _published(output_dir) == []
    assert _published(dashboard) == []
    assert not list(output_dir.glob(".*.tmp")), "staging file left behind"


def test_main_publishes_a_manual_dirty_run_marked_dirty(
    run_comparison, tmp_path, monkeypatch, capsys
):
    root = _repo(tmp_path / "work" / "rulespec-rw")
    (root / "rw/vat.yaml").write_text("rate: 0.17\n")
    expected = worktree_state(root)
    output_dir, dashboard = _registry_suite(tmp_path, monkeypatch, run_comparison, root)
    monkeypatch.delenv("AXIOM_ORACLES_RUN_KIND", raising=False)

    assert run_comparison.main() == 0

    [report_path] = _published(output_dir)
    for path in (report_path, dashboard / "rw-vat.json"):
        rulespecs = json.loads(path.read_text())["provenance"]["rulespecs"]
        assert rulespecs == [
            {
                "repo": "TheAxiomFoundation/rulespec-rw", "sha": _head(root),
                "sha_toplevel": str(root.resolve()),
                "worktree_toplevel": str(root.resolve()), **expected,
            }
        ]
    assert expected["dirty"] is True
    assert "WARNING: rw-vat:" in capsys.readouterr().err


@pytest.mark.parametrize("scenario", ["clean", "untracked-only"])
def test_main_publishes_a_non_manual_run_on_a_clean_tree(
    run_comparison, tmp_path, monkeypatch, capsys, scenario
):
    root = _repo(tmp_path / "work" / "rulespec-rw")
    if scenario == "untracked-only":
        (root / "build-output.json").write_text("{}")
    output_dir, _dashboard = _registry_suite(tmp_path, monkeypatch, run_comparison, root)
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "weekly")

    assert run_comparison.main() == 0

    [report_path] = _published(output_dir)
    rulespecs = json.loads(report_path.read_text())["provenance"]["rulespecs"]
    assert rulespecs == [
        {
            "repo": "TheAxiomFoundation/rulespec-rw", "sha": _head(root), "dirty": False,
            "sha_toplevel": str(root.resolve()), "worktree_toplevel": str(root.resolve()),
        }
    ]
    assert "WARNING" not in capsys.readouterr().err


def test_a_reemission_records_no_tree_state(run_comparison, tmp_path):
    """A re-emission ran no rules, so neither the SHA nor the state of the
    configured checkout belongs in its provenance."""
    root = _repo(tmp_path / "rulespec-us")
    (root / "rw/vat.yaml").write_text("rate: 0.17\n")
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "az-snap-qc"}))
    config = {
        "name": "az-snap-qc",
        "runner": {
            "type": "snap-qc-compare",
            "_reemitted_report": True,
            "rulespec_root": str(root),
            "parameters": {"jurisdiction": "us-az", "fiscal_year": 2024},
        },
    }
    block = run_comparison._build_run_provenance(config, "snap-qc-compare", output)
    assert block["rulespecs"] == [{"repo": "TheAxiomFoundation/rulespec-us", "sha": None}]


def test_completion_records_the_convention_checkouts_state(
    run_comparison, tmp_path, monkeypatch
):
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "affected_map.json").write_text(
        json.dumps({"suites": [{"suite": "demo", "name": "demo", "repos": ["TheAxiomFoundation/rulespec-rw"]}]})
    )
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", comparisons)
    checkout = _repo(tmp_path / "rulespec-rw")
    (checkout / "rw/vat.yaml").write_text("rate: 0.17\n")
    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: checkout)

    [entry] = run_comparison._complete_rulespecs_from_affected_map(
        {"name": "demo"}, {}, []
    )

    assert entry == {
        "repo": "TheAxiomFoundation/rulespec-rw",
        "sha": _head(checkout),
        "sha_toplevel": str(checkout.resolve()),
        "worktree_toplevel": str(checkout.resolve()),
        **worktree_state(checkout),
    }
    assert entry["dirty"] is True


def test_completion_records_the_runner_clones_measured_state(run_comparison, tmp_path, monkeypatch):
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "affected_map.json").write_text(
        json.dumps({"suites": [{"suite": "demo", "name": "demo", "repos": ["TheAxiomFoundation/rulespec-us"]}]})
    )
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", comparisons)
    runner = {
        "_cloned_rulespec_us_sha": _SHA,
        "_cloned_rulespec_us_worktree": {"dirty": True, "diff_sha256": "9" * 64},
    }
    completed = run_comparison._complete_rulespecs_from_affected_map(
        {"name": "demo"}, runner, [{"repo": "TheAxiomFoundation/rulespec-us", "sha": None}]
    )
    assert completed == [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": _SHA,
            "dirty": True,
            "diff_sha256": "9" * 64,
        }
    ]


def test_tax_runner_measures_its_clone_after_the_harness_ran(
    run_comparison, tmp_path, monkeypatch
):
    """The tax lane deletes its rulespec-us clone before provenance is built,
    so it must measure the tree itself, after the harness ran: a harness that
    wrote into a tracked file is recorded dirty, not assumed clean."""
    clone = _repo(tmp_path / "workspace" / "rulespec-us")
    sha = _head(clone)
    for name in ("axiom-encode", "axiom-rules-engine"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(run_comparison, "_ensure_engine_binary", lambda *_a, **_k: None)
    monkeypatch.setattr(run_comparison, "_ensure_rulespec_us_checkout", lambda _remote: clone)
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "uv":  # the harness: writes its report and touches the clone
            (clone / "rw/vat.yaml").write_text("rate: 0.17\n")
            kwargs["stdout"].write("{}")
            return subprocess.CompletedProcess(cmd, 0)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)
    runner = {
        "axiom_encode_repo": str(tmp_path / "axiom-encode"),
        "axiom_rules_repo": str(tmp_path / "axiom-rules-engine"),
        "rulespec_remote": "https://example.test/rulespec-us.git",
        "parameters": {"sample_size": 1, "python": "3.13"},
    }

    run_comparison._run_axiom_encode_tax_ecps_compare(runner, tmp_path / "out.json")

    assert runner["_cloned_rulespec_us_sha"] == sha
    assert runner["_cloned_rulespec_us_worktree"]["dirty"] is True
    assert _is_hex64(runner["_cloned_rulespec_us_worktree"]["diff_sha256"])
    assert not clone.exists(), "the clone is still deleted"


# --- select_affected_suites: a dirty report is stale ------------------------

_MAP = {
    "suites": [
        {"suite": "s1", "name": "s1", "repos": ["o/rulespec-rw"]},
        {
            "suite": "pinned",
            "name": "pinned",
            "repos": ["o/rulespec-us"],
            "pinned": {"o/rulespec-us": "aaa"},
        },
    ]
}


def _report(suite, *rulespecs):
    return {"suite": suite, "provenance": {"rulespecs": list(rulespecs)}}


@pytest.fixture
def selector():
    return _load_script("select_affected_suites.py")


@pytest.mark.parametrize(
    ("dirty", "selected", "words"),
    [
        (True, True, "a dirty working tree at aaa"),
        (None, True, "an unverifiable working tree at aaa"),
        (False, False, None),
        ("absent", False, None),  # a report stamped before the field existed
    ],
)
def test_selector_judges_tree_state_at_head(selector, dirty, selected, words):
    entry = {"repo": "o/rulespec-rw", "sha": "aaa"}
    if dirty != "absent":
        entry["dirty"] = dirty
    decisions = selector.select(
        _MAP,
        {"o/rulespec-rw": "aaa", "o/rulespec-us": "zzz"},
        {
            "s1": _report("s1", entry),
            "pinned": _report("pinned", {"repo": "o/rulespec-us", "sha": "aaa", "dirty": False}),
        },
    )
    by_suite = {d["suite"]: d for d in decisions}
    assert ("s1" in by_suite) is selected
    if words:
        assert words in by_suite["s1"]["reason"]
    assert "pinned" not in by_suite  # recorded == pin, clean: fresh


def test_selector_reruns_a_dirty_pinned_suite(selector):
    """A pinned suite is fresh when it recorded the pin, but not when the pin
    ran from a dirty tree: those numbers are not the pin's."""
    decisions = selector.select(
        _MAP,
        {},
        {"pinned": _report("pinned", {"repo": "o/rulespec-us", "sha": "aaa", "dirty": True})},
    )
    [decision] = [d for d in decisions if d["suite"] == "pinned"]
    assert "a dirty working tree" in decision["reason"]


def test_selector_reruns_a_dirty_report_even_when_head_is_unknown(selector):
    """An unknown HEAD excuses a recorded SHA (staleness unprovable), never a
    dirty run (known not to be any commit's numbers)."""
    decisions = selector.select(
        _MAP,
        {},
        {"s1": _report("s1", {"repo": "o/rulespec-rw", "sha": "aaa", "dirty": True})},
    )
    assert any(d["suite"] == "s1" for d in decisions)


def test_selector_ignores_a_dirty_repo_outside_the_suites_map_entry(selector):
    decisions = selector.select(
        _MAP,
        {"o/rulespec-rw": "aaa"},
        {
            "s1": _report(
                "s1",
                {"repo": "o/rulespec-rw", "sha": "aaa", "dirty": False},
                {"repo": "o/unmapped", "sha": "bbb", "dirty": True},
            )
        },
    )
    assert not any(d["suite"] == "s1" for d in decisions)


_ROOT_IDENTITY = st.fixed_dictionaries(
    {},
    optional={
        "sha_toplevel": st.sampled_from([None, "", "relative", "/repo/a", "/repo/b", 1]),
        "worktree_toplevel": st.sampled_from([None, "", "relative", "/repo/a", "/repo/b", 1]),
    },
)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(identity=_ROOT_IDENTITY)
@example(identity={"sha_toplevel": "/repo/a", "worktree_toplevel": "/repo/b"})
@example(identity={"sha_toplevel": "/repo/a"})
@example(identity={"sha_toplevel": "relative", "worktree_toplevel": "relative"})
@example(identity={"sha_toplevel": None, "worktree_toplevel": None})
def test_selector_freshness_requires_matching_repository_identity(selector, identity):
    """Recorded clean roots must be valid and equal before a SHA proves fresh."""
    entry = {"repo": "o/rulespec-rw", "sha": _SHA, "dirty": False, **identity}
    valid_identity = not identity or (
        isinstance(identity.get("sha_toplevel"), str)
        and isinstance(identity.get("worktree_toplevel"), str)
        and identity["sha_toplevel"].startswith("/")
        and identity["worktree_toplevel"].startswith("/")
        and identity["sha_toplevel"] == identity["worktree_toplevel"]
    )
    affected_map = {"suites": [{"suite": "s1", "name": "s1", "repos": [entry["repo"]]}]}
    expected = [] if valid_identity else ["s1"]
    for heads, pin in (({entry["repo"]: _SHA}, None), ({}, _SHA), ({}, None)):
        if pin is None:
            affected_map["suites"][0].pop("pinned", None)
        else:
            affected_map["suites"][0]["pinned"] = {entry["repo"]: pin}
        decisions = selector.select(affected_map, heads, {"s1": _report("s1", entry)})
        assert [decision["suite"] for decision in decisions] == expected
        if decisions:
            assert "repository identity mismatch" in decisions[0]["reason"]


# --- check_vacuous_gate: freshness surfaces dirty reports -------------------


def test_freshness_lists_dirty_rulespecs_only_when_present(tmp_path, monkeypatch):
    gate = _load_script("check_vacuous_gate.py")
    data = tmp_path / "data"
    data.mkdir()
    stamp = "2026-10-04T00:00:00Z"
    reports = {
        "rw-vat": [
            {"repo": "o/rulespec-rw", "sha": "aaa", "dirty": True, "diff_sha256": "f" * 64},
            {"repo": "o/rulespec-us", "sha": "bbb", "dirty": None},
            {"repo": "o/rulespec-ca", "sha": "ccc", "dirty": False},
        ],
        "clean": [{"repo": "o/rulespec-us", "sha": "bbb", "dirty": False}],
        "legacy": [{"repo": "o/rulespec-us", "sha": "bbb"}],
    }
    for suite, rulespecs in reports.items():
        (data / f"{suite}.json").write_text(
            json.dumps(
                {
                    "suite": suite,
                    "provenance": {
                        "generated_at": stamp,
                        "run_kind": "manual",
                        "rulespecs": rulespecs,
                    },
                }
            )
        )
    monkeypatch.setattr(gate, "DASHBOARD_DATA_DIR", data)
    monkeypatch.setattr(gate, "COVERAGE_OVERVIEW", data / "missing.json")
    monkeypatch.setattr(gate, "AFFECTED_MAP", tmp_path / "missing-map.json")

    suites = {s["suite"]: s for s in gate.build_freshness()["suites"]}

    assert suites["rw-vat"]["dirty_rulespecs"] == ["o/rulespec-rw", "o/rulespec-us"]
    assert "dirty_rulespecs" not in suites["clean"]
    assert "dirty_rulespecs" not in suites["legacy"]
    # ran_against still records the SHAs; the new key qualifies them.
    assert suites["rw-vat"]["ran_against"]["o/rulespec-rw"] == "aaa"



def test_check_mode_warns_in_ci_about_a_dirty_report(tmp_path, monkeypatch, capsys):
    """``--check`` stays green (staleness-style, non-blocking) but emits a
    GitHub ``::warning::`` naming the suite and its dirty repos."""
    gate = _load_script("check_vacuous_gate.py")
    data = tmp_path / "data"
    data.mkdir()
    (data / "rw-vat.json").write_text(
        json.dumps(
            {
                "suite": "rw-vat",
                "provenance": {
                    "generated_at": "2026-10-04T00:00:00Z",
                    "run_kind": "manual",
                    "rulespecs": [
                        {"repo": "o/rulespec-rw", "sha": "aaa", "dirty": True, "diff_sha256": "f" * 64}
                    ],
                },
            }
        )
    )
    monkeypatch.setattr(gate, "DASHBOARD_DATA_DIR", data)
    monkeypatch.setattr(gate, "COVERAGE_OVERVIEW", data / "missing.json")
    monkeypatch.setattr(gate, "AFFECTED_MAP", tmp_path / "missing-map.json")
    monkeypatch.setattr(gate, "FRESHNESS_OUTPUT", tmp_path / "freshness.json")
    # The oracle-backed guard reads the real registry against this stand-in
    # data dir; it is covered in test_vacuous_gate.py.
    monkeypatch.setattr(gate, "check_oracle_backed", lambda: [])
    gate._write_freshness(gate.build_freshness())
    monkeypatch.setattr("sys.argv", ["check_vacuous_gate.py", "--check"])

    assert gate.main() == 0

    out = capsys.readouterr().out
    assert "1 suite(s) from dirty rulespec trees" in out
    assert "::warning::rw-vat report ran on dirty rulespec trees: o/rulespec-rw" in out


# --- submodules -------------------------------------------------------------


def _superproject(tmp_path: Path) -> tuple[Path, Path]:
    module = _repo(tmp_path / "module", {"m.yaml": "m: 1\n"})
    (module / "m.yaml").write_text("m: 2\n")
    _git(module, "commit", "-qam", "second")
    parent = _repo(tmp_path / "rulespec-rw")
    _git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(module), "vendor/module")
    _git(parent, "commit", "-qm", "add submodule")
    return parent, parent / "vendor" / "module"


def test_a_submodule_moved_off_its_recorded_commit_is_dirty(tmp_path):
    parent, sub = _superproject(tmp_path)
    assert worktree_state(parent) == {"dirty": False}
    _git(sub, "checkout", "-q", "HEAD~1")
    state = worktree_state(parent)
    assert state["dirty"] is True
    assert _is_hex64(state["diff_sha256"])


def test_untracked_content_inside_a_submodule_leaves_the_tree_clean(tmp_path):
    parent, sub = _superproject(tmp_path)
    (sub / "build-output.json").write_text("{}")
    assert worktree_state(parent) == {"dirty": False}
    (sub / "m.yaml").write_text("m: 3\n")  # modified content does count
    assert worktree_state(parent)["dirty"] is True


# --- verified upstream pins --------------------------------------------------


def _pinned_config(runner_type: str, root: Path, params: dict) -> dict:
    return {
        "name": "pinned-suite",
        "runner": {
            "type": runner_type,
            "parameters": {"rulespec_root": str(root), **params},
        },
    }


def test_a_pin_read_from_git_objects_records_the_pin_as_clean(run_comparison, tmp_path):
    """The DE producer reads its pinned commit from the object database, so
    the checkout's working tree, dirty against its own HEAD, fed nothing:
    the entry names the pin, and the pin's committed content is what ran."""
    root = _repo(tmp_path / "rulespec-de", {"de/kindergeld.yaml": "amount: 255\n"})
    (root / "de/kindergeld.yaml").write_text("amount: 999\n")
    assert worktree_state(root)["dirty"] is True
    pin = "1" * 40
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "pinned-suite"}))
    config = _pinned_config(
        "de-axiom-oracle-compare",
        root,
        {
            "oracle": "euromod",
            run_comparison._VERIFIED_RULESPEC_UPSTREAM_SHA: pin,
            run_comparison._VERIFIED_RULESPEC_UPSTREAM_TREE: "2" * 40,
        },
    )

    block = run_comparison._build_run_provenance(config, "de-axiom-oracle-compare", output)

    assert block["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-de", "sha": pin, "dirty": False,
            "sha_toplevel": str(root.resolve()), "worktree_toplevel": str(root.resolve()),
        }
    ]


def test_a_snapshot_pin_keeps_the_snapshots_measured_state(run_comparison, tmp_path):
    """The federal path verified a checkout whose tree is the pin's, so the
    state measured on that checkout describes the pin; an edit made after
    verification shows as dirty and is refused for non-manual runs."""
    root = _repo(tmp_path / "rulespec-us")
    verified_tree = _git(root, "rev-parse", "HEAD^{tree}").strip()
    (root / "rw/vat.yaml").write_text("rate: 0.17\n")
    pin = "3" * 40
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "pinned-suite"}))
    config = _pinned_config(
        "federal-tax-liability-grid",
        root,
        {
            run_comparison._VERIFIED_RULESPEC_UPSTREAM_SHA: pin,
            run_comparison._VERIFIED_RULESPEC_WORKTREE_TREE: verified_tree,
        },
    )

    block = run_comparison._build_run_provenance(config, "federal-tax-liability-grid", output)

    [entry] = block["rulespecs"]
    assert entry["sha"] == pin
    assert entry["dirty"] is True
    with pytest.raises(SystemExit):
        run_comparison._guard_unclean_rulespec_trees("pinned-suite", {**block, "run_kind": "weekly"})


def test_a_pinned_federal_run_records_only_the_snapshot_that_ran(
    run_comparison, tmp_path, monkeypatch
):
    """With several configured roots, the pinned federal runner keeps only
    the one holding the pin. Provenance must record exactly that checkout:
    a set-aside or missing root would otherwise carry the pin's SHA with no
    worktree state, and a non-manual run would be refused for a tree that
    never ran."""
    snapshot = _repo(tmp_path / "pins" / "rulespec-us")
    tree = _git(snapshot, "rev-parse", "HEAD^{tree}").strip()
    pin = "4" * 40
    params = {
        "policy": "aca_ptc",
        "rulespec_roots": [str(tmp_path / "missing" / "rulespec-us"), str(snapshot)],
        "rulespec_upstream_sha": pin,
        "rulespec_upstream_tree": tree,
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
    }
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "uv":  # the generator; the git checks run for real
            return subprocess.CompletedProcess(cmd, 0)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)
    config = {"name": "fed-pinned", "runner": {"type": "federal-tax-liability-grid", "parameters": params}}
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "fed-pinned"}))

    run_comparison._run_federal_tax_liability_grid(config["runner"], output)
    block = run_comparison._build_run_provenance(config, "federal-tax-liability-grid", output)

    assert params["rulespec_roots"] == [str(snapshot.resolve())]
    assert block["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-us", "sha": pin, "dirty": False,
            "sha_toplevel": str(snapshot.resolve()), "worktree_toplevel": str(snapshot.resolve()),
        }
    ]
    run_comparison._guard_unclean_rulespec_trees(
        "fed-pinned", {**block, "run_kind": "affected-rerun"}
    )
