#!/usr/bin/env python
"""Bundle every dashboard report (minus per-case rows) into overview.json.

The front page previously fetched all manifest reports sequentially —
206 requests, 23.7 MB — of which 13.5 MB was embedded `cases` arrays that
no overview surface reads (the household drill lazy-loads its own chunked
artifacts under /data/cases/<suite>/ and never falls back to the embedded
rows). This bundle carries everything else (aggregates, summary,
mismatches, concepts, engines, provenance) in ONE fetch.

`--check` rebuilds the bundle from the committed reports and requires the
committed overview to equal it exactly — content, not file sizes. A
size-based check let a regenerated panel report with a byte-length-
identical predecessor ship a stale overview silently (sol stack review
r4: the UI preferentially consumes this bundle, so it carried a
superseded dispositioned block while every size matched).
"""

from __future__ import annotations

import hashlib
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
        payload = path.read_bytes()
        report = json.loads(payload)
        report.pop("cases", None)
        report["file"] = name
        reports.append(report)
        sources[name] = hashlib.sha256(payload).hexdigest()
    return {"schema": "axiom.dashboard_overview.v1", "sources": sources, "reports": reports}


def _serialize(bundle: dict) -> str:
    return json.dumps(bundle, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    bundle = build()
    if check:
        if not OUT.exists():
            print("overview.json missing; run scripts/generate_dashboard_overview.py")
            return 1
        # Byte-exact against the canonical serialization this script would
        # write. Parsed-value equality was not type-strict — Python's
        # `1 == True` accepted a numeric-to-boolean bundle edit (sol stack
        # review r5). Raw bytes, not read_text(): text-mode reads apply
        # universal-newline translation, so a text comparison accepted a
        # terminal LF -> CRLF rewrite of the bundle (sol stack review r6).
        if OUT.read_bytes() != _serialize(bundle).encode("utf-8"):
            print(
                "overview.json is stale (bytes differ from the canonical "
                "serialization of a fresh rebuild of the committed "
                "reports); run scripts/generate_dashboard_overview.py"
            )
            return 1
        print(f"overview OK: {len(bundle['reports'])} reports bundled")
        return 0
    # write_bytes for symmetry with the --check comparison: text-mode
    # writes translate "\n" to os.linesep, which would self-invalidate the
    # bundle on platforms where that is CRLF.
    OUT.write_bytes(_serialize(bundle).encode("utf-8"))
    size = OUT.stat().st_size / 1e6
    print(f"wrote overview.json: {len(bundle['reports'])} reports, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
