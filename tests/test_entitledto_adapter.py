"""entitledto recorded-fixture oracle: mapper, fail-closed runner, provenance, comparator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiom_oracles.adapters.entitledto import (
    CAPTURE_STATUS_CAPTURED,
    CAPTURE_STATUS_PENDING,
    EntitledToInputMapper,
    EntitledToRecordedRunner,
    load_capture,
    load_captures_by_id,
    validate_capture,
)
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.results import EngineResult
from axiom_oracles.suites.uk_ctr import uk_ctr_cases

_CID = "ctr-eng-wa-kingston-single-earner"


def _kingston_case() -> Case:
    return next(c for c in uk_ctr_cases() if c.case_id == _CID)


# --- input mapper ----------------------------------------------------------


def test_mapper_projects_case_to_entitledto_record() -> None:
    record = EntitledToInputMapper().map_case(_kingston_case())

    assert record["relationship_status"] == "single"
    assert record["country"] == "England"
    assert record["local_authority"] == {
        "name": "Kingston upon Thames",
        "gss_code": "E09000021",
        "postcode": "KT1 1EU",
    }
    assert record["council_tax"] == {"band": "D", "annual_liability_gbp": 2171.0}
    assert record["housing"]["tenure"] == "private_rent"
    assert record["housing"]["assessed_for_rent_rebate"] is True
    assert record["income_basis"].startswith("annual GBP, gross")
    assert record["adults"] == [
        {
            "role": "claimant",
            "age": 30,
            "employment_income_annual_gbp": 11000.0,
            "state_pension_annual_gbp": 0.0,
            "private_pension_annual_gbp": 0.0,
        }
    ]
    assert record["children"] == []
    assert record["capital_gbp"] == 3000.0


def test_mapper_handles_couple_and_children() -> None:
    cardiff = next(
        c for c in uk_ctr_cases() if c.case_id == "ctr-wal-wa-cardiff-couple-2kids"
    )
    record = EntitledToInputMapper().map_case(cardiff)

    assert record["relationship_status"] == "couple"
    assert [a["role"] for a in record["adults"]] == ["claimant", "partner"]
    assert record["adults"][0]["employment_income_annual_gbp"] == 22000.0
    assert record["adults"][1]["employment_income_annual_gbp"] == 0.0
    assert record["children"] == [{"age": 5}, {"age": 3}]


def test_owner_occupier_is_not_assessed_for_rent_rebate() -> None:
    birmingham = next(
        c for c in uk_ctr_cases() if c.case_id == "ctr-eng-pa-birmingham-couple-gc"
    )
    record = EntitledToInputMapper().map_case(birmingham)
    assert record["housing"]["tenure"] == "owner"
    assert record["housing"]["assessed_for_rent_rebate"] is False


def test_mapper_reads_non_person_and_child_entities() -> None:
    # A household with a non-person entity (must be ignored) and a child (must be
    # a child, not an adult), plus an adult with no explicit relation (claimant).
    case = Case(
        case_id="x",
        period="2026",
        metadata={"couple": False, "claimant_employment_income": 9000.0},
        entities=(
            Entity("home", "household", {}),  # non-person: ignored
            Entity("adult", "person", {Concepts.PERSON_AGE: 41}),  # no relation
            Entity("kid", "person", {Concepts.PERSON_AGE: 7,
                                     Concepts.HOUSEHOLD_RELATION: "Child"}),
        ),
    )
    record = EntitledToInputMapper().map_case(case)
    assert len(record["adults"]) == 1
    assert record["adults"][0]["age"] == 41
    assert record["adults"][0]["employment_income_annual_gbp"] == 9000.0
    assert record["children"] == [{"age": 7}]


# --- recorded runner: fail-closed replay -----------------------------------


def _captured_fixture(*, ctr, liability=2171.0, **overrides) -> dict:
    provenance = {
        "capture_status": CAPTURE_STATUS_CAPTURED,
        "calculator": "entitledto",
        "calculator_url": "https://www.entitledto.co.uk/benefits-calculator/",
        "scheme_year": "2026-27",
        "council_name": "Kingston upon Thames",
        "council_gss_code": "E09000021",
        "council_tax_band": "D",
        "capture_date": "2026-07-14",
        "captured_by": "tester",
        "entitledto_council_tax_liability_gbp": liability,
    }
    provenance.update(overrides.pop("provenance", {}))
    fixture = {
        "case_id": _CID,
        "oracle": "entitledto",
        "provenance": provenance,
        "inputs": {},
        "outputs": {"council_tax_reduction": ctr, "universal_credit": {"annual_gbp": 4510.0}},
    }
    fixture.update(overrides)
    return fixture


def _write(dir_: Path, fixture: dict, name: str = f"{_CID}.json") -> Path:
    path = dir_ / name
    path.write_text(json.dumps(fixture))
    return path


def _pending_fixture() -> dict:
    return {
        "case_id": _CID,
        "oracle": "entitledto",
        "provenance": {
            "capture_status": CAPTURE_STATUS_PENDING,
            "calculator": "entitledto",
            "calculator_url": "x",
            "scheme_year": "2026-27",
            "council_name": "Kingston upon Thames",
            "council_gss_code": "E09000021",
            "council_tax_band": "D",
        },
        "inputs": {},
        "outputs": None,
    }


def test_runner_reports_pending_as_errored_with_no_values(tmp_path: Path) -> None:
    _write(tmp_path, _pending_fixture())
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values == {}  # never a spurious £0
    assert result.errors and "pending_capture" in result.errors[0]


def test_runner_replays_valid_captured_values(tmp_path: Path) -> None:
    _write(tmp_path, _captured_fixture(ctr={"annual_gbp": 1181.0, "weekly_gbp": 22.71}))
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values["council_tax_reduction"] == 1181.0
    assert result.values["universal_credit"] == 4510.0
    assert not result.errors


def test_runner_reports_missing_fixture(tmp_path: Path) -> None:
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values == {}
    assert result.errors and "no entitledto fixture" in result.errors[0]


def test_weekly_only_output_is_annualised(tmp_path: Path) -> None:
    _write(tmp_path, _captured_fixture(ctr={"weekly_gbp": 20.0}))
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values["council_tax_reduction"] == 1040.0  # 20 * 52


# --- fail-closed: malformed "captured" fixtures are never graded ------------


@pytest.mark.parametrize(
    "ctr",
    [
        False,  # JSON boolean must NOT read as 0 and match a PE £0
        True,
        -5.0,  # negative
        {"annual_gbp": False},
        {"annual_gbp": -1.0},
        {"weekly_gbp": float("nan")},
        {"foo": 1.0},  # no annual/weekly/monthly
    ],
)
def test_malformed_captured_ctr_is_not_graded(tmp_path: Path, ctr) -> None:
    _write(tmp_path, _captured_fixture(ctr=ctr))
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values == {}
    assert result.errors and "invalid capture" in result.errors[0]


def test_captured_missing_liability_is_not_graded(tmp_path: Path) -> None:
    fixture = _captured_fixture(ctr={"annual_gbp": 1181.0})
    del fixture["provenance"]["entitledto_council_tax_liability_gbp"]
    _write(tmp_path, fixture)
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values == {}
    assert result.errors and "invalid capture" in result.errors[0]


def test_captured_unknown_output_key_is_not_graded(tmp_path: Path) -> None:
    fixture = _captured_fixture(ctr={"annual_gbp": 1181.0})
    fixture["outputs"]["not_a_benefit"] = {"annual_gbp": 5.0}
    _write(tmp_path, fixture)
    [result] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    assert result.values == {}


def test_duplicate_case_ids_raise(tmp_path: Path) -> None:
    _write(tmp_path, _pending_fixture(), name=f"{_CID}.json")
    dup = _pending_fixture()
    (tmp_path / "other.json").write_text(json.dumps(dup))  # same case_id, different filename
    with pytest.raises(ValueError, match="does not match its filename stem|duplicate"):
        load_captures_by_id(tmp_path)


# --- provenance validation -------------------------------------------------


def test_validate_accepts_pending_stub(tmp_path: Path) -> None:
    path = _write(tmp_path, _pending_fixture())
    assert validate_capture(load_capture(path)) == []


def test_validate_accepts_complete_capture(tmp_path: Path) -> None:
    path = _write(tmp_path, _captured_fixture(ctr={"annual_gbp": 1181.0}))
    assert validate_capture(load_capture(path)) == []


def test_validate_rejects_captured_without_outputs(tmp_path: Path) -> None:
    fixture = _captured_fixture(ctr={"annual_gbp": 1181.0})
    fixture["outputs"] = None
    path = _write(tmp_path, fixture)
    assert any("outputs" in p for p in validate_capture(load_capture(path)))


def test_validate_rejects_pending_with_outputs(tmp_path: Path) -> None:
    fixture = _pending_fixture()
    fixture["outputs"] = {"council_tax_reduction": {"annual_gbp": 1181.0}}
    path = _write(tmp_path, fixture)
    assert any("pending_capture" in p for p in validate_capture(load_capture(path)))


def test_validate_rejects_boolean_ctr(tmp_path: Path) -> None:
    path = _write(tmp_path, _captured_fixture(ctr=False))
    problems = validate_capture(load_capture(path))
    assert any("council_tax_reduction" in p for p in problems)


# --- comparator wiring -----------------------------------------------------


def test_recorded_oracle_grades_against_policyengine(tmp_path: Path) -> None:
    """A valid captured entitledto value compares to a PolicyEngine value through
    the existing Comparator, keyed by the CTR concept's per-engine targets."""
    _write(tmp_path, _captured_fixture(ctr={"annual_gbp": 1181.0}))
    [left] = EntitledToRecordedRunner(fixtures_dir=tmp_path).run_cases([_kingston_case()])
    mapping = ProgramMapping(
        standard="uk:policies/govuk/council-tax-reduction"
        "#council_tax_reduction_annual_amount",
        description="UK Council Tax Reduction annual amount",
        category="benefits",
        comparison="amount",
        tolerance=0.01,
        targets={"entitledto": "council_tax_reduction", "policyengine": "council_tax_reduction"},
    )
    right = EngineResult("policyengine", _CID, {"council_tax_reduction": 1181.0})
    [comparison] = Comparator([mapping]).compare([left], [right])
    assert comparison.match_count == 1 and comparison.mismatch_count == 0

    # A per-council divergence surfaces as a mismatch, not a silent pass.
    right_gap = EngineResult("policyengine", _CID, {"council_tax_reduction": 0.0})
    [gap] = Comparator([mapping]).compare([left], [right_gap])
    assert gap.mismatch_count == 1
    assert gap.mismatches()[0].difference == 1181.0
