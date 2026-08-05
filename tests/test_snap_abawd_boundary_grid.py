"""Focused invariants for the SNAP ABAWD post-P.L. 119-21 boundary grid.

The grid is the behavioral companion to the PR #400 structural closure
warning on the 2015(o)(3) / 273.24 divergence, so these tests pin (a) that
the case matrix is exactly the statute-boundary set, (b) that the fixture
replay fails closed on construction or verdict drift instead of silently
shifting the matrix, and (c) that the report and runner plumbing keep the
suite inside the repo's gates (one dispositioned architectural residual,
zero unexplained).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[1]


def _load_generator():
    path = REPO_ROOT / "scripts" / "generate_snap_abawd_boundary.py"
    spec = importlib.util.spec_from_file_location(
        "snap_abawd_boundary_generator",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_runner():
    path = REPO_ROOT / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("snap_abawd_grid_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()


def _valid_record(case) -> dict:
    """Build a fixture record satisfying the boundary construction."""
    inputs = {
        GENERATOR._module_input(name): value
        for name, value in GENERATOR._expected_module_inputs(case).items()
    }
    verdict = "holds" if case.expected_exception else "not_holds"
    outputs = {
        GENERATOR.AXIOM_OUTPUT: verdict,
        f"{GENERATOR.MODULE}#snap_member_abawd_time_limit_inapplicable": verdict,
    }
    if case.child_age is not None:
        outputs[
            f"{GENERATOR.MODULE}"
            "#snap_member_abawd_responsible_for_dependent_child_under_fourteen"
        ] = "holds" if case.child_age < 14 else "not_holds"
    return {
        "name": case.case_id,
        "period": GENERATOR.VALIDATION_PERIOD,
        "input": inputs,
        "output": outputs,
    }


def _case(case_id: str):
    matches = [case for case in GENERATOR.CASES if case.case_id == case_id]
    assert len(matches) == 1, case_id
    return matches[0]


def test_matrix_is_exactly_the_section_2015o3_boundary_set():
    expected = {
        "age_55_subject_to_time_limit_post_hr1": (55, False),
        "age_64_subject_despite_general_work_exemption": (64, False),
        "age_65_excepted_under_usda_operational_reading": (65, True),
        "age_66_excepted_under_either_reading": (66, True),
        "age_23_no_exception_post_hr1": (23, False),
        "indian_or_urban_indian_excepted": (40, True),
        "california_indian_excepted": (40, True),
        "abawd_exception_applies_to_responsible_adult_with_child_under_fourteen": (
            30,
            True,
        ),
        "abawd_no_exception_for_dependent_child_aged_fourteen": (30, False),
    }
    observed = {
        case.case_id: (case.age, case.expected_exception)
        for case in GENERATOR.CASES
    }
    assert observed == expected
    child_ages = {
        case.case_id: case.child_age
        for case in GENERATOR.CASES
        if case.child_age is not None
    }
    assert child_ages == {
        "abawd_exception_applies_to_responsible_adult_with_child_under_fourteen": 13,
        "abawd_no_exception_for_dependent_child_aged_fourteen": 14,
    }
    foster_cases = [case.case_id for case in GENERATOR.CASES if case.pe_foster]
    assert foster_cases == ["age_23_no_exception_post_hr1"]
    indian_cases = [case.case_id for case in GENERATOR.CASES if case.indian]
    assert indian_cases == [
        "indian_or_urban_indian_excepted",
        "california_indian_excepted",
    ]


def test_valid_records_replay_cleanly():
    for case in GENERATOR.CASES:
        record = _valid_record(case)
        GENERATOR._validate_fixture_case(case, record)
        compared, diagnostics = GENERATOR._replayed_verdicts(case, record)
        assert compared is case.expected_exception
        assert (
            f"{GENERATOR.MODULE}#snap_member_abawd_time_limit_inapplicable"
            in diagnostics
        )


def test_wrong_age_fails_closed():
    case = _case("age_55_subject_to_time_limit_post_hr1")
    record = _valid_record(case)
    record["input"][GENERATOR._module_input("member_age")] = 56
    with pytest.raises(ValueError, match="member_age"):
        GENERATOR._validate_fixture_case(case, record)


def test_dropped_unrelated_exception_fact_fails_closed():
    case = _case("age_65_excepted_under_usda_operational_reading")
    record = _valid_record(case)
    del record["input"][GENERATOR._module_input("member_is_pregnant")]
    with pytest.raises(ValueError, match="does not assign"):
        GENERATOR._validate_fixture_case(case, record)


def test_negative_case_without_exhausted_months_fails_closed():
    case = _case("age_23_no_exception_post_hr1")
    record = _valid_record(case)
    record["input"][
        GENERATOR._module_input("snap_abawd_countable_months_in_three_year_period")
    ] = 2
    with pytest.raises(ValueError, match="boundary construction"):
        GENERATOR._validate_fixture_case(case, record)


def test_regrown_former_foster_fact_fails_closed():
    case = _case("age_23_no_exception_post_hr1")
    record = _valid_record(case)
    record["input"][
        GENERATOR._module_input("member_is_former_foster_youth")
    ] = True
    with pytest.raises(ValueError, match="former-foster"):
        GENERATOR._validate_fixture_case(case, record)


def test_smuggled_d2_general_exemption_fails_closed():
    case = _case("age_65_excepted_under_usda_operational_reading")
    record = _valid_record(case)
    record["input"][
        GENERATOR._general_input(
            "member_regular_participant_in_drug_or_alcohol_treatment"
        )
    ] = True
    with pytest.raises(ValueError, match="d\\)\\(2\\) carrier"):
        GENERATOR._validate_fixture_case(case, record)


def test_nonzero_general_work_hours_fails_closed():
    case = _case("age_66_excepted_under_either_reading")
    record = _valid_record(case)
    record["input"][GENERATOR._general_input("member_weekly_work_hours")] = 30
    with pytest.raises(ValueError, match="zero-work construction"):
        GENERATOR._validate_fixture_case(case, record)


def test_unpinned_new_module_input_fails_closed():
    case = _case("indian_or_urban_indian_excepted")
    record = _valid_record(case)
    record["input"][GENERATOR._module_input("member_new_exception_fact")] = True
    with pytest.raises(ValueError, match="does not pin"):
        GENERATOR._validate_fixture_case(case, record)


def test_input_outside_known_modules_fails_closed():
    case = _case("age_55_subject_to_time_limit_post_hr1")
    record = _valid_record(case)
    record["input"]["us:regulations/7-cfr/273/8#input.member_resource_test"] = True
    with pytest.raises(ValueError, match="outside the 273.24/273.7 surface"):
        GENERATOR._validate_fixture_case(case, record)


def test_flipped_downstream_diagnostic_fails_closed():
    case = _case("age_23_no_exception_post_hr1")
    record = _valid_record(case)
    record["output"][
        f"{GENERATOR.MODULE}#snap_member_abawd_time_limit_inapplicable"
    ] = "holds"
    with pytest.raises(ValueError, match="boundary construction implies"):
        GENERATOR._replayed_verdicts(case, record)


def test_dropped_required_diagnostic_fails_closed():
    case = _case("age_55_subject_to_time_limit_post_hr1")
    record = _valid_record(case)
    del record["output"][
        f"{GENERATOR.MODULE}#snap_member_abawd_time_limit_inapplicable"
    ]
    with pytest.raises(ValueError, match="no longer asserts"):
        GENERATOR._replayed_verdicts(case, record)


def test_zeroed_minimum_wage_rate_fails_closed():
    # The (d)(2) wages arm reads wages >= rate * 30; a zeroed rate would
    # make it hold vacuously at zero wages.
    case = _case("age_65_excepted_under_usda_operational_reading")
    record = _valid_record(case)
    record["input"][GENERATOR._general_input("member_weekly_wages")] = 0
    record["input"][
        GENERATOR._general_input("federal_or_state_minimum_wage")
    ] = 0
    with pytest.raises(ValueError, match="rate must stay positive"):
        GENERATOR._validate_fixture_case(case, record)


def test_unknown_general_module_input_fails_closed():
    case = _case("age_64_subject_despite_general_work_exemption")
    record = _valid_record(case)
    record["input"][GENERATOR._general_input("member_new_d2_route")] = True
    with pytest.raises(ValueError, match="has not reasoned about"):
        GENERATOR._validate_fixture_case(case, record)


def test_flipped_general_age_exemption_diagnostic_fails_closed():
    case = _case("age_64_subject_despite_general_work_exemption")
    record = _valid_record(case)
    record["output"][
        f"{GENERATOR.GENERAL_MODULE}#snap_member_general_work_requirement_exempt"
    ] = "not_holds"
    with pytest.raises(ValueError, match="boundary construction implies"):
        GENERATOR._replayed_verdicts(case, record)


def test_checkout_guard_rejects_skip_worktree_hidden_edit(tmp_path):
    import subprocess

    runner = _load_runner()
    relpath = runner._ABAWD_FIXTURE_RELPATH
    repo = tmp_path / "rulespec-us"
    fixture = repo / relpath
    fixture.parent.mkdir(parents=True)
    fixture.write_text("- name: canonical\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "seed"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    assert runner._rulespec_checkout_unclean_reason(repo) is None
    fixture.write_text("- name: tampered\n")
    subprocess.run(
        ["git", "update-index", "--skip-worktree", relpath],
        cwd=repo,
        check=True,
        env=env,
    )
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert porcelain.stdout.strip() == ""  # the hidden edit git status misses
    reason = runner._rulespec_checkout_unclean_reason(repo)
    assert reason is not None and "differs from HEAD" in reason


def test_child_routing_probe_rejects_moved_routing():
    healthy = {
        "child_13": {
            "meets_snap_work_requirements_person": True,
            "meets_snap_abawd_work_requirements": False,
            "meets_snap_general_work_requirements": True,
        },
        "child_14": {
            "meets_snap_work_requirements_person": False,
            "meets_snap_abawd_work_requirements": False,
            "meets_snap_general_work_requirements": True,
        },
    }
    GENERATOR._check_child_routing_probe(healthy)
    dropped_routing = {
        label: dict(values) for label, values in healthy.items()
    }
    # If PolicyEngine dropped the upstream routing, the age-64 child-13
    # member would fail the person composite like the child-14 one.
    dropped_routing["child_13"]["meets_snap_work_requirements_person"] = False
    with pytest.raises(RuntimeError, match="child-routing probe"):
        GENERATOR._check_child_routing_probe(dropped_routing)


def test_reduction_premises_reject_pre_hr1_or_waived_evaluation():
    healthy = {
        "is_snap_abawd_hr1_in_effect": True,
        "is_in_snap_abawd_waived_area": False,
    }
    GENERATOR._check_case_reduction_premises("age_55", healthy)
    with pytest.raises(RuntimeError, match="HR1 not in effect"):
        GENERATOR._check_case_reduction_premises(
            "age_55", {**healthy, "is_snap_abawd_hr1_in_effect": False}
        )
    with pytest.raises(RuntimeError, match="waived area"):
        GENERATOR._check_case_reduction_premises(
            "age_55", {**healthy, "is_in_snap_abawd_waived_area": True}
        )


def test_verdict_off_the_statute_boundary_fails_closed():
    case = _case("age_55_subject_to_time_limit_post_hr1")
    record = _valid_record(case)
    record["output"][GENERATOR.AXIOM_OUTPUT] = "holds"
    with pytest.raises(ValueError, match="moved off the statute boundary"):
        GENERATOR._replayed_verdicts(case, record)


def test_wrong_period_fails_closed():
    case = _case("age_66_excepted_under_either_reading")
    record = _valid_record(case)
    record["period"] = "2025-06"
    with pytest.raises(ValueError, match="pinned to 2026-07"):
        GENERATOR._validate_fixture_case(case, record)


def test_pe_projection_pins_the_zero_work_construction():
    for case in GENERATOR.CASES:
        situation = GENERATOR._pe_situation(case)
        member = situation["people"]["member"]
        assert member["weekly_hours_worked_before_lsr"] == {2026: 0}
        assert member["age"] == {2026: case.age}
        household = situation["households"]["household"]
        assert household["state_code"] == {2026: "TX"}
        if case.child_age is not None:
            child = situation["people"]["child"]
            assert child["age"] == {2026: case.child_age}
            assert set(situation["spm_units"]["spm_unit"]["members"]) == {
                "member",
                "child",
            }
        assert ("is_snap_abawd_indian_exempt" in member) is case.indian
        assert ("was_in_foster_care" in member) is case.pe_foster


def test_report_counts_and_mismatch_shape():
    axiom = {case.case_id: case.expected_exception for case in GENERATOR.CASES}
    policyengine = dict(axiom)
    child_13 = (
        "abawd_exception_applies_to_responsible_adult_with_child_under_fourteen"
    )
    policyengine[child_13] = False
    empty = {case.case_id: {} for case in GENERATOR.CASES}
    report = GENERATOR._build_report(axiom, empty, empty, policyengine, empty)
    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["suite"] == GENERATOR.SUITE
    assert report["summary"]["comparison_count"] == 9
    assert report["summary"]["match_count"] == 8
    assert report["summary"]["mismatch_count"] == 1
    (mismatch,) = report["mismatches"]
    assert mismatch["case_id"] == child_13
    assert mismatch["kind"] == "judgment_difference"
    assert mismatch["left"] is True and mismatch["right"] is False
    GENERATOR._assert_non_vacuous(axiom, policyengine)


def test_degenerate_engine_output_fails_closed():
    axiom = {case.case_id: case.expected_exception for case in GENERATOR.CASES}
    constant = {case.case_id: True for case in GENERATOR.CASES}
    with pytest.raises(RuntimeError, match="degenerate"):
        GENERATOR._assert_non_vacuous(axiom, constant)


def test_runner_is_registered_with_reviewed_pins():
    runner = _load_runner()
    assert "snap-abawd-boundary-grid" in runner.RUNNERS
    config = yaml.safe_load(
        (REPO_ROOT / "comparisons" / "us-snap-abawd-grid.yaml").read_text()
    )
    assert config["runner"]["type"] == "snap-abawd-boundary-grid"
    parameters = config["runner"]["parameters"]
    assert parameters["policyengine_version"] == "4.18.9"
    assert parameters["policyengine_us_version"] == "1.767.3"
    assert parameters["policyengine_core_version"] == "3.30.3"
    assert parameters["rulespec_remote"].endswith("rulespec-us.git")
    # Deliberately unpinned: the suite floats on rulespec-us main so the
    # affected-rerun sweep re-runs it whenever the encoding moves.
    assert "rulespec_upstream_sha" not in parameters
    assert "rulespec_upstream_tree" not in parameters
    assert config["dashboard"]["suite"] == "us-snap-abawd-grid"
    assert (REPO_ROOT / "dispositions" / "us-snap-abawd-grid.yaml").is_file()


def test_runner_rejects_a_different_oracle_stack():
    runner = _load_runner()
    with pytest.raises(SystemExit, match="reviewed 2026 oracle stack"):
        runner._run_snap_abawd_boundary_grid(
            {
                "parameters": {
                    "policyengine_version": "4.18.9",
                    "policyengine_us_version": "1.900.0",
                    "policyengine_core_version": "3.30.3",
                }
            },
            Path("/nonexistent/output.json"),
        )
