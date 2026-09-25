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

"Unexplained" uses the shared conservative assessment in
``axiom_oracles.conformance.unexplained``. Producer classifications, declared
counts, and unfiltered mismatch rows all remain visible; concept-less rows are
never explained by known-cause labels. The dashboard mirrors this definition.
Hard assessment defects, unreadable dashboard JSON, and vanished pins fail the
gate. Only the typed dashboard suite table can exempt diagnostics.

Usage:
    uv run scripts/unexplained_ratchet.py --check   # CI gate; exit 1 on rise
    uv run scripts/unexplained_ratchet.py           # re-pin improved ceilings
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.conformance.loader import load_dashboard_reports  # noqa: E402
from axiom_oracles.conformance.unexplained import (  # noqa: E402
    admit_count,
    assess_unexplained,
    load_known_causes,
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


def count_unexplained(report: dict, known_causes: list[dict]) -> int:
    """Return the shared count; full gate validation also checks its defects."""
    return assess_unexplained(report, known_causes=known_causes).count


def diagnostic_suites() -> set[str]:
    """Suites the dashboard marks kind: "diagnostic" (excluded from headlines).

    Parsed from the suite table in dashboard/src/utils/suites.js so the gate
    and the hero share an explicit exemption list. A suite name alone cannot
    exempt a newly published report.
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
    """Every Axiom-pair report in gate scope, including all duplicate suites."""
    diagnostics = diagnostic_suites()
    reports = []
    for report in load_dashboard_reports(DASHBOARD_DATA):
        suite = report["suite"]
        # Grid lanes have summary + mismatches but no aggregates.
        if "mismatches" not in report or "summary" not in report:
            continue
        if suite in diagnostics:
            continue
        engines = report.get("engines") or {}
        if "axiom" not in (engines.get("left"), engines.get("right")) and (
            "axiom" not in engines
        ):
            continue
        reports.append(report)
    return reports


def gated_reports() -> dict[str, dict]:
    """suite -> report chosen by the shared maximum-unexplained resolver."""
    return resolve_suite_reports(
        _gated_report_rows(), known_causes=load_known_causes(REPO_ROOT),
        repo_root=REPO_ROOT,
    )


def live_assessments() -> tuple[dict[str, int], list[str]]:
    """Assess every gated report; duplicates cannot hide a hard defect."""
    known_causes = load_known_causes(REPO_ROOT)
    reports = _gated_report_rows()
    selected = resolve_suite_reports(
        reports, known_causes=known_causes, repo_root=REPO_ROOT,
    )
    problems = sorted({
        f"[{report['suite']}] {report.get('_file', '<unnamed report>')}: {defect}"
        for report in reports
        for defect in assess_unexplained(
            report, known_causes=known_causes, repo_root=REPO_ROOT,
        ).defects
    })
    counts = {
        suite: assess_unexplained(
            report, known_causes=known_causes, repo_root=REPO_ROOT,
        ).count
        for suite, report in selected.items()
    }
    return counts, problems


def live_counts() -> dict[str, int]:
    return live_assessments()[0]


def load_ratchet() -> dict[str, int]:
    if not RATCHET_PATH.exists():
        return {}
    doc = yaml.safe_load(RATCHET_PATH.read_text()) or {}
    if doc.get("schema") != SCHEMA:
        raise SystemExit(f"{RATCHET_PATH}: unexpected schema {doc.get('schema')!r}")
    ceilings = {}
    for row in doc.get("ratchets", []):
        suite = row["suite"]
        value = admit_count(row["unexplained_max"])
        if value is None:
            raise ValueError(f"[{suite}] unexplained_max is not a non-negative count")
        if suite in ceilings:
            raise ValueError(f"[{suite}] duplicate ratchet pin")
        if "note" in row and not isinstance(row["note"], str):
            raise ValueError(f"[{suite}] ratchet note must be a string")
        ceilings[suite] = value
    return ceilings


def write_ratchet(ceilings: dict[str, int], *, notes: dict[str, str] | None = None) -> None:
    """Write ceilings while preserving any existing per-suite correction notes."""
    preserved_notes = {}
    if RATCHET_PATH.exists():
        existing = yaml.safe_load(RATCHET_PATH.read_text()) or {}
        preserved_notes = {
            row["suite"]: row["note"] for row in existing.get("ratchets", [])
            if "note" in row
        }
    preserved_notes.update(notes or {})
    doc = {
        "schema": SCHEMA,
        "_comment": _HEADER_COMMENT,
        "ratchets": [
            {
                "suite": suite, "unexplained_max": ceilings[suite],
                **({"note": preserved_notes[suite]} if suite in preserved_notes else {}),
            }
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
        counts, defects = live_assessments()
        ceilings = load_ratchet()
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    vanished = [
        problem for problem in check(counts, ceilings)
        if "no live gated report" in problem
    ]
    if defects or vanished:
        for problem in defects + vanished:
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
