"""Focused producer and mutant tests for the NZ PCO XML reverse index."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "nz_pco_reverse_index_test", REPO / "scripts" / "nz_pco_reverse_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source(number: int) -> dict:
    eli = (
        "https://www.legislation.govt.nz/secondary-legislation/"
        f"pco-drafted/2025/{number}/en/latest"
    )
    stem = f"secondary-legislation_pco-drafted_2025_{number}_en_2025-01-01"
    return {
        "legislation_status": "in_force",
        "legislation_type": "secondary_legislation",
        "metadata": {"publisher": "Parliamentary Counsel Office"},
        "relative_path": f"secondary-legislation/pco-drafted/2025/{number}/{stem}.xml",
        "title": f"Fixture {number}",
        "version_id": stem,
        "work_id": f"secondary-legislation_pco-drafted_2025_{number}",
        "xml_url": eli + ".xml",
    }


def _write_fixture(tmp_path: Path, module) -> tuple[Path, Path, Path, Path]:
    xml_root = tmp_path / "xml" / "secondary-legislation"
    matched_path = (
        xml_root
        / "pco-drafted"
        / "2025"
        / "1"
        / "secondary-legislation_pco-drafted_2025_1_en_2025-01-01.xml"
    )
    citation_only_path = (
        xml_root
        / "pco-drafted"
        / "2025"
        / "2"
        / "secondary-legislation_pco-drafted_2025_2_en_2025-01-01.xml"
    )
    matched_path.parent.mkdir(parents=True)
    citation_only_path.parent.mkdir(parents=True)
    matched_path.write_text(
        '<regulation date.signed="2025-01-01" date.first.valid="2025-01-01" '
        'date.terminated="nulldate" sr.type="regulation">'
        "<title>Fixture 1</title>"
        "<pursuant><text>Made under section 9 of Test Act 2020.</text></pursuant>"
        "</regulation>"
    )
    # A body/history citation is not an empowering edge.
    citation_only_path.write_text(
        '<regulation date.signed="2025-01-01" date.first.valid="2025-01-01" '
        'date.terminated="nulldate" sr.type="regulation">'
        "<title>Fixture 2</title>"
        "<pursuant><text>Made under Other Act 2019.</text></pursuant>"
        "<history-note><text>Test Act 2020</text></history-note>"
        "</regulation>"
    )

    manifest_path = tmp_path / "manifest-secondary_legislation.json"
    manifest_path.write_text(
        json.dumps(
            {
                "discovered_count": 2,
                "downloaded_count": 2,
                "failed_count": 0,
                "failures": [],
                "sources": [_source(1), _source(2)],
            }
        )
    )

    act = module.ACTS[0]
    graph_path = tmp_path / "nz-instrument-graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "retrieval_receipts": [
                    {
                        "act_citation_path": act.citation_path,
                        "reported_count": 1,
                        "captured_count": 1,
                        "unresolved_count": 0,
                    }
                ],
                "instruments": [
                    {
                        "eli": (
                            "https://www.legislation.govt.nz/secondary-legislation/"
                            "pco-drafted/2025/1/en/latest/"
                        ),
                        "act_eli": act.eli,
                        "act_citation_path": act.citation_path,
                        "date_document": "2025-01-01",
                        "in_force": True,
                        "relation": "basis_for",
                        "title": "Fixture 1",
                        "title_short": "SL 2025/1",
                        "type_document": "REGULATION",
                        "empowering_provisions": (
                            "Made under section 9 of Test Act 2020."
                        ),
                    }
                ],
            }
        )
    )
    return xml_root, manifest_path, graph_path, tmp_path / "reverse-index.json"


def test_pursuant_only_reverse_index_and_dropped_row_mutant(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "ACTS",
        (
            module.Act(
                title="Test Act 2020",
                year="2020",
                number="0001",
                citation_path="nz/statute/act/public/2020/0001",
                reported_count=1,
            ),
        ),
    )
    xml_root, manifest, graph, output = _write_fixture(tmp_path, module)
    arguments = [
        "--xml-root",
        str(xml_root),
        "--manifest",
        str(manifest),
        "--graph",
        str(graph),
        "--output",
        str(output),
    ]

    assert module.main(arguments) == 0
    baseline = output.read_bytes()
    artifact = json.loads(baseline)
    assert artifact["counts"] == {
        "xml_files_scanned": 2,
        "reported_listing_rows": 1,
        "bulk_xml_matches": 1,
        "already_in_instrument_graph": 1,
        "newly_resolved": 0,
        "pending_merges": 0,
        "remaining_capture_gap": 0,
    }
    assert len(artifact["rows"]) == 1
    assert artifact["rows"][0]["title"] == "Fixture 1"
    assert artifact["pending_disposition_rows"] == []
    assert module.main(["--check", *arguments]) == 0

    artifact["rows"].pop()
    output.write_bytes(module.serialize(artifact))
    assert module.main(["--check", *arguments]) == 1

    output.write_bytes(baseline)
    assert module.main(["--check", *arguments]) == 0


def test_new_reverse_edge_is_emitted_as_pending_b2_merge(tmp_path, monkeypatch):
    """MUTANT: a newly captured XML edge must survive reconciliation as pending."""

    module = _load_module()
    act = module.Act(
        title="Test Act 2020",
        year="2020",
        number="0001",
        citation_path="nz/statute/act/public/2020/0001",
        reported_count=2,
    )
    monkeypatch.setattr(module, "ACTS", (act,))
    xml_root, manifest, graph, output = _write_fixture(tmp_path, module)
    second = next(path for path in xml_root.rglob("*.xml") if "_2025_2_" in path.name)
    second.write_text(
        '<regulation date.signed="2025-01-01" date.first.valid="2025-01-01" '
        'date.terminated="nulldate" sr.type="order">'
        "<title>Fixture 2</title>"
        "<pursuant><text>Made under section 10 of Test Act 2020.</text></pursuant>"
        "</regulation>"
    )
    graph_document = json.loads(graph.read_text())
    graph_document["retrieval_receipts"][0].update(
        {"reported_count": 2, "captured_count": 1, "unresolved_count": 1}
    )
    graph.write_text(json.dumps(graph_document))

    assert (
        module.main(
            [
                "--xml-root",
                str(xml_root),
                "--manifest",
                str(manifest),
                "--graph",
                str(graph),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    artifact = json.loads(output.read_text())
    assert artifact["counts"] == {
        "xml_files_scanned": 2,
        "reported_listing_rows": 2,
        "bulk_xml_matches": 2,
        "already_in_instrument_graph": 1,
        "newly_resolved": 1,
        "pending_merges": 1,
        "remaining_capture_gap": 0,
    }
    pending = artifact["pending_disposition_rows"]
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"
    assert pending[0]["classification_owner"] == "B2"
    assert pending[0]["instrument_graph_row"]["title"] == "Fixture 2"
