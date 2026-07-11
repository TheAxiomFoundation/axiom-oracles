from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from ...comparison.mappings import engine_targets_for_concepts
from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult
from .input_mapper import AccessNycInputMapper


class AccessNycPythonRunner(EngineAdapter):
    """Run NYCOpportunity/benefits-screening-api locally."""

    name = "accessnyc"

    def __init__(
        self,
        repo_path: str | Path | None = None,
        interested_programs: list[str] | None = None,
    ):
        self.repo_path = _resolve_repo_path(repo_path)
        self.interested_programs = interested_programs
        self.mapper = AccessNycInputMapper()

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        return [self.run_case(case, variables) for case in cases]

    def run_case(
        self,
        case: Case,
        variables: list[str] | None = None,
    ) -> EngineResult:
        programs = self._interested_programs(case, variables)
        return self._result_from_payload(
            case.case_id,
            self.mapper.map_case(case),
            interested_programs=programs,
        )

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del variables
        return [self.run_household(household) for household in households]

    def run_household(self, household: Household) -> EngineResult:
        return self._result_from_payload(
            household.household_id,
            self.mapper.map_household(household),
            interested_programs=self.interested_programs,
        )

    def available_program_codes(self) -> set[str]:
        if self.repo_path:
            rules_dir = self.repo_path / "src" / "rules" / "program_rules"
            return {path.stem for path in rules_dir.glob("S2R*.py") if path.is_file()}

        self._ensure_import_path()
        try:
            from src.rules.registry import get_rule_codes
        except ImportError as exc:
            raise RuntimeError(_LOCAL_PYTHON_UNAVAILABLE) from exc
        return set(get_rule_codes())

    def _result_from_payload(
        self,
        household_id: int | str,
        payload: dict[str, Any],
        interested_programs: list[str] | None = None,
    ) -> EngineResult:
        self._ensure_import_path()
        try:
            from src.models.schemas import AggregateEligibilityRequest
            from src.rules.calculate_eligibility import calculate_eligibility
            from src.validation.validate_request import validate_request
        except ImportError as exc:
            raise RuntimeError(_LOCAL_PYTHON_UNAVAILABLE) from exc

        is_valid, eligibility_request, errors = validate_request(payload)
        if not is_valid:
            return EngineResult(
                engine=self.name,
                household_id=household_id,
                values={},
                raw=payload,
                errors=tuple(str(error) for error in errors),
            )

        aggregate = AggregateEligibilityRequest.from_eligibility_request(
            eligibility_request
        )
        eligible_programs = calculate_eligibility(aggregate)
        if interested_programs:
            eligible_programs = [
                code for code in eligible_programs if code in interested_programs
            ]

        return EngineResult(
            engine=self.name,
            household_id=household_id,
            values={code: True for code in eligible_programs},
            raw={"eligible_programs": eligible_programs},
        )

    def _interested_programs(
        self,
        case: Case,
        variables: list[str] | None,
    ) -> list[str] | None:
        output_concepts = variables or list(case.outputs)
        if not output_concepts:
            return self.interested_programs
        return engine_targets_for_concepts(output_concepts, self.name)

    def _ensure_import_path(self) -> None:
        if self.repo_path:
            repo = str(self.repo_path)
            if repo not in sys.path:
                sys.path.insert(0, repo)


def _resolve_repo_path(repo_path: str | Path | None) -> Path | None:
    value = repo_path or os.environ.get("ACCESSNYC_PYTHON_PATH")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if not (path / "src" / "rules" / "program_rules").exists():
        raise RuntimeError(
            f"ACCESS NYC Python repo path does not look like "
            f"NYCOpportunity/benefits-screening-api: {path}"
        )
    return path


_LOCAL_PYTHON_UNAVAILABLE = (
    "Local ACCESS NYC Python execution requires the public "
    "NYCOpportunity/benefits-screening-api repo on ACCESSNYC_PYTHON_PATH or "
    "--accessnyc-python-path, plus its Python dependencies."
)
