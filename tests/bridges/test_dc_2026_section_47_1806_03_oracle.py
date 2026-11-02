"""Exact oracle-registry contract for DC's bounded TY2026 joint schedule."""

from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = (
    "us-dc:policies/income_tax/"
    "2026_section_47_1806_03_schedule_before_credits"
)
BOUNDARY = "dc_pit_2026_section_47_1806_03_taxable_income_boundary"
SCHEDULE = "dc_pit_2026_section_47_1806_03_schedule_before_credits"
P4_INTERNALS = {
    "dc_pit_2026_section_47_1806_03_bracket_upper",
    "dc_pit_2026_section_47_1806_03_bracket_floor",
    "dc_pit_2026_section_47_1806_03_bracket_base",
    "dc_pit_2026_section_47_1806_03_bracket_rate",
    "dc_pit_2026_section_47_1806_03_bracket_selector",
}
EXPECTED_OUTPUTS = {BOUNDARY, SCHEDULE, *P4_INTERNALS}


def _mapping(output: str):
    mapping = load_policyengine_registry().mapping_for_legal_id(
        f"{MODULE}#{output}",
        country="us",
    )
    assert mapping is not None
    return mapping


def test_dc_schedule_has_exact_mapping_for_every_rulespec_output() -> None:
    registry = load_policyengine_registry()
    prefix = f"{MODULE}#"
    mapped_outputs = {
        legal_id.removeprefix(prefix)
        for legal_id in registry.mappings_by_legal_id
        if legal_id.startswith(prefix)
    }

    assert mapped_outputs == EXPECTED_OUTPUTS
    for output in EXPECTED_OUTPUTS:
        mapping = _mapping(output)
        assert mapping.match_type == "exact"
        assert mapping.program == "tax"


def test_dc_boundary_and_schedule_use_only_exact_joint_method_targets() -> None:
    boundary = _mapping(BOUNDARY)
    schedule = _mapping(SCHEDULE)

    assert boundary.mapping_type == "direct_variable"
    assert boundary.policyengine_variable == "dc_taxable_income_joint"
    assert schedule.mapping_type == "direct_variable"
    assert schedule.policyengine_variable == "dc_income_tax_before_credits_joint"
    assert "dc_income_tax_before_credits" not in {
        boundary.policyengine_variable,
        schedule.policyengine_variable,
    }
    for mapping in (boundary, schedule):
        assert (
            mapping.entity,
            mapping.period,
            mapping.unit,
            mapping.comparison,
        ) == ("tax_unit", "year", "USD", "money")


def test_dc_internal_tables_and_selector_are_explicit_p4_records() -> None:
    for output in P4_INTERNALS:
        mapping = _mapping(output)
        assert mapping.mapping_type == "not_comparable"
        assert mapping.candidate_priority == "P4"
        assert mapping.policyengine_variable is None


def test_dc_exact_mappings_override_broad_district_p4_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(f"{MODULE}#{SCHEDULE}", country="us")
    fallback = registry.mapping_for_legal_id(
        f"{MODULE}#future_unmapped_output",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert fallback is not None
    assert fallback.legal_id == "us-dc:"
    assert fallback.match_type == "prefix"
    assert fallback.mapping_type == "not_comparable"
    assert fallback.candidate_priority == "P4"
