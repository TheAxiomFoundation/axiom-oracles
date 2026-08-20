#!/usr/bin/env python3
"""Compute the DE Kindergeld executable premise, failing closed.

The certificate may only call this premise computed-true after all four
independent inputs exist and validate:

* the exact Axiom x EUROMOD comparison leg;
* the exact Axiom x GETTSIM comparison leg;
* a cryptographically verified, signed RuleSpec-DE EStG section 66 module; and
* a self-contained receipt whose embedded, digest-pinned release archive is
  freshly replayed against the legs' common request and that signed module.

The historical EUROMOD x GETTSIM report stores only a Kindergeld aggregate.
It therefore identifies the population but is never an expected-output
source.  Replay requests and expected result rows come byte-for-byte from the
two future Axiom leg records, and the producer rejects them unless they agree.

Modes::

    python scripts/de_executable.py             # regenerate pending/pass status
    python scripts/de_executable.py --check     # fail on status drift
    python scripts/de_executable.py --print-status
    python scripts/de_executable.py --run \
      --engine-archive /path/to/release.tar.xz \
      --rulespec-root /path/to/rulespec-de \
      --signing-public-key /path/to/apply-public-key \
      --euromod-model-root /path/to/EUROMOD_RELEASES_J2.0+ \
      --euromod-python /path/to/euromod/python

``--run`` creates that evidence pair.  More importantly, normal regeneration
does not trust its command transcript: it decodes the archived release bytes,
checks their published digest, and executes the binary again.  It also verifies
the upstream apply-manifest Ed25519 signature, the committed RuleSpec bytes,
and both comparison-leg fixtures.  Merely placing JSON at either path cannot
make the status pass.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.evidence import strict_json_loads  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "conformance" / "executable" / "de-kindergeld-manifest.json"

MANIFEST_SCHEMA = "axiom_oracles.de_executable_manifest.v1"
STATUS_SCHEMA = "axiom_oracles.de_executable_status.v1"
SIGNED_ARTIFACT_SCHEMA = "axiom_oracles.de_signed_rulespec_artifact.v2"
REPLAY_SCHEMA = "axiom_oracles.de_release_binary_replay.v2"

PROGRAM = "de/kindergeld"
PERIOD = "2025"
ROOT_NODE = "de:statutes/estg/66#monthly_kindergeld_per_child"
KINDERGELD_CONCEPT = "de:policies/worker_dual_oracle_baseline#kindergeld_monthly"
ORACLE_TARGETS = {
    "euromod": "bch00_s",
    "gettsim": "kindergeld.betrag_m",
}
APPLY_SIGNATURE_DOMAIN = b"axiom-encode/external-signer-sign/v2\x00apply_ed25519\x00"

ENGINE_PIN = {
    "repository": "TheAxiomFoundation/axiom-rules-engine",
    "release": "v0.2.2",
    "commit": "2c0e1edac0dccc355297eb9663e0aa0c4e97e5b4",
    "target": "x86_64-unknown-linux-gnu",
    "asset": "axiom-rules-engine-x86_64-unknown-linux-gnu.tar.xz",
    "archive_sha256": (
        "76565685230d64edf33e4205f01f77c57ef341ba2d3cf75dc967fc12c883f1f4"
    ),
    "binary_in_archive": (
        "axiom-rules-engine-x86_64-unknown-linux-gnu/axiom-rules-engine"
    ),
}
AXIOM_TUPLE_PIN = {
    "id": "axiom",
    "release": ENGINE_PIN["release"],
    "commit": ENGINE_PIN["commit"],
    "asset_sha256": ENGINE_PIN["archive_sha256"],
    "metadata_claim_mode": "attested",
}

REPORT_PIN = {
    "path": "comparisons/de-worker-dual-oracle/unified-record.json",
    "binding": "generator_rederived",
    "generator": "scripts/de_unified_comparison.py",
    "record_schema": "axiom.unified_comparison_record.v1",
    "suite": "de-worker-dual-oracle",
    "view": PROGRAM,
}

# The engine's period schema: {period_kind, start, end} — it carries no
# display name, and the response echoes exactly this shape.
EXPECTED_PERIOD = {
    "period_kind": "tax_year",
    "start": "2025-01-01",
    "end": "2025-12-31",
}

POPULATION_PIN = {
    "id": "de-worker-dual-oracle-13-households",
    "sha256": "db63064fed6fa91fb3a34096b0997fed2e11ac52db2b22516e2e00da2aace951",
    "case_count": 13,
}

LEG_PINS = (
    {
        "id": "axiom-euromod",
        "oracle": "euromod",
        "path": "comparisons/de-worker-dual-oracle/axiom-euromod.json",
        "suite": "de-worker-dual-oracle-axiom-euromod",
    },
    {
        "id": "axiom-gettsim",
        "oracle": "gettsim",
        "path": "comparisons/de-worker-dual-oracle/axiom-gettsim.json",
        "suite": "de-worker-dual-oracle-axiom-gettsim",
    },
)

RULESPEC_PIN = {
    "descriptor_path": ("conformance/executable/de-kindergeld-signed-rulespec.json"),
    "descriptor_schema": SIGNED_ARTIFACT_SCHEMA,
    "repository": "TheAxiomFoundation/rulespec-de",
    # Reviewed rulespec-DE main snapshot shared by both registered Axiom legs.
    # Bumping this full commit (and its tree below) is an intentional, visible
    # comparison-config change; a working-tree HEAD is never accepted as a
    # substitute for the pinned bytes.
    "commit": "d83ba3db30e2f63376aacf822d116687589b8564",
    "tree": "1e75a045e32100544f057ffe335065c1ef99c1bc",
    "module_path": "de/statutes/estg/66.yaml",
    "encoding_manifest_path": (".axiom/encoding-manifests/de/statutes/estg/66.json"),
    "encoding_manifest_schema": "axiom-encode/applied-rulespec/v5",
    "citation_path": "de/statute/estg/66",
    "rule_name": "monthly_kindergeld_per_child",
    "effective_on": "2025-06-30",
    "imports": "forbidden",
    "signature_algorithm": "ed25519-domain-v1",
    "trusted_key_id": (
        "sha256:24a78725a23b1c83cfc38bdc22f75401d8008e7a8477796b55179d1fc79c4d9a"
    ),
    "corpus_release": "de-rulespec-2026-07-21",
    "corpus_release_content_sha256": (
        "b4b405a06bfcf21331cff50a45844fd0117b52212dc24d0f4912ed07575fd574"
    ),
}

ENGINE_VERSION_LINE = (
    f"axiom-rules-engine {ENGINE_PIN['release'].removeprefix('v')}"
)
RECEIPT_PATH = "conformance/executable/de-kindergeld-replay-receipt.json"
STATUS_PATH = "conformance/executable/de-kindergeld-status.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class DEExecutableError(ValueError):
    """The executable contract or one of its evidence inputs is invalid."""


def _canonical_bytes(value: object, *, ascii_only: bool = False) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ascii_only,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _render(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_text_atomic(path: Path, value: str) -> None:
    """Replace one generated artifact without exposing truncated JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise DEExecutableError(f"{label}: cannot read strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DEExecutableError(f"{label}: must contain a JSON object")
    return value


def _repo_path(repo_root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DEExecutableError(f"{label}: must be a non-empty repository path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in value:
        raise DEExecutableError(f"{label}: must be a contained repository path")
    root = repo_root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise DEExecutableError(f"{label}: escapes the repository")
    return resolved


def _require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise DEExecutableError(f"{label}: expected {expected!r}, found {actual!r}")


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise DEExecutableError(f"{label}: must be a lowercase SHA-256")
    return value


def _require_commit(value: object, label: str) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise DEExecutableError(f"{label}: must be a full lowercase commit SHA")
    return value


def _decode_base64(value: object, label: str) -> bytes:
    if not isinstance(value, str):
        raise DEExecutableError(f"{label}: must be base64 text")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise DEExecutableError(f"{label}: invalid base64") from exc


def _validate_manifest(document: dict[str, Any], repo_root: Path) -> None:
    _require_equal(document.get("schema"), MANIFEST_SCHEMA, "manifest.schema")
    _require_equal(document.get("program"), PROGRAM, "manifest.program")
    _require_equal(document.get("period"), PERIOD, "manifest.period")
    _require_equal(
        document.get("subgraph"),
        {"scope": "amount", "root_nodes": [ROOT_NODE]},
        "manifest.subgraph",
    )
    _require_equal(document.get("engine"), ENGINE_PIN, "manifest.engine")

    comparison = document.get("comparison_record")
    if not isinstance(comparison, dict):
        raise DEExecutableError("manifest.comparison_record must be an object")
    expected_comparison_fields = {
        *REPORT_PIN,
        "population",
        "axiom_leg_slots",
        "leg_record_contract",
    }
    _require_equal(
        set(comparison),
        expected_comparison_fields,
        "manifest.comparison_record fields",
    )
    for field, expected in REPORT_PIN.items():
        _require_equal(
            comparison.get(field), expected, f"manifest.comparison_record.{field}"
        )
    _require_equal(
        comparison.get("population"),
        POPULATION_PIN,
        "manifest.comparison_record.population",
    )
    _require_equal(
        comparison.get("axiom_leg_slots"),
        list(LEG_PINS),
        "manifest.comparison_record.axiom_leg_slots",
    )
    _require_equal(
        comparison.get("leg_record_contract"),
        {
            "record_schema": "axiom.unified_comparison_record.v1",
            "view_kind": "subgraph",
            "leg_producer": "scripts/de_executable.py::produce",
            "oracle_execution": "live_no_reemit_case_results",
            "oracle_result_claim_mode": "attested",
            "oracle_result_digest_claim_mode": "computed",
            "comparison_claim_mode": "computed",
            "replay_fixture_field": "executable_replay",
            "expected_results_source": "axiom_execution_case_records",
            "case_value_binding": (
                "left_equals_live_oracle_execution_and_right_equals_root_output_"
                "times_computed_child_count"
            ),
            "request_contract": (
                "exact_empty_dataset_2025_tax_year_amount_root_per_case"
            ),
            "result_contract": "exact_case_entity_period_scalar_eur_root",
            "oracle_identity_source": "unified_record_pinned_oracles",
            "axiom_identity_source": "manifest_engine_release",
            "source_aggregate_conservation": (
                "oracle_and_axiom_household_totals_equal_765_eur"
            ),
            "rulespec_binding": (
                "exact_pinned_commit_tree_signed_module_and_apply_manifest_sha256"
            ),
            "aggregate_expected_results": "forbidden",
        },
        "manifest.comparison_record.leg_record_contract",
    )
    _require_equal(
        document.get("signed_rulespec_artifact"),
        RULESPEC_PIN,
        "manifest.signed_rulespec_artifact",
    )
    replay = document.get("replay")
    if not isinstance(replay, dict):
        raise DEExecutableError("manifest.replay must be an object")
    _require_equal(replay.get("receipt_path"), RECEIPT_PATH, "manifest.replay.path")
    _require_equal(
        replay.get("receipt_schema"), REPLAY_SCHEMA, "manifest.replay.schema"
    )
    _require_equal(
        replay.get("request_source"),
        "exact_common_fixture_from_axiom_leg_slots",
        "manifest.replay.request_source",
    )
    _require_equal(
        replay.get("expected_results_source"),
        "exact_common_axiom_results_from_axiom_leg_slots",
        "manifest.replay.expected_results_source",
    )
    _require_equal(
        replay.get("aggregate_expected_results"),
        "forbidden",
        "manifest.replay.aggregate_expected_results",
    )
    _require_equal(
        replay.get("verification_mode"),
        "fresh_replay_from_embedded_release_archive",
        "manifest.replay.verification_mode",
    )
    _require_equal(
        replay.get("archive_storage"),
        "receipt_embedded_base64",
        "manifest.replay.archive_storage",
    )
    expected_commands = [
        ["axiom-rules-engine", "--version"],
        [
            "axiom-rules-engine",
            "compile",
            "--program",
            RULESPEC_PIN["module_path"],
            "--rulespec-root",
            "rulespec-de",
            "--output",
            "program.compiled.json",
        ],
        [
            "axiom-rules-engine",
            "run-compiled",
            "--artifact",
            "program.compiled.json",
        ],
    ]
    _require_equal(
        replay.get("required_commands"),
        expected_commands,
        "manifest.replay.required_commands",
    )
    _require_equal(document.get("status_path"), STATUS_PATH, "manifest.status_path")

    for label, value in (
        ("comparison report", REPORT_PIN["path"]),
        ("signed RuleSpec descriptor", RULESPEC_PIN["descriptor_path"]),
        ("replay receipt", RECEIPT_PATH),
        ("status", STATUS_PATH),
        *((f"leg {slot['id']}", slot["path"]) for slot in LEG_PINS),
    ):
        _repo_path(repo_root, value, label)


def load_manifest(
    path: Path = MANIFEST_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    document = _load_object(path, "DE executable manifest")
    _validate_manifest(document, repo_root)
    return document


def _validate_unified_record(
    manifest: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    contract = manifest["comparison_record"]
    path = _repo_path(repo_root, contract["path"], "comparison record")
    if not path.is_file():
        raise DEExecutableError(f"comparison record is missing: {contract['path']}")
    observed_sha = _sha256(path)
    record = _load_object(path, "unified DE comparison record")
    generator_path = _repo_path(
        repo_root, contract["generator"], "comparison record generator"
    )
    module_spec = importlib.util.spec_from_file_location(
        "_de_executable_unified", generator_path
    )
    if module_spec is None or module_spec.loader is None:
        raise DEExecutableError("cannot load the unified-record generator")
    generator = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(generator)
    try:
        expected_record = generator.build()
    except (OSError, ValueError) as exc:
        raise DEExecutableError(
            f"cannot rederive the unified comparison record: {exc}"
        ) from exc
    _require_equal(record, expected_record, "generator-rederived comparison record")
    _require_equal(
        record.get("record_schema"), contract["record_schema"], "record schema"
    )
    _require_equal(record.get("suite"), contract["suite"], "record suite")
    _require_equal(record.get("period"), PERIOD, "record period")

    population = (record.get("tuple") or {}).get("population")
    if not isinstance(population, dict):
        raise DEExecutableError("unified record lacks tuple.population")
    for field, expected in POPULATION_PIN.items():
        _require_equal(population.get(field), expected, f"record population.{field}")
    _require_equal(
        (record.get("dataset_identity") or {}).get("sha256"),
        POPULATION_PIN["sha256"],
        "record dataset population SHA-256",
    )

    cases = record.get("cases")
    if not isinstance(cases, list) or len(cases) != POPULATION_PIN["case_count"]:
        raise DEExecutableError("unified record must contain exactly 13 cases")
    case_ids = [row.get("case_id") for row in cases if isinstance(row, dict)]
    if (
        len(case_ids) != POPULATION_PIN["case_count"]
        or any(not isinstance(item, str) or not item for item in case_ids)
        or len(set(case_ids)) != len(case_ids)
    ):
        raise DEExecutableError("unified record case ids must be complete and unique")
    population_payload = {
        "id": POPULATION_PIN["id"],
        "period": PERIOD,
        "cases": cases,
    }
    _require_equal(
        _sha256_bytes(_canonical_bytes(population_payload)),
        POPULATION_PIN["sha256"],
        "rederived unified population SHA-256",
    )

    view = (record.get("views") or {}).get(contract["view"])
    if not isinstance(view, dict):
        raise DEExecutableError("unified record lacks the de/kindergeld view")
    _require_equal(view.get("kind"), "subgraph", "Kindergeld view kind")
    _require_equal(view.get("scope"), "amount", "Kindergeld view scope")
    _require_equal(view.get("root_nodes"), [ROOT_NODE], "Kindergeld root nodes")
    required_ids = [slot["id"] for slot in LEG_PINS]
    _require_equal(
        view.get("required_axiom_legs"), required_ids, "required Axiom leg ids"
    )
    raw_legs = view.get("legs")
    if not isinstance(raw_legs, list):
        raise DEExecutableError("Kindergeld view legs must be an array")
    axiom_rows = {
        row.get("id"): row
        for row in raw_legs
        if isinstance(row, dict) and str(row.get("id", "")).startswith("axiom-")
    }
    _require_equal(set(axiom_rows), set(required_ids), "unified Axiom leg slots")
    for slot in LEG_PINS:
        row = axiom_rows[slot["id"]]
        _require_equal(row.get("artifact"), slot["path"], f"{slot['id']} artifact")
        _require_equal(
            row.get("population_sha256"),
            POPULATION_PIN["sha256"],
            f"{slot['id']} population",
        )
        if row.get("state") not in {"pending", "complete"}:
            raise DEExecutableError(f"{slot['id']} has an invalid state")

    return {
        "path": contract["path"],
        "sha256": observed_sha,
        "case_ids": case_ids,
        "record": record,
    }


def _comparison_semantic_binding(unified: dict[str, Any]) -> dict[str, Any]:
    """Bind replay to stable certification semantics, not report bookkeeping.

    The generated unified record deliberately retains the full source-report
    digest for provenance.  Disposition or run-metadata refreshes can change
    that digest without changing the certified population, amount view, or
    source crosscheck.  A replay receipt therefore binds the latter semantic
    projection plus the two exact leg hashes separately.
    """

    record = unified.get("record")
    if not isinstance(record, dict):
        raise DEExecutableError("unified comparison record is unavailable")
    view = (record.get("views") or {}).get(PROGRAM)
    if not isinstance(view, dict):
        raise DEExecutableError("unified record lacks the Kindergeld amount view")
    legs = view.get("legs")
    if not isinstance(legs, list):
        raise DEExecutableError("unified Kindergeld view lacks comparison legs")
    source_legs = [
        row
        for row in legs
        if isinstance(row, dict) and row.get("id") == "euromod-gettsim"
    ]
    if len(source_legs) != 1:
        raise DEExecutableError("unified record needs one EUROMOD x GETTSIM source leg")
    payload = {
        "record_schema": record.get("record_schema"),
        "suite": record.get("suite"),
        "period": record.get("period"),
        "population": (record.get("tuple") or {}).get("population"),
        "cases": record.get("cases"),
        "amount_view": {
            "kind": view.get("kind"),
            "scope": view.get("scope"),
            "columns": view.get("columns"),
            "root_nodes": view.get("root_nodes"),
            "summary": view.get("summary"),
            "source_crosscheck": source_legs[0],
            "required_axiom_legs": view.get("required_axiom_legs"),
        },
    }
    return {
        "path": unified["path"],
        "semantic_sha256": _sha256_bytes(_canonical_bytes(payload)),
        "population_sha256": POPULATION_PIN["sha256"],
    }


def _clean_summary(summary: object, label: str) -> None:
    if not isinstance(summary, dict):
        raise DEExecutableError(f"{label}: summary must be an object")
    expected = POPULATION_PIN["case_count"]
    for field, value in (
        ("comparison_count", expected),
        ("match_count", expected),
        ("mismatch_count", 0),
        ("error_count", 0),
    ):
        _require_equal(summary.get(field), value, f"{label}.summary.{field}")


def _numeric_engine_output(
    result: object, label: str, *, expected_query: dict[str, Any] | None = None
) -> float:
    if not isinstance(result, dict):
        raise DEExecutableError(f"{label}: result must be an object")
    if result.get("errors") not in (None, []):
        raise DEExecutableError(f"{label}: result contains engine errors")
    if expected_query is not None:
        _require_equal(
            result.get("entity_id"), expected_query["entity_id"], f"{label}.entity_id"
        )
        _require_equal(
            result.get("period"), expected_query["period"], f"{label}.period"
        )
    outputs = result.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {ROOT_NODE}:
        raise DEExecutableError(f"{label}: amount root output is missing")
    output = outputs[ROOT_NODE]
    if not isinstance(output, dict):
        raise DEExecutableError(f"{label}: amount root output must be an object")
    _require_equal(output.get("kind"), "scalar", f"{label}.kind")
    _require_equal(output.get("id"), ROOT_NODE, f"{label}.id")
    _require_equal(output.get("name"), RULESPEC_PIN["rule_name"], f"{label}.name")
    _require_equal(output.get("unit"), "EUR", f"{label}.unit")
    dtype = output.get("dtype")
    if dtype not in {"integer", "decimal"}:
        raise DEExecutableError(f"{label}: amount root dtype is not numeric")
    value = output.get("value")
    if not isinstance(value, dict) or value.get("kind") != dtype:
        raise DEExecutableError(f"{label}: amount root value/dtype differ")
    value = value.get("value")
    if dtype == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        raise DEExecutableError(f"{label}: integer output is not an integer")
    if dtype == "decimal" and not isinstance(value, str):
        raise DEExecutableError(f"{label}: decimal output is not canonical text")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DEExecutableError(f"{label}: amount root is not numeric")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise DEExecutableError(f"{label}: amount root is not numeric") from exc
    if not math.isfinite(numeric):
        raise DEExecutableError(f"{label}: amount root is not finite")
    return numeric


def _validate_leg_record(
    path: Path,
    slot: dict[str, Any],
    manifest: dict[str, Any],
    unified: dict[str, Any],
) -> dict[str, Any]:
    record = _load_object(path, f"{slot['id']} leg")
    contract = manifest["comparison_record"]["leg_record_contract"]
    _require_equal(
        record.get("record_schema"), contract["record_schema"], f"{slot['id']} schema"
    )
    _require_equal(record.get("suite"), slot["suite"], f"{slot['id']} suite")
    _require_equal(record.get("period"), PERIOD, f"{slot['id']} period")
    _require_equal(
        record.get("engines"),
        {"left": slot["oracle"], "right": "axiom"},
        f"{slot['id']} engines",
    )
    tuple_block = record.get("tuple")
    if not isinstance(tuple_block, dict):
        raise DEExecutableError(f"{slot['id']}: tuple must be an object")
    _require_equal(tuple_block.get("jurisdiction"), "de", f"{slot['id']} jurisdiction")
    population = tuple_block.get("population")
    if not isinstance(population, dict):
        raise DEExecutableError(f"{slot['id']}: tuple.population must be an object")
    for field, expected in POPULATION_PIN.items():
        _require_equal(
            population.get(field), expected, f"{slot['id']} population.{field}"
        )
    oracle = tuple_block.get("oracle")
    source_oracles = (unified["record"].get("tuple") or {}).get("oracles")
    expected_oracle = (
        source_oracles.get(slot["oracle"]) if isinstance(source_oracles, dict) else None
    )
    if not isinstance(expected_oracle, dict):
        raise DEExecutableError(f"{slot['id']}: source oracle pin is missing")
    _require_equal(
        oracle,
        {"id": slot["oracle"], **expected_oracle},
        f"{slot['id']} oracle release tuple",
    )
    _require_equal(
        tuple_block.get("axiom"), AXIOM_TUPLE_PIN, f"{slot['id']} Axiom release tuple"
    )

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise DEExecutableError(f"{slot['id']}: provenance is missing")
    _require_equal(
        provenance.get("generated_by"),
        contract["leg_producer"],
        f"{slot['id']} live leg producer",
    )
    oracle_execution = provenance.get("oracle_execution")
    if not isinstance(oracle_execution, dict):
        raise DEExecutableError(f"{slot['id']}: live oracle execution is missing")
    _require_equal(
        oracle_execution.get("engine"),
        slot["oracle"],
        f"{slot['id']} live oracle engine",
    )
    _require_equal(
        oracle_execution.get("target"),
        ORACLE_TARGETS[slot["oracle"]],
        f"{slot['id']} live oracle target",
    )
    _require_equal(
        oracle_execution.get("mode"),
        "live_no_reemit",
        f"{slot['id']} live oracle mode",
    )
    _require_equal(
        oracle_execution.get("claim_mode"),
        contract["oracle_result_claim_mode"],
        f"{slot['id']} live oracle claim mode",
    )
    _require_equal(
        oracle_execution.get("engine_identity_claim_mode"),
        "attested",
        f"{slot['id']} oracle identity claim mode",
    )
    execution_rows = oracle_execution.get("case_results")
    if not isinstance(execution_rows, list):
        raise DEExecutableError(
            f"{slot['id']}: live oracle case results must be an array"
        )
    execution_sha = _sha256_bytes(_canonical_bytes(execution_rows))
    _require_equal(
        oracle_execution.get("case_results_sha256"),
        execution_sha,
        f"{slot['id']} live oracle results SHA-256",
    )
    _require_equal(
        oracle_execution.get("case_results_sha256_claim_mode"),
        contract["oracle_result_digest_claim_mode"],
        f"{slot['id']} live oracle results digest claim mode",
    )

    source_cases = unified["record"].get("cases")
    rows = record.get("cases")
    if (
        not isinstance(source_cases, list)
        or not isinstance(rows, list)
        or len(execution_rows) != POPULATION_PIN["case_count"]
        or len(rows) != POPULATION_PIN["case_count"]
    ):
        raise DEExecutableError(f"{slot['id']}: requires all 13 comparison rows")
    axiom_values: list[float] = []
    oracle_values: list[float] = []
    child_counts: list[int] = []
    for index, (source_case, row, execution_row) in enumerate(
        zip(source_cases, rows, execution_rows, strict=True)
    ):
        if not isinstance(source_case, dict) or not isinstance(row, dict):
            raise DEExecutableError(f"{slot['id']}: malformed case row {index}")
        case_id = source_case.get("case_id")
        _require_equal(row.get("case_id"), case_id, f"{slot['id']} case {index} id")
        if not isinstance(execution_row, dict):
            raise DEExecutableError(
                f"{slot['id']} {case_id}: malformed live oracle row"
            )
        _require_equal(
            execution_row.get("case_id"),
            case_id,
            f"{slot['id']} live oracle case {index} id",
        )
        _require_equal(
            row.get("left_engine"),
            slot["oracle"],
            f"{slot['id']} {case_id} left engine",
        )
        _require_equal(
            row.get("right_engine"),
            "axiom",
            f"{slot['id']} {case_id} right engine",
        )
        if row.get("left_errors") or row.get("right_errors"):
            raise DEExecutableError(f"{slot['id']} {case_id}: engine error")
        source_metadata = source_case.get("metadata")
        metadata = row.get("metadata")
        if not isinstance(source_metadata, dict) or not isinstance(metadata, dict):
            raise DEExecutableError(f"{slot['id']} {case_id}: metadata is missing")
        for name, expected in source_metadata.items():
            _require_equal(
                metadata.get(name), expected, f"{slot['id']} {case_id} input {name}"
            )
        child_count = source_metadata.get("child_count")
        if isinstance(child_count, bool) or not isinstance(child_count, int):
            raise DEExecutableError(f"{slot['id']} {case_id}: invalid child count")
        matches = row.get("matches")
        if (
            not isinstance(matches, list)
            or len(matches) != 1
            or not isinstance(matches[0], dict)
            or row.get("mismatches") != []
        ):
            raise DEExecutableError(
                f"{slot['id']} {case_id}: needs one match and no mismatch"
            )
        match = matches[0]
        _require_equal(
            match.get("concept"),
            KINDERGELD_CONCEPT,
            f"{slot['id']} {case_id} concept",
        )
        left = match.get("left")
        right = match.get("right")
        live_left = execution_row.get("value")
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or isinstance(live_left, bool)
            or not isinstance(left, (int, float))
            or not isinstance(right, (int, float))
            or not isinstance(live_left, (int, float))
            or not math.isfinite(float(left))
            or not math.isfinite(float(right))
            or not math.isfinite(float(live_left))
            or abs(float(left) - float(right)) > 0.01
        ):
            raise DEExecutableError(f"{slot['id']} {case_id}: unclean amount match")
        if abs(float(left) - float(live_left)) > 0.01:
            raise DEExecutableError(
                f"{slot['id']} {case_id}: comparison left is not the live oracle result"
            )
        axiom_values.append(float(right))
        oracle_values.append(float(left))
        child_counts.append(child_count)

    source_view = (unified["record"].get("views") or {}).get(PROGRAM)
    source_summary = (
        source_view.get("summary") if isinstance(source_view, dict) else None
    )
    source_sum_field = (
        "left_weighted_sum" if slot["oracle"] == "euromod" else "right_weighted_sum"
    )
    source_sum = (
        source_summary.get(source_sum_field)
        if isinstance(source_summary, dict)
        else None
    )
    if (
        isinstance(source_sum, bool)
        or not isinstance(source_sum, (int, float))
        or abs(math.fsum(oracle_values) - float(source_sum)) > 0.01
        or abs(math.fsum(axiom_values) - float(source_sum)) > 0.01
    ):
        raise DEExecutableError(
            f"{slot['id']}: case totals do not conserve the source aggregate"
        )
    view = (record.get("views") or {}).get(PROGRAM)
    if not isinstance(view, dict):
        raise DEExecutableError(f"{slot['id']}: missing de/kindergeld view")
    _require_equal(view.get("kind"), contract["view_kind"], f"{slot['id']} view kind")
    _require_equal(view.get("scope"), "amount", f"{slot['id']} view scope")
    _require_equal(
        view.get("claim_mode"),
        contract["comparison_claim_mode"],
        f"{slot['id']} view claim mode",
    )
    _require_equal(view.get("leg_id"), slot["id"], f"{slot['id']} view leg id")
    _require_equal(view.get("state"), "complete", f"{slot['id']} state")
    _require_equal(view.get("root_nodes"), [ROOT_NODE], f"{slot['id']} root nodes")
    _require_equal(view.get("columns"), [KINDERGELD_CONCEPT], f"{slot['id']} columns")
    _clean_summary(view.get("summary"), slot["id"])
    _require_equal(
        view.get("restatement"),
        {
            "root_node": ROOT_NODE,
            "column": KINDERGELD_CONCEPT,
            "operation": "multiply_root_amount_by_canonical_child_count",
            "input_source": "canonical_de_worker_dual_oracle_cases",
            "operation_claim_mode": "attested",
            "result_claim_mode": "computed",
        },
        f"{slot['id']} amount-subgraph restatement",
    )

    rulespec_artifact = provenance.get("rulespec_artifact")
    if not isinstance(rulespec_artifact, dict):
        raise DEExecutableError(f"{slot['id']}: rulespec artifact binding is missing")
    _require_equal(
        rulespec_artifact.get("citation_path"),
        RULESPEC_PIN["citation_path"],
        f"{slot['id']} rulespec citation",
    )
    _require_equal(
        rulespec_artifact.get("claim_mode"),
        "computed",
        f"{slot['id']} rulespec binding claim mode",
    )
    _require_equal(
        rulespec_artifact.get("commit"),
        RULESPEC_PIN["commit"],
        f"{slot['id']} rulespec pinned commit",
    )
    _require_equal(
        rulespec_artifact.get("tree"),
        RULESPEC_PIN["tree"],
        f"{slot['id']} rulespec pinned tree",
    )
    artifact_sha = _require_sha(
        rulespec_artifact.get("artifact_sha256"),
        f"{slot['id']} signed module SHA-256",
    )
    apply_manifest_sha = _require_sha(
        rulespec_artifact.get("apply_manifest_sha256"),
        f"{slot['id']} signed apply-manifest SHA-256",
    )

    fixture = view.get(contract["replay_fixture_field"])
    if not isinstance(fixture, dict):
        raise DEExecutableError(f"{slot['id']}: executable replay fixture is missing")
    _require_equal(
        fixture.get("expected_results_source"),
        contract["expected_results_source"],
        f"{slot['id']} expected-results source",
    )
    if (
        "aggregate" in fixture
        or "aggregate" in str(fixture.get("expected_results_source", "")).lower()
    ):
        raise DEExecutableError(
            f"{slot['id']}: an aggregate cannot supply replay expected results"
        )
    _require_equal(
        fixture.get("case_ids"), unified["case_ids"], f"{slot['id']} replay case ids"
    )
    request = fixture.get("request")
    expected_results = fixture.get("expected_results")
    if not isinstance(request, dict):
        raise DEExecutableError(f"{slot['id']}: replay request must be an object")
    if set(request) != {"mode", "dataset", "queries"}:
        raise DEExecutableError(f"{slot['id']}: replay request fields changed")
    _require_equal(request.get("mode"), "explain", f"{slot['id']} request mode")
    _require_equal(
        request.get("dataset"),
        {"inputs": [], "relations": []},
        f"{slot['id']} request dataset",
    )
    if not isinstance(expected_results, list):
        raise DEExecutableError(f"{slot['id']}: expected_results must be an array")
    if len(expected_results) != POPULATION_PIN["case_count"]:
        raise DEExecutableError(f"{slot['id']}: expected_results must contain 13 rows")
    queries = request.get("queries")
    if not isinstance(queries, list) or len(queries) != POPULATION_PIN["case_count"]:
        raise DEExecutableError(f"{slot['id']}: replay request must contain 13 queries")
    expected_queries = [
        {
            "entity_id": f"case-{index}::tax_unit",
            "period": EXPECTED_PERIOD,
            "outputs": [ROOT_NODE],
        }
        for index in range(POPULATION_PIN["case_count"])
    ]
    _require_equal(queries, expected_queries, f"{slot['id']} replay queries")
    request_sha = _sha256_bytes(_canonical_bytes(request))
    results_sha = _sha256_bytes(_canonical_bytes(expected_results))
    _require_equal(
        fixture.get("request_sha256"), request_sha, f"{slot['id']} request SHA-256"
    )
    _require_equal(
        fixture.get("expected_results_sha256"),
        results_sha,
        f"{slot['id']} expected-results SHA-256",
    )
    root_values: list[float] = []
    for index, (result, axiom_value, child_count, query) in enumerate(
        zip(expected_results, axiom_values, child_counts, queries, strict=True)
    ):
        per_child = _numeric_engine_output(
            result,
            f"{slot['id']} expected result {index}",
            expected_query=query,
        )
        root_values.append(per_child)
        if abs(per_child * child_count - axiom_value) > 0.01:
            raise DEExecutableError(
                f"{slot['id']}: expected result {index} does not bind to its "
                "Axiom household restatement"
            )
    if any(abs(value - root_values[0]) > 0.01 for value in root_values[1:]):
        raise DEExecutableError(
            f"{slot['id']}: parameter root returned case-varying values"
        )

    return {
        "id": slot["id"],
        "path": slot["path"],
        "sha256": _sha256(path),
        "request": request,
        "request_sha256": request_sha,
        "expected_results": expected_results,
        "expected_results_sha256": results_sha,
        "oracle_execution_sha256": execution_sha,
        "case_ids": list(unified["case_ids"]),
        "rulespec_artifact": {
            "citation_path": RULESPEC_PIN["citation_path"],
            "commit": RULESPEC_PIN["commit"],
            "tree": RULESPEC_PIN["tree"],
            "artifact_sha256": artifact_sha,
            "apply_manifest_sha256": apply_manifest_sha,
        },
    }


def _common_leg_fixture(legs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(legs) != len(LEG_PINS):
        raise DEExecutableError("both exact Axiom leg records are required")
    first, second = legs
    for field in (
        "case_ids",
        "request_sha256",
        "expected_results_sha256",
    ):
        _require_equal(second[field], first[field], f"Axiom legs common {field}")
    if _canonical_bytes(second["request"]) != _canonical_bytes(first["request"]):
        raise DEExecutableError("Axiom leg replay requests differ")
    if _canonical_bytes(second["expected_results"]) != _canonical_bytes(
        first["expected_results"]
    ):
        raise DEExecutableError("Axiom leg expected result rows differ")
    _require_equal(
        second["rulespec_artifact"],
        first["rulespec_artifact"],
        "Axiom legs common signed RuleSpec artifact",
    )
    return {
        "case_ids": first["case_ids"],
        "request": first["request"],
        "request_sha256": first["request_sha256"],
        "expected_results": first["expected_results"],
        "expected_results_sha256": first["expected_results_sha256"],
        "rulespec_artifact": first["rulespec_artifact"],
    }


def _unsigned_encoding_manifest_bytes(payload: dict[str, Any]) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    return _canonical_bytes(unsigned, ascii_only=True)


def _verify_apply_signature(
    payload: dict[str, Any], public_key: bytes, contract: dict[str, Any]
) -> None:
    if len(public_key) != 32:
        raise DEExecutableError("apply signing public key must contain 32 raw bytes")
    key_id = f"sha256:{_sha256_bytes(public_key)}"
    _require_equal(key_id, contract["trusted_key_id"], "apply signing key id")
    signature = payload.get("signature")
    if not isinstance(signature, dict):
        raise DEExecutableError("encoding manifest signature is missing")
    _require_equal(
        signature.get("algorithm"),
        contract["signature_algorithm"],
        "encoding manifest signature algorithm",
    )
    _require_equal(
        signature.get("key_id"), contract["trusted_key_id"], "signature key id"
    )
    raw_signature = _decode_base64(signature.get("value"), "encoding signature")
    if len(raw_signature) != 64:
        raise DEExecutableError("encoding signature must contain 64 raw bytes")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise DEExecutableError(
            "cryptography is required once the signed RuleSpec artifact lands"
        ) from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            raw_signature,
            APPLY_SIGNATURE_DOMAIN + _unsigned_encoding_manifest_bytes(payload),
        )
    except (InvalidSignature, ValueError) as exc:
        raise DEExecutableError(
            "encoding manifest Ed25519 signature is invalid"
        ) from exc


def _validate_effective_rule(module: dict[str, Any], contract: dict[str, Any]) -> None:
    _require_equal(module.get("format"), "rulespec/v1", "RuleSpec format")
    if contract["imports"] == "forbidden" and module.get("imports") not in (None, []):
        raise DEExecutableError(
            "the signed amount module must not import other modules"
        )
    module_metadata = module.get("module")
    if not isinstance(module_metadata, dict):
        raise DEExecutableError("signed RuleSpec lacks module metadata")
    source_verification = module_metadata.get("source_verification")
    if not isinstance(source_verification, dict):
        raise DEExecutableError("signed RuleSpec lacks source verification")
    _require_equal(
        source_verification.get("corpus_citation_path"),
        contract["citation_path"],
        "RuleSpec source citation",
    )
    rules = module.get("rules")
    if not isinstance(rules, list):
        raise DEExecutableError("signed RuleSpec rules must be an array")
    matching = [
        row
        for row in rules
        if isinstance(row, dict) and row.get("name") == contract["rule_name"]
    ]
    if len(matching) != 1:
        raise DEExecutableError(
            "signed RuleSpec must contain the exact amount root rule"
        )
    rule = matching[0]
    _require_equal(rule.get("kind"), "parameter", "signed amount rule kind")
    _require_equal(rule.get("dtype"), "Money", "signed amount rule dtype")
    _require_equal(rule.get("unit"), "EUR", "signed amount rule unit")
    versions = rule.get("versions")
    if not isinstance(versions, list) or not versions:
        raise DEExecutableError("signed amount root rule has no versions")
    effective_on = date.fromisoformat(contract["effective_on"])
    selected = []
    for row in versions:
        if not isinstance(row, dict) or not isinstance(row.get("effective_from"), str):
            raise DEExecutableError("signed amount rule has a malformed version")
        try:
            start = date.fromisoformat(row["effective_from"])
        except ValueError as exc:
            raise DEExecutableError(
                "signed amount rule has an invalid effective date"
            ) from exc
        if start <= effective_on:
            selected.append((start, row))
    if not selected or "formula" not in max(selected, key=lambda item: item[0])[1]:
        raise DEExecutableError("signed amount rule has no formula effective for 2025")


def _validate_signed_descriptor_document(
    document: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    contract = manifest["signed_rulespec_artifact"]
    _require_equal(
        document.get("schema"), contract["descriptor_schema"], "descriptor schema"
    )
    _require_equal(document.get("program"), PROGRAM, "descriptor program")
    _require_equal(document.get("period"), PERIOD, "descriptor period")
    checkout = document.get("checkout_observation")
    if not isinstance(checkout, dict):
        raise DEExecutableError("signed descriptor lacks checkout observation")
    _require_equal(
        checkout.get("repository"), contract["repository"], "checkout repository"
    )
    checkout_commit = _require_commit(
        checkout.get("commit"), "checkout observation commit"
    )
    _require_equal(
        checkout_commit,
        contract["commit"],
        "checkout observation pinned commit",
    )
    _require_equal(
        checkout.get("tree"),
        contract["tree"],
        "checkout observation pinned tree",
    )
    _require_equal(
        checkout.get("claim_mode"), "attested", "checkout observation claim mode"
    )

    module_block = document.get("module")
    if not isinstance(module_block, dict):
        raise DEExecutableError("signed descriptor module must be an object")
    _require_equal(
        module_block.get("path"), contract["module_path"], "descriptor module path"
    )
    module_bytes = _decode_base64(
        module_block.get("bytes_base64"), "signed module bytes"
    )
    module_sha = _sha256_bytes(module_bytes)
    _require_equal(module_block.get("sha256"), module_sha, "signed module SHA-256")
    try:
        parsed_module = yaml.safe_load(module_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise DEExecutableError(
            "signed module is not valid UTF-8 RuleSpec YAML"
        ) from exc
    if not isinstance(parsed_module, dict):
        raise DEExecutableError("signed module YAML must contain an object")
    _validate_effective_rule(parsed_module, contract)

    encoding_block = document.get("encoding_manifest")
    if not isinstance(encoding_block, dict):
        raise DEExecutableError("descriptor encoding_manifest must be an object")
    _require_equal(
        encoding_block.get("path"),
        contract["encoding_manifest_path"],
        "descriptor encoding manifest path",
    )
    encoding_bytes = _decode_base64(
        encoding_block.get("bytes_base64"), "signed encoding manifest bytes"
    )
    source_file_sha = _sha256_bytes(encoding_bytes)
    _require_equal(
        encoding_block.get("source_file_sha256"),
        source_file_sha,
        "encoding manifest source-file SHA-256",
    )
    try:
        payload = strict_json_loads(encoding_bytes)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DEExecutableError(
            "signed encoding manifest bytes are not strict JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise DEExecutableError("signed encoding manifest must contain an object")
    _require_equal(
        encoding_block.get("payload"),
        payload,
        "descriptor encoding manifest payload",
    )
    payload_sha = _sha256_bytes(_canonical_bytes(payload))
    _require_equal(
        encoding_block.get("payload_sha256"),
        payload_sha,
        "encoding manifest payload SHA-256",
    )
    _require_equal(
        payload.get("schema_version"),
        contract["encoding_manifest_schema"],
        "encoding manifest schema",
    )
    _require_equal(
        payload.get("citation"), contract["citation_path"], "encoding citation"
    )
    applied = payload.get("applied_files")
    if not isinstance(applied, list):
        raise DEExecutableError("encoding manifest applied_files must be an array")
    module_rows = [
        row
        for row in applied
        if isinstance(row, dict) and row.get("path") == contract["module_path"]
    ]
    if len(module_rows) != 1:
        raise DEExecutableError("encoding manifest must bind the exact EStG 66 module")
    _require_equal(
        module_rows[0].get("sha256"), module_sha, "encoding manifest module SHA-256"
    )
    attestation = payload.get("source_attestation")
    if not isinstance(attestation, dict):
        raise DEExecutableError("encoding manifest lacks source attestation")
    for field in ("requested_corpus_citation_path", "resolved_corpus_citation_path"):
        _require_equal(
            attestation.get(field),
            contract["citation_path"],
            f"source attestation {field}",
        )
    _require_equal(
        attestation.get("corpus_release"),
        contract["corpus_release"],
        "source attestation corpus release",
    )
    _require_equal(
        attestation.get("corpus_release_content_sha256"),
        contract["corpus_release_content_sha256"],
        "source attestation corpus release hash",
    )
    trust = document.get("signature_trust")
    if not isinstance(trust, dict):
        raise DEExecutableError("signed descriptor lacks signature trust material")
    public_key = _decode_base64(trust.get("public_key_base64"), "apply public key")
    _require_equal(
        trust.get("key_id"), contract["trusted_key_id"], "descriptor trust key id"
    )
    _verify_apply_signature(payload, public_key, contract)
    return {
        "checkout_observation": {
            "repository": contract["repository"],
            "commit": checkout_commit,
            "tree": contract["tree"],
            "claim_mode": "attested",
        },
        "module_sha256": module_sha,
        "module_bytes": module_bytes,
        "encoding_payload_sha256": payload_sha,
        "encoding_source_file_sha256": source_file_sha,
        "trusted_key_id": contract["trusted_key_id"],
        "public_key": public_key,
    }


def _validate_signed_descriptor(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    document = _load_object(path, "signed RuleSpec descriptor")
    result = _validate_signed_descriptor_document(document, manifest)
    return {**result, "path": RULESPEC_PIN["descriptor_path"], "sha256": _sha256(path)}


def _validate_replay_receipt(
    path: Path,
    manifest: dict[str, Any],
    unified: dict[str, Any],
    legs: list[dict[str, Any]],
    fixture: dict[str, Any],
    descriptor: dict[str, Any],
    replay_executor: Callable[[bytes, dict[str, Any], dict[str, Any]], dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    receipt = _load_object(path, "release-binary replay receipt")
    _require_equal(receipt.get("schema"), REPLAY_SCHEMA, "replay receipt schema")
    _require_equal(receipt.get("program"), PROGRAM, "replay receipt program")
    _require_equal(receipt.get("period"), PERIOD, "replay receipt period")
    _require_equal(receipt.get("claim_mode"), "computed", "replay receipt claim mode")

    engine = receipt.get("engine")
    if not isinstance(engine, dict):
        raise DEExecutableError("replay receipt engine must be an object")
    for field, expected in ENGINE_PIN.items():
        _require_equal(engine.get(field), expected, f"receipt engine.{field}")
    recorded_binary_sha = _require_sha(
        engine.get("binary_sha256"), "receipt engine binary SHA-256"
    )
    _require_equal(
        engine.get("version_stdout"),
        ENGINE_VERSION_LINE,
        "receipt engine version",
    )

    release_archive = receipt.get("release_archive")
    if not isinstance(release_archive, dict):
        raise DEExecutableError(
            "replay receipt must embed the pinned release archive for fresh verification"
        )
    _require_equal(
        release_archive.get("encoding"),
        "base64",
        "receipt release archive encoding",
    )
    _require_equal(
        release_archive.get("asset"),
        ENGINE_PIN["asset"],
        "receipt release archive asset",
    )
    _require_equal(
        release_archive.get("sha256"),
        ENGINE_PIN["archive_sha256"],
        "receipt release archive SHA-256 claim",
    )
    archive_bytes = _decode_base64(
        release_archive.get("bytes_base64"), "embedded release archive"
    )
    _require_equal(
        _sha256_bytes(archive_bytes),
        ENGINE_PIN["archive_sha256"],
        "embedded release archive SHA-256",
    )

    comparison = receipt.get("comparison_record")
    _require_equal(
        comparison,
        _comparison_semantic_binding(unified),
        "receipt comparison record binding",
    )
    signed = receipt.get("signed_rulespec_artifact")
    _require_equal(
        signed,
        {
            "path": descriptor["path"],
            "sha256": descriptor["sha256"],
            "commit": RULESPEC_PIN["commit"],
            "tree": RULESPEC_PIN["tree"],
            "module_sha256": descriptor["module_sha256"],
            "encoding_manifest_payload_sha256": descriptor["encoding_payload_sha256"],
            "encoding_manifest_source_file_sha256": descriptor[
                "encoding_source_file_sha256"
            ],
            "trusted_key_id": descriptor["trusted_key_id"],
        },
        "receipt signed RuleSpec binding",
    )
    expected_legs = [
        {"id": row["id"], "path": row["path"], "sha256": row["sha256"]} for row in legs
    ]
    _require_equal(receipt.get("axiom_legs"), expected_legs, "receipt Axiom legs")
    _require_equal(
        fixture["rulespec_artifact"],
        {
            "citation_path": RULESPEC_PIN["citation_path"],
            "commit": RULESPEC_PIN["commit"],
            "tree": RULESPEC_PIN["tree"],
            "artifact_sha256": descriptor["module_sha256"],
            "apply_manifest_sha256": descriptor["encoding_source_file_sha256"],
        },
        "Axiom-leg signed RuleSpec binding",
    )

    execution = receipt.get("execution")
    if not isinstance(execution, dict):
        raise DEExecutableError("receipt execution must be an object")
    expected_commands = [
        {"argv": argv, "exit_code": 0}
        for argv in manifest["replay"]["required_commands"]
    ]
    _require_equal(execution.get("commands"), expected_commands, "receipt commands")
    _require_equal(
        execution.get("request_source"),
        manifest["replay"]["request_source"],
        "receipt request source",
    )
    _require_equal(
        execution.get("expected_results_source"),
        manifest["replay"]["expected_results_source"],
        "receipt expected-results source",
    )
    _require_equal(
        execution.get("verification_mode"),
        manifest["replay"]["verification_mode"],
        "receipt verification mode",
    )
    if (
        "aggregate" in execution
        or "aggregate" in str(execution.get("expected_results_source", "")).lower()
    ):
        raise DEExecutableError(
            "receipt may not derive expected results from an aggregate"
        )
    _require_equal(
        execution.get("request_sha256"),
        fixture["request_sha256"],
        "receipt request SHA-256",
    )
    _require_equal(
        execution.get("expected_results_sha256"),
        fixture["expected_results_sha256"],
        "receipt expected-results SHA-256",
    )
    # The receipt is evidence storage, not authority.  Re-execute the exact
    # published archive bytes here so a forged transcript/results array cannot
    # ever promote the computed premise.
    fresh = (replay_executor or _execute_release_archive)(
        archive_bytes, descriptor, fixture
    )
    _require_equal(
        recorded_binary_sha,
        fresh["binary_sha256"],
        "fresh release binary SHA-256",
    )
    _require_equal(
        engine.get("version_stdout"),
        fresh["version_stdout"],
        "fresh engine version stdout",
    )
    observed = execution.get("observed_results")
    if not isinstance(observed, list):
        raise DEExecutableError("receipt observed_results must be an array")
    observed_sha = _sha256_bytes(_canonical_bytes(observed))
    _require_equal(
        execution.get("observed_results_sha256"),
        observed_sha,
        "receipt observed-results SHA-256",
    )
    _require_equal(observed, fixture["expected_results"], "release replay results")
    _require_equal(
        observed,
        fresh["observed_results"],
        "fresh release replay results",
    )
    _require_equal(
        execution.get("result_count"),
        POPULATION_PIN["case_count"],
        "receipt result count",
    )
    _require_sha(
        execution.get("compiled_artifact_sha256"),
        "compiled artifact SHA-256",
    )
    _require_sha(execution.get("stdout_sha256"), "engine stdout SHA-256")
    _require_equal(
        execution.get("compiled_artifact_sha256"),
        fresh["compiled_artifact_sha256"],
        "fresh compiled artifact SHA-256",
    )
    _require_equal(
        execution.get("stdout_sha256"),
        fresh["stdout_sha256"],
        "fresh engine stdout SHA-256",
    )
    return {
        "path": RECEIPT_PATH,
        "sha256": _sha256(path),
        "verification_mode": manifest["replay"]["verification_mode"],
        "fresh_binary_sha256": fresh["binary_sha256"],
        "fresh_observed_results_sha256": fresh["observed_results_sha256"],
    }


def _input_row(
    input_id: str,
    path: str,
    state: str,
    reason: str,
    **evidence: object,
) -> dict[str, Any]:
    return {
        "id": input_id,
        "path": path,
        "state": state,
        "reason": reason,
        **evidence,
    }


def _validate_pending_leg_record(
    path: Path,
    slot: dict[str, Any],
    unified: dict[str, Any],
) -> dict[str, Any]:
    """Accept only the producer-rederived module-not-on-main pending state."""

    record = _load_object(path, f"{slot['id']} pending comparison leg")
    try:
        module = importlib.import_module("scripts.de_axiom_legs")
        module.validate(record, slot["oracle"])
    except (ImportError, OSError, ValueError) as exc:
        raise DEExecutableError(
            f"{slot['id']} pending comparison record is invalid: {exc}"
        ) from exc
    if record.get("state") != "leg-pending" or record.get("pending") != (
        "module-not-on-main"
    ):
        raise DEExecutableError(f"{slot['id']} pending marker changed")
    view = (record.get("views") or {}).get(PROGRAM)
    if (
        not isinstance(view, dict)
        or view.get("state") != "leg-pending"
        or view.get("pending") != "module-not-on-main"
        or view.get("dependency_set", {}).get("complete_on_pinned_ref") is not False
    ):
        raise DEExecutableError(f"{slot['id']} Kindergeld pending view changed")
    unified_view = (unified["record"].get("views") or {}).get(PROGRAM) or {}
    unified_rows = unified_view.get("legs") or []
    unified_row = next(
        (
            row
            for row in unified_rows
            if isinstance(row, dict) and row.get("id") == slot["id"]
        ),
        None,
    )
    observed_sha = _sha256(path)
    if (
        not isinstance(unified_row, dict)
        or unified_row.get("state") != "pending"
        or unified_row.get("pending") != "module-not-on-main"
        or unified_row.get("artifact_sha256") != observed_sha
    ):
        raise DEExecutableError(
            f"{slot['id']} pending record does not bind to the unified view"
        )
    return {"sha256": observed_sha, "pending": "module-not-on-main"}


def build_status(
    *,
    manifest_path: Path = MANIFEST_PATH,
    repo_root: Path = REPO_ROOT,
    replay_executor: Callable[[bytes, dict[str, Any], dict[str, Any]], dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Recompute the executable verdict from the manifest and exact inputs."""

    manifest = load_manifest(manifest_path, repo_root=repo_root)
    unified = _validate_unified_record(manifest, repo_root)
    required_inputs: list[dict[str, Any]] = []
    valid_legs: list[dict[str, Any]] = []

    for slot in LEG_PINS:
        path = _repo_path(repo_root, slot["path"], f"{slot['id']} path")
        if not path.is_file():
            required_inputs.append(
                _input_row(
                    slot["id"],
                    slot["path"],
                    "missing",
                    "required Axiom comparison leg is absent",
                )
            )
            continue
        try:
            candidate = _load_object(path, f"{slot['id']} comparison leg")
        except DEExecutableError as exc:
            required_inputs.append(
                _input_row(slot["id"], slot["path"], "invalid", str(exc))
            )
            continue
        if candidate.get("state") == "leg-pending":
            try:
                pending_leg = _validate_pending_leg_record(
                    path, slot, unified
                )
            except DEExecutableError as exc:
                required_inputs.append(
                    _input_row(slot["id"], slot["path"], "invalid", str(exc))
                )
            else:
                required_inputs.append(
                    _input_row(
                        slot["id"],
                        slot["path"],
                        "pending",
                        "pending: module-not-on-main",
                        pending="module-not-on-main",
                        sha256=pending_leg["sha256"],
                    )
                )
            continue
        try:
            leg = _validate_leg_record(path, slot, manifest, unified)
        except DEExecutableError as exc:
            required_inputs.append(
                _input_row(slot["id"], slot["path"], "invalid", str(exc))
            )
        else:
            valid_legs.append(leg)
            required_inputs.append(
                _input_row(
                    slot["id"],
                    slot["path"],
                    "valid",
                    "exact unified Axiom leg and replay fixture validated",
                    sha256=leg["sha256"],
                    request_sha256=leg["request_sha256"],
                    expected_results_sha256=leg["expected_results_sha256"],
                )
            )

    common_fixture: dict[str, Any] | None = None
    if len(valid_legs) == len(LEG_PINS):
        try:
            common_fixture = _common_leg_fixture(valid_legs)
        except DEExecutableError as exc:
            reason = f"cross-leg consistency failed: {exc}"
            invalid_ids = {row["id"] for row in valid_legs}
            for row in required_inputs:
                if row["id"] in invalid_ids:
                    row["state"] = "invalid"
                    row["reason"] = reason
            valid_legs = []

    descriptor_path = _repo_path(
        repo_root,
        RULESPEC_PIN["descriptor_path"],
        "signed RuleSpec descriptor path",
    )
    descriptor: dict[str, Any] | None = None
    if not descriptor_path.is_file():
        required_inputs.append(
            _input_row(
                "signed-rulespec-estg-66-2025",
                RULESPEC_PIN["descriptor_path"],
                "missing",
                "signed RuleSpec-DE EStG section 66 artifact is absent",
            )
        )
    else:
        try:
            descriptor = _validate_signed_descriptor(descriptor_path, manifest)
        except DEExecutableError as exc:
            required_inputs.append(
                _input_row(
                    "signed-rulespec-estg-66-2025",
                    RULESPEC_PIN["descriptor_path"],
                    "invalid",
                    str(exc),
                )
            )
        else:
            required_inputs.append(
                _input_row(
                    "signed-rulespec-estg-66-2025",
                    RULESPEC_PIN["descriptor_path"],
                    "valid",
                    "module bytes, corpus binding, and Ed25519 signature validated",
                    sha256=descriptor["sha256"],
                    module_sha256=descriptor["module_sha256"],
                    encoding_manifest_payload_sha256=descriptor[
                        "encoding_payload_sha256"
                    ],
                    encoding_manifest_source_file_sha256=descriptor[
                        "encoding_source_file_sha256"
                    ],
                    trusted_key_id=descriptor["trusted_key_id"],
                    checkout_observation=descriptor["checkout_observation"],
                )
            )

    receipt_path = _repo_path(repo_root, RECEIPT_PATH, "replay receipt path")
    if not receipt_path.is_file():
        required_inputs.append(
            _input_row(
                "release-binary-replay-receipt",
                RECEIPT_PATH,
                "missing",
                "actual pinned release-binary replay receipt is absent",
            )
        )
    elif common_fixture is None or descriptor is None:
        required_inputs.append(
            _input_row(
                "release-binary-replay-receipt",
                RECEIPT_PATH,
                "invalid",
                "receipt cannot validate without both Axiom legs and the signed RuleSpec artifact",
            )
        )
    else:
        try:
            receipt = _validate_replay_receipt(
                receipt_path,
                manifest,
                unified,
                valid_legs,
                common_fixture,
                descriptor,
                replay_executor,
            )
        except DEExecutableError as exc:
            required_inputs.append(
                _input_row(
                    "release-binary-replay-receipt",
                    RECEIPT_PATH,
                    "invalid",
                    str(exc),
                )
            )
        else:
            required_inputs.append(
                _input_row(
                    "release-binary-replay-receipt",
                    RECEIPT_PATH,
                    "valid",
                    "verifier freshly reran pinned release bytes and reproduced exact Axiom-leg result rows",
                    sha256=receipt["sha256"],
                    verification_mode=receipt["verification_mode"],
                    fresh_binary_sha256=receipt["fresh_binary_sha256"],
                    fresh_observed_results_sha256=receipt[
                        "fresh_observed_results_sha256"
                    ],
                )
            )

    missing = [row["id"] for row in required_inputs if row["state"] == "missing"]
    pending = [row["id"] for row in required_inputs if row["state"] == "pending"]
    invalid = [row["id"] for row in required_inputs if row["state"] == "invalid"]
    value = bool(required_inputs) and all(
        row["state"] == "valid" for row in required_inputs
    )
    if value:
        state = "computed_pass"
    elif invalid:
        state = "computed_invalid"
    else:
        state = "computed_pending"
    blockers = [
        f"{row['id']}: {row['reason']}"
        for row in required_inputs
        if row["state"] != "valid"
    ]
    return {
        "schema": STATUS_SCHEMA,
        "program": PROGRAM,
        "period": PERIOD,
        "mode": "computed",
        "value": value,
        "state": state,
        "subgraph": manifest["subgraph"],
        "engine": dict(ENGINE_PIN),
        "population": dict(POPULATION_PIN),
        "comparison_record": {
            "path": unified["path"],
            "sha256": unified["sha256"],
        },
        "manifest": {
            "path": manifest_path.relative_to(repo_root).as_posix(),
            "sha256": _sha256(manifest_path),
        },
        "required_inputs": required_inputs,
        "missing_inputs": missing,
        "pending_inputs": pending,
        "invalid_inputs": invalid,
        "blockers": blockers,
        "expected_results_policy": {
            "source": "exact common Axiom execution rows from both required leg records",
            "source_aggregate_allowed": False,
            "verification": manifest["replay"]["verification_mode"],
            "note": (
                "The EUROMOD x GETTSIM aggregate constrains population-level and "
                "household-total conservation, but it contains no stored per-case "
                "matched outputs and never supplies replay expected-result rows."
            ),
        },
    }


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=not binary,
        check=False,
    )
    if process.returncode:
        stderr = process.stderr.decode(errors="replace") if binary else process.stderr
        stdout = process.stdout.decode(errors="replace") if binary else process.stdout
        raise DEExecutableError((stderr or stdout).strip() or "git command failed")
    return process.stdout


def _load_public_key(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) == 32:
        return raw
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise DEExecutableError("signing public key is neither raw nor UTF-8") from exc
    try:
        parsed = strict_json_loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        text = str(parsed.get("public_key_base64", ""))
    return _decode_base64(text, "signing public key")


def _build_signed_descriptor(
    manifest: dict[str, Any], rulespec_root: Path, public_key: bytes
) -> dict[str, Any]:
    contract = manifest["signed_rulespec_artifact"]
    commit = str(
        _git(rulespec_root, "rev-parse", f"{contract['commit']}^{{commit}}")
    ).strip()
    _require_commit(commit, "RuleSpec repository commit")
    _require_equal(commit, contract["commit"], "RuleSpec pinned commit")
    tree = str(_git(rulespec_root, "rev-parse", f"{commit}^{{tree}}")).strip()
    _require_commit(tree, "RuleSpec repository tree")
    _require_equal(tree, contract["tree"], "RuleSpec pinned tree")
    try:
        module_bytes = _git(
            rulespec_root, "show", f"{commit}:{contract['module_path']}", binary=True
        )
        encoding_bytes = _git(
            rulespec_root,
            "show",
            f"{commit}:{contract['encoding_manifest_path']}",
            binary=True,
        )
    except DEExecutableError as exc:
        raise DEExecutableError(
            "pinned rulespec ref lacks EStG 66 module or encoding manifest"
        ) from exc
    assert isinstance(module_bytes, bytes) and isinstance(encoding_bytes, bytes)
    try:
        encoding_payload = strict_json_loads(encoding_bytes)
    except ValueError as exc:
        raise DEExecutableError("encoding manifest is not strict JSON") from exc
    if not isinstance(encoding_payload, dict):
        raise DEExecutableError("encoding manifest must contain an object")
    descriptor = {
        "schema": contract["descriptor_schema"],
        "program": PROGRAM,
        "period": PERIOD,
        "checkout_observation": {
            "repository": contract["repository"],
            "commit": commit,
            "tree": tree,
            "claim_mode": "attested",
        },
        "module": {
            "path": contract["module_path"],
            "sha256": _sha256_bytes(module_bytes),
            "bytes_base64": base64.b64encode(module_bytes).decode("ascii"),
        },
        "encoding_manifest": {
            "path": contract["encoding_manifest_path"],
            "source_file_sha256": _sha256_bytes(encoding_bytes),
            "bytes_base64": base64.b64encode(encoding_bytes).decode("ascii"),
            "payload_sha256": _sha256_bytes(_canonical_bytes(encoding_payload)),
            "payload": encoding_payload,
        },
        "signature_trust": {
            "key_id": f"sha256:{_sha256_bytes(public_key)}",
            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
        },
    }
    _validate_signed_descriptor_document(descriptor, manifest)
    return descriptor


def _extract_release(archive: Path, destination: Path) -> Path:
    try:
        with tarfile.open(archive, mode="r:xz") as bundle:
            for member in bundle.getmembers():
                member_path = Path(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or member.issym()
                    or member.islnk()
                ):
                    raise DEExecutableError("release archive contains an unsafe path")
            bundle.extractall(destination, filter="data")
    except (OSError, tarfile.TarError) as exc:
        raise DEExecutableError(f"cannot extract release archive: {exc}") from exc
    binary = destination / ENGINE_PIN["binary_in_archive"]
    if not binary.is_file():
        raise DEExecutableError("release archive lacks the pinned engine binary")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def _run_process(
    argv: list[str], *, input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        process = subprocess.run(
            argv,
            input=input_bytes,
            capture_output=True,
            check=False,
            timeout=120,
            env={
                "HOME": "/nonexistent",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
                "TZ": "UTC",
                **(
                    {"SYSTEMROOT": os.environ["SYSTEMROOT"]}
                    if "SYSTEMROOT" in os.environ
                    else {}
                ),
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DEExecutableError(
            f"cannot execute pinned release command: {exc}"
        ) from exc
    if process.returncode:
        detail = (process.stderr or process.stdout).decode(errors="replace").strip()
        raise DEExecutableError(
            f"release command exited {process.returncode}: {detail[:1000]}"
        )
    return process


def _execute_release_archive_raw(
    archive_bytes: bytes,
    descriptor: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Compile and run an exact request from pinned release bytes."""

    _require_equal(
        _sha256_bytes(archive_bytes),
        ENGINE_PIN["archive_sha256"],
        "engine archive SHA-256",
    )
    with tempfile.TemporaryDirectory(prefix="de-kindergeld-replay-") as raw_tmp:
        temp = Path(raw_tmp)
        archive = temp / ENGINE_PIN["asset"]
        archive.write_bytes(archive_bytes)
        binary = _extract_release(archive, temp / "engine")
        version = _run_process([str(binary), "--version"])
        try:
            version_stdout = version.stdout.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise DEExecutableError("engine version output is not UTF-8") from exc
        _require_equal(
            version_stdout, ENGINE_VERSION_LINE, "engine version stdout"
        )

        staged_root = temp / "rulespec-de"
        staged_module = staged_root / RULESPEC_PIN["module_path"]
        staged_module.parent.mkdir(parents=True)
        staged_module.write_bytes(descriptor["module_bytes"])
        artifact = temp / "program.compiled.json"
        _run_process(
            [
                str(binary),
                "compile",
                "--program",
                str(staged_module),
                "--rulespec-root",
                str(staged_root),
                "--output",
                str(artifact),
            ]
        )
        if not artifact.is_file():
            raise DEExecutableError("release compile emitted no artifact")
        request_bytes = _canonical_bytes(request)
        replay = _run_process(
            [str(binary), "run-compiled", "--artifact", str(artifact)],
            input_bytes=request_bytes,
        )
        try:
            response = strict_json_loads(replay.stdout)
        except ValueError as exc:
            raise DEExecutableError("release replay emitted invalid JSON") from exc
        if not isinstance(response, dict) or not isinstance(
            response.get("results"), list
        ):
            raise DEExecutableError("release replay response lacks a results array")
        observed_results = response["results"]
        return {
            "binary_sha256": _sha256(binary),
            "version_stdout": version_stdout,
            "compiled_artifact_sha256": _sha256(artifact),
            "stdout_sha256": _sha256_bytes(replay.stdout),
            "observed_results": observed_results,
            "observed_results_sha256": _sha256_bytes(
                _canonical_bytes(observed_results)
            ),
        }


def _execute_release_archive(
    archive_bytes: bytes,
    descriptor: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Freshly replay exact committed rows; never trust the stored transcript."""

    result = _execute_release_archive_raw(
        archive_bytes,
        descriptor,
        fixture["request"],
    )
    _require_equal(
        result["observed_results"],
        fixture["expected_results"],
        "release-binary replay results",
    )
    return result


def _amount_request() -> dict[str, Any]:
    return {
        "mode": "explain",
        "dataset": {"inputs": [], "relations": []},
        "queries": [
            {
                "entity_id": f"case-{index}::tax_unit",
                "period": dict(EXPECTED_PERIOD),
                "outputs": [ROOT_NODE],
            }
            for index in range(POPULATION_PIN["case_count"])
        ],
    }


def _live_kindergeld_oracle_values(
    *,
    euromod_model_root: Path,
    euromod_python: Path,
) -> dict[str, list[float]]:
    """Run both source engines directly; this path cannot re-emit a report."""

    if not euromod_model_root.is_dir():
        raise DEExecutableError("EUROMOD model root does not exist")
    if not euromod_python.is_file():
        raise DEExecutableError("EUROMOD Python interpreter does not exist")
    try:
        from axiom_oracles.adapters.euromod import EuromodPlatformRunner
        from axiom_oracles.adapters.gettsim import GettsimCase, GettsimRunner
        from axiom_oracles.suites.de_worker import (
            DE_GETTSIM_TARGETS,
            de_worker_dual_oracle_cases,
            reduce_gettsim_household_values,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise DEExecutableError(
            "live DE leg production requires the GETTSIM extra and EUROMOD adapter"
        ) from exc

    cases = de_worker_dual_oracle_cases()
    euromod = EuromodPlatformRunner(
        model_root=euromod_model_root,
        country="DE",
        system="DE_2025",
        dataset="DE_2024_b1_2015_03_e2",
        template_dataset="DE_training_data",
        extra_columns=("drgn1",),
        python_executable=str(euromod_python),
    )
    euromod_results = euromod.run_cases(cases, variables=["bch00_s"])
    if len(euromod_results) != len(cases):
        raise DEExecutableError("live EUROMOD execution returned the wrong case count")

    gettsim = GettsimRunner(policy_date_str="2025-06-30")
    try:
        gettsim_version = gettsim.gettsim_version
    except Exception as exc:
        raise DEExecutableError(
            f"cannot identify the live GETTSIM engine: {exc}"
        ) from exc
    _require_equal(gettsim_version, "1.2.1", "live GETTSIM version")
    gettsim_results = []
    for case in cases:
        try:
            gettsim_case = GettsimCase.from_mapping(case.metadata["gettsim_case"])
            raw = gettsim.run_case(gettsim_case, DE_GETTSIM_TARGETS)
            gettsim_results.append(reduce_gettsim_household_values(raw.values))
        except Exception as exc:
            raise DEExecutableError(
                f"live GETTSIM {case.case_id} failed: {exc}"
            ) from exc

    output: dict[str, list[float]] = {"euromod": [], "gettsim": []}
    for case, result in zip(cases, euromod_results, strict=True):
        if result.errors:
            raise DEExecutableError(
                f"live EUROMOD {case.case_id} failed: {'; '.join(result.errors)}"
            )
        value = result.values.get("bch00_s")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise DEExecutableError(
                f"live EUROMOD {case.case_id} returned no finite bch00_s"
            )
        output["euromod"].append(float(value))
    for case, result in zip(cases, gettsim_results, strict=True):
        value = result.get("kindergeld.betrag_m")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise DEExecutableError(
                f"live GETTSIM {case.case_id} returned no finite Kindergeld"
            )
        output["gettsim"].append(float(value))
    return output


def _build_live_leg_documents(
    *,
    unified: dict[str, Any],
    request: dict[str, Any],
    axiom_results: list[dict[str, Any]],
    oracle_values: dict[str, list[float]],
    descriptor: dict[str, Any],
    dependency_inspection: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Restate actual root/oracle executions as two household comparison legs."""

    source_record = unified["record"]
    source_cases = source_record.get("cases")
    queries = request.get("queries")
    if (
        not isinstance(source_cases, list)
        or not isinstance(queries, list)
        or len(source_cases) != POPULATION_PIN["case_count"]
        or len(axiom_results) != len(source_cases)
        or len(queries) != len(source_cases)
    ):
        raise DEExecutableError("live leg producer requires the exact 13-case fixture")
    case_ids = [row["case_id"] for row in source_cases]
    per_child_values = [
        _numeric_engine_output(
            result,
            f"live Axiom result {index}",
            expected_query=query,
        )
        for index, (result, query) in enumerate(
            zip(axiom_results, queries, strict=True)
        )
    ]
    fixture = {
        "expected_results_source": "axiom_execution_case_records",
        "case_ids": case_ids,
        "request": request,
        "request_sha256": _sha256_bytes(_canonical_bytes(request)),
        "expected_results": axiom_results,
        "expected_results_sha256": _sha256_bytes(_canonical_bytes(axiom_results)),
    }
    source_oracles = (source_record.get("tuple") or {}).get("oracles")
    population = (source_record.get("tuple") or {}).get("population")
    if not isinstance(source_oracles, dict) or not isinstance(population, dict):
        raise DEExecutableError("unified record lacks source tuple pins")
    source_view = (source_record.get("views") or {}).get(PROGRAM)
    source_summary = (
        source_view.get("summary") if isinstance(source_view, dict) else None
    )
    if not isinstance(source_summary, dict):
        raise DEExecutableError("unified record lacks source amount summary")

    documents: dict[str, dict[str, Any]] = {}
    try:
        dependency_module = importlib.import_module("scripts.de_axiom_legs")
    except ImportError as exc:
        raise DEExecutableError("cannot load DE output dependency plan") from exc
    dependency_artifacts = {
        row.get("path"): row
        for row in dependency_inspection.get("artifacts", [])
        if isinstance(row, dict)
    }
    for path, expected_sha in (
        (RULESPEC_PIN["module_path"], descriptor["module_sha256"]),
        (
            RULESPEC_PIN["encoding_manifest_path"],
            descriptor["encoding_source_file_sha256"],
        ),
    ):
        if dependency_artifacts.get(path) != {
            "path": path,
            "presence": "on-pinned-ref",
            "sha256": expected_sha,
        }:
            raise DEExecutableError(
                f"live dependency inspection does not bind signed artifact {path}"
            )
    for slot in LEG_PINS:
        oracle = slot["oracle"]
        try:
            view_scaffolds = dependency_module.complete_view_scaffolds(
                oracle, dependency_inspection
            )
        except ValueError as exc:
            raise DEExecutableError(
                f"cannot bind {oracle} output dependency views: {exc}"
            ) from exc
        values = oracle_values.get(oracle)
        if not isinstance(values, list) or len(values) != len(source_cases):
            raise DEExecutableError(
                f"live {oracle} execution returned the wrong case count"
            )
        execution_rows = [
            {"case_id": case_id, "value": value}
            for case_id, value in zip(case_ids, values, strict=True)
        ]
        rows = []
        household_values: list[float] = []
        for source_case, oracle_value, per_child in zip(
            source_cases, values, per_child_values, strict=True
        ):
            metadata = source_case.get("metadata")
            if not isinstance(metadata, dict):
                raise DEExecutableError("unified case metadata is missing")
            child_count = metadata.get("child_count")
            if isinstance(child_count, bool) or not isinstance(child_count, int):
                raise DEExecutableError("unified child count is invalid")
            household_value = per_child * child_count
            if abs(float(oracle_value) - household_value) > 0.01:
                raise DEExecutableError(
                    f"live {oracle} {source_case['case_id']} differs from Axiom"
                )
            household_values.append(household_value)
            rows.append(
                {
                    "case_id": source_case["case_id"],
                    "left_engine": oracle,
                    "right_engine": "axiom",
                    "left_errors": [],
                    "right_errors": [],
                    "metadata": dict(metadata),
                    "matches": [
                        {
                            "concept": KINDERGELD_CONCEPT,
                            "left": oracle_value,
                            "right": household_value,
                        }
                    ],
                    "mismatches": [],
                }
            )
        source_sum_field = (
            "left_weighted_sum" if oracle == "euromod" else "right_weighted_sum"
        )
        source_sum = source_summary.get(source_sum_field)
        if isinstance(source_sum, bool) or not isinstance(source_sum, (int, float)):
            raise DEExecutableError(f"unified record lacks the {oracle} source total")
        if (
            abs(math.fsum(float(value) for value in values) - float(source_sum)) > 0.01
            or abs(math.fsum(household_values) - float(source_sum)) > 0.01
        ):
            raise DEExecutableError(
                f"live {oracle} leg does not conserve the source household total"
            )
        kindergeld_scaffold = view_scaffolds[PROGRAM]
        kindergeld_view = {
            "kind": "subgraph",
            "scope": "amount",
            "claim_mode": "computed",
            "leg_id": slot["id"],
            "state": "complete",
            "root_nodes": [ROOT_NODE],
            "target_root_nodes": kindergeld_scaffold["target_root_nodes"],
            "columns": [KINDERGELD_CONCEPT],
            "oracle_target": kindergeld_scaffold["oracle_target"],
            "dependency_set": kindergeld_scaffold["dependency_set"],
            "summary": {
                "comparison_count": len(rows),
                "match_count": len(rows),
                "mismatch_count": 0,
                "error_count": 0,
            },
            "restatement": {
                "root_node": ROOT_NODE,
                "column": KINDERGELD_CONCEPT,
                "operation": ("multiply_root_amount_by_canonical_child_count"),
                "input_source": "canonical_de_worker_dual_oracle_cases",
                "operation_claim_mode": "attested",
                "result_claim_mode": "computed",
            },
            "executable_replay": dict(fixture),
        }
        complete_views = copy.deepcopy(view_scaffolds)
        complete_views[PROGRAM] = kindergeld_view
        documents[slot["id"]] = {
            "record_schema": REPORT_PIN["record_schema"],
            "schema_version": "axiom.comparison_report.v2",
            "suite": slot["suite"],
            "period": PERIOD,
            "state": "complete",
            "engines": {"left": oracle, "right": "axiom"},
            "tuple": {
                "jurisdiction": "de",
                "population": dict(population),
                "oracle": {"id": oracle, **source_oracles[oracle]},
                "axiom": dict(AXIOM_TUPLE_PIN),
                "rulespec": {
                    "repository": RULESPEC_PIN["repository"],
                    "commit": RULESPEC_PIN["commit"],
                    "tree": RULESPEC_PIN["tree"],
                    "claim_mode": "computed",
                },
            },
            "population": population["id"],
            "dataset_identity": {
                "sha256": population["sha256"],
                "claim_mode": "computed",
            },
            "cases": rows,
            "views": complete_views,
            "provenance": {
                "generated_by": "scripts/de_executable.py::produce",
                "rulespecs": [
                    {
                        "repo": RULESPEC_PIN["repository"],
                        "sha": RULESPEC_PIN["commit"],
                    }
                ],
                "rulespec_ref_inspection": copy.deepcopy(dependency_inspection),
                "oracle_execution": {
                    "engine": oracle,
                    "target": (
                        "bch00_s" if oracle == "euromod" else "kindergeld.betrag_m"
                    ),
                    "mode": "live_no_reemit",
                    "case_results": execution_rows,
                    "case_results_sha256": _sha256_bytes(
                        _canonical_bytes(execution_rows)
                    ),
                    "case_results_sha256_claim_mode": "computed",
                    "claim_mode": "attested",
                    "engine_identity_claim_mode": "attested",
                },
                "rulespec_artifact": {
                    "citation_path": RULESPEC_PIN["citation_path"],
                    "commit": RULESPEC_PIN["commit"],
                    "tree": RULESPEC_PIN["tree"],
                    "artifact_sha256": descriptor["module_sha256"],
                    "apply_manifest_sha256": descriptor["encoding_source_file_sha256"],
                    "claim_mode": "computed",
                },
            },
        }
    return documents


def produce(
    *,
    engine_archive: Path,
    rulespec_root: Path,
    signing_public_key: Path,
    euromod_model_root: Path | None = None,
    euromod_python: Path | None = None,
    oracle_executor: Callable[[], dict[str, list[float]]] | None = None,
    manifest_path: Path = MANIFEST_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Live-run all three engines and write the complete flip evidence bundle."""

    manifest = load_manifest(manifest_path, repo_root=repo_root)
    # Replaceable evidence may be absent, stale, truncated, or left behind by
    # an interrupted earlier run.  Rebuild the immutable source/population view
    # without consulting existing Axiom legs so this command can repair its own
    # bundle instead of failing on the artifacts it is about to replace.
    generator_path = _repo_path(
        repo_root,
        manifest["comparison_record"]["generator"],
        "comparison record generator",
    )
    module_spec = importlib.util.spec_from_file_location(
        "_de_executable_produce_unified", generator_path
    )
    if module_spec is None or module_spec.loader is None:
        raise DEExecutableError("cannot load unified producer for live leg run")
    generator = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(generator)
    try:
        base_record = generator.build(include_axiom_legs=False)
    except (OSError, ValueError) as exc:
        raise DEExecutableError(
            f"cannot derive the source population for live production: {exc}"
        ) from exc
    contract = manifest["comparison_record"]
    _require_equal(
        base_record.get("record_schema"), contract["record_schema"], "record schema"
    )
    _require_equal(base_record.get("suite"), contract["suite"], "record suite")
    _require_equal(base_record.get("period"), PERIOD, "record period")
    population = (base_record.get("tuple") or {}).get("population")
    if not isinstance(population, dict):
        raise DEExecutableError("source population tuple is missing")
    for field, expected in POPULATION_PIN.items():
        _require_equal(population.get(field), expected, f"record population.{field}")
    source_cases = base_record.get("cases")
    if not isinstance(source_cases, list):
        raise DEExecutableError("source population cases are missing")
    case_ids = [row.get("case_id") for row in source_cases if isinstance(row, dict)]
    if len(case_ids) != POPULATION_PIN["case_count"] or len(set(case_ids)) != len(
        case_ids
    ):
        raise DEExecutableError("source population case ids are incomplete")
    unified = {"record": base_record, "case_ids": case_ids}
    archive = engine_archive.expanduser().resolve()
    if not archive.is_file():
        raise DEExecutableError("engine archive does not exist")
    archive_bytes = archive.read_bytes()
    _require_equal(
        _sha256_bytes(archive_bytes),
        ENGINE_PIN["archive_sha256"],
        "engine archive SHA-256",
    )
    public_key = _load_public_key(signing_public_key.expanduser().resolve())
    descriptor_document = _build_signed_descriptor(
        manifest, rulespec_root.expanduser().resolve(), public_key
    )
    descriptor_validation = _validate_signed_descriptor_document(
        descriptor_document, manifest
    )
    request = _amount_request()
    replay_result = _execute_release_archive_raw(
        archive_bytes,
        descriptor_validation,
        request,
    )
    if oracle_executor is not None:
        oracle_values = oracle_executor()
    else:
        if euromod_model_root is None or euromod_python is None:
            raise DEExecutableError(
                "live leg production requires --euromod-model-root and --euromod-python"
            )
        oracle_values = _live_kindergeld_oracle_values(
            euromod_model_root=euromod_model_root.expanduser().resolve(),
            # No resolve(): a venv interpreter is a symlink to the base
            # python, and resolving it escapes the venv's site-packages.
            euromod_python=euromod_python.expanduser(),
        )
    try:
        dependency_module = importlib.import_module("scripts.de_axiom_legs")
        dependency_inspection = dependency_module.inspect_pinned_ref(
            "euromod", rulespec_root=rulespec_root.expanduser().resolve()
        )
    except (ImportError, OSError, ValueError) as exc:
        raise DEExecutableError(
            f"cannot inspect pinned DE output dependencies: {exc}"
        ) from exc
    leg_documents = _build_live_leg_documents(
        unified=unified,
        request=request,
        axiom_results=replay_result["observed_results"],
        oracle_values=oracle_values,
        descriptor=descriptor_validation,
        dependency_inspection=dependency_inspection,
    )

    descriptor_path = _repo_path(
        repo_root, RULESPEC_PIN["descriptor_path"], "signed descriptor output"
    )
    descriptor_sha = _sha256_bytes(_render(descriptor_document).encode("utf-8"))
    _write_text_atomic(descriptor_path, _render(descriptor_document))
    for slot in LEG_PINS:
        leg_path = _repo_path(repo_root, slot["path"], f"{slot['id']} output")
        _write_text_atomic(leg_path, _render(leg_documents[slot["id"]]))

    unified_document = generator.build()
    unified_path = _repo_path(
        repo_root,
        manifest["comparison_record"]["path"],
        "unified comparison output",
    )
    _write_text_atomic(unified_path, _render(unified_document))
    unified = _validate_unified_record(manifest, repo_root)
    legs = [
        _validate_leg_record(
            _repo_path(repo_root, slot["path"], f"{slot['id']} path"),
            slot,
            manifest,
            unified,
        )
        for slot in LEG_PINS
    ]
    fixture = _common_leg_fixture(legs)
    _require_equal(
        fixture["rulespec_artifact"],
        {
            "citation_path": RULESPEC_PIN["citation_path"],
            "commit": RULESPEC_PIN["commit"],
            "tree": RULESPEC_PIN["tree"],
            "artifact_sha256": descriptor_validation["module_sha256"],
            "apply_manifest_sha256": descriptor_validation[
                "encoding_source_file_sha256"
            ],
        },
        "Axiom-leg signed RuleSpec binding",
    )
    _require_equal(
        replay_result["observed_results"],
        fixture["expected_results"],
        "live Axiom results and emitted leg rows",
    )
    receipt_document = {
        "schema": REPLAY_SCHEMA,
        "program": PROGRAM,
        "period": PERIOD,
        "claim_mode": "computed",
        "engine": {
            **ENGINE_PIN,
            "binary_sha256": replay_result["binary_sha256"],
            "version_stdout": replay_result["version_stdout"],
        },
        "release_archive": {
            "asset": ENGINE_PIN["asset"],
            "encoding": "base64",
            "sha256": ENGINE_PIN["archive_sha256"],
            "bytes_base64": base64.b64encode(archive_bytes).decode("ascii"),
        },
        "comparison_record": _comparison_semantic_binding(unified),
        "signed_rulespec_artifact": {
            "path": RULESPEC_PIN["descriptor_path"],
            "sha256": descriptor_sha,
            "commit": RULESPEC_PIN["commit"],
            "tree": RULESPEC_PIN["tree"],
            "module_sha256": descriptor_validation["module_sha256"],
            "encoding_manifest_payload_sha256": descriptor_validation[
                "encoding_payload_sha256"
            ],
            "encoding_manifest_source_file_sha256": descriptor_validation[
                "encoding_source_file_sha256"
            ],
            "trusted_key_id": descriptor_validation["trusted_key_id"],
        },
        "axiom_legs": [
            {"id": row["id"], "path": row["path"], "sha256": row["sha256"]}
            for row in legs
        ],
        "execution": {
            "commands": [
                {"argv": argv, "exit_code": 0}
                for argv in manifest["replay"]["required_commands"]
            ],
            "request_source": manifest["replay"]["request_source"],
            "expected_results_source": manifest["replay"]["expected_results_source"],
            "verification_mode": manifest["replay"]["verification_mode"],
            "request_sha256": fixture["request_sha256"],
            "expected_results_sha256": fixture["expected_results_sha256"],
            "observed_results": replay_result["observed_results"],
            "observed_results_sha256": replay_result["observed_results_sha256"],
            "result_count": len(replay_result["observed_results"]),
            "compiled_artifact_sha256": replay_result["compiled_artifact_sha256"],
            "stdout_sha256": replay_result["stdout_sha256"],
        },
    }
    receipt_path = _repo_path(repo_root, RECEIPT_PATH, "replay receipt output")
    _write_text_atomic(receipt_path, _render(receipt_document))
    status = build_status(manifest_path=manifest_path, repo_root=repo_root)
    status_path = _repo_path(repo_root, STATUS_PATH, "executable status output")
    _write_text_atomic(status_path, _render(status))
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--print-status", action="store_true")
    modes.add_argument("--run", action="store_true")
    parser.add_argument("--engine-archive", type=Path)
    parser.add_argument("--rulespec-root", type=Path)
    parser.add_argument("--signing-public-key", type=Path)
    parser.add_argument("--euromod-model-root", type=Path)
    parser.add_argument("--euromod-python", type=Path)
    args = parser.parse_args()

    try:
        if args.run:
            missing_args = [
                name
                for name, value in (
                    ("--engine-archive", args.engine_archive),
                    ("--rulespec-root", args.rulespec_root),
                    ("--signing-public-key", args.signing_public_key),
                    ("--euromod-model-root", args.euromod_model_root),
                    ("--euromod-python", args.euromod_python),
                )
                if value is None
            ]
            if missing_args:
                raise DEExecutableError("--run requires " + ", ".join(missing_args))
            status = produce(
                engine_archive=args.engine_archive,
                rulespec_root=args.rulespec_root,
                signing_public_key=args.signing_public_key,
                euromod_model_root=args.euromod_model_root,
                euromod_python=args.euromod_python,
            )
            print(_render(status), end="")
            return 0

        status = build_status()
        rendered = _render(status)
        if args.print_status:
            print(rendered, end="")
            return 0
        status_path = _repo_path(REPO_ROOT, STATUS_PATH, "executable status")
        if args.check:
            if (
                not status_path.is_file()
                or status_path.read_text(encoding="utf-8") != rendered
            ):
                print(
                    "DE Kindergeld executable status drifted; regenerate with "
                    "`python scripts/de_executable.py`",
                    file=sys.stderr,
                )
                return 1
            print("DE Kindergeld executable status up to date")
            return 0
        status_path.write_text(rendered, encoding="utf-8")
        print(f"wrote {status_path.relative_to(REPO_ROOT)}")
        return 0
    except (DEExecutableError, OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        print(f"DE executable ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
