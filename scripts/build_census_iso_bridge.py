#!/usr/bin/env python3
"""Build the census-code <-> ISO alpha-2 bridge for the us-tariff-panel suite.

The Yale Budget Lab panel keys countries by 4-digit Census (Schedule C)
codes; the rulespec-us tariff spine takes ISO alpha-2 origins. This script
parses the retained official concordance snapshot
(reference/us-tariff-panel/census_schedule_c_country.txt, from
https://www.census.gov/foreign-trade/schedules/c/country.txt) into
census_iso_bridge.csv and stamps provenance.

Run from the repo root::

    uv run python scripts/build_census_iso_bridge.py

Pass ``--fetch`` to refresh the snapshot from census.gov first (supervised
refresh only — the committed snapshot is the source of record for CI).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "reference" / "us-tariff-panel"
SNAPSHOT = OUT_DIR / "census_schedule_c_country.txt"
BRIDGE = OUT_DIR / "census_iso_bridge.csv"
PROVENANCE = OUT_DIR / "bridge_provenance.json"
SOURCE_URL = "https://www.census.gov/foreign-trade/schedules/c/country.txt"

ROW_RE = re.compile(r"^(\d{4})\s*\|\s*(.*?)\s*\|\s*([A-Z]{2})?\s*$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch", action="store_true",
        help="refresh the Schedule C snapshot from census.gov first",
    )
    args = parser.parse_args()

    if args.fetch:
        with urllib.request.urlopen(SOURCE_URL) as resp:  # noqa: S310
            SNAPSHOT.write_bytes(resp.read())
        print(f"refreshed snapshot from {SOURCE_URL}")

    if not SNAPSHOT.exists():
        print(f"missing snapshot: {SNAPSHOT} (run with --fetch)", file=sys.stderr)
        return 1

    rows: list[tuple[str, str, str]] = []
    produced = None
    for line in SNAPSHOT.read_text().splitlines():
        if produced is None:
            m = re.search(r"\[Produced:\s*([^\]]+)\]", line)
            if m:
                produced = m.group(1)
        m = ROW_RE.match(line)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3) or ""))
    if not rows:
        print("no rows parsed — snapshot format drift?", file=sys.stderr)
        return 1
    no_iso = [(c, n) for c, n, iso in rows if not iso]
    if no_iso:
        # Codes without an ISO counterpart would need bridge_artifact
        # dispositions in the comparison; surface them loudly.
        print(f"WARNING: {len(no_iso)} Schedule C codes lack an ISO code:")
        for c, n in no_iso:
            print(f"  {c}  {n}")

    with BRIDGE.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["census_code", "iso2", "name"])
        for code, name, iso in sorted(rows):
            writer.writerow([code, iso, name])
    print(f"wrote {len(rows)} rows to {BRIDGE}")

    PROVENANCE.write_text(
        json.dumps(
            {
                "schema_version": "us_tariff_panel.bridge_provenance.v1",
                "source": "U.S. Census Bureau, Schedule C - Country List",
                "source_url": SOURCE_URL,
                "source_produced": produced,
                "snapshot": SNAPSHOT.name,
                "snapshot_sha256": sha256(SNAPSHOT),
                "builder": "scripts/build_census_iso_bridge.py",
                "bridge_rows": len(rows),
                "rows_without_iso": len(no_iso),
                "bridge_sha256": sha256(BRIDGE),
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {PROVENANCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
