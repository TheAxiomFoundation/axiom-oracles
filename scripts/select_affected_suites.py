#!/usr/bin/env python3
"""Select which suites the affected-rerun workflow should re-run (O2).

Given the current ``main`` HEAD SHA of each rulespec repo and the committed
reports' provenance, emit the suites whose affected repos have moved past the
SHA their report last ran against — i.e. the reports that are now stale because
the rules underneath them changed. The 6-hourly workflow reruns only these,
leaving the weekly full matrix as the backstop.

Inputs:

* ``comparisons/affected_map.json`` — suite → affected rulespec repos, plus
  each entry's ``name``: the ``run_comparison.py`` registry name the rerun
  matrix must dispatch (explicit ``null`` = not CI-runnable: parameter suites
  run only under the manual ``run_parameter_comparisons.py`` lane, and
  registry suites declaring ``ci: manual`` in their YAML run only under a
  supervised ``run_comparison.py`` invocation).
* ``dashboard/public/data/<report>.json`` — each report's
  ``provenance.rulespecs`` (``[{repo, sha}]``) records the SHA it ran against.
* current HEADs — a JSON map ``{"owner/repo": "<sha>"}`` passed via
  ``--heads-json`` (a path or ``-`` for stdin). The workflow populates it by
  querying each affected repo's default branch through the GitHub API.

A suite is selected when, for any affected repo:

* the report has no provenance at all (never stamped → must run), or
* the report ran against a null/unknown SHA for that repo (can't prove fresh
  → run), or
* the recorded SHA differs from the repo's current HEAD (rules moved → run) —
  unless the map entry pins that repo (``pinned: {repo: sha}``, emitted for
  suites declaring ``rulespec_upstream_sha``): a pinned suite replays one
  reviewed snapshot, so it is judged against the PIN instead and goes stale
  only when the pin itself changes.

A suite whose every affected repo's HEAD equals what its report already ran
against (or whose pin equals what it ran against, for pinned repos) is fresh
and skipped. ``--force-all`` bypasses the staleness logic and
selects every mapped entry (the workflow's force_all input) — the same
validation, filtering, and dispatch rules apply, so the two workflow paths
cannot drift.

Selection is per report suite, but the rerun matrix must dispatch each entry's
``name``. The two often coincide but not always (dashboard suite
``uk-benefit-cap`` runs under registry name ``uk-benefit-cap-ukmod``;
``dk-child-youth-benefit`` under ``dk-child-youth-benefit-euromod``), and
entries with an explicit null ``name`` are excluded from ``lines``/``matrix``/
``github`` output entirely — dispatching either wrong class crashes the leg
with "unknown comparison". A MISSING or malformed ``name`` is a map-schema
error and fails loudly: silently skipping it would let a drifted map empty the
matrix while looking green. The ``json`` format keeps every selected decision,
including non-runnable ones, for diagnostics.

Usage:
    uv run scripts/select_affected_suites.py --heads-json heads.json
    uv run scripts/select_affected_suites.py --force-all --format github
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


def _registry_name(entry: dict) -> str | None:
    """The entry's validated registry name, or None for an explicit manual entry.

    Only an explicit JSON ``null`` means "not CI-runnable" (the parameter
    suites). A missing key or any other falsey/non-string value is a
    map-schema error — regenerate the map — and fails loudly rather than
    silently shrinking the matrix.
    """
    suite = entry.get("suite", "<unnamed>")
    if "name" not in entry:
        raise SystemExit(
            f"affected map entry {suite!r} lacks the `name` field; "
            "regenerate with `uv run scripts/generate_affected_map.py`"
        )
    name = entry["name"]
    if name is None:
        return None
    if not isinstance(name, str) or not name.strip():
        raise SystemExit(
            f"affected map entry {suite!r} has a malformed registry name "
            f"{name!r}; regenerate with `uv run scripts/generate_affected_map.py`"
        )
    return name


def _report_ran_against(report: dict) -> dict[str, str | None]:
    """{repo: sha-or-None} the report's provenance says it ran against."""
    rulespecs = (report.get("provenance") or {}).get("rulespecs") or []
    return {r["repo"]: r.get("sha") for r in rulespecs if r.get("repo")}


def _selector_report_path(value: object) -> Path | None:
    """Resolve a committed selector report, failing loudly on unsafe paths.

    Legacy map entries contain a bare dashboard filename.  New unified-record
    entries contain a repo-relative ``comparisons/...`` path.  Supporting both
    explicitly avoids overloading dashboard suite keys as registry names (the
    #295 failure mode) or making certificate records masquerade as UI reports.
    """

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise SystemExit(f"affected map has malformed report path {value!r}")
    relative = Path(value)
    if ".." in relative.parts:
        raise SystemExit(f"affected map report path escapes the repo: {value!r}")
    if len(relative.parts) == 1:
        return DASHBOARD_DATA_DIR / relative
    candidate = (REPO_ROOT / relative).resolve()
    if REPO_ROOT.resolve() not in candidate.parents:
        raise SystemExit(f"affected map report path escapes the repo: {value!r}")
    return candidate


def load_reports(affected_map: dict) -> dict[str, dict]:
    """Load dashboard and explicitly mapped canonical selector records."""

    reports_by_suite: dict[str, dict] = {}
    paths = set(DASHBOARD_DATA_DIR.glob("*.json"))
    for entry in affected_map.get("suites", []):
        if not isinstance(entry, dict):
            raise SystemExit("affected map suite entries must be objects")
        path = _selector_report_path(entry.get("report"))
        if path is not None:
            paths.add(path)
    for path in sorted(paths):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("suite"):
            reports_by_suite[str(data["suite"])] = data
    return reports_by_suite


def select(
    affected_map: dict,
    heads: dict[str, str],
    reports_by_suite: dict[str, dict],
) -> list[dict]:
    """Return per-suite selection decisions (only the selected ones)."""
    selected: list[dict] = []
    for entry in affected_map.get("suites", []):
        suite = entry["suite"]
        name = _registry_name(entry)  # validate every entry, selected or not
        repos = entry.get("repos", [])
        if not repos:
            continue
        report = reports_by_suite.get(suite)
        if report is None:
            selected.append(
                {
                    "suite": suite,
                    "name": name,
                    "reason": "no committed report",
                    "repos": repos,
                }
            )
            continue
        ran_against = _report_ran_against(report)
        if not ran_against:
            selected.append(
                {
                    "suite": suite,
                    "name": name,
                    "reason": "report has no provenance",
                    "repos": repos,
                }
            )
            continue
        pinned = entry.get("pinned") or {}
        reasons: list[str] = []
        for repo in repos:
            pin = pinned.get(repo)
            if pin is not None:
                # A pinned suite replays one reviewed snapshot; its report can
                # only ever stamp the pinned SHA, so freshness is judged
                # against the PIN, not the repo's moving HEAD. It goes stale
                # exactly when the pin changes (a deliberate re-pin PR) or the
                # report predates pin stamping.
                recorded = ran_against.get(repo)
                if recorded is None:
                    reasons.append(f"{repo}: report ran against unknown SHA")
                elif recorded != pin:
                    reasons.append(
                        f"{repo}: {recorded[:12]} → pin {pin[:12]}"
                    )
                continue
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
                reasons.append(
                    f"{repo}: {recorded[:12]} → {head[:12]}"
                )
        if reasons:
            selected.append(
                {
                    "suite": suite,
                    "name": name,
                    "reason": "; ".join(reasons),
                    "repos": repos,
                }
            )
    return selected


def force_all_selection(affected_map: dict) -> list[dict]:
    """Every mapped, repo-bearing entry, freshness ignored (force_all).

    Runs the same per-entry validation as ``select`` so the workflow's
    force_all path cannot drift from the normal one.
    """
    selected: list[dict] = []
    for entry in affected_map.get("suites", []):
        name = _registry_name(entry)
        if not entry.get("repos"):
            continue
        selected.append(
            {
                "suite": entry["suite"],
                "name": name,
                "reason": "force_all",
                "repos": entry["repos"],
            }
        )
    return selected


def runnable_names(selected: list[dict]) -> list[str]:
    """The deduplicated registry names the rerun matrix can dispatch.

    Decisions whose map entry has an explicit null ``name`` (parameter suites
    run by the manual ``run_parameter_comparisons.py`` lane, and ``ci: manual``
    registry suites run only under a supervised ``run_comparison.py``
    invocation) are excluded: dispatching a parameter suite crashes the matrix
    leg with "unknown comparison", and a ci-manual suite is one CI cannot
    execute at all. Malformed names never reach here —
    ``_registry_name`` fails loudly during selection. Order follows first
    appearance.
    """
    names: list[str] = []
    for decision in selected:
        name = decision.get("name")
        if name is not None and name not in names:
            names.append(name)
    return names


def manual_suites(selected: list[dict]) -> list[str]:
    """Selected suites with no CI-runnable registry name (manual lane)."""
    return sorted(d["suite"] for d in selected if d.get("name") is None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--heads-json",
        help="Path to a {repo: sha} JSON map, or - for stdin. Required "
        "unless --force-all.",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Select every mapped suite regardless of freshness (the "
        "workflow's force_all input). Dispatch rules are identical.",
    )
    parser.add_argument(
        "--format",
        choices=("lines", "json", "matrix", "github"),
        default="lines",
        help="lines: one registry name per line; json: full decisions "
        "(including non-runnable ones); matrix: GitHub Actions include-list "
        "JSON; github: $GITHUB_OUTPUT lines (matrix, count, manual_count, "
        "manual).",
    )
    args = parser.parse_args()

    if not AFFECTED_MAP.exists():
        raise SystemExit(
            "comparisons/affected_map.json missing; run generate_affected_map.py"
        )
    affected_map = json.loads(AFFECTED_MAP.read_text())

    if args.force_all:
        selected = force_all_selection(affected_map)
    else:
        if not args.heads_json:
            raise SystemExit("--heads-json is required unless --force-all")
        heads = _load_heads(args.heads_json)
        reports_by_suite = load_reports(affected_map)
        selected = select(affected_map, heads, reports_by_suite)

    names = runnable_names(selected)
    manual = manual_suites(selected)
    if manual:
        print(
            f"note: {len(manual)} stale suite(s) have no CI-runnable registry "
            f"name and are left to the manual parameter lane: "
            + ", ".join(manual),
            file=sys.stderr,
        )

    if args.format == "json":
        print(json.dumps(selected, indent=2))
    elif args.format == "matrix":
        print(json.dumps({"include": [{"name": n} for n in names]}))
    elif args.format == "github":
        # One line per $GITHUB_OUTPUT key; the matrix JSON is single-line.
        print(
            "matrix="
            + json.dumps({"include": [{"name": n} for n in names]})
        )
        print(f"count={len(names)}")
        print(f"manual_count={len(manual)}")
        print("manual=" + " ".join(manual))
    else:
        for name in names:
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
