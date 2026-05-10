from axiom_programs.core.case import Concepts
from axiom_programs.core.geography import GeographyScope
from axiom_programs.populations.enhanced_cps import (
    NYC_ENHANCED_CPS_DATASET,
    EnhancedCpsCaseLoader,
    _scope_from_geography,
    dataset_for_scope,
    load_enhanced_cps_cases,
)


def test_nyc_scope_uses_nyc_enhanced_cps_dataset() -> None:
    assert (
        dataset_for_scope(GeographyScope(type="census_place", geoid="3651000"))
        == NYC_ENHANCED_CPS_DATASET
    )


def test_loader_projects_sampled_ecps_households_to_cases() -> None:
    sims = []

    def factory(dataset):
        sim = FakeMicrosimulation(dataset)
        sims.append(sim)
        return sim

    cases = load_enhanced_cps_cases(
        scope=GeographyScope(type="census_place", geoid="3651000"),
        period="2026-05",
        sample_size=2,
        microsimulation_factory=factory,
    )

    assert sims[0].dataset == NYC_ENHANCED_CPS_DATASET
    assert sims[0].subsample_size == 2
    assert [case.case_id for case in cases] == ["ecps-101", "ecps-202"]
    assert cases[0].metadata["population"] == "enhanced-cps"
    assert cases[0].metadata["household_weight"] == 12.5
    assert cases[0].scope == GeographyScope(type="census_place", geoid="3651000")
    assert cases[0].entities[0].facts[Concepts.HOUSEHOLD_RELATION] == (
        "HeadOfHousehold"
    )
    assert cases[0].entities[1].facts[Concepts.HOUSEHOLD_RELATION] == "Child"
    assert cases[0].entities[0].facts[Concepts.YEARLY_EARNED_INCOME] == 20_000
    assert cases[0].entities[0].facts[Concepts.BENEFITS_MEDICAID] is True


def test_loader_skips_geographically_unresolvable_records() -> None:
    loader = EnhancedCpsCaseLoader(
        dataset="memory://fake",
        microsimulation_factory=lambda dataset: FakeMicrosimulation(
            dataset,
            place_fips=[b"", b"51000"],
        ),
    )

    cases = loader.load_cases(
        scope=GeographyScope(type="census_place", geoid="3651000"),
        period="2026",
    )

    assert [case.case_id for case in cases] == ["ecps-202"]


def test_scope_from_geography_combines_state_and_county_components() -> None:
    assert _scope_from_geography(29, 135, "") == GeographyScope(
        type="census_county",
        geoid="29135",
    )
    assert _scope_from_geography(36, 36061, "") == GeographyScope(
        type="census_county",
        geoid="36061",
    )
    assert _scope_from_geography(21, 0, "") == GeographyScope(
        type="census_state",
        geoid="21",
    )
    assert _scope_from_geography(float("nan"), 0, "") is None


class FakeSeries:
    def __init__(self, values):
        self.values = values


class FakeMicrosimulation:
    def __init__(self, dataset, *, place_fips=None):
        self.dataset = dataset
        self.subsample_size = None
        self.household_data = {
            "household_id": [101, 202],
            "household_weight": [12.5, 34.0],
            "state_fips": [36, 36],
            "county_fips": ["36061", "36047"],
            "place_fips": place_fips or [b"51000", b"51000"],
        }
        self.person_data = {
            "household_id": [101, 101, 202],
            "person_id": [1, 2, 3],
            "age": [30, 5, 67],
            "employment_income": [20_000, 0, 10_000],
            "is_pregnant": [False, False, False],
            "is_disabled": [False, False, True],
            "is_blind": [False, False, False],
            "is_veteran": [False, False, True],
            "has_medicaid_health_coverage_at_interview": [True, False, False],
        }

    def subsample(self, sample_size):
        self.subsample_size = sample_size

    def calculate(self, variable, period, map_to=None):
        del period
        data = self.person_data if map_to == "person" else self.household_data
        if variable not in data:
            raise ValueError(variable)
        return FakeSeries(data[variable])
