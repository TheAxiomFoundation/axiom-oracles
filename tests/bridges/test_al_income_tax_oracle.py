"""Exact oracle-registry contract for Alabama Code section 40-18-5."""

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = (
    "us-al:policies/income_tax/"
    "2026_section_40_18_5_schedule_before_credits"
)
EXPECTED_OUTPUTS = {
    "al_pit_2026_section_40_18_5_first_rate",
    "al_pit_2026_section_40_18_5_second_rate",
    "al_pit_2026_section_40_18_5_third_rate",
    "al_pit_2026_section_40_18_5_nonjoint_first_bracket_ceiling",
    "al_pit_2026_section_40_18_5_nonjoint_second_bracket_ceiling",
    "al_pit_2026_section_40_18_5_joint_first_bracket_ceiling",
    "al_pit_2026_section_40_18_5_joint_second_bracket_ceiling",
    "al_pit_2026_section_40_18_5_taxable_income_boundary",
    "al_pit_2026_section_40_18_5_schedule_before_credits",
}


def _mapping(rule: str):
    registry = load_policyengine_registry()
    mapping = registry.mapping_for_legal_id(f"{MODULE}#{rule}", country="us")
    assert mapping is not None
    assert mapping.match_type == "exact"
    return mapping


def test_alabama_schedule_mapping_inventory_is_exactly_complete():
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    mapped_names = {
        legal_id.removeprefix(prefix)
        for legal_id in registry.mappings_by_legal_id
        if legal_id.startswith(prefix)
    }

    assert len(mapped_names) == 9
    assert mapped_names == EXPECTED_OUTPUTS


def test_alabama_public_schedule_has_exact_pre_credit_target():
    mapping = _mapping(
        "al_pit_2026_section_40_18_5_schedule_before_credits"
    )
    assert mapping.mapping_type == "direct_variable"
    assert mapping.policyengine_variable == (
        "al_income_tax_before_non_refundable_credits"
    )
    assert (mapping.entity, mapping.period, mapping.unit, mapping.comparison) == (
        "tax_unit",
        "year",
        "USD",
        "money",
    )


def test_alabama_private_parameters_and_boundary_are_exact():
    expected_parameters = {
        "al_pit_2026_section_40_18_5_first_rate": (
            "gov.states.al.tax.income.rates.single",
            ("rates", 0),
        ),
        "al_pit_2026_section_40_18_5_second_rate": (
            "gov.states.al.tax.income.rates.single",
            ("rates", 1),
        ),
        "al_pit_2026_section_40_18_5_third_rate": (
            "gov.states.al.tax.income.rates.single",
            ("rates", 2),
        ),
        "al_pit_2026_section_40_18_5_nonjoint_first_bracket_ceiling": (
            "gov.states.al.tax.income.rates.single",
            ("thresholds", 1),
        ),
        "al_pit_2026_section_40_18_5_nonjoint_second_bracket_ceiling": (
            "gov.states.al.tax.income.rates.single",
            ("thresholds", 2),
        ),
        "al_pit_2026_section_40_18_5_joint_first_bracket_ceiling": (
            "gov.states.al.tax.income.rates.joint",
            ("thresholds", 1),
        ),
        "al_pit_2026_section_40_18_5_joint_second_bracket_ceiling": (
            "gov.states.al.tax.income.rates.joint",
            ("thresholds", 2),
        ),
    }
    for rule, (parameter, key_path) in expected_parameters.items():
        mapping = _mapping(rule)
        assert mapping.mapping_type == "parameter_value"
        assert mapping.policyengine_parameter == parameter
        assert mapping.parameter_key_path == key_path

    boundary = _mapping(
        "al_pit_2026_section_40_18_5_taxable_income_boundary"
    )
    assert boundary.mapping_type == "direct_variable"
    assert boundary.policyengine_variable == "al_taxable_income"


def test_alabama_exact_schedule_overrides_broad_state_fallback():
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#al_pit_2026_section_40_18_5_schedule_before_credits",
        country="us",
    )
    broad_fallback = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert broad_fallback is not None
    assert broad_fallback.match_type == "prefix"
    assert broad_fallback.mapping_type == "not_comparable"
    assert broad_fallback.candidate_priority == "P4"
