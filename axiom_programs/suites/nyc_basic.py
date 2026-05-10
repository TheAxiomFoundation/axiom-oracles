from __future__ import annotations

from ..core.case import Case, Concepts, Entity


NYC_SCOPE = {"type": "census_place", "geoid": "3651000"}
NYC_METADATA = {"locale": "US-NY-NYC", "scope": NYC_SCOPE}
NYC_FACTS = {
    Concepts.STATE_CODE: "NY",
    Concepts.LIVING_RENTING: True,
    Concepts.LIVING_OWNER: False,
}


def nyc_basic_cases() -> list[Case]:
    """Small smoke suite for ACCESS NYC / PolicyEngine comparisons."""

    return [
        Case(
            case_id="nyc-single-adult-20k",
            period="2026-05",
            metadata=NYC_METADATA,
            facts={**NYC_FACTS, Concepts.CASH_ON_HAND: 500},
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 40,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 20_000,
                    },
                ),
            ),
        ),
        Case(
            case_id="nyc-single-adult-35k",
            period="2026-05",
            metadata=NYC_METADATA,
            facts={**NYC_FACTS, Concepts.CASH_ON_HAND: 1_500},
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 40,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 35_000,
                    },
                ),
            ),
        ),
        Case(
            case_id="nyc-single-parent-30k-child5",
            period="2026-05",
            metadata=NYC_METADATA,
            facts={**NYC_FACTS, Concepts.CASH_ON_HAND: 750},
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 30,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 30_000,
                    },
                ),
                Entity(
                    entity_id="child",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 5,
                        Concepts.HOUSEHOLD_RELATION: "Child",
                    },
                ),
            ),
        ),
        Case(
            case_id="nyc-parent-40k-toddler",
            period="2026-05",
            metadata=NYC_METADATA,
            facts={**NYC_FACTS, Concepts.CASH_ON_HAND: 1_000},
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 30,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 40_000,
                    },
                ),
                Entity(
                    entity_id="child",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 2,
                        Concepts.HOUSEHOLD_RELATION: "Child",
                    },
                ),
            ),
        ),
    ]
