from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from numbers import Integral, Real
from typing import Any

from ...comparison.mappings import load_program_mappings
from ...core.case import Case
from ...core.results import EngineResult
from ..taxsim.pins import PINS_PATH, pinned_version
from ..taxsim.projection import TAXSIM_MSTAT_SEPARATE, _mstat_code
from ..taxsim.runner import TaxsimPackageRunner, _records

# The emulator's mstat-6 capability marker (a constant equal to 6). The
# policyengine-taxsim change that adds it builds an mstat 6 row as a
# single-person tax unit whose head is ``is_separated``. The pinned 2.30.0
# lacks it: its batch PolicyEngineRunner puts a spouse in every mstat 2 or 6
# row (``has_spouse = np.isin(mstat, [2, 6])`` in
# runners/policyengine_runner.py) and never sets ``is_separated``, so its
# values for an mstat 6 row are a couple's, not one spouse's separate return.
MARRIED_SEPARATE_CAPABILITY = (
    "policyengine_taxsim.core.input_mapper.MSTAT_MARRIED_SEPARATE"
)


class PolicyEngineTaxsimRunner(TaxsimPackageRunner):
    """Run PolicyEngine through policyengine-taxsim TAXSIM-row projection.

    This is the right PE runner for a PE-vs-TAXSIM oracle comparison because
    both engines receive the same TAXSIM-format input row.

    Rows with TAXSIM mstat 6 (married filing separately) run only when the
    installed emulator exports :data:`MARRIED_SEPARATE_CAPABILITY`, or when
    ``married_separate_supported=True`` is passed. Otherwise each such case
    returns an :class:`EngineResult` with no values and an error naming the
    missing capability and the TAXSIM pin, and only the remaining rows reach
    the emulator.
    """

    name = "policyengine"

    def __init__(
        self,
        runner_factory: Callable[[Any], Any] | None = None,
        *,
        id_column: str = "taxsimid",
        married_separate_supported: bool | None = None,
    ) -> None:
        super().__init__(runner_factory=runner_factory, id_column=id_column)
        # None means "ask the installed policyengine-taxsim"; tests inject a
        # fake runner_factory and pin the capability explicitly.
        self.married_separate_supported = married_separate_supported

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        input_rows = self._input_rows(cases)
        separate = [
            _mstat_code(row.get("mstat")) == TAXSIM_MSTAT_SEPARATE for row in input_rows
        ]
        if not any(separate) or self._supports_married_separate():
            return self._run_rows(cases, input_rows, variables)

        error = married_separate_unsupported_error()
        gated = [
            EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values={},
                errors=(error,),
            )
            for case, is_separate in zip(cases, separate, strict=True)
            if is_separate
        ]
        runnable = [
            (case, row)
            for case, row, is_separate in zip(cases, input_rows, separate, strict=True)
            if not is_separate
        ]
        if not runnable:
            return gated
        results = self._run_rows(
            [case for case, _ in runnable],
            [row for _, row in runnable],
            variables,
        )
        # Keep the callers' case order; a result whose id matches no case
        # sorts last and is left for the comparator's id check to reject.
        position = {case.case_id: index for index, case in enumerate(cases)}
        return sorted(
            [*results, *gated],
            key=lambda result: position.get(result.household_id, len(position)),
        )

    def _supports_married_separate(self) -> bool:
        if self.married_separate_supported is not None:
            return self.married_separate_supported
        return emulator_supports_married_separate()

    def _runner_factory(self) -> Callable[[Any], Any]:
        if self.runner_factory is not None:
            return self.runner_factory
        for module_name, attr_name in (
            ("policyengine_taxsim.runners.policyengine_runner", "PolicyEngineRunner"),
            ("policyengine_taxsim.runners", "PolicyEngineRunner"),
            ("policyengine_taxsim", "PolicyEngineRunner"),
        ):
            try:
                module = import_module(module_name)
            except ImportError:
                continue
            runner = getattr(module, attr_name, None)
            if runner is not None:
                return runner
        raise RuntimeError(
            "Could not import policyengine-taxsim's PolicyEngineRunner. Install "
            "the package or pass runner_factory=..."
        )

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
                    values=_selected_policyengine_values(record, variables),
                    raw=record,
                )
            )
        return results


def emulator_supports_married_separate() -> bool:
    """Whether the installed policyengine-taxsim exports the mstat-6 marker."""

    try:
        module = import_module("policyengine_taxsim.core.input_mapper")
    except ImportError:
        return False
    marker = getattr(module, "MSTAT_MARRIED_SEPARATE", None)
    return marker == TAXSIM_MSTAT_SEPARATE


def married_separate_unsupported_error() -> str:
    """The per-case error for an mstat 6 row the emulator cannot run."""

    try:
        installed = version("policyengine-taxsim")
    except PackageNotFoundError:
        installed = "not installed"
    return (
        "policyengine-taxsim emulator lacks TAXSIM mstat 6 (married filing "
        f"separately) support: {MARRIED_SEPARATE_CAPABILITY} is not exported "
        f"(installed policyengine-taxsim: {installed}; pinned: "
        f"{pinned_version()} in {PINS_PATH.name}). Not run, rather than "
        "return a two-adult household's values; re-pin policyengine-taxsim "
        "to a release that exports the marker."
    )


def _selected_policyengine_values(
    record: Mapping[str, Any],
    variables: list[str] | None,
) -> dict[str, Any]:
    if variables is None:
        return {
            key: value
            for key, value in record.items()
            if key not in {"taxsimid", "year", "state"}
        }

    pairs = _taxsim_to_policyengine_pairs(variables)
    values: dict[str, Any] = {}
    for taxsim_target, policyengine_target in pairs.items():
        if taxsim_target in record:
            values[policyengine_target] = record[taxsim_target]
    return values


def _taxsim_to_policyengine_pairs(variables: list[str]) -> dict[str, str]:
    """Map TAXSIM output columns to the PolicyEngine names the comparator reads.

    Mappings are visited in file order and each TAXSIM column is claimed by
    the first requested mapping that carries it, so canonical concepts
    (declared before suite-specific blocks) win shared columns — e.g.
    ``siitax`` belongs to ``us:tax/state-income-tax#liability``, not to
    whichever state pilot concept happens to be requested last. When the
    PolicyEngine target is a summed list (``tax_before_credits``,
    ``employee_fica``), its first component carries the TAXSIM aggregate:
    the comparator sums the components that are present, so the
    concept-level value reproduces the aggregate exactly.
    """
    requested = set(variables)
    pairs: dict[str, str] = {}
    for mapping in load_program_mappings():
        policyengine_target = mapping.target_for_engine("policyengine")
        taxsim_target = mapping.target_for_engine("taxsim")
        if not isinstance(taxsim_target, str) or taxsim_target in pairs:
            continue
        if isinstance(policyengine_target, str):
            carrier = policyengine_target
            keys = {mapping.concept_id, policyengine_target, taxsim_target}
        elif isinstance(policyengine_target, list) and policyengine_target:
            carrier = policyengine_target[0]
            keys = {mapping.concept_id, taxsim_target, *policyengine_target}
        else:
            continue
        if requested & keys:
            pairs[taxsim_target] = carrier
    return pairs


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
