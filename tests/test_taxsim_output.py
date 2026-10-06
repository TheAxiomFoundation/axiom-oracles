"""The TAXSIM stdout parser and the adapter's per-case attribution.

Fixtures under ``tests/fixtures/taxsim/`` are verbatim captures from the
pinned macOS binary (``taxsimtest-osx.exe``, header ``cdate-20260521``,
SHA-256 in ``taxsim_pins.json``) run on the ``*_input.csv`` next to them on
2026-09-27. Expected values below are read off those captures, not off the
parser under test. The binary writes six copies of a ``" d2 ..."`` line before
the CSV row of every Utah record whose primary filer is 73 or older; with
``idtl=0`` they precede the header itself.
"""

from __future__ import annotations

import logging
import math
import platform
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.taxsim import (
    DIAGNOSTICS_KEY,
    TaxsimExecution,
    TaxsimOutputError,
    TaxsimPackageRunner,
    parse_taxsim_stdout,
    pins,
)
from axiom_oracles.core.case import Case

FIXTURES = Path(__file__).parent / "fixtures" / "taxsim"

# Verbatim from utah_elderly_idtl2_stdout.txt (single filer, joint filer).
D2_SINGLE_30K = " d2       29126       25000         103         346"
D2_JOINT_30K_SS = " d2       33009       32000          25         874"
D2_SINGLE_30K_SS = " d2       38446       25000         336         113"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _input_rows(name: str) -> list[dict[str, int]]:
    header, *lines = _fixture(name).splitlines()
    columns = header.split(",")
    return [
        dict(zip(columns, (int(value) for value in line.split(",")))) for line in lines
    ]


def _cases(name: str) -> list[Case]:
    return [
        Case(
            case_id=f"case-{row['taxsimid']}",
            period=str(row["year"]),
            metadata={"taxsim_input": row},
        )
        for row in _input_rows(name)
    ]


def _executor(stdout: str, *, stderr: str = "", returncode: int = 0):
    def execute(frame):
        del frame
        return TaxsimExecution(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            binary="taxsimtest-fake.exe",
        )

    return execute


# --- parser -----------------------------------------------------------------


def test_parse_attributes_diagnostics_to_the_row_that_follows_them() -> None:
    parsed = parse_taxsim_stdout(_fixture("utah_elderly_idtl2_stdout.txt"))

    assert parsed.header[:3] == ("taxsimid", "year", "state")
    assert parsed.header[-1] == "cdate-20260521"
    assert [record.id_key for record in parsed.records] == ["1", "2", "3", "4", "5"]
    by_id = {record.id_key for record in parsed.records}
    assert by_id == {"1", "2", "3", "4", "5"}
    records = {record.id_key: record for record in parsed.records}

    # California, age 40: a plain row.
    assert records["1"].diagnostics == ()
    assert records["1"].line_number == 2
    assert records["1"].values["fiitax"] == 3820.0
    assert records["1"].values["siitax"] == 980.7
    # Utah, single, age 73: six identical diagnostic lines precede its row.
    assert records["2"].diagnostics == (D2_SINGLE_30K,) * 6
    assert records["2"].line_number == 9
    assert records["2"].values["fiitax"] == 585.0
    assert records["2"].values["siitax"] == 49.88
    # Utah, single, age 72: nothing.
    assert records["3"].diagnostics == ()
    assert records["3"].values["siitax"] == 407.13
    # Utah, joint, both 74, with Social Security.
    assert records["4"].diagnostics == (D2_JOINT_30K_SS,) * 6
    assert records["4"].values["fiitax"] == 0.0
    assert records["4"].values["v13"] == 35500.0
    # Utah, single, age 80, with Social Security.
    assert records["5"].diagnostics == (D2_SINGLE_30K_SS,) * 6
    assert records["5"].values["fiitax"] == 1606.0
    assert parsed.trailing_diagnostics == ()
    assert parsed.diagnostic_count == 18
    # Values are numbers, never NaN.
    for record in parsed.records:
        for column, value in record.values.items():
            assert isinstance(value, (int, float)), (record.id_key, column)
            assert not math.isnan(value), (record.id_key, column)


def test_parse_keeps_diagnostics_written_before_the_header() -> None:
    parsed = parse_taxsim_stdout(_fixture("utah_elderly_idtl0_stdout.txt"))

    assert parsed.header == (
        "taxsimid",
        "year",
        "state",
        "fiitax",
        "siitax",
        "fica",
        "frate",
        "srate",
        "ficar",
        "tfica",
        "cdate-20260521",
    )
    assert [record.id_key for record in parsed.records] == ["7", "8"]
    utah, california = parsed.records
    assert utah.diagnostics == (D2_SINGLE_30K,) * 6
    assert utah.line_number == 8
    assert utah.values == {
        "taxsimid": 7.0,
        "year": 2026,
        "state": 45,
        "fiitax": 585.0,
        "siitax": 49.88,
        "fica": 4590.0,
        "frate": 0.0,
        "srate": 0.0,
        "ficar": 0.0,
        "tfica": 2295.0,
        "cdate-20260521": 0,
    }
    assert california.diagnostics == ()
    assert california.values["fiitax"] == 3820.0


def test_parse_requires_a_header() -> None:
    with pytest.raises(TaxsimOutputError, match="no header line"):
        parse_taxsim_stdout(" d2 1 2 3 4\n")


def test_parse_treats_short_rows_nan_ids_and_blank_lines_correctly() -> None:
    text = "\n".join(
        [
            "taxsimid,year,state,fiitax",
            "1.,2026,5,10.00",
            "",
            "2.,2026,5",  # numeric first field, wrong width: not a row
            "nan,2026,5,1.00",  # NaN parses as float but cannot key a case
            "3.,2026,5,30.00",
            "trailing text",
            "",
        ]
    )

    parsed = parse_taxsim_stdout(text)

    assert [record.id_key for record in parsed.records] == ["1", "3"]
    assert parsed.records[1].diagnostics == ("2.,2026,5", "nan,2026,5,1.00")
    assert parsed.trailing_diagnostics == ("trailing text",)


# --- adapter ----------------------------------------------------------------


def test_runner_maps_every_case_and_keeps_diagnostics_on_raw(caplog) -> None:
    cases = _cases("utah_elderly_idtl2_input.csv")
    runner = TaxsimPackageRunner(
        executor=_executor(_fixture("utah_elderly_idtl2_stdout.txt"))
    )

    with caplog.at_level(logging.WARNING, logger="axiom_oracles.adapters.taxsim"):
        results = runner.run_cases(cases, variables=["fiitax", "siitax"])

    assert [result.household_id for result in results] == [
        "case-1",
        "case-2",
        "case-3",
        "case-4",
        "case-5",
    ]
    assert all(result.engine == "taxsim" for result in results)
    assert all(result.errors == () for result in results)
    assert results[1].values == {"fiitax": 585.0, "siitax": 49.88}
    assert results[0].values == {"fiitax": 3820.0, "siitax": 980.7}
    assert DIAGNOSTICS_KEY not in results[0].raw
    assert results[1].raw[DIAGNOSTICS_KEY] == [D2_SINGLE_30K] * 6
    assert results[3].raw[DIAGNOSTICS_KEY] == [D2_JOINT_30K_SS] * 6
    assert results[4].raw[DIAGNOSTICS_KEY] == [D2_SINGLE_30K_SS] * 6
    assert results[1].raw["v13"] == 18150.0
    [warning] = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert "18 non-record stdout line(s)" in warning.getMessage()
    assert "3 record(s) (taxsimid=2, 4, 5)" in warning.getMessage()


def test_runner_reports_a_case_with_no_output_row_as_an_error(caplog) -> None:
    lines = _fixture("utah_elderly_idtl2_stdout.txt").splitlines()
    without_third = [line for line in lines if not line.startswith("3.,")]
    runner = TaxsimPackageRunner(executor=_executor("\n".join(without_third)))

    with caplog.at_level(logging.WARNING, logger="axiom_oracles.adapters.taxsim"):
        results = runner.run_cases(
            _cases("utah_elderly_idtl2_input.csv"), variables=["fiitax"]
        )

    assert [result.household_id for result in results] == [
        "case-1",
        "case-2",
        "case-3",
        "case-4",
        "case-5",
    ]
    missing = results[2]
    assert missing.values == {}
    assert missing.errors == ("TAXSIM produced no output row for taxsimid=3",)
    assert [result.errors for result in results if result is not missing] == [()] * 4
    assert results[3].values == {"fiitax": 0.0}
    assert any(
        "no output row for 1 of 5" in record.getMessage() for record in caplog.records
    )


def test_runner_attaches_trailing_diagnostics_to_the_missing_last_case() -> None:
    lines = _fixture("utah_elderly_idtl2_stdout.txt").splitlines()
    without_last = [line for line in lines if not line.startswith("5.,")]
    runner = TaxsimPackageRunner(executor=_executor("\n".join(without_last)))

    results = runner.run_cases(
        _cases("utah_elderly_idtl2_input.csv"), variables=["fiitax"]
    )

    assert results[4].household_id == "case-5"
    [error] = results[4].errors
    assert error.startswith("TAXSIM produced no output row for taxsimid=5")
    assert f"trailing stdout lines: {[D2_SINGLE_30K_SS] * 6!r}" in error


def test_runner_refuses_rows_that_match_no_case() -> None:
    text = _fixture("utah_elderly_idtl2_stdout.txt") + (
        "99.,2026,45,1.00" + ",.00" * 49 + ",0\n"
    )
    runner = TaxsimPackageRunner(executor=_executor(text))

    with pytest.raises(
        RuntimeError,
        match=r"1 output row\(s\) matching no submitted case: taxsimid=99 "
        r"\(stdout line 25\) \(binary taxsimtest-fake.exe\)",
    ):
        runner.run_cases(_cases("utah_elderly_idtl2_input.csv"))


def test_runner_refuses_duplicate_rows() -> None:
    lines = _fixture("utah_elderly_idtl2_stdout.txt").splitlines()
    [third] = [line for line in lines if line.startswith("3.,")]
    runner = TaxsimPackageRunner(executor=_executor("\n".join([*lines, third])))

    with pytest.raises(
        RuntimeError,
        match=r"more than one output row for taxsimid=3 \(stdout lines 10 and 25\)",
    ):
        runner.run_cases(_cases("utah_elderly_idtl2_input.csv"))


def test_runner_refuses_unattributable_trailing_output() -> None:
    text = _fixture("utah_elderly_idtl2_stdout.txt") + " d9 1 2 3\n"
    runner = TaxsimPackageRunner(executor=_executor(text))

    with pytest.raises(RuntimeError, match="cannot be attributed to a case"):
        runner.run_cases(_cases("utah_elderly_idtl2_input.csv"))


def test_runner_reports_a_nonzero_exit_with_stderr() -> None:
    # Verbatim from the pinned Linux build fed a 2026 record (2026-09-27).
    stdout = " TAXSIM: Federal tax calculator available 1960 - 2024 only.\n"
    runner = TaxsimPackageRunner(
        executor=_executor(stdout, stderr="STOP 1\n", returncode=1)
    )

    with pytest.raises(
        RuntimeError,
        match=r"TAXSIM exited with status 1 \(binary taxsimtest-fake.exe\); "
        r"stderr: 'STOP 1'; stdout tail: 'TAXSIM: Federal tax calculator "
        r"available 1960 - 2024 only.'",
    ):
        runner.run_cases(_cases("utah_elderly_idtl2_input.csv"))


@pytest.mark.parametrize("output_id", [{}, {"taxsimid": None}])
def test_legacy_runner_without_output_ids_uses_submitted_ids(output_id) -> None:
    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            del input_frame

        def run(self, show_progress=False):
            del show_progress
            return [{**output_id, "fiitax": 100}]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={"taxsim_input": {"taxsimid": 1, "year": 2024}},
    )

    [result] = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner).run_cases(
        [case], variables=["fiitax"]
    )

    assert result.household_id == "case-1"
    assert result.values == {"fiitax": 100}
    assert result.errors == ()
    assert result.raw == {**output_id, "fiitax": 100}


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    batch=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=1_000_000),
            st.integers(min_value=-100_000, max_value=100_000),
        ),
        min_size=1,
        max_size=8,
        unique_by=lambda row: row[0],
    ),
    id_column=st.sampled_from(["taxsimid", "legacy_id"]),
    id_type=st.sampled_from([int, float, str]),
)
def test_property_legacy_output_id_omission_preserves_attribution(
    batch, id_column, id_type
) -> None:
    """Dropping output IDs preserves case attribution, values, and errors."""
    cases = [
        Case(
            case_id=f"case-{index}",
            period="2024",
            metadata={"taxsim_input": {id_column: id_type(submitted), "year": 2024}},
        )
        for index, (submitted, _) in enumerate(batch)
    ]

    def run(include_ids):
        class FakeTaxsimRunner:
            def __init__(self, input_frame):
                del input_frame

            def run(self, show_progress=False):
                del show_progress
                return [
                    {
                        **({id_column: id_type(submitted)} if include_ids else {}),
                        "fiitax": amount,
                    }
                    for submitted, amount in batch
                ]

        return TaxsimPackageRunner(
            runner_factory=FakeTaxsimRunner, id_column=id_column
        ).run_cases(cases, variables=["fiitax"])

    with_ids = run(True)
    without_ids = run(False)

    assert [result.household_id for result in without_ids] == [
        case.case_id for case in cases
    ]
    assert [result.values for result in without_ids] == [
        {"fiitax": amount} for _, amount in batch
    ]
    assert all(result.errors == () for result in without_ids)
    assert [
        (result.household_id, result.values, result.errors) for result in without_ids
    ] == [(result.household_id, result.values, result.errors) for result in with_ids]


def test_legacy_runner_output_with_nan_id_is_rejected() -> None:
    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            del input_frame

        def run(self, show_progress=False):
            del show_progress
            return [
                {"taxsimid": 1.0, "fiitax": 1.0},
                {"taxsimid": float("nan"), "fiitax": float("nan")},
            ]

    runner = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner)

    with pytest.raises(RuntimeError, match="record 2 carries an unusable taxsimid=nan"):
        runner.run_cases(_cases("utah_elderly_idtl2_input.csv")[:1])


def test_legacy_runner_output_missing_a_case_yields_an_error_result() -> None:
    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            del input_frame

        def run(self, show_progress=False):
            del show_progress
            return [{"taxsimid": 1, "fiitax": 1.0}]

    runner = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner)

    results = runner.run_cases(
        _cases("utah_elderly_idtl2_input.csv")[:2], variables=["fiitax"]
    )

    assert [result.household_id for result in results] == ["case-1", "case-2"]
    assert results[0].values == {"fiitax": 1.0}
    assert results[1].values == {}
    assert results[1].errors == ("TAXSIM produced no output row for taxsimid=2",)


# --- the pinned binary ------------------------------------------------------


def _pinned_binary() -> Path:
    if platform.system() != "Darwin":
        pytest.skip(
            "fixtures were captured from the macOS build (cdate-20260521); the "
            "pinned Linux build rejects tax year 2026 outright"
        )
    binary = pins.installed_binary_path()
    if binary is None:
        pytest.skip("policyengine-taxsim (and its bundled binary) is not installed")
    return binary


@pytest.mark.parametrize("stem", ["utah_elderly_idtl2", "utah_elderly_idtl0"])
def test_pinned_macos_binary_reproduces_the_fixture(stem: str) -> None:
    binary = _pinned_binary()

    process = subprocess.run(
        [str(binary)],
        input=(FIXTURES / f"{stem}_input.csv").read_bytes(),
        capture_output=True,
        check=False,
    )

    assert process.returncode == 0
    assert process.stderr == b""
    assert process.stdout.decode() == _fixture(f"{stem}_stdout.txt")


def test_adapter_runs_the_pinned_binary_without_phantom_rows() -> None:
    _pinned_binary()
    runner = TaxsimPackageRunner()

    results = runner.run_cases(
        _cases("utah_elderly_idtl2_input.csv"), variables=["fiitax", "siitax"]
    )

    assert [result.household_id for result in results] == [
        "case-1",
        "case-2",
        "case-3",
        "case-4",
        "case-5",
    ]
    assert all(result.errors == () for result in results)
    assert results[1].values == {"fiitax": 585.0, "siitax": 49.88}
    assert results[1].raw[DIAGNOSTICS_KEY] == [D2_SINGLE_30K] * 6
    assert DIAGNOSTICS_KEY not in results[2].raw
