"""Real report dialects retain engine identity and producer-specific bindings."""

import json
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA, OracleTargetResolver, attest,
)
from axiom_oracles.conformance.loader import parse as parse_universe
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
YALE_COLUMNS = frozenset({
    "statutory_base_rate",
    "statutory_rate_232",
    "statutory_rate_ieepa_recip",
    "statutory_rate_ieepa_fent",
    "statutory_rate_301",
    "statutory_rate_301_cs",
    "statutory_rate_s301fl",
    "statutory_rate_s301br",
    "statutory_rate_s338",
    "statutory_rate_s122",
    "statutory_rate_section_201",
    "statutory_rate_other",
})
PROPERTY_SETTINGS = settings(max_examples=50, deadline=None, derandomize=True)


def _committed_report(filename):
    return json.loads((ROOT / "dashboard/public/data" / filename).read_text())


def _panel_report(units=2):
    return {
        "suite": "us-tariff-panel",
        "engines": {
            "axiom": "tariff_total",
            "yale_statutory": "Yale statutory panel description, not a variable",
            "versions": {"axiom_rules_engine": "0.1.0"},
        },
        "case_count": units,
        "summary": {
            "comparison_count": units,
            "slots": {"mfn": {"matches": units, "mismatches": 0}},
        },
        "scope": {
            "comparison_units": units,
            "authority_slots": ["mfn"],
            "reference": {"columns": ["statutory_base_rate"]},
        },
        "cases": [{
            "unit_count": units,
            "expected": {"mfn": 0.1},
            "axiom": {"mfn": 0.1},
        }],
        "provenance": {"generated_by": "scripts/run_comparison.py::us-tariff-panel"},
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": True,
            "case_count": units,
            "comparison_count": units,
            "error_count": 0,
        },
    }


def test_committed_dk_role_pair_keeps_engine_identity_but_requires_execution_stamp():
    report = _committed_report("axiom-euromod-dk-child-youth-benefit.json")
    universe = parse_universe(ROOT / "conformance/dk.yaml")
    evidence = attest(report, oracle=universe.oracle)

    assert "attestation" not in report
    assert not evidence.eligible
    assert not evidence.executed
    assert evidence.engines == ("axiom", "euromod")
    assert not evidence.attested_outputs
    assert not evidence.outputs_complete
    assert score_jurisdiction(universe, [report])[0].covered == 0


def test_committed_yale_panel_requires_execution_stamp_before_attesting_columns():
    report = _committed_report("axiom-yale-us-tariff-panel.json")
    universe = parse_universe(ROOT / "conformance/us-tariff-yale.yaml")
    evidence = attest(report, oracle=universe.oracle, resolver=OracleTargetResolver())

    assert "attestation" not in report
    assert not evidence.eligible
    assert not evidence.executed
    assert evidence.engines == ("axiom", "yale_statutory")
    assert not evidence.attested_outputs
    assert not evidence.outputs_complete
    assert all(not evidence.binds(policy.output_vars) for policy in universe.policies if policy.in_scope)
    assert score_jurisdiction(universe, [report])[0].covered == 0


def test_yale_direct_generator_provenance_uses_the_same_slot_bindings():
    report = _panel_report()
    report["provenance"] = {"generator": "scripts/generate_us_tariff_panel.py"}
    evidence = attest(report, oracle="yale-tariff", resolver=OracleTargetResolver())

    assert evidence.eligible
    assert evidence.attested_outputs == frozenset({"statutory_base_rate"})
    assert not evidence.outputs_complete


def test_yale_summed_slot_does_not_invent_its_individual_returned_columns():
    report = _panel_report()
    report["summary"]["slots"] = {"ieepa": {"matches": 2, "mismatches": 0}}
    report["scope"]["authority_slots"] = ["ieepa"]
    report["scope"]["reference"]["columns"] = [
        "statutory_rate_ieepa_recip", "statutory_rate_ieepa_fent",
    ]
    report["cases"][0]["expected"] = {"ieepa": 0.1}
    report["cases"][0]["axiom"] = {"ieepa": 0.1}
    evidence = attest(report, oracle="yale-tariff", resolver=OracleTargetResolver())

    assert evidence.eligible
    assert not evidence.attested_outputs
    assert not evidence.outputs_complete


@pytest.mark.parametrize("missing_evidence", [
    "producer", "summary_slot", "declared_slot", "column", "expected_slot",
    "axiom_slot", "cases", "scope_units", "boolean_count", "negative_count",
])
def test_yale_cannot_infer_an_output_without_its_producer_and_comparison_evidence(missing_evidence):
    report = _panel_report()
    if missing_evidence == "producer":
        report.pop("provenance")
    elif missing_evidence == "summary_slot":
        report["summary"]["slots"].pop("mfn")
    elif missing_evidence == "declared_slot":
        report["scope"]["authority_slots"] = []
    elif missing_evidence == "column":
        report["scope"]["reference"]["columns"] = []
    elif missing_evidence == "expected_slot":
        report["cases"][0]["expected"].pop("mfn")
    elif missing_evidence == "axiom_slot":
        report["cases"][0]["axiom"].pop("mfn")
    elif missing_evidence == "cases":
        report["cases"] = []
    elif missing_evidence == "scope_units":
        report["scope"]["comparison_units"] = 0
    elif missing_evidence == "boolean_count":
        report["summary"]["slots"]["mfn"]["matches"] = True
    elif missing_evidence == "negative_count":
        report["summary"]["slots"]["mfn"] = {"matches": 3, "mismatches": -1}
    evidence = attest(report, oracle="yale-tariff", resolver=OracleTargetResolver())

    assert evidence.attested_outputs == frozenset()
    assert not evidence.outputs_complete


@pytest.mark.parametrize("side", ["expected", "axiom"])
@pytest.mark.parametrize("value", [None, "0.1", True, float("nan"), float("inf"), float("-inf")])
def test_yale_family_slot_requires_finite_numeric_comparison_values(side, value):
    report = _panel_report()
    report["cases"][0][side]["mfn"] = value
    evidence = attest(report, oracle="yale-tariff", resolver=OracleTargetResolver())

    assert evidence.attested_outputs == frozenset()
    assert not evidence.outputs_complete


@PROPERTY_SETTINGS
@given(
    axiom_present=st.booleans(),
    oracle_present=st.booleans(),
    versions=st.dictionaries(
        st.sampled_from(("axiom", "euromod", "policyengine", "left", "right")),
        st.text(max_size=20),
        max_size=5,
    ),
)
def test_engine_versions_neither_remove_nor_supply_a_comparison_party(
    axiom_present, oracle_present, versions
):
    report = {
        "suite": "probe",
        "case_count": 1,
        "summary": {"comparison_count": 1},
        "engines": {
            "left": "axiom" if axiom_present else "taxcalc",
            "right": "euromod" if oracle_present else "taxsim",
            "versions": versions,
        },
        "attestation": {"schema_version": EXECUTION_ATTESTATION_SCHEMA, "executed": True},
    }
    evidence = attest(report, oracle="euromod", resolver=OracleTargetResolver())

    assert evidence.eligible == (axiom_present and oracle_present)
    assert "versions" not in evidence.engines
    assert ("axiom" in evidence.engines) == axiom_present
    assert ("euromod" in evidence.engines) == oracle_present


@PROPERTY_SETTINGS
@example(units=1, delta=0)
@given(units=st.integers(min_value=1, max_value=200), delta=st.integers(-200, 200))
def test_yale_output_claim_must_reconcile_to_its_case_family_evidence(units, delta):
    report = _panel_report(units)
    report["summary"]["slots"]["mfn"]["matches"] = units + delta
    evidence = attest(report, oracle="yale-tariff", resolver=OracleTargetResolver())

    assert evidence.binds(("statutory_base_rate",)) == (delta == 0)
