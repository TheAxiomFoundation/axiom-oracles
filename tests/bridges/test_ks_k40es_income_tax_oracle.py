from axiom_oracles.bridges.registry import load_policyengine_registry


MODULE = "us-ks:policies/income_tax/2026_k40es_schedule_before_credits"
EXPECTED_OUTPUTS = {
    "ks_pit_2026_k40es_lower_rate",
    "ks_pit_2026_k40es_upper_rate",
    "ks_pit_2026_k40es_joint_lower_bracket_ceiling",
    "ks_pit_2026_k40es_other_lower_bracket_ceiling",
    "ks_pit_2026_k40es_taxable_income_boundary",
    "ks_pit_2026_k40es_schedule_before_credits",
}


def _mapping(output: str):
    mapping = load_policyengine_registry().mapping_for_legal_id(
        f"{MODULE}#{output}",
        country="us",
    )
    assert mapping is not None
    return mapping


def test_k40es_has_exact_mapping_for_every_canonical_output() -> None:
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


def test_k40es_rates_use_exact_policyengine_scale_entries() -> None:
    for output, index in (
        ("ks_pit_2026_k40es_lower_rate", 0),
        ("ks_pit_2026_k40es_upper_rate", 1),
    ):
        mapping = _mapping(output)
        assert mapping.mapping_type == "parameter_value"
        assert mapping.policyengine_parameter == (
            "gov.states.ks.tax.income.rates.joint"
        )
        assert mapping.parameter_key_path == ("rates", index)
        assert mapping.period == "year"
        assert mapping.comparison == "rate"


def test_k40es_ceiling_representation_difference_is_explicit_p4() -> None:
    for output, scale in (
        ("ks_pit_2026_k40es_joint_lower_bracket_ceiling", "joint"),
        ("ks_pit_2026_k40es_other_lower_bracket_ceiling", "other"),
    ):
        mapping = _mapping(output)
        assert mapping.mapping_type == "not_comparable"
        assert mapping.candidate_priority == "P4"
        assert mapping.policyengine_parameter == (
            f"gov.states.ks.tax.income.rates.{scale}"
        )
        assert "first dollar of the upper bracket" in mapping.rationale


def test_k40es_boundary_and_schedule_have_exact_tax_unit_targets() -> None:
    boundary = _mapping("ks_pit_2026_k40es_taxable_income_boundary")
    schedule = _mapping("ks_pit_2026_k40es_schedule_before_credits")

    assert boundary.mapping_type == "direct_variable"
    assert boundary.policyengine_variable == "ks_taxable_income"
    assert schedule.mapping_type == "direct_variable"
    assert schedule.policyengine_variable == "ks_income_tax_before_credits"
    for mapping in (boundary, schedule):
        assert (
            mapping.entity,
            mapping.period,
            mapping.unit,
            mapping.comparison,
        ) == ("tax_unit", "year", "USD", "money")


def test_k40es_exact_mappings_override_broad_kansas_p4_fallback() -> None:
    registry = load_policyengine_registry()
    exact = registry.mapping_for_legal_id(
        f"{MODULE}#ks_pit_2026_k40es_schedule_before_credits",
        country="us",
    )
    fallback = registry.mapping_for_legal_id(
        f"{MODULE}#future_unmapped_output",
        country="us",
    )

    assert exact is not None
    assert exact.match_type == "exact"
    assert exact.mapping_type == "direct_variable"
    assert fallback is not None
    assert fallback.legal_id == "us-ks:"
    assert fallback.match_type == "prefix"
    assert fallback.mapping_type == "not_comparable"
    assert fallback.candidate_priority == "P4"
