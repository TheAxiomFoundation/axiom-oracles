"""Report pruning keeps the newest generation per suite, v2 files included (#643)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

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


def test_v2_generations_group_with_their_suite(tmp_path):
    old = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-01.json", 1)
    v2 = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-14-v2.json", 2)
    newest = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-20.json", 3)
    other = _write(tmp_path, "axiom-policyengine-ssi-ecps-0-2026-10-01.json", 1)

    removed, _ = prune.prune(tmp_path, tracked=set())

    assert sorted(removed) == sorted([old, v2])
    assert newest.exists() and other.exists()
    assert not old.exists() and not v2.exists()


def test_older_v2_generations_of_one_day_are_pruned(tmp_path):
    first = _write(tmp_path, "suite-0-2026-10-14-v2.json", 1)
    second = _write(tmp_path, "suite-0-2026-10-14-v3.json", 2)
    prune.prune(tmp_path, tracked=set())
    assert not first.exists() and second.exists()


def test_tracked_reports_are_never_deleted(tmp_path):
    # reports/ is gitignored, but the fiit-ecps FULL report a dashboard copy
    # binds by digest is committed. A newer local run must not delete it.
    bound = _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-14-v2.json", 1)
    _write(tmp_path, "axiom-policyengine-fiit-ecps-0-2026-10-20.json", 2)
    removed, _ = prune.prune(tmp_path, tracked={bound.resolve()})
    assert removed == [] and bound.exists()


def test_committed_reports_are_tracked_by_the_real_listing():
    tracked = prune.tracked_reports(prune.REPORTS)
    assert (
        prune.REPORTS / "axiom-policyengine-fiit-ecps-0-2026-10-14-v2.json"
    ).resolve() in tracked
