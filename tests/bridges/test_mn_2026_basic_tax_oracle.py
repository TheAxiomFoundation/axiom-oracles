"""Exact oracle contract and formula grid for Minnesota's 2026 schedule."""

from __future__ import annotations

import pytest

from axiom_oracles.bridges.registry import load_policyengine_registry
from axiom_oracles.bridges.state_tax_populace_runner import (
    _precision_stable_mn_basic_tax,
)


MODULE = "us-mn:policies/income_tax/pilot_liability_pipeline"
OUTPUT = f"{MODULE}#mn_pit_pilot_schedule_tax"
RATES = (0.0535, 0.068, 0.0785, 0.0985)
OFFICIAL_THRESHOLDS = {
    "SINGLE": (33_310, 109_430, 203_150),
    "JOINT": (48_700, 193_480, 337_930),
    "SEPARATE": (24_350, 96_740, 168_965),
    "HEAD_OF_HOUSEHOLD": (41_010, 164_800, 270_060),
    "SURVIVING_SPOUSE": (48_700, 193_480, 337_930),
}
# PolicyEngine-US 1.752.2 predates the final official threshold rounding.
# These values are included only to put probes on both sides of every known
# vintage boundary; the expected tax always comes from OFFICIAL_THRESHOLDS.
PINNED_POLICYENGINE_THRESHOLDS = {
    "SINGLE": (33_310, 109_410, 203_130),
    "JOINT": (48_700, 193_470, 337_900),
    "SEPARATE": (24_350, 96_730, 168_950),
    "HEAD_OF_HOUSEHOLD": (41_010, 164_780, 270_030),
    "SURVIVING_SPOUSE": (48_700, 193_470, 337_900),
}


def _official_schedule(income: float, thresholds: tuple[int, int, int]) -> float:
    taxable = max(0.0, income)
    threshold_2, threshold_3, threshold_4 = thresholds
    return (
        RATES[0] * min(taxable, threshold_2)
        + RATES[1]
        * min(
            max(0.0, taxable - threshold_2),
            threshold_3 - threshold_2,
        )
        + RATES[2]
        * min(
            max(0.0, taxable - threshold_3),
            threshold_4 - threshold_3,
        )
        + RATES[3] * max(0.0, taxable - threshold_4)
    )


def _formula_grid() -> list[tuple[str, int]]:
    cases: list[tuple[str, int]] = []
    for filing_status, official in OFFICIAL_THRESHOLDS.items():
        pinned = PINNED_POLICYENGINE_THRESHOLDS[filing_status]
        incomes = {
            -1,
            0,
            1,
            1_000_000,
            500_000_000,
            *(
                threshold + offset
                for threshold in (*official, *pinned)
                for offset in (-1, 0, 1)
            ),
        }
        cases.extend((filing_status, income) for income in sorted(incomes))
    return cases


def test_minnesota_schedule_has_one_exact_direct_oracle_mapping() -> None:
    registry = load_policyengine_registry()
    mapping = registry.mapping_for_legal_id(OUTPUT, country="us")
    fallback = registry.mapping_for_legal_id(
        f"{MODULE}#future_unmapped_output",
        country="us",
    )

    assert mapping is not None
    assert mapping.match_type == "exact"
    assert mapping.mapping_type == "direct_variable"
    assert mapping.policyengine_variable == "mn_basic_tax"
    assert (
        mapping.entity,
        mapping.period,
        mapping.unit,
        mapping.comparison,
    ) == ("tax_unit", "year", "USD", "money")

    assert fallback is not None
    assert fallback.legal_id == "us-mn:"
    assert fallback.match_type == "prefix"
    assert fallback.mapping_type == "not_comparable"
    assert fallback.candidate_priority == "P4"


def test_minnesota_official_schedule_matches_pinned_policyengine_formula_grid() -> None:
    policyengine_us = pytest.importorskip("policyengine_us")
    cases = _formula_grid()
    people = {}
    tax_units = {}
    families = {}
    spm_units = {}
    households = {}
    expected = []

    for index, (filing_status, income) in enumerate(cases):
        person = f"person_{index}"
        members = [person]
        people[person] = {"age": {2026: 40}}
        tax_units[f"tax_unit_{index}"] = {
            "members": members,
            "mn_taxable_income": {2026: income},
            "filing_status": {2026: filing_status},
        }
        families[f"family_{index}"] = {"members": members}
        spm_units[f"spm_unit_{index}"] = {"members": members}
        households[f"household_{index}"] = {
            "members": members,
            "state_code": {2026: "MN"},
        }
        expected.append(
            _official_schedule(income, OFFICIAL_THRESHOLDS[filing_status])
        )

    simulation = policyengine_us.Simulation(
        situation={
            "people": people,
            "tax_units": tax_units,
            "families": families,
            "spm_units": spm_units,
            "households": households,
        }
    )
    raw = simulation.calculate("mn_basic_tax", 2026)
    recovered = _precision_stable_mn_basic_tax(
        sim=simulation,
        year=2026,
        expected_count=len(cases),
    )
    residuals = [
        abs(recovered_value - expected_value)
        for recovered_value, expected_value in zip(
            recovered,
            expected,
            strict=True,
        )
    ]
    raw_precision_residuals = [
        abs(float(raw_value) - recovered_value)
        for raw_value, recovered_value in zip(raw, recovered, strict=True)
    ]

    assert len(cases) == len(raw) == len(recovered) == 100
    assert max(residuals) == pytest.approx(0.81, abs=1e-6)
    assert all(residual <= 1.0 for residual in residuals)
    assert max(raw_precision_residuals) > 1.0
