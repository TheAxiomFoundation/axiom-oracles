"""Small Git race regressions for the real report packer and publisher.

Generators and conformance gates are explicit no-op fixtures: these tests
isolate publication conflict handling without copying the large oracle corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPORT = "dashboard/public/data/scratch-report.json"
OTHER = "dashboard/public/data/aaa-other-report.json"
ADDED = "dashboard/public/data/new-report.json"
GATE_STUBS = (
    "generate_affected_map.py",
    "apply_dispositions.py",
    "generate_chunk_indexes.py",
    "check_vacuous_gate.py",
    "conformance_scoreboard.py",
    "conformance_burndown.py",
    "generate_dashboard_overview.py",
    "exercise_census.py",
    "certify.py",
    "unexplained_ratchet.py",
    "guard_reemitted_reports.py",
)


def _environment(tmp_path: Path) -> dict[str, str]:
    command_tmp = tmp_path / "command-tmp"
    command_tmp.mkdir()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_") or key in {
            "AXIOM_ORACLES_DATA_SOURCE", "SIMULATE_DERIVED_REFRESH",
        }:
            env.pop(key)
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        TMPDIR=str(command_tmp),
        PYTHON=sys.executable,
        MAX_ATTEMPTS="1",
        PUSH_RETRY_DELAY="0",
    )
    return env


def _git(root: Path, env: dict[str, str], *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, env=env, capture_output=True, text=True,
        timeout=30, check=True,
    ).stdout.strip()


def _write(root: Path, path: str, value: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"value": value}) + "\n")


def _command(root: Path, env: dict[str, str], *args: str):
    return subprocess.run(
        ["bash", "scripts/commit_refreshed_report.sh", *args], cwd=root,
        env=env, capture_output=True, text=True, timeout=90,
    )


def _local_case(tmp_path: Path, *, deletion: bool = False):
    env = _environment(tmp_path)
    remote, seed = tmp_path / "remote.git", tmp_path / "seed"
    producer, publisher = tmp_path / "producer", tmp_path / "publisher"
    bundles = tmp_path / "bundles"
    _git(tmp_path, env, "init", "--bare", "--initial-branch=main", str(remote))
    _git(tmp_path, env, "init", "--initial-branch=main", str(seed))
    _git(seed, env, "config", "user.name", "Test producer")
    _git(seed, env, "config", "user.email", "producer@example.invalid")
    scripts = seed / "scripts"
    scripts.mkdir()
    for name in ("commit_refreshed_report.sh", "oracle_data.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    for name in GATE_STUBS:
        (scripts / name).write_text(f'print("NO-OP TEST GATE: {name}")\n')
    for path in (REPORT, OTHER):
        _write(seed, path, "baseline")
    # All publication pathspecs exist; no real derived producer runs here.
    for path in (
        "conformance/scratch.json",
        "certificates/scratch.json",
        "closure/de/summary.json",
        "closure/nz/summary.json",
        "comparisons/de-worker-dual-oracle/scratch.json",
        "comparisons/affected_map.json",
        "comparisons/nz-treasury-incomeexplorer/single-person-attestations.json",
        "axiom_oracles/data/euromod_be_coverage.json",
    ):
        _write(seed, path, "fixture")
    _git(seed, env, "add", "-A")
    _git(seed, env, "commit", "-m", "Baseline")
    _git(seed, env, "remote", "add", "origin", str(remote))
    _git(seed, env, "push", "origin", "HEAD:refs/heads/main")
    _git(seed, env, "push", "origin", "HEAD:refs/heads/oracle-data")
    for clone in (producer, publisher):
        _git(tmp_path, env, "clone", str(remote), str(clone))
    _write(producer, OTHER, "other-refresh")
    _write(producer, ADDED, "new-refresh")
    if deletion:
        (producer / REPORT).unlink()
    else:
        _write(producer, REPORT, "packed-before-main-edit")
    packed = _command(producer, env, "--pack", str(bundles), "scratch-suite")
    assert packed.returncode == 0, packed.stdout + packed.stderr
    assert "NO-OP TEST GATE" in packed.stdout
    return env, remote, seed, producer, publisher, bundles


@pytest.mark.parametrize("deletion", [False, True], ids=["replace", "delete"])
def test_pack_records_baseline_for_replacements_and_deletions(tmp_path, deletion):
    env, remote, seed, producer, publisher, bundles = _local_case(
        tmp_path, deletion=deletion,
    )
    bundle = json.loads((bundles / "scratch-suite" / "bundle.json").read_text())
    expected = hashlib.sha256((seed / REPORT).read_bytes()).hexdigest()
    assert bundle["baseline"] == {REPORT: expected, OTHER: expected, ADDED: None}


@pytest.mark.parametrize("deletion", [False, True], ids=["replace", "delete"])
def test_control_bundle_publishes_without_reviewed_main_race(tmp_path, deletion):
    env, remote, seed, producer, publisher, bundles = _local_case(
        tmp_path, deletion=deletion,
    )
    main_before = _git(remote, env, "rev-parse", "refs/heads/main")
    result = _command(publisher, env, "--publish", str(bundles), "oracle-data")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(remote, env, "rev-parse", "refs/heads/main") == main_before
    assert json.loads(_git(remote, env, "show", f"oracle-data:{OTHER}")) == {
        "value": "other-refresh",
    }
    if deletion:
        assert REPORT not in _git(remote, env, "ls-tree", "-r", "--name-only", "oracle-data")
    else:
        assert json.loads(_git(remote, env, "show", f"oracle-data:{REPORT}")) == {
            "value": "packed-before-main-edit",
        }


@pytest.mark.parametrize("deletion", [False, True], ids=["replace", "delete"])
def test_reviewed_main_report_edit_refuses_stale_bundle_before_any_write(
    tmp_path, deletion,
):
    env, remote, seed, producer, publisher, bundles = _local_case(
        tmp_path, deletion=deletion,
    )
    data_before = _git(remote, env, "rev-parse", "refs/heads/oracle-data")
    _write(seed, REPORT, "reviewed-main-edit")
    _git(seed, env, "commit", "-am", "Reviewed main correction after packing")
    _git(seed, env, "push", "origin", "HEAD:refs/heads/main")
    main_before = _git(remote, env, "rev-parse", "refs/heads/main")
    result = _command(publisher, env, "--publish", str(bundles), "oracle-data")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "stale bundle" in result.stderr
    assert REPORT in result.stderr
    assert _git(remote, env, "rev-parse", "refs/heads/oracle-data") == data_before
    assert _git(remote, env, "rev-parse", "refs/heads/main") == main_before
    assert (publisher / REPORT).read_bytes() == (seed / REPORT).read_bytes()
    assert (publisher / OTHER).read_bytes() == (seed / OTHER).read_bytes()
    assert not (publisher / ADDED).exists(), "another bundled file was copied before refusal"


@pytest.mark.parametrize("deletion", [False, True], ids=["replace", "delete"])
def test_already_applied_bundle_bytes_are_not_a_stale_conflict(tmp_path, deletion):
    env, remote, seed, producer, publisher, bundles = _local_case(
        tmp_path, deletion=deletion,
    )
    if deletion:
        (seed / REPORT).unlink()
    else:
        _write(seed, REPORT, "packed-before-main-edit")
    _git(seed, env, "commit", "-am", "Reviewed main has the same change")
    _git(seed, env, "push", "origin", "HEAD:refs/heads/main")
    result = _command(publisher, env, "--publish", str(bundles), "oracle-data")
    assert result.returncode == 0, result.stdout + result.stderr


def test_pack_refuses_unreadable_baseline_instead_of_recording_absence(tmp_path):
    env, remote, seed, producer, publisher, bundles = _local_case(tmp_path)
    shim_dir = tmp_path / "git-shim"
    shim_dir.mkdir()
    git_binary = shutil.which("git", path=env["PATH"])
    assert git_binary is not None
    shim = shim_dir / "git"
    shim.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        f"if sys.argv[1:] == ['show', 'HEAD:{REPORT}']:\n"
        "    sys.stderr.write('simulated unreadable baseline blob\\n')\n"
        "    sys.exit(128)\n"
        f"os.execv({git_binary!r}, [{git_binary!r}, *sys.argv[1:]])\n"
    )
    shim.chmod(0o755)
    failed_bundles = tmp_path / "unreadable-baseline-bundles"
    result = _command(
        producer, {**env, "PATH": str(shim_dir) + os.pathsep + env["PATH"]},
        "--pack", str(failed_bundles), "scratch-suite",
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert not (failed_bundles / "scratch-suite").exists()
