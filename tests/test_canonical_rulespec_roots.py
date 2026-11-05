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
CANONICAL_KINDS = (
    "plain",
    "git",
    "git-uppercase-origin",
    "ssh-origin",
    "inline-comment-origin",
    "continuation-origin",
    "no-origin",
    "worktree",
    "symlink",
    "dotdot-through-symlink",
)
NON_CANONICAL_KINDS = (
    "renamed",
    "state-repo",
    "foreign-origin",
    "fork",
    "fork-worktree",
    "other-host",
    "other-host-ssh",
    "uppercase-section-foreign",
    "include-foreign",
    "includeif-foreign",
    "insteadof-rewrite",
    "worktree-config-foreign",
    "continuation-foreign",
    "two-origins",
    "inside-other-repo",
    "empty-dotgit-inside-other-repo",
    "symlink-to-renamed",
    "link-names-another-country",
    "dotdot-to-foreign",
    "nested-same-name",
)
CANONICAL_ORIGIN = "https://github.com/TheAxiomFoundation/rulespec-us.git"
FORK_ORIGIN = "https://github.com/evil/rulespec-us.git"


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


def _append_config(root: Path, text: str) -> None:
    with open(root / ".git" / "config", "a", encoding="utf-8") as config:
        config.write(text)


def _committed(root: Path, origin: str) -> None:
    _init(root, origin)
    _content(root, "committed")
    _git("-C", str(root), "add", "-A")
    _git("-C", str(root), "commit", "-qm", "fixture")


def make_root(kind: str, base: Path) -> Path:
    """Build one root of ``kind`` under ``base`` and return the path to offer."""
    base = base / kind
    base.mkdir(parents=True)
    if kind == "plain":
        root = base / "rulespec-us"
        root.mkdir()
    elif kind == "git":
        root = base / "rulespec-us"
        _init(root, CANONICAL_ORIGIN)
    elif kind == "git-uppercase-origin":
        root = base / "rulespec-us"
        _init(root, "https://github.com/theaxiomfoundation/RuleSpec-US")
    elif kind == "ssh-origin":
        root = base / "rulespec-us"
        _init(root, "git@github.com:TheAxiomFoundation/rulespec-us.git")
    elif kind == "inline-comment-origin":
        root = base / "rulespec-us"
        _init(root, None)
        _append_config(root, f'[remote "origin"]\n\turl = {CANONICAL_ORIGIN} ; a note\n')
    elif kind == "continuation-origin":
        # A trailing backslash joins the next line, so this is the canonical
        # origin split in two.
        root = base / "rulespec-us"
        _init(root, None)
        _append_config(
            root,
            '[remote "origin"]\n\turl = https://github.com/TheAxiom\\\nFoundation/rulespec-us\n',
        )
    elif kind == "no-origin":
        root = base / "rulespec-us"
        _init(root, None)
    elif kind == "worktree":
        main = base / "main" / "rulespec-us"
        _committed(main, CANONICAL_ORIGIN)
        root = base / "wt" / "rulespec-us"
        _git("-C", str(main), "worktree", "add", "-q", str(root))
    elif kind == "symlink":
        target = base / "real" / "rulespec-us"
        _init(target, CANONICAL_ORIGIN)
        _content(target, kind)
        root = base / "link" / "rulespec-us"
        root.parent.mkdir()
        root.symlink_to(target, target_is_directory=True)
        return root
    elif kind == "dotdot-through-symlink":
        # a/link -> b/sub, so a/link/../rulespec-us opens b/rulespec-us;
        # collapsing ".." first would look for a/rulespec-us, which is absent.
        (base / "b" / "sub").mkdir(parents=True)
        target = base / "b" / "rulespec-us"
        _init(target, CANONICAL_ORIGIN)
        _content(target, kind)
        (base / "a").mkdir()
        (base / "a" / "link").symlink_to(base / "b" / "sub", target_is_directory=True)
        return base / "a" / "link" / ".." / "rulespec-us"
    elif kind == "renamed":
        root = base / "rulespec-us-clean"
        _init(root, CANONICAL_ORIGIN)
    elif kind == "state-repo":
        root = base / "rulespec-us-co"
        root.mkdir()
    elif kind == "foreign-origin":
        root = base / "rulespec-us"
        _init(root, "https://github.com/someone/custom-rules.git")
    elif kind == "fork":
        root = base / "rulespec-us"
        _init(root, FORK_ORIGIN)
    elif kind == "fork-worktree":
        main = base / "main" / "rulespec-us"
        _committed(main, FORK_ORIGIN)
        root = base / "wt" / "rulespec-us"
        _git("-C", str(main), "worktree", "add", "-q", str(root))
    elif kind == "other-host":
        root = base / "rulespec-us"
        _init(root, "https://gitlab.com/x/y/rulespec-us")
    elif kind == "other-host-ssh":
        root = base / "rulespec-us"
        _init(root, "git@gitlab.com:TheAxiomFoundation/rulespec-us.git")
    elif kind == "uppercase-section-foreign":
        root = base / "rulespec-us"
        _init(root, None)
        _append_config(root, '[Remote "origin"]\n\turl = https://github.com/evil/other.git\n')
    elif kind in ("include-foreign", "includeif-foreign"):
        root = base / "rulespec-us"
        _init(root, None)
        included = base / "included.cfg"
        included.write_text('[remote "origin"]\n\turl = https://github.com/evil/other.git\n')
        header = "[include]" if kind == "include-foreign" else '[includeIf "gitdir:/"]'
        _append_config(root, f"{header}\n\tpath = {included}\n")
    elif kind == "insteadof-rewrite":
        root = base / "rulespec-us"
        _init(root, CANONICAL_ORIGIN)
        _append_config(
            root,
            '[url "https://github.com/evil/"]\n'
            "\tinsteadOf = https://github.com/TheAxiomFoundation/\n",
        )
    elif kind == "worktree-config-foreign":
        # The shared config names no origin; the per-worktree config, which
        # git reads once extensions.worktreeConfig is on, names a fork.
        root = base / "rulespec-us"
        _init(root, None)
        _git("-C", str(root), "config", "extensions.worktreeConfig", "true")
        _git("-C", str(root), "config", "--worktree", "remote.origin.url", FORK_ORIGIN)
    elif kind == "continuation-foreign":
        # The first line alone is the canonical origin; the continuation
        # makes it rulespec-us-fork.
        root = base / "rulespec-us"
        _init(root, None)
        _append_config(
            root,
            f'[remote "origin"]\n\turl = {CANONICAL_ORIGIN.removesuffix(".git")}\\\n-fork\n',
        )
    elif kind == "two-origins":
        root = base / "rulespec-us"
        _init(root, None)
        _append_config(
            root,
            f'[remote "origin"]\n\turl = {FORK_ORIGIN}\n\turl = {CANONICAL_ORIGIN}\n',
        )
    elif kind == "inside-other-repo":
        _init(base / "outer", "https://github.com/someone/outer.git")
        root = base / "outer" / "rulespec-us"
        root.mkdir()
    elif kind == "empty-dotgit-inside-other-repo":
        _init(base / "outer", "https://github.com/someone/outer.git")
        root = base / "outer" / "rulespec-us"
        (root / ".git").mkdir(parents=True)
    elif kind == "symlink-to-renamed":
        target = base / "rulespec-us-dev"
        target.mkdir()
        _content(target, kind)
        root = base / "link" / "rulespec-us"
        root.parent.mkdir()
        root.symlink_to(target, target_is_directory=True)
        return root
    elif kind == "link-names-another-country":
        target = base / "real" / "rulespec-us"
        _init(target, CANONICAL_ORIGIN)
        _content(target, kind)
        root = base / "link" / "rulespec-uk"
        root.parent.mkdir()
        root.symlink_to(target, target_is_directory=True)
        return root
    elif kind == "dotdot-to-foreign":
        # Lexically a/rulespec-us (canonical); the OS opens b/rulespec-us (a fork).
        (base / "b" / "sub").mkdir(parents=True)
        target = base / "b" / "rulespec-us"
        _init(target, FORK_ORIGIN)
        _content(target, kind)
        decoy = base / "a" / "rulespec-us"
        _init(decoy, CANONICAL_ORIGIN)
        _content(decoy, "decoy")
        (base / "a" / "link").symlink_to(base / "b" / "sub", target_is_directory=True)
        return base / "a" / "link" / ".." / "rulespec-us"
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


#: The origin git itself reports for the fixtures whose config the reader
#: must interpret the way git does.
GIT_SEES_ORIGIN = {
    "continuation-origin": "https://github.com/TheAxiomFoundation/rulespec-us",
    "continuation-foreign": "https://github.com/TheAxiomFoundation/rulespec-us-fork",
    "worktree-config-foreign": FORK_ORIGIN,
}


@pytest.mark.parametrize("kind", sorted(GIT_SEES_ORIGIN))
def test_fixture_origins_are_the_ones_git_reads(kind, tmp_path):
    """Differential control: git reads the origin each fixture claims.

    The worktree-config fixture keeps its shared config free of any origin,
    so a reader that skipped the extensions.worktreeConfig refusal would see
    a checkout with no origin and accept the fork git would fetch from.
    """
    root = make_root(kind, tmp_path)
    got = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert got == GIT_SEES_ORIGIN[kind]


def test_worktree_config_refusal_names_its_reason(tmp_path):
    root = make_root("worktree-config-foreign", tmp_path)
    assert canonical_root_problem(root) == (
        "its Git config is refused: it enables per-worktree config"
    )


def test_continuation_joins_the_origin_before_it_is_judged(tmp_path):
    root = make_root("continuation-foreign", tmp_path)
    assert canonical_root_problem(root) == (
        "its origin 'https://github.com/TheAxiomFoundation/rulespec-us-fork' "
        "is not TheAxiomFoundation/rulespec-us on github.com"
    )


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(
    url=st.sampled_from([
        CANONICAL_ORIGIN,
        FORK_ORIGIN,
        "git@github.com:TheAxiomFoundation/rulespec-us.git",
        "https://github.com/TheAxiomFoundation/rulespec-us-fork",
    ]),
    data=st.data(),
)
def test_a_continuation_anywhere_in_the_origin_reads_as_unsplit(url, data):
    """Invariant: a backslash-newline inside a value changes nothing.

    git-config(1) joins the line to the next, so the parsed origin, and the
    verdict on it, match the unsplit config wherever the split falls.
    """
    from axiom_oracles.rulespec_roots import _canonical_origin, _parse_git_config

    cuts = sorted(set(data.draw(st.lists(st.integers(0, len(url)), max_size=3))))
    pieces = [url[a:b] for a, b in zip([0, *cuts], [*cuts, len(url)])]
    split = "\\\n".join(pieces)
    whole = _parse_git_config(f'[remote "origin"]\n\turl = {url}\n')
    joined = _parse_git_config(f'[remote "origin"]\n\turl = {split}\n')
    assert joined == whole == [("remote", "origin", "url", url)]
    assert _canonical_origin(joined[0][3], "rulespec-us") == _canonical_origin(
        url, "rulespec-us"
    )


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
    return engine, refused, root


#: Paths that hand the offered root over directly (always checked), as
#: opposed to treating a non-country name as a workspace to search.
DIRECT_PATHS = {"compile_with_engine", "tax_populace", "snap_axiom_rules_env"}


def expected_refusal(path_name: str, root: Path) -> bool:
    return path_name in DIRECT_PATHS or bool(CANONICAL_ROOT_NAME.fullmatch(root.name))


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
    engine, refused, root = _drive(path_name, kind, old, tmp_path, monkeypatch)
    _assert_only_canonical_reached(engine)
    assert kind not in engine.sentinels()
    # A root named rulespec-<cc>, or one a path hands over directly, is
    # refused with an error. A directory with another name is read as a
    # workspace and contributes only its canonical children (none here).
    assert refused == expected_refusal(path_name, root), (
        "expected a NonCanonicalRuleSpecRoot" if not refused else "expected a skip"
    )
    if refused:
        assert engine.commands == [], "a refused root must stop before the engine runs"


@pytest.mark.parametrize("old", [False, True], ids=["engine-main", "pre-flag-engine"])
@pytest.mark.parametrize("kind", CANONICAL_KINDS)
@pytest.mark.parametrize("path_name", sorted(RUNTIME_PATHS))
def test_runtime_paths_reach_the_canonical_root_control(
    path_name, kind, old, tmp_path, monkeypatch
):
    engine, refused, _ = _drive(path_name, kind, old, tmp_path, monkeypatch)
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


@settings(max_examples=120, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(owner=st.sampled_from(["TheAxiomFoundation", "theaxiomfoundation",
                              "THEAXIOMFOUNDATION", "evil", "TheAxiomFoundation-fork"]),
       repo=st.sampled_from(["rulespec-us", "RuleSpec-US", "rulespec-uk",
                             "rulespec-us-co", "custom", "RULESPEC-us"]),
       host=st.sampled_from(["github.com", "GitHub.com", "gitlab.com", "github.com.evil.io"]),
       form=st.sampled_from(["https://{h}/{o}/{r}.git", "git@{h}:{o}/{r}.git",
                             "ssh://git@{h}/{o}/{r}.git", "https://{h}/{o}/{r}",
                             "https://{h}/{o}/{r}/", "http://{h}/{o}/{r}.git",
                             "git://{h}/{o}/{r}.git", "https://{h}/x/{o}/{r}.git"]))
def test_property_origin_must_be_the_canonical_github_repository(
    owner, repo, host, form, tmp_path
):
    """Only TheAxiomFoundation/rulespec-us on github.com over https or ssh."""
    url = form.format(h=host, o=owner, r=repo)
    root = tmp_path / f"o{abs(hash(url))}" / "rulespec-us"
    git_dir = root / ".git"
    for sub in ("objects", "refs"):
        (git_dir / sub).mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir / "config").write_text(f'[remote "origin"]\n\turl = {url}\n')
    expected = (
        owner.casefold() == "theaxiomfoundation"
        and repo.casefold() == "rulespec-us"
        and host.casefold() == "github.com"
        and not form.startswith(("http://", "git://"))
        and "/x/" not in form
    )
    assert (canonical_root_problem(root) is None) == expected, url


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
        # Reference: the same discovery over the paths as given, each kept
        # only when the definition accepts it under the name it was given.
        expected: list[Path] = []
        for candidate in candidates:
            named = CANONICAL_ROOT_NAME.fullmatch(candidate.name)
            offered = [candidate] if named else sorted(candidate.glob("rulespec-*"))
            for path in offered:
                if CANONICAL_ROOT_NAME.fullmatch(path.name) and path.is_dir():
                    if canonical_root_problem(path) is None:
                        if path.resolve() not in expected:
                            expected.append(path.resolve())
        assert runtime == expected
        assert set(runtime) <= set(declared)
        assert all(canonical_root_problem(root) is None for root in runtime)

    check()


_REFERENCE_ORIGIN = re.compile(
    r"(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"theaxiomfoundation/rulespec-us(?:\.git)?/?",
    re.IGNORECASE,
)


def _git_cli_problem(path: Path) -> bool:
    """Reference: does the ``git`` binary disqualify this directory?

    Independent of the module under test: git finds the work tree and the
    origin (applying includes and URL rewrites), and a regex decides whether
    that origin is the canonical repository. User and system config are off.
    """
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    resolved = path.resolve()
    top = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, env=env,
    )
    if top.returncode != 0:
        return False
    if Path(top.stdout.strip()).resolve() != resolved:
        return True
    origin = subprocess.run(
        ["git", "-C", str(resolved), "remote", "get-url", "origin"],
        capture_output=True, text=True, env=env,
    )
    if origin.returncode != 0:
        return False
    return _REFERENCE_ORIGIN.fullmatch(origin.stdout.strip()) is None


@pytest.mark.parametrize("kind", (*CANONICAL_KINDS, *NON_CANONICAL_KINDS))
def test_differential_filesystem_git_check_matches_the_git_binary(kind, tmp_path):
    """The filesystem reader and the git CLI agree on every fixture."""
    root = make_root(kind, tmp_path)
    if CANONICAL_ROOT_NAME.fullmatch(root.resolve().name) is None:
        pytest.skip("the name check decides before Git is consulted")
    if (root.resolve() / root.resolve().name).exists():
        pytest.skip("the nested-name check decides before Git is consulted")
    if CANONICAL_ROOT_NAME.fullmatch(root.name) and root.name != root.resolve().name:
        pytest.skip("the given-name check decides before Git is consulted")
    assert (canonical_root_problem(root) is not None) == _git_cli_problem(root)


# --------------------------------------------------------------------------- #
# Checks the runtime matrix reaches only indirectly
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", NON_CANONICAL_KINDS)
def test_stage_pure_root_refuses_a_non_canonical_source(kind, tmp_path):
    root = make_root(kind, tmp_path / "roots")
    stage = tmp_path / "stage"
    with pytest.raises(NonCanonicalRuleSpecRoot):
        engine_compat.stage_pure_root(root, {"us-co"}, stage)
    assert not stage.exists() or not any(stage.rglob("fixture.yaml"))


@pytest.mark.parametrize("kind", CANONICAL_KINDS)
def test_stage_pure_root_copies_a_canonical_source(kind, tmp_path):
    root = make_root(kind, tmp_path / "roots")
    staged = engine_compat.stage_pure_root(root, {"us-co"}, tmp_path / "stage")
    assert (staged / FIXTURE).read_text().strip() == kind
    assert sorted(child.name for child in staged.iterdir()) == ["us-co"]


def _snap_qc_overlay_run(monkeypatch, tmp_path, overlay_root):
    """Run the SNAP QC comparison with stubbed data, returning the run env."""
    from types import SimpleNamespace

    from axiom_oracles.bridges import snap_qc_compare as sc
    from axiom_oracles.populations import snap_qc

    binary = tmp_path / "engine" / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"fake engine")
    monkeypatch.setattr(sc, "resolve_workspace_root", lambda _: tmp_path)
    monkeypatch.setattr(sc, "resolve_axiom_binary", lambda _root, value: value)
    monkeypatch.setattr(sc, "load_overlay_spec", lambda _: SimpleNamespace(module_id_rewrites={}))
    monkeypatch.setattr(snap_qc, "load_qc_units", lambda *a, **k: ([], None))
    monkeypatch.setattr(sc, "load_base_inputs", lambda _: {})
    monkeypatch.setattr(sc, "_load_base_member", lambda *a: {})
    monkeypatch.setattr(sc, "sua_amounts_from_overlay", lambda *a: {})
    # What axiom_rules_env could hand back if it regressed: an inherited list.
    monkeypatch.setattr(sc, "axiom_rules_env", lambda *a: {
        "AXIOM_RULESPEC_REPO_ROOTS": str(tmp_path / "ambient"),
        "AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE": "1",
        "UNRELATED": "kept",
    })
    monkeypatch.setattr(sc, "build_overlay", lambda *a: SimpleNamespace(
        program_path=overlay_root / "us-co" / "program.yaml",
        overlay_root=overlay_root,
        provenance={"fixture": "overlay env"},
    ))
    seen = {}

    def run_cases(**kwargs):
        seen["env"] = dict(kwargs["env"])
        return []

    monkeypatch.setattr(sc, "_run_cases", run_cases)
    sc.run_snap_qc_comparison(
        fiscal_year=2024, jurisdiction="us-co", axiom_binary=binary,
        rulespec_root=tmp_path / "rulespec-us",
    )
    return seen.get("env")


def test_snap_qc_overlay_env_lists_only_the_overlay_root(monkeypatch, tmp_path):
    overlay_root = tmp_path / "overlay" / "rulespec-us"
    overlay_root.mkdir(parents=True)
    env = _snap_qc_overlay_run(monkeypatch, tmp_path, overlay_root)
    assert env["AXIOM_RULESPEC_REPO_ROOTS"] == str(overlay_root.resolve())
    assert "AXIOM_RULESPEC_REPO_ROOTS_EXCLUSIVE" not in env
    assert env["UNRELATED"] == "kept"


def test_snap_qc_overlay_env_refuses_a_non_canonical_overlay(monkeypatch, tmp_path):
    overlay_root = tmp_path / "overlay" / "snap-qc-overlay"
    overlay_root.mkdir(parents=True)
    with pytest.raises(NonCanonicalRuleSpecRoot):
        _snap_qc_overlay_run(monkeypatch, tmp_path, overlay_root)


@pytest.mark.parametrize("child", ["programs", ".git", "uk", "usa", "tools"])
def test_content_root_accepts_only_jurisdiction_directories(child, tmp_path):
    from axiom_oracles.rulespec_roots import require_canonical_content_root

    root = make_root("git", tmp_path)
    (root / child).mkdir(exist_ok=True)
    with pytest.raises(NonCanonicalRuleSpecRoot):
        require_canonical_content_root(root / child)
    with pytest.raises(NonCanonicalRuleSpecRoot):
        _rulespec_repo_alias_parent(root / child)
    for jurisdiction in ("us", "us-co", "us-ny-nyc"):
        (root / jurisdiction).mkdir(exist_ok=True)
        assert require_canonical_content_root(root / jurisdiction) == root.resolve()
