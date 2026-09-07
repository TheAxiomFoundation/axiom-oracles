"""Primary incidence must not be mistaken for UK metal-provenance qualification."""

import json
from pathlib import Path
from scripts import build_us_tariff_metal_evidence as evidence
from scripts import us_tariff_continuation_runtime as runtime


def receipt():
    return json.loads(evidence.OUTPUT.read_bytes())


def test_source_and_input_bindings():
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
    assert all(r["grounding"] == "uncaptured" for r in d["scopes"])


def test_native_metal_results_and_three_counterexamples_are_retained():
    d = receipt()
    matched = mismatched = outputs = 0
    for run in d["runs"]:
        for field in ("request", "response"):
            assert run[field + "_sha256"] == runtime.original.digest(
                runtime.original.canonical(run[field])
            )
        for raw, checked in zip(
            run["response"]["results"], run["results"], strict=True
        ):
            assert raw["entity_id"] == checked["case_id"]
            actual = {
                name.rsplit("#", 1)[-1]: runtime.output(value)
                for name, value in raw["outputs"].items()
            }
            assert checked["actual"] == actual
            differences = {
                name: {"expected": value, "actual": actual[name]}
                for name, value in checked["expected_from_source"].items()
                if actual[name] != value
            }
            assert checked["differences"] == differences
            assert checked["source_match"] is (not differences)
            outputs += len(actual)
            if differences:
                mismatched += 1
            else:
                matched += 1
    assert (matched, mismatched, outputs) == (25, 3, 44)
    assert len(d["known_mismatches"]) == 3
    assert d["validation"]["all_cases_match"] is False


def test_uk_provenance_threshold_changes_source_entitlement_but_is_not_an_input():
    d = receipt()
    rows = {r["case_id"]: r for r in d["fixtures"]}
    for key, output in ((7601103000, evidence.OUTS[0]), (7208103000, evidence.OUTS[1])):
        below = rows[f"metal-{key}-GB-94"]
        at = rows[f"metal-{key}-GB-95"]
        assert below["source_membership"] == at["source_membership"]
        assert below["expected_from_source"][output] == "0.5"
        assert at["expected_from_source"][output] == "0.25"
    for run in d["runs"]:
        names = {
            r["name"].rsplit(".", 1)[-1] for r in run["request"]["dataset"]["inputs"]
        }
        assert "stipulated_uk_qualifying_metal_percent" not in names
    assert all(r["matches_source_membership"] for r in d["adapter_results"])
    assert d["validation"]["new_campaign_rows_scanned"] == 0
