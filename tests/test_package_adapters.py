from axiom_programs.adapters.prd import PrdPackageRunner
from axiom_programs.adapters.taxsim import TaxsimPackageRunner
from axiom_programs.core.case import Case, Concepts, Entity


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
        period="2026",
        metadata={
            "taxsim_input": {
                "year": 2026,
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
    assert captured_inputs[0].iloc[0]["year"] == 2026
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
            return [{"taxsimid": 1, "fiitax": 100, "siitax": 25, "unused": 1}]

    case = Case(
        case_id="case-1",
        period="2026",
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
    assert input_row["state"] == 36
    assert results[0].household_id == "case-1"
    assert results[0].values == {"fiitax": 100, "siitax": 25}


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
