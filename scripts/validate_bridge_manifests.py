#!/usr/bin/env python3
"""Validate bridge manifests — the declared experiment design per suite.

A bridge manifest (``axiom_oracles/bridges/manifests/*.yaml``) declares what a
comparison harness feeds the program under test: mapped, projected, bridged,
or constant, per input. This validator keeps the declarations honest:

* schema and binding-kind checks; every binding is exactly one kind and no
  input-record target is bound twice;
* the suite (or an alias) must have a committed report — a manifest for a
  comparison that doesn't exist certifies nothing;
* population pinning: every non-synthetic population requires
  ``pin_required: true`` and a revision-plus-SHA identity in the committed
  report (charter #374, increment 3);
* suite-backed completeness: ``completeness: {status: verified, source:
  suite_cases}`` reconciles every declared input against the cases returned by
  the suite registry, including record-scoped values and engine-to-Axiom bridge
  targets;
* period honesty: the suite's logical period and the comparison config's
  execution period are reconciled independently. Manifests must declare both
  ``logical_period`` and ``execution_period`` when those periods differ;
* audit debt: ``audit: partial`` entries are counted and printed — a partial
  entry is a to-do, not a certification.

Findings are printed always. ``--strict`` restores the global contract: any
finding on any manifest produces a nonzero exit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO_ROOT / "axiom_oracles" / "bridges" / "manifests"
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
COMPARISON_DIR = REPO_ROOT / "comparisons"

SCHEMA = "axiom_oracles.bridge_manifest.v1"
KINDS = {"mapped", "projected", "bridged", "constant"}
SUITE_CASE_INPUTS = "suite_cases"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
EUROMOD_SYNTHETIC_RUNNER = "euromod-synthetic-compare"
YEAR_MONTH_EXECUTION_RUNNERS = {"axiom-encode-snap-ecps-compare"}


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


def _json_values_equal(left: object, right: object) -> bool:
    """Compare parsed JSON values without conflating booleans and numbers."""

    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_values_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_values_equal(left[key], right[key]) for key in left
        )
    return type(left) is type(right) and left == right


def _valid_dataset_identity(identity: object) -> bool:
    """Require a typed revision and the full lowercase SHA-256 digest."""

    if not isinstance(identity, dict):
        return False
    revision = identity.get("revision")
    sha256 = identity.get("sha256")
    return (
        isinstance(revision, str)
        and bool(revision.strip())
        and isinstance(sha256, str)
        and SHA256_PATTERN.fullmatch(sha256) is not None
    )


def _comparison_execution_periods(
    suite_names: list[str],
) -> tuple[dict[str, str], list[str]]:
    """Return the periods the matching comparison configs actually execute."""

    periods: dict[str, str] = {}
    issues: list[str] = []
    claims = set(suite_names)
    for path in sorted(COMPARISON_DIR.glob("*.yaml")):
        try:
            config = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            issues.append(f"cannot read {path.name}: {exc}")
            continue
        if not isinstance(config, dict):
            continue
        runner = config.get("runner") or {}
        if not isinstance(runner, dict):
            continue
        parameters = runner.get("parameters") or {}
        dashboard = config.get("dashboard") or {}
        if not isinstance(parameters, dict) or not isinstance(dashboard, dict):
            continue
        runner_type = runner.get("type")

        if runner_type == EUROMOD_SYNTHETIC_RUNNER:
            configured_suite = parameters.get("suite")
            if configured_suite not in claims:
                if dashboard.get("suite") in claims:
                    issues.append(
                        f"{path.name} is {EUROMOD_SYNTHETIC_RUNNER} and must bind "
                        "the manifest through runner.parameters.suite"
                    )
                continue
            raw_period = parameters.get("period")
            if raw_period is None or (
                isinstance(raw_period, str) and not raw_period.strip()
            ):
                issues.append(
                    f"{path.name} is {EUROMOD_SYNTHETIC_RUNNER} for suite "
                    f"{configured_suite!r} but lacks required "
                    "runner.parameters.period"
                )
                continue
        else:
            configured_suite = parameters.get("suite") or dashboard.get("suite")
            if configured_suite not in claims:
                continue
            raw_period = parameters.get("period")
            if (
                raw_period is None
                and runner_type in YEAR_MONTH_EXECUTION_RUNNERS
                and parameters.get("year") is not None
            ):
                year = str(parameters["year"])
                month = parameters.get("month")
                raw_period = f"{year}-{int(month):02d}" if month is not None else year
            if raw_period is None:
                issues.append(
                    f"{path.name} matches suite {configured_suite!r} but runner "
                    f"type {runner_type!r} does not declare an execution period"
                )
                continue

        try:
            config_label = str(path.relative_to(REPO_ROOT))
        except ValueError:
            config_label = str(path)
        periods[config_label] = str(raw_period)
    return periods, issues


def _suite_input_catalog(
    suite: str,
) -> tuple[
    set[str],
    set[str],
    dict[str, set[str]],
    set[str],
    set[str],
    list[str],
    dict[str, set[str]],
    dict[tuple[str, str], list[object]],
    dict[tuple[str, str], set[str]],
    dict[str, dict[str, list[object]]],
]:
    """Return the input surface declared by the cases the suite actually runs.

    The suite registry is the comparison runner's source of cases. DK uses two
    supported Axiom input shapes: a flat ``axiom_inputs`` mapping and
    entity-addressed ``axiom_input_records``. Engine-to-Axiom bridge targets are
    inputs too even when they are absent from the pre-bridge flat mapping.

    The final four return values retain record identity: records observed for
    each input, their pre-bridge values, bridge sources by record, and values by
    case. ``varied`` remains the aggregate value check used by older callers.
    A mapped binding may legitimately have one observed value in a one-case
    witness; repeated invariant values across a multi-case suite are constants.
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
            {},
            {},
            {},
            {},
        )
    if not cases:
        return (
            set(),
            set(),
            {},
            set(),
            set(),
            ["suite registry returned no cases"],
            {},
            {},
            {},
            {},
        )

    inputs: set[str] = set()
    bridged: set[str] = set()
    bridge_sources: dict[str, set[str]] = {}
    periods: set[str] = set()
    observed: dict[str, set[str]] = {}
    records_by_input: dict[str, set[str]] = {}
    record_values: dict[tuple[str, str], list[object]] = {}
    record_bridge_sources: dict[tuple[str, str], set[str]] = {}
    case_values: dict[str, dict[str, list[object]]] = {}
    issues: list[str] = []

    def observe(
        name: object,
        value: object,
        where: str,
        *,
        case_id: str,
        record_id: object | None = None,
    ) -> None:
        if not isinstance(name, str) or not name:
            issues.append(f"{where} has a missing/non-string input name")
            return
        inputs.add(name)
        observed.setdefault(name, set()).add(
            json.dumps(value, sort_keys=True, default=str)
        )
        case_values.setdefault(name, {}).setdefault(case_id, []).append(value)
        if record_id is not None:
            if not isinstance(record_id, str) or not record_id:
                issues.append(f"{where} has a missing/non-string entity_id")
                return
            records_by_input.setdefault(name, set()).add(record_id)
            record_values.setdefault((name, record_id), []).append(value)

    def bridge_target(
        name: object,
        source: str,
        where: str,
        *,
        record_id: object | None = None,
    ) -> None:
        if not isinstance(name, str) or not name:
            issues.append(f"{where} has a missing/non-string bridge target name")
            return
        inputs.add(name)
        bridged.add(name)
        bridge_sources.setdefault(name, set()).add(source)
        if record_id is not None:
            if not isinstance(record_id, str) or not record_id:
                issues.append(
                    f"{where} has a missing/non-string bridge target entity_id"
                )
                return
            records_by_input.setdefault(name, set()).add(record_id)
            record_bridge_sources.setdefault((name, record_id), set()).add(source)

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
                    observe(
                        input_name,
                        value,
                        f"case {case_id} axiom_inputs",
                        case_id=case_id,
                    )

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
                        case_id=case_id,
                        record_id=record.get("entity_id"),
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
                            record.get("name"),
                            source,
                            f"{where} records[{index}]",
                            record_id=record.get("entity_id"),
                        )

    for input_record in record_bridge_sources:
        if input_record not in record_values:
            input_name, record_id = input_record
            issues.append(
                f"bridge targets absent input record {input_name!r} / {record_id!r}"
            )

    varied = {name for name, values in observed.items() if len(values) > 1}
    return (
        inputs,
        bridged,
        bridge_sources,
        varied,
        periods,
        issues,
        records_by_input,
        record_values,
        record_bridge_sources,
        case_values,
    )


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
    for field in ("suite", "program", "period", "logical_period", "execution_period"):
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
    binding_claims: dict[str, list[dict[str, object]]] = {}
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
        raw_records = binding.get("records")
        record_scope: frozenset[str] | None
        if raw_records is None:
            record_scope = None
        elif not isinstance(raw_records, list) or not raw_records:
            errors.append(f"{name}: bindings[{index}] records must be a non-empty list")
            record_scope = frozenset()
        elif any(not isinstance(record, str) or not record for record in raw_records):
            errors.append(
                f"{name}: bindings[{index}] records must contain non-empty strings"
            )
            record_scope = frozenset()
        else:
            record_scope = frozenset(raw_records)
            if len(record_scope) != len(raw_records):
                errors.append(
                    f"{name}: bindings[{index}] records contains a duplicate target"
                )
        if record_scope is not None and not named:
            errors.append(
                f"{name}: bindings[{index}] record scope requires explicit input(s)"
            )
        if kind == "constant" and record_scope is not None and "value" not in binding:
            errors.append(
                f"{name}: record-scoped constant binding [{index}] requires value"
            )
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
            seen_inputs.add(input_name)
            claims = binding_claims.setdefault(input_name, [])
            for prior in claims:
                prior_scope = prior["records"]
                if prior_scope is None or record_scope is None:
                    errors.append(
                        f"{name}: input `{input_name}` has overlapping unscoped "
                        "and record-scoped bindings"
                    )
                    continue
                overlap = set(prior_scope) & set(record_scope)
                if overlap:
                    errors.append(
                        f"{name}: input `{input_name}` bound more than once for "
                        f"record(s) {sorted(overlap)}"
                    )
            claims.append(
                {
                    "index": index,
                    "kind": kind,
                    "source": binding.get("source"),
                    "records": record_scope,
                    "value": binding.get("value"),
                    "has_value": "value" in binding,
                }
            )
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
        source = binding.get("source")
        if (
            kind in ("mapped", "projected")
            and isinstance(source, str)
            and source.startswith("population:")
            and manifest["population"].get("family") == "synthetic"
        ):
            errors.append(
                f"{name}: {kind} binding [{index}] fabricates external population "
                "provenance for a suite-enumerated synthetic population"
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
        family = population.get("family")
        if not isinstance(family, str) or not family:
            errors.append(f"{name}: population.family must be a non-empty string")
        pin_required = population.get("pin_required")
        if not isinstance(pin_required, bool):
            errors.append(f"{name}: population.pin_required must be true|false")
        report_provenance = report.get("provenance") or {}
        if not isinstance(report_provenance, dict):
            report_provenance = {}
        provenance_dataset = report_provenance.get("dataset") or {}
        if not isinstance(provenance_dataset, dict):
            provenance_dataset = {}
        identities = (
            report.get("dataset_identity"),
            report_provenance.get("dataset_identity"),
            provenance_dataset,
        )
        pinned = any(_valid_dataset_identity(identity) for identity in identities)
        report_population = report.get("population")
        provenance_population = provenance_dataset.get("population")
        synthetic = (
            population.get("case_source") == "suite"
            or family == "synthetic"
            or report_population == "synthetic"
            or provenance_population == "synthetic"
        )
        if synthetic:
            if family != "synthetic":
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
        else:
            if pin_required is not True:
                findings.append(
                    f"{name}: non-synthetic population family {family!r} requires "
                    "pin_required=true"
                )
            if not pinned:
                findings.append(
                    f"{name}: non-synthetic population family {family!r} has no "
                    f"revision + sha256 identity in {report_path}; revision must "
                    "be a non-empty string and sha256 a full lowercase digest"
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
            records_by_input,
            record_values,
            record_bridge_sources,
            case_values,
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

        resolved_claims: dict[tuple[str, str | None], dict[str, object]] = {}
        for input_name in sorted(catalog & seen_inputs):
            claims = binding_claims.get(input_name, [])
            actual_records = records_by_input.get(input_name, set())
            if actual_records:
                for claim in claims:
                    scope = claim["records"]
                    if scope is None:
                        continue
                    unexpected = set(scope) - actual_records
                    if unexpected:
                        errors.append(
                            f"{name}: input `{input_name}` binding targets record(s) "
                            f"the suite does not feed: {sorted(unexpected)}"
                        )
                for record_id in sorted(actual_records):
                    matching = [
                        claim
                        for claim in claims
                        if claim["records"] is None or record_id in claim["records"]
                    ]
                    if len(matching) != 1:
                        errors.append(
                            f"{name}: input `{input_name}` record {record_id!r} "
                            f"must have exactly one binding, found {len(matching)}"
                        )
                    elif matching:
                        resolved_claims[(input_name, record_id)] = matching[0]
            else:
                scoped = [claim for claim in claims if claim["records"] is not None]
                if scoped:
                    errors.append(
                        f"{name}: flat input `{input_name}` cannot use record-scoped "
                        "bindings"
                    )
                unscoped = [claim for claim in claims if claim["records"] is None]
                if len(unscoped) != 1:
                    errors.append(
                        f"{name}: flat input `{input_name}` must have exactly one "
                        f"binding, found {len(unscoped)}"
                    )
                elif unscoped:
                    resolved_claims[(input_name, None)] = unscoped[0]

        wrong_bridge_kind: list[str] = []
        wrong_bridge_source: list[str] = []
        phantom_bridges: list[str] = []
        for (input_name, record_id), claim in resolved_claims.items():
            label = input_name if record_id is None else f"{input_name}[{record_id}]"
            if record_id is None:
                expected_sources = (
                    bridge_sources.get(input_name, set())
                    if input_name in bridged
                    else set()
                )
            else:
                expected_sources = record_bridge_sources.get(
                    (input_name, record_id), set()
                )
            if expected_sources:
                if claim["kind"] != "bridged":
                    wrong_bridge_kind.append(label)
                source = claim["source"]
                if not isinstance(source, str) or expected_sources != {source}:
                    wrong_bridge_source.append(f"{label}={sorted(expected_sources)}")
            elif claim["kind"] == "bridged":
                phantom_bridges.append(label)
            elif record_id is not None and input_name in bridged:
                if claim["kind"] != "constant" or not claim["has_value"]:
                    errors.append(
                        f"{name}: non-bridge remainder {label} must be a "
                        "record-scoped constant with an explicit value"
                    )
        if wrong_bridge_kind:
            errors.append(
                f"{name}: suite bridge target(s) must be kind=bridged: "
                f"{', '.join(sorted(wrong_bridge_kind))}"
            )
        if wrong_bridge_source:
            errors.append(
                f"{name}: suite bridge target source mismatch; expected "
                f"{', '.join(sorted(wrong_bridge_source))}"
            )
        if phantom_bridges:
            errors.append(
                f"{name}: kind=bridged input record(s) are not suite bridge "
                f"targets: {', '.join(sorted(phantom_bridges))}"
            )

        varied_constants = sorted(
            input_name
            for (input_name, record_id), claim in resolved_claims.items()
            if record_id is None
            and input_name in varied
            and claim["kind"] == "constant"
        )
        if varied_constants:
            errors.append(
                f"{name}: suite-varying input(s) cannot be kind=constant: "
                f"{', '.join(varied_constants)}"
            )
        unscoped_record_constants = {
            input_name
            for (input_name, record_id), claim in resolved_claims.items()
            if record_id is not None
            and claim["records"] is None
            and claim["kind"] == "constant"
        }
        record_varying_constants = []
        for input_name in sorted(unscoped_record_constants):
            values = [
                value
                for (
                    observed_input,
                    _record_id,
                ), observed_values in record_values.items()
                if observed_input == input_name
                for value in observed_values
            ]
            if values and any(
                not _json_values_equal(values[0], value) for value in values[1:]
            ):
                record_varying_constants.append(input_name)
        if record_varying_constants:
            errors.append(
                f"{name}: record-varying input(s) cannot use an unscoped "
                f"kind=constant binding: {', '.join(record_varying_constants)}"
            )
        invariant_mapped = sorted(
            input_name
            for (input_name, record_id), claim in resolved_claims.items()
            if record_id is None
            and len(case_values.get(input_name, {})) > 1
            and input_name not in varied
            and claim["kind"] in ("mapped", "projected")
        )
        if invariant_mapped:
            errors.append(
                f"{name}: suite-invariant multi-case input(s) must be "
                f"kind=constant, not mapped/projected: {', '.join(invariant_mapped)}"
            )

        for (input_name, record_id), claim in resolved_claims.items():
            if (
                record_id is None
                or claim["kind"] != "constant"
                or not claim["has_value"]
            ):
                continue
            actual_values = record_values.get((input_name, record_id), [])
            declared_value = claim["value"]
            if not actual_values or any(
                not _json_values_equal(declared_value, value) for value in actual_values
            ):
                findings.append(
                    f"{name}: record-scoped constant {input_name}[{record_id}] "
                    f"declares {declared_value!r}, but the suite feeds "
                    f"{actual_values!r}"
                )

        logical_period = str(manifest.get("logical_period", manifest["period"]))
        if "logical_period" in manifest and manifest["period"] != logical_period:
            errors.append(
                f"{name}: period {manifest['period']!r} must equal declared "
                f"logical_period {logical_period!r}"
            )
        if periods != {logical_period}:
            errors.append(
                f"{name}: logical_period {logical_period!r} does not match suite "
                f"case period(s) {sorted(periods)}"
            )
        configured_periods, config_issues = _comparison_execution_periods(suite_names)
        errors.extend(f"{name}: comparison config: {issue}" for issue in config_issues)
        if not configured_periods:
            errors.append(
                f"{name}: no comparison config execution period found for "
                f"suite/aliases {suite_names}"
            )
        else:
            executed_values = set(configured_periods.values())
            if len(executed_values) != 1:
                details = ", ".join(
                    f"{config}={period!r}"
                    for config, period in configured_periods.items()
                )
                errors.append(
                    f"{name}: comparison configs disagree on execution period: "
                    f"{details}"
                )
            else:
                configured_execution = next(iter(executed_values))
                if configured_execution != logical_period and not {
                    "logical_period",
                    "execution_period",
                }.issubset(manifest):
                    errors.append(
                        f"{name}: differing logical and execution periods require "
                        "explicit logical_period and execution_period"
                    )
                declared_execution = str(
                    manifest.get("execution_period", logical_period)
                )
                if declared_execution != configured_execution:
                    details = ", ".join(sorted(configured_periods))
                    errors.append(
                        f"{name}: execution_period {declared_execution!r} does not "
                        f"match {details} ({configured_execution!r})"
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return nonzero when any manifest has a finding",
    )
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
    if args.strict:
        print(
            f"strict enforcement: all {len(manifests)} manifest(s), "
            f"{len(all_findings)} finding(s)"
        )
    if all_errors:
        return 1
    if args.strict and all_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
