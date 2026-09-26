"""TaxsimPackageRunner on pinned binaries: partitioning, crash isolation, C1/C2.

Unit tests use fake runner factories and a fake pin document with temporary
fake binaries. The real-package tests at the bottom run policyengine-taxsim's
TaxsimRunner on the pinned executables; they skip when the package or the
bytes are absent (fail under ``AXIOM_TAXSIM_REQUIRE_BINARIES=1``).
"""

from __future__ import annotations

import hashlib
import os
import signal
import sys
from pathlib import Path

import pytest

from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner, pins
from axiom_oracles.adapters.taxsim import runner as runner_module
from axiom_oracles.adapters.taxsim.execution import (
    TaxsimExecutionError,
    crash_signature,
    execute_taxsim_binary,
)
from axiom_oracles.cli import _IdentifiedReportAccumulator, _engine_identity
from axiom_oracles.core.case import Case

REQUIRE_BINARIES = os.environ.get("AXIOM_TAXSIM_REQUIRE_BINARIES") == "1"
C1_BINARY_KEYS = {
    "sha256",
    "build",
    "build_observed",
    "platform",
    "bytes",
    "rows",
    "scope",
}


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    # The real-package tests below read the real cache/binary-dir settings;
    # the fake_pins fixture isolates those for the unit tests.
    monkeypatch.delenv(pins.PROFILE_ENV, raising=False)
    pins.clear_hash_cache()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


HOST = pins.normalize_platform() if sys.platform != "win32" else "windows"
NEW = b'#!/bin/sh\n# fake new\n# "cd2099010100"\n'
OLD = b'#!/bin/sh\n# fake old\n# "cd2098010100"\n'


def _doc() -> dict:
    real = pins.load_pins()
    shas = {"new": _sha(NEW), "old": _sha(OLD)}
    binaries = {
        shas[name]: {
            "platform": HOST,
            "build": build,
            "bytes": len(data),
            "filename": f"fake-{name}.exe",
            "sources": [
                {
                    "kind": "git",
                    "repo": "Example/fake",
                    "commit": "b" * 40,
                    "path": f"fake-{name}.exe",
                }
            ],
        }
        for name, data, build in (
            ("new", NEW, "cd2099010100"),
            ("old", OLD, "cd2098010100"),
        )
    }
    return {
        "schema_version": pins.SCHEMA_VERSION,
        "default_profile": "fake",
        "distribution": real["distribution"],
        "probes": {},
        "binaries": binaries,
        "profiles": {
            "fake": {
                "description": "new except GA/MD 2024-25",
                "binaries": {HOST: shas["new"]},
                "overrides": [
                    {
                        "id": "ga-md",
                        "states": [11, 21],
                        "state_postal": ["GA", "MD"],
                        "years": [2024, 2025],
                        "binaries": {HOST: shas["old"]},
                        "reason": "test",
                        "linked_issue": "https://example.test/1",
                        "source": "https://example.test/2",
                    }
                ],
            }
        },
    }


@pytest.fixture
def fake_pins(monkeypatch, tmp_path):
    monkeypatch.delenv(pins.BINARY_DIR_ENV, raising=False)
    monkeypatch.setenv(pins.CACHE_DIR_ENV, str(tmp_path / "cache"))
    doc = _doc()
    parsed = pins.parse_pin_document(doc)
    monkeypatch.setattr(pins, "load_pins", lambda: doc)
    monkeypatch.setattr(pins, "pin_document", lambda: parsed)
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: None)
    paths = {}
    for name, data in (("new", NEW), ("old", OLD)):
        sha = _sha(data)
        target = pins.cache_path(sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        paths[name] = target
    return {"sha": {"new": _sha(NEW), "old": _sha(OLD)}, "path": paths}


def _case(case_id: str, state: int, year: int, **extra) -> Case:
    row = {"taxsimid": case_id, "state": state, "year": year, "mstat": 1, **extra}
    return Case(case_id=case_id, period=str(year), metadata={"taxsim_input": row})


class RecordingFactory:
    """Fake runner factory: echoes rows as outputs, optionally failing.

    ``fail(rows)`` returns a TaxsimExecutionError to raise for a run, or None.
    Outputs are returned in REVERSE order to prove reassembly is id-based.
    """

    def __init__(self, fail=None):
        self.calls: list[dict] = []
        self.fail = fail

    def __call__(self, frame, taxsim_path=None):
        rows = frame.to_dict(orient="records")
        self.calls.append({"ids": [row["taxsimid"] for row in rows], "path": taxsim_path})
        factory = self

        class _Run:
            def run(self, show_progress=False):
                del show_progress
                error = factory.fail(rows) if factory.fail else None
                if error is not None:
                    raise error
                return [
                    {"taxsimid": row["taxsimid"], "siitax": float(row["state"])}
                    for row in reversed(rows)
                ]

        return _Run()


def _locator_runner(factory, **kwargs) -> TaxsimPackageRunner:
    return TaxsimPackageRunner(
        runner_factory=factory, binary_locator=pins.locate_binary, **kwargs
    )


# --------------------------------------------------------------------------
# Partitioning, reassembly, identity


def test_rows_partition_by_resolved_binary_and_reassemble_in_input_order(
    fake_pins,
) -> None:
    cases = [
        _case("a", 11, 2024),  # GA 2024 -> old
        _case("b", 47, 2021),  # VA -> new
        _case("c", 21, 2025),  # MD 2025 -> old
        _case("d", 11, 2023),  # GA 2023 -> new
        _case("e", 0, 2024),  # no state -> new
    ]
    factory = RecordingFactory()
    results = _locator_runner(factory).run_cases(cases, ["siitax"])

    assert [result.household_id for result in results] == ["a", "b", "c", "d", "e"]
    assert [call["ids"] for call in factory.calls] == [["a", "c"], ["b", "d", "e"]]
    assert [call["path"] for call in factory.calls] == [
        fake_pins["path"]["old"],
        fake_pins["path"]["new"],
    ]
    expected_sha = {
        "a": "old",
        "b": "new",
        "c": "old",
        "d": "new",
        "e": "new",
    }
    for result in results:
        assert result.raw["taxsim_binary_sha256"] == (
            fake_pins["sha"][expected_sha[result.household_id]]
        )
        assert "taxsim_rerun" not in result.raw
        assert result.errors == ()
    assert results[0].values == {"siitax": 11.0}


def test_taxsim_identity_reports_c1_shape_across_batches(fake_pins) -> None:
    runner = _locator_runner(RecordingFactory())
    runner.run_cases([_case("a", 11, 2024), _case("b", 47, 2021)], ["siitax"])
    runner.run_cases([_case("c", 5, 2026), _case("d", 21, 2024)], ["siitax"])
    identity = runner.taxsim_identity()
    assert identity["pin_profile"] == "fake"
    binaries = identity["binaries"]
    assert [b["scope"] for b in binaries] == ["default", "override:ga-md"]
    for item in binaries:
        assert set(item) == C1_BINARY_KEYS
        assert item["platform"] == HOST
    assert binaries[0]["sha256"] == fake_pins["sha"]["new"]
    assert binaries[0]["rows"] == 2
    assert binaries[0]["build"] == "cd2099010100"
    assert binaries[0]["build_observed"] == "cd2099010100"
    assert binaries[0]["bytes"] == len(NEW)
    assert binaries[1]["rows"] == 2
    assert binaries[1]["build_observed"] == "cd2098010100"


def test_explicit_profile_argument_wins_over_env(fake_pins, monkeypatch) -> None:
    monkeypatch.setenv(pins.PROFILE_ENV, "fake")
    runner = _locator_runner(RecordingFactory(), pin_profile="fake")
    assert runner.resolved_pin_profile() == "fake"
    with pytest.raises(pins.TaxsimPinError, match="unknown TAXSIM pin profile"):
        _locator_runner(RecordingFactory(), pin_profile="nope").run_cases(
            [_case("a", 1, 2024)], ["siitax"]
        )


def test_missing_or_tampered_binary_fails_before_any_run(fake_pins) -> None:
    fake_pins["path"]["old"].write_bytes(OLD + b"tamper")
    pins.clear_hash_cache()
    factory = RecordingFactory()
    with pytest.raises(pins.TaxsimPinError) as excinfo:
        _locator_runner(factory).run_cases(
            [_case("b", 47, 2021), _case("a", 11, 2024)], ["siitax"]
        )
    assert fake_pins["sha"]["old"] in str(excinfo.value)
    assert "(state=11, year=2024)" in str(excinfo.value)
    assert factory.calls == []  # nothing ran, not even the healthy partition


def test_default_factory_always_passes_a_verified_path(fake_pins, monkeypatch) -> None:
    constructed = []

    class FakePackageRunner:
        def __init__(self, frame, taxsim_path=None):
            constructed.append(taxsim_path)
            self.rows = frame.to_dict(orient="records")

        def run(self, show_progress=False):
            return [{"taxsimid": r["taxsimid"], "siitax": 1.0} for r in self.rows]

    monkeypatch.setattr(
        runner_module, "pinned_taxsim_runner_class", lambda: FakePackageRunner
    )
    results = TaxsimPackageRunner().run_cases([_case("a", 47, 2021)], ["siitax"])
    assert constructed == [fake_pins["path"]["new"]]
    assert results[0].raw["taxsim_binary_sha256"] == fake_pins["sha"]["new"]

    fake_pins["path"]["new"].unlink()
    constructed.clear()
    with pytest.raises(pins.TaxsimPinError):
        TaxsimPackageRunner().run_cases([_case("a", 47, 2021)], ["siitax"])
    assert constructed == []


def test_row_without_year_fails_closed(fake_pins) -> None:
    case = Case(case_id="x", period="2024", metadata={"taxsim_input": {"state": 5}})
    with pytest.raises(pins.TaxsimPinError, match="no year"):
        _locator_runner(RecordingFactory()).run_cases([case], ["siitax"])


# --------------------------------------------------------------------------
# Crash isolation (C2)


def _sigfpe() -> TaxsimExecutionError:
    return TaxsimExecutionError(
        returncode=-signal.SIGFPE,
        stderr="Program received signal SIGFPE: Floating-point exception",
        binary="/fake",
    )


def test_single_row_crash_is_isolated_and_others_keep_outputs(fake_pins) -> None:
    cases = [_case(str(i), 47, 2021) for i in range(8)]
    factory = RecordingFactory(
        fail=lambda rows: _sigfpe() if any(r["taxsimid"] == "5" for r in rows) else None
    )
    results = _locator_runner(factory).run_cases(cases, ["siitax"])

    assert [r.household_id for r in results] == [str(i) for i in range(8)]
    crashed = results[5]
    assert crashed.values == {}
    assert crashed.errors == ("taxsim-crash:SIGFPE",)
    assert crashed.raw == {
        "taxsim_error": {
            "signature": "SIGFPE",
            "returncode": -int(signal.SIGFPE),
            "stderr_tail": "Program received signal SIGFPE: Floating-point exception",
            "binary_sha256": fake_pins["sha"]["new"],
            "isolation": "single-row",
        }
    }
    for index, result in enumerate(results):
        if index == 5:
            continue
        assert result.errors == ()
        assert result.values == {"siitax": 47.0}
        assert result.raw["taxsim_rerun"] == "bisected"
        assert result.raw["taxsim_binary_sha256"] == fake_pins["sha"]["new"]
    # Deterministic bisection: full run, then halves left-first.
    assert [call["ids"] for call in factory.calls] == [
        ["0", "1", "2", "3", "4", "5", "6", "7"],
        ["0", "1", "2", "3"],
        ["4", "5", "6", "7"],
        ["4", "5"],
        ["4"],
        ["5"],
        ["6", "7"],
    ]


def test_order_dependent_crash_vanishes_deterministically(fake_pins) -> None:
    """pe-taxsim #1214 shape: DE immediately followed by MD crashes."""

    def fail(rows):
        states = [row["state"] for row in rows]
        for first, second in zip(states, states[1:], strict=False):
            if (first, second) == (8, 21):
                return _sigfpe()
        return None

    cases = [
        _case("de", 8, 2023),
        _case("md", 21, 2023),
        _case("va", 47, 2023),
    ]
    runs = []
    for _ in range(2):
        factory = RecordingFactory(fail=fail)
        results = _locator_runner(factory).run_cases(cases, ["siitax"])
        runs.append(([c["ids"] for c in factory.calls], results))
        assert all(result.errors == () for result in results)
        assert all(result.raw["taxsim_rerun"] == "bisected" for result in results)
    assert runs[0][0] == runs[1][0] == [["de", "md", "va"], ["de"], ["md", "va"]]


def test_rerun_budget_bounds_bisection(fake_pins) -> None:
    cases = [_case(str(i), 47, 2021) for i in range(16)]
    poison = {"3", "12"}
    factory = RecordingFactory(
        fail=lambda rows: _sigfpe() if poison & {r["taxsimid"] for r in rows} else None
    )
    results = _locator_runner(factory, max_crash_reruns=3).run_cases(cases, ["siitax"])
    assert len(factory.calls) == 1 + 3
    isolation = {
        r.household_id: r.raw["taxsim_error"]["isolation"]
        for r in results
        if r.errors
    }
    assert isolation["3"] == "budget-exhausted"
    assert isolation["12"] == "budget-exhausted"
    assert set(isolation.values()) == {"budget-exhausted"}
    succeeded = [r.household_id for r in results if not r.errors]
    assert succeeded == ["0", "1"]  # the one clean chunk reached within budget
    assert [r.household_id for r in results] == [str(i) for i in range(16)]


def test_non_execution_errors_propagate(fake_pins) -> None:
    def fail(rows):
        raise ValueError("parser broke")

    with pytest.raises(ValueError, match="parser broke"):
        _locator_runner(RecordingFactory(fail=fail)).run_cases(
            [_case("a", 47, 2021), _case("b", 47, 2021)], ["siitax"]
        )


def test_crash_signature_mapping() -> None:
    assert crash_signature(-8) == "SIGFPE"
    assert crash_signature(-11) == "SIGSEGV"
    assert crash_signature(136, via_shell=True) == "SIGFPE"
    assert crash_signature(136) == "rc=136"  # a direct exit status
    assert crash_signature(2) == "rc=2"
    assert crash_signature(-200) == "SIG200"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fixtures")
def test_execute_taxsim_binary_reports_signal_and_exit_status(tmp_path) -> None:
    input_file = tmp_path / "in.csv"
    input_file.write_text("taxsimid,year\n1,2024\n")
    output_file = tmp_path / "out.csv"

    echo = tmp_path / "echo.sh"
    echo.write_text("#!/bin/sh\ncat\n")
    echo.chmod(0o755)
    execute_taxsim_binary(echo, input_file, output_file)
    assert output_file.read_text() == "taxsimid,year\n1,2024\n"

    fpe = tmp_path / "fpe.sh"
    fpe.write_text('#!/bin/sh\necho "Program received signal SIGFPE" >&2\nkill -FPE $$\n')
    fpe.chmod(0o755)
    with pytest.raises(TaxsimExecutionError) as excinfo:
        execute_taxsim_binary(fpe, input_file, output_file)
    assert excinfo.value.signature == "SIGFPE"
    assert excinfo.value.returncode == -int(signal.SIGFPE)
    assert "SIGFPE" in excinfo.value.stderr_tail

    stop = tmp_path / "stop.sh"
    stop.write_text("#!/bin/sh\necho 'exiting 133' >&2\nexit 133\n")
    stop.chmod(0o755)
    with pytest.raises(TaxsimExecutionError) as excinfo:
        execute_taxsim_binary(stop, input_file, output_file)
    assert excinfo.value.signature == "rc=133"


# --------------------------------------------------------------------------
# The PolicyEngine emulator subclass is untouched


def test_policyengine_taxsim_runner_is_not_partitioned_or_hash_checked(
    monkeypatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("PE emulator runner must not touch TAXSIM pins")

    monkeypatch.setattr(pins, "locate_binary", forbidden)
    monkeypatch.setattr(pins, "get_profile", forbidden)
    monkeypatch.setattr(pins, "active_profile_name", forbidden)
    frames = []

    class FakePolicyEngineRunner:
        def __init__(self, frame):
            frames.append(frame.to_dict(orient="records"))

        def run(self, show_progress=False):
            return [
                {"taxsimid": row["taxsimid"], "fiitax": 1.0, "siitax": 2.0}
                for row in frames[-1]
            ]

    cases = [_case("a", 11, 2024), _case("b", 47, 2021), _case("c", 21, 2025)]
    runner = PolicyEngineTaxsimRunner(runner_factory=FakePolicyEngineRunner)
    results = runner.run_cases(cases, ["us:tax/state-income-tax#liability"])
    assert len(frames) == 1  # one run over every row, no partitioning
    assert [row["taxsimid"] for row in frames[0]] == ["a", "b", "c"]
    assert [r.household_id for r in results] == ["a", "b", "c"]
    for result in results:
        assert "taxsim_binary_sha256" not in result.raw
        assert result.values == {"state_income_tax": 2.0}
    assert runner.taxsim_identity() is None
    assert _engine_identity(runner) is None
    assert not runner._uses_pinned_taxsim_binary()


# --------------------------------------------------------------------------
# CLI report identity


def test_cli_report_carries_engine_identity(fake_pins) -> None:
    runner = _locator_runner(RecordingFactory())
    runner.run_cases([_case("a", 11, 2024), _case("b", 47, 2021)], ["siitax"])
    identity = _engine_identity(runner, PolicyEngineTaxsimRunner())
    assert identity == {"taxsim": runner.taxsim_identity()}
    accumulator = _IdentifiedReportAccumulator(
        suite_name="s", population="p", locales=set(), scope=None, mappings=[]
    )
    assert "engine_identity" not in accumulator.to_dict()
    accumulator.engine_identity = identity
    report = accumulator.to_dict()
    assert report["engine_identity"]["taxsim"]["pin_profile"] == "fake"
    for item in report["engine_identity"]["taxsim"]["binaries"]:
        assert set(item) == C1_BINARY_KEYS


# --------------------------------------------------------------------------
# Real policyengine-taxsim + pinned executables


def _real_package_or_skip():
    try:
        from policyengine_taxsim.runners.taxsim_runner import TaxsimRunner  # noqa: F401
    except ImportError:
        if REQUIRE_BINARIES:
            pytest.fail("policyengine-taxsim is not installed")
        pytest.skip("policyengine-taxsim is not installed (taxsim extra)")


def _real_located_or_skip(sha: str) -> Path:
    path = pins.find_verified_binary(sha)
    if path is None:
        message = (
            f"pinned TAXSIM binary {sha} is not present; run "
            f"`{pins.FETCH_COMMAND} --all-profiles`"
        )
        if REQUIRE_BINARIES:
            pytest.fail(message)
        pytest.skip(message)
    return path


VA_2021_OPT30 = {
    "taxsimid": 1,
    "year": 2021,
    "state": 47,
    "mstat": 2,
    "page": 45,
    "sage": 45,
    "depx": 0,
    "pwages": 60000,
    "idtl": 2,
    "opt1": 30,
    "opt1v": 1,
}
GA_2024 = {
    "taxsimid": 2,
    "year": 2024,
    "state": 11,
    "mstat": 1,
    "page": 40,
    "sage": 0,
    "depx": 0,
    "pwages": 50000,
    "idtl": 2,
}


def test_real_package_runner_still_executes_through_execute_taxsim() -> None:
    """Drift guard: the pinned runner overrides TaxsimRunner._execute_taxsim.

    If policyengine-taxsim stops calling that method from run(), the override
    (exit-status-preserving execution) would silently stop applying.
    """
    _real_package_or_skip()
    import inspect

    from policyengine_taxsim.runners.taxsim_runner import TaxsimRunner

    source = inspect.getsource(TaxsimRunner.run)
    assert "self._execute_taxsim(input_file, output_file)" in source
    parameters = list(inspect.signature(TaxsimRunner._execute_taxsim).parameters)
    assert parameters == ["self", "input_file", "output_file"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX TAXSIM builds only")
@pytest.mark.parametrize(
    "profile", ["dashboard-2026-09", "pe-taxsim-main-2026-08", "policyengine-taxsim-2.30.0"]
)
def test_real_package_runs_each_profile_on_verified_binaries(
    profile, monkeypatch
) -> None:
    _real_package_or_skip()
    from axiom_oracles.adapters.taxsim import execution

    executed = []
    real_execute = execution.execute_taxsim_binary

    def recording(binary, input_file, output_file):
        executed.append(Path(binary))
        return real_execute(binary, input_file, output_file)

    monkeypatch.setattr(execution, "execute_taxsim_binary", recording)
    host = pins.normalize_platform()
    resolved = {
        row["taxsimid"]: pins.resolve(row["state"], row["year"], host, profile)
        for row in (VA_2021_OPT30, GA_2024)
    }
    for resolution in resolved.values():
        _real_located_or_skip(resolution.sha256)
    cases = [
        Case(case_id=f"c{row['taxsimid']}", period=str(row["year"]),
             metadata={"taxsim_input": row})
        for row in (VA_2021_OPT30, GA_2024)
    ]
    runner = TaxsimPackageRunner(pin_profile=profile)
    results = runner.run_cases(cases, ["siitax", "srebate"])
    assert [r.household_id for r in results] == ["c1", "c2"]
    for result, row in zip(results, (VA_2021_OPT30, GA_2024), strict=True):
        assert result.errors == ()
        assert result.raw["taxsim_binary_sha256"] == resolved[row["taxsimid"]].sha256
    va_binary = pins.pinned_binary(resolved[1].sha256)
    for probe in va_binary.probe_results:
        if probe["evidence"]["kind"] == "documented":
            for column, expected in probe["expect"].items():
                assert results[0].values[column] == pytest.approx(expected, abs=0.005)
    assert {pins.cached_sha256(path) for path in executed} == {
        resolution.sha256 for resolution in resolved.values()
    }
    identity = runner.taxsim_identity()
    assert identity["pin_profile"] == profile
    assert sum(item["rows"] for item in identity["binaries"]) == 2
    for item in identity["binaries"]:
        assert item["build_observed"] == item["build"]
    expected_scopes = {resolution.scope for resolution in resolved.values()}
    assert {item["scope"] for item in identity["binaries"]} == expected_scopes


# The two records of policyengine-taxsim's #1214 minimal reproducer
# (tests/fixtures/maryland_taxsim_crash/pension-only-2024.csv at 3a58992a):
# a Delaware (SOI 8) record followed by a Maryland (SOI 21) joint filer with
# one spouse 65+ and a pension. The issue documents a SIGFPE in mdtax22 on
# the September Linux build for this order, and success alone or reversed.
MD_1214_ROWS = [
    {"taxsimid": 76239, "year": 2024, "state": 8, "mstat": 2, "page": 29,
     "sage": 41, "depx": 2, "age1": 4, "age2": 1, "idtl": 2},
    {"taxsimid": 76431, "year": 2024, "state": 21, "mstat": 2, "page": 68,
     "sage": 63, "depx": 0, "pensions": 6782.1240234374645, "idtl": 2},
]
SEPTEMBER_LINUX = "8aa880aeea33fd501f669d42125615e3b2a0ab19c17d93a76457e9de16615059"


@pytest.mark.skipif(sys.platform != "linux", reason="#1214 documents the crash on the Linux build")
def test_real_september_linux_build_on_the_1214_reproducer(monkeypatch) -> None:
    """Route the #1214 records to the September Linux build.

    Whether or not the order-dependent crash reproduces on this host, every
    row must come back with outputs (each succeeds alone per #1214); if the
    combined run crashed, the signature must be SIGFPE and the rows must be
    marked ``bisected``.
    """
    _real_package_or_skip()
    _real_located_or_skip(SEPTEMBER_LINUX)
    profile = pins.get_profile("dashboard-2026-09")
    forced = pins.Profile(
        name=profile.name,
        description=profile.description,
        binaries=profile.binaries,
        overrides=(),
    )
    monkeypatch.setattr(pins, "get_profile", lambda name: forced)
    cases = [
        Case(case_id=str(row["taxsimid"]), period="2024", metadata={"taxsim_input": row})
        for row in MD_1214_ROWS
    ]
    runner = TaxsimPackageRunner(pin_profile="dashboard-2026-09")
    results = runner.run_cases(cases, ["siitax"])
    assert [r.household_id for r in results] == ["76239", "76431"]
    assert all(r.errors == () for r in results)
    assert all(r.raw["taxsim_binary_sha256"] == SEPTEMBER_LINUX for r in results)
    if runner.crash_log:
        assert runner.crash_log[0]["signature"] == "SIGFPE"
        assert all(r.raw.get("taxsim_rerun") == "bisected" for r in results)
    print(f"#1214 reproducer crash log on this host: {runner.crash_log}")
