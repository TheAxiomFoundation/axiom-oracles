"""Order relation tuples using the target artifact's executable entity slots.

Declarations are positional only for unused relations. In particular, an older
artifact can declare [TaxUnit, Person] while its count still uses current_slot=1.
This module reads that executable metadata; it does not evaluate any rules.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any
import warnings


# Generic projection keys these entity kinds by a household id. Other scopes
# can broadcast inputs to Person ids without describing endpoint identities.
UNIT_ENTITY_KINDS = frozenset({
    "Household", "SnapUnit", "TaxUnit", "SpmUnit", "TanfUnit",
    "AssistanceUnit", "Family",
})


class RelationBindingError(ValueError):
    """A producer cannot determine a safe tuple order from the artifact."""


class RelationBindingAmbiguityWarning(UserWarning):
    """Both orientations are compatible; the supplied tuple was preserved.

    Callers can capture this warning or promote it to an error with the
    standard warnings API without adding reporting fields to the request.
    """

    def __init__(self, relation: str, ids: list[str]):
        self.relation = relation
        self.tuple = tuple(ids)
        super().__init__(
            f"Relation {relation!r} tuple {ids!r} has no determined slot order; "
            "preserving the supplied tuple"
        )


def _fragment(name: str) -> str:
    return name.rsplit("#", 1)[-1].removeprefix("relation.")


class _ArtifactRelations:
    def __init__(
        self, artifact: dict[str, Any], *,
        identity_pairs: dict[str, list[list[set[str]]]] | None = None,
        constructor_hint: tuple[str, str, str] | None = None,
    ):
        program = artifact.get("program", artifact)
        self.schemas = {
            relation["name"]: relation for relation in program.get("relations", [])
        }
        self.declared_kinds = {
            kind
            for schema in self.schemas.values()
            for slots in (
                schema.get("slot_entities", []),
                (schema.get("derivation") or {}).get("slot_entities", []),
            )
            for kind in slots
        }
        self.rules = {}
        for rule in program.get("derived", []):
            self.rules[rule["name"]] = rule
            if rule.get("id"):
                self.rules[rule["id"]] = rule
        self.identity_pairs = identity_pairs or {}
        self.constructor_hint = constructor_hint
        self.usages: dict[str, list[list[str | None]]] = defaultdict(list)
        self.owner_slots: dict[str, set[int]] = defaultdict(set)
        self.executable_kinds: set[str] = set()
        self._read_usages(program)
        # Direct aggregate owners and structural pairs prove endpoint kinds
        # before scalar references use them, independently of rule order.
        self.executable_kinds = self.endpoint_kinds()
        self.usages.clear()
        self.owner_slots.clear()
        self._read_usages(program)

    def _constructor_kinds(self, name: str) -> tuple[str, str] | None:
        if self.constructor_hint:
            target, owner, member = self.constructor_hint
            schema = self.schema(name)
            if schema is not None and schema is self.schema(target):
                return owner, member
        return None

    def _related_identity(self, name: str, owner: str | None) -> str | None:
        """A row context is known only if every compatible role assignment agrees."""
        if owner is None:
            return None
        schema = self.schema(name)
        inferred: set[str] = set()
        for supplied_name, pairs in self.identity_pairs.items():
            if schema is None or self.schema(supplied_name) is not schema:
                continue
            for pair in pairs:
                known = [labels & self.executable_kinds for labels in pair]
                if len(known) != 2 or any(len(kinds) > 1 for kinds in known):
                    return None
                candidates = {
                    next(iter(known[1 - index])) if known[1 - index] else None
                    for index in (0, 1)
                    if not known[index] or owner in known[index]
                }
                if len(candidates) != 1 or None in candidates:
                    return None
                inferred.update(candidates)
        return next(iter(inferred)) if len(inferred) == 1 else None

    def _read_usages(self, program: dict[str, Any]) -> None:
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
        constructor_kinds = self._constructor_kinds(name)
        if constructor_kinds and (kinds[current], kinds[related]) == constructor_kinds:
            self.owner_slots[key].add(current)
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

        def depends_on_row(value: Any, stack: tuple[str, ...] = ()) -> bool:
            if isinstance(value, list):
                return any(depends_on_row(child, stack) for child in value)
            if not isinstance(value, dict):
                return False
            kind = value.get("kind")
            if kind == "no_match":
                return depends_on_row(value.get("subject"), stack)
            if kind == "derived":
                name = value.get("name")
                if name in stack:
                    return False
                rule = self.rules.get(name, {})
                return any(
                    depends_on_row(version.get("expr"), (*stack, name))
                    for version in rule.get("versions") or [rule]
                )
            if kind in {"input", "count_related", "sum_related", "relation_member"}:
                return True
            if kind in {"literal", "parameter", "period_start", "period_end", "input_or_else"}:
                # An optional input's default can run on any entity id.
                return False
            return any(depends_on_row(child, stack) for child in value.values())

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                kind = value.get("kind")
                if kind == "no_match":
                    # Patterns label errors; only subject is executed.
                    collect(value.get("subject"))
                    return
                if kind == "derived":
                    name = value.get("name")
                    rule = self.rules.get(name, {})
                    entity = rule.get("entity")
                    if (
                        entity in self.declared_kinds
                        or entity in self.executable_kinds
                        or entity == "Person"
                        or entity in UNIT_ENTITY_KINDS
                    ) and depends_on_row(value):
                        # Keep the referenced rule's execution scope: an alias
                        # may read an input with another broadcast scope.
                        kinds.add(entity)
                    return
                if kind in {"count_related", "sum_related", "relation_member"}:
                    # A nested aggregate's references concern another row.
                    return
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
            if kind == "no_match":
                self._walk(node.get("subject"), entity, context)
                return
            if kind in {"count_related", "sum_related", "relation_member"}:
                current, related = self._slots(node)
                owner = entity
                member = None
                member_scope = None
                schema = self.schema(node["relation"])
                constructor_kinds = self._constructor_kinds(node["relation"])
                if kind == "relation_member":
                    # Membership consumes the enclosing derived pair. Without
                    # that pair the engine rejects execution, so this node
                    # supplies no evidence about the relation's slot order.
                    if context is None:
                        return
                    owner, member = context
                else:
                    if owner is None and constructor_kinds:
                        owner = constructor_kinds[0]
                    derivation = (schema or {}).get("derivation") or {}
                    if entity is not None and derivation.get("entity") == entity:
                        structural = derivation.get("slot_entities", [])
                        if current < len(structural):
                            owner = structural[current]
                    member_scope = self._referenced_kind(
                        [node.get("value"), node.get("where")]
                    )
                    member = member_scope
                    declared = (schema or {}).get("slot_entities", [])
                    if len(declared) == 2 and owner in declared:
                        # The declaration's kind inventory is stronger than
                        # a scalar's scope, which can broadcast onto any id.
                        remaining = list(declared)
                        remaining.remove(owner)
                        member = remaining[0]
                    elif not declared:
                        identity = self._related_identity(node["relation"], owner)
                        if identity is None and constructor_kinds:
                            # A relation may also be traversed from its member
                            # toward its owner. The producer's roles still
                            # describe the same physical endpoint slots.
                            identity = (
                                constructor_kinds[0]
                                if owner == constructor_kinds[1]
                                and owner != constructor_kinds[0]
                                else constructor_kinds[1]
                            )
                        if identity is not None:
                            member = identity
                        elif self.identity_pairs:
                            # A scalar's execution scope is not proof of a
                            # request endpoint's identity, even for Person.
                            member = None
                kinds = self._record(
                    node["relation"], current, related, owner, member
                )
                if kind != "relation_member":
                    self._walk(
                        node.get("where"),
                        kinds[related] if self.identity_pairs or kinds[related] is not None
                        else member_scope,
                    )
                return
            # Scalar operands and conditions run on the same bound pair.
            # Only an aggregate's where clause starts a new entity context
            # (handled above without forwarding context).
            for child in node.values():
                self._walk(child, entity, context)

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

    def endpoint_kinds(self) -> set[str]:
        """Kinds the artifact identifies as relation endpoints, not input scopes."""
        kinds = set(self.declared_kinds)
        kinds.update(
            kind
            for usages in self.usages.values()
            for usage in usages
            for kind in usage
            if kind is not None
        )
        # The generic projector's member inventory is Person even when a
        # count-only artifact never reads a member input. Other input scopes
        # can be broadcast onto these ids, but a unit kind cannot identify
        # the same member as well.
        kinds.add("Person")
        return kinds


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
    if preserve_ambiguous and len(candidates) == 2:
        # A matching label is no evidence against the other orientation when
        # its endpoint is unknown. Preferences can corrupt a correct request.
        warnings.warn(RelationBindingAmbiguityWarning(name, ids), stacklevel=3)
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


def relation_owner_kind(
    artifact: dict[str, Any], name: str, *, default_owner_kind: str, related_kind: str,
) -> str:
    """Read a projected unit's real kind from the artifact's endpoint slots."""
    relations = _ArtifactRelations(artifact)
    schema = relations.schema(name)
    if schema is None:
        return default_owner_kind
    expected = relations.expected(name)
    if expected is None or default_owner_kind in expected:
        return default_owner_kind
    candidates = {kind for kind in expected if kind is not None and kind != related_kind}
    if len(candidates) == 1:
        return next(iter(candidates))
    if expected == [related_kind, related_kind]:
        return related_kind
    if None in expected and not candidates:
        return default_owner_kind
    raise RelationBindingError(f"Cannot determine the owner kind for relation {name!r}")


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
    relations = _ArtifactRelations(
        artifact, constructor_hint=(name, owner_kind, related_kind),
    )
    expected = relations.expected(name)
    if expected is None:
        return ids
    schema = relations.schema(name)
    if owner_kind == related_kind:
        slots = relations.owner_slots[schema["name"]]
        if len(slots) > 1:
            raise RelationBindingError(f"Conflicting executable owner slots for relation {name!r}")
        if slots:
            return [owner_id, related_id] if next(iter(slots)) == 0 else [related_id, owner_id]
    kinds = (
        [related_kind, owner_kind]
        if legacy_owner_slot == 1
        else [owner_kind, related_kind]
    )
    return _ordered_tuple(name, expected, ids, kinds)


def bind_request_relations(
    request: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    """Return a copy with relation records ordered by executable usage.

    Call after resolving request relation names against the artifact. Released
    untyped artifacts retain their related-first order through executable slots.
    Input entity labels also describe broadcast scopes, so multiple labels need
    not contradict an endpoint's identity. Conflicting known endpoint kinds
    are errors. Known labels constrain the executable slots. Repair is allowed
    only when those constraints exclude the other orientation. Otherwise the
    tuple stays byte-identical and a RelationBindingAmbiguityWarning names the
    relation and tuple. The caller's request is never mutated.
    """
    result = deepcopy(request)
    records = result.get("dataset", {}).get("relations", [])
    if not records:
        return result
    labels: dict[str, set[str]] = defaultdict(set)
    for record in result.get("dataset", {}).get("inputs", []):
        if "entity_id" in record and "entity" in record:
            labels[record["entity_id"]].add(record["entity"])
    identity_pairs: dict[str, list[list[set[str]]]] = defaultdict(list)
    for record in records:
        if len(record.get("tuple", [])) == 2:
            identity_pairs[record["name"]].append([
                labels.get(entity_id, set()) for entity_id in record["tuple"]
            ])
    relations = _ArtifactRelations(artifact, identity_pairs=identity_pairs)
    endpoint_kinds = relations.endpoint_kinds()
    scalar_scopes = {
        rule["entity"] for rule in relations.rules.values() if rule.get("entity")
    } - endpoint_kinds
    for record in records:
        name = record["name"]
        schema = relations.schema(name)
        if schema is None or schema.get("arity", 2) != 2:
            continue
        expected = relations.expected(name)
        if expected is None:
            if len(record.get("tuple", [])) == 2:
                warnings.warn(
                    RelationBindingAmbiguityWarning(name, record["tuple"]), stacklevel=2
                )
            continue
        ids = record["tuple"]
        if len(ids) != 2:
            raise RelationBindingError(f"Relation {name!r} requires a two-slot tuple")
        kinds = []
        untyped = not schema.get("slot_entities")
        for entity_id in ids:
            possible = labels.get(entity_id, set())
            identities = possible & endpoint_kinds
            if len(identities) > 1:
                raise RelationBindingError(
                    f"Relation {name!r} entity {entity_id!r} needs one input entity "
                    f"kind; got {sorted(identities)!r}"
                )
            if not untyped and len(possible) == 1 and not possible <= scalar_scopes:
                # A unique typed label must match unless the artifact proves
                # it is only a scalar scope, rather than an endpoint identity.
                kinds.append(next(iter(possible)))
            else:
                kinds.append(next(iter(identities)) if identities else None)
        record["tuple"] = _ordered_tuple(
            name, expected, ids, kinds, preserve_ambiguous=True
        )
    return result
