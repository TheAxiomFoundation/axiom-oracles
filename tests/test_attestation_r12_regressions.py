"""Returned sum members only cover when their own comparison was scored."""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance.attestation import OracleTargetResolver, attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


COMPONENTS = ("ordinary_tax", "gains_tax")


def _component_report(axiom_values, oracle_values, *, independent=False, stamped=True, compact=False):
    if independent:
        mappings = [
            ProgramMapping(
                standard=f"probe:tax#{output}", description=output, category="tax",
                comparison="amount", targets={"axiom": output, "policyengine": output},
            )
            for output in COMPONENTS
        ]
    else:
        mappings = [ProgramMapping(
            standard="probe:tax#total", description="Summed tax", category="tax",
            comparison="amount", targets={"axiom": list(COMPONENTS), "policyengine": list(COMPONENTS)},
        )]
    comparisons = Comparator(mappings).compare(
        [EngineResult("axiom", "real-case", dict(zip(COMPONENTS, axiom_values)))],
        [EngineResult("policyengine", "real-case", dict(zip(COMPONENTS, oracle_values)))],
    )
    report = build_comparison_report(
        suite_name="cancellation-probe", population="synthetic", locales=set(), scope=None,
        cases=[Case(case_id="real-case", period="2026")], mappings=mappings,
        comparisons=comparisons, include_inputs=not compact,
    )
    if not stamped:
        report.pop("attestation")
    resolver = OracleTargetResolver({
        mapping.concept_id: {
            engine: frozenset([target] if isinstance(target, str) else target)
            for engine in ("axiom", "policyengine")
            if (target := mapping.target_for_engine(engine)) is not None
        }
        for mapping in mappings
    })
    universe = Universe(
        "probe", OracleIdentity("probe", "1", "US", "US", "policyengine"),
        [UniversePolicy(output, output, (output,), True, suite="cancellation-probe")
         for output in COMPONENTS],
    )
    return comparisons, report, resolver, universe


@pytest.mark.parametrize("stamped", [False, True])
def test_real_producer_sum_cancellation_cannot_certify_component_policies(stamped):
    comparisons, report, resolver, universe = _component_report(
        (100, 0), (0, 100), stamped=stamped,
    )
    aggregate_comparison = comparisons[0].comparisons[0]
    assert aggregate_comparison.left_value == aggregate_comparison.right_value == 100
    assert aggregate_comparison.matches
    assert report["summary"]["mismatch_count"] == 0
    assert {row["variable"] for row in report["observed_outputs"]} == set(COMPONENTS)

    evidence = attest(report, oracle=universe.oracle, resolver=resolver)
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert not evidence.attested_outputs
    assert board.covered == 0
    assert not any(row.covered for row in rows)
    assert not board.conformant


@pytest.mark.parametrize("stamped", [False, True])
def test_independently_compared_members_preserve_each_residual_and_prevent_conformance(stamped):
    comparisons, report, resolver, universe = _component_report(
        (100, 0), (0, 100), independent=True, stamped=stamped,
    )
    assert [row.difference for row in comparisons[0].comparisons] == [100, -100]
    assert not any(row.matches for row in comparisons[0].comparisons)
    assert report["summary"]["mismatch_count"] == 2
    assert len(report["mismatches"]) == 2
    evidence = attest(report, oracle=universe.oracle, resolver=resolver)
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert evidence.attested_outputs == frozenset(COMPONENTS)
    assert board.covered == 2
    assert all(row.covered for row in rows)
    assert board.unexplained_total > 0
    assert not board.conformant


@settings(max_examples=30, deadline=None, database=None, derandomize=True)
@example(base=0, offset=100, stamped=False)
@given(base=st.integers(-1000, 1000), offset=st.integers(-1000, 1000).filter(bool), stamped=st.booleans())
def test_offsetting_component_residuals_never_imply_component_coverage(base, offset, stamped):
    comparisons, report, resolver, universe = _component_report(
        (base + offset, base), (base, base + offset), stamped=stamped,
    )
    assert comparisons[0].comparisons[0].matches
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert board.covered == 0
    assert not any(row.covered for row in rows)
    assert not board.conformant


def _scored_sum_report():
    _, report, resolver, universe = _component_report((100, 0), (0, 100), stamped=False)
    report["cases"][0]["mismatches"] = [{
        "concept": "probe:tax#total", "variable": output,
        "left": left, "right": right, "difference": left - right,
    } for output, left, right in zip(COMPONENTS, (100, 0), (0, 100))]
    report["summary"]["mismatch_count"] = 2
    return report, resolver, universe


@pytest.mark.parametrize("contradiction", ["match-collection", "explicit-match-flag"])
def test_member_scored_verdict_must_agree_with_retained_residual(contradiction):
    report, resolver, universe = _scored_sum_report()
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert board.covered == 2
    assert all(row.covered for row in rows)
    assert not board.conformant
    members = report["cases"][0]["mismatches"]
    if contradiction == "match-collection":
        report["cases"][0]["matches"].extend(members)
        report["cases"][0]["mismatches"] = []
        report["summary"]["mismatch_count"] = 0
    else:
        for row in members:
            row["matches"] = True
    assert not attest(report, oracle=universe.oracle, resolver=resolver).attested_outputs
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


@pytest.mark.parametrize("declaration", ["engines", "engine_bindings"])
def test_partial_authoritative_binding_cannot_turn_a_summed_mapping_into_a_scalar(declaration):
    _, report, resolver, universe = _component_report(
        (100, 0), (0, 100), stamped=False, compact=True,
    )
    assert "matches" not in report["cases"][0]
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0
    if declaration == "engines":
        report["engines"] = {engine: "ordinary_tax" for engine in ("axiom", "policyengine")}
    else:
        report["engine_bindings"] = {
            engine: {"outputs": ["ordinary_tax"]} for engine in ("axiom", "policyengine")
        }
    assert not attest(report, oracle=universe.oracle, resolver=resolver).attested_outputs
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


def test_grid_member_comparison_values_must_agree_with_its_returned_member_ledgers():
    report, resolver, universe = _scored_sum_report()
    report["engines"] = {engine: ",".join(COMPONENTS) for engine in ("axiom", "policyengine")}
    case = report["cases"][0]
    case.pop("left_engine")
    case.pop("right_engine")
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 2
    case["matches"] = [dict(row, left=0, right=0, difference=0) for row in case["mismatches"]]
    case["mismatches"] = []
    report["summary"]["mismatch_count"] = 0
    assert not attest(report, oracle=universe.oracle, resolver=resolver).attested_outputs
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


def test_compact_scalar_ledger_cannot_override_a_differently_named_actual_comparison():
    _, report, resolver, universe = _component_report(
        (0, 0), (0, 0), independent=True, stamped=False, compact=True,
    )
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 2
    report["cases"][0]["matches"] = [{
        "concept": "probe:tax#ordinary_tax", "variable": "different_target",
        "left": 0, "right": 0, "difference": 0,
    }]
    assert "ordinary_tax" not in attest(report, oracle=universe.oracle, resolver=resolver).attested_outputs
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 1
