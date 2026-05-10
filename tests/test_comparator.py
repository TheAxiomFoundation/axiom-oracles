from axiom_programs.comparison.comparator import Comparator
from axiom_programs.comparison.mappings import ProgramMapping
from axiom_programs.core.results import EngineResult


def test_boolean_eligibility_comparison() -> None:
    mappings = [
        ProgramMapping(
            standard="snap",
            description="SNAP",
            category="food",
            accessnyc_code="S2R007",
            policyengine_variable="snap",
        )
    ]
    left = [EngineResult("accessnyc", 1, {"S2R007": True})]
    right = [EngineResult("policyengine", 1, {"snap": 120})]

    comparison = Comparator(mappings).compare(left, right)[0]

    assert comparison.match_rate == 100
    assert comparison.comparisons[0].matches


def test_boolean_eligibility_mismatch() -> None:
    mappings = [
        ProgramMapping(
            standard="snap",
            description="SNAP",
            category="food",
            accessnyc_code="S2R007",
            policyengine_variable="snap",
        )
    ]
    left = [EngineResult("accessnyc", 1, {"S2R007": True})]
    right = [EngineResult("policyengine", 1, {"snap": 0})]

    comparison = Comparator(mappings).compare(left, right)[0]

    assert comparison.match_rate == 0
    assert comparison.mismatch_count == 1
