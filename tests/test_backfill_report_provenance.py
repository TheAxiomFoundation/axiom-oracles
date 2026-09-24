"""Tests for scripts/backfill_report_provenance.py."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "backfill_report_provenance.py"
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _load():
    spec = importlib.util.spec_from_file_location("backfill_report_provenance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _commit(repo: Path, message: str, when: str) -> None:
    env = {**os.environ, **GIT_ENV, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    for args in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=repo, env=env, check=True, capture_output=True,
        )


def test_restored_report_is_dated_by_the_commit_that_introduced_its_bytes(
    tmp_path, monkeypatch
):
    """A report put back over later re-emissions keeps its original date: the
    last commit touching the file is the restore, not the run."""
    module = _load()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env={**os.environ, **GIT_ENV})
    report = repo / "report.json"
    report.write_text('{"suite": "s", "run": "real"}\n')
    _commit(repo, "real run", "2026-07-05T22:33:02+00:00")
    report.write_text('{"suite": "s", "run": "re-emitted"}\n')
    _commit(repo, "re-emission", "2026-09-23T21:37:31+00:00")
    report.write_text('{"suite": "s", "run": "real"}\n')
    _commit(repo, "restore the real run", "2026-09-24T18:00:00+00:00")
    monkeypatch.setattr(module, "REPO_ROOT", repo)

    assert module._git_commit_date(report) == "2026-07-05T22:33:02Z"

    # Uncommitted content has no introducing commit: fall back to the last
    # commit touching the path.
    report.write_text('{"suite": "s", "run": "edited"}\n')
    assert module._git_commit_date(report) == "2026-09-24T18:00:00Z"
