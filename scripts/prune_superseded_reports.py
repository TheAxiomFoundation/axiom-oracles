#!/usr/bin/env python
"""Delete superseded full-report generations, keeping the newest per suite.

Full-evidence reports (raw input records per household) run to gigabytes
for the larger generic-projector suites; without retention the weekly
regeneration accumulates tens of GB of dead generations locally.

A run writes its raw report ``<suite>-0-YYYY-MM-DD.json`` and then its FULL
v2 sibling ``<suite>-0-YYYY-MM-DD-v2.json`` (``run_comparison.py``'s
``_write_full_v2_report``). Raw reports and each ``-vN`` kind are pruned as
separate groups per suite, so the newest raw report and the newest v2
report each survive: a v2 never deletes its own run's raw report, and a run
that fails before writing its v2 leaves the previous v2 in place. reports/ is
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
GENERATION = re.compile(r"-0-\d{4}-\d{2}-\d{2}(?P<suffix>-v\d+)?\.json$")


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
