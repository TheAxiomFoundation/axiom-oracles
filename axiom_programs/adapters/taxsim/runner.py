from __future__ import annotations

from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult


class TaxsimPackageRunner(EngineAdapter):
    """Adapter shell for PolicyEngine/policyengine-taxsim."""

    name = "taxsim"

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise NotImplementedError(
            "Wrap PolicyEngine/policyengine-taxsim runners here."
        )
