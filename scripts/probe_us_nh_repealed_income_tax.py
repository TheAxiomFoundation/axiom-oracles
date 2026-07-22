#!/usr/bin/env python3
"""Probe New Hampshire's repealed Chapter 77 surface in PolicyEngine-US.

RSA Chapter 77 was repealed in its entirety by 2021, 91:189, II, effective
January 1, 2025. PolicyEngine-US retains the legacy interest-and-dividends tax
variables, but its ``gov.states.nh.tax.income.in_effect`` parameter is false
from 2025. This probe avoids a vacuous wage-only comparison: it supplies large
positive interest and dividend amounts, proves that the retained model produces
a positive liability in 2024, then proves that both the before-refundable and
final outputs are exactly zero after repeal in 2025 and the 2026 validation year.

Run against the oracle release pinned by ``conformance/us-pe.yaml``::

    uv run --python 3.13 --with policyengine-us==1.767.3 \
        python scripts/probe_us_nh_repealed_income_tax.py

The verdict is the probe evidence cited by the ``us-pe:nh_income_tax``
``oracle_models_repealed_law`` exclusion.
"""

from __future__ import annotations

import importlib.metadata as _md

from policyengine_us import Simulation
from policyengine_us.system import system


EXPECTED_POLICYENGINE_US_VERSION = "1.767.3"
PRE_REPEAL_YEAR = 2024
REPEAL_YEAR = 2025
VALIDATION_YEAR = 2026


def _simulation(year: int) -> Simulation:
    situation = {
        "people": {
            "head": {
                "age": {year: 40},
                "interest_income": {year: 100_000},
                "dividend_income": {year: 100_000},
            }
        },
        "tax_units": {"tax_unit": {"members": ["head"]}},
        "families": {"family": {"members": ["head"]}},
        "spm_units": {"spm_unit": {"members": ["head"]}},
        "households": {
            "household": {
                "members": ["head"],
                "state_code": {year: "NH"},
            }
        },
    }
    return Simulation(situation=situation)


def _outputs(year: int) -> dict[str, float]:
    simulation = _simulation(year)
    return {
        variable: float(simulation.calculate(variable, year).sum())
        for variable in (
            "nh_taxable_income",
            "nh_income_tax_before_refundable_credits",
            "nh_income_tax",
        )
    }


def main() -> int:
    installed_version = _md.version("policyengine-us")
    if installed_version != EXPECTED_POLICYENGINE_US_VERSION:
        print(
            "ERROR: expected policyengine-us "
            f"{EXPECTED_POLICYENGINE_US_VERSION}, got {installed_version}"
        )
        return 1

    results = {
        year: _outputs(year)
        for year in (PRE_REPEAL_YEAR, REPEAL_YEAR, VALIDATION_YEAR)
    }
    print(f"policyengine-us {installed_version}")
    for year, values in results.items():
        parameters = system.parameters(f"{year}-01-01").gov.states.nh.tax.income
        print(
            f"{year}: in_effect={bool(parameters.in_effect)}, "
            f"rate={float(parameters.rate)}, "
            f"nh_taxable_income={values['nh_taxable_income']}, "
            "nh_income_tax_before_refundable_credits="
            f"{values['nh_income_tax_before_refundable_credits']}, "
            f"nh_income_tax={values['nh_income_tax']}"
        )

    pre_repeal = results[PRE_REPEAL_YEAR]
    post_repeal = (results[REPEAL_YEAR], results[VALIDATION_YEAR])
    positive_control = (
        pre_repeal["nh_taxable_income"] > 0
        and pre_repeal["nh_income_tax_before_refundable_credits"] > 0
        and pre_repeal["nh_income_tax"] > 0
    )
    post_repeal_zero = all(
        values["nh_income_tax_before_refundable_credits"] == 0
        and values["nh_income_tax"] == 0
        for values in post_repeal
    )
    print(
        "VERDICT: positive_2024_control="
        f"{positive_control}; post_repeal_2025_2026_zero={post_repeal_zero}; "
        "classification=oracle_models_repealed_law"
    )
    return 0 if positive_control and post_repeal_zero else 1


if __name__ == "__main__":
    raise SystemExit(main())
