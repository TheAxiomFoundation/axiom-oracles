from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ..core.case import Case, Concepts, Entity
from ..core.geography import GeographyScope, normalize_scope, scope_contains


ENHANCED_CPS_DATASET = "enhanced_cps_2024"
NYC_ENHANCED_CPS_DATASET = "hf://policyengine/policyengine-us-data/cities/NYC.h5"


MicrosimulationFactory = Callable[[str], Any]
CaseUnit = Literal["household", "tax_unit"]


def dataset_for_scope(scope: GeographyScope | dict[str, Any] | None) -> str:
    normalized = normalize_scope(scope)
    if normalized == GeographyScope(type="census_place", geoid="3651000"):
        return NYC_ENHANCED_CPS_DATASET
    return ENHANCED_CPS_DATASET


def load_enhanced_cps_cases(
    *,
    scope: GeographyScope | dict[str, Any] | None = None,
    period: str = "2026",
    sample_size: int | None = None,
    dataset: str | None = None,
    case_unit: CaseUnit = "household",
    microsimulation_factory: MicrosimulationFactory | None = None,
) -> list[Case]:
    return EnhancedCpsCaseLoader(
        dataset=dataset,
        microsimulation_factory=microsimulation_factory,
    ).load_cases(
        scope=scope,
        period=period,
        sample_size=sample_size,
        case_unit=case_unit,
    )


@dataclass
class EnhancedCpsCaseLoader:
    dataset: str | None = None
    microsimulation_factory: MicrosimulationFactory | None = None

    def load_cases(
        self,
        *,
        scope: GeographyScope | dict[str, Any] | None = None,
        period: str = "2026",
        sample_size: int | None = None,
        case_unit: CaseUnit = "household",
    ) -> list[Case]:
        if case_unit not in {"household", "tax_unit"}:
            raise ValueError("case_unit must be 'household' or 'tax_unit'.")
        normalized_scope = normalize_scope(scope)
        dataset = self.dataset or dataset_for_scope(normalized_scope)
        sim = self._build_microsimulation(dataset)
        if sample_size:
            sim.subsample(sample_size)

        calculation_period = _year(period)
        households = self._households(sim, calculation_period)
        people_by_household = self._people_by_household(sim, calculation_period)
        cases = []
        for household in households:
            household_scope = household.scope
            if normalized_scope is not None:
                if household_scope is None:
                    continue
                if not scope_contains(normalized_scope, household_scope):
                    continue

            people = people_by_household.get(household.household_id, [])
            if not people:
                continue
            metadata = {
                "population": "enhanced-cps",
                "dataset": dataset,
                "household_weight": household.weight,
                **({"scope": household_scope.as_dict()} if household_scope else {}),
                **_locale_metadata(household_scope),
            }
            if case_unit == "household":
                cases.append(
                    Case(
                        case_id=f"ecps-{household.household_id}",
                        period=period,
                        facts={
                            Concepts.CASH_ON_HAND: 0,
                            Concepts.RENT_PAID: household.housing_cost,
                        },
                        entities=tuple(
                            _person_entity(person, index, case_unit=case_unit)
                            for index, person in enumerate(people)
                        ),
                        metadata=metadata,
                    )
                )
                continue

            people_by_tax_unit: dict[int | str, list[_PersonRow]] = defaultdict(list)
            for person in people:
                people_by_tax_unit[person.tax_unit_id].append(person)
            for tax_unit_id, tax_unit_people in people_by_tax_unit.items():
                cases.append(
                    Case(
                        case_id=f"ecps-tax-unit-{tax_unit_id}",
                        period=period,
                        facts={Concepts.CASH_ON_HAND: 0},
                        entities=tuple(
                            _person_entity(person, index, case_unit=case_unit)
                            for index, person in enumerate(tax_unit_people)
                        ),
                        metadata={
                            **metadata,
                            "case_unit": "tax_unit",
                            "household_id": household.household_id,
                            "tax_unit_id": tax_unit_id,
                        },
                    )
                )
        return cases

    def _build_microsimulation(self, dataset: str):
        if self.microsimulation_factory is not None:
            return self.microsimulation_factory(dataset)
        try:
            import policyengine as pe
        except ImportError as exc:
            raise RuntimeError(
                "Install the PolicyEngine extra: uv pip install -e '.[policyengine]'"
            ) from exc
        if pe.us is None:
            raise RuntimeError(
                "Install the US PolicyEngine extra: uv pip install -e '.[policyengine]'"
            )
        return pe.us.managed_microsimulation(
            dataset=dataset,
            allow_unmanaged=dataset != ENHANCED_CPS_DATASET,
        )

    def _households(self, sim, period: int) -> list["_HouseholdRow"]:
        household_ids = _values(sim.calculate("household_id", period=period))
        size = len(household_ids)
        weights = _calculate_values(sim, "household_weight", period, default=1, size=size)
        state_fips = _calculate_values(sim, "state_fips", period, default="", size=size)
        county_fips = _calculate_values(sim, "county_fips", period, default="", size=size)
        place_fips = _calculate_values(sim, "place_fips", period, default="", size=size)
        # housing_cost is an SPMUnit variable; map_to="household" sums across
        # SPM units per household so the result is one value per household.
        housing_costs = _calculate_values(
            sim,
            "housing_cost",
            period,
            map_to="household",
            default=0,
            size=size,
        )

        return [
            _HouseholdRow(
                household_id=_clean_id(household_id),
                weight=float(_clean_number(weight)),
                scope=_scope_from_geography(state, county, place),
                housing_cost=float(_clean_number(housing_cost)),
            )
            for household_id, weight, state, county, place, housing_cost in zip(
                household_ids,
                weights,
                state_fips,
                county_fips,
                place_fips,
                housing_costs,
                strict=True,
            )
        ]

    def _people_by_household(
        self,
        sim,
        period: int,
    ) -> dict[int | str, list["_PersonRow"]]:
        household_ids = _values(
            sim.calculate("household_id", period=period, map_to="person")
        )
        size = len(household_ids)
        person_ids = _calculate_values(
            sim,
            "person_id",
            period,
            map_to="person",
            default=None,
            size=size,
        )
        tax_unit_ids = _calculate_values(
            sim,
            "tax_unit_id",
            period,
            map_to="person",
            default=None,
            size=size,
        )
        is_tax_unit_head = _calculate_values(
            sim,
            "is_tax_unit_head",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        is_tax_unit_spouse = _calculate_values(
            sim,
            "is_tax_unit_spouse",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        is_tax_unit_dependent = _calculate_values(
            sim,
            "is_tax_unit_dependent",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        ages = _calculate_values(sim, "age", period, map_to="person", default=0, size=size)
        employment_income = _calculate_values(
            sim,
            "employment_income",
            period,
            map_to="person",
            default=0,
            size=size,
        )
        pregnant = _calculate_values(
            sim,
            "is_pregnant",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        disabled = _calculate_values(
            sim,
            "is_disabled",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        blind = _calculate_values(
            sim,
            "is_blind",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        veteran = _calculate_values(
            sim,
            "is_veteran",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        medicaid = _calculate_values(
            sim,
            "has_medicaid_health_coverage_at_interview",
            period,
            map_to="person",
            default=False,
            size=size,
        )
        # Non-wage income variables. Missing variables fall back to 0.
        non_wage_income = {
            concept: _calculate_values(
                sim,
                pe_variable,
                period,
                map_to="person",
                default=0,
                size=size,
            )
            for concept, pe_variable in _PERSON_NON_WAGE_VARIABLES.items()
        }

        people_by_household: dict[int | str, list[_PersonRow]] = defaultdict(list)
        for index, household_id in enumerate(household_ids):
            key = _clean_id(household_id)
            person_id = person_ids[index]
            people_by_household[key].append(
                _PersonRow(
                    person_id=(
                        _clean_id(person_id)
                        if person_id is not None
                        else f"{key}-{len(people_by_household[key])}"
                    ),
                    tax_unit_id=(
                        _clean_id(tax_unit_ids[index])
                        if tax_unit_ids[index] is not None
                        else key
                    ),
                    is_tax_unit_head=bool(is_tax_unit_head[index]),
                    is_tax_unit_spouse=bool(is_tax_unit_spouse[index]),
                    is_tax_unit_dependent=bool(is_tax_unit_dependent[index]),
                    age=int(_clean_number(ages[index])),
                    yearly_earned_income=float(_clean_number(employment_income[index])),
                    pregnant=bool(pregnant[index]),
                    disabled=bool(disabled[index]),
                    blind=bool(blind[index]),
                    veteran=bool(veteran[index]),
                    benefits_medicaid=bool(medicaid[index]),
                    non_wage_income={
                        concept: float(_clean_number(values[index]))
                        for concept, values in non_wage_income.items()
                    },
                )
            )
        return people_by_household


@dataclass(frozen=True)
class _HouseholdRow:
    household_id: int | str
    weight: float
    scope: GeographyScope | None
    housing_cost: float = 0.0


_PERSON_NON_WAGE_VARIABLES = {
    Concepts.DIVIDEND_INCOME: "dividend_income",
    Concepts.QUALIFIED_DIVIDEND_INCOME: "qualified_dividend_income",
    Concepts.INTEREST_INCOME: "taxable_interest_income",
    Concepts.SHORT_TERM_CAPITAL_GAINS: "short_term_capital_gains",
    Concepts.LONG_TERM_CAPITAL_GAINS: "long_term_capital_gains",
    Concepts.PENSION_INCOME: "taxable_pension_income",
    Concepts.SOCIAL_SECURITY_BENEFITS: "social_security",
    Concepts.UNEMPLOYMENT_INSURANCE_INCOME: "unemployment_compensation",
    Concepts.RENTAL_INCOME: "rental_income",
    Concepts.SELF_EMPLOYMENT_INCOME: "self_employment_income",
}


@dataclass(frozen=True)
class _PersonRow:
    person_id: int | str
    tax_unit_id: int | str
    is_tax_unit_head: bool
    is_tax_unit_spouse: bool
    is_tax_unit_dependent: bool
    age: int
    yearly_earned_income: float
    pregnant: bool
    disabled: bool
    blind: bool
    veteran: bool
    benefits_medicaid: bool
    non_wage_income: dict[str, float]


def _person_entity(
    person: _PersonRow,
    index: int,
    *,
    case_unit: CaseUnit,
) -> Entity:
    facts: dict[str, Any] = {
        Concepts.PERSON_AGE: person.age,
        Concepts.HOUSEHOLD_RELATION: _relation_for_person(
            person,
            index,
            case_unit=case_unit,
        ),
        Concepts.YEARLY_EARNED_INCOME: person.yearly_earned_income,
        Concepts.PREGNANT: person.pregnant,
        Concepts.DISABLED: person.disabled,
        Concepts.BLIND: person.blind,
        Concepts.VETERAN: person.veteran,
        Concepts.BENEFITS_MEDICAID: person.benefits_medicaid,
    }
    for concept, value in person.non_wage_income.items():
        if value:
            facts[concept] = value
    return Entity(
        entity_id=f"person-{person.person_id}",
        kind="person",
        facts=facts,
    )


def _relation_for_person(
    person: _PersonRow,
    index: int,
    *,
    case_unit: CaseUnit,
) -> str:
    if case_unit == "tax_unit":
        if person.is_tax_unit_head:
            return "HeadOfHousehold"
        if person.is_tax_unit_spouse:
            return "Spouse"
        if person.is_tax_unit_dependent:
            return "Child" if person.age < 19 else "Dependent"
        return "Other"
    if index == 0:
        return "HeadOfHousehold"
    if person.age < 18:
        return "Child"
    return "Other"


def _calculate_values(
    sim,
    variable: str,
    period: int,
    *,
    map_to: str | None = None,
    default: Any,
    size: int,
) -> list[Any]:
    try:
        kwargs = {"period": period}
        if map_to is not None:
            kwargs["map_to"] = map_to
        value = sim.calculate(variable, **kwargs)
    except TypeError:
        if map_to is not None:
            value = sim.calculate(variable, period=period)
        else:
            raise
    except Exception:
        return [default] * size
    return _values(value)


def _values(value) -> list[Any]:
    raw = value.values if hasattr(value, "values") else value
    return [_clean_value(item) for item in list(raw)]


def _clean_value(value):
    if isinstance(value, bytes):
        return value.decode()
    if hasattr(value, "item"):
        return value.item()
    return value


def _clean_id(value) -> int | str:
    cleaned = _clean_value(value)
    if isinstance(cleaned, float) and cleaned.is_integer():
        return int(cleaned)
    return cleaned


def _clean_number(value) -> float:
    cleaned = _clean_value(value)
    if cleaned in {"", None}:
        return 0
    return float(cleaned)


def _scope_from_geography(
    state_fips: Any,
    county_fips: Any,
    place_fips: Any,
) -> GeographyScope | None:
    state = _clean_code(state_fips, 2, zero_is_missing=True)
    county = _clean_code(county_fips, 5, zero_is_missing=True)
    place = _clean_code(place_fips, 5, zero_is_missing=True)
    if state and place:
        return GeographyScope(type="census_place", geoid=f"{state}{place}")
    if county:
        if state and not county.startswith(state):
            county = f"{state}{county[-3:]}"
        return GeographyScope(type="census_county", geoid=county)
    if state:
        return GeographyScope(type="census_state", geoid=state)
    return None


def _clean_code(value: Any, length: int, *, zero_is_missing: bool = False) -> str:
    cleaned = _clean_value(value)
    if cleaned in {"", "UNKNOWN", None}:
        return ""
    if isinstance(cleaned, float) and cleaned != cleaned:
        return ""
    if isinstance(cleaned, float) and cleaned.is_integer():
        cleaned = int(cleaned)
    if zero_is_missing and str(cleaned).strip() in {"0", "0.0"}:
        return ""
    return str(cleaned).zfill(length)


def _locale_metadata(scope: GeographyScope | None) -> dict[str, str]:
    if scope == GeographyScope(type="census_place", geoid="3651000"):
        return {"locale": "US-NY-NYC"}
    return {}


def _year(period: str | int) -> int:
    return int(str(period).split("-", 1)[0])
