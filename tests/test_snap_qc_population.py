"""Tests for the SNAP QC public-use-file loader.

The parsing tests write a small, schema-true CSV (real QC column names,
hand-built rows with internally consistent SNAP arithmetic) so they never touch
the real 92 MB file. Download tests stub ``requests`` through ``sys.modules``,
mirroring ``tests/test_populace_us_population.py``'s fake-``huggingface_hub``
pattern. One env-gated live test exercises the real FY2024 file.
"""

import csv
import hashlib
import io
import os
import sys
import types
import zipfile
from pathlib import Path

import pytest

from axiom_oracles.populations.snap_qc import (
    DATA_DIR_ENV_VAR,
    EARNED_INCOME_SOURCES,
    EXCLUSION_MFIP,
    EXCLUSION_SSI_CAP,
    UNEARNED_INCOME_SOURCES,
    QcExclusionLog,
    QcMember,
    SnapQcPin,
    UtilityTier,
    _download_qc_csv,
    _member_income_field_names,
    _utility_tier_from_sua1,
    load_qc_units,
)

# Real QC column names the fixture populates; every other column defaults to
# "." (missing) via the DictWriter restval below.
_PERSON_COLUMNS = [
    "AGE",
    "FSAFIL",
    "DIS",
    "DIS64_",
    "WAGES",
    "SOCSEC",
    "SSI",
    "TANF",
    "GA",
    "CSUPRT",
]
_FIXTURE_COLUMNS = [
    "STATE",
    "YRMONTH",
    "CERTHHSZ",
    "MN_FIP",
    "SSI_CAP",
    "RENT",
    "SUA1",
    "SUA2",
    "FSMEDEXP",
    "FSDEPDED",
    "FSCSEXP",
    "LIQRESOR",
    "CAT_ELIG",
    "HOMEDED",
    "HWGT",
    "FSEARN",
    "FSUNEARN",
    "FSGRINC",
    "FSNETINC",
    "FSSTDDED",
    "FSERNDED",
    "FSMEDDED",
    "FSCSDED",
    "FSSLTDED",
    "FSBEN",
    "MINIMUM_BEN",
    "FSMINBEN",
    "GROSSCRN",
    "NETSCRN",
    "FSGRTEST",
    "FSNETEST",
    "STATUS",
    "AMTERR",
] + [f"{prefix}{i}" for i in (1, 2) for prefix in _PERSON_COLUMNS]


# Row 0: Colorado 1-person elderly unit, $971 Social Security + SSI, HCSUA
# utilities, zero net income, one-person max allotment. Mirrors a real FY2024
# CO record; the $874 shelter deduction is the *uncapped* excess shelter
# deduction elderly/disabled units receive (FSSLTDED, not the reported SHELDED).
_ROW_ELDERLY_MAX_ALLOTMENT = {
    "STATE": "8",
    "YRMONTH": "202401",
    "CERTHHSZ": "1",
    "MN_FIP": "0",
    "SSI_CAP": "0",
    "AGE1": "66",
    "FSAFIL1": "1",
    "DIS1": "0",
    "SOCSEC1": "700",
    "SSI1": "271",
    "RENT": "700",
    "SUA1": "4",
    "SUA2": "1",
    "FSMEDEXP": "0",
    "FSDEPDED": "0",
    "FSCSEXP": "0",
    "LIQRESOR": "0",
    "CAT_ELIG": "1",
    "HOMEDED": "1",
    "HWGT": "1000.5",
    "FSEARN": "0",
    "FSUNEARN": "971",
    "FSGRINC": "971",
    "FSNETINC": "0",
    "FSSTDDED": "198",
    "FSERNDED": "0",
    "FSMEDDED": "0",
    "FSCSDED": "0",
    "FSSLTDED": "874",
    "FSBEN": "291",
    "MINIMUM_BEN": "23",
    "FSMINBEN": "0",
    "GROSSCRN": "1580",
    "NETSCRN": "1215",
    "FSGRTEST": "1",
    "FSNETEST": "1",
    "STATUS": "1",
    "AMTERR": "0",
}

# Row 1: Colorado 2-person unit, one $1,000-wage earner receiving $100 child
# support, a child receiving $100 TANF; limited (LUA) utilities; homeless
# applying actual shelter. Hand arithmetic: earned deduction 20% x 1000 = 200,
# standard 198, capped excess shelter 672 -> net 130, 2-person max 535 minus
# round(0.3 x 130)=39 -> benefit 496.
_ROW_EARNER_SHELTER = {
    "STATE": "8",
    "YRMONTH": "202402",
    "CERTHHSZ": "2",
    "MN_FIP": "0",
    "SSI_CAP": "0",
    "AGE1": "40",
    "FSAFIL1": "1",
    "DIS1": "0",
    "WAGES1": "1000",
    "CSUPRT1": "100",
    "AGE2": "10",
    "FSAFIL2": "1",
    "DIS2": "0",
    "TANF2": "100",
    "RENT": "800",
    "SUA1": "5",
    "SUA2": "1",
    "FSMEDEXP": "0",
    "FSDEPDED": "0",
    "FSCSEXP": "0",
    "LIQRESOR": "150",
    "CAT_ELIG": "0",
    "HOMEDED": "4",
    "HWGT": "750.0",
    "FSEARN": "1000",
    "FSUNEARN": "200",
    "FSGRINC": "1200",
    "FSNETINC": "130",
    "FSSTDDED": "198",
    "FSERNDED": "200",
    "FSMEDDED": "0",
    "FSCSDED": "0",
    "FSSLTDED": "672",
    "FSBEN": "496",
    "MINIMUM_BEN": "23",
    "FSMINBEN": "0",
    "GROSSCRN": "2137",
    "NETSCRN": "1644",
    "FSGRTEST": "1",
    "FSNETEST": "1",
    "STATUS": "2",
    "AMTERR": "25",
}

# Row 2: Minnesota MFIP unit — excluded (separate benefit procedure).
_ROW_MFIP_EXCLUDED = {
    "STATE": "27",
    "YRMONTH": "202401",
    "CERTHHSZ": "3",
    "MN_FIP": "1",
    "SSI_CAP": "0",
    "AGE1": "35",
    "FSAFIL1": "1",
    "TANF1": "500",
    "RENT": "900",
    "SUA1": "4",
    "SUA2": "1",
    "CAT_ELIG": "1",
    "HOMEDED": "1",
    "HWGT": "600.0",
    "FSBEN": "740",
    "STATUS": "1",
}

_FIXTURE_ROWS = [
    _ROW_ELDERLY_MAX_ALLOTMENT,
    _ROW_EARNER_SHELTER,
    _ROW_MFIP_EXCLUDED,
]


def _fixture_csv_text() -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_FIXTURE_COLUMNS, restval=".")
    writer.writeheader()
    for row in _FIXTURE_ROWS:
        writer.writerow(row)
    return buffer.getvalue()


def _write_fixture(directory: Path, fiscal_year: int = 2024) -> Path:
    path = directory / f"qc_pub_fy{fiscal_year}.csv"
    path.write_text(_fixture_csv_text(), encoding="utf-8")
    return path


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _install_fake_requests(monkeypatch, *, on_get):
    stub = types.ModuleType("requests")
    stub.get = on_get
    monkeypatch.setitem(sys.modules, "requests", stub)


def _zip_bytes(csv_text: str, *, member: str = "qc_pub_fy2024.csv") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, csv_text)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_elderly_max_allotment_unit_maps_every_field(tmp_path) -> None:
    _write_fixture(tmp_path)
    units, _ = load_qc_units(2024, data_dir=tmp_path)

    unit = next(u for u in units if u.certified_size == 1)
    assert unit.case_id == "2024-202401-0"
    assert unit.fiscal_year == 2024
    assert unit.yrmonth == 202401
    assert unit.state_fips == 8
    assert unit.utility_tier is UtilityTier.HEATING_COOLING
    assert unit.shelter_expense == 700.0
    assert unit.homeless is False
    assert unit.categorically_eligible is True
    assert unit.liquid_resources == 0.0
    assert unit.weight == 1000.5

    # Single elderly member: age >= 60 alone sets elderly_or_disabled.
    assert len(unit.members) == 1
    member = unit.members[0]
    assert member.index == 1
    assert member.age == 66
    assert member.elderly_or_disabled is True
    assert member.social_security == 700.0
    assert member.ssi == 271.0
    assert member.earned_income() == 0.0
    assert member.unearned_income() == 971.0
    assert unit.earned_income() == 0.0
    assert unit.unearned_income() == 971.0

    expected = unit.expected
    assert expected.benefit == 291.0
    assert expected.gross_income == 971.0
    assert expected.net_income == 0.0
    assert expected.standard_deduction == 198.0
    assert expected.earned_income_deduction == 0.0
    # shelter_deduction is FSSLTDED (final, uncapped for elderly), not SHELDED.
    assert expected.shelter_deduction == 874.0
    assert expected.minimum_benefit == 23.0
    assert expected.received_minimum_benefit is False
    assert expected.gross_screen == 1580.0
    assert expected.net_screen == 1215.0
    assert expected.passes_gross_test is True
    assert expected.passes_net_test is True
    assert expected.status == 1
    assert expected.error_amount == 0.0

    # The full source row is retained for disposition evidence.
    assert unit.raw["FSBEN"] == "291"
    assert unit.raw["SUA1"] == "4"


def test_earner_shelter_unit_splits_income_across_members(tmp_path) -> None:
    _write_fixture(tmp_path)
    units, _ = load_qc_units(2024, data_dir=tmp_path)

    unit = next(u for u in units if u.certified_size == 2)
    assert unit.case_id == "2024-202402-1"
    assert unit.utility_tier is UtilityTier.LIMITED
    assert unit.shelter_expense == 800.0
    assert unit.homeless is True  # HOMEDED = 4 (homeless, actual shelter)
    assert unit.categorically_eligible is False
    assert unit.liquid_resources == 150.0

    assert len(unit.members) == 2
    earner = unit.members[0]
    assert earner.age == 40
    assert earner.wages == 1000.0
    assert earner.child_support == 100.0
    assert earner.earned_income() == 1000.0
    assert earner.unearned_income() == 100.0
    assert earner.elderly_or_disabled is False

    child = unit.members[1]
    assert child.age == 10
    assert child.tanf == 100.0
    assert child.earned_income() == 0.0
    assert child.unearned_income() == 100.0
    assert child.elderly_or_disabled is False

    assert unit.earned_income() == 1000.0
    assert unit.unearned_income() == 200.0

    expected = unit.expected
    assert expected.benefit == 496.0
    assert expected.gross_income == 1200.0
    assert expected.net_income == 130.0
    assert expected.earned_income_deduction == 200.0
    assert expected.shelter_deduction == 672.0
    assert expected.status == 2
    assert expected.error_amount == 25.0


def test_missing_income_cells_parse_to_zero_not_none(tmp_path) -> None:
    _write_fixture(tmp_path)
    units, _ = load_qc_units(2024, data_dir=tmp_path)
    member = next(u for u in units if u.certified_size == 1).members[0]
    # Wages were "." for this member; a missing per-source cell means $0.
    assert member.wages == 0.0
    assert member.tanf == 0.0


def test_mfip_units_are_excluded_and_counted(tmp_path) -> None:
    _write_fixture(tmp_path)
    units, log = load_qc_units(2024, data_dir=tmp_path)

    assert {u.certified_size for u in units} == {1, 2}
    assert log.total_loaded == 2
    assert log.counts[EXCLUSION_MFIP] == 1
    assert log.total_excluded == 1
    # Every scanned row is accounted for exactly once.
    assert log.total_loaded + log.total_excluded == len(_FIXTURE_ROWS)


def test_include_special_programs_keeps_mfip_units(tmp_path) -> None:
    _write_fixture(tmp_path)
    units, log = load_qc_units(
        2024, data_dir=tmp_path, include_special_programs=True
    )
    assert len(units) == 3
    assert log.total_excluded == 0
    assert 3 in {u.certified_size for u in units}


def test_state_filter_scopes_without_counting_out_of_scope_rows(tmp_path) -> None:
    _write_fixture(tmp_path)
    co_units, co_log = load_qc_units(2024, data_dir=tmp_path, state_fips=8)
    # Only the two Colorado rows are in scope; the Minnesota MFIP row is neither
    # loaded nor counted as an exclusion (it is out of scope).
    assert len(co_units) == 2
    assert co_log.total_loaded == 2
    assert co_log.total_excluded == 0


def test_month_filter_selects_a_single_sample_month(tmp_path) -> None:
    _write_fixture(tmp_path)
    units, _ = load_qc_units(2024, data_dir=tmp_path, months=202402)
    assert [u.yrmonth for u in units] == [202402]


# ---------------------------------------------------------------------------
# Utility tier mapping
# ---------------------------------------------------------------------------


def test_sua1_maps_to_the_documented_utility_tiers() -> None:
    assert _utility_tier_from_sua1(1) is UtilityTier.NONE
    assert _utility_tier_from_sua1(3) is UtilityTier.HEATING_COOLING
    assert _utility_tier_from_sua1(4) is UtilityTier.HEATING_COOLING
    assert _utility_tier_from_sua1(8) is UtilityTier.HEATING_COOLING
    assert _utility_tier_from_sua1(5) is UtilityTier.LIMITED
    assert _utility_tier_from_sua1(6) is UtilityTier.TELEPHONE
    assert _utility_tier_from_sua1(7) is UtilityTier.ONE_UTILITY
    # Actual-expenses (2) and other (9) carry no standard allowance; missing
    # SUA1 (MFIP/SSI-CAP, excluded) also falls to none.
    assert _utility_tier_from_sua1(2) is UtilityTier.NONE
    assert _utility_tier_from_sua1(9) is UtilityTier.NONE
    assert _utility_tier_from_sua1(None) is UtilityTier.NONE


# ---------------------------------------------------------------------------
# Income source helpers
# ---------------------------------------------------------------------------


def test_member_income_fields_match_the_source_maps() -> None:
    # Guards against the declared QcMember float fields drifting away from the
    # earned/unearned source maps that drive parsing and the helpers.
    assert _member_income_field_names() == (
        set(EARNED_INCOME_SOURCES) | set(UNEARNED_INCOME_SOURCES)
    )
    assert len(EARNED_INCOME_SOURCES) == 4
    assert len(UNEARNED_INCOME_SOURCES) == 30


def test_earned_and_unearned_helpers_sum_the_right_subsets() -> None:
    member = QcMember(
        index=1,
        age=45,
        elderly_or_disabled=False,
        wages=800.0,
        self_employment=200.0,
        social_security=300.0,
        ssi=50.0,
        tanf=25.0,
    )
    assert member.earned_income() == 1000.0
    assert member.unearned_income() == 375.0


# ---------------------------------------------------------------------------
# Pins, download, verification, short-circuit
# ---------------------------------------------------------------------------


def test_unpinned_fiscal_year_is_refused_with_no_escape_hatch(tmp_path) -> None:
    _write_fixture(tmp_path, fiscal_year=2099)
    # Even with a readable file on disk, an unpinned year must not load.
    with pytest.raises(ValueError, match="No SNAP QC pin for fiscal year 2099"):
        load_qc_units(2099, data_dir=tmp_path)


def test_download_uses_browser_headers_and_verifies_hash(tmp_path, monkeypatch) -> None:
    csv_text = _fixture_csv_text()
    payload = _zip_bytes(csv_text)
    pin = SnapQcPin(
        fiscal_year=2024,
        url="https://snapqcdata.net/sites/default/files/2026-05/qcfy2024_csv.zip",
        sha256=hashlib.sha256(payload).hexdigest(),
        archive_member="qc_pub_fy2024.csv",
    )
    captured: dict[str, object] = {}

    def fake_get(url, *, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return _FakeResponse(payload)

    _install_fake_requests(monkeypatch, on_get=fake_get)
    path = _download_qc_csv(pin, tmp_path)

    assert path == tmp_path / "qc_pub_fy2024.csv"
    # The extracted CSV is byte-identical to the archived member and is loadable.
    assert path.read_bytes() == csv_text.encode("utf-8")
    downloaded_units, _ = load_qc_units(2024, data_dir=tmp_path)
    assert len(downloaded_units) == 2

    assert captured["url"] == pin.url
    headers = captured["headers"]
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert headers["Referer"] == "https://snapqcdata.net/datafiles"


def test_download_raises_on_sha256_mismatch(tmp_path, monkeypatch) -> None:
    payload = _zip_bytes(_fixture_csv_text())
    pin = SnapQcPin(
        fiscal_year=2024,
        url="https://snapqcdata.net/qcfy2024_csv.zip",
        sha256="0" * 64,
        archive_member="qc_pub_fy2024.csv",
    )

    def fake_get(url, *, headers, timeout):
        return _FakeResponse(payload)

    _install_fake_requests(monkeypatch, on_get=fake_get)
    with pytest.raises(RuntimeError, match="failed its sha256 check"):
        _download_qc_csv(pin, tmp_path)


def test_data_dir_short_circuits_the_download(tmp_path, monkeypatch) -> None:
    _write_fixture(tmp_path)

    def exploding_get(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("download must not be attempted when data is local")

    _install_fake_requests(monkeypatch, on_get=exploding_get)
    units, log = load_qc_units(2024, data_dir=tmp_path)
    assert log.total_loaded == 2


def test_env_var_directory_short_circuits_the_download(tmp_path, monkeypatch) -> None:
    _write_fixture(tmp_path)
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))

    def exploding_get(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("download must not be attempted when data is local")

    _install_fake_requests(monkeypatch, on_get=exploding_get)
    units, _ = load_qc_units(2024)
    assert len(units) == 2


def test_exclusion_log_summary_is_readable() -> None:
    log = QcExclusionLog()
    log.record_loaded()
    log.record_excluded(EXCLUSION_MFIP)
    log.record_excluded(EXCLUSION_SSI_CAP)
    log.record_excluded(EXCLUSION_SSI_CAP)
    assert log.total_loaded == 1
    assert log.total_excluded == 3
    summary = log.summary()
    assert "Loaded 1 units; excluded 3." in summary
    assert "MFIP" in summary
    assert "SSI-CAP" in summary


# ---------------------------------------------------------------------------
# Live test against the real FY2024 file (skips cleanly without the env var)
# ---------------------------------------------------------------------------


def test_live_fy2024_row_counts() -> None:
    data_dir = os.environ.get(DATA_DIR_ENV_VAR)
    if not data_dir or not (Path(data_dir) / "qc_pub_fy2024.csv").exists():
        pytest.skip(f"{DATA_DIR_ENV_VAR} not set to a directory with the FY2024 PUF")

    # Reads through the env-var directory (no data_dir argument).
    units, log = load_qc_units(2024)
    assert log.total_loaded + log.total_excluded == 44_891
    assert log.counts[EXCLUSION_MFIP] == 98
    assert log.counts[EXCLUSION_SSI_CAP] == 874
    assert log.total_loaded == 43_919
    assert len(units) == log.total_loaded

    co_units, co_log = load_qc_units(2024, state_fips=8)
    assert len(co_units) == 856
    assert co_log.total_excluded == 0

    # Member income reproduces the QC-constructed unit aggregates exactly.
    for unit in co_units:
        fsearn = float(unit.raw["FSEARN"]) if unit.raw["FSEARN"] not in ("", ".") else 0.0
        fsunearn = (
            float(unit.raw["FSUNEARN"])
            if unit.raw["FSUNEARN"] not in ("", ".")
            else 0.0
        )
        assert abs(unit.earned_income() - fsearn) < 0.5
        assert abs(unit.unearned_income() - fsunearn) < 0.5
