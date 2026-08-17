#!/usr/bin/env python3
"""Reproduce the committed Denmark child/youth-benefit Axiom values.

This producer makes the executable certification premise a computed claim. It
archives an exact ``rulespec-dk`` Git commit, compiles the two composed benefit
modules through the adapter's ``compile-composed`` path with the configured
engine binary, and replays the ten committed Axiom-side comparison inputs.

The committed artifact is intentionally self-validating without an external
checkout: :func:`validate_artifact` binds it to the in-repo comparison configs,
reports, exact case inputs, and expected values using exact JSON numeric
equality. ``--check`` additionally does the expensive part again: it archives
the receipt's recorded commit, recompiles and reruns every case, then rejects
any serialized drift in the derived artifact.

Usage::

    python scripts/executable_reproduction.py
    python scripts/executable_reproduction.py --check
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner  # noqa: E402
from axiom_oracles.core.case import Case  # noqa: E402
from axiom_oracles.evidence import validate_suite_evidence  # noqa: E402
from axiom_oracles.suites.dk_child_youth_benefit import (  # noqa: E402
    dk_child_youth_benefit_couple_cases,
)

SCHEMA = "axiom_oracles.executable_reproduction.v1"
PROGRAM = "dk/boerne-og-ungeydelse"
GENERATED_BY = "scripts/executable_reproduction.py"
EXECUTION_PERIOD = "2025-06-01"
RULESPEC_REPO = "TheAxiomFoundation/rulespec-dk"
DEFAULT_RULESPEC_REF = "main"

PINNED_ENGINE_SHA256 = (
    "079c26f4244db8c2a72fcbfb8cf88aaa5cb7c99628dc1c8d9d3b2d011e5f32a5"
)
DEFAULT_RULESPEC_ROOT = Path.home() / "TheAxiomFoundation" / "rulespec-dk"
DEFAULT_ENGINE_BINARY = (
    Path.home()
    / "TheAxiomFoundation"
    / "_worktrees"
    / "axiom-rules-engine-pin"
    / "target"
    / "release"
    / "axiom-rules-engine"
)
OUTPUT_PATH = REPO_ROOT / "conformance" / "executable" / "dk-boerne-og-ungeydelse.json"

SINGLE_PROGRAM = "dk:statutes/composed/boerne-og-ungeydelse-pipeline"
COUPLE_PROGRAM = "dk:statutes/composed/boerne-og-ungeydelse-couple-pipeline"
PROGRAM_SPECS = (
    {
        "program": SINGLE_PROGRAM,
        "source_path": ("dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml"),
    },
    {
        "program": COUPLE_PROGRAM,
        "source_path": (
            "dk/statutes/composed/boerne-og-ungeydelse-couple-pipeline.yaml"
        ),
    },
)

REPORT_SPECS = (
    {
        "suite": "dk-child-youth-benefit",
        "path": ("dashboard/public/data/axiom-euromod-dk-child-youth-benefit.json"),
        "config": "comparisons/dk-child-youth-benefit-euromod.yaml",
        "program": SINGLE_PROGRAM,
        "case_count": 8,
        "input_source": "committed_report",
    },
    {
        "suite": "dk-child-youth-benefit-2023",
        "path": (
            "dashboard/public/data/axiom-euromod-dk-child-youth-benefit-2023.json"
        ),
        "config": "comparisons/dk-child-youth-benefit-2023-euromod.yaml",
        "program": SINGLE_PROGRAM,
        "case_count": 1,
        "input_source": "committed_report",
    },
    {
        "suite": "dk-child-youth-benefit-couple",
        "path": (
            "dashboard/public/data/axiom-euromod-dk-child-youth-benefit-couple.json"
        ),
        "config": "comparisons/dk-child-youth-benefit-couple-euromod.yaml",
        "program": COUPLE_PROGRAM,
        "case_count": 1,
        "input_source": "suite_plus_committed_bridge",
    },
)

HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
BRIDGED_RECORD_KEY = re.compile(
    r"^(?P<entity>[^\[]+)\[(?P<entity_id>[^\]]+)\]::(?P<name>.+)$"
)


def _canonical_json(value: Any) -> str:
    """Return a type-aware, exact JSON representation of one value."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _render(document: dict[str, Any]) -> str:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return document


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _configured_engine_pin(repo_root: Path = REPO_ROOT) -> str:
    pins: dict[str, str] = {}
    for spec in REPORT_SPECS:
        config_path = repo_root / str(spec["config"])
        try:
            config = yaml.safe_load(config_path.read_text())
            parameters = config["runner"]["parameters"]
            pin = parameters["engine_binary_sha256"]
        except (OSError, TypeError, KeyError, yaml.YAMLError) as exc:
            raise ValueError(
                f"{config_path}: cannot read runner.parameters.engine_binary_sha256"
            ) from exc
        _require(
            parameters.get("suite") == spec["suite"],
            f"{config_path}: configured suite does not match {spec['suite']}",
        )
        _require(
            str(parameters.get("period")) == EXECUTION_PERIOD,
            f"{config_path}: executable period must be {EXECUTION_PERIOD}",
        )
        _require(
            isinstance(pin, str) and HEX_64.fullmatch(pin) is not None,
            f"{config_path}: invalid engine binary SHA-256",
        )
        pins[str(spec["config"])] = pin
    unique = set(pins.values())
    _require(
        len(unique) == 1,
        "DK comparison configs disagree on engine binary SHA-256: "
        + ", ".join(f"{path}={pin}" for path, pin in pins.items()),
    )
    configured = unique.pop()
    _require(
        configured == PINNED_ENGINE_SHA256,
        "DK comparison config pin drifted from the certification pin: "
        f"{configured} != {PINNED_ENGINE_SHA256}",
    )
    return configured


def _comparison_value(case_row: dict[str, Any], label: str) -> tuple[str, Any]:
    comparisons = [
        *list(case_row.get("matches") or []),
        *list(case_row.get("mismatches") or []),
    ]
    _require(
        len(comparisons) == 1 and isinstance(comparisons[0], dict),
        f"{label}: expected exactly one matches+mismatches comparison",
    )
    comparison = comparisons[0]
    concept = comparison.get("concept")
    _require(
        isinstance(concept, str) and concept,
        f"{label}: comparison concept is missing",
    )
    _require("right" in comparison, f"{label}: Axiom right value is missing")
    # Prove it is finite/JSON-serializable now, not during artifact rendering.
    _canonical_json(comparison["right"])
    return concept, comparison["right"]


def _couple_metadata(
    report_case: dict[str, Any],
    *,
    suite_cases: dict[str, Case],
    label: str,
) -> dict[str, Any]:
    case_id = str(report_case.get("case_id", ""))
    base = suite_cases.get(case_id)
    _require(base is not None, f"{label}: case is absent from the committed suite")
    metadata = copy.deepcopy(dict(base.metadata))
    records = metadata.get("axiom_input_records")
    _require(
        isinstance(records, list) and len(records) == 18,
        f"{label}: suite must declare exactly 18 Axiom input records",
    )

    report_metadata = report_case.get("metadata")
    _require(isinstance(report_metadata, dict), f"{label}: metadata is missing")
    applied = report_metadata.get("euromod_to_axiom_input_bridge_applied")
    _require(
        isinstance(applied, dict) and len(applied) == 2,
        f"{label}: expected exactly two committed bridge-applied records",
    )
    income_basis_prefix = (
        "Person[earner]::dk:statutes/lbk-603-2025/"
        "boerne-og-ungeydelsesloven/paragraf-1-a#input."
    )
    expected_bridge_keys = {
        income_basis_prefix + "personskatteloven_section_7_income_basis",
        income_basis_prefix
        + "personskatteloven_section_7_income_basis_after_section_14_recalculation",
    }
    _require(
        set(applied) == expected_bridge_keys,
        f"{label}: committed bridge must update the earner's two section-7 slots",
    )
    _require(
        all(
            _canonical_json(value) == _canonical_json(1_380_000.0)
            for value in applied.values()
        ),
        f"{label}: committed earner section-7 basis must be exactly 1380000.0",
    )
    matched_indices: set[int] = set()
    for raw_key, value in applied.items():
        key_match = BRIDGED_RECORD_KEY.fullmatch(str(raw_key))
        _require(key_match is not None, f"{label}: malformed bridge key {raw_key!r}")
        key = key_match.groupdict()
        matches = [
            index
            for index, record in enumerate(records)
            if isinstance(record, dict)
            and record.get("entity") == key["entity"]
            and record.get("entity_id") == key["entity_id"]
            and record.get("name") == key["name"]
        ]
        _require(
            len(matches) == 1,
            f"{label}: bridge key {raw_key!r} resolves to {len(matches)} records",
        )
        index = matches[0]
        records[index]["value"] = value
        matched_indices.add(index)
    _require(
        len(matched_indices) == 2,
        f"{label}: bridge must update two distinct records",
    )
    _require(
        report_metadata.get("axiom_input_records_count") == len(records),
        f"{label}: committed record count disagrees with the suite",
    )
    aggregation = metadata.get("axiom_result_aggregation")
    _require(
        aggregation == {"strategy": "sum", "entity_ids": ["earner", "non_earner"]},
        f"{label}: suite must sum earner then non-earner",
    )

    return {
        "axiom_entity": metadata.get("axiom_entity"),
        "axiom_entity_id": metadata.get("axiom_entity_id"),
        "axiom_input_records": records,
        "axiom_result_aggregation": metadata.get("axiom_result_aggregation"),
    }


def _single_metadata(report_case: dict[str, Any], label: str) -> dict[str, Any]:
    metadata = report_case.get("metadata")
    _require(isinstance(metadata, dict), f"{label}: metadata is missing")
    inputs = metadata.get("axiom_inputs")
    _require(
        isinstance(inputs, dict) and len(inputs) == 9,
        f"{label}: committed report must carry exactly nine Axiom inputs",
    )
    _require(
        metadata.get("axiom_entity") == "Person"
        and metadata.get("axiom_entity_id") == "recipient",
        f"{label}: Axiom execution entity must be Person[recipient]",
    )
    return {
        "axiom_entity": metadata.get("axiom_entity"),
        "axiom_entity_id": metadata.get("axiom_entity_id"),
        # Replace wholesale from the report. In particular, preserve the
        # executed floating tails 919999.9999999999 / 1839999.9999999998.
        "axiom_inputs": copy.deepcopy(inputs),
    }


def _input_binding(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": EXECUTION_PERIOD,
        "axiom_entity": metadata.get("axiom_entity"),
        "axiom_entity_id": metadata.get("axiom_entity_id"),
        "axiom_inputs": metadata.get("axiom_inputs", {}),
        "axiom_input_records": metadata.get("axiom_input_records", []),
        "axiom_result_aggregation": metadata.get("axiom_result_aggregation"),
    }


def _expanded_compact_case(
    row: dict[str, Any],
    *,
    report: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """Expand one validated compact verdict row for executable replay."""

    execution = row.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("schema_version") == "axiom_oracles.case_execution.v1",
        f"{label}: compact case execution metadata is missing or unversioned",
    )
    metadata = {
        key: copy.deepcopy(value)
        for key, value in execution.items()
        if key != "schema_version"
    }

    def verdicts(field: str) -> list[dict[str, Any]]:
        expanded: list[dict[str, Any]] = []
        for verdict in row.get(field) or []:
            _require(isinstance(verdict, dict), f"{label}: malformed {field} row")
            expanded.append(
                {
                    "concept": verdict.get("c"),
                    "left": verdict.get("l"),
                    "right": verdict.get("x"),
                }
            )
        return expanded

    return {
        "case_id": row.get("id"),
        "right_engine": (report.get("engines") or {}).get("right"),
        "metadata": metadata,
        "matches": verdicts("v"),
        "mismatches": verdicts("m"),
    }


def _committed_case_rows(
    report_path: Path,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Load inline legacy cases or the report's validated bound chunk corpus."""

    inline = report.get("cases")
    _require(isinstance(inline, list), f"{report_path}: cases must be a list")
    if inline:
        return inline

    evidence = validate_suite_evidence(report_path)
    _require(
        evidence.valid
        and evidence.binding == "bound"
        and evidence.reconciliation == "full",
        f"{report_path}: executable cases require valid bound/full evidence: "
        + "; ".join(evidence.defects),
    )
    chunk_dir = report_path.parent / "cases" / str(evidence.suite)
    expanded: list[dict[str, Any]] = []
    for chunk in evidence.chunks:
        try:
            payload = json.loads((chunk_dir / chunk.name).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{chunk_dir / chunk.name}: cannot read chunk: {exc}") from exc
        _require(
            isinstance(payload, list),
            f"{chunk_dir / chunk.name}: expected a compact case array",
        )
        for position, row in enumerate(payload):
            label = f"{evidence.suite}/{chunk.name}[{position}]"
            _require(isinstance(row, dict), f"{label}: compact case is not a mapping")
            expanded.append(
                _expanded_compact_case(row, report=report, label=label)
            )
    return expanded


def _expected_cases(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    couple_suite = {
        str(case.case_id): case for case in dk_child_youth_benefit_couple_cases()
    }
    expected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for spec in REPORT_SPECS:
        report_path = repo_root / str(spec["path"])
        report = _read_json(report_path)
        _require(
            report.get("suite") == spec["suite"],
            f"{report_path}: suite is {report.get('suite')!r}, expected "
            f"{spec['suite']!r}",
        )
        engines = report.get("engines")
        _require(
            isinstance(engines, dict)
            and engines.get("left") == "euromod"
            and engines.get("right") == "axiom",
            f"{report_path}: expected EUROMOD-left/Axiom-right report",
        )
        cases = _committed_case_rows(report_path, report)
        _require(
            len(cases) == spec["case_count"],
            f"{report_path}: expected {spec['case_count']} cases, found {len(cases)}",
        )
        for case_row in cases:
            _require(
                isinstance(case_row, dict), f"{report_path}: case is not a mapping"
            )
            case_id = str(case_row.get("case_id", ""))
            label = f"{spec['suite']}/{case_id or '<missing>'}"
            _require(case_id != "", f"{label}: case_id is missing")
            _require(case_id not in seen_ids, f"duplicate executable case_id {case_id}")
            seen_ids.add(case_id)
            _require(
                case_row.get("right_engine") == "axiom",
                f"{label}: right_engine must be axiom",
            )
            concept, committed_value = _comparison_value(case_row, label)
            _require(
                concept.startswith(f"{spec['program']}#"),
                f"{label}: output {concept!r} is outside {spec['program']}",
            )
            if spec["program"] == COUPLE_PROGRAM:
                metadata = _couple_metadata(
                    case_row,
                    suite_cases=couple_suite,
                    label=label,
                )
            else:
                metadata = _single_metadata(case_row, label)
            binding = _input_binding(metadata)
            expected.append(
                {
                    "suite": spec["suite"],
                    "case_id": case_id,
                    "program": spec["program"],
                    "output": concept,
                    "committed_value": committed_value,
                    "source_report": spec["path"],
                    "input_source": spec["input_source"],
                    "input_sha256": _sha256_bytes(_canonical_json(binding).encode()),
                    "case": Case(
                        case_id=case_id,
                        period=EXECUTION_PERIOD,
                        outputs=(concept,),
                        metadata=metadata,
                    ),
                }
            )
    _require(
        len(expected) == 10, f"expected 10 executable cases, found {len(expected)}"
    )
    return expected


def _source_reports(repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    return [
        {
            "path": str(spec["path"]),
            "sha256": _sha256(repo_root / str(spec["path"])),
        }
        for spec in REPORT_SPECS
    ]


def _resolve_git_commit(repo: Path, ref: str) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise ValueError(
            f"cannot resolve rulespec ref {ref!r} in {repo}: {detail}"
        ) from exc
    sha = process.stdout.strip()
    _require(HEX_40.fullmatch(sha) is not None, f"git returned invalid commit {sha!r}")
    return sha


def _materialize_rulespec_ref(repo: Path, sha: str, destination: Path) -> Path:
    """Archive the exact ``dk/`` tree without mutating the source checkout."""

    try:
        archive = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", sha, "dk"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        raise ValueError(
            f"cannot archive rulespec commit {sha}: {detail or exc}"
        ) from exc
    root = destination / "rulespec-dk"
    root.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(root, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise ValueError(f"cannot materialize rulespec commit {sha}: {exc}") from exc
    _require((root / "dk").is_dir(), f"rulespec commit {sha} has no dk/ tree")
    return root


def _compile_program(
    spec: dict[str, str],
    *,
    rulespec_root: Path,
    engine_binary: Path,
    work_dir: Path,
) -> Path:
    """Compile through the adapter's canonical ``compile-composed`` path."""

    runner = AxiomRulesRunner(
        binary_path=engine_binary,
        program_imports=(spec["program"],),
        generated_program_target=spec["program"],
        rulespec_repo_roots=(rulespec_root,),
        default_entity="Person",
        default_entity_id="recipient",
        prune_unsupported_inputs=True,
    )
    program_path = runner._program_path(work_dir)
    _require(program_path is not None, f"{spec['program']}: adapter made no program")
    # These adapter helpers are the production compile path. Keeping the
    # artifact inside our outer temp directory lets this producer hash and run
    # the exact bytes that _artifact_path compiled.
    return runner._artifact_path(work_dir, program_path)


def _result_value(result: Any, output: str) -> Any:
    if output in result.values:
        return result.values[output]
    local_name = output.rsplit("#", 1)[-1]
    if local_name in result.values:
        return result.values[local_name]
    return None


def _summary(cases: list[dict[str, Any]], engine_matches_pin: bool) -> dict[str, Any]:
    matched = sum(case.get("match") is True for case in cases)
    all_reproduced = (
        len(cases) == 10
        and matched == 10
        and all(not case.get("errors") for case in cases)
    )
    return {
        "program_count": 2,
        "case_count": len(cases),
        "matched_case_count": matched,
        "all_cases_reproduced": all_reproduced,
        "engine_binary_matches_pin": engine_matches_pin,
        "executable": all_reproduced and engine_matches_pin,
    }


def build_reproduction(
    *,
    rulespec_repo: Path = DEFAULT_RULESPEC_ROOT,
    rulespec_ref: str = DEFAULT_RULESPEC_REF,
    engine_binary: Path = DEFAULT_ENGINE_BINARY,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Compile both programs and reproduce all ten committed case values."""

    rulespec_repo = Path(rulespec_repo).expanduser().resolve()
    engine_binary = Path(engine_binary).expanduser().resolve()
    _require(rulespec_repo.is_dir(), f"rulespec checkout is missing: {rulespec_repo}")
    _require(engine_binary.is_file(), f"engine binary is missing: {engine_binary}")
    configured_pin = _configured_engine_pin(repo_root)
    binary_sha = _sha256(engine_binary)
    rulespec_sha = _resolve_git_commit(rulespec_repo, rulespec_ref)
    expected = _expected_cases(repo_root)
    artifact_cases: list[dict[str, Any]] = []
    compiled_artifacts: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="dk-executable-reproduction-") as raw_tmp:
        temp_dir = Path(raw_tmp).resolve()
        exact_root = _materialize_rulespec_ref(
            rulespec_repo,
            rulespec_sha,
            temp_dir / "rulespec-ref",
        )
        for program_spec in PROGRAM_SPECS:
            program = program_spec["program"]
            work_dir = temp_dir / "compile" / program.rsplit("/", 1)[-1]
            work_dir.mkdir(parents=True)
            compiled = _compile_program(
                program_spec,
                rulespec_root=exact_root,
                engine_binary=engine_binary,
                work_dir=work_dir,
            )
            source_path = exact_root / program_spec["source_path"]
            compiled_artifacts.append(
                {
                    "program": program,
                    "source_path": program_spec["source_path"],
                    "source_sha256": _sha256(source_path),
                    "sha256": _sha256(compiled),
                    "byte_count": compiled.stat().st_size,
                    "compile_contract": "compile-composed",
                }
            )
            program_cases = [row for row in expected if row["program"] == program]
            runner = AxiomRulesRunner(
                compiled_artifact_path=compiled,
                binary_path=engine_binary,
                default_entity="Person",
                default_entity_id="recipient",
            )
            results = runner.run_cases(
                [row["case"] for row in program_cases],
                [str(program_cases[0]["output"])],
            )
            _require(
                len(results) == len(program_cases),
                f"{program}: returned {len(results)} results for "
                f"{len(program_cases)} cases",
            )
            for expected_row, result in zip(program_cases, results, strict=True):
                _require(
                    str(result.household_id) == expected_row["case_id"],
                    f"{program}: result order/id drifted at {expected_row['case_id']}",
                )
                reproduced = _result_value(result, str(expected_row["output"]))
                errors = [str(error) for error in result.errors]
                match = not errors and _canonical_json(reproduced) == _canonical_json(
                    expected_row["committed_value"]
                )
                artifact_cases.append(
                    {
                        key: expected_row[key]
                        for key in (
                            "suite",
                            "case_id",
                            "program",
                            "output",
                            "committed_value",
                            "source_report",
                            "input_source",
                            "input_sha256",
                        )
                    }
                    | {
                        "reproduced_value": reproduced,
                        "errors": errors,
                        "match": match,
                    }
                )

    # Restore the report-defined 8 + 1 + 1 ordering after program batching.
    by_id = {case["case_id"]: case for case in artifact_cases}
    artifact_cases = [by_id[row["case_id"]] for row in expected]
    engine_matches_pin = binary_sha == configured_pin
    document = {
        "schema": SCHEMA,
        "program": PROGRAM,
        "generated_by": GENERATED_BY,
        "execution_period": EXECUTION_PERIOD,
        "engine": {
            "binary_sha256": binary_sha,
            "configured_sha256": configured_pin,
            "matches_config_pin": engine_matches_pin,
        },
        "rulespec": {
            "repo": RULESPEC_REPO,
            # Persist the resolved commit as the replay ref. A moving branch
            # name is only a generation-time selector, never receipt identity.
            "ref": rulespec_sha,
            "sha": rulespec_sha,
        },
        "source_reports": _source_reports(repo_root),
        "compiled_artifacts": compiled_artifacts,
        "cases": artifact_cases,
        "summary": _summary(artifact_cases, engine_matches_pin),
    }
    validate_artifact(document, repo_root=repo_root)
    return document


def validate_artifact(
    document: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Validate a committed artifact hermetically and return its derived summary.

    This does not trust stored booleans. It derives the engine-pin match, every
    per-case match, and the final executable value from in-repo configs/reports
    plus the artifact's reproduced values. External engine and RuleSpec
    checkouts are deliberately not needed; the CLI's ``--check`` performs that
    full rerun separately.
    """

    _require(isinstance(document, dict), "executable artifact must be a mapping")
    _require(document.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    _require(document.get("program") == PROGRAM, f"program must be {PROGRAM}")
    _require(
        document.get("generated_by") == GENERATED_BY,
        f"generated_by must be {GENERATED_BY}",
    )
    _require(
        document.get("execution_period") == EXECUTION_PERIOD,
        f"execution_period must be {EXECUTION_PERIOD}",
    )

    configured_pin = _configured_engine_pin(repo_root)
    engine = document.get("engine")
    _require(isinstance(engine, dict), "engine must be a mapping")
    binary_sha = engine.get("binary_sha256")
    _require(
        isinstance(binary_sha, str) and HEX_64.fullmatch(binary_sha) is not None,
        "engine.binary_sha256 must be a lowercase SHA-256",
    )
    _require(
        engine.get("configured_sha256") == configured_pin,
        "engine.configured_sha256 disagrees with the DK comparison configs",
    )
    engine_matches_pin = binary_sha == configured_pin
    _require(
        engine.get("matches_config_pin") is engine_matches_pin,
        "engine.matches_config_pin is not derived from the two SHA-256 values",
    )

    rulespec = document.get("rulespec")
    _require(isinstance(rulespec, dict), "rulespec must be a mapping")
    _require(
        rulespec.get("repo") == RULESPEC_REPO, f"rulespec.repo must be {RULESPEC_REPO}"
    )
    _require(
        isinstance(rulespec.get("sha"), str)
        and HEX_40.fullmatch(rulespec["sha"]) is not None,
        "rulespec.sha must be a lowercase 40-character Git SHA",
    )
    rulespec_sha = rulespec["sha"]
    _require(
        rulespec.get("ref") == rulespec_sha,
        "rulespec.ref must equal the recorded rulespec.sha commit",
    )

    _require(
        document.get("source_reports") == _source_reports(repo_root),
        "source_reports do not match the committed DK reports and SHA-256s",
    )
    compiled = document.get("compiled_artifacts")
    _require(
        isinstance(compiled, list) and len(compiled) == len(PROGRAM_SPECS),
        "compiled_artifacts must contain exactly the two DK programs",
    )
    expected_programs = {
        (spec["program"], spec["source_path"]) for spec in PROGRAM_SPECS
    }
    actual_programs: set[tuple[str, str]] = set()
    for row in compiled:
        _require(isinstance(row, dict), "compiled artifact row must be a mapping")
        actual_programs.add((str(row.get("program")), str(row.get("source_path"))))
        for field in ("source_sha256", "sha256"):
            digest = row.get(field)
            _require(
                isinstance(digest, str) and HEX_64.fullmatch(digest) is not None,
                f"compiled artifact {row.get('program')}: {field} is invalid",
            )
        _require(
            isinstance(row.get("byte_count"), int) and row["byte_count"] > 0,
            f"compiled artifact {row.get('program')}: byte_count is invalid",
        )
        _require(
            row.get("compile_contract") == "compile-composed",
            f"compiled artifact {row.get('program')}: wrong compile contract",
        )
    _require(
        actual_programs == expected_programs, "compiled program/source set drifted"
    )

    expected_cases = _expected_cases(repo_root)
    cases = document.get("cases")
    _require(
        isinstance(cases, list) and len(cases) == 10,
        "cases must contain exactly 10 rows",
    )
    seen_ids: set[str] = set()
    for actual, expected in zip(cases, expected_cases, strict=True):
        _require(isinstance(actual, dict), "executable case row must be a mapping")
        case_id = actual.get("case_id")
        _require(isinstance(case_id, str) and case_id, "case_id must be non-empty")
        _require(case_id not in seen_ids, f"duplicate executable case_id {case_id}")
        seen_ids.add(case_id)
        for field in (
            "suite",
            "case_id",
            "program",
            "output",
            "source_report",
            "input_source",
            "input_sha256",
        ):
            _require(
                actual.get(field) == expected[field],
                f"{case_id}: {field} drifted from committed case inputs",
            )
        _require(
            _canonical_json(actual.get("committed_value"))
            == _canonical_json(expected["committed_value"]),
            f"{case_id}: committed_value drifted (including JSON numeric type)",
        )
        errors = actual.get("errors")
        _require(
            isinstance(errors, list)
            and all(isinstance(error, str) for error in errors),
            f"{case_id}: errors must be a list of strings",
        )
        reproduced = actual.get("reproduced_value")
        _canonical_json(reproduced)
        derived_match = not errors and _canonical_json(reproduced) == _canonical_json(
            expected["committed_value"]
        )
        _require(
            actual.get("match") is derived_match,
            f"{case_id}: match is not derived by exact JSON numeric equality",
        )

    derived_summary = _summary(cases, engine_matches_pin)
    _require(
        document.get("summary") == derived_summary,
        "summary is not derived from the ten cases and configured engine pin",
    )
    return derived_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Recompile, rerun, and fail on drift."
    )
    parser.add_argument("--artifact", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument(
        "--rulespec-ref",
        default=None,
        help=(
            "Generation-time RuleSpec selector (default: main). During --check, "
            "the recorded commit is replayed; an explicit selector must resolve "
            "to that commit."
        ),
    )
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE_BINARY)
    args = parser.parse_args(argv)

    artifact_path = args.artifact.expanduser()
    committed: dict[str, Any] | None = None
    rulespec_ref = args.rulespec_ref or DEFAULT_RULESPEC_REF
    if args.check:
        if not artifact_path.exists():
            print(f"missing executable artifact: {artifact_path}", file=sys.stderr)
            return 1
        try:
            committed = _read_json(artifact_path)
            recorded_ref = committed["rulespec"]["sha"]
            _require(
                isinstance(recorded_ref, str)
                and HEX_40.fullmatch(recorded_ref) is not None,
                "rulespec.sha must be a lowercase 40-character Git SHA",
            )
            if args.rulespec_ref is not None:
                selected_commit = _resolve_git_commit(
                    args.rulespec_root.expanduser().resolve(), args.rulespec_ref
                )
                _require(
                    selected_commit == recorded_ref,
                    "--rulespec-ref resolves to a different commit than the receipt: "
                    f"{selected_commit} != {recorded_ref}",
                )
            rulespec_ref = recorded_ref
        except (KeyError, TypeError, ValueError) as exc:
            print(f"invalid executable artifact: {exc}", file=sys.stderr)
            return 1

    try:
        reproduced = build_reproduction(
            rulespec_repo=args.rulespec_root,
            rulespec_ref=rulespec_ref,
            engine_binary=args.engine_binary,
            repo_root=REPO_ROOT,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"executable reproduction failed: {exc}", file=sys.stderr)
        return 1

    rendered = _render(reproduced)
    if args.check:
        assert committed is not None
        try:
            validate_artifact(committed, repo_root=REPO_ROOT)
        except ValueError as exc:
            print(f"invalid executable artifact: {exc}", file=sys.stderr)
            return 1
        if artifact_path.read_text() != rendered:
            print(
                "executable reproduction drifted — regenerate with "
                "`python scripts/executable_reproduction.py`",
                file=sys.stderr,
            )
            return 1
        summary = reproduced["summary"]
        print(
            "executable reproduction up to date: "
            f"{summary['matched_case_count']}/{summary['case_count']} exact JSON "
            "numeric equality, "
            f"executable={str(summary['executable']).lower()}"
        )
        return 0

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(rendered)
    summary = reproduced["summary"]
    print(f"wrote {artifact_path}")
    print(
        f"reproduced {summary['matched_case_count']}/{summary['case_count']} "
        "cases with exact JSON numeric equality; "
        f"executable={str(summary['executable']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
