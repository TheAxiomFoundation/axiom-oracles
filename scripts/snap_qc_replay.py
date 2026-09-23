#!/usr/bin/env python3
"""Drive and gate the live SNAP QC replay lane (.github/workflows/snap-qc-replay.yml).

The weekly comparison matrix and the 6-hourly affected rerun run the SNAP QC
suites on bare runners. Those runners have no engine binary and no QC
public-use file, so ``scripts/run_comparison.py`` re-emits the committed
dashboard report (``provenance.reemitted_report: true``). Those legs stay
green whether or not the replay still works: the California replay stopped
compiling after rulespec-us#1176 (2026-07-30) and nothing failed. The live
lane provisions the engine built at rulespec-us's
``axiom_artifact_rules_engine_ref``, a rulespec-us checkout, and the pinned
PUF, runs each suite with ``--require-live``, and then ``check`` accepts only
an executed, exact report.

Subcommands:

* ``suites``: the suites to replay. Every entry in :data:`REQUIRED_SUITES`
  always runs, so a moved or deleted composition fails its leg instead of
  dropping out of the matrix. A :data:`PENDING_SUITES` entry joins once its
  composition exists in the rulespec-us checkout. Every registered
  ``snap-qc-compare`` suite must appear in exactly one of the two, so a new
  suite cannot silently stay out of the lane.
* ``fetch-puf``: materialize the pinned PUF for each fiscal year the suites
  replay, re-verifying the kept zip against ``SNAP_QC_PINS`` on every call.
* ``check``: assert that one suite's report was really computed and is
  exact. That means no re-emission; at least one case, every one compared;
  zero benefit mismatches, error cases and error rows; every stage concept
  compared on every case with no mismatch and no missing side; and the
  expected rulespec-us SHA and engine binary. On failure it names the suite
  and its first divergent cases.

Usage:
    uv run scripts/snap_qc_replay.py suites --rulespec-root ../rulespec-us
    uv run scripts/snap_qc_replay.py fetch-puf --archive-dir A --data-dir D
    uv run scripts/snap_qc_replay.py check ca-snap-qc --report-dir R \\
        --log R/replay.log --expect-rulespec-sha <sha> --expect-axiom-binary B

Inside GitHub Actions, ``suites`` also writes ``$GITHUB_OUTPUT``. ``suites``
and ``check`` append Markdown to ``$GITHUB_STEP_SUMMARY`` and print
``::error``/``::warning`` annotations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

COMPARISONS_DIR = REPO_ROOT / "comparisons"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
RUNNER_TYPE = "snap-qc-compare"
RULESPEC_US = "TheAxiomFoundation/rulespec-us"
BENEFIT_STAGE = "benefit"

#: Suites whose state SNAP composition is merged on rulespec-us main. The live
#: lane executes every one on every run; a composition that disappears fails
#: its leg loudly instead of shrinking the matrix.
REQUIRED_SUITES: tuple[str, ...] = (
    "co-snap-qc",
    "ny-snap-qc",
    "ca-snap-qc",
    "az-snap-qc",
    "ga-snap-qc",
    "md-snap-qc",
)

#: Registered suites whose composition has not landed on rulespec-us main,
#: with the tracker that lands it. A pending suite joins the matrix as soon
#: as its composition exists in the checkout, and the run summary then asks
#: for it to move to REQUIRED_SUITES.
PENDING_SUITES: dict[str, str] = {
    "tx-snap-qc": "TheAxiomFoundation/rulespec-us#888, implemented by PR #891",
}

#: Divergent cases listed per failing suite.
DEFAULT_MAX_CASES = 10


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def registered_suites(comparisons_dir: Path = COMPARISONS_DIR) -> dict[str, dict]:
    """Every ``snap-qc-compare`` registry entry, keyed by suite name."""
    suites: dict[str, dict] = {}
    for path in sorted(comparisons_dir.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            continue
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            continue
        if (config.get("runner") or {}).get("type") == RUNNER_TYPE:
            suites[str(config["name"])] = config
    return suites


def classification_errors(registered: Iterable[str]) -> list[str]:
    """Drift between the registry and the REQUIRED/PENDING classification."""
    registered = set(registered)
    required, pending = set(REQUIRED_SUITES), set(PENDING_SUITES)
    errors = []
    for name in sorted(required & pending):
        errors.append(f"{name} is both required and pending")
    for name in sorted(registered - required - pending):
        errors.append(
            f"{name} is a registered {RUNNER_TYPE} suite but is neither in "
            "REQUIRED_SUITES nor PENDING_SUITES (scripts/snap_qc_replay.py)"
        )
    for name in sorted((required | pending) - registered):
        errors.append(
            f"{name} is classified in scripts/snap_qc_replay.py but no "
            f"comparisons/*.yaml registers it as a {RUNNER_TYPE} suite"
        )
    return errors


def composition_path(config: dict) -> Path:
    """The suite's SNAP composition, relative to the rulespec-us root."""
    from axiom_oracles.bridges.snap_qc_compare import QC_JURISDICTIONS

    jurisdiction = str(config["runner"]["parameters"]["jurisdiction"])
    return QC_JURISDICTIONS[jurisdiction].program


def fiscal_year(config: dict) -> int:
    # Mirrors run_comparison._run_snap_qc_compare's default.
    return int(config["runner"]["parameters"].get("fiscal_year", 2024))


def fiscal_years(registered: dict[str, dict]) -> list[int]:
    """Every fiscal year a registered suite replays (what ``fetch-puf`` fetches)."""
    return sorted({fiscal_year(config) for config in registered.values()})


def puf_cache_key(years: Iterable[int]) -> str:
    """A CI cache key that changes whenever any of the years' pins changes."""
    from axiom_oracles.populations.snap_qc import SNAP_QC_PINS

    identity = ";".join(
        f"{year}:{SNAP_QC_PINS[year].url}:{SNAP_QC_PINS[year].sha256}"
        for year in sorted(years)
    )
    return "snap-qc-puf-" + hashlib.sha256(identity.encode()).hexdigest()[:32]


def select_suites(
    rulespec_root: Path,
    *,
    only: Sequence[str] = (),
    registered: dict[str, dict] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(suites to replay, landed pending suites, pending notes)``.

    Raises ``SystemExit`` on classification drift or an unknown ``only`` name.
    """
    registered = registered_suites() if registered is None else registered
    errors = classification_errors(registered)
    unknown = sorted(set(only) - set(registered))
    if unknown:
        errors.append(
            f"unknown {RUNNER_TYPE} suite(s): {', '.join(unknown)}; "
            f"registered: {', '.join(sorted(registered))}"
        )
    if errors:
        raise SystemExit("\n".join(errors))

    wanted = set(only) if only else set(registered)
    selected = [name for name in REQUIRED_SUITES if name in wanted]
    landed: list[str] = []
    notes: list[str] = []
    for name, tracker in PENDING_SUITES.items():
        if name not in wanted:
            continue
        program = composition_path(registered[name])
        if (rulespec_root / program).exists():
            selected.append(name)
            landed.append(name)
        else:
            notes.append(
                f"{name}: not replayed; its composition {program} is not in "
                f"this rulespec-us checkout yet ({tracker})"
            )
    return selected, landed, notes


# --------------------------------------------------------------------------- #
# Checking one suite's report
# --------------------------------------------------------------------------- #


def find_report(report_dir: Path, config: dict) -> Path | None:
    """The report ``run_comparison.py`` published for this suite, if any."""
    basename = config["artifacts"]["report_basename"]
    candidates = [
        path
        for path in report_dir.glob(f"{basename}-*.json")
        if not path.name.startswith(".")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def check_report(
    report: dict,
    *,
    suite: str,
    expect_rulespec_sha: str | None = None,
    expect_axiom_binary: Path | None = None,
) -> list[str]:
    """Every reason ``report`` is not a live, exact run of ``suite``."""
    failures: list[str] = []
    provenance = report.get("provenance") or {}
    summary = report.get("summary") or {}

    if report.get("suite") != suite:
        failures.append(f"report is for suite {report.get('suite')!r}, not {suite!r}")
    if provenance.get("reemitted_report"):
        source = provenance.get("reemitted_from")
        failures.append(
            "re-emitted the committed report instead of running the replay"
            + (f" (numbers from {json.dumps(source, sort_keys=True)})" if source else "")
        )

    case_count = int(report.get("case_count") or 0)
    if case_count <= 0:
        failures.append("no cases were compared")
    comparison_count = summary.get("comparison_count")
    if comparison_count != case_count:
        failures.append(
            f"summary.comparison_count {comparison_count} != case_count {case_count}"
        )

    mismatch_count = int(summary.get("mismatch_count") or 0)
    mismatch_rows = report.get("mismatches") or []
    if mismatch_count or mismatch_rows:
        failures.append(
            f"{mismatch_count} of {case_count} cases miss the QC benefit "
            f"({len(mismatch_rows)} mismatch rows)"
        )
    error_case_count = int(summary.get("error_case_count") or 0)
    error_rows = report.get("errors") or []
    if error_case_count or error_rows:
        failures.append(
            f"{error_case_count} error cases and {len(error_rows)} error rows"
        )
    stages = summary.get("stages") or []
    if stages:
        rendered = ", ".join(f"{row.get('stage')}={row.get('count')}" for row in stages)
        failures.append(f"first divergent stages: {rendered}")

    concepts = {row.get("id") for row in report.get("concepts") or []}
    aggregates = {row.get("concept"): row for row in report.get("aggregates") or []}
    for concept in sorted(concepts - set(aggregates), key=str):
        failures.append(f"stage {concept} was never compared")
    for concept in sorted(aggregates, key=str):
        row = aggregates[concept]
        problems = []
        if row.get("comparison_count") != case_count:
            problems.append(f"compared {row.get('comparison_count')}/{case_count}")
        if row.get("mismatch_count"):
            problems.append(f"{row['mismatch_count']} mismatches")
        for side in ("missing_left_count", "missing_right_count"):
            if row.get(side):
                problems.append(f"{row[side]} {side.removesuffix('_count')}")
        if problems:
            failures.append(f"stage {concept}: {', '.join(problems)}")

    if expect_rulespec_sha:
        ran_against = [
            entry.get("sha")
            for entry in provenance.get("rulespecs") or []
            if entry.get("repo") == RULESPEC_US
        ]
        if ran_against != [expect_rulespec_sha]:
            failures.append(
                f"ran against {RULESPEC_US} {ran_against or 'unknown'}, "
                f"expected {expect_rulespec_sha}"
            )
    if expect_axiom_binary is not None:
        used = (summary.get("provenance") or {}).get("axiom_binary")
        if not used or Path(used).resolve() != expect_axiom_binary.resolve():
            failures.append(
                f"ran engine binary {used or 'unknown'}, expected {expect_axiom_binary}"
            )
    return failures


def divergent_cases(report: dict, max_cases: int = DEFAULT_MAX_CASES) -> list[str]:
    """Human-readable lines for the first divergent and erroring cases."""
    lines = []
    mismatches = report.get("mismatches") or []
    for row in mismatches[:max_cases]:
        stage = row.get("stage") or BENEFIT_STAGE
        qc, axiom = row.get("qc") or {}, row.get("axiom") or {}
        line = (
            f"case {row.get('case_id')} ({row.get('yrmonth')}): first divergent "
            f"stage {stage}: QC {qc.get(stage)} vs Axiom {axiom.get(stage)}"
        )
        if stage != BENEFIT_STAGE:
            line += (
                f"; benefit QC {qc.get(BENEFIT_STAGE)} vs Axiom "
                f"{axiom.get(BENEFIT_STAGE)}"
            )
        lines.append(line)
    if len(mismatches) > max_cases:
        lines.append(f"... and {len(mismatches) - max_cases} more mismatched cases")
    errors = report.get("errors") or []
    for row in errors[:max_cases]:
        lines.append(f"case {row.get('case_id')}: {row.get('error')}")
    if len(errors) > max_cases:
        lines.append(f"... and {len(errors) - max_cases} more error rows")
    return lines


_EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Exit)\b.*")
_REFUSAL = re.compile(r": --require-live: ")


def log_shows_failure(log_text: str) -> bool:
    """Whether a replay log records a raised exception or a --require-live refusal.

    ``check`` uses this so that a report left in a reused directory by an
    earlier run can never pass for a replay that just failed.
    """
    return "Traceback (most recent call last):" in log_text or bool(
        _REFUSAL.search(log_text)
    )


def failure_excerpt(log_text: str, *, context: int = 4) -> str:
    """Why a replay failed, from its log.

    The raised exception plus its trailing detail lines when there is a
    traceback; otherwise the log's last lines, which hold a ``SystemExit``
    message (``--require-live``) and the skip reason printed before it.
    """
    lines = [line.rstrip() for line in log_text.splitlines() if line.strip()]
    for index in range(len(lines) - 1, -1, -1):
        if _EXCEPTION_LINE.match(lines[index]):
            return "\n".join(lines[index : index + 1 + context])
    return "\n".join(lines[-2:]) if lines else "(empty log)"


def committed_case_count(config: dict) -> int | None:
    """``case_count`` of the suite's dashboard report as committed at HEAD.

    Read from git, not the working tree: the run itself rewrites the working
    copy of the dashboard report before ``check`` runs.
    """
    filename = (config.get("dashboard") or {}).get("filename")
    if not filename:
        return None
    relative = (DASHBOARD_DATA_DIR / filename).relative_to(REPO_ROOT).as_posix()
    try:
        committed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{relative}"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        return int(json.loads(committed).get("case_count") or 0)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# GitHub Actions plumbing
# --------------------------------------------------------------------------- #


def _escape_annotation(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(level: str, title: str, message: str) -> None:
    print(f"::{level} title={_escape_annotation(title)}::{_escape_annotation(message)}")


def _append(env_var: str, text: str) -> None:
    path = os.environ.get(env_var)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #


def cmd_suites(args: argparse.Namespace) -> int:
    only = [name for name in re.split(r"[\s,]+", args.only or "") if name]
    registered = registered_suites()
    selected, landed, notes = select_suites(
        args.rulespec_root, only=only, registered=registered
    )
    for note in notes:
        print(note)
    if not selected:
        raise SystemExit("no SNAP QC suites selected")
    years = fiscal_years(registered)

    print(f"Replaying {len(selected)} suite(s): {', '.join(selected)}")
    for name in landed:
        annotate(
            "warning",
            f"{name} composition has landed",
            f"{name}'s composition is now on rulespec-us, so this run replays "
            "it. Move it from PENDING_SUITES to REQUIRED_SUITES in "
            "scripts/snap_qc_replay.py.",
        )

    _append(
        "GITHUB_OUTPUT",
        f"suites={json.dumps(selected, separators=(',', ':'))}\n"
        f"puf_cache_key={puf_cache_key(years)}\n",
    )
    summary = ["## SNAP QC live replay: suites", ""]
    summary += [f"- {name}" + (" (pending suite, landed)" if name in landed else "") for name in selected]
    summary += [f"- {note}" for note in notes]
    _append("GITHUB_STEP_SUMMARY", "\n".join(summary) + "\n\n")
    if args.json:
        print(
            json.dumps(
                {
                    "suites": selected,
                    "landed_pending": landed,
                    "notes": notes,
                    "puf_cache_key": puf_cache_key(years),
                }
            )
        )
    return 0


def cmd_fetch_puf(args: argparse.Namespace) -> int:
    from axiom_oracles.populations.snap_qc import SNAP_QC_PINS, fetch_pinned_puf

    for year in args.fiscal_year or fiscal_years(registered_suites()):
        path = fetch_pinned_puf(year, args.data_dir, archive_dir=args.archive_dir)
        pin = SNAP_QC_PINS[year]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(
            f"FY{year}: {pin.url} (zip sha256 {pin.sha256}, verified) -> "
            f"{path} ({path.stat().st_size} bytes, csv sha256 {digest})"
        )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    registered = registered_suites()
    if args.suite not in registered:
        raise SystemExit(f"unknown {RUNNER_TYPE} suite {args.suite!r}")
    config = registered[args.suite]
    report_path = find_report(args.report_dir, config)

    details: list[str] = []
    row = {"cases": "-", "benefit": "-", "stages": "-", "errors": "-", "rulespec": "-"}
    log_text = (
        args.log.read_text(errors="replace") if args.log and args.log.exists() else ""
    )
    if report_path is None:
        failures = [
            f"no report was published under {args.report_dir}: the replay failed "
            "before writing one"
        ]
        if log_text:
            details = failure_excerpt(log_text).splitlines()
    else:
        report = json.loads(report_path.read_text())
        failures = check_report(
            report,
            suite=args.suite,
            expect_rulespec_sha=args.expect_rulespec_sha,
            expect_axiom_binary=args.expect_axiom_binary,
        )
        details = divergent_cases(report, args.max_cases)
        if args.replay_failed or log_shows_failure(log_text):
            # Either the replay raised after publishing (e.g. a versioned
            # case-chunk refresh), or it failed and the report found here was
            # left by an earlier run. Either way the report alone must not
            # turn a failed replay into a PASS.
            failures.append(
                "the replay failed (this report may be from an earlier run): "
                + (failure_excerpt(log_text).replace("\n", " ") if log_text else "no log")
            )
        summary = report.get("summary") or {}
        case_count = int(report.get("case_count") or 0)
        stage_mismatches = sum(
            int(agg.get("mismatch_count") or 0) for agg in report.get("aggregates") or []
        )
        shas = [
            str(entry.get("sha"))[:12]
            for entry in (report.get("provenance") or {}).get("rulespecs") or []
            if entry.get("repo") == RULESPEC_US
        ]
        row = {
            "cases": str(case_count),
            "benefit": f"{summary.get('match_count')}/{summary.get('comparison_count')}",
            "stages": str(stage_mismatches),
            "errors": str(int(summary.get("error_case_count") or 0) + len(report.get("errors") or [])),
            "rulespec": ", ".join(shas) or "-",
        }
        committed = committed_case_count(config)
        if committed is not None and committed != case_count:
            annotate(
                "warning",
                f"{args.suite} case count changed",
                f"{args.suite} replayed {case_count} cases; the committed "
                f"dashboard report has {committed}.",
            )

    status = "FAIL" if failures else "PASS"
    print(f"{args.suite}: {status}" + (f" ({report_path})" if report_path else ""))
    for failure in failures:
        print(f"  - {failure}")
    for line in details:
        print(f"    {line}")
    if failures:
        message = "; ".join(failures)
        if details:
            message += "\n" + "\n".join(details)
        annotate("error", f"SNAP QC replay failed: {args.suite}", message)

    table = [
        f"### {args.suite}: {status}",
        "",
        "| cases | benefit exact | stage mismatches | errors | rulespec-us |",
        "| ---: | ---: | ---: | ---: | --- |",
        f"| {row['cases']} | {row['benefit']} | {row['stages']} | {row['errors']} | {row['rulespec']} |",
        "",
    ]
    table += [f"- {failure}" for failure in failures]
    if details:
        table += ["", "```", *details, "```"]
    _append("GITHUB_STEP_SUMMARY", "\n".join(table) + "\n\n")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    suites = sub.add_parser("suites", help="emit the suites to replay")
    suites.add_argument("--rulespec-root", type=Path, required=True)
    suites.add_argument(
        "--only",
        default="",
        help="comma/space-separated suite names to restrict to (blank = all)",
    )
    suites.add_argument("--json", action="store_true", help="also print JSON")
    suites.set_defaults(func=cmd_suites)

    fetch = sub.add_parser("fetch-puf", help="materialize the pinned PUF(s)")
    fetch.add_argument("--archive-dir", type=Path, required=True)
    fetch.add_argument("--data-dir", type=Path, required=True)
    fetch.add_argument(
        "--fiscal-year",
        type=int,
        action="append",
        help="repeatable; default: every fiscal year a registered suite replays",
    )
    fetch.set_defaults(func=cmd_fetch_puf)

    check = sub.add_parser("check", help="assert one suite's report is live and exact")
    check.add_argument("suite")
    check.add_argument("--report-dir", type=Path, required=True)
    check.add_argument("--log", type=Path, default=None)
    check.add_argument("--expect-rulespec-sha", default=None)
    check.add_argument("--expect-axiom-binary", type=Path, default=None)
    check.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES)
    check.add_argument(
        "--replay-failed",
        action="store_true",
        help="the replay step exited nonzero (fails the check even if it published)",
    )
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
