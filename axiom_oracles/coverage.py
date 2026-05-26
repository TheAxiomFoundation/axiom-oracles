"""Compose-spec coverage detection.

A compiled program may contain many atomic eligibility rules (income
tests, residency tests, asset tests, etc.) without the top-level
eligibility concept actually *using* them. That's what bit us on CA
SNAP: the compose spec wired snap_eligible only to per-member
eligibility, leaving the household income/resource limits as orphaned
derived rules in the program. They were available but unreferenced.

This module walks the expr tree of a target rule, collects every
derived rule it transitively depends on, and reports any
eligibility-looking rules in the program that are *not* in that
closure. Surfaced as a non-fatal warning so an MVP spec ships with
explicit coverage acknowledgement instead of silent over-permissiveness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterable


# Names that strongly suggest an "eligibility test" — these are what we
# expect the top-level eligibility concept to ultimately depend on. The
# list is intentionally conservative; false positives are better than
# silent gaps when the cost of a miss is "engine returns wrong answer".
_ELIGIBILITY_MARKERS = (
    "eligible",
    "ineligible",
    "income_limit",
    "income_eligibility",
    "asset_limit",
    "resource_limit",
    "residency",
    "categorically_eligible",
)


def find_uncovered_eligibility_rules(
    compiled_program: Mapping[str, Any] | Path,
    *,
    target: str,
) -> list[str]:
    """Return names of eligibility-looking derived rules that ``target`` does
    not transitively reference.

    Pass either an in-memory compiled-program dict or a path to its
    compiled JSON artifact.
    """
    if isinstance(compiled_program, (str, Path)):
        payload = json.loads(Path(compiled_program).read_text())
        program = payload.get("program", payload)
    else:
        program = compiled_program

    derived_by_name = {r["name"]: r for r in program.get("derived", []) if "name" in r}

    referenced = _transitive_dependencies(target, derived_by_name)
    eligibility_rules = {
        name
        for name in derived_by_name
        if any(marker in name for marker in _ELIGIBILITY_MARKERS)
    }
    uncovered = sorted(eligibility_rules - referenced - {target})
    return uncovered


def _transitive_dependencies(
    target: str, derived_by_name: Mapping[str, Mapping]
) -> set[str]:
    """Walk the target rule's expr tree and return every derived rule name
    it (transitively) references."""
    seen: set[str] = set()
    stack: list[str] = [target]
    while stack:
        name = stack.pop()
        if name in seen or name not in derived_by_name:
            continue
        seen.add(name)
        rule = derived_by_name[name]
        stack.extend(_input_derived_names(rule.get("expr")))
        # Derived relations also reference predicates by derived name.
        derived_relation = rule.get("derived_relation") or rule.get("derivation")
        if isinstance(derived_relation, Mapping):
            predicate = derived_relation.get("predicate")
            if isinstance(predicate, Mapping) and predicate.get("kind") == "derived":
                stack.append(str(predicate.get("name")))
    return seen


def _input_derived_names(node: Any) -> Iterable[str]:
    """Yield every `{kind: derived, name: X}` reference found in an expr tree."""
    if isinstance(node, Mapping):
        if node.get("kind") == "derived" and isinstance(node.get("name"), str):
            yield node["name"]
        for value in node.values():
            yield from _input_derived_names(value)
    elif isinstance(node, list):
        for item in node:
            yield from _input_derived_names(item)


def format_coverage_warning(
    target: str, uncovered: list[str], *, max_items: int = 20
) -> str:
    """Render a human-readable warning block for the CLI summary."""
    if not uncovered:
        return ""
    lines = [
        f"!! COMPOSE COVERAGE GAP for {target}",
        f"   {len(uncovered)} eligibility-looking rule(s) exist in the "
        "compiled program but are NOT referenced by the target's "
        "expression tree:",
    ]
    for name in uncovered[:max_items]:
        lines.append(f"     - {name}")
    if len(uncovered) > max_items:
        lines.append(f"     ...and {len(uncovered) - max_items} more")
    lines.append(
        "   The target may be over-permissive — check whether these "
        "tests belong in the eligibility chain."
    )
    return "\n".join(lines)
