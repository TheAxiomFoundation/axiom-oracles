#!/usr/bin/env python3
"""Generate the entitledto UK-CTR recorded-fixture stubs from the suite.

Each fixture's ``inputs`` block is exactly ``EntitledToInputMapper.map_case`` of
the matching suite case, plus the immutable base provenance (calculator, URL,
scheme year, council, band, scheme). ``test_entitledto_fixtures.py`` pins that
*immutable skeleton* both ways, so the manual-entry record can never drift from
the case definition — while still letting a fixture legitimately transition to
``captured`` (which adds mutable capture fields and outputs) without failing the
drift gate or being clobbered.

The stubs ship as ``pending_capture`` — inputs filled, ``outputs: null`` —
because capturing them requires entitledto's express written consent
(``CAPTURE-PROTOCOL.md``); the writer never overwrites a captured fixture.

    python scripts/generate_uk_ctr_entitledto_fixtures.py           # write missing stubs
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
    CAPTURE_STATUS_CAPTURED,
    CAPTURE_STATUS_PENDING,
    EntitledToInputMapper,
)
from axiom_oracles.adapters.entitledto.recorded import DEFAULT_FIXTURES_DIR  # noqa: E402
from axiom_oracles.core.case import Case  # noqa: E402
from axiom_oracles.suites.uk_ctr import uk_ctr_cases  # noqa: E402

# Provenance keys fixed at generation time (a capture must not change them).
IMMUTABLE_PROVENANCE = (
    "calculator",
    "calculator_url",
    "scheme_year",
    "council_name",
    "council_gss_code",
    "council_tax_band",
    "ctr_scheme",
)

_PENDING_NOTE = (
    "Pending capture. Capturing this research grid requires entitledto's express "
    "written consent (see CAPTURE-PROTOCOL.md); the free calculator's terms bar "
    "systematic collection. Do not invent or estimate values: an uncaptured "
    "fixture stays pending."
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
            "entitledto_council_tax_liability_gbp": None,
            "notes": _PENDING_NOTE,
        },
        "inputs": mapper.map_case(case),
        # Filled on capture, e.g.
        #   {"council_tax_reduction": {"annual_gbp": 1181.0, "weekly_gbp": 22.71},
        #    "universal_credit": {"annual_gbp": ...}, "housing_benefit": {"annual_gbp": ...},
        #    "pension_credit": {"annual_gbp": ...}}
        "outputs": None,
    }


def immutable_skeleton(fixture: dict) -> dict:
    """The parts of a fixture that must never drift from the suite/mapper.

    Excludes the mutable capture fields (status/date/by/version/liability/notes)
    and outputs, so a captured fixture with the same inputs and base provenance
    still matches a fresh generation.
    """
    provenance = fixture.get("provenance") or {}
    return {
        "case_id": fixture.get("case_id"),
        "oracle": fixture.get("oracle"),
        "inputs": fixture.get("inputs"),
        "base_provenance": {k: provenance.get(k) for k in IMMUTABLE_PROVENANCE},
    }


def _render(fixture: dict) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if a committed fixture's immutable skeleton differs from a fresh build.",
    )
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    args = parser.parse_args()
    fixtures_dir: Path = args.fixtures_dir
    mapper = EntitledToInputMapper()

    drift: list[str] = []
    written = 0
    for case in uk_ctr_cases():
        fresh = build_fixture(case, mapper)
        path = fixtures_dir / f"{case.case_id}.json"
        if args.check:
            if not path.exists():
                drift.append(f"missing {path.name}")
            elif immutable_skeleton(json.loads(path.read_text())) != immutable_skeleton(
                fresh
            ):
                drift.append(f"skeleton drift in {path.name}")
        elif not path.exists():
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(_render(fresh))
            written += 1
        else:
            # Never clobber a capture; only refresh a still-pending stub in place.
            existing = json.loads(path.read_text())
            status = (existing.get("provenance") or {}).get("capture_status")
            if status == CAPTURE_STATUS_CAPTURED:
                continue
            if _render(existing) != _render(fresh):
                path.write_text(_render(fresh))
                written += 1

    if args.check and drift:
        sys.stderr.write(
            "entitledto UK-CTR fixtures out of date; run "
            "scripts/generate_uk_ctr_entitledto_fixtures.py\n  " + "\n  ".join(drift) + "\n"
        )
        return 1
    if not args.check:
        print(f"Wrote/updated {written} pending fixtures in {fixtures_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
