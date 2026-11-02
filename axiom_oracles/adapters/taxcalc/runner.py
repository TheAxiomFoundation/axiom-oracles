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
from .projection import taxcalc_input_for_case


class TaxCalcPackageRunner(EngineAdapter):
    """Adapter for PSLmodels Tax-Calculator's Python package."""

    name = "taxcalc"

    def __init__(
        self,
        runner_factory: Callable[[list[dict[str, Any]]], Any] | None = None,
        *,
        id_column: str = "RECID",
    ) -> None:
        self.runner_factory = runner_factory
        self.id_column = id_column

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        input_rows = self._input_rows(cases)
        target_variables = self._target_variables(variables)
        runner = self._runner_factory()(input_rows)
        output = self._run_runner(runner, target_variables)
        return self._engine_results(output, cases, target_variables, input_rows)

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise RuntimeError(
            "Tax-Calculator comparisons require Case inputs so the adapter can "
            "project or read Tax-Calculator rows."
        )

    def _runner_factory(self) -> Callable[[list[dict[str, Any]]], Any]:
        if self.runner_factory is not None:
            return self.runner_factory
        return _PslTaxCalcRunner

    def _input_rows(self, cases: list[Case]) -> list[dict[str, Any]]:
        rows = []
        for index, case in enumerate(cases, start=1):
            row = case.metadata.get("taxcalc_input") or case.fact("taxcalc_input")
            if row is not None and not isinstance(row, Mapping):
                raise RuntimeError(
                    "Case metadata['taxcalc_input'] must be a mapping of "
                    "Tax-Calculator input columns to values."
                )
            if row is None:
                normalized = taxcalc_input_for_case(case, record_id=index)
            else:
                normalized = dict(row)
                normalized.setdefault(self.id_column, case.case_id)
            rows.append(normalized)
        return rows

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
    def _run_runner(runner: Any, variables: list[str] | None) -> Any:
        try:
            return runner.run(variables=variables)
        except TypeError:
            return runner.run()


class _PslTaxCalcRunner:
    def __init__(self, input_rows: list[dict[str, Any]]) -> None:
        self.input_rows = input_rows

    def run(self, variables: list[str] | None = None) -> list[dict[str, Any]]:
        try:
            import pandas as pd
            from taxcalc import Calculator, Policy, Records
        except ImportError as exc:
            raise RuntimeError(
                "Could not import PSL Tax-Calculator. Install the taxcalc "
                "extra or pass runner_factory=..."
            ) from exc

        variables = variables or _DEFAULT_TAXCALC_OUTPUTS
        rows: list[dict[str, Any]] = []
        frame = pd.DataFrame(self.input_rows)
        if frame.empty:
            return rows
        for year, year_frame in frame.groupby("FLPDYR", sort=False):
            records = Records(
                data=year_frame.reset_index(drop=True),
                start_year=int(year),
                gfactors=None,
                weights=None,
            )
            policy = Policy()
            _force_full_credit_claiming(policy, int(year))
            policy.set_year(int(year))
            calculator = Calculator(policy=policy, records=records)
            calculator.calc_all()
            arrays = {variable: calculator.array(variable) for variable in variables}
            record_ids = year_frame["RECID"].tolist()
            for index, record_id in enumerate(record_ids):
                row = {"RECID": record_id}
                row.update(
                    {
                        variable: _scalar(values[index])
                        for variable, values in arrays.items()
                    }
                )
                rows.append(row)
        return rows


_DEFAULT_TAXCALC_OUTPUTS = (
    "iitax",
    "payrolltax",
    "combined",
    "c00100",
    "standard",
    "c04800",
    "taxbc",
    "eitc",
    "ctc_total",
    "ctc_refundable",
    "ctc_nonrefundable",
    "c09600",
    "expanded_income",
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


def _scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _force_full_credit_claiming(policy: Any, year: int) -> None:
    """Make Tax-Calculator report legal credit entitlement amounts."""

    policy.adjust(
        {
            "eitc_claim_prob_scale": [{"year": year, "value": 9e99}],
            "actc_claim_prob_scale": [{"year": year, "value": 9e99}],
        },
        print_warnings=False,
    )


def taxcalc_version() -> str:
    module = import_module("taxcalc")
    return str(getattr(module, "__version__", "unknown"))
