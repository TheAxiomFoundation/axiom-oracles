#!/usr/bin/env python3
"""Build disposition entries for traced snap-ecps survivors.

Consumes a trace JSON from trace_suite_residuals.py, picks the minimal
requested-month forcing that reconciles each case to Axiom within the suite
tolerance, and emits YAML entries in the established house format. Cases no
toggle reconciles are reported as UNRESOLVED with their component values —
they get deeper manual treatment, never a fabricated entry.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

TOLERANCE = 7.0
RUNTIME = "PolicyEngine 4.18.9 / PolicyEngine-US 1.767.3 / PolicyEngine-Core 3.30.3"
ISSUE_397 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/397"
ISSUE_433 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/433"
ECFR_UNEARNED = (
    "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/"
    "part-273#p-273.9(b)(2)(i)"
)

TANF_TEXT = (
    "The comparison bridge zeroes TANF on the Axiom input surface while "
    "PolicyEngine computes state TANF endogenously and counts it as SNAP "
    "unearned income (axiom-oracles#397 counterfactual class)."
)
SE_TEXT = (
    "Self-employment income enters the two engines on different surfaces "
    "(the projection's flat 0.6 netting versus PolicyEngine's state "
    "expense-based treatment), and zeroing it on the PolicyEngine side "
    "closes the residual."
)

CLASSES = [
    # (key in requested_month_counterfactuals, id prefix, forcing phrase,
    #  causal text, classifier record, linked issue)
    (
        "zero_tanf",
        "tanf-zero-counterfactual",
        "Forcing the aggregate and state TANF inputs to zero",
        TANF_TEXT,
        "tanf",
        ISSUE_397,
    ),
    (
        "zero_self_employment",
        "se-zero-counterfactual",
        "Forcing the self-employment income inputs to zero",
        SE_TEXT,
        "self_employment",
        ISSUE_433,
    ),
    (
        "zero_self_employment_and_tanf",
        "se-and-tanf-zero-counterfactual",
        "Forcing the self-employment income inputs and the aggregate and "
        "state TANF inputs to zero",
        TANF_TEXT + " " + SE_TEXT,
        "se_and_tanf",
        ISSUE_397,
    ),
]


def build_entry(
    suite: str,
    case: dict,
    row_concept_suffix: str,
    row: dict,
    cf_key: str,
    prefix: str,
    forcing: str,
    causal: str,
    record: str,
    issue: str,
) -> dict:
    report = case["report"]
    axiom_benefit = report["axiom_benefit"]
    cf = case["requested_month_counterfactuals"][cf_key]
    cf_snap = float(cf["snap"])
    delta = abs(cf_snap - axiom_benefit)
    baseline_rm = case["requested_month_pe"]
    num = case["case_id"].removeprefix("ecps-").removeprefix("spm-")

    mechanism = (
        f"Exact-household requested-month counterfactual on {RUNTIME}. "
        "The committed comparison adapter replayed over the same Case "
        f"projection reproduces the report pin (Axiom {axiom_benefit} versus "
        f"January PolicyEngine {report['pe_benefit']}), and the unmodified "
        "direct requested-month simulation reproduces the same January value "
        f"({baseline_rm['snap']}). {forcing} in the direct requested-month "
        f"simulation produces January SNAP {cf_snap}; its absolute delta "
        f"from Axiom, {round(delta, 6)}, is within the unchanged suite "
        f"tolerance {TOLERANCE}. {causal} "
        f"Replay classifier record: class={record}."
    )
    entry_id = f"{prefix}-{num}"
    concept = row["concept"]
    kind = row["kind"]
    if row_concept_suffix == "eligible":
        entry_id += "-eligibility"
        mechanism += (
            " The same intervention flips January PolicyEngine eligibility "
            f"to {bool(cf['is_snap_eligible'])}, matching Axiom's persisted "
            "verdict."
        )
        pinned = {"left": bool(row["left"]), "right": bool(row["right"])}
    else:
        pinned = {
            "left": float(row["left"]),
            "right": float(row["right"]),
            "difference": float(row["right"]) - float(row["left"]),
        }
    entry = {
        "id": entry_id,
        "concept": concept,
        "case_id": case["case_id"],
        "kind": kind,
        "disposition": "bridge_artifact",
        "linked_issue": issue,
        "evidence": {
            "mechanism": mechanism,
            "upstream_url": issue,
            "arithmetic": [
                {
                    "expression": f"{cf_snap} - {axiom_benefit}",
                    "equals": round(cf_snap - axiom_benefit, 6),
                    "tolerance": max(1e-06, TOLERANCE if delta > 1e-6 else 1e-06),
                }
            ],
            "sources": [
                f"dashboard/public/data/axiom-policyengine-{suite}.json",
                ECFR_UNEARNED,
                issue,
                "axiom_oracles/adapters/policyengine/runner.py",
            ],
        },
        "expires_on_source_change": True,
        "pinned": pinned,
    }
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    trace = json.loads(args.trace.read_text())
    report_path = Path(
        f"dashboard/public/data/axiom-policyengine-{args.suite}.json"
    )
    report = json.loads(report_path.read_text())
    rows_by_case: dict[str, list[dict]] = {}
    for row in report["mismatches"]:
        if row.get("disposition") is None:
            rows_by_case.setdefault(row["case_id"], []).append(row)

    entries = []
    unresolved = []
    for case in trace["cases"]:
        cid = case["case_id"]
        report_rows = rows_by_case.get(cid, [])
        axiom_benefit = case["report"]["axiom_benefit"]
        # The counterfactual template asserts the adapter replay AND the
        # direct requested-month sim both reproduce the committed PE value;
        # only emit it when that is actually true.
        live_delta = abs(
            float(case["live_pe"]["snap"]) - case["report"]["pe_benefit"]
        )
        direct_delta = abs(
            float(case["requested_month_pe"]["snap"])
            - case["report"]["pe_benefit"]
        )
        if live_delta > 0.01 or direct_delta > 0.01:
            unresolved.append(
                {
                    "case_id": cid,
                    "reason": (
                        f"baseline does not reproduce pin: live_delta="
                        f"{live_delta:.6f} direct_delta={direct_delta:.6f}"
                    ),
                    "report": case["report"],
                    "live_pe_snap": case["live_pe"]["snap"],
                    "requested_month_snap": case["requested_month_pe"]["snap"],
                    "counterfactuals": case["requested_month_counterfactuals"],
                }
            )
            continue
        chosen = None
        for cf_key, prefix, forcing, causal, record, issue in CLASSES:
            cf = case["requested_month_counterfactuals"].get(cf_key)
            if cf is None:
                continue
            delta = abs(float(cf["snap"]) - axiom_benefit)
            elig_ok = True
            if any("snap_eligible" in r["concept"] for r in report_rows):
                elig_ok = bool(cf["is_snap_eligible"]) == case["report"][
                    "axiom_eligible"
                ]
            if delta <= TOLERANCE and elig_ok:
                chosen = (cf_key, prefix, forcing, causal, record, issue)
                break
        if chosen is None:
            unresolved.append(
                {
                    "case_id": cid,
                    "report": case["report"],
                    "requested_month_pe": {
                        k: v
                        for k, v in case["requested_month_pe"].items()
                        if not isinstance(v, dict)
                    },
                    "counterfactuals": case["requested_month_counterfactuals"],
                }
            )
            continue
        for row in report_rows:
            suffix = "eligible" if "snap_eligible" in row["concept"] else "benefit"
            entries.append(build_entry(args.suite, case, suffix, row, *chosen))

    out = {
        "suite": args.suite,
        "entries": entries,
        "unresolved": unresolved,
    }
    args.out.write_text(yaml.safe_dump(out, sort_keys=False, width=78))
    print(
        f"{args.suite}: {len(entries)} entries for "
        f"{len(trace['cases']) - len(unresolved)} cases; "
        f"{len(unresolved)} unresolved"
    )
    for row in unresolved:
        print("  UNRESOLVED", row["case_id"], row["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
