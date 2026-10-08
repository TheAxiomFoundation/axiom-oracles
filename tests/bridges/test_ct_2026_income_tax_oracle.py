import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ct:policies/income_tax/2026_resident_liability_source_hold"
RULESPEC_RELATIVE_PATH = Path(
    "us-ct/policies/income_tax/2026_resident_liability_source_hold.yaml"
)
EXPECTED_OUTPUT_COUNT = 17
CANONICAL_MODULE = (
    "us-ct:policies/income_tax/"
    "2026_resident_ordinary_tax_before_personal_credit"
)
CANONICAL_RULESPEC_RELATIVE_PATH = Path(
    "us-ct/policies/income_tax/"
    "2026_resident_ordinary_tax_before_personal_credit.yaml"
)
CANONICAL_OUTPUT_COUNT = 45


def _module_mappings():
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    return {
        legal_id.removeprefix(prefix): mapping
        for legal_id, mapping in registry.mappings_by_legal_id.items()
        if legal_id.startswith(prefix)
    }


def _canonical_module_mappings():
    registry = load_policyengine_registry()
    prefix = f"{CANONICAL_MODULE}#"
    return {
        legal_id.removeprefix(prefix): mapping
        for legal_id, mapping in registry.mappings_by_legal_id.items()
        if legal_id.startswith(prefix)
    }


def _configured_rulespec_path(relative_path: Path) -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root.parent / "rulespec-us" / relative_path,
        repo_root / ".rulespec-us" / relative_path,
    ]
    configured_root = os.environ.get("AXIOM_RULESPEC_ROOT")
    if configured_root:
        configured = Path(configured_root).expanduser()
        candidates = [
            configured / relative_path,
            configured / "rulespec-us" / relative_path,
            *candidates,
        ]
    return next((path for path in candidates if path.is_file()), None)


def _rulespec_path() -> Path | None:
    return _configured_rulespec_path(RULESPEC_RELATIVE_PATH)


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


def test_ct_2026_exact_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert len(output_names) == EXPECTED_OUTPUT_COUNT
    assert set(_module_mappings()) == output_names


def test_ct_2026_core_uses_exact_tax_not_comparable_mappings() -> None:
    mappings = _module_mappings()
    assert len(mappings) == EXPECTED_OUTPUT_COUNT

    for output_name, mapping in mappings.items():
        assert mapping.match_type == "exact", output_name
        assert mapping.legal_id == f"{MODULE}#{output_name}", output_name
        assert mapping.program == "tax", output_name
        assert mapping.mapping_type == "not_comparable", output_name
        assert mapping.rationale


def test_ct_2026_canonical_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _configured_rulespec_path(CANONICAL_RULESPEC_RELATIVE_PATH)
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert len(output_names) == CANONICAL_OUTPUT_COUNT
    assert set(_canonical_module_mappings()) == output_names


def test_ct_2026_canonical_mapping_types_are_exact_and_complete() -> None:
    mappings = _canonical_module_mappings()
    assert len(mappings) == CANONICAL_OUTPUT_COUNT
    assert {
        mapping.mapping_type for mapping in mappings.values()
    } == {
        "not_comparable",
        "parameter_value",
        "direct_variable",
        "derived_expression",
    }
    assert sum(
        mapping.mapping_type == "not_comparable"
        for mapping in mappings.values()
    ) == 3
    assert sum(
        mapping.mapping_type == "parameter_value"
        for mapping in mappings.values()
    ) == 36
    assert sum(
        mapping.mapping_type == "direct_variable"
        for mapping in mappings.values()
    ) == 4
    assert sum(
        mapping.mapping_type == "derived_expression"
        for mapping in mappings.values()
    ) == 2
    assert all(mapping.match_type == "exact" for mapping in mappings.values())
    assert all(mapping.program == "tax" for mapping in mappings.values())


def test_ct_2026_canonical_public_total_uses_exact_pe_recovery() -> None:
    mapping = _canonical_module_mappings()[
        "ct_pit_2026_resident_ordinary_tax_before_personal_credit"
    ]
    assert mapping.mapping_type == "derived_expression"
    assert mapping.expression == (
        "ct_income_tax_after_personal_credits / "
        "(1 - ct_personal_credit_rate)"
    )


@pytest.mark.parametrize("program", [None, "tax"])
def test_ct_2026_core_remains_in_unfiltered_and_tax_coverage(
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
    assert {item["status"] for item in items} == {"known_not_comparable"}
    assert {item["mapping_type"] for item in items} == {"not_comparable"}
