#!/usr/bin/env python3
"""Recompute every committed US tariff evidence capture digest offline.

The producer re-derivation tests for the boundary-evidence receipts skip
unless the frozen corpus, RuleSpec and engine checkouts are configured, and
the identity PDF re-extraction skips without pdftotext, so in a clean checkout
those tests re-hash few of the raw captures. This check needs none of that
configuration. It reads every JSON document under
reference/us-tariff-schedule/boundary-evidence/, collects each SHA-256 (and
byte count, where recorded) that one of them records for a file in that
directory, recomputes it from the committed bytes, and fails on:

* a digest or size that differs from any recorded value;
* a recorded file that is missing;
* a capture file (anything other than a top-level receipt or manifest JSON)
  that no receipt or manifest records;
* a digest-bearing record this checker does not know how to resolve, so a new
  record shape fails closed instead of going unchecked;
* a replay manifest whose recorded manifest_sha256 no longer matches its own
  rendered manifest, or a frontier inventory that pins a different one.

It checks recorded bytes only. It does not re-extract PDF text, rerun the
engine or verify the corpus Ed25519 signature; the producers' --check paths
and their integration-gated tests do that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PREFIX = "reference/us-tariff-schedule/boundary-evidence/"
EVIDENCE_DIRECTORY = ROOT / EVIDENCE_PREFIX

CONTINUATION_MANIFEST = "continuation-replay-manifest.json"
OFFLINE_MANIFEST = "offline-replay-manifest.json"
FRONTIER_INVENTORY = "frontier-inventory.json"
NOTE2_RECEIPT = "note2-exceptions.json"
LIVE_RECEIPT = "live-sources/receipt.json"
ORIGINAL_INGEST_MANIFEST = "live-sources/original-ingest-manifest.json"

# Receipts that record raw captures by bare file name ({"file", "sha256",
# "bytes"}), and the capture directory those names resolve against. These are
# the producers' DIRECTORY constants; tests/test_us_tariff_capture_integrity.py
# pins the correspondence.
FILE_RECORD_DIRECTORIES = {
    "china-action.json": "china-action-sources",
    "column2-resolution.json": "column2-sources",
    "hts-identity.json": "identity-sources",
    "primary-metals.json": "identity-sources",
    "temporal-boundaries.json": "temporal-sources",
    LIVE_RECEIPT: "live-sources",
}

# Fields that pin another committed receipt by digest.
RECEIPT_DIGEST_FIELDS = {
    "chapter99_live_receipt_sha256": LIVE_RECEIPT,
    "live_source_receipt_sha256": LIVE_RECEIPT,
    "identity_receipt_sha256": "hts-identity.json",
}

# The live receipt's signature block pins these captured files by digest.
SIGNATURE_DIGEST_FIELDS = {
    "manifest_sha256": ORIGINAL_INGEST_MANIFEST,
    "canonical_verifier_sha256": "live-sources/ingest_manifests.py",
}

# The original note2 receipt names its source by frozen corpus path; the
# continuation bundle binds those bytes to these captured copies
# (tariff_continuation_replay_bundle.validate_bindings).
NOTE2_SOURCE_CAPTURES = {
    "pdf": "live-sources/chapter99.pdf",
    "notes": "live-sources/provisions.jsonl",
    "ingest_manifest": ORIGINAL_INGEST_MANIFEST,
}

# The offline boundary bundle packages these same bytes under bundle paths
# (tariff_boundary_replay_bundle.verify binds them to the note2 source).
OFFLINE_BUNDLE_ALIASES = {
    "evidence.json": NOTE2_RECEIPT,
    "sources/chapter-99.pdf": "live-sources/chapter99.pdf",
    "sources/provisions.jsonl": "live-sources/provisions.jsonl",
    "sources/ingest-manifest.json": ORIGINAL_INGEST_MANIFEST,
}

# Digest fields that bind something other than a file in this directory:
# RuleSpec modules, compiled programs, engine binaries, producer scripts,
# canonical request/response bodies, extracted PDF text, single JSONL records,
# the trusted public-key value, the input-scope contract and the gzipped
# replay bundles, which are not committed.
NON_FILE_DIGEST_FIELDS = frozenset(
    {
        "bundle_sha256",
        "canonical_scope_sha256",
        "compiled_sha256",
        "engine_sha256",
        "extracted_page_sha256",
        "native_runtime_helper_sha256",
        "producer_sha256",
        "raw_record_sha256",
        "request_sha256",
        "response_sha256",
        "runtime_helper_sha256",
        "trusted_key_sha256",
    }
)


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def render(value: object) -> bytes:
    """The replay bundles' manifest rendering (sorted keys, indent 2)."""
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


class Record(NamedTuple):
    """One recorded digest (and optional size) for one evidence file."""

    path: str
    sha256: Any
    bytes: Any
    recorded_by: str


def _walk(node: Any, pointer: str = "$") -> Iterator[tuple[str, dict]]:
    if isinstance(node, dict):
        yield pointer, node
        for key, value in node.items():
            yield from _walk(value, f"{pointer}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{pointer}[{index}]")


def _safe_relative(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (
        bool(parts)
        and not PurePosixPath(path).is_absolute()
        and all(part not in ("", ".", "..") for part in parts)
        and "\\" not in path
        and str(PurePosixPath(path)) == path
    )


def _documents(directory: Path) -> tuple[dict[str, Any], list[str]]:
    """Every JSON document in the evidence tree, keyed by relative path."""
    documents: dict[str, Any] = {}
    problems: list[str] = []
    for path in sorted(directory.rglob("*.json")):
        relative = path.relative_to(directory).as_posix()
        try:
            documents[relative] = json.loads(path.read_bytes())
        except ValueError as exc:
            problems.append(f"{relative}: not parseable JSON ({exc})")
    return documents, problems


def _url_captures(directory: Path, documents: dict[str, Any]) -> dict[str, str]:
    """Authoritative URL -> captured PDF, from each capture's curl metadata."""
    captures: dict[str, str] = {}
    for relative, document in documents.items():
        if not relative.endswith(".curl.json") or not isinstance(document, dict):
            continue
        url = document.get("url_effective")
        pdf = relative.removesuffix(".curl.json") + ".pdf"
        if isinstance(url, str) and (directory / pdf).is_file():
            captures.setdefault(url, pdf)
    return captures


def collect_records(
    directory: Path, documents: dict[str, Any]
) -> tuple[list[Record], list[str]]:
    """Every recorded file digest, plus problems for unresolvable records."""
    records: list[Record] = []
    problems: list[str] = []
    urls = _url_captures(directory, documents)

    for relative, document in documents.items():
        capture_directory = FILE_RECORD_DIRECTORIES.get(relative)
        for pointer, node in _walk(document):
            where = f"{relative} {pointer}"
            if "file" in node and "sha256" in node:
                if capture_directory is None:
                    problems.append(
                        f"{where}: file digest record in a receipt with no "
                        "known capture directory"
                    )
                else:
                    records.append(
                        Record(
                            f"{capture_directory}/{node['file']}",
                            node["sha256"],
                            node.get("bytes"),
                            where,
                        )
                    )
            path = node.get("path")
            if (
                "sha256" in node
                and isinstance(path, str)
                and path.startswith(EVIDENCE_PREFIX)
            ):
                records.append(
                    Record(
                        path.removeprefix(EVIDENCE_PREFIX),
                        node["sha256"],
                        node.get("bytes"),
                        where,
                    )
                )
            if "pdf_sha256" in node:
                url = node.get("url")
                if url not in urls:
                    problems.append(
                        f"{where}: pdf_sha256 names no captured URL ({url!r})"
                    )
                else:
                    records.append(Record(urls[url], node["pdf_sha256"], None, where))
            for key, value in node.items():
                if not key.endswith("_receipt_sha256"):
                    continue
                target = RECEIPT_DIGEST_FIELDS.get(key)
                if target is None:
                    problems.append(f"{where}.{key}: unknown receipt digest field")
                else:
                    records.append(Record(target, value, None, f"{where}.{key}"))

    live = documents.get(LIVE_RECEIPT)
    if isinstance(live, dict):
        signature = live.get("signature_verification") or {}
        for key, target in SIGNATURE_DIGEST_FIELDS.items():
            if key not in signature:
                problems.append(f"{LIVE_RECEIPT}: signature_verification.{key} missing")
                continue
            records.append(
                Record(
                    target,
                    signature[key],
                    None,
                    f"{LIVE_RECEIPT} $.signature_verification.{key}",
                )
            )

    note2 = documents.get(NOTE2_RECEIPT)
    corpus_captures: dict[str, str] = {}
    if isinstance(note2, dict):
        source = note2.get("source") or {}
        for key, target in NOTE2_SOURCE_CAPTURES.items():
            entry = source.get(key)
            if not isinstance(entry, dict) or "path" not in entry:
                problems.append(f"{NOTE2_RECEIPT}: source.{key} has no corpus path")
                continue
            corpus_captures[entry["path"]] = target
            records.append(
                Record(
                    target,
                    entry.get("sha256"),
                    entry.get("bytes"),
                    f"{NOTE2_RECEIPT} $.source.{key}",
                )
            )

    ingest = documents.get(ORIGINAL_INGEST_MANIFEST)
    if isinstance(ingest, dict):
        for index, entry in enumerate(ingest.get("applied_files") or []):
            target = corpus_captures.get(entry.get("path"))
            if target is not None:
                records.append(
                    Record(
                        target,
                        entry.get("sha256"),
                        None,
                        f"{ORIGINAL_INGEST_MANIFEST} $.applied_files[{index}]",
                    )
                )

    for name, aliases in (
        (CONTINUATION_MANIFEST, None),
        (OFFLINE_MANIFEST, OFFLINE_BUNDLE_ALIASES),
    ):
        replay = documents.get(name)
        if not isinstance(replay, dict):
            problems.append(f"{name}: missing replay manifest")
            continue
        manifest = replay.get("manifest") or {}
        recorded = (replay.get("verification") or {}).get("manifest_sha256")
        if sha256(render(manifest)) != recorded:
            problems.append(
                f"{name}: verification.manifest_sha256 does not match the "
                "rendered manifest"
            )
        for member, entry in sorted((manifest.get("files") or {}).items()):
            if aliases is None:
                if not member.startswith(EVIDENCE_PREFIX):
                    continue
                target = member.removeprefix(EVIDENCE_PREFIX)
            else:
                target = aliases.get(member)
                if target is None:
                    continue
            records.append(
                Record(
                    target,
                    entry.get("sha256"),
                    entry.get("bytes"),
                    f"{name} $.manifest.files[{member!r}]",
                )
            )

    inventory = documents.get(FRONTIER_INVENTORY)
    continuation = documents.get(CONTINUATION_MANIFEST)
    if isinstance(inventory, dict) and isinstance(continuation, dict):
        if (inventory.get("replay_manifest") or {}).get("manifest_sha256") != (
            continuation.get("verification") or {}
        ).get("manifest_sha256"):
            problems.append(
                f"{FRONTIER_INVENTORY}: replay_manifest.manifest_sha256 differs "
                f"from {CONTINUATION_MANIFEST}"
            )

    return records, problems


# Where each non-generic file-digest field may appear. Anywhere else it is an
# unresolved record and fails closed.
DIGEST_FIELD_LOCATIONS = {
    "manifest_sha256": {
        (LIVE_RECEIPT, "$.signature_verification"),
        (CONTINUATION_MANIFEST, "$.verification"),
        (OFFLINE_MANIFEST, "$.verification"),
        (FRONTIER_INVENTORY, "$.replay_manifest"),
    },
    "canonical_verifier_sha256": {(LIVE_RECEIPT, "$.signature_verification")},
}


def _unresolved_digest_fields(documents: dict[str, Any]) -> list[str]:
    """Digest-bearing keys that no extractor above resolves (fail closed)."""
    problems = []
    for relative, document in documents.items():
        for pointer, node in _walk(document):
            for key in node:
                if "sha256" not in key:
                    continue
                if key in NON_FILE_DIGEST_FIELDS or key.endswith("_receipt_sha256"):
                    continue
                if key == "pdf_sha256":
                    continue  # resolved by URL or reported by collect_records
                if key == "sha256":
                    resolved = (
                        "file" in node
                        or "path" in node
                        or (
                            relative in (CONTINUATION_MANIFEST, OFFLINE_MANIFEST)
                            and pointer.startswith("$.manifest.files.")
                        )
                    )
                else:
                    resolved = (relative, pointer) in DIGEST_FIELD_LOCATIONS.get(
                        key, ()
                    )
                if not resolved:
                    problems.append(
                        f"{relative} {pointer}.{key}: digest field this check "
                        "cannot resolve to a file"
                    )
    return problems


def capture_files(directory: Path) -> list[str]:
    """Everything except the top-level receipt and manifest JSON documents."""
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and not (path.parent == directory and path.suffix == ".json")
    )


def check(directory: Path = EVIDENCE_DIRECTORY) -> list[str]:
    """Every capture-integrity violation in ``directory`` (empty when clean)."""
    documents, problems = _documents(directory)
    records, unresolved = collect_records(directory, documents)
    problems += unresolved + _unresolved_digest_fields(documents)
    digests: dict[str, tuple[str, int]] = {}
    for record in records:
        if not _safe_relative(record.path):
            problems.append(f"{record.recorded_by}: unsafe path {record.path!r}")
            continue
        path = directory / record.path
        if not path.is_file():
            problems.append(
                f"{record.path}: recorded by {record.recorded_by} but missing"
            )
            continue
        if record.path not in digests:
            body = path.read_bytes()
            digests[record.path] = (sha256(body), len(body))
        actual, size = digests[record.path]
        if record.sha256 != actual:
            problems.append(
                f"{record.path}: sha256 {actual} != {record.sha256} recorded by "
                f"{record.recorded_by}"
            )
        if record.bytes is not None and record.bytes != size:
            problems.append(
                f"{record.path}: {size} bytes != {record.bytes} recorded by "
                f"{record.recorded_by}"
            )
    recorded = {record.path for record in records}
    problems += [
        f"{path}: capture file recorded by no receipt or manifest"
        for path in capture_files(directory)
        if path not in recorded
    ]
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        default=EVIDENCE_DIRECTORY,
        help="boundary-evidence directory to check (default: the committed one)",
    )
    args = parser.parse_args()
    problems = check(args.evidence_directory)
    if problems:
        for problem in problems:
            print(f"tariff capture integrity: {problem}", file=sys.stderr)
        return 1
    captures = capture_files(args.evidence_directory)
    print(
        f"tariff capture integrity: {len(captures)} committed capture files match "
        "every recorded receipt/manifest digest"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
