"""Live source receipts cannot accept HTTP errors or altered trusted content.

Only the canonical reproduction needs the frozen corpus checkout. Every tamper
case raises in build/verify_signature before the corpus is touched, so those
run hermetically against a tmp_path copy of the committed capture and an absent
tmp_path corpus root; a stub on subprocess.run fails any case that reaches the
corpus.
"""

import json
import subprocess
from pathlib import Path

import pytest

from scripts import us_tariff_live_source_evidence as source


class CorpusTouched(Exception):
    """Raised by the subprocess stub when verification reaches the corpus."""


@pytest.fixture
def absent_corpus(tmp_path, monkeypatch):
    """A corpus root that does not exist, guarded against any git call."""

    def reached_corpus(*args, **kwargs):
        raise CorpusTouched(kwargs.get("cwd"))

    monkeypatch.setattr(subprocess, "run", reached_corpus)
    return tmp_path / "absent-corpus"


def capture_copy(tmp_path: Path, replacements: dict[str, bytes]) -> Path:
    """The committed live capture, with named files replaced, under tmp_path."""
    directory = tmp_path / "live-sources"
    directory.mkdir()
    for path in source.DIRECTORY.iterdir():
        target = directory / path.name
        if path.name in replacements:
            target.write_bytes(replacements.pop(path.name))
        else:
            target.symlink_to(path)
    assert not replacements, f"no committed capture file named {set(replacements)}"
    return directory


@pytest.mark.skipif(
    not source.boundary.evidence_snapshot.integration_configuration_available(),
    reason="frozen corpus/RuleSpec/engine integrations are not configured",
)
def test_canonical_signature_and_live_pdf_bindings_reproduce():
    result = source.build(source.DIRECTORY, source.configured_corpus_root())
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


def test_committed_capture_passes_every_check_before_the_corpus(
    tmp_path, absent_corpus
):
    # Control for the tamper cases below: the untampered capture clears every
    # pre-corpus check and stops only when signature verification asks git
    # about the absent corpus.
    with pytest.raises(CorpusTouched) as reached:
        source.build(capture_copy(tmp_path, {}), absent_corpus)
    assert reached.value.args == (absent_corpus.resolve(),)


@pytest.mark.parametrize(
    "field,value",
    [
        ("http_code", 404),
        ("ssl_verify_result", 1),
        ("url_effective", "https://example.com/substitute"),
    ],
)
def test_untrusted_download_metadata_is_rejected(tmp_path, absent_corpus, field, value):
    altered = json.loads((source.DIRECTORY / "chapter99.curl.json").read_bytes())
    altered[field] = value
    directory = capture_copy(tmp_path, {"chapter99.curl.json": source.render(altered)})
    with pytest.raises(
        ValueError, match="HTTPS retrieval metadata mismatch: chapter99"
    ):
        source.build(directory, absent_corpus)


@pytest.mark.parametrize(
    "file,match",
    [
        ("chapter99.pdf", "PDF mismatch: chapter99"),
        ("general-note11.pdf", "PDF mismatch: general-note11"),
        ("original-ingest-manifest.json", "ingest manifest changed"),
        ("ingest_manifests.py", "verifier changed"),
    ],
)
def test_source_manifest_or_verifier_substitution_is_rejected(
    tmp_path, absent_corpus, file, match
):
    directory = capture_copy(tmp_path, {file: b"changed"})
    with pytest.raises(ValueError, match=match):
        source.build(directory, absent_corpus)


def test_untrusted_public_key_cannot_authenticate_manifest(tmp_path, absent_corpus):
    name = "corpus-ingest-public-key.json"
    altered = json.loads((source.DIRECTORY / name).read_bytes())
    altered["value"] = "untrusted replacement"
    directory = capture_copy(tmp_path, {name: source.render(altered)})
    with pytest.raises(ValueError, match="public-key digest"):
        source.build(directory, absent_corpus)
