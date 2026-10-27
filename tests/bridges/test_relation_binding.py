"""The binder follows engine declarations and uses only wire identity evidence."""

from copy import deepcopy
import warnings

import pytest

from axiom_oracles.bridges.relation_binding import (
    RelationBindingAmbiguityWarning,
    RelationBindingError,
    _effective_slot_entities,
    _executed_relations,
    _filtered_entity_kinds,
    bind_request_relations,
    relation_owner_kind,
    relation_tuple,
)


def artifact_for(*, typed=True, owner_slot=0, owner="TaxUnit", related="Person"):
    kinds = [owner, related] if owner_slot == 0 else [related, owner]
    return {
        "program": {
            "relations": [
                {
                    "name": "members",
                    "arity": 2,
                    **({"slot_entities": kinds} if typed else {}),
                }
            ],
            "derived": [
                {
                    "name": "member_count",
                    "entity": owner,
                    "expr": {
                        "kind": "count_related",
                        "relation": "members",
                        "current_slot": owner_slot,
                        "related_slot": 1 - owner_slot,
                    },
                }
            ],
        }
    }


def request_for(*, owner="TaxUnit", supplied_slot=1, labels=True):
    return {
        "dataset": {
            "inputs": (
                [
                    {"entity_id": "unit", "entity": owner},
                    {"entity_id": "child", "entity": "Person"},
                ]
                if labels
                else []
            ),
            "relations": [
                {
                    "name": "members",
                    "tuple": ["unit", "child"]
                    if supplied_slot == 0
                    else ["child", "unit"],
                    "interval": {"start": "2026-01-01", "end": "2026-12-31"},
                }
            ],
        },
        "queries": [{"entity_id": "unit", "outputs": ["member_count"]}],
    }


def tuple_for(artifact, **kwargs):
    return relation_tuple(
        artifact,
        "members",
        owner_id="unit",
        owner_kind="TaxUnit",
        related_id="child",
        related_kind="Person",
        **kwargs,
    )


def derivation(source, *, kinds=None, entity=None, slot=0):
    result = {
        "source_relation": source,
        "current_slot": slot,
        "related_slot": 1 - slot,
        "predicate": {
            "kind": "comparison",
            "left": {"kind": "literal", "value": {"kind": "integer", "value": 1}},
            "op": "eq",
            "right": {"kind": "literal", "value": {"kind": "integer", "value": 1}},
        },
    }
    if kinds is not None:
        result["slot_entities"] = kinds
    if entity is not None:
        result["entity"] = entity
    return result


@pytest.mark.parametrize("owner_slot", [0, 1])
@pytest.mark.parametrize("supplied_slot", [0, 1])
def test_declared_order_binds_raw_tuples_and_explicit_roles(owner_slot, supplied_slot):
    artifact = artifact_for(owner_slot=owner_slot)
    request = request_for(supplied_slot=supplied_slot)
    original, artifact_before = deepcopy(request), deepcopy(artifact)
    bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"][owner_slot] == "unit"
    assert tuple_for(artifact)[owner_slot] == "unit"
    assert bind_request_relations(bound, artifact) == bound
    assert request == original
    assert artifact == artifact_before
    bound["dataset"]["inputs"][0]["entity"] = "changed"
    assert request == original
    assert "relation_binding" not in bound


@pytest.mark.parametrize("kind", ["count_related", "sum_related"])
@pytest.mark.parametrize("owner_slot", [0, 1])
def test_pre_typing_declaration_contradiction_requires_recompilation(kind, owner_slot):
    artifact = artifact_for(owner_slot=owner_slot)
    expr = artifact["program"]["derived"][0]["expr"]
    expr.update(kind=kind, current_slot=1 - owner_slot, related_slot=owner_slot)
    with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
        tuple_for(artifact)
    with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
        bind_request_relations(request_for(), artifact)


@pytest.mark.parametrize("owner_slot", [0, 1])
def test_versions_do_not_override_declared_order(owner_slot):
    artifact = artifact_for(owner_slot=owner_slot)
    rule = artifact["program"]["derived"][0]
    # The engine executes versions instead of base semantics. The base remains
    # ill typed and is rejected by the engine; the binder must never repair it.
    rule["versions"] = [{"expr": deepcopy(rule["expr"])}]
    assert tuple_for(artifact)[owner_slot] == "unit"


@pytest.mark.parametrize("supplied_slot", [0, 1])
def test_untyped_executed_relation_preserves_supplied_order_and_warns(supplied_slot):
    artifact = artifact_for(typed=False)
    request = request_for(supplied_slot=supplied_slot)
    with pytest.warns(RelationBindingAmbiguityWarning, match="members"):
        assert bind_request_relations(request, artifact) == request
    with pytest.warns(RelationBindingAmbiguityWarning, match="members"):
        assert tuple_for(artifact) == ["child", "unit"]


def test_untyped_unused_relation_has_no_diagnostic():
    artifact = artifact_for(typed=False)
    artifact["program"]["derived"] = []
    request = request_for()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert bind_request_relations(request, artifact) == request
    assert not caught
    assert tuple_for(None) == ["child", "unit"]
    assert tuple_for(None, legacy_owner_slot=0) == ["unit", "child"]


@pytest.mark.parametrize("invalid_kind", ["Entity", "Household"])
def test_both_known_mismatching_orders_raise(invalid_kind):
    request = request_for()
    request["dataset"]["inputs"][0]["entity"] = invalid_kind
    request["queries"] = []
    with pytest.raises(RelationBindingError):
        bind_request_relations(request, artifact_for())


@pytest.mark.parametrize("reverse_labels", [False, True])
def test_conflicting_input_labels_are_unknown_in_the_engine(reverse_labels):
    request = request_for(supplied_slot=0)
    request["dataset"]["inputs"].append({"entity_id": "child", "entity": "Payment"})
    if reverse_labels:
        request["dataset"]["inputs"].reverse()
    # The known TaxUnit endpoint alone fixes the order. Multiple labels on the
    # other id are not an error and do not make the supplied order unclean.
    assert bind_request_relations(request, artifact_for()) == request


def test_conflicting_query_entities_make_identity_unknown():
    artifact = artifact_for()
    artifact["program"]["derived"].append(
        {"name": "other", "entity": "Payment", "expr": {"kind": "input"}}
    )
    request = request_for(labels=False)
    request["queries"][0]["outputs"].append("other")
    with pytest.warns(RelationBindingAmbiguityWarning):
        assert bind_request_relations(request, artifact) == request


def test_query_entity_alone_can_fix_order():
    request = request_for(labels=False)
    bound = bind_request_relations(request, artifact_for())
    assert bound["dataset"]["relations"][0]["tuple"] == ["unit", "child"]


def test_typed_unknown_ids_preserve_and_warn():
    request = request_for(labels=False)
    request["queries"] = []
    with pytest.warns(RelationBindingAmbiguityWarning):
        assert bind_request_relations(request, artifact_for()) == request


def test_same_kind_known_ids_preserve_without_ambiguity_warning():
    artifact = artifact_for(owner="Person", related="Person")
    request = request_for(owner="Person")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert bind_request_relations(request, artifact) == request
    assert not caught


@pytest.mark.parametrize("owner_slot", [0, 1])
def test_same_kind_roles_use_unanimous_source_wrappers(owner_slot):
    artifact = artifact_for(owner="Person", related="Person")
    artifact["program"]["derived"] = []
    artifact["program"]["relations"].extend(
        [
            {
                "name": "filtered",
                "arity": 2,
                "derivation": derivation("members", slot=owner_slot),
            },
            {
                "name": "twice",
                "arity": 2,
                "derivation": derivation("filtered", slot=owner_slot),
            },
        ]
    )
    pair = relation_tuple(
        artifact,
        "members",
        owner_id="parent",
        owner_kind="Person",
        related_id="child",
        related_kind="Person",
    )
    assert pair[owner_slot] == "parent"


def test_same_kind_conflicting_wrappers_preserve_legacy_order_and_warn():
    artifact = artifact_for(owner="Person", related="Person")
    artifact["program"]["derived"] = []
    artifact["program"]["relations"].extend(
        [
            {"name": "left", "arity": 2, "derivation": derivation("members", slot=0)},
            {"name": "right", "arity": 2, "derivation": derivation("members", slot=1)},
        ]
    )
    with pytest.warns(RelationBindingAmbiguityWarning):
        assert relation_tuple(
            artifact,
            "members",
            owner_id="parent",
            owner_kind="Person",
            related_id="child",
            related_kind="Person",
        ) == ["child", "parent"]


def test_public_reference_resolves_a_bare_schema_with_public_rule_ids():
    artifact = artifact_for()
    artifact["program"]["derived"] = [
        {
            "name": "marker",
            "id": "us:statutes/26/1#marker",
            "entity": "TaxUnit",
            "expr": {"kind": "input", "name": "marker"},
        }
    ]
    assert relation_tuple(
        artifact,
        "us:statutes/26/1#relation.members",
        owner_id="unit",
        owner_kind="TaxUnit",
        related_id="child",
        related_kind="Person",
    ) == ["unit", "child"]


def test_short_name_never_borrows_a_namespaced_declaration():
    artifact = artifact_for()
    artifact["program"]["relations"] = [
        {
            "name": f"{prefix}#relation.members",
            "arity": 2,
            "slot_entities": ["TaxUnit", "Person"],
        }
        for prefix in ["one", "two"]
    ]
    artifact["program"]["derived"] = []
    assert tuple_for(artifact) == ["child", "unit"]
    request = request_for()
    assert bind_request_relations(request, artifact) == request


def test_relation_owner_kind_uses_effective_declaration():
    artifact = artifact_for()
    assert (
        relation_owner_kind(
            artifact, "members", default_owner_kind="Household", related_kind="Person"
        )
        == "TaxUnit"
    )
    artifact["program"]["relations"][0].pop("slot_entities")
    assert (
        relation_owner_kind(
            artifact, "members", default_owner_kind="Household", related_kind="Person"
        )
        == "Household"
    )


def test_higher_arity_and_multiplicity_are_preserved():
    artifact = artifact_for()
    artifact["program"]["relations"].append(
        {"name": "triple", "arity": 3, "slot_entities": ["A", "B", "C"]}
    )
    request = request_for()
    request["dataset"]["relations"] *= 3
    request["dataset"]["relations"].append({"name": "triple", "tuple": ["a", "b", "c"]})
    before = deepcopy(request)
    bound = bind_request_relations(request, artifact)
    assert len(bound["dataset"]["relations"]) == 4
    assert bound["dataset"]["relations"][-1] == before["dataset"]["relations"][-1]
    assert all(
        row["interval"] == before["dataset"]["relations"][0]["interval"]
        for row in bound["dataset"]["relations"][:3]
    )
    assert request == before


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_effective_slot_entities_inherits_only_outgoing_source_chain(depth):
    program = {
        "relations": [
            {"name": "base", "arity": 2, "slot_entities": ["Household", "Person"]}
        ]
    }
    source = "base"
    for index in range(depth):
        name = f"filtered{index}"
        program["relations"].append(
            {"name": name, "arity": 2, "derivation": derivation(source)}
        )
        source = name
    assert _effective_slot_entities(program, source) == ["Household", "Person"]
    assert _effective_slot_entities(program, "missing") is None


@pytest.mark.parametrize("schema_kinds", [[], ["Payment", "Person"]])
def test_effective_slot_entities_derivation_has_priority(schema_kinds):
    program = {
        "relations": [
            {"name": "base", "arity": 2, "slot_entities": ["Household", "Person"]},
            {
                "name": "filtered",
                "arity": 2,
                "slot_entities": schema_kinds,
                "derivation": derivation("base", kinds=["TaxUnit", "Person"]),
            },
        ]
    }
    assert _effective_slot_entities(program, "filtered") == ["TaxUnit", "Person"]
    program["relations"][1]["derivation"].pop("slot_entities")
    assert _effective_slot_entities(program, "filtered") == (
        schema_kinds or ["Household", "Person"]
    )


def test_effective_slot_entities_cycle_is_untyped_and_incoming_declaration_is_ignored():
    program = {
        "relations": [
            {"name": "a", "arity": 2, "derivation": derivation("b")},
            {"name": "b", "arity": 2, "derivation": derivation("a")},
            {
                "name": "incoming",
                "arity": 2,
                "slot_entities": ["Household", "Person"],
                "derivation": derivation("a"),
            },
        ]
    }
    assert _effective_slot_entities(program, "a") is None
    assert _effective_slot_entities(program, "b") is None
    assert _effective_slot_entities(program, "incoming") == ["Household", "Person"]


def test_filtered_kinds_filter_of_filter_and_only_entity_derivations_contribute():
    program = {
        "relations": [
            {"name": "base", "arity": 2, "slot_entities": ["Household", "Person"]},
            {
                "name": "filtered",
                "arity": 2,
                "derivation": derivation("base", entity="SnapUnit"),
            },
            {
                "name": "second",
                "arity": 2,
                "derivation": derivation(
                    "filtered", kinds=["SnapUnit", "Person"], entity="FinalUnit"
                ),
            },
            {"name": "ignored", "arity": 2, "derivation": derivation("base")},
        ],
        "derived": [
            {"name": "not_a_filter", "entity": "FakeUnit", "expr": {"kind": "input"}}
        ],
    }
    assert _filtered_entity_kinds(program) == {
        "SnapUnit": "Household",
        "FinalUnit": "Household",
    }


def test_filtered_kinds_conflicts_are_unmapped_and_cycles_return_nothing():
    program = {
        "relations": [
            {
                "name": "one",
                "arity": 2,
                "derivation": derivation(
                    "ghost", kinds=["Household", "Person"], entity="Conflict"
                ),
            },
            {
                "name": "two",
                "arity": 2,
                "derivation": derivation(
                    "ghost", kinds=["TaxUnit", "Person"], entity="Conflict"
                ),
            },
            {
                "name": "a",
                "arity": 2,
                "derivation": derivation("ghost", kinds=["B", "Person"], entity="A"),
            },
            {
                "name": "b",
                "arity": 2,
                "derivation": derivation("ghost", kinds=["A", "Person"], entity="B"),
            },
            {
                "name": "self",
                "arity": 2,
                "derivation": derivation(
                    "ghost", kinds=["Physical", "Person"], entity="Physical"
                ),
            },
            {
                "name": "untyped",
                "arity": 2,
                "derivation": derivation("ghost", entity="Unknown"),
            },
        ]
    }
    assert _filtered_entity_kinds(program) == {"Physical": "Physical"}


def test_filtered_entity_labels_are_canonicalized_in_roles_inputs_and_queries():
    artifact = artifact_for(owner="Household")
    artifact["program"]["relations"].append(
        {
            "name": "filtered",
            "arity": 2,
            "derivation": derivation("members", entity="SnapUnit"),
        }
    )
    artifact["program"]["derived"][0]["entity"] = "SnapUnit"
    request = request_for(owner="SnapUnit")
    assert bind_request_relations(request, artifact)["dataset"]["relations"][0][
        "tuple"
    ] == ["unit", "child"]
    assert relation_tuple(
        artifact,
        "members",
        owner_id="unit",
        owner_kind="SnapUnit",
        related_id="child",
        related_kind="Person",
    ) == ["unit", "child"]


def test_executed_relations_follows_sources_versions_and_nested_expressions():
    program = {
        "relations": [
            {"name": "base", "arity": 2},
            {"name": "filtered", "arity": 2, "derivation": derivation("base")},
            {"name": "unused", "arity": 2},
        ],
        "derived": [
            {
                "name": "n",
                "entity": "Household",
                "expr": {
                    "kind": "count_related",
                    "relation": "ignored_base",
                    "current_slot": 0,
                    "related_slot": 1,
                },
                "versions": [
                    {
                        "expr": {
                            "kind": "sum_related",
                            "relation": "filtered",
                            "current_slot": 0,
                            "related_slot": 1,
                            "where": {
                                "kind": "relation_member",
                                "relation": "tested",
                                "current_slot": 0,
                                "related_slot": 1,
                            },
                        }
                    }
                ],
            }
        ],
    }
    assert _executed_relations(program) == {"base", "filtered", "tested"}


@pytest.mark.parametrize(
    ("entity", "rule_id", "output", "evidence"),
    [
        ("TaxUnit", None, "member_count", True),
        ("TaxUnit", "urn:test#count", "urn:test#count", True),
        ("TaxUnit", "urn:test#count", "member_count", False),
        ("Scalar", None, "member_count", False),
    ],
)
def test_query_identity_resolves_public_ids_and_excludes_scalar(
    entity,
    rule_id,
    output,
    evidence,
):
    artifact = artifact_for()
    artifact["program"]["derived"] = [
        {
            "name": "member_count",
            "entity": entity,
            "expr": {"kind": "literal", "value": {"kind": "integer", "value": 1}},
        }
    ]
    if rule_id:
        artifact["program"]["derived"][0]["id"] = rule_id
    request = request_for(labels=False)
    request["queries"][0]["outputs"] = [output]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bound = bind_request_relations(request, artifact)
    assert bound["dataset"]["relations"][0]["tuple"] == (
        ["unit", "child"] if evidence else ["child", "unit"]
    )
    assert bool(caught) is not evidence


def test_filtered_kind_conflict_is_not_a_mapping_for_other_filter_chains():
    # resolve_filtered_kinds omits a conflicting key before innermost_kinds
    # follows chains. Another entity reaching that name therefore ends there.
    program = {
        "relations": [
            {
                "name": "one",
                "arity": 2,
                "derivation": derivation(
                    "ghost", kinds=["Household", "Person"], entity="Conflict"
                ),
            },
            {
                "name": "two",
                "arity": 2,
                "derivation": derivation(
                    "ghost", kinds=["TaxUnit", "Person"], entity="Conflict"
                ),
            },
            {
                "name": "outer",
                "arity": 2,
                "derivation": derivation(
                    "ghost", kinds=["Conflict", "Person"], entity="Outer"
                ),
            },
        ]
    }
    assert _filtered_entity_kinds(program) == {"Outer": "Conflict"}


@pytest.mark.parametrize("executed", [False, True])
@pytest.mark.parametrize("member_slot", [0, 1])
def test_direct_aggregate_in_a_derivation_predicate_has_related_id_scope(
    executed, member_slot
):
    artifact = artifact_for()
    program = artifact["program"]
    program["relations"].extend(
        [
            {"name": "people", "arity": 2, "slot_entities": ["Household", "Person"]},
            {
                "name": "filtered",
                "arity": 2,
                "derivation": derivation("people", slot=0),
            },
        ]
    )
    program["relations"][-1]["derivation"]["predicate"] = {
        "kind": "comparison",
        "left": {
            "kind": "count_related",
            "relation": "members",
            "current_slot": member_slot,
            "related_slot": 1 - member_slot,
        },
        "op": "gt",
        "right": {"kind": "literal", "value": {"kind": "integer", "value": 0}},
    }
    program["derived"] = (
        []
        if not executed
        else [
            {
                "name": "n",
                "entity": "Household",
                "expr": {
                    "kind": "count_related",
                    "relation": "filtered",
                    "current_slot": 0,
                    "related_slot": 1,
                },
            }
        ]
    )
    if executed and member_slot == 0:
        with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
            tuple_for(artifact)
    else:
        assert tuple_for(artifact) == ["unit", "child"]


def test_executed_relations_ignores_extension_fields_like_engine_serde():
    metadata = {
        "kind": "count_related",
        "relation": "members",
        "current_slot": 0,
        "related_slot": 1,
    }
    artifact = artifact_for(typed=False)
    artifact["program"]["derived"][0]["expr"] = {
        "kind": "comparison",
        "left": {"kind": "literal", "value": {"kind": "integer", "value": 1}},
        "op": "eq",
        "right": {"kind": "literal", "value": {"kind": "integer", "value": 1}},
        "metadata": metadata,
    }
    assert _executed_relations(artifact["program"]) == set()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        request = request_for()
        assert bind_request_relations(request, artifact) == request
    assert not caught


def test_pre_typing_policy_checks_predicates_reached_by_versioned_base_semantics():
    artifact = artifact_for()
    program = artifact["program"]
    program["relations"].extend(
        [
            {"name": "people", "arity": 2, "slot_entities": ["Household", "Person"]},
            {"name": "filtered", "arity": 2, "derivation": derivation("people")},
        ]
    )
    program["relations"][-1]["derivation"]["predicate"] = {
        "kind": "comparison",
        "left": {
            "kind": "count_related",
            "relation": "members",
            "current_slot": 0,
            "related_slot": 1,
        },
        "op": "gt",
        "right": {"kind": "literal", "value": {"kind": "integer", "value": 0}},
    }
    program["derived"] = [
        {
            "name": "n",
            "entity": "Household",
            "expr": {
                "kind": "count_related",
                "relation": "filtered",
                "current_slot": 0,
                "related_slot": 1,
            },
            "versions": [
                {"expr": {"kind": "literal", "value": {"kind": "integer", "value": 1}}}
            ],
        }
    ]
    assert _executed_relations(program) == set()
    with pytest.raises(RelationBindingError, match="recompile|migrate artifact"):
        tuple_for(artifact)
