from __future__ import annotations

from dataclasses import replace
import gc
import json
import os
import sys
from pathlib import Path
import tempfile

import click

from .adapters.accessnyc import (
    AccessNycApiRunner,
    AccessNycDroolsRunner,
    AccessNycPythonRunner,
)
from .adapters.axiom import (
    AxiomRulesRunner,
    US_TAX_ORACLE_BRIDGE_TARGET,
    US_TAX_ORACLE_IMPORTS,
    US_TAX_ORACLE_PROGRAM_RULES,
    US_SNAP_CO_COMPILED_ARTIFACT_PATH,
    attach_axiom_snap_co_inputs,
    attach_axiom_tax_inputs,
    attach_axiom_tax_itemization_choice,
)
from .adapters.euromod import EuromodPlatformRunner
from .adapters.policyengine import PolicyEngineRunner, PolicyEngineTaxsimRunner
from .adapters.prd import PrdPackageRunner
from .adapters.taxcalc import TaxCalcPackageRunner, attach_taxcalc_inputs
from .adapters.taxsim import TaxsimPackageRunner, attach_taxsim_inputs
from .audit.accessnyc_rules import audit_accessnyc_rules
from .comparison.comparator import Comparator, HouseholdComparison
from .comparison.mappings import (
    ProgramMapping,
    comparable_mappings,
    comparison_scope_for_targets,
    engine_targets_for_concepts,
)
from .comparison.report import (
    FULL_CASE_INPUT_LIMIT,
    ComparisonReportAccumulator,
    build_comparison_report,
)
from .conformance.compositions import (
    AXIOM_RULESPEC_ROOT_ENV,
    load_composition,
    rulespec_imports_for_concepts,
)
from .core.case import Case, Concepts
from .core.engine import EngineAdapter
from .core.geography import GeographyScope, scope_contains
from .populations import load_populace_us_cases
from .suites import available_suites, load_suite


NYC_BENEFITS_DATASET_URL = (
    "https://data.cityofnewyork.us/resource/kvhd-5fmu.json?"
    "$select=program_code&$limit=5000"
)
DEFAULT_PERIOD = "2026-05"
# The pinned policyengine-taxsim 2.30.0 binary (see adapters/taxsim/
# taxsim_pins.json) models law year 2026 rate schedules, the OBBBA standard
# deduction, childless EITC, and FICA/SECA, so TAXSIM comparisons default to
# the same 2026 validation year as every other lane. Known 2026 gap, verified
# empirically against the pinned binary: the qualifying-child credit machinery
# is absent at 2026 — CTC collapses to the $500 ODC path, and ACTC, CDCC, and
# EITC-with-children return zero (2025 models all of them, including the OBBBA
# $2,200 CTC). Comparisons of child-credit concepts at 2026 must treat TAXSIM
# zeros as an NBER gap, not evidence.
TAXSIM_DEFAULT_PERIOD = "2026"
MAX_CONSOLE_MISMATCHES = 50
EUROMOD_TO_AXIOM_INPUT_BRIDGE_METADATA_KEY = "euromod_to_axiom_input_bridge"

_SNAP_CONCEPTS = frozenset({Concepts.SNAP_BENEFIT, Concepts.SNAP_ELIGIBLE})
_STATE_TAX_DEPENDENT_FEDERAL_TAX_CONCEPTS = frozenset(
    {
        Concepts.FEDERAL_INCOME_TAX,
        Concepts.TAXABLE_INCOME,
        Concepts.TAX_BEFORE_CREDITS,
        Concepts.AMT,
    }
)


def _wants_snap(concept_ids: tuple[str, ...]) -> bool:
    return any(c in _SNAP_CONCEPTS for c in concept_ids)


def _wants_tax(concept_ids: tuple[str, ...]) -> bool:
    return any(c.startswith("us:tax/") for c in concept_ids)


def _wants_state_tax_dependent_federal_tax(concept_ids: tuple[str, ...]) -> bool:
    return any(c in _STATE_TAX_DEPENDENT_FEDERAL_TAX_CONCEPTS for c in concept_ids)


def _needs_axiom_tax_itemization_choice(concept_ids: tuple[str, ...]) -> bool:
    return (
        Concepts.STATE_INCOME_TAX in concept_ids
        or _wants_state_tax_dependent_federal_tax(concept_ids)
    )


def _rulespec_imports_for_concepts(concept_ids: tuple[str, ...]) -> tuple[str, ...]:
    # Single-sourced with the recorded per-suite compositions so the committed
    # record (conformance/compositions/<jur>.yaml) describes exactly the
    # import-set this runner builds.
    return rulespec_imports_for_concepts(concept_ids)


def _echo_resolved_axiom_composition(
    suite_name: str,
    engines: set[str],
    axiom_program: Path | None,
) -> None:
    """Surface the recorded runnable program the axiom leg composes.

    When ``--axiom-program`` is omitted, the axiom leg builds its program from
    the suite's output concepts. If the suite has a committed composition record
    (``conformance/compositions/<jur>.yaml``, axiom-oracles#185) this echoes the
    resolved program modules so the run is reproducible outside the harness, and
    — when ``AXIOM_RULESPEC_ROOT`` names a checkout — resolves them to concrete
    files and flags any that are missing. Never fails a run: a suite with no
    record (US/UK-PE suites) or an unset root is silent/soft. Backward
    compatible: passing ``--axiom-program`` skips this entirely.
    """

    if "axiom" not in engines or axiom_program is not None:
        return
    try:
        composition = load_composition(suite_name)
    except Exception:  # pragma: no cover - never let surfacing fail a run
        return
    if composition is None:
        return
    rels = ", ".join(composition.paths)
    suffix = ""
    root = os.environ.get(AXIOM_RULESPEC_ROOT_ENV)
    if root:
        resolved = composition.resolve(root)
        suffix = f"; root {resolved.root}"
        missing = resolved.missing_paths()
        if missing:
            suffix += "; WARNING missing " + ", ".join(str(p) for p in missing)
    click.echo(
        f"Resolved '{composition.suite}' composition from conformance record: "
        f"{len(composition.imports)} module(s) [{rels}] as {composition.entity}"
        f"{suffix}.",
        err=True,
    )


@click.group()
def cli() -> None:
    """Axiom program validation and oracle-comparison tools."""


def _attach_axiom_outputs(
    cases: list[Case],
    axiom_results: list,
    concept_ids: tuple[str, ...],
) -> list[Case]:
    """Stash the axiom engine's non-compared outputs into case metadata.

    In full-evidence mode the runner queries every derived rule; the values
    beyond the compared concepts' targets are the household's complete
    computed surface (intermediates included). Ordinary results land under
    ``axiom_all_outputs``. For cross-entity aggregation, intermediate values
    are not meaningful household sums, so they remain attached to their
    executed entity under ``axiom_result_aggregation_applied.components``.
    """

    compared = set(engine_targets_for_concepts(list(concept_ids), "axiom"))
    compared.update(concept_ids)
    by_id = {result.household_id: result for result in axiom_results}
    out = []
    for case in cases:
        result = by_id.get(case.case_id)
        extras = {}
        aggregation_applied = None
        if result is not None:
            for name, value in (result.values or {}).items():
                if name in compared:
                    continue
                if isinstance(value, (int, float, bool)):
                    extras[name] = value
            raw_aggregation = (
                result.raw.get("aggregation") if isinstance(result.raw, dict) else None
            )
            if isinstance(raw_aggregation, dict):
                components = []
                for component in raw_aggregation.get("components") or []:
                    if not isinstance(component, dict):
                        continue
                    component_values = component.get("values") or {}
                    components.append(
                        {
                            "entity_id": component.get("entity_id"),
                            "values": {
                                name: value
                                for name, value in component_values.items()
                                if isinstance(value, (int, float, bool))
                            },
                        }
                    )
                aggregation_applied = {
                    "strategy": raw_aggregation.get("strategy"),
                    "components": components,
                }
        if extras or aggregation_applied is not None:
            metadata = dict(case.metadata)
            if extras:
                metadata["axiom_all_outputs"] = extras
            if aggregation_applied is not None:
                metadata["axiom_result_aggregation_applied"] = aggregation_applied
            case = replace(case, metadata=metadata)
        out.append(case)
    return out


@cli.command("coverage")
@click.option(
    "--compiled-program",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--target", required=True, help="Name of the derived rule to audit.")
def coverage_check(compiled_program: Path, target: str) -> None:
    """Report eligibility-looking rules that exist in a compiled program but
    are not referenced by ``target``.

    Surfaces the compose-spec gap that bit us on CA SNAP — the spec
    only wired per-member eligibility into snap_eligible while gross-
    income, net-income, and resource-limit rules were available but
    unreferenced. Non-zero exit if any gaps are detected.
    """
    from .coverage import find_uncovered_eligibility_rules, format_coverage_warning

    uncovered = find_uncovered_eligibility_rules(compiled_program, target=target)
    if uncovered:
        click.echo(format_coverage_warning(target, uncovered))
        sys.exit(1)
    click.echo(f"Coverage OK — no eligibility-looking rules orphaned from {target}.")


@cli.command("sanity")
@click.argument(
    "fixtures_file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--left", default="axiom", type=click.Choice(["axiom", "policyengine"]))
@click.option(
    "--right", default="policyengine", type=click.Choice(["axiom", "policyengine"])
)
@click.option("--axiom-engine-binary", type=click.Path(path_type=Path, exists=True))
@click.option("--axiom-compiled-program", type=click.Path(path_type=Path, exists=True))
@click.option("--jurisdiction-fips", type=str, default=None)
def sanity_check(
    fixtures_file: Path,
    left: str,
    right: str,
    axiom_engine_binary: Path | None,
    axiom_compiled_program: Path | None,
    jurisdiction_fips: str | None,
) -> None:
    """Run a comparison's sanity fixtures and verify expected per-engine outcomes.

    Sanity fixtures are hand-built cases whose expected outcomes follow
    from public domain knowledge of the program rules. Running them
    *before* a population-scale comparison catches infrastructure bugs
    (missing relations, wrong intervals) and rule-chain gaps
    (over-permissive or over-restrictive defaults) that aggregate match
    rates can mask. Non-zero exit on any failure.
    """
    from .sanity import (
        SanityResult,
        SanitySummary,
        fixture_to_case,
        load_fixtures,
        print_summary,
    )

    concept, period, fixtures = load_fixtures(fixtures_file)
    if not fixtures:
        click.echo("No fixtures to run.", err=True)
        sys.exit(2)

    cases = [fixture_to_case(f, concept=concept, period=period) for f in fixtures]
    concept_ids = (concept,)

    left_runner = _build_runner(
        left,
        "api",
        None,
        None,
        concept_ids,
        axiom_compiled_program=axiom_compiled_program,
        axiom_engine_binary=axiom_engine_binary,
        paired_engine=right,
    )
    right_runner = _build_runner(
        right,
        "api",
        None,
        None,
        concept_ids,
        axiom_compiled_program=axiom_compiled_program,
        axiom_engine_binary=axiom_engine_binary,
        paired_engine=left,
    )

    try:
        prepared = _prepare_cases_for_engines(
            cases,
            {left, right},
            concept_ids,
            axiom_compiled_program=axiom_compiled_program,
            jurisdiction_fips=jurisdiction_fips,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    left_results = left_runner.run_cases(prepared, list(concept_ids))
    right_results = right_runner.run_cases(prepared, list(concept_ids))

    summary = SanitySummary(concept=concept, period=period)
    by_left = {r.household_id: r for r in left_results}
    by_right = {r.household_id: r for r in right_results}
    for fixture, case in zip(fixtures, prepared, strict=False):
        for engine_name, results_by_id in ((left, by_left), (right, by_right)):
            # Fixtures declare which engines they assert against; missing
            # entries mean "this fixture doesn't have a confident expected
            # value for this engine" — skip rather than guess.
            if engine_name not in fixture.expected:
                continue
            expected = bool(fixture.expected[engine_name])
            engine_result = results_by_id.get(case.case_id)
            if engine_result is None:
                summary.results.append(
                    SanityResult(
                        fixture_id=fixture.id,
                        engine=engine_name,
                        expected=expected,
                        actual=None,
                        matched=False,
                        error="no result returned",
                    )
                )
                continue
            # Engines key their output dicts differently — axiom uses bare
            # derived names (`snap_eligible`), PolicyEngine uses its
            # variable names (`is_snap_eligible`), and some emit the full
            # concept ID. Look up by the concept ID first, then by the
            # fragment after `#`, then by any non-None value.
            values = engine_result.values
            fragment = concept.rsplit("#", 1)[-1]
            actual = values.get(concept)
            if actual is None:
                actual = values.get(fragment)
            if actual is None:
                non_none = [v for v in values.values() if v is not None]
                actual = non_none[0] if len(non_none) == 1 else None
            err = "; ".join(engine_result.errors or ()) or None
            # An engine that returns None (couldn't compute) is a hard
            # failure for a sanity check — it means the engine pipeline
            # didn't produce the value the comparison depends on.
            if actual is None and err is None:
                err = (
                    "engine returned no value for the requested concept "
                    f"(values={list(values)!r})"
                )
            summary.results.append(
                SanityResult(
                    fixture_id=fixture.id,
                    engine=engine_name,
                    expected=expected,
                    actual=actual,
                    matched=(bool(actual) == expected) if err is None else False,
                    error=err,
                )
            )

    print_summary(summary)
    sys.exit(0 if summary.passed else 1)


@cli.command()
@click.argument(
    "left",
    type=click.Choice(
        ["accessnyc", "policyengine", "axiom", "taxsim", "taxcalc", "prd", "euromod"]
    ),
)
@click.argument(
    "right",
    type=click.Choice(
        ["accessnyc", "policyengine", "axiom", "taxsim", "taxcalc", "prd", "euromod"]
    ),
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
    "--report-suite",
    default=None,
    help=(
        "Suite label written into the comparison report. ECPS comparisons "
        "have no synthetic suite, so without this the report is labeled "
        "'nyc-synthetic' regardless of what it compared."
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
    "--case-shard",
    default=None,
    help=(
        "Process only shard K of N (format K/N, zero-based) of the loaded "
        "cases. Big states OOM this machine in one process; shards run "
        "sequentially in fresh processes and merge via "
        "scripts/merge_shard_reports.py."
    ),
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
        "Validation period. Defaults to 2026 for TAXSIM comparisons and "
        "2026-05 otherwise."
    ),
)
@click.option(
    "--ecps-dataset",
    type=click.Path(dir_okay=False),
    help=(
        "Override the population dataset (path, hf:// URL, or populace:// "
        "dataset-repo reference). Defaults to the certified populace-us "
        "artifact; NYC scopes keep their dedicated file until populace "
        "grows place geography."
    ),
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
    "--include-components",
    is_flag=True,
    help="Also compare component concepts declared under selected parent concepts.",
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
    "--axiom-batch-size",
    type=click.IntRange(min=1, max=20_000),
    default=5_000,
    show_default=True,
    help="Number of cases per Axiom run-compiled request.",
)
@click.option(
    "--axiom-compiled-program",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    envvar="AXIOM_COMPILED_PROGRAM",
    help=(
        "Compiled program JSON (output of `axiom-rules-engine compile`). "
        "When provided alongside --jurisdiction-fips, the harness uses the "
        "generic input projector instead of program-specific Python "
        "adapters (axiom-oracles#26)."
    ),
)
@click.option(
    "--jurisdiction-fips",
    default=None,
    help=(
        "Two-digit FIPS prefix used to filter ECPS households for this "
        "comparison (e.g. `06` for California, `08` for Colorado). When "
        "unset, the harness applies its legacy Colorado-only SNAP filter."
    ),
)
@click.option(
    "--include-case-inputs/--no-include-case-inputs",
    "include_case_inputs",
    default=None,
    help=(
        "Persist every case's raw input records and matched values in the "
        "report. Defaults by loaded-case count, which overcounts for suites "
        "whose jurisdiction filter runs inside the bridge (state tax) — pass "
        "the flag explicitly for those."
    ),
)
@click.option(
    "--comparison-batch-size",
    type=click.IntRange(min=1),
    default=5_000,
    show_default=True,
    help="Number of cases to prepare and compare per report-accumulation batch.",
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
    report_suite: str | None,
    population: str,
    sample_size: int,
    period: str | None,
    ecps_dataset: str | None,
    concepts: tuple[str, ...],
    categories: tuple[str, ...],
    include_components: bool,
    locales: tuple[str, ...],
    accessnyc_mode: str,
    accessnyc_rules_dir: Path | None,
    accessnyc_python_path: Path | None,
    axiom_program: Path | None,
    axiom_engine_binary: Path | None,
    axiom_entity_id: str,
    axiom_batch_size: int,
    axiom_compiled_program: Path | None,
    jurisdiction_fips: str | None,
    include_case_inputs: bool | None,
    case_shard: str | None,
    comparison_batch_size: int,
    output_path: Path | None,
    json_output: bool,
) -> None:
    """Compare two executable program systems over a validation population."""

    if left == right:
        raise click.ClickException("Choose two different systems to compare.")

    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        period = _resolve_period(period, left, right)
        comparison_scope = comparison_scope_for_targets(left, right)
        suite_name = _resolve_suite_name(suite, left, right)
        _echo_resolved_axiom_composition(
            report_suite or suite_name, {left, right}, axiom_program
        )
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
        if jurisdiction_fips and _wants_snap(concepts):
            cases = [
                case
                for case in cases
                if _household_in_jurisdiction(case, jurisdiction_fips)
            ]
        if not cases:
            raise click.ClickException(
                "No cases found for the resolved target scope and population."
            )
        case_locales = set(locales) if locales else _case_locales(cases)
        requested_concepts = set(concepts) or _case_output_concepts(cases) or None
        mappings = comparable_mappings(
            left,
            right,
            locales=case_locales,
            scope=comparison_scope,
            concepts=requested_concepts,
            categories=set(categories) or None,
            include_components=include_components,
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
        suite_declares_outputs = any(case.outputs for case in cases)
        if concepts or categories or include_components or not suite_declares_outputs:
            # An explicit CLI selection intentionally overrides the suite's
            # declared surfaces for every case. Suites with no declarations
            # retain the historical all-comparable-concepts fallback.
            cases = [replace(case, outputs=concept_ids) for case in cases]
        else:
            # Registered suites may expose different diagnostic surfaces on
            # different cases (for example a negative-income semantics probe
            # alongside final-liability cases). Keep that declaration while
            # trimming any output that is not comparable for this engine pair.
            selected = set(concept_ids)
            cases = [
                replace(
                    case,
                    outputs=tuple(
                        output for output in case.outputs if output in selected
                    ),
                )
                for case in cases
            ]

        if case_shard:
            try:
                shard_index, shard_total = (
                    int(part) for part in case_shard.split("/", 1)
                )
            except ValueError as exc:
                raise click.ClickException(
                    f"--case-shard must be K/N, got {case_shard!r}"
                ) from exc
            if not (0 <= shard_index < shard_total):
                raise click.ClickException(
                    f"--case-shard index out of range: {case_shard}"
                )
            cases = [
                case
                for position, case in enumerate(cases)
                if position % shard_total == shard_index
            ]
            click.echo(
                f"Shard {shard_index + 1}/{shard_total}: {len(cases)} cases",
                err=True,
            )

        # Resolved once: small suites (or an explicit flag) persist full
        # evidence — raw input records AND the axiom engine's complete
        # output surface per case.
        full_evidence = (
            include_case_inputs
            if include_case_inputs is not None
            else len(cases) <= FULL_CASE_INPUT_LIMIT
        )

        left_runner = _build_runner(
            left,
            accessnyc_mode,
            accessnyc_rules_dir,
            accessnyc_python_path,
            concept_ids,
            axiom_program=axiom_program,
            axiom_compiled_program=axiom_compiled_program,
            axiom_engine_binary=axiom_engine_binary,
            axiom_entity_id=axiom_entity_id,
            axiom_batch_size=axiom_batch_size,
            axiom_record_all_outputs=full_evidence,
            paired_engine=right,
        )
        right_runner = _build_runner(
            right,
            accessnyc_mode,
            accessnyc_rules_dir,
            accessnyc_python_path,
            concept_ids,
            axiom_program=axiom_program,
            axiom_compiled_program=axiom_compiled_program,
            axiom_engine_binary=axiom_engine_binary,
            axiom_entity_id=axiom_entity_id,
            axiom_batch_size=axiom_batch_size,
            axiom_record_all_outputs=full_evidence,
            paired_engine=left,
        )

        comparator = Comparator(mappings)
        stream_case_rows = output_path is not None or not json_output
        with tempfile.TemporaryDirectory(prefix="axiom-oracles-report-") as report_dir:
            accumulator = ComparisonReportAccumulator(
                suite_name=report_suite or suite_name,
                population=population,
                locales=case_locales,
                scope=comparison_scope,
                mappings=mappings,
                case_rows_path=Path(report_dir) / "cases.jsonl"
                if stream_case_rows
                else None,
                # Small suites persist full evidence: raw input records and
                # matched values, so a report alone reproduces the run. The
                # loaded-case count overstates suites whose jurisdiction
                # filter runs inside the bridge (state tax slices), so an
                # explicit --include-case-inputs wins over the heuristic.
                include_inputs=full_evidence,
            )
            total_batches = (
                len(cases) + comparison_batch_size - 1
            ) // comparison_batch_size
            for batch_index, case_batch in enumerate(
                _batched(cases, comparison_batch_size),
                start=1,
            ):
                click.echo(
                    f"Comparing batch {batch_index}/{total_batches} "
                    f"({len(case_batch)} case(s))...",
                    err=True,
                )
                try:
                    prepared_cases = _prepare_cases_for_engines(
                        case_batch,
                        {left, right},
                        concept_ids,
                        axiom_program=axiom_program,
                        axiom_compiled_program=axiom_compiled_program,
                        jurisdiction_fips=jurisdiction_fips,
                    )
                except RuntimeError as exc:
                    raise click.ClickException(str(exc)) from exc
                if not prepared_cases:
                    continue
                try:
                    (
                        accumulator_cases,
                        left_results,
                        right_results,
                    ) = _run_comparison_batch(
                        prepared_cases,
                        left=left,
                        right=right,
                        left_runner=left_runner,
                        right_runner=right_runner,
                        concept_ids=concept_ids,
                    )
                except RuntimeError as exc:
                    raise click.ClickException(str(exc)) from exc

                if full_evidence and "axiom" in (left, right):
                    accumulator_cases = _attach_axiom_outputs(
                        accumulator_cases,
                        left_results if left == "axiom" else right_results,
                        concept_ids,
                    )
                accumulator.add_batch(
                    accumulator_cases,
                    _filter_comparisons_for_case_outputs(
                        accumulator_cases,
                        comparator.compare(left_results, right_results),
                    ),
                )

            if not accumulator.case_count:
                raise click.ClickException(
                    "No cases remain after engine-specific preparation filters."
                )

            if output_path:
                accumulator.write_json(output_path)

            if json_output:
                report = accumulator.to_dict()
                click.echo(json.dumps(report, indent=2, sort_keys=True))
                return

            _echo_comparison_report(accumulator.to_dict(include_cases=False))
    finally:
        if gc_was_enabled:
            gc.enable()


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


def _case_output_concepts(cases: list[Case]) -> set[str]:
    return {
        output
        for case in cases
        for output in case.outputs
        if isinstance(output, str) and output
    }


def _filter_comparisons_for_case_outputs(
    cases: list[Case],
    comparisons: list[HouseholdComparison],
) -> list[HouseholdComparison]:
    """Keep only the concepts each registered case declares.

    Runners still receive the union of suite outputs so shared engine/model
    setup happens once. This final projection prevents that union from turning
    a case-specific diagnostic into unintended missing/zero comparisons on
    every other case. Explicit ``--concept``/``--category`` selections replace
    ``Case.outputs`` earlier and therefore retain their historical all-case
    behavior.
    """

    outputs_by_id = {case.case_id: set(case.outputs) for case in cases}
    filtered: list[HouseholdComparison] = []
    for comparison in comparisons:
        declared = outputs_by_id.get(comparison.household_id)
        if declared is None:
            filtered.append(comparison)
            continue
        filtered.append(
            replace(
                comparison,
                comparisons=[
                    item
                    for item in comparison.comparisons
                    if item.variable in declared
                ],
            )
        )
    return filtered


def _run_comparison_batch(
    cases: list[Case],
    *,
    left: str,
    right: str,
    left_runner: EngineAdapter,
    right_runner: EngineAdapter,
    concept_ids: tuple[str, ...],
) -> tuple[list[Case], list, list]:
    variables = list(concept_ids)
    bridge_outputs = _euromod_to_axiom_bridge_outputs(cases)
    euromod_variables = list(dict.fromkeys([*variables, *bridge_outputs]))

    if bridge_outputs and left == "euromod" and right == "axiom":
        left_results = left_runner.run_cases(cases, euromod_variables)
        bridged_cases = _apply_euromod_to_axiom_input_bridge(cases, left_results)
        right_results = right_runner.run_cases(bridged_cases, variables)
        return bridged_cases, left_results, right_results

    if bridge_outputs and left == "axiom" and right == "euromod":
        right_results = right_runner.run_cases(cases, euromod_variables)
        bridged_cases = _apply_euromod_to_axiom_input_bridge(cases, right_results)
        left_results = left_runner.run_cases(bridged_cases, variables)
        return bridged_cases, left_results, right_results

    return (
        cases,
        left_runner.run_cases(cases, variables),
        right_runner.run_cases(cases, variables),
    )


def _euromod_to_axiom_bridge_outputs(cases: list[Case]) -> list[str]:
    outputs: list[str] = []
    for case in cases:
        bridge = case.metadata.get(EUROMOD_TO_AXIOM_INPUT_BRIDGE_METADATA_KEY)
        if not isinstance(bridge, dict):
            continue
        outputs.extend(str(output) for output in bridge if output)
    return list(dict.fromkeys(outputs))


def _apply_euromod_to_axiom_input_bridge(
    cases: list[Case],
    euromod_results: list,
) -> list[Case]:
    results_by_id = {result.household_id: result for result in euromod_results}
    bridged_cases: list[Case] = []
    for case in cases:
        bridge = case.metadata.get(EUROMOD_TO_AXIOM_INPUT_BRIDGE_METADATA_KEY)
        result = results_by_id.get(case.case_id)
        if not isinstance(bridge, dict) or result is None:
            bridged_cases.append(case)
            continue

        inputs = dict(case.metadata.get("axiom_inputs", {}))
        input_records = [
            dict(record) for record in case.metadata.get("axiom_input_records", [])
        ]
        inputs_changed = False
        input_records_changed = False
        applied: dict[str, float | int | bool | str | None] = {}
        for euromod_output, axiom_inputs in bridge.items():
            value = result.values.get(str(euromod_output))
            if value is None:
                continue
            value = _transform_bridged_value(value, axiom_inputs)
            input_names = _bridged_axiom_inputs(axiom_inputs)
            for input_name in input_names:
                inputs[str(input_name)] = value
                applied[str(input_name)] = value
                inputs_changed = True
            for record_spec in _bridged_axiom_input_records(axiom_inputs):
                input_records = _upsert_bridged_axiom_input_record(
                    input_records,
                    record_spec,
                    value,
                )
                applied[
                    f"{record_spec['entity']}[{record_spec['entity_id']}]::"
                    f"{record_spec['name']}"
                ] = value
                input_records_changed = True

        if not applied:
            bridged_cases.append(case)
            continue

        metadata = dict(case.metadata)
        if inputs_changed:
            metadata["axiom_inputs"] = inputs
        if input_records_changed:
            metadata["axiom_input_records"] = input_records
        metadata["euromod_to_axiom_input_bridge_applied"] = applied
        bridged_cases.append(replace(case, metadata=metadata))
    return bridged_cases


def _bridged_axiom_inputs(spec) -> tuple[str, ...]:
    if isinstance(spec, str):
        return (spec,)
    if isinstance(spec, dict):
        inputs = spec.get("inputs") or spec.get("input")
        if isinstance(inputs, str):
            return (inputs,)
        if inputs is None:
            return ()
        return tuple(str(input_name) for input_name in inputs)
    return tuple(str(input_name) for input_name in spec)


def _bridged_axiom_input_records(spec) -> tuple[dict, ...]:
    if not isinstance(spec, dict):
        return ()
    raw_records = spec.get("records") or spec.get("input_records")
    if raw_records is None:
        return ()
    if not isinstance(raw_records, list | tuple):
        raise RuntimeError(
            "EUROMOD-to-Axiom bridge records must be a list of mappings."
        )
    records = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            raise RuntimeError("EUROMOD-to-Axiom bridge records must be mappings.")
        missing = {"name", "entity", "entity_id"} - set(raw_record)
        if missing:
            raise RuntimeError(
                f"EUROMOD-to-Axiom bridge record is missing {sorted(missing)}."
            )
        record = {
            "name": str(raw_record["name"]),
            "entity": str(raw_record["entity"]),
            "entity_id": str(raw_record["entity_id"]),
        }
        if "interval" in raw_record:
            if not isinstance(raw_record["interval"], dict):
                raise RuntimeError(
                    "EUROMOD-to-Axiom bridge record interval must be a mapping."
                )
            record["interval"] = dict(raw_record["interval"])
        records.append(record)
    return tuple(records)


def _upsert_bridged_axiom_input_record(
    records: list[dict],
    record_spec: dict,
    value,
) -> list[dict]:
    key = _bridged_axiom_input_record_key(record_spec)
    updated = []
    matched = False
    for record in records:
        record_key = _bridged_axiom_input_record_key(record)
        if record_key == key:
            updated.append({**record, "value": value})
            matched = True
        else:
            updated.append(record)
    if not matched:
        updated.append({**record_spec, "value": value})
    return updated


def _bridged_axiom_input_record_key(record: dict) -> tuple[str, str, str, str]:
    interval = record.get("interval", {})
    if not isinstance(interval, dict):
        raise RuntimeError("Axiom input record interval must be a mapping.")
    return (
        str(record.get("name", "")),
        str(record.get("entity", "")),
        str(record.get("entity_id", "")),
        json.dumps(interval, sort_keys=True, separators=(",", ":")),
    )


def _transform_bridged_value(value, spec):
    if not isinstance(spec, dict):
        return value
    transformed = value
    if "divide_by" in spec:
        transformed = transformed / float(spec["divide_by"])
    if "multiply_by" in spec:
        transformed = transformed * float(spec["multiply_by"])
    if "add" in spec:
        transformed = transformed + float(spec["add"])
    return transformed


def _batched(cases: list[Case], batch_size: int):
    for start in range(0, len(cases), batch_size):
        yield cases[start : start + batch_size]


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
        return load_populace_us_cases(
            scope=scope,
            period=period,
            sample_size=sample_size or None,
            dataset=ecps_dataset,
            case_unit=_populace_us_case_unit(categories, concepts),
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


def _populace_us_case_unit(
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
    axiom_compiled_program: Path | None = None,
    jurisdiction_fips: str | None = None,
) -> list[Case]:
    prepared = cases
    if "taxsim" in engines:
        prepared = attach_taxsim_inputs(prepared)
    if "taxcalc" in engines:
        prepared = attach_taxcalc_inputs(prepared)
    if "axiom" in engines and axiom_program is None and _wants_tax(concept_ids):
        if _needs_axiom_tax_itemization_choice(concept_ids):
            # The generated state-income-tax bridge currently implements
            # Colorado. Federal taxable-income and liability comparisons also
            # need the encoded state tax for SALT/itemization resolution.
            prepared = [case for case in prepared if _is_co_household(case)]
        prepared = attach_axiom_tax_inputs(prepared)
        if engines & {"policyengine", "taxsim"} and _needs_axiom_tax_itemization_choice(
            concept_ids
        ):
            prepared = attach_axiom_tax_itemization_choice(prepared)
            if set(concept_ids) == {Concepts.STATE_INCOME_TAX}:
                prepared = [
                    _select_axiom_state_income_tax_candidate(case) for case in prepared
                ]
    if "axiom" in engines and _wants_snap(concept_ids):
        # Two paths:
        # - Generic: a compiled program + jurisdiction FIPS were provided.
        #   Drives projection from the program artifact, filters by the
        #   requested state. Same code for any (jurisdiction, SNAP) pair.
        # - Legacy: Colorado-specific Python projection and FIPS filter.
        #   Preserved until the CO mapping is extracted as data
        #   (axiom-oracles#26 follow-up).
        if axiom_compiled_program is not None and jurisdiction_fips:
            from .adapters.axiom.generic_inputs import attach_generic_inputs

            prepared = [
                case
                for case in prepared
                if _household_in_jurisdiction(case, jurisdiction_fips)
            ]
            prepared = attach_generic_inputs(
                prepared,
                compiled_program_path=axiom_compiled_program,
            )
        else:
            prepared = [case for case in prepared if _is_co_household(case)]
            prepared = attach_axiom_snap_co_inputs(prepared)
    elif (
        "axiom" in engines
        and axiom_compiled_program is not None
        and not _wants_tax(concept_ids)
    ):
        # Generic compiled-program path for non-SNAP, non-tax programs
        # (e.g. the us/ssi composition): project inputs from the program
        # artifact via the data-driven ECPS mapping, optionally filtered
        # to a jurisdiction.
        from .adapters.axiom.generic_inputs import attach_generic_inputs

        if jurisdiction_fips:
            prepared = [
                case
                for case in prepared
                if _household_in_jurisdiction(case, jurisdiction_fips)
            ]
        prepared = attach_generic_inputs(
            prepared,
            compiled_program_path=axiom_compiled_program,
        )
    return prepared


def _household_in_jurisdiction(case: Case, fips_prefix: str) -> bool:
    """Generic FIPS-prefix filter (replaces hardcoded _is_co_household)."""
    scope = case.scope
    if scope is None or not scope.geoid:
        return False
    return str(scope.geoid).startswith(fips_prefix)


def _is_co_household(case: Case) -> bool:
    """Legacy Colorado-only filter; kept for the CO-specific SNAP path."""
    return _household_in_jurisdiction(case, "08")


def _select_axiom_state_income_tax_candidate(case: Case) -> Case:
    metadata = dict(case.metadata)
    metadata["axiom_result_selection"] = {
        "strategy": "min",
        "output": "us:tax/oracle-bridge#state_income_tax",
    }
    return replace(case, metadata=metadata)


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
    axiom_compiled_program: Path | None = None,
    axiom_engine_binary: Path | None = None,
    axiom_entity_id: str = "tax_unit",
    axiom_batch_size: int = 5_000,
    axiom_record_all_outputs: bool = False,
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
        return PolicyEngineRunner(batch_size=100 if _wants_snap(concept_ids) else 5_000)
    if engine == "axiom":
        # SNAP runs through a precompiled artifact (avoids re-compiling the
        # CO RuleSpec module on every case and the engine's `kind: reiteration`
        # support requirement). Tax concepts keep compiling fresh from the
        # generated oracle bridge imports.
        # When the caller passes --axiom-compiled-program (e.g. CA SNAP via
        # axiom-programs), use that artifact instead of the bundled CO one.
        wants_snap = _wants_snap(concept_ids) and axiom_program is None
        if axiom_compiled_program is not None:
            compiled_artifact = axiom_compiled_program
        else:
            compiled_artifact = (
                US_SNAP_CO_COMPILED_ARTIFACT_PATH if wants_snap else None
            )
        program_imports = ()
        generated_program_target = None
        program_rules = ()
        # An explicitly provided compiled artifact fully defines the program
        # (compose already resolved its imports); deriving imports from the
        # concept ids here would flip prune_unsupported_inputs and strip the
        # generic ECPS input records the artifact needs.
        if axiom_program is None and not wants_snap and axiom_compiled_program is None:
            if _wants_tax(concept_ids):
                program_imports = _tax_oracle_imports_for_concepts(concept_ids)
                generated_program_target = US_TAX_ORACLE_BRIDGE_TARGET
                program_rules = _tax_oracle_program_rules_for_concepts(concept_ids)
            else:
                program_imports = _rulespec_imports_for_concepts(concept_ids)
                generated_program_target = (
                    program_imports[0] if program_imports else None
                )
        return AxiomRulesRunner(
            program_path=axiom_program,
            compiled_artifact_path=compiled_artifact,
            binary_path=axiom_engine_binary,
            default_entity_id="household" if wants_snap else axiom_entity_id,
            default_entity="Household" if wants_snap else "TaxUnit",
            program_imports=program_imports,
            program_rules=program_rules,
            generated_program_target=generated_program_target,
            prune_unsupported_inputs=bool(program_imports),
            batch_size=axiom_batch_size,
            record_all_outputs=axiom_record_all_outputs,
        )
    if engine == "taxsim":
        return TaxsimPackageRunner()
    if engine == "taxcalc":
        return TaxCalcPackageRunner()
    if engine == "prd":
        return PrdPackageRunner()
    if engine == "euromod":
        model_root = os.environ.get("EUROMOD_MODEL_ROOT")
        if not model_root:
            raise click.ClickException(
                "The euromod engine needs EUROMOD_MODEL_ROOT (a UKMOD or "
                "EUROMOD model directory), plus EUROMOD_COUNTRY and "
                "EUROMOD_SYSTEM; EUROMOD_PYTHON names the execution "
                "environment interpreter."
            )
        return EuromodPlatformRunner(
            model_root=model_root,
            country=os.environ.get("EUROMOD_COUNTRY", "UK"),
            system=os.environ.get("EUROMOD_SYSTEM", "UK_2025"),
            dataset=os.environ.get("EUROMOD_DATASET", "training_data"),
            template_dataset=os.environ.get("EUROMOD_TEMPLATE_DATASET") or None,
            country_code=int(os.environ.get("EUROMOD_COUNTRY_CODE", "15")),
            switches=_parse_euromod_switches(
                os.environ.get("EUROMOD_SWITCHES"),
                "EUROMOD_SWITCHES",
            ),
            policy_switch_overrides=_parse_euromod_switches(
                os.environ.get("EUROMOD_POLICY_SWITCHES"),
                "EUROMOD_POLICY_SWITCHES",
            ),
            constant_overrides=_parse_euromod_constant_overrides(
                os.environ.get("EUROMOD_CONSTANT_OVERRIDES"),
            ),
            extra_columns=_parse_euromod_extra_columns(
                os.environ.get("EUROMOD_EXTRA_COLUMNS"),
            ),
        )
    raise click.ClickException(f"Engine '{engine}' is not implemented yet.")


def _parse_euromod_constant_overrides(
    raw: str | None,
) -> tuple[tuple[str, str, str], ...]:
    """Parse ``$name=value`` pairs, comma-separated; ``$name@group=value``
    targets a grouped constant (e.g. an uprating factor's year group)."""
    if not raw:
        return ()
    overrides: list[tuple[str, str, str]] = []
    for entry in raw.split(","):
        if not entry.strip():
            continue
        if "=" not in entry:
            raise click.ClickException(
                "EUROMOD_CONSTANT_OVERRIDES entries must be name=value pairs "
                "(name@group=value for grouped constants)."
            )
        name, value = entry.split("=", 1)
        name = name.strip()
        group = ""
        if "@" in name:
            name, group = name.split("@", 1)
        if not name:
            raise click.ClickException(
                "EUROMOD_CONSTANT_OVERRIDES entries need a constant name."
            )
        overrides.append((name, group.strip(), value.strip()))
    return tuple(overrides)


def _parse_euromod_extra_columns(raw: str | None) -> tuple[str, ...]:
    """Parse a comma-separated list of input columns absent from the template."""

    if not raw:
        return ()
    return tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))


def _parse_euromod_switches(
    raw: str | None,
    env_var: str = "EUROMOD_SWITCHES",
) -> tuple[tuple[str, bool], ...]:
    if not raw:
        return ()
    switches: list[tuple[str, bool]] = []
    for entry in raw.split(","):
        if not entry.strip():
            continue
        if "=" not in entry:
            raise click.ClickException(f"{env_var} entries must be name=on/off pairs.")
        name, value = entry.split("=", 1)
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            enabled = True
        elif normalized in {"0", "false", "no", "off"}:
            enabled = False
        else:
            raise click.ClickException(
                f"{env_var} values must be booleans or on/off strings."
            )
        switches.append((name.strip(), enabled))
    return tuple(switches)


def _tax_oracle_imports_for_concepts(concept_ids: tuple[str, ...]) -> tuple[str, ...]:
    del concept_ids
    # us:statutes/26/1411 (NIIT) is excluded from every composition until the
    # upstream duplicate-rule encoding is fixed: 1411 imports
    # us:statutes/26/911/a/1#foreign_earned_income_excluded_from_gross_income
    # (the child fragment) while 26/25B and 26/32 transitively reach
    # us:statutes/26/151 -> us:statutes/26/911/a, and BOTH 911/a and 911/a/1
    # define that rule name, so any closure containing 1411 plus either module
    # fails `axiom-rules-engine compile` with "duplicate derived rule". The
    # parent/fragment double definition is an axiom-encode artifact (the
    # parent should import the fragment's rule, not redefine it). Consequence
    # while excluded: the composed federal liability omits NIIT, and TAXSIM's
    # fiitax includes it (verified against the pinned 2.30.0 binary: fiitax =
    # v28 - credits + niit), so units with investment income above the 1411
    # thresholds carry a residual equal to TAXSIM's own `niit` output column.
    return tuple(
        import_ref
        for import_ref in US_TAX_ORACLE_IMPORTS
        if import_ref != "us:statutes/26/1411"
    )


def _tax_oracle_program_rules_for_concepts(
    concept_ids: tuple[str, ...],
) -> tuple[dict, ...]:
    del concept_ids
    # The bridge's generated `self_employment_income` shim
    # (max(0, net_earnings_from_self_employment)) predates the encoded
    # us:statutes/26/1402/b, which now defines the statutory rule of the same
    # name (with the $400 inclusion threshold and nonresident-alien
    # exception) and is pulled in transitively by the 1401/164(f) imports —
    # composing both fails `axiom-rules-engine compile` with "duplicate
    # derived rule". Bridge references resolve to the encoded 1402(b) rule,
    # which is the faithful one; the shim is dropped for every concept set.
    return tuple(
        rule
        for rule in US_TAX_ORACLE_PROGRAM_RULES
        if rule.get("name") != "self_employment_income"
    )


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
    if not summary["mismatch_count"]:
        return
    click.echo("Mismatches:")
    if not report.get("cases"):
        mismatches = report.get("mismatches", [])
        for mismatch in mismatches[:MAX_CONSOLE_MISMATCHES]:
            click.echo(
                f"{mismatch['case_id']}: {mismatch['description']} "
                f"{mismatch['left']} != {mismatch['right']}"
            )
        _echo_omitted_mismatches(
            summary["mismatch_count"],
            min(len(mismatches), MAX_CONSOLE_MISMATCHES),
        )
        return
    printed = 0
    for case in report["cases"]:
        if not case["mismatches"]:
            continue
        case_printed = False
        for mismatch in case["mismatches"]:
            if printed >= MAX_CONSOLE_MISMATCHES:
                _echo_omitted_mismatches(summary["mismatch_count"], printed)
                return
            if not case_printed:
                click.echo(f"{case['case_id']}: {case['match_rate']:.1f}% match")
                case_printed = True
            click.echo(
                f"  {mismatch['description']}: "
                f"{mismatch['left']} != {mismatch['right']}"
            )
            printed += 1


def _echo_omitted_mismatches(total_count: int, printed_count: int) -> None:
    omitted_count = total_count - printed_count
    if omitted_count <= 0:
        return
    click.echo(
        f"... {omitted_count} additional mismatches omitted; "
        "use --output for the full JSON report."
    )


if __name__ == "__main__":
    cli()
