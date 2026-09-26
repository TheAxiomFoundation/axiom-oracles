"""Structured mismatch-row selectors, row signatures, and row arithmetic.

The shared dispositions schema (:mod:`.dispositions`) historically selected
mismatch rows by case id only. That forces every classification of a large
population into an enumerated case list, and it cannot say *why* a row
belongs to a class. This module ports the structured-selector machinery of
the US tariff campaign (``scripts/us_tariff_schedule_campaign.py``:
``selector_matches``, ``mismatch_signature``,
``signature_population_sha256``) from the tariff unit shape to comparison
report mismatch rows, so a disposition can select rows by what they are:

* ``match`` — a structured selector over mismatch-row fields
  (:data:`MATCH_FIELDS`). The tariff guards carry over: an empty selector
  is rejected, and at least one bound beyond the row's concept and kind is
  required (:data:`BOUND_FIELDS`), so no entry can claim a whole concept.
* :func:`mismatch_signature` — a SHA-256 over the canonical row identity
  ``{concept, kind, delta, facts, error_signature}``; case ids and the
  engines' absolute values are deliberately excluded, so rows that differ
  only in who they are collapse onto one signature.
* :func:`signature_population_sha256` — a digest over a population's
  ``(signature, multiplicity)`` pairs, usable as a population binding.
* :func:`evaluate_expression` — the dispositions arithmetic evaluator
  extended with named row variables (``left``, ``right``, ``difference``,
  and ``facts.<name>``) so evidence can be checked against every selected
  row instead of against constants typed next to it.

Row fields read here are the ones :mod:`.report` writes: ``concept``,
``kind``, ``left``, ``right``, ``difference`` (signed ``left - right``),
``facts`` (``case.metadata["selector_facts"]`` copied verbatim when a
population sets it), and ``error`` (engine-error rows only:
``{engine, side, signature, messages, ...}``).
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

#: Fields a ``match`` selector may bound.
MATCH_FIELDS = frozenset(
    {
        "kind",
        "facts",
        "delta",
        "left",
        "right",
        "error_signature",
        "error_engine",
    }
)
#: Fields that count as a real bound. ``kind`` alone (like ``concept``,
#: which lives on the entry) would claim every row of a concept, so a
#: selector needs at least one of these (the tariff "non-slot bound" rule).
BOUND_FIELDS = MATCH_FIELDS - {"kind"}

_DELTA_KEYS = frozenset(
    {"sign", "min", "max", "abs_min", "abs_max", "values", "tolerance"}
)
_VALUE_KEYS = frozenset({"min", "max", "values", "tolerance"})
#: Keys that actually constrain a numeric field; ``tolerance`` alone does not.
_NUMERIC_BOUND_KEYS = frozenset(
    {"sign", "min", "max", "abs_min", "abs_max", "values"}
)

#: Default tolerance for ``values`` membership on delta/left/right bounds;
#: matches the dispositions pin tolerance.
DEFAULT_VALUE_TOLERANCE = 0.005

#: Plain row variables available to row arithmetic, besides ``facts.<name>``.
ROW_VARIABLES = frozenset({"left", "right", "difference"})

_HEX64 = re.compile(r"[0-9a-f]{64}")
_FACT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ArithmeticEvaluationError(ValueError):
    """An evidence arithmetic expression could not be evaluated safely."""


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------


def _is_number(value: object) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _is_json_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | bool) or _is_number(value)


def _scalar_equal(left: object, right: object) -> bool:
    """Type-aware equality: bools only equal bools, numbers compare as numbers.

    Python's ``True == 1`` would let a boolean fact satisfy a numeric bound
    (and vice versa); selectors must not conflate them.
    """

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if _is_number(left) and _is_number(right):
        return float(left) == float(right)
    return type(left) is type(right) and left == right


# ---------------------------------------------------------------------------
# match selector validation
# ---------------------------------------------------------------------------


def _validate_scalar_or_list(value: object, label: str) -> list[str]:
    if isinstance(value, list):
        if not value:
            return [f"{label} must be a non-empty list or a scalar"]
        bad = [item for item in value if not _is_json_scalar(item)]
        if bad:
            return [f"{label} list items must be JSON scalars; got {bad[:3]!r}"]
        return []
    if not _is_json_scalar(value):
        return [f"{label} must be a JSON scalar or a non-empty list of them"]
    return []


def _validate_string_or_list(value: object, label: str) -> list[str]:
    if isinstance(value, str) and value:
        return []
    if (
        isinstance(value, list)
        and value
        and all(isinstance(item, str) and item for item in value)
    ):
        return []
    return [f"{label} must be a non-empty string or list of non-empty strings"]


def _validate_numeric_bound(
    spec: object, label: str, allowed: frozenset[str]
) -> list[str]:
    if not isinstance(spec, dict):
        return [f"{label} must be a mapping"]
    errors: list[str] = []
    unknown = set(spec) - allowed
    if unknown:
        errors.append(f"{label} has unknown keys: {sorted(unknown)}")
    if not (set(spec) & _NUMERIC_BOUND_KEYS):
        errors.append(
            f"{label} is vacuous: it needs at least one of "
            f"{sorted(allowed & _NUMERIC_BOUND_KEYS)}"
        )
    sign = spec.get("sign")
    if "sign" in spec and sign not in ("pos", "neg"):
        errors.append(f"{label}.sign must be 'pos' or 'neg'")
    for key in ("min", "max", "abs_min", "abs_max"):
        if key in spec and not _is_number(spec[key]):
            errors.append(f"{label}.{key} must be a finite number")
    for key in ("abs_min", "abs_max"):
        if key in spec and _is_number(spec[key]) and spec[key] < 0:
            errors.append(f"{label}.{key} must be >= 0")
    if "values" in spec:
        values = spec["values"]
        if (
            not isinstance(values, list)
            or not values
            or not all(_is_number(value) for value in values)
        ):
            errors.append(f"{label}.values must be a non-empty numeric list")
    if "tolerance" in spec:
        tolerance = spec["tolerance"]
        if not _is_number(tolerance) or tolerance < 0:
            errors.append(f"{label}.tolerance must be a number >= 0")
        elif "values" not in spec:
            errors.append(f"{label}.tolerance only applies to `values`")
    for low, high in (("min", "max"), ("abs_min", "abs_max")):
        if (
            _is_number(spec.get(low))
            and _is_number(spec.get(high))
            and spec[low] > spec[high]
        ):
            errors.append(f"{label}.{low} exceeds {label}.{high}")
    return errors


def validate_match(match: object, label: str = "match") -> list[str]:
    """Return every schema violation in a ``match`` selector.

    Guards ported from the tariff campaign: an empty or non-mapping selector
    is invalid, unknown fields are invalid, every present bound must itself
    constrain something, and at least one bound in :data:`BOUND_FIELDS` is
    required — a selector over ``kind`` alone would claim every row of the
    entry's concept.
    """

    if not isinstance(match, dict) or not match:
        return [
            f"{label} must be a non-empty mapping "
            "(universal selectors are forbidden)"
        ]
    errors: list[str] = []
    unknown = set(match) - MATCH_FIELDS
    if unknown:
        errors.append(f"{label} has unknown fields: {sorted(unknown)}")
    if not set(match) & BOUND_FIELDS:
        errors.append(
            f"{label} needs at least one bound beyond concept and kind "
            f"(one of {sorted(BOUND_FIELDS)}); concept/kind-only selectors "
            "would claim every row of the concept"
        )
    if "kind" in match:
        errors.extend(_validate_string_or_list(match["kind"], f"{label}.kind"))
    if "facts" in match:
        facts = match["facts"]
        if not isinstance(facts, dict) or not facts:
            errors.append(f"{label}.facts must be a non-empty mapping")
        else:
            for name, value in facts.items():
                if not isinstance(name, str) or not _FACT_NAME.fullmatch(name):
                    errors.append(
                        f"{label}.facts key {name!r} must be an identifier"
                    )
                    continue
                errors.extend(
                    _validate_scalar_or_list(value, f"{label}.facts.{name}")
                )
    if "delta" in match:
        errors.extend(
            _validate_numeric_bound(match["delta"], f"{label}.delta", _DELTA_KEYS)
        )
    for side in ("left", "right"):
        if side in match:
            errors.extend(
                _validate_numeric_bound(match[side], f"{label}.{side}", _VALUE_KEYS)
            )
    for key in ("error_signature", "error_engine"):
        if key in match:
            errors.extend(_validate_string_or_list(match[key], f"{label}.{key}"))
    return errors


# ---------------------------------------------------------------------------
# match selector evaluation
# ---------------------------------------------------------------------------


def _one_of(value: object, selector: object) -> bool:
    options = selector if isinstance(selector, list) else [selector]
    return any(_scalar_equal(value, option) for option in options)


def _numeric_bound_matches(value: object, spec: Mapping[str, Any]) -> bool:
    if not _is_number(value):
        return False
    number = float(value)
    sign = spec.get("sign")
    if sign == "pos" and not number > 0:
        return False
    if sign == "neg" and not number < 0:
        return False
    if "min" in spec and number < spec["min"]:
        return False
    if "max" in spec and number > spec["max"]:
        return False
    if "abs_min" in spec and abs(number) < spec["abs_min"]:
        return False
    if "abs_max" in spec and abs(number) > spec["abs_max"]:
        return False
    if "values" in spec:
        tolerance = float(spec.get("tolerance", DEFAULT_VALUE_TOLERANCE))
        if not any(abs(number - float(v)) <= tolerance for v in spec["values"]):
            return False
    return True


def match_row(match: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """Whether a (validated) ``match`` selector selects a mismatch row.

    The entry-level ``concept`` (and optional entry-level ``kind``) is
    checked by the caller; this evaluates the structured bounds only. A
    bound on a field the row does not carry never matches — a row without
    ``facts`` cannot satisfy a fact bound, and a row whose ``difference``
    is null cannot satisfy a delta bound. Error bounds can match either
    failing side, but all supplied error bounds must hold on the same side.
    """

    if "kind" in match and not _one_of(row.get("kind"), match["kind"]):
        return False
    if "facts" in match:
        facts = row.get("facts")
        if not isinstance(facts, Mapping):
            return False
        for name, selector in match["facts"].items():
            if name not in facts or not _one_of(facts[name], selector):
                return False
    if "delta" in match and not _numeric_bound_matches(
        row.get("difference"), match["delta"]
    ):
        return False
    for side in ("left", "right"):
        if side in match and not _numeric_bound_matches(row.get(side), match[side]):
            return False
    error_fields = (("error_signature", "signature"), ("error_engine", "engine"))
    if any(key in match for key, _ in error_fields):
        error = row.get("error")
        if not isinstance(error, Mapping):
            return False
        # Both bounds must describe the same failing engine when both sides
        # errored; never combine one side's name with the other signature.
        if not any(
            isinstance(detail, Mapping)
            and all(
                key not in match or _one_of(detail.get(field), match[key])
                for key, field in error_fields
            )
            for detail in (error, error.get("other_side"))
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------


def _canonical(value: object) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def mismatch_signature(row: Mapping[str, Any]) -> str:
    """SHA-256 over a mismatch row's canonical identity.

    The identity is ``{concept, kind, delta, facts, error_signature}``:
    what disagreed, how, by how much, for which kind of household, and —
    for engine-error rows — with which failures. When both engines fail,
    ``error_signature`` records each engine, side, and failure signature
    in canonical order. Single-failure rows keep the historical scalar
    signature, preserving existing population bindings. Case ids and the engines'
    absolute values are excluded on purpose (the tariff campaign's
    aggregation identity), so two households with the same facts and the
    same delta share a signature and a signatures-based entry binds the
    class rather than an enumerated case list.
    """

    error = row.get("error")
    error_signature = error.get("signature") if isinstance(error, Mapping) else None
    if isinstance(error, Mapping) and isinstance(error.get("other_side"), Mapping):
        # A disposition may explain the secondary failure. Binding only the
        # primary signature would let a changed secondary failure retain that
        # explanation. Canonicalize both sides independently of which was first.
        error_signature = sorted(
            (
                {key: detail.get(key) for key in ("engine", "side", "signature")}
                for detail in (error, error["other_side"])
            ),
            key=_canonical,
        )
    identity = {
        "concept": row.get("concept"),
        "kind": row.get("kind"),
        "delta": row.get("difference"),
        "facts": dict(row.get("facts") or {}),
        "error_signature": error_signature,
    }
    return hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()


def row_signature(row: Mapping[str, Any]) -> str:
    """The signature a ``signatures`` selector compares against.

    A row that already carries a generator-stamped string ``signature``
    keeps it (the pre-existing contract); every other row is identified by
    :func:`mismatch_signature`.
    """

    stamped = row.get("signature")
    if isinstance(stamped, str) and stamped:
        return stamped
    return mismatch_signature(row)


def signature_population(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, int]]:
    """``(signature, multiplicity)`` pairs of a selected row population."""

    counts = Counter(row_signature(row) for row in rows)
    return sorted(counts.items())


def signature_population_sha256(population: Iterable[tuple[str, int]]) -> str:
    """Hash a selector's exact mismatch-signature population and multiplicities.

    Ported verbatim in behaviour from the tariff campaign: signatures must
    be 64-char lowercase hex, unique, with positive integer multiplicities;
    the pairs are sorted before hashing so input order is irrelevant.
    """

    normalized: list[list[str | int]] = []
    seen: set[str] = set()
    for signature, units in population:
        if not isinstance(signature, str) or not _HEX64.fullmatch(signature):
            raise ValueError(
                "selector population contains an invalid mismatch signature"
            )
        if signature in seen:
            raise ValueError("selector population contains a duplicate signature")
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise ValueError("selector population contains an invalid multiplicity")
        seen.add(signature)
        normalized.append([signature, units])
    normalized.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical(normalized).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Restricted arithmetic with named row variables
# ---------------------------------------------------------------------------


def expression_variables(expression: str) -> set[str]:
    """Names an expression references (``left``, ``facts.mstat``, ...).

    Raises :class:`ArithmeticEvaluationError` on a syntax error or on any
    node outside the restricted grammar, so a caller can validate an
    expression without evaluating it.
    """

    names: set[str] = set()
    _walk(_parse(expression), expression, names=names, variables=None)
    return names


def evaluate_expression(
    expression: str,
    variables: Mapping[str, float] | None = None,
) -> float:
    """Evaluate a restricted arithmetic expression.

    Grammar: numbers, ``+ - * /``, unary ``+``/``-``, parentheses, and —
    only when ``variables`` is given — bare names and dotted ``facts.<name>``
    references, resolved by lookup in ``variables`` (never by Python
    attribute access). Calls, subscripts, comparisons, and every other
    construct raise :class:`ArithmeticEvaluationError`: evidence must be
    checkable without executing code.
    """

    result = _walk(_parse(expression), expression, names=None, variables=variables)
    if not math.isfinite(result):
        raise ArithmeticEvaluationError(
            f"non-finite result in arithmetic expression {expression!r}"
        )
    return result


@lru_cache(maxsize=4096)
def _parse(expression: str) -> ast.AST:
    # Cached: row arithmetic evaluates one expression on every selected row,
    # and _walk never mutates the tree.
    try:
        return ast.parse(str(expression), mode="eval")
    except SyntaxError as exc:
        raise ArithmeticEvaluationError(
            f"invalid arithmetic expression {expression!r}: {exc.msg}"
        ) from exc


def _variable_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "facts"
    ):
        return f"facts.{node.attr}"
    return None


def _walk(
    node: ast.AST,
    expression: str,
    *,
    names: set[str] | None,
    variables: Mapping[str, float] | None,
) -> float:
    def recurse(child: ast.AST) -> float:
        return _walk(child, expression, names=names, variables=variables)

    if isinstance(node, ast.Expression):
        return recurse(node.body)
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, ast.Add | ast.Sub | ast.Mult | ast.Div
    ):
        left = recurse(node.left)
        right = recurse(node.right)
        if names is not None:
            return 0.0
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ArithmeticEvaluationError(
                f"division by zero in arithmetic expression {expression!r}"
            )
        return left / right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        value = recurse(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if (
        isinstance(node, ast.Constant)
        and _is_number(node.value)
    ):
        return float(node.value)
    name = _variable_name(node)
    if name is not None and (names is not None or variables is not None):
        if name not in ROW_VARIABLES and not name.startswith("facts."):
            raise ArithmeticEvaluationError(
                f"unknown variable {name!r} in arithmetic expression "
                f"{expression!r}; row arithmetic may reference "
                f"{sorted(ROW_VARIABLES)} and facts.<name>"
            )
        if names is not None:
            names.add(name)
            return 0.0
        assert variables is not None
        if name not in variables or not _is_number(variables[name]):
            raise ArithmeticEvaluationError(
                f"variable {name!r} is missing or not numeric on this row"
            )
        return float(variables[name])
    raise ArithmeticEvaluationError(
        f"unsupported syntax in arithmetic expression {expression!r}; "
        "only numbers, + - * /, and parentheses are allowed"
        + (
            ", plus the row variables left, right, difference and facts.<name>"
            if names is not None or variables is not None
            else ""
        )
    )


def row_variables(row: Mapping[str, Any]) -> dict[str, float]:
    """Numeric variables a row exposes to row arithmetic.

    ``left``, ``right``, and ``difference`` when numeric (booleans count as
    0/1, matching how the comparator scores eligibility values), plus
    ``facts.<name>`` for every numeric or boolean fact. A non-numeric or
    missing value is simply absent, so an expression that references it
    fails with a clear error instead of silently reading zero.
    """

    variables: dict[str, float] = {}
    for key in ROW_VARIABLES:
        value = row.get(key)
        if isinstance(value, bool):
            variables[key] = float(value)
        elif _is_number(value):
            variables[key] = float(value)
    facts = row.get("facts")
    if isinstance(facts, Mapping):
        for name, value in facts.items():
            if isinstance(value, bool):
                variables[f"facts.{name}"] = float(value)
            elif _is_number(value):
                variables[f"facts.{name}"] = float(value)
    return variables
