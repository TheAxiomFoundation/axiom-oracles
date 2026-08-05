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
    inputs: dict[str, object] = {
        GENERATOR._module_input("member_age"): case.age,
        GENERATOR._module_input("member_covered_by_abawd_time_limit_waiver"): False,
    }
    own_flag = {
        "indian_or_urban_indian_excepted": "member_is_indian_or_urban_indian",
        "california_indian_excepted": "member_is_california_indian",
    }.get(case.case_id)
    for fact in GENERATOR.EXCEPTION_FACTS:
        if fact == (
            "member_is_parent_or_household_member_responsible_for_dependent_child"
        ):
            inputs[GENERATOR._module_input(fact)] = case.child_age is not None
        else:
            inputs[GENERATOR._module_input(fact)] = fact == own_flag
    if case.child_age is not None:
        inputs[GENERATOR._module_input("member_youngest_dependent_child_age")] = (
            case.child_age
        )
    if not case.expected_exception:
        for fact, expected in GENERATOR.NEGATIVE_CONSTRUCTION.items():
            inputs[GENERATOR._module_input(fact)] = expected
    outputs = {
        GENERATOR.AXIOM_OUTPUT: (
            "holds" if case.expected_exception else "not_holds"
        ),
        f"{GENERATOR.MODULE}#snap_member_abawd_time_limit_inapplicable": (
            "holds" if case.expected_exception else "not_holds"
        ),
    }
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
