#!/usr/bin/env python3
"""Round-4 (Astra F1/Q1): which disability inputs does PE's USDA E/D status consume for ecps-29732,
and do the two forcing counterfactuals (person is_ssi_disabled vs unit has_usda_elderly_disabled) coincide?"""
from __future__ import annotations
import copy, json, os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["POLICYENGINE_SKIP_COUNTRY_IMPORTS"] = "1"
import policyengine, policyengine.provenance.manifest as manifest
def _allow(country_id, runtime_model_version, runtime_data_build_fingerprint=None):
    return manifest.DataCertification(compatibility_basis="probe", certified_for_model_version=runtime_model_version, data_build_fingerprint=runtime_data_build_fingerprint, certified_by="probe")
manifest.certify_data_release_compatibility = _allow
try:
    import policyengine.tax_benefit_models.common.model_version as _mv; _mv.certify_data_release_compatibility = _allow
except ImportError: pass
os.environ.pop("POLICYENGINE_SKIP_COUNTRY_IMPORTS", None)
from policyengine.tax_benefit_models import us as _us; policyengine.us = _us
import numpy as np
from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner, _policyengine_us_simulation
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.populations.populace_us import load_populace_us_cases
cases = load_populace_us_cases(period="2026-01", sample_size=None, scope=GeographyScope(type="census_state", geoid="45"))
case = {c.case_id: c for c in cases}["ecps-29732"]
runner = PolicyEngineRunner()
situation = runner._build_situation_from_cases([case], variables=["snap", "is_snap_eligible"])
people = sorted(situation["people"])
print("situation person keys:", {p: sorted(situation["people"][p].keys()) for p in people})
UNIT = ["snap","is_snap_eligible","meets_snap_gross_income_test","meets_snap_categorical_eligibility","has_usda_elderly_disabled","snap_gross_income"]
PERSON = ["age","is_disabled","meets_ssi_disability_criteria","ssi_engaged_in_sga","ssi_earned_income","employment_income","is_blind","is_ssi_disabled","social_security_disability","is_permanently_disabled_veteran","is_surviving_spouse_of_disabled_veteran","is_surviving_child_of_disabled_veteran","is_usda_disabled","is_usda_elderly"]
def readout(sit):
    sim = _policyengine_us_simulation(sit); tbs = sim.tax_benefit_system; out = {"unit": {}, "person": {}}
    for v in UNIT:
        d = tbs.variables[v]; p = "2026-01" if str(d.definition_period).lower()=="month" else "2026"
        a = np.asarray(sim.calculate(v, p)); out["unit"][v] = bool(a[0]) if a.dtype==bool else round(float(a[0]), 6)
    for v in PERSON:
        d = tbs.variables.get(v)
        if d is None: out["person"][v] = "N/A"; continue
        p = "2026-01" if str(d.definition_period).lower()=="month" else "2026"
        a = np.asarray(sim.calculate(v, p)); out["person"][v] = [bool(x) if a.dtype==bool else round(float(x), 4) for x in a]
    try:
        out["sga_non_blind_2026"] = float(sim.tax_benefit_system.parameters("2026-01").gov.ssa.sga.non_blind)
    except Exception as e:
        out["sga_non_blind_2026"] = f"ERR {e}"
    return out
res = {"people_order": people, "base": readout(situation)}
def force_person(idx, var):
    cf = copy.deepcopy(situation); cf["people"][people[idx]][var] = {2026: True}; return readout(cf)
res["force_is_ssi_disabled_m0"] = force_person(0, "is_ssi_disabled")
res["force_meets_ssi_disability_criteria_m0"] = force_person(0, "meets_ssi_disability_criteria")
cf = copy.deepcopy(situation)
for i in (0, 2):
    if i < len(people): cf["people"][people[i]]["meets_ssi_disability_criteria"] = {2026: True}
res["force_meets_ssi_disability_criteria_m0_m2"] = readout(cf)
cf = copy.deepcopy(situation)
ukey = [k for k in cf if k.startswith("spm_unit")][0]
uname = sorted(cf[ukey])[0]
cf[ukey][uname]["has_usda_elderly_disabled"] = {2026: True}
res["force_has_usda_elderly_disabled_unit"] = readout(cf)
print(json.dumps(res, indent=1))
