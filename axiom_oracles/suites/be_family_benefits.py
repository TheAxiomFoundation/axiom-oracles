from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA


BIRTH_ALLOWANCE_MODULE = "be:statutes/family_benefits/birth_allowance"
CHILD_BENEFIT_BASE_MODULE = (
    "be:statutes/family_benefits/child_benefit_base_2025"
)

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


def be_family_child_benefit_base_cases() -> list[Case]:
    """Belgium one-child base child-benefit cases for EUROMOD BE_2025."""

    return [
        _child_benefit_base_case(
            "be-family-child-benefit-base-brussels-age-0",
            region=BRUSSELS_REGION,
            scenario="brussels-new-system-under-6",
            child_age=0,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-brussels-age-6",
            region=BRUSSELS_REGION,
            scenario="brussels-transition-age-6",
            child_age=6,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-brussels-age-13",
            region=BRUSSELS_REGION,
            scenario="brussels-transition-age-13",
            child_age=13,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-brussels-age-18-no-higher-education",
            region=BRUSSELS_REGION,
            scenario="brussels-age-18-not-enrolled",
            child_age=18,
            higher_education=False,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-brussels-age-18-higher-education",
            region=BRUSSELS_REGION,
            scenario="brussels-age-18-higher-education",
            child_age=18,
            higher_education=True,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-wallonia-age-0",
            region=WALLONIA_REGION,
            scenario="wallonia-new-system-under-6",
            child_age=0,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-wallonia-age-6",
            region=WALLONIA_REGION,
            scenario="wallonia-pre-2020-age-6",
            child_age=6,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-wallonia-age-13",
            region=WALLONIA_REGION,
            scenario="wallonia-pre-2020-age-13",
            child_age=13,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-wallonia-age-18",
            region=WALLONIA_REGION,
            scenario="wallonia-pre-2020-age-18",
            child_age=18,
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


def _child_benefit_base_case(
    case_id: str,
    *,
    region: int,
    scenario: str,
    child_age: int,
    higher_education: bool = False,
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
            "child_age_years": child_age,
            "child_enrolled_in_higher_education": higher_education,
            "axiom_inputs": _child_benefit_base_axiom_inputs(
                region=region,
                child_age=child_age,
                higher_education=higher_education,
            ),
            "euromod_inputs": _child_benefit_base_euromod_inputs(
                region=region,
                child_age=child_age,
                higher_education=higher_education,
            ),
        },
        entities=_child_benefit_base_entities(child_age=child_age),
        outputs=(Concepts.BE_FAMILY_CHILD_BENEFIT_BASE,),
    )


def _child_benefit_base_axiom_inputs(
    *,
    region: int,
    child_age: int,
    higher_education: bool,
) -> dict[str, float | int | bool]:
    return {
        _child_benefit_base_input(
            "belgium_family_benefits_child_benefit_child_age_years"
        ): child_age,
        _child_benefit_base_input(
            "belgium_family_benefits_child_benefit_region"
        ): region,
        _child_benefit_base_input(
            "belgium_family_benefits_child_benefit_household_child_count"
        ): 1,
        _child_benefit_base_input(
            "belgium_family_benefits_child_benefit_child_enrolled_in_higher_education"
        ): higher_education,
    }


def _child_benefit_base_entities(*, child_age: int) -> tuple[Entity, ...]:
    return (
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 35,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            },
        ),
        Entity(
            entity_id="child",
            kind="person",
            facts={
                Concepts.PERSON_AGE: child_age,
                Concepts.HOUSEHOLD_RELATION: "Child",
            },
        ),
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


def _child_benefit_base_euromod_inputs(
    *,
    region: int,
    child_age: int,
    higher_education: bool,
) -> list[dict[str, float | int]]:
    mother_id = 101
    return [
        _euromod_person_row(
            mother_id,
            age=35,
            region=region,
            gender=0,
            employment_income=5_000,
        ),
        _euromod_person_row(
            102,
            age=child_age,
            region=region,
            gender=1,
            mother_id=mother_id,
            in_education=child_age >= 6 or higher_education,
            higher_education=higher_education,
        ),
    ]


def _euromod_person_row(
    person_id: int,
    *,
    age: int,
    region: int,
    gender: int,
    mother_id: int = 0,
    employment_income: float = 0,
    in_education: bool = False,
    higher_education: bool = False,
) -> dict[str, float | int]:
    employed = employment_income > 0
    return {
        "idperson": person_id,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "byr": 2025 - age,
        "dag": age,
        "dec": 6 if higher_education else 0,
        "drgn1": region,
        "dgn": gender,
        "dms": 1,
        "les": 3 if employed else 6 if in_education else 0,
        "lfs": 15 if (employed or in_education) else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 0,
        "liwwh21_h": 18 if employed else 0,
        "liwwh33_h": 24 if employed else 0,
        "liwwh42_h": 5 if employed else 0,
        "loc": 5,
        "xed00": 1 if (in_education or higher_education) else 0,
        "yem": employment_income,
        "yemmy": 12 if employed else 0,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _birth_allowance_input(name: str) -> str:
    return f"{BIRTH_ALLOWANCE_MODULE}#input.{name}"


def _child_benefit_base_input(name: str) -> str:
    return f"{CHILD_BENEFIT_BASE_MODULE}#input.{name}"
