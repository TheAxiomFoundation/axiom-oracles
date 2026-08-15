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
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SCRIPT = "scripts/commit_refreshed_report.sh"
#: A committed report the tests perturb the way a rerun would (score-bearing
#: dispositioned rate + provenance timestamp) — the exact 2026-07-14 class.
REPORT = "dashboard/public/data/axiom-policyengine-taxsim-nc-income-tax-liability.json"
SIBLING_REPORT = (
    "dashboard/public/data/axiom-policyengine-taxsim-mi-income-tax-liability.json"
)
#: Everything the script and its regeneration scripts read or write. `docs`
#: and `reports` (plus the root-level *.md files copied in seed_repo) are
#: dispositions EVIDENCE sources: schema validation fails on dangling paths.
#: `certificates` is a DERIVED tree the script regenerates and stages, so it
#: must be seeded or an "idle" run is not idle — the script would generate the
#: missing certificate and push it. Any tree added to the script's
#: derived_paths belongs here too; that coupling is what this comment is for.
SEED_DIRS = (
    "scripts",
    "axiom_oracles",
    "comparisons",
    "conformance",
    "certificates",
    "closure",
    "dispositions",
    "docs",
    "reference",
    "reports",
)
SEED_DATA = "dashboard/public/data"
#: The EUROMOD-BE coverage rollup — maintained only by apply_dispositions.py,
#: aggregated from every be-* report, gated by ci.yml's `--check`.
BE_ROLLUP = "axiom_oracles/data/euromod_be_coverage.json"
#: A BE report with NO dispositions file: the merge never rewrites it, but it
#: still feeds the rollup — so perturbing it drifts the rollup and nothing else.
BE_REPORT = "dashboard/public/data/axiom-euromod-be-article-51-forfait.json"

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
    # The unexplained publication gate scopes out kind:"diagnostic" suites via
    # the dashboard's suite table; without it, nyc-synthetic (a diagnostic
    # suite the gate must ignore) would trip the fixture's ratchet.
    suites_table = Path("dashboard/src/utils/suites.js")
    (seed / suites_table).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / suites_table, seed / suites_table)
    for md in REPO_ROOT.glob("*.md"):  # dispositions evidence (e.g. PROGRESS.md)
        shutil.copy2(md, seed / md.name)
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
    clone: Path, suite: str = "nc-income-tax-liability", attempts: str = "4"
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


def _perturb_report(clone: Path, report: str = REPORT) -> str:
    """Change the report the way a rerun does and return a sentinel that
    proves THIS refresh landed.

    Moves score-bearing summary counts direction-aware (a report with matches
    loses one to mismatch and vice versa, so counts stay valid — flipping the
    conformance detail and the freshness register, the #282 incident class)
    and stamps a fresh, format-valid provenance timestamp. Only fields the
    dispositions merge PRESERVES are touched: for suites with a dispositions
    file, apply_dispositions.py recomputes the `summary.dispositioned` block
    from the mismatch rows, so perturbing that block would be silently
    reverted by the regeneration and the test could not tell a landed refresh
    from a clobbered one. The sentinel discriminates because it differs from
    the committed historical timestamp, and it honors the repository's
    `%Y-%m-%dT%H:%M:%SZ` provenance format.
    """
    path = clone / report
    doc = json.loads(path.read_text())
    summary = doc["summary"]
    if summary["match_count"] > 0:
        summary["match_count"] -= 1
        summary["mismatch_count"] = summary.get("mismatch_count", 0) + 1
    else:
        summary["match_count"] += 1
        summary["mismatch_count"] = max(summary.get("mismatch_count", 1) - 1, 0)
    sentinel = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert doc["provenance"]["generated_at"] != sentinel, (
        "committed report timestamp collides with now; cannot discriminate"
    )
    doc["provenance"]["generated_at"] = sentinel
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return sentinel


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
    # Every gate ci.yml runs on main must be asserted here, or an artifact can
    # verify inside the bot's worktree and still be omitted from the commit —
    # exactly the stale-certificate failure class (round-3 audit finding 7).
    # Adding a gate to ci.yml means adding it here.
    for script in (
        "apply_dispositions.py",
        "conformance_scoreboard.py",
        "conformance_burndown.py",
        "check_vacuous_gate.py",
        "generate_dashboard_overview.py",
        "exercise_census.py",
        "certify.py",
    ):
        result = _staleness_gate(verify, script)
        assert result.returncode == 0, (
            f"{script} --check failed on the pushed tip:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return verify


def test_refresh_pushes_report_with_derived_artifacts(origin, tmp_path):
    """A report refresh lands together with regenerated scoreboard/detail,
    freshness, and burn-down — the pushed tip passes ci.yml's staleness gates
    (the 2026-07-14 incident tree could not have been pushed)."""
    clone = _clone(origin, tmp_path / "job")
    sentinel = _perturb_report(clone)
    result = _run_script(clone)
    assert result.returncode == 0, result.stderr

    verify = _assert_origin_tip_green(origin, tmp_path)
    pushed = json.loads((verify / REPORT).read_text())
    assert pushed["provenance"]["generated_at"] == sentinel


def test_be_refresh_regenerates_euromod_coverage_rollup(origin, tmp_path):
    """A BE report refresh drifts the EUROMOD-BE coverage rollup — maintained
    ONLY by apply_dispositions.py and gated by ci.yml's
    `apply_dispositions.py --check` — so the pushed tip must carry a
    regenerated rollup, not the seed one (BE suites are in the bot matrix)."""
    clone = _clone(origin, tmp_path / "job")
    before = json.loads((clone / BE_ROLLUP).read_text())["dispositioned_parity"]

    # Flip one comparison from match to mismatch: the rollup's aggregate
    # match_count / raw_match_rate must move, or this test cannot discriminate.
    path = clone / BE_REPORT
    doc = json.loads(path.read_text())
    doc["summary"]["match_count"] -= 1
    doc["summary"]["mismatch_count"] += 1
    path.write_text(json.dumps(doc, indent=2) + "\n")

    result = _run_script(clone, "be-article-51-forfait")
    assert result.returncode == 0, result.stderr

    verify = _assert_origin_tip_green(origin, tmp_path)
    after = json.loads((verify / BE_ROLLUP).read_text())["dispositioned_parity"]
    assert after["match_count"] == before["match_count"] - 1, (
        "the pushed rollup must be regenerated from the refreshed BE report"
    )
    assert after != before


def test_concurrent_siblings_never_leave_main_stale(origin, tmp_path):
    """Two matrix siblings refresh different suites; the second job's clone
    predates the first job's push. The script must rebuild on the new tip (a
    rebase would conflict on the shared derived files) and every pushed tip —
    including the intermediate one — stays gate-green."""
    job_a = _clone(origin, tmp_path / "job-a")
    job_b = _clone(origin, tmp_path / "job-b")  # cloned BEFORE a's push
    sentinel_a = _perturb_report(job_a, REPORT)
    sentinel_b = _perturb_report(job_b, SIBLING_REPORT)

    result_a = _run_script(job_a, "nc-income-tax-liability")
    assert result_a.returncode == 0, result_a.stderr
    intermediate = _git(origin, "rev-parse", "main")
    _assert_origin_tip_green(origin, tmp_path)

    result_b = _run_script(job_b, "mi-income-tax-liability")
    assert result_b.returncode == 0, result_b.stderr
    assert _git(origin, "rev-parse", "main") != intermediate

    verify = _assert_origin_tip_green(origin, tmp_path)
    for report, sentinel in ((REPORT, sentinel_a), (SIBLING_REPORT, sentinel_b)):
        doc = json.loads((verify / report).read_text())
        assert doc["provenance"]["generated_at"] == sentinel, (
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


def test_racing_pusher_converges_when_remote_advances_mid_push(origin, tmp_path):
    """A sibling advances main BETWEEN this leg's rebuild and its push — the
    genuine race, made deterministic with a two-marker barrier: the hook
    intercepting the leg's first push signals the test thread (`racing`),
    then BLOCKS until the test has pushed the sibling commit through and
    touched `sibling-landed`, and only then rejects. The leg's retry
    therefore always fetches a tip the sibling has already advanced — no
    timing window. (git forbids moving refs from inside a hook, so the
    advance must come from outside.) The leg must rebuild on the sibling's
    tip and land a tree that keeps BOTH refreshes — and, because the sibling
    pushed a raw report with no derived regen (the old broken-bot shape), the
    leg's regeneration must heal that too: the final tip passes every gate."""
    # The sibling's commit: a raw report perturbation with NO derived
    # regeneration, exactly what the pre-fix bot pushed. Kept local until the
    # leg's first push is intercepted.
    sibling = _clone(origin, tmp_path / "sibling")
    sentinel_sibling = _perturb_report(sibling, SIBLING_REPORT)
    _git(sibling, "add", "--", "dashboard/public/data/")
    _git(sibling, "commit", "-q", "-m", "data: sibling refresh (no derived regen)")
    sibling_sha = _git(sibling, "rev-parse", "HEAD")

    racing = origin / "racing"
    landed = origin / "sibling-landed"
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        f'racing="{racing}"\nlanded="{landed}"\n'
        "while read old new ref; do\n"
        '  if [ "$ref" = "refs/heads/main" ] && [ ! -f "$racing" ]; then\n'
        '    touch "$racing"\n'
        "    i=0\n"
        '    while [ ! -f "$landed" ] && [ "$i" -lt 1200 ]; do\n'
        "      sleep 0.1; i=$((i + 1))\n"
        "    done\n"
        '    echo "simulated concurrent sibling push" >&2\n'
        "    exit 1\n"
        "  fi\n"
        "done\n"
        "exit 0\n"
    )
    hook.chmod(0o755)

    clone = _clone(origin, tmp_path / "job")
    sentinel = _perturb_report(clone)
    proc = subprocess.Popen(
        [str(clone / SCRIPT), "nc-income-tax-liability", "main"],
        cwd=clone,
        env={
            **os.environ,
            **GIT_ENV,
            "PYTHON": sys.executable,
            "MAX_ATTEMPTS": "4",
            "PUSH_RETRY_DELAY": "0",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Hook has signaled the leg's first push; land the sibling (its push sees
    # `racing` set, so the hook waves it through), then release the hook.
    deadline = time.monotonic() + 120
    while not racing.exists():
        assert time.monotonic() < deadline, "leg never attempted its first push"
        assert proc.poll() is None, proc.communicate()[1]
        time.sleep(0.05)
    _git(sibling, "push", "-q", "origin", "HEAD:main")
    landed.touch()
    stdout, stderr = proc.communicate(timeout=240)
    assert proc.returncode == 0, stderr
    assert "push rejected (attempt 1" in stderr

    verify = _assert_origin_tip_green(origin, tmp_path)
    assert sibling_sha in _git(verify, "rev-list", "HEAD"), (
        "the sibling's mid-race commit must survive as an ancestor"
    )
    for report, expected in ((REPORT, sentinel), (SIBLING_REPORT, sentinel_sibling)):
        doc = json.loads((verify / report).read_text())
        assert doc["provenance"]["generated_at"] == expected, (
            f"{report}: one of the racing refreshes was lost"
        )


def _add_first_time_report(clone: Path, suite: str) -> str:
    """Simulate run_comparison.py landing a brand-new suite: write its first
    report and append its filename to the shared manifest (creating the
    manifest if the tree has none — run_comparison does the same)."""
    filename = f"axiom-policyengine-{suite}.json"
    doc = json.loads((clone / REPORT).read_text())
    doc["suite"] = suite
    (clone / SEED_DATA / filename).write_text(json.dumps(doc, indent=2) + "\n")
    manifest_path = clone / SEED_DATA / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {"reports": []}
    )
    manifest["reports"].append(filename)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return filename


def test_first_time_reports_from_racing_legs_merge_manifest(origin, tmp_path):
    """Two legs each land a brand-new suite; the second leg's clone predates
    the first leg's push. manifest.json is shared and append-only — restoring
    the second leg's stale copy would drop the first leg's entry, so the
    script must replay its own ADDITIONS onto the winning tip instead."""
    job_a = _clone(origin, tmp_path / "job-a")
    job_b = _clone(origin, tmp_path / "job-b")  # cloned BEFORE a's push
    file_a = _add_first_time_report(job_a, "zz-fake-a")
    file_b = _add_first_time_report(job_b, "zz-fake-b")

    result_a = _run_script(job_a, "zz-fake-a")
    assert result_a.returncode == 0, result_a.stderr
    result_b = _run_script(job_b, "zz-fake-b")
    assert result_b.returncode == 0, result_b.stderr

    verify = _assert_origin_tip_green(origin, tmp_path)
    manifest = json.loads((verify / SEED_DATA / "manifest.json").read_text())
    for filename in (file_a, file_b):
        assert filename in manifest["reports"], (
            f"{filename} dropped from the shared manifest by the racing leg"
        )
        assert (verify / SEED_DATA / filename).exists()


def test_first_time_reports_race_when_head_has_no_manifest(origin, tmp_path):
    """Same manifest race, but HEAD has NO committed manifest — the file is
    brand-new (untracked) in both legs. The untracked collector must exclude
    it exactly like the tracked path, or the second leg restores its stale
    whole-file copy and drops the first leg's entry."""
    setup = _clone(origin, tmp_path / "setup")
    _git(setup, "rm", "-q", "--", f"{SEED_DATA}/manifest.json")
    _git(setup, "commit", "-q", "-m", "seed variant: no manifest yet")
    _git(setup, "push", "-q", "origin", "HEAD:main")

    job_a = _clone(origin, tmp_path / "job-a")
    job_b = _clone(origin, tmp_path / "job-b")  # cloned BEFORE a's push
    file_a = _add_first_time_report(job_a, "zz-fake-a")
    file_b = _add_first_time_report(job_b, "zz-fake-b")

    result_a = _run_script(job_a, "zz-fake-a")
    assert result_a.returncode == 0, result_a.stderr
    result_b = _run_script(job_b, "zz-fake-b")
    assert result_b.returncode == 0, result_b.stderr

    verify = _assert_origin_tip_green(origin, tmp_path)
    manifest = json.loads((verify / SEED_DATA / "manifest.json").read_text())
    for filename in (file_a, file_b):
        assert filename in manifest["reports"], (
            f"{filename} dropped: the untracked manifest was restored verbatim"
        )


def test_vacuous_gate_crash_refuses_push(origin, tmp_path):
    """check_vacuous_gate.py exiting 1 can be a schema alarm (tolerated in
    write mode) — but it can also be a crash that never wrote freshness. The
    verify step runs the `--check` arbiter, so a tree whose freshness can't
    be proven fresh is never pushed.

    The failure is injected via a PYTHON wrapper OUTSIDE the repo (an in-repo
    stub would be reverted by the retry loop's `git reset --hard`): every
    check_vacuous_gate.py invocation exits 1 without writing, exactly the
    crash shape — so the perturbed report's freshness is genuinely stale and
    the arbiter must block the push."""
    wrapper = tmp_path / "bin" / "python-wrapper"
    wrapper.parent.mkdir()
    wrapper.write_text(
        "#!/bin/sh\n"
        'case "$*" in *check_vacuous_gate.py*) exit 1 ;; esac\n'
        f'exec "{sys.executable}" "$@"\n'
    )
    wrapper.chmod(0o755)

    clone = _clone(origin, tmp_path / "job")
    before = _git(origin, "rev-parse", "main")
    _perturb_report(clone)
    result = subprocess.run(
        [str(clone / SCRIPT), "nc-income-tax-liability", "main"],
        cwd=clone,
        env={
            **os.environ,
            **GIT_ENV,
            "PYTHON": str(wrapper),
            "MAX_ATTEMPTS": "2",
            "PUSH_RETRY_DELAY": "0",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "a vacuous-gate failure the arbiter can't clear must fail the job"
    )
    assert _git(origin, "rev-parse", "main") == before, (
        "nothing may be pushed when the freshness gate can't be verified"
    )


def test_no_changes_second_run_is_a_noop(origin, tmp_path):
    """Back-to-back runs with nothing new: BOTH take the fast no-op path (the
    checked-out tree already passes every gate), pushing nothing — the daily
    history snapshot only lands alongside an actual refresh. The tip is
    captured BEFORE the first run and the no-op message asserted on both, so
    a variant that pushes a snapshot-churn commit on the first idle run (the
    pre-amendment behavior) fails here."""
    tip = _git(origin, "rev-parse", "main")

    first = _clone(origin, tmp_path / "first")
    result = _run_script(first)
    assert result.returncode == 0, result.stderr
    assert "no report or derived-artifact changes" in result.stdout
    assert _git(origin, "rev-parse", "main") == tip, (
        "an idle run must not churn a commit"
    )
    _assert_origin_tip_green(origin, tmp_path)

    second = _clone(origin, tmp_path / "second")
    result = _run_script(second)
    assert result.returncode == 0, result.stderr
    assert "no report or derived-artifact changes" in result.stdout
    assert _git(origin, "rev-parse", "main") == tip
