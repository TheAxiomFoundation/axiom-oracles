#!/usr/bin/env python3
"""Central CERTIFIED.md v3 closure gate, shared by certify and the DE census.

Every closure artifact — DK, NZ, US tariff, DE — is judged here from its
``computed`` block alone, with no program-name conditionals: the instrument
frontier must be complete (oracles#491) and the dependency closure must be
well-formed and closed (v3 leaf discipline). Any artifact that declares
neither, or declares them inconsistently, fails closed. The blocker strings
these summaries produce are the ones certificates and the DE census carry,
so the two can never disagree about why a program is not closed.
"""

from __future__ import annotations

from typing import Any

FRONTIER_MISSING_REQUIREMENT = (
    "closure must disposition the act's subordinate instruments "
    "(oracles#491); this artifact declares none"
)
DEPENDENCY_MISSING_REQUIREMENT = (
    "closure must type every leaf and encode every law-derived "
    "dependency (CERTIFIED.md v3); this artifact declares no "
    "dependency-closure block"
)
DEPENDENCY_MALFORMED_REQUIREMENT = (
    "the dependency-closure block must carry a well-typed "
    "open_dependency_count, law_derived_inputs, and "
    "instruments_bearing_on_computed that agree with its closed "
    "flag (CERTIFIED.md v3); this artifact's block is incomplete "
    "or inconsistent"
)


def _is_int(value: Any) -> bool:
    # bool is an int subclass: open_dependency_count=false must read
    # malformed, not as a zero count (launch-audit delta r2 finding).
    return isinstance(value, int) and not isinstance(value, bool)


def instrument_frontier_summary(computed: Any) -> dict[str, Any]:
    """The central view of an artifact's instrument frontier (oracles#491)."""

    frontier = computed.get("instrument_frontier") if isinstance(computed, dict) else None
    if not isinstance(frontier, dict):
        return {
            "complete": False,
            "missing": True,
            "requirement": FRONTIER_MISSING_REQUIREMENT,
        }
    return {
        key: frontier.get(key)
        for key in (
            "instrument_count",
            "supplemental_count",
            "counts",
            "pending",
            "complete",
        )
    }


def dependency_closure_summary(computed: Any) -> tuple[dict[str, Any], bool]:
    """The central view of an artifact's dependency closure, and whether the
    block is well-formed.

    A block only satisfies the gate when it is COMPLETE and internally
    consistent: the three enumerations present and list-typed, an integer
    (never bool) ``open_dependency_count`` equal to their combined length,
    and ``closed`` exactly ``open_dependency_count == 0``. ``unclassified_inputs``
    is optional — a discovery ledger that has not yet typed every leaf must
    count those leaves as open, never hide them — but when present it is part
    of the count identity. A bare ``{"closed": true}`` or any block whose
    count and lists disagree is malformed and fails closed.
    """

    block = computed.get("dependency_closure") if isinstance(computed, dict) else None
    if not isinstance(block, dict):
        return (
            {
                "closed": False,
                "missing": True,
                "requirement": DEPENDENCY_MISSING_REQUIREMENT,
            },
            False,
        )
    has_unclassified = "unclassified_inputs" in block
    unclassified = block.get("unclassified_inputs") if has_unclassified else []
    well_formed = (
        _is_int(block.get("open_dependency_count"))
        and isinstance(block.get("law_derived_inputs"), list)
        and isinstance(block.get("instruments_bearing_on_computed"), list)
        and isinstance(unclassified, list)
        and isinstance(block.get("closed"), bool)
        and block["open_dependency_count"]
        == len(block["law_derived_inputs"])
        + len(block["instruments_bearing_on_computed"])
        + len(unclassified)
        and block["closed"] == (block["open_dependency_count"] == 0)
    )
    if not well_formed:
        return (
            {
                "closed": False,
                "malformed": True,
                "requirement": DEPENDENCY_MALFORMED_REQUIREMENT,
            },
            False,
        )
    summary = {
        key: block[key]
        for key in (
            "open_dependency_count",
            "law_derived_inputs",
            "instruments_bearing_on_computed",
            "closed",
        )
    }
    if has_unclassified:
        summary["unclassified_inputs"] = list(unclassified)
    return summary, True


def closure_blockers(
    frontier: dict[str, Any], dependency: dict[str, Any]
) -> list[str]:
    """Blocker lines for a closure that does not compute closed=true.

    Empty exactly when both gates pass. Missing and malformed blocks keep
    their requirement sentence; declared-but-open blocks state the measured
    denominators so a reader can see what closing them costs.
    """

    blockers: list[str] = []
    if frontier.get("complete") is not True:
        if frontier.get("requirement"):
            blockers.append("closed: " + str(frontier["requirement"]))
        else:
            pending = frontier.get("pending")
            pending_count = len(pending) if isinstance(pending, list) else pending
            blockers.append(
                "closed: instrument frontier incomplete — "
                f"{pending_count} of {frontier.get('instrument_count')} "
                "subordinate/bearing instruments pending disposition (oracles#491)"
            )
    if dependency.get("closed") is not True:
        if dependency.get("requirement"):
            blockers.append("closed: " + str(dependency["requirement"]))
        else:
            parts = [
                f"{len(dependency.get('law_derived_inputs') or [])} law-derived inputs",
            ]
            if "unclassified_inputs" in dependency:
                parts.append(
                    f"{len(dependency['unclassified_inputs'])} unclassified inputs"
                )
            parts.append(
                f"{len(dependency.get('instruments_bearing_on_computed') or [])} "
                "bearing instruments"
            )
            blockers.append(
                "closed: dependency closure open — "
                f"{dependency.get('open_dependency_count')} open dependencies "
                f"({', '.join(parts)}) (CERTIFIED.md v3)"
            )
    return blockers


def gate(computed: Any) -> tuple[dict[str, Any], dict[str, Any], bool, list[str]]:
    """(frontier summary, dependency summary, passes, blockers) for one block."""

    frontier = instrument_frontier_summary(computed)
    dependency, well_formed = dependency_closure_summary(computed)
    passes = (
        frontier.get("complete") is True
        and well_formed
        and dependency.get("closed") is True
    )
    return frontier, dependency, passes, closure_blockers(frontier, dependency)
