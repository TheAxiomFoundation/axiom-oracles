#!/usr/bin/env python3
"""Build the body-hash ledger for the adopted NZ legal spine.

The working scope is the 174-root DE-style dependency subgraph ratified by
Brief C1.  173 roots are reproduced from the signed
``nz-rulespec-2026-07-25`` corpus release.  The one off-release amendment
root is reproduced from a committed excerpt of the retained official PCO API
XML and its byte receipt.  ``--check`` performs the full reproduction and
fails on any row, status, body hash, source receipt, or scope-count drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import nz_corpus_gap_scan as corpus_gap
from nz_spine import (
    DEPENDENCY_ROOT_SCOPE_COUNTS,
    EXPECTED_CANDIDATE_CITATIONS,
    EXPECTED_DEPENDENCY_ROOT_CITATIONS,
    EXPECTED_OFF_RELEASE_EXACT_CITATIONS,
    WHOLE_GOVERNING_ACT_SCOPE_COUNTS,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULESPEC_ROOT = corpus_gap.DEFAULT_RULESPEC_ROOT
DEFAULT_CORPUS_ROOT = corpus_gap.DEFAULT_CORPUS_ROOT
DEFAULT_OUTPUT = REPO_ROOT / "closure" / "nz" / "spine-ledger.json"
OFFICIAL_EXCERPT = REPO_ROOT / "closure" / "nz" / "sources" / "taxation-2025-s105.xml"
OFFICIAL_RECEIPT = (
    REPO_ROOT / "closure" / "nz" / "sources" / "taxation-2025-s105-receipt.json"
)
DEFAULT_OFFICIAL_XML = (
    Path.home()
    / "_axiom-worktrees"
    / "nz-legislation-api-downloads"
    / "2026-06-16-pco-latest"
    / "xml"
    / "act"
    / "public"
    / "2025"
    / "9"
    / "act_public_2025_9_en_2026-03-31B.xml"
)
DEFAULT_ACT_MANIFEST = (
    Path.home()
    / "_axiom-worktrees"
    / "nz-legislation-api-downloads"
    / "2026-06-16-pco-latest"
    / "manifest-act.json"
)

SCHEMA = "axiom_oracles.nz_spine_ledger.v1"
EXPECTED_TOTAL = 174
EXPECTED_ENCODED = 57
EXPECTED_PENDING = 117
STRUCTURAL_ROOT = "nz/statute/act/public/2018/0032/schedule/5"
STRUCTURAL_DESCENDANTS = tuple(
    f"{STRUCTURAL_ROOT}/part/{number}" for number in (1, 2, 3)
)
OFF_RELEASE_ROOT = EXPECTED_OFF_RELEASE_EXACT_CITATIONS[0]


class SpineLedgerError(RuntimeError):
    """Raised when a source, spine row, or committed artifact drifts."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpineLedgerError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return _sha256(path.read_bytes())
    except OSError as exc:
        raise SpineLedgerError(f"cannot hash {path}: {exc}") from exc


def _canonical_sha256(value: Any) -> str:
    raw = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return _sha256(raw)


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpineLedgerError(f"cannot read {label} ({path}): {exc}") from exc
    if not isinstance(value, dict):
        raise SpineLedgerError(f"{label} must contain an object")
    return value


def _element_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _render_legal_text(element: ET.Element) -> str:
    """Match axiom-corpus' pinned NZ PCO ``prov.body`` renderer."""

    skipped_tags = {
        "amends-note",
        "editorial-note",
        "history",
        "history-note",
        "ird.aids",
        "notes",
        "struckoutwords",
        "summary",
    }
    block_tags = {
        "amend",
        "def-para",
        "eqn",
        "eqn-line",
        "example",
        "heading",
        "item",
        "label-para",
        "label-para.crosshead",
        "legtable",
        "list",
        "para",
        "proviso",
        "quote",
        "row",
        "subheading",
        "subprov",
        "subprov.crosshead",
        "table",
        "tbody",
        "tgroup",
        "thead",
        "variable-def",
    }

    def clean(value: str | None) -> str:
        return " ".join((value or "").split())

    def join(parts: list[tuple[str, bool]]) -> str:
        output = ""
        prior_block = False
        for value, is_block in parts:
            value = value.strip()
            if not value:
                continue
            if output:
                separator = "\n" if prior_block or is_block else " "
                if output.rsplit("\n", 1)[-1].strip().startswith("(") and is_block:
                    separator = " "
                output += separator
            output += value
            prior_block = is_block
        return "\n".join(
            line
            for line in (" ".join(line.split()) for line in output.splitlines())
            if line
        )

    def render(node: ET.Element) -> str:
        tag = _local_name(node.tag)
        if tag in skipped_tags:
            return ""
        if tag == "brk":
            return "\n"
        if tag == "row":
            cells = [child for child in node if _local_name(child.tag) == "entry"]
            cells = cells or list(node)
            rendered_cells = [
                rendered
                for cell in cells
                if (rendered := " ".join(render(cell).split()))
            ]
            return " | ".join(rendered_cells)

        parts: list[tuple[str, bool]] = []
        if value := clean(node.text):
            parts.append((value, False))
        for child in node:
            child_text = render(child)
            if child_text.strip():
                parts.append((child_text, _local_name(child.tag) in block_tags))
            if tail := clean(child.tail):
                parts.append((tail, False))
        return join(parts)

    return render(element).strip()


def _find_section_105(root: ET.Element) -> ET.Element:
    matches: list[ET.Element] = []
    for element in root.iter():
        if _local_name(element.tag) != "prov":
            continue
        label = next(
            (child for child in element if _local_name(child.tag) == "label"),
            None,
        )
        if label is not None and _element_text(label) == "105":
            matches.append(element)
    _require(len(matches) == 1, "official XML must contain exactly one section 105")
    return matches[0]


def _official_row(
    *, official_xml: Path, act_manifest: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _load_mapping(OFFICIAL_RECEIPT, "official section 105 receipt")
    capture = receipt.get("capture")
    excerpt_receipt = receipt.get("excerpt")
    instrument = receipt.get("instrument")
    _require(isinstance(capture, dict), "official receipt lacks capture")
    _require(isinstance(excerpt_receipt, dict), "official receipt lacks excerpt")
    _require(isinstance(instrument, dict), "official receipt lacks instrument")
    _require(
        receipt.get("schema") == "axiom_oracles.nz_official_xml_receipt.v1",
        "official receipt schema drifted",
    )
    _require(
        instrument
        == {
            "legislation_status": "in_force",
            "publisher": "Parliamentary Counsel Office",
            "stable_source_url": (
                "https://www.legislation.govt.nz/act/public/2025/0009/latest/"
                "LMS1000039.html"
            ),
            "title": (
                "Taxation (Annual Rates for 2024–25, Emergency Response, and "
                "Remedial Measures) Act 2025"
            ),
            "version_id": "act_public_2025_9_en_2026-03-31B",
            "work_id": "act_public_2025_9",
        },
        "official section 105 instrument receipt drifted",
    )
    excerpt_raw = OFFICIAL_EXCERPT.read_bytes()
    _require(
        _sha256(excerpt_raw) == excerpt_receipt.get("sha256"),
        "committed section 105 excerpt bytes drifted",
    )
    _require(
        _file_sha256(official_xml) == capture.get("source_xml_sha256"),
        "retained official Act XML bytes drifted",
    )
    _require(
        official_xml.stat().st_size == capture.get("source_xml_bytes"),
        "retained official Act XML size drifted",
    )
    _require(
        _file_sha256(act_manifest) == capture.get("download_manifest_sha256"),
        "retained official Act manifest bytes drifted",
    )
    try:
        source_section = _find_section_105(ET.parse(official_xml).getroot())
        excerpt_section = ET.fromstring(excerpt_raw)
    except (OSError, ET.ParseError) as exc:
        raise SpineLedgerError(f"cannot parse official section 105 XML: {exc}") from exc
    _require(
        ET.tostring(source_section, encoding="utf-8")
        == ET.tostring(excerpt_section, encoding="utf-8"),
        "committed section 105 excerpt is not the retained official XML element",
    )
    body_elements = [
        child for child in excerpt_section if _local_name(child.tag) == "prov.body"
    ]
    heading_elements = [
        child for child in excerpt_section if _local_name(child.tag) == "heading"
    ]
    _require(len(body_elements) == 1, "official section 105 lacks one prov.body")
    _require(len(heading_elements) == 1, "official section 105 lacks one heading")
    normalized_text = _render_legal_text(body_elements[0])
    body_raw = normalized_text.encode("utf-8")
    body_sha = _sha256(body_raw)
    _require(
        body_sha == excerpt_receipt.get("body_sha256"),
        "official section 105 normalized body hash drifted",
    )
    _require(
        len(body_raw) == excerpt_receipt.get("body_utf8_bytes"),
        "official section 105 normalized body byte count drifted",
    )
    _require(
        excerpt_receipt.get("body_renderer")
        == (
            "axiom-corpus@2d077803ee17f921c30014b9e98ae9ee3b612512 "
            "src/axiom_corpus/converters/nz_pco.py "
            "render_nz_pco_legal_text over prov.body"
        ),
        "official section 105 body renderer receipt drifted",
    )
    _require(
        excerpt_receipt.get("citation_path") == OFF_RELEASE_ROOT,
        "official receipt citation path drifted",
    )
    row = {
        "citation_path": OFF_RELEASE_ROOT,
        "instrument": instrument.get("title"),
        "status": "pending",
        "reason": "dependency root is not yet encoded",
        "heading": _element_text(heading_elements[0]),
        "body_sha256": body_sha,
        "body_utf8_bytes": len(body_raw),
        "resolution": "self",
        "source_class": "official_web_only",
        "source_url": instrument.get("stable_source_url"),
        "source_receipt": str(OFFICIAL_RECEIPT.relative_to(REPO_ROOT)),
        "source_excerpt": str(OFFICIAL_EXCERPT.relative_to(REPO_ROOT)),
        "source_excerpt_sha256": _sha256(excerpt_raw),
    }
    source = {
        "citation_path": OFF_RELEASE_ROOT,
        "official_url": instrument.get("stable_source_url"),
        "xml_url": capture.get("xml_url"),
        "source_xml_sha256": capture.get("source_xml_sha256"),
        "source_xml_bytes": capture.get("source_xml_bytes"),
        "download_manifest_sha256": capture.get("download_manifest_sha256"),
        "excerpt_path": str(OFFICIAL_EXCERPT.relative_to(REPO_ROOT)),
        "excerpt_sha256": _sha256(excerpt_raw),
        "text_extraction": (
            "axiom-corpus NZ PCO legal-text renderer over the exact section "
            "<prov.body> element"
        ),
    }
    return row, source


def _owner(citation_path: str) -> Any:
    matches = [
        scope
        for scope in DEPENDENCY_ROOT_SCOPE_COUNTS
        if citation_path.startswith(scope.citation_prefix)
    ]
    _require(len(matches) == 1, f"{citation_path}: expected exactly one owner")
    return matches[0]


def _release_artifact_for(row: Mapping[str, Any], release: Mapping[str, Any]) -> str:
    version = row.get("version")
    document_class = row.get("document_class")
    matches = [
        str(artifact["path"])
        for artifact in release["provision_artifacts"]
        if isinstance(version, str)
        and isinstance(document_class, str)
        and f"/{document_class}/" in str(artifact["path"])
        and version in str(artifact["path"])
    ]
    _require(
        len(matches) == 1, f"{row.get('citation_path')}: release artifact unresolved"
    )
    return matches[0]


def _counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    statuses = Counter(str(row.get("status")) for row in rows)
    return {
        "total": sum(statuses.values()),
        "encoded": statuses["encoded"],
        "classified": statuses["classified"],
        "excluded": statuses["excluded"],
        "pending": statuses["pending"],
    }


def build_document(
    *,
    rulespec_root: Path,
    corpus_root: Path,
    official_xml: Path,
    act_manifest: Path,
) -> dict[str, Any]:
    try:
        release, artifact_paths = corpus_gap._release_inventory(
            rulespec_root, corpus_root
        )
        corpus_rows = corpus_gap._read_provisions(artifact_paths)
    except corpus_gap.CorpusGapError as exc:
        raise SpineLedgerError(str(exc)) from exc

    by_path: dict[str, list[dict[str, Any]]] = {}
    for row in corpus_rows:
        citation = row.get("citation_path")
        if isinstance(citation, str):
            by_path.setdefault(citation, []).append(row)

    adopted_paths = tuple(
        sorted(
            set(EXPECTED_CANDIDATE_CITATIONS) | set(EXPECTED_DEPENDENCY_ROOT_CITATIONS)
        )
    )
    _require(len(adopted_paths) == EXPECTED_TOTAL, "adopted scope denominator drifted")
    rows: list[dict[str, Any]] = []
    for citation in adopted_paths:
        if citation == OFF_RELEASE_ROOT:
            continue
        matches = by_path.get(citation, [])
        _require(len(matches) == 1, f"{citation}: expected one pinned release row")
        source = matches[0]
        owner = _owner(citation)
        body = source.get("body")
        structural = citation == STRUCTURAL_ROOT
        if structural:
            _require(
                body is None, f"{citation}: structural root unexpectedly has a body"
            )
            descendants: list[dict[str, Any]] = []
            for descendant_path in STRUCTURAL_DESCENDANTS:
                descendant_matches = by_path.get(descendant_path, [])
                _require(
                    len(descendant_matches) == 1,
                    f"{descendant_path}: structural descendant missing",
                )
                descendant_body = descendant_matches[0].get("body")
                _require(
                    isinstance(descendant_body, str) and bool(descendant_body.strip()),
                    f"{descendant_path}: structural descendant body missing",
                )
                descendants.append(
                    {
                        "citation_path": descendant_path,
                        "body_sha256": _sha256(descendant_body.encode("utf-8")),
                        "body_utf8_bytes": len(descendant_body.encode("utf-8")),
                    }
                )
            body_sha: str | None = None
            body_bytes = 0
            resolution = "self_and_descendants"
        else:
            _require(
                isinstance(body, str) and bool(body.strip()),
                f"{citation}: pinned release body is empty",
            )
            descendants = []
            body_sha = _sha256(body.encode("utf-8"))
            body_bytes = len(body.encode("utf-8"))
            resolution = "self"
        status = "encoded" if citation in EXPECTED_CANDIDATE_CITATIONS else "pending"
        row = {
            "citation_path": citation,
            "instrument": owner.instrument,
            "status": status,
            "reason": (
                "exact root is cited by the encoded program subgraph"
                if status == "encoded"
                else "dependency root is not yet encoded"
            ),
            "heading": source.get("heading"),
            "body_sha256": body_sha,
            "body_utf8_bytes": body_bytes,
            "resolution": resolution,
            "source_class": "pinned_corpus_release",
            "source_url": source.get("source_url"),
            "release_artifact": _release_artifact_for(source, release),
        }
        if descendants:
            row["resolved_descendants"] = descendants
            row["resolved_descendants_sha256"] = _canonical_sha256(descendants)
        rows.append(row)

    official_row, official_source = _official_row(
        official_xml=official_xml, act_manifest=act_manifest
    )
    rows.append(official_row)
    rows.sort(key=lambda row: str(row["citation_path"]))
    citations = [str(row["citation_path"]) for row in rows]
    _require(citations == list(adopted_paths), "spine ledger has a silent or extra row")
    counts = _counts(rows)
    _require(
        counts
        == {
            "total": EXPECTED_TOTAL,
            "encoded": EXPECTED_ENCODED,
            "classified": 0,
            "excluded": 0,
            "pending": EXPECTED_PENDING,
        },
        f"spine status counts drifted: {counts!r}",
    )

    instrument_counts: list[dict[str, Any]] = []
    for scope in DEPENDENCY_ROOT_SCOPE_COUNTS:
        owned = [
            row
            for row in rows
            if str(row["citation_path"]).startswith(scope.citation_prefix)
        ]
        status_counts = _counts(owned)
        _require(status_counts["total"] == scope.total, f"{scope.key}: total drifted")
        _require(
            status_counts["encoded"] == scope.encoded
            and status_counts["pending"] == scope.pending,
            f"{scope.key}: disposition drifted",
        )
        instrument_counts.append(
            {
                "key": scope.key,
                "instrument": scope.instrument,
                "citation_prefix": scope.citation_prefix,
                **status_counts,
            }
        )

    conservative_counts = {
        "total": sum(row.total for row in WHOLE_GOVERNING_ACT_SCOPE_COUNTS),
        "encoded": sum(row.encoded for row in WHOLE_GOVERNING_ACT_SCOPE_COUNTS),
        "classified": 0,
        "excluded": 0,
        "pending": sum(row.pending for row in WHOLE_GOVERNING_ACT_SCOPE_COUNTS),
    }
    _require(
        conservative_counts
        == {
            "total": 4707,
            "encoded": 57,
            "classified": 0,
            "excluded": 0,
            "pending": 4650,
        },
        "whole-Act alternative counts drifted",
    )

    document = {
        "schema": SCHEMA,
        "scope_choice": {
            "key": "de_precedent_dependency_root_subgraph",
            "adopted": True,
            "total": EXPECTED_TOTAL,
            "lower_bound": True,
            "reason": (
                "Adopt the exact transitive program-root and strict law-derived "
                "dependency roots. This follows DE's explicit scoped-root shape "
                "without treating the whole host Act as silently encoded. Pending "
                "rows remain visible, and a later adjudication can widen the set."
            ),
            "de_precedent": {
                "merge_commit": "e77c93099",
                "pull_request": 485,
                "source_artifact": "closure/de/source.json",
                "source_shape": (
                    "programs.de/kindergeld root_nodes plus evidence_roots "
                    "resolution=self_and_descendants"
                ),
                "certificate_artifact": "certificates/de-kindergeld.json",
                "certificate_scope": "executable.subgraph.scope=amount",
                "documentation": "docs/de-kindergeld-certification.md",
                "qualification": (
                    "The precedent supports explicit subgraph scope only; its later-"
                    "corrected treatment of law-derived boundary inputs is not adopted."
                ),
            },
        },
        "complete": False,
        "scope_adjudication_pending": False,
        "body_hash_ledger_complete": True,
        "blockers": ["spine_pending_provisions"],
        "counts": counts,
        "source_partition": {
            "pinned_corpus_release": 173,
            "official_web_only": 1,
        },
        "corpus_release": release,
        "official_web_only_root": official_source,
        "instrument_counts": instrument_counts,
        "whole_act_conservative_alternative": {
            "adopted": False,
            "counts": conservative_counts,
            "governing_acts_only": {
                "total": 4635,
                "encoded": 49,
                "pending": 4586,
            },
            "reason": (
                "Disclosed literal whole-governing-Act reading. It can replace the "
                "working scope without changing row or hash conventions."
            ),
        },
        "rowset_sha256": _canonical_sha256(rows),
        "rows": rows,
    }
    validate_document(document)
    return document


def validate_document(document: Mapping[str, Any]) -> None:
    """Validate the committed ledger without reading either sibling clone."""

    _require(document.get("schema") == SCHEMA, "spine ledger schema drifted")
    rows = document.get("rows")
    _require(isinstance(rows, list), "spine ledger rows must be a list")
    expected_paths = sorted(
        set(EXPECTED_CANDIDATE_CITATIONS) | set(EXPECTED_DEPENDENCY_ROOT_CITATIONS)
    )
    actual_paths = [
        str(row.get("citation_path")) for row in rows if isinstance(row, Mapping)
    ]
    _require(len(actual_paths) == len(rows), "spine ledger contains a non-object row")
    _require(
        actual_paths == expected_paths,
        "spine ledger exact 174-root set has a silent, duplicate, or extra row",
    )
    for row in rows:
        citation = str(row["citation_path"])
        expected_status = (
            "encoded" if citation in EXPECTED_CANDIDATE_CITATIONS else "pending"
        )
        _require(
            row.get("status") == expected_status,
            f"{citation}: spine status drifted",
        )
        body_sha = row.get("body_sha256")
        body_bytes = row.get("body_utf8_bytes")
        _require(
            isinstance(body_bytes, int)
            and not isinstance(body_bytes, bool)
            and body_bytes >= 0,
            f"{citation}: body byte count is invalid",
        )
        if citation == STRUCTURAL_ROOT:
            _require(
                body_sha is None and body_bytes == 0,
                f"{citation}: structural root must have a null own-body hash",
            )
            descendants = row.get("resolved_descendants")
            _require(
                isinstance(descendants, list)
                and [item.get("citation_path") for item in descendants]
                == list(STRUCTURAL_DESCENDANTS),
                f"{citation}: structural descendants drifted",
            )
            _require(
                row.get("resolved_descendants_sha256")
                == _canonical_sha256(descendants),
                f"{citation}: descendant hash ledger drifted",
            )
        else:
            _require(
                isinstance(body_sha, str)
                and len(body_sha) == 64
                and all(character in "0123456789abcdef" for character in body_sha)
                and body_bytes > 0,
                f"{citation}: body hash is invalid",
            )
    expected_counts = {
        "total": EXPECTED_TOTAL,
        "encoded": EXPECTED_ENCODED,
        "classified": 0,
        "excluded": 0,
        "pending": EXPECTED_PENDING,
    }
    _require(document.get("counts") == expected_counts, "spine counts drifted")
    _require(_counts(rows) == expected_counts, "spine row counts do not reconcile")
    _require(
        document.get("source_partition")
        == {"pinned_corpus_release": 173, "official_web_only": 1},
        "spine source partition drifted",
    )
    scope = document.get("scope_choice")
    _require(
        isinstance(scope, Mapping)
        and scope.get("adopted") is True
        and scope.get("key") == "de_precedent_dependency_root_subgraph"
        and scope.get("total") == EXPECTED_TOTAL,
        "spine scope choice drifted",
    )
    _require(
        document.get("complete") is False
        and document.get("scope_adjudication_pending") is False
        and document.get("body_hash_ledger_complete") is True
        and document.get("blockers") == ["spine_pending_provisions"],
        "spine completion state drifted",
    )
    alternative = document.get("whole_act_conservative_alternative")
    _require(
        isinstance(alternative, Mapping)
        and alternative.get("adopted") is False
        and alternative.get("counts")
        == {
            "total": 4707,
            "encoded": 57,
            "classified": 0,
            "excluded": 0,
            "pending": 4650,
        },
        "whole-Act alternative drifted",
    )
    _require(
        document.get("rowset_sha256") == _canonical_sha256(rows),
        "spine rowset hash drifted",
    )


def render(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--official-xml", type=Path, default=DEFAULT_OFFICIAL_XML)
    parser.add_argument("--act-manifest", type=Path, default=DEFAULT_ACT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        document = build_document(
            rulespec_root=args.rulespec_root,
            corpus_root=args.corpus_root,
            official_xml=args.official_xml,
            act_manifest=args.act_manifest,
        )
        rendered = render(document)
        if args.check:
            try:
                committed = args.output.read_text(encoding="utf-8")
            except OSError as exc:
                raise SpineLedgerError(
                    f"cannot read committed spine ledger {args.output}: {exc}"
                ) from exc
            if committed != rendered:
                raise SpineLedgerError(
                    "spine ledger drift: run scripts/nz_spine_ledger.py"
                )
            print(
                "NZ spine ledger OK: 174 rows, 57 encoded, 117 pending, "
                "173 corpus + 1 official-web-only"
            )
            return 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output}: 174 rows")
        return 0
    except (OSError, SpineLedgerError) as exc:
        print(f"NZ spine ledger ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
