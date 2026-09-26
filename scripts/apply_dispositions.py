#!/usr/bin/env python3
"""Join dispositions into dashboard reports and registered report artifacts.

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
arithmetic that does not reconcile, dangling source paths, TAXSIM-lane
entries without attribution / oracle binding / population binding), when a
TAXSIM-lane mismatch row is claimed by two entries (classification
conservation), when an entry's `evidence.row_arithmetic` fails on a
checked-in report's rows, or when a checked-in report or coverage rollup no
longer matches what the merge would produce. Reports whose suite has no
dispositions file are left untouched.
Reports that merged dispositions before trimming stored mismatch examples
(premerged-slim) are validated against their bound source full report —
aggregate block, row-level assignment digest, and retained-row annotations,
failing closed when the source is missing or edited; only suites with no
committed full report and no source pointer keep the trusted precomputed
block (see ``_premerged_block_problems``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    DispositionError,
    apply_dispositions,
    assignment_digest,
    dispositioned_rollup,
    load_dispositions,
    report_is_taxsim_lane,
    report_json_text,
    suite_context,
)
from axiom_oracles.comparison.report_io import (  # noqa: E402
    load_report,
    read_report_text,
    registered_report_paths,
    write_report_text,
)

DISPOSITIONS_DIR = REPO_ROOT / "dispositions"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
# This ledger is consumed and validated by us_tariff_schedule_campaign.py.
# Its campaign-unit selectors include slots and instrument fields outside
# the shared mismatch-row schema, so the shared merge must not load it.
CAMPAIGN_LOCAL_DISPOSITIONS_FILES = frozenset({"us-tariff-schedule.yaml"})
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


#: An expiry reason that means the ledger's own evidence is contradicted by
#: the committed report's rows — a hard --check failure, not a soft expiry.
_EVIDENCE_FAILURE_REASONS = frozenset({"row_arithmetic_failed"})


def _evidence_failures(rel: object, block: dict) -> list[str]:
    """Problems for entries whose row arithmetic fails on committed rows."""

    reasons = block.get("expired_reasons") or {}
    return [
        f"{rel}: dispositions entry {entry_id!r} fails its "
        f"evidence.row_arithmetic on the committed rows ({reason}) — the "
        "classification's own evidence is contradicted; fix or remove it"
        for entry_id, reason in sorted(reasons.items())
        if reason in _EVIDENCE_FAILURE_REASONS
    ]


def _taxsim_lane(report: dict) -> bool:
    return (
        report_is_taxsim_lane(report)
        or suite_context(report.get("suite"), REPO_ROOT).taxsim_lane
    )


def _load_dispositions_files() -> tuple[dict[str, dict], list[str]]:
    """Load every shared dispositions file, returning {suite: doc} and errors."""

    by_suite: dict[str, dict] = {}
    errors: list[str] = []
    for path in sorted(DISPOSITIONS_DIR.glob("*.yaml")):
        if path.name in CAMPAIGN_LOCAL_DISPOSITIONS_FILES:
            continue
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


def _reports(*, suites: set[str] | None = None) -> Iterator[tuple[Path, dict]]:
    """Published reports plus explicit suite artifacts, never report archives."""

    reports = [
        (path, report) for path, report in _dashboard_reports()
        if suites is None or report.get("suite") in suites
    ]
    yield from reports
    seen = {path.resolve() for path, _ in reports}
    for path in registered_report_paths(REPO_ROOT, suites=suites):
        if path in seen:
            continue
        # Missing or malformed registered artifacts must fail --check rather
        # than disappearing from the ledger validation surface.
        report = load_report(path)
        if "summary" not in report or "suite" not in report:
            raise ValueError(f"{path}: registered artifact is not a comparison report")
        yield path, report


def _serialize_like(path: Path, original_text: str, report: dict) -> str:
    """Rewrite `report` in the same on-disk format `path` already uses."""

    original = json.loads(original_text)
    if path.suffix == ".gz":
        return json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
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
    for path, report in _reports():
        suite = report.get("suite")
        dispositions = dispositions_by_suite.get(suite)
        if dispositions is None:
            if str(suite).startswith("be-"):
                be_reports.append(report)
            continue
        if _is_premerged_slim_report(report):
            # The slim copy cannot be re-merged (its mismatch rows are a
            # bounded sample), but its embedded full-run block is NOT
            # trusted where the suite commits its full report: it is
            # re-derived from that report, so a dispositions edit or a
            # hand-edited block fails --check instead of riding a
            # trusted-block bypass (sol stack review F2).
            problems.extend(_premerged_block_problems(path, report, dispositions))
            if str(suite).startswith("be-"):
                be_reports.append(report)
            continue
        try:
            merged = apply_dispositions(
                report,
                dispositions,
                dispositions_file=f"dispositions/{suite}.yaml",
                taxsim_lane=_taxsim_lane(report),
            )
        except DispositionError as exc:
            problems.append(f"{path.relative_to(REPO_ROOT)}: {exc}")
            continue
        problems.extend(
            _evidence_failures(
                path.relative_to(REPO_ROOT), merged["summary"]["dispositioned"]
            )
        )
        if str(suite).startswith("be-"):
            be_reports.append(merged)
        original_text = read_report_text(path)
        merged_text = _serialize_like(path, original_text, merged)
        if merged_text == original_text:
            continue
        if check:
            problems.append(
                f"{path.relative_to(REPO_ROOT)} is stale: rerun "
                "`uv run scripts/apply_dispositions.py`"
            )
        else:
            write_report_text(path, merged_text)
            print(f"Updated {path.relative_to(REPO_ROOT)}")
            changed = True
    return problems, be_reports, changed


def _committed_full_reports(suite: str) -> list[tuple[Path, dict]]:
    """Committed FULL reports under reports/ for a suite.

    A report is full when it stores EVERY mismatch row its summary counts —
    the only artifact a premerged-slim dashboard block can be re-derived
    from.
    """

    matches: list[tuple[Path, dict]] = []
    reports_dir = REPO_ROOT / "reports"
    if not reports_dir.exists():
        return matches
    paths = set(reports_dir.glob("*.json")) | set(registered_report_paths(REPO_ROOT, suites={suite}))
    for path in sorted(paths):
        try:
            data = load_report(path)
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("suite") != suite:
            continue
        summary = data.get("summary") or {}
        if len(data.get("mismatches") or []) == summary.get("mismatch_count"):
            matches.append((path, data))
    return matches


#: Block keys the generator adds ON TOP of the fresh-merge block to bind it
#: to its source full report; excluded from the aggregate comparison and
#: validated separately.
_BINDING_KEYS = ("source_report", "assignment_sha256")


def _premerged_block_problems(
    path: Path, report: dict, dispositions: dict
) -> list[str]:
    """Validate a premerged-slim report's embedded dispositioned block.

    Fail-closed validation ladder (sol stack reviews r1 F2 + r2):

    1. A block carrying a ``source_report`` pointer names its exact source
       full report (repo-relative path + file sha256). The pointed file
       must exist, hash-match, and be FULL — otherwise a problem: an
       unavailable or edited source can never silently fall back to
       trusting the block.
    2. Against the resolved source (pointer, or every committed full
       report when the block predates pointers — itself flagged), a fresh
       dispositions merge must reproduce (a) the aggregate block, (b) the
       complete row-level assignment digest, and (c) every retained
       mismatch row's disposition annotation. Aggregate counts alone
       cannot see two equal-cardinality entries swapping classes; the
       digest and row annotations can.
    3. Only a suite with NO committed full report and NO pointer keeps the
       trust-the-block behavior (population diagnostics store aggregates
       only; there is nothing to re-derive from).

    Divergence is a problem in BOTH modes — the dashboard copy is rebuilt
    by the suite's generation lane, never patched here.
    """

    suite = report.get("suite")
    rel = path.relative_to(REPO_ROOT)
    problems: list[str] = []
    embedded = (report.get("summary") or {}).get("dispositioned")
    if not isinstance(embedded, dict):
        return [f"{rel} premerged block is not a mapping"]
    pointer = embedded.get("source_report")

    sources: list[tuple[Path, dict]] = []
    if pointer is not None:
        source = _resolve_source_pointer(rel, str(suite), pointer, problems)
        if source is None:
            return problems  # fail closed: never trust an unbound block
        sources = [source]
    else:
        sources = _committed_full_reports(str(suite))
        if not sources:
            return []  # nothing to re-derive from (rule 3)
        problems.append(
            f"{rel} premerged block lacks a source_report pointer although "
            f"the {suite} suite commits a full report — refresh the report "
            "so its dashboard copy binds to its source"
        )

    embedded_core = {
        k: v for k, v in embedded.items() if k not in _BINDING_KEYS
    }
    # One retained row per (case_id, concept): a case validly carries one
    # mismatch row per concept, so keying by case_id alone would collapse
    # same-case rows and hide drift among them (sol stack review r3).
    embedded_rows = [
        (row.get("case_id"), row.get("concept"), row.get("disposition"))
        for row in report.get("mismatches") or []
    ]
    for full_path, full in sources:
        full_rel = full_path.relative_to(REPO_ROOT)
        try:
            merged = apply_dispositions(
                full,
                dispositions,
                dispositions_file=f"dispositions/{suite}.yaml",
                taxsim_lane=_taxsim_lane(full),
            )
        except DispositionError as exc:
            problems.append(f"{full_rel}: {exc}")
            continue
        problems.extend(
            _evidence_failures(full_rel, merged["summary"]["dispositioned"])
        )
        if embedded_core != merged["summary"]["dispositioned"]:
            problems.append(
                f"{rel} embeds a summary.dispositioned block that does not "
                f"match a fresh dispositions merge over {full_rel} — "
                f"refresh the {suite} report so its dashboard copy is "
                "rebuilt from the full merge"
            )
        expected_digest = assignment_digest(merged)
        if (
            pointer is not None
            and embedded.get("assignment_sha256") != expected_digest
        ):
            problems.append(
                f"{rel} assignment_sha256 does not match the fresh "
                f"dispositions merge over {full_rel} — a row-level "
                "reclassification (possibly count-preserving) drifted from "
                "the embedded block; refresh the report"
            )
        merged_by_row = {
            (row.get("case_id"), row.get("concept")): row.get("disposition")
            for row in merged.get("mismatches") or []
        }
        for case_id, concept, annotation in embedded_rows:
            key = (case_id, concept)
            if key not in merged_by_row:
                problems.append(
                    f"{rel} retains mismatch row {case_id!r}/{concept!r} "
                    f"that the fresh merge over {full_rel} does not produce"
                )
            elif annotation != merged_by_row[key]:
                problems.append(
                    f"{rel} retained mismatch row {case_id!r}/{concept!r} "
                    "carries a disposition annotation that does not match "
                    f"the fresh merge over {full_rel} — refresh the report"
                )
    return problems


def _resolve_source_pointer(
    rel: Path, suite: str, pointer: object, problems: list[str]
) -> tuple[Path, dict] | None:
    """Resolve and verify a block's source_report pointer, fail closed.

    Appends a problem and returns None unless the pointer names an
    existing, hash-matching, FULL report for this suite via a
    repo-relative path inside the repo's reports/ directory.
    """

    if not isinstance(pointer, dict):
        problems.append(f"{rel} source_report pointer is not a mapping")
        return None
    raw_path = pointer.get("path")
    digest = pointer.get("sha256")
    if not isinstance(raw_path, str) or not isinstance(digest, str):
        problems.append(
            f"{rel} source_report pointer needs string `path` and `sha256`"
        )
        return None
    if Path(raw_path).is_absolute():
        problems.append(
            f"{rel} source_report path {raw_path!r} must be repo-relative"
        )
        return None
    candidate = (REPO_ROOT / raw_path).resolve()
    reports_dir = (REPO_ROOT / "reports").resolve()
    if reports_dir not in candidate.parents:
        problems.append(
            f"{rel} source_report path {raw_path!r} is outside reports/"
        )
        return None
    if not candidate.is_file():
        problems.append(
            f"{rel} source_report {raw_path!r} is missing — the premerged "
            "block cannot be validated and is not trusted"
        )
        return None
    payload = candidate.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != digest:
        problems.append(
            f"{rel} source_report {raw_path!r} sha256 mismatch "
            f"(expected {digest}, found {actual}) — the source full report "
            "changed without a dashboard refresh"
        )
        return None
    try:
        data = json.loads(read_report_text(candidate))
    except (ValueError, OSError, EOFError):
        problems.append(f"{rel} source_report {raw_path!r} is not JSON")
        return None
    if not isinstance(data, dict) or data.get("suite") != suite:
        problems.append(
            f"{rel} source_report {raw_path!r} is not a {suite} report"
        )
        return None
    summary = data.get("summary") or {}
    if len(data.get("mismatches") or []) != summary.get("mismatch_count"):
        problems.append(
            f"{rel} source_report {raw_path!r} is not a FULL report "
            "(stored mismatch rows != mismatch_count)"
        )
        return None
    return candidate, data


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
        report.get("suite"): report for _, report in _reports(suites=set(dispositions_by_suite))
    }
    for suite, dispositions in sorted(dispositions_by_suite.items()):
        report = reports_by_suite.get(suite)
        if report is None:
            print(
                f"note: dispositions/{suite}.yaml has no committed "
                "report"
            )
            continue
        if _is_premerged_slim_report(report):
            # Re-merging against the trimmed mismatch sample would report
            # entries outside the stored examples as orphaned/expired; the
            # generator already computed the full-run block.
            block = report["summary"]["dispositioned"]
        else:
            try:
                merged = apply_dispositions(
                    report, dispositions, taxsim_lane=_taxsim_lane(report)
                )
            except DispositionError:
                continue  # already reported as a problem by _merge_reports
            block = merged["summary"]["dispositioned"]
        reasons = block.get("expired_reasons") or {}
        for entry_id in block["orphaned_entries"]:
            print(
                f"warning: dispositions/{suite}.yaml entry {entry_id!r} "
                "matches no live mismatch row; delete it or mark it "
                "expires_on_source_change"
            )
        for entry_id in block["expired_entries"]:
            reason = reasons.get(entry_id)
            print(
                f"note: dispositions/{suite}.yaml entry {entry_id!r} is "
                "expired ("
                + (reason or "source values changed or mismatch cleared")
                + ")"
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

    try:
        problems, be_reports, _ = _merge_reports(
            dispositions_by_suite, check=args.check
        )
    except (OSError, ValueError, EOFError) as exc:
        print(f"Cannot validate registered report: {exc}", file=sys.stderr)
        return 1
    rollup_problems, _ = _refresh_be_rollup(be_reports, check=args.check)
    problems.extend(rollup_problems)
    _report_orphans(dispositions_by_suite)

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("Dispositions are consistent with the committed reports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
