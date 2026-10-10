#!/usr/bin/env python3
"""Build the unified DE worker comparison record used by DE certificates.

The historical DE report is a complete EUROMOD x GETTSIM run, but its legacy
mismatch chunks are not bound to that report and contain no matched output
rows.  This producer therefore re-derives a single, content-addressed
population record from the report's inline cases and the canonical suite.  It
does not manufacture Axiom results: the two Axiom comparison legs required by
the Kindergeld amount-subgraph view remain explicit pending slots until
separate, fully bound records are committed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.core.case import Concepts  # noqa: E402
from axiom_oracles.suites.de_worker import (  # noqa: E402
    DE_WORKER_PERIOD,
    de_worker_dual_oracle_cases,
)

SOURCE_PATH = (
    REPO_ROOT
    / "dashboard"
    / "public"
    / "data"
    / "euromod-gettsim-de-worker-dual-oracle.json"
)
OUTPUT_PATH = (
    REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "unified-record.json"
)

RECORD_SCHEMA = "axiom.unified_comparison_record.v1"
EXPERIMENT_SCHEMA = "axiom.experiment_boundary_receipt.v1"
SUITE = "de-worker-dual-oracle"
PROGRAM = "de/kindergeld"
KINDERGELD_CONCEPT = Concepts.DE_KINDERGELD_MONTHLY
AMOUNT_ROOT_NODE = "de:statutes/estg/66#monthly_kindergeld_per_child"
EXPECTED_HOUSEHOLD_SUM = 765
AXIOM_LEG_PATHS = {
    "axiom-euromod": (
        REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "axiom-euromod.json"
    ),
    "axiom-gettsim": (
        REPO_ROOT / "comparisons" / "de-worker-dual-oracle" / "axiom-gettsim.json"
    ),
}
AXIOM_LEG_SUITES = {
    "axiom-euromod": "de-worker-dual-oracle-axiom-euromod",
    "axiom-gettsim": "de-worker-dual-oracle-axiom-gettsim",
}
AXIOM_LEG_PRODUCER = "scripts/de_executable.py::produce"
ORACLE_TARGETS = {
    "euromod": "bch00_s",
    "gettsim": "kindergeld.betrag_m",
}
ORACLE_PINS = {
    "euromod": {
        "release": "J2.0+",
        "system": "DE_2025",
        "metadata_claim_mode": "attested",
    },
    "gettsim": {
        "version": "1.2.1",
        "policy_date": "2025-06-30",
        "metadata_claim_mode": "attested",
    },
}
AXIOM_ENGINE_PIN = {
    "id": "axiom",
    "release": "v0.2.2",
    "commit": "2c0e1edac0dccc355297eb9663e0aa0c4e97e5b4",
    "asset_sha256": (
        "76565685230d64edf33e4205f01f77c57ef341ba2d3cf75dc967fc12c883f1f4"
    ),
    "metadata_claim_mode": "attested",
}
RULESPEC_REF_PIN = {
    "commit": "d83ba3db30e2f63376aacf822d116687589b8564",
    "tree": "1e75a045e32100544f057ffe335065c1ef99c1bc",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DERecordError(ValueError):
    """The committed DE evidence does not support the generated claim."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        try:
            label = path.relative_to(REPO_ROOT)
        except ValueError:
            label = path
        raise DERecordError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DERecordError(f"{path.name} must contain a JSON object")
    return value


def _number(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DERecordError(f"{label} must be numeric")
    return value


def _source_cases(report: dict) -> list[dict]:
    rows = report.get("cases")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise DERecordError("source report cases must be an array of objects")
    canonical = de_worker_dual_oracle_cases()
    if len(rows) != len(canonical) or len(rows) != 13:
        raise DERecordError(
            f"DE worker population must contain 13 inline cases, found {len(rows)}"
        )

    output: list[dict] = []
    seen: set[str] = set()
    for source, case in zip(rows, canonical, strict=True):
        case_id = str(source.get("case_id", ""))
        if case_id != str(case.case_id):
            raise DERecordError(
                f"source/canonical case order differs: {case_id!r} != {case.case_id!r}"
            )
        if case_id in seen:
            raise DERecordError(f"duplicate source case id {case_id!r}")
        seen.add(case_id)
        if (
            source.get("left_engine") != "euromod"
            or source.get("right_engine") != "gettsim"
        ):
            raise DERecordError(f"{case_id}: source case engine labels changed")
        if source.get("left_errors") or source.get("right_errors"):
            raise DERecordError(
                f"{case_id}: source engine error prevents comparison use"
            )
        metadata = source.get("metadata")
        if not isinstance(metadata, dict):
            raise DERecordError(f"{case_id}: source metadata must be an object")
        child_birth_years = case.metadata.get("child_birth_years")
        if metadata.get("child_birth_years") != child_birth_years:
            raise DERecordError(
                f"{case_id}: source child inputs differ from canonical suite"
            )
        expected_income = sum(
            float(entity.fact(Concepts.YEARLY_EARNED_INCOME, 0))
            for entity in case.entities
        )
        source_income = _number(
            metadata.get("yearly_earned_income"),
            f"{case_id}.metadata.yearly_earned_income",
        )
        household = metadata.get("household_summary")
        if not isinstance(household, dict):
            raise DERecordError(f"{case_id}: household_summary must be an object")
        household_income = _number(
            household.get("yearly_earned_income_total"),
            f"{case_id}.household_summary.yearly_earned_income_total",
        )
        if (
            float(source_income) != expected_income
            or float(household_income) != expected_income
        ):
            raise DERecordError(
                f"{case_id}: source income differs from canonical suite"
            )
        output.append(
            {
                "case_id": case_id,
                "metadata": {
                    "child_count": len(child_birth_years),
                    "yearly_earned_income_total": int(expected_income),
                },
                "source_case_claim_mode": "computed",
            }
        )
    return output


def _kindergeld_aggregate(report: dict) -> dict:
    aggregates = report.get("aggregates")
    if not isinstance(aggregates, list):
        raise DERecordError("source report aggregates must be an array")
    rows = [
        row
        for row in aggregates
        if isinstance(row, dict) and row.get("concept") == KINDERGELD_CONCEPT
    ]
    if len(rows) != 1:
        raise DERecordError(
            f"expected exactly one Kindergeld aggregate, found {len(rows)}"
        )
    row = rows[0]
    comparisons = _number(row.get("comparison_count"), "comparison_count")
    match_weight = _number(row.get("match_weight"), "match_weight")
    mismatches = _number(row.get("mismatch_count"), "mismatch_count")
    left_sum = _number(row.get("left_weighted_sum"), "left_weighted_sum")
    right_sum = _number(row.get("right_weighted_sum"), "right_weighted_sum")
    zero_fields = (
        "mismatch_weight",
        "missing_both_count",
        "missing_left_count",
        "missing_right_count",
        "weighted_difference",
    )
    nonzero = [name for name in zero_fields if _number(row.get(name), name) != 0]
    if comparisons != 13 or match_weight != comparisons or mismatches != 0:
        raise DERecordError("Kindergeld aggregate is not a clean 13-of-13 comparison")
    if nonzero:
        raise DERecordError(
            f"Kindergeld aggregate has nonzero defect fields: {nonzero}"
        )
    if left_sum != right_sum:
        raise DERecordError("Kindergeld source weighted sums differ")
    if left_sum != EXPECTED_HOUSEHOLD_SUM:
        raise DERecordError(
            "Kindergeld source total changed from the certified 765 EUR population"
        )
    return {
        "concept": KINDERGELD_CONCEPT,
        "comparison": "amount",
        "comparison_count": int(comparisons),
        "match_count": int(match_weight),
        "mismatch_count": int(mismatches),
        "left_weighted_sum": left_sum,
        "right_weighted_sum": right_sum,
        "error_count": 0,
        "claim_mode": "computed",
    }


def _active_input(name: str, values: list[int]) -> dict:
    observed = sorted(set(values))
    if not observed:
        raise DERecordError(f"{name}: no observations")
    return {
        "state": "varied" if len(observed) > 1 else "constant",
        "distinct": len(observed),
        "observed_values": observed,
        "observations": len(values),
        "claim_mode": "computed",
    }


def _validate_axiom_leg(
    path: Path,
    *,
    leg_id: str,
    population_sha256: str,
    population_cases: list[dict],
    expected_oracle: dict,
    expected_household_sum: int | float,
) -> dict:
    """Validate one future Axiom x oracle record from its complete case rows."""

    report = _load_object(path)
    oracle = leg_id.removeprefix("axiom-")
    try:
        dependency_producer = importlib.import_module("scripts.de_axiom_legs")
        dependency_producer.validate_complete_views(report, oracle)
    except (ImportError, OSError, ValueError) as exc:
        raise DERecordError(
            f"{leg_id}: complete output dependency views are invalid: {exc}"
        ) from exc
    expected_suite = AXIOM_LEG_SUITES[leg_id]
    if report.get("record_schema") != RECORD_SCHEMA:
        raise DERecordError(f"{leg_id}: comparison is not a unified record")
    if report.get("suite") != expected_suite:
        raise DERecordError(f"{leg_id}: comparison suite identity changed")
    if report.get("period") != DE_WORKER_PERIOD:
        raise DERecordError(f"{leg_id}: comparison period changed")
    if report.get("engines") != {"left": oracle, "right": "axiom"}:
        raise DERecordError(f"{leg_id}: expected {oracle} x Axiom engine order")
    tuple_ = report.get("tuple")
    population = tuple_.get("population") if isinstance(tuple_, dict) else None
    if (
        not isinstance(tuple_, dict)
        or tuple_.get("jurisdiction") != "de"
        or not isinstance(population, dict)
        or population.get("sha256") != population_sha256
        or population.get("case_count") != len(population_cases)
    ):
        raise DERecordError(f"{leg_id}: population tuple is not the certified tuple")
    tuple_oracle = tuple_.get("oracle")
    if tuple_oracle != {"id": oracle, **expected_oracle}:
        raise DERecordError(f"{leg_id}: oracle tuple is not the declared oracle")
    if tuple_.get("axiom") != AXIOM_ENGINE_PIN:
        raise DERecordError(f"{leg_id}: Axiom tuple is not the pinned release")
    view = (report.get("views") or {}).get(PROGRAM)
    if (
        not isinstance(view, dict)
        or view.get("kind") != "subgraph"
        or view.get("scope") != "amount"
        or view.get("claim_mode") != "computed"
    ):
        raise DERecordError(f"{leg_id}: Kindergeld subgraph view is missing")
    if view.get("leg_id") != leg_id or view.get("state") != "complete":
        raise DERecordError(f"{leg_id}: Kindergeld leg is not declared complete")
    if view.get("root_nodes") != [AMOUNT_ROOT_NODE] or view.get("columns") != [
        KINDERGELD_CONCEPT
    ]:
        raise DERecordError(f"{leg_id}: Kindergeld view root/column changed")

    rows = report.get("cases")
    if not isinstance(rows, list) or len(rows) != len(population_cases):
        raise DERecordError(f"{leg_id}: requires all 13 comparison case rows")
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        raise DERecordError(f"{leg_id}: comparison provenance is missing")
    if provenance.get("generated_by") != AXIOM_LEG_PRODUCER:
        raise DERecordError(
            f"{leg_id}: comparison was not emitted by the live producer"
        )
    execution = provenance.get("oracle_execution")
    if not isinstance(execution, dict):
        raise DERecordError(f"{leg_id}: live oracle execution receipt is missing")
    if (
        execution.get("engine") != oracle
        or execution.get("target") != ORACLE_TARGETS[oracle]
        or execution.get("mode") != "live_no_reemit"
        or execution.get("claim_mode") != "attested"
        or execution.get("engine_identity_claim_mode") != "attested"
    ):
        raise DERecordError(f"{leg_id}: live oracle execution contract changed")
    execution_rows = execution.get("case_results")
    if not isinstance(execution_rows, list) or len(execution_rows) != len(
        population_cases
    ):
        raise DERecordError(f"{leg_id}: live oracle execution needs all 13 rows")
    execution_sha = hashlib.sha256(_canonical_bytes(execution_rows)).hexdigest()
    if execution.get("case_results_sha256") != execution_sha:
        raise DERecordError(f"{leg_id}: live oracle execution digest changed")
    if execution.get("case_results_sha256_claim_mode") != "computed":
        raise DERecordError(f"{leg_id}: live oracle execution digest is not computed")

    restatement = view.get("restatement")
    if restatement != {
        "root_node": AMOUNT_ROOT_NODE,
        "column": KINDERGELD_CONCEPT,
        "operation": "multiply_root_amount_by_canonical_child_count",
        "input_source": "canonical_de_worker_dual_oracle_cases",
        "operation_claim_mode": "attested",
        "result_claim_mode": "computed",
    }:
        raise DERecordError(f"{leg_id}: amount-subgraph restatement changed")

    matches = 0
    left_values: list[float] = []
    right_values: list[float] = []
    for expected, row, execution_row in zip(
        population_cases, rows, execution_rows, strict=True
    ):
        if not isinstance(row, dict) or row.get("case_id") != expected["case_id"]:
            raise DERecordError(f"{leg_id}: comparison case order/identity changed")
        if (
            not isinstance(execution_row, dict)
            or execution_row.get("case_id") != expected["case_id"]
        ):
            raise DERecordError(f"{leg_id}: live oracle case identity changed")
        if row.get("left_engine") != oracle or row.get("right_engine") != "axiom":
            raise DERecordError(
                f"{leg_id}: {expected['case_id']} engine labels changed"
            )
        if row.get("left_errors") or row.get("right_errors"):
            raise DERecordError(f"{leg_id}: {expected['case_id']} has an engine error")
        metadata = row.get("metadata")
        if not isinstance(metadata, dict) or any(
            metadata.get(name) != value for name, value in expected["metadata"].items()
        ):
            raise DERecordError(
                f"{leg_id}: {expected['case_id']} inputs do not bind to the population"
            )
        child_count = expected["metadata"].get("child_count")
        if isinstance(child_count, bool) or not isinstance(child_count, int):
            raise DERecordError(
                f"{leg_id}: {expected['case_id']} has an invalid child count"
            )
        match_rows = row.get("matches")
        mismatch_rows = row.get("mismatches")
        if (
            not isinstance(match_rows, list)
            or len(match_rows) != 1
            or mismatch_rows != []
            or not isinstance(match_rows[0], dict)
        ):
            raise DERecordError(
                f"{leg_id}: {expected['case_id']} needs one stored match and no mismatch"
            )
        comparison = match_rows[0]
        if comparison.get("concept") != KINDERGELD_CONCEPT:
            raise DERecordError(f"{leg_id}: {expected['case_id']} concept changed")
        left = comparison.get("left")
        right = comparison.get("right")
        executed_left = execution_row.get("value")
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or isinstance(executed_left, bool)
            or not isinstance(left, (int, float))
            or not isinstance(right, (int, float))
            or not isinstance(executed_left, (int, float))
            or not math.isfinite(float(left))
            or not math.isfinite(float(right))
            or not math.isfinite(float(executed_left))
        ):
            raise DERecordError(
                f"{leg_id}: {expected['case_id']} values are not finite"
            )
        if abs(float(left) - float(executed_left)) > 0.01:
            raise DERecordError(
                f"{leg_id}: {expected['case_id']} left value is not the live oracle result"
            )
        if abs(float(left) - float(right)) > 0.01:
            raise DERecordError(f"{leg_id}: {expected['case_id']} exceeds tolerance")
        left_values.append(float(left))
        right_values.append(float(right))
        matches += 1

    left_sum = math.fsum(left_values)
    right_sum = math.fsum(right_values)
    if (
        abs(left_sum - float(expected_household_sum)) > 0.01
        or abs(right_sum - float(expected_household_sum)) > 0.01
    ):
        raise DERecordError(
            f"{leg_id}: case totals do not reconcile to the 765 EUR source aggregate"
        )

    summary = view.get("summary")
    if not isinstance(summary, dict) or any(
        summary.get(name) != value
        for name, value in {
            "comparison_count": len(rows),
            "match_count": matches,
            "mismatch_count": 0,
            "error_count": 0,
        }.items()
    ):
        raise DERecordError(f"{leg_id}: summary does not reconcile to case rows")
    rulespec = provenance.get("rulespec_artifact")
    if not isinstance(rulespec, dict):
        raise DERecordError(f"{leg_id}: rulespec artifact binding is missing")
    if (
        rulespec.get("citation_path") != "de/statute/estg/66"
        or rulespec.get("commit") != RULESPEC_REF_PIN["commit"]
        or rulespec.get("tree") != RULESPEC_REF_PIN["tree"]
        or rulespec.get("claim_mode") != "computed"
        or any(
            not isinstance(rulespec.get(field), str)
            or not _SHA256_RE.fullmatch(rulespec[field])
            for field in ("artifact_sha256", "apply_manifest_sha256")
        )
    ):
        raise DERecordError(f"{leg_id}: rulespec artifact pins are invalid")
    return {
        "id": leg_id,
        "state": "complete",
        "artifact": path.relative_to(REPO_ROOT).as_posix(),
        "artifact_sha256": _sha256(path),
        "population_sha256": population_sha256,
        "comparison_count": len(rows),
        "match_count": matches,
        "mismatch_count": 0,
        "error_count": 0,
        "left_weighted_sum": left_sum,
        "right_weighted_sum": right_sum,
        "claim_mode": "computed",
    }


def _validate_pending_axiom_leg(
    path: Path,
    *,
    leg_id: str,
    population_sha256: str,
) -> dict:
    """Validate an explicit exact-ref pending record without inventing work."""

    report = _load_object(path)
    oracle = leg_id.removeprefix("axiom-")
    try:
        producer = importlib.import_module("scripts.de_axiom_legs")
        producer.validate(report, oracle)
    except (ImportError, OSError, ValueError) as exc:
        raise DERecordError(f"{leg_id}: invalid pending comparison record: {exc}") from exc
    tuple_ = report.get("tuple")
    population = tuple_.get("population") if isinstance(tuple_, dict) else None
    if not isinstance(population, dict) or population.get("sha256") != (
        population_sha256
    ):
        raise DERecordError(f"{leg_id}: pending population tuple changed")
    if report.get("state") != "leg-pending" or report.get("pending") != (
        "module-not-on-main"
    ):
        raise DERecordError(f"{leg_id}: pending marker changed")
    kindergeld = (report.get("views") or {}).get(PROGRAM)
    if (
        not isinstance(kindergeld, dict)
        or kindergeld.get("state") != "leg-pending"
        or kindergeld.get("pending") != "module-not-on-main"
        or kindergeld.get("dependency_set", {}).get("complete_on_pinned_ref")
        is not False
    ):
        raise DERecordError(f"{leg_id}: Kindergeld pending view changed")
    return {
        "id": leg_id,
        "state": "pending",
        "pending": "module-not-on-main",
        "artifact": path.relative_to(REPO_ROOT).as_posix(),
        "artifact_sha256": _sha256(path),
        "population_sha256": population_sha256,
        "reason": "pending: module-not-on-main",
        "claim_mode": "computed",
    }


def _axiom_legs(
    population_sha256: str,
    population_cases: list[dict],
    expected_household_sum: int | float,
    *,
    include_existing: bool = True,
) -> list[dict]:
    legs = []
    for leg_id, path in AXIOM_LEG_PATHS.items():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if include_existing and path.exists():
            observed = _load_object(path)
            if observed.get("state") == "leg-pending":
                legs.append(
                    _validate_pending_axiom_leg(
                        path,
                        leg_id=leg_id,
                        population_sha256=population_sha256,
                    )
                )
            else:
                if observed.get("state") != "complete":
                    raise DERecordError(f"{leg_id}: comparison state is invalid")
                legs.append(
                    _validate_axiom_leg(
                        path,
                        leg_id=leg_id,
                        population_sha256=population_sha256,
                        population_cases=population_cases,
                        expected_oracle=ORACLE_PINS[leg_id.removeprefix("axiom-")],
                        expected_household_sum=expected_household_sum,
                    )
                )
            continue
        legs.append(
            {
                "id": leg_id,
                "state": "pending",
                "pending": "comparison-record-absent",
                "artifact": relative,
                "population_sha256": population_sha256,
                "reason": "required Axiom comparison record is absent",
                "claim_mode": "computed",
            }
        )
    return legs


def build(*, include_axiom_legs: bool = True) -> dict:
    report = _load_object(SOURCE_PATH)
    if report.get("schema_version") != "axiom.comparison_report.v2.1":
        raise DERecordError("source report schema changed")
    if report.get("suite") != SUITE:
        raise DERecordError(f"source report does not identify suite {SUITE!r}")
    if report.get("engines") != {"left": "euromod", "right": "gettsim"}:
        raise DERecordError("source report must be the EUROMOD x GETTSIM tuple")
    if report.get("errors"):
        raise DERecordError("source report contains engine errors")

    cases = _source_cases(report)
    population_payload = {
        "id": "de-worker-dual-oracle-13-households",
        "period": DE_WORKER_PERIOD,
        "cases": cases,
    }
    population_sha256 = hashlib.sha256(_canonical_bytes(population_payload)).hexdigest()
    aggregate = _kindergeld_aggregate(report)
    child_counts = [row["metadata"]["child_count"] for row in cases]
    incomes = [row["metadata"]["yearly_earned_income_total"] for row in cases]
    source_leg = {
        "id": "euromod-gettsim",
        "state": "complete",
        "engines": ["euromod", "gettsim"],
        "comparison_count": aggregate["comparison_count"],
        "match_count": aggregate["match_count"],
        "mismatch_count": aggregate["mismatch_count"],
        "error_count": aggregate["error_count"],
        "left_weighted_sum": aggregate["left_weighted_sum"],
        "right_weighted_sum": aggregate["right_weighted_sum"],
        "claim_mode": "computed",
    }
    oracle = report.get("provenance", {}).get("oracle")
    if not isinstance(oracle, dict):
        raise DERecordError("source report lacks oracle provenance")
    observed_oracles = {
        "euromod": {
            "release": oracle.get("euromod_release"),
            "system": oracle.get("euromod_system"),
            "metadata_claim_mode": "attested",
        },
        "gettsim": {
            "version": oracle.get("gettsim_version"),
            "policy_date": oracle.get("gettsim_policy_date"),
            "metadata_claim_mode": "attested",
        },
    }
    if observed_oracles != ORACLE_PINS:
        raise DERecordError("source oracle release tuple changed")
    axiom_legs = _axiom_legs(
        population_sha256,
        cases,
        aggregate["left_weighted_sum"],
        include_existing=include_axiom_legs,
    )
    engine_metadata = report.get("engine_metadata")
    if not isinstance(engine_metadata, dict):
        raise DERecordError("source report lacks engine metadata")

    return {
        "record_schema": RECORD_SCHEMA,
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITE,
        "tuple": {
            "jurisdiction": "de",
            "population": {
                "id": population_payload["id"],
                "sha256": population_sha256,
                "case_count": len(cases),
                "claim_mode": "computed",
            },
            "oracles": ORACLE_PINS,
        },
        "period": DE_WORKER_PERIOD,
        "population": population_payload["id"],
        "dataset_identity": {
            "sha256": population_sha256,
            "claim_mode": "computed",
        },
        "engines": {"left": "euromod", "right": "gettsim"},
        "aggregates": [aggregate],
        "cases": cases,
        "mismatches": [],
        "summary": {
            "comparison_count": aggregate["comparison_count"],
            "match_count": aggregate["match_count"],
            "mismatch_count": aggregate["mismatch_count"],
            "error_count": 0,
            "claim_mode": "computed",
        },
        "experiment": {
            "schema": EXPERIMENT_SCHEMA,
            "active_inputs": {
                "child_count": _active_input("child_count", child_counts),
                "yearly_earned_income_total": _active_input(
                    "yearly_earned_income_total", incomes
                ),
            },
            "bridged_through": {},
            "claim_mode": "computed",
        },
        "views": {
            PROGRAM: {
                "kind": "subgraph",
                "scope": "amount",
                "columns": [KINDERGELD_CONCEPT],
                "root_nodes": [AMOUNT_ROOT_NODE],
                "summary": aggregate,
                "legs": [source_leg, *axiom_legs],
                "required_axiom_legs": ["axiom-euromod", "axiom-gettsim"],
                "missing_for_certification": [
                    leg["id"] for leg in axiom_legs if leg["state"] != "complete"
                ],
                "claim_mode": "computed",
            }
        },
        "provenance": {
            "generated_by": "scripts/de_unified_comparison.py",
            "source_report": {
                "artifact": SOURCE_PATH.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(SOURCE_PATH),
                "claim_mode": "computed",
            },
            "source_engine_metadata": engine_metadata,
            "source_engine_metadata_claim_mode": "attested",
            "legacy_dispositions_used": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        record = build()
    except (DERecordError, OSError, ValueError) as exc:
        print(f"DE unified comparison ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        if (
            not OUTPUT_PATH.exists()
            or OUTPUT_PATH.read_text(encoding="utf-8") != rendered
        ):
            print("DE unified comparison record drifted", file=sys.stderr)
            return 1
        print("DE unified comparison record up to date")
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
