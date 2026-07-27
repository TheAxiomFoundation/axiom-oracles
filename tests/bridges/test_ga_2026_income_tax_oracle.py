import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = (
    "us-ga:policies/income_tax/2026_annual_tax_before_nonrefundable_credits"
)
RULESPEC_RELATIVE_PATH = Path(
    "us-ga/policies/income_tax/"
    "2026_annual_tax_before_nonrefundable_credits.yaml"
)
PRIVATE_OUTPUT = "ga_pit_2026_annual_input_is_nonnegative"
PUBLIC_OUTPUT = "ga_pit_2026_annual_tax_before_nonrefundable_credits"
EXPECTED_OUTPUTS = {PRIVATE_OUTPUT, PUBLIC_OUTPUT}


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
                        "versions": [
                            {"effective_from": "2026-01-01", "formula": "0"}
                        ],
                    }
                    for output_name in sorted(EXPECTED_OUTPUTS)
                ],
            },
            sort_keys=False,
        )
    )
    test_path = rulespec_path.with_name(rulespec_path.stem + ".test.yaml")
    test_path.write_text(
        yaml.safe_dump(
            [
                {
                    "name": f"case_{case_number}",
                    "output": {
                        f"{MODULE}#{output_name}": 0
                        for output_name in sorted(EXPECTED_OUTPUTS)
                    },
                }
                for case_number in range(8)
            ],
            sort_keys=False,
        )
    )


def test_ga_2026_exact_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    assert _rulespec_output_names(rulespec_path) == EXPECTED_OUTPUTS
    assert set(_module_mappings()) == EXPECTED_OUTPUTS


def test_ga_2026_exact_records_precede_the_broad_state_fallback() -> None:
    registry = load_policyengine_registry()
    private = registry.mapping_for_legal_id(
        f"{MODULE}#{PRIVATE_OUTPUT}",
        country="us",
    )
    public = registry.mapping_for_legal_id(
        f"{MODULE}#{PUBLIC_OUTPUT}",
        country="us",
    )
    broad_fallback = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )

    assert private is not None
    assert private.match_type == "exact"
    assert private.mapping_type == "not_comparable"
    assert private.candidate_priority == "P4"
    assert private.policyengine_variable is None

    assert public is not None
    assert public.match_type == "exact"
    assert public.mapping_type == "direct_variable"
    assert (
        public.policyengine_variable
        == "ga_income_tax_before_non_refundable_credits"
    )
    assert public.entity == "tax_unit"
    assert public.period == "year"
    assert public.unit == "USD"
    assert public.comparison == "money"
    assert public.candidate_priority is None

    assert broad_fallback is not None
    assert broad_fallback.match_type == "prefix"
    assert broad_fallback.mapping_type == "not_comparable"
    assert broad_fallback.candidate_priority == "P4"


@pytest.mark.parametrize("program", [None, "tax"])
def test_ga_2026_coverage_is_exact_and_tested_eight_times(
    tmp_path: Path,
    program: str | None,
) -> None:
    rulespec_root = tmp_path / "rulespec-us"
    _write_synthetic_module(rulespec_root)

    report = build_policyengine_coverage_report(rulespec_root, program=program)
    items = {
        item["legal_id"].removeprefix(f"{MODULE}#"): item
        for item in report["items"]
        if item["legal_id"].startswith(f"{MODULE}#")
    }

    assert set(items) == EXPECTED_OUTPUTS
    assert items[PRIVATE_OUTPUT]["status"] == "known_not_comparable"
    assert items[PRIVATE_OUTPUT]["mapping_type"] == "not_comparable"
    assert items[PUBLIC_OUTPUT]["status"] == "comparable"
    assert items[PUBLIC_OUTPUT]["mapping_type"] == "direct_variable"
    assert {item["test_output_count"] for item in items.values()} == {8}
    assert all(item["tested"] for item in items.values())
