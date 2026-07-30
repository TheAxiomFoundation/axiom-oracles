"""Tests for the declarative ECPS-to-input mapping loader.

These tests pin down the contract the YAML mapping table promises to the
generic projector: which slots get resolved, which mapper kinds are
supported, and how the household-level aggregation reads people facts.
The mapping itself is data — these tests guard the loader behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom_oracles.adapters.axiom.populace_mapping_loader import (
    load_populace_mapping_for_program,
)
from axiom_oracles.core.case import Concepts


def _program(inputs: list[str]) -> dict:
    """Build a minimal compiled-program shape with the given input slots.

    Mirrors the real compose output: ``derived`` is a list, each entry has
    ``entity`` and an ``expr`` tree whose leaves are ``input_check`` nodes.
    """
    return {
        "derived": [
            {
                "name": "out",
                "entity": "Household",
                "dtype": "judgment",
                "expr": {
                    "kind": "all_of",
                    "checks": [{"kind": "input", "name": name} for name in inputs],
                },
            }
        ]
    }


@pytest.fixture
def custom_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "mapping.yaml"
    path.write_text(
        """
mappings:
  - match: { kind: exact, value: household_size }
    scope: household
    source: { kind: derived, transform: hh_size }
  - match: { kind: substring, value: monthly_income }
    scope: household
    source:
      kind: derived
      transform: monthly
      from_facts: [YEARLY_EARNED_INCOME]
      aggregate: sum_over_people
  - match: { kind: exact, value: member_is_us_citizen }
    scope: person
    source: { kind: constant, value: true }
  - match: { kind: exact, value: member_age }
    scope: person
    source: { kind: fact, name: PERSON_AGE, cast: int }
  - match: { kind: exact, value: in_target_county }
    scope: household
    source:
      kind: derived
      transform: scope_geoid_in
      geoids: ["36047", "36059"]
  - match: { kind: exact, value: all_people_with_assistance }
    scope: household
    source:
      kind: derived
      transform: all_people_any_positive
      from_facts: [SSI_BENEFITS, TANF_BENEFITS]
""".strip()
    )
    return path


def test_loader_resolves_only_matching_slots(custom_yaml: Path) -> None:
    program = _program(
        ["household_size", "monthly_income", "member_is_us_citizen", "unrelated_slot"]
    )
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)
    assert set(mapping) == {
        "household_size",
        "monthly_income",
        "member_is_us_citizen",
    }


def test_hh_size_uses_people_list(custom_yaml: Path) -> None:
    program = _program(["household_size"])
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)
    case_facts = {"__people__": [{}, {}, {}]}
    assert mapping["household_size"](case_facts, None) == 3


def test_monthly_aggregation_sums_over_people(custom_yaml: Path) -> None:
    program = _program(["monthly_income"])
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)
    case_facts = {
        "__people__": [
            {Concepts.YEARLY_EARNED_INCOME: 24000},
            {Concepts.YEARLY_EARNED_INCOME: 12000},
        ]
    }
    assert mapping["monthly_income"](case_facts, None) == pytest.approx(3000.0)


def test_constant_source_ignores_facts(custom_yaml: Path) -> None:
    program = _program(["member_is_us_citizen"])
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)
    assert mapping["member_is_us_citizen"]({}, {}) is True


def test_fact_source_reads_person_scope_and_casts(custom_yaml: Path) -> None:
    program = _program(["member_age"])
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)
    value = mapping["member_age"]({}, {Concepts.PERSON_AGE: 30.0})
    assert value == 30 and isinstance(value, int)


def test_scope_geoid_in_reads_case_metadata(custom_yaml: Path) -> None:
    program = _program(["in_target_county"])
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)

    assert (
        mapping["in_target_county"](
            {"__metadata__": {"scope": {"type": "census_county", "geoid": "36047"}}},
            None,
        )
        is True
    )
    assert (
        mapping["in_target_county"](
            {"__metadata__": {"scope": {"type": "census_county", "geoid": "06037"}}},
            None,
        )
        is False
    )


def test_all_people_any_positive_requires_each_person_to_have_a_listed_fact(
    custom_yaml: Path,
) -> None:
    program = _program(["all_people_with_assistance"])
    mapping = load_populace_mapping_for_program(program, mapping_path=custom_yaml)

    assert (
        mapping["all_people_with_assistance"](
            {
                "__people__": [
                    {Concepts.SSI_BENEFITS: 1},
                    {Concepts.TANF_BENEFITS: 1},
                ]
            },
            None,
        )
        is True
    )
    assert (
        mapping["all_people_with_assistance"](
            {
                "__people__": [
                    {Concepts.SSI_BENEFITS: 1},
                    {},
                ]
            },
            None,
        )
        is False
    )


def test_default_yaml_loads_against_ca_program(tmp_path: Path) -> None:
    """Sanity check: the shipped YAML resolves at least the slots we
    deliberately added entries for (household_size, member_age, etc.).
    The exact count of matches will change as the table grows; we only
    assert the floor here so the test stays useful through additions."""
    program = _program(
        [
            "household_size",
            "member_age",
            "member_is_us_citizen",
            "snap_gross_monthly_income",
            "snap_gross_monthly_earned_income",
            "snap_total_monthly_unearned_income",
            "state_agency_rounds_thirty_percent_net_income_up",
        ]
    )
    mapping = load_populace_mapping_for_program(program)
    assert {
        "household_size",
        "member_age",
        "member_is_us_citizen",
        "snap_gross_monthly_income",
        "snap_gross_monthly_earned_income",
        "snap_total_monthly_unearned_income",
        "state_agency_rounds_thirty_percent_net_income_up",
    }.issubset(mapping)


def test_default_yaml_maps_snap_income_slots_separately() -> None:
    program = _program(
        [
            "snap_gross_monthly_earned_income",
            "snap_total_monthly_unearned_income",
            "snap_gross_monthly_income",
            "state_agency_rounds_thirty_percent_net_income_up",
        ]
    )
    mapping = load_populace_mapping_for_program(program)
    case_facts = {
        "__people__": [
            {
                Concepts.YEARLY_EARNED_INCOME: 24_000,
                Concepts.SELF_EMPLOYMENT_INCOME: 6_000,
                Concepts.TANF_BENEFITS: 6_000,
                Concepts.SSI_BENEFITS: 3_000,
                Concepts.SOCIAL_SECURITY_BENEFITS: 12_000,
                Concepts.INTEREST_INCOME: 120,
            },
            {
                Concepts.YEARLY_EARNED_INCOME: 12_000,
                Concepts.UNEMPLOYMENT_INSURANCE_INCOME: 2_400,
                Concepts.DIVIDEND_INCOME: 240,
            },
        ]
    }

    # Earned income counts wages plus self-employment net of production
    # costs (7 CFR 273.9(b)(1)(ii); 0.6 netting matching the oracle):
    # 12000/12 + 0.6*6000/12 = 1000 + 300 per person over 3 people... see
    # fixture: single person 12000 wages + 6000 SE -> 1000 + 300 = 1300;
    # fixture people sum to 3300.
    assert mapping["snap_gross_monthly_earned_income"](case_facts, None) == 3300
    assert mapping["snap_total_monthly_unearned_income"](case_facts, None) == 1980
    assert mapping["snap_gross_monthly_income"](case_facts, None) == 4980
    assert mapping["state_agency_rounds_thirty_percent_net_income_up"](
        case_facts, None
    ) is True


def test_default_yaml_maps_ecps_snap_cases_as_non_initial_months() -> None:
    program = _program(["household_initial_month"])
    mapping = load_populace_mapping_for_program(program)

    assert mapping["household_initial_month"]({}, None) is False


def test_default_yaml_leaves_calfresh_pub_275_household_facts_unmapped() -> None:
    # axiom-compose preserves these two leaves as bare compiled input names;
    # qualification happens only after the population mapping is resolved.
    issued = "household_was_issued_pub_275"
    online_access = "household_has_online_access_to_pub_275"
    mapping = load_populace_mapping_for_program(_program([issued, online_access]))

    assert issued not in mapping
    assert online_access not in mapping


def test_default_yaml_maps_snap_utility_allowance_projection_assumptions() -> None:
    program = _program(
        [
            "household_has_heating_and_cooling_costs_separate_from_rent_or_mortgage",
            "household_incurs_heating_or_cooling_expenses_separately_from_rent_or_mortgage",
            "household_in_public_housing_unit_with_central_utility_meters_charged_only_for_excess_heating_or_cooling_costs",
            "liheaa_or_similar_energy_assistance_payment_received_or_made_on_household_behalf_in_current_month_or_immediately_preceding_twelve_months",
            "liheaa_or_similar_energy_assistance_annual_payment_amount",
            "limited_utility_allowance_utility_count",
            "state_agency_mandates_use_of_standard_utility_allowances_under_paragraph_g",
        ]
    )
    mapping = load_populace_mapping_for_program(program)

    assert (
        mapping[
            "household_has_heating_and_cooling_costs_separate_from_rent_or_mortgage"
        ]({}, None)
        is True
    )
    assert (
        mapping[
            "household_incurs_heating_or_cooling_expenses_separately_from_rent_or_mortgage"
        ]({}, None)
        is True
    )
    assert (
        mapping[
            "household_in_public_housing_unit_with_central_utility_meters_charged_only_for_excess_heating_or_cooling_costs"
        ]({}, None)
        is False
    )
    assert (
        mapping[
            "liheaa_or_similar_energy_assistance_payment_received_or_made_on_household_behalf_in_current_month_or_immediately_preceding_twelve_months"
        ]({}, None)
        is False
    )
    assert mapping["liheaa_or_similar_energy_assistance_annual_payment_amount"](
        {}, None
    ) == 0
    assert mapping["limited_utility_allowance_utility_count"]({}, None) == 0
    assert (
        mapping[
            "state_agency_mandates_use_of_standard_utility_allowances_under_paragraph_g"
        ]({}, None)
        is False
    )


def test_default_yaml_maps_ma_categorical_assistance_inputs() -> None:
    program = _program(
        [
            "all_members_receive_or_authorized_for_ssi_or_eaedc",
            "all_members_receive_or_authorized_for_tafdc",
            "all_members_receive_or_authorized_for_combination_ssi_eaedc_tafdc",
        ]
    )
    mapping = load_populace_mapping_for_program(program)
    mixed_case = {
        "__people__": [
            {Concepts.SSI_BENEFITS: 1},
            {Concepts.TANF_BENEFITS: 1},
        ]
    }

    assert (
        mapping["all_members_receive_or_authorized_for_ssi_or_eaedc"](
            mixed_case, None
        )
        is False
    )
    assert mapping["all_members_receive_or_authorized_for_tafdc"](
        mixed_case, None
    ) is False
    assert (
        mapping[
            "all_members_receive_or_authorized_for_combination_ssi_eaedc_tafdc"
        ](mixed_case, None)
        is True
    )


def test_deprecated_ecps_mapping_loader_alias_resolves_to_populace_loader() -> None:
    # The loader was renamed ecps_mapping_loader -> populace_mapping_loader
    # (axiom-oracles#74). The old module path and the old
    # load_ecps_mapping_for_program name must still work (same object) and warn.
    import importlib
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with pytest.raises(DeprecationWarning):
            importlib.import_module(
                "axiom_oracles.adapters.axiom.ecps_mapping_loader"
            )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = importlib.import_module(
            "axiom_oracles.adapters.axiom.ecps_mapping_loader"
        )

    assert (
        legacy.load_ecps_mapping_for_program is load_populace_mapping_for_program
    )
