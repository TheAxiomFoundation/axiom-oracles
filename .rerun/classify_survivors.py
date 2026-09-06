#!/usr/bin/env python3
"""Classify every unexplained row from the fresh traces (report-only).

Rules, in order, per case:
  bbce      — January PE grants categorical eligibility while a standard
              income test fails, and axiom is ineligible (axiom encoding gap)
  minors    — every member under 18, axiom projects wages PE excludes
  medical   — forcing imputed medical premiums reconciles benefit
  imputed   — forcing imputed income sources reconciles benefit
  manual    — nothing above fits (listed with full data)
"""
import glob
import json

TOL = 7.0

for tpath in sorted(glob.glob(".rerun/trace-*-snap-ecps.json")):
    suite = tpath.split("trace-")[1].replace(".json", "")
    upath = f".rerun/unforced-{suite}.json"
    try:
        unforced = json.load(open(upath))
    except FileNotFoundError:
        unforced = {}
    trace = json.load(open(tpath))
    print(f"== {suite} ({trace['residual_households']} households)")
    for c in trace["cases"]:
        cid = c["case_id"]
        r = c["report"]
        lv = c["live_pe"]
        ages = c.get("ages") or []
        uf = unforced.get(cid, {})
        imputed = uf.get("imputed_sources", {})
        forced = uf.get("forced", {})
        label = "manual"
        detail = ""
        ax_benefit = r.get("axiom_benefit")
        pe_benefit = r.get("pe_benefit")
        cat = bool(lv.get("meets_snap_categorical_eligibility"))
        net_ok = bool(lv.get("meets_snap_net_income_test"))
        gross_ok = bool(lv.get("meets_snap_gross_income_test"))
        if (
            r["pe_eligible"]
            and not r["axiom_eligible"]
            and cat
            and (not net_ok or not gross_ok)
        ):
            label = "bbce"
            detail = f"cat={cat} net_ok={net_ok} gross_ok={gross_ok}"
        elif ages and all(a < 18 for a in ages) and lv.get("snap_earned_income", 1) == 0:
            label = "minors"
        elif (
            forced
            and ax_benefit is not None
            and abs(float(forced.get("snap", 1e9)) - ax_benefit) <= TOL
        ):
            elig_row = r["pe_eligible"] != r["axiom_eligible"]
            elig_fixed = (not elig_row) or (
                bool(forced.get("is_snap_eligible")) == r["axiom_eligible"]
            )
            if elig_fixed:
                label = "imputed:" + "+".join(sorted(imputed)) if imputed else "imputed:none?"
        pe_disp = f"{pe_benefit:.2f}" if pe_benefit is not None else "?"
        print(
            f"  {cid} [{label}] ax={ax_benefit}/{r['axiom_eligible']} "
            f"pe={pe_disp}/{r['pe_eligible']} {detail}"
        )
        if label == "manual":
            print(
                f"     live: elig={lv.get('is_snap_eligible')} cat={cat} "
                f"net_ok={net_ok} gross_ok={gross_ok} "
                f"gross={lv.get('snap_gross_income', 0):.2f} "
                f"net={lv.get('snap_net_income', 0):.2f} ages={ages}"
            )
            if imputed:
                print(f"     imputed={ {k: round(v, 1) for k, v in imputed.items()} } forced_snap={forced.get('snap')}")
