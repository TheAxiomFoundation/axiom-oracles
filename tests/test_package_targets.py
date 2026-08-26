from axiom_oracles.adapters.prd import PrdPackageRunner
from axiom_oracles.adapters.axiom import AxiomRulesRunner
from axiom_oracles.adapters.axiom.runner import _input_record_names
from axiom_oracles.adapters.euromod import EuromodPlatformRunner
from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner
from axiom_oracles.cli import (
    _apply_euromod_to_axiom_input_bridge,
    _attach_axiom_outputs,
    _build_runner,
    _euromod_to_axiom_bridge_outputs,
    _load_population_cases,
    _prepare_cases_for_engines,
    _run_comparison_batch,
    _resolve_period,
)
from axiom_oracles.comparison.mappings import (
    comparable_mappings,
    comparison_scope_for_targets,
    mappings_by_concept,
)
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.core.results import EngineResult
from axiom_oracles.suites import load_suite


def test_unknown_engines_do_not_get_implicit_concept_targets() -> None:
    concept_ids = {
        mapping.concept_id for mapping in comparable_mappings("taxsim", "policyengine")
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
        mapping.concept_id for mapping in comparable_mappings("prd", "policyengine")
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


def test_cli_builds_euromod_runner_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("EUROMOD_MODEL_ROOT", "/tmp/euromod")
    monkeypatch.setenv("EUROMOD_COUNTRY", "BE")
    monkeypatch.setenv("EUROMOD_SYSTEM", "BE_2025")
    monkeypatch.setenv("EUROMOD_DATASET", "BE_2024_c1_2015_03_e2")
    monkeypatch.setenv("EUROMOD_TEMPLATE_DATASET", "BE_training_data")
    monkeypatch.setenv("EUROMOD_EXTRA_COLUMNS", "drgn1,bhl,drgn1")
    monkeypatch.setenv("EUROMOD_SWITCHES", "Belmod_endo=on,BTA=off")
    monkeypatch.setenv("EUROMOD_POLICY_SWITCHES", "bsaoa_be=on,bun_be=off")

    runner = _build_runner("euromod", "api", None, None, ())

    assert isinstance(runner, EuromodPlatformRunner)
    assert runner.model_root.as_posix() == "/tmp/euromod"
    assert runner.country == "BE"
    assert runner.system == "BE_2025"
    assert runner.dataset == "BE_2024_c1_2015_03_e2"
    assert runner.template_dataset == "BE_training_data"
    assert runner.extra_columns == ("drgn1", "bhl")
    assert runner.switches == (("Belmod_endo", True), ("BTA", False))
    assert runner.policy_switch_overrides == (("bsaoa_be", True), ("bun_be", False))


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
    assert _resolve_period(None, "policyengine", "taxsim") == "2026"
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


def test_euromod_bridge_overwrites_declared_axiom_inputs() -> None:
    [case] = load_suite("be-worker-ssc")[:1]
    contribution_input = (
        "be:regulations/social_security/workers/employee_contributions#input."
        "belgium_employee_social_security_contribution_base"
    )
    reference_input = (
        "be:regulations/social_security/workers/work_bonus#input."
        "belgium_worker_work_bonus_supplied_reference_annual_remuneration"
    )

    assert _euromod_to_axiom_bridge_outputs([case]) == ["yem", "yemeq_s"]

    [bridged] = _apply_euromod_to_axiom_input_bridge(
        [case],
        [
            EngineResult(
                "euromod",
                case.case_id,
                {"yem": 31_651.0, "yemeq_s": 27_100.0},
            )
        ],
    )

    assert bridged.metadata["axiom_inputs"][contribution_input] == 31_651.0
    assert bridged.metadata["axiom_inputs"][reference_input] == 27_100.0
    assert bridged.metadata["euromod_to_axiom_input_bridge_applied"] == {
        contribution_input: 31_651.0,
        reference_input: 27_100.0,
    }


def test_euromod_bridge_overwrites_employer_ssc_base() -> None:
    [case] = load_suite("be-employer-ssc")[:1]
    contribution_input = (
        "be:regulations/social_security/workers/employer_contributions#input."
        "belgium_employer_social_security_contribution_base"
    )

    assert _euromod_to_axiom_bridge_outputs([case]) == ["yem"]

    [bridged] = _apply_euromod_to_axiom_input_bridge(
        [case],
        [
            EngineResult(
                "euromod",
                case.case_id,
                {"yem": 31_651.0},
            )
        ],
    )

    assert bridged.metadata["axiom_inputs"][contribution_input] == 31_651.0
    assert bridged.metadata["euromod_to_axiom_input_bridge_applied"] == {
        contribution_input: 31_651.0,
    }


def test_euromod_bridge_targets_one_entity_input_record() -> None:
    income_input = "dk:statutes/example#input.own_income"
    case = Case(
        case_id="dk-couple",
        period="2025",
        metadata={
            "axiom_input_records": [
                {
                    "name": income_input,
                    "entity": "Person",
                    "entity_id": entity_id,
                    "value": 0,
                }
                for entity_id in ("earner", "non-earner")
            ],
            "euromod_to_axiom_input_bridge": {
                "tintbto_s": {
                    "records": [
                        {
                            "name": income_input,
                            "entity": "Person",
                            "entity_id": "earner",
                        }
                    ]
                }
            },
        },
    )

    [bridged] = _apply_euromod_to_axiom_input_bridge(
        [case],
        [EngineResult("euromod", case.case_id, {"tintbto_s": 1_380_000.0})],
    )

    values_by_entity = {
        record["entity_id"]: record["value"]
        for record in bridged.metadata["axiom_input_records"]
    }
    assert values_by_entity == {"earner": 1_380_000.0, "non-earner": 0}
    assert bridged.metadata["euromod_to_axiom_input_bridge_applied"] == {
        f"Person[earner]::{income_input}": 1_380_000.0
    }


def test_euromod_bridge_targets_one_input_record_interval() -> None:
    income_input = "dk:statutes/example#input.own_income"
    interval_2025 = {"start": "2025-01-01", "end": "2025-12-31"}
    interval_2026 = {"start": "2026-01-01", "end": "2026-12-31"}
    case = Case(
        case_id="dk-couple-interval",
        period="2025",
        metadata={
            "axiom_input_records": [
                {
                    "name": income_input,
                    "entity": "Person",
                    "entity_id": "earner",
                    "interval": interval,
                    "value": 0,
                }
                for interval in (interval_2025, interval_2026)
            ],
            "euromod_to_axiom_input_bridge": {
                "tintbto_s": {
                    "records": [
                        {
                            "name": income_input,
                            "entity": "Person",
                            "entity_id": "earner",
                            "interval": interval_2025,
                        }
                    ]
                }
            },
        },
    )

    [bridged] = _apply_euromod_to_axiom_input_bridge(
        [case],
        [EngineResult("euromod", case.case_id, {"tintbto_s": 1_380_000.0})],
    )

    assert [
        (record["interval"], record["value"])
        for record in bridged.metadata["axiom_input_records"]
    ] == [(interval_2025, 1_380_000.0), (interval_2026, 0)]


def test_attach_axiom_outputs_preserves_per_entity_intermediates() -> None:
    [case] = load_suite("dk-child-youth-benefit-couple")
    concept = Concepts.DK_COUPLE_CHILD_YOUTH_BENEFIT
    result = EngineResult(
        "axiom",
        case.case_id,
        {concept: 8_384},
        raw={
            "aggregation": {
                "strategy": "sum",
                "components": [
                    {
                        "entity_id": "earner",
                        "values": {concept: 0, "own_reduction": 9_260},
                    },
                    {
                        "entity_id": "non_earner",
                        "values": {concept: 8_384, "own_reduction": 0},
                    },
                ],
            }
        },
    )

    [attached] = _attach_axiom_outputs([case], [result], (concept,))

    components = attached.metadata["axiom_result_aggregation_applied"]["components"]
    assert components == result.raw["aggregation"]["components"]


def test_uk_worker_pit_suite_shape() -> None:
    cases = load_suite("uk-worker-pit")
    assert [case.case_id for case in cases] == [
        "uk-worker-pit-30k",
        "uk-worker-pit-45k",
        "uk-worker-pit-60k",
        "uk-worker-pit-130k",
        "uk-worker-pit-360k",
    ]
    # The 2026-27 UK tax year, keyed to its 6 April fiscal start so the engine
    # reads the fiscal-year parameter vintage (it selects versions by
    # period.start) rather than the value live the previous 1 January.
    assert {case.period for case in cases} == {"2026-04-06"}
    for case in cases:
        assert case.locale == "UK"
        assert case.scope == GeographyScope(type="country", geoid="UK")
        assert case.outputs == (Concepts.UK_WORKER_INCOME_TAX_LIABILITY,)
    income_input = (
        "uk:statutes/income_tax/individual/pilot_worker_oracle_pipeline#input."
        "uk_pit_pilot_annual_employment_income"
    )
    assert cases[0].metadata["axiom_inputs"][income_input] == 30_000.0


def test_uk_worker_nic_suite_shape() -> None:
    cases = load_suite("uk-worker-nic")
    assert [case.case_id for case in cases] == [
        "uk-worker-nic-30k",
        "uk-worker-nic-45k",
        "uk-worker-nic-60k",
        "uk-worker-nic-130k",
        "uk-worker-nic-360k",
    ]
    assert {case.period for case in cases} == {"2026-04-06"}
    for case in cases:
        assert case.outputs == (Concepts.UK_WORKER_CLASS_1_EMPLOYEE_NIC,)


def test_uk_worker_pit_bridge_overwrites_gross_income_input() -> None:
    [case] = load_suite("uk-worker-pit")[:1]
    income_input = (
        "uk:statutes/income_tax/individual/pilot_worker_oracle_pipeline#input."
        "uk_pit_pilot_annual_employment_income"
    )

    assert _euromod_to_axiom_bridge_outputs([case]) == ["yem"]

    [bridged] = _apply_euromod_to_axiom_input_bridge(
        [case],
        [EngineResult("euromod", case.case_id, {"yem": 30_990.0})],
    )

    assert bridged.metadata["axiom_inputs"][income_input] == 30_990.0
    assert bridged.metadata["euromod_to_axiom_input_bridge_applied"] == {
        income_input: 30_990.0,
    }


def test_uk_worker_concept_mappings_pair_axiom_and_euromod() -> None:
    by_concept = mappings_by_concept()
    pit = by_concept[Concepts.UK_WORKER_INCOME_TAX_LIABILITY]
    assert pit.target_for_engine("axiom") == "uk_pit_pilot_income_tax_liability"
    assert pit.target_for_engine("euromod") == "tin_s"
    assert "UK" in pit.locales
    nic = by_concept[Concepts.UK_WORKER_CLASS_1_EMPLOYEE_NIC]
    assert nic.target_for_engine("axiom") == "uk_nic_pilot_primary_class_1_contribution"
    assert nic.target_for_engine("euromod") == "tscee_s"
    assert "UK" in nic.locales


def test_axiom_runner_aliases_qualified_input_refs_to_bare_slots() -> None:
    assert _input_record_names(
        "be:regulations/social_security/workers/employer_contributions"
        "#input.belgium_employer_social_security_contribution_base",
        alias_qualified=True,
    ) == (
        "be:regulations/social_security/workers/employer_contributions"
        "#input.belgium_employer_social_security_contribution_base",
        "belgium_employer_social_security_contribution_base",
    )


def test_euromod_bridge_runs_euromod_before_axiom() -> None:
    [case] = load_suite("be-worker-ssc")[:1]
    calls = []

    class FakeEuromodRunner:
        def run_cases(self, cases, variables=None):
            calls.append(("euromod", variables))
            return [
                EngineResult(
                    "euromod",
                    cases[0].case_id,
                    {"tscee_net_s": 4_136.74, "yem": 31_651.0, "yemeq_s": 27_100.0},
                )
            ]

    class FakeAxiomRunner:
        def run_cases(self, cases, variables=None):
            calls.append(("axiom", cases[0].metadata["axiom_inputs"], variables))
            return [
                EngineResult(
                    "axiom",
                    cases[0].case_id,
                    {
                        "belgium_employee_social_security_ordinary_worker_contribution": 4_136.74
                    },
                )
            ]

    bridged_cases, left_results, right_results = _run_comparison_batch(
        [case],
        left="axiom",
        right="euromod",
        left_runner=FakeAxiomRunner(),
        right_runner=FakeEuromodRunner(),
        concept_ids=(Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,),
    )

    assert calls[0] == (
        "euromod",
        [Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS, "yem", "yemeq_s"],
    )
    assert calls[1][0] == "axiom"
    assert list(calls[1][1].values())[0] == 31_651.0
    assert bridged_cases[0].metadata["euromod_to_axiom_input_bridge_applied"]
    assert left_results[0].values
    assert right_results[0].values


def test_tax_only_enhanced_cps_comparisons_use_tax_unit_cases() -> None:
    from axiom_oracles.cli import _populace_us_case_unit

    assert _populace_us_case_unit(("tax",), ()) == "tax_unit"
    assert _populace_us_case_unit((), ("us:tax/federal-income-tax#liability",)) == (
        "tax_unit"
    )
    assert _populace_us_case_unit(("tax", "food"), ()) == "household"
