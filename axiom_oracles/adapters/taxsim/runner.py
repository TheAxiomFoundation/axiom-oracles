from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from numbers import Integral, Real
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from .projection import taxsim_input_for_case


class TaxsimPackageRunner(EngineAdapter):
    """Adapter for PolicyEngine/policyengine-taxsim style runners.

    Cases may carry a TAXSIM-format row in ``metadata["taxsim_input"]``. When
    absent, the adapter projects the thin Axiom case into a TAXSIM input row.
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
        input_rows = self._input_rows(cases)
        input_frame = self._frame_from_rows(input_rows)
        runner = self._runner_factory()(input_frame)
        output = self._run_runner(runner)
        target_variables = self._target_variables(variables)
        return self._engine_results(output, cases, target_variables, input_rows)

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise RuntimeError(
            "TAXSIM comparisons require Case inputs so the adapter can project "
            "or read TAXSIM rows."
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
                # policyengine-taxsim's own executable search assumes
                # sys.prefix carries the wheel's share/ data files, which is
                # false inside uv `--with` overlay environments — resolve the
                # bundled binary ourselves (pins.installed_binary_path also
                # walks the sys.path archive roots) and pass it explicitly;
                # None keeps its native search for source-layout dev runs.
                from .pins import installed_binary_path

                binary = installed_binary_path()
                if binary is not None:
                    # Its signature annotates taxsim_path as str, but
                    # _validate_executable calls .exists() on it — a Path is
                    # what actually works.
                    return lambda frame: runner(frame, taxsim_path=binary)
                return runner
        raise RuntimeError(
            "Could not import policyengine-taxsim's TaxsimRunner. Install the "
            "package or pass runner_factory=..."
        )

    def _input_frame(self, cases: list[Case]) -> Any:
        return self._frame_from_rows(self._input_rows(cases))

    def _input_rows(self, cases: list[Case]) -> list[dict[str, Any]]:
        rows = []
        for index, case in enumerate(cases, start=1):
            row = case.metadata.get("taxsim_input") or case.fact("taxsim_input")
            if row is not None and not isinstance(row, Mapping):
                raise RuntimeError(
                    "Case metadata['taxsim_input'] must be a mapping of TAXSIM "
                    "input columns to values."
                )
            if row is None:
                normalized = taxsim_input_for_case(case, taxsimid=index)
            else:
                normalized = dict(row)
                normalized.setdefault(self.id_column, case.case_id)
            rows.append(normalized)
        return rows

    @staticmethod
    def _frame_from_rows(rows: list[dict[str, Any]]) -> Any:
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
        input_rows: list[dict[str, Any]],
    ) -> list[EngineResult]:
        records = _records(output)
        case_ids_by_input_id = {
            _id_key(row.get(self.id_column)): case.case_id
            for row, case in zip(input_rows, cases, strict=True)
            if row.get(self.id_column) is not None
        }
        case_ids_by_text = {_id_key(case.case_id): case.case_id for case in cases}
        case_ids = [case.case_id for case in cases]
        results = []
        for index, record in enumerate(records):
            household_id = record.get(self.id_column)
            if household_id is None and index < len(case_ids):
                household_id = case_ids[index]
            household_id = case_ids_by_input_id.get(
                _id_key(household_id),
                case_ids_by_text.get(_id_key(household_id), household_id),
            )
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

    def _target_variables(self, variables: list[str] | None) -> list[str] | None:
        if variables is None:
            return None
        targets: list[str] = []
        for variable in variables:
            mapped = engine_targets_for_concepts([variable], self.name)
            targets.extend(mapped or [variable])
        return targets

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


def _id_key(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        number = float(value)
        if number.is_integer():
            return str(int(number))
    return str(value)
