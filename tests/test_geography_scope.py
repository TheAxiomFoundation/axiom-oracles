import pytest

from axiom_programs.core.geography import (
    GeographyScope,
    pe_inputs_for_scope,
    scope_contains,
    scope_intersection,
)


def test_country_scope_contains_census_place() -> None:
    assert scope_contains(
        GeographyScope(type="country", geoid="US"),
        GeographyScope(type="census_place", geoid="3651000"),
    )


def test_census_place_geoid_projects_to_policyengine_inputs() -> None:
    assert pe_inputs_for_scope(
        GeographyScope(type="census_place", geoid="3651000")
    ) == {
        "state_fips": 36,
        "place_fips": "51000",
    }


def test_census_county_geoid_projects_to_policyengine_inputs() -> None:
    assert pe_inputs_for_scope(
        GeographyScope(type="census_county", geoid="36061")
    ) == {
        "state_fips": 36,
        "county_fips": "36061",
    }


def test_puma_scope_requires_vintage() -> None:
    with pytest.raises(ValueError, match="vintage"):
        GeographyScope(type="puma", geoid="3603201")


def test_census_place_and_county_do_not_intersect_without_crosswalk() -> None:
    assert (
        scope_intersection(
            GeographyScope(type="census_place", geoid="3651000"),
            GeographyScope(type="census_county", geoid="36061"),
        )
        is None
    )
