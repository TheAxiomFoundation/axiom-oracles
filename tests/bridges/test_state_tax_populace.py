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
    jurisdiction = next(
        item
        for item in document["jurisdictions"]
        if any(slot["source_kind"] == "blocked" for slot in item["inputs"])
    )
    slot = next(
        slot
        for slot in jurisdiction["inputs"]
        if slot["source_kind"] == "blocked"
    )
    return jurisdiction, slot


def test_packaged_contract_has_exact_campaign_inventory() -> None:
    contract = load_state_tax_populace_contract()

    assert len(contract.jurisdictions) == 43
    assert set(contract.by_state()) == EXPECTED_STATE_CODES
    assert (
        sum(len(item.inputs) for item in contract.jurisdictions)
        == EXPECTED_EXPLICIT_INPUT_COUNT
    )
    assert (
        sum(len(item.relations) for item in contract.jurisdictions)
        == EXPECTED_EXPLICIT_RELATION_COUNT
    )
    assert len({item.program for item in contract.jurisdictions}) == 43
    assert len({item.output for item in contract.jurisdictions}) == 43
    assert len({item.policyengine_target for item in contract.jurisdictions}) == 43


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


def test_contract_pins_arkansas_person_aggregation_surface() -> None:
    contract = load_state_tax_populace_contract()
    arkansas = contract.by_state()["AR"]

    assert arkansas.output.endswith(
        "#ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    )
    assert (
        arkansas.policyengine_target
        == "ar_income_tax_before_non_refundable_credits_indiv"
    )
    assert arkansas.comparison_aggregation == "person_sum_to_tax_unit"

    document = _document()
    _state(document, "AR")["policyengine"]["aggregation"] = "max_person"
    with pytest.raises(
        StateTaxPopulaceContractError,
        match="unsupported comparison aggregation|reviewed surface allowlist",
    ):
        validate_state_tax_populace_contract(document)


def test_contract_pins_kansas_canonical_k40es_surface() -> None:
    kansas = load_state_tax_populace_contract().by_state()["KS"]
    module = "us-ks:policies/income_tax/2026_k40es_schedule_before_credits"

    assert kansas.program == module
    assert kansas.output == (
        f"{module}#ks_pit_2026_k40es_schedule_before_credits"
    )
    assert (
        kansas.policyengine_target
        == "ks_k40es_schedule_before_credits_reviewed"
    )
    assert (kansas.tolerance, kansas.relative_tolerance) == (0.01, 1e-7)
    assert [slot.slot for slot in kansas.inputs] == [
        f"{module}#input.ks_pit_2026_k40es_completed_taxable_income",
        f"{module}#input.ks_pit_2026_k40es_married_joint_schedule_applies",
    ]
    assert [slot.policyengine_variable for slot in kansas.inputs] == [
        "ks_taxable_income",
        "tax_unit_is_joint",
    ]


def test_contract_pins_california_bhst_component_surface() -> None:
    california = load_state_tax_populace_contract().by_state()["CA"]
    module = "us-ca:policies/income_tax/pilot_liability_pipeline"

    assert california.program == module
    assert california.output == (
        f"{module}#ca_pit_pilot_behavioral_health_services_tax"
    )
    assert california.policyengine_target == "ca_mental_health_services_tax"
    assert (
        california.policyengine_target
        != "ca_income_tax_before_refundable_credits"
    )
    assert (california.tolerance, california.relative_tolerance) == (
        0.01,
        1e-7,
    )
    assert [slot.slot for slot in california.inputs] == [
        f"{module}#input.ca_pit_pilot_supplied_completed_taxable_income"
    ]
    assert [slot.policyengine_variable for slot in california.inputs] == [
        "ca_taxable_income"
    ]


def test_contract_pins_minnesota_2026_schedule_surface() -> None:
    minnesota = load_state_tax_populace_contract().by_state()["MN"]
    module = "us-mn:policies/income_tax/pilot_liability_pipeline"

    assert minnesota.program == module
    assert minnesota.output == f"{module}#mn_pit_pilot_schedule_tax"
    assert minnesota.policyengine_target == "mn_basic_tax_precision_stable"
    assert (
        minnesota.policyengine_target
        not in {"mn_basic_tax", "mn_income_tax_before_refundable_credits"}
    )
    assert (minnesota.tolerance, minnesota.relative_tolerance) == (1.0, 0.0)
    assert [slot.slot for slot in minnesota.inputs] == [
        f"{module}#input.mn_pit_pilot_state_taxable_income",
        f"{module}#input.mn_pit_pilot_filing_status_joint_or_surviving_spouse",
        f"{module}#input.mn_pit_pilot_filing_status_separate",
        f"{module}#input.mn_pit_pilot_filing_status_head_of_household",
    ]
    assert [slot.source_kind for slot in minnesota.inputs] == [
        "pe_upstream_boundary",
        "derived",
        "derived",
        "derived",
    ]
    assert [slot.policyengine_variable for slot in minnesota.inputs] == [
        "mn_taxable_income",
        "filing_status",
        "filing_status",
        "filing_status",
    ]
    assert [slot.policyengine_transform for slot in minnesota.inputs] == [
        None,
        "filing_status_joint_or_surviving_spouse",
        "filing_status_is_separate",
        "filing_status_is_head_of_household",
    ]


def test_contract_pins_dc_canonical_joint_method_schedule() -> None:
    district = load_state_tax_populace_contract().by_state()["DC"]
    module = (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits"
    )

    assert district.program == module
    assert district.output == (
        f"{module}#dc_pit_2026_section_47_1806_03_schedule_before_credits"
    )
    assert district.policyengine_target == "dc_income_tax_before_credits_joint"
    assert district.policyengine_target != "dc_income_tax_before_credits"
    assert (district.tolerance, district.relative_tolerance) == (0.01, 1e-7)
    assert [slot.slot for slot in district.inputs] == [
        f"{module}#input."
        "dc_pit_2026_section_47_1806_03_completed_joint_method_taxable_income"
    ]
    assert [slot.policyengine_variable for slot in district.inputs] == [
        "dc_taxable_income_joint"
    ]


def test_packaged_contract_has_reviewed_ready_states() -> None:
    contract = load_state_tax_populace_contract()
    summary = readiness_summary(contract)

    assert summary == {
        "jurisdiction_count": 43,
        "ready_count": 32,
        "blocked_count": 11,
        "ready_states": [
            "AL",
            "AR",
            "AZ",
            "CA",
            "CO",
            "CT",
            "DC",
            "DE",
            "GA",
            "HI",
            "IA",
            "IL",
            "IN",
            "KS",
            "KY",
            "LA",
            "MI",
            "MN",
            "MS",
            "MT",
            "NC",
            "NJ",
            "NM",
            "NY",
            "OH",
            "OK",
            "PA",
            "SC",
            "UT",
            "VA",
            "VT",
            "WV",
        ],
        "blocked_states": sorted(
            EXPECTED_STATE_CODES
            - {
                "AL",
                "AZ",
                "AR",
                "CA",
                "CO",
                "CT",
                "DC",
                "DE",
                "GA",
                "HI",
                "IA",
                "IL",
                "IN",
                "KS",
                "KY",
                "LA",
                "MI",
                "MN",
                "MS",
                "MT",
                "NC",
                "NJ",
                "NM",
                "NY",
                "OH",
                "OK",
                "PA",
                "SC",
                "UT",
                "VA",
                "VT",
                "WV",
            }
        ),
        "explicit_input_count": EXPECTED_EXPLICIT_INPUT_COUNT,
            "explicit_relation_count": EXPECTED_EXPLICIT_RELATION_COUNT,
            "blocked_input_count": EXPECTED_EXPLICIT_INPUT_COUNT - 67,
        "blocked_relation_count": 0,
    }
    assert "NH" not in contract.by_state()
    expected_boundaries = {
        "AL": ["al_taxable_income"],
        "AZ": ["az_taxable_income"],
        "AR": ["ar_taxable_income_indiv"],
        "CA": ["ca_taxable_income"],
        "CT": ["ct_taxable_income", "ct_agi"],
        "CO": ["co_taxable_income"],
        "DC": ["dc_taxable_income_joint"],
        "DE": ["de_taxable_income_indv"],
        "GA": ["ga_taxable_income"],
        "HI": ["hi_taxable_income"],
        "IL": ["il_taxable_income", "recapture_of_investment_credit"],
        "IA": [
            "ia_taxable_income_consolidated",
            "ia_modified_income",
            "ia_alternate_tax_eligible",
        ],
        "IN": ["in_agi"],
        "KS": ["ks_taxable_income", "tax_unit_is_joint"],
        "LA": ["la_taxable_income"],
        "MI": ["mi_taxable_income"],
        "MN": ["mn_taxable_income"],
        "MS": ["ms_taxable_income_joint"],
        "NC": ["nc_taxable_income"],
        "NM": ["nm_taxable_income"],
        "OH": ["oh_taxable_income"],
        "OK": ["ok_taxable_income"],
        "PA": ["pa_adjusted_taxable_income"],
        "SC": ["sc_taxable_income"],
        "UT": ["ut_taxable_income", "ut_income_tax_exempt"],
        "VA": ["va_taxable_income"],
        "VT": ["vt_normal_income_tax", "adjusted_gross_income"],
        "WV": ["wv_taxable_income"],
    }
    for state, variables in expected_boundaries.items():
        inputs = [
            item
            for item in contract.by_state()[state].inputs
            if item.source_kind == "pe_upstream_boundary"
        ]
        assert [item.policyengine_variable for item in inputs] == variables
        assert all(item.source_kind == "pe_upstream_boundary" for item in inputs)
    ga = contract.by_state()["GA"]
    assert ga.program == (
        "us-ga:policies/income_tax/"
        "2026_annual_tax_before_nonrefundable_credits"
    )
    assert ga.output == (
        f"{ga.program}#ga_pit_2026_annual_tax_before_nonrefundable_credits"
    )
    assert [item.slot for item in ga.inputs] == [
        f"{ga.program}#input.ga_pit_2026_completed_georgia_taxable_net_income"
    ]
    assert ga.policyengine_target == "ga_income_tax_before_non_refundable_credits"
    ky_input = contract.by_state()["KY"].inputs[0]
    assert ky_input.source_kind == "derived"
    assert list(ky_input.policyengine_variables) == [
        "ky_taxable_income_indiv",
        "ky_taxable_income_joint",
        "ky_files_separately",
    ]
    assert (
        ky_input.policyengine_transform
        == "filing_method_selected_person_summed_taxable_income"
    )
    va_derived = [
        item
        for item in contract.by_state()["VA"].inputs
        if item.source_kind == "derived"
    ]
    assert [item.policyengine_variable for item in va_derived] == ["va_must_file"]
    assert [item.policyengine_transform for item in va_derived] == [
        "zero_one_to_boolean"
    ]
    ok_derived = [
        item
        for item in contract.by_state()["OK"].inputs
        if item.source_kind == "derived"
    ]
    assert [item.policyengine_variable for item in ok_derived] == ["filing_status"]
    assert [item.policyengine_transform for item in ok_derived] == [
        "filing_status_joint_surviving_spouse_or_head"
    ]
    al_derived = [
        item
        for item in contract.by_state()["AL"].inputs
        if item.source_kind == "derived"
    ]
    assert [item.policyengine_variable for item in al_derived] == ["filing_status"]
    assert [item.policyengine_transform for item in al_derived] == [
        "filing_status_joint_or_surviving_spouse"
    ]
    ct_derived = [
        item
        for item in contract.by_state()["CT"].inputs
        if item.source_kind == "derived"
    ]
    assert [item.policyengine_variable for item in ct_derived] == [
        "filing_status",
        "filing_status",
        "filing_status",
        "filing_status",
    ]
    assert [item.policyengine_transform for item in ct_derived] == [
        "filing_status_is_single",
        "filing_status_is_separate",
        "filing_status_is_head_of_household",
        "filing_status_joint_or_surviving_spouse",
    ]
    ny = contract.by_state()["NY"]
    assert ny.program == "us-ny:policies/income_tax/pilot_liability_pipeline"
    assert ny.output == f"{ny.program}#ny_pit_pilot_main_income_tax"
    assert ny.policyengine_target == "ny_main_income_tax"
    assert (ny.tolerance, ny.relative_tolerance) == (2.25, 1e-7)
    assert [item.policyengine_variable for item in ny.inputs] == [
        "ny_taxable_income",
        "filing_status",
        "filing_status",
    ]
    assert [item.policyengine_transform for item in ny.inputs] == [
        None,
        "filing_status_joint_or_surviving_spouse",
        "filing_status_is_head_of_household",
    ]
    assert "supplemental tax" in ny.evidence
    assert "rounded cumulative bases" in ny.evidence
    il = contract.by_state()["IL"]
    assert il.program == "us-il:policies/income_tax/pilot_liability_pipeline"
    assert il.output == f"{il.program}#il_pit_pilot_income_tax_liability"
    assert il.policyengine_target == (
        "il_income_tax_before_non_refundable_credits"
    )
    assert (il.tolerance, il.relative_tolerance) == (1.0, 0.0)
    assert [item.policyengine_variable for item in il.inputs] == [
        "il_taxable_income",
        "recapture_of_investment_credit",
    ]
    assert all(
        item.source_kind == "pe_upstream_boundary" for item in il.inputs
    )
    assert "4.95% rate" in il.evidence
    assert "2,332 positive-weight" in il.evidence
    assert "all 2,332 positive-weight routed Illinois TaxUnits" in il.evidence
    assert "Every population row had zero recapture" in il.evidence
    assert "positive_taxable_income_with_recapture fixture" in il.evidence
    assert "rather than synthesized population input" in il.inputs[1].evidence
    de = contract.by_state()["DE"]
    assert de.output == (
        "us-de:policies/income_tax/pilot_liability_pipeline#"
        "de_pit_pilot_separate_schedule_tax"
    )
    assert (
        de.policyengine_target
        == "de_income_tax_before_non_refundable_credits_indv"
    )
    assert de.comparison_aggregation == "person_sum_to_tax_unit"
    assert (de.tolerance, de.relative_tolerance) == (0.01, 1e-7)
    assert [item.slot for item in de.inputs] == [
        "us-de:policies/income_tax/pilot_liability_pipeline#input."
        "de_pit_pilot_supplied_separate_taxable_income",
    ]
    assert de.inputs[0].policyengine_variable == "de_taxable_income_indv"
    assert de.inputs[0].source_kind == "pe_upstream_boundary"
    assert de.relations == ()
    ms = contract.by_state()["MS"]
    assert ms.program == (
        "us-ms:policies/income_tax/2026_section_27_7_5_schedule"
    )
    assert ms.output == (
        f"{ms.program}#ms_pit_2026_section_27_7_5_schedule_tax"
    )
    assert ms.policyengine_target == "ms_income_tax_before_credits_joint"
    assert ms.comparison_aggregation == "person_sum_to_tax_unit"
    assert [item.slot for item in ms.inputs] == [
        f"{ms.program}#input.ms_pit_2026_supplied_taxable_income"
    ]
    assert ms.relations == ()
    assert contract.by_state()["VT"].relations == ()
    hi = contract.by_state()["HI"]
    assert hi.policyengine_target == "hi_income_tax_before_non_refundable_credits"
    assert (hi.tolerance, hi.relative_tolerance) == (1.0, 0.0)
    assert hi.relations == ()
    hi_derived = [item for item in hi.inputs if item.source_kind == "derived"]
    assert [item.policyengine_variable for item in hi_derived] == [
        "filing_status",
        "filing_status",
        None,
    ]
    assert [item.policyengine_transform for item in hi_derived] == [
        "filing_status_joint_or_surviving_spouse",
        "filing_status_is_head_of_household",
        "tax_unit_net_and_person_sum_to_capital_gains_worksheet_line_10",
    ]
    assert hi_derived[-1].policyengine_variables == (
        "net_capital_gain",
        "long_term_capital_gains",
    )
    nm_derived = [
        item
        for item in contract.by_state()["NM"].inputs
        if item.source_kind == "derived"
    ]
    assert [item.policyengine_variable for item in nm_derived] == [
        "filing_status",
        "filing_status",
    ]
    assert [item.policyengine_transform for item in nm_derived] == [
        "filing_status_is_separate",
        "filing_status_joint_surviving_spouse_or_head",
    ]
    wv_derived = [
        item
        for item in contract.by_state()["WV"].inputs
        if item.source_kind == "derived"
    ]
    assert [item.policyengine_variable for item in wv_derived] == ["filing_status"]
    assert [item.policyengine_transform for item in wv_derived] == [
        "filing_status_is_separate"
    ]
    mt_derived = [
        item
        for item in contract.by_state()["MT"].inputs
        if item.source_kind == "derived"
    ]
    assert contract.by_state()["MT"].policyengine_target == (
        "mt_income_tax_before_non_refundable_credits_joint"
    )
    assert [item.policyengine_variable for item in mt_derived] == [
        "mt_taxable_income_joint",
        None,
        "filing_status",
        "filing_status",
    ]
    assert [item.policyengine_variables for item in mt_derived] == [
        (),
        ("long_term_capital_gains", "short_term_capital_gains"),
        (),
        (),
    ]
    assert [item.policyengine_transform for item in mt_derived] == [
        "person_sum_to_tax_unit",
        "person_sums_to_net_long_term_capital_gain",
        "filing_status_joint_or_surviving_spouse",
        "filing_status_is_head_of_household",
    ]


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
    with pytest.raises(StateTaxPopulaceContractError, match="exactly 43"):
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

    with pytest.raises(
        StateTaxPopulaceContractError,
        match=f"exactly {EXPECTED_EXPLICIT_INPUT_COUNT}",
    ):
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

    with pytest.raises(StateTaxPopulaceContractError, match="incompatible"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_unreviewed_derived_transform() -> None:
    document = _document()
    slot = next(
        item
        for item in _state(document, "IA")["inputs"]
        if item["source_kind"] == "derived"
    )
    slot["policyengine_transform"] = "greater_than_or_equal_64"

    with pytest.raises(StateTaxPopulaceContractError, match="transform allowlist"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_unreviewed_multi_source_derived_boundary() -> None:
    document = _document()
    slot = next(
        item
        for item in _state(document, "MT")["inputs"]
        if "policyengine_variables" in item
    )
    slot["policyengine_variables"] = [
        "short_term_capital_gains",
        "long_term_capital_gains",
    ]

    with pytest.raises(StateTaxPopulaceContractError, match="transform allowlist"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_ambiguous_single_and_multi_source_metadata() -> None:
    document = _document()
    slot = next(
        item
        for item in _state(document, "MT")["inputs"]
        if "policyengine_variables" in item
    )
    slot["policyengine_variable"] = "long_term_capital_gains"

    with pytest.raises(StateTaxPopulaceContractError, match="exactly one of"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_unreviewed_statutory_constant() -> None:
    document = _document()
    slot = next(
        item
        for item in _state(document, "IA")["inputs"]
        if item["source_kind"] == "statutory_constant"
    )
    slot["constant_value"] = 0.039

    with pytest.raises(StateTaxPopulaceContractError, match="constant allowlist"):
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
    jurisdiction, _ = _first_input(document)
    jurisdiction["status"] = "ready"

    with pytest.raises(StateTaxPopulaceContractError, match="slot-derived status"):
        validate_state_tax_populace_contract(document)
