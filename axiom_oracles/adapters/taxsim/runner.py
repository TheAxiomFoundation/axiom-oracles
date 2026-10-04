from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from .output import TaxsimRecord, TaxsimStdout, id_key, parse_taxsim_stdout
from .projection import taxsim_input_for_case

log = logging.getLogger(__name__)

#: Key under which a result's ``raw`` payload carries the diagnostic lines the
#: binary wrote to stdout before that record's CSV row.
DIAGNOSTICS_KEY = "taxsim_stdout_diagnostics"

_STDERR_EXCERPT = 2_000


@dataclass(frozen=True)
class TaxsimExecution:
    """One invocation of the TAXSIM executable over a batch input file."""

    stdout: str
    stderr: str
    returncode: int
    binary: str | None = None


class TaxsimPackageRunner(EngineAdapter):
    """Adapter for PolicyEngine/policyengine-taxsim style runners.

    Cases may carry a TAXSIM-format row in ``metadata["taxsim_input"]``. When
    absent, the adapter projects the thin Axiom case into a TAXSIM input row.

    The default path writes the batch with policyengine-taxsim's own input
    formatter, runs the pinned binary directly and parses its stdout with
    :func:`parse_taxsim_stdout`, so diagnostic lines the binary interleaves
    with its CSV rows are attributed to the record they precede instead of
    surfacing as phantom NaN-id rows. Every submitted case yields exactly one
    :class:`EngineResult`: a case the binary produced no row for gets an
    ``errors`` entry naming it, and any output row that matches no submitted
    case aborts the batch.

    ``runner_factory`` keeps the older protocol (an object whose ``run()``
    returns records) for tests and for policyengine-taxsim's PolicyEngine
    runner; ``executor`` replaces the binary invocation (tests feed captured
    stdout through it).
    """

    name = "taxsim"

    def __init__(
        self,
        runner_factory: Callable[[Any], Any] | None = None,
        *,
        id_column: str = "taxsimid",
        executor: Callable[[Any], TaxsimExecution] | None = None,
    ) -> None:
        self.runner_factory = runner_factory
        self.id_column = id_column
        self.executor = executor

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        input_rows = self._input_rows(cases)
        input_frame = self._frame_from_rows(input_rows)
        output = self._run(input_frame)
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

    def _run(self, input_frame: Any) -> Any:
        if self.runner_factory is not None:
            return self._run_runner(self.runner_factory(input_frame))
        executor = self.executor or self._execute_binary
        execution = executor(input_frame)
        if execution.returncode != 0:
            raise RuntimeError(
                f"TAXSIM exited with status {execution.returncode}"
                f"{_binary_suffix(execution)}; stderr: "
                f"{_excerpt(execution.stderr)!r}; stdout tail: "
                f"{_excerpt(execution.stdout, tail=True)!r}"
            )
        parsed = parse_taxsim_stdout(execution.stdout, id_column=self.id_column)
        return _ParsedOutput(parsed=parsed, execution=execution)

    def _execute_binary(self, input_frame: Any) -> TaxsimExecution:
        """Write the batch with policyengine-taxsim's formatter and run the binary.

        policyengine-taxsim's ``TaxsimRunner.run()`` reads the whole stdout
        stream with ``pandas.read_csv`` and coerces every column to numeric,
        which turns the binary's diagnostic lines into rows with NaN ids. Use
        its input formatting and executable lookup, but capture the raw bytes
        and parse them here.
        """
        runner = self._runner_factory()(input_frame)
        write_input = getattr(runner, "_create_taxsim_input_file", None)
        binary = getattr(runner, "taxsim_path", None)
        if write_input is None or binary is None:
            raise RuntimeError(
                "policyengine-taxsim's TaxsimRunner no longer exposes "
                "_create_taxsim_input_file/taxsim_path; the pinned release in "
                "taxsim_pins.json does. Refresh the adapter with the pin."
            )
        input_path = write_input(runner.input_df)
        try:
            with open(input_path, "rb") as stdin:
                process = subprocess.run(
                    [str(binary)],
                    stdin=stdin,
                    capture_output=True,
                    check=False,
                )
        finally:
            try:
                os.unlink(input_path)
            except OSError:
                pass
        return TaxsimExecution(
            stdout=process.stdout.decode("utf-8", errors="replace"),
            stderr=process.stderr.decode("utf-8", errors="replace"),
            returncode=process.returncode,
            binary=str(binary),
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
        if isinstance(output, _ParsedOutput):
            records = output.parsed.records
            trailing = output.parsed.trailing_diagnostics
            execution: TaxsimExecution | None = output.execution
        else:
            records = _records_from_legacy_output(
                output, self.id_column, cases, input_rows
            )
            trailing = ()
            execution = None
        return self._results_for_cases(
            records,
            trailing,
            execution,
            cases,
            variables,
            input_rows,
        )

    def _results_for_cases(
        self,
        records: list[TaxsimRecord],
        trailing_diagnostics: tuple[str, ...],
        execution: TaxsimExecution | None,
        cases: list[Case],
        variables: list[str] | None,
        input_rows: list[dict[str, Any]],
    ) -> list[EngineResult]:
        expected: list[tuple[str, Case]] = []
        for row, case in zip(input_rows, cases, strict=True):
            submitted = row.get(self.id_column)
            key = id_key(case.case_id if submitted is None else submitted)
            expected.append((key, case))
        expected_keys = {key for key, _ in expected}

        by_key: dict[str, TaxsimRecord] = {}
        unexpected: list[TaxsimRecord] = []
        for record in records:
            if record.id_key not in expected_keys:
                unexpected.append(record)
                continue
            if record.id_key in by_key:
                raise RuntimeError(
                    f"TAXSIM returned more than one output row for "
                    f"{self.id_column}={record.id_key} (stdout lines "
                    f"{by_key[record.id_key].line_number} and "
                    f"{record.line_number}){_binary_suffix(execution)}"
                )
            by_key[record.id_key] = record
        if unexpected:
            shown = [
                f"{self.id_column}={record.id_key} (stdout line {record.line_number})"
                for record in unexpected[:10]
            ]
            raise RuntimeError(
                f"TAXSIM returned {len(unexpected)} output row(s) matching no "
                f"submitted case: {', '.join(shown)}{_binary_suffix(execution)}"
            )

        missing = [(key, case) for key, case in expected if key not in by_key]
        if trailing_diagnostics and not missing:
            raise RuntimeError(
                f"TAXSIM wrote {len(trailing_diagnostics)} non-record stdout "
                f"line(s) after its last output row although every submitted "
                f"case has a row; they cannot be attributed to a case: "
                f"{list(trailing_diagnostics[:5])!r}{_binary_suffix(execution)}"
            )

        results = []
        first_missing = missing[0][0] if missing else None
        for key, case in expected:
            record = by_key.get(key)
            if record is None:
                results.append(
                    EngineResult(
                        engine=self.name,
                        household_id=case.case_id,
                        values={},
                        raw=None,
                        errors=(
                            _missing_row_error(
                                self.id_column,
                                key,
                                execution,
                                trailing_diagnostics if key == first_missing else (),
                            ),
                        ),
                    )
                )
                continue
            raw: dict[str, Any] = dict(record.values)
            if record.diagnostics:
                raw[DIAGNOSTICS_KEY] = list(record.diagnostics)
            results.append(
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values=_selected_values(
                        record.values,
                        variables,
                        excluded_keys={self.id_column},
                    ),
                    raw=raw,
                )
            )

        flagged = [record for record in by_key.values() if record.diagnostics]
        if flagged:
            flagged.sort(key=lambda record: record.line_number)
            ids = [record.id_key for record in flagged]
            shown = ", ".join(ids[:10]) + (", ..." if len(ids) > 10 else "")
            log.warning(
                "TAXSIM wrote %d non-record stdout line(s) before the rows of %d "
                "record(s) (%s=%s); kept on EngineResult.raw[%r]. First: %r",
                sum(len(record.diagnostics) for record in flagged),
                len(flagged),
                self.id_column,
                shown,
                DIAGNOSTICS_KEY,
                flagged[0].diagnostics[0],
            )
        if missing:
            log.warning(
                "TAXSIM produced no output row for %d of %d submitted case(s); "
                "each carries an error naming it.",
                len(missing),
                len(expected),
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


@dataclass(frozen=True)
class _ParsedOutput:
    parsed: TaxsimStdout
    execution: TaxsimExecution


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


def _records_from_legacy_output(
    output: Any,
    id_column: str,
    cases: list[Case],
    input_rows: list[dict[str, Any]],
) -> list[TaxsimRecord]:
    """Adapt ``runner.run()`` records to :class:`TaxsimRecord`.

    A record without an id column takes the submitted id at its position,
    or the case id if the submitted id is None (the pre-existing positional
    convention for runners that drop the column). An id
    that is not a finite number or text — pandas' NaN for a line it could not
    read, for example — is rejected here rather than passed on as a phantom
    household.
    """
    records = []
    fallback_ids = [
        case.case_id if row.get(id_column) is None else row[id_column]
        for row, case in zip(input_rows, cases, strict=True)
    ]
    for index, record in enumerate(_records(output)):
        household_id = record.get(id_column)
        if household_id is None and index < len(fallback_ids):
            household_id = fallback_ids[index]
        if household_id is None or (
            isinstance(household_id, float) and household_id != household_id
        ):
            raise RuntimeError(
                f"TAXSIM runner output record {index + 1} carries an unusable "
                f"{id_column}={household_id!r}; refusing to attribute it to a "
                "case."
            )
        records.append(
            TaxsimRecord(
                id_key=id_key(household_id),
                values=dict(record),
                line_number=index + 1,
            )
        )
    return records


def _missing_row_error(
    id_column: str,
    key: str,
    execution: TaxsimExecution | None,
    trailing_diagnostics: tuple[str, ...],
) -> str:
    message = f"TAXSIM produced no output row for {id_column}={key}"
    if execution is not None and execution.stderr.strip():
        message += f"; stderr: {_excerpt(execution.stderr)!r}"
    if trailing_diagnostics:
        message += f"; trailing stdout lines: {list(trailing_diagnostics[:10])!r}"
    return message


def _binary_suffix(execution: TaxsimExecution | None) -> str:
    if execution is None or not execution.binary:
        return ""
    return f" (binary {execution.binary})"


def _excerpt(text: str, *, tail: bool = False) -> str:
    text = text.strip()
    if len(text) <= _STDERR_EXCERPT:
        return text
    if tail:
        return "..." + text[-_STDERR_EXCERPT:]
    return text[:_STDERR_EXCERPT] + "..."


def _selected_values(
    record: Mapping[str, Any],
    variables: list[str] | None,
    *,
    excluded_keys: set[str],
) -> dict[str, Any]:
    if variables is None:
        return {key: value for key, value in record.items() if key not in excluded_keys}
    return {variable: record[variable] for variable in variables if variable in record}


def _id_key(value: Any) -> str:
    return id_key(value)
