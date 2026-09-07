"""Adversarial checks for the source-linked, synthetic boundary receipt."""

import json
from pathlib import Path

import pytest

from scripts import build_us_tariff_boundary_evidence as evidence


def receipt():
    return json.loads(evidence.OUTPUT.read_text())


def test_truth_table_is_exhaustive_and_retains_the_9802_exception():
    rows = evidence.fixture_rows()
    assert len(rows) == len({row["case_id"] for row in rows}) == 192
    for origin in evidence.ORIGINS:
        group = [row for row in rows if row["origin"] == origin]
        assert len(group) == 64
        assert sum(row["expected"][evidence.OUTPUT_NAMES[0]] for row in group) == 57
        for name in evidence.INPUTS:
            assert {row["flags"][name] for row in group} == {False, True}
    cn = {
        row["case_id"].split("-")[-1]: row["expected"]
        for row in rows
        if row["origin"] == "CN"
    }
    judgment, rate = evidence.OUTPUT_NAMES
    # Claim alone and acceptance alone are insufficient; both are required.
    assert cn["000100"][rate] == cn["000010"][rate] == 0.1
    assert cn["000110"] == {judgment: True, rate: 0.0}
    # 9802 restores the rate, but does not defeat an independent donation.
    assert cn["000111"] == {judgment: False, rate: 0.1}
    assert cn["100111"] == {judgment: True, rate: 0.0}


def test_receipt_matches_fixed_sources_and_never_upgrades_grounding():
    document = receipt()
    assert document["producer_sha256"] == evidence.digest(
        Path(evidence.__file__).read_bytes()
    )
    assert document["fixture_rows"] == evidence.fixture_rows()
    assert document["scopes"] == evidence.boundary_scopes()
    assert document["limitations"] == evidence.LIMITATIONS
    assert document["source"]["pdf"]["sha256"] == evidence.PDF_SHA256
    assert document["source"]["authoritative_url"] == evidence.SOURCE_URL
    assert document["claim"] == {
        "kind": "bounded_source_and_runtime_evidence",
        "actual_entry_grounding": "uncaptured",
        "closed": False,
        "certified": False,
        "release_authorized": False,
    }
    assert (
        document["source"]["ingest_manifest"]["trusted_signature_verification"]
        == "not_performed"
    )
    for row in document["scopes"]:
        assert row["actual_entry_blocker"]
        assert row["grounding"] == "uncaptured"


def test_saved_runtime_vectors_and_exact_day_requests_reconcile():
    document = receipt()
    positive = 0
    for module, run in zip(evidence.MODULES, document["runs"], strict=True):
        request = evidence.execution_request(module, document["fixture_rows"])
        assert run["request"] == request
        assert evidence.digest(evidence.canonical(request)) == run["request_sha256"]
        assert (
            evidence.digest(evidence.canonical(run["response"]))
            == run["response_sha256"]
        )
        assert (
            evidence.check_results(run["response"], request, document["fixture_rows"])
            == run["checked_results"]
        )
        assert len(run["checked_results"]) == 192
        for row in run["checked_results"]:
            positive += float(row["actual"][evidence.OUTPUT_NAMES[1]]) > 0
    assert positive == document["validation"]["positive_rate_cases"] == 28


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("drop_case", "cardinality"),
        ("duplicate_identity", "identity"),
        ("wrong_period", "period"),
        ("missing_output", "population"),
        ("wrong_rate", "rate mismatch"),
        ("wrong_judgment", "judgment mismatch"),
        ("wrong_rate_type", "invalid runtime rate"),
    ],
)
def test_runtime_evidence_mutants_fail_closed(mutation, match):
    document = receipt()
    run = document["runs"][0]
    payload = run["response"]
    row = payload["results"][0]
    names = run["request"]["queries"][0]["outputs"]
    if mutation == "drop_case":
        payload["results"].pop()
    elif mutation == "duplicate_identity":
        payload["results"][1]["entity_id"] = row["entity_id"]
    elif mutation == "wrong_period":
        row["period"]["end"] = "2027-02-15"
    elif mutation == "missing_output":
        row["outputs"].pop(names[0])
    elif mutation == "wrong_rate":
        row["outputs"][names[1]]["value"]["value"] = "0"
    elif mutation == "wrong_judgment":
        row["outputs"][names[0]]["outcome"] = "holds"
    elif mutation == "wrong_rate_type":
        row["outputs"][names[1]]["value"]["kind"] = "bool"
    with pytest.raises(ValueError, match=match):
        evidence.check_results(payload, run["request"], document["fixture_rows"])


def test_wrong_engine_rejected_before_compilation(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "source_evidence", lambda _: {})
    fake = tmp_path / "engine"
    fake.write_text("not the pinned runtime")
    with pytest.raises(ValueError, match="engine pin"):
        evidence.build(engine=fake)


def test_source_substitution_rejected_before_evidence_claim(monkeypatch):
    monkeypatch.setattr(
        evidence, "git_bytes", lambda *args: b'{"body":"different source"}\n'
    )
    with pytest.raises(ValueError, match="notes digest"):
        evidence.source_evidence(Path("unused"))


def test_source_table_link_and_page_are_preserved():
    source = receipt()["source"]
    records = {
        row["record"]["citation_path"]: row["record"] for row in source["records"]
    }
    note = records["us/statute/hts/chapter-99/page-176"]
    table = records["us/statute/hts/chapter-99/page-598"]
    assert note["metadata"]["page_number"] == 176
    assert "whenever CBP agrees" in note["body"]
    assert "except for goods entered under heading 9802.00.80" in note["body"]
    assert "except to the extent that the President determines" in note["body"]
    assert "9903.01.22" in table["body"] and "informational materials" in table["body"]
    assert {row["source_url"] for row in records.values()} == {evidence.SOURCE_URL}
