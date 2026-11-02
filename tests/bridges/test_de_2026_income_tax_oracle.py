"""Exact oracle-registry contract for Delaware's TY2026 individual schedule."""

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-de:policies/income_tax/pilot_liability_pipeline"
SCHEDULE = "de_pit_pilot_separate_schedule_tax"
STALE_FINAL = "de_pit_pilot_income_tax_liability"


def test_de_2026_person_schedule_has_exact_policyengine_target() -> None:
    registry = load_policyengine_registry()
    mapping = registry.mapping_for_legal_id(
        f"{MODULE}#{SCHEDULE}",
        country="us",
    )

    assert mapping is not None
    assert mapping.match_type == "exact"
    assert mapping.mapping_type == "direct_variable"
    assert (
        mapping.policyengine_variable
        == "de_income_tax_before_non_refundable_credits_indv"
    )
    assert (
        mapping.entity,
        mapping.period,
        mapping.unit,
        mapping.comparison,
    ) == ("person", "year", "USD", "money")
    assert "filing-method selection" in mapping.rationale
    assert "final liability" in mapping.rationale


def test_de_2026_exact_mapping_precedes_broad_state_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#{SCHEDULE}",
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


def test_de_2026_stale_final_output_has_no_exact_liability_claim() -> None:
    registry = load_policyengine_registry()
    stale = registry.mapping_for_legal_id(
        f"{MODULE}#{STALE_FINAL}",
        country="us",
    )

    assert stale is not None
    assert stale.match_type == "prefix"
    assert stale.mapping_type == "not_comparable"
    assert stale.candidate_priority == "P4"
    assert stale.policyengine_variable is None
