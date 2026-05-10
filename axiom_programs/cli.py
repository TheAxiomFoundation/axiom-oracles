from __future__ import annotations

from collections import Counter
from collections import defaultdict
from dataclasses import replace
import json
from pathlib import Path

import click

from .adapters.accessnyc import (
    AccessNycApiRunner,
    AccessNycDroolsRunner,
    AccessNycPythonRunner,
)
from .adapters.policyengine import PolicyEngineRunner
from .audit.accessnyc_rules import audit_accessnyc_rules
from .comparison.comparator import Comparator, HouseholdComparison
from .comparison.mappings import (
    ProgramMapping,
    comparable_mappings,
    comparison_scope_for_targets,
    engine_targets_for_concepts,
)
from .core.case import Case
from .core.engine import EngineAdapter
from .core.geography import GeographyScope, scope_contains
from .core.results import Value
from .populations import load_enhanced_cps_cases
from .suites import available_suites, load_suite


NYC_BENEFITS_DATASET_URL = (
    "https://data.cityofnewyork.us/resource/kvhd-5fmu.json?"
    "$select=program_code&$limit=5000"
)


@click.group()
def cli() -> None:
    """Axiom program validation and oracle-comparison tools."""


@cli.command()
@click.argument("left", type=click.Choice(["accessnyc", "policyengine", "axiom"]))
@click.argument("right", type=click.Choice(["accessnyc", "policyengine", "axiom"]))
@click.option(
    "--suite",
    default="auto",
    show_default=True,
    help=(
        "Synthetic case/scenario suite. Used when --population synthetic; "
        "'auto' chooses an ACCESS NYC-compatible NYC suite."
    ),
)
@click.option(
    "--population",
    type=click.Choice(["enhanced-cps", "synthetic"]),
    default="enhanced-cps",
    show_default=True,
    help="Validation population source.",
)
@click.option(
    "--sample-size",
    type=int,
    default=50,
    show_default=True,
    help="Enhanced CPS household sample size. Use 0 to load the full population.",
)
@click.option(
    "--period",
    default="2026-05",
    show_default=True,
    help="Period for Enhanced CPS-backed cases.",
)
@click.option(
    "--ecps-dataset",
    type=click.Path(dir_okay=False),
    help="Override the Enhanced CPS dataset path or hf:// URL.",
)
@click.option(
    "--concept",
    "concepts",
    multiple=True,
    help="Concept ID to compare. Defaults to the mapped intersection for both engines.",
)
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Limit default concepts to mapping categories such as food or health.",
)
@click.option(
    "--locale",
    "locales",
    multiple=True,
    help="Locale code such as US-NY-NYC. Defaults to locales declared by the suite cases.",
)
@click.option(
    "--accessnyc-mode",
    type=click.Choice(["api", "python", "drools"]),
    default="api",
    show_default=True,
    help="Run ACCESS NYC through the hosted API, local Python replatform, or Drools.",
)
@click.option(
    "--accessnyc-rules-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to ACCESS-NYC-Rules/accessnyc/rules for a future local Drools runner.",
)
@click.option(
    "--accessnyc-python-path",
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to NYCOpportunity/benefits-screening-api for local Python mode.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the JSON comparison report to this path.",
)
@click.option("--json-output", "--json", is_flag=True, help="Emit JSON.")
def compare(
    left: str,
    right: str,
    suite: str,
    population: str,
    sample_size: int,
    period: str,
    ecps_dataset: str | None,
    concepts: tuple[str, ...],
    categories: tuple[str, ...],
    locales: tuple[str, ...],
    accessnyc_mode: str,
    accessnyc_rules_dir: Path | None,
    accessnyc_python_path: Path | None,
    output_path: Path | None,
    json_output: bool,
) -> None:
    """Compare two executable program systems over a validation population."""

    if left == right:
        raise click.ClickException("Choose two different systems to compare.")

    comparison_scope = comparison_scope_for_targets(left, right)
    suite_name = _resolve_suite_name(suite, left, right)
    cases = _load_population_cases(
        population=population,
        suite_name=suite_name,
        scope=comparison_scope,
        period=period,
        sample_size=sample_size,
        ecps_dataset=ecps_dataset,
    )
    if not cases:
        raise click.ClickException(
            "No cases found for the resolved target scope and population."
        )
    case_locales = set(locales) if locales else _case_locales(cases)
    mappings = comparable_mappings(
        left,
        right,
        locales=case_locales,
        scope=comparison_scope,
        concepts=set(concepts) or None,
        categories=set(categories) or None,
    )
    try:
        mappings = _filter_for_accessnyc_mode(
            mappings,
            left,
            right,
            accessnyc_mode,
            accessnyc_python_path,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    if not mappings:
        raise click.ClickException(
            "No comparable concepts found for those engines, locales, and filters."
        )

    concept_ids = tuple(mapping.concept_id for mapping in mappings)
    cases = [replace(case, outputs=concept_ids) for case in cases]

    left_runner = _build_runner(
        left,
        accessnyc_mode,
        accessnyc_rules_dir,
        accessnyc_python_path,
        concept_ids,
    )
    right_runner = _build_runner(
        right,
        accessnyc_mode,
        accessnyc_rules_dir,
        accessnyc_python_path,
        concept_ids,
    )

    try:
        left_results = left_runner.run_cases(cases, list(concept_ids))
        right_results = right_runner.run_cases(cases, list(concept_ids))
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    comparisons = Comparator(mappings).compare(left_results, right_results)
    report = _comparison_report(
        suite_name=suite_name,
        population=population,
        locales=case_locales,
        scope=comparison_scope,
        cases=cases,
        mappings=mappings,
        comparisons=comparisons,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    if json_output:
        click.echo(json.dumps(report, indent=2, sort_keys=True))
        return

    _echo_comparison_report(report)


@cli.group()
def accessnyc() -> None:
    """ACCESS NYC oracle and rule audit commands."""


@accessnyc.command()
@click.option(
    "--rules-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Path to ACCESS-NYC-Rules/accessnyc/rules.",
)
@click.option(
    "--dataset-url",
    default=NYC_BENEFITS_DATASET_URL,
    show_default=False,
    help="Socrata JSON endpoint containing program_code values.",
)
@click.option(
    "--dataset-codes-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional newline-delimited S2R code file, used instead of dataset-url.",
)
@click.option("--json-output", "--json", is_flag=True, help="Emit JSON.")
def audit(
    rules_dir: Path,
    dataset_url: str,
    dataset_codes_file: Path | None,
    json_output: bool,
) -> None:
    """Run static checks over ACCESS NYC Drools rules."""

    dataset_codes = _load_dataset_codes(dataset_url, dataset_codes_file)
    findings = audit_accessnyc_rules(rules_dir, dataset_codes=dataset_codes)

    if json_output:
        click.echo(json.dumps([finding.to_dict() for finding in findings], indent=2))
        return

    if not findings:
        click.echo("No findings.")
        return

    for finding in findings:
        location = ""
        if finding.file:
            location = finding.file
            if finding.line:
                location = f"{location}:{finding.line}"
            location = f" {location}"
        click.echo(
            f"[{finding.severity.upper()}] {finding.kind}{location}\n"
            f"  {finding.message}"
        )
        if finding.details:
            click.echo(f"  details: {json.dumps(finding.details, sort_keys=True)}")


def _load_dataset_codes(
    dataset_url: str,
    dataset_codes_file: Path | None,
) -> set[str] | None:
    if dataset_codes_file:
        return {
            line.strip()
            for line in dataset_codes_file.read_text().splitlines()
            if line.strip()
        }
    if not dataset_url:
        return None

    import requests

    response = requests.get(dataset_url, timeout=60)
    response.raise_for_status()
    return {
        item["program_code"]
        for item in response.json()
        if item.get("program_code", "").startswith("S2R")
    }


def _resolve_suite_name(suite: str, left: str, right: str) -> str:
    if suite != "auto":
        if suite not in available_suites():
            raise click.ClickException(f"Unknown suite '{suite}'.")
        return suite
    if "accessnyc" in {left, right}:
        return "nyc-synthetic"
    return "nyc-synthetic"


def _case_locales(cases: list[Case]) -> set[str]:
    return {case.locale for case in cases if case.locale}


def _load_population_cases(
    *,
    population: str,
    suite_name: str,
    scope: GeographyScope | None,
    period: str,
    sample_size: int,
    ecps_dataset: str | None,
) -> list[Case]:
    if population == "enhanced-cps":
        return load_enhanced_cps_cases(
            scope=scope,
            period=period,
            sample_size=sample_size or None,
            dataset=ecps_dataset,
        )
    if population == "synthetic":
        return _filter_cases_for_scope(load_suite(suite_name), scope)
    raise click.ClickException(f"Unknown population '{population}'.")


def _filter_cases_for_scope(
    cases: list[Case],
    scope: GeographyScope | None,
) -> list[Case]:
    if scope is None:
        return cases
    return [
        case
        for case in cases
        if case.scope is not None and scope_contains(scope, case.scope)
    ]


def _build_runner(
    engine: str,
    accessnyc_mode: str,
    accessnyc_rules_dir: Path | None,
    accessnyc_python_path: Path | None,
    concept_ids: tuple[str, ...],
) -> EngineAdapter:
    if engine == "accessnyc":
        if accessnyc_mode == "drools":
            return AccessNycDroolsRunner(accessnyc_rules_dir)
        if accessnyc_mode == "python":
            return AccessNycPythonRunner(
                repo_path=accessnyc_python_path,
                interested_programs=engine_targets_for_concepts(
                    list(concept_ids),
                    "accessnyc",
                ),
            )
        return AccessNycApiRunner(
            interested_programs=engine_targets_for_concepts(
                list(concept_ids),
                "accessnyc",
            )
        )
    if engine == "policyengine":
        return PolicyEngineRunner()
    raise click.ClickException(f"Engine '{engine}' is not implemented yet.")


def _filter_for_accessnyc_mode(
    mappings: list[ProgramMapping],
    left: str,
    right: str,
    accessnyc_mode: str,
    accessnyc_python_path: Path | None,
) -> list[ProgramMapping]:
    if "accessnyc" not in {left, right} or accessnyc_mode != "python":
        return mappings

    runner = AccessNycPythonRunner(repo_path=accessnyc_python_path)
    available_codes = runner.available_program_codes()
    return [
        mapping
        for mapping in mappings
        if mapping.target_for_engine("accessnyc") in available_codes
    ]


def _comparison_report(
    *,
    suite_name: str,
    population: str,
    locales: set[str],
    scope: GeographyScope | None,
    cases: list[Case],
    mappings: list[ProgramMapping],
    comparisons: list[HouseholdComparison],
) -> dict:
    cases_by_id = {case.case_id: case for case in cases}
    mismatch_rows = _mismatch_rows(comparisons, cases_by_id)
    aggregate_rows = _aggregate_rows(comparisons, cases_by_id, mappings)
    return {
        "suite": suite_name,
        "population": population,
        "locales": sorted(locales),
        "scope": scope.as_dict() if scope is not None else None,
        "concepts": [
            {
                "id": mapping.concept_id,
                "description": mapping.description,
                "category": mapping.category,
                "comparison": mapping.comparison,
            }
            for mapping in mappings
        ],
        "case_count": len(comparisons),
        "summary": {
            "match_count": sum(item.match_count for item in comparisons),
            "mismatch_count": sum(item.mismatch_count for item in comparisons),
            "comparison_count": sum(len(item.comparisons) for item in comparisons),
            "weighted": _weighted_summary(comparisons, cases_by_id),
            "mismatches_by_concept": _count_rows(mismatch_rows, "concept"),
            "mismatches_by_scenario": _count_rows(mismatch_rows, "scenario"),
        },
        "aggregates": aggregate_rows,
        "mismatches": mismatch_rows,
        "cases": [
            {
                "case_id": item.household_id,
                "left_engine": item.left_engine,
                "right_engine": item.right_engine,
                "metadata": dict(cases_by_id[item.household_id].metadata)
                if item.household_id in cases_by_id
                else {},
                "match_rate": item.match_rate,
                "mismatches": [
                    {
                        "concept": mismatch.variable,
                        "description": mismatch.description,
                        "left": mismatch.left_value,
                        "right": mismatch.right_value,
                        "difference": mismatch.difference,
                        "tolerance": mismatch.tolerance,
                    }
                    for mismatch in item.mismatches()
                ],
            }
            for item in comparisons
        ],
    }


def _mismatch_rows(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
) -> list[dict]:
    rows = []
    for item in comparisons:
        metadata = dict(cases_by_id[item.household_id].metadata)
        for mismatch in item.mismatches():
            rows.append(
                {
                    "case_id": item.household_id,
                    "scenario": metadata.get("scenario"),
                    "yearly_earned_income": metadata.get("yearly_earned_income"),
                    "ages": metadata.get("ages"),
                    "pregnant_head": metadata.get("pregnant_head"),
                    "concept": mismatch.variable,
                    "description": mismatch.description,
                    "left": mismatch.left_value,
                    "right": mismatch.right_value,
                }
            )
    return rows


def _aggregate_rows(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
    mappings: list[ProgramMapping],
) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(_aggregate_bucket)
    for item in comparisons:
        weight = _case_weight(cases_by_id.get(item.household_id))
        for comparison in item.comparisons:
            bucket = buckets[comparison.variable]
            bucket["comparison_count"] += 1
            bucket["comparison_weight"] += weight
            if comparison.matches:
                bucket["match_count"] += 1
                bucket["match_weight"] += weight
            else:
                bucket["mismatch_count"] += 1
                bucket["mismatch_weight"] += weight

            bucket["left_positive_weight"] += (
                weight if bool(comparison.left_value) else 0
            )
            bucket["right_positive_weight"] += (
                weight if bool(comparison.right_value) else 0
            )
            bucket["left_weighted_sum"] += _to_number(comparison.left_value) * weight
            bucket["right_weighted_sum"] += _to_number(comparison.right_value) * weight

    rows = []
    for mapping in mappings:
        bucket = buckets.get(mapping.concept_id)
        if bucket is None or not bucket["comparison_count"]:
            continue
        row = {
            "concept": mapping.concept_id,
            "description": mapping.description,
            "category": mapping.category,
            "comparison": mapping.comparison,
            "comparison_count": bucket["comparison_count"],
            "mismatch_count": bucket["mismatch_count"],
            "match_rate": _percentage(
                bucket["match_count"],
                bucket["comparison_count"],
            ),
            "comparison_weight": _clean_float(bucket["comparison_weight"]),
            "match_weight": _clean_float(bucket["match_weight"]),
            "mismatch_weight": _clean_float(bucket["mismatch_weight"]),
            "weighted_match_rate": _percentage(
                bucket["match_weight"],
                bucket["comparison_weight"],
            ),
        }
        if mapping.comparison == "amount":
            row.update(
                {
                    "left_weighted_sum": _clean_float(bucket["left_weighted_sum"]),
                    "right_weighted_sum": _clean_float(bucket["right_weighted_sum"]),
                    "weighted_difference": _clean_float(
                        bucket["left_weighted_sum"]
                        - bucket["right_weighted_sum"]
                    ),
                }
            )
        else:
            row.update(
                {
                    "left_positive_weight": _clean_float(
                        bucket["left_positive_weight"]
                    ),
                    "right_positive_weight": _clean_float(
                        bucket["right_positive_weight"]
                    ),
                    "left_positive_rate": _percentage(
                        bucket["left_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                    "right_positive_rate": _percentage(
                        bucket["right_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                    "positive_rate_difference": _percentage(
                        bucket["left_positive_weight"]
                        - bucket["right_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                }
            )
        rows.append(row)
    return rows


def _aggregate_bucket() -> dict[str, float | int]:
    return {
        "comparison_count": 0,
        "match_count": 0,
        "mismatch_count": 0,
        "comparison_weight": 0.0,
        "match_weight": 0.0,
        "mismatch_weight": 0.0,
        "left_positive_weight": 0.0,
        "right_positive_weight": 0.0,
        "left_weighted_sum": 0.0,
        "right_weighted_sum": 0.0,
    }


def _weighted_summary(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
) -> dict[str, float]:
    comparison_weight = 0.0
    match_weight = 0.0
    mismatch_weight = 0.0
    for item in comparisons:
        weight = _case_weight(cases_by_id.get(item.household_id))
        for comparison in item.comparisons:
            comparison_weight += weight
            if comparison.matches:
                match_weight += weight
            else:
                mismatch_weight += weight
    return {
        "comparison_weight": _clean_float(comparison_weight),
        "match_weight": _clean_float(match_weight),
        "mismatch_weight": _clean_float(mismatch_weight),
        "match_rate": _percentage(match_weight, comparison_weight),
    }


def _case_weight(case: Case | None) -> float:
    if case is None:
        return 1.0
    value = case.metadata.get("household_weight", 1)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _count_rows(rows: list[dict], key: str) -> list[dict]:
    counts = Counter(row.get(key) for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0] or ""))
    ]


def _to_number(value: Value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    return float(value)


def _percentage(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0
    return _clean_float(numerator / denominator * 100)


def _clean_float(value: float) -> float:
    rounded = round(float(value), 6)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _echo_comparison_report(report: dict) -> None:
    summary = report["summary"]
    click.echo(
        f"Population {report['population']} / suite {report['suite']} "
        f"({report['case_count']} cases, locales: {', '.join(report['locales'])})"
    )
    click.echo(
        f"Concepts: {len(report['concepts'])}; "
        f"comparisons: {summary['comparison_count']}; "
        f"mismatches: {summary['mismatch_count']}"
    )
    for case in report["cases"]:
        click.echo(f"{case['case_id']}: {case['match_rate']:.1f}% match")
        for mismatch in case["mismatches"]:
            click.echo(
                f"  {mismatch['description']}: "
                f"{mismatch['left']} != {mismatch['right']}"
            )


if __name__ == "__main__":
    cli()
