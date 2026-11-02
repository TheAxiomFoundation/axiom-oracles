import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-mi:policies/income_tax/e2e_resident_liability_pipeline"
RULESPEC_RELATIVE_PATH = Path(
    "us-mi/policies/income_tax/e2e_resident_liability_pipeline.yaml"
)
EXPECTED_OUTPUTS = frozenset(
    {
        "mi_pit_e2e_complete_liability_source_hold_applies",
        "mi_pit_e2e_credit_surface_source_hold_applies",
        "mi_pit_e2e_deduction_and_exemption_source_hold_applies",
        "mi_pit_e2e_deductions_and_exemptions",
        "mi_pit_e2e_fail_closed_sentinel",
        "mi_pit_e2e_income_base_source_hold_applies",
        "mi_pit_e2e_input_domain_is_valid",
        "mi_pit_e2e_net_income",
        "mi_pit_e2e_net_income_tax_liability_before_payments",
        "mi_pit_e2e_refundable_credits",
        "mi_pit_e2e_tax_after_nonrefundable_credits",
        "mi_pit_e2e_tax_and_surtax_source_hold_applies",
        "mi_pit_e2e_tax_before_credits_including_surtaxes",
        "mi_pit_e2e_taxable_income",
    }
)


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


def _write_synthetic_module(root: Path) -> None:
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
                        "versions": [{"effective_from": "2026-01-01", "formula": "0"}],
                    }
                    for output_name in sorted(EXPECTED_OUTPUTS)
                ],
            },
            sort_keys=False,
        )
    )


def test_michigan_2026_exact_mappings_match_expected_output_set() -> None:
    assert len(EXPECTED_OUTPUTS) == 14
    assert set(_module_mappings()) == EXPECTED_OUTPUTS


def test_michigan_2026_exact_mappings_match_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert output_names == EXPECTED_OUTPUTS
    assert set(_module_mappings()) == output_names


def test_michigan_2026_bounded_outputs_use_exact_tax_classifications() -> None:
    mappings = _module_mappings()

    for output_name, mapping in mappings.items():
        assert mapping.match_type == "exact", output_name
        assert mapping.legal_id == f"{MODULE}#{output_name}", output_name
        assert mapping.program == "tax", output_name
        assert mapping.mapping_type == "not_comparable", output_name
        assert mapping.candidate_priority == "P4", output_name
        assert mapping.rationale


@pytest.mark.parametrize("program", [None, "tax"])
def test_michigan_2026_bounded_outputs_remain_in_coverage(
    tmp_path: Path,
    program: str | None,
) -> None:
    rulespec_root = tmp_path / "rulespec-us"
    _write_synthetic_module(rulespec_root)

    report = build_policyengine_coverage_report(rulespec_root, program=program)
    items = [
        item
        for item in report["items"]
        if item["legal_id"].startswith(f"{MODULE}#")
    ]

    assert len(items) == len(EXPECTED_OUTPUTS)
    assert {item["legal_id"].removeprefix(f"{MODULE}#") for item in items} == (
        EXPECTED_OUTPUTS
    )
    assert {item["program"] for item in items} == {"tax"}
    assert {item["status"] for item in items} == {"known_not_comparable"}
    assert {item["mapping_type"] for item in items} == {"not_comparable"}
