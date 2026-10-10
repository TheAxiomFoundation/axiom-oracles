"""An unresolved owner/member assignment must preserve and report its tuple."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import warnings

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges.relation_binding import bind_request_relations, relation_tuple


OWNERS = st.one_of(
    st.just("Person"),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12).map(
        lambda text: "Owner_" + text
    ),
)


def request_for(owner, owner_slot, pseudo_owner, pseudo_member, query, typed):
    period = {"period_kind": "month", "start": "2026-01-01", "end": "2026-01-31"}
    interval = {key: period[key] for key in ("start", "end")}

    def rule(name, entity, expr):
        return {"name": name, "entity": entity, "dtype": "integer",
                "unit": None, "semantics": "scalar", "expr": expr}

    def inp(name, entity, entity_id):
        return {"name": name, "entity": entity, "entity_id": entity_id,
                "interval": deepcopy(interval), "value": {"kind": "integer", "value": 1}}

    inputs = [inp("marker", owner, "member")]
    for enabled, entity_id in ((pseudo_owner, "owner"), (pseudo_member, "member")):
        if enabled:
            inputs.append(inp("threshold", "BroadcastThreshold", entity_id))
    ids = ["owner", "member"] if owner_slot == 0 else ["member", "owner"]
    schema = {"name": "members", "arity": 2}
    if typed:
        schema["slot_entities"] = [owner, owner]
    return {
        "mode": "explain",
        "program": {"units": [], "parameters": [], "relations": [schema], "derived": [
            rule("n", owner, {"kind": "count_related", "relation": "members",
                 "current_slot": owner_slot, "related_slot": 1 - owner_slot, "where": None}),
            rule("marker", owner, {"kind": "input", "name": "marker"}),
            rule("threshold", "BroadcastThreshold", {"kind": "input", "name": "threshold"}),
        ]},
        "dataset": {"inputs": inputs, "relations": [
            {"name": "members", "tuple": list(ids), "interval": deepcopy(interval)},
            {"name": "members", "tuple": list(ids), "interval": deepcopy(interval)},
        ]},
        "queries": [] if query is None else [{"entity_id": query,
                    "period": deepcopy(period), "outputs": ["n"]}],
    }


@settings(deadline=None)
@example(owner="Person", owner_slot=0, pseudo_owner=False, pseudo_member=False,
         typed=False, query="owner", reversed_tuple=False)
@example(owner="Owner_org", owner_slot=1, pseudo_owner=True, pseudo_member=True,
         typed=True, query="member", reversed_tuple=True)
@given(owner=OWNERS, owner_slot=st.integers(0, 1), pseudo_owner=st.booleans(),
       pseudo_member=st.booleans(), typed=st.booleans(),
       query=st.sampled_from([None, "owner", "member"]), reversed_tuple=st.booleans())
def test_unknown_owner_and_labelled_same_kind_member_preserve_and_report(
    owner, owner_slot, pseudo_owner, pseudo_member, typed, query, reversed_tuple,
):
    request = request_for(owner, owner_slot, pseudo_owner, pseudo_member, query, typed)
    if reversed_tuple:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    before_bytes = json.dumps(request)
    with warnings.catch_warnings(record=True) as reports:
        warnings.simplefilter("always")
        bound = bind_request_relations(request, request)
    assert bound == before
    assert json.dumps(bound) == before_bytes
    assert request == before
    assert len(reports) == len(request["dataset"]["relations"])
    for report, record in zip(reports, request["dataset"]["relations"], strict=True):
        assert report.message.relation == record["name"]
        assert report.message.tuple == tuple(record["tuple"])
        assert record["name"] in str(report.message)
        assert repr(record["tuple"]) in str(report.message)
    with warnings.catch_warnings(record=True) as repeated:
        warnings.simplefilter("always")
        assert bind_request_relations(bound, request) == bound
    assert len(repeated) == len(reports)


@settings(deadline=None)
@given(owner=OWNERS, owner_slot=st.integers(0, 1), typed=st.booleans())
def test_explicit_same_kind_roles_use_executable_owner_slot(owner, owner_slot, typed):
    artifact = request_for(owner, owner_slot, False, False, None, typed)
    emitted = relation_tuple(
        artifact, "members", owner_id="owner", owner_kind=owner,
        related_id="member", related_kind=owner,
    )
    assert emitted[owner_slot] == "owner"
    assert emitted[1 - owner_slot] == "member"


def nominal_scope_request(owner, owner_slot, nested_slot):
    request = request_for(owner, owner_slot, False, True, "owner", False)
    program = request["program"]
    program["derived"].append({
        "name": "person_threshold", "entity": "Person", "dtype": "integer",
        "semantics": "scalar", "expr": {"kind": "input", "name": "threshold"},
    })
    program["derived"][0]["expr"]["where"] = {
        "kind": "comparison", "op": "gt",
        "left": {"kind": "derived", "name": "person_threshold"},
        "right": {"kind": "literal", "value": {"kind": "integer", "value": 0}},
    }
    if nested_slot is not None:
        program["relations"].append({"name": "payments", "arity": 2})
        program["derived"].append({
            "name": "payment_marker", "entity": "Person", "dtype": "integer",
            "semantics": "scalar", "expr": {"kind": "input", "name": "payment_marker"},
        })
        interval = deepcopy(request["dataset"]["relations"][0]["interval"])
        request["dataset"]["inputs"].append({
            "name": "payment_marker", "entity": "Person", "entity_id": "payment",
            "interval": deepcopy(interval), "value": {"kind": "integer", "value": 1},
        })
        ids = ["member", "payment"] if nested_slot == 0 else ["payment", "member"]
        request["dataset"]["relations"].append({
            "name": "payments", "tuple": ids, "interval": interval,
        })
        outer = program["derived"][0]["expr"]
        outer["where"] = {"kind": "and", "items": [outer["where"], {
            "kind": "comparison", "op": "gt",
            "left": {"kind": "count_related", "relation": "payments",
                     "current_slot": nested_slot, "related_slot": 1 - nested_slot},
            "right": {"kind": "literal", "value": {"kind": "integer", "value": 0}},
        }]}
    return request


@settings(deadline=None)
@given(owner=OWNERS, owner_slot=st.integers(0, 1),
       nested_slot=st.one_of(st.none(), st.integers(0, 1)))
@example(owner="TaxUnit", owner_slot=0, nested_slot=0)
def test_nominal_person_scope_cannot_resolve_same_kind_roles(owner, owner_slot, nested_slot):
    request = nominal_scope_request(owner, owner_slot, nested_slot)
    before = deepcopy(request)
    with pytest.warns(UserWarning, match="members"):
        bound = bind_request_relations(request, request)
    assert bound == before
    assert request == before


@pytest.fixture(scope="session")
def strict_engine():
    path = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if path and Path(path).is_file():
        return path
    if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
        pytest.fail("Pinned strict relation engine is required")
    pytest.skip("Pinned strict relation engine is unavailable")


def native_results(strict_engine, payload):
    result = subprocess.run([strict_engine, "run"], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    return response["results"]


@settings(max_examples=24, deadline=None)
@given(owner=OWNERS, owner_slot=st.integers(0, 1), typed=st.booleans(),
       reversed_tuple=st.booleans(), query=st.sampled_from([None, "owner", "member"]))
def test_strict_engine_preserves_ambiguous_native_results(
    strict_engine, owner, owner_slot, typed, reversed_tuple, query,
):
    request = request_for(owner, owner_slot, False, False, query, typed)
    if reversed_tuple:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    with pytest.warns(UserWarning, match="members"):
        bound = bind_request_relations(request, request)
    assert bound == request == before

    assert native_results(strict_engine, bound) == native_results(strict_engine, before)


@settings(max_examples=24, deadline=None)
@given(owner=OWNERS, owner_slot=st.integers(0, 1),
       nested_slot=st.one_of(st.none(), st.integers(0, 1)))
@example(owner="TaxUnit", owner_slot=0, nested_slot=0)
def test_strict_engine_nominal_scope_preserves_correct_count(
    strict_engine, owner, owner_slot, nested_slot,
):
    request = nominal_scope_request(owner, owner_slot, nested_slot)
    before = deepcopy(request)
    with pytest.warns(UserWarning, match="members"):
        bound = bind_request_relations(request, request)
    assert bound == request == before
    correct = native_results(strict_engine, before)
    assert correct[0]["outputs"]["n"]["value"]["value"] == 1
    assert native_results(strict_engine, bound) == correct
