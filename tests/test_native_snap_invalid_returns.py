"""Only finite returned SNAP values enter comparison counts or matches (#604).

The native SNAP producer used to pass every PolicyEngine return through
``native()``, which turned NaN and infinities into zero, and the CSV adapter
read a blank or unparseable cell as 0 or False. An invalid return then
arrived as a match with error-free execution evidence. These tests follow
the native FIIT fix in #368: invalid returns stay visible as diagnostic
mismatches with an engine error, never as a comparison or a match.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges import snap_populace
from axiom_oracles.bridges.snap_populace import (
    COMPARED_AXIOM_OUTPUT,
    JURISDICTION_CONFIGS,
    PE_COMPARED_OUTPUT,
    ProjectedCase,
)
from axiom_oracles.conformance.attestation import attest

ROOT = Path(__file__).parents[1]
CONFIG = JURISDICTION_CONFIGS["us-co"]
INVALID = [
    pytest.param(None, id="missing"),
    pytest.param(math.nan, id="nan"),
    pytest.param(math.inf, id="infinity"),
    pytest.param(-math.inf, id="negative-infinity"),
]
AMOUNT = "us:statutes/7/2014/u#snap_benefit"
ELIGIBILITY = "us:statutes/7/2014/o#snap_eligible"


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache
def runner():
    return _load("snap_604_runner", "scripts/run_comparison.py")


@lru_cache
def merger():
    return _load("snap_604_merge", "scripts/merge_shard_reports.py")


def pe_outputs(amount=100.0, eligible=True) -> dict:
    return {
        PE_COMPARED_OUTPUT: amount,
        "is_snap_eligible": eligible,
        "snap_gross_income": 0,
        "snap_net_income": 0,
        "snap_excess_shelter_expense_deduction": 0,
        "snap_standard_deduction": 0,
        "snap_earned_income_deduction": 0,
        "snap_dependent_care_deduction": 0,
        "snap_child_support_deduction": 0,
        "snap_child_support_gross_income_deduction": 0,
        "snap_excess_medical_expense_deduction": 0,
        "snap_max_allotment": 100,
        "snap_utility_allowance": 0,
        "housing_cost": 0,
        "has_usda_elderly_disabled": False,
        "meets_snap_categorical_eligibility": False,
        "snap_utility_allowance_type": "",
    }


def axiom_outputs(amount=100.0, eligible="holds") -> dict:
    outputs = {}
    for label, output_id in CONFIG.output_id_by_label.items():
        if label == "snap_eligible":
            outputs[output_id] = {"kind": "judgment", "outcome": eligible}
        elif label == COMPARED_AXIOM_OUTPUT:
            outputs[output_id] = {"value": {"kind": "decimal", "value": amount}}
        else:
            outputs[output_id] = {"value": {"kind": "decimal", "value": 0}}
    return {"outputs": outputs}


def produce(pairs):
    """Run the native producer on (pe_amount, pe_eligible, ax_amount, ax_eligible)."""
    cases, results = [], []
    for index, (pe_amount, pe_eligible, ax_amount, ax_eligible) in enumerate(pairs):
        cases.append(
            ProjectedCase(
                spm_unit_id=index + 1,
                household_id=index + 1,
                inputs={},
                member_inputs=[],
                pe_outputs=pe_outputs(pe_amount, pe_eligible),
            )
        )
        results.append(axiom_outputs(ax_amount, ax_eligible))
    return snap_populace.compare(cases, results, 1.5, config=CONFIG)


def through_csv(rows) -> list[dict]:
    """Serialize with the producer's CSV writer and read back as the runner does."""
    buffer = io.StringIO()
    snap_populace.write_csv_handle(buffer, rows)
    buffer.seek(0)
    return list(csv.DictReader(buffer))


def publish(rows) -> dict:
    report = runner()._adapt_snap_ecps_csv_to_v2(
        through_csv(rows), {"parameters": {"jurisdiction": "us-co"}}
    )
    # The published report must be portable through strict JSON.
    return json.loads(json.dumps(report, allow_nan=False))


def aggregate(report, concept):
    return next(row for row in report["aggregates"] if row["concept"] == concept)


# ── producer ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_producer_keeps_invalid_amount_and_records_engine_error(invalid, side):
    row = produce(
        [
            (
                invalid if side == "policyengine" else 100.0,
                True,
                invalid if side == "axiom" else 100.0,
                "holds",
            )
        ]
    )[0]
    assert row["amount_compared"] is False
    assert row["amount_match"] is False and row["match"] is False
    assert row["difference"] is None and row["absolute_difference"] is None
    assert row["errors"] == [
        {
            "engine": side,
            "output": "pe_snap" if side == "policyengine" else "axiom_snap_allotment",
            "error": "missing_or_nonfinite_output",
        }
    ]
    returned = row["pe_snap" if side == "policyengine" else "axiom_snap_allotment"]
    if invalid is None:
        assert returned is None
    else:
        assert returned is invalid or (math.isnan(returned) and math.isnan(invalid))
    assert row["eligibility_compared"] is True


@pytest.mark.parametrize("invalid", [None, math.nan, "maybe"])
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_producer_keeps_invalid_eligibility_out_of_comparison(invalid, side):
    row = produce(
        [
            (
                100.0,
                invalid if side == "policyengine" else True,
                100.0,
                invalid if side == "axiom" else "holds",
            )
        ]
    )[0]
    assert row["eligibility_compared"] is False
    assert row["amount_compared"] is True and row["amount_match"] is True
    assert [error["engine"] for error in row["errors"]] == [side]


@pytest.mark.parametrize(
    "pe_eligible,ax_eligible", [(False, "not_holds"), (True, "holds")]
)
def test_producer_controls_keep_genuine_zero_and_false(pe_eligible, ax_eligible):
    row = produce([(0.0, pe_eligible, 0, ax_eligible)])[0]
    assert row["amount_compared"] is row["eligibility_compared"] is True
    assert row["match"] is True and row["errors"] == []
    assert row["pe_snap"] == row["axiom_snap_allotment"] == 0


def test_producer_summary_prints_with_invalid_rows(capsys):
    rows = produce([(None, True, 100.0, "holds"), (90.0, True, 100.0, "holds")])
    snap_populace.print_summary(rows, 1.5, 5)
    out = capsys.readouterr().out
    assert "Uncompared rows (invalid returns): 1" in out
    assert "Max absolute difference: $10.00" in out


# ── adapter, serialization, attestation ───────────────────────────────────
def assert_one_failed_amount_pair(report, *, engine):
    summary = report["summary"]
    # Two SNAP units: one clean pair per concept, one failed amount pair.
    assert summary["comparison_count"] == 3
    assert summary["match_count"] == 3
    assert summary["mismatch_count"] == summary["uncompared_mismatches"] == 1
    assert summary["weighted"]["mismatch_weight"] == 0
    assert summary["error_count"] == 1
    assert summary["errors_by_engine"] == {engine: 1}
    output = "pe_snap" if engine == "policyengine" else "axiom_snap_allotment"
    assert report["errors"] == [
        {
            "engine": engine,
            "case_id": "ecps-spm-2",
            "concept": AMOUNT,
            "output": output,
            "error": "missing_or_nonfinite_output",
        }
    ]
    amount = aggregate(report, AMOUNT)
    assert amount["comparison_count"] == amount["match_count"] == 1
    assert amount["mismatch_count"] == amount["uncompared_mismatches"] == 1
    assert amount["mismatch_weight"] == 0
    [mismatch] = report["mismatches"]
    assert mismatch["uncompared"] is True and mismatch["difference"] is None
    case = next(case for case in report["cases"] if case["case_id"] == "ecps-spm-2")
    side = "right_errors" if engine == "policyengine" else "left_errors"
    assert case[side] == report["errors"]
    evidence = attest(report, oracle="policyengine")
    assert any("engine error" in problem for problem in evidence.problems)
    assert not evidence.eligible


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_invalid_amount_is_not_a_match_after_csv_and_adapter(invalid, side):
    rows = produce(
        [
            (100.0, True, 100.0, "holds"),
            (
                invalid if side == "policyengine" else 0.0,
                True,
                invalid if side == "axiom" else 0.0,
                "holds",
            ),
        ]
    )
    assert_one_failed_amount_pair(publish(rows), engine=side)


@pytest.mark.parametrize("cell", ["", "nan", "NaN", "inf", "-inf", "None", "n/a"])
@pytest.mark.parametrize("column", ["pe_snap", "axiom_snap_allotment"])
def test_adapter_rejects_invalid_cells_from_any_producer(cell, column):
    # The axiom-encode producer writes the same CSV without the new ledger
    # columns, so the adapter must detect invalid cells by itself.
    rows = through_csv(
        produce([(100.0, True, 100.0, "holds"), (0.0, True, 0.0, "holds")])
    )
    for row in rows:
        for key in ("errors", "amount_compared", "eligibility_compared"):
            row.pop(key)
    rows[1][column] = cell
    rows[1]["match"] = "True"
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    report = json.loads(json.dumps(report, allow_nan=False))
    engine = "policyengine" if column == "pe_snap" else "axiom"
    assert_one_failed_amount_pair(report, engine=engine)


@pytest.mark.parametrize("cell", ["", "None", "nan", "maybe"])
@pytest.mark.parametrize("column", ["pe_snap_eligible", "axiom_snap_eligible"])
def test_adapter_never_reads_a_missing_verdict_as_false(cell, column):
    rows = through_csv(
        produce([(100.0, False, 100.0, "not_holds"), (0.0, False, 0.0, "not_holds")])
    )
    rows[1][column] = cell
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    eligibility = aggregate(report, ELIGIBILITY)
    assert eligibility["comparison_count"] == eligibility["match_count"] == 1
    assert eligibility["uncompared_mismatches"] == 1
    assert report["summary"]["error_count"] == 1
    assert not attest(report, oracle="policyengine").eligible


def test_adapter_controls_keep_genuine_zero_and_false_matches():
    rows = produce([(0.0, False, 0.0, "not_holds"), (0.0, True, 0.0, "holds")])
    report = publish(rows)
    summary = report["summary"]
    assert summary["comparison_count"] == summary["match_count"] == 4
    assert summary["mismatch_count"] == summary["error_count"] == 0
    assert summary["uncompared_mismatches"] == 0
    assert report["errors"] == []
    assert attest(report, oracle="policyengine").error_count == 0


def test_finite_disagreement_keeps_its_comparison_and_weight():
    report = publish(produce([(100.0, True, 50.0, "holds")]))
    amount = aggregate(report, AMOUNT)
    assert amount["comparison_count"] == amount["mismatch_count"] == 1
    assert amount["mismatch_weight"] == 1 and amount["uncompared_mismatches"] == 0
    assert report["summary"]["error_count"] == 0


def test_shard_merge_carries_the_error_ledger():
    rows = produce([(100.0, True, 100.0, "holds"), (None, True, 0.0, "holds")])
    report = publish(rows)
    merged = merger().merge([deepcopy(report), deepcopy(report)])
    summary = merged["summary"]
    assert summary["comparison_count"] == summary["match_count"] == 6
    assert summary["mismatch_count"] == summary["uncompared_mismatches"] == 2
    assert summary["error_count"] == len(merged["errors"]) == 2
    assert summary["errors_by_engine"] == {"policyengine": 2}
    amount = aggregate(merged, AMOUNT)
    assert amount["uncompared_mismatches"] == amount["mismatch_count"] == 2
    assert amount["mismatch_weight"] == 0
    assert not attest(merged, oracle="policyengine").eligible


_values = st.one_of(
    st.none(),
    st.sampled_from([math.nan, math.inf, -math.inf]),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
)
_verdicts = st.sampled_from([True, False, None, math.nan])


@settings(max_examples=60, deadline=None, database=None, derandomize=True)
@example(pairs=[(None, True, 0.0, True)])
@example(pairs=[(0.0, False, 0.0, False)])
@given(
    pairs=st.lists(
        st.tuples(_values, _verdicts, _values, _verdicts), min_size=1, max_size=6
    )
)
def test_only_valid_pairs_enter_snap_denominators(pairs):
    rows = produce(
        [
            (
                pe,
                pe_el,
                ax,
                {True: "holds", False: "not_holds"}.get(ax_el, ax_el)
                if not isinstance(ax_el, float)
                else ax_el,
            )
            for pe, pe_el, ax, ax_el in pairs
        ]
    )
    report = publish(rows)

    def finite(value):
        return isinstance(value, float) and math.isfinite(value)

    valid_amount = [(pe, ax) for pe, _, ax, _ in pairs if finite(pe) and finite(ax)]
    valid_elig = [
        (p, a) for _, p, _, a in pairs if isinstance(p, bool) and isinstance(a, bool)
    ]
    invalid_pairs = (len(pairs) - len(valid_amount)) + (len(pairs) - len(valid_elig))
    amount_matches = sum(abs(ax - pe) <= 1.5 for pe, ax in valid_amount)
    elig_matches = sum(p == a for p, a in valid_elig)
    summary = report["summary"]
    assert summary["comparison_count"] == len(valid_amount) + len(valid_elig)
    assert summary["match_count"] == amount_matches + elig_matches
    assert summary["uncompared_mismatches"] == invalid_pairs
    assert summary["weighted"]["mismatch_weight"] == (
        summary["comparison_count"] - summary["match_count"]
    )
    assert attest(report, oracle="policyengine").error_count >= invalid_pairs
    if invalid_pairs:
        assert not attest(report, oracle="policyengine").eligible


# ── loader: invalid support values never become zero inputs ─────────────────
def load_stub(monkeypatch, variable, value):
    np = pytest.importorskip("numpy")
    arrays = {
        "spm_unit_id": [1],
        "person_spm_unit_id": [1],
        "person_household_id": [1],
        "household_id": [1],
        "state_code_str": ["CO"],
        "snap_unit_size": [1],
        "spm_unit_size": [1],
        PE_COMPARED_OUTPUT: [10.0],
        "snap_utility_allowance_type": ["SUA"],
        "snap_utility_region_str": [""],
    }

    def calculate(name, period=None):
        if name == variable:
            return np.array([value], dtype=object)
        return np.array(arrays.get(name, [0.0]))

    sim = SimpleNamespace(calculate=calculate)
    monkeypatch.setitem(
        __import__("sys").modules,
        "policyengine_us",
        SimpleNamespace(Microsimulation=lambda **_kwargs: sim),
    )
    monkeypatch.setattr(
        snap_populace, "load_populace_dataset", lambda *_a, **_k: object()
    )
    monkeypatch.setattr(snap_populace, "legalize_inputs", lambda inputs, _index: inputs)
    return snap_populace.load_policyengine_cases(
        config=CONFIG,
        base_inputs={},
        period=snap_populace.month_period(2026, 1),
        state="CO",
        sample_size=None,
        positive_snap_only=False,
        utility_projection="raw",
        populace_year=2024,
    )


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize(
    "variable", sorted(snap_populace.POLICYENGINE_INPUT_SUPPORT_VARIABLES)
)
def test_loader_rejects_invalid_support_values_before_projection(
    monkeypatch, invalid, variable
):
    with pytest.raises(
        ValueError, match=f"spm_unit_1 {variable}: missing or nonfinite"
    ):
        load_stub(monkeypatch, variable, invalid)


@pytest.mark.parametrize("invalid", INVALID)
def test_loader_preserves_invalid_compared_return(monkeypatch, invalid):
    [case] = load_stub(monkeypatch, "is_snap_eligible", invalid)
    returned = case.pe_outputs["is_snap_eligible"]
    assert (
        returned is None
        if invalid is None
        else (returned == invalid or (math.isnan(returned) and math.isnan(invalid)))
    )


@pytest.mark.parametrize("value", [0, 0.0, False])
def test_loader_keeps_finite_zero_and_false(monkeypatch, value):
    [case] = load_stub(monkeypatch, "snap_assets", value)
    assert case.pe_outputs["snap_assets"] == value


def test_every_support_variable_read_for_inputs_is_validated():
    # Guard drift: any PolicyEngine value the projections read must be either
    # validated support or a compared/diagnostic output.
    import re

    source = (ROOT / "axiom_oracles/bridges/snap_populace.py").read_text()
    read = set(re.findall(r'values\["([a-z_]+)"\]', source))
    read |= {
        "pre_subsidy_electricity_expense",
        "water_expense",
        "sewage_expense",
        "trash_expense",
        "gas_expense",
        "phone_expense",
    }
    allowed = snap_populace.POLICYENGINE_INPUT_SUPPORT_VARIABLES | {
        "snap_utility_allowance_type",
        "is_snap_eligible",
    }
    assert read <= allowed, read - allowed
