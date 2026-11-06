"""Evaluate RuleSpec companion-fixture cases through the Axiom rules engine.

The statute-boundary and federal tax-liability grids take each case's inputs
from a rulespec ``.test.yaml`` companion fixture. This module compiles the
fixture's module with a receipted engine executable, sends every case's inputs
to ``run-compiled``, and returns the values the engine computed. The fixture's
expected outputs never become report values here: callers compare them with
the engine's output and fail when the two disagree.

Request construction follows the encoder's fixture executor (axiom-encode
``ValidatorPipeline._build_rulespec_dataset``) for the fixture shapes the grids
use:

* an absolute ``<module>#input.<name>`` key with a scalar value is an input on
  the queried entity, sent under its absolute name;
* an absolute ``<module>#relation.<name>`` key with a list of mappings adds one
  related entity per mapping, linked to the queried entity through the
  relation, with each mapping's scalar entries as that entity's inputs.

Anything else (``tables``, nested values, friendly-name keys, a relation the
compiled program never reads) fails closed rather than guessing.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .engine_identity import EngineIdentityError, engine_receipt, record_engine_receipt

_ABSOLUTE_INPUT = re.compile(r"^[a-z][a-z0-9-]*:[^#\s]+#input\.[A-Za-z0-9_]+$")
_ABSOLUTE_RELATION = re.compile(r"^[a-z][a-z0-9-]*:[^#\s]+#relation\.[A-Za-z0-9_]+$")
_ABSOLUTE_OUTPUT = re.compile(r"^[a-z][a-z0-9-]*:[^#\s]+#[A-Za-z0-9_]+$")
_JUDGMENTS = ("holds", "not_holds", "undetermined")

SubprocessRun = Callable[..., subprocess.CompletedProcess[str]]


class FixtureEngineError(RuntimeError):
    """The engine could not evaluate a fixture case, or the request is unsafe."""


class FixtureDisagreement(FixtureEngineError):
    """The engine's output differs from the fixture's recorded expectation."""


@dataclass(frozen=True)
class CompiledModule:
    """A compiled RuleSpec module bound to the executable that compiled it."""

    module_ref: str
    artifact: Path
    binary: Path
    receipt: Mapping[str, Any]


def _receipted_run(
    command: list[str],
    *,
    expected: Mapping[str, Any],
    run: SubprocessRun,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run the engine only when its bytes still match the selected receipt."""
    before = engine_receipt(command[0])
    for field in ("commit", "binary_sha256"):
        if before.get(field) != expected.get(field):
            raise EngineIdentityError(
                f"Axiom engine {field} changed before fixture evaluation"
            )
    invocation = list(command)
    if before.get("binary_sha256") is not None:
        invocation[0] = before["binary_path"]
    result = run(invocation, **kwargs)
    after = engine_receipt(invocation[0])
    for field in ("commit", "binary_sha256"):
        if after.get(field) != before.get(field):
            raise EngineIdentityError(
                f"Axiom engine {field} changed during fixture evaluation"
            )
    record_engine_receipt(before)
    return result


def module_program_path(module_ref: str, roots: Iterable[Path]) -> Path:
    """``us:policies/x`` -> the one ``<root>/us/policies/x.yaml`` that exists."""
    jurisdiction, separator, relative = module_ref.partition(":")
    if not separator or not jurisdiction or not relative or "#" in relative:
        raise FixtureEngineError(f"not a RuleSpec module reference: {module_ref!r}")
    candidates = [Path(root) / jurisdiction / f"{relative}.yaml" for root in roots]
    matches = [path for path in candidates if path.is_file()]
    if len(matches) != 1:
        tried = ", ".join(str(path) for path in candidates)
        raise FixtureEngineError(
            f"{module_ref}: expected exactly one RuleSpec program, found "
            f"{len(matches)} ({tried})"
        )
    return matches[0]


def compile_module(
    binary: Path,
    module_ref: str,
    roots: Iterable[Path],
    work_dir: Path,
    *,
    run: SubprocessRun = subprocess.run,
) -> CompiledModule:
    """Compile ``module_ref`` from a staged copy of its canonical checkout."""
    from .engine_compat import compile_with_engine, import_prefixes, stage_pure_root
    from .rulespec_roots import require_canonical_rulespec_root

    program = module_program_path(module_ref, roots)
    root = next(
        parent for parent in program.parents if parent.name.startswith("rulespec-")
    )
    root = require_canonical_rulespec_root(root)
    receipt = engine_receipt(binary)
    document = yaml.safe_load(program.read_text()) or {}
    imports = document.get("imports") if isinstance(document, Mapping) else None
    jurisdictions = {module_ref.split(":", 1)[0]} | import_prefixes(
        [entry for entry in imports or [] if isinstance(entry, str)]
    )
    staged = stage_pure_root(root, jurisdictions, work_dir / "roots")
    staged_program = staged / program.relative_to(root)
    artifact = work_dir / (re.sub(r"[^A-Za-z0-9]+", "-", module_ref) + ".json")

    def execute(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _receipted_run(command, expected=receipt, run=run, **kwargs)

    compile_with_engine(
        binary,
        staged_program,
        artifact,
        roots=[staged],
        composed=False,
        run=execute,
    )
    return CompiledModule(module_ref, artifact, Path(binary), receipt)


def _scalar(value: Any, *, where: str) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int):
        return {"kind": "integer", "value": value}
    if isinstance(value, float):
        return {"kind": "decimal", "value": repr(value)}
    if isinstance(value, Decimal):
        return {"kind": "decimal", "value": str(value)}
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
            return {"kind": "date", "value": stripped}
        if re.fullmatch(r"-?\d+", stripped):
            return {"kind": "integer", "value": int(stripped)}
        if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", stripped):
            return {"kind": "decimal", "value": stripped}
        return {"kind": "text", "value": value}
    raise FixtureEngineError(f"{where}: unsupported scalar {value!r}")


def _period(raw: Any, *, where: str) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        period = dict(raw)
        if not {"period_kind", "start", "end"} <= set(period):
            raise FixtureEngineError(f"{where}: period needs period_kind/start/end")
        return period
    if isinstance(raw, str) and (match := re.fullmatch(r"(\d{4})-(\d{2})", raw)):
        from calendar import monthrange

        year, month = int(match.group(1)), int(match.group(2))
        last = monthrange(year, month)[1]
        return {
            "period_kind": "month",
            "start": f"{year:04d}-{month:02d}-01",
            "end": f"{year:04d}-{month:02d}-{last:02d}",
        }
    if isinstance(raw, (str, int)) and re.fullmatch(r"\d{4}", str(raw)):
        year = int(raw)
        return {
            "period_kind": "tax_year",
            "start": f"{year:04d}-01-01",
            "end": f"{year:04d}-12-31",
        }
    raise FixtureEngineError(f"{where}: unsupported period {raw!r}")


def _program(artifact: Path) -> dict[str, Any]:
    payload = json.loads(Path(artifact).read_text())
    program = payload.get("program") if isinstance(payload, Mapping) else None
    if not isinstance(program, dict):
        raise FixtureEngineError(f"{artifact}: compiled artifact has no program")
    return program


def _derived_by_id(program: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(rule["id"]): rule
        for rule in program.get("derived") or []
        if isinstance(rule, Mapping) and rule.get("id")
    }


def _relation_slots(program: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Each relation's queried slot (from executable nodes) and slot entities."""
    slots: dict[str, dict[str, Any]] = {}
    for relation in program.get("relations") or []:
        if isinstance(relation, Mapping) and relation.get("name"):
            entry = slots.setdefault(str(relation["name"]), {"current": set()})
            entities = relation.get("slot_entities")
            if isinstance(entities, list) and len(entities) == 2:
                entry["entities"] = tuple(str(entity) for entity in entities)

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            name = node.get("relation")
            if isinstance(name, str) and "current_slot" in node:
                slots.setdefault(name, {"current": set()})["current"].add(
                    node["current_slot"]
                )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for rule in program.get("derived") or []:
        walk(rule)
    return slots


def build_request(
    record: Mapping[str, Any],
    artifact: Path,
    outputs: Iterable[str],
) -> dict[str, Any]:
    """The ``run-compiled`` request for one fixture case."""
    name = str(record.get("name"))
    where = f"fixture case {name!r}"
    if record.get("tables") not in (None, {}, []):
        raise FixtureEngineError(f"{where}: table rows are not supported")
    program = _program(artifact)
    derived = _derived_by_id(program)
    outputs = list(dict.fromkeys(outputs))
    if not outputs:
        raise FixtureEngineError(f"{where}: no outputs requested")
    missing = [output for output in outputs if output not in derived]
    if missing:
        raise FixtureEngineError(
            f"{where}: the compiled program does not define {missing}"
        )
    entities = {str(derived[output].get("entity") or "") for output in outputs}
    if len(entities) != 1 or "" in entities:
        raise FixtureEngineError(
            f"{where}: requested outputs span entities {sorted(entities)}"
        )
    query_entity = entities.pop()
    query_id = "fixture-case"
    period = _period(record.get("period"), where=where)
    interval = {"start": period["start"], "end": period["end"]}
    relation_slots = _relation_slots(program)
    raw_inputs = record.get("input") or {}
    if not isinstance(raw_inputs, Mapping):
        raise FixtureEngineError(f"{where}: input is not a mapping")
    inputs: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for key, value in raw_inputs.items():
        key = str(key)
        if isinstance(value, list):
            if not _ABSOLUTE_RELATION.match(key):
                raise FixtureEngineError(f"{where}: {key!r} is not a relation key")
            slot = relation_slots.get(key)
            if slot is None:
                raise FixtureEngineError(
                    f"{where}: the compiled program declares no relation {key!r}"
                )
            current = slot["current"]
            if not current:
                raise FixtureEngineError(
                    f"{where}: the compiled program never reads relation {key!r}"
                )
            if len(current) > 1:
                raise FixtureEngineError(
                    f"{where}: relation {key!r} is read from both slots"
                )
            current_slot = next(iter(current))
            if current_slot not in (0, 1):
                raise FixtureEngineError(
                    f"{where}: relation {key!r} has queried slot {current_slot!r}"
                )
            slot_entities = slot.get("entities")
            if slot_entities is not None:
                if slot_entities[current_slot] != query_entity:
                    raise FixtureEngineError(
                        f"{where}: relation {key!r} slot {current_slot} holds "
                        f"{slot_entities[current_slot]}, not {query_entity}"
                    )
                related_entity = slot_entities[1 - current_slot]
            else:
                head = key.rsplit("#relation.", 1)[1].split("_of_", 1)[0]
                related_entity = (
                    "".join(part.capitalize() for part in head.split("_") if part)
                    or "Related"
                )
            for index, item in enumerate(value, 1):
                if not isinstance(item, Mapping):
                    raise FixtureEngineError(
                        f"{where}: relation {key!r} item {index} is not a mapping"
                    )
                related_id = f"{query_id}-{key.rsplit('.', 1)[1]}-{index}"
                pair = [related_id, query_id]
                if current_slot == 0:
                    pair.reverse()
                relations.append({"name": key, "tuple": pair, "interval": interval})
                for child_key, child_value in item.items():
                    child_key = str(child_key)
                    if not _ABSOLUTE_INPUT.match(child_key):
                        raise FixtureEngineError(
                            f"{where}: relation {key!r} item {index} key "
                            f"{child_key!r} is not an absolute input"
                        )
                    inputs.append(
                        {
                            "name": child_key,
                            "entity": related_entity,
                            "entity_id": related_id,
                            "interval": interval,
                            "value": _scalar(child_value, where=f"{where} {child_key}"),
                        }
                    )
            continue
        if isinstance(value, Mapping):
            raise FixtureEngineError(f"{where}: {key!r} has a nested mapping")
        if not _ABSOLUTE_INPUT.match(key):
            raise FixtureEngineError(f"{where}: {key!r} is not an absolute input")
        inputs.append(
            {
                "name": key,
                "entity": query_entity,
                "entity_id": query_id,
                "interval": interval,
                "value": _scalar(value, where=f"{where} {key}"),
            }
        )
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": [{"entity_id": query_id, "period": period, "outputs": outputs}],
    }


def engine_value(output: Mapping[str, Any]) -> Any:
    """``holds``/``not_holds``/``undetermined`` for a judgment; else the scalar.

    Integers and decimals come back as :class:`~decimal.Decimal` so callers
    compare them exactly.
    """
    if output.get("kind") == "judgment":
        outcome = str(output.get("outcome"))
        if outcome not in _JUDGMENTS:
            raise FixtureEngineError(f"unknown judgment outcome {outcome!r}")
        return outcome
    scalar = output.get("value") if output.get("kind") == "scalar" else output
    if not isinstance(scalar, Mapping):
        raise FixtureEngineError(f"unrecognised engine output {output!r}")
    kind, raw = scalar.get("kind"), scalar.get("value")
    if kind in {"integer", "decimal"}:
        try:
            return Decimal(str(raw))
        except InvalidOperation as error:
            raise FixtureEngineError(f"non-numeric engine value {raw!r}") from error
    if kind == "bool":
        return "holds" if raw is True else "not_holds"
    if kind in {"text", "date"}:
        return raw
    raise FixtureEngineError(f"unsupported engine value kind {kind!r}")


def evaluate_case(
    compiled: CompiledModule,
    record: Mapping[str, Any],
    outputs: Iterable[str],
    *,
    run: SubprocessRun = subprocess.run,
) -> dict[str, Any]:
    """Run one fixture case and return ``{output id: engine value}``."""
    outputs = list(dict.fromkeys(outputs))
    request = build_request(record, compiled.artifact, outputs)
    result = _receipted_run(
        [str(compiled.binary), "run-compiled", "--artifact", str(compiled.artifact)],
        expected=compiled.receipt,
        run=run,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    where = f"fixture case {record.get('name')!r}"
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise FixtureEngineError(f"{where}: engine failed: {detail}")
    try:
        payload = json.loads(result.stdout)
        rows = payload["results"]
    except (ValueError, KeyError, TypeError) as error:
        raise FixtureEngineError(f"{where}: unreadable engine response") from error
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise FixtureEngineError(f"{where}: expected one result row")
    raw_outputs = rows[0].get("outputs")
    if not isinstance(raw_outputs, Mapping):
        raise FixtureEngineError(f"{where}: result row has no outputs")
    by_reference: dict[str, Mapping[str, Any]] = {}
    for key, value in raw_outputs.items():
        if isinstance(value, Mapping):
            by_reference[str(key)] = value
            if value.get("id"):
                by_reference[str(value["id"])] = value
    values: dict[str, Any] = {}
    for output in outputs:
        if output not in by_reference:
            raise FixtureEngineError(f"{where}: engine returned no {output!r}")
        values[output] = engine_value(by_reference[output])
    return values


def expected_value(raw: Any) -> Any:
    """A fixture's recorded expectation in :func:`engine_value`'s vocabulary."""
    if isinstance(raw, bool):
        return "holds" if raw else "not_holds"
    if isinstance(raw, str):
        normalized = raw.strip().lower().replace("-", "_")
        if normalized in _JUDGMENTS:
            return normalized
        try:
            return Decimal(raw.strip())
        except InvalidOperation:
            return raw
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw))
    raise FixtureEngineError(f"unsupported fixture expectation {raw!r}")


def require_agreement(
    case_id: str,
    engine: Mapping[str, Any],
    fixture_outputs: Mapping[str, Any],
) -> None:
    """Fail unless the engine returned every recorded fixture output, at its value.

    :func:`evaluate_fixture_cases` requests every recorded output the program
    derives on the queried entity, so an output missing here names another
    entity or no rule at all, and the engine never checked it.
    """
    differences = []
    for output, raw in fixture_outputs.items():
        if output not in engine:
            differences.append(f"{output}: fixture {raw!r}, engine evaluated no such output")
            continue
        expected = expected_value(raw)
        actual = engine[output]
        if expected != actual or type(expected) is not type(actual):
            differences.append(f"{output}: fixture {raw!r}, engine {actual!r}")
    if differences:
        raise FixtureDisagreement(
            f"fixture case {case_id!r}: the engine disagrees with the fixture: "
            + "; ".join(differences)
        )


def evaluate_fixture_cases(
    binary: Path,
    module_ref: str,
    roots: Iterable[Path],
    records: Mapping[str, Mapping[str, Any]],
    outputs_for: Callable[[str, Mapping[str, Any]], Iterable[str]],
    *,
    run: SubprocessRun = subprocess.run,
) -> dict[str, dict[str, Any]]:
    """Compile once, evaluate every case, and check it against its fixture."""
    roots = [Path(root) for root in roots]
    with tempfile.TemporaryDirectory(prefix="fixture-engine-") as scratch:
        compiled = compile_module(binary, module_ref, roots, Path(scratch), run=run)
        derived = _derived_by_id(_program(compiled.artifact))
        values: dict[str, dict[str, Any]] = {}
        for case_id, record in records.items():
            required = list(dict.fromkeys(outputs_for(case_id, record)))
            if not required or not all(_ABSOLUTE_OUTPUT.match(o) for o in required):
                raise FixtureEngineError(
                    f"fixture case {case_id!r}: required outputs must be "
                    f"absolute output ids; got {required}"
                )
            # Every other recorded fixture output the program derives on the
            # same entity is evaluated too, and `require_agreement` refuses any
            # it cannot evaluate, so the engine checks the whole recorded case,
            # not only the values the grid reads.
            entity = (derived.get(required[0]) or {}).get("entity")
            extra = [
                str(output)
                for output in (record.get("output") or {})
                if str(output) not in required
                and (derived.get(str(output)) or {}).get("entity") == entity
            ]
            engine = evaluate_case(compiled, record, [*required, *extra], run=run)
            require_agreement(case_id, engine, record.get("output") or {})
            values[case_id] = engine
    return values
