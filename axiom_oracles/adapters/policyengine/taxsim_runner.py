from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from numbers import Integral, Real
from typing import Any

from ...comparison.mappings import load_program_mappings
from ...core.case import Case
from ...core.results import EngineResult
from ..taxsim.runner import TaxsimPackageRunner, _records


class PolicyEngineTaxsimRunner(TaxsimPackageRunner):
    """Run PolicyEngine through policyengine-taxsim TAXSIM-row projection.

    This is the right PE runner for a PE-vs-TAXSIM oracle comparison because
    both engines receive the same TAXSIM-format input row.
    """

    name = "policyengine"

    def __init__(
        self,
        runner_factory: Callable[[Any], Any] | None = None,
        *,
        id_column: str = "taxsimid",
    ) -> None:
        super().__init__(runner_factory=runner_factory, id_column=id_column)

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
    pairs: dict[str, str] = {}
    for requested in variables:
        for mapping in load_program_mappings():
            policyengine_target = mapping.target_for_engine("policyengine")
            taxsim_target = mapping.target_for_engine("taxsim")
            if not isinstance(policyengine_target, str) or not isinstance(
                taxsim_target, str
            ):
                continue
            if requested in {mapping.concept_id, policyengine_target, taxsim_target}:
                pairs[taxsim_target] = policyengine_target
                break
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
