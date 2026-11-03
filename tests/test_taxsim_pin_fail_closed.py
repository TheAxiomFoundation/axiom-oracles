"""The default TAXSIM runner fails closed on its pin, and resolves rows exactly.

Each test sets up a pin document whose binaries are POSIX shell scripts
standing in for taxsimtest. An unpinned executable is also left where
policyengine-taxsim's own search, or the installed share tree, would find
it, so a test can tell a refusal from a silent fallback: every stand-in
drops a marker file when it runs.
"""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.taxsim import TaxsimPackageRunner, pins
from axiom_oracles.adapters.taxsim import runner as runner_module
from axiom_oracles.core.case import Case

pytestmark = pytest.mark.skipif(os.name == "nt", reason="uses POSIX shell scripts")

GEORGIA, MARYLAND, CALIFORNIA = 11, 21, 5


def _script(directory: Path, name: str, fiitax: int, marker: Path) -> Path:
    """A stand-in that echoes each input taxsimid with a fixed fiitax."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "#!/bin/sh\n"
        f'# "cd20990101{fiitax:02d}"\n'
        f'touch "{marker}"\n'
        "awk -F, 'NR==1 {for (i = 1; i <= NF; i++) if ($i == \"taxsimid\") c = i;"
        f' print "taxsimid,fiitax,\\"cd20990101{fiitax:02d}\\""; next}}'
        f" {{print $c \",{fiitax},0\"}}'\n"
    )
    path.chmod(0o755)
    return path


def _entry(path: Path, system: str) -> dict:
    data = path.read_bytes()
    return {
        "platform": system,
        "build": pins.build_stamp_from_bytes(data),
        "bytes": len(data),
        "filename": path.name,
        "sources": [
            {
                "kind": "url",
                "url": "https://example.invalid/stand-in",
                "retrieved_on": "2026-11-02",
            }
        ],
    }


@pytest.fixture
def stand_ins(tmp_path, monkeypatch):
    """Two pinned stand-ins under profile ``split`` and an unpinned decoy.

    ``split`` runs ``main.exe`` (fiitax 11) everywhere except Georgia and
    Maryland in 2024-2025, which run ``old.exe`` (fiitax 22). ``decoy.exe``
    (fiitax 99) is unpinned and is what the installed-package lookup and
    policyengine-taxsim's own search would return.
    """
    system = pins.normalize_platform()
    binaries = tmp_path / "binaries"
    markers = {name: tmp_path / f"ran-{name}" for name in ("main", "old", "decoy")}
    main = _script(binaries, "main.exe", 11, markers["main"])
    old = _script(binaries, "old.exe", 22, markers["old"])
    decoy = _script(tmp_path / "installed", "decoy.exe", 99, markers["decoy"])
    doc = copy.deepcopy(pins.load_pins())
    shas = {}
    for name, path in (("main", main), ("old", old)):
        shas[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        doc["binaries"][shas[name]] = _entry(path, system)
    doc["profiles"]["split"] = {
        "description": "test profile",
        "binaries": {system: shas["main"]},
        "overrides": [
            {
                "id": "ga-md",
                "states": [GEORGIA, MARYLAND],
                "state_postal": ["GA", "MD"],
                "years": [2024, 2025],
                "binaries": {system: shas["old"]},
                "reason": "test",
                "linked_issue": "https://example.invalid/1",
                "source": "https://example.invalid/2",
            }
        ],
    }
    doc["default_profile"] = "split"
    parsed = pins.parse_pin_document(doc)
    monkeypatch.setattr(pins, "load_pins", lambda: doc)
    monkeypatch.setattr(pins, "pin_document", lambda: parsed)
    monkeypatch.setenv(pins.BINARY_DIR_ENV, str(binaries))
    monkeypatch.setenv(pins.CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.delenv(pins.PROFILE_ENV, raising=False)
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: decoy)
    monkeypatch.setattr(pins, "resolve_binary_path", lambda system=None: decoy)
    pins.clear_hash_cache()

    class UpstreamRunner:
        """policyengine-taxsim's TaxsimRunner surface the adapter uses."""

        def __init__(self, frame, taxsim_path=None):
            self.input_df = frame
            # Its own search would find the decoy when no path is given.
            self.taxsim_path = taxsim_path or decoy

        def _create_taxsim_input_file(self, frame):
            path = tmp_path / "input.csv"
            frame.to_csv(path, index=False)
            return str(path)

    original = runner_module.import_module
    monkeypatch.setattr(
        runner_module,
        "import_module",
        lambda name: (
            SimpleNamespace(TaxsimRunner=UpstreamRunner)
            if name in {"policyengine_taxsim", "policyengine_taxsim.runners"}
            else original(name)
        ),
    )
    def set_law_years(name: str, first: int, last: int) -> None:
        """Record a pinned law-year range on one stand-in and reinstall."""
        doc["binaries"][shas[name]]["law_years"] = {"first": first, "last": last}
        reparsed = pins.parse_pin_document(doc)
        monkeypatch.setattr(pins, "pin_document", lambda: reparsed)

    return SimpleNamespace(
        main=main,
        old=old,
        decoy=decoy,
        markers=markers,
        shas=shas,
        system=system,
        set_law_years=set_law_years,
    )


def _case(taxsimid: int, state: int, year: int) -> Case:
    return Case(
        case_id=f"case-{taxsimid}",
        period=str(year),
        metadata={
            "taxsim_input": {"taxsimid": taxsimid, "state": state, "year": year}
        },
    )


def _assert_nothing_ran(stand_ins) -> None:
    assert not any(marker.exists() for marker in stand_ins.markers.values())


# --- fail closed -------------------------------------------------------------


def test_the_pinned_profile_runs_and_the_decoy_never_does(stand_ins) -> None:
    runner = TaxsimPackageRunner()
    [result] = runner.run_cases([_case(1, CALIFORNIA, 2024)], variables=["fiitax"])
    assert result.values == {"fiitax": 11.0}
    assert stand_ins.markers["main"].exists()
    assert not stand_ins.markers["decoy"].exists()


def test_unknown_profile_refuses_without_running_anything(stand_ins, monkeypatch):
    with pytest.raises(pins.TaxsimPinError, match="unknown TAXSIM pin profile"):
        TaxsimPackageRunner(pin_profile="nope").run_cases([_case(1, 0, 2024)])
    monkeypatch.setenv(pins.PROFILE_ENV, "nope")
    with pytest.raises(pins.TaxsimPinError, match="unknown TAXSIM pin profile"):
        TaxsimPackageRunner().run_cases([_case(1, 0, 2024)])
    _assert_nothing_ran(stand_ins)


def test_missing_binary_refuses_without_falling_back(stand_ins) -> None:
    stand_ins.main.unlink()
    with pytest.raises(pins.TaxsimPinError, match="not available as verified") as caught:
        TaxsimPackageRunner().run_cases([_case(1, CALIFORNIA, 2024)])
    message = str(caught.value)
    assert stand_ins.shas["main"] in message
    assert "split" in message and pins.FETCH_COMMAND in message
    _assert_nothing_ran(stand_ins)


def test_hash_mismatch_refuses_without_falling_back(stand_ins) -> None:
    stand_ins.main.write_text(stand_ins.main.read_text() + "# tampered\n")
    with pytest.raises(pins.TaxsimPinError, match="does not match the pin"):
        TaxsimPackageRunner().run_cases([_case(1, CALIFORNIA, 2024)])
    _assert_nothing_ran(stand_ins)


def test_same_size_replacement_after_lookup_refuses_before_running(
    stand_ins, monkeypatch
) -> None:
    """Bytes swapped between lookup and run are caught by the pre-run hash."""
    locate = pins.locate_binary

    def locate_then_swap(sha, **kwargs):
        path = locate(sha, **kwargs)
        data = path.read_bytes()
        path.write_bytes(data.replace(b"fiitax", b"FIITAX"))
        return path

    runner = TaxsimPackageRunner(binary_locator=locate_then_swap)
    with pytest.raises(pins.TaxsimPinError, match="changed after it was verified"):
        runner.run_cases([_case(1, CALIFORNIA, 2024)])
    _assert_nothing_ran(stand_ins)


def test_one_missing_partition_runs_no_partition(stand_ins) -> None:
    """Every partition's binary is located before any partition runs."""
    stand_ins.old.unlink()
    cases = [_case(1, CALIFORNIA, 2024), _case(2, GEORGIA, 2024)]
    with pytest.raises(pins.TaxsimPinError, match=stand_ins.shas["old"]):
        TaxsimPackageRunner().run_cases(cases)
    _assert_nothing_ran(stand_ins)


def test_a_row_without_a_year_refuses_under_a_year_dependent_profile(stand_ins):
    case = Case(case_id="x", period="2024", metadata={"taxsim_input": {"taxsimid": 1}})
    with pytest.raises(pins.TaxsimPinError, match="has no year"):
        TaxsimPackageRunner().run_cases([case])
    _assert_nothing_ran(stand_ins)


def test_default_path_without_a_selection_refuses() -> None:
    with pytest.raises(pins.TaxsimPinError, match="no pinned TAXSIM binary"):
        TaxsimPackageRunner()._execute_binary(None)


# --- invariants --------------------------------------------------------------

_ROWS = st.lists(
    st.tuples(
        st.sampled_from([0, CALIFORNIA, GEORGIA, MARYLAND]),
        st.sampled_from([2023, 2024, 2025]),
    ),
    min_size=1,
    max_size=12,
)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(rows=_ROWS)
def test_rows_run_on_their_resolved_binary_in_input_order(stand_ins, rows) -> None:
    """Order, per-row binary, and per-binary row counts all hold.

    * results are the input cases, in input order;
    * each result's stamped SHA-256 and scope equal the profile's resolution
      for its (state, year), and its output came from that binary;
    * the identity block's rows (and rows per scope) sum to the rows run.
    """
    pins.clear_hash_cache()
    profile = pins.get_profile("split")
    cases = [_case(index + 1, state, year) for index, (state, year) in enumerate(rows)]
    runner = TaxsimPackageRunner()
    results = runner.run_cases(cases, variables=["fiitax"])
    assert [result.household_id for result in results] == [c.case_id for c in cases]
    fiitax_by_sha = {stand_ins.shas["main"]: 11.0, stand_ins.shas["old"]: 22.0}
    for result, (state, year) in zip(results, rows, strict=True):
        expected = profile.resolve(state, year, stand_ins.system)
        assert result.raw["taxsim_binary_sha256"] == expected.sha256
        assert result.raw["taxsim_pin_scope"] == expected.scope
        assert result.values == {"fiitax": fiitax_by_sha[expected.sha256]}
    identity = runner.taxsim_identity()
    assert identity["pin_profile"] == "split"
    assert sum(binary["rows"] for binary in identity["binaries"]) == len(rows)
    for binary in identity["binaries"]:
        assert binary["pinned"] is True
        assert sum(binary["scopes"].values()) == binary["rows"]
    assert not stand_ins.markers["decoy"].exists()


def _naive_resolve(raw_profile: dict, state: int, year: int, system: str) -> str:
    """Reference resolution read straight from the pin JSON."""
    hits = [
        override["binaries"][system]
        for override in raw_profile.get("overrides", [])
        if state in override["states"] and year in override["years"]
    ]
    assert len(hits) <= 1, "overlapping overrides"
    return hits[0] if hits else raw_profile["binaries"][system]


@settings(max_examples=300, deadline=None)
@given(
    profile_name=st.sampled_from(sorted(pins.load_pins()["profiles"])),
    system=st.sampled_from(list(pins.PLATFORMS)),
    state=st.integers(0, 51),
    year=st.integers(1960, 2030),
)
def test_profile_resolution_matches_a_reference_reading_of_the_pin_file(
    profile_name, system, state, year
) -> None:
    """Differential: ``Profile.resolve`` against an independent JSON reading."""
    raw = pins.load_pins()["profiles"][profile_name]
    resolution = pins.get_profile(profile_name).resolve(state, year, system)
    assert resolution.sha256 == _naive_resolve(raw, state, year, system)
    assert pins.load_pins()["binaries"][resolution.sha256]["platform"] == system


# --- taxsim-csv rows -----------------------------------------------------------
#
# A taxsim-csv run without --period skips the CLI's law-year preflight (each
# row keeps its own year), so the runner's per-batch check against each
# profile binary is the only one those rows get.

CSV_FIXTURE = Path(__file__).parent / "fixtures" / "taxsim_csv" / "cps_households_sample.csv"


def _csv_cases(period: str | None = None) -> list[Case]:
    from axiom_oracles.populations.taxsim_csv import read_taxsim_csv

    data = read_taxsim_csv(CSV_FIXTURE, period=period)
    return data.select(scope=None, sample_size=None).cases


def test_taxsim_csv_row_years_are_checked_per_batch_against_the_profile_binary(
    stand_ins,
) -> None:
    cases = _csv_cases()
    assert {case.metadata["taxsim_input"]["year"] for case in cases} == {2021}
    stand_ins.set_law_years("main", 1960, 2020)
    with pytest.raises(pins.TaxsimLawYearError, match="law year 2021"):
        TaxsimPackageRunner().run_cases(cases, variables=["fiitax"])
    _assert_nothing_ran(stand_ins)
    stand_ins.set_law_years("main", 1960, 2021)
    results = TaxsimPackageRunner().run_cases(cases, variables=["fiitax"])
    assert [r.household_id for r in results] == [c.case_id for c in cases]
    assert {r.raw["taxsim_binary_sha256"] for r in results} == {stand_ins.shas["main"]}


def test_taxsim_csv_period_override_routes_ga_md_to_the_override_binary(
    stand_ins,
) -> None:
    cases = _csv_cases(period="2024")
    states = {c.case_id: c.metadata["taxsim_input"]["state"] for c in cases}
    stand_ins.set_law_years("old", 1960, 2023)
    with pytest.raises(pins.TaxsimLawYearError, match="law year 2024"):
        TaxsimPackageRunner().run_cases(cases, variables=["fiitax"])
    # The refusal comes before any partition runs, the default one included.
    _assert_nothing_ran(stand_ins)
    stand_ins.set_law_years("old", 1960, 2024)
    runner = TaxsimPackageRunner()
    results = runner.run_cases(cases, variables=["fiitax"])
    for result in results:
        override = states[result.household_id] in (GEORGIA, MARYLAND)
        assert result.raw["taxsim_binary_sha256"] == (
            stand_ins.shas["old" if override else "main"]
        )
        assert result.raw["taxsim_pin_scope"] == (
            "override:ga-md" if override else "default"
        )
        assert result.values == {"fiitax": 22.0 if override else 11.0}
    scopes = {
        binary["sha256"]: binary["scopes"]
        for binary in runner.taxsim_identity()["binaries"]
    }
    assert scopes == {
        stand_ins.shas["main"]: {"default": 4},
        stand_ins.shas["old"]: {"override:ga-md": 2},
    }
