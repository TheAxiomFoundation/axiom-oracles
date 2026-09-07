"""Fail-closed tests for the small steel-scope causal proof consumer."""

from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path
import shutil

import pytest

from scripts import build_us_tariff_steel_scope_projection_receipt as proof


@pytest.fixture(scope="module")
def artifact() -> dict:
    # This deliberately frozen proof is independent of the changing live
    # classification/report. Full producer --check separately replays its data.
    return proof.foundation.load_json(proof.DEFAULT_OUTPUT)


def rehash(document: dict) -> None:
    document.pop("receipt_payload_sha256", None)
    document["receipt_payload_sha256"] = proof.canonical_sha256(document)


def change(document: dict, path: tuple, replacement) -> None:
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


def test_committed_proof_has_exact_bounded_classes(artifact):
    assert proof.validate_artifact(artifact) is artifact
    assert [
        (row["id"], row["expected_units"], row["expected_signature_count"])
        for row in artifact["classes"]
    ] == [
        ("section232-steel-scope-projection-brazil", 6, 3),
        ("section232-steel-scope-projection-forced-labor", 108, 54),
    ]
    assert all(
        row["disposition"] == "explained_residual"
        and row["attribution"] == "input-comparability"
        for row in artifact["classes"]
    )
    assert len(artifact["cases"]) == 110
    assert len(artifact["units"]) == 114
    assert artifact["replay"]["baseline_exact_recorded_output_values"] == 1210
    assert artifact["replay"]["counterfactual_exact_target_units"] == {
        "brazil_section_301": 6,
        "forced_labor_section_301": 108,
    }
    assert artifact["replay"]["counterfactual_other_slot_mismatches"] == {
        "base": 4,
        "total": 4,
    }
    assert artifact["replay"]["whole_case_parity_claimed"] is False


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("schema",), "axiom_oracles.us_tariff_schedule.steel_scope_projection.v0"),
        (("verdict",), "FAIL"),
        (("bindings", "run_identity_sha256"), "0" * 64),
        (("bindings", "generation_id"), "0" * 32),
        (("bindings", "identity_population_sha256"), "0" * 64),
        (("bindings", "signature_population_sha256"), "0" * 64),
        (("producer", "script", "sha256"), "0" * 64),
        (("inputs", "comparison_artifact", "sha256"), "0" * 64),
        (("inputs", "historical_artifact", "sha256"), "0" * 64),
        (("inputs", "evaluation_manifest", "sha256"), "0" * 64),
        (("inputs", "input_contract", "sha256"), "0" * 64),
        (("source_identity", "engine", "sha256"), "0" * 64),
        (("source_identity", "rulespec", "head_commit"), "0" * 40),
        (("source_identity", "yale", "commit"), "0" * 40),
        (("source_identity", "yale", "files", 0, "sha256"), "0" * 64),
        (("source_identity", "entry_flag_producers", "producer_sha256"), "0" * 64),
        (("source_facts", "winner", "tier"), "annex_1b"),
        (("source_facts", "legacy_steel_row", "effective_date"), "2026-08-03"),
        (("source_facts", "yale_selection"), "Choose a separate tier for every metal."),
        (("limitations", "vintage"), "Steel first became covered on 2026-08-03."),
        (("limitations", "coverage"), "All actual transaction facts are covered."),
        (("shards", 0, "sha256"), "0" * 64),
        (("shards", 0, "cases"), 1),
        (("census", "evaluated_records"), 19_118_618),
        (("census", "historical_records"), 395_329),
        (("census", "new_target_units"), 113),
        (("census", "new_unique_cases"), 109),
        (("census", "new_signatures"), 56),
        (("census", "new_historical_key_overlap"), 1),
        (("census", "engine_errors"), 1),
        (("census", "duplicate_evaluation_case_ids"), False),
        (("classes", 0, "expected_units"), 7),
        (("classes", 0, "expected_signature_count"), 4),
        (("classes", 0, "expected_signature_population_sha256"), "0" * 64),
        (("classes", 0, "identity_population_sha256"), "0" * 64),
        (("classes", 0, "signatures", 0), "0" * 64),
        (("classes", 0, "disposition"), "reference_defect"),
        (("classes", 0, "attribution"), "yale"),
        (("cases", 0, "recorded_evaluation", "probe"), "2026-08-02"),
        (("cases", 0, "recorded_evaluation", "case_id"), "schedule-" + "0" * 24),
        (("cases", 0, "recorded_evaluation", "hts10"), "9403999040"),
        (("cases", 0, "recorded_evaluation", "engine_errors"), ["failed"]),
        (
            (
                "cases",
                0,
                "recorded_evaluation",
                "actual",
                "section_232_steel_component_rate",
            ),
            0.0,
        ),
        (("cases", 0, "baseline_inputs", "entry_is_section_232_steel"), False),
        (("cases", 0, "baseline_inputs", "entry_is_section_232_covered"), False),
        (("cases", 0, "baseline_inputs", "country_of_origin"), "GB"),
        (("cases", 0, "counterfactual_inputs", "entry_is_section_232_steel"), True),
        (
            (
                "cases",
                0,
                "counterfactual_inputs",
                "entry_is_entered_free_of_duty_under_dr_cafta",
            ),
            True,
        ),
        (("cases", 0, "baseline_outputs", "section_232_steel_component_rate"), 0.0),
        (
            (
                "cases",
                0,
                "counterfactual_outputs",
                "forced_labor_section_301_component_rate",
            ),
            0.0,
        ),
        (("units", 0, "identity", "expected"), 99.0),
        (("units", 0, "signature"), "0" * 64),
        (("replay", "compiled_artifact_sha256"), "0" * 64),
        (("replay", "baseline_exact_recorded_output_values"), 1209),
        (
            ("replay", "counterfactual_exact_target_units", "forced_labor_section_301"),
            107,
        ),
        (("replay", "whole_case_parity_claimed"), True),
        (("replay", "counterfactual_other_slot_mismatches", "base"), 0),
    ],
)
def test_rehashed_mutants_cannot_redefine_proof(artifact, path, replacement):
    mutant = deepcopy(artifact)
    change(mutant, path, replacement)
    assert proof.canonical_sha256(mutant) != proof.canonical_sha256(artifact), path
    rehash(mutant)
    with pytest.raises(ValueError):
        proof.validate_artifact(mutant)


@pytest.mark.parametrize("field", ["cases", "units", "classes", "shards"])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "reverse"])
def test_missing_duplicate_or_reordered_populations_fail(artifact, field, mutation):
    mutant = deepcopy(artifact)
    if mutation == "drop":
        mutant[field].pop()
    elif mutation == "duplicate":
        mutant[field].append(deepcopy(mutant[field][0]))
    else:
        mutant[field].reverse()
    rehash(mutant)
    with pytest.raises(ValueError):
        proof.validate_artifact(mutant)


def test_coherently_rehashed_fabricated_case_is_not_a_trusted_population(artifact):
    mutant = deepcopy(artifact)
    case = mutant["cases"][0]
    old_id = case["recorded_evaluation"]["case_id"]
    new_id = "schedule-" + "0" * 24
    case["recorded_evaluation"]["case_id"] = new_id
    for unit in mutant["units"]:
        if unit["identity"]["case_id"] == old_id:
            unit["identity"]["case_id"] = new_id
    mutant["cases"].sort(key=lambda c: c["recorded_evaluation"]["case_id"])
    mutant["bindings"]["identity_population_sha256"] = proof.population_sha256(
        u["identity"] for u in mutant["units"]
    )
    mutant["replay"]["recorded_evaluation_population_sha256"] = proof.population_sha256(
        c["recorded_evaluation"] for c in mutant["cases"]
    )
    rehash(mutant)
    with pytest.raises(ValueError):
        proof.validate_artifact(mutant)


def test_payload_digest_is_mandatory(artifact):
    mutant = deepcopy(artifact)
    mutant["receipt_payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="payload digest"):
        proof.validate_artifact(mutant)


def test_downstream_inputs_cannot_be_added_to_proof(artifact):
    mutant = deepcopy(artifact)
    mutant["inputs"]["classification_receipt"] = {"sha256": "0" * 64}
    rehash(mutant)
    with pytest.raises(ValueError, match="input receipts"):
        proof.validate_artifact(mutant)


def copy_small_consumer_checkout(tmp_path: Path, artifact: dict) -> Path:
    root = tmp_path / "consumer"
    evaluator = artifact["producer"]["campaign_evaluator"]
    relatives = {relative for relative, _digest in proof.SMALL_INPUTS.values()}
    relatives.update(
        row["path"] for row in [evaluator["campaign"], *evaluator["oracle_sources"]]
    )
    relatives.update(
        {
            proof.PRODUCER_PATH,
            "scripts/build_us_tariff_section232_equivalence_receipt.py",
        }
    )
    for relative in relatives:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(proof.REPO_ROOT / relative, destination)
    return root


def test_lightweight_consumer_needs_no_external_data_engine_or_downstream_files(
    artifact, tmp_path, monkeypatch
):
    root = copy_small_consumer_checkout(tmp_path, artifact)
    original_receipt = proof.foundation.file_receipt

    def bounded_receipt(path, **kwargs):
        assert Path(path).resolve().is_relative_to(root.resolve()), path
        return original_receipt(path, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("normal proof validation must not scan or execute")

    monkeypatch.setattr(proof.foundation, "file_receipt", bounded_receipt)
    monkeypatch.setattr(proof, "build_receipt", forbidden)
    monkeypatch.setattr(proof, "_scan_recorded_inputs", forbidden)
    monkeypatch.setattr(proof, "_paired_replay", forbidden)
    monkeypatch.setattr(proof, "_verify_external_sources", forbidden)
    monkeypatch.setattr(proof.campaign, "_rulespec_root_identity", forbidden)
    assert not (
        root / "reference/us-tariff-schedule/campaign-dispositions.yaml"
    ).exists()
    assert not (
        root / "reference/us-tariff-schedule/classification-receipt.json"
    ).exists()
    assert proof.validate_artifact(artifact, repo_root=root) is artifact


@pytest.mark.parametrize(
    "relative",
    [
        proof.PRODUCER_PATH,
        "scripts/us_tariff_schedule_campaign.py",
        "axiom_oracles/adapters/axiom/runner.py",
        "scripts/build_us_tariff_section232_equivalence_receipt.py",
        "reference/us-tariff-schedule/eval/MANIFEST.json",
        "reference/us-tariff-schedule/comparison-summary.json",
        "reference/us-tariff-schedule/declared-input-contract-receipt.json",
    ],
)
def test_current_small_source_or_input_drift_is_rejected(artifact, tmp_path, relative):
    root = copy_small_consumer_checkout(tmp_path, artifact)
    path = root / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="drift"):
        proof.validate_artifact(artifact, repo_root=root)


def test_global_case_id_audit_rejects_duplicate_including_non_target(tmp_path):
    path = tmp_path / "case-ids.txt"
    path.write_bytes(b"0" * 24 + b"\n" + b"0" * 24 + b"\n")
    with pytest.raises(ValueError, match="duplicate evaluation case id"):
        proof._unique_case_buckets([path])


def test_historical_duplicate_keys_are_rejected(artifact):
    record = artifact["cases"][0]["recorded_evaluation"]
    row = next(
        row
        for row in proof.campaign.compare_record(record)
        if row["slot"] in proof.SLOTS and not row["match"]
    )
    with pytest.raises(ValueError, match="duplicate historical unit key"):
        proof._historical_identities([row, deepcopy(row)])


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "engine_error", "wrong_chapter", "hash_drift"]
)
def test_scanner_rejects_bad_recorded_shards(artifact, tmp_path, monkeypatch, fault):
    record = deepcopy(artifact["cases"][0]["recorded_evaluation"])
    records = [record]
    expected_count = 1
    if fault == "missing":
        expected_count = 2
    elif fault == "duplicate":
        records.append(deepcopy(record))
        expected_count = 2
    elif fault == "engine_error":
        record["engine_errors"] = ["recorded failure"]
    elif fault == "wrong_chapter":
        record["chapter"] = "93"
    path = tmp_path / "shard.jsonl.gz"
    with gzip.open(path, "wt") as target:
        for row in records:
            target.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    shard = {
        "path": str(path),
        "chapter": "94",
        "cases": expected_count,
        "sha256": proof.foundation.sha256(path),
    }
    if fault == "hash_drift":
        shard["sha256"] = "0" * 64
    monkeypatch.setattr(proof, "_check_historical_file", lambda path: None)
    monkeypatch.setattr(proof, "_historical_identities", lambda rows: {})
    messages = {
        "missing": "missing or extra",
        "duplicate": "duplicate fresh mismatch",
        "engine_error": "engine error",
        "wrong_chapter": "chapter identity",
        "hash_drift": "shard content drift",
    }
    with pytest.raises(ValueError, match=messages[fault]):
        proof._scan_recorded_inputs(
            {"shards": {"test": shard}}, tmp_path / "unused-history", tmp_path
        )


def test_schema_errors_are_value_errors(artifact):
    for mutant in (None, [], {}, {**artifact, "cases": None}):
        if isinstance(mutant, dict) and mutant:
            rehash(mutant)
        with pytest.raises(ValueError):
            proof.validate_artifact(mutant)
