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
import io
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, BinaryIO, Callable

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_REL = Path("reference/us-tariff-schedule/eval/MANIFEST.json")
COMPARISON_REL = Path("reference/us-tariff-schedule/comparison-summary.json")
INPUT_CONTRACT_REL = Path(
    "reference/us-tariff-schedule/declared-input-contract-receipt.json"
)
REPORT_REL = Path("conformance/detail/us-tariff-schedule.json")
RECEIPT_REL = Path("axiom_oracles/bridges/exercise_receipts/us-tariff-schedule.json")
CAMPAIGN_REL = Path("scripts/us_tariff_schedule_campaign.py")
BRIDGE_REL = Path("axiom_oracles/bridges/manifests/us-tariff-schedule.yaml")
ARTIFACTS = (MANIFEST_REL, COMPARISON_REL, REPORT_REL, BRIDGE_REL)
SUITE = "us-tariff-schedule"
RECEIPT_SCHEMA = "axiom_oracles.committed_exercise_receipt.v1"
MANIFEST_SCHEMA = "axiom_oracles.us_tariff_schedule.eval_manifest.v3"
COMPARISON_SCHEMA = "axiom_oracles.us_tariff_schedule.comparison_summary.v3"
INPUT_CONTRACT_SCHEMA = "axiom_oracles.us_tariff_schedule.declared_input_contract.v4"
TRUSTED_RECEIPT_SHA256 = (
    # Only the two report bindings changed from the audited original. Its
    # measured input cardinalities are preserved by the mandatory publication
    # metadata-rebind gate and scripts/rebind_us_tariff_publication.py --check.
    "41a3bf09bc34c932121c5601672d1cc741aaa0e4026312f30cf819dfc6f72337"
)
MAPPED_FIELDS = {
    "hts_number": "hts10",
    "hts_line": "hts_line",
    "country_of_origin": "iso2",
    "entry_date": "probe",
    "origin_regime": "origin_regime",
}
ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS = frozenset(
    {
        "entry_is_china_301_2024_action",
        "entry_is_china_301_solar",
        "entry_is_note33_auto_part_subject_to_import_adjustment_offset",
        "entry_is_note33_g_automobile_part",
        "entry_is_note37_f_completed_kitchen_cabinet_vanity_or_part",
        "entry_is_note38_i_medium_or_heavy_duty_vehicle_part",
        "entry_is_note38_mhd_part_subject_to_import_adjustment_offset",
        "entry_is_note40_patented_pharmaceutical_article",
        "entry_qualifies_for_note33_certified_auto_part_heading_listed_in_notes_50_52",
        "entry_qualifies_for_note33_vehicle_heading_listed_in_notes_50_52",
        "entry_qualifies_for_note38_certified_mhd_part_heading_listed_in_notes_50_52",
        "entry_qualifies_for_note39_heading_9903_79_01",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    return _snapshot_file(path).sha256


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class _Snapshot:
    def __init__(
        self, path: Path, identity: tuple[int, ...], sha256: str, body: bytes | None
    ) -> None:
        self.path, self.identity, self.sha256, self.body = path, identity, sha256, body

    def receipt(self, repo_root: Path) -> dict[str, Any]:
        resolved = self.path.resolve()
        try:
            name = str(resolved.relative_to(repo_root.resolve()))
        except ValueError:
            name = str(resolved)
        return {"path": name, "bytes": self.identity[2], "sha256": self.sha256}


def _snapshot_file(path: Path, *, keep_body: bool = False) -> _Snapshot:
    """Hash one stable descriptor, never a check-then-reopened pathname."""
    digest = hashlib.sha256()
    blocks = [] if keep_body else None
    with path.open("rb") as source:
        before = _identity(os.fstat(source.fileno()))
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            if blocks is not None:
                blocks.append(block)
        _require(
            before == _identity(os.fstat(source.fileno())) == _identity(path.stat()),
            f"evidence changed while reading: {path}",
        )
    return _Snapshot(
        path,
        before,
        digest.hexdigest(),
        b"".join(blocks) if blocks is not None else None,
    )


def _require_current(snapshots: dict[Path, _Snapshot]) -> None:
    for path, snapshot in snapshots.items():
        _require(
            _identity(path.stat()) == snapshot.identity, f"evidence changed: {path}"
        )
        # Recheck small metadata bytes. Large bodies were hashed from their
        # actual scan descriptors; inode/ctime/mtime guard their later lifetime.
        if snapshot.body is not None:
            current = _snapshot_file(path)
            _require(
                current.sha256 == snapshot.sha256
                and current.identity == snapshot.identity,
                f"evidence changed: {path}",
            )


class _HashingReader:
    """Hash the compressed bytes actually consumed by GzipFile, including ABA."""

    def __init__(self, source: BinaryIO) -> None:
        self.source = source
        self.digest = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        body = self.source.read(size)
        self.digest.update(body)
        return body


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


class _UniqueSafeLoader(yaml.SafeLoader):
    """Reject duplicate YAML mapping keys before they can be last-wins."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        return _unique_pairs(
            [
                (
                    self.construct_object(key, deep=deep),
                    self.construct_object(value, deep=deep),
                )
                for key, value in node.value
            ]
        )


def _repo_file(repo_root: Path, raw: Any, label: str) -> Path:
    """Resolve one manifest-controlled repository file without path escape."""

    _require(isinstance(raw, str) and raw, f"invalid {label} path")
    relative = Path(raw)
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        f"invalid {label} path",
    )
    root = repo_root.resolve()
    resolved = (root / relative).resolve()
    _require(resolved.is_relative_to(root), f"{label} escaped the repository")
    return resolved


def _external_file(raw: Any, label: str) -> Path:
    """External bulk evidence must not depend on the caller's CWD."""

    _require(isinstance(raw, str) and raw, f"invalid {label} path")
    path = Path(raw)
    _require(path.is_absolute(), f"{label} path must be absolute")
    return path


def _load_yaml(snapshot: _Snapshot, label: str) -> dict[str, Any]:
    try:
        value = yaml.load(snapshot.body, Loader=_UniqueSafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid {label}: {snapshot.path}: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be a YAML mapping")
    return value


def _load_json(
    path: Path, label: str, snapshots: dict[Path, _Snapshot] | None = None
) -> dict[str, Any]:
    snapshot = _snapshot_file(path, keep_body=True)
    if snapshots is not None:
        snapshots[path] = snapshot
    try:
        value = json.loads(snapshot.body, object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label}: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object: {path}")
    return value


def _file_receipt(path: Path, *, repo_root: Path) -> dict[str, Any]:
    return _snapshot_file(path).receipt(repo_root)


def _load_campaign(repo_root: Path, snapshot: _Snapshot | None = None) -> ModuleType:
    path = repo_root / CAMPAIGN_REL
    snapshot = snapshot or _snapshot_file(path, keep_body=True)
    module = ModuleType("_tariff_exercise_receipt_campaign_" + snapshot.sha256)
    module.__file__ = str(path)
    # Execute exactly the source bytes authenticated by the run identity.
    exec(compile(snapshot.body, str(path), "exec"), module.__dict__)
    return module


def _validated_evidence(
    repo_root: Path,
    *,
    snapshots: dict[Path, _Snapshot] | None = None,
    verify_comparison_body: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    snapshots = snapshots if snapshots is not None else {}
    manifest_path = repo_root / MANIFEST_REL
    comparison_path = repo_root / COMPARISON_REL
    report_path = repo_root / REPORT_REL
    manifest = _load_json(manifest_path, "evaluation manifest", snapshots)
    comparison = _load_json(comparison_path, "comparison receipt", snapshots)
    report = _load_json(report_path, "campaign report", snapshots)

    _require(manifest.get("schema") == MANIFEST_SCHEMA, "stale eval manifest schema")
    _require(
        comparison.get("schema") == COMPARISON_SCHEMA,
        "stale comparison receipt schema",
    )
    _require(report.get("suite") == SUITE, "campaign report suite drift")
    _require(
        isinstance(report.get("summary"), dict)
        and type(report["summary"].get("engine_errors")) is int
        and report["summary"]["engine_errors"] == 0,
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
    _require(
        isinstance(comparison_artifact.get("path"), str)
        and type(comparison_artifact.get("bytes")) is int
        and comparison_artifact["bytes"] > 0
        and isinstance(comparison_artifact.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", comparison_artifact["sha256"]) is not None,
        "malformed comparison artifact receipt",
    )
    if verify_comparison_body:
        artifact_path = _external_file(
            comparison_artifact["path"], "comparison artifact"
        )
        artifact = _snapshot_file(artifact_path)
        snapshots[artifact_path] = artifact
        _require(
            comparison_artifact == artifact.receipt(repo_root),
            "comparison artifact is absent or stale",
        )
    _require(
        manifest.get("comparison_receipt")
        == snapshots[comparison_path].receipt(repo_root),
        "eval manifest comparison-receipt binding is absent or stale",
    )
    _require(
        type(comparison.get("engine_errors")) is int
        and comparison["engine_errors"] == 0,
        "comparison contains engine errors",
    )
    per_slot = comparison.get("per_slot")
    _require(isinstance(per_slot, dict) and per_slot, "comparison lacks slot counts")
    for slot, counts in per_slot.items():
        _require(
            isinstance(counts, dict)
            and counts
            and set(counts) <= {"match", "mismatch"}
            and all(type(count) is int and count >= 0 for count in counts.values()),
            f"invalid comparison slot counts: {slot}",
        )
    matches = sum(counts.get("match", 0) for counts in per_slot.values())
    mismatches = sum(counts.get("mismatch", 0) for counts in per_slot.values())
    summary = report.get("summary")
    _require(
        isinstance(summary, dict)
        and all(
            type(summary.get(key)) is int
            for key in ("total", "matches", "mismatches", "engine_errors")
        )
        and {
            key: summary[key]
            for key in ("total", "matches", "mismatches", "engine_errors")
        }
        == {
            "total": matches + mismatches,
            "matches": matches,
            "mismatches": mismatches,
            "engine_errors": 0,
        }
        and _canonical_sha256(report.get("output_summary"))
        == _canonical_sha256(per_slot),
        "campaign report does not bind current comparison counts",
    )
    classification = report.get("classification")
    _require(
        isinstance(classification, dict)
        and classification.get("schema")
        == "axiom_oracles.us_tariff_schedule.classification.v2"
        and isinstance(classification.get("inputs"), dict)
        and classification["inputs"].get("comparison_receipt_sha256")
        == snapshots[comparison_path].sha256
        and classification["inputs"].get("comparison_artifact_sha256")
        == comparison_artifact["sha256"],
        "campaign report classification does not bind current comparison",
    )

    run_identity = manifest.get("run_identity")
    _require(isinstance(run_identity, dict), "eval manifest lacks run identity")
    _require(
        _canonical_sha256(run_identity) == run_identity_sha256,
        "eval run-identity hash drift",
    )
    input_contract_ref = run_identity.get("input_contract")
    _require(isinstance(input_contract_ref, dict), "run identity lacks input contract")
    input_contract_path = _repo_file(
        repo_root, input_contract_ref.get("path"), "declared-input contract"
    )
    _require(
        input_contract_path == (repo_root / INPUT_CONTRACT_REL).resolve(),
        "eval run identity names the wrong declared-input contract",
    )
    input_contract = _load_json(
        input_contract_path, "declared-input contract", snapshots
    )
    _require(
        input_contract_ref
        == snapshots[input_contract_path].receipt(repo_root)
        | {"schema": input_contract_ref.get("schema")},
        "eval input-contract binding is absent or stale",
    )
    _require(
        input_contract_ref.get("schema") == INPUT_CONTRACT_SCHEMA
        and input_contract.get("schema") == INPUT_CONTRACT_SCHEMA,
        "declared-input contract schema drift",
    )

    campaign_ref = run_identity.get("campaign_evaluator", {}).get("campaign")
    campaign_path = repo_root / CAMPAIGN_REL
    snapshots[campaign_path] = _snapshot_file(campaign_path, keep_body=True)
    _require(
        campaign_ref == snapshots[campaign_path].receipt(repo_root),
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
    _require(
        all(len(names) == len(set(names)) for names in (emitted, dropped, neutrals))
        and set(dropped) <= set(emitted),
        "declared-input contract contains duplicate/unknown input names",
    )
    projected = tuple(sorted(set(emitted) - set(dropped)))
    neutral = tuple(sorted(neutrals))
    probe = tuple(sorted(probe_block))
    _require(
        not set(MAPPED_FIELDS).intersection(projected, neutral, probe),
        "declared-input catalogs overlap mapped fields",
    )
    expected_feed = {
        "country_of_origin",
        "hts_line",
        "hts_number",
        *projected,
        *neutral,
        *probe,
    }
    _require(
        len(expected_feed) == 3 + len(projected) + len(neutral) + len(probe),
        "declared-input catalogs overlap",
    )
    chapters = input_contract.get("chapters")
    _require(
        isinstance(chapters, list) and len(chapters) == expected_chapter_count,
        "bad chapter census",
    )
    chapter_names: set[str] = set()
    for chapter in chapters:
        _require(
            isinstance(chapter, dict)
            and isinstance(chapter.get("chapter"), str)
            and chapter["chapter"] not in chapter_names
            and isinstance(chapter.get("case_feed_inputs"), list)
            and len(chapter["case_feed_inputs"]) == len(expected_feed)
            and set(chapter.get("case_feed_inputs", [])) == expected_feed,
            f"case-feed input catalog drift: {chapter!r}",
        )
        chapter_names.add(chapter["chapter"])
    _require(
        getattr(campaign, "NEUTRAL_BOOLEAN_INPUTS", None) == tuple(neutrals),
        "campaign neutral-input catalog differs from input contract",
    )
    _require(
        input_contract.get("neutral_boolean_value") is False,
        "declared neutral-input value is not false",
    )
    _require(
        tuple(getattr(campaign, "PROBE_BOOLEAN_INPUTS", ())) == tuple(probe_block),
        "campaign probe-input catalog differs from input contract",
    )
    return projected, neutral, probe


def _expected_binding_semantics(
    input_contract: dict[str, Any],
    projected: tuple[str, ...],
    neutral: tuple[str, ...],
    probe: tuple[str, ...],
) -> dict[str, tuple[str, bool | None]]:
    """Derive every binding kind/value independently of the bridge manifest."""

    projected_set = set(projected)
    _require(
        ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS <= projected_set,
        "entry-flag construction-constant catalog drift",
    )
    reference_assumptions = input_contract.get("reference_assumptions")
    _require(
        isinstance(reference_assumptions, dict) and reference_assumptions,
        "declared-input contract lacks reference assumptions",
    )
    reference_constants: dict[str, bool] = {}
    for label, assumption in reference_assumptions.items():
        binding = (
            assumption.get("campaign_binding") if isinstance(assumption, dict) else None
        )
        name = binding.get("input") if isinstance(binding, dict) else None
        value = binding.get("value") if isinstance(binding, dict) else None
        _require(
            isinstance(label, str)
            and isinstance(name, str)
            and name in projected_set
            and type(value) is bool
            and name not in reference_constants,
            f"malformed reference-assumption binding: {label}",
        )
        reference_constants[name] = value

    constant_entry_flags = ENTRY_FLAG_FALSE_CONSTRUCTION_CONSTANTS | set(
        reference_constants
    )
    semantics: dict[str, tuple[str, bool | None]] = {
        name: ("mapped", None) for name in MAPPED_FIELDS
    }
    semantics.update(
        {
            name: (
                "constant",
                reference_constants.get(name, False),
            )
            if name in constant_entry_flags
            else ("projected", None)
            for name in projected
        }
    )
    semantics.update({name: ("constant", False) for name in neutral})
    semantics.update({name: ("projected", None) for name in probe})
    _require(
        len(semantics)
        == len(MAPPED_FIELDS) + len(projected) + len(neutral) + len(probe),
        "binding-semantics catalogs overlap",
    )
    return semantics


def _bridge_bindings(
    repo_root: Path,
    snapshots: dict[Path, _Snapshot],
    expected_semantics: dict[str, tuple[str, bool | None]],
) -> dict[str, dict[str, Any]]:
    path = repo_root / BRIDGE_REL
    snapshot = _snapshot_file(path, keep_body=True)
    snapshots[path] = snapshot
    manifest = _load_yaml(snapshot, "tariff bridge manifest")
    _require(
        isinstance(manifest, dict)
        and manifest.get("suite") == SUITE
        and manifest.get("strict") is True
        and isinstance(manifest.get("bindings"), list),
        "invalid tariff bridge manifest",
    )
    bindings = {}
    for binding in manifest["bindings"]:
        _require(
            isinstance(binding, dict)
            and binding.get("kind") in {"mapped", "projected", "constant"},
            "invalid tariff bridge binding",
        )
        names = binding.get("inputs", [binding.get("input")])
        _require(isinstance(names, list) and names, "empty tariff bridge binding")
        for name in names:
            _require(
                isinstance(name, str) and name and name not in bindings,
                "duplicate/invalid tariff bridge field",
            )
            expected = expected_semantics.get(name)
            _require(expected is not None, f"unexpected tariff bridge field: {name}")
            expected_kind, expected_value = expected
            _require(
                binding["kind"] == expected_kind,
                f"tariff bridge kind contradicts source semantics: {name}",
            )
            if expected_kind == "constant":
                _require(
                    type(binding.get("value")) is bool
                    and binding["value"] is expected_value,
                    f"tariff construction constant has wrong value: {name}",
                )
            else:
                _require(
                    "value" not in binding,
                    f"non-constant tariff binding declares a value: {name}",
                )
            bindings[name] = binding
    _require(
        set(bindings) == set(expected_semantics),
        "tariff bridge/input catalog drift",
    )
    return bindings


def _shard_catalog(
    manifest: dict[str, Any],
    input_contract: dict[str, Any],
    campaign: ModuleType,
    expected_count: int,
) -> list[dict[str, Any]]:
    shards = manifest.get("shards")
    _require(
        isinstance(shards, dict) and len(shards) == expected_count,
        f"expected {expected_count} eval shards",
    )
    chapters: set[str] = set()
    paths: set[Path] = set()
    expected_keys = campaign._current_shard_keys(
        manifest["run_identity"], manifest["generation_id"]
    )
    _require(
        isinstance(expected_keys, dict)
        and len(expected_keys) == expected_count
        and set(expected_keys)
        == {chapter["chapter"] for chapter in input_contract["chapters"]},
        "authenticated campaign shard-key census drift",
    )
    for key, shard in shards.items():
        _require(isinstance(shard, dict), f"malformed shard receipt: {key}")
        chapter = shard.get("chapter")
        raw_path = shard.get("path")
        path = _external_file(raw_path, f"shard {key}")
        _require(
            shard.get("key") == key
            and isinstance(key, str)
            and re.fullmatch(r"[0-9a-f]{64}", key) is not None
            and shard.get("generation_id") == manifest["generation_id"]
            and shard.get("run_identity_sha256") == manifest["run_identity_sha256"]
            and isinstance(chapter, str)
            and chapter not in chapters
            and expected_keys.get(chapter) == key
            and path not in paths
            and isinstance(shard.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", shard["sha256"]) is not None,
            f"shard identity drift: {key}",
        )
        _require(
            type(shard.get("cases")) is int and shard["cases"] >= 0,
            f"invalid shard case count: {key}",
        )
        _require(
            type(shard.get("engine_errors")) is int and shard["engine_errors"] == 0,
            f"shard has engine errors: {key}",
        )
        chapters.add(chapter)
        paths.add(path)
    _require(
        chapters == {chapter["chapter"] for chapter in input_contract["chapters"]},
        "shard/input-contract chapter census drift",
    )
    return sorted(shards.values(), key=lambda shard: shard["chapter"])


def _comparison_case_count(comparison: dict[str, Any]) -> int:
    """Derive the evaluated case denominator independently of shard receipts."""

    per_slot = comparison.get("per_slot")
    _require(isinstance(per_slot, dict) and per_slot, "comparison lacks slot counts")
    denominators = {
        counts.get("match", 0) + counts.get("mismatch", 0)
        for counts in per_slot.values()
    }
    _require(
        denominators
        and all(type(value) is int and value > 0 for value in denominators),
        "comparison has invalid case denominators",
    )
    return max(denominators)


def validate_committed_receipt(
    receipt: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    expected_shard_count: int = 100,
) -> dict[Path, _Snapshot]:
    """Validate the small, committed handoff without opening external bodies.

    This checks binding and necessary census constraints, not a replacement
    measurement: only build_receipt/--check rederive distinct values by scanning.
    """
    repo_root = repo_root.resolve()
    snapshots: dict[Path, _Snapshot] = {}
    current = _load_json(repo_root / RECEIPT_REL, "exercise receipt", snapshots)
    if repo_root == REPO_ROOT.resolve():
        _require(
            snapshots[repo_root / RECEIPT_REL].sha256 == TRUSTED_RECEIPT_SHA256,
            "tariff exercise receipt has not been independently audited or its bytes changed",
        )
    _require(
        _canonical_sha256(current) == _canonical_sha256(receipt),
        "exercise receipt changed while validating",
    )
    _require(
        receipt.get("schema") == RECEIPT_SCHEMA and receipt.get("suite") == SUITE,
        "wrong tariff exercise receipt identity",
    )
    manifest, comparison, _report, contract = _validated_evidence(
        repo_root,
        snapshots=snapshots,
        verify_comparison_body=False,
    )
    campaign = _load_campaign(repo_root, snapshots[repo_root / CAMPAIGN_REL])
    projected, neutral, probe = _input_catalog(
        contract,
        campaign,
        expected_chapter_count=expected_shard_count,
    )
    expected_semantics = _expected_binding_semantics(
        contract, projected, neutral, probe
    )
    bindings = _bridge_bindings(repo_root, snapshots, expected_semantics)
    shards = _shard_catalog(manifest, contract, campaign, expected_shard_count)
    cases = receipt.get("cases")
    _require(
        type(cases) is int
        and cases > 0
        and cases == sum(shard["cases"] for shard in shards)
        and cases == _comparison_case_count(comparison),
        "exercise case count differs from bound eval manifest",
    )
    _require(
        receipt.get("report") == str(REPORT_REL)
        and receipt.get("report_sha256") == snapshots[repo_root / REPORT_REL].sha256
        and receipt.get("evidence_mode") == "content-addressed-shard-manifest",
        "exercise report/mode binding drift",
    )
    expected_artifacts = [
        {"path": str(path), "sha256": snapshots[repo_root / path].sha256}
        for path in ARTIFACTS
    ]
    _require(
        receipt.get("evidence_artifacts") == expected_artifacts,
        "exercise evidence artifact set/hash drift",
    )
    fields = receipt.get("evidence_fields")
    _require(
        isinstance(fields, dict) and set(fields) == set(expected_semantics),
        "exercise field catalog differs from bound input contract",
    )
    for name, field in fields.items():
        _require(isinstance(field, dict), f"malformed exercise field: {name}")
        distinct = field.get("distinct")
        _require(
            type(distinct) is int and 1 <= distinct <= cases,
            f"invalid exercise distinct count: {name}",
        )
        _require(
            field.get("state") == ("varied" if distinct > 1 else "constant"),
            f"exercise field state/count disagree: {name}",
        )
        if name not in MAPPED_FIELDS:
            _require(
                distinct <= 2, f"boolean exercise field has too many values: {name}"
            )
        if bindings[name]["kind"] == "constant":
            _require(distinct == 1, f"declared construction constant varied: {name}")
    _require_current(snapshots)
    return snapshots


def _bound_shard_lines(shard: dict[str, Any], snapshots: dict[Path, _Snapshot]):
    path = Path(shard["path"])
    with path.open("rb") as raw:
        before = _identity(os.fstat(raw.fileno()))
        hashing = _HashingReader(raw)
        with io.TextIOWrapper(
            gzip.GzipFile(fileobj=hashing, mode="rb"), encoding="utf-8"
        ) as source:
            yield from source
        _require(
            hashing.digest.hexdigest() == shard["sha256"],
            f"shard body is absent or stale: {shard['key']}",
        )
        _require(
            before == _identity(os.fstat(raw.fileno())) == _identity(path.stat()),
            f"shard changed while scanning: {shard['key']}",
        )
        snapshots[path] = _Snapshot(path, before, hashing.digest.hexdigest(), None)


def build_receipt(
    *,
    repo_root: Path = REPO_ROOT,
    expected_shard_count: int = 100,
    _snapshots: dict[Path, _Snapshot] | None = None,
) -> dict[str, Any]:
    """Validate all bound shards and derive the exact exercise field census."""

    repo_root = repo_root.resolve()
    snapshots = _snapshots if _snapshots is not None else {}
    manifest, comparison, _report, input_contract = _validated_evidence(
        repo_root,
        snapshots=snapshots,
    )
    campaign = _load_campaign(repo_root, snapshots[repo_root / CAMPAIGN_REL])
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
    expected_semantics = _expected_binding_semantics(
        input_contract, projected, neutrals, probe_names
    )
    bindings = _bridge_bindings(repo_root, snapshots, expected_semantics)
    shards = _shard_catalog(manifest, input_contract, campaign, expected_shard_count)
    total_cases = 0
    for shard in shards:
        key, chapter = shard["key"], shard["chapter"]
        shard_cases = 0
        # The iterator hashes exactly the descriptor supplying these records.
        source = _bound_shard_lines(shard, snapshots)
        try:
            for line_number, line in enumerate(source, 1):
                try:
                    record = json.loads(line, object_pairs_hook=_unique_pairs)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid shard JSON: {key}:{line_number}: {exc}"
                    ) from exc
                _require(
                    isinstance(record, dict),
                    f"malformed shard row: {key}:{line_number}",
                )
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
                    _require(
                        type(value) is bool,
                        f"non-boolean flag {name}: {key}:{line_number}",
                    )
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
        finally:
            source.close()
        _require(
            shard_cases == shard.get("cases"),
            f"shard case count drift: {key}: {shard_cases} != {shard.get('cases')}",
        )
        total_cases += shard_cases

    _require(
        total_cases > 0 and all(values for values in fields.values()),
        "exercise field has no observations",
    )
    _require(
        total_cases == _comparison_case_count(comparison),
        "exercise case count differs from comparison denominator",
    )
    for name, binding in bindings.items():
        if binding["kind"] == "constant":
            _require(
                fields[name] == {binding["value"]},
                f"observed values contradict construction constant: {name}",
            )
    evidence_fields = {
        name: {
            "distinct": len(values),
            "state": "varied" if len(values) > 1 else "constant",
        }
        for name, values in sorted(fields.items())
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "suite": SUITE,
        "cases": total_cases,
        "evidence_mode": "content-addressed-shard-manifest",
        "report": str(REPORT_REL),
        "report_sha256": snapshots[repo_root / REPORT_REL].sha256,
        "evidence_artifacts": [
            {
                "path": str(path),
                "sha256": snapshots[repo_root / path].sha256,
            }
            for path in ARTIFACTS
        ],
        "evidence_fields": evidence_fields,
    }
    _require_current(snapshots)
    return receipt


def _publish_receipt(
    path: Path, body: bytes, require_current: Callable[[], None]
) -> None:
    """Publish atomically and restore prior committed bytes on late failure."""
    temporary: Path | None = None
    rollback: Path | None = None
    written_inode: tuple[int, int] | None = None
    previous = _snapshot_file(path, keep_body=True) if path.is_file() else None
    previous_mode = 0o644
    if previous is not None:
        previous_stat = path.stat()
        _require(
            _identity(previous_stat) == previous.identity,
            "exercise receipt changed before publication",
        )
        previous_mode = stat.S_IMODE(previous_stat.st_mode)
    try:
        require_current()
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=path.name + ".", delete=False
        ) as target:
            temporary = Path(target.name)
            target.write(body)
            target.flush()
            os.fsync(target.fileno())
            os.fchmod(target.fileno(), previous_mode)
            written_inode = _identity(os.fstat(target.fileno()))[:2]
        require_current()
        os.replace(temporary, path)
        temporary = None
        published = _snapshot_file(path, keep_body=True)
        _require(
            published.body == body and published.identity[:2] == written_inode,
            "published exercise receipt changed",
        )
        require_current()
        current = _snapshot_file(path, keep_body=True)
        _require(
            current.body == body and current.identity == published.identity,
            "published exercise receipt changed",
        )
    except BaseException:
        if (
            written_inode is not None
            and path.is_file()
            and _identity(path.stat())[:2] == written_inode
        ):
            if previous is None:
                path.unlink()
            else:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=path.parent,
                    prefix=path.name + ".rollback.",
                    delete=False,
                ) as target:
                    rollback = Path(target.name)
                    target.write(previous.body)
                    target.flush()
                    os.fsync(target.fileno())
                    os.fchmod(target.fileno(), previous_mode)
                # Do not overwrite a concurrent replacement that arrived while
                # the rollback bytes were being prepared.
                if path.is_file() and _identity(path.stat())[:2] == written_inode:
                    os.replace(rollback, path)
                    rollback = None
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if rollback is not None:
            rollback.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if the committed receipt drifts"
    )
    args = parser.parse_args(argv)
    snapshots: dict[Path, _Snapshot] = {}
    expected = _render(build_receipt(_snapshots=snapshots))
    path = REPO_ROOT / RECEIPT_REL
    if args.check:
        checked = _snapshot_file(path, keep_body=True) if path.is_file() else None
        if checked is None or checked.body != expected.encode():
            print(f"stale tariff exercise receipt: {path}", file=sys.stderr)
            return 1
        _require_current(snapshots | {path: checked})
    else:
        _publish_receipt(path, expected.encode(), lambda: _require_current(snapshots))
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
