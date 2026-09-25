"""Source tax-unit roles: the build's HEAD/SPOUSE/DEPENDENT and filing status.

Expected values in these tests are the source columns themselves -- the
Populace build's own record of who heads each tax unit -- never PolicyEngine's
age-based rule, which is the behavior being replaced.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles.bridges import source_roles
from axiom_oracles.bridges.source_roles import (
    FILING_STATUSES,
    ROLE_VARIABLES,
    SourceRoleError,
    attach_source_roles,
    pin_source_roles,
    read_source_roles,
)

NON_JOINT = sorted(FILING_STATUSES - {"JOINT"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dataset(units: list[dict]) -> SimpleNamespace:
    """Build a dataset from ``[{"id", "status", "members": [(pid, role, age)]}]``."""
    person_rows = [
        {
            "person_id": pid,
            "person_tax_unit_id": unit["id"],
            "age": age,
            "tax_unit_role_input": role,
        }
        for unit in units
        for pid, role, age in unit["members"]
    ]
    unit_rows = [
        {"tax_unit_id": unit["id"], "filing_status_input": unit["status"]}
        for unit in units
    ]
    return SimpleNamespace(
        person=pd.DataFrame(person_rows), tax_unit=pd.DataFrame(unit_rows)
    )


def _adult_dependent_household() -> SimpleNamespace:
    # PolicyEngine's age rule would make the 70-year-old parent the head and
    # the 40-year-old filer the spouse (a joint return). The build says the
    # 40-year-old heads a head-of-household return with two dependents.
    return _dataset(
        [
            {
                "id": 7,
                "status": "HEAD_OF_HOUSEHOLD",
                "members": [
                    (71, "HEAD", 40),
                    (72, "DEPENDENT", 70),
                    (73, "DEPENDENT", 10),
                ],
            },
            {
                "id": 8,
                "status": "JOINT",
                "members": [(81, "SPOUSE", 52), (82, "HEAD", 49)],
            },
        ]
    )


def _flags(dataset) -> pd.DataFrame:
    return dataset.person.set_index("person_id")[list(ROLE_VARIABLES.values())]


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------
def test_attach_writes_the_builds_roles_not_the_age_order():
    dataset = _adult_dependent_household()

    roles = attach_source_roles(dataset)

    assert roles is not None
    flags = _flags(dataset)
    assert flags.loc[71].tolist() == [True, False, False]  # HEAD, aged 40
    assert flags.loc[72].tolist() == [False, False, True]  # parent, aged 70
    assert flags.loc[73].tolist() == [False, False, True]
    assert flags.loc[81].tolist() == [False, True, False]  # older SPOUSE
    assert flags.loc[82].tolist() == [True, False, False]  # younger HEAD
    statuses = dataset.tax_unit.set_index("tax_unit_id")["filing_status"]
    assert statuses.to_dict() == {7: "HEAD_OF_HOUSEHOLD", 8: "JOINT"}
    assert roles.person_count == 5
    assert roles.tax_unit_count == 2


def test_missing_columns_mean_nothing_to_pin_and_leave_the_dataset_untouched():
    dataset = _adult_dependent_household()
    dataset.tax_unit = dataset.tax_unit.drop(columns=["filing_status_input"])
    before = (dataset.person.copy(), dataset.tax_unit.copy())

    assert attach_source_roles(dataset) is None

    pd.testing.assert_frame_equal(dataset.person, before[0])
    pd.testing.assert_frame_equal(dataset.tax_unit, before[1])


@pytest.mark.parametrize(
    "source",
    [
        None,
        SimpleNamespace(file_path="/cache/populace_us_2024.h5"),  # loader double
        SimpleNamespace(person=[1, 2], tax_unit=[3]),  # not DataFrames
        "not-an-h5.csv",
        "/definitely/missing/file.h5",
    ],
)
def test_sources_without_entity_tables_are_a_no_op(source):
    assert read_source_roles(source) is None
    assert attach_source_roles(source) is None


def test_tables_under_data_are_found():
    inner = _adult_dependent_household()
    dataset = SimpleNamespace(data=inner)

    assert attach_source_roles(dataset) is not None
    assert "is_tax_unit_head" in inner.person.columns


def test_a_dataset_whose_attribute_access_raises_type_error_is_a_no_op():
    # policyengine-core's Dataset raises TypeError for unknown table names once a
    # simulation has been subsampled.
    class Exploding:
        def __getattr__(self, name):
            raise TypeError(name)

    assert read_source_roles(Exploding()) is None


def test_bytes_values_are_decoded():
    dataset = _adult_dependent_household()
    dataset.person["tax_unit_role_input"] = [
        value.encode() for value in dataset.person["tax_unit_role_input"]
    ]
    dataset.tax_unit["filing_status_input"] = [
        value.encode() for value in dataset.tax_unit["filing_status_input"]
    ]

    roles = read_source_roles(dataset)

    assert roles.person_role.to_dict()[71] == "HEAD"
    assert roles.tax_unit_filing_status.to_dict()[7] == "HEAD_OF_HOUSEHOLD"


def test_string_dtype_columns_as_stored_in_the_h5_are_read():
    dataset = _adult_dependent_household()
    dataset.person["tax_unit_role_input"] = dataset.person[
        "tax_unit_role_input"
    ].astype("string")
    dataset.tax_unit["filing_status_input"] = dataset.tax_unit[
        "filing_status_input"
    ].astype("string")

    assert attach_source_roles(dataset) is not None
    assert _flags(dataset).loc[71].tolist() == [True, False, False]


def test_missing_filing_status_fails_closed_and_names_the_opt_out():
    # The pre-certified f0af251 build has 10,384 tax units like this.
    dataset = _adult_dependent_household()
    dataset.tax_unit.loc[0, "filing_status_input"] = None

    with pytest.raises(SourceRoleError, match="AXIOM_POPULACE_SOURCE_ROLES=0"):
        attach_source_roles(dataset)
    assert "filing_status" not in dataset.tax_unit.columns


@pytest.mark.parametrize(
    ("units", "message"),
    [
        (
            [
                {
                    "id": 1,
                    "status": "SINGLE",
                    "members": [(1, "HEAD", 30), (2, "HEAD", 31)],
                }
            ],
            "exactly one HEAD",
        ),
        (
            [{"id": 1, "status": "SINGLE", "members": [(1, "DEPENDENT", 30)]}],
            "exactly one HEAD",
        ),
        (
            [
                {
                    "id": 1,
                    "status": "JOINT",
                    "members": [(1, "HEAD", 30), (2, "SPOUSE", 31), (3, "SPOUSE", 32)],
                }
            ],
            "more than one SPOUSE",
        ),
        (
            [{"id": 1, "status": "JOINT", "members": [(1, "HEAD", 30)]}],
            "JOINT without a SPOUSE",
        ),
        (
            [
                {
                    "id": 1,
                    "status": "SINGLE",
                    "members": [(1, "HEAD", 30), (2, "SPOUSE", 31)],
                }
            ],
            "does not file JOINT",
        ),
        (
            [{"id": 1, "status": "SINGLE", "members": [(1, "BOSS", 30)]}],
            "unknown value",
        ),
        (
            [{"id": 1, "status": "MARRIED", "members": [(1, "HEAD", 30)]}],
            "unknown value",
        ),
    ],
)
def test_contradictory_roles_raise(units, message):
    with pytest.raises(SourceRoleError, match=message):
        read_source_roles(_dataset(units))


def test_a_person_in_an_unlisted_tax_unit_raises():
    dataset = _adult_dependent_household()
    dataset.tax_unit = dataset.tax_unit[dataset.tax_unit["tax_unit_id"] == 7]

    with pytest.raises(SourceRoleError):
        read_source_roles(dataset)


def test_duplicate_ids_raise():
    dataset = _adult_dependent_household()
    dataset.tax_unit = pd.concat([dataset.tax_unit, dataset.tax_unit.iloc[[0]]])

    with pytest.raises(SourceRoleError, match="unique"):
        read_source_roles(dataset)


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("0", False),
        ("false", False),
        ("OFF", False),
    ],
)
def test_source_roles_env_switch(monkeypatch, value, enabled):
    if value is None:
        monkeypatch.delenv(source_roles.SOURCE_ROLES_ENV, raising=False)
    else:
        monkeypatch.setenv(source_roles.SOURCE_ROLES_ENV, value)
    assert source_roles.source_roles_enabled() is enabled


def test_entity_h5_path_is_read_and_variable_centric_h5_is_skipped(tmp_path):
    pytest.importorskip("tables")
    dataset = _adult_dependent_household()
    entity = tmp_path / "entity.h5"
    with pd.HDFStore(entity, mode="w") as store:
        store.put("person", dataset.person, format="table")
        store.put("tax_unit", dataset.tax_unit, format="table")
    variable_centric = tmp_path / "variable.h5"
    with pd.HDFStore(variable_centric, mode="w") as store:
        store.put("age", pd.DataFrame({"2024": [40.0, 70.0]}))

    assert read_source_roles(entity).person_role.to_dict()[72] == "DEPENDENT"
    assert read_source_roles(variable_centric) is None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
@st.composite
def valid_units(draw):
    """Tax units that satisfy the build's role contract, with shuffled ids."""
    n_units = draw(st.integers(min_value=1, max_value=12))
    unit_ids = draw(
        st.lists(st.integers(0, 10**9), min_size=n_units, max_size=n_units, unique=True)
    )
    sizes = [draw(st.integers(1, 5)) for _ in range(n_units)]
    person_ids = draw(
        st.lists(
            st.integers(0, 10**9),
            min_size=sum(sizes),
            max_size=sum(sizes),
            unique=True,
        )
    )
    units = []
    cursor = 0
    for unit_id, size in zip(unit_ids, sizes, strict=True):
        spouse = size >= 2 and draw(st.booleans())
        roles = ["HEAD"] + (["SPOUSE"] if spouse else [])
        roles += ["DEPENDENT"] * (size - len(roles))
        roles = draw(st.permutations(roles))
        members = [
            (person_ids[cursor + i], role, draw(st.integers(0, 99)))
            for i, role in enumerate(roles)
        ]
        cursor += size
        status = "JOINT" if spouse else draw(st.sampled_from(NON_JOINT))
        units.append({"id": unit_id, "status": status, "members": members})
    return units


def _expected(units):
    role = {pid: r for unit in units for pid, r, _ in unit["members"]}
    status = {unit["id"]: unit["status"] for unit in units}
    return role, status


PROPERTY_SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@PROPERTY_SETTINGS
@given(valid_units(), st.randoms(use_true_random=False))
def test_attach_reproduces_the_source_for_any_valid_build(units, rng):
    dataset = _dataset(units)
    # Row order must not matter: everything aligns by id.
    dataset.person = dataset.person.sample(frac=1, random_state=rng.randint(0, 999))
    dataset.tax_unit = dataset.tax_unit.sample(frac=1, random_state=rng.randint(0, 999))
    role, status = _expected(units)

    attach_source_roles(dataset)

    flags = _flags(dataset)
    # Every person holds exactly one role, and it is the source role.
    assert (flags.sum(axis=1) == 1).all()
    for name, variable in ROLE_VARIABLES.items():
        expected = pd.Series({pid: r == name for pid, r in role.items()})
        assert flags[variable].to_dict() == expected.to_dict()
    # Every tax unit has exactly one head and at most one spouse.
    by_unit = dataset.person.groupby("person_tax_unit_id")
    assert (by_unit["is_tax_unit_head"].sum() == 1).all()
    assert (by_unit["is_tax_unit_spouse"].sum() <= 1).all()
    # Filing status is the source's, and JOINT exactly when there is a spouse.
    got_status = dataset.tax_unit.set_index("tax_unit_id")["filing_status"].to_dict()
    assert got_status == status
    has_spouse = by_unit["is_tax_unit_spouse"].sum().astype(bool).to_dict()
    assert {u: s == "JOINT" for u, s in got_status.items()} == has_spouse


@PROPERTY_SETTINGS
@given(valid_units())
def test_attach_is_idempotent_and_touches_only_the_pinned_columns(units):
    dataset = _dataset(units)
    original_person = dataset.person.copy()
    original_unit = dataset.tax_unit.copy()

    attach_source_roles(dataset)
    once = (dataset.person.copy(), dataset.tax_unit.copy())
    attach_source_roles(dataset)

    pd.testing.assert_frame_equal(dataset.person, once[0])
    pd.testing.assert_frame_equal(dataset.tax_unit, once[1])
    pd.testing.assert_frame_equal(
        dataset.person[original_person.columns], original_person
    )
    pd.testing.assert_frame_equal(
        dataset.tax_unit[original_unit.columns], original_unit
    )
    assert set(dataset.person.columns) - set(original_person.columns) == set(
        ROLE_VARIABLES.values()
    )
    assert set(dataset.tax_unit.columns) - set(original_unit.columns) == {
        "filing_status"
    }


CORRUPTIONS = (
    "drop_head",
    "second_head",
    "missing_role",
    "missing_status",
    "unknown_status",
    "flip_joint",
)


@PROPERTY_SETTINGS
@given(valid_units(), st.sampled_from(CORRUPTIONS), st.data())
def test_any_contract_violation_is_refused_not_half_pinned(units, corruption, data):
    dataset = _dataset(units)
    person, tax_unit = dataset.person, dataset.tax_unit
    unit_id = data.draw(st.sampled_from(sorted(tax_unit["tax_unit_id"])))
    members = person.index[person["person_tax_unit_id"] == unit_id]
    head = members[(person.loc[members, "tax_unit_role_input"] == "HEAD").to_numpy()][0]
    if corruption == "drop_head":
        person.loc[head, "tax_unit_role_input"] = "DEPENDENT"
    elif corruption == "second_head":
        others = [i for i in members if i != head]
        if others:
            person.loc[others[0], "tax_unit_role_input"] = "HEAD"
        else:  # one-person unit: add a second head
            extra = person.loc[[head]].assign(person_id=person["person_id"].max() + 1)
            dataset.person = person = pd.concat([person, extra], ignore_index=True)
    elif corruption == "missing_role":
        person.loc[head, "tax_unit_role_input"] = None
    elif corruption == "missing_status":
        tax_unit.loc[tax_unit["tax_unit_id"] == unit_id, "filing_status_input"] = None
    elif corruption == "unknown_status":
        tax_unit.loc[tax_unit["tax_unit_id"] == unit_id, "filing_status_input"] = "MFJ"
    elif corruption == "flip_joint":
        row = tax_unit["tax_unit_id"] == unit_id
        status = tax_unit.loc[row, "filing_status_input"].iloc[0]
        tax_unit.loc[row, "filing_status_input"] = (
            "SINGLE" if status == "JOINT" else "JOINT"
        )

    with pytest.raises(SourceRoleError):
        attach_source_roles(dataset)
    assert "is_tax_unit_head" not in dataset.person.columns


# ---------------------------------------------------------------------------
# Simulation-level pin, and agreement with the dataset-level attach
# ---------------------------------------------------------------------------
class _Period:
    def __init__(self, text: str):
        self.text = text
        self.unit = "month" if "-" in text else "year"

    def __str__(self):
        return self.text


class FakeSim:
    """Records set_input calls; serves ids in a fixed (possibly shuffled) order."""

    def __init__(self, person_ids, tax_unit_ids, *, years=("2024", "2025"), known=None):
        self._ids = {
            "person_id": np.asarray(person_ids),
            "tax_unit_id": np.asarray(tax_unit_ids),
        }
        self._known = {
            "household_weight": [_Period(y) for y in years] + [_Period("2024-01")],
            **(known or {}),
        }
        self.inputs: dict[tuple[str, str], np.ndarray] = {}

    def calculate(self, variable, period):
        return SimpleNamespace(values=self._ids[variable])

    def get_known_periods(self, variable):
        return self._known.get(variable, [])

    def set_input(self, variable, period, values):
        self.inputs[(variable, str(period))] = np.asarray(values)


@PROPERTY_SETTINGS
@given(valid_units(), st.randoms(use_true_random=False))
def test_sim_level_pin_agrees_with_the_dataset_level_attach(units, rng):
    dataset = _dataset(units)
    roles = read_source_roles(dataset)
    person_order = list(dataset.person["person_id"])
    unit_order = list(dataset.tax_unit["tax_unit_id"])
    rng.shuffle(person_order)
    rng.shuffle(unit_order)
    sim = FakeSim(person_order, unit_order)

    periods = pin_source_roles(sim, roles)
    attach_source_roles(dataset)

    # Default periods are the data years, not month periods.
    assert periods == ("2024", "2025")
    flags = _flags(dataset)
    statuses = dataset.tax_unit.set_index("tax_unit_id")["filing_status"]
    for period in periods:
        for variable in ROLE_VARIABLES.values():
            assert sim.inputs[(variable, period)].tolist() == [
                bool(flags.loc[pid, variable]) for pid in person_order
            ]
        assert sim.inputs[("filing_status", period)].tolist() == [
            statuses.loc[uid] for uid in unit_order
        ]


def test_pin_refuses_once_a_role_variable_has_been_calculated():
    dataset = _adult_dependent_household()
    roles = read_source_roles(dataset)
    sim = FakeSim(
        dataset.person["person_id"],
        dataset.tax_unit["tax_unit_id"],
        known={"tax_unit_is_joint": [_Period("2026")]},
    )

    with pytest.raises(SourceRoleError, match="before calculating"):
        pin_source_roles(sim, roles, periods=[2026])
    assert sim.inputs == {}


def test_pin_refuses_when_roles_miss_a_simulated_person():
    dataset = _adult_dependent_household()
    roles = read_source_roles(dataset)
    sim = FakeSim([71, 72, 73, 81, 82, 999], dataset.tax_unit["tax_unit_id"])

    with pytest.raises(SourceRoleError, match="do not cover"):
        pin_source_roles(sim, roles, periods=[2024])


def test_pin_without_roles_pins_nothing():
    sim = FakeSim([1], [1])
    assert pin_source_roles(sim, None) == ()
    assert sim.inputs == {}


# ---------------------------------------------------------------------------
# End to end through policyengine-us (skipped without the policyengine extra)
# ---------------------------------------------------------------------------
def _tiny_us_dataset(policyengine_us_data):
    source = _adult_dependent_household()
    person = source.person.assign(
        person_household_id=[1, 1, 1, 2, 2],
        person_spm_unit_id=[1, 1, 1, 2, 2],
        person_family_id=[1, 1, 1, 2, 2],
        person_marital_unit_id=[1, 2, 3, 4, 4],
        employment_income=[60_000.0, 0.0, 0.0, 40_000.0, 50_000.0],
    )
    return policyengine_us_data.USSingleYearDataset(
        person=person,
        household=pd.DataFrame(
            {
                "household_id": [1, 2],
                "household_weight": [1.0, 1.0],
                "state_fips": [6, 6],
            }
        ),
        tax_unit=source.tax_unit.copy(),
        spm_unit=pd.DataFrame({"spm_unit_id": [1, 2]}),
        family=pd.DataFrame({"family_id": [1, 2]}),
        marital_unit=pd.DataFrame({"marital_unit_id": [1, 2, 3, 4]}),
        time_period=2024,
    )


@pytest.mark.parametrize("attach", [False, True])
def test_policyengine_us_uses_the_attached_roles_in_every_year(attach):
    policyengine_us = pytest.importorskip("policyengine_us")
    from policyengine_us import data as policyengine_us_data

    dataset = _tiny_us_dataset(policyengine_us_data)
    if attach:
        attach_source_roles(dataset)
    sim = policyengine_us.Microsimulation(dataset=dataset)

    for year in (2024, 2026):
        head = dict(
            zip(
                sim.calculate("person_id", year).values,
                sim.calculate("is_tax_unit_head", year).values,
                strict=True,
            )
        )
        status = dict(
            zip(
                sim.calculate("tax_unit_id", year).values,
                np.asarray(sim.calculate("filing_status", year).values).astype(str),
                strict=True,
            )
        )
        if attach:
            # The build's own answer, at the data year and a projected year.
            assert head == {71: True, 72: False, 73: False, 81: False, 82: True}
            assert status == {7: "HEAD_OF_HOUSEHOLD", 8: "JOINT"}
        else:
            # Documents the replaced behavior: the oldest adult becomes head.
            assert head[72] and not head[71]
