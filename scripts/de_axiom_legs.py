#!/usr/bin/env python3
"""Build the pinned DE Axiom pair legs, including honest pending records.

The registered legs are one population x one oracle x one jurisdiction each.
This producer inspects the object database at the exact RuleSpec commit named
in both leg configs; it never reads module bytes from checkout HEAD.  Until a
compared output's complete dependency set is present, its view is emitted as
``state: leg-pending`` with ``pending: module-not-on-main`` and no comparison
values.  Once the signed EStG 66 module and apply manifest exist, this pending
producer fails loudly so the live executable/oracle producer must take over.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.suites.de_worker import DE_WORKER_OUTPUTS  # noqa: E402
from scripts import de_unified_comparison  # noqa: E402

PLAN_PATH = (
    REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "output-dependencies.json"
)
PLAN_RELPATH = PLAN_PATH.relative_to(REPO_ROOT).as_posix()
CONFIG_PATHS = {
    "euromod": REPO_ROOT / "comparisons" / "de-worker-dual-oracle-axiom-euromod.yaml",
    "gettsim": REPO_ROOT / "comparisons" / "de-worker-dual-oracle-axiom-gettsim.yaml",
}
OUTPUT_PATHS = {
    "euromod": (
        REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "axiom-euromod.json"
    ),
    "gettsim": (
        REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "axiom-gettsim.json"
    ),
}
SUITES = {
    "euromod": "de-worker-dual-oracle-axiom-euromod",
    "gettsim": "de-worker-dual-oracle-axiom-gettsim",
}
LEG_IDS = {"euromod": "axiom-euromod", "gettsim": "axiom-gettsim"}
RULESPEC_REPOSITORY = "TheAxiomFoundation/rulespec-de"
RULESPEC_REMOTE = "https://github.com/TheAxiomFoundation/rulespec-de.git"
RECORD_SCHEMA = "axiom.unified_comparison_record.v1"
PLAN_SCHEMA = "axiom_oracles.de_axiom_output_dependency_plan.v1"
PENDING_STATE = "leg-pending"
PENDING_MARKER = "module-not-on-main"
RUNNER_TYPE = "de-axiom-oracle-compare"
PRODUCER = "scripts/de_axiom_legs.py::build"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DEAxiomLegError(ValueError):
    """The pinned inputs cannot support the requested DE pair record."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _serialized(record: dict[str, Any]) -> str:
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DEAxiomLegError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DEAxiomLegError(f"{label} must contain an object")
    return value


def _load_yaml_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DEAxiomLegError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DEAxiomLegError(f"{label} must contain an object")
    return value


def _safe_repo_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DEAxiomLegError(f"{label} must be a non-empty repo-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise DEAxiomLegError(f"{label} must be a normalized repo-relative path")
    return value


def _load_plan() -> dict[str, Any]:
    plan = _load_object(PLAN_PATH, "DE output dependency plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise DEAxiomLegError("DE output dependency plan schema changed")
    if plan.get("suite") != "de-worker-dual-oracle" or plan.get("period") != "2025":
        raise DEAxiomLegError("DE output dependency plan identity changed")
    outputs = plan.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 6:
        raise DEAxiomLegError("DE output dependency plan must contain six outputs")
    expected_concepts = list(DE_WORKER_OUTPUTS)
    concepts: list[str] = []
    view_ids: list[str] = []
    for index, output in enumerate(outputs):
        if not isinstance(output, dict):
            raise DEAxiomLegError(f"dependency output {index} must be an object")
        view_id = output.get("view_id")
        concept = output.get("concept")
        if not isinstance(view_id, str) or not view_id:
            raise DEAxiomLegError(f"dependency output {index} lacks view_id")
        if not isinstance(concept, str) or not concept:
            raise DEAxiomLegError(f"dependency output {index} lacks concept")
        view_ids.append(view_id)
        concepts.append(concept)
        roots = output.get("target_root_nodes")
        if not isinstance(roots, list) or not roots or any(
            not isinstance(root, str) or not root for root in roots
        ):
            raise DEAxiomLegError(f"{view_id}: target_root_nodes are malformed")
        targets = output.get("oracle_targets")
        if not isinstance(targets, dict) or set(targets) != set(CONFIG_PATHS):
            raise DEAxiomLegError(f"{view_id}: both oracle targets are required")
        artifacts = output.get("required_artifacts")
        if not isinstance(artifacts, list):
            raise DEAxiomLegError(f"{view_id}: required_artifacts must be an array")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise DEAxiomLegError(f"{view_id}: artifact must be an object")
            _safe_repo_path(artifact.get("path"), f"{view_id} artifact path")
            if not isinstance(artifact.get("role"), str) or not artifact["role"]:
                raise DEAxiomLegError(f"{view_id}: artifact role is required")
            if not isinstance(artifact.get("nodes"), list):
                raise DEAxiomLegError(f"{view_id}: artifact nodes must be an array")
        if not isinstance(output.get("module_artifact_closure_declared_complete"), bool):
            raise DEAxiomLegError(f"{view_id}: dependency closure flag is required")
        if not isinstance(output.get("missing_dependency_roles"), list):
            raise DEAxiomLegError(f"{view_id}: missing roles must be an array")
    if concepts != expected_concepts:
        raise DEAxiomLegError("dependency plan output order differs from DE_WORKER_OUTPUTS")
    if len(set(view_ids)) != len(view_ids):
        raise DEAxiomLegError("dependency plan view ids must be unique")
    if "de/kindergeld" not in view_ids:
        raise DEAxiomLegError("dependency plan lacks the de/kindergeld view")
    return plan


def _load_config(oracle: str, plan: dict[str, Any]) -> dict[str, Any]:
    if oracle not in CONFIG_PATHS:
        raise DEAxiomLegError(f"unknown DE oracle {oracle!r}")
    config = _load_yaml_object(CONFIG_PATHS[oracle], f"{oracle} leg config")
    expected_name = SUITES[oracle]
    if CONFIG_PATHS[oracle].stem != expected_name or config.get("name") != expected_name:
        raise DEAxiomLegError(f"{oracle}: config filename/name must be {expected_name!r}")
    runner = config.get("runner")
    params = runner.get("parameters") if isinstance(runner, dict) else None
    if not isinstance(runner, dict) or runner.get("type") != RUNNER_TYPE:
        raise DEAxiomLegError(f"{oracle}: runner type must be {RUNNER_TYPE!r}")
    if not isinstance(params, dict) or params.get("oracle") != oracle:
        raise DEAxiomLegError(f"{oracle}: runner oracle changed")
    if params.get("suite") != expected_name:
        raise DEAxiomLegError(f"{oracle}: runner suite changed")
    if params.get("rulespec_remote") != RULESPEC_REMOTE:
        raise DEAxiomLegError(f"{oracle}: rulespec remote changed")
    if params.get("output_dependency_plan") != PLAN_RELPATH:
        raise DEAxiomLegError(f"{oracle}: dependency plan path changed")
    if params.get("concepts") != [row["concept"] for row in plan["outputs"]]:
        raise DEAxiomLegError(f"{oracle}: configured concepts differ from the plan")
    commit = params.get("rulespec_upstream_sha")
    tree = params.get("rulespec_upstream_tree")
    if not isinstance(commit, str) or not SHA1_RE.fullmatch(commit):
        raise DEAxiomLegError(f"{oracle}: rulespec_upstream_sha must be a full SHA")
    if not isinstance(tree, str) or not SHA1_RE.fullmatch(tree):
        raise DEAxiomLegError(f"{oracle}: rulespec_upstream_tree must be a full SHA")
    expected_output = OUTPUT_PATHS[oracle].relative_to(REPO_ROOT).as_posix()
    if (config.get("artifacts") or {}).get("canonical_record") != expected_output:
        raise DEAxiomLegError(f"{oracle}: canonical_record path changed")
    if (config.get("selector") or {}).get("report") != expected_output:
        raise DEAxiomLegError(f"{oracle}: selector report path changed")
    return config


def _shared_contract(oracle: str) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    plan = _load_plan()
    configs = {name: _load_config(name, plan) for name in CONFIG_PATHS}
    pins = {
        (
            config["runner"]["parameters"]["rulespec_upstream_sha"],
            config["runner"]["parameters"]["rulespec_upstream_tree"],
        )
        for config in configs.values()
    }
    if len(pins) != 1:
        raise DEAxiomLegError("DE Axiom leg configs must share one commit/tree pin")
    commit, tree = pins.pop()
    return plan, configs[oracle], commit, tree


def _resolve_rulespec_root(config: dict[str, Any], override: Path | None) -> Path:
    if override is not None:
        root = override.expanduser().resolve()
    else:
        env_override = os.environ.get("RULESPEC_DE_REPO")
        raw = env_override or config["runner"]["parameters"].get("rulespec_root")
        if not isinstance(raw, str) or not raw:
            raise DEAxiomLegError("rulespec_root is not configured")
        root = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
    if not root.is_dir():
        raise DEAxiomLegError(f"rulespec-de checkout does not exist: {root}")
    return root


def _available_rulespec_root(
    config: dict[str, Any], override: Path | None
) -> Path | None:
    """Return an inspectable checkout, or None in a hermetic validation run.

    An explicit override is authoritative and fails loudly when absent.  The
    configured sibling checkout is optional while validating committed
    artifacts because ordinary CI and refresh clones contain only this repo.
    """

    if override is not None:
        return _resolve_rulespec_root(config, override)
    env_override = os.environ.get("RULESPEC_DE_REPO")
    raw = env_override or config["runner"]["parameters"].get("rulespec_root")
    if not isinstance(raw, str) or not raw:
        return None
    root = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
    return root if root.is_dir() else None


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=not binary,
        )
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", b"" if binary else "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        detail = str(stderr).strip()
        suffix = f": {detail}" if detail else ""
        raise DEAxiomLegError(f"git {' '.join(args)} failed{suffix}") from exc
    return result.stdout


def inspect_pinned_ref(
    oracle: str,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Any]:
    """Inspect only the configured commit object, ignoring checkout HEAD."""

    plan, config, commit, expected_tree = _shared_contract(oracle)
    root = _resolve_rulespec_root(config, rulespec_root)
    try:
        resolved_commit = str(
            _git(root, "rev-parse", f"{commit}^{{commit}}")
        ).strip()
    except DEAxiomLegError:
        # CI materializes mapped rulespec repos with --depth 1.  A reviewed pin
        # can intentionally trail moving main, so fetch that one exact object
        # rather than inspecting or checking out the unrelated shallow HEAD.
        _git(root, "fetch", "--quiet", "--depth", "1", RULESPEC_REMOTE, commit)
        resolved_commit = str(
            _git(root, "rev-parse", f"{commit}^{{commit}}")
        ).strip()
    if resolved_commit != commit:
        raise DEAxiomLegError(
            f"configured RuleSpec commit resolved to {resolved_commit}, expected {commit}"
        )
    resolved_tree = str(_git(root, "rev-parse", f"{commit}^{{tree}}")).strip()
    if resolved_tree != expected_tree:
        raise DEAxiomLegError(
            f"pinned RuleSpec tree is {resolved_tree}, expected {expected_tree}"
        )

    artifact_paths = sorted(
        {
            artifact["path"]
            for output in plan["outputs"]
            for artifact in output["required_artifacts"]
        }
    )
    observations: list[dict[str, Any]] = []
    for artifact_path in artifact_paths:
        listing = str(
            _git(
                root,
                "ls-tree",
                "-r",
                "--name-only",
                commit,
                "--",
                artifact_path,
            )
        ).splitlines()
        present = artifact_path in listing
        observation: dict[str, Any] = {
            "path": artifact_path,
            "presence": "on-pinned-ref" if present else PENDING_MARKER,
        }
        if present:
            content = _git(root, "show", f"{commit}:{artifact_path}", binary=True)
            assert isinstance(content, bytes)
            observation["sha256"] = hashlib.sha256(content).hexdigest()
        observations.append(observation)
    return {
        "repository": RULESPEC_REPOSITORY,
        "commit": commit,
        "tree": resolved_tree,
        "inspection_mode": "git-object-database-exact-ref",
        "checkout_head_ignored": True,
        "artifacts": observations,
        "claim_mode": "computed",
    }


def _view(
    output: dict[str, Any],
    oracle: str,
    leg_id: str,
    observations: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    artifacts = []
    for declared in output["required_artifacts"]:
        observed = copy.deepcopy(observations[declared["path"]])
        observed.update(
            {
                "kind": declared.get("kind"),
                "role": declared["role"],
                "nodes": copy.deepcopy(declared["nodes"]),
                "dependency_status": (
                    "missing"
                    if observed["presence"] != "on-pinned-ref"
                    else (
                        "required"
                        if output["module_artifact_closure_declared_complete"]
                        else "available-partial"
                    )
                ),
            }
        )
        artifacts.append(observed)
    complete_on_ref = bool(artifacts) and bool(
        output["module_artifact_closure_declared_complete"]
    ) and all(row["presence"] == "on-pinned-ref" for row in artifacts)
    missing_roles = list(output["missing_dependency_roles"])
    missing_roles.extend(
        row["role"] for row in artifacts if row["presence"] != "on-pinned-ref"
    )
    view = {
        "kind": "subgraph",
        "scope": "amount",
        "leg_id": leg_id,
        "state": PENDING_STATE,
        "pending": PENDING_MARKER,
        "columns": [output["concept"]],
        "target_root_nodes": copy.deepcopy(output["target_root_nodes"]),
        "oracle_target": copy.deepcopy(output["oracle_targets"][oracle]),
        "dependency_set": {
            "module_artifacts_declared_complete": output["module_artifact_closure_declared_complete"],
            "complete_on_pinned_ref": complete_on_ref,
            "artifacts": artifacts,
            "available_partial_dependencies": [
                row["path"]
                for row in artifacts
                if row["dependency_status"] == "available-partial"
            ],
            "missing_dependency_roles": missing_roles,
            "claim_mode": "computed",
        },
        "claim_mode": "computed",
    }
    return view, complete_on_ref


def _pending_record_from_inspection(
    oracle: str,
    plan: dict[str, Any],
    inspection: dict[str, Any],
) -> dict[str, Any]:
    """Build the pending record after validating its exact-ref observation."""

    observations = {row["path"]: row for row in inspection["artifacts"]}
    leg_id = LEG_IDS[oracle]
    views: dict[str, Any] = {}
    live_ready: list[str] = []
    for output in plan["outputs"]:
        view, complete_on_ref = _view(output, oracle, leg_id, observations)
        views[output["view_id"]] = view
        if complete_on_ref:
            live_ready.append(output["view_id"])
    if live_ready:
        raise DEAxiomLegError(
            "execution-environment-unavailable: pinned RuleSpec dependency "
            f"closure is present for {live_ready}; refusing to emit "
            f"{PENDING_MARKER!r}. Run scripts/de_executable.py with the "
            "released engine, live oracle, and signing inputs instead."
        )

    try:
        source = de_unified_comparison.build(include_axiom_legs=False)
    except (OSError, ValueError) as exc:
        raise DEAxiomLegError(f"cannot rederive the canonical DE population: {exc}") from exc
    source_tuple = source.get("tuple")
    population = source_tuple.get("population") if isinstance(source_tuple, dict) else None
    source_oracles = source_tuple.get("oracles") if isinstance(source_tuple, dict) else None
    source_cases = source.get("cases")
    if (
        not isinstance(population, dict)
        or population.get("case_count") != 13
        or not isinstance(source_oracles, dict)
        or not isinstance(source_oracles.get(oracle), dict)
        or not isinstance(source_cases, list)
        or len(source_cases) != 13
    ):
        raise DEAxiomLegError("canonical DE source tuple is incomplete")

    return {
        "record_schema": RECORD_SCHEMA,
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITES[oracle],
        "period": "2025",
        "state": PENDING_STATE,
        "pending": PENDING_MARKER,
        "engines": {"left": oracle, "right": "axiom"},
        "tuple": {
            "jurisdiction": "de",
            "population": copy.deepcopy(population),
            "oracle": {"id": oracle, **copy.deepcopy(source_oracles[oracle])},
            "axiom": copy.deepcopy(de_unified_comparison.AXIOM_ENGINE_PIN),
            "rulespec": {
                "repository": RULESPEC_REPOSITORY,
                "commit": inspection["commit"],
                "tree": inspection["tree"],
                "claim_mode": "computed",
            },
        },
        "population": population.get("id"),
        "dataset_identity": {
            "sha256": population.get("sha256"),
            "claim_mode": "computed",
        },
        "cases": copy.deepcopy(source_cases),
        "views": views,
        "provenance": {
            "generated_by": PRODUCER,
            "generation_mode": "exact-pinned-ref-dependency-inspection",
            "rulespecs": [
                {"repo": RULESPEC_REPOSITORY, "sha": inspection["commit"]}
            ],
            "rulespec_ref_inspection": inspection,
            "claim_mode": "computed",
        },
    }


def _validate_inspection(
    inspection: object,
    *,
    plan: dict[str, Any],
    commit: str,
    tree: str,
) -> dict[str, Any]:
    if not isinstance(inspection, dict):
        raise DEAxiomLegError("pending record lacks RuleSpec ref inspection")
    expected_header = {
        "repository": RULESPEC_REPOSITORY,
        "commit": commit,
        "tree": tree,
        "inspection_mode": "git-object-database-exact-ref",
        "checkout_head_ignored": True,
        "claim_mode": "computed",
    }
    for field, expected in expected_header.items():
        if inspection.get(field) != expected:
            raise DEAxiomLegError(f"RuleSpec ref inspection {field} changed")
    expected_paths = sorted(
        {
            artifact["path"]
            for output in plan["outputs"]
            for artifact in output["required_artifacts"]
        }
    )
    rows = inspection.get("artifacts")
    if not isinstance(rows, list) or [
        row.get("path") if isinstance(row, dict) else None for row in rows
    ] != expected_paths:
        raise DEAxiomLegError("RuleSpec ref inspection artifact inventory changed")
    for row in rows:
        assert isinstance(row, dict)
        presence = row.get("presence")
        if presence == "on-pinned-ref":
            if set(row) != {"path", "presence", "sha256"} or not isinstance(
                row.get("sha256"), str
            ) or not SHA256_RE.fullmatch(row["sha256"]):
                raise DEAxiomLegError(
                    f"{row['path']}: present artifact needs an exact SHA-256"
                )
        elif presence == PENDING_MARKER:
            if set(row) != {"path", "presence"}:
                raise DEAxiomLegError(
                    f"{row['path']}: absent artifact cannot carry invented bytes"
                )
        else:
            raise DEAxiomLegError(f"{row['path']}: invalid ref presence marker")
    return inspection


def build(
    oracle: str,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Any]:
    """Build one deterministic pending unified pair record."""

    plan, _config, commit, tree = _shared_contract(oracle)
    inspection = inspect_pinned_ref(oracle, rulespec_root=rulespec_root)
    _validate_inspection(inspection, plan=plan, commit=commit, tree=tree)
    return _pending_record_from_inspection(oracle, plan, inspection)


def validate(
    record: dict[str, Any],
    oracle: str,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Any]:
    """Validate pending evidence, re-inspecting the pin when available."""

    if not isinstance(record, dict):
        raise DEAxiomLegError("DE Axiom leg record must be an object")
    plan, config, commit, tree = _shared_contract(oracle)
    provenance = record.get("provenance")
    inspection = (
        provenance.get("rulespec_ref_inspection")
        if isinstance(provenance, dict)
        else None
    )
    inspection = _validate_inspection(
        inspection, plan=plan, commit=commit, tree=tree
    )
    expected = _pending_record_from_inspection(oracle, plan, inspection)
    if record != expected:
        raise DEAxiomLegError(
            f"{LEG_IDS[oracle]} pending record differs from exact pinned-ref derivation"
        )
    available_root = (
        _available_rulespec_root(config, rulespec_root)
        if rulespec_root is not None
        else None
    )
    if available_root is not None:
        exact = build(oracle, rulespec_root=available_root)
        if record != exact:
            raise DEAxiomLegError(
                f"{LEG_IDS[oracle]} pending record differs from exact pinned-ref "
                "object-database inspection"
            )
    return record


def complete_view_scaffolds(
    oracle: str,
    inspection: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return all six dependency-bound views for a live complete pair leg.

    Only Kindergeld is currently declared as a complete dependency closure.
    Its scaffold is promoted by the live producer with comparison rows,
    summary, and replay fixture; the other five remain honest pending views.
    """

    plan, _config, commit, tree = _shared_contract(oracle)
    inspection = _validate_inspection(
        inspection, plan=plan, commit=commit, tree=tree
    )
    observations = {row["path"]: row for row in inspection["artifacts"]}
    result: dict[str, dict[str, Any]] = {}
    ready: list[str] = []
    for output in plan["outputs"]:
        view, complete_on_ref = _view(
            output, oracle, LEG_IDS[oracle], observations
        )
        result[output["view_id"]] = view
        if complete_on_ref:
            ready.append(output["view_id"])
    if ready != ["de/kindergeld"]:
        raise DEAxiomLegError(
            "live DE pair production requires exactly the Kindergeld dependency "
            f"closure, found {ready}"
        )
    return result


def validate_complete_views(
    record: dict[str, Any],
    oracle: str,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Any]:
    """Validate the six-view module plan around a live Kindergeld result."""

    if record.get("state") != "complete" or record.get("schema_version") != (
        "axiom.comparison_report.v2"
    ):
        raise DEAxiomLegError(f"{LEG_IDS[oracle]} complete record state changed")
    provenance = record.get("provenance")
    inspection = (
        provenance.get("rulespec_ref_inspection")
        if isinstance(provenance, dict)
        else None
    )
    scaffolds = complete_view_scaffolds(oracle, inspection)
    observed_artifacts = {
        row["path"]: row for row in inspection["artifacts"]
    }
    rulespec_artifact = provenance.get("rulespec_artifact")
    if not isinstance(rulespec_artifact, dict):
        raise DEAxiomLegError("complete record lacks signed RuleSpec binding")
    expected_binding = {
        "citation_path": "de/statute/estg/66",
        "commit": inspection["commit"],
        "tree": inspection["tree"],
        "artifact_sha256": observed_artifacts[
            "de/statutes/estg/66.yaml"
        ].get("sha256"),
        "apply_manifest_sha256": observed_artifacts[
            ".axiom/encoding-manifests/de/statutes/estg/66.json"
        ].get("sha256"),
        "claim_mode": "computed",
    }
    if rulespec_artifact != expected_binding:
        raise DEAxiomLegError(
            "complete record dependency inspection and signed binding differ"
        )
    _plan, config, _commit, _tree = _shared_contract(oracle)
    available_root = (
        _available_rulespec_root(config, rulespec_root)
        if rulespec_root is not None
        else None
    )
    if available_root is not None:
        observed_inspection = inspect_pinned_ref(
            oracle, rulespec_root=available_root
        )
        if inspection != observed_inspection:
            raise DEAxiomLegError(
                f"{LEG_IDS[oracle]} ref inspection differs from pinned git objects"
            )
    views = record.get("views")
    if not isinstance(views, dict) or set(views) != set(scaffolds):
        raise DEAxiomLegError(f"{LEG_IDS[oracle]} six-view inventory changed")
    for view_id, expected in scaffolds.items():
        observed = views[view_id]
        if view_id == "de/kindergeld":
            if not isinstance(observed, dict):
                raise DEAxiomLegError("complete Kindergeld view must be an object")
            for field in (
                "oracle_target",
                "target_root_nodes",
                "dependency_set",
            ):
                if observed.get(field) != expected[field]:
                    raise DEAxiomLegError(
                        f"complete Kindergeld {field} dependency evidence changed"
                    )
            if observed.get("state") != "complete" or "pending" in observed:
                raise DEAxiomLegError("complete Kindergeld view retained pending state")
        elif observed != expected:
            raise DEAxiomLegError(f"{view_id}: pending dependency view changed")
    tuple_ = record.get("tuple")
    expected_rulespec = {
        "repository": RULESPEC_REPOSITORY,
        "commit": inspection["commit"],
        "tree": inspection["tree"],
        "claim_mode": "computed",
    }
    if not isinstance(tuple_, dict) or tuple_.get("rulespec") != expected_rulespec:
        raise DEAxiomLegError(f"{LEG_IDS[oracle]} tuple RuleSpec pin changed")
    population = tuple_.get("population")
    if (
        not isinstance(population, dict)
        or record.get("population") != population.get("id")
        or record.get("dataset_identity")
        != {"sha256": population.get("sha256"), "claim_mode": "computed"}
    ):
        raise DEAxiomLegError(f"{LEG_IDS[oracle]} population identity changed")
    return record


def _validate_complete_record(
    path: Path,
    oracle: str,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Any]:
    """Validate a committed live pair plus its still-pending module views."""

    try:
        source = de_unified_comparison.build(include_axiom_legs=False)
        summary = de_unified_comparison._validate_axiom_leg(
            path,
            leg_id=LEG_IDS[oracle],
            population_sha256=source["tuple"]["population"]["sha256"],
            population_cases=source["cases"],
            expected_oracle=de_unified_comparison.ORACLE_PINS[oracle],
            expected_household_sum=de_unified_comparison.EXPECTED_HOUSEHOLD_SUM,
        )
    except (OSError, ValueError, KeyError) as exc:
        raise DEAxiomLegError(f"{LEG_IDS[oracle]} complete record is invalid: {exc}") from exc
    record = _load_object(path, f"{oracle} complete pair record")
    validate_complete_views(record, oracle, rulespec_root=rulespec_root)
    return summary


def write(
    oracle: str | None = None,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Path]:
    """Write one or both canonical pending pair records."""

    selected = [oracle] if oracle is not None else list(CONFIG_PATHS)
    written: dict[str, Path] = {}
    for name in selected:
        target = OUTPUT_PATHS[name]
        _plan, config, _commit, _tree = _shared_contract(name)
        available_root = _available_rulespec_root(config, rulespec_root)
        if available_root is None:
            if not target.is_file():
                raise DEAxiomLegError(
                    f"rulespec-de checkout is unavailable and {target.relative_to(REPO_ROOT)} "
                    "has no committed record to preserve"
                )
            record = _load_object(target, f"{name} pair record")
            if record.get("state") == PENDING_STATE:
                validate(record, name)
            else:
                _validate_complete_record(target, name)
            written[name] = target
            continue
        try:
            record = build(name, rulespec_root=available_root)
        except DEAxiomLegError as exc:
            if "execution-environment-unavailable" not in str(exc):
                raise
            if not target.is_file():
                raise
            existing = _load_object(target, f"{name} complete pair record")
            if existing.get("state") != "complete":
                raise
            _validate_complete_record(
                target, name, rulespec_root=available_root
            )
            written[name] = target
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_serialized(record), encoding="utf-8")
        written[name] = target
    return written


def check(
    oracle: str | None = None,
    *,
    rulespec_root: Path | None = None,
) -> dict[str, Path]:
    """Fail if one or both committed pair records are absent or stale."""

    selected = [oracle] if oracle is not None else list(CONFIG_PATHS)
    checked: dict[str, Path] = {}
    for name in selected:
        target = OUTPUT_PATHS[name]
        try:
            observed = _load_object(target, f"{name} pair record")
        except (OSError, DEAxiomLegError) as exc:
            raise DEAxiomLegError(f"cannot read {target.relative_to(REPO_ROOT)}: {exc}") from exc
        if observed.get("state") == PENDING_STATE:
            _plan, config, _commit, _tree = _shared_contract(name)
            available_root = _available_rulespec_root(config, rulespec_root)
            validate(observed, name, rulespec_root=available_root)
        else:
            _plan, config, _commit, _tree = _shared_contract(name)
            available_root = _available_rulespec_root(config, rulespec_root)
            _validate_complete_record(
                target, name, rulespec_root=available_root
            )
        checked[name] = target
    return checked


def _live_input_path(
    params: dict[str, Any], field: str, *, directory: bool = False
) -> Path:
    raw = params.get(field)
    if not isinstance(raw, str) or not raw:
        raise DEAxiomLegError(f"live transition lacks {field}")
    expanded = os.path.expandvars(os.path.expanduser(raw))
    path = Path(expanded).resolve()
    exists = path.is_dir() if directory else path.is_file()
    if "$" in expanded or not exists:
        kind = "directory" if directory else "file"
        raise DEAxiomLegError(
            "execution-environment-unavailable: signed dependencies are on the "
            f"pinned ref but live {field} {kind} is unavailable ({raw!r}). "
            "Provide the four live paths or run `python scripts/de_executable.py "
            "--run ...`; the leg remains pending and is never counted conformant."
        )
    return path


def _produce_live_bundle(params: dict[str, Any], rulespec_root: Path) -> None:
    """Run the existing released-engine/oracle producer for the first flip."""

    try:
        executable = importlib.import_module("scripts.de_executable")
    except ImportError as exc:
        raise DEAxiomLegError("cannot load DE executable producer") from exc
    try:
        executable.produce(
            engine_archive=_live_input_path(params, "engine_archive"),
            rulespec_root=rulespec_root,
            signing_public_key=_live_input_path(params, "signing_public_key"),
            euromod_model_root=_live_input_path(
                params, "euromod_model_root", directory=True
            ),
            euromod_python=_live_input_path(params, "euromod_python"),
        )
    except (OSError, ValueError) as exc:
        raise DEAxiomLegError(f"live DE evidence production failed: {exc}") from exc


def run_registered_leg(runner: dict[str, Any], output: Path) -> dict[str, Any]:
    """Runner-registry entry point with the standard ``(runner, output)`` API."""

    if not isinstance(runner, dict) or runner.get("type") != RUNNER_TYPE:
        raise DEAxiomLegError(f"registered runner type must be {RUNNER_TYPE!r}")
    params = runner.get("parameters")
    if not isinstance(params, dict):
        raise DEAxiomLegError("registered DE Axiom runner parameters are missing")
    oracle = params.get("oracle")
    if oracle not in CONFIG_PATHS:
        raise DEAxiomLegError(f"registered DE Axiom oracle is invalid: {oracle!r}")
    _plan, config, commit, tree = _shared_contract(oracle)
    expected_params = config["runner"]["parameters"]
    for field in (
        "oracle",
        "suite",
        "output_dependency_plan",
        "rulespec_upstream_sha",
        "rulespec_upstream_tree",
    ):
        if params.get(field) != expected_params.get(field):
            raise DEAxiomLegError(f"registered DE Axiom runner changed {field}")
    raw_root = params.get("rulespec_root")
    if not isinstance(raw_root, str) or not raw_root:
        raise DEAxiomLegError("registered DE Axiom runner lacks rulespec_root")
    root = Path(os.path.expandvars(os.path.expanduser(raw_root))).resolve()
    try:
        record = build(oracle, rulespec_root=root)
    except DEAxiomLegError as exc:
        if "execution-environment-unavailable" not in str(exc):
            raise
        canonical = OUTPUT_PATHS[oracle]
        if canonical.is_file():
            existing = _load_object(canonical, f"{oracle} pair record")
        else:
            existing = {}
        if existing.get("state") != "complete":
            _produce_live_bundle(params, root)
        _validate_complete_record(canonical, oracle, rulespec_root=root)
        record = _load_object(canonical, f"{oracle} complete pair record")
    # run_comparison consumes this only after this producer verified both the
    # commit object and its configured tree; it may therefore stamp the pin
    # rather than the checkout's unrelated moving HEAD.
    params["_verified_rulespec_upstream_sha"] = commit
    params["_verified_rulespec_upstream_tree"] = tree
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_serialized(record), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle", choices=[*CONFIG_PATHS, "all"], default="all")
    parser.add_argument("--rulespec-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    oracle = None if args.oracle == "all" else args.oracle
    try:
        action = check if args.check else write
        paths = action(oracle, rulespec_root=args.rulespec_root)
    except DEAxiomLegError as exc:
        raise SystemExit(str(exc)) from exc
    verb = "Verified" if args.check else "Wrote"
    for path in paths.values():
        print(f"{verb}: {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
