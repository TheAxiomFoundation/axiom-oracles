"""Exercise data publication against tiny local remotes, without network calls."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "oracle_data.py"
spec = importlib.util.spec_from_file_location("oracle_data", SCRIPT)
data = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(data)

REPORT = "dashboard/public/data/report.json"
KPI = "dashboard/public/data/rule_verification.json"
KPI_SUMMARY = "dashboard/public/data/rule_verification_summary.json"
RATCHET = "conformance/ratchet.yaml"


def git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit(root: Path, changes: dict[str, str | None]) -> str:
    for name, content in changes.items():
        path = root / name
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    git(root, "add", "-A")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
        "commit", "-m", "fixture update")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # Never inherit developer signing, identity, global hooks or configuration.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    seed, origin, checkout = (tmp_path / p for p in ("seed", "origin.git", "checkout"))
    seed.mkdir()
    git(seed, "init", "--initial-branch=main")
    main = commit(seed, {
        "source.py": "original source\n",
        REPORT: "original data\n",
        KPI: "original kpi\n",
        KPI_SUMMARY: "original summary\n",
        RATCHET: "human baseline\n",
    })
    git(tmp_path, "init", "--bare", str(origin))
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "origin", "HEAD:refs/heads/main")
    git(tmp_path, "clone", "--branch", "main", str(origin), str(checkout))
    return SimpleNamespace(seed=seed, origin=origin, checkout=checkout, main=main)


def seed_data(repo, changes):
    git(repo.seed, "checkout", "-B", "oracle-data", repo.main)
    tip = commit(repo.seed, changes)
    git(repo.seed, "push", "origin", "HEAD:refs/heads/oracle-data")
    git(repo.seed, "checkout", "main")
    return tip


def advance_main(repo, changes):
    git(repo.seed, "checkout", "main")
    tip = commit(repo.seed, changes)
    git(repo.seed, "push", "origin", "HEAD:refs/heads/main")
    return tip


def advance_data(repo, changes):
    git(repo.seed, "checkout", "oracle-data")
    tip = commit(repo.seed, changes)
    git(repo.seed, "push", "origin", "HEAD:refs/heads/oracle-data")
    git(repo.seed, "checkout", "main")
    return tip


def remote_main(repo):
    return git(repo.origin, "rev-parse", "refs/heads/main")


def test_prepare_bootstraps_missing_data_branch_without_moving_main(repo):
    baseline = data.prepare(repo.checkout)
    assert baseline == repo.main
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert git(repo.checkout, "symbolic-ref", "-q", "HEAD", check=False) == ""
    assert remote_main(repo) == repo.main
    assert git(repo.origin, "show-ref", "--verify", data.DATA_REF, check=False) == ""


def test_prepare_reuses_data_tip_when_source_has_not_moved(repo):
    tip = seed_data(repo, {REPORT: "published data\n"})
    baseline = data.prepare(repo.checkout)
    assert baseline == tip
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert remote_main(repo) == repo.main


def test_prepare_merges_current_main_source_and_human_data_edits(repo):
    tip = seed_data(repo, {REPORT: "published data\n"})
    main = advance_main(repo, {"source.py": "current source\n", RATCHET: "human revision\n"})
    baseline = data.prepare(repo.checkout)
    assert git(repo.checkout, "show", "-s", "--format=%P", baseline).split() == [main, tip]
    assert (repo.checkout / "source.py").read_text() == "current source\n"
    assert (repo.checkout / RATCHET).read_text() == "human revision\n"
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert remote_main(repo) == main


def test_prepare_fetches_latest_main_on_each_attempt(repo):
    seed_data(repo, {REPORT: "published data\n"})
    data.prepare(repo.checkout)
    latest = advance_main(repo, {"source.py": "new main source\n"})
    baseline = data.prepare(repo.checkout)
    assert (repo.checkout / "source.py").read_text() == "new main source\n"
    assert data._ancestor(repo.checkout, latest, baseline)
    assert remote_main(repo) == latest


def test_prepare_conflict_leaves_worktree_and_head_unchanged(repo):
    seed_data(repo, {REPORT: "bot revision\n"})
    advance_main(repo, {REPORT: "human revision\n"})
    (repo.checkout / "source.py").write_text("local changes\n")
    status = git(repo.checkout, "status", "--porcelain")
    with pytest.raises(data.DataError, match="merge failed"):
        data.prepare(repo.checkout)
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert git(repo.checkout, "status", "--porcelain") == status
    assert (repo.checkout / "source.py").read_text() == "local changes\n"


def test_materialize_missing_branch_preserves_checkout(repo):
    assert data.materialize(repo.checkout) == []
    assert git(repo.checkout, "status", "--porcelain") == ""
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


def test_materialize_updates_only_data_and_preserves_index_source_and_head(repo):
    seed_data(repo, {REPORT: "published data\n", "source.py": "data branch source\n"})
    (repo.checkout / "source.py").write_text("local source edit\n")
    git(repo.checkout, "add", "source.py")
    before_index = git(repo.checkout, "write-tree")
    assert data.materialize(repo.checkout) == [REPORT]
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert (repo.checkout / "source.py").read_text() == "local source edit\n"
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert remote_main(repo) == repo.main


def test_materialize_does_not_replace_human_main_changes_in_broad_scope(repo):
    seed_data(repo, {REPORT: "published data\n"})
    main = advance_main(repo, {RATCHET: "human revision\n"})
    git(repo.checkout, "fetch", "origin", data.MAIN_REF)
    git(repo.checkout, "reset", "--hard", "FETCH_HEAD")
    assert data.materialize(repo.checkout) == [REPORT]
    assert (repo.checkout / RATCHET).read_text() == "human revision\n"
    assert git(repo.checkout, "rev-parse", "HEAD") == main


def test_materialize_handles_new_paths_and_deletions_without_staging(repo):
    new = "dashboard/public/data/new.json"
    seed_data(repo, {REPORT: None, new: "new report\n"})
    assert set(data.materialize(repo.checkout)) == {REPORT, new}
    assert not (repo.checkout / REPORT).exists()
    assert (repo.checkout / new).read_text() == "new report\n"
    assert git(repo.checkout, "diff", "--cached", "--name-only") == ""


def test_materialize_conflict_leaves_checkout_unchanged(repo):
    seed_data(repo, {REPORT: "published data\n"})
    commit(repo.checkout, {REPORT: "human report edit\n"})
    before_head = git(repo.checkout, "rev-parse", "HEAD")
    with pytest.raises(data.DataError, match="merge failed"):
        data.materialize(repo.checkout)
    assert git(repo.checkout, "rev-parse", "HEAD") == before_head
    assert (repo.checkout / REPORT).read_text() == "human report edit\n"
    assert git(repo.checkout, "status", "--porcelain") == ""


def test_materialize_ignores_committed_source_only_conflict(repo):
    seed_data(repo, {REPORT: "published data\n", "source.py": "new upstream source\n"})
    source = commit(repo.checkout, {"source.py": "feature source\n"})
    before_index = git(repo.checkout, "write-tree")
    assert data.materialize(repo.checkout) == [REPORT]
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert (repo.checkout / "source.py").read_text() == "feature source\n"
    assert git(repo.checkout, "rev-parse", "HEAD") == source
    assert git(repo.checkout, "write-tree") == before_index


@pytest.mark.parametrize("edit", ["modified", "deleted", "mode"])
def test_materialize_refuses_uncommitted_data_edits(repo, edit):
    seed_data(repo, {REPORT: "published data\n"})
    path = repo.checkout / REPORT
    if edit == "modified":
        path.write_text("local generated data\n")
    elif edit == "deleted":
        path.unlink()
    else:
        path.chmod(0o755)
    status = git(repo.checkout, "status", "--porcelain")
    with pytest.raises(data.DataError, match="local data edits"):
        data.materialize(repo.checkout)
    assert git(repo.checkout, "status", "--porcelain") == status
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    if edit == "modified":
        assert path.read_text() == "local generated data\n"
    elif edit == "deleted":
        assert not path.exists()
    else:
        assert path.stat().st_mode & 0o111


def test_materialize_refuses_staged_data_even_when_matching_remote(repo):
    seed_data(repo, {REPORT: "published data\n"})
    (repo.checkout / REPORT).write_text("published data\n")
    git(repo.checkout, "add", REPORT)
    before_index = git(repo.checkout, "write-tree")
    with pytest.raises(data.DataError, match="staged data"):
        data.materialize(repo.checkout)
    assert git(repo.checkout, "write-tree") == before_index
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


def test_materialize_refuses_untracked_data_collision_before_any_restore(repo):
    new = "dashboard/public/data/new.json"
    seed_data(repo, {REPORT: "published data\n", new: "published addition\n"})
    (repo.checkout / new).write_text("local generated addition\n")
    with pytest.raises(data.DataError, match="local data edits"):
        data.materialize(repo.checkout)
    assert (repo.checkout / new).read_text() == "local generated addition\n"
    assert (repo.checkout / REPORT).read_text() == "original data\n"
    assert git(repo.checkout, "diff", "--cached", "--name-only") == ""


def test_materialize_accepts_matching_target_and_remembers_it_for_next_update(repo):
    seed_data(repo, {REPORT: "published data\n"})
    (repo.checkout / REPORT).write_text("published data\n")
    assert data.materialize(repo.checkout) == [REPORT]
    assert data.materialize(repo.checkout) == [REPORT]
    state = json.loads(data._state_path(repo.checkout).read_text())
    assert state[REPORT]["oid"] == git(repo.checkout, "hash-object", REPORT)
    assert state[REPORT]["mode"] == "100644"
    advance_data(repo, {REPORT: "new published data\n"})
    assert data.materialize(repo.checkout) == [REPORT]
    assert (repo.checkout / REPORT).read_text() == "new published data\n"
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


def test_materialize_refuses_edits_to_previously_materialized_data(repo):
    seed_data(repo, {REPORT: "published data\n"})
    data.materialize(repo.checkout)
    (repo.checkout / REPORT).write_text("new local generated data\n")
    advance_data(repo, {REPORT: "new published data\n"})
    with pytest.raises(data.DataError, match="local data edits"):
        data.materialize(repo.checkout)
    assert (repo.checkout / REPORT).read_text() == "new local generated data\n"


def test_materialize_reverts_prior_materialized_data_to_head(repo):
    seed_data(repo, {REPORT: "published data\n"})
    data.materialize(repo.checkout)
    advance_data(repo, {REPORT: "original data\n"})
    assert data.materialize(repo.checkout) == [REPORT]
    assert (repo.checkout / REPORT).read_text() == "original data\n"
    assert git(repo.checkout, "status", "--porcelain") == ""


def test_materialize_deletes_a_previously_materialized_untracked_addition(repo):
    new = "dashboard/public/data/new.json"
    seed_data(repo, {new: "published addition\n"})
    data.materialize(repo.checkout)
    assert (repo.checkout / new).exists()
    assert git(repo.checkout, "ls-files", new) == ""
    advance_data(repo, {new: None})
    assert data.materialize(repo.checkout) == [new]
    assert not (repo.checkout / new).exists()
    assert git(repo.checkout, "status", "--porcelain") == ""


def test_materialization_metadata_is_local_to_each_worktree(repo):
    seed_data(repo, {REPORT: "published data\n"})
    second = repo.checkout.parent / "second-worktree"
    git(repo.checkout, "worktree", "add", "--detach", str(second), repo.main)
    data.materialize(repo.checkout)
    assert data._state_path(repo.checkout).is_file()
    assert not data._state_path(second).exists()
    data.materialize(second)
    assert data._state_path(second).is_file()
    assert data._state_path(second) != data._state_path(repo.checkout)
    assert (second / REPORT).read_text() == "published data\n"


def test_materialize_baseline_keeps_current_source_and_pins_published_data(repo):
    # New main source has reached the data branch, but this reader is still on
    # an older source commit. A baseline must not silently replace that source.
    latest = advance_main(repo, {"source.py": "newer source\n"})
    git(repo.seed, "checkout", "-B", "oracle-data", latest)
    tip = commit(repo.seed, {REPORT: "published data\n"})
    git(repo.seed, "push", "origin", "HEAD:refs/heads/oracle-data")
    assert data.materialize(repo.checkout, baseline=True) == [REPORT]
    assert (repo.checkout / "source.py").read_text() == "original source\n"
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert git(repo.checkout, "status", "--porcelain") == ""
    parents = git(repo.checkout, "show", "-s", "--format=%P", "HEAD").split()
    assert parents == [repo.main, tip]
    assert remote_main(repo) == latest


def test_materialize_fetches_new_data_after_previous_read(repo):
    seed_data(repo, {REPORT: "first data\n"})
    data.materialize(repo.checkout)
    advance_data(repo, {REPORT: "second data\n"})
    data.materialize(repo.checkout)
    assert (repo.checkout / REPORT).read_text() == "second data\n"
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


def test_materialize_cli_from_dashboard_uses_repository_relative_paths(repo):
    seed_data(repo, {REPORT: "published data\n"})
    before_index = git(repo.checkout, "write-tree")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "materialize"],
        cwd=repo.checkout / "dashboard", capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (repo.checkout / REPORT).read_text() == "published data\n"
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert not (repo.checkout / "dashboard/dashboard").exists()


@pytest.mark.parametrize("command", [data.prepare, data.materialize])
def test_unavailable_remote_fails_instead_of_claiming_branch_absent(repo, command):
    git(repo.checkout, "remote", "set-url", "origin", str(repo.origin / "missing"))
    with pytest.raises(data.DataError, match="cannot read origin"):
        command(repo.checkout)
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert git(repo.checkout, "status", "--porcelain") == ""


def test_checkout_optout_avoids_network_but_does_not_disable_prepare(repo, monkeypatch):
    monkeypatch.setenv("AXIOM_ORACLES_DATA_SOURCE", "checkout")
    git(repo.checkout, "remote", "set-url", "origin", str(repo.origin / "missing"))
    assert data.materialize(repo.checkout) == []
    with pytest.raises(data.DataError, match="cannot read origin"):
        data.prepare(repo.checkout)


def test_publish_bootstraps_data_branch_and_leaves_main_unchanged(repo):
    data.prepare(repo.checkout)
    (repo.checkout / KPI).write_text("refreshed kpi\n")
    assert data.publish(repo.checkout, group="kpi", message="data: refresh KPI")
    published = git(repo.origin, "rev-parse", data.DATA_REF)
    assert git(repo.origin, "show", f"{published}:{KPI}") == "refreshed kpi"
    assert git(repo.origin, "show", f"{published}:{REPORT}") == "original data"
    assert remote_main(repo) == repo.main


def test_publish_noop_makes_no_commit_or_branch(repo):
    data.prepare(repo.checkout)
    assert not data.publish(repo.checkout, group="kpi", message="data: refresh KPI")
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert git(repo.origin, "show-ref", "--verify", data.DATA_REF, check=False) == ""
    assert remote_main(repo) == repo.main


def test_publish_scope_preserves_unstaged_source_edits(repo):
    tip = seed_data(repo, {REPORT: "first data\n"})
    data.prepare(repo.checkout)
    (repo.checkout / REPORT).write_text("refreshed data\n")
    (repo.checkout / "source.py").write_text("local source edit\n")
    assert data.publish(repo.checkout, group="dashboard", message="data: refresh report")
    published = git(repo.origin, "rev-parse", data.DATA_REF)
    assert git(repo.origin, "diff", "--name-only", tip, published) == REPORT
    assert (repo.checkout / "source.py").read_text() == "local source edit\n"
    assert remote_main(repo) == repo.main


def test_publish_rejects_staged_files_outside_scope_without_changing_index(repo):
    data.prepare(repo.checkout)
    (repo.checkout / "source.py").write_text("staged source\n")
    git(repo.checkout, "add", "source.py")
    (repo.checkout / KPI).write_text("refreshed kpi\n")
    before_index = git(repo.checkout, "write-tree")
    with pytest.raises(data.DataError, match="outside the publication group"):
        data.publish(repo.checkout, group="kpi", message="data: refresh KPI")
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert remote_main(repo) == repo.main


@pytest.mark.parametrize("branch", ["main", "oracle-data"])
def test_publish_rejects_advanced_source_or_data_before_staging(repo, branch):
    seed_data(repo, {REPORT: "first data\n"})
    baseline = data.prepare(repo.checkout)
    (repo.checkout / KPI).write_text("refreshed kpi\n")
    if branch == "main":
        advance_main(repo, {"source.py": "new source\n"})
    else:
        advance_data(repo, {REPORT: "concurrent data\n"})
    before_main = remote_main(repo)
    with pytest.raises(data.DataError, match="advanced"):
        data.publish(repo.checkout, group="kpi", message="data: refresh KPI")
    assert git(repo.checkout, "rev-parse", "HEAD") == baseline
    assert git(repo.checkout, "diff", "--cached", "--name-only") == ""
    assert remote_main(repo) == before_main


def test_publish_accepts_prepared_local_data_branch(repo):
    data.prepare(repo.checkout)
    git(repo.checkout, "switch", "-C", data.DATA_BRANCH)
    (repo.checkout / REPORT).write_text("refreshed data\n")
    assert data.publish(repo.checkout, group="dashboard", message="data: refresh report")
    assert git(repo.checkout, "symbolic-ref", "HEAD") == data.DATA_REF
    assert git(repo.origin, "show", f"{data.DATA_REF}:{REPORT}") == "refreshed data"
    assert remote_main(repo) == repo.main


@pytest.mark.parametrize("branch", ["main", "master", "review"])
def test_publish_refuses_other_attached_checkout(repo, branch):
    git(repo.checkout, "switch", "-C", branch)
    (repo.checkout / KPI).write_text("refreshed kpi\n")
    with pytest.raises(data.DataError, match="detached baseline"):
        data.publish(repo.checkout, group="kpi", message="data: refresh KPI")
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert git(repo.checkout, "diff", "--cached", "--name-only") == ""
    assert remote_main(repo) == repo.main


@pytest.mark.parametrize("args", [
    ["prepare", "main"],
    ["publish", "--group", "dashboard", "--message", "refresh", "--target", "main"],
])
def test_cli_rejects_arbitrary_publish_target(repo, args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=repo.checkout,
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert remote_main(repo) == repo.main


@pytest.mark.parametrize("parent", ["dashboard", "dashboard/public", "dashboard/public/data"])
@pytest.mark.parametrize("operation", ["replace", "delete"])
@pytest.mark.parametrize("baseline", [False, True], ids=["ordinary", "baseline"])
def test_materialize_rejects_every_parent_symlink_before_any_restore(repo, parent, operation, baseline):
    earlier = "closure/de/summary.json"
    seed_data(repo, {
        earlier: "published closure\n",
        REPORT: None if operation == "delete" else "published replacement\n",
    })
    outside = repo.checkout.parent / "external-directory"
    shutil.move(str(repo.checkout / parent), outside)
    (repo.checkout / parent).symlink_to(outside, target_is_directory=True)
    external_report = outside / Path(REPORT).relative_to(parent)
    before_index = git(repo.checkout, "write-tree")

    with pytest.raises(data.DataError):
        data.materialize(repo.checkout, baseline=baseline)

    assert external_report.read_text() == "original data\n"
    assert (repo.checkout / parent).is_symlink()
    assert not (repo.checkout / earlier).exists(), "a path was restored before parent validation"
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


def test_materialize_rejects_final_file_symlink_even_with_matching_target_bytes(repo):
    seed_data(repo, {REPORT: None, "closure/de/summary.json": "published closure\n"})
    external_report = repo.checkout.parent / "external-report.json"
    external_report.write_text("original data\n")
    (repo.checkout / REPORT).unlink()
    (repo.checkout / REPORT).symlink_to(external_report)

    with pytest.raises(data.DataError, match="local data edits"):
        data.materialize(repo.checkout)

    assert (repo.checkout / REPORT).is_symlink()
    assert external_report.read_text() == "original data\n"
    assert not (repo.checkout / "closure/de/summary.json").exists()


@pytest.mark.parametrize("changed", [False, True], ids=["identical", "similarity-detected"])
def test_materialize_removes_old_path_for_report_rename(repo, changed):
    original = "".join(f'"row-{i}": "original report value",\n' for i in range(30))
    repo.main = advance_main(repo, {REPORT: original})
    git(repo.checkout, "fetch", "origin", data.MAIN_REF)
    git(repo.checkout, "reset", "--hard", "FETCH_HEAD")
    renamed = "dashboard/public/data/renamed.json"
    git(repo.seed, "checkout", "-B", "oracle-data", repo.main)
    git(repo.seed, "mv", REPORT, renamed)
    expected = original.replace("row-29", "changed-row-29") if changed else original
    tip = commit(repo.seed, {renamed: expected})
    # Verify the fixture exercises Git's rename detection instead of an ordinary
    # addition/deletion; the reader must account for both sides of this record.
    assert git(repo.seed, "diff", "--name-status", "-M", repo.main, tip).startswith("R")
    git(repo.seed, "push", "origin", "HEAD:refs/heads/oracle-data")
    git(repo.seed, "checkout", "main")
    before_index = git(repo.checkout, "write-tree")

    assert set(data.materialize(repo.checkout)) == {REPORT, renamed}

    assert (repo.checkout / renamed).read_text() == expected
    assert not (repo.checkout / REPORT).exists(), "old report survived its published rename"
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


@pytest.mark.parametrize("authored", [
    "conformance/README.md",
    "conformance/executable/de-kindergeld-manifest.json",
    "conformance/ratchet.yaml",
    "comparisons/de-worker-dual-oracle/output-dependencies.json",
])
@pytest.mark.parametrize("baseline", [False, True], ids=["ordinary", "baseline"])
@pytest.mark.parametrize("feature_edit", [False, True], ids=["old-source", "feature-conflict"])
def test_reader_excludes_authored_conformance_inputs(repo, authored, baseline, feature_edit):
    repo.main = advance_main(repo, {authored: "initial authored input\n"})
    git(repo.checkout, "fetch", "origin", data.MAIN_REF)
    git(repo.checkout, "reset", "--hard", "FETCH_HEAD")
    seed_data(repo, {REPORT: "first published data\n"})
    advance_main(repo, {
        authored: "new reviewed authored input\n",
        "source.py": "new reviewed source\n",
    })
    data.prepare(repo.seed)
    commit(repo.seed, {REPORT: "latest published data\n"})
    git(repo.seed, "push", "origin", "HEAD:refs/heads/oracle-data")
    git(repo.seed, "checkout", "main")
    expected = "feature authored input\n" if feature_edit else "initial authored input\n"
    if feature_edit:
        commit(repo.checkout, {authored: expected})
    source = git(repo.checkout, "rev-parse", "HEAD")
    before_index = git(repo.checkout, "write-tree")

    assert data.materialize(repo.checkout, baseline=baseline) == [REPORT]

    assert (repo.checkout / REPORT).read_text() == "latest published data\n"
    assert (repo.checkout / authored).read_text() == expected
    assert git(repo.checkout, "show", f":{authored}") == expected.strip()
    assert (repo.checkout / "source.py").read_text() == "original source\n"
    assert git(repo.checkout, "show", "HEAD:source.py") == "original source"
    if baseline:
        assert git(repo.checkout, "status", "--porcelain") == ""
        assert git(repo.checkout, "show", f"HEAD:{authored}") == expected.strip()
    else:
        assert git(repo.checkout, "rev-parse", "HEAD") == source
        assert git(repo.checkout, "write-tree") == before_index


@pytest.mark.parametrize("baseline", [False, True], ids=["ordinary", "baseline"])
def test_reader_still_materializes_generated_conformance_artifacts(repo, baseline):
    paths = [
        "conformance/scoreboard.json",
        "conformance/detail/de.json",
        "conformance/history/de/2026-10-14.json",
        "conformance/exercise-census.json",
        "conformance/de-certificate-census.json",
        "conformance/executable/de-kindergeld-status.json",
        "conformance/executable/nz-treasury-incomeexplorer.json",
    ]
    seed_data(repo, {path: f"published generated artifact {i}\n" for i, path in enumerate(paths)})
    before_index = git(repo.checkout, "write-tree")

    assert set(data.materialize(repo.checkout, baseline=baseline)) == set(paths)

    for i, path in enumerate(paths):
        assert (repo.checkout / path).read_text() == f"published generated artifact {i}\n"
    assert (repo.checkout / RATCHET).read_text() == "human baseline\n"
    assert (repo.checkout / "source.py").read_text() == "original source\n"
    if baseline:
        assert git(repo.checkout, "status", "--porcelain") == ""
    else:
        assert git(repo.checkout, "write-tree") == before_index
        assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


@pytest.mark.parametrize("baseline", [False, True], ids=["ordinary", "baseline"])
def test_missing_branch_after_materialization_restores_head_and_removes_additions(repo, baseline):
    new = "dashboard/public/data/new.json"
    seed_data(repo, {REPORT: "previously published data\n", KPI: None, new: "published addition\n"})
    data.materialize(repo.checkout)
    git(repo.seed, "push", "origin", ":refs/heads/oracle-data")
    before_index = git(repo.checkout, "write-tree")

    assert set(data.materialize(repo.checkout, baseline=baseline)) == {REPORT, KPI, new}

    assert (repo.checkout / REPORT).read_text() == "original data\n"
    assert (repo.checkout / KPI).read_text() == "original kpi\n"
    assert not (repo.checkout / new).exists()
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main
    assert git(repo.checkout, "status", "--porcelain") == ""
    assert data.materialize(repo.checkout, baseline=baseline) == []


@pytest.mark.parametrize("staged", [False, True], ids=["local-edit", "staged-edit"])
def test_missing_branch_recovery_refuses_local_edits_before_restoring_any_path(repo, staged):
    new = "dashboard/public/data/new.json"
    seed_data(repo, {REPORT: "previously published data\n", KPI: None, new: "published addition\n"})
    data.materialize(repo.checkout)
    git(repo.seed, "push", "origin", ":refs/heads/oracle-data")
    (repo.checkout / REPORT).write_text("local generated data\n")
    if staged:
        git(repo.checkout, "add", REPORT)
    before_index = git(repo.checkout, "write-tree")
    before_status = git(repo.checkout, "status", "--porcelain")

    with pytest.raises(data.DataError, match="staged data" if staged else "local data edits"):
        data.materialize(repo.checkout)

    assert (repo.checkout / REPORT).read_text() == "local generated data\n"
    assert not (repo.checkout / KPI).exists()
    assert (repo.checkout / new).read_text() == "published addition\n"
    assert git(repo.checkout, "write-tree") == before_index
    assert git(repo.checkout, "status", "--porcelain") == before_status
    assert git(repo.checkout, "rev-parse", "HEAD") == repo.main


def test_late_push_rejection_keeps_generated_edits_visible_to_unattended_guard(repo, monkeypatch):
    seed_data(repo, {REPORT: "first published data\n"})
    baseline = data.prepare(repo.checkout)
    git(repo.checkout, "switch", "-C", data.DATA_BRANCH)
    (repo.checkout / KPI).write_text("new generated kpi\n")
    (repo.checkout / "source.py").write_text("local source edit\n")
    original_git = data._git
    raced = False

    def git_with_race(root, *args, **kwargs):
        nonlocal raced
        if args and args[0] == "push" and not raced:
            raced = True
            advance_data(repo, {REPORT: "concurrent published data\n"})
        return original_git(root, *args, **kwargs)

    monkeypatch.setattr(data, "_git", git_with_race)
    with pytest.raises(data.DataError, match="git push failed"):
        data.publish(repo.checkout, group="kpi", message="data: late contention probe")

    assert raced
    assert git(repo.checkout, "rev-parse", "HEAD") == baseline
    assert (repo.checkout / KPI).read_text() == "new generated kpi\n"
    assert (repo.checkout / "source.py").read_text() == "local source edit\n"
    assert git(repo.checkout, "diff", "--cached", "--name-only") == KPI
    assert git(repo.checkout, "show", f":{KPI}") == "new generated kpi"
    assert git(repo.origin, "show", f"{data.DATA_REF}:{KPI}") == "original kpi"
    assert remote_main(repo) == repo.main

    # Run the actual unattended preflight against the retained generated edit.
    # Remove the unrelated source edit so only the failed publication stops it.
    (repo.checkout / "source.py").write_text("original source\n")
    regen = repo.checkout / "scripts/regenerate_all.sh"
    regen.parent.mkdir()
    regen.write_text((SCRIPT.parent / "regenerate_all.sh").read_text())
    result = subprocess.run(["sh", str(regen)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "refusing unattended regen with local tracked changes" in result.stdout
