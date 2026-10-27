#!/usr/bin/env python3
"""Generate the per-suite runnable-program composition record.

For each conformance-covered suite in a committed universe
(``conformance/<jur>.yaml``), record the runnable Axiom program the harness
composes — the RuleSpec import-set (identical to what ``axiom_oracles.cli``
builds when ``--axiom-program`` is omitted), its repo-relative files, the query
entity, its flat and record-targeted supplied inputs and relations, and the
engine->input bridge (including target records and transforms) — into
``conformance/compositions/<jur>.yaml``.

The record is derived, never hand-invented: it reads the same suite definitions
and the same import derivation the runner uses, so it cannot describe a program
the harness would not run. ``--check`` re-derives and fails if the committed
record drifts from the suites (the ``generate_conformance_universe --check``
pattern), so a suite change that alters any of those structural inputs cannot
land without refreshing the record.

Usage::

    uv run scripts/generate_conformance_compositions.py be         # write be.yaml
    uv run scripts/generate_conformance_compositions.py be --check  # verify; nonzero on drift
    uv run scripts/generate_conformance_compositions.py --all        # every jurisdiction
    uv run scripts/generate_conformance_compositions.py --all --check
    uv run scripts/generate_conformance_compositions.py --list       # configured jurisdictions
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.conformance.compositions import (  # noqa: E402
    build_compositions_document,
    compositions_path,
    parse_if_exists,
    serialize,
)

#: Jurisdictions whose covered suites run the EUROMOD-synthetic Axiom lane, so
#: the composition is the concept-derived RuleSpec import-set. ``be`` is the
#: committed lane today; other EUROMOD-lane jurisdictions can be added here once
#: their covered suites use the same concept-derived program construction.
JURISDICTIONS: tuple[str, ...] = ("be",)


def _generate(jurisdiction: str, *, check: bool) -> int:
    output_path = compositions_path(jurisdiction)
    document = build_compositions_document(jurisdiction)
    serialized = serialize(document)

    if check:
        committed = parse_if_exists(output_path)
        if committed is None:
            sys.stderr.write(
                f"conformance/compositions/{jurisdiction}.yaml missing; run "
                f"`uv run scripts/generate_conformance_compositions.py {jurisdiction}`.\n"
            )
            return 1
        if output_path.read_text() != serialized:
            sys.stderr.write(
                f"conformance/compositions/{jurisdiction}.yaml is stale; run "
                f"`uv run scripts/generate_conformance_compositions.py {jurisdiction}` "
                "(a covered suite's program composition changed).\n"
            )
            return 1
        print(
            f"conformance compositions[{jurisdiction}] OK: "
            f"{len(document.compositions)} covered suite(s)"
        )
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized)
    print(
        f"Wrote {output_path.relative_to(REPO_ROOT)} "
        f"({len(document.compositions)} covered suite(s))."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "jurisdiction",
        nargs="?",
        help="Jurisdiction key (be). Omit with --all.",
    )
    parser.add_argument("--all", action="store_true", help="Process every jurisdiction.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI: fail if the committed record drifts from the suites.",
    )
    parser.add_argument("--list", action="store_true", help="List configured jurisdictions.")
    args = parser.parse_args()

    if args.list:
        for jurisdiction in JURISDICTIONS:
            print(jurisdiction)
        return 0

    if args.all:
        jurisdictions: tuple[str, ...] = JURISDICTIONS
    elif args.jurisdiction:
        if args.jurisdiction not in JURISDICTIONS:
            parser.error(
                f"unknown jurisdiction {args.jurisdiction!r}; "
                f"configured: {', '.join(JURISDICTIONS)}"
            )
        jurisdictions = (args.jurisdiction,)
    else:
        parser.error("give a jurisdiction or --all")

    status = 0
    for jurisdiction in jurisdictions:
        status |= _generate(jurisdiction, check=args.check)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
