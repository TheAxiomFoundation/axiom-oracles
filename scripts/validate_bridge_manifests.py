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


def _known_suites() -> set[str]:
    names = set()
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("suite"):
            names.add(str(payload["suite"]))
    return names


KNOWN_SUITES = _known_suites()


def _covered_by_resolves(text: str) -> bool:
    """A covered_by entry must point at something that exists.

    A length heuristic accepts any long string, and a path-SHAPE heuristic
    accepts ghosts — both were demonstrated ("ABCDEFGHIJKL",
    "ghost-sibling/no-such/evidence.yaml", "/etc/passwd"). Require the entry
    to mention a repository path that EXISTS or a suite with a committed
    report; prose around it may stay free-form.

    Evidence living in a sibling repository cannot be verified from here, so
    it is deliberately NOT accepted: cite it in the manifest note and point
    covered_by at something this repository can check.
    """
    if "tbd" in text.lower():
        return False
    for token in text.replace(",", " ").replace("(", " ").replace(")", " ").split():
        candidate = token.strip("'\"`;")
        if not candidate or candidate.startswith("/") or ".." in candidate:
            # Absolute and traversal paths are never evidence in this repo;
            # `/etc/passwd` passed the previous path-shape heuristic.
            continue
        if (REPO_ROOT / candidate).exists():
            return True
        if candidate in KNOWN_SUITES:
            return True
    return False


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
    aliases = manifest.get("aliases")
    if aliases is not None and not isinstance(aliases, list):
        # A scalar alias iterates character-by-character everywhere aliases are
        # consumed, which silently bypasses collision detection (audit F5).
        errors.append(f"{name}: `aliases` must be a list, got {type(aliases).__name__}")
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
                # At least one entry must be checkable HERE. Cross-repository
                # evidence is real but unverifiable from this checkout, so it
                # is recorded as visible debt rather than either silently
                # accepted (the old path-shape heuristic) or discarded.
                resolvable = [r for r in covered_by if _covered_by_resolves(str(r))]
                unresolvable = [r for r in covered_by if str(r) not in map(str, resolvable)]
                if not resolvable:
                    errors.append(
                        f"{name}: bridged binding [{index}] has no covered_by "
                        "entry this repository can check — name a path that "
                        "exists or a suite with a committed report"
                    )
                for ref in unresolvable:
                    findings.append(
                        f"{name}: bridged binding [{index}] covered_by entry "
                        f"{str(ref)[:60]!r} is not verifiable from this "
                        "repository (cross-repo evidence — audit debt)"
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
    if completeness == "verified":
        # Nothing can confirm this yet: verification requires reconciling the
        # bindings against the engine's metadata.input_catalog, which the
        # current artifacts do not carry. A self-asserted `verified` is an
        # unbacked claim, not a state (audit F5).
        errors.append(
            f"{name}: completeness=verified cannot be self-asserted — no "
            "input_catalog is available to reconcile bindings against"
        )
    else:
        findings.append(
            f"{name}: completeness={completeness} — input-catalog verification "
            "pending (engine main's metadata.input_catalog)"
        )
    return errors, findings


def global_collisions(manifests: dict) -> list[str]:
    """Suite/alias claims must be unique across ALL manifests.

    Exposed separately so callers deciding whether a manifest is strict-clean
    (the census's bridge_audited) apply the same rule the CLI does — a
    per-manifest validate() alone misses collisions by construction.
    """
    errors: list[str] = []
    claimed: dict[str, str] = {}
    for path, manifest in manifests.items():
        if not isinstance(manifest, dict):
            continue
        aliases = manifest.get("aliases")
        names = [manifest.get("suite")]
        if isinstance(aliases, list):
            names.extend(aliases)
        for claim in names:
            if not claim:
                continue
            if claim in claimed and claimed[claim] != path.name:
                errors.append(
                    f"{path.name}: suite/alias {claim!r} already claimed by "
                    f"{claimed[claim]} — namespace must be unique"
                )
            claimed[str(claim)] = path.name
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    manifests = load_manifests()
    if not manifests:
        print("no bridge manifests found", file=sys.stderr)
        return 1

    all_errors: list[str] = global_collisions(manifests)
    all_findings: list[str] = []
    for path, manifest in manifests.items():
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
