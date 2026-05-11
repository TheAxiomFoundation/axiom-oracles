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

from ...comparison.mappings import engine_targets_for_concepts
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from ...core.case import Case


SubprocessRun = Callable[..., subprocess.CompletedProcess[str]]


AXIOM_INPUTS_METADATA_KEY = "axiom_inputs"
AXIOM_RELATIONS_METADATA_KEY = "axiom_relations"
AXIOM_ENTITY_ID_METADATA_KEY = "axiom_entity_id"
AXIOM_ENTITY_METADATA_KEY = "axiom_entity"


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
            artifact_path = self._artifact_path(Path(temp_dir))
            results = []
            for case in cases:
                results.append(self._run_case(case, output_targets, artifact_path))
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

    def _artifact_path(self, temp_dir: Path) -> Path:
        if self.compiled_artifact_path is not None:
            return self.compiled_artifact_path
        if self.program_path is None:
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
                str(self.program_path),
                "--output",
                str(artifact_path),
            ],
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
    ) -> EngineResult:
        request = self._execution_request(case, output_targets)
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

    def _execution_request(self, case: Case, outputs: list[str]) -> dict[str, Any]:
        period = _period_for_case(case)
        entity_id = str(case.metadata.get(AXIOM_ENTITY_ID_METADATA_KEY) or "")
        if not entity_id:
            entity_id = self.default_entity_id
        return {
            "mode": self.mode,
            "dataset": {
                "inputs": self._input_records(case, period, entity_id),
                "relations": self._relation_records(case, period),
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
        records = []
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
