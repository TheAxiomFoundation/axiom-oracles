"""Shared explicit runtime arguments for standalone RuleSpec generators."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.bridges.rulespec_paths import (  # noqa: E402
    require_axiom_binary,
    require_rulespec_checkout,
)


def parse_canonical_runtime_args(
    argv: list[str] | None,
    *,
    country: str,
) -> tuple[Path, Path]:
    """Parse and validate one exact RuleSpec checkout and engine binary."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rulespec-root",
        type=Path,
        required=True,
        help=f"Exact canonical rulespec-{country} checkout.",
    )
    parser.add_argument(
        "--axiom-binary",
        type=Path,
        required=True,
        help="Exact executable axiom-rules-engine file.",
    )
    args = parser.parse_args(argv)
    try:
        rulespec_root = require_rulespec_checkout(args.rulespec_root, country=country)
        axiom_binary = require_axiom_binary(args.axiom_binary)
    except ValueError as exc:
        parser.error(str(exc))
    return rulespec_root, axiom_binary
