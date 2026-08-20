"""Mutants proving the NZ subordinate-instrument frontier is rederived.

Each mutant is followed by restoration of the exact guarded input.  That
second assertion distinguishes a live guard from an unrelated test failure.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest


REPO = Path(__file__).resolve().parent.parent
SUMMARY = REPO / "closure" / "nz" / "summary.json"
INSTRUMENT_GRAPH = REPO / "conformance" / "closure" / "nz-instrument-graph.json"


def _load_nz_closure():
    spec = importlib.util.spec_from_file_location(
        "nz_closure_instrument_mutants", REPO / "scripts" / "nz_closure.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_nz_refresh():
    spec = importlib.util.spec_from_file_location(
        "refresh_nz_instrument_graph_test",
        REPO / "scripts" / "refresh_nz_instrument_graph.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _summary() -> dict:
    return json.loads(SUMMARY.read_text())


@contextmanager
def _repo_local_graph_copy(module, monkeypatch) -> Iterator[tuple[Path, bytes, dict]]:
    """Yield an exact graph copy and an artifact adjusted only for its path."""

    original = INSTRUMENT_GRAPH.read_bytes()
    with tempfile.TemporaryDirectory(prefix=".nz-instrument-mutant-", dir=REPO) as raw:
        graph_path = Path(raw) / INSTRUMENT_GRAPH.name
        graph_path.write_bytes(original)
        monkeypatch.setattr(module, "INSTRUMENT_GRAPH_PATH", graph_path)
        artifact = _summary()
        artifact["generated_facts"]["instrument_graph"]["snapshot_path"] = (
            graph_path.relative_to(REPO).as_posix()
        )
        yield graph_path, original, artifact


def test_committed_nz_instrument_frontier_rederives():
    module = _load_nz_closure()
    document = _summary()

    validated = module.validate_artifact(document, repo_root=REPO)
    assert validated == document
    assert validated.closed is False
    verification = module.verify_artifact(artifact_path=SUMMARY)
    assert verification.valid
    assert verification.document == document
    assert set(document["programs"]) == set(module.PROGRAM_INSTRUMENT_ACT)
    assert "instrument_frontier" in document["computed"]
    assert all(
        "instrument_frontier" in program
        for program in document["programs"].values()
    )
    frontiers = [
        document["computed"]["instrument_frontier"],
        *(program["instrument_frontier"] for program in document["programs"].values()),
    ]
    for frontier in frontiers:
        assert frontier["counts"]["total"] == len(frontier["ledger"])
        assert frontier["counts"]["pending"] == len(frontier["pending"])


def test_live_capture_derives_exact_metadata_from_instrument_xml():
    module = _load_nz_refresh()
    raw = (
        b'<regulation date.signed="2025-02-24" date.first.valid="2025-04-01" '
        b'date.terminated="nulldate" sr.type="regulation">'
        b"<cover><title>Accident Compensation (Earners' Levy) Regulations 2025"
        b"</title></cover><front><pursuant><para><text>Made under section 329 "
        b"of the Accident Compensation Act 2001</text></para></pursuant></front>"
        b"</regulation>"
    )

    class Response:
        content = raw

        @staticmethod
        def raise_for_status():
            return None

    class Session:
        @staticmethod
        def get(url, **_kwargs):
            assert url.endswith("/en/latest.xml")
            return Response()

    eli = (
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2025/18/en/latest/"
    )
    row = module._live_instrument_row(
        Session(),
        eli=eli,
        listing_title="",
        act=module.ACTS[2],
        status_as_of=dt.date(2026, 8, 19),
    )

    assert row["date_document"] == "2025-02-24"
    assert row["in_force"] is True
    assert row["type_document"] == "REGULATION"
    assert row["title_short"] == "SL 2025/18"
    assert row["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_live_listing_normalizes_classic_and_modern_links_to_one_eli():
    module = _load_nz_refresh()
    raw = b"""
      <a href="/regulation/public/2025/0018/latest/whole.html">legacy</a>
      <a href="/secondary-legislation/pco-drafted/2025/18/en/latest/">current</a>
    """
    assert module._extract_instrument_links(
        raw,
        "https://www.legislation.govt.nz/act/public/2001/49/en/latest/",
    ) == [
        (
            "https://www.legislation.govt.nz/secondary-legislation/"
            "pco-drafted/2025/18/en/latest/",
            "current",
        )
    ]


def test_removed_instrument_is_rejected_and_exact_graph_restores_guard(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_graph_copy(module, monkeypatch) as (
        graph_path,
        original,
        artifact,
    ):
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact

        mutant = json.loads(original)
        removed_index = next(
            index
            for index, row in enumerate(mutant["instruments"])
            if row["relation"] == "basis_for"
        )
        mutant["instruments"].pop(removed_index)
        graph_path.write_text(json.dumps(mutant, indent=2, sort_keys=True) + "\n")

        with pytest.raises(module.ClosureError, match="counts do not reconcile"):
            module.validate_artifact(artifact, repo_root=REPO)

        graph_path.write_bytes(original)
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact


def test_pending_count_regression_is_rejected_and_guard_reversion_passes():
    module = _load_nz_closure()
    document = _summary()
    assert module.validate_artifact(document, repo_root=REPO) == document

    mutant = copy.deepcopy(document)
    counts = mutant["computed"]["instrument_frontier"]["counts"]
    assert counts["pending"] > 0
    counts["pending"] -= 1

    with pytest.raises(module.ClosureError, match="does not rederive"):
        module.validate_artifact(mutant, repo_root=REPO)

    assert module.validate_artifact(document, repo_root=REPO) == document


def test_semantically_identical_snapshot_byte_edit_is_rejected_and_restores(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_graph_copy(module, monkeypatch) as (
        graph_path,
        original,
        artifact,
    ):
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact

        edited = original + b" "
        assert json.loads(edited) == json.loads(original)
        graph_path.write_bytes(edited)

        with pytest.raises(module.ClosureError, match="does not rederive"):
            module.validate_artifact(artifact, repo_root=REPO)

        graph_path.write_bytes(original)
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact
