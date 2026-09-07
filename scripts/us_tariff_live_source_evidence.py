#!/usr/bin/env python3
"""Authenticate bounded live USITC downloads and the original corpus signature.

This is an unsigned evidence receipt, not a corpus ingest or release certificate.
Use --capture-from on curl downloads with .headers/.curl.json sidecars; --check
reproduces all integrity and Ed25519 checks offline from the committed files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_us_tariff_boundary_evidence as boundary  # noqa: E402

DIRECTORY = ROOT / "reference/us-tariff-schedule/boundary-evidence/live-sources"
RECEIPT = DIRECTORY / "receipt.json"
GN11_URL = "https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=General%20Note%2011"
GN11_SHA256 = "db7ec89a2ef6232c54045e3498b40c494db1b8162a8f8c8e971e4753beaffef3"
KEY_API = "https://api.github.com/repos/TheAxiomFoundation/axiom-corpus/actions/variables/AXIOM_CORPUS_INGEST_PUBLIC_KEY"
KEY_SHA256 = "9b3f3cdbad4e6523ccd114d1649f57a351d05ea117fa77cb0a6184e92ce50f17"
VERIFIER_PATH = "src/axiom_corpus/corpus/ingest_manifests.py"
VERIFIER_SHA256 = "84e08c6d4847a4f049216a654977e6a370074c17592c326546739eb0e5cdce8d"
MANIFEST_SHA256 = "2811c6a36f05dbafbf3b3b1b23b42470377ce6d3e53e3f4e5a865c08dd2f21f7"
DOWNLOADS = {
    "chapter99": (boundary.SOURCE_URL, boundary.PDF_SHA256),
    "general-note11": (GN11_URL, GN11_SHA256),
}


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def render(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()


def bound(path: Path) -> dict:
    body = path.read_bytes()
    return {"file": path.name, "bytes": len(body), "sha256": sha(body)}


def verify_signature(directory: Path, corpus: Path) -> dict:
    key_record = json.loads((directory / "corpus-ingest-public-key.json").read_bytes())
    require(
        key_record["name"] == "AXIOM_CORPUS_INGEST_PUBLIC_KEY",
        "wrong trust-root variable",
    )
    key = key_record["value"]
    require(sha(key.encode()) == KEY_SHA256, "trusted public-key digest changed")
    code = (directory / "ingest_manifests.py").read_bytes()
    require(sha(code) == VERIFIER_SHA256, "canonical corpus verifier changed")
    raw = (directory / "original-ingest-manifest.json").read_bytes()
    require(sha(raw) == MANIFEST_SHA256, "original ingest manifest changed")
    with tempfile.TemporaryDirectory(prefix="tariff-ingest-auth-") as temporary:
        file = Path(temporary) / "ingest_manifests.py"
        file.write_bytes(code)
        spec = importlib.util.spec_from_file_location("tariff_ingest_verifier", file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        issues = module.verify_ingest_manifest(
            json.loads(raw),
            public_key=key,
            repo=corpus,
            head_ref=boundary.closure.CORPUS_REF,
        )
    require(
        not issues,
        "canonical ingest-signature verification failed: " + "; ".join(issues),
    )
    applied = {row["path"]: row["sha256"] for row in json.loads(raw)["applied_files"]}
    require(
        applied[boundary.PDF] == sha((directory / "chapter99.pdf").read_bytes())
        and applied[boundary.closure.NOTES]
        == sha((directory / "provisions.jsonl").read_bytes()),
        "signed applied-file bindings changed",
    )
    return {
        "verified": True,
        "algorithm": "ed25519",
        "issues": [],
        "trusted_key_sha256": KEY_SHA256,
        "trust_root_api": KEY_API,
        "trust_root_updated_at": key_record["updated_at"],
        "canonical_verifier_sha256": VERIFIER_SHA256,
        "canonical_verifier_corpus_ref": boundary.closure.CORPUS_REF,
        "manifest_sha256": MANIFEST_SHA256,
        "applied_pdf_and_provision_hashes_match": True,
    }


def build(directory: Path, corpus: Path) -> dict:
    records = []
    retrievals = json.loads((directory / "retrieval-times.json").read_bytes())
    for stem, (url, expected_sha) in DOWNLOADS.items():
        pdf = directory / (stem + ".pdf")
        body = pdf.read_bytes()
        require(
            body.startswith(b"%PDF-") and sha(body) == expected_sha,
            "pinned live PDF mismatch: " + stem,
        )
        curl = json.loads((directory / (stem + ".curl.json")).read_bytes())
        require(
            curl["http_code"] == 200
            and curl["url_effective"] == url
            and curl["ssl_verify_result"] == 0,
            "live HTTPS retrieval metadata mismatch: " + stem,
        )
        records.append(
            {
                "authoritative_url": url,
                "retrieved_at": retrievals[stem],
                "http_status": 200,
                "tls_verification_result": 0,
                "pdf": bound(pdf),
                "headers": bound(directory / (stem + ".headers")),
                "curl_metadata": bound(directory / (stem + ".curl.json")),
            }
        )
    notes = directory / "provisions.jsonl"
    require(
        sha(notes.read_bytes()) == boundary.closure.NOTES_SHA256,
        "pinned provisions mismatch",
    )
    signature = verify_signature(directory, corpus)
    return {
        "schema": "axiom_oracles.us_tariff_schedule.live_source_evidence.v1",
        "downloads": records,
        "http_metadata": "Set-Cookie omitted; header whitespace normalized; curl fields allowlisted. Raw HTTP metadata retained in the private lane artifact directory.",
        "provisions": bound(notes),
        "signature_verification": signature,
        "trust_root_snapshot": bound(directory / "corpus-ingest-public-key.json"),
        "trust_root_retrieved_at": retrievals["corpus-ingest-public-key"],
        "chapter99_matches_original_frozen_pdf": True,
        "general_note11_status": "raw authoritative PDF capture; not ingested or signed by this sprint",
        "claim": {"closed": False, "certified": False, "release_authorized": False},
        "limitations": [
            "HTTP retrieval metadata is an unsigned receipt, not a newly created cryptographic signature.",
            "The existing corpus signature authenticates the original Chapter99 ingest only; GeneralNote11 remains an unsigned direct-source capture.",
            "A source snapshot and authentic signature do not establish real-entry facts, historical coverage or source completeness.",
        ],
    }


def public_http_metadata(source: Path) -> bytes:
    if source.name.endswith(".headers"):
        return (
            "\n".join(
                line.rstrip()
                for line in source.read_text().splitlines()
                if line.strip() and not line.lower().startswith("set-cookie:")
            )
            + "\n"
        ).encode()
    if source.name.endswith(".curl.json"):
        record = json.loads(source.read_bytes())
        fields = (
            "http_code",
            "url_effective",
            "ssl_verify_result",
            "content_type",
            "http_version",
            "method",
            "size_download",
            "num_redirects",
            "time_total",
            "curl_version",
            "exitcode",
        )
        return render({key: record[key] for key in fields})
    return source.read_bytes()


def capture(downloads: Path, directory: Path, corpus: Path) -> None:
    require(
        not (directory / "retrieval-times.json").exists(),
        "refuse to replace an existing live capture",
    )
    directory.mkdir(parents=True, exist_ok=True)
    times = {}
    for stem in DOWNLOADS:
        for suffix in (".pdf", ".headers", ".curl.json"):
            source = downloads / (stem + suffix)
            (directory / source.name).write_bytes(public_http_metadata(source))
        times[stem] = datetime.fromtimestamp(
            (downloads / (stem + ".pdf")).stat().st_mtime, timezone.utc
        ).isoformat()
    key = downloads / "corpus-ingest-public-key.json"
    (directory / key.name).write_bytes(key.read_bytes())
    times["corpus-ingest-public-key"] = datetime.fromtimestamp(
        key.stat().st_mtime, timezone.utc
    ).isoformat()
    (directory / "retrieval-times.json").write_bytes(render(times))
    for name, path in (
        ("original-ingest-manifest.json", boundary.INGEST),
        ("ingest_manifests.py", VERIFIER_PATH),
        ("provisions.jsonl", boundary.closure.NOTES),
    ):
        (directory / name).write_bytes(
            boundary.git_bytes(corpus, boundary.closure.CORPUS_REF, path)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture-from", type=Path)
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--directory", type=Path, default=DIRECTORY)
    parser.add_argument("--corpus-root", type=Path, default=boundary.closure.CORPUS)
    args = parser.parse_args()
    try:
        if args.capture_from:
            capture(args.capture_from, args.directory, args.corpus_root)
        result = build(args.directory, args.corpus_root)
        receipt = args.directory / "receipt.json"
        if args.check:
            require(
                receipt.read_bytes() == render(result), "live evidence receipt drift"
            )
        else:
            receipt.write_bytes(render(result))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"live source evidence failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Two live USITC PDFs verified; original Chapter99 Ed25519 signature verified against the authenticated repository trust root; certified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
