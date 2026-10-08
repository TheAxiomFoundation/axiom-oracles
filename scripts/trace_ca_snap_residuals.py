#!/usr/bin/env python3
"""Trace the committed ca-snap-ecps residual households on PE-US 1.767.3.

This is deliberately a diagnostic, not a comparison-suite runner. It reads the
committed report and compact case evidence, evaluates only the households with
unexplained rows, and never publishes or rewrites a dashboard artifact.
"""

from __future__ import annotations

import argparse
import json
import os
from importlib.metadata import version
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json"
CASE_DIR = ROOT / "dashboard/public/data/cases/ca-snap-ecps"

EXPECTED_VERSIONS = {
    "policyengine": "4.18.9",
    "policyengine-us": "1.767.3",
    "policyengine-core": "3.30.3",
}

TRACE_VARIABLES = (
    "snap",
    "snap_normal_allotment",
    "is_snap_eligible",
    "takes_up_snap_if_eligible",
    "meets_snap_gross_income_test",
    "meets_snap_net_income_test",
    "meets_snap_asset_test",
    "meets_snap_categorical_eligibility",
    "meets_snap_work_requirements",
    "snap_gross_income",
    "snap_earned_income",
    "snap_earned_income_person",
    "snap_self_employment_income_after_expense_deduction",
    "snap_self_employment_expense_deduction",
    "snap_unearned_income",
    "snap_net_income_pre_shelter",
    "snap_net_income",
    "snap_deductions",
    "snap_standard_deduction",
    "snap_earned_income_deduction",
    "snap_dependent_care_deduction",
    "snap_child_support_deduction",
    "snap_child_support_gross_income_deduction",
    "snap_allowable_medical_expenses",
    "snap_excess_medical_expense_deduction",
    "snap_excess_shelter_expense_deduction",
    "snap_utility_allowance",
    "snap_expected_contribution",
    "snap_max_allotment",
    "snap_min_allotment",
    "snap_assets",
    "snap_unit_size",
    "has_usda_elderly_disabled",
    "housing_cost",
    "employment_income",
    "self_employment_income",
    "self_employment_income_before_lsr",
    "sstb_self_employment_income_before_lsr",
    "ssi",
    "tanf",
    "ca_tanf",
    "general_assistance",
    "pension_income",
    "taxable_pension_income",
    "veterans_benefits",
    "unemployment_compensation",
    "disability_benefits",
    "workers_compensation",
    "social_security",
    "retirement_distributions",
    "rental_income",
    "child_support_received",
    "alimony_income",
    "financial_assistance",
    "survivor_benefits",
    "dividend_income",
    "interest_income",
    "taxable_interest_income",
    "miscellaneous_income",
)

COUNTERFACTUAL_VARIABLES = (
    "snap",
    "snap_normal_allotment",
    "is_snap_eligible",
    "snap_gross_income",
    "snap_earned_income",
    "snap_self_employment_income_after_expense_deduction",
    "snap_unearned_income",
    "snap_net_income",
    "snap_deductions",
    "tanf",
    "ca_tanf",
)

REQUESTED_MONTH_VARIABLES = (
    *COUNTERFACTUAL_VARIABLES,
    "snap_max_allotment",
    "snap_min_allotment",
    "snap_standard_deduction",
    "snap_earned_income_deduction",
    "snap_dependent_care_deduction",
    "snap_child_support_deduction",
    "snap_excess_medical_expense_deduction",
    "snap_excess_shelter_expense_deduction",
    "snap_net_income_pre_shelter",
    "snap_expected_contribution",
)

AXIOM_OUTPUT_SUFFIXES = {
    "benefit": "#snap_benefit",
    "eligible": "#snap_eligible",
    "gross_income": "#snap_total_gross_income",
    "net_income_pre_shelter": "#snap_net_income_before_shelter",
    "net_income": "#snap_net_monthly_income",
    "standard_deduction": "#snap_standard_deduction",
    "earned_income_deduction": "#snap_earned_income_deduction_for_net_income",
    "shelter_deduction": "#snap_excess_shelter_deduction_for_net_income",
    "shelter_cost": "#snap_excess_shelter_cost",
    "utility_allowance": "#snap_standard_utility_allowance",
    "maximum_allotment": "#snap_maximum_allotment",
    "minimum_benefit": "#snap_minimum_benefit",
    "calculated_allotment": "#snap_calculated_monthly_allotment_before_minimums",
    "gross_test": "#snap_standard_gross_income_eligible",
    "net_test": "#snap_standard_net_income_eligible",
    "resource_test": "#snap_resource_eligible",
}

AXIOM_INPUT_SUFFIXES = {
    "earned_income": "#input.snap_gross_monthly_earned_income",
    "unearned_income": "#input.snap_total_monthly_unearned_income",
    "dependent_care_deduction": "#input.dependent_care_deduction",
    "child_support_deduction": "#input.child_support_deduction",
    "medical_deduction": "#input.medical_expense_deduction",
    "housing_cost": "#input.household_shelter_costs_incurred",
    "household_size": "#input.household_size",
}


def _prepare_policyengine() -> dict[str, str]:
    installed = {package: version(package) for package in EXPECTED_VERSIONS}
    if installed != EXPECTED_VERSIONS:
        raise SystemExit(
            "Wrong PolicyEngine runtime: "
            f"expected {EXPECTED_VERSIONS}, imported metadata reports {installed}"
        )

    os.environ["POLICYENGINE_SKIP_COUNTRY_IMPORTS"] = "1"
    try:
        import policyengine
        import policyengine.provenance.manifest as manifest

        def allow_local_oracle_data(
            country_id,
            runtime_model_version,
            runtime_data_build_fingerprint=None,
        ):
            return manifest.DataCertification(
                compatibility_basis="axiom_oracles_ca_snap_362_live_trace",
                certified_for_model_version=runtime_model_version,
                data_build_fingerprint=runtime_data_build_fingerprint,
                certified_by="scripts/trace_ca_snap_residuals.py",
            )

        manifest.certify_data_release_compatibility = allow_local_oracle_data
        try:
            import policyengine.tax_benefit_models.common.model_version as model_version

            model_version.certify_data_release_compatibility = allow_local_oracle_data
        except ImportError:
            pass
    finally:
        os.environ.pop("POLICYENGINE_SKIP_COUNTRY_IMPORTS", None)

    from policyengine.tax_benefit_models import us

    policyengine.us = us
    return installed


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["case_id"], row["concept"], row["kind"]


def _outcome(case: dict[str, Any], suffix: str) -> dict[str, Any]:
    rows = [
        row
        for row in case["mismatches"] + case["matches"]
        if row["concept"].endswith(suffix)
    ]
    if len(rows) != 1:
        raise ValueError(
            f"{case['case_id']} has {len(rows)} committed outcomes for {suffix}"
        )
    return rows[0]


def _eligibility_direction(outcome: dict[str, Any]) -> str:
    left = bool(outcome["left"])
    right = bool(outcome["right"])
    if left and not right:
        return "axiom_only"
    if right and not left:
        return "pe_only"
    if left:
        return "both_eligible"
    return "both_ineligible"


def _benefit_direction(outcome: dict[str, Any]) -> str:
    left = float(outcome["left"])
    right = float(outcome["right"])
    if left > 0 and right == 0:
        return "axiom_only_pays"
    if right > 0 and left == 0:
        return "pe_only_pays"
    if left > right:
        return "axiom_higher"
    if right > left:
        return "pe_higher"
    if left == 0:
        return "both_zero"
    return "equal_positive"


def _household_shape(ages: list[int]) -> str:
    adults = sum(age >= 18 for age in ages)
    minors = len(ages) - adults
    if adults == 0:
        return "lone_minor" if minors == 1 else "multiple_minors_only"
    if adults == 1:
        return "one_adult" if minors == 0 else "one_adult_with_minors"
    return "multiple_adults" if minors == 0 else "multiple_adults_with_minors"


def _load_residuals(
    limit: int | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = json.loads(REPORT.read_text())
    unexplained_keys = {
        _row_key(row)
        for row in report["mismatches"]
        if row.get("disposition") is None
    }
    residuals = []
    for case in report["cases"]:
        rows = [
            row
            for row in case["mismatches"]
            if (case["case_id"], row["concept"], row["kind"]) in unexplained_keys
        ]
        if not rows:
            continue
        eligibility = _outcome(case, "#snap_eligible")
        benefit = _outcome(case, "#snap_benefit")
        ages = case["metadata"]["household_summary"]["ages"]
        residuals.append(
            {
                "case_id": case["case_id"],
                "unexplained_rows": len(rows),
                "unexplained_concepts": [row["concept"] for row in rows],
                "eligibility_direction": _eligibility_direction(eligibility),
                "benefit_direction": _benefit_direction(benefit),
                "household_shape": _household_shape(ages),
                "ages": ages,
                "report": {
                    "axiom_eligible": bool(eligibility["left"]),
                    "pe_eligible": bool(eligibility["right"]),
                    "axiom_benefit": float(benefit["left"]),
                    "pe_benefit": float(benefit["right"]),
                },
            }
        )
    residuals.sort(key=lambda row: int(row["case_id"].removeprefix("ecps-")))
    if limit is not None:
        residuals = residuals[:limit]
    return report, residuals


def _load_compact_evidence(case_ids: set[str]) -> dict[str, dict[str, Any]]:
    compact: dict[str, dict[str, Any]] = {}
    for chunk in sorted(CASE_DIR.glob("chunk-*.json")):
        for case in json.loads(chunk.read_text()):
            if case["id"] in case_ids:
                compact[case["id"]] = case
    missing = sorted(case_ids - compact.keys())
    if missing:
        raise ValueError(f"Committed compact evidence is missing cases: {missing}")
    return compact


def _values_by_suffix(
    rows: list[dict[str, Any]],
    suffixes: dict[str, str],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for label, suffix in suffixes.items():
        matches = [row["v"] for row in rows if row["n"].endswith(suffix)]
        if len(matches) > 1:
            raise ValueError(f"Multiple compact values end with {suffix}: {matches}")
        values[label] = matches[0] if matches else 0
    return values


def _committed_axiom_evidence(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "outputs": _values_by_suffix(case["o"], AXIOM_OUTPUT_SUFFIXES),
        "inputs": _values_by_suffix(case["i"], AXIOM_INPUT_SUFFIXES),
    }


class _InputOverrideRunner:
    def __init__(
        self,
        *,
        person: dict[str, Any] | None = None,
        spm_unit: dict[str, Any] | None = None,
    ) -> None:
        from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner

        class Runner(PolicyEngineRunner):
            def _policyengine_dataset_rows(inner_self, cases, variables):
                rows = list(
                    super(Runner, inner_self)._policyengine_dataset_rows(
                        cases,
                        variables,
                    )
                )
                if person:
                    for row in rows[0]:
                        row.update(person)
                if spm_unit:
                    for row in rows[4]:
                        row.update(spm_unit)
                return tuple(rows)

        self.runner = Runner(batch_size=10_000)

    def run_cases(self, cases, variables):
        return self.runner.run_cases(cases, variables=list(variables))


class _RequestedMonthRunner:
    """Evaluate the exact requested month instead of the calendar average.

    The committed runner normalizes month-defined annual output columns by
    dividing them by 12. A direct PolicyEngine-US situation simulation retains
    the monthly periods, so this diagnostic can separately test January 2026.
    """

    def __init__(
        self,
        *,
        person: dict[str, Any] | None = None,
        spm_unit: dict[str, Any] | None = None,
    ) -> None:
        self.person = person or {}
        self.spm_unit = spm_unit or {}

    @staticmethod
    def _period_input(period: str, value: Any) -> dict[str, Any]:
        return {period: value}

    def run_cases(
        self,
        cases,
        variables,
    ) -> dict[str, dict[str, Any]]:
        import numpy as np
        from policyengine_us import Simulation

        from axiom_oracles.adapters.policyengine.runner import (
            PolicyEngineRunner,
            _PERSON_CASE_CONCEPT_TO_PE,
            _PERSON_INCOME_CONCEPT_TO_PE,
        )

        requested_period = str(cases[0].period)
        year = requested_period.split("-", maxsplit=1)[0]
        runner = PolicyEngineRunner()
        situation = runner._build_situation_from_cases(
            cases,
            variables=list(variables),
        )

        # PolicyEngine-US 1.767.3 requires marital-unit membership. The
        # committed runner predates that entity, so add the same one-unit-per-
        # case relationship used by the requested-month runner fix.
        situation["marital_units"] = {}
        for spm_unit_id, inputs in situation["spm_units"].items():
            prefix = spm_unit_id.partition("__")[0]
            situation["marital_units"][f"{prefix}__marital_unit"] = {
                "members": list(inputs["members"])
            }

        for inputs in situation["people"].values():
            # Match the batch dataset bridge: absent source facts are explicit
            # zero inputs, not invitations for PolicyEngine to impute SSI or
            # another endogenous source in the direct simulation.
            for variable in (
                *_PERSON_INCOME_CONCEPT_TO_PE.values(),
                *_PERSON_CASE_CONCEPT_TO_PE.values(),
            ):
                inputs.setdefault(variable, self._period_input(year, 0))
            inputs["employment_income_before_lsr"] = dict(
                inputs["employment_income"]
            )
            inputs["self_employment_income_before_lsr"] = dict(
                inputs["self_employment_income"]
            )
            for variable, value in self.person.items():
                inputs[variable] = self._period_input(year, value)
        for inputs in situation["spm_units"].values():
            for variable, value in self.spm_unit.items():
                inputs[variable] = self._period_input(requested_period, value)

        simulation = Simulation(situation=situation)
        values = {str(case.case_id): {} for case in cases}
        for variable in variables:
            definition = simulation.tax_benefit_system.variables[variable]
            definition_period = str(definition.definition_period).lower()
            calculation_period = (
                requested_period if definition_period == "month" else year
            )
            raw = np.asarray(
                simulation.calculate(variable, period=calculation_period)
            )
            entity = str(definition.entity.key)
            entity_ids = [
                str(entity_id)
                for entity_id in simulation.populations[entity].ids
            ]
            for index, case in enumerate(cases):
                prefix = f"case_{index}"
                selected = [
                    raw[position]
                    for position, entity_id in enumerate(entity_ids)
                    if entity_id.partition("__")[0] == prefix
                ]
                if not selected:
                    raise RuntimeError(
                        f"No {entity} value for {case.case_id} / {variable}"
                    )
                if raw.dtype == bool:
                    value = bool(np.asarray(selected).any())
                else:
                    value = float(np.asarray(selected).sum())
                values[str(case.case_id)][variable] = value
        return values


def _result_values(results) -> dict[str, dict[str, Any]]:
    values = {}
    for result in results:
        if result.errors:
            raise RuntimeError(
                f"PolicyEngine errors for {result.household_id}: {result.errors}"
            )
        values[str(result.household_id)] = dict(result.values)
    return values


def _bridge_checks(
    residual: dict[str, Any],
    baseline: dict[str, Any],
    zero_self_employment: dict[str, Any],
    zero_tanf: dict[str, Any],
    zero_self_employment_and_tanf: dict[str, Any],
) -> dict[str, Any]:
    report = residual["report"]

    def checks(values: dict[str, Any]) -> dict[str, Any]:
        benefit_delta = abs(float(values["snap"]) - report["axiom_benefit"])
        return {
            "pe_benefit": values["snap"],
            "pe_eligible": bool(values["is_snap_eligible"]),
            "benefit_delta_from_report_axiom": benefit_delta,
            "benefit_within_tolerance": benefit_delta <= 7,
            "eligibility_matches_report_axiom": (
                bool(values["is_snap_eligible"]) == report["axiom_eligible"]
            ),
        }

    live_delta = abs(float(baseline["snap"]) - report["pe_benefit"])
    return {
        "live_baseline": {
            "pe_benefit_delta_from_report": live_delta,
            "pe_benefit_matches_report": live_delta <= 1e-6,
            "pe_benefit_within_report_tolerance": live_delta <= 7,
            "pe_eligibility_matches_report": (
                bool(baseline["is_snap_eligible"]) == report["pe_eligible"]
            ),
        },
        "zero_self_employment": checks(zero_self_employment),
        "zero_tanf": checks(zero_tanf),
        "zero_self_employment_and_tanf": checks(
            zero_self_employment_and_tanf
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit",
        type=int,
        help="Trace only the first N residual households (diagnostic smoke test).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    runtime = _prepare_policyengine()
    report, residuals = _load_residuals(args.limit)
    case_ids = {row["case_id"] for row in residuals}
    compact = _load_compact_evidence(case_ids)

    from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner
    from axiom_oracles.core.geography import GeographyScope
    from axiom_oracles.populations.populace_us import load_populace_us_cases

    ca_cases = load_populace_us_cases(
        period="2026-01",
        sample_size=None,
        scope=GeographyScope(type="census_state", geoid="06"),
    )
    cases_by_id = {case.case_id: case for case in ca_cases}
    missing = sorted(case_ids - cases_by_id.keys())
    if missing:
        raise ValueError(f"Live Populace loader is missing residual cases: {missing}")
    cases = [cases_by_id[row["case_id"]] for row in residuals]

    baseline = _result_values(
        PolicyEngineRunner(batch_size=10_000).run_cases(
            cases,
            variables=list(TRACE_VARIABLES),
        )
    )
    zero_self_employment = _result_values(
        _InputOverrideRunner(
            person={
                "self_employment_income": 0,
                "self_employment_income_before_lsr": 0,
                "sstb_self_employment_income_before_lsr": 0,
            }
        ).run_cases(cases, COUNTERFACTUAL_VARIABLES)
    )
    zero_tanf = _result_values(
        _InputOverrideRunner(
            spm_unit={"ca_tanf": 0, "tanf": 0}
        ).run_cases(cases, COUNTERFACTUAL_VARIABLES)
    )
    zero_self_employment_and_tanf = _result_values(
        _InputOverrideRunner(
            person={
                "self_employment_income": 0,
                "self_employment_income_before_lsr": 0,
                "sstb_self_employment_income_before_lsr": 0,
            },
            spm_unit={"ca_tanf": 0, "tanf": 0},
        ).run_cases(cases, COUNTERFACTUAL_VARIABLES)
    )
    requested_month = _RequestedMonthRunner().run_cases(
        cases,
        REQUESTED_MONTH_VARIABLES,
    )
    requested_month_zero_self_employment = _RequestedMonthRunner(
        person={
            "self_employment_income": 0,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 0,
        }
    ).run_cases(cases, COUNTERFACTUAL_VARIABLES)
    requested_month_zero_tanf = _RequestedMonthRunner(
        spm_unit={"ca_tanf": 0, "tanf": 0}
    ).run_cases(cases, COUNTERFACTUAL_VARIABLES)
    requested_month_zero_self_employment_and_tanf = _RequestedMonthRunner(
        person={
            "self_employment_income": 0,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 0,
        },
        spm_unit={"ca_tanf": 0, "tanf": 0},
    ).run_cases(cases, COUNTERFACTUAL_VARIABLES)

    for residual in residuals:
        case_id = residual["case_id"]
        residual["axiom_evidence"] = _committed_axiom_evidence(compact[case_id])
        residual["live_pe"] = baseline[case_id]
        residual["counterfactuals"] = {
            "zero_self_employment": zero_self_employment[case_id],
            "zero_tanf": zero_tanf[case_id],
            "zero_self_employment_and_tanf": (
                zero_self_employment_and_tanf[case_id]
            ),
        }
        residual["requested_month_pe"] = requested_month[case_id]
        residual["requested_month_counterfactuals"] = {
            "zero_self_employment": (
                requested_month_zero_self_employment[case_id]
            ),
            "zero_tanf": requested_month_zero_tanf[case_id],
            "zero_self_employment_and_tanf": (
                requested_month_zero_self_employment_and_tanf[case_id]
            ),
        }
        residual["checks"] = _bridge_checks(
            residual,
            baseline[case_id],
            zero_self_employment[case_id],
            zero_tanf[case_id],
            zero_self_employment_and_tanf[case_id],
        )

    output = {
        "schema_version": "axiom_oracles.ca_snap_residual_trace.v1",
        "runtime": runtime,
        "committed_report": str(REPORT.relative_to(ROOT)),
        "committed_report_provenance": report.get("provenance"),
        "residual_households": len(residuals),
        "unexplained_rows": sum(row["unexplained_rows"] for row in residuals),
        "trace_variables": list(TRACE_VARIABLES),
        "cases": residuals,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        f"Traced {len(residuals)} households / "
        f"{output['unexplained_rows']} unexplained rows to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
