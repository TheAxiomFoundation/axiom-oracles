"""Mutants and hermetic checks for the DK executable producer."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "executable_reproduction.py"
ARTIFACT = REPO_ROOT / "conformance" / "executable" / "dk-boerne-og-ungeydelse.json"


def _load_script():
    spec = importlib.util.spec_from_file_location("executable_reproduction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_artifact_validates_hermetically():
    module = _load_script()
    document = json.loads(ARTIFACT.read_text())

    assert module.validate_artifact(document) == {
        "program_count": 2,
        "case_count": 10,
        "matched_case_count": 10,
        "all_cases_reproduced": True,
        "engine_binary_matches_pin": True,
        "executable": True,
    }
    assert document["rulespec"]["ref"] == document["rulespec"]["sha"]


def test_hermetic_validator_rejects_a_mutable_rulespec_ref():
    module = _load_script()
    document = json.loads(ARTIFACT.read_text())
    document["rulespec"]["ref"] = "main"

    with pytest.raises(ValueError, match="recorded rulespec.sha commit"):
        module.validate_artifact(document)


def test_exact_value_comparison_is_json_type_aware():
    module = _load_script()

    assert module._canonical_json(1) != module._canonical_json(1.0)


def test_tampered_committed_value_makes_check_red(tmp_path, monkeypatch, capsys):
    """A coherently relabeled expected value cannot survive ``--check``."""

    module = _load_script()
    reproduced = json.loads(ARTIFACT.read_text())
    mutant = copy.deepcopy(reproduced)
    witness = next(
        case for case in mutant["cases"] if case["case_id"].endswith("pension60000")
    )
    witness["committed_value"] += 1
    witness["match"] = False
    mutant["summary"].update(
        {
            "matched_case_count": 9,
            "all_cases_reproduced": False,
            "executable": False,
        }
    )
    mutant_path = tmp_path / "tampered-executable.json"
    mutant_path.write_text(json.dumps(mutant, indent=2, sort_keys=True) + "\n")

    calls = []

    def fake_reproduction(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(reproduced)

    monkeypatch.setattr(module, "build_reproduction", fake_reproduction)

    assert module.main(["--check", "--artifact", str(mutant_path)]) == 1
    assert len(calls) == 1, "--check must rerun before rejecting committed drift"
    assert calls[0]["rulespec_ref"] == reproduced["rulespec"]["sha"]
    assert "committed_value drifted" in capsys.readouterr().err
    with pytest.raises(ValueError, match="committed_value drifted"):
        module.validate_artifact(mutant)


def test_check_replays_the_recorded_commit_and_accepts_that_ref(monkeypatch, capsys):
    module = _load_script()
    committed = json.loads(ARTIFACT.read_text())
    recorded = committed["rulespec"]["sha"]
    calls = []

    def resolve_selected_ref(repo, ref):
        assert ref == recorded
        return recorded

    def fake_reproduction(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(committed)

    monkeypatch.setattr(module, "_resolve_git_commit", resolve_selected_ref)
    monkeypatch.setattr(module, "build_reproduction", fake_reproduction)

    assert (
        module.main(
            [
                "--check",
                "--artifact",
                str(ARTIFACT),
                "--rulespec-ref",
                recorded,
            ]
        )
        == 0
    )
    assert calls[0]["rulespec_ref"] == recorded
    assert "exact JSON numeric equality" in capsys.readouterr().out
