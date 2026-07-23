from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity

# The PRD R package resolves rule years through 2025; requesting 2026
# returns the 2025 parameter vintage unchanged (verified empirically against
# the pinned package — see prd_pins.json). The projection therefore accepts
# 2026 periods (the repo-wide validation year) and comparisons treat PRD's
# output as its latest 2025 vintage in dispositions.
PRD_MAX_GENUINE_RULE_YEAR = 2025

_SPOUSE_RELATIONS = {
    "spouse",
    "wife",
    "husband",
    "partner",
    "marriedpartner",
    "married_partner",
}


def attach_prd_inputs(cases: list[Case]) -> list[Case]:
    """Attach PRD emulator households to cases that do not already carry them.

    The Atlanta Fed PRD is driven through the local policyengine-prd
    emulator, whose ``Household``/``Person`` schema is the canonical input
    the R package's ``create_synthetic_families`` receives. Projection is
    thin: ages, per-person earned income, state FIPS, marriage, tenure,
    cash assets, investment income, and disability/blind flags — the same
    Case concepts the TAXSIM projection reads.
    """

    projected = []
    for index, case in enumerate(cases, start=1):
        metadata = dict(case.metadata)
        household = metadata.get("prd_household") or case.fact("prd_household")
        if household is None:
            household = prd_household_for_case(case, household_id=index)
        metadata["prd_household"] = household
        projected.append(replace(case, metadata=metadata))
    return projected


def prd_household_for_case(case: Case, *, household_id: int) -> dict[str, Any]:
    """Project a thin case into a JSON-serializable PRD household spec.

    A plain mapping (not the emulator's ``Household`` dataclass) so the case
    metadata stays serializable in comparison reports; the runner constructs
    the emulator object lazily via :func:`build_emulator_household`.
    """

    people = _people(case)
    if not people:
        raise RuntimeError("PRD projection requires at least one person entity.")

    spouse_present = any(
        _relation(person) in _SPOUSE_RELATIONS for person in people
    )
    members = []
    for i, person in enumerate(people):
        members.append(
            {
                "age": int(_number(person.fact(Concepts.PERSON_AGE, 0))),
                "employment_income": _number(
                    person.fact(Concepts.YEARLY_EARNED_INCOME, 0)
                ),
                "self_employment_income": _number(
                    person.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0)
                ),
                "investment_income": _investment_income(person),
                "social_security_income": _number(
                    person.fact(Concepts.SOCIAL_SECURITY_BENEFITS, 0)
                ),
                "is_disabled": bool(person.fact(Concepts.DISABLED, False)),
                "is_blind": bool(person.fact(Concepts.BLIND, False)),
                "is_tax_unit_head": i == 0,
                "is_tax_unit_spouse": (
                    i > 0 and _relation(person) in _SPOUSE_RELATIONS
                ),
            }
        )

    return {
        "household_id": household_id,
        "state_fips": _state_fips(case),
        "year": _year(case.period),
        "members": members,
        "is_married": spouse_present,
        "is_renter": bool(case.fact(Concepts.LIVING_RENTING, True)),
        "cash_assets": _number(case.fact(Concepts.CASH_ON_HAND, 0)),
    }


def build_emulator_household(spec: Any) -> Any:
    """Construct the emulator ``Household`` from a projected spec mapping.

    Passes through objects that already look like emulator households (the
    external-injection path used by tests and callers that build their own).
    """

    if not isinstance(spec, Mapping):
        return spec
    from policyengine_prd.core.household import Household, Person

    fields = dict(spec)
    members = [Person(**member) for member in fields.pop("members", [])]
    return Household(members=members, **fields)


def _investment_income(person: Entity) -> float:
    return sum(
        _number(person.fact(concept, 0))
        for concept in (
            Concepts.DIVIDEND_INCOME,
            Concepts.INTEREST_INCOME,
            Concepts.RENTAL_INCOME,
        )
    )


def _people(case: Case) -> list[Entity]:
    return [
        entity
        for entity in case.entities
        if str(entity.kind).lower().replace("_", "-") == "person"
    ]


def _relation(entity: Entity) -> str:
    return (
        str(entity.fact(Concepts.HOUSEHOLD_RELATION, ""))
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, Mapping):
        return 0.0
    return float(value)


def _year(period: str) -> int:
    return int(str(period).split("-", maxsplit=1)[0])


def _state_fips(case: Case) -> int:
    scope = case.scope
    if scope is not None and getattr(scope, "geoid", None):
        geoid = str(scope.geoid)
        if geoid[:2].isdigit():
            return int(geoid[:2])
    state_fips = case.metadata.get("state_fips")
    if state_fips not in (None, ""):
        return int(state_fips)
    raise RuntimeError(
        "PRD projection requires a state scope or state_fips metadata."
    )
