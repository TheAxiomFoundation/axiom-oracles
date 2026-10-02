#!/usr/bin/env python3
"""Keep a re-emission from replacing a committed dashboard report.

``scripts/commit_refreshed_report.sh`` runs this on every push attempt, after
it has reset to the current tip and restored the leg's own outputs. For each
top-level dashboard report (``dashboard/public/data/*.json``) that differs from
the tip, a working copy marked ``provenance.reemitted_report`` (see
:func:`axiom_oracles.provenance.is_real_run_report`) is put back to the tip's
bytes whenever the tip has a copy of that report.

A re-emission copies the committed numbers, so committing it changes labels,
never results. Over a real run it replaces the provenance that run recorded
(the rulespec SHAs it ran against, its run kind and date) with "re-emitted,
SHA unknown". Over an earlier re-emission it only moves ``generated_at``; the
affected rerun committed such timestamp-only diffs for 35 EUROMOD, UKMOD and
tariff suites sweep after sweep. ``run_comparison.py`` already declines to
publish a re-emission over any existing copy; this is the check at the bot's
push, which no CI workflow sees. It runs against each attempt's tip, not the
leg's starting commit, so a report that lands while the leg runs is protected
too. Only a first report (the tip has no copy) may be a re-emission.

Usage:
    python3 scripts/guard_reemitted_reports.py [--rev REV]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.provenance import is_real_run_report  # noqa: E402

DASHBOARD_DATA = "dashboard/public/data"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # Undecodable bytes become replacement characters: a report that is not
    # valid UTF-8 then fails to parse (not a report) instead of crashing the
    # push loop.
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def changed_reports(rev: str) -> list[str]:
    """Top-level dashboard reports whose working copy differs from ``rev``."""
    out = _git("diff", "--name-only", "-z", rev, "--", f"{DASHBOARD_DATA}/*.json")
    return sorted(
        path
        for path in out.stdout.split("\0")
        if path and Path(path).parent.as_posix() == DASHBOARD_DATA
    )


def _load(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


def reemitted_replacements(rev: str) -> list[str]:
    """Reports whose working copy is a re-emission and that ``rev`` already has."""
    found = []
    for path in changed_reports(rev):
        working = REPO_ROOT / path
        if not working.exists():
            continue
        report = _load(working.read_bytes().decode("utf-8", errors="replace"))
        if not isinstance(report, dict) or is_real_run_report(report):
            continue
        committed = _git("cat-file", "-e", f"{rev}:{path}", check=False)
        if committed.returncode == 0:
            found.append(path)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rev",
        default="HEAD",
        help="Commit whose reports to protect (default: HEAD).",
    )
    args = parser.parse_args(argv)

    restored = reemitted_replacements(args.rev)
    for path in restored:
        # Literal pathspec: a report name containing glob characters must not
        # match (and revert) any neighbouring file.
        _git("--literal-pathspecs", "checkout", args.rev, "--", path)
        message = (
            f"kept the committed report {path}: this leg re-emitted it, and a "
            "re-emission never replaces a committed report"
        )
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Re-emission not committed::{message}")
        else:
            print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
