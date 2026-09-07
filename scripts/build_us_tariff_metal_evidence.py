#!/usr/bin/env python3
"""Bound the primary-metal flags and expose the missing UK95 qualification."""

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
from scripts import build_us_tariff_identity_evidence as identity  # noqa: E402

OUTPUT = ROOT / "reference/us-tariff-schedule/boundary-evidence/primary-metals.json"
WITNESS = runtime.original.closure.WITNESS_MODULE
INPUTS = ("entry_is_section_232_aluminum", "entry_is_section_232_steel")
OUTS = ("section_232_aluminum_component_rate", "section_232_steel_component_rate")
LINES = (
    ("7601.10.30.00", 7601103000, 76, "aluminum"),
    ("7208.10.30.00", 7208103000, 72, "steel"),
    ("7202.11.10.00", 7202111000, 72, "neither"),
    ("9506.62.40.40", 9506624040, 95, "neither"),
)
MODULES = (WITNESS,) + tuple(
    f"us/policies/cbp/us-tariff-schedule/generated/ch{n}/ch{n}.yaml"
    for n in (76, 72, 95)
)
DAY = "2026-08-03"


def source_evidence():
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
            f"us/statute/hts/chapter-99/page-{n}"
            for n in (236, 237, 238, 239, 240, 241, 242, 668)
        }:
            records.append(
                {
                    "jsonl_line": number,
                    "raw_record_sha256": sources.sha(raw),
                    "record": row,
                }
            )
    sources.require(len(records) == 8, "metal source record population changed")
    pdf = identity.DIRECTORY / "chapter72.pdf"
    sources.require(
        sources.sha(pdf.read_bytes()) == identity.DOCUMENTS[72][0],
        "live Chapter72 source changed",
    )
    proc = subprocess.run(
        ["pdftotext", "-f", "18", "-l", "18", "-layout", str(pdf), "-"],
        capture_output=True,
        check=True,
    )
    return {
        "chapter99_live_receipt_sha256": sources.sha(sources.RECEIPT.read_bytes()),
        "chapter99_records": records,
        "visually_checked_chapter99_pages": [236, 241, 668],
        "identity_receipt_sha256": sources.sha(identity.OUTPUT.read_bytes()),
        "steel_statistical_line": {
            "pdf": sources.bound(pdf),
            "pdf_page": 18,
            "printed_page": "72-14",
            "extracted_text": proc.stdout.decode(),
            "visually_checked": True,
        },
    }


def fixtures():
    rows = []
    for (hts, key, chapter, metal), country, share in itertools.product(
        LINES, ("FR", "GB"), (94, 95)
    ):
        rate = "0.25" if country == "GB" and share >= 95 else "0.5"
        expected = {
            OUTS[0]: rate if metal == "aluminum" else "0",
            OUTS[1]: rate if metal == "steel" else "0",
        }
        rows.append(
            {
                "case_id": f"metal-{key}-{country}-{share}",
                "day": DAY,
                "hts_number": hts,
                "rate_line": key,
                "chapter": chapter,
                "country": country,
                "source_membership": {
                    INPUTS[0]: metal == "aluminum",
                    INPUTS[1]: metal == "steel",
                },
                "metal": metal,
                "stipulated_uk_qualifying_metal_percent": share,
                "stipulated_fact_meaning": "For aluminum, the percent smelted or most recently cast in the UK; for steel, the percent melted and poured in the UK. This source fact has no supported input in the pinned component.",
                "expected_from_source": expected,
            }
        )
    return rows


def build():
    source = source_evidence()
    rows = fixtures()
    runs = []
    adapter_rows = []
    mismatches = []
    with runtime.compiled(MODULES) as execute:
        for row in rows:
            actual = execute.entry_flags(
                row["rate_line"], row["hts_number"], row["country"], entry_date=DAY
            )
            flags = {name: actual[name] for name in INPUTS}
            sources.require(
                flags == row["source_membership"],
                "primary-metal adapter membership mismatch",
            )
            adapter_rows.append(
                {
                    "case_id": row["case_id"],
                    "actual_flags": flags,
                    "matches_source_membership": True,
                }
            )
        by_id = {row["case_id"]: row["actual_flags"] for row in adapter_rows}
        for module in MODULES:
            relevant = [
                row
                for row in rows
                if (
                    row["metal"] != "steel"
                    if module == WITNESS
                    else f"/ch{row['chapter']}/" in module
                )
            ]
            outputs = OUTS[:1] if module == WITNESS else OUTS
            cases = []
            for row in relevant:
                facts = {"country_of_origin": row["country"]}
                if module == WITNESS:
                    facts["hts_number"] = row["hts_number"]
                else:
                    facts.update(
                        hts_line=row["rate_line"],
                        entry_is_line_d=False,
                        **by_id[row["case_id"]],
                    )
                cases.append({**row, "facts": facts})
            run = execute(module, cases, outputs)
            run["input_mode"] = (
                "direct_witness" if module == WITNESS else "actual_adapter"
            )
            for actual, row in zip(run["results"], relevant, strict=True):
                expected = {name: row["expected_from_source"][name] for name in outputs}
                differences = {
                    name: {"expected": value, "actual": actual["actual"][name]}
                    for name, value in expected.items()
                    if actual["actual"][name] != value
                }
                actual.update(
                    expected_from_source=expected,
                    source_match=not differences,
                    differences=differences,
                )
                if differences:
                    sources.require(
                        row["country"] == "GB"
                        and (
                            (
                                row["metal"] == "aluminum"
                                and row["stipulated_uk_qualifying_metal_percent"] == 94
                                and differences
                                == {OUTS[0]: {"expected": "0.5", "actual": "0.25"}}
                            )
                            or (
                                row["metal"] == "steel"
                                and row["stipulated_uk_qualifying_metal_percent"] == 95
                                and differences
                                == {OUTS[1]: {"expected": "0.25", "actual": "0.5"}}
                            )
                        ),
                        "unexpected metal counterexample",
                    )
                    mismatches.append(
                        {
                            "module": module,
                            "case_id": row["case_id"],
                            "stipulated_uk_qualifying_metal_percent": row[
                                "stipulated_uk_qualifying_metal_percent"
                            ],
                            "differences": differences,
                        }
                    )
            runs.append(run)
        adapter_binding = execute.adapter_binding
    sources.require(
        len(mismatches) == 3 and sum(len(run["results"]) for run in runs) == 28,
        "metal replay population changed",
    )
    return {
        "schema": "axiom_oracles.us_tariff_schedule.primary_metal_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "sources": source,
        "fixtures": rows,
        "adapter": adapter_binding,
        "adapter_results": adapter_rows,
        "runs": runs,
        "known_mismatches": mismatches,
        "scopes": [
            {
                "input": name,
                "source_evidence": "captured_live_primary_source",
                "status": "blocked_on_missing_uk_note16_d_qualification",
                "grounding": "uncaptured",
            }
            for name in INPUTS
        ],
        "validation": {
            "real_runtime_cases": 28,
            "real_runtime_outputs": 44,
            "adapter_cases": 16,
            "matching_cases": 25,
            "known_mismatching_cases": 3,
            "all_cases_match": False,
            "new_campaign_rows_scanned": 0,
        },
        "blocker": {
            "source": "USITC Rev15 note16(d), PDF page241, and headings9903.82.02/.04, PDF page668.",
            "finding": "Primary-metal incidence alone cannot select the UK heading: note16(d) also requires at least95% qualifying UK metal. The aluminum component applies25% solely from UK origin; the generated steel component always applies50%. The real requests cannot carry the missing qualification fact.",
            "required_next_step": "Add source-grounded note16(d) qualification through the authorized encoder/entry-fact workflow, then correct heading selection and replay before admission. Do not globally toggle incidence flags or claim origin establishes metal provenance.",
        },
        "limitations": [
            "All classifications, origins and metal-provenance percentages are stipulated, not actual entry evidence. No other heading-specific exception or Chapter98 claim is asserted.",
            "Primary chapter72/76 cases do not require the15% metal-weight test for non-metal chapters; derivative, zero-metal, Russian and other preference cases are outside this batch.",
            "The witness has no steel component slot; only its supported aluminum component is queried. Steel uses actual generated ch72.",
            "The prior steel114 receipt proves bounded input comparability, not full legal rightness. Its bytes, cases, source bindings and scope remain preserved unchanged.",
            "All58actual-entry groundings, final Fable review and current-base admission gates remain open.",
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
            sources.require(OUTPUT.read_bytes() == body, "metal evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("metal evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
