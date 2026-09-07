"""Retain section122 precision failures and limit section201 claims to expiry."""

import json
from pathlib import Path

from scripts import build_us_tariff_temporal_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_sources_and_producer_bindings_are_current():
    d = receipt()
    assert d["producer_sha256"] == evidence.sources.sha(
        Path(evidence.__file__).read_bytes()
    )
    assert d["runtime_helper_sha256"] == evidence.sources.sha(
        Path(runtime.__file__).read_bytes()
    )
    assert d["sources"] == evidence.source_evidence()
    assert d["surcharge_fixtures"] == evidence.surcharge_fixtures()
    assert all(value is False for value in d["claim"].values())


def test_actual_runtime_and_precision_counterexamples_are_preserved():
    d = receipt()
    matched = mismatched = solar = positive = 0
    counterexamples = set()
    for run in d["runs"]:
        for field in ("request", "response"):
            assert run[field + "_sha256"] == runtime.original.digest(
                runtime.original.canonical(run[field])
            )
        for raw, checked in zip(
            run["response"]["results"], run["results"], strict=True
        ):
            assert raw["entity_id"] == checked["case_id"]
            assert len(raw["outputs"]) == 1
            actual = runtime.output(next(iter(raw["outputs"].values())))
            assert actual == next(iter(checked["actual"].values()))
            assert checked["source_match"] is (
                actual == checked["expected_from_source"]
            )
            positive += actual != "0"
            if checked["source_match"]:
                matched += 1
            else:
                assert actual == "0.1" and checked["expected_from_source"] == "0"
                counterexamples.add(checked["case_id"])
                mismatched += 1
            if run["scope"] == evidence.INPUTS[1]:
                assert actual == "0"
                assert raw["period"]["start"] >= "2026-02-15"
                solar += 1
    assert (matched, mismatched, solar) == (41, 2, 20)
    assert positive > 2
    assert counterexamples == {"s122-start-000000", "s122-start-000059"}
    assert counterexamples == {row["case_id"] for row in d["known_mismatches"]}


def test_solar_membership_is_not_confused_with_an_active_duty():
    d = receipt()
    rows = d["adapter_results"]
    assert len(rows) == 10
    assert sum(row["actual_cspv_membership"] for row in rows) == 5
    assert all(row["duty_is_active"] is False for row in rows)
    assert {row["input"]: row["status"] for row in d["scopes"]} == {
        evidence.INPUTS[0]: "blocked_at_subminute_activation",
        evidence.INPUTS[1]: "bounded_postexpiry_replay_only",
    }
    assert all(row["grounding"] == "uncaptured" for row in d["scopes"])
    assert d["validation"]["all_cases_match"] is False
    assert d["validation"]["new_campaign_rows_scanned"] == 0
