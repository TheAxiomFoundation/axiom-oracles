import os
from collections import Counter
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-sc:policies/income_tax/2026_full_year_resident_core"
RULESPEC_RELATIVE_PATH = Path(
    "us-sc/policies/income_tax/2026_full_year_resident_core.yaml"
)
EXPECTED_OUTPUT_COUNT = 60

DIRECT_VARIABLES = {
    "sc_pit_2026_candidate_sciad": "sc_sciad",
    "sc_pit_2026_candidate_net_capital_gain_deduction": (
        "sc_net_capital_gain_deduction"
    ),
}

PARAMETER_OUTPUTS = {
    "sc_pit_2026_lower_rate",
    "sc_pit_2026_upper_rate",
    "sc_pit_2026_upper_bracket_floor",
    "sc_pit_2026_net_capital_gain_deduction_rate",
    "sc_pit_2026_under_65_retirement_cap",
    "sc_pit_2026_age_65_threshold",
    "sc_pit_2026_sciad_single_or_separate_base",
    "sc_pit_2026_sciad_head_base",
    "sc_pit_2026_sciad_joint_or_surviving_base",
    "sc_pit_2026_sciad_single_or_separate_phaseout_start",
    "sc_pit_2026_sciad_head_phaseout_start",
    "sc_pit_2026_sciad_joint_or_surviving_phaseout_start",
    "sc_pit_2026_sciad_single_or_separate_phaseout_denominator",
    "sc_pit_2026_sciad_head_phaseout_denominator",
    "sc_pit_2026_sciad_joint_or_surviving_phaseout_denominator",
    "sc_pit_2026_two_wage_earner_rate",
    "sc_pit_2026_two_wage_earner_income_cap",
    "sc_pit_2026_eitc_match_rate",
    "sc_pit_2026_eitc_credit_cap",
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


def test_sc_2026_exact_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert len(output_names) == EXPECTED_OUTPUT_COUNT
    assert set(_module_mappings()) == output_names


def test_sc_2026_core_never_uses_the_generic_state_fallback() -> None:
    mappings = _module_mappings()
    assert len(mappings) == EXPECTED_OUTPUT_COUNT

    for output_name, mapping in mappings.items():
        assert mapping.match_type == "exact", output_name
        assert mapping.legal_id == f"{MODULE}#{output_name}", output_name
        assert mapping.program == "tax", output_name
        assert mapping.rationale
        assert "agency policy manuals or state regulations" not in mapping.rationale


def test_sc_2026_core_direct_and_parameter_surfaces_are_truthful() -> None:
    mappings = _module_mappings()

    assert {
        output_name: mapping.policyengine_variable
        for output_name, mapping in mappings.items()
        if mapping.mapping_type == "direct_variable"
    } == DIRECT_VARIABLES
    assert {
        output_name
        for output_name, mapping in mappings.items()
        if mapping.mapping_type == "parameter_value"
    } == PARAMETER_OUTPUTS
    assert all(
        mapping.mapping_type == "not_comparable"
        for output_name, mapping in mappings.items()
        if output_name not in set(DIRECT_VARIABLES) | PARAMETER_OUTPUTS
    )


def test_sc_2026_comparable_stages_are_the_exact_concept_registry_set() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load(
        (root / "axiom_oracles/config/concept_mappings.yaml").read_text()
    )
    concepts = payload["concepts"]
    module_concepts = {
        legal_id: concept
        for legal_id, concept in concepts.items()
        if legal_id.startswith(f"{MODULE}#")
    }

    assert set(module_concepts) == {
        f"{MODULE}#{output_name}" for output_name in DIRECT_VARIABLES
    }
    for output_name, policyengine_variable in DIRECT_VARIABLES.items():
        legal_id = f"{MODULE}#{output_name}"
        assert (
            module_concepts[legal_id]["targets"]["policyengine"]
            == policyengine_variable
        )
        assert module_concepts[legal_id]["targets"]["axiom"]["name"] == output_name


def test_sc_2026_core_remains_in_tax_filtered_coverage(tmp_path: Path) -> None:
    mappings = _module_mappings()
    rulespec_root = tmp_path / "rulespec-us"
    rulespec_path = rulespec_root / RULESPEC_RELATIVE_PATH
    rulespec_path.parent.mkdir(parents=True)
    rulespec_path.write_text(
        yaml.safe_dump(
            {
                "format": "rulespec/v1",
                "module": MODULE.split(":", 1)[1],
                "rules": [
                    {
                        "name": output_name,
                        "kind": (
                            "parameter"
                            if mapping.mapping_type == "parameter_value"
                            else "derived"
                        ),
                        "versions": [
                            {"effective_from": "2026-01-01", "formula": "0"}
                        ],
                    }
                    for output_name, mapping in sorted(mappings.items())
                ],
            },
            sort_keys=False,
        )
    )

    report = build_policyengine_coverage_report(rulespec_root, program="tax")
    items = [
        item
        for item in report["items"]
        if item["legal_id"].startswith(f"{MODULE}#")
    ]

    assert len(items) == EXPECTED_OUTPUT_COUNT
    assert {item["program"] for item in items} == {"tax"}
    assert Counter(item["status"] for item in items) == {
        "comparable": len(DIRECT_VARIABLES) + len(PARAMETER_OUTPUTS),
        "known_not_comparable": (
            EXPECTED_OUTPUT_COUNT - len(DIRECT_VARIABLES) - len(PARAMETER_OUTPUTS)
        ),
    }
