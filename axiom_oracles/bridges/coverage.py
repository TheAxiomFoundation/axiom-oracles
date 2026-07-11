"""PolicyEngine oracle coverage reports for RuleSpec repositories."""

from __future__ import annotations

import ast
import importlib.util
import os
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .repo_routing import (
    canonical_program_spec_path,
    RULESPEC_ATOMIC_ROOTS,
    canonical_rulespec_module_path,
    canonical_rulespec_repo_name,
    canonical_rulespec_root_identity,
    is_policy_repo_root,
    iter_jurisdiction_content_dirs,
)

from .registry import PolicyEngineMapping, load_policyengine_registry

EXECUTABLE_RULE_KINDS = {"parameter", "derived", "derived_relation"}
ORACLE_COVERAGE_STATUSES = {
    "comparable",
    "incomplete_comparable",
    "known_not_comparable",
    "unmapped",
}
PROGRAM_SURFACE_STATUSES = {
    "deferred_jurisdiction",
    "input_only",
    "known_not_comparable",
    "out_of_scope",
    "pe_in_progress",
    "pending_oracle_mapping",
    "pending_rulespec_encoding",
    "pending_source_ingestion",
    "wired",
}
PENDING_PROGRAM_SURFACE_STATUSES = {
    "deferred_jurisdiction",
    "pending_oracle_mapping",
    "pending_rulespec_encoding",
    "pending_source_ingestion",
}
PROGRAM_SURFACE_LIFECYCLES = {"active", "inactive", "sunset", "historical"}
POPULACE_VALIDATION_STATUSES = {
    "validated",
    "pending_validator",
    "not_applicable",
    "not_configured",
    "blocked",
}
POLICYENGINE_CLOUD_QUEUE_SCHEMA = "axiom-encode/policyengine-cloud-queue/v1"
POLICYENGINE_CLOUD_RUN_ARTIFACT_SCHEMA = (
    "axiom-encode/policyengine-cloud-run-artifact/v1"
)
CLOUD_QUEUE_STATUSES = {
    "deferred_jurisdiction",
    "pending_oracle_mapping",
    "pending_rulespec_encoding",
    "pending_source_ingestion",
}
CLOUD_QUEUE_STATUS_ACTIONS = {
    "pending_oracle_mapping": "wire_oracle_mapping",
    "pending_rulespec_encoding": "encode_rulespec",
    "pending_source_ingestion": "ingest_source",
    "deferred_jurisdiction": "ingest_source",
}
_PROGRAM_TOKEN_RE = {
    token: re.compile(rf"(^|[^a-z0-9]){token}([^a-z0-9]|$)")
    for token in ("medicaid", "chip", "aca")
}
_HEALTH_PROGRAMS = frozenset({"medicaid", "chip", "aca_ptc"})
_US_STATE_CODES = frozenset(
    {
        "ak",
        "al",
        "ar",
        "az",
        "ca",
        "co",
        "ct",
        "dc",
        "de",
        "fl",
        "ga",
        "hi",
        "ia",
        "id",
        "il",
        "in",
        "ks",
        "ky",
        "la",
        "ma",
        "md",
        "me",
        "mi",
        "mn",
        "mo",
        "ms",
        "mt",
        "nc",
        "nd",
        "ne",
        "nh",
        "nj",
        "nm",
        "nv",
        "ny",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "va",
        "vt",
        "wa",
        "wi",
        "wv",
        "wy",
    }
)
_US_STATE_VARIABLE_PREFIX_RE = re.compile(
    rf"(^|\s)({'|'.join(sorted(_US_STATE_CODES))})_"
)
_INTERVAL_BOUND_HELPER_RE = re.compile(
    r"(^|_)(tier|band|bracket|interval|row)_(lower|upper)_bound$"
)
_FORMULA_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_QUOTED_STRING_RE = re.compile(r"('([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\")")
_RULESPEC_BUILTIN_IDENTIFIERS = {
    "False",
    "None",
    "True",
    "abs",
    "all",
    "and",
    "any",
    "ceil",
    "count",
    "count_where",
    "else",
    "false",
    "floor",
    "if",
    "in",
    "len",
    "max",
    "min",
    "not",
    "or",
    "round",
    "sum",
    "sum_where",
    "true",
    "where",
}
_UPSTREAM_PLACEHOLDER_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"(^|_)as_defined_in_",
        r"(^|_)defined_(in|under)_",
        r"(^|_)described_in_.*(section|subsection|paragraph|subparagraph|clause|subclause|part|subpart|title|chapter|act)",
        r"(^|_)determined_(for|under|by)_",
        r"(^|_)conditions_under_",
        r"(^|_)state_elected_.*category",
        r"(^|_)previous_mandatory_subclause",
        r"(^|_)mandatory_subclauses",
        r"(^|_)applicable_level",
        r"^person_is_in_.*category",
        r"^person_is_qualified_.*(beneficiary|group)",
    )
)
POLICYBENCH_SOURCE_URL = "https://policybench.org/"
POLICYBENCH_SNAPSHOT = "2026-06-14"
POLICYBENCH_HOUSEHOLD_OUTPUT_WEIGHTS = {
    "person_level_medicaid_eligibility": 29.86,
    "federal_tax_before_refundable_credits": 19.14,
    "payroll_tax": 15.65,
    "person_level_medicare_eligibility": 10.74,
    "state_tax_before_refundable_credits": 6.00,
    "snap": 4.15,
    "federal_refundable_credits": 3.70,
    "person_level_early_head_start_eligibility": 3.10,
    "self_employment_tax": 2.09,
    "ssi": 1.97,
    "person_level_head_start_eligibility": 1.18,
    "free_school_meals_eligibility": 0.74,
    "state_refundable_credits": 0.55,
    "person_level_wic_eligibility": 0.32,
    "local_income_tax": 0.26,
    "tanf": 0.26,
    "person_level_chip_eligibility": 0.18,
    "reduced_price_school_meals_eligibility": 0.10,
}
_POLICYBENCH_OUTPUT_BY_PROGRAM_ID = {
    "federal_income_tax": "federal_tax_before_refundable_credits",
    "state_income_tax": "state_tax_before_refundable_credits",
    "payroll_taxes": "payroll_tax",
    "medicaid": "person_level_medicaid_eligibility",
    "medicare": "person_level_medicare_eligibility",
    "snap": "snap",
    "wic": "person_level_wic_eligibility",
    "chip": "person_level_chip_eligibility",
    "tanf": "tanf",
    "ssi": "ssi",
    "ssi_state_supplement": "ssi",
    "head_start": "person_level_head_start_eligibility",
    "school_meals": "free_school_meals_eligibility",
}
_POLICYBENCH_OUTPUT_BY_VARIABLE = {
    "income_tax": "federal_tax_before_refundable_credits",
    "employee_payroll_tax": "payroll_tax",
    "is_medicare_eligible": "person_level_medicare_eligibility",
    "is_medicaid_eligible": "person_level_medicaid_eligibility",
    "is_chip_eligible": "person_level_chip_eligibility",
    "is_wic_eligible": "person_level_wic_eligibility",
    "is_head_start_eligible": "person_level_head_start_eligibility",
    "is_early_head_start_eligible": "person_level_early_head_start_eligibility",
    "state_income_tax": "state_tax_before_refundable_credits",
    "snap": "snap",
    "wic": "person_level_wic_eligibility",
    "medicaid": "person_level_medicaid_eligibility",
    "chip": "person_level_chip_eligibility",
    "ssi": "ssi",
    "free_school_meals": "free_school_meals_eligibility",
    "reduced_price_school_meals": "reduced_price_school_meals_eligibility",
    "self_employment_tax": "self_employment_tax",
    "nyc_income_tax": "local_income_tax",
}


@dataclass(frozen=True)
class PolicyEngineCoverageItem:
    """One executable RuleSpec output classified against PolicyEngine."""

    legal_id: str
    repo: str
    file: str
    rule_name: str
    kind: str
    status: str
    program: str
    mapping_type: str | None = None
    policyengine_variable: str | None = None
    policyengine_parameter: str | None = None
    parameter_key: str | None = None
    rationale: str | None = None
    candidate_priority: str | None = None
    tested: bool = False
    test_output_count: int = 0
    upstream_completeness_status: str | None = None
    upstream_completeness_issues: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, str | int | bool | None]:
        return {
            "legal_id": self.legal_id,
            "repo": self.repo,
            "file": self.file,
            "rule_name": self.rule_name,
            "kind": self.kind,
            "status": self.status,
            "program": self.program,
            "mapping_type": self.mapping_type,
            "policyengine_variable": self.policyengine_variable,
            "policyengine_parameter": self.policyengine_parameter,
            "parameter_key": self.parameter_key,
            "rationale": self.rationale,
            "candidate_priority": self.candidate_priority,
            "tested": self.tested,
            "test_output_count": self.test_output_count,
            "upstream_completeness_status": self.upstream_completeness_status,
            "upstream_completeness_issues": list(self.upstream_completeness_issues),
        }


@dataclass(frozen=True)
class PolicyEngineCandidateItem:
    """One actionable oracle mapping candidate or review item."""

    legal_id: str
    repo: str
    file: str
    rule_name: str
    status: str
    program: str
    category: str
    priority: str
    recommendation: str
    policyengine_variable: str | None = None
    policyengine_parameter: str | None = None
    rationale: str | None = None
    tested: bool = False
    test_output_count: int = 0
    policybench_output: str | None = None
    policybench_household_weight: float | None = None

    def as_dict(self) -> dict[str, str | int | float | bool | None]:
        return {
            "legal_id": self.legal_id,
            "repo": self.repo,
            "file": self.file,
            "rule_name": self.rule_name,
            "status": self.status,
            "program": self.program,
            "category": self.category,
            "priority": self.priority,
            "recommendation": self.recommendation,
            "policyengine_variable": self.policyengine_variable,
            "policyengine_parameter": self.policyengine_parameter,
            "rationale": self.rationale,
            "tested": self.tested,
            "test_output_count": self.test_output_count,
            "policybench_output": self.policybench_output,
            "policybench_household_weight": self.policybench_household_weight,
        }


@dataclass(frozen=True)
class PolicyEngineProgramSurfaceItem:
    """One PolicyEngine program variable classified against Axiom wiring."""

    country: str
    program_id: str
    program_name: str
    category: str
    policyengine_status: str
    coverage: str
    variable: str
    axiom_status: str
    lifecycle: str = "active"
    source_type: str = "program"
    agency: str | None = None
    state: str | None = None
    priority: str | None = None
    rationale: str | None = None
    mapping_count: int = 0
    comparable_mapping_count: int = 0
    legal_ids: tuple[str, ...] = ()
    policybench_output: str | None = None
    policybench_household_weight: float | None = None
    populace_validation_status: str = "not_configured"
    populace_validation_command: str | None = None
    populace_validation_dataset: str | None = None
    populace_validation_last_run: str | None = None
    populace_validation_rationale: str | None = None

    def as_dict(self) -> dict[str, str | int | float | list[str] | None]:
        return {
            "country": self.country,
            "program_id": self.program_id,
            "program_name": self.program_name,
            "category": self.category,
            "policyengine_status": self.policyengine_status,
            "coverage": self.coverage,
            "variable": self.variable,
            "axiom_status": self.axiom_status,
            "lifecycle": self.lifecycle,
            "source_type": self.source_type,
            "agency": self.agency,
            "state": self.state,
            "priority": self.priority,
            "rationale": self.rationale,
            "mapping_count": self.mapping_count,
            "comparable_mapping_count": self.comparable_mapping_count,
            "legal_ids": list(self.legal_ids),
            "policybench_output": self.policybench_output,
            "policybench_household_weight": self.policybench_household_weight,
            "populace_validation_status": self.populace_validation_status,
            "populace_validation_command": self.populace_validation_command,
            "populace_validation_dataset": self.populace_validation_dataset,
            "populace_validation_last_run": self.populace_validation_last_run,
            "populace_validation_rationale": self.populace_validation_rationale,
        }


@dataclass(frozen=True)
class PolicyEngineCloudQueueItem:
    """One deterministic work item for future cloud-parallel encoding."""

    id: str
    action: str
    priority: str | None
    axiom_status: str
    country: str
    target_repo: str
    target_prefix: str
    program_id: str
    program_name: str
    category: str
    policyengine_variable: str
    policyengine_status: str
    coverage: str
    source_type: str
    agency: str | None = None
    state: str | None = None
    policybench_output: str | None = None
    policybench_household_weight: float | None = None
    oracle_expectation: str | None = None
    lock_scopes: tuple[str, ...] = ()
    legal_ids: tuple[str, ...] = ()
    rationale: str | None = None

    def as_dict(self) -> dict[str, str | float | list[str] | None]:
        return {
            "id": self.id,
            "action": self.action,
            "priority": self.priority,
            "axiom_status": self.axiom_status,
            "country": self.country,
            "target_repo": self.target_repo,
            "target_prefix": self.target_prefix,
            "program_id": self.program_id,
            "program_name": self.program_name,
            "category": self.category,
            "agency": self.agency,
            "state": self.state,
            "policyengine_variable": self.policyengine_variable,
            "policyengine_status": self.policyengine_status,
            "coverage": self.coverage,
            "source_type": self.source_type,
            "policybench_output": self.policybench_output,
            "policybench_household_weight": self.policybench_household_weight,
            "oracle_expectation": self.oracle_expectation,
            "lock_scopes": list(self.lock_scopes),
            "legal_ids": list(self.legal_ids),
            "rationale": self.rationale,
        }


def build_policyengine_coverage_report(
    root: Path,
    *,
    program: str | None = None,
    include_program_surfaces: bool = False,
) -> dict[str, Any]:
    """Classify executable RuleSpec outputs against the PolicyEngine registry."""
    registry = load_policyengine_registry()
    _require_explicit_rulespec_root(root)
    root = root.resolve()
    raw_items = _iter_policyengine_coverage_items(root, registry)
    duplicate_ids = sorted(
        legal_id
        for legal_id, count in Counter(item.legal_id for item in raw_items).items()
        if count > 1
    )
    if duplicate_ids:
        raise ValueError(f"duplicate canonical RuleSpec output: {duplicate_ids[0]}")
    evidence_items = _apply_test_evidence_mappings(raw_items, registry)
    items = sorted(evidence_items, key=lambda item: item.legal_id)
    if program:
        programs = _program_filter_values(program)
        items = [item for item in items if item.program in programs]

    status_counts = Counter(item.status for item in items)
    untested_comparable = [
        item for item in items if item.status == "comparable" and not item.tested
    ]
    program_counts = Counter(item.program for item in items)
    repo_counts: dict[str, Counter[str]] = {}
    for item in items:
        repo_counts.setdefault(item.repo, Counter())[item.status] += 1

    report = {
        "oracle": "policyengine",
        "root": str(root),
        "total_outputs": len(items),
        "duplicate_outputs_collapsed": 0,
        "status_counts": dict(sorted(status_counts.items())),
        "untested_comparable": len(untested_comparable),
        "program_counts": dict(sorted(program_counts.items())),
        "repos": [
            {
                "repo": repo,
                "total_outputs": sum(counter.values()),
                "status_counts": dict(sorted(counter.items())),
            }
            for repo, counter in sorted(repo_counts.items())
        ],
        "items": [item.as_dict() for item in items],
    }
    if include_program_surfaces:
        report["program_surfaces"] = build_policyengine_program_surface_report(
            program=program,
            registry=registry,
        )
    return report


def build_policyengine_cloud_queue_report(
    root: Path,
    *,
    country: str = "us",
    program: str | None = None,
    manifest_path: Path | None = None,
    include_deferred_jurisdictions: bool = True,
) -> dict[str, Any]:
    """Export a deterministic work queue from PolicyEngine program surfaces.

    The queue is intentionally model-free: it does not assign agents or create
    branches. It gives cloud workers a stable work-item contract while the
    orchestration layer is still being designed.
    """
    _require_explicit_rulespec_root(root)
    root = root.resolve()
    surface_report = build_policyengine_program_surface_report(
        country=country,
        program=program,
        manifest_path=manifest_path,
    )
    statuses = set(CLOUD_QUEUE_STATUSES)
    if not include_deferred_jurisdictions:
        statuses.discard("deferred_jurisdiction")
    raw_items = [
        _cloud_queue_item_from_program_surface(item)
        for item in surface_report["items"]
        if item.get("axiom_status") in statuses
    ]
    items = sorted(
        raw_items,
        key=lambda item: (
            -(item.policybench_household_weight or 0.0),
            _candidate_priority_rank(item.priority or ""),
            _cloud_queue_action_rank(item.action),
            item.target_repo,
            item.program_id,
            item.policyengine_variable,
        ),
    )
    action_counts = Counter(item.action for item in items)
    priority_counts = Counter(item.priority for item in items if item.priority)
    repo_counts: dict[str, Counter[str]] = {}
    for item in items:
        repo_counts.setdefault(item.target_repo, Counter())[item.action] += 1
    return {
        "schema": POLICYENGINE_CLOUD_QUEUE_SCHEMA,
        "run_artifact_schema": POLICYENGINE_CLOUD_RUN_ARTIFACT_SCHEMA,
        "oracle": "policyengine",
        "root": str(root),
        "country": country,
        "program": program,
        "source": surface_report.get("source", {}),
        "total_items": len(items),
        "action_counts": dict(sorted(action_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "repos": [
            {
                "repo": repo,
                "total_items": sum(counter.values()),
                "action_counts": dict(sorted(counter.items())),
            }
            for repo, counter in sorted(repo_counts.items())
        ],
        "artifact_contract": {
            "required_fields": [
                "schema",
                "work_item_id",
                "status",
                "encoder_version",
                "encoder_git_sha",
                "corpus_ref",
                "rulespec_base_sha",
                "model",
                "prompt_hash",
                "generated_diff",
                "validation_logs",
                "oracle_results",
                "retry_history",
                "final_classification",
            ],
        },
        "items": [item.as_dict() for item in items],
    }


def build_policyengine_program_surface_report(
    *,
    country: str = "us",
    program: str | None = None,
    manifest_path: Path | None = None,
    registry=None,
) -> dict[str, Any]:
    """Classify PolicyEngine program variables against the Axiom registry."""
    registry = registry or load_policyengine_registry()
    payload = _load_policyengine_program_surface_manifest(
        country=country,
        manifest_path=manifest_path,
    )
    surfaces = [
        _program_surface_item_from_payload(raw_surface, registry=registry)
        for raw_surface in payload["surfaces"]
    ]
    if program:
        surfaces = [
            surface
            for surface in surfaces
            if _program_surface_matches_filter(surface, program)
        ]
    status_counts = Counter(surface.axiom_status for surface in surfaces)
    priority_counts = Counter(
        surface.priority for surface in surfaces if surface.priority
    )
    lifecycle_counts = Counter(surface.lifecycle for surface in surfaces)
    active_priority_counts = Counter(
        surface.priority
        for surface in surfaces
        if surface.lifecycle == "active" and surface.priority
    )
    pending_surfaces = [
        surface
        for surface in surfaces
        if surface.axiom_status in PENDING_PROGRAM_SURFACE_STATUSES
    ]
    active_pending_surfaces = [
        surface for surface in pending_surfaces if surface.lifecycle == "active"
    ]
    unvalidated_populace_surfaces = [
        surface
        for surface in surfaces
        if _surface_requires_populace_validation(surface)
        and surface.populace_validation_status != "validated"
    ]
    populace_validation_counts = Counter(
        surface.populace_validation_status for surface in surfaces
    )
    actionable_surfaces = sorted(
        active_pending_surfaces,
        key=lambda surface: (
            -(surface.policybench_household_weight or 0.0),
            _candidate_priority_rank(surface.priority or ""),
            surface.category,
            surface.coverage,
            surface.program_id,
            surface.variable,
        ),
    )
    return {
        "oracle": "policyengine",
        "country": country,
        "program": program,
        "source": payload.get("source", {}),
        "total_surfaces": len(surfaces),
        "status_counts": dict(sorted(status_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
        "active_priority_counts": dict(sorted(active_priority_counts.items())),
        "policybench": {
            "source": POLICYBENCH_SOURCE_URL,
            "snapshot": POLICYBENCH_SNAPSHOT,
            "weighting": "household",
            "weights": POLICYBENCH_HOUSEHOLD_OUTPUT_WEIGHTS,
        },
        "pending_surfaces": len(pending_surfaces),
        "active_pending_surfaces": len(active_pending_surfaces),
        "unvalidated_populace_surfaces": len(unvalidated_populace_surfaces),
        "populace_validation_counts": dict(sorted(populace_validation_counts.items())),
        "unvalidated_populace_items": [
            surface.as_dict()
            for surface in sorted(
                unvalidated_populace_surfaces,
                key=lambda surface: (
                    -(surface.policybench_household_weight or 0.0),
                    _candidate_priority_rank(surface.priority or ""),
                    surface.category,
                    surface.coverage,
                    surface.program_id,
                    surface.variable,
                ),
            )
        ],
        "actionable_surfaces": [surface.as_dict() for surface in actionable_surfaces],
        "items": [surface.as_dict() for surface in surfaces],
    }


def _surface_requires_populace_validation(
    surface: PolicyEngineProgramSurfaceItem,
) -> bool:
    """Return whether a PE-facing surface needs population-level parity evidence."""
    return surface.lifecycle == "active" and surface.axiom_status == "wired"


def _cloud_queue_item_from_program_surface(
    item: dict[str, Any],
) -> PolicyEngineCloudQueueItem:
    status = str(item.get("axiom_status") or "")
    action = CLOUD_QUEUE_STATUS_ACTIONS[status]
    country = str(item.get("country") or "us").lower()
    state = item.get("state")
    state_text = str(state).lower() if state else None
    target_prefix = f"{country}-{state_text}" if state_text else country
    target_repo = (
        "axiom-corpus"
        if action == "ingest_source"
        else canonical_rulespec_repo_name_from_prefix(target_prefix)
    )
    variable = str(item.get("variable") or "")
    queue_id = ":".join(
        [
            "policyengine-surface",
            country,
            str(item.get("coverage") or "").lower(),
            _queue_slug(variable),
        ]
    )
    lock_scopes = [
        f"policyengine-surface:{country}:{variable}",
        f"target-prefix:{target_prefix}",
    ]
    if target_repo:
        lock_scopes.append(f"repo:{target_repo}")
    legal_ids = tuple(str(legal_id) for legal_id in item.get("legal_ids", []) or ())
    lock_scopes.extend(f"legal-id:{legal_id}" for legal_id in legal_ids)
    if action == "ingest_source":
        lock_scopes.append(
            "corpus-source:"
            f"{country}:{str(item.get('program_id') or '').lower()}:{variable}"
        )

    return PolicyEngineCloudQueueItem(
        id=queue_id,
        action=action,
        priority=item.get("priority"),
        axiom_status=status,
        country=country,
        target_repo=target_repo,
        target_prefix=target_prefix,
        program_id=str(item.get("program_id") or ""),
        program_name=str(item.get("program_name") or ""),
        category=str(item.get("category") or ""),
        agency=item.get("agency"),
        state=str(state) if state else None,
        policyengine_variable=variable,
        policyengine_status=str(item.get("policyengine_status") or ""),
        coverage=str(item.get("coverage") or ""),
        source_type=str(item.get("source_type") or "program"),
        policybench_output=item.get("policybench_output"),
        policybench_household_weight=item.get("policybench_household_weight"),
        oracle_expectation=_cloud_queue_oracle_expectation(action),
        lock_scopes=tuple(dict.fromkeys(lock_scopes)),
        legal_ids=legal_ids,
        rationale=item.get("rationale"),
    )


def canonical_rulespec_repo_name_from_prefix(prefix: str) -> str:
    """Return the country-level RuleSpec repo name for a jurisdiction prefix."""
    country = prefix.split("-", 1)[0].lower()
    return f"rulespec-{country}"


def _cloud_queue_oracle_expectation(action: str) -> str:
    if action == "encode_rulespec":
        return "encode source-law output and add exact oracle mapping when comparable"
    if action == "ingest_source":
        return "ingest source before scheduling RuleSpec encoding"
    if action == "wire_oracle_mapping":
        return "classify existing legal outputs in the oracle registry"
    return "classify outcome before merge"


def _cloud_queue_action_rank(action: str) -> int:
    return {
        "ingest_source": 0,
        "encode_rulespec": 1,
        "wire_oracle_mapping": 2,
    }.get(action, 99)


def _queue_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def build_policyengine_candidate_report(
    root: Path,
    *,
    program: str | None = None,
    policyengine_variables: set[str] | None = None,
) -> dict[str, Any]:
    """Build a triage queue for expanding PolicyEngine oracle coverage."""
    coverage_report = build_policyengine_coverage_report(root, program=program)
    pe_variables = (
        policyengine_variables
        if policyengine_variables is not None
        else _load_policyengine_variable_names()
    )
    raw_candidates = [
        _candidate_from_coverage_item(
            item,
            policyengine_variables=pe_variables,
        )
        for item in coverage_report["items"]
    ]
    candidates = sorted(
        (candidate for candidate in raw_candidates if candidate is not None),
        key=lambda item: (
            _candidate_priority_rank(item.priority),
            -(item.policybench_household_weight or 0.0),
            item.category,
            item.legal_id,
        ),
    )
    category_counts = Counter(item.category for item in candidates)
    priority_counts = Counter(item.priority for item in candidates)
    return {
        "oracle": "policyengine",
        "root": coverage_report["root"],
        "program": program,
        "policyengine_variables_available": pe_variables is not None,
        "total_candidates": len(candidates),
        "category_counts": dict(sorted(category_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "coverage_status_counts": coverage_report["status_counts"],
        "items": [item.as_dict() for item in candidates],
    }


def _require_explicit_rulespec_root(root: Path) -> None:
    """Reject workspace, flat, aliased, and partially migrated scan roots."""

    if is_policy_repo_root(root) or canonical_rulespec_root_identity(root) is not None:
        return
    raise ValueError(
        "coverage root must be an exact rulespec-<country> checkout or its "
        "direct jurisdiction root"
    )


def _iter_canonical_rulespec_yaml(
    content_dir: Path,
    *,
    roots: frozenset[str] = RULESPEC_ATOMIC_ROOTS,
) -> list[Path]:
    """Return exact ``.yaml`` files beneath selected canonical roots.

    A legacy ``.yml`` file is rejected instead of being silently omitted from
    coverage.  Symlinked and otherwise noncanonical files also fail closed.
    """

    files: list[Path] = []
    for root_name in sorted(roots):
        rules_root = content_dir / root_name
        if not rules_root.exists():
            continue
        if rules_root.is_symlink() or not rules_root.is_dir():
            raise ValueError(
                f"canonical RuleSpec root is not a real directory: {rules_root}"
            )
        for rulespec_file in sorted(rules_root.rglob("*")):
            if rulespec_file.suffix == ".yml" and rulespec_file.is_file():
                raise ValueError(
                    f"RuleSpec coverage accepts .yaml only; migrate {rulespec_file}"
                )
            if rulespec_file.suffix != ".yaml" or not rulespec_file.is_file():
                continue
            if root_name == "programs":
                canonical = canonical_program_spec_path(
                    rulespec_file, content_root=content_dir
                )
            else:
                canonical = canonical_rulespec_module_path(
                    rulespec_file, content_root=content_dir
                )
            if canonical is None:
                raise ValueError(f"noncanonical RuleSpec module path: {rulespec_file}")
            files.append(canonical)
    return files


def _iter_policyengine_coverage_items(
    root: Path,
    registry,
) -> list[PolicyEngineCoverageItem]:
    items: list[PolicyEngineCoverageItem] = []
    items.extend(_iter_program_spec_coverage_items(root, registry))
    # Each explicit country checkout contributes only its direct jurisdiction
    # roots.  A direct jurisdiction root contributes only itself.
    for prefix, content_dir in iter_jurisdiction_content_dirs(root):
        repo_name = canonical_rulespec_repo_name(content_dir)
        if repo_name is None:
            raise ValueError(f"noncanonical RuleSpec root: {content_dir}")
        for rulespec_file in _iter_canonical_rulespec_yaml(content_dir):
            if rulespec_file.name.endswith(".test.yaml"):
                continue
            payload = _load_rulespec_payload(rulespec_file)
            if not payload:
                continue
            rules = payload.get("rules")
            if not isinstance(rules, list):
                continue
            defined_identifiers = _rulespec_defined_identifiers(payload)
            test_output_counts = _rulespec_test_output_counts(rulespec_file)
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                kind = str(rule.get("kind") or "").strip()
                if kind not in EXECUTABLE_RULE_KINDS:
                    continue
                rule_name = str(rule.get("name") or "").strip()
                if not rule_name:
                    continue
                legal_id = _canonical_rulespec_legal_id(
                    prefix=prefix,
                    content_dir=content_dir,
                    rulespec_file=rulespec_file,
                    rule_name=rule_name,
                )
                mapping = registry.mapping_for_legal_id(
                    legal_id,
                    country=_country_from_rulespec_prefix(prefix),
                )
                test_output_count = _mapping_test_output_count(
                    legal_id,
                    mapping=mapping,
                    test_output_counts=test_output_counts,
                )
                items.append(
                    _coverage_item_from_mapping(
                        legal_id=legal_id,
                        repo_name=repo_name,
                        root=root,
                        rulespec_file=rulespec_file,
                        rule_name=rule_name,
                        rule=rule,
                        kind=kind,
                        mapping=mapping,
                        defined_identifiers=defined_identifiers,
                        test_output_count=test_output_count,
                    )
                )
    return items


def _apply_test_evidence_mappings(
    items: list[PolicyEngineCoverageItem],
    registry,
) -> list[PolicyEngineCoverageItem]:
    """Mark outputs tested when their mapping points to tested source outputs."""
    test_output_counts_by_id = {item.legal_id: item.test_output_count for item in items}
    out: list[PolicyEngineCoverageItem] = []
    for item in items:
        prefix, _, _ = item.legal_id.partition(":")
        mapping = registry.mapping_for_legal_id(
            item.legal_id,
            country=_country_from_rulespec_prefix(prefix),
        )
        if not mapping or not mapping.tested_by_legal_ids:
            out.append(item)
            continue
        evidence_count = sum(
            test_output_counts_by_id.get(evidence_legal_id, 0)
            for evidence_legal_id in set(mapping.tested_by_legal_ids)
            if evidence_legal_id != item.legal_id
        )
        if evidence_count <= 0:
            out.append(item)
            continue
        total_count = item.test_output_count + evidence_count
        out.append(
            replace(
                item,
                tested=total_count > 0,
                test_output_count=total_count,
            )
        )
    return out


def _iter_program_spec_coverage_items(
    root: Path,
    registry,
) -> list[PolicyEngineCoverageItem]:
    """Enumerate outputs declared under jurisdiction-native ``programs/``."""
    items: list[PolicyEngineCoverageItem] = []
    for _prefix, content_dir in iter_jurisdiction_content_dirs(root):
        repo_name = canonical_rulespec_repo_name(content_dir)
        if repo_name is None:
            raise ValueError(f"noncanonical RuleSpec root: {content_dir}")
        programs_dir = content_dir / "programs"
        if not programs_dir.is_dir():
            continue
        for spec_file in _iter_canonical_rulespec_yaml(
            content_dir,
            roots=frozenset({"programs"}),
        ):
            if spec_file.name.endswith(".test.yaml"):
                continue
            items.extend(
                _program_spec_coverage_items_for_file(
                    root=root,
                    repo_name=repo_name,
                    spec_file=spec_file,
                    registry=registry,
                )
            )
    return items


def _program_spec_coverage_items_for_file(
    *,
    root: Path,
    repo_name: str,
    spec_file: Path,
    registry,
) -> list[PolicyEngineCoverageItem]:
    payload = _load_program_spec_payload(spec_file)
    if not payload:
        return []
    raw_program = payload.get("program")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_program, str) or not raw_program.strip():
        return []
    if not isinstance(raw_outputs, list):
        return []
    program_id = raw_program.strip()
    prefix, _, program_path = program_id.partition("/")
    if not prefix or not program_path:
        return []
    period_stem = spec_file.with_suffix("").name
    spec_legal_path = f"programs/{program_path}/{period_stem}"
    country = _country_from_rulespec_prefix(prefix)
    file_path = _display_file_path(spec_file, root)
    items: list[PolicyEngineCoverageItem] = []
    for raw_output in raw_outputs:
        if not isinstance(raw_output, str) or not raw_output.strip():
            continue
        output_name = raw_output.strip()
        legal_id = f"{prefix}:{spec_legal_path}#{output_name}"
        mapping = registry.mapping_for_legal_id(legal_id, country=country)
        items.append(
            _coverage_item_from_program_spec_mapping(
                legal_id=legal_id,
                repo_name=repo_name,
                file_path=file_path,
                rule_name=output_name,
                program=program_path,
                mapping=mapping,
            )
        )
    return items


def _coverage_item_from_program_spec_mapping(
    *,
    legal_id: str,
    repo_name: str,
    file_path: str,
    rule_name: str,
    program: str,
    mapping: PolicyEngineMapping | None,
) -> PolicyEngineCoverageItem:
    if mapping is None:
        status = "unmapped"
        mapping_type = None
        report_program = program
    elif mapping.comparable:
        status = "comparable"
        mapping_type = mapping.mapping_type
        report_program = mapping.program or program
    else:
        status = "known_not_comparable"
        mapping_type = mapping.mapping_type
        report_program = mapping.program or program

    return PolicyEngineCoverageItem(
        legal_id=legal_id,
        repo=repo_name,
        file=file_path,
        rule_name=rule_name,
        kind="program_output",
        status=status,
        program=report_program,
        mapping_type=mapping_type,
        policyengine_variable=mapping.policyengine_variable if mapping else None,
        policyengine_parameter=mapping.policyengine_parameter if mapping else None,
        rationale=mapping.rationale if mapping else None,
        candidate_priority=mapping.candidate_priority if mapping else None,
        tested=False,
        test_output_count=0,
    )


def _candidate_from_coverage_item(
    item: dict[str, Any],
    *,
    policyengine_variables: set[str] | None,
) -> PolicyEngineCandidateItem | None:
    status = str(item.get("status") or "")
    rule_name = str(item.get("rule_name") or "")
    legal_id = str(item.get("legal_id") or "")
    tested = bool(item.get("tested"))
    pe_variable = item.get("policyengine_variable")
    pe_parameter = item.get("policyengine_parameter")
    exact_pe_variable = bool(
        policyengine_variables and rule_name in policyengine_variables
    )
    pe_looking = _is_policyengine_looking_rule_name(rule_name)

    if status == "comparable" and not tested:
        return _candidate_item(
            item,
            category="comparable_untested",
            priority=_candidate_priority(item, "P1"),
            recommendation=(
                "Add this comparable output to the companion .test.yaml so CI "
                "continues to exercise the oracle mapping."
            ),
        )

    if status == "incomplete_comparable":
        return _candidate_item(
            item,
            category="incomplete_comparable",
            priority=_candidate_priority(item, "P1"),
            recommendation=(
                "Do not treat this direct PolicyEngine mapping as parity-ready "
                "yet. Encode or import the unresolved primary-source "
                "dependencies listed in upstream_completeness_issues, then "
                "rerun coverage and Populace validation."
            ),
        )

    if status == "unmapped":
        if exact_pe_variable:
            return _candidate_item(
                item,
                category="exact_variable_unmapped",
                priority=_candidate_priority(item, "P1" if tested else "P2"),
                policyengine_variable=rule_name,
                recommendation=(
                    f"Review whether `{legal_id}` has the same legal boundary as "
                    f"PolicyEngine variable `{rule_name}`; if exact, add a "
                    "direct_variable mapping."
                ),
            )
        if tested and pe_looking:
            return _candidate_item(
                item,
                category="tested_unmapped_pe_like",
                priority=_candidate_priority(item, "P2"),
                recommendation=(
                    "This tested output looks oracle-relevant but has no explicit "
                    "classification. Add an exact mapping, an adapter-backed "
                    "mapping, or a not_comparable rationale."
                ),
            )
        return _candidate_item(
            item,
            category="unmapped",
            priority=_candidate_priority(item, "P3"),
            recommendation=(
                "Classify this output explicitly before relying on full oracle "
                "coverage gates."
            ),
        )

    if status == "known_not_comparable":
        if pe_variable or pe_parameter:
            priority = _candidate_priority(item, "P2" if tested else "P3")
            return _candidate_item(
                item,
                category="known_adjacent_target",
                priority=priority,
                recommendation=(
                    "A nearby PolicyEngine target is recorded but currently marked "
                    "not comparable. Revisit only if a small adapter can make the "
                    "RuleSpec tests compare without changing the legal boundary."
                    if priority != "P4"
                    else "A nearby PolicyEngine target is recorded, but this "
                    "non-comparable classification has already been reviewed. "
                    "Leave it alone unless the source or oracle semantics change."
                ),
            )
        if exact_pe_variable:
            priority = _candidate_priority(item, "P2" if tested else "P3")
            return _candidate_item(
                item,
                category="pe_name_but_not_comparable",
                priority=priority,
                policyengine_variable=rule_name,
                recommendation=(
                    f"`{rule_name}` exists in PolicyEngine, but the registry "
                    "currently classifies this Axiom output as not comparable. "
                    "Review the rationale before adding an exact override."
                    if priority != "P4"
                    else f"`{rule_name}` exists in PolicyEngine, but this "
                    "non-comparable classification has already been reviewed. "
                    "Leave it alone unless the source or oracle semantics change."
                ),
            )
        return _candidate_item(
            item,
            category="prefix_not_comparable",
            priority=_candidate_priority(item, "P4"),
            recommendation=(
                "Covered by a broad not_comparable prefix. Leave it alone unless "
                "this output becomes tested or a known exact oracle target."
            ),
        )

    return None


def _candidate_item(
    item: dict[str, Any],
    *,
    category: str,
    priority: str,
    recommendation: str,
    policyengine_variable: str | None = None,
    policyengine_parameter: str | None = None,
) -> PolicyEngineCandidateItem:
    output = _policybench_output_for_coverage_item(
        item,
        policyengine_variable=policyengine_variable,
        policyengine_parameter=policyengine_parameter,
    )
    return PolicyEngineCandidateItem(
        legal_id=str(item.get("legal_id") or ""),
        repo=str(item.get("repo") or ""),
        file=str(item.get("file") or ""),
        rule_name=str(item.get("rule_name") or ""),
        status=str(item.get("status") or ""),
        program=str(item.get("program") or "unknown"),
        category=category,
        priority=priority,
        recommendation=recommendation,
        policyengine_variable=policyengine_variable
        if policyengine_variable is not None
        else item.get("policyengine_variable"),
        policyengine_parameter=policyengine_parameter
        if policyengine_parameter is not None
        else item.get("policyengine_parameter"),
        rationale=item.get("rationale"),
        tested=bool(item.get("tested")),
        test_output_count=int(item.get("test_output_count") or 0),
        policybench_output=output,
        policybench_household_weight=(
            POLICYBENCH_HOUSEHOLD_OUTPUT_WEIGHTS.get(output) if output else None
        ),
    )


def _candidate_priority_rank(priority: str) -> int:
    return {"P1": 0, "P2": 1, "P3": 2, "P4": 3}.get(priority, 99)


def _candidate_priority(item: dict[str, Any], default: str) -> str:
    priority = item.get("candidate_priority")
    if priority in {"P1", "P2", "P3", "P4"}:
        return str(priority)
    return default


def _is_policyengine_looking_rule_name(rule_name: str) -> bool:
    lowered = rule_name.lower()
    return lowered.startswith(("snap_", "is_snap_", "meets_snap_")) or any(
        token in lowered
        for token in (
            "tax",
            "deduction",
            "credit",
            "income",
            "allotment",
            "eligible",
            "eligibility",
            "threshold",
            "limit",
            "rate",
        )
    )


def _load_policyengine_variable_names() -> set[str] | None:
    source_names = _load_policyengine_variable_names_from_source()
    if source_names is not None:
        return source_names
    try:
        from policyengine_us import CountryTaxBenefitSystem
    except Exception:
        return None
    try:
        return set(CountryTaxBenefitSystem().variables)
    except Exception:
        return None


def _load_policyengine_variable_names_from_source() -> set[str] | None:
    """Load PolicyEngine-US variable names without importing its model package.

    Candidate triage only needs to know whether a RuleSpec output name exists
    as a PolicyEngine variable. Importing ``policyengine_us`` can execute the
    full tax-benefit system and fail before triage starts, so prefer a source
    tree scan when the package or a local checkout is available.
    """
    source_dirs = _policyengine_variable_source_dirs()
    if not source_dirs:
        return None
    names: set[str] = set()
    for source_dir in source_dirs:
        for source_file in sorted(source_dir.rglob("*.py")):
            names.update(_policyengine_variable_names_from_file(source_file))
    return names


def _policyengine_variable_source_dirs() -> list[Path]:
    source_dirs: list[Path] = []
    for env_name in ("AXIOM_POLICYENGINE_US_ROOT", "POLICYENGINE_US_ROOT"):
        raw_path = os.environ.get(env_name)
        if raw_path:
            source_dirs.extend(_policyengine_variable_dirs_for_path(Path(raw_path)))

    spec = importlib.util.find_spec("policyengine_us")
    if spec and spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            source_dirs.extend(_policyengine_variable_dirs_for_path(Path(location)))

    seen: set[Path] = set()
    out: list[Path] = []
    for source_dir in source_dirs:
        resolved = source_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(source_dir)
    return out


def _policyengine_variable_dirs_for_path(path: Path) -> list[Path]:
    candidates = (
        path,
        path / "variables",
        path / "policyengine_us" / "variables",
    )
    return [
        candidate
        for candidate in candidates
        if candidate.is_dir() and candidate.name == "variables"
    ]


def _policyengine_variable_names_from_file(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if any(_is_policyengine_variable_base(base) for base in node.bases):
            names.add(node.name)
    return names


def _is_policyengine_variable_base(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "Variable"
    if isinstance(node, ast.Attribute):
        return node.attr == "Variable"
    return False


def _load_policyengine_program_surface_manifest(
    *,
    country: str,
    manifest_path: Path | None,
) -> dict[str, Any]:
    path = (
        manifest_path
        if manifest_path is not None
        else Path(__file__).with_name("program_surfaces") / f"{country}.yaml"
    )
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(
            f"Unable to load PolicyEngine surface manifest {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"PolicyEngine surface manifest must be an object: {path}")
    raw_surfaces = payload.get("surfaces")
    if not isinstance(raw_surfaces, list):
        raise ValueError(
            f"PolicyEngine surface manifest surfaces must be a list: {path}"
        )
    for index, raw_surface in enumerate(raw_surfaces):
        if not isinstance(raw_surface, dict):
            raise ValueError(
                f"PolicyEngine surface manifest entry {index} must be an object: {path}"
            )
        missing = [
            key
            for key in (
                "country",
                "program_id",
                "program_name",
                "category",
                "policyengine_status",
                "coverage",
                "variable",
                "axiom_status",
            )
            if not raw_surface.get(key)
        ]
        if missing:
            raise ValueError(
                f"PolicyEngine surface manifest entry {index} missing "
                f"{', '.join(missing)}: {path}"
            )
        status = str(raw_surface.get("axiom_status"))
        if status not in PROGRAM_SURFACE_STATUSES:
            raise ValueError(
                f"Unsupported PolicyEngine surface status for "
                f"{raw_surface.get('variable')}: {status}"
            )
        lifecycle = str(raw_surface.get("lifecycle") or "active")
        if lifecycle not in PROGRAM_SURFACE_LIFECYCLES:
            raise ValueError(
                f"Unsupported PolicyEngine surface lifecycle for "
                f"{raw_surface.get('variable')}: {lifecycle}"
            )
        priority = raw_surface.get("priority")
        if lifecycle != "active" and priority in {"P1", "P2"}:
            raise ValueError(
                f"Non-active PolicyEngine surface {raw_surface.get('variable')} "
                f"must not use top priority {priority}; mark active current-law "
                "surfaces P1/P2 and demote historical, inactive, or sunset "
                "surfaces."
            )
        _validate_populace_validation(raw_surface, path=path)
    return payload


def _validate_populace_validation(raw_surface: dict[str, Any], *, path: Path) -> None:
    raw_validation = raw_surface.get("populace_validation")
    if raw_validation is None:
        return
    variable = raw_surface.get("variable")
    if not isinstance(raw_validation, dict):
        raise ValueError(
            f"PolicyEngine surface {variable} populace_validation must be an object: "
            f"{path}"
        )
    status = str(raw_validation.get("status") or "")
    if status not in POPULACE_VALIDATION_STATUSES:
        raise ValueError(
            f"Unsupported PolicyEngine surface Populace validation status for "
            f"{variable}: {status}"
        )
    if status == "validated":
        missing = [
            key
            for key in ("command", "dataset", "last_run")
            if not str(raw_validation.get(key) or "").strip()
        ]
        if missing:
            raise ValueError(
                f"Validated PolicyEngine surface {variable} missing "
                f"populace_validation {', '.join(missing)}: {path}"
            )
        command = str(raw_validation.get("command") or "")
        if "populace" not in command:
            raise ValueError(
                f"Validated PolicyEngine surface {variable} must cite a Populace "
                f"comparison command: {path}"
            )
    if status in {"blocked", "not_applicable", "pending_validator"}:
        rationale = str(raw_validation.get("rationale") or "").strip()
        if len(rationale) < 20:
            raise ValueError(
                f"PolicyEngine surface {variable} Populace validation status "
                f"{status} requires a rationale: {path}"
            )


def _program_surface_item_from_payload(
    payload: dict[str, Any],
    *,
    registry,
) -> PolicyEngineProgramSurfaceItem:
    variable = str(payload["variable"])
    country = str(payload.get("country") or "us")
    mappings = registry.mappings_for_policyengine_variable(variable, country=country)
    comparable_mapping_count = sum(1 for mapping in mappings if mapping.comparable)
    final_non_comparable_mapping_count = sum(
        1
        for mapping in mappings
        if not mapping.comparable and mapping.candidate_priority != "P4"
    )
    manifest_status = str(payload["axiom_status"])
    if comparable_mapping_count:
        axiom_status = "wired"
    elif final_non_comparable_mapping_count and manifest_status in {
        "pending_oracle_mapping",
        "pending_rulespec_encoding",
        "pending_source_ingestion",
        "deferred_jurisdiction",
    }:
        axiom_status = "known_not_comparable"
    elif manifest_status in PENDING_PROGRAM_SURFACE_STATUSES:
        axiom_status = manifest_status
    else:
        axiom_status = manifest_status
    legal_ids = tuple(mapping.legal_id for mapping in mappings)
    policybench_output = _policybench_output_for_program_surface(
        payload,
        legal_ids=legal_ids,
    )
    populace_validation = _populace_validation_fields(payload)
    return PolicyEngineProgramSurfaceItem(
        country=country,
        program_id=str(payload["program_id"]),
        program_name=str(payload["program_name"]),
        category=str(payload["category"]),
        policyengine_status=str(payload["policyengine_status"]),
        coverage=str(payload["coverage"]),
        variable=variable,
        axiom_status=axiom_status,
        lifecycle=str(payload.get("lifecycle") or "active"),
        source_type=str(payload.get("source_type") or "program"),
        agency=payload.get("agency"),
        state=payload.get("state"),
        priority=payload.get("priority"),
        rationale=payload.get("rationale"),
        mapping_count=len(mappings),
        comparable_mapping_count=comparable_mapping_count,
        legal_ids=legal_ids,
        policybench_output=policybench_output,
        policybench_household_weight=(
            POLICYBENCH_HOUSEHOLD_OUTPUT_WEIGHTS.get(policybench_output)
            if policybench_output
            else None
        ),
        populace_validation_status=populace_validation["status"],
        populace_validation_command=populace_validation.get("command"),
        populace_validation_dataset=populace_validation.get("dataset"),
        populace_validation_last_run=populace_validation.get("last_run"),
        populace_validation_rationale=populace_validation.get("rationale"),
    )


def _populace_validation_fields(payload: dict[str, Any]) -> dict[str, str | None]:
    raw_validation = payload.get("populace_validation")
    if not isinstance(raw_validation, dict):
        return {"status": "not_configured"}
    status = str(raw_validation.get("status") or "not_configured")
    if status not in POPULACE_VALIDATION_STATUSES:
        status = "not_configured"
    return {
        "status": status,
        "command": _optional_text(raw_validation.get("command")),
        "dataset": _optional_text(raw_validation.get("dataset")),
        "last_run": _optional_text(raw_validation.get("last_run")),
        "rationale": _optional_text(raw_validation.get("rationale")),
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _policybench_output_for_program_surface(
    payload: dict[str, Any],
    *,
    legal_ids: tuple[str, ...] = (),
) -> str | None:
    """Return the PolicyBench household output group for a PE program surface."""
    program_id = str(payload.get("program_id") or "")
    variable = str(payload.get("variable") or "")
    category = str(payload.get("category") or "")
    program_name = str(payload.get("program_name") or "").lower()
    if "early head start" in program_name:
        return "person_level_early_head_start_eligibility"
    if variable in _POLICYBENCH_OUTPUT_BY_VARIABLE:
        return _POLICYBENCH_OUTPUT_BY_VARIABLE[variable]
    if program_id in _POLICYBENCH_OUTPUT_BY_PROGRAM_ID:
        return _POLICYBENCH_OUTPUT_BY_PROGRAM_ID[program_id]
    if variable.endswith(("_tanf", "_tafdc", "_tca")) or program_id == "tanf":
        return "tanf"
    if variable.endswith("_income_tax") and variable != "state_income_tax":
        return "local_income_tax"
    if "federal_refundable" in program_id or "federal_refundable" in variable:
        return "federal_refundable_credits"
    if "refundable" in variable:
        return "state_refundable_credits"
    if category.lower() == "taxes" and _is_local_tax_program_surface(
        coverage=str(payload.get("coverage") or ""),
        program_id=program_id,
        program_name=program_name,
        variable=variable,
    ):
        return "local_income_tax"
    lowered_legal_ids = tuple(legal_id.lower() for legal_id in legal_ids)
    if any(legal_id.startswith("us:statutes/26/") for legal_id in lowered_legal_ids):
        text = " ".join(
            (program_id, variable, program_name, category, *lowered_legal_ids)
        ).lower()
        return _policybench_tax_output_from_text("", text)
    if category.lower() == "taxes":
        text = " ".join((program_id, variable, program_name, category)).lower()
        return _policybench_tax_output_from_text("", text)
    return None


def _policybench_output_for_coverage_item(
    item: dict[str, Any],
    *,
    policyengine_variable: str | None = None,
    policyengine_parameter: str | None = None,
) -> str | None:
    program = str(item.get("program") or "")
    if program == "medicaid":
        return "person_level_medicaid_eligibility"
    if program == "chip":
        return "person_level_chip_eligibility"
    if program == "medicare":
        return "person_level_medicare_eligibility"
    if program == "snap":
        return "snap"
    if program == "wic":
        return "person_level_wic_eligibility"
    if program in {"ssi", "ssi_state_supplement"}:
        return "ssi"
    if program in {"tanf", "tca"}:
        return "tanf"
    if program == "head_start":
        text = _policybench_candidate_text(
            item,
            policyengine_variable=policyengine_variable,
            policyengine_parameter=policyengine_parameter,
        )
        if "early_head_start" in text or "early head start" in text:
            return "person_level_early_head_start_eligibility"
        return "person_level_head_start_eligibility"
    if program == "tax" or _is_us_tax_like_coverage_item(
        item,
        policyengine_variable=policyengine_variable,
        policyengine_parameter=policyengine_parameter,
    ):
        return _policybench_tax_output_for_coverage_item(
            item,
            policyengine_variable=policyengine_variable,
            policyengine_parameter=policyengine_parameter,
        )
    return None


def _is_us_tax_like_coverage_item(
    item: dict[str, Any],
    *,
    policyengine_variable: str | None = None,
    policyengine_parameter: str | None = None,
) -> bool:
    legal_id = str(item.get("legal_id") or "").lower()
    if legal_id.startswith("us:statutes/26/"):
        return True
    parameter = policyengine_parameter or item.get("policyengine_parameter") or ""
    parameter = str(parameter).lower()
    if parameter.startswith("gov.irs."):
        return True
    if parameter.startswith("gov.states.") and ".tax." in parameter:
        return True
    text = _policybench_candidate_text(
        item,
        policyengine_variable=policyengine_variable,
        policyengine_parameter=policyengine_parameter,
    )
    return bool(legal_id.startswith("us-") and ".tax." in text)


def _policybench_tax_output_for_coverage_item(
    item: dict[str, Any],
    *,
    policyengine_variable: str | None = None,
    policyengine_parameter: str | None = None,
) -> str:
    legal_id = str(item.get("legal_id") or "").lower()
    text = _policybench_candidate_text(
        item,
        policyengine_variable=policyengine_variable,
        policyengine_parameter=policyengine_parameter,
    )
    return _policybench_tax_output_from_text(legal_id, text)


def _policybench_tax_output_from_text(legal_id: str, text: str) -> str:
    if "self_employment" in text or legal_id.startswith(
        ("us:statutes/26/1401", "us:statutes/26/1402")
    ):
        return "self_employment_tax"
    if any(
        token in text
        for token in (
            "payroll",
            "oasdi",
            "fica",
            "social_security_tax",
            "medicare_tax",
        )
    ) or legal_id.startswith(
        (
            "us:statutes/26/3101",
            "us:statutes/26/3102",
            "us:statutes/26/3111",
            "us:statutes/26/3121",
            "us:statutes/26/3128",
            "us:statutes/26/3201",
            "us:statutes/26/3221",
        )
    ):
        return "payroll_tax"
    if "refundable" in text:
        return (
            "state_refundable_credits"
            if _is_state_tax_candidate(legal_id, text)
            else "federal_refundable_credits"
        )
    if _is_state_tax_candidate(legal_id, text):
        return "state_tax_before_refundable_credits"
    return "federal_tax_before_refundable_credits"


def _is_state_tax_candidate(legal_id: str, text: str) -> bool:
    return bool(
        re.match(r"^us-[a-z]{2}:", legal_id)
        or ".states." in text
        or _US_STATE_VARIABLE_PREFIX_RE.search(text)
    )


def _is_local_tax_program_surface(
    *,
    coverage: str,
    program_id: str,
    program_name: str,
    variable: str,
) -> bool:
    normalized_coverage = coverage.strip().lower()
    if not normalized_coverage:
        return False
    if normalized_coverage in {"us", "u.s.", "united states", "national"}:
        return False
    if normalized_coverage in _US_STATE_CODES:
        return False
    text = " ".join((normalized_coverage, program_id, program_name, variable)).lower()
    return bool(
        re.match(r"^(sf|nyc)_", variable)
        or any(
            token in text
            for token in (
                "city",
                "county",
                "local",
                "municipal",
                "san francisco",
                "new york city",
            )
        )
    )


def _policybench_candidate_text(
    item: dict[str, Any],
    *,
    policyengine_variable: str | None = None,
    policyengine_parameter: str | None = None,
) -> str:
    parts = [
        str(item.get("legal_id") or ""),
        str(item.get("rule_name") or ""),
        str(policyengine_variable or item.get("policyengine_variable") or ""),
        str(policyengine_parameter or item.get("policyengine_parameter") or ""),
    ]
    return " ".join(parts).lower()


def _program_surface_matches_filter(
    surface: PolicyEngineProgramSurfaceItem,
    program: str,
) -> bool:
    programs = _program_filter_values(program)
    normalized = program.lower()
    if surface.program_id in programs or surface.variable in programs:
        return True
    if normalized == "tax" and surface.category.lower() == "taxes":
        return True
    if normalized == "health" and surface.category.lower() == "healthcare":
        return True
    if normalized in {"ccap", "ccdf", "child_care"}:
        return surface.program_id in {"ccdf", "ne_childcare"} or any(
            token in surface.variable
            for token in ("ccap", "ccdf", "child_care", "childcare", "caps")
        )
    return False


def _load_rulespec_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("format") != "rulespec/v1":
        return None
    return payload


def _load_program_spec_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _rulespec_test_output_counts(path: Path) -> Counter[str]:
    """Count canonical output IDs emitted by the companion `.test.yaml` file."""
    test_path = path.with_name(path.stem + ".test.yaml")
    if not test_path.exists():
        return Counter()
    try:
        payload = yaml.safe_load(test_path.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError, ValueError):
        return Counter()
    if isinstance(payload, dict):
        cases = payload.get("cases", payload.get("tests", []))
    else:
        cases = payload
    output_counts: Counter[str] = Counter()
    if not isinstance(cases, list):
        return output_counts
    for case in cases:
        if not isinstance(case, dict):
            continue
        outputs = case.get("output", case.get("expect"))
        if not isinstance(outputs, dict):
            continue
        output_counts.update(str(key) for key in outputs)
    return output_counts


def _mapping_test_output_count(
    legal_id: str,
    *,
    mapping: PolicyEngineMapping | None,
    test_output_counts: Counter[str],
) -> int:
    count = test_output_counts.get(legal_id, 0)
    if mapping is None:
        return count
    return count + sum(test_output_counts.get(alias, 0) for alias in mapping.aliases)


def _canonical_rulespec_legal_id(
    *,
    prefix: str,
    content_dir: Path,
    rulespec_file: Path,
    rule_name: str,
) -> str:
    """Derive an output ID relative to its exact jurisdiction content root."""
    relative = rulespec_file.relative_to(content_dir)
    if relative.suffix == ".yaml":
        relative = relative.with_suffix("")
    return f"{prefix}:{relative.as_posix()}#{rule_name}"


def _country_from_rulespec_prefix(prefix: str) -> str:
    """Infer PolicyEngine country from a RuleSpec repository prefix."""
    return prefix.split("-", 1)[0]


def _display_file_path(rulespec_file: Path, root: Path) -> str:
    """Return a canonical file path relative to the explicit scan root."""

    return str(rulespec_file.relative_to(root))


def _coverage_item_from_mapping(
    *,
    legal_id: str,
    repo_name: str,
    root: Path,
    rulespec_file: Path,
    rule_name: str,
    rule: dict[str, Any],
    kind: str,
    mapping: PolicyEngineMapping | None,
    defined_identifiers: set[str],
    test_output_count: int,
) -> PolicyEngineCoverageItem:
    file_path = _display_file_path(rulespec_file, root)
    upstream_issues: tuple[str, ...] = ()
    upstream_status: str | None = None
    if mapping is None:
        program = _infer_program_from_legal_id(legal_id, rule_name=rule_name)
        if _is_interval_bound_helper_rule(rule_name, rule):
            return PolicyEngineCoverageItem(
                legal_id=legal_id,
                repo=repo_name,
                file=file_path,
                rule_name=rule_name,
                kind=kind,
                status="known_not_comparable",
                program=program,
                mapping_type="not_comparable",
                rationale=(
                    "Indexed interval-bound helper used to select or interpolate "
                    "a source table row; PolicyEngine generally stores final "
                    "parameter scales or computed outputs, not these generated "
                    "RuleSpec row-bound helpers as one-to-one oracle targets."
                ),
                candidate_priority="P4",
                tested=test_output_count > 0,
                test_output_count=test_output_count,
            )
        status = "unmapped"
        mapping_type = None
    elif mapping.comparable:
        status = "comparable"
        program = mapping.program or _infer_program_from_legal_id(
            legal_id, rule_name=rule_name
        )
        mapping_type = mapping.mapping_type
        upstream_issues = _direct_mapping_upstream_completeness_issues(
            rule=rule,
            mapping=mapping,
            defined_identifiers=defined_identifiers,
        )
        if upstream_issues:
            status = "incomplete_comparable"
            upstream_status = "needs_upstream_encoding"
    else:
        status = "known_not_comparable"
        program = mapping.program or _infer_program_from_legal_id(
            legal_id, rule_name=rule_name
        )
        mapping_type = mapping.mapping_type

    return PolicyEngineCoverageItem(
        legal_id=legal_id,
        repo=repo_name,
        file=file_path,
        rule_name=rule_name,
        kind=kind,
        status=status,
        program=program,
        mapping_type=mapping_type,
        policyengine_variable=mapping.policyengine_variable if mapping else None,
        policyengine_parameter=mapping.policyengine_parameter if mapping else None,
        parameter_key=mapping.parameter_key if mapping else None,
        rationale=mapping.rationale if mapping else None,
        candidate_priority=mapping.candidate_priority if mapping else None,
        tested=test_output_count > 0,
        test_output_count=test_output_count,
        upstream_completeness_status=upstream_status,
        upstream_completeness_issues=upstream_issues,
    )


def _rulespec_defined_identifiers(payload: dict[str, Any]) -> set[str]:
    """Return rule/import names available to formulas in one RuleSpec file."""
    identifiers: set[str] = set()
    raw_imports = payload.get("imports") or []
    if isinstance(raw_imports, list):
        for raw_import in raw_imports:
            if not isinstance(raw_import, str):
                continue
            _, _, output_name = raw_import.partition("#")
            if output_name:
                identifiers.add(output_name.strip())

    raw_rules = payload.get("rules") or []
    if isinstance(raw_rules, list):
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            name = str(rule.get("name") or "").strip()
            if name:
                identifiers.add(name)
    return identifiers


def _direct_mapping_upstream_completeness_issues(
    *,
    rule: dict[str, Any],
    mapping: PolicyEngineMapping,
    defined_identifiers: set[str],
) -> tuple[str, ...]:
    """Flag direct PE mappings that still depend on broad upstream placeholders."""
    if mapping.mapping_type != "direct_variable":
        return ()

    unresolved = sorted(
        identifier
        for identifier in _rule_formula_identifiers(rule)
        if identifier not in defined_identifiers
        and identifier not in _RULESPEC_BUILTIN_IDENTIFIERS
    )
    suspicious = [
        identifier
        for identifier in unresolved
        if _is_upstream_placeholder_identifier(identifier)
    ]
    if not suspicious:
        return ()
    return tuple(
        "Direct PolicyEngine mapping depends on unresolved upstream placeholder "
        f"`{identifier}`; encode/import the primary source for that dependency "
        "before treating this output as comparable."
        for identifier in suspicious
    )


def _rule_formula_identifiers(rule: dict[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    versions = rule.get("versions") or []
    if not isinstance(versions, list):
        return identifiers
    for version in versions:
        if not isinstance(version, dict):
            continue
        formula = version.get("formula")
        if formula is None:
            continue
        text = _QUOTED_STRING_RE.sub(" ", str(formula))
        identifiers.update(_FORMULA_IDENTIFIER_RE.findall(text))
    return identifiers


def _is_upstream_placeholder_identifier(identifier: str) -> bool:
    lowered = identifier.lower()
    return any(pattern.search(lowered) for pattern in _UPSTREAM_PLACEHOLDER_PATTERNS)


def _is_interval_bound_helper_rule(rule_name: str, rule: dict[str, Any]) -> bool:
    """Identify generated indexed table-bound helpers that are not PE outputs."""
    if str(rule.get("kind") or "").strip() != "parameter":
        return False
    if not rule.get("indexed_by"):
        return False
    return bool(_INTERVAL_BOUND_HELPER_RE.search(rule_name))


def _program_filter_values(program: str) -> frozenset[str]:
    if program == "health":
        return _HEALTH_PROGRAMS | {"health"}
    return frozenset({program})


def _infer_program_from_legal_id(legal_id: str, *, rule_name: str = "") -> str:
    lowered = legal_id.lower()
    rule = rule_name.lower()
    if lowered.startswith(
        (
            "uk:statutes/ukpga/2007/3/23",
            "uk:statutes/ukpga/2007/3/35",
        )
    ):
        return "tax"
    if lowered.startswith("nz:statutes/income_tax/"):
        return "tax"
    if lowered.startswith("uk:regulations/uksi/2006/965/2"):
        return "child_benefit"
    if lowered.startswith("uk:policies/govuk/child-benefit"):
        return "child_benefit"
    if lowered.startswith("uk:policies/govuk/state-pension"):
        return "state_pension"
    if lowered.startswith("uk:regulations/uksi/2002/1792/6"):
        return "pension_credit"
    if lowered.startswith("uk:regulations/uksi/2013/376/36"):
        return "universal_credit"
    if _is_combined_health_source(lowered):
        return _infer_health_program_from_rule_name(rule)
    if _PROGRAM_TOKEN_RE["medicaid"].search(lowered):
        return "medicaid"
    if _PROGRAM_TOKEN_RE["chip"].search(lowered):
        return "chip"
    if _PROGRAM_TOKEN_RE["aca"].search(lowered) or "premium_tax_credit" in lowered:
        return "aca_ptc"
    if lowered.startswith("us:statutes/26/36b"):
        return "aca_ptc"
    if lowered.startswith("us-ga:policies/decal/caps/"):
        return "ccap"
    if "snap" in lowered:
        return "snap"
    if lowered.startswith(("us:statutes/42/1382", "us:statutes/42/1382f")):
        return "ssi"
    if (
        lowered.startswith("us:statutes/26/")
        or lowered.startswith("us-co:statutes/39/")
        or lowered.startswith("us:policies/irs/")
        or lowered.startswith("us:policies/ssa/")
    ):
        return "tax"
    return "unknown"


def _is_combined_health_source(lowered_legal_id: str) -> bool:
    return bool(
        "medicaid-chip" in lowered_legal_id
        or "medicaid_chip" in lowered_legal_id
        or (
            _PROGRAM_TOKEN_RE["medicaid"].search(lowered_legal_id)
            and _PROGRAM_TOKEN_RE["chip"].search(lowered_legal_id)
            and ("bhp" in lowered_legal_id or "eligibility" in lowered_legal_id)
        )
    )


def _infer_health_program_from_rule_name(rule_name: str) -> str:
    if _PROGRAM_TOKEN_RE["chip"].search(rule_name):
        return "chip"
    if _PROGRAM_TOKEN_RE["medicaid"].search(rule_name):
        return "medicaid"
    if _PROGRAM_TOKEN_RE["aca"].search(rule_name) or "premium_tax_credit" in rule_name:
        return "aca_ptc"
    return "health"
