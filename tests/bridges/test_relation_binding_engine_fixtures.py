"""Differential cases from axiom-rules-engine's pinned #190 tests.

The execution fixtures are copied verbatim. Predicate variants reproduce every
explicit orientation case in relation_usage_context.rs and the nested scalar
operand in relation_scalar_context.rs. The typed fixture comes from the pinned
engine's compilation of relation_binding.rs's inline RuleSpec and wire request.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.bridges.relation_binding import bind_request_relations


_FIXTURES = Path(__file__).parents[1] / "fixtures" / "relation_binding"
_SOURCE_COMMIT = "6f62c12a9eddfba4b30a3bf156bb23d68a8aea7a"
_CONTEXT_ERROR = "can only be evaluated inside a derived relation"


def _fixture(name):
    return json.loads((_FIXTURES / name).read_text())


def _integer(value):
    return {"kind": "literal", "value": {"kind": "integer", "value": value}}


def _compare(left, op, right):
    return {"kind": "comparison", "left": left, "op": op, "right": right}


def _constant(holds):
    return _compare(_integer(1), "eq" if holds else "ne", _integer(1))


def _indicator(condition):
    return {
        "kind": "if", "condition": condition,
        "then_expr": _integer(1), "else_expr": _integer(0),
    }


def _membership(current_slot, related_slot):
    return {
        "kind": "relation_member", "relation": "head",
        "current_slot": current_slot, "related_slot": related_slot,
    }


def _context_wrappers(head):
    """The six explicit wrappers in relation_usage_context.rs, unchanged."""
    arithmetic = {"kind": "mul", "left": _indicator(head), "right": _integer(1)}
    arithmetic = {"kind": "div", "left": arithmetic, "right": _integer(1)}
    arithmetic = {"kind": "sub", "left": arithmetic, "right": _integer(0)}
    arithmetic = {"kind": "floor", "value": arithmetic}
    arithmetic = {"kind": "ceil", "value": arithmetic}
    arithmetic = {"kind": "min", "items": [_integer(1), arithmetic]}
    arithmetic = {"kind": "max", "items": [_integer(0), arithmetic]}
    return {
        "direct": head,
        "if_condition": _compare(_indicator(head), "eq", _integer(1)),
        "arithmetic_operand": _compare(
            {"kind": "add", "items": [_indicator(head), _integer(0)]},
            "eq", _integer(1),
        ),
        "if_branch": _compare({
            "kind": "if", "condition": _constant(True),
            "then_expr": _indicator({
                "kind": "not", "item": {"kind": "not", "item": head},
            }),
            "else_expr": _integer(0),
        }, "gt", _integer(0)),
        "and_or": {"kind": "or", "items": [
            _constant(False), {"kind": "and", "items": [_constant(True), head]},
        ]},
        "scalar_operators": _compare(arithmetic, "ne", _integer(0)),
    }


@dataclass
class _EngineCase:
    name: str
    request: dict
    expected: list[dict] | None


def _head_record(request):
    return next(
        record for record in request["dataset"]["relations"]
        if record["name"] == "head"
    )


def _engine_cases():
    cases = [
        _EngineCase("exact_nested_if", _fixture("relation-member-nested-if.json"), [{"n": 1}]),
    ]
    # These are the declared-order, historical executable-order, and
    # owner-first CDCC cases in relation_binding.rs, using its compiled source.
    for name in ["typed_declared_order", "legacy_executable_order", "cdcc_owner_first"]:
        request = _fixture("typed-relation-binding.json")
        if name != "typed_declared_order":
            request["dataset"]["relations"][0]["tuple"].reverse()
            count = next(
                rule for rule in request["program"]["derived"]
                if rule["name"] == "qualifying_person_count"
            )
            for version in [count, *count["versions"]]:
                version["expr"].update(current_slot=0, related_slot=1)
        if name == "cdcc_owner_first":
            request["program"]["relations"][0]["slot_entities"].reverse()
        cases.append(_EngineCase(
            name, request, [{"qualifying_person_count": 1, "credit": 1500}],
        ))
    scalar_outputs = [
        {"match_count": matches, "record_count": records, "all_records_match": outcome}
        for matches, records, outcome in [
            (2, 2, "holds"), (1, 2, "not_holds"),
            (0, 0, "not_holds"), (0, 1, "not_holds"),
        ]
    ]
    for nested in [False, True]:
        scalar = _fixture("relation-scalar-context.json")
        if nested:
            scalar["program"]["relations"][1]["derivation"]["predicate"]["right"] = {
                "kind": "if",
                "condition": _compare(
                    {"kind": "derived", "name": "group_key"}, "gt", _integer(0),
                ),
                "then_expr": {"kind": "add", "items": [
                    {"kind": "derived", "name": "group_key"}, _integer(0),
                ]},
                "else_expr": {"kind": "derived", "name": "group_key"},
            }
        cases.append(_EngineCase(
            "scalar_nested_operand" if nested else "exact_scalar_context",
            scalar, scalar_outputs,
        ))

    for slots, consumed in [((1, 0), ["p1", "h1"]), ((0, 1), ["h1", "p1"])]:
        for wrapper, predicate in _context_wrappers(_membership(*slots)).items():
            request = _fixture("relation-member-nested-if.json")
            request["program"]["relations"][2]["derivation"]["predicate"] = predicate
            _head_record(request)["tuple"] = consumed
            cases.append(_EngineCase(f"{wrapper}_slot_{slots[0]}", request, [{"n": 1}]))

    # Each shape strictly binds in the engine, but membership has no pair
    # context at execution. Such a site contributes no tuple orientation.
    rule_shapes = {
        "rule_judgment": ("judgment", "judgment", _membership(0, 1)),
        "rule_if_condition": ("integer", "scalar", _indicator(_membership(0, 1))),
        "rule_where_clause": ("integer", "scalar", {
            "kind": "count_related", "relation": "member",
            "current_slot": 1, "related_slot": 0, "where": _membership(1, 0),
        }),
    }
    for name, (dtype, semantics, expr) in rule_shapes.items():
        request = _fixture("relation-member-nested-if.json")
        request["program"]["relations"][2]["derivation"]["predicate"] = _constant(True)
        request["program"]["derived"].append({
            "name": "headed", "entity": "Household", "dtype": dtype,
            "semantics": semantics, "expr": expr,
        })
        request["queries"][0]["outputs"] = ["n", "headed"]
        cases.append(_EngineCase(name, request, None))

    request = _fixture("relation-member-nested-if.json")
    request["program"]["relations"][2]["derivation"]["predicate"] = _compare({
        "kind": "count_related", "relation": "member",
        "current_slot": 0, "related_slot": 1, "where": _membership(0, 1),
    }, "gt", _integer(0))
    cases.append(_EngineCase("derived_predicate_nested_where", request, None))
    return cases


_CASES = _engine_cases()


def test_vendored_engine_fixtures_record_exact_sources():
    sources = json.loads((_FIXTURES / "sources.json").read_text())
    assert sources["commit"] == _SOURCE_COMMIT
    assert {fixture["path"] for fixture in sources["fixtures"]} == {
        "relation-member-nested-if.json", "relation-scalar-context.json",
        "typed-relation-binding.json",
    }
    for fixture in sources["fixtures"]:
        if fixture["path"] == "typed-relation-binding.json":
            assert fixture["source_path"] == "tests/relation_binding.rs"
            assert fixture["source_constant"] == "TYPED_RELATION_RULESPEC"
        else:
            assert fixture["source_path"] == f"tests/fixtures/execution/{fixture['path']}"
        assert hashlib.sha256((_FIXTURES / fixture["path"]).read_bytes()).hexdigest() == fixture["sha256"]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("reversed_tuple", [False, True], ids=["strict_order", "reversed"])
def test_engine_asserted_slot_order_is_preserved_or_repaired(case, reversed_tuple):
    request = deepcopy(case.request)
    if reversed_tuple:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": request["program"]})
    assert bound == case.request
    assert request == before
    assert bind_request_relations(bound, {"program": bound["program"]}) == bound


@settings(max_examples=40, deadline=None)
@given(
    slots=st.sampled_from([(1, 0), (0, 1)]),
    wrappers=st.lists(st.sampled_from([
        "if_condition", "arithmetic_operand", "if_branch", "and_or", "scalar_operators",
    ]), max_size=4),
    reversed_tuple=st.booleans(),
)
def test_generated_scalar_wrappers_preserve_the_engine_pair_context(
    slots, wrappers, reversed_tuple,
):
    # This is the context-preserving subset of the upstream generated-predicate
    # differential: nesting scalar wrappers must never change the bound pair.
    expected = _fixture("relation-member-nested-if.json")
    predicate = _membership(*slots)
    for wrapper in wrappers:
        predicate = _context_wrappers(predicate)[wrapper]
    expected["program"]["relations"][2]["derivation"]["predicate"] = predicate
    _head_record(expected)["tuple"] = ["p1", "h1"] if slots == (1, 0) else ["h1", "p1"]
    request = deepcopy(expected)
    if reversed_tuple:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": request["program"]})
    assert bound == expected
    assert bind_request_relations(bound, {"program": bound["program"]}) == bound
    assert request == before


def _unlabelled_count_request(reversed_tuple):
    request = _fixture("typed-relation-binding.json")
    request["dataset"]["inputs"] = []
    count = next(
        rule for rule in request["program"]["derived"]
        if rule["name"] == "qualifying_person_count"
    )
    for version in [count, *count["versions"]]:
        version["expr"].pop("where")
    if reversed_tuple:
        request["dataset"]["relations"][0]["tuple"].reverse()
    return request


@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_typed_count_with_no_endpoint_inputs_preserves_unknown_order(reversed_tuple):
    request = _unlabelled_count_request(reversed_tuple)
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": request["program"]})
    # Neither endpoint has an identity label, so there is no basis to exchange
    # opaque IDs. The engine's strict binding also leaves this tuple alone.
    assert bound == before
    assert bind_request_relations(bound, {"program": bound["program"]}) == bound
    assert request == before


@pytest.fixture(scope="module")
def strict_engine():
    value = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if not value or not Path(value).is_file():
        message = "AXIOM_STRICT_RELATION_ENGINE_BIN must point to the pinned #190 engine"
        if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    return Path(value).resolve()


def _run(binary, request):
    assert "relation_binding" not in request
    return subprocess.run(
        [str(binary), "run"], input=json.dumps(request), capture_output=True,
        text=True, check=False, timeout=60,
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("reversed_tuple", [False, True], ids=["strict_order", "reversed"])
def test_strict_engine_replays_binding_differential(strict_engine, case, mode, reversed_tuple):
    request = deepcopy(case.request)
    request["mode"] = mode
    if reversed_tuple:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
        rejected = _run(strict_engine, request)
        assert rejected.returncode != 0
        assert "relation" in rejected.stderr.lower()
        assert "expected" in rejected.stderr.lower()
    bound = bind_request_relations(request, {"program": request["program"]})
    result = _run(strict_engine, bound)
    if case.expected is None:
        # The engine asserts these datasets bind, while execution rejects the
        # out-of-context predicate. A binding mismatch is a different defect.
        assert result.returncode != 0
        assert _CONTEXT_ERROR in result.stderr
        return
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    assert len(response["results"]) == len(case.expected)
    for row, expected in zip(response["results"], case.expected, strict=True):
        for name, value in expected.items():
            output = row["outputs"][name]
            actual = output["outcome"] if isinstance(value, str) else int(output["value"]["value"])
            assert actual == value, (case.name, mode, row["entity_id"], name)


@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_strict_engine_accepts_count_without_endpoint_inputs(strict_engine, mode, reversed_tuple):
    request = _unlabelled_count_request(reversed_tuple)
    request["mode"] = mode
    bound = bind_request_relations(request, {"program": request["program"]})
    assert bound == request
    result = _run(strict_engine, bound)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    count = response["results"][0]["outputs"]["qualifying_person_count"]["value"]["value"]
    assert int(count) == (0 if reversed_tuple else 1)
