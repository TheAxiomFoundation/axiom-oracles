"""The Populace constructor's tax-unit roles reach every projection surface (axiom-oracles#633).

Ground truth is the constructor's own roles: the pinned Populace US artifact
carries each person's role in the person column ``tax_unit_role_input``
(``HEAD`` / ``SPOUSE`` / ``DEPENDENT``). Every expected filer, dependent and
relation below is read off those roles. No engine output is used.

Two statutory consequences are tested on top of them.

26 USC 6013(a), U.S. Code 2024 edition (govinfo USCODE-2024-title26, section
6013), verbatim:

    (a) Joint returns
    A husband and wife may make a single return jointly of income taxes under
    subtitle A, even though one of the spouses has neither gross income nor
    deductions, except as provided below:

So only a unit whose roles name a SPOUSE can file jointly.

26 USC 32(c)(1)(A)(ii)(II), U.S. Code 2024 edition (govinfo, section 32),
verbatim:

    (II) such individual (or, if the individual is married, either the
    individual or the individual's spouse) has attained age 25 but not
    attained age 65 before the close of the taxable year,

So the childless EITC age test reads the constructor's HEAD and SPOUSE only.

The simulations here are fakes that follow PolicyEngine-US 1.764.6's role
formulas, which rank by age and never read ``tax_unit_role_input``:

- ``is_tax_unit_head``: ``person.get_rank(tax_unit, -age, ~is_child) == 0``;
- ``is_tax_unit_spouse``: the next-oldest ``~is_child`` member, unless the
  unit is separated.

``tests/test_source_tax_unit_roles_live.py`` repeats the end-to-end checks on
a real PolicyEngine-US.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    _filing_status,
    _tax_dependents,
    _tax_filers,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.bridges import tax_populace
from axiom_oracles.bridges.tax_populace import (
    project_eitc_tax_unit_inputs,
    project_tax_unit_person_contexts,
    tax_unit_filers,
)
from axiom_oracles.bridges.tax_unit_roles import (
    ROLES_ABSENT,
    ROLES_INPUTS,
    ROLES_NATIVE,
    SourceTaxUnitRoleError,
    apply_source_tax_unit_roles,
    normalize_role,
    populace_us_microsimulation,
    role_years,
    source_tax_unit_roles,
)
from axiom_oracles.core.case import Case, Concepts
from axiom_oracles.populations.populace_us import (
    PopulaceUsCaseLoader,
    _person_entity,
    _PersonRow,
)

DATA_YEAR = 2024
YEAR = 2026
AGE_INPUT = "childless_taxpayer_or_spouse_age_eligible_for_eitc"
CASE_AGE_INPUT = f"us:statutes/26/32#input.{AGE_INPUT}"
PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)

# Populace units from axiom-oracles#633, as (age, constructor role) per member.
# PolicyEngine-US 1.764.6 files 138, 1058, 1452 and 3824 jointly: its age
# ranking makes the adult DEPENDENT a filer.
UNIT_138 = [(85, "HEAD"), (60, "DEPENDENT")]
UNIT_1058 = [(74, "HEAD"), (47, "DEPENDENT")]
UNIT_1452 = [(80, "HEAD"), (64, "DEPENDENT")]
UNIT_3824 = [(65, "DEPENDENT"), (36, "HEAD")]
UNIT_57137 = [(85, "DEPENDENT"), (65, "HEAD"), (64, "SPOUSE")]
ISSUE_UNITS = {
    138: UNIT_138,
    1058: UNIT_1058,
    1452: UNIT_1452,
    3824: UNIT_3824,
    57137: UNIT_57137,
}


# ---------------------------------------------------------------------------
# A simulation that ranks roles by age, as PolicyEngine-US 1.764.6 does.
# ---------------------------------------------------------------------------


class AgeRankedSimulation:
    """PolicyEngine-US 1.764.6's role formulas over a small person table.

    ``native=True`` adds #9617's ``tax_unit_role_input``: roles supplied for
    every member of a unit decide its flags. ``subsample`` drops every input,
    as the real one rebuilds the simulation from its dataset.
    """

    def __init__(self, person_table, *, native=False, ignore_roles=False):
        self.person_ids = [int(v) for v in person_table["person_id"]]
        self.tax_unit_ids = [int(v) for v in person_table["person_tax_unit_id"]]
        self.ages = [float(v) for v in person_table["age"]]
        self.separated = [
            bool(v) for v in person_table.get("is_separated", [False] * len(self.ages))
        ]
        self.roles = (
            [normalize_role(v) for v in person_table["tax_unit_role_input"]]
            if "tax_unit_role_input" in person_table
            else [""] * len(self.ages)
        )
        self.native = native
        self.ignore_roles = ignore_roles
        variables = {"tax_unit_role_input": object()} if native else {}
        self.tax_benefit_system = SimpleNamespace(variables=variables)
        self.inputs: dict[tuple[str, int], np.ndarray] = {}
        self.set_input_calls: list[tuple[str, int]] = []

    def set_input(self, variable, period, values):
        self.set_input_calls.append((variable, int(period)))
        self.inputs[(variable, int(period))] = np.asarray(values, dtype=bool)

    def subsample(self, _size):
        self.inputs.clear()

    def calculate(self, variable, period, map_to=None):
        del map_to
        key = (variable, int(period))
        if key in self.inputs:
            return self.inputs[key]
        if variable == "person_id":
            return np.asarray(self.person_ids)
        if variable == "is_tax_unit_head":
            return self._flags(int(period))[0]
        if variable == "is_tax_unit_spouse":
            return self._flags(int(period))[1]
        raise KeyError(variable)

    def _flags(self, period):
        head = np.zeros(len(self.ages), dtype=bool)
        spouse = np.zeros(len(self.ages), dtype=bool)
        for unit in sorted(set(self.tax_unit_ids)):
            members = [i for i, t in enumerate(self.tax_unit_ids) if t == unit]
            roles = [self.roles[i] for i in members]
            if self.native and not self.ignore_roles and all(roles):
                for i, role in zip(members, roles):
                    head[i] = role == "HEAD"
                    spouse[i] = role == "SPOUSE"
                continue
            explicit_head = self.inputs.get(("is_tax_unit_head", period))
            adults = [i for i in members if self.ages[i] >= 18]
            # get_rank over -age: the oldest first, ties by position.
            ranked = sorted(adults, key=lambda i: (-self.ages[i], i))
            if explicit_head is not None:
                head_members = [i for i in members if explicit_head[i]]
            else:
                head_members = ranked[:1]
            for i in head_members:
                head[i] = True
            if any(self.separated[i] for i in members):
                continue
            rest = [i for i in ranked if i not in head_members]
            for i in rest[:1]:
                spouse[i] = True
        return head, spouse


def person_table(units, *, roles=True):
    """A Populace-shaped person table: one row per (age, role) member."""
    rows = []
    person_id = 0
    for tax_unit_id, members in units.items():
        for age, role in members:
            person_id += 1
            row = {"person_id": person_id, "person_tax_unit_id": tax_unit_id, "age": age}
            if roles:
                row["tax_unit_role_input"] = role
            rows.append(row)
    return pd.DataFrame(rows)


def role_flags(sim, year):
    return (
        np.asarray(sim.calculate("is_tax_unit_head", year)).astype(bool),
        np.asarray(sim.calculate("is_tax_unit_spouse", year)).astype(bool),
    )


def expected_flags(table):
    roles = [normalize_role(v) for v in table["tax_unit_role_input"]]
    return (
        np.array([r == "HEAD" for r in roles]),
        np.array([r == "SPOUSE" for r in roles]),
    )


# ---------------------------------------------------------------------------
# Reading the constructor's roles.
# ---------------------------------------------------------------------------


def test_no_role_column_means_no_supplied_roles():
    assert source_tax_unit_roles(person_table({1: UNIT_138}, roles=False)) is None
    assert source_tax_unit_roles(None) is None


def test_supplied_roles_are_read_per_person():
    assert source_tax_unit_roles(person_table({138: UNIT_138, 57137: UNIT_57137})) == {
        1: "HEAD",
        2: "DEPENDENT",
        3: "DEPENDENT",
        4: "HEAD",
        5: "SPOUSE",
    }


@pytest.mark.parametrize(
    "value,expected",
    [
        (b"HEAD", "HEAD"),
        ("spouse", "SPOUSE"),
        (" Dependent ", "DEPENDENT"),
        (SimpleNamespace(name="HEAD"), "HEAD"),
        ("TaxUnitRole.SPOUSE", "SPOUSE"),
        ("UNSPECIFIED", ""),
        ("", ""),
        (None, ""),
        (float("nan"), ""),
    ],
)
def test_role_values_normalize_as_the_artifact_and_enum_spell_them(value, expected):
    assert normalize_role(value) == expected


def test_a_unit_with_no_roles_is_left_to_policyengine():
    table = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "person_tax_unit_id": [10, 10, 20, 20],
            "tax_unit_role_input": ["HEAD", "DEPENDENT", "UNSPECIFIED", ""],
        }
    )
    assert source_tax_unit_roles(table) == {1: "HEAD", 2: "DEPENDENT"}


@pytest.mark.parametrize(
    "roles,message",
    [
        (["HEAD", ""], "1 of its 2 members"),
        (["HEAD", "HEAD"], "2 HEAD"),
        (["DEPENDENT", "DEPENDENT"], "0 HEAD"),
        (["HEAD", "SPOUSE", "SPOUSE"], "2 SPOUSE"),
        (["HEAD", "COUSIN"], "unknown tax_unit_role_input"),
    ],
    ids=["partly supplied", "two heads", "no head", "two spouses", "unknown role"],
)
def test_malformed_roles_raise_rather_than_fall_back(roles, message):
    """PolicyEngine-US's tax_unit_roles_supplied (#9617) raises on the same
    shapes."""
    table = pd.DataFrame(
        {
            "person_id": list(range(1, len(roles) + 1)),
            "person_tax_unit_id": [7] * len(roles),
            "tax_unit_role_input": roles,
        }
    )
    with pytest.raises(SourceTaxUnitRoleError, match=message):
        source_tax_unit_roles(table)


def test_role_years_cover_the_data_year_through_the_comparison_year():
    assert role_years(data_year=2024, year=2026) == (2023, 2024, 2025, 2026, 2027)
    assert role_years(data_year=2024, year=2024) == (2023, 2024, 2025)


# ---------------------------------------------------------------------------
# Applying them to a simulation.
# ---------------------------------------------------------------------------


def test_age_ranking_reproduces_the_issue_without_the_fix():
    """Sanity check on the fake: before the fix, 138's 60-year-old DEPENDENT
    is the spouse."""
    table = person_table({138: UNIT_138})
    head, spouse = role_flags(AgeRankedSimulation(table), YEAR)
    assert head.tolist() == [True, False]
    assert spouse.tolist() == [False, True]


def test_older_policyengine_gets_the_roles_as_inputs_for_every_role_year():
    table = person_table(ISSUE_UNITS)
    sim = AgeRankedSimulation(table)
    assert apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR) == (
        ROLES_INPUTS
    )
    expected = expected_flags(table)
    for year in role_years(data_year=DATA_YEAR, year=YEAR):
        head, spouse = role_flags(sim, year)
        assert head.tolist() == expected[0].tolist()
        assert spouse.tolist() == expected[1].tolist()
    assert {call for call in sim.set_input_calls} == {
        (flag, year)
        for flag in ("is_tax_unit_head", "is_tax_unit_spouse")
        for year in role_years(data_year=DATA_YEAR, year=YEAR)
    }


def test_policyengine_with_9617_reads_the_roles_itself_and_is_only_verified():
    table = person_table(ISSUE_UNITS)
    sim = AgeRankedSimulation(table, native=True)
    assert apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR) == (
        ROLES_NATIVE
    )
    assert sim.set_input_calls == []
    head, spouse = role_flags(sim, YEAR)
    assert (head.tolist(), spouse.tolist()) == tuple(
        flags.tolist() for flags in expected_flags(table)
    )


def test_a_simulation_that_does_not_follow_the_roles_raises():
    """A PolicyEngine-US whose role input is ignored must stop the run, not
    project an age-ranked unit."""
    table = person_table({138: UNIT_138})
    sim = AgeRankedSimulation(table, native=True, ignore_roles=True)
    with pytest.raises(SourceTaxUnitRoleError, match="is_tax_unit_spouse differs"):
        apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR)


def test_units_without_roles_keep_policyengines_own_flags():
    table = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "person_tax_unit_id": [138, 138, 9, 9],
            "age": [85, 60, 70, 50],
            "tax_unit_role_input": ["HEAD", "DEPENDENT", "", ""],
        }
    )
    sim = AgeRankedSimulation(table)
    assert apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR) == (
        ROLES_INPUTS
    )
    head, spouse = role_flags(sim, YEAR)
    # Unit 138 follows its roles; unit 9 keeps the age ranking (70 head, 50 spouse).
    assert head.tolist() == [True, False, True, False]
    assert spouse.tolist() == [False, False, False, True]


def test_no_supplied_roles_leaves_the_simulation_untouched():
    table = person_table({1: UNIT_138}, roles=False)
    sim = AgeRankedSimulation(table)
    assert apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR) == (
        ROLES_ABSENT
    )
    assert sim.set_input_calls == []


def test_roles_are_matched_by_person_id_not_row_order():
    table = person_table(ISSUE_UNITS)
    shuffled = table.iloc[::-1].reset_index(drop=True)
    sim = AgeRankedSimulation(table)
    apply_source_tax_unit_roles(sim, shuffled, data_year=DATA_YEAR, year=YEAR)
    head, spouse = role_flags(sim, YEAR)
    assert (head.tolist(), spouse.tolist()) == tuple(
        flags.tolist() for flags in expected_flags(table)
    )


def test_populace_us_microsimulation_applies_the_roles(monkeypatch):
    table = person_table({138: UNIT_138})
    built = []

    def microsimulation(*, dataset):
        built.append(AgeRankedSimulation(dataset.person))
        return built[-1]

    monkeypatch.setitem(
        sys.modules, "policyengine_us", SimpleNamespace(Microsimulation=microsimulation)
    )
    dataset = SimpleNamespace(person=table, time_period="2024")
    sim = populace_us_microsimulation(dataset, data_year=DATA_YEAR, year=YEAR)
    assert sim is built[0]
    head, spouse = role_flags(sim, YEAR)
    assert head.tolist() == [True, False]
    assert spouse.tolist() == [False, False]


# ---------------------------------------------------------------------------
# The bridge: filers, filing status and person contexts move together.
# ---------------------------------------------------------------------------


def _bridge_rows(units, sim, year=YEAR):
    """Person rows as load_policyengine_tax_data builds them: the raw table
    plus PolicyEngine's role flags."""
    table = person_table(units)
    head, spouse = role_flags(sim, year)
    rows = []
    for index, raw in enumerate(table.to_dict("records")):
        rows.append(
            {
                **raw,
                "ssn_card_type": "CITIZEN",
                "is_tax_unit_head": bool(head[index]),
                "is_tax_unit_spouse": bool(spouse[index]),
                "is_tax_unit_head_or_spouse": bool(head[index] or spouse[index]),
            }
        )
    by_unit = {}
    for row in rows:
        by_unit.setdefault(row["person_tax_unit_id"], []).append(row)
    return by_unit


def _applied_sim(units):
    table = person_table(units)
    sim = AgeRankedSimulation(table)
    apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR)
    return sim


@pytest.mark.parametrize(
    "tax_unit_id,filer_ages,age_test",
    [
        pytest.param(138, [85], False, id="138-head-85-dependent-60"),
        pytest.param(1058, [74], False, id="1058-head-74-dependent-47"),
        pytest.param(1452, [80], False, id="1452-head-80-dependent-64"),
        pytest.param(3824, [36], True, id="3824-head-36-dependent-65"),
        pytest.param(57137, [65, 64], True, id="57137-head-65-spouse-64"),
    ],
)
def test_bridge_filers_and_age_test_follow_the_constructor(
    tax_unit_id, filer_ages, age_test
):
    """The filers are the constructor's HEAD then SPOUSE; clause (II) reads
    only them."""
    units = {tax_unit_id: ISSUE_UNITS[tax_unit_id]}
    persons = _bridge_rows(units, _applied_sim(units))[tax_unit_id]
    assert [p["age"] for p in tax_unit_filers(persons)] == filer_ages
    contexts = project_tax_unit_person_contexts(persons)
    assert [c.is_tax_unit_dependent for c in contexts] == [
        role == "DEPENDENT" for _, role in ISSUE_UNITS[tax_unit_id]
    ]
    row = {"filing_status": "SINGLE", "adjusted_gross_income": 10_000}
    assert project_eitc_tax_unit_inputs(row=row, persons=persons)[AGE_INPUT] is (
        age_test
    )


def test_the_bridge_loader_applies_the_roles_before_policyengine_calculates(
    monkeypatch,
):
    """load_policyengine_tax_data sets the roles before its first calculate,
    so PolicyEngine's filing status is computed for the constructor's unit.

    The fake's filing status is joint exactly when a spouse flag is set, as
    PolicyEngine-US's ``tax_unit_married`` is; 26 USC 6013(a) allows a joint
    return only to "a husband and wife", and unit 138's roles name no SPOUSE.
    """
    units = {138: UNIT_138}
    table = person_table(units)
    sims = []
    calls_before_roles = []

    class Sim(AgeRankedSimulation):
        def calculate(self, variable, period, map_to=None):
            if not self.set_input_calls and variable not in {"person_id"}:
                calls_before_roles.append(variable)
            if variable == "filing_status":
                head, spouse = role_flags(self, period)
                return np.asarray(["JOINT" if spouse.any() else "SINGLE"])
            if variable == "is_tax_unit_head_or_spouse":
                head, spouse = role_flags(self, period)
                return head | spouse
            return super().calculate(variable, period, map_to)

    def microsimulation(*, dataset):
        sims.append(Sim(table))
        return sims[-1]

    tables = {
        "tax_unit": pd.DataFrame([{"tax_unit_id": 138, "tax_unit_weight": 1.0}]),
        "person": table,
        "household": pd.DataFrame([{}]),
    }
    monkeypatch.setitem(
        sys.modules, "policyengine_us", SimpleNamespace(Microsimulation=microsimulation)
    )
    monkeypatch.setattr(
        tax_populace,
        "load_populace_dataset",
        lambda *_a, **_k: SimpleNamespace(person=table, time_period="2024"),
    )
    monkeypatch.setattr(tax_populace, "population_table", lambda _d, kind: tables[kind])
    pe_data = tax_populace.load_policyengine_tax_data(
        year=YEAR,
        sample_size=0,
        positive_ctc_only=False,
        data_folder=None,
        populace_year=DATA_YEAR,
        tax_unit_variables=("filing_status",),
        person_variables=(
            "is_tax_unit_head",
            "is_tax_unit_spouse",
            "is_tax_unit_head_or_spouse",
        ),
    )
    assert calls_before_roles == []
    assert pe_data["tax_unit_roles"] == ROLES_INPUTS
    assert pe_data["tax_units"]["filing_status"].tolist() == ["SINGLE"]
    persons = pe_data["persons"].to_dict("records")
    assert [p["is_tax_unit_head"] for p in persons] == [True, False]
    assert [p["is_tax_unit_spouse"] for p in persons] == [False, False]
    assert [p["age"] for p in tax_unit_filers(persons)] == [85]


# ---------------------------------------------------------------------------
# The Case loader: relations follow the same roles.
# ---------------------------------------------------------------------------


class CaseLoaderSimulation(AgeRankedSimulation):
    """The variables PopulaceUsCaseLoader reads, over one household."""

    def calculate(self, variable, period, map_to=None):
        if variable in {"is_tax_unit_head", "is_tax_unit_spouse", "person_id"}:
            return super().calculate(variable, period)
        if variable == "is_tax_unit_dependent":
            head, spouse = role_flags(self, period)
            return ~head & ~spouse
        n = len(self.ages)
        if map_to == "person" or variable in {"age", "tax_unit_id"}:
            values = {
                "household_id": [1] * n,
                "tax_unit_id": self.tax_unit_ids,
                "age": self.ages,
                "tax_exempt_interest_income": [0.0] * n,
            }
        else:
            values = {"household_id": [1], "household_weight": [1.0], "state_fips": [6]}
        if variable not in values:
            raise KeyError(variable)
        return np.asarray(values[variable])


def _case_loader_cases(units, *, sample_size=None):
    table = person_table(units)
    loader = PopulaceUsCaseLoader(dataset="populace://test/populace.h5")
    sims = []

    def build(_dataset):
        sims.append(CaseLoaderSimulation(table))
        return sims[-1], SimpleNamespace(person=table, time_period="2024")

    loader._build_microsimulation_and_dataset = build
    cases = loader.load_cases(
        period=str(YEAR), case_unit="tax_unit", sample_size=sample_size
    )
    return {int(case.metadata["tax_unit_id"]): case for case in cases}


@pytest.mark.parametrize("sample_size", [None, 5])
def test_case_loader_relations_follow_the_constructor(sample_size):
    """Applied after subsample, which rebuilds the simulation."""
    cases = _case_loader_cases(ISSUE_UNITS, sample_size=sample_size)
    relations = {
        tid: [str(e.fact(Concepts.HOUSEHOLD_RELATION, "")) for e in c.entities]
        for tid, c in cases.items()
    }
    assert relations == {
        138: ["HeadOfHousehold", "Dependent"],
        1058: ["HeadOfHousehold", "Dependent"],
        1452: ["HeadOfHousehold", "Dependent"],
        3824: ["Dependent", "HeadOfHousehold"],
        57137: ["Dependent", "HeadOfHousehold", "Spouse"],
    }


def test_case_surface_filing_status_is_joint_only_for_57137():
    """26 USC 6013(a): only 57137's roles name a spouse."""
    cases = _case_loader_cases(ISSUE_UNITS)
    statuses = {}
    for tid, case in cases.items():
        people = list(case.entities)
        head, spouse = _tax_filers(people)
        statuses[tid] = _filing_status(
            spouse=spouse, dependents=_tax_dependents(people, head, spouse)
        )
    assert {tid for tid, status in statuses.items() if status == 1} == {57137}


# ---------------------------------------------------------------------------
# Properties.
# ---------------------------------------------------------------------------

ages = st.integers(min_value=0, max_value=110)


@st.composite
def constructor_units(draw):
    """Valid constructor units in any member order: exactly one HEAD, at most
    one SPOUSE, the rest DEPENDENT, ages 0 to 110."""
    count = draw(st.integers(min_value=1, max_value=5))
    units = {}
    for tax_unit_id in range(1, count + 1):
        size = draw(st.integers(min_value=1, max_value=5))
        roles = ["HEAD"]
        if size > 1 and draw(st.booleans()):
            roles.append("SPOUSE")
        roles += ["DEPENDENT"] * (size - len(roles))
        order = draw(st.permutations(roles))
        units[tax_unit_id] = [(draw(ages), role) for role in order]
    return units


def _filers_by_role(units):
    return {
        tid: [age for age, role in members if role == "HEAD"]
        + [age for age, role in members if role == "SPOUSE"]
        for tid, members in units.items()
    }


@PROPERTY_SETTINGS
@given(units=constructor_units())
def test_property_flags_equal_the_constructors_roles(units):
    table = person_table(units)
    sim = AgeRankedSimulation(table)
    apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR)
    for year in role_years(data_year=DATA_YEAR, year=YEAR):
        head, spouse = role_flags(sim, year)
        expected = expected_flags(table)
        assert head.tolist() == expected[0].tolist()
        assert spouse.tolist() == expected[1].tolist()


@PROPERTY_SETTINGS
@given(units=constructor_units())
def test_property_a_source_dependent_is_never_a_bridge_filer(units):
    """The bridge's filers are exactly the constructor's HEAD, then SPOUSE."""
    by_unit = _bridge_rows(units, _applied_sim(units))
    for tid, persons in by_unit.items():
        filers = tax_unit_filers(persons)
        assert all(p["tax_unit_role_input"] != "DEPENDENT" for p in filers)
        assert [p["age"] for p in filers] == _filers_by_role(units)[tid]
        contexts = project_tax_unit_person_contexts(persons)
        assert [c.is_tax_unit_dependent for c in contexts] == [
            p["tax_unit_role_input"] == "DEPENDENT" for p in persons
        ]


def _case_rows(units, sim):
    head, spouse = role_flags(sim, YEAR)
    table = person_table(units)
    by_unit = {}
    for index, raw in enumerate(table.to_dict("records")):
        by_unit.setdefault(raw["person_tax_unit_id"], []).append(
            _PersonRow(
                person_id=raw["person_id"],
                tax_unit_id=raw["person_tax_unit_id"],
                is_tax_unit_head=bool(head[index]),
                is_tax_unit_spouse=bool(spouse[index]),
                is_tax_unit_dependent=not (head[index] or spouse[index]),
                age=int(raw["age"]),
                yearly_earned_income=8_000.0 if head[index] else 0.0,
                pregnant=False,
                disabled=False,
                blind=False,
                veteran=False,
                benefits_medicaid=False,
                non_wage_income={},
            )
        )
    return by_unit


@PROPERTY_SETTINGS
@given(units=constructor_units())
def test_property_case_surface_files_jointly_only_with_a_source_spouse(units):
    """26 USC 6013(a): joint only for "a husband and wife"."""
    for tid, rows in _case_rows(units, _applied_sim(units)).items():
        people = [_person_entity(row, i, case_unit="tax_unit") for i, row in enumerate(rows)]
        head, spouse = _tax_filers(people)
        status = _filing_status(
            spouse=spouse, dependents=_tax_dependents(people, head, spouse)
        )
        has_spouse = any(role == "SPOUSE" for _, role in units[tid])
        assert (status == 1) is has_spouse


@PROPERTY_SETTINGS
@given(units=constructor_units())
def test_property_bridge_and_case_loader_agree(units):
    """Same filers and the same clause (II) input on both surfaces."""
    sim = _applied_sim(units)
    bridge = _bridge_rows(units, sim)
    cases = _case_rows(units, sim)
    for tid, persons in bridge.items():
        people = [
            _person_entity(row, i, case_unit="tax_unit")
            for i, row in enumerate(cases[tid])
        ]
        head, spouse = _tax_filers(people)
        case_filer_ages = [
            int(p.fact(Concepts.PERSON_AGE, 0)) for p in (head, spouse) if p is not None
        ]
        assert case_filer_ages == [int(p["age"]) for p in tax_unit_filers(persons)]
        projected = attach_axiom_tax_inputs_to_case(
            Case(case_id=f"unit-{tid}", period=str(YEAR), entities=tuple(people))
        )
        case_age = {
            (r["entity_id"], r["name"]): r["value"]
            for r in projected.metadata["axiom_input_records"]
        }[("tax_unit", CASE_AGE_INPUT)]
        row = {"filing_status": "SINGLE", "adjusted_gross_income": 10_000}
        assert case_age is project_eitc_tax_unit_inputs(row=row, persons=persons)[
            AGE_INPUT
        ]


@PROPERTY_SETTINGS
@given(units=constructor_units(), data=st.data())
def test_property_applying_is_idempotent_and_order_free(units, data):
    table = person_table(units)
    permuted = table.iloc[data.draw(st.permutations(range(len(table))))]
    sim = AgeRankedSimulation(table)
    apply_source_tax_unit_roles(sim, permuted, data_year=DATA_YEAR, year=YEAR)
    first = role_flags(sim, YEAR)
    apply_source_tax_unit_roles(sim, table, data_year=DATA_YEAR, year=YEAR)
    second = role_flags(sim, YEAR)
    assert [f.tolist() for f in first] == [f.tolist() for f in second]
