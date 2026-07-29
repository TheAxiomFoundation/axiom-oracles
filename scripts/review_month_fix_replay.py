"""Replay a month-scoped suite and compare its dashboard artifact byte-for-byte."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


REVIEW_ROOT = Path(__file__).resolve().parents[1]
CLEAN_RULESPEC_US = Path("/private/tmp/month-fix-regen-root/rulespec-us")
SYNCED_RULESPEC_US = Path("/Users/maxghenis/.axiom-oracles/roots/rulespec-us")
AXIOM_RULES_REPO = Path("/Users/maxghenis/axiom-rules-engine")
OUTPUT_ROOT = Path("/private/tmp/month-fix-review-replays")
SUITES = ("ca-snap-ecps", "ks-tanf-ecps", "ssi-ecps")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def differences(left: Any, right: Any, prefix: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [f"{prefix}: type {type(left).__name__} != {type(right).__name__}"]
    if isinstance(left, dict):
        rows: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}"
            if key not in left:
                rows.append(f"{child}: missing from replay")
            elif key not in right:
                rows.append(f"{child}: extra in replay")
            else:
                rows.extend(differences(left[key], right[key], child))
            if len(rows) >= 100:
                return rows[:100]
        return rows
    if isinstance(left, list):
        if len(left) != len(right):
            return [f"{prefix}: length {len(left)} != {len(right)}"]
        rows = []
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            rows.extend(differences(left_item, right_item, f"{prefix}[{index}]"))
            if len(rows) >= 100:
                return rows[:100]
        return rows
    if left != right:
        return [f"{prefix}: replay={left!r} committed={right!r}"]
    return []


def configure_paths(config: dict, suite: str) -> None:
    runner = config["runner"]
    params = runner["parameters"]
    runner["axiom_rules_repo"] = str(AXIOM_RULES_REPO)
    suite_dir = OUTPUT_ROOT / suite
    params["axiom_composed_program"] = str(suite_dir / "composed.yaml")
    params["axiom_compiled_program"] = str(suite_dir / "compiled.json")
    if suite == "ca-snap-ecps":
        params["axiom_program"] = str(
            CLEAN_RULESPEC_US / "programs/us-ca/snap/fy-2026.yaml"
        )
        params["rulespec_roots"] = [str(CLEAN_RULESPEC_US)]
        params["axiom_rulespec_repo_roots"] = str(CLEAN_RULESPEC_US.parent)
    elif suite == "ks-tanf-ecps":
        params["axiom_program"] = str(
            REVIEW_ROOT / "programs/us-ks/tanf/fy-2026.yaml"
        )
        params["rulespec_roots"] = [str(CLEAN_RULESPEC_US)]
        params["axiom_rulespec_repo_roots"] = str(CLEAN_RULESPEC_US)
    elif suite == "ssi-ecps":
        params["axiom_program"] = str(REVIEW_ROOT / "programs/us/ssi/fy-2026.yaml")
        params["rulespec_roots"] = [str(SYNCED_RULESPEC_US)]
        params["axiom_rulespec_repo_roots"] = str(SYNCED_RULESPEC_US.parent)
    else:
        raise ValueError(suite)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=SUITES)
    args = parser.parse_args()

    os.chdir(REVIEW_ROOT)
    sys.path.insert(0, str(REVIEW_ROOT))
    from axiom_oracles.comparison.report import strip_heavy_case_metadata
    from scripts import run_comparison

    suite = args.suite
    config = copy.deepcopy(run_comparison._load_comparison(suite))
    configure_paths(config, suite)
    runner_type = config["runner"]["type"]
    output_dir = OUTPUT_ROOT / suite
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "full-report.json"
    candidate_path = output_dir / "dashboard-candidate.json"
    expected_path = (
        REVIEW_ROOT
        / "dashboard/public/data"
        / f"axiom-policyengine-{suite}.json"
    )

    run_comparison.RUNNERS[runner_type](config["runner"], raw_path)
    provenance = run_comparison._build_run_provenance(
        config,
        runner_type,
        raw_path,
    )
    expected = json.loads(expected_path.read_text())
    expected_provenance = expected["provenance"]
    replay_provenance_without_time = {
        key: value for key, value in provenance.items() if key != "generated_at"
    }
    expected_provenance_without_time = {
        key: value
        for key, value in expected_provenance.items()
        if key != "generated_at"
    }
    provenance_without_time_parity = (
        replay_provenance_without_time == expected_provenance_without_time
    )
    provenance["generated_at"] = expected_provenance["generated_at"]
    run_comparison._stamp_report_provenance(
        raw_path,
        provenance,
        require_engine_versions=True,
    )
    dashboard = run_comparison._adapt_to_v2(
        raw_path,
        runner_type,
        config,
        suite=suite,
    )
    dashboard["provenance"] = provenance
    dashboard = run_comparison._merge_dispositions(dashboard)
    dashboard = run_comparison._slim_report_for_dashboard(
        strip_heavy_case_metadata(dashboard)
    )
    candidate_path.write_text(json.dumps(dashboard, indent=2, sort_keys=True))

    replay = json.loads(candidate_path.read_text())
    delta = differences(replay, expected)
    raw = json.loads(raw_path.read_text())
    receipt = {
        "suite": suite,
        "stack": raw.get("engines", {}).get("versions"),
        "case_count": raw.get("case_count"),
        "mismatch_count": raw.get("summary", {}).get("mismatch_count"),
        "provenance_without_generated_at_parity": provenance_without_time_parity,
        "committed_generated_at_reused_for_byte_comparison": expected_provenance[
            "generated_at"
        ],
        "candidate_sha256": sha256(candidate_path),
        "committed_sha256": sha256(expected_path),
        "byte_parity": candidate_path.read_bytes() == expected_path.read_bytes(),
        "json_difference_count_capped": len(delta),
        "first_json_differences": delta[:20],
        "raw_report": str(raw_path),
        "candidate": str(candidate_path),
        "committed": str(expected_path),
    }
    receipt_path = output_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["byte_parity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
