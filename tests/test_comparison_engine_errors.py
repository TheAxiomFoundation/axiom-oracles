"""Engine errors cannot become agreements, including streamed case evidence."""

import importlib.util
import json
from pathlib import Path

import pytest

from axiom_oracles.comparison.comparator import (
    Comparator,
    HouseholdComparison,
    VariableComparison,
)
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import (
    ComparisonReportAccumulator,
    build_comparison_report,
    engine_error_signature,
)
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


MAPPING = ProgramMapping(
    standard="us:test#income_tax",
    description="Income tax",
    category="tax",
    comparison="amount",
    targets={"policyengine": "tax", "taxsim": "tax"},
)


def _report(cases: list[Case], comparisons: list[HouseholdComparison]) -> dict:
    return build_comparison_report(
        suite_name="error-fixture",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=cases,
        mappings=[MAPPING],
        comparisons=comparisons,
    )


@pytest.mark.parametrize("side", ("left", "right", "both"))
def test_direct_comparison_errors_never_count_as_matches(side: str) -> None:
    left_errors = ("auxiliary output failed",) if side in ("left", "both") else ()
    right_errors = ("taxsim-crash:SIGFPE",) if side in ("right", "both") else ()
    comparison = HouseholdComparison(
        household_id="case-1",
        left_engine="policyengine",
        right_engine="taxsim",
        comparisons=[VariableComparison(MAPPING.standard, 100, 100, True, 0)],
        left_errors=left_errors,
        right_errors=right_errors,
    )
    assert comparison.match_count == 0 and comparison.mismatch_count == 1
    assert comparison.match_rate == 0
    report = _report([Case(case_id="case-1", period="2025")], [comparison])
    assert report["summary"]["match_count"] == 0
    assert report["summary"]["engine_error_count"] == 1
    assert report["summary"]["weighted"]["match_rate"] == 0
    assert report["aggregates"][0]["match_rate"] == 0
    assert report["cases"][0]["matches"] == []
    nested = report["cases"][0]["mismatches"][0]
    top = report["mismatches"][0]
    assert nested["kind"] == top["kind"] == "engine_error"
    assert nested["error"] == top["error"]
    if side == "both":
        assert top["error"]["engine"] == "policyengine"
        assert top["error"]["other_side"]["engine"] == "taxsim"
        assert top["error"]["other_side"]["signature"] == "SIGFPE"


def test_compare_mapping_also_rejects_partial_agreements() -> None:
    comparison = Comparator([MAPPING]).compare_mapping(
        MAPPING,
        EngineResult("policyengine", "case-1", {"tax": 100}),
        EngineResult("taxsim", "case-1", {"tax": 100}, errors=("failed",)),
    )
    assert comparison.matches is False
    assert comparison.difference == 0


@pytest.mark.parametrize("facts", ({}, {"state": None, "year": 2025, "flag": False}))
def test_facts_and_failure_detail_reach_streamed_case_rows(tmp_path: Path, facts: dict) -> None:
    accumulator = ComparisonReportAccumulator(
        suite_name="error-fixture",
        population="synthetic",
        locales=set(),
        scope=None,
        mappings=[MAPPING],
        case_rows_path=tmp_path / "cases.jsonl",
        include_inputs=True,
    )
    comparisons = Comparator([MAPPING]).compare(
        [EngineResult("policyengine", "case-1", {"tax": 100})],
        [EngineResult(
            "taxsim", "case-1", {}, errors=("taxsim-crash:rc=9",),
            raw={"taxsim_error": {
                "signature": "rc=9", "binary_sha256": "a" * 64,
                "returncode": 9, "stderr_tail": "failed",
            }},
        )],
    )
    accumulator.add_batch(
        [Case(case_id="case-1", period="2025", metadata={"selector_facts": facts})],
        comparisons,
    )
    report = accumulator.to_dict()
    top = report["mismatches"][0]
    nested = json.loads((tmp_path / "cases.jsonl").read_text())["mismatches"][0]
    assert top["facts"] == nested["facts"] == facts
    assert top["facts"] is not facts
    assert top["error"] == nested["error"]
    assert nested["error"]["binary_sha256"] == "a" * 64
    assert nested["error"]["signature"] == "rc=9"
    assert nested["error"]["returncode"] == 9


def test_successful_reports_without_selector_facts_keep_their_shape() -> None:
    comparisons = Comparator([MAPPING]).compare(
        [EngineResult("policyengine", "case-1", {"tax": 100})],
        [EngineResult("taxsim", "case-1", {"tax": 200})],
    )
    report = _report([Case(case_id="case-1", period="2025")], comparisons)
    assert "engine_error_count" not in report["summary"]
    for row in [report["mismatches"][0], report["cases"][0]["mismatches"][0]]:
        assert row["kind"] == "amount_difference"
        assert "facts" not in row and "error" not in row


def test_crash_signature_accepts_hyphenated_engine_names() -> None:
    assert engine_error_signature(["policyengine-taxsim-crash:SIGFPE"]) == "SIGFPE"
    assert engine_error_signature(["taxsim-crash:  "]) == "unclassified"


@pytest.mark.parametrize("error_first", (False, True))
def test_actual_shards_conserve_error_counts(error_first: bool) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "merge_shard_reports.py"
    spec = importlib.util.spec_from_file_location("merge_engine_error_shards", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reports = []
    for index, errors in enumerate(((), ("taxsim-crash:SIGFPE",), ("generic failure",))):
        comparisons = Comparator([MAPPING]).compare(
            [EngineResult("policyengine", index, {"tax": 100})],
            [EngineResult("taxsim", index, {"tax": 100}, errors=errors)],
        )
        reports.append(_report([Case(case_id=index, period="2025")], comparisons))
    if error_first:
        reports.reverse()
    merged = module.merge(reports)
    assert merged["summary"]["engine_error_count"] == 2
    assert merged["summary"]["match_count"] == 1
    assert merged["summary"]["mismatch_count"] == 2
    assert merged["summary"]["comparison_count"] == 3
    assert sum(row["kind"] == "engine_error" for row in merged["mismatches"]) == 2
    assert merged["summary"]["errors_by_engine"] == {"taxsim": 2}
