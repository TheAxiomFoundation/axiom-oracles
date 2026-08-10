#!/usr/bin/env python3
"""Generate one federal tax-liability case-grid report.

Each invocation selects exactly one policy.  The selected policy's reviewed
case grid is evaluated independently:

* ``axiom`` reads the expected value from that policy's engine-verified
  RuleSpec companion fixture plus any reviewed repo-owned extension; and
* ``policyengine`` builds a fresh PolicyEngine-US ``Simulation`` at tax year
  2026 from the same case inputs.

RuleSpec checkout locations are supplied by the comparison registry through
repeatable ``--rulespec-root`` arguments.  No sibling checkout is hardcoded.

Run through the registry so the reviewed PolicyEngine pins and dashboard
provenance are applied:

    uv run scripts/run_comparison.py us-niit-grid --summary
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field as dataclass_field
from decimal import Decimal
from importlib.metadata import version as distribution_version
from math import isfinite
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import report_json_text  # noqa: E402
from axiom_oracles.bridges import load_policyengine_registry  # noqa: E402

VALIDATION_YEAR = 2026
ENGINE_VERSIONS = {
    "policyengine": "4.18.9",
    "policyengine_core": "3.30.3",
    "policyengine_us": "1.767.3",
}


@dataclass(frozen=True)
class FederalCase:
    """One contract case and its neutral, auditable input values."""

    case_id: str
    filing_status: str
    inputs: Mapping[str, Any]


@dataclass(frozen=True)
class ComparisonBinding:
    """One scored Axiom concept and its reviewed PolicyEngine target."""

    concept: str
    policyengine_target: str
    comparison: str
    case_ids: tuple[str, ...] = ()
    case_id_suffix: str = ""
    tolerance: float | None = None


@dataclass(frozen=True)
class PolicyConfig:
    """All policy-specific choices required by the generic generator."""

    key: str
    suite: str
    title: str
    axiom_module_ref: str
    fixture_path: Path
    axiom_output: str
    pe_output_variables: tuple[str, ...]
    pe_boundary: str
    cases: tuple[FederalCase, ...]
    pe_situation: Callable[
        [FederalCase, Mapping[str, float]],
        dict[str, Any],
    ]
    fixture_input_validator: Callable[[FederalCase, Mapping[str, Any]], None]
    pe_diagnostic_variables: tuple[str, ...] = ()
    pe_parameter_validator: Callable[[Any], None] | None = None
    supplemental_fixture_paths: tuple[Path, ...] = ()
    comparison_bindings: tuple[ComparisonBinding, ...] = ()
    axiom_bridge_outputs: Mapping[str, str] = dataclass_field(default_factory=dict)
    axiom_diagnostic_outputs: Mapping[str, str] = dataclass_field(default_factory=dict)
    rulespec_domain_inputs: Mapping[str, Any] = dataclass_field(default_factory=dict)
    rulespec_only_inputs: tuple[str, ...] = ()
    pe_input_variables: tuple[str, ...] = ()
    tolerance: float = 0.01
    relative_tolerance: float = 0.0


def _case(
    case_id: str,
    filing_status: str,
    **inputs: Any,
) -> FederalCase:
    return FederalCase(case_id, filing_status, inputs)


_SALT_MODULE = "us:policies/income_tax/salt_deduction_pipeline"
_ITEMIZED_MODULE = "us:policies/income_tax/itemized_taxable_income_deductions_pipeline"
_SALT_SECTION_911_BRIDGE = f"{_SALT_MODULE}#federal_section_911_exclusion_for_salt_magi"
_ITEMIZED_BEFORE_SECTION_68 = (
    f"{_ITEMIZED_MODULE}"
    "#itemized_deductions_otherwise_allowable_after_other_limitations"
)
_ITEMIZED_SECTION_68_REDUCTION = f"{_ITEMIZED_MODULE}#federal_section_68_reduction"
_PE_STRUCTURAL_INPUTS = (
    "age",
    "filing_status",
    "is_separated",
    "is_tax_unit_dependent",
    "state_code",
)


def _salt_case(
    case_id: str,
    filing_status: str,
    *,
    adjusted_gross_income: float,
    state_and_local_sales_or_income_tax: float,
    real_estate_taxes: float = 0,
    state_and_local_personal_property_tax: float = 0,
    section_911_exclusions: tuple[float, ...] = (0,),
) -> FederalCase:
    return _case(
        case_id,
        filing_status,
        adjusted_gross_income=adjusted_gross_income,
        state_and_local_sales_or_income_tax=state_and_local_sales_or_income_tax,
        state_and_local_personal_property_tax=(state_and_local_personal_property_tax),
        real_estate_taxes=real_estate_taxes,
        section_911_exclusions=section_911_exclusions,
    )


_SALT_DEDUCTION_CASES = (
    _salt_case(
        "salt-single-base",
        "single",
        adjusted_gross_income=100_000,
        state_and_local_sales_or_income_tax=8_000,
        real_estate_taxes=2_000,
    ),
    _salt_case(
        "salt-single-at-cap",
        "single",
        adjusted_gross_income=100_000,
        state_and_local_sales_or_income_tax=30_400,
        real_estate_taxes=10_000,
    ),
    _salt_case(
        "salt-single-over-cap",
        "single",
        adjusted_gross_income=100_000,
        state_and_local_sales_or_income_tax=40_000,
        real_estate_taxes=10_000,
    ),
    _salt_case(
        "salt-joint-cap",
        "joint",
        adjusted_gross_income=150_000,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-hoh-cap",
        "head_of_household",
        adjusted_gross_income=150_000,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-surviving-cap",
        "surviving_spouse",
        adjusted_gross_income=150_000,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-mfs-cap",
        "separate",
        adjusted_gross_income=100_000,
        state_and_local_sales_or_income_tax=25_000,
    ),
    _salt_case(
        "salt-single-phaseout-start",
        "single",
        adjusted_gross_income=505_000,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-single-phaseout-plus-one",
        "single",
        adjusted_gross_income=505_001,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-single-phaseout-mid",
        "single",
        adjusted_gross_income=600_000,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-single-floor",
        "single",
        adjusted_gross_income=607_000,
        state_and_local_sales_or_income_tax=50_000,
    ),
    _salt_case(
        "salt-mfs-phaseout-mid",
        "separate",
        adjusted_gross_income=300_000,
        state_and_local_sales_or_income_tax=30_000,
    ),
    _salt_case(
        "salt-mfs-floor",
        "separate",
        adjusted_gross_income=310_000,
        state_and_local_sales_or_income_tax=30_000,
    ),
    _salt_case(
        "salt-low-agi-engine-cap",
        "single",
        adjusted_gross_income=5_000,
        state_and_local_sales_or_income_tax=10_000,
    ),
    _salt_case(
        "salt-magi-911-addback",
        "single",
        adjusted_gross_income=500_000,
        state_and_local_sales_or_income_tax=50_000,
        section_911_exclusions=(4_000, 6_000),
    ),
    _salt_case(
        "salt-personal-property-tax-probe",
        "single",
        adjusted_gross_income=100_000,
        state_and_local_sales_or_income_tax=0,
        state_and_local_personal_property_tax=4_000,
    ),
)


def _itemized_case(
    case_id: str,
    filing_status: str,
    *,
    adjusted_gross_income: float,
    taxable_income_determined_without_section_68: float,
    charitable_deduction: float = 0,
    interest_deduction: float = 0,
    state_and_local_sales_or_income_tax: float = 0,
    real_estate_taxes: float = 0,
    medical_expense_deduction: float = 0,
    casualty_loss_deduction: float = 0,
) -> FederalCase:
    return _case(
        case_id,
        filing_status,
        adjusted_gross_income=adjusted_gross_income,
        state_and_local_sales_or_income_tax=state_and_local_sales_or_income_tax,
        state_and_local_personal_property_tax=0,
        real_estate_taxes=real_estate_taxes,
        charitable_deduction=charitable_deduction,
        interest_deduction=interest_deduction,
        medical_expense_deduction=medical_expense_deduction,
        casualty_loss_deduction=casualty_loss_deduction,
        misc_deduction=0,
        taxable_income_determined_without_section_68=(
            taxable_income_determined_without_section_68
        ),
        section_911_exclusions=(),
    )


_ITEMIZED_DEDUCTION_CASES = (
    _itemized_case(
        "itemized-zero",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=100_000,
    ),
    _itemized_case(
        "itemized-charity-only",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=90_000,
        charitable_deduction=10_000,
    ),
    _itemized_case(
        "itemized-interest-only",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=92_000,
        interest_deduction=8_000,
    ),
    _itemized_case(
        "itemized-salt-only",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=90_000,
        state_and_local_sales_or_income_tax=8_000,
        real_estate_taxes=2_000,
    ),
    _itemized_case(
        "itemized-medical-only",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=98_000,
        medical_expense_deduction=2_000,
    ),
    _itemized_case(
        "itemized-casualty-completed",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=97_000,
        casualty_loss_deduction=3_000,
    ),
    _itemized_case(
        "itemized-mixed",
        "single",
        adjusted_gross_income=100_000,
        taxable_income_determined_without_section_68=70_000,
        charitable_deduction=10_000,
        interest_deduction=8_000,
        state_and_local_sales_or_income_tax=8_000,
        real_estate_taxes=2_000,
        medical_expense_deduction=2_000,
    ),
    _itemized_case(
        "itemized-68-single-at",
        "single",
        adjusted_gross_income=640_600,
        taxable_income_determined_without_section_68=590_600,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-single-plus-one",
        "single",
        adjusted_gross_income=640_601,
        taxable_income_determined_without_section_68=590_601,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-single-income-lesser",
        "single",
        adjusted_gross_income=650_600,
        taxable_income_determined_without_section_68=600_600,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-single-deduction-lesser",
        "single",
        adjusted_gross_income=800_000,
        taxable_income_determined_without_section_68=750_000,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-hoh-at",
        "head_of_household",
        adjusted_gross_income=640_600,
        taxable_income_determined_without_section_68=590_600,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-joint-at",
        "joint",
        adjusted_gross_income=768_700,
        taxable_income_determined_without_section_68=718_700,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-surviving-at",
        "surviving_spouse",
        adjusted_gross_income=768_700,
        taxable_income_determined_without_section_68=718_700,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-mfs-at",
        "separate",
        adjusted_gross_income=384_350,
        taxable_income_determined_without_section_68=334_350,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-other-deduction-base",
        "single",
        adjusted_gross_income=700_000,
        taxable_income_determined_without_section_68=550_000,
        charitable_deduction=50_000,
    ),
    _itemized_case(
        "itemized-68-rational-rate",
        "single",
        adjusted_gross_income=10_640_600,
        taxable_income_determined_without_section_68=640_600,
        charitable_deduction=10_000_000,
    ),
)


# GRID-CONTRACT P1, restricted to the five wage-only cases. The merged
# RuleSpec composition fail-closes its combined output when imported federal
# self-employment income is nonzero, so the former positive-SE case is outside
# this suite's reviewed domain until the operative section 1401 authority lands.
_ADDITIONAL_MEDICARE_CASES = (
    _case(
        "amt-single-150k",
        "single",
        primary_wages=150_000,
        spouse_wages=0,
        self_employment_income=0,
    ),
    _case(
        "amt-single-250k",
        "single",
        primary_wages=250_000,
        spouse_wages=0,
        self_employment_income=0,
    ),
    _case(
        "amt-joint-300k",
        "joint",
        primary_wages=150_000,
        spouse_wages=150_000,
        self_employment_income=0,
    ),
    _case(
        "amt-mfs-150k",
        "separate",
        primary_wages=150_000,
        spouse_wages=0,
        self_employment_income=0,
    ),
    _case(
        "amt-joint-450k",
        "joint",
        primary_wages=400_000,
        spouse_wages=50_000,
        self_employment_income=0,
    ),
)


# GRID-CONTRACT P2.
_SELF_EMPLOYMENT_CASES = (
    _case(
        "seca-under-floor",
        "single",
        primary_wages=0,
        spouse_wages=0,
        self_employment_income=400,
    ),
    _case(
        "seca-50k",
        "single",
        primary_wages=0,
        spouse_wages=0,
        self_employment_income=50_000,
    ),
    _case(
        "seca-120k",
        "single",
        primary_wages=0,
        spouse_wages=0,
        self_employment_income=120_000,
    ),
    _case(
        "seca-300k",
        "single",
        primary_wages=0,
        spouse_wages=0,
        self_employment_income=300_000,
    ),
    _case(
        "seca-wage-mix",
        "single",
        primary_wages=100_000,
        spouse_wages=0,
        self_employment_income=120_000,
    ),
    _case(
        "seca-joint-200k",
        "joint",
        primary_wages=0,
        spouse_wages=0,
        self_employment_income=200_000,
    ),
)


# GRID-CONTRACT P3.  Rent in this closed grid is passive.  No case has a
# section 911 exclusion, so NIIT MAGI equals the naturally derived AGI.
_NIIT_CASES = (
    _case(
        "niit-under",
        "single",
        primary_wages=150_000,
        taxable_interest_income=20_000,
        ordinary_dividend_income=0,
        long_term_capital_gains=0,
        passive_rental_income=0,
    ),
    _case(
        "niit-single-mixed",
        "single",
        primary_wages=190_000,
        taxable_interest_income=10_000,
        ordinary_dividend_income=15_000,
        long_term_capital_gains=15_000,
        passive_rental_income=0,
    ),
    _case(
        "niit-joint-gains",
        "joint",
        primary_wages=200_000,
        taxable_interest_income=0,
        ordinary_dividend_income=0,
        long_term_capital_gains=100_000,
        passive_rental_income=0,
    ),
    _case(
        "niit-mfs",
        "separate",
        primary_wages=150_000,
        taxable_interest_income=10_000,
        ordinary_dividend_income=10_000,
        long_term_capital_gains=10_000,
        passive_rental_income=0,
    ),
    _case(
        "niit-inv-only",
        "single",
        primary_wages=0,
        taxable_interest_income=100_000,
        ordinary_dividend_income=100_000,
        long_term_capital_gains=300_000,
        passive_rental_income=0,
    ),
    _case(
        "niit-rental",
        "joint",
        primary_wages=240_000,
        taxable_interest_income=0,
        ordinary_dividend_income=0,
        long_term_capital_gains=0,
        passive_rental_income=60_000,
    ),
)


# GRID-CONTRACT P4.  Section 36B uses the prior-year (2025) contiguous-US
# poverty guidelines for 2026 coverage: $15,650 for one person plus $5,500 for
# each additional person.  Dollar MAGI values are explicit so both engines bind
# identical inputs rather than independently recomputing percentages.
_ACA_PTC_CASES = (
    _case(
        "ptc-150fpl-family4",
        "joint",
        household_size=4,
        magi=48_225,
        fpl_percentage=150,
        poverty_line=32_150,
        slcsp=18_000,
        enrolled_premium=17_000,
        coverage_months=12,
    ),
    _case(
        "ptc-250fpl-single",
        "single",
        household_size=1,
        magi=39_125,
        fpl_percentage=250,
        poverty_line=15_650,
        slcsp=6_000,
        enrolled_premium=5_800,
        coverage_months=12,
    ),
    _case(
        "ptc-300fpl-joint",
        "joint",
        household_size=2,
        magi=63_450,
        fpl_percentage=300,
        poverty_line=21_150,
        slcsp=14_000,
        enrolled_premium=15_000,
        coverage_months=12,
    ),
    _case(
        "ptc-380fpl-single",
        "single",
        household_size=1,
        magi=59_470,
        fpl_percentage=380,
        poverty_line=15_650,
        slcsp=7_500,
        enrolled_premium=7_000,
        coverage_months=12,
    ),
    _case(
        "ptc-410fpl-single",
        "single",
        household_size=1,
        magi=64_165,
        fpl_percentage=410,
        poverty_line=15_650,
        slcsp=7_500,
        enrolled_premium=7_000,
        coverage_months=12,
    ),
    _case(
        "ptc-95fpl-single",
        "single",
        household_size=1,
        magi=14_867.50,
        fpl_percentage=95,
        poverty_line=15_650,
        slcsp=5_000,
        enrolled_premium=4_800,
        coverage_months=12,
    ),
)


# GRID-CONTRACT P5 plus the companion's five boundary diagnostics.  The
# current-law 2026 thresholds and widths are those published in Revenue
# Procedure 2025-32, section 4.26.  The Axiom boundary separately carries
# active-business QBI for the section 199A(i) minimum; PolicyEngine-US does not
# expose that narrower fact, which the `qbid-above-nowages` case diagnoses.
def _qbid_case(
    case_id: str,
    filing_status: str,
    *,
    qbi: float,
    w2_wages: float,
    taxable_income_before_qbid: float,
    reit_dividends: float = 0,
    ptp_income: float = 0,
    ubia: float = 0,
    active_business_qbi: float = 0,
    net_capital_gain: float = 0,
) -> FederalCase:
    return _case(
        case_id,
        filing_status,
        qbi=qbi,
        w2_wages=w2_wages,
        ubia=ubia,
        reit_dividends=reit_dividends,
        ptp_income=ptp_income,
        taxable_income_before_qbid=taxable_income_before_qbid,
        active_business_qbi=active_business_qbi,
        net_capital_gain=net_capital_gain,
    )


_QBID_CASES = (
    _qbid_case(
        "qbid-ti-limited",
        "single",
        qbi=80_000,
        w2_wages=40_000,
        taxable_income_before_qbid=60_000,
    ),
    _qbid_case(
        "qbid-basic-100k",
        "single",
        qbi=100_000,
        w2_wages=50_000,
        taxable_income_before_qbid=150_000,
    ),
    _qbid_case(
        "qbid-joint-150k",
        "joint",
        qbi=150_000,
        w2_wages=60_000,
        taxable_income_before_qbid=250_000,
    ),
    _qbid_case(
        "qbid-phasein",
        "single",
        qbi=200_000,
        w2_wages=30_000,
        taxable_income_before_qbid=239_250,
    ),
    _qbid_case(
        "qbid-above-nowages",
        "single",
        qbi=300_000,
        w2_wages=0,
        taxable_income_before_qbid=276_751,
    ),
    _qbid_case(
        "qbid-reit-only",
        "joint",
        qbi=0,
        w2_wages=0,
        reit_dividends=20_000,
        taxable_income_before_qbid=100_000,
    ),
    _qbid_case(
        "qbid-zero",
        "single",
        qbi=0,
        w2_wages=0,
        taxable_income_before_qbid=0,
    ),
    _qbid_case(
        "qbid-single-at-threshold",
        "single",
        qbi=150_000,
        w2_wages=0,
        taxable_income_before_qbid=201_750,
    ),
    _qbid_case(
        "qbid-single-one-dollar-over-threshold",
        "single",
        qbi=150_000,
        w2_wages=0,
        taxable_income_before_qbid=201_751,
    ),
    _qbid_case(
        "qbid-active-minimum",
        "single",
        qbi=1_000,
        w2_wages=0,
        taxable_income_before_qbid=10_000,
        active_business_qbi=1_000,
    ),
    _qbid_case(
        "qbid-net-capital-gain-limit",
        "single",
        qbi=100_000,
        w2_wages=50_000,
        taxable_income_before_qbid=100_000,
        net_capital_gain=30_000,
    ),
)


# GRID-CONTRACT P6 plus the merged Notice 2025-67 boundary, filing-status,
# exclusion, contribution-cap, and eligibility diagnostics. The selected PE
# potential variable is the companion's pre-section-26 statutory boundary; the
# separately calculated public variable is retained only as a diagnostic.
def _savers_case(
    case_id: str,
    filing_status: str,
    *,
    adjusted_gross_income: float,
    primary_contributions: float,
    spouse_contributions: float = 0,
    section_911_excluded_income: float = 0,
    section_931_excluded_income: float = 0,
    section_933_excluded_income: float = 0,
    primary_age: int = 30,
    primary_is_student: bool = False,
    primary_is_dependent: bool = False,
) -> FederalCase:
    thresholds = {
        "single": (24_250, 26_250, 40_250),
        "joint": (48_500, 52_500, 80_500),
        "head_of_household": (36_375, 39_375, 60_375),
        "separate": (24_250, 26_250, 40_250),
        "surviving_spouse": (24_250, 26_250, 40_250),
    }[filing_status]
    return _case(
        case_id,
        filing_status,
        adjusted_gross_income=adjusted_gross_income,
        primary_contributions=primary_contributions,
        spouse_contributions=spouse_contributions,
        section_911_excluded_income=section_911_excluded_income,
        section_931_excluded_income=section_931_excluded_income,
        section_933_excluded_income=section_933_excluded_income,
        primary_age=primary_age,
        primary_is_student=primary_is_student,
        primary_is_dependent=primary_is_dependent,
        spouse_age=30,
        spouse_is_student=False,
        spouse_is_dependent=False,
        first_threshold=thresholds[0],
        second_threshold=thresholds[1],
        third_threshold=thresholds[2],
    )


_SAVERS_CREDIT_CASES = (
    _savers_case(
        "single-one-below-50-percent-limit",
        "single",
        adjusted_gross_income=24_249,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-at-50-percent-limit-inclusive",
        "single",
        adjusted_gross_income=24_250,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-one-over-50-percent-limit",
        "single",
        adjusted_gross_income=24_251,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-one-below-20-percent-limit",
        "single",
        adjusted_gross_income=26_249,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-at-20-percent-limit-inclusive",
        "single",
        adjusted_gross_income=26_250,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-one-over-20-percent-limit",
        "single",
        adjusted_gross_income=26_251,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-one-below-10-percent-limit",
        "single",
        adjusted_gross_income=40_249,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-at-10-percent-limit-inclusive",
        "single",
        adjusted_gross_income=40_250,
        primary_contributions=2_000,
    ),
    _savers_case(
        "single-one-over-10-percent-limit",
        "single",
        adjusted_gross_income=40_251,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-one-below-50-percent-limit",
        "joint",
        adjusted_gross_income=48_499,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-at-50-percent-limit-inclusive",
        "joint",
        adjusted_gross_income=48_500,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-one-over-50-percent-limit",
        "joint",
        adjusted_gross_income=48_501,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-one-below-20-percent-limit",
        "joint",
        adjusted_gross_income=52_499,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-at-20-percent-limit-inclusive",
        "joint",
        adjusted_gross_income=52_500,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-one-over-20-percent-limit",
        "joint",
        adjusted_gross_income=52_501,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-one-below-10-percent-limit",
        "joint",
        adjusted_gross_income=80_499,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-at-10-percent-limit-inclusive",
        "joint",
        adjusted_gross_income=80_500,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-one-over-10-percent-limit",
        "joint",
        adjusted_gross_income=80_501,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-one-below-50-percent-limit",
        "head_of_household",
        adjusted_gross_income=36_374,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-at-50-percent-limit-inclusive",
        "head_of_household",
        adjusted_gross_income=36_375,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-one-over-50-percent-limit",
        "head_of_household",
        adjusted_gross_income=36_376,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-one-below-20-percent-limit",
        "head_of_household",
        adjusted_gross_income=39_374,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-at-20-percent-limit-inclusive",
        "head_of_household",
        adjusted_gross_income=39_375,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-one-over-20-percent-limit",
        "head_of_household",
        adjusted_gross_income=39_376,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-one-below-10-percent-limit",
        "head_of_household",
        adjusted_gross_income=60_374,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-at-10-percent-limit-inclusive",
        "head_of_household",
        adjusted_gross_income=60_375,
        primary_contributions=2_000,
    ),
    _savers_case(
        "head-of-household-one-over-10-percent-limit",
        "head_of_household",
        adjusted_gross_income=60_376,
        primary_contributions=2_000,
    ),
    _savers_case(
        "married-filing-separately-uses-all-other-limits",
        "separate",
        adjusted_gross_income=24_250,
        primary_contributions=2_000,
        spouse_contributions=2_000,
    ),
    _savers_case(
        "surviving-spouse-uses-all-other-limits",
        "surviving_spouse",
        adjusted_gross_income=24_250,
        primary_contributions=2_000,
    ),
    _savers_case(
        "section-911-add-back-crosses-inclusive-limit",
        "single",
        adjusted_gross_income=24_250,
        section_911_excluded_income=1,
        primary_contributions=2_000,
    ),
    _savers_case(
        "joint-separate-cap-for-each-spouse",
        "joint",
        adjusted_gross_income=40_000,
        primary_contributions=5_000,
        spouse_contributions=5_000,
    ),
    _savers_case(
        "age-screen",
        "single",
        adjusted_gross_income=20_000,
        primary_contributions=2_000,
        primary_age=17,
    ),
    _savers_case(
        "student-screen",
        "single",
        adjusted_gross_income=20_000,
        primary_contributions=2_000,
        primary_is_student=True,
    ),
    _savers_case(
        "dependent-screen",
        "single",
        adjusted_gross_income=20_000,
        primary_contributions=2_000,
        primary_is_dependent=True,
    ),
)


# GRID-CONTRACT P7 plus three expressible companion diagnostics.  PolicyEngine
# exposes a collapsed `retired_on_total_disability` fact; the fixture validator
# proves every predicate needed to derive that fact before the PE situation
# sets it.  The empty-relation `eld-no-qualified-individual` diagnostic is
# intentionally omitted because a PE TaxUnit must contain a Person and no
# exact age/disability facts exist for that invented member.
def _elderly_disabled_case(
    case_id: str,
    filing_status: str,
    *,
    adjusted_gross_income: float,
    nontaxable_social_security: float,
    primary_age: int = 66,
    spouse_age: int | None = None,
    primary_is_disabled: bool = False,
    primary_disability_income: float = 0,
) -> FederalCase:
    return _case(
        case_id,
        filing_status,
        adjusted_gross_income=adjusted_gross_income,
        nontaxable_social_security=nontaxable_social_security,
        primary_age=primary_age,
        spouse_age=spouse_age,
        primary_retired_on_disability=primary_is_disabled,
        primary_unable_substantial_gainful_activity=primary_is_disabled,
        primary_medically_determinable_impairment=primary_is_disabled,
        primary_impairment_expected_to_result_in_death=False,
        primary_impairment_duration_months=12 if primary_is_disabled else 0,
        primary_disability_proof_furnished=primary_is_disabled,
        primary_disability_income=primary_disability_income,
    )


_ELDERLY_DISABLED_CASES = (
    _elderly_disabled_case(
        "eld-basic",
        "single",
        adjusted_gross_income=8_000,
        nontaxable_social_security=2_000,
    ),
    _elderly_disabled_case(
        "eld-agi-reduce",
        "single",
        adjusted_gross_income=12_000,
        nontaxable_social_security=0,
    ),
    _elderly_disabled_case(
        "eld-joint-both",
        "joint",
        adjusted_gross_income=15_000,
        nontaxable_social_security=3_000,
        spouse_age=66,
    ),
    _elderly_disabled_case(
        "eld-zero-high-agi",
        "single",
        adjusted_gross_income=30_000,
        nontaxable_social_security=0,
    ),
    _elderly_disabled_case(
        "eld-ss-wipes",
        "single",
        adjusted_gross_income=8_000,
        nontaxable_social_security=6_000,
    ),
    _elderly_disabled_case(
        "eld-joint-one-65",
        "joint",
        adjusted_gross_income=12_000,
        nontaxable_social_security=1_000,
        spouse_age=60,
    ),
    _elderly_disabled_case(
        "eld-disabled-under-65",
        "single",
        adjusted_gross_income=0,
        nontaxable_social_security=0,
        primary_age=60,
        primary_is_disabled=True,
        primary_disability_income=2_000,
    ),
    _elderly_disabled_case(
        "eld-at-agi-threshold",
        "single",
        adjusted_gross_income=7_500,
        nontaxable_social_security=0,
    ),
    _elderly_disabled_case(
        "eld-two-dollars-over-agi-threshold",
        "single",
        adjusted_gross_income=7_502,
        nontaxable_social_security=0,
    ),
)


# GRID-CONTRACT P8 plus six companion diagnostics, including the separately
# identified liability-cap case.  Unlike the other two nonrefundable credits,
# the Axiom compose exposes the same final boundary as PE, so all twelve
# companion cases are directly comparable.
def _llc_case(
    case_id: str,
    filing_status: str,
    *,
    modified_adjusted_gross_income: float,
    qualified_expenses: tuple[float, ...],
    income_tax_before_credits: float = 10_000,
) -> FederalCase:
    return _case(
        case_id,
        filing_status,
        modified_adjusted_gross_income=modified_adjusted_gross_income,
        qualified_expenses=qualified_expenses,
        income_tax_before_credits=income_tax_before_credits,
    )


_LLC_CASES = (
    _llc_case(
        "llc-basic",
        "single",
        modified_adjusted_gross_income=50_000,
        qualified_expenses=(4_000,),
    ),
    _llc_case(
        "llc-cap",
        "single",
        modified_adjusted_gross_income=50_000,
        qualified_expenses=(15_000,),
    ),
    _llc_case(
        "llc-phaseout-mid",
        "single",
        modified_adjusted_gross_income=85_000,
        qualified_expenses=(10_000,),
    ),
    _llc_case(
        "llc-over",
        "single",
        modified_adjusted_gross_income=90_001,
        qualified_expenses=(10_000,),
    ),
    _llc_case(
        "llc-joint-mid",
        "joint",
        modified_adjusted_gross_income=170_000,
        qualified_expenses=(8_000,),
    ),
    _llc_case(
        "llc-small",
        "joint",
        modified_adjusted_gross_income=100_000,
        qualified_expenses=(900,),
    ),
    _llc_case(
        "llc-zero-expenses",
        "single",
        modified_adjusted_gross_income=50_000,
        qualified_expenses=(0,),
    ),
    _llc_case(
        "llc-at-phaseout-start",
        "single",
        modified_adjusted_gross_income=80_000,
        qualified_expenses=(10_000,),
    ),
    _llc_case(
        "llc-one-dollar-over-phaseout-start",
        "single",
        modified_adjusted_gross_income=80_001,
        qualified_expenses=(10_000,),
    ),
    _llc_case(
        "llc-at-phaseout-end",
        "single",
        modified_adjusted_gross_income=90_000,
        qualified_expenses=(10_000,),
    ),
    _llc_case(
        "llc-aggregate-cap",
        "single",
        modified_adjusted_gross_income=50_000,
        qualified_expenses=(6_000, 6_000),
    ),
    _llc_case(
        "llc-liability-cap-diagnostic",
        "single",
        modified_adjusted_gross_income=50_000,
        qualified_expenses=(10_000,),
        income_tax_before_credits=500,
    ),
)


def _person(
    *,
    age: int = 40,
    **annual_inputs: float | int | str | bool,
) -> dict[str, dict[int, float | int | str | bool]]:
    values: dict[str, dict[int, float | int | str | bool]] = {
        "age": {VALIDATION_YEAR: age},
    }
    for variable, value in annual_inputs.items():
        values[variable] = {VALIDATION_YEAR: value}
    return values


def _tax_situation(
    case: FederalCase,
    *,
    primary_inputs: Mapping[str, Any],
    spouse_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one tax unit while deriving filing status from relationships."""
    head_inputs: dict[str, float | int | str | bool] = dict(primary_inputs)
    if case.filing_status == "separate":
        head_inputs["is_separated"] = True
    people = {"head": _person(**head_inputs)}
    members = ["head"]
    if case.filing_status == "joint":
        people["spouse"] = _person(**dict(spouse_inputs or {}))
        members.append("spouse")
    if case.filing_status in {"head_of_household", "surviving_spouse"}:
        people["child"] = _person(age=10, is_tax_unit_dependent=True)
        members.append("child")
    situation = {
        "people": people,
        "tax_units": {"tax_unit": {"members": members}},
        "families": {"family": {"members": members}},
        "spm_units": {"spm_unit": {"members": members}},
        "households": {
            "household": {
                "members": members,
                "state_code": {VALIDATION_YEAR: "TX"},
            }
        },
    }
    explicit_statuses = {
        "head_of_household": "HEAD_OF_HOUSEHOLD",
        "surviving_spouse": "SURVIVING_SPOUSE",
    }
    if case.filing_status in explicit_statuses:
        situation["tax_units"]["tax_unit"]["filing_status"] = {
            VALIDATION_YEAR: explicit_statuses[case.filing_status]
        }
    return situation


def _require_bridge_output_values(
    *,
    suite: str,
    case_id: str,
    bridge_outputs: Mapping[str, float],
    expected_keys: tuple[str, ...],
) -> dict[str, float]:
    actual_keys = set(bridge_outputs)
    expected = set(expected_keys)
    missing = sorted(expected - actual_keys)
    unexpected = sorted(actual_keys - expected)
    if missing or unexpected:
        raise ValueError(
            f"{suite}: case {case_id!r} bridge outputs differ; "
            f"missing={missing}, unexpected={unexpected}"
        )
    values: dict[str, float] = {}
    for key in expected_keys:
        value = bridge_outputs[key]
        if isinstance(value, bool) or not isinstance(
            value,
            int | float | Decimal,
        ):
            raise ValueError(
                f"{suite}: case {case_id!r} bridge output {key!r} must "
                f"be numeric; got {value!r}"
            )
        values[key] = float(value)
    return values


def _no_bridge_situation(
    builder: Callable[[FederalCase], dict[str, Any]],
) -> Callable[[FederalCase, Mapping[str, float]], dict[str, Any]]:
    def build(
        case: FederalCase,
        bridge_outputs: Mapping[str, float],
    ) -> dict[str, Any]:
        _require_bridge_output_values(
            suite="federal-tax-liability-grid",
            case_id=case.case_id,
            bridge_outputs=bridge_outputs,
            expected_keys=(),
        )
        return builder(case)

    return build


def _salt_situation(
    case: FederalCase,
    bridge_outputs: Mapping[str, float],
) -> dict[str, Any]:
    values = _require_bridge_output_values(
        suite="us-salt-deduction-grid",
        case_id=case.case_id,
        bridge_outputs=bridge_outputs,
        expected_keys=(_SALT_SECTION_911_BRIDGE,),
    )
    inputs = case.inputs
    situation = _tax_situation(
        case,
        primary_inputs={
            "real_estate_taxes": inputs["real_estate_taxes"],
        },
        spouse_inputs={},
    )
    tax_unit = situation["tax_units"]["tax_unit"]
    tax_unit.update(
        {
            "adjusted_gross_income": {VALIDATION_YEAR: inputs["adjusted_gross_income"]},
            "state_and_local_sales_or_income_tax": {
                VALIDATION_YEAR: inputs["state_and_local_sales_or_income_tax"]
            },
            "foreign_earned_income_exclusion": {
                VALIDATION_YEAR: values[_SALT_SECTION_911_BRIDGE]
            },
        }
    )
    return situation


def _itemized_situation(
    case: FederalCase,
    bridge_outputs: Mapping[str, float],
) -> dict[str, Any]:
    _require_bridge_output_values(
        suite="us-itemized-taxable-income-deductions-grid",
        case_id=case.case_id,
        bridge_outputs=bridge_outputs,
        expected_keys=(),
    )
    situation = _tax_situation(
        case,
        primary_inputs={},
        spouse_inputs={},
    )
    inputs = case.inputs
    tax_unit = situation["tax_units"]["tax_unit"]
    tax_unit.update(
        {
            "adjusted_gross_income": {VALIDATION_YEAR: inputs["adjusted_gross_income"]},
            # Section 151 exemptions are zero in 2026. Binding the completed
            # zero keeps PE's AGI-minus-exemptions proxy fully observable.
            "exemptions": {VALIDATION_YEAR: 0},
            "charitable_deduction": {VALIDATION_YEAR: inputs["charitable_deduction"]},
            "interest_deduction": {VALIDATION_YEAR: inputs["interest_deduction"]},
            # These companion cases carry a completed SALT amount below its
            # own cap. Bind that completed component directly, as the itemized
            # aggregate contract requires.
            "salt_deduction": {
                VALIDATION_YEAR: (
                    inputs["state_and_local_sales_or_income_tax"]
                    + inputs["real_estate_taxes"]
                )
            },
            "medical_expense_deduction": {
                VALIDATION_YEAR: inputs["medical_expense_deduction"]
            },
            "casualty_loss_deduction": {
                VALIDATION_YEAR: inputs["casualty_loss_deduction"]
            },
            "misc_deduction": {VALIDATION_YEAR: inputs["misc_deduction"]},
        }
    )
    return situation


def _payroll_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    primary = {
        "employment_income": inputs["primary_wages"],
        "self_employment_income": inputs["self_employment_income"],
    }
    spouse = {"employment_income": inputs["spouse_wages"]}
    return _tax_situation(case, primary_inputs=primary, spouse_inputs=spouse)


def _niit_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    primary = {
        "employment_income": inputs["primary_wages"],
        "taxable_interest_income": inputs["taxable_interest_income"],
        "ordinary_dividend_income": inputs["ordinary_dividend_income"],
        "long_term_capital_gains": inputs["long_term_capital_gains"],
        # PolicyEngine's input is broad; the contract declares this rent passive.
        "rental_income": inputs["passive_rental_income"],
    }
    return _tax_situation(case, primary_inputs=primary, spouse_inputs={})


def _aca_ptc_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    if inputs["coverage_months"] != 12:
        raise ValueError(
            f"{case.case_id}: ACA PTC grid requires exactly 12 coverage months"
        )
    size = int(inputs["household_size"])
    people: dict[str, dict[str, dict[int, float | int | str | bool]]] = {}
    members: list[str] = []
    for index in range(size):
        if index == 0:
            name, age = "head", 40
        elif index == 1 and case.filing_status == "joint":
            name, age = "spouse", 40
        else:
            name, age = f"child{index}", 10
        people[name] = _person(
            age=age,
            pays_aca_premium=True,
            immigration_status="CITIZEN",
        )
        members.append(name)
    filing_status = "JOINT" if case.filing_status == "joint" else "SINGLE"
    return {
        "people": people,
        "tax_units": {
            "tax_unit": {
                "members": members,
                "filing_status": {VALIDATION_YEAR: filing_status},
                "aca_magi": {VALIDATION_YEAR: inputs["magi"]},
                "slcsp": {VALIDATION_YEAR: inputs["slcsp"]},
                "selected_marketplace_plan_premium_proxy": {
                    VALIDATION_YEAR: inputs["enrolled_premium"]
                },
                "tax_unit_is_filer": {VALIDATION_YEAR: True},
            }
        },
        "families": {"family": {"members": members}},
        "spm_units": {"spm_unit": {"members": members}},
        "households": {
            "household": {
                "members": members,
                "state_code": {VALIDATION_YEAR: "TX"},
            }
        },
    }


def _qbid_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    situation = _tax_situation(
        case,
        primary_inputs={
            # These are the same caller-resolved one-aggregation-group facts
            # consumed by the Axiom compose, rather than raw Schedule C facts.
            "qualified_business_income": inputs["qbi"],
            "w2_wages_from_qualified_business": inputs["w2_wages"],
            "unadjusted_basis_qualified_property": inputs["ubia"],
            "qualified_reit_and_ptp_income": (
                inputs["reit_dividends"] + inputs["ptp_income"]
            ),
            "business_is_sstb": False,
        },
        spouse_inputs={},
    )
    tax_unit = situation["tax_units"]["tax_unit"]
    tax_unit["taxable_income_less_qbid"] = {
        VALIDATION_YEAR: inputs["taxable_income_before_qbid"]
    }
    tax_unit["adjusted_net_capital_gain"] = {
        VALIDATION_YEAR: inputs["net_capital_gain"]
    }
    return situation


def _savers_credit_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    primary = {
        # The companion boundary is already net of testing-period
        # distributions and statutory exceptions.
        "savers_credit_qualified_contributions": inputs["primary_contributions"],
        "is_full_time_student": inputs["primary_is_student"],
        "claimed_as_dependent_on_another_return": inputs["primary_is_dependent"],
    }
    spouse = {
        "savers_credit_qualified_contributions": inputs["spouse_contributions"],
        "is_full_time_student": inputs["spouse_is_student"],
        "claimed_as_dependent_on_another_return": inputs["spouse_is_dependent"],
    }
    situation = _tax_situation(
        case,
        primary_inputs=primary,
        spouse_inputs=spouse,
    )
    situation["people"]["head"]["age"] = {VALIDATION_YEAR: inputs["primary_age"]}
    if case.filing_status == "joint":
        situation["people"]["spouse"]["age"] = {VALIDATION_YEAR: inputs["spouse_age"]}
    tax_unit = situation["tax_units"]["tax_unit"]
    tax_unit["adjusted_gross_income"] = {
        VALIDATION_YEAR: inputs["adjusted_gross_income"]
    }
    tax_unit["foreign_earned_income_exclusion"] = {
        VALIDATION_YEAR: inputs["section_911_excluded_income"]
    }
    return situation


def _collapsed_section_22_disability(inputs: Mapping[str, Any]) -> bool:
    return bool(
        inputs["primary_retired_on_disability"]
        and inputs["primary_unable_substantial_gainful_activity"]
        and inputs["primary_medically_determinable_impairment"]
        and (
            inputs["primary_impairment_expected_to_result_in_death"]
            or inputs["primary_impairment_duration_months"] >= 12
        )
        and inputs["primary_disability_proof_furnished"]
    )


def _elderly_disabled_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    primary = {
        "retired_on_total_disability": _collapsed_section_22_disability(inputs),
        "total_disability_payments": inputs["primary_disability_income"],
    }
    spouse = {
        "retired_on_total_disability": False,
        "total_disability_payments": 0,
    }
    situation = _tax_situation(
        case,
        primary_inputs=primary,
        spouse_inputs=spouse,
    )
    situation["people"]["head"]["age"] = {VALIDATION_YEAR: inputs["primary_age"]}
    if case.filing_status == "joint":
        situation["people"]["spouse"]["age"] = {VALIDATION_YEAR: inputs["spouse_age"]}
    tax_unit = situation["tax_units"]["tax_unit"]
    tax_unit["adjusted_gross_income"] = {
        VALIDATION_YEAR: inputs["adjusted_gross_income"]
    }
    # The companion supplies the excluded portion directly.  PE derives the
    # same non-taxable amount as total benefits less this explicit zero.
    tax_unit["tax_unit_social_security"] = {
        VALIDATION_YEAR: inputs["nontaxable_social_security"]
    }
    tax_unit["tax_unit_taxable_social_security"] = {VALIDATION_YEAR: 0}
    return situation


def _llc_situation(case: FederalCase) -> dict[str, Any]:
    inputs = case.inputs
    people: dict[str, dict[str, dict[int, Any]]] = {
        "head": _person(age=40),
    }
    members = ["head"]
    if case.filing_status == "joint":
        people["spouse"] = _person(age=40)
        members.append("spouse")
    for index, expenses in enumerate(inputs["qualified_expenses"], start=1):
        name = f"student{index}"
        people[name] = _person(
            age=20,
            qualified_tuition_expenses=expenses,
            is_tax_unit_dependent=True,
            attends_eligible_educational_institution_for_lifetime_learning_credit=(
                True
            ),
            has_lifetime_learning_credit_1098_t_or_exception=True,
            meets_lifetime_learning_credit_identification_requirements=True,
            # The companion explicitly denies every AOTC election/qualification
            # path, so this collapsed PE fact is false.
            is_eligible_for_american_opportunity_credit=False,
        )
        members.append(name)
    filing_status = "JOINT" if case.filing_status == "joint" else "SINGLE"
    return {
        "people": people,
        "tax_units": {
            "tax_unit": {
                "members": members,
                "filing_status": {VALIDATION_YEAR: filing_status},
                "adjusted_gross_income": {
                    VALIDATION_YEAR: inputs["modified_adjusted_gross_income"]
                },
                "income_tax_before_credits": {
                    VALIDATION_YEAR: inputs["income_tax_before_credits"]
                },
                "foreign_tax_credit": {VALIDATION_YEAR: 0},
                "cdcc": {VALIDATION_YEAR: 0},
                "non_refundable_american_opportunity_credit": {VALIDATION_YEAR: 0},
                "filer_meets_lifetime_learning_credit_identification_requirements": {
                    VALIDATION_YEAR: True
                },
                "is_nonresident_alien_for_lifetime_learning_credit": {
                    VALIDATION_YEAR: False
                },
            }
        },
        "families": {"family": {"members": members}},
        "spm_units": {"spm_unit": {"members": members}},
        "households": {
            "household": {
                "members": members,
                "state_code": {VALIDATION_YEAR: "TX"},
            }
        },
    }


def _same_scalar(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float, Decimal)) and isinstance(
        expected, (int, float, Decimal)
    ):
        return Decimal(str(actual)) == Decimal(str(expected))
    return actual == expected


def _require_fixture_values(
    *,
    suite: str,
    case_id: str,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    for key, expected_value in expected.items():
        if key not in actual:
            raise ValueError(
                f"{suite}: fixture case {case_id!r} is missing input {key!r}"
            )
        if not _same_scalar(actual[key], expected_value):
            raise ValueError(
                f"{suite}: fixture case {case_id!r} input {key!r} is "
                f"{actual[key]!r}; expected {expected_value!r}"
            )


def _require_exact_fixture_values(
    *,
    suite: str,
    case_id: str,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    _require_fixture_values(
        suite=suite,
        case_id=case_id,
        actual=actual,
        expected=expected,
    )
    unexpected = sorted(set(actual) - set(expected))
    if unexpected:
        raise ValueError(
            f"{suite}: fixture case {case_id!r} has unexpected inputs {unexpected}"
        )


_SALT_INPUT_PREFIX = f"{_SALT_MODULE}#input."
_SALT_SECTION_911_RELATION = (
    f"{_SALT_MODULE}#relation.salt_section_911_individual_of_tax_unit"
)
_SALT_DOMAIN_INPUTS = {
    (
        f"{_SALT_INPUT_PREFIX}"
        "completed_personal_tax_amounts_exclude_business_and_section_212_taxes"
    ): True,
    (
        f"{_SALT_INPUT_PREFIX}"
        "completed_personal_tax_amounts_exclude_acquisition_capitalized_taxes"
    ): True,
    (f"{_SALT_INPUT_PREFIX}completed_personal_tax_amounts_are_net_of_refunds"): True,
    (
        f"{_SALT_INPUT_PREFIX}"
        "completed_personal_tax_amounts_exclude_nondeductible_taxes"
    ): True,
    (
        f"{_SALT_INPUT_PREFIX}"
        "section_911_exclusion_relation_includes_every_tax_unit_individual"
    ): True,
}
_ITEMIZED_INPUT_PREFIX = f"{_ITEMIZED_MODULE}#input."
_ITEMIZED_DOMAIN_INPUTS = {
    **_SALT_DOMAIN_INPUTS,
    f"{_ITEMIZED_INPUT_PREFIX}taxpayer_is_individual": True,
    (
        f"{_ITEMIZED_INPUT_PREFIX}no_other_component_in_pe_six_item_itemized_aggregate"
    ): True,
}
_SALT_PERSONAL_PROPERTY_INPUT = (
    f"{_SALT_INPUT_PREFIX}state_and_local_personal_property_tax"
)
_ITEMIZED_SECTION_68_BASE_INPUT = (
    "us:statutes/26/68#input.taxable_income_determined_without_section_68"
)
_NEUTRAL_POSSESSION_INPUTS = {
    (
        "us:statutes/26/931#input."
        "bona_fide_resident_of_specified_possession_during_entire_taxable_year"
    ): False,
    (
        "us:statutes/26/931#input."
        "income_derived_from_sources_within_specified_possessions"
    ): 0,
    (
        "us:statutes/26/931#input."
        "income_effectively_connected_with_trade_or_business_within_"
        "specified_possessions"
    ): 0,
    (
        "us:statutes/26/931#input."
        "amounts_paid_for_services_as_employee_of_united_states_or_agency"
    ): 0,
    (
        "us:statutes/26/933#input."
        "individual_is_bona_fide_resident_of_puerto_rico_during_entire_"
        "taxable_year"
    ): False,
    ("us:statutes/26/933#input.income_derived_from_sources_within_puerto_rico"): 0,
    (
        "us:statutes/26/933#input."
        "amounts_received_for_services_performed_as_employee_of_united_"
        "states_or_agency"
    ): 0,
    ("us:statutes/26/933#input.individual_is_citizen_of_united_states"): False,
    (
        "us:statutes/26/933#input."
        "individual_changes_residence_from_puerto_rico_during_taxable_year"
    ): False,
    (
        "us:statutes/26/933#input.bona_fide_resident_of_puerto_rico_years_before_change"
    ): 0,
    (
        "us:statutes/26/933#input."
        "puerto_rico_source_income_attributable_to_puerto_rican_residence_"
        "period_before_change"
    ): 0,
    (
        "us:statutes/26/933#input."
        "amounts_received_for_services_performed_as_employee_of_united_"
        "states_or_agency_attributable_to_period_before_change"
    ): 0,
}
_FILING_STATUS_CODES = {
    "single": 0,
    "joint": 1,
    "separate": 2,
    "head_of_household": 3,
    "surviving_spouse": 4,
}


def _section_911_fixture_people(
    amounts: tuple[float, ...],
) -> list[dict[str, Any]]:
    prefix = "us:statutes/26/911/a#input."
    return [
        {
            f"{prefix}individual_is_qualified_individual": amount > 0,
            f"{prefix}election_made_for_foreign_earned_income": amount > 0,
            f"{prefix}foreign_earned_income_of_individual": amount,
            f"{prefix}election_made_for_housing_cost_amount": False,
            f"{prefix}housing_cost_amount_of_individual": 0,
        }
        for amount in amounts
    ]


def _validate_salt_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    personal_property_tax = inputs["state_and_local_personal_property_tax"]
    if case.case_id == "salt-personal-property-tax-probe":
        if not _same_scalar(personal_property_tax, 4_000):
            raise ValueError(
                f"{case.case_id}: personal-property probe must bind exactly 4000"
            )
    elif not _same_scalar(personal_property_tax, 0):
        raise ValueError(
            f"{case.case_id}: personal-property tax is RuleSpec-only and may "
            "be nonzero only in salt-personal-property-tax-probe"
        )
    expected = {
        **_NEUTRAL_POSSESSION_INPUTS,
        _SALT_SECTION_911_RELATION: _section_911_fixture_people(
            tuple(inputs["section_911_exclusions"])
        ),
        **_SALT_DOMAIN_INPUTS,
        f"{_SALT_INPUT_PREFIX}filing_status": _FILING_STATUS_CODES[case.filing_status],
        f"{_SALT_INPUT_PREFIX}adjusted_gross_income": inputs["adjusted_gross_income"],
        (f"{_SALT_INPUT_PREFIX}state_and_local_sales_or_income_tax"): inputs[
            "state_and_local_sales_or_income_tax"
        ],
        _SALT_PERSONAL_PROPERTY_INPUT: personal_property_tax,
        f"{_SALT_INPUT_PREFIX}real_estate_taxes": inputs["real_estate_taxes"],
    }
    _require_exact_fixture_values(
        suite="us-salt-deduction-grid",
        case_id=case.case_id,
        actual=actual,
        expected=expected,
    )


def _validate_itemized_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    if inputs["state_and_local_personal_property_tax"] != 0:
        raise ValueError(
            f"{case.case_id}: itemized adopted cases require zero "
            "state_and_local_personal_property_tax"
        )
    expected = {
        **_NEUTRAL_POSSESSION_INPUTS,
        **_SALT_DOMAIN_INPUTS,
        _SALT_SECTION_911_RELATION: [],
        **{
            key: value
            for key, value in _ITEMIZED_DOMAIN_INPUTS.items()
            if key not in _SALT_DOMAIN_INPUTS
        },
        f"{_ITEMIZED_INPUT_PREFIX}misc_deduction": inputs["misc_deduction"],
        f"{_SALT_INPUT_PREFIX}filing_status": _FILING_STATUS_CODES[case.filing_status],
        f"{_SALT_INPUT_PREFIX}adjusted_gross_income": inputs["adjusted_gross_income"],
        (f"{_SALT_INPUT_PREFIX}state_and_local_sales_or_income_tax"): inputs[
            "state_and_local_sales_or_income_tax"
        ],
        _SALT_PERSONAL_PROPERTY_INPUT: 0,
        f"{_SALT_INPUT_PREFIX}real_estate_taxes": inputs["real_estate_taxes"],
        f"{_ITEMIZED_INPUT_PREFIX}charitable_deduction": inputs["charitable_deduction"],
        f"{_ITEMIZED_INPUT_PREFIX}interest_deduction": inputs["interest_deduction"],
        f"{_ITEMIZED_INPUT_PREFIX}medical_expense_deduction": inputs[
            "medical_expense_deduction"
        ],
        f"{_ITEMIZED_INPUT_PREFIX}casualty_loss_deduction": inputs[
            "casualty_loss_deduction"
        ],
        _ITEMIZED_SECTION_68_BASE_INPUT: inputs[
            "taxable_income_determined_without_section_68"
        ],
    }
    _require_exact_fixture_values(
        suite="us-itemized-taxable-income-deductions-grid",
        case_id=case.case_id,
        actual=actual,
        expected=expected,
    )


def _validate_rulespec_input_contract(
    config: PolicyConfig,
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    overlap = set(config.rulespec_domain_inputs) & set(config.rulespec_only_inputs)
    if overlap:
        raise ValueError(
            f"{config.suite}: domain and RuleSpec-only inputs overlap: "
            f"{sorted(overlap)}"
        )
    _require_fixture_values(
        suite=config.suite,
        case_id=case.case_id,
        actual=actual,
        expected=config.rulespec_domain_inputs,
    )
    for key in config.rulespec_only_inputs:
        if key not in actual:
            raise ValueError(
                f"{config.suite}: fixture case {case.case_id!r} is missing "
                f"RuleSpec-only input {key!r}"
            )
        value = actual[key]
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError(
                f"{config.suite}: RuleSpec-only input {key!r} must be scalar"
            )


def _validate_aca_ptc_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    module = "us:policies/aca/ptc_pipeline"
    inputs = case.inputs
    poverty_line = inputs["poverty_line"]
    if Decimal(str(inputs["magi"])) != (
        Decimal(str(poverty_line))
        * Decimal(str(inputs["fpl_percentage"]))
        / Decimal(100)
    ):
        raise ValueError(f"{case.case_id}: explicit MAGI does not equal its FPL case")
    _require_fixture_values(
        suite="us-aca-ptc-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            f"{module}#input.aca_ptc_household_magi": inputs["magi"],
            f"{module}#input.aca_ptc_family_size": inputs["household_size"],
            f"{module}#input.aca_ptc_poverty_line_for_household": poverty_line,
            f"{module}#input.aca_ptc_annual_slcsp_benchmark_premium": inputs["slcsp"],
            f"{module}#input.aca_ptc_annual_enrolled_premium": inputs[
                "enrolled_premium"
            ],
            f"{module}#input.aca_ptc_coverage_month_count": inputs["coverage_months"],
        },
    )


def _validate_additional_medicare_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    pipeline = "us:policies/income_tax/additional_medicare_tax_pipeline"
    status_codes = {"single": 0, "joint": 1, "separate": 2}
    if Decimal(str(case.inputs["self_employment_income"])) != 0:
        raise ValueError(
            f"us-additional-medicare-grid: case {case.case_id!r} is outside "
            "the reviewed wage-only, zero-self-employment domain"
        )
    _require_fixture_values(
        suite="us-additional-medicare-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            "us:statutes/26/3101/b/2#input.filing_status": status_codes[
                case.filing_status
            ],
            f"{pipeline}#input.wages": (
                Decimal(str(case.inputs["primary_wages"]))
                + Decimal(str(case.inputs["spouse_wages"]))
            ),
            f"{pipeline}#input.no_foreign_system_exclusive_se_income": True,
        },
    )
    _validate_self_employment_relation(
        suite="us-additional-medicare-grid",
        case=case,
        actual=actual,
    )


def _validate_self_employment_relation(
    *,
    suite: str,
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    module = "us:policies/income_tax/self_employment_tax_pipeline"
    relation = f"{module}#relation.self_employed_individual_of_tax_unit"
    people = actual.get(relation)
    expected_people = [
        {
            "self_employment_income": case.inputs["self_employment_income"],
            "wages": case.inputs["primary_wages"],
        }
    ]
    if case.filing_status == "joint":
        expected_people.append(
            {
                "self_employment_income": 0,
                "wages": case.inputs["spouse_wages"],
            }
        )
    if not isinstance(people, list) or len(people) != len(expected_people):
        raise ValueError(
            f"{suite}: fixture case {case.case_id!r} relation {relation!r} "
            f"must contain {len(expected_people)} Person input(s)"
        )
    profit_key = f"{module}#input.gross_self_employment_profit"
    wages_key = (
        "us:statutes/26/1402/b#input."
        "wages_paid_to_individual_during_taxable_year_for_section_1401_a"
    )
    domestic_inputs = {
        "us:statutes/26/1402/b#input.individual_is_nonresident_alien": False,
        "us:statutes/26/1402/b#input."
        "agreement_under_social_security_act_section_233_provides_for_individual": (
            False
        ),
        "us:statutes/26/1402/b#input."
        "individual_is_not_united_states_citizen_and_resident_of_puerto_rico_"
        "virgin_islands_guam_or_american_samoa": False,
    }
    for index, (person, expected_person) in enumerate(
        zip(people, expected_people, strict=True)
    ):
        if not isinstance(person, dict):
            raise ValueError(
                f"{suite}: fixture case {case.case_id!r} Person {index} "
                "input is not a mapping"
            )
        _require_fixture_values(
            suite=suite,
            case_id=case.case_id,
            actual=person,
            expected={
                profit_key: expected_person["self_employment_income"],
                wages_key: expected_person["wages"],
                **domestic_inputs,
            },
        )


def _validate_self_employment_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    _validate_self_employment_relation(
        suite="us-seca-grid",
        case=case,
        actual=actual,
    )


def _validate_niit_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    prefix = "us:statutes/26/1411#input."
    status_codes = {"single": 0, "joint": 1, "separate": 2}
    adjusted_gross_income = sum(
        Decimal(str(inputs[key]))
        for key in (
            "primary_wages",
            "taxable_interest_income",
            "ordinary_dividend_income",
            "long_term_capital_gains",
            "passive_rental_income",
        )
    )
    zero_inputs = (
        "annuity_income",
        "royalty_income",
        "passive_activity_business_income",
        "financial_trading_business_income",
        "investment_of_working_capital_income",
        "allocable_investment_deductions",
        "qualified_plan_distributions",
        "self_employment_income_subject_to_1401_b",
    )
    section_911_zero_inputs = (
        "us:statutes/26/911/a/1#input.elected_foreign_earned_income_exclusion_amount",
        "us:statutes/26/911/d/6#input."
        "deduction_under_subtitle_before_section_911_double_benefit_denial",
        "us:statutes/26/911/d/6#input."
        "deduction_properly_allocable_or_chargeable_to_amounts_excluded_under_"
        "subsection_a",
        "us:statutes/26/911/d/6#input."
        "exclusion_from_gross_income_under_subtitle_before_section_911_double_"
        "benefit_denial",
        "us:statutes/26/911/d/6#input."
        "exclusion_properly_allocable_or_chargeable_to_amounts_excluded_under_"
        "subsection_a",
    )
    _require_fixture_values(
        suite="us-niit-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            f"{prefix}filing_status": status_codes[case.filing_status],
            f"{prefix}adjusted_gross_income": adjusted_gross_income,
            f"{prefix}taxable_interest_income": inputs["taxable_interest_income"],
            f"{prefix}dividend_income": inputs["ordinary_dividend_income"],
            f"{prefix}rental_income": inputs["passive_rental_income"],
            (
                f"{prefix}taxable_net_gain_from_dispositions_after_active_"
                "partnership_s_corporation_exception"
            ): inputs["long_term_capital_gains"],
            **{f"{prefix}{name}": 0 for name in zero_inputs},
            **{name: 0 for name in section_911_zero_inputs},
            f"{prefix}is_nonresident_alien": False,
            (
                f"{prefix}trust_all_unexpired_interests_devoted_to_"
                "section_170_c_2_B_purposes"
            ): False,
            f"{prefix}is_individual": True,
        },
    )


def _validate_qbid_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    statute = "us:statutes/26/199A#input."
    capital_gain = "us:statutes/26/1/h#input."
    pipeline = (
        "us:policies/income_tax/qualified_business_income_deduction_pipeline#input."
    )
    status_codes = {"single": 0, "joint": 1, "separate": 2}
    _require_fixture_values(
        suite="us-qbid-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            f"{pipeline}filing_status": status_codes[case.filing_status],
            (
                f"{pipeline}"
                "supplied_amounts_are_for_taxpayers_only_qualified_trade_or_business"
            ): True,
            f"{statute}qualified_trade_or_business_w2_wages": inputs["w2_wages"],
            f"{statute}qualified_trade_or_business_unadjusted_basis": inputs["ubia"],
            f"{statute}qualified_business_income": inputs["qbi"],
            f"{statute}taxable_income_computed_without_section_199A": inputs[
                "taxable_income_before_qbid"
            ],
            f"{statute}qualified_reit_dividends": inputs["reit_dividends"],
            f"{statute}qualified_publicly_traded_partnership_income": inputs[
                "ptp_income"
            ],
            (
                f"{statute}"
                "aggregate_qualified_business_income_from_active_qualified_"
                "trades_or_businesses"
            ): inputs["active_business_qbi"],
            (
                f"{statute}"
                "qualified_business_income_allocable_to_qualified_"
                "cooperative_payments"
            ): 0,
            (f"{statute}w2_wages_allocable_to_qualified_cooperative_payments"): 0,
            f"{statute}taxpayer_is_corporation": False,
            f"{statute}qualified_production_activities_income": 0,
            (
                f"{statute}"
                "taxpayer_is_specified_agricultural_or_horticultural_"
                "cooperative"
            ): False,
            f"{statute}cooperative_w2_wages": 0,
            (
                f"{capital_gain}"
                "net_capital_gain_taken_into_account_as_investment_income_"
                "under_section_163_d_4_B_iii"
            ): 0,
            f"{capital_gain}long_term_capital_gains": inputs["net_capital_gain"],
            f"{capital_gain}short_term_capital_gains": 0,
            f"{capital_gain}qualified_dividend_income": 0,
        },
    )


def _validate_savers_credit_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    prefix = "us:policies/income_tax/savers_credit_pipeline#input."
    status_codes = {
        "single": 0,
        "joint": 1,
        "separate": 2,
        "head_of_household": 3,
        "surviving_spouse": 4,
    }
    _require_fixture_values(
        suite="us-savers-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            f"{prefix}section_911_excluded_income": inputs[
                "section_911_excluded_income"
            ],
            f"{prefix}section_931_excluded_income": inputs[
                "section_931_excluded_income"
            ],
            f"{prefix}section_933_excluded_income": inputs[
                "section_933_excluded_income"
            ],
            f"{prefix}filing_status": status_codes[case.filing_status],
            f"{prefix}adjusted_gross_income": inputs["adjusted_gross_income"],
            f"{prefix}primary_age_at_close_of_taxable_year": inputs["primary_age"],
            f"{prefix}primary_is_student_under_section_152_f_2": inputs[
                "primary_is_student"
            ],
            (
                f"{prefix}primary_may_be_claimed_as_dependent_by_another_taxpayer"
            ): inputs["primary_is_dependent"],
            f"{prefix}spouse_age_at_close_of_taxable_year": inputs["spouse_age"],
            f"{prefix}spouse_is_student_under_section_152_f_2": inputs[
                "spouse_is_student"
            ],
            (f"{prefix}spouse_may_be_claimed_as_dependent_by_another_taxpayer"): inputs[
                "spouse_is_dependent"
            ],
            (f"{prefix}primary_qualified_retirement_savings_contributions"): inputs[
                "primary_contributions"
            ],
            (f"{prefix}spouse_qualified_retirement_savings_contributions"): inputs[
                "spouse_contributions"
            ],
        },
    )


def _section_22_fixture_person(
    inputs: Mapping[str, Any],
    *,
    spouse: bool,
) -> dict[str, Any]:
    prefix = "us:statutes/26/22#input."
    if spouse:
        return {
            f"{prefix}age": inputs["spouse_age"],
            f"{prefix}retired_on_disability_before_year_end": False,
            f"{prefix}unable_to_engage_substantial_gainful_activity": False,
            f"{prefix}medically_determinable_impairment": False,
            f"{prefix}impairment_expected_to_result_in_death": False,
            f"{prefix}impairment_duration_months": 0,
            f"{prefix}disability_proof_furnished": False,
            f"{prefix}section_22_disability_income": 0,
        }
    return {
        f"{prefix}age": inputs["primary_age"],
        f"{prefix}retired_on_disability_before_year_end": inputs[
            "primary_retired_on_disability"
        ],
        f"{prefix}unable_to_engage_substantial_gainful_activity": inputs[
            "primary_unable_substantial_gainful_activity"
        ],
        f"{prefix}medically_determinable_impairment": inputs[
            "primary_medically_determinable_impairment"
        ],
        f"{prefix}impairment_expected_to_result_in_death": inputs[
            "primary_impairment_expected_to_result_in_death"
        ],
        f"{prefix}impairment_duration_months": inputs[
            "primary_impairment_duration_months"
        ],
        f"{prefix}disability_proof_furnished": inputs[
            "primary_disability_proof_furnished"
        ],
        f"{prefix}section_22_disability_income": inputs["primary_disability_income"],
    }


def _validate_elderly_disabled_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    prefix = "us:statutes/26/22#input."
    relation = "us:statutes/26/22#relation.taxpayer_or_spouse_of_tax_unit"
    payment_relation = "us:statutes/26/22#relation.section_22_payment_of_tax_unit"
    status_codes = {"single": 0, "joint": 1, "separate": 2}
    _require_fixture_values(
        suite="us-elderly-disabled-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            f"{prefix}filing_status": status_codes[case.filing_status],
            f"{prefix}adjusted_gross_income": inputs["adjusted_gross_income"],
            (
                f"{prefix}social_security_title_ii_benefits_excluded_from_gross_income"
            ): inputs["nontaxable_social_security"],
            (f"{prefix}railroad_retirement_act_benefits_excluded_from_gross_income"): 0,
            (
                f"{prefix}"
                "veterans_affairs_pension_annuity_or_disability_benefits_"
                "excluded_from_gross_income"
            ): 0,
            (
                f"{prefix}"
                "other_non_title_pension_annuity_or_disability_benefits_"
                "excluded_from_gross_income"
            ): 0,
            (f"{prefix}workers_compensation_treated_as_social_security_benefit"): 0,
            f"{prefix}married_at_close_of_taxable_year": (
                case.filing_status == "joint"
            ),
            f"{prefix}spouses_lived_apart_all_year": False,
            f"{prefix}is_nonresident_alien": False,
            payment_relation: [],
        },
    )
    people = actual.get(relation)
    expected_people = [_section_22_fixture_person(inputs, spouse=False)]
    if case.filing_status == "joint":
        expected_people.append(_section_22_fixture_person(inputs, spouse=True))
    if not isinstance(people, list) or len(people) != len(expected_people):
        raise ValueError(
            f"us-elderly-disabled-grid: fixture case {case.case_id!r} "
            f"relation {relation!r} must contain {len(expected_people)} "
            "Person input(s)"
        )
    for person, expected_person in zip(
        people,
        expected_people,
        strict=True,
    ):
        if not isinstance(person, dict):
            raise ValueError(
                f"us-elderly-disabled-grid: fixture case {case.case_id!r} "
                "has a non-mapping Person input"
            )
        _require_fixture_values(
            suite="us-elderly-disabled-grid",
            case_id=case.case_id,
            actual=person,
            expected=expected_person,
        )


def _validate_llc_fixture(
    case: FederalCase,
    actual: Mapping[str, Any],
) -> None:
    inputs = case.inputs
    prefix = "us:statutes/26/25A#input."
    relation = "us:statutes/26/25A#relation.education_credit_member_of_tax_unit"
    status_codes = {"single": 0, "joint": 1, "separate": 2}
    _require_fixture_values(
        suite="us-llc-grid",
        case_id=case.case_id,
        actual=actual,
        expected={
            f"{prefix}filing_status": status_codes[case.filing_status],
            f"{prefix}modified_adjusted_gross_income": inputs[
                "modified_adjusted_gross_income"
            ],
            f"{prefix}income_tax_before_credits": inputs["income_tax_before_credits"],
            f"{prefix}foreign_tax_credit": 0,
            f"{prefix}cdcc": 0,
            f"{prefix}taxpayer_is_section_1_g_child": False,
            f"{prefix}is_nonresident_alien": False,
            f"{prefix}section_6013_resident_alien_election": False,
        },
    )
    people = actual.get(relation)
    expenses = inputs["qualified_expenses"]
    if not isinstance(people, list) or len(people) != len(expenses):
        raise ValueError(
            f"us-llc-grid: fixture case {case.case_id!r} relation "
            f"{relation!r} must contain {len(expenses)} Person input(s)"
        )
    common_person = {
        f"{prefix}excludable_educational_assistance": 0,
        f"{prefix}is_tax_unit_dependent": True,
        f"{prefix}is_taxpayer": False,
        f"{prefix}is_spouse": False,
        f"{prefix}meets_higher_education_act_student_requirements": False,
        f"{prefix}at_least_half_time_student": False,
        f"{prefix}aotc_prior_year_election_count": 0,
        (f"{prefix}completed_first_four_years_postsecondary_before_year"): False,
        f"{prefix}has_felony_drug_conviction": False,
        f"{prefix}aotc_election_in_effect": False,
        f"{prefix}education_credit_election_in_effect": True,
        (f"{prefix}education_credit_identification_requirements_met"): True,
        (f"{prefix}institution_employer_identification_number_included"): False,
        f"{prefix}payee_statement_received": True,
        f"{prefix}aotc_disallowance_period_applies": False,
    }
    for person, amount in zip(people, expenses, strict=True):
        if not isinstance(person, dict):
            raise ValueError(
                f"us-llc-grid: fixture case {case.case_id!r} has a "
                "non-mapping Person input"
            )
        _require_fixture_values(
            suite="us-llc-grid",
            case_id=case.case_id,
            actual=person,
            expected={
                **common_person,
                f"{prefix}qualified_tuition_and_related_expenses": amount,
            },
        )


def _verify_parameter_values(
    label: str,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    for key, expected_value in expected.items():
        if key not in actual or not _same_scalar(actual[key], expected_value):
            raise ValueError(
                f"{label}: PolicyEngine 2026 parameter {key!r} is "
                f"{actual.get(key)!r}; expected {expected_value!r}"
            )


def _verify_salt_pe_parameters(tax_benefit_system: Any) -> None:
    parameters = tax_benefit_system.parameters("2026-01-01")
    p = parameters.gov.irs.deductions.itemized.salt_and_real_estate
    simulation = parameters.gov.simulation
    _verify_parameter_values(
        "us-salt-deduction-grid",
        {
            "sources": list(p.sources),
            "cap.SINGLE": float(p.cap.SINGLE),
            "cap.JOINT": float(p.cap.JOINT),
            "cap.SEPARATE": float(p.cap.SEPARATE),
            "cap.HEAD_OF_HOUSEHOLD": float(p.cap.HEAD_OF_HOUSEHOLD),
            "cap.SURVIVING_SPOUSE": float(p.cap.SURVIVING_SPOUSE),
            "phase_out.threshold.SINGLE": float(p.phase_out.threshold.SINGLE),
            "phase_out.threshold.JOINT": float(p.phase_out.threshold.JOINT),
            "phase_out.threshold.SEPARATE": float(p.phase_out.threshold.SEPARATE),
            "phase_out.threshold.HEAD_OF_HOUSEHOLD": float(
                p.phase_out.threshold.HEAD_OF_HOUSEHOLD
            ),
            "phase_out.threshold.SURVIVING_SPOUSE": float(
                p.phase_out.threshold.SURVIVING_SPOUSE
            ),
            "phase_out.rate": float(p.phase_out.rate),
            "phase_out.floor.amount.SINGLE": float(p.phase_out.floor.amount.SINGLE),
            "phase_out.floor.amount.JOINT": float(p.phase_out.floor.amount.JOINT),
            "phase_out.floor.amount.SEPARATE": float(p.phase_out.floor.amount.SEPARATE),
            "phase_out.floor.amount.HEAD_OF_HOUSEHOLD": float(
                p.phase_out.floor.amount.HEAD_OF_HOUSEHOLD
            ),
            "phase_out.floor.amount.SURVIVING_SPOUSE": float(
                p.phase_out.floor.amount.SURVIVING_SPOUSE
            ),
            "phase_out.in_effect": bool(p.phase_out.in_effect),
            "phase_out.floor.applies": bool(p.phase_out.floor.applies),
            "simulation.limit_itemized_deductions_to_taxable_income": bool(
                simulation.limit_itemized_deductions_to_taxable_income
            ),
            "simulation.branch_to_determine_itemization": bool(
                simulation.branch_to_determine_itemization
            ),
        },
        {
            "sources": [
                "state_and_local_sales_or_income_tax",
                "real_estate_taxes",
            ],
            "cap.SINGLE": 40_400,
            "cap.JOINT": 40_400,
            "cap.SEPARATE": 20_200,
            "cap.HEAD_OF_HOUSEHOLD": 40_400,
            "cap.SURVIVING_SPOUSE": 40_400,
            "phase_out.threshold.SINGLE": 505_000,
            "phase_out.threshold.JOINT": 505_000,
            "phase_out.threshold.SEPARATE": 252_500,
            "phase_out.threshold.HEAD_OF_HOUSEHOLD": 505_000,
            "phase_out.threshold.SURVIVING_SPOUSE": 505_000,
            "phase_out.rate": 0.3,
            "phase_out.floor.amount.SINGLE": 10_000,
            "phase_out.floor.amount.JOINT": 10_000,
            "phase_out.floor.amount.SEPARATE": 5_000,
            "phase_out.floor.amount.HEAD_OF_HOUSEHOLD": 10_000,
            "phase_out.floor.amount.SURVIVING_SPOUSE": 10_000,
            "phase_out.in_effect": True,
            "phase_out.floor.applies": True,
            "simulation.limit_itemized_deductions_to_taxable_income": True,
            "simulation.branch_to_determine_itemization": True,
        },
    )


def _verify_itemized_pe_parameters(tax_benefit_system: Any) -> None:
    parameters = tax_benefit_system.parameters("2026-01-01")
    deductions = parameters.gov.irs.deductions
    p = deductions.itemized.limitation
    top_thresholds = parameters.gov.irs.income.bracket.thresholds["6"]
    _verify_parameter_values(
        "us-itemized-taxable-income-deductions-grid",
        {
            "itemized_deductions": list(deductions.itemized_deductions),
            "limitation.applies": bool(p.applies),
            "limitation.obbb.applies": bool(p.obbb.applies),
            "top_threshold.SINGLE": float(top_thresholds.SINGLE),
            "top_threshold.JOINT": float(top_thresholds.JOINT),
            "top_threshold.SEPARATE": float(top_thresholds.SEPARATE),
            "top_threshold.HEAD_OF_HOUSEHOLD": float(top_thresholds.HEAD_OF_HOUSEHOLD),
            "top_threshold.SURVIVING_SPOUSE": float(top_thresholds.SURVIVING_SPOUSE),
            "limitation.obbb.rate": float(p.obbb.rate),
        },
        {
            "itemized_deductions": [
                "charitable_deduction",
                "interest_deduction",
                "salt_deduction",
                "medical_expense_deduction",
                "casualty_loss_deduction",
                "misc_deduction",
            ],
            "limitation.applies": True,
            "limitation.obbb.applies": True,
            "top_threshold.SINGLE": 640_600,
            "top_threshold.JOINT": 768_700,
            "top_threshold.SEPARATE": 384_350,
            "top_threshold.HEAD_OF_HOUSEHOLD": 640_600,
            "top_threshold.SURVIVING_SPOUSE": 768_700,
            "limitation.obbb.rate": 0.05405405,
        },
    )


def _verify_qbid_pe_parameters(tax_benefit_system: Any) -> None:
    p = tax_benefit_system.parameters("2026-01-01").gov.irs.deductions.qbi
    _verify_parameter_values(
        "us-qbid-grid",
        {
            "phase_out.start.SINGLE": p.phase_out.start.SINGLE,
            "phase_out.start.JOINT": p.phase_out.start.JOINT,
            "phase_out.start.SEPARATE": p.phase_out.start.SEPARATE,
            "phase_out.length.SINGLE": p.phase_out.length.SINGLE,
            "phase_out.length.JOINT": p.phase_out.length.JOINT,
            "deduction_floor.in_effect": p.deduction_floor.in_effect,
            "deduction_floor.amount@999": float(p.deduction_floor.amount.calc(999)),
            "deduction_floor.amount@1000": float(p.deduction_floor.amount.calc(1_000)),
        },
        {
            "phase_out.start.SINGLE": 201_750,
            "phase_out.start.JOINT": 403_500,
            "phase_out.start.SEPARATE": 201_775,
            "phase_out.length.SINGLE": 75_000,
            "phase_out.length.JOINT": 150_000,
            "deduction_floor.in_effect": True,
            "deduction_floor.amount@999": 0,
            "deduction_floor.amount@1000": 400,
        },
    )


def _verify_savers_pe_parameters(tax_benefit_system: Any) -> None:
    p = tax_benefit_system.parameters("2026-01-01").gov.irs.credits.retirement_saving
    # ParameterScale thresholds switch at their boundary.  Checking just below
    # and at each published value proves the exact stored breakpoints while
    # leaving the inclusive-maximum truth case to surface as a real mismatch.
    _verify_parameter_values(
        "us-savers-grid",
        {
            "rate.joint@48499.99": float(p.rate.joint.calc(48_499.99)),
            "rate.joint@48500": float(p.rate.joint.calc(48_500)),
            "rate.joint@52500": float(p.rate.joint.calc(52_500)),
            "rate.joint@80500": float(p.rate.joint.calc(80_500)),
            "rate.threshold_adjustment.JOINT": (p.rate.threshold_adjustment.JOINT),
            "rate.threshold_adjustment.SINGLE": (p.rate.threshold_adjustment.SINGLE),
            "rate.threshold_adjustment.SEPARATE": (
                p.rate.threshold_adjustment.SEPARATE
            ),
            "rate.threshold_adjustment.HEAD_OF_HOUSEHOLD": (
                p.rate.threshold_adjustment.HEAD_OF_HOUSEHOLD
            ),
            "rate.threshold_adjustment.SURVIVING_SPOUSE": (
                p.rate.threshold_adjustment.SURVIVING_SPOUSE
            ),
            "contributions_cap": p.contributions_cap,
        },
        {
            "rate.joint@48499.99": 0.5,
            "rate.joint@48500": 0.2,
            "rate.joint@52500": 0.1,
            "rate.joint@80500": 0,
            "rate.threshold_adjustment.JOINT": 1,
            "rate.threshold_adjustment.SINGLE": 0.5,
            "rate.threshold_adjustment.SEPARATE": 0.5,
            "rate.threshold_adjustment.HEAD_OF_HOUSEHOLD": 0.75,
            "rate.threshold_adjustment.SURVIVING_SPOUSE": 0.5,
            "contributions_cap": 2_000,
        },
    )


def _verify_elderly_disabled_pe_parameters(
    tax_benefit_system: Any,
) -> None:
    p = tax_benefit_system.parameters("2026-01-01").gov.irs.credits.elderly_or_disabled
    _verify_parameter_values(
        "us-elderly-disabled-grid",
        {
            "age": p.age,
            "amount.one_qualified": p.amount.one_qualified,
            "amount.two_qualified": p.amount.two_qualified,
            "amount.separate": p.amount.separate,
            "phase_out.threshold.SINGLE": p.phase_out.threshold.SINGLE,
            "phase_out.threshold.JOINT": p.phase_out.threshold.JOINT,
            "phase_out.rate": p.phase_out.rate,
            "rate": p.rate,
        },
        {
            "age": 65,
            "amount.one_qualified": 5_000,
            "amount.two_qualified": 7_500,
            "amount.separate": 3_750,
            "phase_out.threshold.SINGLE": 7_500,
            "phase_out.threshold.JOINT": 10_000,
            "phase_out.rate": 0.5,
            "rate": 0.15,
        },
    )


def _verify_llc_pe_parameters(tax_benefit_system: Any) -> None:
    p = tax_benefit_system.parameters(
        "2026-01-01"
    ).gov.irs.credits.education.lifetime_learning_credit
    _verify_parameter_values(
        "us-llc-grid",
        {
            "phase_out.start.single": p.phase_out.start.single,
            "phase_out.start.joint": p.phase_out.start.joint,
            "phase_out.length.single": p.phase_out.length.single,
            "phase_out.length.joint": p.phase_out.length.joint,
            "expense_limit": p.expense_limit,
            "rate": p.rate,
            "abolition": p.abolition,
        },
        {
            "phase_out.start.single": 80_000,
            "phase_out.start.joint": 160_000,
            "phase_out.length.single": 10_000,
            "phase_out.length.joint": 20_000,
            "expense_limit": 10_000,
            "rate": 0.2,
            "abolition": False,
        },
    )


# The RuleSpec paths and output names below are completed by the companion
# RuleSpec lanes.  Keeping them in this one registry makes each run select and
# read only one fixture; a missing companion cannot prevent another policy from
# running.
POLICIES: dict[str, PolicyConfig] = {
    "salt_deduction": PolicyConfig(
        key="salt_deduction",
        suite="us-salt-deduction-grid",
        title="State and local tax deduction",
        axiom_module_ref=_SALT_MODULE,
        fixture_path=Path("us/policies/income_tax/salt_deduction_pipeline.test.yaml"),
        axiom_output=f"{_SALT_MODULE}#federal_salt_deduction",
        pe_output_variables=("salt_deduction",),
        pe_boundary=(
            "TaxUnit section 164 personal SALT component after the 2026 "
            "cap, phaseout, and PolicyEngine's simulation-only AGI ceiling"
        ),
        cases=_SALT_DEDUCTION_CASES,
        pe_situation=_salt_situation,
        fixture_input_validator=_validate_salt_fixture,
        pe_diagnostic_variables=(
            "salt",
            "salt_cap",
            "adjusted_gross_income",
            "exemptions",
            "foreign_earned_income_exclusion",
            "salt_deduction",
        ),
        pe_parameter_validator=_verify_salt_pe_parameters,
        axiom_bridge_outputs={
            _SALT_SECTION_911_BRIDGE: "foreign_earned_income_exclusion",
        },
        rulespec_domain_inputs=_SALT_DOMAIN_INPUTS,
        rulespec_only_inputs=(_SALT_PERSONAL_PROPERTY_INPUT,),
        pe_input_variables=(
            *_PE_STRUCTURAL_INPUTS,
            "adjusted_gross_income",
            "state_and_local_sales_or_income_tax",
            "real_estate_taxes",
            "foreign_earned_income_exclusion",
        ),
    ),
    "itemized_taxable_income_deductions": PolicyConfig(
        key="itemized_taxable_income_deductions",
        suite="us-itemized-taxable-income-deductions-grid",
        title="Itemized taxable-income deductions",
        axiom_module_ref=_ITEMIZED_MODULE,
        fixture_path=Path(
            "us/policies/income_tax/"
            "itemized_taxable_income_deductions_pipeline.test.yaml"
        ),
        axiom_output=(f"{_ITEMIZED_MODULE}#federal_itemized_taxable_income_deductions"),
        pe_output_variables=("itemized_taxable_income_deductions",),
        pe_boundary=(
            "TaxUnit six-component completed itemized aggregate after the "
            "2026 section 68 limitation"
        ),
        cases=_ITEMIZED_DEDUCTION_CASES,
        pe_situation=_itemized_situation,
        fixture_input_validator=_validate_itemized_fixture,
        pe_diagnostic_variables=(
            "total_itemized_taxable_income_deductions",
            "itemized_taxable_income_deductions_reduction",
            "itemized_taxable_income_deductions",
            "adjusted_gross_income",
            "exemptions",
            "charitable_deduction",
            "interest_deduction",
            "salt_deduction",
            "medical_expense_deduction",
            "casualty_loss_deduction",
            "misc_deduction",
        ),
        pe_parameter_validator=_verify_itemized_pe_parameters,
        axiom_diagnostic_outputs={
            _ITEMIZED_BEFORE_SECTION_68: ("total_itemized_taxable_income_deductions"),
            _ITEMIZED_SECTION_68_REDUCTION: (
                "itemized_taxable_income_deductions_reduction"
            ),
        },
        rulespec_domain_inputs=_ITEMIZED_DOMAIN_INPUTS,
        rulespec_only_inputs=(_ITEMIZED_SECTION_68_BASE_INPUT,),
        pe_input_variables=(
            *_PE_STRUCTURAL_INPUTS,
            "adjusted_gross_income",
            "exemptions",
            "charitable_deduction",
            "interest_deduction",
            "salt_deduction",
            "medical_expense_deduction",
            "casualty_loss_deduction",
            "misc_deduction",
        ),
    ),
    "qualified_business_income_deduction": PolicyConfig(
        key="qualified_business_income_deduction",
        suite="us-qbid-grid",
        title="Qualified business income deduction",
        axiom_module_ref=(
            "us:policies/income_tax/qualified_business_income_deduction_pipeline"
        ),
        fixture_path=Path(
            "us/policies/income_tax/"
            "qualified_business_income_deduction_pipeline.test.yaml"
        ),
        axiom_output=(
            "us:policies/income_tax/"
            "qualified_business_income_deduction_pipeline"
            "#federal_qualified_business_income_deduction"
        ),
        pe_output_variables=("qualified_business_income_deduction",),
        pe_boundary=(
            "TaxUnit section 199A deduction over caller-resolved QBI, wages, "
            "UBIA, REIT/PTP income, taxable income, and net capital gain"
        ),
        cases=_QBID_CASES,
        pe_situation=_no_bridge_situation(_qbid_situation),
        fixture_input_validator=_validate_qbid_fixture,
        pe_parameter_validator=_verify_qbid_pe_parameters,
    ),
    "savers_credit": PolicyConfig(
        key="savers_credit",
        suite="us-savers-grid",
        title="Saver's credit before section 26",
        axiom_module_ref=("us:policies/income_tax/savers_credit_pipeline"),
        fixture_path=Path("us/policies/income_tax/savers_credit_pipeline.test.yaml"),
        axiom_output=(
            "us:policies/income_tax/savers_credit_pipeline#federal_savers_credit"
        ),
        # The public PE variable applies the nonrefundable credit limit.
        # `savers_credit_potential` is PE's TaxUnit pre-section-26 amount and
        # the bridge registry's reviewed direct target for this final.
        pe_output_variables=("savers_credit_potential",),
        pe_boundary=(
            "TaxUnit section 25B amount before section 26, mapped directly to "
            "PE's pre-section-26 potential-credit surface"
        ),
        cases=_SAVERS_CREDIT_CASES,
        pe_situation=_no_bridge_situation(_savers_credit_situation),
        fixture_input_validator=_validate_savers_credit_fixture,
        pe_diagnostic_variables=(
            "savers_credit",
            "savers_credit_credit_limit",
        ),
        pe_parameter_validator=_verify_savers_pe_parameters,
        supplemental_fixture_paths=(
            Path("comparisons/fixtures/us-savers-grid-boundary-probes.yaml"),
        ),
    ),
    "elderly_disabled_credit": PolicyConfig(
        key="elderly_disabled_credit",
        suite="us-elderly-disabled-grid",
        title="Credit for the elderly or disabled before section 26",
        axiom_module_ref=("us:policies/income_tax/elderly_disabled_credit_pipeline"),
        fixture_path=Path(
            "us/policies/income_tax/elderly_disabled_credit_pipeline.test.yaml"
        ),
        axiom_output=(
            "us:policies/income_tax/elderly_disabled_credit_pipeline"
            "#federal_elderly_disabled_credit"
        ),
        # The public PE variable applies the nonrefundable credit limit.
        pe_output_variables=("elderly_disabled_credit_potential",),
        pe_boundary=(
            "TaxUnit statutory section 22 amount before section 26, including "
            "aged and collapsed permanent-total-disability branches"
        ),
        cases=_ELDERLY_DISABLED_CASES,
        pe_situation=_no_bridge_situation(_elderly_disabled_situation),
        fixture_input_validator=_validate_elderly_disabled_fixture,
        pe_diagnostic_variables=(
            "elderly_disabled_credit",
            "elderly_disabled_credit_credit_limit",
        ),
        pe_parameter_validator=_verify_elderly_disabled_pe_parameters,
    ),
    "lifetime_learning_credit": PolicyConfig(
        key="lifetime_learning_credit",
        suite="us-llc-grid",
        title="Lifetime Learning Credit",
        axiom_module_ref=("us:policies/income_tax/lifetime_learning_credit_pipeline"),
        fixture_path=Path(
            "us/policies/income_tax/lifetime_learning_credit_pipeline.test.yaml"
        ),
        axiom_output=(
            "us:policies/income_tax/lifetime_learning_credit_pipeline"
            "#federal_lifetime_learning_credit"
        ),
        pe_output_variables=("lifetime_learning_credit",),
        pe_boundary=(
            "TaxUnit section 25A(c) amount after the section 26 liability "
            "limit; the diagnostic case binds that limit"
        ),
        cases=_LLC_CASES,
        pe_situation=_no_bridge_situation(_llc_situation),
        fixture_input_validator=_validate_llc_fixture,
        pe_diagnostic_variables=(
            "lifetime_learning_credit_potential",
            "lifetime_learning_credit_credit_limit",
        ),
        pe_parameter_validator=_verify_llc_pe_parameters,
    ),
    "additional_medicare_tax": PolicyConfig(
        key="additional_medicare_tax",
        suite="us-additional-medicare-grid",
        title="Additional Medicare Tax",
        axiom_module_ref=("us:policies/income_tax/additional_medicare_tax_pipeline"),
        fixture_path=Path(
            "us/policies/income_tax/additional_medicare_tax_pipeline.test.yaml"
        ),
        axiom_output=(
            "us:policies/income_tax/additional_medicare_tax_pipeline"
            "#federal_additional_medicare_tax"
        ),
        pe_output_variables=("additional_medicare_tax",),
        pe_boundary=(
            "TaxUnit Additional Medicare Tax restricted to zero "
            "self-employment income, where the public total equals the "
            "section 3101(b)(2) wage-only amount"
        ),
        cases=_ADDITIONAL_MEDICARE_CASES,
        pe_situation=_no_bridge_situation(_payroll_situation),
        fixture_input_validator=_validate_additional_medicare_fixture,
    ),
    "self_employment_tax": PolicyConfig(
        key="self_employment_tax",
        suite="us-seca-grid",
        title="Self-employment tax",
        axiom_module_ref="us:policies/income_tax/self_employment_tax_pipeline",
        fixture_path=Path(
            "us/policies/income_tax/self_employment_tax_pipeline.test.yaml"
        ),
        axiom_output=(
            "us:policies/income_tax/self_employment_tax_pipeline"
            "#federal_self_employment_tax"
        ),
        pe_output_variables=("self_employment_tax",),
        pe_boundary=(
            "Person SECA Social Security plus regular Medicare, summed to TaxUnit; "
            "excludes Additional Medicare Tax"
        ),
        cases=_SELF_EMPLOYMENT_CASES,
        pe_situation=_no_bridge_situation(_payroll_situation),
        fixture_input_validator=_validate_self_employment_fixture,
    ),
    "net_investment_income_tax": PolicyConfig(
        key="net_investment_income_tax",
        suite="us-niit-grid",
        title="Net Investment Income Tax",
        axiom_module_ref=("us:policies/income_tax/net_investment_income_tax_pipeline"),
        fixture_path=Path(
            "us/policies/income_tax/net_investment_income_tax_pipeline.test.yaml"
        ),
        axiom_output=(
            "us:policies/income_tax/net_investment_income_tax_pipeline"
            "#federal_net_investment_income_tax"
        ),
        pe_output_variables=("net_investment_income_tax",),
        pe_boundary=(
            "TaxUnit section 1411 tax; AGI equals MAGI because the grid has no "
            "section 911 exclusions"
        ),
        cases=_NIIT_CASES,
        pe_situation=_no_bridge_situation(_niit_situation),
        fixture_input_validator=_validate_niit_fixture,
    ),
    "aca_ptc": PolicyConfig(
        key="aca_ptc",
        suite="us-aca-ptc-grid",
        title="ACA Premium Tax Credit",
        axiom_module_ref="us:policies/aca/ptc_pipeline",
        fixture_path=Path("us/policies/aca/ptc_pipeline.test.yaml"),
        axiom_output=("us:policies/aca/ptc_pipeline#aca_ptc_annual_premium_tax_credit"),
        # `aca_ptc` omits the enrolled-premium cap.  `used_aca_ptc` applies it
        # and therefore matches the section 36B / GRID-CONTRACT output boundary.
        pe_output_variables=("used_aca_ptc",),
        pe_boundary=(
            "TaxUnit annual benchmark credit capped by enrolled marketplace "
            "premium for twelve months"
        ),
        cases=_ACA_PTC_CASES,
        pe_situation=_no_bridge_situation(_aca_ptc_situation),
        fixture_input_validator=_validate_aca_ptc_fixture,
    ),
}


def _fixture_file(config: PolicyConfig, roots: list[Path]) -> Path:
    candidates = [root / config.fixture_path for root in roots]
    matches = [path for path in candidates if path.is_file()]
    if not matches:
        tried = "\n".join(f"  - {path}" for path in candidates)
        raise FileNotFoundError(
            f"{config.suite}: RuleSpec companion fixture not found; tried:\n{tried}"
        )
    if len(matches) > 1:
        choices = "\n".join(f"  - {path}" for path in matches)
        raise RuntimeError(
            f"{config.suite}: fixture is ambiguous across rulespec roots:\n{choices}"
        )
    return matches[0]


def _fixture_records(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text())
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        records = raw.get("tests") or raw.get("cases")
    else:
        records = None
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected a test-case list")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"{path}: every test case must be a mapping")
    names = [str(record.get("name")) for record in records]
    if len(names) != len(set(names)):
        raise ValueError(f"{path}: duplicate test-case names")
    return records


def _scored_bindings(config: PolicyConfig) -> tuple[ComparisonBinding, ...]:
    if config.comparison_bindings:
        return config.comparison_bindings
    if len(config.pe_output_variables) != 1:
        raise ValueError(
            f"{config.suite}: a single legacy PE output or explicit comparison "
            "bindings are required"
        )
    return (
        ComparisonBinding(
            concept=config.axiom_output,
            policyengine_target=config.pe_output_variables[0],
            comparison="amount",
        ),
    )


def _comparison_rows(
    config: PolicyConfig,
) -> list[tuple[str, FederalCase, ComparisonBinding]]:
    known_cases = {case.case_id: case for case in config.cases}
    rows: list[tuple[str, FederalCase, ComparisonBinding]] = []
    for binding in _scored_bindings(config):
        selected_ids = binding.case_ids or tuple(known_cases)
        unknown = sorted(set(selected_ids) - set(known_cases))
        if unknown:
            raise ValueError(
                f"{config.suite}: comparison binding {binding.concept!r} "
                f"selects unknown cases {unknown}"
            )
        for case_id in selected_ids:
            case = known_cases[case_id]
            rows.append((f"{case_id}{binding.case_id_suffix}", case, binding))
    row_ids = [row_id for row_id, _, _ in rows]
    if len(row_ids) != len(set(row_ids)):
        raise ValueError(f"{config.suite}: comparison row IDs are not unique")
    return rows


def _mapping_for_binding(config: PolicyConfig, binding: ComparisonBinding) -> Any:
    mapping = load_policyengine_registry().mapping_for_legal_id(
        binding.concept,
        country="us",
    )
    if mapping is None:
        raise ValueError(
            f"{config.suite}: scored concept {binding.concept!r} is unmapped"
        )
    if not mapping.comparable:
        raise ValueError(
            f"{config.suite}: scored concept {binding.concept!r} is "
            "registry-not-comparable"
        )
    mapped_target = mapping.policyengine_variable or mapping.policyengine_parameter
    if binding.policyengine_target != mapped_target:
        raise ValueError(
            f"{config.suite}: scored concept {binding.concept!r} binds "
            f"{binding.policyengine_target!r}, but the registry target is "
            f"{mapped_target!r}"
        )
    return mapping


def _assert_registry_comparable_bindings(config: PolicyConfig) -> None:
    """Fail closed for grids whose scored bindings have been registry-audited.

    Other older federal grids still need a separate mapping migration. Keeping
    the invariant scoped prevents this work from silently blessing their
    pre-existing unmapped pipeline concepts.
    """

    audited_suites = {
        "us-savers-grid",
        "us-salt-deduction-grid",
        "us-itemized-taxable-income-deductions-grid",
    }
    if config.suite not in audited_suites:
        return
    for binding in _scored_bindings(config):
        _mapping_for_binding(config, binding)


def _validate_policy_config(config: PolicyConfig) -> None:
    scored_outputs = {binding.concept for binding in _scored_bindings(config)}
    bridge_outputs = set(config.axiom_bridge_outputs)
    diagnostic_outputs = set(config.axiom_diagnostic_outputs)
    overlap = scored_outputs & bridge_outputs
    if overlap:
        raise ValueError(
            f"{config.suite}: compared Axiom outputs cannot also be bridge "
            f"outputs: {sorted(overlap)}"
        )
    overlap = (scored_outputs | bridge_outputs) & diagnostic_outputs
    if overlap:
        raise ValueError(
            f"{config.suite}: diagnostic Axiom outputs must be distinct from "
            f"compared and bridge outputs: {sorted(overlap)}"
        )
    for output in bridge_outputs | diagnostic_outputs:
        if not output.startswith(f"{config.axiom_module_ref}#"):
            raise ValueError(
                f"{config.suite}: auxiliary Axiom output {output!r} is not "
                f"defined by configured module {config.axiom_module_ref!r}"
            )
    bridge_targets = tuple(config.axiom_bridge_outputs.values())
    if len(bridge_targets) != len(set(bridge_targets)):
        raise ValueError(
            f"{config.suite}: multiple Axiom bridge outputs target the same "
            "PolicyEngine input"
        )
    if len(config.rulespec_only_inputs) != len(set(config.rulespec_only_inputs)):
        raise ValueError(f"{config.suite}: RuleSpec-only inputs contain duplicates")
    if len(config.pe_input_variables) != len(set(config.pe_input_variables)):
        raise ValueError(
            f"{config.suite}: declared PolicyEngine inputs contain duplicates"
        )
    undeclared_bridge_targets = sorted(
        set(bridge_targets) - set(config.pe_input_variables)
    )
    if undeclared_bridge_targets:
        raise ValueError(
            f"{config.suite}: PolicyEngine bridge targets are not declared "
            f"inputs: {undeclared_bridge_targets}"
        )
    undeclared_diagnostic_targets = sorted(
        set(config.axiom_diagnostic_outputs.values())
        - set(config.pe_diagnostic_variables)
    )
    if undeclared_diagnostic_targets:
        raise ValueError(
            f"{config.suite}: Axiom diagnostic targets are not declared "
            f"PolicyEngine diagnostics: {undeclared_diagnostic_targets}"
        )
    overlap = set(config.rulespec_domain_inputs) & set(config.rulespec_only_inputs)
    if overlap:
        raise ValueError(
            f"{config.suite}: domain and RuleSpec-only inputs overlap: "
            f"{sorted(overlap)}"
        )


def _binding_payload(
    config: PolicyConfig,
    binding: ComparisonBinding,
) -> dict[str, Any]:
    mapping = _mapping_for_binding(config, binding)
    payload: dict[str, Any] = {
        "concept": binding.concept,
        "mapping_type": mapping.mapping_type,
        "comparison": binding.comparison,
    }
    if mapping.policyengine_variable:
        payload["variable"] = mapping.policyengine_variable
    if mapping.policyengine_parameter:
        payload["parameter"] = mapping.policyengine_parameter
    if mapping.parameter_key:
        payload["parameter_key"] = mapping.parameter_key
    if mapping.parameter_key_input:
        payload["parameter_key_input"] = mapping.parameter_key_input
    if mapping.parameter_key_map:
        payload["parameter_key_map"] = dict(mapping.parameter_key_map)
    if binding.case_ids:
        payload["case_ids"] = list(binding.case_ids)
    return payload


def _merge_fixture_record(
    *,
    suite: str,
    base: dict[str, Any],
    extension: Mapping[str, Any],
    extension_path: Path,
) -> dict[str, Any]:
    merged = dict(base)
    for field in ("period",):
        if field in extension and field in merged and extension[field] != merged[field]:
            raise ValueError(
                f"{suite}: {extension_path} conflicts on {field!r} for "
                f"case {base.get('name')!r}"
            )
        if field in extension:
            merged[field] = extension[field]
    for field in ("input", "output"):
        existing = merged.get(field) or {}
        additional = extension.get(field) or {}
        if not isinstance(existing, dict) or not isinstance(additional, dict):
            raise ValueError(
                f"{suite}: fixture case {base.get('name')!r} field {field!r} "
                "must be a mapping"
            )
        combined = dict(existing)
        for key, value in additional.items():
            if key in combined and combined[key] != value:
                raise ValueError(
                    f"{suite}: {extension_path} conflicts on {field}.{key} "
                    f"for case {base.get('name')!r}"
                )
            combined[key] = value
        merged[field] = combined
    return merged


def _merged_fixture_records(
    config: PolicyConfig,
    fixture: Path,
) -> dict[str, dict[str, Any]]:
    by_name = {str(record.get("name")): record for record in _fixture_records(fixture)}
    configured_ids = {case.case_id for case in config.cases}
    for relative_path in config.supplemental_fixture_paths:
        extension_path = REPO_ROOT / relative_path
        if not extension_path.is_file():
            raise FileNotFoundError(
                f"{config.suite}: supplemental fixture not found: {extension_path}"
            )
        for extension in _fixture_records(extension_path):
            name = str(extension.get("name"))
            if name not in configured_ids:
                raise ValueError(
                    f"{config.suite}: {extension_path} contains unconfigured "
                    f"case {name!r}"
                )
            if name in by_name:
                by_name[name] = _merge_fixture_record(
                    suite=config.suite,
                    base=by_name[name],
                    extension=extension,
                    extension_path=extension_path,
                )
            else:
                by_name[name] = extension
    return by_name


def _axiom_values(
    config: PolicyConfig,
    roots: list[Path],
) -> tuple[
    Path,
    dict[str, float],
    dict[str, dict[str, Any]],
    dict[str, dict[str, float]],
    dict[str, dict[str, float]],
]:
    bindings = _scored_bindings(config)
    for binding in bindings:
        if not binding.concept.startswith(f"{config.axiom_module_ref}#"):
            raise ValueError(
                f"{config.suite}: Axiom output {binding.concept!r} is not "
                f"defined by configured module {config.axiom_module_ref!r}"
            )
    fixture = _fixture_file(config, roots)
    by_name = _merged_fixture_records(config, fixture)
    values: dict[str, float] = {}
    fixture_inputs: dict[str, dict[str, Any]] = {}
    bridge_values: dict[str, dict[str, float]] = {}
    diagnostic_values: dict[str, dict[str, float]] = {}
    for case in config.cases:
        if case.case_id not in by_name:
            raise ValueError(f"{fixture}: missing contract case {case.case_id!r}")
        record = by_name[case.case_id]
        expected_period = {
            "period_kind": "tax_year",
            "start": f"{VALIDATION_YEAR}-01-01",
            "end": f"{VALIDATION_YEAR}-12-31",
        }
        if record.get("period") != expected_period:
            raise ValueError(
                f"{fixture}: case {case.case_id!r} must use the exact "
                f"{VALIDATION_YEAR} tax-year period"
            )
        outputs = record.get("output")
        if not isinstance(outputs, dict):
            raise ValueError(
                f"{fixture}: case {case.case_id!r} output is not a mapping"
            )
        raw_inputs = record.get("input") or {}
        if not isinstance(raw_inputs, dict):
            raise ValueError(f"{fixture}: case {case.case_id!r} input is not a mapping")
        config.fixture_input_validator(case, raw_inputs)
        _validate_rulespec_input_contract(config, case, raw_inputs)
        fixture_inputs[case.case_id] = raw_inputs
        bridge_values[case.case_id] = {
            output: _numeric_fixture_output(
                fixture=fixture,
                case_id=case.case_id,
                output=output,
                value=outputs.get(output),
                present=output in outputs,
            )
            for output in config.axiom_bridge_outputs
        }
        diagnostic_values[case.case_id] = {
            output: _numeric_fixture_output(
                fixture=fixture,
                case_id=case.case_id,
                output=output,
                value=outputs.get(output),
                present=output in outputs,
            )
            for output in config.axiom_diagnostic_outputs
        }
    for row_id, case, binding in _comparison_rows(config):
        outputs = by_name[case.case_id].get("output") or {}
        if binding.concept not in outputs:
            raise ValueError(
                f"{fixture}: case {case.case_id!r} has no output {binding.concept!r}"
            )
        values[row_id] = _numeric_fixture_output(
            fixture=fixture,
            case_id=case.case_id,
            output=binding.concept,
            value=outputs[binding.concept],
            present=True,
        )
    return (
        fixture,
        values,
        fixture_inputs,
        bridge_values,
        diagnostic_values,
    )


def _numeric_fixture_output(
    *,
    fixture: Path,
    case_id: str,
    output: str,
    value: Any,
    present: bool,
) -> float:
    if not present:
        raise ValueError(f"{fixture}: case {case_id!r} has no output {output!r}")
    if isinstance(value, bool):
        raise ValueError(
            f"{fixture}: case {case_id!r} output {output!r} must be numeric"
        )
    try:
        numeric = float(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{fixture}: case {case_id!r} output {output!r} must be numeric; "
            f"got {value!r}"
        ) from error
    if not isfinite(numeric):
        raise ValueError(
            f"{fixture}: case {case_id!r} output {output!r} must be finite; "
            f"got {value!r}"
        )
    return numeric


def _situation_input_variables(situation: Mapping[str, Any]) -> set[str]:
    observed: set[str] = set()
    for entities in situation.values():
        if not isinstance(entities, Mapping):
            continue
        for entity in entities.values():
            if not isinstance(entity, Mapping):
                continue
            observed.update(variable for variable in entity if variable != "members")
    return observed


def _validate_pe_situation_inputs(
    config: PolicyConfig,
    case: FederalCase,
    situation: Mapping[str, Any],
) -> None:
    if not config.pe_input_variables:
        return
    observed = _situation_input_variables(situation)
    unexpected = sorted(observed - set(config.pe_input_variables))
    if unexpected:
        raise ValueError(
            f"{config.suite}: case {case.case_id!r} has undeclared "
            f"PolicyEngine overrides {unexpected}"
        )
    missing_bridges = sorted(set(config.axiom_bridge_outputs.values()) - observed)
    if missing_bridges:
        raise ValueError(
            f"{config.suite}: case {case.case_id!r} omits PolicyEngine "
            f"bridge inputs {missing_bridges}"
        )


def _policyengine_values(
    config: PolicyConfig,
    bridge_values: Mapping[str, Mapping[str, float]],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    actual_versions = {
        "policyengine": distribution_version("policyengine"),
        "policyengine_core": distribution_version("policyengine-core"),
        "policyengine_us": distribution_version("policyengine-us"),
    }
    if actual_versions != ENGINE_VERSIONS:
        raise RuntimeError(
            f"{config.suite}: runtime PolicyEngine stack {actual_versions} "
            f"does not match reviewed stack {ENGINE_VERSIONS}"
        )
    from policyengine_us import Simulation

    configured_cases = {case.case_id for case in config.cases}
    missing_bridge_cases = sorted(configured_cases - set(bridge_values))
    unexpected_bridge_cases = sorted(set(bridge_values) - configured_cases)
    if missing_bridge_cases or unexpected_bridge_cases:
        raise ValueError(
            f"{config.suite}: bridge-value cases differ; "
            f"missing={missing_bridge_cases}, "
            f"unexpected={unexpected_bridge_cases}"
        )

    if config.comparison_bindings:
        totals: dict[str, float] = {}
        components: dict[str, dict[str, float]] = {}
        rows_by_case: dict[
            str,
            list[tuple[str, ComparisonBinding]],
        ] = {}
        for row_id, case, binding in _comparison_rows(config):
            rows_by_case.setdefault(case.case_id, []).append((row_id, binding))
        parameters_verified = False
        for case in config.cases:
            situation = config.pe_situation(
                case,
                bridge_values[case.case_id],
            )
            _validate_pe_situation_inputs(config, case, situation)
            simulation = Simulation(situation=situation)
            if config.pe_parameter_validator is not None and not parameters_verified:
                config.pe_parameter_validator(simulation.tax_benefit_system)
                parameters_verified = True
            for row_id, binding in rows_by_case.get(case.case_id, []):
                mapping = _mapping_for_binding(config, binding)
                if mapping.policyengine_variable:
                    calculated = simulation.calculate(
                        mapping.policyengine_variable,
                        VALIDATION_YEAR,
                    )
                    value = sum(float(item) for item in calculated)
                elif mapping.policyengine_parameter:
                    parameter: Any = simulation.tax_benefit_system.parameters(
                        f"{VALIDATION_YEAR}-01-01"
                    )
                    for part in mapping.policyengine_parameter.split("."):
                        parameter = getattr(parameter, part)
                    if mapping.parameter_key:
                        parameter = getattr(parameter, mapping.parameter_key)
                    elif mapping.parameter_key_input:
                        status_codes = {
                            "single": 0,
                            "joint": 1,
                            "separate": 2,
                            "head_of_household": 3,
                            "surviving_spouse": 4,
                        }
                        raw_key = (
                            status_codes[case.filing_status]
                            if mapping.parameter_key_input == "filing_status"
                            else case.inputs[mapping.parameter_key_input]
                        )
                        selected_key = mapping.parameter_key_map.get(
                            str(raw_key),
                            mapping.parameter_key_map.get(raw_key),
                        )
                        if selected_key is None:
                            raise ValueError(
                                f"{config.suite}: no parameter key for "
                                f"{mapping.parameter_key_input}={raw_key!r}"
                            )
                        parameter = getattr(parameter, selected_key)
                    value = float(parameter)
                else:
                    raise ValueError(
                        f"{config.suite}: unsupported scored registry mapping "
                        f"for {binding.concept!r}"
                    )
                totals[row_id] = value
                components[row_id] = {binding.policyengine_target: value}
        return totals, components

    totals: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    parameters_verified = False
    for case in config.cases:
        situation = config.pe_situation(
            case,
            bridge_values[case.case_id],
        )
        _validate_pe_situation_inputs(config, case, situation)
        simulation = Simulation(situation=situation)
        if config.pe_parameter_validator is not None and not parameters_verified:
            config.pe_parameter_validator(simulation.tax_benefit_system)
            parameters_verified = True
        if config.key == "aca_ptc":
            actual_fpg = sum(
                float(value)
                for value in simulation.calculate(
                    "tax_unit_fpg",
                    VALIDATION_YEAR - 1,
                )
            )
            expected_fpg = float(case.inputs["poverty_line"])
            if abs(actual_fpg - expected_fpg) > config.tolerance:
                raise ValueError(
                    f"{case.case_id}: PolicyEngine prior-year FPL is "
                    f"{actual_fpg}; expected {expected_fpg}"
                )
            actual_fraction = sum(
                float(value)
                for value in simulation.calculate(
                    "aca_magi_fraction",
                    VALIDATION_YEAR,
                )
            )
            expected_fraction = float(case.inputs["fpl_percentage"]) / 100
            if abs(actual_fraction - expected_fraction) > 0.000001:
                raise ValueError(
                    f"{case.case_id}: PolicyEngine ACA MAGI/FPL fraction is "
                    f"{actual_fraction}; expected {expected_fraction}"
                )
        case_components: dict[str, float] = {}
        variables = dict.fromkeys(
            (
                *config.pe_output_variables,
                *config.pe_diagnostic_variables,
            )
        )
        for variable in variables:
            values = simulation.calculate(variable, VALIDATION_YEAR)
            case_components[variable] = sum(float(value) for value in values)
        components[case.case_id] = case_components
        totals[case.case_id] = sum(
            case_components[variable] for variable in config.pe_output_variables
        )
    return totals, components


def _matches(
    config: PolicyConfig,
    left: float,
    right: float,
    *,
    tolerance: float | None = None,
) -> bool:
    absolute_tolerance = config.tolerance if tolerance is None else tolerance
    difference = abs(left - right)
    if difference <= absolute_tolerance:
        return True
    scale = max(abs(left), abs(right))
    return (
        config.relative_tolerance > 0
        and scale > 0
        and difference / scale <= config.relative_tolerance
    )


def _assert_non_vacuous(
    config: PolicyConfig,
    axiom: Mapping[str, float],
    policyengine: Mapping[str, float],
) -> None:
    if set(axiom) != set(policyengine):
        raise RuntimeError(
            f"{config.suite}: Axiom and PolicyEngine comparison rows differ"
        )
    tolerances = {
        row_id: binding.tolerance for row_id, _case, binding in _comparison_rows(config)
    }
    nonzero_matches = []
    for row_id in axiom:
        tolerance = (
            config.tolerance
            if tolerances[row_id] is None
            else float(tolerances[row_id])
        )
        if (
            abs(axiom[row_id]) > tolerance
            and abs(policyengine[row_id]) > tolerance
            and _matches(
                config,
                axiom[row_id],
                policyengine[row_id],
                tolerance=tolerance,
            )
        ):
            nonzero_matches.append(row_id)
    if not nonzero_matches:
        raise RuntimeError(
            f"{config.suite}: vacuous grid: no nonzero expected case matches "
            "PolicyEngine within the reviewed tolerance"
        )


def _build_report(
    config: PolicyConfig,
    *,
    axiom: Mapping[str, float],
    fixture_inputs: Mapping[str, Mapping[str, Any]],
    policyengine: Mapping[str, float],
    policyengine_components: Mapping[str, Mapping[str, float]],
    axiom_bridge_values: Mapping[str, Mapping[str, float]] | None = None,
    axiom_diagnostic_values: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    bridge_values = axiom_bridge_values or {}
    diagnostic_values = axiom_diagnostic_values or {}
    cases: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    aggregate_state: dict[str, dict[str, Any]] = {}
    for row_id, case, binding in _comparison_rows(config):
        tolerance = config.tolerance if binding.tolerance is None else binding.tolerance
        axiom_value = axiom[row_id]
        pe_value = policyengine[row_id]
        matched = _matches(
            config,
            axiom_value,
            pe_value,
            tolerance=tolerance,
        )
        difference = axiom_value - pe_value
        case_report = {
            "case_id": row_id,
            "scenario_id": case.case_id,
            "concept": binding.concept,
            "filing_status": case.filing_status,
            "inputs": dict(case.inputs),
            "axiom_fixture_inputs": dict(fixture_inputs[case.case_id]),
            "axiom": axiom_value,
            "policyengine": pe_value,
            "policyengine_components": dict(policyengine_components[row_id]),
            "difference": difference,
            "match": matched,
        }
        if config.axiom_bridge_outputs:
            case_report["axiom_bridge_outputs"] = dict(bridge_values[case.case_id])
        if config.axiom_diagnostic_outputs:
            case_diagnostics = dict(diagnostic_values[case.case_id])
            case_report["axiom_diagnostics"] = case_diagnostics
            case_report["diagnostic_reconciliation"] = [
                {
                    "axiom_output": output,
                    "policyengine_variable": pe_variable,
                    "axiom": case_diagnostics[output],
                    "policyengine": policyengine_components[row_id][pe_variable],
                    "difference": (
                        case_diagnostics[output]
                        - policyengine_components[row_id][pe_variable]
                    ),
                }
                for output, pe_variable in (config.axiom_diagnostic_outputs.items())
            ]
        if (
            config.suite == "us-savers-grid"
            and case.case_id == "section-911-add-back-crosses-inclusive-limit"
        ):
            case_report["diagnostic_note"] = (
                "Observed match is cancellation, not section 911 parity: "
                "PolicyEngine omits the section 25B(e) add-back while "
                "PolicyEngine #9151 moves exact $24,250 into the 20-percent tier."
            )
        cases.append(case_report)
        if not matched:
            mismatches.append(
                {
                    "case_id": row_id,
                    "concept": binding.concept,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": axiom_value,
                    "right": pe_value,
                    "difference": difference,
                }
            )
        state = aggregate_state.setdefault(
            binding.concept,
            {
                "comparison": binding.comparison,
                "tolerance": tolerance,
                "comparison_count": 0,
                "match_count": 0,
                "left_positive": 0,
                "right_positive": 0,
            },
        )
        state["comparison_count"] += 1
        state["match_count"] += int(matched)
        state["left_positive"] += int(abs(axiom_value) > tolerance)
        state["right_positive"] += int(abs(pe_value) > tolerance)

    aggregates: list[dict[str, Any]] = []
    concepts: list[dict[str, Any]] = []
    for concept, state in aggregate_state.items():
        count = state["comparison_count"]
        matched = state["match_count"]
        mismatch = count - matched
        aggregates.append(
            {
                "concept": concept,
                "comparison": state["comparison"],
                "comparison_count": count,
                "match_count": matched,
                "mismatch_count": mismatch,
                "compared": count,
                "matched": matched,
                "mismatched": mismatch,
                "match_rate": 100.0 * matched / count,
                "left_positive_rate": 100.0 * state["left_positive"] / count,
                "right_positive_rate": 100.0 * state["right_positive"] / count,
            }
        )
        concepts.append(
            {
                "id": concept,
                "description": (
                    config.title
                    if len(aggregate_state) == 1
                    else concept.rsplit("#", 1)[-1].replace("_", " ")
                ),
                "category": "tax",
                "comparison": state["comparison"],
                "tolerance": state["tolerance"],
                "relative_tolerance": config.relative_tolerance,
                "priority": "high",
                "components": [],
                "parent": None,
            }
        )

    comparison_count = len(cases)
    match_count = sum(aggregate["match_count"] for aggregate in aggregates)
    mismatch_count = len(mismatches)
    match_rate = 100.0 * match_count / comparison_count
    audited_suite = config.suite in {
        "us-savers-grid",
        "us-salt-deduction-grid",
        "us-itemized-taxable-income-deductions-grid",
    }
    comparison_bindings = (
        [_binding_payload(config, binding) for binding in _scored_bindings(config)]
        if audited_suite
        else []
    )
    scored_concepts = list(aggregate_state)
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": config.suite,
        "concept": config.axiom_output,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "engines": {
            "left": "axiom",
            "right": "policyengine",
            "versions": dict(ENGINE_VERSIONS),
        },
        "engine_bindings": {
            "axiom": {
                "module": config.axiom_module_ref,
                "output": config.axiom_output,
                "outputs": scored_concepts,
                "fixture": str(config.fixture_path),
                "supplemental_fixtures": [
                    str(path) for path in config.supplemental_fixture_paths
                ],
                "bridge_outputs": dict(config.axiom_bridge_outputs),
                "diagnostic_outputs": dict(config.axiom_diagnostic_outputs),
            },
            "policyengine": {
                "outputs": list(config.pe_output_variables),
                "diagnostic_outputs": list(config.pe_diagnostic_variables),
                "boundary": config.pe_boundary,
                "comparison_bindings": comparison_bindings,
            },
        },
        "tolerance": {
            "absolute": config.tolerance,
            "relative": config.relative_tolerance,
        },
        "case_count": comparison_count,
        "scenario_count": len(config.cases),
        "concepts": concepts,
        "aggregates": aggregates,
        "summary": {
            "comparison_count": comparison_count,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "error_count": 0,
            "errors_by_engine": {},
            "mismatches_by_concept": (
                [
                    {
                        "value": aggregate["concept"],
                        "count": aggregate["mismatch_count"],
                    }
                    for aggregate in aggregates
                    if aggregate["mismatch_count"]
                ]
            ),
            "mismatches_by_kind": (
                [{"value": "amount_difference", "count": mismatch_count}]
                if mismatch_count
                else []
            ),
            "mismatches_by_scenario": {},
            "axiom_vs_policyengine_match_rate": match_rate,
        },
        "mismatches": mismatches,
        "cases": cases,
    }


def generate(policy: str, roots: list[Path]) -> dict[str, Any]:
    if policy not in POLICIES:
        raise KeyError(f"unknown federal policy {policy!r}")
    if not roots:
        raise ValueError("at least one --rulespec-root is required")
    config = POLICIES[policy]
    _validate_policy_config(config)
    _assert_registry_comparable_bindings(config)
    (
        _fixture,
        axiom,
        fixture_inputs,
        bridge_values,
        diagnostic_values,
    ) = _axiom_values(config, roots)
    policyengine, components = _policyengine_values(
        config,
        bridge_values,
    )
    _assert_non_vacuous(config, axiom, policyengine)
    return _build_report(
        config,
        axiom=axiom,
        fixture_inputs=fixture_inputs,
        policyengine=policyengine,
        policyengine_components=components,
        axiom_bridge_values=bridge_values,
        axiom_diagnostic_values=diagnostic_values,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=sorted(POLICIES))
    parser.add_argument(
        "--rulespec-root",
        action="append",
        type=Path,
        default=[],
        help="RuleSpec checkout root; repeatable and supplied by comparison YAML",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for key, config in sorted(POLICIES.items()):
            print(f"{key:32s} {config.suite}")
        return 0
    if args.policy is None or args.output is None:
        parser.error("--policy and --output are required unless --list is used")
    report = generate(args.policy, [root.resolve() for root in args.rulespec_root])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_json_text(report))
    summary = report["summary"]
    print(
        f"{report['suite']}: {summary['match_count']}/{report['case_count']} "
        f"matches ({summary['axiom_vs_policyengine_match_rate']:.2f}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
