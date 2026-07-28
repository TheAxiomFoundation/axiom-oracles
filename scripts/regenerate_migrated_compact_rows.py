#!/usr/bin/env python3
"""Regenerate migrated compact rows from their immutable source corpus.

The evidence migration in ``a753d092`` bound two pre-existing Colorado chunk
corpora to slim dashboard reports. This tool replays those exact source chunks
from the migration's parent, projects the current report's disposition markers
onto every mismatch row, validates the complete semantic projection, and only
then writes chunks plus a fresh v1 binding index.

It intentionally does not run comparison engines or the generic dashboard
emitter. The former would create a new execution identity; the latter does not
hold the ignored full reports that originally produced these corpora.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.evidence import (  # noqa: E402
    build_chunk_index,
    dashboard_delta,
    dashboard_match_rate,
    is_safe_suite_name,
    strict_json_loads,
    validate_suite_evidence,
)


SOURCE_REF = "6c4f17bfe6dc8224ee8251401fe0247b1117a25b"
DEFAULT_REPORTS = (
    "dashboard/public/data/axiom-policyengine-co-snap-ecps.json",
    "dashboard/public/data/axiom-snapqc-co-snap.json",
)


def _repo_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{raw}: report must be inside the repository") from exc
    return resolved


def _git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def source_chunks(
    report_path: Path,
    suite: str,
    *,
    source_ref: str,
) -> list[tuple[str, list[dict]]]:
    chunk_dir = report_path.parent / "cases" / suite
    relative_dir = chunk_dir.relative_to(REPO_ROOT).as_posix()
    names = [
        Path(line).name
        for line in _git(
            "ls-tree",
            "-r",
            "--name-only",
            source_ref,
            "--",
            relative_dir,
        )
        .decode()
        .splitlines()
        if Path(line).name.startswith("chunk-") and Path(line).name.endswith(".json")
    ]
    if not names:
        raise ValueError(f"{source_ref}:{relative_dir} contains no compact chunks")

    chunks: list[tuple[str, list[dict]]] = []
    for name in sorted(names):
        relative = f"{relative_dir}/{name}"
        raw = _git("show", f"{source_ref}:{relative}")
        payload = strict_json_loads(raw)
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise ValueError(
                f"{source_ref}:{relative} must be an array of case objects"
            )
        chunks.append((name, payload))
    return chunks


def _case_id(row: dict, key: str) -> str:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"invalid {key} {value!r}")
    if isinstance(value, str) and not value:
        raise ValueError(f"invalid empty {key}")
    return str(value)


def _report_markers(report: dict) -> dict[tuple[str, str], str | None]:
    raw = report.get("mismatches")
    if not isinstance(raw, list):
        raise ValueError("report mismatches must be an array")
    markers: dict[tuple[str, str], str | None] = {}
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"report mismatches[{index}] must be an object")
        case_id = _case_id(row, "case_id")
        concept = row.get("concept")
        if not isinstance(concept, str) or not concept:
            raise ValueError(
                f"report mismatches[{index}].concept must be a non-empty string"
            )
        key = (case_id, concept)
        if key in markers:
            raise ValueError(f"report mismatches repeats {key!r}")
        raw_marker = row.get("disposition")
        if raw_marker is None:
            marker = None
        elif (
            isinstance(raw_marker, dict)
            and isinstance(raw_marker.get("disposition"), str)
            and raw_marker["disposition"]
        ):
            marker = raw_marker["disposition"]
        else:
            raise ValueError(f"report mismatches[{index}].disposition is malformed")
        markers[key] = marker
    return markers


def project_dispositions(
    report: dict,
    chunks: list[tuple[str, list[dict]]],
) -> list[tuple[str, list[dict]]]:
    """Project report markers and canonical deltas onto a source corpus."""

    report_markers = _report_markers(report)
    projected: list[tuple[str, list[dict]]] = []
    stored_keys: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for name, rows in chunks:
        projected_rows: list[dict] = []
        for row_index, source_row in enumerate(rows):
            row = dict(source_row)
            case_id = _case_id(row, "id")
            if case_id in seen_ids:
                raise ValueError(f"source chunks repeat case id {case_id!r}")
            seen_ids.add(case_id)
            raw_matches = row.get("v")
            raw_mismatches = row.get("m")
            if raw_matches is not None and not isinstance(raw_matches, list):
                raise ValueError(f"{name} row {row_index}.v must be an array")
            if not isinstance(raw_mismatches, list):
                raise ValueError(f"{name} row {row_index}.m must be an array")
            matched_concepts = {
                verdict.get("c")
                for verdict in raw_matches or []
                if isinstance(verdict, dict)
            }
            mismatch_concepts: set[str] = set()
            projected_mismatches: list[dict] = []
            for mismatch_index, source_mismatch in enumerate(raw_mismatches):
                if not isinstance(source_mismatch, dict):
                    raise ValueError(
                        f"{name} row {row_index}.m[{mismatch_index}] must be an object"
                    )
                mismatch = dict(source_mismatch)
                concept = mismatch.get("c")
                if not isinstance(concept, str) or not concept:
                    raise ValueError(
                        f"{name} row {row_index}.m[{mismatch_index}].c "
                        "must be a non-empty string"
                    )
                if concept in mismatch_concepts:
                    raise ValueError(
                        f"{name} row {row_index}.m repeats concept {concept!r}"
                    )
                if concept in matched_concepts:
                    raise ValueError(
                        f"{name} row {row_index} concept {concept!r} appears "
                        "in both matched and mismatched verdicts"
                    )
                mismatch_concepts.add(concept)
                key = (case_id, concept)
                if key in stored_keys:
                    raise ValueError(f"source chunks repeat mismatch {key!r}")
                stored_keys.add(key)
                if key not in report_markers:
                    raise ValueError(
                        f"source mismatch {key!r} has no report mismatch row"
                    )
                marker = report_markers[key]
                if marker is None:
                    mismatch.pop("e", None)
                else:
                    mismatch["e"] = marker
                # Historical chunks used the report's left-minus-right
                # diagnostic. The dashboard contract is right minus left, so
                # derive it from the bound values instead of trusting either
                # source convention.
                mismatch["d"] = dashboard_delta(
                    mismatch.get("l"),
                    mismatch.get("x"),
                )
                projected_mismatches.append(mismatch)
            row["m"] = projected_mismatches
            if isinstance(raw_matches, list):
                row["r"] = dashboard_match_rate(
                    len(raw_matches),
                    len(projected_mismatches),
                )
            projected_rows.append(row)
        projected.append((name, projected_rows))

    missing = sorted(set(report_markers) - stored_keys)
    if missing:
        raise ValueError(
            f"report mismatch rows have no source chunk mismatch {missing}"
        )
    return projected


def _render_chunk(rows: list[dict]) -> str:
    return json.dumps(rows, separators=(",", ":"))


def _validate_projection(
    report_path: Path,
    report: dict,
    suite: str,
    chunks: list[tuple[str, list[dict]]],
) -> str:
    with tempfile.TemporaryDirectory(prefix="axiom-evidence-regeneration-") as raw:
        root = Path(raw)
        staged_report = root / report_path.name
        staged_report.write_bytes(report_path.read_bytes())
        staged_dir = root / "cases" / suite
        staged_dir.mkdir(parents=True)
        for name, rows in chunks:
            (staged_dir / name).write_text(_render_chunk(rows))
        evidence = validate_suite_evidence(staged_report)
        if not evidence.content_valid or evidence.reconciliation == "none":
            details = "\n".join(f"- {defect}" for defect in evidence.content_defects)
            raise ValueError(
                f"source corpus does not semantically reproduce {suite}:\n{details}"
            )
        return evidence.reconciliation


def _render_index(payload: dict) -> str:
    return json.dumps(payload, indent=2) + "\n"


def regenerate(
    report_path: Path,
    *,
    source_ref: str,
    check: bool,
) -> tuple[bool, str]:
    report_path = _repo_path(report_path)
    payload = strict_json_loads(report_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{report_path}: report must be an object")
    suite = payload.get("suite")
    if not is_safe_suite_name(suite):
        raise ValueError(f"{report_path}: report suite is unsafe")

    source = source_chunks(report_path, suite, source_ref=source_ref)
    projected = project_dispositions(payload, source)
    reconciliation = _validate_projection(
        report_path,
        payload,
        suite,
        projected,
    )
    out_dir = report_path.parent / "cases" / suite
    expected_chunks = {name: _render_chunk(rows) for name, rows in projected}

    if check:
        stale = [
            name
            for name, expected in expected_chunks.items()
            if not (out_dir / name).is_file()
            or (out_dir / name).read_text() != expected
        ]
        unexpected = sorted(
            path.name
            for path in out_dir.glob("chunk-*.json")
            if path.name not in expected_chunks
        )
        if stale or unexpected:
            return (
                False,
                f"STALE {suite}: chunks={stale}, unexpected={unexpected}",
            )
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, expected in expected_chunks.items():
            (out_dir / name).write_text(expected)
        for path in out_dir.glob("chunk-*.json"):
            if path.name not in expected_chunks:
                path.unlink()

    candidate = build_chunk_index(report_path)
    index_path = out_dir / "index.json"
    expected_index = _render_index(candidate)
    if check:
        if not index_path.is_file() or index_path.read_text() != expected_index:
            return False, f"STALE {index_path.relative_to(REPO_ROOT)}"
    else:
        index_path.write_text(expected_index)

    evidence = validate_suite_evidence(report_path)
    if (
        not evidence.valid
        or evidence.binding != "bound"
        or evidence.reconciliation != reconciliation
    ):
        details = "\n".join(f"- {defect}" for defect in evidence.defects)
        raise ValueError(
            f"regenerated evidence did not validate for {suite}:\n{details}"
        )
    action = "verified" if check else "regenerated"
    return (
        True,
        f"{action} {suite} from {source_ref}: "
        f"{evidence.binding}/{evidence.reconciliation}, "
        f"{evidence.case_count} cases",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports",
        nargs="*",
        help="repository-relative reports (defaults to the two migrated suites)",
    )
    parser.add_argument(
        "--source-ref",
        default=SOURCE_REF,
        help="immutable git ref containing the authoritative source chunks",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify regenerated chunks and indexes without writing",
    )
    args = parser.parse_args()

    ok = True
    for raw in args.reports or DEFAULT_REPORTS:
        try:
            passed, message = regenerate(
                _repo_path(raw),
                source_ref=args.source_ref,
                check=args.check,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            passed, message = False, f"ERROR {raw}: {exc}"
        print(message)
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
