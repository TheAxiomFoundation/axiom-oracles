#!/usr/bin/env python3
"""Source-bound section122 activation and post-expiry section201 replay."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import us_tariff_continuation_runtime as runtime  # noqa: E402
from scripts import us_tariff_live_source_evidence as sources  # noqa: E402

DIRECTORY = ROOT / "reference/us-tariff-schedule/boundary-evidence/temporal-sources"
OUTPUT = DIRECTORY.parent / "temporal-boundaries.json"
DOCUMENTS = {
    "surcharge-2026": (
        "https://www.govinfo.gov/content/pkg/FR-2026-02-25/pdf/2026-03824.pdf",
        "1ad226167d7f1b92feac3a2b1adc54bb332093f46e37c248eb714d9340b63cb9",
        (3, 5),
        9338,
    ),
    "solar-safeguard-2022": (
        "https://www.govinfo.gov/content/pkg/FR-2022-02-09/pdf/2022-02906.pdf",
        "fe4d4a4ea60e2affd41714b78cd9c400fdb3aff8d4ebd446044de9db14bccce8",
        (5,),
        7356,
    ),
}
WITNESS = runtime.original.closure.WITNESS_MODULE
CH95 = "us/policies/cbp/us-tariff-schedule/generated/ch95/ch95.yaml"
CH85 = "us/policies/cbp/us-tariff-schedule/generated/ch85/ch85.yaml"
MODULES = (WITNESS, CH95, CH85)
INPUTS = ("entry_is_section_122_exempt", "entry_is_section_201_cspv")
SURCHARGE = "section_122_component_rate"
SAFEGUARD = "section_201_component_rate"
DAYS = ("2026-02-23", "2026-02-24", "2026-07-23", "2026-07-24", "2026-08-03")
SOLAR_DAYS = ("2026-02-15", "2026-02-16", "2026-02-24", "2026-07-24", "2026-08-03")
START = datetime.fromisoformat("2026-02-24T00:01:00-05:00")


def capture(downloads):
    sources.require(not DIRECTORY.exists(), "refuse to replace temporal capture")
    DIRECTORY.mkdir(parents=True)
    times = {}
    for stem in DOCUMENTS:
        for suffix in (".pdf", ".headers", ".curl.json"):
            p = downloads / (stem + suffix)
            (DIRECTORY / p.name).write_bytes(sources.public_http_metadata(p))
        times[stem] = datetime.fromtimestamp(
            (downloads / (stem + ".pdf")).stat().st_mtime, timezone.utc
        ).isoformat()
    (DIRECTORY / "retrieval-times.json").write_bytes(sources.render(times))


def source_evidence():
    live = sources.build(sources.DIRECTORY, sources.boundary.closure.CORPUS)
    sources.require(
        sources.RECEIPT.read_bytes() == sources.render(live),
        "live source receipt drift",
    )
    times = json.loads((DIRECTORY / "retrieval-times.json").read_bytes())
    documents = []
    for stem, (url, digest, pages, offset) in DOCUMENTS.items():
        pdf = DIRECTORY / (stem + ".pdf")
        sources.require(
            sources.sha(pdf.read_bytes()) == digest, "temporal source PDF mismatch"
        )
        meta = DIRECTORY / (stem + ".curl.json")
        metadata = json.loads(meta.read_bytes())
        sources.require(
            metadata["http_code"] == 200
            and metadata["ssl_verify_result"] == 0
            and metadata["url_effective"] == url,
            "temporal HTTPS metadata mismatch",
        )
        extracted = []
        for n in pages:
            proc = subprocess.run(
                ["pdftotext", "-f", str(n), "-l", str(n), "-layout", str(pdf), "-"],
                check=True,
                capture_output=True,
            )
            extracted.append(
                {
                    "pdf_page": n,
                    "printed_page": offset + n,
                    "text": proc.stdout.decode(),
                    "warnings": proc.stderr.decode(),
                    "visually_checked": True,
                }
            )
        documents.append(
            {
                "url": url,
                "retrieved_at": times[stem],
                "pdf": sources.bound(pdf),
                "headers": sources.bound(DIRECTORY / (stem + ".headers")),
                "retrieval_metadata": sources.bound(meta),
                "pages": extracted,
                "new_ingest_signed": False,
            }
        )
    pages = (*range(221, 233), *range(246, 250), 633, 661)
    records = []
    for number, raw in enumerate(
        (sources.DIRECTORY / "provisions.jsonl").read_bytes().splitlines(), 1
    ):
        record = json.loads(raw)
        if record["citation_path"] in {
            f"us/statute/hts/chapter-99/page-{n}" for n in pages
        }:
            records.append(
                {
                    "jsonl_line": number,
                    "raw_record_sha256": sources.sha(raw),
                    "record": record,
                }
            )
    sources.require(
        len(records) == len(pages), "temporal source record population changed"
    )
    return {
        "chapter99_live_receipt_sha256": sources.sha(sources.RECEIPT.read_bytes()),
        "chapter99_records": records,
        "chapter99_visually_checked_pdf_pages": [221, 661],
        "direct_sources": documents,
    }


def surcharge_fixtures():
    rows = []
    for exempt, day in itertools.product((False, True), DAYS):
        rows.append(
            {
                "case_id": f"s122-{int(exempt)}-{day}",
                "day": day,
                "timestamp_eastern": day
                + "T12:00:00"
                + ("-05:00" if day.startswith("2026-02") else "-04:00"),
                "kind": "noon_control",
                "facts": {INPUTS[0]: exempt, "entry_is_section_232_covered": False},
                "expected": "0.1"
                if "2026-02-24" <= day <= "2026-07-23" and not exempt
                else "0",
            }
        )
    for second in ("00:00:00", "00:00:59", "00:01:00"):
        stamp = "2026-02-24T" + second + "-05:00"
        rows.append(
            {
                "case_id": "s122-start-" + second.replace(":", ""),
                "day": stamp[:10],
                "timestamp_eastern": stamp,
                "kind": "activation_precision_probe",
                "facts": {INPUTS[0]: False, "entry_is_section_232_covered": False},
                "expected": "0.1" if datetime.fromisoformat(stamp) >= START else "0",
            }
        )
    return rows


def build():
    source = source_evidence()
    runs, adapter_rows, mismatches = [], [], []
    rows = surcharge_fixtures()

    def check(run, fixtures, output):
        for actual, row in zip(run["results"], fixtures, strict=True):
            observed = actual["actual"][output]
            actual.update(
                expected_from_source=row["expected"],
                source_match=observed == row["expected"],
            )
            if not actual["source_match"]:
                sources.require(
                    row.get("kind") == "activation_precision_probe"
                    and datetime.fromisoformat(row["timestamp_eastern"]) < START
                    and observed == "0.1",
                    "unexpected temporal runtime mismatch",
                )
                mismatches.append(
                    {
                        "module": run["module"]["path"],
                        "case_id": row["case_id"],
                        "timestamp_eastern": row["timestamp_eastern"],
                        "expected": row["expected"],
                        "actual": observed,
                    }
                )
        runs.append(run)

    with runtime.compiled(MODULES) as execute:
        run = execute(CH95, rows, (SURCHARGE,))
        run["scope"] = INPUTS[0]
        run["fixture_basis"] = (
            "Full exemption determination stipulated, section232-covered false; this is the input contract, not adapter-derived transaction qualification."
        )
        check(run, rows, SURCHARGE)
        witness_rows = []
        for hts, day in itertools.product(("7202.11.10.00", "9506.62.40.40"), DAYS):
            exempt = hts.startswith("7202")
            witness_rows.append(
                {
                    "case_id": f"s122-witness-{hts}-{day}",
                    "day": day,
                    "facts": {"hts_number": hts},
                    "expected": "0.1"
                    if "2026-02-24" <= day <= "2026-07-23" and not exempt
                    else "0",
                }
            )
        run = execute(WITNESS, witness_rows, (SURCHARGE,))
        run["scope"] = INPUTS[0]
        run["fixture_basis"] = (
            "One note2(aa)(ii) listed exclusion and one stipulated nonexempt line; noon only."
        )
        check(run, witness_rows, SURCHARGE)
        solar_rows = []
        for hts, day in itertools.product(
            ("8541.42.00.10", "9506.62.40.40"), SOLAR_DAYS
        ):
            key = 8541420000 if hts.startswith("8541") else 9506624040
            flags = execute.entry_flags(key, hts, "FR", entry_date=day)
            member = flags[INPUTS[1]]
            sources.require(
                member == hts.startswith("8541"),
                "bounded CSPV adapter identity mismatch",
            )
            case = f"s201-{key}-{day}"
            adapter_rows.append(
                {
                    "case_id": case,
                    "hts_number": hts,
                    "day": day,
                    "actual_cspv_membership": member,
                    "duty_is_active": False,
                }
            )
            solar_rows.append(
                {
                    "case_id": case,
                    "day": day,
                    "hts_number": hts,
                    "membership": member,
                    "expected": "0",
                }
            )
        witness = [
            {**row, "facts": {"hts_number": row["hts_number"]}} for row in solar_rows
        ]
        run = execute(WITNESS, witness, (SAFEGUARD,))
        run["scope"] = INPUTS[1]
        run["fixture_basis"] = (
            "Actual post-expiry witness; no active safeguard period queried."
        )
        check(run, witness, SAFEGUARD)
        for module, positive in ((CH85, True), (CH95, False)):
            fixtures = [
                {**row, "facts": {INPUTS[1]: row["membership"]}}
                for row in solar_rows
                if row["membership"] is positive
            ]
            run = execute(module, fixtures, (SAFEGUARD,))
            run["scope"] = INPUTS[1]
            run["fixture_basis"] = (
                "Actual adapter membership supplied to real generated runtime after safeguard expiry."
            )
            check(run, fixtures, SAFEGUARD)
        adapter_binding = execute.adapter_binding
    sources.require(
        len(mismatches) == 2 and sum(len(run["results"]) for run in runs) == 43,
        "temporal replay population changed",
    )
    return {
        "schema": "axiom_oracles.us_tariff_schedule.temporal_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "sources": source,
        "adapter": adapter_binding,
        "surcharge_fixtures": rows,
        "adapter_results": adapter_rows,
        "runs": runs,
        "known_mismatches": mismatches,
        "scopes": [
            {
                "input": INPUTS[0],
                "status": "blocked_at_subminute_activation",
                "source_evidence": "captured_live_primary_source",
                "grounding": "uncaptured",
            },
            {
                "input": INPUTS[1],
                "status": "bounded_postexpiry_replay_only",
                "source_evidence": "captured_live_primary_source",
                "grounding": "uncaptured",
            },
        ],
        "validation": {
            "real_runtime_cases": 43,
            "real_runtime_outputs": 43,
            "adapter_cases": 10,
            "matching_cases": 41,
            "known_mismatching_cases": 2,
            "all_cases_match": False,
            "new_campaign_rows_scanned": 0,
        },
        "limitations": [
            "Section122 exemption is a complete external legal determination. Boolean replay does not derive baggage, Chapter98, GN6, USMCA, CAFTA, transit or product-specific qualification.",
            "The real Day runtime activates section122 at midnight instead of the proclamations 00:01 Eastern boundary. The two first-minute counterexamples block admission pending a timestamp contract and authorized encoder repair.",
            "The proclamation says through 00:01 Eastern July24 whereas the Rev15 compiler note says close of July23. Noon expiration controls agree under either reading; precise end-boundary interpretation is not adjudicated here.",
            "Section201 is tested only after February6,2026 expiry, starting at the compositions February15 lower bound. No active-period rate, quota, exception, or full CSPV classification validation is claimed.",
            "The 2022 proclamation quota level is historical; the Rev15 expired heading records12.5GW. This batch does not infer quota application from the older5GW level.",
            "All current-base admission, actual-entry grounding, final Fable review and release gates remain open.",
        ],
        "claim": {"closed": False, "certified": False, "release_authorized": False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-from", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.capture_from:
            capture(args.capture_from)
        result = build()
        body = sources.render(result)
        if args.check:
            sources.require(OUTPUT.read_bytes() == body, "temporal evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("temporal evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
