#!/usr/bin/env python3
"""Source-linked China list3/list4A projections with the beer overlap preserved."""

from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import us_tariff_continuation_runtime as runtime  # noqa: E402
from scripts import us_tariff_live_source_evidence as sources  # noqa: E402

OUTPUT = ROOT / "reference/us-tariff-schedule/boundary-evidence/china-lists.json"
WITNESS = runtime.original.closure.WITNESS_MODULE
INPUTS = ("entry_is_china_301_list123", "entry_is_china_301_list4a")
FLAGS = (
    *INPUTS,
    "entry_is_china_301_2024_action",
    "entry_is_china_301_solar",
    "entry_is_line_d",
)
OUT = "china_section_301_component_rate"
LINES = (
    ("7202.11.10.00", 7202111000, 72, True, "0.25"),
    ("2203.00.00.30", 2203000000, 22, True, "0.25"),
    ("9506.62.40.40", 9506624040, 95, False, "0.075"),
)
MODULES = (WITNESS,) + tuple(
    f"us/policies/cbp/us-tariff-schedule/generated/ch{n}/ch{n}.yaml"
    for n in (72, 22, 95)
)
DAY = "2026-08-03"
PAGES = (269, 273, 287, 329, 330, 340, 672, 674)


def source_records():
    live = sources.build(sources.DIRECTORY, sources.boundary.closure.CORPUS)
    sources.require(
        sources.RECEIPT.read_bytes() == sources.render(live),
        "live source receipt drift",
    )
    records = []
    for number, raw in enumerate(
        (sources.DIRECTORY / "provisions.jsonl").read_bytes().splitlines(), 1
    ):
        row = json.loads(raw)
        if row["citation_path"] in {
            f"us/statute/hts/chapter-99/page-{n}" for n in PAGES
        }:
            records.append(
                {
                    "jsonl_line": number,
                    "raw_record_sha256": sources.sha(raw),
                    "record": row,
                }
            )
    sources.require(len(records) == len(PAGES), "China list source population changed")
    return records


def fixtures():
    return [
        {
            "case_id": f"list-{key}-{country}",
            "day": DAY,
            "hts_number": hts,
            "rate_line": key,
            "chapter": chapter,
            "country": country,
            "source_membership": {INPUTS[0]: list3, INPUTS[1]: not list3},
            "expected": rate if country == "CN" else "0",
        }
        for (hts, key, chapter, list3, rate), country in itertools.product(
            LINES, ("CN", "HK", "FR")
        )
    ]


def build():
    records = source_records()
    rows = fixtures()
    runs, adapter_rows, mismatches = [], [], []
    with runtime.compiled(MODULES) as execute:
        for row in rows:
            result = execute.entry_flags(
                row["rate_line"], row["hts_number"], row["country"], entry_date=DAY
            )
            flags = {name: result[name] for name in FLAGS}
            sources.require(
                all(flags[k] == v for k, v in row["source_membership"].items()),
                "source-positive list membership mismatch",
            )
            adapter_rows.append(
                {
                    "case_id": row["case_id"],
                    "actual_flags": flags,
                    "membership_matches_source": True,
                }
            )
        by_id = {row["case_id"]: row["actual_flags"] for row in adapter_rows}
        for module in MODULES:
            relevant = (
                rows
                if module == WITNESS
                else [r for r in rows if f"/ch{r['chapter']}/" in module]
            )
            cases = []
            for row in relevant:
                facts = {"country_of_origin": row["country"]}
                if module == WITNESS:
                    facts["hts_number"] = row["hts_number"]
                else:
                    facts.update(hts_line=row["rate_line"], **by_id[row["case_id"]])
                cases.append({**row, "facts": facts})
            run = execute(module, cases, (OUT,))
            run["input_mode"] = (
                "direct_witness" if module == WITNESS else "actual_adapter"
            )
            for actual, row in zip(run["results"], relevant, strict=True):
                observed = actual["actual"][OUT]
                actual.update(
                    expected_from_source=row["expected"],
                    source_match=observed == row["expected"],
                )
                if not actual["source_match"]:
                    sources.require(
                        row["hts_number"] == "2203.00.00.30"
                        and row["country"] == "CN"
                        and module != WITNESS
                        and observed == "0.5",
                        "unexpected China list counterexample",
                    )
                    mismatches.append(
                        {
                            "module": module,
                            "case_id": row["case_id"],
                            "expected": row["expected"],
                            "actual": observed,
                        }
                    )
            runs.append(run)
        adapter_binding = execute.adapter_binding
    sources.require(len(mismatches) == 1, "beer overlap population changed")
    return {
        "schema": "axiom_oracles.us_tariff_schedule.china_list_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "live_source_receipt_sha256": sources.sha(sources.RECEIPT.read_bytes()),
        "source_records": records,
        "visually_checked_pdf_pages": [273, 287, 340, 672, 674],
        "fixtures": rows,
        "adapter": adapter_binding,
        "adapter_results": adapter_rows,
        "runs": runs,
        "known_mismatches": mismatches,
        "scopes": [
            {
                "input": INPUTS[0],
                "status": "blocked_on_beer_list3_overlap",
                "source_evidence": "captured_live_primary_source",
                "grounding": "uncaptured",
            },
            {
                "input": INPUTS[1],
                "status": "bounded_nonexcluded_list4a_replay_matches",
                "source_evidence": "captured_live_primary_source",
                "grounding": "uncaptured",
            },
        ],
        "validation": {
            "real_runtime_cases": 18,
            "real_runtime_outputs": 18,
            "adapter_cases": 9,
            "matching_cases": 17,
            "known_mismatching_cases": 1,
            "all_cases_match": False,
            "new_campaign_rows_scanned": 0,
        },
        "blocker": {
            "path": "us/policies/cbp/us-tariff-schedule/generated/ch22/ch22.yaml",
            "lines": [3243, 3246],
            "finding": "The generated component adds list123 and the retained entry_is_line_d term. The real adapter correctly marks beer as both, so one China entry receives two 25% additions instead of the source single 25% addition.",
            "next_step": "Repair composition overlap through the authorized deterministic composition workflow, with findings/replay and existing review/admission gates. Preserve the frozen campaign proof generation.",
        },
        "limitations": [
            "This is an August3 Rev15 snapshot projection with no transaction-specific exclusion or Chapter98 claim; origin and classification are stipulated.",
            "The aggregate list123 flag is exercised on list3 members only. Complete list1/list2 membership, all excluded descriptions and historical amendments are not validated.",
            "The actual adapter resolves printed code incidence. It does not establish the absence of every heading-specific exclusion or actual-entry qualification.",
            "The list3/list4A rates come from the separate authoritative headings, not from observed runtime values. No membership flag or RuleSpec code was patched.",
            "All actual-entry groundings, final Fable review and current-base admission gates remain open.",
        ],
        "claim": {"closed": False, "certified": False, "release_authorized": False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = build()
        body = sources.render(result)
        if args.check:
            sources.require(OUTPUT.read_bytes() == body, "China list evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("China list evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
