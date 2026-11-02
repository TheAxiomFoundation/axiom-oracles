#!/usr/bin/env python3
"""Probe evidence for two UK↔UKMOD exclusions (run on the x64 UKMOD runner).

Both policies are ``switch=on`` in UKMOD UK_2026 yet cannot be graded on the
registration-free training_data, for two different reasons this probe pins down.

1. ``bwkmt_bfamt`` (Working Tax Credit + Child Tax Credit) →
   ``oracle_models_repealed_law``. Tax credits ended 5 April 2025
   (https://www.gov.uk/tax-credits-have-ended); they are abolished from the
   2025-26 tax year. UKMOD retains ``bwkmt_bfamt_uk`` but gates it (like the
   Housing Benefit UC transition) to a pre-repeal legacy-claimant population, so
   for synthetic post-repeal cases — single childless 30h workers and a lone
   parent with a child, across labour-status and earnings, with WTC/CTC take-up
   pinned to 1.0 and ``$UCtransition=0`` — ``bwkmt_s``/``bfamt_s`` return 0.
   (The wave-2 note's nonzero figures are NOT reproducible on UK_2026.)

2. ``bsadi`` (income-related Employment and Support Allowance) →
   ``oracle_dataset_lacks_input``. The ir-ESA phase selector ``ddipd`` /
   ``ddipd00`` (0 = Income Support fallback, 1 = Work-Related Activity Group,
   3 = Support Group) is absent from the training_data column schema, so the
   ESA-specific WRAG/Support surfaces (``bsadi01_s``/``bsadi00_s``) can never be
   exercised on the registration-free dataset.

Env (x86_64 Rosetta): EUROMOD_PYTHON, DOTNET_ROOT, PYTHONNET_RUNTIME=coreclr,
POLARS_SKIP_CPU_CHECK=1. Run:
    .venv/bin/python scripts/probe_uk_repealed_and_missing_input.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

MODEL_ROOT = Path(os.environ.get(
    "EUROMOD_MODEL_ROOT", os.path.expanduser("~/Downloads/UKMOD_PUBLIC_B2026.03")
))


def _adult(idp, age, les, yem_month, dms, dhr, *, hours=35, child_mother=0):
    row = {
        "idhh": 1, "idperson": idp, "idpartner": 0, "idmother": 0, "idfather": 0,
        "idmotherbio": 0, "idfatherbio": 0, "drgn1": 2, "dct": 15, "dwt": 1000.0,
        "dag": age, "dgn": 1, "dms": dms, "dhr": dhr, "dec": 0, "ddi": 0,
        "les": les, "lhw": hours, "lhw01": hours, "loc": 5, "amrtn": 1,
        "yem": yem_month, "yse": 0.0, "yiy": 0.0, "poa": 0.0, "boact00": 0.0,
        "xhcrt": 0.0, "xhcsc": 0.0, "afc": 0.0,
    }
    return row


def _child(idp, age, mother):
    return {
        "idhh": 1, "idperson": idp, "idpartner": 0, "idmother": mother,
        "idfather": 0, "idmotherbio": mother, "idfatherbio": 0, "drgn1": 2,
        "dct": 15, "dwt": 1000.0, "dag": age, "dgn": 1, "dms": 1, "dhr": 0,
        "dec": 4, "ddi": 0, "les": 6, "lhw": 0, "lhw01": 0, "loc": 5,
        "amrtn": 1, "yem": 0.0, "yse": 0.0, "yiy": 0.0, "poa": 0.0,
        "boact00": 0.0, "xhcrt": 0.0, "xhcsc": 0.0, "afc": 0.0,
    }


def main() -> None:
    from axiom_oracles.adapters.euromod.runner import EuromodPlatformRunner
    from axiom_oracles.core.case import Case

    # --- Dataset column audit (no engine needed) ------------------------------
    header = (MODEL_ROOT / "Input" / "training_data.txt").read_text(
        encoding="utf-8"
    ).splitlines()[0].split("\t")
    cols = {c.strip() for c in header if c.strip()}
    print(f"training_data columns: {len(cols)}")
    for name in ("ddipd", "ddipd00", "ddi02", "bfapl"):
        print(f"  ir-ESA phase input {name!r} present: {name in cols}")
    for name in ("bcrdi", "bunct", "les", "lhw01"):
        print(f"  (buildable-lane input {name!r} present: {name in cols})")

    def runner(overrides):
        return EuromodPlatformRunner(
            model_root=MODEL_ROOT, country="UK", system="UK_2026",
            dataset="training_data",
            policy_switch_overrides=[("BTA_uk", False), ("random_uk", False)],
            constant_overrides=overrides,
        )

    def case(cid, rows):
        return Case(
            case_id=cid, period="2026-04", facts={},
            metadata={"locale": "UK", "scope": {"type": "country", "geoid": "UK"},
                      "euromod_inputs": rows,
                      "euromod_policy_switch_overrides": [["BTA_uk", False],
                                                          ["random_uk", False]]},
            entities=(), outputs=(),
        )

    # --- 1. bwkmt_bfamt: repealed WTC/CTC produce 0 on synthetic cases --------
    tc_overrides = {"$UCtransition": "0", "$WTCCTCTUCoup": "1.0",
                    "$WTCCTCTULP": "1.0", "$WTCCTCTULon": "1.0",
                    "$WTCCTCTUSct": "1.0", "$WTCCTCTUWls": "1.0",
                    "$CTCTUFamonly": "1.0", "$WTCTUnoCTC": "1.0"}
    tc = runner(tc_overrides)
    print("\nbwkmt_bfamt (WTC/CTC, repealed 5 Apr 2025) — expect all 0:")
    probes = [
        ("single-childless-30h-les2", [_adult(101, 30, 2, 600.0, 1, 1, hours=30)]),
        ("single-childless-30h-les3", [_adult(101, 30, 3, 600.0, 1, 1, hours=30)]),
        ("lone-parent-1child-35h-les3",
         [_adult(101, 35, 3, 1000.0, 1, 1), _child(201, 5, 101)]),
    ]
    for cid, rows in probes:
        r = tc.run_cases([case(cid, rows)], variables=["bwkmt_s", "bfamt_s"])[0]
        print(f"  {cid}: WTC bwkmt_s={r.values.get('bwkmt_s')} "
              f"CTC bfamt_s={r.values.get('bfamt_s')} err={r.errors}")

    # --- 2. bsadi: ir-ESA cannot fire without the absent ddipd phase input ----
    esa = runner({"$UCtransition": "0"})
    # A disabled single adult with the training_data disability indicators set,
    # but no ddipd (absent column): the ESA WRAG/Support phase cannot be selected.
    dis = _adult(101, 40, 0, 0.0, 1, 1, hours=0)
    dis["ddi"] = 1
    dis["bdisc"] = 100.0  # DLA/PIP care indicator that IS in the schema
    print("\nbsadi (ir-ESA) — ESA phase input ddipd absent, expect bsadi01/00_s 0:")
    r = esa.run_cases([case("disabled-single-no-ddipd", [dis])],
                      variables=["bsadi_s", "bsadi01_s", "bsadi00_s"])[0]
    print(f"  bsadi_s={r.values.get('bsadi_s')} "
          f"WRAG bsadi01_s={r.values.get('bsadi01_s')} "
          f"Support bsadi00_s={r.values.get('bsadi00_s')} err={r.errors}")


if __name__ == "__main__":
    main()
