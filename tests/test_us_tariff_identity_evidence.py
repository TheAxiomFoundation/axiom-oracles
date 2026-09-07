"""Check actual identity replay, canonicalization boundaries and rate-row binding."""

import json
from pathlib import Path

from scripts import build_us_tariff_identity_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_receipt_binds_sources_producer_and_runtime():
    document = receipt()
    assert document["producer_sha256"] == evidence.sources.sha(
        Path(evidence.__file__).read_bytes()
    )
    assert document["runtime_helper_sha256"] == evidence.sources.sha(
        Path(runtime.__file__).read_bytes()
    )
    assert document["sources"] == evidence.source_rows()
    assert document["fixtures"] == evidence.identity_fixtures()
    assert all(v is False for v in document["claim"].values())
    assert all(row["grounding"] == "uncaptured" for row in document["scopes"])


def test_replay_results_are_rederived_from_raw_engine_outputs():
    cases = outputs = 0
    for run in receipt()["runs"]:
        for key in ("request", "response"):
            assert run[key + "_sha256"] == runtime.original.digest(
                runtime.original.canonical(run[key])
            )
        prefix = (
            "us:"
            + run["module"]["path"].removeprefix("us/").removesuffix(".yaml")
            + "#"
        )
        for raw, checked in zip(
            run["response"]["results"], run["results"], strict=True
        ):
            actual = {
                name.removeprefix(prefix): runtime.output(value)
                for name, value in raw["outputs"].items()
            }
            assert actual == checked["actual"]
            assert raw["entity_id"] == checked["case_id"]
            if "expected" in checked:
                assert checked["expected"] == actual
            cases += 1
            outputs += len(actual)
    assert (cases, outputs) == (63, 189)


def test_raw_aliases_are_not_claimed_to_match_direct_witness():
    document = receipt()
    raw, canonical = document["runs"][:2]
    assert raw["input_form"] == "raw"
    assert canonical["input_form"] == "canonical"
    expected = {row["case_id"]: row for row in document["fixtures"]}
    mismatches = set()
    for run in (raw, canonical):
        for row in run["results"]:
            differs = row["actual"] != expected[row["case_id"]]["expected_flags"]
            assert row["matches_adapter"] is (not differs)
            if run is canonical:
                assert not differs
            elif differs:
                mismatches.add(row["case_id"])
    assert mismatches == {
        row["case_id"] for row in document["normalization_differences"]
    }
    assert len(mismatches) == 9
    assert all(expected[key]["format"] != "canonical" for key in mismatches)


def test_statistical_children_use_integer_legal_rate_keys():
    document = receipt()
    keys = {}
    for run in document["runs"][2:]:
        for row in run["request"]["dataset"]["inputs"]:
            assert row["value"]["kind"] == "integer"
            keys[row["entity_id"].removeprefix("lookup-")] = row["value"]["value"]
    assert keys["7601.10.60.40"] == 7601106000
    for suffix in ("30", "60", "90"):
        assert keys["2203.00.00." + suffix] == 2203000000
    beer = document["runs"][-1]
    assert all(
        row["actual"]["schedule_column2_disposition"] == "specific"
        for row in beer["results"]
    )


def test_runtime_retains_integer_text_and_boolean_distinctions():
    assert runtime.value(7202111000) == {"kind": "integer", "value": 7202111000}
    assert runtime.value("7202111000")["kind"] == "text"
    assert runtime.value(7202111000.0)["kind"] == "decimal"
    assert runtime.value(True)["kind"] == "bool"
    assert (
        runtime.output({"kind": "scalar", "value": {"kind": "integer", "value": 0}})
        == "0"
    )
