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


def test_committed_ledger_is_valid_and_honestly_open():
    module = _module()
    summary = module.validate_artifact(_document(module))
    assert summary.closed is False
    assert summary.non_encoded_reasons_complete is True


def test_closed_cannot_be_self_asserted():
    module = _module()
    document = _document(module)
    document["computed"]["closed"] = True
    with pytest.raises(ValueError, match="computed.closed is not derived"):
        module.validate_artifact(document)


def test_burndown_cannot_hide_an_open_family():
    module = _module()
    document = _document(module)
    document["computed"]["burndown"].pop()
    with pytest.raises(ValueError, match="computed.burndown is not derived"):
        module.validate_artifact(document)


def test_frontier_cannot_change_under_a_complete_label():
    module = _module()
    document = _document(module)
    document["computed"]["boundary_frontier"]["inputs"].pop()
    with pytest.raises(ValueError, match="boundary frontier inputs changed"):
        module.validate_artifact(document)


def test_declared_corpus_roots_reconcile():
    module = _module()
    document = _document(module)
    counts = document["computed"]["counts_by_status_per_root"]
    roots = document["generated_facts"]["corpus_roots"]
    for root in ("hts-rate-provisions", "chapter-99-notes"):
        assert sum(counts[root].values()) == roots[root]["declared_count"]


def test_program_rulespec_pin_cannot_be_mutated():
    module = _module()
    document = _document(module)
    document["program"]["rulespec_ref"] = "0" * 40
    with pytest.raises(ValueError, match="program source pin drift"):
        module.validate_artifact(document)


def test_corpus_blob_pin_cannot_be_mutated():
    module = _module()
    document = _document(module)
    document["generated_facts"]["corpus_roots"]["hts-rate-provisions"][
        "sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="generated corpus source pins changed"):
        module.validate_artifact(document)


def test_coordinated_rulespec_pin_mutation_cannot_self_validate():
    module = _module()
    document = _document(module)
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
    document = _document(module)
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
        (Path.home() / "TheAxiomFoundation/axiom-corpus/.git").exists()
        and (Path.home() / "TheAxiomFoundation/_b1wt/rulespec-us/.git").exists()
    ),
    reason="needs the local pinned corpus and RuleSpec Git object stores",
)
def test_full_reproduction_uses_pinned_git_objects():
    module = _module()
    result = module.verify_artifact()
    assert result.valid, result.errors
    assert result.document == result.expected
    assert result.expected["generated_facts"]["corpus_roots"][
        "hts-rate-provisions"
    ]["commit"] == module.CORPUS_REF
    assert result.expected["generated_facts"]["rulespec"]["commit"] == (
        module.RULESPEC_REF
    )


def test_full_reproduction_rejects_artifact_drift(tmp_path):
    module = _module()
    document = copy.deepcopy(_document(module))
    document["program"]["rulespec_ref"] = "0" * 40
    artifact = tmp_path / "mutant.yaml"
    artifact.write_text(yaml.safe_dump(document, sort_keys=False))
    result = module.verify_artifact(artifact_path=artifact)
    assert not result.valid
    assert "program source pin drift" in "; ".join(result.errors)
