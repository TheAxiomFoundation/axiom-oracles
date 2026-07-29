"""Exact oracle-registry contract for California's TY2026 BHST subgraph."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ca:policies/income_tax/pilot_liability_pipeline"
RULESPEC_RELATIVE_PATH = Path(
    "us-ca/policies/income_tax/pilot_liability_pipeline.yaml"
)
EXPECTED_OUTPUT_COUNT = 29
EXPECTED_PARAMETER_VALUES = {
    "ca_pit_pilot_behavioral_health_services_tax_threshold": (
        "gov.states.ca.tax.income.mental_health_services",
        ("thresholds", 1),
        "money",
    ),
    "ca_pit_pilot_behavioral_health_services_tax_rate": (
        "gov.states.ca.tax.income.mental_health_services",
        ("rates", 1),
        "rate",
    ),
}
EXPECTED_DIRECT_VARIABLES = {
    "ca_pit_pilot_completed_taxable_income": "ca_taxable_income",
    "ca_pit_pilot_behavioral_health_services_tax": (
        "ca_mental_health_services_tax"
    ),
}


def _module_mappings():
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    return {
        legal_id.removeprefix(prefix): mapping
        for legal_id, mapping in registry.mappings_by_legal_id.items()
        if legal_id.startswith(prefix)
    }


def _rulespec_path() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root.parent / "rulespec-us" / RULESPEC_RELATIVE_PATH,
        repo_root / ".rulespec-us" / RULESPEC_RELATIVE_PATH,
    ]
    configured_root = os.environ.get("AXIOM_RULESPEC_ROOT")
    if configured_root:
        configured = Path(configured_root).expanduser()
        candidates = [
            configured / RULESPEC_RELATIVE_PATH,
            configured / "rulespec-us" / RULESPEC_RELATIVE_PATH,
            *candidates,
        ]
    return next((path for path in candidates if path.is_file()), None)


def _rulespec_output_names(path: Path) -> set[str]:
    payload = yaml.safe_load(path.read_text())
    return {
        str(rule["name"])
        for rule in payload["rules"]
        if isinstance(rule, dict) and rule.get("name")
    }


def _write_synthetic_module(root: Path, output_names: set[str]) -> None:
    rulespec_path = root / RULESPEC_RELATIVE_PATH
    rulespec_path.parent.mkdir(parents=True)
    rulespec_path.write_text(
        yaml.safe_dump(
            {
                "format": "rulespec/v1",
                "module": MODULE.split(":", 1)[1],
                "rules": [
                    {
                        "name": output_name,
                        "kind": "derived",
                        "versions": [
                            {"effective_from": "2026-01-01", "formula": "0"}
                        ],
                    }
                    for output_name in sorted(output_names)
                ],
            },
            sort_keys=False,
        )
    )


def test_california_bhst_exact_mappings_match_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert len(output_names) == EXPECTED_OUTPUT_COUNT
    assert set(_module_mappings()) == output_names


def test_california_bhst_has_four_comparable_and_25_explicit_p4_records() -> None:
    mappings = _module_mappings()

    assert len(mappings) == EXPECTED_OUTPUT_COUNT
    assert sum(mapping.comparable for mapping in mappings.values()) == 4
    assert sum(
        mapping.mapping_type == "not_comparable"
        and mapping.candidate_priority == "P4"
        for mapping in mappings.values()
    ) == 25
    for output_name, mapping in mappings.items():
        assert mapping.match_type == "exact", output_name
        assert mapping.legal_id == f"{MODULE}#{output_name}", output_name
        assert mapping.program == "tax", output_name
        if not mapping.comparable:
            assert mapping.rationale


def test_california_bhst_uses_only_exact_parameter_and_variable_targets() -> None:
    mappings = _module_mappings()

    for output_name, (
        parameter,
        key_path,
        comparison,
    ) in EXPECTED_PARAMETER_VALUES.items():
        mapping = mappings[output_name]
        assert mapping.mapping_type == "parameter_value"
        assert mapping.policyengine_parameter == parameter
        assert mapping.parameter_key_path == key_path
        assert mapping.period == "year"
        assert mapping.comparison == comparison
    assert (
        mappings["ca_pit_pilot_behavioral_health_services_tax_threshold"].unit
        == "USD"
    )

    for output_name, variable in EXPECTED_DIRECT_VARIABLES.items():
        mapping = mappings[output_name]
        assert mapping.mapping_type == "direct_variable"
        assert mapping.policyengine_variable == variable
        assert (
            mapping.entity,
            mapping.period,
            mapping.unit,
            mapping.comparison,
        ) == ("tax_unit", "year", "USD", "money")


def test_california_exact_records_override_broad_state_p4_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#ca_pit_pilot_behavioral_health_services_tax",
        country="us",
    )
    fallback = registry.mapping_for_legal_id(
        f"{MODULE}#future_unmapped_output",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert fallback is not None
    assert fallback.legal_id == "us-ca:"
    assert fallback.match_type == "prefix"
    assert fallback.mapping_type == "not_comparable"
    assert fallback.candidate_priority == "P4"


@pytest.mark.parametrize("program", [None, "tax"])
def test_california_bhst_module_remains_in_coverage(
    tmp_path: Path,
    program: str | None,
) -> None:
    mappings = _module_mappings()
    rulespec_root = tmp_path / "rulespec-us"
    _write_synthetic_module(rulespec_root, set(mappings))

    report = build_policyengine_coverage_report(rulespec_root, program=program)
    items = [
        item
        for item in report["items"]
        if item["legal_id"].startswith(f"{MODULE}#")
    ]

    assert len(items) == EXPECTED_OUTPUT_COUNT
    assert {item["program"] for item in items} == {"tax"}
    assert sum(item["status"] == "comparable" for item in items) == 4
    assert sum(item["status"] == "known_not_comparable" for item in items) == 25
