#!/usr/bin/env python3
"""Build or verify a bounded, portable tariff replay using the real Axiom runtime.

Verification needs only Python's standard library and the included macOS arm64
executable. The trusted manifest SHA-256 must come from the separate handoff,
not from the untrusted bundle. No campaign cache or network is used.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile

SCHEMA = "axiom_oracles.us_tariff_schedule.offline_boundary_replay.v1"
FILES = frozenset(
    {
        "verify.py",
        "README.md",
        "axiom-rules-engine",
        "evidence.json",
        "sources/chapter-99.pdf",
        "sources/provisions.jsonl",
        "sources/ingest-manifest.json",
        "runs/0.compiled.json",
        "runs/1.compiled.json",
        "runs/0.request.json",
        "runs/1.request.json",
    }
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def render(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def bounded_file(root: Path, relative: str) -> bytes:
    path = root / relative
    require(
        path.resolve().is_relative_to(root.resolve())
        and not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent),
        f"bundle path escaped or is a symlink: {relative}",
    )
    require(
        path.stat().st_size < 20_000_000, f"unexpected large bundle file: {relative}"
    )
    return path.read_bytes()


def verify(root: Path, expected_manifest_sha256: str) -> dict:
    root = root.resolve()
    raw_manifest = bounded_file(root, "manifest.json")
    require(
        digest(raw_manifest) == expected_manifest_sha256,
        "manifest trust anchor mismatch",
    )
    manifest = json.loads(raw_manifest)
    require(manifest["schema"] == SCHEMA, "unsupported bundle schema")
    require(set(manifest["files"]) == FILES, "bundle file population drift")
    bodies = {}
    for relative in sorted(FILES):
        body = bounded_file(root, relative)
        expected = manifest["files"][relative]
        require(
            len(body) == expected["bytes"] and digest(body) == expected["sha256"],
            f"bundle file digest/size mismatch: {relative}",
        )
        bodies[relative] = body
    evidence = json.loads(bodies["evidence.json"])
    require(
        evidence["claim"]["certified"] is False
        and evidence["claim"]["closed"] is False
        and evidence["claim"]["actual_entry_grounding"] == "uncaptured",
        "bundle must preserve uncertified labels",
    )
    require(len(evidence["runs"]) == 2, "runtime run population drift")
    require(
        digest(bodies["axiom-rules-engine"]) == evidence["engine_sha256"],
        "runtime evidence binding mismatch",
    )
    for name, key in (
        ("chapter-99.pdf", "pdf"),
        ("provisions.jsonl", "notes"),
        ("ingest-manifest.json", "ingest_manifest"),
    ):
        require(
            digest(bodies["sources/" + name]) == evidence["source"][key]["sha256"],
            f"source evidence binding mismatch: {name}",
        )
    require(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "the pinned runtime requires macOS arm64; do not substitute another engine",
    )
    checked = 0
    # Copy verified inputs into a private directory so concurrent replacement
    # of the bundle cannot change the executable or compiled programs in flight.
    with tempfile.TemporaryDirectory(prefix="tariff-offline-replay-") as raw:
        work = Path(raw)
        engine = work / "axiom-rules-engine"
        engine.write_bytes(bodies["axiom-rules-engine"])
        engine.chmod(0o700)
        for index, run in enumerate(evidence["runs"]):
            compiled = bodies[f"runs/{index}.compiled.json"]
            request = bodies[f"runs/{index}.request.json"]
            require(
                digest(compiled) == run["compiled_sha256"],
                "compiled evidence binding mismatch",
            )
            require(
                digest(request) == run["request_sha256"]
                and json.loads(request) == run["request"],
                "request evidence binding mismatch",
            )
            artifact = work / "compiled.json"
            artifact.write_bytes(compiled)
            result = subprocess.run(
                [str(engine), "run-compiled", "--artifact", str(artifact)],
                input=request,
                capture_output=True,
                check=True,
            )
            response = json.loads(result.stdout)
            require(
                digest(canonical(response)) == run["response_sha256"]
                and response == run["response"],
                f"real runtime response mismatch: module {index}",
            )
            checked += sum(len(row["outputs"]) for row in response["results"])
    require(checked == 768, "checked output population drift")
    return {
        "manifest_sha256": expected_manifest_sha256,
        "checked_outputs": checked,
        "cases": 384,
        "certified": False,
        "network_required": False,
    }


def build(destination: Path) -> dict:
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from scripts import build_us_tariff_boundary_evidence as boundary

    evidence_bytes = boundary.OUTPUT.read_bytes()
    evidence = json.loads(evidence_bytes)
    require(
        evidence["producer_sha256"] == digest(Path(boundary.__file__).read_bytes()),
        "boundary producer changed since evidence generation",
    )
    source = boundary.source_evidence(boundary.closure.CORPUS)
    require(source == evidence["source"], "source receipt drift")
    engine_bytes = boundary.closure.INPUT_INVENTORY_ENGINE.read_bytes()
    require(digest(engine_bytes) == evidence["engine_sha256"], "engine pin mismatch")
    files = {
        "verify.py": Path(__file__).read_bytes(),
        "evidence.json": evidence_bytes,
        "axiom-rules-engine": engine_bytes,
        "README.md": b"# Bounded tariff replay\n\nObtain the trusted manifest SHA-256 from the separately committed offline-replay-manifest.json.\nRun: python3 verify.py --verify-bundle . --manifest-sha256 TRUSTED_SHA256\n\nRequires macOS arm64 and Python 3.10+. The included real Axiom engine runs\n384 synthetic cases / 768 outputs without network, repository checkouts,\nPython packages or campaign caches. Source PDFs, provisions and original\ningest manifest are included. The ingest signature has NOT been independently\nverified against a trusted public key. This bundle preserves closed=false,\ncertified=false and all actual-entry groundings uncaptured.\n\nIt replays compiled programs whose hashes match the source-linked receipt.\nRecompiling from RuleSpec Git objects is a separate existing producer check.\nFinal Fable review and the existing release gates remain required.\n",
    }
    for name, path in (
        ("chapter-99.pdf", boundary.PDF),
        ("provisions.jsonl", boundary.closure.NOTES),
        ("ingest-manifest.json", boundary.INGEST),
    ):
        files["sources/" + name] = boundary.git_bytes(
            boundary.closure.CORPUS, boundary.closure.CORPUS_REF, path
        )
    with tempfile.TemporaryDirectory(prefix="tariff-replay-package-") as raw:
        work = Path(raw)
        engine = work / "axiom-rules-engine"
        engine.write_bytes(engine_bytes)
        engine.chmod(0o700)
        archive = subprocess.check_output(
            [
                "git",
                "-C",
                str(boundary.closure.RULESPEC),
                "archive",
                boundary.closure.RULESPEC_REF,
                "us",
                "programs",
            ]
        )
        snapshot = work / "rulespec-us"
        snapshot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(snapshot, filter="data")
        env = dict(os.environ)
        env.pop("AXIOM_RULESPEC_ROOT", None)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(work)
        for index, run in enumerate(evidence["runs"]):
            artifact = work / "compiled.json"
            artifact.unlink(missing_ok=True)
            subprocess.run(
                [
                    str(engine),
                    "compile",
                    "--program",
                    str(snapshot / run["module"]["path"]),
                    "--output",
                    str(artifact),
                ],
                capture_output=True,
                check=True,
                env=env,
            )
            compiled = artifact.read_bytes()
            require(
                digest(compiled) == run["compiled_sha256"],
                "fresh compilation differs from receipt",
            )
            files[f"runs/{index}.compiled.json"] = compiled
            files[f"runs/{index}.request.json"] = canonical(run["request"])
        require(set(files) == FILES, "incomplete package")
        manifest = {
            "schema": SCHEMA,
            "files": {
                name: {"sha256": digest(body), "bytes": len(body)}
                for name, body in sorted(files.items())
            },
            "rulespec_ref": evidence["rulespec_ref"],
            "corpus_ref": evidence["source"]["ref"],
            "runtime_platform": "macOS arm64",
            "claims": evidence["claim"],
        }
        files["manifest.json"] = render(manifest)
        bundle = work / "bundle"
        bundle.mkdir()
        for relative, body in files.items():
            path = bundle / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        verification = verify(bundle, digest(files["manifest.json"]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("wb") as output:
            with gzip.GzipFile(
                fileobj=output, mode="wb", filename="", mtime=0
            ) as zipped:
                with tarfile.open(fileobj=zipped, mode="w") as tar:
                    for relative, body in sorted(files.items()):
                        info = tarfile.TarInfo(relative)
                        info.size = len(body)
                        info.mode = 0o755 if relative == "axiom-rules-engine" else 0o644
                        tar.addfile(info, io.BytesIO(body))
        temporary.replace(destination)
    return {
        "schema": SCHEMA,
        "bundle_sha256": digest(destination.read_bytes()),
        "bundle_bytes": destination.stat().st_size,
        "manifest": manifest,
        "verification": verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", type=Path)
    mode.add_argument("--verify-bundle", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.build:
            require(args.receipt is not None, "--receipt is required for a build")
            result = build(args.build)
            args.receipt.write_bytes(render(result))
        else:
            require(bool(args.manifest_sha256), "trusted --manifest-sha256 is required")
            result = verify(args.verify_bundle, args.manifest_sha256)
        print(json.dumps(result.get("verification", result), sort_keys=True))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"tariff replay bundle failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
