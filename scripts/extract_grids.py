#!/usr/bin/env python
"""Extract canonical per-jurisdiction case grids from the live oracle suites.

Writes ``grids/<jurisdiction>.yaml`` from the case sets registered in
``axiom_oracles.suites`` (and, when importable, the in-flight UK worker
suites), grouping suites by the jurisdiction of their cases' locale. The
output is a *faithful, machine-checkable* projection of the suites — the
extraction-equivalence test reconstructs each suite from the emitted grid and
asserts equality, so a regenerated grid can never silently drift from the
suites and therefore can never shift a comparison report.

Usage::

    uv run python scripts/extract_grids.py            # write grids/*.yaml
    uv run python scripts/extract_grids.py --check     # fail if out of date
    uv run python scripts/extract_grids.py --jurisdiction be

Idempotent: re-running without suite changes reproduces byte-identical files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the repo root is importable when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from axiom_oracles.core.case import Case  # noqa: E402
from axiom_oracles.grids.extract import case_set_skeleton  # noqa: E402
from axiom_oracles.grids.model import GRID_SCHEMA_VERSION  # noqa: E402
from axiom_oracles.suites import available_suites, load_suite  # noqa: E402

GRID_ROOT = _REPO_ROOT / "grids"

# Map a country locale/scope to a grid jurisdiction filename. Locales are the
# ``case.locale`` values the suites emit (``BE``, ``UK``, ``US-NY-NYC``, ...).
_JURISDICTION_BY_COUNTRY = {"BE": "be", "GH": "gh", "UG": "ug", "UK": "uk", "US": "us"}


def _country_of(cases: list[Case]) -> str:
    scopes = {case.scope for case in cases if case.scope is not None}
    countries = set()
    for scope in scopes:
        if scope.type == "country":
            countries.add(scope.geoid)
        else:
            # Sub-country US scopes (NYC place, state) roll up to US.
            countries.add("US")
    if len(countries) != 1:
        raise SystemExit(
            f"Cannot assign a single jurisdiction to a mixed-country suite: {countries}"
        )
    return next(iter(countries))


def _collect_suites() -> list[tuple[str, list[Case]]]:
    """Every registered suite plus the in-flight UK worker suites if present."""
    suites: list[tuple[str, list[Case]]] = [
        (name, load_suite(name)) for name in available_suites()
    ]
    # The UK triangulation suites may not be on ``main`` yet (they land with the
    # UKMOD PR). Extract them opportunistically so ``grids/uk.yaml`` ships whole
    # once they exist, without hard-coupling this script to their presence.
    try:
        from axiom_oracles.suites import uk_worker  # type: ignore
    except Exception:  # pragma: no cover - exercised only pre-UKMOD-merge
        uk_worker = None
    if uk_worker is not None:
        for fn_name in ("uk_worker_pit_cases", "uk_worker_nic_cases"):
            fn = getattr(uk_worker, fn_name, None)
            if fn is None:
                continue
            suite_name = fn_name.replace("_cases", "").replace("_", "-")
            suites.append((suite_name, fn()))
    return suites


def build_grids() -> dict[str, dict]:
    """Build the in-memory grid payloads keyed by jurisdiction."""
    by_jurisdiction: dict[str, dict[str, dict]] = {}
    for suite_name, cases in _collect_suites():
        if not cases:
            continue
        country = _country_of(cases)
        jurisdiction = _JURISDICTION_BY_COUNTRY[country]
        body = case_set_skeleton(suite_name, cases)
        by_jurisdiction.setdefault(jurisdiction, {})[suite_name] = body

    payloads: dict[str, dict] = {}
    for jurisdiction, case_sets in by_jurisdiction.items():
        ordered = {name: case_sets[name] for name in sorted(case_sets)}
        payloads[jurisdiction] = {
            "schema_version": GRID_SCHEMA_VERSION,
            "jurisdiction": jurisdiction,
            "generated_from": {
                "suites_module": "axiom_oracles.suites",
                "extractor": "scripts/extract_grids.py",
            },
            "case_sets": ordered,
        }
    return payloads


class _GridDumper(yaml.SafeDumper):
    """Block-style YAML with stable key order and no aliases."""


def _represent_str(dumper: yaml.Dumper, data: str):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_GridDumper.add_representer(str, _represent_str)
_GridDumper.ignore_aliases = lambda self, data: True  # type: ignore[assignment]

_HEADER = (
    "# Canonical case grid — GENERATED from axiom_oracles.suites; do not edit "
    "by hand.\n"
    "# Regenerate with: uv run python scripts/extract_grids.py\n"
    "# Byte-preserving extraction of the live suites; the extraction-equivalence\n"
    "# test proves this grid and the suites describe the identical case list.\n"
    "# See grids/README.md.\n"
)


def _dump(payload: dict) -> str:
    return _HEADER + yaml.dump(
        payload,
        Dumper=_GridDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jurisdiction",
        help="Only write/check this jurisdiction (us, be, uk).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if any grid file is out of date.",
    )
    args = parser.parse_args()

    GRID_ROOT.mkdir(parents=True, exist_ok=True)
    payloads = build_grids()
    if args.jurisdiction:
        payloads = {
            j: p for j, p in payloads.items() if j == args.jurisdiction
        }
        if not payloads:
            print(f"No suites found for jurisdiction {args.jurisdiction!r}.")
            return 1

    stale: list[str] = []
    for jurisdiction, payload in sorted(payloads.items()):
        path = GRID_ROOT / f"{jurisdiction}.yaml"
        rendered = _dump(payload)
        if args.check:
            existing = path.read_text() if path.exists() else ""
            if existing != rendered:
                stale.append(jurisdiction)
            continue
        path.write_text(rendered)
        case_count = sum(len(cs["cases"]) for cs in payload["case_sets"].values())
        print(
            f"wrote {path.relative_to(_REPO_ROOT)} "
            f"({len(payload['case_sets'])} case sets, {case_count} cases)"
        )

    if args.check and stale:
        print(
            "Grid files are out of date for: "
            + ", ".join(stale)
            + "\nRun: uv run python scripts/extract_grids.py"
        )
        return 1
    if args.check:
        print("Grids up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
