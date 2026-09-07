"""Live source receipts cannot accept HTTP errors or altered trusted content."""

import json
from pathlib import Path

import pytest

from scripts import us_tariff_live_source_evidence as source


def test_canonical_signature_and_live_pdf_bindings_reproduce():
    result = source.build(source.DIRECTORY, source.boundary.closure.CORPUS)
    assert source.RECEIPT.read_bytes() == source.render(result)
    assert result["signature_verification"]["verified"] is True
    assert result["claim"]["certified"] is False
    for stem in source.DOWNLOADS:
        assert (
            "set-cookie:"
            not in (source.DIRECTORY / (stem + ".headers")).read_text().lower()
        )
        assert "local_ip" not in json.loads(
            (source.DIRECTORY / (stem + ".curl.json")).read_bytes()
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("http_code", 404),
        ("ssl_verify_result", 1),
        ("url_effective", "https://example.com/substitute"),
    ],
)
def test_untrusted_download_metadata_is_rejected(monkeypatch, field, value):
    target = source.DIRECTORY / "chapter99.curl.json"
    real = Path.read_bytes
    altered = json.loads(real(target))
    altered[field] = value
    monkeypatch.setattr(
        Path, "read_bytes", lambda p: source.render(altered) if p == target else real(p)
    )
    with pytest.raises(ValueError, match="HTTPS retrieval metadata"):
        source.build(source.DIRECTORY, source.boundary.closure.CORPUS)


@pytest.mark.parametrize(
    "file,match",
    [
        ("chapter99.pdf", "PDF mismatch"),
        ("general-note11.pdf", "PDF mismatch"),
        ("original-ingest-manifest.json", "ingest manifest changed"),
        ("ingest_manifests.py", "verifier changed"),
    ],
)
def test_source_manifest_or_verifier_substitution_is_rejected(monkeypatch, file, match):
    target = source.DIRECTORY / file
    real = Path.read_bytes
    monkeypatch.setattr(
        Path, "read_bytes", lambda p: b"changed" if p == target else real(p)
    )
    with pytest.raises(ValueError, match=match):
        source.build(source.DIRECTORY, source.boundary.closure.CORPUS)


def test_untrusted_public_key_cannot_authenticate_manifest(monkeypatch):
    target = source.DIRECTORY / "corpus-ingest-public-key.json"
    real = Path.read_bytes
    altered = json.loads(real(target))
    altered["value"] = "untrusted replacement"
    monkeypatch.setattr(
        Path, "read_bytes", lambda p: source.render(altered) if p == target else real(p)
    )
    with pytest.raises(ValueError, match="public-key digest"):
        source.build(source.DIRECTORY, source.boundary.closure.CORPUS)
