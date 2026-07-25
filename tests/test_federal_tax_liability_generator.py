"""Focused invariants for the independent federal tax case grids."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


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


def test_all_eight_contract_grids_are_explicit_and_independent():
    generator = _load_generator()

    assert set(generator.POLICIES) == {
        "aca_ptc",
        "additional_medicare_tax",
        "elderly_disabled_credit",
        "lifetime_learning_credit",
        "net_investment_income_tax",
        "qualified_business_income_deduction",
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
            "savers-50pct",
            "savers-20pct",
            "savers-10pct",
            "savers-over",
            "savers-cap",
            "savers-joint-both",
            "savers-zero-contributions",
            "savers-at-first-threshold",
            "savers-one-over-first-threshold",
            "savers-age-screen",
            "savers-student-screen",
            "savers-dependent-screen",
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
        "us:policies/income_tax/"
        "qualified_business_income_deduction_pipeline#input."
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
        (
            f"{statute}"
            "taxpayer_is_specified_agricultural_or_horticultural_cooperative"
        ),
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
    joint = cases["savers-joint-both"]
    situation = generator._savers_credit_situation(joint)

    assert joint.inputs["first_threshold"] == 48_500
    assert joint.inputs["second_threshold"] == 52_500
    assert joint.inputs["third_threshold"] == 80_500
    assert (
        situation["people"]["head"]["savers_credit_qualified_contributions"][2026]
        == 2_000
    )
    assert (
        situation["people"]["spouse"]["savers_credit_qualified_contributions"][2026]
        == 2_000
    )
    assert situation["tax_units"]["tax_unit"]["adjusted_gross_income"][2026] == 38_000
    assert generator.POLICIES["savers_credit"].pe_diagnostic_variables == (
        "savers_credit",
        "savers_credit_credit_limit",
    )


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

    path, values, fixture_inputs = generator._axiom_values(
        config,
        [tmp_path],
    )

    assert path == fixture
    assert values["niit-under"] == 100
    assert values["niit-rental"] == 600
    assert fixture_inputs["niit-single-mixed"] == {"us:policies/test#income": 2}


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
    assert report["engines"] == {"left": "axiom", "right": "policyengine"}
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
