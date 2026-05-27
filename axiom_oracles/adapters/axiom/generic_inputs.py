"""Generic input projection driven by the compiled program.

The harness used to hand-curate per-program input baselines and ECPS overrides
(see ``snap_co_projection.py``). Adding a state SNAP comparison required
copying that whole module and editing the input slot names — exactly the
per-program-code pattern that axiom-compose eliminates at the rule-encoding
layer. This module pushes the same elimination through to the population-
projection layer:

1. Read the compiled program's expr trees; enumerate every ``kind: input``
   reference.
2. Infer each input's entity (Person, Household, …) from the containing
   derived rule's ``entity:``.
3. Infer each input's dtype from how the input is used (boolean ops →
   Judgment; arithmetic → Decimal; comparisons → Decimal; default Judgment).
4. Default unknowns to a type-appropriate zero (False / 0 / "").
5. Let an *ECPS mapping table* — pure data, not code — override the small set
   of facts ECPS actually measures.

A new program comparison is then: declare the ECPS mapping in axiom-programs
or pass it inline. No new Python module per state. No new baselines copied
from upstream test fixtures.

See axiom-oracles#26 for the architectural background.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Input enumeration + type inference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputSlot:
    """A unique input slot the compiled program needs supplied.

    ``name``     — absolute RuleSpec input target
                   (e.g. ``us:regulations/7-cfr/273/6#input.member_has_ssn``).
    ``entity``   — entity scope (Person, Household, SnapUnit, TaxUnit, …),
                   inferred from the rule that references the input.
    ``dtype``    — RuleSpec dtype (Judgment / Money / Decimal / Integer),
                   inferred from how the input participates in expressions.
    """

    name: str
    entity: str
    dtype: str


# Operations that drive dtype inference. Booleans get a Judgment input;
# arithmetic and comparisons get a Decimal-ish input. The default falls
# back to Judgment because the SNAP program is judgment-dominated.
_BOOLEAN_OPS = {"and", "or", "not", "comparison", "if"}
_NUMERIC_OPS = {"add", "sub", "mul", "max", "min", "ceil", "floor"}


def enumerate_inputs(compiled_program: Mapping[str, Any]) -> list[InputSlot]:
    """Return one InputSlot per unique input name referenced by any derived rule."""

    by_name: dict[str, InputSlot] = {}
    for rule in compiled_program.get("derived", []):
        entity = str(rule.get("entity") or "Household")
        expr = rule.get("expr") or {}
        for name, dtype in _walk_for_inputs(expr, parent=None):
            existing = by_name.get(name)
            if existing is not None and existing.entity != entity:
                # Same input referenced from rules with different entities;
                # prefer the more specific (non-Household) scope.
                if existing.entity == "Household" and entity != "Household":
                    by_name[name] = InputSlot(name=name, entity=entity, dtype=dtype)
                continue
            if existing is None:
                by_name[name] = InputSlot(name=name, entity=entity, dtype=dtype)
            elif existing.dtype == "Judgment" and dtype != "Judgment":
                by_name[name] = InputSlot(name=name, entity=entity, dtype=dtype)
    return sorted(by_name.values(), key=lambda slot: slot.name)


def _walk_for_inputs(node: Any, *, parent: dict | None):
    """Yield (input_name, inferred_dtype) tuples from an expr tree.

    Passes the parent NODE (not just kind) so dtype inference can peek at
    siblings — a comparison with a bool literal implies the input is
    Judgment, with a numeric literal implies Decimal.
    """

    if isinstance(node, dict):
        kind = node.get("kind")
        if kind == "input":
            name = node.get("name")
            if isinstance(name, str) and name:
                yield name, _infer_dtype(parent, node)
            return
        for child in node.values():
            yield from _walk_for_inputs(child, parent=node)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_for_inputs(child, parent=parent)


def _infer_dtype(parent: dict | None, input_node: dict) -> str:
    """Infer the input slot's dtype from the way the parent expression uses it."""

    if parent is None:
        return "Judgment"
    parent_kind = parent.get("kind")
    if parent_kind in {"and", "or", "not"}:
        return "Judgment"
    if parent_kind in _NUMERIC_OPS:
        return "Decimal"
    if parent_kind == "comparison":
        # Look at the OTHER side of the comparison; its literal tells us
        # what the input is being compared to.
        for side_key in ("left", "right"):
            side = parent.get(side_key)
            if side is input_node or not isinstance(side, dict):
                continue
            literal_dtype = _literal_dtype(side)
            if literal_dtype is not None:
                return literal_dtype
        return "Decimal"
    if parent_kind == "if":
        # Inputs in the condition of an `if` are Judgment; inputs in the
        # then/else branches inherit the if's overall dtype, which we
        # don't track here. Default Judgment is the safer fallback for
        # SNAP/eligibility-heavy programs.
        return "Judgment"
    return "Judgment"


def _literal_dtype(node: dict) -> str | None:
    """Return the RuleSpec dtype for a literal node, or None if not a literal."""

    if node.get("kind") != "literal":
        return None
    value = node.get("value")
    if not isinstance(value, dict):
        return None
    value_kind = value.get("kind")
    if value_kind == "bool":
        return "Judgment"
    if value_kind in {"decimal", "integer"}:
        return "Decimal"
    return None


# ---------------------------------------------------------------------------
# Type-appropriate defaults
# ---------------------------------------------------------------------------


def default_for(dtype: str) -> Any:
    if dtype in {"Money", "Decimal", "Integer"}:
        return 0
    if dtype == "Judgment":
        return False
    return None


# ---------------------------------------------------------------------------
# ECPS-mapping protocol
# ---------------------------------------------------------------------------
#
# An EcpsMapping is a dict from absolute input name to a callable that takes
# a Case (and a Person, for Person-scoped inputs) and returns the value to
# project. Unknown inputs default via ``default_for(dtype)``. This is the
# only piece of per-program *data* in the generic projector; the rest is
# structural.

EcpsMapping = Mapping[str, Callable[..., Any]]


# ---------------------------------------------------------------------------
# Generic attach
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenericInputRecord:
    """A type-safe input record ready for ``ExecutionRequest.dataset.inputs``."""

    name: str
    entity: str
    entity_id: str
    value: Any
    dtype: str

    def to_dict(self, interval: dict[str, str]) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity": self.entity,
            "entity_id": self.entity_id,
            "interval": interval,
            "value": _scalar_value(self.value, self.dtype),
        }


def _scalar_value(value: Any, dtype: str) -> dict[str, Any]:
    """Wrap a Python value in the engine's ScalarValueSpec shape."""

    if dtype == "Judgment":
        return {"kind": "bool", "value": bool(value)}
    if dtype == "Integer":
        return {"kind": "integer", "value": int(value)}
    # Default to decimal — money/decimal both use the same wrapper.
    return {"kind": "decimal", "value": str(value)}


def project_case_inputs(
    *,
    compiled_program: Mapping[str, Any],
    household_id: str,
    person_ids: list[str],
    ecps_mapping: EcpsMapping | None = None,
    case_facts: Mapping[str, Any] | None = None,
    person_facts: list[Mapping[str, Any]] | None = None,
    program_target: str = "axiom:program",
) -> list[GenericInputRecord]:
    """Project a single case into engine input records the compiled program needs.

    For each input slot in the compiled program:
      1. If an ECPS mapping covers this input name, call the mapper.
      2. Else if case_facts / person_facts carry a value by the same key, use it.
      3. Else default by dtype (False / 0).

    Person-scoped inputs are emitted once per person. Household-scoped inputs
    (and other unit scopes — SnapUnit, TaxUnit) are emitted once per case
    against the household_id; the engine treats SnapUnit and friends as
    keyed by the underlying household when they're filtered entities.
    """

    slots = enumerate_inputs(compiled_program)
    ecps_mapping = ecps_mapping or {}
    case_facts = case_facts or {}
    person_facts = person_facts or [{} for _ in person_ids]
    records: list[GenericInputRecord] = []

    # The engine requires dataset inputs to use absolute legal RuleSpec
    # references (namespace:path#input.<bare-name>); bare names are rejected
    # under public-id mode. The bare slot name is the engine's resolution
    # key — the target prefix is just provenance — so any well-formed
    # public reference works. We synthesize one per slot so the strict
    # path accepts the records. When compose later emits a canonical
    # inputs manifest, callers can pass the real per-slot target through.
    def _qualify(name: str) -> str:
        return f"{program_target}#input.{name}"

    for slot in slots:
        if slot.entity == "Person":
            for person_id, facts in zip(person_ids, person_facts, strict=False):
                value = _resolve_value(
                    slot, ecps_mapping, case_facts=case_facts, person_facts=facts
                )
                records.append(
                    GenericInputRecord(
                        name=_qualify(slot.name),
                        entity="Person",
                        entity_id=person_id,
                        value=value,
                        dtype=slot.dtype,
                    )
                )
        else:
            value = _resolve_value(
                slot, ecps_mapping, case_facts=case_facts, person_facts=None
            )
            records.append(
                GenericInputRecord(
                    name=_qualify(slot.name),
                    entity=slot.entity,
                    entity_id=household_id,
                    value=value,
                    dtype=slot.dtype,
                )
            )

    return records


def _resolve_value(
    slot: InputSlot,
    ecps_mapping: EcpsMapping,
    *,
    case_facts: Mapping[str, Any],
    person_facts: Mapping[str, Any] | None,
) -> Any:
    """Map a slot to a value via, in order: ECPS mapper → case/person facts → default."""

    mapper = ecps_mapping.get(slot.name)
    if mapper is not None:
        if slot.entity == "Person":
            return mapper(case_facts, person_facts or {})
        return mapper(case_facts, None)

    # Fact-table fallback: look up by slot name (or its unqualified suffix).
    unqualified = slot.name.split("#input.")[-1] if "#input." in slot.name else slot.name
    facts_table = person_facts if slot.entity == "Person" else case_facts
    if facts_table is None:
        facts_table = {}
    if slot.name in facts_table:
        return facts_table[slot.name]
    if unqualified in facts_table:
        return facts_table[unqualified]
    return default_for(slot.dtype)


# ---------------------------------------------------------------------------
# Case-level attach (CLI integration entry point)
# ---------------------------------------------------------------------------


def attach_generic_inputs(
    cases: list,
    *,
    compiled_program_path: Path,
    ecps_mapping: EcpsMapping | None = None,
    household_entity: str = "Household",
    household_entity_id: str = "household",
    member_relation: str = "us:statutes/7/2012/j#relation.member_of_household",
    load_default_mapping: bool = True,
) -> list:
    """Attach generic Axiom input records to each case.

    Drop-in replacement for ``attach_axiom_snap_co_inputs`` and friends: the
    compiled program declares its inputs; we project each case's facts into
    those slots, falling back to type-zero defaults for inputs ECPS doesn't
    measure. An optional ``ecps_mapping`` supplies per-program overrides
    (data, not code).

    The case's ``metadata[AXIOM_INPUT_RECORDS_METADATA_KEY]`` ends up with
    one record per input slot per relevant entity; the relation between
    persons and the household is also recorded so the engine can resolve
    member-scoped inputs.
    """
    from dataclasses import replace

    from .runner import (
        AXIOM_INPUT_RECORDS_METADATA_KEY,
        AXIOM_RELATIONS_METADATA_KEY,
    )

    with open(compiled_program_path) as f:
        compiled = json.load(f)
    program = compiled.get("program", compiled)

    # If the caller didn't pass a mapping, resolve one from the default YAML.
    # The mapping table itself is data (axiom_oracles/data/ecps_input_mapping.yaml);
    # this just picks the entries that match the program's specific slots.
    if ecps_mapping is None and load_default_mapping:
        try:
            from .ecps_mapping_loader import load_ecps_mapping_for_program

            ecps_mapping = load_ecps_mapping_for_program(program)
        except Exception:
            ecps_mapping = None

    # Derive a stable synthetic target from the compiled-program path so the
    # absolute references the engine sees are deterministic per program.
    # Example: /tmp/ca-snap-compiled.json → axiom:ca-snap-compiled.
    program_target = f"axiom:{Path(compiled_program_path).stem}"

    projected: list = []
    for case in cases:
        metadata = dict(case.metadata)
        if metadata.get(AXIOM_INPUT_RECORDS_METADATA_KEY):
            projected.append(case)
            continue

        people = [
            entity
            for entity in case.entities
            if str(entity.kind).lower().replace("_", "-") == "person"
        ]
        person_ids = [f"member-{i}" for i, _ in enumerate(people)]
        # Build facts dicts so the generic resolver can look up values by
        # unqualified input name. ECPS Cases store facts on entities, not
        # by input-slot identifiers — the ecps_mapping is the place to do
        # the actual translation. The household-level dict carries a hidden
        # __people__ key so household-scoped transforms (hh_size,
        # sum_over_people) can see the per-person facts.
        person_facts = [dict(person.facts) for person in people]
        case_facts = {"__people__": person_facts}

        records = project_case_inputs(
            compiled_program=program,
            household_id=household_entity_id,
            person_ids=person_ids,
            ecps_mapping=ecps_mapping,
            case_facts=case_facts,
            person_facts=person_facts,
            program_target=program_target,
        )

        interval = {
            "start": _interval_start(case.period),
            "end": _interval_end(case.period),
        }
        input_dicts = [r.to_dict(interval) for r in records]

        # Emit the relation under both the absolute (`us:.../#relation.X`)
        # and bare (`X`) forms. Compose-synthesized rules call
        # `count_related` with bare relation names, while atomic encoded
        # rules use the absolute form. The engine's relation lookup
        # treats them as two distinct relations, so emit both to keep
        # both worlds happy. The bare name is derived from the absolute
        # form's fragment after stripping the `#relation.` prefix.
        bare_name = member_relation
        if "#" in member_relation:
            _, fragment = member_relation.split("#", maxsplit=1)
            bare_name = fragment.removeprefix("relation.")

        relation_records: list[dict[str, Any]] = []
        for pid in person_ids:
            tuple_pair = [pid, household_entity_id]
            relation_records.append({"name": member_relation, "tuple": tuple_pair})
            if bare_name != member_relation:
                relation_records.append({"name": bare_name, "tuple": tuple_pair})

        metadata[AXIOM_INPUT_RECORDS_METADATA_KEY] = input_dicts
        metadata[AXIOM_RELATIONS_METADATA_KEY] = [
            *metadata.get(AXIOM_RELATIONS_METADATA_KEY, []),
            *relation_records,
        ]
        metadata["axiom_entity"] = household_entity
        metadata["axiom_entity_id"] = household_entity_id

        projected.append(replace(case, metadata=metadata))

    return projected


def _interval_start(period: str) -> str:
    """Convert a case period like '2026-01' into an ISO start date."""
    if len(period) == 7:  # YYYY-MM
        return f"{period}-01"
    if len(period) == 4:  # YYYY
        return f"{period}-01-01"
    return period


def _interval_end(period: str) -> str:
    """Convert a case period like '2026-01' into an ISO end date (month-end).

    The end date must cover the full query period — the engine's interval-
    membership check is strict, so an input recorded as 2026-01-01..28 is
    invisible to a query for 2026-01-29..31. Use the calendar's actual
    last day of the month.
    """
    from calendar import monthrange

    if len(period) == 7:
        year, month = period.split("-")
        last_day = monthrange(int(year), int(month))[1]
        return f"{period}-{last_day:02d}"
    if len(period) == 4:
        return f"{period}-12-31"
    return period
