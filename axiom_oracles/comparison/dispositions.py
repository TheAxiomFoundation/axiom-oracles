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
        case_id: be-worker-ssc-30k   # or case_selector / signatures / match
        disposition: upstream_engine_gap
        attribution: euromod          # optional here; see lane rules below
        evidence:
          mechanism: >-
            EUROMOD BE_2025 applies the February-onward 2025 work-bonus
            table to all 12 months; the statutory path weights January
            separately.
          arithmetic:
            - expression: "3398.52 - 3386.87"
              equals: 11.65
          row_arithmetic:             # checked on EVERY selected row
            - expression: "left - right"
              equals: 11.65
              tolerance: 0.01
          upstream_url: https://github.com/ec-jrc/...
          sources:
            - axiom_oracles/data/euromod_issues.json#...
        linked_issue: https://github.com/ec-jrc/...
        expires_on_source_change: true
        pinned:
          left: 3398.5199999999995
          right: 3386.87

The schema id stays ``v1``: every field added since is optional for suites
outside the TAXSIM lane, so every pre-existing file validates unchanged and
the lane-specific requirements below key off the suite's engines rather than
a schema bump.

Selectors — exactly one per entry, always scoped by the entry's ``concept``
(and optional ``kind``):

* ``case_id`` — one mismatch row.
* ``case_selector`` — ``{case_ids: [...]}`` and/or ``{case_id_prefix: ...}``.
* ``signatures`` — rows whose :func:`.selectors.row_signature` (a stamped
  ``signature`` field, else :func:`.selectors.mismatch_signature` over
  ``{concept, kind, delta, facts, error_signature}``) is listed.
* ``match`` — a structured selector over row fields (``kind``,
  ``facts.<name>``, ``delta``, ``left``, ``right``, ``error_signature``,
  ``error_engine``); see :mod:`.selectors`. Universal selectors and
  selectors bounded only by concept/kind are rejected.

Validation rules (enforced in CI via ``scripts/apply_dispositions.py
--check`` and unit tests):

* Every entry MUST carry ``evidence`` with a non-empty ``mechanism`` AND at
  least one of (a) ``arithmetic`` items that reconcile numerically,
  (b) ``row_arithmetic`` items, or (c) an upstream citation
  (``evidence.upstream_url``, ``linked_issue``, or a ``evidence.sources``
  item). A disposition without evidence is invalid — classifications must
  reconcile, not assert.
* ``arithmetic`` items are ``{expression, equals[, tolerance]}``. The
  expression is evaluated with a restricted arithmetic evaluator (numbers,
  ``+ - * /``, parentheses) and must equal ``equals`` within ``tolerance``
  (default ``0.005``). An arithmetic claim that does not reconcile fails
  validation — the Wallonia lesson.
* ``row_arithmetic`` items are ``{expression, equals[, tolerance]}`` whose
  expression references at least one row variable — ``left``, ``right``,
  ``difference`` (signed ``left - right``), or ``facts.<name>`` (dotted fact
  names are dictionary lookups, never attribute access; calls stay
  forbidden). ``equals`` is a number or a non-empty list of numbers (the row
  passes when it equals any of them). They are evaluated at merge time on
  every selected row; one failing row expires the entry with reason
  ``row_arithmetic_failed`` and fails ``apply_dispositions.py --check``.
* ``evidence.sources`` entries that are not URLs must be repo-relative paths
  (an optional ``#fragment`` may name an entry inside the file) and the file
  must exist, so citations cannot dangle.
* ``expires_on_source_change`` is required. When true and the entry carries
  ``pinned`` engine values, the disposition only applies while the live
  mismatch row still shows those values; when the source engines change, the
  disposition expires instead of silently mislabeling a new residual.
* ``selector_binding`` (``case_selector``, ``signatures`` or ``match``
  entries) is either ``{units, rows_sha256}`` (:func:`selected_rows_sha256`
  over identity plus exact values) or, for ``signatures`` entries, ``{units,
  signature_population_sha256}`` (:func:`.selectors.signature_population_sha256`
  over the selected rows' ``(signature, multiplicity)`` pairs). Drift expires
  the entry (``selector_binding_violated``).
* ``attribution`` names who owns the residual. Allowed values are the engine
  names of the suite's two sides (``runner.parameters.left``/``right`` in
  ``comparisons/<suite>.yaml``; the repo's engine adapter names when the
  suite declares no sides) plus ``convention``, ``input`` and
  ``two_sided``. An unknown value is invalid wherever it appears.
* ``oracle_binding`` records the oracle identity a classification was made
  against: ``taxsim_binary_sha256`` (non-empty list of 64-hex digests),
  ``policyengine_taxsim`` (package version string), and/or
  ``identity_unrecorded: true`` (the classifying report recorded no TAXSIM
  identity at all). See :func:`report_oracle_identity` for how a report's
  identity is read and :func:`oracle_binding_mismatch` for the match rule.

TAXSIM lanes (a suite with ``taxsim`` on either side) additionally require,
on every entry:

* ``attribution`` (target vocabulary for the PE-vs-TAXSIM emulator lane:
  ``taxsim | policyengine | convention | input | two_sided``);
* ``oracle_binding`` — re-pinning TAXSIM expires the classification;
* ``selector_binding`` on every ``case_selector``/``signatures``/``match``
  entry, and ``pinned`` ``left`` and ``right`` on every ``case_id`` entry
  (``null`` pins the missing value of an engine-error row);
* ``row_arithmetic`` or an upstream citation — constant-only
  ``evidence.arithmetic`` no longer counts as reconciliation there;
* classification conservation at merge time: a mismatch row selected by
  more than one entry raises :class:`DispositionConservationError` (outside
  TAXSIM lanes the first entry still wins silently).

Suites whose two sides are both external engines (no ``axiom`` side)
require ``attribution`` on every ``upstream_engine_gap`` entry: "upstream"
is otherwise ambiguous.

Merge semantics
---------------

:func:`apply_dispositions` annotates matching mismatch rows with their
disposition and adds ``summary.dispositioned``::

    raw_match_rate    match_count / comparison_count
    explained_rate    (match_count + classified rows) / comparison_count,
                      where classified = explained_residual,
                      upstream_engine_gap, bridge_artifact, and
                      axiom_encoding_gap — a bug we can name, reproduce,
                      and have filed upstream IS explained (owner
                      decision, 2026-08-24); the encoding-gap count stays
                      broken out in ``counts`` so our own open bugs
                      remain visible until fixed
    unexplained_count mismatch_count minus rows classified as any of the
                      four explanatory kinds
    expired_entries   entries that stopped applying; when non-empty,
                      ``expired_reasons`` maps each to a reason code
                      (:data:`EXPIRY_REASONS`)

The result is additive over ``axiom.comparison_report.v2``; merged reports
are stamped ``axiom.comparison_report.v2.1``. Reports that slim their
mismatch rows for the dashboard should merge dispositions before slimming so
counts cover the full row set.
"""

from __future__ import annotations

import hashlib
import json
import math
import pkgutil
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .selectors import (
    ArithmeticEvaluationError,
    evaluate_expression,
    expression_variables,
    match_row,
    row_signature,
    row_variables,
    signature_population,
    signature_population_sha256,
    validate_match,
)

__all__ = [
    "ArithmeticEvaluationError",
    "DispositionConservationError",
    "DispositionError",
    "SuiteContext",
    "apply_dispositions",
    "apply_dispositions_from_dir",
    "assignment_digest",
    "dispositioned_rollup",
    "evaluate_arithmetic",
    "load_dispositions",
    "oracle_binding_mismatch",
    "report_is_taxsim_lane",
    "report_oracle_identity",
    "selected_rows_sha256",
    "suite_context",
    "validate_dispositions",
]

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

#: Attribution values allowed on every suite besides its engine names.
ATTRIBUTION_NON_ENGINE_VALUES = ("convention", "input", "two_sided")
TAXSIM_ENGINE = "taxsim"
AXIOM_ENGINE = "axiom"

#: Reason codes recorded in ``summary.dispositioned.expired_reasons``.
EXPIRY_REASONS = (
    "no_live_rows",
    "pinned_values_changed",
    "selector_binding_violated",
    "oracle_binding_missing",
    "oracle_identity_changed",
    "oracle_identity_unrecorded",
    "oracle_identity_malformed",
    "row_arithmetic_failed",
)

DEFAULT_ARITHMETIC_TOLERANCE = 0.005
DEFAULT_PIN_TOLERANCE = 0.005

_ENTRY_KEYS = {
    "id",
    "concept",
    "case_id",
    "case_selector",
    "signatures",
    "match",
    "kind",
    "disposition",
    "evidence",
    "linked_issue",
    "expires_on_source_change",
    "pinned",
    "selector_binding",
    "oracle_binding",
    "notes",
    "attribution",
    "receipt",
    "reason",
    "comment",
}
_EVIDENCE_KEYS = {
    "mechanism", "arithmetic", "row_arithmetic", "upstream_url", "sources",
    "receipt_type", "instrument_receipt",
}
_SELECTOR_KEYS = {"case_ids", "case_id_prefix"}
_PINNED_KEYS = {"left", "right", "difference"}
_BINDING_KEY_SETS = (
    frozenset({"units", "rows_sha256"}),
    frozenset({"units", "signature_population_sha256"}),
)
_ORACLE_BINDING_KEYS = {
    "taxsim_binary_sha256",
    "policyengine_taxsim",
    "identity_unrecorded",
}
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SELECTOR_FIELDS = ("case_id", "case_selector", "signatures", "match")


class DispositionError(ValueError):
    """A dispositions file failed schema validation."""

    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = list(errors)
        details = "\n".join(f"  - {error}" for error in self.errors)
        super().__init__(f"invalid dispositions file {path}:\n{details}")


class DispositionConservationError(DispositionError):
    """A TAXSIM-lane mismatch row was claimed by more than one entry."""


def evaluate_arithmetic(expression: str) -> float:
    """Evaluate a plain arithmetic expression (numbers, ``+ - * /``, parens).

    Anything else — names, calls, comparisons — raises
    :class:`ArithmeticEvaluationError`. Evidence must be checkable without
    executing code.
    """

    return evaluate_expression(expression, None)


def _is_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _is_number(value: object) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


# ---------------------------------------------------------------------------
# Suite context (which engines sit on the suite's two sides)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def adapter_engine_names() -> frozenset[str]:
    """Engine adapter package names shipped in ``axiom_oracles.adapters``.

    The fallback attribution vocabulary for suites whose comparison config
    declares no ``left``/``right`` sides.
    """

    adapters_dir = Path(__file__).resolve().parent.parent / "adapters"
    return frozenset(
        module.name
        for module in pkgutil.iter_modules([str(adapters_dir)])
        if module.ispkg
    )


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=4)
def _comparison_sides_index(
    comparisons_dir: str,
) -> dict[str, frozenset[tuple[str, str]]]:
    """suite name -> the (left, right) engine pairs its configs declare.

    A config is indexed under its file stem, ``name``, ``dashboard.suite``
    and ``runner.parameters.suite`` — the names a report's ``suite`` field
    can carry. Only configs declaring both ``runner.parameters.left`` and
    ``right`` contribute.
    """

    index: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(Path(comparisons_dir).glob("*.yaml")):
        try:
            text = path.read_text()
        except OSError:
            continue
        try:
            config = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if not isinstance(config, dict):
            continue
        runner = _mapping(config.get("runner"))
        params = _mapping(runner.get("parameters"))
        left, right = params.get("left"), params.get("right")
        if not (isinstance(left, str) and isinstance(right, str)):
            continue
        dashboard = _mapping(config.get("dashboard"))
        names = {
            path.stem,
            config.get("name"),
            dashboard.get("suite"),
            params.get("suite"),
        }
        for name in names:
            if isinstance(name, str) and name:
                index.setdefault(name, set()).add((left, right))
    return {name: frozenset(pairs) for name, pairs in index.items()}


@dataclass(frozen=True)
class SuiteContext:
    """What validation knows about the suite a dispositions file classifies.

    ``engines`` is the set of engine names on the suite's two sides, or
    ``None`` when no comparison config declares them (sides unknown).
    """

    suite: str | None
    engines: frozenset[str] | None = None

    @property
    def taxsim_lane(self) -> bool:
        return self.engines is not None and TAXSIM_ENGINE in self.engines

    @property
    def external_only(self) -> bool:
        """Both sides are external engines (no Axiom side)."""

        return self.engines is not None and AXIOM_ENGINE not in self.engines

    def attribution_values(self) -> frozenset[str]:
        engines = self.engines if self.engines is not None else adapter_engine_names()
        return frozenset(engines) | frozenset(ATTRIBUTION_NON_ENGINE_VALUES)


def suite_context(
    suite: str | None,
    repo_root: Path | None,
    *,
    engines: Iterable[str] | None = None,
) -> SuiteContext:
    """Resolve a suite's engine sides from ``comparisons/<suite>.yaml``.

    ``engines`` overrides the lookup (tests, callers that already know the
    sides). Without a repo root or a config declaring sides the context is
    "sides unknown": attribution falls back to the adapter names and no
    lane-specific requirement applies.
    """

    if engines is not None:
        return SuiteContext(suite, frozenset(engines))
    if not suite or repo_root is None:
        return SuiteContext(suite, None)
    comparisons_dir = Path(repo_root) / "comparisons"
    if not comparisons_dir.is_dir():
        return SuiteContext(suite, None)
    pairs = _comparison_sides_index(str(comparisons_dir.resolve())).get(suite)
    if not pairs:
        return SuiteContext(suite, None)
    return SuiteContext(
        suite, frozenset(engine for pair in pairs for engine in pair)
    )


def report_is_taxsim_lane(report: Mapping[str, Any]) -> bool:
    """Whether a report compares TAXSIM on its left or right side."""

    engines = report.get("engines")
    if not isinstance(engines, Mapping):
        return False
    return TAXSIM_ENGINE in {engines.get("left"), engines.get("right")}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


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
        if not _is_number(equals):
            errors.append(f"{item_label} needs a numeric `equals` value")
            continue
        if not _is_number(tolerance) or tolerance < 0:
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


def _validate_row_arithmetic(items: object, label: str) -> list[str]:
    """Schema-check row arithmetic; the values are checked at merge time."""

    if not isinstance(items, list) or not items:
        return [f"{label}: evidence.row_arithmetic must be a non-empty list"]
    errors: list[str] = []
    for index, item in enumerate(items):
        item_label = f"{label}: evidence.row_arithmetic[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label} must be a mapping")
            continue
        unknown = set(item) - {"expression", "equals", "tolerance"}
        if unknown:
            errors.append(f"{item_label} has unknown keys: {sorted(unknown)}")
        expression = item.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            errors.append(f"{item_label} needs a non-empty expression")
        else:
            try:
                names = expression_variables(expression)
            except ArithmeticEvaluationError as exc:
                errors.append(f"{item_label}: {exc}")
            else:
                if not names:
                    errors.append(
                        f"{item_label} references no row variable (left, "
                        "right, difference, facts.<name>); constant claims "
                        "belong in evidence.arithmetic"
                    )
        equals = item.get("equals")
        if not (
            _is_number(equals)
            or (
                isinstance(equals, list)
                and equals
                and all(_is_number(value) for value in equals)
            )
        ):
            errors.append(
                f"{item_label} needs a numeric `equals` value or a non-empty "
                "list of them"
            )
        tolerance = item.get("tolerance", DEFAULT_ARITHMETIC_TOLERANCE)
        if not _is_number(tolerance) or tolerance < 0:
            errors.append(f"{item_label} tolerance must be >= 0")
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


def _validate_selector_binding(binding: object, label: str) -> list[str]:
    if not isinstance(binding, dict) or frozenset(binding) not in _BINDING_KEY_SETS:
        return [
            f"{label} `selector_binding` must be a mapping with exactly the "
            "keys `units` and `rows_sha256`, or `units` and "
            "`signature_population_sha256`"
        ]
    errors: list[str] = []
    units = binding["units"]
    if not isinstance(units, int) or isinstance(units, bool) or units < 1:
        errors.append(f"{label} selector_binding.units must be a positive integer")
    digest_key = (
        "rows_sha256" if "rows_sha256" in binding else "signature_population_sha256"
    )
    digest = binding[digest_key]
    if not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
        errors.append(
            f"{label} selector_binding.{digest_key} must be a "
            "64-char lowercase hex sha256"
        )
    return errors


def _validate_oracle_binding(binding: object, label: str) -> list[str]:
    if not isinstance(binding, dict) or not binding:
        return [f"{label} `oracle_binding` must be a non-empty mapping"]
    errors: list[str] = []
    unknown = set(binding) - _ORACLE_BINDING_KEYS
    if unknown:
        errors.append(f"{label} oracle_binding has unknown keys: {sorted(unknown)}")
    if not set(binding) & _ORACLE_BINDING_KEYS:
        errors.append(
            f"{label} oracle_binding needs taxsim_binary_sha256, "
            "policyengine_taxsim, or identity_unrecorded"
        )
    shas = binding.get("taxsim_binary_sha256")
    if "taxsim_binary_sha256" in binding and not (
        isinstance(shas, list)
        and shas
        and all(isinstance(sha, str) and _HEX64.fullmatch(sha) for sha in shas)
        and len(set(shas)) == len(shas)
    ):
        errors.append(
            f"{label} oracle_binding.taxsim_binary_sha256 must be a non-empty "
            "list of distinct 64-char lowercase hex digests"
        )
    version = binding.get("policyengine_taxsim")
    if "policyengine_taxsim" in binding and not (
        isinstance(version, str) and version.strip()
    ):
        errors.append(
            f"{label} oracle_binding.policyengine_taxsim must be a non-empty "
            "version string"
        )
    if "identity_unrecorded" in binding and binding["identity_unrecorded"] is not True:
        errors.append(
            f"{label} oracle_binding.identity_unrecorded may only be `true`"
        )
    return errors


def _validate_entry(
    entry: object,
    index: int,
    seen_ids: set[str],
    repo_root: Path | None,
    context: SuiteContext,
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
    signatures = entry.get("signatures")
    match = entry.get("match")
    if sum(entry.get(field) is not None for field in _SELECTOR_FIELDS) != 1:
        errors.append(
            f"{label} needs exactly one of `case_id`, `case_selector`, "
            "`signatures`, or `match`"
        )
    if signatures is not None and (
        not isinstance(signatures, list)
        or not signatures
        or any(not isinstance(value, str) or not value for value in signatures)
    ):
        errors.append(f"{label} `signatures` must be a list of non-empty strings")
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
    if match is not None:
        errors.extend(validate_match(match, f"{label} match"))

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

    multi_row = case_selector is not None or signatures is not None or match is not None
    selector_binding = entry.get("selector_binding")
    if selector_binding is not None:
        if not multi_row:
            errors.append(
                f"{label} `selector_binding` requires a `case_selector`, "
                "`signatures`, or `match` selector"
            )
        errors.extend(_validate_selector_binding(selector_binding, label))
        if (
            isinstance(selector_binding, dict)
            and "signature_population_sha256" in selector_binding
            and signatures is None
        ):
            errors.append(
                f"{label} signature_population_sha256 requires a `signatures` selector"
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
                if key in _PINNED_KEYS and not (
                    value is None or isinstance(value, bool) or _is_number(value)
                ):
                    errors.append(
                        f"{label} pinned.{key} must be finite numeric, boolean, or null"
                    )

    attribution = entry.get("attribution")
    allowed_attribution = context.attribution_values()
    if attribution is not None and (
        not isinstance(attribution, str) or attribution not in allowed_attribution
    ):
        errors.append(
            f"{label} attribution must be one of "
            f"{', '.join(sorted(allowed_attribution))}; got {attribution!r}"
        )
    if attribution is None and context.taxsim_lane:
        errors.append(
            f"{label} needs `attribution` (TAXSIM lane): one of "
            f"{', '.join(sorted(allowed_attribution))}"
        )
    elif (
        attribution is None
        and context.external_only
        and disposition == "upstream_engine_gap"
    ):
        errors.append(
            f"{label} needs `attribution`: both sides of this suite are "
            "external engines, so upstream_engine_gap must name which one "
            f"({', '.join(sorted(allowed_attribution))})"
        )

    oracle_binding = entry.get("oracle_binding")
    if oracle_binding is not None:
        errors.extend(_validate_oracle_binding(oracle_binding, label))

    if context.taxsim_lane:
        if oracle_binding is None:
            errors.append(
                f"{label} needs `oracle_binding` (TAXSIM lane): the TAXSIM "
                "identity the classification was made against"
            )
        if multi_row and selector_binding is None:
            errors.append(
                f"{label} needs `selector_binding` (TAXSIM lane): a "
                "multi-row selector must bind its selected population "
                "(scripts/bind_dispositions.py computes it)"
            )
        if case_id is not None and not (
            isinstance(pinned, dict) and {"left", "right"} <= set(pinned)
        ):
            errors.append(
                f"{label} needs `pinned` left and right values (TAXSIM lane "
                "single-row entry)"
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
    row_arithmetic = evidence.get("row_arithmetic")
    if row_arithmetic is not None:
        errors.extend(_validate_row_arithmetic(row_arithmetic, label))
    upstream_url = evidence.get("upstream_url")
    if upstream_url is not None and not _is_url(upstream_url):
        errors.append(f"{label} evidence.upstream_url must be an http(s) URL")
    sources = evidence.get("sources")
    if sources is not None:
        errors.extend(_validate_sources(sources, label, repo_root))

    has_citation = bool(upstream_url) or bool(linked_issue) or bool(sources)
    if context.taxsim_lane:
        if not row_arithmetic and not has_citation:
            errors.append(
                f"{label} evidence needs row_arithmetic or an upstream "
                "citation (evidence.upstream_url, linked_issue, or "
                "evidence.sources): in a TAXSIM lane constant-only "
                "evidence.arithmetic does not reconcile against the rows"
            )
    elif not (arithmetic or row_arithmetic) and not has_citation:
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
    suite_engines: Iterable[str] | None = None,
) -> list[str]:
    """Return every schema violation in a parsed dispositions document.

    Lane-specific rules need the suite's engine sides: pass
    ``suite_engines`` explicitly, or a ``repo_root`` whose
    ``comparisons/<suite>.yaml`` declares them.
    """

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
    context = suite_context(
        suite if isinstance(suite, str) else None,
        repo_root,
        engines=suite_engines,
    )
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        errors.extend(
            _validate_entry(entry, index, seen_ids, repo_root, context)
        )
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


# ---------------------------------------------------------------------------
# Population digests and oracle identity
# ---------------------------------------------------------------------------


def selected_rows_sha256(rows: list[dict]) -> str:
    """Canonical digest of a selected mismatch population.

    Sorted by case id; each row contributes its identity plus the exact
    ``left``/``right``/signed ``difference`` values, so any value movement —
    sign flips, balanced multi-row swaps, anything that preserves aggregates —
    changes the digest (sol closing review r2 finding 2). Auxiliary output
    evidence extends the row encoding only when ``aux`` is present, keeping
    pre-existing population bindings unchanged when it is absent.
    """
    canonical = sorted(
        [
            str(row.get("case_id")),
            str(row.get("concept")),
            json.dumps(row.get("left"), sort_keys=True),
            json.dumps(row.get("right"), sort_keys=True),
            json.dumps(row.get("difference"), sort_keys=True),
        ]
        + ([json.dumps(row["aux"], sort_keys=True)] if "aux" in row else [])
        for row in rows
    )
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def selection_binding(rows: list[dict], *, signature: bool = False) -> dict:
    """The ``selector_binding`` a selected population satisfies right now."""

    if signature:
        return {
            "units": len(rows),
            "signature_population_sha256": signature_population_sha256(
                signature_population(rows)
            ),
        }
    return {"units": len(rows), "rows_sha256": selected_rows_sha256(rows)}


def _population_binding_holds(binding: Mapping[str, Any], rows: list[dict]) -> bool:
    if binding.get("units") != len(rows):
        return False
    if "rows_sha256" in binding:
        return selected_rows_sha256(rows) == binding["rows_sha256"]
    try:
        digest = signature_population_sha256(signature_population(rows))
    except ValueError:
        return False
    return digest == binding.get("signature_population_sha256")


def report_oracle_identity(report: Mapping[str, Any]) -> dict[str, Any]:
    """The TAXSIM identity a report records (interface contract C1).

    Read in order: ``provenance.oracle.taxsim_binaries[*].sha256``, else
    ``engine_identity.taxsim.binaries[*].sha256`` (the CLI report shape),
    and independently ``provenance.oracle.policyengine_taxsim``. Returns
    ``{"source", "taxsim_binary_sha256", "policyengine_taxsim",
    "malformed"}``: ``taxsim_binary_sha256`` is a sorted list or ``None``
    when no binaries are recorded; ``malformed`` is true when a binary
    field is not a list, an item lacks a 64-hex ``sha256``, or the only
    recorded identity is an invalid version value. An unreadable identity
    binds nothing and never falls back to a lower-priority field.
    """

    provenance = report.get("provenance")
    oracle = provenance.get("oracle") if isinstance(provenance, Mapping) else None
    oracle = oracle if isinstance(oracle, Mapping) else {}
    source = None
    engine_identity = report.get("engine_identity")
    taxsim = (
        engine_identity.get("taxsim")
        if isinstance(engine_identity, Mapping)
        else None
    )
    taxsim = taxsim if isinstance(taxsim, Mapping) else {}
    binaries = None
    malformed = False
    for container, key, path in (
        (oracle, "taxsim_binaries", "provenance.oracle.taxsim_binaries"),
        (taxsim, "binaries", "engine_identity.taxsim.binaries"),
    ):
        if key not in container or container[key] == []:
            continue
        source = path
        candidate = container[key]
        if not isinstance(candidate, list):
            malformed = True
        else:
            binaries = candidate
        # A malformed higher-priority identity never falls back to a weaker one.
        break
    shas: list[str] | None = None
    if binaries is not None:
        collected = set()
        for binary in binaries:
            sha = binary.get("sha256") if isinstance(binary, Mapping) else None
            if isinstance(sha, str) and _HEX64.fullmatch(sha):
                collected.add(sha)
            else:
                malformed = True
        shas = sorted(collected)
    version = oracle.get("policyengine_taxsim")
    if not (isinstance(version, str) and version.strip()):
        if source is None and "policyengine_taxsim" in oracle:
            malformed = True
        version = None
    elif source is None:
        source = "provenance.oracle.policyengine_taxsim"
    return {
        "source": source,
        "taxsim_binary_sha256": shas,
        "policyengine_taxsim": version,
        "malformed": malformed,
    }


def row_binary_sha256(row: Mapping[str, Any]) -> str | None:
    """Per-row TAXSIM binary digest, when the row records one.

    Only engine-error rows carry it today, on the detail whose engine is
    ``taxsim`` (``row["error"]`` or its ``other_side`` detail, from the
    failing run's ``raw.taxsim_error``). Value rows do not, so a population
    of value rows falls back to the report-wide binary set.
    """

    error = row.get("error")
    if isinstance(error, Mapping):
        for detail in (error, error.get("other_side")):
            if not isinstance(detail, Mapping) or detail.get("engine") != TAXSIM_ENGINE:
                continue
            sha = detail.get("binary_sha256")
            if isinstance(sha, str) and _HEX64.fullmatch(sha):
                return sha
    return None


def oracle_binding_mismatch(
    binding: Mapping[str, Any],
    identity: Mapping[str, Any],
    rows: list[dict],
) -> str | None:
    """Why an ``oracle_binding`` does not hold for a report, or ``None``.

    The report's most specific recorded identity governs:

    1. Recorded TAXSIM binaries: the binding must list
       ``taxsim_binary_sha256``, and the binaries that actually ran on the
       entry's selected rows must be a subset of it. Per-row digests are
       used when EVERY selected row records one (engine-error rows);
       otherwise the report's whole recorded set must be a subset — a
       report that ran two binaries (e.g. a per-state fallback) therefore
       needs both listed unless the rows say which one they ran on.
    2. Else a recorded ``policyengine_taxsim`` version: the binding's
       version must equal it.
    3. Else nothing is recorded: only ``identity_unrecorded: true``
       matches. Such a legacy binding expires the moment a report records
       any identity, so re-pinning TAXSIM always expires it.
    """

    if identity.get("malformed"):
        return "oracle_identity_malformed"
    recorded_shas = identity.get("taxsim_binary_sha256")
    if recorded_shas is not None:
        allowed = binding.get("taxsim_binary_sha256")
        if not allowed:
            return "oracle_identity_changed"
        per_row = [row_binary_sha256(row) for row in rows]
        if per_row and all(per_row):
            relevant = set(per_row)
            if not relevant <= set(recorded_shas):
                return "oracle_identity_malformed"
        else:
            relevant = set(recorded_shas)
        return None if relevant <= set(allowed) else "oracle_identity_changed"
    version = identity.get("policyengine_taxsim")
    if version is not None:
        if binding.get("policyengine_taxsim") == version:
            return None
        return "oracle_identity_changed"
    if binding.get("identity_unrecorded") is True:
        return None
    return "oracle_identity_unrecorded"


def _row_arithmetic_holds(items: list[dict], rows: list[dict]) -> bool:
    for row in rows:
        variables = row_variables(row)
        for item in items:
            try:
                value = evaluate_expression(item["expression"], variables)
            except ArithmeticEvaluationError:
                return False
            equals = item["equals"]
            targets = equals if isinstance(equals, list) else [equals]
            tolerance = float(
                item.get("tolerance", DEFAULT_ARITHMETIC_TOLERANCE)
            )
            if not any(
                abs(value - float(target)) <= tolerance for target in targets
            ):
                return False
    return True


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _pin_matches(pinned: dict | None, row: dict) -> bool:
    if not pinned:
        return True
    for key, expected in pinned.items():
        live = row.get(key)
        if live is None or expected is None:
            if live is not expected:
                return False
        elif isinstance(expected, bool) or isinstance(live, bool):
            if bool(live) != bool(expected):
                return False
        elif isinstance(expected, int | float) and isinstance(
            live, int | float
        ):
            if not (_is_number(live) and _is_number(expected)) or (
                abs(float(live) - float(expected)) > DEFAULT_PIN_TOLERANCE
            ):
                return False
        elif live != expected:
            return False
    return True


class _CompiledSelector:
    """One entry's selector, precompiled for repeated row tests.

    Case-id lists become frozensets once instead of once per row — the
    national TAXSIM lane tests 26k rows against selectors listing 11k ids.
    """

    __slots__ = (
        "entry_id", "concept", "kind", "case_id", "case_ids", "prefix",
        "signatures", "match",
    )

    def __init__(self, entry: Mapping[str, Any]) -> None:
        self.entry_id = str(entry.get("id"))
        self.concept = entry.get("concept")
        self.kind = entry.get("kind")
        case_id = entry.get("case_id")
        self.case_id = str(case_id) if case_id is not None else None
        selector = entry.get("case_selector") or {}
        case_ids = selector.get("case_ids") if isinstance(selector, Mapping) else None
        self.case_ids = (
            frozenset(str(value) for value in case_ids)
            if case_ids is not None
            else None
        )
        self.prefix = (
            selector.get("case_id_prefix") if isinstance(selector, Mapping) else None
        )
        signatures = entry.get("signatures")
        self.signatures = frozenset(signatures) if signatures is not None else None
        self.match = entry.get("match")

    def selects(self, row: Mapping[str, Any], signature: str | None = None) -> bool:
        if self.concept != row.get("concept"):
            return False
        if self.kind is not None and row.get("kind") != self.kind:
            return False
        if self.case_id is not None:
            return str(row.get("case_id")) == self.case_id
        if self.signatures is not None:
            if signature is None:
                signature = row_signature(row)
            return signature in self.signatures
        if self.match is not None:
            return match_row(self.match, row)
        row_case = str(row.get("case_id"))
        if self.case_ids is not None and row_case not in self.case_ids:
            return False
        if self.prefix is not None and not row_case.startswith(self.prefix):
            return False
        return True


def _entry_selects_row(entry: dict, row: dict) -> bool:
    """Whether an entry's selector (ignoring pins) selects a mismatch row."""

    return _CompiledSelector(entry).selects(row)


def select_rows(
    entries: list[dict],
    rows: list[dict],
    *,
    conservation: bool,
) -> tuple[
    list[str | None],
    dict[str, list[dict]],
    dict[str, int],
    list[tuple[dict, list[str]]],
]:
    """Assign each row to its winning entry.

    Returns ``(row_winner, selected_rows_by_entry, pin_failures_by_entry,
    conflicts)``. The winner is the first entry (file order) whose selector
    selects the row and whose ``pinned`` values hold. With
    ``conservation``, every selecting entry is recorded and a row selected
    by more than one entry is returned in ``conflicts`` — pins do not
    resolve an overlap, because a pin is an expiry mechanism, not a
    selector.
    """

    selectors = [_CompiledSelector(entry) for entry in entries]
    pinned = {
        selector.entry_id: entry.get("pinned")
        for selector, entry in zip(selectors, entries)
    }
    needs_signature = any(
        selector.signatures is not None for selector in selectors
    )
    row_winner: list[str | None] = []
    selected: dict[str, list[dict]] = {s.entry_id: [] for s in selectors}
    pin_failed: dict[str, int] = {s.entry_id: 0 for s in selectors}
    conflicts: list[tuple[dict, list[str]]] = []
    for row in rows:
        signature = row_signature(row) if needs_signature else None
        winner = None
        claimants: list[str] = []
        for selector in selectors:
            if not selector.selects(row, signature):
                continue
            claimants.append(selector.entry_id)
            if winner is None:
                if not _pin_matches(pinned[selector.entry_id], row):
                    pin_failed[selector.entry_id] += 1
                else:
                    winner = selector.entry_id
                    selected[winner].append(row)
            if winner is not None and not conservation:
                break
        if conservation and len(claimants) > 1:
            conflicts.append((row, claimants))
        row_winner.append(winner)
    return row_winner, selected, pin_failed, conflicts


def _percentage(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0
    value = round(numerator / denominator * 100, 6)
    return int(value) if float(value).is_integer() else value


def _conservation_error(
    conflicts: list[tuple[dict, list[str]]],
    dispositions_file: str | None,
) -> DispositionConservationError:
    messages = [
        "classification conservation failure (TAXSIM lane): mismatch row "
        f"{row.get('case_id')!r}/{row.get('concept')!r} is selected by "
        f"entries {claimants}"
        for row, claimants in conflicts[:20]
    ]
    if len(conflicts) > 20:
        messages.append(f"... and {len(conflicts) - 20} more overlapping rows")
    return DispositionConservationError(
        dispositions_file or "<dispositions>", messages
    )


def apply_dispositions(
    report: dict,
    dispositions: dict | None,
    *,
    dispositions_file: str | None = None,
    taxsim_lane: bool | None = None,
) -> dict:
    """Join dispositions into a v2 comparison report (additive, v2.1).

    Returns a new report dict. Matching mismatch rows gain a ``disposition``
    annotation; ``summary.dispositioned`` carries the raw and explained
    rates. Entries whose pinned values no longer match the live row — or
    that match no live row at all — with ``expires_on_source_change: true``
    are listed as expired; non-expiring entries that match nothing are
    listed as orphaned (delete them when their mismatch clears). An entry
    whose selected population violates its ``selector_binding``,
    ``oracle_binding`` or ``row_arithmetic`` expires regardless of
    ``expires_on_source_change``: its rows return to unexplained.

    ``taxsim_lane`` defaults to :func:`report_is_taxsim_lane`. In a TAXSIM
    lane an entry without ``oracle_binding`` expires
    (``oracle_binding_missing``) and a row claimed by two entries raises
    :class:`DispositionConservationError`.
    """

    merged = dict(report)
    summary = dict(report.get("summary") or {})
    comparison_count = summary.get("comparison_count") or 0
    match_count = summary.get("match_count") or 0
    mismatch_count = summary.get("mismatch_count") or 0
    lane = report_is_taxsim_lane(report) if taxsim_lane is None else taxsim_lane

    entries = list((dispositions or {}).get("entries") or [])
    entry_by_id = {str(entry.get("id")): entry for entry in entries}
    counts = {kind: 0 for kind in DISPOSITION_KINDS}

    # Pass 1 — tentative assignment. Rows are matched to their winning entry
    # but not yet annotated, so population-level checks (selector binding,
    # oracle identity, row arithmetic) see the FULL selected population
    # before any annotation lands.
    source_rows = list(report.get("mismatches") or [])
    row_winner, entry_selected_rows, entry_pin_failed, conflicts = select_rows(
        entries, source_rows, conservation=lane
    )
    if conflicts:
        raise _conservation_error(conflicts, dispositions_file)

    # Pass 1.5 — invalidate entries whose evidence no longer holds on the
    # rows they select. Per ``expires_on_source_change`` semantics an
    # invalidated entry EXPIRES and its rows return to unexplained; drift can
    # never ride an old classification. Precedence: the oracle identity
    # (a different TAXSIM makes every other check moot), then the selector
    # binding (sol closing review F4: identity plus left/right/signed
    # difference, so sign flips and balanced multi-row changes are caught),
    # then row arithmetic.
    identity = report_oracle_identity(report)
    invalid: dict[str, str] = {}
    binding_violated: set[str] = set()
    for entry in entries:
        entry_id = str(entry.get("id"))
        rows = entry_selected_rows[entry_id]
        if not rows:
            continue
        oracle_binding = entry.get("oracle_binding")
        if oracle_binding:
            reason = oracle_binding_mismatch(oracle_binding, identity, rows)
            if reason:
                invalid[entry_id] = reason
                continue
        elif lane:
            invalid[entry_id] = "oracle_binding_missing"
            continue
        binding = entry.get("selector_binding")
        if binding and not _population_binding_holds(binding, rows):
            binding_violated.add(entry_id)
            invalid[entry_id] = "selector_binding_violated"
            continue
        row_arithmetic = (entry.get("evidence") or {}).get("row_arithmetic")
        if row_arithmetic and not _row_arithmetic_holds(row_arithmetic, rows):
            invalid[entry_id] = "row_arithmetic_failed"

    # Pass 2 — annotate, skipping invalidated entries.
    annotated_mismatches = []
    for row, winner in zip(source_rows, row_winner):
        annotated = dict(row)
        annotated.pop("disposition", None)
        if winner is not None and winner not in invalid:
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
        annotated_mismatches.append(annotated)

    expired = []
    expired_reasons: dict[str, str] = {}
    orphaned = []
    for entry in entries:
        entry_id = str(entry.get("id"))
        if entry_id in invalid:
            expired.append(entry_id)
            expired_reasons[entry_id] = invalid[entry_id]
            continue
        if entry_selected_rows[entry_id]:
            continue
        if entry.get("expires_on_source_change"):
            expired.append(entry_id)
            expired_reasons[entry_id] = (
                "pinned_values_changed"
                if entry_pin_failed[entry_id]
                else "no_live_rows"
            )
        else:
            orphaned.append(entry_id)

    classified_rows = sum(
        counts[kind] for kind in CLASSIFIED_DISPOSITION_KINDS
    )
    summary["dispositioned"] = {
        "schema_version": DISPOSITIONS_SCHEMA_VERSION,
        "dispositions_file": dispositions_file,
        "raw_match_rate": _percentage(match_count, comparison_count),
        # Explained = every row whose cause is verified — including rows
        # classified axiom_encoding_gap: a bug we can name, reproduce to
        # the cent, and have filed upstream IS explained (owner decision,
        # 2026-08-24). The encoding-gap count stays broken out separately
        # in `counts` and on the dashboard so our own bugs remain visible
        # until fixed and regenerated away.
        "explained_rate": _percentage(
            match_count + classified_rows, comparison_count
        ),
        "unexplained_count": max(mismatch_count - classified_rows, 0),
        "counts": counts,
        "expired_entries": expired,
        "orphaned_entries": orphaned,
    }
    if expired_reasons:
        summary["dispositioned"]["expired_reasons"] = expired_reasons
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
        report,
        dispositions,
        dispositions_file=label,
        taxsim_lane=(
            report_is_taxsim_lane(report)
            or suite_context(report.get("suite"), root).taxsim_lane
        ),
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
            counts.get(kind, 0) for kind in CLASSIFIED_DISPOSITION_KINDS
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
