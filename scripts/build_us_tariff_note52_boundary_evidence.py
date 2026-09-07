#!/usr/bin/env python3
"""Probe the transit/USMCA exceptions, retaining the sub-minute boundary blocker."""

from __future__ import annotations

import argparse
from datetime import datetime
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import us_tariff_continuation_runtime as runtime  # noqa: E402
from scripts import us_tariff_live_source_evidence as sources  # noqa: E402

OUTPUT = (
    ROOT / "reference/us-tariff-schedule/boundary-evidence/note52-transit-usmca.json"
)
MODULES = (
    runtime.original.closure.WITNESS_MODULE,
    "us/policies/cbp/us-tariff-schedule/generated/ch95/ch95.yaml",
)
INPUTS = (
    "entry_loaded_and_in_transit_before_july_24_2026",
    "entry_is_entered_free_of_duty_under_usmca",
)
OUTPUTS = (
    "forced_labor_in_transit_safe_harbor_applies",
    "forced_labor_usmca_exception_applies",
    "forced_labor_section_301_entry_component_rate",
)
RATES = {"CA": "0.1", "MX": "0.1", "AR": "0.1", "GB": "0.1", "US": "0"}
DAYS = ("2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28", "2026-08-03")
CUTOFF = datetime.fromisoformat("2026-07-28T00:01:00-04:00")
START = datetime.fromisoformat("2026-07-24T00:01:00-04:00")


def fixtures():
    rows = []

    def add(origin, transit, usmca, stamp, kind):
        active = datetime.fromisoformat(stamp) >= START
        safe = active and transit and datetime.fromisoformat(stamp) < CUTOFF
        preference = active and origin in ("CA", "MX") and usmca
        rate = RATES[origin] if active and not safe and not preference else "0"
        rows.append(
            {
                "case_id": f"n52-{origin}-{int(transit)}{int(usmca)}-{stamp[:10]}-{stamp[11:19].replace(':', '')}",
                "day": stamp[:10],
                "stipulated_entry_timestamp_eastern": stamp,
                "kind": kind,
                "facts": {
                    "country_of_origin": origin,
                    INPUTS[0]: transit,
                    INPUTS[1]: usmca,
                },
                "expected_from_source": dict(
                    zip(OUTPUTS, (safe, preference, rate), strict=True)
                ),
            }
        )

    for origin, (transit, usmca), day in itertools.product(
        RATES, itertools.product((False, True), repeat=2), DAYS
    ):
        add(origin, transit, usmca, day + "T12:00:00-04:00", "noon_control")
    for origin, time in itertools.product(RATES, ("00:00:00", "00:00:59", "00:01:00")):
        add(
            origin,
            True,
            False,
            "2026-07-28T" + time + "-04:00",
            "entry_cutoff_precision_probe",
        )
    return rows


def module_fixtures(module, rows):
    result = []
    for row in rows:
        defaults = {
            name: False
            for name, _ in runtime.original.closure.CANONICAL_INPUT_SCOPES
            if name.startswith(("entry_", "cbp_"))
        }
        defaults.update(
            customs_value=0,
            shipment_value=0,
            resolved_non_ad_valorem_column2_rate=0,
            is_postal_shipment=False,
        )
        facts = dict(row["facts"])
        if module == MODULES[0]:
            facts["hts_number"] = "9506.62.40.40"
        else:
            facts["hts_line"] = 9506624040
            defaults["entry_is_forced_labor_301_listed"] = True
        result.append({**row, "facts": facts, "defaults": defaults})
    return result


def source_records():
    records = []
    for line_no, line in enumerate(
        (sources.DIRECTORY / "provisions.jsonl").read_bytes().splitlines(), 1
    ):
        record = json.loads(line)
        if record["citation_path"] in {
            f"us/statute/hts/chapter-99/page-{n}"
            for n in (553, 566, 639, 640, 644, 647, 648)
        }:
            records.append(
                {
                    "jsonl_line": line_no,
                    "raw_record_sha256": sources.sha(line),
                    "record": record,
                }
            )
    sources.require(len(records) == 7, "note52 source record population changed")
    return records


def build():
    live = sources.build(sources.DIRECTORY, sources.boundary.closure.CORPUS)
    sources.require(
        sources.RECEIPT.read_bytes() == sources.render(live),
        "live source receipt changed",
    )
    rows = fixtures()
    runs = []
    mismatches = []
    matched = 0
    with runtime.compiled(MODULES) as execute:
        for module in MODULES:
            run = execute(module, module_fixtures(module, rows), OUTPUTS)
            for actual, row in zip(run["results"], rows, strict=True):
                differences = {
                    name: {"expected": expected, "actual": actual["actual"][name]}
                    for name, expected in row["expected_from_source"].items()
                    if expected != actual["actual"][name]
                }
                actual["source_match"] = not differences
                actual["differences"] = differences
                if differences:
                    mismatches.append(
                        {
                            "module": module,
                            "case_id": row["case_id"],
                            "entry_timestamp": row[
                                "stipulated_entry_timestamp_eastern"
                            ],
                            "differences": differences,
                        }
                    )
                    sources.require(
                        row["kind"] == "entry_cutoff_precision_probe"
                        and row["stipulated_entry_timestamp_eastern"]
                        < CUTOFF.isoformat(),
                        "unexpected source/runtime mismatch: "
                        + module
                        + " "
                        + row["case_id"]
                        + " "
                        + str(differences),
                    )
                    expected_fields = (
                        {OUTPUTS[0]}
                        if row["facts"]["country_of_origin"] == "US"
                        else {OUTPUTS[0], OUTPUTS[2]}
                    )
                    sources.require(
                        set(differences) == expected_fields,
                        "unexpected mismatch output set",
                    )
                else:
                    matched += 1
            runs.append(run)
    sources.require(
        len(mismatches) == 20 and matched == 210,
        "known precision mismatch population changed",
    )
    return {
        "schema": "axiom_oracles.us_tariff_schedule.note52_boundary_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "live_source_receipt_sha256": sources.sha(sources.RECEIPT.read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "source_records": source_records(),
        "activation_source": {
            "url": sources.ACTION_URL,
            "pdf_sha256": sources.ACTION_SHA256,
            "pdf_page": 1,
            "printed_page": 47318,
            "clause": "DATES: July24 00:01 eastern activation and July28 00:01 eastern transit cutoff; visually checked",
        },
        "general_note11": {
            "url": sources.GN11_URL,
            "pdf_sha256": sources.GN11_SHA256,
            "clause": "General note11(a)-(b), PDF page1; complete136-page original captured, actual qualification not derived",
        },
        "scopes": [
            {
                "input": name,
                "source_evidence": "captured",
                "actual_entry_grounding": "uncaptured",
                "status": "blocked_at_subminute_entry_cutoff"
                if name == INPUTS[0]
                else "bounded_stipulated_fact_replay_matches",
            }
            for name in INPUTS
        ],
        "fixtures": rows,
        "runs": runs,
        "validation": {
            "case_count": 230,
            "output_count": 690,
            "matching_cases": matched,
            "known_mismatching_cases": len(mismatches),
            "noon_cases": 200,
            "all_noon_cases_match": True,
            "all_cases_match": False,
            "new_campaign_rows_scanned": 0,
        },
        "known_mismatches": mismatches,
        "blockers": [
            {
                "scope": INPUTS[0],
                "reason": "The RuleSpec Day interval loses the 00:01 eastern entry cutoff. July28 entries at00:00:00 and00:00:59 with qualifying loading/transit satisfy heading9903.05.85, but the program returns no safe harbor and a positive component for covered origins. An entry timestamp/precision contract and supervised RuleSpec repair are required before admitting this scope.",
            }
        ],
        "limitations": [
            "The loading/transit Boolean stipulates all vessel, port, final-mode and July24 00:01 eastern conditions; carrier evidence is not supplied.",
            "USMCA free-duty treatment remains a stipulated fact subject to GeneralNote11 and CBP entry requirements, not a conclusion from origin alone.",
            "The daily control cases stipulate noon eastern entry time. The additional minute probes expose rather than hide the incompatible time granularity.",
            "The sports-ball HTS witness is a preexisting nonexempt projection; the generated composition explicitly stipulates entry_is_forced_labor_301_listed=true and other exception flags=false; this batch does not certify product membership, total duty, or every generated chapter.",
            "Original campaign proofs remain frozen; current-main publication admission and final Fable review remain open.",
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
            sources.require(OUTPUT.read_bytes() == body, "note52 evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("note52 evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
