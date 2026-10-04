#!/usr/bin/env python
"""Publish the oracle findings ledgers to the dashboard.

The ledgers live in the package (axiom_oracles/data/*_issues.json) and are
edited by hand. The dashboard serves static copies:

- dashboard/public/data/euromod-issues.json: the EUROMOD (JRC, UKMOD) ledger.
- dashboard/public/data/southmod-issues.json: one bundle of every SOUTHMOD
  country ledger, in the dashboard's SOUTHMOD_MODELS order, with a null
  ledger and a note for a model that has none. The SOUTHMOD oracle page
  renders it.

Every SOUTHMOD ledger must pass ``ledger_problems`` (closed field allowlist
and licence lint, axiom_oracles/southmod_issues.py) before it is written or
accepted: the published copy is public, and the SOUTHMOD_A4.0 licence bars
model content from it.

``--check`` rebuilds both files and requires the committed copies to equal
the canonical serialization byte for byte. Parsed-value equality would
accept a numeric-to-boolean edit (``1 == True``) and text-mode reads accept
an LF to CRLF rewrite (the same reasons scripts/generate_dashboard_overview.py
compares bytes).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.southmod_issues import (  # noqa: E402
    SOUTHMOD_MODELS,
    ledger_problems,
)

PACKAGE_DATA = REPO_ROOT / "axiom_oracles" / "data"
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "public" / "data"
COMPARISONS = REPO_ROOT / "comparisons"
EUROMOD_SOURCE = PACKAGE_DATA / "euromod_issues.json"
EUROMOD_OUT = DASHBOARD_DATA / "euromod-issues.json"
SOUTHMOD_OUT = DASHBOARD_DATA / "southmod-issues.json"
BUNDLE_SCHEMA = "axiom_oracles.southmod_issues_bundle.v1"
GENERATOR = "scripts/publish_issue_ledgers.py"


def serialize(document: Any) -> bytes:
    """The one canonical encoding both outputs are written and checked in."""
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8"))


def build_southmod_bundle(
    package_data: Path = PACKAGE_DATA,
    comparisons_dir: Path = COMPARISONS,
) -> tuple[dict[str, Any], list[str]]:
    """The SOUTHMOD bundle and every problem that bars publishing it."""
    models = []
    problems = []
    for model in SOUTHMOD_MODELS:
        if model.ledger is None:
            if (package_data / f"{model.model.lower()}_issues.json").exists():
                problems.append(
                    f"{model.model.lower()}_issues.json exists but the "
                    f"{model.model} entry in axiom_oracles/southmod_issues.py "
                    "registers no ledger"
                )
            models.append(
                {
                    "region": model.region,
                    "model": model.model,
                    "source": None,
                    "note": model.no_ledger_note,
                    "ledger": None,
                }
            )
            continue
        path = package_data / model.ledger
        if not path.exists():
            problems.append(f"axiom_oracles/data/{model.ledger} missing")
            continue
        ledger = _read_json(path)
        problems.extend(
            ledger_problems(model.region, ledger, comparisons_dir=comparisons_dir)
        )
        models.append(
            {
                "region": model.region,
                "model": model.model,
                "source": f"axiom_oracles/data/{model.ledger}",
                "ledger": ledger,
            }
        )
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "generated_by": GENERATOR,
        "note": (
            "Generated from the axiom_oracles/data/<model>_issues.json ledgers; "
            f"edit those and run `uv run {GENERATOR}`, never this file."
        ),
        "models": models,
    }
    return bundle, problems


def build_outputs(
    package_data: Path = PACKAGE_DATA,
    comparisons_dir: Path = COMPARISONS,
) -> tuple[dict[str, bytes], list[str]]:
    """Output name -> canonical bytes, plus publishing problems."""
    bundle, problems = build_southmod_bundle(package_data, comparisons_dir)
    euromod = _read_json(package_data / EUROMOD_SOURCE.name)
    return (
        {
            EUROMOD_OUT.name: serialize(euromod),
            SOUTHMOD_OUT.name: serialize(bundle),
        },
        problems,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if a published ledger is missing or stale; write nothing",
    )
    args = parser.parse_args(argv)

    outputs, problems = build_outputs(PACKAGE_DATA, COMPARISONS)
    if problems:
        print(
            "Refusing to publish: the SOUTHMOD ledgers fail validation "
            "(axiom_oracles/southmod_issues.py):",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if args.check:
        failed = False
        for name, expected in outputs.items():
            path = DASHBOARD_DATA / name
            rel = f"dashboard/public/data/{name}"
            if not path.exists():
                print(f"{rel} missing; run `uv run {GENERATOR}`.", file=sys.stderr)
                failed = True
            elif path.read_bytes() != expected:
                print(
                    f"{rel} is stale (bytes differ from the canonical "
                    f"serialization of its source ledgers); run "
                    f"`uv run {GENERATOR}`.",
                    file=sys.stderr,
                )
                failed = True
        if failed:
            return 1
        print(f"issue ledgers OK: {', '.join(sorted(outputs))} current")
        return 0

    for name, payload in outputs.items():
        # write_bytes: text-mode writes would translate "\n" to os.linesep and
        # self-invalidate the --check comparison on CRLF platforms.
        (DASHBOARD_DATA / name).write_bytes(payload)
        print(f"wrote dashboard/public/data/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
