#!/usr/bin/env python3
"""Package/replay both bounded tariff milestones with the real pinned Axiom CLI.

Offline verification uses only Python's standard library. Obtain the manifest
SHA-256 from the separate trusted handoff; the archive is not itself signed.
Reproducing a recorded counterexample does not establish legal correctness.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import tempfile

SCHEMA = "axiom_oracles.us_tariff_schedule.continuation_replay.v1"
ROOT = "reference/us-tariff-schedule/boundary-evidence/"
RECEIPTS = {
    "note2-exceptions": "build_us_tariff_boundary_evidence",
    "note52-transit-usmca": "build_us_tariff_note52_boundary_evidence",
    "hts-identity": "build_us_tariff_identity_evidence",
    "china-action": "build_us_tariff_china_action_evidence",
    "temporal-boundaries": "build_us_tariff_temporal_evidence",
    "china-lists": "build_us_tariff_china_list_evidence",
    "column2-resolution": "build_us_tariff_column2_evidence",
    "primary-metals": "build_us_tariff_metal_evidence",
}
ENGINE_SHA256 = "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
RULESPEC_REF = "4f591c4267063094cc6da9d590872ea982940b81"
MAX_FILE_BYTES = 40_000_000
MAX_TOTAL_BYTES = 200_000_000


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
    parts = PurePosixPath(relative).parts
    require(
        bool(parts)
        and not PurePosixPath(relative).is_absolute()
        and all(part not in ("..", ".") for part in parts)
        and "\\" not in relative
        and str(PurePosixPath(relative)) == relative,
        f"invalid bundle path: {relative}",
    )
    path = root
    for part in parts:
        path = path / part
        require(not path.is_symlink(), f"bundle symlink: {relative}")
    require(path.is_file(), f"not a regular bundle file: {relative}")
    require(path.stat().st_size < MAX_FILE_BYTES, f"oversized bundle file: {relative}")
    body = path.read_bytes()
    require(len(body) < MAX_FILE_BYTES, f"bundle file grew: {relative}")
    return body


def runs(evidence: dict):
    return evidence.get("runs", evidence.get("native_runs", []))


def checked_response(run: dict, result: subprocess.CompletedProcess) -> tuple[int, int]:
    """Return outputs/errors only when the exact recorded native outcome recurs."""
    if "returncode" in run:
        require(result.returncode == run["returncode"], "native return code mismatch")
        require(result.stdout.decode() == run["stdout"], "native stdout mismatch")
        require(result.stderr.decode() == run["stderr"], "native stderr mismatch")
    else:
        require(result.returncode == 0, "real runtime failed")
    if result.returncode:
        require(
            run["returncode"] == 1
            and run["response"] is None
            and run["response_sha256"] is None
            and not result.stdout
            and "missing input `resolved_non_ad_valorem_column2_rate`" in run["stderr"],
            "unexpected failure cannot count as a missing-input rejection",
        )
        return 0, 1
    response = json.loads(result.stdout)
    require(
        response == run["response"]
        and digest(canonical(response)) == run["response_sha256"],
        "real runtime response mismatch",
    )
    return sum(len(row["outputs"]) for row in response["results"]), 0


def validate_bindings(bodies: dict[str, bytes]) -> dict[str, dict]:
    require(
        digest(bodies["axiom-rules-engine"]) == ENGINE_SHA256, "runtime pin mismatch"
    )
    evidence_by_name = {}
    for name, producer in RECEIPTS.items():
        evidence = json.loads(bodies[ROOT + name + ".json"])
        require(
            all(
                evidence["claim"][k] is False
                for k in ("certified", "closed", "release_authorized")
            ),
            "uncertified labels changed",
        )
        require(
            evidence["engine_sha256"] == ENGINE_SHA256, "receipt runtime pin mismatch"
        )
        require(
            evidence["rulespec_ref"] == RULESPEC_REF, "receipt RuleSpec pin mismatch"
        )
        require(
            digest(bodies[f"scripts/{producer}.py"]) == evidence["producer_sha256"],
            "producer binding mismatch",
        )
        for field, script in (
            ("runtime_helper_sha256", "us_tariff_continuation_runtime"),
            ("native_runtime_helper_sha256", "us_tariff_raw_runtime"),
        ):
            if field in evidence:
                require(
                    digest(bodies[f"scripts/{script}.py"]) == evidence[field],
                    "helper binding mismatch",
                )
        for run in runs(evidence):
            require(
                digest(canonical(run["request"])) == run["request_sha256"],
                "request binding mismatch",
            )
            require(
                digest(bodies["compiled/" + run["compiled_sha256"] + ".json"])
                == run["compiled_sha256"],
                "compiled binding mismatch",
            )
            require(
                digest(bodies["rulespec-us/" + run["module"]["path"]])
                == run["module"]["sha256"],
                "module binding mismatch",
            )
        evidence_by_name[name] = evidence
    # The original receipt keeps its frozen corpus paths. Bind those same bytes
    # to the authenticated source copies included in this distinct bundle.
    old_source = evidence_by_name["note2-exceptions"]["source"]
    for key, name in (
        ("pdf", "chapter99.pdf"),
        ("notes", "provisions.jsonl"),
        ("ingest_manifest", "original-ingest-manifest.json"),
    ):
        require(
            digest(bodies[ROOT + "live-sources/" + name]) == old_source[key]["sha256"],
            "original source binding mismatch",
        )
    return evidence_by_name


def verify(root: Path, expected_manifest_sha256: str) -> dict:
    root = root.resolve()
    raw_manifest = bounded_file(root, "manifest.json")
    require(
        digest(raw_manifest) == expected_manifest_sha256,
        "manifest trust anchor mismatch",
    )
    manifest = json.loads(raw_manifest)
    require(manifest["schema"] == SCHEMA, "unsupported bundle schema")
    require(0 < len(manifest["files"]) < 200, "unexpected file population")
    bodies = {}
    total = 0
    for relative, expected in manifest["files"].items():
        require(
            type(expected["bytes"]) is int and 0 <= expected["bytes"] < MAX_FILE_BYTES,
            "invalid declared file size",
        )
        total += expected["bytes"]
        require(total < MAX_TOTAL_BYTES, "oversized bundle population")
        body = bounded_file(root, relative)
        require(
            len(body) == expected["bytes"] and digest(body) == expected["sha256"],
            f"bundle digest/size mismatch: {relative}",
        )
        bodies[relative] = body
    evidence = validate_bindings(bodies)
    require(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "pinned runtime requires macOS arm64",
    )
    counts = {}
    # Execute only bytes already verified and copied into a private directory.
    with tempfile.TemporaryDirectory(prefix="tariff-continuation-offline-") as raw:
        work = Path(raw)
        engine = work / "axiom-rules-engine"
        engine.write_bytes(bodies["axiom-rules-engine"])
        engine.chmod(0o700)
        env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(work), "LANG": "C"}
        for name, receipt in evidence.items():
            count = {"cases": 0, "outputs": 0, "native_missing_input_errors": 0}
            for run in runs(receipt):
                artifact = work / "compiled.json"
                artifact.write_bytes(
                    bodies["compiled/" + run["compiled_sha256"] + ".json"]
                )
                result = subprocess.run(
                    [str(engine), "run-compiled", "--artifact", str(artifact)],
                    input=canonical(run["request"]),
                    capture_output=True,
                    env=env,
                    timeout=60,
                )
                outputs, errors = checked_response(run, result)
                count["cases"] += len(run["request"]["queries"])
                count["outputs"] += outputs
                count["native_missing_input_errors"] += errors
            counts[name] = count
    totals = {
        k: sum(c[k] for c in counts.values()) for k in next(iter(counts.values()))
    }
    require(
        totals == {"cases": 843, "outputs": 1817, "native_missing_input_errors": 12},
        "bounded population drift",
    )
    return {
        "manifest_sha256": expected_manifest_sha256,
        "by_receipt": counts,
        "totals": totals,
        "closed": False,
        "certified": False,
        "network_required": False,
        "legal_correctness_inferred": False,
        "actual_entry_grounding": "uncaptured",
    }


def build(destination: Path) -> dict:
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from scripts import us_tariff_raw_runtime as runtime

    files = {
        "verify.py": Path(__file__).read_bytes(),
        "axiom-rules-engine": runtime.original.closure.INPUT_INVENTORY_ENGINE.read_bytes(),
    }
    for name, producer in RECEIPTS.items():
        for relative in (ROOT + name + ".json", f"scripts/{producer}.py"):
            files[relative] = (repo / relative).read_bytes()
    for name in (
        "us_tariff_continuation_runtime",
        "us_tariff_raw_runtime",
        "us_tariff_live_source_evidence",
    ):
        relative = f"scripts/{name}.py"
        files[relative] = (repo / relative).read_bytes()
    source_dirs = [
        ROOT + name
        for name in (
            "live-sources",
            "identity-sources",
            "china-action-sources",
            "temporal-sources",
            "column2-sources",
        )
    ]
    sources = (
        subprocess.check_output(
            ["git", "-C", str(repo), "ls-files", "-z", "--", *source_dirs]
        )
        .decode()
        .split("\0")
    )
    for relative in filter(None, sources):
        files[relative] = (repo / relative).read_bytes()
    receipts = [json.loads(files[ROOT + name + ".json"]) for name in RECEIPTS]
    modules = sorted(
        {run["module"]["path"] for receipt in receipts for run in runs(receipt)}
    )
    with runtime.compiled(modules) as invoke:
        for module, program in invoke.programs.items():
            compiled = program["compiled_bytes"]
            files["compiled/" + digest(compiled) + ".json"] = compiled
            files["rulespec-us/" + module] = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(runtime.original.closure.RULESPEC),
                    "show",
                    RULESPEC_REF + ":" + module,
                ]
            )
    files["README.md"] = b"""# Combined bounded tariff replay

Obtain the trusted manifest SHA-256 from the separately committed continuation
replay manifest. Requires macOS arm64 and Python 3.10+, no site packages.
Run: python3 -I -S verify.py --verify-bundle . --manifest-sha256 TRUSTED_SHA256

The real pinned Axiom engine replays 843 synthetic/diagnostic cases, 1817
returned outputs and 12 intentional native missing-input errors. This includes
the original 384 cases/768 outputs without modifying their frozen receipt.
Known legal counterexamples and raw-identity differences must reproduce exactly;
a passing replay does not establish legal correctness or real-entry eligibility.

Included source PDFs, HTTP metadata, original ingest signature, actual public
trust root and pinned canonical verifier are source evidence. The live receipt
records performed Ed25519 verification. This standard-library replay checks
their bytes; it does not independently perform Ed25519 or GPO PDF signature
verification. No new signature is claimed. The separately trusted manifest
authenticates this package only to the extent its trust anchor is trusted.

Compiled programs were freshly built from pinned RuleSpec Git objects and
matched to every receipt. Root YAMLs and producer scripts are review material;
this package does not include all imports for full source recompilation or
execute the adapter/PDF extraction producers. Use the Git branch and producer
--check commands for that separate validation. No campaign cache is required.

All 58 actual-entry groundings remain uncaptured. closed=false/certified=false.
Current-base admission, source/runtime repairs and required Fable review remain
open. No release, activation, publication or legal certification is authorized.
"""
    validate_bindings(files)
    manifest = {
        "schema": SCHEMA,
        "producer_ref": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"]
        )
        .decode()
        .strip(),
        "runtime_platform": "macOS arm64",
        "rulespec_ref": RULESPEC_REF,
        "files": {
            name: {"sha256": digest(body), "bytes": len(body)}
            for name, body in sorted(files.items())
        },
    }
    files["manifest.json"] = render(manifest)
    with tempfile.TemporaryDirectory(prefix="tariff-continuation-package-") as raw:
        bundle = Path(raw)
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
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"tariff continuation replay failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
