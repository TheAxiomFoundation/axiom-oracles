#!/usr/bin/env python3
"""Write the UK-CTR entitledto calculator-oracle report on demand.

Reads the recorded entitledto fixtures and the committed PolicyEngine-UK
reference values and writes the combined report (default: gitignored ``reports/``
scratch dir). While fixtures are ``pending_capture`` the report grades nothing;
re-run it after capturing fixtures to grade entitledto against PolicyEngine and
the statutory hand-check. The builder is fail-closed — an inconsistent
fixture/reference set raises rather than emitting a defaulted award.

    python scripts/run_uk_ctr_entitledto_report.py
    python scripts/run_uk_ctr_entitledto_report.py --output /tmp/uk-ctr.json
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

DEFAULT_OUTPUT = REPO_ROOT / "reports" / "axiom-uk-council-tax-reduction-entitledto.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = build_uk_ctr_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    cap = report["capture"]
    print(
        f"Wrote {args.output.name}: {cap['captured']} captured, {cap['pending']} "
        f"pending, {cap['invalid']} invalid, {cap['graded']} graded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
