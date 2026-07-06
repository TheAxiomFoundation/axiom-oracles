#!/usr/bin/env python3
"""Compare source-backed NYC income-tax components against PolicyEngine.

This is intentionally a component comparison, not a final `nyc_income_tax`
comparison. The full liability path still needs NY taxable income and the rest
of the NYC credit stack before it can be compared honestly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from policyengine_us import Simulation

from axiom_oracles.comparison.dispositions import apply_dispositions_from_dir


REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "public" / "data"
RULESPEC_NY = Path.home() / "rulespec-us-ny"
AXIOM_ENGINE = (
    Path.home() / "axiom-rules-engine" / "target" / "release" / "axiom-rules-engine"
)

SCHOOL_PROGRAM = (
    RULESPEC_NY
    / "policies"
    / "tax"
    / "it-201-instructions"
    / "nyc-school-tax-credit-rate-reduction.yaml"
)
CDCC_PROGRAM = (
    RULESPEC_NY
    / "policies"
    / "tax"
    / "it-216-instructions"
    / "nyc-child-dependent-care-credit.yaml"
)

SCHOOL_BASE = (
    "us-ny:policies/tax/it-201-instructions/"
    "nyc-school-tax-credit-rate-reduction"
)
SCHOOL_OUTPUT = (
    f"{SCHOOL_BASE}#nyc_school_tax_credit_rate_reduction_amount"
)
CDCC_BASE = (
    "us-ny:policies/tax/it-216-instructions/nyc-child-dependent-care-credit"
)
CDCC_OUTPUT = f"{CDCC_BASE}#form_it216_line_24_nyc_child_dependent_care_credit"

TAX_YEAR_PERIOD = {
    "period_kind": "tax_year",
    "start": "2025-01-01",
    "end": "2025-12-31",
}
INTERVAL = {"start": "2025-01-01", "end": "2025-12-31"}
TOLERANCE = 0.01


@dataclass(frozen=True)
class ComponentCase:
    case_id: str
    concept: str
    description: str
    component: str
    axiom_program: Path
    axiom_output: str
    axiom_inputs: dict[str, Any]
    pe_variable: str
    pe_situation: dict[str, Any]
    metadata: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report output path. Defaults to reports/<name>-0-<date>.json.",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Also write dashboard/public/data report and update manifest.",
    )
    args = parser.parse_args()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output = args.output or (
        REPO_ROOT
        / "reports"
        / f"axiom-policyengine-nyc-income-tax-components-0-{today}.json"
    )
    cases = _cases()
    artifacts = {
        SCHOOL_PROGRAM: Path("/tmp/nyc-school-rate.compiled.json"),
        CDCC_PROGRAM: Path("/tmp/nyc-cdcc.compiled.json"),
    }
    for program, artifact in artifacts.items():
        _compile(program, artifact)

    rows = []
    for case in cases:
        axiom_value = _run_axiom_case(artifacts[case.axiom_program], case)
        pe_value = _run_policyengine_case(case)
        rows.append((case, axiom_value, pe_value))

    report = _merge_dispositions(_build_report(rows))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Wrote: {output}")

    if args.dashboard:
        target = DASHBOARD_DATA / "axiom-policyengine-nyc-income-tax-components.json"
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        _add_to_manifest(target.name)
        print(f"Wrote dashboard report: {target}")

    summary = report["summary"]
    print(
        "NYC component comparison: "
        f"{summary['match_count']}/{summary['comparison_count']} matched; "
        f"{summary['mismatch_count']} mismatches"
    )
    return 0


def _compile(program: Path, artifact: Path) -> None:
    subprocess.run(
        [
            str(AXIOM_ENGINE),
            "compile",
            "--program",
            str(program),
            "--output",
            str(artifact),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _run_axiom_case(artifact: Path, case: ComponentCase) -> float:
    request = {
        "mode": "fast",
        "dataset": {
            "inputs": [
                _input_record(case.axiom_program, name, value)
                for name, value in case.axiom_inputs.items()
            ],
            "relations": [],
        },
        "queries": [
            {
                "entity_id": "tax_unit:1",
                "period": TAX_YEAR_PERIOD,
                "outputs": [case.axiom_output],
            }
        ],
    }
    completed = subprocess.run(
        [str(AXIOM_ENGINE), "run-compiled", "--artifact", str(artifact)],
        check=True,
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    response = json.loads(completed.stdout)
    output = response["results"][0]["outputs"][case.axiom_output]
    return float(output["value"]["value"])


def _input_record(program: Path, name: str, value: Any) -> dict[str, Any]:
    if program == SCHOOL_PROGRAM:
        base = SCHOOL_BASE
    elif program == CDCC_PROGRAM:
        base = CDCC_BASE
    else:
        raise ValueError(f"unknown program: {program}")
    if isinstance(value, bool):
        kind = "bool"
        encoded = value
    elif isinstance(value, int):
        kind = "integer"
        encoded = value
    else:
        kind = "decimal"
        encoded = str(value)
    return {
        "name": f"{base}#input.{name}",
        "entity": "TaxUnit",
        "entity_id": "tax_unit:1",
        "interval": INTERVAL,
        "value": {"kind": kind, "value": encoded},
    }


def _run_policyengine_case(case: ComponentCase) -> float:
    sim = Simulation(situation=case.pe_situation)
    value = sim.calculate(case.pe_variable, 2026)
    return float(value[0])


def _cases() -> list[ComponentCase]:
    cases: list[ComponentCase] = []
    for status, income, table, expected_case in [
        ("SINGLE", 20_000, "single", "single-20k"),
        ("JOINT", 20_000, "joint", "joint-20k"),
        ("HEAD_OF_HOUSEHOLD", 20_000, "head", "head-20k"),
        ("SEPARATE", 20_000, "single", "separate-20k"),
        ("SURVIVING_SPOUSE", 20_000, "joint", "surviving-spouse-20k"),
        ("JOINT", 500_001, "joint", "joint-500001"),
    ]:
        cases.append(
            ComponentCase(
                case_id=f"nyc-school-rate-{expected_case}",
                concept=SCHOOL_OUTPUT,
                description="NYC school tax credit rate-reduction amount",
                component="school_rate_reduction",
                axiom_program=SCHOOL_PROGRAM,
                axiom_output=SCHOOL_OUTPUT,
                axiom_inputs={
                    "nyc_taxable_income": income,
                    "nyc_school_tax_credit_rate_reduction_joint_table_applies": (
                        table == "joint"
                    ),
                    "nyc_school_tax_credit_rate_reduction_single_table_applies": (
                        table == "single"
                    ),
                    "nyc_school_tax_credit_rate_reduction_head_of_household_table_applies": (
                        table == "head"
                    ),
                },
                pe_variable="nyc_school_tax_credit_rate_reduction_amount",
                pe_situation=_pe_base_situation(
                    {
                        "nyc_taxable_income": {2026: income},
                        "filing_status": {2026: status},
                    }
                ),
                metadata={
                    "suite": "nyc-income-tax-gap",
                    "population": "synthetic-components",
                    "component": "school_rate_reduction",
                    "filing_status": status,
                    "nyc_taxable_income": income,
                },
            )
        )

    for case_id, agi, ny_cdcc, expenses, child_ages in [
        ("full-year-25k-one-under4", 25_000, 1000, 1000, [3]),
        ("full-year-27500-one-under4", 27_500, 1000, 1000, [3]),
        ("full-year-30001-one-under4", 30_001, 1000, 1000, [3]),
        ("full-year-25k-no-under4", 25_000, 1000, 1000, [5]),
        ("full-year-25k-half-expenses-under4", 25_000, 1000, 2000, [3, 5]),
    ]:
        under_four_count = sum(1 for age in child_ages if age < 4)
        share = under_four_count / len(child_ages) if child_ages else 0
        line_23 = expenses * share
        limitation = _nyc_cdcc_limitation_decimal(agi)
        cases.append(
            ComponentCase(
                case_id=f"nyc-cdcc-{case_id}",
                concept=CDCC_OUTPUT,
                description="NYC child and dependent care credit, full-year slice",
                component="cdcc_full_year",
                axiom_program=CDCC_PROGRAM,
                axiom_output=CDCC_OUTPUT,
                axiom_inputs={
                    "fagi": agi,
                    "has_child_under_four_years_old": under_four_count > 0,
                    "qualifies_for_new_york_state_child_dependent_care_credit": (
                        ny_cdcc > 0
                    ),
                    "form_it216_line_14_amount": ny_cdcc,
                    "form_it216_line_23_amount": line_23,
                    "form_it216_line_3a_amount": expenses,
                    "nyc_child_dependent_care_credit_limitation_table_decimal_amount": limitation,
                    "is_full_year_new_york_city_resident": True,
                    "is_part_year_new_york_city_resident": False,
                    "new_york_city_tax_liability_for_credit": 0,
                    "form_it360_1_line_18_column_b_amount": 0,
                    "form_it360_1_line_18_column_a_amount": 1,
                },
                pe_variable="nyc_cdcc",
                pe_situation=_pe_cdcc_situation(
                    agi=agi,
                    ny_cdcc=ny_cdcc,
                    expenses=expenses,
                    child_ages=child_ages,
                ),
                metadata={
                    "suite": "nyc-income-tax-gap",
                    "population": "synthetic-components",
                    "component": "cdcc_full_year",
                    "fagi": agi,
                    "ny_cdcc": ny_cdcc,
                    "child_ages": child_ages,
                },
            )
        )
    return cases


def _nyc_cdcc_limitation_decimal(agi: float) -> float:
    if agi > 30_000:
        return 0.0
    if agi <= 25_000:
        return 0.75
    return 0.75 * (1 - ((agi - 25_000) / 5_000))


def _pe_base_situation(tax_unit_inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "people": {"p1": {"age": {2026: 40}}},
        "families": {"f": {"members": ["p1"]}},
        "marital_units": {"m": {"members": ["p1"]}},
        "tax_units": {"t": {"members": ["p1"], **tax_unit_inputs}},
        "spm_units": {"s": {"members": ["p1"]}},
        "households": {
            "h": {
                "members": ["p1"],
                "state_code": {2026: "NY"},
                "in_nyc": {2026: True},
            }
        },
    }


def _pe_cdcc_situation(
    *, agi: float, ny_cdcc: float, expenses: float, child_ages: list[int]
) -> dict[str, Any]:
    people = {"p1": {"age": {2026: 40}}}
    members = ["p1"]
    for idx, age in enumerate(child_ages, start=1):
        person_id = f"c{idx}"
        people[person_id] = {"age": {2026: age}}
        members.append(person_id)
    return {
        "people": people,
        "families": {"f": {"members": members}},
        "marital_units": {"m": {"members": ["p1"]}},
        "tax_units": {
            "t": {
                "members": members,
                "adjusted_gross_income": {2026: agi},
                "ny_cdcc": {2026: ny_cdcc},
                "tax_unit_childcare_expenses": {2026: expenses},
                "filing_status": {2026: "SINGLE"},
            }
        },
        "spm_units": {"s": {"members": members}},
        "households": {
            "h": {
                "members": members,
                "state_code": {2026: "NY"},
                "in_nyc": {2026: True},
            }
        },
    }


def _build_report(rows: list[tuple[ComponentCase, float, float]]) -> dict[str, Any]:
    mismatches = []
    cases = []
    aggregate = defaultdict(_aggregate)
    for case, left, right in rows:
        diff = abs(left - right)
        matches = diff <= TOLERANCE
        aggregate[case.concept]["comparison_count"] += 1
        aggregate[case.concept]["left_weighted_sum"] += left
        aggregate[case.concept]["right_weighted_sum"] += right
        if matches:
            aggregate[case.concept]["match_count"] += 1
        else:
            aggregate[case.concept]["mismatch_count"] += 1
        mismatch = None
        if not matches:
            mismatch = {
                "case_id": case.case_id,
                "concept": case.concept,
                "description": case.description,
                "difference": diff,
                "kind": "amount_difference",
                "left": left,
                "right": right,
                "tolerance": TOLERANCE,
                "scenario": case.component,
            }
            mismatches.append(mismatch)
        cases.append(
            {
                "case_id": case.case_id,
                "left_engine": "axiom",
                "right_engine": "policyengine",
                "left_errors": [],
                "right_errors": [],
                "metadata": case.metadata,
                "match_rate": 100 if matches else 0,
                "mismatches": [mismatch] if mismatch else [],
            }
        )

    aggregates = []
    concepts = []
    descriptions = {
        SCHOOL_OUTPUT: "NYC school tax credit rate-reduction amount",
        CDCC_OUTPUT: "NYC child and dependent care credit, full-year slice",
    }
    for concept, bucket in aggregate.items():
        compared = bucket["comparison_count"]
        mismatched = bucket["mismatch_count"]
        matched = bucket["match_count"]
        rate = matched / compared * 100 if compared else None
        row = {
            "category": "tax",
            "comparison": "amount",
            "comparison_count": compared,
            "comparison_weight": compared,
            "components": [],
            "concept": concept,
            "description": descriptions[concept],
            "left_weighted_sum": bucket["left_weighted_sum"],
            "match_count": matched,
            "match_rate": rate,
            "match_weight": matched,
            "mismatch_count": mismatched,
            "mismatch_weight": mismatched,
            "missing_both_count": 0,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "parent": "us-ny:tax/nyc-income-tax#liability",
            "right_weighted_sum": bucket["right_weighted_sum"],
            "tolerance": TOLERANCE,
            "weighted_difference": bucket["left_weighted_sum"]
            - bucket["right_weighted_sum"],
            "weighted_match_rate": rate,
        }
        aggregates.append(row)
        concepts.append(
            {
                "category": "tax",
                "comparison": "amount",
                "components": [],
                "description": descriptions[concept],
                "id": concept,
                "parent": "us-ny:tax/nyc-income-tax#liability",
                "tolerance": TOLERANCE,
            }
        )

    compared = len(rows)
    mismatch_count = len(mismatches)
    match_count = compared - mismatch_count
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "nyc-income-tax-gap",
        "population": "synthetic-components",
        "engines": {"left": "axiom", "right": "policyengine"},
        "locales": ["US-NY-NYC"],
        "scope": {"type": "census_place", "geoid": "3651000"},
        "concepts": concepts,
        "case_count": len(cases),
        "summary": {
            "alarms": [
                {
                    "code": "component-only",
                    "severity": "warning",
                    "message": (
                        "NYC comparison is a synthetic source-backed component "
                        "check, not a full Enhanced CPS run. It covers school-tax "
                        "rate reduction and full-year CDCC only, and is not a "
                        "final nyc_income_tax liability comparison."
                    ),
                },
                {
                    "code": "source-vs-pe-rounded-base",
                    "severity": "info",
                    "message": (
                        "School-tax second-band differences are caused by "
                        "Axiom using source-stated rounded base amounts while "
                        "PolicyEngine derives bracket carry-ins from marginal "
                        "rates and thresholds."
                    ),
                },
            ],
            "comparison_count": compared,
            "error_count": 0,
            "errors_by_engine": [],
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "mismatches_by_concept": _counts(mismatches, "concept"),
            "mismatches_by_kind": _counts(mismatches, "kind"),
            "mismatches_by_scenario": _counts(mismatches, "scenario"),
            "weighted": {
                "comparison_weight": compared,
                "match_rate": match_count / compared * 100 if compared else None,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
            },
        },
        "aggregates": aggregates,
        "mismatches": mismatches,
        "errors": [],
        "cases": cases,
    }


def _merge_dispositions(report: dict[str, Any]) -> dict[str, Any]:
    return apply_dispositions_from_dir(
        report,
        REPO_ROOT / "dispositions",
        repo_root=REPO_ROOT,
    )


def _aggregate() -> dict[str, Any]:
    return {
        "comparison_count": 0,
        "match_count": 0,
        "mismatch_count": 0,
        "left_weighted_sum": 0.0,
        "right_weighted_sum": 0.0,
    }


def _counts(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in Counter(row.get(key) for row in rows).items()
    ]


def _add_to_manifest(filename: str) -> None:
    manifest_path = DASHBOARD_DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    reports = manifest.setdefault("reports", [])
    if filename not in reports:
        reports.append(filename)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
