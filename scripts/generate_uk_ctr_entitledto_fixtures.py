#!/usr/bin/env python3
"""Generate the entitledto UK-CTR recorded-fixture stubs from the suite.

Each fixture's ``inputs`` block is exactly ``EntitledToInputMapper.map_case`` of
the matching suite case, so the manual-entry record a human captures against can
never drift from the case definition (``test_entitledto_fixtures.py`` pins this
both ways). The stubs ship as ``pending_capture`` — inputs filled, ``outputs:
null`` — because entitledto's legal notices bar automated collection; a human
fills ``outputs`` per ``CAPTURE-PROTOCOL.md``.

    python scripts/generate_uk_ctr_entitledto_fixtures.py           # write
    python scripts/generate_uk_ctr_entitledto_fixtures.py --check   # CI drift gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.entitledto import (  # noqa: E402
    CAPTURE_STATUS_PENDING,
    EntitledToInputMapper,
)
from axiom_oracles.adapters.entitledto.recorded import DEFAULT_FIXTURES_DIR  # noqa: E402
from axiom_oracles.core.case import Case  # noqa: E402
from axiom_oracles.suites.uk_ctr import uk_ctr_cases  # noqa: E402

_PENDING_NOTE = (
    "Pending manual capture. entitledto's legal notices prohibit systematic or "
    "automated data collection, so a human must run this case once on the public "
    "calculator and record the outputs per CAPTURE-PROTOCOL.md. Do not invent or "
    "estimate values: an uncaptured fixture stays pending."
)


def build_fixture(case: Case, mapper: EntitledToInputMapper | None = None) -> dict:
    """The recorded-fixture stub for one suite case (pending capture)."""
    mapper = mapper or EntitledToInputMapper()
    meta = case.metadata
    return {
        "case_id": str(case.case_id),
        "oracle": "entitledto",
        "provenance": {
            "capture_status": CAPTURE_STATUS_PENDING,
            "calculator": "entitledto",
            "calculator_url": mapper.calculator_url,
            "scheme_year": meta.get("scheme_year"),
            "council_name": meta.get("local_authority_name"),
            "council_gss_code": meta.get("local_authority_gss_code"),
            "council_tax_band": meta.get("council_tax_band"),
            "ctr_scheme": meta.get("ctr_scheme"),
            "capture_date": None,
            "captured_by": None,
            "calculator_version": None,
            "notes": _PENDING_NOTE,
        },
        "inputs": mapper.map_case(case),
        # Filled on capture, e.g.
        #   {"council_tax_reduction": {"annual_gbp": 1181.0, "weekly_gbp": 22.71},
        #    "universal_credit": {"annual_gbp": ..., "monthly_gbp": ...},
        #    "housing_benefit": {"annual_gbp": ...}, "pension_credit": {"annual_gbp": ...}}
        "outputs": None,
    }


def _render(fixture: dict) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed fixtures differ from a fresh generation.",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help="Where the fixtures live (defaults to the packaged directory).",
    )
    args = parser.parse_args()
    fixtures_dir: Path = args.fixtures_dir
    mapper = EntitledToInputMapper()

    drift: list[str] = []
    for case in uk_ctr_cases():
        rendered = _render(build_fixture(case, mapper))
        path = fixtures_dir / f"{case.case_id}.json"
        if args.check:
            if not path.exists():
                drift.append(f"missing {path.name}")
            elif path.read_text() != rendered:
                drift.append(f"stale {path.name}")
        else:
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered)

    if args.check and drift:
        sys.stderr.write(
            "entitledto UK-CTR fixtures out of date; run "
            "scripts/generate_uk_ctr_entitledto_fixtures.py\n  "
            + "\n  ".join(drift)
            + "\n"
        )
        return 1
    if not args.check:
        print(f"Wrote {len(uk_ctr_cases())} fixtures to {fixtures_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
