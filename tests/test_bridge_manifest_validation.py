from __future__ import annotations

import copy
from pathlib import Path

import yaml

from axiom_oracles import suites
from scripts import validate_bridge_manifests as validator


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = REPO_ROOT / "axiom_oracles" / "bridges" / "manifests"


def _manifest(name: str) -> tuple[Path, dict]:
    path = MANIFEST_DIR / name
    return path, yaml.safe_load(path.read_text())


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


def test_strict_is_global(monkeypatch) -> None:
    legacy_path = REPO_ROOT / "legacy.yaml"
    manifests = {legacy_path: {"strict": False}}
    monkeypatch.setattr(validator, "load_manifests", lambda: manifests)
    monkeypatch.setattr(validator, "global_collisions", lambda _manifests: [])
    monkeypatch.setattr(
        validator,
        "validate",
        lambda path, _manifest: ([], [f"{path.name}: mutant finding"]),
    )

    monkeypatch.setattr(
        validator.sys, "argv", ["validate_bridge_manifests.py", "--strict"]
    )
    assert validator.main() == 1
