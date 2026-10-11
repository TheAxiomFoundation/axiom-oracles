"""Only finite returned FIIT values enter arithmetic or match denominators."""

import importlib.util
import json
import math
import sys
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges import tax_populace
from axiom_oracles.conformance.attestation import attest
from axiom_oracles.conformance.loader import Universe, parse
from axiom_oracles.conformance.scoreboard import score_jurisdiction

ROOT = Path(__file__).parents[1]
INVALID = [
    pytest.param(None, id="missing"),
    pytest.param(math.nan, id="nan"),
    pytest.param(math.inf, id="infinity"),
    pytest.param(-math.inf, id="negative-infinity"),
]


class Frame:
    def __init__(self, rows):
        self.iloc = rows

    def reset_index(self, **_kwargs):
        return self

    def iterrows(self):
        return iter(enumerate(self.iloc))


@lru_cache
def runner():
    spec = importlib.util.spec_from_file_location("fiit_r14_runner", ROOT / "scripts/run_comparison.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache
def universe():
    source = parse(ROOT / "conformance/us-pe.yaml")
    policy = replace(source.by_name()["employee_medicare_tax"], suite="fiit-ecps")
    return Universe(source.jurisdiction, source.oracle, [policy])


def produce(oracle_value, axiom_value, *, sibling=0, surface="employee-medicare"):
    specs = tax_populace.SURFACE_OUTPUTS[surface]
    name, output = next(iter(specs.items()))
    pe_rows = [{spec["pe"]: sibling for spec in specs.values()},
               {spec["pe"]: 0 for spec in specs.values()}]
    pe_rows[1][output["pe"]] = oracle_value
    results = [{"outputs": {
        spec["axiom"]: {"kind": "quantity", "value": {"value": amount}}
        for spec in specs.values()
    }} for amount in (sibling, 0)]
    results[1]["outputs"][output["axiom"]]["value"]["value"] = axiom_value
    raw = tax_populace.compare_outputs(
        pe_data={"tax_units": Frame(pe_rows), "persons": Frame(pe_rows),
                 "tax_unit_ids": [1, 2], "person_ids": [1, 2]},
        axiom_outputs_by_surface={surface: results}, tolerance=0, relative_tolerance=0,
    ).to_json()
    return raw, name


def publish(raw, *, stamped):
    # The retained native ledger must be portable through strict JSON too.
    report = runner()._adapt_tax_ecps_to_v2(
        json.loads(json.dumps(deepcopy(raw), allow_nan=False)), {}, suite="fiit-ecps",
    )
    if not stamped:
        report.pop("attestation")
    evidence = attest(report, oracle=universe().oracle)
    board, _ = score_jurisdiction(universe(), [report])
    return report, evidence, board


def assert_invalid(raw, report, evidence, board, *, engine, name="employee_medicare_tax"):
    assert raw["compared_values"] == report["summary"]["comparison_count"] == 1
    assert report["summary"]["match_count"] == 1
    assert raw["mismatch_count"] == report["summary"]["mismatch_count"] == 1
    assert raw["uncompared_mismatches"] == report["summary"]["uncompared_mismatches"] == 1
    assert raw["errors"] == [{
        "engine": engine, "case_id": "person_2", "surface": "employee-medicare",
        "output": name, "error": "missing_or_nonfinite_output",
    }]
    assert report["errors"] == raw["errors"]
    assert report["summary"]["error_count"] == 1
    assert report["summary"]["errors_by_engine"] == {engine: 1}
    assert report["summary"]["weighted"]["mismatch_weight"] == 0
    for aggregate in report["aggregates"]:
        assert aggregate["comparison_count"] == aggregate["match_weight"] == 1
        assert aggregate["mismatch_weight"] == 0
        assert aggregate["uncompared_mismatches"] == 1
    summary = raw["output_summary"][0]
    assert summary["compared"] == summary["uncompared_mismatches"] == summary["mismatches"] == 1
    assert not evidence.eligible
    assert board.covered == 0
    assert not board.conformant
    assert len(raw["observed_outputs"]) == 2
    invalid_side = "value" if engine == "policyengine" else "counterpart_value"
    assert raw["observed_outputs"][1][invalid_side] is None


@pytest.mark.parametrize("sibling", [0, 50])
@pytest.mark.parametrize("invalid", INVALID[:2])
@pytest.mark.parametrize("stamped", [False, True], ids=["unstamped", "stamped"])
def test_missing_oracle_with_clean_sibling_is_not_a_match(sibling, invalid, stamped):
    """The reviewer's eight reachable attacks must fail across publication."""
    raw, name = produce(invalid, 0, sibling=sibling)
    assert_invalid(raw, *publish(raw, stamped=stamped), engine="policyengine", name=name)


@pytest.mark.parametrize("value,side", [(None, "axiom"), (math.nan, "axiom"),
                                        (0, "policyengine"), (False, "policyengine")])
@pytest.mark.parametrize("stamped", [False, True], ids=["unstamped", "stamped"])
def test_review_controls_preserve_missing_axiom_mismatch_and_real_zero(value, side, stamped):
    """Eight controls retain Axiom failure and genuine zero/False agreement."""
    raw, name = produce(value if side == "policyengine" else 0,
                        value if side == "axiom" else 0)
    report, evidence, board = publish(raw, stamped=stamped)
    if side == "axiom":
        assert_invalid(raw, report, evidence, board, engine=side, name=name)
    else:
        assert raw["compared_values"] == report["summary"]["match_count"] == 2
        assert raw["mismatch_count"] == report["summary"]["error_count"] == 0
        assert evidence.eligible and board.covered == 1 and board.conformant
        assert raw["observed_outputs"][1]["value"] == value


@pytest.mark.parametrize("invalid", INVALID[2:])
@pytest.mark.parametrize("side", ["axiom", "policyengine"])
@pytest.mark.parametrize("stamped", [False, True])
def test_infinity_remains_a_diagnostic_mismatch_outside_comparison_counts(invalid, side, stamped):
    raw, name = produce(invalid if side == "policyengine" else 0,
                        invalid if side == "axiom" else 0)
    assert_invalid(raw, *publish(raw, stamped=stamped), engine=side, name=name)


def test_finite_disagreement_keeps_its_comparison_and_mismatch_weight():
    raw, _ = produce(50, 0)
    report, evidence, board = publish(raw, stamped=False)
    assert raw["compared_values"] == report["summary"]["comparison_count"] == 2
    assert report["summary"]["match_count"] == report["summary"]["mismatch_count"] == 1
    assert report["summary"]["weighted"]["mismatch_weight"] == 1
    assert raw["uncompared_mismatches"] == 0
    assert raw["errors"] == []
    assert evidence.eligible and board.covered == 1 and not board.conformant


def test_both_invalid_engines_record_one_failed_pair_and_two_errors():
    raw, _ = produce(None, math.nan)
    report, evidence, board = publish(raw, stamped=True)
    assert raw["compared_values"] == report["summary"]["match_count"] == 1
    assert raw["mismatch_count"] == raw["uncompared_mismatches"] == 1
    assert report["summary"]["error_count"] == 2
    assert report["summary"]["errors_by_engine"] == {"axiom": 1, "policyengine": 1}
    assert not evidence.eligible and not board.covered and not board.conformant


def test_shard_merge_sums_uncompared_diagnostic_mismatches():
    spec = importlib.util.spec_from_file_location("fiit_r14_merge", ROOT / "scripts/merge_shard_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw, _ = produce(None, 0)
    report, _, _ = publish(raw, stamped=False)
    merged = module.merge([deepcopy(report), deepcopy(report)])
    assert merged["summary"]["uncompared_mismatches"] == 2
    assert merged["summary"]["comparison_count"] == merged["summary"]["match_count"] == 2
    assert merged["summary"]["mismatch_count"] == merged["summary"]["error_count"] == 2
    for aggregate in merged["aggregates"]:
        assert aggregate["uncompared_mismatches"] == aggregate["mismatch_count"] == 2
        assert aggregate["mismatch_weight"] == 0
    assert not attest(merged, oracle=universe().oracle).eligible


@pytest.mark.parametrize("surface", list(tax_populace.SURFACE_OUTPUTS))
@pytest.mark.parametrize("side", ["axiom", "policyengine"])
def test_every_fiit_surface_excludes_missing_returns(surface, side):
    raw, name = produce(None if side == "policyengine" else 0,
                        None if side == "axiom" else 0, surface=surface)
    expected = 2 * len(tax_populace.SURFACE_OUTPUTS[surface]) - 1
    assert raw["compared_values"] == expected
    assert raw["mismatch_count"] == raw["uncompared_mismatches"] == 1
    marker = "person_2" if surface in tax_populace.PAYROLL_SURFACES else "tax_unit_2"
    assert raw["errors"] == [{"engine": side, "case_id": marker, "surface": surface,
                               "output": name, "error": "missing_or_nonfinite_output"}]


@settings(max_examples=24, deadline=None, database=None, derandomize=True)
@example(sibling=0, invalid=None, side="policyengine", stamped=False)
@example(sibling=50, invalid=math.nan, side="policyengine", stamped=True)
@given(sibling=st.one_of(st.booleans(), st.integers(-10_000, 10_000)),
       invalid=st.sampled_from([None, math.nan, math.inf, -math.inf]),
       side=st.sampled_from(["axiom", "policyengine"]), stamped=st.booleans())
def test_only_finite_pairs_can_enter_fiit_match_denominators(sibling, invalid, side, stamped):
    raw, name = produce(invalid if side == "policyengine" else 0,
                        invalid if side == "axiom" else 0, sibling=sibling)
    assert_invalid(raw, *publish(raw, stamped=stamped), engine=side, name=name)


def load_stub(monkeypatch, value, *, entity):
    pd = pytest.importorskip("pandas")
    tables = {"tax_unit": pd.DataFrame([{"tax_unit_id": 7}]),
              "person": pd.DataFrame([{"person_id": 9, "person_tax_unit_id": 7}]),
              "household": pd.DataFrame([{}])}
    variable = "adjusted_gross_income" if entity == "tax_unit" else "employment_income"
    sim = SimpleNamespace(calculate=lambda name, period: [value])
    monkeypatch.setitem(sys.modules, "policyengine_us", SimpleNamespace(Microsimulation=lambda **_kwargs: sim))
    monkeypatch.setattr(tax_populace, "load_populace_dataset", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(tax_populace, "population_table", lambda _dataset, kind: tables[kind])
    monkeypatch.setattr(tax_populace, "select_tax_unit_indices", lambda **_kwargs: [0])
    return tax_populace.load_policyengine_tax_data(
        year=2026, sample_size=1, positive_ctc_only=False, data_folder=ROOT,
        populace_year=2024, tax_unit_variables=(variable,) if entity == "tax_unit" else (),
        person_variables=(variable,) if entity == "person" else (),
    )


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("entity", ["tax_unit", "person"])
def test_loader_rejects_invalid_calculated_support_before_zero_projection(monkeypatch, invalid, entity):
    variable = "adjusted_gross_income" if entity == "tax_unit" else "employment_income"
    marker = "tax_unit_7" if entity == "tax_unit" else "person_9"
    with pytest.raises(ValueError, match=f"{marker}.*{variable}.*missing or nonfinite"):
        load_stub(monkeypatch, invalid, entity=entity)


@pytest.mark.parametrize("value", [0, False])
@pytest.mark.parametrize("entity", ["tax_unit", "person"])
def test_loader_keeps_finite_zero_and_false(monkeypatch, value, entity):
    data = load_stub(monkeypatch, value, entity=entity)
    column = "adjusted_gross_income" if entity == "tax_unit" else "employment_income"
    table = data["tax_units" if entity == "tax_unit" else "persons"]
    assert table.iloc[0][column] == value
