"""Exact oracle-registry contract for Mississippi Code section 27-7-5."""

import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ms:policies/income_tax/2026_section_27_7_5_schedule"
RULESPEC_RELATIVE_PATH = Path(
    "us-ms/policies/income_tax/2026_section_27_7_5_schedule.yaml"
)
EXPECTED_OUTPUTS = {
    "ms_pit_2026_zero_tax_ceiling",
    "ms_pit_2026_rate",
    "ms_pit_2026_schedule_taxable_income",
    "ms_pit_2026_section_27_7_5_schedule_tax",
}


def _mapping(rule: str):
    registry = load_policyengine_registry()
    mapping = registry.mapping_for_legal_id(f"{MODULE}#{rule}", country="us")
    assert mapping is not None
    assert mapping.match_type == "exact"
    return mapping


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


def test_ms_2026_exact_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    payload = yaml.safe_load(rulespec_path.read_text())
    rule_names = {
        str(rule["name"])
        for rule in payload["rules"]
        if isinstance(rule, dict) and rule.get("name")
    }
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    mapped_names = {
        legal_id.removeprefix(prefix)
        for legal_id in registry.mappings_by_legal_id
        if legal_id.startswith(prefix)
    }

    assert rule_names == EXPECTED_OUTPUTS
    assert mapped_names == EXPECTED_OUTPUTS


def test_ms_2026_parameters_are_exact_policyengine_scale_entries() -> None:
    expected = {
        "ms_pit_2026_zero_tax_ceiling": (("thresholds", 1), "money"),
        "ms_pit_2026_rate": (("rates", 1), "rate"),
    }
    for rule, (key_path, comparison) in expected.items():
        mapping = _mapping(rule)
        assert mapping.mapping_type == "parameter_value"
        assert mapping.policyengine_parameter == "gov.states.ms.tax.income.rate"
        assert mapping.parameter_key_path == key_path
        assert mapping.period == "year"
        assert mapping.comparison == comparison


def test_ms_2026_person_boundary_is_p4_and_schedule_has_exact_target() -> None:
    taxable_income = _mapping("ms_pit_2026_schedule_taxable_income")
    schedule_tax = _mapping("ms_pit_2026_section_27_7_5_schedule_tax")

    assert taxable_income.mapping_type == "not_comparable"
    assert taxable_income.candidate_priority == "P4"
    assert taxable_income.policyengine_variable is None
    assert schedule_tax.mapping_type == "direct_variable"
    assert schedule_tax.policyengine_variable == "ms_income_tax_before_credits_joint"
    assert (
        schedule_tax.entity,
        schedule_tax.period,
        schedule_tax.unit,
        schedule_tax.comparison,
    ) == ("person", "year", "USD", "money")


def test_ms_2026_exact_records_precede_the_broad_state_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#ms_pit_2026_section_27_7_5_schedule_tax",
        country="us",
    )
    broad_fallback = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert broad_fallback is not None
    assert broad_fallback.match_type == "prefix"
    assert broad_fallback.mapping_type == "not_comparable"
    assert broad_fallback.candidate_priority == "P4"
