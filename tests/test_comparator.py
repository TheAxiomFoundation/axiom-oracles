from copy import deepcopy

import pytest
from hypothesis import given, settings, strategies as st

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


def test_comparison_names_the_engine_behind_a_nan_household_id() -> None:
    mappings = [
        ProgramMapping(
            standard="us:test#income_tax",
            description="Federal income tax",
            category="tax",
            comparison="amount",
            targets={"axiom": "income_tax", "taxsim": "fiitax"},
        )
    ]

    # pandas coerces an unparseable TAXSIM stdout line to a NaN id; NaN is
    # unequal to itself, so it passes the duplicate check and shows up as
    # "unexpected [nan, nan, ...]" — fail on it by name instead.
    with pytest.raises(
        ValueError,
        match=r"Invalid right result household IDs: engine 'taxsim' returned a "
        r"result with household id nan",
    ):
        Comparator(mappings).compare(
            [EngineResult("axiom", "case-1", {"income_tax": 0})],
            [
                EngineResult("taxsim", "case-1", {"fiitax": 0}),
                EngineResult("taxsim", float("nan"), {}),
            ],
        )


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


def _diagnostic_result(count, relation):
    return EngineResult("axiom", "case-1", {"n": 1}, raw={
        "relation_binding_diagnostics": {
            "count": count, "by_relation": {relation: count} if count else {},
            "samples": [
                {"relation": relation, "tuple": ["private-member", "private-owner"]}
                for _ in range(min(count, 20))
            ],
        },
    })


def _diagnostic_comparator():
    return Comparator([ProgramMapping(
        standard="us:test#n", description="count", category="test",
        comparison="amount", targets={"axiom": "n"},
    )])


def test_same_engine_comparison_preserves_both_diagnostic_counts():
    from axiom_oracles.comparison.report import ComparisonReportAccumulator
    from axiom_oracles.core.case import Case

    comparator = _diagnostic_comparator()
    comparison = comparator.compare(
        [_diagnostic_result(2, "members")], [_diagnostic_result(3, "members")],
    )[0]
    accumulator = ComparisonReportAccumulator(
        suite_name="same-engine", population="synthetic", locales=set(),
        scope=None, mappings=comparator.mappings, include_inputs=False,
    )
    identity = {"axiom": {"sha256": "a" * 64}}
    accumulator.engine_identity = identity
    accumulator.add_batch([Case("case-1", "2026-01")], [comparison])

    assert accumulator.to_dict()["provenance"]["relation_binding_diagnostics"] == {
        "count": 5, "by_relation": {"members": 5},
        "samples": [{"relation": "members"}] * 5,
    }
    report = accumulator.to_dict()
    assert (
        report["engine_identity"], report["provenance"]["relation_binding_diagnostics"]["count"],
    ) == (identity, 5)


@settings(max_examples=40, deadline=None)
@given(
    left_count=st.integers(0, 40), right_count=st.integers(0, 40),
    right_relation=st.sampled_from(["members", "payments"]),
)
def test_same_engine_diagnostics_are_additive_bounded_and_leave_sources_unchanged(
    left_count, right_count, right_relation,
):
    left = _diagnostic_result(left_count, "members")
    right = _diagnostic_result(right_count, right_relation)
    before = deepcopy((left.raw, right.raw))

    comparison = _diagnostic_comparator().compare([left], [right])[0]

    total = left_count + right_count
    if total:
        diagnostics = comparison.relation_binding_diagnostics["axiom"]
        counts = {"members": left_count} if left_count else {}
        if right_count:
            counts[right_relation] = counts.get(right_relation, 0) + right_count
        expected_samples = (
            left.raw["relation_binding_diagnostics"]["samples"]
            + right.raw["relation_binding_diagnostics"]["samples"]
        )[:20]
        assert diagnostics == {
            "count": total, "by_relation": counts, "samples": expected_samples,
        }
    else:
        assert comparison.relation_binding_diagnostics == {}
    assert (left.raw, right.raw) == before
