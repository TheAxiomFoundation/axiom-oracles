#!/usr/bin/env python3
"""Counterfactual: give PE the same E/D status axiom's bridge asserts for ecps-29732."""
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
def readout(sit):
    sim = _policyengine_us_simulation(sit); tbs = sim.tax_benefit_system; out = {}
    for v in ["snap","snap_normal_allotment","snap_expected_contribution","snap_net_income","snap_gross_income","is_snap_eligible","meets_snap_gross_income_test","meets_snap_categorical_eligibility","has_usda_elderly_disabled","snap_max_allotment"]:
        d = tbs.variables[v]; p = "2026-01" if str(d.definition_period).lower()=="month" else "2026"
        a = np.asarray(sim.calculate(v, p)); out[v] = bool(a[0]) if a.dtype==bool else float(a[0])
    return out
base = readout(situation)
cf = copy.deepcopy(situation)
first = sorted(cf["people"])[0]   # member-0, age 31, DISABLED true in the populace
cf["people"][first]["is_ssi_disabled"] = {2026: True}
forced = readout(cf)
print(json.dumps({"unforced": base, "is_ssi_disabled_forced_member0": forced}, indent=1))
