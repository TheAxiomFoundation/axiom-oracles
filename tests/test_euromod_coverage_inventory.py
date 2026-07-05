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
        coverage["coverage_summary"]["full_household_disposable_income_parity"] is False
    )
    assert coverage["coverage_summary"]["rule_percentage"] is None
    assert coverage["coverage_summary"]["current_oracle_output_targets"] == 22
    assert coverage["coverage_summary"]["live_verified_oracle_output_targets"] == 16
    assert coverage["coverage_summary"]["prepared_oracle_output_targets"] == 0
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
        outputs["tscer_s"]["status"]
        == "live_oracle_compared_with_known_2025_employer_parameter_residual"
    )
    assert (
        outputs["tin_s"]["status"]
        == "live_oracle_compared_worker_pilot_with_known_article_289ter1_residual"
    )
    assert (
        outputs["bsa_s"]["status"]
        == "live_oracle_verified_isolated_and_dependent_family_no_resources"
    )
    assert (
        outputs["bsaoa_s"]["status"]
        == "live_oracle_verified_isolated_no_resources_with_policy_switch_override"
    )
    assert (
        outputs["tscse_s"]["status"]
        == "live_oracle_verified_main_activity_with_known_secondary_and_post_pension_euromod_issue"
    )
    assert (
        outputs["tsceesp_s"]["status"]
        == "live_oracle_verified_single_worker_low_mid_with_known_euromod_article_108_schedule_issue"
    )
    assert (
        outputs["tci_s"]["status"]
        == "live_oracle_verified_ordinary_and_reduced_adult_flanders"
    )
    assert (
        outputs["bwkrg_s"]["status"]
        == "live_oracle_compared_with_known_2025_jobbonus_parameter_residual"
    )
    assert (
        outputs["khooo_s"]["status"]
        == "live_oracle_compared_with_known_cadastral_income_rounding_residual"
    )
    assert (
        outputs["tprhm_s"]["status"]
        == "live_oracle_verified_high_cadastral_income_no_reductions"
    )
    assert (
        outputs["bchba_s"]["status"]
        == "live_oracle_verified_brussels_flanders_wallonia_with_known_dg_birth_allowance_issue"
    )
    assert (
        outputs["bch_s"]["status"]
        == "live_oracle_verified_one_child_base_and_brussels_same_age_household_with_known_dg_and_pre_2020_wallonia_issues"
    )
    assert (
        outputs["bmact_s"]["status"]
        == "live_oracle_verified_employed_under_cap_mother_newborn_with_pbe_switch"
    )
    assert (
        outputs["bpact_s"]["status"]
        == "live_oracle_verified_under_cap_father_newborn_with_pbe_switch"
    )
    assert outputs["bch_s"]["additional_rulespec_outputs"] == [
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_brussels_2025_annual_amount_with_social_supplement",
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_brussels_2025_same_age_children_annual_household_amount_with_social_supplement",
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_wallonia_2025_annual_amount_with_social_supplement",
    ]
    assert outputs["ils_tax"]["status"] == "live_oracle_verified_worker_pit_pilot"
    assert outputs["ils_ben"]["status"] == "live_oracle_verified_family_benefit_pilot"
    assert (
        outputs["ils_dispy"]["status"]
        == "live_oracle_verified_worker_pit_sic_pilot"
    )


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
    assert {
        entry["id"] for entry in issues["entries"] if entry["jurisdiction"] == "BE"
    } >= {
        "euromod-be-2025-employer-ssc-company-closing-fund-rates",
        "euromod-be-2025-pit-work-bonus-credit-uncapped-ab",
        "euromod-be-2025-self-employed-main-rate",
        "euromod-be-2025-self-employed-threshold-allowance",
        "euromod-be-2025-special-contribution-article-108-schedule",
        "euromod-be-2025-wallonia-pre-2020-child-benefit-supplement-cumulation",
        "euromod-be-2025-dg-child-benefit-zero",
        "euromod-be-2025-dg-birth-allowance-zero",
        "euromod-be-2025-flemish-jobbonus-stale-parameters",
        "euromod-be-2025-cadastral-income-rounding",
    }
    wallonia_issue = next(
        entry
        for entry in issues["entries"]
        if entry["id"]
        == "euromod-be-2025-wallonia-pre-2020-child-benefit-supplement-cumulation"
    )
    assert (
        wallonia_issue["statutory_evidence"]["indexed_2025_rulespec_module"]
        == "be/statutes/family_benefits/child_benefit_base_2025.yaml"
    )
    assert (
        wallonia_issue["statutory_evidence"]["unindexed_statutory_rulespec_module"]
        == "be-wal/statutes/family_benefits/amounts.yaml"
    )
    assert all(
        "2025-indexed Article 13" in case["note"]
        for case in wallonia_issue["observed_with"]["cases"]
    )
