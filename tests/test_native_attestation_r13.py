"""Native producer stops and invalid returns survive publication and scoring."""

import importlib.util
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges import efrs_uk, tax_populace
from axiom_oracles.conformance.attestation import attest
from axiom_oracles.conformance.loader import Universe, parse
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
STOP_FLAGS = [
    pytest.param({"errors": ["execution failed"]}, id="errors"),
    pytest.param({"error": "execution failed"}, id="error"),
    pytest.param({"skipped": True}, id="skipped"),
    pytest.param({"skip_reason": "stopped"}, id="skip-reason"),
    pytest.param({"executed": False}, id="unexecuted"),
]
INVALID_VALUES = [
    pytest.param(None, id="missing"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(
        f"native_r13_{name}", ROOT / "scripts" / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def native_module():
    return _load_script("run_comparison")


class _Frame:
    """The native FIIT producer's small dataframe interface."""

    def __init__(self, rows):
        self.iloc = rows

    def reset_index(self, **_kwargs):
        return self


def _fiit_raw(flags=None, *, stopped_returns=True, amount=0):
    spec = next(iter(tax_populace.SURFACE_OUTPUTS["employee-medicare"].values()))
    outputs = {spec["axiom"]: {"kind": "quantity", "value": {"value": amount}}}
    results = [{"outputs": outputs}]
    if flags is not None:
        results.append({"outputs": outputs if stopped_returns else {}, **flags})
    return tax_populace.compare_outputs(
        pe_data={
            "tax_units": _Frame([{}]),
            "persons": _Frame([{spec["pe"]: amount} for _ in results]),
            "tax_unit_ids": [1],
            "person_ids": list(range(1, len(results) + 1)),
        },
        axiom_outputs_by_surface={"employee-medicare": results},
        tolerance=0,
        relative_tolerance=0,
    ).to_json()


def _fiit_score(report):
    source = parse(ROOT / "conformance/us-pe.yaml")
    policy = replace(source.by_name()["employee_medicare_tax"], suite="fiit-ecps")
    evidence = attest(report, oracle=source.oracle)
    board, rows = score_jurisdiction(
        Universe(source.jurisdiction, source.oracle, [policy]), [report],
    )
    return evidence, board, rows


@pytest.mark.parametrize("flags", STOP_FLAGS)
@pytest.mark.parametrize("stopped_returns", [False, True], ids=["no-return", "matching-zero"])
@pytest.mark.parametrize("stamped", [False, True], ids=["unstamped", "stamped"])
def test_fiit_clean_sibling_cannot_mask_a_stopped_result(
    native_module, flags, stopped_returns, stamped,
):
    raw = _fiit_raw(flags, stopped_returns=stopped_returns)
    report = native_module._adapt_tax_ecps_to_v2(raw, {}, suite="fiit-ecps")
    if not stamped:
        report.pop("attestation")
    evidence, board, rows = _fiit_score(report)

    assert not evidence.eligible
    assert board.covered == 0
    assert not rows[0].covered
    assert not board.conformant
    assert raw["compared_values"] == report["summary"]["comparison_count"] == 1
    assert raw["mismatch_count"] == 0
    assert raw["output_summary"][0]["compared"] == 1
    assert raw["errors"] == [{
        "engine": "axiom", "case_id": "person_2", "surface": "employee-medicare",
        **flags,
    }]
    assert report["errors"] == raw["errors"]
    assert report["summary"]["error_count"] == 1
    assert report["summary"]["errors_by_engine"] == {"axiom": 1}


@pytest.mark.parametrize("flags", STOP_FLAGS)
def test_fiit_shard_merge_preserves_result_stop_ledger(native_module, flags):
    clean = native_module._adapt_tax_ecps_to_v2(_fiit_raw(), {}, suite="fiit-ecps")
    stopped = native_module._adapt_tax_ecps_to_v2(
        _fiit_raw(flags, stopped_returns=False), {}, suite="fiit-ecps",
    )
    merged = _load_script("merge_shard_reports").merge([clean, stopped])
    # Shard merging is not an execution producer; its first shard's optional
    # stamp cannot certify the combined run.
    merged.pop("attestation")
    evidence, board, rows = _fiit_score(merged)

    assert not evidence.eligible
    assert board.covered == 0
    assert not rows[0].covered
    assert merged["errors"] == stopped["errors"]
    assert merged["summary"]["comparison_count"] == 2
    assert merged["summary"]["error_count"] == 1
    assert merged["summary"]["errors_by_engine"] == {"axiom": 1}


@pytest.mark.parametrize("amount", [0, False], ids=["zero", "false"])
@pytest.mark.parametrize("stamped", [False, True], ids=["unstamped", "stamped"])
def test_fiit_finite_clean_result_still_covers(native_module, amount, stamped):
    raw = _fiit_raw(amount=amount)
    report = native_module._adapt_tax_ecps_to_v2(raw, {}, suite="fiit-ecps")
    if not stamped:
        report.pop("attestation")
    evidence, board, rows = _fiit_score(report)

    assert evidence.eligible
    assert evidence.binds(("employee_medicare_tax",))
    assert board.covered == 1
    assert rows[0].covered
    assert board.conformant
    assert raw["compared_values"] == 1
    assert raw["errors"] == report["errors"] == []


@settings(max_examples=20, deadline=None, database=None, derandomize=True)
@example(flags={"skipped": True}, stopped_returns=True, amount=0)
@given(
    flags=st.sampled_from([parameter.values[0] for parameter in STOP_FLAGS]),
    stopped_returns=st.booleans(),
    amount=st.one_of(st.booleans(), st.integers(min_value=-10_000, max_value=10_000)),
)
def test_fiit_result_stops_never_increment_comparison_counts(flags, stopped_returns, amount):
    raw = _fiit_raw(flags, stopped_returns=stopped_returns, amount=amount)

    assert raw["compared_values"] == 1
    assert raw["output_summary"][0]["compared"] == 1
    assert raw["mismatch_count"] == 0
    assert raw["errors"] == [{
        "engine": "axiom", "case_id": "person_2", "surface": "employee-medicare",
        **flags,
    }]


def _efrs_native(oracle_value=0, axiom_value=1, *, flags=None):
    spec = efrs_uk.PERSONAL_ALLOWANCE_OUTPUTS["personal_allowance"]
    return efrs_uk.compare_outputs(
        pe_data={"persons": [{"person_id": 1, "personal_allowance": oracle_value}],
                 "person_ids": [1]},
        axiom_outputs_by_surface={"personal-allowance": [{
            "outputs": {spec["axiom"]: {
                "kind": "quantity", "value": {"value": axiom_value},
            }},
            **(flags or {}),
        }]},
        tolerance=0,
        relative_tolerance=0,
    )


def _standard_json(value):
    try:
        return json.dumps(value, allow_nan=False)
    except ValueError:
        return None


@pytest.mark.parametrize("invalid", INVALID_VALUES)
@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
def test_efrs_invalid_returns_serialize_as_absent_evidence(native_module, invalid, engine):
    native = _efrs_native(**{
        "axiom_value" if engine == "axiom" else "oracle_value": invalid,
    })
    raw = native.to_json()
    encoded = _standard_json(raw)
    assert encoded is not None
    assert raw["mismatches"][0][engine] is None
    assert raw["mismatches"][0]["diff"] is None
    assert raw["compared_values"] == raw["mismatch_count"] == 1
    # Serialization does not change the original invalid return or residual.
    assert native.mismatches[0].diff != 0
    report = native_module._adapt_uk_efrs_to_v2(json.loads(encoded), {}, suite="uk-tax-benefits-efrs")
    assert _standard_json(report) is not None
    assert not attest(report, oracle="policyengine").binds(("personal_allowance",))
    side = "left" if engine == "axiom" else "right"
    assert report["mismatches"][0][side] is None
    assert report["mismatches"][0]["difference"] is None


@pytest.mark.parametrize("invalid", INVALID_VALUES[1:])
def test_efrs_adapter_normalizes_legacy_nonfinite_values_without_erasing_stops(native_module, invalid):
    raw = _efrs_native().to_json()
    raw["mismatches"][0].update(policyengine=invalid, diff=invalid)
    raw["errors"] = [{
        "engine": "axiom", "case_id": "person_1", "surface": "personal-allowance",
        "error": invalid,
    }]
    report = native_module._adapt_uk_efrs_to_v2(raw, {}, suite="uk-tax-benefits-efrs")

    assert _standard_json(report) is not None
    assert report["mismatches"][0]["right"] is None
    assert report["mismatches"][0]["difference"] is None
    assert report["errors"][0]["error"] is True
    assert report["errors"][0]["case_id"] == "person_1"
    assert report["errors"][0]["surface"] == "personal-allowance"
    assert report["summary"]["error_count"] == 1
    assert not attest(report, oracle="policyengine").eligible


@pytest.mark.parametrize("invalid", INVALID_VALUES[1:])
def test_efrs_native_json_preserves_nonfinite_execution_stop_diagnostics(invalid):
    native = _efrs_native(flags={"error": invalid})
    raw = native.to_json()

    assert _standard_json(raw) is not None
    assert raw["errors"] == [{
        "engine": "axiom", "case_id": "person_1", "surface": "personal-allowance",
        "error": True,
    }]
    assert raw["compared_values"] == 0
    assert raw["mismatches"] == []


@pytest.mark.parametrize("oracle_value", [0, False], ids=["zero", "false"])
def test_efrs_finite_zero_returns_survive_strict_json(native_module, oracle_value):
    raw = _efrs_native(oracle_value=oracle_value).to_json()
    encoded = _standard_json(raw)
    assert encoded is not None
    report = native_module._adapt_uk_efrs_to_v2(json.loads(encoded), {}, suite="uk-tax-benefits-efrs")

    assert _standard_json(report) is not None
    assert report["mismatches"][0]["right"] == 0
    assert report["mismatches"][0]["difference"] == 1
    assert attest(report, oracle="policyengine").binds(("personal_allowance",))


@settings(max_examples=30, deadline=None, database=None, derandomize=True)
@example(returned_value=float("nan"))
@given(returned_value=st.one_of(st.none(), st.floats(allow_nan=True, allow_infinity=True)))
def test_efrs_serialization_follows_an_independent_finite_value_predicate(returned_value):
    raw = _efrs_native(oracle_value=returned_value, axiom_value=0).to_json()
    finite_return = returned_value is not None and math.isfinite(returned_value)

    assert _standard_json(raw) is not None
    assert raw["compared_values"] == 1
    if raw["mismatches"]:
        expected_value = float(returned_value) if finite_return else None
        expected_residual = -float(returned_value) if finite_return else None
        assert raw["mismatches"][0]["policyengine"] == expected_value
        assert raw["mismatches"][0]["diff"] == expected_residual
    else:
        assert finite_return and returned_value == 0
