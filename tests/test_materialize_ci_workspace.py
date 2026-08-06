"""Tests for the per-suite CI workspace materializer (#296/#300).

The materializer makes a CI runner isomorphic to the supervised layout the
comparison harnesses resolve paths from — mapped rulespec clones under
``<workspace>/TheAxiomFoundation``, the ``~/rulespec-*`` /
``~/.axiom-oracles/roots`` / ``~/rulespec-uk-official`` conventions, and the
axiom-compose venv. Planning is pure (``build_plan``), so these tests assert
the plans; execution is exercised only for the symlink kind (no network).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[1]
SCRIPTS = REPO_ROOT / "scripts"


def _load():
    module_path = SCRIPTS / "materialize_ci_workspace.py"
    spec = importlib.util.spec_from_file_location(
        "materialize_ci_workspace", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _real_map() -> dict:
    return json.loads((REPO_ROOT / "comparisons" / "affected_map.json").read_text())


def _real_config(name: str) -> dict:
    return yaml.safe_load((REPO_ROOT / "comparisons" / f"{name}.yaml").read_text())


def _kinds(actions: list[dict]) -> set[str]:
    return {a["kind"] for a in actions}


def test_mapped_repos_matches_name_and_suite_and_dedupes():
    mcw = _load()
    amap = {
        "suites": [
            {"suite": "s", "name": "reg", "repos": ["o/rulespec-us"]},
            {"suite": "reg", "name": None, "repos": ["o/rulespec-us", "o/rulespec-x"]},
            {"suite": "other", "name": "other", "repos": ["o/rulespec-y"]},
        ]
    }
    assert mcw.mapped_repos(amap, "reg") == ["o/rulespec-us", "o/rulespec-x"]
    assert mcw.mapped_repos(amap, "nope") == []


def test_plan_clones_mapped_repos_and_links_conventions(tmp_path):
    mcw = _load()
    config = {
        "runner": {
            "type": "axiom-oracles-compare",
            "parameters": {
                "rulespec_roots": ["$HOME/rulespec-us"],
                "axiom_rulespec_repo_roots": "$HOME/.axiom-oracles/roots",
                "axiom_program": "programs/us/ssi/fy-2026.yaml",
            },
        }
    }
    repos = ["TheAxiomFoundation/rulespec-us", "TheAxiomFoundation/rulespec-us-az"]
    actions = mcw.build_plan(config, repos, tmp_path)

    clones = {a["repo"]: a["dest"] for a in actions if a["kind"] == "clone"}
    assert clones["TheAxiomFoundation/rulespec-us"] == str(
        tmp_path / "TheAxiomFoundation" / "rulespec-us"
    )
    assert "TheAxiomFoundation/rulespec-us-az" in clones

    links = {a["link"]: a["target"] for a in actions if a["kind"] == "symlink"}
    # Top-level $HOME/<repo> links exist for every mapped repo (covers both
    # explicit $HOME/rulespec-us references and bare-$HOME roots scanning).
    assert links[str(tmp_path / "rulespec-us")] == str(
        tmp_path / "TheAxiomFoundation" / "rulespec-us"
    )
    assert str(tmp_path / "rulespec-us-az") in links
    # Synced-roots children, one per mapped repo.
    assert links[str(tmp_path / ".axiom-oracles" / "roots" / "rulespec-us")] == str(
        tmp_path / "TheAxiomFoundation" / "rulespec-us"
    )
    # Composed-program suite → compose venv build.
    assert {"kind": "compose-venv", "repo": "TheAxiomFoundation/axiom-compose",
            "dest": str(tmp_path / "axiom-compose")} in actions


def test_plan_is_empty_on_a_materialized_workspace(tmp_path):
    """Skip-if-present: a supervised machine's layout is never touched."""
    mcw = _load()
    org = tmp_path / "TheAxiomFoundation"
    (org / "rulespec-us").mkdir(parents=True)
    (tmp_path / "rulespec-us").symlink_to(org / "rulespec-us")
    roots = tmp_path / ".axiom-oracles" / "roots"
    roots.mkdir(parents=True)
    (roots / "rulespec-us").symlink_to(org / "rulespec-us")
    compose_bin = tmp_path / "axiom-compose" / ".venv" / "bin"
    compose_bin.mkdir(parents=True)
    (compose_bin / "axiom-compose").touch()

    config = {
        "runner": {
            "parameters": {
                "rulespec_roots": ["$HOME/rulespec-us"],
                "axiom_rulespec_repo_roots": "$HOME/.axiom-oracles/roots",
                "axiom_program": "programs/us/ssi/fy-2026.yaml",
            },
        }
    }
    actions = mcw.build_plan(
        config, ["TheAxiomFoundation/rulespec-us"], tmp_path
    )
    assert actions == []


def test_plan_provides_uk_official_alias(tmp_path):
    """#300: the efrs suites resolve $HOME/rulespec-uk-official — the alias
    points at the pristine rulespec-uk clone — plus the dataset cache dir the
    runner resolves fatally before populating. uk-tax-benefits-efrs no longer
    declares the composed-UC program (all its surfaces are source-path), so
    its plan must NOT drag in the axiom-programs checkout or the compose
    venv."""
    mcw = _load()
    config = _real_config("uk-tax-benefits-efrs")
    repos = mcw.mapped_repos(_real_map(), "uk-tax-benefits-efrs")
    assert "TheAxiomFoundation/rulespec-uk" in repos
    actions = mcw.build_plan(config, repos, tmp_path)
    links = {a["link"]: a["target"] for a in actions if a["kind"] == "symlink"}
    assert links[str(tmp_path / "rulespec-uk-official")] == str(
        tmp_path / "TheAxiomFoundation" / "rulespec-uk"
    )
    cloned = {a["repo"] for a in actions if a["kind"] == "clone"}
    assert "TheAxiomFoundation/axiom-programs" not in cloned
    assert _kinds(actions).isdisjoint({"compose-venv"})
    mkdirs = {a["path"] for a in actions if a["kind"] == "mkdir"}
    assert (
        str(tmp_path / "axiom-oracles" / ".axiom" / "policyengine-data") in mkdirs
    )


def test_plan_provides_compose_stack_for_composed_uc_suite(tmp_path):
    """The composed-UC suite (uk-universal-credit-efrs) is the one that needs
    the axiom-programs compose-spec checkout and the compose venv."""
    mcw = _load()
    config = _real_config("uk-universal-credit-efrs")
    repos = mcw.mapped_repos(_real_map(), "uk-universal-credit-efrs")
    actions = mcw.build_plan(config, repos, tmp_path)
    cloned = {a["repo"] for a in actions if a["kind"] == "clone"}
    assert "TheAxiomFoundation/axiom-programs" in cloned
    links = {a["link"]: a["target"] for a in actions if a["kind"] == "symlink"}
    assert links[str(tmp_path / "axiom-programs")] == str(
        tmp_path / "TheAxiomFoundation" / "axiom-programs"
    )
    assert "compose-venv" in _kinds(actions)


def test_real_failing_suites_produce_working_plans(tmp_path):
    """Every #296 failure class maps to a non-empty, correctly-shaped plan."""
    mcw = _load()
    amap = _real_map()

    # az/ca SNAP migrated off the encoder harness onto the generic
    # composed-program runner (household-input-panel): only the federal
    # monorepo clones now, and the compose venv is required.
    plan = mcw.build_plan(
        _real_config("az-snap-ecps"), mcw.mapped_repos(amap, "az-snap-ecps"), tmp_path
    )
    cloned = {a["repo"] for a in plan if a["kind"] == "clone"}
    assert "TheAxiomFoundation/rulespec-us" in cloned
    assert "TheAxiomFoundation/rulespec-us-az" not in cloned
    assert "compose-venv" in _kinds(plan)

    # Composed-program class (tanf/ssi/medicaid + al/fl/... snap): compose
    # venv plus the roots conventions.
    plan = mcw.build_plan(
        _real_config("az-tanf-ecps"), mcw.mapped_repos(amap, "az-tanf-ecps"), tmp_path
    )
    assert "compose-venv" in _kinds(plan)
    links = {a["link"]: a["target"] for a in plan if a["kind"] == "symlink"}
    assert str(tmp_path / "rulespec-us") in links
    # az-tanf names its axiom-programs spec via $HOME/axiom-oracles — CI must
    # get a link to this checkout or the program path resolution is fatal.
    assert links[str(tmp_path / "axiom-oracles")] == str(mcw.REPO_ROOT)

    plan = mcw.build_plan(
        _real_config("ssi-ecps"), mcw.mapped_repos(amap, "ssi-ecps"), tmp_path
    )
    links = {a["link"] for a in plan if a["kind"] == "symlink"}
    assert str(tmp_path / ".axiom-oracles" / "roots" / "rulespec-us") in links

    # Engine hard-cut class (co-state tax): bare-$HOME roots scanning still
    # gets a top-level rulespec-us link.
    plan = mcw.build_plan(
        _real_config("co-state-income-tax-ecps"),
        mcw.mapped_repos(amap, "co-state-income-tax-ecps"),
        tmp_path,
    )
    links = {a["link"] for a in plan if a["kind"] == "symlink"}
    assert str(tmp_path / "rulespec-us") in links


def test_execute_creates_symlinks(tmp_path):
    mcw = _load()
    target = tmp_path / "TheAxiomFoundation" / "rulespec-us"
    target.mkdir(parents=True)
    link = tmp_path / "rulespec-us"
    mcw.execute([{"kind": "symlink", "link": str(link), "target": str(target)}])
    assert link.is_symlink()
    assert link.resolve() == target.resolve()


def test_compile_with_engine_reports_primary_error_when_fallback_also_fails():
    """NEGATIVE: a genuine new-contract failure whose text merely resembles a
    legacy marker triggers the fallback — when that fails too, the primary
    error must lead so the real problem is never masked (#296)."""
    import importlib.util as ilu

    spec = ilu.spec_from_file_location(
        "engine_compat", REPO_ROOT / "axiom_oracles" / "engine_compat.py"
    )
    ec = ilu.module_from_spec(spec)
    spec.loader.exec_module(ec)

    import subprocess

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="invalid choice: 'something-real'"
            )
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="legacy boom"
        )

    import pytest

    with pytest.raises(RuntimeError) as err:
        ec.compile_with_engine(
            "engine",
            Path("/tmp/p.yaml"),
            Path("/tmp/out.json"),
            roots=[],
            composed=True,
            run=fake_run,
        )
    message = str(err.value)
    assert "invalid choice: 'something-real'" in message
    assert "legacy boom" in message
    assert calls[0][1] == "compile-composed"
    assert calls[1][1] == "compile"


def test_clone_falls_back_to_git_when_gh_fails(monkeypatch, tmp_path, capsys):
    """gh occasionally fails instantly with no diagnostic under a busy matrix
    (a restored-sweep leg died on exactly this); the clone must retry with
    plain git using the same token — without ever printing the token URL."""
    import subprocess as sp

    mcw = _load()
    dest = tmp_path / "org" / "axiom-compose"
    monkeypatch.setenv("GH_TOKEN", "sekret-token")
    monkeypatch.setattr(mcw.shutil, "which", lambda _name: "/usr/bin/gh")
    calls = []

    def fake_run(cmd, check=False):
        calls.append(cmd)
        if cmd[0] == "gh":
            return sp.CompletedProcess(cmd, 1)
        dest.mkdir(parents=True, exist_ok=True)
        return sp.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mcw.subprocess, "run", fake_run)

    mcw._clone("TheAxiomFoundation/axiom-compose", dest)

    assert calls[0][0] == "gh"
    assert calls[1][0] == "git"
    assert calls[1][-1] == str(dest)
    assert any("x-access-token:sekret-token@" in arg for arg in calls[1])
    out = capsys.readouterr()
    assert "sekret-token" not in out.out
    assert "sekret-token" not in out.err
    assert "retrying with git" in out.err


def test_clone_uses_gh_when_it_succeeds(monkeypatch, tmp_path):
    import subprocess as sp

    mcw = _load()
    dest = tmp_path / "org" / "rulespec-us"
    monkeypatch.setattr(mcw.shutil, "which", lambda _name: "/usr/bin/gh")
    calls = []

    def fake_run(cmd, check=False):
        calls.append(cmd)
        return sp.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mcw.subprocess, "run", fake_run)

    mcw._clone("TheAxiomFoundation/rulespec-us", dest)

    assert [c[0] for c in calls] == ["gh"]


def test_clone_double_failure_never_leaks_the_token(monkeypatch, tmp_path, capsys):
    import subprocess as sp

    import pytest as _pytest

    mcw = _load()
    dest = tmp_path / "org" / "axiom-compose"
    monkeypatch.setenv("GH_TOKEN", "sekret-token")
    monkeypatch.setattr(mcw.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(
        mcw.subprocess,
        "run",
        lambda cmd, check=False: sp.CompletedProcess(cmd, 1),
    )

    with _pytest.raises(SystemExit) as exc:
        mcw._clone("TheAxiomFoundation/axiom-compose", dest)

    message = str(exc.value)
    assert "TheAxiomFoundation/axiom-compose" in message
    assert "sekret-token" not in message
    out = capsys.readouterr()
    assert "sekret-token" not in out.out + out.err
