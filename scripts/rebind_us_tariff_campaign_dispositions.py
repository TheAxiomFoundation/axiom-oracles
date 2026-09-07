#!/usr/bin/env python3
"""Atomically rebind the tariff disposition ledger to fresh proof receipts.

The four proof producers intentionally precede the human-reviewed disposition
ledger.  A replay changes their file and payload hashes even when every measured
population is unchanged.  This tool performs the deliberately narrow handoff:
exactly 39 existing scalar fields may change, and nothing else in the parsed or
rendered ledger may move.

``--generate`` accepts only the all-stale state (all 39 scalars differ) and
publishes one atomic replacement.  ``--check`` accepts only the all-current
state (all 39 already match).  A partially rebound ledger fails closed.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_ROOT = REPO_ROOT / "reference/us-tariff-schedule"
DEFAULT_LEDGER = REFERENCE_ROOT / "campaign-dispositions.yaml"
DEFAULT_TRANSITION_RECEIPT = REFERENCE_ROOT / "preview-selector-transition-receipt.json"
DEFAULT_CAFTA_RECEIPT = (
    REFERENCE_ROOT / "cafta-reference-defect-supersession-receipt.json"
)
DEFAULT_STEEL_RECEIPT = REFERENCE_ROOT / "steel-scope-projection-receipt.json"
DEFAULT_REMAINING_RECEIPT = REFERENCE_ROOT / "remaining-residual-receipt.json"
DEFAULT_EVAL_MANIFEST = REFERENCE_ROOT / "eval/MANIFEST.json"
DEFAULT_COMPARISON_RECEIPT = REFERENCE_ROOT / "comparison-summary.json"

TRANSITION_SCHEMA = "axiom_oracles.us_tariff_schedule.preview_selector_transitions.v1"
CAFTA_SCHEMA = "axiom_oracles.us_tariff_schedule.cafta_reference_defect_supersession.v1"
STEEL_SCHEMA = "axiom_oracles.us_tariff_schedule.steel_scope_projection.v1"
REMAINING_SCHEMA = "axiom_oracles.us_tariff_schedule.remaining_residuals.v1"
EVAL_MANIFEST_SCHEMA = "axiom_oracles.us_tariff_schedule.eval_manifest.v3"
COMPARISON_SCHEMA = "axiom_oracles.us_tariff_schedule.comparison_summary.v3"
LEDGER_SCHEMA = "axiom_oracles.dispositions.v1"
SUITE = "us-tariff-schedule"
HEX64 = re.compile(r"[0-9a-f]{64}")

# This is the reviewed transition topology, not a population inferred from the
# ledger being modified.  The two exposed parents are intentionally retired and
# therefore have no children.
TRANSITION_PARENT_TO_CHILDREN = {
    "aircraft-utilization-proxy-brazil": (
        "aircraft-utilization-proxy-brazil-fresh-signature-rebind",
    ),
    "aircraft-utilization-proxy-forced-labor": (
        "aircraft-utilization-proxy-forced-labor-fresh-signature-rebind",
    ),
    "cafta-52i-deferred": ("cafta-52i-yale-reference-defect",),
    "chapter98-brazil": ("chapter98-brazil-fresh-signature-rebind",),
    "chapter98-forced-labor": ("chapter98-forced-labor-fresh-signature-rebind",),
    "pharma-utilization-proxy-brazil": (
        "pharma-utilization-proxy-brazil-fresh-signature-rebind",
    ),
    "pharma-utilization-proxy-forced-labor-035": (
        "pharma-utilization-proxy-forced-labor-035-fresh-signature-rebind",
    ),
    "pharma-utilization-proxy-forced-labor-non035": (
        "pharma-utilization-proxy-forced-labor-non035-fresh-signature-rebind",
    ),
    "section232-annex-brazil": (
        "section232-annex-auto-part-candidate-brazil",
        "section232-annex-auto-and-mhd-part-candidates-brazil",
        "section232-annex-mhd-part-candidate-brazil",
        "section232-annex-yale-reference-defect-brazil",
    ),
    "section232-annex-forced-labor": (
        "section232-annex-auto-part-candidate-forced-labor",
        "section232-annex-auto-and-mhd-part-candidates-forced-labor",
        "section232-annex-mhd-part-candidate-forced-labor",
        "section232-annex-yale-reference-defect-forced-labor",
    ),
    "section232-exposed-brazil": (),
    "section232-exposed-forced-labor": (),
    "section232-heading-brazil": (
        "section232-heading-auto-part-candidate-brazil",
        "section232-heading-auto-and-mhd-part-candidates-brazil",
        "section232-heading-vehicle-candidate-brazil",
        "section232-heading-cabinet-vanity-candidate-brazil",
        "section232-heading-mhd-part-candidate-brazil",
    ),
    "section232-heading-forced-labor": (
        "section232-heading-auto-part-candidate-forced-labor",
        "section232-heading-auto-and-mhd-part-candidates-forced-labor",
        "section232-heading-vehicle-candidate-forced-labor",
        "section232-heading-cabinet-vanity-candidate-forced-labor",
        "section232-heading-mhd-part-candidate-forced-labor",
    ),
    "yale-hts8-broadening-brazil": (
        "yale-hts8-broadening-brazil-fresh-signature-rebind",
    ),
    "yale-parser-zero-statutory-base": (
        "yale-parser-zero-statutory-base-fresh-signature-rebind",
    ),
    "yale-zero-pharma-brazil": ("yale-zero-pharma-brazil-fresh-signature-rebind",),
    "yale-zero-pharma-forced-labor": (
        "yale-zero-pharma-forced-labor-fresh-signature-rebind",
    ),
}
TRANSITION_ENTRY_IDS = tuple(
    child for children in TRANSITION_PARENT_TO_CHILDREN.values() for child in children
)
CAFTA_ENTRY_ID = "cafta-52i-yale-reference-defect"
STEEL_ENTRY_IDS = (
    "section232-steel-scope-projection-brazil",
    "section232-steel-scope-projection-forced-labor",
)
REMAINING_ENTRY_IDS = (
    "section232-russia-aluminum-membership-vintage",
    "yale-html-statutory-base-parser-defect",
)
EXPECTED_TARGET_COUNT = 39


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class Snapshot(NamedTuple):
    path: Path
    body: bytes | None
    identity: tuple[int, ...]
    sha256: str


def snapshot_file(path: Path, *, keep_body: bool = True) -> Snapshot:
    path = path.resolve()
    require(path.is_file(), f"missing evidence file: {path}")
    digest = hashlib.sha256()
    blocks: list[bytes] | None = [] if keep_body else None
    with path.open("rb") as source:
        before = _identity(os.fstat(source.fileno()))
        for block in iter(lambda: source.read(1024 * 1024), b""):
            if blocks is not None:
                blocks.append(block)
            digest.update(block)
        after = _identity(os.fstat(source.fileno()))
    require(
        before == after == _identity(path.stat()),
        f"evidence changed while reading: {path}",
    )
    return Snapshot(
        path,
        b"".join(blocks) if blocks is not None else None,
        before,
        digest.hexdigest(),
    )


def require_snapshot_current(snapshot: Snapshot) -> None:
    current = snapshot_file(snapshot.path, keep_body=snapshot.body is not None)
    require(
        current.identity == snapshot.identity
        and current.sha256 == snapshot.sha256
        and current.body == snapshot.body,
        f"evidence changed after validation: {snapshot.path}",
    )


def _relative_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(resolved)


def file_receipt(snapshot: Snapshot, repo_root: Path) -> dict[str, Any]:
    return {
        "path": _relative_path(snapshot.path, repo_root),
        "bytes": snapshot.identity[2],
        "sha256": snapshot.sha256,
    }


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(snapshot: Snapshot) -> dict[str, Any]:
    require(snapshot.body is not None, f"JSON body was not retained: {snapshot.path}")
    try:
        value = json.loads(
            snapshot.body,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON evidence: {snapshot.path}") from exc
    require(isinstance(value, dict), f"JSON evidence is not an object: {snapshot.path}")
    return value


class UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueSafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(key not in result, f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def parse_yaml(body: bytes | str, *, label: str) -> dict[str, Any]:
    try:
        value = yaml.load(body, Loader=UniqueSafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {label}") from exc
    require(isinstance(value, dict), f"YAML is not an object: {label}")
    return value


class Proof(NamedTuple):
    snapshot: Snapshot
    document: dict[str, Any]
    file_receipt: dict[str, Any]
    payload_sha256: str


def load_proof(path: Path, schema: str, repo_root: Path) -> Proof:
    snapshot = snapshot_file(path)
    document = parse_json(snapshot)
    require(
        document.get("schema") == schema and document.get("verdict") == "PASS",
        f"proof is not the expected PASS receipt: {path}",
    )
    payload_sha256 = document.get("receipt_payload_sha256")
    require(
        isinstance(payload_sha256, str) and HEX64.fullmatch(payload_sha256) is not None,
        f"proof payload hash is malformed: {path}",
    )
    payload = dict(document)
    del payload["receipt_payload_sha256"]
    require(
        canonical_sha256(payload) == payload_sha256,
        f"proof payload hash does not authenticate its document: {path}",
    )
    return Proof(
        snapshot,
        document,
        file_receipt(snapshot, repo_root),
        payload_sha256,
    )


class Target(NamedTuple):
    entry_id: str
    path: tuple[str, ...]
    value: str

    @property
    def address(self) -> tuple[str, tuple[str, ...]]:
        return self.entry_id, self.path


class Plan(NamedTuple):
    ledger_snapshot: Snapshot
    evidence_snapshots: tuple[Snapshot, ...]
    original: dict[str, Any]
    expected: dict[str, Any]
    output: bytes
    targets: tuple[Target, ...]
    changed: tuple[Target, ...]
    proof_summary: dict[str, dict[str, str]]


def _entry_catalog(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require(
        ledger.get("schema") == LEDGER_SCHEMA and ledger.get("suite") == SUITE,
        "wrong tariff disposition ledger identity",
    )
    entries = ledger.get("entries")
    require(isinstance(entries, list) and entries, "ledger entries are missing")
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        require(isinstance(entry, dict), "ledger entry is not an object")
        entry_id = entry.get("id")
        require(isinstance(entry_id, str) and entry_id, "ledger entry id is malformed")
        require(entry_id not in result, f"duplicate ledger entry id: {entry_id}")
        result[entry_id] = entry
    return result


def _mapping_at(value: Mapping[str, Any], path: Sequence[str], *, label: str) -> Any:
    current: Any = value
    for part in path:
        require(
            isinstance(current, dict) and part in current, f"missing {label}: {part}"
        )
        current = current[part]
    return current


def _set_mapping_at(
    value: dict[str, Any], path: Sequence[str], replacement: Any
) -> None:
    current: dict[str, Any] = value
    for part in path[:-1]:
        child = current.get(part)
        require(isinstance(child, dict), f"cannot set malformed target path: {path}")
        current = child
    current[path[-1]] = replacement


def _valid_file_receipt(value: Any, *, label: str) -> dict[str, Any]:
    require(
        isinstance(value, dict) and set(value) == {"path", "bytes", "sha256"},
        f"malformed file receipt: {label}",
    )
    require(
        isinstance(value["path"], str)
        and bool(value["path"])
        and type(value["bytes"]) is int
        and value["bytes"] >= 0
        and isinstance(value["sha256"], str)
        and HEX64.fullmatch(value["sha256"]) is not None,
        f"invalid file receipt fields: {label}",
    )
    return value


def _resolve_receipted_path(path: str, repo_root: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _validate_common_bindings(
    proofs: Mapping[str, Proof],
    manifest_snapshot: Snapshot,
    comparison_snapshot: Snapshot,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Snapshot]:
    manifest = parse_json(manifest_snapshot)
    comparison = parse_json(comparison_snapshot)
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
        set(manifest) == expected_manifest_fields
        and manifest.get("schema") == EVAL_MANIFEST_SCHEMA,
        "evaluation manifest is not a complete comparison-bound v3 manifest",
    )
    require(
        comparison.get("schema") == COMPARISON_SCHEMA,
        "comparison receipt is not schema v3",
    )
    manifest_receipt = file_receipt(manifest_snapshot, repo_root)
    comparison_receipt = file_receipt(comparison_snapshot, repo_root)
    run_identity = manifest.get("run_identity")
    run_identity_sha256 = manifest.get("run_identity_sha256")
    generation_id = manifest.get("generation_id")
    require(
        isinstance(run_identity, dict)
        and isinstance(run_identity_sha256, str)
        and HEX64.fullmatch(run_identity_sha256) is not None
        and canonical_sha256(run_identity) == run_identity_sha256
        and run_identity_sha256 == comparison.get("run_identity_sha256"),
        "evaluation run-identity digest drift",
    )
    require(
        isinstance(generation_id, str)
        and re.fullmatch(r"[0-9a-f]{32}", generation_id) is not None
        and generation_id == comparison.get("generation_id"),
        "evaluation/comparison generation is malformed or inconsistent",
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
    require(
        manifest.get("comparison_receipt") == comparison_receipt,
        "evaluation manifest is not bound to the current comparison receipt",
    )
    artifact_receipt = _valid_file_receipt(
        comparison.get("comparison_artifact"), label="comparison artifact"
    )
    artifact_path = _resolve_receipted_path(artifact_receipt["path"], repo_root)
    artifact_snapshot = snapshot_file(artifact_path, keep_body=False)
    require(
        file_receipt(artifact_snapshot, repo_root) == artifact_receipt,
        "comparison artifact hash or size drift",
    )
    require(
        manifest.get("comparison_artifact") == artifact_receipt,
        "evaluation manifest and comparison receipt disagree on the artifact",
    )
    for name, proof in proofs.items():
        inputs = proof.document.get("inputs")
        bindings = proof.document.get("bindings")
        require(isinstance(inputs, dict), f"{name} proof inputs are malformed")
        require(isinstance(bindings, dict), f"{name} proof bindings are malformed")
        require(
            inputs.get("evaluation_manifest") == manifest_receipt
            and inputs.get("comparison_receipt") == comparison_receipt
            and inputs.get("comparison_artifact")
            == comparison.get("comparison_artifact"),
            f"{name} proof is not bound to the current evaluation/comparison",
        )
        require(
            bindings.get("run_identity_sha256") == run_identity_sha256
            and bindings.get("generation_id") == generation_id,
            f"{name} proof run/generation binding drift",
        )
        direct_evaluation_binding = bindings.get("evaluation_manifest_sha256")
        if name in {"transition", "cafta"}:
            require(
                direct_evaluation_binding == evaluation_manifest_sha256,
                f"{name} proof evaluation-manifest binding drift",
            )
        elif direct_evaluation_binding is not None:
            require(
                direct_evaluation_binding == evaluation_manifest_sha256,
                f"{name} proof evaluation-manifest binding drift",
            )
        # Steel and remaining predate a duplicate direct field. Their exact
        # manifest/comparison input receipts above provide the same binding.
    return manifest, comparison, artifact_snapshot


def _transition_children(proof: Proof) -> dict[str, dict[str, Any]]:
    transitions = proof.document.get("transitions")
    require(isinstance(transitions, list), "transition proof transitions are malformed")
    by_parent: dict[str, tuple[str, ...]] = {}
    children: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        require(isinstance(transition, dict), "transition item is not an object")
        parent_id = transition.get("parent_id")
        child_items = transition.get("children")
        require(
            isinstance(parent_id, str)
            and parent_id not in by_parent
            and isinstance(child_items, list),
            "transition parent/children are malformed or duplicated",
        )
        expected_status = "superseded" if child_items else "retired"
        require(
            transition.get("status") == expected_status,
            f"transition status drift: {parent_id} must be {expected_status}",
        )
        child_ids: list[str] = []
        for child in child_items:
            require(isinstance(child, dict), "transition child is not an object")
            child_id = child.get("id")
            require(
                isinstance(child_id, str)
                and child_id not in children
                and child.get("parent_id") == parent_id,
                "transition child identity is malformed or duplicated",
            )
            children[child_id] = child
            child_ids.append(child_id)
        by_parent[parent_id] = tuple(child_ids)
    require(
        by_parent == TRANSITION_PARENT_TO_CHILDREN,
        "transition proof topology differs from the reviewed 18-parent contract",
    )
    require(
        tuple(children) == TRANSITION_ENTRY_IDS,
        "transition proof child order/set differs from the reviewed 30-child contract",
    )
    return children


def _validate_transition_entries(
    entries: Mapping[str, dict[str, Any]], children: Mapping[str, dict[str, Any]]
) -> None:
    compared_fields = (
        "parent_id",
        "logical_class",
        "match",
        "disposition",
        "attribution",
        "expected_units",
        "expected_signature_count",
        "expected_signature_population_sha256",
    )
    for entry_id in TRANSITION_ENTRY_IDS:
        require(entry_id in entries, f"transition ledger entry missing: {entry_id}")
        entry = entries[entry_id]
        child = children[entry_id]
        for field in compared_fields:
            require(
                entry.get(field) == child.get(field),
                f"transition ledger/receipt contract drift: {entry_id}.{field}",
            )
        transition = _mapping_at(
            entry, ("evidence", "transition"), label=f"{entry_id} transition evidence"
        )
        require(
            isinstance(transition, dict)
            and transition.get("parent_id") == child["parent_id"]
            and transition.get("child_id") == entry_id,
            f"transition evidence identity drift: {entry_id}",
        )


def _validate_cafta_embedding(transition: Proof, cafta: Proof) -> None:
    transitions = transition.document["transitions"]
    cafta_transition = next(
        (item for item in transitions if item.get("parent_id") == "cafta-52i-deferred"),
        None,
    )
    require(isinstance(cafta_transition, dict), "CAFTA transition is missing")
    embedded = _mapping_at(
        cafta_transition,
        ("evidence", "cafta_supersession_receipt"),
        label="embedded CAFTA supersession proof",
    )
    require(
        isinstance(embedded, dict)
        and embedded.get("file") == cafta.file_receipt
        and embedded.get("payload") == cafta.document,
        "transition proof does not embed the exact current CAFTA proof",
    )


def _validate_class_entries(
    entries: Mapping[str, dict[str, Any]],
    proof: Proof,
    entry_ids: tuple[str, ...],
    evidence_key: str,
) -> None:
    classes = proof.document.get("classes")
    require(isinstance(classes, list), f"{evidence_key} proof classes are malformed")
    by_id: dict[str, dict[str, Any]] = {}
    for item in classes:
        require(isinstance(item, dict), f"{evidence_key} proof class is malformed")
        class_id = item.get("id")
        require(
            isinstance(class_id, str) and class_id not in by_id,
            f"{evidence_key} proof class identity is malformed or duplicated",
        )
        by_id[class_id] = item
    require(
        tuple(by_id) == entry_ids,
        f"{evidence_key} proof classes differ from the reviewed ledger classes",
    )
    for entry_id in entry_ids:
        require(entry_id in entries, f"proof ledger entry missing: {entry_id}")
        entry = entries[entry_id]
        item = by_id[entry_id]
        for field in (
            "disposition",
            "attribution",
            "expected_units",
            "expected_signature_count",
            "expected_signature_population_sha256",
            "signatures",
        ):
            require(
                entry.get(field) == item.get(field),
                f"ledger/proof class drift: {entry_id}.{field}",
            )
        evidence = _mapping_at(
            entry,
            ("evidence", evidence_key),
            label=f"{entry_id} {evidence_key} evidence",
        )
        require(
            isinstance(evidence, dict)
            and evidence.get("receipt") == proof.file_receipt["path"]
            and evidence.get("identity_population_sha256")
            == item.get("identity_population_sha256"),
            f"ledger/proof evidence identity drift: {entry_id}",
        )


def _targets(
    transition: Proof,
    cafta: Proof,
    steel: Proof,
    remaining: Proof,
) -> tuple[Target, ...]:
    result = [
        Target(
            entry_id,
            ("evidence", "transition", "receipt_payload_sha256"),
            transition.payload_sha256,
        )
        for entry_id in TRANSITION_ENTRY_IDS
    ]
    result.append(
        Target(
            CAFTA_ENTRY_ID,
            ("evidence", "cafta_supersession_receipt_payload_sha256"),
            cafta.payload_sha256,
        )
    )
    for entry_id in STEEL_ENTRY_IDS:
        result.extend(
            (
                Target(
                    entry_id,
                    ("evidence", "steel_scope_projection", "sha256"),
                    steel.file_receipt["sha256"],
                ),
                Target(
                    entry_id,
                    (
                        "evidence",
                        "steel_scope_projection",
                        "receipt_payload_sha256",
                    ),
                    steel.payload_sha256,
                ),
            )
        )
    for entry_id in REMAINING_ENTRY_IDS:
        result.extend(
            (
                Target(
                    entry_id,
                    ("evidence", "remaining_residuals", "sha256"),
                    remaining.file_receipt["sha256"],
                ),
                Target(
                    entry_id,
                    (
                        "evidence",
                        "remaining_residuals",
                        "receipt_payload_sha256",
                    ),
                    remaining.payload_sha256,
                ),
            )
        )
    require(len(result) == EXPECTED_TARGET_COUNT, "internal target count drift")
    require(
        len({target.address for target in result}) == EXPECTED_TARGET_COUNT,
        "internal target address duplication",
    )
    return tuple(result)


def _actual_proof_hash_addresses(
    entries: Mapping[str, dict[str, Any]],
) -> set[tuple[str, tuple[str, ...]]]:
    result: set[tuple[str, tuple[str, ...]]] = set()
    watched = {
        ("evidence", "transition", "receipt_payload_sha256"),
        ("evidence", "cafta_supersession_receipt_payload_sha256"),
        ("evidence", "steel_scope_projection", "sha256"),
        ("evidence", "steel_scope_projection", "receipt_payload_sha256"),
        ("evidence", "remaining_residuals", "sha256"),
        ("evidence", "remaining_residuals", "receipt_payload_sha256"),
    }

    def walk(entry_id: str, value: Any, path: tuple[str, ...] = ()) -> None:
        if path in watched:
            require(
                isinstance(value, str) and HEX64.fullmatch(value) is not None,
                f"malformed proof hash scalar: {entry_id}.{'.'.join(path)}",
            )
            result.add((entry_id, path))
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(key, str):
                    walk(entry_id, child, (*path, key))
        elif isinstance(value, list):
            for child in value:
                walk(entry_id, child, path)

    for entry_id, entry in entries.items():
        walk(entry_id, entry)
    return result


def _node_mapping(node: Node, *, label: str) -> dict[str, Node]:
    require(isinstance(node, MappingNode), f"YAML node is not a mapping: {label}")
    result: dict[str, Node] = {}
    for key_node, value_node in node.value:
        require(isinstance(key_node, ScalarNode), f"non-scalar YAML key: {label}")
        key = key_node.value
        require(key not in result, f"duplicate YAML node key: {label}.{key}")
        result[key] = value_node
    return result


def _target_nodes(text: str, targets: Sequence[Target]) -> dict[Target, ScalarNode]:
    root = yaml.compose(text, Loader=UniqueSafeLoader)
    require(root is not None, "empty ledger YAML node tree")
    root_map = _node_mapping(root, label="root")
    entries_node = root_map.get("entries")
    require(
        isinstance(entries_node, SequenceNode), "ledger entries YAML node is not a list"
    )
    nodes_by_id: dict[str, MappingNode] = {}
    for item in entries_node.value:
        item_map = _node_mapping(item, label="entry")
        id_node = item_map.get("id")
        require(
            isinstance(id_node, ScalarNode), "ledger entry id YAML node is malformed"
        )
        require(
            id_node.value not in nodes_by_id,
            f"duplicate ledger node id: {id_node.value}",
        )
        require(isinstance(item, MappingNode), "ledger entry YAML node is malformed")
        nodes_by_id[id_node.value] = item
    result: dict[Target, ScalarNode] = {}
    for target in targets:
        require(
            target.entry_id in nodes_by_id,
            f"target YAML entry missing: {target.entry_id}",
        )
        current: Node = nodes_by_id[target.entry_id]
        for part in target.path:
            current = _node_mapping(
                current, label=f"{target.entry_id}.{'.'.join(target.path)}"
            ).get(part)  # type: ignore[assignment]
            require(current is not None, f"target YAML path missing: {target.address}")
        require(
            isinstance(current, ScalarNode)
            and current.tag == "tag:yaml.org,2002:str"
            and HEX64.fullmatch(current.value) is not None,
            f"target YAML scalar is not a lowercase SHA-256: {target.address}",
        )
        result[target] = current
    require(len(result) == EXPECTED_TARGET_COUNT, "target YAML node count drift")
    return result


def _render_scalar(node: ScalarNode, value: str) -> str:
    if node.style == "'":
        return "'" + value.replace("'", "''") + "'"
    if node.style == '"':
        return json.dumps(value)
    require(node.style is None, "unsupported YAML scalar style for proof hash")
    return value


def _render_rebound_ledger(
    text: str, targets: Sequence[Target]
) -> tuple[str, tuple[Target, ...]]:
    nodes = _target_nodes(text, targets)
    replacements: list[tuple[int, int, str, Target]] = []
    changed: list[Target] = []
    for target, node in nodes.items():
        if node.value != target.value:
            changed.append(target)
        replacements.append(
            (
                node.start_mark.index,
                node.end_mark.index,
                _render_scalar(node, target.value),
                target,
            )
        )
    spans = sorted((start, end) for start, end, _, _ in replacements)
    require(
        all(previous[1] <= current[0] for previous, current in zip(spans, spans[1:])),
        "target YAML scalar spans overlap",
    )
    result = text
    for start, end, replacement, _target in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result, tuple(changed)


def prepare_plan(
    *,
    repo_root: Path = REPO_ROOT,
    ledger_path: Path = DEFAULT_LEDGER,
    transition_receipt_path: Path = DEFAULT_TRANSITION_RECEIPT,
    cafta_receipt_path: Path = DEFAULT_CAFTA_RECEIPT,
    steel_receipt_path: Path = DEFAULT_STEEL_RECEIPT,
    remaining_receipt_path: Path = DEFAULT_REMAINING_RECEIPT,
    eval_manifest_path: Path = DEFAULT_EVAL_MANIFEST,
    comparison_receipt_path: Path = DEFAULT_COMPARISON_RECEIPT,
) -> Plan:
    repo_root = repo_root.resolve()
    ledger_snapshot = snapshot_file(ledger_path)
    original = parse_yaml(ledger_snapshot.body, label=str(ledger_path))
    entries = _entry_catalog(original)

    transition = load_proof(transition_receipt_path, TRANSITION_SCHEMA, repo_root)
    cafta = load_proof(cafta_receipt_path, CAFTA_SCHEMA, repo_root)
    steel = load_proof(steel_receipt_path, STEEL_SCHEMA, repo_root)
    remaining = load_proof(remaining_receipt_path, REMAINING_SCHEMA, repo_root)
    proofs = {
        "transition": transition,
        "cafta": cafta,
        "steel": steel,
        "remaining": remaining,
    }
    manifest_snapshot = snapshot_file(eval_manifest_path)
    comparison_snapshot = snapshot_file(comparison_receipt_path)
    _manifest, _comparison, artifact_snapshot = _validate_common_bindings(
        proofs, manifest_snapshot, comparison_snapshot, repo_root
    )

    children = _transition_children(transition)
    _validate_transition_entries(entries, children)
    _validate_cafta_embedding(transition, cafta)
    _validate_class_entries(entries, steel, STEEL_ENTRY_IDS, "steel_scope_projection")
    _validate_class_entries(
        entries, remaining, REMAINING_ENTRY_IDS, "remaining_residuals"
    )

    targets = _targets(transition, cafta, steel, remaining)
    expected_addresses = {target.address for target in targets}
    require(
        _actual_proof_hash_addresses(entries) == expected_addresses,
        "ledger proof-hash field set differs from the exact 39-field contract",
    )
    for target in targets:
        value = _mapping_at(
            entries[target.entry_id],
            target.path,
            label=f"target {target.entry_id}.{'.'.join(target.path)}",
        )
        require(
            isinstance(value, str) and HEX64.fullmatch(value) is not None,
            f"ledger target is not a lowercase SHA-256: {target.address}",
        )

    try:
        ledger_text = ledger_snapshot.body.decode()
    except UnicodeDecodeError as exc:
        raise ValueError("ledger is not UTF-8") from exc
    output_text, changed = _render_rebound_ledger(ledger_text, targets)
    require(
        len(changed) in {0, EXPECTED_TARGET_COUNT},
        "partially rebound ledger: expected either 0 or exactly 39 stale scalars, "
        f"found {len(changed)}",
    )

    expected = copy.deepcopy(original)
    expected_entries = _entry_catalog(expected)
    for target in targets:
        _set_mapping_at(expected_entries[target.entry_id], target.path, target.value)
    rendered = parse_yaml(output_text, label="rendered rebound ledger")
    require(
        rendered == expected,
        "rendered ledger changed parsed structure outside the exact 39 targets",
    )
    if not changed:
        require(
            output_text == ledger_text, "current ledger would change byte formatting"
        )

    evidence_snapshots = (
        transition.snapshot,
        cafta.snapshot,
        steel.snapshot,
        remaining.snapshot,
        manifest_snapshot,
        comparison_snapshot,
        artifact_snapshot,
    )
    proof_summary = {
        name: {
            "file_sha256": proof.file_receipt["sha256"],
            "payload_sha256": proof.payload_sha256,
        }
        for name, proof in proofs.items()
    }
    return Plan(
        ledger_snapshot,
        evidence_snapshots,
        original,
        expected,
        output_text.encode(),
        targets,
        changed,
        proof_summary,
    )


@contextmanager
def _publication_lock(*, eval_manifest_path: Path, ledger_path: Path) -> Iterator[None]:
    """Serialize campaign transitions, then lock the current ledger inode.

    The manifest lock is the campaign-wide lock already used by evaluate,
    compare, and the large proof producers.  Acquiring it first gives every
    rebinder process the same deterministic order.  Opening the ledger only
    after that acquisition avoids waiting on an inode another process replaced.
    """

    eval_manifest_path = eval_manifest_path.resolve()
    ledger_path = ledger_path.resolve()
    manifest_lock_path = eval_manifest_path.with_name(
        f".{eval_manifest_path.name}.lock"
    )
    manifest_lock_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_lock_path.open("a+") as manifest_lock:
        fcntl.flock(manifest_lock.fileno(), fcntl.LOCK_EX)
        try:
            with ledger_path.open("rb") as ledger_lock:
                fcntl.flock(ledger_lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(ledger_lock.fileno(), fcntl.LOCK_UN)
        finally:
            fcntl.flock(manifest_lock.fileno(), fcntl.LOCK_UN)


def _atomic_publish(
    plan: Plan, *, before_replace: Callable[[], None] | None = None
) -> None:
    ledger = plan.ledger_snapshot.path
    require(
        plan.ledger_snapshot.body is not None,
        "ledger snapshot body was not retained for conditional rollback",
    )
    previous_mode = stat.S_IMODE(ledger.stat().st_mode)
    temporary: Path | None = None
    rollback: Path | None = None

    def write_temporary(*, prefix: str, body: bytes) -> tuple[Path, Snapshot]:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=ledger.parent,
            prefix=prefix,
            delete=False,
        ) as target:
            path = Path(target.name)
            target.write(body)
            target.flush()
            os.fchmod(target.fileno(), previous_mode)
            os.fsync(target.fileno())
        return path, snapshot_file(path)

    def fsync_directory() -> None:
        directory_fd = os.open(ledger.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    try:
        temporary, prepared_publication = write_temporary(
            prefix=ledger.name + ".rebind.", body=plan.output
        )
        rollback, _prepared_rollback = write_temporary(
            prefix=ledger.name + ".rollback.", body=plan.ledger_snapshot.body
        )
        for snapshot in (*plan.evidence_snapshots, plan.ledger_snapshot):
            require_snapshot_current(snapshot)
        if before_replace is not None:
            before_replace()
            # Re-run the conditional check after the injected race point.
            for snapshot in (*plan.evidence_snapshots, plan.ledger_snapshot):
                require_snapshot_current(snapshot)
        require_snapshot_current(prepared_publication)
        require(
            stat.S_IMODE(temporary.stat().st_mode) == previous_mode,
            "prepared ledger publication mode drifted",
        )
        os.replace(temporary, ledger)
        temporary = None
        fsync_directory()

        published: Snapshot | None = None
        try:
            candidate = snapshot_file(ledger)
            require(
                candidate.identity[:2] == prepared_publication.identity[:2]
                and candidate.sha256 == prepared_publication.sha256
                and candidate.body == prepared_publication.body == plan.output
                and stat.S_IMODE(ledger.stat().st_mode) == previous_mode,
                "published ledger bytes or mode drifted",
            )
            published = candidate
            for snapshot in plan.evidence_snapshots:
                require_snapshot_current(snapshot)
        except Exception as validation_error:
            # A proof producer can only race this point by ignoring the shared
            # manifest lock.  Every repository writer of these receipts and
            # this ledger honors that lock, which is the serialization contract
            # covering the final current-state check and rollback rename.
            # Restore only while the path still names this process's published
            # inode; after a successful publication check, also require its
            # exact authenticated identity and body.
            current = snapshot_file(ledger)
            still_ours = current.identity[:2] == prepared_publication.identity[:2]
            if published is not None:
                still_ours = (
                    still_ours
                    and current.identity == published.identity
                    and current.sha256 == published.sha256
                    and current.body == published.body
                    and stat.S_IMODE(ledger.stat().st_mode) == previous_mode
                )
            require(
                still_ours,
                "post-publish evidence drifted and ledger changed; "
                "conditional rollback refused",
            )
            require(rollback is not None, "conditional rollback was not prepared")
            require_snapshot_current(_prepared_rollback)
            os.replace(rollback, ledger)
            rollback = None
            fsync_directory()
            restored = snapshot_file(ledger)
            require(
                restored.sha256 == plan.ledger_snapshot.sha256
                and restored.body == plan.ledger_snapshot.body
                and stat.S_IMODE(ledger.stat().st_mode) == previous_mode,
                "conditional rollback did not restore the exact prior ledger",
            )
            raise validation_error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if rollback is not None:
            rollback.unlink(missing_ok=True)


def run(
    *,
    mode: str,
    _before_replace: Callable[[], None] | None = None,
    **paths: Any,
) -> dict[str, Any]:
    require(mode in {"generate", "check"}, f"unsupported mode: {mode}")
    ledger_path = Path(paths.get("ledger_path", DEFAULT_LEDGER))
    eval_manifest_path = Path(paths.get("eval_manifest_path", DEFAULT_EVAL_MANIFEST))
    with _publication_lock(
        eval_manifest_path=eval_manifest_path,
        ledger_path=ledger_path,
    ):
        plan = prepare_plan(**paths)
        if mode == "generate":
            require(
                len(plan.changed) == EXPECTED_TARGET_COUNT,
                "generate requires exactly 39 stale scalars; use --check for a current ledger",
            )
            _atomic_publish(plan, before_replace=_before_replace)
        else:
            require(
                not plan.changed,
                f"stale tariff disposition ledger: {len(plan.changed)} of 39 scalars differ",
            )
            for snapshot in (*plan.evidence_snapshots, plan.ledger_snapshot):
                require_snapshot_current(snapshot)
    return {
        "mode": mode,
        "ledger": str(plan.ledger_snapshot.path),
        "target_scalars": len(plan.targets),
        "changed_scalars": len(plan.changed),
        "proofs": plan.proof_summary,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--transition-receipt", type=Path, default=DEFAULT_TRANSITION_RECEIPT
    )
    parser.add_argument("--cafta-receipt", type=Path, default=DEFAULT_CAFTA_RECEIPT)
    parser.add_argument("--steel-receipt", type=Path, default=DEFAULT_STEEL_RECEIPT)
    parser.add_argument(
        "--remaining-receipt", type=Path, default=DEFAULT_REMAINING_RECEIPT
    )
    parser.add_argument("--eval-manifest", type=Path, default=DEFAULT_EVAL_MANIFEST)
    parser.add_argument(
        "--comparison-receipt", type=Path, default=DEFAULT_COMPARISON_RECEIPT
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run(
        mode="generate" if args.generate else "check",
        repo_root=args.repo_root,
        ledger_path=args.ledger,
        transition_receipt_path=args.transition_receipt,
        cafta_receipt_path=args.cafta_receipt,
        steel_receipt_path=args.steel_receipt,
        remaining_receipt_path=args.remaining_receipt,
        eval_manifest_path=args.eval_manifest,
        comparison_receipt_path=args.comparison_receipt,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
