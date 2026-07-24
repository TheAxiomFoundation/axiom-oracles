#!/usr/bin/env python
"""Bundle every dashboard report (minus per-case rows) into overview.json.

The front page previously fetched all manifest reports sequentially —
206 requests, 23.7 MB — of which 13.5 MB was embedded `cases` arrays that
no overview surface reads (the household drill lazy-loads its own chunked
artifacts under /data/cases/<suite>/ and never falls back to the embedded
rows). This bundle carries everything else (aggregates, summary,
mismatches, concepts, engines, provenance) in ONE fetch.

`--check` verifies the committed bundle is consistent with the manifest
(same file set, same source sizes) so a regenerated report can't ship with
a stale overview silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "dashboard" / "public" / "data"
OUT = DATA / "overview.json"


def build() -> dict:
    manifest = json.loads((DATA / "manifest.json").read_text())
    reports = []
    sources = {}
    for name in manifest.get("reports", []):
        path = DATA / name
        if not path.exists():
            continue
        report = json.loads(path.read_text())
        report.pop("cases", None)
        report["file"] = name
        reports.append(report)
        sources[name] = path.stat().st_size
    return {"schema": "axiom.dashboard_overview.v1", "sources": sources, "reports": reports}


def main() -> int:
    check = "--check" in sys.argv
    bundle = build()
    if check:
        if not OUT.exists():
            print("overview.json missing; run scripts/generate_dashboard_overview.py")
            return 1
        committed = json.loads(OUT.read_text())
        if committed.get("sources") != bundle["sources"]:
            print(
                "overview.json is stale (report set or sizes changed); "
                "run scripts/generate_dashboard_overview.py"
            )
            return 1
        print(f"overview OK: {len(bundle['reports'])} reports bundled")
        return 0
    OUT.write_text(json.dumps(bundle, sort_keys=True) + "\n")
    size = OUT.stat().st_size / 1e6
    print(f"wrote overview.json: {len(bundle['reports'])} reports, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
