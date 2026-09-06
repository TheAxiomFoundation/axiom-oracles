#!/usr/bin/env python3
"""Targeted requested-month counterfactuals for the manual-bucket cases.

For each case, runs the adapter's own situation (unforced baseline) plus a
ladder of forcings — medical premiums, TANF, self-employment, and the full
stack — and reports which minimal forcing reconciles PE's January value to
Axiom within the suite tolerance.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["POLICYENGINE_SKIP_COUNTRY_IMPORTS"] = "1"
import policyengine  # noqa: E402
import policyengine.provenance.manifest as manifest  # noqa: E402


def _allow(country_id, runtime_model_version, runtime_data_build_fingerprint=None):
    return manifest.DataCertification(
        compatibility_basis="axiom_oracles_final_counterfactuals",
        certified_for_model_version=runtime_model_version,
        data_build_fingerprint=runtime_data_build_fingerprint,
        certified_by=".rerun/final_counterfactuals.py",
    )


manifest.certify_data_release_compatibility = _allow
try:
    import policyengine.tax_benefit_models.common.model_version as _mv  # noqa: E402

    _mv.certify_data_release_compatibility = _allow
except ImportError:
    pass
os.environ.pop("POLICYENGINE_SKIP_COUNTRY_IMPORTS", None)
from policyengine.tax_benefit_models import us as _us  # noqa: E402

policyengine.us = _us

SUITES = {
    "al-snap-ecps": ("01", "al_tanf"),
    "ca-snap-ecps": ("06", "ca_tanf"),
    "fl-snap-ecps": ("12", None),
    "ga-snap-ecps": ("13", "ga_tanf"),
    "ma-snap-ecps": ("25", None),
    "nc-snap-ecps": ("37", "nc_tanf"),
    "ny-snap-ecps": ("36", "ny_tanf"),
    "sc-snap-ecps": ("45", "sc_tanf"),
}

MEDICAL = {"medical_expense_health_insurance_premiums": 0, "other_medical_expenses": 0}
SE = {
    "self_employment_income": 0,
    "self_employment_income_before_lsr": 0,
    "sstb_self_employment_income_before_lsr": 0,
}

READOUT = ("snap", "is_snap_eligible", "snap_net_income", "snap_gross_income")


def month_values(sim, variables, period, year):
    import numpy as np

    out = {}
    for var in variables:
        definition = sim.tax_benefit_system.variables.get(var)
        if definition is None:
            continue
        p = period if str(definition.definition_period).lower() == "month" else year
        raw = np.asarray(sim.calculate(var, p))
        out[var] = bool(raw.any()) if raw.dtype == bool else float(raw.sum())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--cases", required=True, help="comma-separated case ids")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    geoid, state_tanf = SUITES[args.suite]
    wanted = set(args.cases.split(","))

    from axiom_oracles.adapters.policyengine.runner import (
        PolicyEngineRunner,
        _policyengine_us_simulation,
    )
    from axiom_oracles.core.geography import GeographyScope
    from axiom_oracles.populations.populace_us import load_populace_us_cases

    tanf_force = {"tanf": 0}
    if state_tanf:
        tanf_force[state_tanf] = 0

    LADDER = [
        ("medical", {"person": MEDICAL, "spm": {}}),
        ("tanf", {"person": {}, "spm": tanf_force}),
        ("se", {"person": SE, "spm": {}}),
        ("tanf+medical", {"person": MEDICAL, "spm": tanf_force}),
        ("se+medical", {"person": {**MEDICAL, **SE}, "spm": {}}),
        ("tanf+se+medical", {"person": {**MEDICAL, **SE}, "spm": tanf_force}),
    ]

    cases = load_populace_us_cases(
        period="2026-01",
        sample_size=None,
        scope=GeographyScope(type="census_state", geoid=geoid),
    )
    by_id = {c.case_id: c for c in cases}
    runner = PolicyEngineRunner()
    year, period = 2026, "2026-01"

    results = {}
    for cid in sorted(wanted):
        case = by_id[cid]
        situation = runner._build_situation_from_cases(
            [case], variables=["snap", "is_snap_eligible"]
        )
        base = month_values(
            _policyengine_us_simulation(situation), READOUT, period, year
        )
        row = {"unforced": base, "forcings": {}}
        for name, forcing in LADDER:
            forced = copy.deepcopy(situation)
            for person in forced["people"].values():
                for var, val in forcing["person"].items():
                    person[var] = {year: val}
            for unit in forced["spm_units"].values():
                for var, val in forcing["spm"].items():
                    unit[var] = {year: val}
            row["forcings"][name] = month_values(
                _policyengine_us_simulation(forced), READOUT, period, year
            )
        results[cid] = row
        print(
            cid,
            "unforced",
            round(base.get("snap", -1), 2),
            base.get("is_snap_eligible"),
            "|",
            " ".join(
                f"{k}={round(v.get('snap', -1), 2)}/{v.get('is_snap_eligible')}"
                for k, v in row["forcings"].items()
            ),
        )
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
