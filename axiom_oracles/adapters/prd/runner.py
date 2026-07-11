from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult


class PrdPackageRunner(EngineAdapter):
    """Adapter for Atlanta Fed PRD comparison runners.

    Cases must either carry an external PRD household object in
    ``metadata["prd_household"]`` or be convertible by ``household_mapper``.
    """

    name = "prd"

    def __init__(
        self,
        runner: Any | None = None,
        runner_factory: Callable[[], Any] | None = None,
        household_mapper: Callable[[Case], Any] | None = None,
        *,
        id_column: str = "hhid",
    ) -> None:
        self.runner = runner
        self.runner_factory = runner_factory
        self.household_mapper = household_mapper
        self.id_column = id_column

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        target_variables = self._target_variables(variables)
        households = [self._case_household(case) for case in cases]
        output = self._run_households(self._runner(), households, target_variables)
        return self._engine_results(
            output,
            [case.case_id for case in cases],
            target_variables,
        )

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        target_variables = self._target_variables(variables)
        output = self._run_households(self._runner(), households, target_variables)
        household_ids = [household.household_id for household in households]
        return self._engine_results(output, household_ids, target_variables)

    def _runner(self) -> Any:
        if self.runner is not None:
            return self.runner
        if self.runner_factory is not None:
            return self.runner_factory()
        for module_name, attr_name in (
            ("policyengine_prd", "PRDRunner"),
            ("prd_comparison", "PRDRunner"),
            ("prd_comparison.runner", "PRDRunner"),
        ):
            try:
                module = import_module(module_name)
            except ImportError:
                continue
            runner_class = getattr(module, attr_name, None)
            if runner_class is not None:
                return runner_class()
        raise RuntimeError(
            "Could not import a PRD comparison runner. Install the PRD package "
            "or pass runner=... / runner_factory=..."
        )

    def _case_household(self, case: Case) -> Any:
        metadata_household = case.metadata.get("prd_household")
        if metadata_household is not None:
            return metadata_household
        fact_household = case.fact("prd_household")
        if fact_household is not None:
            return fact_household
        if self.household_mapper is not None:
            return self.household_mapper(case)
        raise RuntimeError(
            "PRD adapter requires metadata['prd_household'] or a household_mapper "
            "for each case."
        )

    @staticmethod
    def _run_households(
        runner: Any,
        households: list[Any],
        variables: list[str] | None,
    ) -> Any:
        if not hasattr(runner, "run_households"):
            raise RuntimeError("PRD runner must expose run_households(...).")
        try:
            return runner.run_households(households, programs=variables)
        except TypeError:
            return runner.run_households(households)

    def _engine_results(
        self,
        output: Any,
        household_ids: list[int | str],
        variables: list[str] | None,
    ) -> list[EngineResult]:
        records = _records(output)
        ids_by_text = {
            str(household_id): household_id for household_id in household_ids
        }
        results = []
        for index, record in enumerate(records):
            household_id = record.get(self.id_column, record.get("case_id"))
            if household_id is None and index < len(household_ids):
                household_id = household_ids[index]
            household_id = ids_by_text.get(str(household_id), household_id)
            results.append(
                EngineResult(
                    engine=self.name,
                    household_id=household_id,
                    values=_selected_values(
                        record,
                        variables,
                        excluded_keys={self.id_column, "case_id"},
                    ),
                    raw=record,
                )
            )
        return results

    def _target_variables(self, variables: list[str] | None) -> list[str] | None:
        if variables is None:
            return None
        targets: list[str] = []
        for variable in variables:
            mapped = engine_targets_for_concepts([variable], self.name)
            targets.extend(mapped or [variable])
        return targets


def _records(output: Any) -> list[dict[str, Any]]:
    if output is None:
        return []
    if hasattr(output, "to_dict"):
        return [dict(row) for row in output.to_dict(orient="records")]
    if isinstance(output, Mapping):
        return [dict(output)]
    return [dict(row) for row in output]


def _selected_values(
    record: Mapping[str, Any],
    variables: list[str] | None,
    *,
    excluded_keys: set[str],
) -> dict[str, Any]:
    if variables is None:
        return {key: value for key, value in record.items() if key not in excluded_keys}
    return {variable: record[variable] for variable in variables if variable in record}
