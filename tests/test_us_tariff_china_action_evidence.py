"""The two omitted classifications must stay visible as counterexamples."""

import json
from pathlib import Path

from scripts import build_us_tariff_china_action_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_source_bindings_and_receipt_generation_are_current():
    d = receipt()
    assert d["producer_sha256"] == evidence.sources.sha(
        Path(evidence.__file__).read_bytes()
    )
    assert d["runtime_helper_sha256"] == evidence.sources.sha(
        Path(runtime.__file__).read_bytes()
    )
    assert d["sources"] == evidence.source_evidence()
    assert d["fixtures"] == evidence.fixtures()
    assert all(value is False for value in d["claim"].values())
    assert {r["status"] for r in d["scopes"]} == {
        "blocked_on_missing_adapter_note31_membership"
    }


def test_replay_preserves_the_actual_adapter_failures_and_controls():
    d = receipt()
    matched = mismatched = 0
    counterexamples = []
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
            assert checked["actual"] == {evidence.OUTPUTS[0]: actual}
            matches = actual == checked["expected_from_source"]
            assert checked["source_match"] is matches
            if matches:
                matched += 1
            else:
                assert run["input_mode"] == "actual_adapter"
                assert "-CN-" in checked["case_id"]
                assert actual == "0"
                assert checked["expected_from_source"] in ("0.25", "0.5")
                counterexamples.append((run["module"]["path"], checked["case_id"]))
                mismatched += 1
    assert (matched, mismatched) == (32, 4)
    assert set(counterexamples) == {
        (r["module"], r["case_id"]) for r in d["known_mismatches"]
    }
    assert d["validation"]["all_cases_match"] is False


def test_source_and_adapter_input_paths_are_not_conflated():
    d = receipt()
    assert len(d["adapter_results"]) == 12
    assert all(r["membership_matches_source"] is False for r in d["adapter_results"])
    for row in d["adapter_results"]:
        assert sum(row["source_membership"].values()) == 1
        assert all(row["actual_china_flags"][name] is False for name in evidence.INPUTS)
    for run in d["runs"]:
        if run["input_mode"] == "declared_source_membership":
            flags = [
                r
                for r in run["request"]["dataset"]["inputs"]
                if any(r["name"].endswith("." + n) for n in evidence.INPUTS)
            ]
            assert sum(r["value"]["value"] for r in flags) == 6
            assert all(r["source_match"] for r in run["results"])


def test_origin_controls_do_not_treat_hong_kong_as_china_for_note31():
    for row in evidence.fixtures():
        if row["country_of_origin"] in ("HK", "FR"):
            assert row["expected_component_rate"] == "0"
    d = receipt()
    assert d["validation"]["new_campaign_rows_scanned"] == 0
    assert all(row["grounding"] == "uncaptured" for row in d["scopes"])
