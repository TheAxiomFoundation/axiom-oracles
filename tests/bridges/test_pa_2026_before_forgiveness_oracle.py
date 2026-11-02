import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-pa:policies/income_tax/pilot_liability_pipeline"
INPUT = "pa_pit_pilot_state_taxable_income"
DIRECT_VARIABLES = {
    "pa_pit_pilot_taxable_income": "pa_adjusted_taxable_income",
    "pa_pit_pilot_income_tax_liability": "pa_income_tax_before_forgiveness",
}
RULESPEC_RELATIVE_PATH = Path(
    "us-pa/policies/income_tax/pilot_liability_pipeline.yaml"
)
FALLBACK_RATIONALE = (
    "PolicyEngine-US does not model PA agency policy manuals or state "
    "regulations at output granularity; comparable state outputs carry exact "
    "mappings which take precedence over this prefix."
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


def _write_synthetic_module(root: Path) -> None:
    path = root / RULESPEC_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "format": "rulespec/v1",
                "module": MODULE.split(":", 1)[1],
                "rules": [
                    {
                        "name": output,
                        "kind": "derived",
                        "versions": [
                            {"effective_from": "2026-01-01", "formula": "0"}
                        ],
                    }
                    for output in DIRECT_VARIABLES
                ],
            },
            sort_keys=False,
        )
    )


def test_pennsylvania_canonical_module_has_two_outputs_and_one_input() -> None:
    path = _rulespec_path()
    if path is None:
        pytest.skip("rulespec-us checkout is not available")

    payload = yaml.safe_load(path.read_text())
    assert [rule["name"] for rule in payload["rules"]] == list(DIRECT_VARIABLES)
    assert [slot["name"] for slot in payload["inputs"]] == [INPUT]


def test_pennsylvania_has_exactly_two_direct_mappings_and_no_input_mapping() -> None:
    mappings = _module_mappings()

    assert set(mappings) == set(DIRECT_VARIABLES)
    for output, variable in DIRECT_VARIABLES.items():
        mapping = mappings[output]
        assert mapping.match_type == "exact"
        assert mapping.mapping_type == "direct_variable"
        assert mapping.policyengine_variable == variable
        assert mapping.program == "tax"
        assert mapping.entity == "tax_unit"
        assert mapping.period == "year"
        assert mapping.unit == "USD"
        assert mapping.comparison == "money"
        assert mapping.candidate_priority is None
        assert "nonnegative" in mapping.rationale
    assert f"input.{INPUT}" not in mappings


def test_pennsylvania_exact_mappings_precede_reviewed_broad_fallback() -> None:
    registry = load_policyengine_registry()

    for output, variable in DIRECT_VARIABLES.items():
        exact = registry.mapping_for_legal_id(
            f"{MODULE}#{output}",
            country="us",
        )
        assert exact is not None
        assert exact.match_type == "exact"
        assert exact.mapping_type == "direct_variable"
        assert exact.policyengine_variable == variable

    broad = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )
    assert broad is not None
    assert broad.legal_id == "us-pa:"
    assert broad.match_type == "prefix"
    assert broad.mapping_type == "not_comparable"
    assert broad.candidate_priority == "P4"
    assert broad.rationale == FALLBACK_RATIONALE


@pytest.mark.parametrize("program", [None, "tax"])
def test_pennsylvania_canonical_outputs_are_comparable_in_coverage(
    tmp_path: Path,
    program: str | None,
) -> None:
    rulespec_root = tmp_path / "rulespec-us"
    _write_synthetic_module(rulespec_root)

    report = build_policyengine_coverage_report(
        rulespec_root,
        program=program,
    )
    items = [
        item
        for item in report["items"]
        if item["legal_id"].startswith(f"{MODULE}#")
    ]

    assert len(items) == 2
    assert {item["rule_name"] for item in items} == set(DIRECT_VARIABLES)
    assert {item["program"] for item in items} == {"tax"}
    assert {item["status"] for item in items} == {"comparable"}
    assert {item["mapping_type"] for item in items} == {"direct_variable"}
    assert {
        item["rule_name"]: item["policyengine_variable"] for item in items
    } == DIRECT_VARIABLES
