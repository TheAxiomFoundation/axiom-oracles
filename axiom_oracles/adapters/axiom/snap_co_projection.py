"""Project thin Axiom Cases into Colorado SNAP RuleSpec input records.

Colorado SNAP FY 2026 (rules-us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml)
declares >340 fully-namespaced ``#input.X`` slots across federal SNAP statutes,
USDA policies, 7-CFR regulations, and the 10-CCR-2506-1 Colorado SNAP manual.
This module ships a baseline drawn from the upstream test fixture and lets a
Case override the small set of facts the ECPS population actually carries
(household size, member ages, citizenship, earned income).

Use ``attach_axiom_snap_co_inputs(cases)`` from the CLI when a SNAP comparison
is requested and the cases scope to Colorado. The runner picks the input
records up via ``case.metadata[AXIOM_INPUT_RECORDS_METADATA_KEY]``.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from ...core.case import Case, Concepts, Entity
from ._snap_co_base_inputs import BASE_INPUTS, BASE_MEMBER
from .runner import (
    AXIOM_INPUT_RECORDS_METADATA_KEY,
    AXIOM_RELATIONS_METADATA_KEY,
)


_SNAP_HOUSEHOLD_ID = "household"
_SNAP_HOUSEHOLD_ENTITY = "Household"
_MEMBER_RELATION = "us:statutes/7/2012/j#relation.member_of_household"
_WAGES_INPUT = "us-co:regulations/10-ccr-2506-1/4.403#input.employee_wages_received"
_HOUSEHOLD_SIZE_INPUT = (
    "us-co:regulations/10-ccr-2506-1/4.207.3#input.household_size"
)

US_SNAP_CO_PROGRAM_PATH = (
    "policies/cdhs/snap/fy-2026-benefit-calculation.yaml"
)

# Precompiled artifact shipped alongside this projection. Bundling the
# artifact lets axiom-oracles use `axiom-rules-engine run-compiled` and
# avoid recompiling the CO SNAP YAML on every case — which would also
# require an engine binary that supports `kind: reiteration`.
US_SNAP_CO_COMPILED_ARTIFACT_PATH = (
    Path(__file__).parent / "artifacts" / "co-snap.compiled.json"
)


def attach_axiom_snap_co_inputs(cases: list[Case]) -> list[Case]:
    """Attach Axiom CO SNAP input records to cases that lack them."""
    projected = []
    for case in cases:
        metadata = dict(case.metadata)
        if metadata.get(AXIOM_INPUT_RECORDS_METADATA_KEY):
            projected.append(case)
            continue

        people = _people(case)
        household_size = max(len(people), 1)

        # Tax-unit/household level inputs: start from the test-fixture
        # baseline, then override the few fields the Case carries.
        inputs = dict(BASE_INPUTS)
        inputs[_HOUSEHOLD_SIZE_INPUT] = household_size
        inputs[_WAGES_INPUT] = _monthly_income(people)

        records = [
            _input_record(name, _SNAP_HOUSEHOLD_ENTITY, _SNAP_HOUSEHOLD_ID, value)
            for name, value in inputs.items()
        ]

        # Member relation: one entry per person, with age and citizenship
        # carried from the Case.
        member_records = []
        relation_tuples = []
        for index, person in enumerate(people):
            person_id = f"snap-member-{index}"
            relation_tuples.append([person_id, _SNAP_HOUSEHOLD_ID])
            for input_name, default in BASE_MEMBER.items():
                value = _member_value(input_name, person, default)
                member_records.append(
                    _input_record(input_name, "Person", person_id, value)
                )

        metadata[AXIOM_INPUT_RECORDS_METADATA_KEY] = records + member_records
        metadata[AXIOM_RELATIONS_METADATA_KEY] = [
            *metadata.get(AXIOM_RELATIONS_METADATA_KEY, []),
            *[
                {"name": _MEMBER_RELATION, "tuple": tup}
                for tup in relation_tuples
            ],
        ]
        # Output entity for SNAP outputs is the Household, not the default
        # TaxUnit used by the federal-income-tax projection.
        metadata["axiom_entity_id"] = _SNAP_HOUSEHOLD_ID
        metadata["axiom_entity"] = _SNAP_HOUSEHOLD_ENTITY

        projected.append(replace(case, metadata=metadata))
    return projected


def _people(case: Case) -> list[Entity]:
    return [
        entity
        for entity in case.entities
        if str(entity.kind).lower().replace("_", "-") == "person"
    ]


def _monthly_income(people: list[Entity]) -> float:
    """CO SNAP wage input is the household's anticipated monthly wages."""
    annual = sum(
        _number(person.fact(Concepts.YEARLY_EARNED_INCOME, 0)) for person in people
    )
    return round(annual / 12, 2)


def _member_value(input_name: str, person: Entity, default: Any) -> Any:
    if "member_age" in input_name:
        age = person.fact(Concepts.PERSON_AGE)
        if age is not None:
            return int(age)
    if "snap_member_is_elderly_or_disabled" in input_name:
        age = _number(person.fact(Concepts.PERSON_AGE, 0))
        disabled = bool(person.fact(Concepts.DISABLED, False))
        return age >= 60 or disabled
    if "enrolled_at_least_half_time" in input_name:
        return False
    if "member_is_us_citizen" in input_name:
        return True
    return default


def _input_record(name: str, entity: str, entity_id: str, value: Any) -> dict:
    return {
        "name": name,
        "entity": entity,
        "entity_id": entity_id,
        "value": value,
    }


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)
