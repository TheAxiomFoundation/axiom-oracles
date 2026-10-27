"""Mapping multiplicity cannot disappear when successful cases are compacted."""

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import (
    ComparisonReportAccumulator, FULL_CASE_INPUT_LIMIT, build_comparison_report,
)
from axiom_oracles.conformance.attestation import OracleTargetResolver
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def _mapping(left, right):
    return ProgramMapping(
        standard="probe:tax#total", description="Tax", category="tax",
        comparison="amount", targets={"axiom": left, "policyengine": right},
    )


def _report(mapping, *, count=1, stamped=True, mode="default"):
    cases = [Case(case_id=index, period="2026") for index in range(count)]
    # The repeated Axiom term sums to the scalar oracle value even though
    # the independently returned tax values differ.
    left = {"tax": 50, "surtax": 50}
    right = {"tax": 100 if mapping.target_for_engine("axiom") == ["tax", "tax"] else 50,
             "surtax": 50}
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", index, left) for index in range(count)],
        [EngineResult("policyengine", index, right) for index in range(count)],
    )
    options = dict(suite_name="mapping-shapes", population="synthetic", locales=set(),
                   scope=None, mappings=[mapping])
    if mode == "no-cases":
        accumulator = ComparisonReportAccumulator(**options)
        accumulator.add_batch(cases, comparisons)
        report = accumulator.to_dict(include_cases=False)
    else:
        report = build_comparison_report(
            **options, cases=cases, comparisons=comparisons,
            include_inputs=False if mode == "compact" else None,
        )
    if not stamped:
        report.pop("attestation")
    resolver = OracleTargetResolver({mapping.concept_id: {
        engine: frozenset([target] if isinstance(target, str) else target)
        for engine in ("axiom", "policyengine")
        if (target := mapping.target_for_engine(engine)) is not None
    }})
    universe = Universe(
        "probe", OracleIdentity("probe", "1", "US", "US", "policyengine"),
        [UniversePolicy("tax", "tax", ("tax",), True, suite="mapping-shapes")],
    )
    return report, score_jurisdiction(universe, [report], resolver=resolver)[0]


@pytest.mark.parametrize("stamped", [False, True])
@pytest.mark.parametrize("mode,count", [
    ("default", FULL_CASE_INPUT_LIMIT + 1), ("compact", 1), ("no-cases", 1),
])
def test_repeated_sum_never_certifies_its_independent_scalar(stamped, mode, count):
    try:
        mapping = _mapping(["tax", "tax"], "tax")
    except ValueError as error:
        assert "repeated target" in str(error)
        return  # Rejecting the mapping is also a valid producer contract.
    report, board = _report(mapping, count=count, stamped=stamped, mode=mode)
    assert report["summary"]["comparison_count"] == count
    assert report["summary"]["mismatch_count"] == 0
    assert board.covered == 0
    assert not board.conformant


@pytest.mark.parametrize("stamped", [False, True])
@pytest.mark.parametrize("mode,count", [
    ("default", FULL_CASE_INPUT_LIMIT + 1), ("compact", 1), ("no-cases", 1),
])
def test_valid_scalar_survives_each_compaction_mode(stamped, mode, count):
    report, board = _report(_mapping("tax", "tax"), count=count, stamped=stamped, mode=mode)
    assert report["summary"]["comparison_count"] == count
    assert board.covered == 1
    assert board.conformant


@pytest.mark.parametrize("engine,shape", [
    (engine, shape) for engine in ("axiom", "policyengine", "euromod")
    for shape in ("list", "name", "variable", "legacy")
    if shape != "legacy" or engine != "euromod"
])
def test_mapping_validation_rejects_repeated_terms_in_each_supported_shape(engine, shape):
    terms = ["tax", "tax"]
    options = {}
    if shape == "legacy":
        options["axiom_output" if engine == "axiom" else "policyengine_variable"] = terms
    else:
        options["targets"] = {engine: terms if shape == "list" else {shape: terms}}
    problem = None
    try:
        ProgramMapping(standard="probe:tax#total", description="Tax", category="tax", **options)
    except ValueError as error:
        problem = str(error)
    assert problem is not None, "Repeated mapping terms passed validation"
    assert "repeated target" in problem


target_shapes = st.one_of(st.sampled_from(["tax", "surtax"]),
                          st.lists(st.sampled_from(["tax", "surtax"]), min_size=1, max_size=3))


@settings(max_examples=60, deadline=None, database=None, derandomize=True)
@example(left=["tax", "tax"], right="tax", stamped=False, mode="no-cases")
@example(left="tax", right="tax", stamped=True, mode="compact")
@example(left=["tax", "surtax"], right=["tax", "surtax"], stamped=False, mode="compact")
@given(left=target_shapes, right=target_shapes, stamped=st.booleans(),
       mode=st.sampled_from(["default", "compact", "no-cases"]))
def test_mapping_shape_coverage_matches_independent_predicate(left, right, stamped, mode):
    # This predicate reads the generated source shape, never the attestation's
    # target sets. A raw member of any multi-term sum has no scored comparison.
    terms = [[target] if isinstance(target, str) else target for target in (left, right)]
    repeated = any(len(values) != len(set(values)) for values in terms)
    expected_coverage = int(not repeated and all(len(values) == 1 for values in terms)
                            and terms[1] == ["tax"])
    try:
        mapping = _mapping(left, right)
    except ValueError as error:
        assert repeated
        assert "repeated target" in str(error)
        return
    assert not repeated, "Repeated terms must be rejected before comparison"
    _, board = _report(mapping, stamped=stamped, mode=mode)
    assert board.covered == expected_coverage
