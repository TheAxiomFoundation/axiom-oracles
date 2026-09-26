"""Recorded releases fail closed; replay ordering and identity are preserved."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.adapters.taxsim.recorded import (
    DEFAULT_REPO,
    DEFAULT_TAG,
    PROVENANCE_SHA256_BY_YEAR,
    SHA256_BY_YEAR,
    RecordedReleaseError,
    fetch_release,
    load_recorded_release,
    release_sha256_by_year,
)
from axiom_oracles.populations.taxsim_csv import TAXSIM_INPUT_COLUMNS, read_taxsim_csv

FIXTURE = Path(__file__).parent / "fixtures/taxsim_csv/cps_households_sample.csv"
YEAR = 2024
PROFILE = "dashboard-2026-09"
FEDERAL = "us:tax/federal-income-tax#liability"
STATE = "us:tax/state-income-tax#liability"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _inputs():
    population = read_taxsim_csv(FIXTURE, period=YEAR)
    return population, population.select().cases


def _rows(cases):
    rows = []
    for index, case in enumerate(cases):
        inputs = case.metadata["taxsim_input"]
        for source in ("policyengine", "taxsim"):
            rows.append({
                **inputs, "source": source, "fiitax": 100 + index,
                "siitax": 20 + index, "niit": index, "v32": 30000,
                "cd2026090910": "ignored header stamp",
                "taxsim_binary_sha256": pins.resolve_binary(
                    inputs["state"], inputs["year"], "linux", PROFILE
                ) if source == "taxsim" else "",
            })
    return rows


def _write_release(directory, rows, population, **updates):
    columns = sorted(set().union(*(row.keys() for row in rows)))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = output.getvalue().encode()
    provenance = {
        "year": YEAR,
        "sourceSha256": population.identity["sha256"],
        "outputSha256": _sha(data),
        "taxsimBinarySha256": pins.resolve_binary(0, YEAR, "linux", PROFILE),
        "taxsimFallback": {"states": ["GA", "MD"], "years": [2024, 2025],
                           "sha256": pins.resolve_binary(11, YEAR, "linux", PROFILE)},
        "emulatorCommit": "a" * 40,
        "policyengineUsVersion": "2.6.17", "policyengineCoreVersion": "3.32.6",
        "assumeW2Wages": True, "disableSalt": False, "policyengineOutputDetail": 5,
        **updates,
    }
    (directory / f"comparison_results_{YEAR}.csv").write_bytes(data)
    (directory / f"provenance_{YEAR}.json").write_text(json.dumps(provenance))
    return _sha(data)


def _load(directory, cases, population, sha):
    return load_recorded_release(
        directory, cases=cases, dataset_identity=population.identity,
        year=YEAR, expected_sha256=sha, pin_profile=PROFILE,
    )


def test_replay_maps_emulator_columns_and_identity(tmp_path):
    population, cases = _inputs()
    sha = _write_release(tmp_path, _rows(cases), population)
    release = _load(tmp_path, cases, population, sha)
    left = release.adapter("policyengine").run_cases(cases, [FEDERAL, STATE])
    right = release.adapter("taxsim").run_cases(cases, [FEDERAL, STATE])
    assert left[0].values == {"income_tax": 100, "state_income_tax": 20}
    assert right[0].values == {"fiitax": 100, "siitax": 20}
    assert left[0].raw["niit"] == 0
    assert "cd2026090910" not in right[0].raw
    assert release.identity["sha256"] == sha
    assert release.identity["repo"] == DEFAULT_REPO
    assert release.identity["tag"] == DEFAULT_TAG
    assert release.policyengine_identity()["policyengineUsVersion"] == "2.6.17"
    assert release.policyengine_identity()["disableSalt"] is False
    identity = release.taxsim_identity()
    assert identity["pin_profile"] == PROFILE
    assert sum(binary["rows"] for binary in identity["binaries"]) == len(cases)
    assert {binary["scope"] for binary in identity["binaries"]} == {
        pins.resolve(0, YEAR, "linux", PROFILE).scope,
        pins.resolve(11, YEAR, "linux", PROFILE).scope,
    }
    for binary in identity["binaries"]:
        assert binary["platform"] == "linux"
        assert binary["build_observed"] is None
        assert binary["build"] == pins.pinned_binary(binary["sha256"]).build


@settings(max_examples=40, deadline=None)
@given(st.permutations(tuple(range(12))), st.permutations(tuple(range(6))))
def test_row_order_does_not_matter_and_result_ids_equal_case_set(row_order, case_order):
    population, cases = _inputs()
    rows = _rows(cases)
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        sha = _write_release(directory, [rows[i] for i in row_order], population)
        shuffled = [cases[i] for i in case_order]
        release = _load(directory, shuffled, population, sha)
        for source in ("taxsim", "policyengine"):
            results = release.adapter(source).run_cases(shuffled, [FEDERAL, STATE])
            assert [r.household_id for r in results] == [c.case_id for c in shuffled]
            assert {r.household_id for r in results} == {c.case_id for c in cases}
            assert {r.household_id: r.raw["fiitax"] for r in results} == {
                case.case_id: 100 + i for i, case in enumerate(cases)
            }


@settings(max_examples=40, deadline=None)
@given(st.sets(st.integers(0, 5), min_size=1))
def test_result_ids_equal_arbitrary_population_case_set(indices):
    population, cases = _inputs()
    chosen = [cases[i] for i in sorted(indices)]
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        sha = _write_release(directory, _rows(chosen), population)
        release = _load(directory, chosen, population, sha)
        for source in ("taxsim", "policyengine"):
            assert {result.household_id for result in release.adapter(source).run_cases(chosen)} == {
                case.case_id for case in chosen
            }


@settings(max_examples=100, deadline=None)
@given(st.integers(0, 11), st.sampled_from(sorted(TAXSIM_INPUT_COLUMNS)), st.integers(1, 1000000))
def test_any_single_input_cell_tamper_fails(row_index, column, increment):
    population, cases = _inputs()
    rows = _rows(cases)
    rows[row_index][column] = rows[row_index].get(column, 0) + increment
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        # Re-pin CSV/provenance: this tests input comparison independently of
        # the cryptographic check, including both sources and year overrides.
        sha = _write_release(directory, rows, population)
        with pytest.raises(RecordedReleaseError, match="input mismatch|case set mismatch"):
            _load(directory, cases, population, sha)


@settings(max_examples=50, deadline=None)
@given(st.integers(0, 100000), st.integers(1, 255))
def test_any_single_output_file_byte_tamper_fails(position, mask):
    population, cases = _inputs()
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        sha = _write_release(directory, _rows(cases), population)
        path = directory / f"comparison_results_{YEAR}.csv"
        data = bytearray(path.read_bytes())
        data[position % len(data)] ^= mask
        path.write_bytes(data)
        with pytest.raises(RecordedReleaseError, match="sha256 mismatch"):
            _load(directory, cases, population, sha)


@settings(max_examples=50, deadline=None)
@given(st.integers(0, 5), st.integers(0, 63), st.integers(1, 15))
def test_any_single_binary_sha_tamper_fails(case_index, position, increment):
    population, cases = _inputs()
    rows = _rows(cases)
    row = rows[2 * case_index + 1]
    sha = list(row["taxsim_binary_sha256"])
    sha[position] = format((int(sha[position], 16) + increment) % 16, "x")
    row["taxsim_binary_sha256"] = "".join(sha)
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        sha = _write_release(directory, rows, population)
        with pytest.raises(RecordedReleaseError, match="TAXSIM binary mismatch"):
            _load(directory, cases, population, sha)


@pytest.mark.parametrize("source", ("taxsim", "policyengine"))
def test_missing_extra_and_duplicate_counts_are_reported(tmp_path, source):
    population, cases = _inputs()
    rows = _rows(cases)
    removed = next(row for row in rows if row["source"] == source)
    rows.remove(removed)
    rows.append({**removed, "taxsimid": 999})
    rows.append({**removed, "taxsimid": 999})
    sha = _write_release(tmp_path, rows, population)
    with pytest.raises(RecordedReleaseError, match=rf"{source} missing=1 extra=1 duplicates=1"):
        _load(tmp_path, cases, population, sha)


def test_selecting_population_subset_rejects_extra_release_rows(tmp_path):
    population, cases = _inputs()
    sha = _write_release(tmp_path, _rows(cases), population)
    with pytest.raises(RecordedReleaseError, match="taxsim missing=0 extra=5"):
        _load(tmp_path, cases[:1], population, sha)


@pytest.mark.parametrize("column", ("outputSha256", "sourceSha256"))
def test_provenance_pins_fail_closed(tmp_path, column):
    population, cases = _inputs()
    sha = _write_release(tmp_path, _rows(cases), population, **{column: "a" * 64})
    with pytest.raises(RecordedReleaseError, match="sha256 mismatch|sourceSha256 differs"):
        _load(tmp_path, cases, population, sha)


@pytest.mark.parametrize("field", ("emulatorCommit", "policyengineUsVersion",
                                   "policyengineCoreVersion", "assumeW2Wages",
                                   "disableSalt", "policyengineOutputDetail"))
def test_missing_emulator_identity_fails_clearly(tmp_path, field):
    population, cases = _inputs()
    sha = _write_release(tmp_path, _rows(cases), population)
    path = tmp_path / f"provenance_{YEAR}.json"
    provenance = json.loads(path.read_text())
    provenance.pop(field)
    path.write_text(json.dumps(provenance))
    with pytest.raises(RecordedReleaseError, match=f"provenance {field}"):
        _load(tmp_path, cases, population, sha)


def test_no_row_sha_uses_provenance_default_and_applicable_fallback(tmp_path):
    population, cases = _inputs()
    rows = _rows(cases)
    for row in rows:
        row.pop("taxsim_binary_sha256")
    sha = _write_release(tmp_path, rows, population)
    release = _load(tmp_path, cases, population, sha)
    assert len(release.taxsim_identity()["binaries"]) == 2


def test_explicit_row_sha_takes_precedence_over_provenance_fallback(tmp_path):
    population, cases = _inputs()
    sha = _write_release(tmp_path, _rows(cases), population,
                         taxsimBinarySha256="a" * 64, taxsimFallback={})
    assert _load(tmp_path, cases, population, sha).taxsim_identity()["binaries"]


@pytest.mark.parametrize("relative_error,passes", [(2e-14, True), (9e-10, True), (2e-9, False)])
def test_only_float_parse_noise_is_accepted(tmp_path, relative_error, passes):
    population, cases = _inputs()
    rows = _rows(cases)
    row = next(row for row in rows if row.get("pwages", 0) > 0)
    row["pwages"] *= 1 + relative_error
    sha = _write_release(tmp_path, rows, population)
    if passes:
        _load(tmp_path, cases, population, sha)
    else:
        with pytest.raises(RecordedReleaseError, match="input mismatch"):
            _load(tmp_path, cases, population, sha)


def test_zero_input_has_no_absolute_tolerance(tmp_path):
    population, cases = _inputs()
    rows = _rows(cases)
    row = next(row for row in rows if row.get("swages") == 0)
    row["swages"] = 1e-20
    sha = _write_release(tmp_path, rows, population)
    with pytest.raises(RecordedReleaseError, match="input mismatch"):
        _load(tmp_path, cases, population, sha)


def test_fetch_verifies_both_assets_before_retaining_either(tmp_path):
    population, cases = _inputs()
    source = tmp_path / "source"
    source.mkdir()
    sha = _write_release(source, _rows(cases), population)
    provenance = (source / f"provenance_{YEAR}.json").read_bytes()
    csv_bytes = (source / f"comparison_results_{YEAR}.csv").read_bytes()
    destination = tmp_path / "destination"
    calls = []

    def download(url):
        calls.append(url)
        return provenance if url.endswith(".json") else csv_bytes

    kwargs = {"sha256_by_year": {YEAR: sha},
              "provenance_sha256_by_year": {YEAR: _sha(provenance)}}
    assets = fetch_release("Example/release", "release-tag", destination,
                           downloader=download, **kwargs)
    assert len(assets) == 2
    assert all(url.startswith("https://github.com/Example/release/releases/download/release-tag/")
               for url in calls)
    fetch_release("Example/release", "release-tag", destination,
                  downloader=lambda url: pytest.fail("verified assets should be reused"), **kwargs)
    failed_destination = tmp_path / "bad"
    with pytest.raises(RecordedReleaseError, match="sha256 mismatch"):
        fetch_release("Example/release", "release-tag", failed_destination,
                      downloader=lambda url: provenance if url.endswith(".json") else b"bad", **kwargs)
    assert not failed_destination.exists()
    with pytest.raises(RecordedReleaseError, match="sha256 mismatch"):
        fetch_release("Example/release", "release-tag", failed_destination,
                      downloader=lambda url: b"bad", **kwargs)
    assert not failed_destination.exists()


def test_known_release_has_pins_for_both_assets():
    assert release_sha256_by_year() == SHA256_BY_YEAR
    assert set(SHA256_BY_YEAR) == set(PROVENANCE_SHA256_BY_YEAR) == set(range(2021, 2026))
    with pytest.raises(RecordedReleaseError, match="No built-in"):
        release_sha256_by_year("Example/release", "untrusted")
