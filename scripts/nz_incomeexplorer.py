#!/usr/bin/env python3
"""Build the unified NZ Treasury IncomeExplorer comparison record.

The committed source receipt is the deterministic double-run output of the
external TheAxiomFoundation/ops reproduction harness. This adapter does not
split that experiment by program: it emits one population x oracle x
jurisdiction record, with program subgraphs represented only as node views.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_FLOOR, localcontext
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from nz_programs import (  # noqa: E402
    PROGRAM_VIEWS,
    REQUESTED_OUTPUT_ROOT_SETS,
    SINGLE_PERSON_PROGRAMS,
)
from emit_case_artifacts import (  # noqa: E402
    CHUNK_SIZE,
    compact_case,
    explained_lookup,
)
from axiom_oracles.evidence import (  # noqa: E402
    build_chunk_index,
    validate_suite_evidence,
)
SOURCE_DIR = REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer"
SOURCE_PATH = SOURCE_DIR / "source-comparison.json"
SNAPSHOT_PATH = SOURCE_DIR / "treasury-emtr-snapshot-expanded.json"
CLOSURES_PATH = SOURCE_DIR / "eligibility-closures.json"
DISPOSITIONS_PATH = REPO_ROOT / "dispositions" / "nz-treasury-incomeexplorer.yaml"
OUTPUT_PATH = (
    REPO_ROOT / "dashboard" / "public" / "data" / "nz-treasury-incomeexplorer.json"
)
CASE_DIR = OUTPUT_PATH.parent / "cases" / "nz-treasury-incomeexplorer"
INDEX_PATH = CASE_DIR / "index.json"
ATTESTATION_PATH = SOURCE_DIR / "single-person-attestations.json"
TRACE_PATH = SOURCE_DIR / "evaluation-traces.json"

SCHEMA = "axiom.unified_comparison_record.v1"
SUITE = "nz-treasury-incomeexplorer"
TRACE_SCHEMA = "axiom_oracles.nz_evaluation_traces.v1"
RAW_TRACE_SCHEMA = "axiom_oracles.nz_evaluation_traces.raw.v1"
SOURCE_SHA256 = "abd3bcbebc01c73e58c27496db5897a306bb0496ae1d53e5abbd5ae487010b3b"
SNAPSHOT_SHA256 = "6bed8c0a91e4ba6416238ef1cf381bc8033f3122f3eeb5766074d763929293fd"
# The regenerated source differs from the committed source only in provenance.
# It is an external receipt, so pin its claimed bytes rather than accepting an
# arbitrary 64-character value from the trace document itself.
REGENERATED_SOURCE_SHA256 = (
    "7b58fcfdb50f8627f0228bf024d95cde3ef3d50caae7f2d9de2862d82ea6e8c6"
)
# Filled from the view-scoped trace artifact. The producer rejects even
# semantically equivalent byte drift so certificates name one exact public
# receipt. Capture lineage is explicitly attested; exercise observations are
# computed from the committed bytes.
TRACE_SHA256 = "43cca386b15e71fc07fa8fb223b2bef8d351e0bb56ecfdf05fe98e790e66f4da"
TREASURY_COMMIT = "741a6ca4f5d27b1dc00b43dc395e39ffc4040a4b"
AMOUNT_TOLERANCE = Decimal("0.005")
ATTESTATION_BASELINE_SCENARIO = "single_no_children_area2_no_housing_costs"
ATTESTATION_PERTURBED_SCENARIO = "couple_two_children_dual_full_time"
ACC_RATE_INCLUDING_GST = Decimal("0.0175")
ACC_MAXIMUM_EARNINGS = Decimal("156641")
ACC_CENTS_SCALE = Decimal("100")

COLUMN_CONCEPTS = {
    "gross_wage1": "nz:population/treasury-incomeexplorer#input.gross_wage1",
    "hours1": "nz:population/treasury-incomeexplorer#input.hours1",
    "gross_wage1_annual": "nz:population/treasury-incomeexplorer#input.gross_wage1_annual",
    "gross_wage2": "nz:population/treasury-incomeexplorer#input.gross_wage2",
    "wage1_tax": PROGRAM_VIEWS["nz/income-tax"]["roots"][0],
    "wage1_ACC_levy": PROGRAM_VIEWS["nz/acc-earners-levy"]["roots"][0],
    "net_wage1": "nz:comparison/treasury-incomeexplorer#net_wage1",
    "net_wage": "nz:comparison/treasury-incomeexplorer#net_wage",
    "net_benefit": PROGRAM_VIEWS["nz/main-benefits"]["roots"][0],
    "FTC_abated": PROGRAM_VIEWS["nz/working-for-families"]["roots"][0],
    "IWTC_abated": PROGRAM_VIEWS["nz/working-for-families"]["roots"][1],
    "MFTC": PROGRAM_VIEWS["nz/working-for-families"]["roots"][2],
    "IETC_abated": PROGRAM_VIEWS["nz/independent-earner-tax-credit"]["roots"][0],
    "WinterEnergy": PROGRAM_VIEWS["nz/winter-energy-payment"]["roots"][0],
    "BestStart_Total": PROGRAM_VIEWS["nz/working-for-families"]["roots"][3],
    "AS_Amount": PROGRAM_VIEWS["nz/accommodation-supplement"]["roots"][0],
    "WFF_abated": "nz:statutes/income_tax/family_scheme/tax_credits#wff_total",
    "Net_Income": "nz:comparison/treasury-incomeexplorer#net_income",
    "Net_Income_annual": "nz:comparison/treasury-incomeexplorer#net_income_annual",
}


class NZRecordError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NZRecordError(f"cannot read {path.relative_to(REPO_ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise NZRecordError(f"{path.relative_to(REPO_ROOT)} must contain an object")
    return value


def _canonical_sha256(value: object) -> str:
    rendered = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(rendered).hexdigest()


def _without_provenance(source: dict) -> dict:
    substance = copy.deepcopy(source)
    substance.pop("provenance", None)
    return substance


def _root_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for view, spec in PROGRAM_VIEWS.items():
        for root in spec["roots"]:
            if root in owners:
                raise NZRecordError(
                    f"requested-output root {root!r} belongs to multiple NZ views"
                )
            owners[root] = view
    return owners


def _observed_input_value(record: dict, location: str) -> str:
    raw = record.get("value")
    if not isinstance(raw, dict):
        raise NZRecordError(f"{location}.value must be an object")
    kind = raw.get("kind")
    value = raw.get("value")
    if kind == "bool":
        if not isinstance(value, bool):
            raise NZRecordError(f"{location}.value is not a typed bool")
        return json.dumps(value, sort_keys=True)
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise NZRecordError(f"{location}.value is not a typed integer")
        return json.dumps(value, sort_keys=True)
    if kind == "decimal":
        if not isinstance(value, str):
            raise NZRecordError(f"{location}.value is not a typed decimal string")
        try:
            number = Decimal(value)
        except Exception as exc:
            raise NZRecordError(f"{location}.value is not decimal") from exc
        if not number.is_finite():
            raise NZRecordError(f"{location}.value is not a finite decimal")
        return value
    raise NZRecordError(f"{location}.value has unsupported kind {kind!r}")


def _catalog_from_observations(
    source_catalog: dict,
    observations: dict[str, set[str]],
) -> dict:
    return {
        slot: {
            "canonical_request_name": row["canonical_request_name"],
            "distinct": len(observations[slot]),
            "state": "constant" if len(observations[slot]) == 1 else "varied",
            "observed_values": sorted(observations[slot]),
        }
        for slot, row in sorted(source_catalog.items())
        if observations.get(slot)
    }


def _trace_view_receipts(
    source: dict,
    traces: dict,
    *,
    verify_file_hash: bool = True,
) -> dict[str, dict]:
    """Validate exact engine calls and derive exercise for each NZ view."""

    if verify_file_hash and _sha256(TRACE_PATH) != TRACE_SHA256:
        raise NZRecordError("NZ evaluation trace bytes changed; a new receipt is required")
    if traces.get("schema") != TRACE_SCHEMA or traces.get("suite") != SUITE:
        raise NZRecordError("NZ evaluation traces have the wrong schema or suite")
    capture = traces.get("capture")
    if not isinstance(capture, dict) or capture.get("lineage_mode") != "attested":
        raise NZRecordError("NZ evaluation trace capture lineage is not identified")
    source_receipt = capture.get("source_comparison")
    expected_substance_sha = _canonical_sha256(_without_provenance(source))
    if not isinstance(source_receipt, dict) or source_receipt != {
        "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
        "sha256": SOURCE_SHA256,
        "regenerated_sha256": REGENERATED_SOURCE_SHA256,
        "substance_sha256": expected_substance_sha,
        "regeneration_difference": "provenance only",
    }:
        raise NZRecordError("NZ evaluation traces are not bound to the source comparison")
    if capture.get("source_harness") != (source.get("provenance") or {}).get(
        "source_comparison_harness"
    ):
        raise NZRecordError("NZ trace harness provenance drifted")
    if traces.get("compiled_program") != source.get("compiled_program"):
        raise NZRecordError("NZ trace compiled-program receipt drifted")
    provenance = source.get("provenance") or {}
    expected_engine = provenance.get("engine") or {}
    if traces.get("engine") != {
        "binary_sha256": expected_engine.get("binary_sha256"),
        "git_sha": expected_engine.get("git_sha"),
    }:
        raise NZRecordError("NZ trace engine receipt drifted")
    if traces.get("rulespec_commit") != (provenance.get("rulespec") or {}).get(
        "git_sha"
    ):
        raise NZRecordError("NZ trace RuleSpec receipt drifted")
    period = traces.get("period")
    if period != {"start": "2026-04-01", "end": "2027-03-31"}:
        raise NZRecordError("NZ trace period drifted")

    source_catalog = source.get("exercise_input_catalog")
    if not isinstance(source_catalog, dict) or not source_catalog:
        raise NZRecordError("NZ source comparison has no exercise input catalog")
    by_name: dict[str, str] = {}
    for slot, row in source_catalog.items():
        if not isinstance(row, dict):
            raise NZRecordError(f"NZ source catalog slot {slot!r} is malformed")
        name = row.get("canonical_request_name")
        if not isinstance(name, str) or not name or name in by_name:
            raise NZRecordError("NZ source catalog canonical names are not unique")
        by_name[name] = slot

    evaluations = traces.get("evaluations")
    expected_count = (source.get("compiled_program") or {}).get("engine_evaluations")
    if (
        not isinstance(evaluations, list)
        or isinstance(traces.get("evaluation_count"), bool)
        or traces.get("evaluation_count") != len(evaluations)
        or len(evaluations) != expected_count
    ):
        raise NZRecordError(
            "NZ trace evaluation count does not match the compiled-program receipt"
        )

    # Evidence-side ownership is the view emitted by the digest-pinned trace.
    # This reverse map is declaration-side only: it audits that the emitted
    # assignment remains bijective with PROGRAM_VIEWS, but never chooses the
    # bucket into which an evaluation is counted.
    declared_owners = _root_owners()
    global_observations: dict[str, set[str]] = defaultdict(set)
    view_observations: dict[str, dict[str, set[str]]] = {
        view: defaultdict(set) for view in PROGRAM_VIEWS
    }
    view_root_sets: dict[str, set[tuple[str, ...]]] = {
        view: set() for view in PROGRAM_VIEWS
    }
    root_set_observations: dict[
        str, dict[tuple[str, ...], dict[str, set[str]]]
    ] = {
        view: defaultdict(lambda: defaultdict(set)) for view in PROGRAM_VIEWS
    }
    root_set_counts: dict[str, Counter[tuple[str, ...]]] = {
        view: Counter() for view in PROGRAM_VIEWS
    }
    view_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for index, evaluation in enumerate(evaluations, start=1):
        location = f"evaluation-traces[{index - 1}]"
        if not isinstance(evaluation, dict):
            raise NZRecordError(f"{location} must be an object")
        expected_id = f"nz-ie-eval-{index:04d}"
        evaluation_id = evaluation.get("evaluation_id")
        if evaluation_id != expected_id or evaluation_id in seen_ids:
            raise NZRecordError(f"{location} has a missing, duplicate, or reordered id")
        seen_ids.add(evaluation_id)
        request = evaluation.get("request")
        if not isinstance(request, dict) or request.get("mode") != "explain":
            raise NZRecordError(f"{location} request is not explain mode")
        dataset = request.get("dataset")
        if not isinstance(dataset, dict) or dataset.get("relations") != []:
            raise NZRecordError(f"{location} dataset must carry the zero-relation request")
        inputs = dataset.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise NZRecordError(f"{location} request has no typed inputs")
        queries = request.get("queries")
        if not isinstance(queries, list) or len(queries) != 1:
            raise NZRecordError(f"{location} must carry exactly one query")
        query = queries[0]
        if not isinstance(query, dict):
            raise NZRecordError(f"{location} query must be an object")
        outputs = query.get("outputs")
        if (
            not isinstance(outputs, list)
            or not outputs
            or not all(isinstance(root, str) and root for root in outputs)
            or len(set(outputs)) != len(outputs)
        ):
            raise NZRecordError(f"{location} requested outputs are invalid")
        declared_roots = evaluation.get("requested_output_roots")
        if declared_roots != outputs:
            raise NZRecordError(f"{location} requested-output root receipt drifted")
        view = evaluation.get("view")
        if not isinstance(view, str) or view not in view_observations:
            raise NZRecordError(f"{location} is assigned to the wrong certificate view")
        output_owners = {declared_owners.get(root) for root in outputs}
        if None in output_owners or len(output_owners) != 1:
            raise NZRecordError(f"{location} requested roots cross or escape NZ views")
        if output_owners != {view}:
            raise NZRecordError(f"{location} is assigned to the wrong certificate view")
        root_set = tuple(outputs)
        if root_set not in REQUESTED_OUTPUT_ROOT_SETS[view]:
            raise NZRecordError(
                f"{location} has an unexpected requested-output root set for {view}"
            )
        expected_period = {
            "period_kind": "tax_year",
            "start": period["start"],
            "end": period["end"],
        }
        if query.get("period") != expected_period:
            raise NZRecordError(f"{location} query period drifted")
        query_entity = query.get("entity_id")
        if not isinstance(query_entity, str) or not query_entity:
            raise NZRecordError(f"{location} query entity_id is invalid")

        input_names: set[str] = set()
        for input_index, record in enumerate(inputs):
            input_location = f"{location}.request.dataset.inputs[{input_index}]"
            if not isinstance(record, dict):
                raise NZRecordError(f"{input_location} must be an object")
            name = record.get("name")
            if not isinstance(name, str) or name not in by_name or name in input_names:
                raise NZRecordError(f"{input_location} names an unknown or duplicate input")
            input_names.add(name)
            if (
                not isinstance(record.get("entity"), str)
                or record.get("entity_id") != query_entity
                or record.get("interval")
                != {"start": period["start"], "end": period["end"]}
            ):
                raise NZRecordError(f"{input_location} entity or interval drifted")
            observed = _observed_input_value(record, input_location)
            slot = by_name[name]
            global_observations[slot].add(observed)
            view_observations[view][slot].add(observed)
            root_set_observations[view][root_set][slot].add(observed)

        response = evaluation.get("response")
        if not isinstance(response, dict):
            raise NZRecordError(f"{location} response must be an object")
        if response.get("metadata") != {
            "actual_mode": "explain",
            "requested_mode": "explain",
        }:
            raise NZRecordError(f"{location} response mode receipt drifted")
        if response.get("entity_id") != query_entity:
            raise NZRecordError(f"{location} response entity_id drifted")
        if response.get("period") != query.get("period"):
            raise NZRecordError(f"{location} response period drifted")
        returned = response.get("outputs")
        if not isinstance(returned, dict) or set(returned) != set(outputs):
            raise NZRecordError(f"{location} returned outputs do not biject requested roots")
        for root in outputs:
            item = returned[root]
            if not isinstance(item, dict) or item.get("id") != root:
                raise NZRecordError(f"{location} returned output {root!r} lost identity")
            if item.get("kind") == "scalar":
                try:
                    _observed_input_value(
                        item,
                        f"{location}.response.outputs[{root!r}]",
                    )
                except NZRecordError as exc:
                    raise NZRecordError(
                        f"{location} returned scalar {root!r} is malformed"
                    ) from exc
            elif item.get("kind") == "judgment":
                if item.get("outcome") not in {"holds", "not_holds"}:
                    raise NZRecordError(f"{location} returned judgment {root!r} is malformed")
            else:
                raise NZRecordError(f"{location} returned output {root!r} has unknown kind")
        view_counts[view] += 1
        view_root_sets[view].add(root_set)
        root_set_counts[view][root_set] += 1

    derived_catalog = _catalog_from_observations(source_catalog, global_observations)
    attested_active_catalog = {
        slot: row
        for slot, row in source_catalog.items()
        if row.get("state") != "not_supplied"
    }
    if derived_catalog != attested_active_catalog:
        raise NZRecordError(
            "NZ trace request inputs do not reproduce the supplied-input receipt"
        )

    receipts: dict[str, dict] = {}
    for view, spec in PROGRAM_VIEWS.items():
        root_sets = view_root_sets[view]
        expected_root_sets = REQUESTED_OUTPUT_ROOT_SETS[view]
        observed_roots = {root for root_set in root_sets for root in root_set}
        expected_roots = set(spec["roots"])
        if (
            view_counts[view] <= 0
            or root_sets != set(expected_root_sets)
            or observed_roots != expected_roots
        ):
            raise NZRecordError(
                f"NZ trace requested root sets do not exactly close view {view}"
            )
        fields = {
            slot: {
                "canonical_request_name": source_catalog[slot][
                    "canonical_request_name"
                ],
                "distinct": len(values),
                "state": "varied" if len(values) > 1 else "constant",
            }
            for slot, values in sorted(view_observations[view].items())
        }
        root_set_receipts = []
        for requested_roots in expected_root_sets:
            observations = root_set_observations[view][requested_roots]
            root_set_receipts.append(
                {
                    "requested_output_roots": list(requested_roots),
                    "evaluation_count": root_set_counts[view][requested_roots],
                    "evidence_fields": {
                        slot: {
                            "canonical_request_name": source_catalog[slot][
                                "canonical_request_name"
                            ],
                            "distinct": len(values),
                            "state": "varied" if len(values) > 1 else "constant",
                        }
                        for slot, values in sorted(observations.items())
                    },
                }
            )
        receipts[view] = {
            "evaluation_count": view_counts[view],
            "evidence_fields": fields,
            "requested_output_root_sets": [
                list(root_set) for root_set in expected_root_sets
            ],
            "root_set_receipts": root_set_receipts,
            "requested_output_roots": list(spec["roots"]),
            "root_reconciliation": "exact",
            "trace_binding": "bound",
        }
    return receipts


def derive_bound_trace_views() -> dict[str, dict]:
    """Reopen and rederive every view/root-set receipt from committed bytes."""

    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    _validate_inputs(source, snapshot, closures)
    return _trace_view_receipts(source, _load(TRACE_PATH))


def build_trace_document(capture: dict, regenerated_source: dict) -> dict:
    """Reconstruct the already-committed public trace from a raw capture.

    This is deliberately a no-drift verification path, not an evidence minting
    path.  Evidence-side view ownership comes from the committed #476 trace;
    ``PROGRAM_VIEWS`` participates only later, when ``_trace_view_receipts``
    audits the declaration side of the bijection.  A candidate must be
    canonically identical to the digest-pinned committed trace before the CLI
    is allowed to write anything.
    """

    source = _load(SOURCE_PATH)
    if _sha256(TRACE_PATH) != TRACE_SHA256:
        raise NZRecordError(
            "committed NZ evaluation trace bytes changed; capture verification "
            "cannot establish its authority"
        )
    committed_trace = _load(TRACE_PATH)
    committed_evaluations = committed_trace.get("evaluations")
    if not isinstance(committed_evaluations, list):
        raise NZRecordError("committed NZ evaluation trace has no evaluations")
    committed_by_request: dict[str, dict] = {}
    for index, evaluation in enumerate(committed_evaluations):
        if not isinstance(evaluation, dict) or not isinstance(
            evaluation.get("request"), dict
        ):
            raise NZRecordError(
                f"committed NZ evaluation trace row {index} has no request"
            )
        key = json.dumps(
            evaluation["request"],
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if key in committed_by_request:
            raise NZRecordError(
                "committed NZ evaluation trace repeats a canonical request"
            )
        committed_by_request[key] = evaluation
    if capture.get("schema") != RAW_TRACE_SCHEMA:
        raise NZRecordError("raw NZ trace capture has the wrong schema")
    if _without_provenance(regenerated_source) != _without_provenance(source):
        raise NZRecordError("instrumented trace run changed comparison substance")
    if _canonical_file_sha(regenerated_source) != REGENERATED_SOURCE_SHA256:
        raise NZRecordError("instrumented trace comparison bytes changed")
    evaluations = copy.deepcopy(capture.get("evaluations"))
    if not isinstance(evaluations, list):
        raise NZRecordError("raw NZ trace capture has no evaluations")
    for index, evaluation in enumerate(evaluations):
        if not isinstance(evaluation, dict):
            raise NZRecordError(f"raw NZ trace evaluation {index} is not an object")
        outputs = ((evaluation.get("request") or {}).get("queries") or [{}])[0].get(
            "outputs"
        )
        if not isinstance(outputs, list) or not outputs:
            raise NZRecordError(f"raw NZ trace evaluation {index} has no outputs")
        request = evaluation.get("request")
        if not isinstance(request, dict):
            raise NZRecordError(f"raw NZ trace evaluation {index} has no request")
        request_key = json.dumps(
            request,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        committed_evaluation = committed_by_request.get(request_key)
        if committed_evaluation is None:
            raise NZRecordError(
                f"raw NZ trace evaluation {index} request/root is absent from the "
                "committed #476 evaluation trace or crosses views"
            )
        # These evidence-side fields are copied from the committed trace, never
        # inferred through PROGRAM_VIEWS or another mutable declaration table.
        evaluation["view"] = committed_evaluation.get("view")
        evaluation["requested_output_roots"] = copy.deepcopy(
            committed_evaluation.get("requested_output_roots")
        )
    document = {
        "_comment": (
            "Normalized from capture-only instrumentation associated with the pinned "
            "external comparison harness. scripts/nz_incomeexplorer.py recomputes "
            "supplied-input observations separately for each certificate view and "
            "requested-output root set from these exact typed requests and returned "
            "outputs. Capture lineage and the compiled-input denominator remain "
            "attested because neither the capture transcript/instrumentation nor "
            "compiled artifact bytes are committed here."
        ),
        "schema": TRACE_SCHEMA,
        "suite": SUITE,
        "capture": {
            "lineage_mode": "attested",
            "source_comparison": {
                "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
                "sha256": SOURCE_SHA256,
                "regenerated_sha256": _canonical_file_sha(regenerated_source),
                "substance_sha256": _canonical_sha256(_without_provenance(source)),
                "regeneration_difference": "provenance only",
            },
            "source_harness": (source.get("provenance") or {}).get(
                "source_comparison_harness"
            ),
        },
        "compiled_program": source["compiled_program"],
        "engine": copy.deepcopy(capture.get("engine")),
        "evaluation_count": capture.get("evaluation_count"),
        "evaluations": evaluations,
        "period": copy.deepcopy(capture.get("period")),
        "rulespec_commit": capture.get("rulespec_commit"),
    }
    if document != committed_trace:
        raise NZRecordError(
            "raw NZ trace capture is not canonically identical to the committed "
            "#476 evaluation trace"
        )
    _trace_view_receipts(source, document, verify_file_hash=False)
    return document


def _canonical_file_sha(value: dict) -> str:
    """SHA of the same sorted, indented JSON form emitted by the ops harness."""

    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return hashlib.sha256(rendered.encode()).hexdigest()


def _case_id(row: dict) -> str:
    return f"nz-ie::{row['scenario_id']}::{row['weekly_wage']}"


def _number(value: object) -> int | float:
    number = Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)


def _decimal_text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    return format(value, "f").rstrip("0").rstrip(".")


def _acc_cell(weekly_wage: int, _profile: dict) -> Decimal:
    """Recompute the exact ACC cell used by the pinned harness.

    The harness passes only primary annual earnings to
    ``acc_standard_earners_levy_including_gst``.  The selected 2026-04-01
    RuleSpec values are 0.0175 and NZD 156,641, with annual-cent rounding
    before conversion back to the 365/7 weekly convention.
    """

    with localcontext() as context:
        context.prec = 40
        nonnegative_wage = max(Decimal(0), Decimal(weekly_wage))
        if nonnegative_wage * Decimal("365") <= ACC_MAXIMUM_EARNINGS * Decimal("7"):
            unrounded_cents = (
                nonnegative_wage
                * Decimal("365")
                * ACC_RATE_INCLUDING_GST
                * ACC_CENTS_SCALE
                / Decimal("7")
            )
        else:
            unrounded_cents = (
                ACC_MAXIMUM_EARNINGS
                * ACC_RATE_INCLUDING_GST
                * ACC_CENTS_SCALE
            )
        annual_levy = (
            (unrounded_cents + Decimal("0.5")).to_integral_value(
                rounding=ROUND_FLOOR
            )
            / ACC_CENTS_SCALE
        )
        return annual_levy * Decimal("7") / Decimal("365")


def _rulespec_receipt_cells(
    source: dict, scenario_id: str, column: str
) -> dict[int, Decimal]:
    return {
        int(row["weekly_wage"]): Decimal(str(row["rulespec"]))
        for row in source.get("comparisons") or []
        if row.get("scenario_id") == scenario_id and row.get("column") == column
    }


def assert_single_person_invariant(
    source: dict,
    program: str,
    calculator=None,
) -> dict:
    """Perturb every non-primary person fact and require identical cell bytes.

    ``calculator`` is injectable solely so the mutant can route the same gate
    through the genuinely cross-person WfF receipt and prove that it bites.
    """

    if program not in PROGRAM_VIEWS:
        raise NZRecordError(f"unknown NZ program {program!r}")
    scenarios = {item["id"]: item for item in source.get("scenarios") or []}
    try:
        baseline = scenarios[ATTESTATION_BASELINE_SCENARIO]
        perturbed = scenarios[ATTESTATION_PERTURBED_SCENARIO]
    except KeyError as exc:
        raise NZRecordError(f"attestation scenario missing: {exc}") from exc
    primary_fields = ("wage1_hourly", "accommodation_area", "accommodation_costs")
    for field in primary_fields:
        if baseline["inputs"].get(field) != perturbed["inputs"].get(field):
            raise NZRecordError(f"attestation changed primary field {field}")
    non_primary_fields = ("partnered", "gross_wage2", "hours2", "children_ages")
    unchanged = [
        field
        for field in non_primary_fields
        if baseline["inputs"].get(field) == perturbed["inputs"].get(field)
    ]
    if unchanged:
        raise NZRecordError(
            f"attestation did not perturb non-primary field(s) {unchanged}"
        )
    baseline_wages = set(baseline["sampled_weekly_wages"])
    perturbed_wages = set(perturbed["sampled_weekly_wages"])
    wages = sorted(baseline_wages & perturbed_wages)
    if not wages:
        raise NZRecordError("attestation scenarios have no shared primary wage cells")
    if calculator is None:
        if program != "nz/acc-earners-levy":
            raise NZRecordError(f"{program}: no single-person calculator is ratified")
        calculator = _acc_cell
    baseline_cells = [
        _decimal_text(calculator(wage, baseline)) for wage in wages
    ]
    perturbed_cells = [
        _decimal_text(calculator(wage, perturbed)) for wage in wages
    ]
    baseline_bytes = json.dumps(
        baseline_cells, separators=(",", ":"), ensure_ascii=False
    ).encode()
    perturbed_bytes = json.dumps(
        perturbed_cells, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if baseline_bytes != perturbed_bytes:
        raise NZRecordError(
            f"{program}: non-primary-person perturbation changed program cells"
        )
    if program == "nz/acc-earners-levy" and calculator is _acc_cell:
        for scenario_id, cells in (
            (ATTESTATION_BASELINE_SCENARIO, baseline_cells),
            (ATTESTATION_PERTURBED_SCENARIO, perturbed_cells),
        ):
            receipt = _rulespec_receipt_cells(source, scenario_id, "wage1_ACC_levy")
            if any(
                abs(receipt[wage] - calculator(wage, scenarios[scenario_id]))
                > Decimal("1e-36")
                for wage in wages
            ):
                raise NZRecordError(
                    f"{program}: recomputed cells differ from the engine receipt"
                )
    return {
        "status": "pass",
        "program": program,
        "root_nodes": list(PROGRAM_VIEWS[program]["roots"]),
        "baseline_scenario": ATTESTATION_BASELINE_SCENARIO,
        "perturbed_scenario": ATTESTATION_PERTURBED_SCENARIO,
        "perturbed_non_primary_inputs": {
            field: {
                "before": baseline["inputs"].get(field),
                "after": perturbed["inputs"].get(field),
            }
            for field in non_primary_fields
        },
        "primary_weekly_wages": wages,
        "cell_count": len(wages),
        "baseline_cells": baseline_cells,
        "perturbed_cells": perturbed_cells,
        "baseline_cells_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "perturbed_cells_sha256": hashlib.sha256(perturbed_bytes).hexdigest(),
    }


def build_single_person_attestations() -> dict:
    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    _validate_inputs(source, snapshot, closures)
    return {
        "schema": "axiom_oracles.nz_single_person_attestations.v1",
        "source_receipt": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": SOURCE_SHA256,
        },
        "programs": {
            program: assert_single_person_invariant(source, program)
            for program in sorted(SINGLE_PERSON_PROGRAMS)
        },
    }


def _validate_inputs(source: dict, snapshot: dict, closures: dict) -> None:
    if _sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise NZRecordError("source comparison bytes changed; a new receipt series is required")
    if _sha256(SNAPSHOT_PATH) != SNAPSHOT_SHA256:
        raise NZRecordError("Treasury snapshot does not reproduce byte-identically")
    oracle = snapshot.get("oracle") or {}
    if oracle.get("commit") != TREASURY_COMMIT:
        raise NZRecordError("Treasury oracle commit drifted")
    provenance = source.get("provenance") or {}
    if (provenance.get("oracle_snapshot") or {}).get("sha256") != SNAPSHOT_SHA256:
        raise NZRecordError("source receipt is not bound to the committed Treasury snapshot")
    closure_provenance = provenance.get("eligibility_closures") or {}
    if closure_provenance.get("sha256") != _sha256(CLOSURES_PATH):
        raise NZRecordError("source receipt is not bound to eligibility-closures.json")
    if source.get("declared_eligibility_closures") != closures:
        raise NZRecordError("declared eligibility closures differ from the harness receipt")

    snapshot_spine = [
        (item["id"], tuple(int(r["gross_wage1"]) for r in item["sampled_outputs"]))
        for item in snapshot.get("scenarios") or []
    ]
    source_spine = [
        (item["id"], tuple(item["sampled_weekly_wages"]))
        for item in source.get("scenarios") or []
    ]
    if source_spine != snapshot_spine or sum(len(wages) for _, wages in source_spine) != 104:
        raise NZRecordError("source population is not Treasury's complete 104-point scenario spine")

    rows = source.get("comparisons") or []
    amount_rows = [row for row in rows if row.get("column") != "EMTR"]
    outside = [row for row in amount_rows if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE]
    classes = Counter(row.get("classification") for row in outside)
    if len(amount_rows) != 1976 or len(outside) != 522 or classes != {"b": 520, "c": 2}:
        raise NZRecordError(
            f"unexpected amount matrix: rows={len(amount_rows)}, outside={len(outside)}, classes={dict(classes)}"
        )
    if set(COLUMN_CONCEPTS) != {row["column"] for row in amount_rows}:
        raise NZRecordError("the amount/control output surface changed without node mappings")


def _mismatch(row: dict) -> dict:
    return {
        "case_id": _case_id(row),
        "concept": COLUMN_CONCEPTS[row["column"]],
        "description": row["reason_title"],
        "difference": _number(row["signed_delta_rulespec_minus_treasury"]),
        "kind": "amount_difference",
        "left": _number(row["rulespec"]),
        "right": _number(row["treasury"]),
        "tolerance": float(AMOUNT_TOLERANCE),
        "metadata": {
            "column": row["column"],
            "classification": row["classification"],
            "reason_code": row["reason_code"],
        },
    }


def _match(row: dict) -> dict:
    return {
        "concept": COLUMN_CONCEPTS[row["column"]],
        "left": _number(row["rulespec"]),
        "right": _number(row["treasury"]),
    }


def _base_report(
    source: dict,
    snapshot: dict,
    closures: dict,
    trace_views: dict[str, dict] | None = None,
) -> dict:
    amount_rows = [row for row in source["comparisons"] if row["column"] != "EMTR"]
    mismatch_rows = [
        _mismatch(row)
        for row in amount_rows
        if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE
    ]
    by_case_mismatches: dict[str, list[dict]] = defaultdict(list)
    for mismatch in mismatch_rows:
        by_case_mismatches[mismatch["case_id"]].append(mismatch)
    by_case_matches: dict[str, list[dict]] = defaultdict(list)
    for row in amount_rows:
        if Decimal(row["absolute_delta"]) < AMOUNT_TOLERANCE:
            by_case_matches[_case_id(row)].append(_match(row))
    scenarios = {item["id"]: item for item in source["scenarios"]}
    cases = []
    for scenario_id, wages in (
        (item["id"], item["sampled_weekly_wages"]) for item in source["scenarios"]
    ):
        scenario = scenarios[scenario_id]
        for wage in wages:
            case_id = f"nz-ie::{scenario_id}::{wage}"
            cases.append(
                {
                    "case_id": case_id,
                    "metadata": {
                        "scenario_id": scenario_id,
                        "weekly_wage": wage,
                        **scenario["inputs"],
                    },
                    "matches": by_case_matches.get(case_id, []),
                    "mismatches": by_case_mismatches.get(case_id, []),
                }
            )

    active_catalog = {
        name: value
        for name, value in source["exercise_input_catalog"].items()
        if value["state"] != "not_supplied"
    }
    if Counter(item["state"] for item in active_catalog.values()) != {
        "constant": 98,
        "varied": 52,
    }:
        raise NZRecordError("the exercised active input surface changed")
    aggregates = []
    for concept in sorted(set(COLUMN_CONCEPTS.values())):
        concept_rows = [row for row in amount_rows if COLUMN_CONCEPTS[row["column"]] == concept]
        concept_mismatches = [
            row for row in concept_rows if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE
        ]
        aggregates.append(
            {
                "concept": concept,
                "comparison": "amount",
                "comparison_count": len(concept_rows),
                "match_count": len(concept_rows) - len(concept_mismatches),
                "mismatch_count": len(concept_mismatches),
            }
        )
    report = {
        "record_schema": SCHEMA,
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITE,
        "tuple": {
            "jurisdiction": "nz",
            "population": {
                "id": "treasury-incomeexplorer-emtr-scenario-grid",
                "sha256": SNAPSHOT_SHA256,
                "scenario_count": 11,
                "points": 104,
            },
            "oracle": {"id": "treasury-incomeexplorer", "version": TREASURY_COMMIT},
        },
        "period": "2026-04-01/2027-03-31",
        "population": "treasury-incomeexplorer-emtr-scenario-grid",
        "dataset_identity": {"sha256": SNAPSHOT_SHA256, "revision": TREASURY_COMMIT},
        "engines": {"left": "axiom", "right": "treasury-incomeexplorer"},
        "case_count": len(cases),
        "concepts": [
            {
                "id": concept,
                "comparison": "amount",
                "tolerance": float(AMOUNT_TOLERANCE),
                "relative_tolerance": 0,
            }
            for concept in sorted(set(COLUMN_CONCEPTS.values()))
        ],
        "aggregates": aggregates,
        "cases": cases,
        "mismatches": mismatch_rows,
        "summary": {
            "comparison_count": len(amount_rows),
            "match_count": len(amount_rows) - len(mismatch_rows),
            "mismatch_count": len(mismatch_rows),
            "error_count": 0,
        },
        "experiment": {
            "schema": "axiom.experiment_boundary_receipt.v1",
            "active_inputs": active_catalog,
            "compiled_input_catalog": {
                "mode": "attested",
                "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
                "sha256": SOURCE_SHA256,
                "input_count": len(source["exercise_input_catalog"]),
                "supplied_input_count": len(active_catalog),
                "not_supplied_count": sum(
                    item["state"] == "not_supplied"
                    for item in source["exercise_input_catalog"].values()
                ),
                "limitation": (
                    "No committed compiled-program artifact or compiler-produced "
                    "catalog enumeration proves the complete input denominator."
                ),
            },
            "bridged_through": {},
            "trace": {
                "artifact": str(TRACE_PATH.relative_to(REPO_ROOT)),
                "sha256": TRACE_SHA256,
                "schema": TRACE_SCHEMA,
                "capture_lineage_mode": "attested",
            }
            if trace_views is not None
            else None,
            "views": trace_views or {},
            "eligibility_closures": {
                "artifact": str(CLOSURES_PATH.relative_to(REPO_ROOT)),
                "sha256": _sha256(CLOSURES_PATH),
                "version": closures["version"],
            },
        },
        "compiled_program": source["compiled_program"],
        "views": {
            program: {
                "kind": "subgraph",
                "columns": list(spec["columns"]),
                "root_nodes": list(spec["roots"]),
            }
            for program, spec in PROGRAM_VIEWS.items()
        },
        "provenance": {
            **source["provenance"],
            "source_receipt": {
                "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
                "sha256": SOURCE_SHA256,
            },
            "generated_by": "scripts/nz_incomeexplorer.py",
        },
    }
    return report


def _apply_and_view(report: dict) -> dict:
    from axiom_oracles.comparison.dispositions import apply_dispositions, load_dispositions

    dispositions = load_dispositions(DISPOSITIONS_PATH, repo_root=REPO_ROOT)
    merged = apply_dispositions(
        report,
        dispositions,
        dispositions_file=str(DISPOSITIONS_PATH.relative_to(REPO_ROOT)),
    )
    for program, view in merged["views"].items():
        columns = set(view["columns"])
        rows = [
            row for row in merged["mismatches"]
            if (row.get("metadata") or {}).get("column") in columns
        ]
        comparisons = 104 * len(columns)
        counts = Counter(
            (row.get("disposition") or {}).get("disposition", "unexplained")
            for row in rows
        )
        view["summary"] = {
            "comparison_count": comparisons,
            "match_count": comparisons - len(rows),
            "mismatch_count": len(rows),
            "dispositioned": {
                "dispositions_file": str(DISPOSITIONS_PATH.relative_to(REPO_ROOT)),
                "counts": {
                    name: counts.get(name, 0)
                    for name in (
                        "explained_residual",
                        "upstream_engine_gap",
                        "bridge_artifact",
                        "axiom_encoding_gap",
                        "unexplained",
                    )
                },
                "unexplained_count": counts.get("unexplained", 0),
            },
        }
    return merged


def build_evidence() -> tuple[dict, list[dict]]:
    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    traces = _load(TRACE_PATH)
    _validate_inputs(source, snapshot, closures)
    trace_views = _trace_view_receipts(source, traces)
    report = _apply_and_view(
        _base_report(source, snapshot, closures, trace_views=trace_views)
    )
    explained = explained_lookup(report)
    rows = [
        compact_case(case, explained)
        for case in report["cases"]
    ]
    # Bound chunks are the sole execution corpus. Keeping the same case IDs
    # inline as well would double the parsed cardinality and weaken identity
    # checks by presenting two copies of every verdict.
    return {**report, "cases": []}, rows


def build() -> dict:
    report, _rows = build_evidence()
    return report


def _render_chunks(rows: list[dict]) -> dict[str, str]:
    chunks = [rows[i : i + CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]
    return {
        f"chunk-{index}.json": json.dumps(chunk, separators=(",", ":"))
        for index, chunk in enumerate(chunks)
    }


def _index_payload(rows: list[dict]) -> dict:
    candidate = build_chunk_index(OUTPUT_PATH)
    return {
        "schema_version": candidate["schema_version"],
        "report_path": candidate["report_path"],
        "report_sha256": candidate["report_sha256"],
        "case_verdicts_sha256": candidate["case_verdicts_sha256"],
        "suite": SUITE,
        "count": len(rows),
        "chunk_size": CHUNK_SIZE,
        "engines": {"left": "axiom", "right": "treasury-incomeexplorer"},
        "mismatch_concepts": sorted(
            {
                mismatch["c"]
                for row in rows
                for mismatch in row["m"]
                if mismatch.get("c")
            }
        ),
        "source": str(SOURCE_PATH.relative_to(REPO_ROOT)),
        "total_cases": len(rows),
        "chunk_count": candidate["chunk_count"],
        "chunks": candidate["chunks"],
    }


def _write_case_artifacts(chunks: dict[str, str], rows: list[dict]) -> None:
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    expected = set(chunks)
    for stale in CASE_DIR.glob("chunk-*.json"):
        if stale.name not in expected:
            stale.unlink()
    for name, rendered in chunks.items():
        (CASE_DIR / name).write_text(rendered, encoding="utf-8")
    INDEX_PATH.write_text(
        json.dumps(_index_payload(rows), indent=2) + "\n",
        encoding="utf-8",
    )


def _case_artifact_drift(chunks: dict[str, str], rows: list[dict]) -> list[str]:
    problems: list[str] = []
    expected_names = set(chunks)
    actual_names = {path.name for path in CASE_DIR.glob("chunk-*.json")}
    if actual_names != expected_names:
        problems.append(
            "NZ IncomeExplorer chunk file set drifted "
            f"(expected={sorted(expected_names)}, actual={sorted(actual_names)})"
        )
    for name, rendered in chunks.items():
        path = CASE_DIR / name
        if not path.exists() or path.read_text(encoding="utf-8") != rendered:
            problems.append(f"NZ IncomeExplorer {name} drifted")
    if problems:
        return problems
    expected_index = json.dumps(_index_payload(rows), indent=2) + "\n"
    if not INDEX_PATH.exists() or INDEX_PATH.read_text(encoding="utf-8") != expected_index:
        problems.append("NZ IncomeExplorer chunk index drifted")
        return problems
    evidence = validate_suite_evidence(OUTPUT_PATH)
    if not evidence.valid or evidence.binding != "bound" or evidence.reconciliation != "full":
        problems.extend(evidence.defects)
    return problems


def _instrument_names(source: dict, row: dict, at_point: dict[tuple, list[dict]]) -> list[str]:
    code = row["reason_code"]
    column = row["column"]
    scenario = next(item for item in source["scenarios"] if item["id"] == row["scenario_id"])
    children = scenario["inputs"]["children_ages"]
    partnered = scenario["inputs"]["partnered"]

    def benefit() -> str:
        if partnered and children:
            return "JSS partnered-with-children weekly rate (SSA 2018 Sch 4 pt 1 cl 1(g)(ii))"
        if children and min(children) < 14:
            return "Sole Parent Support weekly rate (SSA 2018 Sch 4 pt 2 cl 1)"
        if children:
            return "lone-parent JSS weekly rate (SSA 2018 Sch 4 pt 1 cl 1(e))"
        return "JSS single-no-children weekly rate (SSA 2018 Sch 4 pt 1 cl 1(d))"

    direct = {
        "FTC_abated": "Family Tax Credit annual prescribed amount (Income Tax Act 2007 s MD 3)",
        "IWTC_abated": "In-Work Tax Credit base (Income Tax Act 2007 s MD 10)",
        "MFTC": "Minimum Family Tax Credit prescribed amount (Income Tax Act 2007 s ME 1)",
        "BestStart_Total": "Best Start prescribed amount (Income Tax Act 2007 s MG 2)",
    }
    if code == "B_BENEFIT_VINTAGE" or code == "B_BENEFIT_GROSSUP_TAX" or code == "B_WINTER_ENERGY_BENEFIT_GATE":
        return [benefit()]
    if column in direct:
        return [direct[column]]
    if code == "C_IETC_WHOLE_DOLLARS":
        return ["IETC statutory complete-dollar arithmetic (Income Tax Act 2007 s LC 13)"]
    point_rows = at_point[(row["scenario_id"], row["weekly_wage"])]
    names = [direct[item["column"]] for item in point_rows if item["column"] in direct and item["classification"] == "b"]
    if any(item["column"] == "net_benefit" and item["classification"] == "b" for item in point_rows):
        names.append(benefit())
    if not names:
        names = [benefit()]
    return sorted(set(names))


def bootstrap_dispositions() -> str:
    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    _validate_inputs(source, snapshot, closures)
    amount = [row for row in source["comparisons"] if row["column"] != "EMTR"]
    outside = [row for row in amount if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE]
    at_point: dict[tuple, list[dict]] = defaultdict(list)
    for row in amount:
        at_point[(row["scenario_id"], row["weekly_wage"])].append(row)
    entries = []
    for index, row in enumerate(outside, start=1):
        instruments = _instrument_names(source, row, at_point)
        entries.append(
            {
                "id": f"nz-ie-{index:04d}-{row['reason_code'].lower().replace('_', '-')}",
                "concept": COLUMN_CONCEPTS[row["column"]],
                "case_id": _case_id(row),
                "kind": "amount_difference",
                "disposition": "explained_residual",
                "evidence": {
                    "mechanism": (
                        f"{row['reason_title']}: {row['reason']} Named instrument(s): "
                        + "; ".join(instruments)
                    ),
                    "sources": [
                        str(SOURCE_PATH.relative_to(REPO_ROOT)),
                        "https://github.com/TheAxiomFoundation/rulespec-nz/issues/108",
                    ],
                },
                "expires_on_source_change": True,
                "pinned": {
                    "left": _number(row["rulespec"]),
                    "right": _number(row["treasury"]),
                    "difference": _number(row["signed_delta_rulespec_minus_treasury"]),
                },
            }
        )
    document = {
        "schema": "axiom_oracles.dispositions.v1",
        "suite": SUITE,
        "updated": "2026-08-13",
        "entries": entries,
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--bootstrap-dispositions", action="store_true")
    parser.add_argument(
        "--capture-traces",
        type=Path,
        help="raw double-run trace capture from the pinned ops harness",
    )
    parser.add_argument(
        "--capture-comparison",
        type=Path,
        help="comparison.json emitted beside --capture-traces",
    )
    args = parser.parse_args()
    try:
        if args.capture_traces or args.capture_comparison:
            if args.check or not args.capture_traces or not args.capture_comparison:
                parser.error(
                    "--capture-traces and --capture-comparison are required together "
                    "and cannot be used with --check"
                )
            document = build_trace_document(
                _load(args.capture_traces),
                _load(args.capture_comparison),
            )
            TRACE_PATH.write_text(
                json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            print(f"wrote {TRACE_PATH.relative_to(REPO_ROOT)}")
            return 0
        if args.bootstrap_dispositions:
            rendered = bootstrap_dispositions()
            if args.check:
                if not DISPOSITIONS_PATH.exists() or DISPOSITIONS_PATH.read_text() != rendered:
                    print("NZ IncomeExplorer dispositions drifted", file=sys.stderr)
                    return 1
            else:
                DISPOSITIONS_PATH.write_text(rendered, encoding="utf-8")
            return 0
        record, case_rows = build_evidence()
        attestations = build_single_person_attestations()
    except (NZRecordError, OSError, ValueError) as exc:
        print(f"NZ IncomeExplorer ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    attestation_rendered = (
        json.dumps(attestations, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    chunk_renderings = _render_chunks(case_rows)
    if args.check:
        drift: list[str] = []
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != rendered:
            drift.append("NZ IncomeExplorer unified record drifted")
        if (
            not ATTESTATION_PATH.exists()
            or ATTESTATION_PATH.read_text(encoding="utf-8") != attestation_rendered
        ):
            drift.append("NZ single-person attestations drifted")
        if not drift:
            drift.extend(_case_artifact_drift(chunk_renderings, case_rows))
        if drift:
            print("\n".join(drift), file=sys.stderr)
            return 1
        print(
            "NZ IncomeExplorer unified record and bound case evidence up to date"
        )
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    ATTESTATION_PATH.write_text(attestation_rendered, encoding="utf-8")
    _write_case_artifacts(chunk_renderings, case_rows)
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {ATTESTATION_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {INDEX_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
