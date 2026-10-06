"""Producer contract tests; engine value assertions live in test_tax_relation_engine."""

from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.bridges.tax_populace import (
    AOTC_BASE,
    CDCC_BASE,
    CTC_BASE,
    CTC_H_BASE,
    EITC_BASE,
    _runtime_axiom_request,
    build_axiom_request,
)
from axiom_oracles.bridges.input_binding import bind_typed_input_entities
from axiom_oracles.bridges.relation_binding import RelationBindingError

RELATIONS = {
    "ctc": [
        f"{CTC_BASE}#relation.ctc_qualifying_child_of_tax_unit",
        f"{CTC_H_BASE}#relation.dependent_of_tax_unit",
    ],
    "cdcc": [f"{CDCC_BASE}#relation.qualifying_individual_of_tax_unit"],
    "aotc": [f"{AOTC_BASE}#relation.education_credit_member_of_tax_unit"],
    "eitc": [f"{EITC_BASE}#relation.qualifying_child_of_tax_unit"],
}


def population(member_ages):
    units, persons = [], []
    for unit_id, ages in enumerate(member_ages, start=1):
        units.append(
            {
                "tax_unit_id": unit_id,
                "filing_status": "SINGLE",
                "adjusted_gross_income": 15_000,
                "min_head_spouse_earned": 15_000,
                "tax_unit_childcare_expenses": 3_000,
                "cdcc_credit_limit": 5_000,
                "income_tax_before_credits": 5_000,
            }
        )
        for index, age in enumerate(ages):
            persons.append(
                {
                    "person_id": len(persons) + 1,
                    "person_tax_unit_id": unit_id,
                    "age": age,
                    "ssn_card_type": "CITIZEN",
                    "is_tax_unit_head": index == 0,
                    "is_tax_unit_spouse": False,
                }
            )
    return {
        "tax_units": pd.DataFrame(units),
        "persons": pd.DataFrame(persons),
        "tax_unit_ids": [unit["tax_unit_id"] for unit in units],
    }


def artifact_for(surface, declarations):
    relations, derived = [], []
    expected = {}
    for name, (typed, current, declared_current) in zip(
        RELATIONS[surface], declarations, strict=True
    ):
        # Historical untyped artifacts execute related-first. Typed declarations
        # may disagree with usage (the engine preserves them for source fidelity).
        current = current if typed else 1
        schema = {"name": name, "arity": 2}
        if typed:
            schema["slot_entities"] = (
                ["TaxUnit", "Person"]
                if declared_current == 0
                else ["Person", "TaxUnit"]
            )
        relations.append(schema)
        derived.append(
            {
                "name": name + "_count",
                "entity": "TaxUnit",
                "expr": {
                    "kind": "scalar",
                    "expr": {
                        "kind": "count_related",
                        "relation": name,
                        "current_slot": current,
                        "related_slot": 1 - current,
                    },
                },
            }
        )
        expected[name] = current
    return {"program": {"relations": relations, "derived": derived}}, expected


@pytest.mark.parametrize("surface", RELATIONS)
@pytest.mark.parametrize("typed", [False, True])
def test_tax_requests_follow_artifact_slots(surface, typed):
    artifact, slots = artifact_for(surface, [(typed, 0, 0)] * len(RELATIONS[surface]))
    data = population([[35, 8], [50]])
    request = build_axiom_request(
        pe_data=data,
        year=2026,
        surface=surface,
        contribution_base=184_500,
        artifact=artifact,
    )
    kinds = {item["entity_id"]: item["entity"] for item in request["dataset"]["inputs"]}
    assert set(kinds.values()) == ({"TaxUnit", "Person"} if typed else {"Entity"})
    owners = {f"tax_unit_{unit_id}" for unit_id in data["tax_unit_ids"]}
    for relation in request["dataset"]["relations"]:
        owner_slot = slots[relation["name"]]
        assert relation["tuple"][owner_slot] in owners
        assert relation["tuple"][1 - owner_slot] not in owners
    assert "relation_binding" not in request


@pytest.mark.parametrize("surface", RELATIONS)
@settings(max_examples=60, deadline=None)
@given(
    member_ages=st.lists(
        st.lists(st.integers(0, 100), max_size=12), min_size=1, max_size=4
    ),
    declarations=st.lists(
        st.tuples(st.booleans(), st.integers(0, 1), st.integers(0, 1)),
        min_size=2,
        max_size=2,
    ),
)
def test_generated_tax_units_keep_entity_kinds_in_executable_slots(
    surface, member_ages, declarations
):
    data = population(member_ages)
    artifact, slots = artifact_for(surface, declarations[: len(RELATIONS[surface])])
    original_artifact = deepcopy(artifact)
    kwargs = dict(pe_data=data, year=2026, surface=surface, contribution_base=184_500)
    legacy = build_axiom_request(**kwargs)
    request = build_axiom_request(**kwargs, artifact=artifact)
    kinds = {item["entity_id"]: item["entity"] for item in request["dataset"]["inputs"]}
    typed = any(item[0] for item in declarations[: len(RELATIONS[surface])])
    assert all(
        kind in ({"TaxUnit", "Person"} if typed else {"Entity"})
        for kind in kinds.values()
    )
    assert len(request["dataset"]["relations"]) == sum(map(len, member_ages)) * len(
        RELATIONS[surface]
    )
    owners = {f"tax_unit_{unit_id}" for unit_id in data["tax_unit_ids"]}
    for relation in request["dataset"]["relations"]:
        current = slots[relation["name"]]
        assert relation["tuple"][current] in owners
        assert relation["tuple"][1 - current] not in owners
    # Restore the historical labels and orientation. The frozen golden below
    # independently checks the historical contract against the old producer.
    legacy_oriented = deepcopy(request)
    for item in legacy_oriented["dataset"]["inputs"]:
        item["entity"] = "Entity"
    for relation in legacy_oriented["dataset"]["relations"]:
        if slots[relation["name"]] == 0:
            relation["tuple"].reverse()
    assert legacy_oriented == legacy
    if not typed:
        assert request == legacy
    assert artifact == original_artifact


@pytest.mark.parametrize("surface", RELATIONS)
@pytest.mark.parametrize("entrypoint", ["raw", "builder", "compiled_runtime"])
def test_historical_request_bytes_match_merge_base_producer(
    surface, entrypoint, tmp_path
):
    """The fixture was generated by executing merge-base tax_populace.py.

    Its producer commit is recorded in the file; no current producer request
    was used to construct these golden requests.
    """
    golden = json.loads(
        (
            Path(__file__).parent / "fixtures/tax_relation_requests_merge_base.json"
        ).read_text()
    )
    assert golden["producer_commit"] == "57f9d331e1ea09143e2689de4ee3ce4b17c1030c"
    kwargs = dict(
        pe_data=population(golden["member_ages"]),
        year=golden["year"],
        surface=surface,
        contribution_base=golden["contribution_base"],
    )
    artifact = artifact_for(surface, [(False, 1, 1)] * len(RELATIONS[surface]))[0]
    if entrypoint == "builder":
        kwargs["artifact"] = artifact
    request = build_axiom_request(**kwargs)
    if entrypoint == "compiled_runtime":
        request, _ = _runtime_axiom_request(
            request, artifact_payload=artifact, rulespec_root=tmp_path / "rulespec-us"
        )
    assert (
        json.dumps(request).encode() == json.dumps(golden["requests"][surface]).encode()
    )


def test_compiled_input_scope_labels_claimant_and_aggregation_member():
    artifact = {
        "program": {
            "relations": [
                {"name": "members", "arity": 2, "slot_entities": ["Payment", "Person"]}
            ],
            "derived": [
                {
                    "name": "total",
                    "id": "uk:test#total",
                    "entity": "Person",
                    "expr": {
                        "kind": "add",
                        "items": [
                            {"kind": "input", "name": "claimant_income"},
                            {
                                "kind": "sum_related",
                                "relation": "members",
                                "current_slot": 1,
                                "related_slot": 0,
                                "value": {"kind": "input", "name": "amount"},
                            },
                        ],
                    },
                }
            ],
        },
    }
    # Statutory scope comes from expressions, despite the claimant's benunit ID.
    request = {
        "dataset": {
            "inputs": [
                {
                    "name": "uk:test#input.claimant_income",
                    "entity_id": "benunit_1",
                    "entity": "Entity",
                },
                {
                    "name": "uk:test#input.unused",
                    "entity_id": "benunit_1",
                    "entity": "Entity",
                },
                {
                    "name": "uk:test#input.amount",
                    "entity_id": "payment_1",
                    "entity": "Entity",
                },
            ]
        },
        "queries": [],
    }
    original = deepcopy(request)
    bound = bind_typed_input_entities(request, artifact)
    assert [record["entity"] for record in bound["dataset"]["inputs"]] == [
        "Person",
        "Person",
        "Payment",
    ]
    assert request == original
    untyped = deepcopy(artifact)
    untyped["program"]["relations"][0].pop("slot_entities")
    assert bind_typed_input_entities(request, untyped) == original


def test_compiled_input_scope_never_overrides_conflicting_specific_label():
    artifact = {
        "program": {
            "relations": [{"name": "members", "slot_entities": ["TaxUnit", "Person"]}],
            "derived": [
                {
                    "name": "amount",
                    "entity": "Person",
                    "expr": {"kind": "input", "name": "amount"},
                }
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [{"name": "amount", "entity_id": "one", "entity": "TaxUnit"}]
        }
    }
    with pytest.raises(RelationBindingError, match="conflicting compiled input scopes"):
        bind_typed_input_entities(request, artifact)


def test_global_scalar_outputs_and_inputs_do_not_constrain_entity_kinds():
    artifact = {
        "program": {
            "relations": [{"name": "members", "slot_entities": ["TaxUnit", "Person"]}],
            "derived": [
                {
                    "name": "person_amount",
                    "entity": "Person",
                    "expr": {"kind": "input", "name": "amount"},
                },
                {
                    "name": "global_amount",
                    "entity": "Scalar",
                    "expr": {"kind": "input", "name": "global_amount"},
                },
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [
                {"name": "amount", "entity_id": "one", "entity": "Entity"},
                {"name": "global_amount", "entity_id": "one", "entity": "Entity"},
            ]
        },
        "queries": [
            {"entity_id": "one", "outputs": ["person_amount", "global_amount"]}
        ],
    }
    bound = bind_typed_input_entities(request, artifact)
    assert {record["entity"] for record in bound["dataset"]["inputs"]} == {"Person"}


@pytest.mark.parametrize("owner_first", [False, True])
def test_count_only_relation_labels_unused_member_inputs_from_known_owner(owner_first):
    artifact = {
        "program": {
            "relations": [
                {"name": "members", "arity": 2, "slot_entities": ["Person", "TaxUnit"]}
            ],
            "derived": [
                {
                    "name": "count",
                    "entity": "TaxUnit",
                    "expr": {
                        "kind": "count_related",
                        "relation": "members",
                        "current_slot": 0,
                        "related_slot": 1,
                    },
                }
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [
                {"name": "unused", "entity_id": "unit", "entity": "Entity"},
                {"name": "unused", "entity_id": "person", "entity": "Entity"},
            ],
            "relations": [
                {
                    "name": "members",
                    "tuple": ["unit", "person"] if owner_first else ["person", "unit"],
                }
            ],
        },
        "queries": [{"entity_id": "unit", "outputs": ["count"]}],
    }
    bound = bind_typed_input_entities(request, artifact)
    assert [record["entity"] for record in bound["dataset"]["inputs"]] == [
        "TaxUnit",
        "Person",
    ]


def test_runtime_input_binding_preserves_unrelated_higher_arity_relation():
    artifact = {
        "program": {
            "relations": [
                {
                    "name": "triple",
                    "arity": 3,
                    "slot_entities": ["Person", "Family", "Payment"],
                }
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [],
            "relations": [{"name": "triple", "tuple": ["person", "family", "payment"]}],
        }
    }
    assert bind_typed_input_entities(request, artifact) == request


@pytest.mark.parametrize("specific_labels", [False, True])
def test_shared_input_scope_is_narrowed_by_queries_relations_and_known_labels(
    specific_labels,
):
    artifact = {
        "program": {
            "relations": [
                {"name": "members", "arity": 2, "slot_entities": ["TaxUnit", "Person"]}
            ],
            "derived": [
                {
                    "name": "unit_amount",
                    "entity": "TaxUnit",
                    "expr": {"kind": "input", "name": "shared"},
                },
                {
                    "name": "person_amount",
                    "entity": "Person",
                    "expr": {"kind": "input", "name": "shared"},
                },
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [
                {
                    "name": "shared",
                    "entity_id": "unit",
                    "entity": "TaxUnit" if specific_labels else "Entity",
                },
                {
                    "name": "shared",
                    "entity_id": "person",
                    "entity": "Person" if specific_labels else "Entity",
                },
            ],
            "relations": [{"name": "members", "tuple": ["person", "unit"]}],
        },
        "queries": [{"entity_id": "unit", "outputs": ["unit_amount"]}],
    }
    bound = bind_typed_input_entities(request, artifact)
    assert [record["entity"] for record in bound["dataset"]["inputs"]] == [
        "TaxUnit",
        "Person",
    ]


@pytest.mark.parametrize("specific_owner", [False, True])
def test_filtered_entity_alias_keeps_structural_owner_kind(specific_owner):
    artifact = {
        "program": {
            "relations": [
                {
                    "name": "members",
                    "arity": 2,
                    "slot_entities": ["Person", "Household"],
                },
                {
                    "name": "snap_unit",
                    "arity": 2,
                    "slot_entities": ["Person", "Household"],
                    "derivation": {
                        "source_relation": "members",
                        "entity": "SnapUnit",
                        "current_slot": 1,
                        "related_slot": 0,
                        "slot_entities": ["Person", "Household"],
                        "predicate": {"kind": "bool", "value": True},
                    },
                },
            ],
            "derived": [
                {
                    "name": "snap_unit_size",
                    "entity": "SnapUnit",
                    "expr": {
                        "kind": "add",
                        "items": [
                            {"kind": "input", "name": "unused"},
                            {
                                "kind": "count_related",
                                "relation": "snap_unit",
                                "current_slot": 1,
                                "related_slot": 0,
                            },
                        ],
                    },
                }
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [
                {
                    "name": "unused",
                    "entity_id": "household",
                    "entity": "Household" if specific_owner else "Entity",
                },
                {"name": "person_unused", "entity_id": "person", "entity": "Entity"},
            ],
            "relations": [{"name": "members", "tuple": ["person", "household"]}],
        },
        "queries": [{"entity_id": "household", "outputs": ["snap_unit_size"]}],
    }
    bound = bind_typed_input_entities(request, artifact)
    assert [record["entity"] for record in bound["dataset"]["inputs"]] == [
        "Household",
        "Person",
    ]


def test_aggregation_input_scope_uses_executable_member_kind_over_declaration():
    artifact = {
        "program": {
            "relations": [
                {"name": "members", "arity": 2, "slot_entities": ["TaxUnit", "Person"]}
            ],
            "derived": [
                {
                    "name": "eligible",
                    "entity": "Payment",
                    "expr": {"kind": "bool", "value": True},
                },
                {
                    "name": "total",
                    "entity": "TaxUnit",
                    "expr": {
                        "kind": "sum_related",
                        "relation": "members",
                        "current_slot": 0,
                        "related_slot": 1,
                        "where": {"kind": "derived", "name": "eligible"},
                        "value": {"kind": "input", "name": "amount"},
                    },
                },
            ],
        }
    }
    request = {
        "dataset": {
            "inputs": [
                {"name": "unused", "entity_id": "unit", "entity": "Entity"},
                {"name": "amount", "entity_id": "payment", "entity": "Entity"},
            ],
            "relations": [{"name": "members", "tuple": ["unit", "payment"]}],
        },
        "queries": [{"entity_id": "unit", "outputs": ["total"]}],
    }
    bound = bind_typed_input_entities(request, artifact)
    assert [record["entity"] for record in bound["dataset"]["inputs"]] == [
        "TaxUnit",
        "Payment",
    ]
