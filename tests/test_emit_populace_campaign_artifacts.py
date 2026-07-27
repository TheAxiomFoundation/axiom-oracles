import json
from pathlib import Path

import pytest
import yaml

from scripts.emit_populace_campaign_artifacts import (
    RETIRED_MANIFEST_REPORTS,
    reconcile_manifest_reports,
    project_state,
)


DASHBOARD_DATA = Path(__file__).resolve().parents[1] / "dashboard/public/data"
POPULACE_SUITE_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "comparisons/state-income-tax-populace.yaml"
)


def _campaign() -> dict:
    return {
        "generated_at": "2026-07-26T12:00:00Z",
        "run_kind": "manual",
        "dataset_identity": {
            "source": "pinned",
            "revision": "populace-us-test",
            "sha256": "3" * 12,
            "built_with": "1.729.0",
            "country": "us",
        },
        "runtime_provenance": {
            "rulespec": {
                "repository": "TheAxiomFoundation/rulespec-us",
                "commit": "1" * 40,
                "working_tree": "clean",
            },
            "axiom_engine": {
                "repository": "TheAxiomFoundation/axiom-rules-engine",
                "commit": "2" * 40,
                "executable_sha256": "4" * 64,
                "working_tree": "clean",
            },
            "packages": {
                "policyengine": "4.18.9",
                "policyengine-us": "1.752.2",
            },
        },
    }


def test_manifest_reconciliation_retires_only_alabama_taxsim_ghost(tmp_path):
    published = tmp_path / "published.json"
    published.write_text("{}\n")
    (retired_report,) = RETIRED_MANIFEST_REPORTS

    assert reconcile_manifest_reports(
        ["published.json", retired_report],
        data_dir=tmp_path,
        required_reports=frozenset({"published.json"}),
    ) == ["published.json"]


def test_manifest_reconciliation_rejects_missing_required_populace_report(
    tmp_path,
):
    required = "axiom-policyengine-al-income-tax-populace.json"

    with pytest.raises(
        ValueError,
        match="missing required configured Populace report",
    ):
        reconcile_manifest_reports(
            [],
            data_dir=tmp_path,
            required_reports=frozenset({required}),
        )


def test_manifest_reconciliation_rejects_unpublished_nonretired_report(
    tmp_path,
):
    missing = "axiom-policyengine-ct-income-tax-populace.json"

    with pytest.raises(ValueError, match="unpublished dashboard report"):
        reconcile_manifest_reports([missing], data_dir=tmp_path)


def test_every_dashboard_manifest_target_exists():
    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    missing = [
        name
        for name in manifest["reports"]
        if not (DASHBOARD_DATA / name).is_file()
    ]

    assert missing == []


def test_configured_populace_reports_are_published_and_manifested():
    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    config = yaml.safe_load(POPULACE_SUITE_CONFIG.read_text())
    required = {suite["report"] for suite in config["suites"]}

    assert required <= set(manifest["reports"])
    assert all((DASHBOARD_DATA / name).is_file() for name in required)


def test_alabama_dashboard_description_names_narrow_schedule():
    output = (
        "us-al:policies/income_tax/"
        "2026_section_40_18_5_schedule_before_credits"
        "#al_pit_2026_section_40_18_5_schedule_before_credits"
    )
    report = project_state(
        "AL",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "al_income_tax_before_non_refundable_credits"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 40-18-5 schedule before credits" in description
    assert "caller-supplied completed Alabama taxable income" in description
    assert "joint-or-surviving-spouse schedule classifier" in description
    assert "liability" not in description.lower()


def test_connecticut_dashboard_description_names_narrow_component():
    output = (
        "us-ct:policies/income_tax/"
        "2026_resident_ordinary_tax_before_personal_credit"
        "#ct_pit_2026_resident_ordinary_tax_before_personal_credit"
    )
    report = project_state(
        "CT",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "ct_resident_ordinary_tax_before_personal_credit_derived"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "ordinary section 12-700 tax before the personal credit" in description
    assert description != (
        "State income tax liability over every routed tax unit in the "
        "pinned US Populace"
    )


def test_georgia_dashboard_description_names_narrow_component():
    output = (
        "us-ga:policies/income_tax/"
        "2026_annual_tax_before_nonrefundable_credits"
        "#ga_pit_2026_annual_tax_before_nonrefundable_credits"
    )
    report = project_state(
        "GA",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "ga_income_tax_before_non_refundable_credits",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 48-7-20 annual tax before nonrefundable credits" in description
    assert "caller-supplied completed Georgia taxable net income" in description
    assert "liability" not in description.lower()


def test_mississippi_dashboard_description_names_person_schedule():
    output = (
        "us-ms:policies/income_tax/2026_section_27_7_5_schedule"
        "#ms_pit_2026_section_27_7_5_schedule_tax"
    )
    report = project_state(
        "MS",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "ms_income_tax_before_credits_joint",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 27-7-5 Person-grain" in description
    assert "caller-supplied completed Mississippi taxable income" in description
    assert "only for Populace accounting" in description
    assert "liability" not in description.lower()


def test_utah_projection_carries_branch_exercise_diagnostics():
    output = (
        "us-ut:policies/income_tax/"
        "2026_full_year_resident_before_credit_schedule"
        "#ut_pit_2026_resident_income_tax_before_credits"
    )
    campaign = _campaign()
    campaign["projection_diagnostics"] = {
        "UT": {
            "compared_tax_unit_count": 1251,
            "exempt_count": 196,
            "nonexempt_count": 1055,
            "negative_taxable_income_count": 12,
        }
    }
    report = project_state(
        "UT",
        {
            "compared_count": 1251,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "ut_resident_income_tax_before_credits_derived"
            ),
        },
        campaign,
        "campaign.json",
    )

    assert report["provenance"]["branch_diagnostics"] == {
        "compared_tax_unit_count": 1251,
        "exempt_count": 196,
        "nonexempt_count": 1055,
        "negative_taxable_income_count": 12,
    }


def test_projected_report_carries_standard_rulespec_provenance():
    report = project_state(
        "CT",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": "us-ct:policies/income_tax/example#output",
            "program": "us-ct:policies/income_tax/example",
            "policyengine_target": "ct_example",
        },
        _campaign(),
        "campaign.json",
    )

    provenance = report["provenance"]
    assert provenance["schema"] == "axiom_oracles.provenance.v1"
    assert provenance["generated_at"] == "2026-07-26T12:00:00Z"
    assert provenance["run_kind"] == "manual"
    assert provenance["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": "1" * 40,
        }
    ]


@pytest.mark.parametrize("missing", ["generated_at", "run_kind"])
def test_projector_fails_closed_on_missing_campaign_run_provenance(missing):
    campaign = _campaign()
    campaign.pop(missing)
    with pytest.raises(ValueError, match=missing):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("rulespec", "working_tree"),
        ("axiom_engine", "executable_sha256"),
        ("axiom_engine", "working_tree"),
        ("packages", "policyengine-us"),
    ],
)
def test_projector_fails_closed_on_incomplete_runtime_identity(section, field):
    campaign = _campaign()
    campaign["runtime_provenance"][section].pop(field)
    with pytest.raises(ValueError, match=field):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


@pytest.mark.parametrize(
    ("container", "section", "field"),
    [
        ("runtime_provenance", "rulespec", "commit"),
        ("runtime_provenance", "axiom_engine", "executable_sha256"),
        ("runtime_provenance", "packages", "policyengine-us"),
        ("dataset_identity", None, "sha256"),
    ],
)
def test_projector_rejects_non_string_identity(container, section, field):
    campaign = _campaign()
    identity = campaign[container]
    if section is not None:
        identity = identity[section]
    identity[field] = True

    with pytest.raises(ValueError, match=field):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


@pytest.mark.parametrize("field", ["source", "built_with", "country"])
def test_projector_fails_closed_on_incomplete_dataset_identity(field):
    campaign = _campaign()
    campaign["dataset_identity"].pop(field)
    with pytest.raises(ValueError, match=field):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


def test_reprojection_is_deterministic_and_preserves_campaign_time():
    entry = {
        "compared_count": 1,
        "mismatch_count": 0,
        "output": "us-ct:policies/income_tax/example#output",
        "program": "us-ct:policies/income_tax/example",
        "policyengine_target": "ct_example",
    }
    first = project_state("CT", entry, _campaign(), "campaign.json")
    second = project_state("CT", entry, _campaign(), "campaign.json")

    assert first == second
    assert first["provenance"]["generated_at"] == "2026-07-26T12:00:00Z"
