#!/usr/bin/env python3
"""Exercise census: what did each comparison suite actually vary?

A suite's headline (cases x match rate) says nothing about the input surface it
exercised. A suite that pins every input but two and a suite that varies ninety
shelter values are indistinguishable on the scoreboard — which is how a
"100% parity" number can silently carry near-zero evidence about most of a
program, and how mis-readings of suite breadth go uncorrected in both
directions.

This script makes exercise a committed, checkable artifact. For every suite
with committed per-case evidence (inline ``cases`` or
``dashboard/public/data/cases/<suite>/chunk-*.json``), it counts distinct
values per evidence field and per verdict concept across all cases, and writes
``conformance/exercise-census.json``.

Reading a row, three states matter per field:

* **varied** — multiple distinct values across cases; the comparison carries
  evidence about this dimension.
* **constant** — one distinct value across every case. The census cannot say
  *why* (population zeros, harness pin, or a projection mode); it says loudly
  that no evidence about this dimension exists in the suite.
* **bridged-through** — the harness feeds one engine's computed value into the
  other's input (e.g. snap_populace feeds PolicyEngine's dependent-care
  deduction in as the expense with ``reimbursed = 0``), so downstream effect is
  tested but the receiving side's own derivation is satisfied by construction.
  This state is declared by the bridge manifest, not inferable from values:
  ``axiom_oracles/bridges/manifests/<suite>.yaml`` is the source, this script
  only reports it. A suite with no manifest is unaudited, never "nothing
  bridged".

v1 scope, stated plainly: most suites commit *stage evidence* (gross income,
net income, shelter deduction, ...), not raw input records, so this measures
variation in the evidence the suite chose to keep. A suite with no committed
per-case evidence appears with ``cases_scanned: 0`` — that absence is a
finding, not a skip.  Census generation makes one lightweight pass over every
suite's chunks and checks only index identity plus cardinality.  It never
claims full verdict reconciliation; certification performs the strict row and
verdict validation for the suites in its program registry.

Modes::

    uv run python scripts/exercise_census.py           # write the census
    uv run python scripts/exercise_census.py --check   # CI: fail on drift
    uv run python scripts/exercise_census.py --markdown # human summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
CASES_DIR = DATA_DIR / "cases"
OUTPUT_PATH = REPO_ROOT / "conformance" / "exercise-census.json"

# Direct script execution puts ``scripts/`` rather than the repository root at
# the front of sys.path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.evidence import (  # noqa: E402
    EvidenceChunk,
    is_safe_suite_name,
    strict_json_loads,
    validate_chunk_binding,
)

SCHEMA = "axiom_oracles.exercise_census.v1"

MANIFEST_DIR = REPO_ROOT / "axiom_oracles" / "bridges" / "manifests"


def _manifest_strict_clean() -> dict[str, bool]:
    """Which manifests are strict-clean, per the validator itself.

    `bridge_audited` previously meant only "a manifest exists", so an unpinned
    manifest with partial catchalls and unverified completeness still reported
    audited (audit finding 5). The label must mean what it says, and the
    validator — not this script — decides.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_vbm", Path(__file__).resolve().parent / "validate_bridge_manifests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifests = module.load_manifests()
    collisions = module.global_collisions(manifests)
    clean: dict[str, bool] = {}
    for path, manifest in manifests.items():
        errors, findings = module.validate(path, manifest)
        # Global collisions are a property of the SET, so a per-manifest
        # validate() cannot see them; without this a colliding manifest could
        # still report audited (round-2 audit finding 5).
        # A lane counts as audited only when it has OPTED IN to strict
        # enforcement (`strict: true`) AND is clean. Without the flag
        # requirement a strict-clean lane could drop the opt-in — silencing
        # future --strict CI enforcement — while its census row kept
        # bridge_audited=true and its certificate kept exercised=true
        # (delta-audit finding). The opt-in is part of the certified claim.
        declared_strict = isinstance(manifest, dict) and manifest.get("strict") is True
        ok = declared_strict and not errors and not findings and not collisions
        if isinstance(manifest, dict):
            names = [manifest.get("suite")]
            aliases = manifest.get("aliases")
            if isinstance(aliases, list):
                names.extend(aliases)
            for name in names:
                if name:
                    clean[str(name)] = ok
    return clean


def _bridged_through_by_suite() -> dict[str, dict[str, str]]:
    """Bridged-through dimensions come from the declared bridge manifests.

    The manifest is the experiment design; the census only reports it. A suite
    with no manifest is unaudited — never "nothing bridged". Historical suite
    aliases map to the same manifest so committed reports keep their names.
    """
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - environment guard
        sys.exit(
            "exercise_census needs PyYAML to read bridge manifests. Run under "
            "the project env (`uv run python scripts/exercise_census.py`) or "
            "install the package first — bridged-through state must come from "
            "the manifests, never be silently skipped."
        )

    by_suite: dict[str, dict[str, str]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        manifest = yaml.safe_load(path.read_text())
        if not isinstance(manifest, dict):
            continue
        bridged = {
            str(b.get("dimension") or (b.get("inputs") or ["?"])[0]): str(
                b.get("mechanism") or b.get("source") or ""
            )
            for b in manifest.get("bindings") or []
            if b.get("kind") == "bridged"
        }
        for name in [manifest.get("suite"), *(manifest.get("aliases") or [])]:
            if name:
                by_suite[str(name)] = bridged
    return by_suite


BRIDGED_THROUGH: dict[str, dict[str, str]] = _bridged_through_by_suite()
MANIFEST_STRICT_CLEAN: dict[str, bool] = _manifest_strict_clean()


def _iter_suite_reports() -> list[tuple[str, dict, Path]]:
    reports = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            payload = strict_json_loads(path.read_text())
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("suite"), str)
            and payload["suite"]
        ):
            reports.append((payload["suite"], payload, path))
    return reports


def _canonical_value(raw) -> str:
    """Canonicalize an observed value for distinctness counting.

    JSON-string identity is wrong for numbers: 1 vs 1.0 and 0.0 vs -0.0 are
    the same observation, while large integers must not collapse through
    float parsing (2026-07-26 audit, finding 17). Decimal, normalized, with
    signed zero collapsed.
    """
    if isinstance(raw, bool) or raw is None:
        return json.dumps(raw)
    if isinstance(raw, (int, float)):
        raw = str(raw)
    if isinstance(raw, str):
        try:
            number = Decimal(raw)
        except (InvalidOperation, ValueError):
            return json.dumps(raw, sort_keys=True)
        # A non-finite is not an observation of a value; keep it distinct from
        # any numeric and from the look-alike string (audit finding 6).
        if not number.is_finite():
            return json.dumps(f"__nonfinite__{raw}", sort_keys=True)
        if number == 0:
            return "0"
        # normalize() honours the ambient context, whose 28-digit default
        # merged distinct exact integers such as ...678901 and ...678902
        # (audit finding 6). Give it room to be exact.
        with localcontext() as ctx:
            ctx.prec = 200
            return format(number.normalize(), "f")
    return json.dumps(raw, sort_keys=True, default=str)


def _chunk_cases(
    suite: str,
) -> tuple[list[dict], list[dict], tuple[EvidenceChunk, ...]]:
    """Return cases plus identities from the census's existing chunk pass.

    ``EvidenceChunk`` descriptors retain the raw JSON row cardinality, while
    ``cases`` contains only mappings the variation census can inspect.  This
    lets the shared binding validator compare the index without opening every
    chunk a second time.
    """
    cases: list[dict] = []
    manifest: list[dict] = []
    descriptors: list[EvidenceChunk] = []
    if not is_safe_suite_name(suite):
        return cases, manifest, ()
    suite_dir = CASES_DIR / suite
    if not suite_dir.is_dir():
        return cases, manifest, ()
    for chunk in sorted(suite_dir.glob("chunk-*.json")):
        try:
            raw = chunk.read_bytes()
            payload = strict_json_loads(raw)
        except OSError:
            continue
        except (UnicodeDecodeError, ValueError):
            rows = []
        else:
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict) and isinstance(payload.get("cases"), list):
                rows = payload["cases"]
            else:
                rows = []
        digest = hashlib.sha256(raw).hexdigest()
        descriptor = EvidenceChunk(chunk.name, digest, len(rows))
        descriptors.append(descriptor)
        manifest.append(
            {
                "chunk": str(chunk.relative_to(REPO_ROOT)),
                "sha256": digest,
                "cases": len(rows),
            }
        )
        cases.extend(row for row in rows if isinstance(row, dict))
    return cases, manifest, tuple(descriptors)


def _cardinality_reconciliation(report: dict, chunks: tuple[EvidenceChunk, ...]) -> str:
    """State the strongest reconciliation the census itself establishes.

    The census does not interpret per-case verdicts.  It may therefore claim
    only ``cardinality``, and only when all three summary counts are
    non-negative integers, conserve, and comparison_count equals the raw
    number of rows across chunks.
    """

    chunk_case_count = sum(chunk.cases for chunk in chunks)
    if not chunks or chunk_case_count == 0:
        return "none"
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return "none"
    counts = [
        summary.get("comparison_count"),
        summary.get("match_count"),
        summary.get("mismatch_count"),
    ]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts
    ):
        return "none"
    comparison_count, match_count, mismatch_count = counts
    if match_count + mismatch_count != comparison_count:
        return "none"
    return "cardinality" if comparison_count == chunk_case_count else "none"


def _census_suite(suite: str, report: dict, report_path: Path) -> dict:
    # Unified records can carry a verifier-produced experiment receipt over
    # the engine's complete active input catalog. This is stronger than
    # inferring inputs from case metadata and avoids inventing a bridge
    # manifest for a harness whose measured input states are already present.
    experiment = report.get("experiment")
    if report.get("record_schema") == "axiom.unified_comparison_record.v1":
        fields, bridged = _unified_experiment_fields(suite, experiment)
        cases = [case for case in report.get("cases") or [] if isinstance(case, dict)]
        varied = sum(field["state"] == "varied" for field in fields.values())
        return {
            "cases_scanned": len(cases),
            "report": str(report_path.relative_to(REPO_ROOT)),
            "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "evidence_source": "unified-experiment-receipt",
            "inline_cases_not_counted": 0,
            "chunk_manifest": [],
            "evidence_fields": fields,
            "verdict_concepts": {},
            "varied_fields": varied,
            "constant_fields": len(fields) - varied,
            "bridged_through": bridged,
        }
    field_values: dict[str, set[str]] = defaultdict(set)
    concept_values: dict[str, set[str]] = defaultdict(set)
    scanned = 0

    def eat_case(case: dict) -> None:
        nonlocal scanned
        scanned += 1
        # Compact chunk rows: i = [{n, v}], v = [{c, l, x}].
        for record in case.get("i") or []:
            if isinstance(record, dict) and record.get("n") is not None:
                field_values[str(record["n"])].add(
                    _canonical_value(record.get("v"))
                )
        for verdict in case.get("v") or []:
            if isinstance(verdict, dict) and verdict.get("c"):
                concept_values[str(verdict["c"])].add(
                    _canonical_value(verdict.get("l"))
                )
        # Reference-oracle chunks may carry the exact runner inputs used for
        # executable reproduction outside the dashboard-oriented ``i`` rows.
        # Count those inputs as case evidence too: they are report-bound chunk
        # bytes, and omitting them makes a genuinely exercised suite appear
        # evidence-free after inline mirrors are stripped.
        execution = case.get("execution")
        if (
            isinstance(execution, dict)
            and execution.get("schema_version")
            == "axiom_oracles.case_execution.v1"
        ):
            axiom_inputs = execution.get("axiom_inputs")
            if isinstance(axiom_inputs, dict):
                for key, value in axiom_inputs.items():
                    field_values[str(key)].add(_canonical_value(value))
        # Inline report cases: scalar metadata entries are stage evidence.
        metadata = case.get("metadata")
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if isinstance(value, (int, float, str, bool)) or value is None:
                    field_values[str(key)].add(_canonical_value(value))

    # Chunks are the full per-case record when they exist; the inline report
    # usually keeps a single illustrative case. Mixing the two would count
    # every field of that one inline case as "constant" and drown the signal —
    # but the inline cases must not vanish silently either (finding 7): their
    # count is recorded so eclipse is visible.
    # Chunks are keyed by suite name, so when two reports claim one suite the
    # chunks belong to only one of them. Counting them under the other is the
    # substitution the census must not perform silently (round-2 finding 4);
    # the contested flag set in build_census() makes the certificate refuse.
    chunk_cases, chunk_manifest, chunks = _chunk_cases(suite)
    inline_cases = [c for c in report.get("cases") or [] if isinstance(c, dict)]
    if chunks:
        for case in chunk_cases:
            eat_case(case)
    else:
        for case in inline_cases:
            eat_case(case)

    binding, binding_defects = validate_chunk_binding(report_path, chunks, suite=suite)
    reconciliation = _cardinality_reconciliation(report, chunks)

    fields = {
        name: {
            "distinct": len(values),
            "state": "varied" if len(values) > 1 else "constant",
        }
        for name, values in sorted(field_values.items())
    }
    concepts = {
        name: {"distinct_left_values": len(values)}
        for name, values in sorted(concept_values.items())
    }
    varied = sum(1 for f in fields.values() if f["state"] == "varied")
    return {
        "cases_scanned": scanned,
        # The row is bound to the exact report it counted. Without this, two
        # reports claiming one suite are indistinguishable and a row can
        # inherit the other's evidence (audit finding 4).
        "report": str(report_path.relative_to(REPO_ROOT)),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "binding": binding,
        "binding_defects": list(binding_defects),
        # Census-wide validation is intentionally capped at cardinality.
        # Certification reparses program-registry suites and may establish
        # full per-verdict reconciliation.
        "reconciliation": reconciliation,
        "evidence_source": "chunks" if chunks else "inline",
        "inline_cases_not_counted": len(inline_cases) if chunks else 0,
        "chunk_manifest": chunk_manifest,
        "evidence_fields": fields,
        "verdict_concepts": concepts,
        "varied_fields": varied,
        "constant_fields": len(fields) - varied,
        "bridged_through": BRIDGED_THROUGH.get(suite, {}),
        "bridge_declared": suite in BRIDGED_THROUGH,
        # Audited means the validator finds nothing outstanding — not merely
        # that a manifest file exists (audit finding 5).
        "bridge_audited": MANIFEST_STRICT_CLEAN.get(suite, False),
    }


def _unified_experiment_fields(
    suite: str, experiment: object
) -> tuple[dict[str, dict], dict[str, str]]:
    """Validate and normalize a unified record's measured input receipt."""

    if not isinstance(experiment, dict):
        raise ValueError(f"{suite}: unified record lacks an experiment receipt")
    if experiment.get("schema") != "axiom.experiment_boundary_receipt.v1":
        raise ValueError(f"{suite}: unsupported experiment receipt schema")
    active = experiment.get("active_inputs")
    if not isinstance(active, dict) or not active:
        raise ValueError(f"{suite}: experiment receipt has no active inputs")
    fields: dict[str, dict] = {}
    for name, row in sorted(active.items()):
        if not isinstance(row, dict):
            raise ValueError(f"{suite}: active input {name!r} is not a mapping")
        state = row.get("state")
        distinct = row.get("distinct")
        values = row.get("observed_values")
        if state not in {"varied", "constant"}:
            raise ValueError(f"{suite}: active input {name!r} has invalid state {state!r}")
        if not isinstance(values, list) or not values:
            raise ValueError(f"{suite}: active input {name!r} has no observations")
        observed_distinct = len(set(map(str, values)))
        expected_state = "varied" if observed_distinct > 1 else "constant"
        if distinct != observed_distinct or state != expected_state:
            raise ValueError(
                f"{suite}: active input {name!r} state/count contradicts its observations"
            )
        fields[str(name)] = {"distinct": distinct, "state": state}
    bridged = experiment.get("bridged_through")
    if not isinstance(bridged, dict):
        raise ValueError(f"{suite}: bridged_through must be a mapping")
    return fields, {str(name): str(value) for name, value in bridged.items()}


def build_census() -> dict:
    suites: dict[str, dict] = {}
    contested: dict[str, list[str]] = defaultdict(list)
    for suite, report, path in _iter_suite_reports():
        # Unified records carry their own complete, verifier-produced
        # experiment receipt and can expose several program views over one
        # run.  Their exercise evidence is consumed directly by certify.py.
        # Keeping it certificate-scoped prevents an unrelated unified record
        # from changing the global-census hash in every existing program
        # certificate (and therefore preserves those certificates' evidence
        # identity when none of their suites changed).
        if report.get("record_schema") == "axiom.unified_comparison_record.v1":
            continue
        contested[suite].append(str(path.relative_to(REPO_ROOT)))
        suites[suite] = _census_suite(suite, report, path)
    # A suite claimed by more than one report is an ambiguity the census must
    # NOT resolve silently by sort order — it is recorded on the row so the
    # certificate can treat it as a defect (audit finding 4; live case:
    # nyc-synthetic, 813 cases vs 10, sharing one chunk directory).
    for suite, paths in contested.items():
        if len(paths) > 1:
            suites[suite]["contested_reports"] = sorted(paths)
    return {
        "schema": SCHEMA,
        "_comment": (
            "Generated by scripts/exercise_census.py — do not hand-edit. "
            "Per suite: distinct-value counts across committed per-case "
            "evidence. 'constant' means no evidence of variation exists in "
            "the suite, not that the dimension is untested elsewhere; "
            "'bridged_through' lists dimensions satisfied by construction "
            "(declared per audited bridge). cases_scanned: 0 means the suite "
            "commits no per-case rows; nonzero cases with zero evidence "
            "fields means the committed rows carry verdicts only. Either "
            "way, the absence is the finding. Binding checks the versioned "
            "chunk index against the exact report and chunk identities; "
            "unbound evidence is recorded but does not stop census "
            "generation. Reconciliation here is cardinality-only; strict "
            "full verdict reconciliation is limited to certification's "
            "program-registry suites."
        ),
        "suites": suites,
    }


def render_markdown(census: dict) -> str:
    lines = [
        "| suite | cases | varied | constant | bridge audited |",
        "|---|---:|---:|---:|---|",
    ]
    for suite, row in sorted(census["suites"].items()):
        lines.append(
            f"| {suite} | {row['cases_scanned']} | {row['varied_fields']} "
            f"| {row['constant_fields']} | "
            f"{'yes' if row['bridge_audited'] else 'no'} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    census = build_census()
    rendered = json.dumps(census, indent=2, sort_keys=True) + "\n"

    if args.markdown:
        print(render_markdown(census))
        return 0
    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"missing {OUTPUT_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        if OUTPUT_PATH.read_text() != rendered:
            print(
                "exercise census drifted — regenerate with "
                "`uv run python scripts/exercise_census.py`",
                file=sys.stderr,
            )
            return 1
        print("exercise census up to date")
        return 0

    OUTPUT_PATH.write_text(rendered)
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(render_markdown(census))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
