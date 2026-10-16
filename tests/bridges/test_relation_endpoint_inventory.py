"""Thirty structural cases for the engine's directional relation typing rules.

An incoming declaration never types its source. Cycles remain untyped; aliases
are resolved at the binder boundary, without changing source-chain semantics.
"""

from copy import deepcopy
from itertools import permutations
import warnings

import pytest

from axiom_oracles.bridges.relation_binding import (
    RelationBindingAmbiguityWarning,
    _effective_slot_entities,
    bind_request_relations,
    relation_owner_kind,
    relation_tuple,
)


def _derivation(source, slot, kinds=None):
    result = {
        "source_relation": source,
        "current_slot": slot,
        "related_slot": 1 - slot,
        "predicate": {"kind": "literal", "value": {"kind": "bool", "value": True}},
    }
    if kinds is not None:
        result["slot_entities"] = kinds
    return result


def _request(name="payments", slot=0):
    return {
        "dataset": {
            "inputs": [
                {"entity_id": "house", "entity": "Household"},
                {"entity_id": "payment", "entity": "Payment"},
                {"entity_id": "payment", "entity": "Person"},
            ],
            "relations": [
                {
                    "name": name,
                    "tuple": ["house", "payment"]
                    if slot == 0
                    else ["payment", "house"],
                }
            ],
        }
    }


def _assert_binding(program, slot, name="payments"):
    request = _request(name, 1 - slot)
    before = deepcopy(request), deepcopy(program)
    bound = bind_request_relations(request, {"program": program})
    expected = ["house", "payment"] if slot == 0 else ["payment", "house"]
    assert bound["dataset"]["relations"][0]["tuple"] == expected
    assert (
        relation_tuple(
            {"program": program},
            name,
            owner_id="house",
            owner_kind="Household",
            related_id="payment",
            related_kind="Payment",
        )
        == expected
    )
    assert bind_request_relations(bound, {"program": program}) == bound
    assert (request, program) == before


@pytest.mark.parametrize("slot", [0, 1])
@pytest.mark.parametrize(
    "name", ["urn:test#relation.payments", "payment-source-id", "payments"]
)
def test_boundary_aliases_never_borrow_another_relation_declaration(slot, name):
    kinds = ["Household", "Payment"] if slot == 0 else ["Payment", "Household"]
    program = {
        "relations": [
            {
                "name": "urn:test#relation.payments",
                "id": "payment-source-id",
                "arity": 2,
                "slot_entities": kinds,
            }
        ],
        "derived": [],
    }
    request = _request(name, 1 - slot)
    bound = bind_request_relations(request, {"program": program})
    recognized = name == "urn:test#relation.payments"
    assert (
        bound["dataset"]["relations"][0]["tuple"]
        == (["house", "payment"] if slot == 0 else ["payment", "house"])
        if recognized
        else bound == request
    )
    pair = relation_tuple(
        {"program": program},
        name,
        owner_id="house",
        owner_kind="Household",
        related_id="payment",
        related_kind="Payment",
    )
    assert pair[slot if recognized else 1] == "house"


@pytest.mark.parametrize("slot", [0, 1])
@pytest.mark.parametrize("depth", [1, 3])
@pytest.mark.parametrize("seed", ["declaration", "derivation"])
def test_only_outgoing_source_chains_inherit_typing(slot, depth, seed):
    kinds = ["Household", "Payment"] if slot == 0 else ["Payment", "Household"]
    root = {"name": "base", "arity": 2}
    if seed == "declaration":
        root["slot_entities"] = kinds
    else:
        root["derivation"] = _derivation("ghost", slot, kinds)
    relations = [root]
    source = "base"
    for index in range(depth):
        name = "payments" if index == depth - 1 else f"source{index}"
        relations.append(
            {"name": name, "arity": 2, "derivation": _derivation(source, slot)}
        )
        source = name
    _assert_binding({"relations": relations, "derived": []}, slot)


@pytest.mark.parametrize("slot", [0, 1])
@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_incoming_typed_relation_does_not_type_a_source_cycle(slot, order):
    relations = [
        {"name": "payments", "arity": 2, "derivation": _derivation("middle", slot)},
        {"name": "middle", "arity": 2, "derivation": _derivation("payments", slot)},
        {
            "name": "incoming",
            "arity": 2,
            "slot_entities": ["Household", "Payment"],
            "derivation": _derivation("middle", slot),
        },
    ]
    program = {
        "relations": [relations[index] for index in order],
        "derived": [
            {
                "name": "n",
                "entity": "Household",
                "expr": {
                    "kind": "count_related",
                    "relation": "payments",
                    "current_slot": slot,
                    "related_slot": 1 - slot,
                },
            }
        ],
    }
    assert _effective_slot_entities(program, "payments") is None
    request = _request(slot=slot)
    with pytest.warns(RelationBindingAmbiguityWarning):
        assert bind_request_relations(request, {"program": program}) == request


@pytest.mark.parametrize("slot", [0, 1])
def test_same_kind_source_wrapper_retains_both_endpoints(slot):
    program = {
        "relations": [
            {"name": "payments", "arity": 2, "slot_entities": ["Payment", "Payment"]},
            {
                "name": "filtered",
                "arity": 2,
                "derivation": _derivation("payments", slot),
            },
        ],
        "derived": [],
    }
    pair = relation_tuple(
        {"program": program},
        "payments",
        owner_id="parent",
        owner_kind="Payment",
        related_id="child",
        related_kind="Payment",
    )
    assert pair[slot] == "parent"
    assert sorted(pair) == ["child", "parent"]


@pytest.mark.parametrize("slot", [0, 1])
def test_cached_owner_and_roles_use_declaration_without_request_hints(slot):
    kinds = ["Household", "Payment"] if slot == 0 else ["Payment", "Household"]
    artifact = {
        "program": {
            "relations": [{"name": "payments", "arity": 2, "slot_entities": kinds}],
            "derived": [],
        }
    }
    before = deepcopy(artifact)
    with warnings.catch_warnings(record=True) as caught:
        assert (
            relation_owner_kind(
                artifact,
                "payments",
                default_owner_kind="Organization",
                related_kind="Payment",
            )
            == "Household"
        )
        assert (
            relation_tuple(
                artifact,
                "payments",
                owner_id="house",
                owner_kind="Household",
                related_id="payment",
                related_kind="Payment",
            )[slot]
            == "house"
        )
    assert not caught
    assert artifact == before
