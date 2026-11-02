from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urljoin

from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.results import EngineResult
from .common import DEFAULT_TIMEOUT_SECONDS, OfficialArtifact, artifact_from_response, new_session


LANDING_URL = (
    "https://www.canada.ca/en/revenue-agency/services/child-family-benefits/"
    "child-family-benefits-calculator.html"
)
APP_URL = "https://apps.cra-arc.gc.ca/ebci/icbc/prot/ntr?request_locale=en_CA"
APP_ROOT = "https://apps.cra-arc.gc.ca"
METADATA_KEY = "canada_child_family"

_PROVINCIAL_FORM_NAMES = {
    "AB": "alberta",
    "BC": "britishcolumbia",
    "MB": "manitoba",
    "NB": "newbrunswick",
    "NL": "newfoundlandlabrador",
    "NT": "northwestterritories",
    "NS": "novascotia",
    "NU": "nunavut",
    "ON": "ontario",
    "PEI": "princeedwardisland",
    "QC": "quebec",
    "SK": "saskatchewan",
    "YK": "yukon",
}

_TOKEN_RE = re.compile(r'name="token" value="([^"]+)"')
_AMOUNT_ROW_RE = re.compile(
    r'<div class="col-xs-7 col-sm-8">\s*(.*?)\s*</div>\s*'
    r'<div class="col-xs-5 col-sm-3 text-right">\s*\$([0-9,]+(?:\.[0-9]+)?)\s*</div>',
    re.DOTALL,
)


@dataclass(frozen=True)
class ChildFamilyCalculation:
    amounts: dict[str, float]
    artifacts: tuple[OfficialArtifact, ...]
    results_html: str


class ChildFamilyBenefitsClient:
    """Session client for CRA's public child and family benefits calculator."""

    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    def calculate(self, config: Mapping[str, Any]) -> ChildFamilyCalculation:
        session = new_session()
        artifacts: list[OfficialArtifact] = []
        landing = session.get(LANDING_URL, timeout=self.timeout)
        landing.raise_for_status()
        artifacts.append(artifact_from_response(landing))
        response = session.get(
            APP_URL,
            headers={"Referer": LANDING_URL},
            timeout=self.timeout,
        )
        response.raise_for_status()
        artifacts.append(artifact_from_response(response))

        response = self._post(
            session,
            response,
            "/ebci/icbc/prot/proc_taxyear",
            {"taxYear": str(config.get("tax_year", 2025))},
            "action:proc_taxyear",
        )
        artifacts.append(artifact_from_response(response))
        response = self._post(
            session,
            response,
            "/ebci/icbc/prot/proc_personal",
            {
                "residencyStatus": str(config.get("residency_status", "CANADIAN")),
                "province": str(config.get("province", "ON")),
                "maritalStatus": str(config.get("marital_status", "SINGLE")),
            },
            "action:proc_personal",
        )
        artifacts.append(artifact_from_response(response))

        children = list(config.get("children", ()))
        response = self._post(
            session,
            response,
            "/ebci/icbc/prot/proc_family",
            {
                "numOfChildren": str(len(children)),
                "dateOfBirth": str(config["applicant_date_of_birth"]),
                "eligibleForDisabilitySupplement": _bool_text(
                    config.get("eligible_for_disability_supplement", False)
                ),
            },
            "action:proc_family",
        )
        artifacts.append(artifact_from_response(response))

        for index, child in enumerate(children, start=1):
            response = self._post(
                session,
                response,
                "/ebci/icbc/prot/addchld",
                {
                    "name": str(child.get("name", f"Child {index}")),
                    "dateOfBirth": str(child["date_of_birth"]),
                    "disabled": _bool_text(child.get("disabled", False)),
                    "inSharedCustody": _bool_text(
                        child.get("in_shared_custody", False)
                    ),
                },
                "action:addchld",
            )
            artifacts.append(artifact_from_response(response))

        response = self._post(
            session,
            response,
            "/ebci/icbc/prot/proc_children",
            {},
            "action:proc_children",
        )
        artifacts.append(artifact_from_response(response))
        financial = {
            "netIncome": str(config["net_income"]),
            "workingIncome": str(config.get("working_income", config["net_income"])),
            "uccbAndRdspIncome": str(config.get("uccb_and_rdsp_income", 0)),
            "uccbAndRdspRepayment": str(config.get("uccb_and_rdsp_repayment", 0)),
        }
        if config.get("spouse_net_income") is not None:
            financial["spouseNetIncome"] = str(config["spouse_net_income"])
        response = self._post(
            session,
            response,
            "/ebci/icbc/prot/proc_financial",
            financial,
            "action:proc_financial",
        )
        artifacts.append(artifact_from_response(response))

        province_code = str(config.get("province", "ON")).upper()
        province = _PROVINCIAL_FORM_NAMES.get(province_code, province_code.lower())
        provincial_fields = dict(config.get("provincial_fields", {}))
        if province_code == "ON":
            provincial_fields = {
                "rent": 0,
                "propertyTaxes": 0,
                "energyOnAReserveCost": 0,
                "publicLongTermCareCost": 0,
                "northernOntarioResident": False,
                "livingInStudentResidence": False,
                **provincial_fields,
            }
        if _has_form(response.text, f"proc_{province}"):
            response = self._post(
                session,
                response,
                f"/ebci/icbc/prot/proc_{province}",
                {key: _form_text(value) for key, value in provincial_fields.items()},
                f"action:proc_{province}",
            )
            artifacts.append(artifact_from_response(response))

        amounts = _parse_amount_rows(response.text)
        if not amounts:
            raise RuntimeError("CRA child/family calculator returned no result amounts")
        return ChildFamilyCalculation(
            amounts=amounts,
            artifacts=tuple(artifacts),
            results_html=response.text,
        )

    def _post(
        self,
        session,
        previous_response,
        path: str,
        fields: Mapping[str, Any],
        action_name: str,
    ):
        token_match = _TOKEN_RE.search(previous_response.text)
        if not token_match:
            raise RuntimeError(f"CRA calculator form at {previous_response.url} has no token")
        payload = {
            "struts.token.name": "token",
            "token": token_match.group(1),
            **dict(fields),
            action_name: "Next",
        }
        response = session.post(
            urljoin(APP_ROOT, path),
            data=payload,
            headers={"Referer": previous_response.url},
            timeout=self.timeout,
        )
        response.raise_for_status()
        if "alert alert-danger" in response.text:
            raise RuntimeError(f"CRA calculator rejected fields at {path}")
        return response


class ChildFamilyBenefitsRunner(EngineAdapter):
    name = "canada-child-family"

    def __init__(self, client: ChildFamilyBenefitsClient | None = None) -> None:
        self.client = client or ChildFamilyBenefitsClient()

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        requested = set(variables or ())
        results: list[EngineResult] = []
        for case in cases:
            config = case.metadata.get(METADATA_KEY)
            if not isinstance(config, Mapping):
                results.append(
                    EngineResult(
                        engine=self.name,
                        household_id=case.case_id,
                        values={},
                        errors=(f"case metadata missing {METADATA_KEY!r}",),
                    )
                )
                continue
            try:
                calculation = self.client.calculate(config)
                values = _project_values(case, calculation.amounts)
                if requested:
                    values = {key: value for key, value in values.items() if key in requested}
                results.append(
                    EngineResult(
                        engine=self.name,
                        household_id=case.case_id,
                        values=values,
                        raw={
                            "amounts": calculation.amounts,
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


def _parse_amount_rows(document: str) -> dict[str, float]:
    amounts: dict[str, float] = {}
    for raw_label, raw_amount in _AMOUNT_ROW_RE.findall(document):
        label = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw_label)).split())
        amounts[label] = float(raw_amount.replace(",", ""))
    return amounts


def _project_values(case: Case, amounts: Mapping[str, float]) -> dict[str, float]:
    targets = case.metadata.get("canada_child_family_outputs", {})
    if not isinstance(targets, Mapping):
        return {}
    labels = {
        "canada_child_benefit": ("Canada child benefit monthly amount", 12),
        "child_disability_benefit": ("Child disability benefit monthly amount", 12),
        "canada_groceries_and_essentials_benefit": (
            "Canada Groceries and Essentials Benefit quarterly amount",
            4,
        ),
        "ontario_child_benefit": ("Ontario child benefit monthly amount", 12),
        "ontario_sales_tax_credit": ("Ontario sales tax credit monthly amount", 12),
        "advanced_canada_workers_benefit": ("ACWB annual amount", 1),
    }
    values: dict[str, float] = {}
    for surface, concept in targets.items():
        label_and_factor = labels.get(str(surface))
        if label_and_factor is None:
            continue
        label, factor = label_and_factor
        # CRA omits benefit rows whose calculated amount is zero. A configured
        # output therefore maps an absent row to zero, while unknown labels are
        # still ignored above rather than guessed.
        values[str(concept)] = round(amounts.get(label, 0) * factor, 2)
    return values


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _form_text(value: Any) -> str:
    return _bool_text(value) if isinstance(value, bool) else str(value)


def _has_form(document: str, form_id: str) -> bool:
    return f'id="{form_id}"' in document
