"""The API parity corpus builder validates external comparisons the way
axiom-api's validateParityCase does (src/parity.ts), so a corpus axiom-api
cannot load never reaches a release."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import build_api_parity_corpus as builder

CORPUS = Path(__file__).resolve().parent.parent / "corpora" / "api-parity"


def comparison(**overrides: object) -> dict:
    value = {
        "id": "pe",
        "engine": "policyengine",
        "request": {"country_id": "us", "version": "current", "household": {}},
        "mappings": [
            {"axiom_variable": "benefit", "external_path": "result.benefit.2026-01"},
            {"axiom_variable": "net_income", "external_path": "result.net_income.2026-01"},
        ],
        "tolerance": {"amount": 0.01},
    }
    value.update(overrides)
    return value


def case(*comparisons: dict, **overrides: object) -> dict:
    value = {
        "id": "x",
        "axiom_request": {"program_id": "p", "jurisdiction": "j", "household": {"period": "2026-01"}},
        "expected_axiom_outputs": {"benefit": 100, "net_income": 50},
        "tolerance": {"amount": 0.01},
        "external_comparisons": list(comparisons),
    }
    value.update(overrides)
    return value


KNOWN = {
    "issue": "https://github.com/TheAxiomFoundation/axiom-api/issues/257",
    "note": "The engine applies an allowance this case omits.",
    "pinned_engine_outputs": {"benefit": 543, "net_income": 7},
}


def errors(value: dict) -> list[str]:
    return builder.validate_case(value, "case.json")


def test_every_committed_case_is_valid() -> None:
    for path in sorted(CORPUS.glob("*.json")):
        assert errors(json.loads(path.read_text())) == [], path.name


def test_the_build_is_deterministic_and_reports_its_sha(tmp_path, monkeypatch, capsys) -> None:
    out = tmp_path / "corpus.json"
    monkeypatch.setattr(sys, "argv", ["build", "--out", str(out)])
    assert builder.main() == 0
    payload = out.read_bytes()
    assert f"sha256 {hashlib.sha256(payload).hexdigest()}" in capsys.readouterr().out
    assert [entry["id"] for entry in json.loads(payload)] == sorted(
        json.loads(path.read_text())["id"] for path in CORPUS.glob("*.json")
    )


def test_co_snap_compares_january_and_records_its_known_difference() -> None:
    co_snap = json.loads((CORPUS / "co-snap-us-co.json").read_text())
    assert co_snap["axiom_request"]["household"]["period"] == "2026-01"
    [declared] = co_snap["external_comparisons"]
    assert all(m["external_path"].endswith(".2026-01") and "transform" not in m for m in declared["mappings"])
    assert declared["known_difference"]["pinned_engine_outputs"] == {
        "snap_benefit_amount": 543,
        "snap_net_income": 7,
    }
    assert not any("fifty-cent" in note for note in co_snap["notes"])


def test_accepts_a_comparison_with_a_complete_known_difference() -> None:
    assert errors(case(comparison(known_difference=KNOWN))) == []


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (case(comparison(mappings=[{"axiom_variable": "trace_only", "external_path": "r"}])), "not in expected_axiom_outputs"),
        (
            case(comparison(mappings=[{"axiom_variable": "benefit", "external_path": "a"}, {"axiom_variable": "benefit", "external_path": "b"}])),
            "each axiom_variable once",
        ),
        (case(comparison(), comparison()), "ids must be unique"),
        (case(comparison(mappings=[])), "non-empty array"),
        (case(comparison(engine="other")), "engine must be policyengine"),
        (case(comparison(request={"country_id": "us", "version": "beta", "household": {}})), "current or frontier"),
        (
            case(comparison(mappings=[{"axiom_variable": "benefit", "external_path": "result.benefit.2026", "transform": "annual_to_monthly"}])),
            "divides an annual value by 12 while the Axiom case computes 2026-01",
        ),
        (case(comparison(mappings=[{"axiom_variable": "benefit", "external_path": "r", "transform": "weekly"}])), "transform is unsupported"),
        (case(comparison(tolerance={"amount": -1})), "finite, non-negative"),
        (case(comparison(), tolerance={"amount": "0.01"}), "finite, non-negative"),
        (case(comparison(known_difference=None)), "known_difference must be an object"),
        (case(comparison(known_difference={**KNOWN, "issue": "axiom-api#257"})), "tracking-issue URL"),
        (case(comparison(known_difference={**KNOWN, "note": " "})), "known_difference.note required"),
        (case(comparison(known_difference={**KNOWN, "pinned_engine_outputs": {"benefit": 543}})), "pin exactly the mapped variables"),
        (
            case(comparison(known_difference={**KNOWN, "pinned_engine_outputs": {"benefit": True, "net_income": 7}})),
            "finite numbers",
        ),
    ],
)
def test_rejects_malformed_comparisons(value: dict, message: str) -> None:
    assert any(message in error for error in errors(value)), errors(value)


def test_an_annual_mapping_is_fine_when_the_case_names_a_year() -> None:
    annual = comparison(
        mappings=[
            {"axiom_variable": "benefit", "external_path": "result.benefit.2026", "transform": "annual_to_monthly"},
            {"axiom_variable": "net_income", "external_path": "result.net_income.2026", "transform": "annual_to_monthly"},
        ]
    )
    value = case(annual)
    value["axiom_request"]["household"] = {"period": "2026"}
    assert errors(value) == []


@pytest.mark.parametrize("household", [{}, {"period": "Jan 2026"}, {"period": "2026-13"}, {"period": 2026}])
def test_a_case_with_a_comparison_must_name_the_period_it_computes(household: dict) -> None:
    # Without it the runtime computes its package's default period, which
    # the comparison cannot see (axiom-api src/runtime-compiled.ts).
    value = case(comparison())
    value["axiom_request"]["household"] = household
    assert any("must name the period it computes" in error for error in errors(value))


def test_a_case_without_comparisons_needs_no_period() -> None:
    value = case()
    value["axiom_request"]["household"] = {}
    assert errors(value) == []


TRACE = {
    "label": "Utility allowance",
    "axiom_variable": "u",
    "external_variable": "snap_utility_allowance",
    "external_paths": ["result.u.2026-01"],
}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        # Each shape axiom-api's validateParityCase rejects at boot
        # (src/parity.ts), so a release the API cannot load is never cut.
        (lambda c: c["external_comparisons"][0].update(trace_mappings="x"), "trace_mappings must be an array"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=[{**TRACE, "transform": "weekly"}]), "transform is unsupported"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=[{**TRACE, "label": " "}]), "label must be a string"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=[{**TRACE, "axiom_variable": ""}]), "axiom_variable must be a string"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=[{**TRACE, "external_variable": None}]), "external_variable must be a string"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=[{**TRACE, "external_paths": []}]), "external_paths must be non-empty strings"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=[{**TRACE, "external_paths": [" "]}]), "external_paths must be non-empty strings"),
        (lambda c: c["external_comparisons"][0].update(trace_mappings=["x"]), "must be an object"),
        (lambda c: c["external_comparisons"][0].update(notes="x"), "notes must be strings"),
        (lambda c: c.update(notes="x"), "notes must be strings"),
        (lambda c: c.update(trace_variables=[1]), "trace_variables must be strings"),
        # An explicit null is not an absent field to axiom-api.
        (lambda c: c.update(tolerance=None), "tolerance must be an object"),
        (lambda c: c["external_comparisons"][0].update(tolerance=None), "tolerance must be an object"),
        (lambda c: c.update(external_comparisons=None), "external_comparisons must be an array"),
        (lambda c: c.update(known_deviation=None), "known_deviation must be an object"),
        (lambda c: c["external_comparisons"][0]["mappings"][0].update(transform=None), "transform is unsupported"),
    ],
)
def test_rejects_what_axiom_api_rejects(mutate, message: str) -> None:
    value = case(comparison())
    mutate(value)
    assert any(message in error for error in errors(value)), errors(value)


def test_accepts_valid_trace_mappings_and_notes() -> None:
    value = case(
        comparison(
            trace_mappings=[TRACE, {**TRACE, "transform": "annual_to_monthly_sum", "external_paths": ["a", "b"]}],
            notes=["Inputs are annual."],
        ),
        notes=["Monthly values."],
        trace_variables=["u"],
    )
    assert errors(value) == []


def test_the_release_refuses_values_json_cannot_carry(tmp_path, monkeypatch) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    (source / "case.json").write_text('{"id": "x", "axiom_request": {}, "expected_axiom_outputs": {"v": NaN}}')
    monkeypatch.setattr(builder, "CORPUS_DIR", source)
    monkeypatch.setattr(sys, "argv", ["build", "--out", str(tmp_path / "out.json")])
    with pytest.raises(ValueError):
        builder.main()


numbers = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.booleans(),
    st.text(max_size=3),
    st.none(),
)


@given(numbers)
def test_a_tolerance_is_accepted_iff_it_is_a_finite_non_negative_number(amount: object) -> None:
    accepted = builder.validate_tolerance({"amount": amount}, "t") == []
    expected = (
        isinstance(amount, (int, float))
        and not isinstance(amount, bool)
        and math.isfinite(amount)
        and amount >= 0
    )
    assert accepted == expected


variables = st.lists(st.from_regex(r"[a-z][a-z_]{0,8}", fullmatch=True), min_size=1, max_size=4, unique=True)


@given(variables, st.dictionaries(st.from_regex(r"[a-z][a-z_]{0,8}", fullmatch=True), numbers, max_size=5))
def test_a_known_difference_is_accepted_iff_it_pins_exactly_the_mapped_variables_with_numbers(
    mapped: list[str], pinned: dict
) -> None:
    value = {**KNOWN, "pinned_engine_outputs": pinned}
    accepted = builder.validate_known_difference(value, mapped, "k") == []
    expected = sorted(pinned) == sorted(mapped) and all(
        isinstance(pin, (int, float)) and not isinstance(pin, bool) and math.isfinite(pin) for pin in pinned.values()
    )
    assert accepted == expected


@given(st.lists(st.sampled_from(["benefit", "net_income", "extra"]), min_size=1, max_size=4))
def test_validation_never_mutates_the_case(mapped: list[str]) -> None:
    value = case(comparison(mappings=[{"axiom_variable": v, "external_path": f"result.{v}"} for v in mapped]))
    before = copy.deepcopy(value)
    errors(value)
    assert value == before
