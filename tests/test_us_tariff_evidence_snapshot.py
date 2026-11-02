"""Unit and mutant coverage for the frozen evidence-frontier contract."""

from pathlib import Path

import pytest

from scripts import us_tariff_evidence_snapshot as snapshot


def test_frontier_build_performs_live_reachable_input_reproduction(monkeypatch):
    calls = []

    def reproduce(**kwargs):
        calls.append(kwargs)
        return snapshot.AUDITED_REACHABLE_INPUTS

    monkeypatch.setattr(snapshot, "reproduce_input_inventory", reproduce)
    document = snapshot.build_frontier_inventory(
        verify_reachable_inputs=True,
        rulespec_repository=Path("configured-rulespec"),
        engine_repository=Path("configured-engine"),
        engine_executable=Path("configured-binary"),
    )

    assert calls == [
        {
            "rulespec_repository": Path("configured-rulespec"),
            "engine_repository": Path("configured-engine"),
            "engine_executable": Path("configured-binary"),
        }
    ]
    assert document["reachable_input_inventory_live_reproduced"] is True
    assert document["counts"]["reachable_inputs"] == 58


def test_frontier_build_rejects_reachable_input_mutant(monkeypatch):
    monkeypatch.setattr(
        snapshot,
        "reproduce_input_inventory",
        lambda **_kwargs: snapshot.AUDITED_REACHABLE_INPUTS[:-1],
    )

    with pytest.raises(ValueError, match="live reachable-input reproduction drift"):
        snapshot.build_frontier_inventory(verify_reachable_inputs=True)


def test_compiled_dependency_traversal_ignores_unreachable_inputs():
    program = {
        "derived": [
            {
                "name": "result",
                "expr": {"kind": "derived", "name": "helper"},
                "versions": [],
            },
            {
                "name": "helper",
                "expr": {"kind": "input", "name": "reachable"},
                "versions": [{"expr": {"kind": "input_or_else", "name": "versioned"}}],
            },
            {
                "name": "unused",
                "expr": {"kind": "input", "name": "unreachable"},
                "versions": [],
            },
        ]
    }

    assert snapshot.reachable_inputs_from_program(program, ["result"]) == {
        "reachable",
        "versioned",
    }


def test_external_roots_have_no_author_specific_fallback(monkeypatch):
    for name in (
        snapshot.CORPUS_ROOT_ENV,
        snapshot.RULESPEC_ROOT_ENV,
        snapshot.ENGINE_SOURCE_ROOT_ENV,
        snapshot.ENGINE_BINARY_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    assert snapshot.integration_configuration_available() is False
    with pytest.raises(snapshot.EvidenceConfigurationError, match="set .*CORPUS"):
        snapshot.corpus_root()


def test_frozen_engine_contract_binds_source_commit_and_binary_hash():
    inventory = snapshot.audited_input_inventory()
    assert inventory["engine_source_repository"] == (
        "TheAxiomFoundation/axiom-rules-engine"
    )
    assert inventory["engine_source_ref"] == (
        "ffd8213271947b0189a9dd61a055c1e0e78908a0"
    )
    assert inventory["engine_sha256"] == (
        "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
    )
