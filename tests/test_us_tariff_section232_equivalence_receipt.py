from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from scripts import build_us_tariff_section232_equivalence_receipt as producer
from scripts import build_us_tariff_cafta_supersession_receipt as cafta
from scripts import build_us_tariff_preview_selector_transition_receipt as transition
from scripts import us_tariff_schedule_campaign as campaign


SELECTOR_IDS = tuple(sorted(producer.SECTION232_SELECTOR_UNITS))


def _write_gzip(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write(
                    (
                        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode()
                )


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(producer.render(value))


def _row(index: int, selector_id: str, *, fresh: bool) -> dict:
    slot = (
        "brazil_section_301"
        if selector_id.endswith("-brazil")
        else "forced_labor_section_301"
    )
    code = f"{index + 1:010d}"
    expected = 0.0
    actual = 0.0 if fresh else 0.25
    delta = actual - expected
    flags = {
        name: False
        for name in (
            transition.UNCONDITIONAL_PRECEDENCE_FLAGS
            + transition.CANDIDATE_PRECEDENCE_FLAGS
            + transition.DECLARED_PRECEDENCE_FLAGS
            + transition.NOTE16_MEMBERSHIP_FLAGS
            + (transition.NOTE16_METAL_CHAPTER_FLAG, transition.NOTE16_WEIGHT_INPUT)
        )
    }
    flags[transition.NOTE16_WEIGHT_INPUT] = True
    if fresh:
        flags["entry_is_section_232_covered"] = True
    row = {
        "case_id": "schedule-" + hashlib.sha256(selector_id.encode()).hexdigest()[:24],
        "slot": slot,
        "expected": expected,
        "actual": actual,
        "delta": delta,
        "context": {
            "hts10": code,
            "hts_line": code,
            "iso2": "BR" if slot == "brazil_section_301" else "CN",
            "revision": "test-revision",
            "interval": ["2026-07-24", "2026-07-30"],
            "origin_regime": "0000000000000000",
            "flags": flags if fresh else {},
        },
    }
    if fresh:
        row["match"] = True
    else:
        row.update(
            {
                "new_disagreement": True,
                "old_target_class": None,
                "probe": "2026-07-24",
            }
        )
    return row


def _eval_record(row: dict) -> dict:
    slot = row["slot"]
    expected_field, actual_field = producer.SLOT_EVAL_FIELDS[slot]
    return {
        "case_id": row["case_id"],
        "chapter": "01",
        "probe": "2026-07-24",
        # Evaluation shards preserve selected-CSV expected rates as text; the
        # comparison stage parses them to numbers.
        "expected": {expected_field: str(row["expected"])},
        "actual": {actual_field: row["actual"]},
        "engine_errors": [],
        "plan": {"components": [slot]},
        **row["context"],
    }


def _synthetic_yale(
    root: Path,
    *,
    annex_rows: tuple[str, ...] = ("0000,1a,aluminum,proclamation,2026-04-06",),
    derivative_rows: tuple[str, ...] = ("9401999030,9903.85.08,aluminum,2025-08-18",),
) -> tuple[Path, dict, dict]:
    yale_root = root / "yale"
    files = {
        "resources/s232_annex_products.csv": (
            "hts_prefix,annex,metal_type,source,effective_date\n"
            + "\n".join(annex_rows)
            + "\n"
        ),
        "resources/s232_derivative_products.csv": (
            "hts_prefix,ch99_code,derivative_type,effective_date\n"
            + "\n".join(derivative_rows)
            + "\n"
        ),
        "src/model/data_loaders.R": "# synthetic pinned loader\n",
        "scripts/parse_annex_products.R": "# synthetic pinned parser\n",
    }
    for logical_path, content in files.items():
        path = yale_root / logical_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=yale_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=yale_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Transition Test"],
        cwd=yale_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=yale_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "synthetic Yale pin"],
        cwd=yale_root,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=yale_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=yale_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    preview_files = {
        logical_path: {
            "bytes": (yale_root / logical_path).stat().st_size,
            "sha256": producer.sha256(yale_root / logical_path),
        }
        for logical_path in transition.YALE_PREVIEW_SOURCE_FILES
    }
    parser_path = yale_root / "scripts/parse_annex_products.R"
    parser_receipt = {
        "path": "scripts/parse_annex_products.R",
        "bytes": parser_path.stat().st_size,
        "sha256": producer.sha256(parser_path),
    }
    return (
        yale_root,
        {
            "commit": commit,
            "tree": tree,
            "files": preview_files,
        },
        parser_receipt,
    )


def _evidence(
    root: Path,
    *,
    historical_mutator=None,
    source_fresh_mutator=None,
    fresh_mutator=None,
    eval_mutator=None,
    declared_shard_cases: int | None = None,
    shard_engine_errors: int = 0,
    distinct_campaign_producers: bool = False,
    yale_annex_rows: tuple[str, ...] = ("0000,1a,aluminum,proclamation,2026-04-06",),
    yale_derivative_rows: tuple[str, ...] = (
        "9401999030,9903.85.08,aluminum,2025-08-18",
    ),
) -> dict:
    producer_source = root / "scripts/build_receipt.py"
    campaign_source = root / "scripts/us_tariff_schedule_campaign.py"
    producer_source.parent.mkdir(parents=True, exist_ok=True)
    producer_source.write_text("# receipt producer\n")
    campaign_source.write_text("# campaign producer\n")
    selected = root / producer.SELECTED_LOGICAL_PATH
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_bytes(b"selected population\n")

    historical_rows = [
        _row(index, selector_id, fresh=False)
        for index, selector_id in enumerate(SELECTOR_IDS)
    ]
    if historical_mutator is not None:
        historical_mutator(historical_rows)
    historical = root / producer.HISTORICAL_LOGICAL_PATH
    _write_gzip(historical, historical_rows)

    source_fresh_rows = [
        _row(index, selector_id, fresh=True)
        for index, selector_id in enumerate(SELECTOR_IDS)
    ]
    if source_fresh_mutator is not None:
        source_fresh_mutator(source_fresh_rows)
    eval_rows = [_eval_record(row) for row in source_fresh_rows]
    if eval_mutator is not None:
        eval_mutator(eval_rows)
    fresh_rows = json.loads(json.dumps(source_fresh_rows))
    if fresh_mutator is not None:
        fresh_mutator(fresh_rows)
    comparison_artifact = root / "cache/comparison.jsonl.gz"
    _write_gzip(comparison_artifact, fresh_rows)

    expected_units = {selector_id: 1 for selector_id in SELECTOR_IDS}
    campaign_receipt = producer.file_receipt(campaign_source, relative_to=root)
    if distinct_campaign_producers:
        preview_campaign_source = root / "scripts/preview_campaign.py"
        preview_campaign_source.write_text("# historical preview campaign producer\n")
        preview_campaign_receipt = producer.file_receipt(
            preview_campaign_source, relative_to=root
        )
    else:
        preview_campaign_receipt = campaign_receipt
    selectors = []
    line_sets = {}
    for index, selector_id in enumerate(SELECTOR_IDS):
        line_set_name = f"preview-1311-{selector_id}-hts10"
        value = f"{index + 1:010d}"
        line_sets[line_set_name] = {
            "width": 10,
            "value_count": 1,
            "values_sha256": producer.values_sha256([value]),
            "values": [value],
        }
        slot = (
            "brazil_section_301"
            if selector_id.endswith("-brazil")
            else "forced_labor_section_301"
        )
        selectors.append(
            {
                "id": selector_id,
                "logical_class": selector_id.rsplit("-", 1)[0],
                "disposition": "axiom_encoding_gap",
                "attribution": "axiom-attributed-open",
                "expected_units": 1,
                "expected_signature_count": 1,
                "expected_signature_population_sha256": (
                    campaign.signature_population_sha256(
                        [
                            (
                                campaign.mismatch_signature(historical_rows[index]),
                                1,
                            )
                        ]
                    )
                ),
                "match": {
                    "slot": slot,
                    "line_set": line_set_name,
                    "delta": {"sign": "pos"},
                },
            }
        )
    yale_root, yale_sources, yale_parser_receipt = _synthetic_yale(
        root,
        annex_rows=yale_annex_rows,
        derivative_rows=yale_derivative_rows,
    )
    preview = {
        "schema": producer.PREVIEW_SCHEMA,
        "verdict": "PASS",
        "producer": {
            "script": producer.file_receipt(
                transition.preview_builder.PRODUCER_SOURCE,
                relative_to=root,
            ),
            "campaign_classifier": preview_campaign_receipt,
        },
        "inputs": {
            producer.HISTORICAL_LOGICAL_PATH: {
                "path": producer.HISTORICAL_LOGICAL_PATH,
                "bytes": historical.stat().st_size,
                "sha256": producer.sha256(historical),
            },
            producer.SELECTED_LOGICAL_PATH: producer.file_receipt(
                selected, relative_to=root
            ),
        },
        "selectors": selectors,
        "line_sets": line_sets,
        "census": {
            "per_selector": expected_units,
            "total": sum(expected_units.values()),
        },
        "yale_sources": yale_sources,
    }
    expected_preview_snapshot_sha256 = producer.canonical_sha256(
        producer.preview_section232_snapshot(preview, expected_units)
    )
    preview["receipt_payload_sha256"] = producer.canonical_sha256(preview)
    preview_path = (
        root / "reference/us-tariff-schedule/preview-disposition-line-sets.json"
    )
    _write_json(preview_path, preview)

    shard_path = root / "cache/eval-shard.jsonl.gz"
    _write_gzip(shard_path, eval_rows)
    entry_flag_producers = {"producer_sha256": "a" * 64}
    reference_assumptions = {
        "yale_note16_metal_weight": {
            "path": "reference/assumption.json",
            "bytes": 1,
            "sha256": "f" * 64,
        }
    }
    rulespec = {
        "root": "/rulespec",
        "head_commit": "b" * 40,
        "head_tree": "c" * 40,
        "content_sha256": "d" * 64,
    }
    engine = {"path": "/engine", "bytes": 1, "sha256": "e" * 64}
    emitted_entry_flags = sorted(
        set(source_fresh_rows[0]["context"]["flags"])
        | campaign.EXPECTED_DROPPED_ENTRY_FLAGS
    )
    input_contract = {
        "schema": campaign.INPUT_CONTRACT_SCHEMA,
        "verdict": "PASS",
        "emitted_entry_flags": emitted_entry_flags,
        "expected_dropped_entry_flags": sorted(campaign.EXPECTED_DROPPED_ENTRY_FLAGS),
        "entry_flag_producers": entry_flag_producers,
        "reference_assumptions": reference_assumptions,
        "rulespec": rulespec,
        "engine": engine,
    }
    input_contract_path = (
        root / "reference/us-tariff-schedule/declared-input-contract-receipt.json"
    )
    _write_json(input_contract_path, input_contract)
    input_contract_binding = {
        **producer.file_receipt(input_contract_path, relative_to=root),
        "schema": campaign.INPUT_CONTRACT_SCHEMA,
    }
    run_identity = {
        "campaign_evaluator": {"campaign": campaign_receipt},
        "entry_flag_producers": entry_flag_producers,
        "reference_assumptions": reference_assumptions,
        "selected_population": producer.file_receipt(selected, relative_to=root),
        "chapters": {"01": {"module": "generated/ch01.yaml"}},
        "rulespec": rulespec,
        "engine": engine,
        "input_contract": input_contract_binding,
    }
    run_identity_sha256 = producer.canonical_sha256(run_identity)
    generation_id = "1" * 32
    shard_key = "2" * 64
    manifest = {
        "schema": producer.EVAL_SCHEMA,
        "generation_id": generation_id,
        "run_identity": run_identity,
        "run_identity_sha256": run_identity_sha256,
        "shards": {
            shard_key: {
                "chapter": "01",
                "key": shard_key,
                "run_identity_sha256": run_identity_sha256,
                "generation_id": generation_id,
                "path": str(shard_path.resolve()),
                "sha256": producer.sha256(shard_path),
                "cases": (
                    len(eval_rows)
                    if declared_shard_cases is None
                    else declared_shard_cases
                ),
                "engine_errors": shard_engine_errors,
            }
        },
    }
    evaluation_manifest_sha256 = producer.canonical_sha256(manifest)
    per_slot: dict[str, Counter[str]] = defaultdict(Counter)
    artifact_engine_errors = 0
    for row in fresh_rows:
        per_slot[row["slot"]]["match" if row["match"] else "mismatch"] += 1
        artifact_engine_errors += row["slot"] == "engine_error"
    comparison = {
        "schema": producer.COMPARISON_SCHEMA,
        "run_identity_sha256": run_identity_sha256,
        "generation_id": generation_id,
        "evaluation_manifest_sha256": evaluation_manifest_sha256,
        "tolerance": producer.TOLERANCE,
        "comparison_artifact": producer.file_receipt(comparison_artifact),
        "per_slot": {slot: dict(counter) for slot, counter in sorted(per_slot.items())},
        # Keep this zero in artifact-error mutants to exercise the independent
        # row scan rather than only the summary check.
        "engine_errors": 0,
    }
    comparison_path = root / "reference/us-tariff-schedule/comparison-summary.json"
    _write_json(comparison_path, comparison)
    manifest["comparison_artifact"] = comparison["comparison_artifact"]
    manifest["comparison_receipt"] = producer.file_receipt(
        comparison_path, relative_to=root
    )
    manifest_path = root / "reference/us-tariff-schedule/eval/MANIFEST.json"
    _write_json(manifest_path, manifest)
    return {
        "repo_root": root,
        "producer_source": producer_source,
        "preview_receipt_path": preview_path,
        "historical_artifact_path": historical,
        "eval_manifest_path": manifest_path,
        "comparison_receipt_path": comparison_path,
        "expected_preview_snapshot_sha256": expected_preview_snapshot_sha256,
        "expected_selector_units": expected_units,
        "yale_root": yale_root,
        "expected_yale_parser_receipt": yale_parser_receipt,
    }


def _build(inputs: dict) -> dict:
    return producer.build_receipt(
        **{
            key: value
            for key, value in inputs.items()
            if key not in {"yale_root", "expected_yale_parser_receipt"}
        }
    )


def _transition_build_inputs(
    inputs: dict,
) -> tuple[dict, dict[str, frozenset[tuple[str, ...]]]]:
    root = inputs["repo_root"]
    full_closure_guard_source = (
        root / "scripts/build_us_tariff_section232_equivalence_receipt.py"
    )
    full_closure_guard_source.write_text("# independent full-closure guard\n")
    comparison = producer.load_json(inputs["comparison_receipt_path"])
    with gzip.open(comparison["comparison_artifact"]["path"], "rt") as source:
        rows = [json.loads(line) for line in source]
    rows_by_case = {row["case_id"]: row for row in rows}
    expected_parent_patterns: dict[str, frozenset[tuple[str, ...]]] = {}
    for index, selector_id in enumerate(SELECTOR_IDS):
        historical = _row(index, selector_id, fresh=False)
        fresh = rows_by_case[historical["case_id"]]
        if fresh["match"]:
            continue
        pattern = transition._candidate_pattern(fresh["context"]["flags"])
        expected_parent_patterns[selector_id] = frozenset({pattern})
    build_inputs = {
        **inputs,
        "campaign_source": root / "scripts/us_tariff_schedule_campaign.py",
        "full_closure_guard_source": full_closure_guard_source,
        "expected_parent_patterns": expected_parent_patterns,
        "expected_parent_ids": frozenset(inputs["expected_selector_units"]),
        "expected_fallback_hts10": frozenset(),
        "expected_reference_assumptions": {
            "yale_note16_metal_weight": {
                "path": "reference/assumption.json",
                "bytes": 1,
                "sha256": "f" * 64,
            }
        },
    }
    return build_inputs, expected_parent_patterns


def _transition_state() -> dict:
    return {
        "matches": 0,
        "residual": Counter(),
        "patterns": Counter(),
        "child_populations": defaultdict(Counter),
        "defect_source_identities": [],
        "defect_source_arms": Counter(),
        "defect_source_populations": defaultdict(Counter),
        "defect_source_hts10": defaultdict(set),
        "fresh_identities": [],
        "rebind_population": Counter(),
    }


def _synthetic_all_parent_transitions() -> tuple[
    dict[str, dict], dict[str, dict], dict
]:
    selectors: dict[str, dict] = {}
    states: dict[str, dict] = {}
    for parent_id in transition.EXPECTED_PARENT_IDS:
        if parent_id.startswith("section232-annex-"):
            units = len(transition.ANNEX_RESIDUAL_PATTERNS)
        elif parent_id.startswith("section232-heading-"):
            units = len(transition.HEADING_RESIDUAL_PATTERNS)
        else:
            units = 1
        selectors[parent_id] = {
            "id": parent_id,
            "logical_class": f"logical-{parent_id}",
            "disposition": "axiom_encoding_gap",
            "attribution": "axiom-attributed-open",
            "expected_units": units,
            "expected_signature_count": units,
            "expected_signature_population_sha256": "a" * 64,
            "match": {
                "slot": (
                    "brazil_section_301"
                    if parent_id.endswith("-brazil")
                    else "forced_labor_section_301"
                ),
                "line_set": f"preview-1311-{parent_id}-hts10",
                "delta": {"sign": "pos"},
            },
        }
        state = _transition_state()
        if parent_id.startswith("section232-exposed-"):
            state["matches"] = 1
        elif parent_id.startswith("section232-"):
            patterns = (
                transition.ANNEX_RESIDUAL_PATTERNS
                if "-annex-" in parent_id
                else transition.HEADING_RESIDUAL_PATTERNS
            )
            for pattern in patterns:
                signature = hashlib.sha256(
                    f"{parent_id}|{transition._pattern_name(pattern)}".encode()
                ).hexdigest()
                state["residual"][signature] = 1
                state["patterns"][transition._pattern_name(pattern)] = 1
                state["child_populations"][pattern][signature] = 1
                if "-annex-" in parent_id and not pattern:
                    arm = "annex_proclamation_prefix"
                    state["defect_source_identities"].append(
                        [
                            f"case-{parent_id}",
                            selectors[parent_id]["match"]["slot"],
                            "0000000001",
                            "2026-07-24",
                            arm,
                            "0000",
                        ]
                    )
                    state["defect_source_arms"][arm] = 1
                    state["defect_source_populations"][arm][signature] = 1
                    state["defect_source_hts10"][arm].add("0000000001")
        else:
            signature = hashlib.sha256(f"fresh|{parent_id}".encode()).hexdigest()
            state["residual"][signature] = 1
            state["rebind_population"][signature] = 1
            state["fresh_identities"].append(
                {"selector": parent_id, "identity": {"case_id": parent_id}}
            )
        states[parent_id] = state
    cafta_receipt = {
        "file": {"path": "cafta.json", "bytes": 1, "sha256": "b" * 64},
        "payload": {"schema": cafta.SCHEMA, "verdict": "PASS"},
    }
    return selectors, states, cafta_receipt


def _cafta_receipt_inputs(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict]:
    root.mkdir(parents=True, exist_ok=True)

    def receipted(name: str) -> dict:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        return producer.file_receipt(path, relative_to=root)

    producer_source = root / "scripts/build_cafta.py"
    producer_source.parent.mkdir(parents=True, exist_ok=True)
    producer_source.write_text("# synthetic CAFTA producer\n")
    rscript = root / "scripts/Rscript"
    rscript.write_text("# synthetic pinned Rscript\n")
    reproduction = {
        "rscript": producer.file_receipt(rscript),
        "r_runtime_tree": copy.deepcopy(campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT),
        "dplyr_tree": copy.deepcopy(campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT),
        "program_sha256": campaign.CAFTA_EXPECTED_TIDY_EVAL_PROGRAM_SHA256,
        "r_version": "4.3.0",
        "dplyr_version": "1.1.2",
        "dplyr_path": campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT["path"],
        "selected_conditions": "full,fta",
        "result": (
            "PASS: rule_hit('full') selected both the full and fta rows under "
            "the pinned .data$condition %in% condition expression"
        ),
    }
    monkeypatch.setattr(
        campaign,
        "_run_cafta_tidy_eval_reproduction",
        lambda: copy.deepcopy(reproduction),
    )
    preview_file = receipted("reference/preview.json")
    historical_receipt = receipted("reference/historical.jsonl.gz")
    selected_receipt = receipted("reference/selected.csv.gz")
    manifest_file = receipted("reference/MANIFEST.json")
    comparison_file = receipted("reference/comparison.json")
    comparison_artifact = receipted("cache/comparison.jsonl.gz")
    extra_inputs = {
        name: receipted(f"reference/{name}.json")
        for name in (
            "declared_input_contract",
            "reference_provenance",
            "reference_integrity_receipt",
            "selected_panel_extractor",
        )
    }
    run_identity = {
        "rulespec": {"head_commit": "c" * 40},
        "campaign_evaluator": {"campaign": {"sha256": "d" * 64}},
        "chapters": {"01": {}},
        "selected_population": selected_receipt,
    }
    manifest = {"run_identity": run_identity}
    comparison = {
        "generation_id": "1" * 32,
        "run_identity_sha256": "2" * 64,
        "evaluation_manifest_sha256": "3" * 64,
        "per_slot": {"base": {"match": cafta.EXPECTED_CAFTA_UNITS}},
    }
    preview = {"census": {"total": cafta.EXPECTED_CAFTA_UNITS}}
    identity_digest = campaign.CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256
    payload = {
        "schema": cafta.SCHEMA,
        "verdict": "PASS",
        "producer": {
            "script": producer.file_receipt(producer_source, relative_to=root)
        },
        "definition": cafta.EXPECTED_DEFINITION,
        "inputs": {
            "immutable_preview_receipt": preview_file,
            "historical_target_mismatch_artifact": historical_receipt,
            "evaluation_manifest": manifest_file,
            "comparison_receipt": comparison_file,
            "comparison_artifact": comparison_artifact,
            **extra_inputs,
        },
        "bindings": {
            "preview_receipt_payload_sha256": "5" * 64,
            "preview_cafta_snapshot_sha256": (
                cafta.EXPECTED_PREVIEW_CAFTA_SNAPSHOT_SHA256
            ),
            "rulespec": run_identity["rulespec"],
            "campaign_evaluator": run_identity["campaign_evaluator"],
            "selected_population_sha256": selected_receipt["sha256"],
            "fresh_campaign_classifier_sha256": "d" * 64,
            "preview_campaign_classifier_sha256": "d" * 64,
            "campaign_producer_identity_required": False,
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "evaluated_chapters": 1,
            "evaluated_cases": 1,
            "observed_evaluated_cases": 1,
            "reference_compared_field": "statutory_rate_s301fl",
            **comparison,
        },
        "axiom_predicate_proof": {
            "predicates": {name: False for name in cafta.CAFTA_INPUTS},
            "all_joined_actual_case_feeds_false_false": True,
            "joined_fresh_evaluation_records": cafta.EXPECTED_CAFTA_UNITS,
            "chapter_contracts_checked": 1,
            "contract_sha256": extra_inputs["declared_input_contract"]["sha256"],
            "actual_case_feed_projection_sha256": (
                campaign.CAFTA_EXPECTED_ACTUAL_CASE_FEED_PROJECTION_SHA256
            ),
            "scope": "all campaign cases in all 100 compiled chapters",
        },
        "yale_reference_defect": {
            "commit": campaign.PREVIEW_YALE_COMMIT,
            "tree": campaign.PREVIEW_YALE_TREE,
            "files": {
                path: {"path": path, "bytes": 1, "sha256": sha256}
                for path, sha256 in campaign.CAFTA_YALE_FILE_SHA256.items()
            },
            "adapter_source_proof": copy.deepcopy(
                campaign.CAFTA_YALE_ADAPTER_SOURCE_PROOF
            ),
            "source_proof": {
                "rule_hit_function_first_line": 959,
                "rule_hit_use_site_first_line": 973,
                "use_conditioned_first_line": 999,
                "chapter98_precapture_first_line": 2961,
                "statutory_capture_first_line": 3022,
                **campaign.CAFTA_YALE_SOURCE_PROOF_HASHES,
                "defect": (
                    "the function argument is named condition, but dplyr's data "
                    "mask resolves the bare RHS condition to the condition column; "
                    "therefore .data$condition %in% condition is true for every "
                    "nonmissing row"
                ),
                "downstream_effect": (
                    "rule_hit('full') includes condition=fta rows, making "
                    "country_full_hit true, covered false, and rate_s301fl zero "
                    "before preference scaling"
                ),
                "comparison_surface": (
                    "statutory_rate_s301fl captures rate_s301fl before the later "
                    "HS2-country preference scaling; fixing the name collision "
                    "restores the statutory country-tier rate on the compared "
                    "surface regardless of utilization share"
                ),
            },
            "deterministic_minimal_reproduction": copy.deepcopy(reproduction),
        },
        "zero_error_proof": {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": 0,
        },
        "census": {
            "historical_artifact_rows_scanned": cafta.EXPECTED_CAFTA_UNITS,
            "fresh_comparison_rows_scanned": cafta.EXPECTED_CAFTA_UNITS,
            "cafta_units": cafta.EXPECTED_CAFTA_UNITS,
            "cafta_signatures": cafta.EXPECTED_CAFTA_SIGNATURES,
            "origin_units": cafta.EXPECTED_ORIGIN_UNITS,
        },
        "supersession": {
            "authorized_disposition_after_pass": "upstream_engine_gap",
            "authorized_attribution_after_pass": "reference-defect",
            "historical_identity_population_sha256": identity_digest,
            "fresh_identity_population_sha256": identity_digest,
            "historical_mismatch_projection_sha256": (
                campaign.CAFTA_EXPECTED_HISTORICAL_MISMATCH_PROJECTION_SHA256
            ),
            "historical_defect_projection_sha256": (
                campaign.CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
            ),
            "fresh_defect_projection_sha256": (
                campaign.CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
            ),
            "joined_historical_units": cafta.EXPECTED_CAFTA_UNITS,
            "missing_historical_units": 0,
            "duplicate_historical_identities": 0,
            "duplicate_fresh_identities": 0,
            "fresh_mismatching_units": cafta.EXPECTED_CAFTA_UNITS,
            "all_present": True,
            "all_unique": True,
            "all_predicates_false": True,
            "all_yale_defect_zeros_reproduced": True,
            "all_corrected_yale_statutory_rates_match_axiom": True,
        },
    }
    payload["receipt_payload_sha256"] = producer.canonical_sha256(payload)
    receipt_path = root / "reference/cafta.json"
    _write_json(receipt_path, payload)
    kwargs = {
        "path": receipt_path,
        "repo_root": root,
        "producer_source": producer_source,
        "preview_file": preview_file,
        "preview": preview,
        "preview_payload_sha256": "5" * 64,
        "historical_receipt": historical_receipt,
        "selected_receipt": selected_receipt,
        "manifest_file": manifest_file,
        "comparison_file": comparison_file,
        "comparison_artifact": comparison_artifact,
        "manifest": manifest,
        "comparison": comparison,
        "historical_identity_population_sha256": identity_digest,
        "fresh_identity_population_sha256": identity_digest,
    }
    return kwargs, payload


def _single_nonsection_scan_inputs(root: Path, *, matched: bool) -> tuple[dict, dict]:
    parent_id = "chapter98-brazil"
    historical = _row(0, parent_id, fresh=False)
    fresh = _row(0, parent_id, fresh=True)
    if not matched:
        fresh.update({"actual": 0.25, "delta": 0.25, "match": False})
    artifact = root / "fresh.jsonl.gz"
    _write_gzip(artifact, [fresh])
    identity = producer._identity(historical, label="historical")
    key = (identity["case_id"], identity["slot"])
    selector = {
        "id": parent_id,
        "logical_class": "chapter98",
        "disposition": "explained_residual",
        "attribution": "reference-behavior",
        "expected_units": 1,
        "expected_signature_count": 1,
        "expected_signature_population_sha256": "a" * 64,
        "match": {
            "slot": "brazil_section_301",
            "line_set": f"preview-1311-{parent_id}-hts10",
            "delta": {"sign": "pos"},
        },
    }
    source_comparison = {
        field: fresh[field]
        for field in ("context", "match", "actual", "expected", "delta")
    }
    kwargs = {
        "path": artifact,
        "comparison": {
            "tolerance": producer.TOLERANCE,
            "per_slot": {"brazil_section_301": {"match" if matched else "mismatch": 1}},
        },
        "historical_units": {key: {"selector": parent_id, "identity": identity}},
        "source_eval_units": {key: {"comparison": source_comparison}},
        "selectors": {parent_id: selector},
        "line_sets": {selector["match"]["line_set"]: frozenset({"0000000001"})},
        "parent_ids": {parent_id},
        "expected_fresh_flag_names": frozenset(fresh["context"]["flags"]),
        "yale_annex_classifier": lambda _hts10, _start: (
            "annex_proclamation_prefix",
            "0000",
        ),
    }
    return kwargs, fresh


def test_transition_producer_receipts_full_closure_without_children(
    tmp_path: Path,
) -> None:
    build_inputs, _expected = _transition_build_inputs(_evidence(tmp_path))

    receipt = transition.build_receipt(**build_inputs)

    assert receipt["verdict"] == "PASS"
    assert set(receipt) == {
        "schema",
        "verdict",
        "producer",
        "inputs",
        "bindings",
        "zero_error_proof",
        "transitions",
        "receipt_payload_sha256",
    }
    assert set(receipt["inputs"]) == {
        "immutable_preview_receipt",
        "historical_target_mismatch_artifact",
        "evaluation_manifest",
        "comparison_receipt",
        "comparison_artifact",
    }
    assert len(receipt["transitions"]) == 6
    assert all(item["status"] == "retired" for item in receipt["transitions"])
    assert all(not item["children"] for item in receipt["transitions"])
    assert receipt["producer"]["full_closure_guard"] == producer.file_receipt(
        build_inputs["full_closure_guard_source"], relative_to=tmp_path
    )
    assert receipt["zero_error_proof"] == {
        "evaluation_shard_engine_errors": 0,
        "observed_evaluation_record_errors": 0,
        "comparison_receipt_engine_errors": 0,
        "comparison_artifact_engine_error_rows": 0,
    }


def test_transition_producer_accepts_receipted_old_residual_parent_row(
    tmp_path: Path,
) -> None:
    def make_old_residual(rows: list[dict]) -> None:
        rows[0]["new_disagreement"] = False
        rows[0]["old_target_class"] = "legacy-explained-residual"

    build_inputs, _expected = _transition_build_inputs(
        _evidence(tmp_path, historical_mutator=make_old_residual)
    )

    receipt = transition.build_receipt(**build_inputs)

    assert receipt["verdict"] == "PASS"
    assert len(receipt["transitions"]) == 6


def test_transition_items_cover_all_18_parents_and_emit_30_children() -> None:
    selectors, states, cafta_receipt = _synthetic_all_parent_transitions()

    items = transition._transition_items(
        selectors=selectors,
        parent_state=states,
        expected_parent_patterns=transition.EXPECTED_PARENT_PATTERNS,
        expected_fallback_hts10=None,
        yale_source_receipt={"synthetic": True},
        cafta_proof=cafta_receipt,
    )

    assert len(items) == 18
    assert {item["parent_id"] for item in items} == transition.EXPECTED_PARENT_IDS
    assert sum(len(item["children"]) for item in items) == 30
    by_parent = {item["parent_id"]: item for item in items}
    assert all(
        by_parent[parent_id]["status"] == "retired"
        and not by_parent[parent_id]["children"]
        for parent_id in transition.EXPECTED_PARENT_IDS
        if parent_id.startswith("section232-exposed-")
    )
    normal_parent = "chapter98-brazil"
    normal_child = by_parent[normal_parent]["children"][0]
    assert normal_child["id"] == f"{normal_parent}-fresh-signature-rebind"
    assert normal_child["match"] == selectors[normal_parent]["match"]
    assert {
        key: normal_child[key]
        for key in ("logical_class", "disposition", "attribution")
    } == {
        key: selectors[normal_parent][key]
        for key in ("logical_class", "disposition", "attribution")
    }
    cafta_item = by_parent[transition.CAFTA_SELECTOR_ID]
    cafta_child = cafta_item["children"][0]
    assert cafta_child["id"] == "cafta-52i-yale-reference-defect"
    assert cafta_child["disposition"] == "upstream_engine_gap"
    assert cafta_child["attribution"] == "reference-defect"
    assert cafta_child["match"] == selectors[transition.CAFTA_SELECTOR_ID]["match"]
    assert cafta_item["evidence"]["cafta_supersession_receipt"] == cafta_receipt
    assert all(
        set(item)
        == {
            "parent_id",
            "parent_contract",
            "status",
            "historical_units",
            "fresh_matching_units",
            "fresh_residual_population",
            "children",
            "evidence",
        }
        for item in items
    )


def test_transition_items_reject_cross_parent_signature_overlap() -> None:
    selectors, states, cafta_receipt = _synthetic_all_parent_transitions()
    first = "chapter98-brazil"
    second = "yale-hts8-broadening-brazil"
    shared = next(iter(states[first]["residual"]))
    states[second]["residual"] = Counter({shared: 1})
    states[second]["rebind_population"] = Counter({shared: 1})

    with pytest.raises(ValueError, match="child populations overlap"):
        transition._transition_items(
            selectors=selectors,
            parent_state=states,
            expected_parent_patterns=transition.EXPECTED_PARENT_PATTERNS,
            expected_fallback_hts10=None,
            yale_source_receipt={"synthetic": True},
            cafta_proof=cafta_receipt,
        )


def test_nonsection_fresh_scan_derives_rebind_population(tmp_path: Path) -> None:
    kwargs, fresh = _single_nonsection_scan_inputs(tmp_path, matched=False)

    states, audit = transition._scan_fresh_transitions(**kwargs)

    state = states["chapter98-brazil"]
    signature = campaign.mismatch_signature(fresh)
    assert state["matches"] == 0
    assert state["residual"] == Counter({signature: 1})
    assert state["rebind_population"] == Counter({signature: 1})
    assert audit["joined_historical_units"] == 1


def test_nonsection_fresh_scan_rejects_a_new_match(tmp_path: Path) -> None:
    kwargs, _fresh = _single_nonsection_scan_inputs(tmp_path, matched=True)

    with pytest.raises(ValueError, match="unexpectedly matches"):
        transition._scan_fresh_transitions(**kwargs)


def test_all_selector_snapshot_and_fresh_flag_schema_are_exact(
    tmp_path: Path,
) -> None:
    preview, selectors, _line_sets, _historical, _selected = (
        transition._validate_preview(
            producer.PREVIEW_RECEIPT,
            expected_snapshot_sha256=(
                transition.EXPECTED_PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256
            ),
            expected_selector_units=(
                transition.preview_builder.EXPECTED_SELECTOR_UNITS
            ),
        )
    )

    assert len(selectors) == 18
    assert set(selectors) == transition.EXPECTED_PARENT_IDS
    assert preview["census"]["total"] == 395_330
    evidence = _evidence(tmp_path)
    manifest = producer.load_json(evidence["eval_manifest_path"])
    names, contract_path, contract_file = transition._validated_fresh_flag_names(
        repo_root=tmp_path,
        run_identity=manifest["run_identity"],
    )
    assert names == frozenset(_row(0, SELECTOR_IDS[0], fresh=True)["context"]["flags"])
    assert producer.file_receipt(contract_path, relative_to=tmp_path) == contract_file


def test_transition_producer_rejects_fresh_flag_schema_drift(
    tmp_path: Path,
) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[1]["context"]["flags"].pop(
            "entry_is_s232_note16_c_ii_derivative_aluminum_member"
        )

    build_inputs, _expected = _transition_build_inputs(
        _evidence(tmp_path, source_fresh_mutator=mutate)
    )

    with pytest.raises(ValueError, match="fresh preview flag schema drift"):
        transition.build_receipt(**build_inputs)


def test_cafta_receipt_is_fully_validated_and_embedded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, payload = _cafta_receipt_inputs(tmp_path, monkeypatch)

    embedded = transition._validated_cafta_supersession_receipt(**kwargs)

    assert embedded == {
        "file": producer.file_receipt(kwargs["path"], relative_to=tmp_path),
        "payload": payload,
    }


def test_cafta_receipt_rejects_missing_stale_or_fabricated_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, payload = _cafta_receipt_inputs(tmp_path, monkeypatch)
    missing = {**kwargs, "path": tmp_path / "reference/missing-cafta.json"}
    with pytest.raises(ValueError, match="missing receipted file"):
        transition._validated_cafta_supersession_receipt(**missing)

    stale = {
        **kwargs,
        "comparison": {**kwargs["comparison"], "generation_id": "9" * 32},
    }
    with pytest.raises(ValueError, match="runtime binding drift"):
        transition._validated_cafta_supersession_receipt(**stale)

    payload["supersession"]["all_corrected_yale_statutory_rates_match_axiom"] = False
    payload.pop("receipt_payload_sha256")
    payload["receipt_payload_sha256"] = producer.canonical_sha256(payload)
    _write_json(kwargs["path"], payload)
    with pytest.raises(ValueError, match="authorization or identity proof drift"):
        transition._validated_cafta_supersession_receipt(**kwargs)


def test_cafta_receipt_rejects_rehashed_definition_relabeling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs, payload = _cafta_receipt_inputs(tmp_path, monkeypatch)
    payload["definition"] = {
        **payload["definition"],
        "real_entry_frontier": "all real entries are proven duty-free",
    }
    payload.pop("receipt_payload_sha256")
    payload["receipt_payload_sha256"] = producer.canonical_sha256(payload)
    _write_json(kwargs["path"], payload)

    with pytest.raises(ValueError, match="lacks bounded defect evidence"):
        transition._validated_cafta_supersession_receipt(**kwargs)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("actual-case-feed", "predicate proof drift"),
        ("identity-population", "authorization or identity proof drift"),
        ("historical-mismatch", "authorization or identity proof drift"),
        ("defect-projection", "authorization or identity proof drift"),
        ("historical-census", "census drift"),
        ("fresh-census", "census drift"),
        ("runtime-tree", "minimal reproduction drift"),
        ("fake-rscript", "minimal reproduction drift"),
    ],
)
def test_cafta_receipt_rejects_rehashed_self_asserted_proof_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    kwargs, payload = _cafta_receipt_inputs(tmp_path, monkeypatch)
    if mutation == "actual-case-feed":
        payload["axiom_predicate_proof"]["actual_case_feed_projection_sha256"] = (
            "e" * 64
        )
    elif mutation == "identity-population":
        payload["supersession"]["historical_identity_population_sha256"] = "e" * 64
        payload["supersession"]["fresh_identity_population_sha256"] = "e" * 64
        kwargs["historical_identity_population_sha256"] = "e" * 64
        kwargs["fresh_identity_population_sha256"] = "e" * 64
    elif mutation == "historical-mismatch":
        payload["supersession"]["historical_mismatch_projection_sha256"] = "e" * 64
    elif mutation == "defect-projection":
        payload["supersession"]["historical_defect_projection_sha256"] = "e" * 64
        payload["supersession"]["fresh_defect_projection_sha256"] = "e" * 64
    elif mutation == "historical-census":
        payload["census"]["historical_artifact_rows_scanned"] += 1
    elif mutation == "fresh-census":
        payload["census"]["fresh_comparison_rows_scanned"] += 1
    elif mutation == "runtime-tree":
        payload["yale_reference_defect"]["deterministic_minimal_reproduction"][
            "r_runtime_tree"
        ]["bytes"] += 1
    else:
        payload["yale_reference_defect"]["deterministic_minimal_reproduction"][
            "rscript"
        ] = payload["producer"]["script"]
    payload.pop("receipt_payload_sha256")
    payload["receipt_payload_sha256"] = producer.canonical_sha256(payload)
    _write_json(kwargs["path"], payload)

    with pytest.raises(ValueError, match=message):
        transition._validated_cafta_supersession_receipt(**kwargs)


def test_cafta_tidy_eval_replay_rejects_path_shadow_rscript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "Rscript"
    fake.write_text(
        "#!/bin/sh\n"
        "printf 'r_version=4.3.0\\ndplyr_version=1.1.2\\n"
        "selected_conditions=full,fta\\n'\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    with pytest.raises(ValueError, match="Rscript runtime drift"):
        campaign._run_cafta_tidy_eval_reproduction()


def test_cafta_tidy_eval_replay_ignores_hostile_r_startup_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = tmp_path / "hostile.Rprofile"
    profile.write_text('stop("R profile must not execute")\n')
    monkeypatch.setenv("R_PROFILE_USER", str(profile))
    monkeypatch.setenv("R_LIBS_USER", str(tmp_path / "untrusted-library"))
    replay = campaign._run_cafta_tidy_eval_reproduction()
    assert replay["selected_conditions"] == "full,fta"
    assert replay["r_runtime_tree"] == campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT
    assert replay["dplyr_tree"] == campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT


def test_cafta_tidy_eval_replay_revalidates_runtime_after_prior_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert campaign._run_cafta_tidy_eval_reproduction()["result"].startswith("PASS")
    real_tree_receipt = campaign._directory_tree_receipt

    def drift_runtime(path: Path) -> dict:
        receipt = real_tree_receipt(path)
        if str(path) == campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT["path"]:
            receipt["bytes"] += 1
        return receipt

    monkeypatch.setattr(
        campaign,
        "_directory_tree_receipt",
        drift_runtime,
    )

    with pytest.raises(ValueError, match="R runtime tree drift"):
        campaign._run_cafta_tidy_eval_reproduction()


def test_transition_producer_rejects_opaque_reference_assumption(
    tmp_path: Path,
) -> None:
    build_inputs, _expected = _transition_build_inputs(_evidence(tmp_path))
    build_inputs["expected_reference_assumptions"] = {
        "yale_note16_metal_weight": {"opaque": "replacement"}
    }

    with pytest.raises(ValueError, match="reference-assumption provenance"):
        transition.build_receipt(**build_inputs)


def test_transition_producer_separates_annex_gap_and_conditional_heading(
    tmp_path: Path,
) -> None:
    residual_ids = {
        "section232-annex-brazil",
        "section232-heading-forced-labor",
    }

    def mutate(rows: list[dict]) -> None:
        for selector_id in residual_ids:
            row = rows[SELECTOR_IDS.index(selector_id)]
            row.update({"actual": 0.25, "delta": 0.25, "match": False})
            row["context"]["flags"]["entry_is_section_232_covered"] = False
            if "-heading-" in selector_id:
                row["context"]["flags"]["entry_is_s232_note33_vehicle_candidate"] = True

    inputs = _evidence(tmp_path, source_fresh_mutator=mutate)
    with pytest.raises(ValueError, match="still mismatches"):
        _build(inputs)
    build_inputs, _expected = _transition_build_inputs(inputs)

    receipt = transition.build_receipt(**build_inputs)
    by_parent = {item["parent_id"]: item for item in receipt["transitions"]}

    assert by_parent["section232-annex-brazil"]["children"] == [
        {
            **transition._child_ruling("section232-annex-brazil", ()),
            "parent_id": "section232-annex-brazil",
            "expected_units": 1,
            "expected_signature_count": 1,
            "expected_signature_population_sha256": by_parent[
                "section232-annex-brazil"
            ]["fresh_residual_population"]["signature_population_sha256"],
            "match": {
                **by_parent["section232-annex-brazil"]["parent_contract"]["match"],
                "line_class": {"flags": transition._child_flag_vector(())},
            },
        }
    ]
    defect_proof = by_parent["section232-annex-brazil"]["evidence"][
        "yale_annex_defect_source_proof"
    ]
    assert defect_proof["units"] == 1
    assert defect_proof["per_arm"]["annex_proclamation_prefix"]["units"] == 1
    heading = by_parent["section232-heading-forced-labor"]
    assert heading["evidence"]["classification"] == (
        "disjoint-conditional-reference-behavior"
    )
    assert heading["evidence"]["candidate_pattern_units"] == {
        "entry_is_s232_note33_vehicle_candidate": 1
    }
    assert heading["children"][0]["disposition"] == "explained_residual"
    assert heading["children"][0]["attribution"] == "reference-behavior"
    assert all(
        by_parent[parent_id]["status"] == "retired"
        for parent_id in set(SELECTOR_IDS) - residual_ids
    )


def test_transition_producer_rejects_inexact_conditional_heading_ruling(
    tmp_path: Path,
) -> None:
    selector_id = "section232-heading-brazil"

    def mutate(rows: list[dict]) -> None:
        row = rows[SELECTOR_IDS.index(selector_id)]
        row.update({"actual": 0.25, "delta": 0.25, "match": False})
        flags = row["context"]["flags"]
        flags["entry_is_section_232_covered"] = False
        flags["entry_is_s232_note33_vehicle_candidate"] = True
        # This unrelated declared qualifier keeps the row non-exempt, but it
        # means the heading residual is not the exact all-qualifiers-false class.
        flags["entry_is_note33_g_automobile_part"] = True

    build_inputs, _expected = _transition_build_inputs(
        _evidence(tmp_path, source_fresh_mutator=mutate)
    )

    with pytest.raises(ValueError, match="not an exact supported class"):
        transition.build_receipt(**build_inputs)


def test_transition_producer_rejects_expected_pattern_drift_without_freezing_counts(
    tmp_path: Path,
) -> None:
    selector_id = "section232-annex-brazil"

    def mutate(rows: list[dict]) -> None:
        row = rows[SELECTOR_IDS.index(selector_id)]
        row.update({"actual": 0.25, "delta": 0.25, "match": False})
        row["context"]["flags"]["entry_is_section_232_covered"] = False

    build_inputs, expected = _transition_build_inputs(
        _evidence(tmp_path, source_fresh_mutator=mutate)
    )
    expected[selector_id] = frozenset({("entry_is_s232_note33_auto_part_candidate",)})

    with pytest.raises(ValueError, match="transition pattern drift"):
        transition.build_receipt(**build_inputs)


def test_transition_producer_rejects_match_without_precedence_evidence(
    tmp_path: Path,
) -> None:
    def mutate(rows: list[dict]) -> None:
        flags = rows[0]["context"]["flags"]
        for name in flags:
            flags[name] = False
        flags[transition.NOTE16_WEIGHT_INPUT] = True

    build_inputs, _expected = _transition_build_inputs(
        _evidence(tmp_path, source_fresh_mutator=mutate)
    )

    with pytest.raises(ValueError, match="match lacks precedence evidence"):
        transition.build_receipt(**build_inputs)


def test_transition_producer_rejects_mismatch_with_precedence_evidence(
    tmp_path: Path,
) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[0].update({"actual": 0.25, "delta": 0.25, "match": False})

    build_inputs, _expected = _transition_build_inputs(
        _evidence(tmp_path, source_fresh_mutator=mutate)
    )

    with pytest.raises(ValueError, match="residual has invalid legal state"):
        transition.build_receipt(**build_inputs)


@pytest.mark.parametrize(
    "missing",
    (
        *transition.NOTE16_MEMBERSHIP_FLAGS,
        transition.NOTE16_METAL_CHAPTER_FLAG,
        transition.NOTE16_WEIGHT_INPUT,
    ),
)
def test_transition_flags_require_complete_note16_precedence_vector(
    missing: str,
) -> None:
    flags = _row(0, SELECTOR_IDS[0], fresh=True)["context"]["flags"]
    flags.pop(missing)

    with pytest.raises(ValueError, match="flag vector is malformed"):
        transition._typed_flags(flags, key=("case", "slot"))


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"entry_is_s232_note16_c_ii_derivative_aluminum_member": True}, True),
        (
            {
                "entry_is_s232_note16_c_vi_derivative_aluminum_candidate": True,
                transition.NOTE16_METAL_CHAPTER_FLAG: True,
            },
            True,
        ),
        (
            {
                "entry_is_s232_note16_c_vi_derivative_aluminum_candidate": True,
                transition.NOTE16_WEIGHT_INPUT: True,
            },
            True,
        ),
        (
            {"entry_is_s232_note16_c_vi_derivative_aluminum_candidate": True},
            False,
        ),
        (
            {
                "entry_is_s232_note16_c_ix_derivative_aluminum_candidate": True,
                transition.NOTE16_METAL_CHAPTER_FLAG: True,
            },
            True,
        ),
        (
            {
                "entry_is_s232_note16_c_ix_derivative_aluminum_candidate": True,
                transition.NOTE16_WEIGHT_INPUT: True,
            },
            True,
        ),
        (
            {"entry_is_s232_note16_c_ix_derivative_aluminum_candidate": True},
            False,
        ),
    ],
)
def test_note16_precedence_requires_membership_and_metal_or_weight(
    updates: dict[str, bool], expected: bool
) -> None:
    flags = _row(0, SELECTOR_IDS[0], fresh=True)["context"]["flags"]
    for name in flags:
        flags[name] = False
    flags.update(updates)

    assert transition._precedence_exempt(flags) is expected


def test_child_flag_vectors_are_exact_disjoint_and_ignore_metal_chapter() -> None:
    patterns = transition.ANNEX_RESIDUAL_PATTERNS
    vectors = {pattern: transition._child_flag_vector(pattern) for pattern in patterns}
    for pattern, vector in vectors.items():
        assert transition.NOTE16_METAL_CHAPTER_FLAG not in vector
        assert vector[transition.NOTE16_WEIGHT_INPUT] is True
        assert all(vector[name] is False for name in transition.NOTE16_MEMBERSHIP_FLAGS)
        for metal_chapter in (False, True):
            unit = {
                "flags": {
                    **vector,
                    transition.NOTE16_METAL_CHAPTER_FLAG: metal_chapter,
                }
            }
            matching = {
                candidate
                for candidate, candidate_vector in vectors.items()
                if campaign._match_line_class(unit, {"flags": candidate_vector})
            }
            assert matching == {pattern}


def test_transition_child_population_overlap_fails_closed() -> None:
    parent_id = "section232-heading-brazil"
    auto = ("entry_is_s232_note33_auto_part_candidate",)
    both = (
        "entry_is_s232_note33_auto_part_candidate",
        "entry_is_s232_note38_mhd_part_candidate",
    )
    signature = "a" * 64
    selectors = {
        parent_id: {
            "expected_units": 1,
            "match": {
                "slot": "brazil_section_301",
                "line_set": "preview-1311-synthetic",
                "delta": {"sign": "pos"},
            },
        }
    }
    parent_state = {
        parent_id: {
            "matches": 0,
            "residual": Counter({signature: 1}),
            "patterns": Counter(
                {
                    transition._pattern_name(auto): 1,
                    transition._pattern_name(both): 1,
                }
            ),
            "child_populations": {
                auto: Counter({signature: 1}),
                both: Counter({signature: 1}),
            },
            "defect_source_identities": [],
            "defect_source_arms": Counter(),
            "defect_source_populations": {},
            "defect_source_hts10": defaultdict(set),
        }
    }

    with pytest.raises(ValueError, match="child signature populations overlap"):
        transition._transition_items(
            selectors=selectors,
            parent_state=parent_state,
            expected_parent_patterns={parent_id: frozenset({auto, both})},
            expected_fallback_hts10=None,
            yale_source_receipt={},
        )


def test_annex_defect_binds_yale_derivative_fallback_source(
    tmp_path: Path,
) -> None:
    selector_id = "section232-annex-brazil"

    def mutate(rows: list[dict]) -> None:
        row = rows[SELECTOR_IDS.index(selector_id)]
        row.update({"actual": 0.25, "delta": 0.25, "match": False})
        row["context"]["flags"]["entry_is_section_232_covered"] = False

    inputs = _evidence(
        tmp_path,
        source_fresh_mutator=mutate,
        yale_annex_rows=("9999,1a,aluminum,proclamation,2026-04-06",),
        yale_derivative_rows=("0000000001,9903.85.08,aluminum,2025-08-18",),
    )
    build_inputs, _expected = _transition_build_inputs(inputs)
    build_inputs["expected_fallback_hts10"] = frozenset({"0000000001"})

    receipt = transition.build_receipt(**build_inputs)
    item = next(
        value for value in receipt["transitions"] if value["parent_id"] == selector_id
    )
    proof = item["evidence"]["yale_annex_defect_source_proof"]
    assert set(proof) == {
        "classification",
        "units",
        "per_arm",
        "pinned_yale_source",
    }
    assert proof["per_arm"]["legacy_derivative_fallback"]["units"] == 1
    assert proof["per_arm"]["legacy_derivative_fallback"]["hts10"] == ["0000000001"]


@pytest.mark.parametrize(
    ("annex_rows", "message"),
    [
        (
            (
                "0000,1a,aluminum,proclamation,2026-04-06",
                "0000,1b,aluminum,proclamation,2026-04-06",
            ),
            "ambiguous latest-effective Yale annex prefix",
        ),
        (
            ("0000,1a,aluminum,us_note_16,2026-04-06",),
            "does not prove the reference-defect class",
        ),
    ],
)
def test_annex_defect_rejects_ambiguous_or_nonparser_direct_source(
    tmp_path: Path, annex_rows: tuple[str, ...], message: str
) -> None:
    selector_id = "section232-annex-brazil"

    def mutate(rows: list[dict]) -> None:
        row = rows[SELECTOR_IDS.index(selector_id)]
        row.update({"actual": 0.25, "delta": 0.25, "match": False})
        row["context"]["flags"]["entry_is_section_232_covered"] = False

    build_inputs, _expected = _transition_build_inputs(
        _evidence(
            tmp_path,
            source_fresh_mutator=mutate,
            yale_annex_rows=annex_rows,
        )
    )

    with pytest.raises(ValueError, match=message):
        transition.build_receipt(**build_inputs)


def test_annex_defect_rejects_yale_parser_source_mutation(tmp_path: Path) -> None:
    inputs = _evidence(tmp_path)
    parser = inputs["yale_root"] / "scripts/parse_annex_products.R"
    parser.write_text(parser.read_text() + "# mutation\n")
    build_inputs, _expected = _transition_build_inputs(inputs)

    with pytest.raises(ValueError, match="annex parser source drift"):
        transition.build_receipt(**build_inputs)


def test_receipts_every_historical_section232_unit_as_a_unique_fresh_match(
    tmp_path: Path,
) -> None:
    receipt = _build(_evidence(tmp_path))

    assert receipt["verdict"] == "PASS"
    assert receipt["census"]["section232_units"] == 6
    assert receipt["equivalence"]["joined_historical_units"] == 6
    assert receipt["equivalence"]["all_present"] is True
    assert receipt["equivalence"]["all_unique"] is True
    assert receipt["equivalence"]["all_matching"] is True
    assert receipt["bindings"]["evaluated_cases"] == 6
    assert receipt["bindings"]["observed_evaluated_cases"] == 6
    assert receipt["bindings"]["campaign_producer_identity_required"] is False
    assert (
        receipt["equivalence"]["historical_identity_population_sha256"]
        == receipt["equivalence"]["fresh_identity_population_sha256"]
    )
    assert receipt["zero_error_proof"] == {
        "evaluation_shard_engine_errors": 0,
        "observed_evaluation_record_errors": 0,
        "comparison_receipt_engine_errors": 0,
        "comparison_artifact_engine_error_rows": 0,
    }


def test_distinct_preview_and_fresh_campaign_producers_are_explicitly_receipted(
    tmp_path: Path,
) -> None:
    receipt = _build(_evidence(tmp_path, distinct_campaign_producers=True))

    assert (
        receipt["bindings"]["preview_campaign_classifier_sha256"]
        != receipt["bindings"]["fresh_campaign_classifier_sha256"]
    )
    assert receipt["bindings"]["campaign_producer_identity_required"] is False


def test_missing_fresh_historical_identity_fails_closed(tmp_path: Path) -> None:
    inputs = _evidence(tmp_path, fresh_mutator=lambda rows: rows.pop())

    with pytest.raises(ValueError, match="missing 1 historical Section-232 identities"):
        _build(inputs)


def test_fresh_mismatch_fails_closed(tmp_path: Path) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[0].update({"match": False, "actual": 0.25, "delta": 0.25})

    inputs = _evidence(tmp_path, fresh_mutator=mutate)
    with pytest.raises(ValueError, match="still mismatches"):
        _build(inputs)


def test_match_true_with_nonzero_delta_fails_closed(tmp_path: Path) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[0].update({"match": True, "actual": 0.25, "delta": 0.25})

    inputs = _evidence(tmp_path, fresh_mutator=mutate)
    with pytest.raises(ValueError, match="matching arithmetic drift"):
        _build(inputs)


def test_duplicate_fresh_identity_fails_closed(tmp_path: Path) -> None:
    def mutate(rows: list[dict]) -> None:
        rows.append(dict(rows[0]))

    inputs = _evidence(tmp_path, fresh_mutator=mutate)
    with pytest.raises(ValueError, match="duplicate fresh Section-232 identity"):
        _build(inputs)


def test_fresh_legal_identity_drift_fails_closed(tmp_path: Path) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[0] = json.loads(json.dumps(rows[0]))
        rows[0]["context"]["revision"] = "mutated-revision"

    inputs = _evidence(tmp_path, fresh_mutator=mutate)
    with pytest.raises(ValueError, match="fresh Section-232 legal identity drift"):
        _build(inputs)


def test_duplicate_historical_identity_fails_closed(tmp_path: Path) -> None:
    def mutate(rows: list[dict]) -> None:
        rows.append(dict(rows[0]))

    inputs = _evidence(tmp_path, historical_mutator=mutate)
    with pytest.raises(ValueError, match="duplicate historical Section-232 identity"):
        _build(inputs)


def test_historical_cell_must_be_an_all_new_row(tmp_path: Path) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[0]["new_disagreement"] = False

    inputs = _evidence(tmp_path, historical_mutator=mutate)
    with pytest.raises(ValueError, match="is not an all-new row"):
        _build(inputs)


def test_artifact_engine_error_row_fails_even_if_summary_claims_zero(
    tmp_path: Path,
) -> None:
    def mutate(rows: list[dict]) -> None:
        rows.append(
            {
                "case_id": "schedule-" + "f" * 24,
                "slot": "engine_error",
                "match": False,
                "error": ["engine failed"],
                "delta": None,
            }
        )

    inputs = _evidence(tmp_path, fresh_mutator=mutate)
    with pytest.raises(ValueError, match="contains engine-error rows"):
        _build(inputs)


def test_evaluation_shard_engine_error_fails_closed(tmp_path: Path) -> None:
    inputs = _evidence(tmp_path, shard_engine_errors=1)
    with pytest.raises(ValueError, match="evaluation shard contains engine errors"):
        _build(inputs)


def test_truncated_eval_shard_with_stale_case_count_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _evidence(
        tmp_path,
        eval_mutator=lambda rows: rows.pop(),
        declared_shard_cases=6,
    )
    with pytest.raises(ValueError, match="evaluation shard case-count drift"):
        _build(inputs)


def test_hidden_eval_record_error_with_zero_counter_fails_closed(
    tmp_path: Path,
) -> None:
    def mutate(rows: list[dict]) -> None:
        rows[0]["engine_errors"] = ["hidden error"]

    inputs = _evidence(tmp_path, eval_mutator=mutate)
    with pytest.raises(ValueError, match="evaluation shard error-count drift"):
        _build(inputs)


def test_fabricated_fresh_match_disagrees_with_source_evaluation(
    tmp_path: Path,
) -> None:
    def mutate(rows: list[dict]) -> None:
        actual_field = next(iter(rows[0]["actual"]))
        rows[0]["actual"][actual_field] = 0.25

    inputs = _evidence(tmp_path, eval_mutator=mutate)
    with pytest.raises(ValueError, match="disagrees with source evaluation"):
        _build(inputs)


def test_self_consistent_preview_semantic_mutation_fails_closed(tmp_path: Path) -> None:
    inputs = _evidence(tmp_path)
    preview = Path(inputs["preview_receipt_path"])
    payload = producer.load_json(preview)
    payload["line_sets"][next(iter(payload["line_sets"]))]["values_sha256"] = "f" * 64
    payload.pop("receipt_payload_sha256")
    payload["receipt_payload_sha256"] = producer.canonical_sha256(payload)
    _write_json(preview, payload)

    with pytest.raises(
        ValueError, match="immutable preview Section-232 snapshot drift"
    ):
        _build(inputs)


def test_manifest_comparison_receipt_binding_mutation_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _evidence(tmp_path)
    comparison = Path(inputs["comparison_receipt_path"])
    comparison.write_text(comparison.read_text() + "\n")

    with pytest.raises(
        ValueError, match="manifest comparison-receipt binding is stale"
    ):
        _build(inputs)


def test_eval_shard_mutation_during_proof_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _evidence(tmp_path)
    original = producer._scan_fresh_comparison

    def mutate_after_scan(**kwargs):
        result = original(**kwargs)
        with (tmp_path / "cache/eval-shard.jsonl.gz").open("ab") as target:
            target.write(b"out-of-band mutation")
        return result

    monkeypatch.setattr(producer, "_scan_fresh_comparison", mutate_after_scan)
    with pytest.raises(
        ValueError,
        match="evaluation/comparison evidence changed during equivalence proof",
    ):
        _build(inputs)
