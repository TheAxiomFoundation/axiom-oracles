#!/usr/bin/env python3
"""Prove that the six preview Section-232 gaps became fresh matches.

The preview receipt identifies 226,784 mismatching component cells split over
six Section-232 cohorts.  This producer joins every one of those historical
cells to the current comparison artifact by a stable campaign identity and
requires the current cell to be unique and matching.  It also validates the
complete evaluation/comparison binding and rejects any engine error.

This is intentionally a separate, read-only post-comparison producer.  It does
not modify the campaign manifest, comparison artifact, or classifier inputs.
"""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import math
import re
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator


REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER_SOURCE = Path(__file__).resolve()
PREVIEW_RECEIPT = (
    REPO_ROOT / "reference/us-tariff-schedule/preview-disposition-line-sets.json"
)
HISTORICAL_ARTIFACT = (
    REPO_ROOT
    / "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
)
EVAL_MANIFEST = REPO_ROOT / "reference/us-tariff-schedule/eval/MANIFEST.json"
COMPARISON_RECEIPT = (
    REPO_ROOT / "reference/us-tariff-schedule/comparison-summary.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "reference/us-tariff-schedule/section232-all-new-row-equivalence-receipt.json"
)

SCHEMA = "axiom_oracles.us_tariff_schedule.section232_all_new_row_equivalence.v1"
PREVIEW_SCHEMA = "axiom_oracles.us_tariff_schedule.preview_disposition_line_sets.v1"
EVAL_SCHEMA = "axiom_oracles.us_tariff_schedule.eval_manifest.v3"
COMPARISON_SCHEMA = "axiom_oracles.us_tariff_schedule.comparison_summary.v3"
HISTORICAL_LOGICAL_PATH = (
    "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
)
SELECTED_LOGICAL_PATH = "reference/us-tariff-schedule/selected-intervals.csv.gz"

# Producer receipts in the preview file legitimately change when the campaign
# implementation is refreshed.  Pin the producer-independent Section-232
# ruling instead: exact source receipts, Yale pins, definitions, six selector
# contracts, and their complete HTS10 line sets.  The output separately binds
# the actual preview file bytes and its self-authenticating payload digest.
EXPECTED_PREVIEW_SECTION232_SNAPSHOT_SHA256 = (
    "2bb3bd5afe52211ea3de1db1d02c795415b1c1fb85a17ed97b2b9f8bf42138f7"
)
SECTION232_SELECTOR_UNITS = {
    "section232-annex-brazil": 2_478,
    "section232-annex-forced-labor": 41_412,
    "section232-exposed-brazil": 9_096,
    "section232-exposed-forced-labor": 138_340,
    "section232-heading-brazil": 2_370,
    "section232-heading-forced-labor": 33_088,
}
TOLERANCE = 1e-12
HEX64 = re.compile(r"[0-9a-f]{64}")
CASE_ID = re.compile(r"schedule-[0-9a-f]{24}")
SLOT_EVAL_FIELDS = {
    "brazil_section_301": (
        "statutory_rate_s301br",
        "brazil_section_301_component_rate",
    ),
    "forced_labor_section_301": (
        "statutory_rate_s301fl",
        "forced_labor_section_301_component_rate",
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def parse_json(payload: str, *, label: str) -> Any:
    try:
        return json.loads(
            payload,
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_invalid_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {label}") from exc


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing JSON input: {path}")
    value = parse_json(path.read_text(), label=str(path))
    require(isinstance(value, dict), f"JSON input is not an object: {path}")
    return value


def _receipt_path(path: Path, repo_root: Path | None) -> str:
    resolved = path.resolve()
    if repo_root is None:
        return str(resolved)
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(resolved)


def file_receipt(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    require(resolved.is_file(), f"missing receipted file: {resolved}")
    return {
        "path": _receipt_path(resolved, relative_to),
        "bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def _valid_receipt(receipt: Any, *, label: str) -> dict[str, Any]:
    require(
        isinstance(receipt, dict)
        and set(receipt) == {"path", "bytes", "sha256"},
        f"malformed file receipt: {label}",
    )
    require(
        isinstance(receipt["path"], str)
        and bool(receipt["path"])
        and isinstance(receipt["bytes"], int)
        and not isinstance(receipt["bytes"], bool)
        and receipt["bytes"] >= 0
        and isinstance(receipt["sha256"], str)
        and HEX64.fullmatch(receipt["sha256"]) is not None,
        f"invalid file receipt fields: {label}",
    )
    return receipt


def _strict_nonnegative_int(value: Any, *, label: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"{label} must be a nonnegative integer",
    )
    return value


def _finite_number(value: Any, *, label: str) -> float:
    require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be a finite number",
    )
    return float(value)


def _finite_number_or_text(value: Any, *, label: str) -> float:
    """Parse selected-panel values, which are stored as CSV numeric text."""

    if isinstance(value, str):
        require(bool(value.strip()), f"{label} must be finite numeric text")
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be finite numeric text") from exc
        require(math.isfinite(number), f"{label} must be finite numeric text")
        return number
    return _finite_number(value, label=label)


def values_sha256(values: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def population_sha256(values: Iterable[dict[str, Any]]) -> str:
    """Hash a set-like population as sorted canonical JSON lines."""

    encoded = sorted(canonical(value) for value in values)
    digest = hashlib.sha256()
    for value in encoded:
        digest.update(value)
        digest.update(b"\n")
    return digest.hexdigest()


def preview_section232_snapshot(
    preview: dict[str, Any], expected_selector_units: dict[str, int]
) -> dict[str, Any]:
    """Project the immutable, producer-independent Section-232 ruling."""

    raw_selectors = preview.get("selectors")
    raw_line_sets = preview.get("line_sets")
    inputs = preview.get("inputs")
    census = preview.get("census", {}).get("per_selector")
    require(
        isinstance(raw_selectors, list)
        and isinstance(raw_line_sets, dict)
        and isinstance(inputs, dict)
        and isinstance(census, dict),
        "preview Section-232 snapshot inputs are malformed",
    )
    selectors = sorted(
        (
            item
            for item in raw_selectors
            if isinstance(item, dict) and item.get("id") in expected_selector_units
        ),
        key=lambda item: item["id"],
    )
    line_set_names = {
        item.get("match", {}).get("line_set")
        for item in selectors
        if isinstance(item.get("match"), dict)
    }
    require(
        len(selectors) == len(expected_selector_units)
        and None not in line_set_names
        and line_set_names <= set(raw_line_sets),
        "preview Section-232 snapshot coverage is malformed",
    )
    return {
        "schema": preview.get("schema"),
        # All six immutable preview sources are part of the ruling, including
        # the new-mismatch sidecar that establishes "all-new-row" status.
        "inputs": inputs,
        "yale_sources": preview.get("yale_sources"),
        "definition": preview.get("definition"),
        "selectors": selectors,
        "line_sets": {
            name: raw_line_sets[name] for name in sorted(line_set_names)
        },
        "census": {
            selector_id: census.get(selector_id)
            for selector_id in sorted(expected_selector_units)
        },
    }


def _validate_preview(
    path: Path,
    *,
    expected_snapshot_sha256: str,
    expected_selector_units: dict[str, int],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, frozenset[str]],
    dict[str, Any],
    dict[str, Any],
]:
    preview = load_json(path)
    require(
        preview.get("schema") == PREVIEW_SCHEMA and preview.get("verdict") == "PASS",
        "preview disposition receipt is not a PASS v1 receipt",
    )
    payload_sha256 = preview.get("receipt_payload_sha256")
    without_digest = dict(preview)
    without_digest.pop("receipt_payload_sha256", None)
    require(
        payload_sha256 == canonical_sha256(without_digest),
        "preview payload digest drift",
    )
    require(
        canonical_sha256(
            preview_section232_snapshot(preview, expected_selector_units)
        )
        == expected_snapshot_sha256,
        "immutable preview Section-232 snapshot drift",
    )

    inputs = preview.get("inputs")
    require(isinstance(inputs, dict), "preview input receipts are malformed")
    historical_receipt = _valid_receipt(
        inputs.get(HISTORICAL_LOGICAL_PATH), label=HISTORICAL_LOGICAL_PATH
    )
    selected_receipt = _valid_receipt(
        inputs.get(SELECTED_LOGICAL_PATH), label=SELECTED_LOGICAL_PATH
    )
    require(
        historical_receipt["path"] == HISTORICAL_LOGICAL_PATH
        and selected_receipt["path"] == SELECTED_LOGICAL_PATH,
        "preview input logical paths drifted",
    )

    raw_selectors = preview.get("selectors")
    raw_line_sets = preview.get("line_sets")
    require(
        isinstance(raw_selectors, list) and isinstance(raw_line_sets, dict),
        "preview selectors or line sets are malformed",
    )
    selectors: dict[str, dict[str, Any]] = {}
    line_sets: dict[str, frozenset[str]] = {}
    for item in raw_selectors:
        if not isinstance(item, dict) or item.get("id") not in expected_selector_units:
            continue
        selector_id = item["id"]
        require(selector_id not in selectors, f"duplicate Section-232 selector: {selector_id}")
        require(
            set(item)
            == {
                "id",
                "logical_class",
                "disposition",
                "attribution",
                "expected_units",
                "expected_signature_count",
                "expected_signature_population_sha256",
                "match",
            },
            f"Section-232 selector contract fields drifted: {selector_id}",
        )
        require(
            item["expected_units"] == expected_selector_units[selector_id],
            f"Section-232 preview unit census drifted: {selector_id}",
        )
        match = item.get("match")
        require(
            isinstance(match, dict)
            and set(match) == {"slot", "line_set", "delta"}
            and match.get("slot")
            in {"brazil_section_301", "forced_labor_section_301"}
            and match.get("delta") == {"sign": "pos"},
            f"Section-232 selector bounds drifted: {selector_id}",
        )
        expected_slot = (
            "brazil_section_301"
            if selector_id.endswith("-brazil")
            else "forced_labor_section_301"
        )
        require(
            match["slot"] == expected_slot,
            f"Section-232 selector slot drifted: {selector_id}",
        )
        line_set_name = match.get("line_set")
        receipt = raw_line_sets.get(line_set_name)
        require(
            isinstance(line_set_name, str) and isinstance(receipt, dict),
            f"missing Section-232 preview line set: {selector_id}",
        )
        values = receipt.get("values")
        require(
            receipt.get("width") == 10
            and isinstance(values, list)
            and values == sorted(set(values))
            and all(isinstance(value, str) and re.fullmatch(r"[0-9]{10}", value) for value in values)
            and receipt.get("value_count") == len(values)
            and receipt.get("values_sha256") == values_sha256(values),
            f"Section-232 preview line-set receipt drifted: {selector_id}",
        )
        selectors[selector_id] = item
        line_sets[line_set_name] = frozenset(values)
    require(
        set(selectors) == set(expected_selector_units),
        "preview receipt does not contain exactly the six Section-232 selectors",
    )
    census = preview.get("census", {}).get("per_selector")
    require(isinstance(census, dict), "preview selector census is malformed")
    require(
        {selector_id: census.get(selector_id) for selector_id in selectors}
        == expected_selector_units,
        "preview Section-232 selector census disagrees with contracts",
    )
    return preview, selectors, line_sets, historical_receipt, selected_receipt


def _resolve_receipted_path(path: str, repo_root: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _validate_eval_and_comparison_bindings(
    *,
    repo_root: Path,
    eval_manifest_path: Path,
    comparison_receipt_path: Path,
    preview: dict[str, Any],
    selected_receipt: dict[str, Any],
    historical_units: dict[tuple[str, str], dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    Path,
    dict[str, Any],
    dict[tuple[str, str], dict[str, Any]],
    list[dict[str, Any]],
]:
    manifest = load_json(eval_manifest_path)
    comparison = load_json(comparison_receipt_path)
    expected_manifest_fields = {
        "schema",
        "generation_id",
        "run_identity",
        "run_identity_sha256",
        "shards",
        "comparison_artifact",
        "comparison_receipt",
    }
    require(
        set(manifest) == expected_manifest_fields and manifest.get("schema") == EVAL_SCHEMA,
        "evaluation manifest is not a complete comparison-bound v3 manifest",
    )
    generation_id = manifest.get("generation_id")
    require(
        isinstance(generation_id, str) and re.fullmatch(r"[0-9a-f]{32}", generation_id),
        "evaluation generation id is malformed",
    )
    run_identity = manifest.get("run_identity")
    require(isinstance(run_identity, dict), "evaluation run identity is malformed")
    run_identity_sha256 = manifest.get("run_identity_sha256")
    require(
        isinstance(run_identity_sha256, str)
        and HEX64.fullmatch(run_identity_sha256) is not None
        and run_identity_sha256 == canonical_sha256(run_identity),
        "evaluation run-identity digest drift",
    )
    require(
        comparison.get("schema") == COMPARISON_SCHEMA,
        "comparison receipt is not schema v3",
    )
    require(
        comparison.get("generation_id") == generation_id
        and comparison.get("run_identity_sha256") == run_identity_sha256,
        "comparison receipt is bound to another evaluation run",
    )

    evaluation_only = {
        key: manifest[key]
        for key in (
            "schema",
            "shards",
            "run_identity",
            "run_identity_sha256",
            "generation_id",
        )
    }
    evaluation_manifest_sha256 = canonical_sha256(evaluation_only)
    require(
        comparison.get("evaluation_manifest_sha256") == evaluation_manifest_sha256,
        "comparison evaluation-manifest binding is stale",
    )

    actual_comparison_receipt = file_receipt(
        comparison_receipt_path, relative_to=repo_root
    )
    require(
        manifest.get("comparison_receipt") == actual_comparison_receipt,
        "manifest comparison-receipt binding is stale",
    )
    artifact_receipt = _valid_receipt(
        comparison.get("comparison_artifact"), label="comparison artifact"
    )
    artifact_path = _resolve_receipted_path(artifact_receipt["path"], repo_root)
    require(
        file_receipt(artifact_path) == artifact_receipt,
        "comparison artifact hash or size drift",
    )
    require(
        manifest.get("comparison_artifact") == artifact_receipt,
        "manifest comparison-artifact binding is stale",
    )

    comparison_engine_errors = _strict_nonnegative_int(
        comparison.get("engine_errors"), label="comparison engine_errors"
    )
    require(comparison_engine_errors == 0, "comparison receipt contains engine errors")
    tolerance = _finite_number(comparison.get("tolerance"), label="comparison tolerance")
    require(tolerance == TOLERANCE, "comparison tolerance drift")

    chapters = run_identity.get("chapters")
    shards = manifest.get("shards")
    require(
        isinstance(chapters, dict) and bool(chapters) and isinstance(shards, dict),
        "evaluation chapter or shard census is malformed",
    )
    observed_chapters: set[str] = set()
    evaluated_cases = 0
    observed_evaluated_cases = 0
    observed_evaluation_errors = 0
    source_eval_units: dict[tuple[str, str], dict[str, Any]] = {}
    shard_receipts: list[dict[str, Any]] = []
    wanted_by_case: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in historical_units:
        wanted_by_case[key[0]].append(key)
    for key, shard in shards.items():
        require(
            isinstance(key, str)
            and HEX64.fullmatch(key) is not None
            and isinstance(shard, dict),
            "evaluation shard identity is malformed",
        )
        chapter = shard.get("chapter")
        require(
            shard.get("key") == key
            and shard.get("run_identity_sha256") == run_identity_sha256
            and shard.get("generation_id") == generation_id
            and isinstance(chapter, str)
            and chapter in chapters
            and chapter not in observed_chapters,
            f"evaluation shard binding is malformed: {key}",
        )
        observed_chapters.add(chapter)
        declared_cases = _strict_nonnegative_int(
            shard.get("cases"), label=f"shard {chapter} cases"
        )
        declared_engine_errors = _strict_nonnegative_int(
            shard.get("engine_errors"), label=f"shard {chapter} engine_errors"
        )
        require(
            declared_engine_errors == 0,
            f"evaluation shard contains engine errors: {chapter}",
        )
        evaluated_cases += declared_cases
        shard_sha256 = shard.get("sha256")
        shard_path_value = shard.get("path")
        require(
            isinstance(shard_sha256, str)
            and HEX64.fullmatch(shard_sha256) is not None
            and isinstance(shard_path_value, str)
            and bool(shard_path_value),
            f"evaluation shard receipt is malformed: {chapter}",
        )
        shard_path = _resolve_receipted_path(shard_path_value, repo_root)
        shard_receipt = file_receipt(shard_path)
        require(
            shard_receipt["sha256"] == shard_sha256,
            f"evaluation shard artifact drift: {chapter}",
        )
        shard_receipts.append(shard_receipt)
        shard_records = 0
        shard_errors = 0
        for record in _iter_jsonl_gzip(shard_path):
            shard_records += 1
            require(
                record.get("chapter") == chapter,
                f"evaluation shard contains a foreign chapter record: {chapter}",
            )
            errors = record.get("engine_errors")
            require(
                isinstance(errors, list),
                f"evaluation record engine_errors is not a list: {chapter}/{shard_records}",
            )
            shard_errors += bool(errors)
            case_id = record.get("case_id")
            require(
                isinstance(case_id, str) and CASE_ID.fullmatch(case_id) is not None,
                f"evaluation record case_id is malformed: {chapter}/{shard_records}",
            )
            if errors:
                continue
            for historical_key in wanted_by_case.get(case_id, []):
                require(
                    historical_key not in source_eval_units,
                    f"duplicate source evaluation identity: {historical_key}",
                )
                slot = historical_key[1]
                expected_field, actual_field = SLOT_EVAL_FIELDS[slot]
                expected_values = record.get("expected")
                actual_values = record.get("actual")
                plan = record.get("plan")
                require(
                    isinstance(expected_values, dict)
                    and isinstance(actual_values, dict)
                    and isinstance(plan, dict)
                    and isinstance(plan.get("components"), list)
                    and slot in plan["components"],
                    f"source evaluation does not expose target slot: {historical_key}",
                )
                expected = _finite_number_or_text(
                    expected_values.get(expected_field),
                    label=f"source evaluation expected {historical_key}",
                )
                actual = _finite_number(
                    actual_values.get(actual_field),
                    label=f"source evaluation actual {historical_key}",
                )
                context = {
                    name: record.get(name)
                    for name in (
                        "hts10",
                        "hts_line",
                        "iso2",
                        "revision",
                        "interval",
                        "origin_regime",
                        "flags",
                    )
                }
                source_row = {
                    "case_id": case_id,
                    "slot": slot,
                    "expected": expected,
                    "actual": actual,
                    "delta": actual - expected,
                    "match": abs(actual - expected) <= TOLERANCE,
                    "context": context,
                }
                identity = _identity(source_row, label="source evaluation")
                require(
                    identity == historical_units[historical_key]["identity"],
                    f"source evaluation legal identity drift: {historical_key}",
                )
                flags = context.get("flags")
                require(
                    isinstance(flags, dict)
                    and all(
                        isinstance(name, str) and isinstance(value, bool)
                        for name, value in flags.items()
                    ),
                    f"source evaluation flag vector is malformed: {historical_key}",
                )
                source_eval_units[historical_key] = {
                    "selector": historical_units[historical_key]["selector"],
                    "identity": identity,
                    "evaluation_record": {
                        "chapter": chapter,
                        "probe": record.get("probe"),
                        "country": record.get("country"),
                    },
                    "comparison": source_row,
                    "projection": {
                        "selector": historical_units[historical_key]["selector"],
                        "identity": identity,
                        "fresh_actual": actual,
                        "fresh_delta": actual - expected,
                        "match": source_row["match"],
                        "current_flag_vector": flags,
                    },
                }
        require(
            shard_records == declared_cases,
            f"evaluation shard case-count drift: {chapter}: "
            f"declared {declared_cases}, observed {shard_records}",
        )
        require(
            shard_errors == declared_engine_errors == 0,
            f"evaluation shard error-count drift: {chapter}: "
            f"declared {declared_engine_errors}, observed {shard_errors}",
        )
        observed_evaluated_cases += shard_records
        observed_evaluation_errors += shard_errors
        require(
            file_receipt(shard_path) == shard_receipt,
            f"evaluation shard changed during record audit: {chapter}",
        )
    require(
        observed_chapters == set(chapters),
        "evaluation manifest is incomplete or contains foreign chapters",
    )

    campaign_receipt = _valid_receipt(
        run_identity.get("campaign_evaluator", {}).get("campaign"),
        label="fresh campaign producer",
    )
    preview_campaign_receipt = _valid_receipt(
        preview.get("producer", {}).get("campaign_classifier"),
        label="preview campaign producer",
    )
    require(
        set(source_eval_units) == set(historical_units),
        "fresh evaluation shards do not contain every historical Section-232 identity",
    )
    require(
        run_identity.get("selected_population") == selected_receipt,
        "fresh evaluation selected population differs from immutable preview",
    )
    selected_path = _resolve_receipted_path(selected_receipt["path"], repo_root)
    require(
        file_receipt(selected_path, relative_to=repo_root) == selected_receipt,
        "selected population artifact hash or size drift",
    )
    binding_audit = {
        "generation_id": generation_id,
        "run_identity_sha256": run_identity_sha256,
        "evaluation_manifest_sha256": evaluation_manifest_sha256,
        "evaluated_chapters": len(observed_chapters),
        "evaluated_cases": evaluated_cases,
        "observed_evaluated_cases": observed_evaluated_cases,
        "evaluation_shard_engine_errors": 0,
        "observed_evaluation_record_errors": observed_evaluation_errors,
        "comparison_receipt_engine_errors": 0,
        "preview_campaign_classifier_sha256": preview_campaign_receipt["sha256"],
        "fresh_campaign_classifier_sha256": campaign_receipt["sha256"],
        "campaign_producer_identity_required": False,
        "campaign_semantic_equivalence_basis": (
            "identical selected population plus an exact per-unit historical-to-source-"
            "evaluation-to-comparison identity and arithmetic replay"
        ),
    }
    return (
        manifest,
        comparison,
        artifact_path,
        binding_audit,
        source_eval_units,
        shard_receipts,
    )


def _identity(row: dict[str, Any], *, label: str) -> dict[str, Any]:
    case_id = row.get("case_id")
    slot = row.get("slot")
    context = row.get("context")
    require(
        isinstance(case_id, str) and CASE_ID.fullmatch(case_id) is not None,
        f"{label} case_id is malformed",
    )
    require(
        slot in {"brazil_section_301", "forced_labor_section_301"},
        f"{label} authority slot is malformed",
    )
    require(isinstance(context, dict), f"{label} context is malformed")
    interval = context.get("interval")
    require(
        isinstance(interval, list)
        and len(interval) == 2
        and all(isinstance(value, str) and bool(value) for value in interval),
        f"{label} interval is malformed",
    )
    scalar_fields = ("hts10", "hts_line", "iso2", "revision", "origin_regime")
    require(
        all(isinstance(context.get(field), str) and bool(context[field]) for field in scalar_fields),
        f"{label} legal context is malformed",
    )
    require(
        re.fullmatch(r"[0-9]{10}", context["hts10"]) is not None
        and re.fullmatch(r"[0-9]{10}", context["hts_line"]) is not None
        and re.fullmatch(r"[A-Z]{2}", context["iso2"]) is not None,
        f"{label} tariff/origin identity is malformed",
    )
    return {
        "case_id": case_id,
        "slot": slot,
        "hts10": context["hts10"],
        "hts_line": context["hts_line"],
        "iso2": context["iso2"],
        "revision": context["revision"],
        "interval": interval,
        "origin_regime": context["origin_regime"],
        "expected": _finite_number(row.get("expected"), label=f"{label} expected"),
    }


def _identity_key(identity: dict[str, Any]) -> tuple[str, str]:
    return identity["case_id"], identity["slot"]


def _historical_selector(
    row: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    line_sets: dict[str, frozenset[str]],
) -> str | None:
    slot = row.get("slot")
    context = row.get("context")
    if not isinstance(context, dict) or not isinstance(context.get("hts10"), str):
        return None
    delta = _finite_number(row.get("delta"), label="historical delta")
    matches = [
        selector_id
        for selector_id, selector in selectors.items()
        if slot == selector["match"]["slot"]
        and delta > 0
        and context["hts10"] in line_sets[selector["match"]["line_set"]]
    ]
    require(
        len(matches) <= 1,
        f"historical Section-232 selector overlap: {matches}",
    )
    return matches[0] if matches else None


def _iter_jsonl_gzip(path: Path) -> Iterator[dict[str, Any]]:
    require(path.is_file(), f"missing gzip JSONL input: {path}")
    try:
        with gzip.open(path, "rt") as source:
            for line_number, line in enumerate(source, 1):
                row = parse_json(line, label=f"{path}:{line_number}")
                require(
                    isinstance(row, dict),
                    f"JSONL row is not an object: {path}:{line_number}",
                )
                yield row
    except (EOFError, OSError) as exc:
        raise ValueError(f"invalid gzip artifact: {path}") from exc


def _load_historical_units(
    *,
    path: Path,
    expected_receipt: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    line_sets: dict[str, frozenset[str]],
    expected_selector_units: dict[str, int],
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    int,
]:
    require(
        path.stat().st_size == expected_receipt["bytes"]
        and sha256(path) == expected_receipt["sha256"],
        "historical target mismatch artifact does not match immutable preview",
    )
    units: dict[tuple[str, str], dict[str, Any]] = {}
    identities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    projections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_scanned = 0
    for row in _iter_jsonl_gzip(path):
        rows_scanned += 1
        selector_id = _historical_selector(row, selectors, line_sets)
        if selector_id is None:
            continue
        require(
            row.get("new_disagreement") is True
            and row.get("old_target_class") is None,
            f"Section-232 historical cell is not an all-new row: {row.get('case_id')}",
        )
        identity = _identity(row, label="historical")
        key = _identity_key(identity)
        require(key not in units, f"duplicate historical Section-232 identity: {key}")
        actual = _finite_number(row.get("actual"), label="historical actual")
        delta = _finite_number(row.get("delta"), label="historical delta")
        require(
            abs((actual - identity["expected"]) - delta) <= TOLERANCE,
            f"historical mismatch arithmetic drift: {key}",
        )
        require(abs(delta) > TOLERANCE, f"historical Section-232 cell was not a mismatch: {key}")
        units[key] = {"selector": selector_id, "identity": identity}
        identities[selector_id].append(identity)
        projections[selector_id].append(
            {
                "selector": selector_id,
                "identity": identity,
                "historical_actual": actual,
                "historical_delta": delta,
            }
        )
    census = {selector_id: len(identities[selector_id]) for selector_id in selectors}
    require(
        census == expected_selector_units,
        f"historical Section-232 identity census drift: {census}",
    )
    return units, dict(identities), dict(projections), rows_scanned


def _normalized_per_slot(value: Any) -> dict[str, dict[str, int]]:
    require(isinstance(value, dict), "comparison per-slot census is malformed")
    normalized: dict[str, dict[str, int]] = {}
    for slot, states in value.items():
        require(isinstance(slot, str) and isinstance(states, dict), "comparison per-slot entry is malformed")
        normalized[slot] = {
            state: _strict_nonnegative_int(units, label=f"comparison {slot}/{state}")
            for state, units in states.items()
        }
        require(
            set(normalized[slot]) <= {"match", "mismatch"}
            and bool(normalized[slot]),
            f"comparison per-slot states are malformed: {slot}",
        )
    return normalized


def _scan_fresh_comparison(
    *,
    path: Path,
    comparison: dict[str, Any],
    historical_units: dict[tuple[str, str], dict[str, Any]],
    source_eval_units: dict[tuple[str, str], dict[str, Any]],
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
]:
    found: set[tuple[str, str]] = set()
    identities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    projections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    per_slot: dict[str, Counter[str]] = defaultdict(Counter)
    rows_scanned = 0
    engine_error_rows = 0
    tolerance = _finite_number(comparison.get("tolerance"), label="comparison tolerance")
    for row in _iter_jsonl_gzip(path):
        rows_scanned += 1
        case_id = row.get("case_id")
        slot = row.get("slot")
        matched = row.get("match")
        require(
            isinstance(case_id, str) and isinstance(slot, str) and isinstance(matched, bool),
            f"fresh comparison row lacks typed identity/match state at row {rows_scanned}",
        )
        state = "match" if matched else "mismatch"
        per_slot[slot][state] += 1
        if slot == "engine_error":
            engine_error_rows += 1
            continue
        key = (case_id, slot)
        historical = historical_units.get(key)
        if historical is None:
            continue
        require(key not in found, f"duplicate fresh Section-232 identity: {key}")
        found.add(key)
        identity = _identity(row, label="fresh")
        require(
            identity == historical["identity"],
            f"fresh Section-232 legal identity drift: {key}",
        )
        require(matched is True, f"fresh Section-232 cell still mismatches: {key}")
        source_eval = source_eval_units.get(key)
        require(
            isinstance(source_eval, dict),
            f"fresh Section-232 cell lacks source evaluation: {key}",
        )
        source_comparison = source_eval["comparison"]
        require(
            row.get("context") == source_comparison["context"]
            and matched is source_comparison["match"],
            f"fresh comparison row disagrees with source evaluation: {key}",
        )
        actual = _finite_number(row.get("actual"), label="fresh actual")
        delta = _finite_number(row.get("delta"), label="fresh delta")
        require(
            abs(delta) <= tolerance
            and abs(actual - identity["expected"]) <= tolerance
            and abs((actual - identity["expected"]) - delta) <= tolerance,
            f"fresh Section-232 matching arithmetic drift: {key}",
        )
        require(
            abs(actual - source_comparison["actual"]) <= tolerance
            and abs(identity["expected"] - source_comparison["expected"]) <= tolerance
            and abs(delta - source_comparison["delta"]) <= tolerance,
            f"fresh comparison arithmetic disagrees with source evaluation: {key}",
        )
        selector_id = historical["selector"]
        identities[selector_id].append(identity)
        projections[selector_id].append(
            {
                "selector": selector_id,
                "identity": identity,
                "fresh_actual": actual,
                "fresh_delta": delta,
                "match": True,
            }
        )
    require(engine_error_rows == 0, "fresh comparison artifact contains engine-error rows")
    missing = set(historical_units) - found
    require(
        not missing,
        f"fresh comparison is missing {len(missing)} historical Section-232 identities",
    )
    observed_per_slot = {
        slot: dict(counter) for slot, counter in sorted(per_slot.items())
    }
    require(
        observed_per_slot == _normalized_per_slot(comparison.get("per_slot")),
        "comparison artifact per-slot census disagrees with receipt",
    )
    audit = {
        "comparison_rows_scanned": rows_scanned,
        "engine_error_rows": engine_error_rows,
        "joined_historical_units": len(found),
        "missing_historical_units": 0,
        "duplicate_historical_identities": 0,
        "duplicate_fresh_identities": 0,
        "fresh_mismatching_units": 0,
    }
    return dict(identities), dict(projections), audit


@contextmanager
def _manifest_lock(eval_manifest_path: Path) -> Iterator[None]:
    lock_path = eval_manifest_path.with_name(f".{eval_manifest_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def build_receipt(
    *,
    repo_root: Path,
    producer_source: Path,
    preview_receipt_path: Path,
    historical_artifact_path: Path,
    eval_manifest_path: Path,
    comparison_receipt_path: Path,
    expected_preview_snapshot_sha256: str = (
        EXPECTED_PREVIEW_SECTION232_SNAPSHOT_SHA256
    ),
    expected_selector_units: dict[str, int] = SECTION232_SELECTOR_UNITS,
) -> dict[str, Any]:
    producer = file_receipt(producer_source, relative_to=repo_root)
    preview_file = file_receipt(preview_receipt_path, relative_to=repo_root)
    preview, selectors, line_sets, historical_receipt, selected_receipt = _validate_preview(
        preview_receipt_path,
        expected_snapshot_sha256=expected_preview_snapshot_sha256,
        expected_selector_units=expected_selector_units,
    )
    require(
        historical_artifact_path.is_file(),
        f"historical target mismatch artifact is unavailable: {historical_artifact_path}",
    )
    historical_units, historical_identities, historical_rows, historical_rows_scanned = (
        _load_historical_units(
            path=historical_artifact_path,
            expected_receipt=historical_receipt,
            selectors=selectors,
            line_sets=line_sets,
            expected_selector_units=expected_selector_units,
        )
    )

    with _manifest_lock(eval_manifest_path):
        manifest_file = file_receipt(eval_manifest_path, relative_to=repo_root)
        comparison_file = file_receipt(comparison_receipt_path, relative_to=repo_root)
        (
            manifest,
            comparison,
            comparison_artifact_path,
            binding_audit,
            source_eval_units,
            shard_receipts,
        ) = (
            _validate_eval_and_comparison_bindings(
                repo_root=repo_root,
                eval_manifest_path=eval_manifest_path,
                comparison_receipt_path=comparison_receipt_path,
                preview=preview,
                selected_receipt=selected_receipt,
                historical_units=historical_units,
            )
        )
        fresh_identities, fresh_rows, fresh_audit = _scan_fresh_comparison(
            path=comparison_artifact_path,
            comparison=comparison,
            historical_units=historical_units,
            source_eval_units=source_eval_units,
        )

        # The campaign lock prevents sanctioned manifest transitions.  These
        # repeated receipts also reject out-of-band mutation during the scan.
        require(
            file_receipt(eval_manifest_path, relative_to=repo_root) == manifest_file
            and file_receipt(comparison_receipt_path, relative_to=repo_root)
            == comparison_file
            and file_receipt(comparison_artifact_path)
            == comparison["comparison_artifact"]
            and all(
                file_receipt(Path(receipt["path"])) == receipt
                for receipt in shard_receipts
            ),
            "evaluation/comparison evidence changed during equivalence proof",
        )

    per_selector: dict[str, dict[str, Any]] = {}
    all_historical_labeled: list[dict[str, Any]] = []
    all_fresh_labeled: list[dict[str, Any]] = []
    all_historical_rows: list[dict[str, Any]] = []
    all_source_eval_rows: list[dict[str, Any]] = []
    all_fresh_rows: list[dict[str, Any]] = []
    source_eval_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_eval in source_eval_units.values():
        source_eval_rows[source_eval["selector"]].append(source_eval["projection"])
    for selector_id in sorted(selectors):
        old_identities = historical_identities[selector_id]
        new_identities = fresh_identities[selector_id]
        require(
            len(old_identities) == len(new_identities) == expected_selector_units[selector_id],
            f"Section-232 equivalence census drift: {selector_id}",
        )
        old_labeled = [
            {"selector": selector_id, "identity": identity}
            for identity in old_identities
        ]
        new_labeled = [
            {"selector": selector_id, "identity": identity}
            for identity in new_identities
        ]
        old_digest = population_sha256(old_labeled)
        new_digest = population_sha256(new_labeled)
        require(
            old_digest == new_digest,
            f"Section-232 fresh identity population drift: {selector_id}",
        )
        per_selector[selector_id] = {
            "units": len(old_identities),
            "historical_identity_population_sha256": old_digest,
            "fresh_identity_population_sha256": new_digest,
            "historical_mismatch_projection_sha256": population_sha256(
                historical_rows[selector_id]
            ),
            "fresh_source_evaluation_projection_sha256": population_sha256(
                source_eval_rows[selector_id]
            ),
            "fresh_match_projection_sha256": population_sha256(
                fresh_rows[selector_id]
            ),
            "all_present": True,
            "all_unique": True,
            "all_matching": True,
        }
        all_historical_labeled.extend(old_labeled)
        all_fresh_labeled.extend(new_labeled)
        all_historical_rows.extend(historical_rows[selector_id])
        all_source_eval_rows.extend(source_eval_rows[selector_id])
        all_fresh_rows.extend(fresh_rows[selector_id])

    total_units = sum(expected_selector_units.values())
    require(
        len(historical_units) == total_units,
        "aggregate Section-232 equivalence census drift",
    )
    historical_identity_sha256 = population_sha256(all_historical_labeled)
    fresh_identity_sha256 = population_sha256(all_fresh_labeled)
    require(
        historical_identity_sha256 == fresh_identity_sha256,
        "aggregate fresh Section-232 identity population drift",
    )

    rulespec = manifest["run_identity"].get("rulespec")
    engine = manifest["run_identity"].get("engine")
    require(
        isinstance(rulespec, dict) and isinstance(engine, dict),
        "evaluation RuleSpec or engine identity is malformed",
    )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "producer": {"script": producer},
        "definition": {
            "historical_scope": (
                "the six immutable preview Section-232 selectors; every selected "
                "cell must be a preview new_disagreement row"
            ),
            "stable_identity": [
                "case_id",
                "slot",
                "hts10",
                "hts_line",
                "iso2",
                "revision",
                "interval",
                "origin_regime",
                "expected",
            ],
            "excluded_from_identity": (
                "entry flags and Axiom actual/delta values, because the RuleSpec "
                "change is expected to change those fields"
            ),
            "population_hash": (
                "SHA-256 over sorted canonical JSON records, one record per line "
                "with a final newline"
            ),
            "equivalence_condition": (
                "each historical identity occurs exactly once in the fresh comparison, "
                "has match=true, finite zero-within-tolerance delta, and actual equals "
                "the unchanged Yale expected value; every fresh row is independently "
                "replayed from its uniquely joined source evaluation record"
            ),
        },
        "inputs": {
            "immutable_preview_receipt": preview_file,
            "historical_target_mismatch_artifact": historical_receipt,
            "evaluation_manifest": manifest_file,
            "comparison_receipt": comparison_file,
            "comparison_artifact": comparison["comparison_artifact"],
        },
        "bindings": {
            "preview_receipt_payload_sha256": preview["receipt_payload_sha256"],
            "preview_section232_snapshot_sha256": canonical_sha256(
                preview_section232_snapshot(preview, expected_selector_units)
            ),
            "selected_population_sha256": selected_receipt["sha256"],
            **binding_audit,
            "rulespec": rulespec,
            "engine": engine,
        },
        "zero_error_proof": {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": fresh_audit["engine_error_rows"],
        },
        "census": {
            "historical_artifact_rows_scanned": historical_rows_scanned,
            "fresh_comparison_rows_scanned": fresh_audit["comparison_rows_scanned"],
            "section232_units": total_units,
            "per_selector": {
                selector_id: expected_selector_units[selector_id]
                for selector_id in sorted(expected_selector_units)
            },
        },
        "equivalence": {
            "historical_identity_population_sha256": historical_identity_sha256,
            "fresh_identity_population_sha256": fresh_identity_sha256,
            "historical_mismatch_projection_sha256": population_sha256(
                all_historical_rows
            ),
            "fresh_source_evaluation_projection_sha256": population_sha256(
                all_source_eval_rows
            ),
            "fresh_match_projection_sha256": population_sha256(all_fresh_rows),
            "joined_historical_units": fresh_audit["joined_historical_units"],
            "missing_historical_units": 0,
            "duplicate_historical_identities": 0,
            "duplicate_fresh_identities": 0,
            "fresh_mismatching_units": 0,
            "all_present": True,
            "all_unique": True,
            "all_matching": True,
            "per_selector": per_selector,
        },
    }
    payload["receipt_payload_sha256"] = canonical_sha256(payload)
    require(
        file_receipt(producer_source, relative_to=repo_root) == producer
        and file_receipt(preview_receipt_path, relative_to=repo_root) == preview_file
        and historical_artifact_path.stat().st_size == historical_receipt["bytes"]
        and sha256(historical_artifact_path) == historical_receipt["sha256"],
        "producer or immutable historical inputs changed during receipt build",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-receipt", type=Path, default=PREVIEW_RECEIPT)
    parser.add_argument("--historical-artifact", type=Path, default=HISTORICAL_ARTIFACT)
    parser.add_argument("--eval-manifest", type=Path, default=EVAL_MANIFEST)
    parser.add_argument("--comparison-receipt", type=Path, default=COMPARISON_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="compare generated bytes; do not write")
    args = parser.parse_args()

    receipt = build_receipt(
        repo_root=REPO_ROOT,
        producer_source=PRODUCER_SOURCE,
        preview_receipt_path=args.preview_receipt.resolve(),
        historical_artifact_path=args.historical_artifact.resolve(),
        eval_manifest_path=args.eval_manifest.resolve(),
        comparison_receipt_path=args.comparison_receipt.resolve(),
    )
    output = render(receipt)
    if args.check:
        require(args.output.is_file(), f"generated receipt missing: {args.output}")
        require(args.output.read_text() == output, f"generated receipt drift: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=args.output.parent, delete=False) as target:
            target.write(output)
            temporary = Path(target.name)
        temporary.replace(args.output)
    print(
        render(
            {
                "verdict": receipt["verdict"],
                "output": str(args.output.resolve()),
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "section232_units": receipt["census"]["section232_units"],
                "selectors": len(receipt["census"]["per_selector"]),
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
