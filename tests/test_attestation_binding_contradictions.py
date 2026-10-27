"""A returned ledger cannot override its comparison's authoritative identity."""

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance.attestation import OracleTargetResolver, attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def _scalar_report():
    mapping = ProgramMapping(
        standard="probe:tax#scalar", description="Tax", category="tax",
        comparison="amount", targets={"axiom": "tax", "policyengine": "tax"},
    )
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", "real-case", {"tax": 0})],
        [EngineResult("policyengine", "real-case", {"tax": 0})],
    )
    report = build_comparison_report(
        suite_name="binding-probe", population="synthetic", locales=set(), scope=None,
        cases=[Case(case_id="real-case", period="2026")], mappings=[mapping],
        comparisons=comparisons,
    )
    report.pop("attestation")
    resolver = OracleTargetResolver({mapping.concept_id: {
        "axiom": frozenset({"tax"}), "policyengine": frozenset({"tax"}),
    }})
    universe = Universe(
        "probe", OracleIdentity("probe", "1", "US", "US", "policyengine"),
        [UniversePolicy("tax", "tax", ("tax",), True, suite="binding-probe")],
    )
    return report, resolver, universe


def _assert_uncovered(report, resolver, universe):
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(("tax",))
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert board.covered == 0
    assert not rows[0].covered
    assert not board.conformant


@pytest.mark.parametrize("engine", ["axiom", "policyengine", "both"])
@pytest.mark.parametrize("native_binding", [False, True])
def test_engine_heading_must_agree_with_every_recorded_scalar_binding(engine, native_binding):
    report, resolver, universe = _scalar_report()
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].conformant
    report["engines"] = {"axiom": "tax", "policyengine": "tax"}
    if native_binding:
        report["engine_bindings"] = {
            "axiom": {"output": "tax"}, "policyengine": {"outputs": ["tax"]},
        }
    for name in ("axiom", "policyengine") if engine == "both" else (engine,):
        report["engines"][name] = f"different_{name}_target"
    _assert_uncovered(report, resolver, universe)


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
@pytest.mark.parametrize("target", ["", [], None])
def test_explicit_empty_engine_target_cannot_be_replaced_by_a_positive_ledger(engine, target):
    report, resolver, universe = _scalar_report()
    report["engines"] = {"axiom": "tax", "policyengine": "tax"}
    report["engines"][engine] = target
    _assert_uncovered(report, resolver, universe)


@pytest.mark.parametrize("side", ["left", "right"])
def test_case_engine_role_cannot_contradict_the_engine_whose_ledger_is_attested(side):
    report, resolver, universe = _scalar_report()
    report["engines"] = {"axiom": "tax", "policyengine": "tax"}
    report["cases"][0][f"{side}_engine"] = "different_engine"
    _assert_uncovered(report, resolver, universe)


@pytest.mark.parametrize("location", ["matches", "mismatches", "top-mismatches"])
@pytest.mark.parametrize("flags", [{}, {"skipped": True}, {"errors": ["failed"]}, {"executed": False}])
def test_renamed_actual_comparison_cannot_leave_old_ledger_attested(location, flags):
    report, resolver, universe = _scalar_report()
    row = report["cases"][0]["matches"][0]
    row.update(variable="different_target", **flags)
    if location != "matches":
        report["cases"][0]["matches"] = []
        if location == "mismatches":
            report["cases"][0]["mismatches"] = [row]
        else:
            report["mismatches"] = [dict(row, case_id="real-case")]
    _assert_uncovered(report, resolver, universe)


@settings(max_examples=25, deadline=None, database=None, derandomize=True)
@example(target="different_target", stopped=True)
@given(target=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1).filter(lambda s: s != "tax"),
       stopped=st.booleans())
def test_comparison_relabeling_never_preserves_scalar_ledger_coverage(target, stopped):
    report, resolver, universe = _scalar_report()
    report["cases"][0]["matches"][0].update(variable=target, skipped=stopped)
    _assert_uncovered(report, resolver, universe)
