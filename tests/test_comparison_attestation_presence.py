"""A runner may attest only targets observed in the compared engine results."""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping, load_program_mappings
from axiom_oracles.comparison.report import (
    ComparisonReportAccumulator,
    build_comparison_report,
)
from axiom_oracles.conformance.attestation import OracleTargetResolver
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def _report(mapping, left_results, right_results):
    cases = [Case(case_id=result.household_id, period="2026") for result in left_results]
    comparisons = Comparator([mapping]).compare(left_results, right_results)
    report = build_comparison_report(
        suite_name="probe",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=cases,
        mappings=[mapping],
        comparisons=comparisons,
    )
    return report, cases, comparisons


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_partial_list_target_does_not_cover_absent_output(oracle_on_left):
    # Adapt the review's runner_repro.py using the committed FIIT mapping.
    mapping = next(
        mapping
        for mapping in load_program_mappings()
        if mapping.target_for_engine("policyengine")
        == ["income_tax_main_rates", "capital_gains_tax"]
    )
    axiom_target = mapping.target_for_engine("axiom")
    axiom_values = (
        {target: 100 if index == 0 else 0 for index, target in enumerate(axiom_target)}
        if isinstance(axiom_target, list)
        else {axiom_target: 100}
    )
    axiom = EngineResult("axiom", "c1", axiom_values)
    oracle = EngineResult("policyengine", "c1", {"income_tax_main_rates": 100})
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report, _, comparisons = _report(mapping, [left], [right])

    # Main requires every sum component. Output evidence still records only
    # the targets that actually ran, including for an incomplete comparison.
    comparison = comparisons[0].comparisons[0]
    assert not comparison.matches
    assert (comparison.left_value if oracle_on_left else comparison.right_value) is None
    assert report["summary"]["match_count"] == 0
    assert report["summary"]["mismatch_count"] == 1
    oracle_outputs = {
        row["variable"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    }
    assert oracle_outputs == {"income_tax_main_rates"}

    universe = Universe(
        "us-pe",
        OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine"),
        [
            UniversePolicy(
                id="us-pe:capital_gains_tax",
                oracle_policy_name="capital_gains_tax",
                output_vars=("capital_gains_tax",),
                in_scope=True,
                suite="probe",
            )
        ],
    )
    board, rows = score_jurisdiction(universe, [report], resolver=OracleTargetResolver())
    assert board.covered == 0
    assert not board.conformant
    assert rows[0].attested_outputs == []


def test_output_counts_track_presence_across_streaming_batches():
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": ["ordinary_tax", "gains_tax"]},
    )
    report, cases, comparisons = _report(
        mapping,
        [EngineResult("axiom", index, {"tax": 100}) for index in range(3)],
        [
            EngineResult("policyengine", 0, {"ordinary_tax": 100}),
            EngineResult("policyengine", 1, {"ordinary_tax": 100, "gains_tax": 0}),
            EngineResult("policyengine", 2, {"gains_tax": 100}),
        ],
    )
    accumulator = ComparisonReportAccumulator(
        suite_name="probe",
        population="synthetic",
        locales=set(),
        scope=None,
        mappings=[mapping],
        include_inputs=True,
    )
    accumulator.add_batch(cases[:1], comparisons[:1])
    accumulator.add_batch(cases[1:], comparisons[1:])
    assert accumulator.to_dict() == report
    assert report["summary"]["match_count"] == 1
    assert report["summary"]["mismatch_count"] == 2
    counts = {
        (row["engine"], row["variable"]): row["comparisons"]
        for row in report["attestation"]["outputs"]
    }
    # A real zero-valued target counts; an absent target never does.
    assert counts == {
        ("axiom", "tax"): 3,
        ("policyengine", "ordinary_tax"): 2,
        ("policyengine", "gains_tax"): 2,
    }


@pytest.mark.parametrize("missing_engine", ["axiom", "policyengine"])
def test_absent_scalar_target_has_no_output_stamp(missing_engine):
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": "tax"},
    )
    report, _, comparisons = _report(
        mapping,
        [EngineResult("axiom", "c1", {} if missing_engine == "axiom" else {"tax": 0})],
        [
            EngineResult(
                "policyengine",
                "c1",
                {} if missing_engine == "policyengine" else {"tax": 0},
            )
        ],
    )
    assert not comparisons[0].comparisons[0].matches
    assert report["summary"]["mismatch_count"] == 1
    assert all(row["engine"] != missing_engine for row in report["attestation"]["outputs"])


@pytest.mark.parametrize("presence_mask", range(8))
def test_stamp_targets_equal_observed_subset_of_list(presence_mask):
    # Exhaust all presence subsets as a compact deterministic check.
    targets = ["ordinary_tax", "gains_tax", "surtax"]
    observed = {
        target: 0 for index, target in enumerate(targets) if presence_mask & (1 << index)
    }
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": targets},
    )
    report, _, comparisons = _report(
        mapping,
        [EngineResult("axiom", "c1", {"tax": 0})],
        [EngineResult("policyengine", "c1", observed)],
    )
    comparison = comparisons[0].comparisons[0]
    complete = len(observed) == len(targets)
    assert comparison.matches == complete
    assert comparison.right_value == (0 if complete else None)
    assert {
        row["variable"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    } == set(observed)


def _score_registered_output(report, output):
    universe = Universe(
        "us-pe",
        OracleIdentity("policyengine-us", "1.767.3", "us", "US", "policyengine"),
        [
            UniversePolicy(
                id=f"us-pe:{output}",
                oracle_policy_name=output,
                output_vars=(output,),
                in_scope=True,
                suite="probe",
            )
        ],
    )
    return score_jurisdiction(universe, [report], resolver=OracleTargetResolver())


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_null_scalar_target_has_no_output_stamp(oracle_on_left):
    # Reuse the review's null probe with the oracle on either side.
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": "tax"},
    )
    axiom = EngineResult("axiom", "c1", {"tax": 0})
    oracle = EngineResult("policyengine", "c1", {"tax": None})
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report, _, comparisons = _report(mapping, [left], [right])
    comparison = comparisons[0].comparisons[0]
    assert not comparison.matches
    assert (comparison.left_value if oracle_on_left else comparison.right_value) is None
    assert all(
        row["engine"] != "policyengine" for row in report["attestation"]["outputs"]
    )

    # Explaining a missing comparison cannot turn its null value into evidence.
    report["summary"]["dispositioned"] = {
        "unexplained_count": 0,
        "counts": {"upstream_engine_gap": 1},
    }
    board, rows = _score_registered_output(report, "tax")
    assert board.covered == 0
    assert not board.conformant
    assert rows[0].status == "unbound"
    assert rows[0].attested_outputs == []


@pytest.mark.parametrize("oracle_on_left", [False, True])
def test_null_list_component_has_no_output_stamp(oracle_on_left):
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": ["ordinary_tax", "gains_tax"]},
    )
    axiom = EngineResult("axiom", "c1", {"tax": 0})
    oracle = EngineResult(
        "policyengine", "c1", {"ordinary_tax": 0, "gains_tax": None}
    )
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report, _, comparisons = _report(mapping, [left], [right])
    comparison = comparisons[0].comparisons[0]
    assert not comparison.matches
    assert (comparison.left_value if oracle_on_left else comparison.right_value) is None
    assert {
        row["variable"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    } == {"ordinary_tax"}
    board, rows = _score_registered_output(report, "gains_tax")
    assert board.covered == 0
    assert not board.conformant
    assert rows[0].attested_outputs == []


@pytest.mark.parametrize("oracle_on_left", [False, True])
@pytest.mark.parametrize("value", [0, False])
def test_zero_and_false_scalar_targets_remain_observed(oracle_on_left, value):
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": "tax"},
    )
    axiom = EngineResult("axiom", "c1", {"tax": 0})
    oracle = EngineResult("policyengine", "c1", {"tax": value})
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report, _, comparisons = _report(mapping, [left], [right])
    assert comparisons[0].comparisons[0].matches
    assert {
        row["variable"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    } == {"tax"}
    board, _ = _score_registered_output(report, "tax")
    assert board.covered == 1
    assert board.conformant


@settings(max_examples=50, database=None, deadline=None, derandomize=True)
@given(
    values_by_case=st.lists(
        st.dictionaries(
            st.sampled_from(["ordinary_tax", "gains_tax", "surtax"]),
            st.none() | st.booleans() | st.integers(min_value=-100, max_value=100),
        ),
        min_size=1,
        max_size=5,
    ),
    oracle_on_left=st.booleans(),
)
@example(values_by_case=[{"ordinary_tax": 0, "gains_tax": None}], oracle_on_left=False)
@example(values_by_case=[{"ordinary_tax": False, "gains_tax": None}], oracle_on_left=True)
def test_stamp_counts_equal_nonnull_output_evidence(values_by_case, oracle_on_left):
    targets = ["ordinary_tax", "gains_tax", "surtax"]
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": targets},
    )
    axiom = [
        EngineResult("axiom", index, {"tax": 0})
        for index in range(len(values_by_case))
    ]
    oracle = [
        EngineResult("policyengine", index, values)
        for index, values in enumerate(values_by_case)
    ]
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report, cases, comparisons = _report(mapping, left, right)
    expected_counts = {
        target: sum(values.get(target) is not None for values in values_by_case)
        for target in targets
    }
    assert {
        row["variable"]: row["comparisons"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    } == {target: count for target, count in expected_counts.items() if count}
    for values, item in zip(values_by_case, comparisons):
        comparison = item.comparisons[0]
        observed = comparison.left_variables if oracle_on_left else comparison.right_variables
        assert set(observed) == {
            target for target in targets if values.get(target) is not None
        }

    accumulator = ComparisonReportAccumulator(
        suite_name="probe",
        population="synthetic",
        locales=set(),
        scope=None,
        mappings=[mapping],
        include_inputs=True,
    )
    for case, comparison in zip(cases, comparisons):
        accumulator.add_batch([case], [comparison])
    assert accumulator.to_dict() == report
