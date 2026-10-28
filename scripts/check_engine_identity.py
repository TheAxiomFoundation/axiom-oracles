#!/usr/bin/env python3
"""Reject published Axiom reports without an exact engine commit and binary hash.

Only byte-identical historical entries in conformance/legacy-engine-identity.json
are exempt. --strict reports the historical debt without these exemptions.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.engine_publication import check_publications  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check publications (the default).")
    parser.add_argument("--strict", action="store_true", help="Ignore historical exceptions.")
    args = parser.parse_args(argv)
    try:
        result = check_publications(REPO_ROOT, allow_legacy=not args.strict)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"FAILED: engine publication validation: {exc}", file=sys.stderr)
        return 1
    for error in result["errors"]:
        print(f"FAILED: {error}", file=sys.stderr)
    print(
        f"engine identity: {result['axiom_reports']} Axiom reports; "
        f"{result['unresolved_reports']} unresolved; "
        f"{result['legacy_reports']} byte-identical legacy reports"
    )
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
