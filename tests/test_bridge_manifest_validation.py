from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import yaml

from axiom_oracles import suites
from scripts import build_us_tariff_exercise_receipt as tariff_exercise
from scripts import us_tariff_schedule_campaign as tariff_campaign
from scripts import validate_bridge_manifests as validator


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = REPO_ROOT / "axiom_oracles" / "bridges" / "manifests"


def _manifest(name: str) -> tuple[Path, dict]:
    path = MANIFEST_DIR / name
    return path, yaml.safe_load(path.read_text())


def _tariff_input_contract() -> dict:
    path = (
        REPO_ROOT / "reference/us-tariff-schedule/declared-input-contract-receipt.json"
    )
    return json.loads(path.read_text())


def _input_bindings(manifest: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for binding in manifest["bindings"]:
        names = binding.get("inputs", [binding.get("input")])
        for name in names:
            assert isinstance(name, str) and name
            assert name not in result, f"duplicate binding for {name}"
            result[name] = binding
    return result


def test_tariff_schedule_manifest_matches_frozen_input_catalog() -> None:
    """Reconcile source metadata without scanning the running eval shards."""
    _path, manifest = _manifest("us-tariff-schedule.yaml")
    contract = _tariff_input_contract()
    flag_catalog, neutrals, probes = tariff_exercise._input_catalog(
        contract, tariff_campaign, expected_chapter_count=100
    )
    expected = set(flag_catalog) | set(neutrals) | set(probes)
    expected.update(tariff_exercise.MAPPED_FIELDS)
    bindings = _input_bindings(manifest)

    assert set(bindings) == expected
    assert len(bindings) == 60
    assert {len(chapter["case_feed_inputs"]) for chapter in contract["chapters"]} == {
        58
    }
    assert set(
        tariff_exercise.MAPPED_FIELDS
    ) - tariff_campaign.CORE_CASE_FEED_INPUTS == {
        "entry_date",
        "origin_regime",
    }
    assert {
        name for name, binding in bindings.items() if binding["kind"] == "mapped"
    } == set(tariff_exercise.MAPPED_FIELDS)
    # These are provenance-kind counts, not measured distinct-value counts.
    assert Counter(binding["kind"] for binding in bindings.values()) == {
        "mapped": 5,
        "projected": 29,
        "constant": 26,
    }
    assert all(binding["audit"] == "read" for binding in bindings.values())
    assert all(
        type(binding.get("value")) is bool
        for binding in manifest["bindings"]
        if binding["kind"] == "constant"
    )


def test_tariff_panel_unit_reassignment_stays_aggregate_only() -> None:
    """A conserved group-count transfer is not an exact case commitment."""

    receipt = json.loads(
        (
            REPO_ROOT / "axiom_oracles/bridges/exercise_receipts/us-tariff-panel.json"
        ).read_text()
    )
    report = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/axiom-yale-us-tariff-panel.json"
        ).read_text()
    )
    report["cases"][0]["unit_count"] += 1
    report["cases"][1]["unit_count"] -= 1

    assert (
        validator._validate_panel_group_receipt("us-tariff-panel.yaml", receipt, report)
        == []
    )
    assert receipt["population_commitment"] == "grouped-aggregate-only"
    assert receipt["cases"] == len(report["cases"]) == 122
    assert (
        receipt["comparison_units"]
        == sum(row["unit_count"] for row in report["cases"])
        == 39_600
    )


def test_tariff_schedule_note16_assumption_is_a_bounded_true_constant() -> None:
    _path, manifest = _manifest("us-tariff-schedule.yaml")
    bindings = _input_bindings(manifest)
    reference = _tariff_input_contract()["reference_assumptions"][
        "yale_note16_metal_weight"
    ]
    expected = reference["campaign_binding"]
    binding = bindings[expected["input"]]

    assert expected["value"] is True
    assert binding["kind"] == "constant"
    assert binding["value"] is True
    assert binding["source"] == reference["path"]
    assert binding["source_function"] == (
        "scripts/us_tariff_schedule_campaign.py::_case_feed"
    )
    for field in ("factual_status", "interpretation", "scope"):
        assert binding[field] == expected[field]


def test_tariff_schedule_false_facts_are_construction_constants() -> None:
    _path, manifest = _manifest("us-tariff-schedule.yaml")
    bindings = _input_bindings(manifest)
    contract = _tariff_input_contract()
    qualification_inputs = {
        "entry_is_note33_auto_part_subject_to_import_adjustment_offset",
        "entry_is_note33_g_automobile_part",
        "entry_is_note37_f_completed_kitchen_cabinet_vanity_or_part",
        "entry_is_note38_i_medium_or_heavy_duty_vehicle_part",
        "entry_is_note38_mhd_part_subject_to_import_adjustment_offset",
        "entry_is_note40_patented_pharmaceutical_article",
        "entry_qualifies_for_note33_certified_auto_part_heading_listed_in_notes_50_52",
        "entry_qualifies_for_note33_vehicle_heading_listed_in_notes_50_52",
        "entry_qualifies_for_note38_certified_mhd_part_heading_listed_in_notes_50_52",
        "entry_qualifies_for_note39_heading_9903_79_01",
    }
    hardcoded_false = {
        "entry_is_china_301_2024_action",
        "entry_is_china_301_solar",
    }
    false_inputs = (
        set(contract["neutral_boolean_inputs"]) | qualification_inputs | hardcoded_false
    )
    constants = {
        name for name, binding in bindings.items() if binding["kind"] == "constant"
    }
    assert constants == false_inputs | {tariff_campaign.NOTE16_WEIGHT_INPUT}
    for name in false_inputs:
        assert bindings[name]["kind"] == "constant"
        assert bindings[name]["value"] is False
    for name in qualification_inputs:
        assert "entry_flags keyword defaults" in bindings[name]["source_function"]
        assert "declared_s232_precedence_facts" in bindings[name]["source_function"]
        assert "actual transaction fact" in bindings[name]["reason"]
    for name in contract["neutral_boolean_inputs"]:
        assert bindings[name]["source_function"] == (
            "scripts/us_tariff_schedule_campaign.py::_case_feed NEUTRAL_BOOLEAN_INPUTS"
        )
    for name in hardcoded_false:
        assert "hard-codes both flags false" in bindings[name]["reason"]


def test_tariff_schedule_projections_preserve_source_vintage_and_probe_scope() -> None:
    _path, manifest = _manifest("us-tariff-schedule.yaml")
    bindings = _input_bindings(manifest)
    dated_note16 = {
        "entry_is_s232_note16_c_ii_derivative_aluminum_member",
        "entry_is_s232_note16_c_ix_derivative_aluminum_candidate",
        "entry_is_s232_note16_c_vi_derivative_aluminum_candidate",
    }
    sector_membership = {
        "entry_is_s232_copper_additional_member",
        "entry_is_s232_copper_primary_member",
        "entry_is_s232_note33_auto_part_candidate",
        "entry_is_s232_note33_vehicle_candidate",
        "entry_is_s232_note37_cabinet_vanity_candidate",
        "entry_is_s232_note37_softwood_member",
        "entry_is_s232_note37_upholstered_wood_furniture_member",
        "entry_is_s232_note38_bus_member",
        "entry_is_s232_note38_mhd_part_candidate",
        "entry_is_s232_note38_mhd_vehicle_member",
        "entry_is_s232_note39_semiconductor_candidate",
        "entry_is_s232_note40_pharmaceutical_candidate",
    }
    for name in dated_note16:
        binding = bindings[name]
        assert binding["kind"] == "projected"
        assert binding["source"].endswith("/note16-232-aluminum-precedence.yaml")
        assert "_note16_member" in binding["source_function"]
        assert "probe date" in binding["note"]
        assert "2026-07-01" in binding["note"]
    for name in sector_membership:
        binding = bindings[name]
        assert binding["kind"] == "projected"
        assert binding["source"].endswith("/note50-52-232-sector-precedence.yaml")
        assert "2026-08-03" in binding["note"]
        assert "not a historical-vintage panel" in binding["note"]
    metal_chapter = bindings["entry_is_s232_note16_metal_chapter"]
    assert metal_chapter["kind"] == "projected"
    assert "72, 73, 74, or 76" in metal_chapter["note"]
    for name, expected in _tariff_input_contract()["probe_boolean_inputs"].items():
        binding = bindings[name]
        assert binding["kind"] == "projected"
        assert binding["source"] == expected["source_rule"]
        assert binding["source_function"] == (
            "scripts/us_tariff_schedule_campaign.py::_probe_boolean_inputs"
        )
        assert expected["effective_from"] in binding["note"]
        assert expected["effective_through"] in binding["note"]


def test_committed_dk_manifests_are_record_and_period_clean() -> None:
    for filename in (
        "dk-child-youth-benefit.yaml",
        "dk-child-youth-benefit-2023.yaml",
        "dk-child-youth-benefit-couple.yaml",
    ):
        path, manifest = _manifest(filename)
        errors, findings = validator.validate(path, manifest)
        assert errors == []
        assert findings == []


def test_couple_non_earner_777_suite_mutant_is_a_finding(monkeypatch) -> None:
    path, manifest = _manifest("dk-child-youth-benefit-couple.yaml")
    original_load_suite = suites.load_suite

    def load_mutant(name: str):
        cases = copy.deepcopy(original_load_suite(name))
        if name != "dk-child-youth-benefit-couple":
            return cases
        for case in cases:
            for record in case.metadata["axiom_input_records"]:
                if (
                    record["entity_id"] == "non_earner"
                    and "personskatteloven_section_7_income_basis" in record["name"]
                ):
                    record["value"] = 777
        return cases

    monkeypatch.setattr(suites, "load_suite", load_mutant)
    errors, findings = validator.validate(path, manifest)

    assert errors == []
    assert len(findings) == 2
    assert all("declares 0, but the suite feeds [777]" in item for item in findings)


def test_couple_unscoped_constant_rejects_one_record_777_mutant(monkeypatch) -> None:
    path, manifest = _manifest("dk-child-youth-benefit-couple.yaml")
    original_load_suite = suites.load_suite
    cpi_input = (
        "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/"
        "paragraf-1#input.percentage_change_rounded_to_one_decimal_place"
    )

    def load_mutant(name: str):
        cases = copy.deepcopy(original_load_suite(name))
        if name != "dk-child-youth-benefit-couple":
            return cases
        for case in cases:
            for record in case.metadata["axiom_input_records"]:
                if record["entity_id"] == "non_earner" and record["name"] == cpi_input:
                    record["value"] = 777
        return cases

    monkeypatch.setattr(suites, "load_suite", load_mutant)
    errors, _findings = validator.validate(path, manifest)

    assert any(
        "record-varying input(s) cannot use an unscoped kind=constant" in item
        and cpi_input in item
        for item in errors
    )


def test_non_synthetic_population_cannot_disable_pinning() -> None:
    path, manifest = _manifest("co-snap-populace.yaml")
    manifest["population"] = {
        "family": "populace-us",
        "pin_required": False,
    }

    _errors, findings = validator.validate(path, manifest)

    assert any("requires pin_required=true" in item for item in findings)
    assert any("has no revision + sha256 identity" in item for item in findings)


def test_population_identity_rejects_truthy_non_strings(monkeypatch) -> None:
    path, manifest = _manifest("co-snap-populace.yaml")
    report = {
        "population": "enhanced-cps",
        "dataset_identity": {"revision": True, "sha256": True},
        "provenance": {},
    }
    monkeypatch.setattr(
        validator,
        "_report_for",
        lambda _suite_names: ("dashboard/public/data/mutant.json", report),
    )

    _errors, findings = validator.validate(path, manifest)

    assert any("has no revision + sha256 identity" in item for item in findings)

    report["dataset_identity"] = {
        "revision": "populace-us-mutant-test",
        "sha256": "a" * 64,
    }
    _errors, findings = validator.validate(path, manifest)
    assert not any("has no revision + sha256 identity" in item for item in findings)


def test_invariant_cpi_cannot_fabricate_a_mapped_population_source() -> None:
    path, manifest = _manifest("dk-child-youth-benefit.yaml")
    cpi_input = (
        "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/"
        "paragraf-1#input.percentage_change_rounded_to_one_decimal_place"
    )
    [binding] = [
        item for item in manifest["bindings"] if item.get("input") == cpi_input
    ]
    binding["kind"] = "mapped"
    binding["source"] = "population:invented_cpi"

    errors, _findings = validator.validate(path, manifest)

    assert any("fabricates external population provenance" in item for item in errors)
    assert any("suite-invariant multi-case input" in item for item in errors)


def test_execution_period_is_bound_to_comparison_config() -> None:
    path, manifest = _manifest("dk-child-youth-benefit-2023.yaml")
    manifest["execution_period"] = "2023"

    errors, _findings = validator.validate(path, manifest)

    assert any(
        "execution_period '2023' does not match" in item and "2025-06-01" in item
        for item in errors
    )


def test_euromod_period_cannot_fall_back_to_year(monkeypatch, tmp_path: Path) -> None:
    path, manifest = _manifest("dk-child-youth-benefit-2023.yaml")
    manifest["execution_period"] = "2023"
    config_dir = tmp_path / "comparisons"
    config_dir.mkdir()
    config = {
        "name": "coordinated-period-mutant",
        "runner": {
            "type": "euromod-synthetic-compare",
            "parameters": {
                "suite": "dk-child-youth-benefit-2023",
                "year": 2023,
            },
        },
        "dashboard": {"suite": "dk-child-youth-benefit-2023"},
    }
    (config_dir / "mutant.yaml").write_text(yaml.safe_dump(config))
    monkeypatch.setattr(validator, "COMPARISON_DIR", config_dir)

    errors, _findings = validator.validate(path, manifest)

    assert any(
        "euromod-synthetic-compare" in item
        and "lacks required runner.parameters.period" in item
        for item in errors
    )


def test_differing_periods_require_both_explicit_fields() -> None:
    path, manifest = _manifest("dk-child-youth-benefit-2023.yaml")
    manifest.pop("logical_period")
    manifest.pop("execution_period")

    errors, _findings = validator.validate(path, manifest)

    assert any(
        "differing logical and execution periods require explicit" in item
        for item in errors
    )


def test_strict_enforces_declared_lanes_and_surfaces_debt(monkeypatch, capsys) -> None:
    """--strict reds a finding on a strict-declared manifest; a finding on a
    non-strict manifest is printed as audit debt without failing the run."""
    strict_path = REPO_ROOT / "strict-lane.yaml"
    legacy_path = REPO_ROOT / "legacy.yaml"
    monkeypatch.setattr(validator, "global_collisions", lambda _manifests: [])
    monkeypatch.setattr(
        validator,
        "validate",
        lambda path, _manifest: ([], [f"{path.name}: mutant finding"]),
    )
    monkeypatch.setattr(
        validator.sys, "argv", ["validate_bridge_manifests.py", "--strict"]
    )

    # Debt on a non-strict manifest: visible, exit 0.
    monkeypatch.setattr(
        validator, "load_manifests", lambda: {legacy_path: {"strict": False}}
    )
    assert validator.main() == 0
    out = capsys.readouterr().out
    assert "legacy.yaml: mutant finding" in out
    assert "audit-debt finding(s)" in out

    # The same finding on a strict-declared manifest: exit 1.
    monkeypatch.setattr(
        validator, "load_manifests", lambda: {strict_path: {"strict": True}}
    )
    assert validator.main() == 1
