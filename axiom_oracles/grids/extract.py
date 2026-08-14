"""Reduce live suite ``Case`` objects to oracle-neutral grid skeletons.

Both the extractor script and the extraction-equivalence test import from
here, so a single definition of "the skeleton of a case" keeps them in
lock-step: the script *writes* grids from ``case_skeleton``; the test *reads*
grids back into the same skeleton shape and asserts equality against the live
suites. If the two ever disagreed, the test would fail — which is the whole
point of the byte-preserving guarantee.

The skeleton is everything an oracle-neutral description needs and nothing an
engine-specific projection adds. Concretely, from a
:class:`axiom_oracles.core.case.Case` it keeps:

* ``id`` / ``period`` / ``scenario`` / requested output concept ids;
* the Axiom query entity + entity id (from metadata, when set);
* the household as neutral entities (age + relation + any extra neutral facts);
* case-level neutral facts;
* the *scenario parameters* — the case metadata keys that are not the
  engine-projection payloads and not the redundant, already-captured entity
  or scope bookkeeping.

It drops ``axiom_inputs`` / explicit input records, ``euromod_inputs``,
``gettsim_case``, engine-result aggregation wiring,
``euromod_to_axiom_input_bridge`` and the ``*_applied`` evidence echoes — all
re-derivable from the skeleton by the suite factory.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.case import Case, Concepts, Entity

# Metadata keys that are per-engine projection payloads or bridge wiring — the
# derived layer a grid deliberately does not store.
_PROJECTION_METADATA_KEYS = frozenset(
    {
        "axiom_inputs",
        "axiom_input_records",
        "euromod_inputs",
        "gettsim_case",
        "euromod_to_axiom_input_bridge",
        "euromod_to_axiom_input_bridge_applied",
        "axiom_alias_qualified_inputs",
        "axiom_result_selection",
        "axiom_result_aggregation",
        "axiom_result_aggregation_applied",
    }
)

# Metadata keys captured elsewhere in the skeleton (entity/query/scope
# bookkeeping) or that are pure labels; excluded from scenario parameters so the
# parameter block holds only the genuinely varying, oracle-neutral inputs.
_STRUCTURAL_METADATA_KEYS = frozenset(
    {
        "locale",
        "scope",
        "axiom_entity",
        "axiom_entity_id",
        "scenario",
        "suite",
    }
)

# Short neutral names used for the two universal person facts in a grid entity,
# so a grid reads without concept-id noise. Any other entity fact is emitted
# under its own short key derived from the concept fragment.
_AGE_CONCEPT = Concepts.PERSON_AGE
_RELATION_CONCEPT = Concepts.HOUSEHOLD_RELATION

# Neutral entity facts beyond age/relation that suites set, mapped to a short
# grid key. Kept explicit (rather than string-munging the concept id) so the
# grid vocabulary is stable and reviewable.
_ENTITY_FACT_KEYS: dict[str, str] = {
    Concepts.YEARLY_EARNED_INCOME: "yearly_earned_income",
    Concepts.PREGNANT: "pregnant",
    Concepts.BLIND: "blind",
    Concepts.DISABLED: "disabled",
}

# Case-level neutral facts suites set, mapped to a short grid key.
_CASE_FACT_KEYS: dict[str, str] = {
    Concepts.CASH_ON_HAND: "cash_on_hand",
    Concepts.STATE_CODE: "state_code",
    Concepts.LIVING_RENTING: "living_renting",
    Concepts.LIVING_OWNER: "living_owner",
}


def _plain(value: Any) -> Any:
    """Coerce a metadata value into YAML-round-trippable plain data."""
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def scenario_parameters(case: Case) -> dict[str, Any]:
    """The oracle-neutral scenario inputs that vary across a case set."""
    params: dict[str, Any] = {}
    for key, value in case.metadata.items():
        if key in _PROJECTION_METADATA_KEYS or key in _STRUCTURAL_METADATA_KEYS:
            continue
        params[str(key)] = _plain(value)
    return params


def _short_fact_key(
    concept_id: str,
    explicit: dict[str, str],
    taken: dict[str, str],
    *,
    context: str,
) -> str:
    """Short grid key for a fact concept, guarding against collisions.

    Uses the explicit neutral name when mapped; otherwise the concept fragment.
    Raises if two distinct concepts would land on the same short key (the
    fragment-fallback landmine: e.g. ``#...eligible`` on two programs), so a
    collision is a loud extraction failure, never a silent overwrite.
    """
    short = explicit.get(concept_id) or str(concept_id).split("#", 1)[-1]
    prior = taken.get(short)
    if prior is not None and prior != concept_id:
        raise ValueError(
            f"{context}: grid key {short!r} collides between {prior!r} and "
            f"{concept_id!r}; add an explicit neutral name to disambiguate"
        )
    taken[short] = concept_id
    return short


def _entity_skeleton(entity: Entity) -> dict[str, Any]:
    facts = dict(entity.facts)
    skeleton: dict[str, Any] = {"id": entity.entity_id, "kind": entity.kind}
    if _AGE_CONCEPT in facts:
        skeleton["age"] = facts.pop(_AGE_CONCEPT)
    if _RELATION_CONCEPT in facts:
        skeleton["relation"] = facts.pop(_RELATION_CONCEPT)
    taken: dict[str, str] = {}
    for concept_id, value in facts.items():
        short = _short_fact_key(
            str(concept_id),
            _ENTITY_FACT_KEYS,
            taken,
            context=f"entity {entity.entity_id!r}",
        )
        skeleton[short] = _plain(value)
    return skeleton


def _case_facts(case: Case) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    taken: dict[str, str] = {}
    for concept_id, value in case.facts.items():
        short = _short_fact_key(
            str(concept_id),
            _CASE_FACT_KEYS,
            taken,
            context=f"case {case.case_id!r}",
        )
        facts[short] = _plain(value)
    return facts


def case_skeleton(case: Case) -> dict[str, Any]:
    """The full oracle-neutral skeleton of one live case, as plain data."""
    skeleton: dict[str, Any] = {
        "id": str(case.case_id),
        "period": str(case.period),
    }
    scenario = case.metadata.get("scenario")
    if scenario is not None:
        skeleton["scenario"] = str(scenario)
    if case.outputs:
        skeleton["outputs"] = [str(output) for output in case.outputs]
    entity = case.metadata.get("axiom_entity")
    entity_id = case.metadata.get("axiom_entity_id")
    if entity is not None:
        skeleton["entity"] = str(entity)
    if entity_id is not None:
        skeleton["entity_id"] = str(entity_id)
    params = scenario_parameters(case)
    if params:
        skeleton["parameters"] = params
    if case.entities:
        skeleton["entities"] = [_entity_skeleton(entity) for entity in case.entities]
    facts = _case_facts(case)
    if facts:
        skeleton["facts"] = facts
    return skeleton


def case_set_skeleton(name: str, cases: list[Case]) -> dict[str, Any]:
    """Reduce a whole suite (list of cases) to a grid case-set mapping.

    Set-level ``locale`` / ``entity`` / ``entity_id`` / ``outputs`` are lifted
    out when constant across the set, and then omitted from the individual case
    skeletons so the file stays DRY; a case that diverges keeps its own value.
    """
    case_skeletons = [case_skeleton(case) for case in cases]

    def _constant(key: str) -> Any | None:
        # Lift to set level only when the key is present with the SAME value in
        # EVERY case. Requiring presence-in-all (not just agreement among the
        # cases that set it) means a mixed set — some cases with the key, some
        # without — keeps per-case values rather than lifting a default that
        # grid_case_from_spec would wrongly re-inline onto the key-less cases.
        if not case_skeletons:
            return None
        values = [c.get(key) for c in case_skeletons]
        if any(value is None for value in values):
            return None
        if len(set(values)) == 1:
            return values[0]
        return None

    # A case set belongs to one jurisdiction, so its locale is set-level only
    # (case_skeleton never emits a per-case locale). Mixed locales would be
    # silently lost, so reject them loudly rather than drop them.
    locales = {case.locale for case in cases if case.locale is not None}
    if len(locales) > 1:
        raise ValueError(
            f"case set {name!r} mixes locales {sorted(locales)}; a grid case "
            "set must be single-jurisdiction"
        )
    locale = next(iter(locales)) if len(locales) == 1 else None
    set_entity = _constant("entity")
    set_entity_id = _constant("entity_id")
    outputs_values = {tuple(c.get("outputs") or ()) for c in case_skeletons}
    set_outputs = (
        list(next(iter(outputs_values)))
        if len(outputs_values) == 1 and next(iter(outputs_values))
        else None
    )

    body: dict[str, Any] = {}
    if locale is not None:
        body["locale"] = locale
    if set_entity is not None:
        body["entity"] = set_entity
    if set_entity_id is not None:
        body["entity_id"] = set_entity_id
    if set_outputs is not None:
        body["outputs"] = set_outputs

    lifted_cases: list[dict[str, Any]] = []
    for skeleton in case_skeletons:
        case_body = dict(skeleton)
        if set_entity is not None and case_body.get("entity") == set_entity:
            case_body.pop("entity", None)
        if set_entity_id is not None and case_body.get("entity_id") == set_entity_id:
            case_body.pop("entity_id", None)
        if set_outputs is not None and case_body.get("outputs") == set_outputs:
            case_body.pop("outputs", None)
        lifted_cases.append(case_body)
    body["cases"] = lifted_cases
    return body


def grid_case_from_spec(case_spec: Any, case_set: Any) -> dict[str, Any]:
    """Reconstruct a case skeleton dict from loaded grid dataclasses.

    Inverse of :func:`case_skeleton` at the data level: re-inlines the
    set-level defaults a grid file lifts out, so the result can be compared
    field-by-field against ``case_skeleton(live_case)``.
    """
    skeleton: dict[str, Any] = {
        "id": case_spec.id,
        "period": case_spec.period,
    }
    if case_spec.scenario is not None:
        skeleton["scenario"] = case_spec.scenario
    outputs = case_spec.outputs or case_set.outputs
    if outputs:
        skeleton["outputs"] = list(outputs)
    entity = case_spec.entity or case_set.entity
    entity_id = case_spec.entity_id or case_set.entity_id
    if entity is not None:
        skeleton["entity"] = entity
    if entity_id is not None:
        skeleton["entity_id"] = entity_id
    if case_spec.parameters:
        skeleton["parameters"] = _plain(dict(case_spec.parameters))
    if case_spec.entities:
        entities: list[dict[str, Any]] = []
        for entity_spec in case_spec.entities:
            entity_body: dict[str, Any] = {
                "id": entity_spec.id,
                "kind": entity_spec.kind,
            }
            if entity_spec.age is not None:
                entity_body["age"] = entity_spec.age
            if entity_spec.relation is not None:
                entity_body["relation"] = entity_spec.relation
            for key, value in entity_spec.extra.items():
                entity_body[key] = _plain(value)
            entities.append(entity_body)
        skeleton["entities"] = entities
    if case_spec.facts:
        skeleton["facts"] = _plain(dict(case_spec.facts))
    return skeleton
