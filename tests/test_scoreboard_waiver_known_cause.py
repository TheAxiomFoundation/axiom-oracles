"""Merged scoring preserves cause assessment and retired waiver handling."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    OracleTargetResolver,
)
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.conformance.waivers import AttestationWaiver, WaiverIndex


ROOT = Path(__file__).parents[1]


def _universe():
    return Universe("tx", OracleIdentity("M", "R", "S", "TX", "euromod"), [
        UniversePolicy("tx:x", "x", ("x_s",), True, suite="sample"),
    ])


def _report(count: int, bound: bool):
    variable = "x_s" if bound else "other_s"
    engines = {"left": "euromod", "right": "axiom"}
    return {
        "suite": "sample",
        "engines": engines,
        "case_count": count,
        "summary": {
            "comparison_count": count, "match_count": 0,
            "mismatch_count": count, "error_count": 0,
        },
        "mismatches": [{"case_id": index, "concept": "tx:output",
                        "kind": "amount_difference", "left": 1, "right": 0}
                       for index in range(count)],
        "cases": [{"case_id": index, "mismatches": [{
            "concept": "tx:output", "kind": "amount_difference",
            "left": 1, "right": 0,
        }]} for index in range(count)],
        "aggregates": [{"concept": "tx:output", "comparison_count": count}],
        "observed_outputs": [{
            "case_id": index, "concept": "tx:output", "engine": engine,
            "variable": variable, "value": int(engine == "euromod"),
        } for index in range(count) for engine in ("euromod", "axiom")],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": True, "case_count": count,
            "comparison_count": count, "error_count": 0, "engines": engines,
            "outputs": [{"concept": "tx:output", "engine": "euromod",
                         "variable": variable, "comparisons": count}],
        },
    }


def _unusable_report(count: int, gate: str, defect: str):
    report = _report(count, bound=gate != "unbound")
    if gate == "unattested":
        report["attestation"]["executed"] = False
    elif gate == "unwitnessed":
        report["scope"] = {"column_exposure": {"x_s": 0}}
    if defect == "null-comparisons":
        report["summary"]["comparison_count"] = None
    elif defect == "malformed-comparisons":
        report["summary"]["comparison_count"] = "not a count"
    elif defect == "null-matches":
        report["summary"]["match_count"] = None
    else:
        report["summary"]["mismatch_count"] = 0
    return report


@given(count=st.integers(min_value=1, max_value=4),
       gate=st.sampled_from(["unattested", "unbound", "unwitnessed"]),
       defect=st.sampled_from(["null-comparisons", "malformed-comparisons",
                               "null-matches", "understated-mismatches"]))
@settings(max_examples=48, deadline=None, database=None, derandomize=True)
def test_unusable_single_report_stays_uncovered_before_numeric_assessment(count, gate, defect):
    """Rejected execution/output evidence reaches a verdict even with stale counts."""
    board, rows = score_jurisdiction(
        _universe(), [_unusable_report(count, gate, defect)], known_causes=[],
    )
    assert board.covered == 0
    assert not board.conformant
    assert not rows[0].covered
    assert rows[0].status in {"unattested", "unbound", "unwitnessed"}


@pytest.mark.parametrize("duplicate", [False, True])
def test_bound_reports_and_contested_duplicates_still_reject_invalid_counts(duplicate):
    report = _report(1, bound=not duplicate)
    report["summary"]["match_count"] = None
    reports = [report, report] if duplicate else [report]
    with pytest.raises(ValueError, match="match_count"):
        score_jurisdiction(_universe(), reports, known_causes=[])


@given(count=st.integers(min_value=1, max_value=12), bound=st.booleans())
@settings(max_examples=24, deadline=None, database=None, derandomize=True)
def test_known_cause_changes_residual_without_waiving_registered_output_pair(count, bound):
    """Causes explain returned mismatches; waiver metadata cannot supply outputs."""
    report = _report(count, bound)
    waivers = WaiverIndex([AttestationWaiver(
        "tx", "tx:x", "sample", "compared_surface_differs",
    )])
    options = {"repo_root": ROOT, "waivers": waivers,
               "resolver": OracleTargetResolver()}
    causes = [{"suite": "sample", "concept": "tx:output",
               "kind": "amount_difference", "engines": report["engines"]}]
    unexplained, before = score_jurisdiction(_universe(), [report], known_causes=[], **options)
    explained, after = score_jurisdiction(_universe(), [report], known_causes=causes, **options)
    assert explained.covered == unexplained.covered == int(bound)
    assert explained.unexplained_total == 0
    assert unexplained.unexplained_total == (count if bound else 0)
    assert explained.covered_with_waived_output_attestation == 0
    assert unexplained.covered_with_waived_output_attestation == 0
    assert explained.conformant is bound
    if bound:
        assert before[0].unexplained == count
        assert after[0].unexplained == 0
        assert before[0].status == "unexplained"
        assert after[0].status == "conformant"
    else:
        assert before[0].status == after[0].status == "unbound"


def test_scoreboard_builder_forwards_known_causes_repository_and_waivers(monkeypatch):
    """The production builder passes both sides' inputs in the same call."""
    spec = importlib.util.spec_from_file_location(
        "scoreboard_merge_inputs", ROOT / "scripts/conformance_scoreboard.py",
    )
    script = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(script)
    universe = _universe()
    reports = [_report(1, True)]
    causes = [{"suite": "sample", "concept": "tx:output", "kind": "amount_difference"}]
    waivers = WaiverIndex([AttestationWaiver(
        "tx", "tx:x", "sample", "compared_surface_differs",
    )])
    monkeypatch.setattr(script, "_load_reports", lambda: reports)
    monkeypatch.setattr(script, "load_known_causes", lambda root: causes)
    monkeypatch.setattr(script, "parse_waivers", lambda path: waivers)
    monkeypatch.setattr(script, "_universe_paths", lambda: [Path("tx.yaml")])
    monkeypatch.setattr(script, "parse_universe", lambda path: universe)
    calls = []

    def score(received_universe, received_reports, **options):
        assert received_universe is universe
        assert received_reports is reports
        assert options["known_causes"] is causes
        assert options["repo_root"] == ROOT
        assert options["waivers"] is waivers
        calls.append(options)
        return score_jurisdiction(received_universe, received_reports, **options)

    monkeypatch.setattr(script, "score_jurisdiction", score)
    document, details = script.build_scoreboard()
    assert len(calls) == 1
    assert document["jurisdictions"][0]["covered"] == 1
    assert document["jurisdictions"][0]["unexplained_total"] == 0
    assert details["tx"][0].status == "conformant"
