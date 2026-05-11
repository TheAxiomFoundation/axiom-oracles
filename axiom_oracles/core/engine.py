from __future__ import annotations

from abc import ABC

from .case import Case
from .household import Household
from .results import EngineResult


class EngineAdapter(ABC):
    """Base interface for every external oracle or executable policy engine."""

    name: str

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        """Run the engine for concept-keyed cases."""
        del cases, variables
        raise NotImplementedError

    def run_households(
        self,
        households: list[Household],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        """Run the engine for legacy/convenience household objects."""
        del households, variables
        raise NotImplementedError
