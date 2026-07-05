#!/usr/bin/env python3
"""Conformance ratchet gate — the monotonic invariants may not regress.

``conformance/ratchet.yaml`` pins the best conformance numbers so far. This
script has three modes:

* default (write): re-pin every jurisdiction's ratchet to the CURRENT scoreboard,
  but only where that is an improvement (covered up, unexplained/axiom down). It
  never loosens a floor — a ratchet only ever tightens toward conformance.
* ``--check``: recompute the live scoreboard and fail if any invariant regressed,
  naming the exact invariant and jurisdiction. This is the CI gate.
* ``--init``: create the ratchet file from the current scoreboard for the first
  time (or add rows for new jurisdictions), without tightening existing rows.

The ratchet reads the SAME scoreboard the dashboard shows, computed fresh here,
so it can never lag a stale committed copy (the scoreboard-freshness gate keeps
the committed scoreboard honest separately).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.conformance.ratchet import (  # noqa: E402
    RATCHET_SCHEMA,
    RatchetInvariant,
    check_regressions,
)

# Import the scoreboard builder so the ratchet always scores the live universe +
# reports rather than trusting a possibly-stale committed scoreboard.json.
import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "_conformance_scoreboard", REPO_ROOT / "scripts" / "conformance_scoreboard.py"
)
_scoreboard_mod = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_scoreboard_mod)

RATCHET_PATH = REPO_ROOT / "conformance" / "ratchet.yaml"


def _live_summaries() -> dict[str, dict]:
    document, _details = _scoreboard_mod.build_scoreboard()
    return {j["jurisdiction"]: j for j in document["jurisdictions"]}


def _load_ratchets() -> dict[str, RatchetInvariant]:
    if not RATCHET_PATH.exists():
        return {}
    doc = yaml.safe_load(RATCHET_PATH.read_text()) or {}
    return {
        row["jurisdiction"]: RatchetInvariant.from_row(row)
        for row in doc.get("ratchets", [])
    }


def _serialize(ratchets: dict[str, RatchetInvariant]) -> str:
    rows = [ratchets[k].to_row() for k in sorted(ratchets)]
    document = {
        "schema": RATCHET_SCHEMA,
        "_comment": (
            "Conformance ratchets — monotonic floors/ceilings enforced by "
            "scripts/conformance_ratchet.py --check. covered_min may only rise; "
            "unexplained_max and axiom_attributed_open_max may only fall. "
            "Re-pin with `uv run scripts/conformance_ratchet.py` after a genuine "
            "improvement; the gate refuses regressions."
        ),
        "ratchets": rows,
    }
    header = f"# {RATCHET_SCHEMA} — GENERATED; advance only via the ratchet script.\n"
    body = yaml.dump(
        document,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return header + body


def _tighten(existing: RatchetInvariant, summary: dict) -> RatchetInvariant:
    """Return a ratchet tightened toward the current scoreboard (never loosened)."""
    candidate = RatchetInvariant.from_summary(summary)
    return RatchetInvariant(
        jurisdiction=existing.jurisdiction,
        covered_min=max(existing.covered_min, candidate.covered_min),
        unexplained_max=min(existing.unexplained_max, candidate.unexplained_max),
        axiom_attributed_open_max=min(
            existing.axiom_attributed_open_max,
            candidate.axiom_attributed_open_max,
        ),
        # Track the live denominator so covered is read against the right base.
        policies_in_scope=candidate.policies_in_scope,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI: fail if any jurisdiction regressed a conformance invariant.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Seed the ratchet file from the current scoreboard (no tightening).",
    )
    args = parser.parse_args()

    summaries = _live_summaries()
    ratchets = _load_ratchets()

    if args.check:
        if not ratchets:
            sys.stderr.write(
                "conformance/ratchet.yaml missing or empty; seed it with "
                "`uv run scripts/conformance_ratchet.py --init`.\n"
            )
            return 1
        violations: list[str] = []
        for jurisdiction, summary in summaries.items():
            ratchet = ratchets.get(jurisdiction)
            if ratchet is None:
                sys.stderr.write(
                    f"conformance ratchet MISSING for {jurisdiction!r}; a new "
                    "jurisdiction must be pinned with "
                    "`uv run scripts/conformance_ratchet.py --init`.\n"
                )
                return 1
            violations.extend(check_regressions(ratchet, summary))
        if violations:
            for violation in violations:
                sys.stderr.write(violation + "\n")
            return 1
        print(
            f"conformance ratchet OK: {len(summaries)} jurisdiction(s), no "
            "invariant regressed"
        )
        return 0

    # Write modes.
    if args.init:
        for jurisdiction, summary in summaries.items():
            ratchets.setdefault(
                jurisdiction, RatchetInvariant.from_summary(summary)
            )
        RATCHET_PATH.write_text(_serialize(ratchets))
        print(f"Seeded conformance/ratchet.yaml with {len(ratchets)} jurisdiction(s).")
        return 0

    # Default: tighten existing, add new.
    for jurisdiction, summary in summaries.items():
        if jurisdiction in ratchets:
            ratchets[jurisdiction] = _tighten(ratchets[jurisdiction], summary)
        else:
            ratchets[jurisdiction] = RatchetInvariant.from_summary(summary)
    RATCHET_PATH.write_text(_serialize(ratchets))
    print(
        f"Re-pinned conformance/ratchet.yaml ({len(ratchets)} jurisdiction(s)) "
        "to the current scoreboard where it improved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
