import hashlib
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


def test_manifest_reconciliation_retires_only_declared_taxsim_ghosts(tmp_path):
    published = tmp_path / "published.json"
    published.write_text("{}\n")

    assert reconcile_manifest_reports(
        ["published.json", *RETIRED_MANIFEST_REPORTS],
        data_dir=tmp_path,
        required_reports=frozenset({"published.json"}),
    ) == ["published.json"]
    assert RETIRED_MANIFEST_REPORTS == {
        "axiom-policyengine-taxsim-al-income-tax-liability.json",
        "axiom-policyengine-taxsim-de-income-tax-liability.json",
    }


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


def test_arkansas_dashboard_description_names_person_schedule_component():
    output = (
        "us-ar:policies/income_tax/pilot_liability_pipeline"
        "#ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    )
    report = project_state(
        "AR",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "ar_income_tax_before_non_refundable_credits_indiv"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "Arkansas Act 2 of 2026 section 1" in description
    assert "before nonrefundable credits" in description
    assert "Person grain" in description
    assert "summed to TaxUnit only for comparison accounting" in description
    assert "filing-unit aggregation or method selection" in description
    assert "low-income tables" in description
    assert "final liability" in description


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


def test_california_dashboard_description_names_bhst_component():
    output = (
        "us-ca:policies/income_tax/pilot_liability_pipeline"
        "#ca_pit_pilot_behavioral_health_services_tax"
    )
    report = project_state(
        "CA",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "ca_mental_health_services_tax",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "Behavioral Health Services Tax" in description
    assert "completed California taxable income above $1 million" in description
    assert "does not claim broad California income-tax liability" in description


def test_delaware_dashboard_description_names_person_schedule_component():
    output = (
        "us-de:policies/income_tax/pilot_liability_pipeline"
        "#de_pit_pilot_separate_schedule_tax"
    )
    report = project_state(
        "DE",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "de_income_tax_before_non_refundable_credits_indv"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 1102(a)(14) individual schedule" in description
    assert "Person grain" in description
    assert "summed to TaxUnit only for comparison accounting" in description
    assert "filing-method selection" in description
    assert "combined-return computation" in description
    assert "final liability" in description


def test_minnesota_dashboard_description_names_narrow_schedule():
    output = (
        "us-mn:policies/income_tax/pilot_liability_pipeline"
        "#mn_pit_pilot_schedule_tax"
    )
    report = project_state(
        "MN",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "mn_basic_tax_precision_stable",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "Minnesota tax-year-2026 continuous graduated schedule" in description
    assert "completed Minnesota taxable net income" in description
    assert "does not claim tax-table rounding" in description
    assert "final Minnesota liability" in description


def test_montana_dashboard_description_names_bounded_before_credit_tax():
    output = (
        "us-mt:policies/income_tax/pilot_liability_pipeline"
        "#mt_pit_pilot_income_tax_liability"
    )
    report = project_state(
        "MT",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "mt_income_tax_before_non_refundable_credits_joint"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "before nonrefundable credits" in description
    assert "MCA 15-30-2103" in description
    assert "completed Montana taxable income" in description
    assert "section 1222 net-long-term-capital-gain portion" in description
    assert "final annual liability" in description


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


def test_committed_indiana_populace_evidence_is_canonical_and_complete(
    tmp_path,
    monkeypatch,
):
    rulespec_sha = "ecb057ef35ab47fb055213b42459c42ae63485ef"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-in:policies/income_tax/pilot_liability_pipeline"
        "#in_pit_pilot_income_tax_liability"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-in-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-in-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/in-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["IN"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["IN"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert state["compared_count"] == 1_292
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.5360000003129244
    assert state["tolerance"] == 1.0
    assert state["relative_tolerance"] == 0.0
    assert state["output"] == concept
    assert sum(case["policyengine"] == 0 for case in cases) == 76
    assert sum(case["policyengine"] > 0 for case in cases) == 1_216
    assert all(case["matched"] for case in cases)
    assert campaign["projection_diagnostics"]["IN"] == {
        "compared_tax_unit_count": 1_292,
        "nonpositive_agi_count": 76,
        "positive_agi_count": 1_216,
        "zero_output_count": 76,
        "positive_output_count": 1_216,
    }

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
    assert report["suite"] == "in-income-tax-populace"
    assert report["case_count"] == 1_292
    assert report["summary"] == {
        "comparison_count": 1_292,
        "match_count": 1_292,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    assert "2.95 percent state rate" in report["aggregates"][0]["description"]
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["IN"]
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
    assert index["count"] == index["total_cases"] == 1_292
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 292]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 1_292
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    monkeypatch.setattr(emitter, "CASES_ROOT", tmp_path)
    emitter.emit_case_chunks("IN", state)
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "in-income-tax-populace").iterdir())
    }
    emitter.emit_case_chunks("IN", state)
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "in-income-tax-populace").iterdir())
    }
    assert second == first


def test_committed_pennsylvania_populace_evidence_is_canonical_and_complete(
    tmp_path,
    monkeypatch,
):
    rulespec_sha = "ecb057ef35ab47fb055213b42459c42ae63485ef"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-pa:policies/income_tax/pilot_liability_pipeline"
        "#pa_pit_pilot_income_tax_liability"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-pa-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-pa-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/pa-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["PA"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["PA"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert state["compared_count"] == 2_457
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.4159999992698431
    assert state["tolerance"] == 1.0
    assert state["relative_tolerance"] == 0.0
    assert state["output"] == concept
    # Comparison cases are cent-rounded, so nine positive sub-cent runtime
    # outputs serialize as zero. The raw branch inventory below remains the
    # authoritative proof of 118 exact-zero and 2,339 positive outputs.
    assert sum(case["policyengine"] == 0 for case in cases) == 127
    assert sum(case["policyengine"] > 0 for case in cases) == 2_330
    assert all(case["matched"] for case in cases)
    assert campaign["projection_diagnostics"]["PA"] == {
        "compared_tax_unit_count": 2_457,
        "negative_adjusted_taxable_income_count": 0,
        "zero_adjusted_taxable_income_count": 118,
        "positive_adjusted_taxable_income_count": 2_339,
        "zero_output_count": 118,
        "positive_output_count": 2_339,
    }

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
    assert report["suite"] == "pa-income-tax-populace"
    assert report["case_count"] == 2_457
    assert report["summary"] == {
        "comparison_count": 2_457,
        "match_count": 2_457,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    description = report["aggregates"][0]["description"]
    assert "3.07 percent rate" in description
    assert "completed Pennsylvania adjusted taxable income" in description
    assert "fails closed" in description
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["PA"]
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
    assert index["count"] == index["total_cases"] == 2_457
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 500, 500, 457]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 2_457
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    monkeypatch.setattr(emitter, "CASES_ROOT", tmp_path)
    emitter.emit_case_chunks("PA", state)
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "pa-income-tax-populace").iterdir())
    }
    emitter.emit_case_chunks("PA", state)
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "pa-income-tax-populace").iterdir())
    }
    assert second == first


def test_committed_south_carolina_populace_evidence_is_canonical_and_complete(
    tmp_path,
    monkeypatch,
):
    rulespec_sha = "b27a928884c67c158f3547ecba24109b96c35619"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-sc:policies/income_tax/pilot_liability_pipeline"
        "#sc_pit_pilot_income_tax_liability"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-sc-campaign-2026-07-28.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-sc-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/sc-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["SC"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["SC"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert state["compared_count"] == 1_457
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.3760000001639128
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert sum(case["policyengine"] == 0 for case in cases) == 371
    assert sum(case["policyengine"] > 0 for case in cases) == 1_086
    assert all(case["matched"] for case in cases)
    assert campaign["projection_diagnostics"]["SC"] == {
        "compared_tax_unit_count": 1_457,
        "negative_taxable_income_count": 0,
        "zero_taxable_income_count": 371,
        "positive_taxable_income_count": 1_086,
        "zero_output_count": 371,
        "positive_output_count": 1_086,
    }

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
    assert report["suite"] == "sc-income-tax-populace"
    assert report["case_count"] == 1_457
    assert report["summary"] == {
        "comparison_count": 1_457,
        "match_count": 1_457,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    description = report["aggregates"][0]["description"]
    assert "before nonrefundable credits" in description
    assert "completed South Carolina taxable income" in description
    assert "fails closed" in description
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["SC"]
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
    assert index["count"] == index["total_cases"] == 1_457
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 457]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 1_457
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    monkeypatch.setattr(emitter, "CASES_ROOT", tmp_path)
    emitter.emit_case_chunks("SC", state)
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "sc-income-tax-populace").iterdir())
    }
    emitter.emit_case_chunks("SC", state)
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "sc-income-tax-populace").iterdir())
    }
    assert second == first


def test_committed_montana_populace_evidence_is_canonical_and_complete(
    tmp_path,
    monkeypatch,
):
    rulespec_sha = "6c58962f3de57a4dd26737c88767de728d230603"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-mt:policies/income_tax/pilot_liability_pipeline"
        "#mt_pit_pilot_income_tax_liability"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-mt-campaign-2026-07-28.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-mt-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/mt-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["MT"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["MT"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert state["compared_count"] == 1_171
    assert state["weighted_compared_tax_units"] == 564_739.7293636125
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.2914082035422325
    assert state["max_relative_difference"] == 8.977572697967781e-08
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert state["policyengine_target"] == (
        "mt_income_tax_before_non_refundable_credits_joint"
    )
    assert sum(case["policyengine"] == 0 for case in cases) == 254
    assert sum(case["policyengine"] > 0 for case in cases) == 917
    assert all(case["matched"] for case in cases)
    assert campaign["projection_diagnostics"] == {}

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
    assert report["suite"] == "mt-income-tax-populace"
    assert report["case_count"] == 1_171
    assert report["summary"] == {
        "comparison_count": 1_171,
        "match_count": 1_171,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    description = report["aggregates"][0]["description"]
    assert "before nonrefundable credits" in description
    assert "completed Montana taxable income" in description
    assert "section 1222 net-long-term-capital-gain portion" in description
    assert report["provenance"]["campaign_report"] == campaign_path.name
    assert report["provenance"]["branch_diagnostics"] is None
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
    assert index["count"] == index["total_cases"] == 1_171
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 171]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 1_171
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    suite_config = yaml.safe_load(POPULACE_SUITE_CONFIG.read_text())
    assert [
        suite
        for suite in suite_config["suites"]
        if suite["suite"] == "mt-income-tax-populace"
    ] == [
        {
            "suite": "mt-income-tax-populace",
            "report": report_path.name,
            "jurisdiction": "MT",
            "program": "state_income_tax",
            "oracle": "policyengine",
            "campaign_runner": "scripts/run_state_tax_populace.py",
            "projector": "scripts/emit_populace_campaign_artifacts.py",
        }
    ]

    monkeypatch.setattr(emitter, "CASES_ROOT", tmp_path)
    emitter.emit_case_chunks("MT", state)
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "mt-income-tax-populace").iterdir())
    }
    emitter.emit_case_chunks("MT", state)
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "mt-income-tax-populace").iterdir())
    }
    assert second == first


def test_committed_arkansas_populace_evidence_is_canonical_and_complete(
    tmp_path,
    monkeypatch,
):
    rulespec_sha = "6c58962f3de57a4dd26737c88767de728d230603"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-ar:policies/income_tax/pilot_liability_pipeline"
        "#ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-ar-campaign-2026-07-28.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-ar-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/ar-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["AR"]
    cases = state["cases"]
    routing = campaign["routing"]
    assert campaign["requested_states"] == ["AR"]
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert routing["sample_size_per_state"] == 0
    assert routing["errored_count"] == 0
    assert routing["states"]["AR"]["tax_unit_count"] == 1_475
    assert routing["states"]["AR"]["selected_count"] == 1_475
    assert routing["states"]["AR"]["dispositions"] == {"ready": 1_475}
    assert state["compared_count"] == 1_475
    assert state["comparison_aggregation"] == "person_sum_to_tax_unit"
    assert state["weighted_compared_tax_units"] == 1_453_018.637271964
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.0800000000745058
    assert state["max_relative_difference"] == 5.766488640852711e-8
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert (
        state["policyengine_target"]
        == "ar_income_tax_before_non_refundable_credits_indiv"
    )
    assert sum(case["policyengine"] == 0 for case in cases) == 241
    assert sum(case["policyengine"] > 0 for case in cases) == 1_234
    assert all(case["matched"] for case in cases)
    assert campaign["projection_diagnostics"] == {}

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
    assert report["suite"] == "ar-income-tax-populace"
    assert report["case_count"] == 1_475
    assert report["summary"] == {
        "comparison_count": 1_475,
        "match_count": 1_475,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    description = report["aggregates"][0]["description"]
    assert "Arkansas Act 2 of 2026 section 1" in description
    assert "before nonrefundable credits" in description
    assert "Person grain" in description
    assert "summed to TaxUnit only for comparison accounting" in description
    assert "low-income tables" in description
    assert "final liability" in description
    assert report["provenance"]["campaign_report"] == campaign_path.name
    assert report["provenance"]["branch_diagnostics"] is None
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
    assert index["count"] == index["total_cases"] == 1_475
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 475]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert len({case["id"] for case in projected_cases}) == 1_475
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    suite_config = yaml.safe_load(POPULACE_SUITE_CONFIG.read_text())
    assert [
        suite
        for suite in suite_config["suites"]
        if suite["suite"] == "ar-income-tax-populace"
    ] == [
        {
            "suite": "ar-income-tax-populace",
            "report": report_path.name,
            "jurisdiction": "AR",
            "program": "state_income_tax",
            "oracle": "policyengine",
            "campaign_runner": "scripts/run_state_tax_populace.py",
            "projector": "scripts/emit_populace_campaign_artifacts.py",
        }
    ]

    monkeypatch.setattr(emitter, "CASES_ROOT", tmp_path)
    emitter.emit_case_chunks("AR", state)
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "ar-income-tax-populace").iterdir())
    }
    emitter.emit_case_chunks("AR", state)
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((tmp_path / "ar-income-tax-populace").iterdir())
    }
    assert second == first


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


def test_committed_california_bhst_evidence_is_canonical_and_complete():
    rulespec_sha = "6b0773d3f7fa6719f208154f3e609e292ab7abe7"
    engine_sha = "ffd8213271947b0189a9dd61a055c1e0e78908a0"
    executable_sha = (
        "c7eef635dadca73b51d4012fcc2f12c2f08dd82f9d505ba5228f127779a3a4e2"
    )
    concept = (
        "us-ca:policies/income_tax/pilot_liability_pipeline"
        "#ca_pit_pilot_behavioral_health_services_tax"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-ca-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-ca-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/ca-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["CA"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["CA"]
    assert campaign["routing"]["tax_unit_count"] == 87_519
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert campaign["projection_diagnostics"]["CA"] == {
        "compared_tax_unit_count": 8_883,
        "positive_behavioral_health_services_tax_count": 1_206,
        "zero_behavioral_health_services_tax_count": 7_677,
    }
    assert state["compared_count"] == 8_883
    assert state["mismatch_count"] == 0
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert state["policyengine_target"] == "ca_mental_health_services_tax"
    assert sum(case["policyengine"] == 0 for case in cases) == 7_677
    assert sum(case["policyengine"] > 0 for case in cases) == 1_206
    assert len({case["tax_unit_id"] for case in cases}) == 8_883
    assert [case["tax_unit_id"] for case in cases] == sorted(
        case["tax_unit_id"] for case in cases
    )
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
    assert campaign["dataset_identity"]["revision"] == (
        "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    )
    assert campaign["dataset_identity"]["sha256"] == "16be6338f9d0"

    report = json.loads(report_path.read_text())
    assert report["suite"] == "ca-income-tax-populace"
    assert report["case_count"] == 8_883
    assert report["summary"] == {
        "comparison_count": 8_883,
        "match_count": 8_883,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["aggregates"][0]["concept"] == concept
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["CA"]
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
    assert index["count"] == index["total_cases"] == 8_883
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500] * 17 + [383]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    assert (
        manifest["reports"].count(
            "axiom-policyengine-taxsim-ca-income-tax-liability.json"
        )
        == 1
    )


def test_committed_minnesota_schedule_evidence_is_canonical_and_complete():
    rulespec_sha = "453f8fab7c6bd83f0e0efe604377d4ef85b7db72"
    engine_sha = "ffd8213271947b0189a9dd61a055c1e0e78908a0"
    executable_sha = (
        "c7eef635dadca73b51d4012fcc2f12c2f08dd82f9d505ba5228f127779a3a4e2"
    )
    concept = (
        "us-mn:policies/income_tax/pilot_liability_pipeline"
        "#mn_pit_pilot_schedule_tax"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-mn-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-mn-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/mn-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["MN"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["MN"]
    assert campaign["routing"]["tax_unit_count"] == 87_519
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert state["compared_count"] == 1_117
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == pytest.approx(0.81)
    assert state["tolerance"] == 1.0
    assert state["relative_tolerance"] == 0.0
    assert state["output"] == concept
    assert state["policyengine_target"] == "mn_basic_tax_precision_stable"
    assert sum(case["policyengine"] == 0 for case in cases) == 179
    assert sum(case["policyengine"] > 0 for case in cases) == 938
    assert len({case["tax_unit_id"] for case in cases}) == 1_117
    assert [case["tax_unit_id"] for case in cases] == sorted(
        case["tax_unit_id"] for case in cases
    )
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
    assert campaign["dataset_identity"]["revision"] == (
        "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    )
    assert campaign["dataset_identity"]["sha256"] == "16be6338f9d0"

    report = json.loads(report_path.read_text())
    assert report["suite"] == "mn-income-tax-populace"
    assert report["case_count"] == 1_117
    assert report["summary"] == {
        "comparison_count": 1_117,
        "match_count": 1_117,
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
    assert index["count"] == index["total_cases"] == 1_117
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 117]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    assert (
        manifest["reports"].count(
            "axiom-policyengine-taxsim-mn-income-tax-liability.json"
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


def test_new_york_dashboard_description_names_bounded_main_schedule():
    output = (
        "us-ny:policies/income_tax/pilot_liability_pipeline"
        "#ny_pit_pilot_main_income_tax"
    )
    report = project_state(
        "NY",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "ny_main_income_tax",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 601 main resident" in description
    assert "caller-supplied completed New York taxable income" in description
    assert "strict filing-status schedule classifiers" in description
    assert "excludes section 601(d-5) supplemental tax" in description
    assert "local taxes" in description
    assert "final liability" in description


def test_illinois_dashboard_description_names_bounded_before_credit_tax():
    output = (
        "us-il:policies/income_tax/pilot_liability_pipeline"
        "#il_pit_pilot_income_tax_liability"
    )
    report = project_state(
        "IL",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "il_income_tax_before_non_refundable_credits"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "before nonrefundable credits" in description
    assert "caller-supplied completed Illinois taxable income" in description
    assert "completed investment-credit recapture" in description
    assert "excludes taxable-income construction" in description
    assert "payments" in description
    assert "final annual liability" in description


def test_committed_illinois_before_credit_evidence_is_canonical_and_complete():
    rulespec_sha = "453f8fab7c6bd83f0e0efe604377d4ef85b7db72"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-il:policies/income_tax/pilot_liability_pipeline"
        "#il_pit_pilot_income_tax_liability"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-il-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-il-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/il-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["IL"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["IL"]
    assert campaign["routing"]["tax_unit_count"] == 87_519
    assert campaign["routing"]["states"]["IL"]["selected_count"] == 2_332
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert campaign["projection_diagnostics"]["IL"] == {
        "compared_tax_unit_count": 2_332,
        "positive_recapture_count": 0,
        "positive_taxable_income_count": 2_113,
        "zero_recapture_count": 2_332,
        "zero_taxable_income_count": 219,
    }
    assert state["compared_count"] == 2_332
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.5040000006556511
    assert state["tolerance"] == 1.0
    assert state["relative_tolerance"] == 0.0
    assert state["output"] == concept
    assert (
        state["policyengine_target"]
        == "il_income_tax_before_non_refundable_credits"
    )
    assert len({case["tax_unit_id"] for case in cases}) == 2_332
    assert [case["tax_unit_id"] for case in cases] == sorted(
        case["tax_unit_id"] for case in cases
    )
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
    assert campaign["dataset_identity"]["revision"] == (
        "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    )
    assert campaign["dataset_identity"]["sha256"] == "16be6338f9d0"

    report = json.loads(report_path.read_text())
    assert report["suite"] == "il-income-tax-populace"
    assert report["case_count"] == 2_332
    assert report["summary"] == {
        "comparison_count": 2_332,
        "match_count": 2_332,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert (
        report["engines"]["policyengine"]
        == "il_income_tax_before_non_refundable_credits"
    )
    assert report["aggregates"][0]["concept"] == concept
    assert "before nonrefundable credits" in (
        report["aggregates"][0]["description"]
    )
    assert "bounded suite excludes taxable-income construction" in (
        report["aggregates"][0]["description"]
    )
    assert report["provenance"]["campaign_report"] == campaign_path.name
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["IL"]
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
    assert index["count"] == index["total_cases"] == 2_332
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500, 500, 500, 500, 332]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    assert (
        manifest["reports"].count(
            "axiom-policyengine-taxsim-il-income-tax-liability.json"
        )
        == 1
    )


def test_committed_new_york_main_schedule_evidence_is_canonical_and_complete():
    rulespec_sha = "5d8f3469682d8058a1396745812f614ed0f79200"
    engine_sha = "68d65229632e371b96d8eb25c704c1977a2b7ed3"
    executable_sha = (
        "2e881f18dda64ae801d318a16c61525f50d094d83f5de71d330098696da9dd42"
    )
    concept = (
        "us-ny:policies/income_tax/pilot_liability_pipeline"
        "#ny_pit_pilot_main_income_tax"
    )
    campaign_path = (
        REPO_ROOT / "reports/state-tax-populace-ny-campaign-2026-07-27.json"
    )
    report_path = (
        DASHBOARD_DATA / "axiom-policyengine-ny-income-tax-populace.json"
    )
    cases_path = DASHBOARD_DATA / "cases/ny-income-tax-populace"

    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["NY"]
    cases = state["cases"]
    assert campaign["requested_states"] == ["NY"]
    assert campaign["routing"]["tax_unit_count"] == 87_519
    assert campaign["routing"]["states"]["NY"]["selected_count"] == 3_741
    assert campaign["comparison"]["sample_size_per_state"] == 0
    assert campaign["projection_diagnostics"]["NY"] == {
        "compared_tax_unit_count": 3_741,
        "head_of_household_count": 217,
        "joint_or_surviving_count": 1_543,
        "negative_taxable_income_count": 0,
        "positive_taxable_income_count": 3_222,
        "single_or_separate_count": 1_981,
        "zero_taxable_income_count": 519,
    }
    assert state["compared_count"] == 3_741
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 2.119999997317791
    assert state["tolerance"] == 2.25
    assert state["relative_tolerance"] == 1e-7
    assert state["output"] == concept
    assert state["policyengine_target"] == "ny_main_income_tax"
    assert len({case["tax_unit_id"] for case in cases}) == 3_741
    assert [case["tax_unit_id"] for case in cases] == sorted(
        case["tax_unit_id"] for case in cases
    )
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
    assert campaign["dataset_identity"]["revision"] == (
        "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    )
    assert campaign["dataset_identity"]["sha256"] == "16be6338f9d0"

    report = json.loads(report_path.read_text())
    assert report["suite"] == "ny-income-tax-populace"
    assert report["case_count"] == 3_741
    assert report["summary"] == {
        "comparison_count": 3_741,
        "match_count": 3_741,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    assert report["engines"]["policyengine"] == "ny_main_income_tax"
    assert report["aggregates"][0]["concept"] == concept
    assert "section 601 main resident" in report["aggregates"][0]["description"]
    assert "excludes section 601(d-5) supplemental tax" in (
        report["aggregates"][0]["description"]
    )
    assert report["provenance"]["campaign_report"] == campaign_path.name
    assert report["provenance"]["branch_diagnostics"] == (
        campaign["projection_diagnostics"]["NY"]
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
    assert index["count"] == index["total_cases"] == 3_741
    assert index["chunk_size"] == 500
    assert [len(chunk) for chunk in chunks] == [500] * 7 + [241]
    projected_cases = [case for chunk in chunks for case in chunk]
    assert [case["id"] for case in projected_cases] == [
        case["tax_unit_id"] for case in cases
    ]
    assert all(case["r"] == 1.0 for case in projected_cases)

    manifest = json.loads((DASHBOARD_DATA / "manifest.json").read_text())
    assert manifest["reports"].count(report_path.name) == 1
    assert (
        manifest["reports"].count(
            "axiom-policyengine-taxsim-ny-income-tax-liability.json"
        )
        == 1
    )


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
