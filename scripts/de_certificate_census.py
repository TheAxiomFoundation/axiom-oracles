#!/usr/bin/env python3
"""Generate the DE certificate-candidate census.

This is a declaration census, not a conformance report.  It records the exact
legal citation roots and the producer gaps for each requested DE certificate.
Encoding/signature observations are explicitly attested to a pinned
``rulespec-de`` commit; the pending verdict and Kindergeld Axiom-leg inventory
are recomputed from committed artifacts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "conformance" / "de-certificate-census.json"
UNIFIED_PATH = (
    REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "unified-record.json"
)
UNIFIED_GENERATOR = REPO_ROOT / "scripts" / "de_unified_comparison.py"
CLOSURE_SOURCE_PATH = REPO_ROOT / "closure" / "de" / "source.json"
EXECUTABLE_GENERATOR = REPO_ROOT / "scripts" / "de_executable.py"
EXECUTABLE_MANIFEST_PATH = (
    REPO_ROOT / "conformance" / "executable" / "de-kindergeld-manifest.json"
)
SCHEMA = "axiom_oracles.certificate_candidate_census.v1"
RULESPEC_REPOSITORY = "TheAxiomFoundation/rulespec-de"
RULESPEC_MAIN_COMMIT = "d83ba3db30e2f63376aacf822d116687589b8564"

_CITATION_PATH = re.compile(r"^de/(?:statute|regulation)/[a-z0-9-]+/.+$")

EXPECTED_ROOT_SETS = {
    "de/kindergeld": {
        "de/statute/estg/66",
        "de/statute/estg/62",
        "de/statute/estg/63",
        "de/statute/estg/64",
        "de/statute/estg/65",
        "de/statute/bgbl-2024-i-449/steuerfortentwicklungsgesetz",
    },
    "de/rv-employee-contribution": {
        "de/regulation/bsv-2018/1",
        "de/regulation/svbezgrv-2025/4",
        "de/statute/sgb-6/168",
    },
    "de/unterhaltsvorschuss": {
        "de/regulation/minuhv/1",
        "de/statute/uhvorschg/2",
        "de/statute/estg/66",
    },
}
EXPECTED_ROOT_SHAPES = {
    "de/kindergeld": {
        "de/statute/estg/66": ("governing", "encoded", {"pending", "signed"}),
        **{
            f"de/statute/estg/{section}": (
                "boundary_input",
                "excluded-with-reason",
                {"not_applicable"},
            )
            for section in (62, 63, 64, 65)
        },
        "de/statute/bgbl-2024-i-449/steuerfortentwicklungsgesetz": (
            "evidence_root",
            "evidence",
            {"not_applicable"},
        ),
    },
    "de/rv-employee-contribution": {
        "de/regulation/bsv-2018/1": ("governing", "pending", {"pending"}),
        "de/regulation/svbezgrv-2025/4": (
            "dependency",
            "encoded",
            {"signed"},
        ),
        "de/statute/sgb-6/168": ("governing", "encoded", {"pending"}),
    },
    "de/unterhaltsvorschuss": {
        "de/regulation/minuhv/1": ("governing", "encoded", {"signed"}),
        "de/statute/uhvorschg/2": ("governing", "pending", {"pending"}),
        "de/statute/estg/66": ("dependency", "encoded", {"pending", "signed"}),
    },
}
ATTESTED_SIGNED_ROOTS = {
    "de/regulation/svbezgrv-2025/4": {
        "repository": RULESPEC_REPOSITORY,
        "ref": RULESPEC_MAIN_COMMIT,
        "path": ".axiom/encoding-manifests/de/regulations/svbezgrv-2025/4.json",
        "sha256": "a46035cf77c7d2a9e15a6aeb64fee6b49c10991179f3a2388188cafd973dab32",
    },
    "de/regulation/minuhv/1": {
        "repository": RULESPEC_REPOSITORY,
        "ref": RULESPEC_MAIN_COMMIT,
        "path": ".axiom/encoding-manifests/de/regulations/minuhv/1.json",
        "sha256": "cd7a6a3cd40f7098071f50e88f81eaa3072c0b6c833f99af6e88219bbac92e5f",
    },
}


def _root(
    citation_path: str,
    *,
    role: str,
    classification: str,
    signature_state: str,
    reason: str,
    source_ref: str = RULESPEC_MAIN_COMMIT,
    source_path: str | None = None,
    source_sha256: str | None = None,
    scope: str | None = None,
) -> dict:
    row = {
        "citation_path": citation_path,
        "role": role,
        "classification": classification,
        "signature_state": signature_state,
        "reason": reason,
        "claim_mode": "attested",
        "attestation": {
            "repository": RULESPEC_REPOSITORY,
            "ref": source_ref,
        },
    }
    if source_path:
        row["attestation"]["path"] = source_path
    if source_sha256:
        row["attestation"]["sha256"] = source_sha256
    if scope:
        row["scope"] = scope
    return row


PROGRAM_DECLARATIONS = {
    "de/kindergeld": {
        "period": "2025",
        "view": {"kind": "subgraph", "scope": "amount"},
        "root_nodes": ["de:statutes/estg/66#monthly_kindergeld_per_child"],
        "declared_roots": [
            _root(
                "de/statute/estg/66",
                role="governing",
                classification="encoded",
                signature_state="pending",
                reason=(
                    "2025 amount encoding is in the parallel signing lane; the "
                    "visible older unsigned 259 EUR module is a 2026 vintage and "
                    "does not satisfy this declaration"
                ),
            ),
            *[
                _root(
                    f"de/statute/estg/{section}",
                    role="boundary_input",
                    classification="excluded-with-reason",
                    signature_state="not_applicable",
                    reason=(
                        f"EStG section {section} supplies eligibility/payee/child "
                        "membership at the declared cut and is outside the amount "
                        "subgraph"
                    ),
                )
                for section in (62, 63, 64, 65)
            ],
            _root(
                "de/statute/bgbl-2024-i-449/steuerfortentwicklungsgesetz",
                role="evidence_root",
                classification="evidence",
                signature_state="not_applicable",
                reason=(
                    "SteFeG Article 1 number 4 supplies the 2025-effective 255 EUR "
                    "amount that the current consolidated EStG text no longer shows"
                ),
            ),
        ],
    },
    "de/rv-employee-contribution": {
        "period": "2025",
        "view": {
            "kind": "subgraph",
            "scope": "ordinary employee pension-insurance contribution",
        },
        "root_nodes": [
            "de:statutes/sgb-6/168#employee_pension_insurance_contribution_share",
            "de:regulations/svbezgrv-2025/4#general_pension_insurance_monthly_contribution_assessment_ceiling",
        ],
        "declared_roots": [
            _root(
                "de/regulation/bsv-2018/1",
                role="governing",
                classification="pending",
                signature_state="pending",
                reason=(
                    "no RuleSpec encoding exists and the 2018 text alone does not "
                    "prove that the 18.6 percent rate applies in 2025"
                ),
            ),
            _root(
                "de/regulation/svbezgrv-2025/4",
                role="dependency",
                classification="encoded",
                signature_state="signed",
                reason="signed ceiling encoding is merged on the pinned main commit",
                source_path=(
                    ".axiom/encoding-manifests/de/regulations/svbezgrv-2025/4.json"
                ),
                source_sha256=(
                    "a46035cf77c7d2a9e15a6aeb64fee6b49c10991179f3a2388188cafd973dab32"
                ),
            ),
            _root(
                "de/statute/sgb-6/168",
                role="governing",
                classification="encoded",
                signature_state="pending",
                reason="reviewed encoding exists but is not signed or merged",
                source_ref="203420d",
                source_sha256=(
                    "8a21603735171601927e2cbd626c0566a9c9d145c20263d78cb1dd849a79313c"
                ),
                scope="Absatz 1 Nummer 1 — ordinary persons employed for remuneration",
            ),
        ],
    },
    "de/unterhaltsvorschuss": {
        "period": "2025",
        "view": {"kind": "subgraph", "scope": "final maintenance advance amount"},
        "root_nodes": ["de:statutes/uhvorschg/2#advance_maintenance_amount"],
        "declared_roots": [
            _root(
                "de/regulation/minuhv/1",
                role="governing",
                classification="encoded",
                signature_state="signed",
                reason="signed minimum-support encoding is merged on pinned main",
                source_path=".axiom/encoding-manifests/de/regulations/minuhv/1.json",
                source_sha256=(
                    "cd7a6a3cd40f7098071f50e88f81eaa3072c0b6c833f99af6e88219bbac92e5f"
                ),
            ),
            _root(
                "de/statute/uhvorschg/2",
                role="governing",
                classification="pending",
                signature_state="pending",
                reason=(
                    "reviewed unsigned module covers the base subtraction only; "
                    "partial-month, income/maintenance offsets, and school/work "
                    "income abatements in subsections 1, 3, and 4 remain open"
                ),
                source_ref="0a5ba23",
                source_sha256=(
                    "d9c494557d2e439acf1270cb43e070005bf4ec91d9a0117ff076ce11818080cf"
                ),
            ),
            _root(
                "de/statute/estg/66",
                role="dependency",
                classification="encoded",
                signature_state="pending",
                reason="the 2025 Kindergeld dependency is awaiting its signed artifact",
            ),
        ],
    },
}


class DECensusError(ValueError):
    """A DE candidate declaration is ambiguous or self-authorizing."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DECensusError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DECensusError(f"{path}: top level must be an object")
    return value


def _rederived_unified() -> dict:
    spec = importlib.util.spec_from_file_location(
        "_de_census_unified", UNIFIED_GENERATOR
    )
    if spec is None or spec.loader is None:
        raise DECensusError("cannot load the DE unified-record verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.build()
    committed = _load(UNIFIED_PATH)
    if committed != expected:
        raise DECensusError("DE unified record does not rederive")
    return expected


def _rederived_executable() -> dict:
    spec = importlib.util.spec_from_file_location(
        "_de_census_executable", EXECUTABLE_GENERATOR
    )
    if spec is None or spec.loader is None:
        raise DECensusError("cannot load the DE executable verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        status = module.build_status()
    except (OSError, ValueError) as exc:
        raise DECensusError(f"cannot compute DE executable status: {exc}") from exc
    if not isinstance(status, dict) or status.get("mode") != "computed":
        raise DECensusError("DE executable verifier returned no computed status")
    return status


def validate_declarations(
    declarations: dict, *, computed_signed_estg: dict | None = None
) -> None:
    expected_programs = {
        "de/kindergeld",
        "de/rv-employee-contribution",
        "de/unterhaltsvorschuss",
    }
    if set(declarations) != expected_programs:
        raise DECensusError("DE declaration program set changed")
    for program, declaration in declarations.items():
        roots = declaration.get("declared_roots")
        if not isinstance(roots, list) or not roots:
            raise DECensusError(f"{program}: declared_roots must be nonempty")
        paths = [row.get("citation_path") for row in roots if isinstance(row, dict)]
        if len(paths) != len(roots) or len(set(paths)) != len(paths):
            raise DECensusError(f"{program}: citation roots must be unique mappings")
        if set(paths) != EXPECTED_ROOT_SETS[program]:
            raise DECensusError(f"{program}: declared citation root set changed")
        for row in roots:
            citation = row.get("citation_path")
            if not isinstance(citation, str) or not _CITATION_PATH.fullmatch(citation):
                raise DECensusError(
                    f"{program}: {citation!r} is not an exact DE citation path"
                )
            if not str(row.get("reason", "")).strip():
                raise DECensusError(f"{program}: {citation} lacks a reason")
            if row.get("claim_mode") != "attested":
                raise DECensusError(
                    f"{program}: {citation} declaration must remain attested"
                )
            signature = row.get("signature_state")
            if signature not in {"signed", "pending", "not_applicable"}:
                raise DECensusError(
                    f"{program}: {citation} has invalid signature state"
                )
            expected_role, expected_classification, expected_signatures = (
                EXPECTED_ROOT_SHAPES[program][citation]
            )
            if (
                row.get("role") != expected_role
                or row.get("classification") != expected_classification
                or signature not in expected_signatures
            ):
                raise DECensusError(f"{program}: {citation} root declaration changed")
            if signature == "signed":
                computed_estg = (
                    citation == "de/statute/estg/66"
                    and row.get("signature_state_claim_mode") == "computed"
                    and row.get("attestation_claim_mode") == "computed"
                )
                if citation not in ATTESTED_SIGNED_ROOTS and not computed_estg:
                    raise DECensusError(
                        f"{program}: {citation} cannot be hand-promoted to signed"
                    )
                attestation = row.get("attestation")
                if not isinstance(attestation, dict):
                    raise DECensusError(
                        f"{program}: {citation} signed without attestation"
                    )
                required = {"repository", "ref", "path", "sha256"}
                if computed_estg:
                    required = {
                        "artifact",
                        "sha256",
                        "module_sha256",
                        "encoding_manifest_payload_sha256",
                        "encoding_manifest_source_file_sha256",
                        "trusted_key_id",
                    }
                if not required.issubset(attestation):
                    raise DECensusError(
                        f"{program}: {citation} signed without a pinned manifest"
                    )
                digest = attestation.get("sha256")
                if not isinstance(digest, str) or not re.fullmatch(
                    r"[0-9a-f]{64}", digest
                ):
                    raise DECensusError(
                        f"{program}: {citation} signed attestation has invalid SHA-256"
                    )
                if not computed_estg and attestation != ATTESTED_SIGNED_ROOTS[citation]:
                    raise DECensusError(
                        f"{program}: {citation} signed attestation pin changed"
                    )
                if computed_estg and attestation != computed_signed_estg:
                    raise DECensusError(
                        f"{program}: {citation} computed signature does not match "
                        "the executable verifier"
                    )
    for program, citation in (
        ("de/rv-employee-contribution", "de/regulation/svbezgrv-2025/4"),
        ("de/unterhaltsvorschuss", "de/regulation/minuhv/1"),
    ):
        row = next(
            item
            for item in declarations[program]["declared_roots"]
            if item["citation_path"] == citation
        )
        if (
            row.get("signature_state") != "signed"
            or row.get("classification") != "encoded"
        ):
            raise DECensusError(f"{program}: {citation} must remain signed")
    rv_scoped = next(
        item
        for item in declarations["de/rv-employee-contribution"]["declared_roots"]
        if item["citation_path"] == "de/statute/sgb-6/168"
    )
    if rv_scoped.get("scope") != (
        "Absatz 1 Nummer 1 — ordinary persons employed for remuneration"
    ):
        raise DECensusError("de/rv-employee-contribution: SGB VI 168 scope changed")
    kindergeld = {
        row["citation_path"]: row
        for row in declarations["de/kindergeld"]["declared_roots"]
    }
    amount_root = kindergeld["de/statute/estg/66"]
    if (
        amount_root.get("role") != "governing"
        or amount_root.get("classification") != "encoded"
    ):
        raise DECensusError(
            "de/kindergeld: EStG 66 must remain the encoded governing root"
        )
    for section in (62, 63, 64, 65):
        row = kindergeld[f"de/statute/estg/{section}"]
        if (
            row.get("role") != "boundary_input"
            or row.get("classification") != "excluded-with-reason"
        ):
            raise DECensusError(
                f"de/kindergeld: EStG {section} must remain an excluded boundary"
            )
    evidence = kindergeld["de/statute/bgbl-2024-i-449/steuerfortentwicklungsgesetz"]
    if (
        evidence.get("role") != "evidence_root"
        or evidence.get("classification") != "evidence"
    ):
        raise DECensusError("de/kindergeld: SteFeG must remain the evidence root")


def validate_closure_alignment(declarations: dict, source: dict) -> None:
    """Require the census and closure to share one exact citation denominator."""

    programs = source.get("programs")
    if not isinstance(programs, dict) or set(programs) != set(declarations):
        raise DECensusError("DE closure/census program sets differ")
    for program, declaration in declarations.items():
        closure = programs.get(program)
        if not isinstance(closure, dict):
            raise DECensusError(f"{program}: closure declaration is missing")
        if closure.get("root_nodes") != declaration.get("root_nodes"):
            raise DECensusError(f"{program}: closure/census root nodes differ")
        roots: list[str] = []
        for field in ("declared_sources", "evidence_roots", "boundaries"):
            rows = closure.get(field)
            if not isinstance(rows, list):
                raise DECensusError(f"{program}: closure {field} must be an array")
            roots.extend(
                row["citation_path"]
                for row in rows
                if isinstance(row, dict) and row.get("citation_path") is not None
            )
        if set(roots) != EXPECTED_ROOT_SETS[program] or len(roots) != len(set(roots)):
            raise DECensusError(
                f"{program}: closure/census exact citation denominator differs"
            )


def build(declarations: dict | None = None) -> dict:
    declarations = copy.deepcopy(declarations or PROGRAM_DECLARATIONS)
    executable = _rederived_executable()
    executable_inputs = {
        row.get("id"): row
        for row in executable.get("required_inputs") or []
        if isinstance(row, dict)
    }
    signed_estg = executable_inputs.get("signed-rulespec-estg-66-2025")
    computed_signed_estg = None
    for declaration in declarations.values():
        for estg_root in declaration["declared_roots"]:
            if estg_root["citation_path"] != "de/statute/estg/66":
                continue
            estg_root["signature_state_claim_mode"] = "computed"
            estg_root["attestation_claim_mode"] = "attested"
    if isinstance(signed_estg, dict) and signed_estg.get("state") == "valid":
        computed_signed_estg = {
            "artifact": signed_estg["path"],
            "sha256": signed_estg["sha256"],
            "module_sha256": signed_estg["module_sha256"],
            "encoding_manifest_payload_sha256": signed_estg[
                "encoding_manifest_payload_sha256"
            ],
            "encoding_manifest_source_file_sha256": signed_estg[
                "encoding_manifest_source_file_sha256"
            ],
            "trusted_key_id": signed_estg["trusted_key_id"],
        }
        for declaration in declarations.values():
            for estg_root in declaration["declared_roots"]:
                if estg_root["citation_path"] != "de/statute/estg/66":
                    continue
                estg_root.update(
                    {
                        "signature_state": "signed",
                        "signature_state_claim_mode": "computed",
                        "attestation_claim_mode": "computed",
                        "reason": (
                            "the executable verifier validated the exact signed "
                            "2025 module, apply manifest, corpus binding, and "
                            "Ed25519 trust root"
                        ),
                        "attestation": copy.deepcopy(computed_signed_estg),
                    }
                )
    validate_declarations(declarations, computed_signed_estg=computed_signed_estg)
    closure_source = _load(CLOSURE_SOURCE_PATH)
    validate_closure_alignment(declarations, closure_source)
    unified = _rederived_unified()
    kindergeld_view = unified.get("views", {}).get("de/kindergeld")
    if not isinstance(kindergeld_view, dict):
        raise DECensusError("DE unified record lacks the Kindergeld subgraph view")
    missing_axiom = kindergeld_view.get("missing_for_certification")
    required_axiom = kindergeld_view.get("required_axiom_legs")
    expected_axiom = ["axiom-euromod", "axiom-gettsim"]
    if required_axiom != expected_axiom:
        raise DECensusError("Kindergeld required Axiom-leg inventory changed")
    if not isinstance(missing_axiom, list) or missing_axiom != [
        leg for leg in expected_axiom if leg in missing_axiom
    ]:
        raise DECensusError("Kindergeld missing Axiom-leg subset is invalid")

    rows = {}
    for program, declaration in declarations.items():
        blockers: list[str]
        if program == "de/kindergeld":
            blockers = list(executable.get("blockers") or [])
        elif program == "de/rv-employee-contribution":
            blockers = [
                "no comparison record has been declared",
                "de/regulation/bsv-2018/1: encoding and 2025 temporal evidence pending",
                "de/statute/sgb-6/168: signature pending",
                "executable reproduction receipt pending",
            ]
        else:
            blockers = [
                "no comparison record has been declared",
                "de/statute/uhvorschg/2: final-amount encoding remains partial",
                "executable reproduction receipt pending",
            ]
            estg_dependency = next(
                root
                for root in declaration["declared_roots"]
                if root["citation_path"] == "de/statute/estg/66"
            )
            if estg_dependency.get("signature_state") != "signed":
                blockers.insert(2, "de/statute/estg/66: signed 2025 dependency pending")
        rows[program] = {
            **declaration,
            "certificate_path": f"certificates/{program.replace('/', '-')}.json",
            "certificate_status": "ready" if not blockers else "pending",
            "status_claim_mode": "computed",
            "blockers": blockers,
        }
    return {
        "schema": SCHEMA,
        "generated_by": "scripts/de_certificate_census.py",
        "rulespec_observation": {
            "repository": RULESPEC_REPOSITORY,
            "commit": RULESPEC_MAIN_COMMIT,
            "claim_mode": "attested",
        },
        "unified_record": {
            "artifact": UNIFIED_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": _sha256(UNIFIED_PATH),
            "claim_mode": "computed",
        },
        "closure_declarations": {
            "artifact": CLOSURE_SOURCE_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": _sha256(CLOSURE_SOURCE_PATH),
            "claim_mode": "computed",
        },
        "executable_observation": {
            "state": executable.get("state"),
            "value": executable.get("value"),
            "claim_mode": "computed",
            "manifest": EXECUTABLE_MANIFEST_PATH.relative_to(REPO_ROOT).as_posix(),
            "manifest_sha256": _sha256(EXECUTABLE_MANIFEST_PATH),
        },
        "programs": rows,
        "_comment": (
            "Generated declaration census. 'pending' is a computed state, not a "
            "certification label. Encoding/signature observations are attested "
            "to the pinned rulespec-de revision and cannot independently satisfy "
            "a computed certificate premise."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        census = build()
    except (DECensusError, OSError, ValueError) as exc:
        print(f"DE certificate census ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(census, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        if (
            not OUTPUT_PATH.exists()
            or OUTPUT_PATH.read_text(encoding="utf-8") != rendered
        ):
            print("DE certificate census drifted", file=sys.stderr)
            return 1
        print("DE certificate census up to date")
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
