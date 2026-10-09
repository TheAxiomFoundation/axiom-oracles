"""Invariants that must survive the execution-attestation merge with main."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    OracleTargetResolver,
)
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction


PROPERTY_SETTINGS = settings(max_examples=50, deadline=None, derandomize=True)


def _policy(name: str, *, in_scope: bool = True) -> UniversePolicy:
    return UniversePolicy(
        id=f"tx:{name}",
        oracle_policy_name=name,
        output_vars=("x_s" if in_scope else "z_s",),
        in_scope=in_scope,
        exclusion_reason=None if in_scope else "technical",
        suite="shared" if in_scope else None,
    )


def _universe(policies: list[UniversePolicy]) -> Universe:
    return Universe(
        jurisdiction="tx",
        oracle=OracleIdentity("M", "R", "S", "TX", "euromod"),
        policies=policies,
    )


def _report(*, executed: bool = True, bound: bool = True, count: int = 1) -> dict:
    variable = "x_s" if bound else "other_s"
    engines = {"left": "euromod", "right": "axiom"}
    return {
        "suite": "shared",
        "engines": engines,
        "case_count": count,
        "summary": {
            "comparison_count": count,
            "match_count": count,
            "mismatch_count": 0,
            "error_count": 0,
        },
        "aggregates": [{"concept": "tx:output", "comparison_count": count}],
        "observed_outputs": [{
            "case_id": index, "concept": "tx:output", "engine": "euromod",
            "variable": variable, "value": 0,
        } for index in range(count)],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": executed,
            "case_count": count,
            "comparison_count": count,
            "error_count": 0,
            "engines": engines,
            "outputs": [{
                "concept": "tx:output",
                "engine": "euromod",
                "variable": variable,
                "comparisons": count,
            }],
        },
    }


@PROPERTY_SETTINGS
@given(
    executed=st.booleans(),
    bound=st.booleans(),
    exposure=st.integers(min_value=0, max_value=100),
    count=st.integers(min_value=1, max_value=100),
)
@example(executed=True, bound=True, exposure=0, count=1)
@example(executed=False, bound=True, exposure=1, count=1)
@example(executed=True, bound=False, exposure=1, count=1)
def test_coverage_requires_execution_output_binding_and_positive_exposure(
    executed: bool, bound: bool, exposure: int, count: int,
):
    """Each coverage gate is necessary even when the other two gates pass."""
    report = _report(executed=executed, bound=bound, count=count)
    report["scope"] = {"column_exposure": {"x_s": exposure}}
    board, scores = score_jurisdiction(
        _universe([_policy("a")]), [report], resolver=OracleTargetResolver()
    )
    expected = executed and bound and exposure > 0
    assert board.covered == int(expected)
    assert board.conformant is expected
    assert scores[0].covered is expected
    assert board.covered_with_waived_output_attestation == 0
    if executed and exposure == 0:
        assert scores[0].status == "unwitnessed"
        assert board.unwitnessed_policies == ["a"]


@PROPERTY_SETTINGS
@given(
    exposure=st.integers(min_value=1, max_value=100),
    positive_first=st.booleans(),
    positive_executed=st.booleans(),
)
def test_exclusion_tripwire_scans_every_report_independent_of_order_or_attestation(
    exposure: int, positive_first: bool, positive_executed: bool,
):
    """A duplicate or unattested report cannot hide an exposed excluded output."""
    dormant = _report()
    dormant["scope"] = {"column_exposure": {"z_s": 0}}
    positive = _report(executed=positive_executed)
    positive["scope"] = {"column_exposure": {"z_s": exposure}}
    reports = [positive, dormant] if positive_first else [dormant, positive]
    board, scores = score_jurisdiction(
        _universe([_policy("excluded", in_scope=False)]),
        reports,
        resolver=OracleTargetResolver(),
    )
    assert board.invalid_exclusions == ["excluded"]
    assert board.conformant is False
    assert scores[0].status == "excluded:INVALID-nonzero-exposure"


@PROPERTY_SETTINGS
@given(
    policy_count=st.integers(min_value=1, max_value=10),
    pre_domain=st.integers(min_value=0, max_value=100),
    clipped=st.integers(min_value=0, max_value=100),
    record_count=st.integers(min_value=0, max_value=10),
    executed=st.booleans(),
)
def test_temporal_debt_counts_each_covered_report_once(
    policy_count: int, pre_domain: int, clipped: int,
    record_count: int, executed: bool,
):
    """Shared reports contribute debt once; unattested reports contribute none."""
    report = _report(executed=executed)
    report["scope"] = {
        "column_exposure": {"x_s": 1},
        "temporal_debt": {
            "pre_domain_intervals": pre_domain,
            "straddle_clipped_intervals": clipped,
            "records": [{"debt_id": str(i)} for i in range(record_count)],
        },
    }
    board, _ = score_jurisdiction(
        _universe([_policy(str(i)) for i in range(policy_count)]),
        [report],
        resolver=OracleTargetResolver(),
    )
    assert board.covered == (policy_count if executed else 0)
    assert board.temporal_debt == ({
        "pre_domain_intervals": pre_domain,
        "straddle_clipped_intervals": clipped,
        "addressable_records": record_count,
    } if executed else None)


def test_scoreboard_discovers_universes_without_parsing_any_control_file(tmp_path):
    """Main's ratchets and the PR's waiver file all remain outside the universe."""
    script_path = Path(__file__).parents[1] / "scripts" / "conformance_scoreboard.py"
    spec = importlib.util.spec_from_file_location("conformance_merge_script", script_path)
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    script.CONFORMANCE_DIR = tmp_path
    for stem in (
        "uk", "us-pe", "ratchet", "unexplained-ratchet",
        "pe-axiom-standard", "attestation_waivers",
    ):
        (tmp_path / f"{stem}.yaml").write_text("")
    assert [path.stem for path in script._universe_paths()] == ["uk", "us-pe"]
