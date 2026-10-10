"""TAXSIM law-year fail-fast and executed-binary identity.

The pinned policyengine-taxsim 2.30.0 Linux binary (``taxsimtest-linux.exe``,
build ``cdate-compdate``) accepts law years 1960-2024; the macOS binary
(``taxsimtest-osx.exe``, ``cdate-20260521``) accepts 1960-2026. Both ranges,
and the line each binary printed for a rejected year, were captured by
running the binaries on 2026-10-10 and are recorded in ``taxsim_pins.json``.
``linux_2026_rejection_stdout.txt`` / ``_stderr.txt`` are the verbatim output
of the Linux binary (run through pe-taxsim's ``taxsim-docker-wrapper.sh``) on
the 5,000-row fiit-taxsim-ecps batch-13 input at law year 2026; that input is
not bundled. These tests check every caller refuses a year outside the
resolved binary's pinned range before running it, and that reports record
the binary that ran.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles import cli as cli_module
from axiom_oracles.adapters.taxsim import (
    TaxsimExecution,
    TaxsimIdentityError,
    TaxsimLawYearError,
    TaxsimPackageRunner,
    pins,
)
from axiom_oracles.comparison.report import ComparisonReportAccumulator
from axiom_oracles.core.case import Case

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "taxsim"
LINUX_KEY = "taxsimtest/taxsimtest-linux.exe"
DARWIN_KEY = "taxsimtest/taxsimtest-osx.exe"


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_identity_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def on_host(monkeypatch):
    """Pretend to be a host of the given platform with nothing installed."""

    def use(system: str) -> None:
        monkeypatch.setattr(
            pins, "_host_platform", lambda override=None: (override or system).lower()
        )
        monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: None)

    return use


# --- build stamps ------------------------------------------------------------


def test_build_stamps_are_read_from_bytes_header_banner_and_columns() -> None:
    assert pins.build_stamp_from_bytes(b'\x00junk"cdate-20260521"\x00') == (
        "cdate-20260521"
    )
    assert pins.build_stamp_from_bytes(b'"cd2026081819" and "cd2026081819"') == (
        "cd2026081819"
    )
    assert pins.build_stamp_from_bytes(b'"cdate-a" "cdate-b"') is None
    assert pins.build_stamp_from_bytes(b"no stamp") is None

    utah = (FIXTURES / "utah_elderly_idtl2_stdout.txt").read_text()
    assert pins.build_stamp_from_stdout(utah) == "cdate-20260521"
    verbose = (FIXTURES / "california_idtl5_stdout.txt").read_text()
    assert pins.build_stamp_from_stdout(verbose) == "20260521"
    assert pins.same_build("cdate-20260521", "20260521")
    assert pins.same_build('"cd2026081819"', "2026081819")
    assert not pins.same_build("cdate-20260521", "cd2026081819")
    assert not pins.same_build("cdate-20260521", None)

    assert pins.build_stamp_from_columns(["taxsimid", "actc", "cdate-20260521"]) == (
        "cdate-20260521"
    )
    assert pins.build_stamp_from_columns(['"cd2026081819"', "fiitax"]) == (
        "cd2026081819"
    )
    assert pins.build_stamp_from_columns(["taxsimid", "fiitax"]) is None


@settings(max_examples=200, deadline=None)
@given(
    prefix=st.binary(max_size=200).filter(lambda b: b'"' not in b),
    suffix=st.binary(max_size=200).filter(lambda b: b'"' not in b),
    digits=st.integers(min_value=0, max_value=9_999_999_999),
    copies=st.integers(min_value=1, max_value=3),
)
def test_an_embedded_stamp_is_recovered_exactly(prefix, suffix, digits, copies):
    stamp = f"cd{digits:010d}"
    data = prefix + (f'"{stamp}"'.encode() + b"\x00") * copies + suffix
    assert pins.build_stamp_from_bytes(data) == stamp
    assert pins.same_build(stamp, f"{digits:010d}")


def test_the_linux_rejection_capture_names_its_build() -> None:
    stdout = (FIXTURES / "linux_2026_rejection_stdout.txt").read_text()
    entry = pins.bundled_binaries()[LINUX_KEY]
    assert stdout.splitlines()[0] == entry["law_years"]["rejection"]
    assert stdout.splitlines()[-1] == (
        " TAXSIM: Taxsimtest version of    : compdate"
    )
    assert pins.same_build(entry["build"], "compdate")
    assert (FIXTURES / "linux_2026_rejection_stderr.txt").read_text() == "STOP 1\n"


# --- require_law_years -------------------------------------------------------


def test_linux_refuses_2025_and_2026_and_names_the_macos_binary(on_host) -> None:
    on_host("linux")
    with pytest.raises(TaxsimLawYearError) as caught:
        pins.require_law_years([2026])
    message = str(caught.value)
    assert message.startswith("TAXSIM cannot run law year 2026 on linux")
    assert "taxsimtest/taxsimtest-linux.exe as pinned" in message
    assert "build cdate-compdate) accepts law years 1960-2024 only" in message
    assert "'TAXSIM: Federal tax calculator available 1960 - 2024 only.'" in message
    assert "The pinned binary for darwin (taxsimtest/taxsimtest-osx.exe" in message
    assert "or use a law year in 1960-2024" in message

    with pytest.raises(TaxsimLawYearError, match=r"law years 2025, 2026 on linux"):
        pins.require_law_years([2024, 2025, 2026])
    assert pins.require_law_years([1960, 2024]) is None


def test_macos_accepts_2026_and_nothing_accepts_2027(on_host) -> None:
    on_host("darwin")
    assert pins.require_law_years([2026, 2025]) is None
    with pytest.raises(TaxsimLawYearError, match="No pinned binary accepts 2027"):
        pins.require_law_years([2027])


def test_an_unrun_windows_binary_is_not_checked(on_host) -> None:
    on_host("windows")
    assert pins.bundled_binaries()["taxsimtest/taxsimtest-windows.exe"][
        "law_years"
    ] is None
    assert pins.require_law_years([2026]) is None


def test_no_years_and_unknown_platforms_are_not_checked(on_host) -> None:
    on_host("linux")
    assert pins.require_law_years([]) is None
    on_host("plan9")
    assert pins.require_law_years([2026]) is None


@settings(max_examples=300, deadline=None)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    system=st.sampled_from(["linux", "darwin", "windows"]),
)
def test_refusal_holds_exactly_outside_the_pinned_range(year, system) -> None:
    """Invariant: a year is refused iff the platform binary's range excludes it."""
    key = pins.load_pins()["runtime_binary"]["by_platform"][system]
    years = pins.law_year_range(pins.bundled_binaries()[key])
    expect_refusal = years is not None and not years[0] <= year <= years[1]
    original = (pins._host_platform, pins.installed_binary_path)
    pins._host_platform = lambda override=None: (override or system).lower()
    pins.installed_binary_path = lambda system=None: None
    try:
        try:
            pins.require_law_years([year])
            refused = False
        except TaxsimLawYearError:
            refused = True
    finally:
        pins._host_platform, pins.installed_binary_path = original
    assert refused == expect_refusal


def test_an_explicit_binary_is_identified_by_hash(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "taxsim"
    binary.write_bytes(b'#!/bin/sh\n# "cdate-compdate"\n')
    # Not pinned: returned, not checked.
    identity = pins.require_law_years([2026], binary_path=binary)
    assert identity is not None
    assert identity["pinned"] is False
    assert identity["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert identity["build"] == "cdate-compdate"

    # Treat its hash as the pinned Linux binary: now 2026 is refused.
    linux = pins.bundled_binaries()[LINUX_KEY]
    monkeypatch.setattr(
        pins, "pinned_entry_for_sha", lambda sha: (LINUX_KEY, dict(linux))
    )
    with pytest.raises(TaxsimLawYearError, match=f"{LINUX_KEY} at {binary}"):
        pins.require_law_years([2026], binary_path=binary, system="linux")


def test_use_installed_false_checks_the_pin_not_the_local_venv(
    tmp_path, monkeypatch
) -> None:
    stray = tmp_path / "taxsimtest-linux.exe"
    stray.write_bytes(b"some other build")
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: stray)
    # The stray binary is unpinned, so looking at it would skip the check.
    assert pins.require_law_years([2026], system="linux")["pinned"] is False
    with pytest.raises(TaxsimLawYearError):
        pins.require_law_years([2026], system="linux", use_installed=False)


# --- TaxsimIdentityRecorder --------------------------------------------------


def test_recorder_counts_rows_and_keeps_the_printed_build(tmp_path) -> None:
    binary = tmp_path / "taxsim"
    binary.write_bytes(b'"cdate-20260521"')
    recorder = pins.TaxsimIdentityRecorder()
    assert recorder.to_dict() is None
    recorder.observe(binary, rows=3, build_observed="cdate-20260521")
    recorder.observe(binary, rows=4, build_observed="cdate-20260521")
    block = recorder.to_dict()
    assert block["pinned_policyengine_taxsim"] == pins.pinned_version()
    [entry] = block["binaries"]
    assert entry["rows"] == 7
    assert entry["path"] == str(binary)
    assert entry["build"] == "cdate-20260521"
    assert entry["build_observed"] == "cdate-20260521"
    assert entry["platform"] == pins._host_platform()
    assert entry["pinned"] is False
    assert entry["pinned_key"] is None
    assert entry["law_years"] is None


def test_recorder_refuses_a_printed_build_the_hashed_bytes_do_not_embed(
    tmp_path,
) -> None:
    binary = tmp_path / "taxsim"
    binary.write_bytes(b'"cdate-20260521"')
    recorder = pins.TaxsimIdentityRecorder()
    with pytest.raises(TaxsimIdentityError, match="embeds build 'cdate-20260521'"):
        recorder.observe(binary, rows=1, build_observed="cd2026081819")
    # The idtl=5 banner form of the same build is accepted.
    recorder.observe(binary, rows=1, build_observed="20260521")


def test_recorder_refuses_a_binary_that_changed_between_batches(tmp_path) -> None:
    binary = tmp_path / "taxsim"
    binary.write_bytes(b"first build")
    recorder = pins.TaxsimIdentityRecorder()
    first = recorder.observe(binary, rows=1)
    recorder.observe(binary, rows=1, sha256=first["sha256"])
    binary.write_bytes(b"second build")
    with pytest.raises(TaxsimIdentityError, match="changed during the run"):
        recorder.observe(
            binary, rows=1, sha256=hashlib.sha256(b"second build").hexdigest()
        )


def test_recorder_refuses_two_printed_builds_from_one_unstamped_file(
    tmp_path,
) -> None:
    binary = tmp_path / "taxsim"
    binary.write_bytes(b"no stamp")
    recorder = pins.TaxsimIdentityRecorder()
    recorder.observe(binary, rows=1, build_observed="cdate-compdate")
    with pytest.raises(TaxsimIdentityError, match="printed build"):
        recorder.observe(binary, rows=1, build_observed="cdate-20260521")


@settings(max_examples=100, deadline=None)
@given(batches=st.lists(st.integers(min_value=0, max_value=5_000), max_size=20))
def test_recorded_rows_equal_the_rows_run(tmp_path_factory, batches) -> None:
    """Invariant: per-binary row counts sum to the rows submitted."""
    binary = tmp_path_factory.mktemp("bin") / "taxsim"
    binary.write_bytes(b"x")
    recorder = pins.TaxsimIdentityRecorder()
    for rows in batches:
        recorder.observe(binary, rows=rows)
    block = recorder.to_dict()
    if not batches:
        assert block is None
    else:
        assert [entry["rows"] for entry in block["binaries"]] == [sum(batches)]


# --- TaxsimPackageRunner -----------------------------------------------------


_HEADER = 'taxsimid,year,state,fiitax,siitax,fica,frate,srate,ficar,tfica,"{stamp}"'


def _fake_binary(tmp_path: Path, *, stamp: str, embed: str = "") -> tuple[Path, Path]:
    """A shell script standing in for taxsimtest; it drops a marker when run."""
    marker = tmp_path / "ran"
    stdout = tmp_path / "stdout.txt"
    stdout.write_text(
        _HEADER.format(stamp=stamp)
        + "\n1.,2024,0,4016.12,0.00,7650.00,12.00,0.00,0.00,3825.00,0\n"
    )
    script = tmp_path / "taxsim.sh"
    script.write_text(
        "#!/bin/sh\n"
        f"# {embed}\n"
        "cat > /dev/null\n"
        f'touch "{marker}"\n'
        f'cat "{stdout}"\n'
    )
    script.chmod(0o755)
    return script, marker


class _FakeTaxsimRunner:
    def __init__(self, frame, binary: Path, tmp_path: Path):
        self.input_df = frame
        self.taxsim_path = binary
        self._tmp_path = tmp_path

    def _create_taxsim_input_file(self, frame) -> str:
        path = self._tmp_path / "input.csv"
        frame.to_csv(path, index=False)
        return str(path)


def _runner_with(binary: Path, tmp_path: Path) -> TaxsimPackageRunner:
    runner = TaxsimPackageRunner()
    runner._runner_factory = lambda: (
        lambda frame: _FakeTaxsimRunner(frame, binary, tmp_path)
    )
    return runner


def _case(year: int) -> Case:
    return Case(
        case_id="case-1",
        period=str(year),
        metadata={
            "taxsim_input": {
                "taxsimid": 1,
                "year": year,
                "state": 0,
                "mstat": 1,
                "page": 40,
                "pwages": 50000,
                "idtl": 0,
            }
        },
    )


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script")
def test_runner_refuses_2026_on_the_linux_binary_before_running_it(
    tmp_path, monkeypatch
) -> None:
    binary, marker = _fake_binary(tmp_path, stamp="cdate-compdate")
    linux = pins.bundled_binaries()[LINUX_KEY]
    monkeypatch.setattr(
        pins, "pinned_entry_for_sha", lambda sha: (LINUX_KEY, dict(linux))
    )
    runner = _runner_with(binary, tmp_path)

    with pytest.raises(TaxsimLawYearError, match="law year 2026 on"):
        runner.run_cases([_case(2026)])
    assert not marker.exists()
    assert runner.taxsim_identity() is None

    [result] = runner.run_cases([_case(2024)])
    assert marker.exists()
    assert result.errors == ()
    assert result.values["fiitax"] == 4016.12
    [entry] = runner.taxsim_identity()["binaries"]
    assert entry["path"] == str(binary)
    assert entry["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert entry["pinned"] is True and entry["pinned_key"] == LINUX_KEY
    assert entry["law_years"] == {"first": 1960, "last": 2024}
    assert entry["build_observed"] == "cdate-compdate"
    assert entry["rows"] == 1


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script")
def test_runner_refuses_output_from_a_build_other_than_the_hashed_file(
    tmp_path,
) -> None:
    binary, _ = _fake_binary(
        tmp_path, stamp="cd2026081819", embed='"cdate-20260521"'
    )
    runner = _runner_with(binary, tmp_path)
    with pytest.raises(TaxsimIdentityError):
        runner.run_cases([_case(2026)])


def test_the_linux_rejection_output_still_fails_loudly_if_it_is_reached() -> None:
    """An unpinned or unchecked binary's own refusal surfaces verbatim."""
    runner = TaxsimPackageRunner(
        executor=lambda frame: TaxsimExecution(
            stdout=(FIXTURES / "linux_2026_rejection_stdout.txt").read_text(),
            stderr=(FIXTURES / "linux_2026_rejection_stderr.txt").read_text(),
            returncode=1,
            binary="taxsimtest-linux.exe",
        )
    )
    with pytest.raises(RuntimeError) as caught:
        runner.run_cases([_case(2026)])
    message = str(caught.value)
    assert "TAXSIM exited with status 1 (binary taxsimtest-linux.exe)" in message
    assert "STOP 1" in message
    assert "Taxsimtest version of    : compdate" in message


# --- CLI ---------------------------------------------------------------------


def _forbid_population_load(monkeypatch) -> None:
    def refuse(**kwargs):
        raise AssertionError("population loaded")

    monkeypatch.setattr(cli_module, "_load_population_cases", refuse)


@pytest.mark.parametrize("period_args", [["--period", "2026"], []])
def test_compare_stops_on_linux_before_loading_the_population(
    on_host, monkeypatch, period_args
) -> None:
    on_host("linux")
    _forbid_population_load(monkeypatch)
    result = CliRunner().invoke(
        cli_module.cli, ["compare", "axiom", "taxsim", *period_args]
    )
    assert result.exit_code != 0
    assert "TAXSIM cannot run law year 2026 on linux" in result.output
    assert "population loaded" not in str(result.exception)


@pytest.mark.parametrize(("system", "period"), [("linux", "2024"), ("darwin", "2026")])
def test_compare_proceeds_when_the_binary_accepts_the_year(
    on_host, monkeypatch, system, period
) -> None:
    on_host(system)
    _forbid_population_load(monkeypatch)
    result = CliRunner().invoke(
        cli_module.cli, ["compare", "policyengine", "taxsim", "--period", period]
    )
    assert isinstance(result.exception, AssertionError)
    assert str(result.exception) == "population loaded"


def test_compare_rejects_a_period_without_a_year(on_host, monkeypatch) -> None:
    on_host("linux")
    _forbid_population_load(monkeypatch)
    result = CliRunner().invoke(
        cli_module.cli, ["compare", "axiom", "taxsim", "--period", "latest"]
    )
    assert result.exit_code != 0
    assert "does not start with a law year" in result.output


def test_engine_identity_collects_the_taxsim_runner_binaries(tmp_path) -> None:
    binary = tmp_path / "taxsim"
    binary.write_bytes(b'"cdate-20260521"')
    taxsim = TaxsimPackageRunner()
    assert cli_module._engine_identity(object(), taxsim) is None
    taxsim.identity.observe(binary, rows=5, build_observed="cdate-20260521")
    identity = cli_module._engine_identity(object(), taxsim)
    assert identity == {"taxsim": taxsim.taxsim_identity()}
    assert identity["taxsim"]["binaries"][0]["rows"] == 5


def test_report_writes_engine_identity_only_when_set(tmp_path) -> None:
    def accumulator() -> ComparisonReportAccumulator:
        return ComparisonReportAccumulator(
            suite_name="identity-suite",
            population="synthetic",
            locales=set(),
            scope=None,
            mappings=[],
        )

    plain = accumulator()
    assert "engine_identity" not in plain.to_dict()
    with_identity = accumulator()
    block = {"taxsim": {"pinned_policyengine_taxsim": "2.30.0", "binaries": []}}
    with_identity.engine_identity = block
    assert with_identity.to_dict()["engine_identity"] == block
    path = tmp_path / "report.json"
    with_identity.write_json(path)
    assert json.loads(path.read_text())["engine_identity"] == block


# --- scripts -----------------------------------------------------------------


_BINARY_ENTRY = {
    "path": "/venv/share/policyengine_taxsim/taxsimtest/taxsimtest-osx.exe",
    "sha256": "0d9e43a983055d44eec9e5de7edfc933fa061b2a336716d760fe98abf4336319",
    "bytes": 1961912,
    "build": "cdate-20260521",
    "build_observed": "cdate-20260521",
    "platform": "darwin",
    "machine": "arm64",
    "pinned": True,
    "pinned_key": DARWIN_KEY,
    "law_years": {"first": 1960, "last": 2026},
    "policyengine_taxsim": "2.30.0",
    "rows": 5000,
}


def test_run_comparison_lifts_the_binaries_into_provenance_oracle(
    tmp_path, monkeypatch
) -> None:
    run_comparison = _load_script("run_comparison")
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    output = tmp_path / "report.json"
    output.write_text(
        json.dumps(
            {
                "suite": "fiit-taxsim-ecps",
                "engine_identity": {
                    "taxsim": {
                        "pinned_policyengine_taxsim": "2.30.0",
                        "binaries": [_BINARY_ENTRY],
                    }
                },
            }
        )
    )
    config = {
        "name": "fiit-taxsim-ecps",
        "runner": {
            "type": "axiom-oracles-compare",
            "axiom_rules_repo": str(tmp_path / "missing-rules"),
            "parameters": {
                "left": "axiom",
                "right": "taxsim",
                "population": "enhanced-cps",
                "period": "2026",
            },
        },
    }
    block = run_comparison._build_run_provenance(
        config, "axiom-oracles-compare", output
    )
    assert block["oracle"]["name"] == "taxsim"
    assert block["oracle"]["policyengine_taxsim"] == pins.pinned_version()
    assert block["oracle"]["taxsim_binaries"] == [_BINARY_ENTRY]

    # A report written before engine_identity existed keeps the version only.
    output.write_text(json.dumps({"suite": "fiit-taxsim-ecps"}))
    assert run_comparison._taxsim_oracle_identity(output) == {
        "policyengine_taxsim": pins.pinned_version()
    }


def test_run_comparison_stops_before_building_on_linux(on_host, monkeypatch) -> None:
    run_comparison = _load_script("run_comparison")
    on_host("linux")

    def refuse(*args, **kwargs):
        raise AssertionError("environment built")

    monkeypatch.setattr(run_comparison, "_ensure_engine_binary", refuse)
    monkeypatch.setattr(
        run_comparison, "_resolve_state_income_tax_grid_repos", refuse
    )
    monkeypatch.setattr(run_comparison, "_resolve_path", lambda value, key: Path(value))

    with pytest.raises(SystemExit, match="fiit-taxsim-ecps: TAXSIM cannot run"):
        run_comparison._run_axiom_oracles_compare(
            {
                "axiom_rules_repo": "/nonexistent",
                "parameters": {
                    "left": "axiom",
                    "right": "taxsim",
                    "period": "2026",
                    "suite": "fiit-taxsim-ecps",
                },
            },
            Path("/nonexistent/report.json"),
        )
    with pytest.raises(SystemExit, match="AZ: TAXSIM cannot run law year 2026"):
        run_comparison._run_state_income_tax_liability_grid(
            {"parameters": {"state": "AZ", "period": "2026", "taxsim_law_year": 2026}},
            Path("/nonexistent/report.json"),
        )


def test_run_comparison_checks_the_pin_not_its_own_venv(
    tmp_path, monkeypatch
) -> None:
    run_comparison = _load_script("run_comparison")
    stray = tmp_path / "taxsimtest-linux.exe"
    stray.write_bytes(b"a different build")
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: stray)
    monkeypatch.setattr(
        pins, "_host_platform", lambda override=None: (override or "linux").lower()
    )
    with pytest.raises(SystemExit, match="TAXSIM cannot run law year 2026"):
        run_comparison._require_taxsim_law_year("2026", "suite")


def _shard(binaries: list[dict] | None) -> dict:
    shard = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "sharded-suite",
        "population": "synthetic",
        "engines": {"left": "axiom", "right": "taxsim"},
        "locales": ["US"],
        "case_count": 0,
        "summary": {"error_count": 0, "errors_by_engine": {}},
    }
    if binaries is not None:
        shard["engine_identity"] = {
            "taxsim": {"pinned_policyengine_taxsim": "2.30.0", "binaries": binaries}
        }
    return shard


def test_shard_merge_sums_rows_per_binary_and_keeps_distinct_binaries() -> None:
    merge = _load_script("merge_shard_reports").merge
    other = {**_BINARY_ENTRY, "sha256": "f" * 64, "rows": 2}
    merged = merge(
        [
            _shard([{**_BINARY_ENTRY, "rows": 3}]),
            _shard([{**_BINARY_ENTRY, "rows": 4}, other]),
        ]
    )
    binaries = merged["engine_identity"]["taxsim"]["binaries"]
    assert [entry["rows"] for entry in binaries] == [7, 2]
    assert merged["engine_identity"]["taxsim"]["pinned_policyengine_taxsim"] == "2.30.0"
    assert "engine_identity" not in merge([_shard(None), _shard(None)])
    with pytest.raises(SystemExit, match="engine_identity"):
        merge([_shard([_BINARY_ENTRY]), _shard(None)])


@settings(max_examples=100, deadline=None)
@given(
    partition=st.lists(
        st.lists(
            st.tuples(st.sampled_from(["a", "b", "c"]), st.integers(0, 10_000)),
            max_size=3,
        ),
        min_size=1,
        max_size=6,
    )
)
def test_shard_merge_conserves_rows_per_binary(partition) -> None:
    """Invariant: merged rows per binary equal the sum over shards."""
    merge = _load_script("merge_shard_reports").merge
    shards = [
        _shard([{**_BINARY_ENTRY, "sha256": sha * 64, "rows": rows} for sha, rows in part])
        for part in partition
    ]
    merged = merge(shards)
    expected: dict[str, int] = {}
    for part in partition:
        for sha, rows in part:
            expected[sha * 64] = expected.get(sha * 64, 0) + rows
    got = {
        entry["sha256"]: entry["rows"]
        for entry in (merged.get("engine_identity") or {"taxsim": {"binaries": []}})[
            "taxsim"
        ]["binaries"]
    }
    assert got == expected


def test_grid_generator_stops_on_linux_and_records_binaries(
    on_host, monkeypatch
) -> None:
    generator = _load_script("generate_state_income_tax_liability")
    on_host("linux")
    monkeypatch.setattr(generator, "_taxsim_binary", lambda: None)

    def refuse(*args, **kwargs):
        raise AssertionError("grid built")

    monkeypatch.setattr(generator, "_grid", refuse)
    with pytest.raises(SystemExit, match="TAXSIM cannot run law year 2026 on linux"):
        generator.main(["--state", "AZ"])

    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "az-income-tax-liability",
        "summary": {"comparison_count": 0, "match_count": 0, "mismatch_count": 0},
        "mismatches": [],
        "cases": [],
        "engine_identity": {
            "taxsim": {"pinned_policyengine_taxsim": "2.30.0", "binaries": [_BINARY_ENTRY]}
        },
    }
    finalized = generator._finalize_report(
        report, generated_at="2026-10-10T00:00:00Z", rulespecs=[]
    )
    assert finalized["engine_identity"] == report["engine_identity"]
    assert finalized["provenance"]["oracle"] == {
        "name": "policyengine-taxsim",
        "policyengine_taxsim": pins.pinned_version(),
        "taxsim_binaries": [_BINARY_ENTRY],
    }


def test_populace_campaign_stops_on_linux_before_loading_data(
    on_host, monkeypatch, tmp_path
) -> None:
    campaign = _load_script("run_state_tax_populace")
    on_host("linux")

    def refuse(*args, **kwargs):
        raise AssertionError("dataset loaded")

    monkeypatch.setattr(campaign, "load_populace_dataset", refuse)
    args = [
        "--rulespec-root",
        str(tmp_path),
        "--axiom-rules-path",
        str(tmp_path),
        "--output",
        str(tmp_path / "out.json"),
    ]
    with pytest.raises(SystemExit, match="TAXSIM cannot run law year 2026 on linux"):
        campaign.main(args)
    with pytest.raises(AssertionError, match="dataset loaded"):
        campaign.main([*args, "--no-taxsim"])
