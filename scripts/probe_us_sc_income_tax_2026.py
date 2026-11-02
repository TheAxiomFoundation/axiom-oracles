#!/usr/bin/env python3
"""Positive probes for the PolicyEngine-US 2026 South Carolina income tax.

The generic ``us-sc:`` oracle fallback cannot establish that PolicyEngine has
an income-tax surface.  These cases exercise the actual surface pinned by the
US conformance universe: SCIAD and schedule tax, the two-wage-earner credit,
the net-capital-gain deduction, and the new 200-dollar EITC cap.

Run against the conformance release:

    uv run --python 3.13 --with policyengine-us==1.767.3 \
        python scripts/probe_us_sc_income_tax_2026.py
"""

from __future__ import annotations

import importlib.metadata as metadata
import math

import numpy as np
from policyengine_us import Simulation
from policyengine_us.system import system


EXPECTED_POLICYENGINE_US_VERSION = "1.767.3"
YEAR = 2026
OUTPUTS = (
    "sc_sciad",
    "sc_net_capital_gain_deduction",
    "sc_taxable_income",
    "sc_income_tax_before_non_refundable_credits",
    "sc_two_wage_earner_credit_potential",
    "sc_eitc_potential",
    "sc_income_tax_before_refundable_credits",
    "sc_income_tax",
)
DIRECT_ORACLE_VARIABLES = {
    "sc_sciad",
    "sc_net_capital_gain_deduction",
    "sc_taxable_income",
    "sc_income_tax_before_non_refundable_credits",
    "sc_two_wage_earner_credit_potential",
    "sc_eitc_potential",
}


def _simulation(
    people: dict[str, dict],
    *,
    tax_unit_inputs: dict | None = None,
) -> Simulation:
    members = list(people)
    return Simulation(
        situation={
            "people": people,
            "tax_units": {
                "tax_unit": {
                    "members": members,
                    **(tax_unit_inputs or {}),
                }
            },
            "families": {"family": {"members": members}},
            "spm_units": {"spm_unit": {"members": members}},
            "households": {
                "household": {
                    "members": members,
                    "state_code": {YEAR: "SC"},
                }
            },
        }
    )


def _cases() -> dict[str, Simulation]:
    return {
        "single_wages_sciad_and_schedule": _simulation(
            {
                "head": {
                    "age": {YEAR: 40},
                    "employment_income": {YEAR: 50_000},
                }
            }
        ),
        "joint_dual_earners": _simulation(
            {
                "head": {
                    "age": {YEAR: 40},
                    "employment_income": {YEAR: 40_000},
                },
                "spouse": {
                    "age": {YEAR: 40},
                    "employment_income": {YEAR: 40_000},
                },
            }
        ),
        "single_long_term_capital_gain": _simulation(
            {
                "head": {
                    "age": {YEAR: 40},
                    "employment_income": {YEAR: 50_000},
                    "long_term_capital_gains": {YEAR: 20_000},
                }
            }
        ),
        # Supplying the already-computed federal EITC isolates the state match
        # and Act 110 cap from unrelated federal eligibility mechanics.
        "forced_federal_eitc_cap": _simulation(
            {
                "head": {
                    "age": {YEAR: 40},
                    "employment_income": {YEAR: 50_000},
                }
            },
            tax_unit_inputs={"eitc": {YEAR: 1_000}},
        ),
    }


EXPECTED = {
    "single_wages_sciad_and_schedule": {
        "sc_sciad": 12_280,
        "sc_taxable_income": 37_720,
        "sc_income_tax_before_non_refundable_credits": 999.212,
        "sc_income_tax": 999.212,
    },
    "joint_dual_earners": {
        "sc_sciad": 30_000,
        "sc_taxable_income": 50_000,
        "sc_income_tax_before_non_refundable_credits": 1_639,
        "sc_two_wage_earner_credit_potential": 280,
        "sc_income_tax_before_refundable_credits": 1_359,
        "sc_income_tax": 1_359,
    },
    "single_long_term_capital_gain": {
        "sc_sciad": 6_820,
        "sc_net_capital_gain_deduction": 8_800,
        "sc_taxable_income": 54_380,
        "sc_income_tax_before_non_refundable_credits": 1_867.198,
    },
    "forced_federal_eitc_cap": {
        "sc_eitc_potential": 200,
        "sc_income_tax_before_refundable_credits": 799.212,
        "sc_income_tax": 799.212,
    },
}


def _values(simulation: Simulation) -> dict[str, float]:
    return {
        variable: float(simulation.calculate(variable, YEAR).sum())
        for variable in OUTPUTS
    }


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=0.001):
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def _check_parameters() -> None:
    parameters = system.parameters(f"{YEAR}-01-01").gov.states.sc.tax.income
    checks = {
        "lower_rate": (parameters.rates.rates[0], 0.0199),
        "upper_rate": (parameters.rates.rates[1], 0.0521),
        "upper_floor": (parameters.rates.thresholds[1], 30_000),
        "capital_gain_rate": (
            parameters.deductions.net_capital_gain.rate,
            0.44,
        ),
        "under_65_retirement_cap": (
            parameters.subtractions.retirement.cap.amounts[0],
            3_000,
        ),
        "retirement_age_break": (
            parameters.subtractions.retirement.cap.thresholds[1],
            65,
        ),
        "two_wage_rate": (
            parameters.credits.two_wage_earner.rate.rates[0],
            0.007,
        ),
        "two_wage_cap": (
            parameters.credits.two_wage_earner.rate.thresholds[1],
            50_000,
        ),
        "eitc_rate": (parameters.credits.eitc.rate, 1.25),
        "eitc_cap": (parameters.credits.eitc.max, 200),
    }
    for label, (actual, expected) in checks.items():
        _assert_close(float(actual), float(expected), label)

    sciad_cells = {
        "amount": {
            "SINGLE": 15_000,
            "SEPARATE": 15_000,
            "HEAD_OF_HOUSEHOLD": 22_500,
            "JOINT": 30_000,
            "SURVIVING_SPOUSE": 30_000,
        },
        "phase_out.start": {
            "SINGLE": 40_000,
            "SEPARATE": 40_000,
            "HEAD_OF_HOUSEHOLD": 60_000,
            "JOINT": 80_000,
            "SURVIVING_SPOUSE": 80_000,
        },
        "phase_out.width": {
            "SINGLE": 55_000,
            "SEPARATE": 55_000,
            "HEAD_OF_HOUSEHOLD": 82_500,
            "JOINT": 110_000,
            "SURVIVING_SPOUSE": 110_000,
        },
    }
    for path, expected_cells in sciad_cells.items():
        node = parameters.deductions.sciad
        for component in path.split("."):
            node = getattr(node, component)
        for filing_status, expected in expected_cells.items():
            _assert_close(
                float(getattr(node, filing_status)),
                float(expected),
                f"sciad.{path}.{filing_status}",
            )

    # PolicyEngine represents the statutory subtraction form as a marginal
    # scale.  This proves the two forms meet at the enacted breakpoint.
    schedule_at_floor = float(parameters.rates.calc(np.asarray([30_000]))[0])
    statutory_at_floor = 0.0521 * 30_000 - 966
    _assert_close(schedule_at_floor, 597, "schedule_at_floor")
    _assert_close(statutory_at_floor, schedule_at_floor, "statutory_continuity")


def main() -> int:
    installed = metadata.version("policyengine-us")
    if installed != EXPECTED_POLICYENGINE_US_VERSION:
        print(
            "ERROR: expected policyengine-us "
            f"{EXPECTED_POLICYENGINE_US_VERSION}, got {installed}"
        )
        return 1

    missing_variables = DIRECT_ORACLE_VARIABLES - set(system.variables)
    if missing_variables:
        print(f"ERROR: missing mapped variables: {sorted(missing_variables)}")
        return 1

    _check_parameters()
    results = {name: _values(simulation) for name, simulation in _cases().items()}
    for case_name, expected_values in EXPECTED.items():
        for variable, expected in expected_values.items():
            _assert_close(
                results[case_name][variable],
                expected,
                f"{case_name}.{variable}",
            )

    print(f"policyengine-us {installed}; validation_year={YEAR}")
    for case_name, values in results.items():
        rendered = ", ".join(f"{name}={values[name]:.3f}" for name in OUTPUTS)
        print(f"{case_name}: {rendered}")
    print(
        "VERDICT: positive_sc_income_tax_surface=True; "
        "sciad=True; schedule=True; two_wage_earner=True; "
        "net_capital_gain=True; eitc_cap_200=True"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
