#!/usr/bin/env python
"""Compare every currently ready state over the pinned US Populace."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from axiom_oracles.provenance import resolve_run_kind
from axiom_oracles.bridges.population import load_populace_dataset, population_table
from axiom_oracles.bridges.state_tax_populace import (
    StateTaxPopulaceContract,
    load_state_tax_populace_contract,
)
from axiom_oracles.bridges.state_tax_populace_runner import (
    NO_BROAD_PIT_FIPS,
    calculate_policyengine_targets,
    calculate_policyengine_projection_inputs,
    compare_ready_state_tax_units,
    population_routing_report,
    route_tax_units,
    runtime_provenance,
    validate_campaign_dataset_identity,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--populace-year", type=int, default=2024)
    parser.add_argument("--sample-size-per-state", type=int, default=0)
    parser.add_argument(
        "--state",
        action="append",
        dest="states",
        metavar="STATE",
        help="Restrict execution to one or more state abbreviations; repeatable",
    )
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--axiom-rules-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _requested_states(
    raw_states: list[str] | None, *, contract: StateTaxPopulaceContract
) -> set[str]:
    requested = {state.strip().upper() for state in (raw_states or [])}
    not_applicable = sorted(requested & set(NO_BROAD_PIT_FIPS))
    if not_applicable:
        raise SystemExit(
            "requested state(s) have no broad current PIT: " + ", ".join(not_applicable)
        )
    unknown = sorted(requested - set(contract.by_state()) - set(NO_BROAD_PIT_FIPS))
    if unknown:
        raise SystemExit(
            "unknown campaign state abbreviation(s): " + ", ".join(unknown)
        )
    blocked = sorted(
        state for state in requested if contract.by_state()[state].status != "ready"
    )
    if blocked:
        raise SystemExit(
            "requested campaign state(s) are not ready: " + ", ".join(blocked)
        )
    return requested


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    contract = load_state_tax_populace_contract()
    if args.year != contract.validation_year:
        raise SystemExit(
            f"campaign validation year is {contract.validation_year}, got {args.year}"
        )
    if args.populace_year != contract.populace_year:
        raise SystemExit(
            f"campaign Populace year is {contract.populace_year}, "
            f"got {args.populace_year}"
        )
    requested_states = _requested_states(args.states, contract=contract)
    identity: dict = {}
    dataset = load_populace_dataset(
        "us",
        year=args.populace_year,
        command="run-state-tax-populace",
        provenance=identity,
    )
    validate_campaign_dataset_identity(identity, contract=contract)
    raw_tax_units = population_table(dataset, "tax_unit")
    raw_persons = population_table(dataset, "person")
    routes = route_tax_units(
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        raw_households=population_table(dataset, "household"),
        contract=contract,
    )
    comparison_routes = (
        tuple(route for route in routes if route.state in requested_states)
        if requested_states
        else routes
    )
    targets = calculate_policyengine_targets(
        dataset=dataset,
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        routes=comparison_routes,
        year=args.year,
        contract=contract,
    )
    projection_inputs = calculate_policyengine_projection_inputs(
        dataset=dataset,
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        routes=comparison_routes,
        year=args.year,
        contract=contract,
    )
    report = {
        "schema_version": "axiom.state_tax_populace_campaign_report.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_kind": resolve_run_kind(),
        "requested_states": sorted(requested_states),
        "dataset_identity": identity,
        "runtime_provenance": runtime_provenance(
            rulespec_root=args.rulespec_root.resolve(),
            axiom_rules_path=args.axiom_rules_path.resolve(),
        ),
        "routing": population_routing_report(
            routes,
            sample_size_per_state=args.sample_size_per_state,
            contract=contract,
        ),
        "comparison": compare_ready_state_tax_units(
            routes=comparison_routes,
            raw_persons=raw_persons,
            known_tax_unit_ids={route.tax_unit_id for route in routes},
            policyengine_targets=targets,
            policyengine_projection_inputs=projection_inputs,
            year=args.year,
            rulespec_root=args.rulespec_root.resolve(),
            axiom_rules_path=args.axiom_rules_path.resolve(),
            sample_size_per_state=args.sample_size_per_state,
            contract=contract,
        ),
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
