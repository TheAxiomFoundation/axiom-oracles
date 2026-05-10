from __future__ import annotations

import os
from typing import Any

from ...core.engine import EngineAdapter
from ...core.case import Case
from ...core.household import Household
from ...core.results import EngineResult
from ...comparison.mappings import engine_targets_for_concepts
from .input_mapper import AccessNycInputMapper


class AccessNycApiRunner(EngineAdapter):
    name = "accessnyc"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        interested_programs: list[str] | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("ACCESSNYC_API_BASE_URL")
            or "https://sandbox.screeningapi.cityofnewyork.us"
        ).rstrip("/")
        self.token = token or os.environ.get("ACCESSNYC_TOKEN")
        self.username = username or os.environ.get("ACCESSNYC_USERNAME")
        self.password = password or os.environ.get("ACCESSNYC_PASSWORD")
        self.interested_programs = interested_programs
        self.mapper = AccessNycInputMapper()

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del variables
        return [self.run_household(household) for household in households]

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        return [
            self._result_from_response(
                case.case_id,
                self._post_eligibility(
                    [self.mapper.map_case(case)],
                    interested_programs=self._interested_programs(case, variables),
                ),
            )
            for case in cases
        ]

    def run_household(self, household: Household) -> EngineResult:
        response = self._post_eligibility([self.mapper.map_household(household)])
        return self._result_from_response(household.household_id, response)

    def _result_from_response(
        self,
        household_id: int | str,
        response: dict[str, Any],
    ) -> EngineResult:
        eligible_programs = response.get("eligiblePrograms", [])
        values = {
            program["code"]: True
            for program in eligible_programs
            if isinstance(program, dict) and "code" in program
        }
        return EngineResult(
            engine=self.name,
            household_id=household_id,
            values=values,
            raw=response,
        )

    def _post_eligibility(
        self,
        payload: list[dict],
        interested_programs: list[str] | None = None,
    ) -> dict[str, Any]:
        import requests

        params = {}
        programs = interested_programs or self.interested_programs
        if programs:
            params["interestedPrograms"] = "|".join(programs)

        response = requests.post(
            f"{self.base_url}/eligibilityPrograms",
            json=payload,
            params=params,
            headers={"Authorization": self._authorization_header()},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("type") == "FAILURE":
            raise RuntimeError(data)
        return data

    def _interested_programs(
        self,
        case: Case,
        variables: list[str] | None,
    ) -> list[str] | None:
        output_concepts = variables or list(case.outputs)
        if not output_concepts:
            return self.interested_programs
        return engine_targets_for_concepts(output_concepts, self.name)

    def _authorization_header(self) -> str:
        if self.token:
            return self.token
        self.token = self._fetch_token()
        return self.token

    def _fetch_token(self) -> str:
        import requests

        if not self.username or not self.password:
            raise RuntimeError(
                "Set ACCESSNYC_TOKEN or ACCESSNYC_USERNAME/ACCESSNYC_PASSWORD"
            )

        response = requests.post(
            f"{self.base_url}/authToken",
            json={"username": self.username, "password": self.password},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not token:
            raise RuntimeError(f"ACCESS NYC auth did not return a token: {data}")
        return token
