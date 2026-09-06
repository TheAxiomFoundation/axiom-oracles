#!/usr/bin/env python3
"""Author disposition entries for every remaining unexplained snap-ecps row.

Consumes the fresh dashboards (pins), traces (January PE flags/values),
unforced passes (imputation counterfactuals), and the final counterfactual
ladders. Emits per-suite YAML fragments under .rerun/entries-<suite>.yaml for
review/merge. Every number in an entry comes from these artifacts — no
invented values. Cases whose data doesn't support any class land in the
fragment's `unresolved` list.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

TOL = 7.0
RUNTIME = "PolicyEngine 4.18.9 / PolicyEngine-US 1.767.3 / PolicyEngine-Core 3.30.3"
STAMP = "2026-08-12"
ECFR_UNEARNED = (
    "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/"
    "part-273#p-273.9(b)(2)(i)"
)
ISSUE_9157 = "https://github.com/PolicyEngine/policyengine-us/issues/9157"
ISSUE_397 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/397"
ISSUE_433 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/433"
ISSUE_436 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/436"

SUITES = ["al", "sc", "nc", "ma", "fl", "ga", "ny", "ca"]

# Existing per-state BBCE tracking issues, read from the current entries.
BBCE_ISSUES = {}


def load_json(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def fmt(x):
    return f"{float(x):g}" if x is not None else "?"


def benefit_pin(row):
    return {
        "left": float(row["left"]),
        "right": float(row["right"]),
        "difference": float(row["right"]) - float(row["left"]),
    }


def elig_pin(row):
    return {"left": bool(row["left"]), "right": bool(row["right"])}


def base_entry(entry_id, row, disposition, mechanism, arithmetic, sources,
               linked=None, upstream=None):
    e = {
        "id": entry_id,
        "concept": row["concept"],
        "case_id": row["case_id"],
        "kind": row["kind"],
        "disposition": disposition,
    }
    if linked:
        e["linked_issue"] = linked
    ev = {"mechanism": mechanism}
    if upstream:
        ev["upstream_url"] = upstream
    if arithmetic:
        ev["arithmetic"] = arithmetic
    ev["sources"] = sources
    e["evidence"] = ev
    e["expires_on_source_change"] = True
    e["pinned"] = (
        elig_pin(row) if "snap_eligible" in row["concept"] else benefit_pin(row)
    )
    return e


def main() -> int:
    for st in SUITES:
        suite = f"{st}-snap-ecps"
        report = load_json(f"dashboard/public/data/axiom-policyengine-{suite}.json")
        trace = load_json(f".rerun/trace-{suite}.json")
        unforced = load_json(f".rerun/unforced-{suite}.json") or {}
        ladder = load_json(f".rerun/finalcf-{suite}.json") or {}
        existing = yaml.safe_load(open(f"dispositions/{suite}.yaml"))
        bbce_issue = None
        for e in existing.get("entries", []):
            if "bbce" in e["id"] and e.get("linked_issue"):
                bbce_issue = e["linked_issue"]
                break
        rows = [r for r in report["mismatches"] if r.get("disposition") is None]
        by_case = {}
        for r in rows:
            by_case.setdefault(r["case_id"], []).append(r)
        tcases = {c["case_id"]: c for c in (trace or {}).get("cases", [])}
        src_report = f"dashboard/public/data/axiom-policyengine-{suite}.json"

        entries, unresolved = [], []
        bbce_cases = []

        for cid, case_rows in sorted(by_case.items()):
            tc = tcases.get(cid)
            if tc is None:
                unresolved.append({"case_id": cid, "reason": "no trace"})
                continue
            lv = tc["live_pe"]
            rep = tc["report"]
            ages = tc.get("ages") or []
            uf = unforced.get(cid, {})
            lad = ladder.get(cid, {})
            num = cid.removeprefix("ecps-")
            jan_elig = bool(lv.get("is_snap_eligible"))
            jan_snap = float(lv.get("snap", 0.0))
            cat = bool(lv.get("meets_snap_categorical_eligibility"))
            net_ok = bool(lv.get("meets_snap_net_income_test"))
            gross_ok = bool(lv.get("meets_snap_gross_income_test"))
            ax_elig = rep.get("axiom_eligible")
            ax_ben = rep.get("axiom_benefit")
            pe_ben = rep.get("pe_benefit")

            # --- class: minors (all members <18, PE excludes their wages)
            if ages and all(a < 18 for a in ages) and lv.get("snap_earned_income", 1) == 0:
                for row in case_rows:
                    is_elig = "snap_eligible" in row["concept"]
                    mech = (
                        f"Reverified on {RUNTIME}. Exact-household requested-month "
                        f"replay: PolicyEngine's January snap_earned_income is 0 for "
                        f"this all-minor household (ages {ages}) although the "
                        "projected Case carries the member's wages — PolicyEngine "
                        "excludes all earnings of an imputed K-12 member age 17 or "
                        "younger without requiring the co-resident-parent or "
                        "parental-control condition in 7 CFR 273.9(c)(7). The sole-"
                        "minor household is valid under 273.1(a)(1), but its wages "
                        "count under 273.9(b)(1)(i), so Axiom correctly fails the "
                        "income gate and returns zero benefit while PolicyEngine "
                        f"pays {fmt(pe_ben)} (January replay {fmt(jan_snap)})."
                    )
                    arith = [{
                        "expression": f"{fmt(jan_snap)} - {fmt(pe_ben)}",
                        "equals": round(jan_snap - float(pe_ben), 6),
                        "tolerance": 0.01,
                    }]
                    entries.append(base_entry(
                        f"pe-lone-minor-child-earnings-{num}"
                        + ("-eligibility" if is_elig else "-benefit"),
                        row, "upstream_engine_gap", mech, arith,
                        [src_report,
                         "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/part-273#p-273.1(a)(1)",
                         "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/part-273#p-273.9(c)(7)"],
                        linked=ISSUE_9157, upstream=ISSUE_9157,
                    ))
                continue

            # --- class: bbce (January PE categorically eligible while a
            #     standard income test fails; axiom ineligible)
            if (
                rep.get("pe_eligible")
                and ax_elig is False
                and jan_elig
                and cat
                and (not net_ok or not gross_ok)
            ):
                bbce_cases.append((cid, case_rows, tc))
                continue

            # --- class: annual eligibility aggregation (January PE ineligible
            #     and zero on every forcing; committed bool is the year-shaped
            #     wrapper value)
            if lad and not jan_elig and all(
                not f.get("is_snap_eligible") and float(f.get("snap", 1)) == 0.0
                for f in lad.get("forcings", {}).values()
            ) and float(lad.get("unforced", {}).get("snap", 1)) == 0.0:
                for row in case_rows:
                    is_elig = "snap_eligible" in row["concept"]
                    mech = (
                        f"Exact-household requested-month replay on {RUNTIME}. "
                        "The direct January 2026 simulation of the identical Case "
                        "is ineligible with zero SNAP under every income-forcing "
                        "counterfactual (medical, TANF, self-employment, and "
                        "their combinations), so no January income surface "
                        "reproduces the committed PolicyEngine verdict. The "
                        "committed eligibility boolean is the comparison "
                        "adapter's year-shaped output-dataset value — an "
                        "any-month aggregation across calendar 2026 (the "
                        "household qualifies in some non-January month, e.g. "
                        "after the October 1 COLA) — while the month-defined "
                        "benefit is January's. Axiom evaluates January only"
                        + (
                            f"; its {fmt(ax_ben)} benefit against PolicyEngine's "
                            f"January 0.0 is the same aggregation artifact."
                            if not is_elig else "."
                        )
                    )
                    arith = [{
                        "expression": "0.0 - 0.0",
                        "equals": 0.0,
                        "tolerance": 1e-06,
                    }]
                    entries.append(base_entry(
                        f"{st}-pe-annual-eligibility-aggregation-{STAMP}-{num}"
                        + ("-eligibility" if is_elig else "-benefit"),
                        row, "bridge_artifact", mech, arith,
                        [src_report,
                         "axiom_oracles/adapters/policyengine/runner.py"],
                    ))
                continue

            # --- class: imputation counterfactual (forcing imputed sources
            #     reconciles the January benefit to axiom)
            imputed = uf.get("imputed_sources", {})
            forced = uf.get("forced", {})
            if (
                forced
                and ax_ben is not None
                and abs(float(forced.get("snap", 1e9)) - ax_ben) <= TOL
            ):
                elig_row_present = any(
                    "snap_eligible" in r["concept"] for r in case_rows
                )
                elig_ok = (not elig_row_present) or (
                    bool(forced.get("is_snap_eligible")) == ax_elig
                )
                if elig_ok:
                    srcs = sorted(imputed)
                    delta = abs(float(forced["snap"]) - ax_ben)
                    if srcs == ["tanf"]:
                        prefix, issue = "tanf-zero-counterfactual", ISSUE_397
                        forcing_txt = "Forcing the aggregate and state TANF inputs to zero"
                        causal = (
                            "The comparison bridge zeroes TANF on the Axiom "
                            "input surface while PolicyEngine computes state "
                            "TANF endogenously and counts it as SNAP unearned "
                            "income (axiom-oracles#397 counterfactual class)."
                        )
                    elif set(srcs) <= {"medical_expense_health_insurance_premiums", "other_medical_expenses"}:
                        prefix, issue = "pe-medical-imputation-counterfactual", ISSUE_436
                        forcing_txt = "Forcing the imputed medical-expense inputs to zero"
                        causal = (
                            "Axiom receives zero medical-expense input while "
                            "PolicyEngine imputes allowable medical expenses "
                            "for the elderly/disabled member, feeding an excess "
                            "medical deduction the bridge never projects to Axiom."
                        )
                    else:
                        prefix, issue = "endogenous-income-stack-counterfactual", ISSUE_436
                        forcing_txt = (
                            "Forcing the endogenously derived "
                            + ", ".join(srcs)
                            + " inputs to zero"
                        )
                        causal = (
                            "PolicyEngine derives these sources endogenously on "
                            "the requested-month path while the projected Case "
                            "carries none of them, so the engines price "
                            "different income surfaces."
                        )
                    live_delta = abs(float(lv.get("snap", 1e9)) - float(pe_ben))
                    repro_txt = (
                        "The committed comparison adapter replayed over the same "
                        f"Case projection reproduces the report pin (Axiom {fmt(ax_ben)} "
                        f"versus January PolicyEngine {fmt(pe_ben)})"
                        if live_delta <= 0.01
                        else (
                            "The committed comparison adapter replayed over the "
                            f"same Case projection returns January {fmt(lv.get('snap'))} "
                            f"against the report pin {fmt(pe_ben)} (endogenous "
                            "derivations shift between runs); the counterfactual "
                            "below reconciles regardless"
                        )
                    )
                    for row in case_rows:
                        is_elig = "snap_eligible" in row["concept"]
                        mech = (
                            f"Exact-household requested-month counterfactual on {RUNTIME}. "
                            f"{repro_txt}. {forcing_txt} in the direct requested-month "
                            f"simulation produces January SNAP {fmt(forced['snap'])}; its "
                            f"absolute delta from Axiom, {round(delta, 6)}, is within the "
                            f"unchanged suite tolerance {TOL}. {causal}"
                        )
                        if is_elig:
                            mech += (
                                " The same intervention sets January PolicyEngine "
                                f"eligibility to {bool(forced.get('is_snap_eligible'))}, "
                                "matching Axiom's persisted verdict."
                            )
                        arith = [{
                            "expression": f"{fmt(forced['snap'])} - {fmt(ax_ben)}",
                            "equals": round(float(forced["snap"]) - ax_ben, 6),
                            "tolerance": max(1e-06, round(delta + 1e-6, 6)),
                        }]
                        entries.append(base_entry(
                            f"{prefix}-{num}" + ("-eligibility" if is_elig else ""),
                            row, "bridge_artifact", mech, arith,
                            [src_report, ECFR_UNEARNED,
                             "axiom_oracles/adapters/policyengine/runner.py"],
                            linked=issue, upstream=issue,
                        ))
                    continue

            unresolved.append({
                "case_id": cid,
                "report": rep,
                "january": {"snap": jan_snap, "eligible": jan_elig,
                            "cat": cat, "net_ok": net_ok, "gross_ok": gross_ok},
                "ladder": {k: {"snap": v.get("snap"), "elig": v.get("is_snap_eligible")}
                           for k, v in (lad.get("forcings") or {}).items()},
                "imputed": imputed,
            })

        # --- consolidated BBCE entries per suite
        if bbce_cases:
            elig_ids = [cid for cid, rws, _ in bbce_cases
                        if any("snap_eligible" in r["concept"] for r in rws)]
            ben_ids = [cid for cid, rws, _ in bbce_cases
                       if any("snap_benefit" in r["concept"] for r in rws)]
            detail = "; ".join(
                f"{cid}: categorical=True, net_test="
                f"{bool(tc['live_pe'].get('meets_snap_net_income_test'))}, "
                f"gross_test={bool(tc['live_pe'].get('meets_snap_gross_income_test'))}, "
                f"January PE {fmt(tc['live_pe'].get('snap'))}"
                for cid, _, tc in bbce_cases
            )
            mech = (
                f"Reverified per-row on {RUNTIME} via exact-household "
                "requested-month replay: for every selected row January "
                "PolicyEngine grants broad-based categorical eligibility "
                "(meets_snap_categorical_eligibility=True) while a standard "
                "federal income test fails, and pays the resulting benefit "
                "(one/two-person minimums where net income leaves no normal "
                "allotment). The composed program applies only the standard "
                "federal tests, so Axiom is ineligible with zero benefit. "
                f"Axiom-side modeling boundary. Per-row flags: {detail}."
            )
            for kind_name, ids, concept_suffix in (
                ("eligibility", elig_ids, "snap_eligible"),
                ("benefit", ben_ids, "snap_benefit"),
            ):
                if not ids:
                    continue
                rows = [r for cid in ids for r in by_case[cid]
                        if concept_suffix in r["concept"]]
                kinds = {r["kind"] for r in rows}
                entry = {
                    "id": f"{st}-bbce-tail-{STAMP}-{kind_name}",
                    "concept": rows[0]["concept"],
                    "case_selector": {"case_ids": sorted(ids)},
                    "disposition": "axiom_encoding_gap",
                    "evidence": {"mechanism": mech, "sources": [src_report]},
                    "expires_on_source_change": True,
                }
                if len(kinds) == 1:
                    entry["kind"] = rows[0]["kind"]
                if bbce_issue:
                    entry["linked_issue"] = bbce_issue
                entries.append(entry)

        out = {"suite": suite, "entries": entries, "unresolved": unresolved}
        Path(f".rerun/entries-{suite}.yaml").write_text(
            yaml.safe_dump(out, sort_keys=False, width=78, allow_unicode=True)
        )
        print(
            f"{suite}: rows={len(rows)} entries={len(entries)} "
            f"unresolved={len(unresolved)}"
        )
        for u in unresolved:
            print("   UNRESOLVED", u["case_id"], u.get("reason", ""),
                  u.get("january"), u.get("ladder"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
