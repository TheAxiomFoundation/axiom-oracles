"""Legacy bindings require returned oracle values, including for mapped sums."""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.dispositions import apply_dispositions
from axiom_oracles.comparison.mappings import load_program_mappings
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance.attestation import attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


ORACLE = OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine")


def _legacy_report(values_by_case, oracle_on_left=False, *, compact=False, axiom_missing=False):
    # Reuse review-368-r9-attestation-probes.py's real committed sum mapping.
    mapping = next(
        mapping for mapping in load_program_mappings()
        if mapping.target_for_engine("policyengine")
        == ["income_tax_main_rates", "capital_gains_tax"]
    )
    targets = mapping.target_for_engine("axiom")
    axiom_values = {target: 0 for target in targets} if isinstance(targets, list) else {targets: 0}
    if axiom_missing:
        axiom_values = {}
    axiom = [EngineResult("axiom", index, axiom_values) for index in range(len(values_by_case))]
    oracle = [EngineResult("policyengine", index, values) for index, values in enumerate(values_by_case)]
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report = build_comparison_report(
        suite_name="probe", population="synthetic", locales=set(), scope=None,
        cases=[Case(case_id=index, period="2026") for index in range(len(values_by_case))],
        mappings=[mapping], comparisons=Comparator([mapping]).compare(left, right),
    )
    # Exercise legacy binding deduction with explicit execution evidence. The
    # declaration and aggregate counts are not returned per-output values.
    report["attestation"].pop("outputs")
    report["observed_outputs"] = [
        {
            "case_id": index, "engine": "policyengine", "concept": mapping.concept_id,
            "variable": variable, "value": value,
        }
        for index, values in enumerate(values_by_case)
        for variable, value in values.items()
        if variable in mapping.target_for_engine("policyengine")
    ]
    if compact:
        report["cases"] = []
    return report, mapping


def _score(report, output="capital_gains_tax"):
    universe = Universe("us-pe", ORACLE, [UniversePolicy(
        id=f"us-pe:{output}", oracle_policy_name=output,
        output_vars=(output,), in_scope=True, suite="probe",
    )])
    # Deliberately exercise the production resolver, rather than an empty stub.
    return score_jurisdiction(universe, [report])


@pytest.mark.parametrize("oracle_on_left", [False, True])
@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("explained", [False, True])
def test_legacy_partial_sum_cannot_cover_absent_output(oracle_on_left, compact, explained):
    report, mapping = _legacy_report([{"income_tax_main_rates": 0}], oracle_on_left, compact=compact)
    assert report["summary"]["mismatch_count"] == 1
    if explained:
        report = apply_dispositions(report, {
            "schema": "axiom_oracles.dispositions.v1", "suite": "probe",
            "entries": [{
                "id": "missing-oracle-output", "concept": mapping.concept_id,
                "case_id": 0, "disposition": "upstream_engine_gap",
                "evidence": {
                    "mechanism": "The oracle omitted the configured capital_gains_tax output.",
                    "sources": ["tests/test_legacy_attestation_presence.py"],
                },
                "expires_on_source_change": True,
            }],
        })
        assert report["summary"]["dispositioned"]["unexplained_count"] == 0
    evidence = attest(report, oracle=ORACLE)
    assert evidence.eligible
    board, rows = _score(report)
    assert board.covered == 0
    assert not board.conformant
    assert rows[0].status == "unbound"
    assert evidence.attested_outputs == {"income_tax_main_rates"}
    assert not evidence.outputs_complete


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_legacy_positive_comparison_count_alone_is_not_output_evidence(oracle_on_left):
    report, _ = _legacy_report([{"income_tax_main_rates": 0}], oracle_on_left, compact=True)
    # Older compact reports can omit missing-value counters and case values.
    for aggregate in report["aggregates"]:
        for key in ("missing_left_count", "missing_right_count", "missing_both_count"):
            aggregate.pop(key)
    report["mismatches"] = []
    report["observed_outputs"] = []
    assert not attest(report, oracle=ORACLE).attested_outputs
    assert _score(report)[0].covered == 0


@pytest.mark.parametrize("oracle_on_left", [False, True])
@pytest.mark.parametrize("value", [0, False])
def test_legacy_complete_sum_retains_zero_and_false_evidence(oracle_on_left, value):
    report, _ = _legacy_report(
        [{"income_tax_main_rates": 0, "capital_gains_tax": value}], oracle_on_left,
    )
    board, _ = _score(report)
    assert board.covered == 1
    assert board.conformant


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_compact_legacy_returned_output_rows_prove_complete_sum(oracle_on_left):
    report, _ = _legacy_report(
        [{"income_tax_main_rates": 0, "capital_gains_tax": 0}],
        oracle_on_left, compact=True,
    )
    report["aggregates"] = [{
        "concept": report["aggregates"][0]["concept"], "comparison_count": 1,
    }]
    assert _score(report)[0].covered == 1


def test_legacy_grid_retains_its_explicit_variable_binding():
    report, _ = _legacy_report([{"income_tax_main_rates": 0, "capital_gains_tax": 0}])
    report["engines"] = {
        "axiom": "federal_income_tax", "policyengine": "income_tax_main_rates,capital_gains_tax",
    }
    evidence = attest(report, oracle=ORACLE)
    assert evidence.outputs_complete
    assert evidence.attested_outputs == {"income_tax_main_rates", "capital_gains_tax"}
    assert _score(report)[0].covered == 1


@pytest.mark.parametrize("oracle_on_left", [False, True])
@pytest.mark.parametrize("value", [0, False])
def test_legacy_recorded_oracle_value_binds_when_axiom_value_is_missing(oracle_on_left, value):
    report, _ = _legacy_report(
        [{"income_tax_main_rates": 0, "capital_gains_tax": value}],
        oracle_on_left, axiom_missing=True,
    )
    report["aggregates"] = [{
        "concept": report["aggregates"][0]["concept"], "comparison_count": 1,
    }]
    assert report["summary"]["match_count"] == 0
    assert _score(report)[0].covered == 1


@settings(max_examples=40, deadline=None, database=None, derandomize=True)
@given(
    values_by_case=st.lists(
        st.fixed_dictionaries(
            {"income_tax_main_rates": st.booleans() | st.integers(-100, 100)},
            optional={"capital_gains_tax": st.none()},
        ), min_size=1, max_size=5,
    ),
    oracle_on_left=st.booleans(), compact=st.booleans(),
)
@example(values_by_case=[{"income_tax_main_rates": 0}], oracle_on_left=False, compact=False)
@example(values_by_case=[{"income_tax_main_rates": False, "capital_gains_tax": None}], oracle_on_left=True, compact=True)
def test_legacy_binding_never_infers_a_missing_sum_member(values_by_case, oracle_on_left, compact):
    report, _ = _legacy_report(values_by_case, oracle_on_left, compact=compact)
    evidence = attest(report, oracle=ORACLE)
    assert evidence.eligible
    assert not evidence.binds(("capital_gains_tax",))
    assert not evidence.outputs_complete
    assert _score(report)[0].covered == 0
