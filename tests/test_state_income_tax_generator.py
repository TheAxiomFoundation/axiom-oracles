"""Focused invariants for the state income-tax comparison generator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_generator():
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "generate_state_income_tax_liability.py"
    )
    spec = importlib.util.spec_from_file_location("state_income_tax_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summary_counts_both_pairwise_legs_regardless_of_pe_match_status():
    generator = _load_generator()
    cases = [
        generator.Case("dc-single-30000", "DC", "single", 30_000.0),
        generator.Case("dc-married-60000", "DC", "married", 60_000.0),
    ]
    axiom = {
        ("DC", "single", 30_000): 1_000.0,
        ("DC", "married", 60_000): 2_000.0,
    }
    taxsim = {case.case_id: 0.0 for case in cases}

    for policyengine in (
        {"dc-single-30000": 1_000.0, "dc-married-60000": 2_000.0},
        {"dc-single-30000": 900.0, "dc-married-60000": 2_000.0},
    ):
        summary = generator._build_report(
            "DC", cases, axiom, policyengine, taxsim
        )["summary"]
        assert summary["comparison_count"] == 4
        assert summary["match_count"] + summary["mismatch_count"] == 4


@pytest.mark.parametrize(
    ("state", "output", "grid_values"),
    [
        (
            "NY",
            "us-ny:policies/income_tax/pilot_liability_pipeline"
            "#ny_pit_pilot_main_income_tax",
            {
                "single_30000": 1023.4,
                "single_60000": 2643.4,
                "single_150000": 7810.65,
                "joint_60000": 2040.7,
                "joint_120000": 5280.7,
                "joint_300000": 15612.6,
            },
        ),
        (
            "CO",
            "us-co:policies/income_tax/pilot_liability_pipeline"
            "#co_pit_pilot_income_tax_liability",
            {
                "single_30000": 611.6,
                "single_60000": 1931.6,
                "single_150000": 5891.6,
                "joint_60000": 1223.2,
                "joint_120000": 3863.2,
                "joint_300000": 11783.2,
            },
        ),
    ],
)
def test_axiom_liabilities_ignores_non_grid_boundary_fixtures(
    tmp_path, state, output, grid_values
):
    generator = _load_generator()
    fixture_path = (
        tmp_path
        / f"us-{state.lower()}"
        / "policies"
        / "income_tax"
        / "pilot_liability_pipeline.test.yaml"
    )
    fixture_path.parent.mkdir(parents=True)

    boundary_cases = [
        {
            "name": f"single_schedule_boundary_{index}",
            "input": {},
            "output": {output: index},
        }
        for index in range(52)
    ]
    grid_cases = [
        {"name": name, "input": {}, "output": {output: value}}
        for name, value in grid_values.items()
    ]
    fixture_path.write_text(json.dumps(boundary_cases + grid_cases))

    generator.RULESPEC_US = tmp_path
    generator._STATES = (state,)
    generator._LIABILITY_OUTPUT[state] = output

    assert generator._axiom_liabilities() == {
        (
            state,
            "married" if name.startswith("joint") else "single",
            int(name.rsplit("_", 1)[-1]),
        ): value
        for name, value in grid_values.items()
    }


def test_axiom_liabilities_extracts_only_mississippi_canonical_grid(tmp_path):
    generator = _load_generator()
    output = (
        "us-ms:policies/income_tax/pilot_liability_pipeline"
        "#ms_pit_pilot_income_tax_liability"
    )
    fixture_path = (
        tmp_path
        / "us-ms"
        / "policies"
        / "income_tax"
        / "pilot_liability_pipeline.test.yaml"
    )
    fixture_path.parent.mkdir(parents=True)

    boundary_cases = [
        {
            "name": name,
            "input": {},
            "output": {output: index},
        }
        for index, name in enumerate(
            [
                "individual_candidate_negative_income_normalizes_to_zero",
                "joint_candidate_negative_income_normalizes_to_zero",
                "individual_candidate_one_dollar_below_zero_tax_ceiling",
                "joint_candidate_at_zero_tax_ceiling",
                "individual_candidate_one_dollar_above_zero_tax_ceiling",
                "joint_candidate_above_zero_tax_ceiling",
                "relation_aggregates_both_candidate_sets",
                "strict_lower_separate_total_selects_separate_branch",
                "lower_joint_total_selects_joint_branch",
                "equal_totals_choose_joint_branch",
            ]
        )
    ]
    grid_values = {
        "single_30000": 468,
        "single_60000": 1668,
        "single_150000": 5268,
        "joint_60000": 1336,
        "joint_120000": 3736,
        "joint_300000": 10936,
    }
    grid_cases = [
        {"name": name, "input": {}, "output": {output: value}}
        for name, value in grid_values.items()
    ]
    fixture_path.write_text(json.dumps(boundary_cases + grid_cases))

    generator.RULESPEC_US = tmp_path
    generator._STATES = ("MS",)

    assert generator._STRICT_GRID_FIXTURE_STATES == frozenset({"CO", "MS", "NY"})
    assert generator._axiom_liabilities() == {
        ("MS", "single", 30_000): 468.0,
        ("MS", "single", 60_000): 1668.0,
        ("MS", "single", 150_000): 5268.0,
        ("MS", "married", 60_000): 1336.0,
        ("MS", "married", 120_000): 3736.0,
        ("MS", "married", 300_000): 10936.0,
    }


@pytest.mark.parametrize("state", ["CO", "MS", "NY"])
def test_strict_grid_states_ignore_noncanonical_agi_fixture(tmp_path, state):
    generator = _load_generator()
    output = generator._LIABILITY_OUTPUT[state]
    fixture_path = (
        tmp_path
        / f"us-{state.lower()}"
        / "policies"
        / "income_tax"
        / "pilot_liability_pipeline.test.yaml"
    )
    fixture_path.parent.mkdir(parents=True)
    agi_input = (
        f"us-{state.lower()}:policies/income_tax/pilot_liability_pipeline#"
        "input.adjusted_gross_income"
    )
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "name": "noncanonical_boundary_with_agi",
                    "input": {agi_input: 99_999},
                    "output": {output: 999_999},
                },
                {
                    "name": "single_30000",
                    "input": {agi_input: 99_999},
                    "output": {output: 123},
                },
            ]
        )
    )

    generator.RULESPEC_US = tmp_path
    generator._STATES = (state,)

    assert generator._axiom_liabilities() == {
        (state, "single", 30_000): 123.0,
    }


def test_axiom_liabilities_preserves_adjusted_gross_income_mapping(tmp_path):
    generator = _load_generator()
    output = (
        "us-al:policies/income_tax/pilot_liability_pipeline"
        "#al_pit_pilot_income_tax_liability"
    )
    fixture_path = (
        tmp_path
        / "us-al"
        / "policies"
        / "income_tax"
        / "pilot_liability_pipeline.test.yaml"
    )
    fixture_path.parent.mkdir(parents=True)
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "name": "single_standard_grid_case",
                    "input": {
                        "us-al:example#al_adjusted_gross_income": 30_000
                    },
                    "output": {output: 1_000},
                },
                {
                    "name": "married_standard_grid_case",
                    "input": {
                        "us-al:example#al_adjusted_gross_income": 60_000
                    },
                    "output": {output: 2_000},
                },
            ]
        )
    )

    generator.RULESPEC_US = tmp_path
    generator._STATES = ("AL",)
    generator._LIABILITY_OUTPUT["AL"] = output

    assert generator._axiom_liabilities() == {
        ("AL", "single", 30_000): 1_000.0,
        ("AL", "married", 60_000): 2_000.0,
    }


def test_recent_state_income_tax_oracle_registrations():
    generator = _load_generator()

    expected = {
        "KS": (17, "ks_income_tax_before_credits", (1.0, 0.0)),
        "ND": (35, "nd_income_tax_before_credits", (1.0, 0.0)),
        "PA": (39, "pa_income_tax_before_forgiveness", (1.0, 0.0)),
        "MO": (26, "mo_income_tax_before_credits", (1.0, 0.0)),
        "AR": (4, "ar_income_tax_before_non_refundable_credits_unit", (1.0, 0.0)),
        "MS": (25, "ms_income_tax_before_credits_unit", (1.0, 0.0)),
        "NH": (30, "nh_income_tax_before_refundable_credits", (1.0, 0.0)),
        "WV": (49, "wv_income_tax_before_non_refundable_credits", (1.0, 0.0)),
        "VT": (46, "vt_income_tax_before_non_refundable_credits", (0.01, 1e-7)),
        "CO": (6, "co_income_tax_before_non_refundable_credits", (1.0, 0.0)),
    }
    for state, (taxsim_code, policyengine_target, tolerance) in expected.items():
        assert generator._TAXSIM_STATE[state] == taxsim_code
        assert generator._PE_VAR[state] == policyengine_target
        assert generator._TOL[state] == tolerance
        assert state in generator._POPULACE_STATES
        if state == "AR":
            assert state not in generator._STATES
            assert "Person-grain" in generator._GRID_EXCLUDED_STATES[state]
        else:
            assert state in generator._STATES
        assert generator._MODULE[state] == (
            f"us-{state.lower()}:policies/income_tax/pilot_liability_pipeline"
        )
        assert generator._LIABILITY_OUTPUT[state] == (
            f"{generator._MODULE[state]}"
            f"#{state.lower()}_pit_pilot_income_tax_liability"
        )
    assert generator._POPULACE_TOL["CO"] == (0.01, 1e-7)


def test_arkansas_legacy_grid_is_explicitly_decoupled() -> None:
    generator = _load_generator()

    assert "AR" in generator._TAXSIM_STATE
    assert "AR" in generator._POPULACE_STATES
    assert "AR" not in generator._STATES
    assert generator._POPULACE_OUTPUT["AR"].endswith(
        "#ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    )
    assert (
        generator._POPULACE_PE_VAR["AR"]
        == "ar_income_tax_before_non_refundable_credits_indiv"
    )
    assert generator._POPULACE_AGGREGATION["AR"] == "person_sum_to_tax_unit"


def test_finalize_report_adds_v21_dispositions_and_provenance():
    generator = _load_generator()
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "test-state-income-tax-liability",
        "summary": {
            "comparison_count": 0,
            "match_count": 0,
            "mismatch_count": 0,
        },
        "mismatches": [],
        "cases": [],
    }
    generated_at = "2026-07-21T17:00:00Z"
    rulespecs = [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": "0ddfa1215cb5e0298b5c849c6738b2dfe5c77399",
        }
    ]

    finalized = generator._finalize_report(
        report,
        generated_at=generated_at,
        rulespecs=rulespecs,
    )

    assert finalized["schema_version"] == "axiom.comparison_report.v2.1"
    assert isinstance(finalized["summary"]["dispositioned"], dict)
    assert finalized["provenance"]["generated_at"] == generated_at
    assert finalized["provenance"]["rulespecs"] == rulespecs


def test_committed_state_income_tax_reports_are_dispositioned_v21():
    reports = (
        Path(__file__).parents[1] / "dashboard" / "public" / "data"
    ).glob("axiom-policyengine-taxsim-*-income-tax-liability.json")

    for path in reports:
        report = json.loads(path.read_text())
        assert report["schema_version"] == "axiom.comparison_report.v2.1", path
        assert isinstance(report["summary"].get("dispositioned"), dict), path
