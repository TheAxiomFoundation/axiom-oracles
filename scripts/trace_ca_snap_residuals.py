#!/usr/bin/env python3
"""Trace pinned pre-disposition ca-snap-ecps households on PE-US 1.767.3.

This is deliberately a diagnostic, not a comparison-suite runner. It reads the
explicit base report and committed compact case evidence, evaluates only the
households that were unexplained in that base, and never publishes or rewrites
a dashboard artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REPORT_RELATIVE_PATH = "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json"
TRACER_RELATIVE_PATH = "scripts/trace_ca_snap_residuals.py"
RUNNER_RELATIVE_PATH = "axiom_oracles/adapters/policyengine/runner.py"
CASE_DIR = ROOT / "dashboard/public/data/cases/ca-snap-ecps"

BASE_REPORT_SHA256 = "a5ded34100a124ec3c6409a409fb64bca788d510b5233d1c9992a1809e6b484d"
EXPECTED_BASE_MISMATCHES = 684
EXPECTED_BASE_MISMATCH_HOUSEHOLDS = 499
EXPECTED_BASE_UNEXPLAINED_ROWS = 441
EXPECTED_BASE_RESIDUAL_HOUSEHOLDS = 361
LEGACY_ANNUAL_SEMANTICS = "legacy_snap_outputs_calendar_sum_divided_by_12"
LEGACY_MONTHLY_NORMALIZED_VARIABLES = {
    "snap",
    "snap_normal_allotment",
}

EXPECTED_BASE_PROVENANCE = {
    "dataset": {"population": "enhanced-cps", "source": "config"},
    "engine": {
        "axiom_rules_engine_sha": "48797e101c093bb388be718c6f5d8fc9d9f94a7d",
        "axiom_rules_engine_version": "0.1.0",
    },
    "generated_at": "2026-07-26T04:30:45Z",
    "generated_by": "scripts/run_comparison.py::ca-snap-ecps",
    "oracle": {
        "name": "policyengine",
        "policyengine_package": "policyengine==4.18.9",
        "policyengine_us": "1.752.2",
    },
    "rulespecs": [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": "ca2d424fcb85ce8c3a8f4706113331710f114460",
        }
    ],
    "run_kind": "manual",
    "schema": "axiom_oracles.provenance.v1",
}

EXPECTED_POPULACE_PIN = {
    "dataset": "populace://policyengine/populace-us/populace_us_2024.h5",
    "revision": "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z",
    "sha256": ("16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f"),
}

EXPECTED_VERSIONS = {
    "policyengine": "4.18.9",
    "policyengine-us": "1.767.3",
    "policyengine-core": "3.30.3",
}


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["case_id"], row["concept"], row["kind"]


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _implementation_provenance() -> dict[str, str]:
    return {
        "tracer_path": TRACER_RELATIVE_PATH,
        "tracer_sha256": _sha256_path(ROOT / TRACER_RELATIVE_PATH),
        "runner_path": RUNNER_RELATIVE_PATH,
        "runner_sha256": _sha256_path(ROOT / RUNNER_RELATIVE_PATH),
    }


def _validate_base_report(report: dict[str, Any]) -> None:
    if report.get("schema_version") != "axiom.comparison_report.v2.1":
        raise ValueError("base report schema must be axiom.comparison_report.v2.1")
    if report.get("suite") != "ca-snap-ecps":
        raise ValueError("base report must be for ca-snap-ecps")
    if report.get("provenance") != EXPECTED_BASE_PROVENANCE:
        raise ValueError("base report provenance does not match the pinned run")

    mismatches = report.get("mismatches")
    if not isinstance(mismatches, list) or len(mismatches) != (
        EXPECTED_BASE_MISMATCHES
    ):
        raise ValueError(
            "base report must carry exactly "
            f"{EXPECTED_BASE_MISMATCHES} complete mismatches"
        )
    summary = report.get("summary") or {}
    if summary.get("mismatch_count") != EXPECTED_BASE_MISMATCHES:
        raise ValueError("base report summary mismatch_count is not 684")
    stored = summary.get(
        "stored_mismatch_example_count",
        len(mismatches),
    )
    if stored != EXPECTED_BASE_MISMATCHES:
        raise ValueError("base report mismatch list is incomplete")

    keys = [_row_key(row) for row in mismatches]
    if len(set(keys)) != len(keys):
        raise ValueError("base report contains duplicate mismatch keys")

    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != (EXPECTED_BASE_MISMATCH_HOUSEHOLDS):
        raise ValueError("base report mismatch-case evidence is incomplete")
    cases_by_id: dict[str, dict[str, Any]] = {}
    nested_keys: set[tuple[str, str, str]] = set()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in cases_by_id:
            raise ValueError("base report contains duplicate or invalid case ids")
        cases_by_id[case_id] = case
        for row in case.get("mismatches") or []:
            nested_keys.add((case_id, row["concept"], row["kind"]))
    if set(keys) != nested_keys:
        raise ValueError(
            "base report top-level mismatches do not exactly match case evidence"
        )

    unexplained = [row for row in mismatches if row.get("disposition") is None]
    if len(unexplained) != EXPECTED_BASE_UNEXPLAINED_ROWS:
        raise ValueError(
            "base report must carry exactly "
            f"{EXPECTED_BASE_UNEXPLAINED_ROWS} unexplained rows"
        )
    households = {row["case_id"] for row in unexplained}
    if len(households) != EXPECTED_BASE_RESIDUAL_HOUSEHOLDS:
        raise ValueError(
            "base report must carry exactly "
            f"{EXPECTED_BASE_RESIDUAL_HOUSEHOLDS} residual households"
        )


def _load_base_report(
    *,
    base_ref: str | None,
    base_report: Path | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    if (base_ref is None) == (base_report is None):
        raise ValueError("provide exactly one of --base-ref or --base-report")

    source: dict[str, str]
    if base_ref is not None:
        if not base_ref.strip() or base_ref.startswith("-"):
            raise ValueError(f"invalid base ref {base_ref!r}")
        resolved = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{base_ref}^{{commit}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", resolved):
            raise ValueError(f"git resolved {base_ref!r} ambiguously: {resolved!r}")
        raw = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                f"{resolved}:{REPORT_RELATIVE_PATH}",
            ],
            check=True,
            capture_output=True,
        ).stdout
        source = {"kind": "git", "commit": resolved}
    else:
        assert base_report is not None
        raw = base_report.read_bytes()
        source = {"kind": "path", "path": str(base_report)}

    digest = hashlib.sha256(raw).hexdigest()
    if digest != BASE_REPORT_SHA256:
        raise ValueError(
            f"base report sha256 mismatch: expected {BASE_REPORT_SHA256}, got {digest}"
        )
    report = json.loads(raw)
    if not isinstance(report, dict):
        raise ValueError("base report must be a JSON object")
    _validate_base_report(report)
    return report, {**source, "sha256": digest}


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
    report: dict[str, Any],
    limit: int | None,
) -> list[dict[str, Any]]:
    unexplained_keys = {
        _row_key(row) for row in report["mismatches"] if row.get("disposition") is None
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
    return residuals


def _load_compact_evidence(case_ids: set[str]) -> dict[str, dict[str, Any]]:
    compact: dict[str, dict[str, Any]] = {}
    for chunk in sorted(CASE_DIR.glob("chunk-*.json")):
        for case in json.loads(chunk.read_text()):
            if case["id"] in case_ids:
                if case["id"] in compact:
                    raise ValueError(
                        f"Committed compact evidence duplicates {case['id']}"
                    )
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


class _LegacyCalendarAverageMixin:
    """Reproduce the requested-month normalization used by the stamped report.

    Before PR #416, the comparison outputs ``snap`` and
    ``snap_normal_allotment`` were divided by 12, while diagnostic
    intermediates retained their annual dataset values. Supplying that exact
    legacy selection through the current runner's requested-period hook is
    deliberate: it keeps input overrides applied to the annual dataset instead
    of rebuilding an unmodified direct-month situation.
    """

    def _requested_period_values(
        self,
        pe,
        cases,
        annual_values_by_case,
    ) -> list[dict[str, float | bool]]:
        from axiom_oracles.adapters.policyengine.runner import (
            _policyengine_definition_period,
            _policyengine_variable_is_boolean,
        )

        requested: list[dict[str, float | bool]] = []
        for case, annual_values in zip(
            cases,
            annual_values_by_case,
            strict=True,
        ):
            values: dict[str, float | bool] = {}
            if "-" in str(case.period):
                for variable, value in annual_values.items():
                    if _policyengine_variable_is_boolean(pe, variable, value):
                        continue
                    if _policyengine_definition_period(pe, variable) == "month":
                        values[variable] = (
                            float(value) / 12
                            if variable in LEGACY_MONTHLY_NORMALIZED_VARIABLES
                            else float(value)
                        )
            requested.append(values)
        return requested


class _InputOverrideRunner:
    def __init__(
        self,
        *,
        person: dict[str, Any] | None = None,
        spm_unit: dict[str, Any] | None = None,
    ) -> None:
        from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner

        class Runner(_LegacyCalendarAverageMixin, PolicyEngineRunner):
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
            inputs["employment_income_before_lsr"] = dict(inputs["employment_income"])
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
            raw = np.asarray(simulation.calculate(variable, period=calculation_period))
            entity = str(definition.entity.key)
            entity_ids = [
                str(entity_id) for entity_id in simulation.populations[entity].ids
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
        "zero_self_employment_and_tanf": checks(zero_self_employment_and_tanf),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    base = parser.add_mutually_exclusive_group(required=True)
    base.add_argument(
        "--base-ref",
        help=(
            "Git ref containing the exact pre-#362 disposition report. The ref "
            "is resolved to a commit before reading the report blob."
        ),
    )
    base.add_argument(
        "--base-report",
        type=Path,
        help="Path to the exact pre-#362 disposition report JSON.",
    )
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
    report, _base_source = _load_base_report(
        base_ref=args.base_ref,
        base_report=args.base_report,
    )
    runtime = _prepare_policyengine()
    residuals = _load_residuals(report, args.limit)
    case_ids = {row["case_id"] for row in residuals}
    compact = _load_compact_evidence(case_ids)

    from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner
    from axiom_oracles.core.geography import GeographyScope
    from axiom_oracles.populations.populace_us import (
        POPULACE_PINS,
        POPULACE_US_DATASET,
        load_populace_us_cases,
    )

    pin = POPULACE_PINS[("policyengine/populace-us", "populace_us_2024.h5")]
    populace_pin = {
        "dataset": POPULACE_US_DATASET,
        "revision": pin.revision,
        "sha256": pin.sha256,
    }
    if populace_pin != EXPECTED_POPULACE_PIN:
        raise ValueError(
            f"certified Populace pin changed; refusing to replay against {populace_pin}"
        )

    ca_cases = load_populace_us_cases(
        period="2026-01",
        sample_size=None,
        scope=GeographyScope(type="census_state", geoid="06"),
        dataset=POPULACE_US_DATASET,
    )
    cases_by_id = {case.case_id: case for case in ca_cases}
    if len(cases_by_id) != len(ca_cases):
        raise ValueError("Live Populace loader returned duplicate case ids")
    missing = sorted(case_ids - cases_by_id.keys())
    if missing:
        raise ValueError(f"Live Populace loader is missing residual cases: {missing}")
    cases = [cases_by_id[row["case_id"]] for row in residuals]

    class LegacyCalendarAverageRunner(
        _LegacyCalendarAverageMixin,
        PolicyEngineRunner,
    ):
        pass

    baseline = _result_values(
        LegacyCalendarAverageRunner(batch_size=10_000).run_cases(
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
        _InputOverrideRunner(spm_unit={"ca_tanf": 0, "tanf": 0}).run_cases(
            cases, COUNTERFACTUAL_VARIABLES
        )
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
            "zero_self_employment_and_tanf": (zero_self_employment_and_tanf[case_id]),
        }
        residual["requested_month_pe"] = requested_month[case_id]
        residual["requested_month_counterfactuals"] = {
            "zero_self_employment": (requested_month_zero_self_employment[case_id]),
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
        "schema_version": "axiom_oracles.ca_snap_residual_trace.v2",
        "runtime": runtime,
        "annual_baseline_semantics": LEGACY_ANNUAL_SEMANTICS,
        "base_report": {
            "path": REPORT_RELATIVE_PATH,
            "provenance": report["provenance"],
            "sha256": BASE_REPORT_SHA256,
        },
        "implementation": _implementation_provenance(),
        "populace_pin": populace_pin,
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
