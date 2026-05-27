"""Loader for the ECPS-to-input mapping YAML.

Reads ``axiom_oracles/data/ecps_input_mapping.yaml`` and turns the declarative
entries into an ``EcpsMapping`` — the callable-keyed dict that the generic
projector consumes. The mapping itself is pure data; this module is the
small adapter that translates "match this slot, read that fact, apply this
transform" into the lookups the projector needs.

Adding a new program comparison stays declarative: extend the YAML, no
Python changes here.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import yaml

from ...core.case import Concepts
from .generic_inputs import EcpsMapping, InputSlot, enumerate_inputs


_DEFAULT_MAPPING_PATH = (
    Path(__file__).parent.parent.parent / "data" / "ecps_input_mapping.yaml"
)


def load_ecps_mapping_for_program(
    compiled_program: Mapping[str, Any],
    *,
    mapping_path: Path | None = None,
) -> EcpsMapping:
    """Return an EcpsMapping keyed by absolute input slot name.

    The input slots come from the compiled program; the rules come from the
    YAML mapping table. We resolve which YAML entry matches which slot at
    load time, so the per-case projection is just a dict lookup.
    """
    path = mapping_path or _DEFAULT_MAPPING_PATH
    config = yaml.safe_load(Path(path).read_text())
    rules = list(config.get("mappings", []))
    slots = enumerate_inputs(compiled_program)

    mapping: dict[str, Callable[..., Any]] = {}
    for slot in slots:
        rule = _first_matching_rule(slot.name, rules)
        if rule is None:
            continue
        mapping[slot.name] = _build_mapper(slot, rule)
    return mapping


# ---------------------------------------------------------------------------
# Match resolution
# ---------------------------------------------------------------------------


def _first_matching_rule(slot_name: str, rules: list[dict]) -> dict | None:
    for rule in rules:
        match = rule.get("match", {})
        if _match(slot_name, match):
            return rule
    return None


def _match(slot_name: str, match: Mapping[str, Any]) -> bool:
    kind = match.get("kind")
    value = match.get("value", "")
    if kind == "exact":
        return slot_name == value
    if kind == "suffix":
        return slot_name.endswith(value)
    if kind == "substring":
        return value in slot_name
    return False


# ---------------------------------------------------------------------------
# Mapper construction
# ---------------------------------------------------------------------------


def _build_mapper(slot: InputSlot, rule: dict) -> Callable[..., Any]:
    """Return a callable(case_facts, person_facts) → value for one slot.

    The callable matches the ``project_case_inputs`` ECPS-mapping protocol:
    person-scoped slots get (case_facts, person_facts); household-scoped
    slots get (case_facts, None).
    """
    source = rule.get("source", {})
    kind = source.get("kind")
    scope = rule.get("scope", "household")

    if kind == "constant":
        constant = source.get("value")
        return lambda case_facts, person_facts: constant

    if kind == "fact":
        fact_name = source["name"]
        concept = _resolve_concept(fact_name)
        default = source.get("default")
        cast = source.get("cast")

        def fact_mapper(case_facts, person_facts):
            facts_table = person_facts if scope == "person" else case_facts
            value = (facts_table or {}).get(concept, default)
            return _cast(value, cast)

        return fact_mapper

    if kind == "derived":
        return _build_derived_mapper(scope, source)

    return lambda case_facts, person_facts: None


def _build_derived_mapper(scope: str, source: dict) -> Callable[..., Any]:
    transform = source.get("transform")
    from_facts = [_resolve_concept(name) for name in source.get("from_facts", [])]
    aggregate = source.get("aggregate")
    constant = source.get("constant")

    def derived(case_facts, person_facts):
        if transform == "hh_size":
            # The number of people is on the case (not a fact); the generic
            # attach passes person_facts as a list of dicts upstream, but
            # at the slot level we only see one. Fall back to length of a
            # "people" key the attach function injects (see below).
            people = (case_facts or {}).get("__people__")
            return len(people) if people is not None else 1

        if transform == "monthly":
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            return round(float(value) / 12, 2)

        if transform == "weekly":
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            return round(float(value) / 52, 2)

        if transform == "elderly_or_disabled":
            facts = person_facts or {}
            age = float(facts.get(Concepts.PERSON_AGE, 0) or 0)
            disabled = bool(facts.get(Concepts.DISABLED, False) or False)
            return age >= 60 or disabled

        if transform == "positive":
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            return float(value) > 0

        if transform == "positive_to_constant":
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            return constant if float(value) > 0 else 0

        return None

    return derived


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_concept(name: str) -> str:
    """Resolve a Concepts class attribute name (e.g. PERSON_AGE) to its value.

    Bare strings (like ``yearly_earned_income``) pass through unchanged so
    YAML authors can use whichever form is more readable.
    """
    if hasattr(Concepts, name):
        return getattr(Concepts, name)
    return name


def _cast(value: Any, cast: str | None) -> Any:
    if cast is None or value is None:
        return value
    if cast == "int":
        return int(value)
    if cast == "bool":
        return bool(value)
    if cast == "float":
        return float(value)
    return value


def _gather_facts(
    fact_keys: list[str],
    case_facts: Mapping[str, Any] | None,
    person_facts: Mapping[str, Any] | None,
    aggregate: str | None,
) -> float:
    """Read fact values either from a single person or summed over people."""
    if aggregate == "sum_over_people":
        people = (case_facts or {}).get("__people__") or []
        total = 0.0
        for person in people:
            for key in fact_keys:
                total += float(person.get(key, 0) or 0)
        return total
    facts = person_facts if person_facts is not None else (case_facts or {})
    return sum(float((facts or {}).get(key, 0) or 0) for key in fact_keys)
