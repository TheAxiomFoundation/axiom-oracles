"""Mutant and reproduction gates for the U.S. tariff closure producer."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).parents[1]
SCRIPT = REPO / "scripts" / "us_tariff_closure.py"
REVIEWED_INPUT_SCOPES_SHA256 = (
    "13625d5f125cea50515552e197e3d899d7b59467a2b04d121b2e73a2fef040a8"
)
NOTE16_INPUT_SCOPES = {
    "entry_is_s232_note16_c_ii_derivative_aluminum_member": "note 16(c)(ii)",
    "entry_is_s232_note16_c_vi_derivative_aluminum_candidate": "note 16(c)(vi)",
    "entry_is_s232_note16_c_ix_derivative_aluminum_candidate": "note 16(c)(ix)",
    "entry_is_s232_note16_metal_chapter": "chapter 72, 73, 74, or 76",
    "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight": "real-entry determination",
}
REPAIRED_INPUT_SCOPE_MARKERS = {
    "cbp_agrees_chapter_98_entry_is_appropriate": "CBP acceptance",
    "entry_is_9802_excepted_entry": "9802.00.80",
    "entry_is_china_301_2024_action": "U.S. note 31",
    "entry_is_china_301_list123": "lists 1, 2, or 3",
    "entry_is_china_301_list4a": "list 4A",
    "entry_is_china_301_solar": "solar-products",
    "entry_is_entered_free_of_duty_under_usmca": "USMCA",
    "entry_is_humanitarian_donation_article": "humanitarian donation",
    "entry_is_informational_material_article": "informational material",
    "entry_is_line_a": "7202.11.10.00",
    "entry_is_line_b": "7601.10.30.00",
    "entry_is_line_d": "2203.00.00.30",
    "entry_is_personal_use_accompanied_baggage": "accompanied baggage",
    "entry_is_properly_claimed_chapter_98_entry": "Chapter 98 claim",
    "entry_is_section_122_exempt": "section 122",
    "entry_is_section_201_cspv": "CSPV",
    "entry_is_section_232_aluminum": "aluminum",
    "entry_is_section_232_steel": "steel",
    "entry_loaded_and_in_transit_before_july_24_2026": "July 24, 2026",
    "hts_line": "generated Rev-15 rate table",
    "resolved_non_ad_valorem_column2_rate": "non-ad-valorem column-2",
}


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


def _assert_reviewed_input_scope_contract(module):
    assert module.CANONICAL_INPUT_SCOPES_SHA256 == REVIEWED_INPUT_SCOPES_SHA256
    assert (
        module._input_scopes_sha256(module.CANONICAL_INPUT_SCOPES)
        == REVIEWED_INPUT_SCOPES_SHA256
    )


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


def test_frontier_exactly_matches_reachable_inputs_and_is_complete():
    module = _module()
    document = _expected_document(module)
    assert module.validate_artifact(document).closed is False
    frontier = document["computed"]["boundary_frontier"]
    assert frontier["complete"] is True
    assert frontier["input_count"] == 58
    assert frontier["required_input_count"] == 58
    assert frontier["missing_input_count"] == 0
    assert frontier["missing_inputs"] == []
    assert frontier["unexpected_input_count"] == 0
    assert frontier["unexpected_inputs"] == []
    inventory = document["committed_decisions"]["audited_input_inventory"]
    assert inventory["rulespec_ref"] == "4f591c4267063094cc6da9d590872ea982940b81"
    assert inventory["engine_sha256"] == (
        "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
    )
    assert inventory["inputs_sha256"] == (
        "10c812c01fd7c46b309d9cde66b30b6020acef05a5c9c8f0b97fb3e32ae773b1"
    )
    _assert_reviewed_input_scope_contract(module)
    assert inventory["input_scopes_sha256"] == REVIEWED_INPUT_SCOPES_SHA256
    assert frontier["scope_contract_complete"] is True
    assert frontier["input_scopes_sha256"] == inventory["input_scopes_sha256"]
    declared = [row["input"] for row in frontier["inputs"]]
    assert declared == inventory["inputs"]
    assert len(declared) == len(set(declared))


def test_repaired_input_scopes_name_their_exact_external_boundary():
    module = _module()
    frontier = {
        row["input"]: row
        for row in _expected_document(module)["computed"]["boundary_frontier"]["inputs"]
    }
    for name, marker in REPAIRED_INPUT_SCOPE_MARKERS.items():
        assert frontier[name]["grounding"] == "uncaptured"
        assert marker in frontier[name]["uncaptured_scope"]


def test_note16_entry_facts_are_scoped_and_uncaptured():
    module = _module()
    document = _expected_document(module)
    frontier = {
        row["input"]: row for row in document["computed"]["boundary_frontier"]["inputs"]
    }
    for name, scope in NOTE16_INPUT_SCOPES.items():
        assert frontier[name]["grounding"] == "uncaptured"
        assert scope in frontier[name]["uncaptured_scope"]
        assert name in module.AUDITED_REACHABLE_INPUTS
    threshold = frontier[
        "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight"
    ]["uncaptured_scope"]
    assert "Yale-model assumption" in threshold
    assert "not actual-entry proof" in threshold


@pytest.mark.parametrize("missing", NOTE16_INPUT_SCOPES)
def test_omitting_note16_scope_cannot_make_frontier_complete(monkeypatch, missing):
    module = _module()
    monkeypatch.setattr(
        module,
        "INPUTS",
        [(name, scope) for name, scope in module.INPUTS if name != missing],
    )
    document = _expected_document(module)
    frontier = document["computed"]["boundary_frontier"]
    assert missing in frontier["missing_inputs"]
    assert frontier["missing_input_count"] == 1
    assert frontier["unexpected_inputs"] == []
    assert frontier["complete"] is False
    assert module.validate_artifact(document).closed is False
    frontier["complete"] = True
    with pytest.raises(ValueError, match="frontier completeness is not derived"):
        module.validate_artifact(document)


def test_empty_scope_does_not_classify_a_reachable_input(monkeypatch):
    module = _module()
    missing = next(iter(NOTE16_INPUT_SCOPES))
    monkeypatch.setattr(
        module,
        "INPUTS",
        [(name, "" if name == missing else scope) for name, scope in module.INPUTS],
    )
    frontier = _expected_document(module)["computed"]["boundary_frontier"]
    assert missing in frontier["missing_inputs"]
    assert frontier["complete"] is False


def test_stale_alias_keeps_frontier_incomplete(monkeypatch):
    module = _module()
    stale = "section_232_membership"
    monkeypatch.setattr(
        module,
        "INPUTS",
        [*module.INPUTS, (stale, "stale generic alias")],
    )
    frontier = _expected_document(module)["computed"]["boundary_frontier"]
    assert frontier["missing_inputs"] == []
    assert frontier["unexpected_input_count"] == 1
    assert frontier["unexpected_inputs"] == [stale]
    assert frontier["complete"] is False


def test_duplicate_scope_row_keeps_frontier_incomplete(monkeypatch):
    module = _module()
    duplicate = module.INPUTS[0]
    monkeypatch.setattr(module, "INPUTS", [*module.INPUTS, duplicate])
    frontier = _expected_document(module)["computed"]["boundary_frontier"]
    assert frontier["duplicate_input_count"] == 1
    assert frontier["duplicate_inputs"] == [duplicate[0]]
    assert frontier["complete"] is False


def test_runtime_scope_mutation_forces_frontier_incomplete(monkeypatch):
    module = _module()
    mutated = "country_of_origin"
    monkeypatch.setattr(
        module,
        "INPUTS",
        [(name, "x" if name == mutated else scope) for name, scope in module.INPUTS],
    )
    document = _expected_document(module)
    frontier = document["computed"]["boundary_frontier"]
    assert frontier["missing_inputs"] == []
    assert frontier["unexpected_inputs"] == []
    assert frontier["duplicate_inputs"] == []
    assert frontier["scope_contract_complete"] is False
    assert (
        frontier["input_scopes_sha256"]
        != (
            document["committed_decisions"]["audited_input_inventory"][
                "input_scopes_sha256"
            ]
        )
    )
    assert frontier["complete"] is False
    assert module.validate_artifact(document).closed is False


def test_coordinated_scope_artifact_mutation_cannot_validate_as_complete():
    module = _module()
    document = _expected_document(module)
    mutated = "country_of_origin"
    for rows in (
        document["committed_decisions"]["input_grounding"],
        document["computed"]["boundary_frontier"]["inputs"],
    ):
        row = next(item for item in rows if item["input"] == mutated)
        row["uncaptured_scope"] = "x"

    frontier = document["computed"]["boundary_frontier"]
    mutated_rows = [
        (row["input"], row["uncaptured_scope"]) for row in frontier["inputs"]
    ]
    mutated_digest = module._input_scopes_sha256(mutated_rows)
    # Coordinate every artifact-level assertion an attacker could rewrite.
    # The source-pinned canonical contract remains independent.
    document["committed_decisions"]["audited_input_inventory"][
        "input_scopes_sha256"
    ] = mutated_digest
    frontier["input_scopes_sha256"] = mutated_digest
    frontier["scope_contract_complete"] = True
    frontier["complete"] = True
    assert mutated_digest != module.CANONICAL_INPUT_SCOPES_SHA256
    with pytest.raises(ValueError, match="committed closure decisions changed"):
        module.validate_artifact(document)


def test_canonical_scope_contract_definition_is_digest_pinned(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "CANONICAL_INPUT_SCOPES",
        tuple(
            (name, "x" if name == "country_of_origin" else scope)
            for name, scope in module.CANONICAL_INPUT_SCOPES
        ),
    )
    with pytest.raises(ValueError, match="canonical input-scope contract pin changed"):
        _expected_document(module)


def test_coordinated_scope_definition_and_digest_mutation_hits_reviewed_pin(
    monkeypatch,
):
    module = _module()
    mutated_rows = tuple(
        (name, "x" if name == "country_of_origin" else scope)
        for name, scope in module.CANONICAL_INPUT_SCOPES
    )
    mutated_digest = module._input_scopes_sha256(mutated_rows)
    assert mutated_digest != REVIEWED_INPUT_SCOPES_SHA256
    monkeypatch.setattr(module, "CANONICAL_INPUT_SCOPES", mutated_rows)
    monkeypatch.setattr(module, "CANONICAL_INPUT_SCOPES_SHA256", mutated_digest)
    monkeypatch.setattr(module, "INPUTS", list(mutated_rows))

    # The producer's coordinated internal objects are self-consistent; this
    # independently reviewed test literal remains the mutation-resistant pin.
    document = _expected_document(module)
    assert document["computed"]["boundary_frontier"]["complete"] is True
    with pytest.raises(AssertionError):
        _assert_reviewed_input_scope_contract(module)
    assert (
        document["committed_decisions"]["audited_input_inventory"][
            "input_scopes_sha256"
        ]
        == mutated_digest
    )


def test_policy_burndown_keeps_closure_open_after_frontier_completion():
    module = _module()
    document = _expected_document(module)
    assert document["computed"]["burndown"]
    assert document["computed"]["boundary_frontier"]["complete"] is True
    assert module.validate_artifact(document).closed is False
    document["computed"]["closed"] = True
    with pytest.raises(ValueError, match="computed.closed is not derived"):
        module.validate_artifact(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("rulespec_ref", "0" * 40),
        ("engine_sha256", "0" * 64),
        ("inputs_sha256", "0" * 64),
        ("input_scopes_sha256", "0" * 64),
        ("input_count", 57),
        ("inputs", []),
        ("promised_outputs", {"witness": [], "schedule": []}),
    ],
)
def test_audited_inventory_pin_cannot_be_rewritten(field, value):
    module = _module()
    document = _expected_document(module)
    document["committed_decisions"]["audited_input_inventory"][field] = value
    with pytest.raises(ValueError, match="committed closure decisions changed"):
        module.validate_artifact(document)


def test_coordinated_inventory_omission_cannot_self_validate():
    module = _module()
    document = _expected_document(module)
    frontier = document["computed"]["boundary_frontier"]
    inventory = document["committed_decisions"]["audited_input_inventory"]
    omitted = inventory["inputs"][-1]
    inventory["inputs"] = [name for name in inventory["inputs"] if name != omitted]
    inventory["input_count"] = len(inventory["inputs"])
    inventory["inputs_sha256"] = hashlib.sha256(
        ("\n".join(inventory["inputs"]) + "\n").encode()
    ).hexdigest()
    frontier.update(
        complete=True,
        required_input_count=inventory["input_count"],
        missing_input_count=0,
        missing_inputs=[],
        unexpected_input_count=1,
        unexpected_inputs=[omitted],
    )
    with pytest.raises(ValueError, match="frontier input set is not derived"):
        module.validate_artifact(document)


def test_audited_required_input_values_cannot_drift(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module, "AUDITED_REACHABLE_INPUTS", module.AUDITED_REACHABLE_INPUTS[:-1]
    )
    with pytest.raises(
        ValueError, match="audited reachable-input inventory pin changed"
    ):
        _expected_document(module)


def test_compiled_reachability_includes_all_versions_but_not_unused_imports():
    module = _module()
    program = {
        "derived": [
            {
                "name": "promised",
                "versions": [
                    {"expr": {"kind": "derived", "name": "historical_rule"}},
                    {"expr": {"kind": "derived", "name": "current_rule"}},
                ],
            },
            {"name": "historical_rule", "expr": {"kind": "input", "name": "old_fact"}},
            {
                "name": "current_rule",
                "expr": {
                    "kind": "input_or_else",
                    "name": "optional_fact",
                    "default": False,
                },
            },
            {"name": "unused_import", "expr": {"kind": "input", "name": "unused_fact"}},
        ]
    }
    assert module._reachable_inputs_from_program(program, ["promised"]) == {
        "old_fact",
        "optional_fact",
    }
    with pytest.raises(ValueError, match="missing or duplicate outputs"):
        module._reachable_inputs_from_program(program, ["absent_output"])


def test_input_inventory_reproduction_rejects_unpinned_engine(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_git", lambda *_: module.RULESPEC_REF.encode())
    with pytest.raises(ValueError, match="input inventory engine source pin drift"):
        module.reproduce_input_inventory(engine_binary=SCRIPT)


def test_build_cannot_skip_compiler_input_inventory_reproduction(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_blob_facts", lambda *_: ([], {}))
    monkeypatch.setattr(module, "_git", lambda *_: module.RULESPEC_REF.encode())

    def reject_inventory(**_):
        raise ValueError("compiler inventory verification failed")

    monkeypatch.setattr(module, "reproduce_input_inventory", reject_inventory)
    with pytest.raises(ValueError, match="compiler inventory verification failed"):
        module.build()


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
        "commit": "4f591c4267063094cc6da9d590872ea982940b81",
        "module_count": 415,
        "paths_sha256": (
            "4dcc60251e73e11ec25c0909c57aa523b46a50569bfec964545bb6c6adcef1e3"
        ),
    }
    assert document["generated_facts"]["corpus_roots"]["dr-cafta-general-note-29"] == {
        "path": module.GENERAL_NOTE_29,
        "commit": "cc18c703741425a3ebf994a2975cae158bd305d1",
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
        and (
            Path.home()
            / "TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine"
        ).is_file()
    ),
    reason="needs the local pinned corpus and RuleSpec Git object stores and engine",
)
def test_full_reproduction_uses_pinned_git_objects(tmp_path, monkeypatch):
    module = _module()
    compiled_paths = []
    real_run = module.subprocess.run

    def record_compile(command, *args, **kwargs):
        if command[1] == "compile":
            compiled_path = Path(command[command.index("--program") + 1])
            assert module.RULESPEC not in compiled_path.parents
            artifact_path = Path(command[command.index("--output") + 1])
            assert artifact_path.parent / "rulespec-us" in compiled_path.parents
            assert not artifact_path.exists()
            compiled_paths.append(compiled_path)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", record_compile)
    artifact = tmp_path / "us-tariff-duty.yaml"
    artifact.write_text(module.serialize(_expected_document(module)))
    result = module.verify_artifact(artifact_path=artifact)
    assert result.valid, result.errors
    assert result.document == result.expected
    assert len(compiled_paths) == 101
    assert all(not path.exists() for path in compiled_paths)
    assert result.expected["committed_decisions"]["audited_input_inventory"][
        "inputs"
    ] == (list(module.AUDITED_REACHABLE_INPUTS))
    assert result.expected["computed"]["boundary_frontier"]["missing_inputs"] == []
    assert result.expected["computed"]["boundary_frontier"]["unexpected_inputs"] == []
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
