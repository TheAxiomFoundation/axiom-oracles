"""Keep the source single charge distinct from the actual generated overlap."""

import json
from pathlib import Path
from scripts import build_us_tariff_china_list_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_source_and_producer_bindings():
    d = receipt()
    assert d["producer_sha256"] == evidence.sources.sha(
        Path(evidence.__file__).read_bytes()
    )
    assert d["runtime_helper_sha256"] == evidence.sources.sha(
        Path(runtime.__file__).read_bytes()
    )
    assert d["source_records"] == evidence.source_records()
    assert d["fixtures"] == evidence.fixtures()
    assert all(value is False for value in d["claim"].values())


def test_real_beer_overlap_remains_a_counterexample():
    d = receipt()
    matches = differences = 0
    for run in d["runs"]:
        for field in ("request", "response"):
            assert run[field + "_sha256"] == runtime.original.digest(
                runtime.original.canonical(run[field])
            )
        for raw, checked in zip(
            run["response"]["results"], run["results"], strict=True
        ):
            actual = runtime.output(next(iter(raw["outputs"].values())))
            assert checked["actual"] == {evidence.OUT: actual}
            assert checked["source_match"] is (
                actual == checked["expected_from_source"]
            )
            if checked["source_match"]:
                matches += 1
            else:
                differences += 1
                assert checked["case_id"] == "list-2203000000-CN"
                assert (actual, checked["expected_from_source"]) == ("0.5", "0.25")
                assert run["input_mode"] == "actual_adapter"
    assert (matches, differences) == (17, 1)
    assert d["validation"]["all_cases_match"] is False


def test_correct_source_membership_can_still_feed_an_incorrect_composition():
    d = receipt()
    beer = next(r for r in d["adapter_results"] if r["case_id"] == "list-2203000000-CN")
    assert beer["membership_matches_source"] is True
    assert beer["actual_flags"]["entry_is_china_301_list123"] is True
    assert beer["actual_flags"]["entry_is_line_d"] is True
    assert beer["actual_flags"]["entry_is_china_301_list4a"] is False
    ball = next(r for r in d["adapter_results"] if r["case_id"] == "list-9506624040-CN")
    assert ball["actual_flags"]["entry_is_china_301_list4a"] is True
    assert ball["actual_flags"]["entry_is_china_301_list123"] is False
    assert all(r["grounding"] == "uncaptured" for r in d["scopes"])
