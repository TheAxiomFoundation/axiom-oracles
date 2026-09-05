from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isclose, isfinite

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
            return 0
        return self.match_count / len(self.comparisons) * 100

    def mismatches(self) -> list[VariableComparison]:
        return [item for item in self.comparisons if not item.matches]


class Comparator:
    def __init__(self, mappings: list[ProgramMapping]):
        require_unique_ids([mapping.concept_id for mapping in mappings], "mapping concepts")
        self.mappings = mappings

    def compare(
        self,
        left_results: list[EngineResult],
        right_results: list[EngineResult],
        *,
        outputs_by_case: Mapping[int | str, Sequence[str]] | None = None,
    ) -> list[HouseholdComparison]:
        """Compare selected mappings, optionally scoped to each case's outputs."""
        left_ids = [result.household_id for result in left_results]
        right_ids = [result.household_id for result in right_results]
        require_unique_ids(left_ids, "left result household IDs")
        require_unique_ids(right_ids, "right result household IDs")
        require_same_ids(left_ids, right_ids, "right result household IDs")
        if outputs_by_case is not None:
            require_same_ids(list(outputs_by_case), left_ids, "result household IDs")
        right_by_id = {result.household_id: result for result in right_results}
        comparisons: list[HouseholdComparison] = []

        for left in left_results:
            right = right_by_id[left.household_id]

            mappings = [
                mapping
                for mapping in self.mappings
                if self._has_engine_target(mapping, left.engine)
                and self._has_engine_target(mapping, right.engine)
            ]
            if outputs_by_case is not None:
                requested = outputs_by_case[left.household_id]
                require_unique_ids(requested, "requested output concepts")
                unsupported = set(requested) - {
                    mapping.concept_id for mapping in mappings
                }
                if unsupported:
                    raise ValueError(
                        f"Unmapped requested outputs for case {left.household_id!r}: "
                        f"{sorted(unsupported)!r}"
                    )
                mappings = [
                    mapping
                    for mapping in mappings
                    if mapping.concept_id in requested
                ]
            variable_comparisons = [
                self.compare_mapping(mapping, left, right) for mapping in mappings
            ]
            if not variable_comparisons:
                raise ValueError(
                    f"No comparable mappings for household {left.household_id!r} "
                    f"between {left.engine!r} and {right.engine!r}"
                )
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

        for result, value in ((left, left_value), (right, right_value)):
            if value is not None and (
                mapping.comparison == "amount" or isinstance(value, (float, int))
            ):
                if not isfinite(self._to_number(value)):
                    raise ValueError(
                        f"Non-finite {mapping.concept_id!r} value from "
                        f"{result.engine!r} for household {result.household_id!r}"
                    )

        if mapping.comparison == "amount":
            if left_value is None or right_value is None:
                difference = None
                matches = False
            else:
                left_number = self._to_number(left_value)
                right_number = self._to_number(right_value)
                difference = left_number - right_number
                if not isfinite(difference):
                    raise ValueError(
                        f"Non-finite difference for {mapping.concept_id!r} "
                        f"in household {left.household_id!r}"
                    )
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

    def _mapped_value(self, mapping: ProgramMapping, result: EngineResult) -> Value:
        key = self._mapping_key(mapping, result.engine)
        if isinstance(key, list):
            numbers: list[float | None] = []
            for item in key:
                value = result.get(item)
                if value is None:
                    numbers.append(None)
                    continue
                number = self._to_number(value)
                if not isfinite(number):
                    raise ValueError(
                        f"Non-finite component {item!r} from {result.engine!r} "
                        f"for household {result.household_id!r}"
                    )
                numbers.append(number)
            if not key or any(number is None for number in numbers):
                return None
            return sum(number for number in numbers if number is not None)
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


def require_unique_ids(ids: Sequence[int | str], label: str) -> None:
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates[:10]!r}")


def require_same_ids(
    expected: Sequence[int | str], actual: Sequence[int | str], label: str
) -> None:
    expected_set, actual_set = set(expected), set(actual)
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    if missing or extra:
        raise ValueError(
            f"Invalid {label}: missing {sorted(missing, key=repr)[:10]!r}; "
            f"unexpected {sorted(extra, key=repr)[:10]!r}"
        )
