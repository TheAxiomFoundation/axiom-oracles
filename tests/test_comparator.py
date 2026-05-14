from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.core.results import EngineResult


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


def test_missing_amount_output_is_not_treated_as_zero_match() -> None:
    mappings = [
        ProgramMapping(
            standard="us:test#income_tax",
            description="Federal income tax",
            category="tax",
            comparison="amount",
            tolerance=15,
            targets={"policyengine": "income_tax", "taxsim": "fiitax"},
        )
    ]
    left = [EngineResult("policyengine", 1, {})]
    right = [EngineResult("taxsim", 1, {"fiitax": 0})]

    comparison = Comparator(mappings).compare(left, right)[0]
    variable = comparison.comparisons[0]

    assert comparison.mismatch_count == 1
    assert variable.left_value is None
    assert variable.right_value == 0
    assert variable.difference is None
    assert not variable.matches


def test_amount_comparison_can_use_relative_tolerance_for_large_outputs() -> None:
    mappings = [
        ProgramMapping(
            standard="us:test#state_income_tax",
            description="State income tax",
            category="tax",
            comparison="amount",
            tolerance=15,
            relative_tolerance=0.0000002,
            targets={"axiom": "state_income_tax", "policyengine": "state_income_tax"},
        )
    ]
    left = [EngineResult("axiom", 1, {"state_income_tax": 736_657_861.9593371})]
    right = [EngineResult("policyengine", 1, {"state_income_tax": 736_657_920.0})]

    comparison = Comparator(mappings).compare(left, right)[0]
    variable = comparison.comparisons[0]

    assert comparison.match_rate == 100
    assert variable.matches
    assert variable.relative_tolerance == 0.0000002


def test_comparison_carries_engine_errors() -> None:
    mappings = [
        ProgramMapping(
            standard="us:test#income_tax",
            description="Federal income tax",
            category="tax",
            comparison="amount",
            targets={"policyengine": "income_tax", "taxsim": "fiitax"},
        )
    ]

    comparison = Comparator(mappings).compare(
        [
            EngineResult(
                "policyengine",
                "case-1",
                {},
                errors=("income_tax: invalid state",),
            )
        ],
        [EngineResult("taxsim", "case-1", {"fiitax": 0})],
    )[0]

    assert comparison.left_errors == ("income_tax: invalid state",)
    assert comparison.right_errors == ()
