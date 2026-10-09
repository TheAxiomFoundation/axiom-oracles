"""A rulespec SHA and its working-tree attestation name one checkout.

The inherited-GIT_DIR publication regression reuses the independent review's
Git-object-verified consumer probe: only the external engine is replaced;
registry loading, affected-map completion, the weekly gate and publication
run through production code. The property also checks that provenance's Git
processes receive an explicit repository and no inherited repository locator.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from axiom_oracles import provenance
from scripts import de_axiom_legs


# Deliberately independent of production's sanitization list: omitting a
# required variable there must not silently omit it from the regression.
_REPOSITORY_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)
_GIT_IDENTITY = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "repository-provenance-test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "repository-provenance-test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
_SLUG = "TheAxiomFoundation/rulespec-us"


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch):
    for key in (*_REPOSITORY_ENV, "GIT_NAMESPACE", "GIT_PREFIX"):
        monkeypatch.delenv(key, raising=False)
    for key, value in _GIT_IDENTITY.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def run_comparison():
    source = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("repository_run_comparison", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in (*_REPOSITORY_ENV, "GIT_NAMESPACE", "GIT_PREFIX")
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**env, **_GIT_IDENTITY},
    ).stdout


def _repo(path: Path, body: str = "rate: 0.18\n") -> Path:
    path.mkdir(parents=True)
    (path / "rule.yaml").write_text(body)
    for args in (("init", "-q"), ("add", "rule.yaml"), ("commit", "-q", "-m", "seed")):
        _git(path, *args)
    return path.resolve()


def _head(path: Path) -> str:
    return _git(path, "rev-parse", "HEAD").strip()


def _foreign_env(actual: Path, foreign: Path) -> dict[str, str]:
    return {
        "GIT_DIR": str(foreign / ".git"),
        "GIT_WORK_TREE": str(foreign),
        "GIT_INDEX_FILE": str(foreign / ".git" / "index"),
        "GIT_COMMON_DIR": str(foreign / ".git"),
        "GIT_OBJECT_DIRECTORY": str(foreign / ".git" / "objects"),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(foreign / ".git" / "objects"),
        "GIT_CEILING_DIRECTORIES": str(actual.parent),
    }


def _registry(path: Path, run_comparison, monkeypatch, suite: str = "co-snap-ecps") -> Path:
    path.mkdir()
    (path / f"{suite}.yaml").write_text(
        f"name: {suite}\n"
        "runner:\n"
        "  type: axiom-encode-snap-ecps-compare\n"
        "  parameters: {}\n"
        "artifacts:\n"
        "  report_basename: env-probe\n"
    )
    (path / "affected_map.json").write_text(
        json.dumps({"suites": [{"suite": suite, "name": None, "repos": [_SLUG]}]})
    )
    monkeypatch.setattr(run_comparison, "COMPARISONS_DIR", path)
    return path


def test_weekly_publication_ignores_inherited_git_dir(
    run_comparison, tmp_path, monkeypatch
):
    actual = _repo(tmp_path / "rulespec-us", "rate: 0.18\n")
    hook_repo = _repo(tmp_path / "hook-repo", "rate: 0.17\n")
    actual_sha, hook_sha = _head(actual), _head(hook_repo)
    assert actual_sha != hook_sha
    assert _git(actual, "show", f"{actual_sha}:rule.yaml") == "rate: 0.18\n"
    assert _git(hook_repo, "show", f"{hook_sha}:rule.yaml") == "rate: 0.17\n"
    _registry(tmp_path / "comparisons", run_comparison, monkeypatch)

    def file_runner(_runner, output):
        rate = float((actual / "rule.yaml").read_text().split(":")[1])
        output.write_text(json.dumps({
            "compared_values": 1, "mismatch_count": 0, "executed_rate": rate,
        }))

    monkeypatch.setitem(
        run_comparison.RUNNERS, "axiom-encode-snap-ecps-compare", file_runner
    )
    monkeypatch.setenv("GIT_DIR", str(hook_repo / ".git"))
    monkeypatch.setenv("AXIOM_RULESPEC_US_ROOT", str(actual))
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "weekly")
    output_dir = tmp_path / "reports"
    monkeypatch.setattr("sys.argv", [
        "run_comparison.py", "co-snap-ecps", "--output-dir", str(output_dir),
    ])

    assert run_comparison.main() == 0

    [report_path] = output_dir.glob("*.json")
    report = json.loads(report_path.read_text())
    [entry] = report["provenance"]["rulespecs"]
    assert report["executed_rate"] == 0.18
    assert entry["sha"] == actual_sha  # fails at reviewed ce154cc3a
    assert entry["dirty"] is False
    assert entry["sha_toplevel"] == entry["worktree_toplevel"] == str(actual)


def test_tax_clone_marker_ignores_inherited_git_dir(
    run_comparison, tmp_path, monkeypatch
):
    clone = _repo(tmp_path / "workspace" / "rulespec-us")
    hook_repo = _repo(tmp_path / "hook-repo", "rate: 0.17\n")
    actual_sha = _head(clone)
    assert actual_sha != _head(hook_repo)
    assert _git(clone, "show", f"{actual_sha}:rule.yaml") == "rate: 0.18\n"
    _registry(tmp_path / "comparisons", run_comparison, monkeypatch, "fiit-ecps")
    for name in ("axiom-encode", "axiom-rules-engine"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(run_comparison, "_ensure_engine_binary", lambda *_a, **_k: None)
    monkeypatch.setattr(run_comparison, "_ensure_rulespec_us_checkout", lambda _r: clone)
    real_run = subprocess.run
    expected = {}

    def external_runner(cmd, *args, **kwargs):
        if cmd[0] == "uv":
            rate = float((clone / "rule.yaml").read_text().split(":")[1])
            (clone / "rule.yaml").write_text("rate: 0.19\n")
            expected.update(provenance.worktree_state(clone))
            kwargs["stdout"].write(json.dumps({"executed_rate": rate}))
            return subprocess.CompletedProcess(cmd, 0)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(run_comparison.subprocess, "run", external_runner)
    monkeypatch.setenv("GIT_DIR", str(hook_repo / ".git"))
    runner = {
        "axiom_encode_repo": str(tmp_path / "axiom-encode"),
        "axiom_rules_repo": str(tmp_path / "axiom-rules-engine"),
        "rulespec_remote": "https://example.invalid/rulespec-us.git",
        "parameters": {"sample_size": 1, "python": "3.13"},
    }
    output = tmp_path / "tax-report.json"

    run_comparison._run_axiom_encode_tax_ecps_compare(runner, output)

    assert json.loads(output.read_text())["executed_rate"] == 0.18
    assert runner["_cloned_rulespec_us_sha"] == actual_sha  # ce154cc3a records hook SHA
    state = runner["_cloned_rulespec_us_worktree"]
    assert state["dirty"] is True
    assert state["diff_sha256"] == expected["diff_sha256"]
    assert not clone.exists()
    [entry] = run_comparison._complete_rulespecs_from_affected_map(
        {"name": "fiit-ecps"}, runner, [{"repo": _SLUG, "sha": None}]
    )
    assert entry["sha"] == actual_sha
    assert entry["dirty"] is True
    assert entry["sha_toplevel"] == entry["worktree_toplevel"] == str(clone)
    with pytest.raises(SystemExit):
        run_comparison._guard_unclean_rulespec_trees(
            "fiit-ecps", {"run_kind": "weekly", "rulespecs": [entry]}
        )


def test_clone_fetch_and_checkout_ignore_inherited_repository_env(
    run_comparison, tmp_path, monkeypatch
):
    source = _repo(tmp_path / "source" / "rulespec-us")
    pinned_sha = _head(source)
    (source / "rule.yaml").write_text("rate: 0.20\n")
    _git(source, "commit", "-q", "-am", "advance remote")
    assert _head(source) != pinned_sha
    foreign = _repo(tmp_path / "hook-repo", "rate: 0.17\n")
    incoming = _foreign_env(source, foreign)
    real_run, real_mkdtemp = subprocess.run, tempfile.mkdtemp
    observed = []

    def observe_git(cmd, *args, **kwargs):
        if cmd[0] == "git":
            observed.append((cmd, kwargs.get("env")))
        return real_run(cmd, *args, **kwargs)

    def owned_tempdir(*args, **kwargs):
        kwargs["dir"] = tmp_path
        return real_mkdtemp(*args, **kwargs)

    with monkeypatch.context() as patch:
        for variable, value in incoming.items():
            patch.setenv(variable, value)
        patch.setattr(run_comparison.subprocess, "run", observe_git)
        patch.setattr(run_comparison.tempfile, "mkdtemp", owned_tempdir)
        clone = run_comparison._ensure_rulespec_us_checkout(source.as_uri(), pinned_sha)

    assert _head(clone) == pinned_sha
    assert (clone / "rule.yaml").read_text() == "rate: 0.18\n"
    assert len(observed) == 3
    for cmd, env in observed:
        assert cmd[:2] == ["git", "-C"]
        assert Path(cmd[2]).resolve() == (clone.parent if cmd[3] == "clone" else clone)
        assert env is not None
        assert all(variable not in env for variable in _REPOSITORY_ENV)


@settings(
    max_examples=24,
    database=None,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(variables=frozenset(_REPOSITORY_ENV), dirty=False)
@example(variables=frozenset(_REPOSITORY_ENV), dirty=True)
@example(variables=frozenset({"GIT_DIR"}), dirty=False)
@example(variables=frozenset({"GIT_DIR"}), dirty=True)
@example(variables=frozenset({"GIT_WORK_TREE"}), dirty=False)
@example(variables=frozenset({"GIT_WORK_TREE"}), dirty=True)
@example(variables=frozenset({"GIT_INDEX_FILE"}), dirty=False)
@example(variables=frozenset({"GIT_INDEX_FILE"}), dirty=True)
@example(variables=frozenset({"GIT_COMMON_DIR"}), dirty=False)
@example(variables=frozenset({"GIT_COMMON_DIR"}), dirty=True)
@example(variables=frozenset({"GIT_OBJECT_DIRECTORY"}), dirty=False)
@example(variables=frozenset({"GIT_OBJECT_DIRECTORY"}), dirty=True)
@example(variables=frozenset({"GIT_ALTERNATE_OBJECT_DIRECTORIES"}), dirty=False)
@example(variables=frozenset({"GIT_ALTERNATE_OBJECT_DIRECTORIES"}), dirty=True)
@example(variables=frozenset({"GIT_CEILING_DIRECTORIES"}), dirty=False)
@example(variables=frozenset({"GIT_CEILING_DIRECTORIES"}), dirty=True)
@given(
    variables=st.frozensets(st.sampled_from(_REPOSITORY_ENV)), dirty=st.booleans()
)
def test_provenance_repository_identity_survives_inherited_env(
    run_comparison, tmp_path, monkeypatch, variables, dirty
):
    with tempfile.TemporaryDirectory(dir=tmp_path) as temporary:
        scratch = Path(temporary)
        actual = _repo(scratch / "rulespec-us")
        foreign = _repo(scratch / "hook-repo", "rate: 0.17\n")
        actual_sha = _head(actual)
        actual_tree = _git(actual, "rev-parse", "HEAD^{tree}").strip()
        if dirty:
            (actual / "rule.yaml").write_text("rate: 0.19\n")
        expected = provenance.worktree_state(actual)
        incoming = _foreign_env(actual, foreign)
        observed = []
        real_run = subprocess.run

        def observe_git(cmd, *args, **kwargs):
            if cmd[0] == "git":
                observed.append((cmd, kwargs.get("env")))
            return real_run(cmd, *args, **kwargs)

        with monkeypatch.context() as patch:
            _registry(scratch / "comparisons", run_comparison, patch)
            patch.setenv("AXIOM_RULESPEC_US_ROOT", str(actual))
            for variable in variables:
                patch.setenv(variable, incoming[variable])
            patch.setattr(provenance.subprocess, "run", observe_git)
            [direct] = provenance.rulespec_provenance([actual])
            [completed] = run_comparison._complete_rulespecs_from_affected_map(
                {"name": "co-snap-ecps"}, {}, []
            )
            engine = provenance.engine_provenance(actual)
            exact_head = run_comparison._git_toplevel_head(actual)
            de_head = de_axiom_legs._git(actual, "rev-parse", "HEAD").strip()
            pinned = {
                "rulespec_upstream_sha": actual_sha,
                "rulespec_upstream_tree": actual_tree,
            }
            if dirty:
                with pytest.raises(SystemExit, match="working-tree changes"):
                    run_comparison._verify_federal_rulespec_snapshot(pinned, [actual])
            else:
                run_comparison._verify_federal_rulespec_snapshot(pinned, [actual])
                assert pinned[run_comparison._VERIFIED_RULESPEC_UPSTREAM_SHA] == actual_sha
                assert pinned["_verified_rulespec_upstream_toplevel"] == str(actual)
            reason = run_comparison._pinned_snapshot_unusable_reason(actual, actual_tree)
            assert reason == ("working tree is dirty" if dirty else None)

        for entry in (direct, completed):
            assert entry["sha"] == actual_sha
            assert entry["dirty"] is dirty
            if dirty:
                assert entry["diff_sha256"] == expected["diff_sha256"]
        assert engine["axiom_rules_engine_sha"] == actual_sha
        assert exact_head == de_head == actual_sha
        assert observed
        for cmd, env in observed:
            assert cmd[:3] == ["git", "-C", str(actual)]
            assert env is not None
            # The private index supplies its own computed GIT_* overrides;
            # none may equal the inherited foreign-repository locator.
            for variable in variables:
                assert env.get(variable) != incoming[variable], (cmd, variable)
        for entry in (direct, completed):
            assert entry["sha_toplevel"] == entry["worktree_toplevel"] == str(actual)


def test_rulespec_root_inside_another_repository_is_unknown(
    run_comparison, tmp_path, monkeypatch
):
    parent = _repo(tmp_path / "parent")
    requested = parent / "rulespec-us"
    requested.mkdir()
    (requested / "rule.yaml").write_text("rate: 0.18\n")
    _git(parent, "add", "rulespec-us/rule.yaml")
    _git(parent, "commit", "-q", "-m", "nested rules")
    monkeypatch.setenv("GIT_DIR", str(parent / ".git"))

    [entry] = provenance.rulespec_provenance([requested])

    assert entry["sha"] == _head(parent)
    assert entry["dirty"] is None  # ce154cc3a attests the enclosing parent clean
    assert provenance.worktree_state(requested) == {"dirty": False}
    assert entry["sha_toplevel"] == entry["worktree_toplevel"] == str(parent)
    with pytest.raises(SystemExit):
        run_comparison._guard_unclean_rulespec_trees(
            "nested-root", {"run_kind": "weekly", "rulespecs": [entry]}
        )


@pytest.mark.parametrize("identity", [
    {"sha_toplevel": "/requested", "worktree_toplevel": "/foreign"},
    {"sha_toplevel": "/requested"},
    {"worktree_toplevel": "/requested"},
    {"sha_toplevel": None, "worktree_toplevel": "/requested"},
    {"sha_toplevel": "/requested", "worktree_toplevel": None},
    {"sha_toplevel": "", "worktree_toplevel": ""},
], ids=["different-roots", "sha-only", "worktree-only", "sha-null", "worktree-null", "empty"])
def test_weekly_gate_refuses_mismatched_repository_identity(run_comparison, identity):
    entry = {"repo": _SLUG, "sha": "a" * 40, "dirty": False, **identity}

    with pytest.raises(SystemExit):  # ce154cc3a accepts every synthetic clean entry
        run_comparison._guard_unclean_rulespec_trees(
            "identity-probe", {"run_kind": "weekly", "rulespecs": [entry]}
        )


@pytest.mark.parametrize("identity", [
    {}, {"sha_toplevel": "/requested", "worktree_toplevel": "/requested"},
], ids=["legacy-entry", "matching-roots"])
def test_weekly_gate_accepts_clean_matching_repository_identity(run_comparison, identity):
    run_comparison._guard_unclean_rulespec_trees(
        "identity-probe", {
            "run_kind": "weekly",
            "rulespecs": [{"repo": _SLUG, "sha": "a" * 40, "dirty": False, **identity}],
        }
    )


@pytest.mark.parametrize("runner_type,root_name,object_database_pin", [
    ("de-axiom-oracle-compare", "rulespec-de", True),
    ("federal-tax-liability-grid", "rulespec-us", False),
], ids=["de-object-pin", "federal-snapshot-pin"])
def test_verified_pin_cannot_attest_another_configured_repository(
    run_comparison, tmp_path, runner_type, root_name, object_database_pin
):
    source = _repo(tmp_path / "verified" / root_name, "rate: 0.18\n")
    configured = _repo(tmp_path / "configured" / root_name, "rate: 0.17\n")
    source_sha = _head(source)
    source_tree = _git(source, "rev-parse", "HEAD^{tree}").strip()
    assert source_sha != _head(configured)
    assert source_tree != _git(configured, "rev-parse", "HEAD^{tree}").strip()
    params = {
        "rulespec_roots": [str(configured)],
        "rulespec_root": str(source),
        "rulespec_upstream_sha": source_sha,
        "rulespec_upstream_tree": source_tree,
        "_verified_rulespec_upstream_sha": source_sha,
        "_verified_rulespec_upstream_toplevel": str(source),
    }
    if object_database_pin:
        params.update({
            "oracle": "euromod", "_verified_rulespec_upstream_tree": source_tree,
        })
    config = {
        "name": "pin-source-probe",
        "runner": {"type": runner_type, "parameters": params},
    }
    output = tmp_path / "pin-report.json"
    output.write_text("{}")

    block = run_comparison._build_run_provenance(config, runner_type, output)

    # The old stamper copied source's pin onto configured's clean attestation,
    # so the weekly gate approved a different committed rule. Refusal is the
    # first assertion, independent of whether identity fields existed yet.
    with pytest.raises(SystemExit):
        run_comparison._guard_unclean_rulespec_trees(
            "pin-source-probe", {**block, "run_kind": "weekly"}
        )
    for entry in block["rulespecs"]:
        assert entry["sha"] == source_sha
        assert entry["sha_toplevel"] == str(source)
    assert any(
        entry["worktree_toplevel"] == str(configured) for entry in block["rulespecs"]
    )
    assert all(
        entry["dirty"] is None and "diff_sha256" not in entry
        for entry in block["rulespecs"]
        if entry["sha_toplevel"] != entry["worktree_toplevel"]
    )


def test_de_producer_records_the_repository_where_it_verified_the_pin(
    tmp_path, monkeypatch
):
    source = _repo(tmp_path / "rulespec-de")
    commit = _head(source)
    tree = _git(source, "rev-parse", "HEAD^{tree}").strip()
    expected_params = {
        "oracle": "euromod",
        "suite": "de-source-probe",
        "output_dependency_plan": "comparisons/source-probe.json",
        "rulespec_upstream_sha": commit,
        "rulespec_upstream_tree": tree,
    }
    config = {"runner": {"parameters": expected_params}}
    monkeypatch.setattr(
        de_axiom_legs, "_shared_contract", lambda _oracle: ({}, config, commit, tree)
    )
    observed_roots = []

    def inspect_fixture(_oracle, *, rulespec_root):
        observed_roots.append(rulespec_root)
        assert _git(rulespec_root, "show", f"{commit}:rule.yaml") == "rate: 0.18\n"
        return {"state": "leg-pending", "pending": "module-not-on-main"}

    monkeypatch.setattr(de_axiom_legs, "build", inspect_fixture)
    runner = {
        "type": de_axiom_legs.RUNNER_TYPE,
        "parameters": {**expected_params, "rulespec_root": str(source / ".")},
    }
    output = tmp_path / "de-producer.json"

    record = de_axiom_legs.run_registered_leg(runner, output)

    assert observed_roots == [source]
    assert json.loads(output.read_text()) == record
    assert runner["parameters"]["_verified_rulespec_upstream_sha"] == commit
    assert runner["parameters"]["_verified_rulespec_upstream_tree"] == tree
    assert runner["parameters"].get("_verified_rulespec_upstream_toplevel") == str(source)
