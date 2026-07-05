import sys

import pytest

from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.policyengine.runner import (
    _normalize_value_for_requested_period,
)
from axiom_oracles.adapters.prd import PrdPackageRunner
from axiom_oracles.adapters.taxcalc import TaxCalcPackageRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner
from axiom_oracles.adapters.yale_taxsim import YaleTaxSimulatorRunner
from axiom_oracles.core.case import Case, Concepts, Entity


class _FakeVariable:
    def __init__(self, definition_period: str) -> None:
        self.definition_period = definition_period


class _FakePolicyEngineModel:
    def __init__(self, definition_period: str) -> None:
        self.definition_period = definition_period

    def get_variable(self, variable: str) -> _FakeVariable:
        del variable
        return _FakeVariable(self.definition_period)


class _FakePolicyEngine:
    def __init__(self, definition_period: str) -> None:
        self.us = type("FakeUS", (), {"model": _FakePolicyEngineModel(definition_period)})()


def test_policyengine_monthly_numeric_output_is_normalized_for_month_period() -> None:
    value = _normalize_value_for_requested_period(
        _FakePolicyEngine("month"),
        "snap",
        "2026-01",
        1_846.6170654296875,
    )

    assert value == 1_846.6170654296875 / 12


def test_policyengine_normalization_preserves_booleans_and_annual_values() -> None:
    assert (
        _normalize_value_for_requested_period(
            _FakePolicyEngine("month"),
            "is_snap_eligible",
            "2026-01",
            True,
        )
        is True
    )
    assert (
        _normalize_value_for_requested_period(
            _FakePolicyEngine("year"),
            "income_tax",
            "2026-01",
            1200,
        )
        == 1200
    )


def test_taxsim_package_runner_wraps_taxsim_format_rows() -> None:
    captured_inputs = []

    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            captured_inputs.append(input_frame)

        def run(self, show_progress=False):
            del show_progress
            return [
                {"taxsimid": "case-1", "fiitax": 100, "siitax": 25, "unused": 1}
            ]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={
            "taxsim_input": {
                "year": 2024,
                "state": 36,
                "mstat": 1,
                "page": 40,
            }
        },
    )

    results = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner).run_cases(
        [case],
        variables=["fiitax", "siitax"],
    )

    assert captured_inputs[0].iloc[0]["taxsimid"] == "case-1"
    assert captured_inputs[0].iloc[0]["year"] == 2024
    assert results[0].engine == "taxsim"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"fiitax": 100, "siitax": 25}


def test_taxsim_package_runner_projects_cases_and_maps_canonical_concepts() -> None:
    captured_inputs = []

    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            captured_inputs.append(input_frame)

        def run(self, show_progress=False):
            del show_progress
            return [{"taxsimid": 1.0, "fiitax": 100, "siitax": 25, "unused": 1}]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={"scope": {"type": "census_state", "geoid": "36"}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
        ),
    )

    results = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner).run_cases(
        [case],
        variables=[
            Concepts.FEDERAL_INCOME_TAX,
            Concepts.STATE_INCOME_TAX,
        ],
    )

    input_row = captured_inputs[0].to_dict(orient="records")[0]
    assert input_row["taxsimid"] == 1
    assert input_row["state"] == 33
    assert results[0].household_id == "case-1"
    assert results[0].values == {"fiitax": 100, "siitax": 25}


def test_policyengine_taxsim_runner_maps_taxsim_output_to_policyengine_targets() -> None:
    captured_inputs = []

    class FakePolicyEngineTaxsimRunner:
        def __init__(self, input_frame):
            captured_inputs.append(input_frame)

        def run(self, show_progress=False):
            del show_progress
            return [{"taxsimid": "case-1", "fiitax": 100, "siitax": 25, "unused": 1}]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={
            "taxsim_input": {
                "taxsimid": "case-1",
                "year": 2024,
                "state": 33,
                "mstat": 1,
                "page": 40,
            }
        },
    )

    results = PolicyEngineTaxsimRunner(
        runner_factory=FakePolicyEngineTaxsimRunner
    ).run_cases(
        [case],
        variables=[
            Concepts.FEDERAL_INCOME_TAX,
            Concepts.STATE_INCOME_TAX,
        ],
    )

    assert captured_inputs[0].iloc[0]["state"] == 33
    assert results[0].engine == "policyengine"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"income_tax": 100, "state_income_tax": 25}


def test_taxcalc_package_runner_wraps_taxcalc_rows_and_maps_concepts() -> None:
    captured_inputs = []
    captured_variables = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            captured_variables.extend(variables or [])
            return [{"RECID": "case-1", "iitax": 100, "c00100": 50_000}]

    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "taxcalc_input": {
                "FLPDYR": 2026,
                "MARS": 1,
                "age_head": 40,
                "e00200": 50_000,
            }
        },
    )

    results = TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX, Concepts.AGI],
    )

    assert captured_inputs[0]["RECID"] == "case-1"
    assert captured_inputs[0]["FLPDYR"] == 2026
    assert captured_variables == ["iitax", "c00100"]
    assert results[0].engine == "taxcalc"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"iitax": 100, "c00100": 50_000}


def test_taxcalc_package_runner_projects_thin_case_inputs() -> None:
    captured_inputs = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
        ),
    )

    results = TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["FLPDYR"] == 2026
    assert captured_inputs[0]["MARS"] == 1
    assert captured_inputs[0]["e00200"] == 50_000
    assert results[0].household_id == "case-1"
    assert results[0].values == {"iitax": 100}


def test_taxcalc_package_runner_projects_dependent_credit_counts() -> None:
    captured_inputs = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
            Entity(
                "child-5",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 5,
                },
            ),
            Entity(
                "child-17",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 17,
                },
            ),
            Entity(
                "disabled-dependent",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 40,
                    Concepts.DISABLED: True,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    input_row = captured_inputs[0]
    assert input_row["MARS"] == 4
    assert input_row["EIC"] == 3
    assert input_row["n24"] == 1
    assert input_row["nu18"] == 2
    assert input_row["nu13"] == 1
    assert input_row["nu06"] == 1


def test_taxcalc_package_runner_limits_head_of_household_to_qualifying_dependents() -> None:
    captured_inputs = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 66,
                },
            ),
            Entity(
                "adult-dependent",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Dependent",
                    Concepts.PERSON_AGE: 34,
                    Concepts.DISABLED: True,
                    Concepts.YEARLY_EARNED_INCOME: 21_866,
                    Concepts.SELF_EMPLOYMENT_INCOME: 5_010,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["MARS"] == 1


def test_taxcalc_package_runner_caps_qualified_dividends_at_total_dividends() -> None:
    captured_inputs = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.DIVIDEND_INCOME: 100,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 250,
                    Concepts.PENSION_INCOME: 1_000,
                    Concepts.RENTAL_INCOME: 500,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["e00600"] == 100
    assert captured_inputs[0]["e00650"] == 100
    assert captured_inputs[0]["e01500"] == 1_000
    assert captured_inputs[0]["e01700"] == 1_000
    assert captured_inputs[0]["e02000"] == 500


def test_taxcalc_package_runner_reports_legal_eitc_entitlement_when_installed() -> None:
    pytest.importorskip("taxcalc")

    variables = [Concepts.EITC]
    cases = [
        Case(
            case_id=f"age-{age}",
            period="2024",
            entities=(
                Entity(
                    "head",
                    "person",
                    facts={
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.PERSON_AGE: age,
                        Concepts.YEARLY_EARNED_INCOME: 15_000,
                    },
                ),
            ),
            outputs=tuple(variables),
        )
        for age in (64, 65)
    ]

    results = TaxCalcPackageRunner().run_cases(cases, variables=variables)

    assert round(results[0].values["eitc"], 2) == 274.75
    assert results[1].values["eitc"] == 0


def test_yale_taxsim_runner_wraps_bridge_rows_and_maps_concepts() -> None:
    captured_inputs = []
    captured_variables = []

    class FakeYaleRunner:
        def run(self, input_rows, variables=None):
            captured_inputs.extend(input_rows)
            captured_variables.extend(variables or [])
            return [{"id": "case-1", "liab_iit_net": 100, "agi": 50_000}]

    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "yale_taxsim_input": {
                "year": 2026,
                "filing_status": 1,
                "wages": 50_000,
            }
        },
    )

    results = YaleTaxSimulatorRunner(runner=FakeYaleRunner()).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX, Concepts.AGI],
    )

    assert captured_inputs[0]["id"] == "case-1"
    assert captured_inputs[0]["year"] == 2026
    assert captured_variables == ["liab_iit_net", "agi"]
    assert results[0].engine == "yale_taxsim"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"liab_iit_net": 100, "agi": 50_000}


def test_yale_taxsim_command_runner_uses_csv_contract(tmp_path) -> None:
    script = tmp_path / "fake_yale.py"
    script.write_text(
        """
import csv
import os

with open(os.environ["AXIOM_ORACLES_YALE_INPUT"], newline="") as f:
    rows = list(csv.DictReader(f))

with open(os.environ["AXIOM_ORACLES_YALE_OUTPUT"], "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "liab_iit_net", "agi"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"id": row["id"], "liab_iit_net": 100, "agi": row["wages"]})
""".lstrip()
    )
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "yale_taxsim_input": {
                "year": 2026,
                "filing_status": 1,
                "wages": 50_000,
            }
        },
    )

    results = YaleTaxSimulatorRunner(command=[sys.executable, str(script)]).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX, Concepts.AGI],
    )

    assert results[0].values == {"liab_iit_net": 100, "agi": 50_000}


def test_prd_package_runner_wraps_external_prd_households() -> None:
    passed_households = []
    passed_programs = []

    class FakePrdRunner:
        def run_households(self, households, programs=None):
            passed_households.extend(households)
            passed_programs.extend(programs or [])
            return [{"hhid": "case-1", "value.snap": 120, "value.wic": 40}]

    prd_household = object()
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={"prd_household": prd_household},
    )

    results = PrdPackageRunner(runner=FakePrdRunner()).run_cases(
        [case],
        variables=[Concepts.SNAP_BENEFIT],
    )

    assert passed_households == [prd_household]
    assert passed_programs == ["value.snap"]
    assert results[0].engine == "prd"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"value.snap": 120}
