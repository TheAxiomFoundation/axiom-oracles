#!/usr/bin/env python3
"""Read bounded run records and pinned local sources; emit audit evidence only."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

RUN = Path(__file__).resolve().parent
ORACLES = RUN / "B/oracles"
YALE = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")
CORPUS = Path("/Users/maxghenis/TheAxiomFoundation/axiom-corpus")
CORPUS_REF = "5cf7556ad3d68aa0596d58f7ac60942bb5db3120"
NOTES = "data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl"
NOTES_SHA = "0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    ).stdout


sys.path.insert(0, str(ORACLES))
producer_path = ORACLES / "scripts/build_us_tariff_preview_disposition_receipt.py"
spec = importlib.util.spec_from_file_location("measured_gap_source_join", producer_path)
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)
preview = json.loads((ORACLES / "reference/us-tariff-schedule/preview-disposition-line-sets.json").read_text())
bound = preview["yale_sources"]
# Reuse exactly the committed source identities; adapt only their container shape.
audit = {"sources": {
    "yale_repo": {"root": str(YALE), "commit": bound["commit"], "tree": bound["tree"]},
    "files": {str(YALE / name): value for name, value in bound["files"].items()},
}}
headings, annex, source_receipt = producer.verify_yale_sources(YALE, audit)
joins = []
for code, date in [
    ("9403999020", "2026-07-22"), ("9403999020", "2026-07-24"),
    ("8467895030", "2026-07-30"), ("8414308030", "2026-07-22"),
    ("8407344400", "2026-07-24"),
]:
    joins.append({"hts10": code, "probe": date, "yale_annex_tier": annex(code, date),
                  "heading_families": [name for name, prefixes in headings.items()
                                       if producer.prefix_hit(code, prefixes)]})

additional_source_hashes = {}
for name in ("resources/s301fl_final_country_exemptions.csv", "src/model/authority_adapter.R"):
    actual = (YALE / name).read_bytes()
    expected = git(YALE, "show", bound["commit"] + ":" + name)
    assert actual == expected, name
    additional_source_hashes[name] = digest(actual)

targets = {
    ("6203331040", "CR", "2026-08-01"),
    ("8467895030", "BR", "2026-07-30"),
    ("8414308030", "BR", "2026-07-23"),
    ("8407344400", "RU", "2026-07-30"),
    ("9403999020", "BR", "2026-07-22"),
    ("9403999020", "MX", "2026-07-24"),
}
samples, censuses = [], {}
line940 = {"cases": 0, "brazil_component_mismatches": 0, "note52_component_mismatches": 0,
           "cases_with_either_overlay_mismatch": 0, "section232_actual_values": set(),
           "section232_expected_values": set()}
for chapter in ("62", "84", "94"):
    shard = RUN / f"targeted-B/diagnostic-ch{chapter}.jsonl.gz"
    census = json.loads((RUN / f"targeted-B/diagnostic-ch{chapter}-census.json").read_text())
    assert digest(shard.read_bytes()) == census["verified_shard_sha256"], chapter
    censuses[chapter] = {name: census[name] for name in (
        "cases", "class_census", "class_per_slot", "summary", "verified_shard_sha256"
    )}
    with gzip.open(shard, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            if record["hts10"] == "9403999020":
                actual, expected = record["actual"], record["expected"]
                br = abs(actual["brazil_section_301_component_rate"] - float(expected["statutory_rate_s301br"])) > 1e-12
                fl = abs(actual["forced_labor_section_301_component_rate"] - float(expected["statutory_rate_s301fl"])) > 1e-12
                line940["cases"] += 1
                line940["brazil_component_mismatches"] += br
                line940["note52_component_mismatches"] += fl
                line940["cases_with_either_overlay_mismatch"] += br or fl
                line940["section232_actual_values"].add(actual["section_232_steel_component_rate"] + actual["section_232_aluminum_component_rate"])
                line940["section232_expected_values"].add(float(expected["statutory_rate_232"]))
            if (record["hts10"], record["iso2"], record["probe"]) in targets:
                samples.append(record)
assert {(row["hts10"], row["iso2"], row["probe"]) for row in samples} == targets

notes_raw = git(CORPUS, "show", CORPUS_REF + ":" + NOTES)
assert digest(notes_raw) == NOTES_SHA
excerpts = []
for number, line in enumerate(notes_raw.splitlines(), 1):
    row = json.loads(line)
    if row.get("kind") != "page" or row.get("parent_citation_path") != "us/statute/hts/chapter-99":
        continue
    body = row.get("body", "")
    if number in (246, 251):
        excerpts.append({"physical_jsonl_line": number, "citation_path": row["citation_path"], "body": body})
    elif number < 270 and "8467.89.50" in body:
        position = body.index("8467.89.50")
        excerpts.append({"physical_jsonl_line": number, "citation_path": row["citation_path"],
                         "body_prefix": body[:700], "sample_context": body[max(position-100, 0):position+160]})

result = {
    "schema": "measurement.bounded_gap_source_audit.v1",
    "verification": "PASS",
    "verification_basis": "Bounded fresh shard hashes and pinned local source identities; no new engine evaluation or statutory correctness verdict.",
    "yale_sources": source_receipt,
    "additional_yale_sources_equal_pinned_git_blobs": additional_source_hashes,
    "joins": joins,
    "bounded_censuses": censuses,
    "line9403999020_raw_record_census": {key: sorted(value) if isinstance(value, set) else value
                                        for key, value in line940.items()},
    "sample_engine_records": samples,
    "corpus": {"repo": str(CORPUS), "commit": CORPUS_REF, "path": NOTES,
               "sha256": NOTES_SHA, "selected_excerpts": excerpts},
}
output = RUN / "measured-gap-evidence.json"
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"verification": "PASS", "sample_records": len(samples),
                  "source_joins": len(joins), "yale_files_hash_verified": len(source_receipt["files"]),
                  "extra_yale_files_equal_git_blobs": len(additional_source_hashes),
                  "corpus_sha256": NOTES_SHA, "output": str(output)}, indent=2))
