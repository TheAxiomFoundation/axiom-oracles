from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity


TAXSIM_MAX_YEAR = 2026

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

_TAXSIM_STATE_CODES = {
    "AL": 1,
    "AK": 2,
    "AZ": 3,
    "AR": 4,
    "CA": 5,
    "CO": 6,
    "CT": 7,
    "DE": 8,
    "DC": 9,
    "FL": 10,
    "GA": 11,
    "HI": 12,
    "ID": 13,
    "IL": 14,
    "IN": 15,
    "IA": 16,
    "KS": 17,
    "KY": 18,
    "LA": 19,
    "ME": 20,
    "MD": 21,
    "MA": 22,
    "MI": 23,
    "MN": 24,
    "MS": 25,
    "MO": 26,
    "MT": 27,
    "NE": 28,
    "NV": 29,
    "NH": 30,
    "NJ": 31,
    "NM": 32,
    "NY": 33,
    "NC": 34,
    "ND": 35,
    "OH": 36,
    "OK": 37,
    "OR": 38,
    "PA": 39,
    "RI": 40,
    "SC": 41,
    "SD": 42,
    "TN": 43,
    "TX": 44,
    "UT": 45,
    "VT": 46,
    "VA": 47,
    "WA": 48,
    "WV": 49,
    "WI": 50,
    "WY": 51,
}

_USPS_BY_FIPS = {fips: usps for usps, fips in _STATE_FIPS.items()}

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
    "nonprop",
    "transfers",
    "scorp",
)

# Default TAXSIM detail mode. idtl=2 returns the v10..v41 decomposition columns
# (AGI, standard deduction, taxable income, CTC, EITC, AMT, …) used for
# component-level comparisons.
DEFAULT_IDTL = 2


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

    # Household-level inputs are summed across head + spouse for the columns
    # that TAXSIM models at the tax-unit level rather than per-spouse.
    earners = [head] + ([spouse] if spouse is not None else [])

    row: dict[str, Any] = {
        "taxsimid": taxsimid if taxsimid is not None else case.case_id,
        "year": _year(case.period),
        "state": _taxsim_state_for_case(case),
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
        "psemp": _number(head.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0)),
        "ssemp": (
            _number(spouse.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0))
            if spouse is not None
            else 0
        ),
        # TAXSIM's dividends column is qualified-dividend income (taxed at
        # the preferential rate); only the qualified leaf belongs there. The
        # non-qualified remainder rides in otherprop with the other ordinary
        # NIIT-subject property income so AGI stays whole.
        "dividends": _qualified_dividends(earners),
        "intrec": _sum_fact(earners, Concepts.INTEREST_INCOME),
        "stcg": _sum_fact(earners, Concepts.SHORT_TERM_CAPITAL_GAINS),
        "ltcg": _sum_fact(earners, Concepts.LONG_TERM_CAPITAL_GAINS),
        "pensions": _sum_fact(earners, Concepts.PENSION_INCOME),
        # Rental/royalty income flows through TAXSIM's other-property
        # column; zero-filling it depressed TAXSIM AGI on every
        # rental-income unit relative to the axiom side.
        "otherprop": _sum_fact(earners, Concepts.RENTAL_INCOME)
        + _nonqualified_dividends(earners),
        "gssi": _sum_fact(earners, Concepts.SOCIAL_SECURITY_BENEFITS),
        "pui": _number(head.fact(Concepts.UNEMPLOYMENT_INSURANCE_INCOME, 0)),
        "sui": (
            _number(spouse.fact(Concepts.UNEMPLOYMENT_INSURANCE_INCOME, 0))
            if spouse is not None
            else 0
        ),
        "proptax": _number(case.fact(Concepts.PROPERTY_TAX_PAID, 0)),
        "mortgage": _number(case.fact(Concepts.MORTGAGE_INTEREST_PAID, 0)),
        "otheritem": _number(case.fact(Concepts.ITEMIZED_DEDUCTIONS_OTHER, 0)),
        "rentpaid": _number(case.fact(Concepts.RENT_PAID, 0)),
        "childcare": _number(case.fact(Concepts.CHILDCARE_EXPENSES, 0)),
        "idtl": DEFAULT_IDTL,
    }
    for index, age in enumerate(reported_dependent_ages, start=1):
        row[f"age{index}"] = age
    for column in _ZERO_COLUMNS:
        row.setdefault(column, 0)
    return row


def _sum_fact(people: list[Entity], concept: str) -> float:
    return sum(_number(person.fact(concept, 0)) for person in people)


def _qualified_dividends(people: list[Entity]) -> float:
    # Qualified dividends are a subset of total dividends; some ECPS rows
    # carry only the qualified leaf, so cap at the person's larger total.
    return sum(
        min(
            _number(person.fact(Concepts.QUALIFIED_DIVIDEND_INCOME, 0)),
            max(
                _number(person.fact(Concepts.DIVIDEND_INCOME, 0)),
                _number(person.fact(Concepts.QUALIFIED_DIVIDEND_INCOME, 0)),
            ),
        )
        for person in people
    )


def _nonqualified_dividends(people: list[Entity]) -> float:
    return sum(
        max(
            0.0,
            _number(person.fact(Concepts.DIVIDEND_INCOME, 0))
            - _number(person.fact(Concepts.QUALIFIED_DIVIDEND_INCOME, 0)),
        )
        for person in people
    )


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


def _taxsim_state_for_case(case: Case) -> int:
    scope = case.scope
    if scope is not None and scope.type in _STATE_SCOPES:
        return _taxsim_state_from_fips(int(scope.geoid[:2]))

    state_code = case.fact(Concepts.STATE_CODE)
    if state_code not in (None, ""):
        return _taxsim_state_from_usps_or_fips(state_code)
    state_fips = case.metadata.get("state_fips")
    if state_fips not in (None, ""):
        return _taxsim_state_from_fips(int(state_fips))
    for value in (
        case.metadata.get("state_code"),
        case.metadata.get("state"),
    ):
        if value not in (None, ""):
            return _taxsim_state_from_usps_or_fips(value)

    raise RuntimeError(
        "TAXSIM projection requires a state scope, state FIPS, or state code fact."
    )


def _taxsim_state_from_usps_or_fips(value: Any) -> int:
    if isinstance(value, int):
        return _taxsim_state_from_fips(value)
    text = str(value).strip().upper()
    if text.isdigit():
        return _taxsim_state_from_fips(int(text))
    if text in _STATE_FIPS:
        return _TAXSIM_STATE_CODES[text]
    raise RuntimeError(f"Unsupported TAXSIM state code: {value!r}")


def _taxsim_state_from_fips(value: int) -> int:
    usps = _USPS_BY_FIPS.get(value)
    if usps is None:
        raise RuntimeError(f"Unsupported state FIPS code: {value!r}")
    return _TAXSIM_STATE_CODES[usps]
