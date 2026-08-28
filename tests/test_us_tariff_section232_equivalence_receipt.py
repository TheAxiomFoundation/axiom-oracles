from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from scripts import build_us_tariff_section232_equivalence_receipt as producer


SELECTOR_IDS = tuple(sorted(producer.SECTION232_SELECTOR_UNITS))


def _write_gzip(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())


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
            "flags": {},
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


def _evidence(
    root: Path,
    *,
    historical_mutator=None,
    fresh_mutator=None,
    eval_mutator=None,
    declared_shard_cases: int | None = None,
    shard_engine_errors: int = 0,
    distinct_campaign_producers: bool = False,
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
                "expected_signature_population_sha256": "a" * 64,
                "match": {
                    "slot": slot,
                    "line_set": line_set_name,
                    "delta": {"sign": "pos"},
                },
            }
        )
    preview = {
        "schema": producer.PREVIEW_SCHEMA,
        "verdict": "PASS",
        "producer": {"campaign_classifier": preview_campaign_receipt},
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
        "census": {"per_selector": expected_units},
    }
    expected_preview_snapshot_sha256 = producer.canonical_sha256(
        producer.preview_section232_snapshot(preview, expected_units)
    )
    preview["receipt_payload_sha256"] = producer.canonical_sha256(preview)
    preview_path = root / "reference/us-tariff-schedule/preview-disposition-line-sets.json"
    _write_json(preview_path, preview)

    shard_path = root / "cache/eval-shard.jsonl.gz"
    _write_gzip(shard_path, eval_rows)
    run_identity = {
        "campaign_evaluator": {"campaign": campaign_receipt},
        "selected_population": producer.file_receipt(selected, relative_to=root),
        "chapters": {"01": {"module": "generated/ch01.yaml"}},
        "rulespec": {
            "root": "/rulespec",
            "head_commit": "b" * 40,
            "head_tree": "c" * 40,
            "content_sha256": "d" * 64,
        },
        "engine": {"path": "/engine", "bytes": 1, "sha256": "e" * 64},
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
        "per_slot": {
            slot: dict(counter) for slot, counter in sorted(per_slot.items())
        },
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
    }


def _build(inputs: dict) -> dict:
    return producer.build_receipt(**inputs)


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

    with pytest.raises(ValueError, match="immutable preview Section-232 snapshot drift"):
        _build(inputs)


def test_manifest_comparison_receipt_binding_mutation_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _evidence(tmp_path)
    comparison = Path(inputs["comparison_receipt_path"])
    comparison.write_text(comparison.read_text() + "\n")

    with pytest.raises(ValueError, match="manifest comparison-receipt binding is stale"):
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
        ValueError, match="evaluation/comparison evidence changed during equivalence proof"
    ):
        _build(inputs)
