import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ar:policies/income_tax/2026_resident_liability_source_hold"
RULESPEC_RELATIVE_PATH = Path(
    "us-ar/policies/income_tax/2026_resident_liability_source_hold.yaml"
)
EXPECTED_OUTPUT_COUNT = 13


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


def test_ar_2026_exact_mappings_match_the_rulespec_output_set() -> None:
    rulespec_path = _rulespec_path()
    if rulespec_path is None:
        pytest.skip("rulespec-us checkout is not available")

    output_names = _rulespec_output_names(rulespec_path)
    assert len(output_names) == EXPECTED_OUTPUT_COUNT
    assert set(_module_mappings()) == output_names


def test_ar_2026_core_uses_exact_tax_not_comparable_mappings() -> None:
    mappings = _module_mappings()
    assert len(mappings) == EXPECTED_OUTPUT_COUNT

    for output_name, mapping in mappings.items():
        assert mapping.match_type == "exact", output_name
        assert mapping.legal_id == f"{MODULE}#{output_name}", output_name
        assert mapping.program == "tax", output_name
        assert mapping.mapping_type == "not_comparable", output_name
        assert mapping.rationale


@pytest.mark.parametrize("program", [None, "tax"])
def test_ar_2026_core_remains_in_unfiltered_and_tax_coverage(
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
