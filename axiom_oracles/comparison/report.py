from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from .comparator import HouseholdComparison, VariableComparison
from .mappings import ProgramMapping
from ..core.case import Case, Concepts
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


# Below this case count a suite is small enough to carry full evidence —
# every household's raw input records and both engines' values for MATCHED
# variables too, so a disagreement (or agreement) can be reproduced from the
# report alone. Large suites keep the compact household_summary only.
FULL_CASE_INPUT_LIMIT = 5_000


def build_comparison_report(
    *,
    suite_name: str,
    population: str,
    locales: set[str],
    scope: GeographyScope | None,
    cases: list[Case],
    mappings: list[ProgramMapping],
    comparisons: list[HouseholdComparison],
    include_inputs: bool | None = None,
) -> dict:
    """Build the stable JSON report shared by CLI, apps, and oracle wrappers.

    ``include_inputs=None`` (the default) resolves by suite size: suites at or
    under ``FULL_CASE_INPUT_LIMIT`` cases persist full per-case evidence.
    """

    if include_inputs is None:
        include_inputs = len(comparisons) <= FULL_CASE_INPUT_LIMIT
    accumulator = ComparisonReportAccumulator(
        suite_name=suite_name,
        population=population,
        locales=locales,
        scope=scope,
        mappings=mappings,
        include_inputs=include_inputs,
    )
    accumulator.add_batch(cases, comparisons)
    return accumulator.to_dict()


class ComparisonReportAccumulator:
    """Accumulate comparison reports across batches.

    When `case_rows_path` is supplied, per-case rows are written as JSONL and can
    later be streamed into the final JSON report without keeping every successful
    case row in memory.
    """

    def __init__(
        self,
        *,
        suite_name: str,
        population: str,
        locales: set[str],
        scope: GeographyScope | None,
        mappings: list[ProgramMapping],
        case_rows_path: Path | None = None,
        include_inputs: bool = False,
    ) -> None:
        self.include_inputs = include_inputs
        self.suite_name = suite_name
        self.population = population
        self.locales = set(locales)
        self.scope = scope
        self.mappings = list(mappings)
        self._mappings_by_id = {
            mapping.concept_id: mapping for mapping in self.mappings
        }
        self._case_rows_path = case_rows_path
        self._case_rows: list[dict] = []
        if self._case_rows_path is not None:
            self._case_rows_path.parent.mkdir(parents=True, exist_ok=True)
            self._case_rows_path.write_text("")

        self._case_count = 0
        self._match_count = 0
        self._mismatch_count = 0
        self._comparison_count = 0
        self._comparison_weight = 0.0
        self._match_weight = 0.0
        self._mismatch_weight = 0.0
        self._aggregate_buckets: dict[str, dict] = defaultdict(_aggregate_bucket)
        self._mismatch_rows: list[dict] = []
        self._error_rows: list[dict] = []
        self._left_engine: str | None = None
        self._right_engine: str | None = None

    @property
    def case_count(self) -> int:
        return self._case_count

    def add_batch(
        self,
        cases: list[Case],
        comparisons: list[HouseholdComparison],
    ) -> None:
        cases_by_id = {case.case_id: case for case in cases}
        if self._left_engine is None and comparisons:
            self._left_engine, self._right_engine = _engine_pair(comparisons)

        self._case_count += len(comparisons)
        self._match_count += sum(item.match_count for item in comparisons)
        self._mismatch_count += sum(item.mismatch_count for item in comparisons)

        for item in comparisons:
            weight = _case_weight(cases_by_id.get(item.household_id))
            for comparison in item.comparisons:
                self._comparison_count += 1
                self._comparison_weight += weight
                if comparison.matches:
                    self._match_weight += weight
                else:
                    self._mismatch_weight += weight
                _update_aggregate_bucket(
                    self._aggregate_buckets[comparison.variable],
                    comparison,
                    weight,
                )

        self._mismatch_rows.extend(
            _mismatch_rows(comparisons, cases_by_id, self._mappings_by_id)
        )
        self._error_rows.extend(_error_rows(comparisons))
        self._append_case_rows(
            _case_rows(
                comparisons,
                cases_by_id,
                self._mappings_by_id,
                include_inputs=self.include_inputs,
            )
        )

    def to_dict(self, *, include_cases: bool = True) -> dict:
        return {
            "schema_version": COMPARISON_REPORT_SCHEMA_VERSION,
            "suite": self.suite_name,
            "population": self.population,
            "engines": {"left": self._left_engine, "right": self._right_engine},
            "locales": sorted(self.locales),
            "scope": self.scope.as_dict() if self.scope is not None else None,
            "concepts": _concept_rows(self.mappings),
            "case_count": self._case_count,
            "summary": {
                "match_count": self._match_count,
                "mismatch_count": self._mismatch_count,
                "comparison_count": self._comparison_count,
                "weighted": _weighted_summary_from_totals(
                    self._comparison_weight,
                    self._match_weight,
                    self._mismatch_weight,
                ),
                "mismatches_by_concept": _count_rows(
                    self._mismatch_rows,
                    "concept",
                ),
                "mismatches_by_kind": _count_rows(self._mismatch_rows, "kind"),
                "mismatches_by_scenario": _count_rows(
                    self._mismatch_rows,
                    "scenario",
                ),
                "error_count": len(self._error_rows),
                "errors_by_engine": _count_object(self._error_rows, "engine"),
            },
            "aggregates": _aggregate_rows_from_buckets(
                self._aggregate_buckets,
                self.mappings,
            ),
            "mismatches": list(self._mismatch_rows),
            "errors": list(self._error_rows),
            "cases": self._stored_case_rows() if include_cases else [],
        }

    def write_json(self, path: Path) -> None:
        """Write the final report JSON, streaming per-case rows when possible."""

        report = self.to_dict(include_cases=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as handle:
            handle.write("{\n")
            for key in sorted(key for key in report if key != "cases"):
                handle.write(_top_level_json_entry(key, report[key]))
                handle.write(",\n")
            handle.write(f'  {json.dumps("cases")}: [')
            wrote_case = False
            for row in self._iter_case_rows():
                handle.write(",\n" if wrote_case else "\n")
                handle.write(_indented_json(row, 4))
                wrote_case = True
            if wrote_case:
                handle.write("\n")
            handle.write("  ]\n}\n")

    def _append_case_rows(self, rows: list[dict]) -> None:
        if self._case_rows_path is None:
            self._case_rows.extend(rows)
            return
        with self._case_rows_path.open("a") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _stored_case_rows(self) -> list[dict]:
        return list(self._iter_case_rows())

    def _iter_case_rows(self):
        if self._case_rows_path is None:
            yield from self._case_rows
            return
        if not self._case_rows_path.exists():
            return
        with self._case_rows_path.open() as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


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


def _case_rows(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
    mappings_by_id: dict[str, ProgramMapping],
    *,
    include_inputs: bool = False,
) -> list[dict]:
    rows = []
    for item in comparisons:
        row = {
            "case_id": item.household_id,
            "left_engine": item.left_engine,
            "right_engine": item.right_engine,
            "left_errors": list(item.left_errors),
            "right_errors": list(item.right_errors),
            "metadata": _case_report_metadata(
                cases_by_id.get(item.household_id),
                include_inputs=include_inputs,
            ),
            "match_rate": item.match_rate,
            "mismatches": [
                _case_mismatch_row(mismatch, mappings_by_id)
                for mismatch in item.mismatches()
            ],
        }
        if include_inputs:
            # Matched values are evidence too: with them, the report alone
            # reproduces every compared value, not just the disagreements.
            row["matches"] = [
                {
                    "concept": comparison.variable,
                    "left": comparison.left_value,
                    "right": comparison.right_value,
                }
                for comparison in item.comparisons
                if comparison.matches
            ]
        rows.append(row)
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


def _case_report_metadata(
    case: Case | None,
    *,
    include_inputs: bool = False,
) -> dict:
    if case is None:
        return {}
    metadata = dict(case.metadata)
    stripped = {
        "axiom_input_records",
        "axiom_input_record_overlays",
        "axiom_relations",
        "axiom_all_outputs",
    }
    compact = {
        key: value
        for key, value in metadata.items()
        if include_inputs or key not in stripped
    }
    for key in stripped:
        value = metadata.get(key)
        if isinstance(value, (list, tuple, dict)):
            compact[f"{key}_count"] = len(value)
    summary = _household_summary(case)
    if summary:
        compact["household_summary"] = summary
    return compact


def _household_summary(case: Case) -> dict:
    """Extract a compact human-readable household snapshot from a Case.

    The comparison report stores one row per household. Reviewers triaging
    a specific mismatch want to see *who* the household actually is —
    member ages, total earned income, count — without re-running the
    projector. Pulls from the case's Person entities since ECPS-loaded
    cases keep per-person facts under entities[Person].facts."""

    ages: list[int] = []
    incomes: list[float] = []
    pregnant = False
    for entity in case.entities:
        if (entity.kind or "").lower() != "person":
            continue
        facts = entity.facts or {}
        age = facts.get(Concepts.PERSON_AGE)
        if isinstance(age, (int, float)):
            ages.append(int(age))
        income = facts.get(Concepts.YEARLY_EARNED_INCOME)
        if isinstance(income, (int, float)):
            incomes.append(float(income))
        if facts.get(Concepts.PREGNANT) is True:
            pregnant = True

    if not ages and not incomes:
        return {}

    summary: dict[str, Any] = {}
    if ages:
        summary["household_size"] = len(ages)
        summary["ages"] = ages
    if incomes:
        summary["yearly_earned_income_total"] = round(sum(incomes), 2)
        summary["yearly_earned_income_per_person"] = [round(v, 2) for v in incomes]
    if pregnant:
        summary["pregnant_member_present"] = True
    return summary


def _concept_rows(mappings: list[ProgramMapping]) -> list[dict]:
    return [
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
    ]


def _aggregate_rows(
    comparisons: list[HouseholdComparison],
    cases_by_id: dict[int | str, Case],
    mappings: list[ProgramMapping],
) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(_aggregate_bucket)
    for item in comparisons:
        weight = _case_weight(cases_by_id.get(item.household_id))
        for comparison in item.comparisons:
            _update_aggregate_bucket(buckets[comparison.variable], comparison, weight)
    return _aggregate_rows_from_buckets(buckets, mappings)


def _update_aggregate_bucket(
    bucket: dict,
    comparison: VariableComparison,
    weight: float,
) -> None:
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
        bucket["left_positive_weight"] += weight if bool(comparison.left_value) else 0
        bucket["left_weighted_sum"] += _to_number(comparison.left_value) * weight
    if comparison.right_value is None:
        bucket["missing_right_count"] += 1
    else:
        bucket["right_positive_weight"] += weight if bool(comparison.right_value) else 0
        bucket["right_weighted_sum"] += _to_number(comparison.right_value) * weight
    if comparison.left_value is None and comparison.right_value is None:
        bucket["missing_both_count"] += 1


def _aggregate_rows_from_buckets(
    buckets: dict[str, dict],
    mappings: list[ProgramMapping],
) -> list[dict]:
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
            left_rate = _percentage(
                bucket["left_positive_weight"], bucket["comparison_weight"]
            )
            right_rate = _percentage(
                bucket["right_positive_weight"], bucket["comparison_weight"]
            )
            row.update(
                {
                    "left_positive_weight": _clean_float(
                        bucket["left_positive_weight"]
                    ),
                    "right_positive_weight": _clean_float(
                        bucket["right_positive_weight"]
                    ),
                    "left_positive_rate": left_rate,
                    "right_positive_rate": right_rate,
                    "positive_rate_difference": _percentage(
                        bucket["left_positive_weight"]
                        - bucket["right_positive_weight"],
                        bucket["comparison_weight"],
                    ),
                    "quality_flags": _quality_flags(left_rate, right_rate),
                }
            )
        rows.append(row)
    return rows


def _quality_flags(left_rate: float, right_rate: float) -> list[dict]:
    """Detect degenerate positive-rate divergence on binary comparisons.

    A binary engine that *never* returns True (or *always* returns True) while
    the counterpart engine has real spread is almost certainly broken —
    "agreement" on the dominant outcome can mask a silent failure where the
    pipeline returns a constant. We flag these explicitly so the dashboard
    and CLI surface them next to the match rate.
    """
    flags: list[dict] = []
    if left_rate == 0 and right_rate > 0:
        flags.append({
            "severity": "alarm",
            "code": "left_always_false",
            "message": (
                f"Left engine never returned True ({left_rate:.1f}%) while "
                f"right engine returned True for {right_rate:.1f}% of cases "
                "— match rate likely reflects agreement on the dominant False "
                "outcome, not real agreement."
            ),
        })
    if left_rate == 100 and right_rate < 100:
        flags.append({
            "severity": "alarm",
            "code": "left_always_true",
            "message": (
                f"Left engine returned True for {left_rate:.1f}% of cases "
                f"while right engine returned True for {right_rate:.1f}% — "
                "likely over-permissive (missing eligibility tests) or "
                "always-true bug."
            ),
        })
    if right_rate == 0 and left_rate > 0:
        flags.append({
            "severity": "alarm",
            "code": "right_always_false",
            "message": (
                f"Right engine never returned True while left engine "
                f"returned True for {left_rate:.1f}% — right pipeline likely "
                "broken."
            ),
        })
    if right_rate == 100 and left_rate < 100:
        flags.append({
            "severity": "alarm",
            "code": "right_always_true",
            "message": (
                f"Right engine returned True for 100% of cases while left "
                f"returned True for {left_rate:.1f}% — right likely "
                "over-permissive."
            ),
        })
    return flags


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
    return _weighted_summary_from_totals(
        comparison_weight,
        match_weight,
        mismatch_weight,
    )


def _weighted_summary_from_totals(
    comparison_weight: float,
    match_weight: float,
    mismatch_weight: float,
) -> dict[str, float]:
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


def _count_object(rows: list[dict], key: str) -> dict[str, int]:
    """Return certificate-safe named counters instead of display rows."""

    counts = Counter(
        str(row[key]) for row in rows if row.get(key) is not None
    )
    return dict(sorted(counts.items()))


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


def strip_heavy_case_metadata(report: dict) -> dict:
    """Drop raw input-record dumps from every case row, keeping counts.

    Committed dashboard copies must never carry them — at roughly 2 MB per
    generic-projector household they turn a small suite's dashboard copy
    into gigabytes — while the full reports/ artifact stays the complete
    record and feeds the case-explorer input panel via
    scripts/emit_case_artifacts.py.
    """

    heavy = (
        "axiom_input_records",
        "axiom_input_record_overlays",
        "axiom_relations",
        "axiom_all_outputs",
    )
    cases = report.get("cases")
    if not cases:
        return report
    slim_cases = []
    for case in cases:
        metadata = case.get("metadata")
        if metadata and any(key in metadata for key in heavy):
            metadata = dict(metadata)
            for key in heavy:
                value = metadata.pop(key, None)
                if isinstance(value, (list, tuple, dict)):
                    metadata.setdefault(f"{key}_count", len(value))
            case = {**case, "metadata": metadata}
        slim_cases.append(case)
    return {**report, "cases": slim_cases}


def _top_level_json_entry(key: str, value: object) -> str:
    return f"  {json.dumps(key)}: {_indented_json(value, 2).lstrip()}"


def _indented_json(value: object, spaces: int) -> str:
    prefix = " " * spaces
    text = json.dumps(value, indent=2, sort_keys=True)
    return prefix + text.replace("\n", f"\n{prefix}")
