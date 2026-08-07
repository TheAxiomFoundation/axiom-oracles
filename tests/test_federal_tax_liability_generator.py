"""Focused invariants for the independent federal tax case grids."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[1]


def _load_generator():
    path = REPO_ROOT / "scripts" / "generate_federal_tax_liability.py"
    spec = importlib.util.spec_from_file_location(
        "federal_tax_liability_generator",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_runner():
    path = REPO_ROOT / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("federal_grid_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_contract_inputs(generator, validator, case):
    """Return the exact fixture mapping enforced by a config validator."""
    captured = {}
    original = generator._require_exact_fixture_values

    def capture(**kwargs):
        captured.update(kwargs)

    generator._require_exact_fixture_values = capture
    try:
        validator(case, {})
    finally:
        generator._require_exact_fixture_values = original
    return captured["expected"]


def test_every_live_federal_grid_pins_its_reviewed_rulespec_snapshot():
    legacy_snapshot = (
        "3373e8411f7e141fd50879e3de964386f606f7f6",
        "7e00f195ea81ff9aa21c58d53151e937d974a016",
    )
    savers_snapshot = (
        "dcbae4344c522b4ad8004169316266cbc153186f",
        "7ee3ca44edd11cdaaf5d074a6a2a6c32d2f25dfb",
    )
    chunk1_snapshot = (
        "ae64af2740340a40d04ed3c652254f53e62fab61",
        "40e08f7dbaa88a70660006f3a5a32bfa283ebd85",
    )
    chunk1_configs = {
        "us-itemized-taxable-income-deductions-grid.yaml",
        "us-salt-deduction-grid.yaml",
    }
    federal_configs = []
    for path in sorted((REPO_ROOT / "comparisons").glob("*.yaml")):
        config = yaml.safe_load(path.read_text())
        runner = config.get("runner") or {}
        if runner.get("type") != "federal-tax-liability-grid":
            continue
        federal_configs.append(path.name)
        parameters = runner["parameters"]
        if path.name in chunk1_configs:
            expected = chunk1_snapshot
        elif path.name == "us-savers-grid.yaml":
            expected = savers_snapshot
        else:
            expected = legacy_snapshot
        assert (
            parameters["rulespec_upstream_sha"],
            parameters["rulespec_upstream_tree"],
        ) == expected, path

    assert federal_configs == [
        "us-aca-ptc-grid.yaml",
        "us-additional-medicare-grid.yaml",
        "us-elderly-disabled-grid.yaml",
        "us-itemized-taxable-income-deductions-grid.yaml",
        "us-llc-grid.yaml",
        "us-niit-grid.yaml",
        "us-qbid-grid.yaml",
        "us-salt-deduction-grid.yaml",
        "us-savers-grid.yaml",
        "us-seca-grid.yaml",
    ]


def test_all_ten_contract_grids_are_explicit_and_independent():
    generator = _load_generator()

    assert set(generator.POLICIES) == {
        "aca_ptc",
        "additional_medicare_tax",
        "elderly_disabled_credit",
        "itemized_taxable_income_deductions",
        "lifetime_learning_credit",
        "net_investment_income_tax",
        "qualified_business_income_deduction",
        "salt_deduction",
        "savers_credit",
        "self_employment_tax",
    }
    for key, config in generator.POLICIES.items():
        assert config.key == key
        assert len({case.case_id for case in config.cases}) == len(config.cases)
        assert config.tolerance == 0.01
        assert config.relative_tolerance == 0

    expected_case_ids = {
        "additional_medicare_tax": [
            "amt-single-150k",
            "amt-single-250k",
            "amt-joint-300k",
            "amt-mfs-150k",
            "amt-joint-450k",
        ],
        "self_employment_tax": [
            "seca-under-floor",
            "seca-50k",
            "seca-120k",
            "seca-300k",
            "seca-wage-mix",
            "seca-joint-200k",
        ],
        "net_investment_income_tax": [
            "niit-under",
            "niit-single-mixed",
            "niit-joint-gains",
            "niit-mfs",
            "niit-inv-only",
            "niit-rental",
        ],
        "aca_ptc": [
            "ptc-150fpl-family4",
            "ptc-250fpl-single",
            "ptc-300fpl-joint",
            "ptc-380fpl-single",
            "ptc-410fpl-single",
            "ptc-95fpl-single",
        ],
        "qualified_business_income_deduction": [
            "qbid-ti-limited",
            "qbid-basic-100k",
            "qbid-joint-150k",
            "qbid-phasein",
            "qbid-above-nowages",
            "qbid-reit-only",
            "qbid-zero",
            "qbid-single-at-threshold",
            "qbid-single-one-dollar-over-threshold",
            "qbid-active-minimum",
            "qbid-net-capital-gain-limit",
        ],
        "savers_credit": [
            "single-one-below-50-percent-limit",
            "single-at-50-percent-limit-inclusive",
            "single-one-over-50-percent-limit",
            "single-one-below-20-percent-limit",
            "single-at-20-percent-limit-inclusive",
            "single-one-over-20-percent-limit",
            "single-one-below-10-percent-limit",
            "single-at-10-percent-limit-inclusive",
            "single-one-over-10-percent-limit",
            "joint-one-below-50-percent-limit",
            "joint-at-50-percent-limit-inclusive",
            "joint-one-over-50-percent-limit",
            "joint-one-below-20-percent-limit",
            "joint-at-20-percent-limit-inclusive",
            "joint-one-over-20-percent-limit",
            "joint-one-below-10-percent-limit",
            "joint-at-10-percent-limit-inclusive",
            "joint-one-over-10-percent-limit",
            "head-of-household-one-below-50-percent-limit",
            "head-of-household-at-50-percent-limit-inclusive",
            "head-of-household-one-over-50-percent-limit",
            "head-of-household-one-below-20-percent-limit",
            "head-of-household-at-20-percent-limit-inclusive",
            "head-of-household-one-over-20-percent-limit",
            "head-of-household-one-below-10-percent-limit",
            "head-of-household-at-10-percent-limit-inclusive",
            "head-of-household-one-over-10-percent-limit",
            "married-filing-separately-uses-all-other-limits",
            "surviving-spouse-uses-all-other-limits",
            "section-911-add-back-crosses-inclusive-limit",
            "joint-separate-cap-for-each-spouse",
            "age-screen",
            "student-screen",
            "dependent-screen",
        ],
        "elderly_disabled_credit": [
            "eld-basic",
            "eld-agi-reduce",
            "eld-joint-both",
            "eld-zero-high-agi",
            "eld-ss-wipes",
            "eld-joint-one-65",
            "eld-disabled-under-65",
            "eld-at-agi-threshold",
            "eld-two-dollars-over-agi-threshold",
        ],
        "lifetime_learning_credit": [
            "llc-basic",
            "llc-cap",
            "llc-phaseout-mid",
            "llc-over",
            "llc-joint-mid",
            "llc-small",
            "llc-zero-expenses",
            "llc-at-phaseout-start",
            "llc-one-dollar-over-phaseout-start",
            "llc-at-phaseout-end",
            "llc-aggregate-cap",
            "llc-liability-cap-diagnostic",
        ],
        "salt_deduction": [
            "salt-single-base",
            "salt-single-at-cap",
            "salt-single-over-cap",
            "salt-joint-cap",
            "salt-hoh-cap",
            "salt-surviving-cap",
            "salt-mfs-cap",
            "salt-single-phaseout-start",
            "salt-single-phaseout-plus-one",
            "salt-single-phaseout-mid",
            "salt-single-floor",
            "salt-mfs-phaseout-mid",
            "salt-mfs-floor",
            "salt-low-agi-engine-cap",
            "salt-magi-911-addback",
            "salt-personal-property-tax-probe",
        ],
        "itemized_taxable_income_deductions": [
            "itemized-zero",
            "itemized-charity-only",
            "itemized-interest-only",
            "itemized-salt-only",
            "itemized-medical-only",
            "itemized-casualty-completed",
            "itemized-mixed",
            "itemized-68-single-at",
            "itemized-68-single-plus-one",
            "itemized-68-single-income-lesser",
            "itemized-68-single-deduction-lesser",
            "itemized-68-hoh-at",
            "itemized-68-joint-at",
            "itemized-68-surviving-at",
            "itemized-68-mfs-at",
            "itemized-68-other-deduction-base",
            "itemized-68-rational-rate",
        ],
    }
    for key, expected in expected_case_ids.items():
        assert [case.case_id for case in generator.POLICIES[key].cases] == expected
    additional_medicare = generator.POLICIES["additional_medicare_tax"].cases
    assert all(
        case.inputs["self_employment_income"] == 0 for case in additional_medicare
    )
    assert any(
        case.inputs["primary_wages"] + case.inputs["spouse_wages"] > 200_000
        for case in additional_medicare
    )


def test_policyengine_bindings_match_the_reviewed_output_boundaries():
    generator = _load_generator()

    assert generator.POLICIES["additional_medicare_tax"].pe_output_variables == (
        "additional_medicare_tax",
    )
    assert generator.POLICIES["self_employment_tax"].pe_output_variables == (
        "self_employment_tax",
    )
    assert generator.POLICIES["net_investment_income_tax"].pe_output_variables == (
        "net_investment_income_tax",
    )
    # Raw aca_ptc omits the enrolled-plan premium cap.
    assert generator.POLICIES["aca_ptc"].pe_output_variables == ("used_aca_ptc",)
    assert generator.POLICIES[
        "qualified_business_income_deduction"
    ].pe_output_variables == ("qualified_business_income_deduction",)
    # The public PE variables apply section 26 credit-order/liability caps.
    assert generator.POLICIES["savers_credit"].pe_output_variables == (
        "savers_credit_potential",
    )
    assert generator.POLICIES["elderly_disabled_credit"].pe_output_variables == (
        "elderly_disabled_credit_potential",
    )
    # Both engines expose the LLC final, including its liability cap.
    assert generator.POLICIES["lifetime_learning_credit"].pe_output_variables == (
        "lifetime_learning_credit",
    )
    assert generator.POLICIES["salt_deduction"].pe_output_variables == (
        "salt_deduction",
    )
    assert generator.POLICIES[
        "itemized_taxable_income_deductions"
    ].pe_output_variables == ("itemized_taxable_income_deductions",)


def test_chunk1_configs_bind_only_reviewed_bridge_diagnostics_and_inputs():
    generator = _load_generator()
    salt = generator.POLICIES["salt_deduction"]
    itemized = generator.POLICIES["itemized_taxable_income_deductions"]

    assert salt.axiom_bridge_outputs == {
        (
            "us:policies/income_tax/salt_deduction_pipeline"
            "#federal_section_911_exclusion_for_salt_magi"
        ): "foreign_earned_income_exclusion",
    }
    assert salt.axiom_diagnostic_outputs == {}
    assert salt.rulespec_only_inputs == (
        (
            "us:policies/income_tax/salt_deduction_pipeline"
            "#input.state_and_local_personal_property_tax"
        ),
    )
    assert set(salt.rulespec_domain_inputs) == {
        (
            "us:policies/income_tax/salt_deduction_pipeline#input."
            "completed_personal_tax_amounts_exclude_business_and_section_212_taxes"
        ),
        (
            "us:policies/income_tax/salt_deduction_pipeline#input."
            "completed_personal_tax_amounts_exclude_acquisition_capitalized_taxes"
        ),
        (
            "us:policies/income_tax/salt_deduction_pipeline#input."
            "completed_personal_tax_amounts_are_net_of_refunds"
        ),
        (
            "us:policies/income_tax/salt_deduction_pipeline#input."
            "completed_personal_tax_amounts_exclude_nondeductible_taxes"
        ),
        (
            "us:policies/income_tax/salt_deduction_pipeline#input."
            "section_911_exclusion_relation_includes_every_tax_unit_individual"
        ),
    }
    assert itemized.axiom_bridge_outputs == {}
    assert itemized.axiom_diagnostic_outputs == {
        (
            "us:policies/income_tax/"
            "itemized_taxable_income_deductions_pipeline"
            "#itemized_deductions_otherwise_allowable_after_other_limitations"
        ): "total_itemized_taxable_income_deductions",
        (
            "us:policies/income_tax/"
            "itemized_taxable_income_deductions_pipeline"
            "#federal_section_68_reduction"
        ): "itemized_taxable_income_deductions_reduction",
    }
    assert itemized.rulespec_only_inputs == (
        ("us:statutes/26/68#input.taxable_income_determined_without_section_68"),
    )
    assert set(itemized.rulespec_domain_inputs) == {
        *salt.rulespec_domain_inputs,
        (
            "us:policies/income_tax/"
            "itemized_taxable_income_deductions_pipeline"
            "#input.taxpayer_is_individual"
        ),
        (
            "us:policies/income_tax/"
            "itemized_taxable_income_deductions_pipeline"
            "#input.no_other_component_in_pe_six_item_itemized_aggregate"
        ),
    }
    assert "foreign_earned_income_exclusion" in salt.pe_input_variables
    assert (
        "itemized_taxable_income_deductions_reduction"
        not in itemized.pe_input_variables
    )
    generator._validate_policy_config(salt)
    generator._validate_policy_config(itemized)


@pytest.mark.parametrize(
    ("config_key", "validator_name"),
    [
        ("salt_deduction", "_validate_salt_fixture"),
        (
            "itemized_taxable_income_deductions",
            "_validate_itemized_fixture",
        ),
    ],
)
def test_chunk1_fixture_contract_matches_every_adopted_case_exactly(
    config_key,
    validator_name,
):
    generator = _load_generator()
    config = generator.POLICIES[config_key]
    validator = getattr(generator, validator_name)
    report = json.loads(
        (
            REPO_ROOT
            / "dashboard"
            / "public"
            / "data"
            / f"axiom-policyengine-{config.suite}.json"
        ).read_text()
    )
    report_cases = {case["case_id"]: case for case in report["cases"]}
    assert set(report_cases) == {case.case_id for case in config.cases}

    for case in config.cases:
        exact_inputs = report_cases[case.case_id]["axiom_fixture_inputs"]
        validator(case, exact_inputs)
        generator._validate_rulespec_input_contract(
            config,
            case,
            exact_inputs,
        )
        for key, expected in config.rulespec_domain_inputs.items():
            assert exact_inputs[key] is expected
        for key in config.rulespec_only_inputs:
            assert key in exact_inputs

    if config_key == "salt_deduction":
        personal_property = config.rulespec_only_inputs[0]
        assert {
            case.case_id: report_cases[case.case_id]["axiom_fixture_inputs"][
                personal_property
            ]
            for case in config.cases
            if report_cases[case.case_id]["axiom_fixture_inputs"][personal_property]
        } == {"salt-personal-property-tax-probe": 4_000}
    else:
        section_68_base = config.rulespec_only_inputs[0]
        assert all(
            report_cases[case.case_id]["axiom_fixture_inputs"][section_68_base]
            == case.inputs["taxable_income_determined_without_section_68"]
            for case in config.cases
        )


def test_chunk1_fixture_contract_rejects_missing_and_unexpected_inputs():
    generator = _load_generator()
    salt = generator.POLICIES["salt_deduction"]
    case = salt.cases[0]
    exact_inputs = _fixture_contract_inputs(
        generator,
        generator._validate_salt_fixture,
        case,
    )
    domain_input = next(iter(salt.rulespec_domain_inputs))
    rulespec_only_input = salt.rulespec_only_inputs[0]

    missing_domain = dict(exact_inputs)
    missing_domain.pop(domain_input)
    with pytest.raises(ValueError, match="is missing input"):
        generator._validate_rulespec_input_contract(
            salt,
            case,
            missing_domain,
        )

    wrong_domain = dict(exact_inputs)
    wrong_domain[domain_input] = False
    with pytest.raises(ValueError, match="expected True"):
        generator._validate_rulespec_input_contract(
            salt,
            case,
            wrong_domain,
        )

    missing_rulespec_only = dict(exact_inputs)
    missing_rulespec_only.pop(rulespec_only_input)
    with pytest.raises(ValueError, match="missing RuleSpec-only input"):
        generator._validate_rulespec_input_contract(
            salt,
            case,
            missing_rulespec_only,
        )

    unexpected = {**exact_inputs, "us:test#input.unreviewed": 0}
    with pytest.raises(ValueError, match="unexpected inputs"):
        generator._validate_salt_fixture(case, unexpected)

    itemized = generator.POLICIES["itemized_taxable_income_deductions"]
    itemized_case = itemized.cases[0]
    itemized_inputs = _fixture_contract_inputs(
        generator,
        generator._validate_itemized_fixture,
        itemized_case,
    )
    itemized_inputs.pop(itemized.rulespec_only_inputs[0])
    with pytest.raises(ValueError, match="missing RuleSpec-only input"):
        generator._validate_rulespec_input_contract(
            itemized,
            itemized_case,
            itemized_inputs,
        )


def test_salt_bridge_requires_the_exact_numeric_axiom_output():
    generator = _load_generator()
    config = generator.POLICIES["salt_deduction"]
    case = config.cases[0]
    bridge_output = next(iter(config.axiom_bridge_outputs))

    situation = config.pe_situation(case, {bridge_output: 125.5})
    assert (
        situation["tax_units"]["tax_unit"]["foreign_earned_income_exclusion"][2026]
        == 125.5
    )
    assert (
        situation["people"]["head"]["real_estate_taxes"][2026]
        == (case.inputs["real_estate_taxes"])
    )
    assert "real_estate_taxes" not in situation["tax_units"]["tax_unit"]

    with pytest.raises(ValueError, match="missing=.*federal_section_911"):
        config.pe_situation(case, {})
    with pytest.raises(ValueError, match="unexpected=.*unreviewed"):
        config.pe_situation(
            case,
            {bridge_output: 0, "us:test#unreviewed": 0},
        )
    with pytest.raises(ValueError, match="must be numeric"):
        config.pe_situation(case, {bridge_output: "0"})
    with pytest.raises(ValueError, match="must be numeric"):
        config.pe_situation(case, {bridge_output: False})

    itemized = generator.POLICIES["itemized_taxable_income_deductions"]
    with pytest.raises(ValueError, match="unexpected=.*unreviewed"):
        itemized.pe_situation(
            itemized.cases[0],
            {"us:test#unreviewed": 0},
        )


def test_policy_config_rejects_compared_output_as_bridge_and_pe_overrides():
    generator = _load_generator()
    config = generator.POLICIES["salt_deduction"]
    bridge_output = next(iter(config.axiom_bridge_outputs))
    case = config.cases[0]

    with pytest.raises(
        ValueError,
        match="compared Axiom outputs cannot also be bridge",
    ):
        generator._validate_policy_config(
            replace(
                config,
                axiom_bridge_outputs={
                    config.axiom_output: "foreign_earned_income_exclusion"
                },
            )
        )

    situation = config.pe_situation(case, {bridge_output: 0})
    situation["tax_units"]["tax_unit"]["unreviewed_override"] = {2026: 1}
    with pytest.raises(ValueError, match="undeclared PolicyEngine overrides"):
        generator._validate_pe_situation_inputs(
            config,
            case,
            situation,
        )

    situation = config.pe_situation(case, {bridge_output: 0})
    situation["tax_units"]["tax_unit"].pop("foreign_earned_income_exclusion")
    with pytest.raises(ValueError, match="omits PolicyEngine bridge inputs"):
        generator._validate_pe_situation_inputs(
            config,
            case,
            situation,
        )


def test_chunk1_policyengine_situations_preserve_all_filing_status_enums():
    generator = _load_generator()
    policyengine_us = pytest.importorskip("policyengine_us")
    config = generator.POLICIES["salt_deduction"]
    bridge_output = next(iter(config.axiom_bridge_outputs))
    expected = {
        "single": 0,
        "joint": 1,
        "separate": 2,
        "head_of_household": 3,
        "surviving_spouse": 4,
    }
    observed = {}

    for filing_status, expected_enum in expected.items():
        case = next(
            candidate
            for candidate in config.cases
            if candidate.filing_status == filing_status
        )
        situation = config.pe_situation(case, {bridge_output: 0})
        if filing_status == "head_of_household":
            assert (
                situation["tax_units"]["tax_unit"]["filing_status"][2026]
                == "HEAD_OF_HOUSEHOLD"
            )
        if filing_status == "surviving_spouse":
            assert (
                situation["tax_units"]["tax_unit"]["filing_status"][2026]
                == "SURVIVING_SPOUSE"
            )
        simulation = policyengine_us.Simulation(situation=situation)
        observed[filing_status] = int(simulation.calculate("filing_status", 2026)[0])
        assert observed[filing_status] == expected_enum

    assert observed == expected
    assert set(observed.values()) == {0, 1, 2, 3, 4}


def test_chunk1_policyengine_parameter_validators_assert_exact_2026_values(
    monkeypatch,
):
    generator = _load_generator()
    policyengine_us = pytest.importorskip("policyengine_us")
    salt = generator.POLICIES["salt_deduction"]
    bridge_output = next(iter(salt.axiom_bridge_outputs))
    situation = salt.pe_situation(salt.cases[0], {bridge_output: 0})
    tax_benefit_system = policyengine_us.Simulation(
        situation=situation
    ).tax_benefit_system
    captured = {}
    original = generator._verify_parameter_values

    def capture(label, actual, expected):
        captured[label] = (actual, expected)
        original(label, actual, expected)

    monkeypatch.setattr(generator, "_verify_parameter_values", capture)
    salt.pe_parameter_validator(tax_benefit_system)
    generator.POLICIES[
        "itemized_taxable_income_deductions"
    ].pe_parameter_validator(tax_benefit_system)

    salt_expected = {
        "sources": [
            "state_and_local_sales_or_income_tax",
            "real_estate_taxes",
        ],
        "cap.SINGLE": 40_400,
        "cap.JOINT": 40_400,
        "cap.SEPARATE": 20_200,
        "cap.HEAD_OF_HOUSEHOLD": 40_400,
        "cap.SURVIVING_SPOUSE": 40_400,
        "phase_out.threshold.SINGLE": 505_000,
        "phase_out.threshold.JOINT": 505_000,
        "phase_out.threshold.SEPARATE": 252_500,
        "phase_out.threshold.HEAD_OF_HOUSEHOLD": 505_000,
        "phase_out.threshold.SURVIVING_SPOUSE": 505_000,
        "phase_out.rate": 0.3,
        "phase_out.floor.amount.SINGLE": 10_000,
        "phase_out.floor.amount.JOINT": 10_000,
        "phase_out.floor.amount.SEPARATE": 5_000,
        "phase_out.floor.amount.HEAD_OF_HOUSEHOLD": 10_000,
        "phase_out.floor.amount.SURVIVING_SPOUSE": 10_000,
        "phase_out.in_effect": True,
        "phase_out.floor.applies": True,
        "simulation.limit_itemized_deductions_to_taxable_income": True,
        "simulation.branch_to_determine_itemization": True,
    }
    itemized_expected = {
        "itemized_deductions": [
            "charitable_deduction",
            "interest_deduction",
            "salt_deduction",
            "medical_expense_deduction",
            "casualty_loss_deduction",
            "misc_deduction",
        ],
        "limitation.applies": True,
        "limitation.obbb.applies": True,
        "top_threshold.SINGLE": 640_600,
        "top_threshold.JOINT": 768_700,
        "top_threshold.SEPARATE": 384_350,
        "top_threshold.HEAD_OF_HOUSEHOLD": 640_600,
        "top_threshold.SURVIVING_SPOUSE": 768_700,
        "limitation.obbb.rate": 0.05405405,
    }
    assert captured == {
        "us-salt-deduction-grid": (salt_expected, salt_expected),
        "us-itemized-taxable-income-deductions-grid": (
            itemized_expected,
            itemized_expected,
        ),
    }


def test_policyengine_values_creates_a_fresh_simulation_per_case(monkeypatch):
    generator = _load_generator()
    policyengine_us = pytest.importorskip("policyengine_us")
    original = generator.POLICIES["additional_medicare_tax"]
    config = replace(
        original,
        cases=original.cases[:2],
        pe_output_variables=("test_output",),
        pe_diagnostic_variables=(),
        pe_parameter_validator=None,
        pe_situation=lambda case, bridge_outputs: {
            "case_id": case.case_id,
            "bridge_outputs": dict(bridge_outputs),
        },
    )
    created = []

    class FakeSimulation:
        def __init__(self, *, situation):
            self.situation = situation
            created.append(self)

        def calculate(self, variable, year):
            assert variable == "test_output"
            assert year == 2026
            return [len(created)]

    monkeypatch.setattr(
        generator,
        "distribution_version",
        lambda distribution: generator.ENGINE_VERSIONS[distribution.replace("-", "_")],
    )
    monkeypatch.setattr(policyengine_us, "Simulation", FakeSimulation)
    bridge_values = {case.case_id: {} for case in config.cases}

    totals, components = generator._policyengine_values(
        config,
        bridge_values,
    )

    assert len(created) == len(config.cases)
    assert len({id(simulation) for simulation in created}) == len(config.cases)
    assert [simulation.situation for simulation in created] == [
        {"case_id": case.case_id, "bridge_outputs": {}} for case in config.cases
    ]
    assert totals == {
        config.cases[0].case_id: 1,
        config.cases[1].case_id: 2,
    }
    assert components == {
        config.cases[0].case_id: {"test_output": 1},
        config.cases[1].case_id: {"test_output": 2},
    }


def test_axiom_bridge_and_itemized_diagnostics_are_extracted_and_reported(
    tmp_path,
):
    generator = _load_generator()
    period = {
        "period_kind": "tax_year",
        "start": "2026-01-01",
        "end": "2026-12-31",
    }

    salt = generator.POLICIES["salt_deduction"]
    salt_case = salt.cases[0]
    salt_bridge = next(iter(salt.axiom_bridge_outputs))
    salt_config = replace(
        salt,
        cases=(salt_case,),
        fixture_path=Path("salt.test.yaml"),
    )
    salt_fixture = tmp_path / salt_config.fixture_path
    salt_fixture.write_text(
        yaml.safe_dump(
            [
                {
                    "name": salt_case.case_id,
                    "period": period,
                    "input": _fixture_contract_inputs(
                        generator,
                        generator._validate_salt_fixture,
                        salt_case,
                    ),
                    "output": {
                        salt.axiom_output: 10_000,
                        salt_bridge: 1_250,
                    },
                }
            ],
            sort_keys=False,
        )
    )
    (
        path,
        values,
        fixture_inputs,
        bridge_values,
        diagnostic_values,
    ) = generator._axiom_values(salt_config, [tmp_path])
    assert path == salt_fixture
    assert values == {salt_case.case_id: 10_000}
    assert bridge_values == {salt_case.case_id: {salt_bridge: 1_250.0}}
    assert diagnostic_values == {salt_case.case_id: {}}
    salt_report = generator._build_report(
        salt_config,
        axiom=values,
        fixture_inputs=fixture_inputs,
        policyengine=values,
        policyengine_components={salt_case.case_id: {"salt_deduction": 10_000}},
        axiom_bridge_values=bridge_values,
        axiom_diagnostic_values=diagnostic_values,
    )
    assert salt_report["cases"][0]["axiom_bridge_outputs"] == {salt_bridge: 1_250.0}
    assert salt_report["engine_bindings"]["axiom"]["bridge_outputs"] == {
        salt_bridge: "foreign_earned_income_exclusion"
    }

    itemized = generator.POLICIES["itemized_taxable_income_deductions"]
    itemized_case = next(
        case for case in itemized.cases if case.case_id == "itemized-68-single-at"
    )
    itemized_config = replace(
        itemized,
        cases=(itemized_case,),
        fixture_path=Path("itemized.test.yaml"),
    )
    itemized_outputs = {
        itemized.axiom_output: 50_000,
        **{
            output: 50_000 if "otherwise_allowable" in output else 0
            for output in itemized.axiom_diagnostic_outputs
        },
    }
    itemized_fixture = tmp_path / itemized_config.fixture_path
    itemized_fixture.write_text(
        yaml.safe_dump(
            [
                {
                    "name": itemized_case.case_id,
                    "period": period,
                    "input": _fixture_contract_inputs(
                        generator,
                        generator._validate_itemized_fixture,
                        itemized_case,
                    ),
                    "output": itemized_outputs,
                }
            ],
            sort_keys=False,
        )
    )
    (
        _path,
        itemized_values,
        itemized_inputs,
        itemized_bridges,
        itemized_diagnostics,
    ) = generator._axiom_values(itemized_config, [tmp_path])
    assert itemized_bridges == {itemized_case.case_id: {}}
    assert itemized_diagnostics == {
        itemized_case.case_id: {
            output: float(value)
            for output, value in itemized_outputs.items()
            if output in itemized.axiom_diagnostic_outputs
        }
    }
    itemized_report = generator._build_report(
        itemized_config,
        axiom=itemized_values,
        fixture_inputs=itemized_inputs,
        policyengine=itemized_values,
        policyengine_components={
            itemized_case.case_id: {
                "itemized_taxable_income_deductions": 50_000,
                "total_itemized_taxable_income_deductions": 50_000,
                "itemized_taxable_income_deductions_reduction": 0,
            }
        },
        axiom_bridge_values=itemized_bridges,
        axiom_diagnostic_values=itemized_diagnostics,
    )
    assert (
        itemized_report["cases"][0]["axiom_diagnostics"]
        == (itemized_diagnostics[itemized_case.case_id])
    )
    assert itemized_report["cases"][0]["diagnostic_reconciliation"] == [
        {
            "axiom_output": output,
            "policyengine_variable": pe_variable,
            "axiom": itemized_diagnostics[itemized_case.case_id][output],
            "policyengine": (50_000.0 if pe_variable.startswith("total_") else 0.0),
            "difference": 0.0,
        }
        for output, pe_variable in itemized.axiom_diagnostic_outputs.items()
    ]


def test_axiom_bridge_extraction_rejects_missing_and_nonnumeric_outputs(
    tmp_path,
):
    generator = _load_generator()
    original = generator.POLICIES["salt_deduction"]
    case = original.cases[0]
    bridge_output = next(iter(original.axiom_bridge_outputs))
    config = replace(
        original,
        cases=(case,),
        fixture_path=Path("salt-bridge-invalid.test.yaml"),
    )
    fixture = tmp_path / config.fixture_path
    record = {
        "name": case.case_id,
        "period": {
            "period_kind": "tax_year",
            "start": "2026-01-01",
            "end": "2026-12-31",
        },
        "input": _fixture_contract_inputs(
            generator,
            generator._validate_salt_fixture,
            case,
        ),
        "output": {config.axiom_output: 10_000},
    }
    fixture.write_text(yaml.safe_dump([record], sort_keys=False))
    with pytest.raises(ValueError, match="has no output.*section_911"):
        generator._axiom_values(config, [tmp_path])

    record["output"][bridge_output] = "not-a-number"
    fixture.write_text(yaml.safe_dump([record], sort_keys=False))
    with pytest.raises(ValueError, match="must be numeric"):
        generator._axiom_values(config, [tmp_path])


def test_savers_grid_fails_closed_on_unmapped_noncomparable_or_wrong_target():
    generator = _load_generator()
    savers = generator.POLICIES["savers_credit"]
    module = "us:policies/income_tax/savers_credit_pipeline"
    with pytest.raises(ValueError, match="unmapped"):
        generator._assert_registry_comparable_bindings(
            replace(
                savers,
                comparison_bindings=(
                    generator.ComparisonBinding(
                        concept=f"{module}#invented_unmapped_output",
                        policyengine_target="savers_credit_potential",
                        comparison="amount",
                    ),
                ),
            )
        )
    with pytest.raises(ValueError, match="registry-not-comparable"):
        generator._assert_registry_comparable_bindings(
            replace(
                savers,
                comparison_bindings=(
                    generator.ComparisonBinding(
                        concept=(
                            f"{module}"
                            "#pipeline_savers_credit_modified_adjusted_gross_income"
                        ),
                        policyengine_target="adjusted_gross_income",
                        comparison="amount",
                    ),
                ),
            )
        )
    with pytest.raises(ValueError, match="registry target"):
        generator._assert_registry_comparable_bindings(
            replace(
                savers,
                comparison_bindings=(
                    generator.ComparisonBinding(
                        concept=f"{module}#federal_savers_credit",
                        policyengine_target="savers_credit",
                        comparison="amount",
                    ),
                ),
            )
        )

    generator._assert_registry_comparable_bindings(savers)


def test_committed_registry_audited_reports_score_only_comparable_bindings():
    generator = _load_generator()
    registry = generator.load_policyengine_registry()
    expected = {
        "us-itemized-taxable-income-deductions-grid": {
            (
                "us:policies/income_tax/"
                "itemized_taxable_income_deductions_pipeline"
                "#federal_itemized_taxable_income_deductions"
            )
        },
        "us-salt-deduction-grid": {
            "us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction"
        },
        "us-savers-grid": {
            "us:policies/income_tax/savers_credit_pipeline#federal_savers_credit"
        },
    }
    for suite, expected_concepts in expected.items():
        report = json.loads(
            (
                REPO_ROOT / "dashboard/public/data" / f"axiom-policyengine-{suite}.json"
            ).read_text()
        )
        scored = {
            aggregate["concept"]
            for aggregate in report["aggregates"]
            if aggregate["comparison_count"] > 0
        }
        bindings = report["engine_bindings"]["policyengine"]["comparison_bindings"]
        assert scored == expected_concepts
        assert len(bindings) == len(scored)
        assert {binding["concept"] for binding in bindings} == scored
        assert (
            sum(aggregate["comparison_count"] for aggregate in report["aggregates"])
            == report["summary"]["comparison_count"]
        )
        for binding in bindings:
            mapping = registry.mapping_for_legal_id(
                binding["concept"],
                country="us",
            )
            assert mapping is not None and mapping.comparable
            assert binding["mapping_type"] == mapping.mapping_type
            if mapping.policyengine_variable:
                assert binding["variable"] == mapping.policyengine_variable
            if mapping.policyengine_parameter:
                assert binding["parameter"] == mapping.policyengine_parameter
            if mapping.parameter_key_input:
                assert binding["parameter_key_input"] == mapping.parameter_key_input
                assert binding["parameter_key_map"] == mapping.parameter_key_map


def test_aca_grid_pins_prior_year_fpl_dollars_and_enrolled_premium():
    generator = _load_generator()
    cases = {case.case_id: case for case in generator.POLICIES["aca_ptc"].cases}

    assert cases["ptc-150fpl-family4"].inputs["magi"] == 48_225
    assert cases["ptc-250fpl-single"].inputs["magi"] == 39_125
    assert cases["ptc-300fpl-joint"].inputs["magi"] == 63_450
    assert cases["ptc-380fpl-single"].inputs["magi"] == 59_470
    assert cases["ptc-410fpl-single"].inputs["magi"] == 64_165
    assert cases["ptc-95fpl-single"].inputs["magi"] == 14_867.50
    situation = generator._aca_ptc_situation(cases["ptc-250fpl-single"])
    tax_unit = situation["tax_units"]["tax_unit"]
    assert tax_unit["aca_magi"][2026] == 39_125
    assert tax_unit["slcsp"][2026] == 6_000
    assert tax_unit["selected_marketplace_plan_premium_proxy"][2026] == 5_800
    invalid_inputs = dict(cases["ptc-250fpl-single"].inputs)
    invalid_inputs["coverage_months"] = 11
    invalid_case = replace(
        cases["ptc-250fpl-single"],
        inputs=invalid_inputs,
    )
    with pytest.raises(ValueError, match="exactly 12 coverage months"):
        generator._aca_ptc_situation(invalid_case)


def test_payroll_and_niit_inputs_are_derived_from_contract_facts():
    generator = _load_generator()
    payroll_cases = {
        case.case_id: case
        for case in generator.POLICIES["additional_medicare_tax"].cases
    }
    mfs = generator._payroll_situation(payroll_cases["amt-mfs-150k"])
    assert mfs["people"]["head"]["is_separated"][2026] is True
    assert mfs["people"]["head"]["employment_income"][2026] == 150_000

    seca_cases = {
        case.case_id: case for case in generator.POLICIES["self_employment_tax"].cases
    }
    joint = generator._payroll_situation(seca_cases["seca-joint-200k"])
    assert joint["people"]["head"]["self_employment_income"][2026] == 200_000
    assert joint["people"]["spouse"]["employment_income"][2026] == 0

    niit_cases = {
        case.case_id: case
        for case in generator.POLICIES["net_investment_income_tax"].cases
    }
    rental = generator._niit_situation(niit_cases["niit-rental"])
    assert rental["people"]["head"]["rental_income"][2026] == 60_000
    assert "adjusted_gross_income" not in rental["tax_units"]["tax_unit"]


def test_qbid_grid_binds_correct_2026_band_and_active_business_diagnostic():
    generator = _load_generator()
    cases = {
        case.case_id: case
        for case in generator.POLICIES["qualified_business_income_deduction"].cases
    }

    phasein = cases["qbid-phasein"]
    assert "threshold" not in phasein.inputs
    assert phasein.inputs["taxable_income_before_qbid"] == 239_250
    situation = generator._qbid_situation(phasein)
    assert situation["people"]["head"]["qualified_business_income"][2026] == (200_000)
    assert (
        situation["tax_units"]["tax_unit"]["taxable_income_less_qbid"][2026] == 239_250
    )

    passive = cases["qbid-above-nowages"]
    assert passive.inputs["qbi"] == 300_000
    assert passive.inputs["active_business_qbi"] == 0
    active = cases["qbid-active-minimum"]
    assert active.inputs["active_business_qbi"] == 1_000


def test_qbid_fixture_binding_matches_merged_pipeline_surface(monkeypatch):
    generator = _load_generator()
    cases = {
        case.case_id: case
        for case in generator.POLICIES["qualified_business_income_deduction"].cases
    }
    captured = {}

    def capture_fixture_values(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(generator, "_require_fixture_values", capture_fixture_values)
    generator._validate_qbid_fixture(cases["qbid-phasein"], {})

    pipeline = (
        "us:policies/income_tax/qualified_business_income_deduction_pipeline#input."
    )
    statute = "us:statutes/26/199A#input."
    capital_gain = "us:statutes/26/1/h#input."
    expected = captured["expected"]
    assert set(expected) == {
        f"{pipeline}filing_status",
        (
            f"{pipeline}"
            "supplied_amounts_are_for_taxpayers_only_qualified_trade_or_business"
        ),
        f"{statute}qualified_trade_or_business_w2_wages",
        f"{statute}qualified_trade_or_business_unadjusted_basis",
        f"{statute}qualified_business_income",
        f"{statute}taxable_income_computed_without_section_199A",
        (
            f"{statute}"
            "qualified_business_income_allocable_to_qualified_cooperative_payments"
        ),
        f"{statute}w2_wages_allocable_to_qualified_cooperative_payments",
        f"{statute}qualified_reit_dividends",
        f"{statute}qualified_publicly_traded_partnership_income",
        f"{statute}taxpayer_is_corporation",
        (
            f"{statute}"
            "aggregate_qualified_business_income_from_active_qualified_"
            "trades_or_businesses"
        ),
        f"{statute}qualified_production_activities_income",
        (f"{statute}taxpayer_is_specified_agricultural_or_horticultural_cooperative"),
        f"{statute}cooperative_w2_wages",
        (
            f"{capital_gain}"
            "net_capital_gain_taken_into_account_as_investment_income_"
            "under_section_163_d_4_B_iii"
        ),
        f"{capital_gain}long_term_capital_gains",
        f"{capital_gain}short_term_capital_gains",
        f"{capital_gain}qualified_dividend_income",
    }
    assert expected[f"{pipeline}filing_status"] == 0
    assert (
        expected[
            f"{pipeline}"
            "supplied_amounts_are_for_taxpayers_only_qualified_trade_or_business"
        ]
        is True
    )


def test_savers_grid_uses_completed_person_contributions_and_two_caps():
    generator = _load_generator()
    cases = {case.case_id: case for case in generator.POLICIES["savers_credit"].cases}
    joint = cases["joint-separate-cap-for-each-spouse"]
    situation = generator._savers_credit_situation(joint)

    assert joint.inputs["first_threshold"] == 48_500
    assert joint.inputs["second_threshold"] == 52_500
    assert joint.inputs["third_threshold"] == 80_500
    assert (
        situation["people"]["head"]["savers_credit_qualified_contributions"][2026]
        == 5_000
    )
    assert (
        situation["people"]["spouse"]["savers_credit_qualified_contributions"][2026]
        == 5_000
    )
    assert situation["tax_units"]["tax_unit"]["adjusted_gross_income"][2026] == 40_000
    section_911 = generator._savers_credit_situation(
        cases["section-911-add-back-crosses-inclusive-limit"]
    )
    assert (
        section_911["tax_units"]["tax_unit"]["foreign_earned_income_exclusion"][2026]
        == 1
    )
    surviving = generator._savers_credit_situation(
        cases["surviving-spouse-uses-all-other-limits"]
    )
    assert (
        surviving["tax_units"]["tax_unit"]["filing_status"][2026] == "SURVIVING_SPOUSE"
    )
    assert generator.POLICIES["savers_credit"].pe_diagnostic_variables == (
        "savers_credit",
        "savers_credit_credit_limit",
    )


def test_savers_grid_has_matching_b_minus_one_probe_at_all_nine_boundaries():
    generator = _load_generator()
    config = generator.POLICIES["savers_credit"]
    cases = {case.case_id: case for case in config.cases}
    fixture = yaml.safe_load(
        (
            REPO_ROOT / "comparisons/fixtures/us-savers-grid-boundary-probes.yaml"
        ).read_text()
    )
    outputs = {
        record["name"]: record["output"][config.axiom_output] for record in fixture
    }
    expected = {
        "single-one-below-50-percent-limit": (24_249, 1_000),
        "single-one-below-20-percent-limit": (26_249, 400),
        "single-one-below-10-percent-limit": (40_249, 200),
        "joint-one-below-50-percent-limit": (48_499, 1_000),
        "joint-one-below-20-percent-limit": (52_499, 400),
        "joint-one-below-10-percent-limit": (80_499, 200),
        "head-of-household-one-below-50-percent-limit": (36_374, 1_000),
        "head-of-household-one-below-20-percent-limit": (39_374, 400),
        "head-of-household-one-below-10-percent-limit": (60_374, 200),
    }
    assert set(outputs) == set(expected)
    for case_id, (agi, credit) in expected.items():
        assert cases[case_id].inputs["adjusted_gross_income"] == agi
        assert float(outputs[case_id]) == credit


def test_savers_grid_report_discloses_section_911_match_cancellation():
    generator = _load_generator()
    config = generator.POLICIES["savers_credit"]
    values = {case.case_id: 400.0 for case in config.cases}
    empty_by_case = {case.case_id: {} for case in config.cases}

    report = generator._build_report(
        config,
        axiom=values,
        fixture_inputs=empty_by_case,
        policyengine=values,
        policyengine_components=empty_by_case,
    )
    section_911 = next(
        case
        for case in report["cases"]
        if case["case_id"] == "section-911-add-back-crosses-inclusive-limit"
    )

    assert "cancellation, not section 911 parity" in section_911["diagnostic_note"]


def test_elderly_disabled_grid_collapses_only_proven_disability_facts():
    generator = _load_generator()
    config = generator.POLICIES["elderly_disabled_credit"]
    cases = {case.case_id: case for case in config.cases}

    assert "eld-no-qualified-individual" not in cases
    disabled = cases["eld-disabled-under-65"]
    assert generator._collapsed_section_22_disability(disabled.inputs) is True
    situation = generator._elderly_disabled_situation(disabled)
    assert situation["people"]["head"]["retired_on_total_disability"][2026] is True
    assert situation["people"]["head"]["total_disability_payments"][2026] == 2_000
    assert situation["tax_units"]["tax_unit"]["tax_unit_social_security"][2026] == 0

    basic = generator._elderly_disabled_situation(cases["eld-basic"])
    assert basic["tax_units"]["tax_unit"]["tax_unit_social_security"][2026] == 2_000
    assert basic["tax_units"]["tax_unit"]["tax_unit_taxable_social_security"][2026] == 0


def test_llc_grid_binds_explicit_status_and_liability_capped_final():
    generator = _load_generator()
    cases = {
        case.case_id: case
        for case in generator.POLICIES["lifetime_learning_credit"].cases
    }
    diagnostic = generator._llc_situation(cases["llc-liability-cap-diagnostic"])
    tax_unit = diagnostic["tax_units"]["tax_unit"]

    assert tax_unit["filing_status"][2026] == "SINGLE"
    assert tax_unit["income_tax_before_credits"][2026] == 500
    assert (
        diagnostic["people"]["student1"]["qualified_tuition_expenses"][2026] == 10_000
    )
    assert diagnostic["people"]["student1"]["is_tax_unit_dependent"][2026] is True

    aggregate = generator._llc_situation(cases["llc-aggregate-cap"])
    assert {name for name in aggregate["people"] if name.startswith("student")} == {
        "student1",
        "student2",
    }


def test_additional_medicare_fixture_enforces_wage_only_person_boundary():
    generator = _load_generator()
    case = next(
        case
        for case in generator.POLICIES["additional_medicare_tax"].cases
        if case.case_id == "amt-single-250k"
    )
    additional_module = "us:policies/income_tax/additional_medicare_tax_pipeline"
    se_module = "us:policies/income_tax/self_employment_tax_pipeline"
    relation = f"{se_module}#relation.self_employed_individual_of_tax_unit"
    actual = {
        "us:statutes/26/3101/b/2#input.filing_status": 0,
        f"{additional_module}#input.wages": 250_000,
        f"{additional_module}#input.no_foreign_system_exclusive_se_income": True,
        relation: [
            {
                f"{se_module}#input.gross_self_employment_profit": 0,
                (
                    "us:statutes/26/1402/b#input."
                    "wages_paid_to_individual_during_taxable_year_for_section_1401_a"
                ): 250_000,
                ("us:statutes/26/1402/b#input.individual_is_nonresident_alien"): False,
                (
                    "us:statutes/26/1402/b#input."
                    "agreement_under_social_security_act_section_233_provides_"
                    "for_individual"
                ): False,
                (
                    "us:statutes/26/1402/b#input."
                    "individual_is_not_united_states_citizen_and_resident_of_"
                    "puerto_rico_virgin_islands_guam_or_american_samoa"
                ): False,
            }
        ],
    }

    generator._validate_additional_medicare_fixture(case, actual)

    positive_se_case = replace(
        case,
        inputs={**case.inputs, "self_employment_income": 1},
    )
    with pytest.raises(ValueError, match="wage-only, zero-self-employment"):
        generator._validate_additional_medicare_fixture(positive_se_case, actual)

    stale_flat_fixture = dict(actual)
    stale_flat_fixture.pop(relation)
    stale_flat_fixture["us:statutes/26/1401#input.self_employment_income"] = 138_525
    with pytest.raises(ValueError, match="must contain 1 Person input"):
        generator._validate_additional_medicare_fixture(
            case,
            stale_flat_fixture,
        )


def test_axiom_fixture_is_resolved_only_from_supplied_roots(tmp_path):
    generator = _load_generator()
    original = generator.POLICIES["net_investment_income_tax"]
    output = "us:policies/test#net_investment_income_tax"
    config = replace(
        original,
        axiom_module_ref="us:policies/test",
        fixture_path=Path("us/policies/test.test.yaml"),
        axiom_output=output,
        fixture_input_validator=lambda _case, _actual: None,
    )
    fixture = tmp_path / config.fixture_path
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        json.dumps(
            [
                {
                    "name": case.case_id,
                    "period": {
                        "period_kind": "tax_year",
                        "start": "2026-01-01",
                        "end": "2026-12-31",
                    },
                    "input": {"us:policies/test#income": index},
                    "output": {output: index * 100},
                }
                for index, case in enumerate(config.cases, start=1)
            ]
        )
    )

    (
        path,
        values,
        fixture_inputs,
        bridge_values,
        diagnostic_values,
    ) = generator._axiom_values(config, [tmp_path])

    assert path == fixture
    assert values["niit-under"] == 100
    assert values["niit-rental"] == 600
    assert fixture_inputs["niit-single-mixed"] == {"us:policies/test#income": 2}
    assert bridge_values == {case.case_id: {} for case in config.cases}
    assert diagnostic_values == {case.case_id: {} for case in config.cases}


def test_non_vacuous_guard_requires_a_nonzero_matching_case():
    generator = _load_generator()
    config = generator.POLICIES["additional_medicare_tax"]
    all_zero = {case.case_id: 0.0 for case in config.cases}

    with pytest.raises(RuntimeError, match="vacuous grid"):
        generator._assert_non_vacuous(config, all_zero, all_zero)

    axiom = dict(all_zero)
    policyengine = dict(all_zero)
    axiom["amt-single-250k"] = 450
    policyengine["amt-single-250k"] = 450.005
    generator._assert_non_vacuous(config, axiom, policyengine)


def test_v2_report_counts_one_pair_per_case():
    generator = _load_generator()
    config = generator.POLICIES["additional_medicare_tax"]
    axiom = {
        case.case_id: float(index * 100)
        for index, case in enumerate(
            config.cases,
            start=1,
        )
    }
    policyengine = dict(axiom)
    policyengine["amt-single-250k"] -= 1
    fixture_inputs = {case.case_id: {} for case in config.cases}
    components = {
        case.case_id: {"additional_medicare_tax": policyengine[case.case_id]}
        for case in config.cases
    }

    report = generator._build_report(
        config,
        axiom=axiom,
        fixture_inputs=fixture_inputs,
        policyengine=policyengine,
        policyengine_components=components,
    )

    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["suite"] == "us-additional-medicare-grid"
    assert report["engines"] == {
        "left": "axiom",
        "right": "policyengine",
        "versions": {
            "policyengine": "4.18.9",
            "policyengine_core": "3.30.3",
            "policyengine_us": "1.767.3",
        },
    }
    assert report["engine_bindings"]["policyengine"]["outputs"] == [
        "additional_medicare_tax"
    ]
    assert report["summary"]["comparison_count"] == 5
    assert report["summary"]["match_count"] == 4
    assert report["summary"]["mismatch_count"] == 1
    assert report["aggregates"][0]["comparison_count"] == 5
    assert report["aggregates"][0]["match_count"] == 4
    assert report["aggregates"][0]["mismatch_count"] == 1
    assert len(report["mismatches"]) == 1


def test_registry_runner_uses_suite_pin_overrides_and_configured_roots(
    monkeypatch,
    tmp_path,
):
    runner = _load_runner()
    rulespec = tmp_path / "rulespec-us"
    rulespec.mkdir()
    output = tmp_path / "report.json"
    calls: list[list[str]] = []

    def fake_run(cmd, *, check, cwd):
        assert check is True
        assert cwd == runner.REPO_ROOT
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner._run_federal_tax_liability_grid(
        {
            "parameters": {
                "policy": "net_investment_income_tax",
                "python": "3.13",
                "rulespec_roots": [str(rulespec)],
                "policyengine_version": "4.18.9",
                "policyengine_us_version": "1.767.3",
                "policyengine_core_version": "3.30.3",
            }
        },
        output,
    )

    assert runner.RUNNERS["federal-tax-liability-grid"] is (
        runner._run_federal_tax_liability_grid
    )
    cmd = calls[0]
    assert cmd[:4] == ["uv", "run", "--python", "3.13"]
    assert "policyengine==4.18.9" in cmd
    assert "policyengine-us==1.767.3" in cmd
    assert "policyengine-core==3.30.3" in cmd
    assert cmd[cmd.index("--policy") + 1] == "net_investment_income_tax"
    assert cmd[cmd.index("--rulespec-root") + 1] == str(rulespec.resolve())
    assert cmd[cmd.index("--output") + 1] == str(output)


def test_registry_verifies_snapshot_tree_and_stamps_upstream_sha(tmp_path):
    runner = _load_runner()
    rulespec = tmp_path / "rulespec-us"
    rulespec.mkdir()
    subprocess.run(["git", "init", "-q", str(rulespec)], check=True)
    subprocess.run(
        ["git", "-C", str(rulespec), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(rulespec), "config", "user.name", "Test"],
        check=True,
    )
    (rulespec / "fixture.yaml").write_text("value: 1\n")
    subprocess.run(["git", "-C", str(rulespec), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(rulespec), "commit", "-qm", "snapshot"],
        check=True,
    )
    tree = subprocess.run(
        ["git", "-C", str(rulespec), "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    upstream_sha = "a" * 40
    params = {
        "rulespec_roots": [str(rulespec)],
        "rulespec_upstream_sha": upstream_sha,
        "rulespec_upstream_tree": tree,
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
    }

    runner._verify_federal_rulespec_snapshot(params, [rulespec])

    assert params[runner._VERIFIED_RULESPEC_UPSTREAM_SHA] == upstream_sha
    output = tmp_path / "report.json"
    output.write_text('{"suite": "federal-test"}\n')
    block = runner._build_run_provenance(
        {
            "name": "federal-test",
            "runner": {
                "type": "federal-tax-liability-grid",
                "parameters": params,
            },
        },
        "federal-tax-liability-grid",
        output,
    )
    assert block["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": upstream_sha,
        }
    ]


def test_registry_rejects_dirty_or_tree_mismatched_snapshot(tmp_path):
    runner = _load_runner()
    rulespec = tmp_path / "rulespec-us"
    rulespec.mkdir()
    subprocess.run(["git", "init", "-q", str(rulespec)], check=True)
    subprocess.run(
        ["git", "-C", str(rulespec), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(rulespec), "config", "user.name", "Test"],
        check=True,
    )
    (rulespec / "fixture.yaml").write_text("value: 1\n")
    subprocess.run(["git", "-C", str(rulespec), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(rulespec), "commit", "-qm", "snapshot"],
        check=True,
    )
    tree = subprocess.run(
        ["git", "-C", str(rulespec), "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    params = {
        "rulespec_upstream_sha": "a" * 40,
        "rulespec_upstream_tree": "b" * 40,
    }
    with pytest.raises(SystemExit, match="tree mismatch"):
        runner._verify_federal_rulespec_snapshot(params, [rulespec])

    params["rulespec_upstream_tree"] = tree
    (rulespec / "fixture.yaml").write_text("value: 2\n")
    with pytest.raises(SystemExit, match="working-tree changes"):
        runner._verify_federal_rulespec_snapshot(params, [rulespec])


def test_registry_runner_clones_declared_remote_when_dev_root_is_absent(
    monkeypatch,
    tmp_path,
):
    runner = _load_runner()
    clone = tmp_path / "rulespec-us"
    clone.mkdir()
    output = tmp_path / "report.json"
    calls: list[list[str]] = []
    params = {
        "policy": "aca_ptc",
        "rulespec_roots": [str(tmp_path / "missing-wt-fed-ptc")],
        "rulespec_remote": "https://example.test/rulespec-us.git",
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.30.3",
    }
    monkeypatch.setattr(
        runner,
        "_ensure_rulespec_us_checkout",
        lambda remote: (
            clone
            if remote == "https://example.test/rulespec-us.git"
            else pytest.fail("unexpected remote")
        ),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda cmd, *, check, cwd: calls.append(cmd),
    )

    runner._run_federal_tax_liability_grid(
        {"parameters": params},
        output,
    )

    assert params["rulespec_roots"] == [str(clone)]
    cmd = calls[0]
    assert cmd[cmd.index("--rulespec-root") + 1] == str(clone)


def test_registry_runner_rejects_missing_or_wrong_federal_oracle_pins(tmp_path):
    runner = _load_runner()
    rulespec = tmp_path / "rulespec-us"
    rulespec.mkdir()
    parameters = {
        "policy": "aca_ptc",
        "rulespec_roots": [str(rulespec)],
        "policyengine_version": "4.18.9",
        "policyengine_us_version": "1.767.3",
        "policyengine_core_version": "3.28.0",
    }

    with pytest.raises(SystemExit, match="reviewed 2026 oracle stack"):
        runner._run_federal_tax_liability_grid(
            {"parameters": parameters},
            tmp_path / "report.json",
        )
