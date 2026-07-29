import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ny:policies/income_tax/pilot_liability_pipeline"
RULESPEC_RELATIVE_PATH = Path(
    "us-ny/policies/income_tax/pilot_liability_pipeline.yaml"
)
EXPECTED_OUTPUT_COUNT = 38
DIRECT_VARIABLES = {
    "ny_pit_pilot_taxable_income": "ny_taxable_income",
    "ny_pit_pilot_main_income_tax": "ny_main_income_tax",
}
STATUS_PARAMETERS = {
    "joint_or_surviving": "gov.states.ny.tax.income.main.joint",
    "head_of_household": "gov.states.ny.tax.income.main.head_of_household",
    "single_or_separate": "gov.states.ny.tax.income.main.single",
}
ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
)
PARAMETER_OUTPUTS = {
    f"ny_pit_pilot_{status}_{ordinal}_upper_bound": (
        parameter,
        ("thresholds", index),
    )
    for status, parameter in STATUS_PARAMETERS.items()
    for index, ordinal in enumerate(ORDINALS, start=1)
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


def test_ny_2026_exact_mappings_match_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert len(output_names) == EXPECTED_OUTPUT_COUNT
    assert set(_module_mappings()) == output_names


def test_ny_2026_mapping_boundaries_are_truthful_and_exact() -> None:
    mappings = _module_mappings()
    assert len(mappings) == EXPECTED_OUTPUT_COUNT

    for output_name, mapping in mappings.items():
        assert mapping.match_type == "exact", output_name
        assert mapping.program == "tax", output_name
        if output_name in DIRECT_VARIABLES:
            assert mapping.mapping_type == "direct_variable", output_name
            assert mapping.policyengine_variable == DIRECT_VARIABLES[output_name]
            assert mapping.entity == "tax_unit"
            assert mapping.period == "year"
            assert mapping.unit == "USD"
            assert mapping.comparison == "money"
            assert mapping.candidate_priority is None
        elif output_name in PARAMETER_OUTPUTS:
            parameter, key_path = PARAMETER_OUTPUTS[output_name]
            assert mapping.mapping_type == "parameter_value", output_name
            assert mapping.policyengine_parameter == parameter
            assert mapping.parameter_key_path == key_path
            assert mapping.period == "year"
            assert mapping.unit == "USD"
            assert mapping.comparison == "money"
            assert mapping.candidate_priority is None
        else:
            assert mapping.mapping_type == "not_comparable", output_name
            assert mapping.candidate_priority == "P4"
            assert mapping.rationale

    assert sum(item.comparable for item in mappings.values()) == 26
    assert sum(not item.comparable for item in mappings.values()) == 12


def test_ny_2026_exact_records_precede_broad_state_fallback() -> None:
    registry = load_policyengine_registry()

    exact = registry.mapping_for_legal_id(
        f"{MODULE}#ny_pit_pilot_main_income_tax",
        country="us",
    )
    broad = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert exact.policyengine_variable == "ny_main_income_tax"
    assert broad is not None
    assert broad.match_type == "prefix"
    assert broad.mapping_type == "not_comparable"
    assert broad.candidate_priority == "P4"


@pytest.mark.parametrize("program", [None, "tax"])
def test_ny_2026_main_schedule_remains_in_coverage(
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
    assert sum(item["status"] == "comparable" for item in items) == 26
    assert sum(item["status"] == "known_not_comparable" for item in items) == 12
