#!/usr/bin/env python
"""Delete superseded full-report generations, keeping the newest per suite.

Full-evidence reports (raw input records per household) run to gigabytes
for the larger generic-projector suites; without retention the weekly
regeneration accumulates tens of GB of dead generations locally.

A run writes its raw report ``<suite>-0-YYYY-MM-DD.json``; some runs then
write its FULL v2 sibling ``<suite>-0-YYYY-MM-DD-v2.json`` (``run_comparison.py``'s
``_write_full_v2_report``). Raw reports and each ``-vN`` kind are pruned as
separate groups per suite, so the newest raw report and the newest v2
report each survive: a v2 never deletes its own run's raw report, and a run
that fails before writing its v2 leaves the previous v2 in place.

"Newest" is decided by the date in the name, with the modification time only
breaking a tie, so a freshly checked-out or touched older report cannot
outrank a newer-dated one. reports/ is gitignored, but a few reports are
committed on purpose (a dashboard copy binds the fiit-ecps FULL report by
digest). A file Git tracks is never deleted and takes no part in electing
the newest generation.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"
GENERATION = re.compile(r"-0-(?P<date>\d{4}-\d{2}-\d{2})(?P<suffix>-v\d+)?\.json$")


def tracked_reports(reports: Path) -> set[Path]:
    """Report paths Git tracks; raises when Git cannot list them."""
    result = subprocess.run(
        ["git", "-C", str(reports), "ls-files", "-z", "--", "."],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        # Fail closed: an empty set would let a tracked report be deleted.
        raise RuntimeError(
            "git ls-files failed; refusing to prune without the tracked list: "
            + result.stderr.decode(errors="replace").strip()
        )
    return {
        (reports / name.decode()).resolve()
        for name in result.stdout.split(b"\0")
        if name
    }


def generation_key(path: Path) -> tuple[str, float]:
    """Order generations by the date in the name, then by modification time."""
    match = GENERATION.search(path.name)
    if match is None:
        raise ValueError(f"not a report generation: {path.name}")
    return match["date"], os.path.getmtime(path)


def prune(reports: Path, *, tracked: set[Path]) -> tuple[list[Path], int]:
    """Remove every generation but each suite's newest; return what went."""
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path in reports.glob("*-0-*.json"):
        match = GENERATION.search(path.name)
        if match:
            suite = path.name[: match.start()]
            groups[(suite, match["suffix"] or "")].append(path)
    removed: list[Path] = []
    freed = 0
    for paths in groups.values():
        # Tracked reports are never deleted and do not compete for newest.
        candidates = sorted(
            (path for path in paths if path.resolve() not in tracked),
            key=generation_key,
        )
        for old in candidates[:-1]:
            freed += old.stat().st_size
            old.unlink()
            removed.append(old)
    return removed, freed


def main() -> int:
    removed, freed = prune(REPORTS, tracked=tracked_reports(REPORTS))
    print(f"pruned {len(removed)} superseded report(s), freed {freed / 1e9:.1f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
