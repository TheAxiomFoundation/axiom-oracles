"""Recover input kinds from compiled execution scopes for typed requests."""

from collections import defaultdict
from copy import deepcopy
from typing import Any

from .relation_binding import (
    RelationBindingError,
    _ArtifactRelations,
    artifact_has_typed_relations,
)


def bind_typed_input_entities(
    request: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    """Label historical ``Entity`` inputs only when the artifact is typed.

    A producer's IDs identify records, not statutory kinds: a UK benefit-unit
    record can execute in a Person scope. The compiled input expressions and
    query outputs supply those scopes. Once an ID has one known kind, apply it
    to every input for that ID, including inputs unused by the compiled module.
    Existing specific labels remain authoritative and must agree with scope.
    """
    result = deepcopy(request)
    if not artifact_has_typed_relations(artifact):
        return result
    relations = _ArtifactRelations(artifact)
    program = artifact.get("program", artifact)
    schemas = {schema["name"]: schema for schema in program.get("relations", [])}
    concrete_entities = {
        entity
        for schema in schemas.values()
        for kinds in (
            schema.get("slot_entities", []),
            (schema.get("derivation") or {}).get("slot_entities", []),
        )
        for entity in kinds
    }
    aliases: dict[str, set[str]] = defaultdict(set)
    for schema in schemas.values():
        derivation = schema.get("derivation") or {}
        alias = derivation.get("entity")
        kinds = derivation.get("slot_entities", [])
        slot = derivation.get("current_slot")
        if (
            alias
            and alias not in concrete_entities
            and isinstance(slot, int)
            and 0 <= slot < len(kinds)
        ):
            aliases[alias].add(kinds[slot])

    def entity_kind(entity):
        # A filtered entity (e.g. SnapUnit) retains its structural owner kind
        # (Household). Only unique synthetic aliases establish this mapping.
        options = aliases.get(entity, set())
        entity = next(iter(options)) if len(options) == 1 else entity
        return None if entity == "Scalar" else entity

    input_kinds: dict[str, set[str]] = defaultdict(set)
    output_kinds: dict[str, set[str]] = defaultdict(set)

    def walk(node, entity, target):
        if isinstance(node, list):
            for item in node:
                walk(item, entity, target)
            return
        if not isinstance(node, dict):
            return
        kind = node.get("kind")
        if kind in {"input", "input_or_else"} and entity:
            name = node.get("name")
            if isinstance(name, str):
                request_name = (
                    f"{target}#input.{name}" if target and "#" not in name else name
                )
                input_kinds[request_name].add(entity)
        if kind in {"count_related", "sum_related"}:
            schema = relations.schema(node.get("relation", ""))
            expected = (
                relations.expected(node["relation"])
                if schema is not None and schema.get("arity", 2) == 2
                else None
            )
            slot = node.get("related_slot")
            related = (
                entity_kind(expected[slot])
                if expected is not None
                and isinstance(slot, int)
                and 0 <= slot < len(expected)
                else None
            )
            walk(node.get("where"), related, target)
            walk(node.get("value"), related, target)
            return
        if kind == "no_match":
            walk(node.get("subject"), entity, target)
            return
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value, entity, target)

    for rule in program.get("derived", []):
        entity = entity_kind(rule.get("entity"))
        rule_id = rule.get("id")
        target = rule_id.split("#", 1)[0] if rule_id and "#" in rule_id else None
        if entity:
            for name in (rule.get("name"), rule_id):
                if name:
                    output_kinds[name].add(entity)
        for version in rule.get("versions") or [rule]:
            walk(version.get("expr", {}), entity, target)
    for schema in schemas.values():
        derivation = schema.get("derivation")
        if not derivation:
            continue
        kinds = derivation.get("slot_entities", [])
        slot = derivation.get("related_slot")
        entity = (
            kinds[slot] if isinstance(slot, int) and 0 <= slot < len(kinds) else None
        )
        entity = entity_kind(entity)
        name = schema["name"]
        target = name.split("#", 1)[0] if "#" in name else None
        walk(derivation.get("predicate", {}), entity, target)

    options_by_id: dict[str, set[str]] = {}

    def constrain(entity_id, options):
        if not options:
            return
        previous = options_by_id.get(entity_id, options)
        compatible = previous & options
        if not compatible:
            raise RelationBindingError(
                f"Entity {entity_id!r} has conflicting compiled input "
                f"scopes {sorted(previous | options)!r}"
            )
        options_by_id[entity_id] = compatible

    records = result.get("dataset", {}).get("inputs", [])
    for record in records:
        constrain(record["entity_id"], input_kinds.get(record["name"], set()))
        if record.get("entity") and record["entity"] != "Entity":
            constrain(record["entity_id"], {record["entity"]})
    for query in result.get("queries", []):
        for output in query.get("outputs", []):
            constrain(query["entity_id"], output_kinds.get(output, set()))
    # A canonical input slot can be used by multiple entity scopes. Those
    # scopes are alternatives until labels, queries or relations distinguish
    # the request's particular ID; they are not conflicting observed labels.
    kinds_by_id: dict[str, set[str]] = defaultdict(set)
    for entity_id, options in options_by_id.items():
        if len(options) == 1:
            kinds_by_id[entity_id].update(options)
    # A count can execute without reading any member input. Recover that
    # member's kind from an already known owner and the executable relation
    # kinds. Every compatible ordering must agree before assigning a kind.
    pending = result.get("dataset", {}).get("relations", [])
    changed = True
    while changed:
        changed = False
        for record in pending:
            ids = record.get("tuple", [])
            schema = relations.schema(record["name"])
            if len(ids) != 2 or schema is None or schema.get("arity", 2) != 2:
                continue
            expected = relations.expected(record["name"])
            if expected is None or len(expected) != 2:
                continue
            candidates = [
                order
                for order in ([0, 1], [1, 0])
                if all(
                    not (kinds_by_id[ids[index]] or options_by_id.get(ids[index]))
                    or expected[slot] is None
                    or expected[slot]
                    in (kinds_by_id[ids[index]] or options_by_id[ids[index]])
                    for slot, index in enumerate(order)
                )
            ]
            for index, entity_id in enumerate(ids):
                if kinds_by_id[entity_id] or not candidates:
                    continue
                compatible = {expected[order.index(index)] for order in candidates}
                if (
                    len(compatible) == 1
                    and None not in compatible
                    and "Scalar" not in compatible
                ):
                    kinds_by_id[entity_id].update(compatible)
                    changed = True
    for record in records:
        kinds = kinds_by_id[record["entity_id"]]
        if len(kinds) > 1:
            raise RelationBindingError(
                f"Entity {record['entity_id']!r} has conflicting compiled input "
                f"scopes {sorted(kinds)!r}"
            )
        if kinds:
            record["entity"] = next(iter(kinds))
    return result
