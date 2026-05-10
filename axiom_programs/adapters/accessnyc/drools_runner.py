from __future__ import annotations

from pathlib import Path

from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult


class AccessNycDroolsRunner(EngineAdapter):
    """Placeholder for running ACCESS NYC Drools without the hosted API."""

    name = "accessnyc"

    def __init__(self, rules_dir: str | Path | None = None):
        self.rules_dir = Path(rules_dir) if rules_dir else None

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del cases, variables
        raise RuntimeError(_LOCAL_DROOLS_UNAVAILABLE)

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise RuntimeError(_LOCAL_DROOLS_UNAVAILABLE)


_LOCAL_DROOLS_UNAVAILABLE = (
    "Local ACCESS NYC Drools execution is not available from the public "
    "ACCESS-NYC-Rules repo alone. The repo contains .drl files, but not the "
    "compiled Java request/response/fact model classes or a runnable Screening "
    "API/KJAR. Use --accessnyc-mode api, or supply NYC's local API/KJAR/model "
    "artifact and add a runner for it."
)
