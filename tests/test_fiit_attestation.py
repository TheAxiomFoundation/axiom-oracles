"""FIIT binding must follow the FIIT producer's actual compared outputs."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from axiom_oracles.conformance.attestation import attest
from axiom_oracles.bridges.tax_populace import SURFACE_OUTPUTS, compare_outputs
from axiom_oracles.conformance.loader import Universe, parse
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]


def _adapter():
    spec = importlib.util.spec_from_file_location(
        "fiit_run_comparison", ROOT / "scripts/run_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._adapt_tax_ecps_to_v2


@pytest.mark.parametrize(
    ("surface", "output", "variable"),
    [
        ("tax-before-credits", "income_tax_main_rates", "income_tax_main_rates"),
        ("ctc", "ctc_before_advance_payments", "ctc"),
        ("standard-deduction", "basic_standard_deduction", "basic_standard_deduction"),
        ("income-tax", "income_tax_refundable_credits", "income_tax_refundable_credits"),
    ],
)
def test_adapter_attests_only_positive_fiit_output_summary_rows(surface, output, variable):
    raw = {
        "compared_tax_units": 1,
        "compared_values": 1,
        "mismatch_count": 0,
        "mismatches": [],
        "observed_outputs": [
            {"case_id": "tax_unit_1", "surface": surface, "output": output,
             "engine": "policyengine", "variable": variable, "value": 0},
        ],
        "output_summary": [
            {"surface": surface, "output": output, "compared": 1, "mismatches": 0},
            {
                "surface": "capital-gain-definitions",
                "output": "net_capital_gain",
                "compared": 0,
                "mismatches": 0,
            },
        ],
    }
    report = _adapter()(raw, {}, suite="fiit-ecps")
    evidence = attest(report, oracle="policyengine")

    assert evidence.attested_outputs == frozenset({variable})
    assert evidence.outputs_complete
    assert evidence.eligible
    assert report["output_summary"] == raw["output_summary"]
    assert report["attestation"]["outputs"] == [
        {
            "engine": "policyengine",
            "concept": report["aggregates"][1]["concept"],
            "variable": variable,
            "comparisons": 1,
        }
    ]


def test_committed_legacy_fiit_uses_its_own_producer_bindings():
    report = json.loads(
        (ROOT / "dashboard/public/data/axiom-policyengine-fiit-ecps.json").read_text()
    )
    evidence = attest(report, oracle="policyengine")

    assert not evidence.binds(("capital_gains_tax",))
    # This report preserves counts and names but not the returned values.
    assert not evidence.binds(("income_tax_main_rates", "ctc"))
    assert "ctc" not in evidence.attested_outputs
    assert "ctc_value" not in evidence.attested_outputs
    # The parent is a total of component comparisons, not a queried income_tax.
    assert "income_tax" not in evidence.attested_outputs
    # The legacy adapter dropped the final-income-tax surface while retaining
    # its counts in the synthetic parent, so those outputs remain unrecorded.
    assert not evidence.outputs_complete


def test_partial_legacy_fiit_surface_cannot_invent_unrecorded_outputs():
    report = _adapter()(
        {
            "compared_tax_units": 1,
            "compared_values": 1,
            "mismatch_count": 0,
            "mismatches": [],
            "output_summary": [
                {
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "compared": 1,
                    "mismatches": 0,
                }
            ],
        },
        {},
        suite="fiit-ecps",
    )
    report.pop("attestation", None)
    report.pop("output_summary", None)
    report["provenance"] = {"generated_by": "scripts/run_comparison.py::fiit-ecps"}
    evidence = attest(report, oracle="policyengine")

    assert evidence.attested_outputs == frozenset()
    assert not evidence.outputs_complete


def test_unidentified_legacy_fiit_producer_cannot_use_generic_bindings():
    report = json.loads(
        (ROOT / "dashboard/public/data/axiom-policyengine-fiit-ecps.json").read_text()
    )
    report.pop("provenance", None)
    evidence = attest(report, oracle="policyengine")

    assert not evidence.eligible
    assert evidence.attested_outputs == frozenset()
    assert not evidence.outputs_complete


class _Frame:
    """The dataframe interface used by the real FIIT comparison producer."""

    def __init__(self, rows):
        self.iloc = rows

    def reset_index(self, **_kwargs):
        return self


@pytest.mark.parametrize(
    ("surface", "policy_name", "oracle_value", "axiom_value", "covered"),
    [
        pytest.param("employee-medicare", "employee_medicare_tax", None, 0, False,
                     id="review-null-oracle"),
        pytest.param("employee-medicare", "employee_medicare_tax", float("nan"), 0, False,
                     id="review-nan-oracle"),
        pytest.param("ctc", "ctc", None, 0, False, id="review-ctc-null-oracle"),
        pytest.param("employee-medicare", "employee_medicare_tax", float("inf"), 0, False,
                     id="infinite-oracle"),
        pytest.param("employee-medicare", "employee_medicare_tax", 0, None, True,
                     id="observed-oracle-with-missing-axiom"),
        pytest.param("employee-medicare", "employee_medicare_tax", 0, 0, True,
                     id="observed-zero-control"),
        pytest.param("employee-medicare", "employee_medicare_tax", False, False, True,
                     id="observed-false-control"),
        pytest.param("ctc", "ctc", 0, 0, True, id="observed-ctc-zero-control"),
    ],
)
def test_native_fiit_coverage_requires_returned_values(
    surface, policy_name, oracle_value, axiom_value, covered,
):
    """The producer must preserve missing values through adapter and scoreboard."""
    specs = SURFACE_OUTPUTS[surface]
    pe_row = {spec["pe"]: oracle_value for spec in specs.values()}
    outputs = {
        spec["axiom"]: {"kind": "quantity", "value": {"value": axiom_value}}
        for spec in specs.values()
    }
    raw = compare_outputs(
        pe_data={
            "tax_units": _Frame([pe_row]),
            "persons": _Frame([pe_row]),
            "tax_unit_ids": [1],
            "person_ids": [1],
        },
        axiom_outputs_by_surface={surface: [{"outputs": outputs}]},
        tolerance=0,
        relative_tolerance=0,
    ).to_json()
    report = _adapter()(raw, {}, suite="fiit-ecps")
    source = parse(ROOT / "conformance/us-pe.yaml")
    policy = replace(source.by_name()[policy_name], suite="fiit-ecps")
    universe = Universe("us-pe", source.oracle, [policy])
    evidence = attest(report, oracle=source.oracle)
    board, rows = score_jurisdiction(universe, [report])

    assert evidence.binds(policy.output_vars) is covered
    assert board.covered == int(covered)
    assert rows[0].covered is covered


@pytest.mark.parametrize("flags", [
    {"errors": ["engine failed after returning a value"]},
    {"error": "engine failed after returning a value"},
    {"skipped": True},
    {"skip_reason": "comparison skipped"},
    {"executed": False},
])
def test_native_fiit_errors_and_skips_contradict_returned_values(flags):
    """A numeric return cannot override the native comparison's error or skip."""
    spec = next(iter(SURFACE_OUTPUTS["employee-medicare"].values()))
    raw = compare_outputs(
        pe_data={
            "tax_units": _Frame([{}]),
            "persons": _Frame([{spec["pe"]: 0}]),
            "tax_unit_ids": [1],
            "person_ids": [1],
        },
        axiom_outputs_by_surface={"employee-medicare": [{
            "outputs": {spec["axiom"]: {"kind": "quantity", "value": {"value": 0}}},
            **flags,
        }]},
        tolerance=0,
        relative_tolerance=0,
    ).to_json()
    report = _adapter()(raw, {}, suite="fiit-ecps")
    source = parse(ROOT / "conformance/us-pe.yaml")
    policy = replace(source.by_name()["employee_medicare_tax"], suite="fiit-ecps")
    evidence = attest(report, oracle=source.oracle)
    board, rows = score_jurisdiction(Universe("us-pe", source.oracle, [policy]), [report])

    assert not evidence.binds(policy.output_vars)
    assert board.covered == 0
    assert not rows[0].covered


def _native_zero_raw(oracle_value=0, *, result_flags=None):
    spec = next(iter(SURFACE_OUTPUTS["employee-medicare"].values()))
    return compare_outputs(
        pe_data={
            "tax_units": _Frame([{}]),
            "persons": _Frame([{spec["pe"]: oracle_value}]),
            "tax_unit_ids": [1],
            "person_ids": [1],
        },
        axiom_outputs_by_surface={"employee-medicare": [{
            "outputs": {spec["axiom"]: {"kind": "quantity", "value": {"value": 0}}},
            **(result_flags or {}),
        }]},
        tolerance=0,
        relative_tolerance=0,
    ).to_json()


def _score_native_raw(raw):
    report = _adapter()(raw, {}, suite="fiit-ecps")
    source = parse(ROOT / "conformance/us-pe.yaml")
    policy = replace(source.by_name()["employee_medicare_tax"], suite="fiit-ecps")
    return report, attest(report, oracle=source.oracle), score_jurisdiction(
        Universe("us-pe", source.oracle, [policy]), [report],
    )


@pytest.mark.parametrize("flags", [
    pytest.param({"skipped": True}, id="global-skipped"),
    pytest.param({"skip_reason": "comparison cancelled"}, id="global-skip-reason"),
    pytest.param({"executed": False}, id="global-executed-false"),
    pytest.param({"executed": None}, id="global-executed-null"),
    pytest.param({"executed": "true"}, id="global-executed-string"),
    pytest.param({"error": "oracle could not execute"}, id="global-error"),
])
def test_fiit_adapter_preserves_global_execution_contradictions(flags):
    raw = _native_zero_raw()
    raw.update(flags)
    _, evidence, (board, rows) = _score_native_raw(raw)

    assert not evidence.binds(("employee_medicare_tax",))
    assert board.covered == 0
    assert not rows[0].covered


@pytest.mark.parametrize("case_id", [
    pytest.param(None, id="null-case-id"),
    pytest.param([], id="list-case-id"),
    pytest.param(float("nan"), id="nan-case-id"),
])
def test_fiit_adapter_cannot_invent_a_case_identity(case_id):
    raw = _native_zero_raw()
    raw["observed_outputs"][0]["case_id"] = case_id
    _, evidence, (board, rows) = _score_native_raw(raw)

    assert not evidence.binds(("employee_medicare_tax",))
    assert board.covered == 0
    assert not rows[0].covered


def test_fiit_adapter_cannot_prefix_an_absent_case_identity():
    raw = _native_zero_raw()
    raw["observed_outputs"][0].pop("case_id")
    _, evidence, (board, rows) = _score_native_raw(raw)

    assert not evidence.binds(("employee_medicare_tax",))
    assert board.covered == 0
    assert not rows[0].covered


@pytest.mark.parametrize(("oracle_value", "covered"), [
    pytest.param(None, False, id="null-oracle"),
    pytest.param(float("nan"), False, id="nan-oracle"),
    pytest.param(float("inf"), False, id="positive-infinite-oracle"),
    pytest.param(float("-inf"), False, id="negative-infinite-oracle"),
    pytest.param(0, True, id="returned-zero"),
    pytest.param(False, True, id="returned-false"),
])
def test_native_fiit_json_roundtrip_preserves_observation_validity(oracle_value, covered):
    """Published JSON keeps nonfinite returns absent and real zero/False observed."""
    raw = _native_zero_raw(oracle_value)
    serialized = json.dumps(raw, allow_nan=False)
    report, evidence, (board, rows) = _score_native_raw(json.loads(serialized))

    # The adapter's published artifact must also parse as standard JSON.
    json.loads(json.dumps(report, allow_nan=False))
    assert evidence.binds(("employee_medicare_tax",)) is covered
    assert board.covered == int(covered)
    assert rows[0].covered is covered


@pytest.mark.parametrize(("key", "value"), [
    pytest.param("skipped", float("nan"), id="skipped-nan"),
    pytest.param("skipped", float("inf"), id="skipped-positive-infinity"),
    pytest.param("skipped", float("-inf"), id="skipped-negative-infinity"),
    pytest.param("skip_reason", float("nan"), id="skip-reason-nan"),
    pytest.param("skip_reason", float("inf"), id="skip-reason-infinity"),
    pytest.param("error", float("nan"), id="error-nan"),
    pytest.param("errors", float("inf"), id="errors-infinity"),
])
def test_native_fiit_json_roundtrip_preserves_stop_evidence(key, value):
    """Serializing invalid numbers cannot erase an error or skip marker."""
    raw = _native_zero_raw(result_flags={key: value})
    assert raw["observed_outputs"][0][key] is True
    raw = json.loads(json.dumps(raw, allow_nan=False))
    report, evidence, (board, rows) = _score_native_raw(raw)

    json.loads(json.dumps(report, allow_nan=False))
    assert not evidence.binds(("employee_medicare_tax",))
    assert board.covered == 0
    assert not rows[0].covered
