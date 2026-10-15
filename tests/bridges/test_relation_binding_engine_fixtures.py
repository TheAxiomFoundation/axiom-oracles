"""Pinned engine fixtures and the round 9–11 noninterference reproducers.

Historical fixtures retain their exact source bytes. Native controls now use
mandatory relation typing: obsolete declarations are rejected rather than fixed.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import warnings

import pytest

from axiom_oracles.bridges.relation_binding import (
    RelationBindingAmbiguityWarning,
    RelationBindingError,
    _effective_slot_entities,
    _filtered_entity_kinds,
    bind_request_relations,
)

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "relation_binding"
_SOURCE_COMMIT = "6f62c12a9eddfba4b30a3bf156bb23d68a8aea7a"


def _fixture(name):
    return json.loads((_FIXTURES / name).read_text())


def _integer(value):
    return {"kind": "literal", "value": {"kind": "integer", "value": value}}


def _constant():
    return {"kind": "comparison", "left": _integer(1), "op": "eq", "right": _integer(1)}


@pytest.fixture(scope="module")
def strict_engine():
    value = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if not value or not Path(value).is_file():
        message = "AXIOM_STRICT_RELATION_ENGINE_BIN must point to the pinned mandatory-typing engine"
        if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    return Path(value).resolve()


def _run(binary, request):
    assert "relation_binding" not in request
    return subprocess.run(
        [str(binary), "run"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _outputs(binary, request):
    result = _run(binary, request)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    return [row["outputs"] for row in response["results"]]


def _binding_outcome(request):
    before = deepcopy(request)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = bind_request_relations(request, {"program": request["program"]})
    assert request == before
    return result["dataset"], [str(item.message) for item in caught]


def test_vendored_engine_fixtures_record_exact_sources():
    sources = _fixture("sources.json")
    assert sources["commit"] == _SOURCE_COMMIT
    assert {item["path"] for item in sources["fixtures"]} == {
        "relation-member-nested-if.json",
        "relation-scalar-context.json",
        "typed-relation-binding.json",
    }
    for item in sources["fixtures"]:
        assert (
            hashlib.sha256((_FIXTURES / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    for item in _fixture("review-sources.json")["fixtures"]:
        assert (
            hashlib.sha256((_FIXTURES / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )


@pytest.mark.parametrize(
    "name",
    [
        "relation-member-nested-if.json",
        "relation-scalar-context.json",
        "typed-relation-binding.json",
    ],
)
def test_port_effective_types_match_engine_fixture_declarations(name):
    program = _fixture(name)["program"]
    for schema in program["relations"]:
        derivation = schema.get("derivation") or {}
        expected = derivation.get("slot_entities") or schema.get("slot_entities")
        assert expected, "the pinned fixture supplies its engine-asserted kinds"
        assert _effective_slot_entities(program, schema["name"]) == expected


@pytest.mark.parametrize(
    "name", ["relation-member-nested-if.json", "relation-scalar-context.json"]
)
@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_declared_engine_fixture_order_is_preserved_or_repaired(name, reversed_tuple):
    expected = _fixture(name)
    request = deepcopy(expected)
    if reversed_tuple:
        for row in request["dataset"]["relations"]:
            row["tuple"].reverse()
    bound = bind_request_relations(request, {"program": request["program"]})
    assert bound == expected
    assert bind_request_relations(bound, {"program": bound["program"]}) == bound


@pytest.mark.parametrize(
    "name", ["relation-member-nested-if.json", "relation-scalar-context.json"]
)
@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_strict_engine_replays_declared_fixture_order(
    strict_engine, name, mode, reversed_tuple
):
    request = _fixture(name)
    request["mode"] = mode
    if reversed_tuple:
        for row in request["dataset"]["relations"]:
            row["tuple"].reverse()
        rejected = _run(strict_engine, request)
        assert rejected.returncode != 0
        assert "strict dataset relation entity validation failed" in rejected.stderr
    before = deepcopy(request)
    bound = bind_request_relations(request, {"program": request["program"]})
    assert request == before
    _outputs(strict_engine, bound)


@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("owner_first", [False, True])
@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_strict_engine_cdcc_556_credit_remains_1500(
    strict_engine, mode, owner_first, reversed_tuple
):
    expected = _fixture("typed-relation-binding.json")
    expected["mode"] = mode
    if owner_first:
        expected["program"]["relations"][0]["slot_entities"].reverse()
        expected["dataset"]["relations"][0]["tuple"].reverse()
        count = next(
            rule
            for rule in expected["program"]["derived"]
            if rule["name"] == "qualifying_person_count"
        )
        for body in [count, *count["versions"]]:
            body["expr"].update(current_slot=0, related_slot=1)
    request = deepcopy(expected)
    if reversed_tuple:
        request["dataset"]["relations"][0]["tuple"].reverse()
        assert _run(strict_engine, request).returncode != 0
    bound = bind_request_relations(request, {"program": request["program"]})
    assert bound == expected
    result = _outputs(strict_engine, bound)[0]
    assert int(result["qualifying_person_count"]["value"]["value"]) == 1
    assert float(result["credit"]["value"]["value"]) == 1500


@pytest.mark.parametrize("mode", ["explain", "fast"])
def test_pre_typing_artifact_is_rejected_instead_of_repaired(strict_engine, mode):
    request = _fixture("typed-relation-binding.json")
    request["mode"] = mode
    count = next(
        rule
        for rule in request["program"]["derived"]
        if rule["name"] == "qualifying_person_count"
    )
    for body in [count, *count["versions"]]:
        body["expr"].update(current_slot=0, related_slot=1)
    rejected = _run(strict_engine, request)
    assert rejected.returncode != 0
    assert "relation_current_slot_entity_mismatch" in rejected.stderr
    with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
        bind_request_relations(request, {"program": request["program"]})


def _round9_pair():
    # Reconstructed from the r9 evidence report, with exact provenance recorded
    # in review-sources.json. The original report retained no request file.
    pair = _fixture("round9-scalar-broadcast.json")
    return pair["baseline"], pair["extended"]


@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_round9_conflicting_scalar_labels_remain_unknown(reversed_tuple):
    baseline, extended = _round9_pair()
    if reversed_tuple:
        for request in [baseline, extended]:
            request["dataset"]["relations"][0]["tuple"].reverse()
    assert _binding_outcome(baseline) == _binding_outcome(extended)
    assert _binding_outcome(baseline)[0]["relations"][0]["tuple"] == [
        "house",
        "payment",
    ]


@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("legacy_predicate", [False, True])
def test_strict_engine_round9_conflicting_labels_follow_engine_acceptance(
    strict_engine,
    mode,
    legacy_predicate,
):
    baseline, extended = _round9_pair()
    for request in [baseline, extended]:
        request["mode"] = mode
        if not legacy_predicate:
            # The current engine rejects the historical Person predicate on
            # Payment ids. Its valid sibling retains exactly the same wire
            # labels and supplies the native accepted-order control.
            request["program"]["derived"][0]["expr"]["where"] = _constant()
    assert _binding_outcome(baseline) == _binding_outcome(extended)
    for request in [baseline, extended]:
        assert (
            bind_request_relations(request, {"program": request["program"]}) == request
        )
        if legacy_predicate:
            result = _run(strict_engine, request)
            assert result.returncode != 0
            assert "relation_related_slot_entity_mismatch" in result.stderr
        else:
            result = _outputs(strict_engine, request)[0]
            assert int(result["n"]["value"]["value"]) == 1


@pytest.mark.parametrize("supplied_slot", [0, 1])
def test_round10_incoming_typing_never_types_source(supplied_slot):
    request = _fixture("round10-incoming-derivation.json")
    request["dataset"]["relations"][0]["tuple"] = (
        ["house", "payment"] if supplied_slot == 0 else ["payment", "house"]
    )
    assert _effective_slot_entities(request["program"], "payments") is None
    with pytest.warns(RelationBindingAmbiguityWarning):
        assert (
            bind_request_relations(request, {"program": request["program"]}) == request
        )
    baseline = _binding_outcome(request)
    request["program"]["relations"].append(
        {"name": "unrelated", "arity": 2, "slot_entities": ["Person", "Payment"]}
    )
    request["program"]["derived"].append(
        {
            "name": "unqueried",
            "entity": "Person",
            "expr": {
                "kind": "count_related",
                "relation": "unrelated",
                "current_slot": 0,
                "related_slot": 1,
            },
        }
    )
    assert _binding_outcome(request) == baseline


@pytest.mark.parametrize("mode", ["explain", "fast"])
def test_strict_engine_round10_requires_source_typing(strict_engine, mode):
    request = _fixture("round10-incoming-derivation.json")
    request["mode"] = mode
    result = _run(strict_engine, request)
    assert result.returncode != 0
    assert "untyped_relation" in result.stderr
    with pytest.warns(RelationBindingAmbiguityWarning):
        assert (
            bind_request_relations(request, {"program": request["program"]}) == request
        )


def _round11_pair(owner_slot=0, depth=1, same_kind=False):
    pair = _fixture("round11-filtered-inheritance.json")
    baseline = pair["baseline"]
    relations = baseline["program"]["relations"]
    source = relations[0]["name"]
    filtered = deepcopy(relations[-1])
    baseline["program"]["relations"] = relations[:1]
    if same_kind:
        baseline["program"]["relations"][0]["slot_entities"] = [
            "Household",
            "Household",
        ]
        baseline["program"]["derived"][-1]["entity"] = "Household"
        baseline["dataset"]["inputs"][-1]["entity"] = "Household"
    if owner_slot == 1:
        baseline["program"]["relations"][0]["slot_entities"].reverse()
        baseline["dataset"]["relations"][0]["tuple"].reverse()
    baseline["program"]["derived"][0]["expr"].update(
        current_slot=owner_slot, related_slot=1 - owner_slot
    )
    for index in range(depth):
        wrapper = deepcopy(filtered)
        wrapper["name"] = "filtered" if index == depth - 1 else f"source{index}"
        wrapper["derivation"].update(
            source_relation=source, current_slot=owner_slot, related_slot=1 - owner_slot
        )
        if index < depth - 1:
            wrapper["derivation"].pop("entity", None)
        baseline["program"]["relations"].append(wrapper)
        source = wrapper["name"]
    extended = deepcopy(baseline)
    extended["program"]["derived"].append(
        {
            "name": "unqueried",
            "entity": "SnapUnit",
            "dtype": "integer",
            "semantics": "scalar",
            "expr": {
                "kind": "count_related",
                "relation": "filtered",
                "current_slot": owner_slot,
                "related_slot": 1 - owner_slot,
            },
        }
    )
    return baseline, extended


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("depth", [1, 3])
@pytest.mark.parametrize("same_kind", [False, True])
@pytest.mark.parametrize("reversed_tuple", [False, True])
def test_round11_filtered_entity_inherits_physical_kind(
    owner_slot, depth, same_kind, reversed_tuple
):
    baseline, extended = _round11_pair(owner_slot, depth, same_kind)
    if reversed_tuple:
        for request in [baseline, extended]:
            request["dataset"]["relations"][0]["tuple"].reverse()
    assert _filtered_entity_kinds(extended["program"]) == {"SnapUnit": "Household"}
    assert _binding_outcome(baseline) == _binding_outcome(extended)


@pytest.mark.parametrize("mode", ["explain", "fast"])
@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("depth", [1, 3])
@pytest.mark.parametrize("same_kind", [False, True])
def test_strict_engine_round11_unqueried_filtered_aggregate_keeps_native_count(
    strict_engine,
    mode,
    owner_slot,
    depth,
    same_kind,
):
    baseline, extended = _round11_pair(owner_slot, depth, same_kind)
    assert _binding_outcome(baseline) == _binding_outcome(extended)
    for request in [baseline, extended]:
        request["mode"] = mode
        result = _outputs(strict_engine, request)[0]
        assert int(result["n"]["value"]["value"]) == 1
        assert (
            bind_request_relations(request, {"program": request["program"]}) == request
        )


@pytest.mark.parametrize("mode", ["explain", "fast"])
def test_strict_engine_ignored_expression_metadata_cannot_make_binder_raise(
    strict_engine, mode
):
    request = _fixture("typed-relation-binding.json")
    request["mode"] = mode
    count = next(
        rule
        for rule in request["program"]["derived"]
        if rule["name"] == "qualifying_person_count"
    )
    for body in [count, *count["versions"]]:
        body["expr"]["metadata"] = {
            "kind": "count_related",
            "relation": "qualifying_person_of_tax_unit",
            "current_slot": 0,
            "related_slot": 1,
        }
    assert (
        int(
            _outputs(strict_engine, request)[0]["qualifying_person_count"]["value"][
                "value"
            ]
        )
        == 1
    )
    assert bind_request_relations(request, {"program": request["program"]}) == request


@pytest.mark.parametrize("member_slot", [0, 1])
def test_strict_engine_derivation_predicate_aggregates_on_related_id(
    strict_engine, member_slot
):
    request = _fixture("relation-member-nested-if.json")
    request["program"]["relations"][-1]["derivation"]["predicate"] = {
        "kind": "comparison",
        "left": {
            "kind": "count_related",
            "relation": "head",
            "current_slot": member_slot,
            "related_slot": 1 - member_slot,
        },
        "op": "gt",
        "right": _integer(0),
    }
    if member_slot == 0:
        assert int(_outputs(strict_engine, request)[0]["n"]["value"]["value"]) == 1
        assert (
            bind_request_relations(request, {"program": request["program"]}) == request
        )
    else:
        rejected = _run(strict_engine, request)
        assert rejected.returncode != 0
        assert "relation_current_slot_entity_mismatch" in rejected.stderr
        with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
            bind_request_relations(request, {"program": request["program"]})
