from axiom_oracles.cli import _comparison_report
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.core.case import Case, Concepts
from axiom_oracles.core.results import EngineResult


def test_comparison_report_includes_weighted_summary_and_concept_aggregates() -> None:
    mappings = [
        ProgramMapping(
            standard=Concepts.SNAP_ELIGIBLE,
            description="SNAP eligibility",
            category="food",
            accessnyc_code="S2R007",
            policyengine_variable="is_snap_eligible",
        )
    ]
    cases = [
        Case(
            case_id="case-1",
            period="2026",
            metadata={"household_weight": 10},
        ),
        Case(
            case_id="case-2",
            period="2026",
            metadata={"household_weight": 90},
        ),
    ]
    left = [
        EngineResult("accessnyc", "case-1", {"S2R007": True}),
        EngineResult("accessnyc", "case-2", {"S2R007": False}),
    ]
    right = [
        EngineResult("policyengine", "case-1", {"is_snap_eligible": False}),
        EngineResult("policyengine", "case-2", {"is_snap_eligible": False}),
    ]
    comparisons = Comparator(mappings).compare(left, right)

    report = _comparison_report(
        suite_name="auto",
        population="enhanced-cps",
        locales={"US-NY-NYC"},
        scope=None,
        cases=cases,
        mappings=mappings,
        comparisons=comparisons,
    )

    assert report["summary"]["weighted"] == {
        "comparison_weight": 100,
        "match_weight": 90,
        "mismatch_weight": 10,
        "match_rate": 90,
    }
    assert report["aggregates"] == [
        {
            "concept": Concepts.SNAP_ELIGIBLE,
            "description": "SNAP eligibility",
            "category": "food",
            "comparison": "eligibility",
            "parent": None,
            "components": [],
            "comparison_count": 2,
            "mismatch_count": 1,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "missing_both_count": 0,
            "match_rate": 50,
            "comparison_weight": 100,
            "match_weight": 90,
            "mismatch_weight": 10,
            "weighted_match_rate": 90,
            "left_positive_weight": 10,
            "right_positive_weight": 0,
            "left_positive_rate": 10,
            "right_positive_rate": 0,
            "positive_rate_difference": 10,
        }
    ]


def test_comparison_report_defaults_missing_weights_to_one() -> None:
    mapping = ProgramMapping(
        standard=Concepts.SNAP_BENEFIT,
        description="SNAP amount",
        category="food",
        comparison="amount",
        tolerance=1,
        accessnyc_code="S2R007",
        policyengine_variable="snap",
    )
    cases = [Case(case_id="case-1", period="2026")]
    comparisons = Comparator([mapping]).compare(
        [EngineResult("accessnyc", "case-1", {"S2R007": 120})],
        [EngineResult("policyengine", "case-1", {"snap": 125})],
    )

    report = _comparison_report(
        suite_name="auto",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=cases,
        mappings=[mapping],
        comparisons=comparisons,
    )

    assert report["summary"]["weighted"]["comparison_weight"] == 1
    assert report["aggregates"][0]["left_weighted_sum"] == 120
    assert report["aggregates"][0]["right_weighted_sum"] == 125
    assert report["aggregates"][0]["weighted_difference"] == -5
