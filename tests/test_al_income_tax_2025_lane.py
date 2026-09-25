"""Saved-evidence invariants; no Alabama tax law is implemented in these tests."""

import hashlib
import json
import shutil

import pandas as pd
import pytest
import yaml

from scripts import generate_al_income_tax_2025 as lane


@pytest.fixture(scope="module")
def frame():
    return lane.assemble()[0]


def test_manifest_hashes_match():
    manifest = lane.verify_manifest()
    assert set(manifest["files"]) == {
        p.name for p in lane.REFERENCE_DIR.iterdir() if p.name != "manifest.json"
    }
    for name, record in manifest["files"].items():
        path = lane.REFERENCE_DIR / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        assert path.stat().st_size == record["bytes"]


def test_tampered_reference_is_rejected_before_assembly(tmp_path):
    reference = tmp_path / "reference"
    shutil.copytree(lane.REFERENCE_DIR, reference)
    with (reference / "households.csv").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="Manifest hash mismatch: households.csv"):
        lane.assemble(reference)


def test_frame_households_and_observed_bands(frame):
    assert frame.index.is_unique
    assert frame.index.tolist() == list(range(88052, 89207))
    assert len(frame) == 1155
    assert frame.pe_taxsim_liability_band.value_counts().to_dict() == {
        "within_1": 681,
        "over_1_through_15": 76,
        "over_15": 398,
    }


def test_inputs_join_by_id_and_reject_duplicates(tmp_path):
    reference = tmp_path / "reference"
    shutil.copytree(lane.REFERENCE_DIR, reference)
    households = (
        pd.read_csv(reference / "households.csv").set_index("taxsimid").sort_index()
    )
    path = reference / "engine_outputs_state1.csv"
    saved = pd.read_csv(path)
    saved.iloc[::-1].to_csv(path, index=False)
    lanes = lane._release(reference, 1, households)
    assert all(rows.index.equals(households.index) for rows in lanes.values())
    pd.concat([saved, saved.iloc[:1]]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Duplicate release IDs"):
        lane._release(reference, 1, households)


def test_components_retain_sidecar_and_unavailable_taxsim_deduction(frame):
    for metric, variable in lane.PE_EXTRA.items():
        pd.testing.assert_series_equal(
            frame["pe_" + metric], frame["pe_sidecar_" + variable], check_names=False
        )
    assert frame.taxsim_federal_tax_deduction.isna().all()
    assert set(frame.taxsim_deductions_status) == {"observed_behavior_fit"}
    attribution = lane.cause_attribution(frame.copy())
    assert attribution["taxable_income_gap_identity_max_abs_error"] < 1e-6
    assert attribution["liability_gap_identity_max_abs_error"] < 1e-6
    for band in attribution["bands"].values():
        assert sum(band["primary_stage_counts"].values()) == band["households"]


def test_reports_pending_module_and_standard_comparison(tmp_path):
    output = tmp_path / "three-way.json"
    report = lane.generate(rulespec_root=tmp_path / "rulespec-us", output=output)
    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["engines"] == {"left": "policyengine", "right": "taxsim"}
    assert report["period"] == "2025"
    assert report["case_count"] == 1155
    assert report["summary"]["comparison_count"] == 1155
    assert report["summary"]["match_count"] == 681
    assert report["summary"]["mismatch_count"] == 474
    assert report["summary"]["error_count"] == 0
    assert report["concepts"][0]["id"] == lane.CONCEPT
    assert report["axiom_pairwise_reports"] == {}
    for leg in report["axiom_legs"].values():
        assert leg["status"] == "pending_module"
        assert "d270" in leg["reason"]
        assert (
            leg["module_path"]
            == "us-al/policies/income_tax/2025_resident_liability.yaml"
        )
        assert len(leg["cases"]) == 1155
        assert all(case["status"] == "pending_module" for case in leg["cases"])
        assert all(
            value is None for case in leg["cases"] for value in case["outputs"].values()
        )
        assert all(
            "form_1040_line_22" in case["unavailable_inputs"] for case in leg["cases"]
        )
    assert json.loads(output.read_text()) == report
    assert output.with_suffix(".md").is_file()
    components = output.parent / report["component_table"]["path"]
    assert lane.sha256(components) == report["component_table"]["sha256"]
    table = pd.read_csv(components)
    assert table.taxsimid.nunique() == 1155
    assert table.axiom_pe_federal_liability.isna().all()
    assert table.axiom_taxsim_federal_liability.isna().all()


def test_ground_truth_fixtures_have_document_and_page():
    evidence = yaml.safe_load(
        (lane.REFERENCE_DIR / "ground_truth_fixtures.yaml").read_text()
    )
    fixtures = evidence["fixtures"]
    assert fixtures
    assert len({fixture["id"] for fixture in fixtures}) == len(fixtures)
    for fixture in fixtures:
        assert fixture["document"]
        assert "page" in fixture
        # Preserve the supplied unpaginated statute; its subsection is the locator.
        if fixture["page"] is None:
            assert fixture["document"] == "us-al/statute/40-18-19"
            assert fixture["scope"] == "(a)(13)"
        else:
            assert isinstance(fixture["page"], int) and fixture["page"] > 0


def test_failed_axiom_case_with_numeric_liability_is_excluded(tmp_path, monkeypatch):
    original = lane.evaluate_axiom_legs

    def evaluate(households, frame, **kwargs):
        legs = original(households, frame, **kwargs)
        for leg in legs.values():
            for record, status in zip(
                leg["cases"][:2], ["execution_error", "evaluated"]
            ):
                record["status"] = status
                record["outputs"] = dict.fromkeys(lane.OUTPUTS, 25.0)
        return legs

    monkeypatch.setattr(lane, "evaluate_axiom_legs", evaluate)
    report = lane.generate(
        rulespec_root=tmp_path / "rulespec-us", output=tmp_path / "report.json"
    )
    assert len(report["axiom_pairwise_reports"]) == 4
    for pairwise in report["axiom_pairwise_reports"].values():
        assert pairwise["coverage"] == {
            "evaluated": 1,
            "unavailable": 1154,
            "total": 1155,
        }
        assert pairwise["case_count"] == 1
