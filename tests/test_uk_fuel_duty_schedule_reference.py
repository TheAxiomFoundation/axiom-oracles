"""uk-fuel-duty: the primary-source schedule and the committed report built on it.

The schedule's load-bearing identities are reviewed constants here (the
dk-satser pattern): a legitimate refresh updates them in the same diff.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = REPO_ROOT / "reference" / "uk-fuel-duty-schedule" / "schedule.yaml"
REPORT = REPO_ROOT / "dashboard" / "public" / "data" / "axiom-policyengine-uk-fuel-duty.json"
DISPOSITIONS = REPO_ROOT / "dispositions" / "uk-fuel-duty.yaml"

STANDING_RATE = 0.5795
EXPECTED_PERIODS = [
    ("2025-01-01", "2025-03-22", 8.63, 0.5295),
    ("2025-03-23", "2026-03-22", 8.63, 0.5295),
    ("2026-03-23", "2026-12-31", 8.63, 0.5295),
    ("2027-01-01", "2027-02-28", 3.45, 0.5595),
    ("2027-03-01", "2028-12-31", 0, 0.5795),
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def schedule() -> dict:
    return yaml.safe_load(SCHEDULE.read_text())


@pytest.fixture(scope="module")
def report() -> dict:
    return json.loads(REPORT.read_text())


def test_schedule_matches_the_reviewed_constants(schedule: dict) -> None:
    assert schedule["standing_rate"]["rate"] == STANDING_RATE
    got = [
        (
            p["effective_from"],
            p["effective_to"],
            p["percentage_deduction"],
            p["reference_rate"],
        )
        for p in schedule["periods"]
    ]
    assert got == EXPECTED_PERIODS


def test_schedule_is_contiguous_and_covers_2025_to_2028(schedule: dict) -> None:
    periods = schedule["periods"]
    assert periods[0]["effective_from"] == "2025-01-01"
    assert periods[-1]["effective_to"] == "2028-12-31"
    for before, after in zip(periods, periods[1:]):
        end = date.fromisoformat(before["effective_to"])
        assert date.fromisoformat(after["effective_from"]) == end + timedelta(days=1)


def test_reference_rates_are_the_orders_column_d_arithmetic(schedule: dict) -> None:
    for period in schedule["periods"]:
        pct = float(period["percentage_deduction"])
        operative = STANDING_RATE * (1 - pct / 100)
        # Column (D) is the operative rate rounded to the hundredth of a penny,
        # and the gap never exceeds the comparison's per-litre tolerance.
        assert round(operative, 4) == pytest.approx(period["reference_rate"], abs=1e-12)
        assert abs(operative - period["reference_rate"]) < 0.00005
        # Reductions only: no period charges above the standing rate.
        assert period["reference_rate"] <= STANDING_RATE


def test_every_axiom_row_is_the_schedule_rate_less_supplied_relief(report: dict) -> None:
    assert report["case_count"] == len(report["cases"]) == 4 * 13
    for row in report["cases"]:
        expected = row["statutory_rate"] - (row["rural_relief"] if row["rural"] else 0.0)
        assert row["axiom"] == pytest.approx(expected, abs=1e-9), row["case_id"]


def test_2025_matches_and_every_mismatch_is_explained(report: dict) -> None:
    assert all(not m["month"].startswith("2025") for m in report["mismatches"])
    assert {m["pe_mechanism"] for m in report["mismatches"]} <= {
        "superseded_schedule_calendar_average",
        "rpi_indexation_not_enacted",
    }
    for m in report["mismatches"]:
        # Attribution needs PolicyEngine to be charging exactly its own parameter.
        assert m["right"] == pytest.approx(
            m["policyengine_petrol_and_diesel"] - m["rural_relief"], abs=0.00005
        )
        assert (m["pe_mechanism"] == "rpi_indexation_not_enacted") == (m["month"] >= "2027-04")
    dispositioned = report["summary"]["dispositioned"]
    assert dispositioned["unexplained_count"] == 0
    assert dispositioned["expired_entries"] == []
    assert dispositioned["orphaned_entries"] == []


def test_dispositions_file_is_the_builder_output() -> None:
    builder = _load("build_uk_fuel_duty_dispositions")
    rebuilt = builder.HEADER + yaml.safe_dump(
        builder.build(), sort_keys=False, width=100, allow_unicode=True
    )
    assert DISPOSITIONS.read_text() == rebuilt


# --- Review round 1: attribution must require the Axiom side to be statutory. ---


def test_an_axiom_error_is_never_attributed_to_policyengine() -> None:
    generator = _load("generate_uk_fuel_duty")
    case = generator.FDCase("fd-2026-02", date(2026, 2, 1), False, "2026-schedule")
    pe_row = {"fuel_duty": 0.5345, "petrol_and_diesel_parameter": 0.5345, "rural_relief": 0.05}
    assert (
        generator.classify_mechanism(case, pe_row, 0.5295, 0.5295)
        == "superseded_schedule_calendar_average"
    )
    # The reviewer's case: correct PE 0.5295, erroneous Axiom 0.6295.
    correct_pe = {"fuel_duty": 0.5295, "petrol_and_diesel_parameter": 0.5295, "rural_relief": 0.05}
    assert generator.classify_mechanism(case, correct_pe, 0.5295, 0.6295) == "unreconciled"
    assert generator.classify_mechanism(case, pe_row, 0.5295, 0.6295) == "unreconciled"


def test_builder_refuses_a_corrupted_non_representative_row(tmp_path, monkeypatch) -> None:
    builder = _load("build_uk_fuel_duty_dispositions")
    report = json.loads(REPORT.read_text())
    victim = next(m for m in report["mismatches"] if m["month"] == "2026-02")
    victim["left"] = float(victim["left"]) + 0.1
    corrupted = tmp_path / "report.json"
    corrupted.write_text(json.dumps(report))
    monkeypatch.setattr(builder, "REPORT", corrupted)
    with pytest.raises(SystemExit, match="fd-2026-02"):
        builder.build()
