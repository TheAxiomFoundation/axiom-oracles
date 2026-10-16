"""Bind binary relations by the rules engine's declared entity typing.

Typed relations inherit kinds only along their source chain. Input and query
labels provide runtime identity evidence; conflicting labels are unknown.
Untyped relations retain their supplied order and warn when executed. Artifacts
whose declarations contradict direct aggregate slots must be recompiled or
migrated, rather than repaired by this binder.
"""

from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any
import warnings


class RelationBindingError(ValueError):
    """A producer cannot determine a safe tuple order from the artifact."""


class RelationBindingAmbiguityWarning(UserWarning):
    """The supplied tuple was preserved because its order is undetermined."""

    def __init__(self, relation: str, ids: list[str]):
        self.relation = relation
        self.tuple = tuple(ids)
        super().__init__(
            f"Relation {relation!r} tuple {ids!r} has no determined slot order; "
            "preserving the supplied tuple"
        )


def _fragment(name: str) -> str:
    return name.rsplit("#", 1)[-1].removeprefix("relation.")


def _named_records(program: dict[str, Any], key: str) -> dict[str, dict]:
    records = program.get(key, [])
    return (
        records
        if isinstance(records, dict)
        else {node["name"]: node for node in records}
    )


def _effective_slot_entities(program: dict[str, Any], name: str) -> list[str] | None:
    """Port relation_typing.rs:148-182 at engine 97dee1004b2c.

    A derivation's declaration wins, then its schema's declaration, then its
    source. Incoming derivations never type a source relation.
    """
    schemas = _named_records(program, "relations")
    visited = set()
    while name not in visited:
        visited.add(name)
        schema = schemas.get(name)
        if schema is None:
            return None
        derivation = schema.get("derivation") or {}
        if derivation.get("slot_entities"):
            return list(derivation["slot_entities"])
        if schema.get("slot_entities"):
            return list(schema["slot_entities"])
        if not derivation:
            return None
        name = derivation.get("source_relation")
    return None


def _filtered_entity_kinds(program: dict[str, Any]) -> dict[str, str]:
    """Port relation_typing.rs:214-312 at engine 97dee1004b2c.

    Only derived relations with an entity contribute current-slot kinds.
    Conflicts and cycles are unmapped; a self filter resolves to itself.
    """
    known: dict[str, set[str]] = defaultdict(set)
    for name, schema in _named_records(program, "relations").items():
        derivation = schema.get("derivation") or {}
        entity = derivation.get("entity")
        if entity is None:
            continue
        kinds = _effective_slot_entities(program, name)
        current = derivation.get("current_slot")
        if kinds is not None and isinstance(current, int) and 0 <= current < len(kinds):
            known[entity].add(kinds[current])
    direct = {
        entity: next(iter(kinds)) for entity, kinds in known.items() if len(kinds) == 1
    }
    resolved: dict[str, str | None] = {}
    for entity in direct:
        path, visited = [], set()
        kind = entity
        while True:
            if kind in resolved:
                result = resolved[kind]
                break
            if kind in visited:
                result = None
                break
            visited.add(kind)
            path.append(kind)
            target = direct.get(kind)
            if target is None or target == kind:
                result = kind
                break
            kind = target
        for item in path:
            resolved[item] = result
    return {
        entity: resolved[entity] for entity in direct if resolved[entity] is not None
    }


def _expression_children(node: dict) -> Iterable[Any]:
    """Only variant operands deserialize as expressions (spec.rs:1070-1435)."""
    fields = {
        "parameter_lookup": ("index",),
        "add": ("items",),
        "max": ("items",),
        "min": ("items",),
        "sub": ("left", "right"),
        "mul": ("left", "right"),
        "div": ("left", "right"),
        "comparison": ("left", "right"),
        "ceil": ("value",),
        "floor": ("value",),
        "date_add_days": ("date", "days"),
        "date_add_months": ("date", "months"),
        "date_add_years": ("date", "years"),
        "days_between": ("from", "to"),
        "count_related": ("where",),
        "sum_related": ("where",),
        "if": ("condition", "then_expr", "else_expr"),
        "no_match": ("subject", "patterns"),
        "over_periods": ("value", "n"),
        "and": ("items",),
        "or": ("items",),
        "not": ("item",),
        "exactly_one": ("items",),
    }
    return (node.get(key) for key in fields.get(node.get("kind"), ()))


def _execution_nodes(node: Any) -> Iterable[dict]:
    """Visit the engine's scalar/judgment operands, including no_match patterns."""
    pending = [node]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(reversed(value))
        elif isinstance(value, dict):
            yield value
            pending.extend(reversed(list(_expression_children(value))))


def _executed_relations(
    program: dict[str, Any], *, include_base: bool = False
) -> set[str]:
    """Port executed_relations: all versioned rules, then reached sources/predicates."""
    used = set()
    pending = []

    def collect(expr: Any) -> None:
        for node in _execution_nodes(expr):
            if node.get("kind") in {"count_related", "sum_related", "relation_member"}:
                name = node.get("relation")
                if name is not None and name not in used:
                    used.add(name)
                    pending.append(name)

    for rule in _named_records(program, "derived").values():
        versions = (
            [rule, *rule.get("versions", [])]
            if include_base
            else rule.get("versions") or [rule]
        )
        for version in versions:
            collect(version.get("expr"))
    schemas = _named_records(program, "relations")
    while pending:
        derivation = (schemas.get(pending.pop()) or {}).get("derivation") or {}
        source = derivation.get("source_relation")
        if source is not None and source not in used:
            used.add(source)
            pending.append(source)
        collect(derivation.get("predicate"))
    return used


class _ArtifactRelations:
    def __init__(self, artifact: dict[str, Any]):
        self.program = artifact.get("program", artifact)
        self.schemas = _named_records(self.program, "relations")
        self.rules = _named_records(self.program, "derived")
        self.filtered_kinds = _filtered_entity_kinds(self.program)
        self.executed = _executed_relations(self.program)
        self._typing_relations = _executed_relations(self.program, include_base=True)
        self._expected_by_name: dict[str, list[str] | None] = {}
        self._validated_relations: set[str] = set()

    def canonical(self, kind: str) -> str:
        return self.filtered_kinds.get(kind, kind)

    def schema(self, name: str) -> dict[str, Any] | None:
        if name in self.schemas:
            return self.schemas[name]
        # model.rs:640-658 resolves a public reference to a bare key only.
        # Searching all matching fragments lets unrelated declarations interfere.
        if not any(
            rule.get("id") is not None for rule in self.rules.values()
        ) and not any(
            item.get("id") is not None
            for item in _named_records(self.program, "parameters").values()
        ):
            return None
        target, separator, fragment = name.partition("#")
        if not separator or not fragment.startswith("relation.") or "#" in fragment:
            return None
        # PublicReference::parse and validate_module_target (rulespec.rs:1229-1266).
        prefix, colon, relative = target.partition(":")
        segments = relative.split("/")
        if (
            not colon
            or not re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]+)*", prefix)
            or len(segments) < 2
            or segments[0] not in {"legislation", "policies", "regulations", "statutes"}
            or any(
                segment in {"", ".", ".."}
                or not re.fullmatch(r"[A-Za-z0-9_.~\-]+", segment)
                for segment in segments
            )
            or segments[-1].lower().endswith((".yaml", ".yml", ".test"))
            or name != name.strip()
        ):
            return None
        return self.schemas.get(fragment.removeprefix("relation."))

    def expected(self, name: str) -> list[str] | None:
        schema = self.schema(name)
        if schema is None:
            return None
        key = schema["name"]
        if key not in self._expected_by_name:
            if schema.get("arity", 2) != 2:
                raise RelationBindingError(
                    f"Relation {name!r} is not a two-slot relation"
                )
            # spec.rs:617-633 checks schema declarations even when a
            # derivation overrides them with a different effective list.
            declared = schema.get("slot_entities")
            if declared and len(declared) != 2:
                raise RelationBindingError(
                    f"Invalid slot_entities for relation {name!r}"
                )
            kinds = _effective_slot_entities(self.program, key)
            # relation_typing.rs:637 checks effective counts only when the
            # program types a use, including base semantics of versioned rules.
            if kinds is not None and len(kinds) != 2 and key in self._typing_relations:
                raise RelationBindingError(
                    f"Invalid slot_entities for relation {name!r}"
                )
            self._expected_by_name[key] = (
                [self.canonical(kind) for kind in kinds] if kinds is not None else None
            )
        expected = self._expected_by_name[key]
        return list(expected) if expected is not None else None

    def validate_direct_aggregates(self, name: str, expected: list[str]) -> None:
        """Reject a pre-typing artifact's contradiction; never infer from usage.

        Only the relation being bound is checked. Nested aggregate predicates
        run on the related slot's declared kind. This check has no input to
        expected(), identity classification, or tuple orientation.
        """
        schema = self.schema(name)
        target = schema["name"]
        if target in self._validated_relations:
            return
        scopes = []
        for rule in self.rules.values():
            # The engine validates base semantics as well as versions.
            for version in [rule, *rule.get("versions", [])]:
                scopes.append((version.get("expr"), rule.get("entity"), rule["name"]))
        for key in sorted(self._typing_relations):
            derivation = (self.schemas.get(key) or {}).get("derivation") or {}
            kinds = _effective_slot_entities(self.program, key)
            related = derivation.get("related_slot")
            member = (
                kinds[related]
                if kinds is not None
                and isinstance(related, int)
                and 0 <= related < len(kinds)
                else None
            )
            scopes.append((derivation.get("predicate"), member, key))
        while scopes:
            value, entity, citing = scopes.pop()
            if isinstance(value, list):
                scopes.extend((child, entity, citing) for child in value)
            elif isinstance(value, dict):
                kind = value.get("kind")
                if kind in {"count_related", "sum_related"}:
                    relation = value.get("relation")
                    current = value.get("current_slot")
                    related = value.get("related_slot")
                    kinds = _effective_slot_entities(self.program, relation)
                    if (
                        relation == target
                        and entity is not None
                        and (
                            not isinstance(current, int)
                            or not 0 <= current < len(expected)
                            or self.canonical(entity) != expected[current]
                        )
                    ):
                        raise RelationBindingError(
                            f"Relation {name!r} declares slot kinds {expected!r}, "
                            f"but aggregate in {citing!r} uses current_slot="
                            f"{current!r} for entity {entity!r}; recompile or "
                            "`axiom-rules-engine migrate artifact`"
                        )
                    member = (
                        kinds[related]
                        if kinds is not None
                        and isinstance(related, int)
                        and 0 <= related < len(kinds)
                        else None
                    )
                    scopes.append((value.get("where"), member, citing))
                else:
                    scopes.extend(
                        (child, entity, citing) for child in _expression_children(value)
                    )
        self._validated_relations.add(target)

    def wrapper_owner_slot(self, name: str) -> int | None:
        """Use only unanimous same-kind wrapper directions reaching this source."""
        slots = set()
        for schema in self.schemas.values():
            derivation = schema.get("derivation") or {}
            source = derivation.get("source_relation")
            visited = {schema["name"]}
            while source is not None and source not in visited:
                if source == name:
                    current = derivation.get("current_slot")
                    if current in (0, 1):
                        slots.add(current)
                    break
                visited.add(source)
                source = ((self.schemas.get(source) or {}).get("derivation") or {}).get(
                    "source_relation"
                )
        return next(iter(slots)) if len(slots) == 1 else None

    def query_evidence(self, queries: list[dict]) -> Iterable[tuple[str, str]]:
        # api.rs:387-405: entities come from resolved output rules, excluding scalar.
        for query in queries:
            for output in query.get("outputs", []):
                rule = next(
                    (item for item in self.rules.values() if item.get("id") == output),
                    None,
                )
                if rule is None:
                    candidate = self.rules.get(output)
                    rule = (
                        candidate if candidate and candidate.get("id") is None else None
                    )
                if rule and rule.get("entity") not in (None, "Scalar"):
                    yield query["entity_id"], rule["entity"]


@dataclass
class _CachedArtifactRelations:
    artifact: dict[str, Any]
    program_snapshot: dict[str, Any]
    analysis: _ArtifactRelations


_ARTIFACT_RELATION_CACHE: OrderedDict[int, _CachedArtifactRelations] = OrderedDict()
_MAX_CACHED_ARTIFACTS = 8


def _artifact_relation_analysis(artifact: dict[str, Any]) -> _ArtifactRelations:
    """Cache one analysis per immutable snapshot, observing in-place edits."""
    program = artifact.get("program", artifact)
    key = id(artifact)
    cached = _ARTIFACT_RELATION_CACHE.get(key)
    if (
        cached is None
        or cached.artifact is not artifact
        or program != cached.program_snapshot
    ):
        snapshot = deepcopy(program)
        cached = _CachedArtifactRelations(
            artifact, snapshot, _ArtifactRelations(snapshot)
        )
        _ARTIFACT_RELATION_CACHE[key] = cached
    _ARTIFACT_RELATION_CACHE.move_to_end(key)
    while len(_ARTIFACT_RELATION_CACHE) > _MAX_CACHED_ARTIFACTS:
        _ARTIFACT_RELATION_CACHE.popitem(last=False)
    return cached.analysis


def _ordered_tuple(
    name: str, expected: list[str], ids: list[str], kinds: list[str | None]
) -> list[str]:
    def clean(order: list[int]) -> bool:
        return all(
            # spec.rs:542 checks only declarations present for wire slots.
            slot >= len(expected)
            or kinds[index] is None
            or expected[slot] == kinds[index]
            for slot, index in enumerate(order)
        )

    supplied, swapped = clean([0, 1]), clean([1, 0])
    if supplied:
        if swapped and None in kinds:
            warnings.warn(RelationBindingAmbiguityWarning(name, ids), stacklevel=3)
        return list(ids)
    if swapped:
        return list(reversed(ids))
    raise RelationBindingError(
        f"Cannot order relation {name!r}: declared slot kinds {expected!r}, "
        f"supplied entity kinds {kinds!r}"
    )


class RelationBinder:
    """Bind tuples using one validated program snapshot for a request.

    Create a new binder at each request construction or binding boundary so
    in-place program edits between calls are observed. The captured analysis
    owns a detached snapshot, shared by every tuple and owner-kind lookup.
    """

    def __init__(self, artifact: dict[str, Any] | None):
        self._relations = (
            _artifact_relation_analysis(artifact) if artifact is not None else None
        )

    def owner_kind(
        self,
        name: str,
        *,
        default_owner_kind: str,
        related_kind: str,
    ) -> str:
        """Read a projected unit's physical kind from the relation's declared slots."""
        relations = self._relations
        if relations is None:
            return default_owner_kind
        expected = relations.expected(name)
        owner, related = (
            relations.canonical(default_owner_kind),
            relations.canonical(related_kind),
        )
        if expected is None:
            return default_owner_kind
        if owner in expected:
            return owner
        candidates = set(expected) - {related}
        if len(candidates) == 1:
            return next(iter(candidates))
        if expected == [related, related]:
            return related
        raise RelationBindingError(
            f"Cannot determine the owner kind for relation {name!r}"
        )

    def tuple(
        self,
        name: str,
        *,
        owner_id: str,
        owner_kind: str,
        related_id: str,
        related_kind: str,
        legacy_owner_slot: int = 1,
        binding_ambiguities: list[RelationBindingAmbiguityWarning] | None = None,
    ) -> list[str]:
        """Place explicit roles by engine typing; preserve untyped legacy order."""
        if legacy_owner_slot not in (0, 1):
            raise RelationBindingError("legacy_owner_slot must be 0 or 1")
        ids = (
            [related_id, owner_id] if legacy_owner_slot == 1 else [owner_id, related_id]
        )
        relations = self._relations
        if relations is None:
            return ids
        expected = relations.expected(name)
        schema = relations.schema(name)
        if expected is None:
            if schema and schema["name"] in relations.executed:
                _report_ambiguity(name, ids, binding_ambiguities)
            return ids
        relations.validate_direct_aggregates(name, expected)
        owner, related = (
            relations.canonical(owner_kind),
            relations.canonical(related_kind),
        )
        if expected == [owner, owner] and owner == related:
            slot = relations.wrapper_owner_slot(schema["name"])
            if slot is None:
                _report_ambiguity(name, ids, binding_ambiguities)
                return ids
            return [owner_id, related_id] if slot == 0 else [related_id, owner_id]
        kinds = [related, owner] if legacy_owner_slot == 1 else [owner, related]
        return _ordered_tuple(name, expected, ids, kinds)


def relation_owner_kind(
    artifact: dict[str, Any],
    name: str,
    *,
    default_owner_kind: str,
    related_kind: str,
) -> str:
    """Read a projected unit's physical kind from the relation's declared slots."""
    return RelationBinder(artifact).owner_kind(
        name, default_owner_kind=default_owner_kind, related_kind=related_kind
    )


def _report_ambiguity(
    name: str,
    ids: list[str],
    collected: list[RelationBindingAmbiguityWarning] | None = None,
) -> None:
    report = RelationBindingAmbiguityWarning(name, ids)
    if collected is None:
        warnings.warn(report, stacklevel=3)
    else:
        collected.append(report)


def relation_tuple(
    artifact: dict[str, Any] | None,
    name: str,
    *,
    owner_id: str,
    owner_kind: str,
    related_id: str,
    related_kind: str,
    legacy_owner_slot: int = 1,
    binding_ambiguities: list[RelationBindingAmbiguityWarning] | None = None,
) -> list[str]:
    """Place explicit roles by engine typing; preserve untyped legacy order."""
    return RelationBinder(artifact).tuple(
        name,
        owner_id=owner_id,
        owner_kind=owner_kind,
        related_id=related_id,
        related_kind=related_kind,
        legacy_owner_slot=legacy_owner_slot,
        binding_ambiguities=binding_ambiguities,
    )


def bind_request_relations(
    request: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    """Copy a request, preserving every supplied order the engine would accept.

    A swap requires a known mismatch in the supplied order and none after
    swapping. Input and query labels use engine canonical kinds; an ID with
    conflicting labels stays unknown. No usage or incoming derivation can
    supply expected kinds or identity evidence.
    """
    result = deepcopy(request)
    records = result.get("dataset", {}).get("relations", [])
    if not records:
        return result
    binder = RelationBinder(artifact)
    relations = binder._relations
    entity_by_id: dict[str, str | None] = {}
    evidence = [
        (record["entity_id"], record["entity"])
        for record in result.get("dataset", {}).get("inputs", [])
        if "entity_id" in record and "entity" in record
    ]
    evidence.extend(relations.query_evidence(result.get("queries", [])))
    for entity_id, entity in evidence:
        entity = relations.canonical(entity)
        if entity_id in entity_by_id and entity_by_id[entity_id] != entity:
            entity_by_id[entity_id] = None
        else:
            entity_by_id[entity_id] = entity
    checked = set()
    for record in records:
        name = record["name"]
        if "roles" in record:
            record["tuple"] = binder.tuple(name, **record["roles"])
            continue
        schema = relations.schema(name)
        if schema is None or schema.get("arity", 2) != 2:
            continue
        expected = relations.expected(name)
        ids = record.get("tuple", [])
        if expected is None:
            if schema["name"] in relations.executed:
                warnings.warn(RelationBindingAmbiguityWarning(name, ids), stacklevel=2)
            continue
        if len(ids) != 2:
            raise RelationBindingError(f"Relation {name!r} requires a two-slot tuple")
        if schema["name"] not in checked:
            relations.validate_direct_aggregates(name, expected)
            checked.add(schema["name"])
        record["tuple"] = _ordered_tuple(
            name, expected, ids, [entity_by_id.get(i) for i in ids]
        )
    return result


RELATION_BINDING_SAMPLE_LIMIT = 20


def bind_materialized_relations(
    request: dict[str, Any],
    artifact: dict[str, Any],
    *,
    materialized: set[int],
    binder: Callable = bind_request_relations,
) -> tuple[dict[str, Any], list[RelationBindingAmbiguityWarning]]:
    """Bind raw tuples and capture every ambiguity, including repeats.

    The indexes identify records already constructed from explicit roles.
    Neither diagnostics nor role metadata is added to the engine request.
    """
    records = request.get("dataset", {}).get("relations", [])
    if not records or len(materialized) == len(records):
        return request, []
    pending = {
        **request,
        "dataset": {
            **request["dataset"],
            "relations": [
                record
                for index, record in enumerate(records)
                if index not in materialized
            ],
        },
    }
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", RelationBindingAmbiguityWarning)
        bound = binder(pending, artifact)
    raw_records = iter(bound["dataset"]["relations"])
    bound["dataset"]["relations"] = [
        record if index in materialized else next(raw_records)
        for index, record in enumerate(records)
    ]
    return bound, [
        report.message
        for report in captured
        if isinstance(report.message, RelationBindingAmbiguityWarning)
    ]


def relation_binding_diagnostics(
    ambiguities: Iterable[RelationBindingAmbiguityWarning],
    *,
    namespace: str | None = None,
    entity_id: str | None = None,
) -> dict[str, Any]:
    """Count all matching tuples while retaining at most twenty examples."""
    counts: Counter[str] = Counter()
    samples = []
    for ambiguity in ambiguities:
        if namespace is not None and not any(
            value.startswith(namespace) for value in ambiguity.tuple
        ):
            continue
        if entity_id is not None and entity_id not in ambiguity.tuple:
            continue
        counts[ambiguity.relation] += 1
        if len(samples) < RELATION_BINDING_SAMPLE_LIMIT:
            samples.append(
                {"relation": ambiguity.relation, "tuple": list(ambiguity.tuple)}
            )
    return {
        "count": sum(counts.values()),
        "by_relation": dict(counts),
        "samples": samples,
    }


def merge_relation_binding_diagnostics(target: dict, source: dict) -> None:
    """Accumulate counts across batches without deduplicating occurrences."""
    target["count"] = target.get("count", 0) + source.get("count", 0)
    counts = Counter(target.get("by_relation", {}))
    counts.update(source.get("by_relation", {}))
    target["by_relation"] = dict(counts)
    target["samples"] = (target.get("samples", []) + source.get("samples", []))[
        :RELATION_BINDING_SAMPLE_LIMIT
    ]


def public_relation_binding_diagnostics(source: dict[str, Any]) -> dict[str, Any]:
    """Publish counts and bounded relation names without request identifiers.

    Exact endpoint samples remain in native execution evidence. Namespace
    aliases can contain caller data, so only a bounded identifier fragment is
    retained; other names share a redacted bucket whose counts are summed.
    """

    def safe_name(name: Any) -> str:
        fragment = _fragment(name) if isinstance(name, str) else ""
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}", fragment):
            return fragment
        return "redacted_relation"

    counts: Counter[str] = Counter()
    for name, count in source.get("by_relation", {}).items():
        counts[safe_name(name)] += count
    return {
        "count": source.get("count", 0),
        "by_relation": dict(counts),
        "samples": [
            {"relation": safe_name(sample.get("relation"))}
            for sample in source.get("samples", [])[:RELATION_BINDING_SAMPLE_LIMIT]
        ],
    }


def attach_relation_binding_diagnostics(
    results: list[dict],
    ambiguities: list[RelationBindingAmbiguityWarning],
) -> None:
    """Attach every occurrence once, including tuples without a queried id.

    Prefer the first result whose entity is an endpoint. Unattributed request
    diagnostics accompany the first result rather than disappearing.
    """
    if not results or not ambiguities:
        return
    indexes = {}
    for index, result in enumerate(results):
        indexes.setdefault(result.get("entity_id"), index)
    groups: dict[int, list[RelationBindingAmbiguityWarning]] = defaultdict(list)
    for ambiguity in ambiguities:
        matches = [indexes[value] for value in ambiguity.tuple if value in indexes]
        groups[min(matches) if matches else 0].append(ambiguity)
    for index, group in groups.items():
        results[index]["relation_binding_diagnostics"] = relation_binding_diagnostics(
            group
        )


def with_relation_binding_diagnostics(raw: Any, diagnostics: dict) -> Any:
    """Keep successful and failed execution evidence alongside diagnostics."""
    if not diagnostics.get("count"):
        return raw
    return {
        **(raw if isinstance(raw, dict) else {"response": raw}),
        "relation_binding_diagnostics": diagnostics,
    }
