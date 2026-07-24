from pathlib import Path

import yaml

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-sc:policies/income_tax/2026_full_year_resident_core"

OUTPUT_NAMES = {
    "sc_pit_2026_input_domain_is_valid",
    "sc_pit_2026_base_profile_applies",
    "sc_pit_2026_supported_profile_applies",
    "sc_pit_2026_lower_rate",
    "sc_pit_2026_upper_rate",
    "sc_pit_2026_upper_bracket_floor",
    "sc_pit_2026_upper_bracket_subtraction",
    "sc_pit_2026_net_capital_gain_deduction_rate",
    "sc_pit_2026_under_65_retirement_cap",
    "sc_pit_2026_age_65_threshold",
    "sc_pit_2026_sciad_single_or_separate_base",
    "sc_pit_2026_sciad_head_base",
    "sc_pit_2026_sciad_joint_or_surviving_base",
    "sc_pit_2026_sciad_single_or_separate_phaseout_start",
    "sc_pit_2026_sciad_head_phaseout_start",
    "sc_pit_2026_sciad_joint_or_surviving_phaseout_start",
    "sc_pit_2026_sciad_single_or_separate_phaseout_denominator",
    "sc_pit_2026_sciad_head_phaseout_denominator",
    "sc_pit_2026_sciad_joint_or_surviving_phaseout_denominator",
    "sc_pit_2026_sciad_reduction_rounding_increment",
    "sc_pit_2026_regular_workday_count_ceiling",
    "sc_pit_2026_public_safety_daily_deduction",
    "sc_pit_2026_two_wage_earner_tenths_percent",
    "sc_pit_2026_tenths_percent_rate_divisor",
    "sc_pit_2026_two_wage_earner_rate",
    "sc_pit_2026_two_wage_earner_income_cap",
    "sc_pit_2026_nursing_care_credit_rate",
    "sc_pit_2026_nursing_care_credit_cap",
    "sc_pit_2026_eitc_match_rate",
    "sc_pit_2026_eitc_credit_cap",
    "sc_pit_2026_candidate_federal_section_63_deduction_addback",
    # The committed first draft used this narrower name.  Retain its exact
    # disposition while the accepted Act 110 repair moves to the full section
    # 63 reversal above.
    "sc_pit_2026_candidate_itemized_tax_addback",
    "sc_pit_2026_candidate_additions",
    "sc_pit_2026_candidate_article_9_subtractions",
    "sc_pit_2026_candidate_state_income",
    "sc_pit_2026_candidate_sciad_base",
    "sc_pit_2026_candidate_sciad_phaseout_start",
    "sc_pit_2026_candidate_sciad_phaseout_denominator",
    "sc_pit_2026_candidate_sciad_reduction",
    "sc_pit_2026_candidate_sciad",
    "sc_pit_2026_candidate_net_capital_gain_deduction",
    "sc_pit_2026_candidate_primary_retirement_deduction",
    "sc_pit_2026_candidate_spouse_retirement_deduction",
    "sc_pit_2026_candidate_public_safety_subsistence_deduction",
    "sc_pit_2026_candidate_deductions_and_exemptions",
    "sc_pit_2026_candidate_taxable_income",
    "sc_pit_2026_candidate_tax_before_credits",
    "sc_pit_2026_candidate_primary_qualified_earned_income",
    "sc_pit_2026_candidate_spouse_qualified_earned_income",
    "sc_pit_2026_candidate_two_wage_earner_credit",
    "sc_pit_2026_candidate_nursing_care_credit",
    "sc_pit_2026_candidate_earned_income_credit",
    "sc_pit_2026_candidate_nonrefundable_credits",
    "sc_pit_2026_candidate_tax_after_nonrefundable_credits",
    "sc_pit_2026_candidate_net_income_tax_liability",
    "sc_pit_2026_supported_state_income",
    "sc_pit_2026_supported_deductions_and_exemptions",
    "sc_pit_2026_supported_taxable_income",
    "sc_pit_2026_supported_tax_before_credits",
    "sc_pit_2026_supported_tax_after_nonrefundable_credits",
    "sc_pit_2026_supported_net_income_tax_liability",
}

DIRECT_VARIABLES = {
    "sc_pit_2026_candidate_sciad": "sc_sciad",
    "sc_pit_2026_candidate_net_capital_gain_deduction": (
        "sc_net_capital_gain_deduction"
    ),
    "sc_pit_2026_candidate_taxable_income": "sc_taxable_income",
    "sc_pit_2026_candidate_tax_before_credits": (
        "sc_income_tax_before_non_refundable_credits"
    ),
    "sc_pit_2026_candidate_two_wage_earner_credit": (
        "sc_two_wage_earner_credit_potential"
    ),
    "sc_pit_2026_candidate_earned_income_credit": "sc_eitc_potential",
}

PARAMETER_OUTPUTS = {
    "sc_pit_2026_lower_rate",
    "sc_pit_2026_upper_rate",
    "sc_pit_2026_upper_bracket_floor",
    "sc_pit_2026_net_capital_gain_deduction_rate",
    "sc_pit_2026_under_65_retirement_cap",
    "sc_pit_2026_age_65_threshold",
    "sc_pit_2026_sciad_single_or_separate_base",
    "sc_pit_2026_sciad_head_base",
    "sc_pit_2026_sciad_joint_or_surviving_base",
    "sc_pit_2026_sciad_single_or_separate_phaseout_start",
    "sc_pit_2026_sciad_head_phaseout_start",
    "sc_pit_2026_sciad_joint_or_surviving_phaseout_start",
    "sc_pit_2026_sciad_single_or_separate_phaseout_denominator",
    "sc_pit_2026_sciad_head_phaseout_denominator",
    "sc_pit_2026_sciad_joint_or_surviving_phaseout_denominator",
    "sc_pit_2026_two_wage_earner_rate",
    "sc_pit_2026_two_wage_earner_income_cap",
    "sc_pit_2026_eitc_match_rate",
    "sc_pit_2026_eitc_credit_cap",
}


def test_sc_2026_core_never_uses_the_generic_state_fallback() -> None:
    registry = load_policyengine_registry()
    for output_name in OUTPUT_NAMES:
        mapping = registry.mapping_for_legal_id(f"{MODULE}#{output_name}", country="us")
        assert mapping is not None, output_name
        assert mapping.match_type == "exact", output_name
        assert mapping.legal_id == f"{MODULE}#{output_name}", output_name
        assert mapping.rationale
        assert "agency policy manuals or state regulations" not in mapping.rationale


def test_sc_2026_core_direct_and_parameter_surfaces_are_truthful() -> None:
    registry = load_policyengine_registry()
    mappings = {
        output_name: registry.mapping_for_legal_id(
            f"{MODULE}#{output_name}", country="us"
        )
        for output_name in OUTPUT_NAMES
    }

    assert {
        output_name: mapping.policyengine_variable
        for output_name, mapping in mappings.items()
        if mapping.mapping_type == "direct_variable"
    } == DIRECT_VARIABLES
    assert {
        output_name
        for output_name, mapping in mappings.items()
        if mapping.mapping_type == "parameter_value"
    } == PARAMETER_OUTPUTS
    assert all(
        mapping.mapping_type == "not_comparable"
        for output_name, mapping in mappings.items()
        if output_name not in set(DIRECT_VARIABLES) | PARAMETER_OUTPUTS
    )


def test_sc_2026_comparable_stages_are_in_the_concept_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load(
        (root / "axiom_oracles/config/concept_mappings.yaml").read_text()
    )
    mappings = payload["concepts"]

    for output_name, policyengine_variable in DIRECT_VARIABLES.items():
        legal_id = f"{MODULE}#{output_name}"
        assert mappings[legal_id]["targets"]["policyengine"] == policyengine_variable
        assert mappings[legal_id]["targets"]["axiom"]["name"] == output_name
