from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA


BIRTH_ALLOWANCE_MODULE = "be:statutes/family_benefits/birth_allowance"

BRUSSELS_REGION = 1
FLANDERS_REGION = 2
WALLONIA_REGION = 3
GERMAN_SPEAKING_REGION = 4


def be_family_birth_allowance_cases() -> list[Case]:
    """Belgium regional birth-allowance cases for EUROMOD BE_2025."""

    return [
        _birth_allowance_case(
            "be-family-birth-allowance-brussels-first-newborn",
            region=BRUSSELS_REGION,
            scenario="brussels-first-child-or-multiple-birth",
            first_or_multiple=True,
        ),
        _birth_allowance_case(
            "be-family-birth-allowance-brussels-later-newborn",
            region=BRUSSELS_REGION,
            scenario="brussels-later-child",
            first_or_multiple=False,
            existing_child_age=5,
        ),
        _birth_allowance_case(
            "be-family-birth-allowance-flanders-first-newborn",
            region=FLANDERS_REGION,
            scenario="flanders-first-child",
            first_or_multiple=True,
        ),
        _birth_allowance_case(
            "be-family-birth-allowance-flanders-later-newborn",
            region=FLANDERS_REGION,
            scenario="flanders-later-child",
            first_or_multiple=False,
            existing_child_age=5,
        ),
        _birth_allowance_case(
            "be-family-birth-allowance-wallonia-first-newborn",
            region=WALLONIA_REGION,
            scenario="wallonia-first-child",
            first_or_multiple=True,
        ),
        _birth_allowance_case(
            "be-family-birth-allowance-wallonia-later-newborn",
            region=WALLONIA_REGION,
            scenario="wallonia-later-child",
            first_or_multiple=False,
            existing_child_age=5,
        ),
        _birth_allowance_case(
            "be-family-birth-allowance-german-region-newborn-zero",
            region=GERMAN_SPEAKING_REGION,
            scenario="german-speaking-community-not-yet-encoded",
            first_or_multiple=True,
        ),
    ]


def _birth_allowance_case(
    case_id: str,
    *,
    region: int,
    scenario: str,
    first_or_multiple: bool,
    existing_child_age: int | None = None,
) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": scenario,
            "region_code": region,
            "child_age_years": 0,
            "brussels_first_child_or_multiple_birth": first_or_multiple,
            "axiom_inputs": _birth_allowance_axiom_inputs(
                region=region,
                first_or_multiple=first_or_multiple,
            ),
            "euromod_inputs": _birth_allowance_euromod_inputs(
                region=region,
                existing_child_age=existing_child_age,
            ),
        },
        entities=_birth_allowance_entities(existing_child_age=existing_child_age),
        outputs=(Concepts.BE_FAMILY_BIRTH_ALLOWANCE,),
    )


def _birth_allowance_axiom_inputs(
    *,
    region: int,
    first_or_multiple: bool,
) -> dict[str, float | int | bool]:
    return {
        _birth_allowance_input(
            "belgium_family_benefits_birth_allowance_child_age_years"
        ): 0,
        _birth_allowance_input(
            "belgium_family_benefits_birth_allowance_region"
        ): region,
        _birth_allowance_input(
            "belgium_family_benefits_birth_allowance_brussels_first_child_or_multiple_birth"
        ): first_or_multiple,
    }


def _birth_allowance_entities(
    *,
    existing_child_age: int | None,
) -> tuple[Entity, ...]:
    entities = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 35,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            },
        )
    ]
    if existing_child_age is not None:
        entities.append(
            Entity(
                entity_id="child-existing",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: existing_child_age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )
    entities.append(
        Entity(
            entity_id="newborn",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 0,
                Concepts.HOUSEHOLD_RELATION: "Child",
            },
        )
    )
    return tuple(entities)


def _birth_allowance_euromod_inputs(
    *,
    region: int,
    existing_child_age: int | None,
) -> list[dict[str, float | int]]:
    mother_id = 101
    rows = [_euromod_person_row(mother_id, age=35, region=region, gender=0)]
    if existing_child_age is not None:
        rows.append(
            _euromod_person_row(
                102,
                age=existing_child_age,
                region=region,
                gender=1,
                mother_id=mother_id,
            )
        )
        newborn_id = 103
    else:
        newborn_id = 102
    rows.append(
        _euromod_person_row(
            newborn_id,
            age=0,
            region=region,
            gender=1,
            mother_id=mother_id,
        )
    )
    return rows


def _euromod_person_row(
    person_id: int,
    *,
    age: int,
    region: int,
    gender: int,
    mother_id: int = 0,
) -> dict[str, float | int]:
    return {
        "idperson": person_id,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "dag": age,
        "drgn1": region,
        "dgn": gender,
        "dms": 1,
        "les": 0,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": 5,
        "yem": 0,
        "yemmy": 0,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _birth_allowance_input(name: str) -> str:
    return f"{BIRTH_ALLOWANCE_MODULE}#input.{name}"
