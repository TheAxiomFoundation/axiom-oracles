#!/usr/bin/env python3
"""Verify and reproduce the NZ IncomeExplorer executable receipt.

Hermetic verification binds four independent layers: the #476 execution
trace owns the request/root evidence; canonical full engine responses own the
response hashes; the committed host reducer reconstructs every declared
RuleSpec cell; and the Treasury snapshot plus source classifications own the
expected side. ``--live`` additionally rebuilds the pinned composition and
replays every request with the pinned engine checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from nz_executable_reducer import (  # noqa: E402
    SCENARIO_ID,
    WEEKLY_WAGES,
    classify,
    decimal_text,
    reduce_states,
)

OUT_DIR = REPO_ROOT / "conformance" / "executable" / "nz-treasury-incomeexplorer"
RECEIPT_PATH = (
    REPO_ROOT / "conformance" / "executable" / "nz-treasury-incomeexplorer.json"
)
COMPOSITION_PATH = OUT_DIR / "composition.yaml"
ARTIFACT_PATH = OUT_DIR / "compiled-program.json"
REQUESTS_PATH = OUT_DIR / "requests.json"
GOLDEN_PATH = OUT_DIR / "golden-outputs.json"
FULL_RESPONSES_PATH = OUT_DIR / "full-responses.json"
TRANSCRIPT_PATH = OUT_DIR / "transcript.json"
SOURCE_REPORT_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "source-comparison.json"
)
EVALUATION_TRACE_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "evaluation-traces.json"
)
TREASURY_SNAPSHOT_PATH = (
    REPO_ROOT
    / "comparisons"
    / "nz-treasury-incomeexplorer"
    / "treasury-emtr-snapshot-expanded.json"
)
REDUCER_PATH = SCRIPTS_DIR / "nz_executable_reducer.py"

SCHEMA = "axiom_oracles.executable_reproduction.v2"
REQUEST_SCHEMA = "axiom_oracles.nz_executable_requests.v1"
GOLDEN_SCHEMA = "axiom_oracles.nz_executable_expected_comparisons.v2"
FULL_RESPONSES_SCHEMA = "axiom_oracles.nz_executable_full_responses.v1"
TRANSCRIPT_SCHEMA = "axiom_oracles.nz_executable_transcript.v2"
TRACE_SCHEMA = "axiom_oracles.nz_evaluation_traces.v1"
GENERATED_BY = "scripts/nz_executable_reproduction.py"
HARNESS = "TheAxiomFoundation/ops/nz-lane/emtr_reproduction/run.py"
HARNESS_COMMIT = "bcf631b5"
HARNESS_FULL_COMMIT = "bcf631b59968be4907e679b4704f5e029e2188ab"
HARNESS_SHA256 = "9aa0fc64af8dca4a8f7574e98923fe0022561679027c2ed5325bf381e9c6ab27"
RULESPEC_REPO = "TheAxiomFoundation/rulespec-nz"
RULESPEC_SHA = "89a7d25dc03a4d045348620283332de10b1047da"
ENGINE_REPO = "TheAxiomFoundation/axiom-rules-engine"
ENGINE_GIT_SHA = "d59969b53430ae2fd97eb4349d44ad23ce930d85"
# Historical capture provenance. A source-built Linux binary is instead bound
# by its exact Git checkout plus ``cargo build --locked`` because this digest
# names the pinned Mach-O arm64 build and cannot be cross-platform identical.
ENGINE_BINARY_SHA256 = (
    "56fbffea1e0e32c52b6fcbddbca76223bb185b33b49368c288e0c7213b0126e1"
)
COMPOSITION_SHA256 = "af2ce73f1b16a74603965db1da92991545838748e943f3ed81cef394d469c3b0"
COMPILED_SHA256 = "b1d72c1f4840a1774aefbddc9692e22a79ced26cde6c44efb4c01fc394a15c33"
EVALUATION_TRACE_SHA256 = (
    "43cca386b15e71fc07fa8fb223b2bef8d351e0bb56ecfdf05fe98e790e66f4da"
)
TREASURY_SNAPSHOT_SHA256 = (
    "6bed8c0a91e4ba6416238ef1cf381bc8033f3122f3eeb5766074d763929293fd"
)
SOURCE_REPORT_SHA256 = (
    "abd3bcbebc01c73e58c27496db5897a306bb0496ae1d53e5abbd5ae487010b3b"
)
SOURCE_COMPARISON_HARNESS = {
    "repository": "TheAxiomFoundation/ops",
    "path": "nz-lane/emtr_reproduction/run.py",
    "repository_commit": HARNESS_FULL_COMMIT,
    "repository_commit_status": "pinned",
    "sha256": HARNESS_SHA256,
}
EVALUATION_COUNT = 883
PERIOD = {"period_kind": "tax_year", "start": "2026-04-01", "end": "2027-03-31"}

DEFAULT_RULESPEC_ROOT = (
    Path("/Users/maxghenis/TheAxiomFoundation/_axiom-worktrees/")
    / "rulespec-nz-emtr/rulespec-nz"
)
DEFAULT_ENGINE_ROOT = Path(
    "/Users/maxghenis/TheAxiomFoundation/_worktrees/engine-release-clone"
)
DEFAULT_ENGINE_BINARY = DEFAULT_ENGINE_ROOT / "target/release/axiom-rules-engine"

# This mapping is declaration-side comparison scope only. Request/root
# ownership is derived exclusively from evaluation-traces.json.
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
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _render(value: Any) -> str:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


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


def _decimal(value: Any, *, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a decimal") from exc


def _request_outputs(request: Mapping[str, Any], *, label: str) -> list[str]:
    _require(request.get("mode") == "explain", f"{label}: mode must be explain")
    queries = request.get("queries")
    _require(
        isinstance(queries, list) and len(queries) == 1, f"{label}: one query required"
    )
    query = queries[0]
    _require(isinstance(query, dict), f"{label}: query must be an object")
    _require(query.get("period") == PERIOD, f"{label}: tax-year period drifted")
    outputs = query.get("outputs")
    _require(
        isinstance(outputs, list)
        and bool(outputs)
        and outputs == list(dict.fromkeys(outputs))
        and all(isinstance(output, str) and output for output in outputs),
        f"{label}: outputs must be unique non-empty strings",
    )
    return outputs


def _trace_index() -> tuple[dict[bytes, Mapping[str, Any]], dict[str, list[str]]]:
    _require(
        _sha256(EVALUATION_TRACE_PATH) == EVALUATION_TRACE_SHA256,
        "committed #476 evaluation trace bytes drifted",
    )
    trace = _load(EVALUATION_TRACE_PATH)
    _require(trace.get("schema") == TRACE_SCHEMA, "unexpected evaluation trace schema")
    _require(
        trace.get("suite") == "nz-treasury-incomeexplorer",
        "evaluation trace suite drifted",
    )
    _require(
        trace.get("rulespec_commit") == RULESPEC_SHA,
        "evaluation trace RuleSpec pin drifted",
    )
    _require(
        trace.get("engine")
        == {"binary_sha256": ENGINE_BINARY_SHA256, "git_sha": ENGINE_GIT_SHA},
        "evaluation trace engine pin drifted",
    )
    compiled = trace.get("compiled_program") or {}
    _require(
        compiled.get("artifact_sha256") == COMPILED_SHA256, "trace artifact pin drifted"
    )
    evaluations = trace.get("evaluations")
    _require(
        isinstance(evaluations, list)
        and trace.get("evaluation_count") == len(evaluations) == EVALUATION_COUNT,
        "evaluation trace must contain exactly 883 evaluations",
    )
    capture = trace.get("capture") or {}
    harness = capture.get("source_harness") or {}
    _require(
        harness.get("repository") == "TheAxiomFoundation/ops"
        and harness.get("path") == "nz-lane/emtr_reproduction/run.py"
        and harness.get("repository_commit") == HARNESS_FULL_COMMIT,
        "evaluation trace harness pin drifted",
    )

    index: dict[bytes, Mapping[str, Any]] = {}
    roots: dict[str, set[str]] = {}
    for position, evaluation in enumerate(evaluations, start=1):
        label = f"evaluation trace row {position - 1}"
        _require(isinstance(evaluation, dict), f"{label} must be an object")
        _require(
            evaluation.get("evaluation_id") == f"nz-ie-eval-{position:04d}",
            f"{label} id/order drifted",
        )
        view = evaluation.get("view")
        _require(isinstance(view, str) and bool(view), f"{label} has no emitted view")
        request = evaluation.get("request")
        _require(isinstance(request, dict), f"{label} request is missing")
        outputs = _request_outputs(request, label=label)
        _require(
            evaluation.get("requested_output_roots") == outputs,
            f"{label} requested roots differ from query outputs",
        )
        query = request["queries"][0]
        response = evaluation.get("response")
        _require(isinstance(response, dict), f"{label} response is missing")
        _require(
            response.get("metadata")
            == {"actual_mode": "explain", "requested_mode": "explain"}
            and response.get("entity_id") == query.get("entity_id")
            and response.get("period") == PERIOD
            and isinstance(response.get("outputs"), dict)
            and set(response["outputs"]) == set(outputs),
            f"{label} response does not biject the request",
        )
        key = _canonical(request)
        _require(key not in index, f"{label} duplicates a canonical execution request")
        index[key] = evaluation
        roots.setdefault(view, set()).update(outputs)
    return index, {view: sorted(values) for view, values in sorted(roots.items())}


def _validate_requests(document: Mapping[str, Any]) -> dict[str, Any]:
    _require(document.get("schema") == REQUEST_SCHEMA, "unexpected request schema")
    provenance = document.get("provenance")
    _require(isinstance(provenance, dict), "request provenance must be an object")
    _require(provenance.get("harness") == HARNESS, "request harness path drifted")
    _require(
        provenance.get("harness_commit") == HARNESS_COMMIT,
        "request harness commit drifted",
    )
    _require(
        provenance.get("rulespec_commit") == RULESPEC_SHA,
        "request RuleSpec pin drifted",
    )
    _require(
        provenance.get("engine_git_sha") == ENGINE_GIT_SHA,
        "request engine Git pin drifted",
    )
    _require(
        provenance.get("engine_binary_sha256") == ENGINE_BINARY_SHA256,
        "request historical engine binary pin drifted",
    )
    _require(
        provenance.get("compiled_sha256") == COMPILED_SHA256,
        "request artifact pin drifted",
    )
    _require(
        document.get("comparison_subset")
        == {
            "scenario_id": SCENARIO_ID,
            "weekly_wages": list(WEEKLY_WAGES),
            "comparison_columns": sorted(COLUMN_PROGRAM),
            "comparison_cell_count": len(WEEKLY_WAGES) * len(COLUMN_PROGRAM),
            "full_comparison_cell_count": 1976,
        },
        "request comparison subset drifted",
    )

    trace_index, trace_roots = _trace_index()
    rows = document.get("requests")
    _require(isinstance(rows, list) and bool(rows), "request set must be non-empty")
    seen: set[str] = set()
    selected_roots: dict[str, set[str]] = {}
    matched: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        _require(isinstance(row, dict), "request row must be an object")
        request_id = row.get("id")
        _require(
            isinstance(request_id, str) and bool(request_id), "request id is missing"
        )
        _require(request_id not in seen, f"duplicate request id {request_id}")
        seen.add(request_id)
        request = row.get("request")
        _require(isinstance(request, dict), f"{request_id}: request must be an object")
        outputs = _request_outputs(request, label=request_id)
        evaluation = trace_index.get(_canonical(request))
        _require(
            evaluation is not None,
            f"{request_id}: request/root is absent from the committed #476 evaluation trace",
        )
        view = evaluation["view"]
        _require(
            row.get("program") == view,
            f"{request_id}: program differs from trace-emitted view",
        )
        _require(
            evaluation.get("requested_output_roots") == outputs,
            f"{request_id}: roots differ from the matched trace evaluation",
        )
        selected_roots.setdefault(view, set()).update(outputs)
        matched[request_id] = evaluation
    selected = {view: sorted(values) for view, values in sorted(selected_roots.items())}
    _require(
        selected == trace_roots,
        "committed requests do not cover the trace-derived root set",
    )
    _require(
        document.get("requested_outputs_by_program") == trace_roots,
        "requested-output summary is not derived from the #476 execution trace",
    )
    return {"roots": trace_roots, "matched_evaluations": matched, "rows": rows}


def _source_and_expected_cells() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _require(
        _sha256(SOURCE_REPORT_PATH) == SOURCE_REPORT_SHA256,
        "committed source comparison bytes drifted",
    )
    _require(
        _sha256(TREASURY_SNAPSHOT_PATH) == TREASURY_SNAPSHOT_SHA256,
        "committed Treasury snapshot bytes drifted",
    )
    report = _load(SOURCE_REPORT_PATH)
    snapshot = _load(TREASURY_SNAPSHOT_PATH)
    provenance = report.get("provenance") or {}
    _require(
        provenance.get("source_comparison_harness") == SOURCE_COMPARISON_HARNESS,
        "source comparison harness provenance drifted",
    )
    _require(
        provenance.get("oracle_snapshot")
        == {
            "generated_at": "2026-07-29",
            "path": str(TREASURY_SNAPSHOT_PATH.relative_to(REPO_ROOT)),
            "sha256": TREASURY_SNAPSHOT_SHA256,
        },
        "source comparison Treasury snapshot pin drifted",
    )
    rulespec = provenance.get("rulespec") or {}
    _require(
        rulespec.get("expected_git_sha") == rulespec.get("git_sha") == RULESPEC_SHA,
        "source comparison RuleSpec pin drifted",
    )

    scenarios = snapshot.get("scenarios")
    _require(isinstance(scenarios, list), "Treasury snapshot scenarios must be a list")
    target_scenarios = [
        row
        for row in scenarios
        if isinstance(row, dict) and row.get("id") == SCENARIO_ID
    ]
    _require(
        len(target_scenarios) == 1,
        "Treasury snapshot target scenario is missing or duplicated",
    )
    sampled = target_scenarios[0].get("sampled_outputs")
    _require(
        isinstance(sampled, list), "Treasury target scenario has no sampled outputs"
    )
    treasury_by_wage = {
        int(row["gross_wage1"]): row
        for row in sampled
        if isinstance(row, dict) and row.get("gross_wage1") in WEEKLY_WAGES
    }
    _require(
        set(treasury_by_wage) == set(WEEKLY_WAGES),
        "Treasury selected wages are missing",
    )

    wanted = {
        (SCENARIO_ID, wage, column): COLUMN_PROGRAM[column]
        for wage in WEEKLY_WAGES
        for column in COLUMN_PROGRAM
    }
    source_rows: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for row in report.get("comparisons") or []:
        if not isinstance(row, dict):
            continue
        key = (row.get("scenario_id"), row.get("weekly_wage"), row.get("column"))
        if key in wanted:
            _require(
                key not in source_rows,
                f"source comparison duplicates declared cell {key}",
            )
            source_rows[key] = row
    _require(
        set(source_rows) == set(wanted),
        "source comparison declared cell key set drifted",
    )

    cells = []
    for key in sorted(wanted):
        scenario_id, wage, column = key
        source = source_rows[key]
        treasury = _decimal(treasury_by_wage[wage].get(column), label=f"Treasury {key}")
        source_treasury = _decimal(
            source.get("treasury"), label=f"source Treasury {key}"
        )
        _require(
            treasury == source_treasury,
            f"{key}: source Treasury value differs from snapshot",
        )
        declared = source.get("rulespec")
        _require(
            isinstance(declared, str),
            f"{key}: declared RuleSpec value must be decimal text",
        )
        _decimal(declared, label=f"declared RuleSpec {key}")
        classification = source.get("classification")
        reason_code = source.get("reason_code")
        _require(
            isinstance(classification, str)
            and bool(classification)
            and isinstance(reason_code, str)
            and bool(reason_code),
            f"{key}: source classification is incomplete",
        )
        cells.append(
            {
                "scenario_id": scenario_id,
                "weekly_wage": wage,
                "column": column,
                "program": wanted[key],
                "unit": source.get("unit"),
                "treasury_value": decimal_text(treasury),
                "declared_rulespec_value": declared,
                "expected_classification": classification,
                "expected_reason_code": reason_code,
            }
        )
    return report, cells


def _expected_document(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema": GOLDEN_SCHEMA,
        "treasury_snapshot": {
            "path": str(TREASURY_SNAPSHOT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(TREASURY_SNAPSHOT_PATH),
        },
        "source_classifications": {
            "path": str(SOURCE_REPORT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(SOURCE_REPORT_PATH),
        },
        "comparison_cells": list(cells),
    }


def _validate_golden(
    document: Mapping[str, Any], cells: Sequence[Mapping[str, Any]]
) -> None:
    _require(
        document == _expected_document(cells),
        "expected comparison evidence is not derived from Treasury and source classifications",
    )


def _response_projection(
    response: Mapping[str, Any], *, request_id: str
) -> dict[str, Any]:
    metadata = response.get("metadata")
    results = response.get("results")
    _require(isinstance(metadata, dict), f"{request_id}: response metadata missing")
    _require(
        isinstance(results, list) and len(results) == 1,
        f"{request_id}: engine returned != 1 result",
    )
    result = results[0]
    _require(isinstance(result, dict), f"{request_id}: result must be an object")
    _require(
        isinstance(result.get("trace"), dict),
        f"{request_id}: canonical full trace missing",
    )
    return {
        "entity_id": result.get("entity_id"),
        "period": result.get("period"),
        "outputs": result.get("outputs"),
        "metadata": {
            "actual_mode": metadata.get("actual_mode"),
            "requested_mode": metadata.get("requested_mode"),
        },
    }


def _full_responses_document(
    requests: Mapping[str, Any], responses: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    request_rows = requests["requests"]
    _require(len(responses) == len(request_rows), "engine response cardinality drifted")
    return {
        "schema": FULL_RESPONSES_SCHEMA,
        "requests": [
            {
                "id": request_row["id"],
                "program": request_row["program"],
                "request_sha256": _sha256_bytes(_canonical(request_row["request"])),
                "response_sha256": _sha256_bytes(_canonical(response)),
                "response": response,
            }
            for request_row, response in zip(request_rows, responses, strict=True)
        ],
    }


def _validate_full_responses(
    document: Mapping[str, Any],
    requests: Mapping[str, Any],
    request_context: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    _require(
        document.get("schema") == FULL_RESPONSES_SCHEMA,
        "unexpected full-response schema",
    )
    rows = document.get("requests")
    request_rows = requests["requests"]
    _require(
        isinstance(rows, list) and len(rows) == len(request_rows),
        "full-response cardinality drifted",
    )
    by_id: dict[str, Mapping[str, Any]] = {}
    matched = request_context["matched_evaluations"]
    for row, request_row in zip(rows, request_rows, strict=True):
        request_id = request_row["id"]
        _require(
            isinstance(row, dict) and row.get("id") == request_id,
            f"full-response order/id drifted at {request_id}",
        )
        _require(
            row.get("program") == request_row["program"],
            f"{request_id}: response program drifted",
        )
        request_hash = _sha256_bytes(_canonical(request_row["request"]))
        _require(
            row.get("request_sha256") == request_hash,
            f"{request_id}: response request hash drifted",
        )
        response = row.get("response")
        _require(isinstance(response, dict), f"{request_id}: full response is missing")
        _require(
            row.get("response_sha256") == _sha256_bytes(_canonical(response)),
            f"{request_id}: response_sha256 is not derived from full response bytes",
        )
        projection = _response_projection(response, request_id=request_id)
        _require(
            projection == matched[request_id].get("response"),
            f"{request_id}: full response projection differs from the #476 execution trace",
        )
        expected_outputs = set(request_row["request"]["queries"][0]["outputs"])
        _require(
            isinstance(projection["outputs"], dict)
            and set(projection["outputs"]) == expected_outputs,
            f"{request_id}: full response output keys drifted",
        )
        by_id[request_id] = response
    return by_id


def _comparison_rows(
    responses_by_id: Mapping[str, Mapping[str, Any]],
    expected_cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    states = reduce_states(responses_by_id)
    treasury_states: dict[int, dict[str, Decimal]] = {wage: {} for wage in WEEKLY_WAGES}
    for cell in expected_cells:
        treasury_states[cell["weekly_wage"]][cell["column"]] = _decimal(
            cell["treasury_value"], label="Treasury expected value"
        )
    rows = []
    for expected in expected_cells:
        wage = expected["weekly_wage"]
        column = expected["column"]
        value = states[wage][column]
        classification, reason_code = classify(
            column=column,
            wage=wage,
            treasury_state=treasury_states[wage],
            rulespec_states=states,
        )
        declared_match = value == _decimal(
            expected["declared_rulespec_value"], label="declared RuleSpec value"
        )
        classification_match = (
            classification == expected["expected_classification"]
            and reason_code == expected["expected_reason_code"]
        )
        rows.append(
            {
                **expected,
                "rulespec_value": decimal_text(value),
                "classification": classification,
                "reason_code": reason_code,
                "declared_rulespec_match": declared_match,
                "classification_match": classification_match,
                "independent_match": declared_match and classification_match,
            }
        )
    return rows


def _transcript_document(
    requests: Mapping[str, Any],
    full_responses: Mapping[str, Any],
    responses_by_id: Mapping[str, Mapping[str, Any]],
    expected_cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": TRANSCRIPT_SCHEMA,
        "requests": [
            {
                "id": row["id"],
                "program": row["program"],
                "request_sha256": row["request_sha256"],
                "response_sha256": row["response_sha256"],
                "trace_projection_match": True,
            }
            for row in full_responses["requests"]
        ],
        "comparison_cells": _comparison_rows(responses_by_id, expected_cells),
    }


def _summary(
    transcript: Mapping[str, Any], roots: Mapping[str, list[str]]
) -> dict[str, Any]:
    request_rows = transcript["requests"]
    cells = transcript["comparison_cells"]
    programs: dict[str, dict[str, Any]] = {}
    for program in sorted(roots):
        program_cells = [cell for cell in cells if cell["program"] == program]
        request_matches = all(
            row["trace_projection_match"]
            for row in request_rows
            if row["program"] == program
        )
        cell_matches = bool(program_cells) and all(
            cell["independent_match"] for cell in program_cells
        )
        programs[program] = {
            "request_count": sum(row["program"] == program for row in request_rows),
            "requested_root_count": len(roots[program]),
            "comparison_cell_count": len(program_cells),
            "all_trace_responses_reproduced": request_matches,
            "all_independent_cells_reproduced": cell_matches,
            "executable": request_matches and cell_matches,
        }
    return {
        "program_count": len(programs),
        "request_count": len(request_rows),
        "response_count": len(request_rows),
        "comparison_cell_count": len(cells),
        "all_trace_responses_reproduced": all(
            row["trace_projection_match"] for row in request_rows
        ),
        "all_independent_cells_reproduced": all(
            cell["independent_match"] for cell in cells
        ),
        "programs": programs,
        "executable": all(row["executable"] for row in programs.values()),
    }


def _validate_transcript(
    document: Mapping[str, Any],
    requests: Mapping[str, Any],
    full_responses: Mapping[str, Any],
    responses_by_id: Mapping[str, Mapping[str, Any]],
    expected_cells: Sequence[Mapping[str, Any]],
    roots: Mapping[str, list[str]],
) -> dict[str, Any]:
    expected = _transcript_document(
        requests, full_responses, responses_by_id, expected_cells
    )
    _require(
        document == expected,
        "transcript is not derived from full responses and independent evidence",
    )
    summary = _summary(expected, roots)
    _require(
        summary["all_trace_responses_reproduced"],
        "one or more committed responses differ from the #476 execution trace",
    )
    _require(
        summary["all_independent_cells_reproduced"],
        "fresh reduced cells differ from declared values or independent classifications",
    )
    return summary


def _history_note(message: str) -> None:
    print(
        f"NZ executable NOTE: {message}; ancestor denominator check failed open",
        file=sys.stderr,
    )


def _git_history(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _history_revisions() -> dict[str, str]:
    revisions: dict[str, str] = {"committed HEAD": "HEAD"}
    seen = {"HEAD"}
    parents = _git_history("rev-list", "--parents", "--max-count=1", "HEAD")
    if parents.returncode == 0:
        for parent in parents.stdout.split()[1:]:
            if parent not in seen:
                revisions[f"strict HEAD parent {parent}"] = parent
                seen.add(parent)

    # GitHub checks pull requests out at a synthetic merge commit. Its feature
    # parent already contains the proposed denominator bytes, while the base
    # parent may predate this evidence entirely. Direct-parent comparison alone
    # would therefore accept a deletion committed on the feature branch. Walk
    # every path-changing strict ancestor so the last larger request/cell set
    # remains an immutable floor through the synthetic merge layer.
    request_relative = REQUESTS_PATH.relative_to(REPO_ROOT).as_posix()
    golden_relative = GOLDEN_PATH.relative_to(REPO_ROOT).as_posix()
    strict_history = _git_history(
        "rev-list",
        "--full-history",
        "HEAD^@",
        "--",
        request_relative,
        golden_relative,
    )
    if strict_history.returncode == 0:
        for revision in strict_history.stdout.splitlines():
            revision = revision.strip()
            if revision and revision not in seen:
                revisions[f"strict path ancestor {revision}"] = revision
                seen.add(revision)
    else:
        _history_note(
            strict_history.stderr.strip()
            or "strict request/cell denominator history is unavailable"
        )

    merge_base = _git_history("merge-base", "HEAD", "origin/main")
    if merge_base.returncode == 0 and merge_base.stdout.strip():
        revision = merge_base.stdout.strip()
        if revision not in seen:
            revisions[f"origin/main merge-base {revision}"] = revision
    else:
        _history_note(
            merge_base.stderr.strip() or "origin/main or its merge-base is unavailable"
        )
    return revisions


def _json_at(revision: str, path: Path) -> dict[str, Any] | None:
    relative = path.relative_to(REPO_ROOT).as_posix()
    shown = _git_history("show", f"{revision}:{relative}")
    if shown.returncode:
        return None
    try:
        value = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ancestor {revision}:{relative} is invalid JSON") from exc
    _require(
        isinstance(value, dict), f"ancestor {revision}:{relative} must be an object"
    )
    return value


def _request_keys(document: Mapping[str, Any]) -> set[tuple[str, str]]:
    rows = document.get("requests")
    _require(isinstance(rows, list), "request denominator has no rows")
    keys: set[tuple[str, str]] = set()
    for row in rows:
        _require(isinstance(row, dict), "request denominator row must be an object")
        request_id = row.get("id")
        request = row.get("request")
        _require(
            isinstance(request_id, str) and isinstance(request, dict),
            "request denominator key is invalid",
        )
        keys.add((request_id, _sha256_bytes(_canonical(request))))
    _require(len(keys) == len(rows), "request denominator keys are not unique")
    return keys


def _cell_keys(document: Mapping[str, Any]) -> set[tuple[str, int, str, str]]:
    cells = document.get("comparison_cells")
    _require(isinstance(cells, list), "comparison denominator has no cells")
    keys: set[tuple[str, int, str, str]] = set()
    for cell in cells:
        _require(
            isinstance(cell, dict), "comparison denominator cell must be an object"
        )
        key = (
            cell.get("scenario_id"),
            cell.get("weekly_wage"),
            cell.get("column"),
            cell.get("program"),
        )
        _require(
            isinstance(key[0], str)
            and isinstance(key[1], int)
            and not isinstance(key[1], bool)
            and isinstance(key[2], str)
            and isinstance(key[3], str),
            "comparison denominator key is invalid",
        )
        keys.add(key)
    _require(len(keys) == len(cells), "comparison denominator keys are not unique")
    return keys


def _validate_ancestor_denominators(
    requests: Mapping[str, Any],
    expected_document: Mapping[str, Any],
    *,
    ancestor_documents: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]]
    | None = None,
) -> None:
    if ancestor_documents is None:
        loaded: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
        for label, revision in _history_revisions().items():
            prior_requests = _json_at(revision, REQUESTS_PATH)
            prior_cells = _json_at(revision, GOLDEN_PATH)
            if prior_requests is not None and prior_cells is not None:
                loaded[label] = (prior_requests, prior_cells)
        ancestor_documents = loaded
    current_request_keys = _request_keys(requests)
    current_cell_keys = _cell_keys(expected_document)
    for label, (prior_requests, prior_cells) in ancestor_documents.items():
        prior_request_keys = _request_keys(prior_requests)
        prior_cell_keys = _cell_keys(prior_cells)
        _require(
            len(current_request_keys) >= len(prior_request_keys),
            f"ancestor-monotone request count regressed below {label}",
        )
        _require(
            prior_request_keys.issubset(current_request_keys),
            f"ancestor-protected exact request key set changed relative to {label}",
        )
        _require(
            len(current_cell_keys) >= len(prior_cell_keys),
            f"ancestor-monotone comparison cell count regressed below {label}",
        )
        _require(
            prior_cell_keys.issubset(current_cell_keys),
            f"ancestor-protected exact comparison key set changed relative to {label}",
        )


def _receipt_document(summary: Mapping[str, Any]) -> dict[str, Any]:
    report = _load(SOURCE_REPORT_PATH)
    return {
        "schema": SCHEMA,
        "program": "nz/treasury-incomeexplorer-comparison-composition",
        "programs": sorted(summary["programs"]),
        "generated_by": GENERATED_BY,
        "execution_period": "2026-04-01/2027-03-31",
        "engine": {
            "repository": ENGINE_REPO,
            "git_sha": ENGINE_GIT_SHA,
            "historical_capture_binary_sha256": ENGINE_BINARY_SHA256,
            "ci_replay_build": "cargo build --locked --release --bin axiom-rules-engine",
        },
        "rulespec": {"repository": RULESPEC_REPO, "sha": RULESPEC_SHA},
        "source_report": {
            "path": str(SOURCE_REPORT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(SOURCE_REPORT_PATH),
            "compiled_artifact_sha256": (report.get("compiled_program") or {}).get(
                "artifact_sha256"
            ),
        },
        "execution_trace": {
            "path": str(EVALUATION_TRACE_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(EVALUATION_TRACE_PATH),
            "evaluation_count": EVALUATION_COUNT,
        },
        "treasury_snapshot": {
            "path": str(TREASURY_SNAPSHOT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(TREASURY_SNAPSHOT_PATH),
        },
        "reducer": {
            "path": str(REDUCER_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(REDUCER_PATH),
            "source": f"{HARNESS}@{HARNESS_FULL_COMMIT}",
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
        "independent_expected": {
            "path": str(GOLDEN_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(GOLDEN_PATH),
        },
        "full_responses": {
            "path": str(FULL_RESPONSES_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(FULL_RESPONSES_PATH),
        },
        "transcript": {
            "path": str(TRANSCRIPT_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(TRANSCRIPT_PATH),
        },
        "summary": summary,
    }


def _validate_source_and_artifact_pins() -> None:
    report = _load(SOURCE_REPORT_PATH)
    provenance = report.get("provenance") or {}
    engine = provenance.get("engine") or {}
    compiled = report.get("compiled_program") or {}
    _require(
        engine.get("expected_git_sha") == ENGINE_GIT_SHA,
        "source report engine Git pin drifted",
    )
    _require(
        engine.get("binary_sha256") == ENGINE_BINARY_SHA256,
        "source report historical binary pin drifted",
    )
    _require(
        compiled.get("artifact_sha256") == COMPILED_SHA256,
        "source report compiled digest drifted",
    )
    _require(
        _sha256(COMPOSITION_PATH) == COMPOSITION_SHA256,
        "committed composition bytes drifted",
    )
    _require(
        _sha256(ARTIFACT_PATH) == COMPILED_SHA256,
        "committed compiled artifact bytes drifted",
    )


def _derive_committed() -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_source_and_artifact_pins()
    requests = _load(REQUESTS_PATH)
    request_context = _validate_requests(requests)
    _report, expected_cells = _source_and_expected_cells()
    expected_document = _expected_document(expected_cells)
    golden = _load(GOLDEN_PATH)
    _validate_golden(golden, expected_cells)
    _validate_ancestor_denominators(requests, expected_document)
    full_responses = _load(FULL_RESPONSES_PATH)
    responses_by_id = _validate_full_responses(
        full_responses, requests, request_context
    )
    transcript = _load(TRANSCRIPT_PATH)
    summary = _validate_transcript(
        transcript,
        requests,
        full_responses,
        responses_by_id,
        expected_cells,
        request_context["roots"],
    )
    return summary, _receipt_document(summary)


def validate_artifact(
    document: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Hermetically validate receipt bytes and rederive executable values."""

    _require(
        Path(repo_root).resolve() == REPO_ROOT.resolve(),
        "NZ receipt must validate at repository root",
    )
    _require(document.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    _require(document.get("generated_by") == GENERATED_BY, "receipt producer drifted")
    summary, expected = _derive_committed()
    _require(
        document == expected,
        "executable receipt is not derived from committed artifacts",
    )
    return summary


def _run(
    command: list[str],
    *,
    stdin: str | None = None,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd,
        env=dict(env) if env is not None else None,
    )
    if process.returncode:
        raise ValueError(
            process.stderr.strip()
            or process.stdout.strip()
            or f"command failed: {command}"
        )
    return process


def _prepare_live_engine(
    *, engine_root: Path, engine_binary: Path, source_built_engine: bool
) -> None:
    git_sha = _run(["git", "-C", str(engine_root), "rev-parse", "HEAD"]).stdout.strip()
    _require(
        git_sha == ENGINE_GIT_SHA, "engine checkout does not match the pinned Git SHA"
    )
    if source_built_engine:
        _require(
            engine_binary.name == "axiom-rules-engine",
            "source-built engine binary name drifted",
        )
        target_dir = engine_binary.parent.parent
        build_env = dict(os.environ)
        build_env["CARGO_TARGET_DIR"] = str(target_dir)
        _run(
            [
                "cargo",
                "build",
                "--locked",
                "--release",
                "--manifest-path",
                str(engine_root / "Cargo.toml"),
                "--bin",
                "axiom-rules-engine",
            ],
            cwd=engine_root,
            env=build_env,
        )
        _require(
            engine_binary.is_file(),
            f"source-built engine binary is missing: {engine_binary}",
        )
    else:
        _require(
            engine_binary.is_file(), f"pinned engine binary is missing: {engine_binary}"
        )
        _require(
            _sha256(engine_binary) == ENGINE_BINARY_SHA256,
            "engine binary bytes do not match the historical pin",
        )


def _live_reproduction(
    *,
    rulespec_root: Path,
    engine_root: Path,
    engine_binary: Path,
    source_built_engine: bool,
) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    _prepare_live_engine(
        engine_root=engine_root,
        engine_binary=engine_binary,
        source_built_engine=source_built_engine,
    )
    rulespec_sha = _run(
        ["git", "-C", str(rulespec_root), "rev-parse", "HEAD"]
    ).stdout.strip()
    _require(
        rulespec_sha == RULESPEC_SHA,
        "RuleSpec checkout does not match the pinned Git SHA",
    )
    requests = _load(REQUESTS_PATH)
    request_context = _validate_requests(requests)
    _report, expected_cells = _source_and_expected_cells()
    expected_document = _expected_document(expected_cells)
    _validate_ancestor_denominators(requests, expected_document)
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
        _require(
            _sha256_bytes(artifact_bytes) == COMPILED_SHA256,
            "fresh compiled artifact digest drifted",
        )
        _require(
            artifact_bytes == ARTIFACT_PATH.read_bytes(),
            "fresh compiled artifact is not byte-identical",
        )
        responses: list[Mapping[str, Any]] = []
        for row in requests["requests"]:
            process = _run(
                [str(engine_binary), "run-compiled", "--artifact", str(artifact)],
                stdin=json.dumps(row["request"], sort_keys=True, separators=(",", ":")),
            )
            try:
                response = json.loads(process.stdout)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{row['id']}: engine returned invalid JSON") from exc
            _require(
                isinstance(response, dict),
                f"{row['id']}: engine response is not an object",
            )
            responses.append(response)
    full_responses = _full_responses_document(requests, responses)
    responses_by_id = _validate_full_responses(
        full_responses, requests, request_context
    )
    transcript = _transcript_document(
        requests, full_responses, responses_by_id, expected_cells
    )
    summary = _validate_transcript(
        transcript,
        requests,
        full_responses,
        responses_by_id,
        expected_cells,
        request_context["roots"],
    )
    return artifact_bytes, expected_document, full_responses, transcript, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--live", action="store_true", help="recompile and execute the pinned requests"
    )
    parser.add_argument(
        "--source-built-engine",
        action="store_true",
        help="build the pinned engine checkout with cargo --locked (portable CI path)",
    )
    parser.add_argument(
        "--refresh-live-evidence",
        action="store_true",
        help="write canonical full responses, transcript, expected cells, and receipt from a live replay",
    )
    parser.add_argument(
        "--refresh-receipt",
        action="store_true",
        help="reconstruct the outer receipt from committed components without trusting the old receipt",
    )
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--engine-root", type=Path, default=DEFAULT_ENGINE_ROOT)
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE_BINARY)
    args = parser.parse_args(argv)
    try:
        _require(
            not args.check
            or not (args.refresh_live_evidence or args.refresh_receipt),
            "--check is read-only and cannot be combined with a refresh mode",
        )
        _require(
            not args.refresh_live_evidence or args.live,
            "--refresh-live-evidence requires --live",
        )
        _require(
            not args.source_built_engine or args.live,
            "--source-built-engine requires --live",
        )
        live_result = None
        if args.live:
            live_result = _live_reproduction(
                rulespec_root=args.rulespec_root,
                engine_root=args.engine_root,
                engine_binary=args.engine_binary,
                source_built_engine=args.source_built_engine,
            )

        if args.refresh_live_evidence:
            assert live_result is not None
            _artifact, expected, full_responses, transcript, live_summary = live_result
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            GOLDEN_PATH.write_text(_render(expected))
            FULL_RESPONSES_PATH.write_text(_render(full_responses))
            TRANSCRIPT_PATH.write_text(_render(transcript))
            RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            receipt = _receipt_document(live_summary)
            RECEIPT_PATH.write_text(_render(receipt))
            committed = _load(RECEIPT_PATH)
            summary = validate_artifact(committed)
        elif args.refresh_receipt:
            # Deliberately do not read or validate the old outer receipt first.
            summary, expected_receipt = _derive_committed()
            RECEIPT_PATH.write_text(_render(expected_receipt))
            committed = _load(RECEIPT_PATH)
            summary = validate_artifact(committed)
        else:
            committed = _load(RECEIPT_PATH)
            summary = validate_artifact(committed)

        if live_result is not None and not args.refresh_live_evidence:
            artifact, expected, full_responses, transcript, live_summary = live_result
            receipt = _receipt_document(live_summary)
            _require(
                artifact == ARTIFACT_PATH.read_bytes(),
                "fresh compiled artifact drifted",
            )
            _require(
                _render(expected) == GOLDEN_PATH.read_text(),
                "fresh independent expectation drifted",
            )
            _require(
                _render(full_responses) == FULL_RESPONSES_PATH.read_text(),
                "fresh full responses drifted",
            )
            _require(
                _render(transcript) == TRANSCRIPT_PATH.read_text(),
                "fresh execution transcript drifted",
            )
            _require(receipt == committed, "fresh executable receipt drifted")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"NZ executable ERROR: {exc}", file=sys.stderr)
        return 1
    if args.check:
        mode = (
            "source-build live compile+execute"
            if args.source_built_engine
            else (
                "live compile+execute"
                if args.live
                else "hermetic full-response reduction"
            )
        )
        print(
            f"NZ executable receipt OK ({mode}): {summary['request_count']} requests, "
            f"{summary['comparison_cell_count']} independently reconstructed cells"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
