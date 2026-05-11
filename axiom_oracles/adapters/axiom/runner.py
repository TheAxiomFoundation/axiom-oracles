from __future__ import annotations

from ...core.engine import EngineAdapter
from ...core.household import Household
from ...core.results import EngineResult


class AxiomRulesRunner(EngineAdapter):
    """Adapter shell for Axiom RuleSpec programs."""

    name = "axiom"

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del households, variables
        raise NotImplementedError("Wire axiom-rules-engine execution here.")
