"""Report pruning keeps the newest generation per suite, v2 files included (#643)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "prune_superseded_reports", ROOT / "scripts" / "prune_superseded_reports.py"
)
prune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prune)


def _write(directory: Path, name: str, mtime: int) -> Path:
    path = directory / name
    path.write_text("{}\n")
    os.utime(path, (mtime, mtime))
    return path


def test_raw_and_v2_reports_are_pruned_separately(tmp_path):
    # A run writes its raw report X-0-D.json and then its FULL v2 sibling
    # X-0-D-v2.json (run_comparison._write_full_v2_report). The newest of
    # each kind survives; the v2 never deletes its own run's raw report.
    old_raw = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-01.json", 1)
    old_v2 = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-01-v2.json", 2)
    raw = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-20.json", 3)
    v2 = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-20-v2.json", 4)
    other = _write(tmp_path, "axiom-policyengine-ssi-ecps-0-2026-10-01.json", 1)

    removed, _ = prune.prune(tmp_path, tracked=set())

    assert sorted(removed) == sorted([old_raw, old_v2])
    assert raw.exists() and v2.exists() and other.exists()


def test_a_failed_run_keeps_the_previous_v2(tmp_path):
    # The raw report landed but the run failed before writing its v2: the
    # previous v2 is still the newest v2 and must survive.
    old_v2 = _write(tmp_path, "suite-0-2026-10-14-v2.json", 1)
    raw = _write(tmp_path, "suite-0-2026-10-20.json", 2)
    removed, _ = prune.prune(tmp_path, tracked=set())
    assert removed == [] and old_v2.exists() and raw.exists()


def test_older_v2_generations_are_pruned(tmp_path):
    first = _write(tmp_path, "suite-0-2026-10-14-v2.json", 1)
    second = _write(tmp_path, "suite-0-2026-10-20-v2.json", 2)
    prune.prune(tmp_path, tracked=set())
    assert not first.exists() and second.exists()


def test_tracked_reports_are_never_deleted(tmp_path):
    # reports/ is gitignored, but the fiit-ecps FULL report a dashboard copy
    # binds by digest is committed. A newer local run must not delete it.
    bound = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-14-v2.json", 1)
    _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-20.json", 2)
    # A newer v2 of the same suite: without the guard the bound one would go.
    _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-20-v2.json", 3)
    removed, _ = prune.prune(tmp_path, tracked={bound.resolve()})
    assert removed == [] and bound.exists()


def test_committed_reports_are_tracked_by_the_real_listing():
    tracked = prune.tracked_reports(prune.REPORTS)
    assert (
        prune.REPORTS / "axiom-policyengine-fiit-ecps-0-2026-10-14-v2.json"
    ).resolve() in tracked


def test_tracked_reports_raises_when_git_cannot_list(tmp_path):
    # Outside a Git checkout `git ls-files` fails; the guard must not fail
    # open into an empty set and let a tracked report be deleted.
    with pytest.raises(RuntimeError, match="git ls-files"):
        prune.tracked_reports(tmp_path)


def test_a_fresh_tracked_checkout_does_not_outrank_a_newer_dated_report(tmp_path):
    # The review's reproduction: a tracked report with a fresh checkout mtime
    # plus newer-dated untracked reports with older mtimes. The date in the
    # name decides, and tracked files stay out of the newest election.
    tracked = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-14-v2.json", 9)
    newer_v2 = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-11-02-v2.json", 1)
    newer_raw = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-11-02.json", 1)
    removed, _ = prune.prune(tmp_path, tracked={tracked.resolve()})
    assert removed == []
    assert tracked.exists() and newer_v2.exists() and newer_raw.exists()


def test_the_date_in_the_name_outranks_a_later_mtime(tmp_path):
    older_touched = _write(tmp_path, "suite-0-2026-10-14.json", 9)
    newer = _write(tmp_path, "suite-0-2026-11-02.json", 1)
    removed, _ = prune.prune(tmp_path, tracked=set())
    assert removed == [older_touched] and newer.exists()


def test_mtime_breaks_a_tie_on_the_same_date(tmp_path):
    # Within one group two names cannot share a date, so check the ordering
    # key directly: the date in the name first, then the mtime.
    first = _write(tmp_path, "suite-0-2026-11-02.json", 1)
    assert prune.generation_key(first) == ("2026-11-02", 1.0)
