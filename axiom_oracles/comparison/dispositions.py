"""First-class mismatch dispositions for comparison reports.

Raw match rates misrepresent parity when mismatches are fully explained —
e.g. the Belgium lane showed 59/88 (67%) while every residual was either an
arithmetically reconciled convention difference or a filed upstream engine
issue. This module gives those classifications a first-class, schema-validated
home (``dispositions/<suite>.yaml``) and joins them into the v2 comparison
report, which then carries a ``summary.dispositioned`` block with both the raw
and the explained rate.

Schema (``axiom_oracles.dispositions.v1``)
------------------------------------------

A dispositions file classifies mismatch rows of exactly one suite::

    schema: axiom_oracles.dispositions.v1
    suite: be-worker-ssc
    entries:
      - id: work-bonus-january-2025-timing
        concept: be:...#belgium_worker_work_bonus_..._total_reduction
        case_id: be-worker-ssc-30k          # or case_selector: {...}
        disposition: upstream_engine_gap
        evidence:
          mechanism: >-
            EUROMOD BE_2025 applies the February-onward 2025 work-bonus
            table to all 12 months; the statutory path weights January
            separately.
          arithmetic:
            - expression: "3398.52 - 3386.87"
              equals: 11.65
          upstream_url: https://github.com/ec-jrc/...
          sources:
            - axiom_oracles/data/euromod_issues.json#...
        linked_issue: https://github.com/ec-jrc/...
        expires_on_source_change: true
        pinned:
          left: 3398.5199999999995
          right: 3386.87

Validation rules (enforced in CI via ``scripts/apply_dispositions.py
--check`` and unit tests):

* Every entry MUST carry ``evidence`` with a non-empty ``mechanism`` AND at
  least one of (a) ``arithmetic`` items that reconcile numerically, or (b) an
  upstream citation (``evidence.upstream_url``, ``linked_issue``, or a
  ``evidence.sources`` item). A disposition without evidence is invalid —
  classifications must reconcile, not assert.
* ``arithmetic`` items are ``{expression, equals[, tolerance]}``. The
  expression is evaluated with a restricted arithmetic evaluator (numbers,
  ``+ - * /``, parentheses) and must equal ``equals`` within ``tolerance``
  (default ``0.005``). An arithmetic claim that does not reconcile fails
  validation — the Wallonia lesson.
* ``evidence.sources`` entries that are not URLs must be repo-relative paths
  (an optional ``#fragment`` may name an entry inside the file) and the file
  must exist, so citations cannot dangle.
* ``expires_on_source_change`` is required. When true and the entry carries
  ``pinned`` engine values, the disposition only applies while the live
  mismatch row still shows those values; when the source engines change, the
  disposition expires instead of silently mislabeling a new residual.

Merge semantics
---------------

:func:`apply_dispositions` annotates matching mismatch rows with their
disposition and adds ``summary.dispositioned``::

    raw_match_rate    match_count / comparison_count
    explained_rate    (match_count + explained rows) / comparison_count,
                      where explained = explained_residual,
                      upstream_engine_gap, bridge_artifact
    unexplained_count mismatch_count minus rows classified as any of the
                      four explanatory kinds (axiom_encoding_gap counts as
                      classified but never as explained)

The result is additive over ``axiom.comparison_report.v2``; merged reports
are stamped ``axiom.comparison_report.v2.1``. Reports that slim their
mismatch rows for the dashboard should merge dispositions before slimming so
counts cover the full row set.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import yaml

DISPOSITIONS_SCHEMA_VERSION = "axiom_oracles.dispositions.v1"
DISPOSITIONED_REPORT_SCHEMA_VERSION = "axiom.comparison_report.v2.1"

EXPLAINED_DISPOSITION_KINDS = (
    "explained_residual",
    "upstream_engine_gap",
    "bridge_artifact",
)
CLASSIFIED_DISPOSITION_KINDS = EXPLAINED_DISPOSITION_KINDS + (
    "axiom_encoding_gap",
)
DISPOSITION_KINDS = CLASSIFIED_DISPOSITION_KINDS + ("unexplained",)

DEFAULT_ARITHMETIC_TOLERANCE = 0.005
DEFAULT_PIN_TOLERANCE = 0.005

_ENTRY_KEYS = {
    "id",
    "concept",
    "case_id",
    "case_selector",
    "kind",
    "disposition",
    "evidence",
    "linked_issue",
    "expires_on_source_change",
    "pinned",
    "selector_binding",
    "notes",
}
_EVIDENCE_KEYS = {"mechanism", "arithmetic", "upstream_url", "sources"}
_SELECTOR_KEYS = {"case_ids", "case_id_prefix"}
_PINNED_KEYS = {"left", "right", "difference"}


class DispositionError(ValueError):
    """A dispositions file failed schema validation."""

    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = list(errors)
        details = "\n".join(f"  - {error}" for error in self.errors)
        super().__init__(f"invalid dispositions file {path}:\n{details}")


class ArithmeticEvaluationError(ValueError):
    """An evidence arithmetic expression could not be evaluated safely."""


def evaluate_arithmetic(expression: str) -> float:
    """Evaluate a plain arithmetic expression (numbers, ``+ - * /``, parens).

    Anything else — names, calls, comparisons — raises
    :class:`ArithmeticEvaluationError`. Evidence must be checkable without
    executing code.
    """

    try:
        tree = ast.parse(str(expression), mode="eval")
    except SyntaxError as exc:
        raise ArithmeticEvaluationError(
            f"invalid arithmetic expression {expression!r}: {exc.msg}"
        ) from exc

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, ast.USub | ast.UAdd
        ):
            value = _eval(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int | float)
            and not isinstance(node.value, bool)
        ):
            return float(node.value)
        raise ArithmeticEvaluationError(
            f"unsupported syntax in arithmetic expression {expression!r}; "
            "only numbers, + - * /, and parentheses are allowed"
        )

    return _eval(tree)


def _is_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _validate_arithmetic(items: object, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(items, list) or not items:
        return [f"{label}: evidence.arithmetic must be a non-empty list"]
    for index, item in enumerate(items):
        item_label = f"{label}: evidence.arithmetic[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label} must be a mapping")
            continue
        unknown = set(item) - {"expression", "equals", "tolerance"}
        if unknown:
            errors.append(
                f"{item_label} has unknown keys: {sorted(unknown)}"
            )
        expression = item.get("expression")
        equals = item.get("equals")
        tolerance = item.get("tolerance", DEFAULT_ARITHMETIC_TOLERANCE)
        if not isinstance(expression, str) or not expression.strip():
            errors.append(f"{item_label} needs a non-empty expression")
            continue
        if not isinstance(equals, int | float) or isinstance(equals, bool):
            errors.append(f"{item_label} needs a numeric `equals` value")
            continue
        if (
            not isinstance(tolerance, int | float)
            or isinstance(tolerance, bool)
            or tolerance < 0
        ):
            errors.append(f"{item_label} tolerance must be >= 0")
            continue
        try:
            result = evaluate_arithmetic(expression)
        except ArithmeticEvaluationError as exc:
            errors.append(f"{item_label}: {exc}")
            continue
        if abs(result - float(equals)) > float(tolerance):
            errors.append(
                f"{item_label} does not reconcile: {expression} = "
                f"{result:.6f}, expected {equals} "
                f"(tolerance {tolerance})"
            )
    return errors


def _validate_sources(
    sources: object,
    label: str,
    repo_root: Path | None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(sources, list) or not sources:
        return [f"{label}: evidence.sources must be a non-empty list"]
    for index, source in enumerate(sources):
        source_label = f"{label}: evidence.sources[{index}]"
        if not isinstance(source, str) or not source.strip():
            errors.append(f"{source_label} must be a non-empty string")
            continue
        if _is_url(source):
            continue
        relative = source.split("#", 1)[0]
        if Path(relative).is_absolute():
            errors.append(
                f"{source_label} must be repo-relative or a URL: {source}"
            )
            continue
        if repo_root is not None and not (repo_root / relative).exists():
            errors.append(
                f"{source_label} cites a missing file: {relative}"
            )
    return errors


def _validate_entry(
    entry: object,
    index: int,
    seen_ids: set[str],
    repo_root: Path | None,
) -> list[str]:
    label = f"entries[{index}]"
    if not isinstance(entry, dict):
        return [f"{label} must be a mapping"]
    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id.strip():
        label = f"entries[{index}] ({entry_id})"

    errors: list[str] = []
    unknown = set(entry) - _ENTRY_KEYS
    if unknown:
        errors.append(f"{label} has unknown keys: {sorted(unknown)}")

    if not isinstance(entry_id, str) or not entry_id.strip():
        errors.append(f"{label} needs a non-empty string `id`")
    elif entry_id in seen_ids:
        errors.append(f"{label} duplicates entry id {entry_id!r}")
    else:
        seen_ids.add(entry_id)

    concept = entry.get("concept")
    if not isinstance(concept, str) or "#" not in concept:
        errors.append(
            f"{label} needs a `concept` id of the form module#output"
        )

    case_id = entry.get("case_id")
    case_selector = entry.get("case_selector")
    if (case_id is None) == (case_selector is None):
        errors.append(
            f"{label} needs exactly one of `case_id` or `case_selector`"
        )
    if case_id is not None and (
        not isinstance(case_id, str | int) or str(case_id).strip() == ""
    ):
        errors.append(f"{label} `case_id` must be a non-empty scalar")
    if case_selector is not None:
        if not isinstance(case_selector, dict) or not case_selector:
            errors.append(f"{label} `case_selector` must be a mapping")
        else:
            unknown_selector = set(case_selector) - _SELECTOR_KEYS
            if unknown_selector:
                errors.append(
                    f"{label} case_selector has unknown keys: "
                    f"{sorted(unknown_selector)}"
                )
            case_ids = case_selector.get("case_ids")
            if case_ids is not None and (
                not isinstance(case_ids, list) or not case_ids
            ):
                errors.append(
                    f"{label} case_selector.case_ids must be a "
                    "non-empty list"
                )
            prefix = case_selector.get("case_id_prefix")
            if prefix is not None and (
                not isinstance(prefix, str) or not prefix
            ):
                errors.append(
                    f"{label} case_selector.case_id_prefix must be a "
                    "non-empty string"
                )
            if not (case_ids or prefix):
                errors.append(
                    f"{label} case_selector needs case_ids or "
                    "case_id_prefix"
                )

    kind = entry.get("kind")
    if kind is not None and (not isinstance(kind, str) or not kind.strip()):
        errors.append(f"{label} `kind` must be a non-empty string")

    disposition = entry.get("disposition")
    if disposition not in DISPOSITION_KINDS:
        errors.append(
            f"{label} disposition must be one of "
            f"{', '.join(DISPOSITION_KINDS)}; got {disposition!r}"
        )

    expires = entry.get("expires_on_source_change")
    if not isinstance(expires, bool):
        errors.append(
            f"{label} needs `expires_on_source_change` as a boolean"
        )

    selector_binding = entry.get("selector_binding")
    if selector_binding is not None:
        if case_selector is None:
            errors.append(
                f"{label} `selector_binding` requires a `case_selector`"
            )
        if not isinstance(selector_binding, dict) or set(
            selector_binding
        ) != {"units", "abs_difference_sum"}:
            errors.append(
                f"{label} `selector_binding` must be a mapping with exactly "
                "the keys `units` and `abs_difference_sum`"
            )
        else:
            if not isinstance(selector_binding["units"], int):
                errors.append(
                    f"{label} selector_binding.units must be an integer"
                )
            if not isinstance(
                selector_binding["abs_difference_sum"], int | float
            ):
                errors.append(
                    f"{label} selector_binding.abs_difference_sum must be "
                    "a number"
                )

    pinned = entry.get("pinned")
    if pinned is not None:
        if case_id is None:
            errors.append(
                f"{label} `pinned` values require a single `case_id`"
            )
        if not isinstance(pinned, dict) or not pinned:
            errors.append(f"{label} `pinned` must be a non-empty mapping")
        else:
            unknown_pin = set(pinned) - _PINNED_KEYS
            if unknown_pin:
                errors.append(
                    f"{label} pinned has unknown keys: {sorted(unknown_pin)}"
                )
            for key, value in pinned.items():
                if key in _PINNED_KEYS and not isinstance(
                    value, int | float | bool
                ):
                    errors.append(
                        f"{label} pinned.{key} must be numeric or boolean"
                    )

    linked_issue = entry.get("linked_issue")
    if linked_issue is not None and not _is_url(linked_issue):
        errors.append(f"{label} linked_issue must be an http(s) URL")

    evidence = entry.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        errors.append(
            f"{label} needs an `evidence` mapping — a disposition "
            "without evidence is invalid"
        )
        return errors

    unknown_evidence = set(evidence) - _EVIDENCE_KEYS
    if unknown_evidence:
        errors.append(
            f"{label} evidence has unknown keys: {sorted(unknown_evidence)}"
        )
    mechanism = evidence.get("mechanism")
    if not isinstance(mechanism, str) or not mechanism.strip():
        errors.append(
            f"{label} evidence needs a non-empty `mechanism` description"
        )
    arithmetic = evidence.get("arithmetic")
    if arithmetic is not None:
        errors.extend(_validate_arithmetic(arithmetic, label))
    upstream_url = evidence.get("upstream_url")
    if upstream_url is not None and not _is_url(upstream_url):
        errors.append(f"{label} evidence.upstream_url must be an http(s) URL")
    sources = evidence.get("sources")
    if sources is not None:
        errors.extend(_validate_sources(sources, label, repo_root))

    has_reconciliation = bool(arithmetic)
    has_citation = bool(upstream_url) or bool(linked_issue) or bool(sources)
    if not has_reconciliation and not has_citation:
        errors.append(
            f"{label} evidence needs arithmetic that reconciles or an "
            "upstream citation (evidence.upstream_url, linked_issue, or "
            "evidence.sources)"
        )
    return errors


def validate_dispositions(
    data: object,
    *,
    path_label: str = "<dispositions>",
    expected_suite: str | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Return every schema violation in a parsed dispositions document."""

    if not isinstance(data, dict):
        return [f"{path_label}: document must be a mapping"]
    errors: list[str] = []
    schema = data.get("schema")
    if schema != DISPOSITIONS_SCHEMA_VERSION:
        errors.append(
            f"schema must be {DISPOSITIONS_SCHEMA_VERSION!r}; got {schema!r}"
        )
    suite = data.get("suite")
    if not isinstance(suite, str) or not suite.strip():
        errors.append("suite must be a non-empty string")
    elif expected_suite is not None and suite != expected_suite:
        errors.append(
            f"suite {suite!r} does not match the file name "
            f"({expected_suite!r})"
        )
    unknown = set(data) - {"schema", "suite", "updated", "entries"}
    if unknown:
        errors.append(f"document has unknown keys: {sorted(unknown)}")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("entries must be a non-empty list")
        return errors
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        errors.extend(_validate_entry(entry, index, seen_ids, repo_root))
    return errors


def load_dispositions(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> dict:
    """Load and validate one ``dispositions/<suite>.yaml`` file."""

    data = yaml.safe_load(path.read_text())
    errors = validate_dispositions(
        data,
        path_label=str(path),
        expected_suite=path.stem,
        repo_root=repo_root,
    )
    if errors:
        raise DispositionError(str(path), errors)
    return data


def dispositions_path_for_suite(
    dispositions_dir: Path,
    suite: str | None,
) -> Path | None:
    if not suite:
        return None
    candidate = dispositions_dir / f"{suite}.yaml"
    return candidate if candidate.exists() else None


def _pin_matches(pinned: dict | None, row: dict) -> bool:
    if not pinned:
        return True
    for key, expected in pinned.items():
        live = row.get(key)
        if isinstance(expected, bool) or isinstance(live, bool):
            if bool(live) != bool(expected):
                return False
        elif isinstance(expected, int | float) and isinstance(
            live, int | float
        ):
            if abs(float(live) - float(expected)) > DEFAULT_PIN_TOLERANCE:
                return False
        elif live != expected:
            return False
    return True


def _entry_selects_row(entry: dict, row: dict) -> bool:
    if entry.get("concept") != row.get("concept"):
        return False
    kind = entry.get("kind")
    if kind is not None and row.get("kind") != kind:
        return False
    row_case = str(row.get("case_id"))
    case_id = entry.get("case_id")
    if case_id is not None:
        return row_case == str(case_id)
    selector = entry.get("case_selector") or {}
    case_ids = selector.get("case_ids")
    if case_ids is not None and row_case not in {
        str(value) for value in case_ids
    }:
        return False
    prefix = selector.get("case_id_prefix")
    if prefix is not None and not row_case.startswith(prefix):
        return False
    return True


def _percentage(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0
    value = round(numerator / denominator * 100, 6)
    return int(value) if float(value).is_integer() else value


def apply_dispositions(
    report: dict,
    dispositions: dict | None,
    *,
    dispositions_file: str | None = None,
) -> dict:
    """Join dispositions into a v2 comparison report (additive, v2.1).

    Returns a new report dict. Matching mismatch rows gain a ``disposition``
    annotation; ``summary.dispositioned`` carries the raw and explained
    rates. Entries whose pinned values no longer match the live row — or
    that match no live row at all — with ``expires_on_source_change: true``
    are listed as expired; non-expiring entries that match nothing are
    listed as orphaned (delete them when their mismatch clears).
    """

    merged = dict(report)
    summary = dict(report.get("summary") or {})
    comparison_count = summary.get("comparison_count") or 0
    match_count = summary.get("match_count") or 0
    mismatch_count = summary.get("mismatch_count") or 0

    entries = list((dispositions or {}).get("entries") or [])
    counts = {kind: 0 for kind in DISPOSITION_KINDS}
    applied_rows = 0
    entry_applied = {str(entry.get("id")): 0 for entry in entries}
    entry_pin_failed = {str(entry.get("id")): 0 for entry in entries}
    entry_abs_diff_sum = {str(entry.get("id")): 0.0 for entry in entries}
    entry_by_id = {str(entry.get("id")): entry for entry in entries}

    # Pass 1 — tentative assignment. Rows are matched to their winning entry
    # but not yet annotated, so selector-level value bindings can be checked
    # against the FULL selected population before any annotation lands.
    row_winner: list[str | None] = []
    source_rows = list(report.get("mismatches") or [])
    for row in source_rows:
        winner = None
        for entry in entries:
            if not _entry_selects_row(entry, row):
                continue
            entry_id = str(entry.get("id"))
            if not _pin_matches(entry.get("pinned"), row):
                entry_pin_failed[entry_id] += 1
                continue
            winner = entry_id
            entry_applied[entry_id] += 1
            diff = row.get("difference")
            if isinstance(diff, int | float):
                entry_abs_diff_sum[entry_id] += abs(float(diff))
            break
        row_winner.append(winner)

    # Selector-binding validation (sol closing review F4): an entry whose
    # binding no longer matches its live selected population — unit count or
    # summed |difference| drifted — has its declared mechanism basis changed
    # by a source change. Per ``expires_on_source_change`` semantics the
    # entry EXPIRES and its rows return to unexplained; the drift can never
    # ride an old classification.
    binding_violated: set[str] = set()
    for entry in entries:
        entry_id = str(entry.get("id"))
        binding = entry.get("selector_binding")
        if not binding or entry_applied[entry_id] == 0:
            continue
        units_match = entry_applied[entry_id] == binding["units"]
        sum_match = (
            abs(entry_abs_diff_sum[entry_id] - float(binding["abs_difference_sum"]))
            <= 1e-9
        )
        if not (units_match and sum_match):
            binding_violated.add(entry_id)

    # Pass 2 — annotate, skipping entries whose binding was violated.
    annotated_mismatches = []
    for row, winner in zip(source_rows, row_winner):
        annotated = dict(row)
        if winner is not None and winner not in binding_violated:
            entry = entry_by_id[winner]
            disposition_kind = entry["disposition"]
            annotation = {
                "id": winner,
                "disposition": disposition_kind,
            }
            if entry.get("linked_issue"):
                annotation["linked_issue"] = entry["linked_issue"]
            annotated["disposition"] = annotation
            counts[disposition_kind] += 1
            applied_rows += 1
        annotated_mismatches.append(annotated)

    expired = []
    orphaned = []
    for entry in entries:
        entry_id = str(entry.get("id"))
        if entry_id in binding_violated:
            expired.append(entry_id)
            continue
        if entry_applied[entry_id] > 0:
            continue
        if entry.get("expires_on_source_change"):
            expired.append(entry_id)
        else:
            orphaned.append(entry_id)

    explained_rows = sum(
        counts[kind] for kind in EXPLAINED_DISPOSITION_KINDS
    )
    classified_rows = sum(
        counts[kind] for kind in CLASSIFIED_DISPOSITION_KINDS
    )
    summary["dispositioned"] = {
        "schema_version": DISPOSITIONS_SCHEMA_VERSION,
        "dispositions_file": dispositions_file,
        "raw_match_rate": _percentage(match_count, comparison_count),
        "explained_rate": _percentage(
            match_count + explained_rows, comparison_count
        ),
        "unexplained_count": max(mismatch_count - classified_rows, 0),
        "counts": counts,
        "expired_entries": expired,
        "orphaned_entries": orphaned,
    }
    if binding_violated:
        summary["dispositioned"]["binding_violated_entries"] = sorted(
            binding_violated
        )
    merged["summary"] = summary
    merged["mismatches"] = annotated_mismatches
    if report.get("schema_version") == "axiom.comparison_report.v2":
        merged["schema_version"] = DISPOSITIONED_REPORT_SCHEMA_VERSION
    return merged


def assignment_digest(report: dict) -> str:
    """SHA-256 over the complete per-row disposition assignment.

    Serializes ``[case_id, concept, entry_id | None, disposition | None]``
    for EVERY mismatch row of a merged report as a canonically sorted JSON
    list and hashes it. Aggregate counts cannot distinguish two entries of
    equal cardinality swapping disposition classes; this digest can, so a
    premerged-slim dashboard block that embeds it is bound to the exact
    row-level assignment a fresh merge over the full report produces (sol
    stack review r2, F2 residual). A sorted LIST — never a mapping keyed
    by case_id — because a case validly carries one mismatch row per
    concept, and a map would let same-case rows overwrite each other,
    hiding count-preserving reclassifications among them (sol stack
    review r3).
    """

    assignment: list[list[str | None]] = []
    for row in report.get("mismatches") or []:
        annotation = row.get("disposition")
        entry_id, disposition = (
            (str(annotation.get("id")), str(annotation.get("disposition")))
            if isinstance(annotation, dict)
            else (None, None)
        )
        assignment.append(
            [
                str(row.get("case_id")),
                str(row.get("concept")),
                entry_id,
                disposition,
            ]
        )
    assignment.sort(key=lambda item: [part or "" for part in item])
    payload = json.dumps(assignment, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_dispositions_from_dir(
    report: dict,
    dispositions_dir: Path,
    *,
    repo_root: Path | None = None,
) -> dict:
    """Merge ``dispositions/<suite>.yaml`` into ``report`` when it exists.

    Reports for suites without a dispositions file still gain the
    ``summary.dispositioned`` block (explained rate equals the raw rate), so
    every dashboard summary carries both rates.
    """

    path = dispositions_path_for_suite(
        dispositions_dir, report.get("suite")
    )
    if path is None:
        return apply_dispositions(report, None)
    dispositions = load_dispositions(path, repo_root=repo_root)
    root = repo_root if repo_root is not None else dispositions_dir.parent
    try:
        label = str(path.relative_to(root))
    except ValueError:
        label = str(path)
    return apply_dispositions(
        report, dispositions, dispositions_file=label
    )


def dispositioned_rollup(reports: list[dict]) -> dict:
    """Aggregate raw and explained parity across merged reports.

    Feeds coverage summaries (e.g. the Belgium EUROMOD lane) so a lane-level
    surface can show both rates next to its per-suite runs.
    """

    comparison_count = 0
    match_count = 0
    explained_mismatches = 0
    unexplained_count = 0
    suites = []
    for report in reports:
        summary = report.get("summary") or {}
        block = summary.get("dispositioned") or {}
        comparisons = summary.get("comparison_count") or 0
        matches = summary.get("match_count") or 0
        counts = block.get("counts") or {}
        comparison_count += comparisons
        match_count += matches
        explained_mismatches += sum(
            counts.get(kind, 0) for kind in EXPLAINED_DISPOSITION_KINDS
        )
        if "unexplained_count" in block:
            unexplained_count += block["unexplained_count"]
        else:
            unexplained_count += summary.get("mismatch_count") or 0
        if report.get("suite"):
            suites.append(report["suite"])
    return {
        "suites": sorted(suites),
        "comparison_count": comparison_count,
        "match_count": match_count,
        "raw_match_rate": _percentage(match_count, comparison_count),
        "explained_rate": _percentage(
            match_count + explained_mismatches, comparison_count
        ),
        "unexplained_count": unexplained_count,
    }


def report_json_text(report: dict) -> str:
    """Serialize a dashboard report in ``write_json``'s on-disk format.

    Mirrors :meth:`ComparisonReportAccumulator.write_json` — top-level keys
    sorted with ``cases`` streamed last — so rewriting a checked-in report to
    add disposition annotations produces a minimal diff.
    """

    from .report import _indented_json, _top_level_json_entry

    lines = ["{\n"]
    for key in sorted(key for key in report if key != "cases"):
        lines.append(_top_level_json_entry(key, report[key]))
        lines.append(",\n")
    lines.append(f'  {json.dumps("cases")}: [')
    wrote_case = False
    for row in report.get("cases") or []:
        lines.append(",\n" if wrote_case else "\n")
        lines.append(_indented_json(row, 4))
        wrote_case = True
    if wrote_case:
        lines.append("\n")
    lines.append("  ]\n}\n")
    return "".join(lines)
