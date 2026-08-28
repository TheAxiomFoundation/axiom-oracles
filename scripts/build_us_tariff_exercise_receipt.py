#!/usr/bin/env python3
"""Rebuild the committed exercise receipt for the US tariff campaign.

The schedule campaign is too large for committed per-case chunks.  Its eval
manifest content-addresses the external shard bodies instead.  This producer
verifies those bindings, scans every shard record, and derives the exact input
cardinalities consumed by the strict bridge manifest.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_REL = Path("reference/us-tariff-schedule/eval/MANIFEST.json")
COMPARISON_REL = Path("reference/us-tariff-schedule/comparison-summary.json")
REPORT_REL = Path("conformance/detail/us-tariff-schedule.json")
RECEIPT_REL = Path(
    "axiom_oracles/bridges/exercise_receipts/us-tariff-schedule.json"
)
CAMPAIGN_REL = Path("scripts/us_tariff_schedule_campaign.py")
SUITE = "us-tariff-schedule"
RECEIPT_SCHEMA = "axiom_oracles.committed_exercise_receipt.v1"
MANIFEST_SCHEMA = "axiom_oracles.us_tariff_schedule.eval_manifest.v3"
COMPARISON_SCHEMA = "axiom_oracles.us_tariff_schedule.comparison_summary.v3"
MAPPED_FIELDS = {
    "hts_number": "hts10",
    "hts_line": "hts_line",
    "country_of_origin": "iso2",
    "entry_date": "probe",
    "origin_regime": "origin_regime",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def _load_json(path: Path, label: str) -> dict[str, Any]:
    _require(path.is_file(), f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label}: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object: {path}")
    return value


def _file_receipt(path: Path, *, repo_root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    _require(resolved.is_file(), f"missing evidence file: {resolved}")
    try:
        rendered_path = str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        rendered_path = str(resolved)
    return {
        "path": rendered_path,
        "bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _load_campaign(repo_root: Path) -> ModuleType:
    path = repo_root / CAMPAIGN_REL
    module_name = "_tariff_exercise_receipt_campaign_" + _sha256(path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    _require(spec is not None and spec.loader is not None, "cannot load campaign")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validated_evidence(
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = repo_root / MANIFEST_REL
    comparison_path = repo_root / COMPARISON_REL
    report_path = repo_root / REPORT_REL
    manifest = _load_json(manifest_path, "evaluation manifest")
    comparison = _load_json(comparison_path, "comparison receipt")
    report = _load_json(report_path, "campaign report")

    _require(manifest.get("schema") == MANIFEST_SCHEMA, "stale eval manifest schema")
    _require(
        comparison.get("schema") == COMPARISON_SCHEMA,
        "stale comparison receipt schema",
    )
    _require(report.get("suite") == SUITE, "campaign report suite drift")
    _require(
        report.get("summary", {}).get("engine_errors") == 0,
        "campaign report contains engine errors",
    )

    generation_id = manifest.get("generation_id")
    run_identity_sha256 = manifest.get("run_identity_sha256")
    _require(
        isinstance(generation_id, str)
        and re.fullmatch(r"[0-9a-f]{32}", generation_id) is not None,
        "invalid eval generation id",
    )
    _require(
        isinstance(run_identity_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", run_identity_sha256) is not None,
        "invalid eval run-identity hash",
    )
    _require(
        comparison.get("generation_id") == generation_id
        and comparison.get("run_identity_sha256") == run_identity_sha256,
        "comparison does not bind the eval generation",
    )
    evaluation_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in {"comparison_artifact", "comparison_receipt"}
    }
    _require(
        comparison.get("evaluation_manifest_sha256")
        == _canonical_sha256(evaluation_manifest),
        "comparison does not bind the pre-comparison eval manifest",
    )
    comparison_artifact = comparison.get("comparison_artifact")
    _require(
        isinstance(comparison_artifact, dict)
        and manifest.get("comparison_artifact") == comparison_artifact,
        "eval manifest comparison-artifact binding is absent or stale",
    )
    artifact_path = Path(str(comparison_artifact.get("path", "")))
    _require(
        artifact_path.is_file()
        and comparison_artifact == _file_receipt(artifact_path, repo_root=repo_root),
        "comparison artifact is absent or stale",
    )
    _require(
        manifest.get("comparison_receipt")
        == _file_receipt(comparison_path, repo_root=repo_root),
        "eval manifest comparison-receipt binding is absent or stale",
    )
    _require(comparison.get("engine_errors") == 0, "comparison contains engine errors")

    run_identity = manifest.get("run_identity")
    _require(isinstance(run_identity, dict), "eval manifest lacks run identity")
    _require(
        _canonical_sha256(run_identity) == run_identity_sha256,
        "eval run-identity hash drift",
    )
    input_contract_ref = run_identity.get("input_contract")
    _require(isinstance(input_contract_ref, dict), "run identity lacks input contract")
    input_contract_path = repo_root / str(input_contract_ref.get("path", ""))
    _require(
        input_contract_ref == _file_receipt(input_contract_path, repo_root=repo_root)
        | {"schema": input_contract_ref.get("schema")},
        "eval input-contract binding is absent or stale",
    )
    input_contract = _load_json(input_contract_path, "declared-input contract")
    _require(
        input_contract.get("schema") == input_contract_ref.get("schema"),
        "declared-input contract schema drift",
    )

    campaign_ref = run_identity.get("campaign_evaluator", {}).get("campaign")
    _require(
        campaign_ref == _file_receipt(repo_root / CAMPAIGN_REL, repo_root=repo_root),
        "campaign source differs from the evaluated producer",
    )
    return manifest, comparison, report, input_contract


def _input_catalog(
    input_contract: dict[str, Any],
    campaign: ModuleType,
    *,
    expected_chapter_count: int,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    emitted = input_contract.get("emitted_entry_flags")
    dropped = input_contract.get("expected_dropped_entry_flags")
    neutrals = input_contract.get("neutral_boolean_inputs")
    probe_block = input_contract.get("probe_boolean_inputs", {})
    _require(
        isinstance(emitted, list)
        and isinstance(dropped, list)
        and isinstance(neutrals, list)
        and isinstance(probe_block, dict),
        "declared-input contract has malformed input catalogs",
    )
    _require(
        all(isinstance(name, str) and name for name in emitted + dropped + neutrals)
        and all(isinstance(name, str) and name for name in probe_block),
        "declared-input contract contains malformed input names",
    )
    projected = tuple(sorted(set(emitted) - set(dropped)))
    neutral = tuple(sorted(neutrals))
    probe = tuple(sorted(probe_block))
    expected_feed = {
        "country_of_origin",
        "hts_line",
        "hts_number",
        *projected,
        *neutral,
        *probe,
    }
    chapters = input_contract.get("chapters")
    _require(
        isinstance(chapters, list) and len(chapters) == expected_chapter_count,
        "bad chapter census",
    )
    for chapter in chapters:
        _require(
            isinstance(chapter, dict)
            and set(chapter.get("case_feed_inputs", [])) == expected_feed,
            f"case-feed input catalog drift: {chapter!r}",
        )
    _require(
        getattr(campaign, "NEUTRAL_BOOLEAN_INPUTS", None) == tuple(neutrals),
        "campaign neutral-input catalog differs from input contract",
    )
    _require(
        tuple(getattr(campaign, "PROBE_BOOLEAN_INPUTS", ())) == tuple(probe_block),
        "campaign probe-input catalog differs from input contract",
    )
    return projected, neutral, probe


def build_receipt(
    *,
    repo_root: Path = REPO_ROOT,
    expected_shard_count: int = 100,
    campaign: ModuleType | None = None,
) -> dict[str, Any]:
    """Validate all bound shards and derive the exact exercise field census."""

    repo_root = repo_root.resolve()
    manifest, _comparison, _report, input_contract = _validated_evidence(repo_root)
    campaign = campaign or _load_campaign(repo_root)
    projected, neutrals, probe_names = _input_catalog(
        input_contract,
        campaign,
        expected_chapter_count=expected_shard_count,
    )

    fields: dict[str, set[Any]] = {
        **{name: set() for name in MAPPED_FIELDS},
        **{name: set() for name in projected},
        **{name: {False} for name in neutrals},
        **{name: set() for name in probe_names},
    }
    shards = manifest.get("shards")
    _require(
        isinstance(shards, dict) and len(shards) == expected_shard_count,
        f"expected {expected_shard_count} eval shards",
    )
    generation_id = manifest["generation_id"]
    run_identity_sha256 = manifest["run_identity_sha256"]
    total_cases = 0
    chapters: set[str] = set()
    for key, shard in sorted(
        shards.items(), key=lambda item: str(item[1].get("chapter", ""))
    ):
        _require(isinstance(shard, dict), f"malformed shard receipt: {key}")
        path = Path(str(shard.get("path", "")))
        chapter = shard.get("chapter")
        _require(
            shard.get("key") == key
            and shard.get("generation_id") == generation_id
            and shard.get("run_identity_sha256") == run_identity_sha256
            and isinstance(chapter, str)
            and chapter not in chapters,
            f"shard identity drift: {key}",
        )
        chapters.add(chapter)
        _require(
            path.is_file() and shard.get("sha256") == _sha256(path),
            f"shard body is absent or stale: {key}",
        )
        _require(shard.get("engine_errors") == 0, f"shard has engine errors: {key}")
        shard_cases = 0
        with gzip.open(path, "rt") as source:
            for line_number, line in enumerate(source, 1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid shard JSON: {key}:{line_number}: {exc}"
                    ) from exc
                _require(isinstance(record, dict), f"malformed shard row: {key}:{line_number}")
                _require(
                    record.get("chapter") == chapter
                    and record.get("engine_errors") == [],
                    f"shard row identity/error drift: {key}:{line_number}",
                )
                flags = record.get("flags")
                _require(
                    isinstance(flags, dict) and set(flags) == set(projected),
                    f"shard flag catalog drift: {key}:{line_number}",
                )
                for field, source_name in MAPPED_FIELDS.items():
                    value = record.get(source_name)
                    _require(
                        isinstance(value, (str, int)) and not isinstance(value, bool),
                        f"malformed mapped field {field}: {key}:{line_number}",
                    )
                    fields[field].add(value)
                for name in projected:
                    value = flags[name]
                    _require(type(value) is bool, f"non-boolean flag {name}: {key}:{line_number}")
                    fields[name].add(value)
                probe_values = campaign._probe_boolean_inputs(record["probe"])
                _require(
                    isinstance(probe_values, dict)
                    and set(probe_values) == set(probe_names),
                    f"probe-input derivation drift: {key}:{line_number}",
                )
                for name, value in probe_values.items():
                    _require(type(value) is bool, f"non-boolean probe input {name}")
                    fields[name].add(value)
                shard_cases += 1
        _require(
            shard_cases == shard.get("cases"),
            f"shard case count drift: {key}: {shard_cases} != {shard.get('cases')}",
        )
        total_cases += shard_cases

    _require(all(values for values in fields.values()), "exercise field has no observations")
    evidence_fields = {
        name: {
            "distinct": len(values),
            "state": "varied" if len(values) > 1 else "constant",
        }
        for name, values in sorted(fields.items())
    }
    artifacts = [MANIFEST_REL, COMPARISON_REL, REPORT_REL]
    return {
        "schema": RECEIPT_SCHEMA,
        "suite": SUITE,
        "cases": total_cases,
        "evidence_mode": "content-addressed-shard-manifest",
        "report": str(REPORT_REL),
        "report_sha256": _sha256(repo_root / REPORT_REL),
        "evidence_artifacts": [
            {
                "path": str(path),
                "sha256": _sha256(repo_root / path),
            }
            for path in artifacts
        ],
        "evidence_fields": evidence_fields,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if the committed receipt drifts"
    )
    args = parser.parse_args(argv)
    expected = _render(build_receipt())
    path = REPO_ROOT / RECEIPT_REL
    if args.check:
        if not path.is_file() or path.read_text() != expected:
            print(f"stale tariff exercise receipt: {path}", file=sys.stderr)
            return 1
    else:
        path.write_text(expected)
    receipt = json.loads(expected)
    varied = sum(
        row["state"] == "varied" for row in receipt["evidence_fields"].values()
    )
    print(
        f"cases={receipt['cases']} fields={len(receipt['evidence_fields'])} "
        f"varied={varied} constant={len(receipt['evidence_fields']) - varied}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
