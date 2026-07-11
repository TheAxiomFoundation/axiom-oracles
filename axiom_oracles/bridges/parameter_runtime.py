"""Live Axiom execution helper for parameter-oracle comparison scripts."""

from __future__ import annotations

from pathlib import Path

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.core.case import Case

from .rulespec_paths import (
    require_rulespec_module,
    require_axiom_binary,
    require_rulespec_checkout,
)


def evaluate_rulespec_outputs(
    program: Path,
    outputs: list[str] | tuple[str, ...],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
    period: str,
    entity: str = "TaxUnit",
) -> dict[str, float | bool | str | None]:
    """Compile and execute one canonical module for its exact output IDs."""

    checkout = require_rulespec_checkout(rulespec_root)
    binary = require_axiom_binary(axiom_binary)
    program = require_rulespec_module(program, checkout)
    requested = tuple(outputs)
    if not requested:
        return {}
    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=binary,
        rulespec_root=checkout,
        default_entity=entity,
        default_entity_id="oracle_entity",
    )
    [result] = runner.run_cases(
        [
            Case(
                case_id="parameter-oracle",
                period=period,
                metadata={
                    "axiom_entity": entity,
                    "axiom_entity_id": "oracle_entity",
                },
                outputs=requested,
            )
        ],
        list(requested),
    )
    if result.errors:
        raise RuntimeError(f"Axiom RuleSpec execution failed: {result.errors}")
    missing = [output for output in requested if output not in result.values]
    if missing:
        raise RuntimeError(f"Axiom RuleSpec outputs missing: {missing}")
    return {output: result.values[output] for output in requested}


def evaluate_rulespec_formulas(
    module_ref: str,
    formulas: list[str] | tuple[str, ...],
    *,
    rulespec_root: Path,
    axiom_binary: Path,
    period: str,
) -> list[float]:
    """Execute numeric projection formulas over one imported module."""

    if ":" not in module_ref or "#" in module_ref:
        raise ValueError(f"invalid absolute RuleSpec module reference: {module_ref!r}")
    checkout = require_rulespec_checkout(rulespec_root)
    binary = require_axiom_binary(axiom_binary)
    prefix = module_ref.split(":", 1)[0]
    target = f"{prefix}:programs/oracle-parameter-runtime"
    rules = tuple(
        {
            "name": f"oracle_value_{index}",
            "kind": "derived",
            "entity": "TaxUnit",
            "dtype": "Decimal",
            "period": "Year",
            "source": "Axiom oracle parameter projection",
            "versions": [
                {
                    "effective_from": "1900-01-01",
                    "formula": formula,
                }
            ],
        }
        for index, formula in enumerate(formulas)
    )
    outputs = tuple(f"{target}#oracle_value_{index}" for index in range(len(rules)))
    runner = AxiomRulesRunner(
        binary_path=binary,
        rulespec_root=checkout,
        program_imports=(module_ref,),
        program_rules=rules,
        generated_program_target=target,
        default_entity="TaxUnit",
        default_entity_id="oracle_entity",
    )
    [result] = runner.run_cases(
        [
            Case(
                case_id="parameter-oracle",
                period=period,
                outputs=outputs,
            )
        ],
        list(outputs),
    )
    if result.errors:
        raise RuntimeError(f"Axiom RuleSpec execution failed: {result.errors}")
    return [float(result.values[output]) for output in outputs]
