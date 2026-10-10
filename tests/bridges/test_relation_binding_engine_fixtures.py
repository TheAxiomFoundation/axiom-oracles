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
from hypothesis import example, given, settings, strategies as st

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


_IDENTITY_CASES = st.fixed_dictionaries({
    # A generated executable owner must survive classification regardless of
    # its name. Neither endpoint strategy uses the projector's fixed inventory.
    "owner_kind": st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12)
    .map(lambda suffix: "Owner" + suffix),
    "member_kind": st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12)
    .map(lambda suffix: "Member" + suffix),
    "typed": st.booleans(),
    "owner_slot": st.integers(0, 1),
    "reversed_tuple": st.booleans(),
    "owner_pseudo": st.booleans(),
    "member_pseudo": st.booleans(),
    "with_member_inputs": st.booleans(),
    "member_numbers": st.lists(st.integers(0, 3), min_size=1, max_size=5),
    "owner_value": st.integers(-1000, 1000),
    "year": st.integers(2026, 2029),
    "mode": st.sampled_from(["explain", "fast"]),
}).filter(lambda case: case["typed"] or case["with_member_inputs"])
_MIXED_SCOPE_CASE = {
    "owner_kind": "Household", "member_kind": "Person", "typed": False,
    "owner_slot": 1, "reversed_tuple": True, "owner_pseudo": True,
    "member_pseudo": True, "with_member_inputs": True,
    "member_numbers": [0, 0], "owner_value": 17, "year": 2026, "mode": "explain",
}
_CUSTOM_OWNER_CASE = {
    "owner_kind": "Organization", "member_kind": "Payment", "typed": False,
    "owner_slot": 0, "reversed_tuple": True, "owner_pseudo": False,
    "member_pseudo": False, "with_member_inputs": True,
    "member_numbers": [0], "owner_value": 8, "year": 2026, "mode": "fast",
}


def _identity_request(case):
    """Vary the compiled typed fixture, preserving its executable wire shape."""
    expected = _fixture("typed-relation-binding.json")
    expected["mode"] = case["mode"]
    program = expected["program"]
    schema = program["relations"][0]
    if case["typed"]:
        schema["slot_entities"] = [case["member_kind"], case["owner_kind"]]
    else:
        schema.pop("slot_entities")
    for rule in program["derived"]:
        rule["entity"] = (
            case["member_kind"] if rule["entity"] == "Person" else case["owner_kind"]
        )
        if rule["name"] == "qualifying_person_count":
            for version in [rule, *rule["versions"]]:
                expr = version["expr"]
                expr.update(current_slot=case["owner_slot"], related_slot=1 - case["owner_slot"])
                if not case["with_member_inputs"]:
                    expr.pop("where")
    if not case["typed"]:
        # Distinct scalar scopes alone do not prove endpoint identities.
        program["relations"].append({"name": "member_identity", "arity": 2})
        program["derived"].append({
            "name": "member_identity_count", "entity": case["member_kind"],
            "dtype": "integer", "semantics": "scalar",
            "expr": {"kind": "count_related", "relation": "member_identity",
                     "current_slot": 0, "related_slot": 1},
        })
    owner_input = deepcopy(expected["dataset"]["inputs"][1])
    owner_input.update(entity=case["owner_kind"], entity_id="owner-x")
    owner_input["value"]["value"] = case["owner_value"]
    member_input = expected["dataset"]["inputs"][0]
    interval = {"start": f"{case['year']}-01-01", "end": f"{case['year']}-12-31"}
    owner_input["interval"] = deepcopy(interval)
    member_input["interval"] = deepcopy(interval)
    expected["queries"][0]["period"].update(interval)
    expected["dataset"]["inputs"] = [owner_input]
    for member_number in sorted(set(case["member_numbers"])):
        if case["with_member_inputs"]:
            record = deepcopy(member_input)
            record.update(entity=case["member_kind"], entity_id=f"member-{member_number}")
            record["value"]["value"] = member_number % 2 == 0
            expected["dataset"]["inputs"].append(record)
    for pseudo, kind, name, ids in [
        (case["owner_pseudo"], "StatutoryDollarAmount", "owner_broadcast", ["owner-x"]),
        (case["member_pseudo"], "BroadcastThreshold", "member_broadcast", [
            f"member-{number}" for number in sorted(set(case["member_numbers"]))
        ]),
    ]:
        if not pseudo:
            continue
        program["derived"].append({
            "name": name, "entity": kind, "dtype": "integer", "semantics": "scalar",
            "expr": {"kind": "input", "name": name},
        })
        expected["dataset"]["inputs"].extend({
            "name": name, "entity": kind, "entity_id": entity_id,
            "interval": deepcopy(interval), "value": {"kind": "integer", "value": 31},
        } for entity_id in ids)
    if case["typed"] and case["member_pseudo"] and not case["with_member_inputs"]:
        # The pinned strict engine recognizes a missing member identity only
        # when scalar scopes are multiple. Its singleton-scope limitation is
        # covered separately by binder tests; this native control must run.
        program["derived"].append({
            "name": "member_limit", "entity": "BroadcastMemberLimit",
            "dtype": "integer", "semantics": "scalar",
            "expr": {"kind": "input", "name": "member_limit"},
        })
        expected["dataset"]["inputs"].extend({
            "name": "member_limit", "entity": "BroadcastMemberLimit",
            "entity_id": f"member-{number}", "interval": deepcopy(interval),
            "value": {"kind": "integer", "value": 23},
        } for number in sorted(set(case["member_numbers"])))
    expected["dataset"]["relations"] = []
    for member_number in case["member_numbers"]:
        pair = ["owner-x", f"member-{member_number}"]
        if case["owner_slot"] == 1:
            pair.reverse()
        expected["dataset"]["relations"].append({
            "name": schema["name"], "tuple": pair, "interval": deepcopy(interval),
        })
    expected["queries"][0]["entity_id"] = "owner-x"
    request = deepcopy(expected)
    if case["reversed_tuple"]:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    return request, expected


def _assert_identity_binding(request, expected):
    before = deepcopy(request)
    artifact = {"program": expected["program"]}
    bound = bind_request_relations(request, artifact)
    # Equality of the complete request includes values, input scopes, periods,
    # queries, relation multiplicity, and every non-tuple relation field.
    assert bound == expected
    assert request == before
    assert bind_request_relations(bound, artifact) == bound
    if before == expected:
        assert json.dumps(bound) == json.dumps(before)
    return bound


@settings(max_examples=80, deadline=None)
@given(case=_IDENTITY_CASES)
@example(case=_MIXED_SCOPE_CASE)
@example(case=_CUSTOM_OWNER_CASE)
def test_generated_endpoint_identities_determine_executable_order(case):
    request, expected = _identity_request(case)
    _assert_identity_binding(request, expected)


def _strict_integer_outputs(binary, request, name):
    result = _run(binary, request)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    return [int(row["outputs"][name]["value"]["value"]) for row in response["results"]]


@settings(max_examples=80, deadline=None)
@given(case=_IDENTITY_CASES)
@example(case=_MIXED_SCOPE_CASE)
@example(case=_CUSTOM_OWNER_CASE)
def test_strict_engine_generated_endpoint_identity_differential(strict_engine, case):
    request, expected = _identity_request(case)
    # The independently constructed executable-order request is the native
    # oracle; duplicates and count-only behavior belong to the engine.
    counts = _strict_integer_outputs(strict_engine, expected, "qualifying_person_count")
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": expected["program"]})
    assert request == before
    assert _strict_integer_outputs(strict_engine, bound, "qualifying_person_count") == counts
    _assert_identity_binding(request, expected)


def _nested_custom_owner_request(owner_kind, outer_slot, nested_slot, proof_first):
    expected = _fixture("typed-relation-binding.json")
    interval = deepcopy(expected["dataset"]["relations"][0]["interval"])

    def count(name, slot, predicate=None):
        expr = {
            "kind": "count_related", "relation": name,
            "current_slot": slot, "related_slot": 1 - slot,
        }
        if predicate is not None:
            expr["where"] = predicate
        return expr

    def positive(name):
        return _compare({"kind": "derived", "name": name}, "gt", _integer(0))

    def rule(name, entity, expr):
        return {
            "name": name, "entity": entity, "dtype": "integer",
            "semantics": "scalar", "expr": expr,
        }

    proof = rule("org_count", owner_kind, count("org_proof", 0))
    outer = rule("n", "Household", count("members", outer_slot, {
        "kind": "and", "items": [
            positive("org_label"),
            _compare(count("payments", nested_slot, positive("payment_amount")), "gt", _integer(0)),
        ],
    }))
    expected["program"]["relations"] = [
        {"name": name, "arity": 2}
        for name in ["members", "payments", "org_proof", "payment_proof"]
    ]
    expected["program"]["derived"] = [
        *([proof, outer] if proof_first else [outer, proof]),
        rule("payment_count", "Payment", count("payment_proof", 0)),
        rule("org_label", owner_kind, {"kind": "input", "name": "org_label"}),
        rule("payment_amount", "Payment", {"kind": "input", "name": "payment_amount"}),
        rule("house_label", "Household", {"kind": "input", "name": "house_label"}),
    ]
    expected["dataset"]["inputs"] = [{
        "name": name, "entity": kind, "entity_id": entity_id,
        "interval": deepcopy(interval), "value": {"kind": "integer", "value": 1},
    } for name, kind, entity_id in [
        ("house_label", "Household", "h"), ("org_label", owner_kind, "o"),
        ("payment_amount", "Payment", "p"),
    ]]
    expected["dataset"]["relations"] = [{
        "name": name, "tuple": pair if slot == 0 else pair[::-1],
        "interval": deepcopy(interval),
    } for name, slot, pair in [
        ("members", outer_slot, ["h", "o"]), ("payments", nested_slot, ["o", "p"]),
    ]]
    expected["queries"][0].update(entity_id="h", outputs=["n"])
    return expected


@settings(max_examples=40, deadline=None)
@given(
    owner_kind=st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12)
    .map(lambda suffix: "Organization" + suffix),
    outer_slot=st.integers(0, 1), nested_slot=st.integers(0, 1),
    proof_first=st.booleans(), reversed_tuple=st.booleans(), pattern_metadata=st.booleans(),
)
@example(
    owner_kind="Organization", outer_slot=0, nested_slot=0,
    proof_first=False, reversed_tuple=True, pattern_metadata=True,
)
def test_strict_engine_generated_nested_custom_owner_context(
    strict_engine, owner_kind, outer_slot, nested_slot, proof_first, reversed_tuple,
    pattern_metadata,
):
    expected = _nested_custom_owner_request(owner_kind, outer_slot, nested_slot, proof_first)
    if pattern_metadata:
        outer = next(rule for rule in expected["program"]["derived"] if rule["name"] == "n")
        comparison = outer["expr"]["where"]["items"][0]
        reference = comparison["left"]
        comparison["left"] = {
            "kind": "if", "condition": _constant(True), "then_expr": reference,
            "else_expr": {
                "kind": "no_match", "subject": deepcopy(reference),
                "patterns": [{"kind": "derived", "name": "person_metadata"}],
            },
        }
        expected["program"]["derived"].append({
            "name": "person_metadata", "entity": "Person", "dtype": "integer",
            "semantics": "scalar", "expr": {"kind": "input", "name": "person_metadata"},
        })
    request = deepcopy(expected)
    if reversed_tuple:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    assert _strict_integer_outputs(strict_engine, expected, "n") == [1]
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": expected["program"]})
    assert request == before
    assert _strict_integer_outputs(strict_engine, bound, "n") == [1]
    _assert_identity_binding(request, expected)


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("reversed_tuple", [False, True])
@pytest.mark.parametrize("mode", ["explain", "fast"])
def test_strict_engine_no_match_patterns_supply_no_slot_evidence(
    strict_engine, owner_slot, reversed_tuple, mode,
):
    case = {
        **_MIXED_SCOPE_CASE, "typed": True, "owner_slot": owner_slot,
        "owner_pseudo": False, "member_pseudo": False,
        "member_numbers": [0], "reversed_tuple": reversed_tuple, "mode": mode,
    }
    request, expected = _identity_request(case)
    for payload in [request, expected]:
        count = next(
            rule for rule in payload["program"]["derived"]
            if rule["name"] == "qualifying_person_count"
        )
        for version in [count, *count["versions"]]:
            actual = version["expr"]
            pattern = deepcopy(actual)
            pattern.update(current_slot=1 - owner_slot, related_slot=owner_slot)
            version["expr"] = {
                "kind": "if", "condition": _constant(True), "then_expr": actual,
                "else_expr": {"kind": "no_match", "subject": _integer(0), "patterns": [pattern]},
            }
    assert _strict_integer_outputs(strict_engine, expected, "qualifying_person_count") == [1]
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": expected["program"]})
    assert request == before
    assert _strict_integer_outputs(strict_engine, bound, "qualifying_person_count") == [1]
    _assert_identity_binding(request, expected)


def _broadcast_reference_request(case, alias_depth, versions, optional_default):
    request, expected = _identity_request(case)
    for payload in [request, expected]:
        program = payload["program"]
        body = {"kind": "input_or_else", "name": "optional_threshold", "default": _integer(1)["value"]} \
            if optional_default else _integer(1)
        for index in range(alias_depth + 1):
            name = f"threshold_{index}"
            rule = {
                # The pinned strict engine treats a typed constant's nominal
                # scope as a member constraint. Use its declared member kind
                # for that native control; pure properties cover owner scopes.
                "name": name, "entity": case["member_kind"] if case["typed"] else case["owner_kind"],
                "dtype": "integer",
                "semantics": "scalar", "expr": deepcopy(body),
            }
            if versions:
                rule["versions"] = [{
                    "effective_from": "2026-01-01", "semantics": "scalar",
                    "expr": deepcopy(body),
                }]
                rule["expr"] = {"kind": "input", "name": "ignored_base"}
            program["derived"].append(rule)
            body = {"kind": "derived", "name": name}
        count = next(rule for rule in program["derived"] if rule["name"] == "qualifying_person_count")
        for version in [count, *count["versions"]]:
            version["expr"]["where"] = _compare(deepcopy(body), "gt", _integer(0))
    return request, expected


@settings(max_examples=40, deadline=None)
@given(
    case=_IDENTITY_CASES, alias_depth=st.integers(0, 3),
    versions=st.booleans(), optional_default=st.booleans(),
)
@example(case={**_MIXED_SCOPE_CASE, "reversed_tuple": False, "owner_pseudo": False, "member_pseudo": False},
         alias_depth=0, versions=False, optional_default=False)
@example(case={**_MIXED_SCOPE_CASE, "reversed_tuple": False, "owner_pseudo": False, "member_pseudo": False},
         alias_depth=1, versions=True, optional_default=True)
def test_strict_engine_broadcast_reference_differential(
    strict_engine, case, alias_depth, versions, optional_default,
):
    request, expected = _broadcast_reference_request(case, alias_depth, versions, optional_default)
    counts = _strict_integer_outputs(strict_engine, expected, "qualifying_person_count")
    assert counts[0] > 0
    bound = _assert_identity_binding(request, expected)
    assert _strict_integer_outputs(strict_engine, bound, "qualifying_person_count") == counts


def _nested_broadcast_request(owner_kind, outer_slot, nested_slot, typed, optional_default):
    expected = _nested_custom_owner_request(owner_kind, outer_slot, nested_slot, False)
    program = expected["program"]
    program["relations"] = [schema for schema in program["relations"] if schema["name"] != "org_proof"]
    program["derived"] = [rule for rule in program["derived"] if rule["name"] != "org_count"]
    for rule in program["derived"]:
        if rule["entity"] == "Household":
            rule["entity"] = owner_kind
        if rule["name"] == "org_label":
            rule["expr"] = {
                "kind": "input_or_else", "name": "optional_threshold", "default": _integer(1)["value"],
            } if optional_default else _integer(1)
    for record in expected["dataset"]["inputs"]:
        if record["entity"] == "Household":
            record["entity"] = owner_kind
    program["derived"].append({
        "name": "org_input", "entity": owner_kind, "dtype": "integer",
        "semantics": "scalar", "expr": {"kind": "input", "name": "org_label"},
    })
    if typed:
        program["relations"][0]["slot_entities"] = [owner_kind, owner_kind]
        program["relations"][1]["slot_entities"] = ["Payment", owner_kind]
    return expected


@settings(max_examples=40, deadline=None)
@given(
    owner_kind=st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12)
    .map(lambda suffix: "Owner" + suffix),
    outer_slot=st.integers(0, 1), nested_slot=st.integers(0, 1),
    typed=st.booleans(), optional_default=st.booleans(), reversed_tuple=st.booleans(),
)
@example(owner_kind="Household", outer_slot=0, nested_slot=0,
         typed=False, optional_default=False, reversed_tuple=True)
def test_strict_engine_same_kind_member_context_survives_broadcast_reference(
    strict_engine, owner_kind, outer_slot, nested_slot, typed, optional_default, reversed_tuple,
):
    expected = _nested_broadcast_request(owner_kind, outer_slot, nested_slot, typed, optional_default)
    request = deepcopy(expected)
    if reversed_tuple:
        request["dataset"]["relations"][1]["tuple"].reverse()
    # Both outer endpoints have the same real identity. Their original pair
    # stays intact, while that identity still scopes the nested aggregate.
    assert _strict_integer_outputs(strict_engine, expected, "n") == [1]
    bound = _assert_identity_binding(request, expected)
    assert _strict_integer_outputs(strict_engine, bound, "n") == [1]


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_strict_engine_row_dependent_alias_retains_nominal_scope(
    strict_engine, owner_slot, reversed_tuple,
):
    case = {
        **_CUSTOM_OWNER_CASE, "owner_kind": "Household", "member_kind": "Organization",
        "typed": True, "owner_slot": owner_slot, "reversed_tuple": reversed_tuple,
    }
    request, expected = _identity_request(case)
    for payload in [request, expected]:
        payload["program"]["derived"].extend([{
            "name": "person_leaf", "entity": "Person", "dtype": "integer",
            "semantics": "scalar", "expr": {"kind": "input", "name": "org_amount"},
        }, {
            "name": "organization_alias", "entity": "Organization", "dtype": "integer",
            "semantics": "scalar", "expr": {"kind": "derived", "name": "person_leaf"},
        }])
        payload["dataset"]["inputs"].append({
            "name": "org_amount", "entity": "Organization", "entity_id": "member-0",
            "interval": deepcopy(payload["dataset"]["inputs"][0]["interval"]),
            "value": {"kind": "integer", "value": 1},
        })
        count = next(rule for rule in payload["program"]["derived"] if rule["name"] == "qualifying_person_count")
        for version in [count, *count["versions"]]:
            version["expr"]["where"] = _compare(
                {"kind": "derived", "name": "organization_alias"}, "gt", _integer(0),
            )
    assert _strict_integer_outputs(strict_engine, expected, "qualifying_person_count") == [1]
    bound = _assert_identity_binding(request, expected)
    assert _strict_integer_outputs(strict_engine, bound, "qualifying_person_count") == [1]
