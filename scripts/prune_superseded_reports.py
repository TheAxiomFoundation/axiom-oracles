#!/usr/bin/env python
"""Delete superseded full-report generations, keeping the newest per suite.

Full-evidence reports (raw input records per household) run to gigabytes
for the larger generic-projector suites; without retention the weekly
regeneration accumulates tens of GB of dead generations locally.

A generation is ``<suite>-0-YYYY-MM-DD.json`` or a same-day rerun
``<suite>-0-YYYY-MM-DD-vN.json``; all of a suite's generations form one
group, and only the newest by modification time survives. reports/ is
gitignored, but a few reports are committed on purpose (a dashboard copy
binds the fiit-ecps FULL report by digest), so a file Git tracks is never
deleted.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"
GENERATION = re.compile(r"-0-\d{4}-\d{2}-\d{2}(?:-v\d+)?\.json$")


def tracked_reports(reports: Path) -> set[Path]:
    """Report paths Git tracks; empty outside a Git checkout."""
    result = subprocess.run(
        ["git", "-C", str(reports), "ls-files", "-z", "--", "."],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return set()
    return {
        (reports / name.decode()).resolve()
        for name in result.stdout.split(b"\0")
        if name
    }


def prune(reports: Path, *, tracked: set[Path]) -> tuple[list[Path], int]:
    """Remove every generation but each suite's newest; return what went."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in reports.glob("*-0-*.json"):
        if GENERATION.search(path.name):
            groups[GENERATION.sub("", path.name)].append(path)
    removed: list[Path] = []
    freed = 0
    for paths in groups.values():
        paths.sort(key=os.path.getmtime)
        for old in paths[:-1]:
            if old.resolve() in tracked:
                continue
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
