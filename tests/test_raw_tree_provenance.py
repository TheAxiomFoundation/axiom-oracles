"""Raw tracked rules must remain visible through Git's content transformations.

Git's clean representation can equal HEAD while the runner reads other bytes.
The provenance invariant is that those raw bytes cannot be recorded clean,
and the actual weekly publication path must refuse their report.
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

from axiom_oracles.provenance import worktree_state

_HEAD_RULE = b"rate: 0.18\n"
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
    ):
        monkeypatch.delenv(key, raising=False)


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    ).stdout


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    (path / "rule.yaml").write_bytes(_HEAD_RULE)
    _git(path, "add", "rule.yaml")
    _git(path, "commit", "-q", "-m", "seed")
    return path


def _clean_filter(repo: Path) -> None:
    # Reuse the review's Git clean-filter probe; generalize its rate mapping
    # so the property can generate many different executed rates.
    (repo / ".git/info/attributes").write_text("*.yaml filter=vat\n")
    _git(repo, "config", "filter.vat.clean", "sed 's/^rate:.*/rate: 0.18/'")


def _normalized_edit(repo: Path, mechanism: str) -> bytes:
    rule = repo / "rule.yaml"
    if mechanism == "crlf":
        (repo / ".git/info/attributes").write_text("*.yaml text eol=crlf\n")
        raw = b"rate: 0.18\r\n"
        rule.write_bytes(raw)
        # Refresh the normalized index stat data: HEAD and the index still
        # contain LF bytes, while a clean checkout's on-disk bytes are CRLF.
        _git(repo, "add", "rule.yaml")
        assert _git(repo, "diff", "--cached") == b""
    else:
        _clean_filter(repo)
        raw = b"rate: 0.17\n"
        if mechanism == "smudge-filter":
            _git(repo, "config", "filter.vat.smudge", "sed 's/0.18/0.17/g'")
            rule.unlink()
            _git(repo, "checkout", "--", "rule.yaml")
        else:
            rule.write_bytes(raw)
    assert rule.read_bytes() == raw
    assert raw != _git(repo, "show", "HEAD:rule.yaml")
    assert _git(repo, "status", "--porcelain", "--untracked-files=no") == b""
    return raw


def _weekly_suite(tmp_path: Path, monkeypatch, repo: Path):
    script = Path(__file__).parents[1] / "scripts/run_comparison.py"
    spec = importlib.util.spec_from_file_location("raw_tree_run_comparison", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "rw-vat.yaml").write_text(
        "name: rw-vat\n"
        "runner:\n"
        "  type: raw-rw\n"
        "  parameters:\n"
        "    sample_size: 0\n"
        f"    rulespec_roots: [{json.dumps(str(repo))}]\n"
        "artifacts:\n"
        "  report_basename: rw-vat\n"
        "dashboard:\n"
        "  filename: rw-vat.json\n"
    )
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    output_dir = tmp_path / "reports"
    executed = []

    def runner(_config, output):
        executed.append((repo / "rule.yaml").read_bytes())
        output.write_text(json.dumps({"compared_values": 1, "mismatch_count": 0}))

    monkeypatch.setattr(module, "COMPARISONS_DIR", comparisons)
    monkeypatch.setattr(module, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setitem(module.RUNNERS, "raw-rw", runner)
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "weekly")
    monkeypatch.setattr(
        "sys.argv", ["run_comparison.py", "rw-vat", "--output-dir", str(output_dir)]
    )
    return module, output_dir, dashboard, executed


@pytest.mark.parametrize("mechanism", ["clean-filter", "smudge-filter", "crlf"])
def test_weekly_refuses_raw_changes_hidden_by_git_normalization(
    tmp_path, monkeypatch, mechanism
):
    """Even Git-clean transformed bytes are refused before either publication."""
    repo = _repo(tmp_path / "rulespec-rw")
    raw = _normalized_edit(repo, mechanism)
    module, output_dir, dashboard, executed = _weekly_suite(tmp_path, monkeypatch, repo)

    with pytest.raises(SystemExit, match="rw-vat: weekly run refused before publication"):
        module.main()

    assert executed == [raw], "the runner must actually read the transformed rules"
    assert worktree_state(repo)["dirty"] is True
    assert list(output_dir.iterdir()) == [], "report or private staging file was published"
    assert list(dashboard.iterdir()) == [], "dashboard copy was published"


def test_filter_config_alone_keeps_an_identical_tree_publishable(tmp_path, monkeypatch):
    """Filter presence is safe when the runner's raw bytes actually equal HEAD."""
    repo = _repo(tmp_path / "rulespec-rw")
    _clean_filter(repo)
    assert worktree_state(repo) == {"dirty": False}
    module, output_dir, dashboard, executed = _weekly_suite(tmp_path, monkeypatch, repo)

    assert module.main() == 0

    assert executed == [_HEAD_RULE]
    [report] = [path for path in output_dir.iterdir() if not path.name.startswith(".")]
    for path in (report, dashboard / "rw-vat.json"):
        [entry] = json.loads(path.read_text())["provenance"]["rulespecs"]
        assert entry["sha"] == _git(repo, "rev-parse", "HEAD").strip().decode()
        assert entry["dirty"] is False
        assert "diff_sha256" not in entry


@pytest.fixture
def normalized_clones(tmp_path):
    """Reuse one committed clone pair across generated raw-rate examples."""
    origin = _repo(tmp_path / "origin")
    filtered = tmp_path / "filtered"
    plain = tmp_path / "plain"
    for clone in (filtered, plain):
        _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _clean_filter(filtered)
    return filtered, plain


@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(rate=st.integers(min_value=0, max_value=99).filter(lambda value: value != 18))
@example(rate=17)
def test_normalized_raw_edits_are_dirty_and_hash_like_unfiltered_edits(
    normalized_clones, rate
):
    """Raw identity, rather than Git-normalized identity, determines the state."""
    filtered, plain = normalized_clones
    try:
        assert worktree_state(filtered) == {"dirty": False}
        raw = f"rate: 0.{rate:02d}\n".encode()
        for clone in (filtered, plain):
            (clone / "rule.yaml").write_bytes(raw)
        assert _git(filtered, "status", "--porcelain", "--untracked-files=no") == b""

        first = worktree_state(filtered)

        assert first["dirty"] is True
        assert len(first["diff_sha256"]) == 64
        assert first == worktree_state(plain)
        assert first == worktree_state(filtered), "repeated measurement changed the state"

        # The same clean-filter output cannot erase distinct executed content.
        other_rate = (rate + 1) % 100
        if other_rate == 18:
            other_rate = 19
        (filtered / "rule.yaml").write_bytes(f"rate: 0.{other_rate:02d}\n".encode())
        assert _git(filtered, "status", "--porcelain", "--untracked-files=no") == b""
        second = worktree_state(filtered)
        assert second["dirty"] is True
        assert second["diff_sha256"] != first["diff_sha256"]

        (filtered / "rule.yaml").write_bytes(_HEAD_RULE)
        assert worktree_state(filtered) == {"dirty": False}
    finally:
        # Fixture state is shared by Hypothesis examples; failed/shrunk
        # examples must start from the same raw HEAD bytes as passing ones.
        for clone in (filtered, plain):
            (clone / "rule.yaml").write_bytes(_HEAD_RULE)
