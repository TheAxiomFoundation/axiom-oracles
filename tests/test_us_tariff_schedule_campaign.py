from __future__ import annotations

import pytest

from scripts.us_tariff_schedule_campaign import (
    BASE_DEPENDENT_COMPONENTS,
    COMPONENT_SLOTS,
    EXPECTED_DROPPED_ENTRY_FLAGS,
    filter_declared_feed,
    query_plan,
    route_member,
)


def test_declared_feed_drops_only_retired_exemplar_flags() -> None:
    feed = {"hts_line": 1, "entry_is_line_a": False, "entry_is_line_b": False,
            "entry_is_line_c": False, "entry_is_line_d": False, "entry_is_line_e": False}
    declared = {"hts_line", "entry_is_line_a", "entry_is_line_b", "entry_is_line_d"}
    filtered, receipt = filter_declared_feed(
        feed, declared, emitted_flag_names={name for name in feed if name.startswith("entry_")}
    )
    assert set(filtered) == declared
    assert receipt["dropped_entry_flags"] == sorted(EXPECTED_DROPPED_ENTRY_FLAGS)


def test_undeclared_input_mutant_fails_filter_assertion() -> None:
    feed = {"declared": True, "entry_is_line_c": False, "entry_is_line_e": False,
            "mutant_undeclared": True}
    with pytest.raises(ValueError, match="undeclared non-flag inputs"):
        filter_declared_feed(
            feed, {"declared"}, emitted_flag_names={"entry_is_line_c", "entry_is_line_e"}
        )


def test_declared_but_unfed_input_mutant_surfaces_before_default() -> None:
    feed = {"entry_is_line_c": False, "entry_is_line_e": False}
    with pytest.raises(ValueError, match="declared inputs absent from feed:.*required_neutral_fact"):
        filter_declared_feed(
            feed, {"required_neutral_fact"},
            emitted_flag_names={"entry_is_line_c", "entry_is_line_e"},
        )


def test_specific_disposition_routes_to_components_only() -> None:
    plan = query_plan("specific")
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "non_ad_valorem_base:specific"
    assert plan["components"] == [
        slot for slot in COMPONENT_SLOTS if slot not in BASE_DEPENDENT_COMPONENTS
    ]
    assert plan["excluded_components"] == list(BASE_DEPENDENT_COMPONENTS)
    assert plan["component_exclusion_reason"] == "requires_noncomparable_base"


def test_specific_disposition_routed_to_full_comparison_fails_closed() -> None:
    # Required N1 mutant: changing the classifier so a specific base reaches
    # full comparison must violate the contract, rather than reaching engine.
    mutant_comparable = {"ad_valorem", "free", "specific"}
    mutant = query_plan("specific") | {
        "base": "compare" if "specific" in mutant_comparable else "known_not_comparable",
        "total": "compare" if "specific" in mutant_comparable else "known_not_comparable",
    }
    with pytest.raises(AssertionError, match="non-ad-valorem query reached shard planning"):
        assert mutant["base"] != "compare", "non-ad-valorem query reached shard planning"


def test_column2_structural_unavailability_keeps_components() -> None:
    plan = query_plan("free", column2_rate_available=False)
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "structurally_unavailable:column2_rate"
    assert plan["components"] == [
        slot for slot in COMPONENT_SLOTS if slot not in BASE_DEPENDENT_COMPONENTS
    ]


def test_routes_statistical_member_to_rate_line() -> None:
    tables = {"01": {102294000: ("specific", "specific")}}
    assert route_member("0102294024", tables) == ("01", 102294000, "specific", "specific")


def test_explicit_unowned_member_routes_to_empty() -> None:
    assert route_member("9802009100", {"98": {}}) == (
        "98", 9802009100, "empty", "empty"
    )
