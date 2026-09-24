"""Tests for scripts/guard_reemitted_reports.py (the commit-step re-emission guard).

scripts/commit_refreshed_report.sh runs the guard on every push attempt, after
restoring the leg's outputs onto the current tip. A re-emitted dashboard report
must never replace the tip's copy when that copy came from a real run; anything
else the leg wrote passes through untouched.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "guard_reemitted_reports.py"
DATA = "dashboard/public/data"
REAL = {"run_kind": "manual", "rulespecs": [{"repo": "o/rulespec-us", "sha": "a" * 40}]}
REEMITTED = {"run_kind": "affected-rerun", "reemitted_report": True}
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _report(suite: str, provenance: dict | None, stamp: str = "t0") -> str:
    report: dict = {"suite": suite, "case_count": 1}
    if provenance is not None:
        report["provenance"] = {**provenance, "generated_at": stamp}
    return json.dumps(report, indent=2) + "\n"


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("guard_reemitted_reports", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    (repo / DATA / "cases" / "s").mkdir(parents=True)
    files = {
        f"{DATA}/real.json": _report("real", REAL),
        f"{DATA}/legacy.json": _report("legacy", None),
        f"{DATA}/reemitted.json": _report("reemitted", REEMITTED),
        f"{DATA}/cases/s/chunk-0.json": _report("chunk", REAL),
    }
    for path, text in files.items():
        (repo / path).write_text(text)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    monkeypatch.setattr(module, "REPO_ROOT", repo)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return module, repo


def test_reemission_over_a_real_report_is_put_back(guard, capsys):
    module, repo = guard
    committed = (repo / DATA / "real.json").read_text()
    (repo / DATA / "real.json").write_text(_report("real", REEMITTED, stamp="t1"))

    assert module.downgrades("HEAD") == [f"{DATA}/real.json"]
    assert module.main([]) == 0

    assert (repo / DATA / "real.json").read_text() == committed
    assert "a re-emission never replaces a real run" in capsys.readouterr().out
    assert _git(repo, "status", "--porcelain") == ""


def test_unstamped_legacy_report_counts_as_real(guard):
    module, repo = guard
    committed = (repo / DATA / "legacy.json").read_text()
    (repo / DATA / "legacy.json").write_text(_report("legacy", REEMITTED, stamp="t1"))

    assert module.main([]) == 0

    assert (repo / DATA / "legacy.json").read_text() == committed


def test_other_changes_pass_through(guard):
    """Only a real -> re-emitted downgrade is undone: a re-emission over a
    re-emission, a real run over a real run, a first report, and anything below
    the top-level data directory are left as the leg wrote them."""
    module, repo = guard
    writes = {
        f"{DATA}/reemitted.json": _report("reemitted", REEMITTED, stamp="t1"),
        f"{DATA}/real.json": _report("real", REAL, stamp="t1"),
        f"{DATA}/new.json": _report("new", REEMITTED, stamp="t1"),
        f"{DATA}/cases/s/chunk-0.json": _report("chunk", REEMITTED, stamp="t1"),
    }
    for path, text in writes.items():
        (repo / path).write_text(text)

    assert module.downgrades("HEAD") == []
    assert module.main([]) == 0

    for path, text in writes.items():
        assert (repo / path).read_text() == text, path


def test_judged_against_the_given_revision(guard):
    """The commit script runs the guard after resetting to each attempt's tip,
    so what counts is the tip's copy, not the one the leg started from."""
    module, repo = guard
    start = _git(repo, "rev-parse", "HEAD").strip()
    # A real report lands on the tip while the leg runs.
    (repo / DATA / "reemitted.json").write_text(_report("reemitted", REAL, stamp="t2"))
    _git(repo, "commit", "-q", "-am", "real run lands")
    landed = (repo / DATA / "reemitted.json").read_text()
    # The leg restores its own re-emission onto that tip.
    (repo / DATA / "reemitted.json").write_text(
        _report("reemitted", REEMITTED, stamp="t3")
    )

    assert module.downgrades(start) == []
    assert module.main([]) == 0

    assert (repo / DATA / "reemitted.json").read_text() == landed


def test_github_actions_emits_a_warning_annotation(guard, capsys, monkeypatch):
    module, repo = guard
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    (repo / DATA / "real.json").write_text(_report("real", REEMITTED, stamp="t1"))

    assert module.main([]) == 0

    assert capsys.readouterr().out.startswith(
        "::warning title=Re-emission not committed::"
    )

