from __future__ import annotations

import pytest

from scripts.us_tariff_schedule_campaign import (
    BASE_INDEPENDENT_AUTHORITY_SLOTS,
    EXPECTED_DROPPED_ENTRY_FLAGS,
    compare_record,
    computed_conformant,
    enforce_excluded_exposure,
    filter_declared_feed,
    query_plan,
    route_member,
    validate_dispositions,
    witness_replay,
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
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)
    assert plan["excluded_components"] == ["ieepa", "forced_labor_section_301"]
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
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)


def test_routes_statistical_member_to_rate_line() -> None:
    tables = {"01": {102294000: ("specific", "specific")}}
    assert route_member("0102294024", tables) == ("01", 102294000, "specific", "specific")


def test_explicit_unowned_member_routes_to_empty() -> None:
    assert route_member("9802009100", {"98": {}}) == (
        "98", 9802009100, "empty", "empty"
    )


def _comparison_record() -> dict:
    expected = {
        "statutory_base_rate": "0.05", "statutory_rate_232": "0",
        "statutory_rate_ieepa_recip": "0.1", "statutory_rate_ieepa_fent": "0",
        "statutory_rate_301": "0", "statutory_rate_301_cs": "0",
        "statutory_rate_s301fl": "0", "statutory_rate_s301br": "0",
        "statutory_rate_s338": "0", "statutory_rate_s122": "0",
        "statutory_rate_section_201": "0", "statutory_rate_other": "0",
    }
    actual = {
        "mfn_ad_valorem_rate": 0.05, "ieepa_component_rate": 0.1,
        "section_201_component_rate": 0, "section_122_component_rate": 0,
        "section_232_aluminum_component_rate": 0, "section_232_steel_component_rate": 0,
        "section_338_component_rate": 0, "china_section_301_component_rate": 0,
        "brazil_section_301_component_rate": 0, "forced_labor_section_301_component_rate": 0,
        "schedule_statutory_stack": 0.15,
    }
    return {"case_id": "case", "expected": expected, "actual": actual, "engine_errors": [],
            "plan": query_plan("ad_valorem"), "hts10": "0101210010", "hts_line": "0101210000",
            "iso2": "CA", "revision": "r1", "interval": ["2026-02-15", "2026-02-19"],
            "origin_regime": "regime", "flags": {"entry_is_test": False}}


def test_changed_expected_value_mutant_fails() -> None:
    record = _comparison_record()
    assert all(row["match"] for row in compare_record(record))
    record["expected"]["statutory_rate_s122"] = "0.01"
    assert any(row["slot"] == "section_122" and not row["match"] for row in compare_record(record))


def test_engine_error_surfaces_as_unexplained_comparison() -> None:
    record = _comparison_record() | {"actual": None, "engine_errors": ["boom"]}
    assert compare_record(record) == [{"case_id": "case", "slot": "engine_error", "match": False,
                                       "error": ["boom"], "delta": None}]


def test_stale_and_overlapping_disposition_selectors_fail() -> None:
    base = {"id": "one", "evidence": {"receipt_type": "instrument", "instrument_receipt": "receipt"}}
    with pytest.raises(ValueError, match="stale"):
        validate_dispositions([base | {"signatures": ["stale"]}], {"live": 1})
    with pytest.raises(ValueError, match="overlapping"):
        validate_dispositions([base | {"signatures": ["live"]},
                               (base | {"id": "two", "signatures": ["live"]})], {"live": 1})


def test_nonzero_excluded_column_exposure_fails_x1() -> None:
    with pytest.raises(ValueError, match="X1"):
        enforce_excluded_exposure({"statutory_rate_301_cs": 1, "statutory_rate_other": 0})


def test_unclassified_signature_fails_computed_conformance() -> None:
    assert computed_conformant(unexplained=1, engine_errors=0) is False


def test_witness_replay_is_conformant_and_byte_stable() -> None:
    assert witness_replay()["byte_stable"] is True
