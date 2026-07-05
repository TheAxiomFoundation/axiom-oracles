from __future__ import annotations

import csv
from collections.abc import Mapping
import os
from numbers import Integral, Real
from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from .projection import yale_taxsim_input_for_case


class YaleTaxSimulatorRunner(EngineAdapter):
    """CSV-command adapter for the Budget Lab at Yale Tax-Simulator.

    The upstream model is an R microsimulation pipeline, not a Python package.
    This adapter writes bridge input rows, invokes a configured command, and
    reads per-case output rows back into the normal ``EngineResult`` shape.
    """

    name = "yale_taxsim"

    def __init__(
        self,
        runner: Any | None = None,
        *,
        command: str | list[str] | None = None,
        cwd: str | Path | None = None,
        id_column: str = "id",
    ) -> None:
        self.runner = runner
        self.command = command
        self.cwd = Path(cwd) if cwd is not None else None
        self.id_column = id_column

    @classmethod
    def from_environment(cls) -> YaleTaxSimulatorRunner:
        command: str | list[str] | None = os.environ.get("YALE_TAXSIM_COMMAND")
        if not command and os.environ.get("YALE_TAXSIM_REPO"):
            command = [
                "Rscript",
                str(Path(__file__).with_name("yale_taxsim_bridge.R")),
            ]
        return cls(
            command=command,
            cwd=os.environ.get("YALE_TAXSIM_REPO"),
        )

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        input_rows = self._input_rows(cases)
        target_variables = self._target_variables(variables)
        output = self._run(input_rows, target_variables)
        return self._engine_results(output, cases, target_variables, input_rows)

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise RuntimeError(
            "Yale Tax-Simulator comparisons require Case inputs so the adapter "
            "can project or read bridge rows."
        )

    def _input_rows(self, cases: list[Case]) -> list[dict[str, Any]]:
        rows = []
        for case in cases:
            row = case.metadata.get("yale_taxsim_input") or case.fact(
                "yale_taxsim_input"
            )
            if row is not None and not isinstance(row, Mapping):
                raise RuntimeError(
                    "Case metadata['yale_taxsim_input'] must be a mapping of "
                    "Yale Tax-Simulator bridge columns to values."
                )
            if row is None:
                normalized = yale_taxsim_input_for_case(case)
            else:
                normalized = dict(row)
                normalized.setdefault(self.id_column, case.case_id)
            rows.append(normalized)
        return rows

    def _run(
        self,
        input_rows: list[dict[str, Any]],
        variables: list[str] | None,
    ) -> list[dict[str, Any]]:
        if self.runner is not None:
            try:
                return list(self.runner.run(input_rows, variables=variables))
            except TypeError:
                return list(self.runner.run(input_rows))

        if not self.command:
            raise RuntimeError(
                "Yale Tax-Simulator needs YALE_TAXSIM_REPO, "
                "YALE_TAXSIM_MACRO_ROOT, and either the packaged bridge or "
                "YALE_TAXSIM_COMMAND. The command receives "
                "AXIOM_ORACLES_YALE_INPUT, AXIOM_ORACLES_YALE_OUTPUT, and "
                "AXIOM_ORACLES_YALE_VARIABLES."
            )

        with tempfile.TemporaryDirectory(prefix="axiom-yale-taxsim-") as tmpdir:
            input_path = Path(tmpdir) / "input.csv"
            output_path = Path(tmpdir) / "output.csv"
            _write_csv(input_path, input_rows)
            env = dict(os.environ)
            env.update(
                {
                    "AXIOM_ORACLES_YALE_INPUT": str(input_path),
                    "AXIOM_ORACLES_YALE_OUTPUT": str(output_path),
                    "AXIOM_ORACLES_YALE_VARIABLES": ",".join(variables or ()),
                }
            )
            command = (
                self.command
                if isinstance(self.command, list)
                else shlex.split(self.command)
            )
            subprocess.run(
                command,
                cwd=self.cwd,
                env=env,
                check=True,
            )
            if not output_path.exists():
                raise RuntimeError(
                    "Yale Tax-Simulator command did not write "
                    f"{output_path}."
                )
            return _read_csv(output_path)

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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


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
            key: _coerce_scalar(value)
            for key, value in record.items()
            if key not in excluded_keys
        }
    return {
        variable: _coerce_scalar(record[variable])
        for variable in variables
        if variable in record
    }


def _coerce_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


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
