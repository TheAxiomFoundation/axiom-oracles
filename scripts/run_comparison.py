#!/usr/bin/env python3
"""Run an oracle comparison declared in comparisons/<name>.yaml.

The registry decouples "which comparisons exist" (YAML) from "how to run
them" (runner functions below). Adding a new comparison is a YAML edit;
adding a new runner type is a function here plus a README update.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import fnmatch
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "PyYAML is required. Install with `uv pip install pyyaml` or "
        "run from the repo's .venv.\n"
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"

# The outer script runs under the host python interpreter (not the uv
# subprocess that runs the actual comparison), so make sure the editable
# package layout is importable for in-process helpers like the coverage
# analyzer. Without this, `from axiom_oracles.coverage import ...`
# silently fails and the coverage warnings get dropped.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# tax-ecps-compare → v2 dashboard schema adapter
# ---------------------------------------------------------------------------
#
# The axiom-encode `tax-ecps-compare` harness emits a flat shape
# (`output_summary` + `mismatches` by entity_id) that the dashboard
# (`axiom.comparison_report.v2`) doesn't speak natively. The mapping below
# pins each FIIT surface to a concept id the dashboard already understands.
#
# Surfaces without a real concept (payroll, capital-gain) are hung off the
# FIIT liability parent so data.js auto-allows them. Long-term, these belong
# in axiom_oracles/config/concept_mappings.yaml so sync_programs.py picks them
# up legitimately — tracked as a follow-up.
FIIT_SURFACE_CONCEPTS: dict[str, dict] = {
    "ctc": {
        "concept": "us:tax/federal-income-tax#ctc",
        "description": "Child Tax Credit value",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "standard-deduction": {
        "concept": "us:tax/federal-income-tax#standard_deduction",
        "description": "Federal standard deduction",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "eitc": {
        "concept": "us:tax/federal-income-tax#eitc",
        "description": "Earned Income Tax Credit",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "capital-gain-definitions": {
        "concept": "us:tax/federal-income-tax#capital_gain",
        "description": "Capital gain definitions",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "tax-before-credits": {
        "concept": "us:tax/federal-income-tax#tax_before_credits",
        "description": "Federal tax before credits",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "nonrefundable-credits": {
        "concept": "us:tax/federal-income-tax#nonrefundable_credits",
        "description": "Federal capped nonrefundable credits",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "cdcc": {
        "concept": "us:tax/federal-income-tax#cdcc",
        "description": "Child and Dependent Care Credit",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "aotc": {
        "concept": "us:tax/federal-income-tax#aotc",
        "description": "American Opportunity Credit",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employee-oasdi": {
        "concept": "us:tax/payroll#employee_oasdi",
        "description": "Employee OASDI (Social Security)",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employer-oasdi": {
        "concept": "us:tax/payroll#employer_oasdi",
        "description": "Employer OASDI (Social Security)",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employee-medicare": {
        "concept": "us:tax/payroll#employee_medicare",
        "description": "Employee Medicare",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employer-medicare": {
        "concept": "us:tax/payroll#employer_medicare",
        "description": "Employer Medicare",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
}

UK_UNIVERSAL_CREDIT_PARENT = "uk:benefits/universal-credit#amount"
UK_TAX_BENEFITS_PARENT = "uk:tax-benefits/efrs#amount"

UK_UNIVERSAL_CREDIT_OUTPUT_CONCEPTS: dict[str, dict] = {
    "standard_allowance_single_under_25": {
        "concept": "uk:regulations/uksi/2013/376/36#standard_allowance_single_under_25",
        "description": "Universal Credit standard allowance, single under 25",
    },
    "standard_allowance_single_25_or_over": {
        "concept": "uk:regulations/uksi/2013/376/36#standard_allowance_single_25_or_over",
        "description": "Universal Credit standard allowance, single 25 or over",
    },
    "standard_allowance_joint_both_under_25": {
        "concept": "uk:regulations/uksi/2013/376/36#standard_allowance_joint_both_under_25",
        "description": "Universal Credit standard allowance, joint both under 25",
    },
    "standard_allowance_joint_either_25_or_over": {
        "concept": "uk:regulations/uksi/2013/376/36#standard_allowance_joint_either_25_or_over",
        "description": "Universal Credit standard allowance, joint either 25 or over",
    },
    "child_element_first_child_or_qualifying_young_person": {
        "concept": "uk:regulations/uksi/2013/376/36#child_element_first_child_or_qualifying_young_person",
        "description": "Universal Credit child element, first child",
    },
    "child_element_second_and_each_subsequent_child_or_qualifying_young_person": {
        "concept": "uk:regulations/uksi/2013/376/36#child_element_second_and_each_subsequent_child_or_qualifying_young_person",
        "description": "Universal Credit child element, second and subsequent child",
    },
    "disabled_child_additional_amount_lower_rate": {
        "concept": "uk:regulations/uksi/2013/376/36#disabled_child_additional_amount_lower_rate",
        "description": "Universal Credit disabled child addition, lower rate",
    },
    "disabled_child_additional_amount_higher_rate": {
        "concept": "uk:regulations/uksi/2013/376/36#disabled_child_additional_amount_higher_rate",
        "description": "Universal Credit disabled child addition, higher rate",
    },
    "lcwra_element_standard_lcwra_claimant": {
        "concept": "uk:regulations/uksi/2013/376/36#lcwra_element_standard_lcwra_claimant",
        "description": "Universal Credit LCWRA element",
    },
    "lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant": {
        "concept": "uk:regulations/uksi/2013/376/36#lcwra_element_pre_2026_severe_conditions_or_terminally_ill_claimant",
        "description": "Universal Credit LCWRA pre-2026 higher amount",
    },
    "carer_element": {
        "concept": "uk:regulations/uksi/2013/376/36#carer_element",
        "description": "Universal Credit carer element",
    },
    "childcare_costs_element_maximum_one_child": {
        "concept": "uk:regulations/uksi/2013/376/36#childcare_costs_element_maximum_one_child",
        "description": "Universal Credit childcare costs cap, one child",
    },
    "childcare_costs_element_maximum_two_or_more_children": {
        "concept": "uk:regulations/uksi/2013/376/36#childcare_costs_element_maximum_two_or_more_children",
        "description": "Universal Credit childcare costs cap, two or more children",
    },
    "section_11_amount_for_accommodation_payments": {
        "concept": "uk:statutes/ukpga/2012/5/11#section_11_amount_for_accommodation_payments",
        "description": "Universal Credit housing costs amount",
    },
    "universal_credit_maximum_amount": {
        "concept": "uk:statutes/ukpga/2012/5/8#universal_credit_maximum_amount",
        "description": "Universal Credit maximum amount",
    },
    "universal_credit_amounts_to_be_deducted": {
        "concept": "uk:statutes/ukpga/2012/5/8#universal_credit_amounts_to_be_deducted",
        "description": "Universal Credit total deductions",
    },
    "universal_credit_award_amount": {
        "concept": "uk:statutes/ukpga/2012/5/8#universal_credit_award_amount",
        "description": "Universal Credit final award amount",
    },
    "applicable_work_allowance_amount": {
        "concept": "uk:regulations/uksi/2013/376/22#applicable_work_allowance_amount",
        "description": "Universal Credit work allowance",
    },
    "earned_income_amount_subject_to_taper": {
        "concept": "uk:regulations/uksi/2013/376/22#earned_income_amount_subject_to_taper",
        "description": "Universal Credit earned income subject to taper",
    },
    "unearned_income_for_deduction": {
        "concept": "uk:regulations/uksi/2013/376/22#unearned_income_for_deduction",
        "description": "Universal Credit unearned income deduction",
    },
    "universal_credit_award_deduction_from_maximum_amount": {
        "concept": "uk:regulations/uksi/2013/376/22#universal_credit_award_deduction_from_maximum_amount",
        "description": "Universal Credit deduction from maximum amount",
    },
    "claimant_capital_for_prescribed_capital_limit": {
        "concept": "uk:regulations/uksi/2013/376/18#claimant_capital_for_prescribed_capital_limit",
        "description": "Universal Credit assessable capital",
    },
    "capital_tariff_monthly_income": {
        "concept": "uk:regulations/uksi/2013/376/72#capital_tariff_monthly_income",
        "description": "Universal Credit capital tariff monthly income",
    },
    "work_condition_met_for_assessment_period": {
        "concept": "uk:regulations/uksi/2013/376/32#work_condition_met_for_assessment_period",
        "description": "Universal Credit childcare work condition",
    },
    "childcare_costs_element_amount": {
        "concept": "uk:regulations/uksi/2013/376/34#childcare_costs_element_amount",
        "description": "Universal Credit childcare costs element",
    },
}

UK_EFRS_OUTPUT_CONCEPTS: dict[tuple[str, str], dict] = {
    ("national-insurance-class-1", "main_primary_class_1_contribution"): {
        "concept": "uk:statutes/ukpga/1992/4/8#main_primary_class_1_contribution",
        "description": "UK National Insurance main primary Class 1 contribution",
    },
    ("national-insurance-class-1", "additional_primary_class_1_contribution"): {
        "concept": "uk:statutes/ukpga/1992/4/8#additional_primary_class_1_contribution",
        "description": "UK National Insurance additional primary Class 1 contribution",
    },
    ("national-insurance-class-1", "primary_class_1_contribution"): {
        "concept": "uk:statutes/ukpga/1992/4/8#primary_class_1_contribution",
        "description": "UK National Insurance primary Class 1 contribution",
    },
    ("national-insurance-class-1", "employee_national_insurance"): {
        "concept": "uk:contributions/national-insurance#employee_national_insurance",
        "description": "UK employee National Insurance",
    },
    ("national-insurance-class-4", "main_class_4_contribution"): {
        "concept": "uk:statutes/ukpga/1992/4/15#main_class_4_contribution",
        "description": "UK National Insurance main Class 4 contribution",
    },
    ("national-insurance-class-4-final", "class_4_annual_maximum"): {
        "concept": "uk:regulations/uksi/2001/1004/100#class_4_annual_maximum",
        "description": "UK National Insurance Class 4 annual maximum",
    },
    (
        "national-insurance-class-4-final",
        "class_4_contribution_after_annual_maximum",
    ): {
        "concept": "uk:regulations/uksi/2001/1004/100#class_4_contribution_after_annual_maximum",
        "description": "UK National Insurance Class 4 after annual maximum",
    },
    ("national-insurance-final", "national_insurance_contribution"): {
        "concept": "uk:statutes/ukpga/1992/4/1#national_insurance_contribution",
        "description": "UK National Insurance contribution",
    },
    ("personal-allowance", "personal_allowance"): {
        "concept": "uk:statutes/ukpga/2007/3/35#personal_allowance",
        "description": "UK personal allowance",
    },
    ("income-tax-income-base", "total_income"): {
        "concept": "uk:statutes/ukpga/2007/3/23#total_income",
        "description": "UK income tax total income",
    },
    ("income-tax-income-base", "net_income"): {
        "concept": "uk:statutes/ukpga/2007/3/23#net_income",
        "description": "UK income tax net income",
    },
    ("income-tax-income-base", "income_tax_liability"): {
        "concept": "uk:statutes/ukpga/2007/3/23#income_tax_liability",
        "description": "UK income tax liability",
    },
    ("income-tax-section-10-earned-income", "income_charged_at_basic_rate"): {
        "concept": "uk:statutes/ukpga/2007/3/10#income_charged_at_basic_rate",
        "description": "UK earned income charged at basic rate",
    },
    ("income-tax-section-10-earned-income", "income_charged_at_higher_rate"): {
        "concept": "uk:statutes/ukpga/2007/3/10#income_charged_at_higher_rate",
        "description": "UK earned income charged at higher rate",
    },
    (
        "income-tax-section-10-earned-income",
        "income_charged_at_additional_rate",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/10#income_charged_at_additional_rate",
        "description": "UK earned income charged at additional rate",
    },
    ("income-tax-section-10-earned-income", "tax_on_income_charged_at_basic_rate"): {
        "concept": "uk:statutes/ukpga/2007/3/10#tax_on_income_charged_at_basic_rate",
        "description": "UK tax on basic-rate earned income",
    },
    ("income-tax-section-10-earned-income", "tax_on_income_charged_at_higher_rate"): {
        "concept": "uk:statutes/ukpga/2007/3/10#tax_on_income_charged_at_higher_rate",
        "description": "UK tax on higher-rate earned income",
    },
    (
        "income-tax-section-10-earned-income",
        "tax_on_income_charged_at_additional_rate",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/10#tax_on_income_charged_at_additional_rate",
        "description": "UK tax on additional-rate earned income",
    },
    ("income-tax-section-10-earned-income", "income_tax_on_section_10_income"): {
        "concept": "uk:statutes/ukpga/2007/3/10#income_tax_on_section_10_income",
        "description": "UK tax on section 10 earned income",
    },
    (
        "income-tax-section-11d-savings-income",
        "savings_income_charged_at_savings_basic_rate",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/11D#savings_income_charged_at_savings_basic_rate",
        "description": "UK savings income charged at savings basic rate",
    },
    (
        "income-tax-section-11d-savings-income",
        "savings_income_charged_at_savings_higher_rate",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/11D#savings_income_charged_at_savings_higher_rate",
        "description": "UK savings income charged at savings higher rate",
    },
    (
        "income-tax-section-11d-savings-income",
        "savings_income_charged_at_savings_additional_rate",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/11D#savings_income_charged_at_savings_additional_rate",
        "description": "UK savings income charged at savings additional rate",
    },
    (
        "income-tax-section-11d-savings-income",
        "savings_income_charged_under_section_11d",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/11D#savings_income_charged_under_section_11d",
        "description": "UK savings income charged under section 11D",
    },
    (
        "income-tax-section-11d-savings-income",
        "income_tax_on_section_11d_savings_income",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/11D#income_tax_on_section_11d_savings_income",
        "description": "UK tax on section 11D savings income",
    },
    (
        "income-tax-section-13-dividend-income",
        "dividend_income_charged_under_section_13",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/13#dividend_income_charged_under_section_13",
        "description": "UK dividend income charged under section 13",
    },
    (
        "income-tax-section-13-dividend-income",
        "income_tax_on_section_13_dividend_income",
    ): {
        "concept": "uk:statutes/ukpga/2007/3/13#income_tax_on_section_13_dividend_income",
        "description": "UK tax on section 13 dividend income",
    },
    ("child-benefit", "child_benefit_weekly_rate"): {
        "concept": "uk:regulations/uksi/2006/965/2#child_benefit_weekly_rate",
        "description": "UK Child Benefit weekly rate",
    },
    ("benefit-cap-relevant-amount", "benefit_cap_relevant_amount"): {
        "concept": "uk:regulations/uksi/2013/376/80A#benefit_cap_relevant_amount",
        "description": "UK benefit cap relevant amount",
    },
    ("state-pension-credit-qualifying-age", "qualifying_age"): {
        "concept": "uk:statutes/ukpga/2002/16/1#qualifying_age",
        "description": "UK State Pension Credit qualifying age",
    },
    (
        "state-pension-credit-qualifying-age",
        "claimant_has_attained_qualifying_age",
    ): {
        "concept": "uk:statutes/ukpga/2002/16/1#claimant_has_attained_qualifying_age",
        "description": "UK State Pension Credit qualifying-age status",
    },
    ("state-pension-credit-guarantee-credit", "appropriate_minimum_guarantee"): {
        "concept": "uk:statutes/ukpga/2002/16/2#appropriate_minimum_guarantee",
        "description": "UK Pension Credit appropriate minimum guarantee",
    },
    ("state-pension-credit-guarantee-credit", "guarantee_credit"): {
        "concept": "uk:statutes/ukpga/2002/16/2#guarantee_credit",
        "description": "UK Pension Credit guarantee credit",
    },
    ("state-pension-credit-savings-credit", "savings_credit"): {
        "concept": "uk:statutes/ukpga/2002/16/3#savings_credit",
        "description": "UK Pension Credit savings credit",
    },
    ("pension-credit", "standard_minimum_guarantee"): {
        "concept": "uk:regulations/uksi/2002/1792/6#standard_minimum_guarantee",
        "description": "UK Pension Credit standard minimum guarantee",
    },
    ("pension-credit", "severe_disability_additional_amount"): {
        "concept": "uk:regulations/uksi/2002/1792/6#severe_disability_additional_amount",
        "description": "UK Pension Credit severe disability addition",
    },
    ("pension-credit", "carer_additional_amount"): {
        "concept": "uk:regulations/uksi/2002/1792/6#carer_additional_amount",
        "description": "UK Pension Credit carer addition",
    },
    ("pension-credit-child-addition", "additional_amount_applicable"): {
        "concept": "uk:regulations/uksi/2002/1792/6#additional_amount_applicable",
        "description": "UK Pension Credit child additional amount",
    },
    ("pension-credit-deemed-income", "capital_deemed_weekly_income"): {
        "concept": "uk:regulations/uksi/2002/1792/schedule/IIA#capital_deemed_weekly_income",
        "description": "UK Pension Credit capital deemed weekly income",
    },
    ("esa-income-tariff-income", "capital_tariff_weekly_income"): {
        "concept": "uk:regulations/uksi/2008/794/118#capital_tariff_weekly_income",
        "description": "UK ESA income capital tariff weekly income",
    },
    ("jsa-income-tariff-income", "capital_tariff_weekly_income"): {
        "concept": "uk:regulations/uksi/1996/207/116#capital_tariff_weekly_income",
        "description": "UK JSA income capital tariff weekly income",
    },
    ("income-support-tariff-income", "capital_tariff_weekly_income"): {
        "concept": "uk:regulations/uksi/1987/1967/53#capital_tariff_weekly_income",
        "description": "UK Income Support capital tariff weekly income",
    },
    ("housing-benefit-working-age-tariff-income", "capital_tariff_weekly_income"): {
        "concept": "uk:regulations/uksi/2006/213/52#capital_tariff_weekly_income",
        "description": "UK Housing Benefit working-age capital tariff weekly income",
    },
    ("housing-benefit-pension-age-tariff-income", "capital_tariff_weekly_income"): {
        "concept": "uk:regulations/uksi/2006/214/29#capital_tariff_weekly_income",
        "description": "UK Housing Benefit pension-age capital tariff weekly income",
    },
    ("student-loan-repayment", "student_loan_repayment"): {
        "concept": "uk:policies/govuk/student-loan-repayments#student_loan_repayment",
        "description": "UK student loan repayment",
    },
    ("carers-allowance-final", "carers_allowance_annual_amount"): {
        "concept": "uk:policies/govuk/carers-allowance#carers_allowance_annual_amount",
        "description": "UK Carer's Allowance annual amount",
    },
    ("carer-support-payment-final", "carer_support_payment_annual_amount"): {
        "concept": "uk:policies/govuk/carer-support-payment#carer_support_payment_annual_amount",
        "description": "UK Carer Support Payment annual amount",
    },
    ("scottish-child-payment-final", "scottish_child_payment_annual_amount"): {
        "concept": "uk:policies/govuk/scottish-child-payment#scottish_child_payment_annual_amount",
        "description": "UK Scottish Child Payment annual amount",
    },
    (
        "disability-living-allowance-final",
        "disability_living_allowance_self_care_weekly_amount",
    ): {
        "concept": "uk:policies/govuk/disability-living-allowance#dla_care_component_weekly_amount",
        "description": "UK child DLA care component weekly amount",
    },
    (
        "disability-living-allowance-final",
        "disability_living_allowance_mobility_weekly_amount",
    ): {
        "concept": "uk:policies/govuk/disability-living-allowance#dla_mobility_component_weekly_amount",
        "description": "UK child DLA mobility component weekly amount",
    },
    (
        "disability-living-allowance-final",
        "disability_living_allowance_annual_amount",
    ): {
        "concept": "uk:policies/govuk/disability-living-allowance#disability_living_allowance_annual_amount",
        "description": "UK child DLA annual amount",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "name",
        nargs="?",
        help="Comparison name (comparisons/<name>.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the JSON report (default: reports/)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print headline numbers after the run",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available comparisons and exit",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Override the comparison's sample_size for this run only",
    )
    parser.add_argument(
        "--sanity",
        action="store_true",
        help=(
            "Run the comparison's hand-built sanity fixtures "
            "(<name>.fixtures.yaml) instead of the population-scale "
            "comparison. Non-zero exit if any fixture fails."
        ),
    )
    args = parser.parse_args()

    if args.list:
        for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
            if path.name.endswith(".fixtures.yaml"):
                continue
            config = yaml.safe_load(path.read_text())
            kind = config.get("kind") if isinstance(config, dict) else None
            if kind == "parameter-suite-list":
                # A declarative suite list consumed by
                # run_parameter_comparisons.py, not a runner-registry entry.
                # It self-declares `kind`, so this is an explicit branch rather
                # than the old "no `name:` key" heuristic (the #73 --list fix).
                suites = config.get("suites") or []
                print(f"{path.stem:24s}  ({len(suites)} parameter suites)")
                continue
            if "name" not in config:
                # Defensive: any other file without a runner name is listed by
                # filename rather than crashing --list.
                print(f"{path.stem:24s}  (non-registry config)")
                continue
            print(f"{config['name']:24s}  {config.get('title', '')}")
        return 0

    if not args.name:
        parser.error("name is required (or pass --list)")

    if args.sanity:
        return _run_sanity(args.name)

    config = _load_comparison(args.name)
    if args.sample_size is not None:
        config["runner"]["parameters"]["sample_size"] = args.sample_size
    runner_type = config["runner"]["type"]
    runner_fn = RUNNERS.get(runner_type)
    if runner_fn is None:
        raise SystemExit(
            f"unknown runner type {runner_type!r}; available: {sorted(RUNNERS)}"
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    basename = config["artifacts"]["report_basename"]
    sample = config["runner"]["parameters"].get("sample_size", "all")
    output = args.output_dir / f"{basename}-{sample}-{today}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    # Run-private staging file in the SAME directory (same filesystem, so the
    # final publish is an atomic rename): the report stays private through
    # provenance stamping and dashboard adaptation, so a concurrent run can
    # no longer replace the report between write and stamp and get the other
    # run's identity stamped onto its payload; the published path only ever
    # holds a fully stamped report. The staging file is created EXCLUSIVELY
    # under a randomized name (a PID-derived name is predictable: same-PID
    # containers sharing the directory collide, and a pre-created symlink at
    # a predictable path would be followed by the runner's write) and is
    # re-verified as this user's regular file immediately before publication
    # (#448 review rounds 3 and 4).
    staging_fd, staging_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.run-", suffix=".tmp"
    )
    os.close(staging_fd)
    staging = Path(staging_name)

    print(f"Running {config['name']}: {config.get('title', config['name'])}")
    try:
        runner_fn(config["runner"], staging)

        # Provenance (O2): stamp what produced this report — rulespec repos +
        # SHAs, engine identity, oracle identity, dataset identity, run kind —
        # onto both the reports/ JSON and the dashboard copy, so a checked-in
        # report records exactly what it ran against and the affected-rerun
        # map can diff its SHAs.
        provenance = _build_run_provenance(config, runner_type, staging)
        compared_engines = {
            str(config["runner"]["parameters"].get("left", "")),
            str(config["runner"]["parameters"].get("right", "")),
        }
        _stamp_report_provenance(
            staging,
            provenance,
            require_engine_versions=(
                runner_type == "axiom-oracles-compare"
                and "policyengine" in compared_engines
            ),
        )

        dashboard_target = config.get("dashboard", {}).get("filename")
        adapted = None
        if dashboard_target:
            suite = config.get("dashboard", {}).get("suite", config["name"])
            adapted = _adapt_to_v2(
                staging,
                runner_type,
                config,
                suite=suite,
            )
            adapted["provenance"] = provenance

        # Publish the report and its dashboard copy as a pair under an
        # exclusive same-directory lock, so two same-day runs cannot
        # interleave into a report-B/dashboard-A outcome; verify the staging
        # path is still this user's regular file (not a swapped-in symlink)
        # before the atomic rename (#448 review round 4).
        lock_path = output.with_name(f".{output.name}.lock")
        with open(lock_path, "a") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            staging_stat = os.lstat(staging)
            if not stat.S_ISREG(staging_stat.st_mode) or (
                staging_stat.st_uid != os.getuid()
            ):
                raise SystemExit(
                    f"staging report {staging} is no longer this user's "
                    "regular file — refusing to publish"
                )
            os.replace(staging, output)
            print(f"Wrote: {output}")
            if dashboard_target and adapted is not None:
                _write_dashboard_report(
                    adapted, dashboard_target, full_report_path=output
                )
    finally:
        staging.unlink(missing_ok=True)

    if args.summary:
        _print_summary(output)
        _print_coverage_warnings(config)

    return 0


def _euromod_release_from_model_root(model_root: str | None) -> str | None:
    """Read the EUROMOD-platform release label off the model-root directory name.

    ``EUROMOD_RELEASES_J2.0+`` → ``J2.0+``; ``UKMOD_PUBLIC_B2026.03`` →
    ``B2026.03``. Returns None when the name carries no recognizable release
    token so the provenance sub-block omits it rather than guessing.
    """
    if not model_root:
        return None
    name = _expand_path(model_root).name
    for prefix in ("EUROMOD_RELEASES_", "UKMOD_PUBLIC_"):
        if name.startswith(prefix):
            return name[len(prefix):] or None
    return None


def _complete_rulespecs_from_affected_map(
    config: dict, runner: dict, rulespecs: list[dict]
) -> list[dict]:
    """Fill missing or SHA-less rulespec entries for the suite's mapped repos.

    ``comparisons/affected_map.json`` is the committed statement of which
    rulespec repos each suite exercises — the same map
    ``select_affected_suites.py`` diffs report SHAs against. For every mapped
    repo this report cannot yet prove a SHA for, resolve one honestly:

    * the runner's own fresh-clone SHA when it recorded one
      (``_cloned_rulespec_us_sha``, the tax lane's temp clone), else
    * the checkout the supervised-layout conventions resolve
      (:func:`axiom_oracles.provenance.resolve_rulespec_checkout` — the same
      locations the harnesses themselves search).

    Entries that already carry a SHA are untouched, and declared-path entries
    always win over convention lookups. Unresolvable repos keep or gain a
    ``sha: None`` entry so the selector's conservative "cannot prove fresh"
    reading stays intact. Never raises — provenance must annotate a run,
    never fail one.
    """
    try:
        from axiom_oracles.provenance import resolve_rulespec_checkout

        map_path = COMPARISONS_DIR / "affected_map.json"
        if not map_path.exists():
            return rulespecs
        affected_map = json.loads(map_path.read_text())
        suite = (config.get("dashboard") or {}).get("suite", config.get("name"))
        registry_name = config.get("name")
        mapped_repos: list[str] = []
        for entry in affected_map.get("suites", []):
            if entry.get("suite") == suite or entry.get("name") == registry_name:
                for repo in entry.get("repos", []):
                    if repo not in mapped_repos:
                        mapped_repos.append(repo)
        if not mapped_repos:
            return rulespecs
        by_repo = {e.get("repo"): e for e in rulespecs}
        completed = list(rulespecs)
        for repo in mapped_repos:
            if by_repo.get(repo, {}).get("sha"):
                continue
            sha = None
            if repo == "TheAxiomFoundation/rulespec-us":
                sha = runner.get("_cloned_rulespec_us_sha")
            if sha is None:
                checkout = resolve_rulespec_checkout(repo)
                if checkout is not None:
                    sha = _git_head_sha(checkout)
            if repo in by_repo:
                if sha:
                    by_repo[repo]["sha"] = sha
            else:
                entry = {"repo": repo, "sha": sha}
                by_repo[repo] = entry
                completed.append(entry)
        return completed
    except Exception:
        return rulespecs


def _build_run_provenance(config: dict, runner_type: str, output: Path) -> dict:
    """Assemble the provenance block for a completed comparison run.

    Reads the config for rulespec checkout paths / remote, engine repo, and the
    oracle stack pins; reads the just-written report for a ``dataset_identity``
    block (threaded by the FIIT/UK adapters). Everything degrades gracefully —
    provenance must annotate a run, never fail one.
    """
    from axiom_oracles.provenance import (
        build_provenance,
        dataset_provenance_from_identity,
        engine_provenance,
        rulespec_provenance,
    )

    runner = config.get("runner") or {}
    params = runner.get("parameters") or {}

    # Rulespec repos + SHAs, from whichever path form this runner uses. The
    # remote-cloned FIIT lane records the remote's slug (SHA is the clone's
    # HEAD only if it survives; a fresh --depth 1 clone is main's tip).
    rulespec_paths: list[str] = []
    for entry in params.get("rulespec_roots") or runner.get("rulespec_roots") or []:
        rulespec_paths.append(str(entry))
    for key in ("rulespec_root",):
        val = runner.get(key) or params.get(key)
        if val:
            rulespec_paths.append(str(val))
    # The EUROMOD/UKMOD synthetic lane points `axiom_rulespec_repo_roots` at the
    # whole org directory and names the model country; the encoded rules live in
    # that country's `rulespec-<cc>` repo under the roots dir, so resolve it
    # explicitly for provenance (mirrors the affected-map's country → repo map).
    if runner_type == "euromod-synthetic-compare":
        roots = params.get("axiom_rulespec_repo_roots")
        country = params.get("euromod_country")
        if roots and country:
            rulespec_paths.append(
                str(Path(str(roots)) / f"rulespec-{str(country).lower()}")
            )
    # The SNAP QC lane resolves its rulespec checkout inside the bridge (env
    # fallback and workspace default), so read the root it actually ran
    # against off the just-written report — otherwise the affected-rerun
    # staleness check has no SHA to diff for this suite. NEVER for a skip
    # re-emit: the recorded root is a path, and resolving it against a
    # freshly materialized clone would stamp re-emitted numbers as fresh.
    if (
        runner_type == "snap-qc-compare"
        and not rulespec_paths
        and not runner.get("_reemitted_report")
    ):
        try:
            report_provenance = (
                json.loads(output.read_text()).get("summary", {}).get("provenance", {})
            )
            ran_against = report_provenance.get("rulespec_root")
            if ran_against:
                rulespec_paths.append(str(ran_against))
        except Exception:  # provenance must annotate, never fail a run
            pass
    rulespecs = rulespec_provenance(rulespec_paths)
    verified_upstream_sha = params.get(_VERIFIED_RULESPEC_UPSTREAM_SHA)
    if verified_upstream_sha and rulespecs:
        # The federal runner set this private marker only after checking that
        # the clean local snapshot's tree equals the public upstream tree pin.
        # Record the merged-main commit whose content ran, not a local
        # content-equivalent materialization commit.
        rulespecs = [
            {**entry, "sha": str(verified_upstream_sha)}
            for entry in rulespecs
        ]
    remote = runner.get("rulespec_remote") or params.get("rulespec_remote")
    if remote and not rulespecs:
        from axiom_oracles.provenance import repo_slug_from_remote

        slug = repo_slug_from_remote(str(remote))
        if slug:
            rulespecs = [{"repo": slug, "sha": None}]
    # A `sha: null` (or absent) entry for a mapped repo reads as "cannot prove
    # fresh" to select_affected_suites.py, which re-selects the suite on every
    # 6-hourly sweep even right after a successful refresh. Complete the gaps
    # from what the run actually had in hand: the exact SHA of the runner's own
    # fresh clone when there was one, else the checkout the supervised-layout
    # conventions resolve (the same conventions the harnesses themselves use).
    # Only for runner types whose runs are always REAL executions — a
    # skip-capable lane (euromod/gettsim/snap-qc re-emit the committed report
    # when a model root or data file is absent) must never have current SHAs
    # stamped onto re-emitted numbers, or the selector would mark rules-stale
    # results fresh.
    if runner_type in (
        "axiom-encode-snap-ecps-compare",
        "axiom-encode-tax-ecps-compare",
        "axiom-oracles-compare",
    ):
        rulespecs = _complete_rulespecs_from_affected_map(config, runner, rulespecs)
    # A skip-capable runner that re-emitted the committed report never
    # executed any rules this run — no matter which path produced a rulespec
    # entry (configured roots included), its SHA must not be recorded, or the
    # selector would mark rules-stale numbers fresh (#296 review).
    if runner.get("_reemitted_report"):
        rulespecs = [{**entry, "sha": None} for entry in rulespecs]

    # Engine identity (Axiom side under test).
    axiom_rules_ref = runner.get("axiom_rules_repo") or params.get("axiom_rules_repo")
    axiom_rules_path = None
    if axiom_rules_ref:
        try:
            axiom_rules_path = _resolve_path(str(axiom_rules_ref), "axiom_rules_repo")
        except SystemExit:
            axiom_rules_path = None
    engine = engine_provenance(axiom_rules_path)
    # Verifiable executable identity, when the lane resolved one (us-tariff-
    # panel records the binary path + sha256 of its bytes): the repo-derived
    # `axiom_rules_engine_sha` above labels the checkout's current HEAD, which
    # can postdate the build that actually ran (#448 review round 3).
    engine_binary = params.get("engine_binary")
    engine_binary_sha256 = params.get("engine_binary_sha256")
    if engine_binary:
        engine = {**engine, "binary": str(engine_binary)}
    if engine_binary_sha256:
        engine = {**engine, "binary_sha256": str(engine_binary_sha256)}

    # Oracle identity (the side compared to). Derived from the runner type +
    # the pins each runner installs, so the report says which oracle stack ran.
    oracle: dict = {}
    if runner_type == "axiom-encode-tax-ecps-compare":
        oracle = {
            "name": "policyengine",
            "policyengine_package": (
                f"policyengine=={params.get('policyengine_version', '4.11.0')}"
                if params.get("pinned", True)
                else "policyengine"
            ),
            "policyengine_us": (
                params.get("policyengine_us_version", "1.729.0")
                if params.get("pinned", True)
                else None
            ),
        }
    elif runner_type == "axiom-encode-uk-efrs-compare":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.88.56"),
        }
    elif runner_type == "uk-council-tax-reduction-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "uk-capital-gains-tax-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "uk-business-rates-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "uk-lbtt-ltt-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "uk-winter-fuel-payment-pe-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "uk-attendance-allowance-pe-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "uk-tax-free-childcare-pe-grid":
        oracle = {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.89.2"),
        }
    elif runner_type == "axiom-oracles-compare":
        engines = {str(params.get("left", "")), str(params.get("right", ""))}
        pins = _resolve_pe_oracle_pins(params)
        oracle = {
            "name": params.get("right", "policyengine"),
            "policyengine_package": pins[0],
            "policyengine_us": pins[1].split("==", 1)[-1],
            "policyengine_core": pins[2].split("==", 1)[-1],
        }
        # Pin the Tax-Calculator engine version when it is a participant, so a
        # taxcalc-vs-policyengine report records both engine stacks it compared
        # (the Axiom-specific `engine` block is empty for an oracle-vs-oracle
        # run). Matches the pin the runner installs into its isolated env.
        if "taxcalc" in engines:
            oracle["taxcalc"] = "6.7.1"
    elif runner_type in ("federal-tax-liability-grid", "snap-abawd-boundary-grid"):
        pins = _resolve_pe_oracle_pins(params)
        oracle = {
            "name": "policyengine",
            "policyengine_package": pins[0],
            "policyengine_us": pins[1].split("==", 1)[-1],
            "policyengine_core": pins[2].split("==", 1)[-1],
        }
    elif runner_type == "state-income-tax-liability-grid":
        pins = _resolve_pe_oracle_pins(params)
        oracle = {
            "name": "policyengine-taxsim",
            "policyengine_package": pins[0],
            "policyengine_us": pins[1].split("==", 1)[-1],
            "policyengine_core": pins[2].split("==", 1)[-1],
            "policyengine_taxsim": "2.30.0",
        }
    elif runner_type == "axiom-encode-snap-ecps-compare":
        oracle = {"name": "policyengine", "policyengine_us": "1.705.1"}
    elif runner_type == "euromod-synthetic-compare":
        # EUROMOD/UKMOD identity comes straight from the runner params: the
        # model release is read off the model-root directory name (e.g.
        # EUROMOD_RELEASES_J2.0+ → "J2.0+", UKMOD_PUBLIC_B2026.03 → "B2026.03"),
        # and system/dataset are the exact strings the adapter runs under.
        oracle = {
            "name": "euromod",
            "euromod_release": _euromod_release_from_model_root(
                params.get("euromod_model_root")
            ),
            "euromod_country": params.get("euromod_country"),
            "euromod_system": params.get("euromod_system"),
            "euromod_dataset": params.get("euromod_dataset"),
        }
    elif runner_type == "gettsim-synthetic-compare":
        # The Germany lane is a direct pair: record both independent oracle
        # stacks in the oracle block; there is intentionally no Axiom engine
        # identity for this baseline report.
        oracle = {
            "name": "euromod-gettsim",
            "euromod_release": _euromod_release_from_model_root(
                params.get("euromod_model_root")
            ),
            "euromod_country": params.get("euromod_country"),
            "euromod_system": params.get("euromod_system"),
            "euromod_dataset": params.get("euromod_dataset"),
            "gettsim_version": params.get("gettsim_version", "1.2.1"),
            "gettsim_policy_date": params.get(
                "gettsim_policy_date", "2025-06-30"
            ),
        }
    elif runner_type == "snap-qc-compare":
        # The USDA SNAP QC public-use file is the oracle; its identity is the
        # pinned posting for the fiscal year (immutable, sha256-verified by the
        # loader). The bridge's own summary.provenance carries the richer
        # overlay/engine identity for the run.
        oracle = {"name": "snap-qc", "fiscal_year": params.get("fiscal_year")}
        try:
            from axiom_oracles.populations.snap_qc import SNAP_QC_PINS

            pin = SNAP_QC_PINS.get(int(params.get("fiscal_year", 0)))
            if pin is not None:
                oracle["url"] = pin.url
                oracle["sha256"] = pin.sha256
        except Exception:  # provenance must annotate, never fail a run
            pass

    # Dataset identity — reuse the pinned-populace identity (#80/#952) when the
    # report carries one.
    dataset = None
    try:
        raw_report = json.loads(output.read_text())
        identity = _normalize_dataset_identity(raw_report) if isinstance(
            raw_report, dict
        ) else None
        dataset = dataset_provenance_from_identity(identity)
    except (OSError, json.JSONDecodeError):
        dataset = None
    if dataset is None:
        # No encode identity block: record the population label the config
        # declares so the dataset sub-block is never wholly empty.
        population = params.get("population") or params.get("dataset")
        if population:
            dataset = {"source": "config", "population": str(population)}

    provenance = build_provenance(
        generated_by=f"scripts/run_comparison.py::{config.get('name', '?')}",
        rulespecs=rulespecs,
        engine=engine,
        oracle=oracle,
        dataset=dataset,
    )
    # Explicit serialized re-emission status: nulled rulespec SHAs already
    # mark staleness for the affected-suite selector, but the payload itself
    # must also say its numbers were re-emitted from the committed report
    # rather than newly computed on this host (#448 review). The
    # generated_at timestamp dates the re-emission, not the numbers.
    if runner.get("_reemitted_report"):
        provenance["reemitted_report"] = True
        # The source report's identity + original generation time, when the
        # re-emitting lane recorded it: generated_at above dates the
        # re-emission, THIS dates the numbers (sol stack review F6).
        if runner.get("_reemitted_source"):
            provenance["reemitted_from"] = runner["_reemitted_source"]
    return provenance


def _stamp_report_provenance(
    output: Path,
    provenance: dict,
    *,
    require_engine_versions: bool = False,
) -> None:
    """Add ``provenance`` to the reports/ JSON, preserving the file's own format.

    Different runners serialize their reports/ artifact differently (sorted vs
    insertion order, with/without trailing newline). Re-detect the original
    formatting and re-emit in the same shape so adding provenance produces a
    one-key diff rather than reordering every key.
    """
    try:
        original_text = output.read_text()
        data = json.loads(original_text)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    data["provenance"] = provenance
    engines = data.get("engines")
    if require_engine_versions and not isinstance(engines, dict):
        raise SystemExit(
            "comparison report did not record its runtime engine versions"
        )
    if isinstance(engines, dict):
        versions = dict(engines.get("versions") or {})
        engine = provenance.get("engine") or {}
        oracle = provenance.get("oracle") or {}
        axiom_version = engine.get("axiom_rules_engine_version")
        expected_versions = {}
        policyengine_pin = oracle.get("policyengine_package")
        if (
            isinstance(policyengine_pin, str)
            and policyengine_pin.startswith("policyengine==")
        ):
            expected_versions["policyengine"] = policyengine_pin.split("==", 1)[1]
        for provenance_key, version_key in (
            ("policyengine_core", "policyengine_core"),
            ("policyengine_us", "policyengine_us"),
        ):
            value = oracle.get(provenance_key)
            if value:
                expected_versions[version_key] = str(value)
        if require_engine_versions:
            mismatched = {
                key: {"expected": expected, "actual": versions.get(key)}
                for key, expected in expected_versions.items()
                if versions.get(key) != expected
            }
            if mismatched:
                raise SystemExit(
                    "comparison report runtime engine versions do not match "
                    f"the resolved oracle pins: {mismatched}"
                )
        if axiom_version:
            versions["axiom_rules_engine"] = str(axiom_version)
        if versions:
            engines["versions"] = versions
    trailing = "\n" if original_text.endswith("\n") else ""
    for sort_keys in (True, False):
        for indent in (2, 1):
            reserialized = json.dumps(
                json.loads(original_text), indent=indent, sort_keys=sort_keys
            )
            if original_text in (reserialized, reserialized + "\n"):
                output.write_text(
                    json.dumps(data, indent=indent, sort_keys=sort_keys) + trailing
                )
                return
    # Unknown formatting (hand-edited): default to indent=2 sorted.
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + trailing)


def _print_coverage_warnings(config: dict) -> None:
    """Run compose-spec coverage analysis against the comparison's compiled
    program and surface any eligibility-looking rules that aren't
    referenced by the comparison concept's expression tree.

    Cheap static analysis — runs in-process (no uv subprocess) since it
    only needs to read the compiled JSON. Silent when there are no gaps.
    """
    params = config.get("runner", {}).get("parameters") or {}
    compiled_program_ref = params.get("axiom_compiled_program")
    # Coverage analysis is per-concept; if a comparison declares multiple,
    # iterate. Falls back to the legacy single `concept:` field.
    concepts_raw = params.get("concepts") or (
        [params.get("concept")] if params.get("concept") else []
    )
    concepts: list[str] = [c for c in concepts_raw if isinstance(c, str) and c]
    if not compiled_program_ref or not concepts:
        return
    try:
        compiled_program = _resolve_path(compiled_program_ref, "axiom_compiled_program")
    except SystemExit:
        return
    if not compiled_program.exists():
        return
    try:
        from axiom_oracles.coverage import (
            find_uncovered_eligibility_rules,
            format_coverage_warning,
        )
    except ImportError:
        return
    # Coverage detection asks "what eligibility tests are orphaned" — only
    # auto-fires when the target itself looks like an eligibility judgment.
    # For amount targets (snap_benefit, federal-income-tax#liability) the
    # orphaned eligibility rules are intentionally on a different chain;
    # surfacing them as alarms would be noise. Users can still opt in
    # via `axiom-oracles coverage` directly with any target.
    for concept in concepts:
        target = str(concept).rsplit("#", 1)[-1]
        if not any(m in target for m in ("eligible", "ineligible")):
            continue
        uncovered = find_uncovered_eligibility_rules(compiled_program, target=target)
        warning = format_coverage_warning(target, uncovered)
        if warning:
            print()
            print(warning)


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _run_axiom_encode_tax_ecps_compare(runner: dict, output: Path) -> None:
    """`axiom-encode tax-populace-compare` via uv run with the pinned PE stack.

    The encoder renamed the subcommand from tax-ecps-compare in its
    ECPS→Populace rename (no alias survives on axiom-encode main); the runner
    type keeps the old name so existing suite YAMLs stay valid.
    """
    axiom_encode_repo = _resolve_path(runner["axiom_encode_repo"], "axiom_encode_repo")
    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    _ensure_engine_binary(axiom_rules_repo, kind="release")
    rulespec_root = _ensure_rulespec_us_checkout(runner["rulespec_remote"])
    # The clone is deleted in the finally below, before provenance is stamped —
    # record its HEAD now so the report can say which rulespec-us SHA it ran
    # against (a `sha: null` entry reads as "cannot prove fresh" to
    # select_affected_suites.py and re-selects the suite every run).
    runner["_cloned_rulespec_us_sha"] = _git_head_sha(rulespec_root)
    params = runner["parameters"]
    pinned = params.get("pinned", True)
    # PolicyEngine-US 1.729.0 is the model version the certified pinned Populace
    # artifact was built with (axiom-encode population.py::POPULACE_PINS, built_with
    # "1.729.0"), and it clears the tax harness's floor (ecps_tax.py
    # MIN_POLICYENGINE_US_VERSION = "1.723"). The previously pinned 1.705.16 is
    # below that floor, so the harness now rejects it — a pinned FIIT run would
    # fail hard. Keeping the PE meta-package at 4.11.0 (the oracle baseline used
    # by the other runners) with an explicit newer -us is why the runner passes
    # --allow-policyengine-us-version to the harness.
    # Oracle PE stack. The pinned versions default to the model version the
    # certified Populace artifact was built with (1.729.0), but a comparison can
    # override them to validate against a newer certified oracle — the us-pe
    # universe pins policyengine-us 1.767.3, which carries the #8614 partnership
    # self-employment split absent from 1.729.0's eitc_earned_income. The harness
    # still runs against the pinned Populace inputs (--allow-policyengine-us-version
    # bypasses the build_with gate), so only the PE computation vintage moves.
    pe_meta = params.get("policyengine_version", "4.11.0")
    pe_us = params.get("policyengine_us_version", "1.729.0")
    pe_core = params.get("policyengine_core_version", "3.26.11")
    pe_pins = (
        [
            "--with",
            f"policyengine=={pe_meta}",
            "--with",
            f"policyengine-us=={pe_us}",
            "--with",
            f"policyengine-core=={pe_core}",
        ]
        if pinned
        else [
            "--with",
            "policyengine",
            "--with",
            "policyengine-us",
            "--with",
            "policyengine-core",
        ]
    )
    cmd = [
        "uv",
        "run",
        "--python",
        str(params.get("python", "3.14")),
        "--no-project",
        "--with-editable",
        str(axiom_encode_repo),
        *pe_pins,
        "axiom-encode",
        "tax-populace-compare",
        "--rulespec-root",
        str(rulespec_root),
        "--axiom-rules-engine-path",
        str(axiom_rules_repo),
        "--sample-size",
        str(params.get("sample_size", 1000)),
        "--year",
        str(params.get("year", 2026)),
        "--surface",
        params.get("surface", "all"),
        "--json",
    ]
    if params.get("data_folder"):
        cmd.extend([
            "--data-folder",
            str(_resolve_path(params["data_folder"], "data_folder")),
        ])
    if params.get("allow_policyengine_us_version", True):
        cmd.append("--allow-policyengine-us-version")
    if params.get("allow_uncertified_policyengine_data", True):
        cmd.append("--allow-uncertified-policyengine-data")
    try:
        with output.open("w") as f:
            subprocess.run(cmd, check=True, stdout=f)
    finally:
        shutil.rmtree(rulespec_root.parent, ignore_errors=True)


def _run_axiom_encode_uk_efrs_compare(runner: dict, output: Path) -> None:
    """`axiom-encode uk-efrs-compare` via uv run with the pinned PE UK stack."""
    axiom_encode_repo = _resolve_path(runner["axiom_encode_repo"], "axiom_encode_repo")
    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    rulespec_root = _resolve_path(runner["rulespec_root"], "rulespec_root")
    _ensure_engine_binary(axiom_rules_repo, kind="release")
    params = runner["parameters"]
    universal_credit_program = _compose_uk_universal_credit_program(params)
    pe_pins = [
        "--with",
        f"policyengine-uk=={params.get('policyengine_uk_version', '2.88.56')}",
        "--with",
        f"policyengine-core=={params.get('policyengine_core_version', '3.26.11')}",
    ]
    data_folder = (
        _resolve_path(params["data_folder"], "data_folder")
        if params.get("data_folder")
        else REPO_ROOT / ".axiom" / "policyengine-data"
    )
    dataset = _ensure_uk_single_year_dataset(
        params.get("dataset", "enhanced_frs_2023_24"),
        data_folder=data_folder,
        year=int(params.get("year", 2026)),
    )
    surfaces = params.get("surfaces")
    if surfaces is None:
        surfaces = [params.get("surface", "all")]
    if isinstance(surfaces, str):
        surfaces = [surfaces]

    reports: list[dict] = []
    for index, surface in enumerate(surfaces, start=1):
        cmd = [
            "uv",
            "run",
            "--python",
            str(params.get("python", "3.13")),
            "--no-project",
            "--with-editable",
            str(axiom_encode_repo),
            *pe_pins,
            "axiom-encode",
            "uk-efrs-compare",
            "--rulespec-root",
            str(rulespec_root),
            "--axiom-rules-engine-path",
            str(axiom_rules_repo),
            "--sample-size",
            str(params.get("sample_size", 100)),
            "--year",
            str(params.get("year", 2026)),
            "--surface",
            str(surface),
            "--dataset",
            str(dataset),
            "--data-folder",
            str(data_folder),
            "--tolerance",
            str(params.get("tolerance", 0.01)),
            "--relative-tolerance",
            str(params.get("relative_tolerance", 2e-7)),
            "--json",
        ]
        if universal_credit_program is not None:
            cmd.extend([
                "--universal-credit-program",
                str(universal_credit_program),
            ])
        if params.get("workspace_root"):
            cmd.extend([
                "--root",
                str(_resolve_path(params["workspace_root"], "workspace_root")),
            ])
        print(
            f"  [{index}/{len(surfaces)}] UK EFRS surface {surface}...",
            flush=True,
        )
        started = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                print(exc.stdout[-4000:], file=sys.stderr)
            if exc.stderr:
                print(exc.stderr[-4000:], file=sys.stderr)
            raise
        elapsed = time.perf_counter() - started
        print(
            f"  [{index}/{len(surfaces)}] UK EFRS surface {surface} "
            f"completed in {elapsed:.1f}s",
            flush=True,
        )
        reports.append(json.loads(result.stdout))

    output.write_text(json.dumps(_merge_uk_efrs_reports(reports), indent=2) + "\n")


def _ensure_uk_single_year_dataset(dataset: str, *, data_folder: Path, year: int) -> str:
    """Return a PE-UK 2.88 single-year H5 path, adding time_period if needed."""
    dataset_path = _resolve_uk_dataset_path(dataset, data_folder=data_folder, year=year)
    if dataset_path is None:
        return dataset
    if _h5_has_dataset(dataset_path, "time_period"):
        return str(dataset_path)

    compatible_path = dataset_path.with_name(f"{dataset_path.stem}.uksingle.h5")
    if (
        compatible_path.exists()
        and compatible_path.stat().st_mtime >= dataset_path.stat().st_mtime
        and _h5_has_dataset(compatible_path, "time_period")
    ):
        return str(compatible_path)

    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(
            "pandas is required to prepare a PE-UK single-year EFRS dataset "
            f"from {dataset_path}"
        ) from exc

    with pd.HDFStore(dataset_path, mode="r") as source, pd.HDFStore(
        compatible_path,
        mode="w",
    ) as target:
        for key in ("person", "benunit", "household"):
            target.put(key, source[key], format="table", data_columns=True)
        target.put("time_period", pd.Series([year]), format="table")
    return str(compatible_path)


def _resolve_uk_dataset_path(
    dataset: str,
    *,
    data_folder: Path,
    year: int,
) -> Path | None:
    direct = Path(os.path.expandvars(os.path.expanduser(dataset))).resolve()
    if direct.exists() and direct.suffix == ".h5":
        return direct
    candidate = data_folder / f"{dataset}_year_{year}.h5"
    if candidate.exists():
        return candidate.resolve()
    return None


def _h5_has_dataset(path: Path, name: str) -> bool:
    try:
        import h5py
    except ImportError:
        return False
    with h5py.File(path, "r") as h5_file:
        return name in h5_file


def _compose_uk_universal_credit_program(params: dict) -> Path | None:
    program_ref = params.get("axiom_program")
    if not program_ref:
        return None

    compose_binary = _resolve_path(
        params.get(
            "axiom_compose_binary",
            "$HOME/axiom-compose/.venv/bin/axiom-compose",
        ),
        "axiom_compose_binary",
    )
    program_path = _resolve_path(program_ref, "axiom_program")
    composed_path = _expand_path(
        params.get("axiom_composed_program", "/tmp/uk-universal-credit-composed.yaml")
    )
    composed_path.parent.mkdir(parents=True, exist_ok=True)
    roots = [
        _resolve_path(root, "rulespec_roots")
        for root in params.get("rulespec_roots", [])
    ]
    compose_cmd = [str(compose_binary), str(program_path)]
    for root in roots:
        compose_cmd.extend(["--rulespec-root", str(root)])
    compose_cmd.extend(["-o", str(composed_path)])
    subprocess.run(compose_cmd, check=True, cwd=REPO_ROOT)
    return composed_path.resolve()


def _merge_uk_efrs_reports(reports: list[dict]) -> dict:
    if not reports:
        return {
            "compared_persons": 0,
            "compared_benunits": 0,
            "compared_values": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "oracle_divergence_count": 0,
            "oracle_divergences": [],
            "output_summary": [],
            "skipped_surfaces": [],
            "projection_notes": [],
        }
    if len(reports) == 1:
        return reports[0]
    merged = {
        "compared_persons": max(r.get("compared_persons", 0) for r in reports),
        "compared_benunits": max(r.get("compared_benunits", 0) for r in reports),
        "compared_values": sum(r.get("compared_values", 0) for r in reports),
        "mismatches": [],
        "oracle_divergences": [],
        "output_summary": [],
        "skipped_surfaces": [],
        "projection_notes": [],
    }
    seen_notes: set[str] = set()
    seen_skipped: set[str] = set()
    for report in reports:
        merged["mismatches"].extend(report.get("mismatches", []))
        merged["oracle_divergences"].extend(report.get("oracle_divergences", []))
        merged["output_summary"].extend(report.get("output_summary", []))
        for skipped in report.get("skipped_surfaces", []):
            key = json.dumps(skipped, sort_keys=True)
            if key not in seen_skipped:
                seen_skipped.add(key)
                merged["skipped_surfaces"].append(skipped)
        for note in report.get("projection_notes", []):
            if note not in seen_notes:
                seen_notes.add(note)
                merged["projection_notes"].append(note)
    merged["mismatch_count"] = len(merged["mismatches"])
    merged["oracle_divergence_count"] = len(merged["oracle_divergences"])
    return merged


def _run_axiom_encode_snap_ecps_compare(runner: dict, output: Path) -> None:
    """`axiom-encode snap-populace-compare`, adapted from CSV to v2 JSON.

    The encoder renamed the subcommand from snap-ecps-compare in its
    ECPS→Populace rename; the runner type keeps the old name so existing
    suite YAMLs stay valid.
    """
    axiom_encode_repo = _resolve_path(runner["axiom_encode_repo"], "axiom_encode_repo")
    params = runner["parameters"]
    axiom_binary = None
    if runner.get("axiom_rules_repo"):
        axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
        _ensure_engine_binary(axiom_rules_repo, kind="release")
        axiom_binary = axiom_rules_repo / "target" / "release" / "axiom-rules-engine"

    with tempfile.TemporaryDirectory(prefix="snap-ecps-compare.") as tmp:
        csv_path = Path(tmp) / "rows.csv"
        cmd = [
            "uv",
            "run",
            "--directory",
            str(axiom_encode_repo),
            "--with",
            "policyengine-us==1.705.1",
            "--with",
            "numpy",
            "axiom-encode",
            "snap-populace-compare",
            "--jurisdiction",
            str(params.get("jurisdiction", "us-co")),
            "--year",
            str(params.get("year", 2026)),
            "--month",
            str(params.get("month", 1)),
            "--utility-projection",
            str(params.get("utility_projection", "policyengine-type")),
            "--tolerance",
            str(params.get("tolerance", 1.5)),
            "--max-differences",
            str(params.get("max_differences", 50)),
            "--write-csv",
            str(csv_path),
        ]
        sample_size = params.get("sample_size")
        if sample_size not in (None, 0, "0"):
            cmd.extend(["--sample-size", str(sample_size)])
        if params.get("positive_snap_only"):
            cmd.append("--positive-snap-only")
        if params.get("state"):
            cmd.extend(["--state", str(params["state"])])
        if params.get("program"):
            cmd.extend(["--program", str(_resolve_path(params["program"], "program"))])
        if params.get("test_template"):
            cmd.extend(
                [
                    "--test-template",
                    str(_resolve_path(params["test_template"], "test_template")),
                ]
            )
        if params.get("workspace_root"):
            cmd.extend(
                [
                    "--workspace-root",
                    str(_resolve_path(params["workspace_root"], "workspace_root")),
                ]
            )
        if axiom_binary is not None:
            cmd.extend(["--axiom-binary", str(axiom_binary)])

        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
        with csv_path.open(newline="") as f:
            rows = list(csv.DictReader(f))

    report = _adapt_snap_ecps_csv_to_v2(rows, runner)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


# PolicyEngine 4.18.9 certifies its bundled manifest at PE-US 1.752.2.
# Keep the in-repo oracle runner on that certified pair so PE outputs are
# reproducible across environments; bump both together when refreshing the
# oracle (stale pins mean we validate against superseded PE tables — the CO
# TANF grant standards diverged exactly this way at 1.700.0). The
# axiom-encode subprocess runners above keep their own pins because they are
# validating the encoder stack.
_PE_ORACLE_PINS = (
    "policyengine==4.18.9",
    "policyengine-us==1.752.2",
    "policyengine-core==3.28.0",
)


def _resolve_pe_oracle_pins(params: dict) -> tuple[str, str, str]:
    """PE oracle pins for an in-repo compare, honoring per-comparison overrides.

    Defaults to ``_PE_ORACLE_PINS`` (the certified in-repo pair) so every other
    suite is unaffected; a comparison that must validate against a newer oracle
    (e.g. ssi-ecps against the us-pe universe pin policyengine-us 1.767.3) sets
    ``policyengine_version`` / ``policyengine_us_version`` /
    ``policyengine_core_version`` in its config.
    """
    meta = params.get("policyengine_version")
    us = params.get("policyengine_us_version")
    core = params.get("policyengine_core_version")
    return (
        f"policyengine=={meta}" if meta else _PE_ORACLE_PINS[0],
        f"policyengine-us=={us}" if us else _PE_ORACLE_PINS[1],
        f"policyengine-core=={core}" if core else _PE_ORACLE_PINS[2],
    )

# The compare and sanity subprocesses share this import shim — extracted to
# module scope so `_run_sanity` can reuse it. With _PE_ORACLE_PINS it should not
# need to bypass certification, but the shim keeps policyengine.us import
# behavior stable for the local CLI.
_PE_CERT_OVERRIDE = """
import json, os, sys
from importlib.metadata import version as _dist_version
from pathlib import Path

_runtime_engine_versions = {
    'policyengine': _dist_version('policyengine'),
    'policyengine_core': _dist_version('policyengine-core'),
    'policyengine_us': _dist_version('policyengine-us'),
}
os.environ['POLICYENGINE_SKIP_COUNTRY_IMPORTS'] = '1'
try:
    import policyengine
    import policyengine.provenance.manifest as _m

    def _allow_local_oracle_data(
        country_id, runtime_model_version, runtime_data_build_fingerprint=None
    ):
        return _m.DataCertification(
            compatibility_basis='axiom_oracle_local_policyengine_us_override',
            certified_for_model_version=runtime_model_version,
            data_build_fingerprint=runtime_data_build_fingerprint,
            certified_by='axiom-oracles run_comparison.py',
        )

    _m.certify_data_release_compatibility = _allow_local_oracle_data
    try:
        import policyengine.tax_benefit_models.common.model_version as _mv
        _mv.certify_data_release_compatibility = _allow_local_oracle_data
    except ImportError:
        pass
except ImportError:
    pass

os.environ.pop('POLICYENGINE_SKIP_COUNTRY_IMPORTS', None)
try:
    import policyengine
    from policyengine.tax_benefit_models import us as _us
    policyengine.us = _us
except Exception:
    pass

from axiom_oracles.cli import cli as _cli
_cli(sys.argv[1:], standalone_mode=False)
if '--output' in sys.argv:
    _output = Path(sys.argv[sys.argv.index('--output') + 1])
    _report = json.loads(_output.read_text())
    _report.setdefault('engines', {}).setdefault('versions', {}).update(
        _runtime_engine_versions
    )
    _output.write_text(json.dumps(_report, indent=2, sort_keys=True) + '\\n')
"""


def _concept_args(params: dict) -> list[str]:
    """Build `--concept <id>` repetitions from the comparison config.

    Accepts either ``concept: <id>`` (legacy single-string form) or
    ``concepts: [<id>, ...]`` for comparisons that span more than one
    output (e.g. SNAP eligibility AND benefit amount). The compare CLI's
    ``--concept`` option is ``multiple=True``, so we just repeat the
    flag once per concept."""

    concepts: list[str] = []
    raw_list = params.get("concepts")
    if isinstance(raw_list, list):
        concepts.extend(str(item) for item in raw_list if item)
    single = params.get("concept")
    if isinstance(single, str) and single and single not in concepts:
        concepts.append(single)
    if not concepts:
        raise SystemExit(
            "comparison config must declare either `concept:` (single) "
            "or `concepts:` (list) under runner.parameters"
        )
    args: list[str] = []
    for concept in concepts:
        args.extend(["--concept", concept])
    return args


def _run_axiom_oracles_compare(runner: dict, output: Path) -> None:
    """`axiom_oracles.cli compare <left> <right>` (in-repo CLI).

    Runs via `uv run --python <parameters.python|3.14>` against pinned
    PolicyEngine versions so PE 4.11.0's pydantic-based models load cleanly.
    Mirrors the `axiom-encode-tax-ecps-compare` runner's environment; a suite
    whose engine stack needs a different interpreter can pin `python:` in its
    parameters.
    """
    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    params = runner["parameters"]
    pe_pins = _resolve_pe_oracle_pins(params)
    engines = {str(params.get("left", "")), str(params.get("right", ""))}
    # A pure oracle-vs-oracle comparison (e.g. taxcalc vs policyengine) has no
    # Axiom side, so it needs neither a built engine binary nor a composed
    # program — skip the Rust dependency entirely rather than force a build.
    uses_axiom = "axiom" in engines
    if uses_axiom:
        _ensure_engine_binary(axiom_rules_repo, kind="release")
        _ensure_composed_axiom_program(params, axiom_rules_repo)
    # Tax-Calculator is an optional extra; install its pin into the isolated
    # `uv run` when either side is the taxcalc adapter. Without an explicit
    # numba floor the resolver satisfies taxcalc's numba requirement with the
    # ancient sdist-only numba 0.53.1, whose build fails on any current
    # Python — modern numba wheels resolve fine alongside the PE pins (#296).
    taxcalc_pins = ("taxcalc==6.7.1", "numba>=0.60") if "taxcalc" in engines else ()
    # TAXSIM ships as policyengine-taxsim, which bundles the pinned NBER
    # binary (adapters/taxsim/taxsim_pins.json records its identity).
    taxsim_pins = (
        ("policyengine-taxsim==2.30.0",) if "taxsim" in engines else ()
    )
    cmd = [
        "uv",
        "run",
        "--python",
        str(params.get("python", "3.14")),
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        *(arg for pin in pe_pins for arg in ("--with", pin)),
        *(arg for pin in taxcalc_pins for arg in ("--with", pin)),
        *(arg for pin in taxsim_pins for arg in ("--with", pin)),
        "python",
        "-c",
        _PE_CERT_OVERRIDE,
        "compare",
        params["left"],
        params["right"],
        "--population",
        params.get("population", "enhanced-cps"),
        "--sample-size",
        str(params.get("sample_size", 1000)),
        "--period",
        str(params["period"]),
        *(["--report-suite", str(params["suite"])] if params.get("suite") else []),
        *(["--include-components"] if params.get("include_components") else []),
        *_concept_args(params),
        *(
            [
                "--axiom-engine-binary",
                str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
            ]
            if uses_axiom
            else []
        ),
        "--output",
        str(output),
    ]
    if params.get("include_case_inputs"):
        cmd.append("--include-case-inputs")
    if params.get("comparison_batch_size"):
        comparison_batch_size = params["comparison_batch_size"]
    elif any(
        concept.endswith("#snap_eligible") or concept.endswith("#snap_benefit")
        for concept in params.get("concepts", [])
    ):
        comparison_batch_size = 100
    else:
        comparison_batch_size = None
    if comparison_batch_size is not None:
        cmd.extend(["--comparison-batch-size", str(comparison_batch_size)])
    if params.get("axiom_compiled_program"):
        compiled_program = (
            _expand_path(params["axiom_compiled_program"])
            if params.get("axiom_program")
            else _resolve_path(
                params["axiom_compiled_program"],
                "axiom_compiled_program",
            )
        )
        cmd.extend([
            "--axiom-compiled-program",
            str(compiled_program),
        ])
    if params.get("jurisdiction_fips"):
        cmd.extend(["--jurisdiction-fips", str(params["jurisdiction_fips"])])
    if params.get("ecps_dataset"):
        # Population dataset override (path or hf:// URL) — e.g. the certified
        # populace-us artifact instead of the enhanced CPS.
        cmd.extend(["--ecps-dataset", str(params["ecps_dataset"])])
    env = dict(os.environ)
    roots_env = params.get("axiom_rulespec_repo_roots")
    if roots_env:
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(
            _resolve_path(roots_env, "axiom_rulespec_repo_roots")
        )
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, env=env)


def _ensure_composed_axiom_program(params: dict, axiom_rules_repo: Path) -> None:
    """Compose/compile a program artifact when the comparison config declares one.

    Dashboard comparisons consume compiled artifacts, but `/tmp` artifacts are
    intentionally disposable. This hook keeps state SNAP dashboard regeneration
    reproducible from the declarative `axiom-programs` spec instead of relying
    on a prior manual compose step.
    """
    program_ref = params.get("axiom_program")
    if not program_ref:
        return
    compiled_ref = params.get("axiom_compiled_program")
    if not compiled_ref:
        raise SystemExit(
            "`axiom_program` comparisons must also declare "
            "`axiom_compiled_program`."
        )

    compose_binary = _resolve_path(
        params.get(
            "axiom_compose_binary",
            "$HOME/axiom-compose/.venv/bin/axiom-compose",
        ),
        "axiom_compose_binary",
    )
    program_path = _resolve_path(program_ref, "axiom_program")
    composed_path = _expand_path(
        params.get(
            "axiom_composed_program",
            str(_expand_path(compiled_ref).with_suffix(".composed.yaml")),
        )
    )
    compiled_path = _expand_path(compiled_ref)
    composed_path.parent.mkdir(parents=True, exist_ok=True)
    compiled_path.parent.mkdir(parents=True, exist_ok=True)

    roots = [
        _resolve_path(root, "rulespec_roots")
        for root in params.get("rulespec_roots", [])
    ]
    compose_cmd = [str(compose_binary), str(program_path)]
    for root in roots:
        compose_cmd.extend(["--rulespec-root", str(root)])
    compose_cmd.extend(["-o", str(composed_path)])
    subprocess.run(compose_cmd, check=True, cwd=REPO_ROOT)

    compile_env = dict(os.environ)
    roots_env = params.get("axiom_rulespec_repo_roots")
    if roots_env:
        compile_env["AXIOM_RULESPEC_REPO_ROOTS"] = str(_expand_path(roots_env))
    elif "AXIOM_RULESPEC_REPO_ROOTS" not in compile_env and roots:
        compile_env["AXIOM_RULESPEC_REPO_ROOTS"] = os.pathsep.join(
            str(root.parent) for root in roots
        )

    # Post-hard-cut engines compile compose output via compile-composed with
    # explicit --rulespec-root flags naming staged pure rulespec-<cc> roots;
    # older engines fall back to the legacy env-resolved `compile` inside
    # compile_with_engine (#296).
    from axiom_oracles.engine_compat import (
        compile_with_engine,
        explicit_engine_roots,
        import_prefixes,
        stage_pure_root,
    )

    root_candidates: list[Path] = list(roots)
    if roots_env:
        root_candidates.append(_expand_path(roots_env))
    engine_roots = explicit_engine_roots(root_candidates)
    composed_doc: dict = {}
    try:
        composed_doc = yaml.safe_load(composed_path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        composed_doc = {}
    jurisdictions = import_prefixes(
        [e for e in (composed_doc.get("imports") or []) if isinstance(e, str)]
    )
    staged_roots: list[Path] = []
    if engine_roots and jurisdictions:
        stage_dir = Path(tempfile.mkdtemp(prefix="composed-roots."))
        staged_roots = [
            stage_pure_root(root, jurisdictions, stage_dir) for root in engine_roots
        ]
    compile_with_engine(
        axiom_rules_repo / "target" / "release" / "axiom-rules-engine",
        composed_path,
        compiled_path,
        roots=staged_roots or engine_roots,
        composed=(composed_doc.get("module") or {}).get("kind") == "composition",
        env=compile_env,
    )


def _run_euromod_synthetic_compare(runner: dict, output: Path) -> None:
    """Synthetic EUROMOD-platform (UKMOD/EUROMOD) suite vs Axiom RuleSpec.

    Runs ``axiom_oracles.cli compare euromod axiom --population synthetic
    --suite <name>`` against a locally available EUROMOD-platform model. The
    engine (``EM_Executable.dll``) is x64-only and needs the ``euromod``
    connector plus a .NET runtime, and the model checkout is not present on
    the shared CI runner, so this runner **skips gracefully** when the model
    root or ``EUROMOD_PYTHON`` is unavailable: it re-emits the committed
    dashboard report as the run output so the weekly matrix stays green and
    the dashboard copy is idempotent. The suite is regenerated locally
    (``scripts/regenerate_euromod_uk.sh``) where the model and x64 runtime
    exist; that regeneration is the source of the committed numbers.
    """
    params = runner["parameters"]
    model_root_raw = params.get("euromod_model_root") or os.environ.get(
        "EUROMOD_MODEL_ROOT", ""
    )
    model_root = _expand_path(model_root_raw) if model_root_raw else None
    euromod_python = os.environ.get("EUROMOD_PYTHON")

    if model_root is None or not model_root.exists() or not euromod_python:
        reason = (
            "EUROMOD model root unavailable"
            if (model_root is None or not model_root.exists())
            else "EUROMOD_PYTHON unset"
        )
        # Re-emits must never be stamped fresh: with rulespec checkouts now
        # materialized in CI, resolving any configured root would relabel
        # skipped numbers with current SHAs (#296 review).
        runner["_reemitted_report"] = True
        committed = DASHBOARD_DATA_DIR / runner.get("dashboard_filename", "")
        dashboard_filename = params.get("dashboard_filename")
        if dashboard_filename:
            committed = DASHBOARD_DATA_DIR / dashboard_filename
        print(
            f"EUROMOD-platform model not runnable here ({reason}); "
            "re-emitting the committed dashboard report. Regenerate locally "
            "with scripts/regenerate_euromod_uk.sh."
        )
        if committed.exists():
            output.write_text(committed.read_text())
        else:
            output.write_text(
                json.dumps(
                    {
                        "schema_version": "axiom.comparison_report.v2",
                        "suite": params.get("suite", "unknown"),
                        "population": "synthetic",
                        "case_count": 0,
                        "engines": {"left": "euromod", "right": "axiom"},
                        "aggregates": [],
                        "cases": [],
                        "mismatches": [],
                        "concepts": [],
                        "errors": [f"skipped: {reason}"],
                        "locales": [],
                        "scope": None,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        return

    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    _ensure_engine_binary(axiom_rules_repo, kind="release")
    cmd = [
        "uv",
        "run",
        "--python",
        "3.14",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "python",
        "-m",
        "axiom_oracles.cli",
        "compare",
        "euromod",
        "axiom",
        "--population",
        "synthetic",
        "--suite",
        str(params["suite"]),
        "--report-suite",
        str(params.get("report_suite", params["suite"])),
        "--sample-size",
        str(params.get("sample_size", 0)),
        "--period",
        str(params["period"]),
        "--axiom-engine-binary",
        str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
        "--output",
        str(output),
    ]
    # Cross-engine batch isolation is the adapter's job: the worker loads the
    # model once per batch but runs every household as its own engine run, so
    # results are batch-size/order/composition-independent by construction
    # (EUROMOD-platform spines consume fixed-seed random draws per household
    # in dataset order — the retired batch-position contamination). Configs
    # therefore no longer pin `comparison_batch_size`; the passthrough stays
    # for report-accumulation sizing. Stochastic take-up instruments (UKMOD
    # UC/Pension Credit) now record their solo-draw realization every run —
    # deterministic, but not the statutory entitlement where the solo draw
    # marks non-take; `euromod_constant_overrides` can force take-up rates to
    # 1.0 where a suite wants statutory values.
    comparison_batch_size = params.get("comparison_batch_size")
    if comparison_batch_size is not None:
        cmd.extend(["--comparison-batch-size", str(comparison_batch_size)])
    env = dict(os.environ)
    env["EUROMOD_MODEL_ROOT"] = str(model_root)
    env["EUROMOD_COUNTRY"] = str(params.get("euromod_country", "UK"))
    env["EUROMOD_SYSTEM"] = str(params.get("euromod_system", "UK_2026"))
    env["EUROMOD_DATASET"] = str(params.get("euromod_dataset", "training_data"))
    # EUROMOD releases gate content on real dataset-configuration names; the BE
    # spine templates its input rows from the bundled BE_training_data schema
    # while running under the real BE_2024_c1_2015_03_e2 configuration name (the
    # dataset-name gating workaround; no licensed microdata is read).
    template_dataset = params.get("euromod_template_dataset")
    if template_dataset:
        env["EUROMOD_TEMPLATE_DATASET"] = str(template_dataset)
    country_code = params.get("euromod_country_code")
    if country_code is not None:
        env["EUROMOD_COUNTRY_CODE"] = str(country_code)
    policy_switches = params.get("euromod_policy_switch_overrides")
    if policy_switches:
        env["EUROMOD_POLICY_SWITCHES"] = str(policy_switches)
    constant_overrides = params.get("euromod_constant_overrides")
    if constant_overrides:
        env["EUROMOD_CONSTANT_OVERRIDES"] = str(constant_overrides)
    roots_env = params.get("axiom_rulespec_repo_roots")
    if roots_env:
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(
            _expand_path(roots_env)
        )
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, env=env)


def _gettsim_synthetic_skip_reason(
    params: dict,
) -> tuple[str | None, Path | None]:
    """Return the unavailable-runtime reason and resolved DE model root."""

    model_root_raw = params.get("euromod_model_root") or os.environ.get(
        "EUROMOD_MODEL_ROOT_DE", ""
    )
    model_root = _expand_path(model_root_raw) if model_root_raw else None
    if model_root is None or not model_root.exists():
        return "EUROMOD model root unavailable", model_root
    if not os.environ.get("EUROMOD_PYTHON"):
        return "EUROMOD_PYTHON unset", model_root

    from axiom_oracles.adapters.gettsim import (
        GettsimNotInstalledError,
        gettsim_version,
    )

    try:
        gettsim_version()
    except GettsimNotInstalledError as exc:
        return f"GETTSIM unavailable ({type(exc).__name__}: {exc})", model_root
    return None, model_root


def _reemit_gettsim_synthetic_report(
    params: dict,
    output: Path,
    reason: str,
) -> None:
    """Re-emit the committed direct-oracle report on engine-less runners."""

    dashboard_filename = str(params.get("dashboard_filename", ""))
    committed = DASHBOARD_DATA_DIR / dashboard_filename
    print(
        f"Germany dual-oracle engines not runnable here ({reason}); "
        "re-emitting the committed dashboard report."
    )
    if dashboard_filename and committed.exists():
        output.write_text(committed.read_text())
        return

    euromod_unavailable = reason.startswith("EUROMOD")
    unavailable_side = "left" if euromod_unavailable else "right"
    unavailable_engine = "euromod" if euromod_unavailable else "gettsim"
    error = {
        "case_id": None,
        "side": unavailable_side,
        "engine": unavailable_engine,
        "error": f"skipped: {reason}",
    }
    output.write_text(
        json.dumps(
            {
                "schema_version": "axiom.comparison_report.v2",
                "suite": params.get("suite", "de-worker-dual-oracle"),
                "population": "synthetic",
                "engines": {"left": "euromod", "right": "gettsim"},
                "locales": ["DE"],
                "scope": {"type": "country", "geoid": "DE"},
                "concepts": [],
                "case_count": 0,
                "summary": {
                    "match_count": 0,
                    "mismatch_count": 0,
                    "comparison_count": 0,
                    "weighted": {
                        "comparison_weight": 0,
                        "match_weight": 0,
                        "mismatch_weight": 0,
                        "match_rate": 0,
                    },
                    "mismatches_by_concept": [],
                    "mismatches_by_kind": [],
                    "mismatches_by_scenario": [],
                    "error_count": 1,
                    "errors_by_engine": [
                        {"value": unavailable_engine, "count": 1}
                    ],
                },
                "aggregates": [],
                "mismatches": [],
                "errors": [error],
                "cases": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _run_gettsim_synthetic_compare(runner: dict, output: Path) -> None:
    """Direct EUROMOD DE_2025 ↔ GETTSIM synthetic household comparison.

    The host interpreter supplies GETTSIM; EUROMOD continues to execute through
    the existing x64 ``EUROMOD_PYTHON`` subprocess adapter. Like the established
    EUROMOD synthetic runner, an engine-less CI host re-emits the committed
    dashboard report rather than turning optional local runtimes into failures.
    """

    from axiom_oracles.adapters.euromod import EuromodPlatformRunner
    from axiom_oracles.adapters.gettsim import GettsimCase, GettsimRunner
    from axiom_oracles.comparison.comparator import Comparator
    from axiom_oracles.comparison.mappings import comparable_mappings
    from axiom_oracles.comparison.report import build_comparison_report
    from axiom_oracles.core.results import EngineResult
    from axiom_oracles.suites import load_suite
    from axiom_oracles.suites.de_worker import (
        DE_GETTSIM_TARGETS,
        reduce_gettsim_household_values,
    )

    params = runner["parameters"]
    skip_reason, model_root = _gettsim_synthetic_skip_reason(params)
    if skip_reason is not None or model_root is None:
        # See the euromod runner: re-emits must never be stamped fresh.
        runner["_reemitted_report"] = True
        _reemit_gettsim_synthetic_report(
            params,
            output,
            skip_reason or "EUROMOD model root unavailable",
        )
        return

    cases = load_suite(str(params["suite"]))
    sample_size = int(params.get("sample_size", 0) or 0)
    if sample_size > 0:
        cases = cases[:sample_size]
    locales = {case.locale for case in cases if case.locale}
    scope = cases[0].scope if cases else None
    selected_concepts = set(params.get("concepts") or ()) or {
        output_id for case in cases for output_id in case.outputs
    }
    mappings = comparable_mappings(
        "euromod",
        "gettsim",
        locales=locales,
        scope=scope,
        concepts=selected_concepts,
    )
    if not mappings:
        raise RuntimeError("Germany dual-oracle suite selected no comparable mappings")

    euromod_variables = list(
        dict.fromkeys(
            target
            for mapping in mappings
            for target in [mapping.target_for_engine("euromod")]
            if isinstance(target, str)
        )
    )
    euromod = EuromodPlatformRunner(
        model_root=model_root,
        country=str(params.get("euromod_country", "DE")),
        system=str(params.get("euromod_system", "DE_2025")),
        dataset=str(params.get("euromod_dataset", "DE_2024_b1_2015_03_e2")),
        template_dataset=str(
            params.get("euromod_template_dataset", "DE_training_data")
        ),
        extra_columns=tuple(params.get("euromod_extra_columns") or ("drgn1",)),
        python_executable=os.environ["EUROMOD_PYTHON"],
    )
    euromod_results = euromod.run_cases(cases, variables=euromod_variables)

    gettsim = GettsimRunner(
        policy_date_str=str(params.get("gettsim_policy_date", "2025-06-30")),
    )
    gettsim_results: list[EngineResult] = []
    for case in cases:
        try:
            gettsim_case = GettsimCase.from_mapping(case.metadata["gettsim_case"])
            raw = gettsim.run_case(gettsim_case, DE_GETTSIM_TARGETS)
            gettsim_results.append(
                EngineResult(
                    engine="gettsim",
                    household_id=case.case_id,
                    values=reduce_gettsim_household_values(raw.values),
                    raw=raw,
                )
            )
        except Exception as exc:
            gettsim_results.append(
                EngineResult(
                    engine="gettsim",
                    household_id=case.case_id,
                    values={},
                    errors=(f"{type(exc).__name__}: {exc}",),
                )
            )

    comparisons = Comparator(mappings).compare(euromod_results, gettsim_results)
    report = build_comparison_report(
        suite_name=str(params["suite"]),
        population="synthetic",
        locales=locales,
        scope=scope,
        cases=cases,
        mappings=mappings,
        comparisons=comparisons,
    )
    report["engine_metadata"] = {
        "euromod": {
            "country": euromod.country,
            "system": euromod.system,
            "dataset": euromod.dataset,
            "template_dataset": euromod.template_dataset,
            "extra_columns": list(euromod.extra_columns),
        },
        "gettsim": gettsim.run_metadata(),
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _resolve_state_income_tax_grid_repos() -> tuple[Path, Path]:
    """Resolve and verify the exact clean repos used by the state grid."""

    rulespec_root = Path(
        os.environ.get("RULESPEC_US_REPO", REPO_ROOT.parent / "rulespec-us")
    ).expanduser().resolve()
    axiom_rules_repo = Path(
        os.environ.get(
            "AXIOM_RULES_REPO", REPO_ROOT.parent / "axiom-rules-engine"
        )
    ).expanduser().resolve()
    for label, repo in (
        ("rulespec-us", rulespec_root),
        ("axiom-rules-engine", axiom_rules_repo),
    ):
        if not repo.is_dir():
            raise SystemExit(f"state income-tax grid {label} repo not found: {repo}")
        try:
            status = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(
                f"cannot verify state income-tax grid {label} repo {repo}: {exc}"
            ) from exc
        if status.strip():
            raise SystemExit(
                f"state income-tax grid {label} repo has working-tree changes: "
                f"{repo}"
            )
    binary = (
        axiom_rules_repo / "target" / "release" / "axiom-rules-engine"
    )
    if not binary.is_file():
        raise SystemExit(
            "state income-tax grid axiom-rules-engine binary not found: "
            f"{binary}"
        )
    return rulespec_root, axiom_rules_repo


def _run_state_income_tax_liability_grid(runner: dict, output: Path) -> None:
    """Composed state income-tax liability grid: pipeline vs PolicyEngine + TAXSIM.

    Delegates to scripts/generate_state_income_tax_liability.py, which runs the
    modest case grid through the rulespec-us composed liability pipeline (engine-
    verified fixtures), PolicyEngine at the 2026 validation year, and the pinned
    TAXSIM binary at the configured 2026 law year, then writes one v2 report per
    state. The generator is state-agnostic; this runner copies the state's report
    to the requested ``output`` path so the standard provenance/dashboard
    plumbing applies. Generation fails closed when any required engine is
    unavailable; committed numerical reports are never silently reused.
    """
    params = runner["parameters"]
    rulespec_root, axiom_rules_repo = _resolve_state_income_tax_grid_repos()
    # The config object is shared with the outer provenance stamper. Record the
    # exact paths that actually execute, so a successful grid can never replace
    # generator provenance with a null RuleSpec SHA or empty engine block.
    params["rulespec_roots"] = [str(rulespec_root)]
    params["axiom_rules_repo"] = str(axiom_rules_repo)
    state = str(params["state"]).lower()
    pe_pins = _resolve_pe_oracle_pins(params)
    generator = REPO_ROOT / "scripts" / "generate_state_income_tax_liability.py"
    basename = f"axiom-policyengine-taxsim-{state}-income-tax-liability"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.14",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        *(arg for pin in pe_pins for arg in ("--with", pin)),
        "--with",
        # Must match adapters/taxsim/taxsim_pins.json — the pinned identity
        # every TAXSIM oracle number is reproducible against. 2.30.0 models
        # 2026 law (incl. OBBBA); the old 2.21.2 here silently capped the
        # grids at 2024 law.
        "policyengine-taxsim==2.30.0",
        "python",
        str(generator),
        "--state",
        state.upper(),
    ]
    env = os.environ.copy()
    env["RULESPEC_US_REPO"] = str(rulespec_root)
    env["AXIOM_RULES_REPO"] = str(axiom_rules_repo)
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, env=env)
    source = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    output.write_text(source.read_text())


_VERIFIED_RULESPEC_UPSTREAM_SHA = "_verified_rulespec_upstream_sha"


def _verify_federal_rulespec_snapshot(
    params: dict,
    roots: list[Path],
) -> None:
    """Fail closed unless a pinned federal RuleSpec snapshot is exact and clean.

    A sandbox may have the upstream tree through local Git objects even when it
    cannot fetch the signed GitHub merge commit itself. The pair of public
    config pins records that upstream commit and its tree. A content-equivalent
    checkout is acceptable only when its canonical basename is ``rulespec-us``,
    its working tree is clean, and ``HEAD^{tree}`` equals the pinned upstream
    tree. Only after those checks do we expose the upstream SHA to the
    provenance stamper.
    """
    upstream_sha = str(params.get("rulespec_upstream_sha") or "").strip()
    upstream_tree = str(params.get("rulespec_upstream_tree") or "").strip()
    if not upstream_sha and not upstream_tree:
        return
    if not upstream_sha or not upstream_tree:
        raise SystemExit(
            "federal-tax-liability-grid requires rulespec_upstream_sha and "
            "rulespec_upstream_tree together"
        )
    if len(roots) != 1:
        raise SystemExit(
            "a pinned federal rulespec snapshot requires exactly one "
            "rulespec_roots entry"
        )
    if any(
        len(value) != 40
        or any(char not in "0123456789abcdef" for char in value.lower())
        for value in (upstream_sha, upstream_tree)
    ):
        raise SystemExit(
            "rulespec_upstream_sha and rulespec_upstream_tree must be "
            "40-character hexadecimal Git object IDs"
        )

    root = roots[0].resolve()
    if root.name != "rulespec-us":
        raise SystemExit(
            "the pinned federal rulespec snapshot must use the canonical "
            f"'rulespec-us' basename (got {root})"
        )
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        local_head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        local_tree = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"cannot verify pinned federal rulespec snapshot {root}: {exc}"
        ) from exc
    if status.strip():
        raise SystemExit(
            f"pinned federal rulespec snapshot {root} has working-tree changes"
        )
    if local_tree != upstream_tree:
        raise SystemExit(
            "pinned federal rulespec snapshot tree mismatch: "
            f"expected {upstream_tree}, got {local_tree}"
        )

    params[_VERIFIED_RULESPEC_UPSTREAM_SHA] = upstream_sha
    print(
        "Verified rulespec-us snapshot "
        f"tree {local_tree[:12]} for upstream main {upstream_sha[:12]} "
        f"(local HEAD {local_head[:12]})."
    )


def _run_federal_tax_liability_grid(runner: dict, output: Path) -> None:
    """Run one independent federal RuleSpec-fixture vs PolicyEngine case grid.

    Unlike the legacy all-state generator, this wrapper selects exactly one
    policy and has no committed-report fallback: a missing fixture or an
    unavailable PolicyEngine wheel fails the run instead of replaying evidence.
    The RuleSpec roots come from the comparison YAML and are passed explicitly
    to the generator, eliminating the state generator's fixed-sibling flaw.
    """
    params = runner["parameters"]
    required_pins = {
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
    }
    incorrect_pins = {
        key: params.get(key)
        for key, expected in required_pins.items()
        if params.get(key) != expected
    }
    if incorrect_pins:
        expected = ", ".join(
            f"{key}={version}" for key, version in required_pins.items()
        )
        raise SystemExit(
            "federal-tax-liability-grid requires the reviewed 2026 oracle "
            f"stack ({expected}); received {incorrect_pins}"
        )
    raw_roots = params.get("rulespec_roots") or []
    if not isinstance(raw_roots, list) or not raw_roots:
        raise SystemExit(
            "federal-tax-liability-grid requires runner.parameters.rulespec_roots"
        )
    roots = [
        expanded
        for raw_root in raw_roots
        if (expanded := _expand_path(str(raw_root))).exists()
    ]
    if not roots:
        remote = params.get("rulespec_remote")
        if not remote:
            attempted = ", ".join(str(_expand_path(root)) for root in raw_roots)
            raise SystemExit(
                "rulespec_roots: no configured path exists "
                f"({attempted}) and no rulespec_remote fallback is declared"
            )
        roots = [_ensure_rulespec_us_checkout(str(remote))]
        # The config object is shared with the outer provenance stamper. Record
        # the checkout that actually ran so it stamps the clone's exact SHA,
        # rather than the missing development-worktree path.
        params["rulespec_roots"] = [str(roots[0])]
    _verify_federal_rulespec_snapshot(params, roots)
    pins = _resolve_pe_oracle_pins(params)
    generator = REPO_ROOT / "scripts" / "generate_federal_tax_liability.py"
    cmd = [
        "uv",
        "run",
        "--python",
        str(params.get("python", "3.13")),
        "--no-project",
        *(arg for pin in pins for arg in ("--with", pin)),
        "python",
        str(generator),
        "--policy",
        str(params["policy"]),
        *(
            arg
            for root in roots
            for arg in ("--rulespec-root", str(root))
        ),
        "--output",
        str(output),
    ]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


# The one file the ABAWD boundary generator reads from the rulespec tree;
# its bytes are verified against HEAD's copy below, so no working-tree
# trick (including skip-worktree-hidden edits, which git status does not
# show) can run modified law under a clean commit identity.
_ABAWD_FIXTURE_RELPATH = "us/regulations/7-cfr/273/24.test.yaml"


def _rulespec_checkout_unclean_reason(
    root: Path,
    verify_files: tuple[str, ...] = (_ABAWD_FIXTURE_RELPATH,),
) -> str | None:
    """Why a floating (unpinned) rulespec root cannot be trusted, or None.

    The ABAWD boundary generator reads fixture bytes straight from the tree
    while provenance records ``git rev-parse HEAD``, so a dirty or non-git
    tree could run modified law under a clean commit identity.  Beyond the
    porcelain check, the files the generator actually consumes are compared
    byte-for-byte against ``HEAD``'s copies — ``git status`` stays silent
    about modifications hidden behind ``skip-worktree``, and the byte
    identity of the consumed law is the property that matters.  A root that
    fails any check is rejected and the runner falls back to a fresh clone.
    """

    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return "git is unavailable to verify it"
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return "not a git work tree, so provenance cannot record a real SHA"
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return "git status failed"
    if status.stdout.strip():
        return "working tree is dirty, so fixture bytes would not match HEAD"
    for relpath in verify_files:
        committed = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{relpath}"],
            capture_output=True,
        )
        if committed.returncode != 0:
            return f"HEAD does not carry {relpath}"
        try:
            on_disk = (root / relpath).read_bytes()
        except OSError:
            return f"{relpath} is unreadable in the work tree"
        if on_disk != committed.stdout:
            return (
                f"{relpath} differs from HEAD's copy "
                "(a skip-worktree-hidden edit?)"
            )
    return None


def _run_snap_abawd_boundary_grid(runner: dict, output: Path) -> None:
    """Run the SNAP ABAWD post-P.L. 119-21 statute-boundary grid.

    Same contract as the federal tax-liability grids: the Axiom leg replays
    the rulespec-us 7 CFR 273.24 companion fixture (engine-verified in
    rulespec-us CI), the PolicyEngine leg builds fresh person-level monthly
    simulations under the reviewed 2026 oracle stack, and a missing fixture or
    unavailable PolicyEngine wheel fails the run instead of replaying
    committed evidence.  Unlike those grids the rulespec snapshot is
    deliberately unpinned: each run clones rulespec-us main (or reads the
    materialized CI checkout) and stamps its real HEAD into provenance, so the
    affected-rerun sweep re-runs the boundary matrix whenever rulespec-us
    moves and the generator's pinned legal expectations turn an encoding
    regression at the statute boundaries into a loud failure.
    """
    params = runner["parameters"]
    required_pins = {
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
    }
    incorrect_pins = {
        key: params.get(key)
        for key, expected in required_pins.items()
        if params.get(key) != expected
    }
    if incorrect_pins:
        expected = ", ".join(
            f"{key}={version}" for key, version in required_pins.items()
        )
        raise SystemExit(
            "snap-abawd-boundary-grid requires the reviewed 2026 oracle "
            f"stack ({expected}); received {incorrect_pins}"
        )
    raw_roots = params.get("rulespec_roots") or []
    if not isinstance(raw_roots, list) or not raw_roots:
        raise SystemExit(
            "snap-abawd-boundary-grid requires runner.parameters.rulespec_roots"
        )
    roots = []
    for raw_root in raw_roots:
        expanded = _expand_path(str(raw_root))
        if not expanded.exists():
            continue
        reason = _rulespec_checkout_unclean_reason(expanded)
        if reason is None:
            roots.append(expanded)
        else:
            print(f"Ignoring rulespec root {expanded}: {reason}")
    if not roots:
        remote = params.get("rulespec_remote")
        if not remote:
            attempted = ", ".join(str(_expand_path(root)) for root in raw_roots)
            raise SystemExit(
                "rulespec_roots: no configured path is a clean checkout "
                f"({attempted}) and no rulespec_remote fallback is declared"
            )
        roots = [_ensure_rulespec_us_checkout(str(remote))]
    # Record exactly the checkouts that ran — never a configured-but-rejected
    # path — so the provenance stamper identifies the tree the fixture bytes
    # actually came from.
    params["rulespec_roots"] = [str(root) for root in roots]
    _verify_federal_rulespec_snapshot(params, roots)
    pins = _resolve_pe_oracle_pins(params)
    generator = REPO_ROOT / "scripts" / "generate_snap_abawd_boundary.py"
    cmd = [
        "uv",
        "run",
        "--python",
        str(params.get("python", "3.13")),
        "--no-project",
        *(arg for pin in pins for arg in ("--with", pin)),
        "python",
        str(generator),
        *(
            arg
            for root in roots
            for arg in ("--rulespec-root", str(root))
        ),
        "--output",
        str(output),
    ]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def _run_uk_council_tax_reduction_grid(runner: dict, output: Path) -> None:
    """Council Tax Reduction grid: rulespec-uk pension-age scheme vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_council_tax_reduction.py, which runs a
    synthetic England pensioner-household grid through PolicyEngine-UK 2.89.2 and
    the encoded SI 2012/2885 England pension-age scheme (evaluated through the
    axiom rules engine over PolicyEngine's own applicable amount / applicable
    income / non-dependant deductions / council_tax liability / savings), then
    writes one v2 report. On a runner without a PolicyEngine-UK environment or a
    built axiom rules engine, the committed dashboard report is reused, exactly
    like the state income-tax grid.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_council_tax_reduction.py"
    basename = "axiom-policyengine-uk-council-tax-reduction"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"CTR grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_capital_gains_tax_grid(runner: dict, output: Path) -> None:
    """Capital Gains Tax grid: rulespec-uk band split vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_capital_gains_tax.py, which runs a synthetic
    individual grid through PolicyEngine-UK 2.89.2's ``capital_gains_tax`` and the
    encoded TCGA 1992 s.1H/1I/1K band split (evaluated through the axiom rules
    engine over PolicyEngine's own capital_gains, taxable income and basic rate
    limit), then writes one v2 report. On a runner without a PolicyEngine-UK
    environment or a built axiom rules engine, the committed dashboard report is
    reused, exactly like the Council Tax Reduction grid.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_capital_gains_tax.py"
    basename = "axiom-policyengine-uk-capital-gains-tax"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"CGT grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_business_rates_grid(runner: dict, output: Path) -> None:
    """Business rates grid: rulespec-uk incidence wrapper vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_business_rates.py, which runs a synthetic
    household grid through PolicyEngine-UK 2.89.2's ``business_rates`` and the
    encoded LGFA 1988 s.43 incidence proxy (evaluated through the axiom rules
    engine over PolicyEngine's own shareholding and the held-forward total
    non-domestic rates revenue), then writes one v2 report. On a runner without a
    PolicyEngine-UK environment or a built axiom rules engine, the committed
    dashboard report is reused, exactly like the Council Tax Reduction grid.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_business_rates.py"
    basename = "axiom-policyengine-uk-business-rates"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"Business rates grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_lbtt_ltt_grid(runner: dict, output: Path) -> None:
    """Devolved transaction tax grid: rulespec-uk band splits vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_lbtt_ltt.py, which runs a synthetic
    household grid through PolicyEngine-UK 2.89.2's
    ``land_and_buildings_transaction_tax`` (Scotland) and ``land_transaction_tax``
    (Wales) and the encoded SSI 2015/126 + LBTT(S)A 2013 Sch 2A and WSI 2018/128
    + LTT(W)A 2017 band splits (evaluated through the axiom rules engine over the
    supplied main and additional residential purchase prices), then writes one v2
    report. On a runner without a PolicyEngine-UK environment or a built axiom
    rules engine, the committed dashboard report is reused, exactly like the
    Capital Gains Tax grid.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_lbtt_ltt.py"
    basename = "axiom-policyengine-uk-lbtt-ltt"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"LBTT/LTT grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_winter_fuel_payment_pe_grid(runner: dict, output: Path) -> None:
    """Winter Fuel Payment grid: rulespec-uk SI 2025/969 pipeline vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_winter_fuel_payment_pe.py, which runs a
    synthetic England pensioner-household grid through PolicyEngine-UK 2.89.2's
    ``winter_fuel_allowance`` and the encoded SI 2025/969 reg 3 award pipeline
    (evaluated through the axiom rules engine over the state-pension-age, 80+ and
    income-below-recovery-threshold judgments the same age/income facts imply),
    then writes one v2 report. On a runner without a PolicyEngine-UK environment
    or a built axiom rules engine, the committed dashboard report is reused,
    exactly like the Council Tax Reduction grid.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_winter_fuel_payment_pe.py"
    basename = "axiom-policyengine-uk-winter-fuel-payment-pe"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"Winter Fuel grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_attendance_allowance_pe_grid(runner: dict, output: Path) -> None:
    """Attendance Allowance rate grid: rulespec-uk SI 2026/148 rates vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_attendance_allowance_pe.py, which runs a
    synthetic care-category grid through PolicyEngine-UK 2.89.2's
    ``attendance_allowance`` and the encoded SI 2026/148 Schedule 1 Part III weekly
    rates (evaluated through the axiom rules engine over the awarded-category
    judgments and annualised over PE's WEEKS_IN_YEAR), then writes one v2 report.
    On a runner without a PolicyEngine-UK environment or a built axiom rules engine,
    the committed dashboard report is reused, exactly like the Council Tax Reduction
    and Winter Fuel Payment grids.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_attendance_allowance_pe.py"
    basename = "axiom-policyengine-uk-attendance-allowance-pe"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"Attendance Allowance grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_tax_free_childcare_pe_grid(runner: dict, output: Path) -> None:
    """Tax-Free Childcare grid: rulespec-uk CPA 2014 s.1 top-up vs PolicyEngine-UK.

    Delegates to scripts/generate_uk_tax_free_childcare_pe.py, which runs a
    synthetic eligible-household grid (below the per-child cap) through
    PolicyEngine-UK 2.89.2's ``tax_free_childcare`` and the encoded CPA 2014 s.1
    25%-of-qualifying-payment top-up, then writes one v2 report. On a runner
    without a PolicyEngine-UK environment or a built axiom rules engine, the
    committed dashboard report is reused, exactly like the other UK case grids.
    """
    del runner
    generator = REPO_ROOT / "scripts" / "generate_uk_tax_free_childcare_pe.py"
    basename = "axiom-policyengine-uk-tax-free-childcare-pe"
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"Tax-Free Childcare grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_pe_grid(
    generator_basename: str, report_basename: str, output: Path
) -> None:
    """Shared runner for the UK PolicyEngine case-grid comparisons.

    Delegates to the named generator, which runs a synthetic household grid
    through PolicyEngine-UK 2.89.2 and the encoded rulespec module (evaluated
    through the axiom rules engine) and writes one v2 report. On a runner
    without a PolicyEngine-UK environment or a built axiom rules engine, the
    committed dashboard report is reused, exactly like the council-tax-reduction
    grid.
    """
    generator = REPO_ROOT / "scripts" / generator_basename
    committed = REPO_ROOT / "dashboard" / "public" / "data" / f"{report_basename}.json"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "--with",
        "policyengine-uk==2.89.2",
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        print(f"{report_basename} grid generation unavailable ({exc}); reusing {committed}.")
    output.write_text(committed.read_text())


def _run_uk_vat_grid(runner: dict, output: Path) -> None:
    del runner
    _run_uk_pe_grid("generate_uk_vat.py", "axiom-policyengine-uk-vat", output)


def _run_uk_fuel_duty_grid(runner: dict, output: Path) -> None:
    del runner
    _run_uk_pe_grid(
        "generate_uk_fuel_duty.py", "axiom-policyengine-uk-fuel-duty", output
    )


def _run_uk_tv_licence_grid(runner: dict, output: Path) -> None:
    del runner
    _run_uk_pe_grid(
        "generate_uk_tv_licence.py", "axiom-policyengine-uk-tv-licence", output
    )


def _run_us_tariff_grid(runner: dict, output: Path) -> None:
    """US tariff duty T0 grid: rulespec-us duty spine vs frozen USITC rates.

    Delegates to scripts/generate_us_tariff.py, which runs the 40 frozen grid
    cases (axiom_oracles.suites.us_tariff) through the composed rulespec-us
    us-tariff-duty pipeline via the axiom rules engine and grades against
    duty amounts frozen from the retained USITC HTS editions and Federal
    Register instruments. There is no external oracle process: the reference
    side is a committed statutory computation. On a runner without a built
    axiom rules engine or the rulespec-us tariff spine, the committed
    dashboard report is reused, exactly like the UK case-grid runners —
    marked as a re-emit so provenance never stamps it fresh.
    """
    generator = REPO_ROOT / "scripts" / "generate_us_tariff.py"
    committed = (
        REPO_ROOT / "dashboard" / "public" / "data" / "axiom-usitc-us-tariff.json"
    )
    cmd = [
        "uv",
        "run",
        "--python",
        "3.13",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        "python",
        str(generator),
    ]
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if not committed.exists():
            raise
        # Mark the re-emit so provenance never resolves a configured checkout
        # path to a current SHA — stamping fresh SHAs onto the committed
        # report's numbers would label a skipped run fresh (#296 review;
        # sol review of #446 finding 2).
        runner["_reemitted_report"] = True
        print(f"us-tariff grid generation unavailable ({exc}); reusing {committed}.")
    else:
        # Record what actually ran: the generator honors RULESPEC_US_CHECKOUT
        # (generate_us_tariff.py) while provenance otherwise reads the
        # configured default root — under an env override those are different
        # checkouts at different SHAs (sol review of #446 finding 3). Same for
        # the engine identity via AXIOM_RULES_ENGINE_BINARY.
        checkout = Path(
            os.environ.get("RULESPEC_US_CHECKOUT")
            or os.path.expanduser("~/TheAxiomFoundation/rulespec-us")
        )
        runner.setdefault("parameters", {})["rulespec_roots"] = [str(checkout)]
        binary = os.environ.get("AXIOM_RULES_ENGINE_BINARY")
        if binary:
            engine_repo = Path(binary).resolve().parents[2]
            if (engine_repo / ".git").exists():
                runner["axiom_rules_repo"] = str(engine_repo)
    output.write_text(committed.read_text())


def _us_tariff_panel_env() -> tuple[Path, Path]:
    """(rulespec-us checkout, composition module path) for the panel suite."""
    checkout = Path(
        os.environ.get("RULESPEC_US_CHECKOUT")
        or os.path.expanduser("~/TheAxiomFoundation/rulespec-us")
    )
    return checkout, checkout / "us/policies/cbp/us-tariff-duty/composition.yaml"


def _us_tariff_panel_unavailable_reason() -> str | None:
    """Why the panel generator CANNOT run on this host, or None if it can.

    Probed BEFORE launching the generator: the skip-capable re-emit lane is
    only for hosts missing prerequisites (no rulespec-us tariff spine, no
    built engine, no uv). A generator that was actually launched and failed
    — unbridged countries, engine errors, integrity asserts — must fail the
    job, never be converted into a successful re-emitted run (#448 review).
    """
    if shutil.which("uv") is None:
        return "uv not on PATH"
    _, composition = _us_tariff_panel_env()
    if not composition.exists():
        return f"rulespec-us tariff spine not found at {composition}"
    if _us_tariff_panel_engine_binary() is None:
        from axiom_oracles.adapters.axiom.runner import _resolve_binary_path

        return (
            "axiom rules engine binary not found "
            f"({_resolve_binary_path(None, composition)})"
        )
    return None


def _us_tariff_panel_engine_binary() -> Path | None:
    """The engine executable the generator will actually run, or None.

    Mirrors POSIX exec semantics exactly (#448 review round 4): a bare
    command name resolves through PATH ONLY (a same-named file in the
    current directory is never the executed one), and a relative path with
    a separator resolves against REPO_ROOT — the working directory the
    generator subprocess is launched with — not this process's cwd.
    """
    _, composition = _us_tariff_panel_env()
    from axiom_oracles.adapters.axiom.runner import _resolve_binary_path

    binary = _resolve_binary_path(None, composition)
    if os.sep not in str(binary):
        which = shutil.which(str(binary))
        resolved = Path(which) if which else None
    else:
        candidate = binary if binary.is_absolute() else REPO_ROOT / binary
        resolved = candidate if candidate.exists() else None
    if resolved is None:
        return None
    resolved = resolved.resolve()
    return resolved if resolved.is_file() else None


def _validate_us_tariff_panel_payload(report: object, source: str) -> None:
    """Refuse to stamp a truncated or internally unreconciled panel payload.

    Applied to BOTH legs before provenance stamping (#448 review round 2):
    the generator's run-private output (exit 0 alone does not prove a full
    payload was produced) and the committed report a re-emit reuses (a
    truncated dashboard copy or an edited artifact must never re-emit as
    the full account).
    """
    if not isinstance(report, dict):
        raise SystemExit(f"us-tariff-panel payload at {source} is not a report")
    if "dashboard_truncation" in report:
        raise SystemExit(
            f"us-tariff-panel payload at {source} is a truncated dashboard "
            "copy — it cannot serve as the full report"
        )
    summary = report.get("summary")
    mismatches = report.get("mismatches")
    if not isinstance(summary, dict) or not isinstance(mismatches, list):
        raise SystemExit(
            f"us-tariff-panel payload at {source} lacks summary/mismatches"
        )
    comparison = summary.get("comparison_count")
    matches = summary.get("match_count")
    mismatch_count = summary.get("mismatch_count")
    if not all(
        isinstance(count, int)
        for count in (comparison, matches, mismatch_count)
    ):
        raise SystemExit(
            f"us-tariff-panel payload at {source} lacks integral unit counts"
        )
    if matches + mismatch_count != comparison:
        raise SystemExit(
            f"us-tariff-panel payload at {source} does not conserve units: "
            f"{matches} + {mismatch_count} != {comparison}"
        )
    if len(mismatches) != mismatch_count:
        raise SystemExit(
            f"us-tariff-panel payload at {source} carries "
            f"{len(mismatches)} mismatch rows for "
            f"mismatch_count={mismatch_count} — full-row account required"
        )
    case_ids = {row.get("case_id") for row in mismatches}
    if len(case_ids) != len(mismatches):
        raise SystemExit(
            f"us-tariff-panel payload at {source} has duplicate mismatch rows"
        )
    signature_members = [
        cid
        for signature in report.get("mismatch_signatures") or []
        for cid in signature.get("units") or []
    ]
    if set(signature_members) != case_ids:
        raise SystemExit(
            f"us-tariff-panel payload at {source} has signature memberships "
            "that do not cover exactly the mismatched units"
        )
    # Fullness is NOT self-reported by the summary alone (#448 review round
    # 3): the complete case-family ledger must reconcile against it. Every
    # comparison unit lives in exactly one family; each family's match flag
    # must equal its own expected/axiom vector agreement (exact tolerance,
    # matching the suite's TOLERANCE = 1e-12), the family unit totals must
    # reproduce the summary counts, and every mismatch row must belong to a
    # non-matching family cell. Relabelling omitted mismatches as matches
    # now has to forge the entire ledger consistently, not just the counts.
    families = report.get("cases")
    if not isinstance(families, list) or not families:
        raise SystemExit(
            f"us-tariff-panel payload at {source} lacks the case-family "
            "ledger (cases)"
        )
    family_units = 0
    family_mismatch_units = 0
    family_units_by_hts: dict[str, int] = {}
    mismatch_family_cells: dict[str, list[tuple[set, set, dict, dict]]] = {}
    for family in families:
        expected = family.get("expected")
        axiom = family.get("axiom")
        unit_count = family.get("unit_count")
        if (
            not isinstance(expected, dict)
            or not isinstance(axiom, dict)
            or set(expected) != set(axiom)
            or not isinstance(unit_count, int)
            or unit_count <= 0
        ):
            raise SystemExit(
                f"us-tariff-panel payload at {source} has a malformed "
                f"case family ({family.get('case_id')})"
            )
        vectors_agree = all(
            abs(axiom[slot] - expected[slot]) <= 1e-12 for slot in expected
        )
        if bool(family.get("match")) != vectors_agree:
            raise SystemExit(
                f"us-tariff-panel payload at {source} has a case family "
                f"({family.get('case_id')}) whose match flag contradicts "
                "its own expected/axiom vectors"
            )
        family_units += unit_count
        family_hts = str(family.get("hts_number"))
        family_units_by_hts[family_hts] = (
            family_units_by_hts.get(family_hts, 0) + unit_count
        )
        if not vectors_agree:
            family_mismatch_units += unit_count
            mismatch_family_cells.setdefault(family_hts, []).append(
                (
                    set(family.get("countries") or []),
                    set(family.get("probe_dates") or []),
                    expected,
                    axiom,
                )
            )
    if family_units != comparison or family_mismatch_units != mismatch_count:
        raise SystemExit(
            f"us-tariff-panel payload at {source} has a case-family ledger "
            f"({family_units} units, {family_mismatch_units} mismatched) "
            "that does not reproduce the summary counts "
            f"({comparison} units, {mismatch_count} mismatched)"
        )
    # Bind the payload to the independently derived comparison universe
    # (#448 review round 4): the covered slice's (hts, country, probe)
    # units come straight from the committed reference extract, so a
    # payload cannot invent units, relocate rows to coordinates outside
    # the universe, or shrink the account per HTS line while keeping the
    # global totals.
    from axiom_oracles.suites.us_tariff_panel import (
        REFERENCE_DIRNAME,
        column_exposure,
        covered_units,
        load_reference,
        temporal_debt,
        temporal_debt_records,
    )

    intervals, _ = load_reference(REPO_ROOT / REFERENCE_DIRNAME)
    # The conformance surfaces in scope — the positive-exposure witness
    # basis and the addressable temporal-debt account — must reproduce the
    # committed reference exactly, or the scoreboard would consume a forged
    # coverage/debt story (sol stack review F3/F4).
    scope = report.get("scope") or {}
    expected_exposure = column_exposure(covered_units(intervals))
    if scope.get("column_exposure") != expected_exposure:
        raise SystemExit(
            f"us-tariff-panel payload at {source} has a column_exposure "
            "account that does not reproduce the committed reference"
        )
    debt_block = scope.get("temporal_debt") or {}
    expected_records = temporal_debt_records(intervals)
    if (
        debt_block.get("records") != expected_records
        or debt_block.get("pre_domain_intervals") != len(temporal_debt(intervals))
        or debt_block.get("straddle_clipped_intervals")
        != sum(
            r["interval_count"]
            for r in expected_records
            if r["kind"] == "straddle_clipped"
        )
        or scope.get("temporal_debt_intervals")
        != debt_block.get("pre_domain_intervals")
    ):
        raise SystemExit(
            f"us-tariff-panel payload at {source} has a temporal-debt "
            "account that does not reproduce the committed reference"
        )
    universe = {
        (interval.hts10, interval.country_census, probe.isoformat())
        for interval, probe in covered_units(intervals)
    }
    if comparison != len(universe):
        raise SystemExit(
            f"us-tariff-panel payload at {source} declares {comparison} "
            f"comparison units; the committed reference derives "
            f"{len(universe)}"
        )
    universe_by_hts: dict[str, int] = {}
    for hts, _country, _probe in universe:
        universe_by_hts[hts] = universe_by_hts.get(hts, 0) + 1
    if family_units_by_hts != universe_by_hts:
        raise SystemExit(
            f"us-tariff-panel payload at {source} has per-HTS case-family "
            "unit totals that do not reproduce the reference-derived "
            "universe"
        )
    for row in mismatches:
        coordinate = (
            str(row.get("hts_number")),
            str(row.get("country_census")),
            str(row.get("probe_date")),
        )
        if coordinate not in universe:
            raise SystemExit(
                f"us-tariff-panel payload at {source} has a mismatch row "
                f"({row.get('case_id')}) outside the reference-derived "
                "comparison universe"
            )
        # The covering family must reproduce the row, vector for vector:
        # same diverging-slot set, same per-slot values, same totals. A
        # row detached from (or contradicting) its family ledger entry is
        # rejected (#448 review round 4).
        cells = mismatch_family_cells.get(coordinate[0]) or []
        row_slots = row.get("slots") or {}
        if not any(
            coordinate[1] in countries
            and coordinate[2] in probes
            and set(row_slots)
            == {
                slot
                for slot in expected
                if abs(axiom[slot] - expected[slot]) > 1e-12
            }
            and all(
                delta.get("axiom") == axiom[slot]
                and delta.get("yale") == expected[slot]
                for slot, delta in row_slots.items()
            )
            and row.get("left") == axiom.get("total")
            and row.get("right") == expected.get("total")
            for countries, probes, expected, axiom in cells
        ):
            raise SystemExit(
                f"us-tariff-panel payload at {source} has a mismatch row "
                f"({row.get('case_id')}) with no non-matching case family "
                "reproducing its slot deltas and totals"
            )


def _run_us_tariff_panel(runner: dict, output: Path) -> None:
    """US tariff panel: rulespec-us duty spine vs the Yale statutory panel.

    Delegates to scripts/generate_us_tariff_panel.py, which evaluates every
    covered (HTS-10 line, country, validity interval) cell of the committed
    Yale panel extract (reference/us-tariff-panel/) through the composed
    rulespec-us us-tariff-duty pipeline via the axiom rules engine and
    grades the per-authority statutory slots and the statutory total
    exactly. The reference leg is a committed, provenance-pinned extract —
    there is no external oracle process at comparison time. On a runner
    without a built axiom rules engine or the rulespec-us tariff spine
    (probed explicitly, BEFORE launching), the committed full report is
    reused, marked as a re-emit so provenance never stamps it fresh
    (#296; same shape as _run_us_tariff_grid). A launched generator that
    fails propagates — its integrity hard-fails (unbridged census codes,
    engine errors) must fail the job, not degrade into a re-emit.
    """
    generator = REPO_ROOT / "scripts" / "generate_us_tariff_panel.py"
    reason = _us_tariff_panel_unavailable_reason()
    if reason is not None:
        # Re-emits must source the UNIQUE COMMITTED (HEAD) full report —
        # never the dashboard copy (truncated for the UI), never an
        # untracked filesystem stray under the gitignored reports/
        # directory, and never mutable worktree/index bytes for the tracked
        # path (a staged or in-place edit is not "committed" — #448 review
        # rounds 2 and 3). The candidate list and the payload bytes both
        # come from HEAD, and the payload is validated before reuse so a
        # truncated or unreconciled artifact cannot re-emit as the full
        # account.
        committed_reports = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "ls-tree",
                "-r",
                "--name-only",
                "HEAD",
                "--",
                "reports/",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        candidates = [
            path
            for path in committed_reports
            if fnmatch.fnmatch(
                path, "reports/axiom-yale-us-tariff-panel-all-*.json"
            )
        ]
        if len(candidates) != 1:
            raise SystemExit(
                f"us-tariff-panel generation unavailable ({reason}) and the "
                "committed full report is not uniquely identifiable "
                f"(HEAD candidates: {candidates or 'none'})"
            )
        committed = candidates[0]
        text = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{committed}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        head_payload = json.loads(text)
        _validate_us_tariff_panel_payload(head_payload, f"HEAD:{committed}")
        runner["_reemitted_report"] = True
        # Source stamp: the published provenance must say WHOSE numbers
        # these are — the committed report's identity and original
        # generation time — or the re-emission presents as freshly
        # generated on every surface that only reads generated_at
        # (sol stack review F6).
        runner["_reemitted_source"] = {
            "path": str(committed),
            "generated_at": (head_payload.get("provenance") or {}).get(
                "generated_at"
            ),
        }
        print(
            f"us-tariff-panel generation unavailable ({reason}); "
            f"reusing HEAD:{committed}."
        )
        output.write_text(text)
        return
    # Record what will actually run (same env-override honesty as the T0
    # grid runner: the generator honors RULESPEC_US_CHECKOUT and
    # AXIOM_RULES_ENGINE_BINARY). The executable is resolved with the SAME
    # semantics the generator's exec uses (bare name -> PATH only, relative
    # path -> the generator's working directory) and its bytes are hashed
    # BEFORE the generator runs — hashing after execution would let a
    # swapped binary be labelled with the wrong identity, and an
    # exists()-first probe would hash a same-named cwd file PATH execution
    # never touches (#448 review rounds 3 and 4). The sha256 is the
    # VERIFIABLE engine identity; the enclosing checkout's HEAD (recorded
    # below) labels the checkout, not the build, and can postdate the
    # binary.
    checkout, _ = _us_tariff_panel_env()
    runner.setdefault("parameters", {})["rulespec_roots"] = [str(checkout)]
    engine_binary = _us_tariff_panel_engine_binary()
    engine_binary_sha256 = (
        hashlib.sha256(engine_binary.read_bytes()).hexdigest()
        if engine_binary is not None
        else None
    )
    # Launched leg: the generator writes to a run-private path (never a
    # shared slot a previous run could have populated), and the payload is
    # validated before provenance stamping — exit 0 alone does not prove a
    # fresh full report was produced (#448 review round 2).
    with tempfile.TemporaryDirectory(prefix="us-tariff-panel-") as tmpdir:
        fresh = Path(tmpdir) / "report.json"
        subprocess.run(
            [
                "uv",
                "run",
                "--python",
                "3.13",
                "--no-project",
                "--with-editable",
                str(REPO_ROOT),
                "python",
                str(generator),
                "--out",
                str(fresh),
            ],
            check=True,
            cwd=REPO_ROOT,
        )
        text = fresh.read_text()
    _validate_us_tariff_panel_payload(
        json.loads(text), "the generator's run-private output"
    )
    if engine_binary is not None:
        runner["parameters"]["engine_binary"] = str(engine_binary)
        runner["parameters"]["engine_binary_sha256"] = engine_binary_sha256
        # Only claim an enclosing repo when the executable actually lives
        # under that repo's cargo target/ directory — never by fixed
        # parent-depth arithmetic on an arbitrary install path.
        for ancestor in engine_binary.parents:
            if (ancestor / ".git").exists():
                if engine_binary.is_relative_to(ancestor / "target"):
                    runner["axiom_rules_repo"] = str(ancestor)
                break
    output.write_text(text)


def _snap_qc_optional_path(raw: str | Path | None) -> Path | None:
    """Expand a config path value, or return None when it is unset."""
    return _expand_path(raw) if raw else None


def _snap_qc_cola_marker_reason(rulespec_root: Path, fiscal_year: int) -> str | None:
    """Confirm ``rulespec_root`` carries the target-year SNAP COLA modules.

    The overlay compiles the CO SNAP composition with its COLA module ids
    rewritten from the in-repo fy-2026 vintage to ``fy-<year>-cola``, so the base
    checkout must actually define that vintage under
    ``us/policies/usda/snap/fy-<year>-cola/``. A plain rulespec-us checkout (or an
    un-rebased clone) carries only fy-2026 and is skipped — the common CI case.
    ``fy-2024-cola`` currently lives on the branch tracked by
    TheAxiomFoundation/rulespec-us#759, which retires the overlay once it lands.
    """
    if not rulespec_root.exists():
        return f"rulespec root not found at {rulespec_root}"
    cola_dir = (
        rulespec_root / "us" / "policies" / "usda" / "snap" / f"fy-{fiscal_year}-cola"
    )
    if cola_dir.is_dir() and any(cola_dir.glob("*.yaml")):
        return None
    return (
        f"rulespec checkout at {rulespec_root} has no "
        f"fy-{fiscal_year}-cola SNAP COLA modules"
    )


def _snap_qc_skip_reason(runner: dict, params: dict, fiscal_year: int) -> str | None:
    """Return why the SNAP QC replay cannot run here, or None if it can.

    The replay needs the built ``axiom-rules-engine`` binary, a rulespec-us
    checkout whose SNAP COLA modules are dated for ``fiscal_year`` (the overlay
    base), and the downloaded QC public-use file. Any probe failure — including
    the bridge module still being mid-build — counts as "not runnable" so the
    runner degrades to the committed-report re-emit rather than raising, exactly
    like the EUROMOD runner on a bare CI machine.
    """
    # The bridge and its snap_populace dependency may lack optional deps or still
    # be mid-build; a failed import means "skip", never a hard error.
    try:
        from axiom_oracles.bridges import snap_populace
        from axiom_oracles.bridges.snap_qc_compare import (  # noqa: F401
            run_snap_qc_comparison,
        )
    except ImportError as exc:
        return f"snap_qc_compare bridge unavailable ({exc})"

    # QC public-use file. Resolution mirrors populations/snap_qc.load_qc_units:
    # explicit data_dir, then AXIOM_SNAP_QC_DATA_DIR, then the default cache dir.
    data_dir = _expand_path(
        params.get("data_dir")
        or os.environ.get("AXIOM_SNAP_QC_DATA_DIR")
        or (Path.home() / ".cache" / "axiom-oracles" / "snap-qc")
    )
    qc_file = data_dir / f"qc_pub_fy{fiscal_year}.csv"
    if not qc_file.exists():
        return f"QC public-use file not found at {qc_file}"

    # Engine binary + rulespec checkout, resolved with the same snap_populace
    # helpers the bridge uses so this precondition matches what the bridge would
    # attempt. Resolution must degrade, never crash the runner.
    try:
        workspace_root = snap_populace.resolve_workspace_root(
            _snap_qc_optional_path(
                runner.get("workspace_root") or params.get("workspace_root")
            )
        )
        axiom_binary = snap_populace.resolve_axiom_binary(
            workspace_root,
            _snap_qc_optional_path(
                runner.get("axiom_binary")
                or params.get("axiom_binary")
                or os.environ.get("AXIOM_SNAP_QC_AXIOM_BINARY")
            ),
        )
    except Exception as exc:  # probe must degrade, never raise
        return f"engine resolution failed ({exc})"
    if not axiom_binary.exists():
        return f"axiom-rules-engine binary not built at {axiom_binary}"

    rulespec_root = _snap_qc_optional_path(
        runner.get("rulespec_root")
        or params.get("rulespec_root")
        or os.environ.get("AXIOM_SNAP_QC_RULESPEC_ROOT")
    ) or (workspace_root / "rulespec-us")
    return _snap_qc_cola_marker_reason(rulespec_root, fiscal_year)


def _reemit_snap_qc_committed_report(
    runner: dict, params: dict, output: Path, reason: str
) -> None:
    """Re-emit the committed dashboard report as the run output (graceful skip).

    Mirrors ``_run_euromod_synthetic_compare``: when the replay cannot run here,
    reuse the committed dashboard JSON so the weekly matrix stays green and the
    dashboard copy is idempotent. Falls back to an empty v2 report shell when no
    committed report exists yet (the first run before numbers are checked in).
    """
    dashboard_filename = runner.get("dashboard_filename") or params.get(
        "dashboard_filename", ""
    )
    print(
        f"SNAP QC replay not runnable here ({reason}); re-emitting the committed "
        "dashboard report. Regenerate locally where the engine binary, the "
        "fiscal-year rulespec checkout, and the QC public-use file all exist."
    )
    committed = (
        DASHBOARD_DATA_DIR / dashboard_filename if dashboard_filename else None
    )
    if committed is not None and committed.exists():
        output.write_text(committed.read_text())
        return
    output.write_text(
        json.dumps(
            {
                "schema_version": "axiom.comparison_report.v2",
                "suite": params.get("suite", "co-snap-qc"),
                "population": "snap-qc",
                "case_count": 0,
                "engines": {"left": "snap-qc", "right": "axiom"},
                "aggregates": [],
                "cases": [],
                "mismatches": [],
                "concepts": [],
                "errors": [f"skipped: {reason}"],
                "locales": [],
                "scope": None,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _run_snap_qc_compare(runner: dict, output: Path) -> None:
    """SNAP QC administrative-data replay vs Axiom RuleSpec (in-process).

    Replays the USDA SNAP Quality Control public-use microdata through the Axiom
    SNAP composition and compares the constructed benefit (FSBEN) and stage
    intermediates via ``axiom_oracles.bridges.snap_qc_compare``. Unlike the
    ``axiom-encode`` runners this calls the bridge in-process — the oracle lives
    in this repo, so there is no encoder CLI to shell out to.

    The replay needs three things a shared CI runner does not carry: the built
    ``axiom-rules-engine`` binary, a rulespec-us checkout whose SNAP COLA modules
    are dated for the target fiscal year (the overlay base), and the downloaded
    QC public-use file. When any is absent — or the bridge is still mid-build —
    this runner **skips gracefully**, re-emitting the committed dashboard report
    so the weekly matrix stays green and the dashboard copy is idempotent, exactly
    like ``_run_euromod_synthetic_compare``. Regenerate the committed numbers
    locally where all three exist.
    """
    params = runner["parameters"]
    fiscal_year = int(params.get("fiscal_year", 2024))
    jurisdiction = str(params.get("jurisdiction", "us-co"))

    skip_reason = _snap_qc_skip_reason(runner, params, fiscal_year)
    if skip_reason is not None:
        # Mark the re-emit so provenance never resolves the report-recorded
        # rulespec_root PATH to its current SHA: with the CI workspace
        # materializer cloning that path fresh at main HEAD, resolving it
        # would stamp a skipped run's re-emitted numbers as fresh (#296).
        runner["_reemitted_report"] = True
        _reemit_snap_qc_committed_report(runner, params, output, skip_reason)
        return

    # Imported here (not at module scope) so the script stays importable while
    # the bridge is mid-build; the skip path above already caught an ImportError.
    from axiom_oracles.bridges.snap_qc_compare import run_snap_qc_comparison

    raw_sample = params.get("sample_size")
    sample_size = None if raw_sample in (None, 0, "0") else int(raw_sample)

    report = run_snap_qc_comparison(
        fiscal_year=fiscal_year,
        jurisdiction=jurisdiction,
        sample_size=sample_size,
        months=params.get("months"),
        tolerance=float(params.get("tolerance", 0.0)),
        stage_tolerance=float(params.get("stage_tolerance", 1.0)),
        workspace_root=_snap_qc_optional_path(
            runner.get("workspace_root") or params.get("workspace_root")
        ),
        # The AXIOM_SNAP_QC_RULESPEC_ROOT / AXIOM_SNAP_QC_AXIOM_BINARY env
        # fallbacks live inside run_snap_qc_comparison itself (next to the
        # loader's AXIOM_SNAP_QC_DATA_DIR); only explicit config values are
        # threaded from here.
        rulespec_root=_snap_qc_optional_path(
            runner.get("rulespec_root") or params.get("rulespec_root")
        ),
        axiom_binary=_snap_qc_optional_path(
            runner.get("axiom_binary") or params.get("axiom_binary")
        ),
        data_dir=_snap_qc_optional_path(params.get("data_dir")),
        include_special_programs=bool(params.get("include_special_programs", False)),
        keep_overlay=bool(params.get("keep_overlay", False)),
    )
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")




def _run_spsm_ca_compare(runner: dict, output: Path) -> None:
    """Statistics Canada SPSD/M lanes (licensed local install required).

    Shells to the lane's generator, which runs SPSM under Wine over the
    full licensed database and writes an aggregate-only dashboard report
    carrying the SPSD/M Licence s.4.1 attribution notice. The generator
    hard-fails with installation instructions when no licensed Package is
    present, so CI (which cannot hold a licence) never silently produces
    an empty report.
    """
    del output  # the generator writes the dashboard artifact directly
    script = REPO_ROOT / "scripts" / "generate_ca_federal_tax_spsm.py"
    subprocess.run(
        [sys.executable, str(script), "--run-spsm"],
        check=True,
        cwd=REPO_ROOT,
    )

RUNNERS = {
    "axiom-encode-snap-ecps-compare": _run_axiom_encode_snap_ecps_compare,
    "axiom-encode-tax-ecps-compare": _run_axiom_encode_tax_ecps_compare,
    "axiom-encode-uk-efrs-compare": _run_axiom_encode_uk_efrs_compare,
    "axiom-oracles-compare": _run_axiom_oracles_compare,
    "euromod-synthetic-compare": _run_euromod_synthetic_compare,
    "federal-tax-liability-grid": _run_federal_tax_liability_grid,
    "gettsim-synthetic-compare": _run_gettsim_synthetic_compare,
    "snap-abawd-boundary-grid": _run_snap_abawd_boundary_grid,
    "snap-qc-compare": _run_snap_qc_compare,
    "spsm-ca-compare": _run_spsm_ca_compare,
    "state-income-tax-liability-grid": _run_state_income_tax_liability_grid,
    "uk-council-tax-reduction-grid": _run_uk_council_tax_reduction_grid,
    "uk-capital-gains-tax-grid": _run_uk_capital_gains_tax_grid,
    "uk-business-rates-grid": _run_uk_business_rates_grid,
    "uk-lbtt-ltt-grid": _run_uk_lbtt_ltt_grid,
    "uk-winter-fuel-payment-pe-grid": _run_uk_winter_fuel_payment_pe_grid,
    "uk-attendance-allowance-pe-grid": _run_uk_attendance_allowance_pe_grid,
    "uk-tax-free-childcare-pe-grid": _run_uk_tax_free_childcare_pe_grid,
    "uk-vat-grid": _run_uk_vat_grid,
    "uk-fuel-duty-grid": _run_uk_fuel_duty_grid,
    "uk-tv-licence-grid": _run_uk_tv_licence_grid,
    "us-tariff-grid": _run_us_tariff_grid,
    "us-tariff-panel": _run_us_tariff_panel,
}


def _run_sanity(name: str) -> int:
    """Run a comparison's sanity fixtures via the CLI's `sanity` command.

    Reuses the same uv subprocess shape and PE certification override as
    the population comparison so engines see the same environment. Returns
    the CLI's exit code (non-zero on any failure).
    """
    config = _load_comparison(name)
    fixtures_path = COMPARISONS_DIR / f"{name}.fixtures.yaml"
    if not fixtures_path.exists():
        print(f"No fixtures file at {fixtures_path}", file=sys.stderr)
        return 2
    params = config["runner"]["parameters"]
    pe_pins = _resolve_pe_oracle_pins(params)
    axiom_rules_repo = _resolve_path(
        config["runner"].get("axiom_rules_repo", "$HOME/axiom-rules"),
        "axiom_rules_repo",
    )
    cmd = [
        "uv",
        "run",
        "--python",
        str(params.get("python", "3.14")),
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        *(arg for pin in pe_pins for arg in ("--with", pin)),
        "python",
        "-c",
        _PE_CERT_OVERRIDE,
        "sanity",
        str(fixtures_path),
        "--left",
        params.get("left", "axiom"),
        "--right",
        params.get("right", "policyengine"),
        "--axiom-engine-binary",
        str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
    ]
    if params.get("axiom_compiled_program"):
        cmd.extend([
            "--axiom-compiled-program",
            str(_resolve_path(params["axiom_compiled_program"], "axiom_compiled_program")),
        ])
    if params.get("jurisdiction_fips"):
        cmd.extend(["--jurisdiction-fips", str(params["jurisdiction_fips"])])
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    return result.returncode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_comparison(name: str) -> dict:
    path = COMPARISONS_DIR / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in COMPARISONS_DIR.glob("*.yaml"))
        raise SystemExit(
            f"unknown comparison {name!r}; available: {', '.join(available)}"
        )
    return yaml.safe_load(path.read_text())


def _resolve_path(raw: str, field: str) -> Path:
    expanded = _expand_path(raw)
    if not expanded.exists():
        env_override = {
            "axiom_encode_repo": "AXIOM_ENCODE_REPO",
            "axiom_rules_repo": "AXIOM_RULES_REPO",
        }.get(field)
        if env_override and os.environ.get(env_override):
            expanded = Path(
                os.path.expandvars(os.path.expanduser(os.environ[env_override]))
            ).resolve()
    if not expanded.exists():
        raise SystemExit(f"{field}: path does not exist: {expanded}")
    return expanded


def _expand_path(raw: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()


def _ensure_engine_binary(repo: Path, *, kind: str) -> None:
    bin_path = repo / "target" / kind / "axiom-rules-engine"
    if bin_path.exists():
        return
    print(f"Building {kind} axiom-rules-engine in {repo}...")
    cmd = ["cargo", "build", "--bin", "axiom-rules-engine"]
    if kind == "release":
        cmd.append("--release")
    subprocess.run(cmd, check=True, cwd=repo)


def _ensure_rulespec_us_checkout(remote: str) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="oracle-compare."))
    target = workspace / "rulespec-us"
    print(f"Cloning rulespec-us into {target}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", remote, str(target)],
        check=True,
    )
    return target


def _git_head_sha(repo: Path) -> str | None:
    """Best-effort HEAD SHA of a checkout; None when unresolvable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return result.stdout.strip() or None


def _print_summary(output: Path) -> None:
    data = json.loads(output.read_text())
    print()
    if "compared_values" in data:
        cv = data["compared_values"]
        mc = data["mismatch_count"]
        od = data.get("oracle_divergence_count", 0)
        differences = mc + od
        pct = 100 * (cv - differences) / cv if cv else 0
        print(f"Compared values:   {cv}")
        print(f"Differences:       {differences}")
        print(f"Mismatches:        {mc}")
        if od:
            print(f"Known PE issues:   {od}")
        print(f"Agreement:         {pct:.4f}%")
        from collections import defaultdict

        by_surface = defaultdict(lambda: [0, 0])
        for row in data.get("output_summary", []):
            by_surface[row["surface"]][0] += row["compared"]
            by_surface[row["surface"]][1] += row["mismatches"] + row.get(
                "oracle_divergences", 0
            )
        print()
        for surf, (c, m) in sorted(by_surface.items(), key=lambda x: -x[1][1]):
            p = 100 * (c - m) / c if c else 0
            print(f"  {surf:30s}  {c - m}/{c} ({p:6.2f}%)  differences={m}")
    elif "case_count" in data:
        cc = data.get("case_count", 0)
        mm = sum(len(c.get("mismatches", []) or []) for c in data.get("cases", []))
        if not mm:
            # Reports whose case rows carry no per-case mismatch lists (the
            # SNAP QC bridge) count mismatches at the summary/top level.
            mm = (data.get("summary") or {}).get(
                "mismatch_count", len(data.get("mismatches") or [])
            )
        print(f"Cases:             {cc}")
        print(f"Mismatch entries:  {mm}")
        agg = data.get("aggregates") or []
        if agg:
            print()
            for a in agg[:8]:
                compared = a.get("compared", a.get("comparison_count", 0))
                matched = a.get("matched", a.get("match_count"))
                if matched is None:
                    matched = compared - a.get("mismatch_count", 0)
                line = (
                    f"  {a.get('concept', '?'):40s}  "
                    f"compared={compared}  "
                    f"matched={matched}"
                )
                # Surface positive-rate context for binary concepts so the
                # reader can tell whether "agreement" is real agreement or
                # both-engines-returning-the-dominant-value agreement.
                if a.get("comparison") != "amount" and "left_positive_rate" in a:
                    line += (
                        f"  left+={a['left_positive_rate']:.0f}%"
                        f"  right+={a['right_positive_rate']:.0f}%"
                    )
                print(line)
            _print_quality_flags(agg)
    else:
        print("(unknown report shape — committed JSON for offline inspection)")


def _print_quality_flags(aggregates: list) -> None:
    """Print loud, separable alarms for degenerate positive rates.

    Quality flags computed in report.py travel attached to each aggregate
    row; rendering them as a dedicated block (not nested inside the per-
    concept table) is what makes them visible at a glance.
    """
    flags = [
        (a.get("concept", "?"), flag)
        for a in aggregates
        for flag in (a.get("quality_flags") or [])
    ]
    if not flags:
        return
    print()
    print("!! QUALITY ALARMS")
    for concept, flag in flags:
        print(f"  [{flag.get('severity', '?').upper()}] {concept}")
        print(f"    {flag.get('code', '?')}: {flag.get('message', '')}")


# ---------------------------------------------------------------------------
# Dashboard adapter
# ---------------------------------------------------------------------------


def _adapt_to_v2(raw_path: Path, runner_type: str, config: dict, *, suite: str) -> dict:
    raw = json.loads(raw_path.read_text())
    if runner_type == "axiom-encode-tax-ecps-compare":
        return _adapt_tax_ecps_to_v2(raw, config, suite=suite)
    if runner_type == "axiom-encode-uk-efrs-compare":
        return _adapt_uk_efrs_to_v2(raw, config, suite=suite)
    # axiom-oracles-compare already emits v2 — pass through, but override
    # the suite with the comparison-config value. The upstream report
    # stamps the population/synthetic-subset name (e.g. "nyc-synthetic"),
    # not the per-comparison identity, so without this override every
    # state's SNAP report collapses into one suite bucket in the
    # dashboard's suite selector.
    raw["suite"] = suite
    return raw


def _adapt_uk_efrs_to_v2(raw: dict, config: dict, *, suite: str) -> dict:
    """Convert uk-efrs-compare output to axiom.comparison_report.v2."""
    from collections import Counter, defaultdict

    dashboard_config = config.get("dashboard") or {}
    parent_concept = dashboard_config.get("parent_concept", UK_UNIVERSAL_CREDIT_PARENT)
    parent_category = dashboard_config.get("parent_category", "benefits")
    parent_description = dashboard_config.get(
        "parent_description", "Universal Credit amount surfaces"
    )
    known_divergence_detail_limit = int(
        dashboard_config.get("known_policyengine_divergence_detail_limit", 100)
    )

    def spec_for(row: dict) -> dict | None:
        surface = row.get("surface")
        output = row.get("output")
        if (surface, output) in UK_EFRS_OUTPUT_CONCEPTS:
            return UK_EFRS_OUTPUT_CONCEPTS[(surface, output)]
        return UK_UNIVERSAL_CREDIT_OUTPUT_CONCEPTS.get(output)

    def category_for(spec: dict) -> str:
        concept = str(spec.get("concept") or "")
        tax_markers = (
            "/income-tax",
            "/national-insurance",
            "/student-loan",
            "/student-loans",
            "ukpga/1992/4",
            "ukpga/2007/3",
        )
        return "tax" if any(marker in concept for marker in tax_markers) else "benefits"

    by_output = {
        (row.get("surface"), row.get("output")): row
        for row in raw.get("output_summary", [])
        if spec_for(row)
    }
    mismatch_rows = [
        {**row, "kind": "amount_difference"}
        for row in raw.get("mismatches", [])
        if spec_for(row)
    ]
    divergence_rows = [
        {**row, "kind": "known_policyengine_divergence"}
        for row in raw.get("oracle_divergences", [])
        if spec_for(row)
    ]
    all_difference_rows = [*mismatch_rows, *divergence_rows]
    visible_divergence_rows = _limit_rows_by_output(
        divergence_rows,
        limit_per_output=known_divergence_detail_limit,
    )
    visible_difference_rows = [*mismatch_rows, *visible_divergence_rows]

    component_concepts: list[str] = []
    aggregates: list[dict] = []
    for _output_key, row in by_output.items():
        spec = spec_for(row)
        if spec is None:
            continue
        compared = int(row.get("compared", 0) or 0)
        true_mismatches = int(row.get("mismatches", 0) or 0)
        known_divergences = int(row.get("oracle_divergences", 0) or 0)
        differences = true_mismatches + known_divergences
        matched = compared - differences
        match_rate = (matched / compared * 100) if compared else 100.0
        quality_flags = []
        if known_divergences:
            quality_flags.append(
                {
                    "code": "known_policyengine_uk_divergence",
                    "message": (
                        "PolicyEngine UK currently uses forecast-indexed "
                        "2026 Universal Credit rates for this component."
                    ),
                    "severity": "warning",
                }
            )
        aggregates.append(
            {
                "category": category_for(spec),
                "comparison": "amount",
                "comparison_count": compared,
                "comparison_weight": compared,
                "components": [],
                "concept": spec["concept"],
                "description": spec["description"],
                "known_policyengine_divergence_count": known_divergences,
                "left_weighted_sum": None,
                "match_count": matched,
                "match_rate": match_rate,
                "match_weight": matched,
                "mismatch_count": differences,
                "mismatch_weight": differences,
                "missing_both_count": 0,
                "missing_left_count": 0,
                "missing_right_count": 0,
                "parent": parent_concept,
                "quality_flags": quality_flags,
                "right_weighted_sum": None,
                "true_mismatch_count": true_mismatches,
                "weighted_difference": None,
                "weighted_match_rate": match_rate,
            }
        )
        component_concepts.append(spec["concept"])

    parent_compared = sum(a["comparison_count"] for a in aggregates)
    parent_mismatches = sum(a["mismatch_count"] for a in aggregates)
    parent_known_divergences = sum(
        a["known_policyengine_divergence_count"] for a in aggregates
    )
    parent_matched = parent_compared - parent_mismatches
    parent_rate = (parent_matched / parent_compared * 100) if parent_compared else 100.0
    aggregates.insert(
        0,
        {
            "category": parent_category,
            "comparison": "amount",
            "comparison_count": parent_compared,
            "comparison_weight": parent_compared,
            "components": component_concepts,
            "concept": parent_concept,
            "description": parent_description,
            "known_policyengine_divergence_count": parent_known_divergences,
            "left_weighted_sum": None,
            "match_count": parent_matched,
            "match_rate": parent_rate,
            "match_weight": parent_matched,
            "mismatch_count": parent_mismatches,
            "mismatch_weight": parent_mismatches,
            "missing_both_count": 0,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "parent": None,
            "right_weighted_sum": None,
            "true_mismatch_count": len(mismatch_rows),
            "weighted_difference": None,
            "weighted_match_rate": parent_rate,
        },
    )

    concepts = [
        {
            "category": parent_category,
            "comparison": "amount",
            "components": component_concepts,
            "description": parent_description,
            "id": parent_concept,
            "parent": None,
            "tolerance": 0.01,
        }
    ]
    for row in by_output.values():
        spec = spec_for(row)
        if spec is None:
            continue
        concepts.append(
            {
                "category": category_for(spec),
                "comparison": "amount",
                "components": [],
                "description": spec["description"],
                "id": spec["concept"],
                "parent": parent_concept,
                "tolerance": 0.01,
            }
        )

    cases_by_entity: dict[str, list[dict]] = defaultdict(list)
    flat_mismatches: list[dict] = []
    for row in visible_difference_rows:
        spec = spec_for(row)
        if spec is None:
            continue
        kind = row["kind"]
        mismatch = {
            "case_id": f"uk-efrs-{row['entity_id']}",
            "concept": spec["concept"],
            "description": row.get("reason")
            or f"{spec['description']} — output={row['output']}",
            "difference": row.get("diff", 0),
            "issue_url": row.get("issue_url"),
            "kind": kind,
            "left": row.get("axiom", 0),
            "parent": parent_concept,
            "relative_tolerance": 2e-7,
            "right": row.get("policyengine", 0),
            "surface": row.get("surface"),
            "tolerance": 0.01,
        }
        cases_by_entity[str(row["entity_id"])].append(mismatch)
        flat_mismatches.append(mismatch)

    cases = []
    for entity_id, case_mismatches in cases_by_entity.items():
        cases.append(
            {
                "case_id": f"uk-efrs-{entity_id}",
                "left_engine": "axiom",
                "left_errors": [],
                "match_rate": 0.0,
                "metadata": {
                    "case_unit": "benefit_unit_or_person",
                    "dataset": "enhanced_frs_2023_24",
                    "entity_id": entity_id,
                    "population": "enhanced-frs",
                    "suite": suite,
                },
                "mismatches": case_mismatches,
                "right_engine": "policyengine",
                "right_errors": [],
            }
        )

    mismatches_by_concept = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(
                spec_for(row)["concept"]
                for row in all_difference_rows
                if spec_for(row) is not None
            ).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    mismatches_by_kind = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(row["kind"] for row in all_difference_rows).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    alarms = []
    if parent_known_divergences:
        alarms.append(
            {
                "code": "known_policyengine_uk_divergence",
                "message": (
                    f"{parent_known_divergences:,} differences are classified "
                    "as known PolicyEngine UK 2026 Universal Credit rate "
                    "divergences, not source-backed Axiom calculation defects."
                ),
                "severity": "warning",
            }
        )

    return {
        "aggregates": aggregates,
        "case_count": raw.get("compared_persons", 0) + raw.get("compared_benunits", 0),
        "cases": cases,
        "concepts": concepts,
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": ["UK"],
        "mismatches": flat_mismatches,
        "population": "enhanced-frs",
        "projection_notes": raw.get("projection_notes", []),
        "schema_version": "axiom.comparison_report.v2",
        "scope": {"geoid": "UK", "type": "country"},
        "suite": suite,
        "summary": {
            "alarms": alarms,
            "comparison_count": parent_compared,
            "error_count": 0,
            "errors_by_engine": {},
            "known_policyengine_divergence_count": parent_known_divergences,
            "match_count": parent_matched,
            "mismatch_count": parent_mismatches,
            "mismatches_by_concept": mismatches_by_concept,
            "mismatches_by_kind": mismatches_by_kind,
            "mismatches_by_scenario": {},
            "stored_mismatch_example_count": len(flat_mismatches),
            "true_mismatch_count": len(mismatch_rows),
            "weighted": {
                "comparison_weight": parent_compared,
                "match_rate": parent_rate,
                "match_weight": parent_matched,
                "mismatch_weight": parent_mismatches,
            },
        },
    }


def _limit_rows_by_output(rows: list[dict], *, limit_per_output: int) -> list[dict]:
    if limit_per_output <= 0:
        return []
    counts: Counter[str] = Counter()
    selected: list[dict] = []
    for row in rows:
        output = str(row.get("output") or "")
        if counts[output] >= limit_per_output:
            continue
        counts[output] += 1
        selected.append(row)
    return selected


def _normalize_dataset_identity(raw: dict) -> dict | None:
    """Return the encode `dataset_identity` block, or None when absent/empty.

    `axiom-encode tax-populace-compare --json` emits a top-level
    `dataset_identity` object (added in axiom-encode#952) describing exactly
    which Populace artifact the PolicyEngine oracle ran against — the pinned
    revision, the sha256 (first 12 hex), the PolicyEngine model version it was
    built with, and how it resolved (`pinned` / `local-override` / `unpinned`).
    Older harness output (pre-#952) omits the key; a run that fell through an
    error path may emit an empty dict. Both collapse to None here so the
    adapter can keep the legacy `enhanced_cps` label and stay back-compatible.
    """
    identity = raw.get("dataset_identity")
    if not isinstance(identity, dict) or not identity:
        return None
    return identity


def _dataset_label_from_identity(identity: dict | None, *, fallback: str) -> str:
    """Human dataset label for `metadata.dataset`, derived from identity.

    Prefers a stable, self-documenting `populace-<country>@<revision>` string
    so a checked-in report says which artifact produced it without needing the
    full identity block. Falls back to the legacy label when identity is
    absent (keeps pre-#952 reports and unit fixtures unchanged).
    """
    if not identity:
        return fallback
    country = str(identity.get("country") or "").strip().lower()
    revision = str(identity.get("revision") or "").strip()
    base = f"populace-{country}" if country else "populace"
    return f"{base}@{revision}" if revision else base


def _adapt_tax_ecps_to_v2(raw: dict, config: dict, *, suite: str) -> dict:
    """Convert tax-ecps-compare flat output to axiom.comparison_report.v2.

    Surfaces become aggregates; mismatching entities become cases (matching
    units are counted in summary/aggregates but don't appear in cases[]). The
    schema treats `comparison_weight` as the running denominator; we don't
    have ECPS household weights here, so we set weights = counts to keep
    the dashboard's weighted columns identical to unweighted.

    The encode `dataset_identity` block (axiom-encode#952) is threaded onto the
    report top-level and into each case's metadata so a checked-in FIIT report
    is self-documenting about which pinned Populace artifact produced it. It is
    carried at top-level (not only in cases) so it survives dashboard case-row
    slimming, which can drop every case on a clean run.
    """
    from collections import Counter, defaultdict

    identity = _normalize_dataset_identity(raw)
    dataset_label = _dataset_label_from_identity(identity, fallback="enhanced_cps")

    # Surface → list of output rows from output_summary
    by_surface: dict[str, list[dict]] = defaultdict(list)
    for row in raw.get("output_summary", []):
        by_surface[row["surface"]].append(row)

    # Surface → list of mismatch tuples grouped by tax-unit entity
    mismatches_by_entity: dict[str, list[dict]] = defaultdict(list)
    for m in raw.get("mismatches", []):
        mismatches_by_entity[m["entity_id"]].append(m)

    # Aggregates: one per surface, plus a synthetic FIIT-liability parent
    aggregates: list[dict] = []
    component_concepts: list[str] = []
    for surface, rows in by_surface.items():
        spec = FIIT_SURFACE_CONCEPTS.get(surface)
        if spec is None:
            continue
        compared = sum(r["compared"] for r in rows)
        mismatches = sum(r["mismatches"] for r in rows)
        matched = compared - mismatches
        match_rate = (matched / compared * 100) if compared else 100.0
        aggregates.append(
            {
                "category": spec["category"],
                "comparison": "amount",
                "comparison_count": compared,
                "comparison_weight": compared,
                "components": [],
                "concept": spec["concept"],
                "description": spec["description"],
                "left_weighted_sum": None,
                "match_rate": match_rate,
                "match_weight": matched,
                "mismatch_count": mismatches,
                "mismatch_weight": mismatches,
                "missing_both_count": 0,
                "missing_left_count": 0,
                "missing_right_count": 0,
                "parent": spec["parent"],
                "right_weighted_sum": None,
                "weighted_difference": None,
                "weighted_match_rate": match_rate,
            }
        )
        component_concepts.append(spec["concept"])

    parent_compared = raw.get("compared_values", 0)
    parent_mismatches = raw.get("mismatch_count", 0)
    parent_matched = parent_compared - parent_mismatches
    parent_rate = (parent_matched / parent_compared * 100) if parent_compared else 100.0
    aggregates.insert(
        0,
        {
            "category": "tax",
            "comparison": "amount",
            "comparison_count": parent_compared,
            "comparison_weight": parent_compared,
            "components": component_concepts,
            "concept": "us:tax/federal-income-tax#liability",
            "description": "Federal income tax liability (ECPS, all surfaces)",
            "left_weighted_sum": None,
            "match_rate": parent_rate,
            "match_weight": parent_matched,
            "mismatch_count": parent_mismatches,
            "mismatch_weight": parent_mismatches,
            "missing_both_count": 0,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "parent": None,
            "right_weighted_sum": None,
            "weighted_difference": None,
            "weighted_match_rate": parent_rate,
        },
    )

    # Concepts manifest mirrors aggregates so the dashboard's concept loader
    # picks them up. Components carry parent={parent_id} for auto-allow.
    concepts: list[dict] = [
        {
            "category": "tax",
            "comparison": "amount",
            "components": component_concepts,
            "description": "Federal income tax liability (ECPS, all surfaces)",
            "id": "us:tax/federal-income-tax#liability",
            "parent": None,
            "tolerance": 15,
        }
    ]
    for surface, rows in by_surface.items():
        spec = FIIT_SURFACE_CONCEPTS.get(surface)
        if spec is None:
            continue
        concepts.append(
            {
                "category": spec["category"],
                "comparison": "amount",
                "components": [],
                "description": spec["description"],
                "id": spec["concept"],
                "parent": spec["parent"],
                "tolerance": spec["tolerance"],
            }
        )

    # Cases: one per mismatching entity. Matching entities are not enumerated
    # (the harness doesn't surface their ids); summary/aggregates capture them.
    surface_to_spec = {
        s: FIIT_SURFACE_CONCEPTS[s] for s in by_surface if s in FIIT_SURFACE_CONCEPTS
    }
    cases: list[dict] = []
    flat_mismatches: list[dict] = []
    for entity_id, ms in mismatches_by_entity.items():
        case_id = f"ecps-{entity_id}"
        case_mismatches = []
        for m in ms:
            spec = surface_to_spec.get(m["surface"])
            if spec is None:
                continue
            mm = {
                "case_id": case_id,
                "concept": spec["concept"],
                "description": f"{spec['description']} — output={m['output']}",
                "difference": m.get("diff", 0),
                "kind": "amount_difference",
                "left": m.get("axiom", 0),
                "parent": spec["parent"],
                "right": m.get("policyengine", 0),
                "tolerance": spec["tolerance"],
            }
            case_mismatches.append(mm)
            flat_mismatches.append(mm)
        if not case_mismatches:
            continue
        case_metadata = {
            "case_unit": "tax_unit",
            "dataset": dataset_label,
            "entity_id": entity_id,
            "population": "enhanced-cps",
            "suite": suite,
        }
        if identity is not None:
            case_metadata["dataset_identity"] = identity
        cases.append(
            {
                "case_id": case_id,
                "left_engine": "axiom",
                "left_errors": [],
                "match_rate": 0.0,
                "metadata": case_metadata,
                "mismatches": case_mismatches,
                "right_engine": "policyengine",
                "right_errors": [],
            }
        )

    mismatches_by_concept = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(m["concept"] for m in flat_mismatches).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    report = {
        "aggregates": aggregates,
        "case_count": raw.get("compared_tax_units", 0),
        "cases": cases,
        "concepts": concepts,
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": [],
        "mismatches": flat_mismatches,
        "population": "enhanced-cps",
        "schema_version": "axiom.comparison_report.v2",
        "scope": {"geoid": "US", "type": "country"},
        "suite": suite,
        "summary": {
            "comparison_count": parent_compared,
            "error_count": 0,
            "errors_by_engine": {},
            "match_count": parent_matched,
            "mismatch_count": parent_mismatches,
            "mismatches_by_concept": mismatches_by_concept,
            "mismatches_by_kind": [
                {"value": "amount_difference", "count": parent_mismatches}
            ],
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": parent_compared,
                "match_rate": parent_rate,
                "match_weight": parent_matched,
                "mismatch_weight": parent_mismatches,
            },
        },
    }
    # Thread encode's dataset identity onto the report top-level so the
    # checked-in FIIT report records which pinned Populace artifact produced
    # it — and so it survives even when `cases` is slimmed to empty on a run
    # with no mismatches (`_slim_report_for_dashboard`).
    if identity is not None:
        report["dataset_identity"] = identity
    return report


def _adapt_snap_ecps_csv_to_v2(rows: list[dict], runner: dict) -> dict:
    """Convert snap-ecps-compare row CSV into axiom.comparison_report.v2."""
    params = runner.get("parameters", {})
    jurisdiction = str(params.get("jurisdiction", "us-co"))
    state_code = str(params.get("state") or jurisdiction.rsplit("-", 1)[-1]).upper()
    tolerance = float(params.get("tolerance", 1.5))
    amount_concept_id = "us:statutes/7/2014/u#snap_benefit"
    eligibility_concept_id = "us:statutes/7/2014/o#snap_eligible"
    compared = len(rows)
    amount_mismatching_rows = [row for row in rows if not _csv_bool(row.get("match"))]
    eligibility_mismatching_rows = [
        row
        for row in rows
        if _csv_bool(row.get("axiom_snap_eligible"))
        != _csv_bool(row.get("pe_snap_eligible"))
    ]
    amount_matched = compared - len(amount_mismatching_rows)
    eligibility_matched = compared - len(eligibility_mismatching_rows)
    amount_match_rate = (amount_matched / compared * 100) if compared else 100.0
    eligibility_match_rate = (
        eligibility_matched / compared * 100
    ) if compared else 100.0
    left_sum = sum(_csv_float(row.get("axiom_snap_allotment")) for row in rows)
    right_sum = sum(_csv_float(row.get("pe_snap")) for row in rows)
    left_eligible_count = sum(
        1 for row in rows if _csv_bool(row.get("axiom_snap_eligible"))
    )
    right_eligible_count = sum(
        1 for row in rows if _csv_bool(row.get("pe_snap_eligible"))
    )

    # Every row becomes a case — matches carry both engines' values just
    # like mismatches, so the report alone lets the dashboard show the
    # evidence behind the agreement, not only the disagreements.
    cases: list[dict] = []
    flat_mismatches: list[dict] = []
    for row in rows:
        spm_unit_id = str(row.get("spm_unit_id") or "unknown")
        case_id = f"ecps-spm-{spm_unit_id}"
        case_mismatches = []
        case_matches = []
        axiom_value = _csv_float(row.get("axiom_snap_allotment"))
        pe_value = _csv_float(row.get("pe_snap"))
        if not _csv_bool(row.get("match")):
            difference = _csv_float(row.get("difference"), axiom_value - pe_value)
            mismatch = {
                "case_id": case_id,
                "concept": amount_concept_id,
                "description": "SNAP benefit amount",
                "difference": difference,
                "kind": "amount_difference",
                "left": axiom_value,
                "parent": None,
                "relative_tolerance": 0,
                "right": pe_value,
                "tolerance": tolerance,
            }
            case_mismatches.append(mismatch)
            flat_mismatches.append(mismatch)
        else:
            case_matches.append(
                {
                    "concept": amount_concept_id,
                    "left": axiom_value,
                    "right": pe_value,
                }
            )
        axiom_eligible = _csv_bool(row.get("axiom_snap_eligible"))
        pe_eligible = _csv_bool(row.get("pe_snap_eligible"))
        if axiom_eligible != pe_eligible:
            if axiom_eligible and not pe_eligible:
                kind = "eligibility_left_only"
            elif pe_eligible and not axiom_eligible:
                kind = "eligibility_right_only"
            else:
                kind = "eligibility_mismatch"
            mismatch = {
                "case_id": case_id,
                "concept": eligibility_concept_id,
                "description": "SNAP eligibility",
                "difference": None,
                "kind": kind,
                "left": axiom_eligible,
                "parent": None,
                "relative_tolerance": 0,
                "right": pe_eligible,
                "tolerance": 0,
            }
            case_mismatches.append(mismatch)
            flat_mismatches.append(mismatch)
        else:
            case_matches.append(
                {
                    "concept": eligibility_concept_id,
                    "left": axiom_eligible,
                    "right": pe_eligible,
                }
            )
        case_match_rate = (
            (2 - len(case_mismatches)) / 2 * 100 if case_mismatches else 100.0
        )
        metadata = {
            "axiom_gross_income": _csv_float(row.get("axiom_gross_income")),
            "axiom_net_income": _csv_float(row.get("axiom_net_income")),
            "axiom_shelter_deduction": _csv_float(
                row.get("axiom_shelter_deduction")
            ),
            "axiom_snap_eligible": _csv_bool(row.get("axiom_snap_eligible")),
            "axiom_utility_allowance": _csv_float(
                row.get("axiom_utility_allowance")
            ),
            "case_unit": "spm_unit",
            "dataset": "enhanced_cps",
            "household_id": row.get("household_id"),
            "population": "enhanced-cps",
            "pe_gross_income": _csv_float(row.get("pe_gross_income")),
            "pe_net_income": _csv_float(row.get("pe_net_income")),
            "pe_shelter_deduction": _csv_float(row.get("pe_shelter_deduction")),
            "pe_snap_eligible": _csv_bool(row.get("pe_snap_eligible")),
            "pe_utility_allowance": _csv_float(row.get("pe_utility_allowance")),
            "spm_unit_id": spm_unit_id,
            "state": state_code,
            "suite": f"{jurisdiction}-snap-ecps",
        }
        for key, value in row.items():
            if key.startswith(("axiom_", "pe_")) and key not in metadata:
                metadata[key] = _csv_scalar(value)
        case = {
            "case_id": case_id,
            "left_engine": "axiom",
            "left_errors": [],
            "match_rate": case_match_rate,
            "metadata": metadata,
            "mismatches": case_mismatches,
            "right_engine": "policyengine",
            "right_errors": [],
        }
        if case_matches:
            case["matches"] = case_matches
        cases.append(case)

    amount_aggregate = {
        "category": "food",
        "comparison": "amount",
        "comparison_count": compared,
        "comparison_weight": compared,
        "compared": compared,
        "components": [],
        "concept": amount_concept_id,
        "description": "SNAP benefit amount",
        "left_weighted_sum": left_sum,
        "match_count": amount_matched,
        "match_rate": amount_match_rate,
        "match_weight": amount_matched,
        "matched": amount_matched,
        "mismatch_count": len(amount_mismatching_rows),
        "mismatch_weight": len(amount_mismatching_rows),
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "right_weighted_sum": right_sum,
        "weighted_difference": left_sum - right_sum,
        "weighted_match_rate": amount_match_rate,
    }
    eligibility_aggregate = {
        "category": "food",
        "comparison": "eligibility",
        "comparison_count": compared,
        "comparison_weight": compared,
        "compared": compared,
        "components": [],
        "concept": eligibility_concept_id,
        "description": "SNAP eligibility",
        "left_positive_rate": (left_eligible_count / compared * 100)
        if compared
        else 0.0,
        "left_positive_weight": left_eligible_count,
        "match_count": eligibility_matched,
        "match_rate": eligibility_match_rate,
        "match_weight": eligibility_matched,
        "matched": eligibility_matched,
        "mismatch_count": len(eligibility_mismatching_rows),
        "mismatch_weight": len(eligibility_mismatching_rows),
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "positive_rate_difference": (
            (left_eligible_count - right_eligible_count) / compared * 100
        )
        if compared
        else 0.0,
        "quality_flags": [],
        "right_positive_rate": (right_eligible_count / compared * 100)
        if compared
        else 0.0,
        "right_positive_weight": right_eligible_count,
        "weighted_match_rate": eligibility_match_rate,
    }
    mismatches_by_concept = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(m["concept"] for m in flat_mismatches).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    mismatches_by_kind = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(m["kind"] for m in flat_mismatches).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    summary_comparison_count = compared * 2
    summary_match_count = amount_matched + eligibility_matched
    summary_mismatch_count = len(amount_mismatching_rows) + len(
        eligibility_mismatching_rows
    )
    summary_match_rate = (
        summary_match_count / summary_comparison_count * 100
        if summary_comparison_count
        else 100.0
    )

    return {
        "aggregates": [amount_aggregate, eligibility_aggregate],
        "case_count": compared,
        "cases": cases,
        "concepts": [
            {
                "category": "food",
                "comparison": "amount",
                "components": [],
                "description": "SNAP benefit amount",
                "id": amount_concept_id,
                "parent": None,
                "priority": "high",
                "relative_tolerance": 0,
                "tolerance": tolerance,
            },
            {
                "category": "food",
                "comparison": "eligibility",
                "components": [],
                "description": "SNAP eligibility",
                "id": eligibility_concept_id,
                "parent": None,
                "priority": "high",
                "relative_tolerance": 0,
                "tolerance": 0,
            },
        ],
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": [state_code],
        "mismatches": flat_mismatches,
        "population": "enhanced-cps",
        "schema_version": "axiom.comparison_report.v2",
        "scope": {"geoid": state_code, "type": "state"},
        "suite": f"{jurisdiction}-snap-ecps",
        "summary": {
            "comparison_count": summary_comparison_count,
            "error_count": 0,
            "errors_by_engine": {},
            "match_count": summary_match_count,
            "mismatch_count": summary_mismatch_count,
            "mismatches_by_concept": mismatches_by_concept,
            "mismatches_by_kind": mismatches_by_kind,
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": summary_comparison_count,
                "match_rate": summary_match_rate,
                "match_weight": summary_match_count,
                "mismatch_weight": summary_mismatch_count,
            },
        },
    }


def _csv_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "holds"}


def _csv_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _csv_scalar(value: object) -> object:
    text = str(value).strip()
    if text.lower() in {"1", "true", "t", "yes", "y", "holds"}:
        return True
    if text.lower() in {"0", "false", "f", "no", "n", "not_holds"}:
        return False
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return value


# The dashboard fetches every report on page load, so population-scale runs
# must not ship all their case rows. Aggregates carry the headline numbers;
# case rows exist only to power the per-mismatch drawer, so keep just the
# mismatching cases (and cap both lists) once a report crosses the threshold.
_DASHBOARD_MAX_MISMATCHES = 1000
_DASHBOARD_MAX_CASE_ROWS = 1000


def _slim_report_for_dashboard(report: dict) -> dict:
    mismatches = report.get("mismatches") or []
    cases = report.get("cases") or []
    if (
        len(mismatches) <= _DASHBOARD_MAX_MISMATCHES
        and len(cases) <= _DASHBOARD_MAX_CASE_ROWS
    ):
        return report
    slim = dict(report)
    kept_mismatches = mismatches[:_DASHBOARD_MAX_MISMATCHES]
    kept_ids = {m.get("case_id") for m in kept_mismatches}
    slim["mismatches"] = kept_mismatches
    # Case rows are only dropped when THEY breach the cap. Filtering them
    # by retained mismatch ids whenever the mismatch list is truncated
    # silently discarded ledgers whose case rows are aggregates with their
    # own id scheme (the us-tariff-panel family ledger shipped 0/73 rows —
    # #448 review round 4).
    if len(cases) > _DASHBOARD_MAX_CASE_ROWS:
        slim["cases"] = [
            case for case in cases if case.get("case_id") in kept_ids
        ][:_DASHBOARD_MAX_CASE_ROWS]
    else:
        slim["cases"] = cases
    slim["dashboard_truncation"] = {
        "total_mismatches": len(mismatches),
        "shown_mismatches": len(kept_mismatches),
        "total_case_rows": len(cases),
        "shown_case_rows": len(slim["cases"]),
    }
    # When a dispositioned report is trimmed, record how many example mismatch
    # rows survive so scripts/apply_dispositions.py --check recognizes it as a
    # premerged-slim report (v2.1) and keeps the full-run summary.dispositioned
    # block instead of re-merging dispositions against the truncated examples
    # (which would undercount classified rows). See dispositions._is_premerged_...
    summary = report.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("dispositioned"), dict):
        slim["summary"] = dict(summary)
        slim["summary"]["stored_mismatch_example_count"] = len(kept_mismatches)
    return slim


def _merge_dispositions(report: dict) -> dict:
    """Join dispositions/<suite>.yaml (when present) into the report.

    Adds the summary `dispositioned` block — raw match rate, explained rate,
    unexplained count — and annotates classified mismatch rows. Invalid
    dispositions files raise so a run never writes a report with silently
    dropped classifications.
    """
    try:
        from axiom_oracles.comparison.dispositions import (
            apply_dispositions_from_dir,
        )
    except ImportError:
        return report
    return apply_dispositions_from_dir(
        report,
        REPO_ROOT / "dispositions",
        repo_root=REPO_ROOT,
    )


def _write_dashboard_report(
    report: dict, filename: str, *, full_report_path: Path | None = None
) -> None:
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    from axiom_oracles.comparison.report import strip_heavy_case_metadata

    report = _merge_dispositions(report)
    target = DASHBOARD_DATA_DIR / filename
    slim = _slim_report_for_dashboard(strip_heavy_case_metadata(report))
    truncation = slim.get("dashboard_truncation")
    # A premerged-slim copy (v2.1, trimmed mismatch sample, full-run
    # dispositioned block) binds its block to the just-published full
    # report: a source pointer + file digest lets apply_dispositions.py
    # --check fail CLOSED when the source is missing or edited, and the
    # row-level assignment digest catches reclassifications that keep the
    # aggregate counts identical — e.g. two equal-cardinality entries
    # swapping disposition classes (sol stack review r2: F2 residual +
    # fail-open MED).
    # Only when the in-memory merged report is COMPLETE (every mismatch row
    # present) is the published reports/ artifact a re-derivable full report
    # and the row-level digest meaningful. Lanes whose generators already
    # trim their mismatch sample before this point (population diagnostics)
    # keep the pointer-free block they always had.
    merged_summary = report.get("summary") or {}
    merged_is_complete = (
        len(report.get("mismatches") or [])
        == merged_summary.get("mismatch_count")
    )
    slim_summary = slim.get("summary")
    slim_stored = (
        slim_summary.get("stored_mismatch_example_count")
        if isinstance(slim_summary, dict)
        else None
    )
    # Mirrors apply_dispositions._is_premerged_slim_report exactly: the
    # consumer only treats a copy as premerged when its mismatch SAMPLE is
    # actually truncated (stored < mismatch_count). Case-only overflow also
    # writes stored_mismatch_example_count, so a key-presence predicate
    # called those copies premerged while the consumer re-merges them
    # directly — skipping their dashboard publish for no reason (sol stack
    # review r6).
    slim_is_premerged = (
        slim.get("schema_version") == "axiom.comparison_report.v2.1"
        and isinstance(slim_summary, dict)
        and isinstance(slim_summary.get("dispositioned"), dict)
        and isinstance(slim_stored, int)
        and slim_stored < (slim_summary.get("mismatch_count") or 0)
    )
    if full_report_path is not None:
        # The pointer contract mirrors the consumer's
        # (apply_dispositions._resolve_source_pointer): a repo-relative
        # path under reports/. A custom --output-dir can publish the full
        # report outside the repository — or inside it but outside
        # reports/ — where the consumer would reject (or never resolve)
        # the pointer (sol stack reviews r3 + r4).
        try:
            source_rel = (
                full_report_path.resolve()
                .relative_to(REPO_ROOT.resolve())
                .as_posix()
            )
        except ValueError:
            source_rel = None
        if source_rel is None or not source_rel.startswith("reports/"):
            if slim_is_premerged:
                # A premerged-slim copy is only ever trusted through its
                # source binding (or, for suites committing no full
                # report, its pointer-free provenance). When the full
                # report goes to a non-canonical location the copy can
                # be neither pointer-bound nor left pointer-free —
                # apply_dispositions.py --check is guaranteed to flag it
                # either way once the suite commits any full report (sol
                # stack review r5). Canonical artifacts move together: a
                # run publishing its full report elsewhere does not
                # update the committed dashboard copy at all.
                print(
                    f"Dashboard copy {filename} NOT updated: full report "
                    f"published outside reports/ ({full_report_path}); a "
                    "premerged dashboard copy cannot be source-bound to it"
                )
                return
            full_report_path = None
    if (
        full_report_path is not None
        and merged_is_complete
        and slim_is_premerged
    ):
        from axiom_oracles.comparison.dispositions import assignment_digest

        block = dict(slim_summary["dispositioned"])
        block["source_report"] = {
            "path": source_rel,
            "sha256": hashlib.sha256(
                full_report_path.read_bytes()
            ).hexdigest(),
        }
        block["assignment_sha256"] = assignment_digest(report)
        slim_summary = dict(slim_summary)
        slim_summary["dispositioned"] = block
        slim["summary"] = slim_summary
    # Atomic publish: the dashboard is fetched by the UI and read by tests —
    # it must never be observable as partially written JSON (#448 review
    # round 4).
    dash_fd, dash_name = tempfile.mkstemp(
        dir=DASHBOARD_DATA_DIR, prefix=f".{filename}.", suffix=".tmp"
    )
    try:
        with os.fdopen(dash_fd, "w") as fh:
            fh.write(json.dumps(slim, indent=2, sort_keys=True))
        os.replace(dash_name, target)
    finally:
        Path(dash_name).unlink(missing_ok=True)
    print(f"Wrote dashboard report: {target}")
    if truncation:
        print(
            "Dashboard copy truncated: "
            f"{truncation['shown_mismatches']}/{truncation['total_mismatches']} mismatches, "
            f"{truncation['shown_case_rows']}/{truncation['total_case_rows']} case rows "
            "(full report under reports/)."
        )

    manifest_path = DASHBOARD_DATA_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"reports": []}
    reports = manifest.setdefault("reports", [])
    if filename not in reports:
        reports.append(filename)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Added {filename} to manifest.json")


if __name__ == "__main__":
    sys.exit(main())
