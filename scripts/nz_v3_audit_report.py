#!/usr/bin/env python3
"""Render the hermetic NZ CERTIFIED.md v3 audit report.

The report is a view over committed NZ closure artifacts.  It does not read the
ops checkout, the network, the corpus clone, or git state.  The pinned ops,
corpus, rebase, search, and citation-scan receipts are instead consumed from the
committed ledgers (or, for the rebase point, the constant recorded below).

Default usage writes ``V3-AUDIT-OUT.md`` at the repository root.  ``--check``
compares that file byte-for-byte with a fresh rendering.  ``--format json``
prints the same normalized report model as deterministic JSON unless an output
path is supplied explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPENDENCY_PATH = REPO_ROOT / "closure" / "nz" / "dependency-dispositions.json"
INSTRUMENT_PATH = REPO_ROOT / "closure" / "nz" / "instrument-dispositions.json"
SUMMARY_PATH = REPO_ROOT / "closure" / "nz" / "summary.json"
DEFAULT_OUTPUT = REPO_ROOT / "V3-AUDIT-OUT.md"

AUDIT_DATE = "2026-08-20"
REBASE_BASE_REF = "origin/main"
REBASE_BASE_SHA = "9a8274b4303b512876b56453622f3cdca3f91725"
IMPLEMENTATION_SHA_PLACEHOLDER = "PENDING_FINAL_COMMIT_SHA"

EXPECTED_PROGRAMS = (
    "nz/acc-earners-levy",
    "nz/accommodation-supplement",
    "nz/income-tax",
    "nz/independent-earner-tax-credit",
    "nz/main-benefits",
    "nz/winter-energy-payment",
    "nz/working-for-families",
)
EXPECTED_GROUNDING = {"encoded": 2, "law_derived": 229, "world_fact": 57}
EXPECTED_ENCODED_INVENTORY = 35
EXPECTED_ENCODED_DEPENDENCIES = 37
EXPECTED_BEARING_INSTRUMENTS = 18
EXPECTED_OPEN_DEPENDENCIES = 247
EXPECTED_CAPTURE_GAP = 136
EXPECTED_WORKLIST = 248
EXPECTED_FRONTIER_COUNTS = {
    "classified-with-reason": 0,
    "encoded": 13,
    "excluded-with-reason": 137,
    "pending": 197,
    "total": 347,
}
EXPECTED_SPINE_SCOPES = {
    "direct_encoded_subgraph_scope": (57, 57, 0),
    "requested_legal_subgraph_scope": (174, 57, 117),
    "all_channel_legal_subgraph_scope": (200, 57, 143),
    "whole_body_scope": (4707, 57, 4650),
}
F1_FRONTIER_COUNTS = {
    "classified-with-reason": 5,
    "encoded": 11,
    "excluded-with-reason": 128,
    "pending": 179,
    "total": 323,
}


class AuditReportError(RuntimeError):
    """Raised when a committed audit input violates the report contract."""


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditReportError(f"cannot read {path.relative_to(REPO_ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditReportError(f"{path.relative_to(REPO_ROOT)} must contain an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditReportError(message)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _sorted_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})


def _counter(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[key]) for row in rows).items()))


def _certificate_premise(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "value": value.get("value"),
            "mode": value.get("mode"),
            "status": value.get("status"),
        }
    if isinstance(value, bool):
        return {"value": value, "mode": None, "status": None}
    return {"value": None, "mode": None, "status": "missing"}


def _certificate_rows() -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted((REPO_ROOT / "certificates").glob("nz-*.json")):
        document = _load_mapping(path)
        program = document.get("program")
        if program not in EXPECTED_PROGRAMS:
            continue
        verdicts = document.get("verdicts")
        if not isinstance(verdicts, dict):
            verdicts = {}
        certified = document.get("certified")
        if isinstance(certified, dict):
            certified_value = certified.get("value")
            certified_state = certified.get("state")
        else:
            certified_value = certified if isinstance(certified, bool) else None
            certified_state = None
        found[str(program)] = {
            "program": str(program),
            "artifact": str(path.relative_to(REPO_ROOT)),
            "conformant": _certificate_premise(verdicts.get("conformant")),
            "exercised": _certificate_premise(verdicts.get("exercised")),
            "closed": _certificate_premise(verdicts.get("closed")),
            "executable": _certificate_premise(verdicts.get("executable")),
            "certified": {"value": certified_value, "state": certified_state},
            "blocker_count": len(document.get("blockers") or []),
        }
    return [
        found.get(
            program,
            {
                "program": program,
                "artifact": None,
                "conformant": _certificate_premise(None),
                "exercised": _certificate_premise(None),
                "closed": _certificate_premise(None),
                "executable": _certificate_premise(None),
                "certified": {"value": None, "state": "missing"},
                "blocker_count": None,
            },
        )
        for program in EXPECTED_PROGRAMS
    ]


def _bearing_instruments(
    instrument: Mapping[str, Any], summary: Mapping[str, Any]
) -> list[dict[str, Any]]:
    by_eli: dict[str, dict[str, Any]] = {}

    def add(row: Mapping[str, Any], *, channel: str) -> None:
        if row.get("status") != "pending" or not row.get("bears_on_computed_surface"):
            return
        if row.get("size_class") not in {"S", "M", "L"}:
            return
        eli = str(row["eli"])
        current = by_eli.setdefault(
            eli,
            {
                "eli": eli,
                "title": None,
                "programs": set(),
                "size_class": str(row["size_class"]),
                "defining_provisions": set(),
                "target_modules": set(),
                "bearings": set(),
                "reasons": set(),
                "discovery_channels": set(),
            },
        )
        _require(
            current["size_class"] == str(row["size_class"]),
            f"bearing instrument size drift for {eli}",
        )
        current["programs"].update(str(value) for value in _list(row.get("programs")))
        if row.get("program"):
            current["programs"].add(str(row["program"]))
        current["defining_provisions"].update(
            str(value) for value in _list(row.get("defining_provision")) if value
        )
        current["target_modules"].update(
            str(value) for value in _list(row.get("target_module")) if value
        )
        current["bearings"].update(
            str(value) for value in _list(row.get("bearing")) if value
        )
        current["reasons"].update(
            str(value) for value in _list(row.get("reason")) if value
        )
        current["discovery_channels"].add(channel)
        current["discovery_channels"].update(
            str(value) for value in _list(row.get("discovery_channels")) if value
        )
        if row.get("title_short"):
            current["title"] = str(row["title_short"])

    decisions = instrument.get("instrument_dispositions")
    supplements = instrument.get("supplemental_instruments")
    _require(isinstance(decisions, list), "NZ instrument dispositions must be a list")
    _require(isinstance(supplements, list), "NZ supplemental instruments must be a list")
    for row in decisions:
        _require(isinstance(row, dict), "NZ instrument disposition row must be an object")
        add(row, channel="official_link_graph_or_f1_supplement")
    for row in supplements:
        _require(isinstance(row, dict), "NZ supplemental instrument row must be an object")
        add(row, channel="subject_matter_search")

    frontier = summary["computed"]["instrument_frontier"]
    titles = {
        str(row["eli"]): str(row.get("title_short") or row.get("eli"))
        for row in frontier.get("ledger") or []
        if isinstance(row, dict) and row.get("eli")
    }
    normalized: list[dict[str, Any]] = []
    for eli, row in sorted(by_eli.items()):
        normalized.append(
            {
                "eli": eli,
                "title": row["title"] or titles.get(eli, eli),
                "programs": sorted(row["programs"]),
                "size_class": row["size_class"],
                "defining_provisions": sorted(row["defining_provisions"]),
                "target_modules": sorted(row["target_modules"]),
                "bearings": sorted(row["bearings"]),
                "reasons": sorted(row["reasons"]),
                "discovery_channels": sorted(row["discovery_channels"]),
            }
        )
    return normalized


def build_model() -> dict[str, Any]:
    dependency = _load_mapping(DEPENDENCY_PATH)
    instrument = _load_mapping(INSTRUMENT_PATH)
    summary = _load_mapping(SUMMARY_PATH)

    grounding = dependency.get("input_grounding")
    encoded = dependency.get("encoded_dependencies")
    _require(isinstance(grounding, list), "NZ input_grounding must be a list")
    _require(isinstance(encoded, list), "NZ encoded_dependencies must be a list")
    _require(all(isinstance(row, dict) for row in grounding), "invalid grounding row")
    _require(all(isinstance(row, dict) for row in encoded), "invalid encoded row")
    law = sorted(
        (row for row in grounding if row.get("leaf_kind") == "law_derived"),
        key=lambda row: (str(row.get("source_surface")), str(row.get("name"))),
    )
    world = sorted(
        (row for row in grounding if row.get("leaf_kind") == "world_fact"),
        key=lambda row: (str(row.get("source_surface")), str(row.get("name"))),
    )
    encoded_inventory = sorted(
        encoded, key=lambda row: (str(row.get("source_surface")), str(row.get("name")))
    )
    encoded_grounding = sorted(
        (row for row in grounding if row.get("classification") == "encoded"),
        key=lambda row: (str(row.get("source_surface")), str(row.get("name"))),
    )
    encoded_rows = sorted(
        [*encoded_inventory, *encoded_grounding],
        key=lambda row: (str(row.get("source_surface")), str(row.get("name"))),
    )
    _require(len(law) == EXPECTED_GROUNDING["law_derived"], "law-derived count drift")
    _require(len(world) == EXPECTED_GROUNDING["world_fact"], "world-fact count drift")
    _require(
        len(encoded_inventory) == EXPECTED_ENCODED_INVENTORY,
        "encoded inventory count drift",
    )
    _require(len(encoded_rows) == EXPECTED_ENCODED_DEPENDENCIES, "encoded count drift")
    _require(
        len({str(row.get("name")) for row in grounding}) == len(grounding),
        "duplicate NZ grounding name",
    )

    computed = summary.get("computed")
    _require(isinstance(computed, dict), "NZ summary lacks computed block")
    dependency_closure = computed.get("dependency_closure")
    input_grounding = computed.get("input_grounding")
    instrument_frontier = computed.get("instrument_frontier")
    spine = computed.get("spine_frontier")
    _require(isinstance(dependency_closure, dict), "missing dependency closure")
    _require(isinstance(input_grounding, dict), "missing input grounding")
    _require(isinstance(instrument_frontier, dict), "missing instrument frontier")
    _require(isinstance(spine, dict), "missing spine frontier")
    for scope_key, (total, encoded_count, pending_count) in EXPECTED_SPINE_SCOPES.items():
        scope = spine.get(scope_key)
        _require(isinstance(scope, dict), f"missing spine scope {scope_key}")
        _require(scope.get("total") == total, f"{scope_key} total drift")
        statuses = scope.get("by_status")
        _require(isinstance(statuses, dict), f"{scope_key} status block missing")
        _require(
            statuses.get("encoded") == encoded_count
            and statuses.get("pending") == pending_count
            and statuses.get("classified") == 0
            and statuses.get("excluded") == 0,
            f"{scope_key} status counts drift",
        )
        _require(
            sum(int(row["total"]) for row in scope.get("instrument_counts") or [])
            == total,
            f"{scope_key} instrument totals drift",
        )
    _require(
        spine["requested_legal_subgraph_scope"].get("pinned_corpus_path_count")
        == 173
        and spine["all_channel_legal_subgraph_scope"].get(
            "pinned_corpus_path_count"
        )
        == 199
        and spine["whole_body_scope"].get("pinned_corpus_row_count") == 4706,
        "spine corpus-membership counts drift",
    )
    _require(
        dependency_closure.get("open_dependency_count") == EXPECTED_OPEN_DEPENDENCIES,
        "open dependency count drift",
    )
    _require(input_grounding.get("counts") == EXPECTED_GROUNDING, "grounding counts drift")
    _require(instrument_frontier.get("counts") == EXPECTED_FRONTIER_COUNTS, "frontier count drift")

    law_names = {
        f"{row['source_surface']}:{row['name']}"
        for row in law
    }
    _require(
        law_names == set(map(str, dependency_closure.get("law_derived_inputs") or [])),
        "summary law-derived frontier does not match dependency ledger",
    )
    bearing = _bearing_instruments(instrument, summary)
    _require(len(bearing) == EXPECTED_BEARING_INSTRUMENTS, "bearing count drift")
    _require(
        {row["eli"] for row in bearing}
        == set(map(str, dependency_closure.get("instruments_bearing_on_computed") or [])),
        "summary bearing frontier does not match instrument ledger",
    )

    gaps = instrument_frontier.get("capture_gaps") or []
    capture_gap = sum(int(row["unresolved_listing_rows"]) for row in gaps)
    _require(capture_gap == EXPECTED_CAPTURE_GAP, "NZ listing capture gap drift")

    discovery = instrument.get("discovery_receipts")
    _require(isinstance(discovery, dict), "missing NZ discovery receipts")
    subject = discovery.get("subject_matter_search")
    citation = discovery.get("corpus_citation_scan")
    _require(isinstance(subject, dict), "missing subject-search receipt")
    _require(isinstance(citation, dict), "missing citation-scan receipt")
    _require(subject.get("searched_at") == AUDIT_DATE, "subject-search date drift")
    _require(len(subject.get("queries") or []) == 31, "subject-search query count drift")
    _require(len(subject.get("result_elis") or []) == 11, "subject-search result count drift")
    approximation = citation.get("approximation")
    _require(isinstance(approximation, dict), "missing citation-scan approximation")
    _require(approximation.get("provision_rows_scanned") == 10171, "citation corpus count drift")
    _require(
        approximation.get("source_target_match_rows") == 560
        and approximation.get("distinct_source_provision_paths") == 535,
        "citation match/path denominator drift",
    )

    supplement_rows = sorted(
        (dict(row) for row in instrument["supplemental_instruments"]),
        key=lambda row: str(row["eli"]),
    )
    subject_rows = [
        row
        for row in supplement_rows
        if "subject_matter_search" in (row.get("discovery_channels") or [])
    ]
    citation_rows = [
        row
        for row in supplement_rows
        if "corpus_citation_scan_approximation"
        in (row.get("discovery_channels") or [])
    ]
    _require(
        set(map(str, subject.get("result_elis") or []))
        == {str(row["eli"]) for row in subject_rows},
        "subject-search receipt/result rows drifted",
    )
    _require(len(citation_rows) == 14, "citation-scan supplemental count drift")
    _require(
        approximation.get("source_instrument_count") == 20
        and approximation.get("new_frontier_count") == 13,
        "citation-scan source coverage count drift",
    )

    global_ledger = instrument_frontier.get("ledger") or []
    retained_current_exclusions = sorted(
        (
            {
                "eli": str(row["eli"]),
                "title": str(row.get("title_short") or row["eli"]),
                "reason": " ".join(
                    sorted(
                        {
                            str(disposition["reason"])
                            for disposition in row.get("program_dispositions") or []
                            if isinstance(disposition, dict)
                            and disposition.get("reason")
                        }
                    )
                )
                or str(row.get("reason") or "see program dispositions"),
            }
            for row in global_ledger
            if isinstance(row, dict)
            and row.get("status") == "excluded-with-reason"
            and row.get("in_force") is not False
        ),
        key=lambda row: row["eli"],
    )
    revoked_or_out_of_period = sum(
        1
        for row in global_ledger
        if isinstance(row, dict)
        and row.get("status") == "excluded-with-reason"
        and row.get("in_force") is False
    )
    _require(len(retained_current_exclusions) == 16, "current exclusion count drift")
    _require(revoked_or_out_of_period == 121, "not-in-force exclusion count drift")
    graph_bears_on_rows = sum(
        1
        for row in global_ledger
        if isinstance(row, dict) and row.get("relation") == "bears_on"
    )
    external_supplement_rows = len(instrument.get("supplemental_instruments") or [])
    _require(graph_bears_on_rows == 22, "graph bears_on supplement count drift")
    _require(external_supplement_rows == 24, "external supplement count drift")
    _require(
        graph_bears_on_rows + external_supplement_rows
        == instrument_frontier.get("supplemental_count"),
        "supplement decomposition drift",
    )

    capture_item = {
        "kind": "capture_gap",
        "size_class": "L",
        "unresolved_listing_rows": capture_gap,
        "by_act": sorted(
            (dict(row) for row in gaps), key=lambda row: str(row["act_citation_path"])
        ),
        "target": "NZ instrument graph capture",
        "method": (
            "Reverse-index the official PCO bulk XML by empowering-Act citations, "
            "then reconcile canonical ELIs to the advertised Act-tab totals. Do not "
            "scrape the client-rendered tab; respect legislation.govt.nz bot boundaries."
        ),
    }

    worklist: list[dict[str, Any]] = []
    for row in law:
        worklist.append(
            {
                "number": len(worklist) + 1,
                "kind": "law_derived",
                "name": str(row["name"]),
                "source_surface": str(row["source_surface"]),
                "size_class": str(row["size_class"]),
                "defining_instrument": str(row["derivation_instrument"]),
                "target_modules": _sorted_unique(_list(row.get("target_module"))),
                "reason": str(row["reason"]),
            }
        )
    for row in bearing:
        worklist.append({"number": len(worklist) + 1, "kind": "bearing_instrument", **row})
    worklist.append({"number": len(worklist) + 1, **capture_item})
    _require(len(worklist) == EXPECTED_WORKLIST, "typed worklist count drift")
    _require(worklist[-1]["number"] == 248, "capture gap is not worklist item 248")

    worklist_sizes = Counter(str(row["size_class"]) for row in worklist)
    size_by_kind = {
        kind: dict(
            sorted(Counter(row["size_class"] for row in worklist if row["kind"] == kind).items())
        )
        for kind in ("law_derived", "bearing_instrument", "capture_gap")
    }
    _require(
        dict(sorted(worklist_sizes.items())) == {"L": 141, "M": 78, "S": 29},
        "size totals drift",
    )

    scope_receipts = dependency.get("scope_receipts")
    _require(isinstance(scope_receipts, dict), "missing dependency scope receipts")
    corpus_release = str(summary.get("corpus_release"))
    corpus_commit = str(summary.get("corpus_commit"))

    adjudication_questions = [
        (
            "Spine scope: does the DE PR #485 precedent license the 174-root "
            "dependency lower bound (or the 200-root citation-expanded lower bound), "
            "or does v3 require the 4,707-row whole-governing-Act alternative? The "
            "choice, one official-web-only exact amendment root, unresolved root "
            "expansion, and body-hash ledger must be explicit."
        ),
        (
            "Multi-Act graph schema: should NZ retain one extended graph for three "
            "empowering Acts, or publish a standardized wrapper of one v1 graph per Act?"
        ),
        (
            "Disposition dimension: should a single ELI have one global disposition, "
            "or may the same instrument carry different program-scoped decisions?"
        ),
        (
            "Multi-owner instruments: how should guidance or precedent that bears on "
            "more than one Act/program be owned without losing any dependency edge?"
        ),
        (
            "Official capture: which supported PCO reverse-relation endpoint or bulk-XML "
            "reverse index becomes the canonical replacement for the inaccessible "
            "client-rendered Act tab and closes the 136-row gap?"
        ),
    ]

    return {
        "schema": "axiom_oracles.nz_v3_audit_report.v1",
        "audit": {
            "date": AUDIT_DATE,
            "definition": "CERTIFIED.md v3",
            "outcome": "aggregation blockers cleared, closed honestly open under v3",
            "requested_output": "/Users/maxghenis/TheAxiomFoundation/ops/nz-lane/_cert/sol-v3-nz-audit.md",
            "actual_output": "V3-AUDIT-OUT.md",
            "fallback_reason": "The ops checkout is outside the writable sandbox; no ops file was modified.",
            "rebase_base": {"ref": REBASE_BASE_REF, "sha": REBASE_BASE_SHA},
            "implementation_sha": {
                "value": IMPLEMENTATION_SHA_PLACEHOLDER,
                "status": "placeholder: replace with the final implementation commit SHA after commit",
            },
        },
        "part_1_leaf_typing": {
            "scope_receipts": scope_receipts,
            "typed_input_count": len(grounding),
            "counts": EXPECTED_GROUNDING,
            "additional_encoded_inventory_count": EXPECTED_ENCODED_INVENTORY,
            "law_derived_by_surface": _counter(law, "source_surface"),
            "law_derived_by_size": _counter(law, "size_class"),
            "world_facts_by_surface": _counter(world, "source_surface"),
            "encoded_dependencies_by_surface": _counter(encoded_rows, "source_surface"),
            "world_facts": world,
            "encoded_dependencies": encoded_rows,
        },
        "part_2_instruments": {
            "f1_counts": F1_FRONTIER_COUNTS,
            "v3_counts": dict(instrument_frontier["counts"]),
            "reported_link_rows": instrument_frontier.get("reported_instrument_count"),
            "captured_pco_rows": instrument_frontier.get("instrument_count"),
            "supplemental_rows": instrument_frontier.get("supplemental_count"),
            "graph_bears_on_rows": graph_bears_on_rows,
            "external_supplement_rows": external_supplement_rows,
            "capture_gaps": gaps,
            "retained_not_in_force_or_superseded": revoked_or_out_of_period,
            "retained_current_nonbearing_exclusions": retained_current_exclusions,
            "bearing_instruments": bearing,
            "subject_search": subject,
            "subject_search_results": subject_rows,
            "citation_scan_supplemental_results": citation_rows,
            "citation_scan": citation,
        },
        "part_3_spine": {
            "corpus_release": corpus_release,
            "corpus_commit": corpus_commit,
            "release_manifest": {
                "path": "manifests/releases/nz-rulespec-2026-07-18.json",
                "sha256": (
                    "4b7dee4b23c6e5eb2eafcff80e4fa7bee07af30cdb98c535e635fcd56b872447"
                ),
            },
            "pinned_corpus_scopes": [
                {
                    "class": "statute",
                    "rows": 9519,
                    "sha256": (
                        "e18cbb943d3055b93528989afaec4816fd13b4dadc1945a3fde35ffd16a3fd42"
                    ),
                },
                {
                    "class": "regulation",
                    "rows": 652,
                    "sha256": (
                        "a9b0427491069803dce9800a0d86e4afa3dd40a8e5d4e5357d99bed135dfcb0d"
                    ),
                },
                {
                    "class": "district-plan",
                    "rows": 865,
                    "sha256": (
                        "4e34f0659f1287ef711fd81bb3dff1a81a61bb278eb6ecba0b14dd46d46929c4"
                    ),
                },
            ],
            "pinned_corpus_provision_rows": 11036,
            "governing_act_counting_rule": (
                "count pinned JSONL rows for the source_document_id only when "
                "the body field is non-empty"
            ),
            "governing_act_counts": [
                {
                    "instrument": "Accident Compensation Act 2001",
                    "raw_citation_paths": 550,
                    "nonempty_body_rows": 535,
                },
                {
                    "instrument": "Income Tax Act 2007",
                    "raw_citation_paths": 3138,
                    "nonempty_body_rows": 3099,
                },
                {
                    "instrument": "Social Security Act 2018",
                    "raw_citation_paths": 1041,
                    "nonempty_body_rows": 1001,
                },
            ],
            "frontier": spine,
        },
        "part_4_worklist": {
            "open_dependency_count": EXPECTED_OPEN_DEPENDENCIES,
            "capture_gap_count": 1,
            "total": len(worklist),
            "size_counts": dict(sorted(worklist_sizes.items())),
            "size_counts_by_kind": size_by_kind,
            "items": worklist,
        },
        "part_5_integration": {
            "summary_schema": summary.get("schema"),
            "dependency_schema": dependency.get("schema"),
            "instrument_schema": instrument.get("schema"),
            "closed": summary.get("closed"),
            "computed_dependency_closure": dependency_closure,
            "generated_fact_receipts": {
                key: value
                for key, value in (summary.get("generated_facts") or {}).items()
                if key in {"dependency_dispositions", "instrument_dispositions"}
            },
            "certificates": _certificate_rows(),
            "certificate_section_status": (
                "live placeholder: values are read from current certificate artifacts; "
                "rerun this producer after the final certify refresh"
            ),
            "gate_receipts": {
                "producers_check": "PENDING_FINAL_GATE_RUN",
                "certify_check": "PENDING_FINAL_GATE_RUN",
                "whole_mutant_file": "PENDING_FINAL_GATE_RUN",
                "simulated_nz_refresh": "PENDING_FINAL_GATE_RUN",
                "simulated_dk_refresh": "PENDING_FINAL_GATE_RUN",
                "cross_jurisdiction_byte_identity": "PENDING_FINAL_GATE_RUN",
            },
        },
        "adjudication_questions": adjudication_questions,
    }


def render_json(model: Mapping[str, Any]) -> str:
    """Return deterministic, UTF-8-friendly JSON for the normalized report model."""

    return json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _md(value: Any) -> str:
    if value is None:
        text = "—"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _codes(values: Iterable[str]) -> str:
    normalized = list(values)
    return ", ".join(f"`{_md(value)}`" for value in normalized) if normalized else "—"


def _premise_cell(value: Mapping[str, Any]) -> str:
    parts = [_md(value.get("value"))]
    if value.get("mode"):
        parts.append(_md(value["mode"]))
    if value.get("status"):
        parts.append(_md(value["status"]))
    return " / ".join(parts)


def _count_table(title: str, counts: Mapping[str, int]) -> list[str]:
    lines = [f"### {title}", "", "| Type | Count |", "|---|---:|"]
    lines.extend(f"| `{_md(key)}` | {value} |" for key, value in sorted(counts.items()))
    lines.append("")
    return lines


def render_markdown(model: Mapping[str, Any]) -> str:
    """Return deterministic Markdown for the normalized report model."""

    audit = model["audit"]
    part1 = model["part_1_leaf_typing"]
    part2 = model["part_2_instruments"]
    part3 = model["part_3_spine"]
    part4 = model["part_4_worklist"]
    part5 = model["part_5_integration"]
    lines: list[str] = [
        "# NZ audit under CERTIFIED.md definition v3",
        "",
        f"**Outcome:** {audit['outcome']}.",
        "",
        (
            f"This is the deterministic audit rendered on the fixed discovery date "
            f"**{audit['date']}** from the committed NZ ledgers. The requested ops "
            f"destination `{audit['requested_output']}` is outside the writable sandbox, "
            f"so the report is emitted as `{audit['actual_output']}`. {audit['fallback_reason']}"
        ),
        "",
        (
            f"Rebase base: `{audit['rebase_base']['ref']}` at "
            f"`{audit['rebase_base']['sha']}`. Implementation SHA: "
            f"`{audit['implementation_sha']['value']}` — **{audit['implementation_sha']['status']}**."
        ),
        "",
        "## Part 1 — leaf typing (dependency closure)",
        "",
        (
            f"The committed boundary ledger types all **{part1['typed_input_count']}** inputs "
            f"consumed by the NZ comparison composition, harness request surface, declared "
            f"eligibility closures, and semantically upstream omitted legal surface: "
            f"**{part1['counts']['law_derived']} law-derived** and "
            f"**{part1['counts']['world_fact']} world facts**, with "
            f"**{part1['counts']['encoded']} request inputs encoded by cross-module wiring**. "
            f"It separately inventories **{part1['additional_encoded_inventory_count']}** "
            f"compiled parameters, engine outputs, and composition outputs, so the table below "
            f"contains **{len(part1['encoded_dependencies'])} encoded dependencies** in all. Case supply, "
            "a constant, or a documented closure never converts a legally computed quantity "
            f"into a world fact. Every law-derived row appears exactly once in worklist items "
            f"1–{part1['counts']['law_derived']}."
        ),
        "",
        "### Hermetic scope receipts",
        "",
        "| Surface | Repository / artifact | Commit or SHA-256 |",
        "|---|---|---|",
    ]
    for key, receipt in sorted(part1["scope_receipts"].items()):
        if key == "denominator":
            lines.append(
                f"| `{_md(key)}` | compiled/request census | `{_md(receipt)}` |"
            )
            continue
        location = receipt.get("path") or receipt.get("artifact") or receipt.get("repository")
        repository = receipt.get("repository")
        if repository and receipt.get("path"):
            location = f"{repository}:{receipt['path']}"
        binding = receipt.get("repository_commit") or receipt.get("sha256")
        if receipt.get("repository_commit") and receipt.get("sha256"):
            binding = f"{receipt['repository_commit']} / sha256:{receipt['sha256']}"
        lines.append(f"| `{_md(key)}` | `{_md(location)}` | `{_md(binding)}` |")
    lines.append("")
    lines.extend(_count_table("Law-derived rows by source surface", part1["law_derived_by_surface"]))
    lines.extend(_count_table("Law-derived rows by size", part1["law_derived_by_size"]))

    lines.extend(
        [
            f"### All {part1['counts']['world_fact']} world-fact leaves",
            "",
            "These are dates, reported scenario/payroll amounts, register-style payment or "
            "status facts, issued decisions, filings, events, or documented property/contract "
            "facts with independent existence.",
            "",
            "| # | Name | Surface | Observed/declared value | Grounding reason |",
            "|---:|---|---|---|---|",
        ]
    )
    for number, row in enumerate(part1["world_facts"], 1):
        value = row.get("declared_value", row.get("observed_state"))
        lines.append(
            f"| {number} | `{_md(row['name'])}` | `{_md(row['source_surface'])}` | "
            f"{_md(value)} | {_md(row['reason'])} |"
        )
    lines.append("")

    lines.extend(
        [
            f"### All {len(part1['encoded_dependencies'])} encoded dependencies",
            "",
            "| # | Dependency | Surface | Encoded by | Reason |",
            "|---:|---|---|---|---|",
        ]
    )
    for number, row in enumerate(part1["encoded_dependencies"], 1):
        lines.append(
            f"| {number} | `{_md(row['name'])}` | `{_md(row['source_surface'])}` | "
            f"`{_md(row['encoded_by'])}` | {_md(row['reason'])} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Part 2 — instrument re-disposition under the bearing rule",
            "",
            "Any instrument bearing on a computed surface is encoded or pending; none remains "
            "classified around a case-supplied input. F1's five global classifications move "
            "to pending, and the formerly excluded IS 26/12 fact sheet moves to pending. "
            "The current frontier also includes the mandatory search-discovered supplements.",
            "",
            "| Frontier | Encoded | Classified | Excluded | Pending | Total |",
            "|---|---:|---:|---:|---:|---:|",
            (
                f"| F1 before v3 audit | {part2['f1_counts']['encoded']} | "
                f"{part2['f1_counts']['classified-with-reason']} | "
                f"{part2['f1_counts']['excluded-with-reason']} | "
                f"{part2['f1_counts']['pending']} | {part2['f1_counts']['total']} |"
            ),
            (
                f"| v3 audit | {part2['v3_counts']['encoded']} | "
                f"{part2['v3_counts']['classified-with-reason']} | "
                f"{part2['v3_counts']['excluded-with-reason']} | "
                f"{part2['v3_counts']['pending']} | {part2['v3_counts']['total']} |"
            ),
            "",
            (
                f"The official Act tabs advertise **{part2['reported_link_rows']}** rows. The "
                f"PCO bulk replay captured **{part2['captured_pco_rows']}** official graph "
                f"rows. The computed supplement count of **{part2['supplemental_rows']}** "
                f"decomposes into **{part2['graph_bears_on_rows']}** graph rows with relation "
                f"`bears_on` plus **{part2['external_supplement_rows']}** external search/"
                "citation supplements; it is not 46 external instruments. The "
                f"unresolved official-listing gap remains **{sum(row['unresolved_listing_rows'] for row in part2['capture_gaps'])}**."
            ),
            "",
            (
                f"Honest exclusions retain {part2['retained_not_in_force_or_superseded']} "
                "not-in-force, superseded, or out-of-period rows. The 16 current exclusions "
                "are the six F1 graph rows with no computed bearing, the post-period Taxation "
                "(Budget Measures) Act 2026, and nine citation-scan sources that are downstream, "
                "reverse-reference, register-boundary, or outside-surface instruments."
            ),
            "",
            "### Current, honestly non-bearing exclusions",
            "",
            "| Instrument | Reason |",
            "|---|---|",
        ]
    )
    for row in part2["retained_current_nonbearing_exclusions"]:
        lines.append(f"| [{_md(row['title'])}]({row['eli']}) | {_md(row['reason'])} |")
    lines.append("")

    lines.extend(
        [
            "### Subject-matter search pass",
            "",
            (
                f"Search date: **{part2['subject_search']['searched_at']}**. Sources: "
                + ", ".join(f"[{url}]({url})" for url in part2["subject_search"]["sources"])
                + "."
            ),
            "",
            "Queries (verbatim):",
            "",
        ]
    )
    lines.extend(f"- `{_md(query)}`" for query in part2["subject_search"]["queries"])
    lines.extend(
        [
            "",
            "Search results entering the frontier:",
            "",
            "| Instrument | Status | Programs | Bearing / exclusion reason |",
            "|---|---|---|---|",
        ]
    )
    for row in part2["subject_search_results"]:
        lines.append(
            f"| [{_md(row['title_short'])}]({row['eli']}) | `{_md(row['status'])}` | "
            f"{_codes(row.get('programs') or [])} | {_md(row['reason'])} |"
        )
    for row in part2["subject_search"].get("excluded_leads") or []:
        lines.append(
            f"| [Excluded lead]({row['url']}) | `excluded lead` | — | {_md(row['reason'])} |"
        )
    lines.append("")

    citation = part2["citation_scan"]
    approximation = citation["approximation"]
    lines.extend(
        [
            "### Corpus citation-scan note",
            "",
            (
                f"`{citation['implementation_issue']}` is **not runnable for NZ** in the "
                f"inspected clone `{citation['inspected_clone_commit']}`. Status: "
                f"`{citation['status']}`. {citation['reason']}"
            ),
            "",
            (
                f"A read-only exact-title approximation scanned "
                f"**{approximation['provision_rows_scanned']}** pinned provision rows and found "
                f"**{approximation['source_target_match_rows']} source–target citation matches** "
                f"across **{approximation['distinct_source_provision_paths']} distinct source "
                "provision paths**: "
                + ", ".join(
                    f"{name} {count}" for name, count in sorted(approximation["target_counts"].items())
                )
                + ". These are match rows, not 560 unique provisions or instruments, and not "
                "#611 completeness."
            ),
            "",
            (
                f"The hits resolve to **{approximation['source_instrument_count']} distinct "
                f"source instruments**. All 20 are explicitly covered below: 3 governing "
                "spine roots, 3 existing official-graph rows, the already dispositioned 2026 "
                f"annual-rates Act, and **{approximation['new_frontier_count']} newly added "
                "frontier rows** (4 pending because they bear on computed surfaces; 9 honest "
                "exclusions)."
            ),
            "",
            f"- Full approximation: `{approximation['artifact']}`, SHA-256 `{approximation['sha256']}`.",
            f"- Grouped summary: `{approximation['summary_artifact']}`, SHA-256 `{approximation['summary_sha256']}`.",
            f"- Pinned corpus release commit: `{citation['pinned_release_commit']}`.",
            "- A real scan must resolve aliases and provision references in both directions; the pinned release omits guidance, cases, and several amendment Acts, so citation scanning supplements but cannot replace subject search.",
            "",
            "Citation-source disposition coverage:",
            "",
            "| Source instrument | Source–target matches | Distinct provision paths | Resolution | Frontier reference |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in approximation["source_dispositions"]:
        lines.append(
            f"| {_md(row['title'])} | {row['source_target_match_rows']} | "
            f"{row['distinct_source_provision_paths']} | "
            f"`{_md(row['resolution'])}` | `{_md(row['frontier_ref'])}` |"
        )
    lines.extend(
        [
            "",
            "## Part 3 — spine closure position",
            "",
            (
                f"Pinned corpus release `{part3['corpus_release']}` at "
                f"`{part3['corpus_commit']}` contains "
                f"**{part3['pinned_corpus_provision_rows']} provision rows** across the "
                "three scopes below. Its release manifest is "
                f"`{part3['release_manifest']['path']}` at SHA-256 "
                f"`{part3['release_manifest']['sha256']}`."
            ),
            "",
            "| Pinned corpus scope | Provision rows | JSONL SHA-256 |",
            "|---|---:|---|",
            *(
                f"| `{row['class']}` | {row['rows']} | `{row['sha256']}` |"
                for row in part3["pinned_corpus_scopes"]
            ),
            "",
            (
                "Whole-governing-Act denominators "
                f"{part3['governing_act_counting_rule']}: "
                + "; ".join(
                    f"{row['instrument']} {row['nonempty_body_rows']} of "
                    f"{row['raw_citation_paths']} raw citation paths"
                    for row in part3["governing_act_counts"]
                )
                + ". This is why the ITA denominator is 3,099 rather than 3,138."
            ),
            "",
            (
                f"Precedent: {part3['frontier']['precedent']['rule']} Source: "
                f"`{part3['frontier']['precedent']['source']}`. For NZ: "
                f"{part3['frontier']['precedent']['nz_candidate_application']}"
            ),
            "",
            "The precedent does not unambiguously resolve the 3,099-provision Income Tax Act. "
            "All four positions are therefore reported; none is silently selected. The 57 "
            "direct paths are demonstrably insufficient under v3. The 174 dependency-root "
            "and 200 citation-expanded scopes contain respectively 173 and 199 pinned-corpus "
            "paths plus the web-verified 2025 No 9 s 105 root. They remain lower bounds because "
            "vague ranges, imported definitions, subject-search results, and other off-release "
            "sources remain unquantified. "
            "The whole-Act alternative expands the three governing Acts while retaining exact "
            "roots—not whole bodies—for subordinate and evidence instruments.",
            "",
        ]
    )

    for scope_key in (
        "direct_encoded_subgraph_scope",
        "requested_legal_subgraph_scope",
        "all_channel_legal_subgraph_scope",
        "whole_body_scope",
    ):
        scope = part3["frontier"][scope_key]
        lines.extend(
            [
                f"### {scope['label']}",
                "",
                "| Instrument | Encoded | Classified | Excluded | Pending | Total |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in scope["instrument_counts"]:
            status = row["by_status"]
            lines.append(
                f"| {_md(row['instrument'])} | {status['encoded']} | {status['classified']} | "
                f"{status['excluded']} | {status['pending']} | {row['total']} |"
            )
        status = scope["by_status"]
        lines.append(
            f"| **Total** | **{status['encoded']}** | **{status['classified']}** | "
            f"**{status['excluded']}** | **{status['pending']}** | **{scope['total']}** |"
        )
        lines.append("")
    lines.extend(
        [
            f"Spine blockers: {_codes(part3['frontier']['blockers'])}.",
            "",
            "## Part 4 — the typed worklist",
            "",
            (
                f"One continuous list follows: {part1['counts']['law_derived']} law-derived "
                f"inputs, {len(part2['bearing_instruments'])} unique bearing instruments, then "
                f"the 136-row capture gap as item {part4['total']}. The central dependency "
                f"gate counts **{part4['open_dependency_count']}** open legal dependencies; the "
                "capture gap is an additional frontier-completeness item."
            ),
            "",
            "| Kind | S | M | L | Total |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for kind, label in (
        ("law_derived", "Law-derived inputs"),
        ("bearing_instrument", "Bearing instruments"),
        ("capture_gap", "Capture gap"),
    ):
        counts = part4["size_counts_by_kind"][kind]
        lines.append(
            f"| {label} | {counts.get('S', 0)} | {counts.get('M', 0)} | "
            f"{counts.get('L', 0)} | {sum(counts.values())} |"
        )
    lines.append(
        f"| **Total** | **{part4['size_counts']['S']}** | **{part4['size_counts']['M']}** | "
        f"**{part4['size_counts']['L']}** | **{part4['total']}** |"
    )
    lines.append("")

    for item in part4["items"]:
        number = item["number"]
        if item["kind"] == "law_derived":
            lines.append(
                f"{number}. `{_md(item['source_surface'])}:{_md(item['name'])}` — "
                f"**law_derived, size {item['size_class']}**. Defining instrument/provision: "
                f"{_md(item['defining_instrument'])}. Target: {_codes(item['target_modules'])}. "
                f"Grounding: {_md(item['reason'])}"
            )
        elif item["kind"] == "bearing_instrument":
            provisions = "; ".join(item["defining_provisions"]) or "instrument as a whole"
            reasons = " ".join(item["reasons"])
            lines.append(
                f"{number}. [{_md(item['title'])}]({item['eli']}) — "
                f"**bearing instrument, size {item['size_class']}**. Programs: "
                f"{_codes(item['programs'])}. Defining provision: {_md(provisions)}. Target: "
                f"{_codes(item['target_modules'])}. {_md(reasons)}"
            )
        else:
            by_act = ", ".join(
                f"`{row['act_citation_path']}`={row['unresolved_listing_rows']}"
                for row in item["by_act"]
            )
            lines.append(
                f"{number}. **Official instrument-listing capture gap — size L.** "
                f"{item['unresolved_listing_rows']} unresolved rows ({by_act}). Target: "
                f"{item['target']}. {item['method']}"
            )
    lines.append("")

    lines.extend(
        [
            "## Part 5 — ledger integration and certificate position",
            "",
            (
                f"The v3 ledgers use `{part5['dependency_schema']}` and "
                f"`{part5['instrument_schema']}`; the derived summary uses "
                f"`{part5['summary_schema']}`. `closed` is **{_md(part5['closed'])}**. The "
                f"central block exposes {part1['counts']['law_derived']} law-derived inputs "
                f"plus {len(part2['bearing_instruments'])} bearing instruments "
                f"(`open_dependency_count={part4['open_dependency_count']}`) rather than "
                "relying on the stale pre-v3 path."
            ),
            "",
            "Generated-fact bindings:",
            "",
            "| Fact | Artifact | SHA-256 |",
            "|---|---|---|",
        ]
    )
    for key, receipt in sorted(part5["generated_fact_receipts"].items()):
        lines.append(
            f"| `{_md(key)}` | `{_md(receipt['artifact'])}` | `{_md(receipt['sha256'])}` |"
        )
    lines.extend(
        [
            "",
            "### Certificate verdicts after the current refresh",
            "",
            f"**Placeholder behavior:** {part5['certificate_section_status']}.",
            "",
            "| Certificate | Conformant | Exercised | Closed | Executable | Certified | Blockers |",
            "|---|---|---|---|---|---|---:|",
        ]
    )
    for row in part5["certificates"]:
        certified = row["certified"]
        certified_cell = f"{_md(certified['value'])} / {_md(certified['state'])}"
        lines.append(
            f"| `{row['program']}` | {_premise_cell(row['conformant'])} | "
            f"{_premise_cell(row['exercised'])} | {_premise_cell(row['closed'])} | "
            f"{_premise_cell(row['executable'])} | {certified_cell} | "
            f"{_md(row['blocker_count'])} |"
        )
    lines.extend(
        [
            "",
            "### Final integration gate receipt placeholders",
            "",
            "These fields are deliberately placeholders until the final integration lane runs "
            "the required battery against the committed result.",
            "",
            "| Gate | Status |",
            "|---|---|",
        ]
    )
    for gate, status in sorted(part5["gate_receipts"].items()):
        lines.append(f"| `{_md(gate)}` | `{_md(status)}` |")
    lines.extend(
        [
            "",
            "Required final battery: every producer `--check`; `scripts/certify.py --check`; "
            "the whole certification-mutant file including guard reversion; simulated NZ and "
            "DK refreshes; and cross-jurisdiction byte identity against the rebase base.",
            "",
            "## Adjudication questions",
            "",
        ]
    )
    lines.extend(
        f"{number}. {_md(question)}"
        for number, question in enumerate(model["adjudication_questions"], 1)
    )
    lines.extend(
        [
            "",
            "## Final identifiers",
            "",
            f"- Rebase base: `{audit['rebase_base']['sha']}` (`{audit['rebase_base']['ref']}`).",
            f"- Implementation SHA: `{audit['implementation_sha']['value']}` — **placeholder pending final commit**.",
            f"- Rendered output: `{audit['actual_output']}` (ops fallback).",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail unless output is current")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="render Markdown (default) or deterministic JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output path; JSON defaults to stdout, Markdown to V3-AUDIT-OUT.md",
    )
    return parser.parse_args(argv)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        model = build_model()
        rendered = render_markdown(model) if args.format == "markdown" else render_json(model)
    except AuditReportError as exc:
        print(f"NZ v3 audit report error: {exc}", file=sys.stderr)
        return 1

    output = args.output
    if output is None and args.format == "markdown":
        output = DEFAULT_OUTPUT
    if output is None:
        if args.check:
            print("--check with JSON requires --output", file=sys.stderr)
            return 2
        sys.stdout.write(rendered)
        return 0
    if not output.is_absolute():
        output = REPO_ROOT / output

    if args.check:
        try:
            actual = output.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"NZ v3 audit report missing: {output}: {exc}", file=sys.stderr)
            return 1
        if actual != rendered:
            print(f"NZ v3 audit report is stale: {output}", file=sys.stderr)
            return 1
        print(f"NZ v3 audit report is current: {_display_path(output)}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {_display_path(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
