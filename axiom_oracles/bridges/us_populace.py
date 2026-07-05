"""Generic PE-US Populace comparisons for direct-variable RuleSpec mappings."""

from __future__ import annotations

import argparse
import json
import re
from calendar import monthrange
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .adapters import PolicyEngineUSVarAdapter, get_pe_us_var_adapter
from .ecps_tax import (
    array,
    bool_value,
    input_record,
    money,
    output_number,
    person_entity_id,
    relative_diff,
    require_numpy,
    require_policyengine_versions,
    resolve_rulespec_program_path,
    resolve_workspace_root,
    row_value,
    run_axiom_program,
    within_tolerance,
)
from .population import (
    DEFAULT_US_POPULACE_YEAR,
    format_dataset_identity,
    load_populace_dataset,
    population_table,
)
from .registry import PolicyEngineMapping, load_policyengine_registry

STATE_FIPS_TO_CODE = {
    1: "AL",
    2: "AK",
    4: "AZ",
    5: "AR",
    6: "CA",
    8: "CO",
    9: "CT",
    10: "DE",
    11: "DC",
    12: "FL",
    13: "GA",
    15: "HI",
    16: "ID",
    17: "IL",
    18: "IN",
    19: "IA",
    20: "KS",
    21: "KY",
    22: "LA",
    23: "ME",
    24: "MD",
    25: "MA",
    26: "MI",
    27: "MN",
    28: "MS",
    29: "MO",
    30: "MT",
    31: "NE",
    32: "NV",
    33: "NH",
    34: "NJ",
    35: "NM",
    36: "NY",
    37: "NC",
    38: "ND",
    39: "OH",
    40: "OK",
    41: "OR",
    42: "PA",
    44: "RI",
    45: "SC",
    46: "SD",
    47: "TN",
    48: "TX",
    49: "UT",
    50: "VT",
    51: "VA",
    53: "WA",
    54: "WV",
    55: "WI",
    56: "WY",
}
MONTHLY_PERIOD_KIND = "month"
US_VARIABLE_COMMAND = "us-populace-compare"


@dataclass(frozen=True)
class USVariableCase:
    variable: str
    person_id: int
    spm_unit_id: int | None
    state: str | None
    inputs: dict[str, Any]
    pe_outputs: dict[str, float]


@dataclass(frozen=True)
class USVariableComparisonRow:
    variable: str
    entity_id: str
    output: str
    axiom: float
    policyengine: float
    diff: float
    reason: str | None = None


@dataclass(frozen=True)
class USVariableComparisonReport:
    variables: tuple[str, ...]
    compared_persons: int
    compared_spm_units: int
    compared_values: int
    skipped_cases: int
    skipped_reasons: dict[str, int]
    mismatches: list[USVariableComparisonRow]
    output_summary: list[dict[str, Any]]
    projection_notes: list[str]
    dataset_identity: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "variables": list(self.variables),
            "compared_persons": self.compared_persons,
            "compared_spm_units": self.compared_spm_units,
            "compared_values": self.compared_values,
            "skipped_cases": self.skipped_cases,
            "skipped_reasons": self.skipped_reasons,
            "mismatch_count": len(self.mismatches),
            "mismatches": [row.__dict__ for row in self.mismatches],
            "output_summary": self.output_summary,
            "projection_notes": self.projection_notes,
            "dataset_identity": self.dataset_identity,
        }


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Workspace root containing rulespec-us and axiom-rules-engine",
    )
    parser.add_argument(
        "--rulespec-root",
        type=Path,
        default=None,
        help="rulespec-us checkout; defaults to <root>/rulespec-us",
    )
    parser.add_argument(
        "--axiom-rules-engine-path",
        type=Path,
        default=None,
        help="axiom-rules-engine checkout; defaults to <root>/axiom-rules-engine",
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, default=1)
    parser.add_argument(
        "--variable",
        action="append",
        default=None,
        dest="variables",
        help="PolicyEngine variable to compare. Repeat to compare multiple variables.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of matching Populace cases per variable; 0 compares all cases.",
    )
    parser.add_argument(
        "--person-id",
        type=int,
        action="append",
        default=None,
        dest="person_ids",
        help="Compare specific Populace person_id values.",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Optional two-letter state-code filter. Defaults to adapter state.",
    )
    parser.add_argument(
        "--positive-only",
        action="store_true",
        help="Only compare cases with positive PolicyEngine target output.",
    )
    parser.add_argument(
        "--populace-year",
        type=int,
        default=DEFAULT_US_POPULACE_YEAR,
        help="Published US Populace dataset year to load.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="Absolute tolerance for matching PolicyEngine outputs.",
    )
    parser.add_argument(
        "--relative-tolerance",
        type=float,
        default=2e-7,
        help="Relative tolerance for large floating PolicyEngine intermediates.",
    )
    parser.add_argument("--max-differences", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--allow-policyengine-us-version",
        action="store_true",
        help="Allow the installed policyengine-us version to differ from the oracle baseline.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when any compared value differs beyond tolerance.",
    )
    return parser


def main(args: argparse.Namespace) -> int:
    report = compare_us_populace_variables(
        workspace_root=resolve_workspace_root(args.root),
        rulespec_root=args.rulespec_root,
        axiom_rules_path=args.axiom_rules_engine_path,
        year=args.year,
        month=args.month,
        variables=tuple(args.variables or ()),
        sample_size=args.sample_size,
        person_ids=tuple(args.person_ids or ()),
        state=args.state,
        positive_only=args.positive_only,
        populace_year=args.populace_year,
        tolerance=args.tolerance,
        relative_tolerance=args.relative_tolerance,
        allow_policyengine_us_version=args.allow_policyengine_us_version,
    )
    if args.json:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        print_report(
            report,
            tolerance=args.tolerance,
            relative_tolerance=args.relative_tolerance,
            max_differences=args.max_differences,
        )
    if args.fail_on_mismatch and report.mismatches:
        return 1
    return 0


def compare_us_populace_variables(
    *,
    workspace_root: Path,
    rulespec_root: Path | None,
    axiom_rules_path: Path | None,
    year: int,
    month: int,
    variables: tuple[str, ...],
    sample_size: int,
    person_ids: tuple[int, ...],
    state: str | None,
    positive_only: bool,
    populace_year: int,
    tolerance: float,
    relative_tolerance: float,
    allow_policyengine_us_version: bool = False,
) -> USVariableComparisonReport:
    require_numpy()
    require_policyengine_versions(
        allow_policyengine_us_version=allow_policyengine_us_version
    )
    resolved_rulespec_root = (rulespec_root or workspace_root / "rulespec-us").resolve()
    resolved_axiom_rules_path = (
        axiom_rules_path or workspace_root / "axiom-rules-engine"
    ).resolve()
    selected_variables = variables or default_us_populace_variables()
    mappings_by_variable = {
        variable: direct_variable_mappings(variable) for variable in selected_variables
    }
    if not any(mappings_by_variable.values()):
        raise SystemExit("No comparable direct-variable PolicyEngine mappings found.")

    data = load_policyengine_variable_data(
        variables=tuple(mappings_by_variable),
        year=year,
        month=month,
        populace_year=populace_year,
        state=state,
        sample_size=sample_size,
        person_ids=person_ids,
        positive_only=positive_only,
        mappings_by_variable=mappings_by_variable,
    )
    axiom_outputs_by_variable: dict[str, list[dict[str, Any]]] = {}
    active_mappings_by_variable: dict[str, tuple[PolicyEngineMapping, ...]] = {}
    for variable, mappings in mappings_by_variable.items():
        cases = data["cases_by_variable"].get(variable, [])
        if not cases:
            axiom_outputs_by_variable[variable] = []
            active_mappings_by_variable[variable] = ()
            continue
        mappings_by_program = group_existing_mappings_by_program(
            mappings,
            rulespec_root=resolved_rulespec_root,
        )
        if not mappings_by_program:
            raise SystemExit(f"No existing RuleSpec outputs found for {variable}.")
        variable_results: list[dict[str, Any]] = []
        for program, program_mappings in mappings_by_program.items():
            active_mappings_by_variable[variable] = program_mappings
            request = build_variable_request(
                cases=cases,
                mappings=program_mappings,
                rulespec_root=resolved_rulespec_root,
                year=year,
                month=month,
            )
            variable_results = run_axiom_program(
                program=program,
                request=request,
                rulespec_root=resolved_rulespec_root,
                axiom_rules_path=resolved_axiom_rules_path,
            )
            break
        axiom_outputs_by_variable[variable] = variable_results

    return compare_outputs(
        variables=tuple(mappings_by_variable),
        cases_by_variable=data["cases_by_variable"],
        mappings_by_variable=active_mappings_by_variable,
        axiom_outputs_by_variable=axiom_outputs_by_variable,
        skipped_reasons=data["skipped_reasons"],
        tolerance=tolerance,
        relative_tolerance=relative_tolerance,
        dataset_identity=data.get("dataset_identity"),
    )


def default_us_populace_variables() -> tuple[str, ...]:
    return ("co_oap", "co_state_supplement", "ca_capi")


def direct_variable_mappings(variable: str) -> tuple[PolicyEngineMapping, ...]:
    registry = load_policyengine_registry()
    mappings = [
        mapping
        for mapping in registry.mappings_for_policyengine_variable(
            variable, country="us"
        )
        if mapping.mapping_type == "direct_variable"
        and mapping.entity in {None, "person", "spm_unit"}
    ]
    return tuple(sorted(mappings, key=lambda mapping: mapping.legal_id))


def group_existing_mappings_by_program(
    mappings: tuple[PolicyEngineMapping, ...],
    *,
    rulespec_root: Path,
) -> dict[Path, tuple[PolicyEngineMapping, ...]]:
    grouped: dict[Path, list[PolicyEngineMapping]] = {}
    for mapping in mappings:
        program = legal_id_program_path(mapping.legal_id, rulespec_root=rulespec_root)
        if not program.exists():
            continue
        output_name = legal_id_output_name(mapping.legal_id)
        if output_name not in rulespec_rule_names(program):
            continue
        grouped.setdefault(program, []).append(mapping)
    return {path: tuple(items) for path, items in grouped.items()}


def build_variable_request(
    *,
    cases: list[USVariableCase],
    mappings: tuple[PolicyEngineMapping, ...],
    rulespec_root: Path,
    year: int,
    month: int,
) -> dict[str, Any]:
    interval = month_interval(year, month)
    input_base_cache: dict[Path, dict[str, str]] = {}
    inputs: list[dict[str, Any]] = []
    outputs = [mapping.legal_id for mapping in mappings]
    for case in cases:
        entity_id = person_entity_id(case.person_id)
        for mapping in mappings:
            program = legal_id_program_path(
                mapping.legal_id, rulespec_root=rulespec_root
            )
            input_bases = input_base_cache.setdefault(
                program,
                reachable_input_bases(program, rulespec_root=rulespec_root),
            )
            for name, value in case.inputs.items():
                if name not in input_bases:
                    continue
                base = input_bases[name]
                inputs.append(
                    input_record(f"{base}#input.{name}", entity_id, interval, value)
                )
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": [
            {
                "entity_id": person_entity_id(case.person_id),
                "period": interval,
                "outputs": outputs,
            }
            for case in cases
        ],
    }


def load_policyengine_variable_data(
    *,
    variables: tuple[str, ...],
    year: int,
    month: int,
    populace_year: int,
    state: str | None,
    sample_size: int,
    person_ids: tuple[int, ...],
    positive_only: bool,
    mappings_by_variable: dict[str, tuple[PolicyEngineMapping, ...]],
) -> dict[str, Any]:
    try:
        from policyengine_us import Microsimulation
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(
            "Run with: uv run --with policyengine-us --with numpy "
            "--with populace-data[us] axiom-encode us-populace-compare"
        ) from exc

    dataset_identity: dict[str, Any] = {}
    dataset = load_populace_dataset(
        "us",
        year=populace_year,
        command=US_VARIABLE_COMMAND,
        provenance=dataset_identity,
    )
    sim = Microsimulation(dataset=dataset)
    persons = population_table(dataset, "person")
    households = population_table(dataset, "household")
    spm_units = population_table(dataset, "spm_unit")
    person_frame = persons[
        ["person_id", "person_household_id", "person_spm_unit_id"]
    ].copy()
    household_frame = households[
        ["household_id", "state_fips", "household_weight"]
    ].copy()
    household_frame["state"] = household_frame["state_fips"].map(
        lambda value: STATE_FIPS_TO_CODE.get(int(value), None)
    )
    person_frame = person_frame.merge(
        household_frame,
        left_on="person_household_id",
        right_on="household_id",
        how="left",
        validate="many_to_one",
    )
    person_frame = person_frame.sort_values("person_id").reset_index(drop=True)
    person_outputs = person_frame.copy()
    spm_outputs = spm_units[["spm_unit_id"]].copy()
    source_vars = source_variables_for_adapters(variables)
    for variable, mapping in source_vars["person"].items():
        person_outputs[variable] = calculate_policyengine(
            sim,
            variable,
            policyengine_source_period(variable, year=year, month=month),
        )
    if "co_oap" in variables:
        person_outputs["__annual_ssi"] = calculate_policyengine(sim, "ssi", year)
        person_outputs["__annual_ssi_countable_income"] = calculate_policyengine(
            sim,
            "ssi_countable_income",
            year,
        )
    for variable, mapping in source_vars["spm_unit"].items():
        spm_outputs[variable] = calculate_policyengine(
            sim,
            variable,
            policyengine_source_period(variable, year=year, month=month),
        )
    for variable in variables:
        adapter = require_us_var_adapter(variable)
        mapping = first_mapping(mappings_by_variable[variable])
        target_period = policyengine_target_period(
            adapter,
            mapping,
            year=year,
            month=month,
        )
        target_values = calculate_policyengine(sim, variable, target_period)
        multiplier = mapping.result_multiplier or 1.0
        if len(target_values) == len(person_outputs):
            person_outputs[f"__target_{variable}"] = target_values * multiplier
        elif len(target_values) == len(spm_outputs):
            spm_outputs[f"__target_{variable}"] = target_values * multiplier
        else:
            raise SystemExit(
                f"PolicyEngine variable {variable} returned {len(target_values)} rows; "
                f"expected person ({len(person_outputs)}) or SPM unit ({len(spm_outputs)})."
            )
    spm_outputs = spm_outputs.set_index("spm_unit_id", drop=False)
    cases_by_variable: dict[str, list[USVariableCase]] = {}
    skipped_reasons: dict[str, int] = {}
    for variable in variables:
        adapter = require_us_var_adapter(variable)
        variable_state = (state or adapter.default_state_code or "").upper() or None
        cases: list[USVariableCase] = []
        for _idx, row in person_outputs.iterrows():
            if variable_state and row_value(row, "state") != variable_state:
                continue
            if money(row_value(row, "household_weight", 0)) <= 0:
                continue
            person_id = int(row["person_id"])
            if person_ids and person_id not in person_ids:
                continue
            spm_unit_id = int(row["person_spm_unit_id"])
            spm_row = (
                spm_outputs.loc[spm_unit_id]
                if spm_unit_id in spm_outputs.index
                else None
            )
            target_value = policyengine_target_value(variable, row, spm_row)
            if positive_only and target_value <= 0:
                continue
            projected, skip_reason = project_case_inputs(
                variable,
                adapter,
                row=row,
                spm_row=spm_row,
            )
            if skip_reason is not None:
                skipped_reasons[skip_reason] = skipped_reasons.get(skip_reason, 0) + 1
                continue
            cases.append(
                USVariableCase(
                    variable=variable,
                    person_id=person_id,
                    spm_unit_id=spm_unit_id,
                    state=row_value(row, "state"),
                    inputs=projected,
                    pe_outputs={variable: target_value},
                )
            )
            if sample_size and len(cases) >= sample_size:
                break
        cases_by_variable[variable] = cases
    return {
        "cases_by_variable": cases_by_variable,
        "skipped_reasons": skipped_reasons,
        "dataset_identity": dataset_identity,
    }


def source_variables_for_adapters(
    variables: tuple[str, ...],
) -> dict[str, dict[str, PolicyEngineMapping | None]]:
    person_vars: dict[str, PolicyEngineMapping | None] = {}
    spm_vars: dict[str, PolicyEngineMapping | None] = {}
    for variable in variables:
        adapter = require_us_var_adapter(variable)
        for _rule_key, pe_key in (
            *adapter.direct_person_inputs,
            *adapter.annualized_person_inputs,
            *adapter.monthly_person_inputs,
            *adapter.boolean_person_inputs,
            *adapter.monthly_boolean_person_inputs,
            *(
                (rule_key, pe_key)
                for rule_key, pe_key, *_ in adapter.boolean_enum_person_inputs
            ),
        ):
            person_vars[pe_key] = None
        for _rule_key, pe_key in (
            *adapter.direct_spm_overrides,
            *adapter.annual_direct_spm_overrides,
        ):
            spm_vars[pe_key] = None
        if variable == "co_oap":
            person_vars["ssi"] = None
        if variable == "ca_capi":
            person_vars.update(
                {
                    "ca_capi_eligible_person": None,
                    "ssi_amount_if_eligible": None,
                    "ssi_countable_income": None,
                }
            )
            spm_vars.update(
                {
                    "ca_capi_eligible": None,
                    "ca_state_supplement": None,
                    "spm_unit_is_married": None,
                }
            )
        if variable == "mn_mfip":
            spm_vars["mn_mfip_eligible"] = None
    return {"person": person_vars, "spm_unit": spm_vars}


def project_case_inputs(
    variable: str,
    adapter: PolicyEngineUSVarAdapter,
    *,
    row: Any,
    spm_row: Any,
) -> tuple[dict[str, Any], str | None]:
    if variable == "ca_capi":
        return project_ca_capi_inputs(row=row, spm_row=spm_row)
    if spm_row is None and (
        adapter.direct_spm_overrides or adapter.annual_direct_spm_overrides
    ):
        return {}, f"{variable}_missing_spm_unit"
    inputs: dict[str, Any] = {}
    for rule_key, pe_key in adapter.direct_person_inputs:
        inputs[rule_key] = money(row_value(row, pe_key))
    for rule_key, pe_key in adapter.annualized_person_inputs:
        if variable == "co_oap" and rule_key == "client_total_countable_income_for_oap":
            inputs[rule_key] = (
                money(
                    row_value(
                        row,
                        "__annual_ssi_countable_income",
                        row_value(row, "ssi_countable_income"),
                    )
                )
                + money(row_value(row, "__annual_ssi", row_value(row, "ssi")))
            ) / 12.0
        elif variable == "co_state_supplement":
            inputs[rule_key] = money(row_value(row, pe_key))
        else:
            inputs[rule_key] = money(row_value(row, pe_key)) / 12.0
    for rule_key, pe_key in adapter.monthly_person_inputs:
        inputs[rule_key] = money(row_value(row, pe_key))
    for rule_key, pe_key in adapter.boolean_person_inputs:
        inputs[rule_key] = bool_value(row_value(row, pe_key))
    for rule_key, pe_key in adapter.monthly_boolean_person_inputs:
        inputs[rule_key] = bool_value(row_value(row, pe_key))
    for (
        rule_key,
        pe_key,
        _true_value,
        false_value,
    ) in adapter.boolean_enum_person_inputs:
        raw_value = row_value(row, pe_key)
        raw_text = str(raw_value).strip().upper()
        inputs[rule_key] = raw_text != false_value.strip().upper()
    for rule_key, pe_key in adapter.direct_spm_overrides:
        inputs[rule_key] = money(row_value(spm_row, pe_key))
    for rule_key, pe_key in adapter.annual_direct_spm_overrides:
        inputs[rule_key] = money(row_value(spm_row, pe_key)) / 12.0
    for key in adapter.unsupported_truthy_input_keys:
        inputs.setdefault(key, False)
    for key in adapter.unsupported_falsy_input_keys:
        inputs.setdefault(key, True)
    if variable == "co_state_supplement":
        inputs.setdefault("ssa_is_recovering_ssi_payment_due_to_overpayment", False)
    if variable == "mn_mfip":
        if not bool_value(row_value(spm_row, "mn_mfip_eligible")):
            return {}, "mn_mfip_ineligible_spm_unit"
        earned = money(inputs.get("net_earned_income_in_budget_month", 0.0))
        unearned = money(inputs.get("unearned_income_in_budget_month", 0.0))
        if unearned < 0:
            return {}, "mn_mfip_negative_unearned_income"
        inputs.update(
            {
                "unit_receives_no_income_other_than_mfip": (
                    earned <= 0 and unearned <= 0
                ),
                "unit_receives_unearned_income_only": (earned <= 0 and unearned > 0),
                "unit_has_earned_income_only": earned > 0 and unearned <= 0,
                "unit_has_both_earned_and_unearned_income": (
                    earned > 0 and unearned > 0
                ),
                "unit_is_applicant_case": False,
                "prorated_benefit_under_section_0022_12_03": 0.0,
                "recoupment_amount_if_applicable": 0.0,
            }
        )
    return inputs, None


def project_ca_capi_inputs(
    *, row: Any, spm_row: Any
) -> tuple[dict[str, Any], str | None]:
    if spm_row is None:
        return {}, "ca_capi_missing_spm_unit"
    married = bool_value(row_value(spm_row, "spm_unit_is_married"))
    if married:
        return {}, "ca_capi_skipped_married_spm_unit"
    eligible_person = bool_value(row_value(row, "ca_capi_eligible_person"))
    spm_eligible = bool_value(row_value(spm_row, "ca_capi_eligible"))
    if not eligible_person or not spm_eligible:
        selected_standard = 0.0
        countable_income = 0.0
    else:
        selected_standard = money(row_value(spm_row, "ca_state_supplement")) + money(
            row_value(row, "ssi_amount_if_eligible")
        )
        countable_income = money(row_value(row, "ssi_countable_income"))
    return (
        {
            "ssi_ssp_payment_standard_for_selected_individual_living_arrangement": selected_standard,
            "ssi_ssp_payment_standard_for_selected_eligible_couple_living_arrangement": 0.0,
            "person_is_member_of_eligible_couple": False,
            "couple_one_member_receiving_or_applying_for_capi_and_other_receiving_ssi_ssp": False,
            "each_member_of_eligible_couple_receives_capi": False,
            "ca_capi_countable_income_for_payment_month_under_retrospective_accounting": countable_income,
        },
        None,
    )


def compare_outputs(
    *,
    variables: tuple[str, ...],
    cases_by_variable: dict[str, list[USVariableCase]],
    mappings_by_variable: dict[str, tuple[PolicyEngineMapping, ...]],
    axiom_outputs_by_variable: dict[str, list[dict[str, Any]]],
    skipped_reasons: dict[str, int],
    tolerance: float,
    relative_tolerance: float,
    dataset_identity: dict[str, Any] | None = None,
) -> USVariableComparisonReport:
    mismatches: list[USVariableComparisonRow] = []
    summary: dict[str, dict[str, Any]] = {}
    compared_values = 0
    compared_spm_units: set[int] = set()
    compared_person_ids: set[int] = set()
    for variable in variables:
        cases = cases_by_variable.get(variable, [])
        axiom_outputs = axiom_outputs_by_variable.get(variable, [])
        mappings = mappings_by_variable[variable]
        for mapping in mappings:
            if mapping.legal_id not in summary:
                summary[mapping.legal_id] = {
                    "variable": variable,
                    "output": mapping.legal_id,
                    "compared": 0,
                    "mismatches": 0,
                    "max_abs_diff": 0.0,
                    "max_relative_diff": 0.0,
                }
        for index, case in enumerate(cases):
            if index >= len(axiom_outputs):
                for mapping in mappings:
                    item = summary[mapping.legal_id]
                    item["mismatches"] += 1
                    mismatches.append(
                        USVariableComparisonRow(
                            variable=variable,
                            entity_id=person_entity_id(case.person_id),
                            output=mapping.legal_id,
                            axiom=0.0,
                            policyengine=money(case.pe_outputs[variable]),
                            diff=-money(case.pe_outputs[variable]),
                            reason="missing_axiom_row",
                        )
                    )
                continue
            compared_person_ids.add(case.person_id)
            if case.spm_unit_id is not None:
                compared_spm_units.add(case.spm_unit_id)
            result = axiom_outputs[index]
            outputs = result.get("outputs") or {}
            for mapping in mappings:
                if mapping.legal_id not in outputs:
                    item = summary[mapping.legal_id]
                    item["mismatches"] += 1
                    mismatches.append(
                        USVariableComparisonRow(
                            variable=variable,
                            entity_id=person_entity_id(case.person_id),
                            output=mapping.legal_id,
                            axiom=0.0,
                            policyengine=money(case.pe_outputs[variable]),
                            diff=-money(case.pe_outputs[variable]),
                            reason="missing_axiom_output",
                        )
                    )
                    continue
                axiom_value = output_number(outputs.get(mapping.legal_id))
                pe_value = money(case.pe_outputs[variable])
                diff = axiom_value - pe_value
                abs_diff = abs(diff)
                compared_values += 1
                item = summary[mapping.legal_id]
                item["compared"] += 1
                item["max_abs_diff"] = max(item["max_abs_diff"], abs_diff)
                item["max_relative_diff"] = max(
                    item["max_relative_diff"],
                    relative_diff(axiom_value, pe_value),
                )
                if not within_tolerance(
                    axiom_value,
                    pe_value,
                    absolute_tolerance=tolerance,
                    relative_tolerance=relative_tolerance,
                ):
                    item["mismatches"] += 1
                    mismatches.append(
                        USVariableComparisonRow(
                            variable=variable,
                            entity_id=person_entity_id(case.person_id),
                            output=mapping.legal_id,
                            axiom=axiom_value,
                            policyengine=pe_value,
                            diff=diff,
                        )
                    )
    return USVariableComparisonReport(
        variables=variables,
        compared_persons=len(compared_person_ids),
        compared_spm_units=len(compared_spm_units),
        compared_values=compared_values,
        skipped_cases=sum(skipped_reasons.values()),
        skipped_reasons=dict(sorted(skipped_reasons.items())),
        mismatches=mismatches,
        output_summary=list(summary.values()),
        projection_notes=[
            "US variable Populace comparison projects existing PolicyEngine component "
            "values into RuleSpec legal inputs and then executes the real Axiom "
            "Rust rules engine.",
            "Colorado OAP projects PE ssi + ssi_countable_income into the legal "
            "total-countable-income input before comparing the monthly grant amount.",
            "California CAPI is compared only on individual, non-couple SPM units; "
            "PE exposes CAPI as an SPM-unit surface while the encoded legal rule is "
            "a person-level final-benefit formula.",
            "Minnesota MFIP is compared only on PE-eligible SPM units because the "
            "encoded RuleSpec module covers the post-eligibility grant and cash "
            "issuance calculation.",
        ],
        dataset_identity=dataset_identity or None,
    )


def print_report(
    report: USVariableComparisonReport,
    *,
    tolerance: float,
    relative_tolerance: float,
    max_differences: int,
) -> None:
    print("PolicyEngine US Populace variable comparison")
    identity_line = format_dataset_identity(report.dataset_identity)
    if identity_line:
        print(identity_line)
    print(f"Variables: {', '.join(report.variables)}")
    print(f"Compared persons: {report.compared_persons:,}")
    print(f"Compared SPM units: {report.compared_spm_units:,}")
    print(f"Compared values: {report.compared_values:,}")
    print(f"Skipped cases: {report.skipped_cases:,}")
    print(f"Tolerance: {tolerance:g}")
    print(f"Relative tolerance: {relative_tolerance:g}")
    print(f"Mismatches: {len(report.mismatches):,}")
    if report.skipped_reasons:
        print("Skipped reasons:")
        for reason, count in report.skipped_reasons.items():
            print(f"  - {reason}: {count:,}")
    print()
    print("By output:")
    for item in report.output_summary:
        print(
            f"  - {item['output']}: {item['mismatches']:,}/{item['compared']:,} "
            f"mismatch, max_abs_diff={item['max_abs_diff']:.2f}, "
            f"max_rel_diff={item['max_relative_diff']:.2g}"
        )
    if report.mismatches:
        print()
        print("Top mismatches:")
        for row in sorted(
            report.mismatches,
            key=lambda item: abs(item.diff),
            reverse=True,
        )[:max_differences]:
            print(
                f"  - entity={row.entity_id} {row.variable}:{row.output}: "
                f"axiom={row.axiom:.2f} pe={row.policyengine:.2f} diff={row.diff:.2f}"
                + (f" reason={row.reason}" if row.reason else "")
            )
    print()
    print("Projection notes:")
    for note in report.projection_notes:
        print(f"  - {note}")


def calculate_policyengine(sim: Any, name: str, period: str | int) -> Any:
    return array(sim.calculate(name, period=period))


def policyengine_source_period(variable: str, *, year: int, month: int) -> str | int:
    monthly_sources = {
        "ssi",
        "ssi_countable_income",
        "ssi_amount_if_eligible",
        "mn_mfip_countable_earned_income",
        "mn_mfip_countable_unearned_income",
        "mn_mfip_family_wage_level",
        "mn_mfip_food_portion",
        "mn_mfip_full_transitional_standard",
    }
    if variable in monthly_sources:
        return f"{year:04d}-{month:02d}"
    return year


def policyengine_target_period(
    adapter: PolicyEngineUSVarAdapter,
    mapping: PolicyEngineMapping,
    *,
    year: int,
    month: int,
) -> str | int:
    if mapping.result_multiplier is not None:
        return year
    if adapter.monthly:
        return f"{year:04d}-{month:02d}"
    return year


def policyengine_target_value(variable: str, row: Any, spm_row: Any) -> float:
    person_value = row_value(row, f"__target_{variable}", None)
    if person_value is not None:
        return money(person_value)
    if spm_row is None:
        return 0.0
    return money(row_value(spm_row, f"__target_{variable}", 0.0))


def require_us_var_adapter(variable: str) -> PolicyEngineUSVarAdapter:
    adapter = get_pe_us_var_adapter(variable)
    if adapter is None:
        raise SystemExit(f"No PolicyEngine US adapter is configured for {variable}.")
    return adapter


def first_mapping(mappings: tuple[PolicyEngineMapping, ...]) -> PolicyEngineMapping:
    if not mappings:
        raise SystemExit("PolicyEngine variable has no direct-variable mapping.")
    return mappings[0]


def month_interval(year: int, month: int) -> dict[str, str]:
    last_day = monthrange(year, month)[1]
    return {
        "period_kind": MONTHLY_PERIOD_KIND,
        "start": f"{year:04d}-{month:02d}-01",
        "end": f"{year:04d}-{month:02d}-{last_day:02d}",
    }


def legal_id_base(legal_id: str) -> str:
    return legal_id.split("#", 1)[0]


def legal_id_output_name(legal_id: str) -> str:
    if "#" not in legal_id:
        raise ValueError(f"legal ID has no output fragment: {legal_id}")
    return legal_id.rsplit("#", 1)[1]


def legal_id_program_path(legal_id: str, *, rulespec_root: Path) -> Path:
    base = legal_id_base(legal_id)
    prefix, _, tail = base.partition(":")
    if not prefix or not tail:
        raise ValueError(f"invalid legal ID: {legal_id}")
    program_path = Path(prefix) / Path(tail + ".yaml")
    return resolve_rulespec_program_path(rulespec_root, program_path)


def file_legal_base(path: Path, *, rulespec_root: Path) -> str:
    rel = path.resolve().relative_to(rulespec_root.resolve())
    stem = rel.with_suffix("")
    parts = stem.parts
    if not parts:
        raise ValueError(f"Cannot derive legal base from {path}")
    prefix = parts[0]
    return f"{prefix}:{'/'.join(parts[1:])}"


def rulespec_rule_names(path: Path) -> set[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(rule.get("name"))
        for rule in payload.get("rules", []) or []
        if isinstance(rule, dict) and rule.get("name")
    }


def reachable_input_bases(program: Path, *, rulespec_root: Path) -> dict[str, str]:
    formulas_by_base: dict[str, list[str]] = {}
    rule_names_by_base: dict[str, set[str]] = {}
    for path in reachable_rulespec_files(program, rulespec_root=rulespec_root):
        base = file_legal_base(path, rulespec_root=rulespec_root)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        formulas: list[str] = []
        names: set[str] = set()
        for rule in payload.get("rules", []) or []:
            if not isinstance(rule, dict):
                continue
            if rule.get("name"):
                names.add(str(rule["name"]))
            for version in rule.get("versions", []) or []:
                if isinstance(version, dict) and version.get("formula") is not None:
                    formulas.append(str(version["formula"]))
        formulas_by_base[base] = formulas
        rule_names_by_base[base] = names

    inputs: dict[str, str] = {}
    identifiers = sorted(
        {
            identifier
            for formulas in formulas_by_base.values()
            for formula in formulas
            for identifier in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", formula)
        }
    )
    rule_names = (
        set().union(*rule_names_by_base.values()) if rule_names_by_base else set()
    )
    builtins = {"if", "else", "and", "or", "not", "max", "min", "True", "False"}
    for identifier in identifiers:
        if identifier in rule_names or identifier in builtins:
            continue
        for base, formulas in formulas_by_base.items():
            if any(
                re.search(rf"\b{re.escape(identifier)}\b", formula)
                for formula in formulas
            ):
                inputs[identifier] = base
                break
    return inputs


def reachable_rulespec_files(program: Path, *, rulespec_root: Path) -> tuple[Path, ...]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    stack = [program]
    while stack:
        path = stack.pop()
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        ordered.append(resolved)
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        for target in payload.get("imports", []) or []:
            if not isinstance(target, str):
                continue
            with_output = target if "#" in target else f"{target}#_"
            import_path = legal_id_program_path(
                with_output, rulespec_root=rulespec_root
            )
            stack.append(import_path)
    return tuple(ordered)
