#!/usr/bin/env python3
"""Receipt Yale's baseline treatment of Note 16(c)'s metal-weight gate.

This producer does not claim an observed transaction fact.  It binds the
campaign's boolean RuleSpec input to the pinned Yale reference model's explicit
zero-share baseline for articles below the 15-percent threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "reference/us-tariff-schedule/yale-note16-metal-weight-assumption.json"
)
DEFAULT_YALE_REPO = Path(
    "/Users/maxghenis/TheAxiomFoundation/_tariff-yale"
)
SCHEMA = "axiom_oracles.us_tariff_schedule.yale_note16_weight_assumption.v1"
YALE_COMMIT = "c4307e514196618afcbf88cf7fd33746417eeabf"
YALE_TREE = "d3107eae32ae7ac366b319abd4ab7b13c78d5c3c"
CAMPAIGN_INPUT = (
    "entry_has_at_least_fifteen_percent_aggregate_"
    "applicable_listed_metal_weight"
)
EXPECTED_SOURCE_SHA256 = {
    "config/policy_params.yaml": (
        "5f3d79b192b9fb6079e5ad10a1969e12f397567fc9f89d4e202403116ecb6346"
    ),
    "docs/assumptions.md": (
        "e2b65a9641895156c9e3fa1e06c05866e3cfdfb04075b26bee5117c0357f0dbf"
    ),
    "src/pipeline/06_calculate_rates.R": (
        "2620a122159c11cc2b116786925ccbc6d801cb274982034cd8105657ae13a76a"
    ),
}


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_bytes(repo: Path, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{YALE_COMMIT}:{path}"],
        check=True,
        capture_output=True,
    ).stdout


def _git_text(repo: Path, path: str) -> str:
    return _git_bytes(repo, path).decode()


def _file_receipt(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "bytes": len(data),
        "sha256": _sha256(data),
    }


def _source_receipt(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "bytes": len(data), "sha256": _sha256(data)}


def build_receipt(yale_repo: Path) -> dict[str, Any]:
    yale_repo = yale_repo.resolve()
    tree = subprocess.run(
        ["git", "-C", str(yale_repo), "rev-parse", f"{YALE_COMMIT}^{{tree}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tree != YALE_TREE:
        raise ValueError(f"pinned Yale tree drift: {tree}")

    source_bytes = {
        path: _git_bytes(yale_repo, path) for path in EXPECTED_SOURCE_SHA256
    }
    source_receipts = {
        path: _source_receipt(path, data)
        for path, data in sorted(source_bytes.items())
    }
    observed_hashes = {
        path: receipt["sha256"] for path, receipt in source_receipts.items()
    }
    if observed_hashes != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"pinned Yale source drift: {observed_hashes}")

    policy = yaml.safe_load(source_bytes["config/policy_params.yaml"])
    configured = policy["section_232_annexes"]["exemptions"][
        "de_minimis_weight"
    ]
    expected_configuration = {
        "threshold": 0.15,
        "applies_to": ["annex_1b", "annex_3"],
        "excludes_chapters": ["72", "73", "74", "76"],
        "aggregate_share": 0.0,
    }
    if configured != expected_configuration:
        raise ValueError(f"Yale de-minimis configuration drift: {configured}")

    assumptions = source_bytes["docs/assumptions.md"].decode()
    required_assumption_text = (
        "De minimis metal weight <15%",
        "all **dormant (0 / legacy) in the baseline**",
        "`rate_232 *= (1 - share)` on annex 1b/3 excluding primary chapters",
        "| 0.0 | ~0.02 |",
    )
    missing_assumption_text = [
        text for text in required_assumption_text if text not in assumptions
    ]
    if missing_assumption_text:
        raise ValueError(
            "Yale assumptions prose drift: " + repr(missing_assumption_text)
        )

    implementation = source_bytes["src/pipeline/06_calculate_rates.R"].decode()
    required_implementation_text = (
        "dmw_cfg <- annex_cfg$exemptions$de_minimis_weight",
        "dmw_share <- as.numeric(dmw_cfg$aggregate_share %||% 0)",
        "if (!is.na(dmw_share) && dmw_share > 0)",
        "rate_232 * (1 - dmw_share)",
    )
    missing_implementation_text = [
        text for text in required_implementation_text if text not in implementation
    ]
    if missing_implementation_text:
        raise ValueError(
            "Yale implementation semantics drift: "
            + repr(missing_implementation_text)
        )

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "producer": _file_receipt(Path(__file__).resolve()),
        "yale_source": {
            "commit": YALE_COMMIT,
            "tree": YALE_TREE,
            "files": source_receipts,
        },
        "configuration": expected_configuration,
        "model_implementation": {
            "below_threshold_route_is_share_scaled": True,
            "route_executes_only_when_aggregate_share_is_positive": True,
            "baseline_below_threshold_share": 0.0,
            "baseline_at_or_above_threshold_share": 1.0,
        },
        "campaign_binding": {
            "input": CAMPAIGN_INPUT,
            "value": True,
            "scope": (
                "RuleSpec Note 16(c)(vi)/(ix) candidate membership; the input "
                "has no effect outside those candidate branches"
            ),
            "interpretation": (
                "reproduce Yale's point-estimate baseline in which zero of the "
                "scoped import share is below the 15-percent threshold"
            ),
            "factual_status": (
                "reference-model assumption only; not an observed or inferred "
                "transaction-level metal-weight fact"
            ),
        },
    }
    receipt["receipt_payload_sha256"] = _sha256(_canonical_bytes(receipt))
    return receipt


def _render(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yale-repo", type=Path, default=DEFAULT_YALE_REPO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = _render(build_receipt(args.yale_repo))
    if args.check:
        if not args.output.is_file() or args.output.read_text() != rendered:
            raise SystemExit(f"drift: {args.output}")
        print(f"check OK: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
