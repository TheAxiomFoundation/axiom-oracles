"""State Pension Credit Act s.1 qualifying-age projection against PolicyEngine UK.

From PolicyEngine/policyengine-uk#1899, state_pension_age is each person's own
State Pension age from their date of birth, and is_SP_age tests exact age on
6 October: round(12 * floor(age) + months_since_last_birthday
- 12 * state_pension_age, 3) >= 0. The bridge projects claimant_age so that
RuleSpec's ``claimant_age >= qualifying_age`` gives the same answer.

Invariants (property-tested below):

1. Agreement: for every whole age, months since the last birthday in [0, 12]
   and float32 State Pension age, RuleSpec's judgment on the projected inputs
   equals PolicyEngine's is_SP_age.
2. The projection moves the exact age by at most PolicyEngine's rounding band
   (half a thousandth of a month).
3. claimant_age never decreases as months since the last birthday increase.
4. Without months_since_last_birthday (PolicyEngine UK before #1899),
   claimant_age is the age itself, matching that release's age >= threshold.
"""

from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.bridges.efrs_uk import (
    STATE_PENSION_CREDIT_SECTION_1_BASE,
    add_policyengine_uk_person_outputs,
    build_state_pension_credit_qualifying_age_request,
    project_state_pension_credit_qualifying_age_inputs,
)
from axiom_oracles.bridges.tax_populace import decimal_literal

ROUNDING_BAND_YEARS = 0.0005 / 12


def rulespec_has_attained_qualifying_age(inputs):
    """uk:statutes/ukpga/2002/16/1 in rulespec-uk, on the decimals the bridge
    sends the engine."""
    qualifying_age = (
        inputs["pensionable_age"]
        if inputs["claimant_is_woman"]
        else inputs["pensionable_age_for_woman_born_same_day"]
    )
    return Decimal(decimal_literal(float(inputs["claimant_age"]))) >= Decimal(
        decimal_literal(float(qualifying_age))
    )


def policyengine_is_sp_age(age, months_since_last_birthday, state_pension_age):
    """is_SP_age at policyengine-uk#1899, in numpy as PolicyEngine computes it:
    exact_age_in_months, then months_since_state_pension_age rounded with
    np.round and stored as float32."""
    age_in_months = 12 * np.floor(np.float64(np.float32(age))) + np.clip(
        np.float64(np.float32(months_since_last_birthday)), 0, 12 - 1e-4
    )
    months_since = np.round(
        age_in_months - 12 * np.float64(np.float32(state_pension_age)), 3
    )
    return bool(np.float32(months_since) >= 0)


def policyengine_row(age, months_since_last_birthday, state_pension_age, gender):
    row = {
        "age": float(np.float32(age)),
        "state_pension_age": float(np.float32(state_pension_age)),
        "gender": gender,
    }
    if months_since_last_birthday is not None:
        row["months_since_last_birthday"] = float(
            np.float32(months_since_last_birthday)
        )
    return row


# PolicyEngine UK at policyengine-uk#1899 (c46893e2), period 2026, whole age 66.
# Values as PolicyEngine stores them (float32), from Simulation.calculate.
SPLIT_2026_66_YEAR_OLDS = [
    # months since last birthday, state_pension_age, is_SP_age
    (6.0, 66.08333587646484, True),  # born 6 April 1960: 66 and 1 month
    (5.0, 66.16666412353516, True),  # born 6 May 1960: 66 and 2 months
    (2.0, 66.41666412353516, False),  # born 6 August 1960: 66 and 5 months
]


@pytest.mark.parametrize(
    "months, state_pension_age, is_sp_age", SPLIT_2026_66_YEAR_OLDS
)
def test_2026_66_year_olds_split_by_exact_age(months, state_pension_age, is_sp_age):
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(66, months, state_pension_age, "FEMALE")
    )

    assert inputs["claimant_age"] == 66 + months / 12
    assert inputs["pensionable_age"] == state_pension_age
    assert inputs["pensionable_age_for_woman_born_same_day"] == state_pension_age
    assert rulespec_has_attained_qualifying_age(inputs) is is_sp_age
    assert policyengine_is_sp_age(66, months, state_pension_age) is is_sp_age


def test_whole_age_would_put_2026_66_year_olds_under_state_pension_age():
    # The projection before this change: whole age against each person's own
    # State Pension age. PolicyEngine has both people over it.
    for months, state_pension_age, is_sp_age in SPLIT_2026_66_YEAR_OLDS[:2]:
        whole_age_inputs = {
            "claimant_is_woman": True,
            "pensionable_age": state_pension_age,
            "pensionable_age_for_woman_born_same_day": state_pension_age,
            "claimant_age": 66.0,
        }
        assert is_sp_age is True
        assert rulespec_has_attained_qualifying_age(whole_age_inputs) is False


# Attaining State Pension age at the commencement of 6 October. PolicyEngine UK
# at #1899 (c46893e2): 2025 at age 66 and 2028 at age 67, months since last
# birthday 0.001, 0.003 and 0.013 store a State Pension age just above the
# exact age; months_since_state_pension_age rounds to -0.0, so is_SP_age holds.
FLOAT32_TIES = [
    # year, age, months since last birthday, state_pension_age
    (2025, 66, 0.0, 66.0),
    (2025, 66, 0.0010000000474974513, 66.00008392333984),
    (2025, 66, 0.003000000026077032, 66.00025177001953),
    (2025, 66, 0.013000000268220901, 66.00108337402344),
    (2025, 66, 0.009999999776482582, 66.0008316040039),
    (2028, 67, 0.0, 67.0),
    (2028, 67, 0.029999999329447746, 67.00250244140625),
]


@pytest.mark.parametrize("year, age, months, state_pension_age", FLOAT32_TIES)
def test_attaining_state_pension_age_on_6_october_is_a_tie(
    year, age, months, state_pension_age
):
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(age, months, state_pension_age, "MALE")
    )

    assert inputs["claimant_age"] == inputs["pensionable_age"]
    assert rulespec_has_attained_qualifying_age(inputs) is True
    assert policyengine_is_sp_age(age, months, state_pension_age) is True


def test_float32_tie_would_flip_without_the_tie_rule():
    _, age, months, state_pension_age = FLOAT32_TIES[1]
    exact_age = age + float(np.float32(months)) / 12

    assert float(np.float32(state_pension_age)) > exact_age


def test_months_since_last_birthday_is_capped_short_of_the_next_birthday():
    # PolicyEngine caps months since the last birthday at 12 - 1e-4, so a
    # 66-year-old stays 66: under a State Pension age of 67 and 1 month.
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(66, 12.0, 67 + 1 / 12, "MALE")
    )

    assert inputs["claimant_age"] == 66 + (12 - 1e-4) / 12
    assert rulespec_has_attained_qualifying_age(inputs) is False
    assert policyengine_is_sp_age(66, 12.0, 67 + 1 / 12) is False


def test_just_short_of_a_birthday_that_attains_state_pension_age_is_a_tie():
    # 1e-4 of a month short of 67 is inside PolicyEngine's rounding band, so a
    # State Pension age of exactly 67 counts as attained, as in PolicyEngine.
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(66, 12.0, 67.0, "MALE")
    )

    assert inputs["claimant_age"] == 67.0
    assert rulespec_has_attained_qualifying_age(inputs) is True
    assert policyengine_is_sp_age(66, 12.0, 67.0) is True


def test_fractional_age_is_the_exact_age():
    # PolicyEngine reads a fractional age as the exact age on 6 October and
    # sets months_since_last_birthday to its fraction: 66.25 is 66 and 3 months.
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(66.25, 3.0, 66.33333587646484, "MALE")
    )

    assert inputs["claimant_age"] == 66.25
    assert rulespec_has_attained_qualifying_age(inputs) is False


def test_request_queries_6_october():
    request = build_state_pension_credit_qualifying_age_request(
        pe_data={
            "persons": [
                {"person_id": 1, **policyengine_row(66, 6.0, 66.08333587646484, "MALE")}
            ],
            "person_ids": [1],
            "benunits": [],
            "benunit_ids": [],
        },
        year=2026,
    )
    day = {
        "period_kind": "custom",
        "name": "day",
        "start": "2026-10-06",
        "end": "2026-10-06",
    }

    assert [query["period"] for query in request["queries"]] == [day]
    assert {record["interval"]["start"] for record in request["dataset"]["inputs"]} == {
        "2026-10-06"
    }
    claimant_age = {
        record["name"]: record["value"] for record in request["dataset"]["inputs"]
    }[f"{STATE_PENSION_CREDIT_SECTION_1_BASE}#input.claimant_age"]
    assert claimant_age == {"kind": "decimal", "value": "66.5"}


class FakeValues:
    def __init__(self, values):
        self.values = values


class FakeSimulation:
    def __init__(self, defined):
        self.tax_benefit_system = SimpleNamespace(variables=dict.fromkeys(defined))
        self.calls = []

    def calculate(self, variable, *, period, map_to):
        self.calls.append((variable, period, map_to))
        return FakeValues([variable])


def test_person_outputs_skip_months_since_last_birthday_before_1899():
    sim = FakeSimulation(["age", "is_SP_age", "state_pension_age"])

    merged = add_policyengine_uk_person_outputs(
        {},
        sim,
        variables=("age", "months_since_last_birthday", "state_pension_age"),
        year=2026,
    )

    assert set(merged) == {"age", "state_pension_age"}
    assert [call[0] for call in sim.calls] == ["age", "state_pension_age"]


def test_person_outputs_include_months_since_last_birthday_from_1899():
    sim = FakeSimulation(["age", "months_since_last_birthday"])

    merged = add_policyengine_uk_person_outputs(
        {}, sim, variables=("age", "months_since_last_birthday"), year=2026
    )

    assert merged == {
        "age": ["age"],
        "months_since_last_birthday": ["months_since_last_birthday"],
    }


def test_person_outputs_still_fail_loudly_on_required_variables():
    sim = FakeSimulation(["age"])
    sim.calculate = lambda variable, **_: (_ for _ in ()).throw(KeyError(variable))

    with pytest.raises(KeyError, match="is_SP_age"):
        add_policyengine_uk_person_outputs({}, sim, variables=("is_SP_age",), year=2026)


def test_without_months_since_last_birthday_claimant_age_is_the_age():
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(66, None, 66.0, "MALE")
    )

    assert inputs["claimant_age"] == 66.0
    assert rulespec_has_attained_qualifying_age(inputs) is True


float32_months = st.floats(0, 12, allow_nan=False).map(
    lambda value: float(np.float32(value))
)
whole_ages = st.integers(16, 100)


@st.composite
def policyengine_people(draw):
    """A whole age, months since the last birthday and a float32 State Pension
    age, often within a few thousandths of a month of the exact age so the
    rounding band is exercised."""
    age = draw(whole_ages)
    months = draw(float32_months)
    near_tie = draw(st.booleans())
    if near_tie:
        offset = draw(st.floats(-0.003, 0.003, allow_nan=False))
        state_pension_age = (12 * age + min(months, 12 - 1e-4) + offset) / 12
    else:
        state_pension_age = draw(st.floats(60, 68, allow_nan=False))
    return age, months, float(np.float32(state_pension_age))


@settings(max_examples=2000, deadline=None)
@given(policyengine_people(), st.sampled_from(["MALE", "FEMALE"]))
def test_rulespec_judgment_matches_policyengine_is_sp_age(person, gender):
    age, months, state_pension_age = person
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(age, months, state_pension_age, gender)
    )

    assert rulespec_has_attained_qualifying_age(inputs) is policyengine_is_sp_age(
        age, months, state_pension_age
    )


@settings(max_examples=1000, deadline=None)
@given(policyengine_people())
def test_projection_moves_exact_age_only_within_the_rounding_band(person):
    age, months, state_pension_age = person
    exact_age = age + min(months, 12 - 1e-4) / 12
    claimant_age = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(age, months, state_pension_age, "MALE")
    )["claimant_age"]

    assert abs(claimant_age - exact_age) <= ROUNDING_BAND_YEARS + 1e-12


@settings(max_examples=1000, deadline=None)
@given(policyengine_people(), float32_months)
def test_claimant_age_never_decreases_with_months_since_birthday(person, other):
    age, months, state_pension_age = person
    low, high = sorted([months, other])

    def claimant_age(months):
        return project_state_pension_credit_qualifying_age_inputs(
            policyengine_row(age, months, state_pension_age, "MALE")
        )["claimant_age"]

    assert claimant_age(low) <= claimant_age(high)


@settings(max_examples=500, deadline=None)
@given(
    st.floats(0, 110, allow_nan=False).map(lambda value: float(np.float32(value))),
    st.floats(60, 68, allow_nan=False).map(lambda value: float(np.float32(value))),
)
def test_before_1899_judgment_is_age_at_least_state_pension_age(age, state_pension_age):
    inputs = project_state_pension_credit_qualifying_age_inputs(
        policyengine_row(age, None, state_pension_age, "FEMALE")
    )

    assert inputs["claimant_age"] == age
    assert rulespec_has_attained_qualifying_age(inputs) is (age >= state_pension_age)


def policyengine_uk_with_exact_age():
    policyengine_uk = pytest.importorskip("policyengine_uk")
    system = policyengine_uk.CountryTaxBenefitSystem()
    if "months_since_last_birthday" not in system.variables:
        pytest.skip("policyengine-uk predates #1899 (no months_since_last_birthday)")
    return policyengine_uk


@pytest.mark.parametrize("year", [2025, 2026, 2027, 2028])
def test_differential_against_policyengine_uk(year):
    """RuleSpec on the projected inputs agrees with PolicyEngine UK's own
    is_SP_age for 60- to 70-year-olds across the year of age, both sexes, at
    exact birthdays, within a day of 6 October and just short of the next
    birthday. Runs only where the installed policyengine-uk has #1899."""
    policyengine_uk = policyengine_uk_with_exact_age()
    months_grid = [
        0.0,
        0.001,
        0.003,
        0.013,
        0.03,
        1.5,
        2.0,
        5.0,
        6.0,
        9.25,
        11.99,
        12.0,
    ]
    people, benunits, genders = {}, {}, []
    for age in range(60, 71):
        for months in months_grid:
            for gender in ("MALE", "FEMALE"):
                name = f"p{len(people)}"
                people[name] = {
                    "age": {year: age},
                    "months_since_last_birthday": {year: months},
                    "gender": {year: gender},
                }
                benunits[f"b{len(benunits)}"] = {"members": [name]}
                genders.append(gender)
    sim = policyengine_uk.Simulation(
        situation={
            "people": people,
            "benunits": benunits,
            "households": {"h": {"members": list(people)}},
        }
    )
    columns = {
        variable: sim.calculate(variable, year)
        for variable in (
            "age",
            "months_since_last_birthday",
            "state_pension_age",
            "is_SP_age",
        )
    }

    disagreements = []
    for index in range(len(people)):
        row = {
            "age": float(columns["age"][index]),
            "months_since_last_birthday": float(
                columns["months_since_last_birthday"][index]
            ),
            "state_pension_age": float(columns["state_pension_age"][index]),
            "gender": genders[index],
        }
        inputs = project_state_pension_credit_qualifying_age_inputs(row)
        if rulespec_has_attained_qualifying_age(inputs) is not bool(
            columns["is_SP_age"][index]
        ):
            disagreements.append(row)

    assert disagreements == []
