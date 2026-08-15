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
* suite-backed completeness: ``completeness: {status: verified, source:
  suite_cases}`` reconciles every declared input against the cases returned by
  the suite registry, including input-record and engine-to-Axiom bridge targets;
* audit debt: ``audit: partial`` entries are counted and printed — a partial
  entry is a to-do, not a certification.

Findings are printed always. ``--strict`` turns findings on manifests that opt
in with ``strict: true`` into a nonzero exit. This lets a newly audited lane
enforce zero debt without pretending older reporting-only manifests are clean.
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
SUITE_CASE_INPUTS = "suite_cases"


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
        if (REPO_ROOT / candidate).is_file():
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


def _suite_input_catalog(
    suite: str,
) -> tuple[
    set[str],
    set[str],
    dict[str, set[str]],
    set[str],
    set[str],
    list[str],
]:
    """Return the input surface declared by the cases the suite actually runs.

    The suite registry is the comparison runner's source of cases. DK uses two
    supported Axiom input shapes: a flat ``axiom_inputs`` mapping and
    entity-addressed ``axiom_input_records``. Engine-to-Axiom bridge targets are
    inputs too even when they are absent from the pre-bridge flat mapping.

    Returns ``(inputs, bridged, bridge_sources, varied, periods, issues)``.
    ``varied`` is only a one-way check: a constant binding cannot cover values
    that demonstrably vary, while a mapped binding may legitimately have one
    observed value in a one-case witness.
    """
    from axiom_oracles.suites import load_suite

    try:
        cases = load_suite(suite)
    except (KeyError, ValueError) as exc:
        return (
            set(),
            set(),
            {},
            set(),
            set(),
            [f"suite registry load failed: {exc}"],
        )
    if not cases:
        return set(), set(), {}, set(), set(), ["suite registry returned no cases"]

    inputs: set[str] = set()
    bridged: set[str] = set()
    bridge_sources: dict[str, set[str]] = {}
    periods: set[str] = set()
    observed: dict[str, set[str]] = {}
    issues: list[str] = []

    def observe(name: object, value: object, where: str) -> None:
        if not isinstance(name, str) or not name:
            issues.append(f"{where} has a missing/non-string input name")
            return
        inputs.add(name)
        observed.setdefault(name, set()).add(
            json.dumps(value, sort_keys=True, default=str)
        )

    def bridge_target(name: object, source: str, where: str) -> None:
        if not isinstance(name, str) or not name:
            issues.append(f"{where} has a missing/non-string bridge target name")
            return
        inputs.add(name)
        bridged.add(name)
        bridge_sources.setdefault(name, set()).add(source)

    for case in cases:
        case_id = str(getattr(case, "case_id", "?"))
        periods.add(str(getattr(case, "period", "")))
        metadata = getattr(case, "metadata", {})
        if not isinstance(metadata, dict):
            # Case.metadata is typed as Mapping; normalize other Mapping
            # implementations without requiring the validator to know them.
            try:
                metadata = dict(metadata)
            except (TypeError, ValueError):
                issues.append(f"case {case_id} metadata is not a mapping")
                continue

        flat = metadata.get("axiom_inputs")
        if flat is not None:
            if not isinstance(flat, dict):
                issues.append(f"case {case_id} axiom_inputs is not a mapping")
            else:
                for input_name, value in flat.items():
                    observe(input_name, value, f"case {case_id} axiom_inputs")

        records = metadata.get("axiom_input_records")
        if records is not None:
            if not isinstance(records, list):
                issues.append(f"case {case_id} axiom_input_records is not a list")
            else:
                for index, record in enumerate(records):
                    if not isinstance(record, dict):
                        issues.append(
                            f"case {case_id} axiom_input_records[{index}] "
                            "is not a mapping"
                        )
                        continue
                    observe(
                        record.get("name"),
                        record.get("value"),
                        f"case {case_id} axiom_input_records[{index}]",
                    )

        bridge = metadata.get("euromod_to_axiom_input_bridge")
        if bridge is not None:
            if not isinstance(bridge, dict):
                issues.append(
                    f"case {case_id} euromod_to_axiom_input_bridge is not a mapping"
                )
                continue
            for source_name, target_spec in bridge.items():
                where = f"case {case_id} bridge source {source_name}"
                if not isinstance(source_name, str) or not source_name:
                    issues.append(f"{where} has a missing/non-string source name")
                    continue
                source = f"euromod:{source_name}"
                if not isinstance(target_spec, dict):
                    issues.append(f"{where} target specification is not a mapping")
                    continue
                target_inputs = target_spec.get("inputs") or []
                if not isinstance(target_inputs, list):
                    issues.append(f"{where} inputs is not a list")
                else:
                    for input_name in target_inputs:
                        bridge_target(input_name, source, where)
                target_records = target_spec.get("records") or []
                if not isinstance(target_records, list):
                    issues.append(f"{where} records is not a list")
                else:
                    for index, record in enumerate(target_records):
                        if not isinstance(record, dict):
                            issues.append(f"{where} records[{index}] is not a mapping")
                            continue
                        bridge_target(
                            record.get("name"), source, f"{where} records[{index}]"
                        )

    varied = {name for name, values in observed.items() if len(values) > 1}
    return inputs, bridged, bridge_sources, varied, periods, issues


def validate(path: Path, manifest: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    findings: list[str] = []
    name = path.name

    if not isinstance(manifest, dict):
        return [f"{name}: manifest must be a mapping"], findings
    if manifest.get("schema") != SCHEMA:
        errors.append(f"{name}: schema must be {SCHEMA}")
        return errors, findings
    for field in (
        "suite",
        "program",
        "period",
        "bindings",
        "population",
        "oracle",
    ):
        if field not in manifest:
            errors.append(f"{name}: missing required field `{field}`")
    for field in ("suite", "program", "period"):
        if field in manifest and (
            not isinstance(manifest[field], str) or not manifest[field]
        ):
            errors.append(f"{name}: `{field}` must be a non-empty string")
    if "population" in manifest and not isinstance(manifest["population"], dict):
        errors.append(f"{name}: population must be a mapping")
    if "oracle" in manifest and not isinstance(manifest["oracle"], dict):
        errors.append(f"{name}: oracle must be a mapping")
    if "strict" in manifest and not isinstance(manifest["strict"], bool):
        errors.append(
            f"{name}: `strict` must be a boolean, got "
            f"{type(manifest['strict']).__name__}"
        )
    aliases = manifest.get("aliases")
    if aliases is not None and not isinstance(aliases, list):
        # A scalar alias iterates character-by-character everywhere aliases are
        # consumed, which silently bypasses collision detection (audit F5).
        errors.append(f"{name}: `aliases` must be a list, got {type(aliases).__name__}")
    elif isinstance(aliases, list) and any(
        not isinstance(alias, str) or not alias for alias in aliases
    ):
        errors.append(f"{name}: every alias must be a non-empty string")
    if errors:
        return errors, findings

    bindings = manifest["bindings"]
    if not isinstance(bindings, list) or not bindings:
        errors.append(f"{name}: bindings must be a non-empty list")
        return errors, findings
    seen_inputs: set[str] = set()
    input_kinds: dict[str, str] = {}
    input_sources: dict[str, object] = {}
    partial = 0
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            errors.append(f"{name}: bindings[{index}] is not a mapping")
            continue
        kind = binding.get("kind")
        if kind not in KINDS:
            errors.append(
                f"{name}: bindings[{index}] kind `{kind}` not in {sorted(KINDS)}"
            )
            continue
        if binding.get("audit") not in ("read", "partial"):
            errors.append(f"{name}: bindings[{index}] audit must be read|partial")
        if binding.get("audit") == "partial":
            partial += 1
        raw_inputs = binding.get("inputs")
        if raw_inputs is not None and not isinstance(raw_inputs, list):
            errors.append(f"{name}: bindings[{index}] inputs must be a list")
            named = []
        elif raw_inputs is not None:
            named = raw_inputs
        elif binding.get("input"):
            named = [binding["input"]]
        else:
            named = []
        # A bridged binding may declare at dimension level: the receiving
        # inputs are enumerable audit debt, the dimension is the claim.
        if (
            not named
            and not binding.get("group")
            and not (kind == "bridged" and binding.get("dimension"))
        ):
            errors.append(
                f"{name}: bindings[{index}] names neither `input(s)`, `group`, "
                "nor (for bridged) `dimension`"
            )
        for input_name in named:
            if not isinstance(input_name, str) or not input_name:
                errors.append(
                    f"{name}: bindings[{index}] has a missing/non-string input name"
                )
                continue
            if input_name in seen_inputs:
                errors.append(f"{name}: input `{input_name}` bound more than once")
            seen_inputs.add(input_name)
            input_kinds[input_name] = kind
            input_sources[input_name] = binding.get("source")
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
                unresolvable = [
                    r for r in covered_by if str(r) not in map(str, resolvable)
                ]
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
            if not isinstance(binding.get("source"), str) or not binding.get("source"):
                errors.append(
                    f"{name}: bridged binding [{index}] requires a non-empty "
                    "string source"
                )
            if not isinstance(binding.get("mechanism"), str) or not binding.get(
                "mechanism"
            ):
                errors.append(
                    f"{name}: bridged binding [{index}] requires a non-empty "
                    "string mechanism"
                )
        if kind in ("mapped", "projected") and not (
            binding.get("source") or binding.get("source_function")
        ):
            errors.append(
                f"{name}: {kind} binding [{index}] requires source or source_function"
            )
        if kind == "constant" and not (
            binding.get("reason")
            or binding.get("note")
            or binding.get("source_function")
        ):
            errors.append(f"{name}: constant binding [{index}] requires a reason")

    suite_names = [manifest["suite"], *(manifest.get("aliases") or [])]
    report_path, report = _report_for(suite_names)
    if report is None:
        errors.append(
            f"{name}: no committed report found for suite/aliases {suite_names}"
        )
    else:
        population = manifest.get("population") or {}
        pin_required = population.get("pin_required")
        if not isinstance(pin_required, bool):
            errors.append(f"{name}: population.pin_required must be true|false")
        if pin_required:
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
        report_population = report.get("population")
        provenance_population = (
            (report.get("provenance") or {}).get("dataset") or {}
        ).get("population")
        if (
            population.get("case_source") == "suite"
            or population.get("family") == "synthetic"
            or report_population == "synthetic"
            or provenance_population == "synthetic"
        ):
            if population.get("family") != "synthetic":
                errors.append(
                    f"{name}: population.case_source=suite requires family=synthetic"
                )
            if population.get("case_source") != "suite":
                errors.append(
                    f"{name}: synthetic population must declare case_source=suite"
                )
            if pin_required is not False:
                errors.append(
                    f"{name}: suite-enumerated synthetic population must set "
                    "pin_required=false"
                )
            if report_population != "synthetic" or provenance_population != "synthetic":
                errors.append(
                    f"{name}: manifest declares a suite-enumerated synthetic "
                    f"population but {report_path} does not"
                )
    if partial:
        findings.append(f"{name}: {partial} binding(s) audit=partial — audit debt")

    completeness_block = manifest.get("completeness") or {}
    if not isinstance(completeness_block, dict):
        errors.append(f"{name}: completeness must be a mapping")
        completeness_block = {}
    completeness = completeness_block.get("status")
    if completeness == "verified" and completeness_block.get("source") == (
        SUITE_CASE_INPUTS
    ):
        (
            catalog,
            bridged,
            bridge_sources,
            varied,
            periods,
            catalog_issues,
        ) = _suite_input_catalog(str(manifest["suite"]))
        errors.extend(
            f"{name}: suite input catalog: {issue}" for issue in catalog_issues
        )
        missing = sorted(catalog - seen_inputs)
        extra = sorted(seen_inputs - catalog)
        if missing:
            errors.append(f"{name}: bindings omit suite input(s): {', '.join(missing)}")
        if extra:
            errors.append(
                f"{name}: bindings declare input(s) the suite does not feed: "
                f"{', '.join(extra)}"
            )
        wrong_bridge_kind = sorted(
            input_name
            for input_name in bridged
            if input_kinds.get(input_name) != "bridged"
        )
        if wrong_bridge_kind:
            errors.append(
                f"{name}: suite bridge target(s) must be kind=bridged: "
                f"{', '.join(wrong_bridge_kind)}"
            )
        wrong_bridge_source = sorted(
            input_name
            for input_name, expected_sources in bridge_sources.items()
            if not isinstance(input_sources.get(input_name), str)
            or expected_sources != {input_sources[input_name]}
        )
        if wrong_bridge_source:
            expected = ", ".join(
                f"{input_name}={sorted(bridge_sources[input_name])}"
                for input_name in wrong_bridge_source
            )
            errors.append(
                f"{name}: suite bridge target source mismatch; expected {expected}"
            )
        phantom_bridges = sorted(
            input_name
            for input_name, kind in input_kinds.items()
            if kind == "bridged" and input_name not in bridged
        )
        if phantom_bridges:
            errors.append(
                f"{name}: kind=bridged input(s) are not suite bridge targets: "
                f"{', '.join(phantom_bridges)}"
            )
        varied_constants = sorted(
            input_name
            for input_name in varied
            if input_kinds.get(input_name) == "constant"
        )
        if varied_constants:
            errors.append(
                f"{name}: suite-varying input(s) cannot be kind=constant: "
                f"{', '.join(varied_constants)}"
            )
        declared_period = str(manifest.get("period"))
        if periods != {declared_period}:
            errors.append(
                f"{name}: period {declared_period!r} does not match suite "
                f"case period(s) {sorted(periods)}"
            )
    elif completeness == "verified":
        # A bare assertion remains forbidden. `verified` is accepted only when
        # the validator can derive and reconcile the suite's actual case input
        # surface.
        errors.append(
            f"{name}: completeness=verified cannot be self-asserted — set "
            f"source={SUITE_CASE_INPUTS} for computed reconciliation"
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
            if not isinstance(claim, str) or not claim:
                continue
            if claim in claimed and claimed[claim] != path.name:
                errors.append(
                    f"{path.name}: suite/alias {claim!r} already claimed by "
                    f"{claimed[claim]} — namespace must be unique"
                )
            claimed[claim] = path.name
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
    strict_findings: list[str] = []
    strict_manifests = 0
    for path, manifest in manifests.items():
        errors, findings = validate(path, manifest)
        all_errors.extend(errors)
        all_findings.extend(findings)
        if isinstance(manifest, dict) and manifest.get("strict") is True:
            strict_manifests += 1
            strict_findings.extend(findings)

    for line in all_errors:
        print(f"ERROR   {line}", file=sys.stderr)
    for line in all_findings:
        print(f"FINDING {line}")
    print(
        f"{len(manifests)} manifest(s): {len(all_errors)} error(s), "
        f"{len(all_findings)} finding(s)"
    )
    if args.strict:
        print(
            f"strict enforcement: {strict_manifests} manifest(s), "
            f"{len(strict_findings)} finding(s)"
        )
    if all_errors:
        return 1
    if args.strict and strict_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
