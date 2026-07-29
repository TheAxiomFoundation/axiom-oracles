#!/usr/bin/env python3
"""Audit the CA SNAP #423 disposition transition against the literal base.

This checker is deliberately read-only.  It resolves an explicit ``--base-ref``
to a commit, reads the disposition source from that commit with ``git show``,
and reconciles all 345 issue-#362 rows against the committed requested-month
report and its source and served disposition artifacts.

The compact case artifacts intentionally use their current ``id/r/h/m``
schema.  They are validated against every canonical mismatch row; this checker
does not require or recreate the retired ``i/o/v`` evidence payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SUITE = "ca-snap-ecps"

BASE_DISPOSITIONS_RELATIVE_PATH = "dispositions/ca-snap-ecps.yaml"
CURRENT_DISPOSITIONS_PATH = ROOT / BASE_DISPOSITIONS_RELATIVE_PATH
CURRENT_REPORT_PATH = (
    ROOT / "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json"
)
SERVED_DISPOSITIONS_PATH = ROOT / "dashboard/public/data/dispositions/ca-snap-ecps.json"
COMPACT_DIR = ROOT / "dashboard/public/data/cases/ca-snap-ecps"

BASE_DISPOSITIONS_SHA256 = (
    "18cfbe28f951261142bfa3c52d0c88f6d0a3d53b77b597fcd807b4d2e9a23086"
)
EXPECTED_BASE_ROWS = 345
EXPECTED_CURRENT_MISMATCHES = 529
EXPECTED_EXPANDED_DISPOSITIONS = 288
EXPECTED_PARTITION_COUNTS = {
    "vanished": 192,
    "current_but_dropped": 22,
    "kept": 131,
}
EXPECTED_PARTITION_DIGESTS = {
    "vanished": ("f968139b4cc46e2a2d95ce08d7ae97bfa3e446f7d8558a524fa3527bdb45f618"),
    "current_but_dropped": (
        "c4115d13add7504d41939a2e580fb0dab5b04c0cfa73cea1ffcb002dcdadcecd"
    ),
    "kept": ("2cfc51bf11031bd398cc7cd27e568f8a321df35eb9006d1acd86db112851cba3"),
}
EXPECTED_BASE_IDENTITY_DIGEST = (
    "77036d3f70198c2c0c56ffa7e608e8d752338e26152e183ef01351eb48d584f8"
)
EXPECTED_MOVEMENT_COUNTS = {"moved": 115, "unchanged": 16}
EXPECTED_MOVEMENT_DIGESTS = {
    "moved": ("c1c10db5635f1cb76ccc0908c64e1caf958c1826f5f87bd1dce03809589a6bab"),
    "unchanged": ("4ba943d873b252ba1ea84476ee669088829b327e8d9b66f1f73468efe01df475"),
}
# These digests and explicit pins are the compact tracked receipt derived from
# the exhaustive requested-month trace named below. The kept digest binds all
# 131 current source/report pins; the drift map makes each of the other 22
# requested-month-to-current movements reviewable.
EXPECTED_DRIFT_ROWS_SHA256 = (
    "fa54f6fdf05592da62c3c03b74264a4dfb7d9828e4f33ea169e75fc033ad3a51"
)
EXPECTED_KEPT_REQUESTED_MONTH_ROWS_SHA256 = (
    "06524b90f0fd49fac9e2856c73d5ee787df4190003ba7e56b0a71d47f160e0f3"
)
REQUESTED_MONTH_TRACE_SHA256 = (
    "c46af9b87c8f5ad01f1909bc45e80e00b4c4a50e5b802ea4ccbe194b5954b568"
)
REQUESTED_MONTH_DRIFT_PINS = {
    "ca-362-medical-input-ecps-57453-benefit": {
        "left": 225.0,
        "right": 298.0,
        "difference": -73.0,
    },
    "ca-362-period-ecps-57313-benefit": {
        "left": 623.0,
        "right": 623.5999755859375,
        "difference": -0.5999755859375,
    },
    "ca-362-period-self-employment-tanf-ecps-57027-benefit": {
        "left": 1571.0,
        "right": 942.5,
        "difference": 628.5,
    },
    "ca-362-period-self-employment-tanf-ecps-58088-benefit": {
        "left": 687.0,
        "right": 548.199951171875,
        "difference": 138.800048828125,
    },
    "ca-362-period-self-employment-tanf-ecps-60409-benefit": {
        "left": 1196.0,
        "right": 716.0,
        "difference": 480.0,
    },
    "ca-362-self-employment-ecps-58987-benefit": {
        "left": 179.0,
        "right": 78.99998474121094,
        "difference": 100.00001525878906,
    },
    "ca-362-self-employment-ecps-59016-benefit": {
        "left": 298.0,
        "right": 88.29998779296875,
        "difference": 209.70001220703125,
    },
    "ca-362-self-employment-ecps-59103-benefit": {
        "left": 154.0,
        "right": 23.84000015258789,
        "difference": 130.1599998474121,
    },
    "ca-362-self-employment-ecps-59173-benefit": {
        "left": 421.0,
        "right": 277.79998779296875,
        "difference": 143.20001220703125,
    },
    "ca-362-self-employment-ecps-60319-benefit": {
        "left": 298.0,
        "right": 94.29998779296875,
        "difference": 203.70001220703125,
    },
    "ca-362-self-employment-ecps-60859-benefit": {
        "left": 994.0,
        "right": 286.89996337890625,
        "difference": 707.1000366210938,
    },
    "ca-362-self-employment-tanf-ecps-56991-benefit": {
        "left": 1183.0,
        "right": 818.199951171875,
        "difference": 364.800048828125,
    },
    "ca-362-self-employment-tanf-ecps-57529-benefit": {
        "left": 994.0,
        "right": 561.699951171875,
        "difference": 432.300048828125,
    },
    "ca-362-self-employment-tanf-ecps-57845-benefit": {
        "left": 1183.0,
        "right": 688.9000244140625,
        "difference": 494.0999755859375,
    },
    "ca-362-self-employment-tanf-ecps-57891-benefit": {
        "left": 994.0,
        "right": 557.7999877929688,
        "difference": 436.20001220703125,
    },
    "ca-362-self-employment-tanf-ecps-60756-benefit": {
        "left": 603.0,
        "right": 289.3999938964844,
        "difference": 313.6000061035156,
    },
    "ca-362-self-employment-tanf-ecps-60777-benefit": {
        "left": 785.0,
        "right": 387.79998779296875,
        "difference": 397.20001220703125,
    },
    "ca-362-self-employment-tanf-ecps-60978-benefit": {
        "left": 329.0,
        "right": 113.0999755859375,
        "difference": 215.9000244140625,
    },
    "ca-362-self-employment-tanf-ecps-61251-benefit": {
        "left": 994.0,
        "right": 557.5,
        "difference": 436.5,
    },
    "ca-362-self-employment-tanf-ecps-61495-benefit": {
        "left": 785.0,
        "right": 434.8999938964844,
        "difference": 350.1000061035156,
    },
    "ca-362-tanf-ecps-60816-benefit": {
        "left": 361.0,
        "right": 283.89996337890625,
        "difference": 77.10003662109375,
    },
    "ca-362-tanf-ecps-62327-benefit": {
        "left": 239.0,
        "right": 23.84000015258789,
        "difference": 215.1599998474121,
    },
}

BENEFIT_CONCEPT = "us:statutes/7/2014/u#snap_benefit"
ELIGIBILITY_CONCEPT = "us:statutes/7/2014/o#snap_eligible"
EXPECTED_CONCEPTS = {BENEFIT_CONCEPT, ELIGIBILITY_CONCEPT}
EXPECTED_ENGINES = {
    "left": "axiom",
    "right": "policyengine",
    "versions": {
        "axiom_rules_engine": "0.1.0",
        "policyengine": "4.18.9",
        "policyengine_core": "3.30.3",
        "policyengine_us": "1.767.3",
    },
}
EXPECTED_ORACLE_PROVENANCE = {
    "name": "policyengine",
    "policyengine_core": "3.30.3",
    "policyengine_package": "policyengine==4.18.9",
    "policyengine_us": "1.767.3",
}
EXPECTED_RULESPECS = [
    {
        "repo": "TheAxiomFoundation/rulespec-us",
        "sha": "c13cdf7dda5948e7a86ff0c317872f93743a2084",
    }
]
MOVEMENT_THRESHOLD = 0.005

Identity = tuple[str, str, str]


class ReconciliationError(ValueError):
    """Raised when any pinned reconciliation invariant fails."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconciliationError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _path_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _identity(row: dict[str, Any]) -> Identity:
    try:
        values = (row["case_id"], row["concept"], row["kind"])
    except KeyError as exc:
        raise ReconciliationError(
            f"row is missing identity field {exc.args[0]!r}"
        ) from exc
    if not all(isinstance(value, str) and value for value in values):
        raise ReconciliationError(f"invalid disposition identity: {values!r}")
    return values


def _identity_record(entry: dict[str, Any]) -> dict[str, str]:
    case_id, concept, kind = _identity(entry)
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        raise ReconciliationError("disposition entry has no non-empty id")
    return {
        "id": entry_id,
        "case_id": case_id,
        "concept": concept,
        "kind": kind,
    }


def _identity_digest(entries: list[dict[str, Any]]) -> str:
    lines = [
        "\t".join(
            (
                record["id"],
                record["case_id"],
                record["concept"],
                record["kind"],
            )
        )
        for record in (_identity_record(entry) for entry in entries)
    ]
    payload = ("\n".join(sorted(lines)) + "\n").encode()
    return _sha256(payload)


def _json_rows_digest(rows: list[dict[str, Any]]) -> str:
    raw = (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return _sha256(raw)


def _pin(row: dict[str, Any]) -> dict[str, Any]:
    if "left" not in row or "right" not in row:
        raise ReconciliationError(
            f"{row.get('id') or row.get('case_id')}: pin lacks left/right"
        )
    result = {"left": row["left"], "right": row["right"]}
    difference = row.get("difference")
    if isinstance(difference, int | float) and not isinstance(difference, bool):
        result["difference"] = difference
    return result


def _pin_moved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    for field in set(before) | set(after):
        old = before.get(field)
        new = after.get(field)
        if isinstance(old, bool) or isinstance(new, bool):
            if old is not new:
                return True
        elif old is None or new is None:
            if old != new:
                return True
        elif abs(float(old) - float(new)) > MOVEMENT_THRESHOLD:
            return True
    return False


def _resolve_base_ref(base_ref: str) -> str:
    if not base_ref.strip() or base_ref.startswith("-"):
        raise ReconciliationError(f"invalid base ref {base_ref!r}")
    try:
        resolved = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{base_ref}^{{commit}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
        raise ReconciliationError(
            f"cannot resolve base ref {base_ref!r}: {detail or exc}"
        ) from exc
    if re.fullmatch(r"[0-9a-f]{40,64}", resolved) is None:
        raise ReconciliationError(
            f"git resolved {base_ref!r} ambiguously: {resolved!r}"
        )
    return resolved


def _git_show(commit: str, relative_path: str) -> bytes:
    try:
        return subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                f"{commit}:{relative_path}",
            ],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace").strip()
        raise ReconciliationError(
            f"cannot read {relative_path} from {commit}: {stderr or exc}"
        ) from exc


def _yaml_document(raw: bytes, label: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ReconciliationError(f"{label} is invalid YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise ReconciliationError(f"{label} root must be a mapping")
    return document


def _json_document(path: Path, label: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReconciliationError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ReconciliationError(f"{label} root must be an object")
    return document, _sha256(raw)


def _validate_disposition_document(
    document: dict[str, Any],
    *,
    label: str,
) -> list[dict[str, Any]]:
    _require(
        document.get("schema") == "axiom_oracles.dispositions.v1",
        f"{label} schema does not match",
    )
    _require(document.get("suite") == SUITE, f"{label} suite does not match")
    entries = document.get("entries")
    _require(isinstance(entries, list), f"{label} entries must be a list")
    assert isinstance(entries, list)
    ids: set[str] = set()
    for index, entry in enumerate(entries):
        _require(
            isinstance(entry, dict),
            f"{label} entries[{index}] must be a mapping",
        )
        assert isinstance(entry, dict)
        entry_id = entry.get("id")
        _require(
            isinstance(entry_id, str) and bool(entry_id),
            f"{label} entries[{index}] has invalid id",
        )
        assert isinstance(entry_id, str)
        _require(entry_id not in ids, f"{label} duplicates id {entry_id!r}")
        ids.add(entry_id)
        _require(
            isinstance(entry.get("concept"), str) and bool(entry["concept"]),
            f"{label} {entry_id} has invalid concept",
        )
        _require(
            isinstance(entry.get("kind"), str) and bool(entry["kind"]),
            f"{label} {entry_id} has invalid kind",
        )
        _require(
            isinstance(entry.get("disposition"), str),
            f"{label} {entry_id} has invalid disposition",
        )
    return entries


def _load_base_dispositions(
    base_ref: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    commit = _resolve_base_ref(base_ref)
    raw = _git_show(commit, BASE_DISPOSITIONS_RELATIVE_PATH)
    digest = _sha256(raw)
    _require(
        digest == BASE_DISPOSITIONS_SHA256,
        "literal base dispositions sha256 mismatch: "
        f"expected {BASE_DISPOSITIONS_SHA256}, got {digest}",
    )
    document = _yaml_document(raw, "literal base dispositions")
    entries = _validate_disposition_document(
        document,
        label="literal base dispositions",
    )
    issue_entries = [
        entry for entry in entries if str(entry["id"]).startswith("ca-362-")
    ]
    _require(
        len(entries) == 349,
        f"literal base must contain 349 total entries, got {len(entries)}",
    )
    _require(
        len(issue_entries) == EXPECTED_BASE_ROWS,
        "literal base must contain "
        f"{EXPECTED_BASE_ROWS} ca-362 rows, got {len(issue_entries)}",
    )
    base_digest = _identity_digest(issue_entries)
    _require(
        base_digest == EXPECTED_BASE_IDENTITY_DIGEST,
        "literal base ca-362 identity digest mismatch: "
        f"expected {EXPECTED_BASE_IDENTITY_DIGEST}, got {base_digest}",
    )
    return commit, document, issue_entries


def _load_current_dispositions() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    str,
]:
    raw = CURRENT_DISPOSITIONS_PATH.read_bytes()
    document = _yaml_document(raw, "current dispositions")
    entries = _validate_disposition_document(
        document,
        label="current dispositions",
    )
    return document, entries, _sha256(raw)


def _selected_case_ids(entry: dict[str, Any]) -> list[str]:
    direct = entry.get("case_id")
    selector = entry.get("case_selector")
    if direct is not None:
        _require(
            isinstance(direct, str) and bool(direct),
            f"{entry['id']}: direct case_id must be a non-empty string",
        )
        _require(selector is None, f"{entry['id']}: mixes direct and selector cases")
        return [direct]
    _require(
        isinstance(selector, dict),
        f"{entry['id']}: has neither direct case_id nor case_selector",
    )
    case_ids = selector.get("case_ids")
    _require(
        isinstance(case_ids, list) and bool(case_ids),
        f"{entry['id']}: case_selector.case_ids must be non-empty",
    )
    assert isinstance(case_ids, list)
    _require(
        all(isinstance(case_id, str) and case_id for case_id in case_ids),
        f"{entry['id']}: selector includes an invalid case id",
    )
    _require(
        len(set(case_ids)) == len(case_ids),
        f"{entry['id']}: selector duplicates a case id",
    )
    return case_ids


def _expanded_dispositions(
    entries: list[dict[str, Any]],
) -> dict[Identity, dict[str, Any]]:
    expanded: dict[Identity, dict[str, Any]] = {}
    for entry in entries:
        for case_id in _selected_case_ids(entry):
            key = (case_id, entry["concept"], entry["kind"])
            _require(
                key not in expanded,
                f"current dispositions cover identity {key!r} more than once",
            )
            expanded[key] = entry
    _require(
        len(expanded) == EXPECTED_EXPANDED_DISPOSITIONS,
        "current dispositions must expand to "
        f"{EXPECTED_EXPANDED_DISPOSITIONS} rows, got {len(expanded)}",
    )
    return expanded


def _expected_report_note(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "disposition": entry["disposition"],
        "id": entry["id"],
        "linked_issue": entry.get("linked_issue"),
    }


def _validate_report_provenance(report: dict[str, Any]) -> None:
    _require(
        report.get("engines") == EXPECTED_ENGINES,
        "current CA report engine/runtime stack drifted",
    )
    provenance = report.get("provenance")
    _require(
        isinstance(provenance, dict),
        "current CA report provenance is missing",
    )
    assert isinstance(provenance, dict)
    _require(
        provenance.get("oracle") == EXPECTED_ORACLE_PROVENANCE,
        "current CA report oracle provenance drifted",
    )
    _require(
        provenance.get("rulespecs") == EXPECTED_RULESPECS,
        "current CA report RuleSpec provenance drifted",
    )


def _load_and_validate_report(
    expanded: dict[Identity, dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[Identity, dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
]:
    report, digest = _json_document(CURRENT_REPORT_PATH, "current CA report")
    _require(
        report.get("schema_version") == "axiom.comparison_report.v2.1",
        "current CA report schema does not match",
    )
    _require(report.get("suite") == SUITE, "current CA report suite does not match")
    _validate_report_provenance(report)
    concepts = report.get("concepts")
    _require(isinstance(concepts, list), "current CA report concepts must be a list")
    assert isinstance(concepts, list)
    concept_ids = {
        concept.get("id") for concept in concepts if isinstance(concept, dict)
    }
    _require(
        concept_ids == EXPECTED_CONCEPTS and len(concepts) == 2,
        f"current CA report concept set drifted: {sorted(concept_ids)}",
    )

    cases = report.get("cases")
    case_count = report.get("case_count")
    _require(
        isinstance(case_count, int) and case_count > 0,
        "current CA report case_count must be positive",
    )
    _require(
        isinstance(cases, list) and len(cases) <= case_count,
        "current CA report cases must be a bounded list",
    )
    assert isinstance(cases, list)
    cases_by_id: dict[str, dict[str, Any]] = {}
    nested_by_identity: dict[Identity, dict[str, Any]] = {}
    for case in cases:
        _require(isinstance(case, dict), "current CA report has a non-object case")
        assert isinstance(case, dict)
        case_id = case.get("case_id")
        _require(
            isinstance(case_id, str) and bool(case_id),
            "current CA report case has invalid case_id",
        )
        assert isinstance(case_id, str)
        _require(
            case_id not in cases_by_id,
            f"current CA report duplicates case {case_id}",
        )
        cases_by_id[case_id] = case
        nested = case.get("mismatches") or []
        _require(
            isinstance(nested, list),
            f"current CA report case {case_id} mismatches must be a list",
        )
        for row in nested:
            _require(
                isinstance(row, dict),
                f"current CA report case {case_id} has a non-object mismatch",
            )
            assert isinstance(row, dict)
            nested_row = {"case_id": case_id, **row}
            key = _identity(nested_row)
            _require(
                key not in nested_by_identity,
                f"current CA report duplicates nested identity {key!r}",
            )
            nested_by_identity[key] = nested_row

    mismatches = report.get("mismatches")
    _require(
        isinstance(mismatches, list),
        "current CA report mismatches must be a list",
    )
    assert isinstance(mismatches, list)
    summary = report.get("summary")
    _require(isinstance(summary, dict), "current CA report summary is missing")
    assert isinstance(summary, dict)
    _require(
        len(mismatches) == EXPECTED_CURRENT_MISMATCHES,
        "current CA report must contain "
        f"{EXPECTED_CURRENT_MISMATCHES} mismatches, got {len(mismatches)}",
    )
    _require(
        summary.get("mismatch_count") == len(mismatches),
        "current CA report mismatch_count does not match stored rows",
    )
    _require(
        summary.get("stored_mismatch_example_count") == len(mismatches),
        "current CA report mismatch list is incomplete",
    )
    _require(
        summary.get("comparison_count") == case_count * len(concepts),
        "current CA report comparison_count drifted",
    )
    _require(
        summary.get("match_count") + summary.get("mismatch_count")
        == summary.get("comparison_count"),
        "current CA report match/mismatch totals do not close",
    )

    report_by_identity: dict[Identity, dict[str, Any]] = {}
    for row in mismatches:
        _require(
            isinstance(row, dict),
            "current CA report contains a non-object top-level mismatch",
        )
        assert isinstance(row, dict)
        key = _identity(row)
        _require(
            key not in report_by_identity,
            f"current CA report duplicates identity {key!r}",
        )
        report_by_identity[key] = row
        nested = nested_by_identity.get(key)
        _require(
            nested is not None,
            f"current CA report top-level identity {key!r} lacks nested evidence",
        )
        assert nested is not None
        _require(
            _pin(nested) == _pin(row),
            f"current CA report nested pin drift for {key!r}",
        )
        disposition_entry = expanded.get(key)
        expected_note = (
            _expected_report_note(disposition_entry)
            if disposition_entry is not None
            else None
        )
        _require(
            row.get("disposition") == expected_note,
            f"current CA report disposition drift for {key!r}",
        )
    _require(
        set(nested_by_identity) == set(report_by_identity),
        "current CA report nested/top-level mismatch identities differ",
    )
    mismatch_case_ids = {case_id for case_id, _concept, _kind in report_by_identity}
    _require(
        set(cases_by_id) == mismatch_case_ids,
        "current CA report case rows are not the exact mismatch-household set",
    )
    _require(
        set(expanded) <= set(report_by_identity),
        "current dispositions include a non-mismatch identity",
    )
    return report, report_by_identity, cases_by_id, digest


def _served_entry(entry: dict[str, Any]) -> dict[str, Any]:
    evidence = entry.get("evidence") or {}
    _require(
        isinstance(evidence, dict),
        f"{entry['id']}: evidence must be a mapping",
    )
    arithmetic = [
        {"expression": item.get("expression"), "equals": item.get("equals")}
        for item in evidence.get("arithmetic") or []
        if isinstance(item, dict) and item.get("expression") is not None
    ]
    mechanism = str(evidence.get("mechanism") or "").strip() or None
    return {
        "id": entry["id"],
        "concept": entry["concept"],
        "kind": entry["kind"],
        "disposition": entry["disposition"],
        "mechanism": mechanism,
        "cases": _selected_case_ids(entry),
        "arithmetic": arithmetic,
        "linked_issue": entry.get("linked_issue") or evidence.get("upstream_url"),
    }


def _validate_served_dispositions(
    source_document: dict[str, Any],
    entries: list[dict[str, Any]],
) -> str:
    served, digest = _json_document(
        SERVED_DISPOSITIONS_PATH,
        "served CA dispositions",
    )
    _require(
        served.get("suite") == SUITE,
        "served CA dispositions suite does not match",
    )
    _require(
        served.get("updated") == source_document.get("updated"),
        "served CA dispositions updated date drifted",
    )
    expected = [_served_entry(entry) for entry in entries]
    _require(
        served.get("entries") == expected,
        "served CA dispositions do not exactly match compacted source entries",
    )
    return digest


def _expected_compact_household(case: dict[str, Any]) -> dict[str, Any]:
    metadata = case.get("metadata") or {}
    _require(
        isinstance(metadata, dict),
        f"{case.get('case_id')}: report metadata must be an object",
    )
    summary = metadata.get("household_summary") or {}
    _require(
        isinstance(summary, dict),
        f"{case.get('case_id')}: household_summary must be an object",
    )
    ages = summary.get("ages") or []
    earned = summary.get("yearly_earned_income_per_person")
    _require(
        isinstance(ages, list),
        f"{case.get('case_id')}: household ages must be a list",
    )
    if earned is not None:
        _require(
            isinstance(earned, list),
            f"{case.get('case_id')}: household earned income must be a list",
        )
    return {
        "n": summary.get("household_size") or len(ages) or None,
        "e": round(sum(earned)) if earned else None,
        "a": ages,
    }


def _validate_compact_household_shape(
    household: Any,
    *,
    case_id: str,
) -> None:
    _require(
        isinstance(household, dict) and set(household) == {"n", "e", "a"},
        f"CA compact household summary shape drift for {case_id}",
    )
    assert isinstance(household, dict)
    _require(
        household["n"] is None
        or (
            isinstance(household["n"], int)
            and not isinstance(household["n"], bool)
            and household["n"] > 0
        ),
        f"CA compact household size is invalid for {case_id}",
    )
    _require(
        household["e"] is None
        or (
            isinstance(household["e"], int | float)
            and not isinstance(household["e"], bool)
        ),
        f"CA compact earned income is invalid for {case_id}",
    )
    _require(
        isinstance(household["a"], list)
        and all(
            isinstance(age, int | float) and not isinstance(age, bool)
            for age in household["a"]
        ),
        f"CA compact ages are invalid for {case_id}",
    )


def _expected_compact_mismatches(
    case: dict[str, Any],
    report_by_identity: dict[Identity, dict[str, Any]],
) -> list[dict[str, Any]]:
    case_id = case["case_id"]
    expected: list[dict[str, Any]] = []
    for nested in case.get("mismatches") or []:
        key = (case_id, nested["concept"], nested["kind"])
        canonical = report_by_identity[key]
        row = {
            "c": nested["concept"],
            "l": nested["left"],
            "x": nested["right"],
            "d": nested.get("difference"),
        }
        disposition = canonical.get("disposition")
        if disposition is not None:
            row["e"] = disposition["disposition"]
        expected.append(row)
    return expected


def _load_compact_rows(
    report: dict[str, Any],
    report_by_identity: dict[Identity, dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    index_path = COMPACT_DIR / "index.json"
    index, index_digest = _json_document(index_path, "CA compact index")
    declared_chunks = index.get("chunks")
    _require(
        isinstance(declared_chunks, int) and declared_chunks > 0,
        "CA compact index chunks must be a positive integer",
    )
    chunk_size = index.get("chunk_size")
    _require(
        isinstance(chunk_size, int) and chunk_size > 0,
        "CA compact index chunk_size must be positive",
    )
    expected_names = {f"chunk-{number}.json" for number in range(declared_chunks)}
    actual_paths = list(COMPACT_DIR.glob("chunk-*.json"))
    actual_names = {path.name for path in actual_paths}
    _require(
        actual_names == expected_names,
        "CA compact chunk set drifted: "
        f"missing={sorted(expected_names - actual_names)}, "
        f"extra={sorted(actual_names - expected_names)}",
    )

    rows: list[dict[str, Any]] = []
    chunk_receipts: list[dict[str, Any]] = []
    for number in range(declared_chunks):
        path = COMPACT_DIR / f"chunk-{number}.json"
        raw = path.read_bytes()
        try:
            chunk = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReconciliationError(
                f"CA compact {path.name} is invalid JSON: {exc}"
            ) from exc
        _require(
            isinstance(chunk, list),
            f"CA compact {path.name} must be an array",
        )
        assert isinstance(chunk, list)
        _require(
            len(chunk) <= chunk_size,
            f"CA compact {path.name} exceeds chunk_size",
        )
        rows.extend(chunk)
        chunk_receipts.append({"path": _relative(path), "sha256": _sha256(raw)})

    _validate_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
        index,
        rows,
    )
    receipt = {
        "index": {
            "path": _relative(index_path),
            "sha256": index_digest,
        },
        "chunks": chunk_receipts,
        "cases": len(rows),
        "mismatches": len(report_by_identity),
        "annotated": sum(
            row.get("disposition") is not None for row in report_by_identity.values()
        ),
    }
    return index, rows, receipt


def _validate_compact_rows(
    report: dict[str, Any],
    report_by_identity: dict[Identity, dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    index: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    _require(index.get("suite") == SUITE, "CA compact index suite drifted")
    _require(
        index.get("engines") == report.get("engines"),
        "CA compact index engines drifted",
    )
    _require(
        index.get("count") == len(rows) == report.get("case_count"),
        "CA compact case count does not match the canonical report",
    )
    _require(
        index.get("total_cases") == report.get("case_count"),
        "CA compact total_cases drifted",
    )
    _require(
        index.get("partial") is None,
        "CA compact artifacts unexpectedly use mismatch-only mode",
    )
    _require(
        "input_slots" not in index and "output_slots" not in index,
        "CA compact index is not the current id/r/h/m schema",
    )
    expected_concepts = sorted({row["concept"] for row in report_by_identity.values()})
    _require(
        index.get("mismatch_concepts") == expected_concepts,
        "CA compact mismatch_concepts drifted",
    )

    compact_by_id: dict[str, dict[str, Any]] = {}
    compact_mismatches: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        _require(isinstance(row, dict), "CA compact contains a non-object case")
        assert isinstance(row, dict)
        _require(
            set(row) == {"id", "r", "h", "m"},
            f"CA compact case {row.get('id')} is not exact id/r/h/m schema",
        )
        case_id = row.get("id")
        _require(
            isinstance(case_id, str) and bool(case_id),
            f"CA compact has invalid case id {case_id!r}",
        )
        assert isinstance(case_id, str)
        _require(
            case_id not in compact_by_id,
            f"CA compact duplicates case {case_id}",
        )
        compact_by_id[case_id] = row
        _validate_compact_household_shape(row["h"], case_id=case_id)
        canonical_case = cases_by_id.get(case_id)
        if canonical_case is None:
            _require(
                row["r"] == 100.0 and row["m"] == [],
                f"CA compact clean-case payload drift for {case_id}",
            )
        else:
            _require(
                row["r"] == canonical_case.get("match_rate"),
                f"CA compact match rate drift for {case_id}",
            )
            _require(
                row["h"] == _expected_compact_household(canonical_case),
                f"CA compact household summary drift for {case_id}",
            )
            expected_rows = _expected_compact_mismatches(
                canonical_case,
                report_by_identity,
            )
            _require(
                row["m"] == expected_rows,
                f"CA compact mismatch payload drift for {case_id}",
            )
        for mismatch in row["m"]:
            key = (case_id, mismatch["c"])
            _require(
                key not in compact_mismatches,
                f"CA compact duplicates mismatch {key!r}",
            )
            compact_mismatches[key] = mismatch

    _require(
        set(cases_by_id) <= set(compact_by_id),
        "CA compact artifacts omit a canonical mismatch household",
    )
    canonical_case_concepts = {
        (case_id, concept) for case_id, concept, _kind in report_by_identity
    }
    _require(
        set(compact_mismatches) == canonical_case_concepts,
        "CA compact mismatch identity set differs from canonical report",
    )


def _partition_base_entries(
    base_entries: list[dict[str, Any]],
    report_by_identity: dict[Identity, dict[str, Any]],
    current_issue_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    partitions: dict[str, list[dict[str, Any]]] = {
        "vanished": [],
        "current_but_dropped": [],
        "kept": [],
    }
    for entry in base_entries:
        entry_id = entry["id"]
        key = _identity(entry)
        current_entry = current_issue_by_id.get(entry_id)
        if current_entry is not None:
            _require(
                _identity(current_entry) == key,
                f"current entry {entry_id} changed identity",
            )
            _require(
                key in report_by_identity,
                f"current entry {entry_id} is not a current mismatch",
            )
            partitions["kept"].append(entry)
        elif key in report_by_identity:
            partitions["current_but_dropped"].append(entry)
        else:
            partitions["vanished"].append(entry)

    total = sum(len(entries) for entries in partitions.values())
    _require(
        total == EXPECTED_BASE_ROWS,
        f"partition closes to {total}, expected {EXPECTED_BASE_ROWS}",
    )
    for label, entries in partitions.items():
        expected_count = EXPECTED_PARTITION_COUNTS[label]
        _require(
            len(entries) == expected_count,
            f"{label} count is {len(entries)}, expected {expected_count}",
        )
        digest = _identity_digest(entries)
        expected_digest = EXPECTED_PARTITION_DIGESTS[label]
        _require(
            digest == expected_digest,
            f"{label} identity digest mismatch: "
            f"expected {expected_digest}, got {digest}",
        )
    return partitions


def _partition_receipt(
    partitions: dict[str, list[dict[str, Any]]],
    report_by_identity: dict[Identity, dict[str, Any]],
    current_issue_by_id: dict[str, dict[str, Any]],
    expanded: dict[Identity, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    movement: dict[str, list[dict[str, Any]]] = {
        "moved": [],
        "unchanged": [],
    }
    kept_requested_month_rows = []
    for entry in partitions["kept"]:
        entry_id = entry["id"]
        key = _identity(entry)
        current_row = report_by_identity[key]
        current_entry = current_issue_by_id[entry_id]
        current_pin = _pin(current_row)
        for field in (
            "disposition",
            "linked_issue",
            "expires_on_source_change",
        ):
            _require(
                current_entry.get(field) == entry.get(field),
                f"kept entry {entry_id} changed stable {field}",
            )
        _require(
            current_entry.get("pinned") == current_pin,
            f"kept entry {entry_id} pin differs from current report",
        )
        _require(
            expanded.get(key) == current_entry,
            f"kept entry {entry_id} is not the expanded source annotation",
        )
        label = (
            "moved"
            if _pin_moved(entry.get("pinned") or {}, current_pin)
            else "unchanged"
        )
        movement[label].append(entry)
        kept_requested_month_rows.append(
            {
                **_identity_record(entry),
                "requested_month_pin": current_pin,
            }
        )

    kept_requested_month_rows.sort(key=lambda row: row["id"])
    kept_requested_month_digest = _json_rows_digest(kept_requested_month_rows)
    _require(
        kept_requested_month_digest == EXPECTED_KEPT_REQUESTED_MONTH_ROWS_SHA256,
        "kept requested-month receipt digest mismatch: "
        f"expected {EXPECTED_KEPT_REQUESTED_MONTH_ROWS_SHA256}, "
        f"got {kept_requested_month_digest}",
    )

    for label, entries in movement.items():
        _require(
            len(entries) == EXPECTED_MOVEMENT_COUNTS[label],
            f"{label} retained count is {len(entries)}, "
            f"expected {EXPECTED_MOVEMENT_COUNTS[label]}",
        )
        digest = _identity_digest(entries)
        expected = EXPECTED_MOVEMENT_DIGESTS[label]
        _require(
            digest == expected,
            f"{label} retained identity digest mismatch: "
            f"expected {expected}, got {digest}",
        )

    for label in ("vanished", "current_but_dropped"):
        for entry in partitions[label]:
            key = _identity(entry)
            _require(
                key not in expanded,
                f"{label} entry {entry['id']} remains disposition-covered",
            )

    partition_output: dict[str, Any] = {"base_rows": EXPECTED_BASE_ROWS}
    for label, entries in partitions.items():
        partition_output[label] = {
            "count": len(entries),
            "identity_sha256": _identity_digest(entries),
            "ids": sorted(entry["id"] for entry in entries),
        }

    drifted_rows = []
    dropped_ids = {entry["id"] for entry in partitions["current_but_dropped"]}
    _require(
        dropped_ids == set(REQUESTED_MONTH_DRIFT_PINS),
        "requested-month drift receipt ids differ from the dropped partition",
    )
    for entry in sorted(
        partitions["current_but_dropped"],
        key=lambda item: item["id"],
    ):
        current = report_by_identity[_identity(entry)]
        literal_base_pin = _pin(entry.get("pinned") or {})
        requested_month_pin = REQUESTED_MONTH_DRIFT_PINS[entry["id"]]
        current_pin = _pin(current)
        _require(
            _pin_moved(requested_month_pin, current_pin),
            f"dropped entry {entry['id']} did not materially drift from "
            "requested-month evidence",
        )
        drifted_rows.append(
            {
                **_identity_record(entry),
                "literal_base_pin": literal_base_pin,
                "requested_month_pin": requested_month_pin,
                "current_pin": current_pin,
            }
        )
    drift_rows_digest = _json_rows_digest(drifted_rows)
    _require(
        drift_rows_digest == EXPECTED_DRIFT_ROWS_SHA256,
        "full drift-row receipt digest mismatch: "
        f"expected {EXPECTED_DRIFT_ROWS_SHA256}, got {drift_rows_digest}",
    )

    movement_output: dict[str, Any] = {}
    for label, entries in movement.items():
        movement_output[label] = {
            "count": len(entries),
            "identity_sha256": _identity_digest(entries),
            "ids": sorted(entry["id"] for entry in entries),
        }
    movement_output["requested_month_evidence"] = {
        "count": len(kept_requested_month_rows),
        "trace_sha256": REQUESTED_MONTH_TRACE_SHA256,
        "rows_sha256": kept_requested_month_digest,
    }
    return (
        {
            **partition_output,
            "drift_evidence_trace_sha256": REQUESTED_MONTH_TRACE_SHA256,
            "drifted_rows_sha256": drift_rows_digest,
            "drifted_rows": drifted_rows,
        },
        movement_output,
    )


def _validate_partition_compact_evidence(
    partitions: dict[str, list[dict[str, Any]]],
    compact_rows: list[dict[str, Any]],
) -> None:
    compact_by_id = {row["id"]: row for row in compact_rows}
    for label, entries in partitions.items():
        for entry in entries:
            case_id = entry["case_id"]
            compact = compact_by_id.get(case_id)
            _require(
                compact is not None,
                f"{label} base entry {entry['id']} is absent from compact cases",
            )
            assert compact is not None
            concept_rows = [row for row in compact["m"] if row["c"] == entry["concept"]]
            expected_count = 0 if label == "vanished" else 1
            _require(
                len(concept_rows) == expected_count,
                f"{label} base entry {entry['id']} has "
                f"{len(concept_rows)} compact rows for its concept; "
                f"expected {expected_count}",
            )


def check_reconciliation(base_ref: str) -> dict[str, Any]:
    """Validate the complete reconciliation and return a deterministic receipt."""

    base_commit, _base_document, base_entries = _load_base_dispositions(base_ref)
    (
        current_document,
        current_entries,
        current_dispositions_digest,
    ) = _load_current_dispositions()
    expanded = _expanded_dispositions(current_entries)
    (
        report,
        report_by_identity,
        cases_by_id,
        report_digest,
    ) = _load_and_validate_report(expanded)
    served_digest = _validate_served_dispositions(
        current_document,
        current_entries,
    )
    _index, compact_rows, compact_receipt = _load_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
    )

    current_issue_entries = [
        entry for entry in current_entries if str(entry["id"]).startswith("ca-362-")
    ]
    current_issue_by_id = {entry["id"]: entry for entry in current_issue_entries}
    _require(
        len(current_issue_by_id) == EXPECTED_PARTITION_COUNTS["kept"],
        "current source must contain exactly "
        f"{EXPECTED_PARTITION_COUNTS['kept']} ca-362 entries",
    )
    base_ids = {entry["id"] for entry in base_entries}
    _require(
        set(current_issue_by_id) <= base_ids,
        "current source contains a ca-362 id outside the literal base",
    )

    partitions = _partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
    )
    _validate_partition_compact_evidence(partitions, compact_rows)
    partition_receipt, movement_receipt = _partition_receipt(
        partitions,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )

    return {
        "schema": "axiom_oracles.ca_snap_423_reconciliation.v1",
        "suite": SUITE,
        "base": {
            "commit": base_commit,
            "path": BASE_DISPOSITIONS_RELATIVE_PATH,
            "sha256": BASE_DISPOSITIONS_SHA256,
            "identity_sha256": EXPECTED_BASE_IDENTITY_DIGEST,
        },
        "current": {
            "report": {
                "path": _relative(CURRENT_REPORT_PATH),
                "sha256": report_digest,
                "mismatches": len(report_by_identity),
            },
            "source_dispositions": {
                "path": _relative(CURRENT_DISPOSITIONS_PATH),
                "sha256": current_dispositions_digest,
                "entries": len(current_entries),
                "expanded_rows": len(expanded),
            },
            "served_dispositions": {
                "path": _relative(SERVED_DISPOSITIONS_PATH),
                "sha256": served_digest,
                "entries": len(current_entries),
            },
            "compact": compact_receipt,
        },
        "partition": partition_receipt,
        "retained_pin_movement": movement_receipt,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        required=True,
        help=(
            "Git ref containing the literal merged #423 disposition source. "
            "The ref is resolved to a commit before git-showing the pinned blob."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Audit committed artifacts without writing. The checker is always "
            "read-only; this flag makes the intended gate invocation explicit."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        receipt = check_reconciliation(args.base_ref)
    except (OSError, ReconciliationError) as exc:
        print(f"CA SNAP #423 reconciliation FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
