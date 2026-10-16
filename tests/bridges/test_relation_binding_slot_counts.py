"""Slot counts follow schema loading, executed typing, and per-slot wire checks."""

from copy import deepcopy

import pytest

from axiom_oracles.bridges.relation_binding import (
    RelationBindingError,
    bind_request_relations,
    relation_tuple,
)


def _case(kinds):
    artifact = {
        "program": {
            "relations": [
                {"name": "S", "arity": 2, "slot_entities": ["Household", "Person"]},
                {
                    "name": "D",
                    "arity": 2,
                    "slot_entities": ["Household", "Person"],
                    "derivation": {
                        "source_relation": "S",
                        "current_slot": 0,
                        "related_slot": 1,
                        "slot_entities": kinds,
                    },
                },
            ],
            "derived": [],
        }
    }
    request = {
        "dataset": {
            "inputs": [
                {"entity_id": "house", "entity": "Household"},
                {"entity_id": "person", "entity": "Person"},
            ],
            "relations": [{"name": "D", "tuple": ["house", "person"]}],
        }
    }
    return artifact, request


@pytest.mark.parametrize("kinds", [["Household"], ["Household", "Person", "Person"]])
@pytest.mark.parametrize("reversed_tuple", [False, True])
@pytest.mark.parametrize("explicit_roles", [False, True])
def test_unexecuted_derivation_compares_slot_by_slot(
    kinds, reversed_tuple, explicit_roles
):
    artifact, request = _case(kinds)
    record = request["dataset"]["relations"][0]
    if reversed_tuple:
        record["tuple"].reverse()
    if explicit_roles:
        record["roles"] = {
            "owner_id": "house",
            "owner_kind": "Household",
            "related_id": "person",
            "related_kind": "Person",
            "legacy_owner_slot": 1 if reversed_tuple else 0,
        }
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"] == ["house", "person"]
    assert request == before
    assert relation_tuple(
        artifact,
        "D",
        owner_id="house",
        owner_kind="Household",
        related_id="person",
        related_kind="Person",
    ) == ["house", "person"]


def test_unexecuted_short_derivation_leaves_undeclared_slot_unchecked():
    artifact, request = _case(["Household"])
    request["dataset"]["inputs"][1]["entity"] = "Payment"
    assert bind_request_relations(request, artifact) == request
    assert relation_tuple(
        artifact,
        "D",
        owner_id="house",
        owner_kind="Household",
        related_id="payment",
        related_kind="Payment",
    ) == ["house", "payment"]


@pytest.mark.parametrize("kinds", [["Household"], ["Household", "Person", "Person"]])
def test_unexecuted_derivation_still_rejects_known_slot_mismatch(kinds):
    artifact, request = _case(kinds)
    request["dataset"]["inputs"][0]["entity"] = "Payment"
    with pytest.raises(RelationBindingError, match="Cannot order"):
        bind_request_relations(request, artifact)


@pytest.mark.parametrize("kinds", [["Household"], ["Household", "Person", "Person"]])
def test_schema_slot_count_is_checked_even_when_derivation_overrides_it(kinds):
    artifact, request = _case(["Household", "Person"])
    artifact["program"]["relations"][1]["slot_entities"] = kinds
    with pytest.raises(RelationBindingError, match="Invalid slot_entities"):
        bind_request_relations(request, artifact)


@pytest.mark.parametrize("kinds", [["Household"], ["Household", "Person", "Person"]])
@pytest.mark.parametrize("execution", ["base", "version", "base_with_version"])
def test_executable_derivation_requires_one_entity_kind_per_slot(kinds, execution):
    artifact, request = _case(kinds)
    aggregate = {
        "kind": "count_related",
        "relation": "D",
        "current_slot": 0,
        "related_slot": 1,
    }
    constant = {"kind": "literal", "value": {"kind": "integer", "value": 1}}
    rule = {
        "name": "n",
        "entity": "Household",
        "expr": constant if execution == "version" else aggregate,
    }
    if execution != "base":
        rule["versions"] = [{"expr": aggregate if execution == "version" else constant}]
    artifact["program"]["derived"].append(rule)
    with pytest.raises(RelationBindingError, match="Invalid slot_entities"):
        bind_request_relations(request, artifact)
