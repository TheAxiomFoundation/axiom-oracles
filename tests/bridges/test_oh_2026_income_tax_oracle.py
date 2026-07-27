"""Exact oracle-registry contract for Ohio's bounded TY2026 schedule."""

import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-oh:policies/income_tax/pilot_liability_pipeline"
RULESPEC_RELATIVE_PATH = Path(
    "us-oh/policies/income_tax/pilot_liability_pipeline.yaml"
)
EXPECTED_OUTPUTS = {
    "oh_pit_pilot_nonbusiness_taxable_income_construction_source_hold_applies",
    "oh_pit_pilot_business_income_and_excess_exemption_source_hold_applies",
    "oh_pit_pilot_credit_surface_source_hold_applies",
    "oh_pit_pilot_final_return_ordering_source_hold_applies",
    "oh_pit_pilot_taxable_income",
    "oh_pit_pilot_schedule_tax",
    "oh_pit_pilot_income_tax_liability",
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


def test_oh_2026_exact_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    payload = yaml.safe_load(rulespec_path.read_text())
    output_names = {
        str(rule["name"])
        for rule in payload["rules"]
        if isinstance(rule, dict) and rule.get("name")
    }
    assert output_names == EXPECTED_OUTPUTS
    assert set(_module_mappings()) == EXPECTED_OUTPUTS


def test_oh_2026_schedule_uses_the_inclusive_threshold_derived_target() -> None:
    mappings = _module_mappings()
    for output_name in {
        "oh_pit_pilot_schedule_tax",
        "oh_pit_pilot_income_tax_liability",
    }:
        mapping = mappings[output_name]
        assert mapping.match_type == "exact"
        assert mapping.mapping_type == "derived_expression"
        assert (
            mapping.expression
            == "oh_income_tax_before_non_refundable_credits "
            "* (oh_taxable_income > 26050)"
        )
        assert (mapping.entity, mapping.period, mapping.unit, mapping.comparison) == (
            "tax_unit",
            "year",
            "USD",
            "money",
        )


def test_oh_2026_boundary_and_source_holds_are_explicit() -> None:
    mappings = _module_mappings()
    taxable = mappings["oh_pit_pilot_taxable_income"]
    assert taxable.mapping_type == "direct_variable"
    assert taxable.policyengine_variable == "oh_taxable_income"

    for output_name in EXPECTED_OUTPUTS - {
        "oh_pit_pilot_taxable_income",
        "oh_pit_pilot_schedule_tax",
        "oh_pit_pilot_income_tax_liability",
    }:
        mapping = mappings[output_name]
        assert mapping.mapping_type == "not_comparable"
        assert mapping.candidate_priority == "P4"


def test_oh_2026_exact_records_precede_the_broad_state_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#oh_pit_pilot_schedule_tax", country="us"
    )
    broad_fallback = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic", country="us"
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "derived_expression"
    assert broad_fallback is not None
    assert broad_fallback.match_type == "prefix"
    assert broad_fallback.mapping_type == "not_comparable"
    assert broad_fallback.candidate_priority == "P4"
