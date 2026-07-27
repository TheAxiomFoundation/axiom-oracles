"""Exact oracle-registry contract for Utah's canonical TY2026 schedule."""

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = (
    "us-ut:policies/income_tax/"
    "2026_full_year_resident_before_credit_schedule"
)
EXPECTED_OUTPUTS = {
    "ut_pit_2026_input_domain_is_valid",
    "ut_pit_2026_before_credit_schedule_applies",
    "ut_pit_2026_income_tax_rate",
    "ut_pit_2026_resident_state_taxable_income_boundary",
    "ut_pit_2026_resident_income_tax_before_credits",
    "ut_pit_2026_taxpayer_credit_source_hold_applies",
    "ut_pit_2026_final_resident_liability_source_hold_applies",
    "ut_pit_2026_taxpayer_tax_credit",
    "ut_pit_2026_final_resident_income_tax_liability_before_payments",
}


def _mapping(rule: str):
    registry = load_policyengine_registry()
    mapping = registry.mapping_for_legal_id(f"{MODULE}#{rule}", country="us")
    assert mapping is not None
    assert mapping.match_type == "exact"
    return mapping


def test_ut_2026_registry_has_exact_records_for_the_canonical_output_set() -> None:
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    mapped_names = {
        legal_id.removeprefix(prefix)
        for legal_id in registry.mappings_by_legal_id
        if legal_id.startswith(prefix)
    }

    assert mapped_names == EXPECTED_OUTPUTS


def test_ut_2026_rate_maps_to_the_exact_policyengine_parameter() -> None:
    mapping = _mapping("ut_pit_2026_income_tax_rate")

    assert mapping.mapping_type == "parameter_value"
    assert mapping.policyengine_parameter == "gov.states.ut.tax.income.rate"
    assert mapping.period == "year"
    assert mapping.comparison == "rate"


def test_ut_2026_schedule_uses_the_exemption_aware_derived_target() -> None:
    mapping = _mapping("ut_pit_2026_resident_income_tax_before_credits")

    assert mapping.mapping_type == "derived_expression"
    assert (
        mapping.expression
        == "ut_income_tax_before_credits * (1 - ut_income_tax_exempt)"
    )
    assert (mapping.entity, mapping.period, mapping.unit, mapping.comparison) == (
        "tax_unit",
        "year",
        "USD",
        "money",
    )


def test_ut_2026_guards_holds_and_sentinels_are_fail_closed() -> None:
    comparable = {
        "ut_pit_2026_income_tax_rate",
        "ut_pit_2026_resident_income_tax_before_credits",
    }
    for rule in EXPECTED_OUTPUTS - comparable:
        mapping = _mapping(rule)
        assert mapping.mapping_type == "not_comparable"
        assert mapping.candidate_priority == "P4"


def test_ut_2026_exact_records_precede_the_broad_state_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#ut_pit_2026_resident_income_tax_before_credits",
        country="us",
    )
    broad_fallback = registry.mapping_for_legal_id(
        f"{MODULE}#unmapped_diagnostic",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "derived_expression"
    assert broad_fallback is not None
    assert broad_fallback.match_type == "prefix"
    assert broad_fallback.mapping_type == "not_comparable"
    assert broad_fallback.candidate_priority == "P4"
