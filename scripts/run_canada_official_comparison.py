#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from axiom_oracles.adapters.axiom import AxiomRulesRunner
from axiom_oracles.adapters.canada_official import (
    ChildFamilyBenefitsRunner,
    ORACLES,
    PdocRunner,
)
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.core.geography import normalize_scope
from axiom_oracles.suites.ca_cra_family_benefits import (
    CCB,
    CHILD_DISABILITY_BENEFIT,
    FAMILY_MODULE,
    GROCERIES_AND_ESSENTIALS_BENEFIT,
    ca_cra_family_benefit_cases,
)
from axiom_oracles.suites.ca_cra_pdoc import (
    CPP,
    EI,
    INCOME_TAX,
    PDOC_MODULE,
    PDOC_OUTPUTS,
    ca_cra_pdoc_cases,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run reproducible Canadian official-calculator comparisons."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory", help="Print the official oracle registry.")
    family = subparsers.add_parser(
        "family-benefits",
        help="Compare CRA's child/family calculator with RuleSpec Canada.",
    )
    family.add_argument("--rulespec-root", required=True, type=Path)
    family.add_argument("--axiom-binary", required=True, type=Path)
    family.add_argument("--output", required=True, type=Path)
    pdoc = subparsers.add_parser(
        "pdoc",
        help="Compare CRA's payroll calculator with the Ontario RuleSpec pipeline.",
    )
    pdoc.add_argument("--rulespec-root", required=True, type=Path)
    pdoc.add_argument("--axiom-binary", required=True, type=Path)
    pdoc.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "inventory":
        print(json.dumps([item.__dict__ for item in ORACLES], indent=2))
        return
    if args.command == "family-benefits":
        run_family_benefits(args.rulespec_root, args.axiom_binary, args.output)
        return
    run_pdoc(args.rulespec_root, args.axiom_binary, args.output)


def run_family_benefits(
    rulespec_root: Path,
    axiom_binary: Path,
    output: Path,
) -> dict:
    cases = ca_cra_family_benefit_cases()
    concepts = [CCB, CHILD_DISABILITY_BENEFIT, GROCERIES_AND_ESSENTIALS_BENEFIT]
    mappings = [
        _mapping(CCB, "Canada child benefit annual amount", tolerance=0.12),
        _mapping(
            CHILD_DISABILITY_BENEFIT,
            "Child disability benefit annual amount",
            tolerance=0.12,
        ),
        _mapping(
            GROCERIES_AND_ESSENTIALS_BENEFIT,
            "Canada Groceries and Essentials Benefit annual amount",
            tolerance=0.04,
        ),
    ]
    official_results = ChildFamilyBenefitsRunner().run_cases(cases, concepts)
    axiom_results = _axiom_runner(
        rulespec_root,
        axiom_binary,
        module=FAMILY_MODULE,
        entity="Family",
        entity_id="family",
    ).run_cases(cases, concepts)
    comparisons = Comparator(mappings).compare(official_results, axiom_results)
    report = build_comparison_report(
        suite_name="ca-cra-family-benefits",
        population="synthetic",
        locales={"CA-ON"},
        scope=normalize_scope({"type": "country", "geoid": "CA"}),
        cases=cases,
        mappings=mappings,
        comparisons=comparisons,
    )
    report["official_oracle"] = {
        "id": "cra-child-family",
        "mode": "live_http_session",
        "artifacts_by_case": {
            result.household_id: result.raw.get("artifacts", [])
            for result in official_results
            if isinstance(result.raw, dict)
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def run_pdoc(
    rulespec_root: Path,
    axiom_binary: Path,
    output: Path,
) -> dict:
    cases = ca_cra_pdoc_cases()
    concepts = list(PDOC_OUTPUTS)
    mappings = [
        _pdoc_mapping(CPP, "CPP employee contribution"),
        _pdoc_mapping(EI, "EI employee premium"),
        _pdoc_mapping(INCOME_TAX, "Combined income-tax deduction"),
    ]
    official_results = PdocRunner().run_cases(cases, concepts)
    axiom_results = _axiom_runner(
        rulespec_root,
        axiom_binary,
        module=PDOC_MODULE,
        entity="Person",
        entity_id="person",
    ).run_cases(cases, concepts)
    comparisons = Comparator(mappings).compare(official_results, axiom_results)
    report = build_comparison_report(
        suite_name="ca-cra-pdoc",
        population="synthetic",
        locales={"CA-ON"},
        scope=normalize_scope({"type": "country", "geoid": "CA"}),
        cases=cases,
        mappings=mappings,
        comparisons=comparisons,
    )
    report["official_oracle"] = {
        "id": "cra-pdoc",
        "mode": "live_public_json_api",
        "scope": "Ontario regular salary, default TD1 claims, zero YTD",
        "artifacts_by_case": {
            result.household_id: result.raw.get("artifacts", [])
            for result in official_results
            if isinstance(result.raw, dict)
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _mapping(concept: str, description: str, *, tolerance: float) -> ProgramMapping:
    return ProgramMapping(
        standard=concept,
        description=description,
        category="benefit",
        comparison="amount",
        tolerance=tolerance,
        relative_tolerance=0,
        locales=("CA",),
        scope={"type": "country", "geoid": "CA"},
        targets={"canada-child-family": concept, "axiom": concept},
    )


def _axiom_runner(
    rulespec_root: Path,
    axiom_binary: Path,
    *,
    module: str,
    entity: str,
    entity_id: str,
) -> AxiomRulesRunner:
    return AxiomRulesRunner(
        binary_path=axiom_binary,
        default_entity=entity,
        default_entity_id=entity_id,
        program_imports=(module,),
        rulespec_repo_roots=(rulespec_root,),
        prune_unsupported_inputs=True,
    )


def _pdoc_mapping(concept: str, description: str) -> ProgramMapping:
    return ProgramMapping(
        standard=concept,
        description=description,
        category="payroll",
        comparison="amount",
        tolerance=0.01,
        relative_tolerance=0,
        locales=("CA-ON",),
        scope={"type": "country", "geoid": "CA"},
        targets={"canada-pdoc": concept, "axiom": concept},
    )


if __name__ == "__main__":
    main()
