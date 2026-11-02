import hashlib
import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-mt:policies/income_tax/pilot_liability_pipeline"
LIABILITY = "mt_pit_pilot_income_tax_liability"
TARGET = "mt_income_tax_before_non_refundable_credits_joint"
INPUTS = {
    "mt_pit_pilot_state_taxable_income",
    "mt_pit_pilot_section_1222_net_long_term_capital_gain",
    "mt_pit_pilot_filing_status_joint_or_surviving_spouse",
    "mt_pit_pilot_filing_status_head_of_household",
}
RULESPEC_RELATIVE_PATH = Path(
    "us-mt/policies/income_tax/pilot_liability_pipeline.yaml"
)
RULESPEC_SHA256 = (
    "3a99ecb11dad12dda75499431d6d354522537b404dbeb6e3f2b8c9c2dd1e76ff"
)
FALLBACK_RATIONALE = (
    "PolicyEngine-US does not model every Montana statute, agency policy "
    "manual, or state regulation at output granularity; independently "
    "reviewed comparable outputs carry exact mappings which take precedence "
    "over this jurisdiction-wide fallback."
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
                        "versions": [
                            {"effective_from": "2026-01-01", "formula": "0"}
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )


def test_montana_canonical_module_has_reviewed_inventory() -> None:
    path = _rulespec_path()
    if path is None:
        pytest.skip("rulespec-us checkout is not available")

    payload = yaml.safe_load(path.read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == RULESPEC_SHA256
    assert [rule["name"] for rule in payload["rules"]] == [
        "mt_pit_pilot_ordinary_lower_rate",
        "mt_pit_pilot_ordinary_upper_rate",
        "mt_pit_pilot_capital_gain_lower_rate",
        "mt_pit_pilot_capital_gain_upper_rate",
        "mt_pit_pilot_single_or_separate_threshold",
        "mt_pit_pilot_head_of_household_threshold",
        "mt_pit_pilot_joint_or_surviving_spouse_threshold",
        "mt_pit_pilot_taxable_income",
        "mt_pit_pilot_net_long_term_capital_gain",
        "mt_pit_pilot_nonqualified_taxable_income",
        "mt_pit_pilot_filing_status_threshold",
        "mt_pit_pilot_ordinary_income_tax",
        "mt_pit_pilot_capital_gain_lower_band",
        "mt_pit_pilot_capital_gains_tax",
        LIABILITY,
    ]
    assert {slot["name"] for slot in payload["inputs"]} == INPUTS


def test_montana_has_exactly_one_direct_pilot_mapping() -> None:
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
    assert "before nonrefundable credits" in mapping.rationale


def test_montana_exact_mapping_precedes_jurisdiction_fallback() -> None:
    registry = load_policyengine_registry()

    exact = registry.mapping_for_legal_id(
        f"{MODULE}#{LIABILITY}",
        country="us",
    )
    assert exact is not None
    assert exact.mapping_type == "direct_variable"
    assert exact.policyengine_variable == TARGET

    for output in (
        "mt_pit_pilot_taxable_income",
        "mt_pit_pilot_capital_gains_tax",
        "input.mt_pit_pilot_state_taxable_income",
        "mt_pit_pilot_final_annual_liability",
    ):
        broad = registry.mapping_for_legal_id(
            f"{MODULE}#{output}",
            country="us",
        )
        assert broad is not None
        assert broad.legal_id == "us-mt:"
        assert broad.match_type == "prefix"
        assert broad.mapping_type == "not_comparable"
        assert broad.candidate_priority == "P4"
        assert broad.rationale == FALLBACK_RATIONALE


@pytest.mark.parametrize("program", [None, "tax"])
def test_montana_liability_is_comparable_in_coverage(
    tmp_path: Path,
    program: str | None,
) -> None:
    rulespec_root = tmp_path / "rulespec-us"
    _write_synthetic_module(rulespec_root)

    report = build_policyengine_coverage_report(
        rulespec_root,
        program=program,
    )
    item = next(
        item
        for item in report["items"]
        if item["legal_id"] == f"{MODULE}#{LIABILITY}"
    )
    assert item["program"] == "tax"
    assert item["status"] == "comparable"
    assert item["mapping_type"] == "direct_variable"
    assert item["policyengine_variable"] == TARGET


def test_montana_mapping_mirrors_campaign_contract_and_legacy_registry() -> None:
    concept = f"{MODULE}#{LIABILITY}"
    legacy = yaml.safe_load(
        (REPO_ROOT / "axiom_oracles/config/concept_mappings.yaml").read_text()
    )["concepts"][concept]
    assert legacy["targets"]["policyengine"] == TARGET
    assert legacy["tolerance"] == 0.01
    assert legacy["relative_tolerance"] == 0.0000001

    contract = yaml.safe_load(
        (REPO_ROOT / "axiom_oracles/data/state_income_tax_populace.yaml").read_text()
    )
    jurisdiction = next(
        item for item in contract["jurisdictions"] if item["state"] == "MT"
    )
    assert jurisdiction["program"] == MODULE
    assert jurisdiction["output"] == concept
    assert jurisdiction["policyengine"] == {
        "target": TARGET,
        "tolerance": 0.01,
        "relative_tolerance": 0.0000001,
    }
    assert jurisdiction["status"] == "ready"
    assert RULESPEC_SHA256 in jurisdiction["evidence"]
    assert (
        "ec58dce99abe254aaceb8ec33ba7e1e0ebdf54158480aeffe299860b87b12009"
        in jurisdiction["evidence"]
    )
    assert {
        slot["slot"].split("#input.", 1)[1] for slot in jurisdiction["inputs"]
    } == INPUTS
