"""Regression gates for Belgium's documentary-only RuleSpec boundary."""

from __future__ import annotations

import json
from pathlib import Path

from axiom_oracles.suites import available_suites, load_suite


ROOT = Path(__file__).resolve().parents[1]

DELETED_MODULE_PREFIXES = frozenset(
    {
        "be:policies/euromod_benefit_income_list",
        "be:policies/euromod_disposable_income_list",
        "be:policies/euromod_tax_income_list",
        "be:regulations/unemployment/pilot_oracle_pipeline",
        "be:statutes/family_benefits/regional_routing",
        "be:statutes/gift_tax/regional_routing",
        "be:statutes/inheritance_tax/regional_routing",
        "be:statutes/education/study_allowance_routing",
        "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline",
        "be:statutes/income_tax/individual/couple_pit_oracle_pipeline",
        "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline",
        "be:statutes/income_tax/individual/self_employed_oracle_pipeline",
        "be:statutes/property_tax/gross_withholding_and_supplied_centimes",
        "be:statutes/property_tax/regional_routing",
        "be:statutes/vehicle_tax/regional_routing",
    }
)
DELETED_MODULE_PATHS = frozenset(
    f"{prefix.replace(':', '/', 1)}.yaml" for prefix in DELETED_MODULE_PREFIXES
)

REMOVED_OUTPUT_CONCEPTS = frozenset(
    {
        "be:regulations/social_security/workers/work_bonus#belgium_worker_work_bonus_full_year_equal_monthly_total_reduction",
        "be:regulations/unemployment/payable_amount#belgium_unemployment_ordinary_daily_amount_before_minimum",
        "be:regulations/unemployment/payable_amount#belgium_unemployment_ordinary_monthly_payable_amount",
        "be:regulations/unemployment/payable_amount#belgium_unemployment_payable_amount_source_components",
        "be:regulations/unemployment/payable_amount#belgium_unemployment_temporary_monthly_payable_amount",
        "be:statutes/family_benefits/birth_allowance#belgium_family_benefits_birth_allowance_amount",
        "be:statutes/family_benefits/child_benefit_base_2025#belgium_child_benefit_brussels_2025_annual_amount_with_social_supplement",
        "be:statutes/family_benefits/child_benefit_base_2025#belgium_child_benefit_brussels_2025_same_age_children_annual_household_amount_with_social_supplement",
        "be:statutes/family_benefits/child_benefit_base_2025#belgium_child_benefit_wallonia_2025_annual_amount_with_social_supplement",
        "be:statutes/family_benefits/child_benefit_base_2025#belgium_family_benefits_child_benefit_base_2025_annual_amount",
        "be:statutes/social_security/non_labour_income_contributions#belgium_pensioner_total_annual_health_and_solidarity_withholding",
        "be:statutes/property_tax/gross_withholding_and_supplied_centimes#belgium_immovable_withholding_gross_tax_after_supplied_local_centimes",
    }
)

RETIRED_SUITES = frozenset(
    {
        "be-worker-pit",
        "be-work-bonus-credit",
        "be-marital-quotient",
        "be-pensioner-pit",
        "be-replacement-income-pit",
        "be-self-employment-pit",
        "be-worker-tax-income-list",
        "be-worker-disposable-income-list",
        "be-family-child-benefit-income-list",
        "be-unemployment",
        "be-study-allowance",
        "be-worker-ssc",
        "be-family-birth-allowance",
        "be-family-child-benefit-base",
        "be-family-child-benefit-social-supplement",
        "be-family-child-benefit-brussels-same-age-household",
        "be-family-child-benefit-wallonia-social-supplement",
        "be-property-tax",
        "be-pensioner-contributions",
    }
)

ACTIVE_ROOTS = (
    ROOT / "axiom_oracles",
    ROOT / "comparisons",
    ROOT / "conformance",
    ROOT / "dispositions",
    ROOT / "grids",
    ROOT / "dashboard" / "src",
    ROOT / "docs",
)
ACTIVE_SUFFIXES = frozenset({".json", ".js", ".md", ".py", ".yaml", ".yml"})
HISTORICAL_ROOT = (
    ROOT
    / "dashboard"
    / "public"
    / "data"
    / "historical"
    / "retired-documentary-boundary"
)


def _active_surface_files() -> list[Path]:
    files: list[Path] = [ROOT / "README.md"]
    for root in ACTIVE_ROOTS:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in ACTIVE_SUFFIXES
        )

    dashboard_data = ROOT / "dashboard" / "public" / "data"
    files.extend(dashboard_data.glob("*.json"))
    files.extend((dashboard_data / "dispositions").rglob("*.json"))
    files.extend((dashboard_data / "cases").rglob("*.json"))
    return sorted(set(files))


def test_active_surfaces_contain_no_deleted_be_modules_or_outputs() -> None:
    violations: list[str] = []
    for path in _active_surface_files():
        text = path.read_text()
        for prefix in DELETED_MODULE_PREFIXES:
            if prefix in text:
                violations.append(f"{path.relative_to(ROOT)}: {prefix}")
        for module_path in DELETED_MODULE_PATHS:
            if module_path in text:
                violations.append(f"{path.relative_to(ROOT)}: {module_path}")
        for concept in REMOVED_OUTPUT_CONCEPTS:
            if concept in text:
                violations.append(f"{path.relative_to(ROOT)}: {concept}")

    assert not violations, "deleted Belgium modules/outputs remain active:\n" + (
        "\n".join(violations)
    )


def test_active_be_suite_registry_contains_no_retired_modules_or_suites() -> None:
    registered = set(available_suites())
    assert RETIRED_SUITES.isdisjoint(registered)

    for suite in sorted(registered):
        if not suite.startswith("be-"):
            continue
        serialized = json.dumps(
            [
                {
                    "outputs": case.outputs,
                    "metadata": case.metadata,
                }
                for case in load_suite(suite)
            ],
            sort_keys=True,
        )
        assert all(prefix not in serialized for prefix in DELETED_MODULE_PREFIXES), suite
        assert all(concept not in serialized for concept in REMOVED_OUTPUT_CONCEPTS), (
            suite
        )


def test_retired_suites_have_no_current_config_or_dashboard_report() -> None:
    manifest = json.loads(
        (ROOT / "dashboard" / "public" / "data" / "manifest.json").read_text()
    )
    current_report_suites = {
        json.loads(path.read_text()).get("suite")
        for path in (ROOT / "dashboard" / "public" / "data").glob("*.json")
    }

    assert RETIRED_SUITES.isdisjoint(current_report_suites)
    assert all(
        not (ROOT / "comparisons" / f"{suite}.yaml").exists()
        and not (ROOT / "dispositions" / f"{suite}.yaml").exists()
        for suite in RETIRED_SUITES
    )
    assert all(
        not any(suite in filename for suite in RETIRED_SUITES)
        for filename in manifest["reports"]
    )
    assert (HISTORICAL_ROOT / "README.md").is_file()
    assert any((HISTORICAL_ROOT / "report-artifacts").glob("*.json"))


def test_historical_archive_has_expected_byte_preserved_artifact_inventory() -> None:
    files = [path for path in HISTORICAL_ROOT.rglob("*") if path.is_file()]
    assert len(files) == 37
    assert len(list((HISTORICAL_ROOT / "report-artifacts").glob("*.json"))) == 21
    assert len(list((HISTORICAL_ROOT / "dispositions").glob("*.json"))) == 10
    assert len(list((HISTORICAL_ROOT / "cases").rglob("*.json"))) == 4
