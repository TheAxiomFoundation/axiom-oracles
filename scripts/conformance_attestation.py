#!/usr/bin/env python3
"""Execution-attestation gate — report, check and prune the waiver file.

Every committed comparison report that a universe names is attested against that
universe's declared oracle (:mod:`axiom_oracles.conformance.attestation`): a real
run, strictly positive cases and comparisons, zero errors, Axiom and the oracle
both party to it, and comparison evidence bound to the policy's registered
outputs. The scoreboard already refuses coverage to anything that fails; this
script is the operator's view of the same computation, plus the gate on
``conformance/attestation_waivers.yaml``.

The waiver file is hand-authored and **shrink-only**, so ``--check`` fails on:

* a covered policy whose output binding is unattested and *not* waived — a new
  lane cannot green a suite whose comparisons are not tied to the policy;
* a waiver that is no longer needed (the report now attests the binding, or the
  policy is no longer covered) — stale entries must be pruned so the debt only
  falls;
* a waiver whose ``reason`` disagrees with the computed one, or whose ``suite``
  is not the suite the universe now names.

Usage::

    uv run scripts/conformance_attestation.py            # human report
    uv run scripts/conformance_attestation.py --check    # CI gate
    uv run scripts/conformance_attestation.py --prune    # drop stale waivers only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.conformance.attestation import attest  # noqa: E402
from axiom_oracles.conformance.loader import parse as parse_universe  # noqa: E402
from axiom_oracles.conformance.waivers import (  # noqa: E402
    AttestationWaiver,
    parse as parse_waivers,
    serialize as serialize_waivers,
)

CONFORMANCE_DIR = REPO_ROOT / "conformance"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
WAIVERS_PATH = CONFORMANCE_DIR / "attestation_waivers.yaml"


def _load_reports() -> dict[str, dict]:
    reports: dict[str, dict] = {}
    for path in sorted(DASHBOARD_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("suite") and data.get("engines"):
            reports.setdefault(data["suite"], data)
    return reports


def _universe_paths() -> list[Path]:
    return sorted(
        p
        for p in CONFORMANCE_DIR.glob("*.yaml")
        if p.stem not in {"ratchet", "attestation_waivers"}
    )


def survey() -> tuple[list[dict], list[AttestationWaiver]]:
    """Attest every in-scope policy with a report; return rows + needed waivers."""
    reports = _load_reports()
    rows: list[dict] = []
    needed: list[AttestationWaiver] = []

    for path in _universe_paths():
        universe = parse_universe(path)
        for policy in universe.policies:
            if not policy.in_scope or not policy.suite:
                continue
            report = reports.get(policy.suite)
            if report is None:
                continue
            attestation = attest(report, oracle=universe.oracle)
            gap = (
                attestation.binding_gap(policy.output_vars)
                if attestation.eligible
                else None
            )
            rows.append(
                {
                    "jurisdiction": universe.jurisdiction,
                    "policy_id": policy.id,
                    "suite": policy.suite,
                    "eligible": attestation.eligible,
                    "problems": list(attestation.problems),
                    "binding_gap": gap,
                    "cases": attestation.case_count,
                    "comparisons": attestation.comparison_count,
                    "stamped": attestation.stamped,
                    "release_drift": attestation.oracle_release_drift,
                    "attested_outputs": sorted(
                        attestation.attested_outputs & set(policy.output_vars)
                    ),
                }
            )
            if gap is not None:
                needed.append(
                    AttestationWaiver(
                        jurisdiction=universe.jurisdiction,
                        policy_id=policy.id,
                        suite=policy.suite,
                        reason=gap,
                    )
                )
    return rows, needed


def check(rows: list[dict], needed: list[AttestationWaiver]) -> list[str]:
    """Gate messages (empty ⇒ pass)."""
    committed = parse_waivers(WAIVERS_PATH)
    problems: list[str] = []

    for row in rows:
        if not row["eligible"]:
            problems.append(
                f"[{row['jurisdiction']}] {row['policy_id']} is registered to "
                f"suite {row['suite']!r}, whose report cannot attest execution: "
                + "; ".join(row["problems"])
            )

    needed_by_key = {waiver.key: waiver for waiver in needed}
    for key, waiver in sorted(needed_by_key.items()):
        held = committed.waiver_for(waiver.jurisdiction, waiver.policy_id, waiver.suite)
        if held is None:
            problems.append(
                f"[{waiver.jurisdiction}] {waiver.policy_id} is covered by suite "
                f"{waiver.suite!r} but no registered output of that policy carries "
                f"comparison evidence in the report ({waiver.reason}). Bind the "
                "suite to the policy's outputs (regenerate the report so it stamps "
                "an attestation), or — only for a pre-attestation artifact — add "
                "the row to conformance/attestation_waivers.yaml with a note."
            )
        elif held.reason != waiver.reason:
            problems.append(
                f"[{waiver.jurisdiction}] {waiver.policy_id}: waiver reason "
                f"{held.reason!r} no longer matches the computed reason "
                f"{waiver.reason!r} — re-state why the binding cannot be shown."
            )

    for key in sorted(committed.keys() - set(needed_by_key)):
        problems.append(
            f"[{key[0]}] {key[1]}: STALE waiver — the binding no longer needs one "
            "(the report attests it, or the policy is no longer covered by that "
            "suite). Waivers are shrink-only: run "
            "`uv run scripts/conformance_attestation.py --prune`."
        )
    return problems


def prune(needed: list[AttestationWaiver]) -> list[AttestationWaiver]:
    """Drop waivers that are no longer needed. Never adds — that is the point."""
    committed = parse_waivers(WAIVERS_PATH)
    needed_keys = {waiver.key for waiver in needed}
    kept = [waiver for waiver in committed if waiver.key in needed_keys]
    WAIVERS_PATH.write_text(serialize_waivers(kept))
    return kept


def _report(rows: list[dict], needed: list[AttestationWaiver]) -> str:
    lines = ["# Execution attestation", ""]
    by_jurisdiction: dict[str, list[dict]] = {}
    for row in rows:
        by_jurisdiction.setdefault(row["jurisdiction"], []).append(row)
    for jurisdiction, jur_rows in sorted(by_jurisdiction.items()):
        attested = [r for r in jur_rows if r["eligible"] and r["binding_gap"] is None]
        unbound = [r for r in jur_rows if r["eligible"] and r["binding_gap"]]
        failed = [r for r in jur_rows if not r["eligible"]]
        stamped = sum(1 for r in jur_rows if r["stamped"])
        lines.append(
            f"## {jurisdiction} — {len(attested)}/{len(jur_rows)} fully attested "
            f"({stamped} runner-stamped)"
        )
        for row in failed:
            lines.append(
                f"- ⛔ {row['policy_id']} ({row['suite']}): "
                + "; ".join(row["problems"])
            )
        for row in unbound:
            lines.append(
                f"- ⚠️  {row['policy_id']} ({row['suite']}): {row['binding_gap']} "
                f"[{row['cases']} cases, {row['comparisons']} comparisons]"
            )
        drifted = [r for r in jur_rows if r["release_drift"]]
        if drifted:
            by_release: dict[str, set[str]] = {}
            for row in drifted:
                by_release.setdefault(row["release_drift"], set()).add(row["suite"])
            summary = "; ".join(
                f"{release} ({', '.join(sorted(suites))})"
                for release, suites in sorted(by_release.items())
            )
            lines.append(
                f"- 📌 {len(drifted)} covered polic(ies) ran a different oracle "
                f"release than the universe pins: {summary}"
            )
        lines.append("")
    lines.append(f"Waivers needed: {len(needed)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="CI: fail on unattested or stale waivers."
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove waivers that are no longer needed (never adds).",
    )
    args = parser.parse_args()

    rows, needed = survey()

    if args.prune:
        kept = prune(needed)
        print(
            f"Wrote {WAIVERS_PATH.relative_to(REPO_ROOT)}: {len(kept)} waiver(s) kept."
        )
        return 0

    if args.check:
        problems = check(rows, needed)
        if problems:
            for problem in problems:
                sys.stderr.write(f"attestation-gate FAILED: {problem}\n")
            return 1
        attested = sum(1 for r in rows if r["eligible"] and not r["binding_gap"])
        print(
            f"attestation-gate OK: {len(rows)} covered policy/suite pairs attested "
            f"execution; {attested} bind a registered output; "
            f"{len(needed)} on committed waivers"
        )
        return 0

    print(_report(rows, needed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
