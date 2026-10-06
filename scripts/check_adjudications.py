#!/usr/bin/env python3
"""Re-verify every adjudication proof atom against its pinned source bytes."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from axiom_oracles.comparison.adjudications import (  # noqa: E402
    AdjudicationError,
    load_adjudications,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing (always true).")
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--maintainers", type=Path)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or sorted(
        path for path in (args.repo_root / "adjudications").glob("*.yaml")
        if path.name != "maintainers.yaml"
    )
    if not paths:
        print("No adjudication registries found", file=sys.stderr)
        return 1
    failed = False
    for path in paths:
        try:
            document = load_adjudications(
                path, repo_root=args.repo_root, corpus_root=args.corpus_root,
                maintainers_path=args.maintainers,
            )
            counts = Counter(record["status"] for record in document["adjudications"])
            print(f"OK {path.name}: {len(document['adjudications'])} records; " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        except AdjudicationError as exc:
            print(str(exc), file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
