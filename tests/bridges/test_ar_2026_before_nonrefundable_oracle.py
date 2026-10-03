import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from axiom_oracles.bridges.coverage import build_policyengine_coverage_report
from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ar:policies/income_tax/pilot_liability_pipeline"
OUTPUT = "ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
TARGET = "ar_income_tax_before_non_refundable_credits_indiv"
RULESPEC_RELATIVE_PATH = Path(
    "us-ar/policies/income_tax/pilot_liability_pipeline.yaml"
)
RULESPEC_TEST_RELATIVE_PATH = Path(
    "us-ar/policies/income_tax/pilot_liability_pipeline.test.yaml"
)
RULESPEC_SHA256 = (
    "e450df6012dadcec268d7aef45679d46dddef062d811000b04783e0b74f4b210"
)
RULESPEC_TEST_SHA256 = (
    "53305b1547e1a132a78480f6c7703cbde0c2887f52850cd1782606a99595f57a"
)
HELD_BLOCK_SHA256 = (
    "eca7c6609b5543e586afa5ad2d081e6ac564e80e050c963746d2ac38408bb721"
)
FALLBACK_BLOCK_SHA256 = (
    "3d1603f3a9074f5ff9675a1a62c16405cd9ad63064b375cdd87916e8c986ff29"
)
FALLBACK_RATIONALE = (
    "PolicyEngine-US does not model AR agency policy manuals or state "
    "regulations at output granularity; comparable state outputs carry exact "
    "mappings which take precedence over this prefix."
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _rulespec_root() -> Path | None:
    candidates = [
        REPO_ROOT.parent / "rulespec-us",
        REPO_ROOT / ".rulespec-us",
    ]
    configured_root = os.environ.get("AXIOM_RULESPEC_ROOT")
    if configured_root:
        configured = Path(configured_root).expanduser()
        candidates = [configured, configured / "rulespec-us", *candidates]
    return next(
        (
            root
            for root in candidates
            if (root / RULESPEC_RELATIVE_PATH).is_file()
        ),
        None,
    )


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
                        "name": OUTPUT,
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


def test_arkansas_canonical_rulespec_and_fixture_hashes_are_live() -> None:
    root = _rulespec_root()
    if root is None:
        pytest.skip("rulespec-us checkout is not available")

    module_path = root / RULESPEC_RELATIVE_PATH
    test_path = root / RULESPEC_TEST_RELATIVE_PATH
    module = yaml.safe_load(module_path.read_text())
    assert hashlib.sha256(module_path.read_bytes()).hexdigest() == RULESPEC_SHA256
    assert (
        hashlib.sha256(test_path.read_bytes()).hexdigest()
        == RULESPEC_TEST_SHA256
    )
    assert [rule["name"] for rule in module["rules"]] == [
        "ar_pit_pilot_schedule_a_upper",
        "ar_pit_pilot_schedule_a_floor",
        "ar_pit_pilot_schedule_a_rate",
        "ar_pit_pilot_schedule_b_floor",
        "ar_pit_pilot_schedule_b_rate",
        "ar_pit_pilot_adjustment_lower_half_floor",
        "ar_pit_pilot_adjustment_lower_half_amount",
        "ar_pit_pilot_adjustment_upper_half_floor",
        "ar_pit_pilot_adjustment_upper_half_amount",
        "ar_pit_pilot_taxable_income",
        "ar_pit_pilot_uses_high_income_schedule",
        "ar_pit_pilot_schedule_a_bracket",
        "ar_pit_pilot_schedule_b_bracket",
        "ar_pit_pilot_adjustment_lower_half_bracket",
        "ar_pit_pilot_adjustment_upper_half_bracket",
        "ar_pit_pilot_bracket_adjustment",
        "ar_pit_pilot_schedule_tax",
        OUTPUT,
    ]
    tests = yaml.safe_load(test_path.read_text())
    assert len(tests) == 73


def test_arkansas_has_exactly_one_direct_pilot_mapping() -> None:
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    exact = {
        legal_id.removeprefix(prefix): mapping
        for legal_id, mapping in registry.mappings_by_legal_id.items()
        if legal_id.startswith(prefix)
    }

    assert set(exact) == {OUTPUT}
    mapping = exact[OUTPUT]
    assert mapping.match_type == "exact"
    assert mapping.mapping_type == "direct_variable"
    assert mapping.policyengine_variable == TARGET
    assert mapping.program == "tax"
    assert mapping.entity == "person"
    assert mapping.period == "year"
    assert mapping.unit == "USD"
    assert mapping.comparison == "money"
    assert mapping.candidate_priority is None
    assert "Person grain" in mapping.rationale
    assert "filing-unit aggregation or method selection" in mapping.rationale


def test_arkansas_exact_mapping_precedes_unchanged_jurisdiction_fallback() -> None:
    registry = load_policyengine_registry()

    exact = registry.mapping_for_legal_id(
        f"{MODULE}#{OUTPUT}",
        country="us",
    )
    assert exact is not None
    assert exact.mapping_type == "direct_variable"
    assert exact.policyengine_variable == TARGET

    for output in (
        "ar_pit_pilot_taxable_income",
        "ar_pit_pilot_schedule_tax",
        "input.ar_pit_pilot_individual_taxable_income",
        "ar_pit_pilot_final_annual_liability",
    ):
        broad = registry.mapping_for_legal_id(
            f"{MODULE}#{output}",
            country="us",
        )
        assert broad is not None
        assert broad.legal_id == "us-ar:"
        assert broad.match_type == "prefix"
        assert broad.mapping_type == "not_comparable"
        assert broad.candidate_priority == "P4"
        assert broad.rationale == FALLBACK_RATIONALE


def test_arkansas_held_and_fallback_blocks_remain_byte_identical() -> None:
    """The held and fallback Arkansas mappings are frozen.

    The US registry now lives in axiom-mappings, so the guard hashes the exported entries (and the
    held block's documenting comment) instead of a span of the old us.yaml text.
    """
    import axiom_mappings
    from axiom_mappings.export import oracles_registry

    shared = axiom_mappings.load("us")
    exported = oracles_registry(shared)
    held_prefix = "us-ar:policies/income_tax/2026_resident_liability_source_hold#"
    held = [e for e in exported["mappings"] if str(e.get("legal_id", "")).startswith(held_prefix)]
    comment = next(
        r["comment"]
        for r in [*shared.outputs, *shared.parameters]
        if str(r.get("axiom", "")).startswith(held_prefix) and r.get("comment")
    )
    fallback = [e for e in exported["prefixes"] if e.get("legal_id_prefix") == "us-ar:"]

    def digest(obj) -> str:
        return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

    assert len(held) == 13 and len(fallback) == 1
    assert digest({"comment": comment, "entries": held}) == HELD_BLOCK_SHA256
    assert digest(fallback) == FALLBACK_BLOCK_SHA256


@pytest.mark.parametrize("program", [None, "tax"])
def test_arkansas_output_is_comparable_in_coverage(
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
        if item["legal_id"] == f"{MODULE}#{OUTPUT}"
    )
    assert item["program"] == "tax"
    assert item["status"] == "comparable"
    assert item["mapping_type"] == "direct_variable"
    assert item["policyengine_variable"] == TARGET


def test_arkansas_mapping_mirrors_campaign_contract_and_legacy_registry() -> None:
    concept = f"{MODULE}#{OUTPUT}"
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
        item for item in contract["jurisdictions"] if item["state"] == "AR"
    )
    assert jurisdiction["program"] == MODULE
    assert jurisdiction["output"] == concept
    assert jurisdiction["policyengine"] == {
        "target": TARGET,
        "tolerance": 0.01,
        "relative_tolerance": 0.0000001,
        "aggregation": "person_sum_to_tax_unit",
    }
    assert jurisdiction["status"] == "ready"
    assert "2,816" in jurisdiction["evidence"]
    assert [item["policyengine_variable"] for item in jurisdiction["inputs"]] == [
        "ar_taxable_income_indiv"
    ]
