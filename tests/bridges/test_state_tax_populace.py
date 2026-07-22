from __future__ import annotations

from copy import deepcopy

import pytest
import yaml

from axiom_oracles.bridges.state_tax_populace import (
    ALLOWED_SOURCE_KINDS,
    EXPECTED_EXPLICIT_INPUT_COUNT,
    EXPECTED_EXPLICIT_RELATION_COUNT,
    EXPECTED_STATE_CODES,
    STATE_TAX_POPULACE_CONTRACT_PATH,
    StateTaxPopulaceContractError,
    load_state_tax_populace_contract,
    readiness_summary,
    validate_state_tax_populace_contract,
)


def _document() -> dict:
    return yaml.safe_load(STATE_TAX_POPULACE_CONTRACT_PATH.read_text())


def _state(document: dict, state: str) -> dict:
    return next(item for item in document["jurisdictions"] if item["state"] == state)


def _first_input(document: dict) -> tuple[dict, dict]:
    jurisdiction = next(item for item in document["jurisdictions"] if item["inputs"])
    return jurisdiction, jurisdiction["inputs"][0]


def test_packaged_contract_has_exact_campaign_inventory() -> None:
    contract = load_state_tax_populace_contract()

    assert len(contract.jurisdictions) == 44
    assert set(contract.by_state()) == EXPECTED_STATE_CODES
    assert sum(len(item.inputs) for item in contract.jurisdictions) == 255
    assert sum(len(item.relations) for item in contract.jurisdictions) == 1
    assert len({item.program for item in contract.jurisdictions}) == 44
    assert len({item.output for item in contract.jurisdictions}) == 44
    assert len({item.policyengine_target for item in contract.jurisdictions}) == 44


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "axiom.state_tax_populace_contract.v2"),
        (("validation_year",), 2025),
        (("population", "country"), "ca"),
        (("population", "year"), 2023),
        (("population", "revision"), "latest"),
        (("population", "sha256"), "0" * 64),
        (("population", "built_with"), "1.0.0"),
        (("population_scope", "residency_model"), "current_state_only"),
        (("population_scope", "inclusion"), "filtered"),
        (("registry_source",), "scripts/another_generator.py"),
    ],
)
def test_contract_rejects_pinned_campaign_metadata_drift(
    path: tuple[str, ...], value: object
) -> None:
    document = _document()
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(StateTaxPopulaceContractError, match="must be"):
        validate_state_tax_populace_contract(document)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("policyengine", "target"), "ca_income_tax_registry_drift"),
        (("policyengine", "tolerance"), 5.25),
        (("policyengine", "relative_tolerance"), 0.021),
    ],
)
def test_contract_rejects_comparison_registry_drift(
    path: tuple[str, ...], value: object
) -> None:
    document = _document()
    target = document["jurisdictions"][0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(StateTaxPopulaceContractError, match="registry does not match"):
        validate_state_tax_populace_contract(document)


def test_packaged_contract_has_reviewed_nh_and_ut_ready() -> None:
    contract = load_state_tax_populace_contract()
    summary = readiness_summary(contract)

    assert summary == {
        "jurisdiction_count": 44,
        "ready_count": 2,
        "blocked_count": 42,
        "ready_states": ["NH", "UT"],
        "blocked_states": sorted(EXPECTED_STATE_CODES - {"NH", "UT"}),
        "explicit_input_count": EXPECTED_EXPLICIT_INPUT_COUNT,
        "explicit_relation_count": EXPECTED_EXPLICIT_RELATION_COUNT,
        "blocked_input_count": EXPECTED_EXPLICIT_INPUT_COUNT - 1,
        "blocked_relation_count": EXPECTED_EXPLICIT_RELATION_COUNT,
    }
    nh = contract.by_state()["NH"]
    assert nh.inputs == ()
    assert nh.relations == ()
    ut = contract.by_state()["UT"]
    assert len(ut.inputs) == 1
    assert ut.inputs[0].source_kind == "pe_upstream_boundary"
    assert ut.inputs[0].policyengine_variable == "ut_taxable_income"


def test_contract_forbids_filtered_population_slices() -> None:
    document = _document()
    document["population_scope"]["filtered_slices_allowed"] = True

    with pytest.raises(StateTaxPopulaceContractError, match="must be False"):
        validate_state_tax_populace_contract(document)


def test_every_slot_has_status_consistent_source_and_evidence() -> None:
    contract = load_state_tax_populace_contract()

    for jurisdiction in contract.jurisdictions:
        for slot in (*jurisdiction.inputs, *jurisdiction.relations):
            if slot.status == "blocked":
                assert slot.source_kind == "blocked"
            else:
                assert slot.source_kind != "blocked"
            assert slot.evidence


@pytest.mark.parametrize("field", ["source_kind", "status", "evidence"])
def test_slot_rejects_missing_source_status_or_evidence(field: str) -> None:
    document = _document()
    _, slot = _first_input(document)
    del slot[field]

    with pytest.raises(StateTaxPopulaceContractError, match=field):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_missing_jurisdiction_evidence() -> None:
    document = _document()
    del document["jurisdictions"][0]["evidence"]

    with pytest.raises(StateTaxPopulaceContractError, match="evidence"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_missing_or_extra_pit_state() -> None:
    missing = _document()
    missing["jurisdictions"].pop()
    with pytest.raises(StateTaxPopulaceContractError, match="exactly 44"):
        validate_state_tax_populace_contract(missing)

    extra = _document()
    duplicate = deepcopy(extra["jurisdictions"][0])
    duplicate["state"] = "TX"
    duplicate["fips"] = "48"
    duplicate["jurisdiction"] = "us-tx"
    duplicate["program"] = "us-tx:policies/income_tax/pilot_liability_pipeline"
    duplicate["output"] = (
        duplicate["program"] + "#tx_pit_pilot_income_tax_liability"
    )
    duplicate["policyengine"]["target"] = "tx_income_tax"
    extra["jurisdictions"].append(duplicate)
    with pytest.raises(StateTaxPopulaceContractError, match="unexpected PIT/DC"):
        validate_state_tax_populace_contract(extra)


@pytest.mark.parametrize("field", ["program", "output"])
def test_contract_rejects_duplicate_program_or_output(field: str) -> None:
    document = _document()
    document["jurisdictions"][1][field] = document["jurisdictions"][0][field]

    with pytest.raises(StateTaxPopulaceContractError, match=f"duplicate {field}"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_duplicate_policyengine_target() -> None:
    document = _document()
    document["jurisdictions"][1]["policyengine"]["target"] = document[
        "jurisdictions"
    ][0]["policyengine"]["target"]

    with pytest.raises(StateTaxPopulaceContractError, match="duplicate PolicyEngine"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_incomplete_explicit_slot_inventory() -> None:
    document = _document()
    jurisdiction, _ = _first_input(document)
    jurisdiction["inputs"].pop()

    with pytest.raises(StateTaxPopulaceContractError, match="exactly 255"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_changed_explicit_slot_inventory() -> None:
    document = _document()
    jurisdiction, slot = _first_input(document)
    slot["slot"] = jurisdiction["program"] + "#input.invented_boundary"

    with pytest.raises(StateTaxPopulaceContractError, match="inventory does not match"):
        validate_state_tax_populace_contract(document)


@pytest.mark.parametrize(
    "source_kind",
    sorted(ALLOWED_SOURCE_KINDS - {"blocked", "pe_upstream_boundary"}),
)
def test_contract_rejects_unreviewed_non_pe_source_metadata(source_kind: str) -> None:
    document = _document()
    _, slot = _first_input(document)
    slot["source_kind"] = source_kind
    slot["status"] = "ready"
    slot["evidence"] = "Source-backed projection test evidence."

    with pytest.raises(StateTaxPopulaceContractError, match="source metadata"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_unreviewed_upstream_pe_boundary() -> None:
    document = _document()
    _, slot = _first_input(document)
    slot.update(
        {
            "source_kind": "pe_upstream_boundary",
            "status": "ready",
            "evidence": "Declared stage boundary, independently reviewed.",
            "policyengine_variable": "adjusted_gross_income",
            "policyengine_relationship": "upstream",
        }
    )

    with pytest.raises(StateTaxPopulaceContractError, match="upstream allowlist"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_policyengine_target_reuse() -> None:
    document = _document()
    jurisdiction, slot = _first_input(document)
    slot.update(
        {
            "source_kind": "pe_upstream_boundary",
            "status": "ready",
            "evidence": "Invalid circular boundary.",
            "policyengine_variable": jurisdiction["policyengine"]["target"],
            "policyengine_relationship": "upstream",
        }
    )

    with pytest.raises(StateTaxPopulaceContractError, match="may not reuse"):
        validate_state_tax_populace_contract(document)


@pytest.mark.parametrize("relationship", ["target", "downstream", "peer", ""])
def test_contract_rejects_non_upstream_pe_boundaries(relationship: str) -> None:
    document = _document()
    _, slot = _first_input(document)
    slot.update(
        {
            "source_kind": "pe_upstream_boundary",
            "status": "ready",
            "evidence": "Invalid downstream boundary.",
            "policyengine_variable": "some_pe_variable",
            "policyengine_relationship": relationship,
        }
    )

    with pytest.raises(StateTaxPopulaceContractError, match="must be 'upstream'"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_pe_metadata_on_other_source_kind() -> None:
    document = _document()
    _, slot = _first_input(document)
    slot["policyengine_variable"] = "adjusted_gross_income"

    with pytest.raises(StateTaxPopulaceContractError, match="requires source_kind"):
        validate_state_tax_populace_contract(document)


@pytest.mark.parametrize(
    "key",
    [
        "residual_adjustment",
        "dynamic_residual_adjustment",
        "align_to_policyengine",
        "candidate_selection",
        "result_selection",
    ],
)
def test_contract_rejects_dynamic_alignment_controls(key: str) -> None:
    document = _document()
    _, slot = _first_input(document)
    slot[key] = {"strategy": "min"}

    with pytest.raises(StateTaxPopulaceContractError, match="forbidden"):
        validate_state_tax_populace_contract(document)


@pytest.mark.parametrize("strategy", ["min", "max"])
def test_contract_rejects_candidate_min_max_selection(strategy: str) -> None:
    document = _document()
    _, slot = _first_input(document)
    slot["strategy"] = strategy

    with pytest.raises(StateTaxPopulaceContractError, match="min/max"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_unknown_source_kind_and_inconsistent_status() -> None:
    unknown = _document()
    _, slot = _first_input(unknown)
    slot["source_kind"] = "policyengine_target"
    with pytest.raises(StateTaxPopulaceContractError, match="unsupported source_kind"):
        validate_state_tax_populace_contract(unknown)

    inconsistent = _document()
    _, slot = _first_input(inconsistent)
    slot["status"] = "ready"
    with pytest.raises(StateTaxPopulaceContractError, match="blocked source_kind"):
        validate_state_tax_populace_contract(inconsistent)


def test_contract_rejects_declared_readiness_that_ignores_blocked_slots() -> None:
    document = _document()
    _state(document, "CA")["status"] = "ready"

    with pytest.raises(StateTaxPopulaceContractError, match="slot-derived status"):
        validate_state_tax_populace_contract(document)
