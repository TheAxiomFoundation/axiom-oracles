"""Tests for the declarative ECPS-to-input mapping loader.

These tests pin down the contract the YAML mapping table promises to the
generic projector: which slots get resolved, which mapper kinds are
supported, and how the household-level aggregation reads people facts.
The mapping itself is data — these tests guard the loader behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom_oracles.adapters.axiom.ecps_mapping_loader import (
    load_ecps_mapping_for_program,
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
""".strip()
    )
    return path


def test_loader_resolves_only_matching_slots(custom_yaml: Path) -> None:
    program = _program(
        ["household_size", "monthly_income", "member_is_us_citizen", "unrelated_slot"]
    )
    mapping = load_ecps_mapping_for_program(program, mapping_path=custom_yaml)
    assert set(mapping) == {
        "household_size",
        "monthly_income",
        "member_is_us_citizen",
    }


def test_hh_size_uses_people_list(custom_yaml: Path) -> None:
    program = _program(["household_size"])
    mapping = load_ecps_mapping_for_program(program, mapping_path=custom_yaml)
    case_facts = {"__people__": [{}, {}, {}]}
    assert mapping["household_size"](case_facts, None) == 3


def test_monthly_aggregation_sums_over_people(custom_yaml: Path) -> None:
    program = _program(["monthly_income"])
    mapping = load_ecps_mapping_for_program(program, mapping_path=custom_yaml)
    case_facts = {
        "__people__": [
            {Concepts.YEARLY_EARNED_INCOME: 24000},
            {Concepts.YEARLY_EARNED_INCOME: 12000},
        ]
    }
    assert mapping["monthly_income"](case_facts, None) == pytest.approx(3000.0)


def test_constant_source_ignores_facts(custom_yaml: Path) -> None:
    program = _program(["member_is_us_citizen"])
    mapping = load_ecps_mapping_for_program(program, mapping_path=custom_yaml)
    assert mapping["member_is_us_citizen"]({}, {}) is True


def test_fact_source_reads_person_scope_and_casts(custom_yaml: Path) -> None:
    program = _program(["member_age"])
    mapping = load_ecps_mapping_for_program(program, mapping_path=custom_yaml)
    value = mapping["member_age"]({}, {Concepts.PERSON_AGE: 30.0})
    assert value == 30 and isinstance(value, int)


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
        ]
    )
    mapping = load_ecps_mapping_for_program(program)
    assert {
        "household_size",
        "member_age",
        "member_is_us_citizen",
        "snap_gross_monthly_income",
    }.issubset(mapping)
