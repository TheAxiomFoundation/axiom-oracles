"""Source attestations always follow executable bytes, including cache hits."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner, _select_candidate_result
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult
from axiom_oracles.engine_identity import (
    ENGINE_RECEIPT_OUTPUT_ENV,
    ENGINE_REPOSITORY,
    EngineIdentityError,
    build_engine_binary,
    engine_binding_receipt_path,
    engine_receipt,
    ensure_engine_binary,
    main,
    record_engine_receipt,
)


COMMIT = "32bc1c124724ebbb2187a196a3b228cfb2a14721"
PROPERTY_SETTINGS = settings(max_examples=75, deadline=None, derandomize=True)


def _write_binding(binary: Path, **updates) -> None:
    payload = {
        "engine_commit": COMMIT,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "version": "0.1.0",
    }
    payload.update(updates)
    engine_binding_receipt_path(binary).write_text(json.dumps(payload))


@PROPERTY_SETTINGS
@given(payload=st.binary(max_size=4096))
def test_runtime_receipt_hashes_the_executed_file(tmp_path_factory, payload):
    binary = tmp_path_factory.mktemp("executed-bytes") / "axiom-rules-engine"
    binary.write_bytes(payload)
    _write_binding(binary)
    observed = []

    def execute(args, **kwargs):
        observed.append(hashlib.sha256(Path(args[0]).read_bytes()).hexdigest())
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    runner = AxiomRulesRunner(binary_path=binary, subprocess_run=execute)
    runner._execute_engine([str(binary), "run-compiled"])
    assert runner.engine_receipt["binary_sha256"] == hashlib.sha256(payload).hexdigest()
    assert observed == [runner.engine_receipt["binary_sha256"]]
    assert runner.engine_receipt["commit"] == COMMIT


@PROPERTY_SETTINGS
@given(payload=st.binary(max_size=4096))
def test_snap_replay_cache_hit_receipts_its_own_bytes(tmp_path_factory, payload):
    root = tmp_path_factory.mktemp("snap-cache")
    original = root / "build" / "axiom-rules-engine"
    original.parent.mkdir()
    original.write_bytes(payload)
    _write_binding(original)
    cached = root / "restored" / "axiom-rules-engine"
    cached.parent.mkdir()
    shutil.copyfile(original, cached)
    shutil.copyfile(
        engine_binding_receipt_path(original), engine_binding_receipt_path(cached)
    )
    original.write_bytes(b"a checkout's newer binary")
    receipt = engine_receipt(cached)
    assert receipt["binary_sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["commit"] == COMMIT
    assert receipt["binary"] == str(cached)


def test_binary_without_binding_never_borrows_neighboring_checkout(tmp_path):
    binary = tmp_path / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"unreceipted binary")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text(COMMIT + "\n")
    receipt = engine_receipt(binary)
    assert receipt["commit"] is None
    assert receipt["axiom_rules_engine_sha"] is None
    assert receipt["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert receipt["source_status"].startswith("unresolved")


@pytest.mark.parametrize("updates", [
    {"engine_commit": "abc"},
    {"engine_commit": "z" * 40},
    {"binary_sha256": "0" * 64},
    {"binary_sha256": "abcd"},
    {"repository": "another/engine"},
])
def test_unverifiable_sidecars_leave_commit_unresolved(tmp_path, updates):
    binary = tmp_path / "axiom-rules-engine"
    binary.write_bytes(b"executable bytes")
    _write_binding(binary, **updates)
    receipt = engine_receipt(binary)
    assert receipt["commit"] is None
    assert receipt["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()


def test_tampered_cache_never_reuses_a_stale_source_identity(tmp_path):
    binary = tmp_path / "axiom-rules-engine"
    binary.write_bytes(b"original engine")
    _write_binding(binary)
    binary.write_bytes(b"replaced engine")
    receipt = engine_receipt(binary)
    assert receipt["commit"] is None
    assert receipt["binary_sha256"] == hashlib.sha256(b"replaced engine").hexdigest()


def test_runner_rejects_binary_replaced_during_execution(tmp_path):
    binary = tmp_path / "axiom-rules-engine"
    binary.write_bytes(b"original")

    def replace(args, **kwargs):
        binary.write_bytes(b"replacement")
        return subprocess.CompletedProcess(args, 0)

    runner = AxiomRulesRunner(binary_path=binary, subprocess_run=replace)
    with pytest.raises(EngineIdentityError, match="changed during execution"):
        runner._execute_engine([str(binary), "run-compiled"])


def test_runner_rejects_binary_replaced_between_invocations(tmp_path):
    binary = tmp_path / "axiom-rules-engine"
    binary.write_bytes(b"original")
    runner = AxiomRulesRunner(
        binary_path=binary,
        subprocess_run=lambda args, **kwargs: subprocess.CompletedProcess(args, 0),
    )
    runner._execute_engine([str(binary), "compile"])
    binary.write_bytes(b"replacement")
    with pytest.raises(EngineIdentityError, match="changed during this oracle run"):
        runner._execute_engine([str(binary), "run-compiled"])


def test_path_receipt_and_execution_choose_same_executable(tmp_path, monkeypatch):
    binary = tmp_path / "axiom-rules"
    binary.write_bytes(b"PATH engine bytes")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    commands = []

    def execute(args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, 0)

    runner = AxiomRulesRunner(binary_path="axiom-rules", subprocess_run=execute)
    runner._execute_engine(["axiom-rules", "run-compiled"])
    assert commands[0][0] == str(binary)
    assert runner.engine_receipt["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()


@pytest.mark.parametrize("selection", [
    None,
    {"strategy": "max", "output": "amount"},
    {"strategy": "unsupported", "output": "amount"},
])
def test_candidate_selection_preserves_execution_receipt(tmp_path, selection):
    binary = tmp_path / "engine"
    binary.write_bytes(b"candidate engine")
    receipt = engine_receipt(binary)
    case = Case(
        case_id="case", period="2026",
        metadata={"axiom_result_selection": selection} if selection else {},
    )
    candidates = [EngineResult(
        engine="axiom", household_id="case", values={"amount": value},
        raw={"engine_receipt": dict(receipt)},
    ) for value in (1, 2)]
    result = _select_candidate_result("axiom", case, candidates)
    assert result.raw["engine_receipt"] == receipt


def _source_repo(root: Path) -> Path:
    root.mkdir()
    (root / "Cargo.toml").write_text('[package]\nname = "axiom-rules-engine"\nversion = "0.3.0"\n')
    (root / ".gitignore").write_text("/target/\n")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "Cargo.toml", ".gitignore"], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Oracle test",
        "-c", "user.email=oracle@example.test", "-c", "commit.gpgsign=false",
        "commit", "--quiet", "-m", "Engine fixture",
    ], check=True)
    return root


def test_observed_build_binds_clean_source_and_exact_output(tmp_path):
    repo = _source_repo(tmp_path / "source")
    binary = repo / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"stale cached executable")
    calls = []

    def build(command, **kwargs):
        assert not binary.exists()
        assert kwargs["cwd"] == repo
        assert kwargs["env"]["CARGO_TARGET_DIR"] == str(repo / "target")
        assert kwargs["timeout"] == 600
        calls.append(command)
        binary.write_bytes(b"built from observed source")

    receipt = build_engine_binary(repo, binary, ["cargo", "build", "-j", "4"], run=build)
    expected_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert calls == [["cargo", "build", "-j", "4"]]
    assert receipt["repository"] == ENGINE_REPOSITORY
    assert receipt["commit"] == expected_commit
    assert receipt["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert receipt["working_tree"] == "clean"
    assert receipt["version"] == "0.3.0"


def test_successful_build_cannot_receipt_a_stale_output(tmp_path):
    repo = _source_repo(tmp_path / "source")
    binary = repo / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"stale")
    with pytest.raises(EngineIdentityError, match="no readable executable"):
        build_engine_binary(repo, binary, ["cargo", "build"], run=lambda *a, **kw: None)
    assert not engine_binding_receipt_path(binary).exists()


def test_build_rejects_dirty_source_before_invocation(tmp_path):
    repo = _source_repo(tmp_path / "source")
    (repo / "Cargo.toml").write_text("modified source\n")
    with pytest.raises(EngineIdentityError, match="clean"):
        build_engine_binary(repo, repo / "target" / "binary", ["cargo", "build"])


def test_build_rejects_changes_hidden_by_assume_unchanged(tmp_path):
    repo = _source_repo(tmp_path / "source")
    subprocess.run([
        "git", "-C", str(repo), "update-index", "--assume-unchanged", "Cargo.toml",
    ], check=True)
    (repo / "Cargo.toml").write_text("hidden source modification\n")
    assert not subprocess.check_output([
        "git", "-C", str(repo), "status", "--porcelain",
    ], text=True).strip()
    with pytest.raises(EngineIdentityError, match="clean"):
        build_engine_binary(repo, repo / "target" / "binary", ["cargo", "build"])


def test_build_ignores_inherited_git_repository_selectors(tmp_path, monkeypatch):
    repo = _source_repo(tmp_path / "source")
    other = _source_repo(tmp_path / "unrelated")
    # Hook environments commonly export these selectors; they must affect
    # neither our identity checks nor build scripts that themselves call Git.
    selectors = {
        "GIT_DIR": str(other / ".git"),
        "GIT_WORK_TREE": str(other),
        "GIT_INDEX_FILE": str(other / ".git" / "index"),
        "GIT_COMMON_DIR": str(other / ".git"),
    }
    for key, value in selectors.items():
        monkeypatch.setenv(key, value)
    binary = repo / "target" / "release" / "axiom-rules-engine"

    def build(*args, **kwargs):
        assert not selectors.keys() & kwargs["env"].keys()
        assert kwargs["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"correct source output")

    receipt = build_engine_binary(repo, binary, ["cargo", "build"], run=build)
    assert receipt["commit"] is not None
    assert receipt["working_tree"] == "clean"


def test_build_rejects_source_modified_during_build(tmp_path):
    repo = _source_repo(tmp_path / "source")
    binary = repo / "target" / "release" / "axiom-rules-engine"

    def build(*args, **kwargs):
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"unprovable output")
        (repo / "Cargo.toml").write_text("source changed while compiling\n")

    with pytest.raises(EngineIdentityError, match="clean"):
        build_engine_binary(repo, binary, ["cargo", "build"], run=build)
    assert not engine_binding_receipt_path(binary).exists()



def _head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


# Every cache state a build step can restore, against a clean or dirty checkout.
CACHE_STATES = list(itertools.product(
    [False, True], ["none", "head", "older", "mismatched"], [False, True]
))


@pytest.mark.parametrize("exists,receipt,dirty", [
    state for state in CACHE_STATES if state[0] or state[1] == "none"
])
def test_ensure_reuses_only_a_binary_receipted_for_the_clean_head(tmp_path, exists, receipt, dirty):
    repo = _source_repo(tmp_path / "source")
    binary = repo / "target" / "release" / "axiom-rules-engine"
    head = _head(repo)
    if exists:
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"restored from a build cache")
        if receipt == "head":
            _write_binding(binary, engine_commit=head)
        elif receipt == "older":
            _write_binding(binary)
        elif receipt == "mismatched":
            _write_binding(binary, engine_commit=head, binary_sha256="0" * 64)
    if dirty:
        (repo / "Cargo.toml").write_text("modified source\n")
    calls = []

    def build(command, **kwargs):
        calls.append(command)
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"built from observed source")

    if dirty and not exists:
        with pytest.raises(EngineIdentityError, match="clean"):
            ensure_engine_binary(repo, binary, ["cargo", "build"], run=build)
        assert calls == []
        return
    result = ensure_engine_binary(repo, binary, ["cargo", "build"], run=build)
    rebuilt = not exists or (not dirty and receipt != "head")
    assert calls == ([["cargo", "build"]] if rebuilt else [])
    assert result["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    if dirty:
        # A dirty checkout keeps its binary and whatever identity it carries.
        assert result["commit"] == {"head": head, "older": COMMIT}.get(receipt)
    else:
        # A clean checkout always yields an executable receipted for its HEAD.
        assert result["commit"] == head
        assert result["source_status"] == "verified build receipt"


def test_comparison_runner_rebuilds_an_unreceipted_cached_engine(tmp_path, capsys):
    source = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("engine_identity_run_comparison", source)
    run_comparison = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(run_comparison)
    repo = _source_repo(tmp_path / "source")
    binary = repo / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"restored without a receipt")
    calls = []

    def build(command, **kwargs):
        calls.append(command)
        binary.write_bytes(b"built from observed source")

    run_comparison.subprocess = type("FakeSubprocess", (), {"run": staticmethod(build)})
    receipt = run_comparison._ensure_engine_binary(repo, kind="release")
    assert calls == [["cargo", "build", "--locked", "--jobs", "4", "--bin", "axiom-rules-engine", "--release"]]
    assert receipt["commit"] == _head(repo)
    assert "Building release axiom-rules-engine" in capsys.readouterr().out
    calls.clear()
    assert run_comparison._ensure_engine_binary(repo, kind="release")["commit"] == _head(repo)
    assert calls == []


def test_inspect_cli_rejects_unreceipted_cache_hit(tmp_path, capsys):
    binary = tmp_path / "axiom-rules-engine"
    binary.write_bytes(b"old cached binary")
    with pytest.raises(SystemExit) as exc:
        main(["inspect", str(binary), "--expect-commit", COMMIT])
    assert exc.value.code == 2
    assert "no verified receipt" in capsys.readouterr().err
    _write_binding(binary)
    assert main(["inspect", str(binary), "--expect-commit", COMMIT]) == 0
    assert json.loads(capsys.readouterr().out)["commit"] == COMMIT


def test_execution_journal_is_optional(tmp_path, monkeypatch):
    monkeypatch.delenv(ENGINE_RECEIPT_OUTPUT_ENV, raising=False)
    record_engine_receipt({"commit": COMMIT, "binary_sha256": "a" * 64})
    assert not list(tmp_path.iterdir())


def test_execution_journal_preserves_runtime_receipt(tmp_path, monkeypatch):
    output = tmp_path / "private-run" / "engine-receipt.json"
    monkeypatch.setenv(ENGINE_RECEIPT_OUTPUT_ENV, str(output))
    binary = tmp_path / "binary"
    binary.write_bytes(b"executed generator engine")
    _write_binding(binary)
    receipt = engine_receipt(binary)
    record_engine_receipt(receipt)
    assert json.loads(output.read_text()) == receipt
    # Different cached file locations do not change identity.
    moved = {**receipt, "binary": "/another/cache/engine"}
    record_engine_receipt(moved)
    assert json.loads(output.read_text()) == moved


@pytest.mark.parametrize("field,replacement", [
    ("commit", "e" * 40), ("binary_sha256", "f" * 64),
])
def test_execution_journal_rejects_disagreement(tmp_path, monkeypatch, field, replacement):
    output = tmp_path / "engine-receipt.json"
    monkeypatch.setenv(ENGINE_RECEIPT_OUTPUT_ENV, str(output))
    original = {"commit": COMMIT, "binary_sha256": "a" * 64}
    record_engine_receipt(original)
    with pytest.raises(EngineIdentityError, match="identities disagree"):
        record_engine_receipt({**original, field: replacement})
    assert json.loads(output.read_text()) == original


@pytest.mark.parametrize("contents", [b"invalid JSON", b"[]", b"x" * 65537])
def test_execution_journal_rejects_malformed_existing_evidence(tmp_path, monkeypatch, contents):
    output = tmp_path / "engine-receipt.json"
    output.write_bytes(contents)
    monkeypatch.setenv(ENGINE_RECEIPT_OUTPUT_ENV, str(output))
    with pytest.raises(EngineIdentityError, match="journal is malformed"):
        record_engine_receipt({"commit": COMMIT, "binary_sha256": "a" * 64})
    assert output.read_bytes() == contents


@pytest.mark.parametrize("command", ["compile", "run-compiled"])
@pytest.mark.parametrize("returncode", [0, 1])
def test_runner_journals_successful_and_failed_invocations(
    tmp_path, monkeypatch, command, returncode,
):
    output = tmp_path / "engine-receipt.json"
    monkeypatch.setenv(ENGINE_RECEIPT_OUTPUT_ENV, str(output))
    binary = tmp_path / "binary"
    binary.write_bytes(b"generator engine")
    _write_binding(binary)
    runner = AxiomRulesRunner(
        binary_path=binary,
        subprocess_run=lambda args, **kwargs: subprocess.CompletedProcess(args, returncode),
    )
    runner._execute_engine([str(binary), command])
    assert json.loads(output.read_text()) == runner.engine_receipt


def test_runner_never_journals_changed_executable(tmp_path, monkeypatch):
    output = tmp_path / "engine-receipt.json"
    monkeypatch.setenv(ENGINE_RECEIPT_OUTPUT_ENV, str(output))
    binary = tmp_path / "binary"
    binary.write_bytes(b"original bytes")

    def execute(args, **kwargs):
        binary.write_bytes(b"changed while executing")
        return subprocess.CompletedProcess(args, 0)

    runner = AxiomRulesRunner(binary_path=binary, subprocess_run=execute)
    with pytest.raises(EngineIdentityError, match="changed during execution"):
        runner._execute_engine([str(binary), "run-compiled"])
    assert not output.exists()
