import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


# Canonical completed-return boundary module reviewed separately from resident_core.
MODULE = "us-il:policies/income_tax/pilot_liability_pipeline"
RULESPEC_RELATIVE_PATH = Path(
    "us-il/policies/income_tax/pilot_liability_pipeline.yaml"
)
DIRECT_VARIABLES = {
    "il_pit_pilot_taxable_income": "il_taxable_income",
    "il_pit_pilot_income_tax_liability": (
        "il_income_tax_before_non_refundable_credits"
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


def test_il_2026_exact_mappings_match_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    assert _rulespec_output_names(rulespec_path) == set(DIRECT_VARIABLES)
    assert set(_module_mappings()) == set(DIRECT_VARIABLES)


def test_il_2026_positive_recapture_branch_is_fixture_covered() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    fixture_path = rulespec_path.with_name(
        f"{rulespec_path.stem}.test.yaml"
    )
    cases = yaml.safe_load(fixture_path.read_text())
    case = next(
        item
        for item in cases
        if item["name"] == "positive_taxable_income_with_recapture"
    )
    input_prefix = f"{MODULE}#input."

    assert case["input"][
        f"{input_prefix}il_pit_pilot_state_taxable_income"
    ] == 100_000
    assert case["input"][
        f"{input_prefix}il_pit_pilot_recapture_of_investment_credit"
    ] == 125
    assert case["output"][
        f"{MODULE}#il_pit_pilot_income_tax_liability"
    ] == 5_075


def test_il_2026_mapping_boundaries_are_truthful_and_exact() -> None:
    mappings = _module_mappings()

    assert set(mappings) == set(DIRECT_VARIABLES)
    for output_name, variable in DIRECT_VARIABLES.items():
        mapping = mappings[output_name]
        assert mapping.match_type == "exact"
        assert mapping.program == "tax"
        assert mapping.mapping_type == "direct_variable"
        assert mapping.policyengine_variable == variable
        assert mapping.entity == "tax_unit"
        assert mapping.period == "year"
        assert mapping.unit == "USD"
        assert mapping.comparison == "money"
        assert mapping.candidate_priority is None


def test_il_2026_exact_records_precede_broad_state_fallback() -> None:
    registry = load_policyengine_registry()

    exact = registry.mapping_for_legal_id(
        f"{MODULE}#il_pit_pilot_income_tax_liability",
        country="us",
    )
    broad = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert exact.policyengine_variable == (
        "il_income_tax_before_non_refundable_credits"
    )
    assert broad is not None
    assert broad.legal_id == "us-il:"
    assert broad.match_type == "prefix"
    assert broad.mapping_type == "not_comparable"
    assert broad.candidate_priority == "P4"


@pytest.mark.parametrize("program", [None, "tax"])
def test_il_2026_annual_before_credit_surface_remains_in_coverage(
    tmp_path: Path,
    program: str | None,
) -> None:
    rulespec_root = tmp_path / "rulespec-us"
    _write_synthetic_module(rulespec_root, set(DIRECT_VARIABLES))

    report = build_policyengine_coverage_report(rulespec_root, program=program)
    items = [
        item
        for item in report["items"]
        if item["legal_id"].startswith(f"{MODULE}#")
    ]

    assert len(items) == 2
    assert {item["program"] for item in items} == {"tax"}
    assert {item["status"] for item in items} == {"comparable"}
    assert {
        item["rule_name"]: item["policyengine_variable"] for item in items
    } == DIRECT_VARIABLES
