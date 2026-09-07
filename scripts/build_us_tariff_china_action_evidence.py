#!/usr/bin/env python3
"""Retain real note-31 adapter counterexamples against authenticated source rows."""

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

DIRECTORY = ROOT / "reference/us-tariff-schedule/boundary-evidence/china-action-sources"
OUTPUT = DIRECTORY.parent / "china-action.json"
ACTION_SHA = "e83f46c0039b8e647eb9197b48aac363b272f36d6775940389a767d8f2841917"
ACTION_URL = "https://www.govinfo.gov/content/pkg/FR-2024-09-18/pdf/2024-21217.pdf"
WITNESS = runtime.original.closure.WITNESS_MODULE
MODULES = (
    WITNESS,
    "us/policies/cbp/us-tariff-schedule/generated/ch76/ch76.yaml",
    "us/policies/cbp/us-tariff-schedule/generated/ch85/ch85.yaml",
)
INPUTS = ("entry_is_china_301_2024_action", "entry_is_china_301_solar")
CHINA_FLAGS = (
    "entry_is_china_301_list123",
    INPUTS[0],
    "entry_is_china_301_list4a",
    "entry_is_line_d",
    INPUTS[1],
)
OUTPUTS = ("china_section_301_component_rate",)
# Source judgment is independent of the adapter: note31(b) contains 7601.10.30;
# note31(c) contains 8541.42.00. Their distinct headings impose 25% and 50%.
LINES = (
    ("7601.10.30.00", 7601103000, 76, INPUTS[0], "0.25"),
    ("8541.42.00.10", 8541420000, 85, INPUTS[1], "0.5"),
)
PAGES = (509, 510, 511, 512, 513, 514, 685, 686)


def capture(downloads):
    sources.require(not DIRECTORY.exists(), "refuse to replace existing source capture")
    DIRECTORY.mkdir(parents=True)
    for suffix in (".pdf", ".headers", ".curl.json"):
        p = downloads / ("china-2024-action" + suffix)
        (DIRECTORY / p.name).write_bytes(sources.public_http_metadata(p))
    timestamp = datetime.fromtimestamp(
        (downloads / "china-2024-action.pdf").stat().st_mtime, timezone.utc
    ).isoformat()
    (DIRECTORY / "retrieval-time.json").write_bytes(
        sources.render({"retrieved_at": timestamp})
    )


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
        record = json.loads(raw)
        if record["citation_path"] in {
            f"us/statute/hts/chapter-99/page-{n}" for n in PAGES
        }:
            records.append(
                {
                    "jsonl_line": number,
                    "raw_record_sha256": sources.sha(raw),
                    "record": record,
                }
            )
    sources.require(len(records) == len(PAGES), "note31 page population changed")
    pdf = DIRECTORY / "china-2024-action.pdf"
    sources.require(
        sources.sha(pdf.read_bytes()) == ACTION_SHA, "China action PDF mismatch"
    )
    metadata = json.loads((DIRECTORY / "china-2024-action.curl.json").read_bytes())
    sources.require(
        metadata["http_code"] == 200
        and metadata["ssl_verify_result"] == 0
        and metadata["url_effective"] == ACTION_URL,
        "China action HTTPS metadata mismatch",
    )
    pages = []
    for n in (21, 24):
        proc = subprocess.run(
            ["pdftotext", "-f", str(n), "-l", str(n), "-layout", str(pdf), "-"],
            check=True,
            capture_output=True,
        )
        # Poppler reports known malformed ligature names in this official PDF;
        # preserve warnings and visually check the primary page instead of silently repairing text.
        pages.append(
            {
                "pdf_page": n,
                "printed_page": 76580 + n,
                "extracted_text": proc.stdout.decode(),
                "extraction_warnings": proc.stderr.decode(),
                "visually_checked": True,
            }
        )
    return {
        "chapter99_live_receipt_sha256": sources.sha(sources.RECEIPT.read_bytes()),
        "chapter99_records": records,
        "chapter99_visually_checked_pdf_pages": [513, 685, 686],
        "action": {
            "url": ACTION_URL,
            "retrieved_at": json.loads(
                (DIRECTORY / "retrieval-time.json").read_bytes()
            )["retrieved_at"],
            "pdf": sources.bound(pdf),
            "headers": sources.bound(DIRECTORY / "china-2024-action.headers"),
            "retrieval_metadata": sources.bound(
                DIRECTORY / "china-2024-action.curl.json"
            ),
            "pages": pages,
            "new_ingest_signed": False,
        },
    }


def fixtures():
    rows = []
    for (hts, key, chapter, flag, rate), country, day in itertools.product(
        LINES, ("CN", "HK", "FR"), ("2026-02-16", "2026-08-03")
    ):
        rows.append(
            {
                "case_id": f"n31-{key}-{country}-{day}",
                "hts_number": hts,
                "rate_line": key,
                "chapter": chapter,
                "day": day,
                "country_of_origin": country,
                "source_membership": {name: name == flag for name in INPUTS},
                "expected_component_rate": rate if country == "CN" else "0",
                "assumptions": [
                    "No Chapter 98 claim or other transaction-specific exemption.",
                    "Classification is stipulated to the printed subheading; actual-entry grounding remains uncaptured.",
                ],
            }
        )
    return rows


def build():
    source = source_evidence()
    rows = fixtures()
    runs, adapter_rows, mismatches = [], [], []
    with runtime.compiled(MODULES) as execute:
        for row in rows:
            actual = execute.entry_flags(
                row["rate_line"],
                row["hts_number"],
                row["country_of_origin"],
                entry_date=row["day"],
            )
            flags = {name: actual[name] for name in CHINA_FLAGS}
            adapter_rows.append(
                {
                    "case_id": row["case_id"],
                    "actual_china_flags": flags,
                    "source_membership": row["source_membership"],
                    "membership_matches_source": all(
                        flags[k] == v for k, v in row["source_membership"].items()
                    ),
                }
            )
        adapter_by_id = {row["case_id"]: row for row in adapter_rows}
        for module in MODULES:
            relevant = (
                rows
                if module == WITNESS
                else [row for row in rows if f"/ch{row['chapter']}/" in module]
            )
            modes = (
                ("direct_witness",)
                if module == WITNESS
                else ("actual_adapter", "declared_source_membership")
            )
            for mode in modes:
                cases = []
                for row in relevant:
                    facts = {"country_of_origin": row["country_of_origin"]}
                    if mode == "direct_witness":
                        facts["hts_number"] = row["hts_number"]
                    else:
                        facts["hts_line"] = row["rate_line"]
                        facts.update(
                            adapter_by_id[row["case_id"]]["actual_china_flags"]
                            if mode == "actual_adapter"
                            else {
                                name: row["source_membership"].get(name, False)
                                for name in CHINA_FLAGS
                            }
                        )
                    cases.append({**row, "facts": facts})
                run = execute(module, cases, OUTPUTS)
                run["input_mode"] = mode
                for actual, row in zip(run["results"], relevant, strict=True):
                    observed = actual["actual"][OUTPUTS[0]]
                    actual.update(
                        expected_from_source=row["expected_component_rate"],
                        source_match=observed == row["expected_component_rate"],
                    )
                    if not actual["source_match"]:
                        sources.require(
                            mode == "actual_adapter"
                            and row["country_of_origin"] == "CN"
                            and observed == "0",
                            "unexpected China action runtime mismatch",
                        )
                        mismatches.append(
                            {
                                "module": module,
                                "case_id": row["case_id"],
                                "mode": mode,
                                "expected": row["expected_component_rate"],
                                "actual": observed,
                            }
                        )
                runs.append(run)
        adapter_binding = execute.adapter_binding
    sources.require(
        len(mismatches) == 4, "China action counterexample population changed"
    )
    sources.require(
        all(not row["membership_matches_source"] for row in adapter_rows),
        "pinned adapter no longer omits all tested note31 memberships",
    )
    return {
        "schema": "axiom_oracles.us_tariff_schedule.china_action_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "sources": source,
        "adapter": adapter_binding,
        "fixtures": rows,
        "adapter_results": adapter_rows,
        "runs": runs,
        "known_mismatches": mismatches,
        "scopes": [
            {
                "input": name,
                "source_evidence": "captured_live_primary_source",
                "status": "blocked_on_missing_adapter_note31_membership",
                "grounding": "uncaptured",
            }
            for name in INPUTS
        ],
        "validation": {
            "real_runtime_cases": 36,
            "real_runtime_outputs": 36,
            "adapter_cases": 12,
            "matching_cases": 32,
            "known_mismatching_cases": 4,
            "all_cases_match": False,
            "new_campaign_rows_scanned": 0,
        },
        "blocker": {
            "files": [
                {
                    "path": "tools/b16_entry_flags.py",
                    "lines": [385, 386],
                    "finding": "The pinned adapter returns false for both note31 inputs, including these primary-source positive classifications.",
                }
            ],
            "effect": "The real generated ch76/ch85 runtime returns zero with actual adapter facts, while the direct witness and independently declared source-membership inputs return the source rates for China. Hong Kong and France controls remain zero.",
            "required_next_step": "Supply complete source-grounded note31 membership through the authorized encoding/adapter workflow and verify exclusions and precedence. Do not turn on these flags globally, repin frozen proofs, or claim this bounded receipt proves all note31 classifications.",
        },
        "limitations": [
            "The source snapshot is Rev15, not a complete historical-vintage panel. The two sampled dates are after the original 2024 action activation.",
            "Only two source-positive classifications and two origin controls are replayed. Solar table membership includes a second subheading not exercised here.",
            "The declared-membership path is a counterfactual test input to the real engine, not a repaired production adapter.",
            "The canonical 2024_action scope refers broadly to note31, but this Boolean component supplies the 25% heading9903.91.01 rate. Other note31 heading/rate families require separate coverage and must not be collapsed to this flag.",
            "All transaction groundings, final Fable review and release/admission gates remain open. No RuleSpec or adapter code changed.",
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
            sources.require(OUTPUT.read_bytes() == body, "China action evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("China action evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
