#!/usr/bin/env python3
"""Generate report-bound, versioned indexes for certified case chunks.

The default set is the two chunk-backed legs currently named by
``certify.PROGRAMS``. Other reports may be supplied explicitly:

    python scripts/generate_chunk_indexes.py
    python scripts/generate_chunk_indexes.py --check
    python scripts/generate_chunk_indexes.py dashboard/public/data/report.json

``--strip-inline-mirrors`` is a one-time migration aid. It removes inline
``cases`` only when every inline case ID is already present in the chunks.
Strict evidence validation then treats chunks as the sole case corpus and can
enforce global ID uniqueness without silently deduplicating two sources.

After migration, the execution producer owns identity changes: this generic
generator permits only an idempotent v1 write. It refuses to bind changed
report or chunk bytes because summary reconciliation cannot prove that a
replacement chunk corpus came from the same execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.evidence import (  # noqa: E402
    build_chunk_index,
    strict_json_loads,
    validate_suite_evidence,
)


DEFAULT_REPORTS = (
    "dashboard/public/data/axiom-policyengine-co-snap-ecps.json",
    "dashboard/public/data/axiom-snapqc-co-snap.json",
)


def _case_id(row: object, key: str) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value)


def strip_inline_mirrors(report_path: Path) -> bool:
    """Remove inline rows only when chunks already carry every one of them."""

    report = strict_json_loads(report_path.read_text())
    if not isinstance(report, dict):
        raise ValueError(f"{report_path}: report must be an object")
    suite = report.get("suite")
    inline = report.get("cases") or []
    if not inline:
        return False
    if not isinstance(suite, str) or not isinstance(inline, list):
        raise ValueError(f"{report_path}: invalid suite/cases shape")

    inline_ids = [_case_id(row, "case_id") for row in inline]
    if any(case_id is None for case_id in inline_ids):
        raise ValueError(f"{report_path}: inline mirror has a malformed case id")
    if len(set(inline_ids)) != len(inline_ids):
        raise ValueError(f"{report_path}: inline cases contain duplicate IDs")
    chunk_ids: set[str] = set()
    chunk_count = 0
    chunk_dir = report_path.parent / "cases" / suite
    for chunk_path in sorted(chunk_dir.glob("chunk-*.json")):
        payload = strict_json_loads(chunk_path.read_text())
        if not isinstance(payload, list):
            raise ValueError(f"{chunk_path}: expected a compact case array")
        for row in payload:
            case_id = _case_id(row, "id")
            if case_id is None:
                raise ValueError(f"{chunk_path}: chunk has a malformed case id")
            if case_id in chunk_ids:
                raise ValueError(f"{chunk_path}: chunks contain duplicate ID {case_id}")
            chunk_ids.add(case_id)
            chunk_count += 1
    if report.get("case_count") != chunk_count:
        raise ValueError(
            f"{report_path}: report case_count {report.get('case_count')!r} "
            f"does not match {chunk_count} chunk IDs"
        )
    missing = sorted(set(inline_ids) - chunk_ids)
    if missing:
        raise ValueError(
            f"{report_path}: inline cases are not all chunk mirrors; "
            f"missing IDs include {missing[:5]}"
        )
    truncation = report.get("dashboard_truncation")
    if set(inline_ids) != chunk_ids and not (
        isinstance(truncation, dict)
        and truncation.get("shown_case_rows") == len(inline_ids)
        and truncation.get("total_case_rows") == chunk_count
    ):
        raise ValueError(
            f"{report_path}: a partial inline subset lacks matching "
            "dashboard_truncation cardinalities"
        )

    report["cases"] = []
    if isinstance(truncation, dict):
        truncation["shown_case_rows"] = 0
    else:
        mismatches = report.get("mismatches") or []
        report["dashboard_truncation"] = {
            "total_mismatches": len(mismatches),
            "shown_mismatches": len(mismatches),
            "total_case_rows": chunk_count,
            "shown_case_rows": 0,
        }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return True


def _render(payload: dict) -> str:
    return json.dumps(payload, indent=2) + "\n"


def _refuse_implicit_versioned_rebind(
    index_path: Path,
    candidate: dict,
    *,
    migration_verified: bool,
) -> None:
    """Keep the generic generator from blessing unproven replacement evidence.

    Once an index is versioned, only the producer that still holds the full
    execution case corpus may change its report or chunk identities. The
    generator can create an initial v1 index from legacy evidence and can
    repeat an idempotent write, but it cannot prove that changed chunks belong
    to a changed aggregate report after inline mirrors have been removed.
    """

    if not index_path.is_file():
        return
    existing = strict_json_loads(index_path.read_text())
    if (
        not isinstance(existing, dict)
        or existing.get("schema_version") != candidate["schema_version"]
        or migration_verified
    ):
        return
    identity_changed = (
        existing.get("report_path") != candidate["report_path"]
        or existing.get("report_sha256") != candidate["report_sha256"]
        or existing.get("case_verdicts_sha256")
        != candidate.get("case_verdicts_sha256")
        or existing.get("chunks") != candidate["chunks"]
    )
    if identity_changed:
        raise ValueError(
            f"{index_path}: refusing to rebind an existing versioned corpus "
            "to changed report/chunk identities; refresh chunks from the "
            "producer's full case corpus"
        )


def generate(
    report_path: Path,
    *,
    check: bool,
    strip_inline: bool,
) -> tuple[bool, str]:
    if strip_inline:
        if check:
            raise ValueError("--strip-inline-mirrors cannot be used with --check")
        stripped = strip_inline_mirrors(report_path)
    else:
        stripped = False

    candidate = build_chunk_index(report_path)
    suite = candidate["suite"]
    index_path = report_path.parent / "cases" / suite / "index.json"
    _refuse_implicit_versioned_rebind(
        index_path,
        candidate,
        migration_verified=stripped,
    )
    expected = _render(candidate)
    if check:
        actual = index_path.read_text() if index_path.is_file() else None
        if actual != expected:
            return False, f"STALE {index_path.relative_to(REPO_ROOT)}"
        evidence = validate_suite_evidence(report_path)
        if not evidence.valid or evidence.binding != "bound":
            return False, "\n".join(evidence.defects)
        return True, f"OK {suite}: {evidence.binding}/{evidence.reconciliation}"

    index_path.write_text(expected)
    evidence = validate_suite_evidence(report_path)
    if not evidence.valid or evidence.binding != "bound":
        details = "\n".join(f"- {defect}" for defect in evidence.defects)
        raise ValueError(f"generated index did not validate for {suite}:\n{details}")
    action = "migrated inline mirrors; " if stripped else ""
    return (
        True,
        f"{action}wrote {index_path.relative_to(REPO_ROOT)} "
        f"({evidence.binding}/{evidence.reconciliation})",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports",
        nargs="*",
        help="repository-relative report paths (defaults to certified chunk legs)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if an index differs from freshly generated content",
    )
    parser.add_argument(
        "--strip-inline-mirrors",
        action="store_true",
        help="one-time migration: remove inline cases duplicated in chunks",
    )
    args = parser.parse_args()

    raw_reports = args.reports or list(DEFAULT_REPORTS)
    ok = True
    for raw in raw_reports:
        path = Path(raw)
        if not path.is_absolute():
            path = REPO_ROOT / path
        try:
            passed, message = generate(
                path.resolve(),
                check=args.check,
                strip_inline=args.strip_inline_mirrors,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            passed, message = False, f"ERROR {raw}: {exc}"
        print(message)
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
