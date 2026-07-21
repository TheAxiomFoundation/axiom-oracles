from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.results import EngineResult
from .common import (
    DEFAULT_TIMEOUT_SECONDS,
    OfficialArtifact,
    artifact_from_response,
    cra_json,
    new_session,
)


PDOC_APP_URL = "https://apps.cra-arc.gc.ca/ebci/rhpd/beta/entry/en"
PDOC_API_ROOT = "https://apps.cra-arc.gc.ca/ebci/rhpd/rest/api/ext/priv"
PDOC_METADATA_KEY = "canada_pdoc"

PAY_PERIODS = {
    "DAILY": 260,
    "WEEKLY_52PP": 52,
    "BI_WEEKLY": 26,
    "SEMI_MONTHLY": 24,
    "MONTHLY_12PP": 12,
    "TEN_10PP": 10,
    "THIRTEEN_13PP": 13,
    "TWENTYTWO_22PP": 22,
    "WEEKLY_53PP": 53,
    "BI_WEEKLY_27PP": 27,
}


@dataclass(frozen=True)
class PdocCalculation:
    values: dict[str, Any]
    artifacts: tuple[OfficialArtifact, ...]


class PdocClient:
    """HTTP client for CRA's public Payroll Deductions Online Calculator."""

    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout
        self.session = new_session()
        self.client_id = str(uuid.uuid4())
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "rccr-client-id": self.client_id,
            }
        )
        self._bootstrapped = False

    def calculate_salary(self, request: Mapping[str, Any]) -> PdocCalculation:
        self._bootstrap()
        payload = _salary_payload(request)
        artifacts: list[OfficialArtifact] = []

        claim_response = self._post("calculator/SALARY/calculateClaimAmounts", payload)
        claim_amounts = cra_json(claim_response)
        artifacts.append(artifact_from_response(claim_response))
        payload.setdefault("td1ClaimAmountFed", claim_amounts["federalBasicPersonalAmount"])
        payload.setdefault(
            "td1ClaimAmountProv",
            claim_amounts["provincialTerritoryBasicPersonalAmount"],
        )

        display_response = self._post("calculator/SALARY/getTaxExemptDisplay", payload)
        payload.update(cra_json(display_response))
        artifacts.append(artifact_from_response(display_response))

        validate_response = self._post("calculator/SALARY/validate", payload)
        cra_json(validate_response)
        artifacts.append(artifact_from_response(validate_response))

        calculation_response = self._post("calculator/SALARY/calculate", payload)
        calculation = cra_json(calculation_response)
        artifacts.append(artifact_from_response(calculation_response))
        return PdocCalculation(values=calculation, artifacts=tuple(artifacts))

    def app_version(self) -> str:
        response = self.session.get(
            f"{PDOC_API_ROOT}/calculator/getappversion",
            timeout=self.timeout,
        )
        return str(cra_json(response))

    def _bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self.session.get(PDOC_APP_URL, timeout=self.timeout).raise_for_status()
        response = self._post("log/noop", {})
        response.raise_for_status()
        token = self.session.cookies.get("XSRF-TOKEN")
        if not token:
            raise RuntimeError("CRA PDOC did not issue an XSRF token")
        self.session.headers["X-XSRF-TOKEN"] = token
        self._bootstrapped = True

    def _post(self, path: str, payload: Mapping[str, Any]):
        return self.session.post(
            f"{PDOC_API_ROOT}/{path}",
            json=dict(payload),
            timeout=self.timeout,
        )


class PdocRunner(EngineAdapter):
    name = "canada-pdoc"

    def __init__(self, client: PdocClient | None = None) -> None:
        self.client = client or PdocClient()

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        requested = set(variables or ())
        results: list[EngineResult] = []
        for case in cases:
            config = case.metadata.get(PDOC_METADATA_KEY)
            if not isinstance(config, Mapping):
                results.append(
                    EngineResult(
                        engine=self.name,
                        household_id=case.case_id,
                        values={},
                        errors=(f"case metadata missing {PDOC_METADATA_KEY!r}",),
                    )
                )
                continue
            try:
                calculation = self.client.calculate_salary(config)
                values = _project_values(case, config, calculation.values)
                if requested:
                    values = {key: value for key, value in values.items() if key in requested}
                results.append(
                    EngineResult(
                        engine=self.name,
                        household_id=case.case_id,
                        values=values,
                        raw={
                            "response": calculation.values,
                            "artifacts": [item.as_dict() for item in calculation.artifacts],
                        },
                    )
                )
            except Exception as exc:
                results.append(
                    EngineResult(
                        engine=self.name,
                        household_id=case.case_id,
                        values={},
                        errors=(str(exc),),
                    )
                )
        return results


def _salary_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "calculationType": "SALARY",
        "jurisdiction": "ONTARIO",
        "payPeriodFrequency": "BI_WEEKLY",
        "datePaid": "2026-07-20T04:00:00.000Z",
        "employeeName": "Axiom comparison case",
        "employerName": "Axiom",
        "incomeAmount": 0,
        "vacationPay": None,
        "salaryType": "NO_BONUS_PAY_NO_RETROACTIVE_PAY",
        "taxableBenefitsFlag": False,
        "quebecTaxableBenefitsFlag": False,
        "unionDuesFlag": False,
        "clergyFlag": False,
        "clergyType": "NO_HOUSING",
        "contributionEmployerRrspFlag": False,
        "contributionRrspOrRppOrPrppFlag": False,
        "deductionForLivingInPrescribedZoneFlag": False,
        "otherDeductionsAndNonRefundableFlag": False,
        "numberOfDependentsFlag": False,
        "tipsFlag": False,
        "alimonyOrMaintenancePaymentsFlag": False,
        "taxIndigenousFlag": False,
        "cppEqualizationFlag": False,
        "td1ClaimCodeType": "CLAIM_AMOUNT_TD1",
        "federalClaimCode": "CLAIM_CODE_1",
        "provinceTerritoryClaimCode": "CLAIM_CODE_1",
        "requestedAdditionalTaxDeductions": None,
        "cppQppType": "CPP_QPP_YEAR_TO_DATE",
        "numberPensionableMonths": 12,
        "pensionableEarningsYearToDate": None,
        "cppOrQppContributionsDeductedYearToDate": None,
        "secondAdditionalCppOrQppContributionsDeductedYearToDate": None,
        "employmentInsuranceType": "EI_YEAR_TO_DATE",
        "insurableEarningsYearToDate": None,
        "employmentInsuranceDeductedYearToDate": None,
        "employerEmploymentInsurancePremiumRate": 1.4,
    }
    payload.update(request)
    return payload


def _project_values(
    case: Case,
    request: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, float]:
    periods = PAY_PERIODS[str(request.get("payPeriodFrequency", "BI_WEEKLY"))]
    basis = str(case.metadata.get("canada_pdoc_output_basis", "annual"))
    multiplier = periods if basis == "annual" else 1
    if basis not in {"annual", "per_period"}:
        raise ValueError(f"unsupported CRA PDOC output basis: {basis}")
    targets = case.metadata.get("canada_pdoc_outputs", {})
    if not isinstance(targets, Mapping):
        return {}
    response_fields = {
        "cpp_employee_contribution": "totalCppOrQppDeductions",
        "ei_employee_premium": "totalEmploymentInsuranceDeductions",
        "federal_income_tax": "federalTaxDeduction",
        "provincial_income_tax": "provincialTaxDeduction",
        "net_pay": "netAmount",
    }
    values: dict[str, float] = {}
    for surface, concept in targets.items():
        if surface == "income_tax":
            federal = response.get("federalTaxDeduction")
            provincial = response.get("provincialTaxDeduction")
            if federal is not None and provincial is not None:
                values[str(concept)] = round(
                    (float(federal) + float(provincial)) * multiplier,
                    2,
                )
            continue
        field = response_fields.get(str(surface))
        if field and response.get(field) is not None:
            values[str(concept)] = round(float(response[field]) * multiplier, 2)
    return values
