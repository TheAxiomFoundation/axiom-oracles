#!/usr/bin/env python3
"""Probe evidence for three us-pe ``oracle_models_repealed_law`` exclusions.

PolicyEngine-US (the ``us-pe`` oracle) retains three federal programs whose
statutory authority does not reach the 2026 validation year. Each variable is
``switch=on`` — PolicyEngine runs its formula — but the amount is gated to $0 by
a lapsed parameter, so no synthetic case can make it pay. Axiom encodes current
law and has no current-law surface to compare, exactly the pattern the
``oracle_models_repealed_law`` reason documents (canonical UK case: Working/Child
Tax Credit ``bwkmt_bfamt``, ended 5 April 2025).

Programs and their repeal/lapse:

1. ``acp`` — Affordable Connectivity Program (47 USC 1752, IIJA 2021 sec.
   60502). The FCC stopped new enrollments on 7 Feb 2024 and paid the last
   (partial) benefit for May 2024 as appropriated funds ran out; no funds remain
   for 2026. PolicyEngine zeroes ``gov.fcc.acp.amount`` from the wind-down, so
   ``acp`` = 0 even for an ACP-eligible household with broadband cost.

2. ``ebb`` — Emergency Broadband Benefit (Consolidated Appropriations Act 2021,
   47 USC 1752 note). EBB was the pandemic predecessor to ACP; enrollment closed
   and it transitioned to ACP on 31 Dec 2021. ``gov.fcc.ebb.amount`` is $0 for
   2026, so ``ebb`` = 0 even when forced eligible with broadband cost.

3. ``recovery_rebate_credit`` — the economic impact payment credits under IRC
   6428 (CARES Act, 2020), 6428A (CAA 2021, for 2020) and 6428B (ARPA 2021, for
   2021). All three applied only to the 2020 and 2021 tax years; there is no
   current-law rebate for 2026. PolicyEngine sums ``rrc_cares + rrc_caa +
   rrc_arpa``, each $0 at 2026.

Run (pin the oracle to the us-pe universe label, policyengine-us 1.767.3):

    uv run --python 3.13 --with policyengine-us==1.767.3 \
        python scripts/probe_us_repealed_federal.py

The verdict lines are the evidence pointer recorded in conformance/us-pe.yaml.
"""

from __future__ import annotations

import importlib.metadata as _md

import numpy as np
from policyengine_us import Simulation
from policyengine_us.system import system

YEAR = 2026


def _spm_sim(broadband_cost: float, force_eligible: str | None) -> Simulation:
    sit = {
        "people": {"you": {"age": {YEAR: 40}, "employment_income": {YEAR: 6000}}},
        "tax_units": {"tu": {"members": ["you"]}},
        "spm_units": {
            "spm": {"members": ["you"], "broadband_cost": {YEAR: broadband_cost}}
        },
        "households": {"hh": {"members": ["you"], "state_name": {YEAR: "CA"}}},
    }
    sim = Simulation(situation=sit)
    if force_eligible is not None:
        sim.set_input(force_eligible, YEAR, np.array([True]))
    return sim


def main() -> int:
    p = system.parameters(f"{YEAR}-01-01")
    print(f"policyengine-us {_md.version('policyengine-us')}  validation year {YEAR}\n")

    # 1. Lapsed gating parameters (the amount each program can pay in 2026).
    acp_amt = float(p.gov.fcc.acp.amount.standard)
    ebb_amt = float(p.gov.fcc.ebb.amount.standard)
    print("Gating parameters at 2026:")
    print(f"  gov.fcc.acp.amount.standard = {acp_amt}")
    print(f"  gov.fcc.ebb.amount.standard = {ebb_amt}")

    # 2. Maximal activation: force eligibility ON and supply a large broadband
    #    cost. A live program would pay min(amount*12, cost); a lapsed one pays 0.
    acp = float(_spm_sim(2400.0, "is_acp_eligible").calculate("acp", YEAR).sum())
    ebb = float(_spm_sim(2400.0, "is_ebb_eligible").calculate("ebb", YEAR).sum())
    print("\nMaximal activation (eligible forced on, broadband_cost=2400):")
    print(f"  acp = {acp}")
    print(f"  ebb = {ebb}")

    # 3. Recovery rebate credit: each year-limited component, and the total.
    rrc_sim = _spm_sim(0.0, None)
    comps = {
        c: float(rrc_sim.calculate(c, YEAR).sum())
        for c in ("rrc_cares", "rrc_caa", "rrc_arpa", "recovery_rebate_credit")
    }
    print("\nRecovery rebate credit components at 2026:")
    for c, v in comps.items():
        print(f"  {c} = {v}")

    zero = {
        "acp": acp,
        "ebb": ebb,
        "recovery_rebate_credit": comps["recovery_rebate_credit"],
    }
    all_zero = all(v == 0.0 for v in zero.values())
    print("\nVERDICT:")
    for k, v in zero.items():
        print(
            f"  {k}: PolicyEngine-US pays {v} for every synthetic case in {YEAR} "
            f"-> oracle_models_repealed_law"
        )
    print(f"\nall_zero = {all_zero}")
    return 0 if all_zero else 1


if __name__ == "__main__":
    raise SystemExit(main())
