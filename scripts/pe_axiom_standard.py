#!/usr/bin/env python3
"""Gate: a PolicyEngine policy bug is not done until Axiom has the policy right.

Every mismatch explanation that blames PolicyEngine — an
``upstream_engine_gap`` disposition whose rows' counterpart engine is
PolicyEngine (or that links a PolicyEngine issue), or a known cause owned by
PolicyEngine — must carry:

* the PolicyEngine issue URL (``linked_issue`` or ``evidence.upstream_url``
  for dispositions, ``issue_url`` for known causes), and
* either ``axiom_companion: {legal_ids: [...], tests: [rulespec-us@<sha>:
  <path>.test.yaml#<case>]}`` or ``axiom_encoding_debt: <rulespec issue URL>``.

Explanations that predate the standard are grandfathered in
``conformance/pe-axiom-standard.yaml`` with their computed status. Checked
against every committed version of that file: the grandfathered list may only
shrink, and ``open_max`` (attributions without a companion: declared debt plus
grandfathered) may only fall, except through an appended ``debt_raises``
record.

Usage:
    uv run scripts/pe_axiom_standard.py --check
        CI gate (offline; needs full Git history for the monotonic floor).
    uv run scripts/pe_axiom_standard.py --resolve [--rulespec-checkout rulespec-us=PATH]
        Resolve every companion pointer: test file at the pinned commit, the
        commit on main, the case present and asserting each legal id, and the
        disputed Axiom value when the case is the disputed case. Uses local
        clones when given, else raw.githubusercontent.com + the GitHub API.
    uv run scripts/pe_axiom_standard.py
        Re-pin: drop grandfathered entries that became compliant or vanished
        and tighten open_max. Never loosens.
    uv run scripts/pe_axiom_standard.py --raise-ceiling "<reason>"
        Deliberately raise open_max to the live count and append a
        debt_raises record (date, from, to, reason). Maintainer decision.
    uv run scripts/pe_axiom_standard.py --init
        Bootstrap the ratchet file (refuses when it already exists).
    uv run scripts/pe_axiom_standard.py --suggest --rulespec-checkout rulespec-us=PATH
        Print companion pointers for open attributions whose disputed case id
        already exists as a companion case asserting the concept.
    uv run scripts/pe_axiom_standard.py --summary
        Print the live status counts as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.pe_axiom_standard import (  # noqa: E402
    RATCHET_RELATIVE_PATH,
    CompanionResolver,
    GitHubSource,
    LocalGitSource,
    Ratchet,
    RatchetDocumentError,
    check_history,
    check_records,
    collect_records,
    committed_versions,
    derive_ratchet,
    serialize_ratchet,
    suggest_companions,
    summarize,
)


def _load_committed(repo_root: Path) -> Ratchet | None:
    path = repo_root / RATCHET_RELATIVE_PATH
    if not path.exists():
        return None
    return Ratchet.from_document(yaml.safe_load(path.read_text()))


def _source(args: argparse.Namespace):
    checkouts = {}
    for item in args.rulespec_checkout or []:
        name, _, path = item.partition("=")
        if not name or not path:
            raise SystemExit(f"--rulespec-checkout expects repo=path; got {item!r}")
        checkouts[name] = Path(path).expanduser()
    if checkouts:
        return LocalGitSource(checkouts, main_ref=args.rulespec_main_ref)
    return GitHubSource(
        token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    )


def _fail(problems: list[str]) -> int:
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="CI gate; exit 1 on violations or a loosened ratchet")
    mode.add_argument("--resolve", action="store_true", help="resolve companion pointers against RuleSpec repositories")
    mode.add_argument("--init", action="store_true", help="bootstrap the ratchet file (grandfather current non-compliant attributions)")
    mode.add_argument("--raise-ceiling", metavar="REASON", help="re-pin and deliberately raise open_max to the live count, recording REASON")
    mode.add_argument("--suggest", action="store_true", help="print companion pointers discoverable from disputed case ids")
    mode.add_argument("--summary", action="store_true", help="print the live status summary as JSON")
    parser.add_argument("--rulespec-checkout", action="append", metavar="REPO=PATH", help="local clone for a rulespec repository (repeatable)")
    parser.add_argument("--rulespec-main-ref", default="origin/main", help="main ref inside local clones (default origin/main)")
    parser.add_argument("--no-require-merged", action="store_true", help="with --resolve: do not require pinned commits to be on main")
    args = parser.parse_args(argv)

    records, syntax_errors = collect_records(repo_root)
    ratchet_path = repo_root / RATCHET_RELATIVE_PATH

    if args.summary:
        print(json.dumps(summarize(records), indent=2, sort_keys=True))
        return 0

    if args.suggest:
        suggestions = suggest_companions(records, _source(args))
        print(yaml.safe_dump(suggestions, sort_keys=False, width=200), end="")
        print(
            f"# {len(suggestions)} of {sum(1 for r in records if r.open)} open "
            "attributions have a discoverable companion case",
            file=sys.stderr,
        )
        return 0

    if args.resolve:
        resolver = CompanionResolver(
            _source(args), require_merged=not args.no_require_merged
        )
        problems = list(syntax_errors)
        companions = [r for r in records if r.axiom_status == "companion"]
        for record in companions:
            problems.extend(resolver.resolve(record))
        if problems:
            return _fail(problems)
        print(
            f"pe-axiom companions OK: {len(companions)} companion-backed "
            "attributions resolved"
        )
        return 0

    try:
        committed = _load_committed(repo_root)
    except (yaml.YAMLError, RatchetDocumentError) as exc:
        return _fail([f"{RATCHET_RELATIVE_PATH}: {exc}"])

    if args.init:
        if committed is not None:
            return _fail(
                [
                    f"{RATCHET_RELATIVE_PATH} already exists; the grandfather "
                    "door is closed. Re-pin without --init."
                ]
            )
        if syntax_errors:
            return _fail(syntax_errors)
        document = derive_ratchet(records, None)
        ratchet_path.parent.mkdir(parents=True, exist_ok=True)
        ratchet_path.write_text(serialize_ratchet(document))
        print(
            f"Wrote {RATCHET_RELATIVE_PATH}: {len(document['grandfathered'])} "
            f"grandfathered, open_max {document['open_max']}"
        )
        return 0

    if committed is None:
        return _fail(
            [
                f"{RATCHET_RELATIVE_PATH} is missing: bootstrap it with "
                "`uv run scripts/pe_axiom_standard.py --init`"
            ]
        )

    if args.check:
        problems = list(syntax_errors)
        problems.extend(check_records(records, committed))
        versions, history_errors = committed_versions(repo_root)
        problems.extend(history_errors)
        if versions:
            problems.extend(check_history(committed, versions))
        if problems:
            return _fail(problems)
        # Like conformance_ratchet.py, the check fails on regressions only.
        # Slack (a grandfathered entry resolved, or open below open_max) is
        # reported and a deliberate re-pin tightens it; the report-refresh
        # bot never re-pins, so a transient improvement cannot lock in a
        # floor the next honest run would fail.
        tightened = derive_ratchet(records, committed)
        if tightened["open_max"] < committed.open_max:
            print(
                f"note: open_max can tighten {committed.open_max} -> "
                f"{tightened['open_max']}; re-pin with `uv run "
                "scripts/pe_axiom_standard.py`",
                file=sys.stderr,
            )
        resolved = len(committed.grandfathered) - len(tightened["grandfathered"])
        if resolved > 0:
            print(
                f"note: {resolved} grandfathered entr"
                f"{'y is' if resolved == 1 else 'ies are'} resolved or gone; "
                "re-pin to drop them",
                file=sys.stderr,
            )
        summary = summarize(records)
        checked = "unchecked (no Git history)" if versions is None else (
            f"{len(versions)} committed version(s)"
        )
        print(
            "pe-axiom standard OK: "
            f"{summary['pe_attributed']} PolicyEngine attributions, "
            f"{summary['axiom_companion']} companion-backed, "
            f"{summary['axiom_encoding_debt']} declared debt, "
            f"{len(committed.grandfathered)} grandfathered; "
            f"open {summary['open']} <= open_max {committed.open_max}; "
            f"monotonic vs {checked}"
        )
        return 0

    # Re-pin (optionally with a deliberate raise).
    if syntax_errors:
        return _fail(syntax_errors)
    reason = args.raise_ceiling
    if reason is not None and not reason.strip():
        return _fail(["--raise-ceiling needs a non-empty reason"])
    document = derive_ratchet(records, committed, raise_reason=reason)
    # Re-pinning never absorbs a violation: new or regressed attributions are
    # judged against the COMMITTED grandfathered rows, and the open count
    # against the new ceiling (which only a --raise-ceiling can lift).
    problems = check_records(
        records,
        Ratchet(
            open_max=document["open_max"],
            grandfathered=committed.grandfathered,
        ),
    )
    if problems:
        return _fail(problems)
    ratchet_path.write_text(serialize_ratchet(document))
    raised = len(document.get("debt_raises") or []) > len(committed.debt_raises)
    print(
        f"Wrote {RATCHET_RELATIVE_PATH}: {len(document['grandfathered'])} "
        f"grandfathered, open_max {document['open_max']}"
        + (" (raised; debt_raises record appended)" if raised else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
