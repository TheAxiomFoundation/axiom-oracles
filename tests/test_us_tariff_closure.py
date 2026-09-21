"""Mutant and reproduction gates for the U.S. tariff closure producer."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter
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


def _synthetic_rate_module(
    source_paths: list[str],
    proof_paths: list[str],
    *,
    omit_general_rate_key: int | None = None,
):
    keys = {
        path: int(path.split("/")[-1].replace(".", "").ljust(10, "0"))
        for path in source_paths
    }
    unique_keys = sorted(set(keys.values()))
    general_rates = {key: 0.1 for key in unique_keys}
    if omit_general_rate_key is not None:
        general_rates.pop(omit_general_rate_key)
    proof = {
        "proof": {
            "atoms": [
                {"source": {"corpus_citation_path": path}} for path in proof_paths
            ]
        }
    }
    return {
        "module": {
            "proof_validation": {"required": True},
            "source_verification": {"corpus_citation_paths": source_paths},
        },
        "rules": [
            {
                "name": "ch01_general_disposition",
                "metadata": proof,
                "versions": [{"values": {key: "ad_valorem" for key in unique_keys}}],
            },
            {
                "name": "ch01_column2_disposition",
                "versions": [{"values": {key: "ad_valorem" for key in unique_keys}}],
            },
            {
                "name": "ch01_general_rate",
                "versions": [{"values": general_rates}],
            },
            {
                "name": "ch01_column2_rate",
                "versions": [{"values": {key: 0.2 for key in unique_keys}}],
            },
        ],
    }


def _synthetic_schedule(paths: list[str]):
    return [
        {
            "citation_path": path,
            "body": "Rates of duty (1-General): 10%\nRates of duty (2): 20%",
        }
        for path in paths
    ]


def test_committed_ledger_is_valid_and_honestly_open():
    module = _module()
    document = _document(module)
    summary = module.validate_artifact(document)
    assert summary.closed is False
    assert summary.non_encoded_reasons_complete is True
    assert summary.boundary_frontier_complete is True
    assert summary.instrument_frontier_complete is False
    assert summary.open_dependency_count == 31
    contract = document["reproduction_contract"]
    assert contract == module.CLOSURE_REPRODUCTION_CONTRACT
    assert contract["repo_only"] is False
    assert contract["external_corpus_git_object"] == {
        "repository": "TheAxiomFoundation/axiom-corpus",
        "commit": module.CORPUS_REF,
        "required": True,
    }
    assert contract["external_rulespec_git_object"] == {
        "repository": "TheAxiomFoundation/rulespec-us",
        "commit": module.RULESPEC_REF,
        "required": True,
    }
    assert contract["external_engine_binary"] == {
        "sha256": module.INPUT_INVENTORY_ENGINE_SHA256,
        "required": True,
    }
    assert contract["engine_binary_provenance"]["identity"] == "sha256-only"
    assert contract["engine_binary_provenance"]["published_provenance"] is False


def test_closure_reproduction_contract_cannot_drift():
    module = _module()
    document = _document(module)
    document["reproduction_contract"]["repo_only"] = True

    with pytest.raises(ValueError, match="reproduction contract"):
        module.validate_artifact(document)


def test_compiler_frontier_is_exactly_typed():
    module = _module()
    document = _document(module)
    inventory = document["generated_facts"]["input_inventory"]
    frontier = document["computed"]["boundary_frontier"]

    assert inventory["input_count"] == 21
    assert inventory["inputs"] == list(module.AUDITED_REACHABLE_INPUTS)
    assert inventory["inputs_sha256"] == module.AUDITED_REACHABLE_INPUTS_SHA256
    assert frontier["compiled_input_count"] == 21
    assert frontier["execution_context_input_count"] == 1
    assert frontier["input_count"] == 22
    assert Counter(row["leaf_kind"] for row in frontier["inputs"]) == {
        "world_fact": 7,
        "law_derived": 15,
    }
    assert all(
        row["grounding"] == "runtime_required"
        for row in frontier["inputs"]
        if row["leaf_kind"] == "world_fact" and row.get("role") != "execution_context"
    )
    assert all(
        row["grounding"] == "uncaptured"
        for row in frontier["inputs"]
        if row["leaf_kind"] == "law_derived"
    )
    assert frontier["inputs"][-1] == {
        "input": "entry_date",
        "leaf_kind": "world_fact",
        "role": "execution_context",
        "grounding": "query_period",
        "reason": (
            "Axiom query period representing the entry date and effective-time context."
        ),
    }


def test_reachable_input_walk_uses_only_output_dependency_closure():
    module = _module()
    program = {
        "derived": [
            {
                "name": "target",
                "expr": {"kind": "derived", "name": "support"},
                "versions": [
                    {
                        "expr": {
                            "kind": "input_or_else",
                            "name": "versioned_input",
                            "fallback": 0,
                        }
                    }
                ],
            },
            {
                "name": "support",
                "expr": {"kind": "input", "name": "reachable"},
                "versions": [],
            },
            {
                "name": "unrelated",
                "expr": {"kind": "input", "name": "must_not_appear"},
                "versions": [],
            },
        ]
    }
    assert module._reachable_inputs_from_program(program, ["target"]) == {
        "reachable",
        "versioned_input",
    }


def test_compiler_frontier_rejects_untraversed_relations():
    module = _module()
    program = {
        "relations": [{"derivation": {"predicate": {"kind": "input", "name": "x"}}}],
        "derived": [{"name": "target", "expr": 0, "versions": []}],
    }
    with pytest.raises(ValueError, match="predicate inputs are not yet traversed"):
        module._reachable_inputs_from_program(program, ["target"])


def test_compiler_reachable_law_leaf_stays_open_despite_fake_binding():
    module = _module()
    inputs = module._input_grounding_rows()
    target = next(row for row in inputs if row["leaf_kind"] == "law_derived")
    frontier = {"ledger": []}

    target["grounding"] = "rulespec_derived"
    target["derivation_evidence"] = {
        "rulespec_ref": module.RULESPEC_REF,
        "module": "us/example.yaml",
        "rule": "example_membership",
        "module_sha256": "a" * 64,
    }
    closure = module._derive_dependency_closure(inputs, frontier)
    assert target["input"] in closure["law_derived_inputs"]
    assert closure["open_dependency_count"] == 15
    assert module._grounding_is_well_formed(target) is False


def test_chapter_99_root_is_not_reconciled_by_magic_subtraction():
    module = _module()
    document = _document(module)
    rows = [
        row
        for row in document["committed_decisions"]["ledger"]
        if row["root"] == "chapter-99-notes"
    ]
    assert rows == [
        {
            "root": "chapter-99-notes",
            "family": "all-chapter-99-pages",
            "status": "partially-encoded",
            "reason": (
                "Some Chapter 99 rules are composed, but no exact, disjoint "
                "citation-path census yet partitions all 805 source pages into "
                "encoded, excluded, and pending sets."
            ),
            "count": 805,
        }
    ]


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


def test_malformed_frontier_fails_closed_without_crashing():
    module = _module()
    document = _document(module)
    document["computed"]["boundary_frontier"] = 1
    with pytest.raises(ValueError, match="frontier"):
        module.validate_artifact(document)


def test_malformed_root_counts_fail_closed_without_type_error():
    module = _module()
    document = _document(module)
    document["computed"]["counts_by_status_per_root"]["hts-rate-provisions"][
        "encoded"
    ] = "8834"
    with pytest.raises(ValueError, match="declared root counts are malformed"):
        module.validate_artifact(document)


def test_generate_does_not_overwrite_artifact_when_validation_fails(
    tmp_path, monkeypatch
):
    module = _module()
    invalid = copy.deepcopy(_document(module))
    invalid["computed"]["closed"] = True
    artifact = tmp_path / "closure.yaml"
    artifact.write_text("preserve me\n")
    monkeypatch.setattr(module, "build", lambda **_kwargs: invalid)

    assert module.main(["--generate", "--artifact", str(artifact)]) == 1
    assert artifact.read_text() == "preserve me\n"


def test_law_derived_type_or_instrument_cannot_be_relabelled():
    module = _module()
    for mutation in ("leaf_kind", "derivation_instrument"):
        document = _document(module)
        row = next(
            item
            for item in document["computed"]["boundary_frontier"]["inputs"]
            if item["leaf_kind"] == "law_derived"
        )
        if mutation == "leaf_kind":
            row[mutation] = "world_fact"
        else:
            row[mutation] = "invented-instrument"
        with pytest.raises(ValueError, match="frontier inputs changed"):
            module.validate_artifact(document)


def test_declared_corpus_roots_reconcile():
    module = _module()
    document = _document(module)
    counts = document["computed"]["counts_by_status_per_root"]
    roots = document["generated_facts"]["corpus_roots"]
    for root in ("hts-rate-provisions", "chapter-99-notes"):
        assert sum(counts[root].values()) == roots[root]["declared_count"]


def test_rate_table_correspondence_binds_executable_partition():
    module = _module()
    document = _document(module)
    facts = document["generated_facts"]["rate_table_correspondence"]
    counts = document["computed"]["counts_by_status_per_root"]["hts-rate-provisions"]

    assert facts["partition_kind"] == "statutory-column-disposition"
    assert "not execution coverage" in facts["partition_limitation"]
    assert facts["encoded_count_interpretation"] == (
        "Static structural computability within the 100 chapter schedule "
        "programs in the multi-program ensemble; not execution coverage or a "
        "singular composed output."
    )
    assert facts["corpus_rate_bearing_count"] == 13_790
    assert facts["source_citation_count"] == 13_790
    assert facts["proof_citation_count"] == 13_790
    assert facts["general_rate_cell_count"] == 12_042
    assert facts["column2_rate_cell_count"] == 8_857
    assert counts == {
        "encoded": 8_834,
        "partially-encoded": 4_956,
        "excluded-with-reason": 16_055,
        "pending": 0,
    }
    encoded = next(
        row
        for row in document["committed_decisions"]["ledger"]
        if row["family"] == "fully-computable-rate-bearing-lines"
    )
    assert "statically and structurally computable" in encoded["reason"]
    assert "multi-program ensemble" in encoded["reason"]
    assert "not promised-output replay coverage" in encoded["reason"]


def test_closure_binds_and_discloses_the_multi_program_surface():
    module = _module()
    document = _document(module)
    assert document["program"]["scope"] == module.PROGRAM_SET_ID
    assert document["generated_facts"]["program_set"] == module.EXPECTED_PROGRAM_SET
    surface = document["computed"]["instrument_frontier"]["executable_surface"]
    assert surface["rows_sha256"] == module.PROGRAM_SET_ROWS_SHA256
    assert surface["program_count"] == 101
    assert surface["singular_composed_output"] is False
    assert surface["composition_identity_complete"] is False
    assert surface["closure_eligible"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("omitted-source", "source citations do not equal"),
        ("duplicate-source", "source citations are duplicated"),
        ("orphan-proof", "proof citations do not equal"),
        ("corpus-partition", "source citations do not equal"),
        ("omitted-rate-cell", "General rate keys do not equal"),
    ],
)
def test_rate_table_correspondence_mutants_fail_closed(mutation, message):
    module = _module()
    paths = ["us/statute/hts/0101.00.00", "us/statute/hts/0102.00.00"]
    schedule = _synthetic_schedule(paths)
    source_paths = list(paths)
    proof_paths = list(paths)
    omitted_rate_key = None
    if mutation == "omitted-source":
        source_paths.pop()
    elif mutation == "duplicate-source":
        source_paths.append(source_paths[0])
    elif mutation == "orphan-proof":
        proof_paths.append("us/statute/hts/0103.00.00")
    elif mutation == "corpus-partition":
        schedule[1]["body"] = "Structural heading without a statutory rate"
    elif mutation == "omitted-rate-cell":
        omitted_rate_key = int(paths[0].split("/")[-1].replace(".", "").ljust(10, "0"))
    rate_module = _synthetic_rate_module(
        source_paths,
        proof_paths,
        omit_general_rate_key=omitted_rate_key,
    )
    with pytest.raises(ValueError, match=message):
        module._derive_rate_table_correspondence(
            schedule,
            [("generated/ch01.yaml", rate_module)],
            rulespec_ref="a" * 40,
        )


def test_program_rulespec_pin_cannot_be_mutated():
    module = _module()
    document = _document(module)
    document["program"]["rulespec_ref"] = "0" * 40
    with pytest.raises(ValueError, match="program source pin drift"):
        module.validate_artifact(document)


def test_corpus_blob_pin_cannot_be_mutated():
    module = _module()
    document = _document(module)
    document["generated_facts"]["corpus_roots"]["hts-rate-provisions"]["sha256"] = (
        "0" * 64
    )
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


def test_instrument_graph_v1_cannot_assert_channel_complete(tmp_path, monkeypatch):
    module = _module()
    graph = json.loads(module.INSTRUMENT_GRAPH.read_text())
    graph["channels"][0]["state"] = "complete"
    mutant = tmp_path / "graph.json"
    raw = (json.dumps(graph, indent=2) + "\n").encode()
    mutant.write_bytes(raw)
    monkeypatch.setattr(
        module, "INSTRUMENT_GRAPH_SHA256", hashlib.sha256(raw).hexdigest()
    )
    with pytest.raises(ValueError, match="exact pending discovery channels"):
        module._load_instrument_graph(mutant)


def test_instrument_graph_v1_cannot_assert_instrument_disposition(
    tmp_path, monkeypatch
):
    module = _module()
    graph = json.loads(module.INSTRUMENT_GRAPH.read_text())
    graph["instruments"][0]["status"] = "encoded"
    mutant = tmp_path / "graph.json"
    raw = (json.dumps(graph, indent=2) + "\n").encode()
    mutant.write_bytes(raw)
    monkeypatch.setattr(
        module, "INSTRUMENT_GRAPH_SHA256", hashlib.sha256(raw).hexdigest()
    )
    with pytest.raises(ValueError, match="every candidate pending and bearing"):
        module._load_instrument_graph(mutant)


def test_instrument_graph_channel_ids_are_exact(tmp_path, monkeypatch):
    module = _module()
    graph = json.loads(module.INSTRUMENT_GRAPH.read_text())
    graph["channels"][0]["id"] = "invented-search-channel"
    mutant = tmp_path / "graph.json"
    raw = (json.dumps(graph, indent=2) + "\n").encode()
    mutant.write_bytes(raw)
    monkeypatch.setattr(
        module, "INSTRUMENT_GRAPH_SHA256", hashlib.sha256(raw).hexdigest()
    )
    with pytest.raises(ValueError, match="exact pending discovery channels"):
        module._load_instrument_graph(mutant)


def test_custom_instrument_graph_path_is_threaded_through_validation(tmp_path):
    module = _module()
    graph = tmp_path / "graph.json"
    graph.write_bytes(module.INSTRUMENT_GRAPH.read_bytes())
    document = _document(module)
    _, facts = module._load_instrument_graph(graph)
    document["generated_facts"]["instrument_graph"] = facts

    assert module.validate(document, instrument_graph_path=graph) == []
    summary = module.validate_artifact(document, instrument_graph_path=graph)
    assert summary.closed is False


def test_instrument_frontier_discloses_an_unknown_denominator():
    module = _module()
    frontier = _document(module)["computed"]["instrument_frontier"]
    assert "instrument_count" not in frontier
    assert "supplemental_count" not in frontier
    assert frontier["enumeration_scope"] == "seed-only-v1"
    assert frontier["enumerated_seed_candidate_count"] == 16
    assert len(frontier["pending_enumerated_seed_candidates"]) == 16
    assert frontier["discovery_channel_count"] == 4
    assert len(frontier["pending_discovery_channels"]) == 4
    assert frontier["additional_known_families_open"] is True
    assert frontier["denominator_status"] == "unknown"


def test_forged_dependency_count_cannot_flip_closure():
    module = _module()
    document = _document(module)
    dependency = document["computed"]["dependency_closure"]
    dependency["law_derived_inputs"] = []
    dependency["instruments_bearing_on_computed"] = []
    dependency["open_dependency_count"] = 0
    dependency["closed"] = True
    document["computed"]["closed"] = True
    with pytest.raises(ValueError, match="dependency closure is not derived"):
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
    assert (
        result.expected["generated_facts"]["corpus_roots"]["hts-rate-provisions"][
            "commit"
        ]
        == module.CORPUS_REF
    )
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
