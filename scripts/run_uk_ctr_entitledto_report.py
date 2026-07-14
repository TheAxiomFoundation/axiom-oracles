#!/usr/bin/env python3
"""Write the UK-CTR entitledto calculator-oracle report to reports/.

Reads the recorded entitledto fixtures and the committed PolicyEngine-UK
reference values, and writes the combined report. While fixtures are
``pending_capture`` the report grades nothing; re-run it after capturing
fixtures to grade entitledto against PolicyEngine and the statutory hand-check.

    python scripts/run_uk_ctr_entitledto_report.py            # write report
    python scripts/run_uk_ctr_entitledto_report.py --check    # CI drift gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.entitledto.report import build_uk_ctr_report  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "reports" / "axiom-entitledto-uk-council-tax-reduction.json"


def render(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed report differs from a fresh build.",
    )
    args = parser.parse_args()

    rendered = render(build_uk_ctr_report())
    if args.check:
        if not args.output.exists() or args.output.read_text() != rendered:
            sys.stderr.write(
                "UK-CTR entitledto report out of date; run "
                "scripts/run_uk_ctr_entitledto_report.py\n"
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    report = json.loads(rendered)
    print(
        f"Wrote {args.output.name}: {report['capture']['captured']} captured, "
        f"{report['capture']['pending']} pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
