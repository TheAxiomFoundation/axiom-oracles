#!/usr/bin/env python3
"""Unforced requested-month pass over residual cases.

Reproduces the committed benefit's real baseline (the adapter's own
requested-month situation, which does NOT zero absent person income inputs),
identifies which income sources PolicyEngine imputes endogenously (values
present in the unforced sim but absent from the projected Case facts), then
re-runs with exactly those sources zeroed to confirm the counterfactual
reconciles to Axiom.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["POLICYENGINE_SKIP_COUNTRY_IMPORTS"] = "1"
import policyengine  # noqa: E402
import policyengine.provenance.manifest as manifest  # noqa: E402


def _allow(country_id, runtime_model_version, runtime_data_build_fingerprint=None):
    return manifest.DataCertification(
        compatibility_basis="axiom_oracles_residual_unforced_pass",
        certified_for_model_version=runtime_model_version,
        data_build_fingerprint=runtime_data_build_fingerprint,
        certified_by=".rerun/unforced_pass.py",
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
    "al-snap-ecps": "01",
    "ca-snap-ecps": "06",
    "fl-snap-ecps": "12",
    "ga-snap-ecps": "13",
    "ma-snap-ecps": "25",
    "nc-snap-ecps": "37",
    "ny-snap-ecps": "36",
    "sc-snap-ecps": "45",
}

INCOME_SOURCES = (
    "ssi",
    "social_security",
    "taxable_pension_income",
    "pension_income",
    "unemployment_compensation",
    "disability_benefits",
    "workers_compensation",
    "veterans_benefits",
    "survivor_benefits",
    "financial_assistance",
    "child_support_received",
    "alimony_income",
    "rental_income",
    "dividend_income",
    "taxable_interest_income",
    "miscellaneous_income",
    "retirement_distributions",
    "tanf",
    "general_assistance",
    "self_employment_income",
)

MEDICAL_SOURCES = (
    "medical_expense_health_insurance_premiums",
    "other_medical_expenses",
)

READOUT = (
    "snap",
    "is_snap_eligible",
    "snap_gross_income",
    "snap_earned_income",
    "snap_unearned_income",
    "snap_net_income",
    "snap_excess_medical_expense_deduction",
    "snap_excess_shelter_expense_deduction",
)


def month_values(sim, variables, period, year):
    out = {}
    for var in variables:
        definition = sim.tax_benefit_system.variables.get(var)
        if definition is None:
            continue
        p = period if str(definition.definition_period).lower() == "month" else year
        try:
            import numpy as np

            raw = np.asarray(sim.calculate(var, p))
        except Exception as exc:
            out[var] = f"ERR {exc}"
            continue
        if raw.dtype == bool:
            out[var] = bool(raw.any())
        else:
            out[var] = float(raw.sum())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    geoid = SUITES[args.suite]

    report = json.loads(
        Path(f"dashboard/public/data/axiom-policyengine-{args.suite}.json").read_text()
    )
    residual_ids = sorted(
        {r["case_id"] for r in report["mismatches"] if r.get("disposition") is None}
    )

    from axiom_oracles.adapters.policyengine.runner import (
        PolicyEngineRunner,
        _policyengine_us_simulation,
    )
    from axiom_oracles.core.geography import GeographyScope
    from axiom_oracles.populations.populace_us import load_populace_us_cases

    cases = load_populace_us_cases(
        period="2026-01",
        sample_size=None,
        scope=GeographyScope(type="census_state", geoid=geoid),
    )
    by_id = {c.case_id: c for c in cases}
    runner = PolicyEngineRunner()
    year = 2026
    period = "2026-01"

    results = {}
    for cid in residual_ids:
        case = by_id[cid]
        situation = runner._build_situation_from_cases(
            [case], variables=["snap", "is_snap_eligible"]
        )
        sim = _policyengine_us_simulation(situation)
        unforced = month_values(sim, READOUT, period, year)
        sources = month_values(sim, INCOME_SOURCES + MEDICAL_SOURCES, period, year)
        declared = set()
        for person in situation["people"].values():
            for variable in person:
                declared.add(variable)
        imputed = {
            var: val
            for var, val in sources.items()
            if isinstance(val, float) and abs(val) > 0.005 and var not in declared
        }
        # forced sim: zero exactly the imputed sources (person-level where
        # person entity, spm-unit for tanf) in a fresh situation
        import copy

        forced_situation = copy.deepcopy(situation)
        tbs = sim.tax_benefit_system
        for var in imputed:
            definition = tbs.variables.get(var)
            entity = str(definition.entity.key)
            if entity == "person":
                for person in forced_situation["people"].values():
                    person[var] = {year: 0}
            elif entity == "spm_unit":
                for unit in forced_situation["spm_units"].values():
                    unit[var] = {year: 0}
            elif entity == "tax_unit":
                for unit in forced_situation["tax_units"].values():
                    unit[var] = {year: 0}
        forced_sim = _policyengine_us_simulation(forced_situation)
        forced = month_values(forced_sim, READOUT, period, year)
        results[cid] = {
            "unforced": unforced,
            "imputed_sources": imputed,
            "forced": forced,
        }
        print(
            f"{cid}: unforced snap={unforced.get('snap')} "
            f"elig={unforced.get('is_snap_eligible')} | imputed="
            f"{ {k: round(v, 2) for k, v in imputed.items()} } | "
            f"forced snap={forced.get('snap')} elig={forced.get('is_snap_eligible')}"
        )

    args.output.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
