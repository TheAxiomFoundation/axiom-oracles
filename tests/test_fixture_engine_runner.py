"""Engine selection and receipts for the fixture-backed grid runners (#675).

The SNAP boundary and federal tax-liability runners build the engine revision
the rulespec snapshot pins, hand the receipted executable to the generator,
and record the receipt as the report's engine identity. Without that receipt
``check_publications`` refuses the refreshed report.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
PIN = "1" * 40


def _runner():
    path = REPO_ROOT / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("fixture_engine_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = _runner()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    return path


def _commit(repo: Path, files: dict[str, str], message: str = "c") -> str:
    for relpath, text in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


def test_pin_comes_from_the_workflow_toolchain_first(tmp_path):
    root = _repo(tmp_path / "rulespec-us")
    _commit(
        root,
        {
            ".axiom/workflow-toolchain.toml": (
                f'[workflow_toolchain]\naxiom_rules_engine_ref = "{PIN}"\n'
            ),
            ".axiom/toolchain.toml": (
                f'[toolchain]\naxiom_rules_engine_ref = "{"2" * 40}"\n'
            ),
        },
    )
    assert RUNNER._rulespec_engine_pin(root) == PIN


def test_pin_falls_back_to_the_older_toolchain_file(tmp_path):
    root = _repo(tmp_path / "rulespec-us")
    _commit(
        root,
        {
            ".axiom/workflow-toolchain.toml": "[workflow_toolchain]\n",
            ".axiom/toolchain.toml": f'[toolchain]\naxiom_rules_engine_ref = "{PIN}"\n',
        },
    )
    assert RUNNER._rulespec_engine_pin(root) == PIN


def test_pin_is_read_from_head_not_the_work_tree(tmp_path):
    root = _repo(tmp_path / "rulespec-us")
    _commit(root, {".axiom/toolchain.toml": f'[toolchain]\naxiom_rules_engine_ref = "{PIN}"\n'})
    (root / ".axiom/toolchain.toml").write_text(
        f'[toolchain]\naxiom_rules_engine_ref = "{"3" * 40}"\n'
    )
    assert RUNNER._rulespec_engine_pin(root) == PIN


@pytest.mark.parametrize(
    "text",
    ["[toolchain]\n", '[toolchain]\naxiom_rules_engine_ref = "main"\n'],
)
def test_a_missing_or_malformed_pin_fails(tmp_path, text):
    root = _repo(tmp_path / "rulespec-us")
    _commit(root, {".axiom/toolchain.toml": text})
    with pytest.raises(SystemExit, match="axiom_rules_engine_ref"):
        RUNNER._rulespec_engine_pin(root)


def test_engine_checkout_uses_a_worktree_at_the_pin(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    engine = _repo(tmp_path / "axiom-rules")
    pinned = _commit(engine, {"src.rs": "old\n"}, "pinned")
    head = _commit(engine, {"src.rs": "new\n"}, "main")

    checkout = RUNNER._engine_checkout_at(engine.resolve(), pinned)

    assert checkout != engine.resolve()
    assert _git(checkout, "rev-parse", "HEAD") == pinned
    assert (checkout / "src.rs").read_text() == "old\n"
    # The configured checkout never moves, and a second run reuses the tree.
    assert _git(engine, "rev-parse", "HEAD") == head
    assert RUNNER._engine_checkout_at(engine.resolve(), pinned) == checkout
    # When the configured checkout is the pin, it is used directly.
    assert RUNNER._engine_checkout_at(engine.resolve(), head) == engine.resolve()


def test_runner_records_the_pinned_engines_receipt(tmp_path, monkeypatch):
    receipt = {"commit": PIN, "binary_sha256": "d" * 64, "binary_path": "/e"}
    engine = tmp_path / "axiom-rules"
    engine.mkdir()
    calls = []
    monkeypatch.setattr(RUNNER, "_rulespec_engine_pin", lambda _root: PIN)
    monkeypatch.setattr(
        RUNNER,
        "_engine_checkout_at",
        lambda repo, revision: calls.append((repo, revision)) or tmp_path / "wt",
    )
    monkeypatch.setattr(
        RUNNER,
        "_ensure_engine_binary",
        lambda repo, *, kind: calls.append((repo, kind)) or receipt,
    )
    assert (
        RUNNER._fixture_engine_receipt(
            {"axiom_rules_repo": str(engine)}, tmp_path / "rulespec-us"
        )
        is receipt
    )
    assert calls == [(engine.resolve(), PIN), (tmp_path / "wt", "release")]


def test_runner_refuses_a_build_receipted_for_another_commit(tmp_path, monkeypatch):
    engine = tmp_path / "axiom-rules"
    engine.mkdir()
    monkeypatch.setattr(RUNNER, "_rulespec_engine_pin", lambda _root: PIN)
    monkeypatch.setattr(RUNNER, "_engine_checkout_at", lambda repo, revision: repo)
    monkeypatch.setattr(
        RUNNER,
        "_ensure_engine_binary",
        lambda repo, *, kind: {"commit": None, "binary_sha256": "d" * 64},
    )
    with pytest.raises(SystemExit, match="not the pinned"):
        RUNNER._fixture_engine_receipt(
            {"axiom_rules_repo": str(engine)}, tmp_path / "rulespec-us"
        )


def test_every_fixture_grid_suite_names_an_engine_checkout():
    import yaml

    suites = [
        yaml.safe_load(path.read_text())
        for path in sorted((REPO_ROOT / "comparisons").glob("us-*.yaml"))
    ]
    grids = [
        suite
        for suite in suites
        if suite["runner"]["type"]
        in {"federal-tax-liability-grid", "snap-abawd-boundary-grid"}
    ]
    assert len(grids) == 12
    assert all(suite["runner"].get("axiom_rules_repo") for suite in grids)


@pytest.mark.parametrize(
    "runner_type", ["federal-tax-liability-grid", "snap-abawd-boundary-grid"]
)
def test_a_receipted_grid_run_stamps_a_publishable_engine_identity(
    tmp_path, runner_type, fake_rules_engine
):
    """The receipt the runner records becomes provenance.engine, which
    check_publications requires to carry a 40-hex commit and 64-hex digest.
    Without it the block falls back to an engine identity with neither."""
    from axiom_oracles.engine_identity import engine_receipt

    receipt = engine_receipt(fake_rules_engine({}, {}))
    output = tmp_path / "report.json"
    output.write_text('{"suite": "grid"}')

    def block(runner_extra):
        config = {
            "name": "grid",
            "runner": {
                "type": runner_type,
                "axiom_rules_repo": str(tmp_path),
                "parameters": {},
                **runner_extra,
            },
        }
        return RUNNER._build_run_provenance(config, runner_type, output)["engine"]

    engine = block({"_engine_receipt": receipt})
    assert engine["commit"] == "a" * 40
    assert engine["binary_sha256"] == fake_rules_engine.digest
    unreceipted = block({})
    assert unreceipted["commit"] is None and unreceipted["binary_sha256"] is None
