#!/usr/bin/env python3
"""Run a full NYC ECPS diagnostic comparison for encoded NYC tax components.

This is a full-population Enhanced CPS sweep, but it is not an independent
final-liability comparison. Current Axiom NYC RuleSpecs do not yet derive
NY taxable income, NY CDCC, or final NYC income tax from raw ECPS facts, so this
diagnostic uses PE/ECPS upstream tax-unit projections as Axiom inputs and
compares only the source-backed NYC component formulas.

This diagnostic deliberately loads the NYC per-city Enhanced-CPS file
(``NYC_ECPS_DATASET`` below) rather than the certified populace-us artifact
every other US suite reads: populace-us has no place geography yet, so a
national populace artifact cannot be filtered to NYC. It is the sanctioned last
Enhanced-CPS load in this repo and retires only when the populace spine grows
place grain — TheAxiomFoundation/axiom-oracles#74 (and PolicyEngine/populace#204).
The ``ecps`` naming here is therefore accurate, not a leftover lie.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from policyengine_us import Microsimulation


REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "public" / "data"
RULESPEC_NY = Path.home() / "rulespec-us-ny"
AXIOM_ENGINE = (
    Path.home() / "axiom-rules-engine" / "target" / "release" / "axiom-rules-engine"
)

NYC_ECPS_DATASET = "hf://policyengine/policyengine-us-data/cities/NYC.h5"
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
    "start": "2026-01-01",
    "end": "2026-12-31",
}
INTERVAL = {"start": "2026-01-01", "end": "2026-12-31"}
TOLERANCE = 0.01
SUITE = "nyc-income-tax-ecps-diagnostic"


@dataclass(frozen=True)
class TaxUnitRows:
    tax_unit_ids: list[int | str]
    filing_status: list[str]
    nyc_taxable_income: list[float]
    pe_school_rate_reduction: list[float]
    adjusted_gross_income: list[float]
    ny_cdcc: list[float]
    childcare_expenses: list[float]
    under_four_childcare_expenses: list[float]
    has_child_under_four: list[bool]
    pe_nyc_cdcc: list[float]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--mismatch-limit", type=int, default=500)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report output path. Defaults to reports/<name>-<sample>-<date>.json.",
    )
    parser.add_argument("--dashboard", action="store_true")
    args = parser.parse_args()

    rows = _load_tax_unit_rows(sample_size=args.sample_size)
    print(f"Loaded {len(rows.tax_unit_ids):,} NYC ECPS tax units")

    artifacts = {
        SCHOOL_PROGRAM: Path("/tmp/nyc-school-rate.compiled.json"),
        CDCC_PROGRAM: Path("/tmp/nyc-cdcc.compiled.json"),
    }
    for program, artifact in artifacts.items():
        _compile(program, artifact)

    school_left = _run_school_axiom(
        rows,
        artifacts[SCHOOL_PROGRAM],
        batch_size=args.batch_size,
    )
    cdcc_left = _run_cdcc_axiom(
        rows,
        artifacts[CDCC_PROGRAM],
        batch_size=args.batch_size,
    )

    comparisons = [
        _comparison_rows(
            rows=rows,
            concept=SCHOOL_OUTPUT,
            description="NYC school tax credit rate-reduction amount",
            component="school_rate_reduction",
            left=school_left,
            right=rows.pe_school_rate_reduction,
        ),
        _comparison_rows(
            rows=rows,
            concept=CDCC_OUTPUT,
            description="NYC child and dependent care credit, full-year slice",
            component="cdcc_full_year",
            left=cdcc_left,
            right=rows.pe_nyc_cdcc,
        ),
    ]
    report = _build_report(
        comparisons,
        sample_size=args.sample_size,
        mismatch_limit=args.mismatch_limit,
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sample_label = args.sample_size or 0
    output = args.output or (
        REPO_ROOT
        / "reports"
        / f"axiom-policyengine-nyc-income-tax-components-ecps-{sample_label}-{today}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Wrote: {output}")

    if args.dashboard:
        target = (
            DASHBOARD_DATA
            / "axiom-policyengine-nyc-income-tax-components-ecps.json"
        )
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        _add_to_manifest(target.name)
        print(f"Wrote dashboard report: {target}")

    summary = report["summary"]
    print(
        "NYC ECPS diagnostic: "
        f"{summary['match_count']:,}/{summary['comparison_count']:,} matched; "
        f"{summary['mismatch_count']:,} mismatches"
    )
    return 0


def _load_tax_unit_rows(*, sample_size: int) -> TaxUnitRows:
    sim = Microsimulation(dataset=NYC_ECPS_DATASET)
    year = 2026

    tax_unit_ids = _clean_ids(_values(sim.calculate("tax_unit_id", period=year)))
    take = sample_size if sample_size and sample_size > 0 else len(tax_unit_ids)
    take = min(take, len(tax_unit_ids))

    filing_status = [str(v) for v in _values(sim.calculate("filing_status", period=year))[:take]]
    nyc_taxable_income = _floats(sim.calculate("nyc_taxable_income", period=year))[:take]
    pe_school_rate_reduction = _floats(
        sim.calculate("nyc_school_tax_credit_rate_reduction_amount", period=year)
    )[:take]
    adjusted_gross_income = _floats(
        sim.calculate("adjusted_gross_income", period=year)
    )[:take]
    ny_cdcc = _floats(sim.calculate("ny_cdcc", period=year))[:take]
    childcare_expenses = _floats(
        sim.calculate("tax_unit_childcare_expenses", period=year)
    )[:take]
    under_four_childcare_expenses = _floats(
        sim.calculate("nyc_cdcc_age_restricted_expenses", period=year)
    )[:take]
    pe_nyc_cdcc = _floats(sim.calculate("nyc_cdcc", period=year))[:take]
    has_child_under_four = _has_under_four_children(sim, year, tax_unit_ids[:take])

    return TaxUnitRows(
        tax_unit_ids=tax_unit_ids[:take],
        filing_status=filing_status,
        nyc_taxable_income=nyc_taxable_income,
        pe_school_rate_reduction=pe_school_rate_reduction,
        adjusted_gross_income=adjusted_gross_income,
        ny_cdcc=ny_cdcc,
        childcare_expenses=childcare_expenses,
        under_four_childcare_expenses=under_four_childcare_expenses,
        has_child_under_four=has_child_under_four,
        pe_nyc_cdcc=pe_nyc_cdcc,
    )


def _has_under_four_children(
    sim: Microsimulation,
    year: int,
    selected_tax_unit_ids: list[int | str],
) -> list[bool]:
    selected = set(selected_tax_unit_ids)
    person_tax_unit_ids = _clean_ids(
        _values(sim.calculate("tax_unit_id", period=year, map_to="person"))
    )
    ages = _floats(sim.calculate("age", period=year, map_to="person"))
    under_four_by_tax_unit = {tax_unit_id: False for tax_unit_id in selected_tax_unit_ids}
    for tax_unit_id, age in zip(person_tax_unit_ids, ages, strict=True):
        if tax_unit_id in selected and age < 4:
            under_four_by_tax_unit[tax_unit_id] = True
    return [under_four_by_tax_unit[tax_unit_id] for tax_unit_id in selected_tax_unit_ids]


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


def _run_school_axiom(
    rows: TaxUnitRows,
    artifact: Path,
    *,
    batch_size: int,
) -> list[float]:
    specs = []
    for idx, tax_unit_id in enumerate(rows.tax_unit_ids):
        status = rows.filing_status[idx]
        specs.append(
            (
                tax_unit_id,
                {
                    "nyc_taxable_income": rows.nyc_taxable_income[idx],
                    "nyc_school_tax_credit_rate_reduction_joint_table_applies": (
                        status in {"JOINT", "SURVIVING_SPOUSE"}
                    ),
                    "nyc_school_tax_credit_rate_reduction_single_table_applies": (
                        status in {"SINGLE", "SEPARATE"}
                    ),
                    "nyc_school_tax_credit_rate_reduction_head_of_household_table_applies": (
                        status == "HEAD_OF_HOUSEHOLD"
                    ),
                },
            )
        )
    return _run_axiom_batches(
        specs,
        program=SCHOOL_PROGRAM,
        artifact=artifact,
        output=SCHOOL_OUTPUT,
        batch_size=batch_size,
        label="school-rate",
    )


def _run_cdcc_axiom(
    rows: TaxUnitRows,
    artifact: Path,
    *,
    batch_size: int,
) -> list[float]:
    specs = []
    for idx, tax_unit_id in enumerate(rows.tax_unit_ids):
        agi = rows.adjusted_gross_income[idx]
        expenses = rows.childcare_expenses[idx]
        specs.append(
            (
                tax_unit_id,
                {
                    "fagi": agi,
                    "has_child_under_four_years_old": rows.has_child_under_four[idx],
                    "qualifies_for_new_york_state_child_dependent_care_credit": (
                        rows.ny_cdcc[idx] > 0
                    ),
                    "form_it216_line_14_amount": rows.ny_cdcc[idx],
                    "form_it216_line_23_amount": rows.under_four_childcare_expenses[idx],
                    "form_it216_line_3a_amount": expenses if expenses > 0 else 1,
                    "nyc_child_dependent_care_credit_limitation_table_decimal_amount": (
                        _nyc_cdcc_limitation_decimal(agi)
                    ),
                    "is_full_year_new_york_city_resident": True,
                    "is_part_year_new_york_city_resident": False,
                    "new_york_city_tax_liability_for_credit": 0,
                    "form_it360_1_line_18_column_b_amount": 0,
                    "form_it360_1_line_18_column_a_amount": 1,
                },
            )
        )
    return _run_axiom_batches(
        specs,
        program=CDCC_PROGRAM,
        artifact=artifact,
        output=CDCC_OUTPUT,
        batch_size=batch_size,
        label="cdcc",
    )


def _run_axiom_batches(
    specs: list[tuple[int | str, dict[str, Any]]],
    *,
    program: Path,
    artifact: Path,
    output: str,
    batch_size: int,
    label: str,
) -> list[float]:
    values: list[float] = []
    total = len(specs)
    for start in range(0, total, batch_size):
        batch = specs[start : start + batch_size]
        print(f"Running Axiom {label} batch {start + 1:,}-{start + len(batch):,}/{total:,}")
        request = {
            "mode": "fast",
            "dataset": {
                "inputs": [
                    _input_record(program, tax_unit_id, name, value)
                    for tax_unit_id, inputs in batch
                    for name, value in inputs.items()
                ],
                "relations": [],
            },
            "queries": [
                {
                    "entity_id": _entity_id(tax_unit_id),
                    "period": TAX_YEAR_PERIOD,
                    "outputs": [output],
                }
                for tax_unit_id, _inputs in batch
            ],
        }
        completed = subprocess.run(
            [str(AXIOM_ENGINE), "run-compiled", "--artifact", str(artifact)],
            input=json.dumps(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Axiom {label} batch {start + 1}-{start + len(batch)} failed\n"
                f"stderr:\n{completed.stderr}\nstdout:\n{completed.stdout[:2000]}"
            )
        response = json.loads(completed.stdout)
        for result in response["results"]:
            raw = result["outputs"][output]["value"]["value"]
            values.append(float(raw))
    return values


def _input_record(
    program: Path,
    tax_unit_id: int | str,
    name: str,
    value: Any,
) -> dict[str, Any]:
    if program == SCHOOL_PROGRAM:
        base = SCHOOL_BASE
    elif program == CDCC_PROGRAM:
        base = CDCC_BASE
    else:
        raise ValueError(f"unknown program: {program}")
    if isinstance(value, bool):
        kind = "bool"
        encoded = value
    elif isinstance(value, int) and not isinstance(value, bool):
        kind = "integer"
        encoded = value
    else:
        kind = "decimal"
        encoded = str(_finite_number(value))
    return {
        "name": f"{base}#input.{name}",
        "entity": "TaxUnit",
        "entity_id": _entity_id(tax_unit_id),
        "interval": INTERVAL,
        "value": {"kind": kind, "value": encoded},
    }


def _entity_id(tax_unit_id: int | str) -> str:
    return f"tax_unit:{tax_unit_id}"


def _nyc_cdcc_limitation_decimal(agi: float) -> float:
    if agi > 30_000:
        return 0.0
    if agi <= 25_000:
        return 0.75
    return 0.75 * (1 - ((agi - 25_000) / 5_000))


def _comparison_rows(
    *,
    rows: TaxUnitRows,
    concept: str,
    description: str,
    component: str,
    left: list[float],
    right: list[float],
) -> list[dict[str, Any]]:
    output = []
    for idx, tax_unit_id in enumerate(rows.tax_unit_ids):
        axiom_value = _finite_number(left[idx])
        pe_value = _finite_number(right[idx])
        output.append(
            {
                "case_id": f"ecps-tax-unit-{tax_unit_id}",
                "tax_unit_id": tax_unit_id,
                "concept": concept,
                "description": description,
                "component": component,
                "left": axiom_value,
                "right": pe_value,
                "difference": abs(axiom_value - pe_value),
                "matches": abs(axiom_value - pe_value) <= TOLERANCE,
                "metadata": {
                    "adjusted_gross_income": rows.adjusted_gross_income[idx],
                    "childcare_expenses": rows.childcare_expenses[idx],
                    "component": component,
                    "filing_status": rows.filing_status[idx],
                    "has_child_under_four": rows.has_child_under_four[idx],
                    "ny_cdcc": rows.ny_cdcc[idx],
                    "nyc_taxable_income": rows.nyc_taxable_income[idx],
                    "population": "enhanced-cps",
                    "suite": SUITE,
                    "tax_unit_id": tax_unit_id,
                    "upstream_projection": "policyengine_ecps_tax_unit_inputs",
                },
            }
        )
    return output


def _build_report(
    comparison_groups: list[list[dict[str, Any]]],
    *,
    sample_size: int,
    mismatch_limit: int,
) -> dict[str, Any]:
    all_rows = [row for group in comparison_groups for row in group]
    mismatches_all = [row for row in all_rows if not row["matches"]]
    visible_mismatches = mismatches_all[:mismatch_limit]

    aggregates = []
    concepts = []
    for concept, rows in _group_by(all_rows, "concept").items():
        compared = len(rows)
        mismatch_count = sum(1 for row in rows if not row["matches"])
        match_count = compared - mismatch_count
        left_sum = sum(row["left"] for row in rows)
        right_sum = sum(row["right"] for row in rows)
        description = str(rows[0]["description"])
        aggregate = {
            "category": "tax",
            "comparison": "amount",
            "comparison_count": compared,
            "comparison_weight": compared,
            "components": [],
            "concept": concept,
            "description": description,
            "left_weighted_sum": left_sum,
            "match_count": match_count,
            "match_rate": (match_count / compared * 100) if compared else 100.0,
            "match_weight": match_count,
            "mismatch_count": mismatch_count,
            "mismatch_weight": mismatch_count,
            "missing_both_count": 0,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "parent": "us-ny:tax/nyc-income-tax#liability",
            "right_weighted_sum": right_sum,
            "tolerance": TOLERANCE,
            "weighted_difference": left_sum - right_sum,
            "weighted_match_rate": (match_count / compared * 100)
            if compared
            else 100.0,
        }
        aggregates.append(aggregate)
        concepts.append(
            {
                "category": "tax",
                "comparison": "amount",
                "components": [],
                "description": description,
                "id": concept,
                "parent": "us-ny:tax/nyc-income-tax#liability",
                "tolerance": TOLERANCE,
            }
        )

    cases = []
    for row in visible_mismatches:
        mismatch = {
            "case_id": row["case_id"],
            "concept": row["concept"],
            "description": row["description"],
            "difference": row["difference"],
            "kind": "amount_difference",
            "left": row["left"],
            "parent": "us-ny:tax/nyc-income-tax#liability",
            "right": row["right"],
            "scenario": row["component"],
            "tolerance": TOLERANCE,
        }
        cases.append(
            {
                "case_id": row["case_id"],
                "left_engine": "axiom",
                "left_errors": [],
                "match_rate": 0,
                "metadata": row["metadata"],
                "mismatches": [mismatch],
                "right_engine": "policyengine",
                "right_errors": [],
            }
        )

    compared = len(all_rows)
    mismatch_count = len(mismatches_all)
    match_count = compared - mismatch_count
    mismatches_by_concept = [
        {"value": value, "count": count}
        for value, count in Counter(row["concept"] for row in mismatches_all).most_common()
    ]
    mismatches_by_scenario = [
        {"value": value, "count": count}
        for value, count in Counter(row["component"] for row in mismatches_all).most_common()
    ]
    diagnostics = _diagnostics(all_rows)

    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITE,
        "population": "enhanced-cps",
        "engines": {"left": "axiom", "right": "policyengine"},
        "locales": ["US-NY-NYC"],
        "scope": {"type": "census_place", "geoid": "3651000"},
        "concepts": concepts,
        "case_count": len({row["case_id"] for row in all_rows}),
        "cases": cases,
        "aggregates": aggregates,
        "mismatches": [
            {
                "case_id": row["case_id"],
                "concept": row["concept"],
                "description": row["description"],
                "difference": row["difference"],
                "kind": "amount_difference",
                "left": row["left"],
                "parent": "us-ny:tax/nyc-income-tax#liability",
                "right": row["right"],
                "scenario": row["component"],
                "tolerance": TOLERANCE,
            }
            for row in visible_mismatches
        ],
        "errors": [],
        "summary": {
            "alarms": [
                {
                    "code": "diagnostic_uses_policyengine_upstream_inputs",
                    "severity": "warning",
                    "message": (
                        "This is a full NYC Enhanced CPS component diagnostic, "
                        "not an independent final-liability comparison. Axiom "
                        "receives PE/ECPS upstream tax-unit projections such as "
                        "nyc_taxable_income and ny_cdcc because those upstream "
                        "NY/NYC inputs are not yet encoded through final "
                        "nyc_income_tax."
                    ),
                },
                {
                    "code": "not_final_nyc_income_tax",
                    "severity": "warning",
                    "message": (
                        "The report compares encoded NYC component formulas only: "
                        "school-tax rate reduction and full-year CDCC."
                    ),
                },
                {
                    "code": "school_rate_reduction_source_pe_convention",
                    "severity": "info",
                    "message": (
                        "All NYC school-rate mismatches are second-band cases. "
                        "Axiom uses source-stated rounded base amounts ($37, "
                        "$25, $21); PolicyEngine derives carry-ins from the "
                        "first-band rate and threshold ($36.936, $24.624, "
                        "$20.52)."
                    ),
                },
                {
                    "code": "stored_mismatch_examples_limited",
                    "severity": "info",
                    "message": (
                        f"Stored {len(visible_mismatches):,} mismatch examples "
                        f"out of {mismatch_count:,}; aggregate counts use the "
                        "full run."
                    ),
                },
            ],
            "comparison_count": compared,
            "error_count": 0,
            "errors_by_engine": [],
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "mismatches_by_concept": mismatches_by_concept,
            "mismatches_by_kind": [
                {"value": "amount_difference", "count": mismatch_count}
            ],
            "mismatches_by_scenario": mismatches_by_scenario,
            "diagnostics": diagnostics,
            "sample_size": sample_size,
            "stored_mismatch_example_count": len(visible_mismatches),
            "weighted": {
                "comparison_weight": compared,
                "match_rate": (match_count / compared * 100) if compared else 100.0,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
            },
        },
    }


def _diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    school_rows = [row for row in rows if row["component"] == "school_rate_reduction"]
    by_band: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "match_count": 0, "mismatch_count": 0}
    )
    for row in school_rows:
        status = str(row["metadata"]["filing_status"])
        group = _school_status_group(status)
        band = _school_income_band(group, float(row["metadata"]["nyc_taxable_income"]))
        bucket = by_band[(group, band)]
        bucket["count"] += 1
        if row["matches"]:
            bucket["match_count"] += 1
        else:
            bucket["mismatch_count"] += 1
    return {
        "school_rate_reduction": {
            "base_amount_convention": {
                "joint_or_surviving_spouse": {
                    "source_base": 37,
                    "policyengine_carry_in": 21600 * 0.00171,
                    "difference": 37 - 21600 * 0.00171,
                },
                "head_of_household": {
                    "source_base": 25,
                    "policyengine_carry_in": 14400 * 0.00171,
                    "difference": 25 - 14400 * 0.00171,
                },
                "single_or_separate": {
                    "source_base": 21,
                    "policyengine_carry_in": 12000 * 0.00171,
                    "difference": 21 - 12000 * 0.00171,
                },
            },
            "by_status_group_and_band": [
                {
                    "status_group": group,
                    "income_band": band,
                    **counts,
                }
                for (group, band), counts in sorted(by_band.items())
            ],
        }
    }


def _school_status_group(status: str) -> str:
    if status in {"JOINT", "SURVIVING_SPOUSE"}:
        return "joint_or_surviving_spouse"
    if status == "HEAD_OF_HOUSEHOLD":
        return "head_of_household"
    if status in {"SINGLE", "SEPARATE"}:
        return "single_or_separate"
    return "other"


def _school_income_band(status_group: str, income: float) -> str:
    if income <= 0:
        return "zero_or_negative"
    if status_group == "joint_or_surviving_spouse":
        if income <= 21600:
            return "first_band"
        if income <= 500000:
            return "second_band"
        return "over_limit"
    if status_group == "head_of_household":
        if income <= 14400:
            return "first_band"
        if income <= 500000:
            return "second_band"
        return "over_limit"
    if status_group == "single_or_separate":
        if income <= 12000:
            return "first_band"
        if income <= 500000:
            return "second_band"
        return "over_limit"
    return "other"


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return grouped


def _add_to_manifest(filename: str) -> None:
    manifest_path = DASHBOARD_DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    reports = manifest.setdefault("reports", [])
    if filename not in reports:
        reports.append(filename)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def _values(value: Any) -> list[Any]:
    raw = value.values if hasattr(value, "values") else value
    return list(raw)


def _floats(value: Any) -> list[float]:
    return [_finite_number(item) for item in _values(value)]


def _clean_ids(values: list[Any]) -> list[int | str]:
    cleaned = []
    for value in values:
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        cleaned.append(value)
    return cleaned


def _finite_number(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    if value in {"", None}:
        return 0.0
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        return 0.0
    return result


if __name__ == "__main__":
    raise SystemExit(main())
