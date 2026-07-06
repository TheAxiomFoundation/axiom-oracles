import argparse

import pytest

import axiom_oracles.bridges.tax_populace as tax_populace
from axiom_oracles.bridges.tax_populace import (
    AOTC_BASE,
    AOTC_OUTPUTS,
    CAPITAL_GAINS_BASE,
    CAPITAL_GAINS_DEFINITION_OUTPUTS,
    CDCC_BASE,
    CDCC_OUTPUTS,
    CTC_BASE,
    CTC_H_BASE,
    EITC_BASE,
    EITC_OUTPUTS,
    EMPLOYEE_OASDI_BASE,
    EMPLOYEE_OASDI_PROGRAM_PATH,
    INCOME_TAX_BASE,
    INCOME_TAX_OUTPUTS,
    NONREFUNDABLE_CREDITS_BASE,
    NONREFUNDABLE_CREDITS_OUTPUTS,
    OASDI_WAGE_BASE_BASE,
    OASDI_WAGE_BASE_EXCLUSION_OUTPUT,
    OASDI_WAGE_BASE_PROGRAM_PATH,
    SECTION_32_C_2_BASE,
    SECTION_112_BASE,
    SECTION_152_C_BASE,
    SECTION_164_F_BASE,
    SECTION_1401_BASE,
    SECTION_1402_A_BASE,
    SECTION_1402_B_BASE,
    SECTION_7703_BASE,
    TAX_BEFORE_CREDITS_BASE,
    TAX_BEFORE_CREDITS_OUTPUTS,
    TAX_BEFORE_CREDITS_PROGRAM_PATH,
    additional_standard_deduction_entitlement_count,
    build_aotc_request,
    build_capital_gain_definitions_request,
    build_cdcc_request,
    build_contribution_and_benefit_base_request,
    build_ctc_request,
    build_eitc_request,
    build_income_tax_request,
    build_nonrefundable_credits_request,
    build_oasdi_wage_base_request,
    build_payroll_request,
    build_tax_before_credits_request,
    compare_tax_ecps,
    contribution_and_benefit_base_from_results,
    contribution_and_benefit_base_from_rulespec_test,
    contribution_and_benefit_base_output,
    contribution_and_benefit_base_output_for_program,
    contribution_and_benefit_base_program_path,
    ctc_h_filing_status_code,
    filing_status_code,
    individual_is_unmarried_and_not_surviving_spouse,
    output_number,
    person_entity_id,
    policyengine_data_certification_override_required,
    project_aotc_person_inputs,
    project_aotc_tax_unit_inputs,
    project_capital_gain_definition_inputs,
    project_cdcc_person_inputs,
    project_cdcc_tax_unit_inputs,
    project_ctc_h_person_inputs,
    project_ctc_person_inputs,
    project_eitc_person_inputs,
    project_eitc_relevant_investment_income,
    project_eitc_tax_unit_inputs,
    project_fica_wages,
    project_income_tax_inputs,
    project_nonrefundable_credits_inputs,
    project_oasdi_wage_base_inputs,
    project_section_32_c_2_tax_unit_inputs,
    project_section_112_tax_unit_inputs,
    project_section_152_c_person_inputs,
    project_section_164_f_tax_unit_inputs,
    project_section_1401_tax_unit_inputs,
    project_section_1402_a_tax_unit_inputs,
    project_section_1402_b_tax_unit_inputs,
    project_section_7703_tax_unit_inputs,
    project_standard_deduction_inputs,
    project_tax_unit_inputs,
    project_tax_unit_person_contexts,
    remove_raw_columns_replaced_by_outputs,
    require_policyengine_versions,
    resolve_rulespec_program_path,
    select_tax_unit_indices,
    tax_unit_positive_weight_mask,
    taxable_oasdi_wages_by_person_id,
    uses_joint_ctc_phaseout_threshold,
    valid_child_ssn_type,
    within_tolerance,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SINGLE", 0),
        ("JOINT", 1),
        ("SEPARATE", 2),
        ("HEAD_OF_HOUSEHOLD", 3),
        ("SURVIVING_SPOUSE", 4),
    ],
)
def test_filing_status_code_maps_policyengine_enum(value, expected):
    assert filing_status_code(value) == expected


def test_person_entity_id_is_stable_and_namespaced():
    assert person_entity_id(42) == "person_42"


def test_scalar_value_formats_scientific_float_as_decimal_literal():
    value = tax_populace.scalar_value(1.105810581991662e-11)

    assert value == {
        "kind": "decimal",
        "value": "0.00000000001105810581991662",
    }
    assert "e" not in value["value"].lower()


def test_scalar_value_keeps_plain_float_literal_format():
    assert tax_populace.scalar_value(184500.0) == {
        "kind": "decimal",
        "value": "184500.0",
    }


def test_remove_raw_columns_replaced_by_outputs_prefers_period_values():
    pd = pytest.importorskip("pandas")
    raw = pd.DataFrame(
        [
            {
                "person_id": 1,
                "qualified_tuition_expenses": 4_000,
                "age": 20,
            }
        ]
    )
    outputs = pd.DataFrame(
        [
            {
                "person_id": 1,
                "qualified_tuition_expenses": 4_400,
                "american_opportunity_credit": 2_500,
            }
        ]
    )

    filtered = remove_raw_columns_replaced_by_outputs(
        raw=raw,
        outputs=outputs,
        key="person_id",
    )
    merged = filtered.merge(outputs, on="person_id", how="left", validate="one_to_one")

    assert "qualified_tuition_expenses" in merged
    assert "qualified_tuition_expenses_x" not in merged
    assert "qualified_tuition_expenses_y" not in merged
    assert merged.loc[0, "qualified_tuition_expenses"] == 4_400
    assert merged.loc[0, "american_opportunity_credit"] == 2_500


def test_run_axiom_program_compiles_through_canonical_repo_alias(
    monkeypatch,
    tmp_path,
):
    rulespec_root = tmp_path / "rulespec-uk-worktree"
    program = rulespec_root / "statutes" / "ukpga" / "2007" / "3" / "35.yaml"
    program.parent.mkdir(parents=True)
    program.write_text("format: rulespec/v1\nrules: []\n")
    axiom_rules_path = tmp_path / "axiom-rules-engine"
    binary = axiom_rules_path / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_text("")

    compiled_programs = []
    compile_env_roots = []
    runtime_requests = []

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 6 and cmd[:3] == ["git", "-C", str(rulespec_root)]:
            return tax_populace.subprocess.CompletedProcess(
                cmd,
                0,
                stdout="https://github.com/TheAxiomFoundation/rulespec-uk.git\n",
                stderr="",
            )
        if "compile" in cmd:
            compiled_programs.append(cmd[cmd.index("--program") + 1])
            compile_env_roots.extend(
                kwargs["env"]["AXIOM_RULESPEC_REPO_ROOTS"].split(tax_populace.os.pathsep)
            )
            output_path = cmd[cmd.index("--output") + 1]
            with open(output_path, "w") as artifact:
                artifact.write(
                    tax_populace.json.dumps(
                        {
                            "program": {
                                "parameters": [],
                                "derived": [
                                    {
                                        "id": "uk-worktree:statutes/ukpga/2007/3/35#personal_allowance",
                                        "name": "personal_allowance",
                                        "entity": "Person",
                                    }
                                ],
                            }
                        }
                    )
                )
            return tax_populace.subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "run-compiled" in cmd:
            runtime_requests.append(tax_populace.json.loads(kwargs["input"]))
            return tax_populace.subprocess.CompletedProcess(
                cmd,
                0,
                stdout=tax_populace.json.dumps(
                    {
                        "results": [
                            {
                                "outputs": {
                                    "uk-worktree:statutes/ukpga/2007/3/35#personal_allowance": {
                                        "kind": "scalar",
                                        "value": {
                                            "kind": "integer",
                                            "value": 12570,
                                        },
                                    }
                                }
                            }
                        ]
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(tax_populace.subprocess, "run", fake_run)

    results = tax_populace.run_axiom_program(
        program=program,
        request={
            "mode": "explain",
            "dataset": {
                "inputs": [
                    {
                        "name": "uk:statutes/ukpga/2007/3/35#input.adjusted_net_income",
                        "entity": "Person",
                        "entity_id": "person_1",
                        "interval": {
                            "start": "2026-01-01",
                            "end": "2026-12-31",
                        },
                        "value": {
                            "kind": "decimal",
                            "value": "20000",
                        },
                    }
                ],
                "relations": [
                    {
                        "name": "uk:statutes/ukpga/2007/3/35#relation.members",
                        "tuple": ["person_1", "household_1"],
                        "interval": {
                            "start": "2026-01-01",
                            "end": "2026-12-31",
                        },
                    }
                ],
            },
            "queries": [
                {
                    "entity_id": "person_1",
                    "period": {
                        "period_kind": "tax_year",
                        "start": "2026-01-01",
                        "end": "2026-12-31",
                    },
                    "outputs": ["uk:statutes/ukpga/2007/3/35#personal_allowance"],
                }
            ],
        },
        rulespec_root=rulespec_root,
        axiom_rules_path=axiom_rules_path,
    )

    assert (
        results[0]["outputs"]["uk:statutes/ukpga/2007/3/35#personal_allowance"][
            "value"
        ]["value"]
        == 12570
    )
    assert compiled_programs
    assert "rulespec-uk" in compiled_programs[0].split("/")
    assert "rulespec-uk-worktree" not in compiled_programs[0].split("/")
    assert runtime_requests[0]["dataset"]["inputs"][0]["name"] == (
        "uk-worktree:statutes/ukpga/2007/3/35#input.adjusted_net_income"
    )
    assert runtime_requests[0]["dataset"]["relations"][0]["name"] == (
        "uk-worktree:statutes/ukpga/2007/3/35#relation.members"
    )
    assert runtime_requests[0]["queries"][0]["outputs"] == [
        "uk-worktree:statutes/ukpga/2007/3/35#personal_allowance"
    ]
    assert str(rulespec_root) in compile_env_roots
    assert str(rulespec_root.parent) in compile_env_roots
    assert compile_env_roots[0] != str(rulespec_root)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CITIZEN", True),
        ("NON_CITIZEN_VALID_EAD", True),
        ("NONE", False),
        ("OTHER_NON_CITIZEN", False),
    ],
)
def test_valid_child_ssn_type_maps_policyengine_enum(value, expected):
    assert valid_child_ssn_type(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("JOINT", True),
        ("SURVIVING_SPOUSE", True),
        ("SINGLE", False),
        ("SEPARATE", False),
        ("HEAD_OF_HOUSEHOLD", False),
    ],
)
def test_uses_joint_ctc_phaseout_threshold_matches_policyengine(value, expected):
    assert uses_joint_ctc_phaseout_threshold(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("JOINT", 1),
        ("SURVIVING_SPOUSE", 1),
        ("SINGLE", 0),
        ("SEPARATE", 2),
        ("HEAD_OF_HOUSEHOLD", 3),
    ],
)
def test_ctc_h_filing_status_code_matches_policyengine_phaseout_threshold(
    value, expected
):
    assert ctc_h_filing_status_code(value) == expected


def test_ctc_person_projection_marks_under_17_valid_ssn_child():
    projected = project_ctc_person_inputs({"age": 16, "ssn_card_type": "CITIZEN"})

    assert projected["age"] == 16
    assert projected["ctc_child_satisfies_dependency_rules"] is True
    assert projected["ctc_child_deduction_allowed"] is True
    assert projected["ctc_child_missing_identification"] is False
    assert projected["qualifying_child_tin_included_on_return"] is True


def test_ctc_person_projection_marks_under_17_missing_ssn_child():
    projected = project_ctc_person_inputs({"age": 9, "ssn_card_type": "NONE"})
    subsection_h_projected = project_ctc_h_person_inputs(
        {"age": 9, "ssn_card_type": "NONE"}
    )

    assert projected["ctc_child_satisfies_dependency_rules"] is True
    assert projected["ctc_child_missing_identification"] is True
    assert projected["qualifying_child_tin_included_on_return"] is False
    assert subsection_h_projected["ctc_person_satisfies_dependency_rules"] is True
    assert (
        subsection_h_projected["qualifying_child_ssn_is_valid_for_subsection_h"]
        is False
    )


def test_ctc_person_projection_treats_single_adult_as_tax_unit_head():
    projected = project_ctc_person_inputs({"age": 18, "ssn_card_type": "CITIZEN"})
    subsection_h_projected = project_ctc_h_person_inputs(
        {"age": 18, "ssn_card_type": "CITIZEN"}
    )

    assert projected["ctc_child_satisfies_dependency_rules"] is False
    assert projected["ctc_child_deduction_allowed"] is False
    assert subsection_h_projected["ctc_person_satisfies_dependency_rules"] is False


def test_tax_unit_person_contexts_project_head_spouse_and_dependents():
    contexts = project_tax_unit_person_contexts(
        [
            {"age": 42, "ssn_card_type": "CITIZEN"},
            {"age": 58, "ssn_card_type": "CITIZEN"},
            {"age": 24, "ssn_card_type": "CITIZEN"},
            {"age": 18, "ssn_card_type": "CITIZEN"},
            {"age": 15, "ssn_card_type": "CITIZEN"},
        ]
    )

    assert [context.is_head for context in contexts] == [
        False,
        True,
        False,
        False,
        False,
    ]
    assert [context.is_spouse for context in contexts] == [
        True,
        False,
        False,
        False,
        False,
    ]
    assert [context.is_tax_unit_dependent for context in contexts] == [
        False,
        False,
        True,
        True,
        True,
    ]
    assert [
        context.qualifying_child_described_in_subsection_c for context in contexts
    ] == [
        False,
        False,
        False,
        False,
        True,
    ]
    assert all(context.filer_has_valid_child_ctc_ssn for context in contexts)


def test_tax_unit_person_contexts_derive_adult_student_spouse_without_filing_status():
    contexts = project_tax_unit_person_contexts(
        [
            {
                "age": 43,
                "ssn_card_type": "CITIZEN",
                "is_household_head": True,
            },
            {
                "age": 20,
                "ssn_card_type": "CITIZEN",
                "is_full_time_college_student": True,
            },
            {
                "age": 15,
                "ssn_card_type": "CITIZEN",
            },
        ]
    )

    assert [context.is_head for context in contexts] == [True, False, False]
    assert [context.is_spouse for context in contexts] == [False, True, False]
    assert [context.is_tax_unit_dependent for context in contexts] == [
        False,
        False,
        True,
    ]
    assert [context.qualifying_child_under_section_152_c for context in contexts] == [
        False,
        False,
        True,
    ]


def test_tax_unit_person_contexts_handle_minor_only_tax_unit_without_filer_ssn():
    [context] = project_tax_unit_person_contexts(
        [{"age": 16, "ssn_card_type": "CITIZEN"}]
    )
    projected = project_ctc_h_person_inputs(
        {"age": 16, "ssn_card_type": "CITIZEN"}, context
    )

    assert context.is_tax_unit_dependent is True
    assert context.qualifying_child_described_in_subsection_c is True
    assert context.filer_has_valid_child_ctc_ssn is False
    assert projected["taxpayer_or_spouse_ssn_is_valid_for_subsection_h"] is False


@pytest.mark.parametrize("filing_status", ["JOINT", "SURVIVING_SPOUSE"])
def test_build_ctc_request_uses_refreshed_rulespec_input_contract(filing_status):
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "filing_status": filing_status,
                    "adjusted_gross_income": 125_000,
                }
            ]
        ),
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "person_tax_unit_id": 1,
                    "age": 39,
                    "ssn_card_type": "CITIZEN",
                },
                {
                    "person_id": 8,
                    "person_tax_unit_id": 1,
                    "age": 9,
                    "ssn_card_type": "CITIZEN",
                },
            ]
        ),
        "tax_unit_ids": [1],
    }

    request = build_ctc_request(pe_data=pe_data, year=2026)

    inputs = request["dataset"]["inputs"]
    input_names = {item["name"] for item in inputs}
    input_values = {
        (item["name"], item["entity_id"]): item["value"]["value"] for item in inputs
    }
    tax_unit_id = "tax_unit_1"
    child_id = "tax_unit_1_person_1"
    assert input_values[(f"{CTC_H_BASE}#input.filing_status", tax_unit_id)] == 1
    assert (
        input_values[
            (
                f"{CTC_BASE}#input.ctc_phaseout_joint_threshold_applies",
                tax_unit_id,
            )
        ]
        is True
    )
    assert (
        input_values[(f"{CTC_BASE}#input.ctc_advance_payments_received", tax_unit_id)]
        == 0
    )
    assert (
        input_values[
            (f"{CTC_BASE}#input.ctc_child_satisfies_dependency_rules", child_id)
        ]
        is True
    )
    assert (
        input_values[(f"{CTC_BASE}#input.ctc_child_deduction_allowed", child_id)]
        is True
    )
    assert (
        input_values[
            (f"{CTC_H_BASE}#input.ctc_person_satisfies_dependency_rules", child_id)
        ]
        is True
    )
    assert (
        input_values[(f"{CTC_H_BASE}#input.ctc_child_satisfies_subsection_c", child_id)]
        is True
    )
    assert f"{CTC_BASE}#input.filing_status" not in input_names
    assert f"{CTC_H_BASE}#input.filing_status_is_joint_return" not in input_names
    assert (
        f"{CTC_BASE}#input.aggregate_advance_payments_under_section_7527A"
        not in input_names
    )
    assert f"{CTC_BASE}#input.qualifying_child_under_section_152_c" not in input_names
    assert f"{CTC_H_BASE}#input.dependent_under_section_152" not in input_names


def test_tax_unit_projection_uses_boundary_inputs_without_ctc_outputs():
    projected = project_tax_unit_inputs(
        {"adjusted_gross_income": 123_456, "filing_status": "HEAD_OF_HOUSEHOLD"}
    )

    assert projected["adjusted_gross_income"] == 123_456
    assert projected["ctc_phaseout_joint_threshold_applies"] is False
    assert projected["ctc_phaseout_separate_threshold_applies"] is False
    assert projected["ctc_subsection_h_special_rules_apply"] is True
    assert projected["ctc_advance_payments_received"] == 0
    assert "ctc_before_advance_payments" not in projected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SINGLE", True),
        ("HEAD_OF_HOUSEHOLD", True),
        ("JOINT", False),
        ("SEPARATE", False),
        ("SURVIVING_SPOUSE", False),
    ],
)
def test_unmarried_not_surviving_spouse_matches_standard_deduction_status(
    value, expected
):
    assert individual_is_unmarried_and_not_surviving_spouse(value) is expected


def test_additional_standard_deduction_count_uses_head_and_spouse_only():
    count = additional_standard_deduction_entitlement_count(
        [
            {"age": 68, "is_blind": True},
            {"age": 70, "is_blind": False},
            {"age": 80, "is_blind": True},
        ]
    )

    assert count == 3


def test_standard_deduction_projection_uses_leaf_age_and_blind_inputs():
    projected = project_standard_deduction_inputs(
        row={"filing_status": "HEAD_OF_HOUSEHOLD"},
        persons=[
            {"age": 66, "is_blind": True},
            {"age": 15, "is_blind": True},
        ],
    )

    assert projected["filing_status"] == 3
    assert projected["may_be_claimed_as_dependent_by_another_taxpayer"] is False
    assert projected["earned_income"] == 0
    assert (
        projected["additional_standard_deduction_entitlement_count_under_subsection_f"]
        == 2
    )
    assert "individual_is_unmarried_and_not_surviving_spouse" not in projected


def test_capital_gain_definition_projection_uses_ecps_leaf_inputs():
    projected = project_capital_gain_definition_inputs(
        row={"unrecaptured_section_1250_gain": 600},
        persons=[
            {
                "long_term_capital_gains_before_response": 10_000,
                "short_term_capital_gains": -1_500,
                "qualified_dividend_income": 2_000,
                "investment_income_elected_form_4952": 250,
                "long_term_capital_gains_on_collectibles": 700,
            },
            {
                "long_term_capital_gains_before_response": 3_000,
                "short_term_capital_gains": 500,
                "qualified_dividend_income": 400,
                "investment_income_elected_form_4952": 50,
                "long_term_capital_gains_on_small_business_stock": 100,
            },
        ],
    )

    assert projected == {
        "long_term_capital_gains": 13_000,
        "short_term_capital_gains": -1_000,
        "qualified_dividend_income": 2_400,
        "net_capital_gain_taken_into_account_as_investment_income_under_section_163_d_4_B_iii": 300,
        "unrecaptured_section_1250_gain": 600,
        "capital_gains_28_percent_rate_gain": 800,
    }


def test_eitc_projection_uses_ecps_income_and_demographic_inputs():
    row = {
        "filing_status": "HEAD_OF_HOUSEHOLD",
        "adjusted_gross_income": 22_000,
        "unrecaptured_section_1250_gain": 0,
    }
    persons = [
        {
            "age": 34,
            "ssn_card_type": "CITIZEN",
            "employment_income_before_lsr": 18_000,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 0,
            "taxable_interest_income": 40,
            "tax_exempt_interest_income": 20,
            "qualified_dividend_income": 100,
            "non_qualified_dividend_income": 50,
            "rental_income": 0,
            "long_term_capital_gains_before_response": 400,
            "short_term_capital_gains": -100,
        },
        {
            "age": 8,
            "ssn_card_type": "CITIZEN",
            "is_full_time_college_student": False,
            "employment_income_before_lsr": 0,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 0,
        },
    ]

    projected = project_eitc_tax_unit_inputs(row=row, persons=persons)

    assert projected["filing_status"] == 3
    assert "earned_income" not in projected
    assert projected["adjusted_gross_income"] == 22_000
    assert projected["eitc_relevant_investment_income"] == 510
    assert projected["childless_taxpayer_or_spouse_age_eligible_for_eitc"] is True
    assert (
        projected["taxpayer_includes_required_social_security_number_on_return"] is True
    )
    assert "taxpayer_is_married_under_section_7703_a" not in projected
    assert project_section_7703_tax_unit_inputs(row=row) == {
        "spouse_dies_during_taxable_year": False,
        "taxpayer_married_at_time_of_spouse_death": False,
        "taxpayer_married_at_close_of_taxable_year": False,
        "legally_separated_under_decree_of_divorce_or_separate_maintenance": False,
        "taxpayer_files_separate_return": False,
        "taxpayer_maintains_household_as_home": False,
        "taxpayer_household_cost_fraction_furnished": 0,
        "spouse_not_member_of_household_final_month_count": 0,
    }

    contexts = project_tax_unit_person_contexts(persons)
    earned_income_inputs = project_section_32_c_2_tax_unit_inputs(
        persons=persons,
        contexts=contexts,
    )
    self_employment_inputs = project_section_1402_a_tax_unit_inputs(
        persons=persons,
        contexts=contexts,
    )
    assert earned_income_inputs == {
        "employee_compensation_includible_in_gross_income": 18_000,
            "net_earnings_from_self_employment_after_self_employment_tax_deduction": 0.0,
        "pension_or_annuity_amount": 0,
        "nonresident_alien_income_not_connected_with_united_states_business": 0,
        "penal_institution_service_compensation": 0,
        "subsidized_state_work_activity_service_compensation": 0,
        "taxpayer_elects_to_treat_section_112_excluded_amounts_as_earned_income": False,
    }
    assert (
        project_section_112_tax_unit_inputs()[
            "active_service_compensation_as_enlisted_member_excluding_pensions_and_retirement_pay"
        ]
        == 0
    )
    assert self_employment_inputs == {
        "net_earnings_from_self_employment": 0.0,
        "net_earnings_from_self_employment_for_paragraph_2_threshold_test": 0.0,
    }


def test_eitc_projection_matches_policyengine_age_and_identification_edges():
    row = {
        "filing_status": "SEPARATE",
        "adjusted_gross_income": -15_000,
    }
    persons = [
        {
            "age": 66,
            "ssn_card_type": "CITIZEN",
            "is_tax_unit_head": True,
            "is_tax_unit_spouse": False,
            "is_tax_unit_head_or_spouse": True,
            "is_separated": True,
            "employment_income_before_lsr": 0,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 0,
        },
        {
            "age": 34,
            "ssn_card_type": "CITIZEN",
            "is_tax_unit_head": False,
            "is_tax_unit_spouse": False,
            "is_tax_unit_head_or_spouse": False,
            "employment_income_before_lsr": 22_000,
            "self_employment_income_before_lsr": 5_000,
            "sstb_self_employment_income_before_lsr": 0,
        },
    ]

    projected = project_eitc_tax_unit_inputs(row=row, persons=persons)
    contexts = project_tax_unit_person_contexts(persons)

    assert projected["childless_taxpayer_or_spouse_age_eligible_for_eitc"] is True
    assert (
        projected["taxpayer_includes_required_social_security_number_on_return"] is True
    )
    assert (
        projected["spouse_includes_required_social_security_number_on_return"] is True
    )
    assert (
        project_section_7703_tax_unit_inputs(row=row)[
            "taxpayer_married_at_close_of_taxable_year"
        ]
        is True
    )
    assert (
        project_section_7703_tax_unit_inputs(row=row)["taxpayer_files_separate_return"]
        is True
    )
    assert (
        project_section_32_c_2_tax_unit_inputs(
            persons=persons,
            contexts=contexts,
        )[
            "employee_compensation_includible_in_gross_income"
        ]
        == 0
    )


def test_eitc_projection_treats_tax_units_without_explicit_filers_as_id_eligible():
    row = {
        "filing_status": "HEAD_OF_HOUSEHOLD",
        "adjusted_gross_income": 0,
    }
    persons = [
        {
            "age": 16,
            "ssn_card_type": "CITIZEN",
            "is_tax_unit_head": False,
            "is_tax_unit_spouse": False,
            "is_tax_unit_head_or_spouse": False,
            "employment_income_before_lsr": 0,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 0,
        }
    ]

    projected = project_eitc_tax_unit_inputs(row=row, persons=persons)
    context = project_tax_unit_person_contexts(persons)[0]

    assert (
        projected["taxpayer_includes_required_social_security_number_on_return"] is True
    )
    assert (
        projected["spouse_includes_required_social_security_number_on_return"] is True
    )
    assert context.is_tax_unit_dependent is True
    assert context.qualifying_child_under_section_152_c is True


def test_eitc_projection_sends_self_employment_to_section_1402_not_earned_income():
    row = {"filing_status": "SINGLE"}
    persons = [
        {
            "age": 34,
            "ssn_card_type": "CITIZEN",
            "employment_income_before_lsr": 18_000,
            "self_employment_income_before_lsr": 2_500,
            "sstb_self_employment_income_before_lsr": 0,
            "farm_operations_income": 300,
            "partnership_se_income": 450,
        },
        {
            "age": 35,
            "ssn_card_type": "CITIZEN",
            "employment_income_before_lsr": 5_000,
            "self_employment_income_before_lsr": 0,
            "sstb_self_employment_income_before_lsr": 750,
            "farm_operations_income": 0,
            "partnership_se_income": -50,
        },
        {
            "age": 8,
            "ssn_card_type": "CITIZEN",
            "employment_income_before_lsr": 1_000,
            "self_employment_income_before_lsr": 9_999,
            "sstb_self_employment_income_before_lsr": 9_999,
            "farm_operations_income": 9_999,
            "partnership_se_income": 9_999,
        },
    ]
    contexts = project_tax_unit_person_contexts(persons)

    assert project_section_32_c_2_tax_unit_inputs(
        persons=persons,
        contexts=contexts,
    ) == {
        "employee_compensation_includible_in_gross_income": 23_000,
            "net_earnings_from_self_employment_after_self_employment_tax_deduction": (
                3_647.825
            ),
        "pension_or_annuity_amount": 0,
        "nonresident_alien_income_not_connected_with_united_states_business": 0,
        "penal_institution_service_compensation": 0,
        "subsidized_state_work_activity_service_compensation": 0,
        "taxpayer_elects_to_treat_section_112_excluded_amounts_as_earned_income": False,
    }
    assert project_section_1402_a_tax_unit_inputs(
        persons=persons,
        contexts=contexts,
    ) == {
        "net_earnings_from_self_employment": 3_647.825,
        "net_earnings_from_self_employment_for_paragraph_2_threshold_test": (
            3_647.825
        ),
    }
    assert project_section_164_f_tax_unit_inputs() == {
        "taxpayer_is_individual": True,
    }
    assert project_section_1402_b_tax_unit_inputs(
        persons=persons,
        contexts=contexts,
        contribution_base=184_500,
    ) == {
        "individual_is_nonresident_alien": False,
        "agreement_under_social_security_act_section_233_provides_for_individual": False,
        "individual_is_not_united_states_citizen_and_resident_of_puerto_rico_virgin_islands_guam_or_american_samoa": False,
        "contribution_and_benefit_base_effective_for_calendar_year_in_which_taxable_year_begins": 184_500.0,
        "wages_paid_to_individual_during_taxable_year_for_section_1401_a": 23_000,
    }
    assert project_section_1401_tax_unit_inputs(
        row=row,
        persons=persons,
        contexts=contexts,
    ) == {
        "international_social_security_agreement_under_section_233_in_effect": False,
        "filing_status": 0,
        "wages_taken_into_account_for_additional_medicare_tax": 0,
    }


def test_eitc_person_projection_marks_valid_minor_child():
    [head_context, child_context] = project_tax_unit_person_contexts(
        [
            {"age": 34, "ssn_card_type": "CITIZEN"},
            {
                "age": 8,
                "ssn_card_type": "CITIZEN",
                "is_full_time_college_student": False,
            },
        ]
    )

    projected = project_eitc_person_inputs(
        {
            "age": 8,
            "ssn_card_type": "CITIZEN",
            "is_full_time_college_student": False,
        },
        child_context,
    )

    assert head_context.is_head is True
    assert projected == {
        "qualifying_child_principal_place_of_abode_is_in_united_states": True,
        "qualifying_child_name_age_and_tin_included_on_return": True,
        "qualifying_child_marital_status_requires_section_151_entitlement": False,
        "taxpayer_entitled_to_section_151_deduction_for_child_or_would_be_but_for_section_152_e": True,
    }


def test_section_152_c_projection_uses_leaf_child_facts():
    [_head_context, child_context] = project_tax_unit_person_contexts(
        [
            {"age": 34, "ssn_card_type": "CITIZEN", "is_separated": True},
            {
                "age": 20,
                "ssn_card_type": "CITIZEN",
                "is_full_time_college_student": True,
            },
        ]
    )

    projected = project_section_152_c_person_inputs(
        {
            "age": 20,
            "ssn_card_type": "CITIZEN",
            "is_full_time_college_student": True,
        },
        child_context,
    )

    assert (
        projected["individual_is_child_of_taxpayer_or_descendant_of_such_child"] is True
    )
    assert projected["individual_principal_place_of_abode_with_taxpayer_fraction"] == 1
    assert projected["individual_is_younger_than_taxpayer"] is True
    assert projected["individual_age_at_close_of_calendar_year"] == 20
    assert projected["individual_is_student"] is True
    assert projected["individual_own_support_fraction_provided_by_individual"] == 0
    assert projected["filing_status"] == 0
    assert projected["return_filed_only_for_claim_of_refund"] is False
    assert projected["parents_filing_status"] == 1
    assert (
        projected[
            "individual_may_be_claimed_as_qualifying_child_by_two_or_more_taxpayers"
        ]
        is False
    )


def test_eitc_relevant_investment_income_replaces_limited_loss_with_nonnegative_gain():
    assert (
        project_eitc_relevant_investment_income(
            row={"filing_status": "SINGLE"},
            persons=[
                {
                    "taxable_interest_income": 10,
                    "tax_exempt_interest_income": 20,
                    "qualified_dividend_income": 30,
                    "non_qualified_dividend_income": 40,
                    "rental_income": 50,
                    "long_term_capital_gains_before_response": -1_000,
                    "short_term_capital_gains": 200,
                }
            ],
        )
        == 150
    )


def test_build_eitc_request_uses_structural_child_relation_and_component_outputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "filing_status": "HEAD_OF_HOUSEHOLD",
                    "adjusted_gross_income": 22_000,
                    "unrecaptured_section_1250_gain": 0,
                    "eitc_child_count": 1,
                    "eitc_phase_in_rate": 0.34,
                    "eitc_phase_out_rate": 0.1598,
                    "eitc_maximum": 4_427,
                    "eitc_phase_out_start": 23_890,
                    "eitc_phased_in": 4_427,
                    "eitc_reduction": 0,
                    "eitc_investment_income_eligible": True,
                    "eitc_demographic_eligible": True,
                    "eitc_eligible": True,
                }
            ]
        ),
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "person_tax_unit_id": 1,
                    "age": 34,
                    "ssn_card_type": "CITIZEN",
                    "employment_income_before_lsr": 18_000,
                    "self_employment_income_before_lsr": 0,
                    "sstb_self_employment_income_before_lsr": 0,
                },
                {
                    "person_id": 8,
                    "person_tax_unit_id": 1,
                    "age": 8,
                    "ssn_card_type": "CITIZEN",
                    "is_full_time_college_student": False,
                    "employment_income_before_lsr": 0,
                    "self_employment_income_before_lsr": 0,
                    "sstb_self_employment_income_before_lsr": 0,
                },
            ]
        ),
        "tax_unit_ids": [1],
        "person_ids": [7, 8],
    }

    request = build_eitc_request(
        pe_data=pe_data,
        year=2026,
        contribution_base=184_500.0,
    )

    assert request["queries"] == [
        {
            "entity_id": "tax_unit_1",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [spec["axiom"] for spec in EITC_OUTPUTS.values()],
        }
    ]
    assert request["dataset"]["relations"] == [
        {
            "name": f"{EITC_BASE}#relation.qualifying_child_of_tax_unit",
            "tuple": ["tax_unit_1_person_0", "tax_unit_1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
        {
            "name": f"{EITC_BASE}#relation.qualifying_child_of_tax_unit",
            "tuple": ["tax_unit_1_person_1", "tax_unit_1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
    ]
    input_values = {
        item["name"]: item["value"]["value"] for item in request["dataset"]["inputs"]
    }
    assert f"{EITC_BASE}#input.earned_income" not in input_values
    assert (
        f"{SECTION_32_C_2_BASE}#input.section_112_amounts_excluded_from_gross_income"
        not in input_values
    )
    assert (
        input_values[
            f"{SECTION_32_C_2_BASE}#input.employee_compensation_includible_in_gross_income"
        ]
        == "18000.0"
    )
    assert (
        input_values[
            f"{SECTION_112_BASE}#input.active_service_compensation_as_enlisted_member_excluding_pensions_and_retirement_pay"
        ]
        == 0
    )
    # The EITC program no longer imports the 1402/164(f)/1401 SECA chain;
    # its earned income grounds in the 32(c)(2) net-earnings input.
    assert not any("statutes/26/1402" in key for key in input_values)
    assert not any("statutes/26/164/f" in key for key in input_values)
    assert not any("statutes/26/1401#" in key for key in input_values)
    assert (
        input_values[
            f"{SECTION_7703_BASE}#input.taxpayer_married_at_close_of_taxable_year"
        ]
        is False
    )
    assert f"{SECTION_1401_BASE}#input.self_employment_income" not in input_values
    assert (
        input_values[
            f"{SECTION_152_C_BASE}#input.individual_is_child_of_taxpayer_or_descendant_of_such_child"
        ]
        is True
    )
    assert (
        input_values[
            f"{EITC_BASE}#input.qualifying_child_name_age_and_tin_included_on_return"
        ]
        is True
    )


def test_build_capital_gain_definitions_request_uses_raw_person_capital_gains():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "unrecaptured_section_1250_gain": 600,
                    "net_capital_gain": 11_000,
                    "adjusted_net_capital_gain": 10_200,
                }
            ]
        ),
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "person_tax_unit_id": 1,
                    "long_term_capital_gains_before_response": 10_000,
                    "short_term_capital_gains": -1_500,
                    "qualified_dividend_income": 2_000,
                    "investment_income_elected_form_4952": 0,
                    "long_term_capital_gains_on_collectibles": 800,
                }
            ]
        ),
        "tax_unit_ids": [1],
        "person_ids": [7],
    }

    request = build_capital_gain_definitions_request(pe_data=pe_data, year=2026)

    assert request["queries"] == [
        {
            "entity_id": "tax_unit_1",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [
                spec["axiom"] for spec in CAPITAL_GAINS_DEFINITION_OUTPUTS.values()
            ],
        }
    ]
    input_values = {
        item["name"]: item["value"]["value"] for item in request["dataset"]["inputs"]
    }
    assert input_values[f"{CAPITAL_GAINS_BASE}#input.long_term_capital_gains"] == (
        "10000.0"
    )
    assert input_values[f"{CAPITAL_GAINS_BASE}#input.short_term_capital_gains"] == (
        "-1500.0"
    )
    assert (
        input_values[f"{CAPITAL_GAINS_BASE}#input.unrecaptured_section_1250_gain"]
        == "600.0"
    )
    assert (
        input_values[f"{CAPITAL_GAINS_BASE}#input.capital_gains_28_percent_rate_gain"]
        == "800.0"
    )


def test_build_tax_before_credits_request_projects_section_1j_and_1h_inputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 3,
                    "filing_status": "JOINT",
                    "taxable_income": 125_000,
                    "long_term_capital_gains": 2_500,
                    "short_term_capital_gains": 750,
                    "qualified_dividend_income": 400,
                    "unrecaptured_section_1250_gain": 125,
                    "capital_gains_28_percent_rate_gain": 300,
                }
            ]
        ),
        "persons": pd.DataFrame(
            [
                {"person_id": 10, "tax_unit_id": 3},
                {
                    "person_id": 11,
                    "tax_unit_id": 3,
                    "long_term_capital_gains": 2_000,
                    "short_term_capital_gains": 250,
                },
            ]
        ),
        "tax_unit_ids": [3],
    }

    request = build_tax_before_credits_request(pe_data=pe_data, year=2026)

    input_values = {
        item["name"]: item["value"]["value"] for item in request["dataset"]["inputs"]
    }
    assert input_values[f"{TAX_BEFORE_CREDITS_BASE}#input.filing_status"] == 1
    assert input_values[f"{TAX_BEFORE_CREDITS_BASE}#input.taxable_income"] == (
        "125000.0"
    )
    assert input_values[f"{CAPITAL_GAINS_BASE}#input.filing_status"] == 1
    assert input_values[f"{CAPITAL_GAINS_BASE}#input.taxable_income"] == "125000.0"
    assert input_values[f"{CAPITAL_GAINS_BASE}#input.long_term_capital_gains"] == (
        "2000.0"
    )
    assert request["queries"][0]["outputs"] == [
        spec["axiom"] for spec in TAX_BEFORE_CREDITS_OUTPUTS.values()
    ]


def test_project_cdcc_tax_unit_inputs_declares_upstream_boundaries():
    projected = project_cdcc_tax_unit_inputs(
        row={
            "filing_status": "JOINT",
            "adjusted_gross_income": 80_000,
            "min_head_spouse_earned": 50_000,
            "tax_unit_childcare_expenses": 4_000,
            "cdcc_credit_limit": 2_000,
        }
    )

    assert projected["filing_status"] == 1
    assert projected["married_at_close_of_taxable_year"] is True
    assert projected["employment_related_expense_requirements_satisfied"] is True
    assert projected["employment_related_expenses_paid"] == 4_000
    assert projected["taxpayer_earned_income_for_cdcc"] == 50_000
    assert projected["spouse_earned_income_for_cdcc"] == 50_000
    assert projected["tax_imposed_by_chapter_before_cdcc"] == 2_000


def test_project_cdcc_person_inputs_marks_child_and_disabled_paths():
    child_context = project_tax_unit_person_contexts(
        [
            {"age": 38, "is_tax_unit_head": True, "is_tax_unit_spouse": False},
            {"age": 9, "is_tax_unit_head": False, "is_tax_unit_spouse": False},
        ]
    )[1]
    disabled_spouse_context = project_tax_unit_person_contexts(
        [
            {"age": 38, "is_tax_unit_head": True, "is_tax_unit_spouse": False},
            {"age": 35, "is_tax_unit_head": False, "is_tax_unit_spouse": True},
        ]
    )[1]

    child_inputs = project_cdcc_person_inputs(
        {"age": 9, "is_incapable_of_self_care": False},
        child_context,
    )
    disabled_spouse_inputs = project_cdcc_person_inputs(
        {"age": 35, "is_incapable_of_self_care": True},
        disabled_spouse_context,
    )

    assert child_inputs["is_cdcc_child_dependent"] is True
    assert child_inputs["age"] == 9
    assert disabled_spouse_inputs["is_spouse_of_taxpayer"] is True
    assert (
        disabled_spouse_inputs["physically_or_mentally_incapable_of_self_care"] is True
    )


def test_build_cdcc_request_uses_person_to_tax_unit_relation_and_outputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "filing_status": "JOINT",
                    "adjusted_gross_income": 80_000,
                    "min_head_spouse_earned": 50_000,
                    "tax_unit_childcare_expenses": 4_000,
                    "cdcc_credit_limit": 2_000,
                }
            ]
        ),
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "person_tax_unit_id": 1,
                    "age": 38,
                    "is_tax_unit_head": True,
                    "is_tax_unit_spouse": False,
                    "is_incapable_of_self_care": False,
                },
                {
                    "person_id": 8,
                    "person_tax_unit_id": 1,
                    "age": 9,
                    "is_tax_unit_head": False,
                    "is_tax_unit_spouse": False,
                    "is_incapable_of_self_care": False,
                },
            ]
        ),
        "tax_unit_ids": [1],
    }

    request = build_cdcc_request(pe_data=pe_data, year=2026)

    assert request["queries"] == [
        {
            "entity_id": "tax_unit_1",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [spec["axiom"] for spec in CDCC_OUTPUTS.values()],
        }
    ]
    assert request["dataset"]["relations"] == [
        {
            "name": f"{CDCC_BASE}#relation.qualifying_individual_of_tax_unit",
            "tuple": ["tax_unit_1_person_0", "tax_unit_1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
        {
            "name": f"{CDCC_BASE}#relation.qualifying_individual_of_tax_unit",
            "tuple": ["tax_unit_1_person_1", "tax_unit_1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
    ]
    input_values = {
        (item["name"], item["entity_id"]): item["value"]["value"]
        for item in request["dataset"]["inputs"]
    }
    assert (
        input_values[
            (
                f"{CDCC_BASE}#input.employment_related_expenses_paid",
                "tax_unit_1",
            )
        ]
        == "4000.0"
    )
    assert (
        input_values[
            (
                f"{CDCC_BASE}#input.tax_imposed_by_chapter_before_cdcc",
                "tax_unit_1",
            )
        ]
        == "2000.0"
    )
    assert (
        input_values[
            (f"{CDCC_BASE}#input.is_cdcc_child_dependent", "tax_unit_1_person_1")
        ]
        is True
    )


def test_project_aotc_tax_unit_inputs_declares_credit_boundaries():
    projected = project_aotc_tax_unit_inputs(
        row={
            "filing_status": "HEAD_OF_HOUSEHOLD",
            "adjusted_gross_income": 68_000,
            "income_tax_before_credits": 4_200,
            "foreign_tax_credit": 100,
            "cdcc": 750,
        }
    )

    assert projected == {
        "filing_status": 3,
        "modified_adjusted_gross_income": 68_000,
        "is_nonresident_alien": False,
        "section_6013_resident_alien_election": False,
        "taxpayer_is_section_1_g_child": False,
        "income_tax_before_credits": 4_200,
        "foreign_tax_credit": 100,
        "cdcc": 750,
    }


def test_project_aotc_person_inputs_uses_ecps_education_leaves():
    context = project_tax_unit_person_contexts(
        [
            {
                "age": 42,
                "is_tax_unit_head": True,
                "is_tax_unit_spouse": False,
                "ssn_card_type": "CITIZEN",
            },
            {
                "age": 20,
                "is_tax_unit_head": False,
                "is_tax_unit_spouse": False,
                "ssn_card_type": "CITIZEN",
            },
        ]
    )[1]

    projected = project_aotc_person_inputs(
        {
            "qualified_tuition_expenses": 4_500,
            "educational_assistance": 500,
            "is_pursuing_credential_for_american_opportunity_credit": True,
            "attends_eligible_educational_institution_for_american_opportunity_credit": True,
            "is_enrolled_at_least_half_time_for_american_opportunity_credit": True,
            "american_opportunity_credit_claimed_prior_years": 1,
            "has_completed_first_four_years_of_postsecondary_education": False,
            "has_american_opportunity_credit_institution_ein": True,
            "has_american_opportunity_credit_1098_t_or_exception": True,
        },
        context,
    )

    assert projected["qualified_tuition_and_related_expenses"] == 4_500
    assert projected["excludable_educational_assistance"] == 0
    assert projected["is_tax_unit_dependent"] is True
    assert projected["meets_higher_education_act_student_requirements"] is True
    assert projected["at_least_half_time_student"] is True
    assert projected["aotc_prior_year_election_count"] == 1
    assert projected["education_credit_identification_requirements_met"] is True
    assert projected["institution_employer_identification_number_included"] is True
    assert projected["payee_statement_received"] is True
    assert projected["education_credit_election_in_effect"] is False


def test_build_aotc_request_uses_person_to_tax_unit_relation_and_outputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "filing_status": "JOINT",
                    "adjusted_gross_income": 80_000,
                    "income_tax_before_credits": 5_000,
                    "foreign_tax_credit": 0,
                    "cdcc": 600,
                }
            ]
        ),
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "person_tax_unit_id": 1,
                    "age": 44,
                    "is_tax_unit_head": True,
                    "is_tax_unit_spouse": False,
                    "ssn_card_type": "CITIZEN",
                    "qualified_tuition_expenses": 0,
                },
                {
                    "person_id": 8,
                    "person_tax_unit_id": 1,
                    "age": 20,
                    "is_tax_unit_head": False,
                    "is_tax_unit_spouse": False,
                    "ssn_card_type": "CITIZEN",
                    "qualified_tuition_expenses": 4_000,
                    "educational_assistance": 0,
                    "is_pursuing_credential_for_american_opportunity_credit": True,
                    "attends_eligible_educational_institution_for_american_opportunity_credit": True,
                    "is_enrolled_at_least_half_time_for_american_opportunity_credit": True,
                    "american_opportunity_credit_claimed_prior_years": 0,
                    "has_completed_first_four_years_of_postsecondary_education": False,
                    "has_american_opportunity_credit_institution_ein": True,
                    "has_american_opportunity_credit_1098_t_or_exception": True,
                },
            ]
        ),
        "tax_unit_ids": [1],
    }

    request = build_aotc_request(pe_data=pe_data, year=2026)

    assert request["queries"] == [
        {
            "entity_id": "tax_unit_1",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [spec["axiom"] for spec in AOTC_OUTPUTS.values()],
        }
    ]
    assert request["dataset"]["relations"] == [
        {
            "name": f"{AOTC_BASE}#relation.education_credit_member_of_tax_unit",
            "tuple": ["tax_unit_1_person_0", "tax_unit_1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
        {
            "name": f"{AOTC_BASE}#relation.education_credit_member_of_tax_unit",
            "tuple": ["tax_unit_1_person_1", "tax_unit_1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        },
    ]
    input_values = {
        (item["name"], item["entity_id"]): item["value"]["value"]
        for item in request["dataset"]["inputs"]
    }
    assert (
        input_values[
            (
                f"{AOTC_BASE}#input.income_tax_before_credits",
                "tax_unit_1",
            )
        ]
        == "5000.0"
    )
    assert (
        input_values[
            (
                f"{AOTC_BASE}#input.qualified_tuition_and_related_expenses",
                "tax_unit_1_person_1",
            )
        ]
        == "4000.0"
    )
    assert (
        input_values[
            (
                f"{AOTC_BASE}#input.meets_higher_education_act_student_requirements",
                "tax_unit_1_person_1",
            )
        ]
        is True
    )


def test_project_nonrefundable_credits_inputs_uses_credit_boundaries():
    projected = project_nonrefundable_credits_inputs(
        row={
            "foreign_tax_credit": 10,
            "cdcc": 20,
            "non_refundable_american_opportunity_credit": 30,
            "lifetime_learning_credit": 40,
            "savers_credit": 50,
            "residential_clean_energy_credit": 60,
            "energy_efficient_home_improvement_credit": 70,
            "elderly_disabled_credit": 80,
            "new_clean_vehicle_credit": 90,
            "used_clean_vehicle_credit": 100,
            "non_refundable_ctc": 110,
            "income_tax_before_credits": 500,
        }
    )

    assert projected == {
        "foreign_tax_credit": 10,
        "cdcc": 20,
        "non_refundable_american_opportunity_credit": 30,
        "lifetime_learning_credit": 40,
        "savers_credit": 50,
        "residential_clean_energy_credit": 60,
        "energy_efficient_home_improvement_credit": 70,
        "elderly_disabled_credit": 80,
        "new_clean_vehicle_credit": 90,
        "used_clean_vehicle_credit": 100,
        "non_refundable_ctc": 110,
        "income_tax_before_credits": 500,
    }


def test_build_nonrefundable_credits_request_uses_tax_unit_inputs_and_outputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "foreign_tax_credit": 10,
                    "cdcc": 20,
                    "non_refundable_american_opportunity_credit": 30,
                    "lifetime_learning_credit": 40,
                    "savers_credit": 50,
                    "residential_clean_energy_credit": 60,
                    "energy_efficient_home_improvement_credit": 70,
                    "elderly_disabled_credit": 80,
                    "new_clean_vehicle_credit": 90,
                    "used_clean_vehicle_credit": 100,
                    "non_refundable_ctc": 110,
                    "income_tax_before_credits": 500,
                }
            ]
        ),
        "persons": pd.DataFrame([]),
        "tax_unit_ids": [1],
    }

    request = build_nonrefundable_credits_request(pe_data=pe_data, year=2026)

    assert request["queries"] == [
        {
            "entity_id": "tax_unit_1",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [
                spec["axiom"] for spec in NONREFUNDABLE_CREDITS_OUTPUTS.values()
            ],
        }
    ]
    assert request["dataset"]["relations"] == []
    input_values = {
        (item["name"], item["entity_id"]): item["value"]["value"]
        for item in request["dataset"]["inputs"]
    }
    assert (
        input_values[
            (
                f"{NONREFUNDABLE_CREDITS_BASE}#input.savers_credit",
                "tax_unit_1",
            )
        ]
        == "50.0"
    )
    assert (
        input_values[
            (
                f"{NONREFUNDABLE_CREDITS_BASE}#input.income_tax_before_credits",
                "tax_unit_1",
            )
        ]
        == "500.0"
    )


def test_project_income_tax_inputs_uses_6401_boundaries():
    projected = project_income_tax_inputs(
        row={
            "income_tax_before_refundable_credits": 1_200,
            "income_tax_refundable_credits": 300,
        }
    )

    assert projected == {
        "credits_allowable_under_subpart_c_excluding_section_33_for_overpayment": 300,
        "nonresident_withholding_credit_treated_as_refundable_amount": 0.0,
        "tax_imposed_by_subtitle_a_reduced_by_subparts_a_b_d_and_g_credits": 1_200,
        "amount_paid_as_tax": 0.0,
        "no_tax_liability_in_respect_of_amount_paid": False,
    }


def test_build_income_tax_request_uses_tax_unit_inputs_and_outputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "tax_units": pd.DataFrame(
            [
                {
                    "tax_unit_id": 1,
                    "income_tax_before_refundable_credits": 1_200,
                    "income_tax_refundable_credits": 300,
                }
            ]
        ),
        "persons": pd.DataFrame([]),
        "tax_unit_ids": [1],
    }

    request = build_income_tax_request(pe_data=pe_data, year=2026)

    assert request["queries"] == [
        {
            "entity_id": "tax_unit_1",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [spec["axiom"] for spec in INCOME_TAX_OUTPUTS.values()],
        }
    ]
    assert request["dataset"]["relations"] == []
    input_values = {
        (item["name"], item["entity_id"]): item["value"]["value"]
        for item in request["dataset"]["inputs"]
    }
    assert (
        input_values[
            (
                f"{INCOME_TAX_BASE}#input."
                "credits_allowable_under_subpart_c_excluding_section_33_for_overpayment",
                "tax_unit_1",
            )
        ]
        == "300.0"
    )
    assert (
        input_values[
            (
                f"{INCOME_TAX_BASE}#input."
                "tax_imposed_by_subtitle_a_reduced_by_subparts_a_b_d_and_g_credits",
                "tax_unit_1",
            )
        ]
        == "1200.0"
    )


def test_within_tolerance_keeps_cent_level_strictness_for_ordinary_outputs():
    assert within_tolerance(
        1000.005,
        1000,
        absolute_tolerance=0.01,
        relative_tolerance=2e-7,
    )
    assert not within_tolerance(
        1000.02,
        1000,
        absolute_tolerance=0.01,
        relative_tolerance=2e-7,
    )


def test_within_tolerance_accepts_large_policyengine_float_noise():
    assert within_tolerance(
        1_271_556_450,
        1_271_556_352,
        absolute_tolerance=0.01,
        relative_tolerance=2e-7,
    )


def test_output_number_maps_axiom_judgments_to_boolean_numbers():
    assert output_number({"kind": "judgment", "outcome": "holds"}) == 1
    assert output_number({"kind": "judgment", "outcome": "not_holds"}) == 0


def test_tax_ecps_parser_documents_full_sample_size():
    parser = argparse.ArgumentParser()
    tax_populace.configure_parser(parser)

    sample_size_help = next(
        action.help for action in parser._actions if action.dest == "sample_size"
    )
    tax_unit_id_help = next(
        action.help for action in parser._actions if action.dest == "tax_unit_ids"
    )
    assert "0 compares all eligible tax units" in sample_size_help
    assert "bypasses --sample-size" in tax_unit_id_help


def test_select_tax_unit_indices_can_target_known_residuals():
    pd = pytest.importorskip("pandas")
    raw_tax_units = pd.DataFrame(
        [
            {"tax_unit_id": 10, "tax_unit_weight": 1},
            {"tax_unit_id": 2976, "tax_unit_weight": 1},
            {"tax_unit_id": 42, "tax_unit_weight": 0},
        ]
    )
    tax_units = pd.DataFrame(
        [
            {"ctc": 0},
            {"ctc": 10},
            {"ctc": 10},
        ]
    )

    indices = select_tax_unit_indices(
        raw_tax_units=raw_tax_units,
        tax_units=tax_units,
        sample_size=1,
        positive_ctc_only=False,
        tax_unit_ids=(2976,),
    )

    assert indices.tolist() == [1]


def test_resolve_rulespec_program_path_supports_country_monorepo_root(tmp_path):
    root = tmp_path / "rulespec-us"
    program = root / "us" / "statutes" / "26" / "1" / "j.yaml"
    program.parent.mkdir(parents=True)
    program.write_text("program: {}\n")

    assert (
        resolve_rulespec_program_path(root, TAX_BEFORE_CREDITS_PROGRAM_PATH) == program
    )


def test_resolve_rulespec_program_path_keeps_direct_layout(tmp_path):
    root = tmp_path / "rulespec-us"
    program = root / "statutes" / "26" / "1" / "j.yaml"
    program.parent.mkdir(parents=True)
    program.write_text("program: {}\n")

    assert (
        resolve_rulespec_program_path(root, TAX_BEFORE_CREDITS_PROGRAM_PATH) == program
    )


def test_select_tax_unit_indices_rejects_filtered_requested_case():
    pd = pytest.importorskip("pandas")
    raw_tax_units = pd.DataFrame(
        [
            {"tax_unit_id": 2976, "tax_unit_weight": 1},
        ]
    )
    tax_units = pd.DataFrame([{"ctc": 0}])

    with pytest.raises(SystemExit, match="not eligible"):
        select_tax_unit_indices(
            raw_tax_units=raw_tax_units,
            tax_units=tax_units,
            sample_size=0,
            positive_ctc_only=True,
            tax_unit_ids=(2976,),
        )


def test_select_tax_unit_indices_uses_household_weights_when_tax_unit_weight_absent():
    pd = pytest.importorskip("pandas")
    raw_tax_units = pd.DataFrame(
        [
            {"tax_unit_id": 10},
            {"tax_unit_id": 20},
            {"tax_unit_id": 30},
        ]
    )
    raw_persons = pd.DataFrame(
        [
            {"person_tax_unit_id": 10, "person_household_id": 1},
            {"person_tax_unit_id": 20, "person_household_id": 2},
            {"person_tax_unit_id": 30, "person_household_id": 3},
        ]
    )
    raw_households = pd.DataFrame(
        [
            {"household_id": 1, "household_weight": 4.5},
            {"household_id": 2, "household_weight": 0},
            {"household_id": 3, "household_weight": 12},
        ]
    )
    tax_units = pd.DataFrame([{"ctc": 0}, {"ctc": 0}, {"ctc": 0}])

    indices = select_tax_unit_indices(
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        raw_households=raw_households,
        tax_units=tax_units,
        sample_size=0,
        positive_ctc_only=False,
    )

    assert indices.tolist() == [0, 2]


def test_select_tax_unit_indices_rejects_zero_household_weight_requested_case():
    pd = pytest.importorskip("pandas")
    raw_tax_units = pd.DataFrame([{"tax_unit_id": 20}])
    raw_persons = pd.DataFrame([{"person_tax_unit_id": 20, "person_household_id": 2}])
    raw_households = pd.DataFrame([{"household_id": 2, "household_weight": 0}])
    tax_units = pd.DataFrame([{"ctc": 10}])

    with pytest.raises(SystemExit, match="not eligible"):
        select_tax_unit_indices(
            raw_tax_units=raw_tax_units,
            raw_persons=raw_persons,
            raw_households=raw_households,
            tax_units=tax_units,
            sample_size=0,
            positive_ctc_only=False,
            tax_unit_ids=(20,),
        )


def test_tax_unit_positive_weight_mask_requires_person_household_tables():
    pd = pytest.importorskip("pandas")
    raw_tax_units = pd.DataFrame([{"tax_unit_id": 20}])

    with pytest.raises(SystemExit, match="provide person and household tables"):
        tax_unit_positive_weight_mask(raw_tax_units=raw_tax_units)


def test_compare_outputs_reports_max_relative_diff_for_large_float_noise():
    pd = pytest.importorskip("pandas")
    report = tax_populace.compare_outputs(
        pe_data={
            "tax_units": pd.DataFrame(
                [
                    {
                        "tax_unit_id": 1,
                        "net_capital_gain": 1_271_556_352,
                        "adjusted_net_capital_gain": 1_000,
                    }
                ]
            ),
            "persons": pd.DataFrame([]),
            "tax_unit_ids": [1],
            "person_ids": [],
        },
        axiom_outputs_by_surface={
            "capital-gain-definitions": [
                {
                    "outputs": {
                        f"{CAPITAL_GAINS_BASE}#net_capital_gain": {
                            "value": {"value": "1271556450"}
                        },
                        f"{CAPITAL_GAINS_BASE}#adjusted_net_capital_gain": {
                            "value": {"value": "1000"}
                        },
                    }
                }
            ],
        },
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    net_capital_gain_summary = next(
        item for item in report.output_summary if item["output"] == "net_capital_gain"
    )
    assert net_capital_gain_summary["max_abs_diff"] == 98
    assert net_capital_gain_summary["max_relative_diff"] == pytest.approx(
        7.7070922918813e-8
    )


def test_build_contribution_and_benefit_base_request_queries_encoded_ssa_policy():
    request = build_contribution_and_benefit_base_request(year=2026)

    assert request == {
        "mode": "explain",
        "dataset": {"inputs": [], "relations": []},
        "queries": [
            {
                "entity_id": "tax_year_2026",
                "period": {
                    "period_kind": "tax_year",
                    "start": "2026-01-01",
                    "end": "2026-12-31",
                },
                "outputs": [contribution_and_benefit_base_output(2026)],
            }
        ],
    }


def test_build_contribution_and_benefit_base_request_accepts_selected_output():
    output = "us:policies/ssa/contribution-and-benefit-base/2024#contribution_and_benefit_base"

    request = build_contribution_and_benefit_base_request(year=2024, output=output)

    assert request["queries"][0]["outputs"] == [output]


def test_contribution_and_benefit_base_output_for_program_prefers_section_230(
    tmp_path,
):
    program = tmp_path / "2026.yaml"
    program.write_text(
        """format: rulespec/v1
rules:
  - name: contribution_and_benefit_base
    kind: parameter
  - name: contribution_and_benefit_base_under_section_230_of_social_security_act
    kind: parameter
"""
    )

    assert contribution_and_benefit_base_output_for_program(program, year=2026) == (
        "us:policies/ssa/contribution-and-benefit-base/2026"
        "#contribution_and_benefit_base_under_section_230_of_social_security_act"
    )


def test_contribution_and_benefit_base_output_for_program_accepts_simple_base(
    tmp_path,
):
    program = tmp_path / "2024.yaml"
    program.write_text(
        """format: rulespec/v1
rules:
  - name: contribution_and_benefit_base
    kind: parameter
"""
    )

    assert (
        contribution_and_benefit_base_output_for_program(program, year=2024)
        == "us:policies/ssa/contribution-and-benefit-base/2024#contribution_and_benefit_base"
    )


def test_contribution_and_benefit_base_comes_from_axiom_results():
    output = contribution_and_benefit_base_output(2026)
    results = [
        {
            "outputs": {
                output: {
                    "kind": "scalar",
                    "value": {"kind": "decimal", "value": "184500"},
                }
            }
        }
    ]

    assert (
        contribution_and_benefit_base_from_results(
            results,
            year=2026,
        )
        == 184_500
    )


def test_contribution_and_benefit_base_comes_from_selected_axiom_result():
    output = "us:policies/ssa/contribution-and-benefit-base/2024#contribution_and_benefit_base"
    results = [
        {
            "outputs": {
                output: {
                    "kind": "scalar",
                    "value": {"kind": "decimal", "value": "168600"},
                }
            }
        }
    ]

    assert (
        contribution_and_benefit_base_from_results(
            results,
            year=2024,
            output=output,
        )
        == 168_600
    )


def test_contribution_and_benefit_base_can_come_from_rulespec_test(tmp_path):
    test_path = tmp_path / contribution_and_benefit_base_program_path(2024).with_suffix(
        ".test.yaml"
    )
    test_path.parent.mkdir(parents=True)
    output = "us:policies/ssa/contribution-and-benefit-base/2024#contribution_and_benefit_base"
    test_path.write_text(
        f"""- name: base_for_2024
  period:
    period_kind: custom
    name: calendar_year
    start: '2024-01-01'
    end: '2024-12-31'
  input: {{}}
  output:
    {output}: "$168,600"
"""
    )

    assert (
        contribution_and_benefit_base_from_rulespec_test(
            tmp_path,
            year=2024,
            output=output,
        )
        == 168_600
    )


def test_contribution_and_benefit_base_requires_axiom_result():
    with pytest.raises(ValueError, match="contribution-and-benefit-base output"):
        contribution_and_benefit_base_from_results([], year=2026)


def test_fica_wage_projection_does_not_subtract_retirement_deferrals():
    projected = project_fica_wages(
        {
            "employment_income_before_lsr": 106_706,
            "traditional_401k_contributions": 6_006,
            "traditional_403b_contributions": 1_000,
            "pre_tax_health_insurance_premiums": 5_606,
            "health_savings_account_payroll_contributions": 6_750,
            "payroll_tax_gross_wages": 94_344,
        }
    )

    assert projected == 94_350


def test_fica_wage_projection_prefers_policyengine_employment_income():
    projected = project_fica_wages(
        {
            "employment_income": 100_000,
            "employment_income_before_lsr": 110_000,
            "pre_tax_health_insurance_premiums": 5_000,
        }
    )

    assert projected == 95_000


def test_fica_wage_projection_does_not_double_subtract_payroll_wage_fallback():
    projected = project_fica_wages(
        {
            "payroll_tax_gross_wages": 94_350,
            "pre_tax_health_insurance_premiums": 5_606,
            "health_savings_account_payroll_contributions": 6_750,
        }
    )

    assert projected == 94_350


def test_fica_wage_projection_falls_back_to_payroll_wages_for_unit_fixtures():
    assert project_fica_wages({"payroll_tax_gross_wages": 80_000}) == 80_000


def test_fica_wage_projection_skips_missing_gross_income_leaves():
    np = pytest.importorskip("numpy")

    assert (
        project_fica_wages(
            {
                "employment_income_before_lsr": np.nan,
                "employment_income": 100_000,
                "pre_tax_health_insurance_premiums": 2_000,
            }
        )
        == 98_000
    )


def test_oasdi_wage_base_projection_uses_gross_wages_and_official_base():
    projected = project_oasdi_wage_base_inputs(
        {"payroll_tax_gross_wages": 200_000},
        contribution_base=184_500,
    )

    assert (
        projected[
            "contribution_and_benefit_base_under_section_230_of_social_security_act"
        ]
        == 184_500
    )
    assert (
        projected[
            "remuneration_paid_to_individual_by_employer_with_respect_to_employment"
        ]
        == 200_000
    )
    assert (
        projected[
            "remuneration_other_than_succeeding_paragraphs_paid_to_individual_by_employer_during_calendar_year_before_payment"
        ]
        == 0
    )


def test_build_oasdi_wage_base_request_uses_3121_inputs():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "employment_income_before_lsr": 106_706,
                    "traditional_401k_contributions": 6_006,
                    "traditional_403b_contributions": 1_000,
                    "pre_tax_health_insurance_premiums": 5_606,
                    "health_savings_account_payroll_contributions": 6_750,
                    "payroll_tax_gross_wages": 94_344,
                }
            ]
        ),
        "person_ids": [7],
    }

    request = build_oasdi_wage_base_request(
        pe_data=pe_data,
        year=2026,
        contribution_base=184_500.0,
    )

    assert request["queries"] == [
        {
            "entity_id": "person_7",
            "period": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "outputs": [OASDI_WAGE_BASE_EXCLUSION_OUTPUT],
        }
    ]
    input_values = {
        item["name"]: item["value"]["value"] for item in request["dataset"]["inputs"]
    }
    assert (
        input_values[
            f"{OASDI_WAGE_BASE_BASE}#input.contribution_and_benefit_base_under_section_230_of_social_security_act"
        ]
        == "184500.0"
    )
    assert (
        input_values[
            f"{OASDI_WAGE_BASE_BASE}#input.remuneration_paid_to_individual_by_employer_with_respect_to_employment"
        ]
        == "94350.0"
    )


def test_build_medicare_payroll_request_uses_projected_fica_wages():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "employment_income_before_lsr": 106_706,
                    "traditional_401k_contributions": 6_006,
                    "pre_tax_health_insurance_premiums": 5_606,
                    "health_savings_account_payroll_contributions": 6_750,
                    "payroll_tax_gross_wages": 94_344,
                }
            ]
        ),
        "person_ids": [7],
    }

    request = build_payroll_request(
        pe_data=pe_data,
        year=2026,
        surface="employee-medicare",
    )

    input_values = {
        item["name"]: item["value"]["value"] for item in request["dataset"]["inputs"]
    }
    assert input_values["us:statutes/26/3101/b/1#input.wages"] == "94350.0"


def test_policyengine_variables_for_payroll_surface_are_person_scoped():
    tax_unit_variables, person_variables = tax_populace.policyengine_variables_for_surfaces(
        ["employee-medicare"]
    )

    assert tax_unit_variables == ()
    assert person_variables == (
        "employee_medicare_tax",
        "employment_income",
        "health_savings_account_payroll_contributions",
        "payroll_tax_gross_wages",
        "pre_tax_health_insurance_premiums",
    )


def test_policyengine_variables_for_positive_ctc_payroll_surface_selects_ctc():
    tax_unit_variables, person_variables = tax_populace.policyengine_variables_for_surfaces(
        ["employee-oasdi"],
        positive_ctc_only=True,
    )

    assert tax_unit_variables == ("ctc",)
    assert "employee_social_security_tax" in person_variables
    assert "pre_tax_health_insurance_premiums" in person_variables


def test_policyengine_variables_for_non_payroll_surfaces_use_legacy_sets():
    assert tax_populace.policyengine_variables_for_surfaces(["ctc"]) == (
        tax_populace.PE_TAX_UNIT_VARIABLES,
        tax_populace.PE_PERSON_VARIABLES,
    )
    assert tax_populace.policyengine_variables_for_surfaces(["employee-oasdi", "ctc"]) == (
        tax_populace.PE_TAX_UNIT_VARIABLES,
        tax_populace.PE_PERSON_VARIABLES,
    )


def test_policyengine_variables_for_tax_before_credits_include_main_rates_inputs():
    tax_unit_variables, person_variables = tax_populace.policyengine_variables_for_surfaces(
        ["tax-before-credits"]
    )

    assert "income_tax_main_rates" in tax_unit_variables
    assert "taxable_income" in tax_unit_variables
    assert "unrecaptured_section_1250_gain" in tax_unit_variables
    assert "long_term_capital_gains" in person_variables
    assert "qualified_dividend_income" in person_variables
    assert person_variables == tax_populace.PE_PERSON_VARIABLES


def test_taxable_oasdi_wages_come_from_axiom_3121_results():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "persons": pd.DataFrame([{"person_id": 7, "payroll_tax_gross_wages": 200_000}]),
        "person_ids": [7],
    }
    results = [
        {
            "outputs": {
                OASDI_WAGE_BASE_EXCLUSION_OUTPUT: {
                    "kind": "scalar",
                    "value": {"kind": "decimal", "value": "15500"},
                }
            }
        }
    ]

    assert taxable_oasdi_wages_by_person_id(
        pe_data=pe_data,
        oasdi_wage_base_results=results,
    ) == {7: 184_500}


def test_build_oasdi_payroll_request_feeds_3121_taxable_wages():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "persons": pd.DataFrame([{"person_id": 7, "payroll_tax_gross_wages": 200_000}]),
        "person_ids": [7],
    }
    results = [
        {
            "outputs": {
                OASDI_WAGE_BASE_EXCLUSION_OUTPUT: {
                    "kind": "scalar",
                    "value": {"kind": "decimal", "value": "15500"},
                }
            }
        }
    ]

    request = build_payroll_request(
        pe_data=pe_data,
        year=2026,
        surface="employee-oasdi",
        oasdi_wage_base_results=results,
    )

    assert request["dataset"]["inputs"] == [
        {
            "name": "us:statutes/26/3101/a#input.wages",
            "entity": "Entity",
            "entity_id": "person_7",
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "value": {"kind": "decimal", "value": "184500.0"},
        }
    ]


def test_build_oasdi_payroll_request_requires_3121_results():
    pd = pytest.importorskip("pandas")
    pe_data = {
        "persons": pd.DataFrame([{"person_id": 7, "payroll_tax_gross_wages": 200_000}]),
        "person_ids": [7],
    }

    with pytest.raises(ValueError, match="Axiom 3121 wage-base results"):
        build_payroll_request(
            pe_data=pe_data,
            year=2026,
            surface="employee-oasdi",
        )


def test_compare_oasdi_stage_runs_encoded_ssa_base_before_3121(
    monkeypatch,
    tmp_path,
):
    pd = pytest.importorskip("pandas")
    rulespec_root = tmp_path / "rulespec-us"
    for program_path in (
        contribution_and_benefit_base_program_path(2026),
        OASDI_WAGE_BASE_PROGRAM_PATH,
        EMPLOYEE_OASDI_PROGRAM_PATH,
    ):
        target = rulespec_root / program_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("format: rulespec/v1\nrules: []\n")

    pe_data = {
        "tax_units": pd.DataFrame([{"tax_unit_id": 1}]),
        "persons": pd.DataFrame(
            [
                {
                    "person_id": 7,
                    "payroll_tax_gross_wages": 200_000,
                    "employee_social_security_tax": 11_439,
                }
            ]
        ),
        "tax_unit_ids": [1],
        "person_ids": [7],
    }
    monkeypatch.setattr(tax_populace, "require_numpy", lambda: None)
    monkeypatch.setattr(tax_populace, "require_policyengine_versions", lambda **_: None)

    def fake_load_policyengine_tax_data(**kwargs):
        assert kwargs["tax_unit_variables"] == ()
        assert kwargs["person_variables"] == (
            "employee_social_security_tax",
            "employment_income",
            "health_savings_account_payroll_contributions",
            "payroll_tax_gross_wages",
            "pre_tax_health_insurance_premiums",
        )
        return pe_data

    monkeypatch.setattr(
        tax_populace, "load_policyengine_tax_data", fake_load_policyengine_tax_data
    )

    calls = []

    def fake_run_axiom_program(*, program, request, rulespec_root, axiom_rules_path):
        del rulespec_root, axiom_rules_path
        calls.append((program.relative_to(tmp_path / "rulespec-us"), request))
        if program.name == "2026.yaml":
            return [
                {
                    "outputs": {
                        contribution_and_benefit_base_output(2026): {
                            "kind": "scalar",
                            "value": {"kind": "decimal", "value": "184500"},
                        }
                    }
                }
            ]
        if (
            program.relative_to(tmp_path / "rulespec-us")
            == OASDI_WAGE_BASE_PROGRAM_PATH
        ):
            input_values = {
                item["name"]: item["value"]["value"]
                for item in request["dataset"]["inputs"]
            }
            assert (
                input_values[
                    f"{OASDI_WAGE_BASE_BASE}#input.contribution_and_benefit_base_under_section_230_of_social_security_act"
                ]
                == "184500.0"
            )
            return [
                {
                    "outputs": {
                        OASDI_WAGE_BASE_EXCLUSION_OUTPUT: {
                            "kind": "scalar",
                            "value": {"kind": "decimal", "value": "15500"},
                        }
                    }
                }
            ]
        return [
            {
                "outputs": {
                    f"{EMPLOYEE_OASDI_BASE}#oasdi_wage_tax": {
                        "kind": "scalar",
                        "value": {"kind": "decimal", "value": "11439"},
                    }
                }
            }
        ]

    monkeypatch.setattr(tax_populace, "run_axiom_program", fake_run_axiom_program)

    report = compare_tax_ecps(
        workspace_root=tmp_path,
        rulespec_root=rulespec_root,
        axiom_rules_path=tmp_path / "axiom-rules-engine",
        year=2026,
        sample_size=1,
        positive_ctc_only=False,
        surface="employee-oasdi",
        data_folder=tmp_path,
        populace_year=2024,
        tolerance=0.01,
        relative_tolerance=2e-7,
    )

    assert report.mismatches == []
    assert [path for path, _request in calls] == [
        contribution_and_benefit_base_program_path(2026),
        OASDI_WAGE_BASE_PROGRAM_PATH,
        EMPLOYEE_OASDI_PROGRAM_PATH,
    ]


def test_policyengine_version_guard_rejects_old_us_version(monkeypatch):
    def fake_version(package):
        if package == "policyengine-us":
            return "1.722.99"
        raise AssertionError(package)

    monkeypatch.setattr(tax_populace, "version", fake_version)

    with pytest.raises(SystemExit, match="policyengine-us>="):
        require_policyengine_versions()


def test_policyengine_version_guard_allows_newer_us_version(monkeypatch):
    def fake_version(package):
        if package == "policyengine-us":
            return "1.739.2"
        raise AssertionError(package)

    monkeypatch.setattr(tax_populace, "version", fake_version)

    require_policyengine_versions()


def test_policyengine_version_guard_allows_local_us_override(monkeypatch):
    def fake_version(package):
        if package == "policyengine-us":
            return "1.722.99"
        raise AssertionError(package)

    monkeypatch.setattr(tax_populace, "version", fake_version)

    require_policyengine_versions(allow_policyengine_us_version=True)


def test_policyengine_data_certification_override_not_required_for_populace():
    assert policyengine_data_certification_override_required() is False


def test_policyengine_data_certification_override_noop_for_populace(monkeypatch):
    monkeypatch.delenv("POLICYENGINE_SKIP_COUNTRY_IMPORTS", raising=False)

    tax_populace._install_policyengine_data_certification_override()

    assert "POLICYENGINE_SKIP_COUNTRY_IMPORTS" not in tax_populace.os.environ
