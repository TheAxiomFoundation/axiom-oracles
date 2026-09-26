#!/usr/bin/env python3
"""Compute and stamp a suite's disposition bindings from its FULL report.

Hardened dispositions bind every classification to the evidence it was made
against (see ``axiom_oracles/comparison/dispositions.py``):

* ``selector_binding`` — for ``case_selector`` / ``signatures`` / ``match``
  entries, the selected population's row count plus either a per-row digest
  over identity and exact values (``rows_sha256``; the default) or, for
  ``signatures`` entries, the ``(signature, multiplicity)`` population
  digest (``signature_population_sha256``). An entry that already carries
  a binding keeps its form.
* ``pinned`` — for single-row ``case_id`` entries, the row's exact ``left``
  and ``right`` values.
* ``oracle_binding`` — for TAXSIM lanes (or with ``--oracle-binding``), the
  TAXSIM identity the report records, read per interface contract C1:
  ``taxsim_binary_sha256`` (the binaries that ran on the entry's rows —
  per-row digests when every selected row records one, else the report's
  whole recorded set), else ``policyengine_taxsim``, else
  ``identity_unrecorded: true``. ``--legacy-policyengine-taxsim VERSION``
  adds an explicitly supplied legacy package version (this helper cannot
  verify which version an unrecorded historical run used); the binding then
  also matches a report that records exactly that version and no binary
  digests, and still expires on any report that records binaries.

The merge re-derives all three on every application, so a TAXSIM re-pin, a
moved value, or a grown/shrunk population expires the entry instead of
letting it ride. Run this only after re-verifying the classifications
against the refreshed report, in the same commit as that report.

The report is the suite's committed FULL report: ``--report PATH``, else
the dashboard copy when it stores every mismatch row, else the file its
``summary.dispositioned.source_report`` pointer names. A pointer's path and
SHA256 must verify before its source can supply binding evidence. Selection uses the
merge's own selector (:func:`select_rows`); in a TAXSIM lane a row claimed
by two entries aborts (classification conservation). Entries that select no
row are reported and left untouched.

Edits are textual — each managed block is replaced or inserted after the
entry's ``expires_on_source_change`` line — so hand formatting and comments
elsewhere in the file survive. ``--check`` writes nothing and exits 1 when
any stamped binding differs from what the report yields.

Usage:
    uv run scripts/bind_dispositions.py <suite> [--report PATH] [--check]
        [--oracle-binding] [--legacy-policyengine-taxsim VERSION]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    row_binary_sha256,
    report_is_taxsim_lane,
    report_oracle_identity,
    select_rows,
    selection_binding,
    suite_context,
)
from scripts.apply_dispositions import _resolve_source_pointer  # noqa: E402

DISPOSITIONS_DIR = REPO_ROOT / "dispositions"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
MANAGED_KEYS = ("pinned", "selector_binding", "oracle_binding")
_MULTI_ROW_SELECTORS = ("case_selector", "signatures", "match")


def _is_full(report: dict) -> bool:
    summary = report.get("summary") or {}
    return len(report.get("mismatches") or []) == summary.get("mismatch_count")


def resolve_full_report(suite: str, explicit: Path | None) -> tuple[Path, dict]:
    """The suite's committed FULL report (see module docstring)."""

    if explicit is not None:
        path = explicit if explicit.is_absolute() else REPO_ROOT / explicit
        report = json.loads(path.read_text())
        if report.get("suite") != suite:
            raise SystemExit(f"{path} is not a {suite} report")
        if not _is_full(report):
            raise SystemExit(
                f"{path} is not FULL (stored mismatch rows != mismatch_count)"
            )
        return path, report
    candidates: list[tuple[Path, dict]] = []
    for path in sorted(DASHBOARD_DATA_DIR.glob("*.json")):
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict) or report.get("suite") != suite:
            continue
        if _is_full(report):
            candidates.append((path, report))
            continue
        block = (report.get("summary") or {}).get("dispositioned") or {}
        pointer = block.get("source_report") if isinstance(block, dict) else None
        if pointer is not None:
            problems: list[str] = []
            source = _resolve_source_pointer(
                path.relative_to(REPO_ROOT),
                suite,
                pointer,
                problems,
                repo_root=REPO_ROOT,
            )
            if source is None:
                raise SystemExit("\n".join(problems))
            candidates.append(source)
    if len(candidates) != 1:
        found = ", ".join(str(path.relative_to(REPO_ROOT)) for path, _ in candidates)
        raise SystemExit(
            f"need exactly one FULL {suite} report to bind against; found "
            f"{len(candidates)} ({found or 'none'}). Pass --report PATH."
        )
    return candidates[0]


def computed_bindings(
    entries: list[dict],
    report: dict,
    *,
    lane: bool,
    oracle_binding: bool,
    legacy_version: str | None,
) -> tuple[dict[str, dict], list[str]]:
    """``{entry_id: {managed_key: value}}`` plus notes for skipped entries."""

    rows = list(report.get("mismatches") or [])
    # Bind the selector's current rows even when old pins have expired.
    # Keeping the pins here would hide precisely the drift --check must catch.
    selectors = [{key: value for key, value in entry.items() if key != "pinned"}
                 for entry in entries]
    _, selected, _, conflicts = select_rows(selectors, rows, conservation=lane)
    if conflicts:
        details = "; ".join(
            f"{row.get('case_id')}/{row.get('concept')} -> {claimants}"
            for row, claimants in conflicts[:10]
        )
        raise SystemExit(
            f"classification conservation failure: {len(conflicts)} rows are "
            f"claimed by more than one entry ({details})"
        )
    identity = report_oracle_identity(report)
    if identity["malformed"]:
        raise SystemExit("the report's recorded TAXSIM identity is malformed")
    bindings: dict[str, dict] = {}
    notes: list[str] = []
    for entry in entries:
        entry_id = str(entry.get("id"))
        entry_rows = selected[entry_id]
        if not entry_rows:
            notes.append(f"{entry_id}: selects no row in the report; left untouched")
            continue
        values: dict = {}
        if any(entry.get(key) is not None for key in _MULTI_ROW_SELECTORS):
            existing = entry.get("selector_binding")
            signature_form = (
                "signature_population_sha256" in existing
                if isinstance(existing, dict)
                else entry.get("signatures") is not None
            )
            values["selector_binding"] = selection_binding(
                entry_rows, signature=signature_form
            )
        elif entry.get("case_id") is not None:
            if len(entry_rows) != 1:
                raise SystemExit(
                    f"{entry_id}: case_id must select exactly one row; "
                    f"selected {len(entry_rows)}"
                )
            (row,) = entry_rows
            pinned = {"left": row.get("left"), "right": row.get("right")}
            previous = entry.get("pinned")
            previous = previous if isinstance(previous, dict) else {}
            if "difference" in previous:
                pinned["difference"] = row.get("difference")
            values["pinned"] = pinned
        if oracle_binding:
            values["oracle_binding"] = _oracle_binding(
                identity, entry_rows, legacy_version
            )
        bindings[entry_id] = values
    return bindings, notes


def _oracle_binding(
    identity: dict, rows: list[dict], legacy_version: str | None
) -> dict:
    shas = identity["taxsim_binary_sha256"]
    if shas is not None:
        per_row = [row_binary_sha256(row) for row in rows]
        relevant = set(per_row) if per_row and all(per_row) else set(shas)
        if not relevant <= set(shas):
            raise SystemExit("per-row TAXSIM binaries are absent from report identity")
        return {"taxsim_binary_sha256": sorted(relevant)}
    if identity["policyengine_taxsim"] is not None:
        return {"policyengine_taxsim": identity["policyengine_taxsim"]}
    binding: dict = {}
    if legacy_version:
        binding["policyengine_taxsim"] = legacy_version
    binding["identity_unrecorded"] = True
    return binding


def _render_block(key: str, value: object) -> str:
    text = yaml.safe_dump(
        {key: value}, sort_keys=False, default_flow_style=False, width=10**6
    )
    return "".join(f"  {line}\n" for line in text.splitlines())


def stamp(text: str, entry_id: str, updates: dict[str, object]) -> str:
    """Replace or insert managed blocks in one entry's YAML text."""

    entry_pattern = re.compile(
        rf"^- id: [\"']?{re.escape(entry_id)}[\"']?\n(?:.*\n)*?(?=^- id: |\Z)",
        re.M,
    )
    found = entry_pattern.search(text)
    if not found:
        raise SystemExit(f"could not locate the entry block for {entry_id}")
    block = found.group(0)
    for key in updates:
        block = re.sub(
            rf"^  {re.escape(key)}:[^\n]*\n(?:    [^\n]*\n)*", "", block, flags=re.M
        )
    expires = re.search(r"^  expires_on_source_change: .*\n", block, re.M)
    if not expires:
        raise SystemExit(f"{entry_id} lacks an expires_on_source_change line")
    insert = "".join(
        _render_block(key, updates[key]) for key in MANAGED_KEYS if key in updates
    )
    block = block[: expires.end()] + insert + block[expires.end():]
    return text[: found.start()] + block + text[found.end():]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--oracle-binding",
        action="store_true",
        help="Stamp oracle_binding even outside a TAXSIM lane.",
    )
    parser.add_argument("--legacy-policyengine-taxsim", default=None)
    args = parser.parse_args(argv)

    path = DISPOSITIONS_DIR / f"{args.suite}.yaml"
    if not path.exists():
        raise SystemExit(f"{path} does not exist")
    text = path.read_text()
    document = yaml.safe_load(text)
    entries = list(document.get("entries") or [])
    report_path, report = resolve_full_report(args.suite, args.report)
    lane = (
        suite_context(args.suite, REPO_ROOT).taxsim_lane
        or report_is_taxsim_lane(report)
    )
    bindings, notes = computed_bindings(
        entries,
        report,
        lane=lane,
        oracle_binding=lane or args.oracle_binding,
        legacy_version=args.legacy_policyengine_taxsim,
    )
    for note in notes:
        print(f"note: {note}")

    drift: list[str] = []
    entries_by_id = {str(entry.get("id")): entry for entry in entries}
    for entry_id, values in bindings.items():
        updates = {
            key: value
            for key, value in values.items()
            if entries_by_id[entry_id].get(key) != value
        }
        if not updates:
            continue
        drift.append(f"{entry_id}: {', '.join(sorted(updates))}")
        if not args.check:
            text = stamp(text, entry_id, updates)

    try:
        rel_report = report_path.relative_to(REPO_ROOT)
    except ValueError:
        rel_report = report_path
    if args.check:
        if drift or notes:
            for line in drift:
                print(f"drift: {line}", file=sys.stderr)
            print(
                f"{len(drift)} entr{'y' if len(drift) == 1 else 'ies'} of "
                f"{path.name} are not bound to {rel_report}",
                file=sys.stderr,
            )
            return 1
        print(f"{path.name}: every binding matches {rel_report}")
        return 0
    if drift:
        path.write_text(text)
        if yaml.safe_load(path.read_text()) is None:  # pragma: no cover - defensive
            raise SystemExit(f"{path} no longer parses after stamping")
    print(
        f"stamped {len(drift)} entr{'y' if len(drift) == 1 else 'ies'} of "
        f"{path.name} against {rel_report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
