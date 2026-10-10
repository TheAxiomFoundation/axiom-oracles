from copy import deepcopy

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges.relation_binding import (
    RelationBindingError,
    bind_request_relations,
    relation_tuple,
)


def artifact_for(
    *,
    owner="TaxUnit",
    typed=True,
    current_slot=0,
    declared_owner_slot=0,
    kind="count_related",
):
    schema = {"name": "members", "arity": 2}
    if typed:
        schema["slot_entities"] = (
            [owner, "Person"] if declared_owner_slot == 0 else ["Person", owner]
        )
    artifact = {
        "program": {
            "relations": [schema],
            "derived": [
                {
                    "name": "member_count",
                    "entity": owner,
                    "expr": {
                        "kind": kind,
                        "relation": "members",
                        "current_slot": current_slot,
                        "related_slot": 1 - current_slot,
                    },
                }
            ],
        }
    }
    if kind == "relation_member":
        # Membership has executable slots only inside a derived relation's
        # predicate, where the evaluator binds an owner/member pair.
        artifact["program"]["derived"] = []
        artifact["program"]["relations"].extend([
            {"name": "source_members", "arity": 2},
            {
                "name": "filtered_members", "arity": 2,
                "derivation": {
                    "source_relation": "source_members",
                    "current_slot": 0, "related_slot": 1,
                    "slot_entities": [owner, "Person"],
                    "predicate": {
                        "kind": kind, "relation": "members",
                        "current_slot": current_slot, "related_slot": 1 - current_slot,
                    },
                },
            },
        ])
    return artifact


def tuple_for(artifact, name="members", **kwargs):
    return relation_tuple(
        artifact,
        name,
        owner_id="unit-1",
        owner_kind="TaxUnit",
        related_id="child-1",
        related_kind="Person",
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["count_related", "sum_related", "relation_member"])
@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("declared_owner_slot", [0, 1])
def test_executable_usage_takes_precedence_over_declared_order(
    kind, current_slot, declared_owner_slot
):
    artifact = artifact_for(
        kind=kind,
        current_slot=current_slot,
        declared_owner_slot=declared_owner_slot,
    )
    emitted = tuple_for(artifact)
    assert emitted[current_slot] == "unit-1"
    assert emitted[1 - current_slot] == "child-1"


def test_old_untyped_artifact_keeps_legacy_related_first_tuple():
    assert tuple_for(artifact_for(typed=False, current_slot=1)) == [
        "child-1",
        "unit-1",
    ]
    assert tuple_for(None) == ["child-1", "unit-1"]
    assert tuple_for(None, legacy_owner_slot=0) == ["unit-1", "child-1"]


@pytest.mark.parametrize("declared_owner_slot", [0, 1])
def test_only_unused_relations_use_declared_position_order(declared_owner_slot):
    artifact = artifact_for(declared_owner_slot=declared_owner_slot)
    artifact["program"]["derived"] = []
    assert tuple_for(artifact)[declared_owner_slot] == "unit-1"


def test_versions_replace_base_semantics_and_nested_nodes_are_read():
    artifact = artifact_for(current_slot=1)
    rule = artifact["program"]["derived"][0]
    active = deepcopy(rule["expr"])
    active.update(current_slot=0, related_slot=1)
    rule["versions"] = [
        {"effective_from": "2024-01-01", "expr": {"kind": "add", "items": [active]}}
    ]
    assert tuple_for(artifact) == ["unit-1", "child-1"]


def test_conflicting_executable_versions_fail_instead_of_using_declaration():
    artifact = artifact_for()
    rule = artifact["program"]["derived"][0]
    reversed_expr = dict(rule["expr"], current_slot=1, related_slot=0)
    rule["versions"] = [{"expr": rule["expr"]}, {"expr": reversed_expr}]
    with pytest.raises(RelationBindingError, match="Conflicting executable kinds"):
        tuple_for(artifact)


def test_nested_aggregate_uses_related_entity_context():
    artifact = artifact_for(owner="Household")
    program = artifact["program"]
    program["relations"].append(
        {"name": "parents", "arity": 2, "slot_entities": ["TaxUnit", "Person"]}
    )
    program["derived"][0]["expr"]["where"] = {
        "kind": "comparison",
        "left": {
            "kind": "count_related",
            "relation": "parents",
            "current_slot": 1,
            "related_slot": 0,
        },
    }
    assert tuple_for(artifact, "parents") == ["unit-1", "child-1"]


def test_sum_related_value_rule_supplies_related_kind():
    artifact = artifact_for(kind="sum_related")
    # An incomplete declaration cannot identify Person, but the sum's value can.
    artifact["program"]["relations"][0].pop("slot_entities")
    artifact["program"]["derived"][0]["expr"]["value"] = {
        "kind": "derived",
        "name": "earnings",
    }
    artifact["program"]["derived"].append(
        {"name": "earnings", "entity": "Person", "expr": {"kind": "input"}}
    )
    assert tuple_for(artifact) == ["unit-1", "child-1"]


def test_derived_relation_source_and_membership_follow_structural_context():
    artifact = artifact_for()
    program = artifact["program"]
    program["derived"] = []
    program["relations"].extend(
        [
            {"name": "eligible", "arity": 2, "slot_entities": ["TaxUnit", "Person"]},
            {
                "name": "filtered_members",
                "arity": 2,
                "slot_entities": ["Person", "TaxUnit"],
                "derivation": {
                    "source_relation": "members",
                    "current_slot": 1,
                    "related_slot": 0,
                    "slot_entities": ["Person", "TaxUnit"],
                    "predicate": {
                        "kind": "relation_member",
                        "relation": "eligible",
                        "current_slot": 1,
                        "related_slot": 0,
                    },
                },
            },
        ]
    )
    assert tuple_for(artifact) == ["child-1", "unit-1"]
    assert tuple_for(artifact, "eligible") == ["child-1", "unit-1"]


@pytest.mark.parametrize("wrapper", ["direct", "and", "or", "not", "scalar_if"])
def test_derivation_pair_context_survives_scalar_expression_boundaries(wrapper):
    artifact = artifact_for()
    program = artifact["program"]
    program["derived"] = []
    membership = {
        "kind": "relation_member",
        "relation": "eligible",
        "current_slot": 0,
        "related_slot": 1,
    }
    predicate = membership
    if wrapper in {"and", "or"}:
        predicate = {"kind": wrapper, "items": [membership]}
    elif wrapper == "not":
        predicate = {"kind": "not", "item": membership}
    elif wrapper == "scalar_if":
        one = {"kind": "literal", "value": {"kind": "integer", "value": 1}}
        zero = {"kind": "literal", "value": {"kind": "integer", "value": 0}}
        predicate = {
            "kind": "comparison",
            "left": {
                "kind": "if",
                "condition": membership,
                "then_expr": one,
                "else_expr": zero,
            },
            "op": "eq",
            "right": one,
        }
    program["relations"].extend(
        [
            {"name": "eligible", "arity": 2, "slot_entities": ["TaxUnit", "Person"]},
            {
                "name": "filtered_members",
                "arity": 2,
                "derivation": {
                    "source_relation": "members",
                    "current_slot": 1,
                    "related_slot": 0,
                    "slot_entities": ["Person", "TaxUnit"],
                    "predicate": predicate,
                },
            },
        ]
    )
    assert tuple_for(artifact, "eligible") == ["unit-1", "child-1"]


@pytest.mark.parametrize("typed", [True, False])
def test_input_scopes_are_not_unique_endpoint_identities(typed):
    artifact = artifact_for(typed=typed, current_slot=1)
    request = request_for(["child-1"])
    request["dataset"]["inputs"].extend([
        {"entity_id": entity_id, "entity": "StatutoryDollarAmount"}
        for entity_id in ("unit-1", "child-1")
    ])
    before = deepcopy(request)
    assert bind_request_relations(request, artifact) == before
    assert request == before


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("supplied_owner_slot", [0, 1])
def test_typed_count_only_uses_known_owner_without_member_inputs(
    current_slot, supplied_owner_slot
):
    request = request_for(["child-1"])
    request["dataset"]["inputs"].pop()
    if supplied_owner_slot == 0:
        request["dataset"]["relations"][0]["tuple"].reverse()
    original = deepcopy(request)
    artifact = artifact_for(current_slot=current_slot)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"][current_slot] == "unit-1"
    assert bound["dataset"]["relations"][0]["tuple"][1 - current_slot] == "child-1"
    assert bound["dataset"]["inputs"] == original["dataset"]["inputs"]
    assert bind_request_relations(bound, artifact) == bound
    assert request == original


def test_canonical_relation_name_resolves_to_unique_artifact_symbol():
    assert tuple_for(artifact_for(), "us:statutes/26/21#relation.members") == [
        "unit-1",
        "child-1",
    ]


def test_ambiguous_short_relation_name_is_rejected():
    artifact = artifact_for()
    schema = artifact["program"]["relations"][0]
    schema["name"] = "us:statutes/26/21#relation.members"
    artifact["program"]["relations"].append(
        dict(schema, name="us:statutes/26/24#relation.members")
    )
    with pytest.raises(RelationBindingError, match="Ambiguous artifact relation"):
        tuple_for(artifact)


def request_for(member_ids, owner="TaxUnit"):
    return {
        "dataset": {
            "inputs": [
                {"entity_id": "unit-1", "entity": owner},
                *({"entity_id": member, "entity": "Person"} for member in member_ids),
            ],
            "relations": [
                {
                    "name": "members",
                    "tuple": [member, "unit-1"],
                    "interval": {"start": "2024-01-01", "end": "2025-01-01"},
                }
                for member in member_ids
            ],
        },
        "targets": [{"entity_id": "unit-1", "rule": "member_count"}],
    }


def test_binding_returns_independent_copy_without_lenient_opt_out():
    request = request_for(["child-1"])
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact_for())
    assert request == before
    assert bound["dataset"]["relations"][0]["tuple"] == ["unit-1", "child-1"]
    assert "relation_binding" not in bound
    bound["dataset"]["inputs"][0]["entity"] = "changed"
    assert request == before


@pytest.mark.parametrize("invalid_kind", ["Entity", "Household"])
def test_incorrect_input_label_is_not_silently_accepted(invalid_kind):
    request = request_for(["child-1"])
    request["dataset"]["inputs"][0]["entity"] = invalid_kind
    with pytest.raises(RelationBindingError, match="Cannot unambiguously order"):
        bind_request_relations(request, artifact_for())


@pytest.mark.parametrize("typed", [True, False])
def test_conflicting_endpoint_identity_kinds_fail(typed):
    request = request_for(["child-1"])
    request["dataset"]["inputs"].append(
        {"entity_id": "child-1", "entity": "TaxUnit"}
    )
    with pytest.raises(RelationBindingError, match="needs one input entity kind"):
        bind_request_relations(request, artifact_for(typed=typed))


@pytest.mark.parametrize("typed", [True, False])
def test_equal_kind_slots_keep_existing_order(typed):
    artifact = artifact_for(owner="Person", typed=typed, current_slot=1)
    assert relation_tuple(
        artifact,
        "members",
        owner_id="parent",
        owner_kind="Person",
        related_id="child",
        related_kind="Person",
    ) == ["child", "parent"]


def test_unrelated_higher_arity_relation_does_not_block_two_slot_binding():
    artifact = artifact_for()
    artifact["program"]["relations"].append(
        {"name": "other", "arity": 3, "slot_entities": ["Person", "Other", "TaxUnit"]}
    )
    artifact["program"]["derived"].append(
        {
            "name": "other_count",
            "entity": "TaxUnit",
            "expr": {
                "kind": "count_related",
                "relation": "other",
                "current_slot": 2,
                "related_slot": 0,
            },
        }
    )
    assert tuple_for(artifact) == ["unit-1", "child-1"]


def test_untyped_artifact_with_explicit_owner_first_usage_is_honored():
    request = request_for(["child-1"])
    bound = bind_request_relations(request, artifact_for(typed=False, current_slot=0))
    assert bound["dataset"]["relations"][0]["tuple"] == ["unit-1", "child-1"]


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("supplied_owner_slot", [0, 1])
def test_untyped_member_without_inputs_preserves_undetermined_tuple(
    current_slot, supplied_owner_slot
):
    request = request_for(["child-1"])
    request["dataset"]["inputs"].pop()
    if supplied_owner_slot == 0:
        request["dataset"]["relations"][0]["tuple"].reverse()
    before = deepcopy(request)
    with pytest.warns(UserWarning, match="members.*child-1"):
        bound = bind_request_relations(
            request, artifact_for(typed=False, current_slot=current_slot)
        )
    assert bound == before
    assert request == before


@pytest.mark.parametrize("current_slot", [0, 1])
def test_untyped_unlabelled_ids_preserve_existing_tuple(current_slot):
    request = request_for(["child-1"])
    request["dataset"]["inputs"] = []
    assert bind_request_relations(
        request, artifact_for(typed=False, current_slot=current_slot)
    ) == request


def test_untyped_conflicting_input_kinds_still_fail():
    request = request_for(["child-1"])
    request["dataset"]["inputs"].append(
        {"entity_id": "unit-1", "entity": "Household"}
    )
    artifact = artifact_for(typed=False, current_slot=1)
    # Household is a true identity kind here because another relation binds
    # it as an endpoint, rather than an unrelated broadcast input scope.
    artifact["program"]["relations"].append({
        "name": "household_members", "arity": 2,
        "slot_entities": ["Household", "Person"],
    })
    with pytest.raises(RelationBindingError, match="needs one input entity kind"):
        bind_request_relations(request, artifact)


def test_unknown_nested_scope_does_not_borrow_derived_relation_structural_kind():
    artifact = artifact_for(typed=False, current_slot=1)
    program = artifact["program"]
    program["relations"].extend(
        [
            {"name": "source_members", "arity": 2},
            {
                "name": "filtered_members",
                "arity": 2,
                "derivation": {
                    "source_relation": "source_members",
                    "current_slot": 1,
                    "related_slot": 0,
                    "slot_entities": ["Person", "TaxUnit"],
                    "predicate": {"kind": "derived", "name": "eligible"},
                },
            },
        ]
    )
    program["derived"][0]["expr"]["where"] = {
        "kind": "comparison",
        "left": {
            "kind": "count_related",
            "relation": "filtered_members",
            "current_slot": 1,
            "related_slot": 0,
        },
    }
    # The outer untyped count has no evidence identifying its member kind.
    # A derived relation's structural kinds describe its source context; an
    # absent derivation.entity must not match that unknown enclosing scope.
    request = request_for(["child-1"])
    request["dataset"]["relations"] = [
        {"name": "filtered_members", "tuple": ["unit-1", "child-1"]}
    ]
    assert bind_request_relations(request, artifact) == request


def test_request_binding_leaves_higher_arity_records_untouched():
    artifact = artifact_for()
    artifact["program"]["relations"].append(
        {"name": "triplet", "arity": 3, "slot_entities": ["Person", "Person", "TaxUnit"]}
    )
    request = request_for(["child-1"])
    triplet = {"name": "triplet", "tuple": ["unknown-1", "unknown-2", "unknown-3"]}
    request["dataset"]["relations"].append(triplet)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"] == ["unit-1", "child-1"]
    assert bound["dataset"]["relations"][1] == triplet
    with pytest.raises(RelationBindingError, match="not a two-slot relation"):
        tuple_for(artifact, "triplet")


@settings(deadline=None)
@given(
    owner=st.sampled_from(["Household", "TaxUnit"]),
    member_numbers=st.lists(st.integers(min_value=0), unique=True, max_size=30),
    typed=st.booleans(),
    declared_owner_slot=st.integers(min_value=0, max_value=1),
    executable_owner_slot=st.integers(min_value=0, max_value=1),
    used=st.booleans(),
    kind=st.sampled_from(["count_related", "sum_related", "relation_member"]),
)
def test_every_generated_member_occupies_its_expected_kind_slot(
    owner,
    member_numbers,
    typed,
    declared_owner_slot,
    executable_owner_slot,
    used,
    kind,
):
    # Old released artifacts have related-first executable slots. Typed ones
    # may retain either orientation, independently of their declaration order.
    current = executable_owner_slot if typed else 1
    artifact = artifact_for(
        owner=owner,
        typed=typed,
        current_slot=current,
        declared_owner_slot=declared_owner_slot,
        kind=kind,
    )
    if not used:
        artifact["program"]["derived"] = []
        artifact["program"]["relations"] = artifact["program"]["relations"][:1]
    member_ids = [f"member-{number}" for number in member_numbers]
    legacy = request_for(member_ids, owner)
    bound = bind_request_relations(legacy, artifact)
    labels = {
        record["entity_id"]: record["entity"]
        for record in bound["dataset"]["inputs"]
    }
    expected_owner_slot = (current if used else declared_owner_slot) if typed else 1
    expected_kinds = (
        [owner, "Person"] if expected_owner_slot == 0 else ["Person", owner]
    )
    for member, record in zip(member_ids, bound["dataset"]["relations"], strict=True):
        emitted = relation_tuple(
            artifact,
            "members",
            owner_id="unit-1",
            owner_kind=owner,
            related_id=member,
            related_kind="Person",
        )
        assert emitted == record["tuple"]
        assert [labels[entity_id] for entity_id in emitted] == expected_kinds
        assert emitted[expected_owner_slot] == "unit-1"
    if not typed:
        assert bound == legacy


@settings(deadline=None)
@given(
    entity_kinds=st.sampled_from(
        [
            ("TaxUnit", "Person"),
            ("Household", "Person"),
            ("Person", "Payment"),
            ("Organization", "Payment"),
        ]
    ),
    owner_slot=st.integers(min_value=0, max_value=1),
    supplied_owner_slot=st.integers(min_value=0, max_value=1),
    member_numbers=st.lists(
        st.integers(min_value=0), unique=True, min_size=1, max_size=20
    ),
    used=st.booleans(),
)
def test_swapping_declared_and_used_slots_reverses_every_generated_tuple(
    entity_kinds, owner_slot, supplied_owner_slot, member_numbers, used
):
    owner_kind, member_kind = entity_kinds
    member_ids = [f"member-{number}" for number in member_numbers]
    request = request_for(member_ids, owner_kind)
    for record in request["dataset"]["inputs"][1:]:
        record["entity"] = member_kind
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    original = deepcopy(request)

    def artifact_at(slot):
        artifact = artifact_for(
            owner=owner_kind, current_slot=slot, declared_owner_slot=slot
        )
        artifact["program"]["relations"][0]["slot_entities"][1 - slot] = (
            member_kind
        )
        if not used:
            artifact["program"]["derived"] = []
        return artifact

    artifact = artifact_at(owner_slot)
    swapped_artifact = artifact_at(1 - owner_slot)
    bound = bind_request_relations(request, artifact)
    swapped = bind_request_relations(request, swapped_artifact)
    assert bind_request_relations(bound, artifact) == bound
    assert bind_request_relations(swapped, swapped_artifact) == swapped
    assert bound["dataset"]["inputs"] == original["dataset"]["inputs"]
    assert bound["targets"] == original["targets"]
    assert swapped["dataset"]["inputs"] == original["dataset"]["inputs"]
    assert swapped["targets"] == original["targets"]
    for member, before, emitted, reversed_record in zip(
        member_ids,
        original["dataset"]["relations"],
        bound["dataset"]["relations"],
        swapped["dataset"]["relations"],
        strict=True,
    ):
        assert emitted["tuple"] == relation_tuple(
            artifact,
            "members",
            owner_id="unit-1",
            owner_kind=owner_kind,
            related_id=member,
            related_kind=member_kind,
        )
        assert emitted["tuple"][owner_slot] == "unit-1"
        assert emitted["tuple"][1 - owner_slot] == member
        assert reversed_record["tuple"] == emitted["tuple"][::-1]
        assert sorted(emitted["tuple"]) == sorted(before["tuple"])
        assert {key: value for key, value in emitted.items() if key != "tuple"} == {
            key: value for key, value in before.items() if key != "tuple"
        }
        assert {
            key: value for key, value in reversed_record.items() if key != "tuple"
        } == {key: value for key, value in before.items() if key != "tuple"}
    assert request == original


@settings(deadline=None)
@given(
    member_numbers=st.lists(st.integers(0, 20), min_size=1, max_size=20),
    owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1),
    pseudo_inputs=st.booleans(), pseudo_predicate=st.booleans(),
    value=st.one_of(st.booleans(), st.integers(), st.text()),
)
def test_untyped_unresolved_scopes_preserve_entire_request(
    member_numbers, owner_slot, supplied_owner_slot, pseudo_inputs,
    pseudo_predicate, value
):
    # Repeated ids deliberately exercise tuple multiplicity.
    request = request_for([f"member-{number}" for number in member_numbers])
    if pseudo_inputs:
        request["dataset"]["inputs"] = [
            {"entity_id": record["entity_id"], "entity": "StatutoryDollarAmount"}
            for record in request["dataset"]["inputs"]
        ]
    else:
        request["dataset"]["inputs"] = []
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    for record in request["dataset"]["inputs"]:
        record["name"] = "value"
        record["value"] = value
    request["queries"] = [{"entity_id": "unit-1", "outputs": ["count"], "period": "2026"}]
    before = deepcopy(request)
    artifact = artifact_for(typed=False, current_slot=owner_slot)
    if pseudo_predicate:
        artifact["program"]["derived"][0]["expr"]["where"] = {
            "kind": "comparison", "op": "gt",
            "left": {"kind": "derived", "name": "amount"},
            "right": {"kind": "literal", "value": {"kind": "decimal", "value": "0"}},
        }
        artifact["program"]["derived"].append({
            "name": "amount", "entity": "StatutoryDollarAmount",
            "expr": {"kind": "input", "name": "amount"},
        })
    bound = bind_request_relations(request, artifact)
    assert bound == before
    assert bind_request_relations(bound, artifact) == bound
    assert request == before


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("supplied_owner_slot", [0, 1])
def test_untyped_custom_owner_preserves_scalar_only_member(owner_slot, supplied_owner_slot):
    artifact = artifact_for(owner="Organization", typed=False, current_slot=owner_slot)
    artifact["program"]["derived"][0]["expr"]["where"] = {
        "kind": "derived", "name": "payment_amount",
    }
    artifact["program"]["derived"].append({
        "name": "payment_amount", "entity": "Payment",
        "expr": {"kind": "input", "name": "amount"},
    })
    request = request_for(["payment-1"], "Organization")
    request["dataset"]["inputs"][1]["entity"] = "Payment"
    if supplied_owner_slot == 0:
        request["dataset"]["relations"][0]["tuple"].reverse()
    before = deepcopy(request)
    with pytest.warns(UserWarning, match="members.*payment-1"):
        bound = bind_request_relations(request, artifact)
    assert bound == before
    assert request == before


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("supplied_owner_slot", [0, 1])
def test_untyped_custom_owner_repairs_distinct_real_identities(owner_slot, supplied_owner_slot):
    artifact = artifact_for(owner="Organization", typed=False, current_slot=owner_slot)
    # A separate executable endpoint proves Payment is an identity, rather
    # than a scalar broadcast scope inferred from a helper's entity name.
    artifact["program"]["relations"].append({"name": "payment_proof", "arity": 2})
    artifact["program"]["derived"].append({
        "name": "payment_count", "entity": "Payment",
        "expr": {"kind": "count_related", "relation": "payment_proof",
                 "current_slot": 0, "related_slot": 1},
    })
    request = request_for(["payment-1"], "Organization")
    request["dataset"]["inputs"][1]["entity"] = "Payment"
    if supplied_owner_slot == 0:
        request["dataset"]["relations"][0]["tuple"].reverse()
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"][owner_slot] == "unit-1"
    assert bind_request_relations(bound, artifact) == bound
    assert request == before


OWNER_KINDS = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", min_size=1, max_size=24
).filter(lambda kind: kind not in {"Person", "StatutoryDollarAmount", "BroadcastThreshold"})


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("supplied_owner_slot", [0, 1])
def test_typed_count_only_ignores_known_scalar_member_scope(
    owner_slot, supplied_owner_slot,
):
    artifact = artifact_for(current_slot=owner_slot)
    artifact["program"]["derived"].append({
        "name": "threshold", "entity": "BroadcastThreshold",
        "expr": {"kind": "input", "name": "threshold"},
    })
    request = request_for(["child-1"])
    request["dataset"]["inputs"][1]["entity"] = "BroadcastThreshold"
    if supplied_owner_slot == 0:
        request["dataset"]["relations"][0]["tuple"].reverse()
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"][owner_slot] == "unit-1"
    assert request == before
    if owner_slot == supplied_owner_slot:
        assert bound == before


@settings(deadline=None)
@example(
    owner="Household", typed=False, member_numbers=[0, 0], owner_slot=1,
    supplied_owner_slot=0, owner_pseudo=True, member_pseudo=True,
    member_inputs=True, value=17,
)
@given(
    owner=OWNER_KINDS, typed=st.booleans(),
    member_numbers=st.lists(st.integers(0, 20), min_size=1, max_size=20),
    owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1),
    owner_pseudo=st.booleans(), member_pseudo=st.booleans(), member_inputs=st.booleans(),
    value=st.one_of(st.booleans(), st.integers(), st.text()),
)
def test_real_identity_evidence_orders_tuples_through_broadcast_scopes(
    owner, typed, member_numbers, owner_slot, supplied_owner_slot,
    owner_pseudo, member_pseudo, member_inputs, value,
):
    # Executable owner context proves arbitrary kinds independently of naming.
    # Broadcast scopes add no identity evidence. Untyped counts without
    # member identities remain ambiguous. Repeated ids retain multiplicity.
    member_ids = [f"member-{number}" for number in member_numbers]
    request = request_for(member_ids, owner)
    if not member_inputs:
        request["dataset"]["inputs"] = request["dataset"]["inputs"][:1]
    if owner_pseudo:
        request["dataset"]["inputs"].append({
            "entity_id": "unit-1", "entity": "StatutoryDollarAmount",
        })
    if member_pseudo:
        request["dataset"]["inputs"].extend([
            {"entity_id": member, "entity": "BroadcastThreshold"} for member in member_ids
        ])
    for record in request["dataset"]["inputs"]:
        record.update(name="value", value=value)
    request["queries"] = [{"entity_id": "unit-1", "outputs": ["count"], "period": "2026"}]
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    artifact = artifact_for(owner=owner, typed=typed, current_slot=owner_slot)
    artifact["program"]["derived"].extend([
        {"name": "amount", "entity": "StatutoryDollarAmount", "expr": {"kind": "input"}},
        {"name": "threshold", "entity": "BroadcastThreshold", "expr": {"kind": "input"}},
    ])
    if member_inputs:
        artifact["program"]["derived"][0]["expr"]["where"] = {
            "kind": "derived", "name": "person_value",
        }
        artifact["program"]["derived"].append({
            "name": "person_value", "entity": "Person", "expr": {"kind": "input"},
        })
    expected = deepcopy(request)
    if typed or member_inputs:
        for record, member in zip(expected["dataset"]["relations"], member_ids, strict=True):
            record["tuple"] = ["unit-1", member] if owner_slot == 0 else [member, "unit-1"]
    bound = bind_request_relations(request, artifact)
    assert bound == expected  # Only order changes: values, intervals, queries all survive.
    assert bind_request_relations(bound, artifact) == bound
    assert request == before
    if supplied_owner_slot == owner_slot:
        assert bound == before


@settings(deadline=None)
@example(
    owner="Organization", owner_slot=0, supplied_owner_slot=1,
    proof_first=False, pattern_metadata=False, owner_identity=False,
)
@given(
    owner=OWNER_KINDS.filter(lambda kind: kind != "Household"),
    owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1),
    proof_first=st.booleans(), pattern_metadata=st.booleans(), owner_identity=st.booleans(),
)
def test_proved_custom_owner_context_is_available_to_nested_aggregates(
    owner, owner_slot, supplied_owner_slot, proof_first, pattern_metadata, owner_identity,
):
    artifact = artifact_for(owner="Household", typed=False, current_slot=0)
    program = artifact["program"]
    program["relations"].extend([
        {"name": "payments", "arity": 2}, {"name": "owner_proof", "arity": 2},
    ])
    zero = {"kind": "literal", "value": {"kind": "integer", "value": 0}}
    program["derived"][0]["expr"]["where"] = {
        "kind": "and", "items": [
            {"kind": "comparison", "op": "gt", "right": zero,
             "left": {"kind": "derived", "name": "owner_label"}},
            {"kind": "comparison", "op": "gt", "right": zero, "left": {
                "kind": "count_related", "relation": "payments",
                "current_slot": owner_slot, "related_slot": 1 - owner_slot,
            }},
        ],
    }
    program["derived"].append({
        "name": "owner_label", "entity": owner, "expr": {"kind": "input"},
    })
    proof = {
        "name": "owner_count", "entity": owner,
        "expr": {"kind": "count_related", "relation": "owner_proof",
                 "current_slot": 0, "related_slot": 1},
    }
    program["derived"].insert(0 if proof_first else len(program["derived"]), proof)
    if pattern_metadata:
        comparison = program["derived"][0 if not proof_first else 1]["expr"]["where"]["items"][0]
        reference = comparison["left"]
        comparison["left"] = {
            "kind": "if", "condition": {
                "kind": "comparison", "op": "eq", "left": zero, "right": zero,
            },
            "then_expr": reference, "else_expr": {
                "kind": "no_match", "subject": deepcopy(reference),
                "patterns": [{"kind": "derived", "name": "person_metadata"}],
            },
        }
        program["derived"].append({
            "name": "person_metadata", "entity": "Person", "expr": {"kind": "input"},
        })
    request = request_for(["owner-1"], "Household")
    request["dataset"]["inputs"][1]["entity"] = owner
    request["dataset"]["inputs"].append({"entity_id": "payment-1", "entity": "Person"})
    if not owner_identity:
        # Without the outer member's identity the nested owner context is
        # unknown. A scalar scope cannot establish that missing identity.
        request["dataset"]["inputs"][1]["entity"] = "StatutoryDollarAmount"
    request["dataset"]["relations"][0]["tuple"].reverse()
    request["dataset"]["relations"].append({
        "name": "payments",
        "tuple": ["owner-1", "payment-1"] if supplied_owner_slot == 0
        else ["payment-1", "owner-1"],
    })
    before = deepcopy(request)
    expected = deepcopy(request)
    if owner_identity:
        expected["dataset"]["relations"][1]["tuple"] = (
            ["owner-1", "payment-1"] if owner_slot == 0 else ["payment-1", "owner-1"]
        )
    bound = bind_request_relations(request, artifact)
    assert bound == expected
    assert bind_request_relations(bound, artifact) == bound
    assert request == before


@settings(deadline=None)
@given(owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1))
def test_no_match_pattern_metadata_supplies_no_executable_slots(
    owner_slot, supplied_owner_slot,
):
    artifact = artifact_for(current_slot=owner_slot)
    rule = artifact["program"]["derived"][0]
    executable = rule["expr"]
    one = {"kind": "literal", "value": {"kind": "integer", "value": 1}}
    rule["expr"] = {
        "kind": "if", "condition": {
            "kind": "comparison", "op": "eq", "left": one, "right": one,
        },
        "then_expr": executable,
        "else_expr": {
            "kind": "no_match", "subject": one,
            "patterns": [dict(executable, current_slot=1 - owner_slot, related_slot=owner_slot)],
        },
    }
    request = request_for(["child-1"])
    if supplied_owner_slot == 0:
        request["dataset"]["relations"][0]["tuple"].reverse()
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"][owner_slot] == "unit-1"
    assert bind_request_relations(bound, artifact) == bound
    assert request == before
    if owner_slot == supplied_owner_slot:
        assert bound == before


@settings(deadline=None)
@given(
    owner=OWNER_KINDS, typed=st.booleans(), evidence=st.integers(0, 3),
    owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1),
    pseudo=st.booleans(), contradictory=st.booleans(),
)
def test_generated_binding_invariant(
    owner, typed, evidence, owner_slot, supplied_owner_slot, pseudo, contradictory,
):
    artifact = artifact_for(owner=owner, typed=typed, current_slot=owner_slot)
    artifact["program"]["derived"].append({
        "name": "threshold", "entity": "BroadcastThreshold",
        "expr": {"kind": "input"},
    })
    request = request_for(["member-1", "member-1"], owner)
    request["dataset"]["inputs"] = [
        record for record in request["dataset"]["inputs"]
        if (record["entity_id"] == "unit-1" and evidence & 1)
        or (record["entity_id"] == "member-1" and evidence & 2)
    ]
    if pseudo:
        request["dataset"]["inputs"].extend([
            {"entity_id": entity_id, "entity": "BroadcastThreshold"}
            for entity_id in ("unit-1", "member-1")
        ])
    if contradictory:
        request["dataset"]["inputs"].extend([
            {"entity_id": "unit-1", "entity": owner},
            {"entity_id": "unit-1", "entity": "Person"},
        ])
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    if contradictory:
        with pytest.raises(RelationBindingError, match="needs one input entity kind"):
            bind_request_relations(request, artifact)
    else:
        expected = deepcopy(request)
        if evidence & 2 or (typed and evidence & 1):
            for record in expected["dataset"]["relations"]:
                record["tuple"] = (
                    ["unit-1", "member-1"] if owner_slot == 0 else ["member-1", "unit-1"]
                )
        bound = bind_request_relations(request, artifact)
        assert bound == expected
        assert bind_request_relations(bound, artifact) == bound
    assert request == before


@settings(deadline=None)
@given(
    member_numbers=st.lists(st.integers(0, 20), min_size=1, max_size=20),
    owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1),
    value=st.one_of(st.booleans(), st.integers(), st.text()),
)
def test_typed_count_only_preserves_everything_except_tuple_order(
    member_numbers, owner_slot, supplied_owner_slot, value
):
    request = request_for([f"member-{number}" for number in member_numbers])
    request["dataset"]["inputs"] = [request["dataset"]["inputs"][0]]
    request["dataset"]["inputs"][0]["value"] = value
    request["queries"] = [{"entity_id": "unit-1", "outputs": ["count"], "period": "2026"}]
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    artifact = artifact_for(current_slot=owner_slot)
    bound = bind_request_relations(request, artifact)
    assert bind_request_relations(bound, artifact) == bound
    assert len(bound["dataset"]["relations"]) == len(before["dataset"]["relations"])
    restored = deepcopy(bound)
    for old, corrected, record in zip(
        before["dataset"]["relations"], bound["dataset"]["relations"],
        restored["dataset"]["relations"], strict=True,
    ):
        assert corrected["tuple"][owner_slot] == "unit-1"
        assert sorted(corrected["tuple"]) == sorted(old["tuple"])
        record["tuple"] = old["tuple"]
    assert restored == before
    assert request == before


@settings(deadline=None)
@given(
    owner=OWNER_KINDS, typed=st.booleans(), owner_slot=st.integers(0, 1),
    supplied_owner_slot=st.integers(0, 1), alias_depth=st.integers(0, 3),
    versions=st.booleans(), optional_default=st.booleans(),
)
@example(
    owner="Household", typed=False, owner_slot=0, supplied_owner_slot=0,
    alias_depth=0, versions=False, optional_default=False,
)
@example(
    owner="Household", typed=False, owner_slot=0, supplied_owner_slot=0,
    alias_depth=1, versions=True, optional_default=True,
)
def test_broadcast_constants_and_defaults_do_not_identify_members(
    owner, typed, owner_slot, supplied_owner_slot, alias_depth, versions, optional_default,
):
    artifact = artifact_for(owner=owner, typed=typed, current_slot=owner_slot)
    one = {"kind": "literal", "value": {"kind": "integer", "value": 1}}
    body = {"kind": "input_or_else", "name": "optional_threshold", "default": one["value"]} \
        if optional_default else one
    for index in range(alias_depth + 1):
        name = f"threshold_{index}"
        rule = {"name": name, "entity": owner, "expr": deepcopy(body)}
        if versions:
            rule["versions"] = [{"effective_from": "2026-01-01", "expr": deepcopy(body)}]
            rule["expr"] = {"kind": "input", "name": "ignored_base"}
        artifact["program"]["derived"].append(rule)
        body = {"kind": "derived", "name": name}
    artifact["program"]["derived"][0]["expr"]["where"] = {
        "kind": "comparison", "left": body, "op": "gt", "right": one,
    }
    request = request_for(["member-1", "member-1"], owner)
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    expected = deepcopy(request)
    for record in expected["dataset"]["relations"]:
        record["tuple"] = ["unit-1", "member-1"] if owner_slot == 0 else ["member-1", "unit-1"]
    bound = bind_request_relations(request, artifact)
    assert bound == expected
    assert bind_request_relations(bound, artifact) == bound
    assert request == before
    if owner_slot == supplied_owner_slot:
        assert bound == before


@settings(deadline=None)
@given(
    owner=st.one_of(st.just("Person"), OWNER_KINDS), typed=st.booleans(),
    owner_slot=st.integers(0, 1), supplied_owner_slot=st.integers(0, 1), predicate=st.booleans(),
    owner_pseudo=st.booleans(), member_pseudo=st.booleans(),
)
@example(
    owner="Person", typed=False, owner_slot=0, supplied_owner_slot=1,
    predicate=True, owner_pseudo=True, member_pseudo=True,
)
def test_equal_endpoint_identities_preserve_supplied_tuple(
    owner, typed, owner_slot, supplied_owner_slot, predicate, owner_pseudo, member_pseudo,
):
    artifact = artifact_for(owner=owner, typed=typed, current_slot=owner_slot)
    if typed:
        artifact["program"]["relations"][0]["slot_entities"] = [owner, owner]
    if predicate:
        artifact["program"]["derived"][0]["expr"]["where"] = {
            "kind": "comparison", "op": "gt",
            "left": {"kind": "derived", "name": "member_value"},
            "right": {"kind": "literal", "value": {"kind": "integer", "value": 0}},
        }
        artifact["program"]["derived"].append({
            "name": "member_value", "entity": owner, "expr": {"kind": "input"},
        })
    artifact["program"]["derived"].append({
        "name": "broadcast", "entity": "BroadcastThreshold", "expr": {"kind": "input"},
    })
    request = request_for(["member-1", "member-1"], owner)
    for record in request["dataset"]["inputs"]:
        if record["entity_id"] == "member-1":
            record["entity"] = owner
    for enabled, entity_id in [(owner_pseudo, "unit-1"), (member_pseudo, "member-1")]:
        if enabled:
            request["dataset"]["inputs"].append({
                "entity_id": entity_id, "entity": "BroadcastThreshold",
            })
    if supplied_owner_slot == 0:
        for record in request["dataset"]["relations"]:
            record["tuple"].reverse()
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact)
    assert bound == before
    assert bind_request_relations(bound, artifact) == bound
    assert request == before


@settings(deadline=None)
@given(
    owner=OWNER_KINDS, typed=st.booleans(), outer_slot=st.integers(0, 1),
    nested_slot=st.integers(0, 1), supplied_nested_slot=st.integers(0, 1),
    optional_default=st.booleans(),
)
@example(
    owner="Household", typed=False, outer_slot=0, nested_slot=0,
    supplied_nested_slot=1, optional_default=False,
)
def test_same_kind_member_identity_scopes_nested_broadcast_predicates(
    owner, typed, outer_slot, nested_slot, supplied_nested_slot, optional_default,
):
    artifact = artifact_for(owner=owner, typed=typed, current_slot=outer_slot)
    program = artifact["program"]
    if typed:
        program["relations"][0]["slot_entities"] = [owner, owner]
    payments = {"name": "payments", "arity": 2}
    if typed:
        payments["slot_entities"] = ["Person", owner]
    program["relations"].append(payments)
    one = {"kind": "literal", "value": {"kind": "integer", "value": 1}}
    zero = {"kind": "literal", "value": {"kind": "integer", "value": 0}}
    program["derived"].append({
        "name": "threshold", "entity": owner, "expr": {
            "kind": "input_or_else", "name": "optional_threshold", "default": one["value"],
        } if optional_default else one,
    })
    program["derived"][0]["expr"]["where"] = {
        "kind": "and", "items": [{
            "kind": "comparison", "op": "gt", "right": zero,
            "left": {"kind": "derived", "name": "threshold"},
        }, {
            "kind": "comparison", "op": "gt", "right": zero,
            "left": {"kind": "count_related", "relation": "payments",
                     "current_slot": nested_slot, "related_slot": 1 - nested_slot},
        }],
    }
    request = request_for(["member-1"], owner)
    request["dataset"]["inputs"][1]["entity"] = owner
    request["dataset"]["inputs"].append({"entity_id": "payment-1", "entity": "Person"})
    request["dataset"]["relations"][0]["tuple"] = (
        ["unit-1", "member-1"] if outer_slot == 0 else ["member-1", "unit-1"]
    )
    request["dataset"]["relations"].append({
        "name": "payments", "tuple": ["member-1", "payment-1"]
        if supplied_nested_slot == 0 else ["payment-1", "member-1"],
    })
    before = deepcopy(request)
    expected = deepcopy(request)
    expected["dataset"]["relations"][1]["tuple"] = (
        ["member-1", "payment-1"] if nested_slot == 0 else ["payment-1", "member-1"]
    )
    bound = bind_request_relations(request, artifact)
    assert bound == expected
    assert bind_request_relations(bound, artifact) == bound
    assert request == before
    constructed = relation_tuple(
        artifact, "payments", owner_id="member-1", owner_kind=owner,
        related_id="payment-1", related_kind="Person",
    )
    assert constructed == expected["dataset"]["relations"][1]["tuple"]
