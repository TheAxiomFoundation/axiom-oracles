from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose

from .mappings import ProgramMapping
from ..core.results import EngineResult, Value


@dataclass(frozen=True)
class VariableComparison:
    variable: str
    left_value: Value
    right_value: Value
    matches: bool
    difference: float | None = None
    tolerance: float = 0
    relative_tolerance: float = 0
    description: str = ""


@dataclass(frozen=True)
class HouseholdComparison:
    household_id: int | str
    left_engine: str
    right_engine: str
    comparisons: list[VariableComparison] = field(default_factory=list)
    left_errors: tuple[str, ...] = field(default_factory=tuple)
    right_errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def match_count(self) -> int:
        return sum(item.matches for item in self.comparisons)

    @property
    def mismatch_count(self) -> int:
        return len(self.comparisons) - self.match_count

    @property
    def match_rate(self) -> float:
        if not self.comparisons:
            return 100
        return self.match_count / len(self.comparisons) * 100

    def mismatches(self) -> list[VariableComparison]:
        return [item for item in self.comparisons if not item.matches]


class Comparator:
    def __init__(self, mappings: list[ProgramMapping]):
        self.mappings = mappings

    def compare(
        self,
        left_results: list[EngineResult],
        right_results: list[EngineResult],
    ) -> list[HouseholdComparison]:
        right_by_id = {result.household_id: result for result in right_results}
        comparisons: list[HouseholdComparison] = []

        for left in left_results:
            right = right_by_id.get(left.household_id)
            if right is None:
                continue

            variable_comparisons = [
                self.compare_mapping(mapping, left, right)
                for mapping in self.mappings
                if self._has_engine_target(mapping, left.engine)
                and self._has_engine_target(mapping, right.engine)
                and (
                    self._has_mapping_value(mapping, left)
                    or self._has_mapping_value(mapping, right)
                )
            ]
            comparisons.append(
                HouseholdComparison(
                    household_id=left.household_id,
                    left_engine=left.engine,
                    right_engine=right.engine,
                    comparisons=variable_comparisons,
                    left_errors=left.errors,
                    right_errors=right.errors,
                )
            )

        return comparisons

    def compare_mapping(
        self,
        mapping: ProgramMapping,
        left: EngineResult,
        right: EngineResult,
    ) -> VariableComparison:
        left_value = self._mapped_value(mapping, left)
        right_value = self._mapped_value(mapping, right)

        if mapping.comparison == "amount":
            if left_value is None or right_value is None:
                difference = None
                matches = False
            else:
                left_number = self._to_number(left_value)
                right_number = self._to_number(right_value)
                difference = left_number - right_number
                matches = isclose(
                    left_number,
                    right_number,
                    rel_tol=mapping.relative_tolerance,
                    abs_tol=mapping.tolerance,
                )
        else:
            difference = None
            matches = (
                False
                if left_value is None or right_value is None
                else bool(left_value) == bool(right_value)
            )

        return VariableComparison(
            variable=mapping.standard,
            left_value=left_value,
            right_value=right_value,
            matches=matches,
            difference=difference,
            tolerance=mapping.tolerance,
            relative_tolerance=mapping.relative_tolerance,
            description=mapping.description,
        )

    def _has_mapping_value(self, mapping: ProgramMapping, result: EngineResult) -> bool:
        key = self._mapping_key(mapping, result.engine)
        if key is None:
            return False
        if isinstance(key, list):
            return any(item in result.values for item in key)
        return key in result.values

    def _mapped_value(self, mapping: ProgramMapping, result: EngineResult) -> Value:
        key = self._mapping_key(mapping, result.engine)
        if isinstance(key, list):
            if not any(item in result.values for item in key):
                return None
            return sum(self._to_number(result.get(item, 0)) for item in key)
        if key is None:
            return None
        return result.get(key)

    @staticmethod
    def _mapping_key(mapping: ProgramMapping, engine: str) -> str | list[str] | None:
        return mapping.target_for_engine(engine)

    @staticmethod
    def _has_engine_target(mapping: ProgramMapping, engine: str) -> bool:
        return bool(mapping.target_for_engine(engine))

    @staticmethod
    def _to_number(value: Value) -> float:
        if value is None:
            return 0
        if isinstance(value, bool):
            return float(value)
        return float(value)
