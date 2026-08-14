"""Exact oracle dispositions for the legacy Mississippi pilot pipeline."""

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ms:policies/income_tax/pilot_liability_pipeline"


def _mapping(rule: str):
    mapping = load_policyengine_registry().mapping_for_legal_id(
        f"{MODULE}#{rule}", country="us"
    )
    assert mapping is not None
    assert mapping.match_type == "exact"
    return mapping


def test_ms_pilot_supplied_intermediates_are_exact_p4_noncomparables() -> None:
    taxable_income = _mapping("ms_pit_pilot_taxable_income")
    schedule_tax = _mapping("ms_pit_pilot_schedule_tax")

    assert taxable_income.mapping_type == "not_comparable"
    assert taxable_income.policyengine_variable == "ms_taxable_income_joint"
    assert taxable_income.candidate_priority == "P4"

    assert schedule_tax.mapping_type == "not_comparable"
    assert schedule_tax.policyengine_variable == "ms_income_tax_before_credits_unit"
    assert schedule_tax.candidate_priority == "P4"


def test_ms_pilot_final_before_credit_amount_has_exact_taxunit_target() -> None:
    liability = _mapping("ms_pit_pilot_income_tax_liability")

    assert liability.mapping_type == "direct_variable"
    assert liability.policyengine_variable == "ms_income_tax_before_credits_unit"
    assert (
        liability.entity,
        liability.period,
        liability.unit,
        liability.comparison,
        liability.candidate_priority,
    ) == ("tax_unit", "year", "USD", "money", "P1")
