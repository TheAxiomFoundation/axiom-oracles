import json

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import (
    ComparisonReportAccumulator,
    build_comparison_report,
)
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


def test_streaming_report_matches_in_memory_report(tmp_path) -> None:
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        tolerance=5,
        targets={"axiom": "tax", "policyengine": "tax"},
    )
    cases = [
        Case(
            case_id="case-1",
            period="2026",
            metadata={"household_weight": 2, "scenario": "single"},
        ),
        Case(
            case_id="case-2",
            period="2026",
            metadata={"household_weight": 8, "scenario": "married"},
        ),
    ]
    comparisons = Comparator([mapping]).compare(
        [
            EngineResult("axiom", "case-1", {"tax": 100}),
            EngineResult("axiom", "case-2", {"tax": 200}),
        ],
        [
            EngineResult("policyengine", "case-1", {"tax": 100}),
            EngineResult("policyengine", "case-2", {"tax": 212}),
        ],
    )
    expected = build_comparison_report(
        suite_name="tax",
        population="enhanced-cps",
        locales={"US"},
        scope=None,
        cases=cases,
        mappings=[mapping],
        comparisons=comparisons,
    )

    case_rows_path = tmp_path / "cases.jsonl"
    accumulator = ComparisonReportAccumulator(
        suite_name="tax",
        population="enhanced-cps",
        locales={"US"},
        scope=None,
        mappings=[mapping],
        case_rows_path=case_rows_path,
    )
    accumulator.add_batch(cases[:1], comparisons[:1])
    accumulator.add_batch(cases[1:], comparisons[1:])

    assert accumulator.to_dict() == expected
    without_cases = accumulator.to_dict(include_cases=False)
    assert without_cases["cases"] == []
    assert without_cases["summary"] == expected["summary"]
    assert len(case_rows_path.read_text().splitlines()) == 2

    output_path = tmp_path / "report.json"
    accumulator.write_json(output_path)
    assert json.loads(output_path.read_text()) == expected
