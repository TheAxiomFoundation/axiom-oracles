"""A runner may attest only targets observed in the compared engine results."""

import pytest

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
    axiom = EngineResult("axiom", "c1", {mapping.target_for_engine("axiom"): 100})
    oracle = EngineResult("policyengine", "c1", {"income_tax_main_rates": 100})
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    report, _, comparisons = _report(mapping, [left], [right])

    # The parent comparator behavior intentionally sums absent list targets as
    # zero. A matching sum is still not evidence that every component ran.
    assert comparisons[0].comparisons[0].matches
    assert report["summary"]["match_count"] == 1
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
    assert report["summary"]["match_count"] == 3
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
    # Exhaust all presence subsets; this repo has no property-test dependency.
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
    assert comparisons[0].comparisons[0].matches == bool(observed)
    assert {
        row["variable"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    } == set(observed)
