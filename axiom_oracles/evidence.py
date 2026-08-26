"""Validation and binding for committed per-case execution evidence.

Comparison reports are summaries.  The case chunks are the execution
evidence behind those summaries, and ``index.json`` binds the two artifacts.
This module deliberately does not attest engine identity or policy-output
coverage; that is the separate execution-attestation layer.

Reconciliation has three honest strengths:

``full``
    Every stored case carries explicit match/mismatch verdict rows, so all
    summary counts, report aggregate values, and dashboard row semantics are
    recomputed from the stored projection.
``cardinality``
    The chunks carry well-formed cases but no per-case verdicts.  Only
    ``comparison_count == number of cases`` plus summary conservation can be
    established.
``none``
    The stored shape cannot support either claim.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Literal


REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK_INDEX_SCHEMA_VERSION = "axiom_oracles.chunk_index.v1"

Binding = Literal["bound", "unbound"]
Reconciliation = Literal["full", "cardinality", "none"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPRESENTATION_ABS_TOLERANCE = 1e-6


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant {value!r}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r}")
    return parsed


def strict_json_loads(raw: str | bytes) -> object:
    """Parse standards-compliant JSON and reject every non-finite number."""

    return json.loads(
        raw,
        parse_constant=_reject_json_constant,
        parse_float=_finite_json_float,
    )


def _finite_native_number(value: object) -> int | float | None:
    """Return a finite JSON-native number without treating booleans as numbers."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def dashboard_delta(left: object, right: object) -> int | float | None:
    """Return the compact dashboard delta (right minus left), when numeric."""

    left_number = _finite_native_number(left)
    right_number = _finite_native_number(right)
    if left_number is None or right_number is None:
        return None
    difference = right_number - left_number
    return _finite_native_number(difference)


def dashboard_match_rate(matches: int, mismatches: int) -> float:
    """Derive the compact dashboard percentage with exact semantic endpoints."""

    total = matches + mismatches
    return 100.0 if total == 0 else 100.0 * matches / total


def _representation_matches(left: int | float, right: int | float) -> bool:
    """Compare derived JSON numbers at six-decimal/IEEE representation precision."""

    left_float = float(left)
    right_float = float(right)
    tolerance = max(
        _REPRESENTATION_ABS_TOLERANCE,
        4 * math.ulp(left_float),
        4 * math.ulp(right_float),
    )
    return abs(left_float - right_float) <= tolerance


def is_safe_suite_name(value: object) -> bool:
    """Whether ``value`` is one non-traversing case-directory component."""

    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and Path(value).name == value
        and "\\" not in value
    )


@dataclass(frozen=True)
class EvidenceChunk:
    """Identity and cardinality of one parsed chunk."""

    name: str
    sha256: str
    cases: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "cases": self.cases,
        }


@dataclass(frozen=True)
class EvidenceReport:
    """Result of validating one report and all of its committed case chunks."""

    report_path: str
    report_sha256: str | None
    suite: str | None
    binding: Binding
    reconciliation: Reconciliation
    case_count: int
    inline_case_count: int
    chunk_case_count: int
    comparison_count: int | None
    match_count: int | None
    mismatch_count: int | None
    chunks: tuple[EvidenceChunk, ...]
    case_verdicts_sha256: str | None
    content_defects: tuple[str, ...]
    binding_defects: tuple[str, ...]

    @property
    def defects(self) -> tuple[str, ...]:
        """All defects, preserving content-before-binding diagnostic order."""

        return self.content_defects + self.binding_defects

    @property
    def content_valid(self) -> bool:
        """Whether rows and counts are consistent, independent of an index."""

        return not self.content_defects

    @property
    def valid(self) -> bool:
        """Whether both content and report/chunk binding are valid."""

        return not self.defects

    @property
    def clean(self) -> bool:
        """Compatibility spelling for callers expressing a clean evidence leg."""

        return self.valid


@dataclass(frozen=True)
class _Verdict:
    """Canonical semantic projection of one stored comparison verdict."""

    case_id: str | None
    concept: str
    left: object
    right: object
    outcome: Literal["match", "mismatch"]
    disposition: str | None
    location: str


@dataclass(frozen=True)
class _ConceptRule:
    """The report-declared comparison and tolerance semantics for a concept."""

    comparison: str
    tolerance: float
    relative_tolerance: float


def sha256_path(path: Path) -> str:
    """Return the SHA-256 of the exact bytes at ``path``."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    """Render checkout paths deterministically and external fixtures exactly."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def report_identity(report_path: str | Path) -> tuple[str, str | None]:
    """Return the canonical path string and byte identity used by indexes."""

    path = Path(report_path).resolve()
    # Synthetic fixtures outside the checkout still need an unambiguous exact
    # identity. Production indexes are always repository-relative.
    display = _display_path(path)
    if not path.is_file():
        digest = None
    else:
        try:
            digest = sha256_path(path)
        except OSError:
            # The caller's parse/read path records the actionable defect.
            digest = None
    return display, digest


def _defect(suite: str | None, message: str) -> str:
    return f"{suite or '<unknown suite>'}: {message}"


def _strict_count(
    container: dict,
    field: str,
    defects: list[str],
    suite: str | None,
) -> int | None:
    if field not in container:
        defects.append(_defect(suite, f"summary.{field} is missing"))
        return None
    value = container[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        defects.append(
            _defect(
                suite,
                f"summary.{field} is not a non-negative integer ({value!r})",
            )
        )
        return None
    return value


def _case_id(
    row: dict,
    *,
    compact: bool,
    location: str,
    defects: list[str],
    suite: str | None,
) -> str | None:
    key = "id" if compact else ("case_id" if "case_id" in row else "id")
    if key not in row:
        defects.append(_defect(suite, f"{location} has no case id"))
        return None
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        defects.append(
            _defect(
                suite,
                f"{location} case id must be a non-empty string or integer ({value!r})",
            )
        )
        return None
    if isinstance(value, str) and not value:
        defects.append(_defect(suite, f"{location} has an empty case id"))
        return None
    # Producers historically use both integer and string IDs. Treat their
    # textual identity as authoritative so numeric 1 cannot evade a collision
    # with string "1".
    return str(value)


def _record_list(
    row: dict,
    field: str,
    *,
    required: bool,
    required_keys: tuple[str, ...],
    location: str,
    defects: list[str],
    suite: str | None,
) -> list[dict] | None:
    if field not in row:
        if required:
            defects.append(_defect(suite, f"{location}.{field} is missing"))
        return None
    value = row[field]
    if not isinstance(value, list):
        defects.append(_defect(suite, f"{location}.{field} must be an array"))
        return None
    valid: list[dict] = []
    for index, record in enumerate(value):
        record_location = f"{location}.{field}[{index}]"
        if not isinstance(record, dict):
            defects.append(_defect(suite, f"{record_location} must be an object"))
            continue
        missing = [key for key in required_keys if key not in record]
        if missing:
            defects.append(
                _defect(
                    suite,
                    f"{record_location} is missing {', '.join(missing)}",
                )
            )
            continue
        name_key = required_keys[0]
        name = record.get(name_key)
        if not isinstance(name, str) or not name:
            defects.append(
                _defect(
                    suite,
                    f"{record_location}.{name_key} must be a non-empty string",
                )
            )
            continue
        valid.append(record)
    return valid


def _case_verdicts(
    *,
    case_id: str | None,
    matches: list[dict] | None,
    mismatches: list[dict] | None,
    compact: bool,
    location: str,
    defects: list[str],
    suite: str | None,
) -> tuple[_Verdict, ...]:
    """Return canonical verdicts and reject ambiguous per-case concepts."""

    concept_key = "c" if compact else "concept"
    left_key = "l" if compact else "left"
    right_key = "x" if compact else "right"
    match_field = "v" if compact else "matches"
    mismatch_field = "m" if compact else "mismatches"

    def indexed(
        records: list[dict] | None,
        *,
        field: str,
    ) -> dict[str, tuple[dict, int]]:
        out: dict[str, tuple[dict, int]] = {}
        for index, record in enumerate(records or []):
            concept = record.get(concept_key)
            if not isinstance(concept, str) or not concept:
                # _record_list records the precise malformed-name defect.
                continue
            if concept in out:
                defects.append(
                    _defect(
                        suite,
                        f"{location}.{field} repeats concept {concept!r}",
                    )
                )
                continue
            out[concept] = (record, index)
        return out

    matches_by_concept = indexed(matches, field=match_field)
    mismatches_by_concept = indexed(mismatches, field=mismatch_field)
    for concept in sorted(set(matches_by_concept) & set(mismatches_by_concept)):
        defects.append(
            _defect(
                suite,
                f"{location} concept {concept!r} appears in both "
                f".{match_field} and .{mismatch_field}",
            )
        )

    verdicts: list[_Verdict] = []
    for outcome, field, records in (
        ("match", match_field, matches_by_concept),
        ("mismatch", mismatch_field, mismatches_by_concept),
    ):
        for concept, (record, index) in records.items():
            marker: str | None = None
            if outcome == "mismatch":
                raw_marker = record.get("e") if compact else record.get("disposition")
                if raw_marker is not None:
                    if compact:
                        if isinstance(raw_marker, str) and raw_marker:
                            marker = raw_marker
                        else:
                            defects.append(
                                _defect(
                                    suite,
                                    f"{location}.{field}[{index}].e must be a "
                                    "non-empty string",
                                )
                            )
                    elif (
                        isinstance(raw_marker, dict)
                        and isinstance(raw_marker.get("disposition"), str)
                        and raw_marker["disposition"]
                    ):
                        marker = raw_marker["disposition"]
                    else:
                        defects.append(
                            _defect(
                                suite,
                                f"{location}.{field}[{index}].disposition must "
                                "name a disposition",
                            )
                        )
            verdicts.append(
                _Verdict(
                    case_id=case_id,
                    concept=concept,
                    left=record.get(left_key),
                    right=record.get(right_key),
                    outcome=outcome,
                    disposition=marker,
                    location=f"{location}.{field}[{index}]",
                )
            )
    return tuple(verdicts)


def _case_verdicts_sha256(verdicts: tuple[_Verdict, ...]) -> str:
    """Commit exact verdict values to case identity, independent of row order."""

    records = [
        json.dumps(
            {
                "case_id": verdict.case_id,
                "concept": verdict.concept,
                "left": verdict.left,
                "outcome": verdict.outcome,
                "right": verdict.right,
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        for verdict in verdicts
    ]
    payload = (
        "axiom_oracles.case_verdicts.v1\n"
        f"[{','.join(sorted(records))}]"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_compact_delta(
    mismatch: dict,
    *,
    location: str,
    defects: list[str],
    suite: str | None,
) -> None:
    """Validate the dashboard-rendered delta against its stored side values."""

    if "d" not in mismatch:
        defects.append(_defect(suite, f"{location}.d is missing"))
        return
    expected = dashboard_delta(mismatch.get("l"), mismatch.get("x"))
    declared = mismatch["d"]
    if expected is None:
        if declared is not None:
            defects.append(
                _defect(
                    suite,
                    f"{location}.d must be null when l/x are not finite numbers",
                )
            )
        return
    declared_number = _finite_native_number(declared)
    if declared_number is None:
        defects.append(
            _defect(
                suite,
                f"{location}.d must be a finite number equal to x - l "
                f"({expected!r})",
            )
        )
        return
    if not _representation_matches(declared_number, expected):
        defects.append(
            _defect(
                suite,
                f"{location}.d {declared!r} does not equal x - l "
                f"{expected!r} within representation tolerance",
            )
        )


def _validate_compact_case(
    row: object,
    location: str,
    defects: list[str],
    suite: str | None,
) -> tuple[
    str | None,
    tuple[int, int] | None,
    bool,
    tuple[_Verdict, ...],
]:
    if not isinstance(row, dict):
        defects.append(_defect(suite, f"{location} must be an object"))
        return None, None, False, ()

    identity = _case_id(
        row,
        compact=True,
        location=location,
        defects=defects,
        suite=suite,
    )
    for field in ("r", "h", "m"):
        if field not in row:
            defects.append(_defect(suite, f"{location}.{field} is missing"))
    raw_rate = row.get("r")
    rate = _finite_native_number(raw_rate)
    if raw_rate is not None and rate is None:
        defects.append(
            _defect(suite, f"{location}.r must be a finite number or null")
        )
    elif rate is not None and (rate < 0 or rate > 100):
        defects.append(_defect(suite, f"{location}.r must be between 0 and 100"))
    household = row.get("h")
    if not isinstance(household, dict):
        defects.append(_defect(suite, f"{location}.h must be an object"))

    mismatches = _record_list(
        row,
        "m",
        required=True,
        required_keys=("c", "l", "x"),
        location=location,
        defects=defects,
        suite=suite,
    )
    _record_list(
        row,
        "i",
        required=False,
        required_keys=("n", "v"),
        location=location,
        defects=defects,
        suite=suite,
    )
    verdicts = _record_list(
        row,
        "v",
        required=False,
        required_keys=("c", "l", "x"),
        location=location,
        defects=defects,
        suite=suite,
    )
    raw_mismatches = row.get("m")
    if isinstance(raw_mismatches, list):
        for index, mismatch in enumerate(raw_mismatches):
            if isinstance(mismatch, dict):
                _validate_compact_delta(
                    mismatch,
                    location=f"{location}.m[{index}]",
                    defects=defects,
                    suite=suite,
                )
    # ``v`` explicitly stores matched comparisons; a non-empty ``m`` stores
    # explicit mismatch evidence. An absent ``v`` cannot mean zero matches
    # generally (SNAP-QC omits all verdict values), so that row supports full
    # reconciliation only when ``v`` is present. Cardinality is available only
    # when every row omits ``v`` *and* has an empty ``m``; otherwise partial
    # verdict evidence must not be laundered into a weaker passing claim.
    outcomes = (
        (len(verdicts), len(mismatches or []))
        if verdicts is not None and mismatches is not None
        else None
    )
    if outcomes is not None:
        matches, mismatch_count = outcomes
        expected_rate = dashboard_match_rate(matches, mismatch_count)
        if raw_rate is None:
            defects.append(
                _defect(
                    suite,
                    f"{location}.r must equal the stored verdict match rate "
                    f"{expected_rate!r}",
                )
            )
        elif rate is not None:
            if expected_rate in (0.0, 100.0):
                if rate != expected_rate:
                    defects.append(
                        _defect(
                            suite,
                            f"{location}.r {raw_rate!r} does not equal the exact "
                            f"stored verdict match rate endpoint {expected_rate!r}",
                        )
                    )
            elif not _representation_matches(rate, expected_rate):
                defects.append(
                    _defect(
                        suite,
                        f"{location}.r {raw_rate!r} does not equal the stored "
                        f"verdict match rate {expected_rate!r} within "
                        "representation tolerance",
                    )
                )
    elif mismatches and rate == 100:
        defects.append(
            _defect(
                suite,
                f"{location}.r cannot claim 100 percent agreement while the "
                "row stores a mismatch verdict",
            )
        )
    explicit_verdict = "v" in row or bool(mismatches)
    semantic_verdicts = _case_verdicts(
        case_id=identity,
        matches=verdicts,
        mismatches=mismatches,
        compact=True,
        location=location,
        defects=defects,
        suite=suite,
    )
    return identity, outcomes, explicit_verdict, semantic_verdicts


def _validate_inline_case(
    row: object,
    location: str,
    defects: list[str],
    suite: str | None,
) -> tuple[
    str | None,
    tuple[int, int] | None,
    bool,
    tuple[_Verdict, ...],
]:
    if not isinstance(row, dict):
        defects.append(_defect(suite, f"{location} must be an object"))
        return None, None, False, ()
    if "id" in row and "case_id" not in row:
        return _validate_compact_case(row, location, defects, suite)

    identity = _case_id(
        row,
        compact=False,
        location=location,
        defects=defects,
        suite=suite,
    )
    match_key = "matched" if "matched" in row else "match" if "match" in row else None
    if match_key:
        matched = row[match_key]
        if not isinstance(matched, bool):
            defects.append(_defect(suite, f"{location}.{match_key} must be a boolean"))
            return identity, None, True, ()
        # A case-level boolean carries no concept or values and therefore
        # cannot support canonical full semantic reconciliation.
        return identity, (1, 0) if matched else (0, 1), True, ()

    mismatches = _record_list(
        row,
        "mismatches",
        required=False,
        required_keys=("concept", "left", "right"),
        location=location,
        defects=defects,
        suite=suite,
    )
    matches = _record_list(
        row,
        "matches",
        required=False,
        required_keys=("concept", "left", "right"),
        location=location,
        defects=defects,
        suite=suite,
    )
    if "matches" in row and "mismatches" in row:
        if matches is not None and mismatches is not None:
            semantic_verdicts = _case_verdicts(
                case_id=identity,
                matches=matches,
                mismatches=mismatches,
                compact=False,
                location=location,
                defects=defects,
                suite=suite,
            )
            return (
                identity,
                (len(matches), len(mismatches)),
                True,
                semantic_verdicts,
            )
    return identity, None, "matches" in row, ()


def _strict_nonnegative_int(
    container: dict,
    field: str,
    *,
    location: str,
    defects: list[str],
    suite: str | None,
    required: bool = True,
) -> int | None:
    if field not in container:
        if required:
            defects.append(_defect(suite, f"{location}.{field} is missing"))
        return None
    value = container[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        defects.append(
            _defect(
                suite,
                f"{location}.{field} is not a non-negative integer ({value!r})",
            )
        )
        return None
    return value


def _strict_tolerance(
    row: dict,
    field: str,
    *,
    location: str,
    defects: list[str],
    suite: str | None,
) -> float | None:
    if field not in row:
        defects.append(_defect(suite, f"{location}.{field} is missing"))
        return None
    value = row[field]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        defects.append(
            _defect(
                suite,
                f"{location}.{field} must be a finite non-negative number ({value!r})",
            )
        )
        return None
    return float(value)


def _concept_rules(
    report: dict,
    defects: list[str],
    suite: str | None,
) -> dict[str, _ConceptRule]:
    raw = report.get("concepts")
    if not isinstance(raw, list):
        defects.append(
            _defect(
                suite,
                "report concepts must be an array for full reconciliation",
            )
        )
        return {}
    rules: dict[str, _ConceptRule] = {}
    for index, row in enumerate(raw):
        location = f"report concepts[{index}]"
        if not isinstance(row, dict):
            defects.append(_defect(suite, f"{location} must be an object"))
            continue
        concept = row.get("id")
        if not isinstance(concept, str) or not concept:
            defects.append(_defect(suite, f"{location}.id must be a non-empty string"))
            continue
        if concept in rules:
            defects.append(_defect(suite, f"report concepts repeats {concept!r}"))
            continue
        comparison = row.get("comparison")
        if not isinstance(comparison, str) or not comparison:
            defects.append(
                _defect(
                    suite,
                    f"{location}.comparison must be a non-empty string",
                )
            )
            continue
        tolerance = _strict_tolerance(
            row,
            "tolerance",
            location=location,
            defects=defects,
            suite=suite,
        )
        relative_tolerance = _strict_tolerance(
            row,
            "relative_tolerance",
            location=location,
            defects=defects,
            suite=suite,
        )
        if tolerance is not None and relative_tolerance is not None:
            rules[concept] = _ConceptRule(
                comparison=comparison,
                tolerance=tolerance,
                relative_tolerance=relative_tolerance,
            )
    return rules


def _as_finite_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _verdict_is_match(
    left: object,
    right: object,
    rule: _ConceptRule,
) -> bool:
    if left is None or right is None:
        return False
    if rule.comparison == "amount":
        left_number = _as_finite_number(left)
        right_number = _as_finite_number(right)
        return (
            left_number is not None
            and right_number is not None
            and math.isclose(
                left_number,
                right_number,
                rel_tol=rule.relative_tolerance,
                abs_tol=rule.tolerance,
            )
        )
    return bool(left) == bool(right)


def _projected_value_matches(
    chunk_value: object,
    report_value: object,
    rule: _ConceptRule,
) -> bool:
    """Compare two copies of one side using the report's tolerance semantics."""

    if rule.comparison == "amount":
        chunk_number = _as_finite_number(chunk_value)
        report_number = _as_finite_number(report_value)
        return (
            chunk_number is not None
            and report_number is not None
            and math.isclose(
                chunk_number,
                report_number,
                rel_tol=rule.relative_tolerance,
                abs_tol=rule.tolerance,
            )
        )
    return type(chunk_value) is type(report_value) and chunk_value == report_value


def _aggregate_verdicts(
    report: dict,
    verdicts: tuple[_Verdict, ...],
    rules: dict[str, _ConceptRule],
    defects: list[str],
    suite: str | None,
) -> None:
    raw = report.get("aggregates")
    if not isinstance(raw, list):
        defects.append(
            _defect(
                suite,
                "report aggregates must be an array for full reconciliation",
            )
        )
        return

    declared: dict[str, tuple[int, int, dict, str]] = {}
    for index, row in enumerate(raw):
        location = f"report aggregates[{index}]"
        if not isinstance(row, dict):
            defects.append(_defect(suite, f"{location} must be an object"))
            continue
        concept = row.get("concept")
        if not isinstance(concept, str) or not concept:
            defects.append(
                _defect(
                    suite,
                    f"{location}.concept must be a non-empty string",
                )
            )
            continue
        if concept in declared:
            defects.append(
                _defect(suite, f"report aggregates repeats concept {concept!r}")
            )
            continue
        comparisons = _strict_nonnegative_int(
            row,
            "comparison_count",
            location=location,
            defects=defects,
            suite=suite,
        )
        mismatches = _strict_nonnegative_int(
            row,
            "mismatch_count",
            location=location,
            defects=defects,
            suite=suite,
        )
        if comparisons is None or mismatches is None:
            continue
        if mismatches > comparisons:
            defects.append(
                _defect(
                    suite,
                    f"{location}.mismatch_count {mismatches} exceeds "
                    f"comparison_count {comparisons}",
                )
            )
            continue
        matches = comparisons - mismatches
        for field, expected in (
            ("compared", comparisons),
            ("match_count", matches),
            ("matched", matches),
        ):
            if field not in row:
                continue
            value = _strict_nonnegative_int(
                row,
                field,
                location=location,
                defects=defects,
                suite=suite,
                required=False,
            )
            if value is not None and value != expected:
                defects.append(
                    _defect(
                        suite,
                        f"{location}.{field} {value} does not match derived "
                        f"verdict count {expected}",
                    )
                )
        declared[concept] = (matches, mismatches, row, location)

    actual: dict[str, list[_Verdict]] = {}
    for verdict in verdicts:
        actual.setdefault(verdict.concept, []).append(verdict)
    missing = sorted(set(declared) - set(actual))
    unexpected = sorted(set(actual) - set(declared))
    if missing:
        defects.append(
            _defect(
                suite,
                f"report aggregate concepts have no stored verdicts {missing}",
            )
        )
    if unexpected:
        defects.append(
            _defect(
                suite,
                f"stored verdict concepts have no report aggregate {unexpected}",
            )
        )
    for concept in sorted(set(declared) & set(actual)):
        expected_matches, expected_mismatches, row, location = declared[concept]
        concept_verdicts = actual[concept]
        actual_matches = sum(
            verdict.outcome == "match" for verdict in concept_verdicts
        )
        actual_mismatches = len(concept_verdicts) - actual_matches
        if (expected_matches, expected_mismatches) != (
            actual_matches,
            actual_mismatches,
        ):
            defects.append(
                _defect(
                    suite,
                    f"report aggregate {concept!r} declares "
                    f"{expected_matches} matches/{expected_mismatches} "
                    "mismatches but stored verdicts contain "
                    f"{actual_matches}/{actual_mismatches}",
                )
            )
        rule = rules.get(concept)
        if rule is None:
            continue

        value_fields = (
            ("left_weighted_sum", "right_weighted_sum")
            if rule.comparison == "amount"
            else ("left_positive_weight", "right_positive_weight")
        )
        carries_values = any(field in row for field in value_fields)
        if carries_values:
            if "comparison_weight" not in row:
                defects.append(
                    _defect(
                        suite,
                        f"{location}.comparison_weight is required to reconcile "
                        "aggregate value fields",
                    )
                )
            else:
                comparison_weight = _finite_native_number(row["comparison_weight"])
                if comparison_weight is None:
                    defects.append(
                        _defect(
                            suite,
                            f"{location}.comparison_weight must be a finite number",
                        )
                    )
                elif not _representation_matches(
                    comparison_weight,
                    len(concept_verdicts),
                ):
                    defects.append(
                        _defect(
                            suite,
                            f"{location}.comparison_weight "
                            f"{row['comparison_weight']!r} cannot be reproduced "
                            "by unweighted stored verdicts "
                            f"({len(concept_verdicts)})",
                        )
                    )

        for field, side in zip(value_fields, ("left", "right"), strict=True):
            if field not in row:
                continue
            declared_value = _finite_native_number(row[field])
            if declared_value is None:
                defects.append(
                    _defect(
                        suite,
                        f"{location}.{field} must be a finite number",
                    )
                )
                continue
            if rule.comparison == "amount":
                values: list[float] = []
                complete = True
                for verdict in concept_verdicts:
                    raw_value = getattr(verdict, side)
                    if raw_value is None:
                        continue
                    number = _as_finite_number(raw_value)
                    if number is None:
                        defects.append(
                            _defect(
                                suite,
                                f"{verdict.location} {side} value "
                                f"{raw_value!r} cannot contribute to {field}",
                            )
                        )
                        complete = False
                    else:
                        values.append(number)
                if not complete:
                    continue
                actual_value: int | float = math.fsum(values)
            else:
                actual_value = sum(
                    bool(getattr(verdict, side)) for verdict in concept_verdicts
                )
            if not _representation_matches(declared_value, actual_value):
                defects.append(
                    _defect(
                        suite,
                        f"{location}.{field} {row[field]!r} does not match "
                        f"{actual_value!r} recomputed from stored verdict values",
                    )
                )


def _report_disposition(
    row: dict,
    *,
    location: str,
    defects: list[str],
    suite: str | None,
) -> str | None:
    raw = row.get("disposition")
    if raw is None:
        return None
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("disposition"), str)
        and raw["disposition"]
    ):
        return raw["disposition"]
    defects.append(
        _defect(
            suite,
            f"{location}.disposition must be an object naming a disposition",
        )
    )
    return None


def _reconcile_disposition_counts(
    report: dict,
    markers: list[str | None],
    defects: list[str],
    suite: str | None,
) -> None:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return
    dispositioned = summary.get("dispositioned")
    if dispositioned is None:
        return
    if not isinstance(dispositioned, dict):
        # The report-shape validator records this elsewhere in certification.
        return
    counts = dispositioned.get("counts")
    if not isinstance(counts, dict):
        defects.append(
            _defect(
                suite,
                "summary.dispositioned.counts must be an object for full "
                "reconciliation",
            )
        )
        return
    actual = Counter(marker or "unexplained" for marker in markers)
    for kind in sorted(set(counts) | set(actual)):
        declared = _strict_nonnegative_int(
            counts,
            kind,
            location="summary.dispositioned.counts",
            defects=defects,
            suite=suite,
            required=False,
        )
        if declared is None:
            declared = 0
        observed = actual.get(kind, 0)
        if declared != observed:
            defects.append(
                _defect(
                    suite,
                    f"summary.dispositioned.counts.{kind} {declared} does not "
                    f"match {observed} report mismatch disposition marker(s)",
                )
            )


def _reconcile_report_mismatches(
    report: dict,
    verdicts: tuple[_Verdict, ...],
    rules: dict[str, _ConceptRule],
    defects: list[str],
    suite: str | None,
) -> None:
    raw = report.get("mismatches")
    if not isinstance(raw, list):
        defects.append(
            _defect(
                suite,
                "report mismatches must be an array for full reconciliation",
            )
        )
        return

    stored: dict[tuple[str, str], _Verdict] = {}
    for verdict in verdicts:
        if verdict.outcome != "mismatch" or verdict.case_id is None:
            continue
        stored[(verdict.case_id, verdict.concept)] = verdict

    reported: dict[tuple[str, str], tuple[dict, str | None, str]] = {}
    markers: list[str | None] = []
    for index, row in enumerate(raw):
        location = f"report mismatches[{index}]"
        if not isinstance(row, dict):
            defects.append(_defect(suite, f"{location} must be an object"))
            continue
        case_id = _case_id(
            row,
            compact=False,
            location=location,
            defects=defects,
            suite=suite,
        )
        concept = row.get("concept")
        if not isinstance(concept, str) or not concept:
            defects.append(
                _defect(
                    suite,
                    f"{location}.concept must be a non-empty string",
                )
            )
            continue
        if "left" not in row or "right" not in row:
            defects.append(
                _defect(suite, f"{location} must carry left and right values")
            )
            continue
        if case_id is None:
            continue
        key = (case_id, concept)
        if key in reported:
            defects.append(
                _defect(
                    suite,
                    f"report mismatches repeats case/concept {key!r}",
                )
            )
            continue
        marker = _report_disposition(
            row,
            location=location,
            defects=defects,
            suite=suite,
        )
        reported[key] = (row, marker, location)
        markers.append(marker)

    missing = sorted(set(reported) - set(stored))
    unexpected = sorted(set(stored) - set(reported))
    if missing:
        defects.append(
            _defect(
                suite,
                f"report mismatch rows have no stored mismatch verdict {missing}",
            )
        )
    if unexpected:
        defects.append(
            _defect(
                suite,
                f"stored mismatch verdicts have no report mismatch row {unexpected}",
            )
        )

    for key in sorted(set(reported) & set(stored)):
        report_row, report_marker, location = reported[key]
        stored_verdict = stored[key]
        rule = rules.get(key[1])
        if rule is not None:
            for side, chunk_value, report_value in (
                ("left", stored_verdict.left, report_row["left"]),
                ("right", stored_verdict.right, report_row["right"]),
            ):
                if not _projected_value_matches(
                    chunk_value,
                    report_value,
                    rule,
                ):
                    defects.append(
                        _defect(
                            suite,
                            f"{stored_verdict.location} {side} value "
                            f"{chunk_value!r} does not reconcile with "
                            f"{location}.{side} {report_value!r} under report "
                            "tolerance semantics",
                        )
                    )
        if stored_verdict.disposition != report_marker:
            defects.append(
                _defect(
                    suite,
                    f"{stored_verdict.location} disposition marker "
                    f"{stored_verdict.disposition!r} does not match "
                    f"{location} marker {report_marker!r}",
                )
            )
    _reconcile_disposition_counts(report, markers, defects, suite)


def _reconcile_full_semantics(
    report: dict,
    verdicts: tuple[_Verdict, ...],
    defects: list[str],
    suite: str | None,
) -> None:
    """Reconcile every canonical verdict with report semantics and aggregates."""

    rules = _concept_rules(report, defects, suite)
    for verdict in verdicts:
        rule = rules.get(verdict.concept)
        if rule is None:
            defects.append(
                _defect(
                    suite,
                    f"{verdict.location} concept {verdict.concept!r} has no "
                    "report concept definition",
                )
            )
            continue
        observed_match = _verdict_is_match(verdict.left, verdict.right, rule)
        expected_match = verdict.outcome == "match"
        if observed_match != expected_match:
            defects.append(
                _defect(
                    suite,
                    f"{verdict.location} values {verdict.left!r}/"
                    f"{verdict.right!r} do not satisfy the report's "
                    f"{verdict.outcome} tolerance semantics",
                )
            )
    _aggregate_verdicts(report, verdicts, rules, defects, suite)
    _reconcile_report_mismatches(report, verdicts, rules, defects, suite)


def _chunk_rows(
    path: Path,
    defects: list[str],
    suite: str | None,
) -> tuple[list[object], EvidenceChunk]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        defects.append(
            _defect(
                suite,
                f"{path.name} cannot be read ({exc.strerror or type(exc).__name__})",
            )
        )
        return [], EvidenceChunk(path.name, "", 0)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = strict_json_loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        defects.append(_defect(suite, f"{path.name} is not valid JSON ({exc})"))
        return [], EvidenceChunk(path.name, digest, 0)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        rows = payload["cases"]
    else:
        defects.append(
            _defect(
                suite,
                f"{path.name} must be an array or an object with a cases array",
            )
        )
        rows = []
    return rows, EvidenceChunk(path.name, digest, len(rows))


def _validate_chunk_index(
    *,
    index_path: Path,
    report_path: str,
    report_sha256: str | None,
    suite: str | None,
    chunks: tuple[EvidenceChunk, ...],
    case_verdicts_sha256: str | None = None,
) -> tuple[Binding, list[str]]:
    defects: list[str] = []
    if not index_path.is_file():
        return "unbound", [
            _defect(
                suite,
                f"chunk index {_display_path(index_path)} is missing; "
                "report/chunk evidence binding is unbound",
            )
        ]
    try:
        payload = strict_json_loads(index_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return "unbound", [_defect(suite, f"chunk index is not valid JSON ({exc})")]
    if not isinstance(payload, dict):
        return "unbound", [_defect(suite, "chunk index must be an object")]
    if payload.get("schema_version") != CHUNK_INDEX_SCHEMA_VERSION:
        defects.append(
            _defect(
                suite,
                "chunk index schema_version is not "
                f"{CHUNK_INDEX_SCHEMA_VERSION!r}; report/chunk evidence "
                "binding is unbound",
            )
        )
        return "unbound", defects

    indexed_suite = payload.get("suite")
    if indexed_suite is not None and indexed_suite != suite:
        defects.append(
            _defect(
                suite,
                f"chunk index declares suite {indexed_suite!r}, not {suite!r}",
            )
        )
    if payload.get("report_path") != report_path:
        defects.append(
            _defect(
                suite,
                f"chunk index report_path {payload.get('report_path')!r} "
                f"does not match cited report {report_path!r}",
            )
        )
    indexed_sha = payload.get("report_sha256")
    if not isinstance(indexed_sha, str) or not _SHA256.fullmatch(indexed_sha):
        defects.append(_defect(suite, "chunk index report_sha256 is invalid"))
    elif indexed_sha != report_sha256:
        defects.append(
            _defect(
                suite,
                f"chunk index report_sha256 {indexed_sha} does not match "
                f"report bytes {report_sha256}",
            )
        )
    if case_verdicts_sha256 is not None:
        indexed_verdicts_sha = payload.get("case_verdicts_sha256")
        if (
            not isinstance(indexed_verdicts_sha, str)
            or not _SHA256.fullmatch(indexed_verdicts_sha)
        ):
            defects.append(
                _defect(suite, "chunk index case_verdicts_sha256 is invalid")
            )
        elif indexed_verdicts_sha != case_verdicts_sha256:
            defects.append(
                _defect(
                    suite,
                    "chunk index case_verdicts_sha256 does not match the "
                    "recomputed per-case verdict identity "
                    f"({indexed_verdicts_sha} != {case_verdicts_sha256})",
                )
            )

    indexed_chunks = payload.get("chunks")
    if not isinstance(indexed_chunks, list):
        defects.append(_defect(suite, "chunk index chunks must be an array"))
        return "unbound", defects

    declared: dict[str, tuple[str, int]] = {}
    for position, item in enumerate(indexed_chunks):
        location = f"chunk index chunks[{position}]"
        if not isinstance(item, dict):
            defects.append(_defect(suite, f"{location} must be an object"))
            continue
        name = item.get("name")
        digest = item.get("sha256")
        cases = item.get("cases")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.startswith("chunk-")
            or not name.endswith(".json")
        ):
            defects.append(_defect(suite, f"{location}.name is invalid"))
            continue
        if name in declared:
            defects.append(_defect(suite, f"chunk index repeats {name!r}"))
            continue
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            defects.append(_defect(suite, f"{location}.sha256 is invalid"))
            continue
        if isinstance(cases, bool) or not isinstance(cases, int) or cases < 0:
            defects.append(
                _defect(suite, f"{location}.cases is not a non-negative integer")
            )
            continue
        declared[name] = (digest, cases)

    actual = {chunk.name: (chunk.sha256, chunk.cases) for chunk in chunks}
    missing = sorted(set(declared) - set(actual))
    unexpected = sorted(set(actual) - set(declared))
    if missing:
        defects.append(_defect(suite, f"chunk index names missing files {missing}"))
    if unexpected:
        defects.append(
            _defect(suite, f"chunk index omits committed chunks {unexpected}")
        )
    for name in sorted(set(declared) & set(actual)):
        declared_sha, declared_cases = declared[name]
        actual_sha, actual_cases = actual[name]
        if declared_sha != actual_sha:
            defects.append(
                _defect(
                    suite,
                    f"{name} sha256 does not match chunk index "
                    f"({declared_sha} != {actual_sha})",
                )
            )
        if declared_cases != actual_cases:
            defects.append(
                _defect(
                    suite,
                    f"{name} case count does not match chunk index "
                    f"({declared_cases} != {actual_cases})",
                )
            )

    chunk_count = payload.get("chunk_count")
    if chunk_count is not None:
        if (
            isinstance(chunk_count, bool)
            or not isinstance(chunk_count, int)
            or chunk_count < 0
        ):
            defects.append(
                _defect(
                    suite,
                    "chunk index chunk_count is not a non-negative integer",
                )
            )
        elif chunk_count != len(chunks):
            defects.append(
                _defect(
                    suite,
                    f"chunk index chunk_count {chunk_count!r} != {len(chunks)}",
                )
            )
    count = payload.get("count")
    actual_count = sum(chunk.cases for chunk in chunks)
    if count is not None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            defects.append(
                _defect(
                    suite,
                    "chunk index count is not a non-negative integer",
                )
            )
        elif count != actual_count:
            defects.append(
                _defect(
                    suite,
                    f"chunk index count {count!r} != {actual_count}",
                )
            )
    return ("unbound", defects) if defects else ("bound", [])


def validate_chunk_binding(
    report_path: str | Path,
    chunks: tuple[EvidenceChunk, ...],
    *,
    suite: str | None = None,
) -> tuple[Binding, tuple[str, ...]]:
    """Validate only index identity/cardinality, without parsing case rows.

    The census uses this after its existing cardinality scan.  Certification
    uses :func:`validate_suite_evidence`, which performs the strict row and
    verdict validation as well.
    """

    path = Path(report_path).resolve()
    identity, digest = report_identity(path)
    if suite is None and path.is_file():
        try:
            payload = strict_json_loads(path.read_text())
            suite = payload.get("suite") if isinstance(payload, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            suite = None
    if not is_safe_suite_name(suite):
        return "unbound", (
            _defect(
                suite if isinstance(suite, str) else None,
                "report suite must be a non-empty, safe path component; "
                "report/chunk evidence binding is unbound",
            ),
        )
    index_path = path.parent / "cases" / str(suite) / "index.json"
    binding, defects = _validate_chunk_index(
        index_path=index_path,
        report_path=identity,
        report_sha256=digest,
        suite=suite,
        chunks=chunks,
    )
    return binding, tuple(defects)


def validate_suite_evidence(report_path: str | Path) -> EvidenceReport:
    """Parse and validate a report plus every ``chunk-*.json`` for its suite."""

    path = Path(report_path).resolve()
    identity, report_sha = report_identity(path)
    content_defects: list[str] = []
    suite: str | None = None
    report: dict = {}
    if not path.is_file():
        content_defects.append(_defect(None, f"report {identity!r} does not exist"))
    else:
        try:
            payload = strict_json_loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            content_defects.append(
                _defect(None, f"report {identity!r} is not valid JSON ({exc})")
            )
        else:
            if not isinstance(payload, dict):
                content_defects.append(_defect(None, "report must be an object"))
            else:
                report = payload
                raw_suite = report.get("suite")
                if not is_safe_suite_name(raw_suite):
                    content_defects.append(
                        _defect(
                            None,
                            "report suite must be a non-empty, safe path component",
                        )
                    )
                else:
                    suite = raw_suite

    summary = report.get("summary")
    if not isinstance(summary, dict):
        content_defects.append(_defect(suite, "report summary must be an object"))
        summary = {}
    comparison_count = _strict_count(
        summary, "comparison_count", content_defects, suite
    )
    match_count = _strict_count(summary, "match_count", content_defects, suite)
    mismatch_count = _strict_count(summary, "mismatch_count", content_defects, suite)
    if (
        comparison_count is not None
        and match_count is not None
        and mismatch_count is not None
        and match_count + mismatch_count != comparison_count
    ):
        content_defects.append(
            _defect(
                suite,
                "summary counts do not conserve "
                f"({match_count} + {mismatch_count} != {comparison_count})",
            )
        )

    raw_inline = report.get("cases", [])
    if not isinstance(raw_inline, list):
        content_defects.append(_defect(suite, "report cases must be an array"))
        raw_inline = []

    chunk_dir = path.parent / "cases" / str(suite)
    chunk_paths = (
        sorted(chunk_dir.glob("chunk-*.json")) if suite and chunk_dir.is_dir() else []
    )
    chunks: list[EvidenceChunk] = []
    chunk_rows: list[tuple[object, str]] = []
    for chunk_path in chunk_paths:
        rows, chunk = _chunk_rows(chunk_path, content_defects, suite)
        chunks.append(chunk)
        chunk_rows.extend(
            (row, f"{chunk_path.name} row {index}") for index, row in enumerate(rows)
        )

    seen: dict[str, str] = {}
    outcomes: list[tuple[int, int] | None] = []
    explicit_verdicts: list[bool] = []
    semantic_verdicts: list[_Verdict] = []
    canonical_projections: list[bool] = []

    def record(
        case_identity: str | None,
        outcome: tuple[int, int] | None,
        explicit_verdict: bool,
        verdicts: tuple[_Verdict, ...],
        location: str,
    ) -> None:
        if case_identity is not None:
            previous = seen.get(case_identity)
            if previous is not None:
                content_defects.append(
                    _defect(
                        suite,
                        f"duplicate case id {case_identity!r} in "
                        f"{previous} and {location}",
                    )
                )
            else:
                seen[case_identity] = location
        outcomes.append(outcome)
        explicit_verdicts.append(explicit_verdict)
        semantic_verdicts.extend(verdicts)
        canonical_projections.append(
            outcome is not None and (bool(verdicts) or sum(outcome) == 0)
        )

    for index, row in enumerate(raw_inline):
        location = f"report cases[{index}]"
        case_identity, outcome, explicit_verdict, verdicts = _validate_inline_case(
            row, location, content_defects, suite
        )
        record(case_identity, outcome, explicit_verdict, verdicts, location)
    for row, location in chunk_rows:
        case_identity, outcome, explicit_verdict, verdicts = _validate_compact_case(
            row, location, content_defects, suite
        )
        record(case_identity, outcome, explicit_verdict, verdicts, location)

    inline_case_count = len(raw_inline)
    chunk_case_count = len(chunk_rows)
    parsed_case_count = inline_case_count + chunk_case_count
    declared_case_count = report.get("case_count")
    if (
        isinstance(declared_case_count, bool)
        or not isinstance(declared_case_count, int)
        or declared_case_count < 0
    ):
        content_defects.append(
            _defect(
                suite,
                f"report case_count is not a non-negative integer "
                f"({declared_case_count!r})",
            )
        )
    elif declared_case_count != parsed_case_count:
        content_defects.append(
            _defect(
                suite,
                f"report case_count {declared_case_count} does not match "
                f"{parsed_case_count} parsed cases",
            )
        )

    reconciliation: Reconciliation = "none"
    case_verdicts_sha: str | None = None
    if (
        parsed_case_count
        and all(outcome is not None for outcome in outcomes)
        and all(canonical_projections)
    ):
        reconciliation = "full"
        actual_matches = sum(outcome[0] for outcome in outcomes if outcome)
        actual_mismatches = sum(outcome[1] for outcome in outcomes if outcome)
        actual_comparisons = actual_matches + actual_mismatches
        for name, declared, actual in (
            ("comparison_count", comparison_count, actual_comparisons),
            ("match_count", match_count, actual_matches),
            ("mismatch_count", mismatch_count, actual_mismatches),
        ):
            if declared is not None and declared != actual:
                content_defects.append(
                    _defect(
                        suite,
                        f"summary.{name} {declared} does not match parsed "
                        f"per-case verdicts {actual}",
                    )
                )
        _reconcile_full_semantics(
            report,
            tuple(semantic_verdicts),
            content_defects,
            suite,
        )
        case_verdicts_sha = _case_verdicts_sha256(tuple(semantic_verdicts))
    elif chunk_case_count and not inline_case_count and not any(explicit_verdicts):
        reconciliation = "cardinality"
        if comparison_count is not None and comparison_count != chunk_case_count:
            content_defects.append(
                _defect(
                    suite,
                    f"summary.comparison_count {comparison_count} does not "
                    f"match parsed chunk cardinality {chunk_case_count}",
                )
            )
    else:
        content_defects.append(
            _defect(
                suite,
                "stored cases do not support full verdict or chunk-cardinality "
                "reconciliation",
            )
        )

    if parsed_case_count == 0:
        content_defects.append(
            _defect(suite, "report has no committed per-case execution evidence")
        )

    index_path = chunk_dir / "index.json"
    binding, binding_defects = _validate_chunk_index(
        index_path=index_path,
        report_path=identity,
        report_sha256=report_sha,
        suite=suite,
        chunks=tuple(chunks),
        case_verdicts_sha256=case_verdicts_sha,
    )
    return EvidenceReport(
        report_path=identity,
        report_sha256=report_sha,
        suite=suite,
        binding=binding,
        reconciliation=reconciliation,
        case_count=parsed_case_count,
        inline_case_count=inline_case_count,
        chunk_case_count=chunk_case_count,
        comparison_count=comparison_count,
        match_count=match_count,
        mismatch_count=mismatch_count,
        chunks=tuple(chunks),
        case_verdicts_sha256=case_verdicts_sha,
        content_defects=tuple(content_defects),
        binding_defects=tuple(binding_defects),
    )


def build_chunk_index(report_path: str | Path) -> dict:
    """Build a v1 index for structurally consistent report/chunk evidence.

    Existing legacy dashboard metadata is retained as a versioned superset;
    the binding fields and chunk descriptor array are always recomputed.
    """

    path = Path(report_path).resolve()
    evidence = validate_suite_evidence(path)
    if not evidence.content_valid or evidence.reconciliation == "none":
        details = "\n".join(f"- {defect}" for defect in evidence.content_defects)
        raise ValueError(
            f"cannot index inconsistent evidence for {evidence.suite}:\n{details}"
        )
    index_path = path.parent / "cases" / str(evidence.suite) / "index.json"
    legacy: dict = {}
    if index_path.is_file():
        try:
            payload = strict_json_loads(index_path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            legacy = {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "schema_version",
                    "report_path",
                    "report_sha256",
                    "case_verdicts_sha256",
                    "chunks",
                    "chunk_count",
                }
            }
    legacy["suite"] = evidence.suite
    legacy["count"] = evidence.chunk_case_count
    legacy["total_cases"] = evidence.chunk_case_count
    verdict_identity = (
        {"case_verdicts_sha256": evidence.case_verdicts_sha256}
        if evidence.case_verdicts_sha256 is not None
        else {}
    )
    return {
        "schema_version": CHUNK_INDEX_SCHEMA_VERSION,
        "report_path": evidence.report_path,
        "report_sha256": evidence.report_sha256,
        **verdict_identity,
        **legacy,
        "chunk_count": len(evidence.chunks),
        "chunks": [chunk.as_dict() for chunk in evidence.chunks],
    }
