#!/usr/bin/env python3
"""Per-suite unexplained-mismatch ratchet — the publishing gate.

The conformance ratchet (conformance/ratchet.yaml) guards the four oracle
jurisdictions, but most comparison suites publish outside those lanes: a
refreshed report with brand-new unexplained disagreements ships to the
dashboard with no gate at all (fl-snap-ecps sat at 774 unexplained for
weeks). This ratchet closes that hole with the same monotonic contract:

* every Axiom-pair verification suite carries a pinned ceiling on its
  unexplained-mismatch count;
* the ceiling may only FALL — re-pin with ``uv run
  scripts/unexplained_ratchet.py`` after a genuine improvement;
* a suite absent from the pin file has ceiling 0 — a NEW suite cannot
  debut with unexplained disagreements: triage first, publish second.

"Unexplained" here is exactly the dashboard hero's number (the
``countUnexplained`` semantics in dashboard/src/utils/programs.js): a
report whose disposition merge is backed by ``dispositions/<suite>.yaml``
contributes its ``summary.dispositioned.unexplained_count``; any other
report contributes its mismatch buckets minus those labeled in the
known-causes registry (dashboard/public/data/known_causes.json). The gate
and the published headline can therefore never disagree.

Usage:
    uv run scripts/unexplained_ratchet.py --check   # CI gate; exit 1 on rise
    uv run scripts/unexplained_ratchet.py           # re-pin improved ceilings
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.conformance import unexplained as unexplained_definition  # noqa: E402
from axiom_oracles.conformance.loader import load_dashboard_reports  # noqa: E402
from axiom_oracles.conformance.unexplained import (  # noqa: E402
    cause_for,
    published_unexplained,
    require_count,
    resolve_suite_reports,
)

DASHBOARD_DATA = REPO_ROOT / "dashboard" / "public" / "data"
# Lives beside conformance/ratchet.yaml (the other monotonic publishing
# invariant), NOT under dispositions/ — every dispositions/*.yaml is
# schema-validated as a suite dispositions file by apply_dispositions.
RATCHET_PATH = REPO_ROOT / "conformance" / "unexplained-ratchet.yaml"
KNOWN_CAUSES_PATH = DASHBOARD_DATA / "known_causes.json"
SCHEMA = "axiom_oracles.unexplained_ratchet.v1"

_HEADER_COMMENT = (
    "Per-suite unexplained-mismatch ceilings — GENERATED; advance only via "
    "scripts/unexplained_ratchet.py. Ceilings may only fall. A suite absent "
    "from this file has ceiling 0, so a new comparison suite cannot publish "
    "unexplained disagreements: triage first, publish second."
)


def _known_cause_covers(known_causes: list[dict], report: dict, concept: str, kind: str) -> bool:
    """Mirror causeFor() in dashboard/src/utils/programs.js."""
    return cause_for(known_causes, report, concept, kind, report.get("suite")) is not None


def count_unexplained(report: dict, known_causes: list[dict]) -> int:
    """The dashboard hero's per-report unexplained count, in Python."""
    return published_unexplained(report, known_causes=known_causes)


def diagnostic_suites() -> set[str]:
    """Suites the dashboard marks kind: "diagnostic" (excluded from headlines).

    Parsed from the suite table in dashboard/src/utils/suites.js so the gate
    and the hero share an explicit exemption list. A name alone cannot
    exempt a new report.
    """
    suites: set[str] = set()
    table = REPO_ROOT / "dashboard" / "src" / "utils" / "suites.js"
    if table.exists():
        import re

        text = table.read_text()
        for match in re.finditer(
            r'"([\w-]+)":\s*\{[^{}]*?kind:\s*"diagnostic"', text
        ):
            suites.add(match.group(1))
    return suites


def _gated_report_rows() -> list[dict]:
    """Every Axiom-pair report in gate scope, including duplicate suites."""
    diagnostics = diagnostic_suites()
    reports = []
    for report in load_dashboard_reports(DASHBOARD_DATA):
        suite = report["suite"]
        # A comparison report is one that carries graded rows. `aggregates` is
        # present only on the population lanes; the multi-oracle grid reports
        # (scripts/generate_state_income_tax_liability.py) publish `summary` +
        # `mismatches` and no `aggregates`, so requiring it silently dropped
        # 83 suites — every state income-tax grid among them — out of the
        # gate entirely. Absent from the pin file means ceiling 0, so those
        # suites read as governed while nothing actually checked them.
        if "mismatches" not in report or "summary" not in report:
            continue
        if suite in diagnostics:
            continue
        engines = report.get("engines") or {}
        # Two shapes in the wild: two-engine lanes use {left, right}; the grid
        # lanes key each engine by name ({axiom, policyengine, taxsim}).
        if "axiom" not in (engines.get("left"), engines.get("right")) and (
            "axiom" not in engines
        ):
            continue
        reports.append(report)
    return reports


def gated_reports() -> dict[str, dict]:
    """Resolve duplicates by the largest published unexplained count."""
    reports = _gated_report_rows()
    return resolve_suite_reports(
        reports, known_causes=unexplained_definition.load_known_causes(REPO_ROOT),
        published_view="dashboard",
    )


def live_counts() -> dict[str, int]:
    known_causes = []
    if KNOWN_CAUSES_PATH.exists():
        payload = json.loads(KNOWN_CAUSES_PATH.read_text())
        known_causes = payload.get("entries") or []
    # Validate every candidate: a duplicate with a smaller count must not
    # hide malformed data behind the numerical resolver.
    for report in _gated_report_rows():
        count_unexplained(report, known_causes)
    return {
        suite: count_unexplained(report, known_causes)
        for suite, report in gated_reports().items()
    }


def load_ratchet() -> dict[str, int]:
    if not RATCHET_PATH.exists():
        return {}
    doc = yaml.safe_load(RATCHET_PATH.read_text()) or {}
    if doc.get("schema") != SCHEMA:
        raise SystemExit(f"{RATCHET_PATH}: unexpected schema {doc.get('schema')!r}")
    ceilings = {}
    for row in doc.get("ratchets", []):
        suite = row["suite"]
        if suite in ceilings:
            raise ValueError(f"[{suite}] duplicate ratchet pin")
        if "note" in row and not isinstance(row["note"], str):
            raise ValueError(f"[{suite}] ratchet note must be a string")
        ceilings[suite] = require_count(row["unexplained_max"], "unexplained_max", suite)
    return ceilings


def write_ratchet(ceilings: dict[str, int]) -> None:
    preserved_notes = {}
    if RATCHET_PATH.exists():
        existing = yaml.safe_load(RATCHET_PATH.read_text()) or {}
        preserved_notes = {
            row["suite"]: row["note"] for row in existing.get("ratchets", [])
            if "note" in row
        }
    doc = {
        "schema": SCHEMA,
        "_comment": _HEADER_COMMENT,
        "ratchets": [
            {"suite": suite, "unexplained_max": ceilings[suite],
             **({"note": preserved_notes[suite]} if suite in preserved_notes else {})}
            for suite in sorted(ceilings)
        ],
    }
    RATCHET_PATH.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=79)
    )


def check(counts: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    problems = [
        f"[{suite}] pinned suite has no live gated report; retirement requires "
        "deliberately deleting its ratchet row."
        for suite in sorted(set(ceilings) - set(counts))
    ]
    for suite, count in sorted(counts.items()):
        ceiling = ceilings.get(suite, 0)
        if count > ceiling:
            problems.append(
                f"[{suite}] RATCHET regressed: unexplained {count} exceeds the "
                f"pinned ceiling {ceiling}. New disagreements must be "
                f"dispositioned (dispositions/{suite}.yaml) or labeled in the "
                "known-causes registry before this report can publish."
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail (exit 1) if any suite's unexplained count exceeds its ceiling.",
    )
    args = parser.parse_args()

    try:
        counts = live_counts()
        ceilings = load_ratchet()
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    vanished = [problem for problem in check(counts, ceilings) if "no live gated report" in problem]
    if vanished:
        for problem in vanished:
            print(problem, file=sys.stderr)
        return 1

    if args.check:
        problems = check(counts, ceilings)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        gated = sum(1 for c in counts.values())
        open_total = sum(counts.values())
        print(
            f"unexplained ratchet OK: {gated} suites gated, "
            f"{open_total} unexplained within pinned ceilings"
        )
        return 0

    # Re-pin: tighten ceilings that improved, keep ceilings that did not,
    # add new suites at their live counts ONLY if they currently pass (a new
    # suite above 0 must be pinned deliberately by editing this file — the
    # default posture is triage first, publish second).
    next_ceilings: dict[str, int] = {}
    for suite, ceiling in ceilings.items():
        live = counts[suite]
        next_ceilings[suite] = min(ceiling, live)
    for suite, live in counts.items():
        if suite not in next_ceilings and live == 0:
            next_ceilings[suite] = 0
    stray = {
        suite: live
        for suite, live in counts.items()
        if suite not in next_ceilings and live > 0
    }
    write_ratchet(next_ceilings)
    print(f"Re-pinned {RATCHET_PATH.relative_to(REPO_ROOT)} ({len(next_ceilings)} suites).")
    for suite, live in sorted(stray.items()):
        print(
            f"note: {suite} has {live} unexplained and no pinned ceiling — "
            "it will FAIL --check until triaged or deliberately pinned.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
