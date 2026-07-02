from __future__ import annotations

import json
from pathlib import Path

from axiom_oracles.euromod_coverage import (
    load_belgium_coverage,
    load_euromod_issues,
)


ROOT = Path(__file__).resolve().parents[1]


def test_belgium_euromod_coverage_inventory_is_packaged() -> None:
    coverage = load_belgium_coverage()

    assert coverage["jurisdiction"] == "be"
    assert coverage["oracle_configuration"]["system"] == "BE_2025"
    assert coverage["denominator"]["policy_count"] == 43
    assert coverage["denominator"]["function_count"] == 1171
    assert coverage["denominator"]["parameter_count"] == 8211


def test_belgium_euromod_inventory_does_not_claim_full_parity() -> None:
    coverage = load_belgium_coverage()
    outputs = {
        output["euromod_variable"]: output
        for output in coverage["oracle_output_coverage"]
    }

    assert (
        coverage["coverage_summary"]["full_household_disposable_income_parity"]
        is False
    )
    assert coverage["coverage_summary"]["rule_percentage"] is None
    assert outputs["tscee_s"]["status"] == (
        "live_oracle_verified_gross_regular_worker_slice"
    )
    assert outputs["tsceerd_s"]["status"] == (
        "live_oracle_compared_with_known_2025_timing_residual"
    )
    assert outputs["tscee_net_s"]["status"] == (
        "live_oracle_compared_with_known_2025_timing_residual"
    )
    assert (
        outputs["tin_s"]["status"]
        == "live_oracle_compared_worker_pilot_not_full_household_parity"
    )
    assert outputs["ils_dispy"]["status"] == "not_mapped"


def test_dashboard_static_copy_matches_packaged_inventory() -> None:
    packaged = load_belgium_coverage()
    dashboard = json.loads(
        (ROOT / "dashboard/public/data/euromod-be-coverage.json").read_text()
    )

    assert dashboard == packaged


def test_euromod_issue_ledger_is_packaged_and_mirrored() -> None:
    issues = load_euromod_issues()
    dashboard = json.loads(
        (ROOT / "dashboard/public/data/euromod-issues.json").read_text()
    )

    assert dashboard == issues
    assert issues["entries"][0]["id"] == (
        "jrc-euromod-4-be-training-data-income-list-prep"
    )
    assert issues["entries"][0]["upstream_url"].endswith("/issues/4")
    assert issues["entries"][0]["counts_as_axiom_gap"] is False
