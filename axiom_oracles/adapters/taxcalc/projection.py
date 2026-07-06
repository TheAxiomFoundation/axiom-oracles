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

_HOH_YOUNG_ADULT_DEPENDENT_AGE_LIMIT = 24
_HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT = 5_200


def attach_taxcalc_inputs(cases: list[Case]) -> list[Case]:
    """Attach PSL Tax-Calculator input rows to cases that need projection."""

    projected = []
    for index, case in enumerate(cases, start=1):
        metadata = dict(case.metadata)
        row = metadata.get("taxcalc_input") or case.fact("taxcalc_input")
        if row is None:
            row = taxcalc_input_for_case(case, record_id=index)
        elif not isinstance(row, Mapping):
            raise RuntimeError(
                "Case metadata['taxcalc_input'] must be a mapping of "
                "Tax-Calculator input columns to values."
            )
        metadata["taxcalc_input"] = row
        projected.append(replace(case, metadata=metadata))
    return projected


def taxcalc_input_for_case(
    case: Case,
    *,
    record_id: int | str | None = None,
) -> dict[str, Any]:
    people = _people(case)
    if not people:
        raise RuntimeError(
            "Tax-Calculator projection requires at least one person entity."
        )

    head = _head(people)
    spouse = _spouse(people, head)
    dependents = [
        person for person in people if person is not head and person is not spouse
    ]
    dependent_ages = [_age(dependent) for dependent in dependents]
    earners = [head] + ([spouse] if spouse is not None else [])

    head_wages = _number(head.fact(Concepts.YEARLY_EARNED_INCOME, 0))
    spouse_wages = (
        _number(spouse.fact(Concepts.YEARLY_EARNED_INCOME, 0))
        if spouse is not None
        else 0
    )
    head_self_employment = _number(head.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0))
    spouse_self_employment = (
        _number(spouse.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0))
        if spouse is not None
        else 0
    )
    dividend_income = _sum_fact(earners, Concepts.DIVIDEND_INCOME)
    qualified_dividend_income = min(
        dividend_income,
        _sum_fact(
            earners,
            Concepts.QUALIFIED_DIVIDEND_INCOME,
        ),
    )
    pension_income = _sum_fact(earners, Concepts.PENSION_INCOME)
    rental_income = _sum_fact(earners, Concepts.RENTAL_INCOME)

    row: dict[str, Any] = {
        "RECID": record_id if record_id is not None else case.case_id,
        "FLPDYR": _year(case.period),
        "MARS": _mars(spouse=spouse, dependents=dependents),
        "XTOT": len(people),
        "EIC": min(3, sum(_is_eic_qualifying_child(dep) for dep in dependents)),
        "n24": sum(age < 17 for age in dependent_ages),
        "nu18": sum(age < 18 for age in dependent_ages),
        "nu13": sum(age < 13 for age in dependent_ages),
        "nu06": sum(age < 6 for age in dependent_ages),
        "age_head": _age(head),
        "age_spouse": _age(spouse) if spouse is not None else 0,
        "blind_head": int(bool(head.fact(Concepts.BLIND, False))),
        "blind_spouse": (
            int(bool(spouse.fact(Concepts.BLIND, False)))
            if spouse is not None
            else 0
        ),
        "e00200p": head_wages,
        "e00200s": spouse_wages,
        "e00200": head_wages + spouse_wages,
        "e00900p": head_self_employment,
        "e00900s": spouse_self_employment,
        "e00900": head_self_employment + spouse_self_employment,
        "e00300": _sum_fact(earners, Concepts.INTEREST_INCOME),
        "e00600": dividend_income,
        "e00650": qualified_dividend_income,
        "p22250": _sum_fact(earners, Concepts.SHORT_TERM_CAPITAL_GAINS),
        "p23250": _sum_fact(earners, Concepts.LONG_TERM_CAPITAL_GAINS),
        "e01500": pension_income,
        "e01700": pension_income,
        "e02000": rental_income,
        "e02300": _sum_fact(earners, Concepts.UNEMPLOYMENT_INSURANCE_INCOME),
        "e02400": _sum_fact(earners, Concepts.SOCIAL_SECURITY_BENEFITS),
        "e18500": _number(case.fact(Concepts.PROPERTY_TAX_PAID, 0)),
        "e19200": _number(case.fact(Concepts.MORTGAGE_INTEREST_PAID, 0)),
        "e32800": _number(case.fact(Concepts.CHILDCARE_EXPENSES, 0)),
        "s006": _number(case.metadata.get("weight", case.fact("weight", 1))),
    }
    return row


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


def _is_eic_qualifying_child(entity: Entity) -> bool:
    age = _age(entity)
    return age < 19 or bool(entity.fact(Concepts.DISABLED, False))


def _mars(*, spouse: Entity | None, dependents: list[Entity]) -> int:
    if spouse is not None:
        return 2
    if any(_hoh_qualifying_dependent(dependent) for dependent in dependents):
        return 4
    return 1


def _hoh_qualifying_dependent(dependent: Entity) -> bool:
    age = _age(dependent)
    if age < 19:
        return True
    return (
        age < _HOH_YOUNG_ADULT_DEPENDENT_AGE_LIMIT
        and _dependent_gross_income(dependent)
        < _HOH_YOUNG_ADULT_DEPENDENT_GROSS_INCOME_LIMIT
    )


def _dependent_gross_income(dependent: Entity) -> float:
    return (
        _number(dependent.fact(Concepts.YEARLY_EARNED_INCOME, 0))
        + max(0, _number(dependent.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0)))
        + _number(dependent.fact(Concepts.DIVIDEND_INCOME, 0))
        + _number(dependent.fact(Concepts.INTEREST_INCOME, 0))
        + _number(dependent.fact(Concepts.SHORT_TERM_CAPITAL_GAINS, 0))
        + _number(dependent.fact(Concepts.LONG_TERM_CAPITAL_GAINS, 0))
        + _number(dependent.fact(Concepts.PENSION_INCOME, 0))
        + _number(dependent.fact(Concepts.UNEMPLOYMENT_INSURANCE_INCOME, 0))
        + max(0, _number(dependent.fact(Concepts.RENTAL_INCOME, 0)))
    )


def _sum_fact(people: list[Entity], concept: str) -> float:
    return sum(_number(person.fact(concept, 0)) for person in people)


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0
    return float(value)


def _year(period: str) -> int:
    return int(str(period).split("-", maxsplit=1)[0])
