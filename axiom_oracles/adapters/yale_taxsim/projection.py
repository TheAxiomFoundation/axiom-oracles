from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity


_SPOUSE_RELATIONS = {
    "spouse",
    "wife",
    "husband",
    "partner",
    "marriedpartner",
    "married_partner",
}

_HEAD_RELATIONS = {
    "head",
    "headofhousehold",
    "head_of_household",
    "householder",
    "referenceperson",
    "reference_person",
    "self",
}


def attach_yale_taxsim_inputs(cases: list[Case]) -> list[Case]:
    """Attach Yale Tax-Simulator bridge rows to cases that need projection."""

    projected = []
    for case in cases:
        metadata = dict(case.metadata)
        row = metadata.get("yale_taxsim_input") or case.fact("yale_taxsim_input")
        if row is None:
            row = yale_taxsim_input_for_case(case)
        elif not isinstance(row, Mapping):
            raise RuntimeError(
                "Case metadata['yale_taxsim_input'] must be a mapping of Yale "
                "Tax-Simulator bridge columns to values."
            )
        metadata["yale_taxsim_input"] = row
        projected.append(replace(case, metadata=metadata))
    return projected


def yale_taxsim_input_for_case(case: Case) -> dict[str, Any]:
    people = _people(case)
    if not people:
        raise RuntimeError(
            "Yale Tax-Simulator projection requires at least one person entity."
        )

    head = _head(people)
    spouse = _spouse(people, head)
    dependents = [
        person for person in people if person is not head and person is not spouse
    ]

    wages1 = _number(head.fact(Concepts.YEARLY_EARNED_INCOME, 0))
    wages2 = (
        _number(spouse.fact(Concepts.YEARLY_EARNED_INCOME, 0))
        if spouse is not None
        else 0
    )
    self_employment1 = _number(head.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0))
    self_employment2 = (
        _number(spouse.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0))
        if spouse is not None
        else 0
    )
    earners = [head] + ([spouse] if spouse is not None else [])

    return {
        "id": case.case_id,
        "year": _year(case.period),
        "filing_status": 2 if spouse is not None else (4 if dependents else 1),
        "age1": _age(head),
        "age2": _age(spouse) if spouse is not None else 0,
        "n_dep": len(dependents),
        "n_dep_child": sum(_age(dependent) < 17 for dependent in dependents),
        "wages1": wages1,
        "wages2": wages2,
        "wages": wages1 + wages2,
        "sole_prop1": self_employment1,
        "sole_prop2": self_employment2,
        "sole_prop": self_employment1 + self_employment2,
        "txbl_int": _sum_fact(earners, Concepts.INTEREST_INCOME),
        "div_ord": _sum_fact(earners, Concepts.DIVIDEND_INCOME),
        "div_pref": _sum_fact(earners, Concepts.QUALIFIED_DIVIDEND_INCOME),
        "kg_st": _sum_fact(earners, Concepts.SHORT_TERM_CAPITAL_GAINS),
        "kg_lt": _sum_fact(earners, Concepts.LONG_TERM_CAPITAL_GAINS),
        "gross_pens_dist": _sum_fact(earners, Concepts.PENSION_INCOME),
        "gross_ss": _sum_fact(earners, Concepts.SOCIAL_SECURITY_BENEFITS),
        "ui": _sum_fact(earners, Concepts.UNEMPLOYMENT_INSURANCE_INCOME),
        "prop_tax": _number(case.fact(Concepts.PROPERTY_TAX_PAID, 0)),
        "mort_int": _number(case.fact(Concepts.MORTGAGE_INTEREST_PAID, 0)),
        "childcare_exp": _number(case.fact(Concepts.CHILDCARE_EXPENSES, 0)),
        "weight": _number(case.metadata.get("weight", case.fact("weight", 1))),
    }


def _people(case: Case) -> list[Entity]:
    return [
        entity
        for entity in case.entities
        if str(entity.kind).lower().replace("_", "-") == "person"
    ]


def _head(people: list[Entity]) -> Entity:
    for person in people:
        if _relation(person) in _HEAD_RELATIONS:
            return person
    return people[0]


def _spouse(people: list[Entity], head: Entity) -> Entity | None:
    for person in people:
        if person is not head and _relation(person) in _SPOUSE_RELATIONS:
            return person
    return None


def _relation(entity: Entity) -> str:
    return (
        str(entity.fact(Concepts.HOUSEHOLD_RELATION, ""))
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _age(entity: Entity | None) -> int:
    if entity is None:
        return 0
    return int(_number(entity.fact(Concepts.PERSON_AGE, 0)))


def _sum_fact(people: list[Entity], concept: str) -> float:
    return sum(_number(person.fact(concept, 0)) for person in people)


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0
    return float(value)


def _year(period: str) -> int:
    return int(str(period).split("-", maxsplit=1)[0])
