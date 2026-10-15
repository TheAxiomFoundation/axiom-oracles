#!/usr/bin/env python3
"""Build or audit fiit-ecps's EITC attribution evidence and dispositions.

Build, from the outputs of the three attribution stages
(``scripts/fiit_ecps_eitc_attribution/``; see its README):

    uv run python scripts/build_fiit_ecps_eitc_dispositions.py \\
        --stage1 counterfactuals.json \\
        --stage2 counterfactuals_stage2.json \\
        --stage3 counterfactuals_stage3.json \\
        --raw-report reports/axiom-policyengine-fiit-ecps-0-2026-10-14.json
    uv run scripts/stamp_selector_bindings.py fiit-ecps

This writes the evidence report the dispositions cite
(``reports/fiit-ecps-eitc-attribution-2026-10-14.json``) and
``dispositions/fiit-ecps.yaml``. The mismatch rows come from the FULL v2
report the dashboard copy is bound to (its ``source_report`` pointer and
digest); the raw report is read only for its digest.

Audit, offline (``tests/test_fiit_ecps_eitc_attribution.py`` runs it):

    uv run python scripts/build_fiit_ecps_eitc_dispositions.py --check

It checks that the committed files agree:

- the evidence holds exactly the bound FULL report's mismatch rows, with the
  same values;
- every row's entry follows from its recorded stage attributions (EITC) or
  from its surface's per-row bound (the other surfaces);
- each entry's row and tax-unit counts are its rows';
- each disposition entry selects exactly its evidence rows, by output.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = "reports/fiit-ecps-eitc-attribution-2026-10-14.json"
DISPOSITIONS = "dispositions/fiit-ecps.yaml"
DASHBOARD = "dashboard/public/data/axiom-policyengine-fiit-ecps.json"
EVIDENCE_SCHEMA = "axiom_oracles.fiit_ecps_eitc_attribution.v1"
FLAT_SECA_FRACTION = 0.5 * (0.124 + 0.029) * (1 - 0.5 * (0.124 + 0.029))
EITC = "us:tax/federal-income-tax#eitc"
TAX_BEFORE_CREDITS = "us:tax/federal-income-tax#tax_before_credits"
CAPITAL_GAIN = "us:tax/federal-income-tax#capital_gain"
CTC = "us:tax/federal-income-tax#ctc"
PE = "https://github.com/PolicyEngine/policyengine-us"

# Evidence entry key -> disposition id and kind, in file order.
ENTRIES = {
    "se_projection": (
        "eitc-earned-income-bridge-32c2-self-employment-projection",
        "bridge_artifact",
    ),
    "partnership": (
        "eitc-earned-income-populace-partnership-se-income-unread",
        "bridge_artifact",
    ),
    "dividend_aggregate": (
        "eitc-investment-income-populace-dividend-aggregate",
        "bridge_artifact",
    ),
    "pe_investment": (
        "eitc-investment-income-policyengine-1729-definition",
        "upstream_engine_gap",
    ),
    "age": (
        "eitc-childless-age-test-policyengine-counts-dependents",
        "upstream_engine_gap",
    ),
    "tax_before_credits": ("tax-before-credits-bracket-rounding", "explained_residual"),
    "capital_gain": ("capital-gain-float-noise", "explained_residual"),
    "ctc": ("ctc-excess-agi-increment-rounding", "explained_residual"),
}

# The non-EITC surfaces' entries rest on a per-row signature, re-verified
# on every row: concept -> (entry, predicate on the signed difference, label).
ROW_BOUNDS = {
    TAX_BEFORE_CREDITS: (
        "tax_before_credits",
        lambda diff: abs(diff) <= 5.83 + 1e-9,
        "|diff| <= 5.83 (bracket rounding)",
    ),
    CAPITAL_GAIN: (
        "capital_gain",
        lambda diff: abs(diff) <= 3.25 + 1e-9,
        "|diff| <= 3.25 (float noise)",
    ),
    CTC: (
        "ctc",
        lambda diff: abs(diff - 50.0) <= 1e-6,
        "diff == +50 (one excess-AGI increment)",
    ),
}

# The 2026-10-14 stage 3 predates its counterfactual-only row record
# (``base_counterfactual_only_rows``); a one-off dump of its base variant
# found these four.
STAGE3_BASE_NOTE_2026_10_14 = (
    "With the bridge's aggregate and every other mechanism applied, "
    "the base leaves every stage-1 investment row plus 4 "
    "eitc_eligible rows the full run does not have (tax units "
    "27227, 52975, 85432, 95378): the all-members age rule makes "
    "Axiom eligible where PolicyEngine still denies on its own "
    "investment aggregate. They are counterfactual-only and are "
    "not attributed."
)


def case_id(entity_id: str) -> str:
    return f"ecps-{entity_id}"


def tax_unit_number(case: str) -> int:
    return int(case.rsplit("_", 1)[1])


def row_key(row: dict) -> str:
    """``tax_unit_<n>|<output>``, the stages' key for a FULL-report row."""
    return f"{row['case_id'].removeprefix('ecps-')}|{row['output']}"


def eitc_entry_of(stage1: str, stage3: str | None) -> str:
    """The entry an EITC row belongs to, from its stage attributions."""
    if stage1 in ("age", "age+investment"):
        return "age"
    if stage1 == "partnership":
        return "partnership"
    if stage1 == "investment":
        return "dividend_aggregate" if stage3 == "div_aggregate" else "pe_investment"
    if stage1 == "residual":
        return "se_projection"
    raise ValueError(f"no entry for stage-1 mechanism {stage1!r}")


def entry_of(row: dict, stage1: str | None, stage3: str | None) -> str:
    """The entry one FULL-report mismatch row belongs to.

    Raises ``ValueError`` when the row fits no entry: an EITC row without a
    known attribution, or another surface's row outside its bound.
    """
    concept = row["concept"]
    if concept == EITC:
        if stage1 is None:
            raise ValueError(f"{row_key(row)}: EITC row without a stage-1 attribution")
        return eitc_entry_of(stage1, stage3)
    if concept not in ROW_BOUNDS:
        raise ValueError(f"{row_key(row)}: no entry for concept {concept}")
    entry, holds, bound = ROW_BOUNDS[concept]
    if not holds(float(row["difference"])):
        raise ValueError(f"{row_key(row)}: breaks {bound}")
    return entry


def selector(assignment: dict[str, str], entry: str) -> dict[str, list[str]]:
    """``case_ids_by_output`` for one entry: its cases by output, sorted."""
    by_output = collections.defaultdict(list)
    for key, assigned in assignment.items():
        if assigned == entry:
            entity, output = key.split("|")
            by_output[output].append(case_id(entity))
    return {
        output: sorted(cases, key=tax_unit_number)
        for output, cases in sorted(by_output.items())
    }


def counts_of(assignment: dict[str, str]) -> dict[str, dict[str, int]]:
    rows = collections.Counter(assignment.values())
    units = {
        entry: len({key.split("|")[0] for key, value in assignment.items() if value == entry})
        for entry in rows
    }
    return {entry: {"rows": rows[entry], "tax_units": units[entry]} for entry in sorted(rows)}


def bound_full_report(root: Path) -> tuple[Path, dict]:
    """The FULL v2 report the dashboard copy is bound to, digest verified."""
    copy = json.loads((root / DASHBOARD).read_text())
    pointer = copy["summary"]["dispositioned"]["source_report"]
    path = root / pointer["path"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pointer["sha256"]:
        raise ValueError(f"{pointer['path']} does not match the dashboard copy's digest")
    return path, json.loads(data)


def build_evidence(full: dict, stage1: dict, stage2: dict, stage3: dict, *,
                   raw_report: str, raw_sha256: str) -> tuple[dict, dict[str, str]]:
    """The evidence report and the row assignment it records."""
    s1 = stage1["attribution"]
    s2 = stage2["attribution"]
    s3 = stage3["attribution"]
    assignment: dict[str, str] = {}
    records: dict[str, dict] = {}
    for row in full["mismatches"]:
        key = row_key(row)
        if key in assignment:
            raise ValueError(f"{key}: two FULL-report rows")
        stage1_mechanism = s1.get(key, {}).get("mechanism")
        stage3_mechanism = s3.get(key, {}).get("mechanism")
        entry = entry_of(row, stage1_mechanism, stage3_mechanism)
        assignment[key] = entry
        record = {
            "entry": entry,
            "axiom": row["left"],
            "policyengine": row["right"],
            "diff": row["difference"],
        }
        if row["concept"] == EITC:
            record["stage1"] = stage1_mechanism
            if key in s2:
                record["stage2"] = s2[key]["mechanism"]
            if key in s3:
                record["stage3"] = stage3_mechanism
        records[key] = record
    if len(assignment) != full["summary"]["mismatch_count"]:
        raise ValueError("the FULL report's rows are not its mismatch count")

    decomposition = stage2["decomposition"]
    explained = stage2["explained_units"]
    age_units = sorted(
        {str(unit) for unit in (*explained["age"], *explained["age+investment"])}, key=int
    )
    investment_units = sorted(
        {str(unit) for unit in (*explained["investment"], *explained["age+investment"])},
        key=int,
    )
    extra = stage3.get("base_counterfactual_only_rows")
    base_note = STAGE3_BASE_NOTE_2026_10_14 if extra is None else (
        "With the bridge's aggregate and every other mechanism applied, the base "
        f"leaves every stage-1 investment row plus {len(extra)} rows the full run "
        f"does not have ({', '.join(extra) or 'none'}). They are counterfactual-only "
        "and are not attributed."
    )
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "suite": "fiit-ecps",
        "run": {
            "report": raw_report,
            "report_sha256": raw_sha256,
            "provenance": full["provenance"],
            "dataset_identity": full.get("dataset_identity"),
            "mismatch_count": full["summary"]["mismatch_count"],
        },
        "method": (
            "Each mechanism is one Axiom-side input change that makes Axiom see "
            "what PolicyEngine-US 1.729.0 sees; the PolicyEngine leg is fixed. "
            "Every combination of mechanisms re-runs the Axiom EITC surface "
            "over the affected tax units, and a row is attributed to the "
            "smallest set whose re-run clears it. Stage 1: age, partnership, "
            "investment (2^3 combinations). Stage 2, on stage 1's residual: "
            "se_loss, seca on top of all stage-1 mechanisms (2^2). Stage 3, on "
            "the investment rows: the five ways the two 32(i)(2) aggregates "
            "differ (2^5), with every other mechanism applied."
        ),
        "checks": {
            "stage1_baseline_reproduces_full_run": stage1["baseline_reproduces_full_run"],
            "stage1_baseline_value_drift_rows": len(stage1["baseline_value_drift"]),
            "explain_mode_sample_tax_units": stage1["explain_sample_tax_units"],
            "explain_mode_sample_matches_fast_full_run": stage1[
                "explain_sample_matches_full_run"
            ],
            "stage2_base_reproduces_stage1": stage2["base_reproduces_stage1_all_mechanisms"],
            "stage2_all_mechanisms_rows_left": len(stage2["variants"]["se_loss+seca"]["rows"]),
            "stage3_switch_model_reproduces_both_aggregates": stage3["switch_model_exact"],
            "stage3_policyengine_aggregate_clears_all": stage3[
                "policyengine_aggregate_variant_clears_all"
            ],
            "stage3_base_note": base_note,
            "age_units_childless_filers_65_plus_dependent_25_64": len(age_units),
        },
        "entries": counts_of(assignment),
        "rows": dict(sorted(records.items())),
        "age_units": {unit: decomposition[unit] for unit in age_units},
        "investment_units": {unit: decomposition[unit] for unit in investment_units},
    }
    return evidence, assignment


def build_dispositions(evidence: dict, assignment: dict[str, str]) -> str:
    """``dispositions/fiit-ecps.yaml`` (before selector bindings are stamped)."""
    counts = {entry: value["rows"] for entry, value in evidence["entries"].items()}
    units = {entry: value["tax_units"] for entry, value in evidence["entries"].items()}
    rows = evidence["rows"]
    se_sub = collections.Counter(
        rows[key]["stage2"] for key, entry in assignment.items() if entry == "se_projection"
    )
    inv_sub = collections.Counter(
        rows[key]["stage3"] for key, entry in assignment.items() if entry == "pe_investment"
    )

    def src(entry):
        return f"{EVIDENCE}#{entry}"

    def head(entry):
        entry_id, kind = ENTRIES[entry]
        concept = {
            "tax_before_credits": TAX_BEFORE_CREDITS,
            "capital_gain": CAPITAL_GAIN,
            "ctc": CTC,
        }.get(entry, EITC)
        return {
            "id": entry_id,
            "concept": concept,
            "kind": "amount_difference",
            "case_selector": {"case_ids_by_output": selector(assignment, entry)},
            "disposition": kind,
        }

    entries = [
        {
            **head("se_projection"),
            "evidence": {
                "mechanism": (
                    "The bridge computes Axiom's 26 USC 32(c)(2) boundary input "
                    "net_earnings_from_self_employment_after_self_employment_tax_deduction "
                    "by flooring each filer's self-employment amount at zero and "
                    f"deducting a flat {FLAT_SECA_FRACTION:.8f} of it (one-half of "
                    "15.3% of 92.35%). PolicyEngine-US 1.729.0's eitc_earned_income "
                    "sums the non-dependents' gross amounts and subtracts each "
                    "filer's self_employment_tax_ald_person, which is one-half of "
                    "the SECA tax it computes and so stops at the OASDI "
                    "contribution base (26 USC 164(f)(1), 1402(b)). Per-row "
                    "counterfactual with every other mechanism applied: "
                    f"{counts['se_projection']} rows over {units['se_projection']} "
                    f"tax units clear when the input is computed as PolicyEngine "
                    f"does; {se_sub['seca']} on the deduction alone, "
                    f"{se_sub['se_loss']} on summing before flooring alone, and "
                    f"{se_sub['se_loss+seca']} only on both. Tracked in "
                    "TheAxiomFoundation/axiom-oracles#640."
                ),
                "sources": [src("se_projection")],
                "upstream_url": "https://github.com/TheAxiomFoundation/axiom-oracles/issues/640",
            },
            "linked_issue": "https://github.com/TheAxiomFoundation/axiom-oracles/issues/640",
            "expires_on_source_change": True,
        },
        {
            **head("partnership"),
            "evidence": {
                "mechanism": (
                    "The pinned Populace artifact (populace-us-2024-f0af251) "
                    "stores K-1 partnership self-employment earnings as "
                    "partnership_se_income, the variable PolicyEngine-US #8614 "
                    "renamed partnership_self_employment_net_earnings. "
                    "PolicyEngine-US 1.729.0 carries #8614 (its release commit "
                    "180410fe descends from #8614's merge 1de4bff6) and reads "
                    "only the new name, which the artifact does not store, so "
                    "its eitc_earned_income has $0 of partnership earnings. "
                    "The bridge feeds Axiom the stored partnership_se_income. "
                    "PolicyEngine/microcosm#35 asked for the rename; it did not "
                    "reach this build. Per-row counterfactual: "
                    f"{counts['partnership']} rows over {units['partnership']} tax "
                    "units clear when Axiom's partnership_se_income is set to 0, "
                    "what PolicyEngine reads. Tax unit 154343: partnership "
                    "earnings 126,691.93 times one minus the flat 164(f) "
                    "fraction is Axiom's 117,741.43; PolicyEngine 0."
                ),
                "arithmetic": [
                    {
                        "expression": "126691.93286410396 * (1 - 0.07064775)",
                        "equals": 117741.43,
                        "tolerance": 0.01,
                    }
                ],
                "sources": [src("partnership")],
                "upstream_url": "https://github.com/PolicyEngine/microcosm/issues/35",
            },
            "expires_on_source_change": True,
        },
        {
            **head("dividend_aggregate"),
            "evidence": {
                "mechanism": (
                    "The pinned Populace artifact stores dividend_income, which "
                    "PolicyEngine-US 1.729.0 defines as the sum of "
                    "qualified_dividend_income and non_qualified_dividend_income, "
                    "as an input beside those components, and the two disagree. "
                    "PolicyEngine reads the stored aggregate into "
                    "eitc_relevant_investment_income; the bridge sums the "
                    "components into Axiom's 26 USC 32(i)(2) input. "
                    "PolicyEngine/microcosm#37 (merged 2026-06-14) added an "
                    "export gate against formula-owned variables; the "
                    "2026-06-20 build still carries this one. Per-row "
                    f"counterfactual: {counts['dividend_aggregate']} rows over "
                    f"{units['dividend_aggregate']} tax units clear on the "
                    "dividends alone, with every other mechanism applied. Tax "
                    "unit 100004: the components give dividends of 420.20 and "
                    "an Axiom aggregate of 11,681.91, under the $12,200 limit; "
                    "the stored aggregate gives 5,000 and PolicyEngine's "
                    "16,261.71, over it."
                ),
                "arithmetic": [
                    {
                        "expression": "57.56 + 420.2 + 7664.36 + 3539.79",
                        "equals": 11681.91,
                        "tolerance": 0.01,
                    },
                    {
                        "expression": "57.56 + 5000 + 7664.36 + 3539.79",
                        "equals": 16261.71,
                        "tolerance": 0.01,
                    },
                ],
                "sources": [src("dividend_aggregate")],
                "upstream_url": "https://github.com/PolicyEngine/microcosm/pull/37",
            },
            "expires_on_source_change": True,
        },
        {
            **head("pe_investment"),
            "evidence": {
                "mechanism": (
                    "PolicyEngine-US 1.729.0's eitc_relevant_investment_income "
                    "(net_investment_income plus tax-exempt interest, with "
                    "max(0, net_capital_gains) for capital gains) departs from "
                    "26 USC 32(i)(2) and Pub. 596 Worksheet 1 in four ways, all "
                    "fixed upstream since: it leaves out capital gain "
                    "distributions and nets rental losses against other income "
                    "(PolicyEngine/policyengine-us#9572, closing #9567), counts "
                    "dependents' amounts (#9883) and leaves out farm rental "
                    "income (#9889; both tracked in #9635). The bridge follows "
                    "Worksheet 1. Per-row counterfactual with every other "
                    f"mechanism applied: {counts['pe_investment']} rows over "
                    f"{units['pe_investment']} tax units clear only through one "
                    "of these four ("
                    + ", ".join(f"{k} {v}" for k, v in sorted(inv_sub.items()))
                    + "; a row listed with div_aggregate needs or is equally "
                    "cleared by the Populace dividend artifact too). Tax unit "
                    "101289: Axiom 24,108.76 = interest 1,923.04 + farm rent "
                    "22,185.72; PolicyEngine 1,923.04. Tax unit 31656: "
                    "PolicyEngine adds a dependent's 690.67 of interest."
                ),
                "arithmetic": [
                    {
                        "expression": "1923.0374755859375 + 22185.71875",
                        "equals": 24108.76,
                        "tolerance": 0.01,
                    },
                    {
                        "expression": (
                            "5756.72119140625 + 5870.68115234375 + 690.6683959960938"
                        ),
                        "equals": 12318.07,
                        "tolerance": 0.01,
                    },
                ],
                "sources": [src("pe_investment")],
                "upstream_url": f"{PE}/issues/9567",
            },
            "linked_issue": f"{PE}/issues/9635",
            "axiom_encoding_debt": "https://github.com/TheAxiomFoundation/rulespec-us/issues/1416",
            "expires_on_source_change": True,
        },
        {
            **head("age"),
            "evidence": {
                "mechanism": (
                    "26 USC 32(c)(1)(A)(ii)(II) tests the age of \"such "
                    "individual (or, if the individual is married, either the "
                    "individual or the individual's spouse)\". PolicyEngine-US "
                    "1.729.0's eitc_demographic_eligible applies the window with "
                    "tax_unit.any() over every member, dependents included; "
                    "PolicyEngine/policyengine-us#9132 (closing #9131, first "
                    "released in 1.779.8) masks it to non-dependents. Axiom's "
                    "projection counts only the filers (axiom-oracles#632). In "
                    f"all {units['age']} tax units the credit is childless "
                    "(PolicyEngine eitc_child_count 0), every filer is 65 or "
                    "older and a dependent is aged 25-64. Per-row "
                    f"counterfactual: {counts['age']} rows clear when Axiom's "
                    "input is computed over every member, as PolicyEngine does; "
                    "11 of them only together with the investment-income "
                    "difference. The input is a free boundary input in "
                    "us/statutes/26/32.yaml, so no RuleSpec test pins Axiom's "
                    "answer: rulespec-us#1776."
                ),
                "sources": [src("age")],
                "upstream_url": f"{PE}/issues/9131",
            },
            "linked_issue": f"{PE}/issues/9131",
            "axiom_encoding_debt": "https://github.com/TheAxiomFoundation/rulespec-us/issues/1776",
            "expires_on_source_change": True,
        },
        {
            **head("tax_before_credits"),
            "evidence": {
                "mechanism": (
                    "A rounding-scale difference between the two engines' rate "
                    "applications, attributed in July 2026 to bracket-boundary "
                    "rounding. This run re-verifies the per-row signature, not "
                    f"that attribution: all {counts['tax_before_credits']} rows "
                    "have |diff| <= $5.83 with both signs, as in July. "
                    "Representative ecps-tax_unit_154369: Axiom 2,789,654.17 "
                    "vs PE 2,789,660.00."
                ),
                "arithmetic": [
                    {
                        "expression": "2789654.1703 - 2789660.0",
                        "equals": -5.8297,
                        "tolerance": 0.01,
                    },
                    {
                        "expression": "5.8297 / 2789660.0",
                        "equals": 0.0000020897,
                        "tolerance": 0.0000001,
                    },
                ],
                "sources": [src("tax_before_credits")],
            },
            "expires_on_source_change": True,
        },
        {
            **head("capital_gain"),
            "evidence": {
                "mechanism": (
                    "adjusted_net_capital_gain float noise. All "
                    f"{counts['capital_gain']} rows of the 2026-10-14 run have "
                    "|diff| <= $3.25 (max relative 5.0e-7). Representative "
                    "ecps-tax_unit_161790: Axiom 6,471,728.75 vs PE 6,471,732.00."
                ),
                "arithmetic": [
                    {
                        "expression": "6471728.7516 - 6471732.0",
                        "equals": -3.2484,
                        "tolerance": 0.01,
                    },
                    {
                        "expression": "3.2484 / 6471732.0",
                        "equals": 0.000000502,
                        "tolerance": 0.00000001,
                    },
                ],
                "sources": [src("capital_gain")],
            },
            "expires_on_source_change": True,
        },
        {
            **head("ctc"),
            "evidence": {
                "mechanism": (
                    "26 USC 24(b) phaseout: the credit reduces by $50 per $1,000 "
                    f"(or fraction) of AGI over the threshold. All {counts['ctc']} "
                    "rows of the 2026-10-14 run are exactly +$50, one $1,000 "
                    "increment x 5%, a difference of one increment in how each "
                    "engine rounds excess AGI up to the next $1,000. "
                    "Representative ecps-tax_unit_154343: Axiom 15,012,000 vs PE "
                    "15,011,950."
                ),
                "arithmetic": [
                    {"expression": "1000 * 0.05", "equals": 50.0, "tolerance": 0.001},
                    {
                        "expression": "15012000 - 15011950",
                        "equals": 50.0,
                        "tolerance": 0.001,
                    },
                ],
                "sources": [src("ctc")],
            },
            "expires_on_source_change": True,
        },
    ]
    header = f"""\
# Dispositions for fiit-ecps (Axiom RuleSpec vs PolicyEngine-US 1.729.0 over
# the pinned Populace artifact populace-us-2024-f0af251), refreshed from the
# 2026-10-14 run: rulespec-us 172bf04e, axiom-rules-engine v0.1.2 98af0dce,
# axiom-oracles with #632. {evidence['run']['mismatch_count']:,} mismatch rows; every one is
# in exactly one entry below, listed by output (case_ids_by_output), and each
# selector is bound to its rows (selector_binding), so a new mechanism in any
# of these concepts expires the entry instead of riding it.
#
# EITC rows were attributed per row by counterfactual: each mechanism is one
# Axiom-side input change that makes Axiom see what PolicyEngine sees, and a
# row belongs to the smallest set of changes whose re-run clears it. Method,
# checks and every row's attribution: {EVIDENCE}.
# Built by scripts/build_fiit_ecps_eitc_dispositions.py; audit with its --check.
#
#   {'entry':56s} {'rows':>6}  kind
"""
    for entry, (entry_id, kind) in ENTRIES.items():
        header += f"#   {entry_id:56s} {counts[entry]:>6,}  {kind}\n"
    header += """#
# This replaces the July entry eitc-earned-income-8614-partnership-scorp-split,
# whose case_id_prefix matched every tax unit's EITC rows and whose mechanism
# ("PolicyEngine 1.729.0 predates #8614") was wrong: 1.729.0 contains #8614.
"""
    document = {
        "schema": "axiom_oracles.dispositions.v1",
        "suite": "fiit-ecps",
        "updated": "2026-10-15",
        "entries": entries,
    }
    return header + yaml.safe_dump(document, sort_keys=False, width=88, allow_unicode=False)


def check(root: Path = ROOT) -> list[str]:
    """Every disagreement between the committed evidence, dispositions and report."""
    problems: list[str] = []
    try:
        _, full = bound_full_report(root)
    except (OSError, KeyError, TypeError, ValueError) as error:
        return [f"bound FULL report: {error}"]
    evidence = json.loads((root / EVIDENCE).read_text())
    dispositions = yaml.safe_load((root / DISPOSITIONS).read_text())
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        problems.append(f"{EVIDENCE}: schema is not {EVIDENCE_SCHEMA}")
    if evidence["run"]["provenance"] != full.get("provenance"):
        problems.append(f"{EVIDENCE}: run provenance is not the bound report's")

    records = evidence["rows"]
    full_rows = {row_key(row): row for row in full["mismatches"]}
    if len(full_rows) != len(full["mismatches"]):
        problems.append("the bound report repeats a mismatch row")
    for key in sorted(set(full_rows) ^ set(records)):
        side = "the bound report" if key in full_rows else EVIDENCE
        problems.append(f"{key}: only in {side}")
    assignment: dict[str, str] = {}
    for key in sorted(set(full_rows) & set(records)):
        row, record = full_rows[key], records[key]
        if (record["axiom"], record["policyengine"], record["diff"]) != (
            row["left"], row["right"], row["difference"]
        ):
            problems.append(f"{key}: evidence values differ from the bound report's")
        try:
            expected = entry_of(row, record.get("stage1"), record.get("stage3"))
        except ValueError as error:
            problems.append(str(error))
            continue
        if record["entry"] != expected:
            problems.append(f"{key}: entry {record['entry']!r}, stages give {expected!r}")
        assignment[key] = record["entry"]
    if evidence["entries"] != counts_of(
        {key: record["entry"] for key, record in records.items()}
    ):
        problems.append(f"{EVIDENCE}: entry counts are not its rows'")

    by_id = {entry["id"]: entry for entry in dispositions["entries"]}
    if [entry["id"] for entry in dispositions["entries"]] != [
        entry_id for entry_id, _ in ENTRIES.values()
    ]:
        problems.append(f"{DISPOSITIONS}: entries are not exactly {list(ENTRIES)}")
    for entry, (entry_id, kind) in ENTRIES.items():
        disposition = by_id.get(entry_id)
        if disposition is None:
            continue
        if disposition.get("disposition") != kind:
            problems.append(f"{entry_id}: disposition is not {kind}")
        selected = (disposition.get("case_selector") or {}).get("case_ids_by_output")
        if selected != selector(assignment, entry):
            problems.append(f"{entry_id}: selects other rows than its evidence")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stage1", type=Path)
    parser.add_argument("--stage2", type=Path)
    parser.add_argument("--stage3", type=Path)
    parser.add_argument("--raw-report", type=Path)
    args = parser.parse_args()
    if args.check:
        problems = check()
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            f"fiit-ecps EITC attribution: {len(problems)} problem(s)",
            file=sys.stderr,
        )
        return 1 if problems else 0
    if not all((args.stage1, args.stage2, args.stage3, args.raw_report)):
        parser.error("build needs --stage1, --stage2, --stage3 and --raw-report")
    raw = args.raw_report.resolve()
    try:
        raw_report = raw.relative_to(ROOT).as_posix()
    except ValueError:
        parser.error("--raw-report must be under this checkout's reports/")
    if not raw_report.startswith("reports/"):
        parser.error("--raw-report must be under this checkout's reports/")
    digest = hashlib.sha256()
    with raw.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    _, full = bound_full_report(ROOT)
    evidence, assignment = build_evidence(
        full,
        json.loads(args.stage1.read_text()),
        json.loads(args.stage2.read_text()),
        json.loads(args.stage3.read_text()),
        raw_report=raw_report,
        raw_sha256=digest.hexdigest(),
    )
    (ROOT / EVIDENCE).write_text(json.dumps(evidence, indent=1, sort_keys=True) + "\n")
    (ROOT / DISPOSITIONS).write_text(build_dispositions(evidence, assignment))
    print(
        {entry: value["rows"] for entry, value in evidence["entries"].items()},
        file=sys.stderr,
    )
    print(
        "now stamp the selector bindings: "
        "uv run scripts/stamp_selector_bindings.py fiit-ecps",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
