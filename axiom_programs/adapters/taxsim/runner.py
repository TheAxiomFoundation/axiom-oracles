from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any

from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult


class TaxsimPackageRunner(EngineAdapter):
    """Adapter for PolicyEngine/policyengine-taxsim style runners.

    Cases must carry a TAXSIM-format row in ``metadata["taxsim_input"]``.
    The adapter keeps that projection outside the comparison core and only
    standardizes runner inputs and outputs.
    """

    name = "taxsim"

    def __init__(
        self,
        runner_factory: Callable[[Any], Any] | None = None,
        *,
        id_column: str = "taxsimid",
    ) -> None:
        self.runner_factory = runner_factory
        self.id_column = id_column

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        input_frame = self._input_frame(cases)
        runner = self._runner_factory()(input_frame)
        output = self._run_runner(runner)
        return self._engine_results(output, cases, variables)

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise RuntimeError(
            "TAXSIM comparisons require Case.metadata['taxsim_input'] rows. "
            "Project Axiom households to TAXSIM rows before running this adapter."
        )

    def _runner_factory(self) -> Callable[[Any], Any]:
        if self.runner_factory is not None:
            return self.runner_factory
        for module_name, attr_name in (
            ("policyengine_taxsim", "TaxsimRunner"),
            ("policyengine_taxsim.runners", "TaxsimRunner"),
        ):
            try:
                module = import_module(module_name)
            except ImportError:
                continue
            runner = getattr(module, attr_name, None)
            if runner is not None:
                return runner
        raise RuntimeError(
            "Could not import policyengine-taxsim's TaxsimRunner. Install the "
            "package or pass runner_factory=..."
        )

    def _input_frame(self, cases: list[Case]) -> Any:
        rows = []
        for case in cases:
            row = case.metadata.get("taxsim_input") or case.fact("taxsim_input")
            if row is None:
                raise RuntimeError(
                    "TAXSIM adapter requires each case to include "
                    "metadata['taxsim_input']."
                )
            if not isinstance(row, Mapping):
                raise RuntimeError(
                    "Case metadata['taxsim_input'] must be a mapping of TAXSIM "
                    "input columns to values."
                )
            normalized = dict(row)
            normalized.setdefault(self.id_column, case.case_id)
            rows.append(normalized)

        try:
            import pandas as pd

            return pd.DataFrame(rows)
        except ImportError:
            return _SimpleFrame(rows)

    def _engine_results(
        self,
        output: Any,
        cases: list[Case],
        variables: list[str] | None,
    ) -> list[EngineResult]:
        records = _records(output)
        case_ids_by_text = {str(case.case_id): case.case_id for case in cases}
        case_ids = [case.case_id for case in cases]
        results = []
        for index, record in enumerate(records):
            household_id = record.get(self.id_column)
            if household_id is None and index < len(case_ids):
                household_id = case_ids[index]
            household_id = case_ids_by_text.get(str(household_id), household_id)
            results.append(
                EngineResult(
                    engine=self.name,
                    household_id=household_id,
                    values=_selected_values(
                        record,
                        variables,
                        excluded_keys={self.id_column},
                    ),
                    raw=record,
                )
            )
        return results

    @staticmethod
    def _run_runner(runner: Any) -> Any:
        try:
            return runner.run(show_progress=False)
        except TypeError:
            return runner.run()


class _SimpleFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.iloc = _SimpleFrameIloc(rows)

    def to_dict(self, orient: str = "dict") -> list[dict[str, Any]]:
        if orient != "records":
            raise ValueError("_SimpleFrame only supports orient='records'")
        return [dict(row) for row in self._rows]


class _SimpleFrameIloc:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._rows[index]


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
