#!/usr/bin/env python3
"""Verify and reproduce the NZ IncomeExplorer executable receipt.

The committed receipt is usable in two layers:

* ``--check`` is hermetic.  It hashes the committed compiled program bytes,
  request set, golden outputs, and execution transcript; re-derives every
  stored Boolean; and binds the selected comparison cells to the pinned source
  comparison.
* ``--check --live`` additionally requires the pinned RuleSpec checkout and
  engine binary, recompiles the composition byte-for-byte, executes every
  committed request, and compares the fresh transcript byte-for-byte.

The bootstrap option exists to import the original harness capture.  It is not
part of CI: subsequent verification runs only from committed inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "conformance" / "executable" / "nz-treasury-incomeexplorer"
RECEIPT_PATH = REPO_ROOT / "conformance" / "executable" / "nz-treasury-incomeexplorer.json"
COMPOSITION_PATH = OUT_DIR / "composition.yaml"
ARTIFACT_PATH = OUT_DIR / "compiled-program.json"
REQUESTS_PATH = OUT_DIR / "requests.json"
GOLDEN_PATH = OUT_DIR / "golden-outputs.json"
TRANSCRIPT_PATH = OUT_DIR / "transcript.json"
SOURCE_REPORT_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "source-comparison.json"
)

SCHEMA = "axiom_oracles.executable_reproduction.v1"
REQUEST_SCHEMA = "axiom_oracles.nz_executable_requests.v1"
GOLDEN_SCHEMA = "axiom_oracles.nz_executable_golden_outputs.v1"
TRANSCRIPT_SCHEMA = "axiom_oracles.nz_executable_transcript.v1"
GENERATED_BY = "scripts/nz_executable_reproduction.py"
HARNESS = "TheAxiomFoundation/ops/nz-lane/emtr_reproduction/run.py"
HARNESS_COMMIT = "bcf631b5"
RULESPEC_REPO = "TheAxiomFoundation/rulespec-nz"
RULESPEC_SHA = "89a7d25dc03a4d045348620283332de10b1047da"
ENGINE_REPO = "TheAxiomFoundation/axiom-rules-engine"
ENGINE_GIT_SHA = "d59969b53430ae2fd97eb4349d44ad23ce930d85"
ENGINE_BINARY_SHA256 = "56fbffea1e0e32c52b6fcbddbca76223bb185b33b49368c288e0c7213b0126e1"
COMPOSITION_SHA256 = "af2ce73f1b16a74603965db1da92991545838748e943f3ed81cef394d469c3b0"
COMPILED_SHA256 = "b1d72c1f4840a1774aefbddc9692e22a79ced26cde6c44efb4c01fc394a15c33"
SCENARIO_ID = "single_parent_three_children_area1_rent"
WEEKLY_WAGES = (0, 740)
PERIOD = {"period_kind": "tax_year", "start": "2026-04-01", "end": "2027-03-31"}

DEFAULT_RULESPEC_ROOT = (
    Path("/Users/maxghenis/TheAxiomFoundation/_axiom-worktrees/")
    / "rulespec-nz-emtr/rulespec-nz"
)
DEFAULT_ENGINE_ROOT = Path(
    "/Users/maxghenis/TheAxiomFoundation/_worktrees/engine-release-clone"
)
DEFAULT_ENGINE_BINARY = DEFAULT_ENGINE_ROOT / "target/release/axiom-rules-engine"

PROGRAM_ROOTS: dict[str, tuple[str, ...]] = {
    "nz/acc-earners-levy": (
        "nz:regulations/acc/earners_levy#acc_standard_earners_levy_including_gst",
    ),
    "nz/accommodation-supplement": (
        "nz:statutes/social_security/accommodation_supplement/core#accommodation_supplement_rounded_weekly_payment",
        "nz:statutes/social_security/accommodation_supplement/core#accommodation_supplement_weekly_amount_before_rounding",
        "nz:statutes/social_security/accommodation_supplement/core#accommodation_supplement_weekly_qualifying_accommodation_costs",
    ),
    "nz/income-tax": (
        "nz:statutes/income_tax/schedule_1/individual_income_tax#individual_income_tax_before_credits",
    ),
    "nz/independent-earner-tax-credit": (
        "nz:statutes/income_tax/credits/individual_credits#independent_earner_tax_credit",
    ),
    "nz/main-benefits": (
        "nz:statutes/social_security/main_benefits/rates#jobseeker_support_net_weekly_payment",
        "nz:statutes/social_security/main_benefits/rates#sole_parent_support_net_weekly_payment",
    ),
    "nz/winter-energy-payment": (
        "nz:statutes/social_security/winter_energy_payment/core#winter_energy_payment_rate_per_winter_period",
    ),
    "nz/working-for-families": (
        "nz:statutes/income_tax/family_scheme/eligibility#entitled_to_in_work_tax_credit",
        "nz:statutes/income_tax/family_scheme/family_scheme_income#family_scheme_income",
        "nz:statutes/income_tax/family_scheme/tax_credits#best_start_credit_abatement",
        "nz:statutes/income_tax/family_scheme/tax_credits#best_start_tax_credit",
        "nz:statutes/income_tax/family_scheme/tax_credits#best_start_tax_credit_before_abatement",
        "nz:statutes/income_tax/family_scheme/tax_credits#family_tax_credit_after_abatement",
        "nz:statutes/income_tax/family_scheme/tax_credits#family_tax_credit_before_abatement",
        "nz:statutes/income_tax/family_scheme/tax_credits#in_work_tax_credit_before_abatement",
        "nz:statutes/income_tax/family_scheme/tax_credits#minimum_family_tax_credit",
        "nz:statutes/income_tax/family_scheme/tax_credits#wff_abatement_remaining_after_family_tax_credit",
    ),
}

COLUMN_PROGRAM = {
    "wage1_ACC_levy": "nz/acc-earners-levy",
    "AS_Amount": "nz/accommodation-supplement",
    "wage1_tax": "nz/income-tax",
    "IETC_abated": "nz/independent-earner-tax-credit",
    "net_benefit": "nz/main-benefits",
    "WinterEnergy": "nz/winter-energy-payment",
    "FTC_abated": "nz/working-for-families",
    "IWTC_abated": "nz/working-for-families",
    "MFTC": "nz/working-for-families",
    "BestStart_Total": "nz/working-for-families",
    "WFF_abated": "nz/working-for-families",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _render(value: Any) -> str:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _program_for_outputs(outputs: list[str]) -> str:
    matches = [
        program
        for program, roots in PROGRAM_ROOTS.items()
        if outputs and set(outputs).issubset(roots)
    ]
    _require(len(matches) == 1, f"request outputs do not select one NZ program: {outputs}")
    return matches[0]


def _comparison_cells(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    wanted = {
        (SCENARIO_ID, wage, column): program
        for wage in WEEKLY_WAGES
        for column, program in COLUMN_PROGRAM.items()
    }
    found: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in report.get("comparisons") or []:
        if not isinstance(row, dict):
            continue
        key = (row.get("scenario_id"), row.get("weekly_wage"), row.get("column"))
        if key in wanted:
            found[key] = {
                "scenario_id": key[0],
                "weekly_wage": key[1],
                "column": key[2],
                "program": wanted[key],
                "rulespec_value": row.get("rulespec"),
                "unit": row.get("unit"),
            }
    missing = sorted(set(wanted) - set(found))
    _require(not missing, f"source comparison is missing golden cells: {missing}")
    return [found[key] for key in sorted(found)]


def _validate_requests(document: Mapping[str, Any]) -> dict[str, list[str]]:
    _require(document.get("schema") == REQUEST_SCHEMA, "unexpected request schema")
    provenance = document.get("provenance")
    _require(isinstance(provenance, dict), "request provenance must be an object")
    _require(provenance.get("harness") == HARNESS, "request harness path drifted")
    _require(provenance.get("harness_commit") == HARNESS_COMMIT, "request harness commit drifted")
    _require(provenance.get("rulespec_commit") == RULESPEC_SHA, "request RuleSpec pin drifted")
    _require(provenance.get("engine_git_sha") == ENGINE_GIT_SHA, "request engine Git pin drifted")
    _require(
        provenance.get("engine_binary_sha256") == ENGINE_BINARY_SHA256,
        "request engine binary pin drifted",
    )
    _require(provenance.get("compiled_sha256") == COMPILED_SHA256, "request artifact pin drifted")
    subset = document.get("comparison_subset")
    _require(
        subset
        == {
            "scenario_id": SCENARIO_ID,
            "weekly_wages": list(WEEKLY_WAGES),
            "comparison_columns": sorted(COLUMN_PROGRAM),
            "comparison_cell_count": len(WEEKLY_WAGES) * len(COLUMN_PROGRAM),
            "full_comparison_cell_count": 1976,
        },
        "request comparison subset drifted",
    )
    rows = document.get("requests")
    _require(isinstance(rows, list) and rows, "request set must be non-empty")
    seen: set[str] = set()
    roots: dict[str, set[str]] = {program: set() for program in PROGRAM_ROOTS}
    for row in rows:
        _require(isinstance(row, dict), "request row must be an object")
        request_id = row.get("id")
        _require(isinstance(request_id, str) and request_id, "request id is missing")
        _require(request_id not in seen, f"duplicate request id {request_id}")
        seen.add(request_id)
        request = row.get("request")
        _require(isinstance(request, dict), f"{request_id}: request must be an object")
        _require(request.get("mode") == "explain", f"{request_id}: mode must be explain")
        queries = request.get("queries")
        _require(isinstance(queries, list) and len(queries) == 1, f"{request_id}: one query required")
        query = queries[0]
        _require(query.get("period") == PERIOD, f"{request_id}: tax-year period drifted")
        outputs = query.get("outputs")
        _require(
            isinstance(outputs, list)
            and outputs == list(dict.fromkeys(outputs))
            and all(isinstance(output, str) and output for output in outputs),
            f"{request_id}: outputs must be unique non-empty strings",
        )
        program = _program_for_outputs(outputs)
        _require(row.get("program") == program, f"{request_id}: program label is not derived from outputs")
        roots[program].update(outputs)
    derived = {program: sorted(values) for program, values in sorted(roots.items())}
    _require(
        document.get("requested_outputs_by_program") == derived,
        "requested-output root summary is not derived from the request trace",
    )
    return derived


def _validate_golden(
    document: Mapping[str, Any], requests: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    _require(document.get("schema") == GOLDEN_SCHEMA, "unexpected golden schema")
    _require(document.get("source_report") == str(SOURCE_REPORT_PATH.relative_to(REPO_ROOT)), "golden source report path drifted")
    _require(document.get("source_report_sha256") == _sha256(SOURCE_REPORT_PATH), "golden source report hash drifted")
    _require(document.get("comparison_cells") == _comparison_cells(report), "golden comparison-cell subset drifted")
    request_rows = requests["requests"]
    rows = document.get("requests")
    _require(isinstance(rows, list) and len(rows) == len(request_rows), "golden request cardinality drifted")
    by_id: dict[str, Mapping[str, Any]] = {}
    for actual, request_row in zip(rows, request_rows, strict=True):
        _require(isinstance(actual, dict), "golden row must be an object")
        request_id = request_row["id"]
        _require(actual.get("id") == request_id, f"golden row order/id drifted at {request_id}")
        _require(actual.get("program") == request_row["program"], f"{request_id}: golden program drifted")
        expected_hash = _sha256_bytes(_canonical(request_row["request"]))
        _require(actual.get("request_sha256") == expected_hash, f"{request_id}: golden request hash drifted")
        outputs = actual.get("outputs")
        _require(isinstance(outputs, dict), f"{request_id}: golden outputs must be an object")
        _require(set(outputs) == set(request_row["request"]["queries"][0]["outputs"]), f"{request_id}: golden output keys drifted")
        by_id[request_id] = actual
    return by_id


def _transcript_document(
    requests: Mapping[str, Any],
    golden_by_id: Mapping[str, Mapping[str, Any]],
    responses: list[Mapping[str, Any]],
) -> dict[str, Any]:
    request_rows = requests["requests"]
    _require(len(responses) == len(request_rows), "engine response cardinality drifted")
    rows = []
    for request_row, response in zip(request_rows, responses, strict=True):
        request_id = request_row["id"]
        results = response.get("results")
        _require(isinstance(results, list) and len(results) == 1, f"{request_id}: engine returned != 1 result")
        outputs = results[0].get("outputs")
        _require(isinstance(outputs, dict), f"{request_id}: engine outputs missing")
        expected = golden_by_id[request_id]["outputs"]
        match = _canonical(outputs) == _canonical(expected)
        rows.append(
            {
                "id": request_id,
                "program": request_row["program"],
                "request_sha256": _sha256_bytes(_canonical(request_row["request"])),
                "response_sha256": _sha256_bytes(_canonical(response)),
                "metadata": response.get("metadata"),
                "outputs": outputs,
                "golden_match": match,
            }
        )
    return {"schema": TRANSCRIPT_SCHEMA, "requests": rows}


def _validate_transcript(
    document: Mapping[str, Any],
    requests: Mapping[str, Any],
    golden_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _require(document.get("schema") == TRANSCRIPT_SCHEMA, "unexpected transcript schema")
    rows = document.get("requests")
    request_rows = requests["requests"]
    _require(isinstance(rows, list) and len(rows) == len(request_rows), "transcript cardinality drifted")
    matches_by_program = {program: True for program in PROGRAM_ROOTS}
    for row, request_row in zip(rows, request_rows, strict=True):
        request_id = request_row["id"]
        _require(isinstance(row, dict) and row.get("id") == request_id, f"transcript order/id drifted at {request_id}")
        _require(row.get("program") == request_row["program"], f"{request_id}: transcript program drifted")
        _require(row.get("request_sha256") == _sha256_bytes(_canonical(request_row["request"])), f"{request_id}: transcript request hash drifted")
        response_hash = row.get("response_sha256")
        _require(isinstance(response_hash, str) and len(response_hash) == 64, f"{request_id}: response hash invalid")
        expected = golden_by_id[request_id]["outputs"]
        derived_match = _canonical(row.get("outputs")) == _canonical(expected)
        _require(row.get("golden_match") is derived_match, f"{request_id}: golden_match is not derived")
        matches_by_program[request_row["program"]] &= derived_match
        metadata = row.get("metadata")
        _require(
            isinstance(metadata, dict)
            and metadata.get("requested_mode") == "explain"
            and metadata.get("actual_mode") == "explain",
            f"{request_id}: engine did not execute in explain mode",
        )
    programs = {
        program: {
            "request_count": sum(row["program"] == program for row in request_rows),
            "requested_root_count": len(PROGRAM_ROOTS[program]),
            "all_golden_outputs_reproduced": matches_by_program[program],
            "executable": matches_by_program[program],
        }
        for program in sorted(PROGRAM_ROOTS)
    }
    return {
        "program_count": len(programs),
        "request_count": len(request_rows),
        "comparison_cell_count": len(WEEKLY_WAGES) * len(COLUMN_PROGRAM),
        "all_golden_outputs_reproduced": all(matches_by_program.values()),
        "programs": programs,
        "executable": all(matches_by_program.values()),
    }


def _receipt_document(summary: Mapping[str, Any]) -> dict[str, Any]:
    report = _load(SOURCE_REPORT_PATH)
    return {
        "schema": SCHEMA,
        "program": "nz/treasury-incomeexplorer-comparison-composition",
        "programs": sorted(PROGRAM_ROOTS),
        "generated_by": GENERATED_BY,
        "execution_period": "2026-04-01/2027-03-31",
        "engine": {
            "repository": ENGINE_REPO,
            "git_sha": ENGINE_GIT_SHA,
            "binary_sha256": ENGINE_BINARY_SHA256,
        },
        "rulespec": {"repository": RULESPEC_REPO, "sha": RULESPEC_SHA},
        "source_report": {
            "path": str(SOURCE_REPORT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(SOURCE_REPORT_PATH),
            "compiled_artifact_sha256": (report.get("compiled_program") or {}).get("artifact_sha256"),
        },
        "composition": {
            "path": str(COMPOSITION_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(COMPOSITION_PATH),
        },
        "compiled_artifact": {
            "path": str(ARTIFACT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(ARTIFACT_PATH),
            "byte_count": ARTIFACT_PATH.stat().st_size,
            "compile_contract": "compile-composed",
        },
        "request_set": {
            "path": str(REQUESTS_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(REQUESTS_PATH),
        },
        "golden_outputs": {
            "path": str(GOLDEN_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(GOLDEN_PATH),
        },
        "transcript": {
            "path": str(TRANSCRIPT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(TRANSCRIPT_PATH),
        },
        "summary": summary,
    }


def validate_artifact(
    document: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Hermetically validate receipt bytes and re-derive executable values."""

    _require(Path(repo_root).resolve() == REPO_ROOT.resolve(), "NZ receipt must validate at repository root")
    _require(document.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    _require(document.get("generated_by") == GENERATED_BY, "receipt producer drifted")
    report = _load(SOURCE_REPORT_PATH)
    provenance = report.get("provenance") or {}
    engine = provenance.get("engine") or {}
    compiled = report.get("compiled_program") or {}
    _require(engine.get("expected_git_sha") == ENGINE_GIT_SHA, "source report engine Git pin drifted")
    _require(engine.get("binary_sha256") == ENGINE_BINARY_SHA256, "source report engine binary pin drifted")
    _require(compiled.get("artifact_sha256") == COMPILED_SHA256, "source report compiled digest drifted")
    _require(_sha256(COMPOSITION_PATH) == COMPOSITION_SHA256, "committed composition bytes drifted")
    _require(_sha256(ARTIFACT_PATH) == COMPILED_SHA256, "committed compiled artifact bytes drifted")
    requests = _load(REQUESTS_PATH)
    roots = _validate_requests(requests)
    _require(roots == {program: sorted(values) for program, values in sorted(PROGRAM_ROOTS.items())}, "request trace does not cover the full emitted output-root set")
    golden = _load(GOLDEN_PATH)
    golden_by_id = _validate_golden(golden, requests, report)
    transcript = _load(TRANSCRIPT_PATH)
    summary = _validate_transcript(transcript, requests, golden_by_id)
    expected = _receipt_document(summary)
    _require(document == expected, "executable receipt is not derived from committed artifacts")
    return summary


def _run(command: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)
    if process.returncode:
        raise ValueError(process.stderr.strip() or process.stdout.strip() or f"command failed: {command}")
    return process


def _live_reproduction(
    *, rulespec_root: Path, engine_root: Path, engine_binary: Path
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    _require(engine_binary.is_file(), f"pinned engine binary is missing: {engine_binary}")
    _require(_sha256(engine_binary) == ENGINE_BINARY_SHA256, "engine binary bytes do not match the pin")
    git_sha = _run(["git", "-C", str(engine_root), "rev-parse", "HEAD"]).stdout.strip()
    _require(git_sha == ENGINE_GIT_SHA, "engine checkout does not match the pinned Git SHA")
    rulespec_sha = _run(["git", "-C", str(rulespec_root), "rev-parse", "HEAD"]).stdout.strip()
    _require(rulespec_sha == RULESPEC_SHA, "RuleSpec checkout does not match the pinned Git SHA")
    requests = _load(REQUESTS_PATH)
    _validate_requests(requests)
    golden = _load(GOLDEN_PATH)
    golden_by_id = _validate_golden(golden, requests, _load(SOURCE_REPORT_PATH))
    with tempfile.TemporaryDirectory(prefix="nz-executable-reproduction-") as raw_tmp:
        artifact = Path(raw_tmp) / "compiled-program.json"
        _run(
            [
                str(engine_binary),
                "compile-composed",
                "--program",
                str(COMPOSITION_PATH),
                "--rulespec-root",
                str(rulespec_root),
                "--output",
                str(artifact),
            ]
        )
        artifact_bytes = artifact.read_bytes()
        _require(_sha256_bytes(artifact_bytes) == COMPILED_SHA256, "fresh compiled artifact digest drifted")
        _require(artifact_bytes == ARTIFACT_PATH.read_bytes(), "fresh compiled artifact is not byte-identical")
        responses = []
        for row in requests["requests"]:
            process = _run(
                [str(engine_binary), "run-compiled", "--artifact", str(artifact)],
                stdin=json.dumps(row["request"], sort_keys=True, separators=(",", ":")),
            )
            try:
                responses.append(json.loads(process.stdout))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{row['id']}: engine returned invalid JSON") from exc
    transcript = _transcript_document(requests, golden_by_id, responses)
    summary = _validate_transcript(transcript, requests, golden_by_id)
    return artifact_bytes, transcript, _receipt_document(summary)


def _bootstrap_capture(capture_path: Path, compiled_path: Path) -> None:
    capture = _load(capture_path)
    records = capture.get("records")
    _require(isinstance(records, list) and records, "capture has no engine records")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(compiled_path, ARTIFACT_PATH)
    _require(_sha256(ARTIFACT_PATH) == COMPILED_SHA256, "bootstrap compiled artifact has wrong digest")
    request_rows = []
    golden_rows = []
    responses = []
    for index, record in enumerate(records):
        _require(isinstance(record, dict), "capture record must be an object")
        request = record.get("request")
        response = record.get("response")
        _require(isinstance(request, dict) and isinstance(response, dict), "capture request/response missing")
        request_id = f"golden-{index:02d}"
        outputs = request["queries"][0]["outputs"]
        program = _program_for_outputs(outputs)
        request_rows.append(
            {
                "id": request_id,
                "program": program,
                "harness_label": record.get("label"),
                "request": request,
            }
        )
        result_rows = response.get("results")
        _require(isinstance(result_rows, list) and len(result_rows) == 1, f"{request_id}: invalid captured response")
        golden_rows.append(
            {
                "id": request_id,
                "program": program,
                "request_sha256": _sha256_bytes(_canonical(request)),
                "outputs": result_rows[0].get("outputs"),
            }
        )
        responses.append(response)
    roots: dict[str, set[str]] = {program: set() for program in PROGRAM_ROOTS}
    for row in request_rows:
        roots[row["program"]].update(row["request"]["queries"][0]["outputs"])
    requests = {
        "schema": REQUEST_SCHEMA,
        "provenance": {
            "harness": HARNESS,
            "harness_commit": HARNESS_COMMIT,
            "rulespec_commit": RULESPEC_SHA,
            "engine_git_sha": ENGINE_GIT_SHA,
            "engine_binary_sha256": ENGINE_BINARY_SHA256,
            "compiled_sha256": COMPILED_SHA256,
        },
        "comparison_subset": {
            "scenario_id": SCENARIO_ID,
            "weekly_wages": list(WEEKLY_WAGES),
            "comparison_columns": sorted(COLUMN_PROGRAM),
            "comparison_cell_count": len(WEEKLY_WAGES) * len(COLUMN_PROGRAM),
            "full_comparison_cell_count": 1976,
        },
        "requests": request_rows,
        "requested_outputs_by_program": {
            program: sorted(values) for program, values in sorted(roots.items())
        },
    }
    REQUESTS_PATH.write_text(_render(requests))
    golden = {
        "schema": GOLDEN_SCHEMA,
        "source_report": str(SOURCE_REPORT_PATH.relative_to(REPO_ROOT)),
        "source_report_sha256": _sha256(SOURCE_REPORT_PATH),
        "comparison_cells": _comparison_cells(_load(SOURCE_REPORT_PATH)),
        "requests": golden_rows,
    }
    GOLDEN_PATH.write_text(_render(golden))
    golden_by_id = _validate_golden(golden, requests, _load(SOURCE_REPORT_PATH))
    transcript = _transcript_document(requests, golden_by_id, responses)
    TRANSCRIPT_PATH.write_text(_render(transcript))
    summary = _validate_transcript(transcript, requests, golden_by_id)
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.write_text(_render(_receipt_document(summary)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--live", action="store_true", help="recompile and execute the pinned requests")
    parser.add_argument("--refresh-receipt", action="store_true", help="rewrite only the derived receipt after hermetic validation")
    parser.add_argument("--bootstrap-capture", type=Path)
    parser.add_argument("--compiled-artifact", type=Path)
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--engine-root", type=Path, default=DEFAULT_ENGINE_ROOT)
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE_BINARY)
    args = parser.parse_args(argv)
    try:
        if args.bootstrap_capture:
            _require(args.compiled_artifact is not None, "--bootstrap-capture requires --compiled-artifact")
            _bootstrap_capture(args.bootstrap_capture, args.compiled_artifact)
        committed = _load(RECEIPT_PATH)
        summary = validate_artifact(committed)
        if args.refresh_receipt:
            RECEIPT_PATH.write_text(_render(_receipt_document(summary)))
            committed = _load(RECEIPT_PATH)
            validate_artifact(committed)
        if args.live:
            _artifact, transcript, receipt = _live_reproduction(
                rulespec_root=args.rulespec_root,
                engine_root=args.engine_root,
                engine_binary=args.engine_binary,
            )
            _require(_render(transcript) == TRANSCRIPT_PATH.read_text(), "fresh execution transcript drifted")
            _require(receipt == committed, "fresh executable receipt drifted")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"NZ executable ERROR: {exc}", file=sys.stderr)
        return 1
    if args.check:
        mode = "live compile+execute" if args.live else "hermetic artifact/transcript"
        print(
            f"NZ executable receipt OK ({mode}): {summary['request_count']} requests, "
            f"{summary['comparison_cell_count']} declared comparison cells"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
