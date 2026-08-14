from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from calendar import monthrange
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from ...comparison.mappings import engine_targets_for_concepts
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from ...core.case import Case
from ...engine_compat import (
    StagedRootCache,
    compile_with_engine,
    explicit_engine_roots,
    import_prefixes,
)


SubprocessRun = Callable[..., subprocess.CompletedProcess[str]]


AXIOM_INPUTS_METADATA_KEY = "axiom_inputs"
AXIOM_INPUT_RECORDS_METADATA_KEY = "axiom_input_records"
AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY = "axiom_input_record_overlays"
AXIOM_RESULT_SELECTION_METADATA_KEY = "axiom_result_selection"
AXIOM_RESULT_AGGREGATION_METADATA_KEY = "axiom_result_aggregation"
AXIOM_RELATIONS_METADATA_KEY = "axiom_relations"
AXIOM_ENTITY_ID_METADATA_KEY = "axiom_entity_id"
AXIOM_ENTITY_METADATA_KEY = "axiom_entity"
AXIOM_ALIAS_QUALIFIED_INPUTS_METADATA_KEY = "axiom_alias_qualified_inputs"
AXIOM_RULESPEC_REPO_ROOTS_ENV = "AXIOM_RULESPEC_REPO_ROOTS"
FLOAT_ZERO_TOLERANCE = 1e-9


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
        generated_program_target: str | None = None,
        rulespec_repo_roots: tuple[str | Path, ...] = (),
        prune_unsupported_inputs: bool = False,
        record_all_outputs: bool = False,
        batch_size: int = 5_000,
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
        self.generated_program_target = generated_program_target
        self.rulespec_repo_roots = tuple(
            str(Path(root).expanduser()) for root in rulespec_repo_roots
        )
        self.prune_unsupported_inputs = prune_unsupported_inputs
        self.record_all_outputs = record_all_outputs
        self.batch_size = batch_size
        self._subprocess_run = subprocess_run
        self._staged_roots: StagedRootCache | None = None

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
            # Aliases cover per-case result-selection outputs too: candidate
            # selection reads its (often qualified) output id off candidate
            # values before the final remap, so bare-id artifact values must
            # be re-keyed at the candidate level (#296).
            output_aliases = _output_aliases_from_artifact(
                list(
                    dict.fromkeys([*output_targets, *_result_selection_outputs(cases)])
                ),
                artifact_path,
            )
            execution_targets = [
                output_aliases.get(output, output) for output in output_targets
            ]
            allowed_program_refs = (
                _allowed_program_refs_from_artifact(artifact_path)
                if self.prune_unsupported_inputs
                else None
            )
            execution_targets = _execution_output_targets(
                execution_targets,
                cases,
                allowed_program_refs,
                output_aliases=output_aliases,
            )
            # Keep the compared outputs separate from full-evidence closure
            # outputs. Cross-entity aggregation applies only to the requested
            # comparison surface; per-entity intermediates remain component
            # evidence and must not be presented as household sums.
            aggregate_output_targets = tuple(execution_targets)
            if self.record_all_outputs:
                # Full-evidence mode: also query every derived rule in the
                # compared concepts' dependency closure, so each case
                # records the complete computation chain (intermediates
                # included). Rules OUTSIDE the closure are not queried —
                # forcing them evaluates program surfaces whose inputs the
                # projector legitimately prunes (e.g. citizenship modules)
                # and fails every case with missing-input errors.
                known = set(execution_targets)
                case_entity = str(
                    cases[0].metadata.get(AXIOM_ENTITY_METADATA_KEY)
                    or self.default_entity
                )
                execution_targets = execution_targets + [
                    name
                    for name in _derived_closure_ids(
                        artifact_path,
                        execution_targets,
                        entity=case_entity,
                    )
                    if name not in known
                ]
            results = self._run_cases(
                cases,
                execution_targets,
                artifact_path,
                allowed_program_refs=allowed_program_refs,
                output_aliases=output_aliases,
                aggregate_output_targets=aggregate_output_targets,
            )
            return [_remap_output_aliases(result, output_aliases) for result in results]

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
        program_path = _generated_program_path(
            temp_dir,
            self.generated_program_target,
        )
        program_path.parent.mkdir(parents=True, exist_ok=True)
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
                "Axiom comparisons require --axiom-program or AXIOM_RULESPEC_PROGRAM."
            )
        artifact_path = temp_dir / "program.compiled.json"
        program_doc = self._load_program_doc(program_path)
        imports = [
            entry
            for entry in (program_doc.get("imports") or [])
            if isinstance(entry, str)
        ]
        # Post-hard-cut engines refuse a program outside every configured root
        # under `compile`; out-of-root programs (this adapter's generated
        # oracle bridge, compose output) must be `module.kind: composition`
        # and go through `compile-composed`. The generated program is emitted
        # in legacy shape for old engines — write the composition-form twin
        # for the new-engine attempt.
        composed = (program_doc.get("module") or {}).get("kind") == "composition"
        compile_program_path = Path(program_path)
        legacy_program_path = Path(program_path)
        if not composed and self.program_imports:
            compile_program_path = temp_dir / "generated-program.composed.yaml"
            compile_program_path.write_text(
                yaml.safe_dump(
                    {
                        "format": program_doc.get("format", "rulespec/v1"),
                        "module": {
                            "kind": "composition",
                            "summary": (
                                "axiom-oracles generated oracle-bridge program "
                                f"({self.generated_program_target or 'generated'})"
                            ),
                        },
                        "imports": program_doc.get("imports") or [],
                        "rules": program_doc.get("rules") or [],
                    },
                    sort_keys=False,
                )
            )
            composed = True
        roots = explicit_engine_roots(
            list(self.rulespec_repo_roots) or list(_default_rulespec_repo_roots()),
            program=None if composed else compile_program_path,
        )
        # The engine requires a root's top level to hold only jurisdiction
        # dirs; upstream rulespec-us also carries programs/ and repo plumbing,
        # so compile against staged filtered copies. An atomic in-root program
        # compiles as its staged twin so program and root stay consistent.
        jurisdictions = import_prefixes(imports)
        staged_roots: list[Path] = []
        if roots and jurisdictions:
            if self._staged_roots is None:
                self._staged_roots = StagedRootCache()
            for root in roots:
                # A discovered root that carries none of the requested
                # jurisdictions would stage as an empty directory, and the
                # hard-cut engine contract rejects empty roots outright
                # ("must contain a direct matching jurisdiction"). Skip it:
                # sibling-jurisdiction checkouts under a shared roots dir are
                # not part of this program's universe. (The legacy compile
                # path tolerated them, which is why this only bites pinned
                # post-hard-cut engines.)
                if not any((root / name).is_dir() for name in jurisdictions):
                    continue
                staged = self._staged_roots.staged(root, jurisdictions)
                staged_roots.append(staged)
                if not composed:
                    try:
                        relative = compile_program_path.resolve().relative_to(
                            root.resolve()
                        )
                    except ValueError:
                        continue
                    staged_twin = staged / relative
                    if staged_twin.exists():
                        compile_program_path = staged_twin
        compile_with_engine(
            self.binary_path,
            compile_program_path,
            artifact_path,
            roots=staged_roots or roots,
            composed=composed,
            env=self._compile_env(),
            legacy_program=legacy_program_path,
            run=self._subprocess_run,
        )
        return artifact_path

    @staticmethod
    def _load_program_doc(program_path: Path) -> dict:
        try:
            doc = yaml.safe_load(Path(program_path).read_text())
        except (OSError, yaml.YAMLError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _run_case(
        self,
        case: Case,
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        output_aliases: Mapping[str, str] | None = None,
        aggregate_output_targets: tuple[str, ...] = (),
    ) -> EngineResult:
        period = _period_for_case(case)
        input_record_overlays = _case_input_record_overlays(case, period)
        if input_record_overlays:
            candidate_results = [
                _remap_output_aliases(
                    self._run_case_once(
                        case,
                        output_targets,
                        artifact_path,
                        allowed_program_refs=allowed_program_refs,
                        input_record_overlay=overlay,
                        aggregate_output_targets=aggregate_output_targets,
                    ),
                    output_aliases or {},
                )
                for overlay in input_record_overlays
            ]
            return _select_candidate_result(self.name, case, candidate_results)
        return self._run_case_once(
            case,
            output_targets,
            artifact_path,
            allowed_program_refs=allowed_program_refs,
            aggregate_output_targets=aggregate_output_targets,
        )

    def _run_cases(
        self,
        cases: list[Case],
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        output_aliases: Mapping[str, str] | None = None,
        aggregate_output_targets: tuple[str, ...] = (),
    ) -> list[EngineResult]:
        if not output_targets:
            return [
                EngineResult(engine=self.name, household_id=case.case_id, values={})
                for case in cases
            ]
        # Entity aggregation needs more than one query result per Case. Keep
        # those cases on the single-case request path, where the response can
        # preserve and sum the ordered component results. The ordinary batch
        # path intentionally retains its one-query-result-per-case contract.
        if any(_case_result_aggregation(case) is not None for case in cases):
            return [
                self._run_case(
                    case,
                    output_targets,
                    artifact_path,
                    allowed_program_refs=allowed_program_refs,
                    output_aliases=output_aliases,
                    aggregate_output_targets=aggregate_output_targets,
                )
                for case in cases
            ]
        overlays_by_case = [
            _case_input_record_overlays(case, _period_for_case(case)) for case in cases
        ]
        if not any(overlays_by_case):
            return self._run_cases_once(
                cases,
                output_targets,
                artifact_path,
                allowed_program_refs=allowed_program_refs,
            )

        overlay_count = len(overlays_by_case[0])
        if not overlay_count or any(
            len(overlays) != overlay_count for overlays in overlays_by_case
        ):
            return [
                self._run_case(
                    case,
                    output_targets,
                    artifact_path,
                    allowed_program_refs=allowed_program_refs,
                    output_aliases=output_aliases,
                    aggregate_output_targets=aggregate_output_targets,
                )
                for case in cases
            ]

        candidate_batches = [
            self._run_cases_once(
                cases,
                output_targets,
                artifact_path,
                allowed_program_refs=allowed_program_refs,
                input_record_overlays=[
                    overlays[index] for overlays in overlays_by_case
                ],
            )
            for index in range(overlay_count)
        ]
        # Candidate selection reads its output id off each candidate's values
        # — remap bare artifact ids to the requested aliases BEFORE selection,
        # not only on the final results (#296).
        candidate_batches = [
            [
                _remap_output_aliases(result, output_aliases or {})
                for result in candidate_batch
            ]
            for candidate_batch in candidate_batches
        ]
        return [
            _select_candidate_result(
                self.name,
                case,
                [candidate_batch[case_index] for candidate_batch in candidate_batches],
            )
            for case_index, case in enumerate(cases)
        ]

    def _run_cases_once(
        self,
        cases: list[Case],
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        input_record_overlays: list[list[dict[str, Any]]] | None = None,
    ) -> list[EngineResult]:
        results: list[EngineResult] = []
        for start in range(0, len(cases), self.batch_size):
            end = start + self.batch_size
            overlay_chunk = (
                input_record_overlays[start:end]
                if input_record_overlays is not None
                else None
            )
            results.extend(
                self._run_case_batch_once(
                    cases[start:end],
                    output_targets,
                    artifact_path,
                    allowed_program_refs=allowed_program_refs,
                    input_record_overlays=overlay_chunk,
                )
            )
        return results

    def _run_case_batch_once(
        self,
        cases: list[Case],
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        input_record_overlays: list[list[dict[str, Any]]] | None = None,
    ) -> list[EngineResult]:
        request = self._batched_execution_request(
            cases,
            output_targets,
            allowed_program_refs=allowed_program_refs,
            input_record_overlays=input_record_overlays,
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
            return [
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={},
                    errors=(error,),
                )
                for case in cases
            ]
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            return [
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={},
                    errors=(f"Axiom RuleSpec execution emitted invalid JSON: {exc}",),
                    raw=process.stdout,
                )
                for case in cases
            ]

        query_results = [
            result
            for result in payload.get("results", [])
            if isinstance(result, Mapping)
        ]
        if len(query_results) != len(cases):
            error = (
                "Axiom RuleSpec execution returned "
                f"{len(query_results)} results for {len(cases)} cases."
            )
            return [
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={},
                    errors=(error,),
                    raw=payload,
                )
                for case in cases
            ]

        return [
            EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values=_values_from_query_result(query_result),
                raw={
                    "metadata": payload.get("metadata"),
                    "result": query_result,
                },
            )
            for case, query_result in zip(cases, query_results, strict=True)
        ]

    def _run_case_once(
        self,
        case: Case,
        output_targets: list[str],
        artifact_path: Path,
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        input_record_overlay: list[dict[str, Any]] | None = None,
        aggregate_output_targets: tuple[str, ...] = (),
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
        aggregation = _case_result_aggregation(case)
        raw: Any = payload
        if aggregation is None:
            values = _values_from_response(payload)
        else:
            values, components, aggregation_errors = _sum_query_results(
                payload,
                aggregation["entity_ids"],
                aggregate_output_targets or tuple(output_targets),
            )
            raw = {
                **payload,
                "aggregation": {
                    "strategy": aggregation["strategy"],
                    "components": components,
                },
            }
            if aggregation_errors:
                return EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={},
                    errors=aggregation_errors,
                    raw=raw,
                )
        return EngineResult(
            engine=self.name,
            household_id=case.case_id,
            values=values,
            raw=raw,
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
        aggregation = _case_result_aggregation(case)
        query_entity_ids = (
            aggregation["entity_ids"] if aggregation is not None else (entity_id,)
        )
        return {
            "mode": self.mode,
            "dataset": {
                "inputs": input_records,
                "relations": relation_records,
            },
            "queries": [
                {
                    "entity_id": query_entity_id,
                    "period": period,
                    "outputs": outputs,
                }
                for query_entity_id in query_entity_ids
            ],
        }

    def _batched_execution_request(
        self,
        cases: list[Case],
        outputs: list[str],
        *,
        allowed_program_refs: "_AllowedProgramRefs | None" = None,
        input_record_overlays: list[list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        input_records: list[dict[str, Any]] = []
        relation_records: list[dict[str, Any]] = []
        queries: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            input_record_overlay = (
                input_record_overlays[index]
                if input_record_overlays is not None
                else None
            )
            request = self._execution_request(
                case,
                outputs,
                allowed_program_refs=allowed_program_refs,
                input_record_overlay=input_record_overlay,
            )
            namespace = f"case-{index}::"
            input_records.extend(
                _namespace_input_record(record, namespace)
                for record in request["dataset"]["inputs"]
            )
            relation_records.extend(
                _namespace_relation_record(record, namespace)
                for record in request["dataset"]["relations"]
            )
            query = dict(request["queries"][0])
            query["entity_id"] = _namespace_entity_id(namespace, query["entity_id"])
            queries.append(query)

        return {
            "mode": self.mode,
            "dataset": {
                "inputs": input_records,
                "relations": relation_records,
            },
            "queries": queries,
        }

    def _input_records(
        self,
        case: Case,
        period: dict[str, str],
        default_entity_id: str,
    ) -> list[dict[str, Any]]:
        records = _explicit_input_records(case, period)
        alias_qualified_inputs = bool(
            case.metadata.get(AXIOM_ALIAS_QUALIFIED_INPUTS_METADATA_KEY)
        )
        for name, value in _case_axiom_inputs(case).items():
            for input_name in _input_record_names(
                name,
                alias_qualified=alias_qualified_inputs,
            ):
                records.append(
                    {
                        "name": input_name,
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
                ancestor / "axiom-rules-engine/target/release/axiom-rules-engine"
            )
            candidates.append(
                ancestor / "axiom-rules-engine/target/release/axiom-rules"
            )
            candidates.append(
                ancestor / "axiom-rules-engine/target/debug/axiom-rules-engine"
            )
            candidates.append(ancestor / "axiom-rules-engine/target/debug/axiom-rules")
    candidates.extend(
        [
            Path.home()
            / "TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules-engine",
            Path.home()
            / "TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules",
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


def _generated_program_path(temp_dir: Path, target: str | None) -> Path:
    if not target:
        return temp_dir / "generated-program.yaml"
    if "#" in target or ":" not in target:
        raise RuntimeError(
            "generated RuleSpec program target must be an absolute module target."
        )
    prefix, relative = target.split(":", maxsplit=1)
    relative_path = Path(relative.strip("/"))
    if (
        not prefix
        or not relative_path.as_posix()
        or relative_path.is_absolute()
        or any(part == ".." for part in relative_path.parts)
    ):
        raise RuntimeError(
            "generated RuleSpec program target must be an absolute module target."
        )
    return temp_dir / f"rulespec-{prefix}" / relative_path.with_suffix(".yaml")


def _derived_closure_ids(
    artifact_path: Path,
    roots: list[str],
    *,
    entity: str | None = None,
) -> list[str]:
    """Qualified ids of every derived rule reachable from ``roots``.

    Walks ``{"kind": "derived", "name": ...}`` references in the compiled
    expr trees. Roots may be qualified ids or local names.
    """

    try:
        compiled = json.loads(artifact_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    program = compiled.get("program", compiled)
    rules = [r for r in program.get("derived", []) or [] if isinstance(r, dict)]
    by_name: dict[str, dict] = {}
    for rule in rules:
        for key in (rule.get("name"), rule.get("id")):
            if isinstance(key, str) and key:
                by_name.setdefault(key, rule)

    def refs(node) -> list[str]:
        found = []
        if isinstance(node, dict):
            if node.get("kind") == "derived" and isinstance(node.get("name"), str):
                found.append(node["name"])
            for child in node.values():
                found.extend(refs(child))
        elif isinstance(node, list):
            for child in node:
                found.extend(refs(child))
        return found

    seen: set[str] = set()
    queue = [root for root in roots if root in by_name]
    closure_ids: list[str] = []
    while queue:
        key = queue.pop()
        rule = by_name.get(key)
        if rule is None:
            continue
        identifier = rule.get("id") or rule.get("name")
        if not isinstance(identifier, str) or identifier in seen:
            continue
        seen.add(identifier)
        # Queries evaluate at the case's entity; rules scoped to other
        # entities (per-Person intermediates) would be force-evaluated at
        # the wrong scope and fail on entity-mismatched inputs. They are
        # still walked THROUGH so household-level rules beyond them stay
        # reachable — just not queried.
        if entity is None or (rule.get("entity") or entity) == entity:
            closure_ids.append(identifier)
        queue.extend(refs(rule.get("expr")))
    return sorted(closure_ids)


def _output_targets(variables: list[str] | None) -> list[str]:
    if variables is None:
        return []
    targets = engine_targets_for_concepts(variables, "axiom")
    return targets or list(variables)


def _output_aliases_from_artifact(
    output_targets: list[str],
    artifact_path: Path,
) -> dict[str, str]:
    """Map requested local output names to unique qualified RuleSpec IDs.

    Some composed program outputs are compiled under their source legal module
    ID even though the dashboard-facing concept map uses the local program
    name. Keep that concept map stable and query the qualified ID only when the
    compiled artifact makes the local-name mapping unambiguous.
    """

    local_to_ids: dict[str, list[str]] = {}
    try:
        payload = json.loads(artifact_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    program = payload.get("program", {})
    if not isinstance(program, Mapping):
        return {}
    for derived in program.get("derived", []):
        if not isinstance(derived, Mapping):
            continue
        name = derived.get("name")
        identifier = derived.get("id")
        if not isinstance(name, str):
            continue
        # Post-hard-cut engines key an originless program's generated rules by
        # bare name with NO id field; queries match that name (#296).
        if not isinstance(identifier, str) or not identifier:
            identifier = name
        local_to_ids.setdefault(name, []).append(identifier)

    all_ids = {
        identifier
        for identifiers in local_to_ids.values()
        for identifier in identifiers
    }
    aliases: dict[str, str] = {}
    for output in output_targets:
        if ":" in output or "#" in output:
            # The symmetric case: an originless compile-composed program
            # (compose output, the generated oracle bridge) carries BARE rule
            # ids, while the concept map requests the qualified
            # `module#name` form. When the artifact lacks the qualified id
            # but holds the fragment's local name as a BARE, originless rule
            # (which by construction belongs to the program under execution),
            # query the bare id and remap the result back. A same-named
            # output qualified under a DIFFERENT module must never be
            # substituted (#296).
            if output in all_ids:
                continue
            local_name = output.rsplit("#", 1)[-1]
            identifiers = [
                identifier
                for identifier in local_to_ids.get(local_name, [])
                if ":" not in identifier and "#" not in identifier
            ]
            if len(identifiers) == 1:
                aliases[output] = identifiers[0]
            continue
        identifiers = local_to_ids.get(output, [])
        if len(identifiers) == 1:
            aliases[output] = identifiers[0]
    return aliases


def _remap_output_aliases(
    result: EngineResult,
    output_aliases: Mapping[str, str],
) -> EngineResult:
    if not output_aliases:
        return result
    reverse_aliases = {
        actual: requested for requested, actual in output_aliases.items()
    }
    values = dict(result.values)
    for actual, requested in reverse_aliases.items():
        if actual in values and requested not in values:
            values[requested] = values[actual]
    raw = _remap_aggregation_component_aliases(result.raw, reverse_aliases)
    if values == result.values and raw is result.raw:
        return result
    return EngineResult(
        engine=result.engine,
        household_id=result.household_id,
        values=values,
        errors=result.errors,
        raw=raw,
    )


def _remap_aggregation_component_aliases(
    raw: Any,
    reverse_aliases: Mapping[str, str],
) -> Any:
    """Mirror top-level aliases into each per-entity evidence component."""

    if not isinstance(raw, Mapping):
        return raw
    aggregation = raw.get("aggregation")
    if not isinstance(aggregation, Mapping):
        return raw
    raw_components = aggregation.get("components")
    if not isinstance(raw_components, list):
        return raw

    components = []
    changed = False
    for component in raw_components:
        if not isinstance(component, Mapping):
            components.append(component)
            continue
        component_values = component.get("values")
        if not isinstance(component_values, Mapping):
            components.append(component)
            continue
        remapped_values = dict(component_values)
        for actual, requested in reverse_aliases.items():
            if actual in remapped_values and requested not in remapped_values:
                remapped_values[requested] = remapped_values[actual]
        if remapped_values != component_values:
            changed = True
            components.append({**component, "values": remapped_values})
        else:
            components.append(component)
    if not changed:
        return raw
    return {
        **raw,
        "aggregation": {
            **aggregation,
            "components": components,
        },
    }


def _execution_output_targets(
    output_targets: list[str],
    cases: list[Case],
    allowed_program_refs: "_AllowedProgramRefs | None",
    *,
    output_aliases: Mapping[str, str] | None = None,
) -> list[str]:
    aliases = output_aliases or {}
    selection_outputs = [
        aliases.get(output, output) for output in _result_selection_outputs(cases)
    ]
    outputs = list(dict.fromkeys([*output_targets, *selection_outputs]))
    if allowed_program_refs is None:
        return outputs
    return [output for output in outputs if allowed_program_refs.accepts_output(output)]


def _result_selection_outputs(cases: list[Case]) -> list[str]:
    outputs = []
    for case in cases:
        raw_selection = case.metadata.get(AXIOM_RESULT_SELECTION_METADATA_KEY)
        if not isinstance(raw_selection, Mapping):
            continue
        output = raw_selection.get("output")
        if isinstance(output, str) and output:
            outputs.append(output)
    return outputs


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
        raise RuntimeError("metadata['axiom_input_record_overlays'] must be a list.")
    return [
        _normalize_input_records(
            raw_overlay,
            period,
            f"metadata['axiom_input_record_overlays'][{index}]",
        )
        for index, raw_overlay in enumerate(raw_overlays)
    ]


def _case_result_aggregation(case: Case) -> dict[str, Any] | None:
    """Validate and normalize an optional cross-entity result aggregation.

    RuleSpec outputs are entity-scoped. A comparison whose oracle reports a
    household sum can therefore request the same output for several entity ids
    and sum the executed values without inventing a household-level legal rule.
    """

    raw = case.metadata.get(AXIOM_RESULT_AGGREGATION_METADATA_KEY)
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise RuntimeError("metadata['axiom_result_aggregation'] must be a mapping.")
    strategy = str(raw.get("strategy", ""))
    if strategy != "sum":
        raise RuntimeError("metadata['axiom_result_aggregation'].strategy must be sum.")
    raw_entity_ids = raw.get("entity_ids")
    if not isinstance(raw_entity_ids, list | tuple) or isinstance(raw_entity_ids, str):
        raise RuntimeError(
            "metadata['axiom_result_aggregation'].entity_ids must be a list."
        )
    entity_ids = tuple(str(entity_id) for entity_id in raw_entity_ids)
    if not entity_ids or any(not entity_id for entity_id in entity_ids):
        raise RuntimeError(
            "metadata['axiom_result_aggregation'].entity_ids must be non-empty."
        )
    if len(set(entity_ids)) != len(entity_ids):
        raise RuntimeError(
            "metadata['axiom_result_aggregation'].entity_ids must be unique."
        )
    return {"strategy": strategy, "entity_ids": entity_ids}


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


def _input_record_names(name: Any, *, alias_qualified: bool = False) -> tuple[str, ...]:
    text = str(name)
    prefix = "#input."
    if not alias_qualified or prefix not in text:
        return (text,)
    return (text, text.rsplit(prefix, maxsplit=1)[-1])


def _looks_like_axiom_input_ref(value: Any) -> bool:
    text = str(value)
    return ":" in text and "#input." in text


def _period_for_case(case: Case) -> dict[str, str]:
    text = str(case.period)
    year = int(text.split("-", maxsplit=1)[0])
    # A full ISO date (``YYYY-MM-DD``) names a fiscal year that STARTS on that
    # exact day and runs for one year: e.g. ``2026-04-06`` is the UK 2026-27 tax
    # year, 6 Apr 2026 - 5 Apr 2027. The engine keys parameter-version selection
    # off ``period.start`` (``effective_from <= start``; ignores ``end``), so a
    # UK suite must start ON the 6 April fiscal boundary to read the fiscal-year
    # vintage rather than the value live on the preceding 1 January. The bare-
    # year branch below (start 1 Jan) predates a rate that steps on 6 April,
    # which is why UK fiscal-law suites pass the explicit start date instead.
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        month = int(text[5:7])
        day = int(text[8:10])
        start = date(year, month, day)
        end = date(year + 1, month, day) - timedelta(days=1)
        return {
            "period_kind": "tax_year",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "name": f"{year:04d}-{(year + 1) % 100:02d}",
        }
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
        return {"kind": "decimal", "value": _decimal_literal(value)}
    if isinstance(value, date):
        return {"kind": "date", "value": value.isoformat()}
    return {"kind": "text", "value": str(value)}


def _decimal_literal(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError(f"Axiom decimal inputs must be finite, got {value!r}.")
    if abs(value) < FLOAT_ZERO_TOLERANCE:
        return "0"
    literal = format(Decimal(str(value)), "f")
    if "." in literal:
        literal = literal.rstrip("0").rstrip(".")
    return "0" if literal == "-0" else literal


def _relation_tuples(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        if not value:
            return []
        if all(isinstance(item, list | tuple) for item in value):
            return list(value)
        return [value]
    return [[value]]


def _namespace_input_record(
    record: Mapping[str, Any], namespace: str
) -> dict[str, Any]:
    namespaced = dict(record)
    namespaced["entity_id"] = _namespace_entity_id(namespace, namespaced["entity_id"])
    return namespaced


def _namespace_relation_record(
    record: Mapping[str, Any], namespace: str
) -> dict[str, Any]:
    namespaced = dict(record)
    namespaced["tuple"] = [
        _namespace_entity_id(namespace, value) for value in namespaced.get("tuple", [])
    ]
    return namespaced


def _namespace_entity_id(namespace: str, entity_id: Any) -> str:
    return f"{namespace}{entity_id}"


def _values_from_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for result in payload.get("results", []):
        if not isinstance(result, Mapping):
            continue
        values.update(_values_from_query_result(result))
    return values


def _sum_query_results(
    payload: Mapping[str, Any],
    entity_ids: tuple[str, ...],
    aggregate_outputs: tuple[str, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[str, ...]]:
    """Sum requested numeric outputs across ordered entity query results."""

    query_results = [
        result for result in payload.get("results", []) if isinstance(result, Mapping)
    ]
    components = [
        {
            "entity_id": entity_id,
            "values": _values_from_query_result(result),
        }
        for entity_id, result in zip(entity_ids, query_results)
    ]
    if len(query_results) != len(entity_ids):
        return (
            {},
            components,
            (
                "Axiom RuleSpec execution returned "
                f"{len(query_results)} query results for "
                f"{len(entity_ids)} aggregated entities.",
            ),
        )

    aggregated: dict[str, Any] = {}
    errors: list[str] = []
    for output in aggregate_outputs:
        if any(output not in component["values"] for component in components):
            errors.append(
                "Axiom entity aggregation requires every query to return "
                f"output {output!r}."
            )
            continue
        values = [component["values"][output] for component in components]
        if not all(_is_numeric_value(value) for value in values):
            errors.append(
                "Axiom entity aggregation can only sum numeric output "
                f"{output!r}; got {values!r}."
            )
            continue
        aggregated[output] = sum(values)
    return aggregated, components, tuple(errors)


def _values_from_query_result(result: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
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

    def accepts_output(self, reference: str) -> bool:
        if reference in self.public_values:
            return True
        return not self.public_values

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
        # Post-hard-cut engines emit generated rules with a bare name and no
        # id — those names are queryable outputs and must survive pruning
        # (#296).
        if isinstance(derived.get("name"), str):
            public_values.add(derived["name"])
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
    # AXIOM_RULESPEC_ROOT (singular) names one rulespec checkout, or the
    # workspace that holds the rulespec-<country> checkouts, so `compare
    # euromod axiom --suite X` resolves its composition with no --axiom-program
    # (axiom-oracles#185). Module refs resolve as
    # <root>/rulespec-<country>/<prefix>/<path>.yaml, so a path pointing straight
    # at a rulespec-* checkout is lifted to its parent.
    single = os.environ.get("AXIOM_RULESPEC_ROOT")
    if single:
        root = Path(single).expanduser()
        if root.name.startswith("rulespec-"):
            root = root.parent
        return (root,)
    candidate = Path.home() / "TheAxiomFoundation"
    if candidate.exists():
        return (candidate,)
    return ()
