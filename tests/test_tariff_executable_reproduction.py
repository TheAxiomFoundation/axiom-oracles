"""Hermetic validation and fail-closed mutants for the tariff receipt."""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts/tariff_executable_reproduction.py"
ARTIFACT = REPO_ROOT / "conformance/executable/us-tariff-witness.json"


def _module():
    spec = importlib.util.spec_from_file_location(
        "tariff_executable_reproduction", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_committed_tariff_receipt_validates_hermetically():
    module = _module()
    document = json.loads(ARTIFACT.read_text())

    assert module.validate_artifact(document) == {
        "program_count": 101,
        "case_count": 10,
        "matched_case_count": 10,
        "all_cases_reproduced": True,
        "engine_binary_matches_pin": True,
        "compile_replay_reproduced": True,
        "promised_output_coverage_complete": False,
        "executable": False,
        "blockers": [module.EXECUTION_COVERAGE_BLOCKER],
    }
    assert document["rulespec"]["ref"] == document["rulespec"]["sha"]
    assert document["program_set"] == module.PROGRAM_SET
    assert document["execution_scope"] == module.EXECUTION_SCOPE
    assert document["reproduction_contract"] == module.REPRODUCTION_CONTRACT
    provenance = document["engine"]["provenance"]
    assert provenance["identity"] == "sha256-only"
    assert provenance["published_provenance"] is False
    assert provenance["published_source_commit"] is None
    assert provenance["published_release_tag"] is None
    assert provenance["published_build_recipe"] is None
    assert all(
        row["compile_contract"] == module.COMPILE_CONTRACT
        and "AXIOM_RULESPEC_REPO_ROOTS" in row["compile_contract"]
        for row in document["compiled_artifacts"]
    )


def test_receipt_cannot_overstate_promised_output_execution():
    module = _module()
    document = json.loads(ARTIFACT.read_text())
    document["execution_scope"]["replayed_output_is_promised"] = True

    with pytest.raises(ValueError, match="execution scope"):
        module.validate_artifact(document)


def test_compiled_program_set_identity_cannot_drift():
    module = _module()
    document = json.loads(ARTIFACT.read_text())
    document["compiled_artifacts"][1]["promised_output"] = "different_output"

    with pytest.raises(ValueError, match="compiled program set drifted"):
        module.validate_artifact(document)


def test_program_set_summary_cannot_be_self_asserted():
    module = _module()
    document = json.loads(ARTIFACT.read_text())
    document["program_set"]["rows_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="program_set summary drifted"):
        module.validate_artifact(document)


def test_hash_shaped_compiled_artifact_mutation_fails_reviewed_pin():
    module = _module()
    document = json.loads(ARTIFACT.read_text())
    document["compiled_artifacts"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="reviewed producer pin"):
        module.validate_artifact(document)


def test_copied_or_changed_execution_result_fails_reviewed_trace_pin():
    module = _module()
    document = json.loads(ARTIFACT.read_text())
    document["cases"][0]["reproduced_value"] += 1
    document["cases"][0]["match"] = False

    with pytest.raises(ValueError, match="reviewed producer pin"):
        module.validate_artifact(document)


def test_certifier_reproduction_call_uses_pinned_defaults():
    module = _module()
    call = inspect.signature(module.build_reproduction).bind(
        repo_root=REPO_ROOT,
        rulespec_ref="0" * 40,
    )
    call.apply_defaults()

    assert call.arguments["rulespec_repo"] == module.DEFAULT_RULESPEC_ROOT
    assert call.arguments["engine_binary"] == module.DEFAULT_ENGINE_BINARY


def test_changed_reviewed_conformant_value_fails_closed():
    module = _module()
    mutant = json.loads(ARTIFACT.read_text())
    mutant["cases"][0]["committed_value"] += 1

    with pytest.raises(ValueError, match="committed_value drifted"):
        module.validate_artifact(mutant)


def test_changed_engine_hash_fails_closed():
    module = _module()
    mutant = json.loads(ARTIFACT.read_text())
    mutant["engine"]["binary_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="reviewed pin"):
        module.validate_artifact(mutant)


def test_changed_rulespec_sha_fails_closed():
    module = _module()
    mutant = json.loads(ARTIFACT.read_text())
    mutant["rulespec"]["sha"] = "0" * 40

    with pytest.raises(ValueError, match="reviewed pin"):
        module.validate_artifact(mutant)


def test_coordinated_rulespec_ref_and_sha_change_fails_reviewed_pin():
    module = _module()
    mutant = json.loads(ARTIFACT.read_text())
    mutant["rulespec"]["ref"] = "0" * 40
    mutant["rulespec"]["sha"] = "0" * 40

    with pytest.raises(ValueError, match="reviewed pin"):
        module.validate_artifact(mutant)


def test_source_report_metadata_change_fails_closed():
    module = _module()
    mutant = json.loads(ARTIFACT.read_text())
    mutant["source_reports"][0]["path"] = "different-source.txt"

    with pytest.raises(ValueError, match="source report identity"):
        module.validate_artifact(mutant)


def test_check_replays_recorded_commit_before_drift_rejection(tmp_path, monkeypatch):
    module = _module()
    committed = json.loads(ARTIFACT.read_text())
    mutant = copy.deepcopy(committed)
    mutant["cases"][0]["reproduced_value"] += 1
    mutant["cases"][0]["match"] = False
    mutant["summary"].update(
        matched_case_count=9, all_cases_reproduced=False, executable=False
    )
    artifact = tmp_path / "mutant.json"
    artifact.write_text(json.dumps(mutant))
    calls = []

    def fake_build(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(committed)

    monkeypatch.setattr(module, "build_reproduction", fake_build)
    assert module.main(["--check", "--artifact", str(artifact)]) == 1
    assert calls == []  # Hermetic validation rejects the bad receipt first.
