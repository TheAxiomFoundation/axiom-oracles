#!/usr/bin/env python3
"""Exercise census: what did each comparison suite actually vary?

A suite's headline (cases x match rate) says nothing about the input surface it
exercised. A suite that pins every input but two and a suite that varies ninety
shelter values are indistinguishable on the scoreboard — which is how a
"100% parity" number can silently carry near-zero evidence about most of a
program, and how mis-readings of suite breadth go uncorrected in both
directions.

This script makes exercise a committed, checkable artifact. For every suite
with committed per-case evidence (inline ``cases`` or
``dashboard/public/data/cases/<suite>/chunk-*.json``), it counts distinct
values per evidence field and per verdict concept across all cases, and writes
``conformance/exercise-census.json``.

Reading a row, three states matter per field:

* **varied** — multiple distinct values across cases; the comparison carries
  evidence about this dimension.
* **constant** — one distinct value across every case. The census cannot say
  *why* (population zeros, harness pin, or a projection mode); it says loudly
  that no evidence about this dimension exists in the suite.
* **bridged-through** — the harness feeds one engine's computed value into the
  other's input (e.g. snap_populace feeds PolicyEngine's dependent-care
  deduction in as the expense with ``reimbursed = 0``), so downstream effect is
  tested but the receiving side's own derivation is satisfied by construction.
  This state is declared by the bridge manifest, not inferable from values:
  ``axiom_oracles/bridges/manifests/<suite>.yaml`` is the source, this script
  only reports it. A suite with no manifest is unaudited, never "nothing
  bridged".

v1 scope, stated plainly: most suites commit *stage evidence* (gross income,
net income, shelter deduction, ...), not raw input records, so this measures
variation in the evidence the suite chose to keep. A suite with no committed
per-case evidence appears with ``cases_scanned: 0`` — that absence is a
finding, not a skip.

Modes::

    uv run python scripts/exercise_census.py           # write the census
    uv run python scripts/exercise_census.py --check   # CI: fail on drift
    uv run python scripts/exercise_census.py --markdown # human summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
CASES_DIR = DATA_DIR / "cases"
OUTPUT_PATH = REPO_ROOT / "conformance" / "exercise-census.json"

SCHEMA = "axiom_oracles.exercise_census.v1"

MANIFEST_DIR = REPO_ROOT / "axiom_oracles" / "bridges" / "manifests"


def _bridged_through_by_suite() -> dict[str, dict[str, str]]:
    """Bridged-through dimensions come from the declared bridge manifests.

    The manifest is the experiment design; the census only reports it. A suite
    with no manifest is unaudited — never "nothing bridged". Historical suite
    aliases map to the same manifest so committed reports keep their names.
    """
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - environment guard
        sys.exit(
            "exercise_census needs PyYAML to read bridge manifests. Run under "
            "the project env (`uv run python scripts/exercise_census.py`) or "
            "install the package first — bridged-through state must come from "
            "the manifests, never be silently skipped."
        )

    by_suite: dict[str, dict[str, str]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        manifest = yaml.safe_load(path.read_text())
        if not isinstance(manifest, dict):
            continue
        bridged = {
            str(b.get("dimension") or (b.get("inputs") or ["?"])[0]): str(
                b.get("mechanism") or b.get("source") or ""
            )
            for b in manifest.get("bindings") or []
            if b.get("kind") == "bridged"
        }
        for name in [manifest.get("suite"), *(manifest.get("aliases") or [])]:
            if name:
                by_suite[str(name)] = bridged
    return by_suite


BRIDGED_THROUGH: dict[str, dict[str, str]] = _bridged_through_by_suite()


def _iter_suite_reports() -> list[tuple[str, dict]]:
    reports = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("suite"):
            reports.append((str(payload["suite"]), payload))
    return reports


def _canonical_value(raw) -> str:
    """Canonicalize an observed value for distinctness counting.

    JSON-string identity is wrong for numbers: 1 vs 1.0 and 0.0 vs -0.0 are
    the same observation, while large integers must not collapse through
    float parsing (2026-07-26 audit, finding 17). Decimal, normalized, with
    signed zero collapsed.
    """
    if isinstance(raw, bool) or raw is None:
        return json.dumps(raw)
    if isinstance(raw, (int, float)):
        raw = str(raw)
    if isinstance(raw, str):
        try:
            number = Decimal(raw)
        except InvalidOperation:
            return json.dumps(raw, sort_keys=True)
        if number == 0:
            return "0"
        return format(number.normalize(), "f")
    return json.dumps(raw, sort_keys=True, default=str)


def _chunk_cases(suite: str) -> tuple[list[dict], list[dict]]:
    """Return (cases, chunk_manifest) — each chunk named and sha-bound so a
    census row is pinned to the exact evidence it counted (finding 10)."""
    cases: list[dict] = []
    manifest: list[dict] = []
    suite_dir = CASES_DIR / suite
    if not suite_dir.is_dir():
        return cases, manifest
    for chunk in sorted(suite_dir.glob("chunk-*.json")):
        try:
            raw = chunk.read_text()
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        manifest.append(
            {
                "chunk": str(chunk.relative_to(REPO_ROOT)),
                "sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }
        )
        rows = payload if isinstance(payload, list) else payload.get("cases") or []
        cases.extend(row for row in rows if isinstance(row, dict))
    return cases, manifest


def _census_suite(suite: str, report: dict) -> dict:
    field_values: dict[str, set[str]] = defaultdict(set)
    concept_values: dict[str, set[str]] = defaultdict(set)
    scanned = 0

    def eat_case(case: dict) -> None:
        nonlocal scanned
        scanned += 1
        # Compact chunk rows: i = [{n, v}], v = [{c, l, x}].
        for record in case.get("i") or []:
            if isinstance(record, dict) and record.get("n") is not None:
                field_values[str(record["n"])].add(
                    _canonical_value(record.get("v"))
                )
        for verdict in case.get("v") or []:
            if isinstance(verdict, dict) and verdict.get("c"):
                concept_values[str(verdict["c"])].add(
                    _canonical_value(verdict.get("l"))
                )
        # Inline report cases: scalar metadata entries are stage evidence.
        metadata = case.get("metadata")
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if isinstance(value, (int, float, str, bool)) or value is None:
                    field_values[str(key)].add(_canonical_value(value))

    # Chunks are the full per-case record when they exist; the inline report
    # usually keeps a single illustrative case. Mixing the two would count
    # every field of that one inline case as "constant" and drown the signal —
    # but the inline cases must not vanish silently either (finding 7): their
    # count is recorded so eclipse is visible.
    chunk_cases, chunk_manifest = _chunk_cases(suite)
    inline_cases = [c for c in report.get("cases") or [] if isinstance(c, dict)]
    if chunk_cases:
        for case in chunk_cases:
            eat_case(case)
    else:
        for case in inline_cases:
            eat_case(case)

    fields = {
        name: {
            "distinct": len(values),
            "state": "varied" if len(values) > 1 else "constant",
        }
        for name, values in sorted(field_values.items())
    }
    concepts = {
        name: {"distinct_left_values": len(values)}
        for name, values in sorted(concept_values.items())
    }
    varied = sum(1 for f in fields.values() if f["state"] == "varied")
    return {
        "cases_scanned": scanned,
        "evidence_source": "chunks" if chunk_cases else "inline",
        "inline_cases_not_counted": len(inline_cases) if chunk_cases else 0,
        "chunk_manifest": chunk_manifest,
        "evidence_fields": fields,
        "verdict_concepts": concepts,
        "varied_fields": varied,
        "constant_fields": len(fields) - varied,
        "bridged_through": BRIDGED_THROUGH.get(suite, {}),
        "bridge_audited": suite in BRIDGED_THROUGH,
    }


def build_census() -> dict:
    suites = {}
    for suite, report in _iter_suite_reports():
        suites[suite] = _census_suite(suite, report)
    return {
        "schema": SCHEMA,
        "_comment": (
            "Generated by scripts/exercise_census.py — do not hand-edit. "
            "Per suite: distinct-value counts across committed per-case "
            "evidence. 'constant' means no evidence of variation exists in "
            "the suite, not that the dimension is untested elsewhere; "
            "'bridged_through' lists dimensions satisfied by construction "
            "(declared per audited bridge). cases_scanned: 0 means the suite "
            "commits no per-case rows; nonzero cases with zero evidence "
            "fields means the committed rows carry verdicts only. Either "
            "way, the absence is the finding."
        ),
        "suites": suites,
    }


def render_markdown(census: dict) -> str:
    lines = [
        "| suite | cases | varied | constant | bridge audited |",
        "|---|---:|---:|---:|---|",
    ]
    for suite, row in sorted(census["suites"].items()):
        lines.append(
            f"| {suite} | {row['cases_scanned']} | {row['varied_fields']} "
            f"| {row['constant_fields']} | "
            f"{'yes' if row['bridge_audited'] else 'no'} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    census = build_census()
    rendered = json.dumps(census, indent=2, sort_keys=True) + "\n"

    if args.markdown:
        print(render_markdown(census))
        return 0
    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"missing {OUTPUT_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        if OUTPUT_PATH.read_text() != rendered:
            print(
                "exercise census drifted — regenerate with "
                "`uv run python scripts/exercise_census.py`",
                file=sys.stderr,
            )
            return 1
        print("exercise census up to date")
        return 0

    OUTPUT_PATH.write_text(rendered)
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(render_markdown(census))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
