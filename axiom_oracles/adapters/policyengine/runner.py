from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

from ...core.engine import EngineAdapter
from ...core.case import Case, Concepts, Entity
from ...core.geography import pe_inputs_for_scope
from ...core.household import Household
from ...core.results import EngineResult
from ...comparison.mappings import engine_targets_for_concepts


_SCOPE_FREE_FEDERAL_TAX_VARIABLES = {
    "auto_loan_interest_deduction",
    "charitable_deduction_for_non_itemizers",
    "overtime_income_deduction",
    "qualified_business_income_deduction",
    "tip_income_deduction",
}

_STATE_SCOPE_FEDERAL_TAX_VARIABLES = {
    "adjusted_gross_income",
    "irs_gross_income",
    "itemized_taxable_income_deductions",
}

_MONTHLY_NUMERIC_OUTPUT_VARIABLES = {
    "snap",
    "snap_max_allotment",
    "snap_min_allotment",
    "snap_normal_allotment",
}

_MISSING_REQUESTED_PERIOD_VALUE = object()

_PERSON_INCOME_CONCEPT_TO_PE = {
    Concepts.DIVIDEND_INCOME: "dividend_income",
    Concepts.QUALIFIED_DIVIDEND_INCOME: "qualified_dividend_income",
    Concepts.INTEREST_INCOME: "taxable_interest_income",
    Concepts.SHORT_TERM_CAPITAL_GAINS: "short_term_capital_gains",
    Concepts.LONG_TERM_CAPITAL_GAINS: "long_term_capital_gains",
    Concepts.PENSION_INCOME: "taxable_pension_income",
    Concepts.SSI_BENEFITS: "ssi",
    Concepts.SOCIAL_SECURITY_BENEFITS: "social_security",
    Concepts.UNEMPLOYMENT_INSURANCE_INCOME: "unemployment_compensation",
    Concepts.RENTAL_INCOME: "rental_income",
    Concepts.SELF_EMPLOYMENT_INCOME: "self_employment_income",
}

_PERSON_CASE_CONCEPT_TO_PE = {
    Concepts.PROPERTY_TAX_PAID: "real_estate_taxes",
    Concepts.MORTGAGE_INTEREST_PAID: "deductible_mortgage_interest",
    Concepts.RENT_PAID: "pre_subsidy_rent",
}

_TAX_UNIT_CONCEPT_TO_PE = {
    Concepts.ITEMIZED_DEDUCTIONS_OTHER: "misc_deduction",
    Concepts.CHILDCARE_EXPENSES: "tax_unit_childcare_expenses",
}

_SPM_UNIT_CASE_CONCEPT_TO_PE = {
    Concepts.RENT_PAID: "housing_cost",
}

_TAX_FILER_ADULT_AGE = 18

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

_DEPENDENT_RELATIONS = {
    "child",
    "daughter",
    "dependent",
    "foster_child",
    "grandchild",
    "son",
    "stepchild",
}


def _policyengine():
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
    return pe


class PolicyEngineRunner(EngineAdapter):
    name = "policyengine"

    def __init__(self, *, batch_size: int = 5_000) -> None:
        self.batch_size = batch_size

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
        if not cases:
            return []

        requested = (
            tuple(variables) if variables is not None else tuple(cases[0].outputs)
        )
        pe_variables = self._policyengine_variables(requested)
        if not pe_variables:
            return [
                EngineResult(engine=self.name, household_id=case.case_id, values={})
                for case in cases
            ]

        if variables is None:
            case_outputs = {tuple(case.outputs) for case in cases}
            if len(case_outputs) != 1:
                return [
                    self.run_case(
                        case,
                        self._policyengine_variables(tuple(case.outputs)),
                    )
                    for case in cases
                ]

        periods = {str(case.period) for case in cases}
        if len(periods) != 1:
            return [self.run_case(case, pe_variables) for case in cases]

        results: list[EngineResult] = []
        for start in range(0, len(cases), self.batch_size):
            batch = cases[start : start + self.batch_size]
            results.extend(self._run_case_batch(batch, pe_variables))
        return results

    def run_case(self, case: Case, variables: list[str]) -> EngineResult:
        pe = _policyengine()
        values = {}
        errors = []
        household_input = self._build_household_calculator_input_from_case(
            case,
            variables=variables,
        )
        try:
            result = pe.us.calculate_household(
                **household_input,
                extra_variables=variables,
            )
            annual_values = {
                variable: _household_result_value(result, variable)
                for variable in variables
            }
            requested_values = self._requested_period_values(
                pe,
                [case],
                [annual_values],
            )[0]
            values = {
                variable: _normalize_value_for_requested_period(
                    pe,
                    variable,
                    str(case.period),
                    annual_values[variable],
                    requested_value=requested_values.get(
                        variable,
                        _MISSING_REQUESTED_PERIOD_VALUE,
                    ),
                )
                for variable in variables
            }
        except Exception:
            for variable in variables:
                try:
                    result = pe.us.calculate_household(
                        **household_input,
                        extra_variables=[variable],
                    )
                    annual_value = _household_result_value(result, variable)
                    requested_values = self._requested_period_values(
                        pe,
                        [case],
                        [{variable: annual_value}],
                    )[0]
                    values[variable] = _normalize_value_for_requested_period(
                        pe,
                        variable,
                        str(case.period),
                        annual_value,
                        requested_value=requested_values.get(
                            variable,
                            _MISSING_REQUESTED_PERIOD_VALUE,
                        ),
                    )
                except (
                    Exception
                ) as exc:  # pragma: no cover - depends on PE variable set
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
        pe = _policyengine()
        values = {}
        errors = []
        household_input = self._build_household_calculator_input(household)
        try:
            result = pe.us.calculate_household(
                **household_input,
                extra_variables=variables,
            )
            values = {
                variable: _household_result_value(result, variable)
                for variable in variables
            }
        except Exception:
            for variable in variables:
                try:
                    result = pe.us.calculate_household(
                        **household_input,
                        extra_variables=[variable],
                    )
                    values[variable] = _household_result_value(result, variable)
                except (
                    Exception
                ) as exc:  # pragma: no cover - depends on PE variable set
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
            "marital_units": {"marital_unit": {"members": person_names}},
            "families": {"family": {"members": person_names}},
            "tax_units": {"tax_unit": {"members": person_names}},
            "spm_units": {"spm_unit": {"members": person_names}},
            "households": {"household": household_inputs},
        }

    def _build_household_calculator_input(self, household: Household) -> dict[str, Any]:
        people = [
            {
                "age": person.age,
                "employment_income": person.yearly_earned_income,
                "is_pregnant": person.pregnant,
                "is_disabled": person.disabled,
                "is_blind": person.blind,
            }
            for person in household.people
        ]
        household_inputs: dict[str, Any] = {"state_code": household.state}
        if household.county_fips:
            household_inputs["county_fips"] = household.county_fips
            household_inputs["state_fips"] = int(household.county_fips[:2])
        return {
            "people": people,
            "family": {},
            "spm_unit": {},
            "tax_unit": {},
            "household": household_inputs,
            "year": household.year,
        }

    def _build_situation_from_case(
        self,
        case: Case,
        variables: list[str] | None = None,
    ) -> dict:
        year = int(str(case.period).split("-", 1)[0])
        people = {}
        person_names = []
        person_entities = list(case.entities_of_kind("person"))
        head, spouse = _tax_filers(person_entities)
        for index, entity in enumerate(person_entities):
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
                "is_tax_unit_head": {year: entity is head},
                "is_tax_unit_spouse": {year: entity is spouse},
            }
            for pe_variable, value in _person_income_inputs(entity).items():
                person_inputs[pe_variable] = {year: value}
            if entity is head:
                for concept, pe_variable in _PERSON_CASE_CONCEPT_TO_PE.items():
                    value = case.fact(concept)
                    if value is not None:
                        person_inputs[pe_variable] = {year: float(value)}
            people[person_name] = person_inputs

        household_inputs = {"members": person_names}
        state_code = case.fact(Concepts.STATE_CODE)
        if state_code is not None:
            household_inputs["state_code"] = {year: str(state_code)}
        scope_inputs = _scope_inputs_for_variables(case, variables)
        if scope_inputs:
            for variable, value in scope_inputs.items():
                household_inputs[variable] = {year: value}

        tax_unit_inputs: dict[str, Any] = {"members": person_names}
        for concept, pe_variable in _TAX_UNIT_CONCEPT_TO_PE.items():
            value = case.fact(concept)
            if value is not None:
                tax_unit_inputs[pe_variable] = {year: float(value)}

        spm_unit_inputs: dict[str, Any] = {"members": person_names}
        for concept, pe_variable in _SPM_UNIT_CASE_CONCEPT_TO_PE.items():
            value = case.fact(concept)
            if value is not None:
                spm_unit_inputs[pe_variable] = {year: float(value)}

        return {
            "people": people,
            "marital_units": {"marital_unit": {"members": person_names}},
            "families": {"family": {"members": person_names}},
            "tax_units": {"tax_unit": tax_unit_inputs},
            "spm_units": {"spm_unit": spm_unit_inputs},
            "households": {"household": household_inputs},
        }

    def _build_household_calculator_input_from_case(
        self,
        case: Case,
        variables: list[str] | None = None,
    ) -> dict[str, Any]:
        year = int(str(case.period).split("-", 1)[0])
        person_entities = list(case.entities_of_kind("person"))
        head, spouse = _tax_filers(person_entities)
        people = []
        for entity in person_entities:
            person_inputs = {
                "age": int(entity.fact(Concepts.PERSON_AGE, 0) or 0),
                "employment_income": float(
                    entity.fact(Concepts.YEARLY_EARNED_INCOME, 0) or 0
                ),
                "is_pregnant": bool(entity.fact(Concepts.PREGNANT, False)),
                "is_disabled": bool(entity.fact(Concepts.DISABLED, False)),
                "is_blind": bool(entity.fact(Concepts.BLIND, False)),
                "is_tax_unit_head": entity is head,
                "is_tax_unit_spouse": entity is spouse,
            }
            person_inputs.update(_person_income_inputs(entity))
            if entity is head:
                for concept, pe_variable in _PERSON_CASE_CONCEPT_TO_PE.items():
                    value = case.fact(concept)
                    if value is not None:
                        person_inputs[pe_variable] = float(value)
            people.append(person_inputs)

        household_inputs: dict[str, Any] = {}
        state_code = case.fact(Concepts.STATE_CODE)
        if state_code is not None:
            household_inputs["state_code"] = str(state_code)
        for variable, value in _scope_inputs_for_variables(case, variables).items():
            household_inputs[variable] = value

        tax_unit_inputs: dict[str, Any] = {}
        for concept, pe_variable in _TAX_UNIT_CONCEPT_TO_PE.items():
            value = case.fact(concept)
            if value is not None:
                tax_unit_inputs[pe_variable] = float(value)

        spm_unit_inputs: dict[str, Any] = {}
        for concept, pe_variable in _SPM_UNIT_CASE_CONCEPT_TO_PE.items():
            value = case.fact(concept)
            if value is not None:
                spm_unit_inputs[pe_variable] = float(value)

        return {
            "people": people,
            "family": {},
            "spm_unit": spm_unit_inputs,
            "tax_unit": tax_unit_inputs,
            "household": household_inputs,
            "year": year,
        }

    def _build_situation_from_cases(
        self,
        cases: Sequence[Case],
        variables: list[str] | None = None,
    ) -> dict:
        situation: dict[str, dict[str, dict]] = {
            "people": {},
            "marital_units": {},
            "families": {},
            "tax_units": {},
            "spm_units": {},
            "households": {},
        }
        for case_index, case in enumerate(cases):
            case_situation = self._build_situation_from_case(case, variables=variables)
            prefix = f"case_{case_index}"
            for entity_kind, entities in case_situation.items():
                for entity_id, entity_data in entities.items():
                    namespaced_id = _namespaced_entity_id(prefix, entity_id)
                    namespaced_data = dict(entity_data)
                    if "members" in namespaced_data:
                        namespaced_data["members"] = [
                            _namespaced_entity_id(prefix, member)
                            for member in namespaced_data["members"]
                        ]
                    situation[entity_kind][namespaced_id] = namespaced_data
        return situation

    def _run_case_batch(
        self,
        cases: Sequence[Case],
        variables: list[str],
    ) -> list[EngineResult]:
        try:
            return self._run_case_batch_once(cases, variables)
        except RuntimeError:
            raise
        except Exception:
            if len(cases) == 1:
                return [self.run_case(cases[0], variables)]
            midpoint = len(cases) // 2
            return [
                *self._run_case_batch(cases[:midpoint], variables),
                *self._run_case_batch(cases[midpoint:], variables),
            ]

    def _run_case_batch_once(
        self,
        cases: Sequence[Case],
        variables: list[str],
    ) -> list[EngineResult]:
        import tempfile
        from pathlib import Path

        import pandas as pd
        from microdf import MicroDataFrame

        pe = _policyengine()
        year = int(str(cases[0].period).split("-", 1)[0])
        (
            person_rows,
            household_rows,
            marital_unit_rows,
            family_rows,
            spm_unit_rows,
            tax_unit_rows,
            entity_ids_by_case,
        ) = self._policyengine_dataset_rows(cases, variables)
        household_rows = sorted(household_rows, key=lambda row: row["household_id"])
        marital_unit_rows = sorted(
            marital_unit_rows,
            key=lambda row: row["marital_unit_id"],
        )
        family_rows = sorted(family_rows, key=lambda row: row["family_id"])
        spm_unit_rows = sorted(spm_unit_rows, key=lambda row: row["spm_unit_id"])
        tax_unit_rows = sorted(tax_unit_rows, key=lambda row: row["tax_unit_id"])
        extra_variables = _extra_variables_by_entity(pe, variables)

        with tempfile.TemporaryDirectory(prefix="axiom-oracles-pe-") as directory:
            dataset = pe.us.PolicyEngineUSDataset(
                id="axiom-oracles-batch",
                name="axiom-oracles-batch",
                description="Axiom oracle batch generated through policyengine.py",
                filepath=str(Path(directory) / "input.h5"),
                year=year,
                data=pe.us.USYearData(
                    person=MicroDataFrame(
                        pd.DataFrame(person_rows),
                        weights="person_weight",
                    ),
                    household=MicroDataFrame(
                        pd.DataFrame(household_rows),
                        weights="household_weight",
                    ),
                    marital_unit=MicroDataFrame(
                        pd.DataFrame(marital_unit_rows),
                        weights="marital_unit_weight",
                    ),
                    family=MicroDataFrame(
                        pd.DataFrame(family_rows),
                        weights="family_weight",
                    ),
                    spm_unit=MicroDataFrame(
                        pd.DataFrame(spm_unit_rows),
                        weights="spm_unit_weight",
                    ),
                    tax_unit=MicroDataFrame(
                        pd.DataFrame(tax_unit_rows),
                        weights="tax_unit_weight",
                    ),
                ),
            )
            simulation = pe.Simulation(
                dataset=dataset,
                tax_benefit_model_version=pe.us.model,
                extra_variables=extra_variables,
            )
            simulation.run()
            output = simulation.output_dataset.data

        frames = {
            "person": pd.DataFrame(output.person),
            "household": pd.DataFrame(output.household),
            "marital_unit": pd.DataFrame(output.marital_unit),
            "family": pd.DataFrame(output.family),
            "spm_unit": pd.DataFrame(output.spm_unit),
            "tax_unit": pd.DataFrame(output.tax_unit),
        }
        annual_values_by_case: list[dict[str, float | bool]] = []
        for case_index, _case in enumerate(cases):
            case_values = {}
            for variable in variables:
                entity = _variable_entity(pe, variable)
                frame = frames[entity]
                id_column = f"{entity}_id"
                entity_ids = entity_ids_by_case[case_index][entity]
                rows = frame[frame[id_column].isin(entity_ids)]
                if variable not in rows:
                    raise KeyError(variable)
                case_values[variable] = self._coerce_value(rows[variable].to_numpy())
            annual_values_by_case.append(case_values)

        requested_values_by_case = self._requested_period_values(
            pe,
            cases,
            annual_values_by_case,
        )
        values_by_case: list[dict[str, float | bool]] = []
        for case_index, _case in enumerate(cases):
            case_values = {}
            for variable in variables:
                case_values[variable] = _normalize_value_for_requested_period(
                    pe,
                    variable,
                    str(_case.period),
                    annual_values_by_case[case_index][variable],
                    requested_value=requested_values_by_case[case_index].get(
                        variable,
                        _MISSING_REQUESTED_PERIOD_VALUE,
                    ),
                )
            values_by_case.append(case_values)

        return [
            EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values=values_by_case[index],
            )
            for index, case in enumerate(cases)
        ]

    def _requested_period_values(
        self,
        pe,
        cases: Sequence[Case],
        annual_values_by_case: Sequence[Mapping[str, float | bool]],
    ) -> list[dict[str, float | bool]]:
        """Calculate month-defined numeric outputs at the requested month.

        PolicyEngine's high-level output dataset stores month-defined variables
        as annual sums. Its native situation simulation retains the monthly
        periods, so use that simulation to validate month definitions and
        calculate the exact requested month.
        """
        requested_values: list[dict[str, float | bool]] = [{} for _case in cases]
        if not cases:
            return requested_values

        requested_period = str(cases[0].period)
        if "-" not in requested_period:
            return requested_values

        variables = list(annual_values_by_case[0])
        candidates = [
            variable
            for variable in variables
            if not _policyengine_variable_is_boolean(
                pe,
                variable,
                annual_values_by_case[0][variable],
            )
            and _policyengine_definition_period(pe, variable) == "month"
        ]
        if not candidates:
            return requested_values

        try:
            simulation = _policyengine_us_simulation(
                self._build_situation_from_cases(cases, variables=variables)
            )
        except Exception as exc:
            names = ", ".join(repr(variable) for variable in candidates)
            raise RuntimeError(
                "PolicyEngine could not create a direct requested-period "
                f"simulation for {requested_period!r} ({names}); refusing to "
                "derive month values from annual output-dataset sums"
            ) from exc

        import numpy as np

        case_indices_by_entity: dict[str, list[list[int]]] = {}
        for variable in candidates:
            try:
                definition = _simulation_variable_definition(simulation, variable)
                definition_period = str(
                    getattr(definition, "definition_period", "")
                ).lower()
                entity = _simulation_variable_entity(definition)
                if not entity:
                    entity = _variable_entity(pe, variable)
            except Exception as exc:
                raise RuntimeError(
                    "PolicyEngine could not inspect month-defined variable "
                    f"{variable!r} for requested period {requested_period!r}; "
                    "refusing to derive it from the annual output-dataset sum"
                ) from exc

            if definition_period == "year":
                continue
            if definition_period != "month":
                fallback_period = _policyengine_definition_period(pe, variable)
                if fallback_period != "month":
                    continue

            try:
                raw_values = np.asarray(
                    simulation.calculate(variable, period=requested_period)
                )
                population = simulation.populations[entity]
                entity_ids = [str(item) for item in population.ids]
            except Exception as exc:
                raise RuntimeError(
                    "PolicyEngine could not calculate month-defined variable "
                    f"{variable!r} for requested period {requested_period!r}; "
                    "refusing to derive it from the annual output-dataset sum"
                ) from exc

            if raw_values.size != len(entity_ids):
                raise RuntimeError(
                    "PolicyEngine returned "
                    f"{raw_values.size} values for month-defined variable "
                    f"{variable!r} at {requested_period!r}, but its {entity!r} "
                    f"population has {len(entity_ids)} entities"
                )

            if entity not in case_indices_by_entity:
                case_indices = [[] for _case in cases]
                for entity_index, entity_id in enumerate(entity_ids):
                    prefix, separator, _original_id = entity_id.partition("__")
                    if not separator or not prefix.startswith("case_"):
                        continue
                    try:
                        case_index = int(prefix.removeprefix("case_"))
                    except ValueError:
                        continue
                    if 0 <= case_index < len(cases):
                        case_indices[case_index].append(entity_index)
                case_indices_by_entity[entity] = case_indices

            for case_index, indices in enumerate(case_indices_by_entity[entity]):
                if not indices:
                    raise RuntimeError(
                        "PolicyEngine returned no "
                        f"{entity!r} value for case {case_index} while "
                        f"calculating month-defined variable {variable!r} at "
                        f"{requested_period!r}"
                    )
                requested_values[case_index][variable] = self._coerce_value(
                    raw_values[indices]
                )

        return requested_values

    def _policyengine_dataset_rows(
        self,
        cases: Sequence[Case],
        variables: list[str],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, list[str]]],
    ]:
        person_rows: list[dict[str, Any]] = []
        household_rows: list[dict[str, Any]] = []
        marital_unit_rows: list[dict[str, Any]] = []
        family_rows: list[dict[str, Any]] = []
        spm_unit_rows: list[dict[str, Any]] = []
        tax_unit_rows: list[dict[str, Any]] = []
        entity_ids_by_case: list[dict[str, list[str]]] = []

        for case_index, case in enumerate(cases):
            prefix = f"case_{case_index}"
            household_id = _namespaced_entity_id(prefix, "household")
            marital_unit_id = _namespaced_entity_id(prefix, "marital_unit")
            family_id = _namespaced_entity_id(prefix, "family")
            spm_unit_id = _namespaced_entity_id(prefix, "spm_unit")
            tax_unit_id = _namespaced_entity_id(prefix, "tax_unit")
            weight = float(case.metadata.get("household_weight", 1) or 1)
            household_row: dict[str, Any] = {
                "household_id": household_id,
                "household_weight": weight,
            }
            state_code = case.fact(Concepts.STATE_CODE)
            if state_code is not None:
                household_row["state_code"] = str(state_code)
            household_row.update(_scope_inputs_for_variables(case, variables))
            household_rows.append(household_row)
            marital_unit_rows.append(
                {"marital_unit_id": marital_unit_id, "marital_unit_weight": weight}
            )
            family_rows.append({"family_id": family_id, "family_weight": weight})
            spm_unit_row: dict[str, Any] = {
                "spm_unit_id": spm_unit_id,
                "spm_unit_weight": weight,
            }
            for pe_variable in _SPM_UNIT_CASE_CONCEPT_TO_PE.values():
                spm_unit_row[pe_variable] = 0
            for concept, pe_variable in _SPM_UNIT_CASE_CONCEPT_TO_PE.items():
                value = case.fact(concept)
                if value is not None:
                    spm_unit_row[pe_variable] = float(value)
            spm_unit_rows.append(spm_unit_row)
            tax_unit_row: dict[str, Any] = {
                "tax_unit_id": tax_unit_id,
                "tax_unit_weight": weight,
            }
            for pe_variable in _TAX_UNIT_CONCEPT_TO_PE.values():
                tax_unit_row[pe_variable] = 0
            for concept, pe_variable in _TAX_UNIT_CONCEPT_TO_PE.items():
                value = case.fact(concept)
                if value is not None:
                    tax_unit_row[pe_variable] = float(value)
            tax_unit_rows.append(tax_unit_row)

            person_ids = []
            person_entities = list(case.entities_of_kind("person"))
            head, spouse = _tax_filers(person_entities)
            for person_index, entity in enumerate(person_entities):
                person_id = _namespaced_entity_id(
                    prefix,
                    entity.entity_id or f"person_{person_index}",
                )
                person_ids.append(person_id)
                employment_income = float(
                    entity.fact(Concepts.YEARLY_EARNED_INCOME, 0) or 0
                )
                self_employment_income = float(
                    entity.fact(Concepts.SELF_EMPLOYMENT_INCOME, 0) or 0
                )
                person_row = {
                    "person_id": person_id,
                    "household_id": household_id,
                    "marital_unit_id": marital_unit_id,
                    "family_id": family_id,
                    "spm_unit_id": spm_unit_id,
                    "tax_unit_id": tax_unit_id,
                    "person_weight": weight,
                    "age": int(entity.fact(Concepts.PERSON_AGE, 0) or 0),
                    "employment_income": employment_income,
                    # Benefit programs (TANF income sources, among others)
                    # read the pre-labor-supply-response income variables.
                    # The situation-based single-case path back-propagates
                    # employment_income into them, but a custom dataset does
                    # not — leaving them at 0 silently erases earned income
                    # from every program that counts *_before_lsr.
                    "employment_income_before_lsr": employment_income,
                    "self_employment_income_before_lsr": self_employment_income,
                    "is_pregnant": bool(entity.fact(Concepts.PREGNANT, False)),
                    "is_disabled": bool(entity.fact(Concepts.DISABLED, False)),
                    "is_blind": bool(entity.fact(Concepts.BLIND, False)),
                    "is_tax_unit_head": entity is head,
                    "is_tax_unit_spouse": entity is spouse,
                }
                person_row.update(_person_income_inputs(entity))
                for pe_variable in _PERSON_CASE_CONCEPT_TO_PE.values():
                    person_row[pe_variable] = 0
                if entity is head:
                    for concept, pe_variable in _PERSON_CASE_CONCEPT_TO_PE.items():
                        value = case.fact(concept)
                        if value is not None:
                            person_row[pe_variable] = float(value)
                person_rows.append(person_row)

            entity_ids_by_case.append(
                {
                    "person": person_ids,
                    "household": [household_id],
                    "marital_unit": [marital_unit_id],
                    "family": [family_id],
                    "spm_unit": [spm_unit_id],
                    "tax_unit": [tax_unit_id],
                }
            )

        return (
            person_rows,
            household_rows,
            marital_unit_rows,
            family_rows,
            spm_unit_rows,
            tax_unit_rows,
            entity_ids_by_case,
        )

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
        import math

        if hasattr(value, "tolist"):
            raw_values = value.tolist()
        elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
            raw_values = list(value)
        else:
            raw_values = [value]
        if not isinstance(raw_values, list):
            raw_values = [raw_values]
        if all(isinstance(item, bool) for item in raw_values):
            return any(raw_values)
        total = 0.0
        for item in raw_values:
            if hasattr(item, "item"):
                item = item.item()
            try:
                number = float(item)
            except (TypeError, ValueError):
                continue
            if math.isnan(number):
                continue
            total += number
        return total

    @staticmethod
    def _coerce_batch_values(value, size: int) -> list[float | bool]:
        import numpy as np

        array = np.asarray(value)
        if array.size != size:
            raise ValueError(f"expected {size} PolicyEngine values, got {array.size}")
        if array.dtype == bool:
            return [bool(item) for item in array.tolist()]
        cleaned = np.nan_to_num(array, nan=0)
        return [float(item) for item in cleaned.tolist()]

    @staticmethod
    def _policyengine_variables(requested: Sequence[str]) -> list[str]:
        mapped = engine_targets_for_concepts(tuple(requested), PolicyEngineRunner.name)
        if mapped:
            return mapped
        return list(requested)


def _person_income_inputs(entity: Entity) -> dict[str, float]:
    """Person income inputs, pinned for every mapped source.

    Absent source facts become explicit zero inputs — matching what the batch
    dataset bridge always did — so PolicyEngine prices the projected Case
    surface on every evaluation path instead of imputing an endogenous award
    (SSI, dividends, pensions, ...) that the counterpart engine never saw.
    The requested-month situation path previously left absent sources free,
    which made month-defined outputs and year-shaped booleans price two
    different income surfaces for the same household.

    The legacy ``dividend_income`` input is PolicyEngine's ordinary-dividends
    aggregation alias, and both the SNAP unearned-income and IRS gross-income
    source lists read it — so it must carry the declared qualified dividends
    too. ``qualified_dividend_income`` stays declared separately for rate
    treatment.
    """
    inputs = {
        pe_variable: float(entity.fact(concept, 0) or 0)
        for concept, pe_variable in _PERSON_INCOME_CONCEPT_TO_PE.items()
    }
    inputs["dividend_income"] = float(
        entity.fact(Concepts.DIVIDEND_INCOME, 0) or 0
    ) + float(entity.fact(Concepts.QUALIFIED_DIVIDEND_INCOME, 0) or 0)
    return inputs


def _namespaced_entity_id(prefix: str, entity_id: str) -> str:
    return f"{prefix}__{entity_id}"


def _household_result_value(result, variable: str) -> float | bool:
    for entity_name in ("tax_unit", "household", "spm_unit", "family", "marital_unit"):
        entity_result = _result_child(result, entity_name)
        if _result_contains(entity_result, variable):
            return PolicyEngineRunner._coerce_value(
                [_result_get(entity_result, variable)]
            )

    people = _result_child(result, "person")
    if isinstance(people, Sequence) and not isinstance(people, str | bytes):
        values = [
            _result_get(person, variable)
            for person in people
            if _result_contains(person, variable)
        ]
        if values:
            return PolicyEngineRunner._coerce_value(values)

    raise KeyError(variable)


def _result_child(result, name: str):
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


def _result_contains(result, name: str) -> bool:
    if result is None:
        return False
    if isinstance(result, Mapping):
        return name in result
    return hasattr(result, name)


def _result_get(result, name: str):
    if isinstance(result, Mapping):
        return result[name]
    return getattr(result, name)


def _extra_variables_by_entity(pe, variables: Sequence[str]) -> dict[str, list[str]]:
    extra_variables: dict[str, list[str]] = {}
    for variable in variables:
        entity = _variable_entity(pe, variable)
        extra_variables.setdefault(entity, []).append(variable)
    return extra_variables


def _variable_entity(pe, variable: str) -> str:
    return str(pe.us.model.get_variable(variable).entity)


def _normalize_value_for_requested_period(
    pe,
    variable: str,
    requested_period: str,
    value: float | bool,
    *,
    requested_value: float | bool | object = _MISSING_REQUESTED_PERIOD_VALUE,
) -> float | bool:
    """Select requested months from PolicyEngine's annual output dataset.

    policyengine.py's Simulation output dataset is year-shaped: month-defined
    numeric variables such as SNAP are emitted as annual sums. Oracle
    comparisons can request a month (`2026-01`), but annual / 12 is only a
    calendar average. Callers must supply the value calculated for that exact
    month; otherwise fail closed.
    """
    if "-" not in requested_period or _policyengine_variable_is_boolean(
        pe,
        variable,
        value,
    ):
        return value
    definition_period = _policyengine_definition_period(pe, variable)
    if not definition_period:
        if _policyengine_metadata_available(pe):
            raise RuntimeError(
                "Could not determine the definition period of PolicyEngine "
                f"variable {variable!r} for requested period "
                f"{requested_period!r}; refusing to serve the annual "
                "output-dataset value in its place"
            )
        # Without PolicyEngine metadata (stub engines, metadata-less unit
        # environments) no month semantics exist; outputs are year-shaped.
        return value
    if definition_period.lower() != "month":
        return value
    if requested_value is _MISSING_REQUESTED_PERIOD_VALUE:
        raise RuntimeError(
            "PolicyEngine did not calculate month-defined variable "
            f"{variable!r} for requested period {requested_period!r}; refusing "
            "to derive it from the annual output-dataset sum"
        )
    return requested_value


def _policyengine_variable_is_boolean(
    pe,
    variable: str,
    value: float | bool,
) -> bool:
    if isinstance(value, bool):
        return True
    model = getattr(pe.us, "model", None)
    if model is None:
        return False
    try:
        variable_definition = model.get_variable(variable)
    except Exception:
        return False
    return (
        getattr(variable_definition, "value_type", None) is bool
        or getattr(variable_definition, "data_type", None) is bool
    )


def _policyengine_us_simulation(situation):
    try:
        from policyengine_us import Simulation
    except ImportError as exc:
        raise RuntimeError(
            "Install the PolicyEngine US extra to calculate requested-month values"
        ) from exc
    return Simulation(situation=situation)


def _simulation_variable_definition(simulation, variable: str):
    tax_benefit_system = getattr(simulation, "tax_benefit_system", None)
    variables = getattr(tax_benefit_system, "variables", {})
    try:
        return variables[variable]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"PolicyEngine simulation does not define variable {variable!r}"
        ) from exc


def _simulation_variable_entity(variable_definition) -> str:
    entity = getattr(variable_definition, "entity", None)
    key = getattr(entity, "key", None)
    if key:
        return str(key)
    if isinstance(entity, str):
        return entity
    return ""


def _policyengine_definition_period(pe, variable: str) -> str:
    model = getattr(pe.us, "model", None)
    if model is None:
        return _policyengine_source_definition_period(variable)
    variable_definition = model.get_variable(variable)
    definition_period = getattr(variable_definition, "definition_period", None)
    if definition_period is not None:
        return str(definition_period).lower()
    native_definition_period = _policyengine_native_definition_period(variable)
    if native_definition_period:
        return native_definition_period
    if variable in _MONTHLY_NUMERIC_OUTPUT_VARIABLES:
        return "month"
    return _policyengine_source_definition_period(variable)


def _policyengine_metadata_available(pe) -> bool:
    """Report whether any variable-metadata source exists for ``pe``.

    True when the runner can interrogate definition periods at all — via the
    engine's own model or the installed policyengine_us package. Stub engines
    in metadata-less environments return False, and their outputs are treated
    as year-shaped because no month semantics exist without metadata.
    """
    if getattr(getattr(pe, "us", None), "model", None) is not None:
        return True
    try:
        import policyengine_us  # noqa: F401
    except Exception:
        return False
    return True


@lru_cache(maxsize=None)
def _policyengine_native_definition_period(variable: str) -> str:
    try:
        from policyengine_us.system import system as pe_us_system
    except Exception:
        return ""

    variable_definition = pe_us_system.variables.get(variable)
    definition_period = getattr(variable_definition, "definition_period", None)
    if definition_period is None:
        return ""
    return str(definition_period).lower()


@lru_cache(maxsize=None)
def _policyengine_source_definition_period(variable: str) -> str:
    native_definition_period = _policyengine_native_definition_period(variable)
    if native_definition_period:
        return native_definition_period

    try:
        import importlib
        import pkgutil

        import policyengine_us.variables as variables_pkg
    except Exception:
        return ""

    for module_info in pkgutil.walk_packages(
        variables_pkg.__path__,
        prefix=f"{variables_pkg.__name__}.",
    ):
        if module_info.name.rsplit(".", maxsplit=1)[-1] != variable:
            continue
        try:
            module = importlib.import_module(module_info.name)
        except Exception:
            continue
        variable_class = getattr(module, variable, None)
        definition_period = getattr(variable_class, "definition_period", None)
        if definition_period is not None:
            return str(definition_period).lower()
    return ""


def _include_scope_inputs(variables: list[str] | None) -> bool:
    if variables is None:
        return True
    return any(
        variable not in _SCOPE_FREE_FEDERAL_TAX_VARIABLES
        and variable not in _STATE_SCOPE_FEDERAL_TAX_VARIABLES
        for variable in variables
    )


def _scope_inputs_for_variables(
    case: Case,
    variables: list[str] | None,
) -> dict[str, int | str]:
    scope_inputs = pe_inputs_for_scope(case.scope)
    if _include_scope_inputs(variables):
        return scope_inputs
    if variables and any(
        variable in _STATE_SCOPE_FEDERAL_TAX_VARIABLES for variable in variables
    ):
        return {
            variable: value
            for variable, value in scope_inputs.items()
            if variable == "state_fips"
        }
    return {}


def _tax_filers(people: list[Entity]) -> tuple[Entity | None, Entity | None]:
    if not people:
        return None, None
    explicit_head = _head(people)
    explicit_spouse = _spouse(people, explicit_head)
    if explicit_spouse is not None:
        return explicit_head, explicit_spouse

    adult_people = [
        person
        for person in people
        if _age(person) >= _TAX_FILER_ADULT_AGE
        and _relation(person) not in _DEPENDENT_RELATIONS
    ]
    if not adult_people:
        return explicit_head, None
    ranked = sorted(
        adult_people,
        key=lambda person: (_age(person), _earned_income(person)),
        reverse=True,
    )
    head = ranked[0]
    spouse = ranked[1] if len(ranked) > 1 else None
    return head, spouse


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


def _earned_income(entity: Entity) -> float:
    return _number(entity.fact(Concepts.YEARLY_EARNED_INCOME, 0))


def _number(value: object) -> float:
    if value is None or value == "":
        return 0
    return float(value)
