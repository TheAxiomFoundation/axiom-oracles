"""The rules engine reaches only canonical RuleSpec checkouts.

``axiom_oracles.rulespec_roots`` defines a canonical root. These tests check
that definition directly and then drive every runtime path that hands roots
to the engine, with a fake engine that records each root it receives
(``--rulespec-root`` and ``AXIOM_RULESPEC_REPO_ROOTS``). Each fixture root
holds a sentinel file naming its kind, so a test can tell whose content the
engine could read, including through staged copies.

The runtime matrix fails if any path lets the engine reach a non-canonical
root or an inherited root list; its canonical rows are the control and must
reach the canonical checkout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles import engine_compat
from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.bridges import rulespec_overlay, snap_populace, tax_populace
from axiom_oracles.bridges.rulespec_paths import (
    _canonical_rulespec_compile_path,
    _rulespec_repo_alias_parent,
)
from axiom_oracles.rulespec_roots import (
    AMBIENT_ROOT_ENV_VARS,
    CANONICAL_ROOT_NAME,
    NonCanonicalRuleSpecRoot,
    canonical_root_problem,
    canonical_rulespec_root,
    engine_env,
    require_canonical_rulespec_root,
)

FIXTURE = Path("us-co") / "fixture.yaml"
CANONICAL_KINDS = ("plain", "git", "git-uppercase-origin", "worktree", "symlink")
NON_CANONICAL_KINDS = (
    "renamed",
    "state-repo",
    "foreign-origin",
    "inside-other-repo",
    "symlink-to-renamed",
    "nested-same-name",
)


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def _init(path: Path, origin: str | None) -> None:
    _git("init", "-q", str(path))
    _git("-C", str(path), "config", "user.name", "test")
    _git("-C", str(path), "config", "user.email", "test@invalid")
    _git("-C", str(path), "config", "commit.gpgsign", "false")
    if origin is not None:
        _git("-C", str(path), "remote", "add", "origin", origin)


def _content(path: Path, sentinel: str) -> None:
    (path / FIXTURE).parent.mkdir(parents=True, exist_ok=True)
    (path / FIXTURE).write_text(f"{sentinel}\n")


def make_root(kind: str, base: Path) -> Path:
    """Build one root of ``kind`` under ``base`` and return the path to offer."""
    base = base / kind
    base.mkdir(parents=True)
    canonical_origin = "https://github.com/TheAxiomFoundation/rulespec-us.git"
    if kind == "plain":
        root = base / "rulespec-us"
        root.mkdir()
    elif kind == "git":
        root = base / "rulespec-us"
        _init(root, canonical_origin)
    elif kind == "git-uppercase-origin":
        root = base / "rulespec-us"
        _init(root, "git@github.com:theaxiomfoundation/RuleSpec-US.git")
    elif kind == "worktree":
        main = base / "main" / "rulespec-us"
        _init(main, canonical_origin)
        _content(main, "worktree-main")
        _git("-C", str(main), "add", "-A")
        _git("-C", str(main), "commit", "-qm", "fixture")
        root = base / "wt" / "rulespec-us"
        _git("-C", str(main), "worktree", "add", "-q", str(root))
    elif kind == "symlink":
        target = base / "real" / "rulespec-us"
        _init(target, canonical_origin)
        _content(target, kind)
        root = base / "link" / "rulespec-us"
        root.parent.mkdir()
        root.symlink_to(target, target_is_directory=True)
        return root
    elif kind == "renamed":
        root = base / "rulespec-us-clean"
        _init(root, canonical_origin)
    elif kind == "state-repo":
        root = base / "rulespec-us-co"
        root.mkdir()
    elif kind == "foreign-origin":
        root = base / "rulespec-us"
        _init(root, "https://github.com/someone/custom-rules.git")
    elif kind == "inside-other-repo":
        _init(base / "outer", "https://github.com/someone/outer.git")
        root = base / "outer" / "rulespec-us"
        root.mkdir()
    elif kind == "symlink-to-renamed":
        target = base / "rulespec-us-dev"
        target.mkdir()
        _content(target, kind)
        root = base / "link" / "rulespec-us"
        root.parent.mkdir()
        root.symlink_to(target, target_is_directory=True)
        return root
    elif kind == "nested-same-name":
        root = base / "rulespec-us"
        (root / "rulespec-us").mkdir(parents=True)
    else:  # pragma: no cover - guards the parametrization
        raise AssertionError(kind)
    _content(root, kind)
    return root


# --------------------------------------------------------------------------- #
# The definition
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", CANONICAL_KINDS)
def test_canonical_kinds_are_accepted_and_resolved(kind, tmp_path):
    root = make_root(kind, tmp_path)
    assert canonical_root_problem(root) is None
    assert canonical_rulespec_root(root) == root.resolve()
    assert require_canonical_rulespec_root(root, country="us") == root.resolve()


@pytest.mark.parametrize("kind", NON_CANONICAL_KINDS)
def test_non_canonical_kinds_are_refused_with_a_reason(kind, tmp_path):
    root = make_root(kind, tmp_path)
    problem = canonical_root_problem(root)
    assert problem
    assert canonical_rulespec_root(root) is None
    with pytest.raises(NonCanonicalRuleSpecRoot, match=re.escape(problem)):
        require_canonical_rulespec_root(root)


def test_missing_paths_files_and_wrong_country_are_refused(tmp_path):
    assert canonical_root_problem(tmp_path / "rulespec-us") == "it does not exist"
    (tmp_path / "f").mkdir()
    file_root = tmp_path / "f" / "rulespec-us"
    file_root.write_text("")
    assert canonical_root_problem(file_root) == "it is not a directory"
    uk = tmp_path / "rulespec-uk"
    uk.mkdir()
    with pytest.raises(NonCanonicalRuleSpecRoot, match="'rulespec-us'"):
        require_canonical_rulespec_root(uk, country="us")


# --------------------------------------------------------------------------- #
# Every runtime path that hands roots to the engine
# --------------------------------------------------------------------------- #


class FakeEngine:
    """Record every root a command could read, then behave like an engine.

    ``old=True`` imitates an engine that predates ``--rulespec-root``: it
    rejects the flag and accepts the env-resolved legacy compile.
    """

    def __init__(self, binary: Path, *, old: bool) -> None:
        self.binary = binary.resolve()
        self.old = old
        self.commands: list[list[str]] = []
        # (root, why it is not canonical or None, its sentinel or None),
        # captured during the call because staged copies are deleted after.
        self.reached: list[tuple[Path, str | None, str | None]] = []

    def __call__(self, cmd, **kwargs):
        if Path(cmd[0]).resolve() != self.binary:
            return subprocess.CompletedProcess(cmd, 1, "", "unexpected command")
        self.commands.append(list(cmd))
        roots = [Path(cmd[i + 1]) for i, arg in enumerate(cmd) if arg == "--rulespec-root"]
        env = kwargs.get("env")
        env = os.environ if env is None else env
        roots += [Path(p) for p in env.get("AXIOM_RULESPEC_REPO_ROOTS", "").split(os.pathsep) if p]
        for root in roots:
            fixture = root / FIXTURE
            sentinel = fixture.read_text().strip() if fixture.is_file() else None
            self.reached.append((root, canonical_root_problem(root), sentinel))
        verb = cmd[1]
        if verb in ("compile", "compile-composed"):
            if self.old and ("--rulespec-root" in cmd or verb == "compile-composed"):
                return subprocess.CompletedProcess(cmd, 1, "", "unknown compile argument")
            Path(cmd[cmd.index("--output") + 1]).write_text(
                json.dumps({"program": {"derived": [], "parameters": [], "relations": []}})
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"results": []}), "")

    def sentinels(self) -> set[str]:
        return {sentinel for _, _, sentinel in self.reached if sentinel}


def _composition(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "format: rulespec/v1\nmodule: {kind: composition}\n"
        'imports: ["us-co:fixture"]\nrules: []\n'
    )
    return path


def _via_compile_with_engine(root, tmp, engine):
    engine_compat.compile_with_engine(
        engine.binary, _composition(tmp / "program.yaml"), tmp / "out.json",
        roots=[root], composed=True, env=None, run=engine,
    )


def _via_explicit_roots(root, tmp, engine):
    roots = engine_compat.explicit_engine_roots([root, tmp / "workspace"], strict=True)
    engine_compat.compile_with_engine(
        engine.binary, _composition(tmp / "program.yaml"), tmp / "out.json",
        roots=roots, composed=True, env=dict(os.environ), run=engine,
    )


def _via_runner(root, tmp, engine):
    runner = AxiomRulesRunner(
        binary_path=engine.binary, rulespec_repo_roots=(root,), subprocess_run=engine,
    )
    runner._artifact_path(tmp, _composition(tmp / "program.yaml"))


def _via_snap_compile(root, tmp, engine, monkeypatch):
    monkeypatch.setattr(subprocess, "run", engine)
    snap_populace.compile_program(
        engine.binary, _composition(tmp / "program.yaml"), tmp / "out.json",
        env=dict(os.environ), workspace_root=root,
    )


def _via_snap_env(root, tmp, engine, monkeypatch):
    """The SNAP QC and Medicaid shape: an in-checkout program, then a run.

    Both callers build the env with axiom_rules_env, compile the program that
    lives inside the checkout, and pass the same env to run-compiled.
    """
    monkeypatch.setattr(subprocess, "run", engine)
    program = _composition(root / "us-co" / "program.yaml")
    env = snap_populace.axiom_rules_env(program, root.parent)
    snap_populace.compile_program(engine.binary, program, tmp / "out.json", env=env)
    snap_populace._run_receipted_engine(
        [str(engine.binary), "run-compiled", "--artifact", str(tmp / "out.json")],
        expected_receipt=snap_populace.engine_receipt(engine.binary),
        env=env,
    )


def _via_tax_populace(root, tmp, engine, monkeypatch):
    monkeypatch.setattr(subprocess, "run", engine)
    engine_root = engine.binary.parents[2]
    tax_populace.run_axiom_program(
        program=root / FIXTURE, request={"queries": []},
        rulespec_root=root, axiom_rules_path=engine_root,
    )


RUNTIME_PATHS = {
    "compile_with_engine": _via_compile_with_engine,
    "explicit_engine_roots": _via_explicit_roots,
    "axiom_runner": _via_runner,
    "snap_compile_program": _via_snap_compile,
    "snap_axiom_rules_env": _via_snap_env,
    "tax_populace": _via_tax_populace,
}


def _drive(path_name, kind, old, tmp_path, monkeypatch):
    ambient = tmp_path / "ambient" / "rulespec-us"
    ambient.mkdir(parents=True)
    _content(ambient, "ambient")
    for key in AMBIENT_ROOT_ENV_VARS:
        monkeypatch.setenv(key, str(ambient))
    root = make_root(kind, tmp_path / "roots")
    binary = tmp_path / "engine" / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"fake engine")
    engine = FakeEngine(binary, old=old)
    work = tmp_path / "work"
    work.mkdir()
    (work / "workspace").mkdir()
    driver = RUNTIME_PATHS[path_name]
    args = (root, work, engine)
    if driver.__code__.co_argcount == 4:
        args = (*args, monkeypatch)
    try:
        driver(*args)
    except NonCanonicalRuleSpecRoot:
        refused = True
    else:
        refused = False
    return engine, refused


def _assert_only_canonical_reached(engine):
    for root, problem, _ in engine.reached:
        assert problem is None, (root, problem)
        assert root == root.resolve(), f"engine received an unresolved path {root}"
    assert "ambient" not in engine.sentinels()


@pytest.mark.parametrize("old", [False, True], ids=["engine-main", "pre-flag-engine"])
@pytest.mark.parametrize("kind", NON_CANONICAL_KINDS)
@pytest.mark.parametrize("path_name", sorted(RUNTIME_PATHS))
def test_runtime_paths_never_reach_a_non_canonical_root(
    path_name, kind, old, tmp_path, monkeypatch
):
    engine, refused = _drive(path_name, kind, old, tmp_path, monkeypatch)
    _assert_only_canonical_reached(engine)
    assert kind not in engine.sentinels()
    if refused:
        assert engine.commands == [], "a refused root must stop before the engine runs"


@pytest.mark.parametrize("old", [False, True], ids=["engine-main", "pre-flag-engine"])
@pytest.mark.parametrize("kind", CANONICAL_KINDS)
@pytest.mark.parametrize("path_name", sorted(RUNTIME_PATHS))
def test_runtime_paths_reach_the_canonical_root_control(
    path_name, kind, old, tmp_path, monkeypatch
):
    engine, refused = _drive(path_name, kind, old, tmp_path, monkeypatch)
    assert not refused
    _assert_only_canonical_reached(engine)
    assert kind in engine.sentinels()
    compiles = [cmd for cmd in engine.commands if cmd[1].startswith("compile")]
    assert compiles
    if not old:
        assert all("--rulespec-root" in cmd for cmd in compiles)


def test_overlay_must_start_from_a_canonical_checkout(tmp_path):
    # The root is checked before the spec is read, so no spec is needed.
    root = make_root("renamed", tmp_path)
    with pytest.raises(NonCanonicalRuleSpecRoot):
        rulespec_overlay.build_overlay(None, root, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


@pytest.mark.parametrize("kind", NON_CANONICAL_KINDS)
def test_encoder_path_helpers_refuse_instead_of_aliasing(kind, tmp_path):
    root = make_root(kind, tmp_path)
    with pytest.raises(NonCanonicalRuleSpecRoot):
        _rulespec_repo_alias_parent(root)
    with pytest.raises(NonCanonicalRuleSpecRoot):
        _canonical_rulespec_compile_path(root / FIXTURE, root)
    assert not list(tmp_path.rglob("axiom-rulespec-repo-aliases"))


@pytest.mark.parametrize("kind", CANONICAL_KINDS)
def test_encoder_path_helpers_accept_checkout_and_jurisdiction_dir(kind, tmp_path):
    root = make_root(kind, tmp_path)
    assert _rulespec_repo_alias_parent(root) is None
    assert _rulespec_repo_alias_parent(root / "us-co") is None
    assert _canonical_rulespec_compile_path(root / FIXTURE, root) == root / FIXTURE
    outside = tmp_path / "outside.yaml"
    outside.write_text("")
    with pytest.raises(NonCanonicalRuleSpecRoot, match="outside"):
        _canonical_rulespec_compile_path(outside, root)


# --------------------------------------------------------------------------- #
# Properties
# --------------------------------------------------------------------------- #

_NAME_CHARS = st.sampled_from("rulespec-USabkz09_.")


@settings(max_examples=150, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(name=st.one_of(
    st.text(_NAME_CHARS, min_size=1, max_size=16),
    st.builds(lambda cc: f"rulespec-{cc}", st.text(st.sampled_from("abuzAU1-"), max_size=4)),
))
def test_property_plain_directory_is_canonical_iff_its_name_is(name, tmp_path):
    if name in {".", ".."} or "/" in name:
        return
    path = tmp_path / "p" / name
    path.mkdir(parents=True, exist_ok=True)
    try:
        assert (canonical_root_problem(path) is None) == bool(
            CANONICAL_ROOT_NAME.fullmatch(name)
        )
    finally:
        path.rmdir()


@given(env=st.dictionaries(
    st.one_of(st.sampled_from(AMBIENT_ROOT_ENV_VARS), st.text(min_size=1, max_size=8)),
    st.text(max_size=12),
))
def test_property_engine_env_drops_inherited_roots_and_keeps_the_rest(env):
    out = engine_env(env)
    for key in AMBIENT_ROOT_ENV_VARS:
        assert key not in out
    assert out == {k: v for k, v in env.items() if k not in AMBIENT_ROOT_ENV_VARS}
    assert engine_env(None).keys() == {
        k for k in os.environ if k not in AMBIENT_ROOT_ENV_VARS
    }


@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(owner=st.text(st.sampled_from("abcXYZ-"), min_size=1, max_size=6),
       repo=st.sampled_from(["rulespec-us", "RuleSpec-US", "rulespec-uk",
                             "rulespec-us-co", "custom", "RULESPEC-us"]),
       form=st.sampled_from(["https://github.com/{o}/{r}.git", "git@github.com:{o}/{r}.git",
                             "https://github.com/{o}/{r}", "https://github.com/{o}/{r}/"]))
def test_property_origin_must_name_the_checkout_ignoring_case(owner, repo, form, tmp_path):
    root = tmp_path / f"o{abs(hash((owner, repo, form)))}" / "rulespec-us"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "config").write_text(
        f'[remote "origin"]\n\turl = {form.format(o=owner, r=repo)}\n'
    )
    assert (canonical_root_problem(root) is None) == (repo.casefold() == "rulespec-us")


# --------------------------------------------------------------------------- #
# Differential tests
# --------------------------------------------------------------------------- #


@pytest.fixture
def root_pool(tmp_path):
    pool = {kind: make_root(kind, tmp_path / "pool") for kind in
            (*CANONICAL_KINDS, *NON_CANONICAL_KINDS)}
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for kind in ("git", "foreign-origin", "state-repo"):
        source = pool[kind]
        (workspace / kind).mkdir()
        (workspace / kind / source.name).symlink_to(source, target_is_directory=True)
    pool["workspace-git"] = workspace / "git"
    pool["workspace-foreign"] = workspace / "foreign-origin"
    pool["workspace-state"] = workspace / "state-repo"
    return pool


def test_differential_runtime_roots_are_declared_roots_that_validate(root_pool):
    """explicit_engine_roots == declared_engine_roots filtered by the definition.

    Provenance records the declared superset; the runtime must use exactly its
    canonical members, in the same order, for every subset of candidates.
    """
    names = sorted(root_pool)

    @settings(max_examples=80, deadline=None)
    @given(st.lists(st.sampled_from(names), max_size=6))
    def check(selection):
        candidates = [root_pool[name] for name in selection]
        declared = engine_compat.declared_engine_roots(candidates)
        runtime = engine_compat.explicit_engine_roots(candidates)
        assert runtime == [root for root in declared if canonical_root_problem(root) is None]
        assert all(canonical_root_problem(root) is None for root in runtime)

    check()


def _git_cli_problem(path: Path) -> bool:
    """Reference: does the ``git`` binary disqualify this directory?"""
    resolved = path.resolve()
    top = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": ""},
    )
    if top.returncode != 0:
        return False
    if Path(top.stdout.strip()).resolve() != resolved:
        return True
    origin = subprocess.run(
        ["git", "-C", str(resolved), "config", "--get", "remote.origin.url"],
        capture_output=True, text=True,
    ).stdout.strip().rstrip("/")
    if not origin:
        return False
    return re.split(r"[/:]", origin)[-1].removesuffix(".git").casefold() != resolved.name


@pytest.mark.parametrize("kind", (*CANONICAL_KINDS, *NON_CANONICAL_KINDS))
def test_differential_filesystem_git_check_matches_the_git_binary(kind, tmp_path):
    """The filesystem reader and the git CLI agree on every fixture."""
    root = make_root(kind, tmp_path)
    if CANONICAL_ROOT_NAME.fullmatch(root.resolve().name) is None:
        pytest.skip("the name check decides before Git is consulted")
    if (root.resolve() / root.resolve().name).exists():
        pytest.skip("the nested-name check decides before Git is consulted")
    assert (canonical_root_problem(root) is not None) == _git_cli_problem(root)
