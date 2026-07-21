#!/usr/bin/env python3
"""Vacuous-verification gate (O3) — blocking schema check + freshness data.

Two guards, one entrypoint:

1. **Oracle-backed check (blocking).** Every registry comparison config must
   actually compare real independent engines — a config that verifies nothing is
   the definition of vacuous verification. A config passes when its registered
   runner type fixes a real external pair (including direct oracle cross-checks)
   and, for the generic ``axiom-oracles-compare`` runner, names a non-``none``
   ``right`` engine. A config that intentionally has no oracle yet must opt out
   explicitly with a top-level ``oracle: none`` **and** a ``reason:`` string;
   silence is a failure. The same rule applies per fixture case: each
   ``<name>.fixtures.yaml`` fixture must declare an ``expected`` outcome for at
   least one engine, or carry ``oracle: none`` + ``reason``.

2. **Executable-surface freshness (writes data; alarm is non-blocking).**
   Every surface marked ``executable`` in ``coverage_overview.json`` should have
   a committed dashboard report younger than :data:`FRESH_MAX_AGE_DAYS`. This
   step recomputes per-suite freshness (report age vs the affected repos' state)
   and writes ``dashboard/public/data/freshness.json`` for the dashboard's
   freshness register. A stale executable surface raises a dashboard alarm row,
   not a CI failure — staleness is an operational signal, not a broken build.
   ``--check`` still fails if ``freshness.json`` is missing or drifts, because a
   stale *committed* freshness artifact would itself be a silent lie.

Usage:
    uv run scripts/check_vacuous_gate.py            # validate + refresh data
    uv run scripts/check_vacuous_gate.py --check    # CI: block on schema/drift
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("PyYAML is required (uv pip install pyyaml).\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
COVERAGE_OVERVIEW = DASHBOARD_DATA_DIR / "coverage_overview.json"
AFFECTED_MAP = COMPARISONS_DIR / "affected_map.json"
FRESHNESS_OUTPUT = DASHBOARD_DATA_DIR / "freshness.json"

#: An executable surface whose latest report is older than this is flagged as a
#: stale freshness alarm on the dashboard (non-blocking).
FRESH_MAX_AGE_DAYS = 14

_RUN_COMPARISON = REPO_ROOT / "scripts" / "run_comparison.py"


def _registered_runner_types() -> set[str]:
    """The keys of run_comparison.py's ``RUNNERS`` table.

    Every registered runner executes a real comparison pair, so registry
    membership *is* the oracle-backed criterion — deriving the set
    from the source of truth means a newly-registered runner (e.g. a UKMOD
    lane added concurrently) can't silently fall out of the gate's coverage.
    Parsed statically (regex) rather than imported so this stays cheap and
    dependency-free.
    """
    import re

    try:
        text = _RUN_COMPARISON.read_text()
    except OSError:
        return set()
    block = re.search(r"RUNNERS\s*=\s*\{(.*?)\}", text, re.DOTALL)
    if not block:
        return set()
    return set(re.findall(r'"([^"]+)"\s*:', block.group(1)))


#: Runner types whose very shape fixes a real comparison pair — the RUNNERS
#: registry, plus a static fallback if parsing ever fails so the gate degrades
#: to "known set" rather than "everything is unbacked".
_ORACLE_BACKED_RUNNERS = _registered_runner_types() or {
    "axiom-encode-tax-ecps-compare",
    "axiom-encode-uk-efrs-compare",
    "axiom-encode-snap-ecps-compare",
    "axiom-oracles-compare",
    "euromod-synthetic-compare",
    "gettsim-synthetic-compare",
}


# ---------------------------------------------------------------------------
# Guard 1: oracle-backed schema check (blocking)
# ---------------------------------------------------------------------------


def _config_oracle_problems(name: str, config: dict) -> list[str]:
    """Return schema problems for one registry comparison config (empty = ok)."""
    problems: list[str] = []

    # Explicit opt-out: `oracle: none` requires a reason. Only triggers when the
    # key is actually present (a missing `oracle` key is not an opt-out — the
    # config is then required to be genuinely oracle-backed below).
    if "oracle" in config and str(config.get("oracle")).strip().lower() == "none":
        if not str(config.get("reason") or "").strip():
            problems.append(
                f"{name}: `oracle: none` requires a non-empty `reason:` "
                "explaining why this comparison has no oracle yet"
            )
        return problems

    runner = config.get("runner") or {}
    runner_type = runner.get("type")
    if runner_type not in _ORACLE_BACKED_RUNNERS:
        problems.append(
            f"{name}: runner type {runner_type!r} is not a known oracle-backed "
            "runner; set `oracle: none` + `reason:` if that is intentional"
        )
        return problems

    # The generic comparator can be pointed at anything; require a real oracle
    # on the right so it can't be a vacuous axiom-vs-axiom (or axiom-vs-nothing)
    # comparison masquerading as verification.
    if runner_type == "axiom-oracles-compare":
        params = runner.get("parameters") or {}
        right = str(params.get("right") or "").strip().lower()
        left = str(params.get("left") or "").strip().lower()
        if not right or right in {"none", ""}:
            problems.append(
                f"{name}: axiom-oracles-compare needs a real `right:` oracle "
                "(got empty/none); set `oracle: none` + `reason:` to opt out"
            )
        elif right == left:
            problems.append(
                f"{name}: axiom-oracles-compare compares {left!r} against "
                f"itself — that verifies nothing"
            )
    return problems


def _fixture_oracle_problems(path: Path, doc: dict) -> list[str]:
    """Each fixture case must declare an expected engine outcome, or opt out."""
    problems: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    fixtures = doc.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        problems.append(f"{rel}: no fixtures[] — a fixtures file must hold cases")
        return problems
    for fixture in fixtures:
        fid = fixture.get("id", "<unnamed>")
        if "oracle" in fixture and str(fixture.get("oracle")).strip().lower() == "none":
            if not str(fixture.get("reason") or "").strip():
                problems.append(
                    f"{rel}: fixture {fid!r} has `oracle: none` without a "
                    "`reason:`"
                )
            continue
        expected = fixture.get("expected")
        if not isinstance(expected, dict) or not any(
            v is not None for v in expected.values()
        ):
            problems.append(
                f"{rel}: fixture {fid!r} declares no `expected:` engine outcome "
                "(and no `oracle: none` + `reason:`) — it verifies nothing"
            )
    return problems


def check_oracle_backed() -> list[str]:
    problems: list[str] = []
    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            doc = yaml.safe_load(path.read_text()) or {}
            problems.extend(_fixture_oracle_problems(path, doc))
            continue
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            continue
        if config.get("kind") == "parameter-suite-list":
            # Parameter suites compare encoded rulespec values against
            # PolicyEngine parameters — oracle-backed by construction. Guard
            # against a suite that declares no comparisons (nothing to verify).
            for suite in config.get("suites") or []:
                if not (suite.get("comparisons") or []):
                    problems.append(
                        f"parameter-oracles.yaml suite {suite.get('suite')!r} "
                        "declares no comparisons — nothing is verified"
                    )
            continue
        if "name" not in config:
            continue
        problems.extend(_config_oracle_problems(config["name"], config))
    return problems


# ---------------------------------------------------------------------------
# Guard 2: executable-surface freshness (data + non-blocking alarms)
# ---------------------------------------------------------------------------


def _report_age_days(report: dict) -> float | None:
    """Age in days from a report's provenance.generated_at (UTC)."""
    stamp = (report.get("provenance") or {}).get("generated_at")
    if not stamp:
        return None
    try:
        when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def _load_dashboard_reports() -> dict[str, dict]:
    reports: dict[str, dict] = {}
    for path in sorted(DASHBOARD_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("suite"):
            reports[data["suite"]] = data
    return reports


def build_freshness() -> dict:
    """Per-suite freshness for executable surfaces + a stale-alarm summary."""
    reports = _load_dashboard_reports()
    affected = {}
    if AFFECTED_MAP.exists():
        try:
            affected = {
                e["suite"]: e
                for e in json.loads(AFFECTED_MAP.read_text()).get("suites", [])
            }
        except json.JSONDecodeError:
            affected = {}

    # Executable Axiom surfaces from the coverage overview: (program, jurisdiction).
    executable: list[dict] = []
    if COVERAGE_OVERVIEW.exists():
        try:
            overview = json.loads(COVERAGE_OVERVIEW.read_text())
            executable = [
                p
                for p in (overview.get("axiom") or {}).get("programs", [])
                if p.get("status") == "executable"
            ]
        except json.JSONDecodeError:
            executable = []

    # Only TIME-INVARIANT facts are committed here: report timestamps, the
    # rulespec repos each suite is affected by, and the SHAs it ran against.
    # Staleness (age > max_age) and the resulting alarms are DERIVED at render
    # time from `generated_at`, never stored — a stored `stale` flag would flip
    # as wall-clock advances and make the committed file spuriously "drift",
    # failing --check with no code or report change.
    suites_out: list[dict] = []
    for suite, report in sorted(reports.items()):
        provenance = report.get("provenance") or {}
        entry = affected.get(suite, {})
        prov_rulespecs = provenance.get("rulespecs") or []
        ran_against = {
            r.get("repo"): r.get("sha") for r in prov_rulespecs if r.get("repo")
        }
        suites_out.append(
            {
                "suite": suite,
                "generated_at": provenance.get("generated_at"),
                "run_kind": provenance.get("run_kind"),
                "affected_repos": entry.get("repos", []),
                "ran_against": ran_against,
                "unstamped": provenance.get("generated_at") is None,
            }
        )

    # Executable surfaces + the report suites that verify each one, so the
    # dashboard can compute both the "stale report" and "no report at all"
    # alarms at render (again, no time-dependent state stored here).
    surfaces_out: list[dict] = []
    for program in executable:
        jurisdiction = program.get("jurisdiction")
        pname = program.get("program")
        matched = [
            s["suite"]
            for s in suites_out
            if _suite_matches_program(s["suite"], pname, jurisdiction)
        ]
        surfaces_out.append(
            {
                "program": pname,
                "jurisdiction": jurisdiction,
                "suites": matched,
            }
        )

    return {
        "schema": "axiom_oracles.freshness.v1",
        "_comment": (
            "Generated by scripts/check_vacuous_gate.py. TIME-INVARIANT report "
            "provenance timestamps + the rulespec repos each suite is affected "
            "by. Staleness (age > max_age_days) and freshness alarms are derived "
            "at render time from generated_at — never stored — so this file only "
            "changes when a report or the affected map changes."
        ),
        "max_age_days": FRESH_MAX_AGE_DAYS,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suites": suites_out,
        "executable_surfaces": surfaces_out,
    }


#: Program families whose coverage rows map to a differently-slugged suite
#: token (coverage `program` id → the token used in suite slugs).
_PROGRAM_SUITE_TOKENS = {
    "federal_income_tax": "fiit",
    "medicaid_eligibility_groups": "medicaid",
    "medicaid_chip_bhp_thresholds": "health",
    "state_income_tax": "state-income-tax",
    "nyc_income_tax": "nyc-income-tax",
}


def _suite_matches_program(suite: str, program: str | None, jurisdiction: str | None) -> bool:
    """Link a coverage (program, jurisdiction) row to a report suite.

    Suites are slugged like ``co-snap-ecps`` / ``ny-tanf-ecps`` / ``fiit-ecps``;
    coverage rows carry ``program`` + a ``jurisdiction`` that is either a US
    state (``CO``) or the national marker ``US``. A US-national row matches any
    suite of its program family regardless of a state token; a state row also
    requires the state token in the slug. The program token comes from
    :data:`_PROGRAM_SUITE_TOKENS` where the coverage id and the slug differ.
    """
    slug = suite.lower()
    juris = str(jurisdiction or "").lower()
    prog = str(program or "").lower()
    token = _PROGRAM_SUITE_TOKENS.get(prog, prog.split("_")[0] if prog else "")
    if token and token not in slug:
        return False
    # `us` is the national marker, not a slug substring; only a real state
    # jurisdiction must appear in the slug.
    if juris and juris != "us" and juris not in slug:
        return False
    return bool(token or juris)


def _freshness_comparable(doc: dict) -> dict:
    """Freshness doc minus the top-level 'now' timestamp, for --check.

    Per-suite ``generated_at`` is a *report* fact (when the report was
    generated), so it is time-invariant and kept — it changes only when a report
    is rerun. The only wall-clock field is the doc-level ``generated_at`` ('now'
    at generation), which is dropped so re-running the generator without any
    report change compares equal.
    """
    stable = dict(doc)
    stable.pop("generated_at", None)
    return stable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: fail on schema problems or committed-freshness drift.",
    )
    args = parser.parse_args()

    problems = check_oracle_backed()
    freshness = build_freshness()

    if args.check:
        if problems:
            for problem in problems:
                sys.stderr.write(f"vacuous-gate FAILED: {problem}\n")
            return 1
        # Freshness structure (minus wall-clock age) must match the committed
        # file, so a stale committed freshness artifact can't lie silently.
        if not FRESHNESS_OUTPUT.exists():
            sys.stderr.write(
                "vacuous-gate FAILED: dashboard/public/data/freshness.json "
                "missing; run `uv run scripts/check_vacuous_gate.py`\n"
            )
            return 1
        committed = json.loads(FRESHNESS_OUTPUT.read_text())
        if _freshness_comparable(committed) != _freshness_comparable(freshness):
            sys.stderr.write(
                "vacuous-gate FAILED: freshness.json is stale (suite/surface set "
                "or report timestamps changed); run "
                "`uv run scripts/check_vacuous_gate.py`\n"
            )
            return 1
        unstamped = [s for s in freshness["suites"] if s["unstamped"]]
        print(
            f"vacuous-gate OK: {len(list(COMPARISONS_DIR.glob('*.yaml')))} configs "
            f"oracle-backed; {len(freshness['suites'])} suites, "
            f"{len(freshness['executable_surfaces'])} executable surfaces, "
            f"{len(unstamped)} suite(s) awaiting provenance"
        )
        return 0

    if problems:
        for problem in problems:
            sys.stderr.write(f"vacuous-gate FAILED: {problem}\n")
        # Still write freshness so the data refresh isn't blocked by an unrelated
        # schema problem the author is mid-fixing; but signal failure.
        FRESHNESS_OUTPUT.write_text(json.dumps(freshness, indent=2) + "\n")
        return 1

    FRESHNESS_OUTPUT.write_text(json.dumps(freshness, indent=2) + "\n")
    print(
        f"Wrote {FRESHNESS_OUTPUT.relative_to(REPO_ROOT)}: "
        f"{len(freshness['suites'])} suites, "
        f"{len(freshness['executable_surfaces'])} executable surfaces"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
