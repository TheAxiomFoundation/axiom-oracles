#!/usr/bin/env python3
"""Compute DE program closure from a pinned exact-citation-path snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "closure" / "de"
SOURCE_PATH = OUT_DIR / "source.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

# Review pin for the committed denominator. Changing any corpus row,
# classification, boundary, or program root requires an explicit re-review.
SOURCE_SHA256 = "84fbc0559bacae1128bb992052791e0ecc78b71137dfc4244f2fc7f622d19bd7"

SOURCE_SCHEMA = "axiom_oracles.de_closure_source.v1"
SUMMARY_SCHEMA = "axiom_oracles.de_closure_summary.v1"
RELEASE = "de-rulespec-2026-07-21"
RELEASE_CONTENT_SHA256 = (
    "b4b405a06bfcf21331cff50a45844fd0117b52212dc24d0f4912ed07575fd574"
)
RELEASE_SELECTOR_SHA256 = (
    "106612aa6075a23fae4aae7fc80c39920cb6e0ff95e38694baa6191f8f3905f5"
)
CORPUS_COMMIT = "6f064ee6081f16440dc706ae09ac60652bb67570"
RULESPEC_COMMIT = "d83ba3db30e2f63376aacf822d116687589b8564"
RESOLUTION_PROTOCOL = {
    "descendants_by": "parent_citation_path",
    "filename_filters": False,
    "key": "citation_path",
    "match": "exact",
    "protocol": "de-exact-citation-closure-v1",
}

ESTG_66 = "de/statute/estg/66"
STEFEG_ROOT = "de/statute/bgbl-2024-i-449/steuerfortentwicklungsgesetz"
STEFEG_CONTENT = f"{STEFEG_ROOT}/document-1"
KINDERGELD_BOUNDARIES = (
    "de/statute/estg/62",
    "de/statute/estg/63",
    "de/statute/estg/64",
    "de/statute/estg/65",
)

PROGRAM_ROOT_NODES = {
    "de/kindergeld": ("de:statutes/estg/66#monthly_kindergeld_per_child",),
    "de/rv-employee-contribution": (
        "de:statutes/sgb-6/168#employee_pension_insurance_contribution_share",
        "de:regulations/svbezgrv-2025/4#general_pension_insurance_monthly_contribution_assessment_ceiling",
    ),
    "de/unterhaltsvorschuss": ("de:statutes/uhvorschg/2#advance_maintenance_amount",),
}
PROGRAM_SOURCE_PATHS = {
    "de/kindergeld": (ESTG_66,),
    "de/rv-employee-contribution": (
        "de/regulation/bsv-2018/1",
        "de/regulation/svbezgrv-2025/4",
        "de/statute/sgb-6/168",
    ),
    "de/unterhaltsvorschuss": (
        "de/regulation/minuhv/1",
        "de/statute/uhvorschg/2",
        ESTG_66,
    ),
}
PROGRAM_EVIDENCE_ROOTS = {
    "de/kindergeld": (STEFEG_ROOT,),
    "de/rv-employee-contribution": (),
    "de/unterhaltsvorschuss": (),
}

EXPECTED_INVENTORIES = {
    "data/corpus/inventory/de/regulation/"
    "2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.json": (
        "1bf25f052f0c0cb5271bab85c24854b4268149c10cd6261649e3e417fee1ca70",
        172,
    ),
    "data/corpus/inventory/de/statute/"
    "2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.json": (
        "0a31685dd6d68051111646df421f7fe86b551e9166981acdead13a112b2fd974",
        3376,
    ),
}
EXPECTED_PROVISION_SOURCES = {
    "data/corpus/provisions/de/regulation/"
    "2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.jsonl": (
        "abf3c4dcc16224370a4e5e717325fa6374818a5821f3419d981b4cc9c11f6528",
        172,
    ),
    "data/corpus/provisions/de/statute/"
    "2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.jsonl": (
        "e22b6f2910e5d736e7fd58553d23ccb94c5b5f3116ab99d476311bcfb2f83d31",
        3376,
    ),
}

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CLASSIFICATIONS = frozenset({"encoded", "excluded", "pending"})
SIGNATURE_STATES = frozenset({"signed", "pending", "not_applicable"})


class ClosureError(ValueError):
    """The committed DE closure denominator is malformed or inconsistent."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return _sha256(raw)


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ClosureError(f"{label} must be a lowercase 64-hex sha256")
    return value


def _require_nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClosureError(f"{label} must be a non-empty string")
    return value


def _validate_pinned_files(
    raw_rows: object,
    expected: dict[str, tuple[str, int]],
    label: str,
) -> None:
    if not isinstance(raw_rows, list):
        raise ClosureError(f"corpus {label} must be an array")
    paths = [row.get("path") for row in raw_rows if isinstance(row, dict)]
    if paths != sorted(expected):
        raise ClosureError(f"corpus {label} path set or order drifted")
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ClosureError(f"corpus {label} contains a non-object entry")
        path = row["path"]
        expected_sha, expected_count = expected[path]
        if row.get("sha256") != expected_sha or row.get("row_count") != expected_count:
            raise ClosureError(f"corpus {label} pin drifted for {path}")


def load_source() -> dict:
    """Load the source snapshot only when its reviewed bytes still match."""

    try:
        raw = SOURCE_PATH.read_bytes()
        if _sha256(raw) != SOURCE_SHA256:
            raise ClosureError(
                "DE closure source bytes changed; review and re-pin the denominator"
            )
        source = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read the DE closure source: {exc}") from exc
    if not isinstance(source, dict):
        raise ClosureError("DE closure source must contain an object")
    return source


def _row_index(corpus: dict) -> tuple[dict[str, dict], dict[str, list[str]]]:
    raw_rows = corpus.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ClosureError("corpus rows must be a non-empty array")
    citation_paths = [
        row.get("citation_path") for row in raw_rows if isinstance(row, dict)
    ]
    if citation_paths != sorted(set(citation_paths)):
        raise ClosureError("corpus rows must have unique, sorted citation paths")

    rows: dict[str, dict] = {}
    children: dict[str, list[str]] = defaultdict(list)
    provision_pins = {row["path"]: row["sha256"] for row in corpus["provision_sources"]}
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ClosureError("corpus rows contains a non-object entry")
        citation_path = _require_nonempty(
            row.get("citation_path"), "corpus row citation_path"
        )
        if not citation_path.startswith("de/"):
            raise ClosureError(f"non-DE citation path in snapshot: {citation_path}")
        _require_nonempty(row.get("record_id"), f"{citation_path} record_id")
        if not isinstance(row.get("line_number"), int) or row["line_number"] < 1:
            raise ClosureError(f"{citation_path} has an invalid line_number")
        provision_file = _require_nonempty(
            row.get("provision_file"), f"{citation_path} provision_file"
        )
        if provision_file not in provision_pins:
            raise ClosureError(f"{citation_path} names an unpinned provision file")
        if row.get("provision_file_sha256") != provision_pins[provision_file]:
            raise ClosureError(f"{citation_path} provision-file sha drifted")
        _require_hash(row.get("row_sha256"), f"{citation_path} row_sha256")
        _require_hash(row.get("source_sha256"), f"{citation_path} source_sha256")
        body_sha = row.get("body_sha256")
        body_length = row.get("body_length")
        if body_sha is not None:
            _require_hash(body_sha, f"{citation_path} body_sha256")
        if not isinstance(body_length, int) or body_length < 0:
            raise ClosureError(f"{citation_path} has an invalid body_length")
        if (body_length == 0) != (body_sha is None):
            raise ClosureError(
                f"{citation_path} body length/hash presence does not conserve"
            )
        parent = row.get("parent_citation_path")
        if parent is not None:
            _require_nonempty(parent, f"{citation_path} parent_citation_path")
            children[parent].append(citation_path)
        rows[citation_path] = row

    for parent, child_paths in children.items():
        if parent not in rows:
            raise ClosureError(f"snapshot child refers to absent parent {parent!r}")
        if child_paths != sorted(set(child_paths)):
            raise ClosureError(f"children of {parent!r} must be unique and sorted")
    return rows, children


def _descendants(root: str, children: dict[str, list[str]]) -> list[str]:
    reached: set[str] = set()
    stack = list(children.get(root, ()))
    while stack:
        citation = stack.pop()
        if citation in reached:
            continue
        reached.add(citation)
        stack.extend(children.get(citation, ()))
    return sorted(reached)


def _validate_module_catalog(source: dict, rows: dict[str, dict]) -> dict[str, dict]:
    rulespec = source.get("rulespec")
    if not isinstance(rulespec, dict):
        raise ClosureError("rulespec snapshot must be an object")
    if (
        rulespec.get("repository") != "TheAxiomFoundation/rulespec-de"
        or rulespec.get("observed_main_commit") != RULESPEC_COMMIT
        or rulespec.get("claim_mode") != "attested"
    ):
        raise ClosureError("DE RuleSpec repository pin drifted")
    modules = rulespec.get("modules")
    if not isinstance(modules, list):
        raise ClosureError("rulespec modules must be an array")
    citations = [row.get("citation_path") for row in modules if isinstance(row, dict)]
    expected_citations = sorted(
        {citation for values in PROGRAM_SOURCE_PATHS.values() for citation in values}
    )
    if citations != expected_citations:
        raise ClosureError("rulespec module citation set or order drifted")
    indexed: dict[str, dict] = {}
    for module in modules:
        if not isinstance(module, dict):
            raise ClosureError("rulespec modules contains a non-object entry")
        citation = module["citation_path"]
        if citation not in rows:
            raise ClosureError(
                f"RuleSpec module citation is absent from corpus: {citation}"
            )
        classification = module.get("classification")
        signature_state = module.get("signature_state")
        if module.get("claim_mode") != "attested":
            raise ClosureError(f"{citation} module observation must be attested")
        if classification not in CLASSIFICATIONS - {"excluded"}:
            raise ClosureError(f"{citation} has invalid module classification")
        if signature_state not in SIGNATURE_STATES:
            raise ClosureError(f"{citation} has invalid signature_state")
        _require_nonempty(module.get("reason"), f"{citation} module reason")
        if classification == "encoded" and signature_state == "not_applicable":
            raise ClosureError(
                f"encoded module {citation} cannot waive signature state"
            )
        if classification == "pending" and signature_state == "signed":
            raise ClosureError(f"pending module {citation} cannot be signed")
        artifact = module.get("artifact")
        if signature_state == "signed":
            if not isinstance(artifact, dict):
                raise ClosureError(f"signed module {citation} lacks artifact pins")
            if artifact.get("commit") != RULESPEC_COMMIT:
                raise ClosureError(f"signed module {citation} is not pinned to main")
            _require_nonempty(artifact.get("path"), f"{citation} artifact path")
            _require_hash(artifact.get("sha256"), f"{citation} artifact sha256")
            _require_nonempty(
                artifact.get("manifest_path"), f"{citation} manifest path"
            )
            _require_hash(
                artifact.get("manifest_sha256"), f"{citation} manifest sha256"
            )
        elif artifact is not None:
            if not isinstance(artifact, dict):
                raise ClosureError(f"{citation} artifact pin must be an object")
            _require_nonempty(artifact.get("ref"), f"{citation} artifact ref")
            _require_nonempty(artifact.get("path"), f"{citation} artifact path")
            _require_hash(artifact.get("sha256"), f"{citation} artifact sha256")
        indexed[citation] = module

    estg = indexed[ESTG_66]
    if (
        estg.get("classification") != "encoded"
        or estg.get("signature_state") != "signed"
    ):
        raise ClosureError(
            "EStG 66 must be encoded and signed on the pinned main commit "
            "(rulespec-de PR #42, 2026-08-19); the pre-signing pending state "
            "is no longer valid"
        )
    return indexed


def _validate_evidence_root(
    evidence: dict,
    rows: dict[str, dict],
    children: dict[str, list[str]],
) -> dict:
    citation = evidence.get("citation_path")
    if citation != STEFEG_ROOT:
        raise ClosureError(f"unexpected DE evidence root {citation!r}")
    if citation not in rows:
        raise ClosureError(f"evidence root does not resolve exactly: {citation}")
    if evidence.get("resolution") != "self_and_descendants":
        raise ClosureError("SteFeG evidence must resolve by parent-linked descendants")
    _require_nonempty(evidence.get("reason"), "SteFeG evidence reason")
    descendants = _descendants(citation, children)
    if descendants != [STEFEG_CONTENT]:
        raise ClosureError("SteFeG evidence descendant denominator drifted")
    child = rows[STEFEG_CONTENT]
    if child.get("body_length", 0) <= 0 or child.get("body_sha256") is None:
        raise ClosureError("SteFeG evidence child has no content-bearing body")
    targets = rows[citation].get("amendment_targets")
    if not isinstance(targets, list) or targets != sorted(set(targets)):
        raise ClosureError("SteFeG amendment targets must be unique and sorted")
    if ESTG_66 not in targets:
        raise ClosureError("SteFeG evidence does not target EStG 66")
    return {
        "citation_path": citation,
        "classification": "evidence",
        "classification_claim_mode": "attested",
        "reason": evidence["reason"],
        "resolution": "self_and_descendants",
        "resolution_claim_mode": "computed",
        "resolved_citation_paths": [citation, *descendants],
        "content_sha256": child["body_sha256"],
        "source_sha256": child["source_sha256"],
    }


def _validate_boundaries(
    program: str,
    raw_boundaries: object,
    rows: dict[str, dict],
) -> list[dict]:
    if not isinstance(raw_boundaries, list):
        raise ClosureError(f"{program}: boundaries must be an array")
    inputs = [row.get("input") for row in raw_boundaries if isinstance(row, dict)]
    if inputs != sorted(set(inputs)):
        raise ClosureError(f"{program}: boundary inputs must be unique and sorted")
    if program == "de/kindergeld":
        citations = tuple(
            row.get("citation_path") for row in raw_boundaries if isinstance(row, dict)
        )
        if citations != KINDERGELD_BOUNDARIES:
            raise ClosureError("Kindergeld boundary citation denominator drifted")
    rendered = []
    for boundary in raw_boundaries:
        if not isinstance(boundary, dict):
            raise ClosureError(f"{program}: boundary contains a non-object entry")
        if boundary.get("classification") != "excluded-with-reason":
            raise ClosureError(f"{program}: boundary must be excluded-with-reason")
        if boundary.get("assignment_required") is not True:
            raise ClosureError(
                f"{program}: every boundary input must require assignment"
            )
        _require_nonempty(boundary.get("input"), f"{program} boundary input")
        _require_nonempty(boundary.get("reason"), f"{program} boundary reason")
        citation = boundary.get("citation_path")
        if citation is not None and citation not in rows:
            raise ClosureError(
                f"{program}: boundary citation does not resolve exactly: {citation}"
            )
        if citation is None:
            _require_nonempty(boundary.get("basis"), f"{program} boundary basis")
        rendered.append(
            {
                "assignment_required": True,
                "basis": boundary.get("basis"),
                "citation_path": citation,
                "claim_mode": "attested",
                "classification": "excluded-with-reason",
                "input": boundary["input"],
                "reason": boundary["reason"],
            }
        )
    return rendered


def build(source: dict) -> dict:
    """Validate the pinned denominator and compute per-program source closure."""

    if source.get("schema") != SOURCE_SCHEMA:
        raise ClosureError("unexpected DE closure source schema")
    if source.get("jurisdiction") != "de" or source.get("period") != "2025":
        raise ClosureError("DE closure jurisdiction or period drifted")
    if source.get("resolution") != RESOLUTION_PROTOCOL:
        raise ClosureError("DE citation resolution protocol drifted")

    corpus = source.get("corpus")
    if not isinstance(corpus, dict):
        raise ClosureError("corpus snapshot must be an object")
    if (
        corpus.get("repository") != "TheAxiomFoundation/axiom-corpus"
        or corpus.get("commit") != CORPUS_COMMIT
        or corpus.get("release") != RELEASE
        or corpus.get("release_content_sha256") != RELEASE_CONTENT_SHA256
        or corpus.get("release_selector_sha256") != RELEASE_SELECTOR_SHA256
    ):
        raise ClosureError("DE corpus release pin drifted")
    _validate_pinned_files(
        corpus.get("inventories"), EXPECTED_INVENTORIES, "inventories"
    )
    _validate_pinned_files(
        corpus.get("provision_sources"),
        EXPECTED_PROVISION_SOURCES,
        "provision sources",
    )
    rows, children = _row_index(corpus)
    modules = _validate_module_catalog(source, rows)

    raw_programs = source.get("programs")
    if not isinstance(raw_programs, dict) or set(raw_programs) != set(
        PROGRAM_ROOT_NODES
    ):
        raise ClosureError("DE program declaration set drifted")
    programs: dict[str, dict] = {}
    all_pending: set[str] = set()
    all_signature_pending: set[str] = set()
    for program in sorted(PROGRAM_ROOT_NODES):
        declaration = raw_programs[program]
        if not isinstance(declaration, dict):
            raise ClosureError(f"{program}: declaration must be an object")
        if declaration.get("claim_mode") != "attested":
            raise ClosureError(f"{program}: subgraph declaration must be attested")
        root_nodes = declaration.get("root_nodes")
        if root_nodes != list(PROGRAM_ROOT_NODES[program]):
            raise ClosureError(f"{program}: root node denominator drifted")
        raw_sources = declaration.get("declared_sources")
        if not isinstance(raw_sources, list):
            raise ClosureError(f"{program}: declared_sources must be an array")
        source_paths = tuple(
            row.get("citation_path") for row in raw_sources if isinstance(row, dict)
        )
        if source_paths != PROGRAM_SOURCE_PATHS[program]:
            raise ClosureError(f"{program}: declared citation root set drifted")
        source_rows = []
        for declared in raw_sources:
            if not isinstance(declared, dict):
                raise ClosureError(f"{program}: declared source must be an object")
            citation = declared["citation_path"]
            if citation not in rows:
                raise ClosureError(
                    f"{program}: source citation does not resolve exactly: {citation}"
                )
            role = _require_nonempty(
                declared.get("role"), f"{program} source role for {citation}"
            )
            module = modules[citation]
            state = (
                "encoded_pending_signature"
                if module["classification"] == "encoded"
                and module["signature_state"] == "pending"
                else module["classification"]
            )
            source_rows.append(
                {
                    "citation_path": citation,
                    "claim_mode": "attested",
                    "classification": module["classification"],
                    "reason": module["reason"],
                    "role": role,
                    "signature_state": module["signature_state"],
                    "state": state,
                }
            )
        raw_evidence = declaration.get("evidence_roots")
        if not isinstance(raw_evidence, list):
            raise ClosureError(f"{program}: evidence_roots must be an array")
        evidence_paths = tuple(
            row.get("citation_path") for row in raw_evidence if isinstance(row, dict)
        )
        if evidence_paths != PROGRAM_EVIDENCE_ROOTS[program]:
            raise ClosureError(f"{program}: evidence root set drifted")
        evidence_rows = [
            _validate_evidence_root(evidence, rows, children)
            for evidence in raw_evidence
        ]
        boundaries = _validate_boundaries(program, declaration.get("boundaries"), rows)

        pending = sorted(
            row["citation_path"]
            for row in source_rows
            if row["classification"] == "pending"
        )
        signature_pending = sorted(
            row["citation_path"]
            for row in source_rows
            if row["signature_state"] == "pending"
        )
        all_pending.update(pending)
        all_signature_pending.update(signature_pending)
        status_counts = Counter(row["classification"] for row in source_rows)
        status_counts["excluded"] += len(boundaries)
        status_counts["evidence"] += len(evidence_rows)
        signature_counts = Counter(row["signature_state"] for row in source_rows)
        source_closed = not pending
        citation_paths = sorted(
            {
                *(row["citation_path"] for row in source_rows),
                *(
                    citation
                    for evidence in evidence_rows
                    for citation in evidence["resolved_citation_paths"]
                ),
                *(
                    boundary["citation_path"]
                    for boundary in boundaries
                    if boundary["citation_path"] is not None
                ),
            }
        )
        citation_roots = {
            *(row["citation_path"] for row in source_rows),
            *(row["citation_path"] for row in evidence_rows),
            *(
                boundary["citation_path"]
                for boundary in boundaries
                if boundary["citation_path"] is not None
            ),
        }
        programs[program] = {
            "blockers": [
                f"{row['citation_path']}: {row['reason']}"
                for row in source_rows
                if row["classification"] == "pending"
            ],
            "boundaries": boundaries,
            "boundary_count": len(boundaries),
            "by_signature_state": {
                name: signature_counts[name]
                for name in ("signed", "pending", "not_applicable")
            },
            "by_status": {
                name: status_counts[name]
                for name in ("encoded", "excluded", "evidence", "pending")
            },
            "citation_root_count": len(citation_roots),
            "citation_paths": citation_paths,
            "closed": source_closed,
            "closed_claim_mode": "computed",
            "closure_status": "closed" if source_closed else "open",
            "declared_sources": source_rows,
            "evidence_roots": evidence_rows,
            "pending_citations": pending,
            "root_node_count": len(root_nodes),
            "root_nodes": root_nodes,
            "signature_blockers": [
                f"{citation}: signed RuleSpec artifact has not landed"
                for citation in signature_pending
            ],
            "signature_pending_citations": signature_pending,
            "source_closed": source_closed,
            "source_closed_claim_mode": "computed",
            "subgraph_sha256": _canonical_sha256(
                {
                    "boundaries": boundaries,
                    "corpus_release_content_sha256": RELEASE_CONTENT_SHA256,
                    "declared_sources": source_rows,
                    "evidence_roots": evidence_rows,
                    "resolution": RESOLUTION_PROTOCOL,
                    "root_nodes": root_nodes,
                }
            ),
            "unresolved_sources": pending,
        }

    return {
        "schema": SUMMARY_SCHEMA,
        "jurisdiction": "de",
        "period": "2025",
        "closed": all(row["source_closed"] for row in programs.values()),
        "closed_claim_mode": "computed",
        "claim_modes": {
            "attested": (
                "corpus and RuleSpec pins, module observations, and declared "
                "subgraph boundaries"
            ),
            "computed": (
                "exact citation resolution, source-closure verdicts, pending "
                "sets, counts, and digests"
            ),
        },
        "corpus_commit": CORPUS_COMMIT,
        "corpus_release": RELEASE,
        "corpus_release_content_sha256": RELEASE_CONTENT_SHA256,
        "pending_citations": sorted(all_pending),
        "programs": programs,
        "resolution": {
            **RESOLUTION_PROTOCOL,
            "sha256": _canonical_sha256(RESOLUTION_PROTOCOL),
        },
        "rulespec_commit": RULESPEC_COMMIT,
        "signature_pending_citations": sorted(all_signature_pending),
        "source": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(SOURCE_PATH.read_bytes()),
        },
    }


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        summary = build(load_source())
    except (OSError, json.JSONDecodeError, ClosureError) as exc:
        print(f"DE closure ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = _render(summary)
    if args.check:
        if not SUMMARY_PATH.exists() or SUMMARY_PATH.read_text() != rendered:
            print("DE closure summary drifted", file=sys.stderr)
            return 1
        print("DE closure summary up to date")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(rendered)
    print(f"wrote {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
