"""The Arizona SNAP screener grid and the screener-fact projections.

The grid must stay deterministic, bounded and synthetic. The screener facts
must reach both engines for screener Cases, and must leave population Cases
(which carry none of them) projected exactly as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom_oracles.adapters.axiom.populace_mapping_loader import (
    load_populace_mapping_for_program,
)
from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.suites import available_suites, load_suite
from axiom_oracles.suites.us_az_snap_screener import (
    FY2026,
    PATHS,
    guideline_monthly,
    households,
    path_of,
    standard_deduction_fy2026,
    us_az_snap_screener_fy2027_cases,
)

REPO = Path(__file__).resolve().parents[1]

SCREENER_SLOTS = (
    "snap_claimed_homeless_shelter_deduction",
    "snap_allowable_monthly_child_support_payments",
    "snap_total_medical_expenses",
    "household_entitled_to_excess_medical_deduction",
    "budgetary_unit_obligated_to_pay_heating_or_cooling_expense_separately_from_rent_or_mortgage_on_regular_basis",
    "budgetary_unit_heating_or_cooling_expenses_exceed_energy_assistance_payments",
    "budgetary_unit_obligated_to_pay_at_least_two_non_heating_or_non_cooling_utility_expenses",
    "budgetary_unit_obligated_to_pay_only_telephone_expense",
    "budgetary_unit_billed_separately_for_utility_expenses",
    "budgetary_unit_obligated_to_pay_allowable_utility_expenses",
    "budgetary_unit_has_verified_allowable_utility_expenses",
    "billed_for_dependent_care",
    "billed_dependent_care_expense_amount",
    "care_recipient_is_dependent_child",
    "necessary_to_seek_accept_or_continue_employment",
    "snap_countable_financial_resources",
)


def _program(inputs) -> dict:
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


def _project(case: Case, slots) -> dict:
    mapping = load_populace_mapping_for_program(_program(slots))
    people = [dict(entity.facts) for entity in case.entities_of_kind("person")]
    case_facts = {**case.facts, "__people__": people}
    return {slot: mapping[slot](case_facts, None) for slot in slots}


def _by_id(case_id: str) -> Case:
    return next(
        case for case in load_suite("us-az-snap-screener") if case.case_id == case_id
    )


def test_suite_is_registered_bounded_unique_and_deterministic() -> None:
    assert "us-az-snap-screener" in available_suites()
    first = load_suite("us-az-snap-screener")
    assert first == load_suite("us-az-snap-screener")
    ids = [case.case_id for case in first]
    assert len(ids) == len(set(ids)) == 1_211 <= 3_000
    assert [case.case_id for case in us_az_snap_screener_fy2027_cases()] == ids


def test_every_case_is_an_arizona_screener_case_on_a_recorded_path() -> None:
    cases = load_suite("us-az-snap-screener")
    assert {path_of(case) for case in cases} == set(PATHS)
    for case in cases:
        assert case.fact(Concepts.STATE_CODE) == "AZ"
        assert case.scope is not None and case.scope.geoid == "04"
        # Always present: it overrides PolicyEngine's childcare formula.
        assert case.fact(Concepts.DEPENDENT_CARE_PAID) is not None


def test_paths_name_rules_and_variables_and_the_doc_lists_every_path() -> None:
    doc = (REPO / "docs" / "az-snap-screener-grid.md").read_text()
    for path, spec in PATHS.items():
        assert spec.axiom_rules and spec.policyengine_variables
        assert f"`{path}`" in doc


def test_income_edges_sit_on_the_guideline_percentages() -> None:
    case = _by_id("azs-income-n1-p130-earned-none")
    head = case.entities[0]
    # Monthly gross is placed to the cent; the annual fact is 12 times it.
    assert head.fact(Concepts.YEARLY_EARNED_INCOME) == round(
        round(guideline_monthly(1) * 1.3, 2) * 12, 2
    )
    fy2027 = next(
        case
        for case in us_az_snap_screener_fy2027_cases()
        if case.case_id == "azs-income-n4-p200-unearned-elderly"
    )
    assert fy2027.entities[0].fact(Concepts.SOCIAL_SECURITY_BENEFITS) == round(
        round((15_960 + 3 * 5_680) / 12 * 2.0, 2) * 12, 2
    )
    assert len(fy2027.entities) == 4


def test_disabled_heads_receive_a_disability_benefit_inside_gross_income() -> None:
    case = _by_id("azs-income-n2-p130-earned-disabled")
    head = case.entities[0]
    gross = round(round(guideline_monthly(2) * 1.3, 2) * 12, 2)
    assert head.fact(Concepts.DISABLED) is True
    assert head.fact(Concepts.SOCIAL_SECURITY_DISABILITY_BENEFITS) == 1_200.0
    assert head.fact(Concepts.SOCIAL_SECURITY_BENEFITS) == 1_200.0
    assert head.fact(Concepts.YEARLY_EARNED_INCOME) == round(gross - 1_200.0, 2)


def test_shelter_rows_place_the_excess_shelter_cost_around_the_cap() -> None:
    row = next(
        row for row in households() if row.case_id == "azs-shelter-none-n3-p100-cap+1"
    )
    net = row.gross - standard_deduction_fy2026(3)
    assert round(row.rent - 0.5 * net, 2) == FY2026["shelter_cap"] + 1


def test_screener_facts_project_into_axiom_slots() -> None:
    sua = _project(_by_id("azs-utility-sua-n2-rent600-none"), SCREENER_SLOTS)
    assert sua[SCREENER_SLOTS[4]] is True
    assert sua[SCREENER_SLOTS[6]] is False
    assert sua[SCREENER_SLOTS[7]] is False
    assert sua[SCREENER_SLOTS[8]] is True
    lua = _project(_by_id("azs-utility-lua-n2-rent600-none"), SCREENER_SLOTS)
    assert (lua[SCREENER_SLOTS[4]], lua[SCREENER_SLOTS[6]]) == (False, True)
    phone = _project(_by_id("azs-utility-telephone-n2-rent0-none"), SCREENER_SLOTS)
    assert (phone[SCREENER_SLOTS[6]], phone[SCREENER_SLOTS[7]]) == (False, True)
    none = _project(_by_id("azs-utility-none-n2-rent600-none"), SCREENER_SLOTS)
    assert not any(none[slot] for slot in SCREENER_SLOTS[4:11])

    homeless = _project(_by_id("azs-homeless-n1-p50-shelter250"), SCREENER_SLOTS)
    assert homeless["snap_claimed_homeless_shelter_deduction"] == 250.0
    support = _project(_by_id("azs-childsupport-n2-p100-paid150"), SCREENER_SLOTS)
    assert support["snap_allowable_monthly_child_support_payments"] == 150.0
    care = _project(_by_id("azs-depcare-n3-child3-p100-care200"), SCREENER_SLOTS)
    assert care["billed_dependent_care_expense_amount"] == 200.0
    assert care["billed_for_dependent_care"] is True
    assets = _project(_by_id("azs-resources-elderly-n1-p190-assets4501"), SCREENER_SLOTS)
    assert assets["snap_countable_financial_resources"] == 4_501


def test_medical_slots_count_only_elderly_or_disabled_members() -> None:
    elderly = _project(_by_id("azs-medical-elderly-n1-p50-m35.01"), SCREENER_SLOTS)
    assert elderly["snap_total_medical_expenses"] == 35.01
    assert elderly["household_entitled_to_excess_medical_deduction"] is True
    control = _project(_by_id("azs-medical-none-n1-p50-m100"), SCREENER_SLOTS)
    assert control["snap_total_medical_expenses"] == 0
    assert control["household_entitled_to_excess_medical_deduction"] is False


def test_population_cases_keep_the_old_defaults() -> None:
    population_case = Case(
        case_id="ecps-1",
        period="2026-01",
        facts={Concepts.RENT_PAID: 12_000.0, Concepts.CHILDCARE_EXPENSES: 2_400.0},
        entities=(
            Entity("person-1", "person", {Concepts.PERSON_AGE: 70}),
            Entity("person-2", "person", {Concepts.PERSON_AGE: 8}),
        ),
    )
    projected = _project(population_case, SCREENER_SLOTS)
    for slot, value in projected.items():
        assert not value, (slot, value)


def test_policyengine_situation_carries_screener_inputs_only_when_present() -> None:
    runner = PolicyEngineRunner()
    screener = _by_id("azs-medical-elderly-n1-p50-m100")
    situation = runner._build_situation_from_case(screener, variables=["snap"])
    head = situation["people"]["head"]
    assert head["other_medical_expenses"] == {2026: 1_200.0}
    assert situation["spm_units"]["spm_unit"]["childcare_expenses"] == {2026: 0.0}
    utility = runner._build_situation_from_case(
        _by_id("azs-utility-sua-n1-rent600-none"), variables=["snap"]
    )
    assert utility["spm_units"]["spm_unit"]["heating_cooling_expense"] == {
        2026: 1_200.0
    }
    homeless = runner._build_situation_from_case(
        _by_id("azs-homeless-n1-p0-shelter100"), variables=["snap"]
    )
    assert homeless["households"]["household"]["is_homeless"] == {2026: True}

    population_case = Case(
        case_id="ecps-1",
        period="2026-01",
        facts={Concepts.STATE_CODE: "AZ"},
        entities=(Entity("person-1", "person", {Concepts.PERSON_AGE: 70}),),
    )
    plain = runner._build_situation_from_case(population_case, variables=["snap"])
    flat = repr(plain)
    for variable in (
        "other_medical_expenses",
        "child_support_expense",
        "social_security_disability",
        "bank_account_assets",
        "heating_cooling_expense",
        "childcare_expenses",
        "is_homeless",
    ):
        assert variable not in flat


def test_policyengine_batch_fills_plain_screener_inputs_and_refuses_formula_mixes() -> None:
    runner = PolicyEngineRunner()
    sua = _by_id("azs-utility-sua-n1-rent0-none")
    plain = _by_id("azs-income-n1-p50-earned-none")
    person_rows, _h, _m, _f, spm_rows, _t, _ids = runner._policyengine_dataset_rows(
        [sua, plain], ["snap"]
    )
    assert [row["heating_cooling_expense"] for row in spm_rows] == [1_200.0, 0.0]
    population_case = Case(
        case_id="ecps-1",
        period="2026-01",
        facts={Concepts.STATE_CODE: "AZ"},
        entities=(Entity("person-1", "person", {Concepts.PERSON_AGE: 40}),),
    )
    with pytest.raises(RuntimeError, match="childcare_expenses"):
        runner._policyengine_dataset_rows([sua, population_case], ["snap"])
