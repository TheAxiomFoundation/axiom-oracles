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
        # The projection assigns each emulator household a numeric
        # household_id; PRD echoes it back as `hhid`, so results map to
        # case ids through it (the same input-row identity join the TAXSIM
        # adapter performs).
        id_map = {
            str(getattr(household, "household_id", case.case_id)): case.case_id
            for household, case in zip(households, cases, strict=True)
        }
        output = self._run_households(
            self._runner(),
            households,
            _programs_for_targets(target_variables),
        )
        results = self._engine_results(
            output,
            [case.case_id for case in cases],
            target_variables,
            id_map=id_map,
        )
        periods = {case.case_id: str(case.period) for case in cases}
        return [
            _normalize_result_for_period(
                result, periods.get(result.household_id, "")
            )
            for result in results
        ]

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
        from .projection import build_emulator_household

        metadata_household = case.metadata.get("prd_household")
        if metadata_household is not None:
            return build_emulator_household(metadata_household)
        fact_household = case.fact("prd_household")
        if fact_household is not None:
            return build_emulator_household(fact_household)
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
        *,
        id_map: Mapping[str, int | str] | None = None,
    ) -> list[EngineResult]:
        # PRD emits one row per person with household-level values repeated
        # on every member row; keep the first row per household identity.
        records = []
        seen: set[str] = set()
        for record in _records(output):
            key = record.get(self.id_column, record.get("case_id"))
            text = _id_key(key)
            if key is not None and text in seen:
                continue
            if key is not None:
                seen.add(text)
            records.append(record)
        ids_by_text = {str(household_id): household_id for household_id in household_ids}
        results = []
        for index, record in enumerate(records):
            household_id = record.get(self.id_column, record.get("case_id"))
            if household_id is None and index < len(household_ids):
                household_id = household_ids[index]
            if id_map is not None:
                household_id = id_map.get(
                    _id_key(household_id), household_id
                )
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


# Concept mappings name PRD OUTPUT COLUMNS (value.snap, value.tanf, ...),
# but the R package's calculators are selected by PROGRAM NAME ("SNAP",
# "TANF", ...). Passing a column where a program is expected silently
# computes nothing and returns zero-filled columns, so translate before
# invoking the runner. Unknown targets pass through unchanged (external
# callers may already speak program names).
_PROGRAMS_BY_COLUMN = {
    "value.snap": "SNAP",
    "value.tanf": "TANF",
    "value.ssi": "SSI",
    "value.ssdi": "SSDI",
    "value.wic": "WIC",
    "value.liheap": "LIHEAP",
    "value.section8": "SECTION8",
    "value.ccdf": "CCDF",
    "value.CCDF": "CCDF",
    "value.eitc.fed": "EITC",
    "value.eitc.state": "EITC",
    "value.ctc.fed": "CTC",
    "value.ctc.state": "CTC",
    "value.cdctc.fed": "CDCTC",
    "value.cdctc.state": "CDCTC",
    "value.medicaid.adult": "MEDICAID_ADULT",
    "value.medicaid.child": "MEDICAID_CHILD",
    "value.aca": "ACA",
    "value.schoolmeals": "SLP",
}


def _programs_for_targets(targets: list[str] | None) -> list[str] | None:
    if targets is None:
        return None
    programs = [
        _PROGRAMS_BY_COLUMN.get(target, target) for target in targets
    ]
    return list(dict.fromkeys(programs))


def _id_key(value: Any) -> str:
    """Normalize numeric identities (1, 1.0, "1") to one text key."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            return str(int(number))
    return str(value)


# PRD emits annual sums for month-defined benefit programs. When a
# comparison requests a month period (e.g. "2026-01"), these columns are
# normalized to one month — the same convention the PolicyEngine adapter
# applies to its month-defined variables.
_MONTHLY_PRD_COLUMNS = frozenset(
    {
        "value.snap",
        "value.tanf",
        "value.ssi",
        "value.ssdi",
        "value.section8",
        "value.wic",
        "value.liheap",
    }
)


def _normalize_result_for_period(result: EngineResult, period: str) -> EngineResult:
    if "-" not in period:
        return result
    values = {
        key: (
            float(value) / 12
            if key in _MONTHLY_PRD_COLUMNS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            else value
        )
        for key, value in result.values.items()
    }
    return EngineResult(
        engine=result.engine,
        household_id=result.household_id,
        values=values,
        raw=result.raw,
        errors=result.errors,
    )


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
        return {
            key: value
            for key, value in record.items()
            if key not in excluded_keys
        }
    return {variable: record[variable] for variable in variables if variable in record}
