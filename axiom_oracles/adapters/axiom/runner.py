from __future__ import annotations

import json
import os
import subprocess
import tempfile
from calendar import monthrange
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from ...comparison.mappings import engine_targets_for_concepts
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from ...core.case import Case


SubprocessRun = Callable[..., subprocess.CompletedProcess[str]]


AXIOM_INPUTS_METADATA_KEY = "axiom_inputs"
AXIOM_INPUT_RECORDS_METADATA_KEY = "axiom_input_records"
AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY = "axiom_input_record_overlays"
AXIOM_RESULT_SELECTION_METADATA_KEY = "axiom_result_selection"
AXIOM_RELATIONS_METADATA_KEY = "axiom_relations"
AXIOM_ENTITY_ID_METADATA_KEY = "axiom_entity_id"
AXIOM_ENTITY_METADATA_KEY = "axiom_entity"
AXIOM_RULESPEC_REPO_ROOTS_ENV = "AXIOM_RULESPEC_REPO_ROOTS"


class AxiomRulesRunner(EngineAdapter):
    """Adapter for executing Axiom RuleSpec programs."""

    name = "axiom"

    def __init__(
        self,
        *,
        program_path: str | Path | None = None,
        compiled_artifact_path: str | Path | None = None,
        binary_path: str | Path | None = None,
        default_entity_id: str = "tax_unit",
        default_entity: str = "TaxUnit",
        mode: str = "explain",
        program_imports: tuple[str, ...] = (),
        program_rules: tuple[Mapping[str, Any], ...] = (),
        rulespec_repo_roots: tuple[str | Path, ...] = (),
        prune_unsupported_inputs: bool = False,
        subprocess_run: SubprocessRun = subprocess.run,
    ) -> None:
        self.program_path = Path(program_path).expanduser() if program_path else None
        self.compiled_artifact_path = (
            Path(compiled_artifact_path).expanduser()
            if compiled_artifact_path
            else None
        )
        self.binary_path = _resolve_binary_path(binary_path, self.program_path)
        self.default_entity_id = default_entity_id
        self.default_entity = default_entity
        self.mode = mode
        self.program_imports = tuple(program_imports)
        self.program_rules = tuple(program_rules)
        self.rulespec_repo_roots = tuple(
            str(Path(root).expanduser()) for root in rulespec_repo_roots
        )
        self.prune_unsupported_inputs = prune_unsupported_inputs
        self._subprocess_run = subprocess_run

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        if not cases:
            return []
        requested_outputs = variables or list(cases[0].outputs)
        output_targets = _output_targets(requested_outputs)
        with tempfile.TemporaryDirectory(prefix="axiom-oracles-") as temp_dir:
            temp_path = Path(temp_dir)
            program_path = self._program_path(temp_path)
            artifact_path = self._artifact_path(temp_path, program_path)
            allowed_program_refs = (
                _allowed_program_refs_from_artifact(artifact_path)
                if self.prune_unsupported_inputs
                else None
            )
            results = []
            for case in cases:
                results.append(
                    self._run_case(
                        case,
                        output_targets,
                        artifact_path,
                        allowed_program_refs=allowed_program_refs,
                    )
                )
            return results

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise RuntimeError(
            "Axiom RuleSpec comparisons require Case inputs with "
            "metadata['axiom_inputs']; household projection is not implemented."
        )

    def _program_path(self, temp_dir: Path) -> Path | None:
        if self.program_path is not None:
            return self.program_path
        if not self.program_imports:
            return None
        program_path = temp_dir / "generated-program.yaml"
        program_path.write_text(
            yaml.safe_dump(
                {
                    "format": "rulespec/v1",
                    "imports": list(self.program_imports),
                    "rules": [dict(rule) for rule in self.program_rules],
                },
                sort_keys=False,
            )
        )
        return program_path

    def _artifact_path(self, temp_dir: Path, program_path: Path | None) -> Path:
        if self.compiled_artifact_path is not None:
            return self.compiled_artifact_path
        if program_path is None:
            raise RuntimeError(
                "Axiom comparisons require --axiom-program or "
                "AXIOM_RULESPEC_PROGRAM."
            )
        artifact_path = temp_dir / "program.compiled.json"
        process = self._subprocess_run(
            [
                str(self.binary_path),
                "compile",
                "--program",
                str(program_path),
                "--output",
                str(artifact_path),
            ],
            env=self._compile_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            stderr = process.stderr.strip() or "Axiom RuleSpec compile failed"
            raise RuntimeError(stderr)
        return artifact_path

    def _run_case(
        self,
        case: Case,
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
    ) -> EngineResult:
        period = _period_for_case(case)
        input_record_overlays = _case_input_record_overlays(case, period)
        if input_record_overlays:
            candidate_results = [
                self._run_case_once(
                    case,
                    output_targets,
                    artifact_path,
                    allowed_program_refs=allowed_program_refs,
                    input_record_overlay=overlay,
                )
                for overlay in input_record_overlays
            ]
            return _select_candidate_result(self.name, case, candidate_results)
        return self._run_case_once(
            case,
            output_targets,
            artifact_path,
            allowed_program_refs=allowed_program_refs,
        )

    def _run_case_once(
        self,
        case: Case,
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        input_record_overlay: list[dict[str, Any]] | None = None,
    ) -> EngineResult:
        request = self._execution_request(
            case,
            output_targets,
            allowed_program_refs=allowed_program_refs,
            input_record_overlay=input_record_overlay,
        )
        process = self._subprocess_run(
            [
                str(self.binary_path),
                "run-compiled",
                "--artifact",
                str(artifact_path),
            ],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            error = process.stderr.strip() or "Axiom RuleSpec execution failed"
            return EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values={},
                errors=(error,),
            )
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            return EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values={},
                errors=(f"Axiom RuleSpec execution emitted invalid JSON: {exc}",),
                raw=process.stdout,
            )
        values = _values_from_response(payload)
        return EngineResult(
            engine=self.name,
            household_id=case.case_id,
            values=values,
            raw=payload,
        )

    def _execution_request(
        self,
        case: Case,
        outputs: list[str],
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        input_record_overlay: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        period = _period_for_case(case)
        entity_id = str(case.metadata.get(AXIOM_ENTITY_ID_METADATA_KEY) or "")
        if not entity_id:
            entity_id = self.default_entity_id
        input_records = self._input_records(case, period, entity_id)
        if input_record_overlay:
            input_records = _apply_input_record_overlay(
                input_records,
                input_record_overlay,
            )
        if allowed_program_refs is not None:
            input_records = [
                record
                for record in input_records
                if allowed_program_refs.accepts_input(str(record["name"]))
            ]
        relation_records = self._relation_records(case, period)
        if allowed_program_refs is not None:
            relation_records = [
                record
                for record in relation_records
                if allowed_program_refs.accepts_relation(str(record["name"]))
            ]
        return {
            "mode": self.mode,
            "dataset": {
                "inputs": input_records,
                "relations": relation_records,
            },
            "queries": [
                {
                    "entity_id": entity_id,
                    "period": period,
                    "outputs": outputs,
                }
            ],
        }

    def _input_records(
        self,
        case: Case,
        period: dict[str, str],
        default_entity_id: str,
    ) -> list[dict[str, Any]]:
        records = _explicit_input_records(case, period)
        for name, value in _case_axiom_inputs(case).items():
            records.append(
                {
                    "name": name,
                    "entity": str(
                        case.metadata.get(AXIOM_ENTITY_METADATA_KEY)
                        or self.default_entity
                    ),
                    "entity_id": default_entity_id,
                    "interval": _interval(period),
                    "value": _scalar_value(value),
                }
            )
        return records

    def _compile_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if AXIOM_RULESPEC_REPO_ROOTS_ENV not in env:
            roots = self.rulespec_repo_roots or _default_rulespec_repo_roots()
            if roots:
                env[AXIOM_RULESPEC_REPO_ROOTS_ENV] = os.pathsep.join(
                    str(root) for root in roots
                )
        return env

    def _relation_records(
        self,
        case: Case,
        period: dict[str, str],
    ) -> list[dict[str, Any]]:
        raw_relations = case.metadata.get(AXIOM_RELATIONS_METADATA_KEY, [])
        if isinstance(raw_relations, Mapping):
            raw_relations = [
                {"name": name, "tuple": tuple_value}
                for name, tuples in raw_relations.items()
                for tuple_value in _relation_tuples(tuples)
            ]
        if not isinstance(raw_relations, list | tuple):
            raise RuntimeError("metadata['axiom_relations'] must be a list or mapping.")
        records = []
        for relation in raw_relations:
            if not isinstance(relation, Mapping):
                raise RuntimeError("Axiom relation records must be mappings.")
            records.append(
                {
                    "name": str(relation["name"]),
                    "tuple": [str(value) for value in relation["tuple"]],
                    "interval": _interval(period),
                }
            )
        return records


def _resolve_binary_path(
    binary_path: str | Path | None,
    program_path: Path | None,
) -> Path:
    if binary_path:
        return Path(binary_path).expanduser()
    env_binary = os.environ.get("AXIOM_RULES_ENGINE_BINARY")
    if env_binary:
        return Path(env_binary).expanduser()
    candidates = []
    if program_path is not None:
        for ancestor in program_path.resolve().parents:
            candidates.append(
                ancestor / "axiom-rules-engine/target/debug/axiom-rules-engine"
            )
            candidates.append(ancestor / "axiom-rules-engine/target/debug/axiom-rules")
    candidates.extend(
        [
            Path.home()
            / "TheAxiomFoundation/axiom-rules-engine/target/debug/axiom-rules-engine",
            Path.home()
            / "TheAxiomFoundation/axiom-rules-engine/target/debug/axiom-rules",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path("axiom-rules")


def _output_targets(variables: list[str] | None) -> list[str]:
    if variables is None:
        return []
    targets = engine_targets_for_concepts(variables, "axiom")
    return targets or list(variables)


def _explicit_input_records(
    case: Case,
    period: dict[str, str],
) -> list[dict[str, Any]]:
    raw_records = case.metadata.get(AXIOM_INPUT_RECORDS_METADATA_KEY, [])
    return _normalize_input_records(
        raw_records,
        period,
        "metadata['axiom_input_records']",
    )


def _case_input_record_overlays(
    case: Case,
    period: dict[str, str],
) -> list[list[dict[str, Any]]]:
    raw_overlays = case.metadata.get(AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY, [])
    if raw_overlays is None:
        return []
    if not isinstance(raw_overlays, list | tuple):
        raise RuntimeError(
            "metadata['axiom_input_record_overlays'] must be a list."
        )
    return [
        _normalize_input_records(
            raw_overlay,
            period,
            f"metadata['axiom_input_record_overlays'][{index}]",
        )
        for index, raw_overlay in enumerate(raw_overlays)
    ]


def _normalize_input_records(
    raw_records: Any,
    period: dict[str, str],
    label: str,
) -> list[dict[str, Any]]:
    if raw_records is None:
        return []
    if not isinstance(raw_records, list | tuple):
        raise RuntimeError(f"{label} must be a list.")
    records = []
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise RuntimeError(f"{label} records must be mappings.")
        record = dict(raw_record)
        if "name" not in record:
            raise RuntimeError(f"{label} records must include a name.")
        if "entity" not in record:
            raise RuntimeError(f"{label} records must include an entity.")
        if "entity_id" not in record:
            raise RuntimeError(f"{label} records must include an entity_id.")
        if "value" not in record:
            raise RuntimeError(f"{label} records must include a value.")
        record["name"] = str(record["name"])
        record["entity"] = str(record["entity"])
        record["entity_id"] = str(record["entity_id"])
        if "interval" not in record:
            record["interval"] = _interval(period)
        if not isinstance(record["value"], Mapping) or "kind" not in record["value"]:
            record["value"] = _scalar_value(record["value"])
        records.append(record)
    return records


def _apply_input_record_overlay(
    base_records: list[dict[str, Any]],
    overlay_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    ordered_keys = []
    for record in [*base_records, *overlay_records]:
        key = _input_record_key(record)
        if key not in by_key:
            ordered_keys.append(key)
        by_key[key] = dict(record)
    return [by_key[key] for key in ordered_keys]


def _input_record_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    interval = record.get("interval", {})
    interval_key = json.dumps(interval, sort_keys=True)
    return (
        str(record["name"]),
        str(record["entity"]),
        str(record["entity_id"]),
        interval_key,
    )


def _select_candidate_result(
    engine_name: str,
    case: Case,
    candidates: list[EngineResult],
) -> EngineResult:
    raw_selection = case.metadata.get(AXIOM_RESULT_SELECTION_METADATA_KEY)
    if not isinstance(raw_selection, Mapping):
        return EngineResult(
            engine=engine_name,
            household_id=case.case_id,
            values={},
            errors=(
                "metadata['axiom_result_selection'] is required when "
                "metadata['axiom_input_record_overlays'] is provided.",
            ),
            raw=_candidate_raw(candidates),
        )
    strategy = str(raw_selection.get("strategy", ""))
    output = str(raw_selection.get("output", ""))
    if strategy not in {"min", "max"}:
        return EngineResult(
            engine=engine_name,
            household_id=case.case_id,
            values={},
            errors=("metadata['axiom_result_selection'].strategy must be min or max.",),
            raw=_candidate_raw(candidates),
        )
    if not output:
        return EngineResult(
            engine=engine_name,
            household_id=case.case_id,
            values={},
            errors=("metadata['axiom_result_selection'].output is required.",),
            raw=_candidate_raw(candidates),
        )

    valid_candidates = [
        (index, result)
        for index, result in enumerate(candidates)
        if not result.errors and _is_numeric_value(result.values.get(output))
    ]
    if not valid_candidates:
        candidate_errors = tuple(
            error for result in candidates for error in result.errors
        )
        return EngineResult(
            engine=engine_name,
            household_id=case.case_id,
            values={},
            errors=(
                f"Axiom candidate selection found no numeric '{output}' result.",
                *candidate_errors,
            ),
            raw=_candidate_raw(candidates),
        )

    selector = min if strategy == "min" else max
    selected_index, selected = selector(
        valid_candidates,
        key=lambda item: item[1].values[output],
    )
    return EngineResult(
        engine=engine_name,
        household_id=case.case_id,
        values=selected.values,
        raw={
            "selection": dict(raw_selection),
            "selected_candidate": selected_index,
            "candidates": _candidate_raw(candidates),
        },
        errors=selected.errors,
    )


def _candidate_raw(candidates: list[EngineResult]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "values": result.values,
            "errors": list(result.errors),
            "raw": result.raw,
        }
        for index, result in enumerate(candidates)
    ]


def _is_numeric_value(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _case_axiom_inputs(case: Case) -> dict[str, Any]:
    raw_inputs = case.metadata.get(AXIOM_INPUTS_METADATA_KEY, {})
    if raw_inputs and not isinstance(raw_inputs, Mapping):
        raise RuntimeError("metadata['axiom_inputs'] must be a mapping.")
    inputs = dict(raw_inputs)
    for key, value in case.facts.items():
        if _looks_like_axiom_input_ref(key):
            inputs[str(key)] = value
    return inputs


def _looks_like_axiom_input_ref(value: Any) -> bool:
    text = str(value)
    return ":" in text and "#input." in text


def _period_for_case(case: Case) -> dict[str, str]:
    text = str(case.period)
    year = int(text.split("-", maxsplit=1)[0])
    if len(text) >= 7 and text[4] == "-":
        month = int(text[5:7])
        last_day = monthrange(year, month)[1]
        return {
            "period_kind": "month",
            "start": date(year, month, 1).isoformat(),
            "end": date(year, month, last_day).isoformat(),
            "name": f"{year:04d}-{month:02d}",
        }
    return {
        "period_kind": "tax_year",
        "start": date(year, 1, 1).isoformat(),
        "end": date(year, 12, 31).isoformat(),
        "name": str(year),
    }


def _interval(period: Mapping[str, str]) -> dict[str, str]:
    return {"start": period["start"], "end": period["end"]}


def _scalar_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"kind": "integer", "value": value}
    if isinstance(value, float):
        return {"kind": "decimal", "value": str(value)}
    if isinstance(value, date):
        return {"kind": "date", "value": value.isoformat()}
    return {"kind": "text", "value": str(value)}


def _relation_tuples(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        if not value:
            return []
        if all(isinstance(item, list | tuple) for item in value):
            return list(value)
        return [value]
    return [[value]]


def _values_from_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for result in payload.get("results", []):
        if not isinstance(result, Mapping):
            continue
        for output_key, output in result.get("outputs", {}).items():
            if not isinstance(output, Mapping):
                continue
            values[str(output_key)] = _output_value(output)
    return values


def _output_value(output: Mapping[str, Any]) -> Any:
    if output.get("kind") == "judgment":
        outcome = output.get("outcome")
        if outcome == "holds":
            return True
        if outcome == "not_holds":
            return False
        return None
    value = output.get("value")
    if isinstance(value, Mapping):
        kind = value.get("kind")
        raw = value.get("value")
        if kind == "bool":
            return bool(raw)
        if kind == "integer":
            return int(raw)
        if kind == "decimal":
            return float(raw)
        return raw
    return value


class _AllowedProgramRefs:
    def __init__(
        self,
        *,
        input_slots: set[str],
        public_values: set[str],
        relation_names: set[str],
    ) -> None:
        self.input_slots = input_slots
        self.public_values = public_values
        self.relation_names = relation_names

    def accepts_input(self, reference: str) -> bool:
        if reference in self.public_values:
            return True
        if "#" not in reference:
            return not self.public_values
        _, fragment = reference.split("#", maxsplit=1)
        if fragment.startswith("input."):
            return fragment.removeprefix("input.") in self.input_slots
        return fragment in self.input_slots

    def accepts_relation(self, reference: str) -> bool:
        if reference in self.relation_names:
            return True
        if "#" not in reference:
            return not self.relation_names
        _, fragment = reference.split("#", maxsplit=1)
        if fragment.startswith("relation."):
            return fragment.removeprefix("relation.") in self.relation_names
        return fragment in self.relation_names


def _allowed_program_refs_from_artifact(artifact_path: Path) -> _AllowedProgramRefs:
    payload = json.loads(artifact_path.read_text())
    program = payload.get("program", {})
    input_slots: set[str] = set()
    public_values: set[str] = set()
    relation_names: set[str] = set()
    for derived in program.get("derived", []):
        if not isinstance(derived, Mapping):
            continue
        if isinstance(derived.get("id"), str):
            public_values.add(derived["id"])
        _collect_input_slots(derived.get("expr"), input_slots)
    for parameter in program.get("parameters", []):
        if not isinstance(parameter, Mapping):
            continue
        if isinstance(parameter.get("id"), str):
            public_values.add(parameter["id"])
        indexed_by = parameter.get("indexed_by")
        if isinstance(indexed_by, str) and indexed_by:
            input_slots.add(indexed_by)
    for relation in program.get("relations", []):
        if not isinstance(relation, Mapping):
            continue
        name = relation.get("name")
        if isinstance(name, str) and name:
            relation_names.add(name)
    return _AllowedProgramRefs(
        input_slots=input_slots,
        public_values=public_values,
        relation_names=relation_names,
    )


def _collect_input_slots(node: Any, slots: set[str]) -> None:
    if not isinstance(node, Mapping):
        if isinstance(node, list | tuple):
            for item in node:
                _collect_input_slots(item, slots)
        return
    if node.get("kind") == "input" and isinstance(node.get("name"), str):
        slots.add(node["name"])
    for value in node.values():
        _collect_input_slots(value, slots)


def _default_rulespec_repo_roots() -> tuple[Path, ...]:
    candidate = Path.home() / "TheAxiomFoundation"
    if candidate.exists():
        return (candidate,)
    return ()
