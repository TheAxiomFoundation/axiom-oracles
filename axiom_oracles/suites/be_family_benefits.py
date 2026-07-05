from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


BIRTH_ALLOWANCE_MODULE = "be:statutes/family_benefits/birth_allowance"
CHILD_BENEFIT_BASE_MODULE = (
    "be:statutes/family_benefits/child_benefit_base_2025"
)

BRUSSELS_REGION = 1
FLANDERS_REGION = 2
WALLONIA_REGION = 3
GERMAN_SPEAKING_REGION = 4
GERMAN_SPEAKING_BIRTH_PREMIUM_2019 = 1_144
GERMAN_SPEAKING_BIRTH_PREMIUM_2025 = 1_376.16
GERMAN_SPEAKING_PRE_2025_INDEX_FACTOR = (
    GERMAN_SPEAKING_BIRTH_PREMIUM_2025
    / GERMAN_SPEAKING_BIRTH_PREMIUM_2019
)


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
            "be-family-birth-allowance-german-speaking-community-newborn",
            region=GERMAN_SPEAKING_REGION,
            scenario="german-speaking-community-birth-premium",
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
            "be-family-child-benefit-base-flanders-age-0",
            region=FLANDERS_REGION,
            scenario="flanders-new-system-age-0",
            child_age=0,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-flanders-age-6",
            region=FLANDERS_REGION,
            scenario="flanders-new-system-age-6",
            child_age=6,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-flanders-age-13",
            region=FLANDERS_REGION,
            scenario="flanders-old-system-age-13",
            child_age=13,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-flanders-age-18",
            region=FLANDERS_REGION,
            scenario="flanders-old-system-age-18-higher-education",
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
        _child_benefit_base_case(
            "be-family-child-benefit-base-german-speaking-community-age-0",
            region=GERMAN_SPEAKING_REGION,
            scenario="german-speaking-community-age-0",
            child_age=0,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-german-speaking-community-age-6",
            region=GERMAN_SPEAKING_REGION,
            scenario="german-speaking-community-age-6",
            child_age=6,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-german-speaking-community-age-13",
            region=GERMAN_SPEAKING_REGION,
            scenario="german-speaking-community-age-13",
            child_age=13,
        ),
        _child_benefit_base_case(
            "be-family-child-benefit-base-german-speaking-community-age-18-higher-education",
            region=GERMAN_SPEAKING_REGION,
            scenario="german-speaking-community-age-18-higher-education",
            child_age=18,
            higher_education=True,
        ),
    ]


def be_family_child_benefit_social_supplement_cases() -> list[Case]:
    """Belgium Brussels low-income child-benefit cases for EUROMOD BE_2025."""

    return [
        _child_benefit_social_supplement_case(
            "be-family-child-benefit-social-supplement-brussels-age-0",
            scenario="brussels-low-income-one-child-under-6",
            child_age=0,
        ),
        _child_benefit_social_supplement_case(
            "be-family-child-benefit-social-supplement-brussels-age-13",
            scenario="brussels-low-income-one-child-age-13",
            child_age=13,
        ),
        _child_benefit_social_supplement_case(
            "be-family-child-benefit-social-supplement-brussels-age-18-higher-education",
            scenario="brussels-low-income-one-child-age-18-higher-education",
            child_age=18,
            higher_education=True,
        ),
    ]


def be_family_child_benefit_brussels_same_age_household_cases() -> list[Case]:
    """Belgium Brussels same-age multi-child household bch_s cases."""

    return [
        _child_benefit_brussels_same_age_household_case(
            "be-family-child-benefit-brussels-same-age-household-two-children-age-0-low-income-single-parent",
            scenario="brussels-low-income-two-same-age-children-under-6-single-parent",
            child_age=0,
            child_count=2,
            single_parent=True,
            employment_income=500,
        ),
        _child_benefit_brussels_same_age_household_case(
            "be-family-child-benefit-brussels-same-age-household-two-children-age-13-low-income-couple",
            scenario="brussels-low-income-two-same-age-children-age-13-couple",
            child_age=13,
            child_count=2,
            single_parent=False,
            employment_income=500,
        ),
        _child_benefit_brussels_same_age_household_case(
            "be-family-child-benefit-brussels-same-age-household-three-children-age-13-low-income-couple",
            scenario="brussels-low-income-three-same-age-children-age-13-couple",
            child_age=13,
            child_count=3,
            single_parent=False,
            employment_income=500,
        ),
        _child_benefit_brussels_same_age_household_case(
            "be-family-child-benefit-brussels-same-age-household-two-children-age-0-middle-income-single-parent",
            scenario="brussels-middle-income-two-same-age-children-under-6-single-parent",
            child_age=0,
            child_count=2,
            single_parent=True,
            employment_income=4_000,
        ),
    ]


def be_family_child_benefit_wallonia_social_supplement_cases() -> list[Case]:
    """Belgium Wallonia Article 13 child-benefit cases for EUROMOD BE_2025."""

    return [
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-low-income-age-0",
            scenario="wallonia-low-income-one-child-under-6",
            child_age=0,
            annual_household_income=30_422.76,
            employment_income=2_500,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-low-income-age-6",
            scenario="wallonia-low-income-one-child-age-6",
            child_age=6,
            annual_household_income=30_422.76,
            employment_income=2_500,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-low-income-age-13",
            scenario="wallonia-low-income-one-child-age-13",
            child_age=13,
            annual_household_income=30_422.76,
            employment_income=2_500,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-low-income-age-18",
            scenario="wallonia-low-income-one-child-age-18",
            child_age=18,
            annual_household_income=30_422.76,
            employment_income=2_500,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-age-0",
            scenario="wallonia-middle-income-one-child-under-6",
            child_age=0,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-age-6",
            scenario="wallonia-middle-income-one-child-age-6",
            child_age=6,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-age-13",
            scenario="wallonia-middle-income-one-child-age-13",
            child_age=13,
        ),
        _child_benefit_wallonia_social_supplement_case(
            "be-family-child-benefit-wallonia-social-supplement-age-18",
            scenario="wallonia-middle-income-one-child-age-18",
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


def _child_benefit_social_supplement_case(
    case_id: str,
    *,
    scenario: str,
    child_age: int,
    higher_education: bool = False,
    annual_household_income: float = 12_000,
) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": scenario,
            "region_code": BRUSSELS_REGION,
            "child_age_years": child_age,
            "child_enrolled_in_higher_education": higher_education,
            "brussels_article_9_household_annual_income": annual_household_income,
            "axiom_inputs": _child_benefit_social_supplement_axiom_inputs(
                child_age=child_age,
                higher_education=higher_education,
                annual_household_income=annual_household_income,
            ),
            "euromod_inputs": _child_benefit_base_euromod_inputs(
                region=BRUSSELS_REGION,
                child_age=child_age,
                higher_education=higher_education,
                employment_income=500,
                single_parent=True,
            ),
        },
        entities=_child_benefit_base_entities(child_age=child_age),
        outputs=(Concepts.BE_FAMILY_CHILD_BENEFIT_WITH_SOCIAL_SUPPLEMENT,),
    )


def _child_benefit_brussels_same_age_household_case(
    case_id: str,
    *,
    scenario: str,
    child_age: int,
    child_count: int,
    single_parent: bool,
    employment_income: float,
    annual_household_income: float = 12_000,
    higher_education: bool = False,
) -> Case:
    income_input = _child_benefit_base_input(
        "belgium_child_benefit_brussels_article_9_household_annual_income"
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": scenario,
            "region_code": BRUSSELS_REGION,
            "child_age_years": child_age,
            "child_count": child_count,
            "same_age_children": True,
            "single_parent": single_parent,
            "child_enrolled_in_higher_education": higher_education,
            "brussels_article_9_household_annual_income": annual_household_income,
            "axiom_inputs": _child_benefit_social_supplement_axiom_inputs(
                child_age=child_age,
                higher_education=higher_education,
                annual_household_income=annual_household_income,
                child_count=child_count,
                single_parent=single_parent,
            ),
            "euromod_inputs": _child_benefit_base_euromod_inputs(
                region=BRUSSELS_REGION,
                child_age=child_age,
                higher_education=higher_education,
                employment_income=employment_income,
                single_parent=single_parent,
                child_count=child_count,
            ),
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "il_bch_means": [income_input],
            },
        },
        entities=_child_benefit_base_entities(
            child_age=child_age,
            child_count=child_count,
        ),
        outputs=(
            Concepts.BE_FAMILY_CHILD_BENEFIT_BRUSSELS_SAME_AGE_HOUSEHOLD_WITH_SOCIAL_SUPPLEMENT,
        ),
    )


def _child_benefit_wallonia_social_supplement_case(
    case_id: str,
    *,
    scenario: str,
    child_age: int,
    annual_household_income: float = 54_441.17,
    employment_income: float = 5_000,
) -> Case:
    household_income_input = _child_benefit_base_input(
        "belgium_child_benefit_wallonia_article_13_household_annual_income"
    )
    axiom_inputs = _child_benefit_base_axiom_inputs(
        region=WALLONIA_REGION,
        child_age=child_age,
        higher_education=False,
    )
    axiom_inputs[household_income_input] = annual_household_income
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Household",
            "axiom_entity_id": "household",
            "scenario": scenario,
            "region_code": WALLONIA_REGION,
            "child_age_years": child_age,
            "child_enrolled_in_higher_education": False,
            "wallonia_article_13_household_annual_income": annual_household_income,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": _child_benefit_base_euromod_inputs(
                region=WALLONIA_REGION,
                child_age=child_age,
                higher_education=False,
                employment_income=employment_income,
                single_parent=True,
            ),
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "il_bch_means": [household_income_input],
            },
        },
        entities=_child_benefit_base_entities(child_age=child_age),
        outputs=(Concepts.BE_FAMILY_CHILD_BENEFIT_WALLONIA_WITH_SOCIAL_SUPPLEMENT,),
    )


def _child_benefit_base_axiom_inputs(
    *,
    region: int,
    child_age: int,
    higher_education: bool,
    household_child_count: int = 1,
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
        ): household_child_count,
        _child_benefit_base_input(
            "belgium_family_benefits_child_benefit_child_enrolled_in_higher_education"
        ): higher_education,
    }


def _child_benefit_social_supplement_axiom_inputs(
    *,
    child_age: int,
    higher_education: bool,
    annual_household_income: float,
    child_count: int = 1,
    single_parent: bool = True,
) -> dict[str, float | int | bool]:
    inputs = _child_benefit_base_axiom_inputs(
        region=BRUSSELS_REGION,
        child_age=child_age,
        higher_education=higher_education,
        household_child_count=child_count,
    )
    inputs.update(
        {
            _child_benefit_base_input(
                "belgium_child_benefit_brussels_article_9_household_annual_income"
            ): annual_household_income,
            _child_benefit_base_input(
                "belgium_child_benefit_brussels_article_9_child_in_single_parent_family"
            ): single_parent,
            _child_benefit_base_input(
                "belgium_child_benefit_brussels_article_9_cadastral_income_cap_exceeded"
            ): False,
        }
    )
    return inputs


def _child_benefit_base_entities(
    *,
    child_age: int,
    child_count: int = 1,
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
    for index in range(child_count):
        entity_id = "child" if child_count == 1 else f"child-{index + 1}"
        entities.append(
            Entity(
                entity_id=entity_id,
                kind="person",
                facts={
                    Concepts.PERSON_AGE: child_age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )
    return tuple(entities)


def _birth_allowance_axiom_inputs(
    *,
    region: int,
    first_or_multiple: bool,
) -> dict[str, float | int | bool]:
    inputs = {
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
    if region == GERMAN_SPEAKING_REGION:
        inputs[
            _birth_allowance_input(
                "belgium_family_benefits_birth_allowance_german_speaking_community_pre_2025_index_factor"
            )
        ] = GERMAN_SPEAKING_PRE_2025_INDEX_FACTOR
    return inputs


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
    employment_income: float = 5_000,
    single_parent: bool = False,
    child_count: int = 1,
) -> list[dict[str, float | int]]:
    mother_id = 101
    child_id = 102
    father_id = 103
    if single_parent:
        rows = [
            _euromod_person_row(
                mother_id,
                age=35,
                region=region,
                gender=0,
                employment_income=employment_income,
            )
        ]
        rows.extend(
            _euromod_person_row(
                child_id + index,
                age=child_age,
                region=region,
                gender=1,
                mother_id=mother_id,
                in_education=child_age >= 6 or higher_education,
                higher_education=higher_education,
            )
            for index in range(child_count)
        )
        return rows

    rows = [
        _euromod_person_row(
            mother_id,
            age=35,
            region=region,
            gender=0,
            partner_id=father_id,
            marital_status=2,
            employment_income=employment_income,
        ),
        _euromod_person_row(
            father_id,
            age=35,
            region=region,
            gender=1,
            partner_id=mother_id,
            marital_status=2,
        ),
    ]
    child_ids = [child_id]
    child_ids.extend(range(father_id + 1, father_id + child_count))
    rows.extend(
        _euromod_person_row(
            id_,
            age=child_age,
            region=region,
            gender=1,
            mother_id=mother_id,
            father_id=father_id,
            in_education=child_age >= 6 or higher_education,
            higher_education=higher_education,
        )
        for id_ in child_ids
    )
    return rows


def _euromod_person_row(
    person_id: int,
    *,
    age: int,
    region: int,
    gender: int,
    partner_id: int = 0,
    mother_id: int = 0,
    father_id: int = 0,
    marital_status: int = 1,
    employment_income: float = 0,
    in_education: bool = False,
    higher_education: bool = False,
) -> dict[str, float | int]:
    employed = employment_income > 0
    return {
        "idperson": person_id,
        "idpartner": partner_id,
        "idmother": mother_id,
        "idfather": father_id,
        "byr": 0,
        "dag": age,
        "dec": 6 if higher_education else 0,
        "drgn1": region,
        "dgn": gender,
        "dms": marital_status,
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
