#!/usr/bin/env python3
"""Extract grounded FY2024 SNAP QC and engine features to the user cache."""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from axiom_oracles.bridges.rulespec_overlay import build_overlay, load_overlay_spec
from axiom_oracles.bridges.snap_populace import (
    axiom_rules_env, load_base_inputs, month_period, outputs_by_reference,
    output_to_python, resolve_axiom_binary, resolve_workspace_root,
)
from axiom_oracles.bridges.snap_qc_compare import (
    NOMINAL_PERIOD, QC_JURISDICTIONS, _LABELS, _load_base_member,
    _output_id_by_label, _run_cases, map_qc_unit, sua_amounts_from_overlay,
)
import axiom_oracles.bridges.snap_qc_compare as qc_compare
from axiom_oracles.populations.snap_qc import load_qc_units
from axiom_oracles.bridges.snap_qc_compare import FY2024_MAX_ALLOTMENT_48_STATES, FY2024_MAX_ALLOTMENT_ADDITIONAL_MEMBER

SEED = 294
STATES = ("co", "ny", "ca", "az", "ga", "md", "tx")
CACHE = Path(os.environ.get("AXIOM_QC_ERROR_CACHE", Path.home() / ".cache/axiom-oracles/qc-error-pilot"))

FED = "us:regulations/7-cfr/273/10#"
EXTRA_OUTPUTS = {
    "earned_income_deduction": FED + "snap_earned_income_deduction_for_net_income",
    "net_income_before_shelter": FED + "snap_net_income_before_shelter",
    "uncapped_excess_shelter": FED + "snap_excess_shelter_cost",
    "excess_shelter_deduction": FED + "snap_excess_shelter_deduction_for_net_income",
    "net_income": FED + "snap_net_monthly_income",
    "minimum_benefit": FED + "snap_minimum_benefit",
    "benefit_before_minimum": FED + "snap_calculated_monthly_allotment_before_minimums",
    "issued_allotment": FED + "snap_monthly_allotment",
}


def value(result, output_id):
    out = outputs_by_reference(result.get("outputs", {})).get(output_id)
    return None if out is None else output_to_python(out)


def proxy(unit, kind: str, delta: float = 10.0):
    """Copy a unit and perturb one bridge-consumed, documented QC input."""
    p = SimpleNamespace(**unit.__dict__)
    p.earned_income = lambda: unit.earned_income() + (delta if kind == "earned" else 0)
    p.unearned_income = lambda: unit.unearned_income() + (delta if kind == "unearned" else 0)
    p.shelter_expense = (unit.shelter_expense or 0) + (delta if kind == "shelter" else 0)
    p.dependent_care_expense = (unit.dependent_care_expense or 0) + (delta if kind == "dependent_care" else 0)
    expected = SimpleNamespace(**unit.expected.__dict__)
    if kind == "child_support":
        expected.child_support_deduction = (unit.expected.child_support_deduction or 0) + delta
    if kind == "medical" and unit.unit_has_elderly_or_disabled:
        expected.medical_deduction = (unit.expected.medical_deduction or 0) + delta
    p.expected = expected
    return p


def raw_row(unit, state, exclusions):
    members = unit.members
    ages = [m.age for m in members if m.age is not None]
    status, amterr = unit.expected.status, unit.expected.error_amount
    return {
        "case_id": unit.case_id, "state": state, "yrmonth": unit.yrmonth,
        "label_error": int(status in (2, 3) and (amterr or 0) > 0),
        "status": status, "error_amount": amterr, "issued_benefit": float(unit.raw["RAWBEN"]),
        "verified_benefit": unit.expected.benefit, "weight": unit.weight,
        "household_size": unit.certified_size, "member_count": len(members),
        "child_count": sum(a < 18 for a in ages), "elderly_count": sum(a >= 60 for a in ages),
        "disabled_or_elderly": int(bool(unit.unit_has_elderly_or_disabled)),
        "earned_income": unit.earned_income(), "unearned_income": unit.unearned_income(),
        "shelter_expense": unit.shelter_expense, "utility_amount": unit.utility_amount,
        "utility_tier": unit.utility_tier.value, "medical_expenses": unit.medical_expenses,
        "dependent_care_expense": unit.dependent_care_expense,
        "child_support_expense": unit.child_support_expense,
        "homeless": int(bool(unit.homeless)), "categorically_eligible": int(bool(unit.categorically_eligible)),
        "liquid_resources": unit.liquid_resources, "excluded_universe": exclusions,
    }


def extract_state(state, rulespec_root, binary):
    jurisdiction = f"us-{state}"
    cfg = QC_JURISDICTIONS[jurisdiction]
    units, log = load_qc_units(2024, state_fips=cfg.state_fips)
    units = sorted(units, key=lambda u: u.case_id)
    spec = load_overlay_spec(cfg.overlay)
    output_map = _output_id_by_label(cfg, spec.module_id_rewrites)
    stage_ids = {x.stage: output_map[x.label] for x in _LABELS}
    requested = list(dict.fromkeys([*output_map.values(), *EXTRA_OUTPUTS.values()]))
    root = resolve_workspace_root(None)
    base = load_base_inputs(rulespec_root / cfg.template)
    member = _load_base_member(rulespec_root / cfg.template, cfg.base.relation_id)
    benefit_id = stage_ids["benefit"]
    overlay = Path(tempfile.mkdtemp(prefix=f"qc-pilot-{state}-"))
    try:
        build = build_overlay(spec, rulespec_root, overlay)
        env = axiom_rules_env(build.program_path, root)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(build.overlay_root)
        sua = sua_amounts_from_overlay(spec, cfg)
        variants = ("base", "earned", "unearned", "shelter", "dependent_care", "child_support", "medical")
        # The base variant needs the full internal-stage output surface; the six
        # perturbation variants only need the compared benefit output, which
        # keeps the debug engine's per-case cost near the nightly replay's.
        blocks = {}
        for kind in variants:
            projected = [map_qc_unit(u if kind == "base" else proxy(u, kind), base, member,
                                     config=cfg, sua_amount_by_tier=sua) for u in units]
            blocks[kind] = _run_cases(binary=binary, program_path=build.program_path, cases=projected,
                                      period=month_period(*NOMINAL_PERIOD),
                                      output_ids=(requested if kind == "base" else [benefit_id]),
                                      config=cfg, env=env)
    finally:
        shutil.rmtree(overlay, ignore_errors=True)
    n = len(units)
    rows = []
    for i, unit in enumerate(units):
        row = raw_row(unit, state, log.total_excluded)
        base_result = blocks["base"][i]
        for name, oid in {**stage_ids, **EXTRA_OUTPUTS}.items(): row[f"engine_{name}"] = value(base_result, oid)
        maxa = row["engine_maximum_allotment"]
        net = row["engine_net_income"]
        unbounded = maxa - __import__("math").ceil(0.30 * net)
        before_min = row["engine_benefit_before_minimum"]
        minimum = row["engine_minimum_benefit"]
        uncapped = row["engine_uncapped_excess_shelter"]
        capped = row["engine_excess_shelter_deduction"]
        before_shelter = row["engine_net_income_before_shelter"]
        row.update(engine_unbounded_benefit=unbounded,
                   engine_net_zero_clamp=int(net == 0 and before_shelter - capped < 0),
                   engine_shelter_cap=int(capped < uncapped), engine_benefit_at_max=int(unbounded >= maxa),
                   engine_minimum_floor=int(row["engine_issued_allotment"] > before_min),
                   engine_benefit_zero=int(row["engine_issued_allotment"] == 0),
                   engine_net_floor_slack=before_shelter-capped,
                   engine_shelter_cap_slack=capped-uncapped,
                   engine_minimum_slack=unbounded-minimum,
                   engine_max_slack=maxa-unbounded)
        base_ben = value(base_result, benefit_id)
        row["engine_benefit"] = base_ben
        for kind in variants[1:]: row[f"engine_sensitivity_{kind}_10"] = value(blocks[kind][i], benefit_id) - base_ben
        rows.append(row)
    # Identity check: the engine benefit must reproduce FSBEN case-for-case —
    # the replay theorem the seven suites prove nightly. A nonzero count means
    # the wide-output request or this extractor changed evaluation semantics.
    mismatches = [r["case_id"] for r in rows if r["engine_benefit"] != r["verified_benefit"]]
    return rows, {"state": state, "loaded": n, "excluded": log.total_excluded,
                  "exclusions": dict(log.counts), "fsben_identity_mismatches": len(mismatches),
                  "fsben_identity_mismatch_cases": mismatches[:20]}

def analytical_state(state):
    """Deadline fallback: encoded-chain algebra over bridge-grounded QC inputs."""
    cfg=QC_JURISDICTIONS[f"us-{state}"]; units,log=load_qc_units(2024,state_fips=cfg.state_fips)
    rows=[]
    for u in sorted(units,key=lambda x:x.case_id):
        r=raw_row(u,state,log.total_excluded); e=u.expected; size=u.certified_size
        maxa=FY2024_MAX_ALLOTMENT_48_STATES.get(size,FY2024_MAX_ALLOTMENT_48_STATES[8]+(size-8)*FY2024_MAX_ALLOTMENT_ADDITIONAL_MEMBER)
        net_before=max(0,(e.gross_income or 0)-(e.earned_income_deduction or 0)-(e.standard_deduction or 0)-(e.medical_deduction or 0)-(e.dependent_care_deduction or 0)-(e.child_support_deduction or 0)-(u.homeless_deduction_amount or 0))
        shelter=(u.shelter_expense or 0)+(u.utility_amount or 0)
        uncapped=0 if (u.homeless_deduction_amount or 0)>0 else max(0,int(shelter-.5*net_before+.5))
        capped=e.shelter_deduction or 0; net=e.net_income or 0; unbounded=maxa-__import__('math').ceil(.3*net)
        before=max(0,unbounded); minimum=e.minimum_benefit or 23; issued=e.benefit or 0
        r.update(engine_gross_income=e.gross_income,engine_standard_deduction=e.standard_deduction,
          engine_shelter_deduction=capped,engine_maximum_allotment=maxa,engine_earned_income_deduction=e.earned_income_deduction,
          engine_net_income_before_shelter=net_before,engine_uncapped_excess_shelter=uncapped,
          engine_excess_shelter_deduction=capped,engine_net_income=net,engine_minimum_benefit=minimum,
          engine_benefit_before_minimum=before,engine_issued_allotment=issued,engine_benefit=issued,
          engine_unbounded_benefit=unbounded,engine_net_zero_clamp=int(net==0 and net_before-capped<0),
          engine_shelter_cap=int(capped<uncapped),engine_benefit_at_max=int(unbounded>=maxa),
          engine_minimum_floor=int(issued>before),engine_benefit_zero=int(issued==0),
          engine_net_floor_slack=net_before-capped,engine_shelter_cap_slack=capped-uncapped,
          engine_minimum_slack=unbounded-minimum,engine_max_slack=maxa-unbounded)
        # Exact local algebra for the encoded 273.10 chain away from other clamps.
        def benefit(dnet):
            z=max(0,maxa-__import__('math').ceil(.3*max(0,net+dnet)))
            return minimum if size<=2 and z<minimum else z
        for k,d in {'earned':8,'unearned':10,'shelter':-10,'dependent_care':-10,'child_support':-10,'medical':(-10 if u.unit_has_elderly_or_disabled else 0)}.items(): r[f"engine_sensitivity_{k}_10"]=benefit(d)-issued
        rows.append(r)
    return rows,{"state":state,"loaded":len(rows),"excluded":log.total_excluded,"exclusions":dict(log.counts)}


def main():
    # Internal-stage queries are substantially wider than the parity runner's
    # ordinary six-output request; smaller payloads avoid debug-engine slowdown.
    qc_compare.CHUNK_SIZE = 50
    ap = argparse.ArgumentParser(); ap.add_argument("--states", nargs="*", default=STATES); ap.add_argument("--engine",action="store_true"); ap.add_argument("--out", default="features.parquet"); args = ap.parse_args()
    rules = Path(os.environ["AXIOM_SNAP_QC_RULESPEC_ROOT"])
    binary = resolve_axiom_binary(resolve_workspace_root(None), Path(os.environ["AXIOM_SNAP_QC_AXIOM_BINARY"]))
    CACHE.mkdir(parents=True, exist_ok=True)
    rows=[]; universe=[]
    for state in args.states:
        r,u=(extract_state(state,rules,binary) if args.engine else analytical_state(state)); rows.extend(r); universe.append(u); print(state, len(r), u.get("fsben_identity_mismatches"), flush=True)
    df=pd.DataFrame(rows).sort_values(["state","case_id"]).reset_index(drop=True)
    df["mode"] = "engine" if args.engine else "analytical"
    df.to_parquet(CACHE/args.out, index=False)
    stem = Path(args.out).stem
    (CACHE/f"universe-{stem}.json").write_text(json.dumps(universe,indent=2,sort_keys=True)+"\n")
    bad = sum(u.get("fsben_identity_mismatches") or 0 for u in universe)
    if args.engine and bad:
        raise SystemExit(f"FSBEN identity FAILED: {bad} mismatching case(s); see universe-{stem}.json")
    print(CACHE/args.out, len(df))

if __name__ == "__main__": main()
