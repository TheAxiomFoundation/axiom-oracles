"""CI-side validator for the dk-satser ministry reference extract.

Trust model (us-tariff-panel pattern, see reference/dk-satser/README.md):
provenance stamps are mutable data files, so every load-bearing identity is
a reviewed constant here — the extract bytes, the full expected row sets,
and the internal arithmetic of the printed amounts. A legitimate refresh
updates these constants in the same reviewed diff; narrowing the reference
to force agreement is the failure mode this file exists to catch.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference" / "dk-satser"

EXPECTED_SATSER_SHA256 = (
    "de5f11a49e8ebead7551de35d3390d590ccf9b8be37316d86aae27a08acf13a7"
)
EXPECTED_THRESHOLD_SHA256 = (
    "c1eeefca0d12bd2e2e95116d63879e4935ecf1ea89ace495fd9b75cb4236d326"
)

# The ministry's printed annual amounts (svmn.dk historical overview
# 2022-2026, page stamped 12-01-2026; current-satser page for 2026/2027,
# stamped 12-01-2026). 2023 prints two values per band: base and including
# the Q1 engangsforhøjelse of 660 kr.
EXPECTED_ANNUAL: dict[tuple[int, str], tuple[int, int | None]] = {
    (2022, "0-2"): (18612, None),
    (2022, "3-6"): (14724, None),
    (2022, "7-17"): (11592, None),
    (2023, "0-2"): (18984, 19644),
    (2023, "3-6"): (15024, 15684),
    (2023, "7-17"): (11820, 12480),
    (2024, "0-2"): (20496, None),
    (2024, "3-6"): (16224, None),
    (2024, "7-17"): (12768, None),
    (2025, "0-2"): (21168, None),
    (2025, "3-6"): (16764, None),
    (2025, "7-17"): (13188, None),
    (2026, "0-2"): (21480, None),
    (2026, "3-6"): (16992, None),
    (2026, "7-17"): (13368, None),
    (2027, "0-2"): (21912, None),
    (2027, "3-6"): (17328, None),
    (2027, "7-17"): (13632, None),
}

# § 1 a aftrapningsgrænse series as printed (2010 grundbeløb per the
# statute; 2023 per the historical overview; 2025/2026 per the § 20
# regulated-amounts table, stamped 16-01-2026).
EXPECTED_THRESHOLDS = {2010: 700000, 2023: 852600, 2025: 917000, 2026: 961100}

# Printed quarterly/monthly amounts on the current-satser page. The
# ungeydelse (15-17) is monthly; the rest are quarterly.
EXPECTED_PERIOD_AMOUNTS = {
    2026: {"0-2_quarter": 5370, "3-6_quarter": 4248, "7-14_quarter": 3342, "15-17_month": 1114},
    2027: {"0-2_quarter": 5478, "3-6_quarter": 4332, "7-14_quarter": 3408, "15-17_month": 1136},
}

# LOV nr 1642 af 16/12/2025 § 1, nr. 1 moves the § 1, stk. 3, 7. pkt.
# rounding divisor from 12 to 24 with effect from 2026-01-01.
ROUND_12_YEARS = range(2022, 2026)
ROUND_24_YEARS = range(2026, 2028)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _annual_rows() -> dict[tuple[int, str], tuple[int, int | None]]:
    rows: dict[tuple[int, str], tuple[int, int | None]] = {}
    with (REFERENCE_DIR / "satser_annual.csv").open() as fh:
        for row in csv.DictReader(fh):
            supplement = row["annual_dkk_incl_2023_supplement"]
            rows[(int(row["year"]), row["age_band"])] = (
                int(row["annual_dkk"]),
                int(supplement) if supplement else None,
            )
    return rows


def test_extract_bytes_are_pinned() -> None:
    assert _sha256(REFERENCE_DIR / "satser_annual.csv") == EXPECTED_SATSER_SHA256
    assert (
        _sha256(REFERENCE_DIR / "aftrapning_threshold.csv")
        == EXPECTED_THRESHOLD_SHA256
    )


def test_annual_rows_match_reviewed_constants_exactly() -> None:
    assert _annual_rows() == EXPECTED_ANNUAL


def test_threshold_rows_match_reviewed_constants_exactly() -> None:
    rows: dict[int, int] = {}
    with (REFERENCE_DIR / "aftrapning_threshold.csv").open() as fh:
        for row in csv.DictReader(fh):
            rows[int(row["year"])] = int(row["threshold_dkk"])
    assert rows == EXPECTED_THRESHOLDS


def test_statutory_rounding_divisibility() -> None:
    for (year, _band), (base, with_supplement) in EXPECTED_ANNUAL.items():
        if year in ROUND_12_YEARS:
            assert base % 12 == 0, (year, base)
        if year in ROUND_24_YEARS:
            assert base % 24 == 0, (year, base)
        if with_supplement is not None:
            assert with_supplement - base == 660, (year, base, with_supplement)


def test_printed_period_amounts_reproduce_annual() -> None:
    for year, amounts in EXPECTED_PERIOD_AMOUNTS.items():
        assert amounts["0-2_quarter"] * 4 == EXPECTED_ANNUAL[(year, "0-2")][0]
        assert amounts["3-6_quarter"] * 4 == EXPECTED_ANNUAL[(year, "3-6")][0]
        assert amounts["7-14_quarter"] * 4 == EXPECTED_ANNUAL[(year, "7-17")][0]
        assert amounts["15-17_month"] * 12 == EXPECTED_ANNUAL[(year, "7-17")][0]


def test_provenance_stamp_consistency() -> None:
    provenance = json.loads((REFERENCE_DIR / "provenance.json").read_text())
    assert provenance["schema_version"] == "dk_satser.reference_provenance.v1"
    urls = {page["url"] for page in provenance["pages"]}
    assert all(url.startswith("https://svmn.dk/") for url in urls)
    assert provenance["period_amounts_as_printed"] == {
        str(year): amounts for year, amounts in EXPECTED_PERIOD_AMOUNTS.items()
    }
