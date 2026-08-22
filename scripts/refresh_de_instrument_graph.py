#!/usr/bin/env python3
"""Capture the measured DE instrument-discovery graph.

This is the network-using ops producer.  The closure-ledger producer consumes
only the committed JSON snapshot and must never import this module.

Corpus discovery is reproducible: corpus bytes are read with ``git show`` at
the exact commit pinned by ``closure/de/source.json``.  Subject-matter URLs
are attempted only during capture; ``--offline`` records each attempt as
unretrieved instead of fabricating a result.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "closure" / "de" / "source.json"
DEFAULT_QUERY_SET = REPO_ROOT / "conformance" / "closure" / "de-subject-matter-queries.json"
DEFAULT_OUTPUT = REPO_ROOT / "conformance" / "closure" / "de-instrument-graph.json"
DEFAULT_CORPUS_ROOT = Path.home() / "TheAxiomFoundation" / "axiom-corpus-de-wave"
CORPUS_ROOT_ENV = "AXIOM_CORPUS_DE_ROOT"

SCHEMA = "axiom_oracles.closure.de_instrument_graph.v1"
SOURCE_SCHEMA = "axiom_oracles.de_closure_source.v1"
QUERY_SCHEMA = "axiom_oracles.closure.de_subject_query_set.v1"
PROGRAMS = (
    "de/kindergeld",
    "de/rv-employee-contribution",
    "de/unterhaltsvorschuss",
)
PROGRAM_PREFIX = {
    "de/kindergeld": "de-kg",
    "de/rv-employee-contribution": "de-rv",
    "de/unterhaltsvorschuss": "de-uhv",
}
RV_ROOTS = {
    "de/regulation/bsv-2018/1",
    "de/regulation/svbezgrv-2025/4",
    "de/statute/sgb-6/168",
}
MAX_FETCH_BYTES = 64 * 1024 * 1024
DEFAULT_TIMEOUT = 20.0


class CaptureError(RuntimeError):
    """A pinned input or generated snapshot is invalid."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _add_receipt(value: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(value)
    value.pop("receipt_sha256", None)
    value["receipt_sha256"] = _sha(_canonical_bytes(value))
    return value


def _verify_receipt(value: Mapping[str, Any], where: str) -> None:
    receipt = value.get("receipt_sha256")
    if not isinstance(receipt, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise CaptureError(f"{where}: missing or malformed receipt_sha256")
    material = dict(value)
    material.pop("receipt_sha256", None)
    actual = _sha(_canonical_bytes(material))
    if receipt != actual:
        raise CaptureError(f"{where}: receipt mismatch: expected {actual}, got {receipt}")


def _read_json(path: Path, expected_schema: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != expected_schema:
        raise CaptureError(f"{path}: expected schema {expected_schema}")
    return payload, raw


def _run(argv: list[str], *, cwd: Path | None = None) -> bytes:
    env = None
    if argv and Path(argv[0]).name == "git":
        env = os.environ.copy()
        env["GIT_NO_LAZY_FETCH"] = "1"
        env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise CaptureError(f"command failed: {' '.join(argv)}: {detail or exc}") from exc
    return result.stdout


def _configured_corpus_root(corpus_root: str | Path | None = None) -> Path:
    """Resolve the ops checkout without relying on machine-local helpers."""

    configured = corpus_root
    if configured is None:
        configured = os.environ.get(CORPUS_ROOT_ENV) or DEFAULT_CORPUS_ROOT
    return Path(configured).expanduser().resolve()


def _resolve_corpus_root(corpus_root: str | Path | None = None) -> Path:
    root = _configured_corpus_root(corpus_root)
    if not root.is_dir():
        raise CaptureError(
            f"DE corpus checkout not found at {root}; pass --corpus-root or set "
            f"{CORPUS_ROOT_ENV}"
        )
    actual_root = Path(
        _run(["git", "-C", str(root), "rev-parse", "--show-toplevel"])
        .decode()
        .strip()
    ).resolve()
    if actual_root != root:
        raise CaptureError(f"--corpus-root must be the git top-level: {actual_root}")
    return root


def _git_blob(root: Path, commit: str, path: str) -> bytes:
    if path.startswith("/") or "\\" in path or any(
        part in {"", ".", ".."} for part in path.split("/")
    ):
        raise CaptureError(f"unsafe corpus path: {path!r}")
    return _run(["git", "-C", str(root), "show", f"{commit}:{path}"])


@dataclass(frozen=True)
class CorpusRow:
    value: dict[str, Any]
    line_number: int
    raw_sha256: str
    body_sha256: str | None

    @property
    def path(self) -> str:
        return str(self.value["citation_path"])


@dataclass
class Corpus:
    rows: list[CorpusRow]
    by_path: dict[str, CorpusRow]
    documents: dict[str, CorpusRow]
    document_for_path: dict[str, str]
    scans: list[dict[str, Any]]
    release_object: dict[str, Any]


def _release_object(root: Path, corpus: Mapping[str, Any]) -> dict[str, Any]:
    release = str(corpus["release"])
    content_sha = str(corpus["release_content_sha256"])
    path = root / "releases" / release / f"{content_sha}.json"
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read cached release object {path}: {exc}") from exc
    content = payload.get("content")
    if not isinstance(content, dict):
        raise CaptureError("release object has no content mapping")
    calculated = _sha(_canonical_bytes(content))
    if calculated != content_sha or payload.get("content_sha256") != content_sha:
        raise CaptureError("release object content hash does not match source.json")
    if payload.get("release") != release or content.get("release") != release:
        raise CaptureError("release object name does not match source.json")
    if content.get("git", {}).get("commit") != corpus.get("commit"):
        raise CaptureError("release object commit does not match source.json")
    if content.get("selector_sha256") != corpus.get("release_selector_sha256"):
        raise CaptureError("release object selector hash does not match source.json")
    return {
        "path": path.relative_to(root).as_posix(),
        "raw_sha256": _sha(raw),
        "content_sha256": content_sha,
        "artifacts": content.get("artifacts", []),
    }


def _load_corpus(root: Path, source: Mapping[str, Any]) -> Corpus:
    corpus = source.get("corpus")
    if not isinstance(corpus, dict):
        raise CaptureError("source.json corpus block is missing")
    commit = str(corpus.get("commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise CaptureError("source.json corpus commit is malformed")
    _run(["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"])
    release = _release_object(root, corpus)
    release_artifacts = {
        row.get("path"): row for row in release.pop("artifacts") if isinstance(row, dict)
    }

    inventories = corpus.get("inventories")
    provisions = corpus.get("provision_sources")
    if not isinstance(inventories, list) or not isinstance(provisions, list):
        raise CaptureError("source.json must pin inventory and provision files")
    inventory_by_class: dict[str, dict[str, Any]] = {}
    for pin in inventories:
        path = str(pin.get("path", ""))
        document_class = path.split("/")[4] if len(path.split("/")) > 4 else ""
        raw = _git_blob(root, commit, path)
        if _sha(raw) != pin.get("sha256"):
            raise CaptureError(f"inventory hash mismatch at pinned commit: {path}")
        try:
            items = json.loads(raw).get("items")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise CaptureError(f"invalid inventory JSON: {path}") from exc
        if not isinstance(items, list) or len(items) != pin.get("row_count"):
            raise CaptureError(f"inventory row count mismatch: {path}")
        artifact = release_artifacts.get(path)
        if not artifact or artifact.get("sha256") != pin.get("sha256"):
            raise CaptureError(f"inventory is not bound by the release object: {path}")
        inventory_by_class[document_class] = {
            "path": path,
            "sha256": pin["sha256"],
            "row_count": len(items),
        }

    rows: list[CorpusRow] = []
    by_path: dict[str, CorpusRow] = {}
    scans: list[dict[str, Any]] = []
    for pin in provisions:
        path = str(pin.get("path", ""))
        parts = path.split("/")
        document_class = parts[4] if len(parts) > 4 else ""
        raw = _git_blob(root, commit, path)
        if _sha(raw) != pin.get("sha256"):
            raise CaptureError(f"provision hash mismatch at pinned commit: {path}")
        lines = [line for line in raw.splitlines() if line.strip()]
        if len(lines) != pin.get("row_count"):
            raise CaptureError(f"provision row count mismatch: {path}")
        artifact = release_artifacts.get(path)
        if (
            not artifact
            or artifact.get("sha256") != pin.get("sha256")
            or artifact.get("rows") != len(lines)
        ):
            raise CaptureError(f"provision file is not bound by the release object: {path}")
        for number, line in enumerate(lines, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CaptureError(f"invalid JSONL at {path}:{number}") from exc
            citation_path = value.get("citation_path")
            if not isinstance(citation_path, str) or citation_path in by_path:
                raise CaptureError(f"missing or duplicate citation_path at {path}:{number}")
            if value.get("document_class") != document_class:
                raise CaptureError(f"document_class mismatch at {path}:{number}")
            body = value.get("body")
            row = CorpusRow(
                value=value,
                line_number=number,
                raw_sha256=_sha(line),
                body_sha256=_sha(body.encode("utf-8")) if isinstance(body, str) else None,
            )
            rows.append(row)
            by_path[citation_path] = row
        scans.append(
            {
                "document_class": document_class,
                "inventory": inventory_by_class[document_class],
                "provisions": {
                    "path": path,
                    "sha256": pin["sha256"],
                    "row_count": len(lines),
                },
            }
        )

    expected_total = sum(int(pin["row_count"]) for pin in provisions)
    if len(rows) != expected_total:
        raise CaptureError("not every pinned corpus row was scanned")
    documents = {
        row.path: row
        for row in rows
        if row.value.get("level") == 0
        or (
            row.value.get("metadata", {}).get("kind") == "document"
            and not row.value.get("parent_citation_path")
        )
    }
    document_for_path: dict[str, str] = {}
    for row in rows:
        source_document = row.value.get("source_document_id")
        if isinstance(source_document, str) and source_document in documents:
            document_for_path[row.path] = source_document
            continue
        cursor = row.path
        while cursor not in documents and "/" in cursor:
            cursor = cursor.rsplit("/", 1)[0]
        if cursor in documents:
            document_for_path[row.path] = cursor
    return Corpus(rows, by_path, documents, document_for_path, scans, release)


def _document_aliases(document: CorpusRow) -> list[str]:
    metadata = document.value.get("metadata", {})
    law = metadata.get("law_metadata", {}) if isinstance(metadata, dict) else {}
    aliases: set[str] = set()
    for value in (
        document.value.get("citation_label"),
        metadata.get("jurabk"),
        metadata.get("law_title"),
        law.get("jurabk") if isinstance(law, dict) else None,
        law.get("amtabk") if isinstance(law, dict) else None,
        law.get("langtitel") if isinstance(law, dict) else None,
    ):
        if isinstance(value, str) and len(value.strip()) >= 3:
            aliases.add(value.strip())
    match = re.fullmatch(r"de/statute/sgb-(\d+)", document.path)
    if match:
        number = int(match.group(1))
        roman = {1:"I",2:"II",3:"III",4:"IV",5:"V",6:"VI",7:"VII",8:"VIII",9:"IX",10:"X",11:"XI",12:"XII"}[number]
        ordinal = {1:"Ersten",2:"Zweiten",3:"Dritten",4:"Vierten",5:"Fünften",6:"Sechsten",7:"Siebten",8:"Achten",9:"Neunten",10:"Zehnten",11:"Elften",12:"Zwölften"}[number]
        title_ordinal = {1:"Erstes",2:"Zweites",3:"Drittes",4:"Viertes",5:"Fünftes",6:"Sechstes",7:"Siebtes",8:"Achtes",9:"Neuntes",10:"Zehntes",11:"Elftes",12:"Zwölftes"}[number]
        grounding = " ".join(aliases)
        if re.search(
            rf"\b(?:{re.escape(title_ordinal)}|{re.escape(ordinal)})\b"
            rf"[^\n]{{0,40}}\bBuch",
            grounding,
        ):
            aliases.update(
                {
                    f"{ordinal} Buch",
                    f"{ordinal} Buches",
                    f"{ordinal} Buch Sozialgesetzbuch",
                    f"{ordinal} Buches Sozialgesetzbuch",
                }
            )
        if re.search(rf"(?:\({roman}\)|\bSGB\s*{roman}\b)", grounding):
            aliases.add(f"SGB {roman}")
        if re.search(rf"\bSGB\s*{number}\b", grounding):
            aliases.add(f"SGB {number}")
    return sorted(aliases, key=lambda text: (-len(text), text.casefold()))


def _alias_pattern(alias: str) -> str:
    """Match a legal-title alias as a token, never inside ``festgesetzt`` etc."""

    return rf"(?<![\w]){re.escape(alias)}(?![\w])"


_RAW_REFERENCE_RULES: tuple[tuple[str, str], ...] = (
    ("abgabenordnung", r"\bAbgabenordnung\b"),
    ("ewr-abkommen", r"\b(?:Abkommen über den Europäischen Wirtschaftsraum|EWR-Abkommen)\b"),
    ("freizuegigkeitsgesetz-eu", r"\bFreizügigkeitsgesetz(?:es)?/EU\b"),
    ("aufenthaltsgesetz", r"\bAufenthaltsgesetz(?:es)?\b"),
    ("bgb", r"\b(?:Bürgerlichen Gesetzbuchs|Bürgerliches Gesetzbuch)\b"),
    ("owig", r"\b(?:Gesetzes über Ordnungswidrigkeiten|Ordnungswidrigkeitengesetz(?:es)?|OWiG)\b"),
    ("auslaendergesetz", r"\bAusländergesetz(?:es)?\b"),
    ("zpo", r"\b(?:Zivilprozessordnung|ZPO)\b"),
    ("steuerberatungsgesetz", r"\bSteuerberatungsgesetz(?:es)?\b"),
    ("altersteilzeitgesetz", r"\bAltersteilzeitgesetz(?:es)?\b"),
    ("sgb-1", r"\b(?:SGB\s+I|Ersten Buch(?:es)? Sozialgesetzbuch)\b"),
    ("sgb-4", r"\b(?:SGB\s+IV|Vierten Buch(?:es)?(?: Sozialgesetzbuch)?)\b"),
    ("sgb-7", r"\b(?:SGB\s+VII|Siebten Buch(?:es)? Sozialgesetzbuch)\b"),
    ("sgb-8", r"\b(?:SGB\s+VIII|Achten Buch(?:es)? Sozialgesetzbuch)\b"),
    ("sgb-9", r"\b(?:SGB\s+IX|Neunten Buch(?:es)?(?: Sozialgesetzbuch)?)\b"),
    ("sgb-10", r"\b(?:SGB\s+X|Zehnten Buch(?:es)? Sozialgesetzbuch)\b"),
)
_EU_REGULATION = re.compile(r"\bVerordnung \((?:EG|EU)\) (?:Nr\.\s*)?\d{3,4}/\d+\b")
_HISTORICAL_ACT = re.compile(
    r"\bGesetzes vom \d{1,2}\. [A-ZÄÖÜa-zäöüß]+ \d{4} "
    r"\(BGBl\.?(?: \d{4})? I S\. ?\d+\)"
)
_SECTION = re.compile(r"§{1,2}\s*([0-9]+[a-z]?)", re.IGNORECASE)
_ANLAGE = re.compile(r"\bAnlage\s+([0-9]+[a-z]?)\b", re.IGNORECASE)
_NAMED_INSTRUMENT = re.compile(
    r"(?<![\w])"
    r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9/-]*?"
    r"(?:gesetz(?:es)?|verordnung(?:en|s)?)"
    r"(?![\w])"
)
_NONSPECIFIC_INSTRUMENT_TERMS = {
    "bundesgesetz",
    "bundesgesetzes",
    "einführungsgesetz",
    "einführungsgesetzes",
    "ersatzverordnung",
    "ersatzverordnungen",
    "landesgesetz",
    "landesgesetzes",
    "rechtsverordnung",
    "rechtsverordnungen",
    "steuergesetz",
    "steuergesetzes",
    "änderungsgesetz",
    "änderungsgesetzes",
}

_GLOBAL_INDEX_SCHEMA = "axiom_oracles.closure.de_corpus_extraction_index.v1"
_GLOBAL_MECHANISMS = (
    "amendment_targets",
    "explicit_cross_reference_body",
    "law_metadata_changed_by",
    "law_metadata_fundstelle",
)


def _normalized_instrument_name(value: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", value.casefold())


def _generic_reference_matches_aliases(
    matched_text: str, target_aliases: Iterable[str]
) -> bool:
    matched = _normalized_instrument_name(matched_text)
    for alias in target_aliases:
        for token_match in _NAMED_INSTRUMENT.finditer(alias):
            normalized = _normalized_instrument_name(token_match.group(0))
            if matched in {normalized, f"{normalized}s", f"{normalized}es"}:
                return True
    return False


def _generic_reference_target(
    matched_text: str,
    aliases: Mapping[str, list[str]],
    source_document: str | None,
) -> str | None:
    candidates: set[str] = set()
    for target_document, target_aliases in aliases.items():
        if target_document == source_document:
            continue
        if _generic_reference_matches_aliases(matched_text, target_aliases):
            candidates.add(target_document)
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _span_overlaps(span: tuple[int, int], occupied: Iterable[tuple[int, int]]) -> bool:
    return any(start < span[1] and span[0] < end for start, end in occupied)


def _global_row_findings(
    row: CorpusRow,
    corpus: Corpus,
    aliases: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    """Extract corpus-only discovery facts from one row without disposition."""

    findings: dict[bytes, dict[str, Any]] = {}

    def add(fact: dict[str, Any]) -> None:
        findings.setdefault(_canonical_bytes(fact), fact)

    metadata = row.value.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    law = metadata.get("law_metadata", {})
    if not isinstance(law, Mapping):
        law = {}
    for key, mechanism in (
        ("fundstelle", "law_metadata_fundstelle"),
        ("stand", "law_metadata_changed_by"),
    ):
        raw_reference = law.get(key)
        if isinstance(raw_reference, str) and raw_reference.strip():
            add(
                {
                    "mechanism": mechanism,
                    "source_citation_path": row.path,
                    "source_row_sha256": row.raw_sha256,
                    "raw_reference": raw_reference,
                }
            )

    targets = row.value.get("amendment_targets")
    if not isinstance(targets, list):
        targets = metadata.get("amendment_targets")
    if isinstance(targets, list):
        for target in sorted({item for item in targets if isinstance(item, str)}):
            add(
                {
                    "mechanism": "amendment_targets",
                    "source_citation_path": row.path,
                    "source_row_sha256": row.raw_sha256,
                    "target_citation_path": target,
                }
            )

    body = row.value.get("body")
    source_document = corpus.document_for_path.get(row.path)
    if not isinstance(body, str):
        return [findings[key] for key in sorted(findings)]

    named_spans: list[tuple[int, int]] = []
    for target_document, target_aliases in aliases.items():
        for alias in target_aliases:
            for match in re.finditer(_alias_pattern(alias), body, flags=re.IGNORECASE):
                named_spans.append(match.span())
                if target_document == source_document:
                    continue
                add(
                    {
                        "mechanism": "explicit_cross_reference_body",
                        "source_citation_path": row.path,
                        "source_body_sha256": row.body_sha256,
                        "source_row_sha256": row.raw_sha256,
                        "matched_text": match.group(0),
                        "target_citation_path": target_document,
                        "target_row_sha256": corpus.documents[
                            target_document
                        ].raw_sha256,
                    }
                )

    corpus_hints = {
        "sgb-1": "de/statute/sgb-1",
        "sgb-4": "de/statute/sgb-4",
        "sgb-7": "de/statute/sgb-7",
        "sgb-8": "de/statute/sgb-8",
        "sgb-9": "de/statute/sgb-9",
        "sgb-10": "de/statute/sgb-10",
    }
    for key, pattern in _RAW_REFERENCE_RULES:
        for match in re.finditer(pattern, body, flags=re.IGNORECASE):
            if any(start <= match.start() and match.end() <= end for start, end in named_spans):
                continue
            named_spans.append(match.span())
            target = corpus_hints.get(key)
            fact = {
                "mechanism": "explicit_cross_reference_body",
                "source_citation_path": row.path,
                "source_body_sha256": row.body_sha256,
                "source_row_sha256": row.raw_sha256,
                "matched_text": match.group(0),
            }
            if target in corpus.documents:
                fact["target_citation_path"] = target
                fact["target_row_sha256"] = corpus.documents[target].raw_sha256
            else:
                fact["unresolved_identity"] = f"law:{key}"
            add(fact)

    for regex, prefix in (
        (_EU_REGULATION, "eu-regulation"),
        (_HISTORICAL_ACT, "bgbl-act"),
    ):
        for match in regex.finditer(body):
            if _span_overlaps(match.span(), named_spans):
                continue
            named_spans.append(match.span())
            normalized = re.sub(r"\s+", " ", match.group(0)).casefold()
            add(
                {
                    "mechanism": "explicit_cross_reference_body",
                    "source_citation_path": row.path,
                    "source_body_sha256": row.body_sha256,
                    "source_row_sha256": row.raw_sha256,
                    "matched_text": match.group(0),
                    "unresolved_identity": f"{prefix}:{normalized}",
                }
            )
    for match in _NAMED_INSTRUMENT.finditer(body):
        if _span_overlaps(match.span(), named_spans):
            continue
        if source_document is not None and _generic_reference_matches_aliases(
            match.group(0), aliases[source_document]
        ):
            named_spans.append(match.span())
            continue
        if _normalized_instrument_name(match.group(0)) in _NONSPECIFIC_INSTRUMENT_TERMS:
            named_spans.append(match.span())
            continue
        target = _generic_reference_target(match.group(0), aliases, source_document)
        fact = {
            "mechanism": "explicit_cross_reference_body",
            "source_citation_path": row.path,
            "source_body_sha256": row.body_sha256,
            "source_row_sha256": row.raw_sha256,
            "matched_text": match.group(0),
        }
        if target is not None:
            fact["target_citation_path"] = target
            fact["target_row_sha256"] = corpus.documents[target].raw_sha256
        else:
            normalized = re.sub(r"\s+", " ", match.group(0)).casefold()
            fact["unresolved_identity"] = f"named-instrument:{normalized}"
        add(fact)
        named_spans.append(match.span())
    return [findings[key] for key in sorted(findings)]


def _global_corpus_extraction_index(corpus: Corpus) -> dict[str, Any]:
    """Return a compact, rederivable receipt proving all corpus rows were scanned."""

    aliases = {
        path: _document_aliases(document)
        for path, document in sorted(corpus.documents.items())
    }
    mechanism_counts = {key: 0 for key in _GLOBAL_MECHANISMS}
    row_receipts: list[dict[str, Any]] = []
    all_findings: list[dict[str, Any]] = []
    act_rows = {path: [] for path in corpus.documents}
    act_findings = {path: [] for path in corpus.documents}
    unmapped_row_count = 0
    body_row_count = 0

    for row in sorted(corpus.rows, key=lambda item: item.path):
        if isinstance(row.value.get("body"), str):
            body_row_count += 1
        findings = _global_row_findings(row, corpus, aliases)
        all_findings.extend(findings)
        for fact in findings:
            mechanism_counts[fact["mechanism"]] += 1
        source_document = corpus.document_for_path.get(row.path)
        if source_document in act_rows:
            act_rows[source_document].append(row)
            act_findings[source_document].extend(findings)
        else:
            unmapped_row_count += 1
        row_receipts.append(
            {
                "citation_path": row.path,
                "row_sha256": row.raw_sha256,
                "body_sha256": row.body_sha256,
                "source_document": source_document,
                "finding_count": len(findings),
                "findings_sha256": _sha(_canonical_bytes({"findings": findings})),
            }
        )

    acts: list[dict[str, Any]] = []
    for document_path in sorted(corpus.documents):
        findings = sorted(
            act_findings[document_path], key=lambda row: _canonical_bytes(row)
        )
        counts = {key: 0 for key in _GLOBAL_MECHANISMS}
        for fact in findings:
            counts[fact["mechanism"]] += 1
        acts.append(
            {
                "document_citation_path": document_path,
                "document_row_sha256": corpus.documents[document_path].raw_sha256,
                "row_count": len(act_rows[document_path]),
                "mechanism_counts": counts,
                "findings_sha256": _sha(_canonical_bytes({"findings": findings})),
                "findings": findings,
            }
        )

    all_findings.sort(key=lambda row: _canonical_bytes(row))
    index: dict[str, Any] = {
        "schema": _GLOBAL_INDEX_SCHEMA,
        "row_count": len(row_receipts),
        "body_row_count": body_row_count,
        "mapped_row_count": len(row_receipts) - unmapped_row_count,
        "unmapped_row_count": unmapped_row_count,
        "act_count": len(acts),
        "mechanism_counts": mechanism_counts,
        "row_scan_sha256": _sha(_canonical_bytes({"rows": row_receipts})),
        "canonical_index_sha256": _sha(
            _canonical_bytes({"findings": all_findings})
        ),
        "per_act_sha256": _sha(_canonical_bytes({"acts": acts})),
        "acts": acts,
        "method": {
            "row_participation": "one canonical row receipt for every pinned statute and regulation row, including rows with zero findings",
            "law_metadata": "Fundstelle and stand values read from law_metadata on every row; values remain verbatim corpus facts",
            "body_references": "every string body scanned; counts are canonical unique source-row/matched-text/target facts from corpus-grounded cross-act aliases, versioned known-reference patterns, and an unmatched specific compound-law/regulation fallback retained verbatim; the committed nonspecific-term stoplist does not assert generic classes as instruments",
            "amendment_targets": "every amendment_targets key on every row scanned; counts are canonical unique source-row/target facts retained verbatim",
            "projection": "program frontiers remain the separately recorded relevant-root projection; the global index does not disposition or inject unrelated acts",
        },
    }
    return _add_receipt(index)


def _strict_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_global_extraction_index(
    index: Mapping[str, Any], *, scanned_row_count: Any
) -> None:
    expected_keys = {
        "schema",
        "row_count",
        "body_row_count",
        "mapped_row_count",
        "unmapped_row_count",
        "act_count",
        "mechanism_counts",
        "row_scan_sha256",
        "canonical_index_sha256",
        "per_act_sha256",
        "acts",
        "method",
        "receipt_sha256",
    }
    if set(index) != expected_keys or index.get("schema") != _GLOBAL_INDEX_SCHEMA:
        raise CaptureError("global corpus extraction index shape is invalid")
    _verify_receipt(index, "global corpus extraction index")
    counts = (
        index.get("row_count"),
        index.get("body_row_count"),
        index.get("mapped_row_count"),
        index.get("unmapped_row_count"),
        index.get("act_count"),
    )
    if not all(_strict_nonnegative_int(value) for value in counts):
        raise CaptureError("global corpus extraction counts must be nonnegative integers")
    if (
        index["row_count"] != scanned_row_count
        or index["body_row_count"] > index["row_count"]
        or index["mapped_row_count"] + index["unmapped_row_count"]
        != index["row_count"]
    ):
        raise CaptureError("global corpus extraction row counts do not agree")
    mechanism_counts = index.get("mechanism_counts")
    if (
        not isinstance(mechanism_counts, Mapping)
        or set(mechanism_counts) != set(_GLOBAL_MECHANISMS)
        or not all(_strict_nonnegative_int(value) for value in mechanism_counts.values())
    ):
        raise CaptureError("global corpus extraction mechanism counts are invalid")
    for key in ("row_scan_sha256", "canonical_index_sha256", "per_act_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(index.get(key, ""))):
            raise CaptureError(f"global corpus extraction {key} is malformed")
    acts = index.get("acts")
    if not isinstance(acts, list) or any(not isinstance(row, Mapping) for row in acts):
        raise CaptureError("global corpus extraction acts must be a list of mappings")
    act_paths = [row.get("document_citation_path") for row in acts]
    if (
        len(acts) != index["act_count"]
        or any(not isinstance(value, str) for value in act_paths)
        or act_paths != sorted(set(act_paths))
        or sum(
            row.get("row_count", -1)
            for row in acts
            if _strict_nonnegative_int(row.get("row_count"))
        )
        != index["mapped_row_count"]
    ):
        raise CaptureError("global corpus extraction act rows or counts are invalid")
    summed = {key: 0 for key in _GLOBAL_MECHANISMS}
    stored_findings: list[dict[str, Any]] = []
    for row in acts:
        if set(row) != {
            "document_citation_path",
            "document_row_sha256",
            "row_count",
            "mechanism_counts",
            "findings_sha256",
            "findings",
        }:
            raise CaptureError("global corpus extraction act shape is invalid")
        if not _strict_nonnegative_int(row.get("row_count")):
            raise CaptureError("global corpus extraction act row_count is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("document_row_sha256", ""))):
            raise CaptureError("global corpus extraction document hash is malformed")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("findings_sha256", ""))):
            raise CaptureError("global corpus extraction act findings hash is malformed")
        act_counts = row.get("mechanism_counts")
        if (
            not isinstance(act_counts, Mapping)
            or set(act_counts) != set(_GLOBAL_MECHANISMS)
            or not all(_strict_nonnegative_int(value) for value in act_counts.values())
        ):
            raise CaptureError("global corpus extraction act mechanism counts are invalid")
        findings = row.get("findings")
        if (
            not isinstance(findings, list)
            or any(not isinstance(fact, Mapping) for fact in findings)
            or findings != sorted(findings, key=lambda fact: _canonical_bytes(fact))
            or len({_canonical_bytes(fact) for fact in findings}) != len(findings)
        ):
            raise CaptureError("global corpus extraction act findings are noncanonical")
        if row["findings_sha256"] != _sha(
            _canonical_bytes({"findings": findings})
        ):
            raise CaptureError("global corpus extraction act findings digest does not agree")
        derived_act_counts = {key: 0 for key in _GLOBAL_MECHANISMS}
        for fact in findings:
            mechanism = fact.get("mechanism")
            if mechanism not in derived_act_counts:
                raise CaptureError("global corpus extraction finding mechanism is invalid")
            if (
                not isinstance(fact.get("source_citation_path"), str)
                or not re.fullmatch(
                    r"[0-9a-f]{64}", str(fact.get("source_row_sha256", ""))
                )
            ):
                raise CaptureError("global corpus extraction finding source is invalid")
            if mechanism == "explicit_cross_reference_body":
                resolved = isinstance(fact.get("target_citation_path"), str) and bool(
                    re.fullmatch(
                        r"[0-9a-f]{64}", str(fact.get("target_row_sha256", ""))
                    )
                )
                unresolved = isinstance(fact.get("unresolved_identity"), str)
                if (
                    not isinstance(fact.get("matched_text"), str)
                    or not re.fullmatch(
                        r"[0-9a-f]{64}", str(fact.get("source_body_sha256", ""))
                    )
                    or resolved == unresolved
                ):
                    raise CaptureError("global corpus body-reference finding is invalid")
            derived_act_counts[mechanism] += 1
            stored_findings.append(dict(fact))
        if derived_act_counts != act_counts:
            raise CaptureError("global corpus extraction act findings/counts disagree")
        for key in _GLOBAL_MECHANISMS:
            summed[key] += act_counts[key]
    if summed != mechanism_counts:
        raise CaptureError("global corpus extraction mechanism counts do not agree by act")
    stored_findings.sort(key=lambda fact: _canonical_bytes(fact))
    if index["canonical_index_sha256"] != _sha(
        _canonical_bytes({"findings": stored_findings})
    ):
        raise CaptureError("global corpus extraction canonical digest does not agree")
    if index["per_act_sha256"] != _sha(_canonical_bytes({"acts": acts})):
        raise CaptureError("global corpus extraction per-act digest does not agree")
    method = index.get("method")
    if not isinstance(method, Mapping) or set(method) != {
        "row_participation",
        "law_metadata",
        "body_references",
        "amendment_targets",
        "projection",
    }:
        raise CaptureError("global corpus extraction method is invalid")


def _scope_paths(program: str, corpus: Corpus) -> set[str]:
    if program == "de/kindergeld":
        out = set()
        for row in corpus.rows:
            if corpus.document_for_path.get(row.path) != "de/statute/estg":
                continue
            ordinal = row.value.get("ordinal")
            if isinstance(ordinal, int) and 62 <= ordinal <= 78:
                out.add(row.path)
        return out
    if program == "de/unterhaltsvorschuss":
        return {
            row.path
            for row in corpus.rows
            if row.path.startswith("de/statute/uhvorschg/")
        }
    return set(RV_ROOTS)


def _declared_paths(program_block: Mapping[str, Any]) -> set[str]:
    paths = {
        row.get("citation_path")
        for row in program_block.get("declared_sources", [])
        if isinstance(row, dict)
    }
    return {path for path in paths if isinstance(path, str)}


def _row_fact(row: CorpusRow, corpus: Corpus) -> dict[str, Any]:
    metadata = row.value.get("metadata", {})
    law = metadata.get("law_metadata", {}) if isinstance(metadata, dict) else {}
    fact: dict[str, Any] = {
        "citation_path": row.path,
        "row_sha256": row.raw_sha256,
        "document_class": row.value.get("document_class"),
        "citation_label": row.value.get("citation_label"),
        "body_sha256": row.body_sha256,
        "source_sha256": row.value.get("source_sha256") or row.value.get("sha256"),
    }
    document_path = corpus.document_for_path.get(row.path)
    if document_path:
        document = corpus.documents[document_path].value
        document_metadata = document.get("metadata", {})
        fact["document_citation_path"] = document_path
        if isinstance(document_metadata, dict):
            fact["legal_authority_url"] = document_metadata.get("legal_authority_url")
            for key in ("title", "title_short", "date_document", "document_type"):
                if document_metadata.get(key) is not None:
                    fact[key] = document_metadata[key]
    if isinstance(law, dict) and law.get("fundstelle"):
        fact["fundstelle"] = law["fundstelle"]
    return {key: value for key, value in fact.items() if value is not None}


@dataclass
class Candidate:
    identity: str
    facts: dict[str, Any]
    refs: set[str] = field(default_factory=set)
    seed_ids: set[str] = field(default_factory=set)


def _evidence_id(payload: Mapping[str, Any]) -> str:
    return "de-corpus-" + _sha(_canonical_bytes(payload))[:20]


def _corpus_candidate_id(program: str, identity: str) -> str:
    return f"{PROGRAM_PREFIX[program]}-instr-{_sha(identity.encode())[:16]}"


def _add_evidence(
    evidence: dict[str, dict[str, Any]], payload: dict[str, Any]
) -> str:
    evidence_id = _evidence_id(payload)
    record = {"id": evidence_id, **payload}
    existing = evidence.setdefault(evidence_id, record)
    if existing != record:
        raise CaptureError(f"corpus evidence id collision: {evidence_id}")
    return evidence_id


def _add_candidate(
    candidates: dict[str, Candidate], identity: str, facts: dict[str, Any], evidence_id: str
) -> Candidate:
    candidate = candidates.setdefault(identity, Candidate(identity, facts))
    for key, value in facts.items():
        if key in candidate.facts and candidate.facts[key] != value:
            if isinstance(candidate.facts[key], list) and isinstance(value, list):
                candidate.facts[key] = sorted(set(candidate.facts[key]) | set(value))
                continue
            raise CaptureError(f"conflicting candidate fact {key} for {identity}")
        candidate.facts[key] = value
    candidate.refs.add(evidence_id)
    return candidate


def _resolved_section(corpus: Corpus, document_path: str, section: str) -> str | None:
    direct = f"{document_path}/{section}"
    if direct in corpus.by_path:
        return direct
    for row in corpus.rows:
        if corpus.document_for_path.get(row.path) != document_path:
            continue
        legal_identifier = str(row.value.get("legal_identifier", "")).casefold().replace(" ", "")
        if legal_identifier in {f"§{section}", f"anlage{section}"}:
            return row.path
    return None


def _discover_corpus_program(
    program: str,
    source_program: Mapping[str, Any],
    corpus: Corpus,
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}
    scope = _scope_paths(program, corpus)
    declared = _declared_paths(source_program)
    outbound_scan_paths = scope | declared
    excluded = scope | declared
    declared_documents = {
        corpus.document_for_path.get(path, path) for path in declared if path in corpus.by_path
    }

    def add_path(path: str, payload: dict[str, Any]) -> None:
        if path in excluded or path in declared_documents or path not in corpus.by_path:
            return
        evidence_id = _add_evidence(evidence, {"program": program, **payload})
        _add_candidate(
            candidates,
            f"corpus:{path}",
            {"identity_kind": "corpus_citation", **_row_fact(corpus.by_path[path], corpus)},
            evidence_id,
        )

    def add_raw(key: str, raw_reference: str, payload: dict[str, Any]) -> None:
        evidence_id = _add_evidence(evidence, {"program": program, **payload})
        _add_candidate(
            candidates,
            f"raw:{key}",
            {"identity_kind": "unresolved_reference", "raw_references": [raw_reference]},
            evidence_id,
        )

    # Fundstelle is an identity fact for each declared act; ``stand`` is an
    # opaque changed_by analogue and therefore a pending candidate verbatim.
    for document_path in sorted(declared_documents):
        document = corpus.documents.get(document_path)
        if not document:
            raise CaptureError(f"declared source has no corpus document: {document_path}")
        metadata = document.value.get("metadata", {})
        law = metadata.get("law_metadata", {}) if isinstance(metadata, dict) else {}
        if not isinstance(law, dict):
            law = {}
        fundstelle = law.get("fundstelle")
        if isinstance(fundstelle, str):
            _add_evidence(
                evidence,
                {
                    "program": program,
                    "mechanism": "law_metadata_fundstelle",
                    "source_citation_path": document_path,
                    "source_row_sha256": document.raw_sha256,
                    "raw_reference": fundstelle,
                },
            )
        stand = law.get("stand")
        if isinstance(stand, str) and stand.strip():
            add_raw(
                f"stand:{document_path}:{stand.casefold()}",
                stand,
                {
                    "mechanism": "law_metadata_changed_by",
                    "source_citation_path": document_path,
                    "source_row_sha256": document.raw_sha256,
                    "raw_reference": stand,
                },
            )

    aliases = {path: _document_aliases(row) for path, row in corpus.documents.items()}

    # Outbound references are scanned only in the preregistered spine/exact
    # dependency bodies.  Exact same-act provisions outside the spine remain.
    for source_path in sorted(outbound_scan_paths):
        row = corpus.by_path.get(source_path)
        if not row:
            raise CaptureError(f"preregistered corpus scope row missing: {source_path}")
        body = row.value.get("body")
        if not isinstance(body, str):
            continue
        source_document = corpus.document_for_path.get(source_path)
        if not source_document:
            continue

        named_spans: list[tuple[int, int]] = []
        for target_document, target_aliases in aliases.items():
            for alias in target_aliases:
                for match in re.finditer(_alias_pattern(alias), body, flags=re.IGNORECASE):
                    named_spans.append(match.span())
                    if target_document == source_document:
                        continue
                    # The corpus body is unstructured prose.  A neighbouring
                    # number can be a paragraph, Absatz, Nummer, amount or
                    # year, so cross-act matches resolve only to the named
                    # instrument.  Exact same-act sections are handled below.
                    add_path(
                        target_document,
                        {
                            "mechanism": "explicit_cross_reference_outbound",
                            "source_citation_path": source_path,
                            "source_body_sha256": row.body_sha256,
                            "source_row_sha256": row.raw_sha256,
                            "matched_text": match.group(0),
                            "resolved_citation_path": target_document,
                        },
                    )

        for key, pattern in _RAW_REFERENCE_RULES:
            for match in re.finditer(pattern, body, flags=re.IGNORECASE):
                if any(start <= match.start() and match.end() <= end for start, end in named_spans):
                    continue
                named_spans.append(match.span())
                corpus_hint = {
                    "sgb-1": "de/statute/sgb-1",
                    "sgb-4": "de/statute/sgb-4",
                    "sgb-7": "de/statute/sgb-7",
                    "sgb-8": "de/statute/sgb-8",
                    "sgb-9": "de/statute/sgb-9",
                    "sgb-10": "de/statute/sgb-10",
                }.get(key)
                if corpus_hint and corpus_hint in corpus.documents:
                    add_path(
                        corpus_hint,
                        {
                            "mechanism": "explicit_cross_reference_outbound",
                            "source_citation_path": source_path,
                            "source_body_sha256": row.body_sha256,
                            "source_row_sha256": row.raw_sha256,
                            "matched_text": match.group(0),
                            "resolved_citation_path": corpus_hint,
                        },
                    )
                else:
                    add_raw(
                        f"law:{key}",
                        match.group(0),
                        {
                            "mechanism": "explicit_cross_reference_outbound",
                            "source_citation_path": source_path,
                            "source_body_sha256": row.body_sha256,
                            "source_row_sha256": row.raw_sha256,
                            "matched_text": match.group(0),
                        },
                    )
        for regex, prefix in ((_EU_REGULATION, "eu-regulation"), (_HISTORICAL_ACT, "bgbl-act")):
            for match in regex.finditer(body):
                named_spans.append(match.span())
                normalized = re.sub(r"\s+", " ", match.group(0)).casefold()
                add_raw(
                    f"{prefix}:{normalized}",
                    match.group(0),
                    {
                        "mechanism": "explicit_cross_reference_outbound",
                        "source_citation_path": source_path,
                        "source_body_sha256": row.body_sha256,
                        "source_row_sha256": row.raw_sha256,
                        "matched_text": match.group(0),
                    },
                )

        for match in _NAMED_INSTRUMENT.finditer(body):
            if _span_overlaps(match.span(), named_spans):
                continue
            if _generic_reference_matches_aliases(
                match.group(0), aliases[source_document]
            ):
                named_spans.append(match.span())
                continue
            if (
                _normalized_instrument_name(match.group(0))
                in _NONSPECIFIC_INSTRUMENT_TERMS
            ):
                named_spans.append(match.span())
                continue
            target_document = _generic_reference_target(
                match.group(0), aliases, source_document
            )
            if target_document is not None:
                add_path(
                    target_document,
                    {
                        "mechanism": "explicit_cross_reference_outbound",
                        "source_citation_path": source_path,
                        "source_body_sha256": row.body_sha256,
                        "source_row_sha256": row.raw_sha256,
                        "matched_text": match.group(0),
                        "resolved_citation_path": target_document,
                    },
                )
            else:
                normalized = re.sub(r"\s+", " ", match.group(0)).casefold()
                add_raw(
                    f"named-instrument:{normalized}",
                    match.group(0),
                    {
                        "mechanism": "explicit_cross_reference_outbound",
                        "source_citation_path": source_path,
                        "source_body_sha256": row.body_sha256,
                        "source_row_sha256": row.raw_sha256,
                        "matched_text": match.group(0),
                    },
                )
            named_spans.append(match.span())

        # Bare section/Anlage references resolve to the current act.  A named
        # other-law phrase in the immediate suffix suppresses false self-links.
        for match in _SECTION.finditer(body):
            suffix = body[match.end() : match.end() + 120]
            named_nearby = any(
                match.start() - 20 <= start <= match.end() + 140
                for start, _end in named_spans
            )
            if named_nearby or re.search(
                r"\b(?:(?:Ersten|Zweiten|Dritten|Vierten|Fünften|Sechsten|Siebten|Achten|Neunten|Zehnten|Elften|Zwölften) Buch(?:es)?|Buch(?:es)? Sozialgesetzbuch|[A-Za-zÄÖÜäöüß/-]*(?:gesetz(?:es)?|verordnung)|Abgabenordnung)\b",
                suffix,
                flags=re.IGNORECASE,
            ):
                continue
            target = _resolved_section(corpus, source_document, match.group(1).lower())
            if target:
                add_path(
                    target,
                    {
                        "mechanism": "explicit_cross_reference_outbound",
                        "source_citation_path": source_path,
                        "source_body_sha256": row.body_sha256,
                        "source_row_sha256": row.raw_sha256,
                        "matched_text": match.group(0),
                        "resolved_citation_path": target,
                    },
                )
        for match in _ANLAGE.finditer(body):
            suffix = body[match.end() : match.end() + 120]
            named_nearby = any(
                match.start() - 20 <= start <= match.end() + 140
                for start, _end in named_spans
            )
            if named_nearby or re.search(
                r"\b(?:(?:Ersten|Zweiten|Dritten|Vierten|Fünften|Sechsten|Siebten|Achten|Neunten|Zehnten|Elften|Zwölften) Buch(?:es)?|Buch(?:es)? Sozialgesetzbuch|[A-Za-zÄÖÜäöüß/-]*(?:gesetz(?:es)?|verordnung)|Abgabenordnung)\b",
                suffix,
                flags=re.IGNORECASE,
            ):
                continue
            target = _resolved_section(corpus, source_document, match.group(1).lower())
            if target:
                add_path(
                    target,
                    {
                        "mechanism": "explicit_cross_reference_outbound",
                        "source_citation_path": source_path,
                        "source_body_sha256": row.body_sha256,
                        "source_row_sha256": row.raw_sha256,
                        "matched_text": match.group(0),
                        "resolved_citation_path": target,
                    },
                )

    # All 3,548 rows participate in the two inbound mechanisms.  Body matching
    # is targeted to explicit act+section citations to configured roots; it is
    # not the future comprehensive citation scan tracked in corpus#611.
    exact_targets = sorted(scope | declared)
    for row in corpus.rows:
        targets = row.value.get("amendment_targets")
        metadata = row.value.get("metadata", {})
        if not isinstance(targets, list) and isinstance(metadata, dict):
            targets = metadata.get("amendment_targets")
        if isinstance(targets, list):
            matched_targets = sorted(
                target
                for target in targets
                if isinstance(target, str)
                and any(target == root or target.startswith(root + "/") for root in exact_targets)
            )
            if matched_targets:
                candidate_path = corpus.document_for_path.get(row.path, row.path)
                add_path(
                    candidate_path,
                    {
                        "mechanism": "amendment_targets_inbound",
                        "source_citation_path": row.path,
                        "source_row_sha256": row.raw_sha256,
                        "matched_targets": matched_targets,
                    },
                )

        body = row.value.get("body")
        if not isinstance(body, str) or row.path in scope:
            continue
        for target in exact_targets:
            target_row = corpus.by_path.get(target)
            target_document = corpus.document_for_path.get(target)
            if not target_row or not target_document or target == target_document:
                continue
            section = target.rsplit("/", 1)[-1]
            for alias in aliases[target_document]:
                alias_re = _alias_pattern(alias)
                before = re.compile(
                    rf"§{{1,2}}\s*{re.escape(section)}\b[^§\n]{{0,140}}{alias_re}",
                    flags=re.IGNORECASE,
                )
                after = re.compile(
                    rf"{alias_re}[^§\n]{{0,140}}§{{1,2}}\s*{re.escape(section)}\b",
                    flags=re.IGNORECASE,
                )
                reference_match = before.search(body) or after.search(body)
                if reference_match is not None:
                    source_candidate = corpus.document_for_path.get(row.path, row.path)
                    if source_candidate not in excluded:
                        add_path(
                            source_candidate,
                            {
                                "mechanism": "explicit_cross_reference_inbound",
                                "source_citation_path": row.path,
                                "source_body_sha256": row.body_sha256,
                                "source_row_sha256": row.raw_sha256,
                                "matched_text": reference_match.group(0),
                                "resolved_citation_path": target,
                            },
                        )
                    break
                else:
                    continue
                break
    return candidates


def _fetch_attempt(query: Mapping[str, Any], timeout: float, captured_at: str) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "id": str(query["id"]),
        "programs": sorted(query["programs"]),
        "source_id": query["source_id"],
        "query": query["query"],
        "url": query["url"],
        "captured_at": captured_at,
    }
    request = urllib.request.Request(
        str(query["url"]),
        headers={
            "Accept": "application/pdf,text/html,application/xhtml+xml,application/json,*/*;q=0.1",
            "User-Agent": "axiom-oracles-de-discovery/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_FETCH_BYTES + 1)
            if len(data) > MAX_FETCH_BYTES:
                raise CaptureError(f"response exceeded {MAX_FETCH_BYTES}-byte capture limit")
            attempt.update(
                {
                    "state": "retrieved",
                    "final_url": response.geturl(),
                    "http_status": response.getcode(),
                    "content_type": response.headers.get("Content-Type"),
                    "byte_count": len(data),
                    "content_sha256": _sha(data),
                }
            )
    except Exception as exc:  # every network failure is captured, never invented
        if isinstance(exc, urllib.error.HTTPError):
            reason = f"HTTPError: {exc.code} {exc.reason}"
        elif isinstance(exc, urllib.error.URLError):
            reason = f"URLError: {exc.reason}"
        else:
            reason = f"{type(exc).__name__}: {exc}"
        attempt.update({"state": "unretrieved", "reason": reason})
    return _add_receipt({key: value for key, value in attempt.items() if value is not None})


def _offline_attempt(query: Mapping[str, Any], captured_at: str) -> dict[str, Any]:
    return _add_receipt(
        {
            "id": str(query["id"]),
            "programs": sorted(query["programs"]),
            "source_id": query["source_id"],
            "query": query["query"],
            "url": query["url"],
            "captured_at": captured_at,
            "state": "unretrieved",
            "reason": "offline capture requested; network was not attempted",
        }
    )


def _subject_channel(
    query_set: Mapping[str, Any], attempt_network: bool, timeout: float, captured_at: str
) -> dict[str, Any]:
    queries = query_set.get("queries")
    sources = query_set.get("sources")
    if not isinstance(queries, list) or not isinstance(sources, list):
        raise CaptureError("query set must contain sources and queries lists")
    source_ids = {row.get("id") for row in sources if isinstance(row, dict)}
    seen: set[str] = set()
    for query in queries:
        if not isinstance(query, dict) or not isinstance(query.get("id"), str):
            raise CaptureError("query set contains a malformed query")
        if query["id"] in seen or query.get("source_id") not in source_ids:
            raise CaptureError(f"duplicate query or unknown source: {query.get('id')}")
        if not isinstance(query.get("programs"), list) or not set(query["programs"]) <= set(PROGRAMS):
            raise CaptureError(f"invalid query programs: {query['id']}")
        if not isinstance(query.get("url"), str) or not query["url"].startswith(("http://", "https://")):
            raise CaptureError(f"invalid query URL: {query['id']}")
        seen.add(query["id"])
    if attempt_network:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_fetch_attempt, query, timeout, captured_at) for query in queries]
            attempts = [future.result() for future in futures]
    else:
        attempts = [_offline_attempt(query, captured_at) for query in queries]
    attempts.sort(key=lambda row: row["id"])
    states = {row["state"] for row in attempts}
    state = "retrieved" if states == {"retrieved"} else "unretrieved" if states == {"unretrieved"} else "partial"
    return _add_receipt(
        {
            "state": state,
            "version": query_set.get("version"),
            "date": query_set.get("date"),
            "target_period": query_set.get("target_period"),
            "attempts": attempts,
        }
    )


def _merge_subject_candidates(
    program: str,
    candidates: dict[str, Candidate],
    attempts: Iterable[Mapping[str, Any]],
    queries: Mapping[str, Mapping[str, Any]],
    corpus: Corpus,
    source_program: Mapping[str, Any],
) -> None:
    url_documents: dict[str, str] = {}
    for path, row in corpus.documents.items():
        metadata = row.value.get("metadata", {})
        for key in ("legal_authority_url", "xml_source_url"):
            value = metadata.get(key) if isinstance(metadata, dict) else None
            if isinstance(value, str):
                url_documents[value.rstrip("/")] = path
        source_url = row.value.get("source_url")
        if isinstance(source_url, str):
            url_documents[source_url.rstrip("/")] = path
    declared = _declared_paths(source_program)
    declared_documents = {
        corpus.document_for_path.get(path, path) for path in declared
    }
    for attempt in attempts:
        if program not in attempt.get("programs", []):
            continue
        query = queries[str(attempt["id"])]
        seed = query.get("candidate_seed")
        if isinstance(seed, str) and not seed.startswith(PROGRAM_PREFIX[program] + "-"):
            seed = None
        path = url_documents.get(str(query["url"]).rstrip("/"))
        if path in declared or path in declared_documents:
            continue
        if path:
            identity = f"corpus:{path}"
            facts = {"identity_kind": "corpus_citation", **_row_fact(corpus.by_path[path], corpus)}
        elif isinstance(seed, str):
            identity = f"subject-seed:{seed}"
            facts = {
                "identity_kind": "subject_seed",
                "raw_reference": query["query"],
                "subject_urls": [query["url"]],
            }
        else:
            continue
        candidate = candidates.setdefault(identity, Candidate(identity, facts))
        candidate.refs.add(str(attempt["id"]))
        if isinstance(seed, str):
            candidate.seed_ids.add(seed)
        if identity.startswith("subject-seed:"):
            urls = set(candidate.facts.get("subject_urls", []))
            urls.add(query["url"])
            candidate.facts["subject_urls"] = sorted(urls)


def _render_candidates(program: str, candidates: Mapping[str, Candidate]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    ids: set[str] = set()
    for identity, candidate in sorted(candidates.items()):
        if len(candidate.seed_ids) > 1:
            raise CaptureError(f"multiple seed ids resolve to one candidate: {identity}")
        candidate_id = next(iter(candidate.seed_ids), _corpus_candidate_id(program, identity))
        if candidate_id in ids:
            raise CaptureError(f"duplicate candidate id in {program}: {candidate_id}")
        ids.add(candidate_id)
        rendered.append(
            {
                "id": candidate_id,
                "status": "pending",
                "discovery_refs": sorted(candidate.refs),
                **candidate.facts,
            }
        )
    rendered.sort(key=lambda row: row["id"])
    return rendered


def build_snapshot(
    query_set_path: str | Path,
    source_path: str | Path,
    corpus_root: str | Path | None,
    attempt_network: bool = True,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Build one DE discovery snapshot from pinned corpus blobs and URL attempts."""
    query_path = Path(query_set_path).resolve()
    source_file = Path(source_path).resolve()
    source, source_raw = _read_json(source_file, SOURCE_SCHEMA)
    query_set, query_raw = _read_json(query_path, QUERY_SCHEMA)
    if set(source.get("programs", {})) != set(PROGRAMS):
        raise CaptureError("source.json program set is not the preregistered DE candidate set")
    root = _resolve_corpus_root(corpus_root)
    corpus = _load_corpus(root, source)
    captured_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    global_extraction_index = _global_corpus_extraction_index(corpus)
    evidence: dict[str, dict[str, Any]] = {}
    program_candidates = {
        program: _discover_corpus_program(program, source["programs"][program], corpus, evidence)
        for program in PROGRAMS
    }
    corpus_channel = _add_receipt(
        {
            "state": "retrieved",
            "repository": source["corpus"].get("repository"),
            "release": source["corpus"]["release"],
            "commit": source["corpus"]["commit"],
            "release_content_sha256": source["corpus"]["release_content_sha256"],
            "release_object": corpus.release_object,
            "scans": sorted(corpus.scans, key=lambda row: row["document_class"]),
            "scanned_row_count": len(corpus.rows),
            "global_extraction_index": global_extraction_index,
            "extraction_protocol": {
                "global_index": "every pinned row contributes to a per-act receipt covering law_metadata, body cross-references, and amendment_targets",
                "law_metadata": "global index scans every row; program evidence projects Fundstelle identity and stand changed_by analogues from declared-source documents",
                "outbound_cross_references": "global index scans every body; program evidence projects provision bodies in each preregistered spine plus every exact declared source",
                "inbound_cross_references": "all pinned rows, targeted to exact spine and declared-source citations",
                "amendment_targets": "global index and program projection both scan all pinned rows",
                "program_projection": "candidate frontiers are the relevant-root projection and do not import unrelated global-index acts",
            },
            "evidence": sorted(evidence.values(), key=lambda row: row["id"]),
        }
    )
    subject_channel = _subject_channel(query_set, attempt_network, timeout, captured_at)
    query_by_id = {row["id"]: row for row in query_set["queries"]}
    for program in PROGRAMS:
        _merge_subject_candidates(
            program,
            program_candidates[program],
            subject_channel["attempts"],
            query_by_id,
            corpus,
            source["programs"][program],
        )
    kindergeld_section_31 = program_candidates["de/kindergeld"].get(
        "corpus:de/statute/estg/31"
    )
    if kindergeld_section_31 is not None:
        kindergeld_section_31.seed_ids.add("de-kg-instr-003")
    citation_channel = _add_receipt(
        {
            "state": "not_yet_available",
            "issue": "axiom-corpus#611",
            "reason": "The corpus citation-scan channel has not landed; no citation-scan candidates are asserted.",
        }
    )
    rendered_programs = [
        {"id": program, "instruments": _render_candidates(program, program_candidates[program])}
        for program in PROGRAMS
    ]
    kindergeld = next(row for row in rendered_programs if row["id"] == "de/kindergeld")
    kindergeld_candidate_ids = {row["id"] for row in kindergeld["instruments"]}
    for seed in ("de-kg-instr-001", "de-kg-instr-002", "de-kg-instr-003"):
        if seed not in kindergeld_candidate_ids:
            raise CaptureError(f"required Kindergeld candidate seed is missing: {seed}")
    kindergeld["seed_bindings"] = [
        {
            "id": seed,
            "binding_kind": "instrument_candidate",
            "candidate_id": seed,
            "status": "pending",
        }
        for seed in ("de-kg-instr-001", "de-kg-instr-002", "de-kg-instr-003")
    ] + [
        {
            "id": "de-kg-instr-004",
            "binding_kind": "spine_scope_receipt",
            "status": "pending",
            "scope": "de/statute/estg direct provisions with corpus ordinal 62 through 78 inclusive",
        },
        {
            "id": "de-kg-instr-005",
            "binding_kind": "discovery_channel_receipts",
            "status": "pending",
            "receipts": {
                name: channel["receipt_sha256"]
                for name, channel in (
                    ("corpus_release", corpus_channel),
                    ("subject_matter_search", subject_channel),
                    ("citation_scan", citation_channel),
                )
            },
        },
    ]
    snapshot: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": captured_at,
        "source": {"path": str(source_file.relative_to(REPO_ROOT)), "sha256": _sha(source_raw)},
        "query_set": {"path": str(query_path.relative_to(REPO_ROOT)), "sha256": _sha(query_raw)},
        "channels": {
            "corpus_release": corpus_channel,
            "subject_matter_search": subject_channel,
            "citation_scan": citation_channel,
        },
        "programs": rendered_programs,
    }
    snapshot = _add_receipt(snapshot)
    validate_snapshot(
        snapshot,
        source_path=source_file,
        query_set_path=query_path,
        corpus=corpus,
    )
    return snapshot


def validate_snapshot(
    snapshot: Mapping[str, Any],
    *,
    source_path: Path = DEFAULT_SOURCE,
    query_set_path: Path = DEFAULT_QUERY_SET,
    corpus: Corpus | None = None,
) -> None:
    """Validate receipts and the all-pending graph invariants."""
    if snapshot.get("schema") != SCHEMA:
        raise CaptureError(f"expected snapshot schema {SCHEMA}")
    if set(snapshot.get("channels", {})) != {
        "corpus_release", "subject_matter_search", "citation_scan"
    }:
        raise CaptureError("snapshot must contain exactly the three DE discovery channels")
    _verify_receipt(snapshot, "snapshot")
    for key, path in (("source", source_path), ("query_set", query_set_path)):
        binding = snapshot.get(key)
        if not isinstance(binding, Mapping):
            raise CaptureError(f"snapshot {key} binding is missing")
        try:
            expected_path = path.resolve().relative_to(REPO_ROOT).as_posix()
            expected_sha = _sha(path.read_bytes())
        except (OSError, ValueError) as exc:
            raise CaptureError(f"cannot verify snapshot {key} binding: {exc}") from exc
        if binding != {"path": expected_path, "sha256": expected_sha}:
            raise CaptureError(f"snapshot {key} binding does not match committed bytes")
    channels = snapshot["channels"]
    for name, channel in channels.items():
        if not isinstance(channel, dict):
            raise CaptureError(f"channel {name} is not a mapping")
        _verify_receipt(channel, f"channel {name}")
    if channels["corpus_release"].get("state") != "retrieved":
        raise CaptureError("corpus-release channel must be retrieved")
    global_index = channels["corpus_release"].get("global_extraction_index")
    if not isinstance(global_index, Mapping):
        raise CaptureError("corpus-release channel lacks the global extraction index")
    _validate_global_extraction_index(
        global_index,
        scanned_row_count=channels["corpus_release"].get("scanned_row_count"),
    )
    if corpus is not None and global_index != _global_corpus_extraction_index(corpus):
        raise CaptureError("global corpus extraction index does not rederive")
    citation = channels["citation_scan"]
    if (
        citation.get("state") != "not_yet_available"
        or citation.get("issue") != "axiom-corpus#611"
    ):
        raise CaptureError("citation channel must be the axiom-corpus#611 placeholder")
    attempts = channels["subject_matter_search"].get("attempts")
    if not isinstance(attempts, list):
        raise CaptureError("subject channel attempts must be a list")
    evidence_ids = {
        row.get("id") for row in channels["corpus_release"].get("evidence", [])
        if isinstance(row, dict)
    }
    attempt_ids: set[str] = set()
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise CaptureError(f"attempt {index} is not a mapping")
        _verify_receipt(attempt, f"attempt {attempt.get('id', index)}")
        attempt_id = attempt.get("id")
        if not isinstance(attempt_id, str) or attempt_id in attempt_ids:
            raise CaptureError("subject attempt ids must be unique strings")
        if attempt.get("state") not in {"retrieved", "unretrieved"}:
            raise CaptureError(f"invalid attempt state: {attempt_id}")
        if attempt["state"] == "retrieved" and not re.fullmatch(
            r"[0-9a-f]{64}", str(attempt.get("content_sha256", ""))
        ):
            raise CaptureError(f"retrieved attempt lacks content sha: {attempt_id}")
        if attempt["state"] == "unretrieved" and not isinstance(attempt.get("reason"), str):
            raise CaptureError(f"unretrieved attempt lacks reason: {attempt_id}")
        attempt_ids.add(attempt_id)
    if [row["id"] for row in attempts] != sorted(attempt_ids):
        raise CaptureError("subject attempts must be sorted by unique id")
    attempt_states = {row["state"] for row in attempts}
    expected_subject_state = (
        "retrieved"
        if attempt_states == {"retrieved"}
        else "unretrieved"
        if attempt_states == {"unretrieved"}
        else "partial"
    )
    if channels["subject_matter_search"].get("state") != expected_subject_state:
        raise CaptureError("subject channel state does not derive from attempt states")
    evidence = channels["corpus_release"].get("evidence")
    if not isinstance(evidence, list) or any(not isinstance(row, Mapping) for row in evidence):
        raise CaptureError("corpus evidence must be a list of mappings")
    evidence_order = [row.get("id") for row in evidence]
    if (
        any(not isinstance(value, str) for value in evidence_order)
        or evidence_order != sorted(evidence_order)
        or len(evidence_order) != len(set(evidence_order))
    ):
        raise CaptureError("corpus evidence ids must be unique and sorted")
    valid_refs = evidence_ids | attempt_ids
    programs = snapshot.get("programs")
    if (
        not isinstance(programs, list)
        or any(not isinstance(row, Mapping) for row in programs)
        or [row.get("id") for row in programs] != list(PROGRAMS)
    ):
        raise CaptureError("snapshot programs must be the sorted preregistered program list")
    for program in programs:
        if not isinstance(program, Mapping):
            raise CaptureError("snapshot program rows must be mappings")
        instruments = program.get("instruments")
        if not isinstance(instruments, list):
            raise CaptureError(f"{program['id']}: instruments must be a list")
        ids: set[str] = set()
        ordered_ids = [
            row.get("id") for row in instruments if isinstance(row, Mapping)
        ]
        if ordered_ids != sorted(ordered_ids):
            raise CaptureError(f"{program['id']}: instruments must be sorted by id")
        for row in instruments:
            if not isinstance(row, Mapping):
                raise CaptureError(f"{program['id']}: instrument rows must be mappings")
            candidate_id = row.get("id")
            refs = row.get("discovery_refs")
            if not isinstance(candidate_id, str) or candidate_id in ids:
                raise CaptureError(f"{program['id']}: candidate ids must be unique strings")
            if row.get("status") != "pending":
                raise CaptureError(f"{program['id']}/{candidate_id}: status must be pending")
            if (
                not isinstance(refs, list)
                or not refs
                or refs != sorted(set(refs))
                or not all(isinstance(ref, str) and ref in valid_refs for ref in refs)
            ):
                raise CaptureError(f"{program['id']}/{candidate_id}: invalid discovery_refs")
            ids.add(candidate_id)
        if program["id"] == "de/kindergeld":
            bindings = program.get("seed_bindings")
            if (
                not isinstance(bindings, list)
                or any(not isinstance(row, Mapping) for row in bindings)
                or [row.get("id") for row in bindings] != [
                    f"de-kg-instr-{number:03d}" for number in range(1, 6)
                ]
            ):
                raise CaptureError("Kindergeld seed bindings 001 through 005 are required")
            if any(
                not isinstance(row, Mapping)
                or row.get("status") != "pending"
                or (
                    row.get("binding_kind") == "instrument_candidate"
                    and row.get("candidate_id") not in ids
                )
                for row in bindings
            ):
                raise CaptureError("Kindergeld seed binding does not resolve")


def serialize(snapshot: Mapping[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _semantic_for_diff(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(snapshot))
    value.pop("generated_at", None)
    value.pop("receipt_sha256", None)
    for attempt in value.get("channels", {}).get("subject_matter_search", {}).get("attempts", []):
        attempt.pop("captured_at", None)
        attempt.pop("receipt_sha256", None)
    value.get("channels", {}).get("subject_matter_search", {}).pop("receipt_sha256", None)
    return value


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--capture", action="store_true", help="capture and write the snapshot (default)")
    mode.add_argument(
        "--check-snapshot",
        action="store_true",
        help="validate committed snapshot bytes without corpus or network access",
    )
    parser.add_argument("--offline", action="store_true", help="capture explicit unretrieved attempts without network")
    parser.add_argument("--diff", action="store_true", help="capture, show semantic drift, and write nothing")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--query-set", type=Path, default=DEFAULT_QUERY_SET)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        if args.check_snapshot:
            payload = json.loads(args.output.read_bytes())
            validate_snapshot(
                payload,
                source_path=args.source,
                query_set_path=args.query_set,
            )
            print(f"valid: {args.output}")
            return 0
        if args.timeout <= 0:
            raise CaptureError("--timeout must be positive")
        snapshot = build_snapshot(
            args.query_set,
            args.source,
            args.corpus_root,
            attempt_network=not args.offline,
            timeout=args.timeout,
        )
        if args.diff:
            if not args.output.exists():
                print(f"no committed snapshot: {args.output}")
                return 1
            committed = json.loads(args.output.read_bytes())
            left = json.dumps(_semantic_for_diff(committed), ensure_ascii=False, indent=2, sort_keys=True).splitlines()
            right = json.dumps(_semantic_for_diff(snapshot), ensure_ascii=False, indent=2, sort_keys=True).splitlines()
            if left == right:
                print("DE instrument graph unchanged")
                return 0
            print("\n".join(difflib.unified_diff(left, right, fromfile="committed", tofile="fresh", lineterm="")))
            return 1
        _write_atomic(args.output, serialize(snapshot))
        counts = {row["id"]: len(row["instruments"]) for row in snapshot["programs"]}
        print(f"wrote {args.output}: {counts}")
        return 0
    except (CaptureError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
