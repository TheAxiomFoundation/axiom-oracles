from axiom_programs.comparison.comparator import Comparator
from axiom_programs.comparison.mappings import ProgramMapping
from axiom_programs.comparison.report import (
    COMPARISON_REPORT_SCHEMA_VERSION,
    MismatchKind,
    build_comparison_report,
)
from axiom_programs.core.case import Case
from axiom_programs.core.results import EngineResult


def test_report_has_stable_schema_and_eligibility_mismatch_kind() -> None:
    mapping = ProgramMapping(
        standard="us:test#snap_eligible",
        description="SNAP eligibility",
        category="food",
        targets={"accessnyc": "S2R007", "policyengine": "is_snap_eligible"},
    )
    comparisons = Comparator([mapping]).compare(
        [EngineResult("accessnyc", "case-1", {"S2R007": True})],
        [EngineResult("policyengine", "case-1", {"is_snap_eligible": False})],
    )

    report = build_comparison_report(
        suite_name="nyc-synthetic",
        population="synthetic",
        locales={"US-NY-NYC"},
        scope=None,
        cases=[Case(case_id="case-1", period="2026")],
        mappings=[mapping],
        comparisons=comparisons,
    )

    assert report["schema_version"] == COMPARISON_REPORT_SCHEMA_VERSION
    assert report["engines"] == {"left": "accessnyc", "right": "policyengine"}
    assert report["summary"]["mismatches_by_kind"] == [
        {"value": MismatchKind.ELIGIBILITY_LEFT_ONLY, "count": 1}
    ]
    assert report["mismatches"][0]["kind"] == MismatchKind.ELIGIBILITY_LEFT_ONLY
    assert report["cases"][0]["mismatches"][0]["kind"] == (
        MismatchKind.ELIGIBILITY_LEFT_ONLY
    )


def test_amount_mismatch_kind_is_reported_for_nonmatching_amounts() -> None:
    mapping = ProgramMapping(
        standard="us:test#income_tax",
        description="Federal income tax",
        category="tax",
        comparison="amount",
        tolerance=15,
        targets={"taxsim": "fiitax", "policyengine": "fiitax"},
    )
    comparisons = Comparator([mapping]).compare(
        [EngineResult("taxsim", 1, {"fiitax": 100})],
        [EngineResult("policyengine", 1, {"fiitax": 125})],
    )

    report = build_comparison_report(
        suite_name="taxsim-fixture",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=[Case(case_id=1, period="2026")],
        mappings=[mapping],
        comparisons=comparisons,
    )

    assert report["summary"]["mismatches_by_kind"] == [
        {"value": MismatchKind.AMOUNT_DIFFERENCE, "count": 1}
    ]
    assert report["mismatches"][0]["difference"] == -25


def test_missing_output_mismatch_kind_and_engine_errors_are_reported() -> None:
    mapping = ProgramMapping(
        standard="us:test#income_tax",
        description="Federal income tax",
        category="tax",
        comparison="amount",
        tolerance=15,
        targets={"policyengine": "income_tax", "taxsim": "fiitax"},
    )
    comparisons = Comparator([mapping]).compare(
        [
            EngineResult(
                "policyengine",
                "case-1",
                {},
                errors=("income_tax: invalid state",),
            )
        ],
        [EngineResult("taxsim", "case-1", {"fiitax": 0})],
    )

    report = build_comparison_report(
        suite_name="taxsim-fixture",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=[Case(case_id="case-1", period="2026")],
        mappings=[mapping],
        comparisons=comparisons,
    )

    assert report["summary"]["mismatches_by_kind"] == [
        {"value": MismatchKind.MISSING_LEFT, "count": 1}
    ]
    assert report["summary"]["error_count"] == 1
    assert report["summary"]["errors_by_engine"] == [
        {"value": "policyengine", "count": 1}
    ]
    assert report["mismatches"][0]["difference"] is None
    assert report["errors"] == [
        {
            "case_id": "case-1",
            "side": "left",
            "engine": "policyengine",
            "error": "income_tax: invalid state",
        }
    ]
    assert report["cases"][0]["left_errors"] == ["income_tax: invalid state"]
    assert report["aggregates"][0]["missing_left_count"] == 1
