"""entitledto recorded-fixture oracle: mapper, runner, provenance, comparator."""

from __future__ import annotations

import json
from pathlib import Path

from axiom_oracles.adapters.entitledto import (
    CAPTURE_STATUS_CAPTURED,
    CAPTURE_STATUS_PENDING,
    EntitledToInputMapper,
    EntitledToRecordedRunner,
    load_capture,
    validate_capture,
)
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.results import EngineResult
from axiom_oracles.suites.uk_ctr import uk_ctr_cases


# --- input mapper ----------------------------------------------------------


def _kingston_case() -> Case:
    return next(
        c for c in uk_ctr_cases() if c.case_id == "ctr-eng-wa-kingston-single-earner"
    )


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


# --- recorded runner: pending vs captured ----------------------------------


def _write_fixture(path: Path, *, captured: bool, ctr_annual: float = 1181.0) -> None:
    fixture = {
        "case_id": "ctr-eng-wa-kingston-single-earner",
        "oracle": "entitledto",
        "provenance": {
            "capture_status": CAPTURE_STATUS_CAPTURED
            if captured
            else CAPTURE_STATUS_PENDING,
            "calculator": "entitledto",
            "calculator_url": "https://www.entitledto.co.uk/benefits-calculator/",
            "scheme_year": "2026-27",
            "council_name": "Kingston upon Thames",
            "council_gss_code": "E09000021",
            "council_tax_band": "D",
            "capture_date": "2026-07-14" if captured else None,
            "captured_by": "tester" if captured else None,
        },
        "inputs": {"synthetic": True},
        "outputs": {
            "council_tax_reduction": {"annual_gbp": ctr_annual, "weekly_gbp": 22.71},
            "universal_credit": {"annual_gbp": 4510.0},
        }
        if captured
        else None,
    }
    path.write_text(json.dumps(fixture))


def test_runner_reports_pending_as_errored_with_no_values(tmp_path: Path) -> None:
    _write_fixture(tmp_path / "ctr-eng-wa-kingston-single-earner.json", captured=False)
    runner = EntitledToRecordedRunner(fixtures_dir=tmp_path)

    [result] = runner.run_cases([_kingston_case()])

    assert result.engine == "entitledto"
    assert result.values == {}  # never a spurious £0
    assert result.errors and "pending_capture" in result.errors[0]


def test_runner_replays_captured_values(tmp_path: Path) -> None:
    _write_fixture(tmp_path / "ctr-eng-wa-kingston-single-earner.json", captured=True)
    runner = EntitledToRecordedRunner(fixtures_dir=tmp_path)

    [result] = runner.run_cases([_kingston_case()])

    assert result.values["council_tax_reduction"] == 1181.0
    assert result.values["universal_credit"] == 4510.0
    assert not result.errors


def test_runner_reports_missing_fixture(tmp_path: Path) -> None:
    runner = EntitledToRecordedRunner(fixtures_dir=tmp_path)
    [result] = runner.run_cases([_kingston_case()])
    assert result.values == {}
    assert result.errors and "no entitledto fixture" in result.errors[0]


def test_weekly_only_output_is_annualised(tmp_path: Path) -> None:
    fixture = {
        "case_id": "ctr-eng-wa-kingston-single-earner",
        "oracle": "entitledto",
        "provenance": {
            "capture_status": CAPTURE_STATUS_CAPTURED,
            "calculator": "entitledto",
            "calculator_url": "x",
            "scheme_year": "2026-27",
            "council_name": "Kingston upon Thames",
            "council_gss_code": "E09000021",
            "council_tax_band": "D",
            "capture_date": "2026-07-14",
            "captured_by": "tester",
        },
        "inputs": {},
        "outputs": {"council_tax_reduction": {"weekly_gbp": 20.0}},
    }
    path = tmp_path / "ctr-eng-wa-kingston-single-earner.json"
    path.write_text(json.dumps(fixture))
    runner = EntitledToRecordedRunner(fixtures_dir=tmp_path)
    [result] = runner.run_cases([_kingston_case()])
    assert result.values["council_tax_reduction"] == 1040.0  # 20 * 52


# --- provenance validation -------------------------------------------------


def test_validate_accepts_pending_stub(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    _write_fixture(path, captured=False)
    assert validate_capture(load_capture(path)) == []


def test_validate_accepts_complete_capture(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    _write_fixture(path, captured=True)
    assert validate_capture(load_capture(path)) == []


def test_validate_rejects_captured_without_outputs(tmp_path: Path) -> None:
    fixture = {
        "case_id": "c",
        "provenance": {
            "capture_status": CAPTURE_STATUS_CAPTURED,
            "calculator": "entitledto",
            "calculator_url": "x",
            "scheme_year": "2026-27",
            "council_name": "Kingston upon Thames",
            "council_gss_code": "E09000021",
            "council_tax_band": "D",
            "capture_date": "2026-07-14",
            "captured_by": "tester",
        },
        "inputs": {},
        "outputs": None,
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(fixture))
    problems = validate_capture(load_capture(path))
    assert any("outputs" in p for p in problems)


def test_validate_rejects_pending_with_outputs(tmp_path: Path) -> None:
    fixture = {
        "case_id": "c",
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
        "outputs": {"council_tax_reduction": {"annual_gbp": 1181.0}},
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(fixture))
    problems = validate_capture(load_capture(path))
    assert any("pending_capture" in p for p in problems)


# --- comparator wiring -----------------------------------------------------


def test_recorded_oracle_grades_against_policyengine(tmp_path: Path) -> None:
    """A captured entitledto value compares to a PolicyEngine value through the
    existing Comparator, keyed by the CTR concept's per-engine targets."""
    _write_fixture(
        tmp_path / "ctr-eng-wa-kingston-single-earner.json",
        captured=True,
        ctr_annual=1181.0,
    )
    entitledto = EntitledToRecordedRunner(fixtures_dir=tmp_path)
    [left] = entitledto.run_cases([_kingston_case()])
    right = EngineResult(
        engine="policyengine",
        household_id="ctr-eng-wa-kingston-single-earner",
        values={"council_tax_reduction": 1181.0},
    )
    mapping = ProgramMapping(
        standard="uk:policies/govuk/council-tax-reduction"
        "#council_tax_reduction_annual_amount",
        description="UK Council Tax Reduction annual amount",
        category="benefits",
        comparison="amount",
        tolerance=0.01,
        targets={
            "entitledto": "council_tax_reduction",
            "policyengine": "council_tax_reduction",
        },
    )
    [comparison] = Comparator([mapping]).compare([left], [right])
    assert comparison.match_count == 1
    assert comparison.mismatch_count == 0

    # A per-council divergence (entitledto models the local scheme; PE returns
    # the reported fallback) surfaces as a mismatch, not a silent pass.
    right_gap = EngineResult(
        engine="policyengine",
        household_id="ctr-eng-wa-kingston-single-earner",
        values={"council_tax_reduction": 0.0},
    )
    [gap] = Comparator([mapping]).compare([left], [right_gap])
    assert gap.mismatch_count == 1
    assert gap.mismatches()[0].difference == 1181.0


def test_entity_kind_helper_omits_non_person_children() -> None:
    case = Case(
        case_id="x",
        period="2026",
        metadata={"couple": False},
        entities=(Entity("claimant", "person", {Concepts.PERSON_AGE: 40}),),
    )
    record = EntitledToInputMapper().map_case(case)
    assert record["children"] == []
    assert record["adults"][0]["age"] == 40
