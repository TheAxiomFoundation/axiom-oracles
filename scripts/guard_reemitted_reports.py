#!/usr/bin/env python3
"""Keep a re-emission from replacing a real committed dashboard report.

``scripts/commit_refreshed_report.sh`` runs this on every push attempt, after
it has reset to the current tip and restored the leg's own outputs. For each
top-level dashboard report (``dashboard/public/data/*.json``) that differs from
the tip, a working copy marked ``provenance.reemitted_report`` is put back to
the tip's bytes when the tip's copy came from a real run
(:func:`axiom_oracles.provenance.is_real_run_report`).

A re-emission copies the committed numbers, so committing it can only replace
the real run's provenance (the rulespec SHAs it ran against, its run kind and
date) with "re-emitted, SHA unknown". ``run_comparison.py`` already declines to
publish one over a real report; this is the check at the bot's push, which no
CI workflow sees. It runs against each attempt's tip, not the leg's starting
commit, so a real report that lands while the leg runs is protected too.

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
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=check
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


def downgrades(rev: str) -> list[str]:
    """Reports whose working copy is a re-emission and whose ``rev`` copy is real."""
    found = []
    for path in changed_reports(rev):
        working = REPO_ROOT / path
        if not working.exists():
            continue
        report = _load(working.read_text())
        if not isinstance(report, dict) or is_real_run_report(report):
            continue
        committed = _git("show", f"{rev}:{path}", check=False)
        if committed.returncode != 0:
            continue
        if is_real_run_report(_load(committed.stdout)):
            found.append(path)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rev",
        default="HEAD",
        help="Commit whose real reports to protect (default: HEAD).",
    )
    args = parser.parse_args(argv)

    restored = downgrades(args.rev)
    for path in restored:
        _git("checkout", args.rev, "--", path)
        message = (
            f"kept the real report {path}: this leg re-emitted it, and a "
            "re-emission never replaces a real run"
        )
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Re-emission not committed::{message}")
        else:
            print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
