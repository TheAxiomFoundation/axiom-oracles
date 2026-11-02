#!/usr/bin/env python
"""Fail closed when the all-state Populace projection contract drifts."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

from axiom_oracles.bridges.state_tax_populace import (
    StateTaxPopulaceContractError,
    load_state_tax_populace_contract,
    readiness_summary,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="Optional contract override; defaults to the packaged registry.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract = load_state_tax_populace_contract(args.contract)
        _validate_generator_registry(contract)
        summary = readiness_summary(contract)
    except (OSError, StateTaxPopulaceContractError) as exc:
        print(f"state-tax-populace contract invalid: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "state-tax-populace contract OK: "
            f"{summary['jurisdiction_count']} jurisdictions, "
            f"{summary['ready_count']} ready, "
            f"{summary['blocked_count']} blocked, "
            f"{summary['explicit_input_count']} explicit inputs, "
            f"{summary['explicit_relation_count']} explicit relations"
        )
    return 0


def _validate_generator_registry(contract) -> None:
    """Recompute comparison metadata from the declared campaign generator."""

    generator_path = REPO_ROOT / contract.registry_source
    spec = importlib.util.spec_from_file_location(
        "state_income_tax_populace_registry_source",
        generator_path,
    )
    if spec is None or spec.loader is None:
        raise StateTaxPopulaceContractError(
            f"cannot load registry source {generator_path}"
        )
    generator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = generator
    spec.loader.exec_module(generator)

    errors: list[str] = []
    states = tuple(item.state for item in contract.jurisdictions)
    registry_states = getattr(generator, "_POPULACE_STATES", generator._STATES)
    if set(states) != set(registry_states):
        errors.append("jurisdiction set differs from generator Populace states")
    if contract.validation_year != generator.VALIDATION_YEAR:
        errors.append("validation year differs from generator VALIDATION_YEAR")
    for item in contract.jurisdictions:
        state = item.state
        generated = (
            generator._TAXSIM_STATE.get(state),
            getattr(generator, "_POPULACE_MODULE", {}).get(
                state, generator._MODULE.get(state)
            ),
            getattr(generator, "_POPULACE_OUTPUT", {}).get(
                state, generator._LIABILITY_OUTPUT.get(state)
            ),
            getattr(generator, "_POPULACE_PE_VAR", {}).get(
                state, generator._PE_VAR.get(state)
            ),
            getattr(generator, "_POPULACE_TOL", {}).get(
                state, generator._TOL.get(state)
            ),
            getattr(generator, "_POPULACE_AGGREGATION", {}).get(
                state, "tax_unit"
            ),
        )
        expected = (
            item.taxsim_state_code,
            item.program,
            item.output,
            item.policyengine_target,
            (item.tolerance, item.relative_tolerance),
            item.comparison_aggregation,
        )
        if generated != expected:
            errors.append(f"{state} registry metadata differs from generator")
    if errors:
        raise StateTaxPopulaceContractError("; ".join(errors))


if __name__ == "__main__":
    raise SystemExit(main())
