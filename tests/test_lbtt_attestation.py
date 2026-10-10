"""The native devolved grid records exact per-case queries despite its heading."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.conformance.attestation import attest
from axiom_oracles.conformance.loader import Universe, parse
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
LBTT = "uk:policies/govuk/lbtt#land_and_buildings_transaction_tax"
LTT = "uk:policies/govuk/ltt#land_transaction_tax"
PE_LBTT = "land_and_buildings_transaction_tax"
PE_LTT = "land_transaction_tax"


def _report(value=0):
    return {
        "suite": "uk-lbtt-ltt", "concept": "uk-lbtt-ltt",
        "engines": {
            "axiom": "uk:policies/govuk/{lbtt,ltt} devolved transaction tax",
            "policyengine": f"{PE_LBTT}, {PE_LTT}",
        },
        "case_count": 1,
        "summary": {"comparison_count": 1, "error_count": 0},
        "cases": [{"case_id": "real-1", "country": "SCOTLAND",
                   "concept": LBTT, "axiom": value, "policyengine": value,
                   "axiom_vs_policyengine": {"match": True, "difference": 0}}],
        "provenance": {"generator": "scripts/generate_uk_lbtt_ltt.py"},
    }


def _covered(report):
    original = parse(ROOT / "conformance/uk-pe.yaml")
    policy = next(row for row in original.policies if row.id == "uk-pe:lbtt_ltt")
    universe = Universe(original.jurisdiction, original.oracle,
                        [replace(policy, suite="uk-lbtt-ltt")])
    return score_jurisdiction(universe, [report])[0].covered


def test_historical_native_lbtt_pairs_cover_without_a_stamp():
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-uk-lbtt-ltt.json").read_text())
    assert "attestation" not in report
    assert any(row["axiom"] == row["policyengine"] == 0 for row in report["cases"])
    evidence = attest(report, oracle="policyengine")
    assert evidence.eligible
    assert evidence.attested_outputs == frozenset({PE_LBTT, PE_LTT})
    assert _covered(report) == 1


def test_native_lbtt_authority_matches_the_actual_producers_queries():
    from scripts.generate_uk_lbtt_ltt import TxnCase

    report = _report()
    wales = TxnCase("real-2", "WALES", 0, 0, "nil-rate")
    report["cases"].append({"case_id": wales.case_id, "country": wales.country,
                            "concept": wales.concept, "axiom": 0, "policyengine": 0})
    scotland = TxnCase("real-1", "SCOTLAND", 0, 0, "nil-rate")
    report["case_count"] = report["summary"]["comparison_count"] = 2
    assert report["cases"][0]["concept"] == scotland.output
    assert report["cases"][1]["concept"] == wales.output
    assert attest(report, oracle="policyengine").attested_outputs == frozenset({
        scotland.pe_variable, wales.pe_variable,
    })


@settings(max_examples=40, deadline=None, derandomize=True)
@given(value=st.one_of(st.booleans(), st.floats(allow_nan=False, allow_infinity=False)))
def test_native_lbtt_finite_same_case_pairs_preserve_zero_and_false(value):
    assert attest(_report(value), oracle="policyengine").attested_outputs == frozenset({PE_LBTT})


@pytest.mark.parametrize("outputs", [LBTT, [LBTT, LTT]])
def test_native_lbtt_explicit_axiom_heading_agrees_with_the_recorded_query(outputs):
    report = _report()
    report["engines"]["axiom"] = outputs
    assert attest(report, oracle="policyengine").attested_outputs == frozenset({PE_LBTT})


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), float("-inf")])
def test_native_lbtt_missing_or_nonfinite_side_cannot_cover(engine, value):
    report = _report()
    report["cases"][0][engine] = value
    assert not attest(report, oracle="policyengine").attested_outputs
    assert _covered(report) == 0


def test_native_lbtt_disjoint_real_cases_cannot_supply_one_pair():
    report = _report()
    report["cases"][0]["axiom"] = None
    other = deepcopy(report["cases"][0])
    other.update(case_id="real-2", axiom=0, policyengine=None)
    report["cases"].append(other)
    report["case_count"] = report["summary"]["comparison_count"] = 2
    assert not attest(report, oracle="policyengine").attested_outputs
    assert _covered(report) == 0


@pytest.mark.parametrize("contradiction", [
    "country", "query", "diagnostic", "producer", "suite", "declared_axiom", "declared_oracle",
    "explicit_axiom", "explicit_oracle", "empty_oracle", "engine_axiom", "engine_oracle",
])
def test_native_lbtt_ambiguous_or_contradicted_bindings_cannot_cover(contradiction):
    report = _report()
    if contradiction == "country":
        report["cases"][0]["country"] = "WALES"
    elif contradiction == "query":
        report["cases"][0]["concept"] = LTT
    elif contradiction == "diagnostic":
        report["cases"][0]["concept"] = "uk:policies/govuk/lbtt#lbtt_main_residential_standard_charge"
    elif contradiction == "producer":
        report["provenance"]["generator"] = "a-different-producer"
    elif contradiction == "suite":
        report["suite"] = "a-different-suite"
    elif contradiction == "declared_axiom":
        report["engines"]["axiom"] = LTT
    elif contradiction == "declared_oracle":
        report["engines"]["policyengine"] = PE_LTT
    elif contradiction == "explicit_axiom":
        report["output_bindings"] = {LBTT: {"axiom": LTT}}
    elif contradiction == "explicit_oracle":
        report["output_bindings"] = {LBTT: {"policyengine": PE_LTT}}
    elif contradiction == "empty_oracle":
        report["output_bindings"] = {LBTT: {"policyengine": []}}
    elif contradiction == "engine_axiom":
        report["engine_bindings"] = {"axiom": {"outputs": [LTT]}}
    elif contradiction == "engine_oracle":
        report["engine_bindings"] = {"policyengine": {"outputs": [PE_LTT]}}
    assert not attest(report, oracle="policyengine").attested_outputs
    assert _covered(report) == 0


@pytest.mark.parametrize("flag", ["skipped", "error", "executed", "right_errors"])
def test_native_lbtt_case_stop_evidence_overrides_finite_pairs(flag):
    report = _report()
    report["cases"][0][flag] = False if flag == "executed" else ["stopped"] if flag == "right_errors" else True
    assert not attest(report, oracle="policyengine").attested_outputs
    assert _covered(report) == 0
