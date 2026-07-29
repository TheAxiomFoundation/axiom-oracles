#!/usr/bin/env python3
"""Compute AUTOGO certification for exact legal nodes.

This is the integration layer between the compiled artifact, closure summary,
comparison/evidence stack, exercise census, executable receipt producer, and
the generated ``certified-nodes.yaml`` ledger.  It intentionally does not
infer missing applicability, roots, provenance, or exercise coverage.

Examples::

    uv run python scripts/certify_nodes.py \
      us:statutes/26/3101/b/1#medicare_wage_tax \
      --artifact build/us-payroll.compiled.json \
      --node-index conformance/node-certification-index.json \
      --closure-summary closure/summary.json \
      --comparisons conformance/node-comparisons.json \
      --exercise-census conformance/exercise-census.json \
      --executable certificates/executable/node-results.json \
      --run-manifest certificates/certify-nodes-run.json \
      --output /path/to/ops/launch-readiness/certified-nodes.yaml

    # Recompute without writing and fail on any byte drift.
    uv run python scripts/certify_nodes.py ... --check
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

LEDGER_SCHEMA = "axiom.certified_nodes.v1"
RESULT_SCHEMA = "axiom_oracles.certify_nodes.result.v1"
NODE_INDEX_SCHEMA = "axiom_oracles.node_certification_index.v1"
CLOSURE_SCHEMA = "axiom_oracles.closure.summary.v1"
COMPARISON_SCHEMA = "axiom_oracles.node_comparisons.v1"
CENSUS_SCHEMA = "axiom_oracles.exercise_census.v1"
EXECUTABLE_SCHEMA = "axiom_oracles.node_executable.v1"
RECEIPT_SCHEMA = "axiom_oracles.executable_receipt.v1"
RUN_SCHEMA = "axiom_oracles.certify_nodes.run.v1"
GOVERNANCE_SCHEMA = "axiom_oracles.certify_nodes.governance.v1"
REPORT_SCHEMA = "axiom.comparison_report.v2.1"

CRITERIA = (
    "provision_rooted",
    "conformant",
    "exercised",
    "closed",
    "executable",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_NODE_RE = re.compile(
    r"^[a-z]{2}(?:-[a-z0-9]+)*:"
    r"(?:legislation|policies|regulations|statutes)/"
    r"(?:[A-Za-z0-9_.~-]+/)*[A-Za-z0-9_.~-]+#[A-Za-z0-9_.-]+$"
)

HEADER = """\
# Certified nodes — the single source of truth for what the app shows as certified.
#
# RULING (Max, 2026-07-27 late): there is NO human review gate on certification.
# Axiom's gates are deterministic checks, oracles, and adversarial verification
# — never a person's signature. This file is therefore GENERATED OUTPUT ONLY:
# when the certification harness computes all five criteria green for a node,
# the node appears here automatically ("autogo"), and nothing else can add one.
# The earlier attested_by/human-check pathway in this file's first draft is
# deleted, not deferred: a hand-added entry is invalid by definition, whoever
# adds it and however good the evidence looks.
#
# Autogo is live only when the harness is bulletproof. The named holes on that
# critical path, tracked where listed:
#   1. computed(executable): a sign-only CI producer that runs the PUBLISHED
#      artifact on the RELEASED engine by the stranger path and emits the
#      receipt deterministically (notary pattern — no model calls, no creds).
#   2. computed(closed): closure harness lands (axiom-oracles#400) and runs
#      per-node over declared roots.
#   3. computed(exercised): census + evidence stack unparked — the two open
#      category-(a) residues on #378/#379 must close first; they are exactly
#      the kind of hole autogo cannot carry.
#   4. provision_rooted as a computed field: engine#115 node-provenance
#      annotations merged and artifacts rebuilt to carry them.
#   5. Verifier governance (the self-certification question): the harness that
#      grants certification must be separately governed from the lanes that
#      produce candidates — protocol frozen before any candidate sha is known.
#      Decision open with Max.
#   6. Mutant discipline: every gate ships with the input it rejects, and the
#      gate set survives adversarial review.
#
# Until autogo is live this file stays EMPTY — including for nodes whose
# evidence packages look complete. Five nodes currently sit at 4-of-5 with
# agent-assembled evidence (rulespec-us #1149 #1161 #1162 #1163 #1165); they
# certify themselves the moment the harness goes green, and not before.
# The five criteria are unchanged: provision_rooted, conformant, exercised,
# closed, executable — all computed, zero defects.
"""

ENTRY_SHAPE_COMMENT = """\
# Entry shape — written only by the harness. No mode field exists: every
# criterion is computed, or the entry does not exist.
#
# - node: us:statutes/26/3101/b/1#medicare_wage_tax
#   label: Employee Medicare payroll tax
#   provision: 26 USC 3101(b)(1)
#   corpus_citation_path: us/statute/26/3101
#   certified_at: <UTC timestamp of the harness run>
#   harness:
#     run: <CI run id + workflow sha — the producer that computed this entry>
#     certify_check: <sha of the certify --check pass>
#   pinned:
#     rulespec_us: <sha>
#     corpus: <sha>
#     engine: <released version>
#     artifact: <content hash>
#   criteria:   # every value computed; evidence = machine-checkable pointers
#     provision_rooted: {holds: true, evidence: <artifact node-provenance field>}
#     conformant:       {holds: true, evidence: <committed report + dispositions>}
#     exercised:        {holds: true, evidence: <census rows>}
#     closed:           {holds: true, evidence: <closure summary rows>}
#     executable:       {holds: true, evidence: <stranger receipt from the CI producer>}
"""

_CODE_ALIASES = {
    "producer_schema_invalid": "producer_invalid",
    "node_metadata_invalid": "graph_invalid",
    "dependency_graph_missing": "graph_missing",
    "dependency_graph_invalid": "graph_invalid",
    "dependency_unknown": "graph_invalid",
    "unverified_provenance": "unverified",
    "artifact_pin_mismatch": "pin_mismatch",
    "node_declaration_missing": "declaration_missing",
    "closure_roots_missing": "declaration_missing",
    "closure_root_missing": "root_missing",
    "closure_summary_invalid": "producer_invalid",
    "closure_pending": "pending",
    "comparison_applicability_missing": "declaration_missing",
    "comparison_applicability_invalid": "declaration_invalid",
    "comparison_missing": "row_missing",
    "comparison_report_missing": "report_missing",
    "comparison_report_invalid": "report_invalid",
    "comparison_declaration_mismatch": "declaration_mismatch",
    "comparison_uncommitted": "not_committed",
    "comparison_zero_cases": "empty",
    "comparison_unbound": "unbound",
    "comparison_not_fully_reconciled": "not_full",
    "comparison_result_invalid": "producer_invalid",
    "comparison_errors": "errors",
    "unexplained_mismatch": "unexplained",
    "axiom_attributed_mismatch": "axiom_attributed",
    "exercise_dimensions_invalid": "declaration_invalid",
    "exercise_suite_missing": "suite_missing",
    "exercise_report_identity_mismatch": "report_mismatch",
    "exercise_contested_reports": "contested_reports",
    "exercise_evidence_missing": "evidence_missing",
    "dimension_bridged": "dimension_bridged",
    "dimension_missing": "dimension_missing",
    "dimension_constant": "dimension_constant",
    "exercise_dimension_invalid": "dimension_unvaried",
    "executable_unvalidated": "unvalidated",
    "executable_receipt_missing": "receipt_invalid",
    "executable_receipt_invalid": "receipt_invalid",
    "executable_coverage_invalid": "coverage_invalid",
    "output_drift": "drift",
}


@dataclass(frozen=True, slots=True)
class Loaded:
    """One producer document and its immutable byte identity."""

    name: str
    path: Path
    value: dict[str, Any] | None
    sha256: str | None
    error: str | None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _producer_path(root: Path, value: Any) -> Path | None:
    """Resolve one producer-declared evidence path below ``root``."""

    if not _is_string(value):
        return None
    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    resolved = (root / relative).resolve()
    if resolved == root or root not in resolved.parents:
        return None
    return resolved


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.YAMLError("unhashable YAML mapping key") from exc
        if duplicate:
            raise yaml.YAMLError(f"duplicate YAML mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _reject_nonfinite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not allowed")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_nonfinite(key)
            _reject_nonfinite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite(item)


def _load(root: Path, value: str | Path, name: str) -> Loaded:
    path = _resolve(root, value)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return Loaded(name, path, None, None, f"cannot read {name}: {exc}")
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            payload = yaml.load(raw, Loader=_UniqueKeyLoader)
        else:
            payload = json.loads(
                raw,
                object_pairs_hook=_json_object,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON number: {value}")
                ),
            )
        _reject_nonfinite(payload)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ValueError,
    ) as exc:
        return Loaded(name, path, None, _sha256(raw), f"invalid {name}: {exc}")
    if not isinstance(payload, dict):
        return Loaded(
            name,
            path,
            None,
            _sha256(raw),
            f"{name} must contain an object",
        )
    return Loaded(name, path, payload, _sha256(raw), None)


def _path_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_int(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _is_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reason(
    criterion: str,
    code: str,
    producer: str,
    detail: str,
    *,
    evidence: str | None = None,
) -> dict[str, Any]:
    if "." not in code:
        code = f"{criterion}.{_CODE_ALIASES.get(code, code)}"
    row: dict[str, Any] = {
        "criterion": criterion,
        "code": code,
        "producer": producer,
        "detail": detail,
    }
    if evidence is not None:
        row["evidence"] = evidence
    return row


def _missing(criterion: str, loaded: Loaded) -> dict[str, Any]:
    return _reason(
        criterion,
        "producer_missing",
        loaded.name,
        loaded.error or f"{loaded.name} is unavailable",
    )


def _schema_reason(
    criterion: str, loaded: Loaded, expected: str
) -> dict[str, Any] | None:
    if loaded.value is None:
        return _missing(criterion, loaded)
    observed = loaded.value.get("schema")
    if observed != expected:
        return _reason(
            criterion,
            "producer_schema_invalid",
            loaded.name,
            f"expected schema {expected!r}, got {observed!r}",
        )
    return None


def _artifact_nodes(
    artifact: Loaded, node_id: str
) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Resolve ``node_id`` plus all transitive dependencies."""

    reasons: list[dict[str, Any]] = []
    if artifact.value is None:
        return [], {}, [_missing("provision_rooted", artifact)]
    if artifact.value.get("artifact_format_version") != 2 or not isinstance(
        artifact.value.get("program"), dict
    ):
        reasons.append(
            _reason(
                "provision_rooted",
                "producer_schema_invalid",
                artifact.name,
                (
                    "compiled artifact must use the engine's exact v2 "
                    "artifact_format_version and carry a program object"
                ),
            )
        )
    metadata = artifact.value.get("metadata")
    if not isinstance(metadata, dict):
        return (
            [],
            {},
            [
                _reason(
                    "provision_rooted",
                    "producer_missing",
                    artifact.name,
                    "compiled artifact has no metadata object",
                )
            ],
        )
    raw_nodes = metadata.get("nodes")
    if not isinstance(raw_nodes, list):
        return (
            [],
            {},
            [
                _reason(
                    "provision_rooted",
                    "producer_missing",
                    artifact.name,
                    "compiled artifact metadata.nodes producer is absent",
                )
            ],
        )
    nodes: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(raw_nodes):
        if not isinstance(row, dict) or not _is_string(row.get("id")):
            reasons.append(
                _reason(
                    "provision_rooted",
                    "node_metadata_invalid",
                    artifact.name,
                    f"metadata.nodes[{index}] lacks a nonempty id",
                )
            )
            continue
        item_id = str(row["id"])
        if item_id in nodes:
            reasons.append(
                _reason(
                    "provision_rooted",
                    "node_metadata_invalid",
                    artifact.name,
                    f"metadata.nodes contains duplicate id {item_id!r}",
                )
            )
            continue
        nodes[item_id] = row

    graph = metadata.get("dependency_graph")
    if not isinstance(graph, dict):
        reasons.append(
            _reason(
                "provision_rooted",
                "dependency_graph_missing",
                artifact.name,
                "compiled artifact metadata.dependency_graph is absent",
            )
        )
        return [], nodes, reasons
    if node_id not in nodes:
        reasons.append(
            _reason(
                "provision_rooted",
                "node_missing",
                artifact.name,
                f"requested node {node_id!r} is absent from metadata.nodes",
            )
        )
        return [], nodes, reasons

    ordered: list[str] = []
    seen: set[str] = set()
    active: set[str] = set()
    stack: list[tuple[str, bool]] = [(node_id, False)]
    while stack:
        current, exiting = stack.pop()
        if exiting:
            active.discard(current)
            seen.add(current)
            continue
        if current in seen:
            continue
        if current in active:
            reasons.append(
                _reason(
                    "provision_rooted",
                    "dependency_graph_invalid",
                    artifact.name,
                    f"dependency graph contains a cycle through {current!r}",
                )
            )
            continue
        active.add(current)
        ordered.append(current)
        stack.append((current, True))
        dependencies = graph.get(current)
        if not isinstance(dependencies, list) or not all(
            _is_string(item) for item in dependencies
        ):
            reasons.append(
                _reason(
                    "provision_rooted",
                    "dependency_graph_invalid",
                    artifact.name,
                    f"dependency row for {current!r} is missing or malformed",
                )
            )
            continue
        if len(set(dependencies)) != len(dependencies):
            reasons.append(
                _reason(
                    "provision_rooted",
                    "dependency_graph_invalid",
                    artifact.name,
                    f"dependency row for {current!r} contains duplicate nodes",
                )
            )
        for dependency in reversed(dependencies):
            if dependency not in nodes:
                reasons.append(
                    _reason(
                        "provision_rooted",
                        "dependency_unknown",
                        artifact.name,
                        f"{current!r} depends on unknown node {dependency!r}",
                    )
                )
                continue
            if dependency in active:
                reasons.append(
                    _reason(
                        "provision_rooted",
                        "dependency_graph_invalid",
                        artifact.name,
                        (
                            "dependency graph contains a cycle from "
                            f"{current!r} to {dependency!r}"
                        ),
                    )
                )
                continue
            stack.append((dependency, False))
    return ordered, nodes, reasons


def _node_declarations(
    node_index: Loaded,
    artifact: Loaded,
    node_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    schema = _schema_reason("provision_rooted", node_index, NODE_INDEX_SCHEMA)
    if schema:
        return {}, [schema]
    assert node_index.value is not None
    if node_index.value.get("artifact_sha256") != artifact.sha256:
        reasons.append(
            _reason(
                "provision_rooted",
                "artifact_pin_mismatch",
                node_index.name,
                "node index artifact_sha256 does not match the compiled artifact bytes",
            )
        )
    producer = node_index.value.get("producer")
    if not isinstance(producer, dict) or producer.get("mode") != "computed":
        reasons.append(
            _reason(
                "provision_rooted",
                "producer_missing",
                node_index.name,
                "node index is not marked mode=computed",
            )
        )
    declarations = node_index.value.get("nodes")
    if not isinstance(declarations, dict):
        reasons.append(
            _reason(
                "provision_rooted",
                "producer_missing",
                node_index.name,
                "node index has no nodes object",
            )
        )
        return {}, reasons
    clean: dict[str, dict[str, Any]] = {}
    for node_id in node_ids:
        declaration = declarations.get(node_id)
        if not isinstance(declaration, dict):
            reasons.append(
                _reason(
                    "provision_rooted",
                    "node_declaration_missing",
                    node_index.name,
                    f"node index has no declaration for subgraph node {node_id!r}",
                )
            )
            continue
        clean[node_id] = declaration
    return clean, reasons


def _provision_rooted(
    artifact: Loaded,
    node_ids: list[str],
    nodes: dict[str, dict[str, Any]],
    prior: list[dict[str, Any]],
    *,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reasons = list(prior)
    for item_id in node_ids:
        row = nodes[item_id]
        provenance = row.get("provenance", "unverified")
        citation = row.get("corpus_citation_path")
        if provenance != "provision_backed" or not _is_string(citation):
            reasons.append(
                _reason(
                    "provision_rooted",
                    "unverified_provenance",
                    artifact.name,
                    (
                        f"subgraph node {item_id!r} has provenance "
                        f"{provenance!r}; provision_backed with a citation is required"
                    ),
                    evidence=f"metadata.nodes[{item_id}]",
                )
            )
    evidence = {
        "artifact": _path_label(artifact.path, root),
        "sha256": artifact.sha256,
        "nodes": node_ids,
    }
    return {"holds": not reasons, "evidence": evidence}, reasons


def _run_context(
    run_manifest: Loaded,
    governance: Loaded,
    artifact: Loaded,
    producer_inputs: dict[str, Loaded],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    if run_manifest.value is None:
        return None, [
            _reason(
                "harness",
                "producer_missing",
                run_manifest.name,
                run_manifest.error or "certification run manifest is unavailable",
            )
        ]
    value = run_manifest.value
    if value.get("schema") != RUN_SCHEMA:
        reasons.append(
            _reason(
                "harness",
                "producer_schema_invalid",
                run_manifest.name,
                f"expected schema {RUN_SCHEMA!r}, got {value.get('schema')!r}",
            )
        )
    certified_at = value.get("certified_at")
    if not _is_string(certified_at):
        reasons.append(
            _reason(
                "harness",
                "harness_provenance_invalid",
                run_manifest.name,
                "certified_at must be a UTC RFC3339 timestamp",
            )
        )
    else:
        try:
            parsed = datetime.fromisoformat(str(certified_at).replace("Z", "+00:00"))
            if not str(certified_at).endswith("Z") or parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            reasons.append(
                _reason(
                    "harness",
                    "harness_provenance_invalid",
                    run_manifest.name,
                    "certified_at must be a UTC RFC3339 timestamp ending in Z",
                )
            )
    harness = value.get("harness")
    if not isinstance(harness, dict):
        harness = {}
        reasons.append(
            _reason(
                "harness",
                "harness_provenance_invalid",
                run_manifest.name,
                "harness object is missing",
            )
        )
    run_id = harness.get("ci_run_id")
    if not (
        (type(run_id) is int and run_id > 0)
        or (isinstance(run_id, str) and run_id.isdigit() and int(run_id) > 0)
    ):
        reasons.append(
            _reason(
                "harness",
                "harness_provenance_invalid",
                run_manifest.name,
                "harness.ci_run_id must be a positive integer",
            )
        )
    for field in ("workflow_sha", "certify_check"):
        if not isinstance(harness.get(field), str) or not _COMMIT_RE.fullmatch(
            harness[field]
        ):
            reasons.append(
                _reason(
                    "harness",
                    "harness_provenance_invalid",
                    run_manifest.name,
                    f"harness.{field} must be a full lowercase commit SHA",
                )
            )
    governed: dict[str, Any] = {}
    governance_schema = _schema_reason("harness", governance, GOVERNANCE_SCHEMA)
    if governance_schema:
        reasons.append(governance_schema)
    elif governance.value is not None:
        governed = governance.value
        for field in ("repository", "workflow_path", "event", "ref"):
            if not _is_string(governed.get(field)):
                reasons.append(
                    _reason(
                        "harness",
                        "governance_invalid",
                        governance.name,
                        f"{field} must be a nonempty string",
                    )
                )
            elif harness.get(field) != governed[field]:
                reasons.append(
                    _reason(
                        "harness",
                        "governance_mismatch",
                        governance.name,
                        f"harness.{field} is not the governed value",
                    )
                )
        allowlists = (
            ("workflow_sha", "allowed_workflow_shas"),
            ("certify_check", "allowed_certify_check_shas"),
        )
        for harness_field, governance_field in allowlists:
            allowed = governed.get(governance_field)
            if (
                not isinstance(allowed, list)
                or not allowed
                or not all(
                    isinstance(item, str) and _COMMIT_RE.fullmatch(item)
                    for item in allowed
                )
                or len(set(allowed)) != len(allowed)
            ):
                reasons.append(
                    _reason(
                        "harness",
                        "governance_invalid",
                        governance.name,
                        (
                            f"{governance_field} must be a nonempty, unique "
                            "array of full lowercase commit SHAs"
                        ),
                    )
                )
            elif harness.get(harness_field) not in allowed:
                reasons.append(
                    _reason(
                        "harness",
                        "governance_mismatch",
                        governance.name,
                        f"harness.{harness_field} is not allowlisted",
                    )
                )
    pins = value.get("pinned")
    if not isinstance(pins, dict):
        pins = {}
        reasons.append(
            _reason(
                "harness",
                "pin_missing",
                run_manifest.name,
                "pinned object is missing",
            )
        )
    for field in ("rulespec_us", "corpus"):
        if not isinstance(pins.get(field), str) or not _COMMIT_RE.fullmatch(
            pins[field]
        ):
            reasons.append(
                _reason(
                    "harness",
                    "pin_missing",
                    run_manifest.name,
                    f"pinned.{field} must be a full lowercase commit SHA",
                )
            )
    if not _is_string(pins.get("engine")):
        reasons.append(
            _reason(
                "harness",
                "pin_missing",
                run_manifest.name,
                "pinned.engine must name a released engine version",
            )
        )
    if not isinstance(pins.get("artifact"), str) or not _SHA256_RE.fullmatch(
        pins["artifact"]
    ):
        reasons.append(
            _reason(
                "harness",
                "pin_missing",
                run_manifest.name,
                "pinned.artifact must be a SHA-256 content hash",
            )
        )
    elif pins["artifact"] != artifact.sha256:
        reasons.append(
            _reason(
                "harness",
                "artifact_pin_mismatch",
                run_manifest.name,
                "pinned.artifact does not match the compiled artifact bytes",
            )
        )
    artifact_metadata = (
        artifact.value.get("metadata") if artifact.value is not None else None
    )
    artifact_pins = (
        artifact_metadata.get("pinned") if isinstance(artifact_metadata, dict) else None
    )
    expected_artifact_pins = {
        field: pins.get(field) for field in ("rulespec_us", "corpus", "engine")
    }
    if artifact_pins != expected_artifact_pins:
        reasons.append(
            _reason(
                "harness",
                "pin_mismatch",
                artifact.name,
                "compiled artifact metadata.pinned does not match the harness pins",
            )
        )

    inputs = value.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != set(producer_inputs):
        reasons.append(
            _reason(
                "harness",
                "harness_inputs_invalid",
                run_manifest.name,
                "run manifest must name exactly every producer input SHA-256",
            )
        )
    else:
        for name, loaded in producer_inputs.items():
            if loaded.sha256 is None or inputs.get(name) != loaded.sha256:
                reasons.append(
                    _reason(
                        "harness",
                        "harness_input_mismatch",
                        run_manifest.name,
                        f"inputs.{name} does not match the producer bytes",
                    )
                )
    verified_runs = governed.get("verified_runs")
    if not isinstance(verified_runs, list) or not all(
        isinstance(row, dict) for row in verified_runs
    ):
        reasons.append(
            _reason(
                "harness",
                "governance_invalid",
                governance.name,
                "verified_runs must be an array of separately governed run records",
            )
        )
    else:
        matching_runs = [
            row for row in verified_runs if str(row.get("ci_run_id")) == str(run_id)
        ]
        if len(matching_runs) != 1:
            reasons.append(
                _reason(
                    "harness",
                    "governance_mismatch",
                    governance.name,
                    "CI run id has no unique separately governed verification record",
                )
            )
        else:
            verified = matching_runs[0]
            for field, expected in (
                ("workflow_sha", harness.get("workflow_sha")),
                ("certify_check", harness.get("certify_check")),
                ("certified_at", certified_at),
            ):
                if verified.get(field) != expected:
                    reasons.append(
                        _reason(
                            "harness",
                            "governance_mismatch",
                            governance.name,
                            f"verified run carries a different {field}",
                        )
                    )
            if verified.get("inputs") != inputs:
                reasons.append(
                    _reason(
                        "harness",
                        "governance_mismatch",
                        governance.name,
                        "verified run does not bind the exact candidate producer bytes",
                    )
                )
            if verified.get("run_manifest_sha256") != run_manifest.sha256:
                reasons.append(
                    _reason(
                        "harness",
                        "governance_mismatch",
                        governance.name,
                        "verified run does not bind the exact run manifest bytes",
                    )
                )
    return (value if not reasons else None), reasons


def _closed(
    closure: Loaded,
    declarations: dict[str, dict[str, Any]],
    node_ids: list[str],
    pins: dict[str, Any] | None,
    *,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    schema = _schema_reason("closed", closure, CLOSURE_SCHEMA)
    if schema:
        reasons.append(schema)
    roots: list[str] = []
    seen_roots: set[str] = set()
    for node_id in node_ids:
        declaration = declarations.get(node_id)
        declared_roots = declaration.get("closure_roots") if declaration else None
        if (
            not isinstance(declared_roots, list)
            or not declared_roots
            or not all(_is_string(item) for item in declared_roots)
        ):
            reasons.append(
                _reason(
                    "closed",
                    "closure_roots_missing",
                    "node_index",
                    (
                        f"subgraph node {node_id!r} must name at least one "
                        "exact closure root"
                    ),
                )
            )
            continue
        if len(set(declared_roots)) != len(declared_roots):
            reasons.append(
                _reason(
                    "closed",
                    "declaration_invalid",
                    "node_index",
                    f"subgraph node {node_id!r} repeats a closure root",
                )
            )
        for root_id in declared_roots:
            if root_id not in seen_roots:
                seen_roots.add(root_id)
                roots.append(root_id)
    rows: dict[str, dict[str, Any]] = {}
    if closure.value is not None:
        raw_rows = closure.value.get("roots")
        if not isinstance(raw_rows, list):
            reasons.append(
                _reason(
                    "closed",
                    "producer_missing",
                    closure.name,
                    "closure summary has no roots array",
                )
            )
        else:
            for index, row in enumerate(raw_rows):
                if not isinstance(row, dict) or not _is_string(row.get("root")):
                    reasons.append(
                        _reason(
                            "closed",
                            "closure_summary_invalid",
                            closure.name,
                            f"closure roots[{index}] is malformed",
                        )
                    )
                    continue
                root_id = str(row["root"])
                if root_id in rows:
                    reasons.append(
                        _reason(
                            "closed",
                            "closure_summary_invalid",
                            closure.name,
                            f"closure root {root_id!r} appears more than once",
                        )
                    )
                    continue
                rows[root_id] = row
    for root_id in roots:
        row = rows.get(root_id)
        if row is None:
            reasons.append(
                _reason(
                    "closed",
                    "closure_root_missing",
                    closure.name,
                    f"declared closure root {root_id!r} is absent",
                )
            )
            continue
        by_status = row.get("by_status")
        if (
            not isinstance(by_status, dict)
            or set(by_status) != {"encoded", "excluded", "pending"}
            or any(
                not _is_int(by_status.get(status))
                for status in ("encoded", "excluded", "pending")
            )
        ):
            reasons.append(
                _reason(
                    "closed",
                    "closure_summary_invalid",
                    closure.name,
                    f"closure root {root_id!r} has malformed status counts",
                )
            )
            continue
        by_reason = row.get("by_reason")
        if (
            not isinstance(by_reason, dict)
            or any(
                not _is_string(reason) or not _is_int(count, minimum=1)
                for reason, count in by_reason.items()
            )
            or sum(by_reason.values()) != by_status["excluded"]
        ):
            reasons.append(
                _reason(
                    "closed",
                    "closure_summary_invalid",
                    closure.name,
                    (
                        f"closure root {root_id!r} excluded count is not "
                        "fully accounted for by_reason"
                    ),
                )
            )
        total = row.get("total")
        accounted = sum(
            by_status[status] for status in ("encoded", "excluded", "pending")
        )
        if not _is_int(total, minimum=1) or total != accounted:
            reasons.append(
                _reason(
                    "closed",
                    "closure_summary_invalid",
                    closure.name,
                    f"closure root {root_id!r} counts do not sum to total",
                )
            )
        if by_status["pending"] != 0:
            reasons.append(
                _reason(
                    "closed",
                    "closure_pending",
                    closure.name,
                    (
                        f"closure root {root_id!r} has "
                        f"{by_status['pending']} pending provision(s)"
                    ),
                )
            )
        if not isinstance(row.get("pins_sha256"), str) or not _SHA256_RE.fullmatch(
            row["pins_sha256"]
        ):
            reasons.append(
                _reason(
                    "closed",
                    "producer_provenance_missing",
                    closure.name,
                    f"closure root {root_id!r} lacks pins_sha256",
                )
            )
        expected = {"rulespec_us": None, "corpus": None}
        if pins:
            expected = {key: pins.get(key) for key in expected}
        if row.get("pinned") != expected:
            reasons.append(
                _reason(
                    "closed",
                    "pin_mismatch",
                    closure.name,
                    f"closure root {root_id!r} is not pinned to this harness vintage",
                )
            )
    evidence = {
        "summary": _path_label(closure.path, root),
        "sha256": closure.sha256,
        "roots": roots,
    }
    return {"holds": not reasons, "evidence": evidence}, reasons


def _comparison_declarations(
    declarations: dict[str, dict[str, Any]],
    node_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clean: list[dict[str, Any]] = []
    reasons: list[dict[str, Any]] = []
    for node_id in node_ids:
        declaration = declarations.get(node_id)
        comparisons = declaration.get("comparisons") if declaration else None
        if not isinstance(comparisons, list) or not comparisons:
            reasons.append(
                _reason(
                    "conformant",
                    "producer_missing",
                    "node_index",
                    (
                        f"subgraph node {node_id!r} has no applicable "
                        "comparison producer rows"
                    ),
                )
            )
            continue
        seen: set[str] = set()
        for index, row in enumerate(comparisons):
            if not isinstance(row, dict) or not _is_string(row.get("suite")):
                reasons.append(
                    _reason(
                        "conformant",
                        "comparison_applicability_missing",
                        "node_index",
                        (
                            f"subgraph node {node_id!r} comparisons[{index}] "
                            "has no suite"
                        ),
                    )
                )
                continue
            suite = str(row["suite"])
            if suite in seen:
                reasons.append(
                    _reason(
                        "conformant",
                        "comparison_applicability_invalid",
                        "node_index",
                        (
                            f"subgraph node {node_id!r} declares suite "
                            f"{suite!r} more than once"
                        ),
                    )
                )
                continue
            dimensions = row.get("required_dimensions")
            if (
                not isinstance(dimensions, list)
                or not dimensions
                or not all(_is_string(item) for item in dimensions)
                or len(set(dimensions)) != len(dimensions)
            ):
                reasons.append(
                    _reason(
                        "conformant",
                        "comparison_applicability_invalid",
                        "node_index",
                        (
                            f"subgraph node {node_id!r} suite {suite!r} "
                            "has invalid required_dimensions"
                        ),
                    )
                )
                continue
            seen.add(suite)
            clean.append({**row, "node": node_id})
    return clean, reasons


def _conformant(
    comparisons: Loaded,
    node_ids: list[str],
    applicable: list[dict[str, Any]],
    prior: list[dict[str, Any]],
    artifact: Loaded,
    pins: dict[str, Any] | None,
    *,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    reasons = list(prior)
    schema = _schema_reason("conformant", comparisons, COMPARISON_SCHEMA)
    if schema:
        reasons.append(schema)
    suites: dict[str, dict[str, Any]] = {}
    if comparisons.value is not None:
        if comparisons.value.get("artifact_sha256") != artifact.sha256:
            reasons.append(
                _reason(
                    "conformant",
                    "artifact_pin_mismatch",
                    comparisons.name,
                    "comparison index artifact_sha256 does not match the artifact",
                )
            )
        producer = comparisons.value.get("producer")
        if not isinstance(producer, dict) or producer.get("mode") != "computed":
            reasons.append(
                _reason(
                    "conformant",
                    "producer_missing",
                    comparisons.name,
                    "comparison index is not marked mode=computed",
                )
            )
        raw = comparisons.value.get("comparisons")
        if isinstance(raw, dict):
            suites = {
                str(key): value for key, value in raw.items() if isinstance(value, dict)
            }
        else:
            reasons.append(
                _reason(
                    "conformant",
                    "producer_missing",
                    comparisons.name,
                    "comparison index has no comparisons object",
                )
            )

    declared_by_node: dict[str, dict[str, dict[str, Any]]] = {
        node_id: {} for node_id in node_ids
    }
    for declaration in applicable:
        declared_by_node[str(declaration["node"])][str(declaration["suite"])] = (
            declaration
        )
    producer_suites_by_node: dict[str, set[str]] = {
        node_id: set() for node_id in node_ids
    }
    for suite, row in suites.items():
        applicable_nodes = row.get("applicable_nodes")
        required_by_node = row.get("required_dimensions")
        if (
            not isinstance(applicable_nodes, list)
            or not applicable_nodes
            or not all(_is_string(item) for item in applicable_nodes)
            or len(set(applicable_nodes)) != len(applicable_nodes)
            or not isinstance(required_by_node, dict)
            or set(required_by_node) != set(applicable_nodes)
        ):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_applicability_invalid",
                    comparisons.name,
                    (
                        f"suite {suite!r} must carry unique applicable_nodes "
                        "and one required_dimensions row for each"
                    ),
                )
            )
            continue
        dimensions_valid = True
        for covered_node, dimensions in required_by_node.items():
            if (
                not isinstance(dimensions, list)
                or not dimensions
                or not all(_is_string(item) for item in dimensions)
                or len(set(dimensions)) != len(dimensions)
            ):
                dimensions_valid = False
                reasons.append(
                    _reason(
                        "conformant",
                        "comparison_applicability_invalid",
                        comparisons.name,
                        (
                            f"suite {suite!r} has invalid required_dimensions "
                            f"for {covered_node!r}"
                        ),
                    )
                )
        for node_id in node_ids:
            if node_id not in applicable_nodes:
                continue
            producer_suites_by_node[node_id].add(suite)
            declared = declared_by_node[node_id].get(suite)
            declared_dimensions = (
                declared.get("required_dimensions") if declared else None
            )
            produced_dimensions = required_by_node.get(node_id)
            if (
                not dimensions_valid
                or not isinstance(declared_dimensions, list)
                or set(declared_dimensions) != set(produced_dimensions or [])
                or len(declared_dimensions) != len(produced_dimensions or [])
            ):
                reasons.append(
                    _reason(
                        "conformant",
                        "comparison_declaration_mismatch",
                        comparisons.name,
                        (
                            f"subgraph node {node_id!r} suite {suite!r} required "
                            "dimensions disagree between the node index and "
                            "comparison producer"
                        ),
                    )
                )
    for node_id in node_ids:
        if producer_suites_by_node[node_id] != set(declared_by_node[node_id]):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_declaration_mismatch",
                    comparisons.name,
                    (
                        f"subgraph node {node_id!r} applicable suite set "
                        "disagrees between the node index and comparison producer"
                    ),
                )
            )

    evidence_rows: list[dict[str, Any]] = []
    relevant_suites = list(
        dict.fromkeys(str(declaration["suite"]) for declaration in applicable)
    )
    for suite in relevant_suites:
        row = suites.get(suite)
        if row is None:
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_missing",
                    comparisons.name,
                    f"applicable suite {suite!r} has no computed comparison row",
                )
            )
            continue
        report = row.get("report")
        report_path: Path | None = None
        report_hash: str | None = None
        report_value: dict[str, Any] | None = None
        if isinstance(report, dict):
            report_path = _producer_path(root, report.get("path"))
        if report_path is not None and report_path.suffix.lower() == ".json":
            loaded_report = _load(root, report_path, f"comparison_report:{suite}")
            report_hash = loaded_report.sha256
            report_value = loaded_report.value
        if (
            report_path is None
            or report_hash is None
            or not isinstance(report, dict)
            or report.get("sha256") != report_hash
        ):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_report_missing",
                    comparisons.name,
                    f"suite {suite!r} report is absent or not hash-bound",
                )
            )
        else:
            evidence_rows.append(
                {
                    "suite": suite,
                    "report": _path_label(report_path, root),
                    "sha256": report_hash,
                }
            )
            summary = report_value.get("summary") if report_value else None
            report_errors: list[str] = []
            if report_value is None:
                report_errors.append("report is not valid JSON")
            elif report_value.get("schema_version") != REPORT_SCHEMA:
                report_errors.append(f"schema_version is not {REPORT_SCHEMA}")
            if report_value is not None and report_value.get("suite") != suite:
                report_errors.append("suite identity does not match")
            case_count = (
                report_value.get("case_count") if report_value is not None else None
            )
            if not _is_int(case_count, minimum=1):
                report_errors.append("case_count is invalid")
            if not isinstance(summary, dict):
                report_errors.append("summary is missing")
                summary = {}
            raw_counts: dict[str, int] = {}
            for field in (
                "comparison_count",
                "match_count",
                "mismatch_count",
                "error_count",
            ):
                observed = summary.get(field)
                if not _is_int(
                    observed,
                    minimum=1 if field == "comparison_count" else 0,
                ):
                    report_errors.append(f"summary.{field} is invalid")
                else:
                    raw_counts[field] = observed
            if all(
                field in raw_counts
                for field in ("comparison_count", "match_count", "mismatch_count")
            ) and (
                raw_counts["match_count"] + raw_counts["mismatch_count"]
                != raw_counts["comparison_count"]
            ):
                report_errors.append("summary counts do not conserve")

            mismatch_count = raw_counts.get("mismatch_count")
            dispositioned = summary.get("dispositioned")
            if dispositioned is None and mismatch_count is not None:
                derived_unexplained = mismatch_count
                derived_axiom = 0
            elif isinstance(dispositioned, dict):
                derived_unexplained = dispositioned.get("unexplained_count")
                counts = dispositioned.get("counts")
                derived_axiom = (
                    counts.get("axiom_encoding_gap")
                    if isinstance(counts, dict)
                    else None
                )
                if not _is_int(derived_unexplained):
                    report_errors.append(
                        "summary.dispositioned.unexplained_count is invalid"
                    )
                if not _is_int(derived_axiom):
                    report_errors.append(
                        "summary.dispositioned.counts.axiom_encoding_gap is invalid"
                    )
                counts_valid = isinstance(counts, dict) and all(
                    _is_string(category) and _is_int(count)
                    for category, count in counts.items()
                )
                explicit_unexplained = (
                    counts.get("unexplained", 0) if isinstance(counts, dict) else None
                )
                dispositioned_other = (
                    sum(
                        count
                        for category, count in counts.items()
                        if category != "unexplained"
                    )
                    if counts_valid
                    else None
                )
                if (
                    not counts_valid
                    or not _is_int(explicit_unexplained)
                    or not _is_int(derived_unexplained)
                    or mismatch_count is None
                    or explicit_unexplained > derived_unexplained
                    or dispositioned_other + derived_unexplained != mismatch_count
                ):
                    report_errors.append(
                        "summary.dispositioned counts do not reconcile mismatches"
                    )
                if mismatch_count and dispositioned.get("dispositions_file") is None:
                    report_errors.append(
                        "summary.dispositioned.dispositions_file is missing"
                    )
            else:
                derived_unexplained = None
                derived_axiom = None
                report_errors.append("summary.dispositioned is invalid")

            expected_counts = {
                "case_count": case_count,
                "comparison_count": raw_counts.get("comparison_count"),
                "error_count": raw_counts.get("error_count"),
                "unexplained_count": derived_unexplained,
                "axiom_attributed_count": derived_axiom,
            }
            for field, expected in expected_counts.items():
                if not _is_int(expected) or row.get(field) != expected:
                    report_errors.append(f"computed {field} does not match the report")
            if report_errors:
                reasons.append(
                    _reason(
                        "conformant",
                        "comparison_report_invalid",
                        comparisons.name,
                        f"suite {suite!r}: " + "; ".join(report_errors),
                    )
                )
        if row.get("committed") is not True:
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_uncommitted",
                    comparisons.name,
                    f"suite {suite!r} is not a committed comparison",
                )
            )
        if not _is_int(row.get("comparison_count"), minimum=1):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_zero_cases",
                    comparisons.name,
                    f"suite {suite!r} has no positive comparison count",
                )
            )
        if not _is_int(row.get("case_count"), minimum=1):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_zero_cases",
                    comparisons.name,
                    f"suite {suite!r} has no positive case count",
                )
            )
        if row.get("binding") != "bound":
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_unbound",
                    comparisons.name,
                    f"suite {suite!r} evidence is not bound",
                )
            )
        if row.get("reconciliation") != "full":
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_not_fully_reconciled",
                    comparisons.name,
                    f"suite {suite!r} evidence is not fully reconciled",
                )
            )
        errors = row.get("error_count")
        if not _is_int(errors):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_result_invalid",
                    comparisons.name,
                    f"suite {suite!r} lacks error_count",
                )
            )
        elif errors:
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_errors",
                    comparisons.name,
                    f"suite {suite!r} has {errors} comparison error(s)",
                )
            )
        unexplained = row.get("unexplained_count")
        if not _is_int(unexplained):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_result_invalid",
                    comparisons.name,
                    f"suite {suite!r} lacks unexplained_count",
                )
            )
        elif unexplained:
            reasons.append(
                _reason(
                    "conformant",
                    "unexplained_mismatch",
                    comparisons.name,
                    f"suite {suite!r} has {unexplained} unexplained mismatch(es)",
                )
            )
        axiom = row.get("axiom_attributed_count")
        if not _is_int(axiom):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_result_invalid",
                    comparisons.name,
                    f"suite {suite!r} lacks axiom_attributed_count",
                )
            )
        elif axiom:
            reasons.append(
                _reason(
                    "conformant",
                    "axiom_attributed_mismatch",
                    comparisons.name,
                    f"suite {suite!r} has {axiom} Axiom-attributed mismatch(es)",
                )
            )
        if pins is not None and row.get("pinned") != pins:
            reasons.append(
                _reason(
                    "conformant",
                    "pin_mismatch",
                    comparisons.name,
                    f"suite {suite!r} is not pinned to this harness vintage",
                )
            )
    evidence = {
        "index": _path_label(comparisons.path, root),
        "sha256": comparisons.sha256,
        "reports": evidence_rows,
    }
    return {"holds": not reasons, "evidence": evidence}, reasons, suites


def _exercised(
    census: Loaded,
    applicable: list[dict[str, Any]],
    comparison_rows: dict[str, dict[str, Any]],
    *,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    if not applicable:
        reasons.append(
            _reason(
                "exercised",
                "producer_missing",
                "node_index",
                "node declaration has no applicable suites or required dimensions",
            )
        )
    schema = _schema_reason("exercised", census, CENSUS_SCHEMA)
    if schema:
        reasons.append(schema)
    suites: dict[str, dict[str, Any]] = {}
    if census.value is not None:
        raw = census.value.get("suites")
        if isinstance(raw, dict):
            suites = {
                str(key): value for key, value in raw.items() if isinstance(value, dict)
            }
        else:
            reasons.append(
                _reason(
                    "exercised",
                    "producer_missing",
                    census.name,
                    "exercise census has no suites object",
                )
            )
    evidence_rows: list[dict[str, Any]] = []
    required_by_suite: dict[str, list[str]] = {}
    for declaration in applicable:
        suite = str(declaration["suite"])
        required = declaration.get("required_dimensions")
        if (
            not isinstance(required, list)
            or not required
            or not all(_is_string(item) for item in required)
        ):
            reasons.append(
                _reason(
                    "exercised",
                    "producer_missing",
                    "node_index",
                    f"suite {suite!r} has no behavior-changing required_dimensions",
                )
            )
            continue
        if len(set(required)) != len(required):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_dimensions_invalid",
                    "node_index",
                    f"suite {suite!r} repeats a required dimension",
                )
            )
            continue
        combined = required_by_suite.setdefault(suite, [])
        combined.extend(
            dimension for dimension in required if dimension not in combined
        )

    for suite, required in required_by_suite.items():
        row = suites.get(suite)
        if row is None:
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_suite_missing",
                    census.name,
                    f"exercise census has no row for suite {suite!r}",
                )
            )
            continue
        comparison = comparison_rows.get(suite, {})
        report = comparison.get("report")
        expected_path = report.get("path") if isinstance(report, dict) else None
        expected_sha = report.get("sha256") if isinstance(report, dict) else None
        if (
            row.get("report") != expected_path
            or row.get("report_sha256") != expected_sha
        ):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_report_identity_mismatch",
                    census.name,
                    f"suite {suite!r} census row names a different report",
                )
            )
        if row.get("contested_reports") not in (None, []):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_contested_reports",
                    census.name,
                    (
                        f"suite {suite!r} is claimed by multiple reports; "
                        "suite-keyed evidence ownership is ambiguous"
                    ),
                )
            )
        if row.get("binding") != "bound":
            reasons.append(
                _reason(
                    "exercised",
                    "comparison_unbound",
                    census.name,
                    f"suite {suite!r} census evidence is not bound",
                )
            )
        if row.get("binding_defects") != []:
            reasons.append(
                _reason(
                    "exercised",
                    "comparison_unbound",
                    census.name,
                    f"suite {suite!r} census has binding defects",
                )
            )
        if row.get("reconciliation") not in {"cardinality", "full"}:
            reasons.append(
                _reason(
                    "exercised",
                    "comparison_not_fully_reconciled",
                    census.name,
                    (f"suite {suite!r} census evidence is not cardinality-reconciled"),
                )
            )
        if row.get("bridge_declared") is not True:
            reasons.append(
                _reason(
                    "exercised",
                    "bridge_undeclared",
                    census.name,
                    (
                        f"suite {suite!r} has no bridge manifest; "
                        "absence cannot establish that a dimension is unbridged"
                    ),
                )
            )
        if row.get("bridge_audited") is not True:
            reasons.append(
                _reason(
                    "exercised",
                    "bridge_unaudited",
                    census.name,
                    (
                        f"suite {suite!r} has no clean bridge audit; "
                        "absence cannot establish that a dimension is unbridged"
                    ),
                )
            )
        cases_scanned = row.get("cases_scanned")
        if not _is_int(cases_scanned, minimum=1):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_evidence_missing",
                    census.name,
                    f"suite {suite!r} has no scanned cases",
                )
            )
        comparison_case_count = comparison.get("case_count")
        if (
            not _is_int(comparison_case_count, minimum=1)
            or cases_scanned != comparison_case_count
        ):
            reasons.append(
                _reason(
                    "exercised",
                    "evidence_incomplete",
                    census.name,
                    (
                        f"suite {suite!r} census scanned {cases_scanned!r} "
                        f"case(s), but the comparison report binds "
                        f"{comparison_case_count!r}"
                    ),
                )
            )
        fields = row.get("evidence_fields")
        if not isinstance(fields, dict):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_evidence_missing",
                    census.name,
                    f"suite {suite!r} has no evidence_fields object",
                )
            )
            fields = {}
        bridged = row.get("bridged_through")
        if not isinstance(bridged, dict):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_evidence_missing",
                    census.name,
                    f"suite {suite!r} has malformed bridged_through evidence",
                )
            )
            bridged = {}
        for dimension in required:
            if dimension in bridged:
                reasons.append(
                    _reason(
                        "exercised",
                        "dimension_bridged",
                        census.name,
                        (
                            f"suite {suite!r} dimension {dimension!r} is "
                            "bridged-through and contributes zero fidelity"
                        ),
                    )
                )
                continue
            field = fields.get(dimension)
            if not isinstance(field, dict):
                reasons.append(
                    _reason(
                        "exercised",
                        "dimension_missing",
                        census.name,
                        f"suite {suite!r} does not census dimension {dimension!r}",
                    )
                )
                continue
            if field.get("state") == "constant":
                reasons.append(
                    _reason(
                        "exercised",
                        "dimension_constant",
                        census.name,
                        (
                            f"suite {suite!r} dimension {dimension!r} is "
                            "constant and contributes zero fidelity"
                        ),
                    )
                )
                continue
            distinct = field.get("distinct")
            if (
                field.get("state") != "varied"
                or not _is_int(distinct, minimum=2)
                or not _is_int(cases_scanned, minimum=1)
                or distinct > cases_scanned
            ):
                reasons.append(
                    _reason(
                        "exercised",
                        "exercise_dimension_invalid",
                        census.name,
                        (
                            f"suite {suite!r} dimension {dimension!r} must be "
                            "state=varied with at least two distinct values"
                        ),
                    )
                )
        evidence_rows.append({"suite": suite, "required_dimensions": required})
    evidence = {
        "census": _path_label(census.path, root),
        "sha256": census.sha256,
        "suites": evidence_rows,
    }
    return {"holds": not reasons, "evidence": evidence}, reasons


def _executable(
    executable: Loaded,
    node_id: str,
    artifact: Loaded,
    pins: dict[str, Any] | None,
    *,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Consume a node adapter over the parked program-receipt validator.

    ``axiom_oracles.executable_receipt.v1`` remains the rich program receipt
    owned by the executable producer.  The node index is a separate computed
    adapter: it must invoke that receipt's upstream validator, then derive node
    coverage from the receipt manifest's hash-bound golden-output bindings.
    """

    reasons: list[dict[str, Any]] = []
    schema = _schema_reason("executable", executable, EXECUTABLE_SCHEMA)
    if schema:
        reasons.append(schema)
    row: dict[str, Any] | None = None
    expected_validator_sha256: str | None = None
    if executable.value is not None:
        if executable.value.get("artifact_sha256") != artifact.sha256:
            reasons.append(
                _reason(
                    "executable",
                    "artifact_pin_mismatch",
                    executable.name,
                    "executable index artifact_sha256 does not match the artifact",
                )
            )
        producer = executable.value.get("producer")
        if (
            not isinstance(producer, dict)
            or producer.get("mode") != "computed"
            or producer.get("adapter")
            != "axiom_oracles.node_executable.from_validated_receipt.v1"
            or producer.get("validator")
            != "axiom_oracles.executable_receipt.validate_executable_receipt"
            or not isinstance(producer.get("validator_sha256"), str)
            or not _SHA256_RE.fullmatch(producer["validator_sha256"])
        ):
            reasons.append(
                _reason(
                    "executable",
                    "producer_missing",
                    executable.name,
                    (
                        "executable index was not computed by the required "
                        "upstream receipt validator adapter"
                    ),
                )
            )
        else:
            expected_validator_sha256 = producer["validator_sha256"]
        nodes = executable.value.get("nodes")
        if isinstance(nodes, dict) and isinstance(nodes.get(node_id), dict):
            row = nodes[node_id]
        else:
            reasons.append(
                _reason(
                    "executable",
                    "producer_missing",
                    executable.name,
                    f"no computed executable result exists for {node_id!r}",
                )
            )
    linked_evidence: dict[str, Any] = {}
    if row is not None:
        if row.get("validated") is not True:
            reasons.append(
                _reason(
                    "executable",
                    "executable_unvalidated",
                    executable.name,
                    "executable producer did not validate the receipt",
                )
            )
        program = row.get("program")
        covered_nodes = row.get("covered_nodes")
        clean_covered_nodes: list[str] = []
        if (
            not _is_string(program)
            or not isinstance(covered_nodes, list)
            or not covered_nodes
            or not all(_is_string(item) for item in covered_nodes)
            or len(set(covered_nodes)) != len(covered_nodes)
            or node_id not in covered_nodes
        ):
            reasons.append(
                _reason(
                    "executable",
                    "executable_coverage_invalid",
                    executable.name,
                    "validated program receipt does not compute coverage for this node",
                )
            )
        else:
            clean_covered_nodes = list(covered_nodes)

        manifest = row.get("manifest")
        receipt = row.get("receipt")
        manifest_path: Path | None = None
        receipt_path: Path | None = None
        manifest_hash: str | None = None
        receipt_hash: str | None = None
        manifest_value: dict[str, Any] | None = None
        receipt_value: dict[str, Any] | None = None
        if isinstance(manifest, dict):
            manifest_path = _producer_path(root, manifest.get("path"))
        if manifest_path is not None and manifest_path.suffix.lower() == ".json":
            loaded_manifest = _load(root, manifest_path, "executable_manifest")
            manifest_hash = loaded_manifest.sha256
            manifest_value = loaded_manifest.value
        if isinstance(receipt, dict):
            receipt_path = _producer_path(root, receipt.get("path"))
        if receipt_path is not None and receipt_path.suffix.lower() == ".json":
            loaded_receipt = _load(root, receipt_path, "executable_receipt")
            receipt_hash = loaded_receipt.sha256
            receipt_value = loaded_receipt.value
        if (
            manifest_path is None
            or manifest_hash is None
            or not isinstance(manifest, dict)
            or manifest.get("sha256") != manifest_hash
            or manifest_value is None
            or receipt_path is None
            or receipt_hash is None
            or not isinstance(receipt, dict)
            or receipt.get("sha256") != receipt_hash
            or receipt_value is None
        ):
            reasons.append(
                _reason(
                    "executable",
                    "executable_receipt_missing",
                    executable.name,
                    (
                        "executable manifest/receipt is absent, malformed, "
                        "outside the repository, or not hash-bound"
                    ),
                )
            )
        else:
            linked_evidence = {
                "manifest": _path_label(manifest_path, root),
                "manifest_sha256": manifest_hash,
                "receipt": _path_label(receipt_path, root),
                "receipt_sha256": receipt_hash,
                "covered_nodes": clean_covered_nodes,
            }
            manifest_engine = manifest_value.get("engine")
            manifest_golden = manifest_value.get("golden")
            manifest_workflow = manifest_value.get("workflow")
            trust_root_paths = [
                manifest_engine.get("release_manifest")
                if isinstance(manifest_engine, dict)
                else None,
                manifest_golden.get("input_path")
                if isinstance(manifest_golden, dict)
                else None,
                manifest_golden.get("outputs_path")
                if isinstance(manifest_golden, dict)
                else None,
                manifest_workflow.get("allowlist")
                if isinstance(manifest_workflow, dict)
                else None,
            ]
            declared_trust_roots = row.get("trust_roots")
            if (
                not all(_is_string(path) for path in trust_root_paths)
                or len(set(trust_root_paths)) != len(trust_root_paths)
                or not isinstance(declared_trust_roots, dict)
                or set(declared_trust_roots) != set(trust_root_paths)
                or not all(
                    isinstance(digest, str) and _SHA256_RE.fullmatch(digest)
                    for digest in declared_trust_roots.values()
                )
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "executable_receipt_invalid",
                        executable.name,
                        (
                            "executable row does not hash-bind every transitive "
                            "receipt trust root"
                        ),
                    )
                )
            else:
                linked_roots: list[dict[str, str]] = []
                for declared_path in trust_root_paths:
                    resolved = _producer_path(root, declared_path)
                    loaded_root = (
                        _load(root, resolved, f"executable_trust_root:{declared_path}")
                        if resolved is not None and resolved.suffix.lower() == ".json"
                        else None
                    )
                    if (
                        loaded_root is None
                        or loaded_root.sha256 is None
                        or declared_trust_roots[declared_path] != loaded_root.sha256
                    ):
                        reasons.append(
                            _reason(
                                "executable",
                                "executable_receipt_invalid",
                                executable.name,
                                (
                                    f"transitive receipt trust root "
                                    f"{declared_path!r} is missing or hash-mismatched"
                                ),
                            )
                        )
                    else:
                        linked_roots.append(
                            {
                                "path": _path_label(resolved, root),
                                "sha256": loaded_root.sha256,
                            }
                        )
                linked_evidence["trust_roots"] = linked_roots
            try:
                validator_module = importlib.import_module(
                    "axiom_oracles.executable_receipt"
                )
                validator = getattr(
                    validator_module,
                    "validate_executable_receipt",
                )
            except (ImportError, AttributeError) as exc:
                reasons.append(
                    _reason(
                        "executable",
                        "producer_missing",
                        executable.name,
                        f"upstream executable receipt validator is unavailable: {exc}",
                    )
                )
            else:
                module_file = getattr(validator_module, "__file__", None)
                try:
                    validator_path = Path(module_file).resolve()
                    validator_path.relative_to(root)
                except (TypeError, ValueError):
                    reasons.append(
                        _reason(
                            "executable",
                            "producer_missing",
                            executable.name,
                            (
                                "upstream executable receipt validator is not "
                                "loaded from the governed repository checkout"
                            ),
                        )
                    )
                    validator_path = None
                if validator_path is not None:
                    try:
                        validator_sha256 = _sha256(validator_path.read_bytes())
                    except OSError as exc:
                        reasons.append(
                            _reason(
                                "executable",
                                "producer_missing",
                                executable.name,
                                f"upstream validator bytes are unreadable: {exc}",
                            )
                        )
                        validator_path = None
                    else:
                        linked_evidence["validator_path"] = _path_label(
                            validator_path, root
                        )
                        linked_evidence["validator_sha256"] = validator_sha256
                        if validator_sha256 != expected_validator_sha256:
                            reasons.append(
                                _reason(
                                    "executable",
                                    "executable_receipt_invalid",
                                    executable.name,
                                    (
                                        "loaded validator bytes do not match the "
                                        "hash-bound executable producer"
                                    ),
                                )
                            )
                try:
                    validation = (
                        validator(
                            receipt_path,
                            repo_root=root,
                            manifest_path=manifest_path,
                        )
                        if validator_path is not None
                        else None
                    )
                except Exception as exc:
                    reasons.append(
                        _reason(
                            "executable",
                            "executable_receipt_invalid",
                            executable.name,
                            (
                                "upstream executable receipt validator raised "
                                f"{type(exc).__name__}: {exc}"
                            ),
                        )
                    )
                else:
                    validation_evidence = getattr(validation, "evidence", None)
                    validation_engine = (
                        validation_evidence.get("engine")
                        if isinstance(validation_evidence, dict)
                        else None
                    )
                    validation_artifact = (
                        validation_evidence.get("artifact")
                        if isinstance(validation_evidence, dict)
                        else None
                    )
                    if validation is None:
                        pass
                    elif getattr(validation, "valid", None) is not True:
                        failures = getattr(validation, "failures", ())
                        detail = "; ".join(str(item) for item in failures)
                        reasons.append(
                            _reason(
                                "executable",
                                "executable_receipt_invalid",
                                executable.name,
                                (
                                    "upstream executable receipt validator "
                                    f"rejected the receipt: {detail or 'no detail'}"
                                ),
                            )
                        )
                    elif (
                        getattr(validation, "receipt_sha256", None) != receipt_hash
                        or not isinstance(validation_evidence, dict)
                        or validation_evidence.get("program") != program
                        or not isinstance(validation_engine, dict)
                        or pins is None
                        or validation_engine.get("release") != pins.get("engine")
                        or not isinstance(validation_artifact, dict)
                        or validation_artifact.get("sha256") != artifact.sha256
                    ):
                        reasons.append(
                            _reason(
                                "executable",
                                "executable_receipt_invalid",
                                executable.name,
                                (
                                    "upstream validator evidence does not bind "
                                    "this program, receipt, engine, and artifact"
                                ),
                            )
                        )
                    else:
                        linked_evidence["validator"] = (
                            "axiom_oracles.executable_receipt."
                            "validate_executable_receipt"
                        )
            manifest_artifact = manifest_value.get("artifact")
            if (
                manifest_value.get("schema") != "axiom_oracles.executable_manifest.v1"
                or manifest_value.get("program") != program
                or not isinstance(manifest_artifact, dict)
                or manifest_artifact.get("sha256") != artifact.sha256
                or not isinstance(manifest_engine, dict)
                or pins is None
                or manifest_engine.get("release") != pins.get("engine")
                or not isinstance(manifest_golden, dict)
                or manifest_value.get("receipt_path") != receipt.get("path")
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "executable_receipt_invalid",
                        executable.name,
                        "executable manifest identity or release pins are invalid",
                    )
                )

            output_bindings_path = (
                _producer_path(root, manifest_golden.get("outputs_path"))
                if isinstance(manifest_golden, dict)
                else None
            )
            output_bindings: dict[str, Any] | None = None
            output_bindings_hash: str | None = None
            if (
                output_bindings_path is not None
                and output_bindings_path.suffix.lower() == ".json"
            ):
                loaded_bindings = _load(
                    root,
                    output_bindings_path,
                    "executable_output_bindings",
                )
                output_bindings = loaded_bindings.value
                output_bindings_hash = loaded_bindings.sha256
            bindings = (
                output_bindings.get("bindings")
                if isinstance(output_bindings, dict)
                else None
            )
            expected = (
                output_bindings.get("expected")
                if isinstance(output_bindings, dict)
                else None
            )
            derived_nodes = (
                sorted(set(bindings.values()))
                if isinstance(bindings, dict)
                and bindings
                and all(_is_string(item) for item in bindings.values())
                else None
            )
            if (
                output_bindings_hash is None
                or not isinstance(manifest_golden, dict)
                or manifest_golden.get("outputs_sha256") != output_bindings_hash
                or not isinstance(expected, dict)
                or not isinstance(bindings, dict)
                or set(expected) != set(bindings)
                or derived_nodes is None
                or sorted(clean_covered_nodes) != derived_nodes
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "executable_coverage_invalid",
                        executable.name,
                        (
                            "node coverage does not equal the hash-bound "
                            "golden-output legal-id bindings"
                        ),
                    )
                )
            else:
                linked_evidence["output_bindings"] = _path_label(
                    output_bindings_path, root
                )
                linked_evidence["output_bindings_sha256"] = output_bindings_hash

            receipt_engine = receipt_value.get("engine")
            receipt_artifact = receipt_value.get("artifact")
            receipt_golden = receipt_value.get("golden")
            workflow = receipt_value.get("workflow")
            if (
                receipt_value.get("schema") != RECEIPT_SCHEMA
                or receipt_value.get("program") != program
                or not isinstance(receipt_engine, dict)
                or pins is None
                or receipt_engine.get("release") != pins.get("engine")
                or not _is_string(receipt_engine.get("version"))
                or not isinstance(receipt_artifact, dict)
                or receipt_artifact.get("sha256") != artifact.sha256
                or not isinstance(receipt_golden, dict)
                or not isinstance(receipt_value.get("commands"), list)
                or not receipt_value["commands"]
                or not _is_string(receipt_value.get("timestamp"))
                or not isinstance(workflow, dict)
                or not _is_string(workflow.get("repository"))
                or not _is_string(workflow.get("path"))
                or not _is_string(workflow.get("event"))
                or not _is_string(workflow.get("ref"))
                or not (
                    (type(workflow.get("run_id")) is int and workflow["run_id"] > 0)
                    or (
                        isinstance(workflow.get("run_id"), str)
                        and workflow["run_id"].isdigit()
                        and int(workflow["run_id"]) > 0
                    )
                )
                or not (
                    type(workflow.get("run_attempt")) is int
                    and workflow["run_attempt"] > 0
                )
                or not isinstance(workflow.get("sha"), str)
                or not _COMMIT_RE.fullmatch(workflow["sha"])
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "executable_receipt_invalid",
                        executable.name,
                        (
                            "receipt does not match the parked v1 program "
                            "receipt identity and provenance interface"
                        ),
                    )
                )
            elif (
                not isinstance(bindings, dict)
                or not isinstance(receipt_golden.get("outputs"), dict)
                or set(receipt_golden["outputs"]) != set(bindings)
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "executable_coverage_invalid",
                        executable.name,
                        "receipt outputs do not match the bound output names",
                    )
                )
        expected_pins = (
            {"engine": pins.get("engine"), "artifact": pins.get("artifact")}
            if pins
            else None
        )
        if row.get("pinned") != expected_pins:
            reasons.append(
                _reason(
                    "executable",
                    "pin_mismatch",
                    executable.name,
                    "executable result is not pinned to this harness vintage",
                )
            )
    evidence = {
        "index": _path_label(executable.path, root),
        "index_sha256": executable.sha256,
        **linked_evidence,
    }
    return {"holds": not reasons, "evidence": evidence}, reasons


def evaluate_node(
    node_id: str,
    *,
    root: Path,
    artifact: Loaded,
    node_index: Loaded,
    closure: Loaded,
    comparisons: Loaded,
    census: Loaded,
    executable: Loaded,
    run_manifest: Loaded,
    governance: Loaded,
) -> dict[str, Any]:
    """Evaluate one requested node without ever converting absence to success."""

    subgraph, nodes, graph_reasons = _artifact_nodes(artifact, node_id)
    declarations, declaration_reasons = _node_declarations(
        node_index, artifact, subgraph
    )
    declaration = declarations.get(node_id)
    run, harness_reasons = _run_context(
        run_manifest,
        governance,
        artifact,
        {
            "compiled_artifact": artifact,
            "node_index": node_index,
            "closure_summary": closure,
            "node_comparisons": comparisons,
            "exercise_census": census,
            "node_executable": executable,
        },
    )
    pins = run.get("pinned") if run else None

    provision, provision_reasons = _provision_rooted(
        artifact,
        subgraph,
        nodes,
        [*graph_reasons, *declaration_reasons],
        root=root,
    )
    closed, closed_reasons = _closed(
        closure,
        declarations,
        subgraph,
        pins,
        root=root,
    )
    applicable, applicability_reasons = _comparison_declarations(
        declarations,
        subgraph,
    )
    conformant, conformant_reasons, comparison_rows = _conformant(
        comparisons,
        subgraph,
        applicable,
        applicability_reasons,
        artifact,
        pins,
        root=root,
    )
    exercised, exercised_reasons = _exercised(
        census,
        applicable,
        comparison_rows,
        root=root,
    )
    executable_result, executable_reasons = _executable(
        executable,
        node_id,
        artifact,
        pins,
        root=root,
    )
    criteria = {
        "provision_rooted": provision,
        "conformant": conformant,
        "exercised": exercised,
        "closed": closed,
        "executable": executable_result,
    }
    reasons = [
        *provision_reasons,
        *conformant_reasons,
        *exercised_reasons,
        *closed_reasons,
        *executable_reasons,
        *harness_reasons,
    ]

    entry: dict[str, Any] | None = None
    if not reasons and all(criteria[name]["holds"] for name in CRITERIA):
        assert declaration is not None
        assert run is not None
        root_metadata = nodes[node_id]
        for field in ("label", "provision", "corpus_citation_path"):
            if not _is_string(declaration.get(field)):
                reasons.append(
                    _reason(
                        "provision_rooted",
                        "node_declaration_invalid",
                        node_index.name,
                        f"node declaration field {field!r} is missing",
                    )
                )
        if declaration.get("corpus_citation_path") != root_metadata.get(
            "corpus_citation_path"
        ):
            reasons.append(
                _reason(
                    "provision_rooted",
                    "node_declaration_invalid",
                    node_index.name,
                    "declared corpus citation does not match artifact provenance",
                )
            )
        if not reasons:
            harness = run["harness"]
            entry = {
                "node": node_id,
                "label": declaration["label"],
                "provision": declaration["provision"],
                "corpus_citation_path": declaration["corpus_citation_path"],
                "certified_at": run["certified_at"],
                "harness": {
                    "run": f"{harness['ci_run_id']}@{harness['workflow_sha']}",
                    "certify_check": harness["certify_check"],
                },
                "pinned": {
                    "rulespec_us": pins["rulespec_us"],
                    "corpus": pins["corpus"],
                    "engine": pins["engine"],
                    "artifact": pins["artifact"],
                },
                "criteria": {name: criteria[name] for name in CRITERIA},
            }
    if any(reason["criterion"] == "provision_rooted" for reason in reasons):
        criteria["provision_rooted"]["holds"] = False
    return {
        "node": node_id,
        "certified": entry is not None,
        "entry": entry,
        "criteria": criteria,
        "reasons": reasons,
    }


def _render_ledger(
    evaluations: list[dict[str, Any]],
    run: dict[str, Any] | None,
) -> str:
    certified = sorted(
        (row["entry"] for row in evaluations if row["entry"] is not None),
        key=lambda row: row["node"],
    )
    as_of: str
    if run is not None and _is_string(run.get("certified_at")):
        as_of = str(run["certified_at"]).split("T", 1)[0]
    else:
        as_of = "unverified"
    payload = {
        "schema": LEDGER_SCHEMA,
        "generated": True,
        "as_of": as_of,
        "nodes": certified,
    }
    rendered = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return HEADER + "\n" + rendered + "\n" + ENTRY_SHAPE_COMMENT


def _result_document(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "certified": [row["node"] for row in evaluations if row["certified"]],
        "rejected": [
            {
                "node": row["node"],
                "criteria": row["criteria"],
                "reasons": row["reasons"],
            }
            for row in evaluations
            if not row["certified"]
        ],
    }


def _drifted(path: Path, rendered: str) -> bool:
    """Compare exact bytes, including newline convention and encoding."""

    try:
        return path.read_bytes() != rendered.encode("utf-8")
    except OSError:
        return True


def _existing_node_ids(path: Path) -> set[str]:
    """Return nodes already in the generated projection for recomputation."""

    try:
        payload = yaml.load(path.read_bytes(), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError):
        return set()
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return set()
    return {
        str(row["node"])
        for row in payload["nodes"]
        if isinstance(row, dict) and _is_string(row.get("node"))
    }


def _atomic_write_documents(documents: dict[Path, str]) -> None:
    """Stage every document before replacing any target."""

    staged: dict[Path, Path] = {}
    try:
        for target, rendered in documents.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )
            temporary = Path(temporary_name)
            staged[target] = temporary
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(rendered.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        for target, temporary in staged.items():
            temporary.replace(target)
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _declared_evidence_paths(
    root: Path,
    comparisons: Loaded,
    executable: Loaded,
) -> set[Path]:
    paths: set[Path] = set()
    if comparisons.value is not None:
        rows = comparisons.value.get("comparisons")
        if isinstance(rows, dict):
            for row in rows.values():
                report = row.get("report") if isinstance(row, dict) else None
                resolved = (
                    _producer_path(root, report.get("path"))
                    if isinstance(report, dict)
                    else None
                )
                if resolved is not None:
                    paths.add(resolved)
    if executable.value is not None:
        producer = executable.value.get("producer")
        if (
            isinstance(producer, dict)
            and producer.get("validator")
            == "axiom_oracles.executable_receipt.validate_executable_receipt"
        ):
            try:
                validator_module = importlib.import_module(
                    "axiom_oracles.executable_receipt"
                )
                validator_source = Path(validator_module.__file__).resolve()
            except (AttributeError, ImportError, TypeError):
                pass
            else:
                paths.add(validator_source)
        rows = executable.value.get("nodes")
        if isinstance(rows, dict):
            for row in rows.values():
                if not isinstance(row, dict):
                    continue
                for field in ("manifest", "receipt"):
                    reference = row.get(field)
                    resolved = (
                        _producer_path(root, reference.get("path"))
                        if isinstance(reference, dict)
                        else None
                    )
                    if resolved is not None:
                        paths.add(resolved)
                        if field == "manifest":
                            loaded_manifest = _load(
                                root,
                                resolved,
                                "executable_manifest",
                            )
                            engine = (
                                loaded_manifest.value.get("engine")
                                if loaded_manifest.value is not None
                                else None
                            )
                            golden = (
                                loaded_manifest.value.get("golden")
                                if loaded_manifest.value is not None
                                else None
                            )
                            workflow = (
                                loaded_manifest.value.get("workflow")
                                if loaded_manifest.value is not None
                                else None
                            )
                            trust_root_references = (
                                engine.get("release_manifest")
                                if isinstance(engine, dict)
                                else None,
                                golden.get("input_path")
                                if isinstance(golden, dict)
                                else None,
                                golden.get("outputs_path")
                                if isinstance(golden, dict)
                                else None,
                                workflow.get("allowlist")
                                if isinstance(workflow, dict)
                                else None,
                            )
                            for reference in trust_root_references:
                                trust_root_path = _producer_path(root, reference)
                                if trust_root_path is not None:
                                    paths.add(trust_root_path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nodes", nargs="+", help="exact legal node id(s)")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--node-index", required=True)
    parser.add_argument("--closure-summary", required=True)
    parser.add_argument("--comparisons", required=True)
    parser.add_argument("--exercise-census", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--governance", required=True)
    parser.add_argument("--output", default="certified-nodes.yaml")
    parser.add_argument("--reasons-output")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if len(set(args.nodes)) != len(args.nodes):
        parser.error("node ids must be unique")
    for node_id in args.nodes:
        if not _NODE_RE.fullmatch(node_id):
            parser.error(f"invalid legal node id: {node_id!r}")

    root = Path(args.repo_root).resolve()
    artifact = _load(root, args.artifact, "compiled_artifact")
    node_index = _load(root, args.node_index, "node_index")
    closure = _load(root, args.closure_summary, "closure_summary")
    comparisons = _load(root, args.comparisons, "node_comparisons")
    census = _load(root, args.exercise_census, "exercise_census")
    executable = _load(root, args.executable, "node_executable")
    run_manifest = _load(root, args.run_manifest, "run_manifest")
    governance = _load(root, args.governance, "workflow_governance")

    output_path = _resolve(root, args.output)
    reasons_path = _resolve(root, args.reasons_output) if args.reasons_output else None
    protected_paths = {
        Path(__file__).resolve(),
        artifact.path,
        node_index.path,
        closure.path,
        comparisons.path,
        census.path,
        executable.path,
        run_manifest.path,
        governance.path,
        *_declared_evidence_paths(root, comparisons, executable),
    }
    output_paths = {output_path}
    if reasons_path is not None:
        if reasons_path == output_path:
            parser.error("--output and --reasons-output must be different files")
        output_paths.add(reasons_path)
    collisions = output_paths & protected_paths
    if collisions:
        parser.error(
            "output paths must not overwrite producer/evidence inputs: "
            + ", ".join(sorted(path.as_posix() for path in collisions))
        )

    candidate_nodes = set(args.nodes)
    candidate_nodes.update(_existing_node_ids(output_path))

    evaluations = [
        evaluate_node(
            node_id,
            root=root,
            artifact=artifact,
            node_index=node_index,
            closure=closure,
            comparisons=comparisons,
            census=census,
            executable=executable,
            run_manifest=run_manifest,
            governance=governance,
        )
        for node_id in sorted(candidate_nodes)
    ]
    validated_run, _ = _run_context(
        run_manifest,
        governance,
        artifact,
        {
            "compiled_artifact": artifact,
            "node_index": node_index,
            "closure_summary": closure,
            "node_comparisons": comparisons,
            "exercise_census": census,
            "node_executable": executable,
        },
    )
    ledger = _render_ledger(evaluations, validated_run)
    result = _result_document(evaluations)
    result_rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"

    output_drift = _drifted(output_path, ledger)
    reasons_drift = (
        _drifted(reasons_path, result_rendered) if reasons_path is not None else False
    )
    write_error: OSError | None = None
    if not args.check:
        documents: dict[Path, str] = {}
        if reasons_path is not None:
            documents[reasons_path] = result_rendered
        # Replace the canonical ledger last: a failure updating a diagnostic
        # artifact must never leave the ledger advanced on its own.
        documents[output_path] = ledger
        try:
            _atomic_write_documents(documents)
        except OSError as exc:
            write_error = exc
        else:
            output_drift = False
            reasons_drift = False

    result["drift"] = {
        "certified_nodes": output_drift,
        "reasons": reasons_drift,
    }
    output_reasons = []
    if output_drift:
        output_reasons.append(
            _reason(
                "output",
                "output_drift",
                "certified_nodes",
                "committed certified-nodes.yaml differs from the harness projection",
            )
        )
    if reasons_drift:
        output_reasons.append(
            _reason(
                "output",
                "reasons_drift",
                "certify_nodes_result",
                "committed machine-readable reasons differ from the harness projection",
            )
        )
    if write_error is not None:
        output_reasons.append(
            _reason(
                "output",
                "write_failed",
                "certify_nodes",
                f"could not atomically write generated outputs: {write_error}",
            )
        )
    result["output_reasons"] = output_reasons
    print(json.dumps(result, sort_keys=True))
    rejected = bool(result["rejected"])
    if args.check and (output_drift or reasons_drift):
        print(
            "certified node output drifted; regenerate with scripts/certify_nodes.py",
            file=sys.stderr,
        )
        return 1
    if write_error is not None:
        print("could not write generated certification outputs", file=sys.stderr)
        return 1
    if rejected:
        print("one or more requested nodes did not certify", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
