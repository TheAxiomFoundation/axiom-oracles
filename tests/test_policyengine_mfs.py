"""Married-filing-separately projection into the direct PolicyEngine runner.

Expectations are the projected PolicyEngine inputs, which the runner fixes:
the separate filer (tax-unit head) is ``is_separated`` and the tax unit's
``cohabitating_spouses`` is the negation of the lived-apart fact. PolicyEngine
derives the filing status from those inputs, so no builder sets
``filing_status``.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.adapters.policyengine import runner as runner_module
from axiom_oracles.core.case import Case, Concepts, Entity

YEAR = 2026


def _person(entity_id: str, relation: str, age: int, **facts) -> Entity:
    return Entity(
        entity_id=entity_id,
        kind="person",
        facts={
            Concepts.HOUSEHOLD_RELATION: relation,
            Concepts.PERSON_AGE: age,
            **facts,
        },
    )


def _filer(age: int = 40, wages: float = 40_000, **facts) -> Entity:
    return _person(
        "filer",
        "HeadOfHousehold",
        age,
        **{Concepts.YEARLY_EARNED_INCOME: wages, **facts},
    )


def _case(case_id: str, *entities: Entity, **facts) -> Case:
    return Case(
        case_id=case_id,
        period=str(YEAR),
        facts={Concepts.STATE_CODE: "CO", **facts},
        entities=entities,
    )


def _mfs_case(case_id: str, *entities: Entity, lived_apart: bool | None = None):
    facts = {Concepts.MARRIED_FILING_SEPARATELY: True}
    if lived_apart is not None:
        facts[Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR] = lived_apart
    return _case(case_id, *entities, **facts)


def _situation(case: Case) -> dict:
    return PolicyEngineRunner()._build_situation_from_case(
        case, variables=["income_tax"]
    )


def _calculator_input(case: Case) -> dict:
    return PolicyEngineRunner()._build_household_calculator_input_from_case(
        case, variables=["income_tax"]
    )


def _dataset_rows(cases: list[Case]) -> tuple[list[dict], list[dict]]:
    rows = PolicyEngineRunner()._policyengine_dataset_rows(cases, ["income_tax"])
    person_rows, tax_unit_rows = rows[0], rows[5]
    return person_rows, tax_unit_rows


def _all_input_keys(case: Case) -> set[str]:
    """Every PolicyEngine input name any of the three builders emits."""
    situation = _situation(case)
    keys = {
        key
        for group in situation.values()
        for entity_inputs in group.values()
        for key in entity_inputs
    }
    calculator = _calculator_input(case)
    keys.update(key for person in calculator["people"] for key in person)
    for entity_name in ("family", "spm_unit", "tax_unit", "household"):
        keys.update(calculator[entity_name])
    person_rows, tax_unit_rows = _dataset_rows([case])
    keys.update(key for row in [*person_rows, *tax_unit_rows] for key in row)
    return keys


# --- situation builder (requested-month path) ------------------------------


def test_situation_marks_separate_filer_and_cohabiting_tax_unit() -> None:
    situation = _situation(_mfs_case("mfs-wages-40000", _filer()))

    filer = situation["people"]["filer"]
    assert filer["is_separated"] == {YEAR: True}
    assert filer["is_tax_unit_head"] == {YEAR: True}
    assert filer["is_tax_unit_spouse"] == {YEAR: False}
    # LIVED_APART_FROM_SPOUSE_ALL_YEAR defaults to False (spouses shared a
    # home), so the tax unit is cohabiting.
    assert situation["tax_units"]["tax_unit"]["cohabitating_spouses"] == {YEAR: True}


def test_situation_lived_apart_is_not_cohabiting() -> None:
    situation = _situation(
        _mfs_case("mfs-lived-apart", _filer(age=70), lived_apart=True)
    )

    assert situation["people"]["filer"]["is_separated"] == {YEAR: True}
    assert situation["tax_units"]["tax_unit"]["cohabitating_spouses"] == {YEAR: False}


def test_situation_marks_only_the_filer_separated_with_a_child() -> None:
    situation = _situation(
        _mfs_case(
            "mfs-child-wages-15000",
            _filer(age=35, wages=15_000),
            _person("child", "Child", 8),
            lived_apart=True,
        )
    )

    assert situation["people"]["filer"]["is_separated"] == {YEAR: True}
    child = situation["people"]["child"]
    assert "is_separated" not in child
    assert child["is_tax_unit_head"] == {YEAR: False}
    assert child["is_tax_unit_spouse"] == {YEAR: False}
    assert situation["tax_units"]["tax_unit"]["members"] == ["filer", "child"]
    assert situation["tax_units"]["tax_unit"]["cohabitating_spouses"] == {YEAR: False}


# --- household calculator input (single-case path) -------------------------


def test_calculator_input_marks_separate_filer_and_tax_unit() -> None:
    household_input = _calculator_input(
        _mfs_case(
            "mfs-child-wages-45000",
            _filer(age=35, wages=45_000),
            _person("child", "Child", 8),
        )
    )

    filer, child = household_input["people"]
    assert filer["is_separated"] is True
    assert filer["is_tax_unit_head"] is True
    assert filer["is_tax_unit_spouse"] is False
    assert "is_separated" not in child
    assert household_input["tax_unit"]["cohabitating_spouses"] is True


def test_calculator_input_lived_apart_is_not_cohabiting() -> None:
    household_input = _calculator_input(
        _mfs_case("mfs-lived-apart", _filer(), lived_apart=True)
    )

    assert household_input["people"][0]["is_separated"] is True
    assert household_input["tax_unit"]["cohabitating_spouses"] is False


# --- batch dataset rows ----------------------------------------------------


def test_dataset_rows_mark_separate_filer_and_tax_unit() -> None:
    person_rows, tax_unit_rows = _dataset_rows(
        [
            _mfs_case(
                "mfs-child",
                _filer(age=35, wages=15_000),
                _person("child", "Child", 8),
                lived_apart=True,
            )
        ]
    )

    rows_by_id = {row["person_id"]: row for row in person_rows}
    assert rows_by_id["case_0__filer"]["is_separated"] is True
    assert rows_by_id["case_0__filer"]["is_tax_unit_head"] is True
    assert rows_by_id["case_0__filer"]["is_tax_unit_spouse"] is False
    # Dense column: the child carries PolicyEngine's default explicitly.
    assert rows_by_id["case_0__child"]["is_separated"] is False
    assert tax_unit_rows[0]["cohabitating_spouses"] is False


def test_mixed_batch_fills_separate_columns_with_false_on_other_rows() -> None:
    single = _case("single", _filer(wages=40_000))
    joint = _case(
        "joint",
        _filer(wages=40_000),
        _person("spouse", "Spouse", 38, **{Concepts.YEARLY_EARNED_INCOME: 20_000}),
    )
    mfs = _mfs_case("mfs", _filer(wages=150_000))

    person_rows, tax_unit_rows = _dataset_rows([single, joint, mfs])

    separated = {row["person_id"]: row["is_separated"] for row in person_rows}
    assert separated == {
        "case_0__filer": False,
        "case_1__filer": False,
        "case_1__spouse": False,
        "case_2__filer": True,
    }
    cohabiting = {
        row["tax_unit_id"]: row["cohabitating_spouses"] for row in tax_unit_rows
    }
    assert cohabiting == {
        "case_0__tax_unit": False,
        "case_1__tax_unit": False,
        "case_2__tax_unit": True,
    }
    # The batch path builds one DataFrame per entity from these rows; dense
    # keys keep both columns boolean instead of NaN-filled.
    assert pd.DataFrame(person_rows)["is_separated"].dtype == bool
    assert pd.DataFrame(tax_unit_rows)["cohabitating_spouses"].dtype == bool


# --- non-separate cases are unchanged --------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        _case("single", _filer()),
        _case(
            "joint",
            _filer(),
            _person("spouse", "Spouse", 38),
        ),
        _case("single-parent", _filer(age=35), _person("child", "Child", 8)),
        _case(
            "explicit-not-separate",
            _filer(),
            **{Concepts.MARRIED_FILING_SEPARATELY: False},
        ),
    ],
    ids=lambda case: case.case_id,
)
def test_non_separate_cases_emit_no_separate_return_inputs(case: Case) -> None:
    keys = _all_input_keys(case)

    assert "is_separated" not in keys
    assert "cohabitating_spouses" not in keys


def test_batch_without_a_separate_return_emits_no_separate_columns() -> None:
    person_rows, tax_unit_rows = _dataset_rows(
        [
            _case("single", _filer()),
            _case("joint", _filer(), _person("spouse", "Spouse", 38)),
        ]
    )

    assert all("is_separated" not in row for row in person_rows)
    assert all("cohabitating_spouses" not in row for row in tax_unit_rows)


@pytest.mark.parametrize(
    "case",
    [
        _mfs_case("mfs", _filer()),
        _mfs_case("mfs-child", _filer(), _person("child", "Child", 8)),
    ],
    ids=lambda case: case.case_id,
)
def test_no_builder_sets_filing_status(case: Case) -> None:
    assert "filing_status" not in _all_input_keys(case)


# --- refusals ---------------------------------------------------------------

_BUILDERS = {
    "situation": _situation,
    "calculator": _calculator_input,
    "dataset": lambda case: _dataset_rows([case]),
}


@pytest.mark.parametrize("builder", list(_BUILDERS), ids=str)
def test_separate_return_with_spouse_entity_raises(builder: str) -> None:
    case = _mfs_case(
        "mfs-with-spouse",
        _filer(),
        _person("spouse", "Spouse", 38),
    )

    with pytest.raises(RuntimeError, match=r"'mfs-with-spouse'.*spouse entity"):
        _BUILDERS[builder](case)


@pytest.mark.parametrize("builder", list(_BUILDERS), ids=str)
def test_separate_return_with_second_non_dependent_adult_raises(builder: str) -> None:
    # Without a spouse relation, _tax_filers still ranks a second adult into
    # the spouse role (here the older adult becomes head), which PolicyEngine
    # would compute as a joint return.
    case = _mfs_case(
        "mfs-with-other-adult",
        _filer(),
        _person("parent", "Other", 70),
    )

    with pytest.raises(
        RuntimeError,
        match=r"'mfs-with-other-adult'.*two non-dependent adults",
    ):
        _BUILDERS[builder](case)


def test_separate_return_keeps_an_adult_child_out_of_the_spouse_role() -> None:
    case = _mfs_case(
        "mfs-adult-child",
        _filer(age=50),
        _person("adult-child", "Child", 23),
    )

    people = _situation(case)["people"]

    assert people["filer"]["is_separated"] == {YEAR: True}
    assert people["adult-child"]["is_tax_unit_spouse"] == {YEAR: False}
    assert "is_separated" not in people["adult-child"]


@pytest.mark.parametrize("builder", list(_BUILDERS), ids=str)
def test_separate_return_without_a_person_raises(builder: str) -> None:
    with pytest.raises(RuntimeError, match=r"'mfs-empty'.*no person entity"):
        _BUILDERS[builder](_mfs_case("mfs-empty"))


@pytest.mark.parametrize("builder", list(_BUILDERS), ids=str)
def test_invalid_separate_return_facts_raise_runtime_error(builder: str) -> None:
    # The shared resolver rejects residence facts without the separate-return
    # fact; the runner re-raises its ValueError as a RuntimeError.
    case = _case(
        "lived-apart-not-separate",
        _filer(),
        **{Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True},
    )

    with pytest.raises(RuntimeError, match="lived-apart-not-separate") as info:
        _BUILDERS[builder](case)
    assert isinstance(info.value.__cause__, ValueError)


def test_batch_refusal_propagates_without_bisecting(monkeypatch) -> None:
    """_run_case_batch re-raises a RuntimeError instead of splitting the batch.

    A bisected batch would fall back to run_case per case; the refusal must
    surface from the first batch attempt instead.
    """

    def fail_run_case(*_args, **_kwargs):
        raise AssertionError("a projection refusal must not bisect the batch")

    monkeypatch.setattr(PolicyEngineRunner, "run_case", fail_run_case)
    monkeypatch.setattr(
        runner_module, "_policyengine", lambda: SimpleNamespace(us=None)
    )
    # _run_case_batch_once imports microdf before building rows; the dev
    # environment does not install it.
    monkeypatch.setitem(sys.modules, "microdf", SimpleNamespace(MicroDataFrame=object))
    cases = [
        _case("single", _filer()),
        _mfs_case("mfs-with-spouse", _filer(), _person("spouse", "Spouse", 38)),
    ]

    with pytest.raises(RuntimeError, match="'mfs-with-spouse'"):
        PolicyEngineRunner().run_cases(cases, ["income_tax"])
