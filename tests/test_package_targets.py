from axiom_oracles.adapters.prd import PrdPackageRunner
from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner
from axiom_oracles.cli import (
    _build_runner,
    _load_population_cases,
    _prepare_cases_for_engines,
    _resolve_period,
)
from axiom_oracles.comparison.mappings import (
    comparable_mappings,
    comparison_scope_for_targets,
)
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.geography import GeographyScope


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
    policyengine_for_taxsim = _build_runner(
        "policyengine",
        "api",
        None,
        None,
        (),
        paired_engine="taxsim",
    )

    assert isinstance(taxsim, TaxsimPackageRunner)
    assert isinstance(prd, PrdPackageRunner)
    assert isinstance(policyengine_for_taxsim, PolicyEngineTaxsimRunner)


def test_cli_prepares_taxsim_cases_only_when_taxsim_is_compared() -> None:
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
                },
            ),
        ),
    )

    [taxsim_case] = _prepare_cases_for_engines([case], {"policyengine", "taxsim"})
    [pe_case] = _prepare_cases_for_engines([case], {"policyengine", "prd"})

    assert taxsim_case.metadata["taxsim_input"]["taxsimid"] == 1
    assert taxsim_case.metadata["taxsim_input"]["state"] == 33
    assert "taxsim_input" not in pe_case.metadata


def test_cli_prepares_axiom_tax_inputs_for_generated_tax_program() -> None:
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

    [projected] = _prepare_cases_for_engines(
        [case],
        {"policyengine", "axiom"},
        (Concepts.FEDERAL_INCOME_TAX,),
        axiom_program=None,
    )
    [explicit] = _prepare_cases_for_engines(
        [case],
        {"policyengine", "axiom"},
        (Concepts.FEDERAL_INCOME_TAX,),
        axiom_program=__file__,
    )

    assert projected.metadata["axiom_input_records"]
    assert "axiom_input_records" not in explicit.metadata


def test_cli_defaults_taxsim_comparisons_to_supported_tax_year() -> None:
    assert _resolve_period(None, "policyengine", "taxsim") == "2024"
    assert _resolve_period(None, "accessnyc", "policyengine") == "2026-05"
    assert _resolve_period("2023", "policyengine", "taxsim") == "2023"


def test_synthetic_population_honors_requested_period_and_sample_size() -> None:
    cases = _load_population_cases(
        population="synthetic",
        suite_name="nyc-synthetic",
        scope=GeographyScope(type="country", geoid="US"),
        period="2024",
        sample_size=3,
        ecps_dataset=None,
    )

    assert len(cases) == 3
    assert {case.period for case in cases} == {"2024"}
