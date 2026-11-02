#!/usr/bin/env python
"""Audit all tax units in the pinned US Populace state-tax campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from axiom_oracles.bridges.population import load_populace_dataset, population_table
from axiom_oracles.bridges.state_tax_populace import load_state_tax_populace_contract
from axiom_oracles.bridges.state_tax_populace_runner import (
    population_routing_report,
    route_tax_units,
    validate_campaign_dataset_identity,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--populace-year", type=int, default=2024)
    parser.add_argument("--sample-size-per-state", type=int, default=0)
    parser.add_argument("--output", type=Path)
    return parser


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
    identity: dict = {}
    dataset = load_populace_dataset(
        "us",
        year=args.populace_year,
        command="audit-state-tax-populace",
        provenance=identity,
    )
    validate_campaign_dataset_identity(identity, contract=contract)
    routes = route_tax_units(
        raw_tax_units=population_table(dataset, "tax_unit"),
        raw_persons=population_table(dataset, "person"),
        raw_households=population_table(dataset, "household"),
        contract=contract,
    )
    report = population_routing_report(
        routes,
        sample_size_per_state=args.sample_size_per_state,
        dataset_identity=identity,
        contract=contract,
    )
    report["validation_year"] = args.year
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
