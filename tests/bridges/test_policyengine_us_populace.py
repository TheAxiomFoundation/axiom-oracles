from __future__ import annotations

import argparse

from axiom_oracles.bridges import us_populace
from axiom_oracles.bridges.adapters import get_pe_us_var_adapter
from axiom_oracles.bridges.registry import PolicyEngineMapping


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_reachable_input_bases_include_imported_capi_inputs(tmp_path):
    rulespec_root = tmp_path / "rulespec-us"
    program = _write(
        rulespec_root / "us-ca/regulations/cdss/eas/49/49-055.yaml",
        """format: rulespec/v1
imports:
- us-ca:regulations/cdss/eas/49/49-050#ca_capi_payment_standard
rules:
- name: ca_capi
  kind: derived
  versions:
  - effective_from: '2026-01-01'
    formula: max(0, ca_capi_payment_standard - ca_capi_countable_income_for_payment_month_under_retrospective_accounting)
""",
    )
    _write(
        rulespec_root / "us-ca/regulations/cdss/eas/49/49-050.yaml",
        """format: rulespec/v1
rules:
- name: ca_capi_payment_standard
  kind: derived
  versions:
  - effective_from: '2026-01-01'
    formula: if person_is_member_of_eligible_couple then ssi_ssp_payment_standard_for_selected_eligible_couple_living_arrangement else ssi_ssp_payment_standard_for_selected_individual_living_arrangement
""",
    )

    input_bases = us_populace.reachable_input_bases(
        program,
        rulespec_root=rulespec_root,
    )

    assert (
        input_bases[
            "ssi_ssp_payment_standard_for_selected_individual_living_arrangement"
        ]
        == "us-ca:regulations/cdss/eas/49/49-050"
    )
    assert (
        input_bases[
            "ca_capi_countable_income_for_payment_month_under_retrospective_accounting"
        ]
        == "us-ca:regulations/cdss/eas/49/49-055"
    )


def test_build_variable_request_uses_imported_input_bases(tmp_path):
    rulespec_root = tmp_path / "rulespec-us"
    _write(
        rulespec_root / "us-ca/regulations/cdss/eas/49/49-055.yaml",
        """format: rulespec/v1
imports:
- us-ca:regulations/cdss/eas/49/49-050#ca_capi_payment_standard
rules:
- name: ca_capi
  kind: derived
  versions:
  - effective_from: '2026-01-01'
    formula: ca_capi_payment_standard - ca_capi_countable_income_for_payment_month_under_retrospective_accounting
""",
    )
    _write(
        rulespec_root / "us-ca/regulations/cdss/eas/49/49-050.yaml",
        """format: rulespec/v1
rules:
- name: ca_capi_payment_standard
  kind: derived
  versions:
  - effective_from: '2026-01-01'
    formula: ssi_ssp_payment_standard_for_selected_individual_living_arrangement
""",
    )
    mapping = PolicyEngineMapping(
        legal_id="us-ca:regulations/cdss/eas/49/49-055#ca_capi",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="ca_capi",
    )
    case = us_populace.USVariableCase(
        variable="ca_capi",
        person_id=123,
        spm_unit_id=99,
        state="CA",
        inputs={
            "ssi_ssp_payment_standard_for_selected_individual_living_arrangement": 1000,
            "ca_capi_countable_income_for_payment_month_under_retrospective_accounting": 400,
        },
        pe_outputs={"ca_capi": 600},
    )

    request = us_populace.build_variable_request(
        cases=[case],
        mappings=(mapping,),
        rulespec_root=rulespec_root,
        year=2026,
        month=1,
    )
    input_names = [item["name"] for item in request["dataset"]["inputs"]]

    assert (
        "us-ca:regulations/cdss/eas/49/49-050#input.ssi_ssp_payment_standard_for_selected_individual_living_arrangement"
        in input_names
    )
    assert (
        "us-ca:regulations/cdss/eas/49/49-055#input.ca_capi_countable_income_for_payment_month_under_retrospective_accounting"
        in input_names
    )


def test_build_variable_request_omits_unreferenced_projected_inputs(tmp_path):
    rulespec_root = tmp_path / "rulespec-us"
    _write(
        rulespec_root / "us-co/regulations/9-ccr-2503-5/3.548.yaml",
        """format: rulespec/v1
rules:
- name: and_cs_authorized_grant_payment
  kind: derived
  versions:
  - effective_from: '2026-01-01'
    formula: and_cs_total_grant_standard - client_countable_income_other_than_ssi_for_and_cs
""",
    )
    mapping = PolicyEngineMapping(
        legal_id="us-co:regulations/9-ccr-2503-5/3.548#and_cs_authorized_grant_payment",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="co_state_supplement",
    )
    case = us_populace.USVariableCase(
        variable="co_state_supplement",
        person_id=456,
        spm_unit_id=88,
        state="CO",
        inputs={
            "client_countable_income_other_than_ssi_for_and_cs": 100,
            "client_total_countable_income_for_and_cs": 200,
        },
        pe_outputs={"co_state_supplement": 894},
    )

    request = us_populace.build_variable_request(
        cases=[case],
        mappings=(mapping,),
        rulespec_root=rulespec_root,
        year=2026,
        month=1,
    )
    input_names = [item["name"] for item in request["dataset"]["inputs"]]

    assert (
        "us-co:regulations/9-ccr-2503-5/3.548#input.client_countable_income_other_than_ssi_for_and_cs"
        in input_names
    )
    assert (
        "us-co:regulations/9-ccr-2503-5/3.548#input.client_total_countable_income_for_and_cs"
        not in input_names
    )


def test_compare_outputs_flags_missing_axiom_row_as_mismatch():
    mapping = PolicyEngineMapping(
        legal_id="us-co:regulations/9-ccr-2503-5/3.548#and_cs_authorized_grant_payment",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="co_state_supplement",
    )
    case = us_populace.USVariableCase(
        variable="co_state_supplement",
        person_id=456,
        spm_unit_id=88,
        state="CO",
        inputs={},
        pe_outputs={"co_state_supplement": 894},
    )

    report = us_populace.compare_outputs(
        variables=("co_state_supplement",),
        cases_by_variable={"co_state_supplement": [case]},
        mappings_by_variable={"co_state_supplement": (mapping,)},
        axiom_outputs_by_variable={"co_state_supplement": []},
        skipped_reasons={},
        tolerance=0.01,
        relative_tolerance=1e-9,
    )

    assert report.compared_values == 0
    assert len(report.mismatches) == 1
    assert report.mismatches[0].reason == "missing_axiom_row"


def test_compare_outputs_flags_missing_legal_output_as_mismatch():
    mapping = PolicyEngineMapping(
        legal_id="us-ca:regulations/cdss/eas/49/49-055#ca_capi",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="ca_capi",
    )
    case = us_populace.USVariableCase(
        variable="ca_capi",
        person_id=123,
        spm_unit_id=99,
        state="CA",
        inputs={},
        pe_outputs={"ca_capi": 600},
    )

    report = us_populace.compare_outputs(
        variables=("ca_capi",),
        cases_by_variable={"ca_capi": [case]},
        mappings_by_variable={"ca_capi": (mapping,)},
        axiom_outputs_by_variable={"ca_capi": [{"outputs": {}}]},
        skipped_reasons={},
        tolerance=0.01,
        relative_tolerance=1e-9,
    )

    assert report.compared_values == 0
    assert len(report.mismatches) == 1
    assert report.mismatches[0].reason == "missing_axiom_output"


def test_project_oap_combines_pe_ssi_sources_into_total_countable_income():
    adapter = get_pe_us_var_adapter("co_oap")
    assert adapter is not None

    projected, reason = us_populace.project_case_inputs(
        "co_oap",
        adapter,
        row={
            "ssi_countable_income": 1200,
            "ssi": 600,
            "co_oap_eligible": True,
        },
        spm_row=None,
    )

    assert reason is None
    assert projected["client_total_countable_income_for_oap"] == 150
    assert (
        projected["client_is_oap_eligible_under_sections_3_520_6_and_3_520_7"] is True
    )
    assert projected["client_is_inmate_in_penal_institution"] is False


def test_project_oap_prefers_annual_pe_ssi_sources_for_monthly_legal_input():
    adapter = get_pe_us_var_adapter("co_oap")
    assert adapter is not None

    projected, reason = us_populace.project_case_inputs(
        "co_oap",
        adapter,
        row={
            "ssi_countable_income": 100,
            "ssi": 50,
            "__annual_ssi_countable_income": 1200,
            "__annual_ssi": 600,
            "co_oap_eligible": True,
        },
        spm_row=None,
    )

    assert reason is None
    assert projected["client_total_countable_income_for_oap"] == 150


def test_project_co_state_supplement_keeps_monthly_pe_income_monthly():
    adapter = get_pe_us_var_adapter("co_state_supplement")
    assert adapter is not None

    projected, reason = us_populace.project_case_inputs(
        "co_state_supplement",
        adapter,
        row={
            "ssi_countable_income": 120,
            "ssi": 600,
            "co_state_supplement_eligible": True,
            "is_ssi_eligible_individual": True,
            "is_ssi_disabled": True,
        },
        spm_row=None,
    )

    assert reason is None
    assert projected["client_countable_income_other_than_ssi_for_and_cs"] == 120
    assert projected["ssi_payment_received_amount"] == 600


def test_project_mn_mfip_spm_inputs_to_cash_portion_boundary():
    adapter = get_pe_us_var_adapter("mn_mfip")
    assert adapter is not None

    projected, reason = us_populace.project_case_inputs(
        "mn_mfip",
        adapter,
        row={},
        spm_row={
            "mn_mfip_eligible": True,
            "mn_mfip_full_transitional_standard": 1087,
            "mn_mfip_family_wage_level": 1195.7,
            "mn_mfip_countable_earned_income": 467.5,
            "mn_mfip_countable_unearned_income": 0,
            "mn_mfip_food_portion": 445,
        },
    )

    assert reason is None
    assert projected["transitional_standard_for_corresponding_payment_month"] == 1087
    assert projected["family_wage_level_for_corresponding_payment_month"] == 1195.7
    assert projected["net_earned_income_in_budget_month"] == 467.5
    assert projected["unearned_income_in_budget_month"] == 0
    assert projected["mfip_food_portion_amount_under_section_0020_09"] == 445
    assert projected["unit_has_earned_income_only"] is True
    assert projected["unit_receives_no_income_other_than_mfip"] is False
    assert projected["unit_is_applicant_case"] is False
    assert projected["recoupment_amount_if_applicable"] == 0


def test_project_mn_mfip_skips_negative_unearned_income():
    adapter = get_pe_us_var_adapter("mn_mfip")
    assert adapter is not None

    projected, reason = us_populace.project_case_inputs(
        "mn_mfip",
        adapter,
        row={},
        spm_row={
            "mn_mfip_eligible": True,
            "mn_mfip_full_transitional_standard": 1087,
            "mn_mfip_family_wage_level": 1195.7,
            "mn_mfip_countable_earned_income": 0,
            "mn_mfip_countable_unearned_income": -10,
            "mn_mfip_food_portion": 445,
        },
    )

    assert projected == {}
    assert reason == "mn_mfip_negative_unearned_income"


def test_project_mn_mfip_skips_ineligible_spm_units():
    adapter = get_pe_us_var_adapter("mn_mfip")
    assert adapter is not None

    projected, reason = us_populace.project_case_inputs(
        "mn_mfip",
        adapter,
        row={},
        spm_row={
            "mn_mfip_eligible": False,
            "mn_mfip_full_transitional_standard": 1087,
            "mn_mfip_family_wage_level": 1195.7,
            "mn_mfip_countable_earned_income": 0,
            "mn_mfip_countable_unearned_income": 0,
            "mn_mfip_food_portion": 445,
        },
    )

    assert projected == {}
    assert reason == "mn_mfip_ineligible_spm_unit"


def test_policyengine_target_period_uses_mapping_multiplier_before_monthly_adapter():
    co_oap_adapter = get_pe_us_var_adapter("co_oap")
    assert co_oap_adapter is not None
    co_oap_mapping = PolicyEngineMapping(
        legal_id="us-co:regulations/9-ccr-2503-5/3.532#oap_authorized_grant_payment_for_month",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="co_oap",
        result_multiplier=1 / 12,
    )

    assert (
        us_populace.policyengine_target_period(
            co_oap_adapter,
            co_oap_mapping,
            year=2026,
            month=1,
        )
        == 2026
    )

    co_ssp_adapter = get_pe_us_var_adapter("co_state_supplement")
    assert co_ssp_adapter is not None
    co_ssp_mapping = PolicyEngineMapping(
        legal_id="us-co:regulations/9-ccr-2503-5/3.548#and_cs_authorized_grant_payment",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="co_state_supplement",
    )

    assert (
        us_populace.policyengine_target_period(
            co_ssp_adapter,
            co_ssp_mapping,
            year=2026,
            month=1,
        )
        == "2026-01"
    )


def test_source_variables_for_adapters_excludes_target_variables():
    source_vars = us_populace.source_variables_for_adapters(
        ("co_oap", "co_state_supplement", "ca_capi", "mn_mfip")
    )

    assert "co_oap" not in source_vars["person"]
    assert "co_state_supplement" not in source_vars["person"]
    assert "ca_capi" not in source_vars["person"]
    assert "mn_mfip" not in source_vars["spm_unit"]
    assert "ca_capi" not in source_vars["spm_unit"]
    assert "ca_capi_eligible" in source_vars["spm_unit"]
    assert "mn_mfip_eligible" in source_vars["spm_unit"]
    assert "mn_mfip_full_transitional_standard" in source_vars["spm_unit"]


def test_configure_us_populace_parser_accepts_repeated_variables():
    parser = argparse.ArgumentParser()
    us_populace.configure_parser(parser)

    args = parser.parse_args(
        ["--variable", "co_oap", "--variable", "co_state_supplement"]
    )

    assert args.variables == ["co_oap", "co_state_supplement"]
