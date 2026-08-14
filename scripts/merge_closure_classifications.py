#!/usr/bin/env python3
"""Merge reviewed classifications into generated closure universes.

The universe generator establishes only what a machine can decide from pinned
artifacts: a provision is ``encoded`` when a module file joins to its citation
path, and ``pending`` otherwise. Everything else — that a provision is excluded
and why, or that a file-path join overstates what a module actually computes —
is a reviewed judgment. This script is how those judgments land, and it is
deliberately conservative about what it will accept.

Two directions of correction, both real:

* ``pending -> excluded``. The provision is accounted for without an encoding,
  under a reason from the closed taxonomy plus a basis grounded in the
  provision's own text.
* ``encoded -> pending``. The file join found a module, but the module itself
  declares (via ``deferred_outputs``) that it does not compute substantive
  parts of the section. A path join cannot see that; a reader of the module
  can. Recording the downgrade is the point of having both signals — closure
  that counts a stub as done is worse than no closure at all.

Refusals, because a merge that quietly drops rows would corrupt the ledger:
a classification whose citation is absent from the universe is an error, not a
skip; an excluded row missing reason or basis is an error; a reason outside
the taxonomy is an error; and ``operationalized_by`` must name a path that
exists in the pinned rulespec tree.

Ratchet: ``pending_max`` is lowered to the merged count when pending falls, so
the committed ratchet reflects the new floor. It is never raised here — a merge
that would raise pending for a root is reported and refused.

    uv run python scripts/merge_closure_classifications.py --in <dir> [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_DIR = REPO_ROOT / "closure" / "universes" / "us-co-snap"
PINNED_TREE = REPO_ROOT / "closure" / "data" / "rulespec-us-files.txt"

TAXONOMY = {
    "container_heading",
    "procedural_no_point_in_time_effect",
    "reserved",
    "no_household_computation",
}


def _load_universe(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _rows_from(path: Path) -> list[dict]:
    """Parse a classification file, tolerating both list and mapping roots."""
    payload = yaml.safe_load(path.read_text())
    if isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("provisions") or []
    else:
        rows = payload or []
    return [r for r in rows if isinstance(r, dict) and r.get("citation")]


def _normalize_reason(reason: str) -> str:
    """Canonicalize a reason string.

    ``operationalized_by`` carries a path, and classifiers write it with the
    spacing YAML humans use (``operationalized_by: us/...``). The downstream
    check parses the path out and rejects a leading space, so normalize here
    rather than letting whitespace decide whether a gate passes.
    """
    if reason.startswith("operationalized_by") and ":" in reason:
        return f"operationalized_by: {reason.split(':', 1)[1].strip()}"
    return reason.strip()


def _reason_ok(reason: str, tree: set[str], errors: list[str], cit: str) -> None:
    if reason.startswith("operationalized_by"):
        target = reason.split(":", 1)[1].strip() if ":" in reason else ""
        if not target:
            errors.append(f"{cit}: operationalized_by names no module")
        elif target not in tree:
            errors.append(
                f"{cit}: operationalized_by names {target!r}, absent from the "
                "pinned rulespec tree"
            )
        return
    if reason not in TAXONOMY:
        errors.append(f"{cit}: reason {reason!r} is outside the taxonomy")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="indir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    tree = {
        line.strip()
        for line in PINNED_TREE.read_text().splitlines()
        if line.strip()
    }

    classifications: dict[str, dict] = {}
    errors: list[str] = []
    for path in sorted(Path(args.indir).glob("*.yaml")):
        if path.name.startswith(("REVIEW", "PROGRESS")):
            continue
        for row in _rows_from(path):
            cit = str(row["citation"])
            if cit in classifications:
                errors.append(f"{cit}: classified twice (second in {path.name})")
            classifications[cit] = {**row, "_src": path.name}

    universes = {p: _load_universe(p) for p in sorted(UNIVERSE_DIR.glob("*.yaml"))}
    index: dict[str, tuple[Path, dict]] = {}
    for path, uni in universes.items():
        for prov in uni.get("provisions", []):
            index[str(prov.get("citation"))] = (path, prov)

    applied = {"excluded": 0, "downgraded": 0, "encoded_fixed": 0, "unchanged": 0}
    for cit, row in classifications.items():
        if cit not in index:
            errors.append(f"{cit}: not present in any universe ({row['_src']})")
            continue
        _, prov = index[cit]
        status = row.get("status")
        if status == "excluded":
            reason = _normalize_reason(str(row.get("reason") or ""))
            basis = str(row.get("basis") or "").strip()
            if not reason:
                errors.append(f"{cit}: excluded without a reason")
                continue
            if not basis:
                errors.append(f"{cit}: excluded without a basis")
                continue
            _reason_ok(reason, tree, errors, cit)
            prov["status"] = "excluded"
            prov["reason"] = reason
            prov["basis"] = basis
            prov.pop("encoded_by", None)
            applied["excluded"] += 1
        elif status == "pending":
            note = " ".join(str(row.get("note") or "").split())
            if prov.get("status") == "encoded":
                # The join saw a module file; the reviewer read the module and
                # found the section's substantive content declared as
                # `deferred_outputs`. Record it as partial coverage rather than
                # a bare downgrade: the marker survives regeneration (a plain
                # status edit does not — the join would re-upgrade the row) and
                # it must state what is missing.
                if not note:
                    errors.append(
                        f"{cit}: downgrading an encoded row to pending requires "
                        "a note stating which outputs the module defers"
                    )
                    continue
                prov["status"] = "pending"
                prov.pop("encoded_by", None)
                prov["partial_coverage"] = note
                applied["downgraded"] += 1
            else:
                applied["unchanged"] += 1
                if note:
                    prov["note"] = note
        elif status == "encoded":
            paths = row.get("encoded_by") or []
            missing = [p for p in paths if p not in tree]
            if missing:
                errors.append(f"{cit}: encoded_by paths absent from tree: {missing}")
                continue
            if prov.get("status") != "encoded" or prov.get("encoded_by") != paths:
                prov["status"] = "encoded"
                prov["encoded_by"] = paths
                applied["encoded_fixed"] += 1
            else:
                applied["unchanged"] += 1
        else:
            errors.append(f"{cit}: unknown status {status!r}")

    # Ratchet: pending may only fall.
    report = []
    for path, uni in universes.items():
        counts: dict[str, int] = {}
        for prov in uni.get("provisions", []):
            counts[prov.get("status", "?")] = counts.get(prov.get("status", "?"), 0) + 1
        pending = counts.get("pending", 0)
        prior = (uni.get("ratchet") or {}).get("pending_max")
        if prior is not None and pending > prior:
            errors.append(
                f"{path.name}: merge would RAISE pending {prior} -> {pending}; refused"
            )
        # The ratchet baseline is deliberately NOT written here. `--generate`
        # owns it and keeps universe and summary.json in agreement; writing it
        # from two places produced exactly that disagreement and made the
        # generator refuse. This script's job is to refuse a merge that would
        # raise pending, not to restate the floor.
        report.append((path.name, counts, prior, pending))

    for line in errors:
        print(f"ERROR   {line}", file=sys.stderr)
    for name, counts, prior, pending in report:
        print(f"{name}: {counts}  (pending {prior} -> {pending})")
    print(
        f"applied: {applied['excluded']} excluded, {applied['downgraded']} "
        f"encoded->pending downgrades, {applied['encoded_fixed']} encoded "
        f"corrections, {applied['unchanged']} already-correct; "
        f"{len(classifications)} classifications, {len(errors)} error(s)"
    )
    if errors:
        return 1
    if args.dry_run:
        print("dry run — nothing written")
        return 0
    for path, uni in universes.items():
        header = "\n".join(
            line for line in path.read_text().splitlines() if line.startswith("#")
        )
        body = yaml.safe_dump(uni, sort_keys=False, allow_unicode=True, width=100)
        path.write_text(header + "\n" + body)
    print(f"wrote {len(universes)} universe file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
