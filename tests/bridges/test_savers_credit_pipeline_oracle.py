"""Defensive mapping contract for the Saver's Credit pipeline."""

from axiom_oracles.bridges import load_policyengine_registry


PIPELINE = "us:policies/income_tax/savers_credit_pipeline"


def test_savers_credit_pipeline_final_maps_to_pre_section_26_pe_surface():
    registry = load_policyengine_registry()
    mapping = registry.mapping_for_legal_id(
        f"{PIPELINE}#federal_savers_credit",
        country="us",
    )

    assert mapping is not None
    assert mapping.mapping_type == "direct_variable"
    assert mapping.policyengine_variable == "savers_credit_potential"
    assert mapping.entity == "tax_unit"
    assert mapping.period == "year"
    assert mapping.unit == "USD"
    assert mapping.comparison == "money"
    assert mapping.comparable is True


def test_every_other_savers_credit_pipeline_output_is_explicitly_not_comparable():
    registry = load_policyengine_registry()
    outputs = {
        "pipeline_savers_credit_modified_adjusted_gross_income",
        "pipeline_tier_50_applicable_ceiling_for_return_category",
        "pipeline_tier_20_applicable_ceiling_for_return_category",
        "pipeline_tier_10_applicable_ceiling_for_return_category",
        "pipeline_savers_credit_filing_status_is_enumerated",
        "pipeline_savers_credit_applicable_percentage",
        "primary_savers_credit_eligible",
        "spouse_savers_credit_eligible",
        "primary_savers_credit_contributions_taken_into_account",
        "spouse_savers_credit_contributions_taken_into_account",
    }

    for output in outputs:
        mapping = registry.mapping_for_legal_id(
            f"{PIPELINE}#{output}",
            country="us",
        )
        assert mapping is not None, output
        assert mapping.mapping_type == "not_comparable", output
        assert mapping.comparable is False, output
        assert mapping.rationale, output
