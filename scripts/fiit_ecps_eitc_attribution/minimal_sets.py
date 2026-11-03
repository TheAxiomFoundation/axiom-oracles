"""Attribute each mismatch row to the smallest mechanism sets that clear it.

Every attribution stage runs one variant per combination of its mechanisms.
A variant is the set of rows still mismatched once its mechanisms are
applied; the empty combination is the stage's base and never clears a row.
A row's mechanism is the minimal clearing combination: one whose variant
clears the row while no proper subset's does. Two or more minimal sets make
the row ambiguous, and a row no combination clears is residual.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Hashable, Iterable, Mapping

RESIDUAL = "residual"
AMBIGUOUS_PREFIX = "ambiguous:"


def minimal_clearing_sets(
    key: Hashable, variants: Mapping[frozenset[str], Collection[Hashable]]
) -> tuple[list[frozenset[str]], list[frozenset[str]]]:
    """Return ``(clearing, minimal)`` for one row.

    ``clearing`` lists every nonempty combination whose variant no longer
    holds ``key``, in the order of ``variants``; ``minimal`` keeps those
    with no clearing proper subset.
    """
    clearing = [
        mechanisms
        for mechanisms, rows in variants.items()
        if mechanisms and key not in rows
    ]
    minimal = [
        mechanisms
        for mechanisms in clearing
        if not any(other < mechanisms for other in clearing)
    ]
    return clearing, minimal


def label(minimal: list[frozenset[str]], name: Callable[[frozenset[str]], str]) -> str:
    """The mechanism label of a row with these minimal clearing sets."""
    if not minimal:
        return RESIDUAL
    if len(minimal) == 1:
        return name(minimal[0])
    return AMBIGUOUS_PREFIX + "|".join(sorted(name(mechanisms) for mechanisms in minimal))


def attribute(
    keys: Iterable[Hashable],
    variants: Mapping[frozenset[str], Collection[Hashable]],
    name: Callable[[frozenset[str]], str],
) -> dict[Hashable, dict]:
    """Attribute every key: its mechanism label and its clearing variants."""
    attribution = {}
    for key in keys:
        clearing, minimal = minimal_clearing_sets(key, variants)
        attribution[key] = {
            "mechanism": label(minimal, name),
            "clearing_variants": sorted(name(mechanisms) for mechanisms in clearing),
        }
    return attribution
