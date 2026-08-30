"""Bounded causal proof, lossless evidence, and fail-closed replay regressions."""

from __future__ import annotations

from copy import deepcopy
import gzip
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import build_us_tariff_remaining_residual_receipt as proof


@pytest.fixture(scope="module")
def artifact():
    # Intentionally independent of the changing live ledger/report. Full
    # producer --check separately reexecutes R/Axiom and all frozen shards.
    return proof.foundation.load_json(proof.DEFAULT_OUTPUT)


def rehash(document):
    document.pop("receipt_payload_sha256", None)
    document["receipt_payload_sha256"] = proof.canonical_sha256(document)


def change(document, path, replacement):
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


def test_exact_bounded_classes_and_actual_replays(artifact):
    assert proof.validate_artifact(artifact) is artifact
    assert [
        (
            row["id"],
            row["expected_units"],
            row["expected_signature_count"],
            row["disposition"],
            row["attribution"],
        )
        for row in artifact["classes"]
    ] == [
        (
            "section232-russia-aluminum-membership-vintage",
            24,
            12,
            "explained_residual",
            "input-comparability",
        ),
        (
            "yale-html-statutory-base-parser-defect",
            5709,
            3114,
            "upstream_engine_gap",
            "reference-defect",
        ),
    ]
    assert artifact["census"] == proof.EXPECTED_CENSUS
    assert len(artifact["units"]) == 5733
    assert len(artifact["source_records"]) == 57
    replay = artifact["replay"]
    assert replay["baseline_exact_recorded_output_values"] == 63063
    assert replay["r_original_statutory_matches_recorded_base_units"] == 5709
    assert replay["r_markup_only_statutory_matches_actual_general_units"] == 5709
    assert replay["r_direct_original_na_probes"] == 21
    assert replay["r_statistical_original_inherited_zero_probes"] == 30
    assert replay["r_max_absolute_roundoff"] < 1e-12
    assert replay["aluminum_counterfactual_exact_target_units"] == 24
    assert replay["aluminum_counterfactual_other_slot_mismatches"] == {
        "base": 24,
        "total": 24,
    }
    assert (
        replay["aluminum_changed_output_case_counts"]["section_122_component_rate"]
        == 12
    )
    assert replay["whole_case_parity_claimed"] is False
    assert (
        artifact["r_replay"]["contract"]["whole_archive_non_general_fields_unchanged"]
        is True
    )
    assert artifact["r_replay"]["contract"]["cached_products_used"] is False
    assert artifact["source_identity"]["r_runtime_tree"]["file_count"] == 8300


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("schema",), "unrecognized"),
        (("verdict",), "FAIL"),
        (("bindings", "run_identity_sha256"), "0" * 64),
        (("bindings", "generation_id"), "0" * 32),
        (("bindings", "actual_case_feed_and_output_population_sha256"), "0" * 64),
        (("producer", "script", "sha256"), "0" * 64),
        (("producer", "runtime_helper", "sha256"), "0" * 64),
        (("inputs", "evaluation_manifest", "sha256"), "0" * 64),
        (("inputs", "comparison_receipt", "sha256"), "0" * 64),
        (("inputs", "comparison_artifact", "sha256"), "0" * 64),
        (("inputs", "input_contract", "sha256"), "0" * 64),
        (("source_identity", "engine", "sha256"), "0" * 64),
        (("source_identity", "rulespec", "head_commit"), "0" * 40),
        (("source_identity", "yale", "commit"), "0" * 40),
        (("source_identity", "yale", "files", 0, "sha256"), "0" * 64),
        (("source_identity", "r_runtime_tree", "file_count"), 8299),
        (("source_identity", "r_runtime_tree", "manifest_sha256"), "0" * 64),
        (("source_identity", "dplyr_tree", "manifest_sha256"), "0" * 64),
        (("source_identity", "entry_flag_producers", "producer_sha256"), "0" * 64),
        (("source_facts", "base_source_map", 0, "source_hts"), "8708103000"),
        (("source_facts", "aluminum_scope", "existing_russia_override", "rate"), 0.0),
        (
            (
                "source_facts",
                "aluminum_scope",
                "axiom_primary_membership",
                "snapshot_effective_from",
            ),
            "2026-02-15",
        ),
        (("source_records", 0, "product", "general"), "2.5%"),
        (("source_records", 0, "product_index"), 1),
        (("source_records", 0, "source", "general"), "Free"),
        (("shards", 0, "sha256"), "0" * 64),
        (("shards", 0, "cases"), 1),
        (("census", "evaluated_records"), 19_118_618),
        (("census", "selected_unique_cases"), 5732),
        (("census", "engine_errors"), 1),
        (("census", "duplicate_evaluation_case_ids"), False),
        (("census", "selected_target_units", "base"), 3311),
        (("census", "selected_target_units", "section_232"), 16),
        (("classes", 0, "expected_units"), 16),
        (("classes", 0, "identity_population_sha256"), "0" * 64),
        (("classes", 1, "attribution"), "input-comparability"),
        (("classes", 1, "disposition"), "explained_residual"),
        (("classes", 1, "expected_signature_count"), 3113),
        (("classes", 1, "expected_signature_population_sha256"), "0" * 64),
        (("classes", 1, "signatures", 0), "0" * 64),
        (("r_replay", "contract", "inherited_environment"), True),
        (("r_replay", "contract", "environment", "LC_ALL"), "C"),
        (("r_replay", "contract", "program_sha256"), "0" * 64),
        (("r_replay", "contract", "tolerance"), 0.1),
        (("r_replay", "contract", "cached_products_used"), True),
        (("r_replay", "contract", "full_archive_replays"), 0),
        (("r_replay", "contract", "changed_general_fields_per_archive"), 17),
        (("r_replay", "result", "r_version"), "4.4.0"),
        (("r_replay", "result", "rows", 0, "baseline_statutory_base_rate"), 0.025),
        (("r_replay", "result", "rows", 0, "source_general_raw"), "2.5%"),
        (("r_replay", "result", "rows", 0, "source_index"), 1),
        (("r_replay", "result", "rows", 0, "sanitized_statutory_base_rate"), 0.0),
        (("replay", "baseline_exact_recorded_output_values"), 63062),
        (("replay", "r_statistical_original_inherited_zero_probes"), 0),
        (("replay", "aluminum_counterfactual_exact_target_units"), 16),
        (("replay", "whole_case_parity_claimed"), True),
        (
            ("limitations", "base"),
            "Only origin preference explains the base discrepancy.",
        ),
        (
            ("limitations", "vintage"),
            "Aluminum first became legally covered on August3.",
        ),
        (("limitations", "coverage"), "The comparison certifies actual entries."),
        (("units", 0, "case_id"), "schedule-" + "0" * 24),
        (("units", 0, "actual"), 0),
        (("units", 0, "slot"), "total"),
    ],
)
def test_rehashed_metadata_or_source_mutants_fail(artifact, path, replacement):
    mutant = deepcopy(artifact)
    change(mutant, path, replacement)
    rehash(mutant)
    with pytest.raises(ValueError):
        proof.validate_artifact(mutant)


@pytest.mark.parametrize(
    "slot,path,replacement",
    [
        ("base", ("recorded_evaluation", "case_id"), "schedule-" + "0" * 24),
        ("base", ("recorded_evaluation", "probe"), "2026-08-03"),
        ("base", ("recorded_evaluation", "hts_line"), "8708103000"),
        ("base", ("recorded_evaluation", "iso2"), "RU"),
        ("base", ("recorded_evaluation", "origin_regime"), "1" * 16),
        ("base", ("recorded_evaluation", "expected", "statutory_base_rate"), "0.025"),
        ("base", ("recorded_evaluation", "actual", "mfn_ad_valorem_rate"), 0.0),
        ("base", ("recorded_evaluation", "engine_errors"), ["missing-output"]),
        ("base", ("baseline_inputs", "hts_number"), "8708103000"),
        (
            "base",
            ("baseline_inputs", "entry_is_entered_free_of_duty_under_dr_cafta"),
            True,
        ),
        ("base", ("baseline_outputs", "mfn_ad_valorem_rate"), 0.0),
        ("section_232", ("baseline_inputs", "entry_is_section_232_aluminum"), False),
        (
            "section_232",
            ("counterfactual_inputs", "entry_is_section_232_aluminum"),
            True,
        ),
        (
            "section_232",
            ("counterfactual_inputs", "entry_is_section_232_covered"),
            True,
        ),
        ("section_232", ("counterfactual_inputs", "country_of_origin"), "CA"),
        (
            "section_232",
            (
                "counterfactual_inputs",
                "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight",
            ),
            False,
        ),
        (
            "section_232",
            ("counterfactual_outputs", "section_232_aluminum_component_rate"),
            2.0,
        ),
        (
            "section_232",
            ("counterfactual_outputs", "section_232_aluminum_component_rate"),
            None,
        ),
        ("section_232", ("counterfactual_outputs", "mfn_ad_valorem_rate"), 0.0),
    ],
)
def test_repacked_rehashed_actual_evidence_mutants_fail(
    artifact, slot, path, replacement
):
    mutant = deepcopy(artifact)
    cases = proof._unpack_cases(mutant["cases"])
    case = next(
        c for c in cases if proof._target_slot(c["recorded_evaluation"]) == slot
    )
    change(case, path, replacement)
    mutant["cases"] = proof._pack_cases(cases)
    rehash(mutant)
    with pytest.raises(
        ValueError, match="trusted actual case/feed/paired-output population"
    ):
        proof.validate_artifact(mutant)


@pytest.mark.parametrize(
    "action",
    [
        "remove",
        "duplicate",
        "bool_index",
        "negative_index",
        "wide_row",
        "unused_catalog",
        "extra_field",
    ],
)
def test_invalid_or_noncanonical_catalogs_fail(artifact, action):
    mutant = deepcopy(artifact)
    packed = mutant["cases"]
    if action == "remove":
        packed["rows"].pop()
    elif action == "duplicate":
        packed["rows"][1] = deepcopy(packed["rows"][0])
    elif action == "bool_index":
        packed["rows"][0][0] = False
    elif action == "negative_index":
        packed["rows"][0][0] = -1
    elif action == "wide_row":
        packed["rows"][0].append(0)
    elif action == "unused_catalog":
        packed["record_catalogs"]["engine_errors"].append(["unused"])
    else:
        packed["extra"] = True
    rehash(mutant)
    with pytest.raises(ValueError):
        proof.validate_artifact(mutant)


def test_equivalent_but_reordered_catalog_is_rejected(artifact):
    mutant = deepcopy(artifact)
    packed = mutant["cases"]
    position = packed["record_fields"].index("chapter")
    assert len(packed["record_catalogs"]["chapter"]) == 2
    packed["record_catalogs"]["chapter"].reverse()
    for row in packed["rows"]:
        row[position] = 1 - row[position]
    rehash(mutant)
    with pytest.raises(ValueError, match="canonical lossless case catalog"):
        proof.validate_artifact(mutant)


def test_duplicate_catalog_entry_is_rejected(artifact):
    mutant = deepcopy(artifact)
    catalog = mutant["cases"]["record_catalogs"]["engine_errors"]
    catalog.append(deepcopy(catalog[0]))
    rehash(mutant)
    with pytest.raises(ValueError, match="canonical lossless case catalog"):
        proof.validate_artifact(mutant)


def test_missing_zero_output_column_is_rejected(artifact):
    mutant = deepcopy(artifact)
    packed = mutant["cases"]
    index = packed["output_fields"].index("section_201_component_rate")
    assert all(vector[index] == 0 for vector in packed["output_vectors"])
    packed["output_fields"].pop(index)
    for vector in packed["output_vectors"]:
        vector.pop(index)
    rehash(mutant)
    with pytest.raises(ValueError):
        proof.validate_artifact(mutant)


def test_missing_counterfactual_pair_is_rejected_even_when_repacked(artifact):
    mutant = deepcopy(artifact)
    cases = proof._unpack_cases(mutant["cases"])
    case = next(c for c in cases if "counterfactual_outputs" in c)
    del case["counterfactual_inputs"]
    del case["counterfactual_outputs"]
    mutant["cases"] = proof._pack_cases(cases)
    rehash(mutant)
    with pytest.raises(
        ValueError, match="trusted actual case/feed/paired-output population"
    ):
        proof.validate_artifact(mutant)


def test_coordinated_rehashed_source_parser_and_actual_output_fabrication_fails(
    artifact,
):
    mutant = deepcopy(artifact)
    cases = deepcopy(proof._unpack_cases(mutant["cases"]))
    selected = next(
        c for c in cases if c["recorded_evaluation"]["hts10"] == "8708220000"
    )
    selected["recorded_evaluation"]["actual"]["mfn_ad_valorem_rate"] = 0.03
    selected["baseline_outputs"]["mfn_ad_valorem_rate"] = 0.03
    mutant["cases"] = proof._pack_cases(cases)
    for row in mutant["source_facts"]["base_source_map"]:
        if row["hts10"] == "8708220000":
            row["axiom_general"] = 0.03
    for row in mutant["source_records"]:
        if row["hts10"] == "8708220000":
            row["product"]["general"] = "3% <u></u>"
            row["source"]["general"] = "3% <u></u>"
    for row in mutant["r_replay"]["result"]["rows"]:
        if row["hts10"] == "8708220000":
            row["source_general_raw"] = row["product_general_raw"] = "3% <u></u>"
            row["sanitized_source_general"] = "3%"
            row["sanitized_parse_rate"] = row["sanitized_statutory_base_rate"] = 0.03
    mutant["r_replay"]["contract"]["result_sha256"] = proof.canonical_sha256(
        mutant["r_replay"]["result"]
    )
    rehash(mutant)
    with pytest.raises(ValueError, match="trusted source facts"):
        proof.validate_artifact(mutant)


def _copy_required_inputs(artifact, target):
    def visit(value):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                path = Path(value["path"])
                if not path.is_absolute():
                    destination = target / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(proof.REPO_ROOT / path, destination)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(artifact["producer"])
    visit(artifact["inputs"])


def test_normal_validation_only_requires_small_committed_inputs(
    artifact, tmp_path, monkeypatch
):
    _copy_required_inputs(artifact, tmp_path)
    actual_receipt = proof.foundation.file_receipt

    def guarded_receipt(path, **kwargs):
        assert Path(path).is_relative_to(tmp_path), (
            "normal validator touched an external mount"
        )
        return actual_receipt(path, **kwargs)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("normal validation must not scan or execute a runtime")

    monkeypatch.setattr(proof.foundation, "file_receipt", guarded_receipt)
    for name in (
        "_scan_records",
        "_run_r",
        "_paired_replay",
        "_verify_external_sources",
        "_check_runtime",
    ):
        monkeypatch.setattr(proof, name, forbidden)
    monkeypatch.setattr(proof.subprocess, "run", forbidden)
    assert proof.validate_artifact(artifact, repo_root=tmp_path) is artifact


@pytest.mark.parametrize(
    "relative",
    [value[0] for value in proof.SMALL_INPUTS.values()]
    + [proof.PRODUCER_PATH, "scripts/build_us_tariff_cafta_supersession_receipt.py"],
)
@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_changed_small_inputs_fail(artifact, tmp_path, relative, missing):
    _copy_required_inputs(artifact, tmp_path)
    path = tmp_path / relative
    if missing:
        path.unlink()
    else:
        path.write_text("changed\n")
    with pytest.raises(ValueError):
        proof.validate_artifact(artifact, repo_root=tmp_path)


def _minimal_record(**updates):
    return {
        "case_id": "schedule-" + "1" * 24,
        "chapter": "87",
        "engine_errors": [],
        "flags": {},
        "hts10": "0100000000",
        "hts_line": "0100000000",
        **updates,
    }


def _scan_fixture(tmp_path, records, count=None):
    path = tmp_path / "eval.jsonl.gz"
    with gzip.open(path, "wb") as target:
        for record in records:
            target.write(proof.foundation.canonical(record) + b"\n")
    return {
        "shards": {
            "fixture": {
                "path": str(path),
                "sha256": proof.foundation.sha256(path),
                "chapter": "87",
                "cases": len(records) if count is None else count,
            }
        }
    }


@pytest.mark.parametrize(
    "records,count,error",
    [
        ([_minimal_record(), _minimal_record()], 2, "duplicate evaluation case id"),
        ([_minimal_record()], 2, "missing or extra evaluation records"),
        ([_minimal_record(engine_errors=["failed"])], 1, "recorded engine error"),
        ([_minimal_record(chapter="76")], 1, "case/chapter identity drift"),
        (
            [_minimal_record(case_id="schedule-not-hex")],
            1,
            "case/chapter identity drift",
        ),
    ],
)
def test_complete_scanner_rejects_errors_including_nontarget_duplicates(
    tmp_path, records, count, error
):
    manifest = _scan_fixture(tmp_path, records, count)
    with pytest.raises(ValueError, match=error):
        proof._scan_records(manifest, tmp_path)


def test_scanner_rechecks_shard_after_consumption(tmp_path, monkeypatch):
    manifest = _scan_fixture(tmp_path, [_minimal_record()])
    shard = manifest["shards"]["fixture"]
    calls = []

    def drifting_hash(path):
        calls.append(Path(path))
        return shard["sha256"] if len(calls) == 1 else "0" * 64

    monkeypatch.setattr(proof.foundation, "sha256", drifting_hash)
    with pytest.raises(ValueError, match="fresh shard changed during scan"):
        proof._scan_records(manifest, tmp_path)
    assert len(calls) == 2


@pytest.mark.parametrize("changed_tree", ["runtime", "dplyr"])
def test_runtime_guard_binds_both_complete_trees(monkeypatch, changed_tree):
    runtime = proof.campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT
    dplyr = proof.campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT
    seen = []

    def receipt(path):
        seen.append(Path(path))
        original = runtime if str(path) == runtime["path"] else dplyr
        result = deepcopy(original)
        if (original is runtime) == (changed_tree == "runtime"):
            result["manifest_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(
        proof.foundation,
        "file_receipt",
        lambda _path: proof.campaign.CAFTA_EXPECTED_RSCRIPT_RECEIPT,
    )
    monkeypatch.setattr(proof.cafta, "_directory_tree_receipt", receipt)
    with pytest.raises(ValueError, match="tree drift"):
        proof._check_runtime()
    assert Path(runtime["path"]) in seen
    if changed_tree == "dplyr":
        assert Path(dplyr["path"]) in seen


@pytest.mark.parametrize("mutation", [None, "program", "request", "post_runtime"])
def test_r_execution_uses_isolated_environment_and_postguards(
    artifact, tmp_path, monkeypatch, mutation
):
    checks, invoked = [], []

    def check_runtime():
        checks.append(True)
        if mutation == "post_runtime" and len(checks) == 2:
            raise ValueError("actual full R runtime tree drift")

    def run(argv, **kwargs):
        invoked.append((argv, kwargs))
        assert argv[1] == "--vanilla"
        assert kwargs["env"] == {
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(tmp_path),
        }
        assert "HOME" not in kwargs["env"] and "R_LIBS_USER" not in kwargs["env"]
        if mutation == "program":
            Path(argv[2]).write_text("changed")
        elif mutation == "request":
            Path(argv[4]).write_text("changed")
        return subprocess.CompletedProcess(
            argv, 0, stdout=proof.render(artifact["r_replay"]["result"]), stderr=""
        )

    monkeypatch.setattr(proof, "_check_runtime", check_runtime)
    monkeypatch.setattr(proof.subprocess, "run", run)
    if mutation:
        with pytest.raises(ValueError, match="drift"):
            proof._run_r(tmp_path / "yale", artifact["source_records"], tmp_path)
    else:
        result = proof._run_r(tmp_path / "yale", artifact["source_records"], tmp_path)
        assert result == artifact["r_replay"]
        assert len(checks) == 2
    assert len(invoked) == 1
    if mutation == "post_runtime":
        assert len(checks) == 2


@pytest.mark.parametrize("stale", [False, True])
def test_cli_check_always_reproduces_and_never_rewrites(
    artifact, tmp_path, monkeypatch, stale
):
    output = tmp_path / "proof.json"
    content = "stale\n" if stale else proof.render(artifact)
    output.write_text(content)
    before = output.stat().st_mtime_ns
    reproduced = []

    def build(**_kwargs):
        reproduced.append(True)
        return artifact

    monkeypatch.setattr(proof, "build_receipt", build)
    monkeypatch.setattr(
        proof.sys, "argv", [proof.PRODUCER_PATH, "--check", "--output", str(output)]
    )
    if stale:
        with pytest.raises(ValueError, match="missing or stale"):
            proof.main()
    else:
        assert proof.main() == 0
    assert reproduced == [True]
    assert output.read_text() == content
    assert output.stat().st_mtime_ns == before
