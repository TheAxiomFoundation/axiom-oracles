from __future__ import annotations

from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult


class PrdPackageRunner(EngineAdapter):
    """Adapter shell for PolicyEngine/prd-comparison."""

    name = "prd"

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise NotImplementedError("Wrap PolicyEngine/prd-comparison runners here.")
