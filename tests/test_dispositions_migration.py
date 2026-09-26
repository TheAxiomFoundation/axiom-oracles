"""Regression fixtures computed independently with origin/main's merge and data.

The baseline is not inferred from the new merge or from already annotated rows.
See docs/taxsim-disposition-migration-audit.md for the reconstruction procedure.
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from axiom_oracles.comparison.dispositions import (
    apply_dispositions,
    assignment_digest,
    load_dispositions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "docs/taxsim-disposition-migration-baseline.json"


@pytest.fixture(scope="module")
def baseline():
    return json.loads(BASELINE_PATH.read_text())


@pytest.fixture(scope="module")
def merged_reports(baseline):
    documents = {}
    merged = {}

    def merge(record):
        path = record["path"]
        if path in merged:
            return merged[path]
        report = json.loads((REPO_ROOT / path).read_text())
        source = record.get("source_report")
        if source:
            source_record = next(
                row for row in baseline["reports"] if row["path"] == source["path"]
            )
            full = merge(source_record)
            assert len(full["mismatches"]) == report["summary"]["mismatch_count"]
            assert assignment_digest(full) == record["full_assignment_digest"]
            assert hashlib.sha256(
                (REPO_ROOT / source["path"]).read_bytes()
            ).hexdigest() == source["sha256"]
            annotations = {
                (row["case_id"], row["concept"]): row.get("disposition")
                for row in full["mismatches"]
            }
            for row in report["mismatches"]:
                # The slim report is annotated from its complete population;
                # its sample alone cannot satisfy the population binding.
                assert row.get("disposition") == annotations[
                    (row["case_id"], row["concept"])
                ]
            merged[path] = report
            return report
        document_path = record["dispositions_file"]
        if document_path not in documents:
            documents[document_path] = (
                load_dispositions(REPO_ROOT / document_path, repo_root=REPO_ROOT)
                if document_path
                else None
            )
        # Force a fresh assignment. Preserving old row annotations accidentally
        # must not satisfy this regression check.
        for row in report["mismatches"]:
            row.pop("disposition", None)
        result = apply_dispositions(report, documents[document_path])
        merged[path] = result
        return result

    for record in baseline["reports"]:
        merge(record)
    return merged


def test_every_checked_in_taxsim_report_preserves_original_assignments(
    baseline, merged_reports
):
    assert len(baseline["reports"]) == 45
    for record in baseline["reports"]:
        assert record["before_assignment_digest"] == record["after_assignment_digest"]
        merged = merged_reports[record["path"]]
        assert len(merged["mismatches"]) == record["stored_rows"]
        assert assignment_digest(merged) == record["before_assignment_digest"], record[
            "path"
        ]
        if record["dispositions_file"]:
            block = merged["summary"]["dispositioned"]
            assert block["expired_entries"] == []
            assert block["orphaned_entries"] == []
            assert block["unexplained_count"] == 0


def test_migration_fixture_detects_lost_or_changed_assignment(baseline, merged_reports):
    record = next(
        row for row in baseline["reports"] if row["suite"] == "co-state-income-tax-taxsim"
    )
    report = merged_reports[record["path"]]
    assert report["mismatches"][0].get("disposition")
    changed = copy.deepcopy(report)
    changed["mismatches"][0].pop("disposition")
    assert assignment_digest(changed) != record["before_assignment_digest"]
    changed = copy.deepcopy(report)
    changed["mismatches"][0]["disposition"]["id"] = "wrong-entry"
    assert assignment_digest(changed) != record["before_assignment_digest"]


def test_taxsim_case_chunks_are_unchanged_by_migration(baseline):
    assert len(baseline["unchanged_case_artifacts"]) == 8
    for record in baseline["unchanged_case_artifacts"]:
        assert hashlib.sha256(
            (REPO_ROOT / record["path"]).read_bytes()
        ).hexdigest() == record["sha256"], record["path"]
