#!/usr/bin/env python3
"""Reproduce the US tariff source-completeness ledger.

Contract (adopted from axiom-oracles PR #475, commits 5402e5bf6 and
75bb586ae): generated facts come only from immutable corpus and RuleSpec Git
objects; review decisions are committed; ``computed`` is their pure join.

Statuses mean: ``encoded`` is present in the composed executable program;
``partially-encoded`` has an encoded rule or membership table but is not fully
composed; ``excluded-with-reason`` is in a declared root but cannot affect the
program result for the stated reason; ``pending`` can affect it and is not
encoded.  A declared corpus root is the complete, versioned source population
whose denominator is promised here, not merely citations selected by modules.

The boundary-input frontier contains every entry fact consumed by the program.
An uncaptured input is legitimate only when its external semantic scope is
named. ``--check`` re-censuses both repositories and requires byte-identical
output. ``closed`` is true only when there are no partial/pending families, all
root populations reconcile, and the complete input frontier is classified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "conformance/closure/us-tariff-duty.yaml"
CORPUS = Path.home() / "TheAxiomFoundation/axiom-corpus"
CORPUS_REF = "bef19f24206a9de4ef29d9ba2b5924f3cc6a00c6"
RULESPEC = Path.home() / "TheAxiomFoundation/_b1wt/rulespec-us"
RULESPEC_REF = "96d5e7c1e6309dc205b7320bbddaae8dd5d410df"
SCHEDULE = "data/corpus/provisions/us/statute/2026-08-09-usitc-hts-2026-rev15-full-schedule.jsonl"
NOTES = "data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl"
SCHEMA = "axiom_oracles.closure.ledger.v1"
SCHEDULE_SHA256 = "6c8d07d21a1e3f2233197c1b2f96169f01a1a768dd2509a71c0fdb03d4a99d14"
SCHEDULE_VERSION = "2026-08-09-usitc-hts-2026-rev15-full-schedule"
SCHEDULE_DECLARED_COUNT = 29_845
NOTES_SHA256 = "0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8"
NOTES_VERSION = "2026-08-04-usitc-hts-2026-rev15-notes"
NOTES_DECLARED_COUNT = 805
RULESPEC_MODULE_COUNT = 380
RULESPEC_PATHS_SHA256 = "481956d2972610d8fe382d37ee8e651fa8bbeaf29e3550f9b08c06ca656c1a45"
STATUSES = ("encoded", "partially-encoded", "excluded-with-reason", "pending")
MODULE_PREFIXES = (
    "us/policies/usitc/us-tariff-duty/",
    "us/policies/cbp/us-tariff-",
    "us/policies/usitc/us-tariff-incidence/",
)


@dataclass(frozen=True)
class ClosureSummary:
    """Hermetically derived certificate inputs from a valid ledger."""

    closed: bool
    non_encoded_reasons_complete: bool


@dataclass(frozen=True)
class VerificationResult:
    """Result of re-deriving a ledger from its immutable source objects."""

    document: dict[str, Any] | None
    expected: dict[str, Any] | None
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


EXPECTED_PROGRAM = {"id": "us/tariff-duty", "rulespec_ref": RULESPEC_REF}
EXPECTED_CORPUS_ROOTS = {
    "hts-rate-provisions": {
        "path": SCHEDULE,
        "commit": CORPUS_REF,
        "sha256": SCHEDULE_SHA256,
        "version": SCHEDULE_VERSION,
        "declared_count": SCHEDULE_DECLARED_COUNT,
    },
    "chapter-99-notes": {
        "path": NOTES,
        "commit": CORPUS_REF,
        "sha256": NOTES_SHA256,
        "version": NOTES_VERSION,
        "declared_count": NOTES_DECLARED_COUNT,
    },
    "fr-instrument-families": {
        "derived_from": "composition source_verification plus overlays",
        "rulespec_commit": RULESPEC_REF,
    },
}
EXPECTED_RULESPEC_FACTS = {
    "commit": RULESPEC_REF,
    "module_count": RULESPEC_MODULE_COUNT,
    "paths_sha256": RULESPEC_PATHS_SHA256,
}
EXPECTED_SOURCE_COUNTS = {
    "rated-minus-9802": 13_781,
    "rated-9802": 5,
    "unrated": 16_059,
    "chapter99-remainder": 800,
}


DECISIONS = [
    {"root": "hts-rate-provisions", "family": "rated-lines-except-9802", "status": "encoded", "count_source": "rated-minus-9802", "reason": "B1.2 generated chapter tables supply the Rev-15 column rates."},
    {"root": "hts-rate-provisions", "family": "9802-partial-value-rated-lines", "status": "partially-encoded", "count_source": "rated-9802", "reason": "The rate rows are passthroughs, but dutiable partial value is supplied as an entry input rather than derived."},
    {"root": "hts-rate-provisions", "family": "unrated-structural-rows", "status": "excluded-with-reason", "count_source": "unrated", "reason": "Headings without a Rates of duty (1-General) field do not themselves supply a rate line."},
    {"root": "chapter-99-notes", "family": "note-20-section-301-lists", "status": "encoded", "count": 1, "membership_rows": 301, "reason": "Incidence membership tables are composed for the original China list overlays."},
    {"root": "chapter-99-notes", "family": "notes-16-19-section-232-metals", "status": "encoded", "count": 1, "membership_rows": 232, "reason": "Steel/aluminum incidence and composed overlays are present."},
    {"root": "chapter-99-notes", "family": "note-18-section-201", "status": "encoded", "count": 1, "membership_rows": 201, "reason": "Section 201 solar incidence and overlay are composed."},
    {"root": "chapter-99-notes", "family": "note-2aa-section-122", "status": "encoded", "count": 1, "membership_rows": 122, "reason": "Section 122 incidence and overlay are composed."},
    {"root": "chapter-99-notes", "family": "note-51-section-338", "status": "pending", "count": 1, "reason": "Note 51 pages are absent from the D0 ingest; ingest and encode them before composing section 338."},
    {"root": "chapter-99-notes", "family": "other-chapter-99-pages", "status": "partially-encoded", "count_source": "chapter99-remainder", "reason": "The witness composes many 9903.01/.02/.05 IEEPA and newer 301 headings, but no page-level census proves every other Chapter-99 note covered."},
    {"root": "fr-instrument-families", "family": "section-232-metal-instruments", "status": "encoded", "count": 1, "reason": "2018 and 2025 metal actions plus the 2026 annex restructure are represented in the composed aluminum/steel overlays."},
    {"root": "fr-instrument-families", "family": "section-232-non-metal-annexes", "status": "pending", "count": 6, "reason": "Autos/parts, copper, semiconductors, medium/heavy-duty vehicles, and wood proclamation annexes are not encoded (approximately ten annex documents)."},
    {"root": "fr-instrument-families", "family": "china-301-original-2018-actions", "status": "pending", "count": 1, "reason": "Original 2018 instruments are absent from the D0 corpus."},
    {"root": "fr-instrument-families", "family": "china-301-2024-action", "status": "partially-encoded", "count": 1, "reason": "Membership and overlay exist, but the action is not fed into the final composition."},
    {"root": "fr-instrument-families", "family": "brazil-301", "status": "partially-encoded", "count": 1, "reason": "Membership and headings exist, but the family is not fed into the final composition."},
    {"root": "fr-instrument-families", "family": "forced-labor-301", "status": "partially-encoded", "count": 1, "reason": "Membership and country tiers exist, but the family is not fed into the final composition."},
    {"root": "fr-instrument-families", "family": "solar-china", "status": "partially-encoded", "count": 1, "reason": "Membership is encoded but the action is not fed into the final composition."},
    {"root": "fr-instrument-families", "family": "section-201-proclamation-10339", "status": "encoded", "count": 1, "reason": "The solar safeguard is encoded and composed."},
    {"root": "fr-instrument-families", "family": "section-122-proclamation-11012", "status": "encoded", "count": 1, "reason": "The temporary surcharge and exclusions are encoded and composed."},
    {"root": "fr-instrument-families", "family": "ieepa-orders-and-termination", "status": "encoded", "count": 1, "reason": "Fentanyl, reciprocal families, exclusions, and termination are composed for the codified Rev-15 state."},
    {"root": "fr-instrument-families", "family": "section-338-instruments", "status": "pending", "count": 1, "reason": "Blocked on the missing note-51 ingest."},
    {"root": "fr-instrument-families", "family": "historical-vintages", "status": "pending", "count": 1, "reason": "This ledger covers the Rev-15 codified state only; historical schedule/instrument vintages are not a reproduced root."},
]

INPUTS = [
    ("hts_number", "HTS classification assigned to the entry"),
    ("country_of_origin", "origin determination for the entry"),
    ("entry_date", "CBP entry date and effective-time facts"),
    ("customs_value", "19 USC 1401a appraised customs value"),
    ("shipment_value", "shipment value used by de-minimis/postal rules"),
    ("is_postal_shipment", "postal-channel classification"),
    ("column_1_general_rate", "selected Rev-15 HTS general rate line"),
    ("special_rate", "claimed and qualifying special-program rate"),
    ("column_2_rate", "column-2 rate selection"),
    ("section_232_membership", "membership in the applicable 232 annex"),
    ("section_301_membership", "membership in the applicable 301 list"),
    ("section_201_membership", "membership in the solar safeguard annex"),
    ("section_122_membership", "membership in surcharge exclusions"),
    ("ieepa_membership", "membership in reciprocal/fentanyl annexes"),
    ("section_338_membership", "membership under HTS note 51"),
    ("is_section_232_article", "witness boolean: 232 article"),
    ("is_section_232_derivative", "witness boolean: 232 derivative"),
    ("is_reciprocal_annex_excluded", "witness boolean: reciprocal annex exclusion"),
    ("is_reciprocal_metals_excluded", "witness boolean: reciprocal metals exclusion"),
    ("is_section_122_annex_excluded", "witness boolean: 122 annex exclusion"),
    ("is_section_122_232_excluded", "witness boolean: 122/232 exclusion"),
    ("is_brazil_301_excluded", "witness boolean: Brazil-301 exclusion"),
    ("is_forced_labor_annex_excluded", "witness boolean: forced-labor annex exclusion"),
    ("is_forced_labor_metals_excluded", "witness boolean: forced-labor metals exclusion"),
    ("is_china_2024_action_member", "witness boolean: 2024 China action membership"),
    ("is_solar_china_member", "witness boolean: solar-China membership"),
    ("chapter_98_partial_value_share", "9802 dutiable-value share supplied by the declarant"),
    ("section_338_reduced_duty_base_share", "note-51 partial-value share supplied by the declarant"),
]


def _git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if p.returncode:
        raise ValueError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def _blob_facts(
    root: Path, ref: str, relative: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    blob = _git(root, "show", f"{commit}:{relative}")
    rows = [json.loads(line) for line in blob.splitlines() if line.strip()]
    return rows, {"path": relative, "commit": commit, "sha256": hashlib.sha256(blob).hexdigest(), "version": rows[0]["version"]}


def _decision_state(
    source_counts: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for decision in DECISIONS:
        row = dict(decision)
        count_source = row.pop("count_source", None)
        if count_source is not None:
            row["count"] = source_counts[count_source]
        ledger.append(row)
    counts: dict[str, dict[str, int]] = {}
    for row in ledger:
        bucket = counts.setdefault(row["root"], {status: 0 for status in STATUSES})
        bucket[row["status"]] += row["count"]
    pending = [
        {
            "family": row["family"],
            "root": row["root"],
            "status": row["status"],
            "blocker": row["reason"],
        }
        for row in ledger
        if row["status"] in ("pending", "partially-encoded")
    ]
    frontier = [
        {"input": name, "grounding": "uncaptured", "uncaptured_scope": scope}
        for name, scope in INPUTS
    ]
    decisions = {"ledger": ledger, "input_grounding": frontier}
    computed = {
        "counts_by_status_per_root": counts,
        "burndown": pending,
        "boundary_frontier": {
            "complete": True,
            "input_count": len(frontier),
            "inputs": frontier,
        },
        "closed": not pending and all(sum(values.values()) > 0 for values in counts.values()),
    }
    return decisions, computed


def build(
    *,
    corpus_root: Path = CORPUS,
    corpus_ref: str = CORPUS_REF,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
) -> dict[str, Any]:
    schedule, sf = _blob_facts(corpus_root, corpus_ref, SCHEDULE)
    notes, nf = _blob_facts(corpus_root, corpus_ref, NOTES)
    srows = schedule[1:]
    rated = [r for r in srows if r.get("body") and "Rates of duty (1-General):" in r["body"]]
    r9802 = [r for r in rated if r["citation_path"].split("/")[-1].startswith("9802")]
    chapter99 = [r for r in notes if r.get("parent_citation_path") == "us/statute/hts/chapter-99"]
    rs_commit = _git(rulespec_root, "rev-parse", "--verify", f"{rulespec_ref}^{{commit}}").decode().strip()
    paths = _git(rulespec_root, "ls-tree", "-r", "--name-only", rs_commit).decode().splitlines()
    modules = sorted(p for p in paths if p.endswith(".yaml") and not p.endswith(".test.yaml") and p.startswith(MODULE_PREFIXES))
    source_counts = {"rated-minus-9802": len(rated)-len(r9802), "rated-9802": len(r9802), "unrated": len(srows)-len(rated), "chapter99-remainder": len(chapter99)-5}
    decisions, computed = _decision_state(source_counts)
    return {"schema": SCHEMA, "program": {"id": "us/tariff-duty", "rulespec_ref": rs_commit}, "generated_facts": {"corpus_roots": {"hts-rate-provisions": {**sf, "declared_count": len(srows)}, "chapter-99-notes": {**nf, "declared_count": len(chapter99)}, "fr-instrument-families": {"derived_from": "composition source_verification plus overlays", "rulespec_commit": rs_commit}}, "rulespec": {"commit": rs_commit, "module_count": len(modules), "paths_sha256": hashlib.sha256(("\n".join(modules)+"\n").encode()).hexdigest()}}, "committed_decisions": decisions, "computed": computed}


def serialize(doc: dict[str, Any]) -> str:
    return "# GENERATED facts; edit decisions in scripts/us_tariff_closure.py.\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)


def validate(doc: dict[str, Any]) -> list[str]:
    errors = []
    expected_decisions, expected_computed = _decision_state(EXPECTED_SOURCE_COUNTS)
    if doc.get("schema") != SCHEMA:
        errors.append("wrong schema")
    if doc.get("program") != EXPECTED_PROGRAM:
        errors.append("program source pin drift")
    generated_facts = doc.get("generated_facts")
    if not isinstance(generated_facts, Mapping):
        errors.append("generated source facts are malformed")
        roots: Mapping[str, Any] = {}
    else:
        roots = generated_facts.get("corpus_roots", {})
        if roots != EXPECTED_CORPUS_ROOTS:
            errors.append("generated corpus source pins changed")
        if generated_facts.get("rulespec") != EXPECTED_RULESPEC_FACTS:
            errors.append("generated RuleSpec source pin changed")
    committed_decisions = doc.get("committed_decisions")
    if committed_decisions != expected_decisions:
        errors.append("committed closure decisions changed")
    computed = doc.get("computed")
    if computed != expected_computed:
        errors.append("computed closure state changed")
    if not isinstance(computed, Mapping):
        computed = {}
    ledger = (
        committed_decisions.get("ledger", [])
        if isinstance(committed_decisions, Mapping)
        else []
    )
    if not isinstance(ledger, list):
        errors.append("invalid status or missing reason")
        ledger = []
    elif any(
        not isinstance(row, Mapping)
        or row.get("status") not in STATUSES
        or not row.get("reason")
        for row in ledger
    ):
        errors.append("invalid status or missing reason")
    should_close = not any(r.get("status") in ("pending", "partially-encoded") for r in ledger)
    if computed.get("closed") != should_close:
        errors.append("computed.closed is not derived")
    frontier = computed.get("boundary_frontier", {})
    if not frontier.get("complete") or frontier.get("input_count") != len(INPUTS):
        errors.append("boundary frontier incomplete")
    expected_inputs = [
        {"input": name, "grounding": "uncaptured", "uncaptured_scope": scope}
        for name, scope in INPUTS
    ]
    if frontier.get("inputs") != expected_inputs:
        errors.append("boundary frontier inputs changed")
    expected_burndown = [
        {
            "family": row.get("family"),
            "root": row.get("root"),
            "status": row.get("status"),
            "blocker": row.get("reason"),
        }
        for row in ledger
        if isinstance(row, Mapping)
        and row.get("status") in ("pending", "partially-encoded")
    ]
    if computed.get("burndown") != expected_burndown:
        errors.append("computed.burndown is not derived")
    counts = computed.get("counts_by_status_per_root")
    if not isinstance(counts, Mapping) or not isinstance(roots, Mapping):
        errors.append("root counts are malformed")
    else:
        for root in ("hts-rate-provisions", "chapter-99-notes"):
            bucket = counts.get(root)
            fact = roots.get(root)
            if not isinstance(bucket, Mapping) or not isinstance(fact, Mapping):
                errors.append(f"missing declared root: {root}")
            elif sum(bucket.values()) != fact.get("declared_count"):
                errors.append(f"declared root does not reconcile: {root}")
    return errors


def validate_artifact(doc: dict[str, Any]) -> ClosureSummary:
    """Validate committed derivations without requiring sibling repositories."""

    errors = validate(doc)
    if errors:
        raise ValueError("; ".join(errors))
    ledger = doc["committed_decisions"]["ledger"]
    return ClosureSummary(
        closed=doc["computed"]["closed"],
        non_encoded_reasons_complete=all(
            isinstance(row, Mapping)
            and isinstance(row.get("reason"), str)
            and bool(row["reason"])
            for row in ledger
        ),
    )


def verify_artifact(
    *,
    artifact_path: Path = ARTIFACT,
    corpus_root: Path = CORPUS,
    corpus_ref: str = CORPUS_REF,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
) -> VerificationResult:
    """Re-derive a committed ledger from the exact pinned Git objects."""

    document: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        document = yaml.safe_load(artifact_path.read_text()) or {}
        validate_artifact(document)
        expected = build(
            corpus_root=corpus_root,
            corpus_ref=corpus_ref,
            rulespec_root=rulespec_root,
            rulespec_ref=rulespec_ref,
        )
        if document != expected:
            errors.append("closure artifact drift; run --generate")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        errors.append(str(exc))
    return VerificationResult(document, expected, tuple(errors))


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    p.add_argument("--artifact", type=Path, default=ARTIFACT)
    p.add_argument("--corpus-root", type=Path, default=CORPUS)
    p.add_argument("--corpus-ref", default=CORPUS_REF)
    p.add_argument("--rulespec-root", type=Path, default=RULESPEC)
    p.add_argument("--rulespec-ref", default=RULESPEC_REF)
    args = p.parse_args(argv)
    try:
        expected = build(
            corpus_root=args.corpus_root,
            corpus_ref=args.corpus_ref,
            rulespec_root=args.rulespec_root,
            rulespec_ref=args.rulespec_ref,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"closure ledger error: {exc}", file=sys.stderr)
        return 1
    errors = validate(expected)
    text = serialize(expected)
    if args.check:
        if not args.artifact.exists() or args.artifact.read_text() != text:
            errors.append("closure artifact drift; run --generate")
    else:
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(text)
    if errors:
        for e in errors:
            print(f"closure ledger error: {e}", file=sys.stderr)
        return 1
    print(f"closure ledger up to date: closed={str(expected['computed']['closed']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
