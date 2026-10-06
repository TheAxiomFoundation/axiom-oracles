"""Committed raw tariff captures must match every recorded digest, offline.

None of these tests needs the frozen corpus/RuleSpec/engine checkouts or
pdftotext, so they run in a clean CI checkout where the producer re-derivation
tests skip.
"""

import json
from pathlib import Path

import pytest

from scripts import build_us_tariff_china_action_evidence as china_action
from scripts import build_us_tariff_column2_evidence as column2
from scripts import build_us_tariff_identity_evidence as identity
from scripts import build_us_tariff_metal_evidence as metal
from scripts import build_us_tariff_temporal_evidence as temporal
from scripts import us_tariff_capture_integrity as integrity
from scripts import us_tariff_live_source_evidence as live

EVIDENCE = integrity.EVIDENCE_DIRECTORY


def evidence_copy(tmp_path: Path) -> Path:
    """A symlinked copy of the committed evidence tree that tests can tamper."""
    copy = tmp_path / "boundary-evidence"
    for path in sorted(EVIDENCE.rglob("*")):
        target = copy / path.relative_to(EVIDENCE)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(path)
    return copy


def replace(copy: Path, relative: str, body: bytes) -> None:
    target = copy / relative
    target.unlink()
    target.write_bytes(body)


def test_committed_captures_match_every_recorded_digest():
    assert integrity.check() == []


def test_capture_population_is_the_committed_source_directories():
    captures = integrity.capture_files(EVIDENCE)
    assert len(captures) == 40
    assert {Path(path).parts[0] for path in captures} == {
        "china-action-sources",
        "column2-sources",
        "identity-sources",
        "live-sources",
        "temporal-sources",
    }


def test_every_downloaded_capture_is_bound_by_its_producer_and_the_replay_manifest():
    documents, problems = integrity._documents(EVIDENCE)
    assert problems == []
    records, unresolved = integrity.collect_records(EVIDENCE, documents)
    assert unresolved == []
    recorders: dict[str, set[str]] = {}
    for record in records:
        recorders.setdefault(record.path, set()).add(record.recorded_by.split()[0])
    downloads = [
        path
        for path in integrity.capture_files(EVIDENCE)
        if path.endswith((".pdf", ".headers", ".curl.json"))
    ]
    assert len(downloads) == 30  # 10 downloads x (PDF, headers, curl metadata)
    for path in downloads:
        producers = recorders[path] - {integrity.CONTINUATION_MANIFEST}
        assert producers, f"{path} is bound only by the replay manifest"
        assert integrity.CONTINUATION_MANIFEST in recorders[path], path


def test_file_record_directories_are_the_producers_capture_directories():
    resolved = {
        (EVIDENCE / receipt).resolve(): (EVIDENCE / directory).resolve()
        for receipt, directory in integrity.FILE_RECORD_DIRECTORIES.items()
    }
    assert resolved == {
        china_action.OUTPUT.resolve(): china_action.DIRECTORY.resolve(),
        column2.OUTPUT.resolve(): column2.DIRECTORY.resolve(),
        identity.OUTPUT.resolve(): identity.DIRECTORY.resolve(),
        # The metal producer binds the identity capture's chapter72.pdf.
        metal.OUTPUT.resolve(): identity.DIRECTORY.resolve(),
        temporal.OUTPUT.resolve(): temporal.DIRECTORY.resolve(),
        live.RECEIPT.resolve(): live.DIRECTORY.resolve(),
    }


@pytest.mark.parametrize(
    "relative",
    [
        "identity-sources/chapter72.pdf",
        "temporal-sources/surcharge-2026.pdf",
        "china-action-sources/china-2024-action.pdf",
        "column2-sources/general-note3.headers",
        "live-sources/forced-labor-action.curl.json",
        "live-sources/general-note11.pdf",
        "live-sources/provisions.jsonl",
        "live-sources/ingest_manifests.py",
        "live-sources/original-ingest-manifest.json",
        "live-sources/corpus-ingest-public-key.json",
        "live-sources/receipt.json",
        "identity-sources/retrieval-times.json",
    ],
)
def test_appended_byte_in_any_capture_fails(tmp_path, relative):
    copy = evidence_copy(tmp_path)
    replace(copy, relative, (EVIDENCE / relative).read_bytes() + b"\n")
    problems = integrity.check(copy)
    assert any(p.startswith(f"{relative}: sha256 ") for p in problems), problems
    assert any(p.startswith(f"{relative}: ") and " bytes != " in p for p in problems)
    assert all(p.startswith(relative + ": ") for p in problems), problems


def test_same_size_byte_flip_fails_on_digest_alone(tmp_path):
    relative = "live-sources/chapter99.pdf"
    body = bytearray((EVIDENCE / relative).read_bytes())
    body[len(body) // 2] ^= 0x01
    copy = evidence_copy(tmp_path)
    replace(copy, relative, bytes(body))
    problems = integrity.check(copy)
    assert problems
    assert all(p.startswith(f"{relative}: sha256 ") for p in problems), problems


def test_missing_recorded_capture_fails(tmp_path):
    copy = evidence_copy(tmp_path)
    (copy / "identity-sources/chapter22.headers").unlink()
    problems = integrity.check(copy)
    assert problems
    assert all(
        p.startswith("identity-sources/chapter22.headers: recorded by ")
        and p.endswith(" but missing")
        for p in problems
    ), problems


@pytest.mark.parametrize(
    "relative",
    ["identity-sources/chapter85.pdf", "live-sources/notes.txt", "stray.pdf"],
)
def test_unrecorded_capture_fails(tmp_path, relative):
    copy = evidence_copy(tmp_path)
    (copy / relative).write_bytes(b"%PDF-unrecorded")
    assert integrity.check(copy) == [
        f"{relative}: capture file recorded by no receipt or manifest"
    ]


def test_manifest_edited_to_follow_a_tampered_capture_fails(tmp_path):
    relative = "identity-sources/chapter76.pdf"
    body = (EVIDENCE / relative).read_bytes() + b"\n"
    copy = evidence_copy(tmp_path)
    replace(copy, relative, body)
    name = integrity.CONTINUATION_MANIFEST
    replay = json.loads((EVIDENCE / name).read_bytes())
    replay["manifest"]["files"][integrity.EVIDENCE_PREFIX + relative] = {
        "bytes": len(body),
        "sha256": integrity.sha256(body),
    }
    replace(copy, name, integrity.render(replay))
    problems = integrity.check(copy)
    assert (
        f"{name}: verification.manifest_sha256 does not match the rendered manifest"
    ) in problems
    # The producer receipt still records the original bytes.
    assert any(
        p.startswith(f"{relative}: sha256 ") and "hts-identity.json" in p
        for p in problems
    )


@pytest.mark.parametrize(
    "document,match",
    [
        (
            {"sources": {"pdf": {"file": "chapter72.pdf", "sha256": "0" * 64}}},
            "file digest record in a receipt with no known capture directory",
        ),
        (
            {"sources": {"pdf": {"name": "chapter72.pdf", "sha256": "0" * 64}}},
            "digest field this check cannot resolve to a file",
        ),
        (
            {"sources": {"new_capture_sha256": "0" * 64}},
            "digest field this check cannot resolve to a file",
        ),
        (
            {"sources": {"metals_receipt_sha256": "0" * 64}},
            "unknown receipt digest field",
        ),
        (
            {"source": {"pdf_sha256": "0" * 64, "url": "https://example.com/x.pdf"}},
            "pdf_sha256 names no captured URL",
        ),
    ],
)
def test_unresolvable_digest_record_fails_closed(tmp_path, document, match):
    copy = evidence_copy(tmp_path)
    (copy / "new-receipt.json").write_bytes(integrity.render(document))
    problems = integrity.check(copy)
    assert len(problems) == 1, problems
    assert problems[0].startswith("new-receipt.json ")
    assert match in problems[0]


def test_url_bound_pdf_digest_is_checked(tmp_path):
    copy = evidence_copy(tmp_path)
    document = {
        "source": {
            "pdf_sha256": "0" * 64,
            "url": json.loads(
                (EVIDENCE / "live-sources/chapter99.curl.json").read_bytes()
            )["url_effective"],
        }
    }
    (copy / "new-receipt.json").write_bytes(integrity.render(document))
    problems = integrity.check(copy)
    assert len(problems) == 1, problems
    assert problems[0].startswith("live-sources/chapter99.pdf: sha256 ")
    assert "new-receipt.json $.source" in problems[0]


def test_cli_reports_clean_and_tampered_trees(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["us_tariff_capture_integrity.py"])
    assert integrity.main() == 0
    assert "40 committed capture files" in capsys.readouterr().out
    copy = evidence_copy(tmp_path)
    replace(copy, "identity-sources/chapter72.pdf", b"%PDF-substitute")
    monkeypatch.setattr(
        "sys.argv",
        ["us_tariff_capture_integrity.py", "--evidence-directory", str(copy)],
    )
    assert integrity.main() == 1
    assert "identity-sources/chapter72.pdf: sha256 " in capsys.readouterr().err
