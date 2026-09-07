#!/usr/bin/env python3
"""Bind three HTS identity flags and generated lookup keys to live primary rows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import us_tariff_continuation_runtime as runtime  # noqa: E402
from scripts import us_tariff_live_source_evidence as sources  # noqa: E402

DIRECTORY = ROOT / "reference/us-tariff-schedule/boundary-evidence/identity-sources"
OUTPUT = DIRECTORY.parent / "hts-identity.json"
DOCUMENTS = {
    72: (
        "8c8346ef492310a4b34ff540286f902c8079bcf0c5900a7e1175771614cd699a",
        12,
        "72-8",
    ),
    76: ("fcda655f4da588f193ab28f9540b27329efbd9bb7413e1cfc01fd24a6bcae0d5", 3, "76-3"),
    22: ("faf177c73bf71c0c3815f366042f50eccc3b6cfc76777e8c3d48cc4488f47eb1", 5, "22-5"),
}
FLAGS = {
    "entry_is_line_a": "7202.11.10.00",
    "entry_is_line_b": "7601.10.30.00",
    "entry_is_line_d": "2203.00.00.30",
}
# Independent transcription from the three visually checked official PDF pages.
# Statistical children inherit their explicitly identified legal rate row.
LINES = (
    ("7202.11.10.00", 7202111000, "0.014", "ad_valorem", "ad_valorem"),
    ("7202.11.50.00", 7202115000, "0.015", "ad_valorem", "ad_valorem"),
    ("7601.10.30.00", 7601103000, "0.026", "ad_valorem", "ad_valorem"),
    ("7601.10.60.40", 7601106000, "0", "free", "ad_valorem"),
    ("2203.00.00.30", 2203000000, "0", "free", "specific"),
    ("2203.00.00.60", 2203000000, "0", "free", "specific"),
    ("2203.00.00.90", 2203000000, "0", "free", "specific"),
)
WITNESS = runtime.original.closure.WITNESS_MODULE
MODULES = (WITNESS,) + tuple(
    f"us/policies/cbp/us-tariff-schedule/generated/ch{n}/ch{n}.yaml" for n in DOCUMENTS
)
TABLE_OUTPUTS = (
    "schedule_base_general_rate",
    "schedule_general_disposition",
    "schedule_column2_disposition",
)
DAY = "2026-08-03"


def capture(downloads):
    sources.require(
        not DIRECTORY.exists(), "refuse to replace existing identity capture"
    )
    DIRECTORY.mkdir(parents=True)
    times = {}
    for chapter in DOCUMENTS:
        stem = f"chapter{chapter}"
        for suffix in (".pdf", ".headers", ".curl.json"):
            p = downloads / (stem + suffix)
            (DIRECTORY / p.name).write_bytes(sources.public_http_metadata(p))
        times[stem] = datetime.fromtimestamp(
            (downloads / (stem + ".pdf")).stat().st_mtime, timezone.utc
        ).isoformat()
    (DIRECTORY / "retrieval-times.json").write_bytes(sources.render(times))


def source_rows():
    result = []
    times = json.loads((DIRECTORY / "retrieval-times.json").read_bytes())
    for chapter, (expected, page, printed) in DOCUMENTS.items():
        stem = f"chapter{chapter}"
        pdf = DIRECTORY / (stem + ".pdf")
        body = pdf.read_bytes()
        sources.require(
            sources.sha(body) == expected and body.startswith(b"%PDF-"),
            "identity primary PDF mismatch",
        )
        metadata = json.loads((DIRECTORY / (stem + ".curl.json")).read_bytes())
        url = f"https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%20{chapter}"
        sources.require(
            metadata["url_effective"] == url
            and metadata["http_code"] == 200
            and metadata["ssl_verify_result"] == 0,
            "identity HTTPS metadata mismatch",
        )
        text = subprocess.check_output(
            ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"]
        ).decode()
        result.append(
            {
                "url": url,
                "retrieved_at": times[stem],
                "http_status": 200,
                "pdf": sources.bound(pdf),
                "pdf_page": page,
                "printed_page": printed,
                "headers": sources.bound(DIRECTORY / (stem + ".headers")),
                "retrieval_metadata": sources.bound(DIRECTORY / (stem + ".curl.json")),
                "extracted_page_text": text,
                "extracted_page_sha256": sources.sha(text.encode()),
                "visually_checked": True,
            }
        )
    return result


def identity_fixtures():
    rows = []
    for canonical, line, *_ in LINES:
        variants = {
            "canonical": canonical,
            "digits": canonical.replace(".", ""),
            "spaces": canonical.replace(".", " "),
            "hyphens": canonical.replace(".", "-"),
        }
        for variant, raw in variants.items():
            rows.append(
                {
                    "case_id": f"identity-{line}-{canonical[-2:]}-{variant}",
                    "day": DAY,
                    "canonical_hts": canonical,
                    "raw_hts": raw,
                    "format": variant,
                    "rate_line": line,
                    "expected_flags": {
                        flag: canonical == code for flag, code in FLAGS.items()
                    },
                }
            )
    return rows


def build():
    records = source_rows()
    rows = identity_fixtures()
    runs = []
    adapter_rows = []
    differences = []
    table_cases = 0
    with runtime.compiled(MODULES) as execute:
        for row in rows:
            flags = execute.entry_flags(
                row["rate_line"], row["raw_hts"], "FR", entry_date=DAY
            )
            selected = {name: flags[name] for name in FLAGS}
            sources.require(
                selected == row["expected_flags"],
                "pinned Axiom adapter identity mismatch",
            )
            adapter_rows.append(
                {
                    "case_id": row["case_id"],
                    "actual_flags": selected,
                    "matches_source_identity": True,
                }
            )
        for form in ("raw", "canonical"):
            fixtures = [
                {
                    **row,
                    "facts": {
                        "hts_number": row["raw_hts"]
                        if form == "raw"
                        else row["canonical_hts"]
                    },
                }
                for row in rows
            ]
            run = execute(WITNESS, fixtures, tuple(FLAGS))
            run["input_form"] = form
            for actual, row in zip(run["results"], rows, strict=True):
                mismatch = {
                    k: {"adapter": row["expected_flags"][k], "direct_witness": v}
                    for k, v in actual["actual"].items()
                    if v != row["expected_flags"][k]
                }
                actual["matches_adapter"] = not mismatch
                if mismatch:
                    sources.require(
                        form == "raw" and row["format"] != "canonical",
                        "canonical input identity must match",
                    )
                    differences.append(
                        {
                            "case_id": row["case_id"],
                            "raw_hts": row["raw_hts"],
                            "canonical_hts": row["canonical_hts"],
                            "differences": mismatch,
                        }
                    )
            runs.append(run)
        for module, chapter in zip(MODULES[1:], DOCUMENTS, strict=True):
            fixtures = []
            for canonical, line, rate, general, column2 in LINES:
                if int(canonical[:2]) != chapter:
                    continue
                fixtures.append(
                    {
                        "case_id": f"lookup-{canonical}",
                        "day": DAY,
                        "facts": {"hts_line": line},
                        "expected": dict(
                            zip(TABLE_OUTPUTS, (rate, general, column2), strict=True)
                        ),
                    }
                )
            run = execute(module, fixtures, TABLE_OUTPUTS)
            for actual, row in zip(run["results"], fixtures, strict=True):
                sources.require(
                    actual["actual"] == row["expected"],
                    "source-linked rate-row lookup mismatch: "
                    + row["case_id"]
                    + " "
                    + str(actual),
                )
                actual.update(expected=row["expected"], matches_source=True)
            table_cases += len(fixtures)
            runs.append(run)
        adapter_binding = execute.adapter_binding
    sources.require(
        len(differences) == 9 and table_cases == 7,
        "identity boundary population changed",
    )
    return {
        "schema": "axiom_oracles.us_tariff_schedule.hts_identity_evidence.v1",
        "producer_sha256": sources.sha(Path(__file__).read_bytes()),
        "runtime_helper_sha256": sources.sha(Path(runtime.__file__).read_bytes()),
        "rulespec_ref": runtime.original.closure.RULESPEC_REF,
        "engine_sha256": runtime.original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "sources": records,
        "adapter": adapter_binding,
        "fixtures": rows,
        "adapter_results": adapter_rows,
        "runs": runs,
        "normalization_differences": differences,
        "source_line_transcription": [
            {
                "statistical_hts": c,
                "rate_line_key": f"{line:010d}",
                "general_rate": r,
                "general_disposition": g,
                "column2_disposition": d,
            }
            for c, line, r, g, d in LINES
        ],
        "scopes": [
            {
                "input": name,
                "source_evidence": "captured_live_primary_source",
                "status": "bounded_canonical_contract_replay_matches",
                "grounding": "uncaptured",
            }
            for name in (*FLAGS, "hts_line")
        ],
        "validation": {
            "real_runtime_cases": 63,
            "real_runtime_outputs": 189,
            "adapter_cases": 28,
            "canonical_witness_cases": 28,
            "source_rate_lookup_cases": 7,
            "all_canonical_contract_cases_match": True,
            "raw_direct_witness_alias_differences": 9,
            "new_campaign_rows_scanned": 0,
        },
        "input_contract": [
            "The adapter accepts ten digits with dots/spaces/hyphens; the direct witness compares the canonical dotted Text value literally. Normalize before calling the witness; raw input formats are not interchangeable.",
            "hts_line is an INTEGER legal rate-row key (displayed here with ten digits), not Text or Decimal. It can differ from the statistical reporting number: beer suffixes30/60/90 use2203000000; aluminum statistical suffix40 uses7601106000.",
            "The beer Column2 rate is13.2cents/liter, a specific duty. The real generated output retains specific disposition; no ad-valorem equivalent is inferred.",
            "These are interface and source-row tests, not CBP classification, preference qualification, historical-vintage coverage or total-duty certification.",
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
            sources.require(OUTPUT.read_bytes() == body, "identity evidence drift")
        else:
            OUTPUT.write_bytes(body)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("identity evidence failed: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode(), file=sys.stderr)
        return 1
    print(json.dumps(result["validation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
