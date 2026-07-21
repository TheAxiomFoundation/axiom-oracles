from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from axiom_oracles.adapters.canada_official.child_family import (
    _parse_amount_rows,
    _project_values as project_family_values,
)
from axiom_oracles.adapters.canada_official.pdoc import (
    _project_values as project_pdoc_values,
    _salary_payload,
)
from axiom_oracles.adapters.canada_official.registry import ORACLES, get_oracle
from axiom_oracles.core.case import Case
from axiom_oracles.core.geography import normalize_scope
from axiom_oracles.suites.ca_cra_family_benefits import (
    CCB,
    CHILD_DISABILITY_BENEFIT,
    GROCERIES_AND_ESSENTIALS_BENEFIT,
    ca_cra_family_benefit_cases,
)
from axiom_oracles.suites.ca_cra_pdoc import (
    PDOC_MODULE,
    PDOC_OUTPUTS,
    ca_cra_pdoc_cases,
)
from scripts.run_canada_official_comparison import _axiom_runner


def test_parse_child_family_amount_rows_and_annualize() -> None:
    document = """
    <div class="col-xs-7 col-sm-8">Canada child benefit monthly amount</div>
    <div class="col-xs-5 col-sm-3 text-right">$1,253.33</div>
    <div class="col-xs-7 col-sm-8">Canada Groceries and Essentials Benefit quarterly amount</div>
    <div class="col-xs-5 col-sm-3 text-right">$339.50</div>
    """
    amounts = _parse_amount_rows(document)
    case = ca_cra_family_benefit_cases()[0]
    values = project_family_values(case, amounts)
    assert values[CCB] == 15_039.96
    assert values[CHILD_DISABILITY_BENEFIT] == 0
    assert values[GROCERIES_AND_ESSENTIALS_BENEFIT] == 1_358.0


def test_pdoc_salary_defaults_and_output_projection() -> None:
    payload = _salary_payload({"incomeAmount": 2_000})
    assert payload["calculationType"] == "SALARY"
    assert payload["payPeriodFrequency"] == "BI_WEEKLY"
    case = Case(
        case_id="pdoc",
        period="2026-07-20",
        metadata={
            "canada_pdoc_outputs": {
                "cpp_employee_contribution": "cpp",
                "ei_employee_premium": "ei",
            }
        },
    )
    values = project_pdoc_values(
        case,
        payload,
        {
            "totalCppOrQppDeductions": Decimal("110.99"),
            "totalEmploymentInsuranceDeductions": Decimal("32.60"),
        },
    )
    assert values == {"cpp": 2_885.74, "ei": 847.6}

    per_period_case = Case(
        case_id="pdoc-per-period",
        period="2026-07-20",
        metadata={
            "canada_pdoc_output_basis": "per_period",
            "canada_pdoc_outputs": {
                "cpp_employee_contribution": "cpp",
                "income_tax": "tax",
            },
        },
    )
    values = project_pdoc_values(
        per_period_case,
        payload,
        {
            "totalCppOrQppDeductions": Decimal("110.99"),
            "federalTaxDeduction": Decimal("163.23"),
            "provincialTaxDeduction": Decimal("91.60"),
        },
    )
    assert values == {"cpp": 110.99, "tax": 254.83}


def test_family_suite_has_fully_qualified_axiom_inputs() -> None:
    cases = ca_cra_family_benefit_cases()
    assert len(cases) == 3
    for case in cases:
        inputs = case.metadata["axiom_inputs"]
        assert inputs
        assert all("#input." in key for key in inputs)
        assert set(case.outputs) == {
            CCB,
            "ca:policies/cra/benefits-2026/federal-family-and-climate-benefits#child_disability_benefit_annual_amount",
            GROCERIES_AND_ESSENTIALS_BENEFIT,
        }


def test_pdoc_suite_has_fully_qualified_axiom_inputs() -> None:
    cases = ca_cra_pdoc_cases()
    assert len(cases) == 3
    for case in cases:
        inputs = case.metadata["axiom_inputs"]
        assert len(inputs) == 24
        assert inputs[
            "ca:policies/cra/t4127-2026/ontario-salary-payroll#input.pay_periods_in_year"
        ] in {12, 26, 52}
        assert inputs[
            "ca:policies/cra/t4127-2026/ontario-salary-payroll#input.cpp_contribution_months_required"
        ] == 12
        assert case.outputs == PDOC_OUTPUTS
        assert case.metadata["canada_pdoc"]["jurisdiction"] == "ONTARIO"
        assert case.metadata["canada_pdoc_output_basis"] == "per_period"


def test_canada_is_a_supported_country_scope() -> None:
    scope = normalize_scope({"type": "country", "geoid": "ca"})
    assert scope is not None
    assert scope.as_dict() == {"type": "country", "geoid": "CA"}


def test_canada_official_registry_covers_numeric_and_non_numeric_surfaces() -> None:
    assert {item.oracle_id for item in ORACLES} == {
        "cra-child-family",
        "cra-pdoc",
        "cra-gst-hst",
        "rq-webras",
        "esdc-ei-estimator",
        "esdc-retirement-calculator",
        "esdc-canada-disability-benefit",
        "canada-benefits-finder",
        "statcan-spsdm",
    }
    assert get_oracle("cra-pdoc").implemented is True
    assert get_oracle("canada-benefits-finder").comparison_role == "coverage"
    assert get_oracle("statcan-spsdm").mode == "licensed_local_model"


def test_official_comparison_wrapper_does_not_shadow_imported_module(
    tmp_path: Path,
) -> None:
    runner = _axiom_runner(
        tmp_path / "rulespec-ca",
        tmp_path / "axiom-rules-engine",
        module=PDOC_MODULE,
        entity="Person",
        entity_id="person",
    )
    assert runner.program_imports == (PDOC_MODULE,)
    assert runner.generated_program_target is None
