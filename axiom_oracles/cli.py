from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import click

from .adapters.accessnyc import (
    AccessNycApiRunner,
    AccessNycDroolsRunner,
    AccessNycPythonRunner,
)
from .adapters.axiom import (
    AxiomRulesRunner,
    US_FEDERAL_INCOME_TAX_BRIDGE_TARGET,
    US_FEDERAL_INCOME_TAX_IMPORTS,
    US_FEDERAL_INCOME_TAX_PROGRAM_RULES,
    US_SNAP_CO_COMPILED_ARTIFACT_PATH,
    attach_axiom_snap_co_inputs,
    attach_axiom_tax_inputs,
    attach_axiom_tax_itemization_choice,
)
from .adapters.policyengine import PolicyEngineRunner, PolicyEngineTaxsimRunner
from .adapters.prd import PrdPackageRunner
from .adapters.taxsim import TaxsimPackageRunner, attach_taxsim_inputs
from .audit.accessnyc_rules import audit_accessnyc_rules
from .comparison.comparator import Comparator, HouseholdComparison
from .comparison.mappings import (
    ProgramMapping,
    comparable_mappings,
    comparison_scope_for_targets,
    engine_targets_for_concepts,
)
from .comparison.report import build_comparison_report
from .core.case import Case, Concepts
from .core.engine import EngineAdapter
from .core.geography import GeographyScope, scope_contains
from .populations import load_enhanced_cps_cases
from .suites import available_suites, load_suite


NYC_BENEFITS_DATASET_URL = (
    "https://data.cityofnewyork.us/resource/kvhd-5fmu.json?"
    "$select=program_code&$limit=5000"
)
DEFAULT_PERIOD = "2026-05"
TAXSIM_DEFAULT_PERIOD = "2024"

_SNAP_CONCEPTS = frozenset({Concepts.SNAP_BENEFIT, Concepts.SNAP_ELIGIBLE})


def _wants_snap(concept_ids: tuple[str, ...]) -> bool:
    return any(c in _SNAP_CONCEPTS for c in concept_ids)


@click.group()
def cli() -> None:
    """Axiom program validation and oracle-comparison tools."""


@cli.command()
@click.argument(
    "left",
    type=click.Choice(["accessnyc", "policyengine", "axiom", "taxsim", "prd"]),
)
@click.argument(
    "right",
    type=click.Choice(["accessnyc", "policyengine", "axiom", "taxsim", "prd"]),
)
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
    help="Household sample size. Use 0 to load the full population.",
)
@click.option(
    "--period",
    default=None,
    show_default="auto",
    help=(
        "Validation period. Defaults to 2024 for TAXSIM comparisons and "
        "2026-05 otherwise."
    ),
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
    "--axiom-program",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    envvar="AXIOM_RULESPEC_PROGRAM",
    help="RuleSpec program YAML to execute for Axiom comparisons.",
)
@click.option(
    "--axiom-engine-binary",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    envvar="AXIOM_RULES_ENGINE_BINARY",
    help="Path to the axiom-rules executable.",
)
@click.option(
    "--axiom-entity-id",
    default="tax_unit",
    show_default=True,
    help="Default Axiom query entity id when a case does not override it.",
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
    period: str | None,
    ecps_dataset: str | None,
    concepts: tuple[str, ...],
    categories: tuple[str, ...],
    locales: tuple[str, ...],
    accessnyc_mode: str,
    accessnyc_rules_dir: Path | None,
    accessnyc_python_path: Path | None,
    axiom_program: Path | None,
    axiom_engine_binary: Path | None,
    axiom_entity_id: str,
    output_path: Path | None,
    json_output: bool,
) -> None:
    """Compare two executable program systems over a validation population."""

    if left == right:
        raise click.ClickException("Choose two different systems to compare.")

    period = _resolve_period(period, left, right)
    comparison_scope = comparison_scope_for_targets(left, right)
    suite_name = _resolve_suite_name(suite, left, right)
    cases = _load_population_cases(
        population=population,
        suite_name=suite_name,
        scope=comparison_scope,
        period=period,
        sample_size=sample_size,
        ecps_dataset=ecps_dataset,
        categories=categories,
        concepts=concepts,
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
    try:
        cases = _prepare_cases_for_engines(
            cases,
            {left, right},
            concept_ids,
            axiom_program=axiom_program,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    left_runner = _build_runner(
        left,
        accessnyc_mode,
        accessnyc_rules_dir,
        accessnyc_python_path,
        concept_ids,
        axiom_program=axiom_program,
        axiom_engine_binary=axiom_engine_binary,
        axiom_entity_id=axiom_entity_id,
        paired_engine=right,
    )
    right_runner = _build_runner(
        right,
        accessnyc_mode,
        accessnyc_rules_dir,
        accessnyc_python_path,
        concept_ids,
        axiom_program=axiom_program,
        axiom_engine_binary=axiom_engine_binary,
        axiom_entity_id=axiom_entity_id,
        paired_engine=left,
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
    categories: tuple[str, ...] = (),
    concepts: tuple[str, ...] = (),
) -> list[Case]:
    if population == "enhanced-cps":
        return load_enhanced_cps_cases(
            scope=scope,
            period=period,
            sample_size=sample_size or None,
            dataset=ecps_dataset,
            case_unit=_enhanced_cps_case_unit(categories, concepts),
        )
    if population == "synthetic":
        cases = [
            replace(case, period=period)
            for case in _filter_cases_for_scope(load_suite(suite_name), scope)
        ]
        if sample_size:
            return cases[:sample_size]
        return cases
    raise click.ClickException(f"Unknown population '{population}'.")


def _enhanced_cps_case_unit(
    categories: tuple[str, ...],
    concepts: tuple[str, ...],
) -> str:
    if categories and set(categories) == {"tax"}:
        return "tax_unit"
    if concepts and all(concept.startswith("us:tax/") for concept in concepts):
        return "tax_unit"
    return "household"


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


def _prepare_cases_for_engines(
    cases: list[Case],
    engines: set[str],
    concept_ids: tuple[str, ...] = (),
    *,
    axiom_program: Path | None = None,
) -> list[Case]:
    prepared = cases
    if "taxsim" in engines:
        prepared = attach_taxsim_inputs(prepared)
    if (
        "axiom" in engines
        and axiom_program is None
        and Concepts.FEDERAL_INCOME_TAX in concept_ids
    ):
        prepared = attach_axiom_tax_inputs(prepared)
        if engines & {"policyengine", "taxsim"}:
            prepared = attach_axiom_tax_itemization_choice(prepared)
    if "axiom" in engines and _wants_snap(concept_ids):
        # Axiom SNAP is encoded only for Colorado today. Filter the
        # population to CO households so the comparison is apples-to-apples.
        prepared = [case for case in prepared if _is_co_household(case)]
        prepared = attach_axiom_snap_co_inputs(prepared)
    return prepared


def _is_co_household(case: Case) -> bool:
    scope = case.scope
    if scope is None or not scope.geoid:
        return False
    return str(scope.geoid)[:2] == "08"


def _resolve_period(period: str | None, left: str, right: str) -> str:
    if period:
        return period
    if "taxsim" in {left, right}:
        return TAXSIM_DEFAULT_PERIOD
    return DEFAULT_PERIOD


SNAP_DEFAULT_PERIOD = "2026-01"


def _build_runner(
    engine: str,
    accessnyc_mode: str,
    accessnyc_rules_dir: Path | None,
    accessnyc_python_path: Path | None,
    concept_ids: tuple[str, ...],
    *,
    axiom_program: Path | None = None,
    axiom_engine_binary: Path | None = None,
    axiom_entity_id: str = "tax_unit",
    paired_engine: str | None = None,
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
        if paired_engine == "taxsim":
            return PolicyEngineTaxsimRunner()
        return PolicyEngineRunner()
    if engine == "axiom":
        # SNAP runs through a precompiled artifact (avoids re-compiling the
        # CO RuleSpec module on every case and the engine's `kind: reiteration`
        # support requirement). FIT and other concepts keep compiling fresh
        # from the program imports.
        wants_snap = _wants_snap(concept_ids) and axiom_program is None
        compiled_artifact = (
            US_SNAP_CO_COMPILED_ARTIFACT_PATH if wants_snap else None
        )
        program_imports = (
            US_FEDERAL_INCOME_TAX_IMPORTS
            if axiom_program is None
            and not wants_snap
            and Concepts.FEDERAL_INCOME_TAX in concept_ids
            else ()
        )
        return AxiomRulesRunner(
            program_path=axiom_program,
            compiled_artifact_path=compiled_artifact,
            binary_path=axiom_engine_binary,
            default_entity_id="household" if wants_snap else axiom_entity_id,
            default_entity="Household" if wants_snap else "TaxUnit",
            program_imports=program_imports,
            program_rules=US_FEDERAL_INCOME_TAX_PROGRAM_RULES
            if program_imports
            else (),
            generated_program_target=US_FEDERAL_INCOME_TAX_BRIDGE_TARGET
            if program_imports
            else None,
            prune_unsupported_inputs=bool(program_imports),
        )
    if engine == "taxsim":
        return TaxsimPackageRunner()
    if engine == "prd":
        return PrdPackageRunner()
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
    return build_comparison_report(
        suite_name=suite_name,
        population=population,
        locales=locales,
        scope=scope,
        cases=cases,
        mappings=mappings,
        comparisons=comparisons,
    )


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
