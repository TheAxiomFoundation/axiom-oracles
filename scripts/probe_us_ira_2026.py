#!/usr/bin/env python3
"""Probe the two PE-US 1.767.3 surfaces used by Tier-3 scope decisions.

The 2026 ``energy_efficient_home_improvement_credit`` (IRC 25C) probe supplies
enough heat-pump expenditure and tax liability to produce a positive component,
then verifies that the top-level ``in_effect`` gate suppresses both potential
and final credit throughout the validation year.

The ``spm_unit_capped_housing_subsidy`` probe inspects the installed variable's
Census SPM reference and formula, records the indirect HUD parameter values,
and forces its three immediate operands. This isolates the outer SPM
resource-accounting cap from the underlying statutory HUD payment surface.

Run against the exact oracle release with a warm uv cache:

    UV_CACHE_DIR=/private/tmp/axiom-tier3-uv-cache \
    uv run --offline --isolated --no-project --python 3.13 \
      --with policyengine-us==1.767.3 \
      python scripts/probe_us_ira_2026.py
"""

from __future__ import annotations

import importlib.metadata as _md
import inspect

import numpy as np
from policyengine_us import Simulation
from policyengine_us.system import system


EXPECTED_POLICYENGINE_US_VERSION = "1.767.3"
VALIDATION_YEAR = 2026
VALIDATION_INSTANTS = ("2026-01-01", "2026-12-31")


def _base_situation(*, wages: float = 0) -> dict[str, object]:
    return {
        "people": {
            "head": {
                "age": {VALIDATION_YEAR: 40},
                "employment_income": {VALIDATION_YEAR: wages},
            }
        },
        "tax_units": {"tax_unit": {"members": ["head"]}},
        "families": {"family": {"members": ["head"]}},
        "spm_units": {"spm_unit": {"members": ["head"]}},
        "households": {
            "household": {
                "members": ["head"],
                "state_name": {VALIDATION_YEAR: "CA"},
            }
        },
    }


def _amount(simulation: Simulation, variable: str) -> float:
    return float(simulation.calculate(variable, VALIDATION_YEAR).sum())


def _parameter_snapshot(instant: str) -> dict[str, float | bool]:
    parameters = system.parameters(instant)
    tenant_payment = parameters.gov.hud.total_tenant_payment
    return {
        "25c_in_effect": bool(
            parameters.gov.irs.credits.energy_efficient_home_improvement.in_effect
        ),
        "hud_abolition": bool(parameters.gov.hud.abolition),
        "hud_ttp_adjusted_income_share": float(
            tenant_payment.adjusted_income_share
        ),
        "hud_ttp_income_share": float(tenant_payment.income_share),
    }


def _probe_25c() -> dict[str, float]:
    situation = _base_situation(wages=200_000)
    situation["tax_units"]["tax_unit"]["heat_pump_expenditures"] = {
        VALIDATION_YEAR: 50_000
    }
    simulation = Simulation(situation=situation)
    return {
        "component": _amount(
            simulation,
            "capped_heat_pump_heat_pump_water_heater_biomass_stove_boiler_credit",
        ),
        "limit": _amount(
            simulation,
            "energy_efficient_home_improvement_credit_credit_limit",
        ),
        "potential": _amount(
            simulation,
            "energy_efficient_home_improvement_credit_potential",
        ),
        "output": _amount(
            simulation,
            "energy_efficient_home_improvement_credit",
        ),
    }


def _probe_spm_cap() -> tuple[float, str, object]:
    variable = system.variables["spm_unit_capped_housing_subsidy"]
    formula_source = inspect.getsource(variable.formula).strip()
    simulation = Simulation(situation=_base_situation())
    simulation.set_input(
        "housing_assistance",
        VALIDATION_YEAR,
        np.array([30_000.0]),
    )
    simulation.set_input(
        "spm_unit_spm_threshold_housing_portion",
        VALIDATION_YEAR,
        np.array([17_720.0]),
    )
    simulation.set_input(
        "hud_ttp",
        VALIDATION_YEAR,
        np.array([10_000.0]),
    )
    return (
        _amount(simulation, "spm_unit_capped_housing_subsidy"),
        formula_source,
        variable.reference,
    )


def main() -> int:
    installed_version = _md.version("policyengine-us")
    core_version = _md.version("policyengine-core")
    print(
        f"policyengine-us {installed_version}; "
        f"policyengine-core {core_version}"
    )
    if installed_version != EXPECTED_POLICYENGINE_US_VERSION:
        print(
            "ERROR: expected policyengine-us "
            f"{EXPECTED_POLICYENGINE_US_VERSION}, got {installed_version}"
        )
        return 1

    transition_gate = bool(
        system.parameters(
            "2025-12-31"
        ).gov.irs.credits.energy_efficient_home_improvement.in_effect
    )
    snapshots = {
        instant: _parameter_snapshot(instant)
        for instant in VALIDATION_INSTANTS
    }
    print(f"25C transition control at 2025-12-31: {transition_gate}")
    for instant, snapshot in snapshots.items():
        print(f"{instant}: {snapshot}")

    credit = _probe_25c()
    print(
        "25C forced activation "
        "(employment_income=200000, heat_pump_expenditures=50000): "
        f"{credit}"
    )

    spm_output, spm_formula, spm_reference = _probe_spm_cap()
    print(f"SPM variable reference: {spm_reference}")
    print("SPM installed formula:")
    print(spm_formula)
    print(
        "SPM forced operands "
        "(housing_assistance=30000, housing_portion=17720, hud_ttp=10000): "
        f"{spm_output}"
    )

    formula_tokens = (
        "housing_assistance",
        "spm_unit_spm_threshold_housing_portion",
        "hud_ttp",
        "min_",
        "max_",
    )
    checks = {
        "25c_transition_control_is_on": transition_gate,
        "25c_off_throughout_2026": all(
            not snapshot["25c_in_effect"]
            for snapshot in snapshots.values()
        ),
        "hud_live_throughout_2026": all(
            not snapshot["hud_abolition"]
            for snapshot in snapshots.values()
        ),
        "hud_ttp_shares_match": all(
            snapshot["hud_ttp_adjusted_income_share"] == 0.30
            and snapshot["hud_ttp_income_share"] == 0.10
            for snapshot in snapshots.values()
        ),
        "25c_positive_component_is_suppressed": credit
        == {
            "component": 2_000.0,
            "limit": 36_734.0,
            "potential": 0.0,
            "output": 0.0,
        },
        "spm_formula_matches_outer_cap": all(
            token in spm_formula for token in formula_tokens
        )
        and "parameters(" not in spm_formula,
        "spm_reference_is_census": "census" in str(spm_reference).lower(),
        "spm_forced_output_is_7720": spm_output == 7_720.0,
    }
    print(f"CHECKS: {checks}")
    passed = all(checks.values())
    print(
        "VERDICT: "
        f"passed={passed}; "
        "25C=oracle_models_repealed_law; "
        "spm_unit_capped_housing_subsidy=technical"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
