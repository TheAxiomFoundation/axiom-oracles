"""The taxsim-csv population: TAXSIM-format CSV rows loaded verbatim as cases.

The fixture ``tests/fixtures/taxsim_csv/cps_households_sample.csv`` uses the
exact header of policyengine-taxsim's ``cps_households.csv`` and six rows:
state 0 (TAXSIM's "no state tax" code), two Alabama rows (SOI 1), Georgia
(SOI 11), a Maryland (SOI 21) married-filing-jointly itemizer, and a
California row whose secondary-taxpayer age cell is blank. Rows are not in
taxsimid order (104 precedes 103) so file order is observable.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import os
import random
import shutil
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner, attach_taxsim_inputs
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.populations import taxsim_csv as taxsim_csv_module
from axiom_oracles.populations.taxsim_csv import (
    TAXSIM_INPUT_COLUMNS,
    TaxsimCsvError,
    TaxsimCsvIntegrityError,
    load_taxsim_csv_cases,
    parse_taxsim_csv_origin,
    read_taxsim_csv,
    taxsim_csv_identity,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "taxsim_csv" / "cps_households_sample.csv"
)
FIXTURE_SHA256 = "bec30a98b3d8b2591e9dc39decd7100abe5134beccc7f812b803499552ea7b24"
FILE_ORDER = [
    "taxsim-101",
    "taxsim-102",
    "taxsim-104",
    "taxsim-103",
    "taxsim-105",
    "taxsim-106",
]
ORIGIN = {
    "repo": "PolicyEngine/policyengine-taxsim",
    "commit": "2b69146bfb2e16f83e1c021d72c4258d67872190",
    "path": "cps_households.csv",
}
FEDERAL = "us:tax/federal-income-tax#liability"

# The benchmark file the September pe-taxsim dashboard ran (commit 2b69146b,
# PR #1204) and the older file still on pe-taxsim main.
DASHBOARD_SHA256 = "ecabc8dd33e8b570fad21650745b9d94f6b51fc9780d9c59bb033ede7d16a689"
MAIN_SHA256 = "828b67406aec4189f9c1a4900527080b0ac18a380f6ae02fe521e9d3de414e55"


def _by_id(cases):
    return {case.case_id: case for case in cases}


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _fixture_header_and_rows() -> tuple[list[str], list[list[str]]]:
    with FIXTURE.open(newline="") as handle:
        records = list(csv.reader(handle))
    return records[0], records[1:]


# ---------------------------------------------------------------------------
# Verbatim rows
# ---------------------------------------------------------------------------


def test_fixture_pin_matches_its_bytes():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256


def test_rows_pass_through_verbatim_in_file_order():
    cases = load_taxsim_csv_cases(FIXTURE)

    assert [case.case_id for case in cases] == FILE_ORDER
    itemizer = _by_id(cases)["taxsim-104"].metadata["taxsim_input"]
    # Integer literals stay ints, every other number is a float, and blank
    # cells (age3..age11 here) are absent — nothing is added or renamed.
    assert itemizer == {
        "taxsimid": 104,
        "year": 2021,
        "state": 21,
        "mstat": 2,
        "page": 45,
        "sage": 43,
        "depx": 2,
        "pwages": 150000.0,
        "psemp": 0.0,
        "swages": 90000.0,
        "ssemp": 0.0,
        "dividends": 1200.0,
        "intrec": 0.0,
        "stcg": 0.0,
        "ltcg": 5000.0,
        "otherprop": 0,
        "nonprop": 0,
        "pensions": 0.0,
        "gssi": 0.0,
        "pui": 0.0,
        "sui": 0.0,
        "transfers": 0,
        "rentpaid": 0.0,
        "proptax": 9000.0,
        "otheritem": 4000,
        "childcare": 0.0,
        "mortgage": 18000.0,
        "scorp": 0.0,
        "idtl": 2,
        "age1": 12.0,
        "age2": 9.0,
    }
    for key, value in itemizer.items():
        assert type(value) in (int, float), key
    assert type(itemizer["otheritem"]) is int
    assert type(itemizer["age1"]) is float


def test_every_row_matches_the_csv_cells_exactly():
    header, records = _fixture_header_and_rows()
    cases = load_taxsim_csv_cases(FIXTURE)

    for case, record in zip(cases, records, strict=True):
        expected = {}
        for column, cell in zip(header, record, strict=True):
            if cell == "":
                continue
            expected[column] = int(cell) if cell.lstrip("-").isdigit() else float(cell)
        assert case.metadata["taxsim_input"] == expected
        assert case.period == "2021"
        assert case.metadata["population"] == "taxsim-csv"
        assert case.metadata["dataset_sha256"] == FIXTURE_SHA256


def test_blank_age_cell_is_omitted_not_zero_filled():
    case = _by_id(load_taxsim_csv_cases(FIXTURE))["taxsim-105"]

    assert "sage" not in case.metadata["taxsim_input"]
    assert case.metadata["selector_facts"]["sage"] is None
    assert case.metadata["taxsim_input"]["psemp"] == -1500.0


def test_state_zero_is_passed_through_and_scoped_national():
    case = _by_id(load_taxsim_csv_cases(FIXTURE))["taxsim-101"]

    assert case.metadata["taxsim_input"]["state"] == 0
    assert case.metadata["selector_facts"]["taxsim_state"] == 0
    assert case.metadata["selector_facts"]["state"] is None
    assert case.scope == GeographyScope(type="country", geoid="US")
    assert case.locale == "US"


@pytest.mark.parametrize(
    ("case_id", "soi", "usps", "fips"),
    [
        ("taxsim-102", 1, "AL", "01"),
        ("taxsim-103", 11, "GA", "13"),
        ("taxsim-104", 21, "MD", "24"),
        ("taxsim-105", 5, "CA", "06"),
    ],
)
def test_state_geography_comes_from_the_soi_crosswalk(case_id, soi, usps, fips):
    case = _by_id(load_taxsim_csv_cases(FIXTURE))[case_id]

    # SOI codes are not FIPS: GA is SOI 11 / FIPS 13, MD is SOI 21 / FIPS 24.
    assert case.metadata["taxsim_input"]["state"] == soi
    assert case.metadata["selector_facts"]["state"] == usps
    assert case.scope == GeographyScope(type="census_state", geoid=fips)
    assert case.locale == f"US-{usps}"


def test_selector_facts_follow_contract_c3():
    cases = load_taxsim_csv_cases(FIXTURE)
    facts = _by_id(cases)["taxsim-104"].metadata["selector_facts"]

    assert facts == {
        "taxsim_state": 21,
        "state": "MD",
        "year": 2021,
        "mstat": 2,
        "page": 45,
        "sage": 43,
        "depx": 2,
        "idtl": 2,
    }
    for case in cases:
        selector_facts = case.metadata["selector_facts"]
        # Flat JSON scalars only.
        assert json.loads(json.dumps(selector_facts)) == selector_facts
        assert all(
            value is None or isinstance(value, (int, float, str))
            for value in selector_facts.values()
        )


def test_cases_are_unweighted():
    for case in load_taxsim_csv_cases(FIXTURE):
        assert "household_weight" not in case.metadata


# ---------------------------------------------------------------------------
# Year override and identity
# ---------------------------------------------------------------------------


def test_year_override_rewrites_every_row_and_is_recorded():
    data = read_taxsim_csv(FIXTURE, period="2024")
    cases = data.select().cases

    assert {case.metadata["taxsim_input"]["year"] for case in cases} == {2024}
    assert all(type(case.metadata["taxsim_input"]["year"]) is int for case in cases)
    assert {case.period for case in cases} == {"2024"}
    assert {case.metadata["selector_facts"]["year"] for case in cases} == {2024}
    assert data.identity["year_override"] == 2024
    assert data.identity["years_in_file"] == [2021]
    # Only the year changes.
    original = _by_id(load_taxsim_csv_cases(FIXTURE))
    for case in cases:
        before = dict(original[case.case_id].metadata["taxsim_input"])
        before["year"] = 2024
        assert case.metadata["taxsim_input"] == before


def test_year_override_accepts_an_int_and_rejects_non_year_periods():
    assert read_taxsim_csv(FIXTURE, period=2025).identity["year_override"] == 2025
    for bad in ("2024-05", "24", "twenty"):
        with pytest.raises(TaxsimCsvError, match="YYYY"):
            read_taxsim_csv(FIXTURE, period=bad)


def test_identity_describes_the_file(tmp_path, monkeypatch):
    # A HOME that does not contain the checkout, so the path shows as given.
    monkeypatch.setenv("HOME", str(tmp_path))
    identity = taxsim_csv_identity(FIXTURE, origin=ORIGIN)
    header, _ = _fixture_header_and_rows()

    assert identity == {
        "source": "taxsim-csv",
        "path": str(FIXTURE),
        "filename": "cps_households_sample.csv",
        "sha256": FIXTURE_SHA256,
        "bytes": len(FIXTURE.read_bytes()),
        "rows": 6,
        "columns": header,
        "years_in_file": [2021],
        "year_override": None,
        "year_override_applied": False,
        "state_counts": {"0": 1, "1": 2, "5": 1, "11": 1, "21": 1},
        "origin": ORIGIN,
    }
    assert json.loads(json.dumps(identity)) == identity


def test_identity_path_is_home_relative_when_under_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    target = home / "data" / "cps_households.csv"
    target.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURE, target)
    monkeypatch.setenv("HOME", str(home))

    assert taxsim_csv_identity(target)["path"] == "$HOME/data/cps_households.csv"
    assert taxsim_csv_identity("~/data/cps_households.csv")["path"] == (
        "$HOME/data/cps_households.csv"
    )
    outside = tmp_path / "elsewhere.csv"
    shutil.copyfile(FIXTURE, outside)
    assert taxsim_csv_identity(outside)["path"] == str(outside)


def test_expected_sha256_is_checked_case_insensitively():
    identity = taxsim_csv_identity(FIXTURE, expected_sha256=FIXTURE_SHA256.upper())

    assert identity["sha256"] == FIXTURE_SHA256


def test_sha256_mismatch_fails_closed_before_any_row_is_parsed(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("no row may be parsed after a sha256 mismatch")

    monkeypatch.setattr(taxsim_csv_module, "_parse_row", forbidden)
    monkeypatch.setattr(taxsim_csv_module, "_case_for_row", forbidden)

    with pytest.raises(TaxsimCsvIntegrityError, match="sha256"):
        load_taxsim_csv_cases(FIXTURE, expected_sha256=DASHBOARD_SHA256)


def test_malformed_expected_sha256_is_rejected():
    with pytest.raises(TaxsimCsvError, match="64 hexadecimal"):
        read_taxsim_csv(FIXTURE, expected_sha256="ecabc8dd")


def test_origin_parsing_and_validation():
    assert (
        parse_taxsim_csv_origin(
            "PolicyEngine/policyengine-taxsim@"
            "2b69146bfb2e16f83e1c021d72c4258d67872190:cps_households.csv"
        )
        == ORIGIN
    )
    for bad in ("no-at-sign", "repo@deadbeef", "repo@not-a-sha:path"):
        with pytest.raises(TaxsimCsvError):
            parse_taxsim_csv_origin(bad)
    with pytest.raises(TaxsimCsvError, match="exactly repo, commit, and path"):
        read_taxsim_csv(FIXTURE, origin={"repo": "x", "commit": "abcdef1"})


# ---------------------------------------------------------------------------
# Fail-closed validation
# ---------------------------------------------------------------------------


def test_unknown_column_is_rejected_unless_allowed(tmp_path):
    header, records = _fixture_header_and_rows()
    path = _write_csv(
        tmp_path / "extra.csv",
        [*header, "fica_override"],
        [[*record, "7"] for record in records],
    )

    with pytest.raises(TaxsimCsvError, match="'fica_override'"):
        read_taxsim_csv(path)

    data = read_taxsim_csv(path, allow_unknown_columns=True)
    assert data.identity["unknown_columns"] == ["fica_override"]
    assert all(row["fica_override"] == 7 for row in data.rows)


def test_duplicate_taxsimid_is_rejected(tmp_path):
    header, records = _fixture_header_and_rows()
    duplicate = list(records[1])
    duplicate[0] = "101.0"  # same id as the first row, written as a float
    path = _write_csv(tmp_path / "dup.csv", header, [*records, duplicate])

    with pytest.raises(TaxsimCsvError, match=r"repeats taxsimid values \(101\)"):
        read_taxsim_csv(path)


@pytest.mark.parametrize(
    ("column", "cell", "message"),
    [
        ("pwages", "NA", "not a finite decimal number"),
        ("pwages", "inf", "not a finite decimal number"),
        ("pwages", "nan", "not a finite decimal number"),
        ("pwages", "1_000", "not a finite decimal number"),
        ("pwages", "٣", "not a finite decimal number"),
        ("state", "", "needs an integer state"),
        ("state", "52", "neither 0"),
        ("state", "-1", "neither 0"),
        ("state", "5.5", "needs an integer state"),
        ("taxsimid", "", "needs an integer taxsimid"),
        ("taxsimid", "7.5", "needs an integer taxsimid"),
        ("year", "", "blank year"),
        ("year", "2021.5", "needs an integer year"),
    ],
)
def test_bad_cells_fail_the_load(tmp_path, column, cell, message):
    header, records = _fixture_header_and_rows()
    records[2][header.index(column)] = cell
    path = _write_csv(tmp_path / "bad.csv", header, records)

    with pytest.raises(TaxsimCsvError, match=message):
        read_taxsim_csv(path)


def test_state_given_as_integral_float_is_accepted_verbatim(tmp_path):
    header, records = _fixture_header_and_rows()
    records[0][header.index("state")] = "0.0"
    path = _write_csv(tmp_path / "float-state.csv", header, records)

    case = read_taxsim_csv(path).select().cases[0]
    assert case.metadata["taxsim_input"]["state"] == 0.0
    assert type(case.metadata["taxsim_input"]["state"]) is float
    assert case.metadata["selector_facts"]["taxsim_state"] == 0


def test_structural_problems_fail_the_load(tmp_path):
    header, records = _fixture_header_and_rows()
    ragged = _write_csv(tmp_path / "ragged.csv", header, [records[0], records[1][:-1]])
    with pytest.raises(TaxsimCsvError, match="data row 2"):
        read_taxsim_csv(ragged)

    repeated = _write_csv(tmp_path / "repeated.csv", [*header, "pwages"], [])
    with pytest.raises(TaxsimCsvError, match="repeats header column"):
        read_taxsim_csv(repeated)

    bad_quote = tmp_path / "bad-quote.csv"
    bad_quote.write_text(",".join(header) + '\n"101,' + ",".join(records[0][1:]) + "\n")
    with pytest.raises(TaxsimCsvError, match="malformed"):
        read_taxsim_csv(bad_quote)

    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(TaxsimCsvError, match="no header"):
        read_taxsim_csv(empty)

    no_state = _write_csv(
        tmp_path / "no-state.csv",
        [name for name in header if name != "state"],
        [],
    )
    with pytest.raises(TaxsimCsvError, match="lacks required column"):
        read_taxsim_csv(no_state)


def test_missing_year_column_needs_a_period(tmp_path):
    header, records = _fixture_header_and_rows()
    year_index = header.index("year")
    path = _write_csv(
        tmp_path / "no-year.csv",
        [name for index, name in enumerate(header) if index != year_index],
        [
            [cell for index, cell in enumerate(record) if index != year_index]
            for record in records
        ],
    )

    with pytest.raises(TaxsimCsvError, match="lacks required column"):
        read_taxsim_csv(path)
    data = read_taxsim_csv(path, period="2023")
    assert data.identity["years_in_file"] == []
    assert {row["year"] for row in data.rows} == {2023}


def test_non_utf8_bytes_fail_the_load(tmp_path):
    path = tmp_path / "latin1.csv"
    path.write_bytes(FIXTURE.read_bytes().replace(b"30000.5", b"3\xff000.5"))

    with pytest.raises(TaxsimCsvError, match="not UTF-8"):
        read_taxsim_csv(path)


def test_utf8_bom_and_blank_lines_are_tolerated(tmp_path):
    raw = FIXTURE.read_bytes()
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbf" + raw + b"\n")

    data = read_taxsim_csv(path)
    assert data.identity["rows"] == 6
    assert data.identity["columns"][0] == "taxsimid"
    # The recorded sha256 covers the bytes on disk, BOM included.
    assert data.identity["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Scope filtering and sampling
# ---------------------------------------------------------------------------


def test_single_state_scope_keeps_only_that_state():
    data = read_taxsim_csv(FIXTURE)

    alabama = data.select(scope={"type": "census_state", "geoid": "01"})
    assert [case.case_id for case in alabama.cases] == ["taxsim-102", "taxsim-106"]
    assert alabama.summary["rows_in_scope"] == 2

    national = data.select(scope={"type": "country", "geoid": "US"})
    assert [case.case_id for case in national.cases] == FILE_ORDER
    assert [case.case_id for case in data.select().cases] == FILE_ORDER

    # A finer-than-state scope cannot place a state-only TAXSIM row.
    county = data.select(scope={"type": "census_county", "geoid": "01001"})
    assert county.cases == []
    # A non-US country scope holds none of them either.
    assert data.select(scope={"type": "country", "geoid": "UK"}).cases == []


def test_sample_is_deterministic_and_order_independent(tmp_path):
    data = read_taxsim_csv(FIXTURE)
    first = data.select(sample_size=3)
    second = data.select(sample_size=3)

    ids = [case.case_id for case in first.cases]
    assert ids == [case.case_id for case in second.cases]
    assert len(ids) == 3
    # Returned in file order.
    assert ids == [case_id for case_id in FILE_ORDER if case_id in ids]
    assert first.summary == {
        "scope": None,
        "rows_in_scope": 6,
        "sample_size": 3,
        "sample_seed": 0,
        "sample_method": "sha256-rank",
        "cases": 3,
    }

    header, records = _fixture_header_and_rows()
    shuffled = _write_csv(tmp_path / "shuffled.csv", header, list(reversed(records)))
    reordered = read_taxsim_csv(shuffled).select(sample_size=3)
    assert {case.case_id for case in reordered.cases} == set(ids)

    assert [case.case_id for case in data.select(sample_size=0).cases] == FILE_ORDER
    assert [case.case_id for case in data.select(sample_size=60).cases] == FILE_ORDER
    with pytest.raises(ValueError, match="non-negative"):
        data.select(sample_size=-1)


def test_sample_is_drawn_within_scope():
    data = read_taxsim_csv(FIXTURE)
    selection = data.select(
        scope={"type": "census_state", "geoid": "01"}, sample_size=1
    )

    assert len(selection.cases) == 1
    assert selection.cases[0].case_id in {"taxsim-102", "taxsim-106"}


# ---------------------------------------------------------------------------
# Invariants over generated files (seeded, exhaustive-style property checks)
# ---------------------------------------------------------------------------

_GENERATED_COLUMNS = ["taxsimid", "year", "state", "mstat", "page", "sage", "depx"]
_GENERATED_MONEY = ["pwages", "swages", "intrec", "pensions", "gssi", "age1", "age2"]


def _random_cell(rng: random.Random) -> str:
    kind = rng.randrange(6)
    if kind == 0:
        return ""
    if kind == 1:
        return str(rng.randrange(-5, 200_000))
    if kind == 2:
        return f"{rng.uniform(-1e4, 3e5):.6f}"
    if kind == 3:
        return f"{rng.randrange(0, 90)}.0"
    if kind == 4:
        return f"{rng.uniform(0, 1):.3e}"
    return str(rng.randrange(0, 5))


def _generated_csv(rng: random.Random, path: Path) -> Path:
    states = [0, *range(1, 52)]
    n_rows = rng.randrange(1, 40)
    ids = rng.sample(range(1, 10_000), n_rows)
    rows = []
    for taxsimid in ids:
        rows.append(
            [
                str(taxsimid) if rng.random() < 0.8 else f"{taxsimid}.0",
                rng.choice(["2021", "2022", "2024"]),
                str(rng.choice(states)),
                str(rng.choice([1, 2])),
                str(rng.randrange(18, 90)),
                rng.choice(["", "0", str(rng.randrange(18, 90))]),
                str(rng.randrange(0, 4)),
                *(_random_cell(rng) for _ in _GENERATED_MONEY),
            ]
        )
    return _write_csv(path, [*_GENERATED_COLUMNS, *_GENERATED_MONEY], rows)


def test_generated_files_satisfy_loader_invariants(tmp_path):
    rng = random.Random(20260925)
    for index in range(150):
        path = _generated_csv(rng, tmp_path / f"generated-{index}.csv")
        with path.open(newline="") as handle:
            records = list(csv.reader(handle))
        header, body = records[0], records[1:]
        data = read_taxsim_csv(path)

        # Row count and per-state counts account for every data row.
        assert data.identity["rows"] == len(body)
        assert sum(data.identity["state_counts"].values()) == len(body)
        # Each row holds exactly the non-blank cells, each equal to its text.
        for row, record in zip(data.rows, body, strict=True):
            nonblank = {c: v for c, v in zip(header, record, strict=True) if v}
            assert set(row) == set(nonblank)
            for column, text in nonblank.items():
                assert row[column] == float(text)
                assert type(row[column]) is (
                    int if "." not in text and "e" not in text else float
                )
        # The year override touches only the year.
        overridden = read_taxsim_csv(path, period="2030")
        for before, after in zip(data.rows, overridden.rows, strict=True):
            assert after == {**before, "year": 2030}
        # Samples are deterministic subsets in file order, sized min(k, n).
        k = rng.randrange(0, len(body) + 3)
        sample = [case.case_id for case in data.select(sample_size=k).cases]
        everything = [case.case_id for case in data.select().cases]
        assert sample == [case.case_id for case in data.select(sample_size=k).cases]
        assert len(sample) == (min(k, len(body)) if k else len(body))
        assert sample == [case_id for case_id in everything if case_id in set(sample)]
        # State filters partition the national rows.
        by_state = sum(
            len(data.select(scope={"type": "census_state", "geoid": fips}).cases)
            for fips in {
                case.metadata["scope"]["geoid"]
                for case in data.select().cases
                if case.metadata["scope"]["type"] == "census_state"
            }
        )
        assert by_state == len(body) - data.identity["state_counts"].get("0", 0)


def _assert_frame_matches_read_csv(rows, csv_path):
    # round_trip: pandas' default C float parser is not correctly rounded (on
    # the benchmark file it misses the cell text in the last digits), while
    # the loader keeps Python's correctly rounded float() of each cell.
    pd = pytest.importorskip("pandas")
    from_rows = pd.DataFrame(list(rows))
    from_csv = pd.read_csv(csv_path, float_precision="round_trip")
    default_dtypes = pd.read_csv(csv_path).dtypes
    assert len(from_rows) == len(from_csv)
    for column in from_csv.columns:
        if from_csv[column].isna().all():
            # An all-blank column has no cell to carry, so rows omit it.
            assert column not in from_rows.columns
            continue
        assert from_rows[column].dtype == from_csv[column].dtype, column
        assert from_rows[column].dtype == default_dtypes[column], column
        left = from_rows[column].tolist()
        right = from_csv[column].tolist()
        for a, b in zip(left, right, strict=True):
            if isinstance(b, float) and math.isnan(b):
                assert isinstance(a, float) and math.isnan(a), column
            else:
                assert a == b, column


def test_rows_frame_like_pandas_read_csv():
    """Differential: the benchmark worker reads its batch CSV with pd.read_csv."""
    _assert_frame_matches_read_csv(read_taxsim_csv(FIXTURE).rows, FIXTURE)


def test_generated_rows_frame_like_pandas_read_csv(tmp_path):
    pytest.importorskip("pandas")
    rng = random.Random(7)
    for index in range(40):
        path = _generated_csv(rng, tmp_path / f"pandas-{index}.csv")
        _assert_frame_matches_read_csv(read_taxsim_csv(path).rows, path)


# ---------------------------------------------------------------------------
# Column vocabulary drift guard
# ---------------------------------------------------------------------------


def test_column_set_covers_the_installed_taxsim_runner():
    if importlib.util.find_spec("policyengine_taxsim") is None:
        pytest.skip("policyengine-taxsim (the taxsim extra) is not installed")
    from policyengine_taxsim.runners.taxsim_runner import TaxsimRunner

    assert set(TaxsimRunner.ALL_COLUMNS) <= TAXSIM_INPUT_COLUMNS


def test_column_set_covers_the_benchmark_header():
    header, _ = _fixture_header_and_rows()
    assert set(header) <= TAXSIM_INPUT_COLUMNS


# ---------------------------------------------------------------------------
# Runner consumption: the rows reach both TAXSIM-row runners unchanged
# ---------------------------------------------------------------------------


class _EchoRunner:
    """Stands in for policyengine-taxsim's runners: echoes a fiitax per row."""

    frames: list = []

    def __init__(self, frame, *, offset: float = 0.0):
        self.frame = frame
        self.offset = offset
        _EchoRunner.frames.append(frame)

    def run(self, show_progress=False):
        del show_progress
        records = self.frame.to_dict(orient="records")
        return [
            {
                "taxsimid": record["taxsimid"],
                "fiitax": round(0.1 * float(record.get("pwages", 0) or 0), 2)
                + (self.offset if record["taxsimid"] == 104 else 0.0),
            }
            for record in records
        ]


def test_taxsim_row_runners_receive_rows_verbatim():
    cases = load_taxsim_csv_cases(FIXTURE, period="2024")

    # The CLI's preparation step leaves an attached row alone.
    prepared = attach_taxsim_inputs(cases)
    assert [case.metadata["taxsim_input"] for case in prepared] == [
        case.metadata["taxsim_input"] for case in cases
    ]

    for runner in (
        TaxsimPackageRunner(runner_factory=lambda frame: _EchoRunner(frame)),
        PolicyEngineTaxsimRunner(runner_factory=lambda frame: _EchoRunner(frame)),
    ):
        assert runner._input_rows(prepared) == [
            case.metadata["taxsim_input"] for case in cases
        ]
        results = runner.run_cases(prepared, [FEDERAL])
        assert [result.household_id for result in results] == FILE_ORDER
        state_zero = results[0]
        assert state_zero.values  # the state-0 row ran; nothing was dropped


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_module(monkeypatch):
    import importlib

    module = importlib.import_module("axiom_oracles.cli")
    _EchoRunner.frames = []

    def build_runner(engine, *args, **kwargs):
        del args, kwargs
        if engine == "taxsim":
            return TaxsimPackageRunner(runner_factory=lambda frame: _EchoRunner(frame))
        if engine == "policyengine":
            return PolicyEngineTaxsimRunner(
                runner_factory=lambda frame: _EchoRunner(frame, offset=100.0)
            )
        raise AssertionError(f"unexpected engine {engine}")

    monkeypatch.setattr(module, "_build_runner", build_runner)
    monkeypatch.delenv("AXIOM_TAXSIM_CSV", raising=False)
    return module


def _compare(cli_module, *extra, env=None):
    return CliRunner().invoke(
        cli_module.cli,
        [
            "compare",
            "policyengine",
            "taxsim",
            "--population",
            "taxsim-csv",
            "--concept",
            FEDERAL,
            *extra,
        ],
        env=env,
    )


def test_cli_compares_the_csv_rows_and_stamps_dataset_identity(cli_module):
    run = _compare(
        cli_module,
        "--taxsim-csv",
        str(FIXTURE),
        "--taxsim-csv-sha256",
        FIXTURE_SHA256,
        "--taxsim-csv-origin",
        f"{ORIGIN['repo']}@{ORIGIN['commit']}:{ORIGIN['path']}",
        "--period",
        "2024",
        "--sample-size",
        "0",
        "--json",
    )
    assert run.exit_code == 0, run.output
    report = json.loads(run.stdout[run.stdout.index("{") :])

    assert report["population"] == "taxsim-csv"
    assert report["case_count"] == 6
    identity = report["dataset_identity"]
    assert identity["sha256"] == FIXTURE_SHA256
    assert identity["rows"] == 6
    assert identity["year_override"] == 2024
    assert identity["years_in_file"] == [2021]
    assert identity["origin"] == ORIGIN
    assert identity["state_counts"] == {"0": 1, "1": 2, "5": 1, "11": 1, "21": 1}
    assert identity["selection"] == {
        "scope": {"type": "country", "geoid": "US"},
        "rows_in_scope": 6,
        "sample_size": None,
        "sample_seed": None,
        "sample_method": None,
        "cases": 6,
    }
    # Both engines saw every row, state 0 included, at the override year.
    for frame in _EchoRunner.frames:
        assert sorted(frame["taxsimid"].tolist()) == [101, 102, 103, 104, 105, 106]
        assert set(frame["year"].tolist()) == {2024}
        assert 0 in set(frame["state"].tolist())
    # The one engineered disagreement is the MFJ itemizer.
    assert [row["case_id"] for row in report["mismatches"]] == ["taxsim-104"]
    by_case = {case["case_id"]: case for case in report["cases"]}
    assert by_case["taxsim-101"]["metadata"]["taxsim_input"]["state"] == 0
    assert by_case["taxsim-104"]["metadata"]["selector_facts"]["state"] == "MD"


def test_cli_keeps_row_years_without_an_explicit_period(cli_module, tmp_path):
    output = tmp_path / "report.json"
    run = _compare(cli_module, "--taxsim-csv", str(FIXTURE), "--output", str(output))
    assert run.exit_code == 0, run.output
    # The console summary names the dataset.
    assert f"sha256 {FIXTURE_SHA256}" in run.output

    report = json.loads(output.read_text())
    assert report["dataset_identity"]["year_override"] is None
    # --sample-size defaults to 50, more than the fixture holds.
    assert report["dataset_identity"]["selection"]["sample_size"] == 50
    assert report["case_count"] == 6
    for frame in _EchoRunner.frames:
        assert set(frame["year"].tolist()) == {2021}


def test_cli_reads_the_path_from_the_environment(cli_module):
    run = _compare(cli_module, "--json", env={"AXIOM_TAXSIM_CSV": str(FIXTURE)})
    assert run.exit_code == 0, run.output
    report = json.loads(run.stdout[run.stdout.index("{") :])
    assert report["dataset_identity"]["filename"] == FIXTURE.name


def test_cli_requires_a_csv_path(cli_module):
    run = _compare(cli_module)
    assert run.exit_code != 0
    assert "needs --taxsim-csv PATH" in run.output


def test_cli_sha_mismatch_fails_closed_without_a_report(cli_module, tmp_path):
    output = tmp_path / "report.json"
    run = _compare(
        cli_module,
        "--taxsim-csv",
        str(FIXTURE),
        "--taxsim-csv-sha256",
        DASHBOARD_SHA256,
        "--output",
        str(output),
    )
    assert run.exit_code != 0
    assert "failed its sha256 check" in run.output
    assert not output.exists()
    assert _EchoRunner.frames == []


def test_cli_jurisdiction_narrows_to_one_state(cli_module):
    run = _compare(
        cli_module,
        "--taxsim-csv",
        str(FIXTURE),
        "--jurisdiction-fips",
        "01",
        "--json",
    )
    assert run.exit_code == 0, run.output
    report = json.loads(run.stdout[run.stdout.index("{") :])
    assert sorted(case["case_id"] for case in report["cases"]) == [
        "taxsim-102",
        "taxsim-106",
    ]
    assert report["dataset_identity"]["selection"]["scope"] == {
        "type": "census_state",
        "geoid": "01",
    }
    # The file identity still describes the whole file.
    assert report["dataset_identity"]["rows"] == 6


def test_cli_rejects_engines_that_cannot_read_taxsim_rows(cli_module):
    run = CliRunner().invoke(
        cli_module.cli,
        [
            "compare",
            "axiom",
            "taxsim",
            "--population",
            "taxsim-csv",
            "--taxsim-csv",
            str(FIXTURE),
        ],
    )
    assert run.exit_code != 0
    assert "only `compare policyengine taxsim`" in run.output


def test_cli_rejects_taxsim_csv_flags_on_other_populations(cli_module):
    run = CliRunner().invoke(
        cli_module.cli,
        [
            "compare",
            "policyengine",
            "taxsim",
            "--taxsim-csv-sha256",
            FIXTURE_SHA256,
        ],
    )
    assert run.exit_code != 0
    assert "apply only to --population taxsim-csv" in run.output


def test_load_population_cases_supports_taxsim_csv(cli_module):
    cases = cli_module._load_population_cases(
        population="taxsim-csv",
        suite_name="unused",
        scope=GeographyScope(type="country", geoid="US"),
        period="2022",
        sample_size=0,
        ecps_dataset=None,
        taxsim_csv=str(FIXTURE),
        taxsim_csv_sha256=FIXTURE_SHA256,
    )
    assert [case.case_id for case in cases] == FILE_ORDER
    assert {case.period for case in cases} == {"2022"}


# ---------------------------------------------------------------------------
# run_comparison.py plumbing
# ---------------------------------------------------------------------------


def _load_run_comparison():
    module_path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _taxsim_csv_params(**overrides):
    params = {
        "left": "policyengine",
        "right": "taxsim",
        "concept": FEDERAL,
        "population": "taxsim-csv",
        "sample_size": 0,
        "period": "2024",
        "taxsim_csv": {
            "path": str(FIXTURE),
            "sha256": FIXTURE_SHA256,
            "origin": dict(ORIGIN),
        },
    }
    params.update(overrides)
    return params


def _captured_compare_cmd(run_comparison, monkeypatch, tmp_path, params):
    calls = []

    def fake_run(cmd, *, check, cwd=None, env=None, **kwargs):
        del check, cwd, env, kwargs
        calls.append(cmd)

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)
    axiom_rules = tmp_path / "axiom-rules-engine"
    axiom_rules.mkdir(exist_ok=True)
    run_comparison._run_axiom_oracles_compare(
        {"axiom_rules_repo": str(axiom_rules), "parameters": params},
        tmp_path / "out.json",
    )
    return calls[-1]


def _flag(cmd, name):
    return cmd[cmd.index(name) + 1]


def test_run_comparison_passes_the_taxsim_csv_block(monkeypatch, tmp_path):
    run_comparison = _load_run_comparison()
    cmd = _captured_compare_cmd(
        run_comparison, monkeypatch, tmp_path, _taxsim_csv_params()
    )

    assert _flag(cmd, "--population") == "taxsim-csv"
    assert _flag(cmd, "--taxsim-csv") == str(FIXTURE.resolve())
    assert _flag(cmd, "--taxsim-csv-sha256") == FIXTURE_SHA256
    assert _flag(cmd, "--taxsim-csv-origin") == (
        f"{ORIGIN['repo']}@{ORIGIN['commit']}:{ORIGIN['path']}"
    )
    assert _flag(cmd, "--period") == "2024"
    assert "--taxsim-csv-allow-unknown-columns" not in cmd
    # TAXSIM runs through the pinned policyengine-taxsim distribution.
    assert any(str(arg).startswith("policyengine-taxsim==") for arg in cmd)


def test_run_comparison_omits_period_to_keep_row_years(monkeypatch, tmp_path):
    run_comparison = _load_run_comparison()
    params = _taxsim_csv_params()
    del params["period"]
    cmd = _captured_compare_cmd(run_comparison, monkeypatch, tmp_path, params)

    assert "--period" not in cmd


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (_taxsim_csv_params(taxsim_csv=None), "must declare"),
        (
            _taxsim_csv_params(taxsim_csv={"path": str(FIXTURE)}),
            "taxsim_csv.sha256` is required",
        ),
        (
            _taxsim_csv_params(
                taxsim_csv={"path": str(FIXTURE), "sha256": "x", "extra": 1}
            ),
            "unknown `taxsim_csv` keys",
        ),
        (
            _taxsim_csv_params(
                taxsim_csv={
                    "path": str(FIXTURE),
                    "sha256": FIXTURE_SHA256,
                    "origin": {"repo": "x"},
                }
            ),
            "exactly repo, commit",
        ),
        (
            _taxsim_csv_params(population="enhanced-cps"),
            "apply only to `population: taxsim-csv`",
        ),
    ],
)
def test_run_comparison_validates_the_taxsim_csv_block(
    monkeypatch, tmp_path, params, message
):
    run_comparison = _load_run_comparison()
    with pytest.raises(SystemExit, match=message):
        _captured_compare_cmd(run_comparison, monkeypatch, tmp_path, params)


def test_run_comparison_records_the_cli_dataset_identity_as_provenance(
    cli_module, monkeypatch, tmp_path
):
    """End to end: CLI report -> run_comparison provenance.dataset."""
    output = tmp_path / "report.json"
    run = _compare(
        cli_module,
        "--taxsim-csv",
        str(FIXTURE),
        "--taxsim-csv-sha256",
        FIXTURE_SHA256,
        "--taxsim-csv-origin",
        f"{ORIGIN['repo']}@{ORIGIN['commit']}:{ORIGIN['path']}",
        "--period",
        "2023",
        "--output",
        str(output),
    )
    assert run.exit_code == 0, run.output

    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    config = {
        "name": "taxsim-csv-demo",
        "runner": {
            "type": "axiom-oracles-compare",
            "axiom_rules_repo": str(tmp_path / "missing-rules"),
            "parameters": _taxsim_csv_params(period="2023"),
        },
    }
    block = run_comparison._build_run_provenance(
        config, "axiom-oracles-compare", output
    )
    dataset = block["dataset"]
    assert dataset["source"] == "taxsim-csv"
    assert dataset["sha256"] == FIXTURE_SHA256
    assert len(dataset["sha256"]) == 64
    assert dataset["bytes"] == len(FIXTURE.read_bytes())
    assert dataset["rows"] == 6
    assert dataset["year_override"] == 2023
    assert dataset["origin"] == ORIGIN
    assert dataset["state_counts"]["0"] == 1
    assert dataset["selection"]["cases"] == 6


def test_provenance_without_a_year_override_records_the_boolean(tmp_path):
    run_comparison = _load_run_comparison()
    identity = taxsim_csv_identity(FIXTURE)
    assert run_comparison._taxsim_csv_dataset_provenance(identity) == identity
    from axiom_oracles.provenance import build_provenance

    block = build_provenance(
        generated_by="test",
        dataset=run_comparison._taxsim_csv_dataset_provenance(identity),
    )
    # The null year_override is dropped by build_provenance, but the explicit
    # boolean keeps the "no override applied" fact in provenance.
    assert "year_override" not in block["dataset"]
    assert block["dataset"]["year_override_applied"] is False
    assert block["dataset"]["sha256"] == FIXTURE_SHA256


def test_empty_expected_sha256_is_rejected_not_ignored():
    with pytest.raises(TaxsimCsvError, match="64 hexadecimal"):
        load_taxsim_csv_cases(FIXTURE, expected_sha256="")


def test_fractional_selector_fact_is_rejected(tmp_path):
    text = FIXTURE.read_text().splitlines()
    header = text[0].split(",")
    row = text[1].split(",")
    row[header.index("mstat")] = "1.5"
    bad = tmp_path / "fractional.csv"
    bad.write_text("\n".join([text[0], ",".join(row)]) + "\n")
    with pytest.raises(TaxsimCsvError, match="mstat=1.5 is not an integer"):
        load_taxsim_csv_cases(bad)


# ---------------------------------------------------------------------------
# The real benchmark file (opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("AXIOM_TAXSIM_CSV")
    or not Path(os.environ["AXIOM_TAXSIM_CSV"]).expanduser().is_file(),
    reason="AXIOM_TAXSIM_CSV does not point at policyengine-taxsim's cps_households.csv",
)
def test_real_benchmark_file_loads_every_row():
    path = Path(os.environ["AXIOM_TAXSIM_CSV"]).expanduser()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

    started = time.process_time()
    data = read_taxsim_csv(path, period="2024", expected_sha256=sha256)
    cases = data.select().cases
    elapsed = time.process_time() - started

    assert len(cases) == 111_347
    assert data.identity["rows"] == 111_347
    assert data.identity["sha256"] == sha256
    assert data.identity["years_in_file"] == [2021]
    assert data.identity["year_override"] == 2024
    assert len({case.case_id for case in cases}) == 111_347
    if sha256 == DASHBOARD_SHA256:
        # PR #1204 recoded the 1,155 Alabama rows from state 0 to state 1.
        assert "0" not in data.identity["state_counts"]
        assert data.identity["state_counts"]["1"] == 1155
    elif sha256 == MAIN_SHA256:
        assert data.identity["state_counts"]["0"] == 1155
        assert "1" not in data.identity["state_counts"]
    assert sum(data.identity["state_counts"].values()) == 111_347
    print(f"loaded {len(cases)} cases in {elapsed:.1f}s CPU")

    unmodified = read_taxsim_csv(path)
    _assert_frame_matches_read_csv(unmodified.rows, path)
