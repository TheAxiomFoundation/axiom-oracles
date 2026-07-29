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
import json
import re
import sys
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
# Certified nodes — generated output only.
#
# Written by scripts/certify_nodes.py. A node appears only when all five
# computed criteria are green. Manual entries are invalid, and a regression
# removes the node on the next harness run.
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
    "exercise_evidence_missing": "evidence_missing",
    "dimension_bridged": "dimension_bridged",
    "dimension_missing": "dimension_missing",
    "dimension_constant": "dimension_constant",
    "exercise_dimension_invalid": "dimension_unvaried",
    "executable_unvalidated": "unvalidated",
    "executable_receipt_missing": "receipt_invalid",
    "executable_receipt_invalid": "receipt_invalid",
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


def _load(root: Path, value: str | Path, name: str) -> Loaded:
    path = _resolve(root, value)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return Loaded(name, path, None, None, f"cannot read {name}: {exc}")
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            payload = yaml.safe_load(raw)
        else:
            payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
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
    metadata = artifact.value.get("metadata")
    if not isinstance(metadata, dict):
        return [], {}, [
            _reason(
                "provision_rooted",
                "producer_missing",
                artifact.name,
                "compiled artifact has no metadata object",
            )
        ]
    raw_nodes = metadata.get("nodes")
    if not isinstance(raw_nodes, list):
        return [], {}, [
            _reason(
                "provision_rooted",
                "producer_missing",
                artifact.name,
                "compiled artifact metadata.nodes producer is absent",
            )
        ]
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


def _node_declaration(
    node_index: Loaded,
    artifact: Loaded,
    node_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    schema = _schema_reason("provision_rooted", node_index, NODE_INDEX_SCHEMA)
    if schema:
        return None, [schema]
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
        return None, reasons
    declaration = declarations.get(node_id)
    if not isinstance(declaration, dict):
        reasons.append(
            _reason(
                "provision_rooted",
                "node_declaration_missing",
                node_index.name,
                f"node index has no declaration for {node_id!r}",
            )
        )
        return None, reasons
    return declaration, reasons


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
    artifact: Loaded,
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
    return (value if not reasons else None), reasons


def _closed(
    closure: Loaded,
    declaration: dict[str, Any] | None,
    pins: dict[str, Any] | None,
    *,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    schema = _schema_reason("closed", closure, CLOSURE_SCHEMA)
    if schema:
        reasons.append(schema)
    roots = declaration.get("closure_roots") if declaration else None
    if not isinstance(roots, list) or not roots or not all(
        _is_string(item) for item in roots
    ):
        reasons.append(
            _reason(
                "closed",
                "closure_roots_missing",
                "node_index",
                "node declaration must name at least one exact closure root",
            )
        )
        roots = []
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
            for row in raw_rows:
                if isinstance(row, dict) and _is_string(row.get("root")):
                    rows[str(row["root"])] = row
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
        if not isinstance(by_status, dict) or any(
            not _is_int(by_status.get(status))
            for status in ("encoded", "excluded", "pending")
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
            or any(not _is_int(count) for count in by_reason.values())
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
        accounted = sum(by_status[status] for status in ("encoded", "excluded", "pending"))
        if not _is_int(total) or total != accounted:
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
    declaration: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    comparisons = declaration.get("comparisons") if declaration else None
    if not isinstance(comparisons, list) or not comparisons:
        reason = _reason(
            "conformant",
            "producer_missing",
            "node_index",
            "node declaration has no applicable comparison producer rows",
        )
        return [], [reason]
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    reasons: list[dict[str, Any]] = []
    for index, row in enumerate(comparisons):
        if not isinstance(row, dict) or not _is_string(row.get("suite")):
            reasons.append(
                _reason(
                    "conformant",
                    "comparison_applicability_missing",
                    "node_index",
                    f"comparisons[{index}] has no suite",
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
                    f"suite {suite!r} is declared more than once",
                )
            )
            continue
        seen.add(suite)
        clean.append(row)
    return clean, reasons


def _conformant(
    comparisons: Loaded,
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
            suites = {str(key): value for key, value in raw.items() if isinstance(value, dict)}
        else:
            reasons.append(
                _reason(
                    "conformant",
                    "producer_missing",
                    comparisons.name,
                    "comparison index has no comparisons object",
                )
            )

    evidence_rows: list[dict[str, Any]] = []
    for declaration in applicable:
        suite = str(declaration["suite"])
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
        if isinstance(report, dict) and _is_string(report.get("path")):
            report_path = _resolve(root, str(report["path"]))
            try:
                report_hash = _sha256(report_path.read_bytes())
            except OSError:
                report_hash = None
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
            suites = {str(key): value for key, value in raw.items() if isinstance(value, dict)}
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
    for declaration in applicable:
        suite = str(declaration["suite"])
        required = declaration.get("required_dimensions")
        if not isinstance(required, list) or not required or not all(
            _is_string(item) for item in required
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
        if row.get("report") != expected_path or row.get("report_sha256") != expected_sha:
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_report_identity_mismatch",
                    census.name,
                    f"suite {suite!r} census row names a different report",
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
        if row.get("reconciliation") != "full":
            reasons.append(
                _reason(
                    "exercised",
                    "comparison_not_fully_reconciled",
                    census.name,
                    f"suite {suite!r} census evidence is not fully reconciled",
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
        if not _is_int(row.get("cases_scanned"), minimum=1):
            reasons.append(
                _reason(
                    "exercised",
                    "exercise_evidence_missing",
                    census.name,
                    f"suite {suite!r} has no scanned cases",
                )
            )
        fields = row.get("evidence_fields")
        if not isinstance(fields, dict):
            fields = {}
        bridged = row.get("bridged_through")
        if not isinstance(bridged, dict):
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
            if field.get("state") != "varied" or not _is_int(
                field.get("distinct"), minimum=2
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
    reasons: list[dict[str, Any]] = []
    schema = _schema_reason("executable", executable, EXECUTABLE_SCHEMA)
    if schema:
        reasons.append(schema)
    row: dict[str, Any] | None = None
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
        if not isinstance(producer, dict) or producer.get("mode") != "computed":
            reasons.append(
                _reason(
                    "executable",
                    "producer_missing",
                    executable.name,
                    "executable index is not marked mode=computed",
                )
            )
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
    receipt_evidence: dict[str, Any] = {}
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
        receipt = row.get("receipt")
        receipt_path: Path | None = None
        receipt_hash: str | None = None
        receipt_value: dict[str, Any] | None = None
        if isinstance(receipt, dict) and _is_string(receipt.get("path")):
            receipt_path = _resolve(root, str(receipt["path"]))
            loaded_receipt = _load(root, receipt_path, "executable_receipt")
            receipt_hash = loaded_receipt.sha256
            receipt_value = loaded_receipt.value
        if (
            receipt_path is None
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
                    "executable receipt is absent, malformed, or not hash-bound",
                )
            )
        else:
            receipt_evidence = {
                "receipt": _path_label(receipt_path, root),
                "sha256": receipt_hash,
            }
            if receipt_value.get("schema") != RECEIPT_SCHEMA:
                reasons.append(
                    _reason(
                        "executable",
                        "executable_receipt_invalid",
                        executable.name,
                        "executable receipt schema is invalid",
                    )
                )
            receipt_engine = receipt_value.get("engine")
            receipt_artifact = receipt_value.get("artifact")
            workflow = receipt_value.get("workflow")
            if (
                not isinstance(receipt_engine, dict)
                or pins is None
                or receipt_engine.get("version") != pins.get("engine")
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "pin_mismatch",
                        executable.name,
                        "receipt engine version differs from the harness pin",
                    )
                )
            if (
                not isinstance(receipt_artifact, dict)
                or receipt_artifact.get("sha256") != artifact.sha256
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "pin_mismatch",
                        executable.name,
                        "receipt artifact hash differs from the compiled artifact",
                    )
                )
            if (
                not isinstance(workflow, dict)
                or not (
                    (type(workflow.get("run_id")) is int and workflow["run_id"] > 0)
                    or (
                        isinstance(workflow.get("run_id"), str)
                        and workflow["run_id"].isdigit()
                        and int(workflow["run_id"]) > 0
                    )
                )
                or not isinstance(workflow.get("sha"), str)
                or not _COMMIT_RE.fullmatch(workflow["sha"])
            ):
                reasons.append(
                    _reason(
                        "executable",
                        "producer_provenance_missing",
                        executable.name,
                        "receipt lacks CI run id and workflow SHA",
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
        "sha256": executable.sha256,
        **receipt_evidence,
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
) -> dict[str, Any]:
    """Evaluate one requested node without ever converting absence to success."""

    subgraph, nodes, graph_reasons = _artifact_nodes(artifact, node_id)
    declaration, declaration_reasons = _node_declaration(node_index, artifact, node_id)
    run, harness_reasons = _run_context(run_manifest, artifact)
    pins = run.get("pinned") if run else None

    provision, provision_reasons = _provision_rooted(
        artifact,
        subgraph,
        nodes,
        [*graph_reasons, *declaration_reasons],
        root=root,
    )
    closed, closed_reasons = _closed(closure, declaration, pins, root=root)
    applicable, applicability_reasons = _comparison_declarations(declaration)
    conformant, conformant_reasons, comparison_rows = _conformant(
        comparisons,
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


def _render_ledger(evaluations: list[dict[str, Any]], run: Loaded) -> str:
    certified = sorted(
        (row["entry"] for row in evaluations if row["entry"] is not None),
        key=lambda row: row["node"],
    )
    as_of: str
    if run.value is not None and _is_string(run.value.get("certified_at")):
        as_of = str(run.value["certified_at"]).split("T", 1)[0]
    else:
        as_of = "unverified"
    payload = {
        "schema": LEDGER_SCHEMA,
        "generated": True,
        "as_of": as_of,
        "nodes": certified,
    }
    return HEADER + "\n" + yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


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


def _check_or_write(path: Path, rendered: str, *, check: bool) -> bool:
    """Return true when the target drifted."""

    if check:
        try:
            return path.read_text() != rendered
        except OSError:
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    return False


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
        )
        for node_id in sorted(args.nodes)
    ]
    ledger = _render_ledger(evaluations, run_manifest)
    result = _result_document(evaluations)
    result_rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"

    output_path = _resolve(root, args.output)
    output_drift = _check_or_write(output_path, ledger, check=args.check)
    reasons_drift = False
    if args.reasons_output:
        reasons_path = _resolve(root, args.reasons_output)
        reasons_drift = _check_or_write(
            reasons_path,
            result_rendered,
            check=args.check,
        )

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
    result["output_reasons"] = output_reasons
    print(json.dumps(result, sort_keys=True))
    rejected = bool(result["rejected"])
    if args.check and (output_drift or reasons_drift):
        print(
            "certified node output drifted; regenerate with scripts/certify_nodes.py",
            file=sys.stderr,
        )
        return 1
    if rejected:
        print("one or more requested nodes did not certify", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
