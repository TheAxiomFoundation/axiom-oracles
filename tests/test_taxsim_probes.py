"""Probe inputs, pin selection, and crash-report conservation (no PE run)."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.comparison.mappings import load_program_mappings
from axiom_oracles.core.results import EngineResult
from scripts import taxsim_probes as probes


@pytest.mark.parametrize("year", (2024, 2025))
@pytest.mark.parametrize("state", (0, 11, 21, 44))
@pytest.mark.parametrize("system", ("linux", "darwin", "windows"))
def test_no_fallback_profile_always_uses_september_default(year, state, system):
    actual = pins.resolve_binary(state, year, system, probes.NO_FALLBACK_PROFILE)
    expected = pins.resolve_binary(0, year, system, "dashboard-2026-09")
    assert actual == expected
    assert pins.get_profile(probes.NO_FALLBACK_PROFILE).resolve(
        state, year, system
    ).scope == pins.DEFAULT_SCOPE


def test_itemizer_fixture_is_the_two_exact_inputs():
    _, cases = probes.probe_inputs("emulator", 2024)
    first, second = [case.metadata["taxsim_input"] for case in cases]
    assert first == {
        "taxsimid": 77, "year": 2024, "state": 0, "mstat": 2,
        "page": 45, "sage": 45, "depx": 0, "pwages": 300000,
        "proptax": 3000, "mortgage": 30000, "idtl": 2,
    }
    assert second == {**first, "taxsimid": 78, "state": 44}


@pytest.mark.parametrize("year", (2024, 2025))
def test_crash_fixture_preserves_upstream_order_and_precision(year):
    _, cases = probes.probe_inputs("crash", year)
    assert [case.case_id for case in cases] == ["taxsim-76239", "taxsim-76431"]
    rows = [case.metadata["taxsim_input"] for case in cases]
    assert [row["state"] for row in rows] == [8, 21]
    assert rows[1]["pensions"] == float("6782.1240234374645")
    assert rows[1]["year"] == year


def test_failed_probe_becomes_one_engine_error_per_concept():
    _, cases = probes.probe_inputs("crash", 2024)
    mappings = [m for m in load_program_mappings() if m.concept_id in probes.CONCEPTS]
    success = [EngineResult("taxsim", c.case_id, {"fiitax": 0, "siitax": 0},
                            raw={"fiitax": 0, "siitax": 0}) for c in cases]
    failure = replace(
        success[1], values={}, errors=("taxsim-crash:SIGFPE",),
        raw={"taxsim_error": {"signature": "SIGFPE", "returncode": -8}},
    )
    probes.assert_result_contract(cases, [success[0], failure])
    report = probes._report("taxsim-crash-probes-2024", cases, mappings,
                            success, [success[0], failure])
    assert len(report["mismatches"]) == 2
    assert all(row["kind"] == "engine_error" for row in report["mismatches"])
    assert all(row["error"]["signature"] == "SIGFPE" for row in report["mismatches"])


def test_probe_contract_rejects_dropped_households():
    _, cases = probes.probe_inputs("crash", 2024)
    with pytest.raises(AssertionError, match="IDs"):
        probes.assert_result_contract(cases, [])


@pytest.mark.parametrize("suite", (
    "taxsim-emulator-probes", "taxsim-crash-probes-2024", "taxsim-crash-probes-2025",
))
def test_committed_probe_report_preserves_all_observed_outputs(suite):
    path = Path(__file__).resolve().parents[1] / "reports" / "taxsim-emulator" / f"{suite}.json"
    report = json.loads(path.read_text())
    observed = report["probe_observations"]
    assert observed["platform"] in {"darwin", "linux", "windows"}
    assert report["dataset_identity"]["rows"] == 2
    assert len(observed["left"]) == len(observed["right"]) == 2
    assert {row["case_id"] for row in observed["left"]} == {
        row["case_id"] for row in observed["right"]
    }
    assert sum(b["rows"] for b in report["engine_identity"]["taxsim"]["binaries"]) == 2
