"""Pin the engine branches missed by the round 12 mutation review."""

from copy import deepcopy
import warnings

import pytest

from axiom_oracles.bridges.relation_binding import (
    RelationBindingAmbiguityWarning,
    RelationBindingError,
    bind_request_relations,
    relation_binding_diagnostics,
)


def _integer(value=0):
    return {"kind": "literal", "value": {"kind": "integer", "value": value}}


def _count(relation, *, current_slot=0):
    return {
        "kind": "count_related",
        "relation": relation,
        "current_slot": current_slot,
        "related_slot": 1 - current_slot,
    }


def _request(*names, roles=False):
    records = []
    for name in names:
        record = {"name": name, "tuple": ["person", "house"]}
        if roles:
            record["roles"] = {
                "owner_id": "house",
                "owner_kind": "Household",
                "related_id": "person",
                "related_kind": "Person",
            }
        records.append(record)
    return {
        "dataset": {
            "inputs": [
                {"entity_id": "house", "entity": "Household"},
                {"entity_id": "person", "entity": "Person"},
            ],
            "relations": records,
        }
    }


def _bind_with_diagnostics(request, artifact):
    before = deepcopy(request)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RelationBindingAmbiguityWarning)
        bound = bind_request_relations(request, artifact)
    assert request == before
    assert all(
        isinstance(item.message, RelationBindingAmbiguityWarning) for item in caught
    )
    return bound, relation_binding_diagnostics(item.message for item in caught)


@pytest.mark.parametrize("roles", [False, True], ids=["raw", "roles"])
def test_versions_only_execution_diagnoses_active_relation(roles):
    artifact = {
        "program": {
            "relations": [
                {"name": name, "arity": 2}
                for name in ("base_members", "version_members")
            ],
            "derived": [
                {
                    "name": "member_count",
                    "entity": "Household",
                    "expr": _count("base_members"),
                    "versions": [{"expr": _count("version_members")}],
                }
            ],
        }
    }
    request = _request("base_members", "version_members", roles=roles)
    bound, diagnostics = _bind_with_diagnostics(request, artifact)
    assert bound == request
    assert diagnostics == {
        "count": 1,
        "by_relation": {"version_members": 1},
        "samples": [{"relation": "version_members", "tuple": ["person", "house"]}],
    }


@pytest.mark.parametrize("roles", [False, True], ids=["raw", "roles"])
def test_no_match_patterns_execute_relation_and_emit_diagnostic(roles):
    artifact = {
        "program": {
            "relations": [{"name": "members", "arity": 2}],
            "derived": [
                {
                    "name": "no_matching_count",
                    "entity": "Household",
                    "expr": {
                        "kind": "no_match",
                        "subject": _integer(),
                        "patterns": [_count("members")],
                    },
                }
            ],
        }
    }
    request = _request("members", roles=roles)
    bound, diagnostics = _bind_with_diagnostics(request, artifact)
    assert bound == request
    assert diagnostics == {
        "count": 1,
        "by_relation": {"members": 1},
        "samples": [{"relation": "members", "tuple": ["person", "house"]}],
    }


@pytest.mark.parametrize("roles", [False, True], ids=["raw", "roles"])
def test_no_match_patterns_validate_contradictory_aggregate(roles):
    artifact = {
        "program": {
            "relations": [
                {
                    "name": "members",
                    "arity": 2,
                    "slot_entities": ["Household", "Person"],
                }
            ],
            "derived": [
                {
                    "name": "no_matching_count",
                    "entity": "Household",
                    "expr": {
                        "kind": "no_match",
                        "subject": _integer(),
                        "patterns": [_count("members", current_slot=1)],
                    },
                }
            ],
        }
    }
    with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
        bind_request_relations(_request("members", roles=roles), artifact)


@pytest.mark.parametrize("roles", [False, True], ids=["raw", "roles"])
@pytest.mark.parametrize("record_kind", ["derived", "parameters"])
@pytest.mark.parametrize("public_id", ["absent", "null", "present"])
def test_public_relation_resolution_requires_rule_or_parameter_id(
    roles, record_kind, public_id
):
    marker = {"name": "marker"}
    if record_kind == "derived":
        marker.update(entity="Household", expr=_integer())
    if public_id != "absent":
        marker["id"] = "us:statutes/26/1#marker" if public_id == "present" else None
    artifact = {
        "program": {
            "relations": [
                {
                    "name": "members",
                    "arity": 2,
                    "slot_entities": ["Household", "Person"],
                }
            ],
            record_kind: [marker],
        }
    }
    public_name = "us:statutes/26/1#relation.members"
    bound, diagnostics = _bind_with_diagnostics(
        _request(public_name, "members", roles=roles), artifact
    )
    public_record, bare_record = bound["dataset"]["relations"]
    assert public_record["tuple"] == (
        ["house", "person"] if public_id == "present" else ["person", "house"]
    )
    assert bare_record["tuple"] == ["house", "person"]
    assert diagnostics == {"count": 0, "by_relation": {}, "samples": []}
