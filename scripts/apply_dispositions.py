#!/usr/bin/env python3
"""Join dispositions/<suite>.yaml into checked-in dashboard reports.

Comparison suites that run outside CI (the EUROMOD Belgium lane, for
example) commit their dashboard JSON directly, so the disposition merge that
`scripts/run_comparison.py` performs at generation time has to be applied to
those files here. The script also maintains the Belgium EUROMOD coverage
rollup (`dispositioned_parity`) so the coverage surface carries both the raw
and the explained parity rate.

Usage:
    uv run scripts/apply_dispositions.py            # rewrite reports in place
    uv run scripts/apply_dispositions.py --check    # validate; exit 1 on drift

`--check` fails when a dispositions file is schema-invalid (missing evidence,
arithmetic that does not reconcile, dangling source paths) or when a
checked-in report or coverage rollup no longer matches what the merge would
produce. Reports whose suite has no dispositions file are left untouched.
Reports that already merged dispositions before trimming stored mismatch
examples keep that precomputed full-run disposition block.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    DispositionError,
    apply_dispositions,
    dispositioned_rollup,
    load_dispositions,
    report_json_text,
)

DISPOSITIONS_DIR = REPO_ROOT / "dispositions"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
BE_COVERAGE_SOURCES = (
    REPO_ROOT / "axiom_oracles" / "data" / "euromod_be_coverage.json",
    DASHBOARD_DATA_DIR / "euromod-be-coverage.json",
)
BE_ROLLUP_NOTE = (
    "Raw = exact per-comparison matches across the committed be-* dashboard "
    "suites. Explained adds mismatches carrying a schema-validated "
    "disposition (explained residuals, upstream engine gaps, bridge "
    "artifacts) from dispositions/<suite>.yaml."
)


def _load_dispositions_files() -> tuple[dict[str, dict], list[str]]:
    """Load every dispositions file, returning {suite: doc} and errors."""

    by_suite: dict[str, dict] = {}
    errors: list[str] = []
    for path in sorted(DISPOSITIONS_DIR.glob("*.yaml")):
        try:
            by_suite[path.stem] = load_dispositions(path, repo_root=REPO_ROOT)
        except DispositionError as exc:
            errors.append(str(exc))
    return by_suite, errors


def _dashboard_reports() -> list[tuple[Path, dict]]:
    reports = []
    for path in sorted(DASHBOARD_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "summary" in data and "suite" in data:
            reports.append((path, data))
    return reports


def _serialize_like(path: Path, original_text: str, report: dict) -> str:
    """Rewrite `report` in the same on-disk format `path` already uses."""

    original = json.loads(original_text)
    if report_json_text(original) == original_text:
        return report_json_text(report)
    plain = json.dumps(original, indent=2, sort_keys=True)
    if original_text in (plain, plain + "\n"):
        text = json.dumps(report, indent=2, sort_keys=True)
        return text + "\n" if original_text.endswith("\n") else text
    # Unknown formatting (hand-edited): use the streaming report format.
    return report_json_text(report)


def _merge_reports(
    dispositions_by_suite: dict[str, dict],
    *,
    check: bool,
) -> tuple[list[str], list[dict], bool]:
    """Merge dispositions into dashboard reports.

    Returns (problems, merged BE reports for the rollup, changed_anything).
    """

    problems: list[str] = []
    be_reports: list[dict] = []
    changed = False
    for path, report in _dashboard_reports():
        suite = report.get("suite")
        dispositions = dispositions_by_suite.get(suite)
        if dispositions is None:
            if str(suite).startswith("be-"):
                be_reports.append(report)
            continue
        if _is_premerged_slim_report(report):
            if str(suite).startswith("be-"):
                be_reports.append(report)
            continue
        merged = apply_dispositions(
            report,
            dispositions,
            dispositions_file=f"dispositions/{suite}.yaml",
        )
        if str(suite).startswith("be-"):
            be_reports.append(merged)
        original_text = path.read_text()
        merged_text = _serialize_like(path, original_text, merged)
        if merged_text == original_text:
            continue
        if check:
            problems.append(
                f"{path.relative_to(REPO_ROOT)} is stale: rerun "
                "`uv run scripts/apply_dispositions.py`"
            )
        else:
            path.write_text(merged_text)
            print(f"Updated {path.relative_to(REPO_ROOT)}")
            changed = True
    return problems, be_reports, changed


def _is_premerged_slim_report(report: dict) -> bool:
    """Whether a report merged dispositions before trimming mismatch rows.

    Some population diagnostics keep aggregate counts over the full run while
    storing only a bounded sample of mismatch examples for the dashboard. For
    those reports, applying dispositions after the trim would undercount the
    full-run explained residuals, so the generator writes the v2.1 report with a
    precomputed ``summary.dispositioned`` block.
    """

    summary = report.get("summary") or {}
    if report.get("schema_version") != "axiom.comparison_report.v2.1":
        return False
    if not isinstance(summary.get("dispositioned"), dict):
        return False
    stored = summary.get("stored_mismatch_example_count")
    mismatch_count = summary.get("mismatch_count") or 0
    return isinstance(stored, int) and stored < mismatch_count


def _refresh_be_rollup(
    be_reports: list[dict],
    *,
    check: bool,
) -> tuple[list[str], bool]:
    if not be_reports:
        return [], False
    rollup = dispositioned_rollup(be_reports)
    rollup["note"] = BE_ROLLUP_NOTE
    problems: list[str] = []
    changed = False
    for path in BE_COVERAGE_SOURCES:
        if not path.exists():
            continue
        text = path.read_text()
        data = json.loads(text)
        if data.get("dispositioned_parity") == rollup:
            continue
        if check:
            problems.append(
                f"{path.relative_to(REPO_ROOT)} dispositioned_parity is "
                "stale: rerun `uv run scripts/apply_dispositions.py`"
            )
            continue
        data["dispositioned_parity"] = rollup
        serialized = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(
            serialized + "\n" if text.endswith("\n") else serialized
        )
        print(f"Updated {path.relative_to(REPO_ROOT)} dispositioned_parity")
        changed = True
    return problems, changed


def _report_orphans(dispositions_by_suite: dict[str, dict]) -> None:
    """Warn about entries that no longer match any live mismatch row."""

    reports_by_suite = {
        report.get("suite"): report for _, report in _dashboard_reports()
    }
    for suite, dispositions in sorted(dispositions_by_suite.items()):
        report = reports_by_suite.get(suite)
        if report is None:
            print(
                f"note: dispositions/{suite}.yaml has no committed "
                "dashboard report"
            )
            continue
        merged = apply_dispositions(report, dispositions)
        block = merged["summary"]["dispositioned"]
        for entry_id in block["orphaned_entries"]:
            print(
                f"warning: dispositions/{suite}.yaml entry {entry_id!r} "
                "matches no live mismatch row; delete it or mark it "
                "expires_on_source_change"
            )
        for entry_id in block["expired_entries"]:
            print(
                f"note: dispositions/{suite}.yaml entry {entry_id!r} is "
                "expired (source values changed or mismatch cleared)"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate without writing; non-zero exit on any problem.",
    )
    args = parser.parse_args()

    dispositions_by_suite, schema_errors = _load_dispositions_files()
    if schema_errors:
        for error in schema_errors:
            print(error, file=sys.stderr)
        return 1
    print(
        f"Validated {len(dispositions_by_suite)} dispositions "
        f"file{'s' if len(dispositions_by_suite) != 1 else ''}"
    )

    problems, be_reports, _ = _merge_reports(
        dispositions_by_suite, check=args.check
    )
    rollup_problems, _ = _refresh_be_rollup(be_reports, check=args.check)
    problems.extend(rollup_problems)
    _report_orphans(dispositions_by_suite)

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("Dispositions are consistent with the committed dashboard data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
