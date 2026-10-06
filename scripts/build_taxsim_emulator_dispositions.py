#!/usr/bin/env python3
"""Seed the recorded emulator ledger from explicitly reconciled row classes.

This is a selection recipe, not a legal adjudicator. Evidence and decisions
are deliberately static; reports determine membership, never who is right.
Run after replay, then run bind_dispositions.py and apply_dispositions.py.
--check verifies the complete generated YAML, including population bindings.
"""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_oracles.comparison.report_io import load_report  # noqa: E402
from scripts.bind_dispositions import computed_bindings  # noqa: E402

FEDERAL = "us:tax/federal-income-tax#liability"
STATE = "us:tax/state-income-tax#liability"
UPSTREAM = "https://github.com/PolicyEngine/policyengine-taxsim/"
SCORP_SOURCES = ["https://taxsim.nber.org/taxsimtest/", "https://taxsim.nber.org/taxsim35/"]
ADJUDICATION_SOURCE = "adjudications/taxsim-emulator.yaml"
SCORP_EVIDENCE = (
    "Adjudication pe-taxsim-1053 records the active/passive S-corp input question. "
    "Its current-law source does not prove applicability to these historical "
    "law years. The following numerical signature is a hypothesis, not a "
    "verified legal explanation; this class remains unexplained. "
)
ADDMED_URL = UPSTREAM + "issues/1225#issuecomment-5820033668"
ADDMED_EVIDENCE = (
    "Adjudication pe-taxsim-1225 verifies the TAXSIM maintainer's acknowledgment "
    "of the AddMed-in-fiitax error for 2000-2023. The recorded emulator has no "
    "addmed output (null); the row identity uses TAXSIM's reported addmed. "
)
REBATE_SOURCES = [ADJUDICATION_SOURCE + "#pe-taxsim-1068"]
REBATE_EVIDENCE = (
    "Adjudication pe-taxsim-1068 verifies the assessment-year versus payout-year "
    "rebate convention. Adding each engine's reported rebate back to its state "
    "liability brings every selected row within the suite's $15 tolerance. "
    "This identifies a convention; it does not establish legal correctness."
)
NIIT = "difference + right_aux.niit - left_aux.niit"
# Numerical signatures retained from PR4 as hypotheses. The operative text
# and unresolved historical scope are in adjudication pe-taxsim-1053.
SCORP_PASSIVE_NIIT = "right_aux.niit - left_aux.niit - 0.038 * facts.scorp"
NIIT_1411_URL = "https://www.law.cornell.edu/uscode/text/26/1411"
COMBINED = NIIT + " + right_aux.addmed"
REBATE = "difference + left_aux.srebate - right_aux.srebate"
COUNTY = "difference + 0.032 * (right_aux.v36 - right_aux.v25)"


def arithmetic(expression, tolerance=1, equals=0):
    return {"expression": expression, "equals": equals, "tolerance": tolerance}


def document(year: int) -> dict:
    suite = f"taxsim-emulator-ecps-{year}"
    report = load_report(ROOT / f"reports/taxsim-emulator/{suite}.json.gz")
    remaining = list(report["mismatches"])
    entries = []

    def add(entry_id, concept, predicate, kind, attribution, issue, mechanism,
            checks=(), sources=()):
        rows = [r for r in remaining if r["concept"] == concept and predicate(r)]
        if not rows:
            return
        ids = {r["case_id"] for r in rows}
        remaining[:] = [r for r in remaining
                        if r["concept"] != concept or r["case_id"] not in ids]
        evidence = {"mechanism": mechanism}
        if checks:
            evidence["row_arithmetic"] = list(checks)
        if sources:
            evidence["sources"] = list(sources)
        adjudication = {
            "addmed-in-fiitax": "pe-taxsim-1225",
            "rebate-timing": "pe-taxsim-1068",
            "la-standard-deduction-omission": "pe-taxsim-1222",
        }.get(entry_id)
        if entry_id == "niit-scorp" or entry_id.startswith("niit-scorp-at-cap-"):
            adjudication = "pe-taxsim-1053"
        entry = {
            "id": entry_id, "concept": concept, "kind": "amount_difference",
            "case_selector": {"case_ids": sorted(ids)}, "disposition": kind,
            "attribution": attribution, "evidence": evidence,
            "linked_issue": UPSTREAM + issue, "expires_on_source_change": True,
        }
        if adjudication:
            entry["adjudication"] = adjudication
            source = ADJUDICATION_SOURCE + "#" + adjudication
            if source not in evidence.setdefault("sources", []):
                evidence["sources"].append(source)
        entries.append(entry)

    def niit_gap(r):
        return r["aux"]["right"]["niit"] - r["aux"]["left"]["niit"]

    if year <= 2023:
        add("addmed-in-fiitax", FEDERAL,
            lambda r: abs(niit_gap(r)) <= .005
            and abs(r["difference"] + r["aux"]["right"]["addmed"]) <= 1,
            "upstream_engine_gap", "taxsim", "issues/1225",
            ADDMED_EVIDENCE + "NIIT agrees within half a cent; the liability gap "
            "equals minus TAXSIM AddMed within $1 on every selected row.",
            [arithmetic("right_aux.niit - left_aux.niit", .005),
             arithmetic("difference + right_aux.addmed")],
            [ADDMED_URL, UPSTREAM + "pull/1239"])

    def pure_niit(r, scorp):
        return ((r["facts"]["scorp"] != 0) == scorp
                and abs(niit_gap(r)) > .005 and abs(r["difference"] + niit_gap(r)) <= 1
                and (year >= 2024 or r["aux"]["right"]["addmed"] == 0))

    for scorp in (True, False):
        suffix = "scorp" if scorp else "no-scorp"
        scorp_check = arithmetic("facts.scorp / facts.scorp", 0, 1) if scorp else arithmetic("facts.scorp", 0)
        pure_checks = [arithmetic(NIIT), scorp_check]
        if year <= 2023:
            pure_checks.append(arithmetic("right_aux.addmed", 0))
        if scorp:
            # Preserve the historical uncapped numeric signature. It remains
            # unexplained until the registry proves law-year applicability.
            add("niit-scorp", FEDERAL,
                lambda r: pure_niit(r, True)
                and abs(niit_gap(r) - .038 * r["facts"]["scorp"]) <= 1,
                "unexplained", "two_sided", "issues/1053",
                SCORP_EVIDENCE + "On every selected row the liability gap lies in "
                "NIIT within $1, and TAXSIM's NIIT exceeds the emulator's by 3.8% of "
                "scorp within $1: the effect of counting scorp as passive net "
                "investment income under 26 U.S.C. 1411(a)(1) while neither NIIT is "
                "at the MAGI limit. This records the documented active/passive input "
                "ambiguity; it does not adjudicate which treatment is legally correct.",
                [*pure_checks, arithmetic(SCORP_PASSIVE_NIIT)],
                [*SCORP_SOURCES, NIIT_1411_URL])
            # Preserve the at-limit numeric signatures, also unexplained.
            # Neither this identity nor agreement of engine outputs proves law.
            for label, mstat, threshold in (("single", 1, 200000), ("joint", 2, 250000),
                                            ("separate", 6, 125000), ("dependent", 8, 200000)):
                def at_cap(r, mstat=mstat, threshold=threshold):
                    left, right = r["aux"]["left"], r["aux"]["right"]
                    limit = .038 * (right["v10"] - threshold)
                    return (pure_niit(r, True) and r["facts"]["mstat"] == mstat
                            and abs(left["v10"] - right["v10"]) <= 1 and limit > 0
                            and abs(right["niit"] - limit) <= 1
                            and left["niit"] < limit - .5
                            and left["niit"] + .038 * r["facts"]["scorp"] >= limit - 1)
                add(f"niit-scorp-at-cap-{label}", FEDERAL, at_cap,
                    "unexplained", "two_sided", "issues/1053",
                    SCORP_EVIDENCE + "On every selected row the liability gap lies in NIIT "
                    "within $1; AGI agrees within $1; TAXSIM's NIIT equals 3.8% of AGI "
                    f"over the ${threshold:,} threshold for mstat {mstat} within $1 (the "
                    "26 U.S.C. 1411(a)(1)(B) limit); and the emulator's NIIT is below that "
                    "limit while its implied net investment income plus scorp reaches it "
                    "(checked by the recipe and tests/test_taxsim_emulator_dispositions.py). "
                    "Counting scorp as passive therefore moves NIIT to the limit. This "
                    "assumes the engines agree on the other net investment income; it "
                    "records the documented input ambiguity, not which treatment is right.",
                    [*pure_checks, arithmetic("facts.mstat", 0, mstat),
                     arithmetic("left_aux.v10 - right_aux.v10"),
                     arithmetic(f"right_aux.niit - 0.038 * (right_aux.v10 - {threshold})")],
                    [*SCORP_SOURCES, NIIT_1411_URL])
            add("niit-scorp-unreconciled", FEDERAL,
                lambda r: pure_niit(r, True),
                "unexplained", "two_sided", "issues/1053",
                "The liability gap lies in NIIT within $1 and scorp is nonzero, but "
                "neither the uncapped (3.8% of scorp) nor the at-limit reconciliation "
                "holds, so the active/passive convention alone does not account for "
                "it. Possible causes, unverified: the engines' AGI differs, or their "
                "other net investment income differs (e.g. a state-tax allocation, "
                "#1226). Open; engine outputs do not establish the cause.",
                pure_checks, [*SCORP_SOURCES, NIIT_1411_URL])
        else:
            add("niit-no-scorp", FEDERAL,
                lambda r: pure_niit(r, False),
                "unexplained", "two_sided", "issues/1226",
                "The liability gap lies in NIIT within $1 despite scorp being zero. "
                "#1226 records a non-itemizer state-tax allocation error acknowledged "
                "by Feenberg, but these rows have not individually been shown to "
                "share that cause. Allocation is a hypothesis; engine outputs do "
                "not establish which amount is legally correct.",
                pure_checks, [UPSTREAM + "issues/1226"])

        if year <= 2023:
            add(f"niit-addmed-{suffix}", FEDERAL,
                lambda r, scorp=scorp: (r["facts"]["scorp"] != 0) == scorp
                and abs(niit_gap(r)) > .005
                and abs(r["difference"] + niit_gap(r) + r["aux"]["right"]["addmed"]) <= 1,
                "unexplained", "two_sided", "issues/1053" if scorp else "issues/1226",
                (SCORP_EVIDENCE if scorp else "The scorp input is zero. ")
                + ADDMED_EVIDENCE + "Both NIIT and AddMed enter the reconciled "
                "liability identity. The AddMed acknowledgment does not resolve "
                "the NIIT question; this mixed class remains unexplained. "
                "The identity locates the difference, not legal correctness.",
                [arithmetic(COMBINED), scorp_check],
                [ADDMED_URL, UPSTREAM + "issues/1226", *SCORP_SOURCES])

    add("rebate-timing", STATE,
        lambda r: abs(r["difference"] + r["aux"]["left"]["srebate"]
                      - r["aux"]["right"]["srebate"]) <= 15,
        "explained_residual", "convention", "issues/1068", REBATE_EVIDENCE,
        [arithmetic(REBATE, 15)], REBATE_SOURCES)

    if year >= 2024:
        add("md-august-county-signature", STATE,
            lambda r: r["facts"]["state"] == "MD" and abs(r["difference"]
            + .032 * (r["aux"]["right"]["v36"] - r["aux"]["right"]["v25"])) <= 1,
            "unexplained", "two_sided", "pull/1223",
            "On August fallback rows, the liability gap equals minus 3.2% of "
            "TAXSIM state taxable income (v36) less federal EITC (v25), within $1. "
            "PR #1223 describes the county-tax hypothesis and keeps the emulator "
            "state-only. The output identity is not legal evidence or a TAXSIM "
            "maintainer acknowledgment. The published-source comparison has not "
            "been independently reproduced here; no Fortran is redistributed.",
            [arithmetic(COUNTY)], [UPSTREAM + "pull/1223",
             UPSTREAM + "blob/a80b8c1dca088b147e36f9c770ed92d403d747f6/README.md"])

    for concept, name in ((FEDERAL, "federal"), (STATE, "state")):
        add(f"al-{name}-residual", concept,
            lambda r: r["facts"]["state"] == "AL",
            "unexplained", "two_sided", "pull/1204",
            "Alabama residual after the earlier reconciled classes. PR #1204 "
            "reports broad income-relative agreement but weaker $15 agreement, "
            "and a federal change in 277-279 households after state recoding. "
            "These recorded rows do not contain paired state-zero reruns, so "
            "membership does not assert that they are those affected households. "
            "No common numerical reconciliation or legal attribution is established.")

    if year == 2025:
        add("la-standard-deduction-omission", STATE,
            lambda r: r["facts"]["state"] == "LA"
            and r["aux"]["left"]["v34"] in (12500, 25000)
            and abs(r["aux"]["left"]["v32"] - r["aux"]["right"]["v32"]) <= 1
            and abs(r["aux"]["right"]["v36"] - r["aux"]["left"]["v36"]
                    - r["aux"]["left"]["v34"]) <= 1
            and abs(r["difference"] + .03 * (r["aux"]["right"]["v36"]
                                            - r["aux"]["left"]["v36"])) <= 1,
            "upstream_engine_gap", "taxsim", "issues/1222",
            "Adjudication pe-taxsim-1222 verifies the TAXSIM maintainer's acknowledgment "
            "of the Louisiana 2025 standard-deduction omission. "
            "Selected rows have agreeing state AGI within $1, a taxable-income "
            "gap equal to PE's reported $12,500 or $25,000 deduction within $1, "
            "and a liability gap equal to minus 3% of that taxable-income gap "
            "within $1. Other Louisiana rows are not attributed by this identity.",
            [arithmetic("left_aux.v34", 0, [12500, 25000]),
             arithmetic("left_aux.v32 - right_aux.v32"),
             arithmetic("right_aux.v36 - left_aux.v36 - left_aux.v34"),
             arithmetic("difference + 0.03 * (right_aux.v36 - left_aux.v36)")],
            [UPSTREAM + "issues/1222#issuecomment-5833721957"])
        add("la-other-state-residual", STATE,
            lambda r: r["facts"]["state"] == "LA",
            "unexplained", "two_sided", "issues/1222",
            "Louisiana 2025 rows outside the fully reconciled deduction class. "
            "#1222 is a related acknowledged issue, but these residuals do not "
            "all satisfy that mechanism. Their causes and ownership remain open.")

    bindings, notes = computed_bindings(entries, report, lane=True,
                                        oracle_binding=True, legacy_version=None)
    assert not notes, notes
    for entry in entries:
        entry.update(bindings[entry["id"]])
    return {"schema": "axiom_oracles.dispositions.v1", "suite": suite,
            "updated": "2026-09-27", "entries": entries}


def probe_document():
    suite = "taxsim-emulator-probes"
    report = load_report(ROOT / f"reports/taxsim-emulator/{suite}.json")
    entries = []
    for row in report["mismatches"]:
        assert row["concept"] == FEDERAL
        state = row["facts"]["taxsim_state"]
        assert state in (0, 44)
        if state == 0:
            # A PR body is not a qualifying maintainer comment atom. Preserve
            # the observation, but withdraw the unsupported engine attribution.
            entries.append({
                "id": "state-zero-sales-tax",
                "concept": FEDERAL, "kind": "amount_difference", "case_id": row["case_id"],
                "disposition": "unexplained", "attribution": "two_sided",
                "adjudication": "pe-taxsim-1249",
                "evidence": {
                    "mechanism": "Observed state-zero probe: TAXSIM fiitax 50165.00 and "
                    "emulator fiitax 49315.8515625. Adjudication pe-taxsim-1249 has no "
                    "qualifying maintainer comment acknowledging an emulator error. "
                    "The sales-tax explanation in the linked PR remains a hypothesis "
                    "under this registry's evidence rules; engine outputs are not proof.",
                    "row_arithmetic": [arithmetic("difference", .000001, row["difference"])],
                    "sources": [UPSTREAM + "pull/1249", UPSTREAM + "pull/1204"],
                },
                "linked_issue": UPSTREAM + "pull/1249", "expires_on_source_change": True,
            })
            continue
        entries.append({
            "id": "texas-sales-tax-proxy",
            "concept": FEDERAL, "kind": "amount_difference", "case_id": row["case_id"],
            "disposition": "unexplained", "attribution": "two_sided",
            "evidence": {
                "mechanism": "Observed native-SALT macOS probe from PR #1204 at state 44 "
                "(Texas): TAXSIM fiitax 49618.30, emulator 49315.8515625. Both engines take "
                "a sales-tax deduction here, in different amounts; PR #1249 fixed only the "
                "state-0 case. The cause of this difference is not established. Bound to "
                "the observed macOS binary; expires on changes to either output.",
                "row_arithmetic": [arithmetic("difference", .000001, row["difference"])],
                "sources": [UPSTREAM + "pull/1204", UPSTREAM + "pull/1249"],
            },
            "linked_issue": UPSTREAM + "pull/1204", "expires_on_source_change": True,
        })
    bindings, notes = computed_bindings(entries, report, lane=True,
                                        oracle_binding=True, legacy_version=None)
    assert not notes, notes
    for entry in entries:
        entry.update(bindings[entry["id"]])
    return {"schema": "axiom_oracles.dispositions.v1", "suite": suite,
            "updated": "2026-09-27", "entries": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift = False
    for doc in [*(document(year) for year in range(2021, 2026)), probe_document()]:
        path = ROOT / "dispositions" / f"{doc['suite']}.yaml"
        rendered = yaml.safe_dump(doc, sort_keys=False, width=100)
        if args.check:
            if not path.exists() or path.read_text() != rendered:
                print(f"drift: {path.relative_to(ROOT)}")
                drift = True
        else:
            path.write_text(rendered)
            print(f"wrote {path.relative_to(ROOT)} ({len(doc['entries'])} entries)")
    if args.check and not drift:
        print("emulator ledger selections, evidence and bindings match the reports")
    return int(drift)


if __name__ == "__main__":
    # The report graphs are large and acyclic, as in the comparison CLI.
    # Reference counting releases each year's graph as the recipe advances.
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        raise SystemExit(main())
    finally:
        if gc_was_enabled:
            gc.enable()
