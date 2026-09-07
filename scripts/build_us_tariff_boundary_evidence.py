#!/usr/bin/env python3
"""Reproduce bounded source evidence and real-runtime boundary probes, offline.

This receipt is evidence about a frozen program, not an entry classification or
program certificate. All six transaction inputs remain uncaptured. No campaign
shards or comparison rows are scanned. Expected truth-table values are test
oracles; every observed value comes from the pinned Axiom Rust binary.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import us_tariff_closure as closure  # noqa: E402

OUTPUT = ROOT / "reference/us-tariff-schedule/boundary-evidence/note2-exceptions.json"
SCHEMA = "axiom_oracles.us_tariff_schedule.boundary_evidence.v1"
SOURCE_URL = (
    "https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%2099"
)
PDF = "data/corpus/sources/us/statute/2026-08-04-usitc-hts-2026-rev15-notes/official-documents/usitc-hts-2026-rev15-chapter-99.pdf"
PDF_SHA256 = "92822e8f38873a7275c4cf9bd5341f96f5834dbea964623e7a7aa7b2cd02f225"
INGEST = ".axiom/ingest-manifests/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.json"
INPUTS = (
    "entry_is_humanitarian_donation_article",
    "entry_is_informational_material_article",
    "entry_is_personal_use_accompanied_baggage",
    "entry_is_properly_claimed_chapter_98_entry",
    "cbp_agrees_chapter_98_entry_is_appropriate",
    "entry_is_9802_excepted_entry",
)
MODULES = (
    closure.WITNESS_MODULE,
    "us/policies/cbp/us-tariff-schedule/generated/ch72/ch72.yaml",
)
OUTPUT_NAMES = (
    "entry_is_fentanyl_china_excepted",
    "ieepa_component_rate_with_declared_exceptions",
)
ORIGINS = ("CN", "HK", "FR")
DAY = "2026-02-16"
# Independently transcribed from note 2(u): absent donation/information/baggage,
# only a claim AND CBP agreement AND no 9802 carve-out produces the exception.
# Bit order is INPUTS. The other 57 assignments satisfy an exception predicate.
NONEXEMPT_BITS = frozenset(
    ("000000", "000001", "000010", "000011", "000100", "000101", "000111")
)
LIMITATIONS = [
    "All inputs are synthetic stipulated facts, not evidence about any actual entry.",
    "The donation flag means the complete note 2(t) condition, including its presidential-determination caveats; the program does not derive those qualifications.",
    "Chapter 98 claim, CBP acceptance, baggage use and 9802 classification remain external determinations. The 9802 partial customs-value basis is not tested or certified here.",
    "The exception judgment is origin-independent; the component rate applies the China/Hong Kong origin gate. France is a negative origin control.",
    "HTS 7202.11.10.00 uses the program's preexisting reciprocal-annex exclusion. This batch does not establish that separate annex membership or total-duty parity.",
    "Rev-15 is a frozen source snapshot. One encoded day and two compositions do not establish historical-vintage completeness or all-100-chapter behavioral coverage.",
    "An existing ingest signature is preserved and its applied-file hashes are checked. This receipt does not independently verify that signature against a trusted public key.",
    "No boundary grounding, closure status, campaign disposition, or release approval changes. Final Fable review and existing release gates remain required.",
]


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def render(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_bytes(repo: Path, ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{path}"])


def binding(path: str, data: bytes) -> dict:
    return {"path": path, "bytes": len(data), "sha256": digest(data)}


def source_evidence(corpus: Path) -> dict:
    notes = git_bytes(corpus, closure.CORPUS_REF, closure.NOTES)
    require(digest(notes) == closure.NOTES_SHA256, "pinned notes digest drift")
    pdf = git_bytes(corpus, closure.CORPUS_REF, PDF)
    require(
        digest(pdf) == PDF_SHA256 and pdf.startswith(b"%PDF-"),
        "pinned PDF digest/format drift",
    )
    manifest_bytes = git_bytes(corpus, closure.CORPUS_REF, INGEST)
    manifest = json.loads(manifest_bytes)
    applied = {row["path"]: row["sha256"] for row in manifest["applied_files"]}
    require(
        applied.get(PDF) == digest(pdf) and applied.get(closure.NOTES) == digest(notes),
        "ingest applied-file bindings drift",
    )
    records = []
    citations = {f"us/statute/hts/chapter-99/page-{page}" for page in (176, 598)}
    for line_number, line in enumerate(notes.splitlines(), 1):
        row = json.loads(line)
        if row.get("citation_path") in citations:
            require(
                row["source_url"] == SOURCE_URL
                and row["source_path"] == PDF.removeprefix("data/corpus/"),
                "source URL/path drift",
            )
            require(row["metadata"]["primary_source"] is True, "source is not primary")
            records.append(
                {
                    "jsonl_line": line_number,
                    "raw_record_sha256": digest(line),
                    "record": row,
                }
            )
    require(
        {row["record"]["citation_path"] for row in records} == citations
        and len(records) == 2,
        "source citation population drift",
    )
    return {
        "repo": "TheAxiomFoundation/axiom-corpus",
        "ref": closure.CORPUS_REF,
        "notes": binding(closure.NOTES, notes),
        "pdf": binding(PDF, pdf),
        "authoritative_url": SOURCE_URL,
        "ingest_manifest": {
            **binding(INGEST, manifest_bytes),
            "signature": manifest["signature"],
            "applied_file_hashes_match": True,
            "trusted_signature_verification": "not_performed",
        },
        "records": records,
    }


def boundary_scopes() -> list[dict]:
    scopes = dict(closure.CANONICAL_INPUT_SCOPES)
    evidence = (
        (
            "176",
            "U.S. note 2(t), complete donation condition",
            "donor jurisdiction, humanitarian purpose and applicable presidential determinations",
        ),
        (
            "598",
            "HTS 9903.01.22, article description",
            "article facts establishing informational-material status",
        ),
        (
            "176",
            "U.S. note 2(u), accompanied-baggage exclusion",
            "traveler, accompaniment and personal-use records",
        ),
        (
            "176",
            "U.S. note 2(u), Chapter 98 claim clause",
            "proper Chapter 98 claim under applicable CBP regulations",
        ),
        (
            "176",
            "U.S. note 2(u), CBP agreement clause",
            "entry record of CBP agreement with the Chapter 98 treatment",
        ),
        (
            "176",
            "U.S. note 2(u), four 9802 carve-outs and partial-value bases",
            "classification under 9802.00.40/.50/.60/.80 and separately supported dutiable partial value",
        ),
    )
    return [
        {
            "input": name,
            "canonical_scope": scopes[name],
            "grounding": "uncaptured",
            "source_evidence": "captured_for_frozen_snapshot",
            "citation_path": f"us/statute/hts/chapter-99/page-{page}",
            "clause": clause,
            "actual_entry_blocker": blocker,
        }
        for name, (page, clause, blocker) in zip(INPUTS, evidence, strict=True)
    ]


def fixture_rows() -> list[dict]:
    rows = []
    for origin, bits in itertools.product(
        ORIGINS, itertools.product((False, True), repeat=6)
    ):
        bitstring = "".join(str(int(value)) for value in bits)
        excepted = bitstring not in NONEXEMPT_BITS
        rows.append(
            {
                "case_id": f"note2-{origin}-{bitstring}",
                "origin": origin,
                "flags": dict(zip(INPUTS, bits, strict=True)),
                "expected": {
                    OUTPUT_NAMES[0]: excepted,
                    OUTPUT_NAMES[1]: 0.1
                    if origin in ("CN", "HK") and not excepted
                    else 0.0,
                },
            }
        )
    return rows


def scalar(value: object) -> dict:
    if type(value) is bool:
        return {"kind": "bool", "value": value}
    require(isinstance(value, str), "unsupported input type")
    return {"kind": "text", "value": value}


def execution_request(module: str, fixtures: list[dict]) -> dict:
    prefix = "us:" + module.removeprefix("us/").removesuffix(".yaml") + "#"
    inputs, queries = [], []
    for row in fixtures:
        facts = {**row["flags"], "country_of_origin": row["origin"]}
        if module == closure.WITNESS_MODULE:
            facts["hts_number"] = "7202.11.10.00"
        else:
            facts.update(
                entry_is_line_a=True, entry_is_line_b=False, entry_is_line_d=False
            )
        for name, value in sorted(facts.items()):
            inputs.append(
                {
                    "name": prefix + "input." + name,
                    "entity": "CustomsEntry",
                    "entity_id": row["case_id"],
                    "interval": {"start": DAY, "end": DAY},
                    "value": scalar(value),
                }
            )
        queries.append(
            {
                "entity_id": row["case_id"],
                "period": {
                    "period_kind": "custom",
                    "name": "day",
                    "start": DAY,
                    "end": DAY,
                },
                "outputs": [prefix + name for name in OUTPUT_NAMES],
            }
        )
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def check_results(payload: dict, request: dict, fixtures: list[dict]) -> list[dict]:
    results = payload.get("results")
    require(
        isinstance(results, list) and len(results) == len(fixtures),
        "runtime result cardinality drift",
    )
    checked = []
    for result, query, fixture in zip(
        results, request["queries"], fixtures, strict=True
    ):
        require(
            result["entity_id"] == fixture["case_id"]
            and result["period"] == query["period"],
            "runtime result identity/period drift",
        )
        require(
            set(result["outputs"]) == set(query["outputs"]),
            "runtime output population drift",
        )
        actual = {}
        for name, absolute in zip(OUTPUT_NAMES, query["outputs"], strict=True):
            value = result["outputs"][absolute]
            if name == OUTPUT_NAMES[0]:
                require(
                    value["kind"] == "judgment"
                    and value["outcome"] in ("holds", "not_holds"),
                    "invalid runtime judgment",
                )
                actual[name] = value["outcome"] == "holds"
                require(
                    actual[name] is fixture["expected"][name],
                    f"runtime judgment mismatch: {fixture['case_id']}",
                )
            else:
                require(
                    value["kind"] == "scalar" and value["value"]["kind"] == "decimal",
                    "invalid runtime rate",
                )
                from decimal import Decimal

                require(
                    Decimal(value["value"]["value"])
                    == Decimal(str(fixture["expected"][name])),
                    f"runtime rate mismatch: {fixture['case_id']}",
                )
                actual[name] = value["value"]["value"]
        checked.append({"case_id": fixture["case_id"], "actual": actual, "match": True})
    return checked


def build(
    *,
    corpus: Path = closure.CORPUS,
    rulespec: Path = closure.RULESPEC,
    engine: Path = closure.INPUT_INVENTORY_ENGINE,
) -> dict:
    source = source_evidence(corpus)
    engine_bytes = engine.read_bytes()
    require(
        digest(engine_bytes) == closure.INPUT_INVENTORY_ENGINE_SHA256,
        "engine pin drift",
    )
    fixtures = fixture_rows()
    runs = []
    with tempfile.TemporaryDirectory(prefix="tariff-boundary-evidence-") as raw:
        work = Path(raw)
        binary = work / "axiom-rules-engine"
        binary.write_bytes(engine_bytes)
        binary.chmod(0o700)
        archive = subprocess.check_output(
            [
                "git",
                "-C",
                str(rulespec),
                "archive",
                closure.RULESPEC_REF,
                "us",
                "programs",
            ]
        )
        snapshot = work / "rulespec-us"
        snapshot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(snapshot, filter="data")
        env = dict(os.environ)
        env.pop("AXIOM_RULESPEC_ROOT", None)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(work)
        for module in MODULES:
            artifact = work / "compiled.json"
            artifact.unlink(missing_ok=True)
            subprocess.run(
                [
                    str(binary),
                    "compile",
                    "--program",
                    str(snapshot / module),
                    "--output",
                    str(artifact),
                ],
                check=True,
                capture_output=True,
                env=env,
            )
            request = execution_request(module, fixtures)
            response = subprocess.run(
                [str(binary), "run-compiled", "--artifact", str(artifact)],
                input=canonical(request),
                check=True,
                capture_output=True,
                env=env,
            )
            payload = json.loads(response.stdout)
            checked = check_results(payload, request, fixtures)
            runs.append(
                {
                    "module": binding(module, (snapshot / module).read_bytes()),
                    "compiled_sha256": digest(artifact.read_bytes()),
                    "request": request,
                    "request_sha256": digest(canonical(request)),
                    "response": payload,
                    "response_sha256": digest(canonical(payload)),
                    "checked_results": checked,
                }
            )
    return {
        "schema": SCHEMA,
        "generated_by": "scripts/build_us_tariff_boundary_evidence.py",
        "producer_sha256": digest(Path(__file__).read_bytes()),
        "source": source,
        "rulespec_ref": closure.RULESPEC_REF,
        "engine_sha256": digest(engine_bytes),
        "scopes": boundary_scopes(),
        "day": DAY,
        "fixture_rows": fixtures,
        "runs": runs,
        "validation": {
            "module_count": 2,
            "scope_count": 6,
            "boolean_assignments_per_origin": 64,
            "origins": list(ORIGINS),
            "case_count": 384,
            "checked_output_count": 768,
            "positive_rate_cases": 28,
            "all_cases_match": True,
        },
        "claim": {
            "kind": "bounded_source_and_runtime_evidence",
            "actual_entry_grounding": "uncaptured",
            "closed": False,
            "certified": False,
            "release_authorized": False,
        },
        "limitations": LIMITATIONS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="replay all 384 cases and compare exact receipt bytes",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--corpus-root", type=Path, default=closure.CORPUS)
    parser.add_argument("--rulespec-root", type=Path, default=closure.RULESPEC)
    parser.add_argument("--engine", type=Path, default=closure.INPUT_INVENTORY_ENGINE)
    args = parser.parse_args()
    try:
        document = build(
            corpus=args.corpus_root, rulespec=args.rulespec_root, engine=args.engine
        )
        text = render(document)
        if args.check:
            require(
                args.output.read_text() == text, "boundary evidence receipt drifted"
            )
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_suffix(".tmp")
            temporary.write_text(text)
            temporary.replace(args.output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"boundary evidence failed: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(
                exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr,
                file=sys.stderr,
            )
        return 1
    print(
        "boundary evidence reproduced: 6 scopes, 384 cases, 768 outputs; actual-entry grounding=uncaptured, certified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
