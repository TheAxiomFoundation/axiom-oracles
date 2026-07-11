#!/usr/bin/env python3
"""Select which suites the affected-rerun workflow should re-run (O2).

Given the current ``main`` HEAD SHA of each rulespec repo and the committed
reports' provenance, emit the suites whose affected repos have moved past the
SHA their report last ran against — i.e. the reports that are now stale because
the rules underneath them changed. The 6-hourly workflow reruns only these,
leaving the weekly full matrix as the backstop.

Inputs:

* ``comparisons/affected_map.json`` — suite → affected rulespec repos.
* ``dashboard/public/data/<report>.json`` — each report's
  ``provenance.rulespecs`` (``[{repo, sha}]``) records the SHA it ran against.
* current HEADs — a JSON map ``{"owner/repo": "<sha>"}`` passed via
  ``--heads-json`` (a path or ``-`` for stdin). The workflow populates it by
  querying each affected repo's default branch through the GitHub API.

A suite is selected when, for any affected repo:

* the report has no provenance at all (never stamped → must run), or
* the report ran against a null/unknown SHA for that repo (can't prove fresh
  → run), or
* the recorded SHA differs from the repo's current HEAD (rules moved → run).

A suite whose every affected repo's HEAD equals what its report already ran
against is fresh and skipped. Output is the newline- or JSON-listed set of
suite names, ready to feed the matrix.

Usage:
    uv run scripts/select_affected_suites.py --heads-json heads.json
    echo '{"TheAxiomFoundation/rulespec-us":"abc…"}' | \
        uv run scripts/select_affected_suites.py --heads-json - --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
AFFECTED_MAP = COMPARISONS_DIR / "affected_map.json"


def _load_heads(source: str) -> dict[str, str]:
    text = sys.stdin.read() if source == "-" else Path(source).read_text()
    data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise SystemExit("--heads-json must contain a JSON object {repo: sha}")
    return {str(k): str(v) for k, v in data.items()}


def _report_ran_against(report: dict) -> dict[str, str | None]:
    """{repo: sha-or-None} the report's provenance says it ran against."""
    rulespecs = (report.get("provenance") or {}).get("rulespecs") or []
    return {r["repo"]: r.get("sha") for r in rulespecs if r.get("repo")}


def select(
    affected_map: dict,
    heads: dict[str, str],
    reports_by_suite: dict[str, dict],
) -> list[dict]:
    """Return per-suite selection decisions (only the selected ones)."""
    selected: list[dict] = []
    for entry in affected_map.get("suites", []):
        suite = entry["suite"]
        repos = entry.get("repos", [])
        if not repos:
            continue
        report = reports_by_suite.get(suite)
        if report is None:
            selected.append(
                {"suite": suite, "reason": "no committed report", "repos": repos}
            )
            continue
        ran_against = _report_ran_against(report)
        if not ran_against:
            selected.append(
                {"suite": suite, "reason": "report has no provenance", "repos": repos}
            )
            continue
        reasons: list[str] = []
        for repo in repos:
            head = heads.get(repo)
            if head is None:
                # HEAD unknown (repo not queried) — cannot prove staleness, so
                # do not force a rerun on missing data; the weekly backstop
                # still covers it.
                continue
            recorded = ran_against.get(repo)
            if recorded is None:
                reasons.append(f"{repo}: report ran against unknown SHA")
            elif recorded != head:
                reasons.append(f"{repo}: {recorded[:12]} → {head[:12]}")
        if reasons:
            selected.append(
                {"suite": suite, "reason": "; ".join(reasons), "repos": repos}
            )
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--heads-json",
        required=True,
        help="Path to a {repo: sha} JSON map, or - for stdin.",
    )
    parser.add_argument(
        "--format",
        choices=("lines", "json", "matrix"),
        default="lines",
        help="lines: one suite per line; json: full decisions; matrix: "
        "GitHub Actions include-list JSON.",
    )
    args = parser.parse_args()

    if not AFFECTED_MAP.exists():
        raise SystemExit(
            "comparisons/affected_map.json missing; run generate_affected_map.py"
        )
    affected_map = json.loads(AFFECTED_MAP.read_text())
    heads = _load_heads(args.heads_json)

    reports_by_suite: dict[str, dict] = {}
    for path in sorted(DASHBOARD_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("suite"):
            reports_by_suite[data["suite"]] = data

    selected = select(affected_map, heads, reports_by_suite)

    if args.format == "json":
        print(json.dumps(selected, indent=2))
    elif args.format == "matrix":
        print(json.dumps({"include": [{"name": s["suite"]} for s in selected]}))
    else:
        for s in selected:
            print(s["suite"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
