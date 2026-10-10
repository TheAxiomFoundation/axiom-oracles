"""PolicyEngine-US's treatment of tax-exempt interest in the benefit lanes (live).

The benefit suites compare Axiom with PolicyEngine on household Cases that
carry tax-exempt interest (axiom-oracles#567). The Axiom input projection
counts it for SNAP, TANF and Medicaid MAGI exactly like taxable interest, and
leaves all interest out of SSI (tests/test_tax_exempt_interest_benefit_inputs.py
has the law). These tests replay one person in PolicyEngine-US and pin the
counterpart's side of each claim, so the two engines are known to read the
same household the same way wherever the law lets them:

* SNAP, TANF (the federal source list) and Medicaid MAGI give a dollar of
  tax-exempt interest and a dollar of taxable interest the same weight.
* SSI counts both, which 42 USC 1382a(b)(23) does not
  (__PE_SSI_ISSUE__). That last test is a tripwire: when PolicyEngine
  implements the exclusion it fails, and the ssi-ecps dispositions citing the
  issue should be retired with it.

Expected amounts come from the inputs alone: 12,000 a year is 1,000 a month,
and a filer with no other income has AGI equal to the taxable interest.

Without policyengine-us these skip, unless
AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE=1 (set in CI's policyengine-live job)
turns the skip into a failure.
"""

from __future__ import annotations

import os

import pytest

REQUIRE_LIVE = os.environ.get("AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE") == "1"
YEAR = 2026
MONTH = "2026-01"
ANNUAL_INTEREST = 12_000


def _simulation(**person_income):
    try:
        from policyengine_us import Simulation
    except ImportError:
        if REQUIRE_LIVE:
            raise
        pytest.skip("policyengine-us is not installed")
    situation = {
        "people": {
            "adult": {
                # Aged, so SNAP counts the member's income in full (no work-
                # requirement proration), with SSI pinned to zero as the
                # oracle's PolicyEngine runner pins every mapped income source.
                "age": {YEAR: 70},
                "ssi": {YEAR: 0},
                **{name: {YEAR: value} for name, value in person_income.items()},
            }
        },
        "tax_units": {"tax_unit": {"members": ["adult"]}},
        "spm_units": {"spm_unit": {"members": ["adult"]}},
        "families": {"family": {"members": ["adult"]}},
        "marital_units": {"marital_unit": {"members": ["adult"]}},
        "households": {
            "household": {"members": ["adult"], "state_code": {YEAR: "TX"}}
        },
    }
    return Simulation(situation=situation)


def _value(simulation, variable, period):
    return float(simulation.calculate(variable, period)[0])


@pytest.fixture(scope="module")
def simulations():
    return {
        "none": _simulation(),
        "taxable": _simulation(taxable_interest_income=ANNUAL_INTEREST),
        "exempt": _simulation(tax_exempt_interest_income=ANNUAL_INTEREST),
    }


@pytest.mark.parametrize(
    ("variable", "period", "expected"),
    [
        # 7 CFR 273.9(b)(2)(v): interest is SNAP unearned income.
        ("snap_unearned_income", MONTH, ANNUAL_INTEREST / 12),
        # The federal TANF unearned-income source list.
        ("tanf_gross_unearned_income", MONTH, ANNUAL_INTEREST / 12),
        # 26 USC 36B(d)(2)(B): AGI (taxable interest) or the (ii) add-back.
        ("medicaid_magi", YEAR, ANNUAL_INTEREST),
    ],
)
def test_policyengine_weighs_tax_exempt_interest_like_taxable_interest(
    simulations, variable, period, expected
) -> None:
    assert _value(simulations["none"], variable, period) == 0
    assert _value(simulations["taxable"], variable, period) == pytest.approx(expected)
    assert _value(simulations["exempt"], variable, period) == pytest.approx(expected)


def test_policyengine_ssi_still_counts_interest(simulations) -> None:
    """Tripwire for __PE_SSI_ISSUE__ (see the module docstring)."""
    for arm in ("taxable", "exempt"):
        assert _value(simulations[arm], "ssi_unearned_income", YEAR) == pytest.approx(
            ANNUAL_INTEREST
        ), (
            "PolicyEngine no longer counts interest as SSI unearned income: "
            "retire the ssi-ecps dispositions that cite __PE_SSI_ISSUE__ and this test"
        )
