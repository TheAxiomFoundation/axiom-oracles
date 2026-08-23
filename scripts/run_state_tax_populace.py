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
    DISPOSITION_READY,
    NO_BROAD_PIT_FIPS,
    calculate_policyengine_targets,
    calculate_policyengine_projection_inputs,
    calculate_taxsim_targets,
    compare_ready_state_tax_units,
    population_routing_report,
    route_tax_units,
    runtime_provenance,
    validate_campaign_dataset_identity,
)

_UT_INPUT_PREFIX = (
    "us-ut:policies/income_tax/"
    "2026_full_year_resident_before_credit_schedule#input."
)
_DC_TAXABLE_INCOME_INPUT = (
    "us-dc:policies/income_tax/"
    "2026_section_47_1806_03_schedule_before_credits#input."
    "dc_pit_2026_section_47_1806_03_completed_joint_method_taxable_income"
)
_CA_TAXABLE_INCOME_INPUT = (
    "us-ca:policies/income_tax/pilot_liability_pipeline#input."
    "ca_pit_pilot_supplied_completed_taxable_income"
)
_CA_BHST_THRESHOLD = 1_000_000.0
_IL_INPUT_PREFIX = (
    "us-il:policies/income_tax/pilot_liability_pipeline#input."
)
_IL_TAXABLE_INCOME_INPUT = (
    f"{_IL_INPUT_PREFIX}il_pit_pilot_state_taxable_income"
)
_IL_RECAPTURE_INPUT = (
    f"{_IL_INPUT_PREFIX}il_pit_pilot_recapture_of_investment_credit"
)
_IN_AGI_INPUT = (
    "us-in:policies/income_tax/pilot_liability_pipeline#input."
    "in_pit_pilot_indiana_adjusted_gross_income"
)
_PA_ADJUSTED_TAXABLE_INCOME_INPUT = (
    "us-pa:policies/income_tax/pilot_liability_pipeline#input."
    "pa_pit_pilot_state_taxable_income"
)
_SC_TAXABLE_INCOME_INPUT = (
    "us-sc:policies/income_tax/pilot_liability_pipeline#input."
    "sc_pit_pilot_state_taxable_income"
)
_NY_INPUT_PREFIX = (
    "us-ny:policies/income_tax/pilot_liability_pipeline#input."
)
_NY_TAXABLE_INCOME_INPUT = (
    f"{_NY_INPUT_PREFIX}ny_pit_pilot_state_taxable_income"
)
_NY_JOINT_OR_SURVIVING_INPUT = (
    f"{_NY_INPUT_PREFIX}"
    "ny_pit_pilot_filing_status_joint_or_surviving_spouse"
)
_NY_HEAD_OF_HOUSEHOLD_INPUT = (
    f"{_NY_INPUT_PREFIX}ny_pit_pilot_filing_status_head_of_household"
)


def _projection_branch_diagnostics(
    projection_inputs: dict,
    routes: tuple,
    policyengine_targets: dict | None = None,
) -> dict[str, dict[str, int]]:
    """Summarize reviewed state branch exercise without exposing microdata."""

    diagnostics: dict[str, dict[str, int]] = {}
    california = projection_inputs.get("CA")
    if isinstance(california, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "CA" and route.disposition == DISPOSITION_READY
        }
        taxable_values = california[_CA_TAXABLE_INCOME_INPUT]
        selected_values = [
            float(taxable_values[tax_unit_id]) for tax_unit_id in ready_ids
        ]
        diagnostics["CA"] = {
            "compared_tax_unit_count": len(ready_ids),
            "zero_behavioral_health_services_tax_count": sum(
                value <= _CA_BHST_THRESHOLD for value in selected_values
            ),
            "positive_behavioral_health_services_tax_count": sum(
                value > _CA_BHST_THRESHOLD for value in selected_values
            ),
        }
    dc = projection_inputs.get("DC")
    if isinstance(dc, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "DC" and route.disposition == DISPOSITION_READY
        }
        taxable_values = dc[_DC_TAXABLE_INCOME_INPUT]
        selected_values = [
            float(taxable_values[tax_unit_id]) for tax_unit_id in ready_ids
        ]
        diagnostics["DC"] = {
            "compared_tax_unit_count": len(ready_ids),
            "negative_taxable_income_count": sum(
                value < 0 for value in selected_values
            ),
            "zero_taxable_income_count": sum(
                value == 0 for value in selected_values
            ),
            "positive_taxable_income_count": sum(
                value > 0 for value in selected_values
            ),
        }
    illinois = projection_inputs.get("IL")
    if isinstance(illinois, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "IL" and route.disposition == DISPOSITION_READY
        }
        taxable_values = illinois[_IL_TAXABLE_INCOME_INPUT]
        recapture_values = illinois[_IL_RECAPTURE_INPUT]
        taxable = [float(taxable_values[item]) for item in ready_ids]
        recapture = [float(recapture_values[item]) for item in ready_ids]
        if any(value < 0 for value in taxable):
            raise ValueError(
                "IL projection diagnostics require nonnegative completed "
                "taxable income"
            )
        if any(value < 0 for value in recapture):
            raise ValueError(
                "IL projection diagnostics require nonnegative completed "
                "investment-credit recapture"
            )
        diagnostics["IL"] = {
            "compared_tax_unit_count": len(ready_ids),
            "zero_taxable_income_count": sum(value == 0 for value in taxable),
            "positive_taxable_income_count": sum(value > 0 for value in taxable),
            "zero_recapture_count": sum(value == 0 for value in recapture),
            "positive_recapture_count": sum(value > 0 for value in recapture),
        }
    indiana = projection_inputs.get("IN")
    if isinstance(indiana, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "IN" and route.disposition == DISPOSITION_READY
        }
        agi_values = indiana[_IN_AGI_INPUT]
        target_values = (
            (policyengine_targets or {}).get("IN")
            if isinstance(policyengine_targets, dict)
            else None
        )
        if not isinstance(target_values, dict):
            raise ValueError(
                "IN projection diagnostics require the reviewed in_agi_tax "
                "target values"
            )
        missing_agi = sorted(ready_ids - set(agi_values), key=str)
        missing_targets = sorted(ready_ids - set(target_values), key=str)
        if missing_agi or missing_targets:
            raise ValueError(
                "IN projection diagnostics require AGI and output values for "
                "every ready TaxUnit"
            )
        agi = [float(agi_values[item]) for item in ready_ids]
        outputs = [float(target_values[item]) for item in ready_ids]
        diagnostics["IN"] = {
            "compared_tax_unit_count": len(ready_ids),
            "nonpositive_agi_count": sum(value <= 0 for value in agi),
            "positive_agi_count": sum(value > 0 for value in agi),
            "zero_output_count": sum(value == 0 for value in outputs),
            "positive_output_count": sum(value > 0 for value in outputs),
        }
    pennsylvania = projection_inputs.get("PA")
    if isinstance(pennsylvania, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "PA" and route.disposition == DISPOSITION_READY
        }
        taxable_values = pennsylvania[_PA_ADJUSTED_TAXABLE_INCOME_INPUT]
        target_values = (
            (policyengine_targets or {}).get("PA")
            if isinstance(policyengine_targets, dict)
            else None
        )
        if not isinstance(target_values, dict):
            raise ValueError(
                "PA projection diagnostics require the reviewed "
                "pa_income_tax_before_forgiveness target values"
            )
        missing_taxable = sorted(ready_ids - set(taxable_values), key=str)
        missing_targets = sorted(ready_ids - set(target_values), key=str)
        if missing_taxable or missing_targets:
            raise ValueError(
                "PA projection diagnostics require adjusted taxable income and "
                "output values for every ready TaxUnit"
            )
        taxable = [float(taxable_values[item]) for item in ready_ids]
        outputs = [float(target_values[item]) for item in ready_ids]
        if any(value < 0 for value in taxable):
            raise ValueError(
                "PA projection diagnostics require nonnegative adjusted "
                "taxable income for every ready TaxUnit"
            )
        if any(value < 0 for value in outputs):
            raise ValueError(
                "PA projection diagnostics require nonnegative "
                "before-forgiveness tax for every ready TaxUnit"
            )
        diagnostics["PA"] = {
            "compared_tax_unit_count": len(ready_ids),
            "negative_adjusted_taxable_income_count": 0,
            "zero_adjusted_taxable_income_count": sum(
                value == 0 for value in taxable
            ),
            "positive_adjusted_taxable_income_count": sum(
                value > 0 for value in taxable
            ),
            "zero_output_count": sum(value == 0 for value in outputs),
            "positive_output_count": sum(value > 0 for value in outputs),
        }
    south_carolina = projection_inputs.get("SC")
    if isinstance(south_carolina, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "SC" and route.disposition == DISPOSITION_READY
        }
        taxable_values = south_carolina[_SC_TAXABLE_INCOME_INPUT]
        target_values = (
            (policyengine_targets or {}).get("SC")
            if isinstance(policyengine_targets, dict)
            else None
        )
        if not isinstance(target_values, dict):
            raise ValueError(
                "SC projection diagnostics require the reviewed "
                "sc_income_tax_before_non_refundable_credits target values"
            )
        missing_taxable = sorted(ready_ids - set(taxable_values), key=str)
        missing_targets = sorted(ready_ids - set(target_values), key=str)
        if missing_taxable or missing_targets:
            raise ValueError(
                "SC projection diagnostics require taxable income and output "
                "values for every ready TaxUnit"
            )
        taxable = [float(taxable_values[item]) for item in ready_ids]
        outputs = [float(target_values[item]) for item in ready_ids]
        if any(value < 0 for value in taxable):
            raise ValueError(
                "SC projection diagnostics require nonnegative South Carolina "
                "taxable income for every ready TaxUnit"
            )
        if any(value < 0 for value in outputs):
            raise ValueError(
                "SC projection diagnostics require nonnegative tax before "
                "nonrefundable credits for every ready TaxUnit"
            )
        diagnostics["SC"] = {
            "compared_tax_unit_count": len(ready_ids),
            "negative_taxable_income_count": 0,
            "zero_taxable_income_count": sum(value == 0 for value in taxable),
            "positive_taxable_income_count": sum(value > 0 for value in taxable),
            "zero_output_count": sum(value == 0 for value in outputs),
            "positive_output_count": sum(value > 0 for value in outputs),
        }
    new_york = projection_inputs.get("NY")
    if isinstance(new_york, dict):
        ready_ids = {
            route.tax_unit_id
            for route in routes
            if route.state == "NY" and route.disposition == DISPOSITION_READY
        }
        taxable_values = new_york[_NY_TAXABLE_INCOME_INPUT]
        joint_values = new_york[_NY_JOINT_OR_SURVIVING_INPUT]
        head_values = new_york[_NY_HEAD_OF_HOUSEHOLD_INPUT]
        taxable = [float(taxable_values[item]) for item in ready_ids]
        joint_or_surviving_count = 0
        head_of_household_count = 0
        single_or_separate_count = 0
        for tax_unit_id in ready_ids:
            joint = joint_values[tax_unit_id]
            head = head_values[tax_unit_id]
            if type(joint) is not bool or type(head) is not bool:
                raise ValueError(
                    "NY projection diagnostics require strict Boolean filing "
                    "status values for every ready TaxUnit"
                )
            if joint and head:
                raise ValueError(
                    "NY projection diagnostics require mutually exclusive "
                    "filing-status schedule values"
                )
            joint_or_surviving_count += joint
            head_of_household_count += head
            single_or_separate_count += not joint and not head
        diagnostics["NY"] = {
            "compared_tax_unit_count": len(ready_ids),
            "negative_taxable_income_count": sum(value < 0 for value in taxable),
            "zero_taxable_income_count": sum(value == 0 for value in taxable),
            "positive_taxable_income_count": sum(value > 0 for value in taxable),
            "joint_or_surviving_count": joint_or_surviving_count,
            "head_of_household_count": head_of_household_count,
            "single_or_separate_count": single_or_separate_count,
        }
    utah = projection_inputs.get("UT")
    if not isinstance(utah, dict):
        return diagnostics
    ready_ids = {
        route.tax_unit_id
        for route in routes
        if route.state == "UT" and route.disposition == DISPOSITION_READY
    }
    exempt_values = utah[
        f"{_UT_INPUT_PREFIX}ut_pit_2026_is_exempt_under_section_59_10_104_1"
    ]
    taxable_values = utah[
        f"{_UT_INPUT_PREFIX}ut_pit_2026_state_taxable_income"
    ]
    exempt_count = sum(exempt_values[tax_unit_id] is True for tax_unit_id in ready_ids)
    nonexempt_count = sum(
        exempt_values[tax_unit_id] is False for tax_unit_id in ready_ids
    )
    if exempt_count + nonexempt_count != len(ready_ids):
        raise ValueError(
            "UT projection diagnostics require strict Boolean exemption values "
            "for every ready TaxUnit"
        )
    diagnostics["UT"] = {
        "compared_tax_unit_count": len(ready_ids),
        "exempt_count": exempt_count,
        "nonexempt_count": nonexempt_count,
        "negative_taxable_income_count": sum(
            float(taxable_values[tax_unit_id]) < 0
            for tax_unit_id in ready_ids
        ),
    }
    return diagnostics


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
    parser.add_argument(
        "--no-taxsim",
        action="store_true",
        help=(
            "Skip the TAXSIM oracle leg. By default every ready state is "
            "also graded against the pinned policyengine-taxsim binary "
            "(adapters/taxsim/taxsim_pins.json); the run fails if the "
            "package is missing rather than silently dropping the leg."
        ),
    )
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

    # One Microsimulation shared across the three calculators: each builds
    # its own by default, and two-to-three concurrent full-population sims
    # OOM-killed every full campaign attempt on 2026-08-24. The calculators
    # only ever .calculate() — sharing is read-only.
    _shared_sim: dict = {}

    def _shared_microsimulation(source):
        if "sim" not in _shared_sim:
            from policyengine_us import Microsimulation

            _shared_sim["sim"] = Microsimulation(dataset=source)
        return _shared_sim["sim"]

    targets = calculate_policyengine_targets(
        dataset=dataset,
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        routes=comparison_routes,
        year=args.year,
        contract=contract,
        microsimulation_factory=_shared_microsimulation,
    )
    projection_inputs = calculate_policyengine_projection_inputs(
        dataset=dataset,
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        routes=comparison_routes,
        year=args.year,
        contract=contract,
        microsimulation_factory=_shared_microsimulation,
    )
    taxsim_targets = None
    if not args.no_taxsim:
        taxsim_targets = calculate_taxsim_targets(
            dataset=dataset,
            raw_tax_units=raw_tax_units,
            raw_persons=raw_persons,
            routes=comparison_routes,
            year=args.year,
            contract=contract,
            microsimulation_factory=_shared_microsimulation,
        )
    report = {
        "schema_version": "axiom.state_tax_populace_campaign_report.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/run_state_tax_populace.py",
        "run_kind": resolve_run_kind(),
        "requested_states": sorted(requested_states),
        "dataset_identity": identity,
        "runtime_provenance": runtime_provenance(
            rulespec_root=args.rulespec_root.resolve(),
            axiom_rules_path=args.axiom_rules_path.resolve(),
        ),
        "projection_diagnostics": _projection_branch_diagnostics(
            projection_inputs,
            tuple(comparison_routes),
            targets,
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
            taxsim_targets=taxsim_targets,
            year=args.year,
            rulespec_root=args.rulespec_root.resolve(),
            axiom_rules_path=args.axiom_rules_path.resolve(),
            sample_size_per_state=args.sample_size_per_state,
            contract=contract,
        ),
        "taxsim_leg": (
            "skipped" if args.no_taxsim else "graded"
        ),
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
