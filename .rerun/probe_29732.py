#!/usr/bin/env python3
"""Which gate zeroes PE's January SNAP for sc-snap-ecps ecps-29732?"""
from __future__ import annotations
import json, os, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["POLICYENGINE_SKIP_COUNTRY_IMPORTS"] = "1"
import policyengine
import policyengine.provenance.manifest as manifest
def _allow(country_id, runtime_model_version, runtime_data_build_fingerprint=None):
    return manifest.DataCertification(compatibility_basis="probe", certified_for_model_version=runtime_model_version,
        data_build_fingerprint=runtime_data_build_fingerprint, certified_by="probe")
manifest.certify_data_release_compatibility = _allow
try:
    import policyengine.tax_benefit_models.common.model_version as _mv
    _mv.certify_data_release_compatibility = _allow
except ImportError: pass
os.environ.pop("POLICYENGINE_SKIP_COUNTRY_IMPORTS", None)
from policyengine.tax_benefit_models import us as _us
policyengine.us = _us
import numpy as np
from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner, _policyengine_us_simulation
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.populations.populace_us import load_populace_us_cases

cid = sys.argv[1] if len(sys.argv) > 1 else "ecps-29732"
cases = load_populace_us_cases(period="2026-01", sample_size=None, scope=GeographyScope(type="census_state", geoid="45"))
case = {c.case_id: c for c in cases}[cid]
runner = PolicyEngineRunner()
situation = runner._build_situation_from_cases([case], variables=["snap", "is_snap_eligible"])
print("SITUATION people:", json.dumps({p: {k: v for k, v in d.items() if k in ("age","employment_income","is_disabled","is_ssi_disabled","is_permanently_and_totally_disabled","is_full_time_student","is_in_k12_school","is_full_time_college_student","immigration_status","is_citizen","weekly_hours_worked","is_blind")} for p, d in situation["people"].items()}, default=str)[:1500])
sim = _policyengine_us_simulation(situation)
tbs = sim.tax_benefit_system
def val(var, period):
    d = tbs.variables.get(var)
    if d is None: return "N/A"
    p = period if str(d.definition_period).lower() == "month" else "2026"
    a = np.asarray(sim.calculate(var, p))
    return a.tolist() if a.size > 1 else (bool(a[0]) if a.dtype == bool else float(a[0]))
spm_vars = ["snap","snap_normal_allotment","snap_max_allotment","snap_min_allotment","snap_expected_contribution","snap_net_income","snap_gross_income",
            "is_snap_eligible","meets_snap_categorical_eligibility","meets_snap_gross_income_test","meets_snap_net_income_test","meets_snap_asset_test",
            "meets_snap_work_requirements","snap_deductions","snap_earned_income","snap_unearned_income","snap_standard_deduction","snap_earned_income_deduction",
            "snap_excess_shelter_expense_deduction","snap_medical_expense_deduction","snap_dependent_care_deduction","snap_child_support_deduction",
            "snap_unit_size","has_usda_elderly_disabled","takes_up_snap_if_eligible","receives_snap","snap_emergency_allotment"]
person_vars = ["is_snap_ineligible_student","is_snap_immigration_status_eligible","meets_snap_work_requirements","is_snap_abawd_work_requirement_exempt","is_snap_general_work_requirement_exempt","meets_snap_abawd_work_requirements","meets_snap_general_work_requirements","age","is_disabled","employment_income","weekly_hours_worked","is_full_time_student","is_in_k12_school","is_full_time_college_student","is_snap_work_registrant"]
for period in ("2026-01", "2026-06"):
    print(f"\n=== {period} ===")
    for v in spm_vars:
        try: print(f"  {v:45} {val(v, period)}")
        except Exception as e: print(f"  {v:45} ERR {type(e).__name__}: {str(e)[:80]}")
    print("  -- persons --")
    for v in person_vars:
        try: print(f"  {v:45} {val(v, period)}")
        except Exception as e: print(f"  {v:45} ERR {type(e).__name__}: {str(e)[:80]}")
