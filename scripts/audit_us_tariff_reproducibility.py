#!/usr/bin/env python3
"""Audit tariff receipt file bindings without decompressing campaign data.

Only files of at most 20 MB are hashed. Larger files receive an explicit
presence/size-only result; that is never represented as verified content.
Relative paths are assigned to their declared project, not searched globally.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROOFS = tuple(
    "reference/us-tariff-schedule/" + name
    for name in (
        "cafta-reference-defect-supersession-receipt.json",
        "steel-scope-projection-receipt.json",
        "remaining-residual-receipt.json",
        "preview-selector-transition-receipt.json",
    )
)
MAX_HASH_BYTES = 20_000_000
HISTORICAL_PATH = (
    "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
)
HISTORICAL_SHA256 = "d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705"


def bindings(value: object, pointer: str = ""):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            yield pointer, value
        for key, child in value.items():
            yield from bindings(child, pointer + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from bindings(child, pointer + "/" + str(index))


def root_for(path: str, *, repo: Path, rulespec: Path, yale: Path) -> tuple[str, Path]:
    if Path(path).is_absolute():
        return "external", Path(path)
    if path.startswith("us/") or path == "tools/b16_entry_flags.py":
        return "rulespec-us", rulespec / path
    if (
        path.startswith(("config/", "src/", "resources/", "data/hts_archives/"))
        or path == "scripts/parse_annex_products.R"
    ):
        return "yale", yale / path
    return "axiom-oracles", repo / path


def inspect_file(path: Path, expected: dict) -> dict:
    if not path.is_file():
        return {"status": "missing"}
    size = path.stat().st_size
    if "bytes" in expected and size != expected["bytes"]:
        return {"status": "size_mismatch", "actual_bytes": size}
    if size > MAX_HASH_BYTES:
        return {"status": "present_not_rehashed_large", "actual_bytes": size}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "status": "sha256_match" if digest == expected["sha256"] else "sha256_mismatch",
        "actual_bytes": size,
        "actual_sha256": digest,
    }


def audit(
    *, repo: Path, rulespec: Path, yale: Path, historical_source: Path | None = None
) -> dict:
    expected = {}
    proof_rows = []
    for relative in PROOFS:
        raw = (repo / relative).read_bytes()
        proof_rows.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
        for pointer, receipt in bindings(json.loads(raw)):
            key = (receipt["path"], receipt["sha256"])
            row = expected.setdefault(
                key,
                {
                    "path": receipt["path"],
                    "sha256": receipt["sha256"],
                    "references": [],
                },
            )
            if "bytes" in receipt:
                if "bytes" in row and row["bytes"] != receipt["bytes"]:
                    raise ValueError(f"conflicting byte counts for {receipt['path']}")
                row["bytes"] = receipt["bytes"]
            row["references"].append({"proof": relative, "pointer": pointer})
    rows = []
    for _, receipt in sorted(expected.items()):
        namespace, path = root_for(
            receipt["path"], repo=repo, rulespec=rulespec, yale=yale
        )
        result = inspect_file(path, receipt)
        row = {**receipt, "namespace": namespace, "resolved_path": str(path), **result}
        if receipt["path"] == HISTORICAL_PATH and historical_source is not None:
            row["recovery_copy"] = {
                "path": str(historical_source),
                **inspect_file(historical_source, receipt),
            }
        rows.append(row)
    counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    return {
        "schema": "axiom_oracles.us_tariff_schedule.reproducibility_inventory.v1",
        "proofs": proof_rows,
        "max_hashed_file_bytes": MAX_HASH_BYTES,
        "method": "Read small bound files; stat larger files. No decompression, campaign scan or engine execution.",
        "roots": {
            "axiom-oracles": str(repo),
            "rulespec-us": str(rulespec),
            "yale": str(yale),
        },
        "binding_count": len(rows),
        "counts": counts,
        "bindings": rows,
        "full_reproduction_verified": False,
        "remaining_requirements": [
            "Large campaign artifacts retain prior verified digests; this audit does not rehash or replay them.",
            (
                "The relative historical artifact is restored and hash-matches its preserved proof binding."
                if any(
                    row["path"] == HISTORICAL_PATH and row["status"] == "sha256_match"
                    for row in rows
                )
                else "The relative historical artifact must be restored from its exact hash-matching copy before full replay."
            ),
            "Source closure, trusted ingest-signature verification and final Fable release review remain separate gates.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--yale-root", type=Path, required=True)
    parser.add_argument("--historical-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        repo=args.repo_root,
        rulespec=args.rulespec_root,
        yale=args.yale_root,
        historical_source=args.historical_source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))
    # Inventory gaps are useful output, but never a green reproduction check.
    return int(
        any(
            row["status"] in {"missing", "size_mismatch", "sha256_mismatch"}
            for row in result["bindings"]
        )
    )


if __name__ == "__main__":
    sys.exit(main())
