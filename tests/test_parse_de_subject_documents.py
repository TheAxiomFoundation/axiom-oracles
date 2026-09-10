"""Contract tests for the DE subject-document heading parser and its ledger
consumption: pure parsing on synthetic text, receipt/binding validation, and
document_heading candidates in the closure ledger."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SNAPSHOT = REPO_ROOT / "conformance" / "closure" / "de-instrument-graph.json"
HEADINGS = REPO_ROOT / "conformance" / "closure" / "de-subject-document-headings.json"


def _load(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SYNTHETIC = """DA-KG 2025 Titel

Inhaltsverzeichnis

Kapitel O  Organisation
     O1         Familienleistungsausgleich                                   13
     O 1.1      Allgemeines                                                  13
   A 2.1.9     Wiener Übereinkommen über diplomatische Beziehungen und übe
                Beziehungen                                                  40
   A5          Mitglieder und Beschäftigte diplomatischer Missionen sowie
                konsularischer Vertretungen und deren Angehörige
3
   V 18.1      Anwendungsbereich                                             96
Abkürzungsverzeichnis                                                       171

Kapitel O
O 1 Familienleistungsausgleich
Text of O 1 paragraph one.
O 1.1 Allgemeines
Text of O 1.1.
A 2.1.9 Wiener Übereinkommen über diplomatische Beziehungen
Diplomats text.
A 5 Mitglieder und Beschäftigte diplomatischer Missionen sowie
Members text.
V 18.1 Anwendungsbereich
Scope text.
Abkürzungsverzeichnis
"""


def test_parse_toc_joins_wrapped_entries_and_locates_every_section():
    parser = _load("parse_de_subject_documents")
    entries, start, end = parser.parse_toc(SYNTHETIC)
    assert [row["code"] for row in entries] == ["O 1", "O 1.1", "A 2.1.9", "A 5", "V 18.1"]
    wrapped = entries[2]
    assert wrapped["title"] == "Wiener Übereinkommen über diplomatische Beziehungen und übe Beziehungen"
    assert wrapped["toc_page"] == 40
    assert entries[3]["toc_page"] == 3
    rows = parser.locate_sections(SYNTHETIC, entries, end + 1)
    assert all(row["section_located"] for row in rows)
    o1, o11 = rows[0], rows[1]
    assert o1["section_line_start"] < o11["section_line_start"] == o1["section_line_end"]
    assert o1["body_sha256"] != o11["body_sha256"]
    assert parser.heading_id("de/kindergeld", "A 2.1.9") == "de-kg-dakg-A2.1.9"


def test_parse_toc_rejects_duplicates_and_unclosed_entries():
    parser = _load("parse_de_subject_documents")
    duplicated = SYNTHETIC.replace("     O 1.1      Allgemeines", "     O1         Allgemeines", 1)
    with pytest.raises(parser.ParseError, match="duplicate"):
        parser.parse_toc(duplicated)
    unclosed = SYNTHETIC.replace("   V 18.1      Anwendungsbereich                                             96", "   V 18.1      Anwendungsbereich")
    with pytest.raises(parser.ParseError, match="never closed"):
        parser.parse_toc(unclosed)


def test_build_document_refuses_bytes_that_do_not_match_the_snapshot_receipt():
    parser = _load("parse_de_subject_documents")
    snapshot, _raw = parser.load_snapshot(SNAPSHOT)
    with pytest.raises(parser.ParseError, match="do not match the snapshot receipt"):
        parser.build_document(
            snapshot=snapshot,
            program="de/kindergeld",
            subject_id="de-subject-003",
            pdf_bytes=b"not the retrieved document",
            text=SYNTHETIC,
            tool_version="test",
            page_count=1,
        )


def test_committed_headings_artifact_validates_against_the_committed_snapshot():
    parser = _load("parse_de_subject_documents")
    snapshot, raw = parser.load_snapshot(SNAPSHOT)
    payload = json.loads(HEADINGS.read_text())
    parser.validate_artifact(payload, snapshot, raw, "conformance/closure/de-instrument-graph.json")
    document = payload["documents"][0]
    assert document["subject_id"] == "de-subject-003"
    assert document["seed_candidate_id"] == "de-kg-instr-001"
    assert document["heading_count"] == 420 == document["sections_located"]
    assert document["extraction"]["tool"] == "pdftotext"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p["documents"][0].__setitem__("content_sha256", "0" * 64), "receipt mismatch"),
        (lambda p: p["snapshot"].__setitem__("sha256", "0" * 64), "does not bind the committed instrument snapshot"),
        (lambda p: p["documents"][0]["headings"][0].__setitem__("title", "forged"), "receipt mismatch"),
        (lambda p: p.__setitem__("extra", 1), "not canonical"),
    ],
)
def test_headings_artifact_mutants_are_rejected(mutate, message):
    parser = _load("parse_de_subject_documents")
    snapshot, raw = parser.load_snapshot(SNAPSHOT)
    payload = json.loads(HEADINGS.read_text())
    mutate(payload)
    with pytest.raises(parser.ParseError, match=message):
        parser.validate_artifact(payload, snapshot, raw, "conformance/closure/de-instrument-graph.json")


def test_reissued_receipts_cannot_launder_a_content_hash_change():
    """MUTANT: rehashing receipts after changing content_sha256 still fails
    the binding to the snapshot's retrieval receipt."""

    parser = _load("parse_de_subject_documents")
    snapshot, raw = parser.load_snapshot(SNAPSHOT)
    payload = json.loads(HEADINGS.read_text())
    payload["documents"][0]["content_sha256"] = "1" * 64
    payload["documents"][0] = parser._add_receipt(payload["documents"][0])
    payload = parser._add_receipt(payload)
    with pytest.raises(parser.ParseError, match="does not match the snapshot receipt"):
        parser.validate_artifact(payload, snapshot, raw, "conformance/closure/de-instrument-graph.json")


def test_ledger_consumes_heading_rows_as_pending_document_heading_candidates(tmp_path, monkeypatch):
    ledger = _load("de_closure_ledger")
    facts = ledger._snapshot_facts("de/kindergeld", SNAPSHOT, REPO_ROOT / "closure" / "de" / "source.json")
    kinds = {}
    for row in facts["candidates"]:
        kinds[row["identity_kind"]] = kinds.get(row["identity_kind"], 0) + 1
    assert kinds["document_heading"] == 420
    assert facts["candidate_count"] == len(facts["candidates"]) == 28 + 420
    assert [row["id"] for row in facts["candidates"]] == sorted(row["id"] for row in facts["candidates"])
    heading = next(row for row in facts["candidates"] if row["id"] == "de-kg-dakg-O2.1")
    assert heading["status"] == "pending"
    assert heading["discovery_refs"] == ["de-kg-instr-001", "de-subject-003"]
    assert heading["section_located"] is True and len(heading["body_sha256"]) == 64
    assert facts["document_headings"]["documents"][0]["heading_count"] == 420

    # Other programs are untouched by a kindergeld document.
    rv = ledger._snapshot_facts("de/rv-employee-contribution", SNAPSHOT, REPO_ROOT / "closure" / "de" / "source.json")
    assert "document_headings" not in rv
    assert all(row["identity_kind"] != "document_heading" for row in rv["candidates"])

    # Absent artifact: the pre-document frontier, byte for byte.
    monkeypatch.setattr(ledger, "HEADINGS_PATH", tmp_path / "missing.json")
    bare = ledger._snapshot_facts("de/kindergeld", SNAPSHOT, REPO_ROOT / "closure" / "de" / "source.json")
    assert bare["candidate_count"] == 28 and "document_headings" not in bare

    # A forged artifact fails closed in the ledger, not silently.
    forged = json.loads(HEADINGS.read_text())
    forged["documents"][0]["headings"][0]["body_sha256"] = "2" * 64
    forged_path = tmp_path / "forged.json"
    forged_path.write_text(json.dumps(forged))
    monkeypatch.setattr(ledger, "HEADINGS_PATH", forged_path)
    with pytest.raises(ledger._SourceError, match="headings artifact is invalid"):
        ledger._snapshot_facts("de/kindergeld", SNAPSHOT, REPO_ROOT / "closure" / "de" / "source.json")


def test_heading_dispositions_must_bind_the_section_text():
    ledger = _load("de_closure_ledger")
    facts = ledger._snapshot_facts("de/kindergeld", SNAPSHOT, REPO_ROOT / "closure" / "de" / "source.json")
    heading = next(row for row in facts["candidates"] if row["identity_kind"] == "document_heading")
    document = ledger.load_document(Path(ledger.ARTIFACT_PATHS["de/kindergeld"]))
    generated = document["generated_facts"]
    base = {
        "id": heading["id"],
        "status": "excluded-with-reason",
        "classification": "test_only",
        "reason": "synthetic",
        "bears_on_computed_surface": False,
    }
    for body, expected in ((None, "does not bind the captured instrument text"), ("3" * 64, "does not bind"), (heading["body_sha256"], None)):
        decision = dict(base)
        if body is not None:
            decision["body_sha256"] = body
        errors: list[str] = []
        ledger._canonical_decisions(
            {"instrument_dispositions": [decision]},
            spine=generated["provision_spine"],
            leaves=generated["leaf_frontier"],
            candidates=facts["candidates"],
            modules=generated["rulespec_modules"],
            errors=errors,
        )
        if expected is None:
            assert errors == []
        else:
            assert any(expected in error for error in errors), errors
