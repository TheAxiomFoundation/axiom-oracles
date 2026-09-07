"""The original measurement audit survives only an exact metadata transformation."""

import json
from pathlib import Path

import pytest

from scripts import rebind_us_tariff_publication as rebind
from scripts import us_tariff_publication as publication

ROOT = Path(__file__).resolve().parents[1]


def test_live_rebind_is_exact_and_never_reads_bulk(monkeypatch):
    real_open = Path.open

    def bounded_open(path, *args, **kwargs):
        assert "c1-cache" not in path.parts
        assert path.stat().st_size < 20_000_000
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", bounded_open)
    rebind.check(ROOT)
    receipt = json.loads((ROOT / rebind.RECEIPT).read_text())
    assert len(receipt["ledger_hash_changes"]) == 39
    assert len(receipt["classification_input_hash_changes"]) == 3
    assert receipt["new_comparison_rows_scanned"] == 0
    assert receipt["preserved_comparison_units"] == 216_111_132
    assert receipt["preserved_mismatch_units"] == 6_807_741


def test_only_classification_provenance_changes():
    old = json.loads(
        (ROOT / rebind.BASELINE / "classification-receipt.json").read_text()
    )
    new = json.loads((ROOT / rebind.CLASSIFICATION).read_text())
    inputs = new.pop("inputs")
    old_inputs = old.pop("inputs")
    assert (
        new.pop("metadata_rebind")["audited_classification_sha256"]
        == rebind.BASELINE_HASHES["classification-receipt.json"]
    )
    assert old == new
    assert {key for key in inputs if inputs[key] != old_inputs[key]} == {
        "disposition_ledger_sha256",
        "preview_selector_transition_receipt_sha256",
        "preview_selector_transition_payload_sha256",
    }
    old_exercise = json.loads(
        (ROOT / rebind.BASELINE / "exercise-receipt.json").read_text()
    )
    new_exercise = json.loads((ROOT / rebind.EXERCISE).read_text())
    assert old_exercise["evidence_fields"] == new_exercise["evidence_fields"]
    assert old_exercise["cases"] == new_exercise["cases"] == 19_118_619
    old_exercise["report_sha256"] = new_exercise["report_sha256"]
    for old_row, new_row in zip(
        old_exercise["evidence_artifacts"],
        new_exercise["evidence_artifacts"],
        strict=True,
    ):
        if old_row["path"] == rebind.REPORT:
            old_row["sha256"] = new_row["sha256"]
    assert old_exercise == new_exercise


@pytest.mark.parametrize("name", list(rebind.BASELINE_HASHES))
def test_replacing_any_audited_baseline_is_rejected(monkeypatch, name):
    target = ROOT / rebind.BASELINE / name
    real_read = Path.read_bytes
    monkeypatch.setattr(
        Path, "read_bytes", lambda p: b"{}" if p == target else real_read(p)
    )
    with pytest.raises(ValueError, match="audited baseline changed"):
        rebind.build(ROOT)


@pytest.mark.parametrize(
    "relative",
    [
        rebind.LEDGER,
        rebind.CLASSIFICATION,
        rebind.REPORT,
        rebind.EXERCISE,
        rebind.RECEIPT,
    ],
)
def test_publication_gate_rejects_changed_or_missing_successor(relative, monkeypatch):
    snapshot = publication._Snapshot(ROOT)
    real_read = snapshot.read
    monkeypatch.setattr(
        snapshot, "read", lambda path: b"{}" if path == relative else real_read(path)
    )
    with pytest.raises(ValueError, match="metadata-rebound artifact drift"):
        publication._validate_metadata_rebind(snapshot)


def test_semantic_ledger_change_is_outside_rebind_contract(monkeypatch):
    real_render = rebind.ledger_rebind._render_rebound_ledger

    def mutate(*args):
        text, changed = real_render(*args)
        return text.replace("expected_units: 6\n", "expected_units: 7\n", 1), changed

    monkeypatch.setattr(rebind.ledger_rebind, "_render_rebound_ledger", mutate)
    with pytest.raises(ValueError, match="outside the 39 permitted"):
        rebind.build(ROOT)
