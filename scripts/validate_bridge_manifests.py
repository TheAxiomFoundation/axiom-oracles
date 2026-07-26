#!/usr/bin/env python3
"""Validate bridge manifests — the declared experiment design per suite.

A bridge manifest (``axiom_oracles/bridges/manifests/*.yaml``) declares what a
comparison harness feeds the program under test: mapped, projected, bridged,
or constant, per input. This validator keeps the declarations honest:

* schema and binding-kind checks; every binding is exactly one kind and no
  input name is bound twice;
* the suite (or an alias) must have a committed report — a manifest for a
  comparison that doesn't exist certifies nothing;
* population pinning: when ``pin_required`` is true and the committed report
  carries no dataset identity, that is a finding (charter #374, increment 3);
* audit debt: ``audit: partial`` entries are counted and printed — a partial
  entry is a to-do, not a certification.

Findings are printed always; ``--strict`` turns them into a nonzero exit for
CI once the lanes have had a chance to stamp their populations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO_ROOT / "axiom_oracles" / "bridges" / "manifests"
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"

SCHEMA = "axiom_oracles.bridge_manifest.v1"
KINDS = {"mapped", "projected", "bridged", "constant"}


def load_manifests() -> dict[Path, dict]:
    return {
        path: yaml.safe_load(path.read_text())
        for path in sorted(MANIFEST_DIR.glob("*.yaml"))
    }


def _report_for(suite_names: list[str]) -> tuple[str | None, dict | None]:
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("suite") in suite_names:
            return str(path.relative_to(REPO_ROOT)), payload
    return None, None


def validate(path: Path, manifest: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    findings: list[str] = []
    name = path.name

    if manifest.get("schema") != SCHEMA:
        errors.append(f"{name}: schema must be {SCHEMA}")
        return errors, findings
    for field in ("suite", "program", "bindings", "population", "oracle"):
        if field not in manifest:
            errors.append(f"{name}: missing required field `{field}`")
    if errors:
        return errors, findings

    bindings = manifest["bindings"]
    if not isinstance(bindings, list) or not bindings:
        errors.append(f"{name}: bindings must be a non-empty list")
        return errors, findings
    seen_inputs: set[str] = set()
    partial = 0
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            errors.append(f"{name}: bindings[{index}] is not a mapping")
            continue
        kind = binding.get("kind")
        if kind not in KINDS:
            errors.append(f"{name}: bindings[{index}] kind `{kind}` not in {sorted(KINDS)}")
            continue
        if binding.get("audit") not in ("read", "partial"):
            errors.append(f"{name}: bindings[{index}] audit must be read|partial")
        if binding.get("audit") == "partial":
            partial += 1
        named = binding.get("inputs") or (
            [binding["input"]] if binding.get("input") else []
        )
        # A bridged binding may declare at dimension level: the receiving
        # inputs are enumerable audit debt, the dimension is the claim.
        if not named and not binding.get("group") and not (
            kind == "bridged" and binding.get("dimension")
        ):
            errors.append(
                f"{name}: bindings[{index}] names neither `input(s)`, `group`, "
                "nor (for bridged) `dimension`"
            )
        for input_name in named:
            if input_name in seen_inputs:
                errors.append(f"{name}: input `{input_name}` bound more than once")
            seen_inputs.add(input_name)
        if kind == "bridged":
            covered_by = binding.get("covered_by")
            if not isinstance(covered_by, list) or not covered_by:
                errors.append(
                    f"{name}: bridged binding [{index}] needs covered_by as a "
                    "non-empty list of evidence references"
                )
            else:
                for ref in covered_by:
                    text = str(ref)
                    if len(text) < 12 or "tbd" in text.lower():
                        errors.append(
                            f"{name}: bridged binding [{index}] covered_by "
                            f"entry {text!r} is a placeholder, not evidence"
                        )
            if not binding.get("source") or not binding.get("mechanism"):
                errors.append(
                    f"{name}: bridged binding [{index}] requires source and "
                    "mechanism"
                )
        if kind in ("mapped", "projected") and not (
            binding.get("source") or binding.get("source_function")
        ):
            errors.append(
                f"{name}: {kind} binding [{index}] requires source or "
                "source_function"
            )
        if kind == "constant" and not (
            binding.get("reason") or binding.get("note")
            or binding.get("source_function")
        ):
            errors.append(
                f"{name}: constant binding [{index}] requires a reason"
            )

    suite_names = [manifest["suite"], *(manifest.get("aliases") or [])]
    report_path, report = _report_for(suite_names)
    if report is None:
        errors.append(
            f"{name}: no committed report found for suite/aliases {suite_names}"
        )
    else:
        population = manifest.get("population") or {}
        if population.get("pin_required"):
            provenance = (report.get("provenance") or {}).get("dataset") or {}
            identity = report.get("dataset_identity") or {}
            pinned = bool(
                identity.get("revision")
                or identity.get("sha256")
                or provenance.get("revision")
                or provenance.get("sha256")
            )
            if not pinned:
                findings.append(
                    f"{name}: population pin required but {report_path} carries "
                    "no dataset identity — the lane must stamp the exact "
                    "populace revision + sha (fiit-ecps shows the pattern)"
                )
    if partial:
        findings.append(f"{name}: {partial} binding(s) audit=partial — audit debt")

    completeness = (manifest.get("completeness") or {}).get("status")
    if completeness != "verified":
        findings.append(
            f"{name}: completeness={completeness} — input-catalog verification "
            "pending (engine main's metadata.input_catalog)"
        )
    return errors, findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    manifests = load_manifests()
    if not manifests:
        print("no bridge manifests found", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    all_findings: list[str] = []
    claimed: dict[str, str] = {}
    for path, manifest in manifests.items():
        if isinstance(manifest, dict):
            for claim in [manifest.get("suite"), *(manifest.get("aliases") or [])]:
                if not claim:
                    continue
                if claim in claimed:
                    all_errors.append(
                        f"{path.name}: suite/alias {claim!r} already claimed "
                        f"by {claimed[claim]} — namespace must be unique"
                    )
                claimed[str(claim)] = path.name
        errors, findings = validate(path, manifest)
        all_errors.extend(errors)
        all_findings.extend(findings)

    for line in all_errors:
        print(f"ERROR   {line}", file=sys.stderr)
    for line in all_findings:
        print(f"FINDING {line}")
    print(
        f"{len(manifests)} manifest(s): {len(all_errors)} error(s), "
        f"{len(all_findings)} finding(s)"
    )
    if all_errors:
        return 1
    if args.strict and all_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
