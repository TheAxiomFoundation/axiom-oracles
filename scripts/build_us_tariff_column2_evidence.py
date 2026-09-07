#!/usr/bin/env python3
"""Keep non-flat Column2 resolution external and preserve native missing-input errors."""

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
from scripts import us_tariff_raw_runtime as native  # noqa: E402
from scripts import us_tariff_live_source_evidence as sources  # noqa: E402

DIRECTORY = ROOT / "reference/us-tariff-schedule/boundary-evidence/column2-sources"
OUTPUT = DIRECTORY.parent / "column2-resolution.json"
GN3_SHA = "a2cf79ac77e973d0c13129faae26b40cf4791b302f3a9f0ff6a578b37626685f"
GN3_URL = "https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=General%20Note%203"
INPUT = "resolved_non_ad_valorem_column2_rate"
OUT = "mfn_ad_valorem_rate"
MODULES = tuple(
    f"us/policies/cbp/us-tariff-schedule/generated/ch{n}/ch{n}.yaml"
    for n in ("99a", "99b")
)
LINES = (
    (MODULES[0], 9901005000, "specific", 4, "before 2012-01-01"),
    (MODULES[0], 9902010100, "conditional", 7, "on or before 2020-12-31"),
    (MODULES[1], 9902094300, "conditional", 74, "on or before 2020-12-31"),
)
DAY = "2026-08-03"


def capture(downloads):
    sources.require(not DIRECTORY.exists(), "refuse to replace Column2 source capture")
    DIRECTORY.mkdir(parents=True)
    for suffix in (".pdf", ".headers", ".curl.json"):
        p = downloads / ("general-note3" + suffix)
        (DIRECTORY / p.name).write_bytes(sources.public_http_metadata(p))
    stamp = datetime.fromtimestamp(
        (downloads / "general-note3.pdf").stat().st_mtime, timezone.utc
    ).isoformat()
    (DIRECTORY / "retrieval-time.json").write_bytes(
        sources.render({"retrieved_at": stamp})
    )


def source_evidence():
    live = sources.build(sources.DIRECTORY, sources.boundary.closure.CORPUS)
    sources.require(
        sources.RECEIPT.read_bytes() == sources.render(live),
        "live source receipt drift",
    )
    pdf = DIRECTORY / "general-note3.pdf"
    meta = DIRECTORY / "general-note3.curl.json"
    sources.require(sources.sha(pdf.read_bytes()) == GN3_SHA, "GN3 PDF mismatch")
    metadata = json.loads(meta.read_bytes())
    sources.require(
        metadata["http_code"] == 200
        and metadata["ssl_verify_result"] == 0
        and metadata["url_effective"] == GN3_URL,
        "GN3 HTTPS metadata mismatch",
    )
    proc = subprocess.run(
        ["pdftotext", "-f", "4", "-l", "4", "-layout", str(pdf), "-"],
        check=True,
        capture_output=True,
    )
    records = []
    for number, raw in enumerate(
        (sources.DIRECTORY / "provisions.jsonl").read_bytes().splitlines(), 1
    ):
        row = json.loads(raw)
        if row["citation_path"] in {
            f"us/statute/hts/chapter-99/page-{n}" for n in (4, 7, 74)
        }:
            records.append(
                {
                    "jsonl_line": number,
                    "raw_record_sha256": sources.sha(raw),
                    "record": row,
                }
            )
    sources.require(len(records) == 3, "Column2 page population changed")
    return {
        "chapter99_live_receipt_sha256": sources.sha(sources.RECEIPT.read_bytes()),
        "chapter99_records": records,
        "visually_checked_chapter99_pages": [4, 7, 74],
        "general_note3": {
            "url": GN3_URL,
            "pdf": sources.bound(pdf),
            "headers": sources.bound(DIRECTORY / "general-note3.headers"),
            "retrieval_metadata": sources.bound(meta),
            "retrieved_at": json.loads(
                (DIRECTORY / "retrieval-time.json").read_bytes()
            )["retrieved_at"],
            "pdf_page": 4,
            "extracted_text": proc.stdout.decode(),
            "visually_checked": True,
            "new_ingest_signed": False,
        },
    }


def fixtures():
    rows = []
    for (
        module,
        key,
        disposition,
        page,
        expiry,
    ), country, resolved in itertools.product(
        LINES, ("CU", "KP", "BY", "RU"), (None, 0.0125, 0.25)
    ):
        case = f"column2-{key}-{country}-" + (
            "missing" if resolved is None else str(resolved)
        )
        facts = {"hts_line": key, "country_of_origin": country}
        if resolved is not None:
            facts[INPUT] = resolved
        rows.append(
            {
                "case_id": case,
                "day": DAY,
                "module": module,
                "facts": facts,
                "expected_kind": "missing_input"
                if resolved is None
                else "stipulated_passthrough",
                "expected": None if resolved is None else str(resolved),
                "outputs": [OUT],
                "source_disposition": disposition,
                "source_pdf_page": page,
                "source_effective_period": expiry,
                "valid_2026_entry_claim": False,
            }
        )
    for module, key, disposition, page, expiry in LINES:
        rows.append(
            {
                "case_id": f"disposition-{key}",
                "day": DAY,
                "module": module,
                "facts": {"hts_line": key},
                "expected_kind": "source_disposition",
                "expected": disposition,
                "outputs": ["schedule_column2_disposition"],
                "source_effective_period": expiry,
                "valid_2026_entry_claim": False,
            }
        )
        if disposition == "conditional":
            rows.append(
                {
                    "case_id": f"general-control-{key}",
                    "day": DAY,
                    "module": module,
                    "facts": {"hts_line": key, "country_of_origin": "FR"},
                    "expected_kind": "diagnostic_general_control",
                    "expected": "0",
                    "outputs": [OUT],
                    "source_effective_period": expiry,
                    "valid_2026_entry_claim": False,
                }
            )
    return rows


def build():
    source = source_evidence()
    rows = fixtures()
    runs = []
    rejections = outputs = 0
    with native.compiled(MODULES) as execute:
        for row in rows:
            request = runtime.request(row["module"], [row], tuple(row["outputs"]))
            run = execute(row["module"], request)
            if row["expected_kind"] == "missing_input":
                sources.require(
                    run["returncode"] == 1
                    and run["response"] is None
                    and run["stdout"] == ""
                    and f"missing input `{INPUT}`" in run["stderr"],
                    "missing resolution was not rejected by real engine",
                )
                run["checked"] = {
                    "kind": "native_missing_input_rejection",
                    "matches_contract": True,
                }
                rejections += 1
            else:
                sources.require(
                    run["returncode"] == 0 and run["response"] is not None,
                    "unexpected native runtime failure",
                )
                raw = run["response"]["results"]
                sources.require(
                    len(raw) == 1 and raw[0]["entity_id"] == row["case_id"],
                    "native response identity changed",
                )
                values = raw[0]["outputs"]
                sources.require(len(values) == 1, "native output count changed")
                value = runtime.output(next(iter(values.values())))
                sources.require(
                    value == row["expected"], "native contract/disposition mismatch"
                )
                run["checked"] = {
                    "kind": row["expected_kind"],
                    "actual": value,
                    "matches_contract": True,
                }
                outputs += 1
            run["case_id"] = row["case_id"]
            runs.append(run)
    sources.require(
        (len(rows), outputs, rejections) == (41, 29, 12), "Column2 population changed"
    )
    return {
        "schema": "axiom_oracles.us_tariff_schedule.column2_resolution_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "native_runtime_helper_sha256": sources.sha(Path(native.__file__).read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "sources": source,
        "fixtures": rows,
        "native_runs": runs,
        "scopes": [
            {
                "input": INPUT,
                "source_evidence": "captured_live_primary_source",
                "status": "blocked_on_external_non_ad_valorem_resolution_and_vintage_admission",
                "grounding": "uncaptured",
            }
        ],
        "validation": {
            "real_runtime_cases": 41,
            "real_runtime_outputs": 29,
            "native_missing_input_rejections": 12,
            "all_contract_checks_match": True,
            "legal_resolved_rates_validated": 0,
            "new_campaign_rows_scanned": 0,
        },
        "blocker": {
            "missing_inputs": [
                "Valid entry classification and source-effective vintage admission before querying an archival chapter99 row.",
                "Underlying applicable Chapter1-97 duty for a No change Column2 provision.",
                "Source quantities, units, customs value and applicable specific/compound/conditional duty calculation with provenance.",
                "An authorized real resolver receipt bound to those facts; arbitrary supplied Rate values do not supply it.",
            ],
            "required_next_step": "Stop this scope at interface evidence. Obtain the entry-resolution receipt and vintage admission or an authorized encoder implementation, then replay. Never infer a flat rate from the source disposition or default a missing resolution to zero.",
        },
        "limitations": [
            "The source rows shown here explicitly expired before 2012 or at the end of2020. The August3,2026 calls are diagnostic interface probes only, never valid current-entry duty calculations.",
            "The two positive supplied Rate values are diagnostic sentinels, not legal rates or manually computed ad-valorem equivalents. The real engine passes them through and does not independently resolve or certify them.",
            "All four GeneralNote3(b) origins reject a missing resolution; two non-Column2 controls do not require the unused branch input.",
            "The actual engine error is preserved including return code and stderr. Source dispositions remain specific/conditional; no generated flat Column2 table is invented.",
            "All58actual-entry groundings, final Fable review and current-base release/admission gates remain open.",
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
            sources.require(OUTPUT.read_bytes() == body, "Column2 evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("Column2 evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
