"""Live FY2026 SNAP income-standard checks against pinned PolicyEngine US.

The expected limits are the selected 48-state/DC outputs in the protected
rulespec-us FY2026 income-eligibility-standards companion tests. This checks
PolicyEngine behavior, not RuleSpec execution or Arizona benefit parity.
"""

from __future__ import annotations

import os

import pytest


PERIOD = "2026-01"
# Household size, 100% net limit, 130% gross limit, 165% gross limit.
LIMITS = ((1, 1305, 1696, 2152), (8, 4513, 5867, 7446), (9, 4972, 6463, 8203))


@pytest.fixture(scope="module")
def pe():
    try:
        import policyengine_us
        from policyengine_us.variables.gov.usda.snap.income.snap_income_standard_helpers import (
            snap_monthly_income_standard,
        )
    except ImportError:
        if os.environ.get("AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE") == "1":
            pytest.fail("The pinned PolicyEngine US SNAP standard helper is required")
        pytest.skip("PolicyEngine US SNAP standard helper is not installed")
    return policyengine_us, snap_monthly_income_standard


def _simulation(pe, rows):
    people = {f"p{i}": {"age": {2026: 30}} for i, _ in enumerate(rows)}
    spm_units = {
        f"s{i}": {
            "members": [f"p{i}"],
            "snap_unit_size": {PERIOD: size},
            "snap_gross_test_income": {PERIOD: gross},
            "snap_net_income": {PERIOD: net},
        }
        for i, (size, net, gross) in enumerate(rows)
    }
    tax_units = {
        f"t{i}": {"members": [f"p{i}"], "filing_status": {2026: "SINGLE"}}
        for i, _ in enumerate(rows)
    }
    households = {
        f"h{i}": {"members": [f"p{i}"], "state_code_str": {2026: "AZ"}}
        for i, _ in enumerate(rows)
    }
    families = {f"f{i}": {"members": [f"p{i}"]} for i, _ in enumerate(rows)}
    marital_units = {f"m{i}": {"members": [f"p{i}"]} for i, _ in enumerate(rows)}
    return pe.Simulation(
        situation={
            "people": people,
            "spm_units": spm_units,
            "tax_units": tax_units,
            "households": households,
            "families": families,
            "marital_units": marital_units,
        }
    )


def test_monthly_standard_matches_selected_fy2026_limits(pe):
    from policyengine_core.periods import period

    policyengine_us, snap_monthly_income_standard = pe
    sim = _simulation(policyengine_us, [(size, 0, 0) for size, *_ in LIMITS])

    class SPMUnit:
        def __call__(self, name, _period):
            return sim.calculate(name, PERIOD)

        def household(self, name, _period):
            return sim.calculate(name, 2026)

    for rate, index in ((1.0, 1), (1.3, 2), (1.65, 3)):
        actual = snap_monthly_income_standard(
            SPMUnit(), period(PERIOD), sim.tax_benefit_system.parameters, rate
        )
        assert [int(value) for value in actual] == [row[index] for row in LIMITS]


def test_net_and_gross_tests_flip_one_dollar_above_fy2026_limits(pe):
    policyengine_us, _ = pe
    rows = [
        (size, net + offset, gross + offset)
        for size, net, gross, _ in LIMITS
        for offset in (0, 1)
    ]
    sim = _simulation(policyengine_us, rows)

    assert sim.calculate("meets_snap_net_income_test", PERIOD).tolist() == [
        True,
        False,
    ] * len(LIMITS)
    assert sim.calculate("meets_snap_gross_income_test", PERIOD).tolist() == [
        True,
        False,
    ] * len(LIMITS)
