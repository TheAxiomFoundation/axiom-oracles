"""The receipt must preserve both successful controls and real precision failures."""

import json
from pathlib import Path

import pytest

from scripts import build_us_tariff_note52_boundary_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_committed_replay_preserves_real_results_and_known_failures():
    document = receipt()
    assert document["producer_sha256"] == evidence.sources.sha(
        Path(evidence.__file__).read_bytes()
    )
    assert document["runtime_helper_sha256"] == evidence.sources.sha(
        Path(runtime.__file__).read_bytes()
    )
    assert document["fixtures"] == evidence.fixtures()
    matched = 0
    mismatched = 0
    outputs = 0
    positive = 0
    for run in document["runs"]:
        assert (
            runtime.original.digest(runtime.original.canonical(run["request"]))
            == run["request_sha256"]
        )
        assert (
            runtime.original.digest(runtime.original.canonical(run["response"]))
            == run["response_sha256"]
        )
        for raw, checked, fixture in zip(
            run["response"]["results"],
            run["results"],
            document["fixtures"],
            strict=True,
        ):
            # Resolve by the absolute names, never trust JSON map ordering.
            actual = {
                name: runtime.output(
                    raw["outputs"][
                        "us:"
                        + run["module"]["path"]
                        .removeprefix("us/")
                        .removesuffix(".yaml")
                        + "#"
                        + name
                    ]
                )
                for name in evidence.OUTPUTS
            }
            assert actual == checked["actual"]
            expected = fixture["expected_from_source"]
            differences = {
                name: {"expected": value, "actual": actual[name]}
                for name, value in expected.items()
                if actual[name] != value
            }
            assert differences == checked["differences"]
            assert checked["source_match"] is (not differences)
            if fixture["kind"] == "noon_control":
                assert not differences
            if differences:
                mismatched += 1
            else:
                matched += 1
            outputs += len(actual)
            positive += actual[evidence.OUTPUTS[2]] != "0"
    assert (matched, mismatched, outputs) == (210, 20, 690)
    assert positive > 0
    assert document["validation"]["all_cases_match"] is False
    assert document["claim"] == {
        "closed": False,
        "certified": False,
        "release_authorized": False,
    }


def test_source_cutoff_retains_the_last_second_of_the_safe_harbor():
    rows = {
        x["stipulated_entry_timestamp_eastern"]: x
        for x in evidence.fixtures()
        if x["facts"]["country_of_origin"] == "CA"
        and x["kind"] == "entry_cutoff_precision_probe"
    }
    for second in ("00:00:00", "00:00:59"):
        expected = rows["2026-07-28T" + second + "-04:00"]["expected_from_source"]
        assert expected[evidence.OUTPUTS[0]] is True
        assert expected[evidence.OUTPUTS[2]] == "0"
    assert (
        rows["2026-07-28T00:01:00-04:00"]["expected_from_source"][evidence.OUTPUTS[0]]
        is False
    )
    assert (
        rows["2026-07-28T00:01:00-04:00"]["expected_from_source"][evidence.OUTPUTS[2]]
        == "0.1"
    )


def test_usmca_flag_alone_cannot_exempt_a_non_usmca_origin():
    for row in evidence.fixtures():
        if row["facts"]["country_of_origin"] not in ("CA", "MX"):
            assert row["expected_from_source"][evidence.OUTPUTS[1]] is False
    document = receipt()
    assert {x["input"]: x["status"] for x in document["scopes"]} == {
        evidence.INPUTS[0]: "blocked_at_subminute_entry_cutoff",
        evidence.INPUTS[1]: "bounded_stipulated_fact_replay_matches",
    }
    assert len(document["known_mismatches"]) == 20
    assert all(
        row["differences"][evidence.OUTPUTS[0]] == {"expected": True, "actual": False}
        for row in document["known_mismatches"]
    )


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "judgment", "outcome": "unknown"},
        {"kind": "scalar", "value": {"kind": "bool", "value": False}},
    ],
)
def test_runtime_rejects_unproven_or_mistyped_outputs(value):
    with pytest.raises(ValueError):
        runtime.output(value)


def test_live_source_and_activation_bindings_are_explicit():
    document = receipt()
    assert document["live_source_receipt_sha256"] == evidence.sources.sha(
        evidence.sources.RECEIPT.read_bytes()
    )
    assert document["activation_source"]["pdf_sha256"] == evidence.sources.ACTION_SHA256
    assert document["general_note11"]["pdf_sha256"] == evidence.sources.GN11_SHA256
    assert len(document["source_records"]) == 7
