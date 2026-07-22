from __future__ import annotations

from ..core.case import Case
from ..adapters.canada_official.pdoc import PAY_PERIODS


PDOC_MODULE = "ca:policies/cra/t4127-2026/ontario-salary-payroll"
CPP = f"{PDOC_MODULE}#pdoc_cpp_employee_contribution_per_period"
EI = f"{PDOC_MODULE}#pdoc_ei_employee_premium_per_period"
INCOME_TAX = f"{PDOC_MODULE}#pdoc_estimated_tax_deduction_per_period"

PDOC_OUTPUTS = (CPP, EI, INCOME_TAX)
CA_SCOPE = {"type": "country", "geoid": "CA"}


def ca_cra_pdoc_cases() -> list[Case]:
    return [
        _case(
            "ca-cra-pdoc-biweekly-2000",
            income_amount=2_000,
            pay_period_frequency="BI_WEEKLY",
        ),
        _case(
            "ca-cra-pdoc-monthly-3000",
            income_amount=3_000,
            pay_period_frequency="MONTHLY_12PP",
        ),
        _case(
            "ca-cra-pdoc-weekly-1000",
            income_amount=1_000,
            pay_period_frequency="WEEKLY_52PP",
        ),
    ]


def _case(
    case_id: str,
    *,
    income_amount: float,
    pay_period_frequency: str,
) -> Case:
    pay_periods = PAY_PERIODS[pay_period_frequency]
    return Case(
        case_id=case_id,
        period="2026-07-20",
        outputs=PDOC_OUTPUTS,
        metadata={
            "locale": "CA-ON",
            "scope": CA_SCOPE,
            "scenario": "cra-pdoc-ontario-salary",
            "axiom_entity": "Person",
            "axiom_entity_id": "person",
            "axiom_inputs": _axiom_inputs(income_amount, pay_periods),
            "canada_pdoc": {
                "jurisdiction": "ONTARIO",
                "payPeriodFrequency": pay_period_frequency,
                "incomeAmount": income_amount,
            },
            "canada_pdoc_outputs": {
                "cpp_employee_contribution": CPP,
                "ei_employee_premium": EI,
                "income_tax": INCOME_TAX,
            },
            "canada_pdoc_output_basis": "per_period",
        },
    )


def _input(name: str) -> str:
    return f"{PDOC_MODULE}#input.{name}"


def _axiom_inputs(income_amount: float, pay_periods: int) -> dict[str, float | int | bool]:
    return {
        _input("pay_periods_in_year"): pay_periods,
        _input("gross_remuneration_for_pay_period"): income_amount,
        _input("cpp_pensionable_earnings_for_pay_period"): income_amount,
        _input("ei_insurable_earnings_for_pay_period"): income_amount,
        _input("cpp_contribution_months_required"): 12,
        _input("employee_ytd_cpp_contribution_before_pay_period"): 0,
        _input("employee_ytd_cpp2_contribution_before_pay_period"): 0,
        _input("employee_ytd_pensionable_earnings_before_pay_period"): 0,
        _input("employee_ytd_ei_premium_before_pay_period"): 0,
        _input("registered_plan_deductions_for_pay_period"): 0,
        _input("deductible_alimony_for_pay_period"): 0,
        _input("union_dues_for_pay_period"): 0,
        _input("prescribed_zone_annual_deduction"): 0,
        _input("authorized_annual_deductions"): 0,
        _input("federal_td1_not_filed"): True,
        _input("federal_td1_total_claim_amount"): 0,
        _input("ontario_td1_not_filed"): True,
        _input("ontario_td1_total_claim_amount"): 0,
        _input("other_federal_non_refundable_credit_amount"): 0,
        _input("other_ontario_non_refundable_credit_amount"): 0,
        _input("federal_labour_sponsored_funds_tax_credit_for_pay_period"): 0,
        _input("disabled_dependants_count_for_ontario_tax_reduction"): 0,
        _input("dependants_under_age_19_count_for_ontario_tax_reduction"): 0,
        _input("additional_tax_deduction_requested_for_pay_period"): 0,
    }
