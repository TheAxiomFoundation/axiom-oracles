"""Functional tests for scripts/commit_refreshed_report.sh (affected-rerun bot).

The affected-rerun workflow pushes refreshed comparison reports straight to
main. A report refresh changes the inputs of derived, CI-validated artifacts
(conformance scoreboard + detail, freshness, burn-down); pushing one without
regenerating them turns main red at ci.yml's staleness gates — the 2026-07-14
il/ky/oh/va incident, repaired by hand in #282. These tests drive the real
script against a real (bare) origin built from this repo's own tree and assert
the property that matters: EVERY tree the bot pushes passes the same staleness
gates ci.yml runs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SCRIPT = "scripts/commit_refreshed_report.sh"
#: A committed report the tests perturb the way a rerun would (score-bearing
#: dispositioned rate + provenance timestamp) — the exact 2026-07-14 class.
REPORT = "dashboard/public/data/axiom-policyengine-taxsim-il-income-tax-liability.json"
SIBLING_REPORT = (
    "dashboard/public/data/axiom-policyengine-taxsim-ky-income-tax-liability.json"
)
#: Everything the script and its regeneration scripts read or write.
SEED_DIRS = ("scripts", "axiom_oracles", "comparisons", "conformance")
SEED_DATA = "dashboard/public/data"

#: Hermetic git: no user/system config (no signing hooks, no identity — the
#: script must supply the bot identity itself, exactly as on a CI runner).
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=seed", "-c", "user.email=seed@test", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(scope="session")
def seed_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """This repo's relevant subtrees, committed once as a throwaway git repo."""
    seed = tmp_path_factory.mktemp("affected-rerun") / "seed"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv")
    for d in SEED_DIRS:
        shutil.copytree(REPO_ROOT / d, seed / d, ignore=ignore)
    shutil.copytree(REPO_ROOT / SEED_DATA, seed / SEED_DATA, ignore=ignore)
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    return seed


@pytest.fixture()
def origin(seed_repo: Path, tmp_path: Path) -> Path:
    """A fresh BARE origin per test (pushable; hardlinked, so cheap)."""
    bare = tmp_path / "origin.git"
    _git(seed_repo.parent, "clone", "-q", "--bare", str(seed_repo), str(bare))
    return bare


def _clone(origin: Path, dst: Path) -> Path:
    _git(origin.parent, "clone", "-q", str(origin), str(dst))
    return dst


def _run_script(
    clone: Path, suite: str = "il-income-tax-liability", attempts: str = "4"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(clone / SCRIPT), suite, "main"],
        cwd=clone,
        env={
            **os.environ,
            **GIT_ENV,
            "PYTHON": sys.executable,
            "MAX_ATTEMPTS": attempts,
            "PUSH_RETRY_DELAY": "0",
        },
        capture_output=True,
        text=True,
    )


def _perturb_report(clone: Path, report: str = REPORT) -> None:
    """Change the report the way a rerun does: a score-bearing dispositioned
    rate (flips the conformance detail — the #282 incident field) plus the
    provenance timestamp (flips freshness.json)."""
    path = clone / report
    doc = json.loads(path.read_text())
    dispositioned = doc["summary"]["dispositioned"]
    dispositioned["explained_rate"] = (
        100 if dispositioned.get("explained_rate") is None else None
    )
    doc["provenance"]["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    path.write_text(json.dumps(doc, indent=2) + "\n")


def _staleness_gate(clone: Path, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, f"scripts/{script}", "--check"],
        cwd=clone,
        env={**os.environ, **GIT_ENV},
        capture_output=True,
        text=True,
    )


def _assert_origin_tip_green(origin: Path, tmp_path: Path) -> Path:
    """Clone origin's tip and assert ci.yml's staleness gates all pass on it."""
    verify = _clone(origin, tmp_path / f"verify-{len(list(tmp_path.iterdir()))}")
    for script in (
        "conformance_scoreboard.py",
        "conformance_burndown.py",
        "check_vacuous_gate.py",
    ):
        result = _staleness_gate(verify, script)
        assert result.returncode == 0, (
            f"{script} --check failed on the pushed tip:\n{result.stderr}"
        )
    return verify


def test_refresh_pushes_report_with_derived_artifacts(origin, tmp_path):
    """A report refresh lands together with regenerated scoreboard/detail,
    freshness, and burn-down — the pushed tip passes ci.yml's staleness gates
    (the 2026-07-14 incident tree could not have been pushed)."""
    clone = _clone(origin, tmp_path / "job")
    _perturb_report(clone)
    result = _run_script(clone)
    assert result.returncode == 0, result.stderr

    verify = _assert_origin_tip_green(origin, tmp_path)
    pushed = json.loads((verify / REPORT).read_text())
    assert pushed["summary"]["dispositioned"]["explained_rate"] is None


def test_concurrent_siblings_never_leave_main_stale(origin, tmp_path):
    """Two matrix siblings refresh different suites; the second job's clone
    predates the first job's push. The script must rebuild on the new tip (a
    rebase would conflict on the shared derived files) and every pushed tip —
    including the intermediate one — stays gate-green."""
    job_a = _clone(origin, tmp_path / "job-a")
    job_b = _clone(origin, tmp_path / "job-b")  # cloned BEFORE a's push
    _perturb_report(job_a, REPORT)
    _perturb_report(job_b, SIBLING_REPORT)

    result_a = _run_script(job_a, "il-income-tax-liability")
    assert result_a.returncode == 0, result_a.stderr
    intermediate = _git(origin, "rev-parse", "main")
    _assert_origin_tip_green(origin, tmp_path)

    result_b = _run_script(job_b, "ky-income-tax-liability")
    assert result_b.returncode == 0, result_b.stderr
    assert _git(origin, "rev-parse", "main") != intermediate

    verify = _assert_origin_tip_green(origin, tmp_path)
    for report in (REPORT, SIBLING_REPORT):
        doc = json.loads((verify / report).read_text())
        assert doc["summary"]["dispositioned"]["explained_rate"] is None, (
            f"{report}: a sibling push clobbered this refresh"
        )


def test_rejected_push_retries_by_rebuilding_on_tip(origin, tmp_path):
    """A rejected push (sibling won the race) is retried by rebuilding the
    commit from scratch — and the retry actually lands."""
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(
        '#!/bin/sh\nmarker="$GIT_DIR/rejected-once"\n'
        'if [ ! -f "$marker" ]; then\n'
        '  touch "$marker"\n'
        '  echo "simulated concurrent sibling push" >&2\n'
        "  exit 1\n"
        "fi\nexit 0\n"
    )
    hook.chmod(0o755)

    clone = _clone(origin, tmp_path / "job")
    before = _git(origin, "rev-parse", "main")
    _perturb_report(clone)
    result = _run_script(clone)
    assert result.returncode == 0, result.stderr
    assert "push rejected (attempt 1" in result.stderr
    assert _git(origin, "rev-parse", "main") != before
    _assert_origin_tip_green(origin, tmp_path)


def test_exhausted_retries_fail_loudly(origin, tmp_path):
    """If the push NEVER lands, the job must fail (the old loop exited 0 and
    silently dropped the refresh)."""
    hook = origin / "hooks" / "pre-receive"
    hook.write_text('#!/bin/sh\necho "always rejected" >&2\nexit 1\n')
    hook.chmod(0o755)

    clone = _clone(origin, tmp_path / "job")
    _perturb_report(clone)
    result = _run_script(clone, attempts="2")
    assert result.returncode == 1
    assert "NOT committed" in result.stderr


def test_self_heals_preexisting_staleness(origin, tmp_path):
    """A stale tree already on main (what the pre-fix workflow used to push;
    the #282 state) converges back to green on the next rerun with NO local
    report change — no manual regeneration PR needed."""
    # Reproduce the old broken bot: push a perturbed report WITHOUT
    # regenerating anything derived.
    broken = _clone(origin, tmp_path / "broken-bot")
    _perturb_report(broken)
    _git(broken, "add", "--", "dashboard/public/data/")
    _git(broken, "commit", "-q", "-m", "data: refresh (no derived regen)")
    _git(broken, "push", "-q", "origin", "HEAD:main")

    # NEGATIVE control: that tip must actually fail the scoreboard gate,
    # otherwise this test could not discriminate.
    stale = _clone(origin, tmp_path / "stale-check")
    assert _staleness_gate(stale, "conformance_scoreboard.py").returncode == 1

    # The next rerun (even with nothing of its own to refresh) self-heals.
    healer = _clone(origin, tmp_path / "healer")
    result = _run_script(healer)
    assert result.returncode == 0, result.stderr
    _assert_origin_tip_green(origin, tmp_path)


def test_no_changes_second_run_is_a_noop(origin, tmp_path):
    """Back-to-back runs with nothing new: the first may commit the daily
    history snapshot (idempotent per day); the second must exit cleanly
    without committing anything."""
    first = _clone(origin, tmp_path / "first")
    result = _run_script(first)
    assert result.returncode == 0, result.stderr
    tip = _git(origin, "rev-parse", "main")
    _assert_origin_tip_green(origin, tmp_path)

    second = _clone(origin, tmp_path / "second")
    result = _run_script(second)
    assert result.returncode == 0, result.stderr
    assert "no report or derived-artifact changes" in result.stdout
    assert _git(origin, "rev-parse", "main") == tip
