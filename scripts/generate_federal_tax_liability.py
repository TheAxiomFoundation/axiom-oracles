#!/usr/bin/env python3
"""Generate one federal tax-liability case-grid report.

Each invocation selects exactly one policy.  The selected policy's six-case
grid is evaluated independently:

* ``axiom`` reads the expected value from that policy's engine-verified
  RuleSpec companion fixture; and
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
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import report_json_text  # noqa: E402

VALIDATION_YEAR = 2026


@dataclass(frozen=True)
class FederalCase:
    """One contract case and its neutral, auditable input values."""

    case_id: str
    filing_status: str
    inputs: Mapping[str, float | int | str]


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
    pe_situation: Callable[[FederalCase], dict[str, Any]]
    fixture_input_validator: Callable[
        [FederalCase, Mapping[str, Any]], None
    ]
    tolerance: float = 0.01
    relative_tolerance: float = 0.0


def _case(
    case_id: str,
    filing_status: str,
    **inputs: float | int | str,
) -> FederalCase:
    return FederalCase(case_id, filing_status, inputs)


# GRID-CONTRACT P1.  ``self_employment_income`` is Schedule C-style gross net
# profit; PolicyEngine applies the section 1402(a)(12) employer-share factor.
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
        "amt-single-wage-se",
        "single",
        primary_wages=100_000,
        spouse_wages=0,
        self_employment_income=150_000,
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
    primary_inputs: Mapping[str, float | int],
    spouse_inputs: Mapping[str, float | int] | None = None,
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
    return {
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
            f"{module}#input.aca_ptc_annual_slcsp_benchmark_premium": inputs[
                "slcsp"
            ],
            f"{module}#input.aca_ptc_annual_enrolled_premium": inputs[
                "enrolled_premium"
            ],
            f"{module}#input.aca_ptc_coverage_month_count": inputs[
                "coverage_months"
            ],
        },
    )


def _validate_self_employment_fixture(
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
            f"us-seca-grid: fixture case {case.case_id!r} relation {relation!r} "
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
                f"us-seca-grid: fixture case {case.case_id!r} Person {index} "
                "input is not a mapping"
            )
        _require_fixture_values(
            suite="us-seca-grid",
            case_id=case.case_id,
            actual=person,
            expected={
                profit_key: expected_person["self_employment_income"],
                wages_key: expected_person["wages"],
                **domestic_inputs,
            },
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
        "us:statutes/26/911/a/1#input."
        "elected_foreign_earned_income_exclusion_amount",
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


# The RuleSpec paths and output names below are completed by the companion
# RuleSpec lanes.  Keeping them in this one registry makes each run select and
# read only one fixture; a missing companion cannot prevent another policy from
# running.
POLICIES: dict[str, PolicyConfig] = {
    "additional_medicare_tax": PolicyConfig(
        key="additional_medicare_tax",
        suite="us-additional-medicare-grid",
        title="Additional Medicare Tax",
        axiom_module_ref="PENDING",
        fixture_path=Path("PENDING"),
        axiom_output="PENDING#additional_medicare_tax",
        pe_output_variables=("additional_medicare_tax",),
        pe_boundary=(
            "TaxUnit Form 8959 total over wage and taxable self-employment income"
        ),
        cases=_ADDITIONAL_MEDICARE_CASES,
        pe_situation=_payroll_situation,
        fixture_input_validator=lambda _case, _actual: None,
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
        pe_situation=_payroll_situation,
        fixture_input_validator=_validate_self_employment_fixture,
    ),
    "net_investment_income_tax": PolicyConfig(
        key="net_investment_income_tax",
        suite="us-niit-grid",
        title="Net Investment Income Tax",
        axiom_module_ref=(
            "us:policies/income_tax/net_investment_income_tax_pipeline"
        ),
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
        pe_situation=_niit_situation,
        fixture_input_validator=_validate_niit_fixture,
    ),
    "aca_ptc": PolicyConfig(
        key="aca_ptc",
        suite="us-aca-ptc-grid",
        title="ACA Premium Tax Credit",
        axiom_module_ref="us:policies/aca/ptc_pipeline",
        fixture_path=Path("us/policies/aca/ptc_pipeline.test.yaml"),
        axiom_output=(
            "us:policies/aca/ptc_pipeline#aca_ptc_annual_premium_tax_credit"
        ),
        # `aca_ptc` omits the enrolled-premium cap.  `used_aca_ptc` applies it
        # and therefore matches the section 36B / GRID-CONTRACT output boundary.
        pe_output_variables=("used_aca_ptc",),
        pe_boundary=(
            "TaxUnit annual benchmark credit capped by enrolled marketplace "
            "premium for twelve months"
        ),
        cases=_ACA_PTC_CASES,
        pe_situation=_aca_ptc_situation,
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


def _axiom_values(
    config: PolicyConfig,
    roots: list[Path],
) -> tuple[Path, dict[str, float], dict[str, dict[str, Any]]]:
    if not config.axiom_output.startswith(f"{config.axiom_module_ref}#"):
        raise ValueError(
            f"{config.suite}: Axiom output {config.axiom_output!r} is not "
            f"defined by configured module {config.axiom_module_ref!r}"
        )
    fixture = _fixture_file(config, roots)
    records = _fixture_records(fixture)
    by_name = {str(record.get("name")): record for record in records}
    values: dict[str, float] = {}
    fixture_inputs: dict[str, dict[str, Any]] = {}
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
        if not isinstance(outputs, dict) or config.axiom_output not in outputs:
            raise ValueError(
                f"{fixture}: case {case.case_id!r} has no output "
                f"{config.axiom_output!r}"
            )
        values[case.case_id] = float(str(outputs[config.axiom_output]))
        raw_inputs = record.get("input") or {}
        if not isinstance(raw_inputs, dict):
            raise ValueError(f"{fixture}: case {case.case_id!r} input is not a mapping")
        config.fixture_input_validator(case, raw_inputs)
        fixture_inputs[case.case_id] = raw_inputs
    return fixture, values, fixture_inputs


def _policyengine_values(
    config: PolicyConfig,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    from policyengine_us import Simulation

    totals: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    for case in config.cases:
        simulation = Simulation(situation=config.pe_situation(case))
        case_components: dict[str, float] = {}
        for variable in config.pe_output_variables:
            values = simulation.calculate(variable, VALIDATION_YEAR)
            case_components[variable] = sum(float(value) for value in values)
        components[case.case_id] = case_components
        totals[case.case_id] = sum(case_components.values())
    return totals, components


def _matches(config: PolicyConfig, left: float, right: float) -> bool:
    difference = abs(left - right)
    if difference <= config.tolerance:
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
    nonzero_matches = [
        case.case_id
        for case in config.cases
        if abs(axiom[case.case_id]) > config.tolerance
        and abs(policyengine[case.case_id]) > config.tolerance
        and _matches(
            config,
            axiom[case.case_id],
            policyengine[case.case_id],
        )
    ]
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
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    match_count = 0
    left_positive = 0
    right_positive = 0
    for case in config.cases:
        axiom_value = axiom[case.case_id]
        pe_value = policyengine[case.case_id]
        matched = _matches(config, axiom_value, pe_value)
        match_count += int(matched)
        left_positive += int(abs(axiom_value) > config.tolerance)
        right_positive += int(abs(pe_value) > config.tolerance)
        difference = axiom_value - pe_value
        cases.append(
            {
                "case_id": case.case_id,
                "concept": config.axiom_output,
                "filing_status": case.filing_status,
                "inputs": dict(case.inputs),
                "axiom_fixture_inputs": dict(fixture_inputs[case.case_id]),
                "axiom": axiom_value,
                "policyengine": pe_value,
                "policyengine_components": dict(policyengine_components[case.case_id]),
                "difference": difference,
                "match": matched,
            }
        )
        if not matched:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": config.axiom_output,
                    "kind": "amount_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": axiom_value,
                    "right": pe_value,
                    "difference": difference,
                }
            )
    comparison_count = len(config.cases)
    mismatch_count = len(mismatches)
    match_rate = 100.0 * match_count / comparison_count
    aggregate = {
        "concept": config.axiom_output,
        "comparison": "amount",
        "comparison_count": comparison_count,
        "match_count": match_count,
        "mismatch_count": mismatch_count,
        "compared": comparison_count,
        "matched": match_count,
        "mismatched": mismatch_count,
        "match_rate": match_rate,
        "left_positive_rate": 100.0 * left_positive / comparison_count,
        "right_positive_rate": 100.0 * right_positive / comparison_count,
    }
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": config.suite,
        "concept": config.axiom_output,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "engines": {"left": "axiom", "right": "policyengine"},
        "engine_bindings": {
            "axiom": {
                "module": config.axiom_module_ref,
                "output": config.axiom_output,
                "fixture": str(config.fixture_path),
            },
            "policyengine": {
                "outputs": list(config.pe_output_variables),
                "boundary": config.pe_boundary,
            },
        },
        "tolerance": {
            "absolute": config.tolerance,
            "relative": config.relative_tolerance,
        },
        "case_count": comparison_count,
        "concepts": [
            {
                "id": config.axiom_output,
                "description": config.title,
                "category": "tax",
                "comparison": "amount",
                "tolerance": config.tolerance,
                "relative_tolerance": config.relative_tolerance,
                "priority": "high",
                "components": [],
                "parent": None,
            }
        ],
        "aggregates": [aggregate],
        "summary": {
            "comparison_count": comparison_count,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "error_count": 0,
            "errors_by_engine": {},
            "mismatches_by_concept": (
                [{"value": config.axiom_output, "count": mismatch_count}]
                if mismatch_count
                else []
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
    _fixture, axiom, fixture_inputs = _axiom_values(config, roots)
    policyengine, components = _policyengine_values(config)
    _assert_non_vacuous(config, axiom, policyengine)
    return _build_report(
        config,
        axiom=axiom,
        fixture_inputs=fixture_inputs,
        policyengine=policyengine,
        policyengine_components=components,
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
