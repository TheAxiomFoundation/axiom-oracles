#!/usr/bin/env python3
"""Generate the computed node-certification ledger and refusal queue.

Program-level truth comes from ``scripts/certify.py`` and its committed
certificates.  This adapter maps an explicit public-node candidate surface into
those registered programs, verifies exact program-graph membership, and then
projects the five ops criteria without promoting missing evidence.

The expected state today is successful generation with zero certified nodes:
engine #136 has not produced per-node provision provenance.  Refused
candidates are normal output, not a process failure.

Modes::

    python3 scripts/certify_nodes.py
    python3 scripts/certify_nodes.py --check
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_SCHEMA = "axiom_oracles.node_candidates.v1"
LEDGER_SCHEMA = "axiom.certified_nodes.v1"
REFUSAL_SCHEMA = "axiom_oracles.node_certification_refusals.v1"
VALIDATION_EVIDENCE_FORMAT = "axiom-validation-evidence/1"
CERTIFICATE_SCHEMA = "axiom_oracles.program_certificate.v1"
CRITERIA = (
    "provision_rooted",
    "conformant",
    "exercised",
    "closed",
    "executable",
)
EXECUTABLE_TIERS = ("source_reproduction", "release_receipt")
SOURCE_REPRODUCTION_PRODUCERS = {
    "scripts/executable_reproduction.py",
    "scripts/nz_executable_reproduction.py",
    "scripts/tariff_executable_reproduction.py",
}
RELEASE_RECEIPT_PRODUCERS = {
    "axiom_oracles/executable_receipt.py",
    "scripts/produce_executable_receipt.py",
}
SHARED_EXECUTABLE_RECEIPT_SCHEMA = "axiom_oracles.executable_receipt.v2"
RELEASE_TIER_PROGRAMS = {"us-co/snap"}
COMPILED_PROGRAM_ARTIFACTS = {
    "us-co/snap": "axiom_oracles/adapters/axiom/artifacts/co-snap.compiled.json",
}
PROVENANCE_PRODUCER = "TheAxiomFoundation/axiom-rules-engine#136"
RELEASE_RECEIPT_PRODUCER = "TheAxiomFoundation/axiom-oracles#461"
DEFAULT_CANDIDATES = Path("node-candidates.yaml")
DEFAULT_LEDGER = Path("certified-nodes.yaml")
DEFAULT_REFUSALS = Path("certified-node-refusals.json")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CertificationError(ValueError):
    """The producer graph or committed generated artifacts are invalid."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _repo_path(repo_root: Path, relative: object, *, label: str) -> Path:
    if not _nonempty(relative):
        raise CertificationError(f"{label} must be a non-empty repository path")
    posix = PurePosixPath(str(relative))
    if posix.is_absolute() or ".." in posix.parts:
        raise CertificationError(f"{label} must be repository-relative: {relative!r}")
    path = repo_root.joinpath(*posix.parts).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:  # pragma: no cover - defense beyond lexical check
        raise CertificationError(f"{label} escapes the repository") from exc
    return path


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CertificationError(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CertificationError(f"{label} must contain a JSON object")
    return value


def _read_yaml(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CertificationError(f"{label} is not readable YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise CertificationError(f"{label} must contain a YAML mapping")
    return value


def _load_module(repo_root: Path, relative: str, *, purpose: str) -> ModuleType:
    path = _repo_path(repo_root, relative, label=purpose)
    if not path.is_file():
        raise CertificationError(f"{purpose} is missing: {relative}")
    name = f"_certify_nodes_{path.stem}_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise CertificationError(f"cannot import {purpose}: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    spec.loader.exec_module(module)
    return module


def _refusal(
    criterion: str,
    code: str,
    message: str,
    *,
    producer: str | None = None,
) -> dict[str, Any]:
    return {
        "criterion": criterion,
        "code": code,
        **({"producer": producer} if producer else {}),
        "message": message,
    }


def _criterion(holds: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {"holds": holds, "evidence": dict(evidence)}


def load_candidate_registry(
    repo_root: Path,
    relative: Path = DEFAULT_CANDIDATES,
) -> tuple[dict[str, Any], Path]:
    path = _repo_path(repo_root, relative.as_posix(), label="candidate registry")
    document = _read_yaml(path, label=str(relative))
    if document.get("schema") != CANDIDATE_SCHEMA:
        raise CertificationError(f"{relative} must use schema {CANDIDATE_SCHEMA!r}")
    programs = document.get("programs")
    candidates = document.get("candidates")
    if not isinstance(programs, dict) or not programs:
        raise CertificationError(f"{relative}: programs must be a non-empty mapping")
    if not isinstance(candidates, list) or not candidates:
        raise CertificationError(f"{relative}: candidates must be a non-empty list")

    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        label = f"{relative} candidates[{index}]"
        if not isinstance(candidate, dict):
            raise CertificationError(f"{label} must be a mapping")
        node = candidate.get("node")
        program = candidate.get("program")
        if not _nonempty(node) or "#" not in str(node):
            raise CertificationError(f"{label}.node must be an exact legal node id")
        if node in seen:
            raise CertificationError(f"{relative}: duplicate candidate {node!r}")
        seen.add(str(node))
        if not _nonempty(program) or program not in programs:
            raise CertificationError(f"{label}.program is not declared in programs")
        for field in ("label", "provision", "selection_basis"):
            if not _nonempty(candidate.get(field)):
                raise CertificationError(f"{label}.{field} must be non-empty")

    for program, config in programs.items():
        if not _nonempty(program) or not isinstance(config, dict):
            raise CertificationError(f"{relative}: invalid program configuration")
        membership = config.get("membership")
        closure = config.get("closure")
        executable = config.get("executable")
        if not isinstance(membership, dict) or membership.get("adapter") not in {
            "closure_ledger_rule",
            "compiled_program_node",
        }:
            raise CertificationError(
                f"{relative}: {program} has invalid membership adapter"
            )
        if not isinstance(closure, dict) or closure.get("adapter") not in {
            "certificate",
            "co_closure_universes",
        }:
            raise CertificationError(
                f"{relative}: {program} has invalid closure adapter"
            )
        required = (
            executable.get("required_tier") if isinstance(executable, dict) else None
        )
        if required not in EXECUTABLE_TIERS:
            raise CertificationError(
                f"{relative}: {program} executable.required_tier must be one of "
                f"{EXECUTABLE_TIERS}"
            )
    return document, path


def _load_program_certificates(
    repo_root: Path,
    programs: Sequence[str],
) -> tuple[ModuleType, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    certify = _load_module(
        repo_root,
        "scripts/certify.py",
        purpose="program certificate producer",
    )
    registry = getattr(certify, "PROGRAMS", None)
    if not isinstance(registry, dict):
        raise CertificationError("scripts/certify.py exposes no PROGRAMS registry")

    certificates: dict[str, dict[str, Any]] = {}
    specs: dict[str, dict[str, Any]] = {}
    for program in programs:
        spec = registry.get(program)
        if not isinstance(spec, dict):
            raise CertificationError(
                f"candidate program {program!r} is not in PROGRAMS"
            )
        try:
            computed = certify.build_certificate(program, spec)
        except (OSError, RuntimeError, ValueError) as exc:
            raise CertificationError(
                f"program certificate producer failed for {program}: {exc}"
            ) from exc
        relative = Path("certificates") / f"{program.replace('/', '-')}.json"
        path = _repo_path(
            repo_root, relative.as_posix(), label=f"{program} certificate"
        )
        committed = _read_json(path, label=str(relative))
        if (
            committed.get("schema") != CERTIFICATE_SCHEMA
            or committed.get("program") != program
        ):
            raise CertificationError(f"{relative} has the wrong schema or program")
        if committed != computed:
            raise CertificationError(
                f"{relative} drifted from scripts/certify.py; run the program "
                "certificate producer first"
            )
        certificates[program] = committed
        specs[program] = spec
    return certify, certificates, specs


def _certificate_criterion(
    program: str,
    certificate: Mapping[str, Any],
    name: str,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = repo_root / "certificates" / f"{program.replace('/', '-')}.json"
    verdicts = certificate.get("verdicts")
    verdict = verdicts.get(name) if isinstance(verdicts, dict) else None
    if not isinstance(verdict, dict):
        raise CertificationError(f"{program} certificate has no {name} verdict")
    mode = verdict.get("mode")
    value = verdict.get("value")
    evidence: dict[str, Any] = {
        "certificate": path.relative_to(repo_root).as_posix(),
        "certificate_sha256": _sha256(path),
        "mode": mode,
        "value": value,
    }
    if name == "conformant":
        evidence["reference_legs"] = [
            {
                "suite": row.get("suite"),
                "clean": row.get("clean"),
                "binding": row.get("binding"),
                "reconciliation": row.get("reconciliation"),
            }
            for row in verdict.get("reference_legs") or []
            if isinstance(row, dict)
        ]
    elif name == "exercised":
        evidence["census"] = "conformance/exercise-census.json"
        raw_suites = verdict.get("suites") or {}
        if not isinstance(raw_suites, dict):
            raise CertificationError(f"{program} exercised.suites must be a mapping")
        evidence["suites"] = [
            {
                "suite": suite,
                "binding": row.get("binding"),
                "bridge_audited": row.get("bridge_audited"),
                "cases": row.get("cases"),
                "per_case_evidence_committed": row.get("per_case_evidence_committed"),
                "reconciliation": row.get("reconciliation"),
                "varied_fields": row.get("varied_fields"),
            }
            for suite, row in sorted(raw_suites.items())
            if isinstance(row, dict)
        ]
    elif name == "closed":
        evidence.update(
            {
                "artifact": verdict.get("artifact"),
                "status": verdict.get("status"),
                "rulespec_commit": verdict.get("rulespec_commit"),
            }
        )

    holds = mode == "computed" and value is True
    if holds:
        return _criterion(True, evidence), None
    if mode != "computed":
        return _criterion(False, evidence), _refusal(
            name,
            f"{name}.not_computed",
            f"{program} carries {mode or 'no'} {name} evidence; computed evidence is required",
            producer="scripts/certify.py",
        )
    return _criterion(False, evidence), _refusal(
        name,
        f"{name}.computed_false",
        f"{program} has a computed {name}=false verdict",
        producer="scripts/certify.py",
    )


def _co_closure_criterion(
    repo_root: Path,
    program: str,
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    producer_ref = str(config.get("producer") or "scripts/closure_universe.py")
    producer = _load_module(
        repo_root, producer_ref, purpose=f"{program} closure producer"
    )
    closure_dir = _repo_path(
        repo_root,
        str(config.get("directory") or "closure"),
        label=f"{program} closure directory",
    )
    try:
        universes, summary, errors = producer.build_artifacts(
            closure_dir,
            check_citation_drift=True,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise CertificationError(f"{program} closure producer failed: {exc}") from exc
    if errors:
        raise CertificationError(
            f"{program} closure producer refused: {'; '.join(errors)}"
        )
    if not isinstance(summary, dict) or summary.get("program") != program:
        raise CertificationError(f"{program} closure producer returned the wrong scope")

    summary_path = closure_dir / "summary.json"
    if summary_path.read_text(encoding="utf-8") != producer.serialize_summary(summary):
        raise CertificationError(
            "closure/summary.json drifted from closure_universe.py"
        )
    universe_refs: list[dict[str, Any]] = []
    for root, universe in sorted(universes.items()):
        path = closure_dir / "universes" / "us-co-snap" / f"{root}.yaml"
        if path.read_text(encoding="utf-8") != producer.serialize_universe(universe):
            raise CertificationError(
                f"{path.relative_to(repo_root)} drifted from its producer"
            )
        universe_refs.append(
            {
                "root": root,
                "artifact": path.relative_to(repo_root).as_posix(),
                "sha256": _sha256(path),
            }
        )

    roots = summary.get("roots") or []
    pending = sum(
        int((row.get("by_status") or {}).get("pending", 0))
        for row in roots
        if isinstance(row, dict)
    )
    evidence = {
        "producer": producer_ref,
        "summary": summary_path.relative_to(repo_root).as_posix(),
        "summary_sha256": _sha256(summary_path),
        "universes": universe_refs,
        "root_count": len(roots),
        "provision_count": sum(
            int(row.get("total", 0)) for row in roots if isinstance(row, dict)
        ),
        "pending_count": pending,
        "value": summary.get("closed"),
        "certificate_attestation_ignored": True,
    }
    holds = summary.get("closed") is True and pending == 0
    if holds:
        return _criterion(True, evidence), None
    return _criterion(False, evidence), _refusal(
        "closed",
        "closed.computed_open",
        f"{program} closure has {pending} pending provisions across {len(roots)} roots",
        producer=producer_ref,
    )


def recognize_executable_tier(
    producer: object,
    schema: object,
    *,
    declared_tier: object = None,
    contract: object = None,
) -> str | None:
    """Classify a receipt only after its program certificate validated it.

    Current main uses producer-specific source-reproduction v1 documents. The
    pending #461 integration uses a shared v2 envelope whose explicit ``tier``
    discriminator is copied into the computed certificate verdict. The older
    #461 release-only branch used receipt v1 plus a certificate verdict that
    points at the producer-validated receipt.
    """

    if schema == SHARED_EXECUTABLE_RECEIPT_SCHEMA:
        return str(declared_tier) if declared_tier in EXECUTABLE_TIERS else None

    if producer in SOURCE_REPRODUCTION_PRODUCERS and isinstance(schema, str):
        if schema.startswith("axiom_oracles.executable_reproduction.v"):
            return "source_reproduction"
    if (
        producer in RELEASE_RECEIPT_PRODUCERS or contract == "release_receipt"
    ) and schema == "axiom_oracles.executable_receipt.v1":
        return "release_receipt"
    return None


def _registry_executable_config(spec: Mapping[str, Any]) -> dict[str, Any] | None:
    computed = (spec.get("computed") or {}).get("executable")
    if isinstance(computed, dict):
        return computed
    # The public v1 #461 branch predates the computed namespace.
    legacy = spec.get("executable")
    return legacy if isinstance(legacy, dict) else None


def resolve_required_executable_tier(
    program: str,
    candidate_tier: object,
    spec: Mapping[str, Any],
) -> str:
    """Bind candidate policy to registry policy and hard release surfaces."""

    if candidate_tier not in EXECUTABLE_TIERS:
        raise CertificationError(
            f"{program} candidate executable tier must be one of {EXECUTABLE_TIERS}"
        )
    config = _registry_executable_config(spec) or {}
    registered = config.get("required_tier")
    if registered is not None and registered not in EXECUTABLE_TIERS:
        raise CertificationError(
            f"{program} registry has unknown executable tier {registered!r}"
        )
    expected = registered
    if config.get("contract") == "release_receipt" or program in RELEASE_TIER_PROGRAMS:
        if expected not in (None, "release_receipt"):
            raise CertificationError(
                f"{program} release contract conflicts with registry tier {expected!r}"
            )
        expected = "release_receipt"
    if expected is not None and candidate_tier != expected:
        raise CertificationError(
            f"{program} candidate tier {candidate_tier!r} disagrees with "
            f"registry-required {expected!r}"
        )
    return str(expected or candidate_tier)


def _offered_executable_tier(
    repo_root: Path,
    program: str,
    spec: Mapping[str, Any],
    certificate: Mapping[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    verdicts = certificate.get("verdicts")
    verdict = verdicts.get("executable") if isinstance(verdicts, dict) else None
    computed = _registry_executable_config(spec)
    evidence: dict[str, Any] = {
        "certificate_mode": verdict.get("mode") if isinstance(verdict, dict) else None,
        "certificate_value": verdict.get("value")
        if isinstance(verdict, dict)
        else None,
        "legacy_attestation_ignored": bool(
            isinstance(verdict, dict) and verdict.get("mode") == "attested"
        ),
    }
    if (
        not isinstance(verdict, dict)
        or verdict.get("mode") != "computed"
        or verdict.get("value") is not True
    ):
        return None, evidence
    if not isinstance(computed, dict):
        return None, evidence
    # The public release-only #461 v1 shape predates both ``computed`` and an
    # explicit tier/contract field. Its recomputed verdict names the validated
    # receipt, while the registry names the manifest and pinned outputs. Only a
    # hard release-tier program may use that compatibility path.
    legacy_v1_contract = bool(
        program in RELEASE_TIER_PROGRAMS
        and _nonempty(computed.get("manifest"))
        and isinstance(computed.get("expected_outputs"), dict)
        and _nonempty(verdict.get("receipt"))
        and not _nonempty(computed.get("artifact"))
    )
    artifact_ref = computed.get("artifact") or (
        verdict.get("receipt") if legacy_v1_contract else None
    )
    artifact_path = _repo_path(
        repo_root,
        artifact_ref,
        label=f"{program} executable artifact",
    )
    document = _read_json(artifact_path, label=str(artifact_ref))
    verdict_receipt_sha256 = verdict.get("receipt_sha256")
    if verdict_receipt_sha256 is not None and verdict_receipt_sha256 != _sha256(
        artifact_path
    ):
        raise CertificationError(
            f"{program} executable receipt hash disagrees with its certificate"
        )
    producer = computed.get("producer")
    schema = document.get("schema")
    document_tier = document.get("tier")
    verdict_tier = verdict.get("tier")
    if verdict_tier is not None and verdict_tier not in EXECUTABLE_TIERS:
        raise CertificationError(
            f"{program} computed executable verdict has unknown tier {verdict_tier!r}"
        )
    tier = recognize_executable_tier(
        producer,
        schema,
        declared_tier=document_tier,
        contract=(
            computed.get("contract")
            or ("release_receipt" if legacy_v1_contract else None)
        ),
    )
    if verdict_tier is not None:
        if tier is not None and verdict_tier != tier:
            raise CertificationError(
                f"{program} executable receipt tier {tier!r} disagrees with "
                f"certificate tier {verdict_tier!r}"
            )
        tier = str(verdict_tier)
    if schema == SHARED_EXECUTABLE_RECEIPT_SCHEMA and tier != document_tier:
        raise CertificationError(
            f"{program} shared executable receipt lacks an agreed explicit tier"
        )
    released_artifact = document.get("artifact")
    receipt_artifact_sha256 = (
        released_artifact.get("sha256") if isinstance(released_artifact, dict) else None
    )
    verdict_evidence = verdict.get("evidence")
    validated_artifact = (
        verdict_evidence.get("artifact") if isinstance(verdict_evidence, dict) else None
    )
    validated_artifact_sha256 = (
        validated_artifact.get("sha256")
        if isinstance(validated_artifact, dict)
        else None
    )
    if (
        _nonempty(receipt_artifact_sha256)
        and _nonempty(validated_artifact_sha256)
        and receipt_artifact_sha256 != validated_artifact_sha256
    ):
        raise CertificationError(
            f"{program} executable artifact hash disagrees with its certificate"
        )
    released_artifact_sha256 = validated_artifact_sha256 or receipt_artifact_sha256
    evidence.update(
        {
            "artifact": str(artifact_ref),
            "artifact_sha256": _sha256(artifact_path),
            "producer": producer,
            "schema": schema,
            "receipt_declared_tier": document_tier,
            "certificate_declared_tier": verdict_tier,
            "registry_required_tier": computed.get("required_tier"),
            "registry_contract": computed.get("contract"),
            "legacy_v1_release_contract": legacy_v1_contract,
            "recognized_tier": tier,
            "verification": "program_certificate_producer_validation",
            "rulespec_sha": verdict.get("rulespec_sha"),
            "engine_binary_sha256": verdict.get("engine_binary_sha256"),
            "released_artifact_sha256": released_artifact_sha256,
        }
    )
    return tier, evidence


def assess_executable_tier(
    required_tier: str,
    offered_tier: str | None,
    evidence: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Apply exact executable-tier equality from the shared #461 contract."""

    if required_tier not in EXECUTABLE_TIERS:
        raise CertificationError(f"unknown required executable tier {required_tier!r}")
    if offered_tier not in (*EXECUTABLE_TIERS, None):
        raise CertificationError(f"unknown offered executable tier {offered_tier!r}")
    detail = {
        **dict(evidence or {}),
        "required_tier": required_tier,
        "offered_tier": offered_tier,
    }
    holds = offered_tier == required_tier
    if holds:
        return _criterion(True, detail), None
    if required_tier == "release_receipt" and offered_tier == "source_reproduction":
        return _criterion(False, detail), _refusal(
            "executable",
            "executable.tier_insufficient",
            "source_reproduction was offered, but this published artifact requires a release_receipt",
            producer=RELEASE_RECEIPT_PRODUCER,
        )
    if offered_tier is not None:
        return _criterion(False, detail), _refusal(
            "executable",
            "executable.tier_mismatch",
            f"{offered_tier} was offered, but the registry requires {required_tier}",
            producer=RELEASE_RECEIPT_PRODUCER,
        )
    if required_tier == "release_receipt":
        return _criterion(False, detail), _refusal(
            "executable",
            "executable.release_receipt_missing",
            "no computed release_receipt exists for the published artifact and released engine",
            producer=RELEASE_RECEIPT_PRODUCER,
        )
    return _criterion(False, detail), _refusal(
        "executable",
        "executable.source_reproduction_missing",
        "no computed source_reproduction receipt exists for the program",
        producer="scripts/executable_reproduction.py",
    )


def bind_release_artifact(
    executable: Mapping[str, Any],
    membership: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Bind a release receipt to the exact compiled graph used for membership."""

    result = copy.deepcopy(dict(executable))
    evidence = result.get("evidence")
    if not isinstance(evidence, dict):
        raise CertificationError("executable criterion evidence must be a mapping")
    if not result.get("holds") or evidence.get("offered_tier") != "release_receipt":
        return result, None
    released_sha = evidence.get("released_artifact_sha256")
    membership_sha = membership.get("artifact_sha256")
    evidence["membership_artifact_sha256"] = membership_sha
    if not _nonempty(released_sha) or not _nonempty(membership_sha):
        result["holds"] = False
        return result, _refusal(
            "executable",
            "executable.release_artifact_unbound",
            "the release receipt does not bind the compiled program used for node membership",
            producer=RELEASE_RECEIPT_PRODUCER,
        )
    if released_sha != membership_sha:
        result["holds"] = False
        return result, _refusal(
            "executable",
            "executable.release_artifact_mismatch",
            "the release receipt artifact hash differs from the membership graph artifact hash",
            producer=RELEASE_RECEIPT_PRODUCER,
        )
    return result, None


def assess_provision_rooted(
    node_record: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Refuse annotations until the engine #136 catalog producer is validated."""

    record = dict(node_record or {})
    provenance = record.get("provenance")
    citation = record.get("corpus_citation_path")
    evidence = {
        "required_provenance": "provision_backed",
        "producer": PROVENANCE_PRODUCER,
        "observed_provenance": provenance,
        "corpus_citation_path": citation,
        "producer_validated": False,
    }
    return _criterion(False, evidence), _refusal(
        "provision_rooted",
        "provision_rooted.producer_missing",
        "no validated engine #136 metadata.nodes provenance catalog is available",
        producer=PROVENANCE_PRODUCER,
    )


def _membership(
    repo_root: Path,
    program: str,
    node: str,
    config: Mapping[str, Any],
) -> tuple[bool, dict[str, Any], Mapping[str, Any] | None, dict[str, Any] | None]:
    adapter = config.get("adapter")
    artifact_ref = config.get("artifact")
    artifact_path = _repo_path(
        repo_root,
        artifact_ref,
        label=f"{program} membership artifact",
    )
    base_evidence: dict[str, Any] = {
        "adapter": adapter,
        "artifact": str(artifact_ref),
        "artifact_sha256": _sha256(artifact_path),
    }

    if adapter == "compiled_program_node":
        expected_artifact = COMPILED_PROGRAM_ARTIFACTS.get(program)
        if expected_artifact is None or artifact_ref != expected_artifact:
            raise CertificationError(
                f"{program} has no gate-bound compiled membership artifact "
                f"matching {artifact_ref!r}"
            )
        base_evidence["program_binding"] = expected_artifact
        artifact = _read_json(artifact_path, label=str(artifact_ref))
        raw_program = artifact.get("program")
        if not isinstance(raw_program, dict):
            raise CertificationError(f"{artifact_ref} has no compiled program object")
        matches: list[tuple[str, dict[str, Any]]] = []
        for collection in ("parameters", "derived", "relations"):
            rows = raw_program.get(collection) or []
            if not isinstance(rows, list):
                raise CertificationError(
                    f"{artifact_ref} program.{collection} must be a list"
                )
            matches.extend(
                (collection, row)
                for row in rows
                if isinstance(row, dict) and row.get("id") == node
            )
        if len(matches) == 1:
            collection, record = matches[0]
            evidence = {
                **base_evidence,
                "collection": collection,
                "name": record.get("name"),
            }
            return True, evidence, record, None
        reason = _refusal(
            "program_subgraph",
            "program_subgraph.membership_unavailable",
            f"{node} occurs {len(matches)} times in the {program} compiled program; exactly one is required",
            producer=str(artifact_ref),
        )
        return False, base_evidence, None, reason

    if adapter == "closure_ledger_rule":
        ledger = _read_yaml(artifact_path, label=str(artifact_ref))
        ledger_program = ledger.get("program")
        ledger_program_id = (
            ledger_program.get("id")
            if isinstance(ledger_program, dict)
            else ledger_program
        )
        if (
            ledger.get("schema") != "axiom_oracles.closure.ledger.v2"
            or ledger_program_id != program
        ):
            raise CertificationError(
                f"{artifact_ref} is not the {program} closure ledger"
            )
        module_id, rule = node.rsplit("#", 1)
        facts = ledger.get("generated_facts")
        if not isinstance(facts, dict):
            raise CertificationError(f"{artifact_ref} has no generated_facts")
        modules = [
            row
            for row in facts.get("rulespec_modules") or []
            if isinstance(row, dict) and row.get("module_id") == module_id
        ]
        rule_names: set[str] = set()
        for row in facts.get("module_inputs") or []:
            if isinstance(row, dict) and row.get("module") == module_id:
                rule_names.update(
                    str(name) for name in row.get("read_by") or [] if _nonempty(name)
                )
        for module in modules:
            rule_names.update(
                str(atom.get("rule"))
                for atom in module.get("proof_atoms") or []
                if isinstance(atom, dict) and _nonempty(atom.get("rule"))
            )
        selection_ref = config.get("selection_artifact")
        selection_path = _repo_path(
            repo_root,
            selection_ref,
            label=f"{program} candidate selection artifact",
        )
        selection = _read_json(selection_path, label=str(selection_ref))
        selected = any(
            isinstance(row, dict)
            and row.get("program") == module_id
            and row.get("output") == node
            for row in selection.get("cases") or []
        )
        evidence = {
            **base_evidence,
            "module": module_id,
            "rule": rule,
            "selection_artifact": str(selection_ref),
            "selection_artifact_sha256": _sha256(selection_path),
            "selected_as_source_reproduction_output": selected,
        }
        if len(modules) == 1 and rule in rule_names and selected:
            return True, evidence, modules[0], None
        reason = _refusal(
            "program_subgraph",
            "program_subgraph.membership_unavailable",
            f"{node} is not an exact rule/output member of the {program} closure subgraph",
            producer=str(artifact_ref),
        )
        return False, evidence, None, reason

    raise CertificationError(f"unsupported membership adapter {adapter!r}")


def _program_contexts(
    repo_root: Path,
    registry: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    program_configs = registry["programs"]
    programs = sorted(program_configs)
    _, certificates, specs = _load_program_certificates(repo_root, programs)
    contexts: dict[str, dict[str, Any]] = {}
    for program in programs:
        certificate = certificates[program]
        config = program_configs[program]
        conformant, conformant_refusal = _certificate_criterion(
            program, certificate, "conformant", repo_root
        )
        exercised, exercised_refusal = _certificate_criterion(
            program, certificate, "exercised", repo_root
        )
        closure_config = config["closure"]
        if closure_config["adapter"] == "certificate":
            closed, closed_refusal = _certificate_criterion(
                program, certificate, "closed", repo_root
            )
        else:
            closed, closed_refusal = _co_closure_criterion(
                repo_root, program, closure_config
            )
        offered_tier, executable_evidence = _offered_executable_tier(
            repo_root, program, specs[program], certificate
        )
        required_tier = resolve_required_executable_tier(
            program,
            config["executable"]["required_tier"],
            specs[program],
        )
        executable, executable_refusal = assess_executable_tier(
            required_tier,
            offered_tier,
            executable_evidence,
        )
        certificate_path = (
            repo_root / "certificates" / f"{program.replace('/', '-')}.json"
        )
        contexts[program] = {
            "certificate": certificate,
            "certificate_ref": {
                "artifact": certificate_path.relative_to(repo_root).as_posix(),
                "sha256": _sha256(certificate_path),
                "state": (certificate.get("certified") or {}).get("state"),
                "value": (certificate.get("certified") or {}).get("value"),
            },
            "criteria": {
                "conformant": conformant,
                "exercised": exercised,
                "closed": closed,
                "executable": executable,
            },
            "refusals": {
                "conformant": conformant_refusal,
                "exercised": exercised_refusal,
                "closed": closed_refusal,
                "executable": executable_refusal,
            },
            "required_tier": required_tier,
            "offered_tier": offered_tier,
            "membership": config["membership"],
        }
    return contexts


def _git_head(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _ledger_entry(
    candidate: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    as_of: str,
    repo_head: str,
) -> dict[str, Any]:
    """Render the documented computed-only ops entry shape.

    This path is intentionally unreachable until provenance lands, but keeping
    it strict prevents a future green criterion from producing an ad-hoc shape.
    """

    criteria = result["criteria"]
    citation = criteria["provision_rooted"]["evidence"].get("corpus_citation_path")
    if not _nonempty(citation):
        raise CertificationError("certified candidate has no computed corpus citation")
    executable = criteria["executable"]["evidence"]
    closed = criteria["closed"]["evidence"]
    membership = result["membership"]
    evidence_digest = _canonical_sha(
        {"node": result["node"], "criteria": criteria, "membership": membership}
    )
    return {
        "node": result["node"],
        "label": candidate["label"],
        "provision": candidate["provision"],
        "corpus_citation_path": citation,
        "certified_at": f"{as_of}T00:00:00Z",
        "harness": {
            "run": f"scripts/certify_nodes.py@{repo_head}",
            "certify_check": evidence_digest,
        },
        "pinned": {
            "rulespec_us": executable.get("rulespec_sha")
            or closed.get("rulespec_commit")
            or "unavailable",
            "corpus": closed.get("summary_sha256")
            or closed.get("certificate_sha256")
            or "unavailable",
            "engine": executable.get("engine_binary_sha256") or "unavailable",
            "artifact": membership.get("artifact_sha256") or "unavailable",
        },
        "criteria": {
            name: {
                "holds": True,
                "evidence": _canonical_sha(criteria[name]["evidence"]),
            }
            for name in CRITERIA
        },
    }


def evaluate_candidates(
    repo_root: Path,
    registry: Mapping[str, Any],
    *,
    as_of: str,
) -> list[dict[str, Any]]:
    contexts = _program_contexts(repo_root, registry)
    results: list[dict[str, Any]] = []
    repo_head = _git_head(repo_root)
    for candidate in registry["candidates"]:
        node = str(candidate["node"])
        program = str(candidate["program"])
        context = contexts[program]
        attempts = {
            owner: _membership(
                repo_root,
                owner,
                node,
                owner_context["membership"],
            )
            for owner, owner_context in contexts.items()
        }
        matched_programs = sorted(
            owner for owner, attempt in attempts.items() if attempt[0]
        )
        member, membership_evidence, node_record, membership_refusal = attempts[program]
        membership_evidence = {
            **membership_evidence,
            "matched_programs": matched_programs,
        }
        if matched_programs != [program]:
            member = False
            node_record = None
            membership_refusal = _refusal(
                "program_subgraph",
                "program_subgraph.membership_ambiguous",
                f"{node} resolved to {matched_programs}; exactly {program!r} is required",
            )
        criteria: dict[str, dict[str, Any]] = {}
        refusals: list[dict[str, Any]] = []
        if member:
            provision, provision_refusal = assess_provision_rooted(node_record)
            criteria["provision_rooted"] = provision
            if provision_refusal:
                refusals.append(provision_refusal)
            for name in CRITERIA[1:]:
                criteria[name] = copy.deepcopy(context["criteria"][name])
                refusal = context["refusals"][name]
                if refusal:
                    refusals.append(dict(refusal))
            executable, binding_refusal = bind_release_artifact(
                criteria["executable"],
                membership_evidence,
            )
            criteria["executable"] = executable
            if binding_refusal:
                refusals.append(binding_refusal)
        else:
            unavailable = {
                "holds": False,
                "evidence": {
                    "reason": "program subgraph membership was not established",
                },
            }
            criteria = {name: dict(unavailable) for name in CRITERIA}
            refusals.append(
                membership_refusal
                or _refusal(
                    "program_subgraph",
                    "program_subgraph.membership_unavailable",
                    f"{node} has no exact registered program subgraph",
                )
            )

        certified = member and all(criteria[name]["holds"] for name in CRITERIA)
        result: dict[str, Any] = {
            "node": node,
            "label": candidate["label"],
            "program": program,
            "certified": certified,
            "program_certificate": context["certificate_ref"],
            "membership": {"holds": member, **membership_evidence},
            "executable_tier": {
                "required": context["required_tier"],
                "offered": context["offered_tier"],
            },
            "criteria": criteria,
            "refusals": refusals,
        }
        if certified:
            result["ledger_entry"] = _ledger_entry(
                candidate,
                result,
                as_of=as_of,
                repo_head=repo_head,
            )
        results.append(result)
    return results


LEDGER_HEADER = """# Certified nodes — generated computed-only source for the ops/API ledger.
#
# Generated by scripts/certify_nodes.py from the real program-certificate
# registry, strict report/census evidence, closure producers, executable
# receipts, and exact program-subgraph membership. Manual entries are invalid.
# A node appears only when provision_rooted, conformant, exercised, closed,
# and executable all hold in computed mode.
#
# Current honest state: engine #136 has not emitted node-level provision
# provenance annotations, so candidates are recorded in the machine-readable
# certified-node-refusals.json queue and this ledger remains empty.
"""


def _render_ledger(as_of: str, results: Sequence[Mapping[str, Any]]) -> str:
    nodes = [result["ledger_entry"] for result in results if result["certified"]]
    document = {
        "schema": LEDGER_SCHEMA,
        "generated": True,
        "as_of": as_of,
        "nodes": nodes,
    }
    return (
        LEDGER_HEADER
        + "\n"
        + yaml.safe_dump(
            document,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    )


def _render_refusals(
    as_of: str,
    results: Sequence[Mapping[str, Any]],
    registry_path: Path,
    repo_root: Path,
) -> str:
    refused = [result for result in results if not result["certified"]]
    codes = Counter(
        refusal["code"]
        for result in refused
        for refusal in result.get("refusals") or []
    )
    by_program: dict[str, dict[str, int]] = {}
    for program in sorted({str(result["program"]) for result in results}):
        rows = [result for result in results if result["program"] == program]
        by_program[program] = {
            "candidates": len(rows),
            "certified": sum(bool(row["certified"]) for row in rows),
            "refused": sum(not bool(row["certified"]) for row in rows),
        }
    queue_entries = []
    for result in refused:
        conformant = result["criteria"]["conformant"]
        if not conformant["holds"]:
            continue
        suites = [
            str(row["suite"])
            for row in conformant["evidence"].get("reference_legs") or []
            if isinstance(row, dict) and _nonempty(row.get("suite"))
        ]
        certificate = result["program_certificate"]
        queue_entries.append(
            {
                "legal_id": result["node"],
                "oracle": ", ".join(suites)
                or f"{result['program']} program certificate",
                "evidence": (
                    f"{certificate['artifact']}@sha256:{certificate['sha256']}; "
                    "certified-node-refusals.json"
                ),
                "shortfall": "; ".join(
                    f"{row['code']}: {row['message']}"
                    for row in result.get("refusals") or []
                ),
            }
        )
    document = {
        # axiom-api can consume this file directly as its validated-status
        # queue. It ignores the richer sibling fields below.
        "format": VALIDATION_EVIDENCE_FORMAT,
        "schema": REFUSAL_SCHEMA,
        "generated": True,
        "as_of": as_of,
        "generator": "scripts/certify_nodes.py",
        "candidate_registry": {
            "artifact": registry_path.relative_to(repo_root).as_posix(),
            "sha256": _sha256(registry_path),
        },
        "summary": {
            "candidates": len(results),
            "certified": len(results) - len(refused),
            "refused": len(refused),
            "by_program": by_program,
            "refusal_codes": dict(sorted(codes.items())),
        },
        "entries": queue_entries,
        "refusals": refused,
    }
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def build_outputs(
    repo_root: Path = REPO_ROOT,
    *,
    as_of: str,
    candidate_registry: Path = DEFAULT_CANDIDATES,
) -> tuple[str, str, list[dict[str, Any]]]:
    if not isinstance(as_of, str) or not _DATE.fullmatch(as_of):
        raise CertificationError("as_of must be YYYY-MM-DD")
    try:
        date.fromisoformat(as_of)
    except ValueError as exc:
        raise CertificationError("as_of must be a real calendar date") from exc
    registry, registry_path = load_candidate_registry(repo_root, candidate_registry)
    results = evaluate_candidates(repo_root, registry, as_of=as_of)
    return (
        _render_ledger(as_of, results),
        _render_refusals(as_of, results, registry_path, repo_root),
        results,
    )


def _as_of_for_check(path: Path) -> str:
    if not path.is_file():
        raise CertificationError(f"{path} is missing; pass --as-of for generation")
    document = _read_yaml(path, label=str(path))
    value = document.get("as_of")
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise CertificationError(f"{path} has no quoted YYYY-MM-DD as_of string")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail on generated-output drift"
    )
    parser.add_argument(
        "--as-of", help="ledger date (YYYY-MM-DD); defaults to today when writing"
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--refusals", type=Path, default=DEFAULT_REFUSALS)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo_root / args.output
    refusals = (
        args.refusals if args.refusals.is_absolute() else repo_root / args.refusals
    )
    try:
        as_of = args.as_of or (
            _as_of_for_check(output) if args.check else date.today().isoformat()
        )
        ledger_text, refusal_text, results = build_outputs(
            repo_root,
            as_of=as_of,
            candidate_registry=args.candidates,
        )
    except CertificationError as exc:
        print(f"certify_nodes REFUSED: {exc}", file=sys.stderr)
        return 2

    expected = ((output, ledger_text), (refusals, refusal_text))
    if args.check:
        drift = [
            path
            for path, text in expected
            if not path.is_file() or path.read_text(encoding="utf-8") != text
        ]
        if drift:
            for path in drift:
                print(f"generated output drift: {path}", file=sys.stderr)
            return 1
        print(
            f"certify_nodes outputs up to date: {len(results)} candidates, "
            f"{sum(bool(row['certified']) for row in results)} certified"
        )
        return 0

    for path, text in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    certified = sum(bool(row["certified"]) for row in results)
    print(
        f"wrote {output} + {refusals}: {len(results)} candidates, "
        f"{certified} certified, {len(results) - certified} refused"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
