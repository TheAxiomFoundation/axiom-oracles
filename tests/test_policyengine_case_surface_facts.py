"""PolicyEngine case-surface facts and the Arizona SNAP medical projection.

The Arizona medical-deduction slots read SNAP medical expenses that
PolicyEngine prices on the Case surface its leg compares. These tests pin
three things without PolicyEngine installed: the facts land on the right
people, the mapping turns them into the four Arizona inputs, and the CLI
runs PolicyEngine for them only when the compiled program reads them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiom_oracles import cli
from axiom_oracles.adapters.axiom.populace_mapping_loader import (
    facts_read_by_program,
    load_populace_mapping_for_program,
)
from axiom_oracles.adapters.policyengine import case_surface_facts
from axiom_oracles.adapters.policyengine.case_surface_facts import (
    attach_policyengine_case_surface_facts,
)
from axiom_oracles.core.case import Case, Concepts, Entity

MEDICAL = Concepts.SNAP_ALLOWABLE_MEDICAL_EXPENSES
ELDERLY_OR_DISABLED = Concepts.USDA_ELDERLY_OR_DISABLED

AZ_MEDICAL_SLOTS = (
    "monthly_combined_out_of_pocket_medical_expenses",
    "verified_out_of_pocket_medical_expenses",
    "budgetary_unit_includes_elderly_or_disabled_participant_with_medical_expenses",
    "medical_expenses_belong_to_and_are_billed_to_elderly_or_disabled_participant",
)
AZ_DEFAULT_FALSE_SLOTS = (
    "deceased_participant_would_have_been_eligible_in_month_expense_was_billed",
    "remaining_budgetary_unit_participants_are_legally_responsible_for_bill",
    "participant_is_eligible_for_and_receiving_ssi",
    "ssi_recipient_expenses_incurred_from_later_of_na_application_or_ssi_eligibility_begin_date",
)


def _program(inputs: list[str]) -> dict:
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


def _person(entity_id: str, age: int, **facts) -> Entity:
    return Entity(
        entity_id=entity_id,
        kind="person",
        facts={Concepts.PERSON_AGE: age, **facts},
    )


def _case(case_id: str, *people: Entity) -> Case:
    return Case(
        case_id=case_id,
        period="2026-01",
        entities=people,
        facts={Concepts.STATE_CODE: "AZ"},
    )


class _Population:
    def __init__(self, ids):
        self.ids = ids


class _FakeSimulation:
    """Answers per-person YEAR variables keyed by situation person id."""

    def __init__(self, situation: dict, values: dict[str, dict[str, object]]):
        self.situation = situation
        self.ids = list(situation["people"])
        self.populations = {"person": _Population(self.ids)}
        self.values = values
        self.calls: list[tuple[str, object]] = []

    def calculate(self, variable: str, period):
        self.calls.append((variable, period))
        return [self.values[variable].get(person, 0) for person in self.ids]


def test_attach_puts_policyengine_values_on_the_matching_people() -> None:
    cases = [
        _case("a", _person("p-1", 70), _person("p-2", 30)),
        _case("b", _person("p-1", 45, **{Concepts.DISABLED: True})),
    ]
    values = {
        "snap_allowable_medical_expenses": {
            "case_0__p-1": 2434.8,
            "case_0__p-2": 600.0,
            "case_1__p-1": 1200.004,
        },
        "is_usda_elderly": {"case_0__p-1": True},
        "is_usda_disabled": {"case_1__p-1": True},
    }
    built: list[_FakeSimulation] = []

    def factory(situation):
        built.append(_FakeSimulation(situation, values))
        return built[0]

    attached = attach_policyengine_case_surface_facts(
        cases, policyengine_variables=["snap"], simulation_factory=factory
    )

    first, second = attached
    assert first.entities[0].facts[MEDICAL] == 2434.8
    assert first.entities[0].facts[ELDERLY_OR_DISABLED] is True
    assert first.entities[1].facts[MEDICAL] == 600.0
    assert first.entities[1].facts[ELDERLY_OR_DISABLED] is False
    assert second.entities[0].facts[MEDICAL] == 1200.0
    assert second.entities[0].facts[ELDERLY_OR_DISABLED] is True
    # Existing facts stay; the situation is the PolicyEngine leg's own.
    assert second.entities[0].facts[Concepts.DISABLED] is True
    assert set(built[0].situation["people"]) == {
        "case_0__p-1",
        "case_0__p-2",
        "case_1__p-1",
    }
    # YEAR variables are read at the case year.
    assert {period for _variable, period in built[0].calls} == {2026}


def test_attach_refuses_mixed_periods() -> None:
    cases = [
        _case("a", _person("p-1", 70)),
        Case(case_id="b", period="2026-02", entities=(_person("p-1", 70),)),
    ]
    with pytest.raises(RuntimeError, match="one period per batch"):
        attach_policyengine_case_surface_facts(
            cases, simulation_factory=lambda situation: None
        )


def test_default_yaml_projects_arizona_medical_slots_from_case_surface_facts() -> None:
    program = _program([*AZ_MEDICAL_SLOTS, *AZ_DEFAULT_FALSE_SLOTS])
    mapping = load_populace_mapping_for_program(program)
    people = [
        {MEDICAL: 2434.8, ELDERLY_OR_DISABLED: True},
        {MEDICAL: 1200.0, ELDERLY_OR_DISABLED: True},
        # Not elderly or disabled: PolicyEngine's deduction ignores these.
        {MEDICAL: 6000.0, ELDERLY_OR_DISABLED: False},
    ]
    case_facts = {"__people__": people}

    monthly = mapping["monthly_combined_out_of_pocket_medical_expenses"]
    verified = mapping["verified_out_of_pocket_medical_expenses"]
    assert monthly(case_facts, None) == round((2434.8 + 1200.0) / 12, 2)
    # Comparison assumption: every projected expense is verified.
    assert verified(case_facts, None) == monthly(case_facts, None)
    for slot in AZ_MEDICAL_SLOTS[2:]:
        assert mapping[slot](case_facts, None) is True
        assert mapping[slot]({"__people__": people[2:]}, None) is False
    assert monthly({"__people__": people[2:]}, None) == 0
    for slot in AZ_DEFAULT_FALSE_SLOTS:
        assert slot not in mapping


def test_suffix_of_another_state_slot_is_not_mapped() -> None:
    # South Carolina's manual declares a longer slot with the same ending.
    program = _program(["applicant_verified_out_of_pocket_medical_expenses"])
    assert load_populace_mapping_for_program(program) == {}
    assert facts_read_by_program(program).isdisjoint({MEDICAL, ELDERLY_OR_DISABLED})


def test_facts_read_by_program_names_case_surface_facts_only_when_slots_exist() -> None:
    assert {MEDICAL, ELDERLY_OR_DISABLED} <= facts_read_by_program(
        _program(list(AZ_MEDICAL_SLOTS))
    )
    plain = facts_read_by_program(
        _program(["household_size", "snap_gross_monthly_earned_income"])
    )
    assert Concepts.YEARLY_EARNED_INCOME in plain
    assert plain.isdisjoint({MEDICAL, ELDERLY_OR_DISABLED})


def _write_compiled(tmp_path: Path, inputs: list[str]) -> Path:
    path = tmp_path / "compiled.json"
    path.write_text(json.dumps({"program": _program(inputs)}))
    return path


def test_cli_skips_policyengine_when_program_reads_no_case_surface_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("PolicyEngine must not run for this program")

    monkeypatch.setattr(
        case_surface_facts, "attach_policyengine_case_surface_facts", fail
    )
    cases = [_case("a", _person("p-1", 70))]
    compiled = _write_compiled(tmp_path, ["household_size"])
    assert (
        cli._attach_case_surface_facts_if_read(
            cases, compiled, ("us:statutes/7/2014/u#snap_benefit",)
        )
        is cases
    )


def test_cli_attaches_case_surface_facts_when_program_reads_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_attach(cases, *, policyengine_variables=None):
        seen["variables"] = policyengine_variables
        return [*cases, "attached"]

    monkeypatch.setattr(
        case_surface_facts, "attach_policyengine_case_surface_facts", fake_attach
    )
    cases = [_case("a", _person("p-1", 70))]
    compiled = _write_compiled(tmp_path, list(AZ_MEDICAL_SLOTS))
    result = cli._attach_case_surface_facts_if_read(
        cases, compiled, ("us:statutes/7/2014/u#snap_benefit",)
    )
    assert result[-1] == "attached"
    assert seen["variables"]
