"""Loader for the populace-to-input mapping YAML.

Reads ``axiom_oracles/data/populace_input_mapping.yaml`` and turns the
declarative entries into an ``EcpsMapping`` — the callable-keyed dict that the
generic projector consumes. The mapping itself is pure data; this module is the
small adapter that translates "match this slot, read that fact, apply this
transform" into the lookups the projector needs.

Adding a new program comparison stays declarative: extend the YAML, no
Python changes here.

Renamed from ``ecps_mapping_loader`` — the projected population is the certified
populace-us artifact, not Enhanced CPS (TheAxiomFoundation/axiom-oracles#74).
The old module path and the old ``load_ecps_mapping_for_program`` name remain as
deprecation aliases (see the bottom of this module).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import yaml

from ...core.case import Concepts
from .generic_inputs import EcpsMapping, InputSlot, enumerate_inputs


_DEFAULT_MAPPING_PATH = (
    Path(__file__).parent.parent.parent / "data" / "populace_input_mapping.yaml"
)


def load_populace_mapping_for_program(
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
    geoids = tuple(str(value) for value in source.get("geoids", ()))

    def derived(case_facts, person_facts):
        if transform == "hh_size":
            # The number of people is on the case (not a fact); the generic
            # attach passes person_facts as a list of dicts upstream, but
            # at the slot level we only see one. Fall back to length of a
            # "people" key the attach function injects (see below).
            people = (case_facts or {}).get("__people__")
            return len(people) if people is not None else 1

        if transform == "sum":
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            return round(float(value), 2)

        if transform == "flag_and_not_flags":
            # First fact truthy AND every remaining fact falsy — e.g.
            # "disabled and not blind" for SSI's disabled-branch exclusion.
            facts = person_facts if scope == "person" else (case_facts or {})
            facts = facts or {}
            if not from_facts:
                return False
            first = bool(facts.get(from_facts[0], False) or False)
            rest = [bool(facts.get(key, False) or False) for key in from_facts[1:]]
            return first and not any(rest)

        if transform == "age_at_least_and_not_flags":
            # First fact (an age) >= source.threshold AND every remaining
            # fact falsy — e.g. SSI's age-65 earned-income branch, which
            # applies only to people not in the blind/disabled branches.
            facts = person_facts if scope == "person" else (case_facts or {})
            facts = facts or {}
            if not from_facts:
                return False
            age = float(facts.get(from_facts[0], 0) or 0)
            rest = [bool(facts.get(key, False) or False) for key in from_facts[1:]]
            return age >= float(source.get("threshold", 0)) and not any(rest)

        if transform == "abd_adult_with_abd_adult_partner":
            # SSI eligible-spouse approximation: this person is an
            # aged (65+)/blind/disabled adult AND exactly one other
            # aged/blind/disabled adult lives in the household. ECPS lacks
            # marital linkage at this layer, so two ABD adults in one
            # household are treated as an eligible couple.
            facts = person_facts or {}
            def _abd(f):
                return (
                    float(f.get(Concepts.PERSON_AGE, 0) or 0) >= 65
                    or bool(f.get(Concepts.BLIND, False) or False)
                    or bool(f.get(Concepts.DISABLED, False) or False)
                )
            def _adult(f):
                return float(f.get(Concepts.PERSON_AGE, 0) or 0) >= 18
            if not (_abd(facts) and _adult(facts)):
                return False
            others = [
                f for f in facts.get("__others__", []) if _abd(f) and _adult(f)
            ]
            return len(others) == 1

        if transform == "ssi_couple_countable_income":
            # Combined countable income for an SSI eligible couple (this
            # person + the single other ABD adult): unearned less the $240
            # annual general exclusion, plus earned less $780 and half the
            # remainder — mirroring the individual-side wrapper math.
            facts = person_facts or {}
            def _abd2(f):
                return (
                    float(f.get(Concepts.PERSON_AGE, 0) or 0) >= 65
                    or bool(f.get(Concepts.BLIND, False) or False)
                    or bool(f.get(Concepts.DISABLED, False) or False)
                ) and float(f.get(Concepts.PERSON_AGE, 0) or 0) >= 18
            members = [facts] + [
                f for f in facts.get("__others__", []) if _abd2(f)
            ][:1]
            unearned_keys = [
                Concepts.SOCIAL_SECURITY_BENEFITS,
                Concepts.PENSION_INCOME,
                Concepts.INTEREST_INCOME,
                Concepts.DIVIDEND_INCOME,
                Concepts.RENTAL_INCOME,
                Concepts.UNEMPLOYMENT_INSURANCE_INCOME,
            ]
            earned_keys = [
                Concepts.YEARLY_EARNED_INCOME,
                Concepts.SELF_EMPLOYMENT_INCOME,
            ]
            unearned = sum(
                float(m.get(k, 0) or 0) for m in members for k in unearned_keys
            )
            earned = sum(
                float(m.get(k, 0) or 0) for m in members for k in earned_keys
            )
            countable_unearned = max(0.0, unearned - 240.0)
            earned_after_initial = max(0.0, earned - 780.0)
            countable_earned = earned_after_initial / 2
            return round(countable_unearned + countable_earned, 2)

        if transform == "count_age_below":
            people = (case_facts or {}).get("__people__") or []
            threshold = float(source.get("threshold", 0))
            return sum(
                1 for p in people
                if float(p.get(Concepts.PERSON_AGE, 0) or 0) < threshold
            )

        if transform == "count_age_at_least":
            people = (case_facts or {}).get("__people__") or []
            threshold = float(source.get("threshold", 0))
            cap = source.get("cap")
            count = sum(
                1 for p in people
                if float(p.get(Concepts.PERSON_AGE, 0) or 0) >= threshold
            )
            return min(count, int(cap)) if cap is not None else count

        if transform == "monthly_rate_plus_flat":
            # Earned income disregard shaped as rate x monthly income + flat,
            # capped at the income itself (a disregard can't exceed income).
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            monthly = float(value) / 12
            rate = float(source.get("rate", 0))
            flat = float(source.get("flat", 0))
            return round(min(monthly, monthly * rate + flat), 2)

        if transform == "monthly_flat_then_rate":
            # Countable monthly income where a flat amount is subtracted
            # first and a rate of the remainder is then disregarded
            # (CalWORKs recipient: (gross - $600) x 50%). With
            # flat_per_earner, the flat applies once per member with
            # positive income from from_facts (MFIP's $65 per wage earner).
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            monthly = float(value) / 12
            flat = float(source.get("flat", 0))
            if source.get("flat_per_earner"):
                people = (case_facts or {}).get("__people__") or []
                earners = sum(
                    1 for p in people
                    if any(float(p.get(k, 0) or 0) > 0 for k in from_facts)
                )
                flat *= max(1, earners)
            rate = float(source.get("rate", 0))
            return round(max(0.0, (monthly - flat)) * (1 - rate), 2)

        if transform == "monthly_countable_after_exclusion":
            # Countable monthly income after a rate + flat exclusion.
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            monthly = float(value) / 12
            rate = float(source.get("rate", 0))
            flat = float(source.get("flat", 0))
            return round(max(0.0, monthly - (monthly * rate + flat)), 2)

        if transform == "adult_table_plus_per_child":
            # Standard tables keyed by capped adult count with a per-child
            # add-on beyond the first child (Colorado Works need standards).
            people = (case_facts or {}).get("__people__") or []
            adults = sum(
                1 for p in people
                if float(p.get(Concepts.PERSON_AGE, 0) or 0) >= 18
            )
            children = sum(
                1 for p in people
                if float(p.get(Concepts.PERSON_AGE, 0) or 0) < 18
            )
            table = {int(k): float(v) for k, v in (source.get("table") or {}).items()}
            if not table:
                return 0.0
            key = min(adults, max(table))
            per_child = float(source.get("per_child", 0))
            return round(
                table.get(key, 0.0)
                + per_child * max(0, children - 1),
                2,
            )

        if transform == "table_by_hh_size":
            # Standard schedules keyed by household size, with an optional
            # per-additional-person increment beyond max_size and a scalar
            # multiplier (e.g. MFIP family wage level = 110% of the
            # transitional standard).
            people = (case_facts or {}).get("__people__") or []
            size = max(1, len(people))
            table = {int(k): float(v) for k, v in (source.get("table") or {}).items()}
            if not table:
                return 0.0
            cap = int(source.get("max_size", max(table)))
            key = min(size, cap)
            extra = float(source.get("per_additional", 0)) * max(0, size - cap)
            return round(
                (table.get(key, 0.0) + extra) * float(source.get("multiplier", 1)),
                2,
            )

        if transform == "sum_is_zero":
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            return float(value) <= 0

        if transform == "sum_positive_and_zero":
            # True when from_facts sum positive AND zero_facts sum to zero —
            # e.g. MFIP's "unearned income only" budgeting branch.
            value = _gather_facts(from_facts, case_facts, person_facts, aggregate)
            zero_keys = [_resolve_concept(n) for n in source.get("zero_facts", [])]
            zero_sum = _gather_facts(zero_keys, case_facts, person_facts, aggregate)
            return float(value) > 0 and float(zero_sum) <= 0

        if transform == "age_below":
            # Person-scope: age fact strictly below source.threshold.
            facts = person_facts or {}
            age_key = from_facts[0] if from_facts else Concepts.PERSON_AGE
            return float(facts.get(age_key, 0) or 0) < float(source.get("threshold", 0))

        if transform == "age_at_least_or_flags":
            # Person-scope: age >= threshold OR any of the remaining flags —
            # e.g. Medicaid's aged (65+) / blind / disabled status.
            facts = person_facts or {}
            if not from_facts:
                return False
            age_key, *flag_keys = from_facts
            if float(facts.get(age_key, 0) or 0) >= float(source.get("threshold", 0)):
                return True
            return any(bool(facts.get(key, False) or False) for key in flag_keys)

        if transform == "fpl_ratio":
            # Household annual income (sum of from_facts over people) as a
            # fraction of the federal poverty guideline for the household
            # size: base + per_person * (size - 1). Guideline values come
            # from the mapping entry so the projector mirrors the oracle's
            # published FPG table.
            people = (case_facts or {}).get("__people__") or []
            total = 0.0
            for person in people:
                for key in from_facts:
                    total += float(person.get(key, 0) or 0)
            base = float(source.get("fpg_base", 0) or 0)
            per = float(source.get("fpg_per_person", 0) or 0)
            size = max(1, len(people))
            guideline = base + per * (size - 1)
            return round(total / guideline, 6) if guideline else 0.0

        if transform == "any_age_below_or_flags":
            # True when any person is younger than source.threshold OR has
            # any of the remaining flags — e.g. TANF's "unit contains a
            # minor child or pregnant member" demographic gate.
            people = (case_facts or {}).get("__people__") or []
            threshold = float(source.get("threshold", 0))
            if not from_facts:
                return False
            age_key, *flag_keys = from_facts
            for person in people:
                if float(person.get(age_key, 0) or 0) < threshold:
                    return True
                if any(bool(person.get(key, False) or False) for key in flag_keys):
                    return True
            return False

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

        if transform == "all_people_any_positive":
            people = (case_facts or {}).get("__people__") or []
            if not people:
                return False
            return all(
                any(float(person.get(key, 0) or 0) > 0 for key in from_facts)
                for person in people
            )

        if transform == "scope_geoid_in":
            metadata = (case_facts or {}).get("__metadata__") or {}
            case_scope = metadata.get("scope") or {}
            geoid = str(case_scope.get("geoid") or "")
            return any(
                geoid == candidate or geoid.startswith(candidate)
                for candidate in geoids
            )

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


# Deprecated alias — the loader was renamed from ``ecps_mapping_loader`` to
# ``populace_mapping_loader`` (axiom-oracles#74). Same function, old name.
load_ecps_mapping_for_program = load_populace_mapping_for_program
