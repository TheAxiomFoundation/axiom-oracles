import json
from pathlib import Path

import pytest
import yaml

import scripts.emit_populace_campaign_artifacts as emitter
from scripts.emit_populace_campaign_artifacts import (
    RETIRED_MANIFEST_REPORTS,
    reconcile_manifest_reports,
    project_state,
)


DASHBOARD_DATA = Path(__file__).resolve().parents[1] / "dashboard/public/data"
REPO_ROOT = Path(__file__).resolve().parents[1]
POPULACE_SUITE_CONFIG = (
    REPO_ROOT / "comparisons/state-income-tax-populace.yaml"
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


def test_dc_dashboard_description_names_joint_method_schedule():
    output = (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits"
        "#dc_pit_2026_section_47_1806_03_schedule_before_credits"
    )
    report = project_state(
        "DC",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "dc_income_tax_before_credits_joint",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 47-1806.03(a)(11)" in description
    assert "joint-method schedule before credits" in description
    assert "caller-supplied completed joint-method District taxable income" in (
        description
    )
    assert "liability" not in description.lower()


def test_dc_case_emitter_preserves_all_1362_routed_units(
    tmp_path,
    monkeypatch,
):
    output = (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits"
        "#dc_pit_2026_section_47_1806_03_schedule_before_credits"
    )
    cases = [
        {
            "tax_unit_id": tax_unit_id,
            "axiom": float(tax_unit_id),
            "policyengine": float(tax_unit_id),
            "matched": True,
        }
        for tax_unit_id in range(1, 1_363)
    ]
    monkeypatch.setattr(emitter, "CASES_ROOT", tmp_path)

    assert emitter.emit_case_chunks(
        "DC",
        {"output": output, "cases": cases},
    ) == "dc-income-tax-populace: 1362 cases in 3 chunks"

    suite_root = tmp_path / "dc-income-tax-populace"
    index = json.loads((suite_root / "index.json").read_text())
    chunks = [
        json.loads((suite_root / f"chunk-{number}.json").read_text())
        for number in range(index["chunks"])
    ]
    assert index["count"] == index["total_cases"] == 1_362
    assert [len(chunk) for chunk in chunks] == [500, 500, 362]
    projected = [case for chunk in chunks for case in chunk]
    assert [case["id"] for case in projected] == list(range(1, 1_363))
    assert all(case["r"] == 1.0 for case in projected)


def test_kansas_dashboard_description_names_k40es_schedule():
    output = (
        "us-ks:policies/income_tax/2026_k40es_schedule_before_credits"
        "#ks_pit_2026_k40es_schedule_before_credits"
    )
    report = project_state(
        "KS",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "ks_k40es_schedule_before_credits_reviewed"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "tax-year-2026 K-40ES" in description
    assert "joint or all-other-filer schedule before credits" in description
    assert "caller-supplied completed Kansas taxable income" in description
    assert "liability" not in description.lower()


def test_committed_kansas_populace_evidence_is_canonical_and_complete():
    rulespec_sha = "a0a3032ca9e25b6d7d6d6b92be3f9609d796d143"
    engine_sha = "ffd8213271947b0189a9dd61a055c1e0e78908a0"
    executable_sha = (
        "c7eef635dadca73b51d4012fcc2f12c2f08dd82f9d505ba5228f127779a3a4e2"
    )
    concept = (
        "us-ks:policies/income_tax/2026_k40es_schedule_before_credits"
        "#ks_pit_2026_k40es_schedule_before_credits"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-ks-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-ks-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/ks-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["KS"]
    cases = state["cases"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert state["compared_count"] == 989
    assert state["mismatch_count"] == 0
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert sum(case["policyengine"] == 0 for case in cases) == 158
    assert sum(case["policyengine"] > 0 for case in cases) == 831
    assert all(case["matched"] for case in cases)

    runtime = campaign["runtime_provenance"]
    assert runtime["rulespec"]["commit"] == rulespec_sha
    assert runtime["rulespec"]["working_tree"] == "clean"
    assert runtime["axiom_engine"]["commit"] == engine_sha
    assert runtime["axiom_engine"]["executable_sha256"] == executable_sha
    assert runtime["axiom_engine"]["working_tree"] == "clean"

    report = json.loads(report_path.read_text())
    assert report["suite"] == "ks-income-tax-populace"
    assert report["case_count"] == 989
    assert report["summary"] == {
        "comparison_count": 989,
        "match_count": 989,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    assert report["provenance"]["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": rulespec_sha,
        }
    ]

    index = json.loads((cases_path / "index.json").read_text())
    chunks = [
        json.loads((cases_path / f"chunk-{number}.json").read_text())
        for number in range(index["chunks"])
    ]
    assert index["count"] == index["total_cases"] == 989
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 489]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 989
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)
    for projected, source in zip(projected_cases, cases, strict=True):
        assert projected["h"] == {}
        assert projected["m"] == []
        assert projected["v"] == [
            {
                "c": concept,
                "l": source["axiom"],
                "x": source["policyengine"],
            }
        ]

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    assert (
        manifest["reports"].count(
            "axiom-policyengine-taxsim-ks-income-tax-liability.json"
        )
        == 1
    )


def test_committed_dc_populace_evidence_is_canonical_and_complete():
    rulespec_sha = "6b0773d3f7fa6719f208154f3e609e292ab7abe7"
    engine_sha = "ffd8213271947b0189a9dd61a055c1e0e78908a0"
    executable_sha = (
        "c7eef635dadca73b51d4012fcc2f12c2f08dd82f9d505ba5228f127779a3a4e2"
    )
    concept = (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits"
        "#dc_pit_2026_section_47_1806_03_schedule_before_credits"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-dc-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-dc-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/dc-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["DC"]
    cases = state["cases"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert campaign["projection_diagnostics"]["DC"] == {
        "compared_tax_unit_count": 1_362,
        "negative_taxable_income_count": 271,
        "positive_taxable_income_count": 1_088,
        "zero_taxable_income_count": 3,
    }
    assert state["compared_count"] == 1_362
    assert state["mismatch_count"] == 0
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert state["policyengine_target"] == "dc_income_tax_before_credits_joint"
    assert sum(case["policyengine"] == 0 for case in cases) == 274
    assert sum(case["policyengine"] > 0 for case in cases) == 1_088
    assert all(case["matched"] for case in cases)

    runtime = campaign["runtime_provenance"]
    assert runtime["rulespec"]["commit"] == rulespec_sha
    assert runtime["rulespec"]["working_tree"] == "clean"
    assert runtime["axiom_engine"]["commit"] == engine_sha
    assert runtime["axiom_engine"]["executable_sha256"] == executable_sha
    assert runtime["axiom_engine"]["working_tree"] == "clean"
    assert runtime["packages"] == {
        "policyengine": "4.18.9",
        "policyengine-us": "1.752.2",
    }

    report = json.loads(report_path.read_text())
    assert report["suite"] == "dc-income-tax-populace"
    assert report["case_count"] == 1_362
    assert report["summary"] == {
        "comparison_count": 1_362,
        "match_count": 1_362,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["DC"]
    )
    assert report["provenance"]["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": rulespec_sha,
        }
    ]

    index = json.loads((cases_path / "index.json").read_text())
    chunks = [
        json.loads((cases_path / f"chunk-{number}.json").read_text())
        for number in range(index["chunks"])
    ]
    assert index["count"] == index["total_cases"] == 1_362
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 362]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 1_362
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)
    for projected, source in zip(projected_cases, cases, strict=True):
        assert projected["h"] == {}
        assert projected["m"] == []
        assert projected["v"] == [
            {
                "c": concept,
                "l": source["axiom"],
                "x": source["policyengine"],
            }
        ]

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    assert (
        manifest["reports"].count(
            "axiom-policyengine-taxsim-dc-income-tax-liability.json"
        )
        == 1
    )


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


def test_ohio_dashboard_description_names_bounded_schedule():
    output = (
        "us-oh:policies/income_tax/pilot_liability_pipeline"
        "#oh_pit_pilot_schedule_tax"
    )
    report = project_state(
        "OH",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "oh_nonbusiness_income_tax_before_non_refundable_credits_derived"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 5747.02(A)(3)(c)" in description
    assert "nonbusiness-income schedule before nonrefundable credits" in description
    assert "caller-supplied completed Ohio taxable nonbusiness income" in description
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
