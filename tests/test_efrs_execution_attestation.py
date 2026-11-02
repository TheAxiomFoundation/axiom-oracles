"""Stopped native EFRS executions must survive through coverage scoring."""

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges.efrs_uk import (
    CARERS_ALLOWANCE_FINAL_OUTPUTS,
    compare_outputs,
)
from axiom_oracles.conformance.attestation import attest
from axiom_oracles.conformance.loader import Universe, parse
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
SUITE = "uk-tax-benefits-efrs"
STOP_FLAGS = [
    pytest.param({"errors": ["execution failed"]}, id="errors"),
    pytest.param({"error": "execution failed"}, id="error"),
    pytest.param({"skipped": True}, id="skipped"),
    pytest.param({"skip_reason": "execution cancelled"}, id="skip-reason"),
    pytest.param({"executed": False}, id="unexecuted"),
]


@pytest.fixture(scope="module")
def native_module():
    spec = importlib.util.spec_from_file_location(
        "efrs_execution_run_comparison", ROOT / "scripts/run_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adapter(native_module):
    return native_module._adapt_uk_efrs_to_v2


def _native_report(flags, *, omitted=False, amount=100):
    output = next(iter(CARERS_ALLOWANCE_FINAL_OUTPUTS.values()))["axiom"]

    def result(value, markers):
        return {
            "outputs": {
                output: {"kind": "quantity", "value": {"value": value}}
            },
            **markers,
        }

    # A matching stopped case would never appear in the displayed mismatches.
    # Keep a genuine mismatch beside it so omission cannot hide the error.
    results = (
        [result(0, {}), result(amount, flags)]
        if omitted
        else [result(0, flags)]
    )
    persons = [
        {"person_id": index + 1, "carers_allowance": amount}
        for index in range(len(results))
    ]
    return compare_outputs(
        pe_data={"persons": persons, "person_ids": list(range(1, len(results) + 1))},
        axiom_outputs_by_surface={"carers-allowance-final": results},
        tolerance=0,
        relative_tolerance=0,
    ).to_json()


def _score(raw, adapter):
    report = adapter(raw, {}, suite=SUITE)
    source = parse(ROOT / "conformance/uk-pe.yaml")
    policy = replace(source.by_name()["carers_allowance"], suite=SUITE)
    board, rows = score_jurisdiction(
        Universe(source.jurisdiction, source.oracle, [policy]), [report]
    )
    return report, attest(report, oracle=source.oracle), board, rows


@pytest.mark.parametrize("flags", STOP_FLAGS)
@pytest.mark.parametrize("omitted", [False, True], ids=["visible", "omitted-match"])
def test_native_efrs_stop_markers_defeat_coverage_through_the_full_pipeline(
    adapter, flags, omitted,
):
    raw = _native_report(flags, omitted=omitted)
    report, evidence, board, rows = _score(raw, adapter)

    assert not evidence.eligible
    assert board.covered == 0
    assert not rows[0].covered
    assert len(raw["errors"]) == 1
    error = raw["errors"][0]
    assert error["engine"] == "axiom"
    assert error["surface"] == "carers-allowance-final"
    assert error["case_id"] == ("person_2" if omitted else "person_1")
    for key, value in flags.items():
        assert error[key] == value
    assert report["errors"] == raw["errors"]
    assert report["summary"]["error_count"] == len(raw["errors"])
    assert report["summary"]["errors_by_engine"] == {"axiom": len(raw["errors"])}
    assert raw["compared_values"] == int(omitted)
    assert len(raw["mismatches"]) == int(omitted)


def test_native_efrs_successful_execution_still_covers_its_returned_output(adapter):
    raw = _native_report({"errors": [], "skipped": False, "executed": True})
    report, evidence, board, rows = _score(raw, adapter)

    assert evidence.eligible
    assert evidence.binds(("carers_allowance",))
    assert board.covered == 1
    assert rows[0].covered
    assert raw["compared_values"] == len(raw["mismatches"]) == 1
    assert not raw.get("errors")
    assert not report["errors"]


@pytest.mark.parametrize("flags", STOP_FLAGS)
def test_native_efrs_merge_retains_stopped_cases_omitted_from_mismatches(
    native_module, adapter, flags,
):
    raw = native_module._merge_uk_efrs_reports([
        _native_report({}),
        _native_report(flags, omitted=True),
    ])
    report, evidence, board, rows = _score(raw, adapter)

    assert not evidence.eligible
    assert board.covered == 0
    assert not rows[0].covered
    assert len(raw["errors"]) == 1
    assert report["errors"] == raw["errors"]
    assert raw["compared_values"] == len(raw["mismatches"]) == 2


@settings(max_examples=30, deadline=None, derandomize=True)
@example(flags={"errors": ["execution failed"]}, omitted=False, amount=100)
@given(
    flags=st.sampled_from([entry.values[0] for entry in STOP_FLAGS]),
    omitted=st.booleans(),
    amount=st.integers(min_value=1, max_value=10_000),
)
def test_native_efrs_finite_returns_cannot_override_execution_stop_evidence(
    adapter, flags, omitted, amount,
):
    raw = _native_report(flags, omitted=omitted, amount=amount)
    _report, evidence, board, rows = _score(raw, adapter)

    assert not evidence.eligible
    assert board.covered == 0
    assert not rows[0].covered
