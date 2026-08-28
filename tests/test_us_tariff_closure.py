"""Mutant and reproduction gates for the U.S. tariff closure producer."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).parents[1]
SCRIPT = REPO / "scripts" / "us_tariff_closure.py"


def _module():
    spec = importlib.util.spec_from_file_location("us_tariff_closure_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _document(module):
    return yaml.safe_load(module.ARTIFACT.read_text())


def _expected_document(module):
    decisions, computed = module._decision_state(module.EXPECTED_SOURCE_COUNTS)
    return {
        "schema": module.SCHEMA,
        "program": copy.deepcopy(module.EXPECTED_PROGRAM),
        "generated_facts": {
            "corpus_roots": copy.deepcopy(module.EXPECTED_CORPUS_ROOTS),
            "rulespec": copy.deepcopy(module.EXPECTED_RULESPEC_FACTS),
        },
        "committed_decisions": decisions,
        "computed": computed,
    }


def test_committed_ledger_is_valid_and_honestly_open():
    module = _module()
    summary = module.validate_artifact(_document(module))
    assert summary.closed is False
    assert summary.non_encoded_reasons_complete is True


def test_closed_cannot_be_self_asserted():
    module = _module()
    document = _expected_document(module)
    document["computed"]["closed"] = True
    with pytest.raises(ValueError, match="computed.closed is not derived"):
        module.validate_artifact(document)


def test_burndown_cannot_hide_an_open_family():
    module = _module()
    document = _expected_document(module)
    document["computed"]["burndown"].pop()
    with pytest.raises(ValueError, match="computed.burndown is not derived"):
        module.validate_artifact(document)


def test_frontier_cannot_change_under_a_complete_label():
    module = _module()
    document = _expected_document(module)
    document["computed"]["boundary_frontier"]["inputs"].pop()
    with pytest.raises(ValueError, match="boundary frontier inputs changed"):
        module.validate_artifact(document)


def test_declared_corpus_roots_reconcile():
    module = _module()
    document = _expected_document(module)
    counts = document["computed"]["counts_by_status_per_root"]
    roots = document["generated_facts"]["corpus_roots"]
    for root in (
        "hts-rate-provisions",
        "chapter-99-notes",
        "dr-cafta-general-note-29",
    ):
        assert sum(counts[root].values()) == roots[root]["declared_count"]


def test_pinned_sources_capture_final_rulespec_and_general_note_29():
    module = _module()
    document = _expected_document(module)
    assert module.validate(document) == []
    assert document["generated_facts"]["rulespec"] == {
        "commit": "550818779a5fb0618e1374ed33bc471084c0b4ce",
        "module_count": 414,
        "paths_sha256": (
            "493113e001ab82a210c28b5a8d100a541905774f410d87861421de1ce87a2cea"
        ),
    }
    assert document["generated_facts"]["corpus_roots"]["dr-cafta-general-note-29"] == {
        "path": module.GENERAL_NOTE_29,
        "commit": "a664e437fafc7784f0a833abd76ddd16ea83686b",
        "sha256": ("3b3de5d98c81bad3cc560fcb738551591d7b7b5c080ca914718047a4a797368b"),
        "version": "2026-08-28-usitc-hts-2026-rev15-general-note-29",
        "declared_count": 93,
    }


def test_cafta_source_and_entry_facts_remain_explicitly_open():
    module = _module()
    document = _expected_document(module)
    ledger = {row["family"]: row for row in document["committed_decisions"]["ledger"]}
    assert ledger["note-29-d-v-textile-apparel-definition"]["status"] == (
        "partially-encoded"
    )
    assert ledger["note-29-origin-and-free-duty-remainder"]["status"] == ("pending")
    assert ledger["forced-labor-301"]["status"] == "partially-encoded"
    assert document["computed"]["closed"] is False

    frontier = {
        row["input"]: row for row in document["computed"]["boundary_frontier"]["inputs"]
    }
    assert "entry_is_general_note_29_d_v_textile_or_apparel_good" in frontier
    assert "entry_is_entered_free_of_duty_under_dr_cafta" in frontier
    assert (
        "uncaptured_scope"
        in frontier["entry_is_general_note_29_d_v_textile_or_apparel_good"]
    )
    assert (
        "uncaptured_scope" in frontier["entry_is_entered_free_of_duty_under_dr_cafta"]
    )


def test_note_50_52_precedence_is_composed_but_not_source_closed():
    module = _module()
    document = _expected_document(module)
    ledger = {row["family"]: row for row in document["committed_decisions"]["ledger"]}
    assert ledger["notes-50-52-section-232-sector-precedence"]["status"] == (
        "partially-encoded"
    )
    frontier = {
        row["input"] for row in document["computed"]["boundary_frontier"]["inputs"]
    }
    assert "entry_is_s232_note39_semiconductor_candidate" in frontier
    assert "entry_qualifies_for_note39_heading_9903_79_01" in frontier


def test_program_rulespec_pin_cannot_be_mutated():
    module = _module()
    document = _expected_document(module)
    document["program"]["rulespec_ref"] = "0" * 40
    with pytest.raises(ValueError, match="program source pin drift"):
        module.validate_artifact(document)


@pytest.mark.parametrize("root", ("hts-rate-provisions", "dr-cafta-general-note-29"))
def test_corpus_blob_pin_cannot_be_mutated(root):
    module = _module()
    document = _expected_document(module)
    document["generated_facts"]["corpus_roots"][root]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="generated corpus source pins changed"):
        module.validate_artifact(document)


def test_coordinated_rulespec_pin_mutation_cannot_self_validate():
    module = _module()
    document = _expected_document(module)
    mutant = "0" * 40
    document["program"]["rulespec_ref"] = mutant
    document["generated_facts"]["rulespec"]["commit"] = mutant
    document["generated_facts"]["rulespec"]["paths_sha256"] = "0" * 64
    document["generated_facts"]["corpus_roots"]["fr-instrument-families"][
        "rulespec_commit"
    ] = mutant
    with pytest.raises(ValueError, match="source pin"):
        module.validate_artifact(document)


def test_coordinated_closed_ledger_mutation_cannot_self_validate():
    module = _module()
    document = _expected_document(module)
    ledger = document["committed_decisions"]["ledger"]
    for row in ledger:
        if row["status"] in {"pending", "partially-encoded"}:
            row["status"] = "encoded"
    counts = {}
    for row in ledger:
        bucket = counts.setdefault(
            row["root"], {status: 0 for status in module.STATUSES}
        )
        bucket[row["status"]] += row["count"]
    document["computed"]["counts_by_status_per_root"] = counts
    document["computed"]["burndown"] = []
    document["computed"]["closed"] = True
    document["computed"]["instrument_frontier"] = {"complete": True, "open": []}
    document["computed"]["dependency_closure"] = {"complete": True, "open": []}
    with pytest.raises(ValueError, match="committed closure decisions changed"):
        module.validate_artifact(document)


@pytest.mark.skipif(
    not (
        (
            Path.home()
            / "TheAxiomFoundation/_worktrees/axiom-corpus-gn29-20260828/.git"
        ).exists()
        and (
            Path.home()
            / "TheAxiomFoundation/_worktrees/tariff-policy-combined-20260829/rulespec-us/.git"
        ).exists()
    ),
    reason="needs the local pinned corpus and RuleSpec Git object stores",
)
def test_full_reproduction_uses_pinned_git_objects(tmp_path):
    module = _module()
    artifact = tmp_path / "us-tariff-duty.yaml"
    artifact.write_text(module.serialize(_expected_document(module)))
    result = module.verify_artifact(artifact_path=artifact)
    assert result.valid, result.errors
    assert result.document == result.expected
    assert (
        result.expected["generated_facts"]["corpus_roots"]["hts-rate-provisions"][
            "commit"
        ]
        == module.CORPUS_REF
    )
    assert result.expected["generated_facts"]["rulespec"]["commit"] == (
        module.RULESPEC_REF
    )
    assert (
        result.expected["generated_facts"]["corpus_roots"]["dr-cafta-general-note-29"][
            "commit"
        ]
        == module.CORPUS_REF
    )


def test_full_reproduction_rejects_artifact_drift(tmp_path):
    module = _module()
    document = copy.deepcopy(_expected_document(module))
    document["program"]["rulespec_ref"] = "0" * 40
    artifact = tmp_path / "mutant.yaml"
    artifact.write_text(yaml.safe_dump(document, sort_keys=False))
    result = module.verify_artifact(artifact_path=artifact)
    assert not result.valid
    assert "program source pin drift" in "; ".join(result.errors)
