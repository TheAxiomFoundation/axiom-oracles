"""Tests for the generic input projector.

Pure-function tests — no engine binary or PolicyEngine dependency required.
"""

from __future__ import annotations

import json

from axiom_oracles.adapters.axiom.generic_inputs import (
    GenericInputRecord,
    attach_generic_inputs,
    default_for,
    enumerate_inputs,
    project_case_inputs,
)
from axiom_oracles.core.case import Case, Concepts, Entity


def _input(name: str) -> dict:
    return {"kind": "input", "name": name}


def _bool_literal(value: bool) -> dict:
    return {"kind": "literal", "value": {"kind": "bool", "value": value}}


def _decimal_literal(value: str) -> dict:
    return {"kind": "literal", "value": {"kind": "decimal", "value": value}}


# ---------------------------------------------------------------------------
# enumerate_inputs / type inference
# ---------------------------------------------------------------------------


def test_enumerate_inputs_returns_one_slot_per_unique_name() -> None:
    program = {
        "derived": [
            {
                "name": "rule_a",
                "entity": "Person",
                "expr": {
                    "kind": "and",
                    "items": [_input("flag_x"), _input("flag_y")],
                },
            },
            {
                "name": "rule_b",
                "entity": "Person",
                "expr": _input("flag_x"),  # duplicate
            },
        ],
    }
    slots = enumerate_inputs(program)
    names = [s.name for s in slots]
    assert names == ["flag_x", "flag_y"]
    assert all(s.entity == "Person" for s in slots)


def test_boolean_op_input_inferred_as_judgment() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Person",
                "expr": {
                    "kind": "and",
                    "items": [_input("flag"), _bool_literal(True)],
                },
            }
        ],
    }
    [slot] = enumerate_inputs(program)
    assert slot.dtype == "Judgment"


def test_comparison_with_bool_literal_inferred_as_judgment() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "expr": {
                    "kind": "comparison",
                    "left": _input("resident_of_shelter"),
                    "op": "eq",
                    "right": _bool_literal(True),
                },
            }
        ],
    }
    [slot] = enumerate_inputs(program)
    assert slot.dtype == "Judgment"


def test_comparison_with_decimal_literal_inferred_as_decimal() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "expr": {
                    "kind": "comparison",
                    "left": _input("monthly_income"),
                    "op": "lt",
                    "right": _decimal_literal("1000"),
                },
            }
        ],
    }
    [slot] = enumerate_inputs(program)
    assert slot.dtype == "Decimal"


def test_arithmetic_op_input_inferred_as_decimal() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "expr": {
                    "kind": "add",
                    "items": [_input("wages"), _input("benefits")],
                },
            }
        ],
    }
    slots = enumerate_inputs(program)
    assert all(s.dtype == "Decimal" for s in slots)


def test_root_input_uses_containing_rule_dtype() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "dtype": "decimal",
                "expr": _input("household_shelter_costs_incurred"),
            }
        ],
    }

    [slot] = enumerate_inputs(program)

    assert slot.dtype == "Decimal"


def test_if_condition_is_judgment_but_branches_inherit_rule_dtype() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "dtype": "decimal",
                "expr": {
                    "kind": "if",
                    "condition": _input("has_self_employment"),
                    "then_expr": _input("annual_self_employment_income"),
                    "else_expr": _decimal_literal("0"),
                },
            }
        ],
    }

    slots = {slot.name: slot for slot in enumerate_inputs(program)}

    assert slots["has_self_employment"].dtype == "Judgment"
    assert slots["annual_self_employment_income"].dtype == "Decimal"


def test_more_specific_entity_wins_when_input_appears_in_multiple_rules() -> None:
    program = {
        "derived": [
            {"name": "hh_rule", "entity": "Household", "expr": _input("shared_input")},
            {"name": "person_rule", "entity": "Person", "expr": _input("shared_input")},
        ],
    }
    [slot] = enumerate_inputs(program)
    assert slot.entity == "Person"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_default_for_judgment_is_false() -> None:
    assert default_for("Judgment") is False


def test_default_for_decimal_is_zero() -> None:
    assert default_for("Decimal") == 0
    assert default_for("Money") == 0
    assert default_for("Integer") == 0


# ---------------------------------------------------------------------------
# project_case_inputs
# ---------------------------------------------------------------------------


def test_project_case_inputs_defaults_all_slots_to_type_zero() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "expr": {
                    "kind": "and",
                    "items": [_input("flag"), _input("other_flag")],
                },
            }
        ],
    }
    records = project_case_inputs(
        compiled_program=program,
        household_id="hh-1",
        person_ids=[],
    )
    assert len(records) == 2
    for r in records:
        assert r.value is False  # Judgment default
        assert r.entity == "Household"
        assert r.entity_id == "hh-1"


def test_project_case_inputs_emits_per_person_for_person_scoped_slots() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Person",
                "expr": {
                    "kind": "and",
                    "items": [_input("flag")],
                },
            }
        ],
    }
    records = project_case_inputs(
        compiled_program=program,
        household_id="hh-1",
        person_ids=["p-1", "p-2"],
    )
    assert len(records) == 2
    assert {r.entity_id for r in records} == {"p-1", "p-2"}


def test_project_case_inputs_ecps_mapping_overrides_default() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "expr": {
                    "kind": "comparison",
                    "left": _input("monthly_income"),
                    "op": "lt",
                    "right": _decimal_literal("1000"),
                },
            }
        ],
    }
    records = project_case_inputs(
        compiled_program=program,
        household_id="hh-1",
        person_ids=[],
        ecps_mapping={"monthly_income": lambda case, person: 1500},
    )
    [r] = records
    assert r.value == 1500


def test_project_case_inputs_falls_back_to_case_facts_by_unqualified_name() -> None:
    program = {
        "derived": [
            {
                "name": "rule",
                "entity": "Household",
                "expr": {
                    "kind": "and",
                    "items": [_input("us:regulations/7-cfr/273/10#input.is_homeless")],
                },
            }
        ],
    }
    records = project_case_inputs(
        compiled_program=program,
        household_id="hh-1",
        person_ids=[],
        case_facts={"is_homeless": True},
    )
    [r] = records
    assert r.value is True


def test_attach_generic_inputs_passes_household_facts_to_mapping(tmp_path) -> None:
    compiled = {
        "program": {
            "derived": [
                {
                    "name": "rule",
                    "entity": "Household",
                    "expr": {
                        "kind": "add",
                        "items": [_input("household_shelter_costs_incurred")],
                    },
                }
            ]
        }
    }
    compiled_path = tmp_path / "program.compiled.json"
    compiled_path.write_text(json.dumps(compiled))
    case = Case(
        case_id="case-1",
        period="2026-01",
        facts={Concepts.RENT_PAID: 12_000},
        entities=(Entity("person-1", "person", facts={}),),
    )

    [projected] = attach_generic_inputs(
        [case],
        compiled_program_path=compiled_path,
    )

    record = next(
        item
        for item in projected.metadata["axiom_input_records"]
        if item["name"].endswith("#input.household_shelter_costs_incurred")
    )
    assert record["value"] == {"kind": "decimal", "value": "1000.0"}


def test_generic_input_record_to_dict_emits_scalar_value_spec() -> None:
    interval = {"start": "2026-01-01", "end": "2026-01-31"}
    record = GenericInputRecord(
        name="some_input",
        entity="Household",
        entity_id="hh-1",
        value=True,
        dtype="Judgment",
    )
    payload = record.to_dict(interval)
    assert payload["value"] == {"kind": "bool", "value": True}
    assert payload["entity"] == "Household"
    assert payload["interval"] == interval
