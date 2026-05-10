from axiom_programs.adapters.prd import PrdPackageRunner
from axiom_programs.adapters.taxsim import TaxsimPackageRunner
from axiom_programs.cli import _build_runner, _prepare_cases_for_engines
from axiom_programs.comparison.mappings import (
    comparable_mappings,
    comparison_scope_for_targets,
)
from axiom_programs.core.case import Case, Concepts, Entity
from axiom_programs.core.geography import GeographyScope


def test_unknown_engines_do_not_get_implicit_concept_targets() -> None:
    concept_ids = {
        mapping.concept_id
        for mapping in comparable_mappings("taxsim", "policyengine")
    }

    assert "us:statutes/7/2014/o#snap_eligible" not in concept_ids
    assert "us:tax/federal-income-tax#liability" in concept_ids
    assert "us:tax/state-income-tax#liability" in concept_ids


def test_package_targets_have_us_scope_and_intersect_with_accessnyc() -> None:
    assert comparison_scope_for_targets("policyengine", "taxsim") == GeographyScope(
        type="country",
        geoid="US",
    )
    assert comparison_scope_for_targets("accessnyc", "taxsim") == GeographyScope(
        type="census_place",
        geoid="3651000",
    )
    assert comparison_scope_for_targets("policyengine", "prd") == GeographyScope(
        type="country",
        geoid="US",
    )


def test_prd_defaults_to_mapped_policyengine_intersection() -> None:
    concept_ids = {
        mapping.concept_id
        for mapping in comparable_mappings("prd", "policyengine")
    }

    assert concept_ids == {"us:statutes/7/2014/u#snap_benefit"}


def test_cli_builds_package_target_runners() -> None:
    taxsim = _build_runner("taxsim", "api", None, None, ())
    prd = _build_runner("prd", "api", None, None, ())

    assert isinstance(taxsim, TaxsimPackageRunner)
    assert isinstance(prd, PrdPackageRunner)


def test_cli_prepares_taxsim_cases_only_when_taxsim_is_compared() -> None:
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
                },
            ),
        ),
    )

    [taxsim_case] = _prepare_cases_for_engines([case], {"policyengine", "taxsim"})
    [pe_case] = _prepare_cases_for_engines([case], {"policyengine", "prd"})

    assert taxsim_case.metadata["taxsim_input"]["taxsimid"] == 1
    assert taxsim_case.metadata["taxsim_input"]["state"] == 36
    assert "taxsim_input" not in pe_case.metadata
