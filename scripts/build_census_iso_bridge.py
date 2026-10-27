#!/usr/bin/env python3
"""Build the census-code -> origin-code bridge for the us-tariff-panel suite.

The Yale Budget Lab panel keys countries by 4-digit Census (Schedule C)
codes; the rulespec-us tariff spine takes 2-letter origin codes. The origin
codes are ISO 3166-1 alpha-2 **plus the Census Schedule C extensions** listed
in :data:`SCHEDULE_C_EXTENSIONS` (codes Census assigns where ISO assigns
none, or splits a single ISO country). The composed tariff program matches
named countries by code and falls back to the statutory "any country"
baseline otherwise (HTS 9903.01.25), so extension codes receive the
statutorily correct default treatment and country-specific encoding gaps
surface as classified mismatches — never a silent generic remap.

This script parses the retained official concordance snapshot
(reference/us-tariff-panel/census_schedule_c_country.txt, from
https://www.census.gov/foreign-trade/schedules/c/country.txt) into
census_iso_bridge.csv and stamps provenance. It fails closed: the snapshot
is only replaced after the fetched copy validates, every candidate data line
must parse, codes must be unique, every code must map to an assigned ISO
alpha-2 or a documented Schedule C extension, and the bridge must cover
every country present in the committed Yale panel extract.

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
PANEL_EXTRACT = OUT_DIR / "yale_panel_slice.csv"
SOURCE_URL = "https://www.census.gov/foreign-trade/schedules/c/country.txt"

ROW_RE = re.compile(r"^(\d{4})\s*\|\s*(.*?)\s*\|\s*([A-Z]{2})?\s*$")
#: The single legitimate non-data pipe line in the concordance.
HEADER_RE = re.compile(r"^Code\s*\|\s*Name\s*\|\s*ISO Code\s*$")


def _is_candidate(line: str) -> bool:
    """A line that looks like data must parse — no silent skipping.

    Candidates are any line containing the pipe delimiter (except the one
    column-header line) or whose stripped form starts with a digit. This
    catches indented rows, malformed codes (e.g. ``737X``), and any other
    data-shaped drift: they become parse failures, never silent omissions.
    """
    if HEADER_RE.match(line.strip()):
        return False
    return "|" in line or line.strip()[:1].isdigit()

#: Assigned ISO 3166-1 alpha-2 codes (officially assigned entries only).
#: Frozen from pycountry 26.2.16 (ISO 3166-1 dataset); 249 codes. A bridge
#: alpha code must be in this set or in SCHEDULE_C_EXTENSIONS.
ISO_3166_ALPHA2 = frozenset({
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
    "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
    "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY",
    "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
    "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK",
    "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL",
    "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
    "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR",
    "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS",
    "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
    "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
    "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP",
    "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
    "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM",
    "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF",
    "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW",
    "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
})

#: Census Schedule C alpha codes with NO assigned ISO 3166-1 counterpart.
#: These pass through the bridge unchanged (see module docstring for why
#: that is safe); any new unassigned code fails the build until reviewed
#: and added here with a rationale.
SCHEDULE_C_EXTENSIONS = {
    "KV": "Kosovo — no assigned ISO 3166-1 code (XK is only a private-use "
          "convention); Census assigns KV.",
    "GZ": "Gaza Strip — ISO assigns PS to the State of Palestine as a "
          "whole; Census splits Gaza (GZ) and West Bank (WE).",
    "WE": "West Bank — ISO assigns PS to the State of Palestine as a "
          "whole; Census splits Gaza (GZ) and West Bank (WE).",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BridgeError(Exception):
    pass


def parse_snapshot(text: str) -> tuple[list[tuple[str, str, str]], str | None]:
    """Parse and validate a Schedule C snapshot. Raises BridgeError."""
    rows: list[tuple[str, str, str]] = []
    produced = None
    unparsed: list[str] = []
    for line in text.splitlines():
        if produced is None:
            m = re.search(r"\[Produced:\s*([^\]]+)\]", line)
            if m:
                produced = m.group(1)
        if not _is_candidate(line):
            continue
        m = ROW_RE.match(line)
        if m is None:
            unparsed.append(line)
            continue
        rows.append((m.group(1), m.group(2), m.group(3) or ""))
    if unparsed:
        raise BridgeError(
            f"{len(unparsed)} candidate data line(s) did not parse — "
            "snapshot format drift, refusing a partial bridge:\n  "
            + "\n  ".join(unparsed[:10])
        )
    if len(rows) < 200:
        raise BridgeError(
            f"only {len(rows)} rows parsed (Schedule C carries ~240 "
            "countries) — truncated or drifted snapshot"
        )
    codes = [c for c, _, _ in rows]
    dup_codes = sorted({c for c in codes if codes.count(c) > 1})
    if dup_codes:
        raise BridgeError(f"duplicate census codes: {dup_codes}")
    no_alpha = [(c, n) for c, n, alpha in rows if not alpha]
    if no_alpha:
        raise BridgeError(
            "Schedule C code(s) lack an alpha code; the bridge cannot "
            "silently drop them — resolve (or record a reviewed exception) "
            f"first: {no_alpha}"
        )
    alphas = [a for _, _, a in rows]
    dup_alphas = sorted({a for a in alphas if alphas.count(a) > 1})
    if dup_alphas:
        raise BridgeError(
            f"alpha code collisions (two census codes -> one origin): "
            f"{dup_alphas} — review before shipping a many-to-one bridge"
        )
    unknown = sorted(
        {a for a in alphas if a not in ISO_3166_ALPHA2 and a not in SCHEDULE_C_EXTENSIONS}
    )
    if unknown:
        raise BridgeError(
            f"alpha code(s) neither assigned ISO 3166-1 alpha-2 nor a "
            f"documented Schedule C extension: {unknown} — review and add "
            "to SCHEDULE_C_EXTENSIONS with a rationale if legitimate"
        )
    return rows, produced


def panel_country_codes() -> set[str]:
    """Distinct 4-digit country codes in the committed Yale panel extract."""
    with PANEL_EXTRACT.open(newline="") as fh:
        return {row["country"] for row in csv.DictReader(fh)}


def check_panel_coverage(rows: list[tuple[str, str, str]]) -> None:
    """Every committed-panel country must be bridged. Raises BridgeError.

    An uncovered code would mean silently dropped comparison rows.
    """
    if not PANEL_EXTRACT.exists():
        print(f"note: {PANEL_EXTRACT.name} absent; panel-coverage check skipped")
        return
    uncovered = sorted(panel_country_codes() - {c for c, _, _ in rows})
    if uncovered:
        raise BridgeError(
            f"panel extract countries missing from the bridge: {uncovered}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch", action="store_true",
        help="refresh the Schedule C snapshot from census.gov first",
    )
    args = parser.parse_args()

    retrieved_at = None
    if PROVENANCE.exists():
        retrieved_at = json.loads(PROVENANCE.read_text()).get("snapshot_retrieved_at")

    if args.fetch:
        with urllib.request.urlopen(SOURCE_URL) as resp:  # noqa: S310
            fetched = resp.read()
        # ALL validation — structural parse AND panel coverage — runs on the
        # fetched bytes BEFORE the retained snapshot is replaced: a response
        # that parses but has lost a panel country must never clobber the
        # source of record. The replacement itself is atomic (temp + rename).
        try:
            fetched_rows, _ = parse_snapshot(fetched.decode())
            check_panel_coverage(fetched_rows)
        except BridgeError as exc:
            print(f"fetched snapshot rejected, retained copy kept: {exc}",
                  file=sys.stderr)
            return 1
        tmp = SNAPSHOT.with_suffix(".txt.tmp")
        tmp.write_bytes(fetched)
        tmp.replace(SNAPSHOT)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"refreshed snapshot from {SOURCE_URL}")

    if not SNAPSHOT.exists():
        print(f"missing snapshot: {SNAPSHOT} (run with --fetch)", file=sys.stderr)
        return 1

    try:
        rows, produced = parse_snapshot(SNAPSHOT.read_text())
        check_panel_coverage(rows)
    except BridgeError as exc:
        print(f"snapshot invalid: {exc}", file=sys.stderr)
        return 1

    extensions_used = sorted(
        {a for _, _, a in rows if a in SCHEDULE_C_EXTENSIONS}
    )
    with BRIDGE.open("w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["census_code", "iso2", "name"])
        for code, name, alpha in sorted(rows):
            writer.writerow([code, alpha, name])
    print(f"wrote {len(rows)} rows to {BRIDGE}")

    PROVENANCE.write_text(
        json.dumps(
            {
                "schema_version": "us_tariff_panel.bridge_provenance.v2",
                "source": "U.S. Census Bureau, Schedule C - Country List",
                "source_url": SOURCE_URL,
                "source_produced": produced,
                "snapshot": SNAPSHOT.name,
                "snapshot_sha256": sha256(SNAPSHOT),
                "snapshot_retrieved_at": retrieved_at,
                "builder": "scripts/build_census_iso_bridge.py",
                "builder_sha256": sha256(Path(__file__)),
                "bridge_rows": len(rows),
                "schedule_c_extensions": {
                    a: SCHEDULE_C_EXTENSIONS[a] for a in extensions_used
                },
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
