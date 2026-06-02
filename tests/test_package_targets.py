from axiom_oracles.adapters.prd import PrdPackageRunner
from axiom_oracles.adapters.axiom import AxiomRulesRunner
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


def test_cli_passes_axiom_batch_size_to_runner() -> None:
    runner = _build_runner(
        "axiom",
        "api",
        None,
        None,
        (Concepts.FEDERAL_INCOME_TAX,),
        axiom_batch_size=123,
        paired_engine="policyengine",
    )

    assert isinstance(runner, AxiomRulesRunner)
    assert runner.batch_size == 123


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
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
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
    assert projected.metadata["axiom_input_record_overlays"]
    assert projected.metadata["axiom_result_selection"] == {
        "strategy": "min",
        "output": "us:statutes/26/6401#income_tax",
    }
    assert "axiom_tax_unit_inputs" not in projected.metadata
    assert "axiom_input_records" not in explicit.metadata
    assert "axiom_input_record_overlays" not in explicit.metadata


def test_cli_prepares_axiom_tax_inputs_for_state_income_tax() -> None:
    co_case = Case(
        case_id="state-tax",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
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
    ny_case = Case(
        case_id="ny-state-tax",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "36"}},
        entities=co_case.entities,
    )

    [projected] = _prepare_cases_for_engines(
        [co_case, ny_case],
        {"policyengine", "axiom"},
        (Concepts.STATE_INCOME_TAX,),
        axiom_program=None,
    )

    assert projected.case_id == "state-tax"
    assert projected.metadata["axiom_input_records"]
    assert projected.metadata["axiom_input_record_overlays"]
    assert projected.metadata["axiom_result_selection"] == {
        "strategy": "min",
        "output": "us:tax/oracle-bridge#state_income_tax",
    }


def test_cli_filters_state_tax_dependent_federal_tax_to_encoded_state() -> None:
    co_case = Case(
        case_id="co-federal-tax",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
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
    ca_case = Case(
        case_id="ca-federal-tax",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "06"}},
        entities=co_case.entities,
    )

    prepared = _prepare_cases_for_engines(
        [co_case, ca_case],
        {"policyengine", "axiom"},
        (Concepts.FEDERAL_INCOME_TAX,),
        axiom_program=None,
    )

    assert [case.case_id for case in prepared] == ["co-federal-tax"]


def test_cli_keeps_scope_free_federal_components_national() -> None:
    co_case = Case(
        case_id="co-standard-deduction",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
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
    ca_case = Case(
        case_id="ca-standard-deduction",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "06"}},
        entities=co_case.entities,
    )

    prepared = _prepare_cases_for_engines(
        [co_case, ca_case],
        {"policyengine", "axiom"},
        (Concepts.STANDARD_DEDUCTION,),
        axiom_program=None,
    )

    assert [case.case_id for case in prepared] == [
        "co-standard-deduction",
        "ca-standard-deduction",
    ]


def test_cli_skips_itemization_overlays_for_scope_free_federal_components() -> None:
    case = Case(
        case_id="standard-deduction",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "06"}},
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

    [prepared] = _prepare_cases_for_engines(
        [case],
        {"policyengine", "axiom"},
        (Concepts.STANDARD_DEDUCTION,),
        axiom_program=None,
    )

    assert prepared.metadata["axiom_input_records"]
    assert "axiom_input_record_overlays" not in prepared.metadata


def test_cli_preparation_does_not_use_oracles_as_input_providers(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs) -> None:
        raise AssertionError("oracle runner was used during input preparation")

    monkeypatch.setattr(
        "axiom_oracles.adapters.policyengine.runner.PolicyEngineRunner.run_cases",
        fail_if_called,
    )
    monkeypatch.setattr(
        "axiom_oracles.adapters.taxsim.runner.TaxsimPackageRunner.run_cases",
        fail_if_called,
    )
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

    [projected] = _prepare_cases_for_engines(
        [case],
        {"axiom", "policyengine", "taxsim"},
        (Concepts.STANDARD_DEDUCTION,),
        axiom_program=None,
    )

    assert projected.metadata["taxsim_input"]["state"] == 33
    assert projected.metadata["axiom_input_records"]
    assert "axiom_input_record_overlays" not in projected.metadata
    assert "axiom_tax_unit_inputs" not in projected.metadata


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


def test_tax_only_enhanced_cps_comparisons_use_tax_unit_cases() -> None:
    from axiom_oracles.cli import _enhanced_cps_case_unit

    assert _enhanced_cps_case_unit(("tax",), ()) == "tax_unit"
    assert _enhanced_cps_case_unit((), ("us:tax/federal-income-tax#liability",)) == (
        "tax_unit"
    )
    assert _enhanced_cps_case_unit(("tax", "food"), ()) == "household"
