import json
import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry
from scripts.emit_populace_campaign_artifacts import project_state


MODULE = "us-ok:policies/income_tax/pilot_liability_pipeline"
LIABILITY = "ok_pit_pilot_income_tax_liability"
TARGET = "ok_income_tax_before_credits"
INPUTS = {
    "ok_pit_pilot_state_taxable_income",
    "ok_pit_pilot_filing_status_uses_wide_schedule",
}
RULESPEC_RELATIVE_PATH = Path("us-ok/policies/income_tax/pilot_liability_pipeline.yaml")
FALLBACK_RATIONALE = (
    "PolicyEngine-US does not model OK agency policy manuals or state "
    "regulations at output granularity; comparable state outputs carry exact "
    "mappings which take precedence over this prefix."
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _rulespec_path() -> Path | None:
    candidates = [
        REPO_ROOT.parent / "rulespec-us" / RULESPEC_RELATIVE_PATH,
        REPO_ROOT / ".rulespec-us" / RULESPEC_RELATIVE_PATH,
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
                        "versions": [{"effective_from": "2026-01-01", "formula": "0"}],
                    }
                ],
            },
            sort_keys=False,
        )
    )


def _campaign() -> dict:
    return {
        "generated_at": "2026-07-25T12:00:00Z",
        "run_kind": "manual",
        "dataset_identity": {
            "source": "pinned",
            "revision": "populace-us-test",
            "sha256": "3" * 12,
            "built_with": "1.729.0",
            "country": "us",
        },
        "runtime_provenance": {
            "rulespec": {
                "repository": "TheAxiomFoundation/rulespec-us",
                "commit": "1" * 40,
                "working_tree": "clean",
            },
            "axiom_engine": {
                "repository": "TheAxiomFoundation/axiom-rules-engine",
                "commit": "2" * 40,
                "executable_sha256": "4" * 64,
                "working_tree": "clean",
            },
            "packages": {
                "policyengine": "4.18.9",
                "policyengine-us": "1.752.2",
            },
        },
    }


def test_oklahoma_canonical_module_has_reviewed_inventory() -> None:
    path = _rulespec_path()
    if path is None:
        pytest.skip("rulespec-us checkout is not available")

    payload = yaml.safe_load(path.read_text())
    assert [rule["name"] for rule in payload["rules"]] == [
        "ok_pit_pilot_second_bracket_rate",
        "ok_pit_pilot_third_bracket_rate",
        "ok_pit_pilot_top_bracket_rate",
        "ok_pit_pilot_other_zero_bracket_ceiling",
        "ok_pit_pilot_other_second_bracket_width",
        "ok_pit_pilot_other_third_bracket_width",
        "ok_pit_pilot_wide_zero_bracket_ceiling",
        "ok_pit_pilot_wide_second_bracket_width",
        "ok_pit_pilot_wide_third_bracket_width",
        "ok_pit_pilot_taxable_income",
        "ok_pit_pilot_schedule_tax",
        LIABILITY,
    ]
    assert {slot["name"] for slot in payload["inputs"]} == INPUTS


def test_oklahoma_has_exactly_one_direct_pilot_mapping() -> None:
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
    assert "completed-return boundary" in mapping.rationale
    assert "before credits" in mapping.rationale


def test_oklahoma_exact_mapping_precedes_unchanged_fallback() -> None:
    registry = load_policyengine_registry()

    exact = registry.mapping_for_legal_id(
        f"{MODULE}#{LIABILITY}",
        country="us",
    )
    assert exact is not None
    assert exact.mapping_type == "direct_variable"
    assert exact.policyengine_variable == TARGET

    for output in (
        "ok_pit_pilot_taxable_income",
        "ok_pit_pilot_schedule_tax",
        "input.ok_pit_pilot_state_taxable_income",
        "input.ok_pit_pilot_filing_status_uses_wide_schedule",
        "ok_pit_pilot_final_annual_liability",
    ):
        broad = registry.mapping_for_legal_id(
            f"{MODULE}#{output}",
            country="us",
        )
        assert broad is not None
        assert broad.legal_id == "us-ok:"
        assert broad.match_type == "prefix"
        assert broad.mapping_type == "not_comparable"
        assert broad.candidate_priority == "P4"
        assert broad.rationale == FALLBACK_RATIONALE


@pytest.mark.parametrize("program", [None, "tax"])
def test_oklahoma_liability_is_comparable_in_coverage(
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
        item for item in report["items"] if item["legal_id"] == f"{MODULE}#{LIABILITY}"
    ]

    assert len(items) == 1
    assert items[0]["program"] == "tax"
    assert items[0]["status"] == "comparable"
    assert items[0]["mapping_type"] == "direct_variable"
    assert items[0]["policyengine_variable"] == TARGET


def test_oklahoma_mapping_mirrors_campaign_contract() -> None:
    concept_mappings = yaml.safe_load(
        (REPO_ROOT / "axiom_oracles/config/concept_mappings.yaml").read_text()
    )
    concept = f"{MODULE}#{LIABILITY}"
    assert concept_mappings["concepts"][concept]["targets"]["policyengine"] == TARGET

    contract = yaml.safe_load(
        (REPO_ROOT / "axiom_oracles/data/state_income_tax_populace.yaml").read_text()
    )
    jurisdiction = next(
        item for item in contract["jurisdictions"] if item["state"] == "OK"
    )
    assert jurisdiction["program"] == MODULE
    assert jurisdiction["output"] == concept
    assert jurisdiction["policyengine"] == {
        "target": TARGET,
        "tolerance": 0.01,
        "relative_tolerance": 0.0000001,
    }
    assert jurisdiction["status"] == "ready"
    assert {
        slot["slot"].split("#input.", 1)[1] for slot in jurisdiction["inputs"]
    } == INPUTS


def test_committed_oklahoma_populace_summary_is_bounded_and_exact() -> None:
    concept = f"{MODULE}#{LIABILITY}"
    campaign = json.loads(
        (REPO_ROOT / "reports/state-tax-populace-campaign-2026-07-23.json").read_text()
    )
    state = campaign["comparison"]["states"]["OK"]
    assert state["compared_count"] == 1_292
    assert state["mismatch_count"] == 0
    assert state["max_absolute_difference"] == 0.46000000089406967
    assert state["max_relative_difference"] == 5.692069032073562e-08
    assert state["tolerance"] == 0.01
    assert state["relative_tolerance"] == 1e-07
    assert state["output"] == concept
    assert state["policyengine_target"] == TARGET

    projected = project_state("OK", state, _campaign(), "campaign.json")
    assert projected["summary"] == {
        "comparison_count": 1_292,
        "match_count": 1_292,
        "match_rate": 100.0,
        "mismatch_count": 0,
    }
    dashboard = json.loads(
        (
            REPO_ROOT
            / "dashboard/public/data/axiom-policyengine-ok-income-tax-populace.json"
        ).read_text()
    )
    assert (
        dashboard["provenance"]["campaign_report"]
        == "state-tax-populace-campaign-2026-07-23.json"
    )
    assert dashboard["summary"] == projected["summary"]
    assert dashboard["aggregates"][0]["description"] == projected["aggregates"][0][
        "description"
    ]
    description = projected["aggregates"][0]["description"]
    assert "tax-year-2026 individual income tax before credits" in description
    assert "caller-supplied completed Oklahoma taxable income" in description
    assert "credits, payments, and final annual liability" in description
