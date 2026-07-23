from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.policyengine.runner import (
    _normalize_value_for_requested_period,
)
from axiom_oracles.adapters.prd import PrdPackageRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner
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


def test_policyengine_taxsim_pairs_prefer_canonical_concepts_on_shared_columns() -> None:
    from axiom_oracles.adapters.policyengine.taxsim_runner import (
        _taxsim_to_policyengine_pairs,
    )

    # The state pilot concepts share TAXSIM's `siitax` with the canonical
    # state-liability concept. The canonical mapping is declared first, so it
    # must claim the column no matter how many pilots are requested after it;
    # the pilots' PolicyEngine variables are not produced by the
    # policyengine-taxsim emulator and must stay unmapped rather than
    # clobbering `state_income_tax` (the last-writer-wins regression the
    # 2026-07-21 ECPS run surfaced).
    pairs = _taxsim_to_policyengine_pairs(
        [
            "state_income_tax",
            "nc_income_tax_before_credits",
            "co_income_tax_before_non_refundable_credits",
        ]
    )
    assert pairs["siitax"] == "state_income_tax"


def test_policyengine_taxsim_pairs_carry_aggregates_for_list_targets() -> None:
    from axiom_oracles.adapters.policyengine.taxsim_runner import (
        _taxsim_to_policyengine_pairs,
    )

    # Concepts whose PolicyEngine target is a summed list (employee_fica,
    # tax_before_credits) map their TAXSIM aggregate onto the first list
    # component; the comparator sums the components that are present, so the
    # concept-level value reproduces the aggregate exactly.
    pairs = _taxsim_to_policyengine_pairs(
        [
            "employee_social_security_tax",
            "employee_medicare_tax",
            "self_employment_tax",
            "income_tax_main_rates",
            "capital_gains_tax",
        ]
    )
    assert pairs["tfica"] == "employee_social_security_tax"
    assert pairs["v28"] == "income_tax_main_rates"


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
    # Concept targets name output columns; the runner translates them to the
    # R package's program selectors before invoking PRD.
    assert passed_programs == ["SNAP"]
    assert results[0].engine == "prd"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"value.snap": 120}


def test_prd_package_runner_normalizes_annual_benefits_to_month_periods() -> None:
    class FakePrdRunner:
        def run_households(self, households, programs=None):
            del households, programs
            return [
                {"hhid": "case-1", "value.snap": 6432.0, "tax.income.state": 238.0}
            ]

    case = Case(
        case_id="case-1",
        period="2026-01",
        metadata={"prd_household": object()},
    )

    results = PrdPackageRunner(runner=FakePrdRunner()).run_cases([case])

    # PRD emits annual sums; month-period comparisons read one month for
    # month-defined benefit columns, mirroring the PolicyEngine convention.
    assert results[0].values["value.snap"] == 536.0
    # Non-benefit columns pass through untouched.
    assert results[0].values["tax.income.state"] == 238.0


def test_prd_package_runner_joins_hhid_rows_back_to_case_ids() -> None:
    class FakeHousehold:
        def __init__(self, household_id):
            self.household_id = household_id

    class FakePrdRunner:
        def run_households(self, households, programs=None):
            del households, programs
            # One row per person, household values repeated on every member
            # row, float hhids — the shape the R package actually returns.
            return [
                {"hhid": 1.0, "value.snap": 6432.0},
                {"hhid": 2.0, "value.snap": 5851.0},
                {"hhid": 2.0, "value.snap": 5851.0},
                {"hhid": 2.0, "value.snap": 5851.0},
            ]

    cases = [
        Case(
            case_id="ecps-77",
            period="2026-01",
            metadata={"prd_household": FakeHousehold(1)},
        ),
        Case(
            case_id="ecps-99",
            period="2026-01",
            metadata={"prd_household": FakeHousehold(2)},
        ),
    ]

    results = PrdPackageRunner(runner=FakePrdRunner()).run_cases(cases)

    assert [result.household_id for result in results] == ["ecps-77", "ecps-99"]
    assert results[0].values["value.snap"] == 536.0
    assert results[1].values["value.snap"] == pytest_approx(5851.0 / 12)


def pytest_approx(value):
    import pytest

    return pytest.approx(value)


def test_prd_projection_builds_emulator_household_from_thin_case() -> None:
    import pytest

    pytest.importorskip("policyengine_prd.core.household")
    from axiom_oracles.adapters.prd import attach_prd_inputs
    from axiom_oracles.core.case import Entity

    case = Case(
        case_id="ecps-1",
        period="2026-01",
        metadata={"state_fips": "01"},
        entities=(
            Entity(
                entity_id="p1",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 30,
                    Concepts.YEARLY_EARNED_INCOME: 20000,
                    Concepts.HOUSEHOLD_RELATION: "head",
                },
            ),
            Entity(
                entity_id="p2",
                kind="person",
                facts={Concepts.PERSON_AGE: 4},
            ),
        ),
    )

    (prepared,) = attach_prd_inputs([case])
    spec = prepared.metadata["prd_household"]
    # The projected spec is a plain JSON-serializable mapping (comparison
    # reports serialize case metadata); the runner builds the emulator
    # object from it lazily.
    import json

    json.dumps(spec)
    assert spec["state_fips"] == 1
    assert spec["year"] == 2026
    assert [m["age"] for m in spec["members"]] == [30, 4]
    assert spec["is_married"] is False

    from axiom_oracles.adapters.prd.projection import build_emulator_household

    household = build_emulator_household(spec)
    assert household.state_fips == 1
    assert household.ages == [30, 4]
    assert household.total_earned_income == 20000
