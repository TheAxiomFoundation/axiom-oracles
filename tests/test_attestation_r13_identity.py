"""Retained comparisons and declarations must reconcile with output ledgers."""

from functools import lru_cache
import importlib.util
from pathlib import Path

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges.tax_populace import SURFACE_OUTPUTS, compare_outputs
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance.attestation import OracleTargetResolver, attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def _report(*, summed=False, compact=False, stamped=False, value=0):
    targets = ["ordinary_tax", "gains_tax"] if summed else "tax"
    mapping = ProgramMapping(
        standard="probe:tax#identity", description="Tax", category="tax",
        comparison="amount", targets={engine: targets for engine in ("axiom", "policyengine")},
    )
    values = {name: value for name in targets} if summed else {targets: value}
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", "real-case", values)],
        [EngineResult("policyengine", "real-case", values)],
    )
    report = build_comparison_report(
        suite_name="identity-probe", population="synthetic", locales=set(), scope=None,
        cases=[Case(case_id="real-case", period="2026")], mappings=[mapping],
        comparisons=comparisons, include_inputs=not compact,
    )
    if not stamped:
        report.pop("attestation")
    names = frozenset(targets if summed else [targets])
    resolver = OracleTargetResolver({mapping.concept_id: {
        engine: names for engine in ("axiom", "policyengine")
    }})
    universe = Universe(
        "probe", OracleIdentity("probe", "1", "US", "US", "policyengine"),
        [UniversePolicy(name, name, (name,), True, suite="identity-probe") for name in sorted(names)],
    )
    return report, resolver, universe


def _assert_coverage(report, resolver, universe, expected):
    evidence = attest(report, oracle=universe.oracle, resolver=resolver)
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert bool(evidence.attested_outputs) is expected
    assert board.covered == (len(universe.policies) if expected else 0)
    assert all(row.covered is expected for row in rows)
    assert board.conformant is expected


@pytest.mark.parametrize("stamped", [False, True])
@pytest.mark.parametrize("location", ["matches", "mismatches", "top-mismatches"])
@pytest.mark.parametrize("flags", [{}, {"errors": ["failed"]}, {"skipped": True}, {"executed": False}])
def test_both_comparison_identifiers_must_reconcile_with_original_ledger(stamped, location, flags):
    report, resolver, universe = _report(stamped=stamped)
    row = report["cases"][0]["matches"][0]
    row.update(concept="different:concept", variable="different_target", **flags)
    if location != "matches":
        report["cases"][0]["matches"] = []
        if location == "mismatches":
            report["cases"][0]["mismatches"] = [row]
        else:
            report["mismatches"] = [dict(row, case_id="real-case")]
    _assert_coverage(report, resolver, universe, False)


def test_complete_comparisons_cannot_leave_an_old_ledger_after_a_known_concept_rename():
    report, resolver, universe = _report()
    report["aggregates"].append({"concept": "different:concept", "comparison_count": 1})
    report["output_bindings"]["different:concept"] = {
        engine: "different_target" for engine in ("axiom", "policyengine")
    }
    report["cases"][0]["matches"][0].update(concept="different:concept", variable="different_target")
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(("tax",))
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert board.covered == 0
    assert not rows[0].covered
    assert not board.conformant


@pytest.mark.parametrize("location", ["case", "top-mismatches"])
@pytest.mark.parametrize("case_id", ["missing", None, False])
@pytest.mark.parametrize("flags", [{}, {"errors": ["failed"]}, {"skipped": True}, {"executed": False}])
def test_retained_comparison_cannot_hide_behind_an_absent_or_invalid_case_identity(location, case_id, flags):
    report, resolver, universe = _report()
    row = report["cases"][0]["matches"][0]
    row.update(flags)
    if location == "case":
        if case_id == "missing":
            report["cases"][0].pop("case_id")
        else:
            report["cases"][0]["case_id"] = case_id
    else:
        report["cases"][0]["matches"] = []
        report["mismatches"] = [dict(row)]
        if case_id != "missing":
            report["mismatches"][0]["case_id"] = case_id
    _assert_coverage(report, resolver, universe, False)


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
@pytest.mark.parametrize("declaration", ["engines", "engine_bindings"])
def test_foreign_top_level_concept_cannot_mask_a_conflicting_engine_target(engine, declaration):
    report, resolver, universe = _report()
    report["concept"] = "different:concept"
    if declaration == "engines":
        report["engines"] = {"axiom": "tax", "policyengine": "tax"}
        report["engines"][engine] = "different_target"
    else:
        report["engine_bindings"] = {
            name: {"output": "different_target" if name == engine else "tax"}
            for name in ("axiom", "policyengine")
        }
    _assert_coverage(report, resolver, universe, False)


@pytest.mark.parametrize("stamped", [False, True])
def test_compact_sum_primary_binding_cannot_discard_an_unscored_component(stamped):
    report, resolver, universe = _report(summed=True, compact=True, stamped=stamped)
    assert "matches" not in report["cases"][0]
    report["output_bindings"]["probe:tax#identity"] = {
        engine: "ordinary_tax" for engine in ("axiom", "policyengine")
    }
    _assert_coverage(report, resolver, universe, False)


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("stamped", [False, True])
@pytest.mark.parametrize("value", [0, False])
def test_reconciled_scalar_zero_and_false_keep_coverage(compact, stamped, value):
    report, resolver, universe = _report(compact=compact, stamped=stamped, value=value)
    _assert_coverage(report, resolver, universe, True)


@settings(max_examples=30, deadline=None, database=None, derandomize=True)
@example(concept="different:concept", variable="different_target", stopped=False)
@example(concept="probe:tax#identity", variable=None, stopped=False)
@given(concept=st.sampled_from(("probe:tax#identity", "different:concept", None)),
       variable=st.sampled_from(("tax", "different_target", None)), stopped=st.booleans())
def test_scalar_coverage_requires_a_reconciled_executed_comparison_identity(concept, variable, stopped):
    report, resolver, universe = _report()
    report["cases"][0]["matches"][0].update(concept=concept, variable=variable, skipped=stopped)
    # The expected decision depends only on this test's original scalar contract.
    expected = concept == "probe:tax#identity" and variable in (None, "tax") and not stopped
    _assert_coverage(report, resolver, universe, expected)


class _Frame:
    def __init__(self, rows):
        self.iloc = rows

    def reset_index(self, **_kwargs):
        return self


@lru_cache(maxsize=1)
def _adapter():
    spec = importlib.util.spec_from_file_location(
        "r13_identity_runner", Path(__file__).parents[1] / "scripts/run_comparison.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._adapt_tax_ecps_to_v2


def _native_report():
    spec = next(iter(SURFACE_OUTPUTS["employee-medicare"].values()))
    raw = compare_outputs(
        pe_data={"tax_units": _Frame([{}]), "persons": _Frame([{spec["pe"]: 0}]),
                 "tax_unit_ids": [1], "person_ids": [1]},
        axiom_outputs_by_surface={"employee-medicare": [{
            "outputs": {spec["axiom"]: {"kind": "quantity", "value": {"value": 0}}},
        }]},
        tolerance=0, relative_tolerance=0,
    ).to_json()
    report = _adapter()(raw, {}, suite="fiit-ecps")
    universe = Universe(
        "probe", OracleIdentity("probe", "1", "US", "US", "policyengine"),
        [UniversePolicy(spec["pe"], spec["pe"], (spec["pe"],), True, suite="fiit-ecps")],
    )
    return report, OracleTargetResolver(), universe, spec


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
@pytest.mark.parametrize("target", ["", [], None])
@pytest.mark.parametrize("stamped", [False, True])
def test_native_fiit_explicit_empty_engine_target_is_a_contradiction(engine, target, stamped):
    report, resolver, universe, spec = _native_report()
    if not stamped:
        report.pop("attestation")
    report["engines"] = {"axiom": spec["axiom"], "policyengine": spec["pe"]}
    report["engines"][engine] = target
    if stamped:
        report["attestation"]["engines"] = dict(report["engines"])
    _assert_coverage(report, resolver, universe, False)


@pytest.mark.parametrize("headings", [False, True])
def test_native_fiit_missing_or_reconciled_headings_preserve_zero_coverage(headings):
    report, resolver, universe, spec = _native_report()
    if headings:
        report["engines"] = {"axiom": spec["axiom"], "policyengine": spec["pe"]}
        report["attestation"]["engines"] = dict(report["engines"])
    _assert_coverage(report, resolver, universe, True)


def _disposition_metadata_report():
    report, resolver, universe = _report()
    report["summary"]["dispositioned"] = {
        "unexplained_count": 0, "counts": {"upstream_engine_gap": 1},
    }
    report["mismatches"] = [{"disposition": {
        "disposition": "upstream_engine_gap",
        "linked_issue": "https://github.com/TheAxiomFoundation/rulespec-uk/issues/9",
    }}]
    return report, resolver, universe


def test_disposition_only_metadata_preserves_coverage_and_open_issue_attribution():
    report, resolver, universe = _disposition_metadata_report()
    assert attest(report, oracle=universe.oracle, resolver=resolver).binds(("tax",))
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert board.covered == 1
    assert rows[0].covered
    assert board.axiom_attributed_open == 1
    assert board.oracle_attributed == 1
    assert not board.conformant


@pytest.mark.parametrize("flags", [
    {"errors": ["failed"]}, {"error": "failed"}, {"skipped": True},
    {"skip_reason": "stopped"}, {"executed": False}, {"missing": True},
])
def test_disposition_only_metadata_cannot_hide_a_retained_execution_stop(flags):
    report, resolver, universe = _disposition_metadata_report()
    report["mismatches"][0].update(flags)
    _assert_coverage(report, resolver, universe, False)
