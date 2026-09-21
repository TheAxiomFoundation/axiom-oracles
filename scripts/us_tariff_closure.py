"""Reproduce the US tariff source-completeness ledger.

Contract (adopted from axiom-oracles PR #475, commits 5402e5bf6 and
75bb586ae): generated facts come only from immutable corpus and RuleSpec Git
objects; review decisions are committed; ``computed`` is their pure join.

Statuses mean: ``encoded`` has a generated RuleSpec representation within one
or more programs in the identified multi-program ensemble; it does not assert
a singular composed output or execution coverage. ``partially-encoded`` has an
encoded rule or membership table but is not fully composed;
``excluded-with-reason`` is in a declared root but cannot affect the relevant
program results for the stated reason; ``pending`` can affect them and is not
encoded. A declared corpus root is the complete, versioned source population
whose denominator is promised here, not merely citations selected by modules.

The boundary-input frontier is reproduced from the pinned compiler and engine,
not maintained as a conceptual alias list. Runtime record facts, law-derived
leaves, and the entry-date execution context are typed separately. ``--check``
re-censuses both repositories and requires byte-identical output. ``closed`` is
true only when there are no partial/pending families, all root populations
reconcile, the input inventory is complete, every bearing instrument is
dispositioned, and no law-derived dependency remains open.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "conformance/closure/us-tariff-duty.yaml"
CORPUS = Path.home() / "TheAxiomFoundation/axiom-corpus"
CORPUS_REF = "bef19f24206a9de4ef29d9ba2b5924f3cc6a00c6"
RULESPEC = Path.home() / "TheAxiomFoundation/_b1wt/rulespec-us"
RULESPEC_REF = "96d5e7c1e6309dc205b7320bbddaae8dd5d410df"
SCHEDULE = "data/corpus/provisions/us/statute/2026-08-09-usitc-hts-2026-rev15-full-schedule.jsonl"
NOTES = "data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl"
SCHEMA = "axiom_oracles.closure.ledger.v3"
# The certificate registry (scripts/certify.py PROGRAMS["us/tariff-duty"]
# .computed.closed.contract) must name exactly this contract; certify.py
# fails closed on any mismatch, and the contract version must be the
# ledger SCHEMA version.
CONTRACT = "us_tariff_closure_v3"
SCHEDULE_SHA256 = "6c8d07d21a1e3f2233197c1b2f96169f01a1a768dd2509a71c0fdb03d4a99d14"
SCHEDULE_VERSION = "2026-08-09-usitc-hts-2026-rev15-full-schedule"
SCHEDULE_DECLARED_COUNT = 29_845
NOTES_SHA256 = "0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8"
NOTES_VERSION = "2026-08-04-usitc-hts-2026-rev15-notes"
NOTES_DECLARED_COUNT = 805
RULESPEC_MODULE_COUNT = 380
RULESPEC_PATHS_SHA256 = (
    "481956d2972610d8fe382d37ee8e651fa8bbeaf29e3550f9b08c06ca656c1a45"
)
STATUSES = ("encoded", "partially-encoded", "excluded-with-reason", "pending")
INSTRUMENT_STATUSES = (
    "encoded",
    "classified-with-reason",
    "excluded-with-reason",
    "pending",
)
MODULE_PREFIXES = (
    "us/policies/usitc/us-tariff-duty/",
    "us/policies/cbp/us-tariff-",
    "us/policies/usitc/us-tariff-incidence/",
)
RATE_TABLE_MODULE_PREFIX = "us/policies/usitc/us-tariff-duty/lines/generated/"
RATE_TABLE_MODULE_COUNT = 100
RATE_TABLE_MODULE_PATHS_SHA256 = (
    "0fd13ed87875af2a948eeb954b7cacad5d0823253b934a86eee1c86aa9d007b0"
)
RATE_TABLE_CITATION_COUNT = 13_790
RATE_TABLE_CITATIONS_SHA256 = (
    "448a3b049638a6a08861baaca11508123e4a4562d1a11fb9aee410d60ceb5ed9"
)
RATE_DISPOSITIONS = (
    "ad_valorem",
    "free",
    "specific",
    "compound",
    "component",
    "conditional",
    "empty",
)
COMPUTABLE_RATE_DISPOSITIONS = frozenset({"ad_valorem", "free"})
PROGRAM_SET_ID = "us-tariff-schedule-ensemble-v1"
PROGRAM_SET_COUNT = 101
PROGRAM_SET_ROWS_SHA256 = (
    "c476cb14ac580ff7e8cf92b8f077bbbe58915beca429ee0c18b76e44484c53d3"
)
EXPECTED_PROGRAM_SET = {
    "id": PROGRAM_SET_ID,
    "scope_kind": "multi-program-ensemble",
    "row_contract": "program_spec<TAB>module<TAB>promised_output",
    "program_count": PROGRAM_SET_COUNT,
    "rows_sha256": PROGRAM_SET_ROWS_SHA256,
    "singular_composed_output": False,
}
INSTRUMENT_GRAPH = ROOT / "conformance/closure/us-tariff-instrument-graph.json"
INSTRUMENT_GRAPH_SCHEMA = "axiom_oracles.closure.us_tariff_instrument_graph.v1"
INSTRUMENT_GRAPH_SHA256 = (
    "11ae44adb7e5131e56c0ca93560d0a84e866a488098b474d77be879b84a169ed"
)
INPUT_INVENTORY_ENGINE = (
    Path.home()
    / "TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine"
)
INPUT_INVENTORY_ENGINE_SHA256 = (
    "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
)
ENGINE_BINARY_PROVENANCE = {
    "identity": "sha256-only",
    "published_source_commit": None,
    "published_release_tag": None,
    "published_build_recipe": None,
    "source_build_proven": False,
    "published_provenance": False,
    "limitation": (
        "Within this contract, identity is the tested binary SHA-256 only; the "
        "contract does not bind a source commit, release tag, or build recipe "
        "and does not prove a source build. Other artifacts may record a source "
        "ref without proving its build link to these bytes."
    ),
}
CLOSURE_REPRODUCTION_CONTRACT = {
    "repo_only": False,
    "external_corpus_git_object": {
        "repository": "TheAxiomFoundation/axiom-corpus",
        "commit": CORPUS_REF,
        "required": True,
    },
    "external_rulespec_git_object": {
        "repository": "TheAxiomFoundation/rulespec-us",
        "commit": RULESPEC_REF,
        "required": True,
    },
    "external_engine_binary": {
        "sha256": INPUT_INVENTORY_ENGINE_SHA256,
        "required": True,
    },
    "engine_binary_provenance": ENGINE_BINARY_PROVENANCE,
    "limitation": (
        "Full closure reproduction requires the exact external corpus and "
        "RuleSpec Git objects plus the hash-identified engine binary; repo-only "
        "validation checks the committed ledger but does not rederive it."
    ),
}
WITNESS_MODULE = "us/policies/cbp/us-tariff-duty/composition.yaml"
SCHEDULE_MODULE_PREFIX = "us/policies/cbp/us-tariff-schedule/generated/"
AUDITED_REACHABLE_INPUTS = (
    "country_of_origin",
    "customs_value",
    "entry_is_brazil_301_listed",
    "entry_is_china_301_2024_action",
    "entry_is_china_301_list123",
    "entry_is_china_301_list4a",
    "entry_is_china_301_solar",
    "entry_is_forced_labor_301_listed",
    "entry_is_line_a",
    "entry_is_line_b",
    "entry_is_line_d",
    "entry_is_section_122_exempt",
    "entry_is_section_201_cspv",
    "entry_is_section_232_aluminum",
    "entry_is_section_232_covered",
    "entry_is_section_232_steel",
    "hts_line",
    "hts_number",
    "is_postal_shipment",
    "resolved_non_ad_valorem_column2_rate",
    "shipment_value",
)
AUDITED_REACHABLE_INPUTS_SHA256 = (
    "aa2ffb176ce74f8a339fc784afe2f5b09a176d0e7779934d780062d3c9e253c7"
)
WORLD_FACT_INPUTS = {
    "country_of_origin": "Country-of-origin determination on the filed or issued entry record.",
    "customs_value": "Appraised customs value on the filed or issued entry record.",
    "hts_line": "Selected HTS line key on the filed or issued entry record.",
    "hts_number": "HTS classification assigned on the filed or issued entry record.",
    "is_postal_shipment": "Postal-channel classification on the filed or issued entry record.",
    "shipment_value": "Shipment value on the filed or issued entry record.",
}
LAW_DERIVED_INPUTS = {
    "entry_is_brazil_301_listed": (
        "Membership in the HTS Note 50 Brazil Section 301 list.",
        "us-hts-2026-rev15",
    ),
    "entry_is_china_301_2024_action": (
        "Membership in the 2024 China Section 301 action.",
        "fr-2024-21217",
    ),
    "entry_is_china_301_list123": (
        "Membership in China Section 301 lists 1, 2, or 3.",
        "us-hts-2026-rev15",
    ),
    "entry_is_china_301_list4a": (
        "Membership in China Section 301 list 4A.",
        "us-hts-2026-rev15",
    ),
    "entry_is_china_301_solar": (
        "Membership in the China solar Section 301 action.",
        "us-hts-2026-rev15",
    ),
    "entry_is_forced_labor_301_listed": (
        (
            "Membership in the HTS Note 52 country-tier action; the reachable "
            "RuleSpec input retains a legacy label that is not used as a legal "
            "description here."
        ),
        "fr-2026-15181",
    ),
    "entry_is_line_a": (
        "Qualification for the applicable Chapter 99 line-A treatment.",
        "us-hts-2026-rev15",
    ),
    "entry_is_line_b": (
        "Qualification for the applicable Chapter 99 line-B treatment.",
        "us-hts-2026-rev15",
    ),
    "entry_is_line_d": (
        "Qualification for the applicable Chapter 99 line-D treatment.",
        "us-hts-2026-rev15",
    ),
    "entry_is_section_122_exempt": (
        "Qualification for a Section 122 surcharge exemption.",
        "fr-2026-03824",
    ),
    "entry_is_section_201_cspv": (
        "Membership in the Section 201 CSPV safeguard scope.",
        "fr-2022-02906",
    ),
    "entry_is_section_232_aluminum": (
        "Membership in the Section 232 aluminum scope.",
        "us-hts-2026-rev15",
    ),
    "entry_is_section_232_covered": (
        "Membership in any Section 232 scope used by the composition.",
        "us-hts-2026-rev15",
    ),
    "entry_is_section_232_steel": (
        "Membership in the Section 232 steel scope.",
        "us-hts-2026-rev15",
    ),
    "resolved_non_ad_valorem_column2_rate": (
        "Resolved ad-valorem equivalent for a non-ad-valorem Column 2 rate.",
        "us-hts-2026-rev15",
    ),
}


@dataclass(frozen=True)
class ClosureSummary:
    """Hermetically derived certificate inputs from a valid ledger."""

    closed: bool
    non_encoded_reasons_complete: bool
    boundary_frontier_complete: bool
    instrument_frontier_complete: bool
    open_dependency_count: int


@dataclass(frozen=True)
class VerificationResult:
    """Result of re-deriving a ledger from its immutable source objects."""

    document: dict[str, Any] | None
    expected: dict[str, Any] | None
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


EXPECTED_PROGRAM = {
    "id": "us/tariff-duty",
    "scope": PROGRAM_SET_ID,
    "rulespec_ref": RULESPEC_REF,
}
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
EXPECTED_DECISION_ROOTS = frozenset(EXPECTED_CORPUS_ROOTS)
EXPECTED_RULESPEC_FACTS = {
    "commit": RULESPEC_REF,
    "module_count": RULESPEC_MODULE_COUNT,
    "paths_sha256": RULESPEC_PATHS_SHA256,
}
EXPECTED_RATE_TABLE_CORRESPONDENCE_FACTS = {
    "partition_kind": "statutory-column-disposition",
    "partition_limitation": (
        "Derived from generated General/column-2 disposition tables plus the "
        "9802 prefix rule; this is not execution coverage."
    ),
    "encoded_count_interpretation": (
        "Static structural computability within the 100 chapter schedule "
        "programs in the multi-program ensemble; not execution coverage or a "
        "singular composed output."
    ),
    "rulespec_commit": RULESPEC_REF,
    "module_count": RATE_TABLE_MODULE_COUNT,
    "module_paths_sha256": RATE_TABLE_MODULE_PATHS_SHA256,
    "corpus_general_rate_count": 13_786,
    "corpus_column2_only_count": 4,
    "corpus_rate_bearing_count": RATE_TABLE_CITATION_COUNT,
    "source_citation_count": RATE_TABLE_CITATION_COUNT,
    "source_citations_sha256": RATE_TABLE_CITATIONS_SHA256,
    "proof_citation_count": RATE_TABLE_CITATION_COUNT,
    "proof_citations_sha256": RATE_TABLE_CITATIONS_SHA256,
    "general_disposition_counts": {
        "ad_valorem": 6_247,
        "free": 5_795,
        "specific": 777,
        "compound": 326,
        "component": 93,
        "conditional": 548,
        "empty": 4,
    },
    "column2_disposition_counts": {
        "ad_valorem": 8_004,
        "free": 853,
        "specific": 1_271,
        "compound": 1_189,
        "component": 84,
        "conditional": 2_229,
        "empty": 160,
    },
    "general_rate_cell_count": 12_042,
    "general_rate_keys_sha256": (
        "06820e14481edbd7033c2a03f5a1f585f358ecb951b7b797789ddf950cbbbd42"
    ),
    "column2_rate_cell_count": 8_857,
    "column2_rate_keys_sha256": (
        "ab2b904788ca792f4e6c6aaca0006a65725e9cb23f62f2b8c9741e4f2c7755ca"
    ),
    "unresolved_non_ad_valorem_count": 4_955,
    "unresolved_non_ad_valorem_paths_sha256": (
        "4be3f417b479a00336e733246a6379f2f997d396abdd50f793577f3a6bbae0a4"
    ),
    "partial_count": 4_956,
    "partial_paths_sha256": (
        "58e50a696df9f67a4a1eca060d79d99ac05e7e680ffd07767d74c060c38d152d"
    ),
    "encoded_count": 8_834,
    "encoded_paths_sha256": (
        "9cce7e06c23e83fc81c23928b73ba0aaab1d7d1f549237e56cbd3fe16d8de467"
    ),
}
EXPECTED_SOURCE_COUNTS = {
    "fully-computable-rate-bearing": 8_834,
    "partial-rate-bearing": 4_956,
    "non-rate": 16_055,
    "chapter99-total": 805,
}


DECISIONS = [
    {
        "root": "hts-rate-provisions",
        "family": "fully-computable-rate-bearing-lines",
        "status": "encoded",
        "count_source": "fully-computable-rate-bearing",
        "reason": (
            "Generated chapter tables source-verify and proof-bind these Rev-15 "
            "rows, and both General and column-2 dispositions are ad valorem or "
            "Free, making them statically and structurally computable within "
            "their chapter schedule programs in the multi-program ensemble. "
            "This classification is not promised-output replay coverage."
        ),
    },
    {
        "root": "hts-rate-provisions",
        "family": "non-ad-valorem-or-partial-value-rate-bearing-lines",
        "status": "partially-encoded",
        "count_source": "partial-rate-bearing",
        "reason": (
            "The generated tables classify and proof-bind these rows, but at "
            "least one statutory column is specific, compound, component-valued, "
            "conditional, or empty, or the 9802 row requires a partial-value duty "
            "base that the promised output neither encodes nor applies; the "
            "compiled frontier has no reduced-base input."
        ),
    },
    {
        "root": "hts-rate-provisions",
        "family": "non-rate-structural-rows",
        "status": "excluded-with-reason",
        "count_source": "non-rate",
        "reason": (
            "Rows without either a Rates of duty (1-General) or Rates of duty "
            "(2) field do not themselves supply a statutory-column rate line."
        ),
    },
    {
        "root": "chapter-99-notes",
        "family": "all-chapter-99-pages",
        "status": "partially-encoded",
        "count_source": "chapter99-total",
        "reason": "Some Chapter 99 rules are composed, but no exact, disjoint citation-path census yet partitions all 805 source pages into encoded, excluded, and pending sets.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-232-metal-instruments",
        "status": "encoded",
        "count": 1,
        "reason": (
            "The 2018 and 2025 metal-action formula paths plus the 2026 annex "
            "restructure are represented in composed aluminum/steel overlays; "
            "instrument disposition and law-derived membership leaves remain "
            "open in the separate dependency frontier."
        ),
    },
    {
        "root": "fr-instrument-families",
        "family": "section-232-non-metal-annexes",
        "status": "pending",
        "count": 6,
        "reason": "Autos/parts, copper, semiconductors, medium/heavy-duty vehicles, and wood proclamation annexes are not encoded (approximately ten annex documents).",
    },
    {
        "root": "fr-instrument-families",
        "family": "china-301-original-2018-actions",
        "status": "pending",
        "count": 1,
        "reason": "Original 2018 instruments are absent from the D0 corpus.",
    },
    {
        "root": "fr-instrument-families",
        "family": "china-301-2024-action",
        "status": "partially-encoded",
        "count": 1,
        "reason": "Membership and overlay exist, but the action is not fed into the final composition.",
    },
    {
        "root": "fr-instrument-families",
        "family": "brazil-301",
        "status": "partially-encoded",
        "count": 1,
        "reason": "Membership and headings exist, but the family is not fed into the final composition.",
    },
    {
        "root": "fr-instrument-families",
        "family": "note-52-country-tier-action",
        "status": "partially-encoded",
        "count": 1,
        "reason": (
            "Membership and country tiers exist under a legacy-named input, but "
            "the family is not fed into the final composition; the exact legal "
            "label remains open."
        ),
    },
    {
        "root": "fr-instrument-families",
        "family": "solar-china",
        "status": "partially-encoded",
        "count": 1,
        "reason": "Membership is encoded but the action is not fed into the final composition.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-201-proclamation-10339",
        "status": "encoded",
        "count": 1,
        "reason": (
            "The solar-safeguard formula path is encoded and composed; the "
            "defining instrument and law-derived membership leaf remain open in "
            "the separate dependency frontier."
        ),
    },
    {
        "root": "fr-instrument-families",
        "family": "section-122-proclamation-11012",
        "status": "encoded",
        "count": 1,
        "reason": (
            "The temporary-surcharge formula and exclusion gate are encoded and "
            "composed; the defining instrument and law-derived exemption leaf "
            "remain open in the separate dependency frontier."
        ),
    },
    {
        "root": "fr-instrument-families",
        "family": "ieepa-orders-and-termination",
        "status": "encoded",
        "count": 1,
        "reason": (
            "Fentanyl, reciprocal-family, exclusion, and termination formula "
            "paths are composed for the codified Rev-15 state; defining "
            "instruments and law-derived leaves remain open in the separate "
            "dependency frontier."
        ),
    },
    {
        "root": "fr-instrument-families",
        "family": "section-338-instruments",
        "status": "pending",
        "count": 1,
        "reason": "Blocked on the missing note-51 ingest.",
    },
    {
        "root": "fr-instrument-families",
        "family": "historical-vintages",
        "status": "pending",
        "count": 1,
        "reason": "This ledger covers the Rev-15 codified state only; historical schedule/instrument vintages are not a reproduced root.",
    },
]

EXECUTION_CONTEXT_INPUTS = {
    "entry_date": (
        "Axiom query period representing the entry date and effective-time context."
    )
}
EXPECTED_INSTRUMENT_IDS = (
    "fr-2022-02906",
    "fr-2024-21217",
    "fr-2025-06063",
    "fr-2025-23316",
    "fr-2026-03824",
    "fr-2026-03829",
    "fr-2026-03832",
    "fr-2026-06960",
    "fr-2026-12669",
    "fr-2026-12670",
    "fr-2026-14542",
    "fr-2026-14991",
    "fr-2026-15181",
    "fr-2026-15274",
    "us-code-19-1321-a-2-c",
    "us-hts-2026-rev15",
)
EXPECTED_INSTRUMENT_CHANNEL_IDS = (
    "corpus-bidirectional-citation-scan",
    "federal-register-authority-and-subject-search",
    "hts-chapter-99-page-census",
    "rulespec-source-verification-citations",
)
EXPECTED_GRAPH_EVIDENCE_CONTRACT = {
    "mode": "pending-only-v1",
    "rule": (
        "This seed graph cannot assert completion or disposition. Every channel "
        "and instrument remains pending until a successor schema rederives source "
        "blobs, query results, candidate union, bearing edges, and encoded-rule "
        "reachability."
    ),
}


def _git(root: Path, *args: str) -> bytes:
    p = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False
    )
    if p.returncode:
        raise ValueError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def _blob_facts(
    root: Path, ref: str, relative: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    blob = _git(root, "show", f"{commit}:{relative}")
    rows = [json.loads(line) for line in blob.splitlines() if line.strip()]
    return rows, {
        "path": relative,
        "commit": commit,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "version": rows[0]["version"],
    }


def _lines_sha256(values: Sequence[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def _derive_program_set(
    rulespec_root: Path,
    rulespec_ref: str,
    paths: Sequence[str],
) -> dict[str, Any]:
    """Hash the exact program-spec, module, and promised-output ensemble."""

    witness_spec = "programs/us/us-tariff-duty/fy-2026.yaml"
    schedule_specs = sorted(
        path
        for path in paths
        if path.startswith("programs/us/us-tariff-schedule/ch")
        and path.endswith(".yaml")
    )
    rows = [
        (
            witness_spec,
            WITNESS_MODULE,
            "us_tariff_duty",
        )
    ]
    rows.extend(
        (
            spec_path,
            (
                SCHEDULE_MODULE_PREFIX
                + f"{Path(spec_path).stem}/{Path(spec_path).stem}.yaml"
            ),
            "schedule_statutory_stack",
        )
        for spec_path in schedule_specs
    )
    if len(schedule_specs) != 100 or len(rows) != PROGRAM_SET_COUNT:
        raise ValueError("tariff program-set cardinality changed")
    path_set = set(paths)
    for spec_path, module_path, promised_output in rows:
        if spec_path not in path_set or module_path not in path_set:
            raise ValueError(
                f"tariff program-set path is absent: {spec_path} / {module_path}"
            )
        spec = yaml.safe_load(
            _git(rulespec_root, "show", f"{rulespec_ref}:{spec_path}")
        )
        outputs = spec.get("outputs") if isinstance(spec, Mapping) else None
        if outputs != [promised_output]:
            raise ValueError(f"tariff program-set promised output changed: {spec_path}")
    lines = ["\t".join(row) for row in rows]
    return {
        "id": PROGRAM_SET_ID,
        "scope_kind": "multi-program-ensemble",
        "row_contract": "program_spec<TAB>module<TAB>promised_output",
        "program_count": len(rows),
        "rows_sha256": _lines_sha256(lines),
        "singular_composed_output": False,
    }


def _derive_rate_table_correspondence(
    schedule_rows: Sequence[Mapping[str, Any]],
    modules: Sequence[tuple[str, Mapping[str, Any]]],
    *,
    rulespec_ref: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Bind every corpus rate-bearing row to generated RuleSpec evidence.

    The complete corpus partition is derived from the pinned HTS row bodies.
    The complete generated-table side is derived from each module's declared
    source-verification paths and rule proof atoms.  Exact set equality makes
    the public encoded count a correspondence, not merely two plausible
    independent totals.
    """

    corpus_paths = [row.get("citation_path") for row in schedule_rows]
    if any(not isinstance(path, str) or not path for path in corpus_paths):
        raise ValueError("HTS schedule has a malformed citation path")
    if len(corpus_paths) != len(set(corpus_paths)):
        raise ValueError("HTS schedule has duplicate citation paths")

    general_paths = {
        row["citation_path"]
        for row in schedule_rows
        if isinstance(row.get("body"), str)
        and "Rates of duty (1-General):" in row["body"]
    }
    column2_paths = {
        row["citation_path"]
        for row in schedule_rows
        if isinstance(row.get("body"), str) and "Rates of duty (2):" in row["body"]
    }
    rate_bearing_paths = general_paths | column2_paths

    module_paths = [path for path, _ in modules]
    if len(module_paths) != len(set(module_paths)):
        raise ValueError("generated rate-table module paths are duplicated")
    source_paths: list[str] = []
    proof_paths: set[str] = set()
    general_dispositions: dict[int, str] = {}
    column2_dispositions: dict[int, str] = {}
    general_rates: dict[int, float] = {}
    column2_rates: dict[int, float] = {}
    for path, document in modules:
        if not isinstance(document, Mapping):
            raise TypeError(f"generated rate-table document is malformed: {path}")
        module = document.get("module")
        if not isinstance(module, Mapping):
            raise TypeError(f"generated rate-table module is malformed: {path}")
        if module.get("proof_validation") != {"required": True}:
            raise ValueError(
                f"generated rate-table module does not require proofs: {path}"
            )
        source_verification = module.get("source_verification")
        citations = (
            source_verification.get("corpus_citation_paths")
            if isinstance(source_verification, Mapping)
            else None
        )
        if not isinstance(citations, list) or any(
            not isinstance(citation, str) or not citation for citation in citations
        ):
            raise ValueError(
                f"generated rate-table source citations are malformed: {path}"
            )
        source_paths.extend(citations)

        rules = document.get("rules")
        if not isinstance(rules, list):
            raise TypeError(f"generated rate-table rules are malformed: {path}")
        rules_by_name = {
            rule.get("name"): rule for rule in rules if isinstance(rule, Mapping)
        }
        if len(rules_by_name) != len(rules):
            raise ValueError(
                f"generated rate-table rules are unnamed or duplicated: {path}"
            )
        stem = Path(path).stem
        for column, target, rate_target in (
            ("general", general_dispositions, general_rates),
            ("column2", column2_dispositions, column2_rates),
        ):
            rule = rules_by_name.get(f"{stem}_{column}_disposition")
            versions = rule.get("versions") if isinstance(rule, Mapping) else None
            values = (
                versions[0].get("values")
                if isinstance(versions, list)
                and len(versions) == 1
                and isinstance(versions[0], Mapping)
                else None
            )
            if (
                not isinstance(values, Mapping)
                or any(
                    not isinstance(key, int)
                    or isinstance(key, bool)
                    or value not in RATE_DISPOSITIONS
                    for key, value in values.items()
                )
                or set(target) & set(values)
            ):
                raise ValueError(
                    f"generated {column} disposition table is malformed: {path}"
                )
            target.update(values)

            rate_rule = rules_by_name.get(f"{stem}_{column}_rate")
            if rate_rule is None:
                rate_values: Mapping[Any, Any] = {}
            else:
                rate_versions = (
                    rate_rule.get("versions")
                    if isinstance(rate_rule, Mapping)
                    else None
                )
                candidate_rate_values = (
                    rate_versions[0].get("values")
                    if isinstance(rate_versions, list)
                    and len(rate_versions) == 1
                    and isinstance(rate_versions[0], Mapping)
                    else None
                )
                if not isinstance(candidate_rate_values, Mapping):
                    raise ValueError(
                        f"generated {column} rate table is malformed: {path}"
                    )
                rate_values = candidate_rate_values
            if any(
                not isinstance(key, int)
                or isinstance(key, bool)
                or not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for key, value in rate_values.items()
            ) or set(rate_target) & set(rate_values):
                raise ValueError(f"generated {column} rate table is malformed: {path}")
            rate_target.update(
                {key: float(value) for key, value in rate_values.items()}
            )
        for rule in rules:
            if not isinstance(rule, Mapping):
                raise TypeError(f"generated rate-table rule is malformed: {path}")
            metadata = rule.get("metadata")
            proof = metadata.get("proof") if isinstance(metadata, Mapping) else None
            atoms = proof.get("atoms", []) if isinstance(proof, Mapping) else []
            if not isinstance(atoms, list):
                raise TypeError(f"generated rate-table proof is malformed: {path}")
            for atom in atoms:
                source = atom.get("source") if isinstance(atom, Mapping) else None
                citation = (
                    source.get("corpus_citation_path")
                    if isinstance(source, Mapping)
                    else None
                )
                if citation is not None:
                    if not isinstance(citation, str) or not citation:
                        raise ValueError(
                            f"generated rate-table proof citation is malformed: {path}"
                        )
                    proof_paths.add(citation)

    if len(source_paths) != len(set(source_paths)):
        raise ValueError("generated rate-table source citations are duplicated")
    source_path_set = set(source_paths)
    if source_path_set != rate_bearing_paths:
        raise ValueError(
            "generated rate-table source citations do not equal the corpus "
            "rate-bearing rows: "
            f"missing={sorted(rate_bearing_paths - source_path_set)[:10]}, "
            f"unexpected={sorted(source_path_set - rate_bearing_paths)[:10]}"
        )
    if proof_paths != rate_bearing_paths:
        raise ValueError(
            "generated rate-table proof citations do not equal the corpus "
            "rate-bearing rows: "
            f"missing={sorted(rate_bearing_paths - proof_paths)[:10]}, "
            f"unexpected={sorted(proof_paths - rate_bearing_paths)[:10]}"
        )

    def line_key(path: str) -> int:
        suffix = path.split("/")[-1]
        digits = suffix.replace(".", "")
        if not digits.isdigit() or len(digits) > 10:
            raise ValueError(f"rate-bearing citation is not an HTS line: {path}")
        return int(digits.ljust(10, "0"))

    path_by_key = {line_key(path): path for path in rate_bearing_paths}
    if len(path_by_key) != len(rate_bearing_paths):
        raise ValueError("rate-bearing citation paths collide as HTS line keys")
    expected_keys = set(path_by_key)
    if set(general_dispositions) != expected_keys:
        raise ValueError("General disposition keys do not equal rate-bearing rows")
    if set(column2_dispositions) != expected_keys:
        raise ValueError("column-2 disposition keys do not equal rate-bearing rows")

    expected_general_rate_keys = {
        key
        for key, value in general_dispositions.items()
        if value in COMPUTABLE_RATE_DISPOSITIONS
    }
    expected_column2_rate_keys = {
        key
        for key, value in column2_dispositions.items()
        if value in COMPUTABLE_RATE_DISPOSITIONS
    }
    if set(general_rates) != expected_general_rate_keys:
        raise ValueError(
            "General rate keys do not equal ad-valorem/free disposition keys"
        )
    if set(column2_rates) != expected_column2_rate_keys:
        raise ValueError(
            "column-2 rate keys do not equal ad-valorem/free disposition keys"
        )
    if any(
        general_dispositions[key] == "free" and value != 0
        for key, value in general_rates.items()
    ) or any(
        column2_dispositions[key] == "free" and value != 0
        for key, value in column2_rates.items()
    ):
        raise ValueError("a Free disposition has a nonzero generated rate cell")

    unresolved_keys = {
        key
        for key in expected_keys
        if general_dispositions[key] not in COMPUTABLE_RATE_DISPOSITIONS
        or column2_dispositions[key] not in COMPUTABLE_RATE_DISPOSITIONS
    }
    partial_9802_keys = {
        key
        for key, path in path_by_key.items()
        if path.split("/")[-1].startswith("9802")
    }
    partial_keys = unresolved_keys | partial_9802_keys
    encoded_keys = expected_keys - partial_keys
    disposition_counts = {
        column: {
            status: sum(value == status for value in dispositions.values())
            for status in RATE_DISPOSITIONS
        }
        for column, dispositions in (
            ("general", general_dispositions),
            ("column2", column2_dispositions),
        )
    }
    facts = {
        "partition_kind": "statutory-column-disposition",
        "partition_limitation": (
            "Derived from generated General/column-2 disposition tables plus the "
            "9802 prefix rule; this is not execution coverage."
        ),
        "encoded_count_interpretation": (
            "Static structural computability within the 100 chapter schedule "
            "programs in the multi-program ensemble; not execution coverage or a "
            "singular composed output."
        ),
        "rulespec_commit": rulespec_ref,
        "module_count": len(modules),
        "module_paths_sha256": _lines_sha256(module_paths),
        "corpus_general_rate_count": len(general_paths),
        "corpus_column2_only_count": len(column2_paths - general_paths),
        "corpus_rate_bearing_count": len(rate_bearing_paths),
        "source_citation_count": len(source_path_set),
        "source_citations_sha256": _lines_sha256(source_path_set),
        "proof_citation_count": len(proof_paths),
        "proof_citations_sha256": _lines_sha256(proof_paths),
        "general_disposition_counts": disposition_counts["general"],
        "column2_disposition_counts": disposition_counts["column2"],
        "general_rate_cell_count": len(general_rates),
        "general_rate_keys_sha256": _lines_sha256([str(key) for key in general_rates]),
        "column2_rate_cell_count": len(column2_rates),
        "column2_rate_keys_sha256": _lines_sha256([str(key) for key in column2_rates]),
        "unresolved_non_ad_valorem_count": len(unresolved_keys),
        "unresolved_non_ad_valorem_paths_sha256": _lines_sha256(
            [path_by_key[key] for key in unresolved_keys]
        ),
        "partial_count": len(partial_keys),
        "partial_paths_sha256": _lines_sha256(
            [path_by_key[key] for key in partial_keys]
        ),
        "encoded_count": len(encoded_keys),
        "encoded_paths_sha256": _lines_sha256(
            [path_by_key[key] for key in encoded_keys]
        ),
    }
    counts = {
        "fully-computable-rate-bearing": len(encoded_keys),
        "partial-rate-bearing": len(partial_keys),
        "non-rate": len(schedule_rows) - len(rate_bearing_paths),
    }
    return facts, counts


def _audited_input_inventory() -> dict[str, Any]:
    digest = hashlib.sha256(
        ("\n".join(AUDITED_REACHABLE_INPUTS) + "\n").encode()
    ).hexdigest()
    typed = set(WORLD_FACT_INPUTS) | set(LAW_DERIVED_INPUTS)
    if (
        len(AUDITED_REACHABLE_INPUTS) != 21
        or digest != AUDITED_REACHABLE_INPUTS_SHA256
        or typed != set(AUDITED_REACHABLE_INPUTS)
        or set(WORLD_FACT_INPUTS) & set(LAW_DERIVED_INPUTS)
    ):
        raise ValueError("audited reachable-input inventory pin changed")
    return {
        "rulespec_ref": RULESPEC_REF,
        "engine_sha256": INPUT_INVENTORY_ENGINE_SHA256,
        "method": (
            "all-version compiled dependency closure of the promised witness "
            "and schedule outputs"
        ),
        "module_scope": [
            WITNESS_MODULE,
            SCHEDULE_MODULE_PREFIX + "ch*/ch*.yaml",
        ],
        "promised_outputs": {
            "witness": ["us_tariff_duty"],
            "schedule": ["schedule_statutory_stack"],
        },
        "schedule_composition_count": 100,
        "input_count": len(AUDITED_REACHABLE_INPUTS),
        "inputs_sha256": digest,
        "inputs": list(AUDITED_REACHABLE_INPUTS),
    }


def _reachable_inputs_from_program(
    program: Mapping[str, Any], outputs: Sequence[str]
) -> set[str]:
    """Traverse compiled dependencies instead of fixture keys or source tokens."""

    relations = program.get("relations", [])
    if relations != []:
        raise ValueError(
            "compiled input inventory contains relations whose predicate inputs "
            "are not yet traversed"
        )
    derived = program.get("derived")
    if not isinstance(derived, list) or any(
        not isinstance(rule, Mapping) or not isinstance(rule.get("name"), str)
        for rule in derived
    ):
        raise ValueError("compiled input inventory has malformed derived rules")
    by_name = {rule["name"]: rule for rule in derived}
    if len(by_name) != len(derived) or not set(outputs) <= by_name.keys():
        raise ValueError("compiled input inventory has missing or duplicate outputs")
    inputs: set[str] = set()
    visited: set[str] = set()

    def visit_expression(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit_expression(item)
        elif isinstance(node, Mapping):
            kind = node.get("kind")
            if kind in {"input", "input_or_else"}:
                name = node.get("name")
                if not isinstance(name, str) or not name:
                    raise ValueError("compiled input inventory has an unnamed input")
                inputs.add(name)
            elif kind == "derived":
                name = node.get("name")
                if not isinstance(name, str) or name not in by_name:
                    raise ValueError("compiled input inventory has an unresolved rule")
                visit_rule(name)
            for value in node.values():
                visit_expression(value)

    def visit_rule(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        rule = by_name[name]
        visit_expression(rule.get("expr"))
        versions = rule.get("versions", [])
        if not isinstance(versions, list) or any(
            not isinstance(version, Mapping) for version in versions
        ):
            raise ValueError("compiled input inventory has malformed versions")
        for version in versions:
            visit_expression(version.get("expr"))

    for output in outputs:
        visit_rule(output)
    return inputs


def reproduce_input_inventory(
    *,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
    engine_binary: Path = INPUT_INVENTORY_ENGINE,
) -> tuple[str, ...]:
    """Reproduce the promised input union from immutable RuleSpec and engine bytes."""

    audit = _audited_input_inventory()
    commit = (
        _git(rulespec_root, "rev-parse", "--verify", f"{rulespec_ref}^{{commit}}")
        .decode()
        .strip()
    )
    if commit != audit["rulespec_ref"]:
        raise ValueError("input inventory RuleSpec source pin drift")
    engine_binary = engine_binary.resolve()
    engine_bytes = engine_binary.read_bytes()
    engine_digest = hashlib.sha256(engine_bytes).hexdigest()
    if engine_digest != audit["engine_sha256"]:
        raise ValueError("input inventory engine source pin drift")
    paths = (
        _git(rulespec_root, "ls-tree", "-r", "--name-only", commit)
        .decode()
        .splitlines()
    )
    chapters = sorted(
        path
        for path in paths
        if path.startswith(SCHEDULE_MODULE_PREFIX)
        and path.endswith(".yaml")
        and not path.endswith(".test.yaml")
    )
    if len(chapters) != audit["schedule_composition_count"]:
        raise ValueError("input inventory schedule composition count changed")
    programs = [
        (WITNESS_MODULE, "programs/us/us-tariff-duty/fy-2026.yaml", "witness")
    ] + [
        (
            path,
            f"programs/us/us-tariff-schedule/{Path(path).stem}.yaml",
            "schedule",
        )
        for path in chapters
    ]
    inputs: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="tariff-closure-input-inventory-") as raw:
        snapshot = Path(raw) / "rulespec-us"
        snapshot.mkdir()
        snapshot_engine = Path(raw) / "axiom-rules-engine"
        snapshot_engine.write_bytes(engine_bytes)
        snapshot_engine.chmod(0o700)
        archive_bytes = _git(rulespec_root, "archive", "--format=tar", commit)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
                archive.extractall(snapshot, filter="data")
        except tarfile.TarError as exc:
            raise ValueError(f"input inventory Git export failed: {exc}") from exc
        env = dict(os.environ)
        env.pop("AXIOM_RULESPEC_ROOT", None)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(snapshot.parent)
        for module_path, spec_path, kind in programs:
            spec = yaml.safe_load((snapshot / spec_path).read_text())
            outputs = spec.get("outputs") if isinstance(spec, Mapping) else None
            if outputs != audit["promised_outputs"][kind]:
                raise ValueError(
                    f"input inventory promised outputs changed: {spec_path}"
                )
            compiled_path = Path(raw) / "inventory.compiled.json"
            compiled_path.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    str(snapshot_engine),
                    "compile",
                    "--program",
                    str(snapshot / module_path),
                    "--output",
                    str(compiled_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                env=env,
            )
            if result.returncode:
                raise ValueError(
                    "input inventory compile failed for "
                    f"{module_path}: {result.stderr.strip()}"
                )
            payload = json.loads(compiled_path.read_text())
            program = payload.get("program") if isinstance(payload, Mapping) else None
            if not isinstance(program, Mapping):
                raise TypeError("compiled input inventory has no program")
            inputs.update(_reachable_inputs_from_program(program, outputs))
    if hashlib.sha256(engine_binary.read_bytes()).hexdigest() != engine_digest:
        raise ValueError("input inventory engine changed during compilation")
    observed = tuple(sorted(inputs))
    if observed != AUDITED_REACHABLE_INPUTS:
        raise ValueError(
            "compiled reachable-input inventory changed: "
            f"missing={sorted(set(AUDITED_REACHABLE_INPUTS) - inputs)}, "
            f"unexpected={sorted(inputs - set(AUDITED_REACHABLE_INPUTS))}"
        )
    return observed


def _load_instrument_graph(
    path: Path = INSTRUMENT_GRAPH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != INSTRUMENT_GRAPH_SHA256:
        raise ValueError("instrument graph source pin drift")
    graph = json.loads(raw)
    if not isinstance(graph, dict):
        raise TypeError("instrument graph must be an object")
    if graph.get("schema") != INSTRUMENT_GRAPH_SCHEMA:
        raise ValueError("instrument graph schema changed")
    if graph.get("program") != "us/tariff-duty":
        raise ValueError("instrument graph program changed")
    if graph.get("rulespec_ref") != RULESPEC_REF:
        raise ValueError("instrument graph RuleSpec pin changed")
    if graph.get("evidence_contract") != EXPECTED_GRAPH_EVIDENCE_CONTRACT:
        raise ValueError("instrument graph evidence contract changed")
    channels = graph.get("channels")
    if not isinstance(channels, list) or len(channels) != 4:
        raise ValueError("instrument graph discovery channels changed")
    if any(
        not isinstance(row, Mapping)
        or not isinstance(row.get("id"), str)
        or row.get("state") != "pending"
        or not isinstance(row.get("reason"), str)
        or not row["reason"].strip()
        for row in channels
    ) or tuple(sorted(row["id"] for row in channels)) != (
        EXPECTED_INSTRUMENT_CHANNEL_IDS
    ):
        raise ValueError(
            "instrument graph v1 requires the exact pending discovery channels"
        )
    instruments = graph.get("instruments")
    if not isinstance(instruments, list):
        raise TypeError("instrument graph instruments are malformed")
    if any(
        not isinstance(row, Mapping) or not isinstance(row.get("id"), str)
        for row in instruments
    ):
        raise ValueError("instrument graph candidate inventory changed")
    ids = tuple(sorted(row["id"] for row in instruments))
    if ids != EXPECTED_INSTRUMENT_IDS or len(ids) != len(instruments):
        raise ValueError("instrument graph candidate inventory changed")
    if any(
        not isinstance(row, Mapping)
        or row.get("status") != "pending"
        or row.get("relation")
        not in {"issued_under", "amends", "bears_on", "rates_publication"}
        or not isinstance(row.get("citation"), str)
        or not row["citation"].strip()
        or not isinstance(row.get("reason"), str)
        or not row["reason"].strip()
        or row.get("bears_on_computed_surface") is not True
        for row in instruments
    ):
        raise ValueError(
            "instrument graph v1 requires every candidate pending and bearing"
        )
    facts = {
        "path": (
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        ),
        "sha256": digest,
        "schema": graph["schema"],
        "rulespec_ref": graph["rulespec_ref"],
        "channel_count": len(channels),
        "enumerated_seed_candidate_count": len(instruments),
    }
    return graph, facts


def _input_grounding_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in AUDITED_REACHABLE_INPUTS:
        if name in WORLD_FACT_INPUTS:
            rows.append(
                {
                    "input": name,
                    "leaf_kind": "world_fact",
                    "grounding": "runtime_required",
                    "reason": WORLD_FACT_INPUTS[name],
                }
            )
            continue
        reason, instrument = LAW_DERIVED_INPUTS[name]
        rows.append(
            {
                "input": name,
                "leaf_kind": "law_derived",
                "grounding": "uncaptured",
                "reason": reason,
                "derivation_instrument": instrument,
            }
        )
    rows.extend(
        {
            "input": name,
            "leaf_kind": "world_fact",
            "role": "execution_context",
            "grounding": "query_period",
            "reason": reason,
        }
        for name, reason in EXECUTION_CONTEXT_INPUTS.items()
    )
    return rows


def _derive_instrument_frontier(graph: Mapping[str, Any]) -> dict[str, Any]:
    instruments = [dict(row) for row in graph["instruments"]]
    counts = {status: 0 for status in INSTRUMENT_STATUSES}
    for row in instruments:
        counts[row["status"]] += 1
    pending = sorted(row["id"] for row in instruments if row.get("status") == "pending")
    channels = [dict(row) for row in graph["channels"]]
    pending_channels = sorted(
        row["id"] for row in channels if row.get("state") != "complete"
    )
    executable_surface = {
        **EXPECTED_PROGRAM_SET,
        "composition_identity_complete": False,
        "closure_eligible": False,
        "reason": (
            "The audited surface is one witness output plus 100 separate "
            "chapter schedule outputs; those outputs are not composed into one "
            "us_tariff_duty output."
        ),
    }
    complete = (
        bool(instruments)
        and not pending
        and all(row.get("state") == "complete" for row in channels)
        and executable_surface["closure_eligible"]
    )
    return {
        "enumeration_scope": "seed-only-v1",
        "enumerated_seed_candidate_count": len(instruments),
        "enumerated_seed_counts_by_status": counts,
        "pending_enumerated_seed_candidates": pending,
        "discovery_channel_count": len(channels),
        "pending_discovery_channels": pending_channels,
        "additional_known_families_open": True,
        "denominator_status": "unknown",
        "executable_surface": executable_surface,
        "complete": complete,
        "discovery_channels": channels,
        "ledger": instruments,
    }


def _derive_dependency_closure(
    inputs: Sequence[Mapping[str, Any]],
    instrument_frontier: Mapping[str, Any],
) -> dict[str, Any]:
    law_derived = sorted(
        row["input"] for row in inputs if row.get("leaf_kind") == "law_derived"
    )
    unclassified = sorted(
        row["input"]
        for row in inputs
        if row.get("leaf_kind") not in {"world_fact", "law_derived"}
    )
    instruments_bearing = sorted(
        row["id"]
        for row in instrument_frontier["ledger"]
        if row.get("bears_on_computed_surface") is True
        and row.get("status") != "encoded"
    )
    open_count = len(law_derived) + len(unclassified) + len(instruments_bearing)
    return {
        "law_derived_inputs": law_derived,
        "unclassified_inputs": unclassified,
        "instruments_bearing_on_computed": instruments_bearing,
        "open_dependency_count": open_count,
        "closed": open_count == 0,
    }


def _grounding_is_well_formed(row: Mapping[str, Any]) -> bool:
    kind = row.get("leaf_kind")
    if kind == "world_fact":
        if row.get("role") == "execution_context":
            return row.get("grounding") == "query_period"
        return "role" not in row and row.get("grounding") == "runtime_required"
    return kind == "law_derived" and row.get("grounding") == "uncaptured"


def _decision_state(
    source_counts: Mapping[str, int],
    instrument_graph: Mapping[str, Any],
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
    frontier = _input_grounding_rows()
    boundary_complete = (
        [row["input"] for row in frontier[: len(AUDITED_REACHABLE_INPUTS)]]
        == list(AUDITED_REACHABLE_INPUTS)
        and [row["input"] for row in frontier[len(AUDITED_REACHABLE_INPUTS) :]]
        == list(EXECUTION_CONTEXT_INPUTS)
        and all(
            row.get("leaf_kind") in {"world_fact", "law_derived"}
            and _grounding_is_well_formed(row)
            and isinstance(row.get("reason"), str)
            and bool(row["reason"].strip())
            for row in frontier
        )
    )
    instrument_frontier = _derive_instrument_frontier(instrument_graph)
    dependency_closure = _derive_dependency_closure(frontier, instrument_frontier)
    reasons_complete = all(
        isinstance(row.get("reason"), str) and bool(row["reason"].strip())
        for row in ledger
    )
    decisions = {"ledger": ledger, "input_grounding": frontier}
    computed = {
        "counts_by_status_per_root": counts,
        "burndown": pending,
        "boundary_frontier": {
            "complete": boundary_complete,
            "compiled_input_count": len(AUDITED_REACHABLE_INPUTS),
            "execution_context_input_count": len(EXECUTION_CONTEXT_INPUTS),
            "input_count": len(frontier),
            "inputs_sha256": AUDITED_REACHABLE_INPUTS_SHA256,
            "inputs": frontier,
        },
        "instrument_frontier": instrument_frontier,
        "dependency_closure": dependency_closure,
        "non_encoded_reasons_complete": reasons_complete,
        "closed": (
            not pending
            and set(counts) == EXPECTED_DECISION_ROOTS
            and all(sum(values.values()) > 0 for values in counts.values())
            and boundary_complete
            and instrument_frontier["complete"]
            and dependency_closure["closed"]
            and reasons_complete
        ),
    }
    return decisions, computed


def build(
    *,
    corpus_root: Path = CORPUS,
    corpus_ref: str = CORPUS_REF,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
    engine_binary: Path = INPUT_INVENTORY_ENGINE,
    instrument_graph_path: Path = INSTRUMENT_GRAPH,
) -> dict[str, Any]:
    schedule, sf = _blob_facts(corpus_root, corpus_ref, SCHEDULE)
    notes, nf = _blob_facts(corpus_root, corpus_ref, NOTES)
    srows = schedule[1:]
    chapter99 = [
        r for r in notes if r.get("parent_citation_path") == "us/statute/hts/chapter-99"
    ]
    rs_commit = (
        _git(rulespec_root, "rev-parse", "--verify", f"{rulespec_ref}^{{commit}}")
        .decode()
        .strip()
    )
    paths = (
        _git(rulespec_root, "ls-tree", "-r", "--name-only", rs_commit)
        .decode()
        .splitlines()
    )
    program_set = _derive_program_set(rulespec_root, rs_commit, paths)
    if program_set != EXPECTED_PROGRAM_SET:
        raise ValueError("tariff program-set pin changed")
    modules = sorted(
        p
        for p in paths
        if p.endswith(".yaml")
        and not p.endswith(".test.yaml")
        and p.startswith(MODULE_PREFIXES)
    )
    rate_table_paths = sorted(
        path
        for path in paths
        if path.startswith(RATE_TABLE_MODULE_PREFIX)
        and path.endswith(".yaml")
        and not path.endswith(".test.yaml")
    )
    rate_table_modules = [
        (path, yaml.safe_load(_git(rulespec_root, "show", f"{rs_commit}:{path}")))
        for path in rate_table_paths
    ]
    rate_table_facts, rate_table_counts = _derive_rate_table_correspondence(
        srows,
        rate_table_modules,
        rulespec_ref=rs_commit,
    )
    if rate_table_facts != EXPECTED_RATE_TABLE_CORRESPONDENCE_FACTS:
        raise ValueError("generated rate-table correspondence pin changed")
    reproduce_input_inventory(
        rulespec_root=rulespec_root,
        rulespec_ref=rs_commit,
        engine_binary=engine_binary,
    )
    instrument_graph, instrument_graph_facts = _load_instrument_graph(
        instrument_graph_path
    )
    source_counts = {**rate_table_counts, "chapter99-total": len(chapter99)}
    decisions, computed = _decision_state(source_counts, instrument_graph)
    return {
        "schema": SCHEMA,
        "program": {
            "id": "us/tariff-duty",
            "scope": PROGRAM_SET_ID,
            "rulespec_ref": rs_commit,
        },
        "reproduction_contract": CLOSURE_REPRODUCTION_CONTRACT,
        "generated_facts": {
            "corpus_roots": {
                "hts-rate-provisions": {**sf, "declared_count": len(srows)},
                "chapter-99-notes": {**nf, "declared_count": len(chapter99)},
                "fr-instrument-families": {
                    "derived_from": "composition source_verification plus overlays",
                    "rulespec_commit": rs_commit,
                },
            },
            "rulespec": {
                "commit": rs_commit,
                "module_count": len(modules),
                "paths_sha256": hashlib.sha256(
                    ("\n".join(modules) + "\n").encode()
                ).hexdigest(),
            },
            "rate_table_correspondence": rate_table_facts,
            "program_set": program_set,
            "input_inventory": _audited_input_inventory(),
            "instrument_graph": instrument_graph_facts,
        },
        "committed_decisions": decisions,
        "computed": computed,
    }


def serialize(doc: dict[str, Any]) -> str:
    return (
        "# GENERATED facts; edit decisions in scripts/us_tariff_closure.py.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)
    )


def validate(
    doc: dict[str, Any],
    *,
    instrument_graph_path: Path = INSTRUMENT_GRAPH,
) -> list[str]:
    errors: list[str] = []
    try:
        instrument_graph, expected_instrument_graph_facts = _load_instrument_graph(
            instrument_graph_path
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    expected_decisions, expected_computed = _decision_state(
        EXPECTED_SOURCE_COUNTS, instrument_graph
    )
    if doc.get("schema") != SCHEMA:
        errors.append("wrong schema")
    if doc.get("program") != EXPECTED_PROGRAM:
        errors.append("program source pin drift")
    if doc.get("reproduction_contract") != CLOSURE_REPRODUCTION_CONTRACT:
        errors.append("closure reproduction contract changed")
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
        if (
            generated_facts.get("rate_table_correspondence")
            != EXPECTED_RATE_TABLE_CORRESPONDENCE_FACTS
        ):
            errors.append("generated rate-table correspondence changed")
        if generated_facts.get("program_set") != EXPECTED_PROGRAM_SET:
            errors.append("generated program set changed")
        if generated_facts.get("input_inventory") != _audited_input_inventory():
            errors.append("generated input inventory changed")
        if generated_facts.get("instrument_graph") != expected_instrument_graph_facts:
            errors.append("generated instrument graph source pin changed")
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
    frontier_value = computed.get("boundary_frontier", {})
    instrument_frontier_value = computed.get("instrument_frontier", {})
    dependency_value = computed.get("dependency_closure", {})
    frontier = frontier_value if isinstance(frontier_value, Mapping) else {}
    instrument_frontier = (
        instrument_frontier_value
        if isinstance(instrument_frontier_value, Mapping)
        else {}
    )
    dependency = dependency_value if isinstance(dependency_value, Mapping) else {}
    reasons_complete = all(
        isinstance(row, Mapping)
        and isinstance(row.get("reason"), str)
        and bool(row["reason"].strip())
        for row in ledger
    )
    should_close = (
        bool(ledger)
        and all(
            isinstance(row, Mapping)
            and row.get("status") not in ("pending", "partially-encoded")
            for row in ledger
        )
        and {row.get("root") for row in ledger if isinstance(row, Mapping)}
        == EXPECTED_DECISION_ROOTS
        and frontier.get("complete") is True
        and instrument_frontier.get("complete") is True
        and dependency.get("closed") is True
        and reasons_complete
    )
    if computed.get("closed") != should_close:
        errors.append("computed.closed is not derived")
    if (
        not isinstance(frontier_value, Mapping)
        or frontier.get("complete") is not True
        or frontier.get("compiled_input_count") != len(AUDITED_REACHABLE_INPUTS)
        or frontier.get("execution_context_input_count")
        != len(EXECUTION_CONTEXT_INPUTS)
        or frontier.get("input_count")
        != len(AUDITED_REACHABLE_INPUTS) + len(EXECUTION_CONTEXT_INPUTS)
        or frontier.get("inputs_sha256") != AUDITED_REACHABLE_INPUTS_SHA256
    ):
        errors.append("boundary frontier incomplete")
    expected_inputs = _input_grounding_rows()
    if frontier.get("inputs") != expected_inputs:
        errors.append("boundary frontier inputs changed")
    if any(
        row.get("leaf_kind") == "law_derived"
        and row.get("derivation_instrument") not in EXPECTED_INSTRUMENT_IDS
        for row in expected_inputs
    ):
        errors.append("law-derived input lacks a defining instrument")
    if not isinstance(instrument_frontier_value, Mapping):
        errors.append("instrument frontier is malformed")
    else:
        instrument_counts = instrument_frontier.get("enumerated_seed_counts_by_status")
        seed_count = instrument_frontier.get("enumerated_seed_candidate_count")
        if (
            isinstance(seed_count, bool)
            or seed_count != len(EXPECTED_INSTRUMENT_IDS)
            or not isinstance(instrument_counts, Mapping)
            or any(
                isinstance(instrument_counts.get(field), bool)
                or not isinstance(instrument_counts.get(field), int)
                for field in INSTRUMENT_STATUSES
            )
            or sum(instrument_counts.values()) != seed_count
            or instrument_frontier.get("discovery_channel_count")
            != len(EXPECTED_INSTRUMENT_CHANNEL_IDS)
            or instrument_frontier.get("denominator_status") != "unknown"
            or instrument_frontier.get("additional_known_families_open") is not True
            or instrument_frontier.get("executable_surface")
            != {
                **EXPECTED_PROGRAM_SET,
                "composition_identity_complete": False,
                "closure_eligible": False,
                "reason": (
                    "The audited surface is one witness output plus 100 separate "
                    "chapter schedule outputs; those outputs are not composed into "
                    "one us_tariff_duty output."
                ),
            }
        ):
            errors.append("instrument frontier counts are malformed")
        if instrument_frontier != expected_computed["instrument_frontier"]:
            errors.append("instrument frontier is not derived")
    if not isinstance(dependency_value, Mapping):
        errors.append("dependency closure is malformed")
    else:
        law_derived = dependency.get("law_derived_inputs")
        unclassified = dependency.get("unclassified_inputs")
        bearing = dependency.get("instruments_bearing_on_computed")
        open_count = dependency.get("open_dependency_count")
        well_formed = (
            isinstance(law_derived, list)
            and isinstance(unclassified, list)
            and isinstance(bearing, list)
            and isinstance(open_count, int)
            and not isinstance(open_count, bool)
            and isinstance(dependency.get("closed"), bool)
            and open_count == len(law_derived) + len(unclassified) + len(bearing)
            and dependency["closed"] == (open_count == 0)
        )
        if not well_formed:
            errors.append("dependency closure is malformed")
        if dependency != expected_computed["dependency_closure"]:
            errors.append("dependency closure is not derived")
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
    if computed.get("non_encoded_reasons_complete") != reasons_complete:
        errors.append("non-encoded reason completeness is not derived")
    counts = computed.get("counts_by_status_per_root")
    if not isinstance(counts, Mapping) or not isinstance(roots, Mapping):
        errors.append("root counts are malformed")
    else:
        for root in ("hts-rate-provisions", "chapter-99-notes"):
            bucket = counts.get(root)
            fact = roots.get(root)
            if not isinstance(bucket, Mapping) or not isinstance(fact, Mapping):
                errors.append(f"missing declared root: {root}")
            elif set(bucket) != set(STATUSES) or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in bucket.values()
            ):
                errors.append(f"declared root counts are malformed: {root}")
            elif sum(bucket.values()) != fact.get("declared_count"):
                errors.append(f"declared root does not reconcile: {root}")
    return errors


def validate_artifact(
    doc: dict[str, Any],
    *,
    instrument_graph_path: Path = INSTRUMENT_GRAPH,
) -> ClosureSummary:
    """Validate committed derivations without requiring sibling repositories."""

    errors = validate(doc, instrument_graph_path=instrument_graph_path)
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
        boundary_frontier_complete=doc["computed"]["boundary_frontier"]["complete"],
        instrument_frontier_complete=doc["computed"]["instrument_frontier"]["complete"],
        open_dependency_count=doc["computed"]["dependency_closure"][
            "open_dependency_count"
        ],
    )


def verify_artifact(
    *,
    artifact_path: Path = ARTIFACT,
    corpus_root: Path = CORPUS,
    corpus_ref: str = CORPUS_REF,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
    engine_binary: Path = INPUT_INVENTORY_ENGINE,
    instrument_graph_path: Path = INSTRUMENT_GRAPH,
) -> VerificationResult:
    """Re-derive a committed ledger from the exact pinned Git objects."""

    document: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        document = yaml.safe_load(artifact_path.read_text()) or {}
        validate_artifact(
            document,
            instrument_graph_path=instrument_graph_path,
        )
        expected = build(
            corpus_root=corpus_root,
            corpus_ref=corpus_ref,
            rulespec_root=rulespec_root,
            rulespec_ref=rulespec_ref,
            engine_binary=engine_binary,
            instrument_graph_path=instrument_graph_path,
        )
        if document != expected:
            errors.append("closure artifact drift; run --generate")
    except (
        OSError,
        TypeError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:
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
    p.add_argument("--engine-binary", type=Path, default=INPUT_INVENTORY_ENGINE)
    p.add_argument("--instrument-graph", type=Path, default=INSTRUMENT_GRAPH)
    args = p.parse_args(argv)
    try:
        expected = build(
            corpus_root=args.corpus_root,
            corpus_ref=args.corpus_ref,
            rulespec_root=args.rulespec_root,
            rulespec_ref=args.rulespec_ref,
            engine_binary=args.engine_binary,
            instrument_graph_path=args.instrument_graph,
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"closure ledger error: {exc}", file=sys.stderr)
        return 1
    errors = validate(expected, instrument_graph_path=args.instrument_graph)
    text = serialize(expected)
    if args.check and (not args.artifact.exists() or args.artifact.read_text() != text):
        errors.append("closure artifact drift; run --generate")
    if errors:
        for e in errors:
            print(f"closure ledger error: {e}", file=sys.stderr)
        return 1
    if args.generate:
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(text)
    print(
        "closure ledger up to date: "
        f"closed={str(expected['computed']['closed']).lower()}, "
        "frontier_complete="
        f"{str(expected['computed']['boundary_frontier']['complete']).lower()}, "
        "instrument_frontier_complete="
        f"{str(expected['computed']['instrument_frontier']['complete']).lower()}, "
        "enumerated_open_dependencies_at_least="
        f"{expected['computed']['dependency_closure']['open_dependency_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
