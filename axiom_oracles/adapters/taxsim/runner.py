from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from numbers import Integral, Real
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from . import pins
from .execution import TaxsimExecutionError, pinned_taxsim_runner_class
from .projection import taxsim_input_for_case

DEFAULT_MAX_CRASH_RERUNS = 64


class TaxsimPackageRunner(EngineAdapter):
    """Adapter for PolicyEngine/policyengine-taxsim style runners.

    Cases may carry a TAXSIM-format row in ``metadata["taxsim_input"]``. When
    absent, the adapter projects the thin Axiom case into a TAXSIM input row.

    Every row runs on a pinned TAXSIM binary (``pins.py``): rows are
    partitioned by the binary their (state, year) resolves to under the
    active pin profile, each partition runs on SHA-256-verified bytes, and
    results come back in input order with ``raw["taxsim_binary_sha256"]``.
    A partition whose executable fails is bisected to isolate the rows that
    fail on their own (:meth:`_run_isolated`).

    Subclasses that override ``_runner_factory`` to run a different engine
    over TAXSIM-format rows (``PolicyEngineTaxsimRunner``) keep the original
    single-run path: no partitioning, no binary lookup.
    """

    name = "taxsim"

    def __init__(
        self,
        runner_factory: Callable[..., Any] | None = None,
        *,
        id_column: str = "taxsimid",
        pin_profile: str | None = None,
        platform: str | None = None,
        binary_locator: Callable[..., Any] | None = None,
        max_crash_reruns: int = DEFAULT_MAX_CRASH_RERUNS,
    ) -> None:
        """Build the adapter.

        ``runner_factory`` is called as ``factory(frame, taxsim_path=path)``
        when a binary locator is active and ``factory(frame)`` otherwise. The
        default (no factory) always locates verified bytes with
        ``pins.locate_binary``; an injected factory skips binary lookup unless
        ``binary_locator`` is also given (test seam).
        """
        self.runner_factory = runner_factory
        self.id_column = id_column
        self.pin_profile = pin_profile
        self.platform = platform
        if binary_locator is None and runner_factory is None:
            binary_locator = pins.locate_binary
        self.binary_locator = binary_locator
        self.max_crash_reruns = max_crash_reruns
        self.crash_log: list[dict[str, Any]] = []
        self._profile_name: str | None = None
        self._binary_usage: dict[tuple[str, str], int] = {}
        self._build_observed: dict[str, str | None] = {}

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        input_rows = self._input_rows(cases)
        target_variables = self._target_variables(variables)
        if not self._uses_pinned_taxsim_binary():
            input_frame = self._frame_from_rows(input_rows)
            runner = self._runner_factory()(input_frame)
            output = self._run_runner(runner)
            return self._engine_results(output, cases, target_variables, input_rows)
        return self._run_pinned(cases, input_rows, target_variables)

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

    # ------------------------------------------------------------------
    # Pinned-binary execution

    def _uses_pinned_taxsim_binary(self) -> bool:
        return type(self)._runner_factory is TaxsimPackageRunner._runner_factory

    def resolved_pin_profile(self) -> str:
        """The active pin profile (explicit > env > default), resolved once."""
        if self._profile_name is None:
            self._profile_name = pins.active_profile_name(self.pin_profile)
        return self._profile_name

    def taxsim_identity(self) -> dict[str, Any] | None:
        """C1 identity: the pin profile and each binary's row count so far."""
        if not self._binary_usage:
            return None
        doc = pins.pin_document()
        binaries = []
        for (sha, scope), rows in self._binary_usage.items():
            binary = doc.binaries[sha]
            binaries.append(
                {
                    "sha256": sha,
                    "build": binary.build,
                    "build_observed": self._build_observed.get(sha),
                    "platform": binary.platform,
                    "bytes": binary.bytes,
                    "rows": rows,
                    "scope": scope,
                }
            )
        binaries.sort(
            key=lambda item: (
                item["scope"] != pins.DEFAULT_SCOPE,
                item["scope"],
                item["sha256"],
            )
        )
        return {"pin_profile": self.resolved_pin_profile(), "binaries": binaries}

    def _run_pinned(
        self,
        cases: list[Case],
        input_rows: list[dict[str, Any]],
        variables: list[str] | None,
    ) -> list[EngineResult]:
        profile = pins.get_profile(self.resolved_pin_profile())
        system = pins.normalize_platform(self.platform)
        partitions: dict[str, list[int]] = {}
        scopes: list[str] = []
        for index, row in enumerate(input_rows):
            if row.get("year") is None:
                raise pins.TaxsimPinError(
                    f"case {cases[index].case_id!r}: TAXSIM row has no year, "
                    "so no pinned binary can be resolved"
                )
            # A missing state column is filled with 0 (TAXSIM "no state") by
            # policyengine-taxsim's input formatter; resolve it the same way.
            resolution = profile.resolve(row.get("state", 0), row["year"], system)
            partitions.setdefault(resolution.sha256, []).append(index)
            scopes.append(resolution.scope)

        # Locate every partition's verified bytes before running any, so a
        # missing or mismatched binary fails the batch without partial runs.
        binary_paths: dict[str, Any] = {}
        for sha, indices in partitions.items():
            first = input_rows[indices[0]]
            binary_paths[sha] = (
                self.binary_locator(
                    sha,
                    profile=profile.name,
                    state=first.get("state", 0),
                    year=first.get("year"),
                )
                if self.binary_locator is not None
                else None
            )
            if binary_paths[sha] is not None and sha not in self._build_observed:
                self._build_observed[sha] = pins.read_build_stamp(binary_paths[sha])

        for sha, indices in partitions.items():
            for index in indices:
                key = (sha, scopes[index])
                self._binary_usage[key] = self._binary_usage.get(key, 0) + 1

        results_by_index: dict[int, list[EngineResult]] = {}
        unmatched: list[EngineResult] = []
        for sha, indices in partitions.items():
            successes, failures = self._run_isolated(
                indices, input_rows, binary_paths[sha], sha
            )
            for chunk, output, bisected in successes:
                chunk_cases = [cases[i] for i in chunk]
                chunk_rows = [input_rows[i] for i in chunk]
                index_by_case_id = {
                    _id_key(cases[i].case_id): i for i in chunk
                }
                for result in self._engine_results(
                    output, chunk_cases, variables, chunk_rows
                ):
                    stamped = _stamp(result, sha, bisected)
                    index = index_by_case_id.get(_id_key(result.household_id))
                    if index is None:
                        unmatched.append(stamped)
                    else:
                        results_by_index.setdefault(index, []).append(stamped)
            for index, error, isolation in failures:
                results_by_index.setdefault(index, []).append(
                    self._crash_result(cases[index], error, sha, isolation)
                )

        ordered: list[EngineResult] = []
        for index in range(len(cases)):
            ordered.extend(results_by_index.get(index, []))
        ordered.extend(unmatched)
        return ordered

    def _run_isolated(
        self,
        indices: list[int],
        input_rows: list[dict[str, Any]],
        binary_path: Any,
        sha: str,
    ) -> tuple[
        list[tuple[list[int], Any, bool]],
        list[tuple[int, TaxsimExecutionError, str]],
    ]:
        """Run one partition, bisecting on executable failure.

        A failed run is split at its midpoint (input order) and each half is
        re-run, left first, until a failing run is a single row. Every run
        after the first counts against ``max_crash_reruns``; the split depth
        is at most ceil(log2(n)) + 1. Rows whose single-row run fails get a
        ``taxsim-crash`` error (isolation ``single-row``); rows left when the
        budget or depth bound runs out get the failure of the smallest run
        that contained them (isolation ``budget-exhausted``). Rows that
        succeed in a sub-run keep those outputs and are marked ``bisected``.

        TAXSIM failures can depend on record order (policyengine-taxsim
        #1214: a Delaware record followed by a Maryland record crashes the
        September Linux build; either alone or reversed succeeds), so a
        failure can vanish once its rows are split. The split sequence is a
        fixed function of the input order, so the outcome is deterministic
        for a given input and binary; a bisected row's output comes from a
        smaller run than its partition and need not equal what the full run
        would have produced.
        """
        successes: list[tuple[list[int], Any, bool]] = []
        failures: list[tuple[int, TaxsimExecutionError, str]] = []
        max_depth = math.ceil(math.log2(len(indices))) + 1 if len(indices) > 1 else 0
        reruns = 0
        stack: list[tuple[list[int], int, TaxsimExecutionError | None]] = [
            (list(indices), 0, None)
        ]
        while stack:
            chunk, depth, parent_error = stack.pop()
            if depth > 0:
                if reruns >= self.max_crash_reruns or depth > max_depth:
                    assert parent_error is not None
                    failures.extend(
                        (index, parent_error, "budget-exhausted") for index in chunk
                    )
                    continue
                reruns += 1
            try:
                output = self._execute_chunk(chunk, input_rows, binary_path)
            except TaxsimExecutionError as error:
                self.crash_log.append(
                    {
                        "binary_sha256": sha,
                        "rows": len(chunk),
                        "depth": depth,
                        "signature": error.signature,
                        "returncode": error.returncode,
                    }
                )
                if len(chunk) == 1:
                    failures.append((chunk[0], error, "single-row"))
                    continue
                middle = len(chunk) // 2
                stack.append((chunk[middle:], depth + 1, error))
                stack.append((chunk[:middle], depth + 1, error))
                continue
            successes.append((chunk, output, depth > 0))
        return successes, failures

    def _execute_chunk(
        self,
        chunk: list[int],
        input_rows: list[dict[str, Any]],
        binary_path: Any,
    ) -> Any:
        frame = self._frame_from_rows([input_rows[index] for index in chunk])
        factory = self._runner_factory()
        if binary_path is not None:
            runner = factory(frame, taxsim_path=binary_path)
        else:
            runner = factory(frame)
        return self._run_runner(runner)

    def _crash_result(
        self,
        case: Case,
        error: TaxsimExecutionError,
        sha: str,
        isolation: str,
    ) -> EngineResult:
        return EngineResult(
            engine=self.name,
            household_id=case.case_id,
            values={},
            raw={
                "taxsim_error": {
                    "signature": error.signature,
                    "returncode": error.returncode,
                    "stderr_tail": error.stderr_tail,
                    "binary_sha256": sha,
                    "isolation": isolation,
                }
            },
            errors=(f"taxsim-crash:{error.signature}",),
        )

    def _runner_factory(self) -> Callable[..., Any]:
        if self.runner_factory is not None:
            return self.runner_factory
        try:
            return pinned_taxsim_runner_class()
        except ImportError as exc:
            raise RuntimeError(
                "Could not import policyengine-taxsim's TaxsimRunner. Install "
                "the package or pass runner_factory=..."
            ) from exc

    # ------------------------------------------------------------------
    # Input rows and result mapping

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


def _stamp(result: EngineResult, sha: str, bisected: bool) -> EngineResult:
    raw = dict(result.raw) if isinstance(result.raw, Mapping) else {"record": result.raw}
    raw["taxsim_binary_sha256"] = sha
    if bisected:
        raw["taxsim_rerun"] = "bisected"
    return replace(result, raw=raw)


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
