"""Relation-local binding, with an independent native-engine oracle.

The same generated (P, Q, A) cases drive both properties. A may contain invalid
or untyped programs: those still exercise Python noninterference, but are
explicitly counted as outside the native engine's accepted-program domain.
No expected orientation is obtained from the Python binder's private helpers.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import warnings

from hypothesis import event, example, given, settings, strategies as st
import pytest

from axiom_oracles.bridges.relation_binding import (
    RelationBindingError,
    bind_request_relations,
)


_KINDS = ("Person", "Household", "TaxUnit", "Payment", "SnapUnit", "FreshKind")
_ENTITY_KINDS = st.one_of(
    st.sampled_from(_KINDS),
    st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10).map(lambda suffix: f"New{suffix}"),
)
_INTERVAL = {"start": "2026-01-01", "end": "2026-12-31"}
_STYLES = ("own", "derivation", "chain1", "chain2", "chain3", "untyped")
_NOISE_SHAPES = (
    "data", "chain", "cycle", "count", "sum", "membership", "nested",
    "broadcast", "versions", "input_or_else", "no_match", "fragment_collision",
)


def _integer(value=1):
    return {"kind": "literal", "value": {"kind": "integer", "value": value}}


def _comparison(left=None):
    return {
        "kind": "comparison", "left": left or _integer(), "op": "gt",
        "right": _integer(0),
    }


def _rule(name, entity, expr):
    return {
        "name": name, "entity": entity, "dtype": "integer",
        "semantics": "scalar", "expr": expr,
    }


def _count(name, slot, where=None):
    result = {
        "kind": "count_related", "relation": name,
        "current_slot": slot, "related_slot": 1 - slot,
    }
    if where is not None:
        result["where"] = where
    return result


def _derived_relation(name, source, slot, *, kinds=None, entity=None, predicate=None):
    derivation = {
        "source_relation": source, "current_slot": slot, "related_slot": 1 - slot,
        "predicate": predicate or _comparison(),
    }
    if kinds is not None:
        derivation["slot_entities"] = list(kinds)
    if entity is not None:
        derivation["entity"] = entity
    return {"name": name, "arity": 2, "derivation": derivation}


def _wrap(expression, wrappers):
    """Generate arbitrary-depth syntax, including nonexecuted match patterns."""
    for wrapper in wrappers:
        if wrapper == "add":
            expression = {"kind": "add", "items": [expression, _integer(0)]}
        elif wrapper == "mul":
            expression = {"kind": "mul", "left": expression, "right": _integer()}
        elif wrapper == "if":
            expression = {
                "kind": "if", "condition": _comparison(),
                "then_expr": expression, "else_expr": _integer(0),
            }
        else:
            expression = {
                "kind": "if", "condition": _comparison(), "then_expr": expression,
                "else_expr": {
                    "kind": "no_match", "subject": _integer(),
                    "patterns": [deepcopy(expression), _integer(0)],
                },
            }
    return expression


@dataclass
class BindingCase:
    program: dict
    request: dict
    additions: dict
    canonical_tuple: list[str]
    style: str
    noise_shapes: tuple[str, ...]

    def extended_program(self):
        extended = deepcopy(self.program)
        for key, additions in self.additions.items():
            extended.setdefault(key, []).extend(deepcopy(additions))
        return extended


def _base_case(
    style="own", owner="Household", member="Payment", slot=0,
    reverse=False, evidence="complete", executed=True, alias=False, public_reference=False,
):
    kinds = [owner, member] if slot == 0 else [member, owner]
    relations = []
    if style == "own":
        relations.append({"name": "R", "arity": 2, "slot_entities": kinds})
    elif style == "untyped":
        relations.append({"name": "R", "arity": 2})
    else:
        hops = 1 if style == "derivation" else int(style[-1])
        relations.append({"name": "base_source", "arity": 2, "slot_entities": kinds})
        source = "base_source"
        for index in range(hops):
            name = "R" if index == hops - 1 else f"base_hop_{index}"
            relation = _derived_relation(
                name, source, slot, kinds=kinds if style == "derivation" else None,
            )
            relations.append(relation)
            source = name

    query_kind = owner
    if alias:
        # This mapping is part of P. A can introduce fresh filters, but never
        # change this label or the physical kinds used in Q.
        query_kind = "BaseFilteredOwner"
        relations.extend([
            {"name": "base_filter_source", "arity": 2, "slot_entities": kinds},
            _derived_relation(
                "base_owner_filter", "base_filter_source", slot, entity=query_kind,
            ),
        ])

    derived = [_rule("n", query_kind, _count("R", slot) if executed else _integer())]
    inputs = []

    def add_label(name, entity_id, kind):
        derived.append(_rule(f"read_{name}", kind, {"kind": "input", "name": name}))
        inputs.append({
            "name": name, "entity": kind, "entity_id": entity_id,
            "interval": deepcopy(_INTERVAL), "value": {"kind": "integer", "value": 1},
        })

    add_label("owner_marker", "owner", owner)
    if evidence != "unknown_member":
        add_label("member_marker", "member", member)
    if evidence in {"conflicting_owner", "all_conflicting"}:
        add_label("owner_conflict", "owner", "ConflictingKind")
    if evidence in {"conflicting_member", "all_conflicting"}:
        add_label("member_conflict", "member", "ConflictingKind")

    canonical = ["owner", "member"] if slot == 0 else ["member", "owner"]
    request = {
        "mode": "explain", "dataset": {"inputs": inputs, "relations": [{
            "name": "R", "tuple": canonical[::-1] if reverse else canonical,
            "interval": deepcopy(_INTERVAL),
        }]},
        "queries": [{
            "entity_id": "owner", "period": {"period_kind": "tax_year", **_INTERVAL},
            "outputs": ["n"],
        }],
    }
    if public_reference:
        # The engine permits public relation references to bare schemas when
        # the program has public rule IDs. A different module's same fragment
        # is still an independent relation, even after it is added to P.
        derived.append({
            **_rule("public_marker", "Scalar", _integer()),
            "id": "us:statutes/26/21#public_marker",
        })
        request["dataset"]["relations"][0]["name"] = "us:statutes/26/21#relation.R"
    return BindingCase(
        {"relations": relations, "derived": derived}, request,
        {"relations": [], "derived": []}, canonical, style, (),
    )


def _scalar_query_case():
    case = _base_case(evidence="unknown_member")
    case.program["derived"].append(_rule("scalar_output", "Scalar", _integer()))
    case.request["queries"].append({
        "entity_id": "member", "period": {"period_kind": "tax_year", **_INTERVAL},
        "outputs": ["scalar_output"],
    })
    return case


def _derivation_priority_case():
    case = _base_case(style="derivation")
    # The engine's effective lookup prioritizes the derivation. Its separate
    # source-conflict check rejects this malformed schema at execution time.
    case.program["relations"][-1]["slot_entities"] = ["Payment", "Household"]
    return case


def _duplicate_fragment_case(reverse=False):
    case = _base_case(public_reference=True, reverse=reverse)
    case.additions["relations"].append({
        "name": "us:statutes/26/999#relation.R", "arity": 2,
        "slot_entities": ["TaxUnit", "Person"],
    })
    case.noise_shapes = ("fragment_collision",)
    return case


def _ignored_metadata_case(reverse=False):
    case = _base_case(reverse=reverse)
    # Serde ignores extension fields. An apparent contradictory aggregate in
    # one must have no effect on execution reachability or binder policy.
    case.program["derived"][0]["expr"]["metadata"] = _count("R", 1)
    return case


@st.composite
def binding_cases(draw):
    """Generate disjoint program extensions, without imposing valid typing.

    There is no incoming edge into R, its source chain, or its wrappers. Fresh
    filter names ensure A cannot change canonicalization of a label in Q.
    Arbitrary existing/fresh nominal kinds, relation graphs, and nested syntax
    remain allowed, including additions that the mandatory-typing engine rejects.
    """
    style = draw(st.sampled_from(_STYLES))
    owner = draw(_ENTITY_KINDS)
    member = draw(_ENTITY_KINDS)
    case = _base_case(
        style=style, owner=owner, member=member, slot=draw(st.integers(0, 1)),
        reverse=draw(st.booleans()),
        evidence=draw(st.sampled_from((
            "complete", "unknown_member", "conflicting_owner",
            "conflicting_member", "all_conflicting",
        ))),
        executed=draw(st.booleans()), alias=draw(st.booleans()),
        public_reference=draw(st.booleans()),
    )
    shapes = draw(st.lists(st.sampled_from(_NOISE_SHAPES), min_size=0, max_size=5))
    case.noise_shapes = tuple(shapes)
    relations = case.additions["relations"]
    derived = case.additions["derived"]
    for index, shape in enumerate(shapes):
        prefix = f"noise_{index}"
        left = draw(_ENTITY_KINDS)
        right = draw(_ENTITY_KINDS)
        slot = draw(st.integers(0, 1))
        kinds = [left, right] if slot == 0 else [right, left]
        typed = draw(st.booleans())
        base = {"name": f"{prefix}_data", "arity": 2}
        if typed:
            base["slot_entities"] = kinds
        relations.append(base)
        # Entity declarations in this IR are attached to derived rules. This
        # adds arbitrary fresh entities even in a data-only extension.
        derived.append(_rule(f"{prefix}_entity", f"NewEntity{index}", _integer()))
        wrappers = draw(st.lists(st.sampled_from(("add", "mul", "if", "no_match")), max_size=5))
        value_name = f"{prefix}_value"
        derived.append(_rule(value_name, right, _integer()))
        count = _count(base["name"], slot)

        if shape == "fragment_collision":
            relations.append({
                "name": f"us:statutes/26/{900 + index}#relation.R", "arity": 2,
                "slot_entities": kinds,
            })
        elif shape in {"chain", "cycle"}:
            chain_length = draw(st.integers(1, 4))
            names = [f"{prefix}_derived_{hop}" for hop in range(chain_length)]
            for hop, name in enumerate(names):
                source = names[(hop + 1) % chain_length] if shape == "cycle" else (
                    base["name"] if hop == 0 else names[hop - 1]
                )
                own_kinds = kinds if draw(st.booleans()) else None
                relations.append(_derived_relation(
                    name, source, slot, kinds=own_kinds,
                    entity=f"FreshFilter{index}" if draw(st.booleans()) else None,
                ))
        elif shape == "data":
            continue
        elif shape == "membership":
            membership = {
                "kind": "relation_member", "relation": base["name"],
                "current_slot": slot, "related_slot": 1 - slot,
            }
            predicate = _comparison(_wrap({
                "kind": "if", "condition": membership,
                "then_expr": _integer(), "else_expr": _integer(0),
            }, wrappers))
            filtered = f"{prefix}_filtered"
            relations.append(_derived_relation(
                filtered, base["name"], slot, predicate=predicate,
                entity=f"FreshFilter{index}" if draw(st.booleans()) else None,
            ))
            derived.append(_rule(f"{prefix}_count", left, _count(filtered, slot)))
        else:
            if shape == "sum":
                count.update(kind="sum_related", value={"kind": "derived", "name": value_name})
            elif shape == "nested":
                inner_slot = draw(st.integers(0, 1))
                nested_kinds = [right, left] if inner_slot == 0 else [left, right]
                nested = f"{prefix}_nested"
                relations.append({"name": nested, "arity": 2, "slot_entities": nested_kinds})
                count["where"] = _comparison(_count(nested, inner_slot, _comparison()))
            elif shape == "broadcast":
                name = f"{prefix}_broadcast"
                derived.append(_rule(name, draw(st.sampled_from((*_KINDS, "Scalar"))), _integer()))
                count["where"] = _comparison({"kind": "derived", "name": name})
            elif shape == "input_or_else":
                count["where"] = _comparison({
                    "kind": "input_or_else", "name": f"{prefix}_optional",
                    "default": {"kind": "integer", "value": 1},
                })
            elif shape == "no_match":
                wrappers = [*wrappers, "no_match"]
            rule = _rule(f"{prefix}_aggregate", left, _wrap(count, wrappers))
            if shape == "versions":
                rule["versions"] = [{
                    "effective_from": "2026-01-01", "semantics": "scalar",
                    "expr": deepcopy(rule["expr"]),
                }]
                # A different base body is inactive for executed_relations.
                rule["expr"] = _integer()
            derived.append(rule)
    return case


def _observe(request, program):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            output = bind_request_relations(request, {"program": program})
            result = ("bound", output)
        except RelationBindingError as error:
            result = ("error", type(error).__name__, str(error))
    return result, [(warning.category.__name__, str(warning.message)) for warning in caught]


@settings(max_examples=500, deadline=None, derandomize=True)
@given(case=binding_cases())
@example(case=_base_case(style="untyped", reverse=True))
@example(case=_base_case(style="chain3", alias=True, evidence="all_conflicting"))
@example(case=_scalar_query_case())
@example(case=_derivation_priority_case())
@example(case=_duplicate_fragment_case())
@example(case=_duplicate_fragment_case(reverse=True))
@example(case=_ignored_metadata_case())
@example(case=_ignored_metadata_case(reverse=True))
def test_arbitrary_unrelated_additions_preserve_binding_and_warnings(case):
    before = deepcopy(case)
    event(f"base={case.style}")
    for shape in case.noise_shapes:
        event(f"addition={shape}")
    baseline = _observe(case.request, case.program)
    extended = _observe(case.request, case.extended_program())
    assert extended == baseline
    assert case == before


@pytest.fixture(scope="module")
def mandatory_typing_engine():
    configured = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if not configured or not Path(configured).is_file():
        message = "AXIOM_STRICT_RELATION_ENGINE_BIN must point to the pinned mandatory-typing engine"
        if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    return Path(configured).resolve()


@pytest.fixture(scope="module")
def native_differential_observations():
    counts = Counter()
    yield counts
    print("Native differential program observations:", json.dumps(dict(counts), sort_keys=True))


def _native(binary, request, program):
    return subprocess.run(
        [str(binary), "run"], input=json.dumps({"program": program, **request}),
        capture_output=True, text=True, check=False, timeout=20,
    )


def _wire_bytes(request):
    # Comparing the entire serialized request catches tuple, record ordering,
    # and metadata changes, as well as accidental mutation of Q.
    return json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()


def _assert_differential(binary, case, program, *, record_event=lambda value: None):
    # Check supplied-order acceptance before any domain control, so (a)/(c)
    # apply to every engine acceptance, including unexpected acceptances.
    supplied = _native(binary, case.request, program)
    before = _wire_bytes(case.request)
    result, _ = _observe(case.request, program)
    assert _wire_bytes(case.request) == before
    if supplied.returncode == 0:
        # (a) accepting the supplied tuple forbids any byte change; (c) it
        # also forbids the binder from raising, even for unknown/conflicting IDs.
        assert result[0] == "bound", result
        assert _wire_bytes(result[1]) == before
        record_event("native differential: supplied accepted byte-identically")
        return "accepted_unchanged"

    canonical = deepcopy(case.request)
    canonical["dataset"]["relations"][0]["tuple"] = case.canonical_tuple
    control = _native(binary, canonical, program)
    if control.returncode != 0:
        # The arbitrary-extension property deliberately includes untyped and
        # cyclic programs. Reject parse/catalog errors so malformed generators
        # cannot silently make this differential vacuous.
        assert any(marker in control.stderr.lower() for marker in (
            "untyped_relation", "relation_current_slot_entity_mismatch",
            "relation_related_slot_entity_mismatch", "filtered_entity",
            "derived_relation", "cycle", "cyclic",
        )), control.stderr
        record_event("native domain: program rejected")
        return "rejected_program"

    assert "strict dataset relation entity validation failed" in supplied.stderr, supplied.stderr
    assert result[0] == "bound", result
    bound = result[1]
    assert _wire_bytes(bound) != before
    # (b) every reorder in an executable program must be accepted, and the
    # original must have been rejected specifically for strict wire binding.
    corrected = _native(binary, bound, program)
    assert corrected.returncode == 0, corrected.stderr
    record_event("native differential: supplied rejected, reorder accepted")
    return "accepted_reorder"


@settings(max_examples=140, deadline=None, derandomize=True)
@given(case=binding_cases())
@example(case=_base_case(style="own", reverse=False))
@example(case=_base_case(style="own", reverse=True))
@example(case=_base_case(style="derivation", reverse=True))
@example(case=_base_case(style="chain3", reverse=True, alias=True))
@example(case=_base_case(style="untyped", reverse=True))
@example(case=_base_case(style="untyped", reverse=True, executed=False))
@example(case=_base_case(style="own", reverse=True, evidence="all_conflicting"))
@example(case=_scalar_query_case())
@example(case=_derivation_priority_case())
@example(case=_duplicate_fragment_case())
@example(case=_duplicate_fragment_case(reverse=True))
@example(case=_ignored_metadata_case())
@example(case=_ignored_metadata_case(reverse=True))
def test_generated_programs_match_native_strict_binding(
    mandatory_typing_engine, native_differential_observations, case,
):
    for program in (case.program, case.extended_program()):
        result = _assert_differential(mandatory_typing_engine, case, program, record_event=event)
        native_differential_observations[result] += 1


@pytest.mark.parametrize("style", _STYLES)
@pytest.mark.parametrize("reverse", (False, True))
@pytest.mark.parametrize("slot", (0, 1))
def test_native_differential_has_acceptance_and_reordering_controls(
    mandatory_typing_engine, native_differential_observations, style, reverse, slot,
):
    """Keep generated rejection coverage from hiding an empty accepted domain."""
    case = _base_case(style=style, reverse=reverse, slot=slot)
    result = _assert_differential(mandatory_typing_engine, case, case.program)
    native_differential_observations[result] += 1
    expected = "rejected_program" if style == "untyped" else (
        "accepted_reorder" if reverse else "accepted_unchanged"
    )
    assert result == expected
