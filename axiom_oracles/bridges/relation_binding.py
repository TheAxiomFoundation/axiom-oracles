"""Order relation tuples using the target artifact's executable entity slots.

Declarations are positional only for unused relations. In particular, an older
artifact can declare [TaxUnit, Person] while its count still uses current_slot=1.
This module reads that executable metadata; it does not evaluate any rules.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


class RelationBindingError(ValueError):
    """A producer cannot determine a safe tuple order from the artifact."""


def _fragment(name: str) -> str:
    return name.rsplit("#", 1)[-1].removeprefix("relation.")


class _ArtifactRelations:
    def __init__(self, artifact: dict[str, Any]):
        program = artifact.get("program", artifact)
        self.schemas = {
            relation["name"]: relation for relation in program.get("relations", [])
        }
        self.rules = {}
        for rule in program.get("derived", []):
            self.rules[rule["name"]] = rule
            if rule.get("id"):
                self.rules[rule["id"]] = rule
        self.usages: dict[str, list[list[str | None]]] = defaultdict(list)
        for rule in program.get("derived", []):
            # The engine ignores base semantics when explicit versions exist.
            for version in rule.get("versions") or [rule]:
                self._walk(version.get("expr", {}), rule.get("entity"))
        for schema in self.schemas.values():
            derivation = schema.get("derivation")
            if derivation:
                current, related = self._slots(derivation)
                kinds = derivation.get("slot_entities", [])
                owner = kinds[current] if current < len(kinds) else None
                member = kinds[related] if related < len(kinds) else None
                self._record(
                    derivation["source_relation"], current, related, owner, member
                )
                self._walk(
                    derivation.get("predicate", {}), member, (owner, member)
                )

    def schema(self, name: str) -> dict[str, Any] | None:
        if name in self.schemas:
            return self.schemas[name]
        matches = [
            schema
            for key, schema in self.schemas.items()
            if schema.get("id") == name or _fragment(key) == _fragment(name)
        ]
        if len(matches) > 1:
            raise RelationBindingError(f"Ambiguous artifact relation {name!r}")
        return matches[0] if matches else None

    @staticmethod
    def _slots(node: dict[str, Any]) -> tuple[int, int]:
        current, related = node.get("current_slot"), node.get("related_slot")
        if (
            not isinstance(current, int)
            or not isinstance(related, int)
            or min(current, related) < 0
            or current == related
        ):
            raise RelationBindingError(
                f"Expected distinct nonnegative relation slots, got "
                f"{current!r} and {related!r}"
            )
        return current, related

    def _record(
        self,
        name: str,
        current: int,
        related: int,
        owner: str | None,
        member: str | None,
        stack: tuple[str, ...] = (),
    ) -> list[str | None]:
        schema = self.schema(name)
        arity = schema.get("arity", 2) if schema else max(current, related) + 1
        if max(current, related) >= arity:
            raise RelationBindingError(f"Executable slots exceed arity for {name!r}")
        kinds: list[str | None] = [None] * arity
        kinds[current], kinds[related] = owner, member
        if schema is None:
            return kinds
        declared = schema.get("slot_entities", [])
        if len(declared) == arity and kinds.count(None) == 1:
            remaining = list(declared)
            for known in (kind for kind in kinds if kind is not None):
                if known not in remaining:
                    break
                remaining.remove(known)
            else:
                kinds[kinds.index(None)] = remaining[0]
        key = schema["name"]
        self.usages[key].append(kinds)
        derivation = schema.get("derivation")
        if derivation and key not in stack:
            source_current, source_related = self._slots(derivation)
            self._record(
                derivation["source_relation"],
                source_current,
                source_related,
                kinds[current],
                kinds[related],
                (*stack, key),
            )
        return kinds

    def _referenced_kind(self, node: Any) -> str | None:
        kinds: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                kind = value.get("kind")
                if kind in {"count_related", "sum_related", "relation_member"}:
                    return
                if kind == "derived":
                    rule = self.rules.get(value.get("name"), {})
                    entity = rule.get("entity")
                    if entity and entity != "Scalar":
                        kinds.add(entity)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(node)
        return next(iter(kinds)) if len(kinds) == 1 else None

    def _walk(
        self,
        node: Any,
        entity: str | None,
        context: tuple[str | None, str | None] | None = None,
    ) -> None:
        if isinstance(node, list):
            for child in node:
                self._walk(child, entity, context)
        elif isinstance(node, dict):
            kind = node.get("kind")
            if kind in {"count_related", "sum_related", "relation_member"}:
                current, related = self._slots(node)
                owner = entity
                member = None
                schema = self.schema(node["relation"])
                if kind == "relation_member":
                    owner, member = context or (entity, None)
                else:
                    derivation = (schema or {}).get("derivation") or {}
                    if entity is not None and derivation.get("entity") == entity:
                        structural = derivation.get("slot_entities", [])
                        if current < len(structural):
                            owner = structural[current]
                    member = self._referenced_kind(
                        [node.get("value"), node.get("where")]
                    )
                kinds = self._record(
                    node["relation"], current, related, owner, member
                )
                if kind != "relation_member":
                    self._walk(node.get("where"), kinds[related])
                return
            # A derivation's pair context belongs to judgment membership.
            # Comparisons enter scalar expressions, whose conditional
            # judgments use the current entity, not that outer pair context.
            child_context = None if kind in {"comparison", "if"} else context
            for child in node.values():
                self._walk(child, entity, child_context)

    def expected(self, name: str) -> list[str | None] | None:
        schema = self.schema(name)
        if schema is None:
            return None
        if schema.get("arity", 2) != 2:
            raise RelationBindingError(f"Relation {name!r} is not a two-slot relation")
        declared = schema.get("slot_entities", [])
        if declared and len(declared) != 2:
            raise RelationBindingError(f"Invalid slot_entities for relation {name!r}")
        usages = self.usages.get(schema["name"])
        if not usages:
            return list(declared) if declared else None
        result: list[str | None] = []
        for slot in range(2):
            candidates = {kinds[slot] for kinds in usages if kinds[slot] is not None}
            if len(candidates) > 1:
                raise RelationBindingError(
                    f"Conflicting executable kinds for relation {name!r} "
                    f"slot {slot}: {sorted(candidates)!r}"
                )
            result.append(next(iter(candidates)) if candidates else None)
        return result


def _ordered_tuple(
    name: str,
    expected: list[str | None],
    ids: list[str],
    kinds: list[str | None],
    *,
    preserve_ambiguous: bool = False,
) -> list[str]:
    candidates = [
        order
        for order in ([0, 1], [1, 0])
        if all(
            expected[slot] is None
            or (preserve_ambiguous and kinds[index] is None)
            or expected[slot] == kinds[index]
            for slot, index in enumerate(order)
        )
    ]
    if preserve_ambiguous and candidates:
        # Old artifacts can count members without reading any member inputs.
        # Prefer the orientation supported by known labels, while retaining
        # the existing tuple if absent labels leave both orders unresolved.
        scores = [
            sum(
                expected[slot] is not None and expected[slot] == kinds[index]
                for slot, index in enumerate(order)
            )
            for order in candidates
        ]
        candidates = [
            order
            for order, score in zip(candidates, scores, strict=True)
            if score == max(scores)
        ]
        if len(candidates) == 2:
            return list(ids)
    if (
        len(candidates) == 2
        and kinds[0] == kinds[1]
        and any(kind is not None for kind in expected)
    ):
        # Equal-kind slots carry no evidence for exchanging the existing ids.
        return list(ids)
    if len(candidates) != 1:
        raise RelationBindingError(
            f"Cannot unambiguously order relation {name!r}: executable slot kinds "
            f"{expected!r}, supplied entity kinds {kinds!r}"
        )
    return [ids[index] for index in candidates[0]]


def relation_tuple(
    artifact: dict[str, Any] | None,
    name: str,
    *,
    owner_id: str,
    owner_kind: str,
    related_id: str,
    related_kind: str,
    legacy_owner_slot: int = 1,
) -> list[str]:
    """Build a two-slot tuple, retaining the legacy order without metadata."""
    if legacy_owner_slot not in (0, 1):
        raise RelationBindingError("legacy_owner_slot must be 0 or 1")
    ids = [related_id, owner_id] if legacy_owner_slot == 1 else [owner_id, related_id]
    if artifact is None:
        return ids
    expected = _ArtifactRelations(artifact).expected(name)
    if expected is None:
        return ids
    kinds = (
        [related_kind, owner_kind]
        if legacy_owner_slot == 1
        else [owner_kind, related_kind]
    )
    return _ordered_tuple(name, expected, ids, kinds)


def bind_request_relations(
    request: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    """Return a copy with typed relation records ordered by executable usage.

    Call after resolving request relation names against the artifact. Released
    untyped artifacts retain their related-first order through executable slots.
    Input labels are authoritative; conflicting or missing kinds are errors for
    typed tuples because the producer cannot safely infer an order from ids.
    Untyped artifacts can count members without member inputs: use the known
    labels when they determine an order, otherwise retain the supplied tuple.
    """
    result = deepcopy(request)
    records = result.get("dataset", {}).get("relations", [])
    if not records:
        return result
    relations = _ArtifactRelations(artifact)
    labels: dict[str, set[str]] = defaultdict(set)
    for record in result.get("dataset", {}).get("inputs", []):
        if "entity_id" in record and "entity" in record:
            labels[record["entity_id"]].add(record["entity"])
    for record in records:
        name = record["name"]
        schema = relations.schema(name)
        if schema is None or schema.get("arity", 2) != 2:
            continue
        expected = relations.expected(name)
        if expected is None:
            continue
        ids = record["tuple"]
        if len(ids) != 2:
            raise RelationBindingError(f"Relation {name!r} requires a two-slot tuple")
        kinds = []
        untyped = not schema.get("slot_entities")
        for entity_id in ids:
            possible = labels.get(entity_id, set())
            if len(possible) > 1 or (not possible and not untyped):
                raise RelationBindingError(
                    f"Relation {name!r} entity {entity_id!r} needs one input entity "
                    f"kind; got {sorted(possible)!r}"
                )
            kinds.append(next(iter(possible)) if possible else None)
        record["tuple"] = _ordered_tuple(
            name, expected, ids, kinds, preserve_ambiguous=untyped
        )
    return result
