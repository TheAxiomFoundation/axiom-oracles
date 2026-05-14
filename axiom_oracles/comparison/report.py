from __future__ import annotations

from collections import Counter, defaultdict

from .comparator import HouseholdComparison, VariableComparison
from .mappings import ProgramMapping
from ..core.case import Case
from ..core.geography import GeographyScope
from ..core.results import Value


COMPARISON_REPORT_SCHEMA_VERSION = "axiom.comparison_report.v2"


class MismatchKind:
    """Stable mismatch taxonomy for cross-oracle reports."""

    AMOUNT_DIFFERENCE = "amount_difference"
    ELIGIBILITY_LEFT_ONLY = "eligibility_left_only"
    ELIGIBILITY_RIGHT_ONLY = "eligibility_right_only"
    MISSING_LEFT = "missing_left"
    MISSING_RIGHT = "missing_right"
    MISSING_BOTH = "missing_both"
    VALUE_MISMATCH = "value_mismatch"


def build_comparison_report(
    *,
    suite_name: str,
    population: str,
    locales: set[str],
    scope: GeographyScope | None,
    cases: list[Case],
    mappings: list[ProgramMapping],
    comparisons: list[HouseholdComparison],
) -> dict:
    """Build the stable JSON report shared by CLI, apps, and oracle wrappers."""

    cases_by_id = {case.case_id: case for case in cases}
    mappings_by_id = {mapping.concept_id: mapping for mapping in mappings}
    mismatch_rows = _mismatch_rows(comparisons, cases_by_id, mappings_by_id)
    error_rows = _error_rows(comparisons)
    aggregate_rows = _aggregate_rows(comparisons, cases_by_id, mappings)
    left_engine, right_engine = _engine_pair(comparisons)
    return {
        "schema_version": COMPARISON_REPORT_SCHEMA_VERSION,
        "suite": suite_name,
        "population": population,
        "engines": {"left": left_engine, "right": right_engine},
        "locales": sorted(locales),
        "scope": scope.as_dict() if scope is not None else None,
        "concepts": [
            {
                "id": mapping.concept_id,
                "description": mapping.description,
                "category": mapping.category,
                "comparison": mapping.comparison,
                "tolerance": mapping.tolerance,
                "relative_tolerance": mapping.relative_tolerance,
                "priority": mapping.priority,
                "components": list(mapping.components),
                "parent": mapping.parent,
            }
            for mapping in mappings
        ],
        "case_count": len(comparisons),
        "summary": {
            "match_count": sum(item.match_count for item in comparisons),
            "mismatch_count": sum(item.mismatch_count for item in comparisons),
            "comparison_count": sum(len(item.comparisons) for item in comparisons),
            "weighted": _weighted_summary(comparisons, cases_by_id),
            "mismatches_by_concept": _count_rows(mismatch_rows, "concept"),
            "mismatches_by_kind": _count_rows(mismatch_rows, "kind"),
            "mismatches_by_scenario": _count_rows(mismatch_rows, "scenario"),
            "error_count": len(error_rows),
            "errors_by_engine": _count_rows(error_rows, "engine"),
        },
        "aggregates": aggregate_rows,
        "mismatches": mismatch_rows,
        "errors": error_rows,
        "cases": [
            {
                "case_id": item.household_id,
                "left_engine": item.left_engine,
                "right_engine": item.right_engine,
                "left_errors": list(item.left_errors),
                "right_errors": list(item.right_errors),
                "metadata": _case_report_metadata(cases_by_id.get(item.household_id)),
                "match_rate": item.match_rate,
                "mismatches": [
                    _case_mismatch_row(mismatch, mappings_by_id)
                    for mismatch in item.mismatches()
                ],
            }
            for item in comparisons
        ],
    }


def classify_mismatch(
    comparison: VariableComparison,
    mapping: ProgramMapping | None = None,
) -> str:
    if comparison.left_value is None and comparison.right_value is None:
        return MismatchKind.MISSING_BOTH
    if comparison.left_value is None:
        return MismatchKind.MISSING_LEFT
    if comparison.right_value is None:
        return MismatchKind.MISSING_RIGHT

    comparison_type = mapping.comparison if mapping is not None else ""
    if comparison_type == "amount":
        return MismatchKind.AMOUNT_DIFFERENCE
    if comparison_type != "eligibility":
        return MismatchKind.VALUE_MISMATCH

    left_truthy = bool(comparison.left_value)
    right_truthy = bool(comparison.right_value)
    if left_truthy and not right_truthy:
        return MismatchKind.ELIGIBILITY_LEFT_ONLY
    if right_truthy and not left_truthy:
        return MismatchKind.ELIGIBILITY_RIGHT_ONLY
    return MismatchKind.VALUE_MISMATCH


def _engine_pair(
    comparisons: list[HouseholdComparison],
) -> tuple[str | None, str | None]:
    if not comparisons:
        return None, None
    first = comparisons[0]
    return first.left_engine, first.right_engine


def _mismatch_rows(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
    mappings_by_id: dict[str, ProgramMapping],
) -> list[dict]:
    rows = []
    for item in comparisons:
        case = cases_by_id.get(item.household_id)
        metadata = dict(case.metadata) if case is not None else {}
        for mismatch in item.mismatches():
            mapping = mappings_by_id.get(mismatch.variable)
            rows.append(
                {
                    "case_id": item.household_id,
                    "scenario": metadata.get("scenario"),
                    "yearly_earned_income": metadata.get("yearly_earned_income"),
                    "ages": metadata.get("ages"),
                    "pregnant_head": metadata.get("pregnant_head"),
                    "concept": mismatch.variable,
                    "description": mismatch.description,
                    "kind": classify_mismatch(mismatch, mapping),
                    "left": mismatch.left_value,
                    "right": mismatch.right_value,
                    "difference": mismatch.difference,
                    "tolerance": mismatch.tolerance,
                    "relative_tolerance": mismatch.relative_tolerance,
                    "parent": mapping.parent if mapping is not None else None,
                }
            )
    return rows


def _error_rows(comparisons: list[HouseholdComparison]) -> list[dict]:
    rows = []
    for item in comparisons:
        for error in item.left_errors:
            rows.append(
                {
                    "case_id": item.household_id,
                    "side": "left",
                    "engine": item.left_engine,
                    "error": error,
                }
            )
        for error in item.right_errors:
            rows.append(
                {
                    "case_id": item.household_id,
                    "side": "right",
                    "engine": item.right_engine,
                    "error": error,
                }
            )
    return rows


def _case_mismatch_row(
    mismatch: VariableComparison,
    mappings_by_id: dict[str, ProgramMapping],
) -> dict:
    mapping = mappings_by_id.get(mismatch.variable)
    return {
        "concept": mismatch.variable,
        "description": mismatch.description,
        "kind": classify_mismatch(mismatch, mapping),
        "left": mismatch.left_value,
        "right": mismatch.right_value,
        "difference": mismatch.difference,
        "tolerance": mismatch.tolerance,
        "relative_tolerance": mismatch.relative_tolerance,
        "parent": mapping.parent if mapping is not None else None,
    }


def _case_report_metadata(case: Case | None) -> dict:
    if case is None:
        return {}
    metadata = dict(case.metadata)
    compact = {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "axiom_input_records",
            "axiom_input_record_overlays",
            "axiom_relations",
        }
    }
    for key in (
        "axiom_input_records",
        "axiom_input_record_overlays",
        "axiom_relations",
    ):
        value = metadata.get(key)
        if isinstance(value, list | tuple):
            compact[f"{key}_count"] = len(value)
    return compact


def _aggregate_rows(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
    mappings: list[ProgramMapping],
) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(_aggregate_bucket)
    for item in comparisons:
        weight = _case_weight(cases_by_id.get(item.household_id))
        for comparison in item.comparisons:
            bucket = buckets[comparison.variable]
            bucket["comparison_count"] += 1
            bucket["comparison_weight"] += weight
            if comparison.matches:
                bucket["match_count"] += 1
                bucket["match_weight"] += weight
            else:
                bucket["mismatch_count"] += 1
                bucket["mismatch_weight"] += weight

            if comparison.left_value is None:
                bucket["missing_left_count"] += 1
            else:
                bucket["left_positive_weight"] += (
                    weight if bool(comparison.left_value) else 0
                )
                bucket["left_weighted_sum"] += (
                    _to_number(comparison.left_value) * weight
                )
            if comparison.right_value is None:
                bucket["missing_right_count"] += 1
            else:
                bucket["right_positive_weight"] += (
                    weight if bool(comparison.right_value) else 0
                )
                bucket["right_weighted_sum"] += (
                    _to_number(comparison.right_value) * weight
                )
            if comparison.left_value is None and comparison.right_value is None:
                bucket["missing_both_count"] += 1

    rows = []
    for mapping in mappings:
        bucket = buckets.get(mapping.concept_id)
        if bucket is None or not bucket["comparison_count"]:
            continue
        row = {
            "concept": mapping.concept_id,
            "description": mapping.description,
            "category": mapping.category,
            "comparison": mapping.comparison,
            "parent": mapping.parent,
            "components": list(mapping.components),
            "comparison_count": bucket["comparison_count"],
            "mismatch_count": bucket["mismatch_count"],
            "missing_left_count": bucket["missing_left_count"],
            "missing_right_count": bucket["missing_right_count"],
            "missing_both_count": bucket["missing_both_count"],
            "match_rate": _percentage(
                bucket["match_count"],
                bucket["comparison_count"],
            ),
            "comparison_weight": _clean_float(bucket["comparison_weight"]),
            "match_weight": _clean_float(bucket["match_weight"]),
            "mismatch_weight": _clean_float(bucket["mismatch_weight"]),
            "weighted_match_rate": _percentage(
                bucket["match_weight"],
                bucket["comparison_weight"],
            ),
        }
        if mapping.comparison == "amount":
            row.update(
                {
                    "left_weighted_sum": _clean_float(bucket["left_weighted_sum"]),
                    "right_weighted_sum": _clean_float(bucket["right_weighted_sum"]),
                    "weighted_difference": _clean_float(
                        bucket["left_weighted_sum"]
                        - bucket["right_weighted_sum"]
                    ),
                }
            )
        else:
            row.update(
                {
                    "left_positive_weight": _clean_float(
                        bucket["left_positive_weight"]
                    ),
                    "right_positive_weight": _clean_float(
                        bucket["right_positive_weight"]
                    ),
                    "left_positive_rate": _percentage(
                        bucket["left_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                    "right_positive_rate": _percentage(
                        bucket["right_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                    "positive_rate_difference": _percentage(
                        bucket["left_positive_weight"]
                        - bucket["right_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                }
            )
        rows.append(row)
    return rows


def _aggregate_bucket() -> dict[str, float | int]:
    return {
        "comparison_count": 0,
        "match_count": 0,
        "mismatch_count": 0,
        "comparison_weight": 0.0,
        "match_weight": 0.0,
        "mismatch_weight": 0.0,
        "left_positive_weight": 0.0,
        "right_positive_weight": 0.0,
        "left_weighted_sum": 0.0,
        "right_weighted_sum": 0.0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "missing_both_count": 0,
    }


def _weighted_summary(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
) -> dict[str, float]:
    comparison_weight = 0.0
    match_weight = 0.0
    mismatch_weight = 0.0
    for item in comparisons:
        weight = _case_weight(cases_by_id.get(item.household_id))
        for comparison in item.comparisons:
            comparison_weight += weight
            if comparison.matches:
                match_weight += weight
            else:
                mismatch_weight += weight
    return {
        "comparison_weight": _clean_float(comparison_weight),
        "match_weight": _clean_float(match_weight),
        "mismatch_weight": _clean_float(mismatch_weight),
        "match_rate": _percentage(match_weight, comparison_weight),
    }


def _case_weight(case: Case | None) -> float:
    if case is None:
        return 1.0
    value = case.metadata.get("household_weight", 1)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _count_rows(rows: list[dict], key: str) -> list[dict]:
    counts = Counter(row.get(key) for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0] or ""),
        )
    ]


def _to_number(value: Value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    return float(value)


def _percentage(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0
    return _clean_float(numerator / denominator * 100)


def _clean_float(value: float) -> float:
    rounded = round(float(value), 6)
    if rounded.is_integer():
        return int(rounded)
    return rounded
