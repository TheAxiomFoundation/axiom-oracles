#!/usr/bin/env python3
"""Parse a captured DE subject document into per-heading frontier rows.

This is the ops producer for the measured instrument frontier's document
layer. The committed instrument snapshot (``de-instrument-graph.json``)
records that a subject-matter query retrieved a document and binds its bytes
by ``content_sha256``; this script reads a local copy of that document,
refuses it unless the bytes match the receipt, extracts its table of contents
and section bodies with ``pdftotext -layout``, and writes
``conformance/closure/de-subject-document-headings.json``: one row per
numbered heading, each binding the document hash, the heading text, and the
located section text (``body_sha256``) that a later disposition must cite.

The closure-ledger producer consumes only the committed JSON and never reads
the PDF or runs pdftotext. ``--check`` validates the committed JSON against
the snapshot without either.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT = REPO_ROOT / "conformance" / "closure" / "de-instrument-graph.json"
DEFAULT_OUTPUT = REPO_ROOT / "conformance" / "closure" / "de-subject-document-headings.json"
SCHEMA = "axiom_oracles.closure.de_subject_document_headings.v1"
SNAPSHOT_SCHEMA = "axiom_oracles.closure.de_instrument_graph.v1"
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: DA-KG chapter letters: O Organisation, A Anspruchsvoraussetzungen,
#: V Verfahren, R Rechtsbehelfe, S Sonstiges. A numbered heading is
#: ``<letter><space?><n(.n)*>`` followed by a title.
_HEADING_START = re.compile(r"^\s*([AOVSR])\s?(\d+(?:\.\d+)*)\s{2,}(\S.*?)\s*$")
_TOC_PAGE_TAIL = re.compile(r"^(.*?)\s{2,}(\d+)\s*$")
_TOC_INLINE = re.compile(r"^\s*([AOVSR])\s?(\d+(?:\.\d+)*)\s{2,}(\S.*?)\s{2,}(\d+)\s*$")


class ParseError(RuntimeError):
    pass


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _add_receipt(value: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(value)
    value.pop("receipt_sha256", None)
    value["receipt_sha256"] = _sha(_canonical_bytes(value))
    return value


def _verify_receipt(value: Mapping[str, Any], where: str) -> None:
    receipt = value.get("receipt_sha256")
    if not isinstance(receipt, str) or not _HEX_SHA256.fullmatch(receipt):
        raise ParseError(f"{where}: missing or malformed receipt_sha256")
    material = dict(value)
    material.pop("receipt_sha256", None)
    if _sha(_canonical_bytes(material)) != receipt:
        raise ParseError(f"{where}: receipt mismatch")


def heading_id(program: str, code: str) -> str:
    prefix = {"de/kindergeld": "de-kg", "de/unterhaltsvorschuss": "de-uhv", "de/rv-employee-contribution": "de-rv"}[program]
    return f"{prefix}-dakg-{code.replace(' ', '')}"


def parse_toc(text: str) -> tuple[list[dict[str, Any]], int, int]:
    """Return (entries, toc_start_line, toc_end_line) from pdftotext output.

    Entries are numbered headings in table-of-contents order. A wrapped entry
    (title continued on following lines, page number on the last) is joined.
    """

    lines = text.split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "Inhaltsverzeichnis")
    except StopIteration as exc:
        raise ParseError("no Inhaltsverzeichnis line in extracted text") from exc
    try:
        end = next(
            i for i, line in enumerate(lines) if i > start and line.strip().startswith("Abkürzungsverzeichnis")
        )
    except StopIteration as exc:
        raise ParseError("no Abkürzungsverzeichnis line closing the table of contents") from exc

    entries: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for line_no in range(start + 1, end):
        line = lines[line_no]
        if not line.strip():
            continue
        inline = _TOC_INLINE.match(line)
        if inline:
            if pending is not None:
                raise ParseError(f"table-of-contents entry {pending['code']} never closed with a page number")
            entries.append(
                {
                    "code": f"{inline.group(1)} {inline.group(2)}",
                    "title": _squash(inline.group(3)),
                    "toc_page": int(inline.group(4)),
                    "toc_line": line_no,
                }
            )
            continue
        started = _HEADING_START.match(line)
        if started:
            if pending is not None:
                raise ParseError(f"table-of-contents entry {pending['code']} never closed with a page number")
            pending = {
                "code": f"{started.group(1)} {started.group(2)}",
                "title": _squash(started.group(3)),
                "toc_line": line_no,
            }
            continue
        if pending is not None:
            tail = _TOC_PAGE_TAIL.match(line)
            if tail and tail.group(1).strip():
                pending["title"] = _squash(pending["title"] + " " + tail.group(1))
                pending["toc_page"] = int(tail.group(2))
                entries.append(pending)
                pending = None
            elif line.strip().isdigit():
                pending["toc_page"] = int(line.strip())
                entries.append(pending)
                pending = None
            else:
                pending["title"] = _squash(pending["title"] + " " + line)
    if pending is not None:
        raise ParseError(f"table-of-contents entry {pending['code']} never closed with a page number")
    codes = [entry["code"] for entry in entries]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        raise ParseError(f"duplicate table-of-contents codes: {duplicates}")
    return entries, start, end


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def locate_sections(text: str, entries: list[dict[str, Any]], body_start_line: int) -> list[dict[str, Any]]:
    """Find each heading's first body occurrence after the table of contents
    and bind the section text up to the next located heading."""

    lines = text.split("\n")
    located: list[tuple[int, int]] = []  # (line_no, entry index)
    for index, entry in enumerate(entries):
        letter, number = entry["code"].split(" ")
        title_prefix = re.escape(entry["title"][:12])
        pattern = re.compile(r"^\s*" + letter + r"\s?" + re.escape(number) + r"\s+" + title_prefix)
        found = next(
            (line_no for line_no in range(body_start_line, len(lines)) if pattern.match(lines[line_no])),
            None,
        )
        if found is not None:
            located.append((found, index))
    located.sort()
    bounds: dict[int, tuple[int, int]] = {}
    for position, (line_no, index) in enumerate(located):
        end_line = located[position + 1][0] if position + 1 < len(located) else len(lines)
        bounds[index] = (line_no, end_line)
    rows = []
    for index, entry in enumerate(entries):
        row = dict(entry)
        row["heading_sha256"] = _sha(f"{entry['code']}\t{entry['title']}".encode("utf-8"))
        if index in bounds:
            start_line, end_line = bounds[index]
            section = "\n".join(line.rstrip() for line in lines[start_line:end_line]).strip("\n")
            row.update(
                {
                    "section_located": True,
                    "section_line_start": start_line,
                    "section_line_end": end_line,
                    "section_char_count": len(section),
                    "body_sha256": _sha(section.encode("utf-8")),
                }
            )
        else:
            row["section_located"] = False
        rows.append(row)
    return rows


def _pdftotext_version() -> str:
    try:
        completed = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ParseError(f"pdftotext is not available: {exc}") from exc
    banner = (completed.stderr or completed.stdout).strip().splitlines()
    if not banner or "pdftotext" not in banner[0]:
        raise ParseError("cannot read the pdftotext version banner")
    return banner[0].split()[-1]


def _extract_text(pdf_path: Path) -> str:
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ParseError(f"pdftotext failed on {pdf_path}: {exc}") from exc
    return completed.stdout.decode("utf-8")


def _page_count(pdf_path: Path) -> int | None:
    try:
        completed = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[-1])
    return None


def _snapshot_attempt(snapshot: Mapping[str, Any], subject_id: str) -> dict[str, Any]:
    attempts = snapshot.get("channels", {}).get("subject_matter_search", {}).get("attempts") or []
    match = next((row for row in attempts if row.get("id") == subject_id), None)
    if match is None:
        raise ParseError(f"snapshot has no subject-matter attempt {subject_id}")
    if match.get("state") != "retrieved" or not isinstance(match.get("content_sha256"), str):
        raise ParseError(f"{subject_id} was not retrieved with a content hash in the snapshot")
    return match


def _seed_for(snapshot: Mapping[str, Any], program: str, subject_id: str) -> str:
    programs = snapshot.get("programs") or []
    block = next((row for row in programs if row.get("id") == program), None)
    if block is None:
        raise ParseError(f"snapshot has no program {program}")
    seeds = [
        row["id"]
        for row in block.get("instruments") or []
        if row.get("identity_kind") == "subject_seed" and subject_id in (row.get("discovery_refs") or [])
    ]
    if len(seeds) != 1:
        raise ParseError(f"{program}: expected exactly one subject_seed candidate citing {subject_id}, found {seeds}")
    return seeds[0]


def build_document(
    *,
    snapshot: Mapping[str, Any],
    program: str,
    subject_id: str,
    pdf_bytes: bytes,
    text: str,
    tool_version: str,
    page_count: int | None,
) -> dict[str, Any]:
    attempt = _snapshot_attempt(snapshot, subject_id)
    content_sha = _sha(pdf_bytes)
    if content_sha != attempt["content_sha256"]:
        raise ParseError(
            f"{subject_id}: local document bytes {content_sha} do not match the snapshot receipt "
            f"{attempt['content_sha256']}"
        )
    entries, toc_start, toc_end = parse_toc(text)
    headings = locate_sections(text, entries, toc_end + 1)
    for row in headings:
        row["id"] = heading_id(program, row["code"])
    ids = [row["id"] for row in headings]
    if len(ids) != len(set(ids)):
        raise ParseError("heading ids collide")
    document = {
        "subject_id": subject_id,
        "program": program,
        "seed_candidate_id": _seed_for(snapshot, program, subject_id),
        "url": attempt.get("final_url") or attempt.get("url"),
        "content_sha256": content_sha,
        "byte_count": len(pdf_bytes),
        "page_count": page_count,
        "text_sha256": _sha(text.encode("utf-8")),
        "extraction": {"tool": "pdftotext", "version": tool_version, "arguments": ["-layout"]},
        "toc": {"start_line": toc_start, "end_line": toc_end, "entry_count": len(entries)},
        "heading_count": len(headings),
        "sections_located": sum(1 for row in headings if row["section_located"]),
        "headings": headings,
    }
    return _add_receipt(document)


def validate_artifact(payload: Any, snapshot: Mapping[str, Any], snapshot_raw: bytes, snapshot_relative: str) -> None:
    """Hermetic validation against the committed snapshot: bindings, receipts,
    identities, and per-row shape. Never touches the PDF."""

    if not isinstance(payload, Mapping) or payload.get("schema") != SCHEMA:
        raise ParseError(f"headings artifact must carry schema {SCHEMA}")
    if set(payload) != {"schema", "snapshot", "documents", "receipt_sha256"}:
        raise ParseError("headings artifact top-level keys are not canonical")
    if payload.get("snapshot") != {"path": snapshot_relative, "sha256": _sha(snapshot_raw)}:
        raise ParseError("headings artifact does not bind the committed instrument snapshot")
    _verify_receipt(payload, "headings artifact")
    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ParseError("headings artifact must list at least one document")
    seen_subjects: set[str] = set()
    for document in documents:
        if not isinstance(document, Mapping):
            raise ParseError("document row must be a mapping")
        where = f"document {document.get('subject_id')}"
        _verify_receipt(document, where)
        subject_id = document.get("subject_id")
        if not isinstance(subject_id, str) or subject_id in seen_subjects:
            raise ParseError(f"{where}: subject_id missing or duplicated")
        seen_subjects.add(subject_id)
        attempt = _snapshot_attempt(snapshot, subject_id)
        if document.get("content_sha256") != attempt["content_sha256"]:
            raise ParseError(f"{where}: content_sha256 does not match the snapshot receipt")
        if document.get("byte_count") != attempt.get("byte_count"):
            raise ParseError(f"{where}: byte_count does not match the snapshot receipt")
        program = document.get("program")
        if document.get("seed_candidate_id") != _seed_for(snapshot, str(program), subject_id):
            raise ParseError(f"{where}: seed_candidate_id does not match the snapshot's subject seed")
        headings = document.get("headings")
        if not isinstance(headings, list) or document.get("heading_count") != len(headings):
            raise ParseError(f"{where}: heading_count does not match the rows")
        located = 0
        ids: list[str] = []
        for row in headings:
            if not isinstance(row, Mapping):
                raise ParseError(f"{where}: heading row must be a mapping")
            code = row.get("code")
            if not isinstance(code, str) or row.get("id") != heading_id(str(program), code):
                raise ParseError(f"{where}: heading id does not derive from its code")
            ids.append(row["id"])
            if not isinstance(row.get("title"), str) or not row["title"].strip():
                raise ParseError(f"{where}: heading {code} has no title")
            if row.get("heading_sha256") != _sha(f"{code}\t{row['title']}".encode("utf-8")):
                raise ParseError(f"{where}: heading {code} hash does not bind its code and title")
            if row.get("section_located") is True:
                located += 1
                if not isinstance(row.get("body_sha256"), str) or not _HEX_SHA256.fullmatch(row["body_sha256"]):
                    raise ParseError(f"{where}: located heading {code} lacks a body_sha256")
            elif row.get("section_located") is not False or "body_sha256" in row:
                raise ParseError(f"{where}: heading {code} section binding is malformed")
        if len(ids) != len(set(ids)):
            raise ParseError(f"{where}: heading ids collide")
        if document.get("sections_located") != located:
            raise ParseError(f"{where}: sections_located does not match the rows")


def load_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    snapshot = json.loads(raw)
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ParseError(f"{path}: expected schema {SNAPSHOT_SCHEMA}")
    return snapshot, raw


def serialize(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--parse", action="store_true", help="parse a local copy of the document and write the artifact (default)")
    mode.add_argument("--check", action="store_true", help="validate the committed artifact against the snapshot")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--program", default="de/kindergeld")
    parser.add_argument("--subject-id", default="de-subject-003")
    parser.add_argument("--pdf", type=Path, help="local copy of the retrieved document (bytes must match the snapshot receipt)")
    args = parser.parse_args(argv)
    try:
        snapshot, raw = load_snapshot(args.snapshot)
        relative = args.snapshot.resolve().relative_to(REPO_ROOT).as_posix()
        if args.check:
            payload = json.loads(args.output.read_bytes())
            validate_artifact(payload, snapshot, raw, relative)
            counts = {row["subject_id"]: f"{row['sections_located']}/{row['heading_count']} located" for row in payload["documents"]}
            print(f"valid: {args.output.relative_to(REPO_ROOT)} {counts}")
            return 0
        if args.pdf is None:
            raise ParseError("--parse requires --pdf")
        pdf_bytes = args.pdf.read_bytes()
        text = _extract_text(args.pdf)
        document = build_document(
            snapshot=snapshot,
            program=args.program,
            subject_id=args.subject_id,
            pdf_bytes=pdf_bytes,
            text=text,
            tool_version=_pdftotext_version(),
            page_count=_page_count(args.pdf),
        )
        documents: list[dict[str, Any]] = []
        if args.output.exists():
            existing = json.loads(args.output.read_bytes())
            documents = [row for row in existing.get("documents", []) if row.get("subject_id") != args.subject_id]
        documents.append(document)
        documents.sort(key=lambda row: row["subject_id"])
        payload = _add_receipt(
            {
                "schema": SCHEMA,
                "snapshot": {"path": relative, "sha256": _sha(raw)},
                "documents": documents,
            }
        )
        validate_artifact(payload, snapshot, raw, relative)
        args.output.write_text(serialize(payload), encoding="utf-8")
        print(
            f"wrote {args.output.relative_to(REPO_ROOT)}: {args.subject_id} "
            f"{document['sections_located']}/{document['heading_count']} headings located"
        )
        return 0
    except (ParseError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
