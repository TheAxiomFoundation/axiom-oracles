#!/usr/bin/env python
"""Delete superseded full-report generations, keeping the newest per suite.

Full-evidence reports (raw input records per household) run to gigabytes
for the larger generic-projector suites; without retention the weekly
regeneration accumulates tens of GB of dead generations locally.
reports/ is gitignored — this touches nothing committed.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def main() -> int:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in REPORTS.glob("*-0-*.json"):
        base = re.sub(r"-0-\d{4}-\d{2}-\d{2}\.json$", "", path.name)
        groups[base].append(path)
    freed = 0
    removed = 0
    for paths in groups.values():
        paths.sort(key=os.path.getmtime)
        for old in paths[:-1]:
            freed += old.stat().st_size
            old.unlink()
            removed += 1
    print(f"pruned {removed} superseded report(s), freed {freed / 1e9:.1f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
