"""The constructor's tax-unit roles in a real PolicyEngine-US (axiom-oracles#633).

The same checks as ``tests/test_source_tax_unit_roles.py``, over a real
``policyengine_us.Microsimulation`` built from a Populace-shaped dataset. The
expectations come from the constructor's roles and from two statutes.

26 USC 6013(a), U.S. Code 2024 edition (govinfo USCODE-2024-title26, section
6013), verbatim:

    (a) Joint returns
    A husband and wife may make a single return jointly of income taxes under
    subtitle A, even though one of the spouses has neither gross income nor
    deductions, except as provided below:

26 USC 32(c)(1)(A)(ii)(II), U.S. Code 2024 edition (govinfo, section 32),
verbatim:

    (II) such individual (or, if the individual is married, either the
    individual or the individual's spouse) has attained age 25 but not
    attained age 65 before the close of the taxable year,

These tests run under whatever PolicyEngine-US is installed:

- one without ``tax_unit_role_input`` (before PolicyEngine/policyengine-us#9617,
  first in 2.34.0) takes the roles as ``is_tax_unit_head`` /
  ``is_tax_unit_spouse`` inputs;
- one with it reads them natively.

CI's policyengine-live job runs this file under one of each, so the two paths
are checked against the same expectations. Without policyengine-us the tests
skip, unless AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE=1 turns the skip into a
failure.
"""

from __future__ import annotations

import importlib.metadata
import os
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles.bridges import tax_populace
from axiom_oracles.bridges.tax_populace import (
    group_person_rows_by_tax_unit,
    project_eitc_tax_unit_inputs,
    project_tax_unit_person_contexts,
    tax_unit_filers,
)
from axiom_oracles.bridges.tax_unit_roles import (
    ROLES_INPUTS,
    ROLES_NATIVE,
    policyengine_reads_role_input,
    populace_us_microsimulation,
)
from axiom_oracles.core.case import Concepts
from axiom_oracles.populations.populace_us import PopulaceUsCaseLoader

REQUIRE_LIVE = os.environ.get("AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE") == "1"
# Set by each CI job to the path its policyengine-us must take.
EXPECTED_PATH = os.environ.get("AXIOM_ORACLES_EXPECT_ROLE_PATH")
DATA_YEAR = 2024
YEAR = 2026
AGE_INPUT = "childless_taxpayer_or_spouse_age_eligible_for_eitc"

# Populace units from axiom-oracles#633: (age, constructor role) per member.
ISSUE_UNITS = {
    138: [(85, "HEAD"), (60, "DEPENDENT")],
    1058: [(74, "HEAD"), (47, "DEPENDENT")],
    1452: [(80, "HEAD"), (64, "DEPENDENT")],
    3824: [(65, "DEPENDENT"), (36, "HEAD")],
    57137: [(85, "DEPENDENT"), (65, "HEAD"), (64, "SPOUSE")],
}
# Clause (II) over each unit's constructor HEAD and SPOUSE.
ISSUE_AGE_TEST = {138: False, 1058: False, 1452: False, 3824: True, 57137: True}


@pytest.fixture(scope="module")
def pe():
    def unavailable(reason: str):
        if REQUIRE_LIVE:
            pytest.fail(reason)
        pytest.skip(reason)

    try:
        import policyengine_us
        from policyengine_us.data import USSingleYearDataset
    except ImportError:
        unavailable("policyengine-us is not installed")
    return SimpleNamespace(
        module=policyengine_us,
        Dataset=USSingleYearDataset,
        version=importlib.metadata.version("policyengine-us"),
    )


def populace_dataset(pe, units):
    """A Populace-shaped dataset: one household, SPM unit and family per tax
    unit; the HEAD and SPOUSE share a marital unit, as a married couple does."""
    persons, households, tax_units, spm_units, families, marital_units = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    person_id = 0
    marital_unit_id = 0
    for tax_unit_id, members in units.items():
        households.append(
            {"household_id": tax_unit_id, "household_weight": 1.0, "state_fips": 6}
        )
        tax_units.append({"tax_unit_id": tax_unit_id})
        spm_units.append({"spm_unit_id": tax_unit_id})
        families.append({"family_id": tax_unit_id})
        couple_unit = None
        for age, role in members:
            person_id += 1
            if role in {"HEAD", "SPOUSE"} and couple_unit is not None:
                marital = couple_unit
            else:
                marital_unit_id += 1
                marital = marital_unit_id
                marital_units.append({"marital_unit_id": marital})
                if role in {"HEAD", "SPOUSE"}:
                    couple_unit = marital
            persons.append(
                {
                    "person_id": person_id,
                    "age": float(age),
                    "employment_income": 9_000.0 if role != "DEPENDENT" else 0.0,
                    "person_household_id": tax_unit_id,
                    "person_tax_unit_id": tax_unit_id,
                    "person_spm_unit_id": tax_unit_id,
                    "person_family_id": tax_unit_id,
                    "person_marital_unit_id": marital,
                    "tax_unit_role_input": role,
                }
            )
    return pe.Dataset(
        person=pd.DataFrame(persons),
        household=pd.DataFrame(households),
        tax_unit=pd.DataFrame(tax_units),
        spm_unit=pd.DataFrame(spm_units),
        family=pd.DataFrame(families),
        marital_unit=pd.DataFrame(marital_units),
        time_period=DATA_YEAR,
    )


def values(sim, variable, year):
    result = sim.calculate(variable, year)
    if hasattr(result, "decode_to_str"):
        return [str(value) for value in result.decode_to_str()]
    raw = result.values if hasattr(result, "values") else result
    return list(raw)


@pytest.fixture(scope="module")
def issue_sim(pe):
    dataset = populace_dataset(pe, ISSUE_UNITS)
    return dataset, populace_us_microsimulation(
        dataset, data_year=DATA_YEAR, year=YEAR
    )


def test_role_flags_are_the_constructors_in_every_compared_year(pe, issue_sim):
    dataset, sim = issue_sim
    roles = list(dataset.person["tax_unit_role_input"])
    for year in range(DATA_YEAR, YEAR + 1):
        assert [bool(v) for v in values(sim, "is_tax_unit_head", year)] == [
            role == "HEAD" for role in roles
        ]
        assert [bool(v) for v in values(sim, "is_tax_unit_spouse", year)] == [
            role == "SPOUSE" for role in roles
        ]
        assert [bool(v) for v in values(sim, "is_tax_unit_dependent", year)] == [
            role == "DEPENDENT" for role in roles
        ]


def test_the_path_matches_the_installed_policyengine(pe, issue_sim):
    _, sim = issue_sim
    native = "tax_unit_role_input" in pe.module.CountryTaxBenefitSystem().variables
    assert policyengine_reads_role_input(sim) is native
    if EXPECTED_PATH:
        assert (ROLES_NATIVE if native else ROLES_INPUTS) == EXPECTED_PATH, pe.version


def test_policyengine_files_jointly_only_with_a_constructor_spouse(pe, issue_sim):
    """26 USC 6013(a): only 57137's roles name a spouse. PolicyEngine-US
    1.764.6 without the roles files 138, 1058, 1452 and 3824 jointly too."""
    dataset, sim = issue_sim
    statuses = dict(
        zip(
            dataset.tax_unit["tax_unit_id"],
            values(sim, "filing_status", YEAR),
            strict=True,
        )
    )
    assert {tid for tid, status in statuses.items() if status == "JOINT"} == {57137}


def _bridge_and_case_surfaces(pe, monkeypatch, units):
    dataset = populace_dataset(pe, units)
    monkeypatch.setattr(
        tax_populace, "load_populace_dataset", lambda *_args, **_kwargs: dataset
    )
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
    loader = PopulaceUsCaseLoader(dataset="populace://test/populace.h5")
    loader._build_microsimulation_and_dataset = lambda _dataset: (
        pe.module.Microsimulation(dataset=dataset),
        dataset,
    )
    cases = {
        int(case.metadata["tax_unit_id"]): case
        for case in loader.load_cases(period=str(YEAR), case_unit="tax_unit")
    }
    return pe_data, cases


def test_bridge_and_case_loader_describe_the_constructors_unit(pe, monkeypatch):
    pe_data, cases = _bridge_and_case_surfaces(pe, monkeypatch, ISSUE_UNITS)
    expected_mode = (
        ROLES_NATIVE
        if "tax_unit_role_input" in pe.module.CountryTaxBenefitSystem().variables
        else ROLES_INPUTS
    )
    assert pe_data["tax_unit_roles"] == expected_mode
    by_unit = group_person_rows_by_tax_unit(pe_data["persons"])
    statuses = dict(
        zip(
            pe_data["tax_units"]["tax_unit_id"],
            pe_data["tax_units"]["filing_status"],
            strict=True,
        )
    )
    for tax_unit_id, members in ISSUE_UNITS.items():
        persons = by_unit[tax_unit_id]
        constructor_filers = [age for age, role in members if role == "HEAD"] + [
            age for age, role in members if role == "SPOUSE"
        ]
        assert [int(p["age"]) for p in tax_unit_filers(persons)] == constructor_filers
        assert [
            c.is_tax_unit_dependent for c in project_tax_unit_person_contexts(persons)
        ] == [role == "DEPENDENT" for _, role in members]
        row = {"filing_status": statuses[tax_unit_id], "adjusted_gross_income": 9_000}
        projected = project_eitc_tax_unit_inputs(row=row, persons=persons)
        assert projected[AGE_INPUT] is ISSUE_AGE_TEST[tax_unit_id]
        assert (statuses[tax_unit_id] == "JOINT") is (tax_unit_id == 57137)
        relations = [
            str(entity.fact(Concepts.HOUSEHOLD_RELATION, ""))
            for entity in cases[tax_unit_id].entities
        ]
        assert relations == [
            {"HEAD": "HeadOfHousehold", "SPOUSE": "Spouse", "DEPENDENT": "Dependent"}[
                role
            ]
            for _, role in members
        ]


@st.composite
def constructor_units(draw):
    """Valid constructor units in any member order: one HEAD, at most one
    SPOUSE, the rest DEPENDENT."""
    units = {}
    for tax_unit_id in range(1, draw(st.integers(min_value=1, max_value=6)) + 1):
        size = draw(st.integers(min_value=1, max_value=4))
        roles = ["HEAD"]
        if size > 1 and draw(st.booleans()):
            roles.append("SPOUSE")
        roles += ["DEPENDENT"] * (size - len(roles))
        units[tax_unit_id] = [
            (draw(st.integers(min_value=0, max_value=100)), role)
            for role in draw(st.permutations(roles))
        ]
    return units


@settings(
    max_examples=6,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(units=constructor_units())
def test_property_real_policyengine_follows_any_constructor_unit(pe, units):
    """For any valid constructor units: the flags are the roles, a DEPENDENT is
    never a filer, and PolicyEngine files jointly exactly when the roles name
    a SPOUSE (26 USC 6013(a))."""
    dataset = populace_dataset(pe, units)
    sim = populace_us_microsimulation(dataset, data_year=DATA_YEAR, year=YEAR)
    roles = list(dataset.person["tax_unit_role_input"])
    assert [bool(v) for v in values(sim, "is_tax_unit_head", YEAR)] == [
        role == "HEAD" for role in roles
    ]
    assert [bool(v) for v in values(sim, "is_tax_unit_spouse", YEAR)] == [
        role == "SPOUSE" for role in roles
    ]
    statuses = dict(
        zip(dataset.tax_unit["tax_unit_id"], values(sim, "filing_status", YEAR))
    )
    for tax_unit_id, members in units.items():
        has_spouse = any(role == "SPOUSE" for _, role in members)
        assert (statuses[tax_unit_id] == "JOINT") is has_spouse
