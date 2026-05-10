from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity


TAXSIM_MAX_YEAR = 2024

_STATE_FIPS = {
    "AL": 1,
    "AK": 2,
    "AZ": 4,
    "AR": 5,
    "CA": 6,
    "CO": 8,
    "CT": 9,
    "DE": 10,
    "DC": 11,
    "FL": 12,
    "GA": 13,
    "HI": 15,
    "ID": 16,
    "IL": 17,
    "IN": 18,
    "IA": 19,
    "KS": 20,
    "KY": 21,
    "LA": 22,
    "ME": 23,
    "MD": 24,
    "MA": 25,
    "MI": 26,
    "MN": 27,
    "MS": 28,
    "MO": 29,
    "MT": 30,
    "NE": 31,
    "NV": 32,
    "NH": 33,
    "NJ": 34,
    "NM": 35,
    "NY": 36,
    "NC": 37,
    "ND": 38,
    "OH": 39,
    "OK": 40,
    "OR": 41,
    "PA": 42,
    "RI": 44,
    "SC": 45,
    "SD": 46,
    "TN": 47,
    "TX": 48,
    "UT": 49,
    "VT": 50,
    "VA": 51,
    "WA": 53,
    "WV": 54,
    "WI": 55,
    "WY": 56,
}

_STATE_SCOPES = {
    "census_state",
    "census_county",
    "census_place",
    "census_tract",
    "census_block",
    "puma",
}

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

_ZERO_COLUMNS = (
    "psemp",
    "ssemp",
    "dividends",
    "intrec",
    "stcg",
    "ltcg",
    "otherprop",
    "nonprop",
    "pensions",
    "gssi",
    "pui",
    "sui",
    "transfers",
    "rentpaid",
    "proptax",
    "otheritem",
    "childcare",
    "mortgage",
    "scorp",
    "idtl",
)


def attach_taxsim_inputs(cases: list[Case]) -> list[Case]:
    """Attach TAXSIM input rows to cases that do not already carry them."""

    projected = []
    for index, case in enumerate(cases, start=1):
        metadata = dict(case.metadata)
        row = metadata.get("taxsim_input") or case.fact("taxsim_input")
        if row is None:
            row = taxsim_input_for_case(case, taxsimid=index)
        elif not isinstance(row, Mapping):
            raise RuntimeError(
                "Case metadata['taxsim_input'] must be a mapping of TAXSIM "
                "input columns to values."
            )
        metadata["taxsim_input"] = row
        projected.append(replace(case, metadata=metadata))
    return projected


def taxsim_input_for_case(
    case: Case,
    *,
    taxsimid: int | str | None = None,
) -> dict[str, Any]:
    people = _people(case)
    if not people:
        raise RuntimeError("TAXSIM projection requires at least one person entity.")

    head = _head(people)
    spouse = _spouse(people, head)
    dependents = [
        person for person in people if person is not head and person is not spouse
    ]
    dependent_ages = [_age(dependent) for dependent in dependents]
    reported_dependent_ages = dependent_ages[:11]

    row: dict[str, Any] = {
        "taxsimid": taxsimid if taxsimid is not None else case.case_id,
        "year": _year(case.period),
        "state": _state_fips_for_case(case),
        "mstat": 2 if spouse is not None else 1,
        "page": _age(head),
        "sage": _age(spouse) if spouse is not None else 0,
        "depx": len(dependents),
        "dep13": sum(age < 13 for age in dependent_ages),
        "dep17": sum(age < 17 for age in dependent_ages),
        "dep18": sum(age < 18 for age in dependent_ages),
        "pwages": _number(head.fact(Concepts.YEARLY_EARNED_INCOME, 0)),
        "swages": (
            _number(spouse.fact(Concepts.YEARLY_EARNED_INCOME, 0))
            if spouse is not None
            else 0
        ),
    }
    for index, age in enumerate(reported_dependent_ages, start=1):
        row[f"age{index}"] = age
    for column in _ZERO_COLUMNS:
        row.setdefault(column, 0)
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


def _age(entity: Entity) -> int:
    return int(_number(entity.fact(Concepts.PERSON_AGE, 0)))


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0
    return float(value)


def _year(period: str) -> int:
    year = int(str(period).split("-", maxsplit=1)[0])
    if year > TAXSIM_MAX_YEAR:
        raise RuntimeError(
            f"The bundled TAXSIM executable supports tax years through "
            f"{TAXSIM_MAX_YEAR}; got {year}."
        )
    return year


def _state_fips_for_case(case: Case) -> int:
    scope = case.scope
    if scope is not None and scope.type in _STATE_SCOPES:
        return int(scope.geoid[:2])

    for value in (
        case.fact(Concepts.STATE_CODE),
        case.metadata.get("state_fips"),
        case.metadata.get("state_code"),
        case.metadata.get("state"),
    ):
        if value not in (None, ""):
            return _state_fips(value)

    raise RuntimeError(
        "TAXSIM projection requires a state scope, state FIPS, or state code fact."
    )


def _state_fips(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if text.isdigit():
        return int(text)
    if text in _STATE_FIPS:
        return _STATE_FIPS[text]
    raise RuntimeError(f"Unsupported TAXSIM state code: {value!r}")
