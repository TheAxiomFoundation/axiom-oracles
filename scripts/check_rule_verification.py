#!/usr/bin/env python3
"""Validate the committed per-rule verification artifacts (CI, PR-time).

Runs without a rulespec-us checkout: it only checks that the two committed
files parse, are internally consistent with each other, and that the recorded
counts actually recompute from the per-rule rows. This is the guard that keeps
a broken or hand-edited coverage number from landing on main — it cannot verify
the numbers are *current* (the scheduled job does that), but it proves they are
*coherent*.

Exits non-zero with a specific message on the first inconsistency.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "dashboard" / "public" / "data" / "rule_verification.json"
SUMMARY = ROOT / "dashboard" / "public" / "data" / "rule_verification_summary.json"


def fail(msg: str) -> None:
    sys.stderr.write(f"rule_verification check FAILED: {msg}\n")
    raise SystemExit(1)


def main() -> int:
    for p in (FULL, SUMMARY):
        if not p.exists():
            fail(f"missing {p.relative_to(ROOT)} — run scripts/rule_verification.py")

    try:
        full = json.loads(FULL.read_text())
        summary = json.loads(SUMMARY.read_text())
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    rules = full.get("rules")
    if not isinstance(rules, list) or not rules:
        fail("full file has no rules[]")

    # Recompute the headline counts from the per-rule rows and demand they match
    # what the summary claims. This catches a stale summary committed against a
    # freshly regenerated full file (or vice versa).
    total = len(rules)
    grounded = sum(1 for r in rules if r.get("grounded"))
    manifest = sum(1 for r in rules if r.get("manifest_backed"))
    on_oracle = sum(1 for r in rules if r.get("surface_oracle"))

    s = summary.get("rules", {})
    checks = {
        "total": (total, s.get("total")),
        "grounded": (grounded, s.get("grounded")),
        "manifest_backed": (manifest, s.get("manifest_backed")),
        "on_oracle_surface": (on_oracle, s.get("on_oracle_surface")),
    }
    for name, (recomputed, claimed) in checks.items():
        if recomputed != claimed:
            fail(
                f"summary.rules.{name} = {claimed} but recomputed {recomputed} "
                "from rules[] — regenerate both files together"
            )

    # Provenance must agree across the two files (same generator run).
    if full.get("provenance", {}).get("rulespec_commit") != summary.get(
        "provenance", {}
    ).get("rulespec_commit"):
        fail("full and summary provenance commits differ — regenerate together")

    # Percentages must be self-consistent (guards a hand-edited pct).
    def pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 1) if den else 0.0

    if s.get("grounded_pct") != pct(grounded, total):
        fail(f"summary grounded_pct {s.get('grounded_pct')} != {pct(grounded, total)}")

    # Surface KPI sanity: executable ⊆ any_oracle ⊆ total.
    surf = summary.get("surfaces", {})
    if not (
        0
        <= surf.get("executable", -1)
        <= surf.get("any_oracle", -1)
        <= surf.get("total", -1)
    ):
        fail("surface counts violate executable ≤ any_oracle ≤ total")

    print(
        f"rule_verification OK: {total} rules, "
        f"{s['grounded_pct']}% grounded, {s['manifest_backed_pct']}% manifest-backed, "
        f"{surf['executable']}/{surf['total']} executable surfaces "
        f"(commit {summary['provenance']['rulespec_commit'][:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
