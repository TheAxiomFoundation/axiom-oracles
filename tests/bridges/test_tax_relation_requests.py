"""Producer contract tests; engine value assertions live in test_tax_relation_engine."""

from copy import deepcopy

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.bridges.tax_populace import (
    AOTC_BASE,
    CDCC_BASE,
    CTC_BASE,
    CTC_H_BASE,
    EITC_BASE,
    build_axiom_request,
)

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
    assert set(kinds.values()) == {"TaxUnit", "Person"}
    for relation in request["dataset"]["relations"]:
        owner_slot = slots[relation["name"]]
        assert kinds[relation["tuple"][owner_slot]] == "TaxUnit"
        assert kinds[relation["tuple"][1 - owner_slot]] == "Person"
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
    assert all(kind in {"TaxUnit", "Person"} for kind in kinds.values())
    assert len(request["dataset"]["relations"]) == sum(map(len, member_ages)) * len(
        RELATIONS[surface]
    )
    for relation in request["dataset"]["relations"]:
        current = slots[relation["name"]]
        assert kinds[relation["tuple"][current]] == "TaxUnit"
        assert kinds[relation["tuple"][1 - current]] == "Person"
    # Check retained producer roles, then compare every original wire field.
    legacy_wire = deepcopy(legacy)
    for relation in legacy_wire["dataset"]["relations"]:
        assert relation.pop("roles") == {
            "owner_id": relation["tuple"][1],
            "owner_kind": "TaxUnit",
            "related_id": relation["tuple"][0],
            "related_kind": "Person",
            "legacy_owner_slot": 1,
        }
    # Restore only the known legacy orientation: every input, value, interval,
    # query, relation multiplicity and relation name must remain identical.
    legacy_oriented = deepcopy(request)
    for relation in legacy_oriented["dataset"]["relations"]:
        if slots[relation["name"]] == 0:
            relation["tuple"].reverse()
    assert legacy_oriented == legacy_wire
    if all(slot == 1 for slot in slots.values()):
        assert request == legacy_wire
    assert artifact == original_artifact
