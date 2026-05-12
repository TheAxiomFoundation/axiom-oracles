from __future__ import annotations

from typing import Any

from ...core.engine import EngineAdapter
from ...core.case import Case, Concepts
from ...core.geography import pe_inputs_for_scope
from ...core.household import Household
from ...core.results import EngineResult
from ...comparison.mappings import engine_targets_for_concepts


_PERSON_INCOME_CONCEPT_TO_PE = {
    Concepts.DIVIDEND_INCOME: "dividend_income",
    Concepts.INTEREST_INCOME: "interest_income",
    Concepts.SHORT_TERM_CAPITAL_GAINS: "short_term_capital_gains",
    Concepts.LONG_TERM_CAPITAL_GAINS: "long_term_capital_gains",
    Concepts.PENSION_INCOME: "taxable_pension_income",
    Concepts.SOCIAL_SECURITY_BENEFITS: "social_security",
    Concepts.UNEMPLOYMENT_INSURANCE_INCOME: "unemployment_compensation",
    Concepts.RENTAL_INCOME: "rental_income",
    Concepts.SELF_EMPLOYMENT_INCOME: "self_employment_income",
}

_TAX_UNIT_CONCEPT_TO_PE = {
    Concepts.PROPERTY_TAX_PAID: "real_estate_taxes",
    Concepts.MORTGAGE_INTEREST_PAID: "deductible_mortgage_interest",
    Concepts.ITEMIZED_DEDUCTIONS_OTHER: "misc_deduction",
    Concepts.CHILDCARE_EXPENSES: "tax_unit_childcare_expenses",
}


class PolicyEngineRunner(EngineAdapter):
    name = "policyengine"

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        if variables is None:
            variables = [
                "snap",
                "tanf",
                "medicaid",
                "basic_health_program",
                "wic",
                "head_start",
                "early_head_start",
                "ccdf",
                "eitc",
                "ctc",
                "cdcc",
                "liheap",
            ]

        return [self.run_household(household, variables) for household in households]

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        results = []
        for case in cases:
            output_concepts = variables or list(case.outputs)
            pe_variables = engine_targets_for_concepts(
                output_concepts,
                self.name,
            )
            results.append(self.run_case(case, pe_variables))
        return results

    def run_case(self, case: Case, variables: list[str]) -> EngineResult:
        try:
            from policyengine_us import Simulation
        except ImportError as exc:
            raise RuntimeError(
                "Install the PolicyEngine extra: uv pip install -e '.[policyengine]'"
            ) from exc

        simulation = Simulation(situation=self._build_situation_from_case(case))
        values = {}
        errors = []
        for variable in variables:
            try:
                period = self._calculation_period(
                    simulation,
                    variable,
                    str(case.period),
                )
                calculated = simulation.calculate(variable, period)
                values[variable] = self._coerce_value(calculated)
            except Exception as exc:  # pragma: no cover - depends on PE variable set
                errors.append(f"{variable}: {exc}")

        return EngineResult(
            engine=self.name,
            household_id=case.case_id,
            values=values,
            errors=tuple(errors),
        )

    def run_household(
        self,
        household: Household,
        variables: list[str],
    ) -> EngineResult:
        try:
            from policyengine_us import Simulation
        except ImportError as exc:
            raise RuntimeError(
                "Install the PolicyEngine extra: uv pip install -e '.[policyengine]'"
            ) from exc

        simulation = Simulation(situation=self._build_situation(household))
        values = {}
        errors = []
        for variable in variables:
            try:
                calculated = simulation.calculate(variable, household.year)
                values[variable] = self._coerce_value(calculated)
            except Exception as exc:  # pragma: no cover - depends on PE variable set
                errors.append(f"{variable}: {exc}")

        return EngineResult(
            engine=self.name,
            household_id=household.household_id,
            values=values,
            errors=tuple(errors),
        )

    def _build_situation(self, household: Household) -> dict:
        year = household.year
        people = {}
        person_names = []
        for index, person in enumerate(household.people):
            person_name = f"person_{index}"
            person_names.append(person_name)
            people[person_name] = {
                "age": {year: person.age},
                "employment_income": {year: person.yearly_earned_income},
                "is_pregnant": {year: person.pregnant},
                "is_disabled": {year: person.disabled},
                "is_blind": {year: person.blind},
            }

        household_inputs = {
            "members": person_names,
            "state_code": {year: household.state},
        }
        if household.county_fips:
            household_inputs["county_fips"] = {year: household.county_fips}
            household_inputs["state_fips"] = {year: int(household.county_fips[:2])}

        return {
            "people": people,
            "families": {"family": {"members": person_names}},
            "tax_units": {"tax_unit": {"members": person_names}},
            "spm_units": {"spm_unit": {"members": person_names}},
            "households": {"household": household_inputs},
        }

    def _build_situation_from_case(self, case: Case) -> dict:
        year = int(str(case.period).split("-", 1)[0])
        people = {}
        person_names = []
        for index, entity in enumerate(case.entities_of_kind("person")):
            person_name = entity.entity_id or f"person_{index}"
            person_names.append(person_name)
            person_inputs = {
                "age": {year: int(entity.fact(Concepts.PERSON_AGE, 0) or 0)},
                "employment_income": {
                    year: float(entity.fact(Concepts.YEARLY_EARNED_INCOME, 0) or 0)
                },
                "is_pregnant": {year: bool(entity.fact(Concepts.PREGNANT, False))},
                "is_disabled": {year: bool(entity.fact(Concepts.DISABLED, False))},
                "is_blind": {year: bool(entity.fact(Concepts.BLIND, False))},
            }
            for concept, pe_variable in _PERSON_INCOME_CONCEPT_TO_PE.items():
                value = entity.fact(concept)
                if value is not None:
                    person_inputs[pe_variable] = {year: float(value)}
            people[person_name] = person_inputs

        household_inputs = {"members": person_names}
        state_code = case.fact(Concepts.STATE_CODE)
        if state_code is not None:
            household_inputs["state_code"] = {year: str(state_code)}
        for variable, value in pe_inputs_for_scope(case.scope).items():
            household_inputs[variable] = {year: value}

        tax_unit_inputs: dict[str, Any] = {"members": person_names}
        for concept, pe_variable in _TAX_UNIT_CONCEPT_TO_PE.items():
            value = case.fact(concept)
            if value is not None:
                tax_unit_inputs[pe_variable] = {year: float(value)}

        return {
            "people": people,
            "families": {"family": {"members": person_names}},
            "tax_units": {"tax_unit": tax_unit_inputs},
            "spm_units": {"spm_unit": {"members": person_names}},
            "households": {"household": household_inputs},
        }

    @staticmethod
    def _calculation_period(simulation, variable: str, requested_period: str) -> str:
        if "-" not in requested_period:
            return requested_period
        tax_benefit_system = getattr(simulation, "tax_benefit_system", None)
        variables = getattr(tax_benefit_system, "variables", {})
        variable_definition = (
            variables.get(variable) if hasattr(variables, "get") else None
        )
        definition_period = getattr(variable_definition, "definition_period", None)
        if str(definition_period) == "year":
            return requested_period.split("-", maxsplit=1)[0]
        return requested_period

    @staticmethod
    def _coerce_value(value) -> float | bool:
        import numpy as np

        array = np.asarray(value)
        if array.dtype == bool:
            return bool(array.any())
        number = float(np.nan_to_num(array, nan=0).sum())
        return number
