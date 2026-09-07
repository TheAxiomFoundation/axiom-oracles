"""Native errors are evidence of missing resolution, never substituted zero rates."""

import json
from pathlib import Path
from scripts import build_us_tariff_column2_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_source_binding_and_diagnostic_only_claims():
    d = receipt()
    assert d["producer_sha256"] == evidence.sources.sha(
        Path(evidence.__file__).read_bytes()
    )
    assert d["native_runtime_helper_sha256"] == evidence.sources.sha(
        Path(evidence.native.__file__).read_bytes()
    )
    assert d["runtime_helper_sha256"] == evidence.sources.sha(
        Path(runtime.__file__).read_bytes()
    )
    assert d["sources"] == evidence.source_evidence()
    assert d["fixtures"] == evidence.fixtures()
    assert all(row["valid_2026_entry_claim"] is False for row in d["fixtures"])
    assert d["validation"]["legal_resolved_rates_validated"] == 0
    assert all(value is False for value in d["claim"].values())


def test_missing_resolution_really_exited_with_error_for_each_column2_origin():
    d = receipt()
    failed = []
    checked = 0
    by_id = {row["case_id"]: row for row in d["fixtures"]}
    for run in d["native_runs"]:
        assert run["request_sha256"] == runtime.original.digest(
            runtime.original.canonical(run["request"])
        )
        if run["returncode"]:
            assert run["returncode"] == 1
            assert run["stdout"] == "" and run["response"] is None
            assert f"missing input `{evidence.INPUT}`" in run["stderr"]
            assert by_id[run["case_id"]]["expected_kind"] == "missing_input"
            assert evidence.INPUT not in by_id[run["case_id"]]["facts"]
            failed.append(by_id[run["case_id"]]["facts"]["country_of_origin"])
        else:
            assert run["response_sha256"] == runtime.original.digest(
                runtime.original.canonical(run["response"])
            )
            raw = run["response"]["results"][0]
            assert raw["entity_id"] == run["case_id"]
            actual = runtime.output(next(iter(raw["outputs"].values())))
            assert (
                actual == run["checked"]["actual"] == by_id[run["case_id"]]["expected"]
            )
            checked += 1
    assert (len(failed), checked) == (12, 29)
    assert {country: failed.count(country) for country in set(failed)} == {
        "CU": 3,
        "KP": 3,
        "BY": 3,
        "RU": 3,
    }


def test_dispositions_and_unused_branch_are_preserved():
    d = receipt()
    disposition = [
        row for row in d["native_runs"] if row["case_id"].startswith("disposition-")
    ]
    assert [row["checked"]["actual"] for row in disposition] == [
        "specific",
        "conditional",
        "conditional",
    ]
    controls = [
        row
        for row in d["fixtures"]
        if row["expected_kind"] == "diagnostic_general_control"
    ]
    assert len(controls) == 2 and all(
        evidence.INPUT not in row["facts"] for row in controls
    )
    assert d["scopes"][0]["grounding"] == "uncaptured"
    assert d["scopes"][0]["status"].startswith("blocked_on_external")
