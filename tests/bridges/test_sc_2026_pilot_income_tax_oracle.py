import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-sc:policies/income_tax/pilot_liability_pipeline"
LIABILITY = "sc_pit_pilot_income_tax_liability"
INPUT = "sc_pit_pilot_state_taxable_income"
TARGET = "sc_income_tax_before_non_refundable_credits"
RULESPEC_RELATIVE_PATH = Path(
    "us-sc/policies/income_tax/pilot_liability_pipeline.yaml"
)
FALLBACK_RATIONALE = (
    "PolicyEngine-US does not model SC agency policy manuals or state "
    "regulations at output granularity; comparable state outputs carry exact "
    "mappings which take precedence over this prefix."
)


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
                        "name": LIABILITY,
                        "kind": "derived",
                        "versions": [
                            {"effective_from": "2026-01-01", "formula": "0"}
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )


def test_south_carolina_canonical_module_has_reviewed_inventory() -> None:
    path = _rulespec_path()
    if path is None:
        pytest.skip("rulespec-us checkout is not available")

    payload = yaml.safe_load(path.read_text())
    assert [rule["name"] for rule in payload["rules"]] == [
        "sc_pit_pilot_lower_bracket_rate",
        "sc_pit_pilot_upper_bracket_floor",
        "sc_pit_pilot_upper_bracket_rate",
        "sc_pit_pilot_upper_bracket_subtraction",
        "sc_pit_pilot_taxable_income",
        "sc_pit_pilot_schedule_tax",
        LIABILITY,
    ]
    assert [slot["name"] for slot in payload["inputs"]] == [INPUT]


def test_south_carolina_has_exactly_one_direct_pilot_mapping() -> None:
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    exact = {
        legal_id.removeprefix(prefix): mapping
        for legal_id, mapping in registry.mappings_by_legal_id.items()
        if legal_id.startswith(prefix)
    }

    assert set(exact) == {LIABILITY}
    mapping = exact[LIABILITY]
    assert mapping.match_type == "exact"
    assert mapping.mapping_type == "direct_variable"
    assert mapping.policyengine_variable == TARGET
    assert mapping.program == "tax"
    assert mapping.entity == "tax_unit"
    assert mapping.period == "year"
    assert mapping.unit == "USD"
    assert mapping.comparison == "money"
    assert mapping.candidate_priority is None
    assert "nonnegative" in mapping.rationale
    assert f"input.{INPUT}" not in exact


def test_south_carolina_exact_mapping_precedes_unchanged_fallback() -> None:
    registry = load_policyengine_registry()

    exact = registry.mapping_for_legal_id(
        f"{MODULE}#{LIABILITY}",
        country="us",
    )
    assert exact is not None
    assert exact.mapping_type == "direct_variable"
    assert exact.policyengine_variable == TARGET

    for output in (
        "sc_pit_pilot_taxable_income",
        "sc_pit_pilot_schedule_tax",
        "unmapped_diagnostic",
    ):
        broad = registry.mapping_for_legal_id(
            f"{MODULE}#{output}",
            country="us",
        )
        assert broad is not None
        assert broad.legal_id == "us-sc:"
        assert broad.match_type == "prefix"
        assert broad.mapping_type == "not_comparable"
        assert broad.candidate_priority == "P4"
        assert broad.rationale == FALLBACK_RATIONALE


@pytest.mark.parametrize("program", [None, "tax"])
def test_south_carolina_liability_is_comparable_in_coverage(
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
        if item["legal_id"] == f"{MODULE}#{LIABILITY}"
    ]

    assert len(items) == 1
    assert items[0]["program"] == "tax"
    assert items[0]["status"] == "comparable"
    assert items[0]["mapping_type"] == "direct_variable"
    assert items[0]["policyengine_variable"] == TARGET
